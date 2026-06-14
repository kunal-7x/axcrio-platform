"""comm.consent — write one APPEND-ONLY consent artifact into comm_consent_log (RLS-scoped).

Spec: communication/COMMUNICATION-MASTER-PLAN.md §5 (the canonical `(channel × purpose)`
consent model) + §3.1 (comm_consent_log is append-only: REVOKE UPDATE/DELETE + a BEFORE
UPDATE/DELETE RAISE trigger). The table is LIVE on the box (db/ddl_comm.sql §97-110).

WHY THIS EXISTS (the legal gate on the founder's flagship post-call auto-summary):
  Per §5.3 — the post-call auto-message to the contact records a consent artifact at finalize
  time, BEFORE the first contact-facing send. The post-call summary is the SERVICE-IMPLICIT
  lane (a contact who just had a phone call with the tenant about an enquiry; basis derived
  from lead_source per §5.2) — the only lane that legally auto-fires. This module writes that
  artifact (basis + wording + timestamp + the call provenance) so the send is defensible.

WHAT THIS DOES:
  * `new_consent_id()`     -> a fresh "cco_<uuid4hex>" id.
  * `derive_basis(...)`    -> the consent_basis derived from lead_source (NEVER a constant).
  * `record_consent(...)`  -> INSERT one comm_consent_log row under the tenant GUC.

EARNER / RLS LAW (mirrors send_log.py exactly):
  * the write runs inside db.engine.session(tenant_id=..., is_admin=False) — the GUC binds the
    row to the tenant; cross-tenant is impossible at the DB layer (FORCE-RLS).
  * NEVER raises into the caller — a write failure (PG down, append-only trigger) degrades to a
    False return. The detached post-call task must never crash on a consent-write failure.
  * db.engine is imported lazily; on a local build box (no PG) every call degrades to False.
  * this is INSERT-only (the table forbids UPDATE/DELETE by design) — exactly the append-only
    artifact the compliance model wants.
"""
from __future__ import annotations

import logging
import uuid

_log = logging.getLogger("comm.consent")


def new_consent_id() -> str:
    """A fresh comm_consent_log PK."""
    return f"cco_{uuid.uuid4().hex}"


def derive_basis(lead_source: str = "", *, default: str = "prior_transaction") -> str:
    """Derive consent_basis from lead_source (§5.2 — NEVER a constant).

    Inbound-form / the tenant's own customer / a prior transaction -> service-implicit is
    defensible. Purchased/scraped lists -> promotional, explicit opt-in required (those never
    auto-fire in W1 — only the service-implicit post-call lane does). This is a conservative
    classifier; the tenant attests per-list ownership separately (the audit artifact)."""
    ls = (lead_source or "").strip().lower()
    if not ls:
        return default
    if any(k in ls for k in ("purchase", "scrape", "bought", "third_party", "thirdparty", "list_buy")):
        return "purchased_optin"          # promotional — does NOT auto-fire in W1
    if any(k in ls for k in ("inbound", "form", "website", "web", "landing", "enquiry", "inquiry")):
        return "inbound_form"
    if any(k in ls for k in ("call", "phone", "ivr", "voice")):
        return "prior_transaction"
    if any(k in ls for k in ("customer", "existing", "crm", "import_owned", "owned")):
        return "prior_transaction"
    return default


def _engine():
    try:
        from db import engine  # type: ignore
        return engine
    except Exception:  # noqa: BLE001
        return None


def available() -> bool:
    eng = _engine()
    try:
        return bool(eng and eng.available())
    except Exception:  # noqa: BLE001
        return False


# The explicit column projection — kept in sync with db/ddl_comm.sql comm_consent_log.
_INSERT_SQL = (
    "INSERT INTO comm_consent_log "
    "  (consent_id, tenant_id, contact_ref, channel, purpose, action, consent_basis, "
    "   lead_source, wording, captured_by, call_id) "
    "VALUES "
    "  (:consent_id, :tenant_id, :contact_ref, :channel, :purpose, :action, :consent_basis, "
    "   :lead_source, :wording, :captured_by, :call_id) "
    "RETURNING consent_id"
)


def record_consent(
    tenant_id: str,
    *,
    contact_ref: str,
    channel: str = "telegram",
    purpose: str = "service",
    action: str = "grant",
    consent_basis: str = "",
    lead_source: str = "",
    wording: str = "",
    captured_by: str = "system",
    call_id: str = "",
) -> bool:
    """INSERT one append-only comm_consent_log row. Returns True iff a row was written
    (False on any failure). NEVER raises. `consent_basis` is derived from `lead_source`
    when not supplied (§5.2)."""
    if not available() or not tenant_id or not contact_ref:
        return False
    basis = (consent_basis or "").strip() or derive_basis(lead_source)
    eng = _engine()
    params = {
        "consent_id": new_consent_id(),
        "tenant_id": tenant_id,
        "contact_ref": (contact_ref or "")[:200],
        "channel": (channel or "telegram")[:40],
        "purpose": (purpose or "service")[:40],
        "action": (action or "grant")[:20],
        "consent_basis": (basis or "")[:60],
        "lead_source": (lead_source or "")[:120],
        "wording": (wording or "")[:400],
        "captured_by": (captured_by or "system")[:40],
        "call_id": (call_id or "")[:80],
    }
    try:
        from sqlalchemy import text
        with eng.session(tenant_id=tenant_id, is_admin=False) as s:  # type: ignore
            res = s.execute(text(_INSERT_SQL), params)
            return res.fetchone() is not None
    except Exception as exc:  # noqa: BLE001 — best-effort artifact; never crash the detached task
        _log.warning("comm.consent.record_consent failed: %r", type(exc).__name__)
        return False
