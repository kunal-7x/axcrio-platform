"""ads_engine.ad_events — the CONVERSION-SIGNAL SUBSTRATE (V2-W3 parity loop).

The optimizer is only as smart as the signal it sees. Meta/Google run on first-party conversion
events (Pixel + CAPI); without our own event spine, every budget/creative decision flies blind
(research/comp-autonomy.md gap #2). This module is that spine: an APPEND-ONLY, idempotent ingestion
of pixel/server conversion events, a SAME-DAY mapping of the high-quality ones to Meta/Google via the
existing feedback loop, and an aggregation that feeds the bandit REAL-buyer labels (qualified/hot/
booked) instead of cheap form-submits.

Event ladder (master plan §8 — the closed loop the voice earner uniquely produces):

    lead_submitted -> call_connected -> lead_qualified / hot -> site_visit_booked -> booking
    └ pixel/webhook ┘ └─ voice earner (telephony connector) ─┘ └──── CRM ────┘

Only the QUALITY rungs (qualified/hot/visited/booked) escalate to CAPI — the platform already counted
the raw "Lead" at form-submit; what it does NOT know is which of those our ground truth says is a real
buyer. Feeding that back same-day is the moat (research §A.16-17 proxy trap; reuse feedback.emit_quality).

EARNER-SAFE: no caller.py/agent.py/voice edit; NO `from caller import ...`. All IO via store seams;
CAPI via the injectable feedback path (dormant/mocked offline => no socket). Every fn NEVER raises into
the tick/spine — a failure is a structured result, never an exception. Deterministic + offline-testable.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Optional

from . import feedback, optimization, store

_log = logging.getLogger("ads_engine.ad_events")

# ---------------------------------------------------------------------------
# EVENT VOCABULARY — the canonical conversion ladder + common pixel upper-funnel events.
# ---------------------------------------------------------------------------
EV_LEAD_SUBMITTED = "lead_submitted"     # form/CTWA submit (platform already counts this)
EV_CALL_CONNECTED = "call_connected"     # the 60s voice earner reached the lead
EV_LEAD_QUALIFIED = "lead_qualified"     # our scorer/agent says: real, intent-bearing
EV_HOT = "hot"                           # hottest in-call signal (strongest pre-CRM)
EV_SITE_VISIT_BOOKED = "site_visit_booked"   # CRM: a visit is on the calendar
EV_BOOKING = "booking"                   # CRM: a booking/sale closed (terminal truth)
# Upper-funnel pixel events (dense early proxy signal; never escalated to CAPI quality).
EV_PAGE_VIEW = "page_view"
EV_VIEW_CONTENT = "view_content"
EV_CLICK = "click"

CONVERSION_LADDER = (
    EV_LEAD_SUBMITTED, EV_CALL_CONNECTED, EV_LEAD_QUALIFIED, EV_HOT,
    EV_SITE_VISIT_BOOKED, EV_BOOKING,
)
PROXY_EVENTS = frozenset({EV_PAGE_VIEW, EV_VIEW_CONTENT, EV_CLICK, EV_CALL_CONNECTED})
KNOWN_EVENTS = frozenset(CONVERSION_LADDER) | PROXY_EVENTS

# Ordinal rank for "strongest signal wins" + monotonic ladder progress (learning-phase counting).
_RANK = {ev: i for i, ev in enumerate(CONVERSION_LADDER)}

# The QUALITY rungs that escalate to CAPI same-day, and the feedback.py quality-event they map to.
# (feedback derives Meta/Google events from a {score, crm_outcome} lead; we map the rung to those.)
_CAPI_QUALITY = {
    EV_LEAD_QUALIFIED: {"score": "qualified", "crm_outcome": "qualified"},
    EV_HOT:            {"score": "hot", "crm_outcome": "qualified"},
    EV_SITE_VISIT_BOOKED: {"score": "warm", "crm_outcome": "visited"},
    EV_BOOKING:        {"score": "warm", "crm_outcome": "booked"},
}

# Per-rung CRM-true conversion WEIGHT folded into the bandit reward. A booking is worth far more than a
# bare qualified; a connected call is a dense proxy (small positive). lead_submitted is the form-fill the
# platform already over-counts — it contributes NOTHING to the true-conversion term (proxy trap guard).
_TRUE_CONV_WEIGHT = {
    EV_LEAD_QUALIFIED: 0.5,
    EV_HOT: 0.7,
    EV_SITE_VISIT_BOOKED: 0.85,
    EV_BOOKING: 1.0,
}


def _norm(s: Any) -> str:
    return str(s or "").strip().lower()


def make_event_id(tenant_id: str, lead_id: str, ad_id: str, event_type: str) -> str:
    """Deterministic, TENANT-PREFIXED idempotency key. The SAME (tenant, lead, ad, type) always yields
    the SAME id, so a pixel duplicate, a webhook retry and a server event collapse to ONE row.
    Tenant-prefix makes a cross-tenant id collision structurally impossible."""
    return f"{_norm(tenant_id)}|{_norm(lead_id)}|{_norm(ad_id)}|{_norm(event_type)}"


# ===========================================================================
# INGEST — append-only, idempotent. The single producer door for pixel/server events.
# ===========================================================================
def ingest_event(tenant_id: str, ev: dict, *, now_ts: Optional[float] = None) -> dict:
    """Append ONE conversion-signal event to the tenant's ad_events spine (idempotent on event_id).

    Required-ish fields (all degrade-safe): type (an event name), ad_id/variant_id, source_campaign_id,
    lead_id, platform, sentiment, value_minor, and any matchable user_data (phone/email/name/source_ref)
    for the downstream CAPI map. Returns {ingested, deduped, event}. NEVER raises into the producer."""
    try:
        if not tenant_id:
            return {"ingested": False, "reason": "no_tenant"}
        e = dict(ev or {})
        etype = _norm(e.get("type") or e.get("event"))
        if not etype:
            return {"ingested": False, "reason": "no_type"}
        ts = float(now_ts if now_ts is not None else e.get("ts") or time.time())
        lead_id = str(e.get("lead_id") or "")
        ad_id = str(e.get("ad_id") or e.get("variant_id") or "")
        eid = str(e.get("event_id") or make_event_id(tenant_id, lead_id, ad_id, etype))

        existing = store.find_ad_event(tenant_id, eid)
        if existing is not None:
            return {"ingested": False, "deduped": True, "event": existing}

        row = {
            "event_id": eid,
            "type": etype,
            "ts": ts,
            "source_campaign_id": str(e.get("source_campaign_id") or e.get("campaign_id") or ""),
            "campaign_id": str(e.get("campaign_id") or e.get("source_campaign_id") or ""),
            "ad_id": ad_id,
            "variant_id": str(e.get("variant_id") or ad_id or ""),
            "platform": _norm(e.get("platform")) or "meta",
            "lead_id": lead_id,
            "sentiment": _norm(e.get("sentiment")),
            "value_minor": int(e.get("value_minor") or 0),
            # matchable identifiers for the CAPI map (hashed by the connector, NEVER stored hashed here).
            "user_data": {k: e.get(k) for k in ("phone", "email", "name") if e.get(k)},
            "source_ref": e.get("source_ref") if isinstance(e.get("source_ref"), dict) else {},
            # CAPI send-state (stamped later by the same-day drain; None => not yet sent).
            "capi_sent_at": None,
            "capi_status": None,
            "is_quality": etype in _CAPI_QUALITY,
        }
        store.append_ad_event(tenant_id, row)
        return {"ingested": True, "deduped": False, "event": row}
    except Exception as exc:  # noqa: BLE001 — ingest NEVER raises into the producer
        _log.warning("ad_events.ingest_event failed: %r", type(exc).__name__)
        return {"ingested": False, "reason": "ingest_error"}


def _event_to_lead(ev: dict) -> dict:
    """Project an ad_event into the {score, crm_outcome, ...} lead shape feedback.emit_quality expects."""
    etype = _norm(ev.get("type"))
    mapped = _CAPI_QUALITY.get(etype, {})
    ud = ev.get("user_data") or {}
    return {
        "lead_id": str(ev.get("lead_id") or ev.get("event_id") or ""),
        "campaign_id": str(ev.get("campaign_id") or ev.get("source_campaign_id") or ""),
        "score": mapped.get("score", ""),
        "crm_outcome": mapped.get("crm_outcome", ""),
        "value_minor": int(ev.get("value_minor") or 0),
        "phone": ud.get("phone"), "email": ud.get("email"), "name": ud.get("name"),
        "source_ref": ev.get("source_ref") or {},
    }


# ===========================================================================
# SAME-DAY CAPI — escalate the QUALITY rungs to Meta/Google via the existing feedback loop.
# ===========================================================================
async def same_day_capi_drain(tenant_id: str, *, now_epoch: Optional[float] = None,
                              emit_fn: Any = None, max_events: int = 200) -> dict:
    """Send every NOT-yet-sent QUALITY ad_event to CAPI (reusing feedback.emit_quality), stamping
    capi_sent_at/capi_status onto the row. SAME-DAY by construction: the tick runs this each pass, so a
    qualified/booked signal reaches Meta the day it happens (the moat). DRY/dormant-safe: a dormant
    connector returns not_configured -> capi_status='pending' (feedback queues a retry), never an error.

    Returns {sent, pending, skipped}. NEVER raises into the tick."""
    out = {"sent": 0, "pending": 0, "skipped": 0}
    try:
        emit = emit_fn or feedback.emit_quality
        events = store.get_ad_events(tenant_id)
        n = 0
        for ev in events:
            if n >= max_events:
                break
            if not ev.get("is_quality") or ev.get("capi_sent_at"):
                continue
            n += 1
            lead = _event_to_lead(ev)
            try:
                res = await emit(tenant_id, lead, now_epoch=now_epoch)
            except Exception as exc:  # noqa: BLE001 — one event's failure never aborts the drain
                _log.warning("ad_events.same_day_capi_drain emit failed: %r", type(exc).__name__)
                res = {"emitted": False, "reason": "emit_error"}
            emitted = bool(res.get("emitted"))
            meta_ok = bool((res.get("meta") or {}).get("ok"))
            google_ok = bool((res.get("google") or {}).get("ok"))
            if emitted and (meta_ok or google_ok):
                status = "sent"
                out["sent"] += 1
            elif not emitted and res.get("reason") == "no_quality_event":
                status = "skipped"
                out["skipped"] += 1
            else:
                status = "pending"   # dormant connector / dry-run / failed dest -> feedback retry queue
                out["pending"] += 1
            store.update_ad_event(tenant_id, str(ev.get("event_id")), {
                "capi_sent_at": float(now_epoch if now_epoch is not None else time.time())
                if status == "sent" else None,
                "capi_status": status,
            })
        return out
    except Exception as exc:  # noqa: BLE001
        _log.warning("ad_events.same_day_capi_drain failed: %r", type(exc).__name__)
        return out


# ===========================================================================
# AGGREGATION — events -> per-variant + per-platform signal the optimizer consumes.
# ===========================================================================
def aggregate_signals(events: list, *, campaign_id: Optional[str] = None) -> dict:
    """Roll an event list up to per-variant and per-platform signal buckets.

    Per variant: impressions/clicks (proxy), and CRM-true conversion weight (quality rungs only — a
    lead_submitted contributes ZERO true-conv, defeating the form-fill proxy trap). Returns
    {"variants": {vid: {...}}, "platforms": {plat: {...}}}. Pure, deterministic, never raises."""
    variants: dict = {}
    platforms: dict = {}
    for ev in events or []:
        if campaign_id is not None and str(ev.get("campaign_id") or ev.get("source_campaign_id")) != str(campaign_id):
            continue
        etype = _norm(ev.get("type"))
        vid = str(ev.get("variant_id") or ev.get("ad_id") or "")
        plat = _norm(ev.get("platform")) or "meta"
        v = variants.setdefault(vid, {"variant_id": vid, "impressions": 0, "clicks": 0,
                                      "lp_views": 0, "leads": 0, "qualified": 0, "hot": 0,
                                      "visited": 0, "booked": 0, "true_conv": 0.0,
                                      "value_minor": 0})
        p = platforms.setdefault(plat, {"platform": plat, "impressions": 0, "clicks": 0,
                                        "true_conv": 0.0, "value_minor": 0})
        # Proxy counters (dense early signal).
        if etype in (EV_PAGE_VIEW, EV_VIEW_CONTENT):
            v["impressions"] += 1; v["lp_views"] += 1; p["impressions"] += 1
        if etype == EV_CLICK:
            v["clicks"] += 1; p["clicks"] += 1
        if etype == EV_CALL_CONNECTED:
            v["clicks"] += 1; p["clicks"] += 1  # a connected call is a strong engagement proxy
        if etype == EV_LEAD_SUBMITTED:
            v["leads"] += 1
        # Quality rungs -> CRM-true conversion weight (the honest reward).
        if etype == EV_LEAD_QUALIFIED:
            v["qualified"] += 1
        elif etype == EV_HOT:
            v["hot"] += 1
        elif etype == EV_SITE_VISIT_BOOKED:
            v["visited"] += 1
        elif etype == EV_BOOKING:
            v["booked"] += 1
        w = _TRUE_CONV_WEIGHT.get(etype, 0.0)
        if w:
            v["true_conv"] += w
            p["true_conv"] += w
            val = int(ev.get("value_minor") or 0)
            v["value_minor"] += val
            p["value_minor"] += val
    return {"variants": variants, "platforms": platforms}


def feed_optimizer(tenant_id: str, campaign_id: str, *, window_s: Optional[float] = None,
                   now_ts: Optional[float] = None, persist: bool = True) -> dict:
    """Fold the LIVE ad_events for a campaign into its bandit_state, REWARDING quality rungs (real-buyer
    labels) — not form-submits. Reuses optimization.update_arm + the existing BanditState shape; only the
    SIGNAL source is new. CAS-persists the updated state (propose-only; never spends). Returns a summary.

    This is what makes the continuous daemon optimize on conversations, not clicks (the differentiator)."""
    try:
        since = None
        if window_s is not None:
            since = float(now_ts if now_ts is not None else time.time()) - float(window_s)
        events = store.get_ad_events(tenant_id, since_ts=since)
        agg = aggregate_signals(events, campaign_id=campaign_id)
        variants = agg["variants"]
        if not variants:
            return {"ok": True, "updated_arms": 0, "reason": "no_signal"}
        existing = store.get_bandit_state(tenant_id, campaign_id)
        state = existing if isinstance(existing, dict) and existing else \
            optimization.new_bandit_state(campaign_id, tenant_id)
        updated = 0
        for vid, s in variants.items():
            if not vid:
                continue
            impressions = int(s["impressions"]) or int(s["clicks"]) or 1
            # pCVR proxy = clicks / impressions (dense, early). true_conv = quality-weighted (honest).
            pcvr = (float(s["clicks"]) / impressions) if impressions else 0.0
            true_conv = float(s["true_conv"])
            optimization.update_arm(
                state, vid,
                pcvr_calibrated=min(1.0, pcvr),
                observed_conv=true_conv,
                expected_observed_fraction=1.0,
                platform_reported_conv=float(s["leads"]),  # platform counts form-fills…
                crm_true_conv=true_conv,                    # …we reconcile to CRM-true quality
                impressions=impressions, clicks=int(s["clicks"]),
                lp_views=int(s["lp_views"]),
                ts=int(now_ts if now_ts is not None else time.time()))
            updated += 1
        # Stamp the current leader so the daemon/UI knows the winning variant (reuses the bandit's own
        # posterior-confidence estimator; propose_bandit_moves still re-gates before any spend move).
        try:
            best_id, conf = optimization.best_arm_confidence(state)
            state["best_arm_id"] = best_id
            state["best_arm_confidence"] = conf
        except Exception:  # noqa: BLE001
            pass
        if persist:
            try:
                ver = int(existing.get("version", 0) or 0) if isinstance(existing, dict) and existing else None
                store.put_bandit_state(tenant_id, campaign_id, state, expected_version=ver)
            except store.VersionConflict:
                _log.info("ad_events.feed_optimizer: bandit_state CAS conflict %s/%s (retry next tick)",
                          tenant_id, campaign_id)
        return {"ok": True, "updated_arms": updated, "best_arm_id": state.get("best_arm_id"),
                "state": state}
    except Exception as exc:  # noqa: BLE001 — never raise into the daemon
        _log.warning("ad_events.feed_optimizer failed: %r", type(exc).__name__)
        return {"ok": False, "reason": "feed_error"}


__all__ = [
    "ingest_event", "same_day_capi_drain", "aggregate_signals", "feed_optimizer",
    "make_event_id", "CONVERSION_LADDER", "KNOWN_EVENTS",
    "EV_LEAD_SUBMITTED", "EV_CALL_CONNECTED", "EV_LEAD_QUALIFIED", "EV_HOT",
    "EV_SITE_VISIT_BOOKED", "EV_BOOKING",
]
