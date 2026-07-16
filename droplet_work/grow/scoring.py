"""grow.scoring — L5 Lead Scoring (transparent heuristic v1, real-estate pack).

Turns the joined journey signals (voice-call outcome + WhatsApp behavior + capture
validity) into `{score 0-100, tier hot|warm|investor|end_user|junk, reasons[], confidence}`
— the deck's "hot buyer / warm prospect / investor / end-user / junk", with a one-line
"why" (GROWTH-OS §9.5). v1 is a TRANSPARENT WEIGHTED HEURISTIC (editable per industry
pack, deterministic, no model file, no network) so every score is explainable and the
features are stored WITH the score as training data for a future gradient-boosted v2.

This is pure business logic — the IP no OSS gives you. stdlib-only; never raises.
"""
from __future__ import annotations

import logging
from typing import Callable, Optional

from .config import GrowConfig
from .model import (LeadTier, ScoredLead, ScoringInput, mask_phone, principal_ref)

log = logging.getLogger("grow.scoring")

# outcomes that hard-disqualify regardless of any positive signal
_DNC_OUTCOMES = {"dnc", "do_not_call", "opted_out", "opt_out", "not_interested", "wrong_number"}


class LeadScorer:
    """Construct once with a GrowConfig; `.score(ScoringInput) -> ScoredLead`.

    The weights below are the real-estate pack. They are intentionally legible (an
    operator can read them) and sum so that a genuinely qualified buyer clears the hot
    threshold while a cheap form-filler stays warm/junk — the whole point of the loop
    (don't scale garbage, §11 / ElevateX feedback loop)."""

    # ---- weights (real-estate v1) -------------------------------------------------
    W_ANSWERED = 8
    W_TALK_60S = 10            # answered call ≥60s = the platform-grade quality signal
    W_TALK_180S = 6           # a deep ≥3-min conversation, on top of the 60s bonus
    W_BUDGET = 18             # stated a budget => real buyer intent
    W_TIMELINE = 12           # stated a purchase timeline
    W_AUTHORITY = 10          # talking to the actual decision-maker
    W_SITE_VISIT = 20         # site-visit ready (the deck's north-star intent)
    W_BOOKING = 26            # actually booked a visit => near-certain hot
    W_WA_REPLY = 6
    W_WA_DEPTH = 6            # ≥3 inbound WA turns
    W_INTEREST_BLEND = 0.30   # blend 30% of the live agent's own 0-100 interest read

    def __init__(self, config: Optional[GrowConfig] = None,
                 llm_rerank: Optional[Callable[[ScoringInput, ScoredLead], ScoredLead]] = None):
        self.cfg = config or GrowConfig()
        # optional v2 seam: a small-LLM re-ranker over the Hot bucket (deferred, off by default)
        self._llm_rerank = llm_rerank

    # ----------------------------------------------------------------- public #
    def score(self, inp: ScoringInput) -> ScoredLead:
        """Never raises — on any internal error returns a JUNK ScoredLead with a reason."""
        try:
            return self._score(inp)
        except Exception as exc:  # noqa: BLE001
            log.info("grow.scoring failed (-> junk): %r", exc)
            return ScoredLead(
                tenant_id=inp.tenant_id, lead_id=inp.lead_id, journey_id=inp.journey_id,
                score=0, tier=LeadTier.JUNK, confidence=0.0,
                reasons=["scoring_error_fail_safe"], model="heuristic_v1",
                source_platform=inp.source_platform)

    # ----------------------------------------------------------------- core #
    def _score(self, inp: ScoringInput) -> ScoredLead:
        reasons: list[str] = []
        features: dict = {}
        pts = 0
        signals_seen = 0

        # --- capture validity (hard gates) ---
        if not inp.phone_valid:
            return self._finalize(inp, 5, LeadTier.JUNK, ["invalid_phone"], 0.9,
                                  {"phone_valid": False})
        if (inp.last_outcome or "").strip().lower() in _DNC_OUTCOMES:
            return self._finalize(inp, 8, LeadTier.JUNK,
                                  [f"hard_disqualify:{inp.last_outcome}"], 0.95,
                                  {"last_outcome": inp.last_outcome})
        if inp.disposable_email:
            pts -= 10
            reasons.append("disposable_email(-10)")

        # --- voice call outcome ---
        if inp.call_answered:
            pts += self.W_ANSWERED
            reasons.append(f"answered_call(+{self.W_ANSWERED})")
            signals_seen += 1
            if inp.call_duration_s >= 60:
                pts += self.W_TALK_60S
                reasons.append(f"talk_{inp.call_duration_s}s_ge60(+{self.W_TALK_60S})")
            if inp.call_duration_s >= 180:
                pts += self.W_TALK_180S
                reasons.append(f"deep_talk_ge180s(+{self.W_TALK_180S})")
        if inp.budget_mentioned:
            pts += self.W_BUDGET
            reasons.append(f"budget_mentioned(+{self.W_BUDGET})")
            signals_seen += 1
        if inp.timeline_mentioned:
            pts += self.W_TIMELINE
            reasons.append(f"timeline_mentioned(+{self.W_TIMELINE})")
            signals_seen += 1
        if inp.decision_authority:
            pts += self.W_AUTHORITY
            reasons.append(f"decision_maker(+{self.W_AUTHORITY})")
            signals_seen += 1
        if inp.site_visit_ready:
            pts += self.W_SITE_VISIT
            reasons.append(f"site_visit_ready(+{self.W_SITE_VISIT})")
            signals_seen += 1
        if inp.booking_made:
            pts += self.W_BOOKING
            reasons.append(f"booking_made(+{self.W_BOOKING})")
            signals_seen += 1

        # --- whatsapp behavior ---
        if inp.wa_replied:
            pts += self.W_WA_REPLY
            reasons.append(f"wa_replied(+{self.W_WA_REPLY})")
            signals_seen += 1
            if inp.wa_depth >= 3:
                pts += self.W_WA_DEPTH
                reasons.append(f"wa_depth_{inp.wa_depth}(+{self.W_WA_DEPTH})")

        # --- blend the live agent's own interest read (it already extracts 0-100) ---
        if inp.interest_score > 0:
            blended = int(round(inp.interest_score * self.W_INTEREST_BLEND))
            if blended:
                pts += blended
                reasons.append(f"agent_interest_{inp.interest_score}(+{blended})")
                signals_seen += 1

        score = max(0, min(100, pts))
        # a CONFIRMED booking is committed ground-truth intent — floor it to hot so the
        # tier reflects reality even if the other points didn't add up (deck: booked = hot).
        if inp.booking_made and score < self.cfg.hot_threshold:
            score = self.cfg.hot_threshold
            reasons.append(f"booking_floor_to_hot({self.cfg.hot_threshold})")
        features = {
            "answered": inp.call_answered, "duration_s": inp.call_duration_s,
            "budget": inp.budget_mentioned, "timeline": inp.timeline_mentioned,
            "authority": inp.decision_authority, "site_visit": inp.site_visit_ready,
            "booking": inp.booking_made, "wa_replied": inp.wa_replied, "wa_depth": inp.wa_depth,
            "interest_score": inp.interest_score, "investor_intent": inp.investor_intent,
            "end_user_intent": inp.end_user_intent, "raw_points": pts,
        }
        tier = self._tier(score, inp, reasons)
        # confidence grows with how much evidence we actually observed
        confidence = round(min(1.0, 0.30 + 0.11 * signals_seen), 3)
        return self._finalize(inp, score, tier, reasons, confidence, features)

    # ----------------------------------------------------------------- tiering #
    def _tier(self, score: int, inp: ScoringInput, reasons: list) -> str:
        if score < self.cfg.junk_threshold:
            reasons.append(f"below_junk_threshold({self.cfg.junk_threshold})")
            return LeadTier.JUNK
        # persona overlay: a qualified investor routes as INVESTOR (also sales-ready)
        if inp.investor_intent and score >= self.cfg.warm_threshold:
            reasons.append("persona:investor")
            return LeadTier.INVESTOR
        if score >= self.cfg.hot_threshold:
            return LeadTier.HOT
        if score >= self.cfg.warm_threshold:
            if inp.end_user_intent:
                reasons.append("persona:end_user")
                return LeadTier.END_USER
            return LeadTier.WARM
        return LeadTier.JUNK

    # ----------------------------------------------------------------- finalize #
    def _finalize(self, inp: ScoringInput, score: int, tier: str, reasons: list,
                  confidence: float, features: dict) -> ScoredLead:
        sl = ScoredLead(
            tenant_id=inp.tenant_id, lead_id=inp.lead_id, journey_id=inp.journey_id,
            principal_ref=principal_ref(self.cfg.hash_salt, inp.phone, lead_id=inp.lead_id),
            phone_masked=mask_phone(inp.phone), score=score, tier=tier,
            confidence=confidence, reasons=reasons, features=features,
            model="heuristic_v1", source_platform=inp.source_platform)
        if self._llm_rerank is not None:
            try:
                sl = self._llm_rerank(inp, sl) or sl
            except Exception as exc:  # noqa: BLE001
                log.info("grow llm_rerank skipped: %r", exc)
        return sl
