"""Tests for voice_ops.flywheel.causal — B4 doubly-robust X-learner CATE.

Runnable with pytest OR directly:
    python3 -m voice_ops.flywheel.tests.test_causal
Validates the PROPERTIES that make the causal estimate honest (AIPW/DR with LOGGED propensity;
X-learner cross-imputation; cross-fit-by-call cluster honesty), not magic numbers:
  * dr_xlearner on a SYNTHETIC dataset with a KNOWN constant treatment effect (and KNOWN logged
    propensity) recovers the SIGN and roughly the magnitude of that effect;
  * kfold_by_group NEVER splits a call across folds (a group is assigned WHOLE to one fold) -- the
    cluster-honesty primitive that stops within-call rows fabricating sample size;
  * build_move_cate is DORMANT-SAFE: with no ClickHouse it returns [] and never raises.
NO network, NO ClickHouse, NO numpy -- pure synthetic inputs.
"""
from __future__ import annotations

import asyncio
import random

from voice_ops.flywheel.causal import build_move_cate, dr_xlearner, kfold_by_group, r_learner_sign


def test_kfold_by_group_never_splits_a_call_across_folds():
    """Cluster honesty: every row sharing a group (call_id) MUST land in the same fold, else cross-
    fitting leaks correlated within-call turns and shrinks the CI fraudulently. Deterministic."""
    groups = ["c0", "c0", "c0", "c1", "c1", "c2", "c3", "c4", "c5", "c5"]
    folds = kfold_by_group(groups, 3)
    assert len(folds) == len(groups)
    g2f: dict = {}
    for g, f in zip(groups, folds):
        assert g2f.setdefault(g, f) == f, ("a call straddled folds", g, f, g2f[g])
    assert len(set(folds)) <= 3
    # determinism: the same input yields the same fold assignment.
    assert kfold_by_group(groups, 3) == folds
    assert kfold_by_group([]) == []


def test_dr_xlearner_recovers_a_known_positive_effect():
    """Construct a logged-bandit dataset where the treatment adds a KNOWN +0.30 to the booking
    probability, with the propensity LOGGED & known. The DR X-learner must recover a POSITIVE CATE
    of roughly the right magnitude (honest, not exact) and an independent R-learner must agree on
    the sign. Folds split by call_id so no call straddles a fold."""
    rng = random.Random(7)
    X, T, Y, P, G = [], [], [], [], []
    true_effect = 0.30
    for c in range(220):
        cid = f"call_{c}"
        friction = rng.uniform(-1, 1)
        arousal = rng.uniform(-1, 1)
        prop = max(0.1, min(0.9, 0.5 + 0.2 * friction))      # logged P(T=1), state-dependent
        for _ in range(rng.randint(2, 5)):
            t = 1 if rng.random() < prop else 0
            base = max(0.01, min(0.99, 0.30 + 0.15 * arousal))
            book_p = max(0.01, min(0.99, base + (true_effect if t else 0.0)))
            y = 1 if rng.random() < book_p else 0
            X.append([friction, arousal, 1.0 if friction > 0 else 0.0])
            T.append(t)
            Y.append(y)
            P.append(prop)                                    # p = P(T=1) per the AIPW convention
            G.append(cid)
    cate, se = dr_xlearner(X, T, Y, P, k_folds=5, groups=G)
    assert isinstance(cate, float) and isinstance(se, float)
    assert se >= 0.0
    assert cate > 0.05, f"expected a positive CATE near +0.30, got {cate}"
    assert cate < 0.6, f"recovered CATE implausibly large, got {cate}"   # roughly the right scale
    assert r_learner_sign(X, T, Y, P) in (0, 1), "R-learner must agree the sign is non-negative"


def test_dr_xlearner_degenerate_inputs_return_clean_zeros():
    """No contrast (all treated / all control), length mismatch, or empty input -> (0.0, 0.0): an
    honest 'no causal estimate', never a raise."""
    assert dr_xlearner([[0.0]], [1], [1], [0.5]) == (0.0, 0.0)     # no control row
    assert dr_xlearner([[0.0]], [0], [1], [0.5]) == (0.0, 0.0)     # no treated row
    assert dr_xlearner([], [], [], []) == (0.0, 0.0)
    assert dr_xlearner([[0.0], [0.0]], [1], [1, 0], [0.5, 0.5]) == (0.0, 0.0)  # length mismatch
    assert r_learner_sign([], [], [], []) == 0


def test_build_move_cate_dormant_returns_empty_and_never_raises():
    """With no ClickHouse configured (the resting state) the async entrypoint must return [] and
    never raise -- the side-pipeline stays dormant-safe (mirrors build_move_prm's contract)."""
    out = asyncio.new_event_loop().run_until_complete(build_move_cate("t_demo"))
    assert out == [], out
    # an empty tenant id is also a clean [] (best-effort), never raises.
    out2 = asyncio.new_event_loop().run_until_complete(build_move_cate(""))
    assert out2 == []


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for fn in fns:
        fn()
        passed += 1
        print(f"  ok  {fn.__name__}")
    print(f"\n{passed}/{len(fns)} tests passed — test_causal OK")


if __name__ == "__main__":
    _run_all()
