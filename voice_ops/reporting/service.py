"""voice_ops.reporting.service — the query API surface (W14).

The single object the panel API + the AI-Manager call. It ties the store
(read-model) to the date-range engine + the aggregation engine, tenant-scoped:

    report(tenant, preset|custom, filters)        -> the full universal report
    metric(tenant, key, ...)                      -> one top-line number (AIM live read)
    hot_leads(tenant, range)                      -> hot-lead rows (names + next action)
    funnel / timeline / agents / sources ...      -> individual sections

Every query RE-SCANS the store + RE-AGGREGATES for the requested range, so the AI
Manager and the dashboard read the SAME live numbers — there is no separate stale
cache (founder pain #2). `now` is injectable so tests pin the clock.

Pure orchestration over sibling modules + the injected store. No droplet import.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from .aggregate import (
    aggregate as _aggregate,
    agent_performance as _agent_performance,
    build_funnel as _build_funnel,
    campaign_analytics as _campaign_analytics,
    daily_timeline as _daily_timeline,
    drill as _drill,
    followup_analytics as _followup_analytics,
    in_range as _in_range,
    source_analytics as _source_analytics,
    totals as _totals,
)
from .config import ReportingConfig
from .daterange import DateRange, resolve_range
from .model import FactCall, LeadStatus
from .store import ReportingStore


class ReportingService:
    """Tenant-scoped query API over the read-model store."""

    def __init__(self, store: Optional[ReportingStore] = None, config: Optional[ReportingConfig] = None):
        self.store = store or ReportingStore()
        self.config = config or ReportingConfig()

    # ------------------------------------------------------------- ranges #
    def resolve(self, preset: str, *, frm: str = "", to: str = "",
                now: Optional[datetime] = None) -> DateRange:
        return resolve_range(preset, now=now, frm=frm, to=to, tz_name=self.config.vendor_tz)

    def _rows(self, tenant_id: str) -> list[FactCall]:
        return self.store.scan(tenant_id)

    # ------------------------------------------------------------- report #
    def report(self, tenant_id: str, preset: str = "", *, frm: str = "", to: str = "",
               filters: Optional[dict] = None, now: Optional[datetime] = None) -> dict:
        """The full universal report for a range + optional drill-down filters.
        Empty preset -> the configured default ('today'). Tenant-isolated."""
        rng = self.resolve(preset or self.config.default_preset, frm=frm, to=to, now=now)
        return _aggregate(self._rows(tenant_id), rng, filters)

    # ------------------------------------------------ single-value reads #
    def totals(self, tenant_id: str, preset: str = "", *, frm: str = "", to: str = "",
               filters: Optional[dict] = None, now: Optional[datetime] = None) -> dict:
        rng = self.resolve(preset or self.config.default_preset, frm=frm, to=to, now=now)
        scoped = _drill(_in_range(self._rows(tenant_id), rng), filters)
        return _totals(scoped)

    def metric(self, tenant_id: str, key: str, preset: str = "", *, frm: str = "", to: str = "",
               filters: Optional[dict] = None, now: Optional[datetime] = None):
        """One top-line metric (e.g. 'connected', 'booked', 'hot') for a range.
        This is the AI-Manager's LIVE number — identical to what `totals` returns,
        so the manager can never diverge from the dashboard. Unknown key -> 0."""
        return self.totals(tenant_id, preset, frm=frm, to=to, filters=filters, now=now).get(key, 0)

    def funnel(self, tenant_id: str, preset: str = "", *, frm: str = "", to: str = "",
               filters: Optional[dict] = None, now: Optional[datetime] = None) -> list[dict]:
        rng = self.resolve(preset or self.config.default_preset, frm=frm, to=to, now=now)
        scoped = _drill(_in_range(self._rows(tenant_id), rng), filters)
        return _build_funnel(scoped)

    def timeline(self, tenant_id: str, preset: str = "", *, frm: str = "", to: str = "",
                 filters: Optional[dict] = None, now: Optional[datetime] = None) -> list[dict]:
        rng = self.resolve(preset or self.config.default_preset, frm=frm, to=to, now=now)
        scoped = _drill(_in_range(self._rows(tenant_id), rng), filters)
        return _daily_timeline(scoped, rng)

    def agents(self, tenant_id: str, preset: str = "", *, frm: str = "", to: str = "",
               now: Optional[datetime] = None) -> list[dict]:
        rng = self.resolve(preset or self.config.default_preset, frm=frm, to=to, now=now)
        return _agent_performance(_in_range(self._rows(tenant_id), rng))

    def sources(self, tenant_id: str, preset: str = "", *, frm: str = "", to: str = "",
                now: Optional[datetime] = None) -> list[dict]:
        rng = self.resolve(preset or self.config.default_preset, frm=frm, to=to, now=now)
        return _source_analytics(_in_range(self._rows(tenant_id), rng))

    def campaigns(self, tenant_id: str, preset: str = "", *, frm: str = "", to: str = "",
                  now: Optional[datetime] = None) -> list[dict]:
        rng = self.resolve(preset or self.config.default_preset, frm=frm, to=to, now=now)
        return _campaign_analytics(_in_range(self._rows(tenant_id), rng))

    def followups(self, tenant_id: str, preset: str = "", *, frm: str = "", to: str = "",
                  now: Optional[datetime] = None) -> dict:
        rng = self.resolve(preset or self.config.default_preset, frm=frm, to=to, now=now)
        return _followup_analytics(_in_range(self._rows(tenant_id), rng))

    # ----------------------------------------------------------- hot leads #
    def hot_leads(self, tenant_id: str, preset: str = "", *, frm: str = "", to: str = "",
                  limit: int = 0, now: Optional[datetime] = None) -> list[dict]:
        """Hot leads in range, richest first (booked > conversion_prob). Each row
        carries the name + masked phone + short AI summary + next action — exactly
        what the daily executive WhatsApp summary lists (founder pain #4)."""
        rng = self.resolve(preset or self.config.default_preset, frm=frm, to=to, now=now)
        rows = [f for f in _in_range(self._rows(tenant_id), rng)
                if getattr(f.lead_status, "value", f.lead_status) == LeadStatus.HOT.value]
        rows.sort(key=lambda f: (f.booked, f.conversion_prob, f.ts_iso), reverse=True)
        lim = limit or self.config.hot_lead_limit
        out = []
        for f in rows[:lim]:
            out.append({
                "call_id": f.call_id,
                "name": f.lead_name or "(unknown)",
                "phone_masked": f.lead_phone_masked,
                "campaign_id": f.campaign_id,
                "source": f.source,
                "booked": f.booked,
                "conversion_prob": f.conversion_prob,
                "summary": f.ai_summary,
                "next_action": f.next_action or ("Confirm booking" if f.booked else "Call back / send proposal"),
                "ts_iso": f.ts_iso,
            })
        return out
