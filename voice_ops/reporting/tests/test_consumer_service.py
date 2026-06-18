"""W14 reporting — consumer materializes FactCall from W8 events; service queries
the read-model; tenant isolation; end-to-end via the InMemoryEventBus."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from voice_kernel.events import (
    EventBusConfig,
    InMemoryEventBus,
    SinkConsumer,
)
from voice_kernel.events import taxonomy as tx

from voice_ops.reporting.config import ReportingConfig
from voice_ops.reporting.consumer import build_consumer_handler, fact_from_event
from voice_ops.reporting.model import CallStatus, LeadStatus
from voice_ops.reporting.service import ReportingService
from voice_ops.reporting.store import ReportingStore

NOW = datetime(2026, 6, 18, 12, 0, tzinfo=timezone.utc)
TS = "2026-06-18T06:00:00Z"


def test_reduce_call_lifecycle_into_one_fact():
    f = None
    f = fact_from_event(f, tx.call_started("c1", "t1", ts_iso=TS))
    assert f.call_status == CallStatus.DIALING
    f = fact_from_event(f, tx.call_connected("c1", "t1"))
    assert f.connected is True
    f = fact_from_event(f, tx.call_ended("c1", "t1", duration_s=90))
    assert f.duration_s == 90
    assert f.call_status == CallStatus.COMPLETED
    # the call's ts stays pinned to the start event (range-stable)
    assert f.ts_iso == TS


def test_reduce_summary_and_booking_promote_hot_and_funnel():
    f = fact_from_event(None, tx.call_started("c1", "t1", ts_iso=TS))
    f = fact_from_event(f, tx.summary_ready("c1", "t1", lifecycle="warm", conversion_prob=0.55,
                                            summary="Interested, wants brochure", next_action="Send brochure"))
    assert f.lead_status == LeadStatus.WARM
    assert f.interested is True
    assert f.ai_summary == "Interested, wants brochure"
    assert f.next_action == "Send brochure"
    assert f.conversion_prob == 55
    f = fact_from_event(f, tx.site_visit_booked("c1", "t1", slot_ts="2026-06-20T10:00:00Z"))
    assert f.booked is True
    assert f.lead_status == LeadStatus.HOT
    assert f.funnel_stage == "booked"


def test_handler_upserts_latest_wins():
    store = ReportingStore()
    handler = build_consumer_handler(store)

    async def run():
        await handler(tx.call_started("c1", "t1", ts_iso=TS))
        await handler(tx.call_connected("c1", "t1"))
        await handler(tx.lead_classified("c1", "t1", "hot", conversion_prob=0.9))
    asyncio.run(run())
    f = store.get("t1", "c1")
    assert f is not None
    assert f.connected is True
    assert f.lead_status == LeadStatus.HOT
    # one row, not three
    assert len(store.scan("t1")) == 1


def test_handler_skips_non_call_events_and_never_raises():
    store = ReportingStore()
    handler = build_consumer_handler(store)

    async def run():
        await handler(tx.daily_report("t1", report_date="2026-06-18"))
        await handler(tx.config_changed("t1", namespace="profile", version=2))
        # missing tenant/call -> dropped, no raise
        await handler(tx.make_event("call_started", "", "", {}))
    asyncio.run(run())
    assert store.scan("t1") == []


def test_service_metric_matches_aggregate_live():
    """The AI-Manager reads the SAME numbers the dashboard report shows."""
    store = ReportingStore()
    handler = build_consumer_handler(store)

    async def run():
        for cid in ("c1", "c2", "c3"):
            await handler(tx.call_started(cid, "t1", ts_iso=TS))
        await handler(tx.call_connected("c1", "t1"))
        await handler(tx.call_connected("c2", "t1"))
        await handler(tx.lead_classified("c1", "t1", "hot", conversion_prob=0.9))
        await handler(tx.site_visit_booked("c1", "t1"))
    asyncio.run(run())

    svc = ReportingService(store=store)
    report = svc.report("t1", "today", now=NOW)
    assert report["totals"]["calls"] == 3
    assert report["totals"]["connected"] == 2
    assert report["totals"]["booked"] == 1
    # metric() must equal the report's totals (no separate stale path)
    assert svc.metric("t1", "connected", "today", now=NOW) == report["totals"]["connected"]
    assert svc.metric("t1", "booked", "today", now=NOW) == report["totals"]["booked"]
    assert svc.metric("t1", "calls", "today", now=NOW) == report["totals"]["calls"]


def test_tenant_isolation_no_cross_bleed():
    store = ReportingStore()
    handler = build_consumer_handler(store)

    async def run():
        await handler(tx.call_started("a1", "tenantA", ts_iso=TS))
        await handler(tx.call_started("b1", "tenantB", ts_iso=TS))
        await handler(tx.lead_classified("b1", "tenantB", "hot"))
    asyncio.run(run())
    svc = ReportingService(store=store)
    assert svc.report("tenantA", "today", now=NOW)["totals"]["calls"] == 1
    assert svc.report("tenantB", "today", now=NOW)["totals"]["calls"] == 1
    # tenantA sees ZERO hot leads; tenantB sees 1
    assert svc.metric("tenantA", "hot", "today", now=NOW) == 0
    assert svc.metric("tenantB", "hot", "today", now=NOW) == 1
    # an empty tenant query is fail-closed (no rows)
    assert svc.report("", "today", now=NOW)["totals"]["calls"] == 0


def test_hot_leads_lists_names_and_next_actions():
    store = ReportingStore()
    handler = build_consumer_handler(store)

    async def run():
        await handler(tx.call_started("c1", "t1", ts_iso=TS, lead_name="Asha"))
        await handler(tx.summary_ready("c1", "t1", lifecycle="hot", conversion_prob=0.9,
                                       summary="Ready to buy", next_action="Send agreement"))
        await handler(tx.site_visit_booked("c1", "t1"))
    asyncio.run(run())
    svc = ReportingService(store=store)
    hot = svc.hot_leads("t1", "today", now=NOW)
    assert len(hot) == 1
    assert hot[0]["name"] == "Asha"
    assert hot[0]["booked"] is True
    assert hot[0]["next_action"] == "Send agreement"


def test_end_to_end_via_in_memory_event_bus():
    """Prove the real SinkConsumer drives the reporting handler off a tenant stream."""
    cfg = EventBusConfig()
    bus = InMemoryEventBus(cfg)
    store = ReportingStore()
    handler = build_consumer_handler(store)
    rcfg = ReportingConfig()
    consumer = SinkConsumer(bus, cfg, "t1", rcfg.consumer_group, handler)

    async def run():
        await bus.emit(tx.call_started("c1", "t1", ts_iso=TS))
        await bus.emit(tx.call_connected("c1", "t1"))
        await bus.emit(tx.lead_classified("c1", "t1", "hot"))
        task = asyncio.create_task(consumer.run())
        # let the consumer drain
        for _ in range(50):
            await asyncio.sleep(0.01)
            if store.get("t1", "c1") and store.get("t1", "c1").lead_status == LeadStatus.HOT:
                break
        consumer.stop()
        bus.close()
        await asyncio.sleep(0.05)
        task.cancel()
    asyncio.run(run())

    svc = ReportingService(store=store)
    assert svc.metric("t1", "connected", "today", now=NOW) == 1
    assert svc.metric("t1", "hot", "today", now=NOW) == 1
