"""Tests for the Phase 1-2 power upgrades: multimodal axes (engagement / LLM-friction / SER-arousal),
conversational dynamics, the conversion-risk head, and the conformal intervene trigger.
    python3 -m voice_ops.research.tests.test_advanced
"""
from __future__ import annotations

from voice_ops.research.affect_filter import AffectConfig, AffectTracker
from voice_ops.research.conformal import ConformalTrigger
from voice_ops.research.dynamics import compute_dynamics
from voice_ops.research.llm_affect import llm_affect_for_turn
from voice_ops.research.outcome import OutcomeModel


def test_engagement_axis_responds_to_dynamics_obs():
    tr = AffectTracker(AffectConfig())
    base = {"f0_mean_hz": 180, "loudness_db": -26, "speech_rate_sps": 4.2, "confidence": 0.8}
    for _ in range(5):
        tr.update({**base, "engagement_obs": 0.0})
    low = tr.update({**base, "engagement_obs": -1.5}).engagement
    tr2 = AffectTracker(AffectConfig())
    for _ in range(5):
        tr2.update({**base, "engagement_obs": 0.0})
    high = tr2.update({**base, "engagement_obs": 1.5}).engagement
    assert high > low, "engagement axis must move with the dynamics observation"


def test_llm_friction_overrides_prosody_on_friction_axis():
    """A strong LLM friction read should push friction up even when prosody is neutral."""
    tr = AffectTracker(AffectConfig())
    base = {"f0_mean_hz": 180, "loudness_db": -26, "speech_rate_sps": 4.2, "pause_ratio": 0.18, "confidence": 0.8}
    for _ in range(4):
        tr.update(base)
    neutral = tr.update(base).friction
    for _ in range(3):
        last = tr.update({**base, "llm_friction_z": 2.5, "llm_conf": 0.8}).friction
    assert last > neutral + 3, "LLM-read friction should lift the friction axis"


def test_ssl_arousal_channel_drives_arousal():
    tr = AffectTracker(AffectConfig())
    base = {"loudness_db": -26, "speech_rate_sps": 4.2, "confidence": 0.8}
    for _ in range(4):
        tr.update({**base, "ssl_arousal": 0.45, "ssl_conf": 0.85})   # mid baseline
    hi = None
    for _ in range(3):
        hi = tr.update({**base, "ssl_arousal": 0.85, "ssl_conf": 0.85}).arousal
    assert hi > 55, "a high SER arousal estimate should raise the arousal index"


def test_dynamics_backchannel_and_engagement_direction():
    stream = [
        {"speaker": "agent", "transcript": "Hi, is this a good time?", "audio_duration_s": 2.0, "t_sec": 0},
        {"speaker": "caller", "transcript": "haan", "audio_duration_s": 0.5, "turn_latency_ms": 300, "t_sec": 2.5},
        {"speaker": "agent", "transcript": "Great, so about the property...", "audio_duration_s": 3.0, "t_sec": 3.2},
        {"speaker": "caller", "transcript": "mm-hmm yes go on", "audio_duration_s": 1.0, "turn_latency_ms": 250, "t_sec": 6.4},
    ]
    d = compute_dynamics(stream)
    caller_idx = [i for i, t in enumerate(stream) if t["speaker"] == "caller"]
    assert d[caller_idx[0]]["backchannel"] is True
    assert all("engagement_obs" in d[i] for i in caller_idx)
    # quick replies + backchannels → positive engagement obs
    assert d[caller_idx[1]]["engagement_obs"] > -0.5


def test_llm_affect_heuristic_reads_objection_and_intent():
    obj = llm_affect_for_turn("no that is too expensive for my budget")
    assert obj["llm_friction_z"] > 0 and obj["intent"] in ("price-resistant", "objecting")
    pos = llm_affect_for_turn("yes I am interested let's proceed")
    assert pos["llm_friction_z"] < obj["llm_friction_z"] and pos["buying_intent"] > 0


def test_llm_affect_uses_callable_when_given():
    def fake_llm(_prompt):
        return '{"objection":0.9,"hesitation":0.1,"price_concern":0.8,"frustration":0.2,"buying_intent":-0.5,"label":"objecting"}'
    out = llm_affect_for_turn("whatever", llm=fake_llm)
    assert out["source"] == "llm" and out["llm_conf"] == 0.75 and out["llm_friction_z"] > 1.0


def test_outcome_risk_higher_for_frictional_trajectory():
    good = [{"friction": 48, "arousal": 55, "engagement": 58, "turn_latency_ms": 400,
             "intent": "interested", "buying_intent": 0.8} for _ in range(8)]
    bad = [{"friction": 70, "arousal": 48, "engagement": 38, "turn_latency_ms": 1200,
            "intent": "objecting", "buying_intent": 0.0} for _ in range(8)]
    m = OutcomeModel()
    assert m.final_risk(bad) > m.final_risk(good) + 20


def test_outcome_fit_improves_separation():
    won = [([{"friction": 46, "arousal": 56, "engagement": 60, "turn_latency_ms": 350,
              "intent": "interested", "buying_intent": 0.85} for _ in range(6)], True) for _ in range(12)]
    lost = [([{"friction": 72, "arousal": 47, "engagement": 36, "turn_latency_ms": 1300,
               "intent": "objecting", "buying_intent": 0.05} for _ in range(6)], False) for _ in range(12)]
    m = OutcomeModel().fit(won + lost)
    r_won = m.final_risk(won[0][0])
    r_lost = m.final_risk(lost[0][0])
    assert r_lost > r_won, "after fit, lost-pattern risk should exceed won-pattern risk"


def test_conformal_trigger_calibrates_and_fires():
    trig = ConformalTrigger(alpha=0.2)
    won_risks = [10, 20, 25, 30, 35, 40, 45]      # converters rarely high-risk
    trig.calibrate(won_risks)
    assert 30 <= trig.threshold <= 50
    assert trig.fire(trig.threshold + 5, rising=True) is True
    assert trig.fire(trig.threshold + 5, rising=False) is False    # not firing once resolving
    assert trig.fire(trig.threshold - 5, rising=True) is False


def test_conformal_first_trigger_turn():
    trig = ConformalTrigger()
    trig.threshold = 60.0
    curve = [20, 30, 45, 62, 80, 70]
    assert trig.first_trigger_turn(curve) == 3      # first crossing while rising


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)}/{len(fns)} advanced tests passed")


if __name__ == "__main__":
    _run_all()
