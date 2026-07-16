"""grow.orchestrator — L3 Speed-to-Lead (the "60-second call", demystified).

The mechanism the deck calls magic, done honestly (ElevateX §1): the instant a
CONSENT-CLEAN lead raises its hand (Meta/Google leadgen form, CTWA, or a landing-page
form), this orchestrator — within the <60s window where intent is hot (71% of leads go
cold after 5 min) — mints the journey, runs the India-compliance preflight gate
(TCCPR/DPDP/DND), and fires WhatsApp + an outbound AI call IN PARALLEL, threading one
correlation_id through every event. The qualified call outcome then flows back into the
W1 scoring + CAPI signal loop. Capture → fire latency + SLA are recorded.

SEAM-BASED so it's fully offline-testable and never couples to the live spine: the
compliance gate, the WhatsApp sender, and the voice caller are INJECTED callables. The
defaults are dormant-safe (compliance = unenforced when the engine is off; channels =
skipped_no_config when not wired) — exactly the house posture. Real adapters
(voice_ops.compliance + the WhatsApp Cloud API + caller dial) are bound at wiring time,
never edited into the shared caller.py from here. NEVER raises.
"""
from __future__ import annotations

import logging
from typing import Callable, Optional

from .config import GrowConfig
from .model import (CapturedLead, ChannelResult, ChannelStatus, Journey, OrchStatus,
                    Orchestration, _now, mask_phone, principal_ref)

log = logging.getLogger("grow.orchestrator")

# A compliance gate returns (decision, reasons). decision in allow|block|soft|unenforced.
ComplianceGate = Callable[[CapturedLead, Journey], "tuple[str, list]"]
# A channel sender returns a ChannelResult.
ChannelSender = Callable[[CapturedLead, Journey], ChannelResult]


def _default_compliance(_c: CapturedLead, _j: Journey) -> "tuple[str, list]":
    """No gate wired => UNENFORCED (the compliance engine is OFF by default). The real
    voice_ops ComplianceEngine is injected at wiring time; until then we don't fabricate
    a pass — we mark it unenforced so the audit is honest."""
    return "unenforced", ["compliance_engine_not_wired"]


def _default_whatsapp(_c: CapturedLead, _j: Journey) -> ChannelResult:
    return ChannelResult(channel="whatsapp", status=ChannelStatus.SKIPPED_NO_CONFIG,
                         reason="no_whatsapp_sender_wired")


def _default_voice(_c: CapturedLead, _j: Journey) -> ChannelResult:
    return ChannelResult(channel="voice", status=ChannelStatus.SKIPPED_NO_CONFIG,
                         reason="no_voice_caller_wired")


class Orchestrator:
    """Construct with a GrowConfig + a JourneyStore + (optional) injected seams.
    `orchestrate(CapturedLead) -> Orchestration`. Used by GrowLoop.on_lead_captured."""

    def __init__(self, config: Optional[GrowConfig] = None, journeys=None, *,
                 compliance_gate: Optional[ComplianceGate] = None,
                 whatsapp_sender: Optional[ChannelSender] = None,
                 voice_caller: Optional[ChannelSender] = None,
                 sla_seconds: int = 60,
                 now_fn: Optional[Callable[[], object]] = None,
                 emit: Optional[Callable[[str, dict], None]] = None):
        self.cfg = config or GrowConfig()
        self.journeys = journeys
        self.compliance_gate = compliance_gate or _default_compliance
        self.whatsapp_sender = whatsapp_sender or _default_whatsapp
        self.voice_caller = voice_caller or _default_voice
        self.sla_seconds = max(1, int(sla_seconds))
        self._now = now_fn or _now
        self._emit = emit or (lambda _t, _p: None)

    def orchestrate(self, captured: CapturedLead) -> Orchestration:
        """Never raises — on any internal error returns an ERROR Orchestration."""
        try:
            return self._orchestrate(captured)
        except Exception as exc:  # noqa: BLE001
            log.info("grow.orchestrate failed: %r", exc)
            jid = ""
            try:
                jid = self._journey_id(captured)
            except Exception:  # noqa: BLE001
                pass
            return Orchestration(tenant_id=captured.tenant_id, journey_id=jid,
                                 lead_id=captured.lead_id, status=OrchStatus.ERROR,
                                 compliance_reasons=[f"error:{exc!r}"[:160]])

    # --------------------------------------------------------------- internals #
    def _journey_id(self, c: CapturedLead) -> str:
        from .model import capi_hash
        return "j_" + capi_hash(f"{c.tenant_id}|{c.lead_id}")[:20]

    def _ensure_journey(self, c: CapturedLead) -> Journey:
        jid = self._journey_id(c)
        j = self.journeys.get(c.tenant_id, jid) if self.journeys else None
        if j is None:
            j = Journey(tenant_id=c.tenant_id, journey_id=jid,
                        principal_ref=principal_ref(self.cfg.hash_salt, c.phone, lead_id=c.lead_id),
                        phone_masked=mask_phone(c.phone), source_platform=c.source_platform,
                        source_ad_id=c.source_ad_id, ctwa_clid=c.ctwa_clid, fbclid=c.fbclid,
                        gclid=c.gclid)
        else:
            if c.source_platform and not j.source_platform: j.source_platform = c.source_platform
            if c.source_ad_id and not j.source_ad_id: j.source_ad_id = c.source_ad_id
            if c.ctwa_clid and not j.ctwa_clid: j.ctwa_clid = c.ctwa_clid
            if c.fbclid and not j.fbclid: j.fbclid = c.fbclid
            if c.gclid and not j.gclid: j.gclid = c.gclid
        if self.journeys:
            self.journeys.upsert(j)
        return j

    def _orchestrate(self, c: CapturedLead) -> Orchestration:
        if not (c.tenant_id or "").strip() or not (c.lead_id or "").strip():
            return Orchestration(tenant_id=c.tenant_id or "", journey_id="", lead_id=c.lead_id,
                                 status=OrchStatus.ERROR, compliance_reasons=["missing_tenant_or_lead"])
        journey = self._ensure_journey(c)
        self._emit("lead.captured", {"tenant_id": c.tenant_id, "journey_id": journey.journey_id,
                                     "lead_id": c.lead_id, "source": c.source_platform})

        # --- compliance preflight (TCCPR place-call / DPDP / DND) ---
        decision, reasons = self.compliance_gate(c, journey)
        channels: list[ChannelResult] = []
        if decision == "block":
            self._emit("lead.disqualified", {"tenant_id": c.tenant_id,
                                             "journey_id": journey.journey_id, "reason": "compliance_block"})
            orch = self._finish(c, journey, OrchStatus.BLOCKED, decision, reasons,
                                [ChannelResult("whatsapp", ChannelStatus.BLOCKED, reason="compliance_block"),
                                 ChannelResult("voice", ChannelStatus.BLOCKED, reason="compliance_block")])
            return orch

        # --- fire channels (parallel in production; seams here return their result) ---
        wa = self._safe_channel(self.whatsapp_sender, c, journey, "whatsapp")
        call = self._safe_channel(self.voice_caller, c, journey, "voice")
        channels = [wa, call]
        if wa.status == ChannelStatus.FIRED:
            self._emit("wa.message.sent", {"tenant_id": c.tenant_id, "journey_id": journey.journey_id,
                                           "ref": wa.ref})
        if call.status == ChannelStatus.FIRED:
            self._emit("call.initiated", {"tenant_id": c.tenant_id, "journey_id": journey.journey_id,
                                          "ref": call.ref})

        any_fired = any(ch.status == ChannelStatus.FIRED for ch in channels)
        status = OrchStatus.DONE if any_fired else OrchStatus.NO_CHANNELS
        return self._finish(c, journey, status, decision, reasons, channels)

    def _safe_channel(self, sender: ChannelSender, c: CapturedLead, j: Journey,
                      name: str) -> ChannelResult:
        try:
            r = sender(c, j)
            return r if isinstance(r, ChannelResult) else ChannelResult(name, ChannelStatus.FAILED,
                                                                         reason="bad_sender_return")
        except Exception as exc:  # noqa: BLE001
            log.info("grow channel %s failed: %r", name, exc)
            return ChannelResult(name, ChannelStatus.FAILED, reason=f"error:{exc!r}"[:120])

    def _finish(self, c: CapturedLead, j: Journey, status: str, decision: str,
                reasons: list, channels: list) -> Orchestration:
        completed = self._now()
        captured_at = c.captured_at or completed
        latency_ms = max(0, int((completed - captured_at).total_seconds() * 1000))
        sla_met = (completed - captured_at).total_seconds() <= self.sla_seconds
        return Orchestration(
            tenant_id=c.tenant_id, journey_id=j.journey_id, lead_id=c.lead_id, status=status,
            compliance_decision=decision, compliance_reasons=list(reasons), channels=channels,
            latency_ms=latency_ms, sla_seconds=self.sla_seconds, sla_met=sla_met,
            captured_at=captured_at, completed_at=completed)


# =========================================================================== #
# Real-adapter factories — bound at wiring time (never imported at module load).
# These keep the live couplings OUT of this module so it stays offline-testable.
# =========================================================================== #
def make_compliance_gate() -> Optional[ComplianceGate]:
    """Return a gate backed by voice_ops.compliance.ComplianceEngine if it's importable
    AND enabled, else None (caller falls back to the unenforced default). The engine's
    preflight is async; we run it on a fresh loop in the worker thread the orchestrator
    is already dispatched on (off the main event loop)."""
    try:
        import asyncio  # noqa: PLC0415
        from voice_ops.compliance.engine import ComplianceEngine  # type: ignore  # noqa: PLC0415
        from voice_ops.compliance.config import ComplianceConfig  # type: ignore  # noqa: PLC0415
    except Exception:  # noqa: BLE001
        return None
    try:
        cfg = ComplianceConfig.from_env()
        if not getattr(cfg, "enabled", False):
            return None
        engine = ComplianceEngine(cfg)
    except Exception:  # noqa: BLE001
        return None

    def _gate(c: CapturedLead, j: Journey) -> "tuple[str, list]":
        try:
            lead = {"phone": c.phone, "lead_id": c.lead_id}
            camp = {"campaign_id": c.campaign_id}
            dec = asyncio.run(engine.preflight(c.tenant_id, lead, camp))
            allow = getattr(dec, "allow", None)
            reasons = list(getattr(dec, "reasons", []) or [])
            if allow is True:
                return "allow", reasons or ["compliance_pass"]
            if getattr(dec, "soft", False):
                return "soft", reasons
            return "block", reasons or ["compliance_block"]
        except Exception as exc:  # noqa: BLE001 — fail-closed on a gate error
            return "block", [f"compliance_error:{exc!r}"[:120]]

    return _gate
