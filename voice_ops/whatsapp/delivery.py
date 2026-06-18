"""voice_ops.whatsapp.delivery — per-message delivery tracking (W16).

One tenant-scoped `wa_delivery` row per dispatched message, advanced LATEST-WINS
through the funnel the founder asked for:

    sent -> delivered -> read     (happy path, monotone forward-only)
    failed / opted_out            (terminal)
    skipped_no_config             (dormant — WA creds not present)

Fed two ways, both idempotent + forward-only (a late/duplicate Meta webhook never
regresses a 'read' back to 'delivered'):

  * the SEND orchestrator seeds a row at dispatch (sent / skipped_no_config);
  * the Meta status webhook calls `on_status(...)` (delivered/read/failed) — this is
    the seam the live caller.py `/whatsapp/inbound` webhook will call.

Every transition ALSO emits the matching W8 event (whatsapp_delivered/read/
failed/opted_out) fire-and-forget, so the panel + analytics react in real time
without polling. The emit is best-effort (a dead bus never breaks tracking).
ZERO redis / droplet import at module load.
"""
from __future__ import annotations

import logging
import time
from typing import Optional

from .model import DeliveryRow, DeliveryStatus
from .store import DeliveryStore

log = logging.getLogger("voice_ops.whatsapp.delivery")


class DeliveryTracker:
    """Tenant-scoped delivery tracker over a DeliveryStore + (optional) W8 EventBus.

    `event_bus` : any object with an async `emit(Event)` (RedisEventBus in prod,
                  InMemoryEventBus in tests, None = no push). Emission is fire-and-
                  forget + fail-soft — tracking persists even if the bus is dead."""

    def __init__(self, store: Optional[DeliveryStore] = None, *, event_bus=None) -> None:
        self.store = store or DeliveryStore()
        self.event_bus = event_bus

    # ------------------------------------------------------------- seed (send) -- #
    def seed(self, tenant_id: str, message_id: str, *, campaign_id: str = "", template: str = "",
             phone_masked: str = "", lead_id: str = "", media_count: int = 0,
             active: bool = True) -> DeliveryRow:
        """Create the initial row at dispatch. active=True -> 'sent'; active=False
        (dormant, no creds) -> 'skipped_no_config'. Idempotent (forward-only)."""
        status = DeliveryStatus.SENT if active else DeliveryStatus.SKIPPED_NO_CONFIG
        row = DeliveryRow(
            tenant_id=tenant_id, message_id=message_id, campaign_id=campaign_id,
            template=template, phone_masked=phone_masked, lead_id=lead_id,
            status=status, media_count=media_count, updated_at=time.time(),
            sent_at=time.time() if active else 0.0)
        self.store.upsert(row)
        return row

    # -------------------------------------------------------- webhook ingest -- #
    def on_status(self, tenant_id: str, message_id: str, status: str, *, reason: str = "",
                  campaign_id: str = "", template: str = "", phone_masked: str = "") -> bool:
        """Ingest a Meta status webhook (delivered/read/failed/opted_out). Forward-
        only (never regresses the funnel). Emits the matching W8 event. Returns True
        if the row advanced. Pulls campaign/template/phone from the existing row if
        not supplied (the webhook only carries the message id + status)."""
        if not (tenant_id or "").strip() or not (message_id or "").strip():
            return False
        st = DeliveryStatus.coerce(status)
        cur = self.store.get(tenant_id, message_id)
        now = time.time()
        row = cur.copy() if cur else DeliveryRow(tenant_id=tenant_id, message_id=message_id)
        row.status = st
        row.reason = reason or row.reason
        row.campaign_id = campaign_id or row.campaign_id
        row.template = template or row.template
        row.phone_masked = phone_masked or row.phone_masked
        row.updated_at = now
        if st == DeliveryStatus.DELIVERED:
            row.delivered_at = now
        elif st == DeliveryStatus.READ:
            row.read_at = now
            if not row.delivered_at:
                row.delivered_at = now
        elif st == DeliveryStatus.FAILED:
            row.failed_at = now

        advanced = self.store.upsert(row)
        if advanced:
            self._emit(st, row)
        return advanced

    # --------------------------------------------------------------- queries -- #
    def list(self, tenant_id: str, *, campaign_id: str = "") -> list[DeliveryRow]:
        return self.store.list(tenant_id, campaign_id=campaign_id)

    def summary(self, tenant_id: str, *, campaign_id: str = "") -> dict:
        return self.store.summary(tenant_id, campaign_id=campaign_id)

    # ----------------------------------------------------------------- emit -- #
    def _emit(self, status: DeliveryStatus, row: DeliveryRow) -> None:
        bus = self.event_bus
        if bus is None:
            return
        try:
            from voice_kernel.events import (
                whatsapp_delivered, whatsapp_read, whatsapp_failed, whatsapp_opted_out,
            )
        except Exception as exc:  # noqa: BLE001
            log.info("delivery event factories unavailable: %r", exc)
            return
        factory = {
            DeliveryStatus.DELIVERED: lambda: whatsapp_delivered(
                row.message_id, row.tenant_id, campaign_id=row.campaign_id,
                template=row.template, phone_masked=row.phone_masked),
            DeliveryStatus.READ: lambda: whatsapp_read(
                row.message_id, row.tenant_id, campaign_id=row.campaign_id,
                template=row.template, phone_masked=row.phone_masked),
            DeliveryStatus.FAILED: lambda: whatsapp_failed(
                row.message_id, row.tenant_id, campaign_id=row.campaign_id,
                template=row.template, reason=row.reason, phone_masked=row.phone_masked),
            DeliveryStatus.OPTED_OUT: lambda: whatsapp_opted_out(
                row.message_id, row.tenant_id, campaign_id=row.campaign_id,
                phone_masked=row.phone_masked),
        }.get(status)
        if factory is None:
            return
        self._fire(bus, factory())

    @staticmethod
    def _fire(bus, event) -> None:
        """Fire-and-forget emit (mirrors voice_ops.config.events._emit). Never raises,
        never blocks. Schedules a task in an async context; runs to completion on a
        throwaway loop in a sync context."""
        import asyncio
        try:
            coro = bus.emit(event)
        except Exception as exc:  # noqa: BLE001
            log.warning("delivery emit setup failed (non-fatal): %r", exc)
            return

        async def _guard():
            try:
                await coro
            except Exception as exc:  # noqa: BLE001
                log.warning("delivery emit failed (non-fatal): %r", exc)

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop is not None:
            task = loop.create_task(_guard())
            task.add_done_callback(lambda t: t.exception() if not t.cancelled() else None)
            return
        try:
            asyncio.run(_guard())
        except Exception as exc:  # noqa: BLE001
            log.warning("delivery emit failed (non-fatal): %r", exc)
