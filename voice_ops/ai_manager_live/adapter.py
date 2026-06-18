"""voice_ops.ai_manager_live.adapter — answer operational questions from the LIVE
reporting layer (W14).

This is the heart of founder pain #2. The adapter wraps a `ReportingService` and
exposes question-shaped methods that return LIVE numbers — the SAME aggregates the
dashboard renders, because they come from the same service + the same read-model.
There is NO second cache to drift from.

Each method takes a tenant + a range preset (or custom from/to) and returns a
plain dict the manager can read out (voice) or format (WhatsApp). `now` is
injectable so tests pin the clock; in prod it is None -> live now.

Pure orchestration over ReportingService. No droplet import.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from voice_ops.reporting.service import ReportingService

from .config import AIManagerLiveConfig


class LiveAdapter:
    def __init__(self, reporting: ReportingService, config: Optional[AIManagerLiveConfig] = None):
        self.reporting = reporting
        self.config = config or AIManagerLiveConfig()

    def _preset(self, preset: str) -> str:
        return preset or self.config.default_preset

    # ----------------------------------------------------- single metric #
    def metric(self, tenant_id: str, key: str, preset: str = "", *, frm: str = "", to: str = "",
               filters: Optional[dict] = None, now: Optional[datetime] = None):
        """One LIVE number (calls/connected/booked/hot/connect_rate/...). Identical
        to the dashboard's `totals[key]` for the same range — by construction."""
        return self.reporting.metric(tenant_id, key, self._preset(preset),
                                     frm=frm, to=to, filters=filters, now=now)

    # ----------------------------------------------------------- totals #
    def totals(self, tenant_id: str, preset: str = "", *, frm: str = "", to: str = "",
               filters: Optional[dict] = None, now: Optional[datetime] = None) -> dict:
        return self.reporting.totals(tenant_id, self._preset(preset),
                                    frm=frm, to=to, filters=filters, now=now)

    # ------------------------------------------------- full live report #
    def report(self, tenant_id: str, preset: str = "", *, frm: str = "", to: str = "",
               filters: Optional[dict] = None, now: Optional[datetime] = None) -> dict:
        return self.reporting.report(tenant_id, self._preset(preset),
                                    frm=frm, to=to, filters=filters, now=now)

    # ------------------------------------------------------- hot leads #
    def hot_leads(self, tenant_id: str, preset: str = "", *, frm: str = "", to: str = "",
                  status: str = "hot", limit: int = 0, now: Optional[datetime] = None) -> list[dict]:
        """Live hot (or warm/cold/dead) leads with names + summaries + next actions.
        For non-hot statuses we report from the full report's status counts is not
        enough (we need names), so we route through the service's range scan +
        filter by status here for parity with the dashboard CRM list."""
        if status == "hot":
            return self.reporting.hot_leads(tenant_id, self._preset(preset),
                                           frm=frm, to=to, limit=limit, now=now)
        # generic status: reuse the report scan via a drilled report (counts) +
        # fall back to hot_leads' richer payload shape only for hot.
        rng = self.reporting.resolve(self._preset(preset), frm=frm, to=to, now=now)
        rows = [f for f in self.reporting.store.scan(tenant_id)
                if rng.contains(f.ts_iso)
                and getattr(f.lead_status, "value", f.lead_status) == status]
        rows.sort(key=lambda f: (f.conversion_prob, f.ts_iso), reverse=True)
        lim = limit or self.config.hot_lead_limit
        return [{
            "call_id": f.call_id,
            "name": f.lead_name or "(unknown)",
            "phone_masked": f.lead_phone_masked,
            "campaign_id": f.campaign_id,
            "source": f.source,
            "booked": f.booked,
            "conversion_prob": f.conversion_prob,
            "summary": f.ai_summary,
            "next_action": f.next_action,
            "ts_iso": f.ts_iso,
        } for f in rows[:lim]]

    # ------------------------------------------------ campaign analytics #
    def campaign_performance(self, tenant_id: str, campaign: str, preset: str = "", *,
                             frm: str = "", to: str = "", now: Optional[datetime] = None) -> dict:
        """Performance for ONE campaign. `campaign` may be the id OR a fuzzy name —
        we match against the campaign_id breakdown the reporting layer produces and
        also return the drilled totals/funnel for that campaign."""
        camps = self.reporting.campaigns(tenant_id, self._preset(preset), frm=frm, to=to, now=now)
        match = self._match_campaign(camps, campaign)
        cid = match["key"] if match else campaign
        totals = self.reporting.totals(tenant_id, self._preset(preset), frm=frm, to=to,
                                       filters={"campaign": cid}, now=now)
        funnel = self.reporting.funnel(tenant_id, self._preset(preset), frm=frm, to=to,
                                       filters={"campaign": cid}, now=now)
        return {
            "campaign_id": cid,
            "matched": match is not None,
            "totals": totals,
            "funnel": funnel,
            "rollup": match or {},
        }

    @staticmethod
    def _match_campaign(camps: list[dict], query: str) -> Optional[dict]:
        q = (query or "").strip().lower()
        if not q:
            return None
        # exact id match first, then substring (fuzzy name).
        for c in camps:
            if str(c["key"]).lower() == q:
                return c
        for c in camps:
            if q in str(c["key"]).lower() or str(c["key"]).lower() in q:
                return c
        return None

    def funnel(self, tenant_id: str, preset: str = "", *, frm: str = "", to: str = "",
               filters: Optional[dict] = None, now: Optional[datetime] = None) -> list[dict]:
        return self.reporting.funnel(tenant_id, self._preset(preset),
                                    frm=frm, to=to, filters=filters, now=now)
