"""Tests for voice_ops.flywheel.ensemble — B1 PESSIMISTIC reward ensemble (anti-over-optimization).

Runnable with pytest OR directly:
    python3 -m voice_ops.flywheel.tests.test_ensemble
Validates the PROPERTIES that make the 4-head ensemble Goodhart-safe (Gao scaling-laws / WARM / UWO /
ODIN), not magic numbers:
  * the LCB reward is PESSIMISTIC: lcb_reward <= mu always (it can only DISCOUNT the mean);
  * more head DISAGREEMENT (higher variance) -> a LOWER lcb (the UWO mean - lambda*var penalty bites);
  * a MISSING head is EXCLUDED, never folded in as a fabricated 0 datapoint;
  * fuse_pessimistic flips a RewardComponents to ensemble_computed=True and rc.optimized()==lcb_reward
    (the .fused()->.optimized() flip is the whole guard); the .fused() point estimate stays untouched;
  * odin_residualize strips a long/sweet (length+warmth) nuisance off a score.
NO network, NO ClickHouse, NO numpy — pure synthetic inputs.
"""
from __future__ import annotations

import math

from voice_ops.flywheel.ensemble import (
    HEAD_KEYS, ensemble_stats, fuse_pessimistic, head_contributions, lcb_reward,
    odin_residualize,
)
from voice_ops.flywheel.schema import RewardComponents

# A z-baseline that leaves each head on its raw scale (mean 0, std 1) so the disagreement is legible.
_UNIT_Z = {"_z": {k: (0.0, 1.0) for k in HEAD_KEYS}}


def _heads(o, a, j, v):
    """Four explicitly-present heads with unit z-baselines (so z == raw value)."""
    h = {
        "h_outcome": o, "h_affect": a, "h_judge": j, "h_value": v,
        "_present": {k: True for k in HEAD_KEYS},
    }
    h.update(_UNIT_Z)
    return h


def test_lcb_is_pessimistic_never_above_the_mean():
    """The whole point of B1: the optimizer consumes a LOWER bound. With λ,κ >= 0 the penalty
    terms -λ·var - κ·u are non-positive, so lcb_reward can never exceed the ensemble mean."""
    for heads in (_heads(0.8, 0.6, 0.7, 0.5), _heads(0.2, -0.3, 0.1, 0.0),
                  _heads(1.0, 1.0, 1.0, 1.0)):
        mu, var, u = ensemble_stats(heads)
        lcb = lcb_reward(heads, lam=0.5, kappa=1.0)
        assert lcb <= mu + 1e-9, (lcb, mu)
        assert var >= 0.0 and u >= 0.0, (var, u)


def test_higher_head_disagreement_lowers_the_lcb():
    """UWO penalises head DISAGREEMENT. Two head-sets with the SAME mean but more spread must
    yield a STRICTLY lower lcb — the more the heads fight, the less the optimizer is allowed to
    claim. Both sets average 0.5; the spread set has a far larger variance."""
    agree = _heads(0.5, 0.5, 0.5, 0.5)      # zero disagreement
    spread = _heads(0.0, 1.0, 0.0, 1.0)     # same mean (0.5), large disagreement
    mu_a, var_a, _ = ensemble_stats(agree)
    mu_s, var_s, _ = ensemble_stats(spread)
    assert abs(mu_a - mu_s) < 1e-9, (mu_a, mu_s)   # means matched
    assert var_s > var_a, (var_s, var_a)            # spread genuinely disagrees more
    lcb_a = lcb_reward(agree, lam=0.5, kappa=1.0)
    lcb_s = lcb_reward(spread, lam=0.5, kappa=1.0)
    assert lcb_s < lcb_a, (lcb_s, lcb_a)


def test_missing_head_is_excluded_not_treated_as_zero():
    """A dormant value head (not supplied, ~0) must be DROPPED, not counted as a real 0. If it were
    folded in as 0 it would (a) drag the mean of three positive heads down toward 0 and (b) inflate
    the disagreement. We compare the genuine 3-head mean to the would-be 4-with-a-fake-0 mean."""
    turn = {
        "terminal_credit": 0.9, "affect_delta": 0.9, "judge_score": 0.9,
        "judge_model_id": "anthropic/claude-3.5-sonnet",  # makes h_judge present
        # NO value_head key at all -> dormant critic head
        "confidence": 0.8,
    }
    heads = head_contributions(turn)
    heads.update(_UNIT_Z)
    assert heads["_present"]["h_value"] is False, "dormant value head must be flagged MISSING"
    mu, _var, _u = ensemble_stats(heads)
    # the honest 3-head mean is ~0.9; a fake-0 4-head mean would be ~0.675 — far lower.
    assert abs(mu - 0.9) < 1e-6, mu
    fake_four = (0.9 + 0.9 + 0.9 + 0.0) / 4.0
    assert mu > fake_four + 0.1, (mu, fake_four)


def test_fuse_pessimistic_sets_computed_and_optimized_returns_lcb():
    """fuse_pessimistic flips the rc: ensemble_computed True, the ensemble fields filled, and
    rc.optimized() now returns the LCB (rounded) instead of .fused(). The .fused() point estimate
    is left untouched (it is the console's honest-science provenance number)."""
    rc = RewardComponents(
        terminal_credit=0.8, affect_delta=0.3, judge_score=0.6,
        judge_model_id="anthropic/claude-3.5-sonnet", confidence=0.7,
        w_outcome=1.0, w_affect=0.15, w_judge=0.10,
    )
    before_fused = rc.fused()
    assert rc.ensemble_computed is False
    assert rc.optimized() == before_fused, "optimized() falls back to fused() before B1 runs"

    rc2 = fuse_pessimistic(rc, value_head=0.2)
    assert rc2 is rc, "fuse_pessimistic enriches IN PLACE and returns the same object"
    assert rc2.ensemble_computed is True
    assert rc2.value_head == 0.2
    # optimized() now returns the LCB (the .fused()->.optimized() flip — the whole anti-Goodhart guard)
    assert rc2.optimized() == round(rc2.lcb_reward, 5), (rc2.optimized(), rc2.lcb_reward)
    # the LCB is pessimistic vs the ensemble mean.
    assert rc2.lcb_reward <= rc2.ensemble_mean + 1e-9, (rc2.lcb_reward, rc2.ensemble_mean)
    # the point estimate the console shows is unchanged.
    assert abs(rc2.fused() - before_fused) < 1e-9, (rc2.fused(), before_fused)


def test_fuse_pessimistic_never_raises_and_stays_dormant_safe_on_junk():
    """A malformed rc-like object must leave ensemble_computed False (so optimized() keeps falling
    back to fused()) and NEVER raise into the call path."""
    rc = RewardComponents(terminal_credit=float("nan"), affect_delta=None, judge_score="x")  # type: ignore[arg-type]
    out = fuse_pessimistic(rc, value_head=float("inf"))
    assert isinstance(out, RewardComponents)
    # whatever happened, optimized() must still return a finite float and never raise.
    assert isinstance(out.optimized(), float)


def test_odin_residualize_strips_a_long_and_sweet_score():
    """ODIN disentanglement: with non-zero nuisance betas, a long (many-token) AND sweet (warm)
    turn has its reward DOCKED — the optimizer can't win by being longer or sweeter. With zero
    betas (the dormant default — no nuisance fit yet) it is the identity."""
    base = 0.8
    # identity when no nuisance has been fit.
    assert odin_residualize(base, length=200, warmth=0.9) == round(base, 6)
    # a long + warm turn is residualised DOWN once the betas are non-zero.
    stripped = odin_residualize(base, length=200, warmth=0.9, beta_len=0.02, beta_warm=0.2)
    assert stripped < base, (stripped, base)
    # a short, cool turn loses (almost) nothing relative to the long, warm one.
    short_cool = odin_residualize(base, length=5, warmth=0.0, beta_len=0.02, beta_warm=0.2)
    assert short_cool > stripped, (short_cool, stripped)
    # never raises on junk -> returns the raw score.
    assert isinstance(odin_residualize(float("nan"), length=None, warmth="x"), float)  # type: ignore[arg-type]


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for fn in fns:
        fn()
        passed += 1
        print(f"  ok  {fn.__name__}")
    print(f"\n{passed}/{len(fns)} tests passed — test_ensemble OK")


if __name__ == "__main__":
    _run_all()
