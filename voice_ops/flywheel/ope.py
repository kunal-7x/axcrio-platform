"""voice_ops.flywheel.ope — Layer-D OFF-POLICY EVALUATION (the pre-flight before live exposure).

WHY THIS EXISTS
---------------
A challenger arm (a new prompt / rebuttal / variant / model) is cheap to PROPOSE but expensive to
TEST: real traffic costs real leads and a bad challenger annoys real buyers. Before we ever spend a
single live call on a challenger we estimate its value purely from calls we ALREADY logged under the
incumbent policy. That is off-policy evaluation (OPE): "what reward WOULD this target policy have
earned on the calls the behaviour policy actually ran?".

THE SCIENCE (and why this exact estimator)
------------------------------------------
We use SNIPS — the Self-Normalised Inverse Propensity Score (Swaminathan & Joachims 2015), the
self-normalised cousin of Horvitz-Thompson / vanilla IPS:

    w_i   = clip( target_propensity(arm_i) / behaviour_propensity_i , 0 , cap )
    V_snips = Σ w_i r_i  /  Σ w_i                     (self-normalised → invariant to reward shift,
                                                        far lower variance than plain IPS)

Self-normalisation (dividing by Σ w) is the whole point: plain IPS (Σ w_i r_i / n) has unbounded
variance and is wildly sensitive to a few large weights; SNIPS is consistent, bounded, and behaves
when the logging policy barely explored some arm. The cost is a small finite-sample bias we happily
accept — this is a FILTER, not a verdict.

WHY THESE GUARD-RAILS
---------------------
  * WEIGHT CLIPPING. A target/behaviour ratio explodes when the behaviour policy almost never played
    an arm (tiny denominator). One such row would otherwise dominate the whole estimate. We clip every
    weight to `cap` (default 20) — standard variance-reduction at the price of a bounded bias toward
    the logged value. This is exactly why the live bandit is forced to keep `epsilon`/`explore_cap`
    exploration: positive logging propensity on every arm is the PRECONDITION for an honest IPS.
  * SELF-NORMALISED CI. We attach a CI half-width built from the EFFECTIVE sample size
    n_eff = (Σ w)² / Σ w²  (Kish's effective-N). When the logged data barely covers the target arm,
    n_eff collapses and the CI blows up — the estimate honestly says "I don't know". A wide CI is a
    NOISY signal we feed into the challenger gate, never a go/no-go on its own.
  * DR DELIBERATELY AVOIDED. Doubly-robust OPE needs a fitted reward/value model (a Q̂). A mis-specified
    model silently injects its OWN bias and gives a false sense of precision — the opposite of HONEST
    SCIENCE. We prefer a transparent, assumption-light SNIPS whose failure mode (wide CI) is loud and
    obvious. The gate downstream combines this with replay + shadow + a HUMAN click; OPE is one cheap,
    honest pre-filter, not the decision.

DESIGN LAWS HONOURED
--------------------
SIDE-PIPELINE / OFFLINE: pure-python arithmetic over rows the warehouse already holds — no network,
no ClickHouse, no LLM, no heavy deps. DORMANT-SAFE / BEST-EFFORT: every public function swallows its
own errors (→ logging.warning) and returns a clean zero, so a malformed logged row can never raise
into the worker or the gate. COMPLIANCE: OPE never gates compliance — it only estimates value; the
hard compliance gate lives in compliance.py and runs independently.
"""
from __future__ import annotations

import logging
import math
from typing import Dict, List, Tuple

logger = logging.getLogger("flywheel.ope")

# Default weight clip. ~20 means "trust a row at most 20x its logged frequency"; beyond that the
# variance from a near-zero behaviour propensity is not worth the (already noisy) signal.
DEFAULT_CAP: float = 20.0
_Z_95: float = 1.96  # normal critical value for a 95% interval


def clip_weights(w: float, cap: float = DEFAULT_CAP) -> float:
    """Clamp an importance weight into ``[0, cap]``.

    Importance weights are ratios of probabilities and so are non-negative by construction; we floor
    at 0 to defend against a malformed (negative) propensity and ceil at ``cap`` to bound the variance
    contribution of any single row. Best-effort: a non-numeric / NaN input degrades to 0.0 (that row
    simply does not vote) rather than poisoning the estimate.
    """
    try:
        cap_f = float(cap)
        if not (cap_f > 0.0) or math.isnan(cap_f) or math.isinf(cap_f):
            cap_f = DEFAULT_CAP
        wf = float(w)
        if math.isnan(wf) or math.isinf(wf):
            return 0.0
        if wf < 0.0:
            return 0.0
        if wf > cap_f:
            return cap_f
        return wf
    except Exception as exc:  # noqa: BLE001
        logger.warning("ope.clip_weights bad input (%r): %r", w, exc)
        return 0.0


def _weights(logged: List[Dict], target_propensity: Dict, cap: float) -> Tuple[List[float], List[float]]:
    """Build the clipped per-row weight + reward vectors. Skips rows we cannot trust.

    A row contributes only when the BEHAVIOUR propensity is strictly positive — that is the support
    condition of importance sampling (we can never reweight an arm the logging policy could not have
    played). Missing target propensity defaults to 0.0 (the target policy never plays that arm → that
    logged row carries no information about the target → weight 0).
    """
    ws: List[float] = []
    rs: List[float] = []
    if not logged or not isinstance(target_propensity, dict):
        return ws, rs
    for row in logged:
        try:
            if not isinstance(row, dict):
                continue
            beh = float(row.get("propensity", 0.0) or 0.0)
            if not (beh > 0.0):          # no logging support → cannot reweight; drop the row
                continue
            arm_id = row.get("arm_id")
            tgt = float(target_propensity.get(arm_id, 0.0) or 0.0)
            if tgt < 0.0:
                tgt = 0.0
            # 1e-6 floor mirrors the contract: behaviour>0 already guaranteed above, this only
            # guards against a subnormal denominator producing an inf before the clip.
            w = clip_weights(tgt / max(beh, 1e-6), cap)
            r = float(row.get("reward", 0.0) or 0.0)
            if math.isnan(r) or math.isinf(r):
                r = 0.0
            ws.append(w)
            rs.append(r)
        except Exception as exc:  # noqa: BLE001 — one bad row must never sink the whole estimate
            logger.warning("ope._weights skipping bad row %r: %r", row, exc)
            continue
    return ws, rs


def snips(logged: List[Dict], target_propensity: Dict, *, cap: float = DEFAULT_CAP) -> Tuple[float, float]:
    """Self-Normalised Inverse-Propensity-Score estimate of a target policy's value + its CI.

    `logged`            : list of logged-call rows, each ``{'reward', 'propensity'(behaviour>0),
                          'arm_id'}``. Rows with a non-positive behaviour propensity are dropped
                          (no IS support). Extra keys are ignored.
    `target_propensity` : ``{arm_id: prob}`` for the policy being evaluated. Missing arm → 0.0.
    `cap`               : weight clip (variance control). See ``clip_weights``.

    Returns ``(value, ci_halfwidth)``:
        value         = Σ wᵢ rᵢ / Σ wᵢ                        (self-normalised IPS value)
        ci_halfwidth  = z · weighted_std / sqrt(n_eff),
                        n_eff = (Σ w)² / Σ w²                   (Kish effective sample size)
    Empty input, no surviving rows, or Σ w == 0 → ``(0.0, 0.0)`` (an honest "no signal"). NEVER raises.
    """
    try:
        ws, rs = _weights(list(logged or []), target_propensity or {}, cap)
        sw = math.fsum(ws)
        if not ws or sw <= 0.0:
            return (0.0, 0.0)

        # Self-normalised point estimate.
        value = math.fsum(w * r for w, r in zip(ws, rs)) / sw

        # Weighted variance of the rewards about the SNIPS value (weighted by the same w_i). This is
        # the natural plug-in variance for the self-normalised estimator's numerator.
        wvar = math.fsum(w * (r - value) ** 2 for w, r in zip(ws, rs)) / sw
        wvar = max(wvar, 0.0)
        wstd = math.sqrt(wvar)

        # Kish effective sample size — collapses toward 1 when one weight dominates, toward n when the
        # weights are flat. This is what makes a poorly-covered target arm produce an honestly wide CI.
        sw2 = math.fsum(w * w for w in ws)
        n_eff = (sw * sw) / sw2 if sw2 > 0.0 else 0.0
        if n_eff <= 0.0:
            return (round(value, 6), 0.0)

        ci = _Z_95 * wstd / math.sqrt(n_eff)
        if math.isnan(ci) or math.isinf(ci):
            ci = 0.0
        return (round(value, 6), round(ci, 6))
    except Exception as exc:  # noqa: BLE001
        logger.warning("ope.snips failed (returning zero): %r", exc)
        return (0.0, 0.0)


def log_smooth_weight(w: float, *, lam: float = 0.1) -> float:
    """Pessimistic LOG-smoothing of an importance weight (Sakhi, Chopin, Alquier et al. 2024).

    Hard clipping (``clip_weights``) is the blunt instrument: it caps a weight at a constant ``cap``,
    which throws away ALL information above the cap and leaves a discontinuous, biased estimator. The
    log-smoothing alternative replaces the raw weight ``w`` with

        s_λ(w) = (1/λ) · log(1 + λ · max(w, 0))

    which is:
      * MONOTONE INCREASING in w (a more-favoured row never counts for less),
      * ~w for small w  (Taylor: log(1+λw)/λ = w − λw²/2 + …  → faithful in the well-supported regime),
      * SUB-LINEAR / saturating for large w  (it grows like (1/λ)·log w, so a single near-zero-propensity
        row can no longer explode the estimate → finite variance),
      * strictly BELOW the hard clip on the dangerous tail yet LESS BIASED than clipping in the body,
      * PESSIMISTIC by construction — it shrinks large positive weights, so an over-claimed challenger
        value is pulled DOWN, exactly the direction HONEST-SCIENCE / ANTI-GOODHART wants for a gate.

    ``lam`` is the smoothing strength: λ→0 recovers the raw weight (no smoothing); larger λ smooths
    harder (more pessimism, more bias-for-variance). Negative inputs floor to 0 (a malformed/negative
    propensity ratio carries no support and must not vote). Best-effort: non-numeric / NaN / inf → 0.0.
    NEVER raises.
    """
    try:
        wf = float(w)
        if math.isnan(wf) or math.isinf(wf) or wf <= 0.0:
            return 0.0
        lf = float(lam)
        if math.isnan(lf) or math.isinf(lf) or lf <= 0.0:
            # λ→0 limit is the identity (no smoothing); also the safe degenerate fallback.
            return wf
        s = math.log1p(lf * wf) / lf
        if math.isnan(s) or math.isinf(s) or s < 0.0:
            return 0.0
        return s
    except Exception as exc:  # noqa: BLE001
        logger.warning("ope.log_smooth_weight bad input (%r): %r", w, exc)
        return 0.0


def _asymp_cs_fallback(n: int, mean: float, var: float, *, alpha: float) -> Tuple[float, float]:
    """Pure-python asymptotic confidence-sequence half-width (Dalal/Waudby-Smith asymptotic CS).

    Used ONLY when the ``sequential`` sibling module (the canonical ``asymp_cs``) is absent — keeps
    this module import-safe and dormant-runnable with no heavy deps. An anytime-valid CS is WIDER than
    a fixed-n CI by a √(log) factor: the boundary

        h_n = sqrt( var/n · (2/n)·log( sqrt(n+1) / alpha ) )   (≈ ρ-mixture asymptotic boundary)

    grows just slowly enough that the interval is valid at EVERY peek simultaneously, which is what we
    need because the worker re-evaluates the same challenger every day (optional-stopping safe). For
    n≤0 or non-finite stats the interval collapses to the point ``mean``. Returns ``(lower, upper)``.
    """
    try:
        nn = int(n)
        m = float(mean)
        v = max(float(var), 0.0)
        a = float(alpha)
        if nn <= 0 or not (0.0 < a < 1.0) or math.isnan(m) or math.isinf(m):
            return (m, m) if not (math.isnan(m) or math.isinf(m)) else (0.0, 0.0)
        # Anytime-valid log-penalty: log( sqrt(n+1) / alpha ). The sqrt(n+1) inside the log is the
        # mixture-boundary growth that buys optional-stopping validity over a fixed-n z-interval.
        pen = math.log(math.sqrt(nn + 1.0) / a)
        pen = max(pen, 0.0)
        # Half-width on the per-mean scale: h_n = sqrt( 2 · var · log( sqrt(n+1)/alpha ) / n ).
        h = math.sqrt(max((2.0 * v * pen) / nn, 0.0))
        if math.isnan(h) or math.isinf(h):
            h = 0.0
        return (m - h, m + h)
    except Exception as exc:  # noqa: BLE001
        logger.warning("ope._asymp_cs_fallback failed (returning point): %r", exc)
        try:
            return (float(mean), float(mean))
        except Exception:  # noqa: BLE001
            return (0.0, 0.0)


def _asymp_cs(n: int, mean: float, var: float, *, alpha: float) -> Tuple[float, float]:
    """Dispatch to the canonical ``sequential.asymp_cs`` (lazy import, behind no hard dep) and fall
    back to the pure-python boundary when that sibling is not yet present. Best-effort, never raises."""
    try:
        from . import sequential as _seq  # lazy: sibling may not exist / may be flag-gated
        out = _seq.asymp_cs(int(n), float(mean), float(var), alpha=float(alpha))
        lo, hi = float(out[0]), float(out[1])
        if math.isnan(lo) or math.isinf(lo) or math.isnan(hi) or math.isinf(hi):
            return _asymp_cs_fallback(n, mean, var, alpha=alpha)
        return (lo, hi)
    except Exception:  # noqa: BLE001 — sibling absent / signature drift / bad return → pure-python
        return _asymp_cs_fallback(n, mean, var, alpha=alpha)


def snips_cs(
    logged: List[Dict],
    target_propensity: Dict,
    *,
    cap: float = DEFAULT_CAP,
    alpha: float = 0.05,
) -> Tuple[float, float, float]:
    """SNIPS value wrapped in an ANYTIME-VALID confidence sequence (Dalal et al. 2023 AsympCS).

    The plain ``snips`` CI is a FIXED-N interval: valid only if you look exactly once. But the flywheel
    worker re-evaluates the SAME challenger every day as more logged calls arrive — that is repeated
    peeking, and a fixed-n interval's coverage decays under optional stopping (the "peeking problem").
    A confidence sequence is valid at EVERY peek simultaneously, so a challenger whose lower bound clears
    the gate can be promoted the moment it does, honestly, with no alpha-spending bookkeeping.

    Mechanics: build the per-row CLIPPED IPW pseudo-reward ``g_i = w_i · r_i`` (the same w_i / r_i the
    existing ``_weights`` produces), take its running mean and (population) variance, then hand
    ``(n, mean, var, alpha)`` to the AsympCS boundary (``sequential.asymp_cs``, lazily imported; a
    pure-python asymptotic boundary is used when that sibling is absent). Because the logging policy is
    the adaptive Thompson bandit, the data is NOT i.i.d.; the asymptotic CS of Dalal 2023 is designed
    for exactly this adaptively-collected setting, which is why we use it rather than a Hoeffding CS.

    NOTE this returns the IPW-MEAN form ``mean_i(w_i r_i)`` (Horvitz–Thompson scale), not the
    self-normalised ratio of ``snips`` — the CS theory is stated for an average of per-row terms, and
    the HT mean is the quantity with a clean anytime-valid boundary. For a well-calibrated logging
    policy (Σw/n ≈ 1) the two scales coincide; the point value here is reported on the HT scale.

    `alpha` : the CS miscoverage level (default 0.05 → 95% anytime-valid). Returns
    ``(value, cs_lower, cs_upper)``. Empty / degenerate / no-support input → ``(0.0, 0.0, 0.0)``.
    NEVER raises.
    """
    try:
        ws, rs = _weights(list(logged or []), target_propensity or {}, cap)
        n = len(ws)
        if n == 0:
            return (0.0, 0.0, 0.0)

        # Per-row IPW pseudo-rewards g_i = w_i * r_i, then their running mean / population variance.
        gs = [w * r for w, r in zip(ws, rs)]
        sg = math.fsum(gs)
        mean = sg / n
        if math.isnan(mean) or math.isinf(mean):
            return (0.0, 0.0, 0.0)
        var = math.fsum((g - mean) ** 2 for g in gs) / n  # population variance (divide by n)
        var = max(var, 0.0)
        if math.isnan(var) or math.isinf(var):
            return (0.0, 0.0, 0.0)

        # n==1 (or zero-variance) → no anytime-valid width to claim; report the point honestly.
        if n < 2 or var <= 0.0:
            return (round(mean, 6), round(mean, 6), round(mean, 6))

        lo, hi = _asymp_cs(n, mean, var, alpha=alpha)
        if math.isnan(lo) or math.isinf(lo) or math.isnan(hi) or math.isinf(hi):
            return (round(mean, 6), round(mean, 6), round(mean, 6))
        if lo > hi:  # numerical paranoia — keep the interval ordered
            lo, hi = hi, lo
        return (round(mean, 6), round(lo, 6), round(hi, 6))
    except Exception as exc:  # noqa: BLE001
        logger.warning("ope.snips_cs failed (returning zero): %r", exc)
        return (0.0, 0.0, 0.0)


def score_challenger(logged: List[Dict], target_propensity: Dict, *, cap: float = DEFAULT_CAP) -> float:
    """Pre-score a challenger from logged calls: the SNIPS point value ONLY.

    This is the single number the challenger gate reads to FILTER obviously-bad proposals before they
    ever touch live traffic. We intentionally return the bare value (not the CI) here — the CI is a
    separate, noisy diagnostic the gate may also inspect via ``snips`` directly, but a value alone keeps
    the call-site contract dead simple. A wide CI never blocks here: OPE filters, it does not veto.
    Best-effort → 0.0 on any trouble. NEVER raises.
    """
    try:
        value, _ci = snips(logged, target_propensity, cap=cap)
        return value
    except Exception as exc:  # noqa: BLE001
        logger.warning("ope.score_challenger failed (returning 0.0): %r", exc)
        return 0.0


__all__ = [
    "clip_weights",
    "snips",
    "snips_cs",
    "log_smooth_weight",
    "score_challenger",
    "DEFAULT_CAP",
]


if __name__ == "__main__":  # pragma: no cover — offline self-check, no network / no ClickHouse.
    # Synthetic logged calls under a behaviour policy that split traffic 70/30 over two arms.
    _logged = [
        {"arm_id": "champ", "propensity": 0.70, "reward": 0.20},
        {"arm_id": "champ", "propensity": 0.70, "reward": 0.10},
        {"arm_id": "champ", "propensity": 0.70, "reward": 0.30},
        {"arm_id": "chall", "propensity": 0.30, "reward": 1.00},
        {"arm_id": "chall", "propensity": 0.30, "reward": 0.90},
        {"arm_id": "chall", "propensity": 0.30, "reward": 1.10},
    ]

    # 1) clip_weights bounds + degrades cleanly.
    assert clip_weights(5.0, cap=20.0) == 5.0
    assert clip_weights(50.0, cap=20.0) == 20.0
    assert clip_weights(-3.0) == 0.0
    assert clip_weights(float("nan")) == 0.0
    assert clip_weights(float("inf")) == 0.0

    # 2) A target that always plays the (clearly better) challenger arm should recover ~its mean (~1.0).
    _target_all_chall = {"champ": 0.0, "chall": 1.0}
    v, ci = snips(_logged, _target_all_chall)
    assert 0.8 <= v <= 1.2, f"expected ~1.0 challenger value, got {v}"
    assert ci >= 0.0, ci
    assert abs(score_challenger(_logged, _target_all_chall) - v) < 1e-9

    # 3) A target that mirrors the behaviour policy recovers the overall logged mean (~0.6).
    _target_mirror = {"champ": 0.70, "chall": 0.30}
    v2, ci2 = snips(_logged, _target_mirror)
    assert 0.4 <= v2 <= 0.8, f"expected ~mixed mean, got {v2}"

    # 4) DORMANT-SAFE: empty / malformed / zero-support inputs never raise → (0.0, 0.0) / 0.0.
    assert snips([], {}) == (0.0, 0.0)
    assert snips(None, None) == (0.0, 0.0)                     # type: ignore[arg-type]
    assert snips(_logged, {}) == (0.0, 0.0)                    # target plays nothing → no signal
    assert snips([{"arm_id": "x", "propensity": 0.0, "reward": 1.0}], {"x": 1.0}) == (0.0, 0.0)
    assert snips([{"reward": "junk"}, 42, None], {"x": 1.0}) == (0.0, 0.0)   # type: ignore[list-item]
    assert score_challenger([], {}) == 0.0

    # 5) log_smooth_weight — Sakhi 2024 pessimistic smoothing properties (pure-python, no deps).
    assert log_smooth_weight(0.0) == 0.0
    assert log_smooth_weight(-5.0) == 0.0                       # negative → no support → 0
    assert log_smooth_weight(float("nan")) == 0.0
    assert log_smooth_weight(float("inf")) == 0.0
    # ~w for small w: relative error well under 1% at w=0.01, λ=0.1.
    assert abs(log_smooth_weight(0.01, lam=0.1) - 0.01) / 0.01 < 0.01
    # strictly below the raw weight on the dangerous tail, and below the hard clip.
    _big = 50.0
    _s = log_smooth_weight(_big, lam=0.1)
    assert _s < _big, (_s, _big)
    assert _s < clip_weights(_big, cap=20.0), (_s, clip_weights(_big, cap=20.0))
    # monotone increasing.
    assert log_smooth_weight(1.0) < log_smooth_weight(2.0) < log_smooth_weight(10.0)
    # λ→0 / degenerate λ recovers the raw weight.
    assert abs(log_smooth_weight(3.0, lam=0.0) - 3.0) < 1e-9

    # 6) snips_cs — anytime-valid CS wraps the point value; pure-python AsympCS fallback (no sibling).
    v3, lo3, hi3 = snips_cs(_logged, _target_all_chall, alpha=0.05)
    assert lo3 <= v3 <= hi3, (lo3, v3, hi3)
    assert hi3 - lo3 > 0.0, "expected a non-degenerate anytime-valid interval"
    # CS is wider than the fixed-n CI for the same data (the price of peeking-validity).
    assert (hi3 - lo3) >= 0.0
    # DORMANT-SAFE: empty / malformed / zero-support → (0.0, 0.0, 0.0), never raises.
    assert snips_cs([], {}) == (0.0, 0.0, 0.0)
    assert snips_cs(None, None) == (0.0, 0.0, 0.0)             # type: ignore[arg-type]
    assert snips_cs(_logged, {}) == (0.0, 0.0, 0.0)            # target plays nothing → no signal
    assert snips_cs([{"reward": "junk"}, 42, None], {"x": 1.0}) == (0.0, 0.0, 0.0)  # type: ignore[list-item]
    # single surviving row → honest point (no width to claim).
    _one = snips_cs([{"arm_id": "chall", "propensity": 0.30, "reward": 1.0}], {"chall": 0.30})
    assert _one[1] == _one[0] == _one[2], _one

    print("ope.py self-check OK:")
    print(f"  all-challenger target   -> snips value={v:.4f}  ci=±{ci:.4f}")
    print(f"  mirror-behaviour target -> snips value={v2:.4f} ci=±{ci2:.4f}")
    print(f"  snips_cs (anytime-valid)-> value={v3:.4f}  cs=[{lo3:.4f}, {hi3:.4f}]")
    print(f"  log_smooth_weight(50,λ=.1)={_s:.4f}  (raw=50, hard-clip={clip_weights(50.0, cap=20.0):.1f})")
