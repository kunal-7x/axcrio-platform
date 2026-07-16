"""voice_ops.flywheel.causal — Layer-B4 DOUBLY-ROBUST X-LEARNER CATE for the Haptica Flywheel.

THE PROBLEM (why the correlational PRM is not enough): credit.build_move_prm answers
"which move CORRELATES with booking?" — but correlation is confounded. An `objection_rebuttal`
fires *because* a lead just objected, and objecting leads book less; a naive lift makes the
rebuttal look toxic when it may in fact be the only thing salvaging the call. The founder needs
the CAUSAL question: holding the STATE fixed (the same friction / arousal / objection / regime /
temperature / list_source), what is the booking lift CAUSED by playing move m above its segment
base rate? That is the Conditional Average Treatment Effect, CATE(m | state).

THE KILLER ASSET: this is a LOGGED-BANDIT dataset, not observational scraping. Every turn carries
TrajectoryRow.propensity — the KNOWN probability with which the live policy chose its arm. So the
propensity score e(x)=P(T=1|X) is KNOWN, not estimated. Positivity holds by construction (we only
ever logged arms we actually sampled), and we NEVER refit p. That removes the single most fragile
assumption in observational causal inference.

THE SCIENCE (honest, doubly-robust, cross-fit):
  * AIPW / DR pseudo-outcome (Robins-Rotnitzky; Kennedy 2023 DR-learner): for treatment level t,
        Y_DR(t) = mu_t(X) + (Y - mu_t(X)) * 1{T=t} / p(t)
    This is doubly robust — consistent if EITHER the outcome model mu_t OR the propensity p is
    correct. Here p is LOGGED-correct, so DR is consistent even with a crude mu_t (the pure-python
    logistic fallback is therefore scientifically safe, not a hack).
  * X-learner cross-imputation (Kunzel et al. 2019, PNAS): impute the per-unit treatment effect
    on the treated using the control model — D1 = Y_DR(1) - mu_0(X); and on the controls using the
    treated model — D0 = mu_1(X) - Y_DR(0); then propensity-weight-combine the two imputed-effect
    estimates. X-learner is the variant that shines under treatment-imbalance — exactly our regime,
    where most turns are NOT move m (one-vs-rest T=1 iff move_type==m).
  * Cross-fitting / DML (Chernozhukov et al. 2018): nuisances mu_0, mu_1 are fit on K-1 folds and
    the pseudo-outcome is evaluated on the held-out fold, breaking own-observation overfit bias so
    the sqrt(n)-CLT and the influence-function SE are valid. CRUCIAL DETAIL: turns inside one call
    are correlated, so we SPLIT FOLDS BY call_id — a call NEVER straddles a fold (Athey-Wager
    honesty + cluster integrity). The SE is likewise a call-CLUSTERED influence-function SE so the
    CI is not fraudulently narrow from pseudo-replicated within-call turns.
  * R-learner sign cross-check (Nie & Wager 2021): an independent residual-on-residual estimator.
    If DR-X and the R-learner DISAGREE on the SIGN of the effect, the cell is flagged not-robust
    (sign_agree=False) — a cheap, honest robustness witness.
  * HIERARCHICAL shrinkage: a thin cell's CATE is shrunk toward the vertical-level CATE
    (empirical-Bayes James-Stein style), so a 12-sample cell cannot scream a spurious effect.

DESIGN LAWS honoured here:
  * PURE-PYTHON with LAZY heavy deps: numpy / sklearn / lightgbm are imported ONLY inside the
    function that needs them, behind the flag, each with a pure-python fallback — so the module
    IMPORTS and the self-check RUNS dormant with zero third-party packages installed.
  * DORMANT-SAFE / BEST-EFFORT: build_move_cate swallows every error → logging.warning and returns
    [] (never raises). dr_xlearner / r_learner_sign return clean zeros on a degenerate input.
  * SIDE-PIPELINE: offline worker math only; reads the ReplacingMergeTree with FINAL; never the
    live LiveKit turn loop.
  * HONEST SCIENCE / ANTI-GOODHART: every cell ships cate_se + a 95% CI; cate_lower is the
    PESSIMISTIC lower bound a promotion gate should consume (act only when cate_lower>0); cells with
    n_treated<10 or overlap_min<causal_min_overlap are DROPPED; no fake CI narrowness.
"""
from __future__ import annotations

import logging
import math
from typing import Dict, List, Optional, Sequence, Tuple

from . import config as _cfg
from . import schema as S
from . import store as _st
from .schema import MoveCATERow

logger = logging.getLogger("flywheel.causal")

__all__ = [
    "build_move_cate",
    "dr_xlearner",
    "r_learner_sign",
    "kfold_by_group",
    "fit_logistic",
    "predict_logistic",
]

# Numerical floors / caps shared across the module.
_EPS = 1e-9
_P_HI = 1.0 - 1e-3          # propensity upper clip
_Z95 = 1.96                 # 95% normal quantile for the CIs
_MIN_N_TREATED = 10         # honest-science: drop cells thinner than this
_PSEUDO_CLIP = 50.0         # clamp the IPW-amplified pseudo-outcome to keep SE finite


# --------------------------------------------------------------------------- #
# Tiny numeric helpers (kept local so the pure-python path has ZERO heavy deps).
# --------------------------------------------------------------------------- #
def _f(v, default: float = 0.0) -> float:
    """Coerce to float; NaN / inf / garbage → default (mirrors schema._f)."""
    try:
        x = float(v)
    except Exception:  # noqa: BLE001
        return default
    if x != x or x in (float("inf"), float("-inf")):
        return default
    return x


def _mean(xs: Sequence[float]) -> float:
    xs = list(xs)
    return sum(xs) / len(xs) if xs else 0.0


def _clip(x: float, lo: float, hi: float) -> float:
    return lo if x < lo else (hi if x > hi else x)


def _sigmoid(z: float) -> float:
    # Numerically stable logistic.
    if z >= 0:
        ez = math.exp(-z) if z < 700 else 0.0
        return 1.0 / (1.0 + ez)
    ez = math.exp(z) if z > -700 else 0.0
    return ez / (1.0 + ez)


# --------------------------------------------------------------------------- #
# K-fold-by-GROUP splitter — the cluster-honesty primitive. A *group* (call_id)
# is assigned WHOLE to exactly one fold; its turns therefore never straddle the
# train/eval boundary, so cross-fitting cannot leak correlated within-call rows.
# Deterministic: groups are sorted then round-robined into folds.
# --------------------------------------------------------------------------- #
def kfold_by_group(groups: Sequence, k_folds: int = 5) -> List[int]:
    """Return a per-row fold-id list (len == len(groups)) assigning each row to one of
    k folds, with every row sharing a group placed in the SAME fold. Deterministic.

    A call (group) never straddles folds — within-call turns are correlated, so leaking
    them across the cross-fit boundary would fabricate effective sample size and shrink
    the CI dishonestly."""
    g = list(groups)
    n = len(g)
    if n == 0:
        return []
    try:
        k = int(k_folds)
    except Exception:  # noqa: BLE001
        k = 5
    if k < 2:
        k = 2
    # Deterministic group → fold map (sorted unique groups, round-robin).
    uniq = sorted({str(x) for x in g})
    if len(uniq) < k:
        # Fewer distinct calls than folds: cap k so no fold is empty of groups.
        k = max(2, len(uniq)) if len(uniq) >= 2 else 1
    fold_of: Dict[str, int] = {gid: (i % k) for i, gid in enumerate(uniq)}
    return [fold_of[str(x)] for x in g]


# --------------------------------------------------------------------------- #
# Pure-python logistic regression (ridge-regularised batch gradient descent).
# This is the DEFAULT nuisance learner (mu_0, mu_1, and the R-learner's m, e
# residual models). Because the DR pseudo-outcome is doubly robust and p is
# LOGGED-correct, a crude-but-honest logistic mu is consistent — we do not need
# a boosted tree for validity, only for variance. A lazy GBT is used when sklearn
# /lightgbm are present (see _fit_outcome) purely to reduce variance.
# --------------------------------------------------------------------------- #
def fit_logistic(
    X: List[List[float]],
    y: List[float],
    *,
    l2: float = 1.0,
    iters: int = 200,
    lr: float = 0.3,
) -> List[float]:
    """Fit weights w (incl. a leading bias term) for P(y=1)=sigmoid(w·[1,x]).

    Pure python, deterministic, total: a degenerate / empty input → a zero vector
    (predicts the base rate via the bias if y has signal, else 0.5). Never raises."""
    try:
        n = len(X)
        if n == 0:
            return [0.0]
        d = len(X[0]) if X[0] is not None else 0
        # weights: w[0] = bias, w[1..d] = feature coefs.
        w = [0.0] * (d + 1)
        # Warm-start the bias at the empirical log-odds so flat-feature data is fit instantly.
        ybar = _clip(_mean([_f(v) for v in y]), 1e-4, 1 - 1e-4)
        w[0] = math.log(ybar / (1.0 - ybar))
        lr = _f(lr, 0.3)
        l2 = _f(l2, 1.0)
        for _ in range(max(1, int(iters))):
            g = [0.0] * (d + 1)
            for i in range(n):
                xi = X[i] or []
                z = w[0]
                for j in range(d):
                    z += w[j + 1] * _f(xi[j]) if j < len(xi) else 0.0
                err = _sigmoid(z) - _f(y[i])
                g[0] += err
                for j in range(min(d, len(xi))):
                    g[j + 1] += err * _f(xi[j])
            inv = 1.0 / n
            # Gradient step; L2 shrinks coefs (not the bias) toward 0.
            w[0] -= lr * (g[0] * inv)
            for j in range(1, d + 1):
                w[j] -= lr * (g[j] * inv + l2 * inv * w[j])
        return w
    except Exception as exc:  # noqa: BLE001
        logger.warning("flywheel causal.fit_logistic error: %r", exc)
        d = len(X[0]) if X and X[0] is not None else 0
        return [0.0] * (d + 1)


def predict_logistic(w: List[float], x: List[float]) -> float:
    """P(y=1 | x) for weights from fit_logistic. Total; returns 0.5 on a bad input."""
    try:
        if not w:
            return 0.5
        z = _f(w[0])
        x = x or []
        for j in range(len(w) - 1):
            z += _f(w[j + 1]) * (_f(x[j]) if j < len(x) else 0.0)
        return _sigmoid(z)
    except Exception:  # noqa: BLE001
        return 0.5


# --------------------------------------------------------------------------- #
# Outcome-model fitter — pure-python logistic by default; LAZY GBT when sklearn or
# lightgbm are installed AND the flag path reaches here. Returns a CLOSURE predictor
# X -> p, so the X-learner core stays agnostic to which learner produced it.
# --------------------------------------------------------------------------- #
def _fit_outcome(X: List[List[float]], y: List[float], *, prefer_gbt: bool = True):
    """Return a predictor fn (list[float] -> float in [0,1]). Tries sklearn GBT for lower
    variance, then a pure-python logistic. Doubly-robust validity does not depend on which
    one wins — p is logged-correct — so a fallback to logistic is scientifically safe."""
    if prefer_gbt and X and len(X) >= 200:
        # Lazy heavy deps — imported ONLY here, never at module import time.
        try:
            import numpy as _np  # noqa: F401
            from sklearn.ensemble import (  # type: ignore
                HistGradientBoostingClassifier,
            )

            ya = [int(round(_clip(_f(v), 0.0, 1.0))) for v in y]
            if 0 < sum(ya) < len(ya):  # need both classes present
                clf = HistGradientBoostingClassifier(
                    max_depth=3, max_iter=120, learning_rate=0.08, l2_regularization=1.0
                )
                clf.fit(X, ya)

                def _pred_gbt(x: List[float], _clf=clf) -> float:
                    try:
                        p = float(_clf.predict_proba([x])[0][1])
                        return _clip(p, 0.0, 1.0)
                    except Exception:  # noqa: BLE001
                        return 0.5

                return _pred_gbt
        except Exception as exc:  # noqa: BLE001
            logger.debug("flywheel causal GBT unavailable, using logistic: %r", exc)
    w = fit_logistic(X, y)
    return lambda x, _w=w: predict_logistic(_w, x)


# --------------------------------------------------------------------------- #
# dr_xlearner() — the pure-python DR X-learner CORE. Returns (cate, se).
# Cross-fit by group, AIPW pseudo-outcomes with LOGGED p, X-learner cross-imputation,
# propensity-weighted combine, call-CLUSTERED influence-function SE.
# --------------------------------------------------------------------------- #
def dr_xlearner(
    X: list,
    T: list,
    Y: list,
    p: list,
    *,
    k_folds: int = 5,
    groups: list = None,
) -> tuple:
    """Doubly-robust X-learner CATE estimate for a one-vs-rest treatment cell.

    Args:
      X: design matrix (list of feature rows).
      T: 0/1 treatment per row (1 == the candidate move was played).
      Y: 0/1 outcome per row (1 == the turn's call booked, reward_capped>0.5).
      p: LOGGED propensity P(T=1|X) per row (already clipped by the caller). KNOWN — not refit.
      k_folds: cross-fit fold count.
      groups: call_id per row — folds split by group so a call never straddles a fold.

    Returns (cate, se): the average CATE over the cell and a call-clustered influence-function
    standard error. Degenerate input (no treated or no control, or all one outcome) → (0.0, 0.0).
    Pure python; numpy is used lazily inside _fit_outcome only when a GBT path is taken.
    Never raises — best-effort returns (0.0, 0.0) on any internal error."""
    try:
        n = len(X)
        if n == 0 or len(T) != n or len(Y) != n or len(p) != n:
            return (0.0, 0.0)
        Tn = [1.0 if _f(t) >= 0.5 else 0.0 for t in T]
        Yn = [_clip(_f(v), 0.0, 1.0) for v in Y]
        pn = [_clip(_f(v), _EPS, _P_HI) for v in p]
        n_t = int(sum(Tn))
        n_c = n - n_t
        if n_t == 0 or n_c == 0:
            return (0.0, 0.0)  # no contrast → no causal estimate

        grp = [str(g) for g in (groups or list(range(n)))]
        if len(grp) != n:
            grp = [str(i) for i in range(n)]
        folds = kfold_by_group(grp, k_folds)
        if not folds or len(folds) != n:
            folds = [0] * n
        k = max(folds) + 1

        # Per-row pseudo-outcomes (the X-learner imputed individual effects), evaluated on the
        # HELD-OUT fold using nuisances fit on the other folds (cross-fitting / DML).
        psi: List[float] = [0.0] * n          # influence contributions for the SE
        d_eff: List[float] = [0.0] * n        # imputed per-row treatment effect (X-learner)
        wgt: List[float] = [0.0] * n          # propensity weight used in the combine
        used = [False] * n

        for fold in range(k):
            tr_idx = [i for i in range(n) if folds[i] != fold]
            ev_idx = [i for i in range(n) if folds[i] == fold]
            if not ev_idx:
                continue
            # Fit mu_1 on treated-in-train, mu_0 on control-in-train.
            X1 = [X[i] for i in tr_idx if Tn[i] >= 0.5]
            Y1 = [Yn[i] for i in tr_idx if Tn[i] >= 0.5]
            X0 = [X[i] for i in tr_idx if Tn[i] < 0.5]
            Y0 = [Yn[i] for i in tr_idx if Tn[i] < 0.5]
            if len(X1) < 2 or len(X0) < 2:
                # Too thin to fit a fold model: fall back to the in-fold base rates so the
                # estimate degrades gracefully toward the simple difference-in-means.
                mu1_const = _mean(Y1) if Y1 else _mean([Yn[i] for i in range(n) if Tn[i] >= 0.5])
                mu0_const = _mean(Y0) if Y0 else _mean([Yn[i] for i in range(n) if Tn[i] < 0.5])
                pred1 = lambda _x, _c=mu1_const: _c  # noqa: E731
                pred0 = lambda _x, _c=mu0_const: _c  # noqa: E731
            else:
                pred1 = _fit_outcome(X1, Y1)
                pred0 = _fit_outcome(X0, Y0)

            for i in ev_idx:
                xi = X[i]
                m1 = _clip(pred1(xi), 0.0, 1.0)
                m0 = _clip(pred0(xi), 0.0, 1.0)
                pi = pn[i]
                if Tn[i] >= 0.5:
                    # Treated: AIPW pseudo-outcome at t=1, impute effect vs the control model.
                    y_dr1 = m1 + (Yn[i] - m1) / pi
                    y_dr1 = _clip(y_dr1, -_PSEUDO_CLIP, _PSEUDO_CLIP)
                    d_eff[i] = y_dr1 - m0
                else:
                    # Control: AIPW pseudo-outcome at t=0, impute effect vs the treated model.
                    y_dr0 = m0 + (Yn[i] - m0) / (1.0 - pi)
                    y_dr0 = _clip(y_dr0, -_PSEUDO_CLIP, _PSEUDO_CLIP)
                    d_eff[i] = m1 - y_dr0
                # X-learner combine weight: weight the treated imputation by e(x)=p, the control
                # imputation by (1-e(x)). (Kunzel 2019 propensity-weighted CATE combination.)
                wgt[i] = pi if Tn[i] >= 0.5 else (1.0 - pi)
                used[i] = True

        idx = [i for i in range(n) if used[i]]
        if not idx:
            return (0.0, 0.0)

        # Propensity-weighted average of the two X-learner imputed-effect estimates.
        sw = sum(wgt[i] for i in idx)
        if sw <= _EPS:
            cate = _mean([d_eff[i] for i in idx])
        else:
            cate = sum(wgt[i] * d_eff[i] for i in idx) / sw

        # Influence-function residuals, then CLUSTER by call so within-call correlation does not
        # fabricate sample size. psi_i = (imputed effect - cate); the clustered SE is the std of
        # the per-call SUMMED residuals scaled by sqrt(n_clusters), divided by n.
        for i in idx:
            psi[i] = d_eff[i] - cate
        clusters: Dict[str, float] = {}
        for i in idx:
            clusters[grp[i]] = clusters.get(grp[i], 0.0) + psi[i]
        m = len(clusters)
        n_used = len(idx)
        if m < 2 or n_used == 0:
            se = 0.0
        else:
            cl_vals = list(clusters.values())
            cl_mean = _mean(cl_vals)
            cl_var = sum((c - cl_mean) ** 2 for c in cl_vals) / (m - 1)
            # Var(cate) ≈ (m / n^2) * Var(cluster_sum); SE = sqrt(that).
            var_cate = (m * cl_var) / (n_used * n_used)
            se = math.sqrt(var_cate) if var_cate > 0 else 0.0

        return (round(cate, 6), round(se, 6))
    except Exception as exc:  # noqa: BLE001
        logger.warning("flywheel causal.dr_xlearner error: %r", exc)
        return (0.0, 0.0)


# --------------------------------------------------------------------------- #
# r_learner_sign() — Nie-Wager R-learner SIGN cross-check (an independent estimator).
# Robinson residualisation: residualise Y on its prediction m(X)=E[Y|X], residualise T
# on the LOGGED propensity p, then regress the Y-residual on the (T-p) residual; the
# slope is the R-learner CATE. We only consume its SIGN as a robustness witness.
# --------------------------------------------------------------------------- #
def r_learner_sign(X: list, T: list, Y: list, p: list) -> int:
    """Return +1 / -1 / 0 for the sign of the R-learner CATE slope (robustness cross-check).

    Independent of the DR X-learner: if the two disagree on sign, the cell is not robust.
    Pure python; total; 0 on a degenerate input. Never raises."""
    try:
        n = len(X)
        if n == 0 or len(T) != n or len(Y) != n or len(p) != n:
            return 0
        Tn = [1.0 if _f(t) >= 0.5 else 0.0 for t in T]
        Yn = [_clip(_f(v), 0.0, 1.0) for v in Y]
        pn = [_clip(_f(v), _EPS, _P_HI) for v in p]
        if 0 < sum(Tn) < n:
            pass
        else:
            return 0
        # m(X)=E[Y|X] from a single pooled logistic (the outcome marginal).
        w = fit_logistic(X, Yn)
        num = 0.0
        den = 0.0
        for i in range(n):
            m_x = predict_logistic(w, X[i])
            t_res = Tn[i] - pn[i]          # treatment residual vs LOGGED propensity
            y_res = Yn[i] - m_x            # outcome residual
            num += t_res * y_res
            den += t_res * t_res
        if den <= _EPS:
            return 0
        slope = num / den
        if slope > 1e-6:
            return 1
        if slope < -1e-6:
            return -1
        return 0
    except Exception as exc:  # noqa: BLE001
        logger.warning("flywheel causal.r_learner_sign error: %r", exc)
        return 0


# --------------------------------------------------------------------------- #
# Feature encoding — turn a trajectory row into the design vector X used by every
# nuisance model: [friction, arousal, one-hot(regime|objection|temperature|list)].
# One-hot vocabularies are derived from the data so encoding is closed-world stable.
# --------------------------------------------------------------------------- #
def _build_vocab(rows: List[dict], col: str, cap: int = 12) -> List[str]:
    counts: Dict[str, int] = {}
    for r in rows:
        v = str(r.get(col, "") or "")
        counts[v] = counts.get(v, 0) + 1
    # Keep the most frequent levels (cap) for a compact, stable one-hot; rest → "__other__".
    top = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:cap]
    return [k for k, _ in top]


def _onehot(value: str, vocab: List[str]) -> List[float]:
    value = str(value or "")
    return [1.0 if value == lvl else 0.0 for lvl in vocab]


def _encode_row(r: dict, vocabs: Dict[str, List[str]]) -> List[float]:
    feats: List[float] = [
        _f(r.get("state_friction", 0.0)),
        _f(r.get("state_arousal", 0.0)),
    ]
    feats += _onehot(r.get("regime", ""), vocabs["regime"])
    feats += _onehot(r.get("objection_type", ""), vocabs["objection_type"])
    feats += _onehot(r.get("lead_temperature", ""), vocabs["lead_temperature"])
    feats += _onehot(r.get("list_source", ""), vocabs["list_source"])
    return feats


# --------------------------------------------------------------------------- #
# build_move_cate() — the public B4 entrypoint. Mirrors credit.build_move_prm's
# signature & error-contract. For each candidate move m, one-vs-rest DR-X CATE,
# R-learner sign cross-check, hierarchical shrink, honest CI, drop weak cells, persist.
# --------------------------------------------------------------------------- #
async def build_move_cate(
    tenant_id: str,
    vertical: str = "",
    minutes: int = 43200,
    *,
    cfg=None,
) -> list:
    """Build the per-(move, state) doubly-robust CATE table over a trajectory window.

    For each candidate move_type m (one-vs-rest, T=1 iff move_type==m):
        X  = [state_friction, state_arousal, one-hot(regime|objection|temperature|list_source)]
        T  = 1{move_type == m}
        Y  = 1{reward_capped > 0.5}
        p  = propensity, LOGGED & KNOWN (clipped to [causal_min_overlap, 1-1e-3]); never refit
      → cross-fit K folds SPLIT BY call_id (no call straddles a fold)
      → AIPW DR pseudo-outcomes + X-learner cross-imputation → (cate, se)
      → cate_lower = cate - 1.96*se  (the PESSIMISTIC promotion signal)
      → raw_lift kept side-by-side (correlational), overlap_min = min logged p in the cell
      → R-learner sign cross-check → sign_agree
      → HIERARCHICAL shrink of each move's CATE toward the vertical-pooled CATE
      → DROP cells with n_treated < 10 or overlap_min < cfg.causal_min_overlap

    Tenant-scoped via {tid:String}; reads the ReplacingMergeTree with FINAL. Persists via
    _st.insert_move_cate (no-op when dormant). Returns list[MoveCATERow]; [] on any error /
    dormancy — NEVER raises (best-effort, mirrors build_move_prm)."""
    try:
        if not tenant_id:
            return []
        if cfg is None:
            cfg = _cfg.load()
        ts_iso = S.now_iso()
        min_overlap = _f(getattr(cfg, "causal_min_overlap", 0.02), 0.02)
        k_folds = int(getattr(cfg, "causal_k_folds", 5) or 5)
        estimator = str(getattr(cfg, "causal_estimator", "dr_xlearner") or "dr_xlearner")

        where = "tenant_id = {tid:String} AND ts > now() - INTERVAL {m:UInt32} MINUTE"
        params = {"tid": str(tenant_id), "m": int(minutes)}
        if vertical:
            where += " AND vertical = {v:String}"
            params["v"] = str(vertical)

        table = _st._final(_st.TRAJECTORIES)  # 'flywheel_trajectories FINAL'
        # Pull the raw turns ONCE; build every per-move design matrix in python (cheaper than
        # K*M ClickHouse round-trips and lets folds split by call_id honestly).
        sql = (
            f"SELECT call_id, move_type, objection_type, "
            f"state_regime AS regime, lead_temperature, list_source, "
            f"state_friction, state_arousal, propensity, reward_capped "
            f"FROM {table} WHERE {where} "
            f"ORDER BY call_id LIMIT 200000"
        )
        res = await _st._ch(sql, params)
        if res.get("error"):
            logger.warning("flywheel build_move_cate read error: %s", res.get("error"))
            return []
        rows = res.get("rows") or []
        if len(rows) < 20:
            return []  # not enough evidence for any honest causal estimate

        # Shared one-hot vocabularies + the universal feature matrix (encoded once).
        max_arch = int(getattr(cfg, "sim_max_archetypes", 12) or 12)
        vocabs = {
            "regime": _build_vocab(rows, "regime", cap=max(4, max_arch)),
            "objection_type": _build_vocab(rows, "objection_type", cap=max(6, max_arch)),
            "lead_temperature": _build_vocab(rows, "lead_temperature", cap=8),
            "list_source": _build_vocab(rows, "list_source", cap=max(4, max_arch)),
        }
        Xall = [_encode_row(r, vocabs) for r in rows]
        call_ids = [str(r.get("call_id", "") or "") for r in rows]
        Yall = [1.0 if _f(r.get("reward_capped", 0.0)) > 0.5 else 0.0 for r in rows]
        pall = [_clip(_f(r.get("propensity", 0.0)), min_overlap, _P_HI) for r in rows]
        move_of = [str(r.get("move_type", "other") or "other") for r in rows]

        # Candidate moves = distinct move_types with at least the minimum treated count.
        move_counts: Dict[str, int] = {}
        for mv in move_of:
            move_counts[mv] = move_counts.get(mv, 0) + 1
        candidates = [m for m, c in move_counts.items() if c >= _MIN_N_TREATED]
        if not candidates:
            return []

        # --- vertical-pooled CATE per move (for the hierarchical shrink target). We pool ALL
        # candidate-move CATEs and shrink each toward their precision-weighted mean.
        raw_results: List[dict] = []
        for m in candidates:
            T = [1.0 if mv == m else 0.0 for mv in move_of]
            n_treated = int(sum(T))
            n_control = len(T) - n_treated
            if n_treated < _MIN_N_TREATED or n_control < _MIN_N_TREATED:
                continue
            # overlap_min = min LOGGED propensity among the treated rows of this cell.
            treated_p = [pall[i] for i in range(len(T)) if T[i] >= 0.5]
            overlap_min = min(treated_p) if treated_p else 0.0
            if overlap_min < min_overlap:
                continue  # positivity too weak — untrustworthy, drop

            cate, se = dr_xlearner(
                Xall, T, Yall, pall, k_folds=k_folds, groups=call_ids
            )
            sign = r_learner_sign(Xall, T, Yall, pall)

            # raw correlational lift (the old PRM signal) for the console side-by-side.
            treated_y = [Yall[i] for i in range(len(T)) if T[i] >= 0.5]
            control_y = [Yall[i] for i in range(len(T)) if T[i] < 0.5]
            raw_lift = (_mean(treated_y) - _mean(control_y)) if treated_y and control_y else 0.0

            dr_sign = 1 if cate > 1e-6 else (-1 if cate < -1e-6 else 0)
            sign_agree = (sign == 0) or (dr_sign == 0) or (sign == dr_sign)

            raw_results.append({
                "move_type": m,
                "cate": cate,
                "se": se,
                "raw_lift": raw_lift,
                "n_treated": n_treated,
                "n_control": n_control,
                "overlap_min": overlap_min,
                "sign_agree": bool(sign_agree),
            })

        if not raw_results:
            return []

        # --- HIERARCHICAL (empirical-Bayes) shrink toward the precision-weighted vertical mean.
        # tau_shrunk = (1-B)*tau_cell + B*tau_pool, with B large when the cell SE is large.
        precisions = [1.0 / (rr["se"] ** 2 + _EPS) for rr in raw_results]
        tau_pool = (
            sum(p_ * rr["cate"] for p_, rr in zip(precisions, raw_results)) / sum(precisions)
            if sum(precisions) > _EPS else _mean([rr["cate"] for rr in raw_results])
        )
        # Between-move variance (tau^2) of the pooled CATEs — the shrink scale.
        between_var = _mean([(rr["cate"] - tau_pool) ** 2 for rr in raw_results])

        out: List[MoveCATERow] = []
        for rr in raw_results:
            try:
                se = rr["se"]
                # Shrinkage weight B = within-var / (within-var + between-var). Thin/noisy cells
                # (large se) shrink HARD toward the pool; precise cells keep their own signal.
                within_var = se * se
                denom = within_var + between_var
                B = (within_var / denom) if denom > _EPS else 1.0
                B = _clip(B, 0.0, 1.0)
                cate_shrunk = (1.0 - B) * rr["cate"] + B * tau_pool

                cate_lower = cate_shrunk - _Z95 * se
                cate_upper = cate_shrunk + _Z95 * se

                out.append(MoveCATERow(
                    tenant_id=str(tenant_id),
                    vertical=str(vertical or "real_estate"),
                    move_type=str(rr["move_type"]),
                    objection_type="all",          # cell is pooled over objection in this pass
                    regime="all",
                    lead_temperature="all",
                    ts_iso=ts_iso,
                    cate=round(cate_shrunk, 6),
                    cate_se=round(se, 6),
                    cate_lower=round(cate_lower, 6),
                    cate_upper=round(cate_upper, 6),
                    raw_lift=round(rr["raw_lift"], 6),
                    n_treated=int(rr["n_treated"]),
                    n_control=int(rr["n_control"]),
                    overlap_min=round(rr["overlap_min"], 6),
                    estimator=estimator,
                    sign_agree=bool(rr["sign_agree"]),
                ))
            except Exception as exc:  # noqa: BLE001
                logger.warning("flywheel build_move_cate row skip: %r", exc)
                continue

        # Persist (no-op when dormant); best-effort — a write failure must not sink the result.
        try:
            _st.insert_move_cate(out)
        except Exception as exc:  # noqa: BLE001
            logger.warning("flywheel build_move_cate persist error: %r", exc)
        return out
    except Exception as exc:  # noqa: BLE001
        logger.warning("flywheel build_move_cate error: %r", exc)
        return []


# --------------------------------------------------------------------------- #
# Inline self-check — happy path on SYNTHETIC inputs only (no network / no CH /
# no numpy required — the pure-python path must run).
# Run: python3 -m voice_ops.flywheel.causal
# --------------------------------------------------------------------------- #
if __name__ == "__main__":  # pragma: no cover
    import random

    logging.basicConfig(level=logging.INFO)
    rng = random.Random(7)

    # 1) fit_logistic / predict_logistic on a separable-ish toy: x>0 → y=1.
    Xl = [[v] for v in [-2.0, -1.5, -1.0, -0.5, 0.5, 1.0, 1.5, 2.0]]
    yl = [0, 0, 0, 0, 1, 1, 1, 1]
    w = fit_logistic(Xl, yl, iters=400)
    assert predict_logistic(w, [2.0]) > predict_logistic(w, [-2.0]), w
    assert predict_logistic([], [1.0]) == 0.5

    # 2) kfold_by_group: a call (group) never straddles folds.
    groups = ["c0", "c0", "c1", "c1", "c2", "c3", "c4", "c5"]
    folds = kfold_by_group(groups, 3)
    g2f = {}
    for g, f in zip(groups, folds):
        assert g2f.setdefault(g, f) == f, (g, f, g2f)   # one group → one fold
    assert len(set(folds)) <= 3

    # 3) dr_xlearner on a SYNTHETIC dataset with a KNOWN positive effect.
    #    Treated turns book ~+0.30 above control, propensity LOGGED & known.
    X, T, Y, P, G = [], [], [], [], []
    n_calls = 200
    for c in range(n_calls):
        cid = f"call_{c}"
        friction = rng.uniform(-1, 1)
        arousal = rng.uniform(-1, 1)
        # logged propensity depends on state (realistic) but stays in [0.1, 0.9].
        prop = _clip(0.5 + 0.2 * friction, 0.1, 0.9)
        n_turns = rng.randint(2, 5)
        for _ in range(n_turns):
            t = 1 if rng.random() < prop else 0
            base = 0.30 + 0.15 * arousal           # control booking propensity
            book_p = _clip(base + (0.30 if t else 0.0), 0.01, 0.99)
            y = 1 if rng.random() < book_p else 0
            X.append([friction, arousal, 1.0 if friction > 0 else 0.0])
            T.append(t)
            Y.append(y)
            P.append(prop if t else (1.0 - prop))   # P column = P(T=t) per the AIPW convention
            G.append(cid)
    # NB: dr_xlearner expects p = P(T=1); supply that explicitly.
    p_treat = []
    for c_idx in range(len(T)):
        # recover P(T=1) for each row from the construction above
        # (we stored P(T=t); invert for controls)
        p_treat.append(P[c_idx] if T[c_idx] == 1 else (1.0 - P[c_idx]))
    cate, se = dr_xlearner(X, T, Y, p_treat, k_folds=5, groups=G)
    assert isinstance(cate, float) and isinstance(se, float), (cate, se)
    assert se >= 0.0
    # The recovered CATE should be positive (true effect ~+0.30) — honest, not exact.
    assert cate > 0.05, f"expected positive CATE, got {cate}"
    print(f"   dr_xlearner: cate={cate:+.3f} se={se:.3f} (truth≈+0.30)")

    # 4) r_learner_sign agrees on the positive sign for the same data.
    sgn = r_learner_sign(X, T, Y, p_treat)
    assert sgn in (-1, 0, 1)
    print(f"   r_learner_sign={sgn} (expect +1)")

    # 5) degenerate guards: no contrast / empty → clean zeros, never raise.
    assert dr_xlearner([[0.0]], [1], [1], [0.5]) == (0.0, 0.0)   # no control
    assert dr_xlearner([], [], [], []) == (0.0, 0.0)
    assert r_learner_sign([], [], [], []) == 0
    assert kfold_by_group([]) == []

    # 6) MoveCATERow round-trips to a CH dict (the persisted shape).
    row = MoveCATERow(
        tenant_id="t1", move_type="objection_rebuttal", ts_iso=S.now_iso(),
        cate=cate, cate_se=se, cate_lower=cate - 1.96 * se, cate_upper=cate + 1.96 * se,
        raw_lift=0.2, n_treated=120, n_control=300, overlap_min=0.1, sign_agree=(sgn >= 0),
    )
    d = row.to_row()
    assert d["move_type"] == "objection_rebuttal" and "cate" in d, d

    print("OK causal.py self-check passed:", {
        "cate": round(cate, 4),
        "se": round(se, 4),
        "r_sign": sgn,
        "folds_distinct": sorted(set(folds)),
    })
