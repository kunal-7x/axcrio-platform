"""Tests for voice_ops.flywheel.conformal — B2 distribution-free Mondrian split-conformal.

Runnable with pytest OR directly:
    python3 -m voice_ops.flywheel.tests.test_conformal
Validates the PROPERTIES that make the calibrated lower bound honest (Vovk split conformal; Mondrian
group-conditional), not magic numbers:
  * conformal_quantile uses the FINITE-SAMPLE (n+1) correction -- when (n+1)(1-alpha) > n there is
    no certifiable quantile so it returns +inf (the honest "trust nothing" sentinel), and it is
    MONOTONE NON-DECREASING in alpha (looser miscoverage -> a smaller / equal q_hat);
  * calibrate_mondrian gives a fat bucket its OWN q_hat but falls a THIN bucket back to the marginal
    parent (small cohorts under-cover otherwise);
  * pessimistic_lower(pred, q_hat) = pred - q_hat <= pred (we only ever read the worst plausible
    value; an uncalibrated +inf q_hat collapses the bound to -inf = worthless).
NO network, NO ClickHouse, NO numpy -- pure synthetic scores.
"""
from __future__ import annotations

import math
import random

from voice_ops.flywheel.conformal import (
    INF, calibrate_mondrian, conformal_quantile, nonconformity, pessimistic_lower,
)


def test_conformal_quantile_uses_the_n_plus_one_correction():
    """The (n+1) finite-sample correction means a sample too small to certify 1-alpha coverage
    returns +inf, NOT the max score. n=8, alpha=0.1 needs the ceil(9*0.9)=9th of 8 -> impossible
    -> +inf. With enough samples the quantile is a real, finite value in range."""
    # too small to certify 90% coverage -> honest +inf sentinel.
    assert conformal_quantile([0.1] * 8, alpha=0.1) == INF
    assert conformal_quantile([], alpha=0.1) == INF      # no data
    # a known small set where the corrected rank is computable:
    # n=9, alpha=0.1 -> rank = ceil(10*0.9) = 9 -> the 9th (largest) order statistic.
    scores9 = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]
    assert abs(conformal_quantile(scores9, alpha=0.1) - 0.9) < 1e-9
    # n=9, alpha=0.2 -> rank = ceil(10*0.8) = 8 -> the 8th order statistic (0.8) <= the 9th.
    assert abs(conformal_quantile(scores9, alpha=0.2) - 0.8) < 1e-9
    # a big calibration set yields a finite, in-range q_hat.
    rng = random.Random(7)
    big = [round(rng.random(), 4) for _ in range(500)]
    q = conformal_quantile(big, alpha=0.1)
    assert math.isfinite(q) and 0.0 <= q <= 1.0, q


def test_conformal_quantile_is_monotone_in_alpha():
    """A LOOSER miscoverage (larger alpha) demands a SMALLER order statistic, so q_hat is monotone
    NON-INCREASING as alpha rises (equivalently non-decreasing as alpha falls). We sweep alpha up
    and assert q_hat never increases."""
    rng = random.Random(11)
    scores = [round(rng.random(), 4) for _ in range(300)]
    alphas = [0.01, 0.05, 0.1, 0.2, 0.3, 0.5]
    qs = [conformal_quantile(scores, alpha=a) for a in alphas]
    # all finite at n=300 for these alphas.
    assert all(math.isfinite(q) for q in qs), qs
    for earlier, later in zip(qs, qs[1:]):
        assert later <= earlier + 1e-12, ("q_hat must not rise as alpha rises", earlier, later)


def test_calibrate_mondrian_falls_back_to_marginal_for_a_thin_bucket():
    """A fat bucket (>= min_calib) gets its OWN (tighter) Mondrian q_hat; a thin bucket inherits
    the marginal parent -- the Mondrian fallback that stops small cohorts from silently under-
    covering. The '_marginal' pseudo-bucket is always present and finite."""
    rng = random.Random(7)
    rows = []
    for _ in range(300):                                  # fat bucket 'hot': small residuals (<=0.4)
        rows.append({"bucket": "hot", "score": round(rng.random() * 0.4, 4)})
    for _ in range(5):                                     # thin bucket 'cold' (< min_calib=50)
        rows.append({"bucket": "cold", "score": round(rng.random(), 4)})
    qmap = calibrate_mondrian(rows, alpha=0.1, min_calib=50)
    assert "_marginal" in qmap and math.isfinite(qmap["_marginal"])
    # the fat bucket earned its own, tighter q_hat (its residuals never exceed 0.4).
    assert math.isfinite(qmap["hot"]) and qmap["hot"] <= 0.4 + 1e-9, qmap["hot"]
    # the thin bucket inherits the marginal exactly (the fallback).
    assert qmap["cold"] == qmap["_marginal"], (qmap["cold"], qmap["_marginal"])
    # malformed input -> a safe "trust nothing" map, never raises.
    assert calibrate_mondrian([], alpha=0.1) == {"_marginal": INF}
    assert calibrate_mondrian(None, alpha=0.1) == {"_marginal": INF}  # type: ignore[arg-type]


def test_pessimistic_lower_never_exceeds_pred():
    """B2 only lets the rest of the flywheel read the LOWER bound pred - q_hat. For any finite,
    non-negative q_hat this is <= pred (we can only DISCOUNT). An uncalibrated +inf q_hat collapses
    the bound to -inf (worthless) -- the anti-Goodhart default."""
    assert abs(nonconformity(0.8, 0.5) - 0.3) < 1e-9      # |pred - label| (float-safe)
    assert nonconformity("junk", 1.0) == INF              # non-numeric -> maximally non-conforming
    for pred, q in ((0.7, 0.0), (0.7, 0.2), (0.7, 0.7), (0.7, 1.5)):
        lb = pessimistic_lower(pred, q)
        assert lb <= pred + 1e-12, (pred, q, lb)
        assert abs(lb - (pred - q)) < 1e-12, (lb, pred - q)
    # uncalibrated predictor (+inf q_hat) -> -inf lower bound (trust nothing).
    assert pessimistic_lower(0.7, INF) == -INF
    # bad input -> -inf (worthless), never raises.
    assert pessimistic_lower("x", 0.1) == -INF            # type: ignore[arg-type]


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for fn in fns:
        fn()
        passed += 1
        print(f"  ok  {fn.__name__}")
    print(f"\n{passed}/{len(fns)} tests passed — test_conformal OK")


if __name__ == "__main__":
    _run_all()
