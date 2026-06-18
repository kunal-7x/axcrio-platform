"""voice_ops.whatsapp.send — the campaign SEND orchestrator (W16).

Assemble a campaign send: a template + attached media (banner, images, video,
brochure) -> a resolved audience -> dispatch. It is the spine that ties the media
library, audience resolver, and delivery tracker together.

FUTURE-READY / DORMANT-UNTIL-CREDS (the founder's whole requirement): the
orchestrator is fully WIRED but NEVER sends blind. It gates on the W13
`WhatsAppConfig.is_active(has_whatsapp_key)` — exactly the seam W13 built:

  * creds PRESENT  -> active run: hands each message to the (injected) sender,
    seeds a 'sent' delivery row, emits whatsapp_sent, lets the webhook advance it.
  * creds ABSENT   -> dormant run: seeds 'skipped_no_config' delivery rows so the
    panel shows EXACTLY what WOULD be sent (audience + media), and flips to live the
    moment creds land — zero code change.

The actual Meta Cloud-API call is an INJECTED `sender(plan, lead) -> message_id`
(the live caller.py whatsapp.py provides it; tests inject a stub). This module
imports ZERO requests / droplet code — it only orchestrates.
"""
from __future__ import annotations

import logging
import uuid
from typing import Callable, Optional

from .model import AudienceSpec, SendPlan, SendResult
from .audience import AudienceResolver
from .media import MediaLibrary
from .delivery import DeliveryTracker

log = logging.getLogger("voice_ops.whatsapp.send")


class SendOrchestrator:
    """Tenant-scoped campaign send orchestrator.

    `profile_hook`  : Callable[[tenant_id], (is_active: bool, reason: str)] reporting
                      whether WA creds are present (wraps W13 WhatsAppConfig.is_active).
                      Default = always-dormant (safe: nothing sends without an explicit
                      live hook).
    `sender`        : Callable[[SendPlan, lead], message_id] performing the real Meta
                      send (injected by the live seam). Only called on an active run.
    """

    def __init__(self, *, media: Optional[MediaLibrary] = None,
                 audience: Optional[AudienceResolver] = None,
                 tracker: Optional[DeliveryTracker] = None,
                 profile_hook: Optional[Callable[[str], tuple]] = None,
                 sender: Optional[Callable] = None,
                 event_bus=None) -> None:
        self.media = media or MediaLibrary()
        self.audience = audience or AudienceResolver()
        self.tracker = tracker or DeliveryTracker(event_bus=event_bus)
        self.profile_hook = profile_hook
        self.sender = sender
        self.event_bus = event_bus

    # --------------------------------------------------------------- gating -- #
    def is_active(self, tenant_id: str) -> tuple:
        """(active, reason). Default-dormant when no profile_hook is wired (a send
        will record but not dispatch). NEVER raises — a broken hook = dormant."""
        if not self.profile_hook:
            return (False, "whatsapp credentials not configured")
        try:
            active, reason = self.profile_hook(tenant_id)
            return (bool(active), reason or ("" if active else "whatsapp credentials not configured"))
        except Exception as exc:  # noqa: BLE001
            log.info("profile_hook failed -> dormant: %r", exc)
            return (False, "whatsapp config check failed")

    # ----------------------------------------------------------------- plan -- #
    def plan(self, tenant_id: str, *, template: str, media_ids=(), audience_spec: AudienceSpec) -> SendPlan:
        """Build the SendPlan: validate that referenced media exist (drop missing,
        keep order), resolve the audience. Pure (no dispatch) — the panel calls this
        for a truthful preview."""
        valid_media = []
        for mid in media_ids or ():
            if self.media.get(tenant_id, mid):
                valid_media.append(mid)
        res = self.audience.resolve(tenant_id, audience_spec)
        phones = {l.lead_id: l.phone_masked for l in res.leads}
        return SendPlan(
            tenant_id=tenant_id, template=template, media_ids=tuple(valid_media),
            audience_lead_ids=res.lead_ids, audience_phones=phones)

    # ----------------------------------------------------------------- send -- #
    def send(self, tenant_id: str, *, campaign_id: str = "", template: str, media_ids=(),
             audience_spec: AudienceSpec) -> SendResult:
        """Resolve + dispatch (or dormant-record) a campaign. ALWAYS creates delivery
        rows so the panel sees the run; only dispatches when creds are active. Bumps
        media used_count. Fail-closed on empty tenant / empty audience."""
        if not (tenant_id or "").strip():
            return SendResult(tenant_id="", reason="missing tenant")

        active, reason = self.is_active(tenant_id)
        p = self.plan(tenant_id, template=template, media_ids=media_ids, audience_spec=audience_spec)
        p.campaign_id = campaign_id

        if not p.audience_lead_ids:
            return SendResult(tenant_id=tenant_id, campaign_id=campaign_id, active=active,
                              reason="empty audience (select a target segment)")

        message_ids: list[str] = []
        dispatched = skipped = 0
        for lead_id in p.audience_lead_ids:
            phone = p.audience_phones.get(lead_id, "")
            msg_id = ""
            if active and self.sender:
                try:
                    msg_id = self.sender(p, lead_id) or ""
                except Exception as exc:  # noqa: BLE001
                    log.info("wa sender failed lead=%s: %r", lead_id, exc)
                    msg_id = ""
            # always create a row (local id pre-ack; Meta wamid replaces it post-send).
            if not msg_id:
                msg_id = f"wa_{uuid.uuid4().hex}"
            really_sent = bool(active and self.sender)
            self.tracker.seed(
                tenant_id, msg_id, campaign_id=campaign_id, template=template,
                phone_masked=phone, lead_id=lead_id, media_count=len(p.media_ids),
                active=really_sent)
            if really_sent:
                dispatched += 1
                self._emit_sent(tenant_id, msg_id, campaign_id, template)
            else:
                skipped += 1
            message_ids.append(msg_id)

        # mark attached media as used (analytics 'used in N campaigns').
        if p.media_ids:
            self.media.mark_used(tenant_id, p.media_ids)

        return SendResult(
            tenant_id=tenant_id, campaign_id=campaign_id, active=active,
            queued=len(message_ids), dispatched=dispatched, skipped_no_config=skipped,
            message_ids=tuple(message_ids),
            reason="" if active else reason)

    # ----------------------------------------------------------------- emit -- #
    def _emit_sent(self, tenant_id: str, message_id: str, campaign_id: str, template: str) -> None:
        if self.event_bus is None:
            return
        try:
            from voice_kernel.events import whatsapp_sent
            self.tracker._fire(self.event_bus, whatsapp_sent(
                message_id, tenant_id, template=template, campaign_id=campaign_id))
        except Exception as exc:  # noqa: BLE001
            log.info("whatsapp_sent emit failed (non-fatal): %r", exc)
