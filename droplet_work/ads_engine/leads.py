"""ads_engine.leads — ad-lead ingest, normalize, gate, and the lead->call enqueue (W6).

Four ingest sources funnel into ONE normalized lead record with a SERVER-MINTED lead_id:
  (a) meta_leadgen — from the inbound webhook (page_id->tenant resolved + HMAC-verified upstream).
  (b) form         — own-landing FORM via a signed+scoped+revocable+rate-limited token.
  (c) ctwa         — click-to-WhatsApp inbound (free 72h entry-point window; still needs DCA voice).
  (d) bulk_import  — Dead-Lead Revival: a vendor uploads its OWN consented leads under a DPA.

On ingest -> compliance.pre_dial_gate(tenant, lead) -> if PASS, enqueue ONE instant dial.

ENQUEUE (the heart, redteam earner-safety C2 + M2): builds the SAME JOBS row + create_task(run_job)
as caller.py:5754-5768, via the INJECTED seams (seams().jobs / seams().run_job / seams().tenant_by_id
/ seams().active_calls) — NEVER `from caller import`. Applies the SAME tenant clamps as
caller.py:5752 (concurrency = max(1,min(req,20,tenant.max_concurrency)); hourly/daily from the
tenant rec). Tags the job source=ad + ads_source=<source> + ads_lead_id so the retry engine can
structurally skip it (the matching caller.py guard). force_window is COMPUTED by compliance
(quiet-hours + verified DCA voice consent), NEVER a literal True.

DRY-RUN UNTIL 140-SERIES (fork #1 / compliance M1): real ad-lead dialing stays DISABLED until the
`ADS_TELEPHONY_140` flag is set. In dry-run, enqueue LOGS the would-dial + the gate verdict but
does NOT place a call (no JOBS row, no create_task). Promo-voice 140-series is a HUMAN_TASK.

NO `from caller import ...`. Phone normalization + server-minted ids are pure. Never raises into
the webhook/route — an ingest error returns an error record, never an exception into the spine.
"""

from __future__ import annotations

import logging
import re
import time
import uuid
from typing import Any, Optional

from . import compliance, config, seams, store

_log = logging.getLogger("ads_engine.leads")

# Sources (the lead record's `source` enum).
SOURCE_META = "meta_leadgen"
SOURCE_FORM = "form"
SOURCE_CTWA = "ctwa"
SOURCE_BULK = "bulk_import"
_VALID_SOURCES = frozenset({SOURCE_META, SOURCE_FORM, SOURCE_CTWA, SOURCE_BULK})


# ---------------------------------------------------------------------------
# 140-series telephony gate (fork #1). Real ad-lead dialing stays DRY-RUN/disabled until a
# registered 140-series promo CLI is wired (consent does NOT cure non-140-series origination).
# ---------------------------------------------------------------------------
def telephony_140_enabled() -> bool:
    """True iff a 140-series promo-telephony path is confirmed wired (ADS_TELEPHONY_140). Default
    OFF => every ad-lead dial is DRY-RUN (logged, not placed). This is the M1 build-time gate."""
    return config._flag("ADS_TELEPHONY_140", "0")


# ===========================================================================
# NORMALIZE — one funnel, server-minted lead_id, E.164 +91 phone.
# ===========================================================================
def _mint_lead_id() -> str:
    return "ad_" + uuid.uuid4().hex[:10]


def _normalize_phone(raw: str) -> Optional[str]:
    """Phone -> E.164 +91… for Indian promo voice. Returns None for a non-Indian/invalid number
    (rejected for promo-voice — the gate would deny anyway, but we reject at ingest cheaply)."""
    digits = re.sub(r"\D", "", str(raw or ""))
    if not digits:
        return None
    if digits.startswith("91") and len(digits) == 12:
        return "+" + digits
    if len(digits) == 10 and digits[0] in "6789":
        return "+91" + digits
    if str(raw or "").strip().startswith("+91") and len(digits) == 12:
        return "+" + digits
    return None  # non-Indian / malformed -> not dial-eligible for promo voice


def normalize(source: str, raw: dict) -> dict:
    """Map any source's payload -> the ONE normalized lead record (server-minted lead_id).

    `raw` is the source-specific dict (meta field_data already flattened, form body, ctwa msg,
    bulk row). Every non-canonical field is preserved verbatim in raw_fields. tenant_id is NEVER
    taken from `raw` — the caller passes the authenticated/resolved tenant_id to ingest()."""
    src = source if source in _VALID_SOURCES else SOURCE_FORM
    name = str(raw.get("name") or raw.get("full_name") or "").strip()
    phone_raw = str(raw.get("phone") or raw.get("phone_number") or raw.get("num") or "")
    email = str(raw.get("email") or "").strip()
    phone = _normalize_phone(phone_raw)
    canonical = {"name", "full_name", "phone", "phone_number", "num", "email"}
    raw_fields = {k: v for k, v in raw.items() if k not in canonical}
    return {
        "lead_id": _mint_lead_id(),       # SERVER-MINTED — never client-supplied.
        "source": src,
        "source_ref": raw.get("source_ref") or {},
        "name": name,
        "phone": phone or "",
        "phone_raw": phone_raw,
        "email": email,
        "raw_fields": raw_fields,
        "campaign_id": str(raw.get("campaign_id") or ""),
        "consent_ref": "",
        "status": "ingested" if phone else "error",
        "block_reason": "" if phone else "invalid_phone",
        "job_id": "",
        "score": None,
        "ingested_ts": time.time(),
        "gated_ts": None,
        "enqueued_ts": None,
    }


# ===========================================================================
# INGEST — normalize -> persist -> gate -> (dry-run) enqueue.
# ===========================================================================
def ingest(tenant_id: str, source: str, raw: dict, *,
           channel: str = "voice", now_epoch: Optional[float] = None) -> dict:
    """The single ingest entry. Returns the lead record stamped with its gate verdict + enqueue state.

    Flow: normalize -> server-mint lead_id -> persist to the tenant's leads_ads file ->
    compliance.pre_dial_gate -> if PASS enqueue (or DRY-RUN log if 140-series not enabled). NEVER
    raises into the caller — an internal error stamps status=error and returns the record.
    """
    try:
        if not tenant_id:
            return {"ok": False, "error": "no_tenant"}
        lead = normalize(source, raw or {})
        lead["tenant_id"] = str(tenant_id)
        # Persist the normalized lead (tenant-scoped, server-stamped) BEFORE gating so the audit
        # trail records every ingest even if the gate denies (compliance audit requirement).
        try:
            store.append_tenant_row(tenant_id, "leads_ads", lead)
        except Exception:  # noqa: BLE001 — persistence failure must not crash the webhook
            _log.warning("leads.ingest: persist failed for %s", lead.get("lead_id"))

        if lead["status"] == "error":
            return lead  # invalid phone etc. — never gate/dial a malformed lead.

        decision = compliance.pre_dial_gate(tenant_id, lead, channel=channel, now_epoch=now_epoch)
        lead["gated_ts"] = float(now_epoch if now_epoch is not None else time.time())
        lead["gate"] = decision.to_dict()
        if not decision.allow:
            lead["status"] = _block_status(decision.reason)
            lead["block_reason"] = decision.reason
            _persist_update(tenant_id, lead)
            return lead

        # PASS -> compute force_window structurally (quiet-hours + verified DCA voice consent) and
        # enqueue (or DRY-RUN). NEVER a literal True (redteam C2/M1).
        force_window = compliance.compute_force_window(decision, now_epoch=now_epoch)
        enq = enqueue_call(tenant_id, lead, force_window=force_window)
        lead.update(enq)
        _persist_update(tenant_id, lead)
        return lead
    except Exception as exc:  # noqa: BLE001 — ingest NEVER raises into the webhook/route
        _log.warning("leads.ingest failed: %r", type(exc).__name__)
        return {"ok": False, "error": "ingest_error"}


def _block_status(reason: str) -> str:
    return {
        "no_dpdp_consent": "blocked_no_consent",
        "no_dca_consent": "blocked_no_consent",
        "dca_not_dlt_backed_for_voice": "blocked_no_consent",
        "cooloff_90d": "blocked_cooloff",
        "ncpr_full_dnd": "blocked_dnd",
        "ncpr_realestate_cat": "blocked_realestate_cat",
        "ncpr_unavailable": "blocked_ncpr_unavailable",
    }.get(reason, "blocked")


def _persist_update(tenant_id: str, lead: dict) -> None:
    """Rewrite the lead row in the tenant's leads_ads file (find by lead_id). Best-effort."""
    try:
        rows = store.get_tenant_file(tenant_id, "leads_ads")
        out = [lead if r.get("lead_id") == lead.get("lead_id") else r for r in rows]
        if not any(r.get("lead_id") == lead.get("lead_id") for r in rows):
            out.append(lead)
        store.put_tenant_file(tenant_id, "leads_ads", out)
    except Exception:  # noqa: BLE001
        _log.warning("leads._persist_update failed for %s", lead.get("lead_id"))


# ===========================================================================
# BULK IMPORT — Dead-Lead Revival: a vendor uploads its OWN consented leads under a DPA.
#
# This is the SINGLE place the import logic lives. The /ads/leads/import endpoint delegates here so
# the gate + dry-run enqueue are NEVER duplicated in the route. For each row we:
#   1. record the asserted consent in the per-tenant hash-chained consent ledger (DPDP always; DCA
#      only when a DLT/OTP method is supplied — a bare checkbox DCA will NOT pass the voice gate),
#   2. funnel through the SAME ingest() path -> compliance.pre_dial_gate -> dry-run enqueue_call.
# A no-consent row is gated OUT by ingest() (status=blocked_*, no enqueue). No real dial fires until
# the 140-series flag (enqueue stays dry-run). The DPA acknowledgement is enforced by the CALLER
# (the endpoint REJECTS the whole import when dpa_acknowledged is false) — this fn assumes the DPA
# gate already passed and records dpa_ref as the consent evidence.
# ===========================================================================
def bulk_import(tenant_id: str, rows: list, *, dpa_ref: str = "",
                channel: str = "voice", now_epoch: Optional[float] = None,
                dpa_acknowledged: bool = False, max_rows: int = 5000) -> dict:
    """Import a list of vendor-consented leads. Returns {ok, ingested, blocked, leads:[...]}.

    `rows` items: {name, phone, source?, consent:{dpdp:bool, dca_method?, dlt_consent_id?}}. For each
    row we record the asserted DPDP (and, when DLT-backed, DCA) consent into the immutable ledger,
    then ingest() runs the fail-closed gate + dry-run enqueue (source=ad, ads_source=revival/<src>).
    A row whose consent does not satisfy the gate is COUNTED as blocked and NOT enqueued. Never
    raises into the route — a row error is skipped (best-effort), the batch continues.

    `dpa_acknowledged`: when the caller (route) confirmed a signed DPA covers the whole batch, the
    DPA IS the per-row DPDP processing basis — so a row that omits an explicit consent.dpdp inherits
    DPDP from the batch DPA. DCA is NEVER inherited: a promo voice dial still needs a DLT-backed DCA
    per row, so a DPA-only lead is still gated OUT for voice (fail-closed) until a DLT id is supplied.
    """
    ingested, blocked = 0, 0
    out_leads: list = []
    for r in (rows or [])[:max_rows]:
        if not isinstance(r, dict):
            continue
        phone_raw = str(r.get("phone") or r.get("phone_number") or "")
        phone = _normalize_phone(phone_raw)
        who = str(r.get("name") or phone or phone_raw)
        src_label = str(r.get("source") or "revival")
        consent = r.get("consent") if isinstance(r.get("consent"), dict) else {}
        # The batch DPA is the per-row DPDP processing basis: a row without an explicit consent.dpdp
        # inherits DPDP from the acknowledged DPA. DCA is NOT inherited (see fn docstring).
        dpdp_ok = bool(consent.get("dpdp", False)) or bool(dpa_acknowledged)
        # Record the asserted consent BEFORE gating (ledger is the audit trail). DPDP from the DPDP
        # flag; DCA only when a DLT/OTP-backed method + id is present (a checkbox DCA never satisfies
        # the voice gate, so we DON'T forge a DLT row — the gate then fail-closes that lead out).
        if phone:
            try:
                if dpdp_ok:
                    compliance.record_consent(
                        tenant_id, lead_id="", phone=phone, kind=compliance.KIND_DPDP,
                        who=who, source="bulk_import_dpa",
                        method=compliance.METHOD_FORM_CHECKBOX,
                        evidence={"dpa_ref": dpa_ref}, now_epoch=now_epoch)
                dlt_id = str(consent.get("dlt_consent_id") or "")
                dca_method = str(consent.get("dca_method") or "")
                # Only a DLT/OTP-backed DCA is valid for promo voice (compliance C4). A checkbox/other
                # method is recorded as-is (it will be gated out for voice) — we never upgrade it.
                if dca_method == compliance.METHOD_OTP_127_DLT and dlt_id:
                    compliance.record_consent(
                        tenant_id, lead_id="", phone=phone, kind=compliance.KIND_DCA,
                        who=who, source="bulk_import_dpa",
                        method=compliance.METHOD_OTP_127_DLT,
                        evidence={"dpa_ref": dpa_ref, "dlt_consent_id": dlt_id},
                        now_epoch=now_epoch)
                elif dca_method:
                    compliance.record_consent(
                        tenant_id, lead_id="", phone=phone, kind=compliance.KIND_DCA,
                        who=who, source="bulk_import_dpa", method=dca_method,
                        evidence={"dpa_ref": dpa_ref}, now_epoch=now_epoch)
            except Exception:  # noqa: BLE001 — a consent-write error never aborts the batch
                _log.warning("bulk_import: consent record failed for a row")
        # Funnel through the SAME ingest path (normalize -> gate -> dry-run enqueue). The bulk source
        # is tagged so the retry engine skips it; src_label rides in source_ref for attribution.
        lead = ingest(tenant_id, SOURCE_BULK,
                      {"name": r.get("name", ""), "phone": phone_raw,
                       "email": r.get("email", ""),
                       "source_ref": {"dpa_ref": dpa_ref, "revival_source": src_label}},
                      channel=channel, now_epoch=now_epoch)
        # Count as ingested ONLY on a positive enqueue verdict (dry_run today / enqueued once 140 is
        # live). Anything else — a blocked_* gate deny, status=error, or an ingest internal-error
        # record ({"ok": False, "error": ...} with NO status key) — is counted as blocked, never as
        # a success (an errored lead must never be reported as imported).
        status = str(lead.get("status", ""))
        if status in ("dry_run", "enqueued"):
            ingested += 1
        else:
            blocked += 1
        out_leads.append({"lead_id": lead.get("lead_id", ""), "status": status or "error",
                          "block_reason": lead.get("block_reason", "") or lead.get("error", "")})
    return {"ok": True, "ingested": ingested, "blocked": blocked, "leads": out_leads}


# ===========================================================================
# ENQUEUE (lead->call) — ADDITIVE replica of caller.py:5754-5768 via INJECTED seams.
# ===========================================================================
def enqueue_call(tenant_id: str, lead: dict, *, force_window: bool = False) -> dict:
    """Build the SAME JOBS row + create_task(run_job) as caller.py:5754-5768 — via injected seams.

    redteam earner-safety C2: uses seams().jobs / seams().run_job / seams().tenant_by_id — NEVER
    `from caller import`. M2: applies the SAME tenant clamps as caller.py:5752 (concurrency =
    max(1,min(1,20,tenant.max_concurrency)); hourly/daily from the tenant rec, never hardcoded).
    Tags source=ad + ads_source so the retry engine structurally skips re-dialing (matching guard).

    DRY-RUN UNTIL 140-SERIES (M1): if telephony_140_enabled() is False, NO job is written + NO task
    is created — we LOG the would-dial + the verdict and return status=dry_run. Real dialing stays
    disabled until the 140-series flag is confirmed (a HUMAN_TASK).
    """
    s = seams()
    tenant = {}
    try:
        if s.tenant_by_id is not None:
            tenant = s.tenant_by_id(tenant_id) or {}
    except Exception:  # noqa: BLE001
        tenant = {}

    # SAME clamps as caller.py:5752 — concurrency clamped to the tenant ceiling; caps from the rec.
    max_conc = int(tenant.get("max_concurrency", 3) or 3)
    concurrency = max(1, min(1, 20, max_conc))   # one ad-lead => one instant call, clamped.
    daily_cap = max(1, int(tenant.get("daily_call_cap", 500) or 500))
    hourly_cap = max(1, min(200, daily_cap))     # never above the tenant's daily ceiling.

    job_id = uuid.uuid4().hex[:10]
    job_row = {
        "state": "queued",
        "campaign_id": str(lead.get("campaign_id") or ""),
        "tenant_id": str(tenant_id),               # token-derived; NEVER body/query.
        "concurrency": concurrency,
        "hourly_cap": hourly_cap,
        "daily_cap": daily_cap,
        "force_window": bool(force_window),        # COMPUTED by compliance (quiet-hours), never literal True.
        "leads": [{
            "name": lead.get("name", ""),
            "num": lead.get("phone", ""),          # E.164 +91…
            "status": "queued", "room": "",
            "launched_at": 0.0, "attempt": 0,
        }],
        # ── ad-source provenance: the retry engine reads these to SKIP re-dialing an ad-lead
        # without re-passing the consent gate (redteam compliance C1). run_job stamps source=ad
        # onto the CALLS row; the reconcile sweep then skips retry-enqueue for ad-source calls.
        "source": "ad",
        "ads_source": lead.get("source", ""),
        "ads_lead_id": lead.get("lead_id", ""),
    }

    # DRY-RUN UNTIL 140-SERIES — log the would-dial + verdict, but do NOT place a call.
    if not telephony_140_enabled():
        _log.info("ads dry-run (140-series disabled): would-dial lead=%s tenant=%s force_window=%s",
                  lead.get("lead_id"), tenant_id, force_window)
        try:
            store.append_tenant_row(tenant_id, "ads_audit", {
                "event": "dial.dry_run", "lead_id": lead.get("lead_id"),
                "job_preview_id": job_id, "force_window": bool(force_window),
                "concurrency": concurrency, "hourly_cap": hourly_cap, "daily_cap": daily_cap,
                "ts": time.time(),
            })
        except Exception:  # noqa: BLE001
            pass
        return {"status": "dry_run", "job_id": "", "dry_run": True,
                "would_dial": True, "force_window": bool(force_window)}

    # LIVE path (only when 140-series is confirmed): write the JOBS row + create_task(run_job).
    jobs = s.jobs
    run_job = s.run_job
    if jobs is None or run_job is None:
        _log.warning("ads enqueue: jobs/run_job seam not wired — cannot dial (degraded)")
        return {"status": "error", "job_id": "", "error": "enqueue_seam_unavailable"}
    try:
        jobs[job_id] = job_row
        import asyncio
        asyncio.create_task(run_job(job_id))
    except Exception as exc:  # noqa: BLE001 — never raise into the route
        _log.warning("ads enqueue failed: %r", type(exc).__name__)
        return {"status": "error", "job_id": "", "error": "enqueue_failed"}
    try:
        store.append_tenant_row(tenant_id, "ads_audit", {
            "event": "dial.enqueued", "lead_id": lead.get("lead_id"), "job_id": job_id,
            "force_window": bool(force_window), "ts": time.time(),
        })
    except Exception:  # noqa: BLE001
        pass
    return {"status": "enqueued", "job_id": job_id, "dry_run": False,
            "force_window": bool(force_window)}
