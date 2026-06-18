"""W14 reporting — aggregation: totals recalc per range, drill-down filters,
funnel math, timeline, agent/source/follow-up analytics, tenant isolation."""
from __future__ import annotations

from datetime import datetime, timezone

from voice_ops.reporting.daterange import resolve_range
from voice_ops.reporting.model import (
    BookingStatus,
    CallStatus,
    FactCall,
    LeadStatus,
)
from voice_ops.reporting import aggregate as agg

NOW = datetime(2026, 6, 18, 12, 0, tzinfo=timezone.utc)
T = "t1"


def _fact(call_id, ts, **kw):
    return FactCall(tenant_id=T, call_id=call_id, ts_iso=ts, **kw)


def _rows():
    # 3 today (IST), 1 yesterday, distributed across stages/statuses/agents/sources.
    return [
        _fact("c1", "2026-06-18T06:00:00Z", funnel_stage="converted", connected=True,
              interested=True, booked=True, converted=True, lead_status=LeadStatus.HOT,
              call_status=CallStatus.COMPLETED, booking_status=BookingStatus.BOOKED,
              agent="riya", source="meta", campaign_id="camp-A", duration_s=120,
              lead_name="Asha", conversion_prob=88),
        _fact("c2", "2026-06-18T07:00:00Z", funnel_stage="warm", connected=True,
              interested=True, lead_status=LeadStatus.WARM, call_status=CallStatus.COMPLETED,
              agent="riya", source="google", campaign_id="camp-A", duration_s=60,
              callback_scheduled=True, whatsapp_sent=True),
        _fact("c3", "2026-06-18T08:00:00Z", funnel_stage="dialed",
              lead_status=LeadStatus.COLD, call_status=CallStatus.NO_ANSWER,
              agent="meera", source="meta", campaign_id="camp-B"),
        # yesterday IST (this is 2026-06-17 ~23:00 IST -> still 06-17)
        _fact("c4", "2026-06-17T15:00:00Z", funnel_stage="hot", connected=True,
              interested=True, lead_status=LeadStatus.HOT, call_status=CallStatus.COMPLETED,
              agent="meera", source="meta", campaign_id="camp-A", duration_s=200,
              lead_name="Vik", conversion_prob=80),
    ]


def test_totals_recalculate_per_range():
    rows = _rows()
    today = agg.aggregate(rows, resolve_range("today", now=NOW))
    yest = agg.aggregate(rows, resolve_range("yesterday", now=NOW))
    assert today["totals"]["calls"] == 3
    assert yest["totals"]["calls"] == 1
    # today: c1+c2 connected, c3 no-answer
    assert today["totals"]["connected"] == 2
    assert today["totals"]["booked"] == 1
    assert today["totals"]["converted"] == 1
    assert today["totals"]["hot"] == 1
    assert today["totals"]["warm"] == 1
    assert today["totals"]["no_answer"] == 1
    # yesterday: only c4
    assert yest["totals"]["connected"] == 1
    assert yest["totals"]["hot"] == 1


def test_7d_covers_all_four():
    rows = _rows()
    r = agg.aggregate(rows, resolve_range("7d", now=NOW))
    assert r["totals"]["calls"] == 4


def test_rates_no_div_by_zero():
    r = agg.aggregate([], resolve_range("today", now=NOW))
    assert r["totals"]["connect_rate"] == 0.0
    assert r["totals"]["avg_talk_time_s"] == 0.0


def test_drilldown_by_campaign():
    rows = _rows()
    r = agg.aggregate(rows, resolve_range("7d", now=NOW), {"campaign": "camp-A"})
    # c1, c2, c4 are camp-A
    assert r["totals"]["calls"] == 3
    r2 = agg.aggregate(rows, resolve_range("7d", now=NOW), {"campaign": "camp-B"})
    assert r2["totals"]["calls"] == 1


def test_drilldown_by_lead_status():
    rows = _rows()
    r = agg.aggregate(rows, resolve_range("7d", now=NOW), {"lead_status": "hot"})
    assert r["totals"]["calls"] == 2  # c1, c4


def test_drilldown_by_source_and_agent_combined():
    rows = _rows()
    r = agg.aggregate(rows, resolve_range("7d", now=NOW), {"source": "meta", "agent": "riya"})
    assert r["totals"]["calls"] == 1  # only c1 is meta+riya


def test_drilldown_by_call_status():
    rows = _rows()
    r = agg.aggregate(rows, resolve_range("today", now=NOW), {"call_status": "no_answer"})
    assert r["totals"]["calls"] == 1


def test_drilldown_by_booking_status():
    rows = _rows()
    r = agg.aggregate(rows, resolve_range("7d", now=NOW), {"booking_status": "booked"})
    assert r["totals"]["calls"] == 1


def test_funnel_math_is_monotone_cumulative():
    rows = _rows()
    funnel = {s["stage"]: s["count"] for s in agg.build_funnel(agg.in_range(rows, resolve_range("7d", now=NOW)))}
    # all 4 reached 'uploaded' and 'dialed'
    assert funnel["uploaded"] == 4
    assert funnel["dialed"] == 4
    # connected: c1,c2,c4 (c3 only dialed)
    assert funnel["connected"] == 3
    # interested: c1,c2,c4
    assert funnel["interested"] == 3
    # warm stage reached by c1(>=warm),c2(=warm),c4(>=warm) = 3
    assert funnel["warm"] == 3
    # hot reached by c1(converted>hot), c4(hot) = 2
    assert funnel["hot"] == 2
    # booked: c1 only
    assert funnel["booked"] == 1
    # converted: c1 only
    assert funnel["converted"] == 1
    # monotone non-increasing
    counts = [funnel[s] for s in ("uploaded", "dialed", "connected", "interested", "warm", "hot", "booked", "converted")]
    assert counts == sorted(counts, reverse=True)


def test_funnel_step_conv_pct():
    rows = _rows()
    funnel = {s["stage"]: s for s in agg.build_funnel(agg.in_range(rows, resolve_range("7d", now=NOW)))}
    # connected/dialed = 3/4 = 75%
    assert funnel["connected"]["step_conv"] == 75.0
    # booked/hot = 1/2 = 50%
    assert funnel["booked"]["step_conv"] == 50.0


def test_agent_performance():
    rows = _rows()
    agents = {a["key"]: a for a in agg.agent_performance(agg.in_range(rows, resolve_range("7d", now=NOW)))}
    assert agents["riya"]["calls"] == 2
    assert agents["riya"]["booked"] == 1
    assert agents["meera"]["calls"] == 2


def test_source_analytics():
    rows = _rows()
    srcs = {s["key"]: s for s in agg.source_analytics(agg.in_range(rows, resolve_range("7d", now=NOW)))}
    assert srcs["meta"]["calls"] == 3  # c1,c3,c4
    assert srcs["google"]["calls"] == 1


def test_followup_analytics():
    rows = _rows()
    fu = agg.followup_analytics(agg.in_range(rows, resolve_range("today", now=NOW)))
    assert fu["callbacks_scheduled"] == 1
    assert fu["whatsapp_followups"] == 1


def test_daily_timeline_zero_filled_and_correct_days():
    rows = _rows()
    rng = resolve_range("7d", now=NOW)
    tl = agg.daily_timeline(rows, rng)
    assert len(tl) == 7
    days = {row["date"]: row for row in tl}
    assert days["2026-06-18"]["calls"] == 3
    assert days["2026-06-17"]["calls"] == 1
    # a day with no calls is present + zero
    assert days["2026-06-15"]["calls"] == 0


def test_status_breakdowns():
    rows = _rows()
    bd = agg.status_breakdowns(agg.in_range(rows, resolve_range("7d", now=NOW)))
    assert bd["lead_status"]["hot"] == 2
    assert bd["call_status"]["no_answer"] == 1
