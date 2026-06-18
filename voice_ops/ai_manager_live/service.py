"""voice_ops.ai_manager_live.service — the AI-Manager live command center (W14).

The single façade the inbound AI-Manager calls with a free-text command. It:
  1. parses the command (commands.parse_command),
  2. answers it from the LIVE reporting layer (adapter),
  3. renders a human-friendly reply (WhatsApp-ready text),
  4. optionally DELIVERS it to the tenant's registered number (if the user said
     "send/share/whatsapp ..." and creds are wired).

`handle(tenant_id, message)` returns a structured envelope: the parsed command, the
LIVE data, the rendered reply text, and (if delivery was requested) the delivery
result. The manager can speak the `reply` aloud (inbound voice) or the delivery
sends it on WhatsApp — same numbers either way (founder pain #2/#5).

Pure orchestration. ZERO droplet import; sender/number-resolver injected.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from voice_ops.reporting.service import ReportingService

from .adapter import LiveAdapter
from .commands import Command, CommandKind, parse_command
from .config import AIManagerLiveConfig
from .delivery import ReportDelivery
from .summary import build_daily_summary


class AIManagerLiveService:
    def __init__(self, reporting: ReportingService, *,
                 config: Optional[AIManagerLiveConfig] = None,
                 delivery: Optional[ReportDelivery] = None):
        self.config = config or AIManagerLiveConfig()
        self.adapter = LiveAdapter(reporting, self.config)
        self.delivery = delivery or ReportDelivery()

    # ----------------------------------------------------- command entry #
    def handle(self, tenant_id: str, message: str, *, now: Optional[datetime] = None,
               to: str = "") -> dict:
        """Parse + answer + (optionally) deliver one manager command. Tenant-scoped.
        Never raises — an unparseable command returns a friendly fallback."""
        cmd = parse_command(message, default_preset=self.config.default_preset)
        data, reply = self._answer(tenant_id, cmd, now=now)
        envelope = {
            "command": {
                "kind": cmd.kind.value,
                "preset": cmd.preset,
                "target": cmd.target,
                "metric": cmd.metric,
                "filters": cmd.filters,
                "deliver": cmd.deliver,
            },
            "tenant_id": tenant_id,
            "reply": reply,
            "data": data,
        }
        if cmd.deliver:
            envelope["delivery"] = self.delivery.deliver(tenant_id, reply, to=to)
        return envelope

    # ----------------------------------------------------- daily summary #
    def daily_summary(self, tenant_id: str, *, preset: str = "today", frm: str = "", to: str = "",
                      now: Optional[datetime] = None, deliver: bool = False,
                      to_number: str = "") -> dict:
        """Build the end-of-day executive summary (totals + hot-lead names + AI
        summaries + next actions). When `deliver=True`, also send it to the
        tenant's registered WhatsApp number (dormant until creds wired)."""
        summary = build_daily_summary(self.adapter, tenant_id, preset=preset, frm=frm, to=to,
                                      now=now, config=self.config)
        out = {"summary": summary.to_dict()}
        if deliver:
            out["delivery"] = self.delivery.deliver(tenant_id, summary.text, to=to_number)
        return out

    # --------------------------------------------------------- answering #
    def _answer(self, tenant_id: str, cmd: Command, *, now: Optional[datetime] = None) -> tuple[dict, str]:
        """Resolve a parsed command to (live data, rendered reply text)."""
        a = self.adapter
        if cmd.kind == CommandKind.SEND_REPORT:
            s = build_daily_summary(a, tenant_id, preset=cmd.preset, now=now, config=self.config)
            return ({"totals": s.totals, "hot_leads": s.hot_leads, "next_actions": s.next_actions,
                     "range": {"from": s.range_from, "to": s.range_to, "preset": s.preset}}, s.text)

        if cmd.kind == CommandKind.HOT_LEADS:
            status = cmd.filters.get("lead_status", "hot")
            leads = a.hot_leads(tenant_id, cmd.preset, status=status, now=now)
            return ({"hot_leads": leads, "status": status}, _render_leads(status, leads))

        if cmd.kind == CommandKind.CAMPAIGN_PERF:
            perf = a.campaign_performance(tenant_id, cmd.target, cmd.preset, now=now)
            return (perf, _render_campaign(cmd.target, perf))

        if cmd.kind == CommandKind.FUNNEL:
            funnel = a.funnel(tenant_id, cmd.preset, filters=cmd.filters or None, now=now)
            return ({"funnel": funnel}, _render_funnel(cmd.preset, funnel))

        if cmd.kind == CommandKind.METRIC:
            totals = a.totals(tenant_id, cmd.preset, filters=cmd.filters or None, now=now)
            val = totals.get(cmd.metric, 0)
            return ({"metric": cmd.metric, "value": val, "totals": totals},
                    _render_metric(cmd.metric, val, cmd.preset))

        # UNKNOWN -> a helpful fallback listing what it CAN answer (no raise).
        return ({"recognized": False},
                "I can send today's report, show hot leads, give a campaign's "
                "performance, or a specific number (calls/connected/booked) for "
                "today, yesterday, this week or this month. Try: \"send today's report\".")


# --------------------------------------------------------------------------- #
# Tiny renderers (WhatsApp-ready plain text). Kept here so the service owns the
# voice/WA reply shape; the dashboard uses the structured `data` instead.
# --------------------------------------------------------------------------- #
def _render_metric(metric: str, value, preset: str) -> str:
    label = {
        "calls": "calls", "connected": "connected calls", "booked": "bookings",
        "converted": "conversions", "hot": "hot leads", "warm": "warm leads",
        "connect_rate": "connect rate", "conversion_rate": "conversion rate",
        "book_rate": "booking rate", "callbacks": "callbacks scheduled",
        "whatsapp_sent": "WhatsApp follow-ups", "handoff": "handoffs",
        "no_answer": "no-answers",
    }.get(metric, metric)
    suffix = "%" if metric.endswith("_rate") else ""
    return f"{label.capitalize()} {_range_phrase(preset)}: {value}{suffix}."


def _render_leads(status: str, leads: list[dict]) -> str:
    if not leads:
        return f"No {status} leads in this period."
    lines = [f"*{status.capitalize()} leads ({len(leads)}):*"]
    for lead in leads[:10]:
        tag = " [BOOKED]" if lead.get("booked") else ""
        na = (lead.get("next_action") or "").strip()
        na = f" — next: {na}" if na else ""
        lines.append(f"• {lead.get('name', 'lead')}{tag}{na}")
    if len(leads) > 10:
        lines.append(f"• +{len(leads) - 10} more")
    return "\n".join(lines)


def _render_campaign(name: str, perf: dict) -> str:
    t = perf.get("totals", {})
    cid = perf.get("campaign_id", name)
    if not perf.get("matched") and not t.get("calls"):
        return f"No data for campaign \"{name}\" in this period."
    return (
        f"*Campaign {cid}:*\n"
        f"Calls: {t.get('calls', 0)}  |  Connected: {t.get('connected', 0)} "
        f"({t.get('connect_rate', 0)}%)\n"
        f"Interested: {t.get('interested', 0)}  |  Booked: {t.get('booked', 0)} "
        f"|  Hot: {t.get('hot', 0)}"
    )


def _render_funnel(preset: str, funnel: list[dict]) -> str:
    lines = [f"*Funnel {_range_phrase(preset)}:*"]
    for s in funnel:
        lines.append(f"• {s['stage']}: {s['count']} ({s['pct_of_top']}%)")
    return "\n".join(lines)


def _range_phrase(preset: str) -> str:
    return {
        "today": "today", "yesterday": "yesterday", "7d": "this week",
        "30d": "last 30 days", "this-month": "this month", "prev-month": "last month",
    }.get(preset, preset)
