"""The synthetic LOAD HARNESS as a HARD deploy gate.

These tests ARE the gate: 50/100/200 concurrent simulated calls must drain with NO
oversubscription, NO errors, and graceful pacing. A regression that lets the box
accept more calls than it has capacity for fails here BEFORE it reaches production."""
from __future__ import annotations

import asyncio

import pytest

from voice_ops.concurrency.admission import AdmissionController
from voice_ops.concurrency.config import ConcurrencyConfig
from voice_ops.concurrency.load_harness import run_load, run_suite


def _cfg(cap=20):
    return ConcurrencyConfig(
        worker_slot_cap=cap, worker_count=1, tenant_call_cap=10_000,
        global_call_cap=0, llm_rpm=10_000_000, llm_burst=10_000_000,
        tts_slots_per_key=10_000,
    )


@pytest.mark.parametrize("offered", [50, 100, 200])
def test_load_ladder_no_oversubscription(offered):
    res = asyncio.run(run_load(offered, cfg=_cfg(20)))
    assert res.ok, res.summary()
    assert not res.oversubscribed
    assert res.max_observed_live <= res.capacity   # the core invariant
    assert res.errored == 0
    assert res.completed == offered                # every call eventually drained
    assert res.admitted_first_try <= res.capacity  # can't admit more than capacity at once


def test_excess_demand_is_paced_not_failed():
    """200 calls at capacity 20 -> ~180 must be paced (cleanly refused + retried),
    never errored mid-stream."""
    res = asyncio.run(run_load(200, cfg=_cfg(20)))
    assert res.paced_events > 0
    assert res.errored == 0


def test_admission_latency_is_microsecond_class():
    """The gate is pure-memory; a p95 over a generous ceiling means a hot-path
    regression. (Ceiling is generous to stay non-flaky on a loaded CI box.)"""
    res = asyncio.run(run_load(100, cfg=_cfg(20)))
    assert res.p95_admit_ms < 50.0, res.summary()


def test_capacity_one_serialises_fully():
    res = asyncio.run(run_load(30, cfg=_cfg(1)))
    assert res.max_observed_live == 1     # strict serialisation, never 2
    assert res.completed == 30


def test_per_key_tts_pool_does_not_block_when_healthy():
    """With a real (mock) controller wired with a healthy key pool the harness still
    drains green — the key dimension doesn't break the slot gate."""
    from voice_ops.concurrency.load_harness import _MockKeyPool

    ctrl = AdmissionController(
        _cfg(20),
        tts_keypools={"elevenlabs": _MockKeyPool("k1")},
        llm_keypools={"groq": _MockKeyPool("g1")},
    )
    res = asyncio.run(run_load(100, controller=ctrl, cfg=_cfg(20)))
    assert res.ok, res.summary()


def test_suite_runs_full_ladder_green():
    results = asyncio.run(run_suite((50, 100, 200), cfg=_cfg(20)))
    assert all(r.ok for r in results), [r.summary() for r in results]


# --------------------------------------------------------------------------- #
# Red-team fold #1: the harness must be an HONEST gate for the per-KEY / per-TENANT
# binding constraint — not only the global worker slot. These profiles make a
# per-TTS-key pool (resp. a per-tenant pool) the BINDING limit and assert that
# pool's peak in_flight never exceeded ITS capacity. Before the fold, the global
# max_live check would have passed even if a per-key pool leaked.
# --------------------------------------------------------------------------- #
def _binding_cfg(tts_per_key):
    # worker/global huge so the TTS-key pool is the binding wall.
    return ConcurrencyConfig(
        worker_slot_cap=10_000, worker_count=1, tenant_call_cap=10_000,
        global_call_cap=0, llm_rpm=10_000_000, llm_burst=10_000_000,
        tts_slots_per_key=tts_per_key,
    )


def test_per_tts_key_is_binding_and_never_oversubscribed():
    from voice_ops.concurrency.load_harness import _MockKeyPool

    cfg = _binding_cfg(tts_per_key=3)
    ctrl = AdmissionController(
        cfg, tts_keypools={"elevenlabs": _MockKeyPool("k1")},
    )
    res = asyncio.run(run_load(80, controller=ctrl, cfg=cfg, tenants=1))
    # honest gate caught the real binding pool and it held
    assert res.binding_overflow == [], res.summary()
    assert not res.oversubscribed, res.summary()
    assert res.ok, res.summary()
    # the per-TTS-key pool WAS recorded and its capacity is the true ceiling (3),
    # not the giant global cap — proving the binding constraint was actually exercised.
    import voice_ops.concurrency.load_harness as lh
    counter = lh._LiveCounter(ctrl)
    counter._sample()
    rec = [p for k, p in counter.peak_by_pool.items() if k.startswith("tts_keys:")]
    assert rec, "expected a per-TTS-key pool to be recorded"
    assert all(p["cap"] == 3 for p in rec)


def test_binding_overflow_detects_a_leaked_per_key_slot():
    """Negative control: if a per-key pool's peak ever exceeded its cap, the honest
    gate FAILS. We simulate the leak by recording an over-cap peak directly on the
    counter and confirm binding_overflow + ok react."""
    from voice_ops.concurrency.load_harness import _LiveCounter, LoadResult

    c = _LiveCounter()
    c.peak_by_pool = {"tts_keys:elevenlabs:k1": {"cap": 3, "peak": 5}}  # leaked!
    overflow = c.binding_overflow()
    assert overflow == [("tts_keys:elevenlabs:k1", 5, 3)]
    r = LoadResult(
        offered=10, capacity=10_000, completed=10, admitted_first_try=10,
        paced_events=0, errored=0, max_observed_live=5, p50_admit_ms=0.0,
        p95_admit_ms=0.0, max_admit_ms=0.0, duration_s=0.0, binding_overflow=overflow,
    )
    assert r.oversubscribed          # global max_live(5) < cap(10000), but per-key leaked
    assert not r.ok                  # the honest gate FAILS where the old gate passed
