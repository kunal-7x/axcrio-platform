"""ads_engine.analytics — READ-SIDE: shapes the /ads/health and /ads/campaigns payloads.

Pure read + aggregation. Reads `store` rows ONLY (always tenant-scoped via store.py's enforced
accessors — REDTEAM C1), touches no platform API, writes no row, reads no credential. Empty-but-
valid when a tenant has no data: the panel renders the dormant/empty state cleanly, never an error.

Money is minor units (paise), matching `_lib.ts`.
"""

from __future__ import annotations

from typing import Any

from . import budget as _budget
from . import config, store, vault_adapter


def health(tenant_id: str) -> dict:
    """GET /ads/health -> AdsHealth (`_lib.ts:60`). Caps from config + provider 'row exists?' status.
    Default-safe: provider status degrades to not_configured if the vault is unreachable.

    BLINDSPOTS B13/B15: also carries the non-secret ad-budget block (funded balance + gateway
    configured?) so Connections / the Budget surface can show 'Funded ✓ / gateway not connected'
    without a second round-trip. Secret/id-free; default-safe (zero balance when unreadable)."""
    try:
        provider_status = vault_adapter.provider_status_for_health(tenant_id)
    except Exception:  # noqa: BLE001
        provider_status = {"meta": "not_configured", "google": "not_configured"}
    block = config.health_block(provider_status)
    try:
        bal = _budget.get_balance(tenant_id)
        block["budget"] = {
            "balance_minor": bal.get("balance_minor", 0),
            "currency": bal.get("currency", "INR"),
            "gateway": bal.get("gateway", {}),
            "funded": bool(int(bal.get("balance_minor", 0) or 0) > 0),
        }
    except Exception:  # noqa: BLE001
        block["budget"] = {"balance_minor": 0, "currency": "INR",
                           "gateway": {"configured": False}, "funded": False}
    return block


def _campaign_view(rec: dict) -> dict:
    """Project a stored campaign into the AdsCampaign shape (`_lib.ts:108`), default-safe."""
    rec = rec or {}
    return {
        "plan_id": rec.get("plan_id", ""),
        "org_id": rec.get("org_id", rec.get("tenant_id", "")),
        "provider": rec.get("provider", "noop"),
        "name": rec.get("name", ""),
        "objective": rec.get("objective", ""),
        "plan": rec.get("plan", {}) or {},
        "status": rec.get("status", "draft"),
        "campaign_ref": rec.get("campaign_ref", ""),
        "daily_cap_minor": int(rec.get("daily_cap_minor", 0) or 0),
        "lifetime_cap_minor": int(rec.get("lifetime_cap_minor", 0) or 0),
        "cpl_max_minor": int(rec.get("cpl_max_minor", 0) or 0),
        "approved_by": rec.get("approved_by"),
        "approved_ts": rec.get("approved_ts"),
        "spend_today_minor": int(rec.get("spend_today_minor", 0) or 0),
        "spend_life_minor": int(rec.get("spend_life_minor", 0) or 0),
        "last_cpl_minor": rec.get("last_cpl_minor"),
        "last_polled_ts": rec.get("last_polled_ts"),
        "pause_reason": rec.get("pause_reason", ""),
    }


def status(tenant_id: str) -> dict:
    """GET /ads/campaigns -> AdsStatusResponse (`_lib.ts:130`). Empty-but-valid when no data."""
    try:
        recs = store.list_campaigns(tenant_id)
    except Exception:  # noqa: BLE001
        recs = []
    campaigns = [_campaign_view(r) for r in recs]
    spend_today = sum(c["spend_today_minor"] for c in campaigns)
    try:
        caps = store.get_spend_caps(tenant_id) or {}
    except Exception:  # noqa: BLE001
        caps = {}
    org_daily_cap = int(caps.get("org_daily_cap_minor", config.caps().get("org_daily_cap_minor", 0)) or 0)
    return {
        "ok": True,
        "config": health(tenant_id),
        "campaigns": campaigns,
        "count": len(campaigns),
        "spend_today_minor": spend_today,
        "org_daily_cap_minor": org_daily_cap,
    }


# ===========================================================================
# ANALYTICS ROLLUPS (BLINDSPOTS B6) — the 4 read-only rollups behind
# GET /ads/analytics/{funnel|per-ad|per-platform|real-vs-reported}. Each is a pure,
# tenant-scoped store aggregation: it reads the tenant's own rows ONLY, touches no
# platform API, writes nothing, and is empty-but-valid (never raises) for a tenant
# with no data. Shapes match `_lib.ts:AdsAnalyticsResponse` ({kind, rows?, funnel?,
# totals?}). Money is minor units (paise).
# ===========================================================================
def _safe_int(v: Any, default: int = 0) -> int:  # noqa: ANN401
    try:
        return int(v or 0)
    except Exception:  # noqa: BLE001
        return default


def _leads(tenant_id: str) -> list:
    try:
        rows = store.get_tenant_file(tenant_id, "leads_ads")
        return rows if isinstance(rows, list) else []
    except Exception:  # noqa: BLE001
        return []


def _conversions(tenant_id: str) -> list:
    try:
        rows = store.get_tenant_file(tenant_id, "conversions")
        return rows if isinstance(rows, list) else []
    except Exception:  # noqa: BLE001
        return []


def _campaign_match(rec: dict, campaign_id: str) -> bool:
    if not campaign_id:
        return True
    return str(rec.get("campaign_id") or rec.get("plan_id") or "") == str(campaign_id)


# Lead lifecycle buckets used by the funnel (derived from a stored lead row's status/gate).
def _is_dialed(lead: dict) -> bool:
    return str(lead.get("status", "")) in ("dry_run", "enqueued")


def _is_gate_allowed(lead: dict) -> bool:
    g = lead.get("gate") if isinstance(lead.get("gate"), dict) else {}
    return bool(g.get("allow")) or _is_dialed(lead)


def _is_consented(lead: dict) -> bool:
    # consented = a phone we did NOT block for missing consent (the gate ran past the consent check).
    if _is_gate_allowed(lead):
        return True
    return str(lead.get("status", "")) not in ("error", "blocked_no_consent")


def funnel(tenant_id: str, *, campaign_id: str = "") -> dict:
    """Lead funnel from leads_ads: captured -> valid_phone -> consented -> gate_passed -> dialed.

    Each stage carries count + pct_of_top (share of captured) + step_conv (share of the prior
    stage). Empty-but-valid (all zeros) when the tenant has no leads."""
    rows = [r for r in _leads(tenant_id) if isinstance(r, dict) and _campaign_match(r, campaign_id)]
    captured = len(rows)
    valid = sum(1 for r in rows if str(r.get("status", "")) != "error" and r.get("phone"))
    consented = sum(1 for r in rows if _is_consented(r))
    gate_passed = sum(1 for r in rows if _is_gate_allowed(r))
    dialed = sum(1 for r in rows if _is_dialed(r))
    ordered = [
        ("captured", captured),
        ("valid_phone", valid),
        ("consented", consented),
        ("gate_passed", gate_passed),
        ("dialed", dialed),
    ]
    out = []
    prev = None
    for stage, count in ordered:
        pct_top = (count / captured) if captured else 0.0
        step = (count / prev) if (prev not in (None, 0)) else (1.0 if count else 0.0)
        out.append({"stage": stage, "count": count,
                    "pct_of_top": round(pct_top, 4), "step_conv": round(step, 4)})
        prev = count
    return {"ok": True, "kind": "funnel", "funnel": out,
            "totals": {"captured": captured, "dialed": dialed}}


def per_ad(tenant_id: str, *, campaign_id: str = "") -> dict:
    """Per-ad rollup from ad_variants: one row per creative variant with its moderation verdict +
    a lead count joined from leads_ads by campaign/plan. Store-only; empty-but-valid."""
    try:
        variants = list(store.get_collection(tenant_id, "ad_variants").values())
    except Exception:  # noqa: BLE001
        variants = []
    leads = _leads(tenant_id)
    leads_by_campaign: dict = {}
    for lr in leads:
        cid = str(lr.get("campaign_id") or "")
        if not cid:
            continue
        leads_by_campaign[cid] = leads_by_campaign.get(cid, 0) + 1
    rows = []
    for v in variants:
        if not isinstance(v, dict):
            continue
        plan_id = str(v.get("plan_id") or "")
        if campaign_id and plan_id != str(campaign_id):
            continue
        rows.append({
            "variant_id": v.get("variant_id", ""),
            "plan_id": plan_id,
            "kind": v.get("kind", ""),
            "headline": v.get("headline", ""),
            "moderation_status": v.get("moderation_status", "pending"),
            "source": v.get("source", ""),
            "leads": _safe_int(leads_by_campaign.get(plan_id, 0)),
            "cost_minor": _safe_int(v.get("cost_minor", 0)),
            "created_at": v.get("created_at"),
        })
    approved = sum(1 for r in rows if r["moderation_status"] == "approved")
    return {"ok": True, "kind": "per-ad", "rows": rows,
            "totals": {"variants": len(rows), "approved": approved}}


def per_platform(tenant_id: str, *, campaign_id: str = "") -> dict:
    """Per-platform rollup from campaigns: group by provider (meta/google/...) with campaign count,
    spend, and a lead count joined from leads_ads. Store-only; empty-but-valid."""
    try:
        recs = store.list_campaigns(tenant_id)
    except Exception:  # noqa: BLE001
        recs = []
    leads = _leads(tenant_id)
    plan_ids_by_provider: dict = {}
    agg: dict = {}
    for rec in recs:
        if not isinstance(rec, dict):
            continue
        if campaign_id and str(rec.get("plan_id") or "") != str(campaign_id):
            continue
        prov = str(rec.get("provider") or "noop")
        a = agg.setdefault(prov, {"platform": prov, "campaigns": 0,
                                  "spend_today_minor": 0, "spend_life_minor": 0,
                                  "active": 0, "leads": 0})
        a["campaigns"] += 1
        a["spend_today_minor"] += _safe_int(rec.get("spend_today_minor", 0))
        a["spend_life_minor"] += _safe_int(rec.get("spend_life_minor", 0))
        if str(rec.get("status", "")) == "active":
            a["active"] += 1
        plan_ids_by_provider.setdefault(prov, set()).add(str(rec.get("plan_id") or ""))
    # join leads -> provider via the lead's campaign_id matching a plan_id.
    for lr in leads:
        cid = str(lr.get("campaign_id") or "")
        if not cid:
            continue
        for prov, plan_ids in plan_ids_by_provider.items():
            if cid in plan_ids:
                agg[prov]["leads"] += 1
                break
    rows = list(agg.values())
    totals = {
        "spend_today_minor": sum(r["spend_today_minor"] for r in rows),
        "spend_life_minor": sum(r["spend_life_minor"] for r in rows),
        "campaigns": sum(r["campaigns"] for r in rows),
        "leads": sum(r["leads"] for r in rows),
    }
    return {"ok": True, "kind": "per-platform", "rows": rows, "totals": totals}


def real_vs_reported(tenant_id: str, *, campaign_id: str = "") -> dict:
    """Real (CRM-true) vs platform-reported conversions from the conversions ledger, grouped by
    event_name. `real` = our crm_true count; `reported` = the platform_reported counts the platform
    echoed back. match_rate = reported/real (clamped display). Store-only; empty-but-valid."""
    rows_in = [r for r in _conversions(tenant_id)
               if isinstance(r, dict) and _campaign_match(r, campaign_id)]
    by_event: dict = {}
    for c in rows_in:
        ev = str(c.get("event_name") or "unknown")
        a = by_event.setdefault(ev, {"event": ev, "real": 0, "reported": 0})
        if c.get("crm_true"):
            a["real"] += 1
        pr = c.get("platform_reported") if isinstance(c.get("platform_reported"), dict) else {}
        for _plat, val in pr.items():
            if val is not None:
                a["reported"] += _safe_int(val, 0) if not isinstance(val, bool) else 1
        # also count a successfully-sent CAPI/Data-Manager event as reported when no echo present.
        if not pr or all(v is None for v in pr.values()):
            if (c.get("sent_meta") or {}).get("ok") or (c.get("sent_google") or {}).get("ok"):
                a["reported"] += 1
    rows = []
    for a in by_event.values():
        real = a["real"]
        reported = a["reported"]
        a["match_rate"] = round((reported / real), 4) if real else 0.0
        rows.append(a)
    total_real = sum(r["real"] for r in rows)
    total_reported = sum(r["reported"] for r in rows)
    return {"ok": True, "kind": "real-vs-reported", "rows": rows,
            "totals": {"real": total_real, "reported": total_reported,
                       "match_rate": round((total_reported / total_real), 4) if total_real else 0.0}}


# Dispatch table for the GET /ads/analytics/{kind} route (hyphenated kinds match `_lib.ts`).
ANALYTICS_KINDS = {
    "funnel": funnel,
    "per-ad": per_ad,
    "per-platform": per_platform,
    "real-vs-reported": real_vs_reported,
}


def rollup(tenant_id: str, kind: str, *, campaign_id: str = "") -> dict | None:
    """Dispatch one analytics kind -> its rollup dict, or None for an unknown kind (route -> 404)."""
    fn = ANALYTICS_KINDS.get(str(kind or ""))
    if fn is None:
        return None
    try:
        return fn(tenant_id, campaign_id=campaign_id)
    except Exception:  # noqa: BLE001 — empty-but-valid, never raise into the route
        return {"ok": True, "kind": str(kind), "rows": [], "totals": {}}


# ===========================================================================
# LEAD + CONSENT VIEWS (BLINDSPOTS B8) — normalize a stored leads_ads row into the
# `_lib.ts:AdsLead` shape (id / phone_masked / consent_status / gate_decision / score /
# call_outcome) so LeadsTab renders real values instead of blanks. Phone is masked
# (last 4 only) — the raw E.164 number never leaves the backend in a list/detail read.
# ===========================================================================
def _mask_phone(phone: str) -> str:
    ph = str(phone or "")
    digits = "".join(ch for ch in ph if ch.isdigit())
    if len(digits) >= 4:
        return "•••" + digits[-4:]
    return ""


def _consent_status_for(lead: dict) -> str:
    """Derive a coarse consent status from the lead's gate verdict / block reason."""
    status = str(lead.get("status", ""))
    if status == "blocked_no_consent":
        return "blocked_no_consent"
    g = lead.get("gate") if isinstance(lead.get("gate"), dict) else {}
    if g.get("allow"):
        return "consent_ok"
    reason = str(g.get("reason") or lead.get("block_reason") or "")
    return reason or ("consent_ok" if _is_dialed(lead) else "pending")


def lead_view(lead: dict) -> dict:
    """Project a stored leads_ads row -> `_lib.ts:AdsLead` (default-safe; phone masked)."""
    lead = lead or {}
    gate = lead.get("gate") if isinstance(lead.get("gate"), dict) else {}
    return {
        "id": lead.get("lead_id", ""),
        "lead_id": lead.get("lead_id", ""),
        "name": lead.get("name", ""),
        "phone_masked": _mask_phone(lead.get("phone", "")),
        "source": lead.get("source", ""),
        "consent_status": _consent_status_for(lead),
        "gate_decision": str(gate.get("reason") or lead.get("status", "")),
        "score": lead.get("score"),
        "call_outcome": lead.get("call_outcome", lead.get("status", "")),
        "cpl_minor": lead.get("cpl_minor"),
        "campaign": lead.get("campaign_id", ""),
        "status": lead.get("status", ""),
        "ts": lead.get("ingested_ts") or lead.get("gated_ts"),
    }


def list_leads(tenant_id: str, *, limit: int = 1000) -> dict:
    """GET /ads/leads -> `_lib.ts:AdsLeadsResponse` (newest first, normalized to AdsLead)."""
    rows = _leads(tenant_id)
    leads = [lead_view(r) for r in reversed(rows)][:max(1, int(limit or 1000))]
    return {"ok": True, "leads": leads, "count": len(rows), "next_cursor": None}


def get_lead(tenant_id: str, lead_id: str) -> dict | None:
    """GET /ads/leads/{id} -> the raw stored row (or None). The route normalizes via lead_view."""
    for r in _leads(tenant_id):
        if isinstance(r, dict) and r.get("lead_id") == lead_id:
            return r
    return None


def consent_for_lead(tenant_id: str, lead_id: str, *, phone: str = "") -> dict:
    """GET /ads/consent/{leadId} -> `_lib.ts:AdsConsentResponse` ({ok, lead_id, entries}).

    Filters the tenant's hash-chained consent_log to rows for THIS lead (by lead_id OR the lead's
    phone), masking the phone. Empty-but-valid when the lead has no recorded consent."""
    try:
        rows = store.consent_log_rows(tenant_id)
    except Exception:  # noqa: BLE001
        rows = []
    ph = str(phone or "")
    entries = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        if r.get("lead_id") == lead_id or (ph and r.get("phone") == ph):
            entries.append({
                "ts": r.get("when"),
                "kind": r.get("kind", ""),
                "status": "revoked" if r.get("revoked") else ("granted" if r.get("granted") else "denied"),
                "method": r.get("method", ""),
                "source": r.get("source", ""),
                "hash": r.get("hash_chain", ""),
                "prev_hash": r.get("prev_hash", ""),
            })
    return {"ok": True, "lead_id": lead_id, "entries": entries}
