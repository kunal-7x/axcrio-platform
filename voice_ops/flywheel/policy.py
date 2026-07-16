"""voice_ops.flywheel.policy — B6 CONTEXTUAL per-state rebuttal/move selector (LinTS).

WHY THIS EXISTS (and why it is the natural successor to bandit.py)
------------------------------------------------------------------
bandit.py learns ONE Beta belief per (knob, arm) — a *context-free* posterior. But the best
rebuttal to "too costly" depends on the STATE: a hot, low-friction lead who balks at price wants
a value reframe; a cold, high-friction, already-disengaging lead wants an empathy/handoff beat. A
single global "best price rebuttal" averages those away. We want the policy to condition the action
on the conversational state vector. That is a CONTEXTUAL bandit.

We use **Linear Thompson Sampling** (Agrawal & Goyal, ICML 2013, "Thompson Sampling for Contextual
Bandits with Linear Payoffs"). Each candidate play / rebuttal template `a` is an ARM that carries a
Bayesian linear-regression belief over the reward as a linear function of the state features `x`:

    reward_a ≈ θ_a · x ,    θ_a ~ N( A_a^{-1} b_a ,  v² A_a^{-1} )
    A_a = λ I + Σ x xᵀ      (ridge-regularised design / precision matrix)
    b_a = Σ r x             (reward-weighted feature sums)

At decision time we DRAW one θ̃_a ~ N(μ_a, v² A_a^{-1}) per arm and pick argmaxₐ θ̃_a · x. Sampling
(rather than taking the mean) is what makes it explore: an arm with little data has a fat posterior
and so sometimes draws high — Thompson exploration in feature space, with the same provable
regret/UX trade-off as the context-free sampler, no jarring forced randomness most of the time.

THE DEPLOYMENT STANCE (why a "policy" over a FROZEN LLM, not weights)
--------------------------------------------------------------------
Riya is a frozen hosted LLM we cannot fine-tune live. So this B6 "policy" is NOT a set of model
weights — it is a *queryable selector* over a per-tenant PLAY LIBRARY (schema.PlayTemplate rows):
the data-defined action space of rebuttal/move templates. The agent asks `select(state, model)` and
gets a template_id to splice in. The frozen LLM stays frozen; only the *choice of play* is learned.
A fine-tuned model may only ever ship as a separate self-hosted SHADOW challenger behind the gate
(see the discrete-BCQ/IQL stub at the bottom — lazy-torch, NEVER live).

HONEST OFF-POLICY EVALUATION (Swaminathan & Joachims CRM/POEM, 2015)
-------------------------------------------------------------------
`train_policy` rebuilds each arm's (A_a, b_a) sufficient statistics from LOGGED trajectories (the
Counterfactual Risk Minimisation log-bootstrap) and then scores the resulting policy with a 3-LEG
off-policy estimate — SNIPS (model-free, low-bias) + a simple FQE (a fitted-Q value model) + a
MAGIC-style blend of the two — and persists the PESSIMISTIC MINIMUM `ope_lower`. The challenger gate
consumes that lower bound, never the optimistic point estimate: an OPE leg can be wrong in our
favour, so we trust the worst of the three. This mirrors ope.snips' philosophy: OPE FILTERS, it
never vetoes, and a model with no logged support honestly reports a near-zero, inactive policy.

ANTI-GOODHART. Compliance is NEVER an arm here — it is a hard gate upstream (compliance.py). The
reward this policy maximises is the already-capped, already-compliance-screened fused reward off the
trajectory; the policy cannot "buy" bookings with pushiness because that reward was clipped first.

DESIGN LAWS HONOURED
--------------------
PURE-PYTHON math (a Gauss-Jordan matrix inverse; numpy is optional and only used opportunistically
inside the functions that benefit). SIDE-PIPELINE: `select`/`update_arm` are read off the policy
decision and the post-call update — never the live LiveKit turn loop; `train_policy` is worker-only.
DORMANT-SAFE + BEST-EFFORT: every public function swallows its own errors → logging.warning and
returns a clean empty/zero/inactive value, NEVER raising into a caller. `rng` is injectable for
deterministic tests. Imports and serves with zero ClickHouse / network / numpy.
"""
from __future__ import annotations

import json
import logging
import math
import random
from typing import Dict, List, Optional, Tuple

from . import schema as S
from .schema import OBJECTION_TYPES, LEAD_TEMPERATURES, PolicyModel, now_iso

logger = logging.getLogger("flywheel.policy")

# --------------------------------------------------------------------------- #
# Fixed default vocabularies for the one-hot blocks of the feature vector.
# Order is LOAD-BEARING: it pins the column layout so a PolicyModel trained today
# is read back identically tomorrow. OBJECTION_TYPES / LEAD_TEMPERATURES come from
# schema (the single source of truth); REGIMES mirrors the canonical affect-regime
# label set (voice_ops/research/schema.py: steady|warming|rising_friction|disengaging|
# resolving) — there is no flywheel.schema constant for it, so we pin it here.
# --------------------------------------------------------------------------- #
REGIMES: Tuple[str, ...] = (
    "steady", "warming", "rising_friction", "disengaging", "resolving",
)

# Monte-Carlo budget for the epsilon-mixed propensity estimate. Mirrors bandit._MC_SAMPLES
# (2000 joint draws → ~±1% std-error on a probability). Module-level so tests can shrink it.
_MC_SAMPLES: int = 2000

# Never log/return a propensity of exactly 0 — that nukes the OPE importance weight
# (un-invertible). Floor mirrors bandit._PROP_FLOOR.
_PROP_FLOOR: float = 1e-4

# LinTS posterior-scale (v²): the exploration temperature on the sampled θ̃. v=1 keeps it
# honest without over-exploring; kept module-level for tuning/tests.
_V_SCALE: float = 1.0

# Ridge regularisation for A_a = λI + Σ x xᵀ — keeps the precision matrix invertible even
# with one observation, and is the Bayesian-linear-regression prior precision.
_RIDGE: float = 1.0

# train_policy will not mark a policy active unless it has at least this much logged support
# AND at least 2 usable arms (a 1-arm "policy" is just the incumbent — nothing to select over).
_MIN_TRAIN_ROWS: int = 200
_MIN_ARMS: int = 2

# A tiny numerical floor used by the FQE leg and matrix inverse pivots.
_EPS: float = 1e-9


# =========================================================================== #
# featurize_state — the fixed-layout context vector x.
# =========================================================================== #
def featurize_state(
    state: dict,
    *,
    objection_types: Optional[List[str]] = None,
    regimes: Optional[List[str]] = None,
    temperatures: Optional[List[str]] = None,
) -> list:
    """Map a conversational state dict to the LinTS context vector x (fixed layout).

    LAYOUT (this order is the contract — it MUST match between train and serve):

        x = [ 1.0,                              # 0   intercept / bias term
              state_friction / 100.0,           # 1   continuous, ~[0,1]
              state_arousal  / 100.0,            # 2   continuous, ~[0,1]
              one_hot(regime)            ...,    # 3 .. 3+|R|-1
              one_hot(objection_type)    ...,    #     next |O| slots
              one_hot(lead_temperature)  ... ]   #     final |T| slots

    The intercept lets each arm learn a context-free baseline; the two continuous channels are the
    affect state (divided by 100 to land friction/arousal in ~[0,1] like the rest of the vector);
    the three one-hot blocks encode the categorical state. Default vocabularies come from the schema
    constants (single source of truth) so every caller produces the SAME column layout.

    `state` keys read (all optional, defaulted): state_friction|friction, state_arousal|arousal,
    state_regime|regime, objection_type, lead_temperature|temperature|temp. An unknown category
    contributes an all-zero block (no spurious column) rather than raising. Best-effort: any failure
    returns the intercept-only [1.0]-padded zero vector of the correct width, never an exception.
    """
    objs = list(objection_types) if objection_types else list(OBJECTION_TYPES)
    regs = list(regimes) if regimes else list(REGIMES)
    temps = list(temperatures) if temperatures else list(LEAD_TEMPERATURES)
    width = 3 + len(regs) + len(objs) + len(temps)
    try:
        st = state if isinstance(state, dict) else {}

        def _num(*keys, default=50.0) -> float:
            for k in keys:
                if k in st and st[k] is not None:
                    try:
                        v = float(st[k])
                        return default if v != v else v   # NaN guard
                    except Exception:  # noqa: BLE001
                        continue
            return default

        def _cat(*keys, default="") -> str:
            for k in keys:
                if k in st and st[k] is not None:
                    return str(st[k])
            return default

        friction = _num("state_friction", "friction", default=50.0)
        arousal = _num("state_arousal", "arousal", default=50.0)
        regime = _cat("state_regime", "regime", default="steady")
        objection = _cat("objection_type", "objection", default="none")
        temperature = _cat("lead_temperature", "temperature", "temp", default="unknown")

        x: List[float] = [1.0, friction / 100.0, arousal / 100.0]

        def _onehot(value: str, vocab: List[str]) -> List[float]:
            block = [0.0] * len(vocab)
            try:
                block[vocab.index(value)] = 1.0
            except ValueError:
                pass  # unknown category → all-zero block (no spurious signal)
            return block

        x.extend(_onehot(regime, regs))
        x.extend(_onehot(objection, objs))
        x.extend(_onehot(temperature, temps))
        # Defensive: guarantee the contracted width exactly.
        if len(x) != width:
            if len(x) < width:
                x.extend([0.0] * (width - len(x)))
            else:
                x = x[:width]
        return x
    except Exception as exc:  # noqa: BLE001
        logger.warning("flywheel.policy.featurize_state error: %r", exc)
        z = [0.0] * width
        if z:
            z[0] = 1.0
        return z


# =========================================================================== #
# mat_inv — pure-python Gauss-Jordan inverse of a small (d×d) matrix.
# =========================================================================== #
def mat_inv(A: list) -> list:
    """Invert a small square matrix A (list-of-lists) via Gauss-Jordan with partial pivoting.

    Pure-python — no numpy needed (the LinTS precision matrices here are small, d≈30). Partial
    pivoting (swap in the row with the largest pivot) keeps it numerically stable; a singular /
    near-singular matrix falls back to the pseudo-inverse-ish diagonal-ridge so a caller always
    gets a usable PSD-ish inverse instead of a crash. Best-effort: a malformed/non-square input
    returns a scaled identity of a best-guess size; NEVER raises.

    (numpy is used opportunistically if present AND the matrix is large enough to matter, but the
    pure-python path is always correct and is what the self-check exercises.)
    """
    try:
        n = len(A)
        if n == 0:
            return []
        # Validate squareness; coerce to float rows.
        M: List[List[float]] = []
        for row in A:
            if len(row) != n:
                raise ValueError("non-square matrix")
            M.append([float(v) for v in row])

        # Opportunistic numpy fast-path (correctness identical; only a speed/precision nicety).
        if n >= 24:
            try:
                import numpy as _np  # lazy, optional
                inv = _np.linalg.inv(_np.asarray(M, dtype=float))
                return inv.tolist()
            except Exception:  # noqa: BLE001 — fall through to pure-python below
                pass

        # Augment [M | I].
        aug: List[List[float]] = [M[i] + [1.0 if i == j else 0.0 for j in range(n)] for i in range(n)]

        for col in range(n):
            # Partial pivot: pick the row (>=col) with the largest |value| in this column.
            piv = col
            best = abs(aug[col][col])
            for r in range(col + 1, n):
                if abs(aug[r][col]) > best:
                    best, piv = abs(aug[r][col]), r
            if best < _EPS:
                # Singular column — nudge the pivot with a tiny ridge so we stay invertible.
                aug[col][col] += _RIDGE
                if abs(aug[col][col]) < _EPS:
                    raise ZeroDivisionError("singular matrix")
            if piv != col:
                aug[col], aug[piv] = aug[piv], aug[col]

            pivot = aug[col][col]
            inv_p = 1.0 / pivot
            for j in range(2 * n):
                aug[col][j] *= inv_p
            # Eliminate this column from every other row.
            for r in range(n):
                if r == col:
                    continue
                factor = aug[r][col]
                if factor == 0.0:
                    continue
                rowc = aug[col]
                rowr = aug[r]
                for j in range(2 * n):
                    rowr[j] -= factor * rowc[j]

        return [aug[i][n:] for i in range(n)]
    except Exception as exc:  # noqa: BLE001
        logger.warning("flywheel.policy.mat_inv error: %r", exc)
        # Best-effort fallback: a scaled identity so downstream LinTS draws still work.
        try:
            n = len(A)
        except Exception:  # noqa: BLE001
            n = 0
        return [[(1.0 / _RIDGE) if i == j else 0.0 for j in range(n)] for i in range(n)]


# --------------------------------------------------------------------------- #
# Small pure-python linear-algebra helpers (no numpy required).
# --------------------------------------------------------------------------- #
def _matvec(M: List[List[float]], v: List[float]) -> List[float]:
    """M (d×d) · v (d) → d."""
    return [math.fsum(M[i][j] * v[j] for j in range(len(v))) for i in range(len(M))]


def _dot(a: List[float], b: List[float]) -> float:
    return math.fsum(ai * bi for ai, bi in zip(a, b))


def _chol_lower(M: List[List[float]]) -> Optional[List[List[float]]]:
    """Cholesky L (lower-triangular) of an SPD matrix M, or None if not SPD.

    Used to draw a correlated Gaussian θ̃ = μ + v·L·z (z ~ N(0,I)) from the LinTS posterior whose
    covariance is v² A^{-1}. A_inv is SPD by construction (ridge + Σxxᵀ), so this normally succeeds;
    None signals the caller to degrade to the posterior mean (no exploration noise) rather than crash.
    """
    try:
        n = len(M)
        L = [[0.0] * n for _ in range(n)]
        for i in range(n):
            for j in range(i + 1):
                s = math.fsum(L[i][k] * L[j][k] for k in range(j))
                if i == j:
                    d = M[i][i] - s
                    if d <= 0.0:
                        return None
                    L[i][j] = math.sqrt(d)
                else:
                    if abs(L[j][j]) < _EPS:
                        return None
                    L[i][j] = (M[i][j] - s) / L[j][j]
        return L
    except Exception:  # noqa: BLE001
        return None


def _sample_theta(mu: List[float], A_inv: List[List[float]], v: float,
                  rng: random.Random) -> List[float]:
    """Draw θ̃ ~ N(mu, v² A_inv). Symmetrise A_inv, Cholesky it, θ̃ = mu + v·L·z.

    Degrades to the mean `mu` (deterministic, no exploration) if A_inv is not usefully SPD — a
    safe, honest fallback (the arm simply exploits its mean this turn)."""
    n = len(mu)
    # Symmetrise to kill tiny asymmetries from the inverse.
    sym = [[0.5 * (A_inv[i][j] + A_inv[j][i]) for j in range(n)] for i in range(n)]
    L = _chol_lower(sym)
    if L is None:
        return list(mu)
    z = [rng.gauss(0.0, 1.0) for _ in range(n)]
    noise = [v * math.fsum(L[i][k] * z[k] for k in range(i + 1)) for i in range(n)]
    return [mu[i] + noise[i] for i in range(n)]


# --------------------------------------------------------------------------- #
# Arm (de)serialisation — a parsed arms dict {template_id: {A_flat, b_vec, plays}}.
# --------------------------------------------------------------------------- #
def _unflatten(A_flat: List[float], d: int) -> List[List[float]]:
    return [[float(A_flat[i * d + j]) for j in range(d)] for i in range(d)]


def _flatten(A: List[List[float]]) -> List[float]:
    out: List[float] = []
    for row in A:
        out.extend(float(x) for x in row)
    return out


def _new_arm(d: int) -> dict:
    """A fresh arm with the ridge prior A = λI, b = 0, plays = 0."""
    A = [[(_RIDGE if i == j else 0.0) for j in range(d)] for i in range(d)]
    return {"A_flat": _flatten(A), "b_vec": [0.0] * d, "plays": 0}


def _arms_dict(model) -> Tuple[Dict[str, dict], int]:
    """Coerce `model` (a PolicyModel | parsed arms dict | json str) → (arms, d).

    Returns ({}, 0) when there is nothing usable. `d` is inferred from the first arm's b_vec."""
    arms: Dict[str, dict] = {}
    try:
        if model is None:
            return {}, 0
        # PolicyModel → parse its arms_json.
        if isinstance(model, PolicyModel):
            raw = model.arms_json or ""
            arms = json.loads(raw) if raw else {}
        elif isinstance(model, str):
            arms = json.loads(model) if model.strip() else {}
        elif isinstance(model, dict):
            # Could be the bare arms dict, or a row dict carrying arms_json.
            if "arms_json" in model and isinstance(model.get("arms_json"), str):
                raw = model.get("arms_json") or ""
                arms = json.loads(raw) if raw else {}
            else:
                arms = model
        else:
            return {}, 0
        if not isinstance(arms, dict) or not arms:
            return {}, 0
        # Infer d from the first arm that has a b_vec.
        d = 0
        for a in arms.values():
            if isinstance(a, dict) and a.get("b_vec"):
                d = len(a["b_vec"])
                break
        return arms, d
    except Exception as exc:  # noqa: BLE001
        logger.warning("flywheel.policy._arms_dict parse error: %r", exc)
        return {}, 0


# =========================================================================== #
# select — per-arm LinTS draw + an epsilon-mixed Monte-Carlo propensity.
# =========================================================================== #
def select(
    state: dict,
    model,
    *,
    epsilon: float = 0.08,
    rng: Optional[random.Random] = None,
) -> tuple:
    """Pick a play TEMPLATE for `state` under per-arm LinTS, return (template_id, propensity).

    Mechanism (mirrors bandit.select_arm's epsilon-floored, OPE-honest design):
      * With probability `epsilon` (the forced-exploration floor) pick a UNIFORM-random template —
        guaranteeing every arm keeps positive selection probability (the positivity assumption the
        OPE importance weights in train_policy / ope.py depend on).
      * Otherwise LinTS: for each arm draw θ̃_a ~ N(A_a^{-1} b_a, v² A_a^{-1}) and pick argmaxₐ θ̃_a·x.

    `propensity` is the TRUE probability THIS exact rule would have selected the returned template:
    (1 - eps)·p_lints + eps/n, where p_lints is estimated by a quick Monte-Carlo of joint LinTS
    draws (count of times the chosen arm is the argmax). Floored above 0 so a logged turn never
    carries an un-invertible weight. Reuses the 2000-draw approach of bandit.select_arm.

    `model` may be a schema.PolicyModel or a parsed arms dict {template_id: {A_flat, b_vec, plays}}.
    Empty / no usable arms → ('', 1.0). `rng` is injectable for deterministic tests.

    Best-effort: any internal failure degrades to a uniform pick with propensity 1/n (or ('',1.0)).
    NEVER raises — it is read off the policy decision but stays robust regardless.
    """
    try:
        arms, d = _arms_dict(model)
        ids = [k for k, a in arms.items() if isinstance(a, dict) and a.get("b_vec")]
        n = len(ids)
        if n == 0 or d == 0:
            return ("", 1.0)

        x = featurize_state(state)
        # Reconcile feature width with the trained dimension (defend cross-version drift).
        if len(x) != d:
            if len(x) < d:
                x = x + [0.0] * (d - len(x))
            else:
                x = x[:d]

        r = rng or random
        eps = epsilon
        if eps != eps or eps < 0.0:  # NaN / negative guard
            eps = 0.0
        eps = min(1.0, eps)

        if n == 1:
            return (ids[0], 1.0)

        # Pre-compute each arm's posterior (mean μ_a = A_a^{-1} b_a, cov A_a^{-1}).
        posteriors: List[Tuple[List[float], List[List[float]]]] = []
        for aid in ids:
            a = arms[aid]
            try:
                A = _unflatten(list(a["A_flat"]), d)
                b = [float(v) for v in a["b_vec"]]
            except Exception:  # noqa: BLE001
                A = [[(_RIDGE if i == j else 0.0) for j in range(d)] for i in range(d)]
                b = [0.0] * d
            A_inv = mat_inv(A)
            mu = _matvec(A_inv, b)
            posteriors.append((mu, A_inv))

        def _argmax_draw() -> int:
            best_i, best_v = 0, -float("inf")
            for i, (mu, A_inv) in enumerate(posteriors):
                theta = _sample_theta(mu, A_inv, math.sqrt(_V_SCALE), r)
                score = _dot(theta, x)
                if score > best_v:
                    best_i, best_v = i, score
            return best_i

        # --- choose the arm --------------------------------------------------- #
        if r.random() < eps:
            idx = r.randrange(n)              # uniform forced-exploration draw
        else:
            idx = _argmax_draw()              # LinTS exploit/explore draw

        # --- estimate p_lints for the CHOSEN arm via joint Monte-Carlo -------- #
        wins = 0
        n_mc = max(1, _MC_SAMPLES)
        for _ in range(n_mc):
            if _argmax_draw() == idx:
                wins += 1
        p_lints = wins / float(n_mc)

        propensity = (1.0 - eps) * p_lints + eps / float(n)
        propensity = min(1.0, max(_PROP_FLOOR, propensity))
        return (ids[idx], propensity)
    except Exception as exc:  # noqa: BLE001
        logger.warning("flywheel.policy.select error: %r", exc)
        try:
            arms, _d = _arms_dict(model)
            ids = [k for k, a in arms.items() if isinstance(a, dict)]
            if not ids:
                return ("", 1.0)
            return (ids[0], 1.0 / float(len(ids)))
        except Exception:  # noqa: BLE001
            return ("", 1.0)


# =========================================================================== #
# update_arm — one LinTS sufficient-statistic update (A_a += xxᵀ; b_a += r·x).
# =========================================================================== #
def update_arm(arms: dict, arm_id: str, x: list, reward: float) -> dict:
    """Fold one (x, reward) observation into arm `arm_id`'s Bayesian-linear-regression stats.

    Updates (the closed-form sufficient-statistics update):
        A_a  +=  x xᵀ          (rank-1 precision bump)
        b_a  +=  reward · x     (reward-weighted feature accumulation)
        plays += 1

    Mutates AND returns `arms` for convenience (consistent with the worker's accumulate loop). A
    missing arm is created at the ridge prior A = λI, b = 0 with `d = len(x)`. A dimension mismatch
    on an existing arm is reconciled (pad/trim x) so a vocabulary bump never crashes the update.
    Best-effort: any failure returns `arms` unchanged → logging.warning. NEVER raises.
    """
    try:
        if not isinstance(arms, dict):
            arms = {}
        xs = [float(v) for v in (x or [])]
        d = len(xs)
        if d == 0:
            return arms
        try:
            rwd = float(reward)
            if rwd != rwd:  # NaN guard
                rwd = 0.0
        except Exception:  # noqa: BLE001
            rwd = 0.0

        arm = arms.get(arm_id)
        if not isinstance(arm, dict) or not arm.get("b_vec"):
            arm = _new_arm(d)
        # Reconcile dimension if an existing arm was trained at a different width.
        cur_d = len(arm.get("b_vec") or [])
        if cur_d != d:
            if cur_d == 0:
                arm = _new_arm(d)
            elif len(xs) < cur_d:
                xs = xs + [0.0] * (cur_d - len(xs))
                d = cur_d
            else:
                xs = xs[:cur_d]
                d = cur_d

        A = _unflatten(list(arm["A_flat"]), d)
        b = [float(v) for v in arm["b_vec"]]

        # A += x xᵀ  (rank-1 outer product) ; b += r·x
        for i in range(d):
            xi = xs[i]
            if xi != 0.0:
                Ai = A[i]
                for j in range(d):
                    Ai[j] += xi * xs[j]
            b[i] += rwd * xi

        arm["A_flat"] = _flatten(A)
        arm["b_vec"] = b
        arm["plays"] = int(arm.get("plays", 0) or 0) + 1
        arms[arm_id] = arm
        return arms
    except Exception as exc:  # noqa: BLE001
        logger.warning("flywheel.policy.update_arm error: %r", exc)
        return arms if isinstance(arms, dict) else {}


# --------------------------------------------------------------------------- #
# The 3-leg OPE for train_policy (SNIPS + a simple FQE + a MAGIC-style blend).
# --------------------------------------------------------------------------- #
def _greedy_target_propensity(arms: Dict[str, dict], x: List[float], d: int,
                              ids: List[str]) -> Dict[str, float]:
    """Deterministic (mean-greedy) target action for state x → a {arm_id: prob} one-hot.

    For OPE we evaluate the LEARNED policy's *greedy* action (argmaxₐ μ_a·x, μ_a = A_a^{-1} b_a) on
    each logged state. A one-hot target keeps the SNIPS leg transparent and assumption-light."""
    best_id, best_v = ids[0], -float("inf")
    for aid in ids:
        a = arms[aid]
        try:
            A = _unflatten(list(a["A_flat"]), d)
            b = [float(v) for v in a["b_vec"]]
        except Exception:  # noqa: BLE001
            continue
        mu = _matvec(mat_inv(A), b)
        score = _dot(mu, x[:d] if len(x) >= d else x + [0.0] * (d - len(x)))
        if score > best_v:
            best_id, best_v = aid, score
    return {best_id: 1.0}


def _fqe_value(arms: Dict[str, dict], rows: List[dict], d: int, ids: List[str]) -> float:
    """A SIMPLE one-step Fitted-Q Evaluation leg: the model-based value of the greedy policy.

    Honest, transparent FQE for a CONTEXTUAL bandit (horizon-1, so no bootstrapping needed): each
    arm's fitted Q̂_a(x) = μ_a·x is the ridge-regression reward model we already maintain in (A_a,
    b_a). The greedy policy's value is then the average over logged states of Q̂ at the greedy arm:

        V_FQE = mean_i  max_a μ_a · x_i

    This is the model-BASED leg (it can extrapolate where SNIPS has no support — its strength) and
    so it carries the model's bias (its weakness). That bias is exactly why we blend it with SNIPS
    (MAGIC) and then take the pessimistic MIN. Clamped to a sane reward range. Best-effort → 0.0.
    """
    try:
        if not rows or not ids:
            return 0.0
        # Pre-compute each arm's μ once.
        mus: Dict[str, List[float]] = {}
        for aid in ids:
            a = arms[aid]
            try:
                A = _unflatten(list(a["A_flat"]), d)
                b = [float(v) for v in a["b_vec"]]
                mus[aid] = _matvec(mat_inv(A), b)
            except Exception:  # noqa: BLE001
                continue
        if not mus:
            return 0.0
        total = 0.0
        cnt = 0
        for row in rows:
            x = row.get("_x")
            if not x:
                continue
            xv = x[:d] if len(x) >= d else x + [0.0] * (d - len(x))
            best = max((_dot(mu, xv) for mu in mus.values()), default=0.0)
            total += best
            cnt += 1
        if cnt == 0:
            return 0.0
        v = total / float(cnt)
        # Clamp to a sane fused-reward band so a degenerate μ can't explode the estimate.
        return max(-2.0, min(2.0, v))
    except Exception as exc:  # noqa: BLE001
        logger.warning("flywheel.policy._fqe_value error: %r", exc)
        return 0.0


def _three_leg_ope(arms: Dict[str, dict], rows: List[dict], d: int,
                   ids: List[str]) -> Tuple[float, float, float, float]:
    """Run all three OPE legs and return (snips, fqe, magic, lower=pessimistic MIN).

    LEG 1 SNIPS (model-free, low bias, needs logging support) — via ope.snips.
    LEG 2 FQE (model-based, extrapolates, carries model bias) — via _fqe_value.
    LEG 3 MAGIC-style blend: a convex combination ω·SNIPS + (1-ω)·FQE with ω driven by SNIPS'
          effective coverage (more IS support → trust the model-free leg more). This is the spirit
          of Thomas & Brunskill's MAGIC (2016): blend the IS and model-based estimators to minimise
          MSE rather than picking one. We approximate the optimal weight cheaply from coverage.

    ope_lower = MIN(snips, fqe, magic) — the PESSIMISTIC bound the challenger gate consumes. We
    trust the worst leg because an OPE estimator that is wrong in our favour would wave a bad policy
    through; the min is the anti-Goodhart, honest-science choice. Best-effort → all-zeros.
    """
    try:
        from . import ope as _ope  # lazy sibling import (pure-python, no deps)

        # Build the SNIPS row format: {arm_id (logged action), propensity (behaviour>0), reward}.
        # arm_id is the LOGGED play_template_id; the target propensity is the greedy one-hot.
        logged: List[dict] = []
        for row in rows:
            logged.append({
                "arm_id": row.get("play_template_id"),
                "propensity": row.get("propensity"),
                "reward": row.get("reward"),
            })

        # Target propensity = average greedy one-hot over the logged states (the policy's action
        # distribution under the logged context mix). SNIPS reweights logged rows toward it.
        tgt_counts: Dict[str, float] = {}
        n_states = 0
        for row in rows:
            x = row.get("_x")
            if not x:
                continue
            oneh = _greedy_target_propensity(arms, x, d, ids)
            for k, v in oneh.items():
                tgt_counts[k] = tgt_counts.get(k, 0.0) + v
            n_states += 1
        target_prop = ({k: v / float(n_states) for k, v in tgt_counts.items()}
                       if n_states else {})

        snips_v, snips_ci = _ope.snips(logged, target_prop)
        fqe_v = _fqe_value(arms, rows, d, ids)

        # MAGIC blend weight ω from SNIPS coverage: a tight CI (good IS support) → trust SNIPS more.
        # ω = 1/(1+ci) maps ci→0 to ω→1 (all SNIPS) and a wide ci to ω→0 (lean on the model).
        omega = 1.0 / (1.0 + max(0.0, float(snips_ci)))
        omega = max(0.0, min(1.0, omega))
        magic_v = omega * snips_v + (1.0 - omega) * fqe_v

        lower = min(snips_v, fqe_v, magic_v)
        return (round(snips_v, 6), round(fqe_v, 6), round(magic_v, 6), round(lower, 6))
    except Exception as exc:  # noqa: BLE001
        logger.warning("flywheel.policy._three_leg_ope error: %r", exc)
        return (0.0, 0.0, 0.0, 0.0)


# =========================================================================== #
# train_policy — CRM log-bootstrap of the per-arm LinTS stats + 3-leg OPE.
# =========================================================================== #
async def train_policy(tenant_id: str, campaign_id: str = "", *, cfg=None):
    """Rebuild a contextual LinTS PolicyModel from logged trajectories and 3-leg-OPE-score it.

    PIPELINE (offline / worker-only; never the live turn loop):
      1. DORMANCY GATE. If `cfg.policy_active()` is False (flag off / no ClickHouse), return an
         INACTIVE PolicyModel immediately — no reads, no writes. The selector still serves dormant.
      2. CRM LOG-BOOTSTRAP. Read logged turns that actually used a play (play_template_id != '')
         carrying (state_feature_json OR the raw state, play_template_id, reward, propensity). For
         each, reconstruct x (prefer the stored state_feature_json so OPE reconstructs the EXACT
         vector — that is why trajectory.py persists it) and fold it into the chosen arm's (A_a, b_a)
         via update_arm. This is the Counterfactual-Risk-Minimisation log-bootstrap (Swaminathan &
         Joachims): we rebuild the policy's belief from the logged interaction record.
      3. 3-LEG OPE. Score the resulting greedy policy with SNIPS + FQE + a MAGIC blend; persist the
         pessimistic MIN as ope_lower (the gate's input).
      4. PERSIST. Build a schema.PolicyModel and write it via _st.insert_policy_model (a no-op when
         dormant). Mark `active` only with enough logged support AND ≥2 arms.

    Returns the PolicyModel (active or inactive). NEVER raises — any failure → an inactive model.
    """
    cfg = cfg or _load_cfg()
    knob = "rebuttal"
    try:
        if cfg is None or not cfg.policy_active():
            return PolicyModel(tenant_id=tenant_id, campaign_id=campaign_id,
                               vertical="real_estate", ts_iso=now_iso(), knob=knob, active=False)

        from . import store as _st  # lazy — keeps the module importable with no store configured

        # --- read logged play-turns ------------------------------------------ #
        where = ("tenant_id = {tid:String} AND play_template_id != '' "
                 "AND reward_capped != 0")
        params: Dict[str, object] = {"tid": tenant_id}
        if campaign_id:
            where += " AND campaign_id = {cid:String}"
            params["cid"] = campaign_id
        sql = (
            "SELECT play_template_id, state_feature_json, "
            "state_friction, state_arousal, state_regime, objection_type, lead_temperature, "
            "propensity, reward_capped, vertical "
            f"FROM {_st._final(_st.TRAJECTORIES)} WHERE {where} "
            "ORDER BY ts DESC LIMIT 100000"
        )
        res = await _st._ch(sql, params)
        rows_raw = res.get("rows") or []

        vertical = "real_estate"
        # --- build the per-arm stats + the OPE row buffer -------------------- #
        arms: Dict[str, dict] = {}
        ope_rows: List[dict] = []
        d = 0
        for r in rows_raw:
            try:
                tpl = str(r.get("play_template_id") or "")
                if not tpl:
                    continue
                if r.get("vertical"):
                    vertical = str(r.get("vertical"))
                # Prefer the EXACT stored feature vector (so train ≡ serve ≡ OPE). Fall back to
                # re-featurizing the raw state if the json is absent/malformed.
                x = _parse_feature_json(r.get("state_feature_json"))
                if not x:
                    x = featurize_state({
                        "state_friction": r.get("state_friction"),
                        "state_arousal": r.get("state_arousal"),
                        "state_regime": r.get("state_regime"),
                        "objection_type": r.get("objection_type"),
                        "lead_temperature": r.get("lead_temperature"),
                    })
                if not x:
                    continue
                d = max(d, len(x))
                try:
                    reward = float(r.get("reward_capped") or 0.0)
                except Exception:  # noqa: BLE001
                    reward = 0.0
                try:
                    prop = float(r.get("propensity") or 0.0)
                except Exception:  # noqa: BLE001
                    prop = 0.0
                update_arm(arms, tpl, x, reward)
                ope_rows.append({
                    "_x": x,
                    "play_template_id": tpl,
                    "propensity": prop,
                    "reward": reward,
                })
            except Exception as exc:  # noqa: BLE001 — one bad row must not sink the train
                logger.warning("flywheel.policy.train_policy bad row skipped: %r", exc)
                continue

        ids = [k for k, a in arms.items() if isinstance(a, dict) and a.get("b_vec")]
        n_rows = len(ope_rows)

        # --- 3-leg OPE ------------------------------------------------------- #
        if ids and d > 0:
            snips_v, fqe_v, magic_v, lower = _three_leg_ope(arms, ope_rows, d, ids)
        else:
            snips_v = fqe_v = magic_v = lower = 0.0

        active = bool(len(ids) >= _MIN_ARMS and n_rows >= _MIN_TRAIN_ROWS)

        model = PolicyModel(
            tenant_id=tenant_id,
            campaign_id=campaign_id,
            vertical=vertical,
            ts_iso=now_iso(),
            knob=knob,
            n_features=int(d),
            arms_json=json.dumps(arms, ensure_ascii=False),
            ope_snips=snips_v,
            ope_fqe=fqe_v,
            ope_magic=magic_v,
            ope_lower=lower,
            active=active,
        )
        try:
            _st.insert_policy_model([model])
        except Exception as exc:  # noqa: BLE001 — persistence is best-effort
            logger.warning("flywheel.policy.train_policy persist failed: %r", exc)
        return model
    except Exception as exc:  # noqa: BLE001
        logger.warning("flywheel.policy.train_policy error: %r", exc)
        return PolicyModel(tenant_id=tenant_id, campaign_id=campaign_id,
                           vertical="real_estate", ts_iso=now_iso(), knob=knob, active=False)


def _parse_feature_json(raw) -> List[float]:
    """Parse a persisted state_feature_json into a float list, or [] if absent/malformed."""
    try:
        if not raw:
            return []
        v = json.loads(raw) if isinstance(raw, str) else raw
        if isinstance(v, dict):
            # Allow {"x":[...]} envelopes as well as a bare list.
            v = v.get("x") or v.get("features") or []
        if isinstance(v, list) and v:
            return [float(z) for z in v]
        return []
    except Exception:  # noqa: BLE001
        return []


def _load_cfg():
    """Lazy config load — kept out of import time and best-effort."""
    try:
        from . import config as _cfg
        return _cfg.load()
    except Exception as exc:  # noqa: BLE001
        logger.warning("flywheel.policy._load_cfg error: %r", exc)
        return None


# =========================================================================== #
# SHADOW STUB — discrete-BCQ / IQL multi-turn variant (lazy-torch, NEVER live).
# =========================================================================== #
def train_offline_rl_shadow(*args, **kwargs):
    """SHADOW-ONLY discrete-BCQ / IQL offline-RL policy over the MULTI-TURN trajectory.

    NOT WIRED. NOT LIVE. This is the clearly-marked placeholder for the offline-RL upgrade to the
    horizon-1 contextual bandit above: a discrete Batch-Constrained Q-learning (Fujimoto et al.,
    2019) or Implicit Q-Learning (Kostrikov et al., 2021) value policy trained on the full logged
    multi-turn MDP (state → move → next-state → reward), which can credit a sequence of moves rather
    than a single turn. Like any fine-tuned artefact against the FROZEN Riya, such a policy may ONLY
    ever ship as a SEPARATE self-hosted SHADOW challenger behind the gate — it must NEVER touch the
    live turn loop. torch is imported LAZILY here so the module stays dep-free and importable; when
    torch is absent (the normal case) this returns a clean inactive marker rather than raising.
    """
    try:
        import torch  # noqa: F401  (lazy, optional, shadow-only — never reached in prod)
        # Intentionally unimplemented: the real BCQ/IQL trainer would live behind here, write a
        # Challenger(is_shadow=True, adapter_uri=...) and NEVER mutate the live PolicyModel.
        raise NotImplementedError(
            "offline-RL shadow trainer is a placeholder; ship only as a gated shadow challenger")
    except ImportError:
        logger.info("flywheel.policy.train_offline_rl_shadow: torch absent — shadow stub inactive")
        return {"active": False, "is_shadow": True, "reason": "torch_absent"}
    except Exception as exc:  # noqa: BLE001
        logger.warning("flywheel.policy.train_offline_rl_shadow inactive: %r", exc)
        return {"active": False, "is_shadow": True, "reason": "not_implemented"}


__all__ = [
    "featurize_state",
    "mat_inv",
    "select",
    "update_arm",
    "train_policy",
    "train_offline_rl_shadow",
    "REGIMES",
]


# =========================================================================== #
# Inline self-check (no network / no ClickHouse / no numpy) — pure-python path.
# =========================================================================== #
if __name__ == "__main__":  # pragma: no cover
    import sys

    rng = random.Random(13)  # deterministic for a repeatable smoke test

    # 1. featurize_state: fixed layout, correct width, intercept + scaled continuous + one-hots.
    width = 3 + len(REGIMES) + len(OBJECTION_TYPES) + len(LEAD_TEMPERATURES)
    x = featurize_state({
        "state_friction": 80.0, "state_arousal": 40.0,
        "state_regime": "rising_friction", "objection_type": "price",
        "lead_temperature": "hot",
    })
    assert len(x) == width, (len(x), width)
    assert x[0] == 1.0                                   # intercept
    assert abs(x[1] - 0.8) < 1e-9 and abs(x[2] - 0.4) < 1e-9
    assert sum(x[3:3 + len(REGIMES)]) == 1.0             # exactly one regime hot
    # unknown category → all-zero block, still correct width, never raises
    xu = featurize_state({"objection_type": "??unknown??", "state_regime": "??"})
    assert len(xu) == width
    # garbage input → intercept-padded zero vector
    xg = featurize_state(None)  # type: ignore[arg-type]
    assert len(xg) == width and xg[0] == 1.0
    print(f"[1] featurize_state width={len(x)} (regimes={len(REGIMES)}, "
          f"objections={len(OBJECTION_TYPES)}, temps={len(LEAD_TEMPERATURES)})")

    # 2. mat_inv: A @ A^{-1} ≈ I on a small SPD matrix; singular falls back gracefully.
    A = [[4.0, 1.0, 0.0], [1.0, 3.0, 1.0], [0.0, 1.0, 2.0]]
    Ainv = mat_inv(A)
    prod = _matvec  # reuse helper for a quick identity check
    ident_ok = True
    for i in range(3):
        for j in range(3):
            v = math.fsum(A[i][k] * Ainv[k][j] for k in range(3))
            if abs(v - (1.0 if i == j else 0.0)) > 1e-6:
                ident_ok = False
    assert ident_ok, "mat_inv failed the A·A^{-1}=I identity"
    assert mat_inv([]) == []
    _ = mat_inv([[0.0, 0.0], [0.0, 0.0]])               # singular → ridge fallback, no raise
    print("[2] mat_inv: A·A^{-1} = I verified (pure-python Gauss-Jordan)")

    # 3. update_arm: builds an arm at the ridge prior, bumps plays, accumulates A and b.
    d = width
    arms: dict = {}
    # Synthesize two clearly-different arms over 600 logged turns:
    #   tpl_value wins on HOT/price; tpl_empathy wins on COLD/disengaging.
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
    assert arms["tpl_value"]["plays"] == 600
    assert len(arms["tpl_value"]["b_vec"]) == d
    assert len(arms["tpl_value"]["A_flat"]) == d * d
    print(f"[3] update_arm: 2 arms, plays={arms['tpl_value']['plays']}, d={d}")

    # 4. select: real template id + a positive, <=1 propensity; LinTS prefers the right arm.
    _MC_SAMPLES = 200  # shrink the MC budget for a fast self-check
    tid, prop = select(
        {"state_friction": 30.0, "state_arousal": 60.0, "state_regime": "warming",
         "objection_type": "price", "lead_temperature": "hot"},
        arms, epsilon=0.08, rng=rng)
    assert tid in {"tpl_value", "tpl_empathy"}, tid
    assert 0.0 < prop <= 1.0, prop
    # Over many no-explore draws the hot/price state should favour tpl_value.
    wins = 0
    for _ in range(60):
        t, _p = select({"state_friction": 30.0, "state_arousal": 60.0, "state_regime": "warming",
                        "objection_type": "price", "lead_temperature": "hot"},
                       arms, epsilon=0.0, rng=rng)
        wins += (t == "tpl_value")
    assert wins >= 40, f"LinTS should favour tpl_value on hot/price (got {wins}/60)"
    # empty / single-arm contracts
    assert select({}, {}) == ("", 1.0)
    assert select({}, None) == ("", 1.0)
    one = {"only": arms["tpl_value"]}
    assert select({}, one)[0] == "only" and select({}, one)[1] == 1.0
    print(f"[4] select -> tpl={tid!r} propensity={prop:.4f}; tpl_value won {wins}/60 on hot/price")

    # 5. PolicyModel round-trip through select (model = a PolicyModel carrying arms_json).
    pm = PolicyModel(tenant_id="t1", campaign_id="c1", knob="rebuttal", n_features=d,
                     arms_json=json.dumps(arms), active=True)
    tid2, prop2 = select({"state_friction": 85.0, "state_arousal": 30.0,
                          "state_regime": "disengaging", "objection_type": "not_interested",
                          "lead_temperature": "cold"}, pm, epsilon=0.0, rng=rng)
    assert tid2 in {"tpl_value", "tpl_empathy"}
    assert 0.0 < prop2 <= 1.0
    row = pm.to_row()
    assert row["knob"] == "rebuttal" and row["n_features"] == d
    print(f"[5] PolicyModel-driven select -> tpl={tid2!r} propensity={prop2:.4f}")

    # 6. 3-leg OPE: build synthetic logged rows and confirm legs + pessimistic MIN are sane.
    ids = ["tpl_value", "tpl_empathy"]
    ope_rows = []
    for _ in range(120):
        xs = featurize_state({"state_friction": 30.0, "state_arousal": 60.0,
                              "state_regime": "warming", "objection_type": "price",
                              "lead_temperature": "hot"})
        ope_rows.append({"_x": xs, "play_template_id": "tpl_value", "propensity": 0.6,
                         "reward": 1.0})
        ope_rows.append({"_x": xs, "play_template_id": "tpl_empathy", "propensity": 0.4,
                         "reward": 0.0})
    snips_v, fqe_v, magic_v, lower = _three_leg_ope(arms, ope_rows, d, ids)
    assert lower == min(snips_v, fqe_v, magic_v), (snips_v, fqe_v, magic_v, lower)
    assert -2.0 <= lower <= 2.0
    print(f"[6] 3-leg OPE: snips={snips_v:.3f} fqe={fqe_v:.3f} magic={magic_v:.3f} "
          f"lower(min)={lower:.3f}")

    # 7. shadow stub: inactive marker when torch is absent (the normal path); never live.
    sh = train_offline_rl_shadow()
    assert sh["active"] is False and sh["is_shadow"] is True
    print(f"[7] shadow RL stub -> {sh}")

    # 8. train_policy is dormant-safe with no ClickHouse: returns an INACTIVE PolicyModel, no raise.
    import asyncio

    class _DormantCfg:
        def policy_active(self) -> bool:
            return False
    pm_dormant = asyncio.run(train_policy("t1", "c1", cfg=_DormantCfg()))
    assert isinstance(pm_dormant, PolicyModel) and pm_dormant.active is False
    print(f"[8] train_policy (dormant) -> active={pm_dormant.active}")

    print("OK: flywheel.policy self-check passed")
    sys.exit(0)
