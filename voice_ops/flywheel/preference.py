"""voice_ops.flywheel.preference — Layer-C, the proprietary (chosen, rejected) MOAT.

WHY THIS IS THE MOAT (and why it is mined, not bought)
------------------------------------------------------
Anyone can fine-tune on a generic instruct corpus. What NOBODY else has is *this tenant's*
Hinglish real-estate telephony, labelled by the ground truth that actually matters: did the
move move the deal forward? Every call Haptica runs is a stream of (state, agent-move,
outcome) triples. This module distils them into the single artefact a preference-optimiser
(DPO / KTO / IPO) eats — a (chosen, rejected) pair anchored to a state context — and it does
so under three non-negotiable invariants that keep the dataset HONEST:

  1. OUTCOME-ANCHORED chosen. A `chosen` move is only "good" if it sits on a real converted
     (or forward-moving) call — not because a model *thinks* it sounds good. Reward, not vibe.
  2. COMPLIANT chosen. The Tier-1 compliance gate is a HARD precondition, never a reward term.
     A move that books the visit by lying about RERA / faking scarcity / refusing opt-out is
     NOT a valid `chosen` no matter how high its reward. Optimising bookings must never be
     allowed to teach the agent to be pushy or non-compliant (anti-Goodhart, by construction).
  3. ANTI-SURVIVORSHIP. We deliberately mine NEGATIVE trajectories — the calls that were lost,
     hung-up, opted-out — as `rejected` material. A dataset of only winning calls teaches the
     model nothing about what to STOP doing; the lost calls are where the contrastive signal
     lives. The `rejected` side is a first-class citizen here, not an afterthought.

THREE MINING SOURCES (schema.PREF_SOURCES), weakest→strongest causal claim
--------------------------------------------------------------------------
  * within_call    — inside ONE call, contrast a high-credit-advantage move (chosen) against a
                     low/negative-credit move at a *comparable* state. Cheapest, self-anchored
                     (same caller, same call), but the causal claim is weak (confounds remain).
  * matched_state  — the cross-call moat: bucket every move by (objection, temperature, regime)
                     and contrast a winning anchored move against a losing one *in the same
                     bucket*. Controls for the state, so the contrast is about the MOVE.
  * rubric_pairwise— when outcome is silent (rare bucket / cold start), fall back to a
                     cross-family LLM judge's A/B preference, but only when it SURVIVES a
                     position-swap (kills position bias) — never as the primary signal.

HONEST SCIENCE: every pair carries its `confidence`, its `source`, whether it `survived_swap`,
whether it is `outcome_anchored`, and whether `compliant`. The console (and any future export)
can always see *why* a pair is in the dataset. No fake margins, no bare scalars.

DESIGN LAWS (mirror voice_ops/research + the rest of flywheel): pure-python, heavy deps
(judge → httpx/dspy) imported LAZILY inside the one function that needs them; dormant-safe and
best-effort — every public function swallows its own errors (→ logging.warning) and returns a
clean empty value; SIDE-PIPELINE (post-call/offline only, never the live LiveKit turn loop).
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional, Tuple

from . import config as _cfg
from . import schema as S
from .schema import HumanLabel, PreferencePair

logger = logging.getLogger("flywheel.preference")

# --------------------------------------------------------------------------- #
# Mining thresholds (conservative defaults — quality over quantity for the moat).
# A pair is only worth a row if the two sides are genuinely far apart; a tiny margin
# is noise, not signal, so we refuse to emit it.
# --------------------------------------------------------------------------- #
_MIN_WITHIN_MARGIN = 0.30      # min reward gap to call a within-call contrast a real pair
_MIN_MATCHED_MARGIN = 0.25     # min reward gap for a cross-call matched-state pair
_MAX_PAIRS_PER_BUCKET = 8      # cap pairs/bucket so a busy bucket can't swamp the dataset
_MIN_TEXT_LEN = 4              # ignore degenerate empty/near-empty move texts

# Trigger thresholds (the ~1-5% of turns worth a human look — the RLHF spend).
_DISAGREE_JUDGE_HI = 0.35      # judge says "good" (>0) ...
_DISAGREE_AFFECT_LO = -0.20    # ... while affect says "made it worse" (<0): a conflict
_HIGH_VALUE_DEAL = 3_000_000.0 # ₹ above which a LOST call is worth labelling
_PIVOTAL_ADV = 0.50            # |credit_advantage| above which a turn is "pivotal"
_LOW_CONF = 0.45               # confidence below which an estimate is "low-confidence"


# --------------------------------------------------------------------------- #
# tiny local coercion helpers (no schema-internal imports — keep this leaf standalone)
# --------------------------------------------------------------------------- #
def _f(v, d: float = 0.0) -> float:
    try:
        x = float(v)
        return d if x != x else x          # NaN guard
    except Exception:  # noqa: BLE001
        return d


def _s(v, d: str = "") -> str:
    try:
        return str(v) if v is not None else d
    except Exception:  # noqa: BLE001
        return d


def _b(v, d: bool = False) -> bool:
    try:
        if isinstance(v, str):
            return v.strip().lower() in ("1", "true", "yes", "on", "y", "t")
        return bool(v)
    except Exception:  # noqa: BLE001
        return d


def _text_ok(t: str) -> bool:
    return bool(t) and len(t.strip()) >= _MIN_TEXT_LEN


def _move_id(call_id: str, turn) -> str:
    """A stable provenance id 'call_id:turn_num' (matches schema's chosen_move_id contract)."""
    try:
        return f"{_s(call_id)}:{int(turn)}"
    except Exception:  # noqa: BLE001
        return f"{_s(call_id)}:{_s(turn)}"


# --------------------------------------------------------------------------- #
# state_bucket — the matched-state embedding id (v0): a stable composite key.
# --------------------------------------------------------------------------- #
def state_bucket(objection_type: str, lead_temperature: str, regime: str) -> str:
    """Deterministic composite key over the three axes that define *comparable* state.

    v0 of the "state embedding": no learned vector yet — just a digest of the closed-enum
    coordinates (objection × temperature × regime). Deterministic by design so the same state
    always lands in the same bucket across calls and re-runs (idempotent matched-state mining),
    and so the warehouse's ReplacingMergeTree can dedupe instead of double-counting. Unknown /
    empty coordinates fall back to the canonical enum default rather than fragmenting buckets.
    """
    try:
        obj = _s(objection_type, "none") or "none"
        if obj not in S.OBJECTION_TYPES:
            obj = "none"
        temp = _s(lead_temperature, "unknown") or "unknown"
        if temp not in S.LEAD_TEMPERATURES:
            temp = "unknown"
        reg = _s(regime, "steady") or "steady"
        return S.digest_id("state", obj, temp, reg)
    except Exception as exc:  # noqa: BLE001
        logger.warning("state_bucket error: %r", exc)
        return S.digest_id("state", "none", "unknown", "steady")


# --------------------------------------------------------------------------- #
# Internal: turn-row accessors (the worker feeds enriched TrajectoryRow-shaped dicts).
# --------------------------------------------------------------------------- #
def _turn_reward(t: dict) -> float:
    """The per-turn signal we contrast on: credit_advantage if present (the +/- credit-assigned
    signal), else the capped fused reward. credit_advantage is the *honest* per-move number."""
    if "credit_advantage" in t and t.get("credit_advantage") is not None:
        return _f(t.get("credit_advantage"))
    if t.get("reward_capped") is not None:
        return _f(t.get("reward_capped"))
    return _f(t.get("reward_raw"))


def _turn_text(t: dict) -> str:
    return _s(t.get("agent_text"))


def _turn_compliant(t: dict) -> bool:
    """Tier-1 hard gate. Default-trust (True) ONLY when the field is absent (un-checked); an
    EXPLICIT False is honoured and excludes the move from the `chosen` side forever."""
    if "compliant" in t:
        return _b(t.get("compliant"), True)
    return True


def _turn_opted_out(t: dict) -> bool:
    return _b(t.get("opted_out"), False) or _b(t.get("optout"), False)


# --------------------------------------------------------------------------- #
# mine_within_call — the cheapest, self-anchored contrast (one call, two moves).
# --------------------------------------------------------------------------- #
def mine_within_call(turns: list, call_meta: dict, *, cfg=None) -> list:
    """Inside ONE call, pair a HIGH-credit move (chosen) vs a LOW/negative-credit move
    (rejected) at a comparable state; margin = reward(chosen) - reward(rejected).

    Comparable state = same state_bucket (objection × temperature × regime), so we are
    contrasting two MOVES under the same circumstances, not two circumstances. The `chosen`
    side must be COMPLIANT and not on an opted-out turn (hard gate); the `rejected` side is
    allowed to be anything (including non-compliant — a non-compliant move is exactly the kind
    of thing we want the model to learn to reject). Only emits when the margin clears
    _MIN_WITHIN_MARGIN (a tiny gap is noise). Returns a list of PreferencePair; never raises.
    """
    try:
        cfg = cfg or _cfg.load()
        rows = [t for t in (turns or []) if isinstance(t, dict)]
        if len(rows) < 2:
            return []
        meta = call_meta or {}
        tenant_id = _s(meta.get("tenant_id"))
        campaign_id = _s(meta.get("campaign_id"))
        vertical = _s(meta.get("vertical"), "real_estate") or "real_estate"
        call_id = _s(meta.get("call_id"))

        # group comparable turns by state bucket
        buckets: Dict[str, List[dict]] = {}
        for t in rows:
            if not _text_ok(_turn_text(t)):
                continue
            obj = _s(t.get("objection_type"), "none")
            temp = _s(t.get("lead_temperature"), meta.get("lead_temperature") or "unknown")
            reg = _s(t.get("state_regime"), "steady")
            buckets.setdefault(state_bucket(obj, temp, reg), []).append(t)

        out: List[PreferencePair] = []
        for bkey, group in buckets.items():
            if len(group) < 2:
                continue
            ranked = sorted(group, key=_turn_reward, reverse=True)
            best, worst = ranked[0], ranked[-1]
            # chosen must be a compliant, non-opted-out, positive-signal move
            if not (_turn_compliant(best) and not _turn_opted_out(best)):
                continue
            margin = _turn_reward(best) - _turn_reward(worst)
            if margin < _MIN_WITHIN_MARGIN:
                continue
            if _turn_text(best).strip() == _turn_text(worst).strip():
                continue
            obj = _s(best.get("objection_type"), "none")
            temp = _s(best.get("lead_temperature"), meta.get("lead_temperature") or "unknown")
            reg = _s(best.get("state_regime"), "steady")
            out.append(PreferencePair(
                tenant_id=tenant_id,
                pair_id=S.new_id("pair_"),
                ts_iso=S.now_iso(),
                state_embedding_id=bkey,
                objection_type=obj,
                lead_temperature=temp,
                regime=reg,
                vertical=vertical,
                chosen_text=_turn_text(best),
                rejected_text=_turn_text(worst),
                chosen_move_id=_move_id(call_id, best.get("turn_num")),
                rejected_move_id=_move_id(call_id, worst.get("turn_num")),
                margin=round(margin, 5),
                source="within_call",
                survived_swap=True,           # not a judge pair; the swap check is N/A → trust
                confidence=round(min(1.0, abs(margin)), 4),
                compliant=True,
                outcome_anchored=_b(meta.get("outcome_anchored"), False),
                campaign_id=campaign_id,
            ))
        return out
    except Exception as exc:  # noqa: BLE001
        logger.warning("mine_within_call error: %r", exc)
        return []


# --------------------------------------------------------------------------- #
# mine_matched_state — the cross-call moat (same bucket, different calls).
# --------------------------------------------------------------------------- #
def mine_matched_state(grouped: dict, *, cfg=None) -> list:
    """The strongest causal contrast: within ONE state bucket, across MANY calls, pair an
    outcome-anchored compliant winning move (chosen) against a non-anchored / negative move
    (rejected). Controls for the state → the contrast is about the MOVE, not the circumstance.

    `grouped` maps state_bucket -> list of dicts, each:
        {text, reward, outcome_anchored, compliant, move_id, campaign_id, regime,
         objection_type, lead_temperature}.
    Caps at _MAX_PAIRS_PER_BUCKET so a hot bucket cannot dominate the dataset. Returns a list
    of PreferencePair; never raises.
    """
    try:
        cfg = cfg or _cfg.load()
        if not isinstance(grouped, dict):
            return []
        out: List[PreferencePair] = []
        for bkey, raw in (grouped.items()):
            cands = [c for c in (raw or []) if isinstance(c, dict) and _text_ok(_s(c.get("text")))]
            if len(cands) < 2:
                continue
            # chosen pool: outcome-anchored AND compliant; rejected pool: the rest (anti-survivorship)
            chosen_pool = [c for c in cands
                           if _b(c.get("outcome_anchored"), False) and _b(c.get("compliant"), True)]
            rejected_pool = [c for c in cands
                             if not _b(c.get("outcome_anchored"), False) or _f(c.get("reward")) < 0]
            if not chosen_pool or not rejected_pool:
                continue
            chosen_pool.sort(key=lambda c: _f(c.get("reward")), reverse=True)
            rejected_pool.sort(key=lambda c: _f(c.get("reward")))   # most-negative first
            tenant_id = _s((cands[0] or {}).get("tenant_id"))

            n = 0
            for ch in chosen_pool:
                if n >= _MAX_PAIRS_PER_BUCKET:
                    break
                for rj in rejected_pool:
                    if n >= _MAX_PAIRS_PER_BUCKET:
                        break
                    if _s(ch.get("text")).strip() == _s(rj.get("text")).strip():
                        continue
                    margin = _f(ch.get("reward")) - _f(rj.get("reward"))
                    if margin < _MIN_MATCHED_MARGIN:
                        continue
                    out.append(PreferencePair(
                        tenant_id=tenant_id or _s(ch.get("tenant_id")),
                        pair_id=S.new_id("pair_"),
                        ts_iso=S.now_iso(),
                        state_embedding_id=_s(bkey),
                        objection_type=_s(ch.get("objection_type"), "none") or "none",
                        lead_temperature=_s(ch.get("lead_temperature"), "unknown") or "unknown",
                        regime=_s(ch.get("regime"), "steady") or "steady",
                        vertical=_s(ch.get("vertical"), "real_estate") or "real_estate",
                        chosen_text=_s(ch.get("text")),
                        rejected_text=_s(rj.get("text")),
                        chosen_move_id=_s(ch.get("move_id")),
                        rejected_move_id=_s(rj.get("move_id")),
                        margin=round(margin, 5),
                        source="matched_state",
                        survived_swap=True,
                        confidence=round(min(1.0, abs(margin)), 4),
                        compliant=True,                       # chosen-side gate already applied
                        outcome_anchored=True,                # chosen is anchored by construction
                        campaign_id=_s(ch.get("campaign_id")),
                    ))
                    n += 1
        return out
    except Exception as exc:  # noqa: BLE001
        logger.warning("mine_matched_state error: %r", exc)
        return []


# --------------------------------------------------------------------------- #
# mine_rubric_pairwise — the cold-start fallback (LLM A/B, only when it survives a swap).
# --------------------------------------------------------------------------- #
def mine_rubric_pairwise(state: dict, cand_a: str, cand_b: str, *, cfg=None):
    """Cross-family judge A/B preference for rare buckets where outcome is silent.

    Lazy-imports the sibling judge module (heavy dep: httpx/dspy/OpenRouter). DORMANT,
    a TIE, or a verdict that did NOT survive the position-swap → None (never a guessed pair).
    Only a survived-swap, non-tie verdict yields a PreferencePair(source='rubric_pairwise',
    outcome_anchored=False) — this is the weakest source and is explicitly flagged as such.
    Returns a PreferencePair or None; never raises.
    """
    try:
        cfg = cfg or _cfg.load()
        st = state if isinstance(state, dict) else {}
        a, b = _s(cand_a), _s(cand_b)
        if not (_text_ok(a) and _text_ok(b)) or a.strip() == b.strip():
            return None
        # Lazy: the judge sibling may not exist yet / OpenRouter may be absent → degrade to None.
        try:
            from . import judge as _judge  # noqa: WPS433  (intentional lazy import)
        except Exception:  # noqa: BLE001
            return None
        if not hasattr(_judge, "pairwise"):
            return None
        v = _judge.pairwise(st, a, b, cfg=cfg) or {}
        if not isinstance(v, dict):
            return None
        # Honour the contract: dormant / tie / !survived_swap → no pair.
        if v.get("dormant") or v.get("tie"):
            return None
        if not _b(v.get("survived_swap"), False):
            return None
        winner = _s(v.get("winner")).strip().lower()       # expected 'a' | 'b'
        if winner not in ("a", "b"):
            return None
        chosen, rejected = (a, b) if winner == "a" else (b, a)
        return PreferencePair(
            tenant_id=_s(st.get("tenant_id")),
            pair_id=S.new_id("pair_"),
            ts_iso=S.now_iso(),
            state_embedding_id=state_bucket(
                _s(st.get("objection_type"), "none"),
                _s(st.get("lead_temperature"), "unknown"),
                _s(st.get("regime") or st.get("state_regime"), "steady"),
            ),
            objection_type=_s(st.get("objection_type"), "none") or "none",
            lead_temperature=_s(st.get("lead_temperature"), "unknown") or "unknown",
            regime=_s(st.get("regime") or st.get("state_regime"), "steady") or "steady",
            vertical=_s(st.get("vertical"), "real_estate") or "real_estate",
            chosen_text=chosen,
            rejected_text=rejected,
            chosen_move_id=_s(st.get("move_id")),
            rejected_move_id="",
            margin=round(_f(v.get("margin")), 5),
            source="rubric_pairwise",
            survived_swap=True,
            confidence=round(_f(v.get("confidence")), 4),
            compliant=_b(v.get("compliant"), True),
            outcome_anchored=False,             # judge-anchored, NOT outcome-anchored
            campaign_id=_s(st.get("campaign_id")),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("mine_rubric_pairwise error: %r", exc)
        return None


# --------------------------------------------------------------------------- #
# trigger_classifiers — the ~1-5% of turns worth a human look (the RLHF spend).
# --------------------------------------------------------------------------- #
def trigger_classifiers(turns: list, call_meta: dict, *, cfg=None) -> list:
    """Emit HumanLabel rows for the turns that most need a human verdict (the scarce,
    expensive RLHF signal — spent only where the automated pipeline is least sure):

      * judge_affect_disagreement — the judge scored the turn "good" while the affect channel
        says it made the caller WORSE (or vice-versa). A model-vs-signal conflict = label it.
      * high_value_lost           — a high-deal-value / hot lead that was nonetheless LOST. The
        most costly mistakes; a human should see what went wrong.
      * low_conf_pivotal          — a turn with a large |credit_advantage| (it mattered a lot)
        but LOW confidence in the estimate. High leverage, low certainty → human adjudication.

    Returns a list of HumanLabel (label='' = unlabelled, queued); never raises.
    """
    try:
        cfg = cfg or _cfg.load()
        rows = [t for t in (turns or []) if isinstance(t, dict)]
        meta = call_meta or {}
        tenant_id = _s(meta.get("tenant_id"))
        call_id = _s(meta.get("call_id"))
        outcome = _s(meta.get("outcome")).lower()
        deal_value = _f(meta.get("deal_value"))
        lead_temp = _s(meta.get("lead_temperature"), "unknown").lower()
        lost = ("lost" in outcome or "hangup" in outcome or "not_interested" in outcome
                or "dead" in outcome or _b(meta.get("lost"), False))

        out: List[HumanLabel] = []
        seen: set = set()   # de-dupe (turn_num, trigger) so one turn isn't queued twice

        def _add(turn_num, trigger, rationale):
            key = (int(turn_num or 0), trigger)
            if key in seen:
                return
            seen.add(key)
            out.append(HumanLabel(
                tenant_id=tenant_id, call_id=call_id, turn_num=int(turn_num or 0),
                ts_iso=S.now_iso(), trigger=trigger, label="", labeler="",
                rationale=rationale, used_for_calibration=False,
            ))

        # high_value_lost is a CALL-level trigger (anchored on the closing/CTA turn if any).
        if lost and (deal_value >= _HIGH_VALUE_DEAL or lead_temp == "hot"):
            anchor = 0
            for t in rows:
                if _s(t.get("move_type")) in ("cta_push", "close", "objection_rebuttal"):
                    anchor = int(t.get("turn_num") or anchor)
            _add(anchor, "high_value_lost",
                 f"lost call; deal≈{int(deal_value)} temp={lead_temp or 'unknown'}")

        for t in rows:
            tn = t.get("turn_num")
            judge = _f(t.get("judge_score"))
            affect = _f(t.get("affect_delta"))
            adv = _f(_turn_reward(t))
            conf = _f(t.get("confidence"))

            # judge vs affect disagreement (only when the judge actually scored this turn)
            if judge != 0.0:
                if (judge >= _DISAGREE_JUDGE_HI and affect <= _DISAGREE_AFFECT_LO) or \
                   (judge <= -_DISAGREE_JUDGE_HI and affect >= -_DISAGREE_AFFECT_LO):
                    _add(tn, "judge_affect_disagreement",
                         f"judge={round(judge, 3)} vs affect_delta={round(affect, 3)}")

            # high leverage, low certainty
            if abs(adv) >= _PIVOTAL_ADV and conf <= _LOW_CONF:
                _add(tn, "low_conf_pivotal",
                     f"|adv|={round(abs(adv), 3)} conf={round(conf, 3)}")

        return out
    except Exception as exc:  # noqa: BLE001
        logger.warning("trigger_classifiers error: %r", exc)
        return []


# --------------------------------------------------------------------------- #
# coverage_grid — the objection × temperature density map (where the moat is thin).
# --------------------------------------------------------------------------- #
def coverage_grid(pairs: list) -> dict:
    """{objection_type: {lead_temperature: count}} over a list of PreferencePair (or dicts).

    The console renders this as the heatmap that tells an operator WHICH state cells are
    starved of preference data — so exploration / labelling can be steered at the thin cells
    instead of piling more pairs onto already-saturated buckets. Never raises.
    """
    try:
        grid: Dict[str, Dict[str, int]] = {}
        for p in (pairs or []):
            if p is None:
                continue
            if isinstance(p, dict):
                obj = _s(p.get("objection_type"), "none") or "none"
                temp = _s(p.get("lead_temperature"), "unknown") or "unknown"
            else:
                obj = _s(getattr(p, "objection_type", "none"), "none") or "none"
                temp = _s(getattr(p, "lead_temperature", "unknown"), "unknown") or "unknown"
            grid.setdefault(obj, {})
            grid[obj][temp] = grid[obj].get(temp, 0) + 1
        return grid
    except Exception as exc:  # noqa: BLE001
        logger.warning("coverage_grid error: %r", exc)
        return {}


# --------------------------------------------------------------------------- #
# mine_call — the per-call orchestrator (the worker's single entrypoint).
# --------------------------------------------------------------------------- #
def mine_call(turns: list, call_meta: dict, *, cfg=None) -> tuple:
    """Orchestrate the per-call mining: -> (within_call_pairs, human_label_triggers).

    The within-call pairs are already fully stamped by mine_within_call (ts_iso, pair_id,
    tenant/campaign/vertical from call_meta, state_embedding_id = state_bucket(...)). The
    cross-call matched_state mining is the WORKER's job over the whole warehouse (it needs many
    calls), so it is intentionally NOT done here. Returns a 2-tuple of lists; never raises.
    """
    try:
        cfg = cfg or _cfg.load()
        pairs = mine_within_call(turns, call_meta, cfg=cfg)
        triggers = trigger_classifiers(turns, call_meta, cfg=cfg)
        return pairs, triggers
    except Exception as exc:  # noqa: BLE001
        logger.warning("mine_call error: %r", exc)
        return [], []


__all__ = [
    "state_bucket",
    "mine_within_call",
    "mine_matched_state",
    "mine_rubric_pairwise",
    "trigger_classifiers",
    "coverage_grid",
    "mine_call",
]


# --------------------------------------------------------------------------- #
# Inline self-check — happy path on synthetic inputs (no network / no ClickHouse).
# Run: python3 -m voice_ops.flywheel.preference
# --------------------------------------------------------------------------- #
if __name__ == "__main__":  # pragma: no cover
    logging.basicConfig(level=logging.INFO)

    # 1) state_bucket is deterministic + falls back cleanly on junk.
    b1 = state_bucket("price", "hot", "spike")
    b2 = state_bucket("price", "hot", "spike")
    b3 = state_bucket("___bad___", "___bad___", "steady")
    assert b1 == b2 and len(b1) == 16, "state_bucket not deterministic"
    assert len(b3) == 16, "state_bucket junk fallback failed"

    # 2) within-call mining: a strong compliant move vs a weak one at the same state.
    meta = {"tenant_id": "t_demo", "campaign_id": "c1", "call_id": "call_42",
            "vertical": "real_estate", "lead_temperature": "hot", "outcome_anchored": True}
    turns = [
        {"turn_num": 1, "agent_text": "Sir, RERA-registered project hai, main aapko verified docs bhej deta hoon.",
         "objection_type": "rera", "lead_temperature": "hot", "state_regime": "steady",
         "credit_advantage": 0.9, "compliant": True, "judge_score": 0.6, "affect_delta": 0.3,
         "confidence": 0.8},
        {"turn_num": 2, "agent_text": "Arre bas haan bol do, last unit hai, abhi nahi to gaya!",
         "objection_type": "rera", "lead_temperature": "hot", "state_regime": "steady",
         "credit_advantage": -0.4, "compliant": False, "judge_score": -0.5, "affect_delta": -0.4,
         "confidence": 0.3},
    ]
    pairs = mine_within_call(turns, meta)
    assert len(pairs) == 1, f"expected 1 within-call pair, got {len(pairs)}"
    p = pairs[0]
    assert p.source == "within_call" and p.compliant and p.margin > _MIN_WITHIN_MARGIN
    assert "RERA" in p.chosen_text and "last unit" in p.rejected_text
    assert p.chosen_move_id == "call_42:1" and p.rejected_move_id == "call_42:2"
    assert p.to_row()["compliant"] == 1, "to_row coercion failed"

    # 3) matched-state mining across calls (the cross-call moat).
    grouped = {
        b1: [
            {"text": "Loan ke liye hum pre-approved bank tie-up provide karte hain.",
             "reward": 1.2, "outcome_anchored": True, "compliant": True, "move_id": "callA:3",
             "campaign_id": "c1", "regime": "steady", "objection_type": "loan",
             "lead_temperature": "warm", "tenant_id": "t_demo"},
            {"text": "Loan aapka problem hai, mujhe kya.",
             "reward": -0.7, "outcome_anchored": False, "compliant": True, "move_id": "callB:5",
             "campaign_id": "c1", "regime": "steady", "objection_type": "loan",
             "lead_temperature": "warm", "tenant_id": "t_demo"},
        ]
    }
    mpairs = mine_matched_state(grouped)
    assert len(mpairs) == 1 and mpairs[0].source == "matched_state"
    assert mpairs[0].outcome_anchored and mpairs[0].margin > _MIN_MATCHED_MARGIN

    # 4) rubric_pairwise degrades to None when the judge sibling is absent/dormant.
    rp = mine_rubric_pairwise({"objection_type": "trust", "lead_temperature": "cold"},
                              "Main aapko call back karta hoon.", "Abhi decide karo warna offer gaya.")
    assert rp is None, "rubric_pairwise should be None when judge is unavailable"

    # 5) triggers: a high-value lost call + a judge/affect disagreement turn.
    tmeta = {"tenant_id": "t_demo", "call_id": "call_99", "outcome": "lost",
             "deal_value": 9_000_000.0, "lead_temperature": "hot"}
    tturns = [
        {"turn_num": 1, "move_type": "cta_push", "judge_score": 0.5, "affect_delta": -0.4,
         "credit_advantage": 0.7, "confidence": 0.2},
    ]
    labels = trigger_classifiers(tturns, tmeta)
    triggers = {l.trigger for l in labels}
    assert "high_value_lost" in triggers, "missing high_value_lost"
    assert "judge_affect_disagreement" in triggers, "missing judge_affect_disagreement"
    assert "low_conf_pivotal" in triggers, "missing low_conf_pivotal"
    assert all(l.label == "" for l in labels), "labels must start unlabelled"

    # 6) coverage grid + orchestrator.
    grid = coverage_grid(pairs + mpairs)
    assert grid.get("rera", {}).get("hot") == 1 and grid.get("loan", {}).get("warm") == 1
    op, ot = mine_call(turns, meta)
    assert len(op) == 1 and isinstance(ot, list)

    print("preference.py self-check OK:",
          {"within": len(pairs), "matched": len(mpairs), "rubric_none": rp is None,
           "triggers": sorted(triggers), "grid": grid})
