"""comm.send_log — write one row per outbound message into comm_send_log (RLS-scoped).

Spec: communication/COMMUNICATION-MASTER-PLAN.md §3.1 (comm_send_log: every outbound, every
channel; cost_minor BIGINT paise; idempotency_key UNIQUE = comms:{message_id}; outcome CAPI
col day-1) + db/ddl_comm.sql (the table is LIVE on the box).

WHAT THIS DOES:
  * `new_message_id()`   -> a fresh "cms_<uuid4hex>" id (the send_log PK + the idem_key seed).
  * `record_send(...)`   -> INSERT one comm_send_log row under the tenant GUC. Idempotent on
    (tenant_id, idempotency_key): a retried create_task that reuses the same idem_key writes
    NOTHING the second time (ON CONFLICT DO NOTHING) — exactly-once logging.

RLS / EARNER LAW:
  * the write runs inside db.engine.session(tenant_id=..., is_admin=False) — the GUC binds the
    row to the tenant; cross-tenant is impossible at the DB layer (FORCE-RLS).
  * NEVER raises into the caller — a log-write failure (PG down) degrades to a False return; the
    send already happened, the log is best-effort durability. (The detached post-call task must
    never crash on a log failure.)
  * the body_preview is truncated to ~280 chars (audit, never the full PII blob); we NEVER store
    a token or a full media blob.
  * db.engine is imported lazily; on a local build box (no PG) every call degrades to False.
"""
from __future__ import annotations

import logging
import uuid
from typing import Optional

_log = logging.getLogger("comm.send_log")


def new_message_id() -> str:
    """A fresh send_log PK (also the idempotency_key seed: comms:{message_id})."""
    return f"cms_{uuid.uuid4().hex}"


def idem_key_for(message_id: str) -> str:
    """The canonical per-message idempotency key (the plan's comms:{message_id})."""
    return f"comms:{message_id}"


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


# The explicit column projection — kept in sync with db/ddl_comm.sql comm_send_log.
_INSERT_SQL = (
    "INSERT INTO comm_send_log "
    "  (message_id, tenant_id, session_id, channel, provider_def_id, direction, kind, purpose, "
    "   to_ref, body_preview, media_ref, cost_minor, wallet_txn_id, idempotency_key, status, "
    "   external_id, error_code, outcome) "
    "VALUES "
    "  (:message_id, :tenant_id, :session_id, :channel, :provider_def_id, :direction, :kind, "
    "   :purpose, :to_ref, :body_preview, :media_ref, :cost_minor, :wallet_txn_id, "
    "   :idempotency_key, :status, :external_id, :error_code, :outcome) "
    "ON CONFLICT (tenant_id, idempotency_key) DO NOTHING "
    "RETURNING message_id"
)


def record_send(
    tenant_id: str,
    *,
    message_id: str,
    channel: str = "telegram",
    status: str = "sent",
    to_ref: str = "",
    kind: str = "text",
    purpose: str = "service",
    body_preview: str = "",
    provider_def_id: str = "",
    session_id: str = "",
    media_ref: str = "",
    cost_minor: int = 0,
    wallet_txn_id: str = "",
    external_id: str = "",
    error_code: str = "",
    outcome: str = "",
    direction: str = "outbound",
    idempotency_key: str = "",
) -> bool:
    """INSERT one comm_send_log row (idempotent on (tenant, idem_key)). Returns True iff a row
    was written (False on conflict/duplicate OR on any failure). NEVER raises."""
    if not available() or not tenant_id or not message_id:
        return False
    eng = _engine()
    params = {
        "message_id": message_id,
        "tenant_id": tenant_id,
        "session_id": session_id or "",
        "channel": channel or "telegram",
        "provider_def_id": provider_def_id or "",
        "direction": direction or "outbound",
        "kind": kind or "text",
        "purpose": purpose or "service",
        "to_ref": to_ref or "",
        "body_preview": (body_preview or "")[:280],
        "media_ref": (media_ref or "")[:300],
        "cost_minor": int(cost_minor or 0),
        "wallet_txn_id": (wallet_txn_id or "")[:80],
        "idempotency_key": idempotency_key or idem_key_for(message_id),
        "status": (status or "sent")[:40],
        "external_id": (external_id or "")[:120],
        "error_code": (error_code or "")[:160],
        "outcome": (outcome or "")[:60],
    }
    try:
        from sqlalchemy import text
        with eng.session(tenant_id=tenant_id, is_admin=False) as s:  # type: ignore
            res = s.execute(text(_INSERT_SQL), params)
            row = res.fetchone()
            return row is not None
    except Exception as exc:  # noqa: BLE001 — best-effort durability; never crash the detached task
        _log.warning("comm.send_log.record_send failed: %r", type(exc).__name__)
        return False
