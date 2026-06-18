"""voice_ops.reporting.consumer — turn W8 events into FactCall upserts (W14).

This is the SINK side of the founder's real-time fix. A `SinkConsumer`
(voice_kernel.events.consumer) runs in a SEPARATE process, subscribes to one
tenant stream, and calls `build_consumer_handler(store)(event)` for each event.
The handler REDUCES the event onto the (latest-wins) FactCall row for that call:
call_started creates the row; call_connected / summary_ready / lead_* /
callback_scheduled / site_visit_booked / whatsapp_sent / recording_ready /
transcript_ready refine the SAME row. After each reduce the row is re-upserted, so
the read-model is always the merged truth of every event seen for that call.

Reuses the W7 Lifecycle values via LeadStatus.coerce — reporting records the
classification the memory FSM already made; it does NOT re-derive it.

The handler is ASYNC (SinkConsumer awaits it) and NEVER raises — an event must
never break the sink (a raise would leave the entry in the PEL forever). On a
genuinely malformed event we log + drop. ZERO droplet import; the store backend is
injected.
"""
from __future__ import annotations

import logging
from typing import Awaitable, Callable, Optional

from voice_kernel.contracts import Event
from voice_kernel.events.taxonomy import EventName

from .model import (
    BookingStatus,
    CallStatus,
    FactCall,
    LeadStatus,
)
from .store import ReportingStore

log = logging.getLogger("voice_ops.reporting.consumer")


class EventReducer:
    """Pure reducer: (existing FactCall | None, Event) -> updated FactCall.

    Kept as a class so a future variant (e.g. PG-side reduce) can subclass, but it
    holds no state — every method is a static transform. The reducer is the single
    place that knows how each event name maps onto the read-model fields."""

    @staticmethod
    def _base(event: Event) -> FactCall:
        return FactCall(
            tenant_id=event.tenant_id,
            call_id=event.call_id,
            ts_iso=event.ts_iso,
        )

    @staticmethod
    def reduce(prior: Optional[FactCall], event: Event) -> FactCall:
        """Merge `event` onto `prior` (or a fresh base). The call's ts_iso is
        pinned to the EARLIEST event we saw (the call's start) so range-filtering
        is stable; later events refine measures/dimensions, not the timestamp —
        except a row that started life on a non-start event keeps its first ts."""
        f = prior.copy() if prior is not None else EventReducer._base(event)
        p = event.payload or {}
        name = event.name

        # Common dimensions: any event may carry these refinements.
        if p.get("campaign_id"):
            f.campaign_id = str(p["campaign_id"])
        if p.get("source"):
            f.source = str(p["source"])
        if p.get("agent"):
            f.agent = str(p["agent"])
        if p.get("lead_name"):
            f.lead_name = str(p["lead_name"])
        if p.get("lead_phone_masked"):
            f.lead_phone_masked = str(p["lead_phone_masked"])

        if name == EventName.CALL_STARTED.value:
            # The start event defines the canonical call timestamp.
            f.ts_iso = event.ts_iso
            f.call_status = CallStatus.DIALING
            f.bump_stage("dialed")

        elif name == EventName.CALL_CONNECTED.value:
            f.connected = True
            f.call_status = CallStatus.CONNECTED
            f.bump_stage("connected")

        elif name == EventName.CALL_ENDED.value:
            f.duration_s = int(p.get("duration_s") or f.duration_s or 0)
            # a call that connected + ended is COMPLETED; else keep the last status.
            if f.connected or f.duration_s >= 8:
                f.connected = True
                f.call_status = CallStatus.COMPLETED
                f.bump_stage("connected")
            outcome = (p.get("outcome") or "").lower()
            if outcome in ("no_answer", "busy", "voicemail", "failed", "opted_out"):
                f.call_status = CallStatus(outcome) if outcome != "busy" else CallStatus.BUSY

        elif name == EventName.CALL_FAILED.value:
            reason = (p.get("reason") or "").lower()
            if "no_answer" in reason or "noanswer" in reason:
                f.call_status = CallStatus.NO_ANSWER
            elif "busy" in reason:
                f.call_status = CallStatus.BUSY
            elif "voicemail" in reason or "machine" in reason:
                f.call_status = CallStatus.VOICEMAIL
            else:
                f.call_status = CallStatus.FAILED

        elif name == EventName.RECORDING_READY.value:
            f.has_recording = True
            if p.get("duration_s"):
                f.duration_s = int(p["duration_s"])

        elif name == EventName.TRANSCRIPT_READY.value:
            f.has_transcript = True

        elif name == EventName.SUMMARY_READY.value:
            if p.get("lifecycle"):
                f.lead_status = LeadStatus.coerce(p["lifecycle"])
                EventReducer._apply_lifecycle_stage(f)
            if p.get("conversion_prob") is not None:
                try:
                    f.conversion_prob = int(round(float(p["conversion_prob"]) * (100 if float(p["conversion_prob"]) <= 1 else 1)))
                except Exception:
                    pass
            if p.get("summary"):
                f.ai_summary = str(p["summary"])[:600]
            if p.get("next_action"):
                f.next_action = str(p["next_action"])[:240]
            if p.get("interested"):
                f.interested = True
                f.bump_stage("interested")
            if p.get("converted"):
                f.converted = True
                f.bump_stage("converted")

        elif name in (EventName.LEAD_HOT.value, EventName.LEAD_WARM.value,
                      EventName.LEAD_COLD.value, EventName.LEAD_DEAD.value):
            status = {
                EventName.LEAD_HOT.value: LeadStatus.HOT,
                EventName.LEAD_WARM.value: LeadStatus.WARM,
                EventName.LEAD_COLD.value: LeadStatus.COLD,
                EventName.LEAD_DEAD.value: LeadStatus.DEAD,
            }[name]
            f.lead_status = status
            if p.get("conversion_prob") is not None:
                try:
                    cp = float(p["conversion_prob"])
                    f.conversion_prob = int(round(cp * (100 if cp <= 1 else 1)))
                except Exception:
                    pass
            EventReducer._apply_lifecycle_stage(f)

        elif name == EventName.CALLBACK_SCHEDULED.value:
            f.callback_scheduled = True
            if p.get("next_action"):
                f.next_action = str(p["next_action"])[:240]
            elif not f.next_action and p.get("preferred_ts"):
                f.next_action = f"Call back at {p['preferred_ts']}"

        elif name == EventName.SITE_VISIT_BOOKED.value:
            f.booked = True
            f.booking_status = BookingStatus.BOOKED
            f.lead_status = LeadStatus.HOT  # a booking is the strongest positive
            f.bump_stage("booked")

        elif name == EventName.HANDOFF_REQUESTED.value:
            f.handoff = True

        elif name == EventName.WHATSAPP_SENT.value:
            f.whatsapp_sent = True

        # interested marker can ride other events (e.g. summary) — already handled.
        return f

    @staticmethod
    def _apply_lifecycle_stage(f: FactCall) -> None:
        """Reflect the lead lifecycle onto the funnel + interested flag."""
        ls = getattr(f.lead_status, "value", f.lead_status)
        if ls in ("warm", "hot"):
            f.interested = True
            f.bump_stage("interested")
            f.bump_stage(ls)  # 'warm' or 'hot' are funnel stages


def fact_from_event(prior: Optional[FactCall], event: Event) -> FactCall:
    """Convenience wrapper for tests + the handler: reduce one event."""
    return EventReducer.reduce(prior, event)


# Events that are NOT call-scoped (config/key/report/provider) — the reducer
# ignores them (they don't describe a call). Kept explicit so a new taxonomy entry
# fails LOUD in tests rather than silently corrupting a row.
_NON_CALL_EVENTS = {
    EventName.PROVIDER_FAILED.value,
    EventName.DAILY_REPORT.value,
    EventName.CONFIG_CHANGED.value,
    EventName.PROVIDER_KEY_ADDED.value,
    EventName.PROVIDER_KEY_REVOKED.value,
    EventName.KEY_POOL_EXHAUSTED.value,
    EventName.HANDOFF_DONE.value,
}


def build_consumer_handler(store: ReportingStore) -> Callable[[Event], Awaitable[None]]:
    """Build the async handler a SinkConsumer drives. It reduces each call-scoped
    event onto the FactCall read-model and upserts it. Non-call events are skipped.
    NEVER raises — a bad event is logged + dropped so the sink keeps draining."""

    async def handler(event: Event) -> None:
        try:
            if not event.call_id or not event.tenant_id:
                return
            if event.name in _NON_CALL_EVENTS:
                return
            prior = store.get(event.tenant_id, event.call_id)
            merged = EventReducer.reduce(prior, event)
            store.upsert(merged)
        except Exception as exc:  # noqa: BLE001 — never break the sink loop
            log.warning("reporting handler dropped %s (non-fatal): %r",
                        getattr(event, "name", "?"), exc)

    return handler
