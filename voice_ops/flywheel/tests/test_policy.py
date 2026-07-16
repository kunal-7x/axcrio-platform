"""Tests for voice_ops.flywheel.policy — B6 contextual per-state move selector (LinTS).

Runnable with pytest OR directly:
    python3 -m voice_ops.flywheel.tests.test_policy
Validates the PROPERTIES of the Linear-Thompson-Sampling selector (Agrawal & Goyal 2013), not magic
numbers:
  * featurize_state is FIXED-LAYOUT (a constant width set by the vocabularies) for any state;
  * mat_inv is a real inverse: A @ A^{-1} ~= I on a small SPD matrix (pure-python Gauss-Jordan);
  * select returns a VALID template_id (one of the arms) with a propensity in (0, 1] -- the logged
    propensity OPE depends on, floored above 0 so a logged turn never carries an un-invertible weight;
  * update_arm INCREASES the chosen arm's pull count, builds a fresh arm at the ridge prior, and does
    not leave an UNRELATED arm's stats mutated.
NO network, NO ClickHouse, NO numpy -- pure synthetic inputs.
"""
from __future__ import annotations

import math
import random

from voice_ops.flywheel import policy as P
from voice_ops.flywheel.policy import featurize_state, mat_inv, select, update_arm
from voice_ops.flywheel.schema import LEAD_TEMPERATURES, OBJECTION_TYPES


def test_featurize_state_is_fixed_layout():
    """The context vector x = [bias, friction/100, arousal/100, one-hot(regime|objection|temp)] has a
    CONSTANT width set by the vocabularies. The intercept is 1.0, the continuous channels are scaled,
    and exactly one regime slot is hot. An unknown category -> an all-zero block (no spurious
    column), and garbage input -> an intercept-padded zero vector -- never a raise."""
    width = 3 + len(P.REGIMES) + len(OBJECTION_TYPES) + len(LEAD_TEMPERATURES)
    x = featurize_state({"state_friction": 80.0, "state_arousal": 40.0,
                         "state_regime": "rising_friction", "objection_type": "price",
                         "lead_temperature": "hot"})
    assert len(x) == width, (len(x), width)
    assert x[0] == 1.0                                        # intercept
    assert abs(x[1] - 0.8) < 1e-9 and abs(x[2] - 0.4) < 1e-9  # scaled continuous channels
    assert sum(x[3:3 + len(P.REGIMES)]) == 1.0               # exactly one regime hot
    # unknown category -> all-zero block, still the contracted width.
    xu = featurize_state({"objection_type": "??nope??", "state_regime": "??"})
    assert len(xu) == width
    # garbage -> intercept-padded zero vector, no raise.
    xg = featurize_state(None)                                # type: ignore[arg-type]
    assert len(xg) == width and xg[0] == 1.0


def test_mat_inv_is_a_real_inverse():
    """mat_inv @ A ~= I on a small SPD matrix (the LinTS precision matrices are small + SPD). A
    singular matrix falls back to the ridge identity rather than raising; [] -> []."""
    A = [[4.0, 1.0, 0.0], [1.0, 3.0, 1.0], [0.0, 1.0, 2.0]]
    Ainv = mat_inv(A)
    for i in range(3):
        for j in range(3):
            v = math.fsum(Ainv[i][k] * A[k][j] for k in range(3))   # A^{-1} @ A
            assert abs(v - (1.0 if i == j else 0.0)) < 1e-6, (i, j, v)
    assert mat_inv([]) == []
    # a singular matrix degrades gracefully (a usable fallback), never raises.
    fallback = mat_inv([[0.0, 0.0], [0.0, 0.0]])
    assert len(fallback) == 2 and len(fallback[0]) == 2


def _two_arm_model(rng):
    """Build a 2-arm LinTS model from logged turns: tpl_value wins on hot/price, tpl_empathy on
    cold/disengaging."""
    arms: dict = {}
    for _ in range(300):
        xs = featurize_state({"state_friction": 30.0, "state_arousal": 60.0,
                              "state_regime": "warming", "objection_type": "price",
                              "lead_temperature": "hot"})
        update_arm(arms, "tpl_value", xs, 1.0)
        update_arm(arms, "tpl_empathy", xs, 0.0)
    for _ in range(300):
        xs = featurize_state({"state_friction": 85.0, "state_arousal": 30.0,
                              "state_regime": "disengaging", "objection_type": "not_interested",
                              "lead_temperature": "cold"})
        update_arm(arms, "tpl_value", xs, 0.0)
        update_arm(arms, "tpl_empathy", xs, 1.0)
    return arms


def test_select_returns_a_valid_template_and_bounded_propensity():
    """select must return a template_id that is one of the model's arms and a propensity in (0, 1]
    (floored above 0 so a logged turn never carries an un-invertible OPE weight). Empty / single-arm
    contracts hold too. rng is injectable so the draw is deterministic."""
    rng = random.Random(13)
    P._MC_SAMPLES = 200                                       # shrink the MC budget for speed
    arms = _two_arm_model(rng)
    tid, prop = select({"state_friction": 30.0, "state_arousal": 60.0, "state_regime": "warming",
                        "objection_type": "price", "lead_temperature": "hot"},
                       arms, epsilon=0.08, rng=rng)
    assert tid in {"tpl_value", "tpl_empathy"}, tid
    assert 0.0 < prop <= 1.0, prop
    # empty / no-arm model -> the honest ('', 1.0) sentinel.
    assert select({}, {}) == ("", 1.0)
    assert select({}, None) == ("", 1.0)
    # single-arm model -> that arm with propensity 1.0 (nothing to choose over).
    one = {"only": arms["tpl_value"]}
    sid, sprop = select({}, one)
    assert sid == "only" and sprop == 1.0


def test_update_arm_increments_plays_and_does_not_mutate_unrelated_arms():
    """update_arm folds one (x, reward) into the named arm: plays++ and the (A, b) sufficient stats
    grow. A fresh arm is created at the ridge prior. Updating arm A must NOT change arm B's stats
    (no cross-arm aliasing)."""
    arms: dict = {}
    x = featurize_state({"state_friction": 30.0, "state_regime": "warming",
                         "objection_type": "price", "lead_temperature": "hot"})
    d = len(x)

    update_arm(arms, "a1", x, 1.0)
    assert arms["a1"]["plays"] == 1
    assert len(arms["a1"]["b_vec"]) == d and len(arms["a1"]["A_flat"]) == d * d

    update_arm(arms, "a2", x, 0.0)                            # a second, unrelated arm
    a2_b_before = list(arms["a2"]["b_vec"])
    a2_plays_before = arms["a2"]["plays"]

    # several more updates to a1 must bump ONLY a1's pull count.
    for _ in range(5):
        update_arm(arms, "a1", x, 1.0)
    assert arms["a1"]["plays"] == 6, arms["a1"]["plays"]
    # a2 untouched by a1's updates.
    assert arms["a2"]["plays"] == a2_plays_before
    assert arms["a2"]["b_vec"] == a2_b_before, "updating a1 must not mutate a2's stats"
    # junk input is swallowed (returns arms), never raises.
    assert update_arm(arms, "a1", [], 1.0) is arms          # empty x -> no-op, same dict back
    # a non-dict `arms` is coerced to a fresh dict and the arm is added there -- never raises.
    coerced = update_arm("not-a-dict", "a1", x, 1.0)         # type: ignore[arg-type]
    assert isinstance(coerced, dict) and "a1" in coerced


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for fn in fns:
        fn()
        passed += 1
        print(f"  ok  {fn.__name__}")
    print(f"\n{passed}/{len(fns)} tests passed — test_policy OK")


if __name__ == "__main__":
    _run_all()
