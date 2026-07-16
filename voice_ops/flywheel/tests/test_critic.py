"""Tests for voice_ops.flywheel.critic — B3 learned, calibrated V(state)->P(book) critic.

Runnable with pytest OR directly:
    python3 -m voice_ops.flywheel.tests.test_critic
Validates the PROPERTIES of the value head (Math-Shepherd partial-sequence labeling; Platt
calibration; BSRS-bounded shaping), not magic numbers:
  * featurize is FIXED-LENGTH (== N_FEATURES) and DETERMINISTIC (same turn -> same vector);
  * ece == ~0 on a PERFECTLY-CALIBRATED synthetic set, auc == ~1 on a PERFECTLY-RANKED set;
  * predict always returns a probability in [0,1] (and 0.5, the agnostic prior, with no model);
  * pbrs_potential is BOUNDED by +-eta/2 (anti-Goodhart -- a confident critic can't override outcome);
  * train_critic is DORMANT-SAFE: with the activation env cleared it returns an INACTIVE model and
    never raises (we monkeypatch the env to force the resting state).
NO network, NO ClickHouse, NO numpy -- pure synthetic inputs.
"""
from __future__ import annotations

import asyncio
import os

from voice_ops.flywheel.critic import (
    N_FEATURES, auc, ece, featurize, pbrs_potential, predict, train_critic,
)

# Env vars that could accidentally activate the package -- cleared so train_critic asserts dormancy
# regardless of the developer's shell (mirrors test_dormant._ACTIVATION_ENV).
_ACTIVATION_ENV = (
    "FLYWHEEL_ENABLED", "FLYWHEEL_CLICKHOUSE_URL", "CLICKHOUSE_URL", "CLICKHOUSE_WRITE_URL",
    "FLYWHEEL_CLICKHOUSE_READ_URL", "CLICKHOUSE_READ_URL",
)


def _force_dormant():
    for k in _ACTIVATION_ENV:
        os.environ.pop(k, None)


def test_featurize_is_fixed_length_and_deterministic():
    """The feature vector is the train/serve contract: it MUST be exactly N_FEATURES long for ANY
    turn (a missing key -> a sane default, never a short/long vector) and DETERMINISTIC (the same
    turn always maps to the same vector -- no hidden randomness leaks into the critic)."""
    turn = {"state_friction": 70, "state_arousal": 40, "turn_num": 3, "call_len": 10,
            "state_regime": "rising", "move_type": "objection_rebuttal",
            "objection_type": "price", "lead_temperature": "warm"}
    f1 = featurize(turn)
    f2 = featurize(dict(turn))
    assert len(f1) == N_FEATURES, (len(f1), N_FEATURES)
    assert f1 == f2, "featurize must be deterministic for the same turn"
    # an empty / garbage turn still yields a full-length vector, never raises.
    assert len(featurize({})) == N_FEATURES
    assert len(featurize(None)) == N_FEATURES                 # type: ignore[arg-type]
    # the prior turn changes the vector (prior_present flag flips) but keeps the length fixed.
    f_prior = featurize(turn, prior={"state_friction": 90})
    assert len(f_prior) == N_FEATURES


def test_ece_is_zero_on_a_perfectly_calibrated_set():
    """ECE is |accuracy - confidence| per bin. On a synthetic set where, within each probability
    bin, the empirical positive rate EQUALS the predicted probability, ECE must be ~0 (perfectly
    calibrated). We build 10 bins, each with the right fraction of positives at a fixed prob."""
    probs, labels = [], []
    # bin centred at p: put 100 examples at prob p with exactly p*100 positives.
    for k in range(1, 10):
        p = k / 10.0
        npos = int(round(p * 100))
        probs += [p] * 100
        labels += [1.0] * npos + [0.0] * (100 - npos)
    e = ece(probs, labels, bins=10)
    assert e <= 0.02, e                                       # ~perfectly calibrated
    # empty input -> worst-case 1.0 (an honest "no calibration evidence").
    assert ece([], []) == 1.0


def test_auc_is_one_on_a_perfectly_ranked_set():
    """AUC via the rank-sum identity. When every positive scores strictly above every negative the
    ranking is perfect -> AUC == 1.0. When all examples share one class AUC degenerates to 0.5."""
    probs = [0.10, 0.20, 0.30, 0.40, 0.80, 0.85, 0.90, 0.95]
    labels = [0, 0, 0, 0, 1, 1, 1, 1]                        # every positive ranks above every neg
    assert abs(auc(probs, labels) - 1.0) < 1e-9, auc(probs, labels)
    # a perfectly INVERTED ranking is AUC 0.0 (the complement).
    assert abs(auc(probs, [1, 1, 1, 1, 0, 0, 0, 0]) - 0.0) < 1e-9
    # single class -> no discrimination possible -> 0.5.
    assert auc([0.3, 0.7], [1, 1]) == 0.5


def test_predict_is_a_probability_and_agnostic_without_a_model():
    """predict always returns a calibrated P(book) in [0,1]; with no model it returns the agnostic
    0.5 prior (never raises, never extrapolates a wild value)."""
    coef = {"w": [0.0] * N_FEATURES, "b": 0.0, "platt_a": 1.0, "platt_b": 0.0}
    p = predict(featurize({"state_friction": 20}), coef)
    assert 0.0 <= p <= 1.0, p
    # no model -> 0.5 agnostic prior.
    assert predict([], None) == 0.5
    assert predict(featurize({}), None) == 0.5


def test_pbrs_potential_is_bounded_by_eta_half():
    """BSRS-bounded shaping Phi = eta*(V - 0.5): centred (V=0.5 -> 0) and capped at +-eta/2 even for
    V at the extremes. This bound is the anti-Goodhart guard -- a confident value head can never
    swamp the outcome reward."""
    eta = 0.3
    assert abs(pbrs_potential(0.5, eta=eta)) < 1e-9          # neutral state -> zero potential
    hi = pbrs_potential(1.0, eta=eta)
    lo = pbrs_potential(0.0, eta=eta)
    assert abs(hi - eta / 2.0) < 1e-9 and abs(lo + eta / 2.0) < 1e-9, (hi, lo)
    # bounded for every V in [0,1].
    for v in (0.0, 0.1, 0.25, 0.5, 0.75, 0.9, 1.0):
        assert -eta / 2.0 - 1e-9 <= pbrs_potential(v, eta=eta) <= eta / 2.0 + 1e-9
    # junk input -> 0.0, never raises.
    assert pbrs_potential(float("nan")) == 0.0


def test_train_critic_dormant_returns_inactive_and_never_raises():
    """With the activation env cleared (the resting state) train_critic must short-circuit to an
    INACTIVE CriticModel -- no warehouse to read -- and NEVER raise into the worker."""
    _force_dormant()
    model = asyncio.new_event_loop().run_until_complete(train_critic("t_demo"))
    assert model is not None
    assert model.active is False, "dormant train_critic must return an inactive model"
    assert model.n_rows == 0, model.n_rows
    # an empty tenant id is also a clean inactive (never raises).
    m2 = asyncio.new_event_loop().run_until_complete(train_critic(""))
    assert m2.active is False


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for fn in fns:
        fn()
        passed += 1
        print(f"  ok  {fn.__name__}")
    print(f"\n{passed}/{len(fns)} tests passed — test_critic OK")


if __name__ == "__main__":
    _run_all()
