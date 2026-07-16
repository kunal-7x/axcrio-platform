"""Tests for voice_ops.flywheel.ope — B2 anytime-valid OPE confidence sequence + log-smoothing.

Runnable with pytest OR directly:
    python3 -m voice_ops.flywheel.tests.test_ope_cs
Validates the two POWER-UP additions to ope.py (snips_cs, log_smooth_weight), not magic numbers:
  * ope.snips_cs returns an ORDERED anytime-valid interval cs_lower <= value <= cs_upper and recovers
    ~the mean reward when the target policy mirrors the behaviour policy (every weight ~1);
  * ope.log_smooth_weight (Sakhi 2024 pessimistic smoothing) is STRICTLY BELOW the hard clip on the
    dangerous tail (w large) and is MONOTONE INCREASING in w.
NO network, NO ClickHouse, NO numpy -- pure synthetic logged rows.
"""
from __future__ import annotations

from voice_ops.flywheel.ope import clip_weights, log_smooth_weight, snips, snips_cs

# Logged calls under a behaviour policy that split traffic 70/30 over two arms.
_LOGGED = [
    {"arm_id": "champ", "propensity": 0.70, "reward": 0.20},
    {"arm_id": "champ", "propensity": 0.70, "reward": 0.10},
    {"arm_id": "champ", "propensity": 0.70, "reward": 0.30},
    {"arm_id": "chall", "propensity": 0.30, "reward": 1.00},
    {"arm_id": "chall", "propensity": 0.30, "reward": 0.90},
    {"arm_id": "chall", "propensity": 0.30, "reward": 1.10},
]


def test_snips_cs_interval_is_ordered_and_brackets_the_value():
    """The anytime-valid CS must be ORDERED (lower <= value <= upper) -- the optional-stopping-safe
    interval the daily-peeking worker reads. A non-degenerate stream yields a real (non-zero-width)
    interval."""
    value, lo, hi = snips_cs(_LOGGED, {"champ": 0.0, "chall": 1.0}, alpha=0.05)
    assert lo <= value <= hi, (lo, value, hi)
    assert hi - lo > 0.0, "expected a non-degenerate anytime-valid interval"
    # a single surviving row has no width to claim -> an honest point interval.
    one = snips_cs([{"arm_id": "chall", "propensity": 0.30, "reward": 1.0}], {"chall": 0.30})
    assert one[0] == one[1] == one[2], one
    # dormant-safe: empty / no-support input -> (0,0,0), never raises.
    assert snips_cs([], {}) == (0.0, 0.0, 0.0)
    assert snips_cs(None, None) == (0.0, 0.0, 0.0)            # type: ignore[arg-type]
    assert snips_cs(_LOGGED, {}) == (0.0, 0.0, 0.0)           # target plays nothing


def test_snips_cs_recovers_the_mean_when_target_mirrors_behaviour():
    """When the target propensities EQUAL the behaviour propensities every clipped IPW weight is 1,
    so the Horvitz-Thompson per-row mean g_i = w_i*r_i == r_i and the CS point value recovers the
    plain logged mean reward (~0.6 over {.2,.1,.3,1,.9,1.1}), bracketed by the CS."""
    mirror = {"champ": 0.70, "chall": 0.30}
    expected_mean = sum(r["reward"] for r in _LOGGED) / len(_LOGGED)
    value, lo, hi = snips_cs(_LOGGED, mirror, alpha=0.05)
    assert abs(value - expected_mean) < 1e-6, (value, expected_mean)
    assert lo <= value <= hi, (lo, value, hi)
    # cross-check: the self-normalised snips point also recovers that mean on a mirror target.
    sn_value, _ci = snips(_LOGGED, mirror)
    assert abs(sn_value - expected_mean) < 1e-6, (sn_value, expected_mean)


def test_log_smooth_weight_below_clip_on_the_tail_and_monotone():
    """Sakhi 2024 pessimistic log-smoothing: on the dangerous tail (a large weight from a near-zero
    behaviour propensity) the smoothed weight is STRICTLY BELOW the hard clip -- it shrinks an over-
    claimed challenger value DOWN (the anti-Goodhart direction). It is also monotone increasing in w
    and ~w for small w (faithful in the well-supported regime)."""
    big = 50.0
    smoothed = log_smooth_weight(big, lam=0.1)
    assert smoothed < big, (smoothed, big)                          # sub-linear / saturating
    assert smoothed < clip_weights(big, cap=20.0), (smoothed, clip_weights(big, cap=20.0))
    # monotone increasing across the whole positive range.
    assert log_smooth_weight(0.5) < log_smooth_weight(1.0) < log_smooth_weight(2.0) \
        < log_smooth_weight(10.0) < log_smooth_weight(100.0)
    # faithful to the raw weight in the body (small w): relative error well under 1%.
    assert abs(log_smooth_weight(0.01, lam=0.1) - 0.01) / 0.01 < 0.01
    # lambda -> 0 / degenerate lambda recovers the raw weight (no smoothing).
    assert abs(log_smooth_weight(3.0, lam=0.0) - 3.0) < 1e-9
    # junk / negative -> 0 (no support, does not vote), never raises.
    assert log_smooth_weight(-5.0) == 0.0
    assert log_smooth_weight(float("nan")) == 0.0
    assert log_smooth_weight(float("inf")) == 0.0


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for fn in fns:
        fn()
        passed += 1
        print(f"  ok  {fn.__name__}")
    print(f"\n{passed}/{len(fns)} tests passed — test_ope_cs OK")


if __name__ == "__main__":
    _run_all()
