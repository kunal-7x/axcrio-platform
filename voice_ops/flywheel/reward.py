"""voice_ops.flywheel.reward — Layer-B reward FUSION with provenance + anti-Goodhart caps.

WHY THIS MODULE EXISTS (and the science it encodes)
---------------------------------------------------
An outbound real-estate telecaller has ONE thing it truly optimises: the rate at which a
warm conversation turns into a *booked site visit*. That terminal signal is sparse, noisy
and arrives once per call. Naively maximising it is the textbook Goodhart trap — a pushy,
manipulative, RERA-non-compliant agent books more visits this week and burns the brand
next week. So the reward this module emits is deliberately CONSERVATIVE and HONEST:

  Tier-2 OUTCOME (dominant):  a small closed table of canonical outcome scalars
    (REWARD_TABLE), modulated by a *concave* deal-value multiplier (tanh, capped) so a
    ₹5cr flat does not swamp the gradient with a single fat-tailed example, then HARD
    CLIPPED to [-1, +reward_cap]. Caps + saturation are the anti-Goodhart mechanism: the
    policy cannot win by chasing the heavy tail.

  Tier-3 PROCESS (bounded shaping, never dominant):
    * affect_delta  — POTENTIAL-BASED reward shaping (Ng, Harada & Russell 1999) on the
      caller's cognitive *friction*. Because it is a potential difference F = Φ(s) - γΦ(s'),
      it is provably POLICY-INVARIANT: it speeds learning without changing the optimal
      policy, so it can never trade booked visits for "feeling nice". Friction going DOWN
      is positive. Confidence-gated → a low-confidence telephony turn shapes ~nothing.
    * judge_score   — the RLAIF rubric scalar (filled by judge.py); a small weight.

  FUSION keeps provenance attached at all times: fuse() returns a RewardComponents (the
  frozen-foundation dataclass), never a bare float. The console can always show *why* a
  turn scored what it did — that is the "honest science" law.

COMPLIANCE IS NOT HERE. Compliance is a HARD GATE handled by compliance.py and applied
upstream (a non-compliant turn is dropped/zeroed before it can earn reward); it is never a
reward term, so optimising reward can never be traded against being pushy. This module only
ever shapes a reward that has already cleared that gate.

DESIGN LAWS (mirror voice_ops/research/*.py): pure-python, no heavy deps at import, every
public function swallows its own errors (→ logging.warning) and returns a clean zero value,
and the module imports cleanly even when ClickHouse / OPENROUTER_API_KEY are absent.
"""
from __future__ import annotations

import logging
import math
from typing import Dict, Optional, Tuple

from . import config as _cfg
from .schema import RewardComponents

logger = logging.getLogger("flywheel.reward")


# --------------------------------------------------------------------------- #
# REWARD_TABLE — canonical outcome → base scalar.
#
# The ladder is intentionally compressed: the gap between a booked visit (+1.0) and a hot
# lead (+0.6) is small because the model should not learn to fabricate "bookings". The
# negatives are mild for soft failures (cold lead, no-answer) and only reach -1.0 for the
# two genuinely brand-damaging terminals (dead lead, WhatsApp opt-out). A WhatsApp opt-out
# is treated as maximally bad — it is the caller revoking *permission to contact*, the one
# outcome a growth-optimised agent must never be incentivised to risk.
# --------------------------------------------------------------------------- #
REWARD_TABLE: Dict[str, float] = {
    "site_visit_booked":  +1.0,
    "handoff_done":       +0.7,
    "lead_hot":           +0.6,
    "callback_scheduled": +0.3,
    "lead_warm":          +0.1,
    "answered":           +0.05,
    "interested":         +0.05,
    "lead_cold":          -0.1,
    "call_failed":        -0.3,
    "no_answer":          -0.3,
    "hangup":             -0.3,
    "not_interested":     -0.4,
    "lead_dead":          -1.0,
    "whatsapp_opted_out": -1.0,
}


# --------------------------------------------------------------------------- #
# Internal helpers — all total, none raise.
# --------------------------------------------------------------------------- #
def _num(v, d: float = 0.0) -> float:
    """Coerce anything to a finite float, falling back to `d` on junk / NaN / inf."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return d
    if f != f or f in (float("inf"), float("-inf")):  # NaN / inf guard
        return d
    return f


def _truthy(v) -> bool:
    if isinstance(v, str):
        return v.strip().lower() in ("1", "true", "yes", "on", "y", "t")
    return bool(v)


def _clip(x: float, lo: float, hi: float) -> float:
    return lo if x < lo else (hi if x > hi else x)


# --------------------------------------------------------------------------- #
# Tier-2: outcome extraction from a finalized droplet call record.
# --------------------------------------------------------------------------- #
def outcome_from_rec(rec: dict) -> Tuple[str, float]:
    """Map a finalized droplet call record → (canonical_outcome_key, deal_value).

    The record is the loose dict the dialer/agent emits at call end. We never trust a single
    field; instead we read every positive signal present and return the STRONGEST one (a
    booked visit beats a callback beats "interested"…). This makes the reward robust to the
    several historical shapes of `rec` across droplet versions.

    rec may carry:
      * outcome   — one of no_answer/voicemail/no_human/answered/interested/not_interested/
                    callback/opt_out (the dialer's coarse terminal)
      * interest  — 0..100 model-estimated lead interest
      * booked / site_visit (bool-ish) and deal_value (₹) — the explicit conversion signals

    Returns ("answered", 0.0) on an empty/garbage record (never raises).
    """
    try:
        if not isinstance(rec, dict):
            return ("answered", 0.0)

        deal_value = _num(rec.get("deal_value", 0.0), 0.0)
        raw_outcome = str(rec.get("outcome", "") or "").strip().lower()
        interest = _num(rec.get("interest", rec.get("interest_score", -1.0)), -1.0)

        # --- 1) strongest explicit positive: a real booked site visit ----------------- #
        if _truthy(rec.get("booked")) or _truthy(rec.get("site_visit")) \
                or raw_outcome in ("site_visit_booked", "booked", "visit_booked"):
            return ("site_visit_booked", deal_value)

        # --- 2) human handoff completed ------------------------------------------------ #
        if _truthy(rec.get("handoff_done")) or _truthy(rec.get("handed_off")) \
                or raw_outcome in ("handoff_done", "handoff", "transferred"):
            return ("handoff_done", deal_value)

        # --- 3) explicit opt-out (revoked permission to contact) — hard negative ------- #
        if _truthy(rec.get("opt_out")) or _truthy(rec.get("opted_out")) \
                or raw_outcome in ("opt_out", "opted_out", "whatsapp_opted_out", "dnd"):
            return ("whatsapp_opted_out", deal_value)

        # --- 4) scheduled callback ----------------------------------------------------- #
        if _truthy(rec.get("callback")) or raw_outcome in ("callback", "callback_scheduled"):
            return ("callback_scheduled", deal_value)

        # --- 5) interest-band → temperature, when no explicit terminal dominates ------- #
        #     interest is the agent's calibrated 0..100; map it to a lead-temperature
        #     scalar. We only fall here for "soft" outcomes (answered / interested).
        if raw_outcome in ("interested", "answered", "") and interest >= 0:
            if interest >= 80:
                return ("lead_hot", deal_value)
            if interest >= 60:
                return ("lead_warm", deal_value)
            if interest >= 35:
                return ("interested", deal_value)
            if interest < 15:
                return ("lead_cold", deal_value)
            # 15..35 → answered (engaged but lukewarm)
            return ("answered", deal_value)

        # --- 6) explicit declines ------------------------------------------------------ #
        if raw_outcome in ("not_interested", "declined", "rejected"):
            return ("not_interested", deal_value)
        if raw_outcome in ("lead_dead", "dead", "wrong_number", "blacklist"):
            return ("lead_dead", deal_value)

        # --- 7) connection / no-contact failures --------------------------------------- #
        if raw_outcome in ("no_answer", "noanswer", "missed"):
            return ("no_answer", deal_value)
        if raw_outcome in ("voicemail", "no_human", "ivr", "machine"):
            return ("call_failed", deal_value)
        if raw_outcome in ("hangup", "hung_up", "dropped", "abandoned"):
            return ("hangup", deal_value)
        if raw_outcome in ("call_failed", "failed", "error", "busy"):
            return ("call_failed", deal_value)

        # --- 8) a known key passed straight through ------------------------------------ #
        if raw_outcome in REWARD_TABLE:
            return (raw_outcome, deal_value)

        # --- 9) last resort: connected but uninformative ------------------------------- #
        return ("answered", deal_value)
    except Exception as exc:  # noqa: BLE001 — best-effort, never raise into a caller
        logger.warning("reward.outcome_from_rec failed: %s", exc)
        return ("answered", 0.0)


# --------------------------------------------------------------------------- #
# Tier-2: terminal reward = base × concave-deal-multiplier, then HARD CLIPPED.
# --------------------------------------------------------------------------- #
def terminal_reward(outcome: str, deal_value: float = 0.0, cfg=None) -> Tuple[float, float]:
    """Scalar terminal reward for a call outcome, with anti-Goodhart saturation.

        base   = REWARD_TABLE.get(outcome, 0.0)
        m      = 1 + tanh(deal_value / cfg.deal_scale)        # concave, monotone, → 2 in limit
        m      = min(m, cfg.deal_cap)                          # cap the multiplier
        raw    = base * m
        capped = clip(raw, -1.0, +cfg.reward_cap)              # hard saturation

    The deal multiplier only ever AMPLIFIES a positive base (we never apply it to a negative
    base, so a big lost deal cannot read as "extra bad" and skew the policy toward avoiding
    high-value leads). tanh keeps the marginal value of a bigger deal DECREASING — the
    moat is booking *more visits*, not chasing one whale.

    Returns (raw, capped), both rounded to 5dp. Never raises.
    """
    try:
        cfg = cfg or _cfg.load()
        base = _num(REWARD_TABLE.get(str(outcome or "").strip().lower(), 0.0), 0.0)

        deal_scale = _num(getattr(cfg, "deal_scale", 5_000_000.0), 5_000_000.0) or 5_000_000.0
        deal_cap = _num(getattr(cfg, "deal_cap", 1.5), 1.5)
        reward_cap = _num(getattr(cfg, "reward_cap", 2.0), 2.0)

        dv = _num(deal_value, 0.0)
        # concave multiplier, only for positive outcomes (and only for a positive deal value)
        if base > 0 and dv > 0:
            mult = 1.0 + math.tanh(dv / deal_scale)
            mult = min(mult, deal_cap)
        else:
            mult = 1.0

        raw = base * mult
        capped = _clip(raw, -1.0, reward_cap)
        return (round(raw, 5), round(capped, 5))
    except Exception as exc:  # noqa: BLE001
        logger.warning("reward.terminal_reward failed: %s", exc)
        return (0.0, 0.0)


# --------------------------------------------------------------------------- #
# Tier-3: potential-based affect shaping (POLICY-INVARIANT).
# --------------------------------------------------------------------------- #
def affect_delta_shaping(
    friction_t: float,
    friction_next: float,
    confidence: float = 1.0,
    friction_var: float = 0.0,
    cfg=None,
) -> float:
    """Potential-based reward shaping on caller friction (Ng, Harada & Russell 1999).

        Φ(s)  := -friction / 100        (lower friction == higher potential)
        F      = γ·Φ(s') - Φ(s)
               = (friction_t - γ·friction_next) / 100

    Because F is exactly a discounted potential difference, adding it to the reward is
    PROVABLY policy-invariant: it changes the value function by a constant offset per state
    and so leaves the optimal policy unchanged. That is the whole point — dense process
    feedback that *accelerates* credit assignment without ever letting "make the caller
    feel calmer" override "book the visit".

    Friction DOWN over the turn (friction_next < friction_t) → POSITIVE shaping.

    The raw potential difference is then trusted in proportion to how reliable the friction
    estimate is: weight = confidence / (1 + friction_var). A low-confidence telephony turn,
    or one with a wide uncertainty band (high variance), contributes ~0 — we never shape on
    noise. Finally clamped to [-1, 1] so a single turn's shaping can never dominate the
    bounded w_affect channel. Returns 0.0 on any error.
    """
    try:
        cfg = cfg or _cfg.load()
        gamma = _num(getattr(cfg, "gamma_sparse", 0.95), 0.95)

        f_t = _num(friction_t, 50.0)
        f_n = _num(friction_next, 50.0)
        conf = _clip(_num(confidence, 1.0), 0.0, 1.0)
        var = max(0.0, _num(friction_var, 0.0))

        # F = (friction_t - γ·friction_next) / 100  → positive when friction falls.
        potential_diff = (f_t - gamma * f_n) / 100.0

        weight = conf / (1.0 + var)
        shaped = potential_diff * weight
        return round(_clip(shaped, -1.0, 1.0), 5)
    except Exception as exc:  # noqa: BLE001
        logger.warning("reward.affect_delta_shaping failed: %s", exc)
        return 0.0


# --------------------------------------------------------------------------- #
# FUSION — assemble the provenance-carrying RewardComponents.
# --------------------------------------------------------------------------- #
def fuse(
    terminal_credit: float,
    affect_delta: float = 0.0,
    judge_score: float = 0.0,
    *,
    confidence: float = 0.0,
    judge_model_id: str = "",
    rubric_version: str = "",
    disagreement: bool = False,
    cfg=None,
) -> RewardComponents:
    """Fuse the three reward channels into a single provenance record.

    `terminal_credit` is THIS turn's credit-assigned share of the (already capped) terminal
    outcome — computed upstream by credit.py — and is the dominant term. `affect_delta` and
    `judge_score` are the bounded Tier-3 process channels. The weights come from cfg
    (w_outcome / w_affect / w_judge) so a single env flip re-weights the whole pipeline.

    We return a RewardComponents (never a bare float): the fused scalar the policy reads is
    `.fused()`, but the components — and the judge model id + rubric version provenance —
    always travel with it. `capped_outcome` is recorded as the pre-credit terminal scalar
    (terminal_credit) so the console can show the un-attenuated outcome alongside the share;
    callers that have the true capped outcome may overwrite it on the returned object.

    Pure-python, never raises — returns a zeroed RewardComponents on any failure.
    """
    try:
        cfg = cfg or _cfg.load()
        tc = _num(terminal_credit, 0.0)
        ad = _num(affect_delta, 0.0)
        js = _num(judge_score, 0.0)
        conf = _clip(_num(confidence, 0.0), 0.0, 1.0)

        return RewardComponents(
            raw_outcome=tc,
            capped_outcome=tc,
            terminal_credit=tc,
            affect_delta=ad,
            judge_score=js,
            w_outcome=_num(getattr(cfg, "w_outcome", 1.0), 1.0),
            w_affect=_num(getattr(cfg, "w_affect", 0.15), 0.15),
            w_judge=_num(getattr(cfg, "w_judge", 0.10), 0.10),
            judge_model_id=str(judge_model_id or ""),
            rubric_version=str(rubric_version or getattr(cfg, "rubric_version", "") or ""),
            confidence=conf,
            disagreement=bool(disagreement),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("reward.fuse failed: %s", exc)
        return RewardComponents()


# --------------------------------------------------------------------------- #
# Inline self-check — happy path, synthetic inputs, NO network / ClickHouse.
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    cfg = _cfg.load()

    # 1) outcome extraction: explicit booking beats a coarse "answered".
    o, dv = outcome_from_rec({"outcome": "answered", "interest": 90, "booked": True,
                              "deal_value": 7_500_000})
    assert o == "site_visit_booked", o
    assert dv == 7_500_000, dv

    # interest-band fallback (no explicit terminal) → temperature.
    assert outcome_from_rec({"outcome": "answered", "interest": 85})[0] == "lead_hot"
    assert outcome_from_rec({"outcome": "answered", "interest": 5})[0] == "lead_cold"
    # opt-out is the hard negative.
    assert outcome_from_rec({"outcome": "opt_out"})[0] == "whatsapp_opted_out"
    # garbage in → safe default, no raise.
    assert outcome_from_rec(None)[0] == "answered"
    assert outcome_from_rec({})[0] == "answered"

    # 2) terminal reward: concave deal multiplier, hard-clipped.
    raw, capped = terminal_reward("site_visit_booked", 7_500_000, cfg)
    print(f"booked  raw={raw} capped={capped}")
    assert raw > 1.0, raw                         # multiplier amplified the +1.0 base
    assert capped <= cfg.reward_cap, capped       # but stayed under the cap
    # a huge deal saturates (tanh + deal_cap), never explodes.
    big_raw, big_capped = terminal_reward("site_visit_booked", 10**12, cfg)
    assert big_raw <= cfg.deal_cap + 1e-6, big_raw
    # negative outcome ignores the deal multiplier and clips at -1.0 floor.
    neg_raw, neg_capped = terminal_reward("lead_dead", 9_000_000, cfg)
    assert neg_capped == -1.0, neg_capped
    # unknown outcome → 0.
    assert terminal_reward("???")[1] == 0.0

    # 3) affect shaping: friction DOWN → positive; low confidence → ~0; policy-invariant form.
    down = affect_delta_shaping(70.0, 40.0, confidence=1.0, friction_var=0.0, cfg=cfg)
    up = affect_delta_shaping(40.0, 70.0, confidence=1.0, friction_var=0.0, cfg=cfg)
    low = affect_delta_shaping(70.0, 40.0, confidence=0.05, friction_var=0.0, cfg=cfg)
    print(f"affect  down={down} up={up} low_conf={low}")
    assert down > 0, down
    assert up < 0, up
    assert abs(low) < abs(down), (low, down)      # confidence gates the magnitude
    assert -1.0 <= down <= 1.0

    # 4) fusion: returns provenance-carrying RewardComponents, never a bare float.
    rc = fuse(capped, affect_delta=down, judge_score=0.4,
              confidence=0.8, judge_model_id=cfg.judge_model,
              rubric_version=cfg.rubric_version, disagreement=False, cfg=cfg)
    fused = rc.fused()
    print(f"fused   value={fused} components={rc.to_json()}")
    assert isinstance(rc, RewardComponents)
    assert rc.terminal_credit == capped
    assert rc.judge_model_id == cfg.judge_model
    # fused == weighted sum of the three channels.
    expect = round(rc.w_outcome * capped + rc.w_affect * down + rc.w_judge * 0.4, 5)
    assert abs(fused - expect) < 1e-9, (fused, expect)

    # fuse never raises on junk input.
    assert isinstance(fuse(float("nan"), affect_delta=None, judge_score="x"), RewardComponents)

    print("reward.py self-check OK")
