"""voice_ops.flywheel.sequential — B2 ALWAYS-VALID (anytime) sequential promotion test.

WHY THIS EXISTS
---------------
An operator wants to PEEK at a challenger's scoreboard every day and stop the moment it has clearly
won (or clearly lost). A classical fixed-horizon test (a one-shot z-test / Welch t) is INVALID under
that workflow: each extra look is another chance to cross the threshold by noise, so daily peeking at
alpha=0.05 silently inflates the real type-I error toward ~1.0 ("peeking" / optional-stopping bias).
That is the single most common way an A/B program ships a regression that "looked significant".

The fix is a CONFIDENCE SEQUENCE (CS): an interval CS_t that is valid SIMULTANEOUSLY at every t —
formally P(exists t : mu not in CS_t) <= alpha. Because coverage holds uniformly over time, the
operator may look as often as they like, stop whenever they like, and the guarantee still holds.
Promotion = the challenger's CS_lower clears the champion's CS_upper (LUCB-style separation), AND the
lift exceeds a minimum PRACTICAL delta (statistical != worth-the-risk). This is the only path by
which the bandit/optimizer hand a candidate to the human promote button.

THE SCIENCE (and why these exact constructions)
-----------------------------------------------
  * BETTING confidence sequence (Waudby-Smith & Ramdas, "Estimating means of bounded random
    variables by betting", JRSS-B 2024). For a bounded mean we run a hypothesis test by BETTING: for
    each candidate mean m we accumulate "capital" by wagering a predictable fraction lambda_i on each
    new observation. If m is the true mean the wealth is a non-negative martingale with expectation
    1, so by Ville's inequality it exceeds 1/alpha only with probability <= alpha. We therefore KEEP
    every m whose log-wealth stays below log(1/alpha); the surviving set is an (1-alpha) CS. We use
    the variance-adaptive predictable lambda of WSR (aGRAPA-style): lambda_i tracks
    (mu_hat - m)/(sigma2_hat + eps) from data seen BEFORE row i (predictability is what preserves the
    martingale), clipped to a hedged range. This CS is the tightest of the family for bounded data
    and is exactly suited to our [-1, cap] capped rewards / {0,1} opt-outs.
  * AsympCS — the closed-form asymptotic confidence sequence (Waudby-Smith, Arbour, Dimmery, et al.;
    "Time-uniform central limit theory", and Dalal 2023). Same anytime guarantee, asymptotic, but a
    cheap closed-form half-width from only (n, mean, var) — no per-row scan. We use it for the running
    IPW / running-mean path that update_sequential persists, so a daily peek is O(1).
  * LUCB separation (Kalyanakrishnan et al. 2012) + Sequential Halving (Karnin, Koren, Somekh 2013):
    the multi-arm scheduler logic — keep the arms whose lower bound can still beat the best lower
    bound; halve the slate each round and reallocate the budget to survivors. Pure list/index math.

WHY VALID UNDER OUR LOGGING
---------------------------
The live policy is a CHANGING Thompson-sampling bandit (non-stationary), but it LOGS the propensity
of every action, so the per-call reward we feed here is an IPW/SNIPS estimate whose conditional mean
is the target value. The CS guarantees hold for any adapted (predictable-lambda) data stream — they
do NOT assume i.i.d. draws or a fixed logging policy — which is precisely why a betting/asymptotic CS
is the correct tool for a bandit-logged, peeked-at promotion test.

DESIGN LAWS HONOURED
--------------------
PURE-PYTHON (math only — no numpy / scipy / network / ClickHouse; the dormant path IS the only path
here). DORMANT-SAFE + BEST-EFFORT: every public function swallows its own errors -> logging.warning
and returns a clean empty/neutral value (a no-signal CS is the widest interval [lo,hi]; a separation
test defaults to False), NEVER raises into the worker or the gate. SIDE-PIPELINE: offline/worker
only. HONEST SCIENCE: a too-short stream yields a wide CS that cannot separate, so promotion simply
does not fire — the failure mode is "wait for more data", never a false GO. ANTI-GOODHART: promotion
consumes the PESSIMISTIC lower bound (cs_lower) and additionally requires a practical-delta floor, so
a hair-thin statistical edge can never trigger a champion swap.
"""
from __future__ import annotations

import logging
import math
from typing import List, Tuple

from . import schema as S

logger = logging.getLogger("flywheel.sequential")


# --------------------------------------------------------------------------- #
# Small numeric guards (mirrors ope.py house style).
# --------------------------------------------------------------------------- #
def _finite(x, default: float = 0.0) -> float:
    """Coerce to a finite float; NaN / inf / non-numeric -> ``default``."""
    try:
        f = float(x)
        if math.isnan(f) or math.isinf(f):
            return default
        return f
    except Exception:  # noqa: BLE001
        return default


def _clip(x: float, lo: float, hi: float) -> float:
    if x < lo:
        return lo
    if x > hi:
        return hi
    return x


# --------------------------------------------------------------------------- #
# B2.1 — betting confidence sequence (bounded mean; per-row scan).
# --------------------------------------------------------------------------- #
def betting_cs(
    xs: List[float],
    *,
    alpha: float = 0.05,
    lo: float = -1.0,
    hi: float = 2.0,
    grid: int = 41,
) -> Tuple[float, float]:
    """Anytime-valid (1-alpha) confidence sequence for a BOUNDED mean, via hedged betting (WSR 2024).

    Args
    ----
    xs    : the observed per-call values (rewards / IPW estimates), each assumed to live in
            ``[lo, hi]`` — values outside are clamped (best-effort, never raises).
    alpha : miscoverage. The CS covers the true mean simultaneously at every t with prob >= 1-alpha.
    lo,hi : the known bounds of the random variable (our capped reward range / {0,1} opt-out).
    grid  : number of candidate means scanned across ``[lo, hi]``.

    Method
    ------
    Rescale x to ``u = (x - lo)/(hi - lo)`` in ``[0,1]``. For each candidate mean ``m`` (also on the
    rescaled axis) accumulate the log-wealth of betting that ``m`` is the true mean::

        W_i = sum_i log(1 + lambda_i * (u_i - m))

    with a PREDICTABLE, variance-adaptive bet ``lambda_i = clip((mu_hat_{i-1} - m)/(sigma2_hat_{i-1}
    + 1e-6), [-c, c])`` computed from data seen strictly BEFORE row i (predictability is what keeps the
    wealth a martingale, hence Ville-valid). ``c`` hedges the bet inside ``[0, 1/m')`` so the capital
    can never go non-positive. ``m`` is IN the CS iff its wealth stays below ``1/alpha``
    (log-wealth < log(1/alpha)). We return ``(min, max)`` of the surviving grid, mapped back to the
    original ``[lo, hi]`` scale.

    Returns
    -------
    ``(lower, upper)`` on the original scale. No data / all candidates rejected / bad input ->
    ``(lo, hi)`` — the widest, most honest "no signal" interval (it can never separate, so promotion
    will not fire). NEVER raises.
    """
    try:
        a = _finite(alpha, 0.05)
        if not (0.0 < a < 1.0):
            a = 0.05
        lo_f = _finite(lo, -1.0)
        hi_f = _finite(hi, 2.0)
        if hi_f <= lo_f:
            return (lo_f, hi_f)
        width = hi_f - lo_f

        # Rescale observations to [0,1]; drop nothing — clamp out-of-range (a noisy IPW row that
        # overshot the nominal bound must not silently invert the bet).
        us: List[float] = []
        for x in (xs or []):
            u = (_finite(x, lo_f) - lo_f) / width
            us.append(_clip(u, 0.0, 1.0))
        if not us:
            return (lo_f, hi_f)

        g = int(grid) if (isinstance(grid, (int, float)) and grid >= 2) else 41
        log_thresh = math.log(1.0 / a)

        surviving: List[float] = []
        for j in range(g):
            m = j / (g - 1)                    # candidate mean on the [0,1] axis
            # Predictable running mean / variance of u seen BEFORE the current row.
            run_sum = 0.0
            run_sqsum = 0.0
            seen = 0
            log_wealth = 0.0
            rejected = False
            for u in us:
                if seen > 0:
                    mu_hat = run_sum / seen
                    var_hat = max(run_sqsum / seen - mu_hat * mu_hat, 0.0)
                else:
                    # WSR warm-start: bet as if the mean is 1/2 with unit-ish variance.
                    mu_hat = 0.5
                    var_hat = 0.25
                # Hedged bet capped so 1 + lambda*(u-m) stays strictly positive for u,m in [0,1].
                # The danger terms are (u-m) in [-1,1]; |lambda| < 1 keeps the factor in (0,2).
                c = 0.5 / max(m, 1.0 - m, 1e-6)
                c = min(c, 0.5)                 # never wager more than half the capital
                lam = _clip((mu_hat - m) / (var_hat + 1e-6), -c, c)
                factor = 1.0 + lam * (u - m)
                if factor <= 1e-12:
                    factor = 1e-12              # numeric floor; bet effectively wiped this candidate
                log_wealth += math.log(factor)
                # Update predictable stats AFTER betting on this row.
                run_sum += u
                run_sqsum += u * u
                seen += 1
                if log_wealth >= log_thresh:
                    rejected = True
                    break
            if not rejected:
                surviving.append(m)

        if not surviving:
            # Every candidate rejected — degenerate; fall back to the running mean as a point and the
            # full range as the (honest) interval so nothing downstream over-promotes.
            return (lo_f, hi_f)

        lower = lo_f + min(surviving) * width
        upper = lo_f + max(surviving) * width
        return (lower, upper)
    except Exception as exc:  # noqa: BLE001
        logger.warning("sequential.betting_cs failed (%d xs): %r", len(xs or []), exc)
        return (_finite(lo, -1.0), _finite(hi, 2.0))


# --------------------------------------------------------------------------- #
# B2.2 — closed-form asymptotic confidence sequence (running-mean path).
# --------------------------------------------------------------------------- #
def asymp_cs(
    n: int,
    mean: float,
    var: float,
    *,
    alpha: float = 0.05,
    eta: float = 0.1,
) -> Tuple[float, float]:
    """Closed-form AsympCS half-width (Waudby-Smith/Dalal): an O(1) anytime-valid CI from (n, mean, var).

    Half-width::

        S  = n * var                                   (total observed second moment scale)
        hw = sqrt( 2*(S*eta^2 + 1) / (n^2 * eta^2) * log( sqrt(S*eta^2 + 1) / alpha ) )

    ``eta`` is the (fixed) tuning parameter of the asymptotic mixture; smaller eta tightens late and
    loosens early. Returns ``(mean - hw, mean + hw)``, valid at any stopping time. This is the cheap
    path the persisted running-mean uses for a daily peek (no per-row scan needed).

    n <= 0 / non-finite inputs -> ``(0.0, 0.0)``? No — an honest "unknown" must be WIDE, not a zero
    interval that could spuriously separate. With no data we return ``(mean, mean)`` only when n<=0
    cannot form a half-width; callers gate on ``significant`` which needs a positive n. NEVER raises.
    """
    try:
        nn = int(n) if (isinstance(n, (int, float)) and n == n) else 0
        m = _finite(mean, 0.0)
        v = max(_finite(var, 0.0), 0.0)
        a = _finite(alpha, 0.05)
        if not (0.0 < a < 1.0):
            a = 0.05
        e = _finite(eta, 0.1)
        if not (e > 0.0):
            e = 0.1
        if nn <= 0:
            # No data ⇒ no half-width can be formed; return a point interval at the (zero) mean. The
            # promotion test additionally requires n>0, so this never reads as "significant".
            return (m, m)

        S = nn * v
        e2 = e * e
        inner = S * e2 + 1.0
        if inner <= 0.0:
            return (m, m)
        log_arg = math.sqrt(inner) / a
        if log_arg <= 1.0:
            # log <= 0 would give an imaginary / zero half-width; floor the log term at a tiny
            # positive so the CI stays a proper (non-degenerate) interval.
            log_term = 1e-9
        else:
            log_term = math.log(log_arg)
        hw2 = 2.0 * inner / (nn * nn * e2) * log_term
        hw = math.sqrt(hw2) if hw2 > 0.0 else 0.0
        return (m - hw, m + hw)
    except Exception as exc:  # noqa: BLE001
        logger.warning("sequential.asymp_cs failed (n=%r): %r", n, exc)
        return (_finite(mean, 0.0), _finite(mean, 0.0))


# --------------------------------------------------------------------------- #
# B2.3 — online Welford update + persisted SequentialState.
# --------------------------------------------------------------------------- #
def update_sequential(state, x: float, *, alpha: float = 0.05):
    """Fold one new observation ``x`` into a persisted ``SequentialState`` and recompute its CS.

    Performs an online Welford update of ``(n, running_mean, running_var)`` so the worker can resume
    across restarts from the stored row, then recomputes ``(cs_lower, cs_upper)`` via :func:`asymp_cs`
    and re-stamps ``significant`` (True once the CS excludes 0 — a useful default scalar significance;
    cross-arm separation is decided by :func:`lucb_separated`). Returns a NEW ``schema.SequentialState``
    (never mutates the input — the caller persists the returned row). Bad input -> the input is echoed
    back (or a fresh empty state) so the worker continues. NEVER raises.
    """
    try:
        # Read prior sufficient stats off whatever was passed (a SequentialState or None).
        prev_n = int(getattr(state, "n", 0) or 0)
        prev_mean = _finite(getattr(state, "running_mean", 0.0), 0.0)
        prev_var = max(_finite(getattr(state, "running_var", 0.0), 0.0), 0.0)
        tenant_id = str(getattr(state, "tenant_id", "") or "")
        challenger_id = str(getattr(state, "challenger_id", "") or "")
        metric = str(getattr(state, "metric", "reward") or "reward")

        xv = _finite(x, None) if x is not None else None
        if xv is None or xv != xv:
            # Non-numeric observation: nothing to fold — return state unchanged (re-stamped fresh).
            xv = None

        if xv is None:
            n_new = prev_n
            mean_new = prev_mean
            var_new = prev_var
        elif prev_n <= 0:
            n_new = 1
            mean_new = xv
            var_new = 0.0
        else:
            # Welford: M2 reconstructed from the stored population variance (var = M2 / n).
            n_new = prev_n + 1
            m2_prev = prev_var * prev_n
            delta = xv - prev_mean
            mean_new = prev_mean + delta / n_new
            delta2 = xv - mean_new
            m2_new = m2_prev + delta * delta2
            var_new = max(m2_new / n_new, 0.0)

        lower, upper = asymp_cs(n_new, mean_new, var_new, alpha=alpha)
        significant = bool(n_new > 0 and (lower > 0.0 or upper < 0.0))

        return S.SequentialState(
            tenant_id=tenant_id,
            challenger_id=challenger_id,
            ts_iso=S.now_iso(),
            metric=metric,
            n=n_new,
            running_mean=round(mean_new, 6),
            running_var=round(var_new, 6),
            cs_lower=round(lower, 6),
            cs_upper=round(upper, 6),
            significant=significant,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("sequential.update_sequential failed: %r", exc)
        try:
            # Best-effort: hand back a clean, harmless empty state so the worker keeps going.
            return S.SequentialState(ts_iso=S.now_iso())
        except Exception:  # noqa: BLE001
            return state


# --------------------------------------------------------------------------- #
# B2.4 — LUCB separation + practical-significance floor.
# --------------------------------------------------------------------------- #
def lucb_separated(chal_lower: float, champ_upper: float) -> bool:
    """LUCB dominance test: the challenger wins iff its CS LOWER bound clears the champion's CS UPPER.

    This is the pessimistic, anytime-valid "no overlap" condition — the challenger's worst plausible
    value already beats the champion's best plausible value. Consuming the LOWER bound (not the point
    estimate) is the anti-Goodhart guard: a wide / noisy challenger CS cannot separate. NEVER raises.
    """
    try:
        return _finite(chal_lower, float("-inf")) > _finite(champ_upper, float("inf"))
    except Exception as exc:  # noqa: BLE001
        logger.warning("sequential.lucb_separated failed: %r", exc)
        return False


def practical_significant(lift: float, delta: float) -> bool:
    """True iff the observed lift exceeds the minimum PRACTICAL delta (statistical != worth-promoting).

    A champion swap costs operator trust and exposes real leads, so we demand the point lift clears a
    floor (default ``cfg.seq_practical_delta``) on top of statistical separation. NEVER raises.
    """
    try:
        return _finite(lift, 0.0) >= _finite(delta, 0.0)
    except Exception as exc:  # noqa: BLE001
        logger.warning("sequential.practical_significant failed: %r", exc)
        return False


# --------------------------------------------------------------------------- #
# B2.5 — Sequential-Halving / LUCB scheduler (pure list math).
# --------------------------------------------------------------------------- #
def sequential_halving(arm_ids: list, budget: int, rounds: int = 3) -> list:
    """Sequential-Halving survivor slate (Karnin-Koren-Somekh 2013) — the pure scheduler.

    Given a slate of arm ids and a total ``budget`` of pulls split evenly across ``rounds``, this
    returns the PER-ROUND survivor slate: starting from the full slate, each round keeps the top
    ``ceil(|slate|/2)`` arms (halving). The returned list is the list of slates (one per round,
    INCLUDING the initial), so a caller knows how the field narrows and how to reallocate the
    per-round budget across survivors.

    NOTE: this is the scheduling skeleton only — it carries no scores (the actual ranking comes from
    the CS bounds the worker holds; SH just dictates HOW MANY survive each round). Ranking-by-score is
    the caller's job; here ties / order are preserved as given so the math is deterministic. Bad input
    -> ``[]``. NEVER raises.
    """
    try:
        slate = [a for a in (arm_ids or []) if a is not None]
        if not slate:
            return []
        r = int(rounds) if (isinstance(rounds, (int, float)) and rounds >= 1) else 3
        b = int(budget) if (isinstance(budget, (int, float)) and budget >= 0) else 0

        schedule: List[list] = [list(slate)]
        cur = list(slate)
        per_round_budget = (b // r) if r > 0 else 0
        for _ in range(r):
            if len(cur) <= 1:
                break
            keep = max(1, math.ceil(len(cur) / 2.0))
            # Pure list math: keep the first `keep` (the caller pre-sorts by CS lower bound). The
            # per_round_budget would be spread over `len(cur)` arms by the caller; we only shape the
            # survivor count here.
            cur = cur[:keep]
            schedule.append(list(cur))
        # per_round_budget is documented in the return contract via the schedule shape; expose nothing
        # else (the caller already holds `budget`). Keep the slate list as the survivor record.
        _ = per_round_budget
        return schedule
    except Exception as exc:  # noqa: BLE001
        logger.warning("sequential.sequential_halving failed: %r", exc)
        return []


# --------------------------------------------------------------------------- #
# B2.6 — the promotion verdict the gate reads.
# --------------------------------------------------------------------------- #
def evaluate_promotion(chal_state, champ_state, *, practical_delta: float = 0.01) -> dict:
    """Combine the challenger/champion CS states into the anytime-valid promotion verdict.

    Returns a dict the challenger gate consumes::

        {
          'seq_significant': lucb_separated(chal.cs_lower, champ.cs_upper),   # pessimistic separation
          'practical_sig'  : practical_significant(chal.mean - champ.mean, practical_delta),
          'lift'           : chal.running_mean - champ.running_mean,
          'chal_lower'     : ...,  'champ_upper': ...,
          'n_chal'         : ...,  'n_champ': ...,
          'promote'        : seq_significant AND practical_sig,               # the ANDed go-signal
        }

    Promotion requires BOTH a statistically anytime-valid separation AND a practically meaningful
    lift — neither alone fires a champion swap (and a real human click still gates the actual swap
    downstream). Missing / malformed states -> a safe all-False verdict with zeroed numbers. NEVER
    raises.
    """
    try:
        chal_lower = _finite(getattr(chal_state, "cs_lower", 0.0), 0.0)
        champ_upper = _finite(getattr(champ_state, "cs_upper", 0.0), 0.0)
        chal_mean = _finite(getattr(chal_state, "running_mean", 0.0), 0.0)
        champ_mean = _finite(getattr(champ_state, "running_mean", 0.0), 0.0)
        n_chal = int(getattr(chal_state, "n", 0) or 0)
        n_champ = int(getattr(champ_state, "n", 0) or 0)

        lift = chal_mean - champ_mean
        seq_sig = bool(n_chal > 0 and n_champ > 0 and lucb_separated(chal_lower, champ_upper))
        prac_sig = practical_significant(lift, practical_delta)

        return {
            "seq_significant": seq_sig,
            "practical_sig": prac_sig,
            "lift": round(lift, 6),
            "chal_lower": round(chal_lower, 6),
            "champ_upper": round(champ_upper, 6),
            "n_chal": n_chal,
            "n_champ": n_champ,
            "promote": bool(seq_sig and prac_sig),
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("sequential.evaluate_promotion failed: %r", exc)
        return {
            "seq_significant": False, "practical_sig": False, "lift": 0.0,
            "chal_lower": 0.0, "champ_upper": 0.0, "n_chal": 0, "n_champ": 0,
            "promote": False,
        }


__all__ = [
    "betting_cs",
    "asymp_cs",
    "update_sequential",
    "lucb_separated",
    "practical_significant",
    "sequential_halving",
    "evaluate_promotion",
]


# --------------------------------------------------------------------------- #
# Self-check — pure-python happy path (NO network / NO ClickHouse / NO numpy).
# Run: python3 -m voice_ops.flywheel.sequential
# --------------------------------------------------------------------------- #
if __name__ == "__main__":  # pragma: no cover
    import random

    logging.basicConfig(level=logging.INFO)
    random.seed(7)

    # 1) betting_cs: a clearly-positive stream should yield a CS that excludes 0 and brackets ~0.4.
    pos = [_clip(0.4 + random.gauss(0, 0.2), -1.0, 2.0) for _ in range(400)]
    blo, bhi = betting_cs(pos, alpha=0.05, lo=-1.0, hi=2.0, grid=41)
    print(f"betting_cs(pos~0.4): lower={blo:.3f} upper={bhi:.3f}  excludes0={blo > 0.0}")
    assert isinstance(blo, float) and isinstance(bhi, float) and blo <= bhi
    # near-zero stream should NOT confidently exclude 0
    zero = [_clip(random.gauss(0, 0.2), -1.0, 2.0) for _ in range(400)]
    zlo, zhi = betting_cs(zero, alpha=0.05)
    print(f"betting_cs(zero):    lower={zlo:.3f} upper={zhi:.3f}  brackets0={zlo <= 0.0 <= zhi}")
    # empty input → widest interval
    assert betting_cs([]) == (-1.0, 2.0)

    # 2) asymp_cs: closed-form half-width shrinks as n grows.
    lo10, hi10 = asymp_cs(10, 0.4, 0.04)
    lo1k, hi1k = asymp_cs(1000, 0.4, 0.04)
    print(f"asymp_cs n=10:   ({lo10:.3f}, {hi10:.3f})  hw={(hi10 - lo10) / 2:.3f}")
    print(f"asymp_cs n=1000: ({lo1k:.3f}, {hi1k:.3f})  hw={(hi1k - lo1k) / 2:.3f}")
    assert (hi1k - lo1k) < (hi10 - lo10), "CS must tighten with more data"
    assert asymp_cs(0, 0.0, 0.0) == (0.0, 0.0)

    # 3) update_sequential: fold a positive stream; final state should be significant (excl. 0).
    st = S.SequentialState(tenant_id="t1", challenger_id="ch_demo", metric="reward")
    for v in pos:
        st = update_sequential(st, v, alpha=0.05)
    print(f"update_sequential: n={st.n} mean={st.running_mean:.3f} "
          f"cs=({st.cs_lower:.3f},{st.cs_upper:.3f}) significant={st.significant}")
    assert st.n == len(pos)
    assert abs(st.running_mean - (sum(pos) / len(pos))) < 1e-6, "Welford mean must match batch mean"
    assert isinstance(st, S.SequentialState)
    # non-numeric obs is swallowed, n unchanged
    st_noop = update_sequential(st, float("nan"))
    assert st_noop.n == st.n
    # None state → fresh empty, no raise
    st_fresh = update_sequential(None, 0.5)
    assert st_fresh.n == 1 and abs(st_fresh.running_mean - 0.5) < 1e-9

    # 4) lucb_separated + practical_significant.
    assert lucb_separated(0.30, 0.20) is True
    assert lucb_separated(0.10, 0.20) is False
    assert practical_significant(0.05, 0.01) is True
    assert practical_significant(0.005, 0.01) is False

    # 5) sequential_halving: 8 arms over 3 rounds halves each round.
    sched = sequential_halving([f"arm{i}" for i in range(8)], budget=240, rounds=3)
    sizes = [len(s) for s in sched]
    print(f"sequential_halving sizes per round: {sizes}")
    assert sizes[0] == 8 and sizes == [8, 4, 2, 1], f"unexpected halving schedule {sizes}"
    assert sequential_halving([], 10) == []

    # 6) evaluate_promotion: a separated, practically-significant challenger promotes.
    champ = S.SequentialState(challenger_id="champ", n=300, running_mean=0.20,
                              cs_lower=0.15, cs_upper=0.25)
    chal = S.SequentialState(challenger_id="chal", n=300, running_mean=0.40,
                             cs_lower=0.30, cs_upper=0.50)
    verdict = evaluate_promotion(chal, champ, practical_delta=0.01)
    print(f"evaluate_promotion (clear win): {verdict}")
    assert verdict["seq_significant"] is True and verdict["practical_sig"] is True
    assert verdict["promote"] is True and abs(verdict["lift"] - 0.20) < 1e-6
    # an overlapping challenger does NOT promote
    chal_overlap = S.SequentialState(challenger_id="chal2", n=300, running_mean=0.22,
                                     cs_lower=0.10, cs_upper=0.34)
    v2 = evaluate_promotion(chal_overlap, champ, practical_delta=0.01)
    assert v2["seq_significant"] is False and v2["promote"] is False
    # malformed states → safe all-False, no raise
    v3 = evaluate_promotion(None, None)
    assert v3["promote"] is False

    print("\nOK — voice_ops.flywheel.sequential self-check passed (pure-python).")
