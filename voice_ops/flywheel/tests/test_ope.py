"""Tests for voice_ops.flywheel.ope — Self-Normalised Inverse-Propensity-Score OPE.

Runnable with pytest OR directly:
    python3 -m voice_ops.flywheel.tests.test_ope
Validates the PROPERTIES that make the off-policy estimate trustworthy:
  * a target policy that MIRRORS the behaviour policy recovers ~the logged mean reward
    (the estimator is consistent / unbiased on its own logging distribution);
  * a target that always plays the (better) challenger arm recovers ~that arm's mean;
  * clip_weights caps an exploding importance weight and degrades junk to 0.0;
  * empty / zero-support / malformed input -> (0.0, 0.0) (an honest 'no signal'), never a raise.
NO network, NO ClickHouse — pure synthetic logged rows.
"""
from __future__ import annotations

from voice_ops.flywheel.ope import clip_weights, score_challenger, snips

# Logged calls under a behaviour policy that split traffic 70/30 over two arms.
_LOGGED = [
    {"arm_id": "champ", "propensity": 0.70, "reward": 0.20},
    {"arm_id": "champ", "propensity": 0.70, "reward": 0.10},
    {"arm_id": "champ", "propensity": 0.70, "reward": 0.30},
    {"arm_id": "chall", "propensity": 0.30, "reward": 1.00},
    {"arm_id": "chall", "propensity": 0.30, "reward": 0.90},
    {"arm_id": "chall", "propensity": 0.30, "reward": 1.10},
]


def test_snips_target_equals_behaviour_recovers_the_logged_mean():
    """When the target propensities EQUAL the behaviour propensities every weight is 1, so the
    SNIPS value is the plain logged mean reward (~0.6 here: mean of {.2,.1,.3,1,.9,1.1})."""
    target_mirror = {"champ": 0.70, "chall": 0.30}
    expected_mean = sum(r["reward"] for r in _LOGGED) / len(_LOGGED)
    value, ci = snips(_LOGGED, target_mirror)
    assert abs(value - expected_mean) < 1e-6, (value, expected_mean)
    assert ci >= 0.0, ci


def test_snips_all_challenger_target_recovers_the_challenger_mean():
    """A target that always plays the (clearly better) challenger arm should recover ~that
    arm's mean reward (~1.0), reweighting away the champion rows."""
    target_all_chall = {"champ": 0.0, "chall": 1.0}
    chall_mean = sum(r["reward"] for r in _LOGGED if r["arm_id"] == "chall") / 3
    value, _ci = snips(_LOGGED, target_all_chall)
    assert abs(value - chall_mean) < 1e-6, (value, chall_mean)
    # score_challenger returns exactly the SNIPS point value.
    assert abs(score_challenger(_LOGGED, target_all_chall) - value) < 1e-9


def test_clip_weights_caps_and_floors():
    assert clip_weights(5.0, cap=20.0) == 5.0
    assert clip_weights(50.0, cap=20.0) == 20.0     # capped
    assert clip_weights(-3.0) == 0.0                # negative -> floored to 0
    assert clip_weights(float("nan")) == 0.0        # junk -> 0 (that row does not vote)
    assert clip_weights(float("inf")) == 0.0


def test_snips_empty_and_malformed_inputs_return_zero_no_raise():
    assert snips([], {}) == (0.0, 0.0)
    assert snips(None, None) == (0.0, 0.0)                       # type: ignore[arg-type]
    assert snips(_LOGGED, {}) == (0.0, 0.0)                      # target plays nothing
    # zero behaviour propensity -> no IS support -> dropped -> no signal.
    assert snips([{"arm_id": "x", "propensity": 0.0, "reward": 1.0}], {"x": 1.0}) == (0.0, 0.0)
    # garbage rows are skipped without sinking the estimate.
    assert snips([{"reward": "junk"}, 42, None], {"x": 1.0}) == (0.0, 0.0)  # type: ignore[list-item]
    assert score_challenger([], {}) == 0.0


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for fn in fns:
        fn()
        passed += 1
        print(f"  ok  {fn.__name__}")
    print(f"\n{passed}/{len(fns)} tests passed — test_ope OK")


if __name__ == "__main__":
    _run_all()
