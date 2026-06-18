"""AdmissionController — the pre-dial all-or-nothing reservation gate (W24).

Async tests run on a fresh event loop each (no pytest-asyncio dependency — we drive
the coroutine with asyncio.run, matching the codebase's no-extra-plugin posture)."""
from __future__ import annotations

import asyncio

from voice_ops.concurrency.admission import (
    ADMITTED,
    PACE,
    QUEUE,
    AdmissionController,
)
from voice_ops.concurrency.config import ConcurrencyConfig


def run(coro):
    return asyncio.run(coro)


class _Clock:
    def __init__(self, t=0.0):
        self.t = t

    def __call__(self):
        return self.t

    def advance(self, dt):
        self.t += dt


class _MockPool:
    """W13-shaped key pool: .pick() returns a fp or None (exhausted)."""

    def __init__(self, fp="fp1", exhausted=False):
        self.fp = fp
        self.exhausted = exhausted

    def pick(self):
        return None if self.exhausted else self.fp


class _RecordingBus:
    def __init__(self):
        self.events = []

    async def emit(self, ev):
        self.events.append(ev)


def _cfg(**kw):
    base = dict(worker_slot_cap=2, worker_count=1, tenant_call_cap=2,
                global_call_cap=0, llm_rpm=10_000_000, llm_burst=10_000_000,
                tts_slots_per_key=10_000)
    base.update(kw)
    return ConcurrencyConfig(**base)


def test_admits_until_worker_cap_then_queues():
    # global_call_cap high so the WORKER gate (not the derived global cap) is binding
    ctrl = AdmissionController(_cfg(worker_slot_cap=2, tenant_call_cap=10, global_call_cap=100))

    async def go():
        d1 = await ctrl.reserve("t1", "c1")
        d2 = await ctrl.reserve("t1", "c2")
        d3 = await ctrl.reserve("t1", "c3")  # worker full
        assert d1.admitted and d2.admitted
        assert not d3.admitted and d3.outcome == QUEUE and d3.gate == "worker"
        # free one -> next admits
        await ctrl.release(d1.reservation)
        d4 = await ctrl.reserve("t1", "c4")
        assert d4.admitted

    run(go())


def test_tenant_cap_isolates_tenants():
    ctrl = AdmissionController(_cfg(worker_slot_cap=100, tenant_call_cap=1))

    async def go():
        a1 = await ctrl.reserve("tA", "a1")
        a2 = await ctrl.reserve("tA", "a2")   # tenant A at cap
        b1 = await ctrl.reserve("tB", "b1")   # tenant B unaffected
        assert a1.admitted and b1.admitted
        assert not a2.admitted and a2.gate == "tenant"

    run(go())


def test_global_cap_bounds_across_tenants():
    ctrl = AdmissionController(_cfg(worker_slot_cap=100, tenant_call_cap=100,
                                    global_call_cap=2))

    async def go():
        d1 = await ctrl.reserve("tA", "a1")
        d2 = await ctrl.reserve("tB", "b1")
        d3 = await ctrl.reserve("tC", "c1")   # global ceiling hit
        assert d1.admitted and d2.admitted
        assert not d3.admitted and d3.gate == "global"

    run(go())


def test_rollback_on_refusal_leaks_nothing():
    """A refusal at the WORKER gate must release the global + tenant slots it took,
    so a queued call does not permanently consume upstream capacity."""
    ctrl = AdmissionController(_cfg(worker_slot_cap=1, tenant_call_cap=100,
                                    global_call_cap=100))

    async def go():
        d1 = await ctrl.reserve("t1", "c1")   # takes global+tenant+worker
        assert d1.admitted
        d2 = await ctrl.reserve("t1", "c2")   # worker full -> refuse, roll back global+tenant
        assert not d2.admitted and d2.gate == "worker"
        snap = ctrl.snapshot()
        # only ONE global + ONE tenant slot in flight (c2 rolled back fully)
        assert snap["global"]["in_flight"] == 1
        assert snap["tenants"]["t1"]["in_flight"] == 1

    run(go())


def test_release_is_idempotent():
    ctrl = AdmissionController(_cfg(worker_slot_cap=1))

    async def go():
        d = await ctrl.reserve("t1", "c1")
        assert d.admitted
        await ctrl.release(d.reservation)
        await ctrl.release(d.reservation)  # double release -> no-op
        d2 = await ctrl.reserve("t1", "c2")
        assert d2.admitted  # slot truly freed exactly once
        assert ctrl.snapshot()["worker"]["in_flight"] == 1

    run(go())


def test_llm_key_pool_exhausted_paces():
    ctrl = AdmissionController(
        _cfg(),
        llm_keypools={"groq": _MockPool(exhausted=True)},
    )

    async def go():
        d = await ctrl.reserve("t1", "c1", provider_llm="groq")
        assert not d.admitted and d.outcome == PACE and d.gate == "llm_key"
        # nothing leaked: worker/global/tenant all rolled back
        snap = ctrl.snapshot()
        assert snap["global"]["in_flight"] == 0
        assert snap["worker"]["in_flight"] == 0

    run(go())


def test_tts_key_pool_exhausted_paces():
    ctrl = AdmissionController(
        _cfg(),
        tts_keypools={"elevenlabs": _MockPool(exhausted=True)},
    )

    async def go():
        d = await ctrl.reserve("t1", "c1", provider_tts="elevenlabs")
        assert not d.admitted and d.outcome == PACE and d.gate == "tts_key"
        assert ctrl.snapshot()["worker"]["in_flight"] == 0

    run(go())


def test_tts_slot_per_key_caps_concurrency():
    clk = _Clock()
    ctrl = AdmissionController(
        _cfg(tts_slots_per_key=1, worker_slot_cap=100, tenant_call_cap=100),
        tts_keypools={"elevenlabs": _MockPool(fp="k1")},
        clock=clk,
    )

    async def go():
        d1 = await ctrl.reserve("t1", "c1", provider_tts="elevenlabs")
        d2 = await ctrl.reserve("t1", "c2", provider_tts="elevenlabs")  # same TTS key, slot full
        assert d1.admitted
        assert not d2.admitted and d2.gate == "tts_slot" and d2.outcome == QUEUE
        await ctrl.release(d1.reservation)
        d3 = await ctrl.reserve("t1", "c3", provider_tts="elevenlabs")
        assert d3.admitted

    run(go())


def test_per_tenant_llm_budget_is_denial_of_wallet_guard():
    clk = _Clock()
    # 60 rpm = 1/sec, burst 2 -> only 2 calls before refill
    ctrl = AdmissionController(
        _cfg(llm_rpm=60, llm_burst=2, worker_slot_cap=100, tenant_call_cap=100),
        clock=clk,
    )

    async def go():
        assert (await ctrl.reserve("t1", "c1")).admitted
        assert (await ctrl.reserve("t1", "c2")).admitted
        d3 = await ctrl.reserve("t1", "c3")  # budget exhausted
        assert not d3.admitted and d3.gate == "llm_tenant" and d3.outcome == PACE
        clk.advance(1.0)                      # +1 token
        assert (await ctrl.reserve("t1", "c4")).admitted

    run(go())


def test_missing_identity_is_failed_closed():
    ctrl = AdmissionController(_cfg())

    async def go():
        d = await ctrl.reserve("", "c1")
        assert not d.admitted and d.gate == "identity"
        d2 = await ctrl.reserve("t1", "")
        assert not d2.admitted and d2.gate == "identity"

    run(go())


def test_emits_admit_and_pace_on_w8_bus():
    bus = _RecordingBus()
    ctrl = AdmissionController(_cfg(worker_slot_cap=1), event_bus=bus)

    async def go():
        await ctrl.reserve("t1", "c1")   # admitted
        await ctrl.reserve("t1", "c2")   # queued
        names = [e.name for e in bus.events]
        assert "call_admitted" in names
        assert "call_paced" in names
        # tenant isolation on the wire: events carry the tenant_id
        assert all(e.tenant_id == "t1" for e in bus.events)

    run(go())


def test_renew_keeps_a_long_call_from_being_swept_into_oversubscription():
    """Red-team fold (W24, finding #2): a call longer than reserve_ttl_s must heartbeat
    its reservation through the CONTROLLER (not just SlotPool) or its slots get swept
    while still live and a second call admits into the phantom-free slot.

    With renew(): the long call's slots survive the TTL window, so the worker stays at
    cap and a second call is correctly QUEUED — no oversubscription."""
    clk = _Clock()
    ctrl = AdmissionController(
        _cfg(worker_slot_cap=1, tenant_call_cap=10, global_call_cap=10,
             reserve_ttl_s=300.0),
        clock=clk,
    )

    async def go():
        d1 = await ctrl.reserve("t1", "c1")            # long call holds the only slot
        assert d1.admitted
        # 5 minutes pass; the seam heartbeats every 100s (< ttl) for the live call
        for _ in range(4):
            clk.advance(100.0)
            assert ctrl.renew(d1.reservation) is True  # slot TTL extended, lease alive
        # now > 300s of wall time elapsed, but the slot is STILL held by the live call
        assert ctrl.snapshot()["worker"]["in_flight"] == 1
        d2 = await ctrl.reserve("t1", "c2")            # must be refused, NOT admitted
        assert not d2.admitted and d2.gate == "worker"
        # teardown frees exactly the live lease
        await ctrl.release(d1.reservation)
        assert ctrl.snapshot()["worker"]["in_flight"] == 0

    run(go())


def test_renew_is_noop_after_release_and_for_swept_lease():
    """renew() returns False once a reservation is released (the seam stops the
    heartbeat) and for a lease already swept by TTL expiry (no resurrection)."""
    clk = _Clock()
    ctrl = AdmissionController(_cfg(worker_slot_cap=1, reserve_ttl_s=100.0), clock=clk)

    async def go():
        d1 = await ctrl.reserve("t1", "c1")
        assert d1.admitted
        await ctrl.release(d1.reservation)
        assert ctrl.renew(d1.reservation) is False     # released -> stop heartbeating
        assert ctrl.renew(None) is False
        # a lease that was NOT renewed expires and is swept -> renew can't resurrect it
        d2 = await ctrl.reserve("t1", "c2")
        assert d2.admitted
        clk.advance(101.0)                              # ttl elapsed, c2 not renewed
        assert ctrl.renew(d2.reservation) is False      # swept -> no-op False
        # the swept slot is genuinely free for a new call
        d3 = await ctrl.reserve("t1", "c3")
        assert d3.admitted

    run(go())


def test_bus_failure_never_breaks_admission():
    class _DeadBus:
        async def emit(self, ev):
            raise RuntimeError("redis down")

    ctrl = AdmissionController(_cfg(worker_slot_cap=1), event_bus=_DeadBus())

    async def go():
        d = await ctrl.reserve("t1", "c1")
        assert d.admitted  # a dead bus does NOT fail the call (earner-safe)

    run(go())
