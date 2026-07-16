"""grow.metrics — L8 the ROI funnel + the semantic metrics layer (the deck's "100% analytics").

ONE place that defines the KPIs — dashboard, optimizer, and reports all read from here, never
compute ad hoc (GROWTH-OS §8.5). Computes the true funnel from the data the loop produces
(journeys → scored leads → qualified → CAPI signals → bookings → won) plus cost-per-EVERYTHING
the moment spend is connected. The north-star is **CPqL = spend / qualified_leads** — cost per
a *real* outcome, not the vanity "cost per lead".

spend is INJECTED (a query param now; the W5 ad-connector spend feed later) so the funnel +
quality metrics are fully live today and the ₹ metrics light up when spend lands. stdlib only;
never raises (a metrics error must never break a dashboard read)."""
from __future__ import annotations

import logging

from .model import LeadTier

log = logging.getLogger("grow.metrics")


def _pct(n: int, d: int) -> float:
    return round(n / d, 4) if d else 0.0


def _cost(spend_minor: int, n: int) -> int:
    """Cost per outcome in minor units (paise). 0 outcomes -> 0 (UI renders '—')."""
    return int(round(spend_minor / n)) if n else 0


def _percentile(vals: list, p: float) -> int:
    if not vals:
        return 0
    s = sorted(vals)
    k = max(0, min(len(s) - 1, int(round((p / 100.0) * (len(s) - 1)))))
    return int(s[k])


class GrowMetrics:
    """Construct with a GrowLoop; all reads are tenant-scoped + dormant-safe (empty -> zeros)."""

    def __init__(self, loop):
        self.loop = loop

    # ----------------------------------------------------------------- funnel #
    def funnel(self, tenant_id: str) -> dict:
        """Stranger → buyer (ElevateX § analytics): captured → contacted → scored →
        qualified → signal-qualified → booked → won, with the drop-off at each step."""
        try:
            journeys = self.loop.journeys.list(tenant_id)
            scores = self.loop.scores.list(tenant_id)
            orchs = self.loop.orchestrations.list(tenant_id)
            signals = self.loop.signals_store.list(tenant_id)
        except Exception as exc:  # noqa: BLE001
            log.info("grow.metrics.funnel error: %r", exc)
            journeys = scores = orchs = signals = []

        captured = len(journeys)
        contacted = len([o for o in orchs if o.fired])
        scored = len(scores)
        qualified = len([s for s in scores if s.sales_ready])
        signal_qualified = len([e for e in signals if e.event_name == "QualifiedLead"
                                and e.status != "deduped"])
        booked = len([j for j in journeys if j.status in ("booked", "won")])
        won = len([j for j in journeys if j.status == "won"])

        stages = [
            {"key": "captured", "label": "Captured", "count": captured},
            {"key": "contacted", "label": "Contacted (<60s)", "count": contacted},
            {"key": "scored", "label": "Scored", "count": scored},
            {"key": "qualified", "label": "Qualified", "count": qualified},
            {"key": "signal_qualified", "label": "Signal: QualifiedLead", "count": signal_qualified},
            {"key": "booked", "label": "Site visit booked", "count": booked},
            {"key": "won", "label": "Won", "count": won},
        ]
        # conversion from the TOP of the funnel + step-over-step retention
        top = captured or 1
        prev = None
        for st in stages:
            st["of_captured"] = _pct(st["count"], top)
            st["step_rate"] = _pct(st["count"], prev) if prev is not None and prev else None
            prev = st["count"]
        return {"stages": stages, "captured": captured, "qualified": qualified,
                "booked": booked, "won": won}

    # ------------------------------------------------------------ distributions #
    def tier_distribution(self, tenant_id: str) -> dict:
        try:
            scores = self.loop.scores.list(tenant_id)
        except Exception:  # noqa: BLE001
            scores = []
        out = {t: 0 for t in (LeadTier.HOT, LeadTier.WARM, LeadTier.INVESTOR,
                              LeadTier.END_USER, LeadTier.JUNK)}
        for s in scores:
            out[s.tier] = out.get(s.tier, 0) + 1
        return out

    def by_source(self, tenant_id: str) -> dict:
        """Per-platform lead + qualified counts (which channel works best)."""
        try:
            scores = self.loop.scores.list(tenant_id)
        except Exception:  # noqa: BLE001
            scores = []
        out: dict = {}
        for s in scores:
            src = s.source_platform or "unknown"
            row = out.setdefault(src, {"leads": 0, "qualified": 0})
            row["leads"] += 1
            if s.sales_ready:
                row["qualified"] += 1
        return out

    # ----------------------------------------------------------------- sla #
    def sla(self, tenant_id: str) -> dict:
        """Speed-to-lead SLA: how fast capture → first touch, and how often <60s held."""
        try:
            orchs = self.loop.orchestrations.list(tenant_id)
        except Exception:  # noqa: BLE001
            orchs = []
        fired = [o for o in orchs if o.fired]
        lats = [o.latency_ms for o in fired]
        met = len([o for o in fired if o.sla_met])
        return {"runs": len(orchs), "fired": len(fired), "sla_met": met,
                "sla_met_rate": _pct(met, len(fired)),
                "avg_latency_ms": int(round(sum(lats) / len(lats))) if lats else 0,
                "p50_latency_ms": _percentile(lats, 50), "p95_latency_ms": _percentile(lats, 95)}

    # ----------------------------------------------------------------- roi #
    def roi(self, tenant_id: str, *, spend_minor: int = 0, currency: str = "INR") -> dict:
        """Cost per EVERYTHING — the only numbers that tell the truth. Computed the moment
        spend is connected; until then `spend_connected=false` and the funnel still shows
        full volume. north_star = CPqL (cost per qualified lead)."""
        f = self.funnel(tenant_id)
        leads = f["captured"]
        qualified = f["qualified"]
        booked = f["booked"]
        won = f["won"]
        spend_connected = spend_minor > 0
        return {
            "currency": currency, "spend_minor": int(spend_minor),
            "spend_connected": spend_connected,
            "leads": leads, "qualified": qualified, "booked": booked, "won": won,
            "cpl_minor": _cost(spend_minor, leads),
            "cpql_minor": _cost(spend_minor, qualified),          # ★ north star
            "cost_per_booking_minor": _cost(spend_minor, booked),
            "cost_per_won_minor": _cost(spend_minor, won),
            "north_star": "cpql_minor",
        }

    # ----------------------------------------------------------------- summary #
    def summary(self, tenant_id: str, *, spend_minor: int = 0) -> dict:
        """The L8 command-center payload: funnel + tiers + per-source + SLA + ROI +
        signal health, in one read."""
        return {
            "funnel": self.funnel(tenant_id),
            "tier_distribution": self.tier_distribution(tenant_id),
            "by_source": self.by_source(tenant_id),
            "sla": self.sla(tenant_id),
            "roi": self.roi(tenant_id, spend_minor=spend_minor),
            "signal_health": self.loop.signal_health(tenant_id),
        }
