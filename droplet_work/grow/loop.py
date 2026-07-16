"""grow.loop — the Signal-Loop orchestrator facade (the one thing the backend calls).

Ties L5 scoring + L7 signal dispatch + the journey spine + stores into a handful of
fire-and-forget methods. caller.py's post-call touchpoint (_finalize_call) calls
`grow.on_call_outcome(...)` behind FEATURE_GROW; the booking + sale hooks climb the CAPI
event ladder. EVERY method is wrapped so it can NEVER raise into the live call/booking
path (a Grow error must never break an earner call). A process-wide lazy singleton keeps
the InMemory stores warm across requests.
"""
from __future__ import annotations

import logging
import os
import threading
from typing import Optional

from .config import GrowConfig
from .model import (CapturedLead, Journey, Ladder, ScoredLead, ScoringInput, capi_hash,
                    mask_phone, principal_ref)
from .acquisition import AcquisitionService
from .adapters import live_voice_caller, live_whatsapp_sender
from .metrics import GrowMetrics
from .optimizer import Optimizer
from .orchestrator import Orchestrator, make_compliance_gate
from .scoring import LeadScorer
from .signals import SignalDispatcher
from .store import make_stores

log = logging.getLogger("grow.loop")


class GrowLoop:
    def __init__(self, config: Optional[GrowConfig] = None, stores=None, *,
                 whatsapp_sender=None, voice_caller=None):
        self.cfg = config or GrowConfig.from_env()
        use_pg = (os.getenv("GROW_USE_PG", "0") or "0").strip().lower() in ("1", "true", "yes", "on")
        self.scores, self.signals_store, self.journeys, self.orchestrations = (
            stores or make_stores(use_pg=use_pg))
        self.scorer = LeadScorer(self.cfg)
        self.dispatcher = SignalDispatcher(self.cfg, self.signals_store)
        # L3 orchestrator: compliance gate auto-wires to voice_ops.compliance when ENABLED
        # (else unenforced); channels stay dormant (skipped_no_config) until real adapters
        # are injected at wiring time — never coupling grow to the live spine.
        # Default channel seams = the LIVE late-binding adapters (real Graph WhatsApp +
        # the voice dial caller.py registers). An explicit sender (tests) overrides them.
        self.orchestrator = Orchestrator(
            self.cfg, self.journeys, compliance_gate=make_compliance_gate(),
            whatsapp_sender=whatsapp_sender or live_whatsapp_sender,
            voice_caller=voice_caller or live_voice_caller,
            sla_seconds=60, emit=self._emit_event)
        # L1 acquisition: parse Meta/Google/CTWA payloads -> record consent -> capture
        self.acquisition = AcquisitionService(self)
        # L8 metrics: the funnel + the semantic metrics layer (CPqL north star)
        self.metrics = GrowMetrics(self)
        # L7 ad-optimization brain (Draft/Trash/Promote). Live execute is connector-gated.
        self.optimizer = Optimizer()

    @staticmethod
    def _emit_event(etype: str, payload: dict) -> None:
        # fire-and-forget event log (a later wave can bridge to voice_kernel.events / the bus)
        log.info("grow.event %s %s", etype, payload)

    # --------------------------------------------------------------- journeys #
    def journey_id_for(self, tenant_id: str, lead_id: str, given: str = "") -> str:
        if given:
            return given
        return "j_" + capi_hash(f"{tenant_id}|{lead_id}")[:20]

    def ensure_journey(self, tenant_id: str, lead_id: str, *, journey_id: str = "",
                       phone: str = "", source_platform: str = "", source_ad_id: str = "",
                       ctwa_clid: str = "", fbclid: str = "", gclid: str = "") -> Journey:
        jid = self.journey_id_for(tenant_id, lead_id, journey_id)
        j = self.journeys.get(tenant_id, jid)
        if j is None:
            j = Journey(tenant_id=tenant_id, journey_id=jid,
                        principal_ref=principal_ref(self.cfg.hash_salt, phone, lead_id=lead_id),
                        phone_masked=mask_phone(phone), source_platform=source_platform,
                        source_ad_id=source_ad_id, ctwa_clid=ctwa_clid, fbclid=fbclid, gclid=gclid)
        else:
            # enrich missing attribution without clobbering existing
            if source_platform and not j.source_platform: j.source_platform = source_platform
            if source_ad_id and not j.source_ad_id: j.source_ad_id = source_ad_id
            if ctwa_clid and not j.ctwa_clid: j.ctwa_clid = ctwa_clid
            if fbclid and not j.fbclid: j.fbclid = fbclid
            if gclid and not j.gclid: j.gclid = gclid
            if not j.principal_ref:
                j.principal_ref = principal_ref(self.cfg.hash_salt, phone, lead_id=lead_id)
            if not j.phone_masked and phone:
                j.phone_masked = mask_phone(phone)
        self.journeys.upsert(j)
        return j

    # --------------------------------------------------------------- scoring #
    def score_only(self, inp: ScoringInput) -> ScoredLead:
        """Score WITHOUT persisting or dispatching — powers the /grow/score 'try-it' tool."""
        try:
            return self.scorer.score(inp)
        except Exception as exc:  # noqa: BLE001
            log.info("grow.score_only failed: %r", exc)
            return ScoredLead(tenant_id=inp.tenant_id, lead_id=inp.lead_id, score=0,
                              reasons=["score_error"])

    # ------------------------------------------- L3 speed-to-lead (W2) #
    def on_lead_captured(self, tenant_id: str, lead_id: str, *, phone: str = "", name: str = "",
                         email: str = "", source_platform: str = "", source_ad_id: str = "",
                         ctwa_clid: str = "", fbclid: str = "", gclid: str = "",
                         campaign_id: str = "", consent_basis: str = "explicit",
                         consent_channel: str = "web_form") -> dict:
        """The <60s speed-to-lead entry: a consent-clean lead arrives -> compliance gate ->
        fire WhatsApp + AI call (seams), journey-threaded, SLA-tracked. NEVER raises
        (fire-and-forget from the L1 ingest webhook)."""
        try:
            if not (tenant_id or "").strip() or not (lead_id or "").strip():
                return {"ok": False, "reason": "missing_tenant_or_lead"}
            captured = CapturedLead(
                tenant_id=tenant_id, lead_id=lead_id, phone=phone, name=name, email=email,
                source_platform=source_platform, source_ad_id=source_ad_id, ctwa_clid=ctwa_clid,
                fbclid=fbclid, gclid=gclid, campaign_id=campaign_id, consent_basis=consent_basis,
                consent_channel=consent_channel)
            orch = self.orchestrator.orchestrate(captured)
            self.orchestrations.upsert(orch)
            return {"ok": orch.status != "error", "orchestration": orch.public()}
        except Exception as exc:  # noqa: BLE001
            log.info("grow.on_lead_captured failed: %r", exc)
            return {"ok": False, "reason": f"error:{exc!r}"[:160]}

    # --------------------------------------------------------- the main hook #
    def on_call_outcome(self, tenant_id: str, lead_id: str, *, phone: str = "", name: str = "",
                        email: str = "", journey_id: str = "", source_platform: str = "",
                        source_ad_id: str = "", ctwa_clid: str = "", fbclid: str = "",
                        gclid: str = "", **outcome) -> dict:
        """Post-call touchpoint: score the lead, persist, and fire the CAPI Lead +
        (if qualified) QualifiedLead signals — shadow-safe. Returns a small summary dict.
        NEVER raises (fire-and-forget from _finalize_call)."""
        try:
            if not (tenant_id or "").strip() or not (lead_id or "").strip():
                return {"ok": False, "reason": "missing_tenant_or_lead"}
            inp = ScoringInput(
                tenant_id=tenant_id, lead_id=lead_id,
                journey_id=self.journey_id_for(tenant_id, lead_id, journey_id),
                phone=phone, name=name, source_platform=source_platform,
                phone_valid=bool(outcome.get("phone_valid", True)),
                disposable_email=bool(outcome.get("disposable_email", False)),
                call_answered=bool(outcome.get("call_answered", False)),
                call_duration_s=int(outcome.get("call_duration_s", 0) or 0),
                interest_score=int(outcome.get("interest_score", 0) or 0),
                budget_mentioned=bool(outcome.get("budget_mentioned", False)),
                timeline_mentioned=bool(outcome.get("timeline_mentioned", False)),
                decision_authority=bool(outcome.get("decision_authority", False)),
                site_visit_ready=bool(outcome.get("site_visit_ready", False)),
                booking_made=bool(outcome.get("booking_made", False)),
                investor_intent=bool(outcome.get("investor_intent", False)),
                end_user_intent=bool(outcome.get("end_user_intent", False)),
                last_outcome=str(outcome.get("last_outcome", "") or ""),
                wa_replied=bool(outcome.get("wa_replied", False)),
                wa_reply_latency_s=int(outcome.get("wa_reply_latency_s", 0) or 0),
                wa_depth=int(outcome.get("wa_depth", 0) or 0))

            scored = self.scorer.score(inp)
            self.scores.upsert(scored)

            j = self.ensure_journey(tenant_id, lead_id, journey_id=inp.journey_id, phone=phone,
                                    source_platform=source_platform, source_ad_id=source_ad_id,
                                    ctwa_clid=ctwa_clid, fbclid=fbclid, gclid=gclid)

            dispatched = []
            # ladder step 1 — Lead (value = quality score)
            ev = self.dispatcher.emit(j, scored, Ladder.LEAD, raw_phone=phone,
                                      raw_email=email, raw_name=name)
            dispatched.append(ev.public())
            # ladder step 2 — QualifiedLead (only when the truth says it's qualified)
            if self.dispatcher.should_emit_qualified(scored):
                ev2 = self.dispatcher.emit(j, scored, Ladder.QUALIFIED, raw_phone=phone,
                                           raw_email=email, raw_name=name)
                dispatched.append(ev2.public())
                if j.status == "open":
                    j.status = "qualified"
                    self.journeys.upsert(j)

            return {"ok": True, "scored": scored.public(), "journey_id": j.journey_id,
                    "signals": dispatched}
        except Exception as exc:  # noqa: BLE001
            log.info("grow.on_call_outcome failed (swallowed): %r", exc)
            return {"ok": False, "reason": f"error:{exc!r}"[:160]}

    # ---------------------------------------------------- deeper ladder hooks #
    def on_booking(self, tenant_id: str, lead_id: str, *, phone: str = "", email: str = "",
                   name: str = "", journey_id: str = "") -> dict:
        try:
            j = self.ensure_journey(tenant_id, lead_id, journey_id=journey_id, phone=phone)
            scored = self.scores.get(tenant_id, lead_id)
            ev = self.dispatcher.emit(j, scored, Ladder.SCHEDULE, raw_phone=phone,
                                      raw_email=email, raw_name=name)
            j.status = "booked"
            self.journeys.upsert(j)
            return {"ok": True, "signal": ev.public()}
        except Exception as exc:  # noqa: BLE001
            log.info("grow.on_booking failed: %r", exc)
            return {"ok": False, "reason": f"error:{exc!r}"[:160]}

    def on_sale(self, tenant_id: str, lead_id: str, *, value: int, phone: str = "",
                email: str = "", name: str = "", journey_id: str = "",
                currency: str = "INR") -> dict:
        try:
            j = self.ensure_journey(tenant_id, lead_id, journey_id=journey_id, phone=phone)
            scored = self.scores.get(tenant_id, lead_id)
            ev = self.dispatcher.emit(j, scored, Ladder.PURCHASE, value=int(value),
                                      raw_phone=phone, raw_email=email, raw_name=name,
                                      currency=currency)
            j.status = "won"
            self.journeys.upsert(j)
            return {"ok": True, "signal": ev.public()}
        except Exception as exc:  # noqa: BLE001
            log.info("grow.on_sale failed: %r", exc)
            return {"ok": False, "reason": f"error:{exc!r}"[:160]}

    # --------------------------------------------------------------- reads #
    def signal_health(self, tenant_id: str) -> dict:
        return self.dispatcher.health(tenant_id)


# =========================================================================== #
# Process-wide lazy singleton — keeps InMemory stores warm across requests.
# =========================================================================== #
_LOOP: Optional[GrowLoop] = None
_LOCK = threading.Lock()


def get_loop() -> GrowLoop:
    global _LOOP
    if _LOOP is None:
        with _LOCK:
            if _LOOP is None:
                _LOOP = GrowLoop()
    return _LOOP


def reset_loop() -> None:
    """Test helper — drop the singleton so a fresh config/env is picked up."""
    global _LOOP
    with _LOCK:
        _LOOP = None
