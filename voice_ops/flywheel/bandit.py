"""voice_ops.flywheel.bandit — Layer-D online learner (hierarchical Thompson sampling).

WHY a bandit, and WHY this shape. The Flywheel has knobs the agent can turn at call time —
the LLM `model`, the TTS `voice`, the prompt `variant`, the `opening` line, the `rebuttal`
playbook (schema.KNOBS). We do NOT want a slow, monolithic A/B test per joint configuration
(the joint arm space is multiplicative and most cells never get data); we want each knob to
learn INDEPENDENTLY and CONTINUOUSLY from the fused reward, exploiting what already wins while
still spending a small, *honest* fraction of traffic on exploration. That is exactly what a
**factored Beta-Bernoulli Thompson sampler** gives: one ArmPosterior (a Beta(alpha, beta)
belief over P(good-turn|arm)) per (knob, arm, context_bucket), updated post-call, sampled at
decision time. Thompson sampling is the right regret/UX trade-off for a conversational product
because it explores *probabilistically* (no jarring forced-random arm in the user's face most
of the time) yet provably converges.

The four pillars this module implements, and the science behind each:

  * HIERARCHICAL cold-start (hier_prior). A brand-new arm (a freshly proposed variant) has no
    data. Rather than start at the flat Beta(1,1) prior and waste calls discovering it is
    average, we SHRINK it toward the pooled mean of its siblings (empirical-Bayes partial
    pooling). New arms inherit the family's prior belief and only diverge as their own evidence
    accumulates — far less cold-start regret, and it is the statistically honest prior.

  * FORCED EXPLORATION FLOOR (select_arm epsilon). Pure Thompson sampling can drive an arm's
    selection probability to ~0, which DESTROYS off-policy evaluation: SNIPS/IPS importance
    weights need every logged action to have had a positive, KNOWN propensity (the positivity /
    overlap assumption). So with probability `epsilon` we pick a uniform-random arm. This is not
    just exploration — it is the PRECONDITION that lets ope.py honestly score challengers from
    logged data later. The propensity we return is the true mixture
    `(1 - epsilon) * p_thompson + epsilon / n`, floored above zero, and written into every
    TrajectoryRow.propensity. No fabricated propensities — honest science.

  * NON-STATIONARITY (update_posterior discount). Real-estate demand, the caller pool, and the
    competing models all drift. A stationary Beta posterior with unbounded pseudo-counts becomes
    deaf to recent evidence (an arm that was great six months ago can no longer be dethroned).
    So before adding new evidence we DECAY the pseudo-counts toward the prior by `discount`
    (a sliding-window / exponential-forgetting Beta-Bernoulli). The belief stays responsive.

  * GUARDRAILS + REVERT (guardrails, revert_to_champion). COMPLIANCE/SAFETY IS NEVER A REWARD
    TERM (anti-Goodhart). The bandit optimizes the fused reward, but an arm that wins bookings
    while spiking the opt-out rate or the cost-per-booking is BLOCKED by a hard guardrail gate,
    not penalized in the reward. `revert_to_champion` gives the worker an instant kill-switch:
    fall back to the highest-posterior-mean arm with enough plays to trust it.

DESIGN LAWS: pure-python (random + math only — NO numpy/scipy), `rng` injectable for
deterministic tests, dormant-safe & best-effort (every public function swallows its own errors
→ logging.warning, never raises into a caller), and it imports/works with zero ClickHouse /
network. This is offline/post-call policy state — it never touches the live LiveKit turn loop.
"""
from __future__ import annotations

import logging
import math
import random
from typing import List, Optional, Tuple

from .schema import ArmPosterior, now_iso

logger = logging.getLogger("flywheel.bandit")

# Monte-Carlo budget for estimating each arm's Thompson selection probability p_ts.
# 2000 joint draws gives a ~±1% std-error on a probability — plenty for a logged propensity,
# and cheap (pure-python, off the live path). Kept module-level so tests can shrink it.
_MC_SAMPLES = 2000

# Never log (or write) a propensity of exactly 0 — that nukes the OPE importance weight
# (division by zero / undefined overlap). Floor at a small epsilon. Also used to keep
# Beta parameters strictly positive.
_PROP_FLOOR = 1e-4
_MIN_BETA_PARAM = 1e-6

# revert_to_champion trust threshold — an arm needs this many plays before its posterior mean
# is considered earned rather than prior-driven noise.
_TRUST_PLAYS = 20


# --------------------------------------------------------------------------- #
# Core draw — one Beta sample via the gamma-ratio identity (pure-python).
# --------------------------------------------------------------------------- #
def beta_sample(alpha: float, beta: float, rng: Optional[random.Random] = None) -> float:
    """One draw X ~ Beta(alpha, beta) using X = G1 / (G1 + G2), Gi ~ Gamma(ai, 1).

    Pure stdlib (random.gammavariate) so the bandit carries no heavy deps. Guards alpha,beta>0
    (a non-positive shape would make gammavariate raise) and the degenerate G1+G2==0 case.
    Best-effort: any failure falls back to the prior mean alpha/(alpha+beta) so a caller never
    sees an exception. Returns a value in [0, 1]."""
    try:
        r = rng or random
        a = float(alpha) if alpha and alpha > 0 else _MIN_BETA_PARAM
        b = float(beta) if beta and beta > 0 else _MIN_BETA_PARAM
        g1 = r.gammavariate(a, 1.0)
        g2 = r.gammavariate(b, 1.0)
        denom = g1 + g2
        if denom <= 0.0:
            return a / (a + b)
        x = g1 / denom
        # Clamp away from exact 0/1 to keep downstream logs/weights well-behaved.
        if x < 0.0:
            return 0.0
        if x > 1.0:
            return 1.0
        return x
    except Exception as exc:  # noqa: BLE001
        logger.warning("flywheel.bandit.beta_sample error: %r", exc)
        try:
            a = float(alpha) or 1.0
            b = float(beta) or 1.0
            return a / (a + b) if (a + b) > 0 else 0.5
        except Exception:  # noqa: BLE001
            return 0.5


# --------------------------------------------------------------------------- #
# select_arm — epsilon-floored Thompson selection + an HONEST mixture propensity.
# --------------------------------------------------------------------------- #
def _arm_id(arm) -> str:
    """arm may be an ArmPosterior or a dict (store rows) — read its id either way."""
    if arm is None:
        return ""
    if isinstance(arm, dict):
        return str(arm.get("arm_id") or "")
    return str(getattr(arm, "arm_id", "") or "")


def _ab(arm) -> Tuple[float, float]:
    """Pull (alpha, beta) off an ArmPosterior or a dict, guarded strictly positive."""
    if isinstance(arm, dict):
        a = float(arm.get("alpha", 1.0) or 1.0)
        b = float(arm.get("beta", 1.0) or 1.0)
    else:
        a = float(getattr(arm, "alpha", 1.0) or 1.0)
        b = float(getattr(arm, "beta", 1.0) or 1.0)
    return (max(a, _MIN_BETA_PARAM), max(b, _MIN_BETA_PARAM))


def select_arm(
    arms: List,
    *,
    epsilon: float = 0.08,
    explore_cap: float = 0.15,
    rng: Optional[random.Random] = None,
) -> Tuple[str, float]:
    """Pick ONE arm and return (arm_id, propensity) — the load-bearing OPE primitive.

    Mechanism:
      * With probability `epsilon` (the forced-exploration floor, clamped to [0, explore_cap])
        pick a UNIFORM random arm. This guarantees every arm keeps a positive selection
        probability → the positivity assumption ope.py's importance weights depend on.
      * Otherwise Thompson-sample: one Beta draw per arm, argmax. This is the exploit path.

    `propensity` is the TRUE probability the live policy would have chosen the returned arm under
    this exact rule: (1 - eps) * p_thompson + eps / n, where p_thompson is estimated by a quick
    Monte-Carlo of joint Beta draws (count of times this arm is the argmax). Floored above zero
    so a logged turn never carries an un-invertible weight. Empty list → ('', 1.0).

    Best-effort: any internal failure degrades to a uniform pick with propensity 1/n. NEVER
    raises into the caller (this is read off the policy decision, but stays robust regardless)."""
    try:
        pool = [a for a in (arms or []) if _arm_id(a)]
        n = len(pool)
        if n == 0:
            return ("", 1.0)
        if n == 1:
            return (_arm_id(pool[0]), 1.0)

        r = rng or random
        eps = epsilon
        if eps != eps or eps < 0.0:  # NaN / negative guard
            eps = 0.0
        cap = explore_cap if (explore_cap == explore_cap and explore_cap >= 0.0) else 0.15
        eps = min(eps, cap)

        params = [_ab(a) for a in pool]
        ids = [_arm_id(a) for a in pool]

        # --- choose the arm ------------------------------------------------- #
        if r.random() < eps:
            idx = r.randrange(n)  # uniform forced-exploration draw
        else:
            best_i, best_x = 0, -1.0
            for i, (a, b) in enumerate(params):
                x = beta_sample(a, b, rng=r)
                if x > best_x:
                    best_i, best_x = i, x
            idx = best_i

        # --- estimate p_thompson for the CHOSEN arm via joint MC ------------ #
        wins = 0
        n_mc = max(1, _MC_SAMPLES)
        for _ in range(n_mc):
            best_j, best_v = 0, -1.0
            for j, (a, b) in enumerate(params):
                v = beta_sample(a, b, rng=r)
                if v > best_v:
                    best_j, best_v = j, v
            if best_j == idx:
                wins += 1
        p_ts = wins / float(n_mc)

        # Honest mixture propensity: exploit mass + forced-exploration mass.
        propensity = (1.0 - eps) * p_ts + eps / float(n)
        propensity = min(1.0, max(_PROP_FLOOR, propensity))
        return (ids[idx], propensity)
    except Exception as exc:  # noqa: BLE001
        logger.warning("flywheel.bandit.select_arm error: %r", exc)
        try:
            pool = [a for a in (arms or []) if _arm_id(a)]
            if not pool:
                return ("", 1.0)
            return (_arm_id(pool[0]), 1.0 / float(len(pool)))
        except Exception:  # noqa: BLE001
            return ("", 1.0)


# --------------------------------------------------------------------------- #
# update_posterior — discounted (forgetting) Beta-Bernoulli evidence update.
# --------------------------------------------------------------------------- #
def update_posterior(arm, reward: float, *, discount: float = 0.98) -> ArmPosterior:
    """Fold one fused reward into an arm's belief and return a NEW ArmPosterior (no mutation).

    Steps (the forgetting Beta-Bernoulli):
      1. Clip reward to [0, 1] — the bandit treats the fused reward as a soft-Bernoulli success
         signal; an out-of-range or NaN reward is squashed, never trusted.
      2. DECAY the pseudo-counts toward the flat prior by `discount` BEFORE adding evidence:
         alpha <- 1 + d*(alpha-1), beta <- 1 + d*(beta-1). This is exponential forgetting — old
         evidence fades so the posterior tracks non-stationary drift (caller pool, model perf).
      3. ADD the new evidence: alpha += reward, beta += (1 - reward).
      4. Bump plays, reward_sum, the discounted reward mass, and last_reward_ts = now_iso().

    Best-effort: a malformed `arm` or bad reward returns the input coerced to a fresh posterior
    (or a flat prior) rather than raising. NEVER raises into a caller."""
    try:
        # --- read current state (dataclass OR dict) ------------------------ #
        if isinstance(arm, dict):
            base = ArmPosterior(
                tenant_id=str(arm.get("tenant_id", "") or ""),
                campaign_id=str(arm.get("campaign_id", "") or ""),
                vertical=str(arm.get("vertical", "real_estate") or "real_estate"),
                knob=str(arm.get("knob", "variant") or "variant"),
                arm_id=str(arm.get("arm_id", "") or ""),
                context_bucket=str(arm.get("context_bucket", "all") or "all"),
                alpha=float(arm.get("alpha", 1.0) or 1.0),
                beta=float(arm.get("beta", 1.0) or 1.0),
                plays=int(arm.get("plays", 0) or 0),
                reward_sum=float(arm.get("reward_sum", 0.0) or 0.0),
                last_reward_ts=str(arm.get("last_reward_ts", "") or ""),
                discounted=float(arm.get("discounted", 0.0) or 0.0),
                guardrail_optout_rate=float(arm.get("guardrail_optout_rate", 0.0) or 0.0),
                guardrail_cost_per_booking=float(arm.get("guardrail_cost_per_booking", 0.0) or 0.0),
            )
        elif isinstance(arm, ArmPosterior):
            base = arm
        else:
            base = ArmPosterior()

        # 1. clip reward to a soft-Bernoulli [0, 1]
        try:
            rwd = float(reward)
        except Exception:  # noqa: BLE001
            rwd = 0.0
        if rwd != rwd:  # NaN guard
            rwd = 0.0
        rwd = min(1.0, max(0.0, rwd))

        # 2. forget toward the flat Beta(1,1) prior
        d = float(discount)
        if d != d or d < 0.0:  # NaN / negative guard
            d = 0.0
        d = min(1.0, d)
        old_a = max(_MIN_BETA_PARAM, float(base.alpha) or 1.0)
        old_b = max(_MIN_BETA_PARAM, float(base.beta) or 1.0)
        a = 1.0 + d * (old_a - 1.0)
        b = 1.0 + d * (old_b - 1.0)

        # 3. add the new evidence (soft success / failure split)
        a = max(_MIN_BETA_PARAM, a + rwd)
        b = max(_MIN_BETA_PARAM, b + (1.0 - rwd))

        # 4. bump counters + provenance ts; discounted mass also forgets old contributions
        new_discounted = d * float(base.discounted or 0.0) + rwd

        return ArmPosterior(
            tenant_id=base.tenant_id,
            campaign_id=base.campaign_id,
            vertical=base.vertical,
            knob=base.knob,
            arm_id=base.arm_id,
            context_bucket=base.context_bucket,
            ts_iso=now_iso(),
            alpha=round(a, 6),
            beta=round(b, 6),
            plays=int(base.plays or 0) + 1,
            reward_sum=round(float(base.reward_sum or 0.0) + rwd, 6),
            last_reward_ts=now_iso(),
            discounted=round(new_discounted, 6),
            guardrail_optout_rate=float(base.guardrail_optout_rate or 0.0),
            guardrail_cost_per_booking=float(base.guardrail_cost_per_booking or 0.0),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("flywheel.bandit.update_posterior error: %r", exc)
        try:
            if isinstance(arm, ArmPosterior):
                return arm
        except Exception:  # noqa: BLE001
            pass
        return ArmPosterior()


# --------------------------------------------------------------------------- #
# hier_prior — empirical-Bayes shrunk shared prior for cold-start arms.
# --------------------------------------------------------------------------- #
def hier_prior(sibling_arms: List) -> Tuple[float, float]:
    """Pool sibling arms into a single shrunk Beta(alpha0, beta0) prior for a cold-start arm.

    Empirical-Bayes partial pooling: estimate the family's grand success rate from the siblings'
    POOLED pseudo-counts, then express it as a weak prior with a small effective sample size
    (so a new arm inherits the family belief but is quickly overridden by its own evidence).
    This is the statistically honest way to start a fresh variant instead of the flat Beta(1,1)
    (which wastes calls re-discovering the family mean).

    Returns (alpha0, beta0); falls back to the flat prior (1.0, 1.0) when there are no usable
    siblings. Best-effort — never raises."""
    try:
        sibs = sibling_arms or []
        sum_a = 0.0
        sum_b = 0.0
        for s in sibs:
            a, b = _ab(s)
            # Use the evidence mass above the flat prior so unplayed siblings don't dominate.
            sum_a += max(0.0, a - 1.0)
            sum_b += max(0.0, b - 1.0)
        total = sum_a + sum_b
        if total <= 0.0:
            return (1.0, 1.0)
        p = sum_a / total
        # Guard the pooled rate into the open interval so neither shape collapses to ~0.
        p = min(1.0 - 1e-3, max(1e-3, p))
        # Weak prior strength: a small effective sample size keeps it easy to override.
        # Scale gently with how much family evidence we have (more siblings -> a touch firmer),
        # but cap so the prior never swamps a new arm's own data.
        strength = min(8.0, max(2.0, math.sqrt(total)))
        alpha0 = max(_MIN_BETA_PARAM, p * strength)
        beta0 = max(_MIN_BETA_PARAM, (1.0 - p) * strength)
        return (round(alpha0, 6), round(beta0, 6))
    except Exception as exc:  # noqa: BLE001
        logger.warning("flywheel.bandit.hier_prior error: %r", exc)
        return (1.0, 1.0)


# --------------------------------------------------------------------------- #
# guardrails — the hard SAFETY gate (NEVER a reward term; anti-Goodhart).
# --------------------------------------------------------------------------- #
def guardrails(arm, *, max_optout: float = 0.15, max_cost_per_booking: float = 0.0) -> dict:
    """Is this arm SAFE to keep serving? A hard gate, never a reward penalty.

    Optimizing bookings must never be allowed to make the agent pushy/manipulative or blow the
    unit economics. So the bandit's reward stays clean and these limits sit OUTSIDE it: an arm
    that exceeds the opt-out ceiling (a manipulation/annoyance proxy) or the cost-per-booking
    ceiling is flagged not-ok and the worker can revert it — the optimization never gets to
    "buy" bookings with non-compliance.

    Returns {'ok': bool, 'reasons': [...]}. `max_cost_per_booking <= 0` disables that check
    (no budget configured). Best-effort — a malformed arm returns ok=True with an empty reason
    list rather than raising (fail-open on read errors; the explicit checks below fail-closed)."""
    reasons: List[str] = []
    try:
        if isinstance(arm, dict):
            optout = float(arm.get("guardrail_optout_rate", 0.0) or 0.0)
            cpb = float(arm.get("guardrail_cost_per_booking", 0.0) or 0.0)
        else:
            optout = float(getattr(arm, "guardrail_optout_rate", 0.0) or 0.0)
            cpb = float(getattr(arm, "guardrail_cost_per_booking", 0.0) or 0.0)

        if max_optout and max_optout > 0 and optout > max_optout:
            reasons.append(
                f"optout_rate {optout:.3f} > max {float(max_optout):.3f}")
        if max_cost_per_booking and max_cost_per_booking > 0 and cpb > max_cost_per_booking:
            reasons.append(
                f"cost_per_booking {cpb:.2f} > max {float(max_cost_per_booking):.2f}")
        return {"ok": not reasons, "reasons": reasons}
    except Exception as exc:  # noqa: BLE001
        logger.warning("flywheel.bandit.guardrails error: %r", exc)
        return {"ok": True, "reasons": []}


# --------------------------------------------------------------------------- #
# revert_to_champion — the instant kill-switch back to the trusted best arm.
# --------------------------------------------------------------------------- #
def revert_to_champion(arms: List) -> str:
    """Return the arm_id of the safe champion to fall back to (or '' if none).

    Champion = the highest posterior-mean arm AMONG those with enough plays to trust
    (plays >= _TRUST_PLAYS). If no arm has crossed that bar yet (early days), fall back to the
    highest posterior mean overall so the worker always has *something* to revert to. Posterior
    mean is alpha/(alpha+beta) (ArmPosterior.mean()). Best-effort — never raises."""
    try:
        pool = [a for a in (arms or []) if _arm_id(a)]
        if not pool:
            return ""

        def _mean(arm) -> float:
            a, b = _ab(arm)
            tot = a + b
            return (a / tot) if tot > 0 else 0.0

        def _plays(arm) -> int:
            if isinstance(arm, dict):
                return int(arm.get("plays", 0) or 0)
            return int(getattr(arm, "plays", 0) or 0)

        trusted = [a for a in pool if _plays(a) >= _TRUST_PLAYS]
        candidates = trusted if trusted else pool
        best = max(candidates, key=_mean)
        return _arm_id(best)
    except Exception as exc:  # noqa: BLE001
        logger.warning("flywheel.bandit.revert_to_champion error: %r", exc)
        return ""


__all__ = [
    "beta_sample",
    "select_arm",
    "update_posterior",
    "hier_prior",
    "guardrails",
    "revert_to_champion",
]


# --------------------------------------------------------------------------- #
# Inline self-check (no network / no ClickHouse) — happy path, synthetic arms.
# --------------------------------------------------------------------------- #
if __name__ == "__main__":  # pragma: no cover
    import sys

    rng = random.Random(7)  # deterministic for a repeatable smoke test

    # Build three synthetic arms with clearly different track records.
    arms = [
        ArmPosterior(tenant_id="t1", knob="variant", arm_id="A",
                     alpha=8.0, beta=2.0, plays=30, reward_sum=8.0),   # strong
        ArmPosterior(tenant_id="t1", knob="variant", arm_id="B",
                     alpha=3.0, beta=7.0, plays=30, reward_sum=3.0),   # weak
        ArmPosterior(tenant_id="t1", knob="variant", arm_id="C",
                     alpha=1.0, beta=1.0, plays=0, reward_sum=0.0),    # cold-start
    ]

    # 1. beta_sample in [0,1] and degenerate guard
    x = beta_sample(8.0, 2.0, rng=rng)
    assert 0.0 <= x <= 1.0, x
    assert 0.0 <= beta_sample(0.0, 0.0, rng=rng) <= 1.0       # guarded shapes
    print(f"[1] beta_sample(8,2) = {x:.4f}")

    # 2. select_arm: real id + a positive, <=1 propensity; empty -> ('',1.0)
    arm_id, prop = select_arm(arms, epsilon=0.08, explore_cap=0.15, rng=rng)
    assert arm_id in {"A", "B", "C"}, arm_id
    assert 0.0 < prop <= 1.0, prop
    assert select_arm([], rng=rng) == ("", 1.0)
    # single arm is deterministic with propensity 1.0
    assert select_arm([arms[0]], rng=rng) == ("A", 1.0)
    print(f"[2] select_arm -> arm={arm_id!r} propensity={prop:.4f}")

    # 3. update_posterior: NEW object, input untouched, counters bumped, discount applied
    before_alpha = arms[0].alpha
    upd = update_posterior(arms[0], 1.0, discount=0.98)
    assert isinstance(upd, ArmPosterior)
    assert upd is not arms[0]
    assert arms[0].alpha == before_alpha, "input was mutated!"
    assert upd.plays == arms[0].plays + 1
    assert upd.last_reward_ts and upd.ts_iso
    # reward clipping: an out-of-range reward must not explode the posterior
    upd_clip = update_posterior(arms[0], 5.0, discount=0.98)
    assert upd_clip.alpha <= before_alpha + 1.0 + 1e-6
    # dict-shaped arm also works
    upd_dict = update_posterior({"arm_id": "D", "alpha": 2.0, "beta": 2.0, "plays": 4}, 0.0)
    assert upd_dict.arm_id == "D" and upd_dict.plays == 5
    print(f"[3] update_posterior A: alpha {before_alpha} -> {upd.alpha}, mean {upd.mean()}")

    # 4. hier_prior: shrunk family prior; empty -> flat
    a0, b0 = hier_prior(arms[:2])
    assert a0 > 0 and b0 > 0
    assert hier_prior([]) == (1.0, 1.0)
    print(f"[4] hier_prior(siblings) = Beta({a0}, {b0})")

    # 5. guardrails: clean arm ok; breaching arm flagged
    clean = ArmPosterior(arm_id="clean", guardrail_optout_rate=0.05)
    bad = ArmPosterior(arm_id="bad", guardrail_optout_rate=0.40,
                       guardrail_cost_per_booking=900.0)
    assert guardrails(clean, max_optout=0.15)["ok"] is True
    g = guardrails(bad, max_optout=0.15, max_cost_per_booking=500.0)
    assert g["ok"] is False and len(g["reasons"]) == 2, g
    print(f"[5] guardrails(bad) = {g}")

    # 6. revert_to_champion: prefers the trusted high-mean arm (A)
    champ = revert_to_champion(arms)
    assert champ == "A", champ
    assert revert_to_champion([]) == ""
    print(f"[6] revert_to_champion -> {champ!r}")

    print("OK: flywheel.bandit self-check passed")
    sys.exit(0)
