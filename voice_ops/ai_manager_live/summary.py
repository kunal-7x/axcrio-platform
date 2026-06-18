"""voice_ops.ai_manager_live.summary — the daily executive summary generator (W14).

Founder pain #4: a DAILY EXECUTIVE WhatsApp SUMMARY to the registered number at
end of day — totals + hot-lead names + short AI summaries + next actions. This
module builds that summary as a structured `DailySummary` AND renders it to a
WhatsApp-friendly plain-text block. It pulls from the LIVE reporting layer so the
numbers match the dashboard exactly.

Pure: (LiveAdapter, tenant, preset) -> DailySummary. No I/O (delivery is a separate
module). `now` injectable for deterministic tests.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from voice_kernel.events.timeutil import render_vendor

from .adapter import LiveAdapter
from .config import AIManagerLiveConfig


@dataclass
class DailySummary:
    tenant_id: str
    preset: str
    range_from: str
    range_to: str
    totals: dict
    hot_leads: list[dict]
    next_actions: list[str]
    headline: str
    text: str  # the rendered WhatsApp-ready block

    def to_dict(self) -> dict:
        return {
            "tenant_id": self.tenant_id,
            "preset": self.preset,
            "range_from": self.range_from,
            "range_to": self.range_to,
            "totals": self.totals,
            "hot_leads": self.hot_leads,
            "next_actions": self.next_actions,
            "headline": self.headline,
            "text": self.text,
        }


def build_daily_summary(adapter: LiveAdapter, tenant_id: str, *, preset: str = "today",
                        frm: str = "", to: str = "", now: Optional[datetime] = None,
                        config: Optional[AIManagerLiveConfig] = None) -> DailySummary:
    """Build the executive summary for a tenant + range from LIVE data."""
    cfg = config or adapter.config
    report = adapter.report(tenant_id, preset, frm=frm, to=to, now=now)
    totals = report["totals"]
    rng = report["range"]
    hot = adapter.hot_leads(tenant_id, preset, frm=frm, to=to, limit=cfg.hot_lead_limit, now=now)

    next_actions = _collect_next_actions(hot, totals)
    headline = _headline(totals, cfg)
    text = _render_text(cfg, rng, totals, hot, next_actions)

    return DailySummary(
        tenant_id=tenant_id,
        preset=rng["preset"],
        range_from=rng["from"],
        range_to=rng["to"],
        totals=totals,
        hot_leads=hot,
        next_actions=next_actions,
        headline=headline,
        text=text,
    )


def _headline(totals: dict, cfg: AIManagerLiveConfig) -> str:
    return (
        f"{totals.get('calls', 0)} calls, {totals.get('connected', 0)} connected, "
        f"{totals.get('hot', 0)} hot, {totals.get('booked', 0)} booked"
    )


def _collect_next_actions(hot: list[dict], totals: dict) -> list[str]:
    """The actionable to-do list: each hot lead's next action, plus a roll-up
    nudge for pending callbacks. De-duplicated, order-preserving."""
    actions: list[str] = []
    seen = set()
    for lead in hot:
        na = (lead.get("next_action") or "").strip()
        name = lead.get("name") or "lead"
        if na:
            line = f"{name}: {na}"
            if line not in seen:
                seen.add(line)
                actions.append(line)
    callbacks = totals.get("callbacks", 0)
    if callbacks:
        line = f"{callbacks} callback(s) scheduled — confirm timing"
        if line not in seen:
            actions.append(line)
    return actions


def _render_text(cfg: AIManagerLiveConfig, rng: dict, totals: dict,
                 hot: list[dict], next_actions: list[str]) -> str:
    """Render the WhatsApp-ready plain-text block. Vendor-tz dates in the header so
    'today' reads as the right local day."""
    day_label = _range_label(rng, cfg.vendor_tz)
    lines = [
        f"*{cfg.business_name} — Daily Report ({day_label})*",
        "",
        f"Calls: {totals.get('calls', 0)}  |  Connected: {totals.get('connected', 0)}"
        f"  ({totals.get('connect_rate', 0)}%)",
        f"Interested: {totals.get('interested', 0)}  |  Booked: {totals.get('booked', 0)}"
        f"  |  Converted: {totals.get('converted', 0)}",
        f"Leads — Hot: {totals.get('hot', 0)}  Warm: {totals.get('warm', 0)}"
        f"  Cold: {totals.get('cold', 0)}  Dead: {totals.get('dead', 0)}",
    ]
    if hot:
        lines.append("")
        lines.append(f"*Hot leads ({len(hot)}):*")
        for lead in hot[:cfg.summary_max_leads_detail]:
            tag = " [BOOKED]" if lead.get("booked") else ""
            summ = (lead.get("summary") or "").strip()
            summ = f" — {summ}" if summ else ""
            lines.append(f"• {lead.get('name', 'lead')}{tag}{summ}")
        extra = len(hot) - cfg.summary_max_leads_detail
        if extra > 0:
            lines.append(f"• +{extra} more")
    if next_actions:
        lines.append("")
        lines.append("*Next actions:*")
        for a in next_actions[:cfg.summary_max_leads_detail + 2]:
            lines.append(f"→ {a}")
    if not hot and not totals.get("calls"):
        lines.append("")
        lines.append("No calls in this period.")
    return "\n".join(lines)


def _range_label(rng: dict, tz: str) -> str:
    """Human label for the range header. For a single-day window show the local
    date; otherwise show 'from → to'."""
    try:
        frm = render_vendor(rng["from"], tz, "%d %b %Y")
        # end is exclusive; subtract a tick conceptually by labeling the inclusive last day
        if rng["preset"] in ("today", "yesterday"):
            return frm
        return f"{frm} → {render_vendor(rng['to'], tz, '%d %b %Y')}"
    except Exception:
        return rng.get("preset", "today")
