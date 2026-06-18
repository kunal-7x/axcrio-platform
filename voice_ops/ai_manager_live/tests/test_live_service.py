"""W14 AI-Manager — live adapter returns numbers matching the reporting layer;
daily summary lists hot leads + next actions; delivery dormant; tenant-isolated."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from voice_kernel.events import taxonomy as tx

from voice_ops.reporting.consumer import build_consumer_handler
from voice_ops.reporting.service import ReportingService
from voice_ops.reporting.store import ReportingStore

from voice_ops.ai_manager_live.adapter import LiveAdapter
from voice_ops.ai_manager_live.config import AIManagerLiveConfig
from voice_ops.ai_manager_live.delivery import ReportDelivery, NullWhatsAppSender
from voice_ops.ai_manager_live.service import AIManagerLiveService
from voice_ops.ai_manager_live.summary import build_daily_summary

NOW = datetime(2026, 6, 18, 12, 0, tzinfo=timezone.utc)
TS = "2026-06-18T06:00:00Z"


def _seeded_store():
    store = ReportingStore()
    h = build_consumer_handler(store)

    async def run():
        # 4 calls today for tenant t1
        for cid in ("c1", "c2", "c3", "c4"):
            await h(tx.call_started(cid, "t1", ts_iso=TS, campaign_id="camp-A"))
        await h(tx.call_connected("c1", "t1"))
        await h(tx.call_connected("c2", "t1"))
        await h(tx.call_connected("c4", "t1"))
        # c1 -> hot + booked (Asha)
        await h(tx.summary_ready("c1", "t1", lifecycle="hot", conversion_prob=0.9,
                                 summary="Ready to buy 2BHK", next_action="Send agreement", lead_name="Asha"))
        await h(tx.site_visit_booked("c1", "t1"))
        # c2 -> warm (Vik)
        await h(tx.summary_ready("c2", "t1", lifecycle="warm", conversion_prob=0.5,
                                 summary="Wants brochure", next_action="WhatsApp brochure", lead_name="Vik"))
        await h(tx.callback_scheduled("c2", "t1", preferred_ts="2026-06-19T10:00:00Z"))
        # c4 -> hot (Ravi)
        await h(tx.summary_ready("c4", "t1", lifecycle="hot", conversion_prob=0.8,
                                 summary="Negotiating price", next_action="Call back with offer", lead_name="Ravi"))
        # tenant t2 — must stay isolated
        await h(tx.call_started("x1", "t2", ts_iso=TS))
        await h(tx.lead_classified("x1", "t2", "hot"))
    asyncio.run(run())
    return store


def test_adapter_metric_matches_reporting_layer():
    store = _seeded_store()
    svc = ReportingService(store=store)
    adapter = LiveAdapter(svc)
    report = svc.report("t1", "today", now=NOW)
    # adapter's LIVE number == the dashboard report's totals, by construction
    assert adapter.metric("t1", "calls", "today", now=NOW) == report["totals"]["calls"] == 4
    assert adapter.metric("t1", "connected", "today", now=NOW) == report["totals"]["connected"] == 3
    assert adapter.metric("t1", "booked", "today", now=NOW) == report["totals"]["booked"] == 1
    assert adapter.metric("t1", "hot", "today", now=NOW) == report["totals"]["hot"] == 2


def test_adapter_hot_leads_have_names_and_next_actions():
    adapter = LiveAdapter(ReportingService(store=_seeded_store()))
    hot = adapter.hot_leads("t1", "today", now=NOW)
    names = {h["name"] for h in hot}
    assert names == {"Asha", "Ravi"}
    # booked lead sorts first
    assert hot[0]["name"] == "Asha"
    assert hot[0]["booked"] is True
    assert all(h["next_action"] for h in hot)


def test_campaign_performance_live():
    adapter = LiveAdapter(ReportingService(store=_seeded_store()))
    perf = adapter.campaign_performance("t1", "camp-A", "today", now=NOW)
    assert perf["matched"] is True
    assert perf["totals"]["calls"] == 4
    assert perf["totals"]["booked"] == 1


def test_daily_summary_lists_hot_leads_and_next_actions():
    adapter = LiveAdapter(ReportingService(store=_seeded_store()),
                          AIManagerLiveConfig(business_name="Godrej Properties"))
    s = build_daily_summary(adapter, "t1", preset="today", now=NOW)
    assert s.totals["calls"] == 4
    assert s.totals["hot"] == 2
    assert s.totals["booked"] == 1
    # hot-lead names present in the structured + rendered output
    hot_names = {h["name"] for h in s.hot_leads}
    assert {"Asha", "Ravi"} <= hot_names
    assert "Asha" in s.text and "Ravi" in s.text
    assert "Godrej Properties" in s.text
    # next actions include each hot lead's action + the callback nudge
    joined = " ".join(s.next_actions)
    assert "Send agreement" in joined
    assert "callback" in joined.lower()


def test_service_handle_send_report_matches_live_numbers():
    svc = AIManagerLiveService(ReportingService(store=_seeded_store()))
    env = svc.handle("t1", "send today's report", now=NOW)
    assert env["command"]["kind"] == "send_report"
    assert env["command"]["deliver"] is True
    assert env["data"]["totals"]["calls"] == 4
    assert env["data"]["totals"]["booked"] == 1
    # delivery attempted but dormant (no sender wired)
    assert env["delivery"]["status"] == "no_recipient"  # no number resolver -> fail-closed


def test_service_handle_metric_live():
    svc = AIManagerLiveService(ReportingService(store=_seeded_store()))
    env = svc.handle("t1", "how many calls today", now=NOW)
    assert env["command"]["kind"] == "metric"
    assert env["data"]["value"] == 4
    assert "4" in env["reply"]


def test_service_handle_hot_leads_live():
    svc = AIManagerLiveService(ReportingService(store=_seeded_store()))
    env = svc.handle("t1", "show hot leads", now=NOW)
    assert env["command"]["kind"] == "hot_leads"
    assert len(env["data"]["hot_leads"]) == 2
    assert "Asha" in env["reply"]


def test_tenant_isolation_in_manager():
    svc = AIManagerLiveService(ReportingService(store=_seeded_store()))
    env_t2 = svc.handle("t2", "how many calls today", now=NOW)
    assert env_t2["data"]["value"] == 1   # t2 has only x1
    env_hot_t2 = svc.handle("t2", "show hot leads", now=NOW)
    assert len(env_hot_t2["data"]["hot_leads"]) == 1
    # t1's Asha must NEVER appear for t2
    assert "Asha" not in env_hot_t2["reply"]


def test_delivery_dormant_not_configured_with_number_resolver():
    """With a number resolver but the NullSender, delivery resolves a recipient
    then reports not_configured (dormant) — never sends blind."""
    delivery = ReportDelivery(sender=NullWhatsAppSender(),
                              number_resolver=lambda t: "+919876543210")
    svc = AIManagerLiveService(ReportingService(store=_seeded_store()), delivery=delivery)
    env = svc.handle("t1", "send today's report", now=NOW)
    assert env["delivery"]["status"] == "not_configured"
    assert env["delivery"]["to"].endswith("10")  # masked recipient


def test_delivery_real_sender_injected():
    """A real (fake) sender receives the rendered body + masked recipient."""
    sent = {}

    class FakeSender:
        def send(self, to, body):
            sent["to"] = to
            sent["body"] = body
            return {"status": "sent", "id": "wamid.123"}

    delivery = ReportDelivery(sender=FakeSender(), number_resolver=lambda t: "+919876543210")
    svc = AIManagerLiveService(ReportingService(store=_seeded_store()), delivery=delivery)
    out = svc.daily_summary("t1", preset="today", now=NOW, deliver=True)
    assert out["delivery"]["status"] == "sent"
    assert sent["to"] == "+919876543210"
    assert "Daily Report" in sent["body"]
    assert "Asha" in sent["body"]


def test_unknown_command_friendly_fallback():
    svc = AIManagerLiveService(ReportingService(store=_seeded_store()))
    env = svc.handle("t1", "make me a sandwich", now=NOW)
    assert env["command"]["kind"] == "unknown"
    assert "report" in env["reply"].lower()
