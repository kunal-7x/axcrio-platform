"""W14 AI-Manager — the deterministic NL command parser."""
from __future__ import annotations

from voice_ops.ai_manager_live.commands import CommandKind, parse_command


def test_send_todays_report():
    c = parse_command("send today's report")
    assert c.kind == CommandKind.SEND_REPORT
    assert c.preset == "today"
    assert c.deliver is True


def test_report_without_send_is_not_deliver():
    c = parse_command("show me today's report")
    assert c.kind == CommandKind.SEND_REPORT
    assert c.deliver is False


def test_show_hot_leads():
    c = parse_command("show hot leads")
    assert c.kind == CommandKind.HOT_LEADS
    assert c.filters["lead_status"] == "hot"


def test_show_warm_leads():
    c = parse_command("list warm leads")
    assert c.kind == CommandKind.HOT_LEADS
    assert c.filters["lead_status"] == "warm"


def test_campaign_performance():
    c = parse_command("campaign Diwali performance")
    assert c.kind == CommandKind.CAMPAIGN_PERF
    assert c.target.lower() == "diwali"


def test_campaign_perf_with_range():
    c = parse_command("campaign GodrejQ3 performance this week")
    assert c.kind == CommandKind.CAMPAIGN_PERF
    assert c.preset == "7d"
    assert "godrej" in c.target.lower()


def test_metric_how_many_calls_today():
    c = parse_command("how many calls today")
    assert c.kind == CommandKind.METRIC
    assert c.metric == "calls"
    assert c.preset == "today"


def test_metric_connect_rate_this_week():
    c = parse_command("what's the connect rate this week")
    assert c.kind == CommandKind.METRIC
    assert c.metric == "connect_rate"
    assert c.preset == "7d"


def test_metric_bookings_yesterday():
    c = parse_command("how many bookings yesterday")
    assert c.kind == CommandKind.METRIC
    assert c.metric == "booked"
    assert c.preset == "yesterday"


def test_funnel():
    c = parse_command("show me the funnel this month")
    assert c.kind == CommandKind.FUNNEL
    assert c.preset == "this-month"


def test_send_report_via_whatsapp_sets_deliver():
    c = parse_command("whatsapp me this week's summary")
    assert c.kind == CommandKind.SEND_REPORT
    assert c.preset == "7d"
    assert c.deliver is True


def test_prev_month_phrase():
    c = parse_command("send last month's report")
    assert c.kind == CommandKind.SEND_REPORT
    assert c.preset == "prev-month"


def test_empty_and_garbage_are_unknown():
    assert parse_command("").kind == CommandKind.UNKNOWN
    assert parse_command("hello there how are you").kind == CommandKind.UNKNOWN


def test_never_raises_on_weird_input():
    for s in ["", "   ", "campaign", "leads", "!!!", "report report report",
              "campaign 'My Big Launch 2026' stats yesterday"]:
        parse_command(s)  # must not raise
