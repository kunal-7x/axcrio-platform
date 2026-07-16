"""Tests for voice_ops.flywheel.sequential — B2 ALWAYS-VALID (anytime) promotion test.

Runnable with pytest OR directly:
    python3 -m voice_ops.flywheel.tests.test_sequential
Validates the PROPERTIES that keep a peeked-at A/B promotion honest (Waudby-Smith & Ramdas betting
CS / AsympCS / LUCB), not magic numbers:
  * both confidence sequences bracket the running mean (lower <= mean <= upper) and the interval
    SHRINKS as n grows (more data -> tighter, the anytime guarantee still holding);
  * lucb_separated is True ONLY when the challenger's lower bound clears the champion's upper (no
    overlap) -- a hair of overlap blocks promotion;
  * evaluate_promotion needs BOTH seq_significant AND practical_sig -- neither alone fires a swap;
  * update_sequential NEVER mutates its input row and its online Welford (n, mean, var) matches the
    batch mean/variance exactly.
NO network, NO ClickHouse, NO numpy -- pure synthetic streams.
"""
from __future__ import annotations

import random

from voice_ops.flywheel import schema as S
from voice_ops.flywheel.sequential import (
    asymp_cs, betting_cs, evaluate_promotion, lucb_separated, practical_significant,
    update_sequential,
)


def _stream(mean, sd, n, seed):
    rng = random.Random(seed)
    return [max(-1.0, min(2.0, mean + rng.gauss(0.0, sd))) for _ in range(n)]


def test_betting_cs_brackets_mean_and_shrinks_with_n():
    """The betting CS (WSR) must contain the sample mean and TIGHTEN as more data arrives: a
    400-sample interval is narrower than a 40-sample interval on the same process. The surviving
    set lives on a discrete grid (41 nodes across [lo,hi] => step ~0.075), so we bracket the mean
    up to one grid step -- the honest resolution of this estimator, not a continuous interval."""
    lo_b, hi_b, lo_s, hi_s = -1.0, 2.0, -1.0, 2.0
    grid = 41
    grid_step = (hi_b - lo_b) / (grid - 1)
    small = _stream(0.4, 0.2, 40, seed=1)
    big = _stream(0.4, 0.2, 400, seed=1)
    lo_s, hi_s = betting_cs(small, alpha=0.05, lo=-1.0, hi=2.0, grid=grid)
    lo_b, hi_b = betting_cs(big, alpha=0.05, lo=-1.0, hi=2.0, grid=grid)
    assert lo_s <= hi_s and lo_b <= hi_b
    mean_s = sum(small) / len(small)
    mean_b = sum(big) / len(big)
    # the mean lies inside the surviving grid interval, up to one grid step of discretisation slack.
    assert lo_s - grid_step <= mean_s <= hi_s + grid_step, (lo_s, mean_s, hi_s)
    assert lo_b - grid_step <= mean_b <= hi_b + grid_step, (lo_b, mean_b, hi_b)
    assert (hi_b - lo_b) < (hi_s - lo_s), ("CS must shrink with n", hi_b - lo_b, hi_s - lo_s)
    # empty input -> the widest, most honest "no signal" interval.
    assert betting_cs([], lo=-1.0, hi=2.0) == (-1.0, 2.0)


def test_asymp_cs_brackets_mean_and_shrinks_with_n():
    """The closed-form AsympCS half-width must contain the mean and shrink with n on the same
    (mean, var)."""
    lo10, hi10 = asymp_cs(10, 0.4, 0.04)
    lo1k, hi1k = asymp_cs(1000, 0.4, 0.04)
    assert lo10 <= 0.4 <= hi10, (lo10, hi10)
    assert lo1k <= 0.4 <= hi1k, (lo1k, hi1k)
    assert (hi1k - lo1k) < (hi10 - lo10), "AsympCS must tighten with more data"
    # n<=0 cannot form a half-width -> a point interval at the mean (never spuriously separates).
    assert asymp_cs(0, 0.0, 0.0) == (0.0, 0.0)


def test_lucb_separated_only_on_separation():
    """LUCB dominance: True iff the challenger LOWER clears the champion UPPER (no overlap). The
    pessimistic, anti-Goodhart condition -- a challenger whose worst plausible value already beats
    the champion's best plausible value."""
    assert lucb_separated(0.30, 0.20) is True       # clears
    assert lucb_separated(0.21, 0.20) is True        # just clears
    assert lucb_separated(0.20, 0.20) is False       # touching == overlap, no go
    assert lucb_separated(0.10, 0.20) is False       # overlaps
    # junk inputs degrade to False (never a spurious GO), no raise.
    assert lucb_separated(float("nan"), float("nan")) is False


def test_evaluate_promotion_requires_both_significance_legs():
    """A champion swap costs operator trust, so promotion = seq_significant AND practical_sig.
    We construct three challengers: (a) separated + big lift (promotes), (b) separated but a
    sub-delta lift (statistical-only -> no promote), (c) a big lift but overlapping CS (no
    separation -> no promote)."""
    champ = S.SequentialState(challenger_id="champ", n=300, running_mean=0.20,
                              cs_lower=0.15, cs_upper=0.25)

    # (a) clear win: lower 0.30 clears upper 0.25, lift 0.20 >> delta.
    win = S.SequentialState(challenger_id="win", n=300, running_mean=0.40,
                            cs_lower=0.30, cs_upper=0.50)
    v_win = evaluate_promotion(win, champ, practical_delta=0.01)
    assert v_win["seq_significant"] is True and v_win["practical_sig"] is True
    assert v_win["promote"] is True and abs(v_win["lift"] - 0.20) < 1e-6

    # (b) statistically separated but the lift is below the practical floor -> NO promote.
    tiny = S.SequentialState(challenger_id="tiny", n=300, running_mean=0.205,
                             cs_lower=0.252, cs_upper=0.258)
    v_tiny = evaluate_promotion(tiny, champ, practical_delta=0.05)
    assert v_tiny["seq_significant"] is True, v_tiny
    assert v_tiny["practical_sig"] is False, v_tiny
    assert v_tiny["promote"] is False

    # (c) a big point lift but the CS still overlaps the champion -> NO separation -> NO promote.
    noisy = S.SequentialState(challenger_id="noisy", n=300, running_mean=0.40,
                              cs_lower=0.10, cs_upper=0.70)
    v_noisy = evaluate_promotion(noisy, champ, practical_delta=0.01)
    assert v_noisy["seq_significant"] is False, v_noisy
    assert v_noisy["promote"] is False

    # malformed states -> a safe all-False verdict, never raises.
    assert evaluate_promotion(None, None)["promote"] is False
    assert practical_significant(0.05, 0.01) is True
    assert practical_significant(0.005, 0.01) is False


def test_update_sequential_never_mutates_input_and_welford_matches_batch():
    """The online Welford update must (1) return a NEW state and never mutate the persisted input,
    and (2) reproduce the exact batch mean/variance of the folded stream so a resumed worker has
    the same sufficient statistics as a one-shot batch compute."""
    xs = _stream(0.4, 0.2, 200, seed=7)

    st = S.SequentialState(tenant_id="t1", challenger_id="ch", metric="reward")
    for v in xs:
        before_n, before_mean = st.n, st.running_mean
        nxt = update_sequential(st, v, alpha=0.05)
        # the input row was NOT mutated in place.
        assert st.n == before_n and st.running_mean == before_mean, "input must not be mutated"
        assert nxt is not st, "update must return a NEW state"
        st = nxt

    assert st.n == len(xs)
    batch_mean = sum(xs) / len(xs)
    batch_var = sum((x - batch_mean) ** 2 for x in xs) / len(xs)   # population variance
    # the persisted stats are round(..., 6) each step, so we match the batch values to that
    # documented 6-decimal resolution (cumulative rounding over 200 folds, not estimator error).
    assert abs(st.running_mean - batch_mean) < 1e-5, (st.running_mean, batch_mean)
    assert abs(st.running_var - batch_var) < 1e-5, (st.running_var, batch_var)

    # a non-numeric observation is swallowed: n unchanged, no raise.
    st_noop = update_sequential(st, float("nan"))
    assert st_noop.n == st.n
    # a None prior state seeds a fresh n=1 state without raising.
    fresh = update_sequential(None, 0.5)
    assert fresh.n == 1 and abs(fresh.running_mean - 0.5) < 1e-9


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for fn in fns:
        fn()
        passed += 1
        print(f"  ok  {fn.__name__}")
    print(f"\n{passed}/{len(fns)} tests passed — test_sequential OK")


if __name__ == "__main__":
    _run_all()
