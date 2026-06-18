"""voice_kernel.events — the event-driven real-time backbone (W8).

The founder's "nothing updates in real time" fix: every meaningful action in a
call's life emits ONE typed Event on a Redis Stream; dashboard / CRM / analytics /
AI-Manager / reports all react instantly from that single source of truth instead
of polling stale rows. Plus a canonical timestamp layer (store UTC, render in the
vendor's tz) that fixes "timeline shows 1 day ago for a call just now".

This package is DISJOINT and additive: it imports ONLY from voice_kernel.contracts
(the frozen Event/EventBus surface) — never from droplet_work, never from agent.py
or caller.py. It is inert until a LATER founder-signed seam wave registers a bus
and flips EVENTBUS_ENABLED (default OFF -> NullEventBus -> zero behavior change).
See design/W8-EVENT-SEAM.md.

Public surface:
  - RedisEventBus       — the production EventBus over Redis Streams
  - InMemoryEventBus    — dependency-free EventBus (tests + local fallback)
  - EventBusConfig      — knobs + tenant-scoped stream-key helpers
  - SinkConsumer        — per-sink consume loop (dedup + handler)
  - reclaim_and_dlq     — XAUTOCLAIM janitor + dead-letter routing
  - EventName + factories (taxonomy) — the closed typed event taxonomy
  - timeutil            — canonical UTC store / vendor-tz render helpers
"""
from __future__ import annotations

from .bus import RedisEventBus
from .config import EventBusConfig
from .consumer import SinkConsumer, reclaim_and_dlq
from .fake import InMemoryEventBus
from .serde import decode, encode, idempotency_id
from . import taxonomy, timeutil
from .taxonomy import (
    EventName,
    call_connected,
    call_ended,
    call_failed,
    call_started,
    callback_scheduled,
    daily_report,
    handoff_done,
    handoff_requested,
    lead_classified,
    make_event,
    provider_failed,
    recording_ready,
    site_visit_booked,
    summary_ready,
    transcript_ready,
    whatsapp_sent,
)
from .timeutil import (
    VENDOR_TZ_NAME,
    ensure_utc,
    humanize,
    now_utc,
    now_utc_iso,
    parse_iso,
    render_vendor,
    to_vendor,
    vendor_date,
)

__all__ = [
    # bus + config
    "RedisEventBus",
    "InMemoryEventBus",
    "EventBusConfig",
    "SinkConsumer",
    "reclaim_and_dlq",
    # serde
    "encode",
    "decode",
    "idempotency_id",
    # taxonomy
    "EventName",
    "make_event",
    "call_started",
    "call_connected",
    "call_ended",
    "call_failed",
    "recording_ready",
    "transcript_ready",
    "summary_ready",
    "lead_classified",
    "callback_scheduled",
    "site_visit_booked",
    "handoff_requested",
    "handoff_done",
    "whatsapp_sent",
    "provider_failed",
    "daily_report",
    "taxonomy",
    # timeutil
    "timeutil",
    "VENDOR_TZ_NAME",
    "now_utc",
    "now_utc_iso",
    "ensure_utc",
    "parse_iso",
    "to_vendor",
    "render_vendor",
    "vendor_date",
    "humanize",
]
