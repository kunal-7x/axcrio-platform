"""Tests for the Phase 3-4 in-call modules: realtime arousal inference (degradation chain), the
adaptive-TTS decision logic, and the fail-safe gating (everything off by default).
    python3 -m voice_ops.research.tests.test_realtime
"""
from __future__ import annotations

import os

from voice_ops.research import adaptive_tts, agent_tap
from voice_ops.research.realtime import infer_arousal


def test_realtime_arousal_proxy_monotonic():
    """Louder, higher-pitch audio should read as higher arousal than quiet low audio (proxy or ONNX)."""
    try:
        import numpy as np
    except Exception:
        return
    sr = 16000
    t = np.linspace(0, 1.0, sr, endpoint=False)
    loud_high = 0.5 * np.sin(2 * np.pi * 240 * t)
    quiet_low = 0.03 * np.sin(2 * np.pi * 110 * t)
    a_hi, c_hi, src = infer_arousal(loud_high.astype("float32"), sr)
    a_lo, c_lo, _ = infer_arousal(quiet_low.astype("float32"), sr)
    assert 0.0 <= a_lo <= 1.0 and 0.0 <= a_hi <= 1.0
    assert a_hi >= a_lo, f"loud/high arousal {a_hi} should be >= quiet/low {a_lo} ({src})"


def test_realtime_handles_garbage_without_raising():
    a, c, src = infer_arousal([], 16000)          # empty input → energy/none proxy, never raises
    assert 0.0 <= a <= 1.0 and 0.0 <= c <= 1.0


def test_adaptive_tts_decide_directions_and_never_pitch():
    de = adaptive_tts.decide("rising_friction", friction=66, engagement=45, conversion_risk=70)
    assert de and de["speed"] < 1.0 and de["stability"] >= 0.7      # de-escalate: slower, steadier
    assert "pitch" not in de                                        # NEVER pitch (Benus 2018)
    re = adaptive_tts.decide("disengaging", friction=52, engagement=38, conversion_risk=40)
    assert re and re["speed"] > 1.0                                 # re-engage: livelier
    assert adaptive_tts.decide("steady", 50, 50, 20) is None        # no change when calm


def test_adaptive_tts_disabled_by_default(monkeypatch_env=None):
    os.environ.pop("FAMIT_RESEARCH_ADAPTIVE_TTS", None)
    ctrl = adaptive_tts.AdaptiveTtsController()
    applied = []
    out = ctrl.step({"regime": "rising_friction", "friction": 70, "engagement": 40, "conversion_risk": 80},
                    apply_fn=lambda s, st: applied.append((s, st)))
    assert out is None and applied == []           # OFF by default → no behavior change


def test_adaptive_tts_applies_when_enabled_and_dedupes():
    os.environ["FAMIT_RESEARCH_ADAPTIVE_TTS"] = "1"
    try:
        ctrl = adaptive_tts.AdaptiveTtsController()
        applied = []
        s1 = ctrl.step({"regime": "rising_friction", "friction": 70, "engagement": 40, "conversion_risk": 80},
                       apply_fn=lambda s, st: applied.append((s, st)))
        assert s1 is not None and len(applied) == 1
        assert SPEED_OK(applied[0][0]) and "pitch" not in s1
        # same state again → cache-safe no-op (no redundant update_options)
        s2 = ctrl.step({"regime": "rising_friction", "friction": 70, "engagement": 40, "conversion_risk": 80},
                       apply_fn=lambda s, st: applied.append((s, st)))
        assert s2 is None and len(applied) == 1
    finally:
        os.environ.pop("FAMIT_RESEARCH_ADAPTIVE_TTS", None)


def SPEED_OK(s):
    return adaptive_tts.SPEED_MIN <= s <= adaptive_tts.SPEED_MAX


def test_agent_tap_disabled_by_default_returns_none():
    os.environ.pop("FAMIT_RESEARCH_REALTIME", None)
    assert agent_tap.maybe_start(object()) is None  # flag off → never spawns, zero overhead


def test_live_session_disabled_returns_none():
    os.environ.pop("FAMIT_RESEARCH_REALTIME", None)
    os.environ.pop("FAMIT_RESEARCH_ADAPTIVE_TTS", None)
    from voice_ops.research import live
    assert live.maybe_start(object(), tenant_id="t", call_id="c") is None


def test_live_session_on_turn_runs_and_drives_adaptive_tts():
    os.environ["FAMIT_RESEARCH_ADAPTIVE_TTS"] = "1"   # no tap (realtime off), just the live loop + TTS
    os.environ.pop("FAMIT_RESEARCH_REALTIME", None)

    def fake_llm(prompt):                             # a real model read (branch on the turn content)
        if "expensive" in prompt or "budget" in prompt:
            return '{"objection":0.9,"price_concern":0.9,"hesitation":0.2,"frustration":0.3,"buying_intent":-0.4,"label":"price-resistant"}'
        return '{"objection":-0.5,"price_concern":-0.5,"hesitation":-0.3,"frustration":-0.5,"buying_intent":0.7,"label":"interested"}'
    try:
        from voice_ops.research.live import LiveResearchSession
        s = LiveResearchSession("t", "c", llm=fake_llm)
        applied = []
        cb = lambda sp, st_: applied.append((sp, st_))
        for _ in range(5):                            # establish a low-friction baseline
            s.on_turn("yes okay that sounds good", apply_prosody=cb)
        base_fr = s.last_state.friction
        st = None
        for _ in range(4):                            # strong objection → friction up → de-escalate
            st = s.on_turn("no that is far too expensive for my budget", apply_prosody=cb)
        assert st is not None and st.friction > base_fr + 4, f"friction {st.friction} should rise over baseline {base_fr}"
        assert applied, "adaptive TTS should have applied a prosody change on rising friction"
        assert all(adaptive_tts.SPEED_MIN <= sp <= adaptive_tts.SPEED_MAX for sp, _ in applied)
    finally:
        os.environ.pop("FAMIT_RESEARCH_ADAPTIVE_TTS", None)


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)}/{len(fns)} realtime/adaptive tests passed")


if __name__ == "__main__":
    _run_all()
