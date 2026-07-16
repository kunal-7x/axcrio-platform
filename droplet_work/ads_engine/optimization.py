"""ads_engine.optimization — the PROPOSE-ONLY optimization brain (W3).

This module PROPOSES; it NEVER executes or spends. Every public entrypoint returns
proposed `Move` dicts (and persisted *state*); turning a move into a platform mutation
is the job of `guardrails.evaluate(...)` -> connector. Nothing here calls a connector,
opens a socket, or touches the live earner.

Two cores (research/optimization-algos.md §1, §2, §5):

  1. TTTS bandit over creative variants — Beta(alpha,beta) posteriors, top-two sampling,
     best-arm-confidence gate. Reward = blended decaying-`w`:
         reward = w * pCVR_calibrated + (1-w) * delay_corrected_conv
     where the proxy term (clicks/LP-views/WA-started) gives dense early signal and the
     conversion term is reconciled to CRM-truth + delay-corrected. `w` decays toward a
     floor as true conversions accumulate (start proxy-heavy, end truth-heavy).

  2. Cross-channel allocator — per-channel GP-UCB response curve (sklearn GP if present,
     else a pure-numpy isotonic-ish fallback) + multi-choice knapsack DP to split a total
     budget under min/max bounds. Change-point (MAE>tau) resets a poisoned curve.

REDTEAM folded in:
  * M1 (anomaly cold-start) -> `_warmed_up`: require min-n samples + a std floor before
    trusting an estimate (here, before a kill/scale is even *proposed*).
  * M3 (reconciliation_factor) -> `_clamp_reconciliation`: clamp to a sane band + floor
    the platform-reported denominator (no div-by-tiny amplification of a false winner).
  * C5 (only-decreasing auto-applies) -> moves carry `spend_delta_sign`; guardrails uses
    it to force draft/approve on any non-decreasing move. Optimization only *labels*.

Deterministic + offline-testable: the RNG is injectable (`rng=` / numpy Generator) so
tests seed it; all math is pure-numpy (no network, no sklearn hard-dep).
"""

from __future__ import annotations

import math
from typing import Any, Callable, Optional

import numpy as np

# ---------------------------------------------------------------------------
# Tunables (kept here, overridable via the state rows / config in the caller).
# ---------------------------------------------------------------------------
DEFAULT_TTTS_BETA = 0.5          # P(stay on top arm) vs challenger
DEFAULT_W0 = 0.85                # initial proxy weight in the blended reward
DEFAULT_W_FLOOR = 0.05
DEFAULT_W_DECAY_PER_CONV = 0.02  # w := max(floor, w0 - decay * true_conv_count)
DEFAULT_CONF_GATE = 0.70         # P(best > 2nd-best) required to propose kill/scale
DEFAULT_CONF_SAMPLES = 4000      # posterior samples for the confidence estimate

# Anomaly / cold-start warm-up (REDTEAM M1).
WARMUP_MIN_SAMPLES = 30          # min impressions/observations before trusting an arm
WARMUP_STD_FLOOR = 1e-3          # posterior std must exceed this (degenerate-posterior guard)

# Reconciliation clamp band (REDTEAM M3).
RECON_FACTOR_MIN = 0.1
RECON_FACTOR_MAX = 2.0
RECON_DENOM_FLOOR = 1.0          # floor platform-reported conversions before dividing

# Allocator (GP-UCB + knapsack).
DEFAULT_UCB_BETA = 1.0           # exploration weight
DEFAULT_CHANGEPOINT_MAE = 0.35   # normalized MAE threshold to trip a reset


def _rng(rng: Any = None) -> "np.random.Generator":
    """Resolve a numpy Generator. Pass an int seed, a Generator, or None (fresh)."""
    if isinstance(rng, np.random.Generator):
        return rng
    if isinstance(rng, (int, np.integer)):
        return np.random.default_rng(int(rng))
    return np.random.default_rng()


# ===========================================================================
# REDTEAM M3 — reconciliation factor clamp + denominator floor.
# ===========================================================================
def clamp_reconciliation(platform_reported: float, crm_true: float,
                         lo: float = RECON_FACTOR_MIN, hi: float = RECON_FACTOR_MAX) -> float:
    """reconciliation_factor = crm_true / max(platform_reported, FLOOR), clamped to [lo,hi].

    Without the floor a near-zero platform_reported would explode the factor and let a
    bad feedback value manufacture a false winner (REDTEAM M3). Without the clamp a
    >1 factor (platform under-reporting OR a feedback bug) over-inflates a creative.
    """
    denom = max(float(platform_reported or 0.0), RECON_DENOM_FLOOR)
    factor = float(crm_true or 0.0) / denom
    if not math.isfinite(factor):
        factor = 1.0
    return float(min(hi, max(lo, factor)))


# ===========================================================================
# Blended reward + delay correction (research §5A/§5B).
# ===========================================================================
def delay_correction(observed_conv: float, expected_observed_fraction: float) -> float:
    """Unbiased eventual-conversion estimate = observed / fraction-observed-so-far.

    `expected_observed_fraction` = CDF of the conversion-delay distribution at the
    elapsed time (in [0,1]); floored so a creative isn't punished for in-flight
    conversions and we never divide by ~0 (research §5B)."""
    frac = max(float(expected_observed_fraction or 0.0), 1e-3)
    return float(observed_conv or 0.0) / frac


def decay_w(w0: float, decay_per_conv: float, true_conv_count: float, w_floor: float) -> float:
    """w := max(w_floor, w0 - decay * true_conv_count). Proxy-heavy -> truth-heavy."""
    return float(max(w_floor, w0 - decay_per_conv * float(true_conv_count or 0.0)))


def blended_reward(pcvr_calibrated: float, delay_corrected_conv: float, w: float) -> float:
    """reward = w*pCVR + (1-w)*delay_corrected_conv, clamped to [0,1] (Beta domain)."""
    r = w * float(pcvr_calibrated or 0.0) + (1.0 - w) * float(delay_corrected_conv or 0.0)
    return float(min(1.0, max(0.0, r)))


# ===========================================================================
# TTTS bandit over creative variants.
# ===========================================================================
def new_bandit_state(campaign_id: str, tenant_id: str, provider: str = "meta",
                     objective_event: str = "lead") -> dict:
    """A fresh BanditState row (no arms yet)."""
    return {
        "campaign_id": campaign_id,
        "tenant_id": tenant_id,
        "provider": provider,
        "objective_event": objective_event,
        "ttts_beta": DEFAULT_TTTS_BETA,
        "w": DEFAULT_W0,
        "w0": DEFAULT_W0,
        "w_floor": DEFAULT_W_FLOOR,
        "w_decay_per_conv": DEFAULT_W_DECAY_PER_CONV,
        "arms": {},
        "best_arm_id": None,
        "best_arm_confidence": 0.0,
        "reconciliation_factor": 1.0,
        "version": 0,
    }


def _new_arm(variant_id: str) -> dict:
    return {
        "variant_id": variant_id,
        "alpha": 1.0, "beta": 1.0,        # Beta(1,1) uniform prior
        "impressions": 0, "clicks": 0, "lp_views": 0, "wa_started": 0,
        "proxy_pcvr_sum": 0.0,
        "conv_observed": 0.0, "conv_corrected": 0.0, "conv_true_crm": 0.0,
        "spend_minor": 0,
        "state": "active",
        "n_reward_updates": 0,
        "last_update_ts": 0,
    }


def ensure_arm(state: dict, variant_id: str) -> dict:
    arms = state.setdefault("arms", {})
    if variant_id not in arms:
        arms[variant_id] = _new_arm(variant_id)
    return arms[variant_id]


def update_arm(state: dict, variant_id: str, *,
               pcvr_calibrated: float = 0.0,
               observed_conv: float = 0.0,
               expected_observed_fraction: float = 1.0,
               platform_reported_conv: float = 0.0,
               crm_true_conv: float = 0.0,
               impressions: int = 0, clicks: int = 0,
               lp_views: int = 0, wa_started: int = 0,
               spend_minor: int = 0, ts: int = 0) -> dict:
    """Fold one observation into an arm's Beta posterior using the blended reward.

    Reconciliation_factor is recomputed (clamped, REDTEAM M3) from CRM-vs-platform and
    used to scale the delay-corrected conversion to CRM-truth before blending. `w`
    decays with cumulative true conversions. Returns the updated arm."""
    arm = ensure_arm(state, variant_id)
    arm["impressions"] += int(impressions)
    arm["clicks"] += int(clicks)
    arm["lp_views"] += int(lp_views)
    arm["wa_started"] += int(wa_started)
    arm["spend_minor"] += int(spend_minor)
    arm["conv_observed"] += float(observed_conv)

    # Reconcile platform-reported -> CRM-true (clamped).
    factor = clamp_reconciliation(platform_reported_conv, crm_true_conv)
    state["reconciliation_factor"] = factor

    # Delay-correct, then pull toward CRM-truth via the factor.
    corrected = delay_correction(observed_conv, expected_observed_fraction) * factor
    arm["conv_corrected"] += corrected
    arm["conv_true_crm"] += float(crm_true_conv)
    arm["proxy_pcvr_sum"] += float(pcvr_calibrated)

    # Decaying blend weight off cumulative true conversions across all arms.
    total_true = sum(float(a.get("conv_true_crm", 0.0)) for a in state["arms"].values())
    state["w"] = decay_w(state.get("w0", DEFAULT_W0),
                         state.get("w_decay_per_conv", DEFAULT_W_DECAY_PER_CONV),
                         total_true, state.get("w_floor", DEFAULT_W_FLOOR))

    reward = blended_reward(pcvr_calibrated, corrected, state["w"])
    arm["alpha"] += reward
    arm["beta"] += (1.0 - reward)
    arm["n_reward_updates"] += 1
    arm["last_update_ts"] = int(ts)
    return arm


def _active_arms(state: dict) -> list:
    return [a for a in state.get("arms", {}).values() if a.get("state") == "active"]


def select_arm(state: dict, rng: Any = None) -> Optional[str]:
    """Top-Two Thompson selection: sample argmax; with prob (1-beta) return a distinct
    challenger. Returns the chosen variant_id to *serve next* (proposal, not a spend)."""
    arms = _active_arms(state)
    if not arms:
        return None
    if len(arms) == 1:
        return arms[0]["variant_id"]
    g = _rng(rng)
    a = np.array([float(x["alpha"]) for x in arms])
    b = np.array([float(x["beta"]) for x in arms])
    ids = [x["variant_id"] for x in arms]
    beta_p = float(state.get("ttts_beta", DEFAULT_TTTS_BETA))
    s = g.beta(a, b)
    i = int(np.argmax(s))
    if g.random() < beta_p:
        return ids[i]
    # Challenger: resample until a distinct argmax appears (best-arm-identification).
    for _ in range(64):
        s2 = g.beta(a, b)
        j = int(np.argmax(s2))
        if j != i:
            return ids[j]
    return ids[i]


def best_arm_confidence(state: dict, rng: Any = None,
                        n_samples: int = DEFAULT_CONF_SAMPLES) -> tuple[Optional[str], float]:
    """(best_arm_id, P(best > 2nd-best)) by Monte-Carlo over the posteriors.

    Confidence = fraction of joint samples in which the posterior-mean leader also
    has the largest sampled draw. Gates kill/scale (research §5A)."""
    arms = _active_arms(state)
    if not arms:
        return (None, 0.0)
    if len(arms) == 1:
        return (arms[0]["variant_id"], 1.0)
    g = _rng(rng)
    a = np.array([float(x["alpha"]) for x in arms])
    b = np.array([float(x["beta"]) for x in arms])
    ids = [x["variant_id"] for x in arms]
    means = a / (a + b)
    leader = int(np.argmax(means))
    samples = g.beta(a[None, :], b[None, :], size=(n_samples, len(arms)))
    winners = np.argmax(samples, axis=1)
    conf = float(np.mean(winners == leader))
    return (ids[leader], conf)


def _warmed_up(arm: dict) -> bool:
    """REDTEAM M1 cold-start: only trust an arm once it has min-n samples AND a
    non-degenerate posterior (std above the floor). Suppresses early false kills."""
    n = int(arm.get("impressions", 0) or 0)
    updates = int(arm.get("n_reward_updates", 0) or 0)
    if n < WARMUP_MIN_SAMPLES or updates < 1:
        return False
    a = float(arm.get("alpha", 1.0)); b = float(arm.get("beta", 1.0))
    # std of Beta(a,b)
    denom = (a + b) ** 2 * (a + b + 1.0)
    std = math.sqrt((a * b) / denom) if denom > 0 else 0.0
    return std > WARMUP_STD_FLOOR


def _move(plan_id: str, move: str, reason: str, *, variant_id: str = None,
          spend_delta_sign: int = 0, **extra) -> dict:
    """A proposed Move. `spend_delta_sign`: -1 reduces spend, +1 increases, 0 neutral.
    REDTEAM C5: guardrails forces draft/approve on any sign >= 0 (non-decreasing)."""
    m = {
        "plan_id": plan_id,
        "move": move,
        "reason": reason,
        "variant_id": variant_id,
        "spend_delta_sign": int(spend_delta_sign),
        "outcome": "proposed",
        "blocked_by": None,
    }
    m.update(extra)
    return m


def propose_bandit_moves(state: dict, *, conf_gate: float = DEFAULT_CONF_GATE,
                         rng: Any = None) -> list[dict]:
    """PROPOSE bandit moves (never spends). Returns a list of Move dicts.

    Logic (all gated, conservative):
      * compute best arm + confidence;
      * if not enough confidence OR the best arm isn't warmed up -> `hold` only;
      * else propose `scale_winner` for the leader (spend-INCREASING => sign +1, so
        guardrails forces approval, REDTEAM C5) and `kill_loser` for clearly-worse,
        warmed-up arms (spend-DECREASING => sign -1, auto-applyable).
    The learning-phase lock + caps live in guardrails; this only emits candidates."""
    plan_id = state.get("campaign_id", "")
    moves: list[dict] = []
    best_id, conf = best_arm_confidence(state, rng=rng)
    state["best_arm_id"] = best_id
    state["best_arm_confidence"] = conf
    arms = _active_arms(state)
    if best_id is None or len(arms) < 2:
        moves.append(_move(plan_id, "hold", "single/zero active arm; nothing to compare"))
        return moves

    best_arm = state["arms"].get(best_id, {})
    if conf < conf_gate or not _warmed_up(best_arm):
        moves.append(_move(
            plan_id, "hold",
            f"insufficient confidence/warm-up: P(best>2nd)={conf:.2f}<{conf_gate:.2f} "
            f"or leader not warmed up (n={best_arm.get('impressions',0)})",
            best_arm_confidence=conf))
        return moves

    means = {x["variant_id"]: float(x["alpha"]) / (float(x["alpha"]) + float(x["beta"]))
             for x in arms}
    best_mean = means[best_id]
    # Scale the winner — spend-INCREASING, so it must route through draft/approve.
    moves.append(_move(
        plan_id, "scale_winner",
        f"posterior mean {best_mean:.4f} leads, P(best>2nd)={conf:.2f}>={conf_gate:.2f}",
        variant_id=best_id, spend_delta_sign=+1, best_arm_confidence=conf))
    # Kill clear losers — spend-DECREASING, warmed-up, and well below the winner.
    for x in arms:
        vid = x["variant_id"]
        if vid == best_id:
            continue
        if _warmed_up(x) and means[vid] < 0.5 * best_mean:
            moves.append(_move(
                plan_id, "kill_loser",
                f"posterior mean {means[vid]:.4f} << winner {best_mean:.4f}; warmed up",
                variant_id=vid, spend_delta_sign=-1, best_arm_confidence=conf))
    return moves


# ===========================================================================
# Cross-channel budget allocation: GP-UCB response curve + multi-choice knapsack.
# ===========================================================================
def _gp_ucb_curve(history: list, levels: "np.ndarray", theta: float,
                  ucb_beta: float, saturation: Optional[float]) -> "np.ndarray":
    """Predictive UCB reward at each candidate budget level.

    Uses sklearn GaussianProcessRegressor(RBF) when available; otherwise a pure-numpy
    fallback: monotone interpolation of the (spend->reward) points + a sparsity-based
    uncertainty term. Saturates reward beyond the max observed spend (diminishing
    returns). `ucb = mean + ucb_beta*(1-theta)*std` (research §2/§5C)."""
    levels = np.asarray(levels, dtype=float)
    if not history:
        # No data: flat tiny reward, all uncertainty -> exploration-only.
        return ucb_beta * (1.0 - theta) * np.ones_like(levels)
    xs = np.array([float(h[0]) for h in history], dtype=float)
    ys = np.array([float(h[1]) for h in history], dtype=float)
    order = np.argsort(xs)
    xs, ys = xs[order], ys[order]

    mean = None
    std = None
    try:  # sklearn path (preferred when present)
        from sklearn.gaussian_process import GaussianProcessRegressor
        from sklearn.gaussian_process.kernels import RBF, WhiteKernel
        span = max(float(xs.max() - xs.min()), 1.0)
        kernel = RBF(length_scale=span / 2.0) + WhiteKernel(noise_level=1e-2)
        gp = GaussianProcessRegressor(kernel=kernel, normalize_y=True, alpha=1e-6)
        gp.fit(xs.reshape(-1, 1), ys)
        mean, std = gp.predict(levels.reshape(-1, 1), return_std=True)
    except Exception:  # noqa: BLE001 — numpy fallback (no hard sklearn dep)
        mean = np.interp(levels, xs, ys, left=ys[0], right=ys[-1])
        # Uncertainty grows with distance to the nearest observed spend point.
        nearest = np.array([np.min(np.abs(xs - lv)) for lv in levels])
        scale = max(float(np.std(ys)), 1e-6)
        span = max(float(xs.max() - xs.min()), 1.0)
        std = scale * (nearest / span)

    mean = np.asarray(mean, dtype=float)
    std = np.asarray(std, dtype=float)
    # Saturate beyond the diminishing-returns ceiling.
    if saturation is not None:
        cap = float(saturation)
        mean = np.where(levels > cap, np.interp(cap, levels, mean), mean)
    ucb = mean + ucb_beta * (1.0 - float(theta)) * std
    # Reward must be non-negative for the knapsack value semantics.
    return np.maximum(ucb, 0.0)


def detect_change_point(history: list, mae_threshold: float = DEFAULT_CHANGEPOINT_MAE) -> bool:
    """True if the recent residual vs the older trend exceeds the normalized MAE
    threshold (regime shift -> reset the GP window, research §2). Conservative: needs
    >=4 points; normalizes by reward scale so it's unit-free."""
    if not history or len(history) < 4:
        return False
    ys = np.array([float(h[1]) for h in history], dtype=float)
    half = len(ys) // 2
    old, new = ys[:half], ys[half:]
    scale = max(float(np.mean(np.abs(ys))), 1e-6)
    mae = float(np.mean(np.abs(new.mean() - old)))
    return (mae / scale) > float(mae_threshold)


def knapsack_allocate(channels: list, level_values: dict, total_budget: int, step: int,
                      min_bounds: dict | None = None, max_bounds: dict | None = None) -> dict:
    """Multi-choice knapsack DP: pick exactly one budget level per channel to maximize
    total reward s.t. sum(levels) <= total_budget, honoring per-channel min/max.

    `level_values[ch]` = list of (budget_minor, value). Budgets are multiples of `step`.
    Returns {channel: allocated_budget_minor}. If a feasible all-channel pick can't be
    found within budget, falls back to each channel's min bound (clamped to budget)."""
    min_bounds = min_bounds or {}
    max_bounds = max_bounds or {}
    step = max(int(step), 1)
    G = int(total_budget) // step
    n = len(channels)
    NEG = -1e18
    # dp[j][g] = best value using first j channels with g*step budget spent.
    dp = np.full((n + 1, G + 1), NEG, dtype=float)
    dp[0, 0] = 0.0
    pick = [[None] * (G + 1) for _ in range(n + 1)]
    for j, ch in enumerate(channels, 1):
        lo = int(min_bounds.get(ch, 0))
        hi = int(max_bounds.get(ch, total_budget))
        opts = [(int(b), float(v)) for (b, v) in level_values.get(ch, [])
                if lo <= int(b) <= hi]
        if not opts:
            opts = [(lo, 0.0)]  # forced minimum if no valid level
        # Guarantee the per-channel MIN bound is always selectable (leftover budget is
        # absorbed by NOT spending it, never by skipping a channel — so min_bounds bind).
        if lo > 0 and not any(b == lo for (b, _) in opts):
            opts.append((lo, 0.0))
        for g in range(G + 1):
            # Each channel MUST pick exactly one of its options (no row carry/skip), so a
            # channel can never be dropped below its min bound. Leaving total budget unspent
            # is modelled by each channel's own low-budget option, not by skipping the channel.
            for (b, val) in opts:
                gb = b // step
                if gb <= g and dp[j - 1, g - gb] + val > dp[j, g]:
                    dp[j, g] = dp[j - 1, g - gb] + val
                    pick[j][g] = (g - gb, ch, b)
    # Backtrack from the best g.
    best_g = int(np.argmax(dp[n]))
    if dp[n, best_g] <= NEG / 2:
        # Infeasible -> min-bound fallback within budget.
        alloc, spent = {}, 0
        for ch in channels:
            b = min(int(min_bounds.get(ch, 0)), max(0, total_budget - spent))
            alloc[ch] = b
            spent += b
        return alloc
    alloc = {ch: 0 for ch in channels}
    g = best_g
    for j in range(n, 0, -1):
        entry = pick[j][g]
        if entry is None:
            break
        prev_g, ch, b = entry
        alloc[ch] = int(b)
        g = prev_g
    return alloc


def propose_allocation(alloc_state: dict, *, total_budget_minor: int | None = None,
                       step_minor: int | None = None, ucb_beta: float = DEFAULT_UCB_BETA,
                       min_bounds: dict | None = None, max_bounds: dict | None = None,
                       rng: Any = None) -> dict:
    """PROPOSE a cross-channel split (never spends). Returns:
        {"allocation": {channel: budget_minor}, "moves": [Move...],
         "changed_points": [channels reset], "solver": "gp_ucb_knapsack"}.

    Any channel whose proposed alloc RISES vs its current `alloc_minor` yields a
    spend-increasing `reallocate` move (sign +1 -> draft/approve, REDTEAM C5);
    decreases are sign -1 (auto-applyable)."""
    channels_meta = alloc_state.get("channels", {})
    channels = list(channels_meta.keys())
    B = int(total_budget_minor if total_budget_minor is not None
            else alloc_state.get("total_budget_minor", 0))
    step = int(step_minor if step_minor is not None
               else alloc_state.get("step_minor", max(B // 20, 1)))
    step = max(step, 1)
    cp_threshold = float(alloc_state.get("change_point", {}).get("mae_threshold",
                                                                 DEFAULT_CHANGEPOINT_MAE))
    changed: list[str] = []
    level_values: dict = {}
    levels = np.arange(0, B + step, step, dtype=float)
    for ch in channels:
        meta = channels_meta[ch]
        history = list(meta.get("history", []))
        # Change-point reset: drop older points, keep the recent window.
        if detect_change_point(history, cp_threshold):
            keep = max(2, len(history) // 2)
            history = history[-keep:]
            meta["history"] = history
            changed.append(ch)
        theta = float(meta.get("theta", 0.5))
        saturation = meta.get("saturation_minor")
        ucb = _gp_ucb_curve(history, levels, theta, ucb_beta,
                            float(saturation) if saturation is not None else None)
        level_values[ch] = list(zip([int(x) for x in levels], [float(v) for v in ucb]))

    alloc = knapsack_allocate(channels, level_values, B, step, min_bounds, max_bounds)

    moves: list[dict] = []
    for ch in channels:
        cur = int(channels_meta[ch].get("alloc_minor", 0))
        new = int(alloc.get(ch, 0))
        channels_meta[ch]["alloc_minor"] = new  # proposed; not a spend until approved
        if new == cur:
            continue
        sign = +1 if new > cur else -1
        moves.append(_move(
            alloc_state.get("account_id", ""), "reallocate",
            f"channel {ch}: {cur} -> {new} paise/day (GP-UCB+knapsack)",
            channel=ch, from_minor=cur, to_minor=new, spend_delta_sign=sign))

    alloc_state["last_alloc_minor"] = int(sum(alloc.values()))
    alloc_state.setdefault("change_point", {})["tripped"] = bool(changed)
    alloc_state["solver"] = "gp_ucb_knapsack"
    return {
        "allocation": alloc,
        "moves": moves,
        "changed_points": changed,
        "solver": "gp_ucb_knapsack",
    }
