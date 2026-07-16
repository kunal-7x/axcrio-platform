"""voice_ops.flywheel.credit — Layer-B CREDIT ASSIGNMENT for the Haptica Flywheel.

THE PROBLEM (the founder's literal ask): an outbound real-estate call is a long
Hinglish trajectory of agent MOVES (probe, price_reveal, objection_rebuttal, cta_push …)
and the only ground-truth signal — "did the lead book a site visit?" — arrives ONCE, at
the very end. That is a *sparse terminal reward*. Reinforcement learning on a sparse,
delayed signal is the classic credit-assignment problem: WHICH move actually moved the
needle? Which rebuttal earned the booking; which pushy CTA poisoned it?

THE SCIENCE (how we split the credit honestly):
  * A^O — the OUTCOME advantage. We z-score the call's terminal reward against its
    *cohort* baseline (mean, std over comparable calls). A booking from an already-hot
    lead is worth less surprise than a booking clawed back from a cold one; the cohort
    baseline is the control that removes that confound. (This is the GRPO group-baseline
    idea: advantage = (reward - group_mean) / group_std.)
  * A^I_k — per-turn INTERMEDIATE advantage. The dense process channels (affect_delta
    PBRS-shaping + sampled judge_score) z-scored WITHIN the call tell us, turn by turn,
    where the conversation got better or worse irrespective of the final outcome.
  * A_k — the BLEND. Each turn k inherits a discounted tail of intermediate advantages
    PLUS a discounted share of the terminal outcome advantage (the further a move sits
    from the close, the less terminal credit it claims — credit_alpha is the decay). This
    is the MT-GRPO multi-turn blend: dense intermediate signal anchored by the sparse
    outcome so neither hallucinates on its own.

  Layer-C — build_move_prm(): aggregating those credited turns across thousands of calls
  yields a per-MOVE Process Reward Model: P(book | this move at this state), its lift over
  the cohort baseline, the sample count and a Wilson confidence interval. THAT table is the
  literal answer to "which move is positive / negative" — and it is honest because a group
  with n<5 is dropped and every rate ships with its CI (no fake numbers).

DESIGN LAWS honoured here:
  * Pure-python, deterministic math; numpy is NEVER imported (small per-call arrays — a
    plain list comprehension is faster and dep-free). assign() is byte-deterministic.
  * DORMANT-SAFE / BEST-EFFORT: build_move_prm swallows its own errors → WARNING and
    returns []. The sync helpers are pure and total (a degenerate call → zeros, never a
    raise). Importing this module never touches ClickHouse or the network.
  * HONEST SCIENCE: every PRM rate carries n_samples + a Wilson CI; sub-threshold groups
    are dropped; the terminal/intermediate split is explicit, never a fused mystery scalar.
  * SIDE-PIPELINE: pure post-call offline math; never touches the live LiveKit turn loop.
"""
from __future__ import annotations

import logging
import math
from typing import List, Sequence, Tuple

from . import config as _cfg
from . import schema as S
from . import store as _st
from .schema import MovePRMRow

logger = logging.getLogger("flywheel.credit")

__all__ = [
    "wilson_ci",
    "cohort_baseline",
    "assign",
    "mt_grpo_blend",
    "build_move_prm",
]


# --------------------------------------------------------------------------- #
# Tiny numeric helpers (kept local so the module has ZERO heavy deps).
# --------------------------------------------------------------------------- #
def _f(v, default: float = 0.0) -> float:
    """Coerce to float, NaN/inf/garbage → default (mirrors schema._f)."""
    try:
        x = float(v)
    except Exception:  # noqa: BLE001
        return default
    if x != x or x in (float("inf"), float("-inf")):  # NaN / inf guard
        return default
    return x


def _mean(xs: Sequence[float]) -> float:
    xs = list(xs)
    return sum(xs) / len(xs) if xs else 0.0


def _std(xs: Sequence[float], mean: float) -> float:
    """Population standard deviation (n divisor) — we are describing the sample we have,
    not inferring a wider population, so the biased estimator is the honest one here."""
    xs = list(xs)
    if not xs:
        return 0.0
    var = sum((x - mean) ** 2 for x in xs) / len(xs)
    return math.sqrt(var) if var > 0 else 0.0


# --------------------------------------------------------------------------- #
# Wilson score interval — the honest CI for a proportion (the founder's "no fake
# numbers" law). Far better than the naive normal approximation at small n / extreme
# p, and it never escapes [0, 1]. n == 0 → (0.0, 0.0) (no evidence, no interval).
# --------------------------------------------------------------------------- #
def wilson_ci(k: int, n: int, z: float = 1.96) -> Tuple[float, float]:
    """Wilson score CI for k successes in n trials at confidence z (default 95%).

    Returns (low, high), each clamped to [0, 1]. n == 0 → (0.0, 0.0)."""
    try:
        k = int(k)
        n = int(n)
    except Exception:  # noqa: BLE001
        return (0.0, 0.0)
    if n <= 0:
        return (0.0, 0.0)
    k = max(0, min(k, n))
    z = _f(z, 1.96)
    phat = k / n
    z2 = z * z
    denom = 1.0 + z2 / n
    centre = (phat + z2 / (2 * n)) / denom
    half = (z * math.sqrt((phat * (1 - phat) + z2 / (4 * n)) / n)) / denom
    low = max(0.0, centre - half)
    high = min(1.0, centre + half)
    return (round(low, 6), round(high, 6))


# --------------------------------------------------------------------------- #
# Cohort baseline — the GRPO group control for the OUTCOME advantage. Comparing a
# call's terminal reward to its cohort's mean removes the "hot leads book anyway"
# confound. std is floored at 0.1 so a low-variance cohort can't blow the z-score up.
# --------------------------------------------------------------------------- #
def cohort_baseline(outcomes: list) -> Tuple[float, float]:
    """(mean, std) of a list of terminal rewards. std floored at >= 0.1 to keep the
    outcome advantage z-score finite and stable on a degenerate (zero-variance) cohort.
    Empty cohort → (0.0, 0.1) (a neutral baseline with the floor std)."""
    try:
        xs = [_f(o) for o in (outcomes or [])]
    except Exception:  # noqa: BLE001
        xs = []
    if not xs:
        return (0.0, 0.1)
    mu = _mean(xs)
    sd = _std(xs, mu)
    return (round(mu, 6), round(max(sd, 0.1), 6))


# --------------------------------------------------------------------------- #
# MT-GRPO blend — the per-turn combine of the dense intermediate tail with the sparse
# outcome share. Factored out so assign() (and any caller) shares ONE definition.
# --------------------------------------------------------------------------- #
def mt_grpo_blend(intermediate_adv: list, outcome_adv: float, alpha: float = 0.6) -> list:
    """Blend a per-turn intermediate-advantage list with the call's scalar outcome
    advantage, discounting both toward the terminal step by `alpha`.

    For a call of K turns and turn index k (0-based):
        A_k = sum_{l>=k} alpha^(l-k) * A^I_l   +   alpha^(K-k) * A^O

    The first term is a discounted tail of intermediate advantages (a move owns its own
    A^I_k fully and an exponentially-fading share of every later turn's). The second is
    the terminal credit: a move nearer the close (smaller K-k) claims more of the outcome
    surprise, a move 12 turns back claims almost none. Returns a list len == K.
    Deterministic; pure list math (no numpy)."""
    iadv = [_f(a) for a in (intermediate_adv or [])]
    k_count = len(iadv)
    if k_count == 0:
        return []
    a = _f(alpha, 0.6)
    # Clamp the discount into (0, 1]; outside that the discounted-tail geometry breaks.
    if a < 0.0:
        a = 0.0
    elif a > 1.0:
        a = 1.0
    oadv = _f(outcome_adv)

    out: List[float] = []
    for k in range(k_count):
        # discounted tail of intermediate advantages for l >= k
        tail = 0.0
        for l in range(k, k_count):
            tail += (a ** (l - k)) * iadv[l]
        # discounted share of the terminal outcome advantage
        terminal_share = (a ** (k_count - k)) * oadv
        out.append(round(tail + terminal_share, 6))
    return out


# --------------------------------------------------------------------------- #
# assign() — the public credit-assignment entrypoint. Turns one call's turn list +
# its terminal reward into a per-turn advantage list (the +/- signal per move).
# --------------------------------------------------------------------------- #
def assign(turns: list, terminal_reward: float, cohort: tuple = (0.0, 1.0), *, cfg=None) -> list:
    """Distribute a sparse terminal reward across a call's turns.

    Args:
      turns: ordered list of turn dicts (each may carry 'affect_delta' and 'judge_score';
             both default to 0.0 when absent). Order == conversation order (turn 0 first).
      terminal_reward: the call's capped terminal outcome (from reward.terminal_reward).
      cohort: (mean, std) baseline for the OUTCOME advantage — pass cohort_baseline(...).
              A bad/empty cohort std is floored so A^O stays finite.
      cfg: optional FlywheelConfig (credit_alpha is the blend decay). Loaded if None.

    Returns a list of per-turn advantages, len == len(turns). Deterministic, never raises.
    """
    if not turns:
        return []
    try:
        if cfg is None:
            cfg = _cfg.load()
        alpha = _f(getattr(cfg, "credit_alpha", 0.6), 0.6)

        # --- A^O: the cohort-relative OUTCOME advantage (one scalar for the whole call).
        try:
            c_mean = _f(cohort[0], 0.0)
            c_std = _f(cohort[1], 1.0)
        except Exception:  # noqa: BLE001
            c_mean, c_std = 0.0, 1.0
        if c_std < 0.1:                      # mirror cohort_baseline's std floor
            c_std = 0.1
        outcome_adv = (_f(terminal_reward) - c_mean) / c_std

        # --- A^I_k: per-turn INTERMEDIATE advantage = z-score WITHIN the call of the
        # dense process channels (affect_delta + judge_score). Within-call z-scoring is a
        # per-call baseline: it asks "relative to THIS conversation, was this turn good?",
        # which is the right frame for crediting a move inside its own dialogue.
        raw_inter: List[float] = []
        for t in turns:
            t = t if isinstance(t, dict) else {}
            raw_inter.append(_f(t.get("affect_delta", 0.0)) + _f(t.get("judge_score", 0.0)))
        mu = _mean(raw_inter)
        sd = _std(raw_inter, mu)
        if sd < 1e-9:
            # Zero within-call variance → no intermediate signal to differentiate turns.
            inter_adv = [0.0 for _ in raw_inter]
        else:
            inter_adv = [(x - mu) / sd for x in raw_inter]

        # --- A_k: the MT-GRPO blend (shared helper).
        return mt_grpo_blend(inter_adv, outcome_adv, alpha)
    except Exception as exc:  # noqa: BLE001
        logger.warning("flywheel credit.assign error: %r", exc)
        # Best-effort: never raise into a caller; return a zero vector of the right length.
        return [0.0 for _ in turns]


# --------------------------------------------------------------------------- #
# build_move_prm() — Layer-C: aggregate credited turns into a per-MOVE Process Reward
# Model. THE table that answers "which move is positive / negative" with honest CIs.
# --------------------------------------------------------------------------- #
async def build_move_prm(tenant_id: str, vertical: str = "", minutes: int = 43200) -> list:
    """Build the per-move PRM by grouping flywheel_trajectories over a window.

    For each (move_type, objection_type, regime, lead_temperature) group:
        book_rate    = countIf(reward_capped > 0.5) / count()
        baseline_rate = the overall booked-turn rate for the vertical (the cohort control)
        lift         = book_rate - baseline_rate          (the +/- signal)
        n_samples    = count()
        ci_low/high  = wilson_ci(booked_in_group, n_samples)

    Groups with n_samples < 5 are DROPPED (honest-science: no rate without evidence).
    Tenant-scoped via {tid:String}. Reads the ReplacingMergeTree with FINAL. Returns a
    list[MovePRMRow]; [] on any error — never raises."""
    try:
        if not tenant_id:
            return []
        ts_iso = S.now_iso()

        where = "tenant_id = {tid:String} AND ts > now() - INTERVAL {m:UInt32} MINUTE"
        params = {"tid": str(tenant_id), "m": int(minutes)}
        if vertical:
            where += " AND vertical = {v:String}"
            params["v"] = str(vertical)

        table = _st._final(_st.TRAJECTORIES)  # 'flywheel_trajectories FINAL'

        # --- overall baseline booked-turn rate for the vertical (one number).
        base_sql = (
            f"SELECT count() AS n, countIf(reward_capped > 0.5) AS booked "
            f"FROM {table} WHERE {where}"
        )
        base_res = await _st._ch(base_sql, params)
        if base_res.get("error"):
            logger.warning("flywheel build_move_prm baseline error: %s", base_res.get("error"))
            return []
        base_rows = base_res.get("rows") or []
        base_n = int(_f((base_rows[0] if base_rows else {}).get("n", 0)))
        base_booked = int(_f((base_rows[0] if base_rows else {}).get("booked", 0)))
        baseline_rate = (base_booked / base_n) if base_n > 0 else 0.0

        # --- per-group book rate.
        grp_sql = (
            f"SELECT move_type, objection_type, regime, lead_temperature, "
            f"count() AS n, countIf(reward_capped > 0.5) AS booked "
            f"FROM {table} WHERE {where} "
            f"GROUP BY move_type, objection_type, regime, lead_temperature "
            f"HAVING n >= 5 "
            f"ORDER BY n DESC LIMIT 5000"
        )
        grp_res = await _st._ch(grp_sql, params)
        if grp_res.get("error"):
            logger.warning("flywheel build_move_prm group error: %s", grp_res.get("error"))
            return []

        out: List[MovePRMRow] = []
        for r in (grp_res.get("rows") or []):
            try:
                n = int(_f(r.get("n", 0)))
                if n < 5:                       # belt-and-braces (HAVING already enforces)
                    continue
                booked = int(_f(r.get("booked", 0)))
                booked = max(0, min(booked, n))
                book_rate = booked / n
                ci_low, ci_high = wilson_ci(booked, n)
                out.append(MovePRMRow(
                    tenant_id=str(tenant_id),
                    vertical=str(vertical or "real_estate"),
                    move_type=str(r.get("move_type", "other") or "other"),
                    objection_type=str(r.get("objection_type", "none") or "none"),
                    regime=str(r.get("regime", "steady") or "steady"),
                    lead_temperature=str(r.get("lead_temperature", "unknown") or "unknown"),
                    ts_iso=ts_iso,
                    book_rate=round(book_rate, 6),
                    baseline_rate=round(baseline_rate, 6),
                    lift=round(book_rate - baseline_rate, 6),
                    n_samples=n,
                    ci_low=ci_low,
                    ci_high=ci_high,
                ))
            except Exception as exc:  # noqa: BLE001
                logger.warning("flywheel build_move_prm row skip: %r", exc)
                continue
        return out
    except Exception as exc:  # noqa: BLE001
        logger.warning("flywheel build_move_prm error: %r", exc)
        return []


# --------------------------------------------------------------------------- #
# Inline self-check — happy path on synthetic inputs only (no network / no CH).
# Run: python3 -m voice_ops.flywheel.credit
# --------------------------------------------------------------------------- #
if __name__ == "__main__":  # pragma: no cover
    logging.basicConfig(level=logging.INFO)

    # 1) wilson_ci: degenerate + a real proportion.
    assert wilson_ci(0, 0) == (0.0, 0.0), "n==0 must give (0,0)"
    lo, hi = wilson_ci(7, 10)
    assert 0.0 <= lo < 0.7 < hi <= 1.0, (lo, hi)
    # k clamped to n
    assert wilson_ci(15, 10)[1] == 1.0

    # 2) cohort_baseline: floor on std, empty case.
    m, s = cohort_baseline([1.0, 1.0, 1.0])
    assert m == 1.0 and s == 0.1, (m, s)            # zero-variance -> floored std
    me, se = cohort_baseline([])
    assert me == 0.0 and se == 0.1, (me, se)
    m2, s2 = cohort_baseline([0.0, 2.0])
    assert m2 == 1.0 and s2 >= 0.1

    # 3) mt_grpo_blend: shape, determinism, and the terminal-decay direction.
    iadv = [0.0, 0.0, 0.0]
    blended = mt_grpo_blend(iadv, outcome_adv=1.0, alpha=0.6)
    assert len(blended) == 3
    # With zero intermediate signal, terminal credit must INCREASE toward the close:
    assert blended[0] < blended[1] < blended[2], blended
    assert mt_grpo_blend([], 1.0) == []
    assert mt_grpo_blend(iadv, 1.0, 0.6) == blended  # deterministic

    # 4) assign: full happy path on a synthetic 4-turn call.
    turns = [
        {"affect_delta": -2.0, "judge_score": 0.0},   # bad opening
        {"affect_delta": 1.0, "judge_score": 1.0},    # good probe
        {"affect_delta": 0.5, "judge_score": 0.5},    # decent rebuttal
        {"affect_delta": 3.0, "judge_score": 1.0},    # strong close
    ]
    cohort = cohort_baseline([0.0, 1.0, 2.0, 0.0, 1.0])
    adv = assign(turns, terminal_reward=2.0, cohort=cohort)
    assert len(adv) == len(turns), adv
    assert all(isinstance(x, float) for x in adv), adv
    # The strong-close turn should out-credit the bad opening.
    assert adv[3] > adv[0], adv
    # Determinism: identical inputs -> identical output.
    assert assign(turns, 2.0, cohort) == adv

    # 5) edge cases: empty + zero-variance intermediate channel must not raise.
    assert assign([], 1.0) == []
    flat = assign([{"affect_delta": 0.0}, {"affect_delta": 0.0}], 1.0, (0.0, 1.0))
    assert len(flat) == 2

    print("OK credit.py self-check passed:", {
        "wilson_7_10": (lo, hi),
        "cohort_floor": (m, s),
        "blend_terminal_decay": blended,
        "assign_4turn": adv,
    })
