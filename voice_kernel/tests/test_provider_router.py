"""W5 tests — ProviderRouter: authoritative selection (lean -> Sarvam, never a
silent EL swap), LOGGED fallback (not silent), health-scored key pool, contract
conformance, build_kernel registration, 0 droplet imports."""
from __future__ import annotations

import logging

from voice_kernel.contracts import CallContext, ProviderChoice, ProviderRouter
from voice_kernel.kernel import build_kernel
from voice_kernel.packet import PacketMeta
from voice_kernel.providers import (
    SARVAM_WS_CONTRACT,
    ProviderDiagnostics,
    build_provider_router,
)
from voice_kernel.providers.keypool import KeyPool
from voice_kernel.providers.router import DefaultProviderRouter


def _ctx(fields: dict, call_id="c1") -> CallContext:
    meta = PacketMeta(tenant_id="t1", campaign_id="cam1", call_id=call_id, room="r1")
    return CallContext(meta=meta, fields=fields)


def test_router_conforms_to_protocol():
    r = DefaultProviderRouter()
    assert isinstance(r, ProviderRouter)


# --------------------------------------------------------------------------- #
# authoritative selection: lean plan -> Sarvam (the live bug was always EL)
# --------------------------------------------------------------------------- #
def test_lean_plan_selects_sarvam_not_silent_elevenlabs():
    r = DefaultProviderRouter()
    choice = r.resolve(_ctx({"plan": "lean"}))
    assert choice.tts == "sarvam", "lean tier MUST resolve to Sarvam, never silent EL"
    assert "sarvam" in r.diag.selected_tts
    assert not r.diag.silent_swap


def test_premium_plan_selects_elevenlabs():
    r = DefaultProviderRouter()
    assert r.resolve(_ctx({"plan": "premium"})).tts == "elevenlabs"


def test_explicit_override_wins():
    r = DefaultProviderRouter()
    assert r.resolve(_ctx({"plan": "premium", "tts_provider": "sarvam"})).tts == "sarvam"


def test_diagnostics_record_selected_and_no_silent_swap():
    r = DefaultProviderRouter()
    r.resolve(_ctx({"plan": "lean"}))
    d = r.diag
    assert isinstance(d, ProviderDiagnostics)
    assert d.selected_tts == "sarvam"
    assert d.actual_tts == "sarvam"
    assert d.trail  # a decision trail exists (loud, not silent)


# --------------------------------------------------------------------------- #
# fallback is LOGGED, not silent
# --------------------------------------------------------------------------- #
def test_fallback_is_logged_not_silent(caplog):
    r = DefaultProviderRouter()
    r.resolve(_ctx({"plan": "lean"}))  # seeds diag
    with caplog.at_level(logging.INFO, logger="voice_kernel.providers"):
        alt = r.on_error("sarvam", 500)
    assert alt.tts == "elevenlabs"
    assert "fallback" in alt.reason.lower()
    # the fallback decision was LOGGED
    assert any("FALLBACK" in rec.message or "fallback" in rec.message.lower() for rec in caplog.records)


def test_429_rotates_same_provider_when_keys_healthy():
    pools = {"sarvam": KeyPool("sarvam", ("k1", "k2"))}
    r = DefaultProviderRouter(pools=pools)
    r.resolve(_ctx({"plan": "lean"}))
    out = r.on_error("sarvam", 429)
    assert out.tts == "sarvam"  # rotate key, stay on Sarvam
    assert "rotate" in out.reason.lower()


def test_429_falls_back_when_no_healthy_key(monkeypatch):
    # a pool whose only key is demoted -> no healthy key -> loud fallback
    t = {"v": 0.0}
    pool = KeyPool("sarvam", ("k1",), cooldown_s=100.0)
    pool._now = lambda: t["v"]
    pool.report_failure("k1", 429)  # demote the only key
    assert pool.healthy_count == 0
    r = DefaultProviderRouter(pools={"sarvam": pool})
    r.resolve(_ctx({"plan": "lean"}))
    out = r.on_error("sarvam", 429)
    assert out.tts == "elevenlabs"  # loud fallback (no silent stick on dead key)


# --------------------------------------------------------------------------- #
# health-scored key pool
# --------------------------------------------------------------------------- #
def test_keypool_demotes_on_429_and_recovers_after_cooldown():
    t = {"v": 0.0}
    pool = KeyPool("sarvam", ("k1", "k2"), cooldown_s=30.0)
    pool._now = lambda: t["v"]
    assert pool.healthy_count == 2
    pool.report_failure("k1", 429)
    assert pool.healthy_count == 1  # k1 demoted
    assert pool.pick() == "k2"      # routes to the healthy key
    t["v"] = 31.0                   # cooldown elapsed
    assert pool.healthy_count == 2  # k1 recovered


def test_keypool_400_does_not_demote_key():
    pool = KeyPool("sarvam", ("k1",))
    pool.report_failure("k1", 400)  # bad-request is not a key problem
    assert pool.healthy_count == 1


def test_keypool_exhausted_returns_none_loud():
    t = {"v": 0.0}
    pool = KeyPool("sarvam", ("k1",), cooldown_s=100.0)
    pool._now = lambda: t["v"]
    pool.report_failure("k1", 429)
    assert pool.pick() is None  # explicit None, not a silent stale key


# --------------------------------------------------------------------------- #
# WS contract + registration + 0 droplet imports
# --------------------------------------------------------------------------- #
def test_sarvam_ws_contract_present():
    assert SARVAM_WS_CONTRACT["min_buffer_size"] > 0
    assert SARVAM_WS_CONTRACT["max_chunk_length"] >= SARVAM_WS_CONTRACT["min_buffer_size"]
    assert SARVAM_WS_CONTRACT["output_sample_rate"] == 8000
    assert SARVAM_WS_CONTRACT["output_audio_codec"] == "mulaw"


def test_router_registers_via_build_kernel():
    r = build_provider_router(sarvam_keys=("k1",), elevenlabs_keys=("e1",))
    k = build_kernel(router=r)
    assert k.svc.router is r
    assert k.svc.router.resolve(_ctx({"plan": "lean"})).tts == "sarvam"


def test_no_droplet_agent_import_in_providers_package():
    import ast
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[1] / "providers"
    banned = ("droplet_work", "agent", "aim_voice_agent", "caller")
    for f in root.glob("*.py"):
        tree = ast.parse(f.read_text(encoding="utf-8"), filename=str(f))
        for node in ast.walk(tree):
            mods = []
            if isinstance(node, ast.Import):
                mods = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                mods = [node.module or ""]
            for m in mods:
                top = m.split(".")[0]
                assert top not in banned, f"{f} imports {m}"
