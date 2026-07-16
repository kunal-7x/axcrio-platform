"""Tests for the Famit Research scientific core. Runnable with pytest OR directly:
    python3 -m voice_ops.research.tests.test_affect_filter
Validates the PROPERTIES that make the model defensible (mean-reversion, confidence-weighting,
regime detection, demo consistency) — not magic numbers.
"""
from __future__ import annotations

import math

from voice_ops.research.affect_filter import (
    INDEX_CENTER, AffectConfig, AffectTracker, BaselineCalibrator,
)
from voice_ops.research.demo import demo_calls, synthetic_call
from voice_ops.research.extractor import extract_call, summarize
from voice_ops.research.features import turn_features_from_metadata


def test_baseline_zscore_centers_on_caller_mean():
    cal = BaselineCalibrator(warmup=2)
    for _ in range(8):
        cal.z("f0", 180.0)              # constant input → z must collapse toward 0
    assert abs(cal.z("f0", 180.0)) < 0.2
    assert cal.z("f0", 260.0) > 0.5     # a spike above baseline reads positive


def test_mean_reversion_relaxes_to_baseline():
    """Establish a neutral resting baseline, spike arousal, then confirm the OU process pulls
    the state back DOWN toward 50 once the stimulation stops (mean reversion)."""
    tr = AffectTracker(AffectConfig(mode="kalman"))
    neutral = {"f0_mean_hz": 180, "loudness_db": -26, "speech_rate_sps": 4.2, "confidence": 0.9}
    hot_obs = {"f0_mean_hz": 290, "loudness_db": -15, "speech_rate_sps": 7.0, "confidence": 0.9}
    for _ in range(7):                  # > baseline_lock → resting baseline frozen at "neutral"
        tr.update(neutral)
    hot = None
    for _ in range(4):                  # spike
        hot = tr.update(hot_obs).arousal
    assert hot > 56, f"arousal should rise above baseline on a hot streak (got {hot})"
    last = hot
    for _ in range(10):                 # stimulation stops → relax back toward 50
        last = tr.update(neutral).arousal
    assert last < hot, "arousal should relax after the hot streak ends"
    assert abs(last - INDEX_CENTER) < abs(hot - INDEX_CENTER), "should end closer to baseline than the peak"


def test_low_confidence_moves_state_less():
    """A low-confidence (noisy 8 kHz) turn must shift the latent state LESS than a high-confidence
    one with the same observation — the whole point of confidence-weighted measurement noise."""
    def shift(conf):
        tr = AffectTracker(AffectConfig())
        for _ in range(3):              # establish a baseline first
            tr.update({"f0_mean_hz": 180, "loudness_db": -26, "speech_rate_sps": 4.2, "confidence": 0.9})
        before = tr.update({"f0_mean_hz": 180, "loudness_db": -26, "speech_rate_sps": 4.2, "confidence": 0.9}).arousal
        after = tr.update({"f0_mean_hz": 300, "loudness_db": -14, "speech_rate_sps": 7.0, "confidence": conf}).arousal
        return abs(after - before)
    assert shift(0.9) > shift(0.2), "high-confidence turn should move the state more"


def test_confidence_zero_is_preserved_not_coerced():
    """A turn with explicit confidence=0.0 (e.g. fully unvoiced) must be trusted LESS than a
    high-confidence turn — the `... or 0.5` bug would have coerced 0.0 → 0.5."""
    def shift(conf):
        tr = AffectTracker(AffectConfig())
        for _ in range(4):
            tr.update({"f0_mean_hz": 180, "loudness_db": -26, "speech_rate_sps": 4.2, "confidence": 0.9})
        before = tr.update({"f0_mean_hz": 180, "loudness_db": -26, "speech_rate_sps": 4.2, "confidence": 0.9}).arousal
        after = tr.update({"f0_mean_hz": 300, "loudness_db": -14, "speech_rate_sps": 7.0, "confidence": conf}).arousal
        return abs(after - before)
    assert shift(0.0) < shift(0.9), "a 0.0-confidence turn must move the state less than a 0.9 one"


def test_nan_inf_features_do_not_poison_the_trace():
    """One NaN/inf feature must not permanently corrupt the running baseline — the next clean turn
    must still produce a finite arousal/friction."""
    tr = AffectTracker(AffectConfig())
    for bad in (float("nan"), float("inf"), float("-inf")):
        st = tr.update({"f0_mean_hz": bad, "loudness_db": bad, "speech_rate_sps": bad,
                        "pause_ratio": bad, "valence_hint": bad, "confidence": bad})
        assert math.isfinite(st.arousal) and math.isfinite(st.friction)
        assert math.isfinite(st.arousal_var) and math.isfinite(st.friction_var)
    clean = tr.update({"f0_mean_hz": 200, "loudness_db": -22, "speech_rate_sps": 5.0, "confidence": 0.7})
    assert math.isfinite(clean.arousal) and 0 <= clean.arousal <= 100


def test_summary_started_iso_from_first_turn():
    rows = extract_call("t", "c1", [
        {"transcript": "hi", "audio_duration_s": 2.0, "t_sec": 0.0},
        {"transcript": "yes ok", "audio_duration_s": 2.0, "t_sec": 3.0},
    ], started_iso="2026-06-20T10:00:00.000Z")
    summ = summarize(rows)
    assert summ.started_iso == rows[0].ts_iso  # header time tracks the call start, not "now"


def test_uncertainty_band_is_positive_and_finite():
    tr = AffectTracker(AffectConfig())
    st = tr.update({"f0_mean_hz": 200, "loudness_db": -22, "speech_rate_sps": 5.0, "confidence": 0.6})
    assert st.arousal_var > 0 and math.isfinite(st.arousal_var)
    assert 0 <= st.arousal <= 100 and 0 <= st.friction <= 100


def test_regime_detection_flags_rising_friction():
    rows, summ = synthetic_call("t", "demo-call-7739", "objection_lost")
    assert any(r.regime in ("rising_friction", "disengaging") for r in rows)
    assert summ.friction_peak > summ.friction_mean
    # objection_lost should end MORE frictional than it began
    assert rows[-1].friction > rows[0].friction


def test_smooth_close_stays_low_friction():
    rows, summ = synthetic_call("t", "demo-call-7740", "smooth_close")
    assert summ.friction_mean < 58, "a smooth close should not read as high friction"
    assert summ.converted is True


def test_demo_calls_shape():
    calls = demo_calls("demo")
    assert len(calls) >= 6
    for rows, summ in calls:
        assert len(rows) >= 8
        assert all(0 <= r.arousal <= 100 and 0 <= r.friction <= 100 for r in rows)
        assert all(r.source == "demo" for r in rows)
        assert summ.turns == len(rows)


def test_metadata_path_speech_rate_plausible():
    f = turn_features_from_metadata(
        transcript="haan ji main interested hoon batao kya price hai",
        audio_duration_s=3.0, silence_s=0.4)
    assert 1.0 < f["speech_rate_sps"] < 9.0
    assert f["source"] == "asr_metadata" and f["low_conf"] is True
    assert 0 <= f["pause_ratio"] <= 1


def test_extract_call_metadata_pipeline():
    turns = [
        {"transcript": "hello yes", "audio_duration_s": 2.0, "silence_s": 0.3, "turn_latency_ms": 400},
        {"transcript": "that is too expensive no", "audio_duration_s": 3.0, "silence_s": 0.8, "turn_latency_ms": 900},
        {"transcript": "okay maybe the emi helps", "audio_duration_s": 2.5, "silence_s": 0.3, "turn_latency_ms": 500},
    ]
    rows = extract_call("t", "c1", turns)
    assert len(rows) == 3
    summ = summarize(rows, duration_s=8.0, outcome="warm", converted=False)
    assert summ.turns == 3 and summ.source == "asr_metadata"


def test_acoustic_path_on_synthetic_tone_if_librosa():
    """If librosa is installed, a 200 Hz tone should be tracked near 200 Hz by pyin."""
    try:
        import numpy as np
        import librosa  # noqa: F401
    except Exception:
        return
    from voice_ops.research.features import extract_acoustics
    sr = 16000
    t = np.linspace(0, 1.0, sr, endpoint=False)
    y = 0.3 * np.sin(2 * np.pi * 200 * t)
    f = extract_acoustics(y, sr, transcript="testing one two three")
    assert f["source"] == "acoustic_pyin"
    assert 150 < f["f0_mean_hz"] < 260, f"pyin F0 {f['f0_mean_hz']} not near 200"
    assert 0 <= f["confidence"] <= 0.95


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for fn in fns:
        fn()
        passed += 1
        print(f"  ok  {fn.__name__}")
    print(f"\n{passed}/{len(fns)} tests passed")


if __name__ == "__main__":
    _run_all()
