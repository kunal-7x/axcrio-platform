"""comm.sessions — read + upsert comm_sessions (the LLM-brain rolling window), RLS-scoped.

Spec: communication/COMMUNICATION-MASTER-PLAN.md §3.1 (comm_sessions: one session per
(tenant, channel, external_chat_id, provider_def_id); rolling last-20-turn JSONB window;
seeded post-call; UNIQUE no-shared-bot-across-tenants S4) + db/ddl_comm.sql (the table is
LIVE on the box) + WAVE 2 (the brain reads this; W1 only seeds + the inbound webhook appends).

WHAT THIS DOES (W1 surface — the webhook + the sessions API consume it):
  * `new_session_id()`          -> a fresh "cse_<uuid4hex>" id.
  * `get_or_create(...)`        -> resolve the (tenant, channel, chat_id, provider_def) session
    row; create it if absent (UNIQUE upsert). Returns the session_id (or None on failure).
  * `append_turn(...)`          -> append one {role,text,at} turn to the rolling window (trim to
    the last 20), bump last_message_at/updated_at. Idempotency is the WEBHOOK's job (update_id);
    this is the storage primitive.
  * `list_sessions(...)`        -> keyset/ordered list for the GET /comm/sessions page.
  * `get_session(...)`          -> one full session (turns + seeds) for GET /comm/sessions/{id}.

RLS / EARNER LAW (mirrors comm/send_log.py + provider_registry/store.py):
  * every read/write runs inside db.engine.session(tenant_id=..., is_admin=...) — the GUC binds
    the row to the tenant; cross-tenant is impossible at the DB layer (FORCE-RLS).
  * NEVER raises into the caller — a failure (PG down / no row) degrades to None/[]/False.
  * db.engine is imported lazily; on a local build box (no PG) every call degrades safely.
  * the turn TEXT is truncated (audit hygiene); we NEVER store a token or a full media blob.
"""
from __future__ import annotations

import json
import logging
import uuid
from typing import Any, Dict, List, Optional

_log = logging.getLogger("comm.sessions")

_MAX_TURNS = 20            # the rolling window (plan §3.1)
_TURN_TEXT_CAP = 2000      # per-turn text cap (audit hygiene; not a token / media blob)


def new_session_id() -> str:
    """A fresh comm_sessions PK."""
    return f"cse_{uuid.uuid4().hex}"


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


# The explicit column projection — kept in sync with db/ddl_comm.sql comm_sessions.
_SESSION_COLS = (
    "session_id, tenant_id, channel, external_chat_id, provider_def_id, contact_phone, "
    "lead_id, call_id, agent_persona, turns, call_summary, next_action, outcome, interest, "
    "status, last_message_at, created_at, updated_at"
)


# ---------------------------------------------------------------------------
# resolve / create
# ---------------------------------------------------------------------------
def get_or_create(
    tenant_id: str,
    *,
    channel: str = "telegram",
    external_chat_id: str = "",
    provider_def_id: str = "",
    contact_phone: str = "",
    lead_id: str = "",
    call_id: str = "",
    agent_persona: str = "Riya",
    is_admin: bool = False,
) -> Optional[str]:
    """Return the session_id for (tenant, channel, external_chat_id, provider_def_id), creating
    it if absent. Idempotent via the table UNIQUE constraint (ON CONFLICT DO NOTHING then SELECT).
    Returns the session_id, or None on any failure. NEVER raises."""
    if not available() or not tenant_id:
        return None
    eng = _engine()
    new_id = new_session_id()
    try:
        from sqlalchemy import text
        with eng.session(tenant_id=tenant_id, is_admin=is_admin) as s:  # type: ignore
            s.execute(text(
                "INSERT INTO comm_sessions "
                "  (session_id, tenant_id, channel, external_chat_id, provider_def_id, "
                "   contact_phone, lead_id, call_id, agent_persona, last_message_at) "
                "VALUES "
                "  (:sid, :tid, :ch, :cid, :pdid, :phone, :lead, :call, :persona, now()) "
                "ON CONFLICT (tenant_id, channel, external_chat_id, provider_def_id) DO NOTHING"
            ), {
                "sid": new_id, "tid": tenant_id, "ch": channel or "telegram",
                "cid": external_chat_id or "", "pdid": provider_def_id or "",
                "phone": contact_phone or "", "lead": lead_id or "", "call": call_id or "",
                "persona": agent_persona or "Riya",
            })
            row = s.execute(text(
                "SELECT session_id FROM comm_sessions "
                "WHERE tenant_id = :tid AND channel = :ch AND external_chat_id = :cid "
                "AND provider_def_id = :pdid LIMIT 1"
            ), {"tid": tenant_id, "ch": channel or "telegram",
                "cid": external_chat_id or "", "pdid": provider_def_id or ""}).fetchone()
            return str(row[0]) if row else None
    except Exception as exc:  # noqa: BLE001
        _log.warning("comm.sessions.get_or_create failed: %r", type(exc).__name__)
        return None


def append_turn(
    tenant_id: str,
    session_id: str,
    *,
    role: str = "user",
    text_body: str = "",
    is_admin: bool = False,
) -> bool:
    """Append one {role,text,at} turn to the session's rolling window (trim to the last 20),
    bump last_message_at + updated_at. Returns True iff a row was updated. NEVER raises.

    NOTE: idempotency (a Telegram retry re-delivering the same update_id) is the WEBHOOK's
    responsibility — this primitive blindly appends. The webhook gates on update_id first."""
    if not available() or not tenant_id or not session_id:
        return False
    eng = _engine()
    turn = {"role": (role or "user")[:16], "text": (text_body or "")[:_TURN_TEXT_CAP]}
    try:
        from sqlalchemy import text
        with eng.session(tenant_id=tenant_id, is_admin=is_admin) as s:  # type: ignore
            # append + trim to last _MAX_TURNS, server-side (jsonb), single statement.
            res = s.execute(text(
                "UPDATE comm_sessions SET "
                "  turns = ( "
                "    SELECT COALESCE(jsonb_agg(elem ORDER BY ord), '[]'::jsonb) FROM ( "
                "      SELECT elem, ord FROM ( "
                "        SELECT elem, row_number() OVER () AS ord "
                "        FROM jsonb_array_elements( "
                "          (turns || jsonb_build_array( "
                "             jsonb_build_object('role', :role, 'text', :body, "
                "                                'at', to_char(now(),'YYYY-MM-DD\"T\"HH24:MI:SSOF')) )) "
                "        ) AS elem "
                "      ) AS numbered "
                "      ORDER BY ord DESC LIMIT :maxn "
                "    ) AS trimmed "
                "  ), "
                "  last_message_at = now(), updated_at = now() "
                "WHERE session_id = :sid AND tenant_id = :tid"
            ), {"role": (role or "user")[:16], "body": turn["text"],
                "maxn": _MAX_TURNS, "sid": session_id, "tid": tenant_id})
            return (res.rowcount or 0) > 0
    except Exception as exc:  # noqa: BLE001
        _log.warning("comm.sessions.append_turn failed: %r", type(exc).__name__)
        return False


# ---------------------------------------------------------------------------
# reads (the GET /comm/sessions API)
# ---------------------------------------------------------------------------
def _rows(tenant_id: str, sql: str, params: dict, *, is_admin: bool) -> List[dict]:
    if not available():
        return []
    eng = _engine()
    try:
        from sqlalchemy import text
        with eng.session(tenant_id=tenant_id, is_admin=is_admin) as s:  # type: ignore
            res = s.execute(text(sql), params)
            cols = list(res.keys())
            return [dict(zip(cols, row)) for row in res.fetchall()]
    except Exception as exc:  # noqa: BLE001
        _log.warning("comm.sessions._rows failed: %r", type(exc).__name__)
        return []


def _shape(row: dict) -> dict:
    """JSON-able shape for the API (turns coerced to a list; timestamps to iso str)."""
    out = dict(row or {})
    turns = out.get("turns")
    if isinstance(turns, str):
        try:
            turns = json.loads(turns)
        except Exception:  # noqa: BLE001
            turns = []
    if not isinstance(turns, list):
        turns = []
    out["turns"] = turns
    for k in ("last_message_at", "created_at", "updated_at"):
        v = out.get(k)
        if v is not None and not isinstance(v, str):
            out[k] = str(v)
    return out


def list_sessions(
    tenant_id: str,
    *,
    channel: str = "",
    status: str = "",
    limit: int = 50,
    offset: int = 0,
    is_admin: bool = False,
) -> List[dict]:
    """List sessions for the tenant (newest activity first), optionally filtered by channel/status.
    Turns are omitted from the LIST projection (cheap); the detail endpoint returns them."""
    where = ["tenant_id = :tid"]
    params: Dict[str, Any] = {"tid": tenant_id or "",
                              "lim": max(1, min(int(limit or 50), 200)),
                              "off": max(0, int(offset or 0))}
    if channel:
        where.append("channel = :ch"); params["ch"] = channel
    if status:
        where.append("status = :st"); params["st"] = status
    sql = (
        "SELECT session_id, tenant_id, channel, external_chat_id, provider_def_id, "
        "       contact_phone, lead_id, call_id, agent_persona, call_summary, next_action, "
        "       outcome, interest, status, last_message_at, created_at, updated_at, "
        "       jsonb_array_length(turns) AS turn_count "
        f"FROM comm_sessions WHERE {' AND '.join(where)} "
        "ORDER BY last_message_at DESC NULLS LAST, created_at DESC "
        "LIMIT :lim OFFSET :off"
    )
    rows = _rows(tenant_id, sql, params, is_admin=is_admin)
    out = []
    for r in rows:
        d = dict(r)
        for k in ("last_message_at", "created_at", "updated_at"):
            if d.get(k) is not None and not isinstance(d[k], str):
                d[k] = str(d[k])
        out.append(d)
    return out


def get_session(tenant_id: str, session_id: str, *, is_admin: bool = False) -> Optional[dict]:
    """One full session (turns + post-call seeds). RLS-scoped: a tenant can only read its own.
    Returns the JSON-able dict or None. NEVER raises."""
    if not session_id:
        return None
    sql = (f"SELECT {_SESSION_COLS} FROM comm_sessions "
           "WHERE session_id = :sid AND tenant_id = :tid LIMIT 1")
    rows = _rows(tenant_id, sql, {"sid": session_id, "tid": tenant_id or ""}, is_admin=is_admin)
    return _shape(rows[0]) if rows else None


# ---------------------------------------------------------------------------
# founder chat_id persistence (W1-P3) — the hot-lead-alert destination.
#
# Telegram getUpdates only retains ~24h of updates and drops confirmed ones, so a chat_id
# derived once from getUpdates ages out. We persist the derived founder chat_id as a SENTINEL
# comm_sessions row (call_id=_FOUNDER_SENTINEL) so the alert destination survives — RLS-scoped,
# tenant-private, reusing the live table (zero schema change). NEVER raises.
# ---------------------------------------------------------------------------
_FOUNDER_SENTINEL = "__founder_chat__"


def set_founder_chat_id(
    tenant_id: str,
    chat_id: str,
    *,
    provider_def_id: str = "",
    channel: str = "telegram",
    is_admin: bool = False,
) -> bool:
    """Persist the tenant's founder chat_id (the hot-lead-alert destination) as a sentinel
    comm_sessions row. Idempotent on the UNIQUE (tenant, channel, external_chat_id, provider_def).
    Returns True on a successful write. NEVER raises."""
    if not available() or not tenant_id or not (chat_id or "").strip():
        return False
    eng = _engine()
    try:
        from sqlalchemy import text
        with eng.session(tenant_id=tenant_id, is_admin=is_admin) as s:  # type: ignore
            s.execute(text(
                "INSERT INTO comm_sessions "
                "  (session_id, tenant_id, channel, external_chat_id, provider_def_id, "
                "   call_id, agent_persona, status, last_message_at) "
                "VALUES (:sid, :tid, :ch, :cid, :pdid, :sentinel, 'Riya', 'founder', now()) "
                "ON CONFLICT (tenant_id, channel, external_chat_id, provider_def_id) "
                "DO UPDATE SET call_id = :sentinel, status = 'founder', updated_at = now()"
            ), {
                "sid": new_session_id(), "tid": tenant_id, "ch": channel or "telegram",
                "cid": (chat_id or "").strip(), "pdid": provider_def_id or "",
                "sentinel": _FOUNDER_SENTINEL,
            })
            return True
    except Exception as exc:  # noqa: BLE001
        _log.warning("comm.sessions.set_founder_chat_id failed: %r", type(exc).__name__)
        return False


def get_founder_chat_id(
    tenant_id: str,
    *,
    provider_def_id: str = "",
    channel: str = "telegram",
    is_admin: bool = False,
) -> str:
    """Read the persisted founder chat_id for this tenant's bot (the hot-lead-alert destination).

    STRICT: returns ONLY the explicitly-marked sentinel row (call_id=_FOUNDER_SENTINEL, written
    by set_founder_chat_id when the chat_id is derived from getUpdates after the founder taps
    Start). We deliberately do NOT fall back to 'the most recent inbound session' — that could
    be any contact's chat_id and would mis-route a hot-lead alert to a customer. Returns '' when
    no founder chat is confirmed. NEVER raises."""
    if not available() or not tenant_id:
        return ""
    where = ["tenant_id = :tid", "channel = :ch", "external_chat_id <> ''",
             "call_id = :sentinel"]
    params: Dict[str, Any] = {"tid": tenant_id, "ch": channel or "telegram",
                              "sentinel": _FOUNDER_SENTINEL}
    if provider_def_id:
        where.append("provider_def_id = :pdid"); params["pdid"] = provider_def_id
    sql = (
        "SELECT external_chat_id FROM comm_sessions "
        f"WHERE {' AND '.join(where)} "
        "ORDER BY updated_at DESC NULLS LAST, created_at DESC LIMIT 1"
    )
    rows = _rows(tenant_id, sql, params, is_admin=is_admin)
    return str(rows[0].get("external_chat_id", "")) if rows else ""
