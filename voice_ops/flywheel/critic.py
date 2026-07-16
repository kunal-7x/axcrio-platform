"""voice_ops.flywheel.critic — B3: a learned, CALIBRATED V(state)→P(book) critic.

THE PROBLEM. credit.py shapes process reward with a HAND-PICKED potential Φ(s) = -friction/100
(Ng-Harada-Russell PBRS). That potential is a guess: it assumes "less caller friction == closer to
a booking" with a fixed linear map. But the real value of a state — the probability this call still
ends in a booked site-visit GIVEN where we are right now — depends on far more than friction (the
regime, the move just played, the objection on the table, the lead's temperature, how deep into the
call we are). B3 LEARNS that value function from the warehouse instead of hand-setting it.

THE SCIENCE (process-reward / value-function literature).
  * PARTIAL-SEQUENCE LABELING. We never have a per-turn ground-truth "was this turn good". The only
    label is terminal (did the call book). Following Math-Shepherd (Wang et al. 2024) Monte-Carlo
    process labeling, OmegaPRM (Luo et al. 2024) soft targets, and the partial-sequence value
    objective of arXiv:2406.07780, we PROPAGATE the call's terminal booked label back onto EVERY
    turn of that call. A turn from a call that eventually booked is a positive value example; a turn
    from a call that didn't is negative. We NEVER read an in-call ORM/booking mid-trajectory (there
    is none) — the label is the *final* outcome, attached to every prefix state.
  * SOFT TARGETS. A pure binary back-propagated label is noisy (a great state in a call that happened
    to fall apart at the very end is mislabeled 0). So we BLEND the binary terminal label with the
    matched-state cohort book-rate (OmegaPRM-style soft target): y_soft = κ·binary + (1-κ)·cohort.
    The cohort rate is the empirical P(book) over turns sharing the same coarse state bucket.
  * CALIBRATION (Platt 1999). A value head is only useful for shaping if its probabilities are
    HONEST. We fit a logistic V(state) by deterministic batch gradient descent, then Platt-scale its
    logit (a·logit+b) on a HELD split, and we gate on Expected Calibration Error (ECE) and AUC. A
    critic with ECE>0.1 or AUC<0.55 ships INACTIVE and the live shaper keeps the hand-set fallback.
  * BOUNDED SHAPING (BSRS). The trained potential Φ = η·(V-0.5) is bounded — anti-Goodhart, so a
    confident value head can never dominate the outcome reward. pbrs_potential() returns that Φ for
    reward.affect_delta_shaping to optionally substitute for -friction/100.

DESIGN LAWS honoured here.
  * PURE-PYTHON CORE, numpy LAZY/OPTIONAL. featurize / predict / the GD trainer / ece / auc all run
    on plain lists; numpy is imported ONLY inside the trainer to vectorize, behind a try, with the
    pure-python loop as the fallback. The module imports and serves dormant with no heavy deps.
  * DORMANT-SAFE / BEST-EFFORT. Every public fn swallows its errors → logging.warning and returns a
    clean empty/zero/inactive value. train_critic on dormancy or insufficient data returns an
    INACTIVE CriticModel; it NEVER raises.
  * SIDE-PIPELINE. train_critic is offline/worker-only — it reads the warehouse with FINAL and never
    touches the live LiveKit turn loop. predict/featurize/pbrs_potential are cheap enough to be used
    by the offline shaper but make zero network calls.
  * HONEST SCIENCE. active = (ece<=0.1 and auc>=0.55 and n>=critic_min_rows); we carry n_rows, auc,
    ece into the persisted CriticModel so the console can show WHY a critic is (in)active. No fake
    numbers: too little data → inactive, never a fabricated coefficient.
"""
from __future__ import annotations

import json
import logging
import math
import random
from typing import List, Optional

from . import config as _cfg
from . import schema as S
from . import store as _st

logger = logging.getLogger("flywheel.critic")


# --------------------------------------------------------------------------- #
# FEATURE LAYOUT — fixed-length numeric vector. Documented here so predict() and
# train_critic() agree on the spec and a persisted coef_json is interpretable.
# Every block is a small FIXED one-hot (unknown/overflow → the last "other" slot)
# so the dimension never depends on the data. The intercept (bias) is NOT in this
# list; the trainer carries it as a separate `b`.
# --------------------------------------------------------------------------- #
_REGIMES = ("steady", "rising", "resolving", "critical")          # state_regime buckets
_MOVES = ("probe", "price_reveal", "objection_rebuttal", "cta_push",
          "rapport", "qualify", "schedule")                       # common move_types
_OBJECTIONS = ("none", "price", "location", "trust", "timing", "spouse", "not_interested")
_TEMPS = ("cold", "warm", "hot")                                  # lead_temperature

# Layout (index : meaning):
#   0  state_friction / 100                  (continuous, 0..1)
#   1  state_arousal  / 100                  (continuous, 0..1)
#   2  turn_num                              (raw count, small)
#   3  turn_num / max(call_len, 1)           (call-progress fraction, 0..1)
#   4  prior state_friction / 100            (continuous; 0.5 when no prior)
#   5  prior-move present flag               (1 if a prior turn exists, else 0)
#   regime  one-hot   : len(_REGIMES)   + 1 other
#   move    one-hot   : len(_MOVES)     + 1 other
#   object. one-hot   : len(_OBJECTIONS)+ 1 other
#   temp    one-hot   : len(_TEMPS)     + 1 other
_CONT_DIM = 6
_BLOCKS = (
    ("state_regime", _REGIMES),
    ("move_type", _MOVES),
    ("objection_type", _OBJECTIONS),
    ("lead_temperature", _TEMPS),
)
N_FEATURES = _CONT_DIM + sum(len(vals) + 1 for _, vals in _BLOCKS)

#: human-readable feature spec persisted alongside the weights for interpretability.
FEATURES = {
    "version": "v1",
    "n_features": N_FEATURES,
    "continuous": [
        "friction_norm", "arousal_norm", "turn_num", "turn_progress",
        "prior_friction_norm", "prior_present",
    ],
    "onehot_blocks": {name: list(vals) + ["other"] for name, vals in _BLOCKS},
}


# --------------------------------------------------------------------------- #
# Small pure helpers (total, never raise).
# --------------------------------------------------------------------------- #
def _num(v, d: float = 0.0) -> float:
    try:
        f = float(v)
        return d if f != f else f          # NaN guard
    except Exception:  # noqa: BLE001
        return d


def _clip(x: float, lo: float, hi: float) -> float:
    return lo if x < lo else (hi if x > hi else x)


def _sigmoid(z: float) -> float:
    # numerically stable logistic
    if z >= 0:
        ez = math.exp(-z) if z < 700 else 0.0
        return 1.0 / (1.0 + ez)
    ez = math.exp(z) if z > -700 else 0.0
    return ez / (1.0 + ez)


def _logit(p: float) -> float:
    p = _clip(_num(p, 0.5), 1e-6, 1.0 - 1e-6)
    return math.log(p / (1.0 - p))


def _onehot(value: str, vocab) -> List[float]:
    """Fixed one-hot with a trailing 'other' slot (unknown/empty → other)."""
    out = [0.0] * (len(vocab) + 1)
    v = (str(value or "")).strip().lower()
    for i, k in enumerate(vocab):
        if v == k:
            out[i] = 1.0
            return out
    out[-1] = 1.0
    return out


# --------------------------------------------------------------------------- #
# featurize — turn dict → fixed-length numeric vector (see FEATURES layout).
# --------------------------------------------------------------------------- #
def featurize(turn: dict, prior: Optional[dict] = None) -> List[float]:
    """Map a trajectory turn (and optionally the PRIOR turn) to the fixed-length feature
    vector documented in FEATURES. Total/pure: a missing key → a sane default, never raises.
    Length is always exactly N_FEATURES."""
    try:
        turn = turn or {}
        friction = _num(turn.get("state_friction"), 50.0)
        arousal = _num(turn.get("state_arousal"), 50.0)
        turn_num = _num(turn.get("turn_num"), 0.0)
        call_len = _num(turn.get("call_len") or turn.get("call_turns"), 0.0)
        if call_len <= 0:
            # fall back to "at least this turn" so progress is in (0,1]
            call_len = max(turn_num, 1.0)
        progress = _clip(turn_num / max(call_len, 1.0), 0.0, 1.0)

        prior = prior or {}
        prior_present = 1.0 if prior else 0.0
        prior_friction = _num(prior.get("state_friction"), 50.0) if prior else 50.0

        feats: List[float] = [
            _clip(friction / 100.0, 0.0, 1.0),
            _clip(arousal / 100.0, 0.0, 1.0),
            turn_num,
            progress,
            _clip(prior_friction / 100.0, 0.0, 1.0),
            prior_present,
        ]
        feats += _onehot(turn.get("state_regime"), _REGIMES)
        feats += _onehot(turn.get("move_type"), _MOVES)
        feats += _onehot(turn.get("objection_type"), _OBJECTIONS)
        feats += _onehot(turn.get("lead_temperature"), _TEMPS)

        # belt-and-braces: guarantee exact length even if a vocab edit slips.
        if len(feats) < N_FEATURES:
            feats += [0.0] * (N_FEATURES - len(feats))
        elif len(feats) > N_FEATURES:
            feats = feats[:N_FEATURES]
        return feats
    except Exception as exc:  # noqa: BLE001
        logger.warning("critic.featurize failed: %s", exc)
        return [0.0] * N_FEATURES


# --------------------------------------------------------------------------- #
# predict — calibrated P(book) for a feature vector.
# --------------------------------------------------------------------------- #
def _parse_coef(model) -> Optional[dict]:
    """Accept a CriticModel, its parsed coef dict, or a JSON string → {w, b, platt_a, platt_b}."""
    if model is None:
        return None
    try:
        if isinstance(model, dict):
            d = model
        elif isinstance(model, str):
            d = json.loads(model)
        else:
            # a schema.CriticModel — pull coef_json + platt params off the dataclass
            raw = getattr(model, "coef_json", "") or ""
            d = json.loads(raw) if raw else {}
            d.setdefault("platt_a", _num(getattr(model, "platt_a", 1.0), 1.0))
            d.setdefault("platt_b", _num(getattr(model, "platt_b", 0.0), 0.0))
        w = [float(x) for x in (d.get("w") or [])]
        b = _num(d.get("b"), 0.0)
        return {
            "w": w,
            "b": b,
            "platt_a": _num(d.get("platt_a"), 1.0),
            "platt_b": _num(d.get("platt_b"), 0.0),
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("critic._parse_coef failed: %s", exc)
        return None


def predict(features: List[float], model) -> float:
    """Calibrated P(book) ∈ [0,1]. Raw logistic z = w·x + b → sigmoid; then Platt-scale the
    LOGIT: p = sigmoid(platt_a · logit(p_raw) + platt_b). model = a CriticModel, a parsed coef
    dict, or a JSON coef string. Returns 0.5 (the agnostic prior) on any error / missing model."""
    try:
        coef = _parse_coef(model)
        if not coef or not coef["w"]:
            return 0.5
        w = coef["w"]
        x = list(features or [])
        # tolerate a length mismatch (pad/truncate) so an old model never raises on a new vector.
        if len(x) < len(w):
            x = x + [0.0] * (len(w) - len(x))
        z = coef["b"] + sum(wi * _num(xi, 0.0) for wi, xi in zip(w, x))
        p_raw = _sigmoid(z)
        # Platt calibration on the logit.
        p_cal = _sigmoid(coef["platt_a"] * _logit(p_raw) + coef["platt_b"])
        return _clip(p_cal, 0.0, 1.0)
    except Exception as exc:  # noqa: BLE001
        logger.warning("critic.predict failed: %s", exc)
        return 0.5


# --------------------------------------------------------------------------- #
# Calibration metrics — pure-python (no sklearn).
# --------------------------------------------------------------------------- #
def ece(probs: List[float], labels: List[float], bins: int = 10) -> float:
    """Expected Calibration Error: |accuracy − confidence| averaged over equal-width prob bins,
    weighted by bin population. 0 == perfectly calibrated. Returns 1.0 (worst) on bad input."""
    try:
        ps = [_clip(_num(p, 0.5), 0.0, 1.0) for p in (probs or [])]
        ys = [1.0 if _num(y, 0.0) > 0.5 else 0.0 for y in (labels or [])]
        n = min(len(ps), len(ys))
        if n == 0:
            return 1.0
        ps, ys = ps[:n], ys[:n]
        bins = max(1, int(bins))
        sums = [0.0] * bins      # sum of probabilities in bin
        accs = [0.0] * bins      # sum of labels in bin
        cnts = [0] * bins
        for p, y in zip(ps, ys):
            b = min(bins - 1, int(p * bins))
            sums[b] += p
            accs[b] += y
            cnts[b] += 1
        total = 0.0
        for b in range(bins):
            if cnts[b] == 0:
                continue
            conf = sums[b] / cnts[b]
            acc = accs[b] / cnts[b]
            total += (cnts[b] / n) * abs(acc - conf)
        return round(_clip(total, 0.0, 1.0), 5)
    except Exception as exc:  # noqa: BLE001
        logger.warning("critic.ece failed: %s", exc)
        return 1.0


def auc(probs: List[float], labels: List[float]) -> float:
    """ROC-AUC via the rank-sum (Mann-Whitney U) identity — pure-python, ties averaged.
    0.5 == no discrimination. Returns 0.5 on degenerate input (all one class / empty)."""
    try:
        ps = [_num(p, 0.5) for p in (probs or [])]
        ys = [1.0 if _num(y, 0.0) > 0.5 else 0.0 for y in (labels or [])]
        n = min(len(ps), len(ys))
        if n == 0:
            return 0.5
        ps, ys = ps[:n], ys[:n]
        pos = sum(1 for y in ys if y > 0.5)
        neg = n - pos
        if pos == 0 or neg == 0:
            return 0.5
        # average ranks of the scores (1-based), ties share the mean rank.
        order = sorted(range(n), key=lambda i: ps[i])
        ranks = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j + 1 < n and ps[order[j + 1]] == ps[order[i]]:
                j += 1
            avg_rank = (i + j) / 2.0 + 1.0     # mean of 1-based ranks i..j
            for k in range(i, j + 1):
                ranks[order[k]] = avg_rank
            i = j + 1
        sum_pos = sum(ranks[i] for i in range(n) if ys[i] > 0.5)
        u = sum_pos - pos * (pos + 1) / 2.0
        return round(_clip(u / (pos * neg), 0.0, 1.0), 5)
    except Exception as exc:  # noqa: BLE001
        logger.warning("critic.auc failed: %s", exc)
        return 0.5


# --------------------------------------------------------------------------- #
# Shaping helpers — BSRS-bounded potential + momentum.
# --------------------------------------------------------------------------- #
def pbrs_potential(v: float, *, eta: float = 0.3) -> float:
    """BSRS-bounded value potential Φ = η·(V − 0.5), centred so a neutral state (V=0.5) has
    zero potential and the magnitude is capped by η. This is the TRAINED replacement for the
    hand-set Φ = -friction/100 in reward.affect_delta_shaping. Bounded → anti-Goodhart: a
    confident critic can never override the outcome reward. Returns 0.0 on bad input."""
    try:
        vv = _clip(_num(v, 0.5), 0.0, 1.0)
        e = _num(eta, 0.3)
        return round(e * (vv - 0.5), 6)
    except Exception as exc:  # noqa: BLE001
        logger.warning("critic.pbrs_potential failed: %s", exc)
        return 0.0


def momentum(v_now: float, v_prev: float) -> float:
    """Per-turn value momentum ΔV = V(s_t) − V(s_{t-1}) — the dense "are we getting closer to a
    booking this turn" signal. Clamped to [-1, 1]. Returns 0.0 on bad input."""
    try:
        return round(_clip(_num(v_now, 0.5) - _num(v_prev, 0.5), -1.0, 1.0), 6)
    except Exception as exc:  # noqa: BLE001
        logger.warning("critic.momentum failed: %s", exc)
        return 0.0


# --------------------------------------------------------------------------- #
# Trainer internals — deterministic logistic GD + Platt scaling.
# --------------------------------------------------------------------------- #
def _train_logistic(X: List[List[float]], y: List[float], *,
                    epochs: int = 200, lr: float = 0.3, l2: float = 1e-3,
                    seed: int = 1234) -> tuple:
    """Deterministic batch gradient descent on binary logistic loss. Targets y may be SOFT
    (in [0,1]). Returns (w, b). Lazy-numpy vectorizes if present; otherwise a pure-python loop
    (same result up to float order). Standardizes nothing — features are already 0..1-ish."""
    n = len(X)
    d = len(X[0]) if n else N_FEATURES
    # try the vectorized path (lazy, optional) -------------------------------
    try:
        import numpy as np  # noqa: WPS433  (lazy: only here, behind the flag-gated trainer)
        Xa = np.asarray(X, dtype="float64")
        ya = np.asarray(y, dtype="float64")
        w = np.zeros(d, dtype="float64")
        b = 0.0
        for _ in range(int(epochs)):
            z = Xa.dot(w) + b
            p = 1.0 / (1.0 + np.exp(-np.clip(z, -700, 700)))
            err = p - ya
            grad_w = Xa.T.dot(err) / n + l2 * w
            grad_b = float(err.sum() / n)
            w -= lr * grad_w
            b -= lr * grad_b
        return [float(x) for x in w], float(b)
    except Exception:  # noqa: BLE001  (numpy absent OR any vectorized hiccup → pure python)
        pass
    # pure-python fallback ---------------------------------------------------
    w = [0.0] * d
    b = 0.0
    inv_n = 1.0 / n if n else 0.0
    for _ in range(int(epochs)):
        grad_w = [0.0] * d
        grad_b = 0.0
        for xi, yi in zip(X, y):
            z = b + sum(w[k] * xi[k] for k in range(d))
            p = _sigmoid(z)
            err = p - yi
            grad_b += err
            for k in range(d):
                grad_w[k] += err * xi[k]
        for k in range(d):
            w[k] -= lr * (grad_w[k] * inv_n + l2 * w[k])
        b -= lr * (grad_b * inv_n)
    return w, b


def _raw_proba(X: List[List[float]], w: List[float], b: float) -> List[float]:
    return [_sigmoid(b + sum(w[k] * xi[k] for k in range(len(w)))) for xi in X]


def _platt_fit(p_raw: List[float], y: List[float], *, epochs: int = 200, lr: float = 0.2) -> tuple:
    """Fit Platt scaling a·logit(p)+b by logistic GD on the held split. Returns (a, b)."""
    logits = [_logit(p) for p in p_raw]
    a, b = 1.0, 0.0
    n = len(logits)
    if n == 0:
        return 1.0, 0.0
    inv_n = 1.0 / n
    yb = [1.0 if _num(t, 0.0) > 0.5 else 0.0 for t in y]   # Platt calibrates against HARD labels
    for _ in range(int(epochs)):
        ga = gb = 0.0
        for li, yi in zip(logits, yb):
            p = _sigmoid(a * li + b)
            err = p - yi
            ga += err * li
            gb += err
        a -= lr * ga * inv_n
        b -= lr * gb * inv_n
    return a, b


# --------------------------------------------------------------------------- #
# train_critic — the offline/worker entrypoint.
# --------------------------------------------------------------------------- #
async def train_critic(tenant_id: str, *, cfg=None):
    """Pull recent turns from flywheel_trajectories (FINAL), PROPAGATE each call's terminal booked
    label onto EVERY turn (partial-sequence labeling), build a SOFT target by blending that binary
    label with the matched-state cohort book-rate, train a deterministic logistic V(state) by batch
    GD, Platt-calibrate + score (auc/ece) on a held split, gate active, persist a schema.CriticModel
    via _st.insert_critic_model, and return it.

    Dormant / insufficient-data / any error → an INACTIVE CriticModel (never raises)."""
    cfg = cfg or _cfg.load()
    vertical = "real_estate"
    inactive = S.CriticModel(
        tenant_id=str(tenant_id or ""), vertical=vertical, ts_iso=S.now_iso(),
        model_type=str(getattr(cfg, "critic_model", "logistic") or "logistic"),
        coef_json="", platt_a=1.0, platt_b=0.0, auc=0.0, ece=1.0, n_rows=0, active=False,
    )
    try:
        if not tenant_id:
            return inactive
        if not cfg.critic_active() and not cfg.read_active():
            # dormant: no warehouse to read — return the inactive sentinel.
            return inactive

        min_rows = int(getattr(cfg, "critic_min_rows", 5000) or 5000)
        table = _st._final(_st.TRAJECTORIES)  # 'flywheel_trajectories FINAL'

        # --- (1) terminal booked label per CALL (partial-sequence labeling).
        # A call is positive iff ANY turn has reward_capped > 0.5 (a terminal positive somewhere).
        # Compute it call-side so we can back-propagate the SAME label onto every turn.
        where = "tenant_id = {tid:String} AND ts > now() - INTERVAL {m:UInt32} MINUTE"
        params = {"tid": str(tenant_id), "m": int(60 * 24 * 90)}   # 90-day window
        # group state into a coarse bucket so the cohort book-rate is the matched-state soft target.
        rows_sql = (
            f"SELECT call_id, turn_num, state_friction, state_arousal, "
            f"state_regime, move_type, objection_type, lead_temperature, "
            f"maxOver_call AS call_booked, call_len "
            f"FROM ("
            f"  SELECT call_id, turn_num, state_friction, state_arousal, state_regime, "
            f"  move_type, objection_type, lead_temperature, "
            f"  max(if(reward_capped > 0.5, 1, 0)) OVER (PARTITION BY call_id) AS maxOver_call, "
            f"  count() OVER (PARTITION BY call_id) AS call_len "
            f"  FROM {table} WHERE {where}"
            f") LIMIT 500000"
        )
        res = await _st._ch(rows_sql, params)
        if res.get("error"):
            logger.warning("critic.train_critic read error: %s", res.get("error"))
            return inactive
        rows = res.get("rows") or []
        if len(rows) < min_rows:
            logger.info("critic.train_critic: %d rows < critic_min_rows=%d → inactive",
                        len(rows), min_rows)
            inactive.n_rows = len(rows)
            return inactive

        # --- (2) matched-state cohort book-rate (soft target component).
        # bucket = (regime, move, objection, temperature, coarse friction band).
        def _bucket(r: dict) -> tuple:
            fr = _num(r.get("state_friction"), 50.0)
            band = int(_clip(fr, 0.0, 99.9) // 25)   # 0..3 friction quartile band
            return (
                str(r.get("state_regime") or "steady"),
                str(r.get("move_type") or "other"),
                str(r.get("objection_type") or "none"),
                str(r.get("lead_temperature") or "unknown"),
                band,
            )
        cohort_pos: dict = {}
        cohort_n: dict = {}
        labels_bin: List[float] = []
        for r in rows:
            yb = 1.0 if _num(r.get("call_booked"), 0.0) > 0.5 else 0.0
            labels_bin.append(yb)
            bk = _bucket(r)
            cohort_n[bk] = cohort_n.get(bk, 0) + 1
            cohort_pos[bk] = cohort_pos.get(bk, 0.0) + yb

        # --- (3) featurize + SOFT target (OmegaPRM-style blend).
        kappa = 0.6   # binary weight; (1-kappa) on the matched-state cohort rate.
        X: List[List[float]] = []
        Y: List[float] = []
        prior_by_call: dict = {}
        for r, yb in zip(rows, labels_bin):
            cid = str(r.get("call_id") or "")
            prior = prior_by_call.get(cid)
            feat_turn = dict(r)
            feat_turn["call_len"] = r.get("call_len")
            X.append(featurize(feat_turn, prior))
            prior_by_call[cid] = r
            bk = _bucket(r)
            crate = (cohort_pos[bk] / cohort_n[bk]) if cohort_n.get(bk) else yb
            Y.append(_clip(kappa * yb + (1.0 - kappa) * crate, 0.0, 1.0))

        # --- (4) deterministic train/calibration split (seeded; held split for Platt+metrics).
        rng = random.Random(1234)
        idx = list(range(len(X)))
        rng.shuffle(idx)
        cut = int(len(idx) * 0.8)
        tr, ho = idx[:cut], idx[cut:]
        if not tr or not ho:
            inactive.n_rows = len(rows)
            return inactive
        Xtr = [X[i] for i in tr]
        Ytr = [Y[i] for i in tr]
        Xho = [X[i] for i in ho]
        Yho_bin = [labels_bin[i] for i in ho]      # gate metrics use HARD labels

        # --- (5) train logistic on SOFT targets, Platt-calibrate on the held split.
        w, b = _train_logistic(Xtr, Ytr, seed=1234)
        p_ho_raw = _raw_proba(Xho, w, b)
        a_platt, b_platt = _platt_fit(p_ho_raw, Yho_bin)
        p_ho_cal = [_sigmoid(a_platt * _logit(p) + b_platt) for p in p_ho_raw]

        # --- (6) honest metrics on the held split + the active gate.
        au = auc(p_ho_cal, Yho_bin)
        ec = ece(p_ho_cal, Yho_bin)
        n_total = len(rows)
        is_active = bool(ec <= 0.1 and au >= 0.55 and n_total >= min_rows)

        coef_json = json.dumps({
            "w": [round(x, 7) for x in w],
            "b": round(b, 7),
            "platt_a": round(a_platt, 7),
            "platt_b": round(b_platt, 7),
            "features": FEATURES,
        }, ensure_ascii=False)

        model = S.CriticModel(
            tenant_id=str(tenant_id), vertical=vertical, ts_iso=S.now_iso(),
            model_type=str(getattr(cfg, "critic_model", "logistic") or "logistic"),
            coef_json=coef_json, platt_a=round(a_platt, 7), platt_b=round(b_platt, 7),
            auc=round(au, 5), ece=round(ec, 5), n_rows=n_total, active=is_active,
        )
        # best-effort persist (no-op when dormant / writes off).
        try:
            _st.insert_critic_model([model])
        except Exception as exc:  # noqa: BLE001
            logger.warning("critic.train_critic persist failed: %s", exc)
        logger.info("critic.train_critic tenant=%s n=%d auc=%.3f ece=%.3f active=%s",
                    tenant_id, n_total, au, ec, is_active)
        return model
    except Exception as exc:  # noqa: BLE001
        logger.warning("critic.train_critic failed: %s", exc)
        return inactive


# --------------------------------------------------------------------------- #
# load_critic — read the latest ACTIVE critic for live shaping.
# --------------------------------------------------------------------------- #
async def load_critic(tenant_id: str):
    """Return the latest ACTIVE schema.CriticModel for the tenant, or None. Best-effort: any
    read error / no active critic → None (the caller keeps the hand-set friction fallback)."""
    try:
        if not tenant_id:
            return None
        res = await _st.read_critic(str(tenant_id))
        if res.get("error"):
            logger.warning("critic.load_critic read error: %s", res.get("error"))
        for r in (res.get("critics") or []):
            if int(_num(r.get("active"), 0.0)) != 1:
                continue
            return S.CriticModel(
                tenant_id=str(tenant_id),
                vertical=str(r.get("vertical") or "real_estate"),
                ts_iso=str(r.get("ts") or ""),
                model_type=str(r.get("model_type") or "logistic"),
                coef_json=str(r.get("coef_json") or ""),
                platt_a=_num(r.get("platt_a"), 1.0),
                platt_b=_num(r.get("platt_b"), 0.0),
                auc=_num(r.get("auc"), 0.0),
                ece=_num(r.get("ece"), 1.0),
                n_rows=int(_num(r.get("n_rows"), 0.0)),
                active=True,
            )
        return None
    except Exception as exc:  # noqa: BLE001
        logger.warning("critic.load_critic failed: %s", exc)
        return None


# --------------------------------------------------------------------------- #
# Self-check — pure-python happy path (NO network / NO ClickHouse / NO numpy).
# --------------------------------------------------------------------------- #
if __name__ == "__main__":  # pragma: no cover
    import asyncio

    logging.basicConfig(level=logging.INFO)
    print(f"[critic] N_FEATURES = {N_FEATURES}")

    # --- featurize: fixed length + sane defaults ---------------------------
    t0 = {"state_friction": 70, "state_arousal": 40, "turn_num": 3, "call_len": 10,
          "state_regime": "rising", "move_type": "objection_rebuttal",
          "objection_type": "price", "lead_temperature": "warm"}
    t1 = {"state_friction": 45, "state_arousal": 55, "turn_num": 4, "call_len": 10,
          "state_regime": "resolving", "move_type": "cta_push",
          "objection_type": "none", "lead_temperature": "hot"}
    f0 = featurize(t0)
    f1 = featurize(t1, prior=t0)
    assert len(f0) == N_FEATURES and len(f1) == N_FEATURES, "feature length must be fixed"
    assert len(featurize({})) == N_FEATURES, "empty turn must still be N_FEATURES long"
    print(f"[critic] featurize ok (len={len(f0)})")

    # --- synthetic separable training set (booked when low friction + resolving) ----
    rng = random.Random(7)
    X: List[List[float]] = []
    Ybin: List[float] = []
    for _ in range(400):
        fr = rng.uniform(0, 100)
        booked = 1.0 if (fr < 45 and rng.random() < 0.85) else (1.0 if rng.random() < 0.1 else 0.0)
        turn = {"state_friction": fr, "state_arousal": rng.uniform(0, 100),
                "turn_num": rng.randint(1, 12), "call_len": 12,
                "state_regime": "resolving" if booked else "rising",
                "move_type": "cta_push" if booked else "probe",
                "objection_type": "none" if booked else "price",
                "lead_temperature": "hot" if booked else "cold"}
        X.append(featurize(turn))
        Ybin.append(booked)

    w, b = _train_logistic(X, Ybin, epochs=150)
    p_raw = _raw_proba(X, w, b)
    a, bp = _platt_fit(p_raw, Ybin)
    p_cal = [_sigmoid(a * _logit(p) + bp) for p in p_raw]
    au = auc(p_cal, Ybin)
    ec = ece(p_cal, Ybin)
    print(f"[critic] trained: auc={au:.3f} ece={ec:.3f} (a={a:.3f} b={bp:.3f})")
    assert au >= 0.55, f"AUC should beat chance on separable data (got {au})"
    assert 0.0 <= ec <= 1.0

    # --- predict via a CriticModel round-trip ------------------------------
    coef_json = json.dumps({"w": w, "b": b, "platt_a": a, "platt_b": bp, "features": FEATURES})
    cm = S.CriticModel(tenant_id="t_demo", coef_json=coef_json, platt_a=a, platt_b=bp,
                       auc=au, ece=ec, n_rows=len(X), active=True)
    p_book_hot = predict(featurize({"state_friction": 20, "state_regime": "resolving",
                                    "move_type": "cta_push", "objection_type": "none",
                                    "lead_temperature": "hot", "turn_num": 8, "call_len": 10}), cm)
    p_book_cold = predict(featurize({"state_friction": 90, "state_regime": "rising",
                                     "move_type": "probe", "objection_type": "price",
                                     "lead_temperature": "cold", "turn_num": 2, "call_len": 10}), cm)
    print(f"[critic] predict: P(book|hot)={p_book_hot:.3f}  P(book|cold)={p_book_cold:.3f}")
    assert 0.0 <= p_book_cold <= p_book_hot <= 1.0, "low-friction state should value higher"
    assert predict([], None) == 0.5, "no model → agnostic 0.5"

    # --- shaping helpers ---------------------------------------------------
    phi = pbrs_potential(p_book_hot, eta=0.3)
    mom = momentum(p_book_hot, p_book_cold)
    print(f"[critic] pbrs_potential(hot)={phi:+.4f}  momentum(hot,cold)={mom:+.4f}")
    assert -0.15 <= phi <= 0.15, "BSRS potential bounded by eta/2"
    assert mom >= 0.0, "value rose hot vs cold → non-negative momentum"

    # --- ece/auc edge cases ------------------------------------------------
    assert auc([0.5, 0.5], [1, 1]) == 0.5, "single-class → 0.5"
    assert ece([], []) == 1.0, "empty → worst ece"

    # --- train_critic is dormant-safe (no CH configured → inactive, no raise) ----
    m = asyncio.get_event_loop().run_until_complete(train_critic("t_demo"))
    assert m is not None and m.active is False, "dormant train must return inactive model"
    print(f"[critic] dormant train_critic → active={m.active} n_rows={m.n_rows}")

    # --- load_critic dormant-safe -----------------------------------------
    lc = asyncio.get_event_loop().run_until_complete(load_critic("t_demo"))
    assert lc is None, "dormant load_critic → None"

    print("[critic] self-check OK")
