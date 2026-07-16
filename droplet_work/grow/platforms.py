"""grow.platforms — the Realtime All-Ads-Platform layer (Famit Growth).

One normalized view across EVERY ad platform (Google, Facebook, Instagram, YouTube,
LinkedIn, Twitter/X, TikTok). Each platform's metrics are pulled into ONE schema
(spend / impressions / clicks / conversions / CTR / CPC / CPM / CPI + by-location, by-device,
top-ads) so the dashboard, the aggregator, and the advisor all read the same shape.

REAL platform APIs are founder-gated (OAuth per platform). The fetch is a registered seam
(`register_platform_fetcher`) — exactly the adapters pattern — so a provider module / caller
injects the live pull when creds land. Until then:
  * GROW_PLATFORMS_DEMO=1 -> deterministic synthetic metrics (status="demo") so the whole
    dashboard renders immediately for review — clearly labelled, never confused with live;
  * else -> status="no_creds" (the card shows "connect this platform").

stdlib only; never raises (a metrics error must never break the dashboard). Money = INTEGER
minor units (paise). The aggregator computes the cross-platform insights the design asks for
(total platforms, average cost, cheapest/best platform, same-type-ad overlap, ...)."""
from __future__ import annotations

import hashlib
import logging
import os
from dataclasses import dataclass, field, replace
from typing import Callable, Optional

log = logging.getLogger("grow.platforms")

# Ordered to match the Famit Growth design.
PLATFORMS: list = [
    {"key": "google", "label": "Google", "icon": "earth", "kind": "search_display"},
    {"key": "facebook", "label": "Facebook", "icon": "facebook", "kind": "social"},
    {"key": "instagram", "label": "Instagram", "icon": "instagram", "kind": "social"},
    {"key": "youtube", "label": "YouTube", "icon": "video", "kind": "video"},
    {"key": "linkedin", "label": "LinkedIn", "icon": "profile", "kind": "social_b2b"},
    {"key": "twitter", "label": "Twitter / X", "icon": "twitter", "kind": "social"},
    {"key": "tiktok", "label": "TikTok", "icon": "video", "kind": "video"},
]
PLATFORM_KEYS = [p["key"] for p in PLATFORMS]
_PLATFORM_BY_KEY = {p["key"]: p for p in PLATFORMS}


def _flag(name: str, default: str = "0") -> bool:
    return (os.getenv(name, default) or default).strip().lower() in ("1", "true", "yes", "on")


def _ratio(n: int, d: int) -> float:
    return round(n / d, 4) if d else 0.0


def _cost(spend_minor: int, n: int) -> int:
    return int(round(spend_minor / n)) if n else 0


@dataclass
class PlatformMetrics:
    platform: str
    label: str = ""
    status: str = "no_creds"            # live | demo | no_creds | error
    currency: str = "INR"
    period: str = "30d"
    spend_minor: int = 0
    impressions: int = 0
    clicks: int = 0
    conversions: int = 0                # qualified outcomes (leads/installs/sales)
    reach: int = 0
    by_location: list = field(default_factory=list)   # [{name, spend_minor, conversions}]
    by_device: list = field(default_factory=list)     # [{name, share}] mobile/desktop/tablet
    top_ads: list = field(default_factory=list)       # [{name, spend_minor, ctr, conversions}]
    reason: str = ""

    # derived cost metrics (the deck's "CTC, CPI, ... everything")
    @property
    def ctr(self) -> float:
        return _ratio(self.clicks, self.impressions)

    @property
    def cpc_minor(self) -> int:
        return _cost(self.spend_minor, self.clicks)

    @property
    def cpm_minor(self) -> int:
        return int(round(self.spend_minor / self.impressions * 1000)) if self.impressions else 0

    @property
    def cpi_minor(self) -> int:                # cost per conversion/install
        return _cost(self.spend_minor, self.conversions)

    @property
    def cvr(self) -> float:
        return _ratio(self.conversions, self.clicks)

    def copy(self) -> "PlatformMetrics":
        return replace(self, by_location=list(self.by_location), by_device=list(self.by_device),
                       top_ads=list(self.top_ads))

    def public(self) -> dict:
        meta = _PLATFORM_BY_KEY.get(self.platform, {})
        return {
            "platform": self.platform, "label": self.label or meta.get("label", self.platform),
            "icon": meta.get("icon", "promote"), "kind": meta.get("kind", ""),
            "status": self.status, "currency": self.currency, "period": self.period,
            "spend_minor": self.spend_minor, "impressions": self.impressions,
            "clicks": self.clicks, "conversions": self.conversions, "reach": self.reach,
            "ctr": self.ctr, "cpc_minor": self.cpc_minor, "cpm_minor": self.cpm_minor,
            "cpi_minor": self.cpi_minor, "cvr": self.cvr,
            "by_location": list(self.by_location), "by_device": list(self.by_device),
            "top_ads": list(self.top_ads), "reason": self.reason,
        }


# =========================================================================== #
# Live-fetch registry (founder-gated real APIs inject here, like grow.adapters).
# =========================================================================== #
_FETCHERS: dict = {}


def register_platform_fetcher(platform: str, fn: Callable) -> None:
    """fn(tenant_id, platform, period) -> PlatformMetrics (status='live'). Injected by the
    provider/connector module when that platform's OAuth + API are wired."""
    _FETCHERS[platform] = fn
    log.info("grow: live fetcher registered for %s", platform)


def clear_fetchers() -> None:
    _FETCHERS.clear()


def configured_platforms() -> list:
    """Which platforms have a live fetcher registered (+ whether demo is on)."""
    demo = _flag("GROW_PLATFORMS_DEMO", "0")
    return [{"key": p["key"], "label": p["label"], "icon": p["icon"],
             "live": p["key"] in _FETCHERS, "demo": demo} for p in PLATFORMS]


# =========================================================================== #
# Deterministic DEMO metrics (no RNG) — seeded by (platform, period) so the
# dashboard renders realistic, stable numbers labelled status="demo".
# =========================================================================== #
def _seed(platform: str, period: str, salt: str = "") -> int:
    h = hashlib.sha256(f"{platform}|{period}|{salt}".encode()).hexdigest()
    return int(h[:8], 16)


def _demo_metrics(platform: str, period: str) -> PlatformMetrics:
    meta = _PLATFORM_BY_KEY.get(platform, {"label": platform})
    s = _seed(platform, period)
    spend = 50_00_000 + (s % 40) * 5_00_000          # ₹5L–₹25L (paise)
    impressions = 200_000 + (s % 50) * 30_000
    clicks = max(100, int(impressions * (0.008 + (s % 25) / 1000.0)))   # ctr 0.8%-3.3%
    conversions = max(1, int(clicks * (0.03 + (s % 18) / 200.0)))       # cvr 3%-12%
    reach = int(impressions * (0.55 + (s % 30) / 100.0))
    locs = ["Mumbai", "Delhi NCR", "Bengaluru", "Pune", "Hyderabad"]
    by_location = [{"name": locs[i], "spend_minor": int(spend * w), "conversions": int(conversions * w)}
                   for i, w in enumerate([0.34, 0.26, 0.18, 0.13, 0.09])]
    dshare = [0.62, 0.30, 0.08] if (s % 2 == 0) else [0.71, 0.22, 0.07]
    by_device = [{"name": n, "share": w} for n, w in zip(("mobile", "desktop", "tablet"), dshare)]
    top_ads = [
        {"name": f"{meta['label']}-Question-Hook-{(s % 3) + 1}", "spend_minor": int(spend * 0.42),
         "ctr": round(0.012 + (s % 20) / 1000.0, 4), "conversions": int(conversions * 0.46)},
        {"name": f"{meta['label']}-Price-Anchor-{(s % 4) + 1}", "spend_minor": int(spend * 0.33),
         "ctr": round(0.009 + (s % 15) / 1000.0, 4), "conversions": int(conversions * 0.31)},
    ]
    return PlatformMetrics(
        platform=platform, label=meta.get("label", platform), status="demo", period=period,
        spend_minor=spend, impressions=impressions, clicks=clicks, conversions=conversions,
        reach=reach, by_location=by_location, by_device=by_device, top_ads=top_ads,
        reason="demo data (connect this platform for live metrics)")


# =========================================================================== #
# Connector — registered live fetcher, else demo (if on), else no_creds.
# =========================================================================== #
def fetch_platform(tenant_id: str, platform: str, *, period: str = "30d",
                   demo: Optional[bool] = None) -> PlatformMetrics:
    meta = _PLATFORM_BY_KEY.get(platform)
    if meta is None:
        return PlatformMetrics(platform=platform, status="error", reason="unknown_platform")
    fn = _FETCHERS.get(platform)
    if fn is not None:
        try:
            m = fn(tenant_id, platform, period)
            if isinstance(m, PlatformMetrics):
                # a live fetcher that returned data is "live" unless it explicitly set
                # a different status (error/demo) — the default no_creds means "didn't say".
                if m.status in ("", "no_creds"):
                    m.status = "live"
                return m
            log.info("grow platform fetcher for %s returned non-PlatformMetrics", platform)
        except Exception as exc:  # noqa: BLE001
            log.info("grow platform fetch %s failed: %r", platform, exc)
            return PlatformMetrics(platform=platform, label=meta["label"], status="error",
                                   reason=f"fetch_error:{exc!r}"[:120])
    use_demo = _flag("GROW_PLATFORMS_DEMO", "0") if demo is None else demo
    if use_demo:
        return _demo_metrics(platform, period)
    return PlatformMetrics(platform=platform, label=meta["label"], status="no_creds",
                           reason="connect this platform")


# =========================================================================== #
# Aggregator — the cross-platform insights the design asks for.
# =========================================================================== #
class AdsAggregator:
    def snapshot(self, tenant_id: str, *, period: str = "30d",
                 demo: Optional[bool] = None) -> dict:
        rows = [fetch_platform(tenant_id, p["key"], period=period, demo=demo) for p in PLATFORMS]
        return {"period": period, "platforms": [r.public() for r in rows],
                "summary": self._summary(rows, period)}

    def _summary(self, rows: list, period: str) -> dict:
        active = [r for r in rows if r.status in ("live", "demo") and r.spend_minor > 0]
        total_spend = sum(r.spend_minor for r in active)
        total_impr = sum(r.impressions for r in active)
        total_clicks = sum(r.clicks for r in active)
        total_conv = sum(r.conversions for r in active)

        def _min_by(metric) -> Optional[dict]:
            cand = [r for r in active if metric(r) > 0]
            if not cand:
                return None
            best = min(cand, key=metric)
            return {"platform": best.platform, "label": best.label, "value": metric(best)}

        def _max_by(metric) -> Optional[dict]:
            cand = [r for r in active if metric(r) > 0]
            if not cand:
                return None
            best = max(cand, key=metric)
            return {"platform": best.platform, "label": best.label, "value": metric(best)}

        # same-type-ad overlap: distinct ad "concepts" (hook family) run on 2+ platforms
        concept_platforms: dict = {}
        for r in active:
            for ad in r.top_ads:
                # concept = the hook family, e.g. "Question-Hook" from "Google-Question-Hook-2"
                parts = str(ad.get("name", "")).split("-")
                concept = "-".join(parts[1:3]) if len(parts) >= 3 else (parts[-1] if parts else "")
                if concept:
                    concept_platforms.setdefault(concept, set()).add(r.platform)
        same_type = [{"concept": c, "platforms": sorted(ps)}
                     for c, ps in concept_platforms.items() if len(ps) >= 2]

        return {
            "total_platforms": len(PLATFORMS),
            "active_platforms": len(active),
            "active_platform_keys": [r.platform for r in active],
            "currency": (active[0].currency if active else "INR"),
            "total_spend_minor": total_spend,
            "total_impressions": total_impr,
            "total_clicks": total_clicks,
            "total_conversions": total_conv,
            "avg_ctr": _ratio(total_clicks, total_impr),
            "avg_cpc_minor": _cost(total_spend, total_clicks),
            "avg_cpm_minor": int(round(total_spend / total_impr * 1000)) if total_impr else 0,
            "avg_cpi_minor": _cost(total_spend, total_conv),     # avg cost per conversion
            "cheapest_cpc": _min_by(lambda r: r.cpc_minor),
            "cheapest_cpi": _min_by(lambda r: r.cpi_minor),       # cheapest cost/outcome
            "best_ctr": _max_by(lambda r: r.ctr),
            "best_cvr": _max_by(lambda r: r.cvr),
            "top_spender": _max_by(lambda r: r.spend_minor),
            "same_type_ads": same_type,
            "period": period,
        }


_AGG = AdsAggregator()


def snapshot(tenant_id: str, *, period: str = "30d", demo: Optional[bool] = None) -> dict:
    """Module-level convenience used by the advisor + endpoints."""
    return _AGG.snapshot(tenant_id, period=period, demo=demo)
