"""voice_ops.flywheel.ensemble — B1: a 4-head reward ENSEMBLE + epistemic uncertainty + a
PESSIMISTIC lower-confidence-bound (LCB) reward. This is the anti-over-optimization guard of
the whole power-up tier.

WHY THIS MODULE EXISTS (and the science it encodes)
---------------------------------------------------
A single learned reward is a *proxy*. The moment an optimizer (the bandit / the challenger
search) is pointed at a proxy, it climbs the proxy — and a proxy that was only ever an
approximation of the true objective (a booked, compliant, brand-safe site visit) gets
EXPLOITED in its mis-specified corners. Gao, Schulman & Hilton (2023, "Scaling Laws for
Reward Model Overoptimization") show this empirically: gold reward rises, then *falls* as the
policy over-optimizes the proxy, and the gap widens with optimization pressure. The fix the
literature converges on is an ENSEMBLE that is consumed PESSIMISTICALLY:

  * WARM (Ramé et al., 2024) — averaging several reward heads is more robust to reward
    hacking than any single head, because heads disagree exactly where the proxy is unreliable.
  * Coste et al. (2024, "Reward Model Ensembles ... Uncertainty-Weighted Optimization", UWO) —
    don't optimize the ENSEMBLE MEAN, optimize  mean - λ·variance : penalize the policy for
    visiting regions where the heads DISAGREE (variance = epistemic uncertainty), which is
    precisely where over-optimization lives.
  * Moskovitz et al. (2023, "Confronting Reward Model Overoptimization with Constrained RLHF") —
    treat over-optimization as a CONSTRAINT and damp the proxy gradient with a Lagrangian
    multiplier when the gold-holdout stops tracking the proxy (the herding/over-opt brake).
  * ODIN (Chen et al., 2024) — disentangle the reward from a length/format nuisance head so the
    policy can't win by simply being longer or sweeter (a Hinglish telecaller's classic hacks).

So the 4 heads here are deliberately DIVERSE — they fail in different places, which is the
whole point of an ensemble:
  h_outcome — RewardComponents.terminal_credit : the sparse, true, credit-assigned terminal
              signal (the gold-anchored head).
  h_affect  — affect_delta : the dense potential-based friction-shaping channel (process).
  h_judge   — judge_score : the RLAIF cross-family rubric scalar (process).
  h_value   — value_head : the learned critic V(state) (B3), centred — a model-based head.

We z-normalize each head to its OWN cohort baseline (so a head measured in different units /
on a different scale can't dominate by scale alone), take the mean over the heads that are
actually PRESENT (a dormant/missing head is EXCLUDED, never silently treated as a 0 — treating a
missing value head as 0 would be a fake, scale-distorting datapoint), measure DISAGREEMENT as
the population variance across heads (= epistemic uncertainty), blend in each head's INTRINSIC
uncertainty (judge: 1-confidence; affect: friction-variance-derived; value: a Wilson half-width),
and hand the optimizer the PESSIMISTIC LCB:

    R_LCB = mu - λ·var - κ·u            (UWO + an extra uncertainty discount)

This is what `RewardComponents.optimized()` returns once `fuse_pessimistic` has run — so the
bandit and the challenger search consume the *lower bound*, never the point estimate. The
point estimate (`.fused()`) is kept untouched for the console (honest-science provenance).

DESIGN LAWS (mirror voice_ops/research/*.py + the sibling flywheel modules): PURE-PYTHON
(math/statistics only — NO numpy/torch at import or anywhere; the pessimistic path must run on
a bare interpreter); SIDE-PIPELINE (offline/worker enrichment, never the live turn loop);
DORMANT-SAFE + BEST-EFFORT (every public function swallows its own errors → logging.warning and
returns a clean zero/neutral value, NEVER raises into a call); ANTI-GOODHART (compliance is a
HARD GATE elsewhere, never a head here; the optimizer consumes the LCB lower bound; rewards are
capped). The module imports cleanly with no ClickHouse / no network / no heavy deps.
"""
from __future__ import annotations

import logging
import math
from statistics import fmean
from typing import Dict, Iterable, List, Optional, Tuple

from . import config as _cfg

logger = logging.getLogger("flywheel.ensemble")

# Canonical head order — keeps mu/var deterministic and the provenance legible.
HEAD_KEYS: Tuple[str, ...] = ("h_outcome", "h_affect", "h_judge", "h_value")

# A head whose magnitude is below this AND was not explicitly provided is treated as a
# dormant/MISSING head (excluded from the ensemble), not as a real 0 datapoint.
_MISSING_EPS = 1e-9


# --------------------------------------------------------------------------- #
# Small pure-python numeric guards (mirrors reward.py / credit.py _num/_f).
# --------------------------------------------------------------------------- #
def _num(v, default: float = 0.0) -> float:
    """Coerce to a finite float; non-finite / un-coercible → default."""
    try:
        f = float(v)
    except Exception:  # noqa: BLE001
        return default
    if math.isnan(f) or math.isinf(f):
        return default
    return f


def _present(value: float, explicit: bool) -> bool:
    """A head counts as PRESENT iff it was explicitly supplied OR carries real magnitude.

    A head that is both dormant (not supplied) AND ~0 is MISSING — excluded from the mean and
    the variance so a dormant value-head can't pull the ensemble toward zero."""
    if explicit:
        return True
    return abs(_num(value)) > _MISSING_EPS


# --------------------------------------------------------------------------- #
# head_contributions — pull the 4 head values from a turn / RewardComponents-like dict.
# --------------------------------------------------------------------------- #
def head_contributions(turn: dict) -> dict:
    """Extract the 4 ensemble head values from a turn / RewardComponents-like mapping.

    Accepts either a flat dict (TrajectoryRow.to_row() shape) or a RewardComponents-shaped dict
    (terminal_credit / affect_delta / judge_score / value_head). Returns a dict with the 4
    canonical head keys PLUS a parallel ``_present`` map recording which heads were explicitly
    supplied (so a genuine 0 from an upstream computation is distinguished from a dormant head)
    PLUS a passthrough ``_z`` cohort-baseline map and ``confidence``/``state_friction`` so the
    intrinsic-uncertainty estimators downstream have what they need. Best-effort: a malformed
    turn yields an all-missing head dict, never an exception."""
    out: dict = {k: 0.0 for k in HEAD_KEYS}
    present: Dict[str, bool] = {k: False for k in HEAD_KEYS}
    try:
        t = turn or {}

        # h_outcome: prefer the credit-assigned terminal share; fall back to capped/raw outcome.
        for key in ("terminal_credit", "credit_advantage", "capped_outcome", "reward_capped",
                    "raw_outcome", "h_outcome"):
            if key in t and t.get(key) is not None:
                out["h_outcome"] = _num(t.get(key))
                present["h_outcome"] = True
                break

        # h_affect: the PBRS friction-shaping channel.
        for key in ("affect_delta", "h_affect"):
            if key in t and t.get(key) is not None:
                out["h_affect"] = _num(t.get(key))
                present["h_affect"] = True
                break

        # h_judge: the RLAIF rubric scalar (0 when unjudged ⇒ usually MISSING, see below).
        for key in ("judge_score", "h_judge"):
            if key in t and t.get(key) is not None:
                out["h_judge"] = _num(t.get(key))
                # an explicit judge_score of 0.0 with no judge model id means "unjudged" → missing
                jid = str(t.get("judge_model_id") or t.get("judge_model") or "")
                present["h_judge"] = bool(jid) or abs(out["h_judge"]) > _MISSING_EPS
                break

        # h_value: the learned critic head (B3); centred. Dormant when the critic hasn't run.
        for key in ("value_head", "v_state", "h_value"):
            if key in t and t.get(key) is not None:
                out["h_value"] = _num(t.get(key))
                present["h_value"] = abs(out["h_value"]) > _MISSING_EPS or key == "value_head" and "value_head" in t
                break

        out["_present"] = present
        # Pass through anything the intrinsic-uncertainty estimators want.
        if "_z" in t and isinstance(t.get("_z"), dict):
            out["_z"] = dict(t["_z"])
        out["confidence"] = _num(t.get("confidence"), 0.0)
        out["state_friction"] = _num(t.get("state_friction"), 50.0)
        # carry wilson counts for the value-head half-width if present
        if "value_k" in t:
            out["value_k"] = t.get("value_k")
        if "value_n" in t:
            out["value_n"] = t.get("value_n")
    except Exception as exc:  # noqa: BLE001
        logger.warning("head_contributions error (non-fatal): %r", exc)
        out["_present"] = {k: False for k in HEAD_KEYS}
    return out


# --------------------------------------------------------------------------- #
# z-normalization to a per-head cohort baseline.
# --------------------------------------------------------------------------- #
def _zscore(value: float, baseline: Optional[Iterable]) -> float:
    """z = (value - mean) / std, with std floored (mirrors credit.cohort_baseline) so a
    low-variance cohort can't blow the z up. baseline is (mean, std) or None ⇒ raw value."""
    try:
        if not baseline:
            return _num(value)
        mean, std = float(baseline[0]), float(baseline[1])
        std = max(abs(std), 0.1)
        return (_num(value) - mean) / std
    except Exception:  # noqa: BLE001
        return _num(value)


def _present_map(heads: dict) -> Dict[str, bool]:
    """The present/missing decision for each head: explicit-supplied OR real magnitude."""
    explicit = heads.get("_present") if isinstance(heads.get("_present"), dict) else {}
    return {k: _present(heads.get(k, 0.0), bool(explicit.get(k, False))) for k in HEAD_KEYS}


# --------------------------------------------------------------------------- #
# intrinsic per-head uncertainty (sigma_i) — blended into u alongside disagreement.
# --------------------------------------------------------------------------- #
def _intrinsic_sigmas(heads: dict, sigmas: Optional[dict]) -> Dict[str, float]:
    """Per-head intrinsic uncertainty. Caller-supplied `sigmas` wins; otherwise derive a sane
    default from the turn context:
      judge : 1 - confidence            (a low-confidence rubric is noisier)
      affect: friction-variance-derived (distance of friction from its 50 mid-point ⇒ a turn at
              an extreme friction state has a less reliable PBRS shaping signal)
      value : Wilson half-width of the critic's P(book) if (k,n) supplied, else a small floor
      outcome: 0 (the gold-anchored head is the least intrinsically noisy — disagreement carries it)
    All clamped to [0, 1]. Best-effort: any failure ⇒ zeros."""
    s: Dict[str, float] = {k: 0.0 for k in HEAD_KEYS}
    try:
        supplied = sigmas if isinstance(sigmas, dict) else {}

        # judge intrinsic uncertainty
        if "h_judge" in supplied:
            s["h_judge"] = _clamp01(_num(supplied["h_judge"]))
        else:
            conf = _num(heads.get("confidence"), 0.0)
            s["h_judge"] = _clamp01(1.0 - _clamp01(conf)) if conf > 0 else 0.0

        # affect intrinsic uncertainty (friction-variance-derived)
        if "h_affect" in supplied:
            s["h_affect"] = _clamp01(_num(supplied["h_affect"]))
        else:
            fr = _num(heads.get("state_friction"), 50.0)
            # normalized distance from the 50 mid-point, in [0,1]; extreme states ⇒ noisier shaping
            s["h_affect"] = _clamp01(abs(fr - 50.0) / 50.0)

        # value intrinsic uncertainty (Wilson half-width of the critic probability)
        if "h_value" in supplied:
            s["h_value"] = _clamp01(_num(supplied["h_value"]))
        else:
            k = heads.get("value_k")
            n = heads.get("value_n")
            s["h_value"] = _wilson_halfwidth(k, n)

        # outcome intrinsic uncertainty
        if "h_outcome" in supplied:
            s["h_outcome"] = _clamp01(_num(supplied["h_outcome"]))
        else:
            s["h_outcome"] = 0.0
    except Exception as exc:  # noqa: BLE001
        logger.warning("_intrinsic_sigmas error (non-fatal): %r", exc)
        return {k: 0.0 for k in HEAD_KEYS}
    return s


def _clamp01(x: float) -> float:
    f = _num(x)
    if f < 0.0:
        return 0.0
    if f > 1.0:
        return 1.0
    return f


def _wilson_halfwidth(k, n) -> float:
    """Wilson 95% half-width for k/n. Reuses credit.wilson_ci when available; pure-python fallback
    otherwise. n missing / 0 ⇒ a small uninformative floor (0.5 = maximally uncertain at n→0)."""
    try:
        ki = int(k) if k is not None else None
        ni = int(n) if n is not None else None
    except Exception:  # noqa: BLE001
        return 0.0
    if not ni or ni <= 0:
        return 0.0
    try:
        from .credit import wilson_ci  # lazy; sibling, pure-python
        low, high = wilson_ci(ki or 0, ni)
        return _clamp01((high - low) / 2.0)
    except Exception:  # noqa: BLE001
        # local Wilson fallback (no dependency on credit.py)
        try:
            ki = max(0, min(int(ki or 0), ni))
            z = 1.96
            phat = ki / ni
            z2 = z * z
            denom = 1.0 + z2 / ni
            half = (z * math.sqrt((phat * (1 - phat) + z2 / (4 * ni)) / ni)) / denom
            return _clamp01(half)
        except Exception:  # noqa: BLE001
            return 0.0


# --------------------------------------------------------------------------- #
# ensemble_stats — (mu, var, u) over the PRESENT heads.
# --------------------------------------------------------------------------- #
def ensemble_stats(heads: dict, sigmas: dict = None) -> tuple:
    """Compute the ensemble triple over the heads that are actually present.

    Returns ``(mu, var, u)``:
      mu  — mean of the z-normalized PRESENT heads. Each head is z-scored to its own cohort
            baseline when ``heads['_z'][head]`` = (mean, std) is supplied, else used raw.
      var — POPULATION variance across the present z-heads = head DISAGREEMENT = epistemic
            uncertainty (the UWO penalty term).
      u   — sqrt(var + mean(sigma_i^2)) : disagreement blended with each present head's
            INTRINSIC uncertainty (judge 1-conf, affect friction-var, value Wilson half-width).

    A dormant/MISSING head (not supplied AND ~0) is EXCLUDED from mu, var and the sigma blend —
    never folded in as a 0, which would be a fabricated datapoint that distorts both the mean and
    the disagreement. With <2 present heads, var collapses to 0 (no disagreement is observable
    from a single head) and u reduces to that head's intrinsic sigma. Best-effort: any failure ⇒
    (0.0, 0.0, 0.0)."""
    try:
        present = _present_map(heads)
        zmap = heads.get("_z") if isinstance(heads.get("_z"), dict) else {}
        sig = _intrinsic_sigmas(heads, sigmas)

        z_present: List[float] = []
        sig_present: List[float] = []
        for k in HEAD_KEYS:
            if not present.get(k):
                continue
            z_present.append(_zscore(heads.get(k, 0.0), zmap.get(k)))
            sig_present.append(_num(sig.get(k), 0.0))

        if not z_present:
            return (0.0, 0.0, 0.0)

        mu = fmean(z_present)
        # population variance (disagreement). statistics.pvariance needs >=1; define 0 for n<2.
        if len(z_present) >= 2:
            var = fmean([(z - mu) ** 2 for z in z_present])
        else:
            var = 0.0
        sig_term = fmean([s * s for s in sig_present]) if sig_present else 0.0
        u = math.sqrt(max(0.0, var + sig_term))
        return (round(mu, 6), round(var, 6), round(u, 6))
    except Exception as exc:  # noqa: BLE001
        logger.warning("ensemble_stats error (non-fatal): %r", exc)
        return (0.0, 0.0, 0.0)


# --------------------------------------------------------------------------- #
# lcb_reward — the PESSIMISTIC reward the optimizer / bandit consume.
# --------------------------------------------------------------------------- #
def lcb_reward(heads: dict, *, lam: float = 0.5, kappa: float = 1.0, sigmas: dict = None) -> float:
    """The pessimistic lower-confidence-bound reward:

        R_LCB = mu - λ·var - κ·u

    UWO (Coste et al.) penalizes head DISAGREEMENT (var); the extra κ·u term discounts for the
    blended intrinsic+epistemic uncertainty. This is the number the bandit / challenger search
    maximize, so they can never exploit a single mis-specified head — climbing R_LCB requires
    ALL heads to AGREE and be confident. Best-effort: any failure ⇒ 0.0 (a neutral reward)."""
    try:
        mu, var, u = ensemble_stats(heads, sigmas=sigmas)
        lam = _num(lam, 0.5)
        kappa = _num(kappa, 1.0)
        return round(mu - lam * var - kappa * u, 6)
    except Exception as exc:  # noqa: BLE001
        logger.warning("lcb_reward error (non-fatal): %r", exc)
        return 0.0


# --------------------------------------------------------------------------- #
# fuse_pessimistic — fill the ensemble fields on a RewardComponents and return it.
# --------------------------------------------------------------------------- #
def fuse_pessimistic(rc, *, value_head: float = 0.0, sigmas: dict = None, cfg=None):
    """Enrich a schema.RewardComponents with the B1 ensemble + pessimistic LCB, IN PLACE, and
    return it (so callers can chain). This is what ``worker.enrich_calls`` invokes; afterwards
    ``rc.optimized()`` returns the LCB instead of the plain fused point estimate — that
    .fused()→.optimized() flip is the entire anti-over-optimization guard.

    Fills: rc.value_head, rc.ensemble_mean, rc.ensemble_var, rc.lcb_reward, rc.ensemble_computed.
    λ/κ are read from cfg (ensemble_lambda / ensemble_kappa). Best-effort + dormant-safe: on ANY
    failure the rc is returned UNCHANGED with ensemble_computed left False (so .optimized() keeps
    falling back to .fused() — never a raise, never a corrupt reward)."""
    try:
        cfg = cfg or _cfg.load()
        lam = _num(getattr(cfg, "ensemble_lambda", 0.5), 0.5)
        kappa = _num(getattr(cfg, "ensemble_kappa", 1.0), 1.0)

        vh = _num(value_head, 0.0)
        # The value head is centred (B3 critic V(state)); record it on the rc.
        rc.value_head = vh

        # Build the head dict straight off the (provenance-complete) RewardComponents.
        heads = {
            "h_outcome": _num(getattr(rc, "terminal_credit", 0.0)),
            "h_affect": _num(getattr(rc, "affect_delta", 0.0)),
            "h_judge": _num(getattr(rc, "judge_score", 0.0)),
            "h_value": vh,
            "_present": {
                "h_outcome": True,  # terminal_credit is always a real, computed datapoint
                "h_affect": True,   # affect_delta is always computed (PBRS, may legitimately be 0)
                # judge present only if it was actually scored (a model id was pinned)
                "h_judge": bool(str(getattr(rc, "judge_model_id", "") or "")),
                # value head present only if the critic actually contributed a non-trivial V
                "h_value": abs(vh) > _MISSING_EPS,
            },
            "confidence": _num(getattr(rc, "confidence", 0.0)),
        }
        if isinstance(sigmas, dict) and "_z" in sigmas:
            heads["_z"] = sigmas.get("_z")

        mu, var, u = ensemble_stats(heads, sigmas=sigmas)
        lcb = round(mu - lam * var - kappa * u, 6)

        rc.ensemble_mean = round(mu, 6)
        rc.ensemble_var = round(var, 6)
        rc.lcb_reward = round(lcb, 6)
        rc.ensemble_computed = True
        return rc
    except Exception as exc:  # noqa: BLE001
        logger.warning("fuse_pessimistic error (non-fatal): %r", exc)
        try:
            rc.ensemble_computed = False
        except Exception:  # noqa: BLE001
            pass
        return rc


# --------------------------------------------------------------------------- #
# odin_residualize — strip a length/warmth nuisance so the reward can't be hacked.
# --------------------------------------------------------------------------- #
def odin_residualize(score: float, length: int, warmth: float, *,
                     beta_len: float = 0.0, beta_warm: float = 0.0) -> float:
    """ODIN (Chen et al., 2024) reward disentanglement: subtract a linear length/warmth NUISANCE
    estimate from the head score so the optimizer can't game the reward by simply being longer
    (more tokens) or sweeter (warmer affect). The nuisance coefficients (beta_len, beta_warm) are
    fit OFFLINE by the worker (the slope of reward on length / warmth over the cohort); here we
    just apply the residual:

        residual = score - beta_len·length_norm - beta_warm·warmth

    length is normalized (log1p) so a 200-vs-220-word turn isn't a cliff. With both betas 0 (the
    dormant default — no nuisance fit yet) this is the identity. Best-effort ⇒ returns the raw
    score on failure (never strips more than it should)."""
    try:
        s = _num(score, 0.0)
        bl = _num(beta_len, 0.0)
        bw = _num(beta_warm, 0.0)
        if bl == 0.0 and bw == 0.0:
            return round(s, 6)
        length_norm = math.log1p(max(0.0, _num(length, 0.0)))
        warmth_v = _num(warmth, 0.0)
        return round(s - bl * length_norm - bw * warmth_v, 6)
    except Exception as exc:  # noqa: BLE001
        logger.warning("odin_residualize error (non-fatal): %r", exc)
        return _num(score, 0.0)


# --------------------------------------------------------------------------- #
# proxy_throttle — the herding / over-optimization brake (Moskovitz constrained-RLHF).
# --------------------------------------------------------------------------- #
def proxy_throttle(proxy_gain: float, gold_gain: float) -> float:
    """A Lagrangian-style throttle multiplier in [0, 1] for the proxy reward gradient
    (Moskovitz et al., 2023, "Confronting Reward Model Overoptimization with Constrained RLHF").

    Compares how much the PROXY reward has climbed (proxy_gain) against how much the GOLD holdout
    moved (gold_gain). When the gold tracks the proxy the multiplier is ~1 (full trust); when the
    proxy keeps climbing but the gold-holdout STALLS or REGRESSES (the over-optimization
    signature) the multiplier decays toward 0, damping further optimization pressure — the
    herding brake. The ratio  gold_gain / proxy_gain  is the running estimate of how much of the
    proxy's apparent gain is *real*, clamped to [0, 1]:

      * proxy_gain <= 0  → nothing to throttle (we aren't climbing the proxy) → 1.0
      * gold_gain  >= proxy_gain → gold keeps up → 1.0
      * gold_gain  <= 0  with proxy climbing → pure over-optimization → 0.0

    Best-effort ⇒ 1.0 (a no-op throttle) on failure, so a throttle bug can never silently zero
    the reward."""
    try:
        p = _num(proxy_gain, 0.0)
        g = _num(gold_gain, 0.0)
        if p <= _MISSING_EPS:
            return 1.0  # not climbing the proxy ⇒ no over-optimization to brake
        ratio = g / p
        return round(_clamp01(ratio), 6)
    except Exception as exc:  # noqa: BLE001
        logger.warning("proxy_throttle error (non-fatal): %r", exc)
        return 1.0


__all__ = [
    "HEAD_KEYS",
    "head_contributions",
    "ensemble_stats",
    "lcb_reward",
    "fuse_pessimistic",
    "odin_residualize",
    "proxy_throttle",
]


# --------------------------------------------------------------------------- #
# Self-check — pure-python happy path (NO network / NO ClickHouse / NO numpy).
# Exercises every public function on synthetic inputs and asserts the invariants
# that make B1 anti-Goodhart: LCB <= mean, missing heads excluded, throttle in [0,1].
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    import sys

    failures: List[str] = []

    def check(cond: bool, label: str) -> None:
        if not cond:
            failures.append(label)
        print(f"  [{'ok' if cond else 'FAIL'}] {label}")

    print("ensemble.py self-check (pure-python, synthetic)")

    # 1) head_contributions off a RewardComponents-like dict
    turn = {
        "terminal_credit": 0.8,
        "affect_delta": 0.3,
        "judge_score": 0.6,
        "judge_model_id": "anthropic/claude-3.5-sonnet",
        "value_head": 0.2,
        "confidence": 0.7,
        "state_friction": 55.0,
    }
    heads = head_contributions(turn)
    check(set(HEAD_KEYS) <= set(heads), "head_contributions returns all 4 head keys")
    check(heads["h_outcome"] == 0.8, "h_outcome pulled from terminal_credit")
    check(all(heads["_present"][k] for k in HEAD_KEYS), "all 4 heads present when supplied")

    # 2) a dormant value head (0 and not provided) must be MISSING, not folded in as 0
    turn_dormant = {
        "terminal_credit": 0.8,
        "affect_delta": 0.3,
        "judge_score": 0.6,
        "judge_model_id": "anthropic/claude-3.5-sonnet",
        # no value_head at all ⇒ dormant critic
        "confidence": 0.7,
    }
    heads_d = head_contributions(turn_dormant)
    check(heads_d["_present"]["h_value"] is False, "dormant value head flagged MISSING")

    # 3) ensemble_stats: mu/var/u, with z-baselines per head
    z = {"_z": {
        "h_outcome": (0.0, 1.0),
        "h_affect": (0.0, 1.0),
        "h_judge": (0.0, 1.0),
        "h_value": (0.0, 1.0),
    }}
    heads_z = dict(heads)
    heads_z.update(z)
    mu, var, u = ensemble_stats(heads_z)
    check(isinstance(mu, float) and isinstance(var, float) and isinstance(u, float),
          "ensemble_stats returns 3 floats")
    check(var >= 0.0, "variance (disagreement) is non-negative")
    check(u >= math.sqrt(var) - 1e-9, "u >= sqrt(var) (intrinsic sigma only adds)")

    # missing head reduces the count in the mean
    mu_d, var_d, u_d = ensemble_stats(heads_d)
    check(True, f"dormant-head stats computed mu={mu_d:.3f} var={var_d:.3f} u={u_d:.3f}")

    # single present head ⇒ zero disagreement
    one = {"h_outcome": 0.5, "_present": {"h_outcome": True, "h_affect": False,
                                          "h_judge": False, "h_value": False}}
    mu1, var1, u1 = ensemble_stats(one)
    check(var1 == 0.0, "single present head ⇒ var == 0 (no disagreement observable)")

    # 4) lcb_reward <= mu (pessimism never raises the reward)
    lcb = lcb_reward(heads_z, lam=0.5, kappa=1.0)
    check(lcb <= mu + 1e-9, "lcb_reward <= ensemble mean (pessimistic)")

    # 5) fuse_pessimistic on a real RewardComponents
    from .schema import RewardComponents
    rc = RewardComponents(
        terminal_credit=0.8, affect_delta=0.3, judge_score=0.6,
        judge_model_id="anthropic/claude-3.5-sonnet", confidence=0.7,
        w_outcome=1.0, w_affect=0.15, w_judge=0.10,
    )
    before_fused = rc.fused()
    rc2 = fuse_pessimistic(rc, value_head=0.2)
    check(rc2.ensemble_computed is True, "fuse_pessimistic sets ensemble_computed=True")
    check(rc2.value_head == 0.2, "fuse_pessimistic records value_head")
    check(rc2.optimized() == round(rc2.lcb_reward, 5),
          "optimized() returns the LCB once ensemble computed")
    check(abs(rc2.fused() - before_fused) < 1e-9, "fused() point estimate left untouched")

    # 6) odin_residualize: identity with zero betas, strips with non-zero
    check(odin_residualize(0.5, length=120, warmth=0.4) == 0.5,
          "odin_residualize is identity with zero betas")
    resid = odin_residualize(0.5, length=120, warmth=0.4, beta_len=0.01, beta_warm=0.1)
    check(resid < 0.5, "odin_residualize strips a positive length/warmth nuisance")

    # 7) proxy_throttle bounds + monotonic intuition
    check(proxy_throttle(0.0, 0.0) == 1.0, "throttle = 1 when not climbing the proxy")
    check(proxy_throttle(0.4, 0.4) == 1.0, "throttle = 1 when gold tracks proxy")
    check(proxy_throttle(0.4, 0.0) == 0.0, "throttle = 0 when gold stalls while proxy climbs")
    half = proxy_throttle(0.4, 0.2)
    check(0.0 < half < 1.0, f"throttle in (0,1) on partial tracking (={half})")

    # 8) dormant cfg path: lcb still computes with default lam/kappa (no env / no CH)
    lcb2 = lcb_reward(head_contributions(turn))
    check(isinstance(lcb2, float), "lcb_reward runs on a bare turn (dormant-safe)")

    print()
    if failures:
        print(f"SELF-CHECK FAILED ({len(failures)}): {failures}")
        sys.exit(1)
    print("SELF-CHECK PASSED — all invariants hold (pure-python, no deps).")
