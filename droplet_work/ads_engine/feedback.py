"""ads_engine.feedback — the QUALITY feedback loop back to Meta + Google (W6).

THE HONESTY CORE. After an AI call lands and the lead is scored (and the CRM-true outcome is
known), we send the *quality* signal back to the ad platforms — NOT "a form was submitted". The
platform already counted the lead at form-submit; what it does NOT know is whether OUR ground
truth says that lead is Hot / Qualified / Booked or Junk. Feeding that CRM-true quality back is
what makes the optimizer reward real revenue, not cheap form-fills (research §A.16-17 proxy trap).

Two destinations, ONE deterministic event_id (idempotent dedup across both + retries):

  * META — Conversions API on the UNIFIED Dataset (POST /{dataset_id}/events). The legacy
    Offline Event Sets path was removed 2025-05-14; we send to the Dataset only. action_source is
    `phone_call` for the AI-call-sourced quality signal and `system_generated` for a CRM-derived
    outcome (visited/booked). user_data is SHA-256 hashed by the connector (NEVER plaintext PII).
    Extends connectors/meta.py: build_capi_event + send_capi (already W6-shaped).

  * GOOGLE — the **Data Manager API** :ingestEvents (datamanager.googleapis.com). The Ads-API
    offline-conversion + EC-for-leads path is BLOCKED for new integrations from 2026-06-15 (we are
    NOT allowlisted) — a legacy UploadClickConversions call is a HARD NO (BLOCKED_GOOGLE_LEGACY).
    So ALL Google conversion feedback goes through Data Manager (config.DATA_MANAGER_API_REVISION).
    Extends connectors/google.py: upload_conversions (the :ingestEvents path).

event_id = `tenant_id|lead_id|event_name` (TENANT-PREFIXED + idempotent): the same lead+event
always yields the same id, so a CAPI retry, a pixel duplicate, and the Google ingest all dedup to
one conversion. Tenant-prefixing makes a cross-tenant id collision structurally impossible.

reconciliation_factor = crm_true_count / max(platform_reported_count, 1), CLAMPED to [0.1, 3.0],
written into bandit_state so `optimization` rewards CRM-true conversions, not raw platform counts.

EARNER-SAFE: no caller.py / agent.py / voice edit. NO `from caller import ...`. All IO via the
injected store seam; connectors resolved via the (injectable) connectors.get_connector seam so the
offline tests run against a MOCKED connector with ZERO real network. Every public fn is async-or-
sync but NEVER raises into the tick / the live spine — a failure is a structured result + a retry
queue row, never an exception.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Callable, Optional

from . import config, store

_log = logging.getLogger("ads_engine.feedback")

# ---------------------------------------------------------------------------
# QUALITY EVENT VOCABULARY — what we send back (NOT "Lead"/"form submitted").
#
# The platform already booked the raw "Lead" at form-submit. The feedback loop sends the QUALITY
# escalation: Qualified (our scorer says it's a real, intent-bearing lead) and the CRM-true
# milestones Visited / Booked. A Junk-scored lead deliberately sends NOTHING (we don't reward the
# platform for a bad lead) — the absence IS the negative signal vs. the platform's optimistic count.
# ---------------------------------------------------------------------------
EVENT_QUALIFIED = "Qualified"
EVENT_VISITED = "Visited"
EVENT_BOOKED = "Booked"
EVENT_LEAD = "Lead"  # only used when explicitly re-sending the base lead (rare; reconcile path)

_QUALITY_EVENTS = frozenset({EVENT_QUALIFIED, EVENT_VISITED, EVENT_BOOKED, EVENT_LEAD})

# Score -> the lead_quality custom_data tag (the honest "platform thinks lead; CRM says <x>").
# Hot/Warm/Investor/End-user all clear the QUALIFIED bar; Junk sends nothing (negative-by-absence).
_QUALIFYING_SCORES = frozenset({"hot", "warm", "investor", "end_user", "end-user"})
_JUNK_SCORES = frozenset({"junk", "", "none"})

# CRM-true outcome -> the milestone event it emits (the strongest available signal wins).
_CRM_OUTCOME_EVENT = {
    "booked": EVENT_BOOKED,
    "visited": EVENT_VISITED,
    "qualified": EVENT_QUALIFIED,
    # "lost" / "" -> no positive milestone (the lead did not convert).
}

# action_source per event origin (research §5 / design §7.1).
ACTION_SOURCE_CALL = "phone_call"        # the AI-call-sourced quality signal
ACTION_SOURCE_CRM = "system_generated"   # a CRM-derived outcome (visited/booked)

# reconciliation clamp (design §2.3 / §7.3) — env can never widen it (HARD code bounds).
RECON_FACTOR_MIN = 0.1
RECON_FACTOR_MAX = 3.0


# ---------------------------------------------------------------------------
# CONNECTOR SEAM — injectable so the offline tests use a MOCKED connector (no network).
# Default resolves the real connectors.get_connector (which itself returns None when dormant).
# ---------------------------------------------------------------------------
_get_connector: Optional[Callable[..., Any]] = None


def set_connector_resolver(fn: Optional[Callable[..., Any]]) -> None:
    """Inject a connector resolver fn(tenant_id, channel, *, http=None) -> connector|None.

    Tests pass a resolver that returns a mock Meta/Google connector (so send_capi /
    upload_conversions hit a MockTransport, never a socket). Default uses the real registry."""
    global _get_connector
    _get_connector = fn


def _resolve_connector(tenant_id: str, channel: str):
    """Resolve a connector for (tenant, channel) via the injected seam, else the real registry.
    None => the channel is dormant (no creds / not configured); the caller skips that destination."""
    fn = _get_connector
    if fn is None:
        try:
            from . import connectors
            fn = connectors.get_connector
        except Exception:  # noqa: BLE001 — connectors package unavailable => dormant
            return None
    try:
        return fn(tenant_id, channel)
    except Exception as exc:  # noqa: BLE001 — degrade-never-raise into the spine
        _log.warning("feedback._resolve_connector(%s) failed: %r", channel, type(exc).__name__)
        return None


# ===========================================================================
# EVENT DERIVATION — score + crm_outcome -> the quality event(s) to emit.
# ===========================================================================
def _norm(s: Any) -> str:
    return str(s or "").strip().lower()


def derive_event(lead: dict) -> Optional[str]:
    """Map a scored lead -> the SINGLE strongest quality event to emit, or None to emit nothing.

    Precedence (strongest-true-signal wins): CRM-true outcome (booked > visited > qualified) THEN
    the call score (a qualifying score -> Qualified). A Junk score with no CRM milestone emits
    NOTHING — we never feed the platform a positive signal for a bad lead (the absence is the
    honest negative). Returns an event name in _QUALITY_EVENTS, or None."""
    crm = _norm(lead.get("crm_outcome"))
    ev = _CRM_OUTCOME_EVENT.get(crm)
    if ev:
        return ev
    score = _norm(lead.get("score"))
    if score in _QUALIFYING_SCORES:
        return EVENT_QUALIFIED
    # Junk / unscored / lost with no milestone -> emit nothing (negative-by-absence).
    return None


def _action_source_for(event_name: str, lead: dict) -> str:
    """phone_call for the AI-call-sourced Qualified signal; system_generated for CRM milestones."""
    if event_name in (EVENT_VISITED, EVENT_BOOKED):
        return ACTION_SOURCE_CRM
    # Qualified is derived from the AI call outcome unless it came from a CRM 'qualified' flag.
    if _norm(lead.get("crm_outcome")) == "qualified":
        return ACTION_SOURCE_CRM
    return ACTION_SOURCE_CALL


def make_event_id(tenant_id: str, lead_id: str, event_name: str) -> str:
    """The deterministic, TENANT-PREFIXED, idempotent dedup key: `tenant_id|lead_id|event_name`.

    The SAME (tenant, lead, event) always yields the SAME id, so a CAPI retry, a pixel duplicate,
    and the Google ingest all collapse to ONE conversion. Tenant-prefixing makes a cross-tenant id
    collision impossible (lead A of tenant X never dedups against tenant Y)."""
    return f"{str(tenant_id)}|{str(lead_id)}|{str(event_name)}"


# ===========================================================================
# CONVERSION RECORD — the platform-reported vs CRM-true substrate (conversions.json).
# ===========================================================================
def _find_conversion(tenant_id: str, event_id: str) -> Optional[dict]:
    """Find the existing conversion row by event_id (idempotency: never double-create). None-safe."""
    try:
        for row in store.get_tenant_file(tenant_id, "conversions"):
            if row.get("event_id") == event_id:
                return row
    except Exception:  # noqa: BLE001
        return None
    return None


def _upsert_conversion(tenant_id: str, conv: dict) -> None:
    """Idempotent upsert of a conversion row by event_id (rewrite in place, else append)."""
    try:
        rows = store.get_tenant_file(tenant_id, "conversions")
        eid = conv.get("event_id")
        found = False
        out = []
        for r in rows:
            if r.get("event_id") == eid:
                out.append(conv)
                found = True
            else:
                out.append(r)
        if not found:
            out.append(conv)
        store.put_tenant_file(tenant_id, "conversions", out)
    except Exception:  # noqa: BLE001 — persistence failure must never crash the spine
        _log.warning("feedback._upsert_conversion failed for %s", conv.get("event_id"))


def _build_conversion(tenant_id: str, lead: dict, event_name: str, *,
                      now_ts: Optional[float] = None) -> dict:
    """Build the conversion record (design §2.3). crm_true=True (OUR ground truth from scoring)."""
    lead_id = str(lead.get("lead_id") or "")
    eid = make_event_id(tenant_id, lead_id, event_name)
    return {
        "conv_id": "cv_" + (eid.encode("utf-8").hex()[:10] if eid else ""),
        "tenant_id": str(tenant_id),
        "lead_id": lead_id,
        "campaign_id": str(lead.get("campaign_id") or ""),
        "event_name": event_name,
        "event_id": eid,
        "value_minor": int(lead.get("value_minor") or 0),
        "currency": config.caps().get("currency", "INR"),
        "crm_true": True,
        "lead_quality": _norm(lead.get("score")) or "qualified",
        "platform_reported": {"meta": None, "google": None},
        "sent_meta": {"ok": False, "ts": None, "fbtrace_id": "", "attempts": 0},
        "sent_google": {"ok": False, "ts": None, "request_id": "", "attempts": 0},
        "occurred_ts": float(now_ts if now_ts is not None else time.time()),
    }


# ===========================================================================
# USER-DATA — the matchable identifiers (hashed by the connector, never here-plaintext-out).
# ===========================================================================
def _user_data(lead: dict) -> dict:
    """Assemble the matchable user_data keys for CAPI. The connector SHA-256-hashes em/ph/fn/ln;
    fbp/fbc/ctwa_clid pass plaintext. We pass RAW values in (the connector normalizes+hashes) so we
    never hand a half-hashed blob downstream. Names split into fn/ln best-effort."""
    ud: dict = {}
    phone = str(lead.get("phone") or "")
    if phone:
        ud["ph"] = phone
    email = str(lead.get("email") or "")
    if email:
        ud["em"] = email
    name = str(lead.get("name") or "").strip()
    if name:
        parts = name.split()
        ud["fn"] = parts[0]
        if len(parts) > 1:
            ud["ln"] = parts[-1]
    # CTWA / Meta click identifiers (plaintext, kept by the connector's plaintext allowlist).
    ref = lead.get("source_ref") or {}
    if isinstance(ref, dict):
        if ref.get("ctwa_clid"):
            ud["ctwa_clid"] = str(ref["ctwa_clid"])
        # the Meta leadgen_id is a matchable external id for the Lead/Qualified follow-up.
        if ref.get("leadgen_id"):
            ud["lead_id"] = str(ref["leadgen_id"])
    return ud


def _custom_data(lead: dict, event_name: str) -> dict:
    """The lead_quality + value the platform reads (the honest CRM-true tag)."""
    return {
        "lead_quality": _norm(lead.get("score")) or _norm(lead.get("crm_outcome")) or "qualified",
        "value": int(lead.get("value_minor") or 0),
        "currency": config.caps().get("currency", "INR"),
        "lead_event_source": "elevatex_ai_call",
        "crm_outcome": _norm(lead.get("crm_outcome")),
    }


# ===========================================================================
# META CAPI SEND — unified Dataset (extends connectors/meta.py send_capi).
# ===========================================================================
async def _send_meta(tenant_id: str, lead: dict, event_name: str, conv: dict, *,
                     now_ts: float) -> dict:
    """Send ONE quality event to Meta CAPI (unified Dataset). Returns a result dict (never raises).

    Builds the event via the connector's build_capi_event (which hashes user_data) with the
    deterministic event_id for dedup, then POSTs via send_capi. A dormant connector (no creds) =>
    {ok:False, error:'not_configured'} and the conversion goes to the retry queue."""
    mc = _resolve_connector(tenant_id, "meta")
    if mc is None:
        return {"ok": False, "error": "not_configured", "channel": "meta"}
    try:
        ev = mc.build_capi_event(
            event_name=event_name,
            event_time=int(now_ts),
            action_source=_action_source_for(event_name, lead),
            user_data=_user_data(lead),
            custom_data=_custom_data(lead, event_name),
            event_id=conv.get("event_id", ""),
        )
        res = await mc.send_capi([ev])
    except Exception as exc:  # noqa: BLE001 — never raise into the spine
        _log.warning("feedback._send_meta failed: %r", type(exc).__name__)
        return {"ok": False, "error": "send_error", "channel": "meta"}
    ok = bool(getattr(res, "ok", False))
    detail = ""
    fbtrace = ""
    if not ok:
        err = getattr(res, "error", None)
        detail = getattr(err, "value", str(err)) if err is not None else getattr(res, "detail", "")
    data = getattr(res, "data", None)
    if isinstance(data, dict):
        fbtrace = str(data.get("fbtrace_id") or "")
    return {"ok": ok, "error": detail, "fbtrace_id": fbtrace, "channel": "meta",
            "event_id": conv.get("event_id", "")}


# ===========================================================================
# GOOGLE DATA MANAGER SEND — :ingestEvents (extends connectors/google.py upload_conversions).
# ===========================================================================
def _google_event(lead: dict, conv: dict, *, now_ts: float) -> dict:
    """Build ONE Data Manager ingestEvents event (design §7.2). gclid where present, else the
    enhanced-conversion hashed identifiers. The CONNECTOR sends; PII is hashed by the connector
    path — we pass the matchable raw identifiers + the deterministic dedup transactionId."""
    ref = lead.get("source_ref") or {}
    gclid = str(ref.get("gclid") or "") if isinstance(ref, dict) else ""
    ev: dict = {
        "transactionId": conv.get("event_id", ""),   # idempotency key (our tenant-prefixed event_id)
        "eventName": conv.get("event_name", ""),
        "conversionDateTime": int(now_ts),
        "currencyCode": config.caps().get("currency", "INR"),
        "conversionValue": int(lead.get("value_minor") or 0),
        "userData": _user_data(lead),
        "adIdentifiers": {},
    }
    if gclid:
        ev["adIdentifiers"]["gclid"] = gclid
    return ev


async def _send_google(tenant_id: str, lead: dict, event_name: str, conv: dict, *,
                       now_ts: float) -> dict:
    """Send ONE quality event to Google via the Data Manager API (:ingestEvents). Never raises.

    Routed through connectors/google.py upload_conversions, which targets datamanager.googleapis.com
    (config.DATA_MANAGER_API_REVISION) — the ONLY allowed Google path (the Ads-API offline path is
    BLOCKED for new integrations from 2026-06-15). A dormant connector => retry queue."""
    gc = _resolve_connector(tenant_id, "google")
    if gc is None:
        return {"ok": False, "error": "not_configured", "channel": "google"}
    try:
        ev = _google_event(lead, conv, now_ts=now_ts)
        res = await gc.upload_conversions([ev])   # Data Manager :ingestEvents — never the legacy path
    except Exception as exc:  # noqa: BLE001
        _log.warning("feedback._send_google failed: %r", type(exc).__name__)
        return {"ok": False, "error": "send_error", "channel": "google"}
    ok = bool(getattr(res, "ok", False))
    detail = ""
    req_id = ""
    if not ok:
        err = getattr(res, "error", None)
        detail = getattr(err, "value", str(err)) if err is not None else getattr(res, "detail", "")
    data = getattr(res, "data", None)
    if isinstance(data, dict):
        req_id = str(data.get("requestId") or data.get("request_id") or "")
    return {"ok": ok, "error": detail, "request_id": req_id, "channel": "google",
            "event_id": conv.get("event_id", "")}


# ===========================================================================
# THE PUBLIC EMIT — derive the event, persist the conversion, send BOTH, queue retries.
# ===========================================================================
async def emit_quality(tenant_id: str, lead: dict, *, event: Optional[str] = None,
                       now_epoch: Optional[float] = None) -> dict:
    """Emit the QUALITY signal for a scored lead to Meta CAPI + Google Data Manager.

    Flow: derive the strongest quality event (or skip a Junk lead) -> mint the deterministic
    tenant-prefixed event_id -> idempotently upsert the conversion row (crm_true=True) -> send to
    BOTH platforms -> stamp send-state -> queue any failed destination for the tick retry drain.

    NEVER raises. Returns a summary dict: {emitted, event, event_id, meta, google}. A Junk/unscored
    lead returns {emitted:False, reason:'no_quality_event'} and sends nothing (negative-by-absence).
    """
    try:
        if not tenant_id:
            return {"emitted": False, "reason": "no_tenant"}
        now_ts = float(now_epoch if now_epoch is not None else time.time())
        event_name = event if (event in _QUALITY_EVENTS) else derive_event(lead or {})
        if not event_name:
            return {"emitted": False, "reason": "no_quality_event",
                    "lead_id": (lead or {}).get("lead_id")}

        lead_id = str((lead or {}).get("lead_id") or "")
        eid = make_event_id(tenant_id, lead_id, event_name)

        # Idempotency: reuse the existing conversion row if this (lead,event) already fired.
        conv = _find_conversion(tenant_id, eid) or _build_conversion(
            tenant_id, lead or {}, event_name, now_ts=now_ts)
        conv["event_name"] = event_name
        conv["event_id"] = eid

        meta_res = await _send_meta(tenant_id, lead or {}, event_name, conv, now_ts=now_ts)
        google_res = await _send_google(tenant_id, lead or {}, event_name, conv, now_ts=now_ts)

        # Stamp send-state onto the conversion (attempt counters bumped; idempotent on event_id).
        conv["sent_meta"] = {
            "ok": bool(meta_res.get("ok")), "ts": now_ts if meta_res.get("ok") else None,
            "fbtrace_id": meta_res.get("fbtrace_id", ""),
            "attempts": int(conv.get("sent_meta", {}).get("attempts", 0)) + 1,
            "error": "" if meta_res.get("ok") else meta_res.get("error", ""),
        }
        conv["sent_google"] = {
            "ok": bool(google_res.get("ok")), "ts": now_ts if google_res.get("ok") else None,
            "request_id": google_res.get("request_id", ""),
            "attempts": int(conv.get("sent_google", {}).get("attempts", 0)) + 1,
            "error": "" if google_res.get("ok") else google_res.get("error", ""),
        }
        _upsert_conversion(tenant_id, conv)

        # Any failed destination -> the retry queue (idempotent on event_id; tick drains it).
        if not meta_res.get("ok"):
            _queue_retry(tenant_id, eid, "meta")
        if not google_res.get("ok"):
            _queue_retry(tenant_id, eid, "google")

        # Audit (best-effort; the conversion row IS the durable record).
        _audit(tenant_id, "feedback.emit", lead_id, {
            "event": event_name, "event_id": eid,
            "meta_ok": bool(meta_res.get("ok")), "google_ok": bool(google_res.get("ok"))})

        return {"emitted": True, "event": event_name, "event_id": eid,
                "meta": meta_res, "google": google_res}
    except Exception as exc:  # noqa: BLE001 — emit NEVER raises into the spine
        _log.warning("feedback.emit_quality failed: %r", type(exc).__name__)
        return {"emitted": False, "reason": "emit_error"}


# ===========================================================================
# RETRY QUEUE — failed sends drained by tick._feedback_retry_drain (idempotent on event_id).
# ===========================================================================
def _queue_retry(tenant_id: str, event_id: str, channel: str) -> None:
    """Record a failed destination for retry. The drain re-sends via emit (idempotent on event_id),
    so a duplicate queue row is harmless. Append-only into the per-tenant ads_audit stream."""
    try:
        store.append_tenant_row(tenant_id, "ads_audit", {
            "event": "feedback.retry_queued", "event_id": event_id,
            "channel": channel, "ts": time.time()})
    except Exception:  # noqa: BLE001
        pass


def _audit(tenant_id: str, action: str, lead_id: str, meta: dict) -> None:
    try:
        store.append_tenant_row(tenant_id, "ads_audit", {
            "event": action, "lead_id": lead_id, "meta": meta, "ts": time.time()})
    except Exception:  # noqa: BLE001
        pass


# ===========================================================================
# RECONCILIATION — CRM-true vs platform-reported -> a clamped factor in bandit_state.
# ===========================================================================
def _clamp_factor(raw: float) -> float:
    """Clamp the reconciliation factor into [RECON_FACTOR_MIN, RECON_FACTOR_MAX] (HARD bounds).

    A factor < 0.1 (platform massively over-reports vs our CRM truth) or > 3.0 (we see far more
    true conversions than the platform attributes) is clamped so a noisy ratio can never swing the
    optimizer's reward wildly. Always returns a float inside the band."""
    try:
        v = float(raw)
    except Exception:  # noqa: BLE001
        return 1.0
    if v != v:  # NaN guard
        return 1.0
    return max(RECON_FACTOR_MIN, min(RECON_FACTOR_MAX, v))


def compute_reconciliation(tenant_id: str) -> dict:
    """Compute the per-campaign reconciliation factor from the conversions ledger (pure read).

    recon_factor[campaign] = crm_true_count / max(platform_reported_count, 1), clamped [0.1, 3.0].
    crm_true_count = our scored conversions (crm_true==True). platform_reported_count = how many of
    those the platform actually attributed back (platform_reported.meta/google not None). Returns
    {campaign_id: {crm_true, platform_reported, factor}}. Never raises (returns {} on any error)."""
    out: dict = {}
    try:
        rows = store.get_tenant_file(tenant_id, "conversions")
    except Exception:  # noqa: BLE001
        return {}
    agg: dict = {}
    for r in rows or []:
        cid = str(r.get("campaign_id") or "")
        if not cid:
            continue
        a = agg.setdefault(cid, {"crm_true": 0, "platform_reported": 0})
        if r.get("crm_true"):
            a["crm_true"] += 1
        pr = r.get("platform_reported") or {}
        if isinstance(pr, dict) and (pr.get("meta") is not None or pr.get("google") is not None):
            a["platform_reported"] += 1
    for cid, a in agg.items():
        factor = _clamp_factor(a["crm_true"] / max(a["platform_reported"], 1))
        out[cid] = {"crm_true": a["crm_true"], "platform_reported": a["platform_reported"],
                    "factor": factor}
    return out


def reconcile(tenant_id: str) -> dict:
    """Compute reconciliation factors AND write each into the campaign's bandit_state so the
    optimizer rewards CRM-true conversions, not raw platform counts (design §7.3). Also a tick pass.

    For each campaign, CAS-merge `recon_factor` into the existing bandit_state row (creating a
    minimal row if none exists). Never raises — a write failure on one campaign is logged + skipped,
    the rest proceed. Returns the {campaign_id: {...factor}} map that was computed/applied."""
    factors = compute_reconciliation(tenant_id)
    for cid, info in factors.items():
        try:
            existing = store.get_bandit_state(tenant_id, cid) or {}
            merged = dict(existing)
            merged["recon_factor"] = info["factor"]
            merged["recon_crm_true"] = info["crm_true"]
            merged["recon_platform_reported"] = info["platform_reported"]
            merged["recon_ts"] = time.time()
            ver = int(existing.get("version", 0) or 0) if isinstance(existing, dict) else None
            store.put_bandit_state(tenant_id, cid, merged, expected_version=ver)
        except store.VersionConflict:
            # a concurrent writer bumped the row — skip this pass; the next tick re-applies.
            _log.info("feedback.reconcile: bandit_state CAS conflict for %s/%s (retry next tick)",
                      tenant_id, cid)
        except Exception as exc:  # noqa: BLE001 — one campaign's failure never aborts the rest
            _log.warning("feedback.reconcile write failed %s/%s: %r",
                         tenant_id, cid, type(exc).__name__)
    return factors
