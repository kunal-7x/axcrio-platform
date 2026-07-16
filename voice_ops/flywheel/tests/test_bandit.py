"""Tests for voice_ops.flywheel.bandit — hierarchical Thompson-sampling online learner.

Runnable with pytest OR directly:
    python3 -m voice_ops.flywheel.tests.test_bandit
Validates the PROPERTIES (with a FIXED random.Random seed so the test is deterministic):
  * select_arm favours the higher-alpha (better track record) arm in the MAJORITY of draws;
  * the returned propensity is a true probability in (0, 1] (load-bearing for honest OPE);
  * update_posterior moves the posterior MEAN toward 1 on reward=1 and NEVER mutates the input
    (it returns a NEW ArmPosterior);
  * revert_to_champion picks the best-played, highest-mean arm (the safe kill-switch).
NO network, NO ClickHouse — pure synthetic arms.
"""
from __future__ import annotations

import random

from voice_ops.flywheel.bandit import (
    beta_sample, revert_to_champion, select_arm, update_posterior,
)
from voice_ops.flywheel.schema import ArmPosterior


def _arms():
    """A strong arm (A), a weak arm (B), and a cold-start arm (C)."""
    return [
        ArmPosterior(tenant_id="t1", knob="variant", arm_id="A",
                     alpha=8.0, beta=2.0, plays=30, reward_sum=8.0),   # strong
        ArmPosterior(tenant_id="t1", knob="variant", arm_id="B",
                     alpha=3.0, beta=7.0, plays=30, reward_sum=3.0),   # weak
        ArmPosterior(tenant_id="t1", knob="variant", arm_id="C",
                     alpha=1.0, beta=1.0, plays=0, reward_sum=0.0),    # cold-start
    ]


def test_beta_sample_in_unit_interval_and_guards_degenerate_shapes():
    rng = random.Random(7)
    x = beta_sample(8.0, 2.0, rng=rng)
    assert 0.0 <= x <= 1.0, x
    # non-positive shapes must be guarded (gammavariate would otherwise raise).
    assert 0.0 <= beta_sample(0.0, 0.0, rng=rng) <= 1.0


def test_select_arm_favours_the_higher_alpha_arm_in_the_majority():
    """With a fixed seed, repeated select_arm calls should pick the clearly-better arm A
    MORE OFTEN than any other arm — Thompson sampling exploits the better posterior."""
    rng = random.Random(123)
    counts = {"A": 0, "B": 0, "C": 0}
    draws = 60
    for _ in range(draws):
        arm_id, prop = select_arm(_arms(), epsilon=0.08, explore_cap=0.15, rng=rng)
        assert arm_id in counts
        assert 0.0 < prop <= 1.0, prop  # honest mixture propensity, never 0
        counts[arm_id] += 1
    # A (alpha=8, beta=2) must be the plurality winner, and a clear majority of draws.
    assert counts["A"] == max(counts.values()), counts
    assert counts["A"] > draws / 2, counts


def test_select_arm_propensity_is_a_probability():
    rng = random.Random(9)
    _arm_id, prop = select_arm(_arms(), rng=rng)
    assert 0.0 < prop <= 1.0, prop


def test_select_arm_edge_cases():
    rng = random.Random(1)
    assert select_arm([], rng=rng) == ("", 1.0)
    # a single arm is deterministic with propensity 1.0.
    assert select_arm([_arms()[0]], rng=rng) == ("A", 1.0)


def test_update_posterior_moves_mean_toward_one_on_success():
    arms = _arms()
    a = arms[0]
    before_mean = a.mean()
    upd = update_posterior(a, 1.0, discount=0.98)
    assert isinstance(upd, ArmPosterior)
    # a success pushes the posterior mean UP (toward 1).
    assert upd.mean() > before_mean, (upd.mean(), before_mean)
    assert upd.plays == a.plays + 1
    assert upd.last_reward_ts and upd.ts_iso


def test_update_posterior_failure_moves_mean_down():
    arms = _arms()
    a = arms[0]
    before_mean = a.mean()
    upd = update_posterior(a, 0.0, discount=0.98)
    # a failure pulls the posterior mean DOWN.
    assert upd.mean() < before_mean, (upd.mean(), before_mean)


def test_update_posterior_never_mutates_the_input():
    arms = _arms()
    a = arms[0]
    before_alpha, before_beta, before_plays = a.alpha, a.beta, a.plays
    upd = update_posterior(a, 1.0)
    assert upd is not a
    assert a.alpha == before_alpha and a.beta == before_beta and a.plays == before_plays


def test_update_posterior_clips_out_of_range_reward():
    """A reward of 5.0 (out of the soft-Bernoulli [0,1] range) must not explode the posterior;
    it is squashed to a single success-worth of evidence."""
    arms = _arms()
    a = arms[0]
    upd = update_posterior(a, 5.0, discount=0.98)
    # alpha gained at most ~one success even though reward was 5.0.
    assert upd.alpha <= a.alpha + 1.0 + 1e-6, upd.alpha


def test_revert_to_champion_picks_best_played_arm():
    """The kill-switch must fall back to the highest-mean arm among those with enough plays
    to TRUST (here A: alpha=8/beta=2, 30 plays). Empty -> ''."""
    champ = revert_to_champion(_arms())
    assert champ == "A", champ
    assert revert_to_champion([]) == ""


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for fn in fns:
        fn()
        passed += 1
        print(f"  ok  {fn.__name__}")
    print(f"\n{passed}/{len(fns)} tests passed — test_bandit OK")


if __name__ == "__main__":
    _run_all()
