"""ai_manager.store — tenant-scoped persistence for the AI-Manager command lifecycle.

House pattern (mirrors grow/store.py + provider_registry/store.py): a dependency-free,
thread-safe InMemory backend that is the DEFAULT and the fully-tested path (CI + every
dormant/key-less box), plus a lazy `_Pg` backend that rides the shared P1 `db.engine`
spine (`from db import engine; engine.available(); engine.session(tenant_id, is_admin)`)
with FORCE-RLS GUCs per txn. This module imports ZERO sqlalchemy at load — the engine
and sqlalchemy.text are imported LAZILY inside the Pg methods, each guarded so ABSENCE
degrades to InMemory and NEVER crashes.

On this box `db.engine` is ABSENT → `available()` is False → InMemory is always used.

Every read/write is `vendor_id`-scoped and FAIL-CLOSED on a blank tenant (returns
`[]`/`None`/no-op). No raw PIN/OTP/secret is ever stored, logged or returned — audit
metadata is scrubbed of secret-shaped keys; authorized-user rows expose `has_pin`
(bool) only, never `pin_hash`. All rows are returned as plain JSON-able dicts
(datetime→iso, Decimal→number).

The 7 ai_manager_* tables (vendor_id-keyed, admin-GUC RLS, audit append-only) are
defined in ai_manager/db/schema.sql; this store is their access layer.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import logging
import threading
import uuid
from typing import Any, Optional

log = logging.getLogger("ai_manager.store")


# =========================================================================== #
# helpers
# =========================================================================== #
def _ok(tenant_id: str) -> bool:
    """A usable tenant scope. Blank → fail-closed everywhere."""
    return bool((tenant_id or "").strip())


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


def _new_id(prefix: str) -> str:
    return f"{prefix}{uuid.uuid4().hex[:12]}"


def _clamp(value: Any, lo: int, hi: int, default: int) -> int:
    try:
        v = int(value)
    except Exception:  # noqa: BLE001
        return default
    return max(lo, min(v, hi))


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:  # noqa: BLE001
        return default


_SECRET_KEYS = {"pin", "otp", "secret", "code", "token", "step_up_token", "password",
                "pin_hash", "api_key"}


def _scrub(obj: Any) -> Any:
    """Recursively mask secret-shaped keys (defense in depth before any persist)."""
    if isinstance(obj, dict):
        return {k: ("***" if str(k).lower() in _SECRET_KEYS else _scrub(v))
                for k, v in obj.items()}
    if isinstance(obj, list):
        return [_scrub(x) for x in obj]
    return obj


def _jsonify(value: Any) -> Any:
    """Make a value JSON-able: datetime→iso, Decimal→number, jsonb-string→object.
    Recurses into dicts/lists. NEVER raises."""
    try:
        import decimal as _dec
        if isinstance(value, dict):
            return {k: _jsonify(v) for k, v in value.items()}
        if isinstance(value, list):
            return [_jsonify(v) for v in value]
        if isinstance(value, (_dt.datetime, _dt.date)):
            return value.isoformat()
        if isinstance(value, _dec.Decimal):
            f = float(value)
            return int(f) if f == int(f) else f
        if isinstance(value, str):
            s = value.strip()
            if s[:1] in ("{", "["):
                try:
                    return json.loads(s)
                except Exception:  # noqa: BLE001
                    return value
            return value
        return value
    except Exception:  # noqa: BLE001
        return value


def _iso_ge(row_ts: str, bound: str) -> bool:
    """row_ts >= bound, string-lexicographic on ISO is monotone; lenient parse."""
    if not bound:
        return True
    return (row_ts or "") >= bound


def _iso_lt(row_ts: str, bound: str) -> bool:
    if not bound:
        return True
    return (row_ts or "") < bound


# the §8 enum buckets (zero-fill targets for dashboard_summary)
_CMD_STATUSES = ("pending", "needs_confirmation", "needs_pin", "executing",
                 "succeeded", "failed", "denied", "cancelled")
_SESSION_STATUSES = ("active", "completed", "failed", "blocked")
_SESSION_CHANNELS = ("phone", "whatsapp", "dashboard")
_RUN_STATUSES = ("queued", "running", "succeeded", "failed", "retried", "cancelled")
_AUDIT_SEVERITIES = ("info", "warn", "error", "critical", "debug")


# =========================================================================== #
# engine resolution — shared db.engine preferred, ai_manager.db.engine fallback
# =========================================================================== #
def _engine():
    """Return a usable engine module (db.engine or ai_manager.db.engine) or None.
    Prefer the SHARED P1 `db.engine` (matches grow/store.py); fall back to the
    package-private `ai_manager.db.engine`. NEVER raises → None when neither is
    importable/available (the dormant local box → InMemory)."""
    try:
        from db import engine as eng  # type: ignore
        if eng.available():
            return eng
    except Exception:  # noqa: BLE001
        pass
    try:
        from .db import engine as eng2  # type: ignore
        if eng2.available():
            return eng2
    except Exception:  # noqa: BLE001
        pass
    return None


def _text(sql: str):
    from sqlalchemy import text
    return text(sql)


# =========================================================================== #
# 1) ai_manager_sessions + ai_manager_session_turns  (InMemory)
# =========================================================================== #
class _InMemSessions:
    def __init__(self):
        self._rows: dict[tuple[str, str], dict] = {}            # (vendor, id) -> session row
        self._turns: dict[tuple[str, str], list[dict]] = {}     # (vendor, session) -> [turn]
        self._lock = threading.RLock()

    def create(self, row: dict) -> None:
        with self._lock:
            key = (row["vendor_id"], row["id"])
            if key not in self._rows:
                self._rows[key] = dict(row)

    def patch(self, tenant_id: str, session_id: str, fields: dict) -> None:
        with self._lock:
            r = self._rows.get((tenant_id, session_id))
            if r is not None:
                r.update(fields)

    def get(self, tenant_id: str, session_id: str) -> Optional[dict]:
        with self._lock:
            r = self._rows.get((tenant_id, session_id))
            return dict(r) if r else None

    def add_turn(self, turn: dict) -> None:
        with self._lock:
            self._turns.setdefault((turn["vendor_id"], turn["session_id"]), []).append(dict(turn))

    def turns(self, tenant_id: str, session_id: str) -> list[dict]:
        with self._lock:
            rows = list(self._turns.get((tenant_id, session_id), []))
        rows.sort(key=lambda t: (_as_int(t.get("seq"), 0), t.get("created_at", "")))
        return [dict(t) for t in rows]

    def scan(self, tenant_id: str) -> list[dict]:
        with self._lock:
            return [dict(r) for (t, _i), r in self._rows.items() if t == tenant_id]


# =========================================================================== #
# 2) ai_manager_commands  (InMemory)
# =========================================================================== #
class _InMemCommands:
    def __init__(self):
        self._rows: dict[tuple[str, str], dict] = {}        # (vendor, id) -> command row
        self._idem: dict[tuple[str, str], str] = {}         # (vendor, idem_key) -> id
        self._lock = threading.RLock()

    def insert(self, row: dict) -> str:
        with self._lock:
            tenant = row["vendor_id"]
            key = (row.get("idempotency_key") or "").strip()
            if key:
                existing = self._idem.get((tenant, key))
                if existing:
                    return existing
            self._rows[(tenant, row["id"])] = dict(row)
            if key:
                self._idem[(tenant, key)] = row["id"]
            return row["id"]

    def patch(self, tenant_id: str, command_id: str, fields: dict) -> None:
        with self._lock:
            r = self._rows.get((tenant_id, command_id))
            if r is not None:
                r.update(fields)
                r["updated_at"] = _now()

    def get(self, tenant_id: str, command_id: str) -> Optional[dict]:
        with self._lock:
            r = self._rows.get((tenant_id, command_id))
            return dict(r) if r else None

    def scan(self, tenant_id: str, *, is_admin: bool = False) -> list[dict]:
        with self._lock:
            if is_admin:
                return [dict(r) for r in self._rows.values()]
            return [dict(r) for (t, _i), r in self._rows.items() if t == tenant_id]


# =========================================================================== #
# 3) ai_manager_audit_logs (append-only) + 4) ai_manager_action_runs  (InMemory)
# =========================================================================== #
class _InMemAudit:
    def __init__(self):
        self._rows: list[dict] = []
        self._lock = threading.RLock()

    def insert(self, row: dict) -> None:
        with self._lock:
            self._rows.append(dict(row))            # INSERT only — never mutate/delete

    def scan(self, tenant_id: str, *, is_admin: bool = False) -> list[dict]:
        with self._lock:
            if is_admin:
                return [dict(r) for r in self._rows]
            return [dict(r) for r in self._rows if r.get("vendor_id") == tenant_id]


class _InMemRuns:
    def __init__(self):
        self._rows: dict[tuple[str, str], dict] = {}
        self._lock = threading.RLock()

    def insert(self, row: dict) -> None:
        with self._lock:
            self._rows[(row["vendor_id"], row["id"])] = dict(row)

    def patch(self, tenant_id: str, run_id: str, fields: dict) -> None:
        with self._lock:
            r = self._rows.get((tenant_id, run_id))
            if r is not None:
                r.update(fields)

    def scan(self, tenant_id: str, *, is_admin: bool = False) -> list[dict]:
        with self._lock:
            if is_admin:
                return [dict(r) for r in self._rows.values()]
            return [dict(r) for (t, _i), r in self._rows.items() if t == tenant_id]


# =========================================================================== #
# 5) ai_manager_profiles + 6) ai_manager_authorized_users  (InMemory)
# =========================================================================== #
class _InMemProfiles:
    def __init__(self):
        self._rows: dict[str, dict] = {}            # vendor -> profile row
        self._lock = threading.RLock()

    def get(self, tenant_id: str) -> Optional[dict]:
        with self._lock:
            r = self._rows.get(tenant_id)
            return dict(r) if r else None

    def upsert(self, tenant_id: str, fields: dict) -> dict:
        with self._lock:
            r = self._rows.get(tenant_id)
            if r is None:
                r = _profile_defaults(tenant_id)
                self._rows[tenant_id] = r
            for k, v in fields.items():
                if k in _PROFILE_WRITABLE:
                    r[k] = v
            r["updated_at"] = _now()
            return dict(r)


class _InMemUsers:
    def __init__(self):
        self._rows: dict[tuple[str, str], dict] = {}    # (vendor, user_row_id) -> row
        self._lock = threading.RLock()

    def insert(self, row: dict) -> None:
        with self._lock:
            self._rows[(row["vendor_id"], row["id"])] = dict(row)

    def get(self, tenant_id: str, user_id: str) -> Optional[dict]:
        with self._lock:
            r = self._rows.get((tenant_id, user_id))
            return dict(r) if r else None

    def patch(self, tenant_id: str, user_id: str, fields: dict) -> Optional[dict]:
        with self._lock:
            r = self._rows.get((tenant_id, user_id))
            if r is None:
                return None
            r.update(fields)
            r["updated_at"] = _now()
            return dict(r)

    def scan(self, tenant_id: str) -> list[dict]:
        with self._lock:
            return [dict(r) for (t, _i), r in self._rows.items() if t == tenant_id]


# ---- profile default shape (zero-filled; mirrors ai_manager_profiles cols) ----
_PROFILE_WRITABLE = {
    "enabled", "ai_manager_phone_number", "language_preference", "default_voice_provider",
    "require_pin_for_level", "daily_spend_limit", "monthly_spend_limit",
    "max_bulk_leads_without_pin", "allowed_call_start_time", "allowed_call_end_time",
    "timezone",
}


def _profile_defaults(tenant_id: str) -> dict:
    return {
        "id": _new_id("aimp_"),
        "vendor_id": tenant_id,
        "enabled": False,
        "ai_manager_phone_number": "",
        "language_preference": "en",
        "default_voice_provider": "",
        "require_pin_for_level": 3,
        "daily_spend_limit": 0,
        "monthly_spend_limit": 0,
        "max_bulk_leads_without_pin": 0,
        "allowed_call_start_time": "",
        "allowed_call_end_time": "",
        "timezone": "Asia/Kolkata",
        "created_at": _now(),
        "updated_at": _now(),
    }


# user fields the frontend may write (never pin_hash directly)
_USER_WRITABLE = {"name", "phone_number", "normalized_phone_number", "role",
                  "permissions", "is_active", "user_id"}


def _user_public(row: dict) -> dict:
    """Project a user row for return — `has_pin` bool ONLY; pin_hash NEVER leaked."""
    out = {k: v for k, v in row.items() if k not in ("pin_hash",)}
    out["has_pin"] = bool(row.get("pin_hash"))
    return out


# =========================================================================== #
# module-level singletons (the InMemory backend — the default + tested path)
# =========================================================================== #
_LOCK = threading.RLock()
_SESS = _InMemSessions()
_CMDS = _InMemCommands()
_AUDIT = _InMemAudit()
_RUNS = _InMemRuns()
_PROFILES = _InMemProfiles()
_USERS = _InMemUsers()
_PG_READY = False       # init() latch (best-effort ensure_schema)


# =========================================================================== #
# availability + init
# =========================================================================== #
def available() -> bool:
    """True iff a Postgres engine is resolvable AND probes OK. On this box db.engine
    is absent → False → InMemory is used. NEVER raises."""
    try:
        return _engine() is not None
    except Exception:  # noqa: BLE001
        return False


def init() -> None:
    """Best-effort: lazily run ensure_schema() (no-op unless AIM_PG_DSN / shared engine).
    Sets the availability latch. NEVER raises; safe to call repeatedly."""
    global _PG_READY
    try:
        try:
            from .db import engine as eng  # type: ignore
            eng.ensure_schema()
        except Exception:  # noqa: BLE001
            pass
        with _LOCK:
            _PG_READY = available()
    except Exception:  # noqa: BLE001
        pass


# =========================================================================== #
# SESSIONS
# =========================================================================== #
def create_session(tenant_id: str, session_id: str, *, channel: str = "phone",
                   caller_phone: str = "", llm_provider: str = "", stt_provider: str = "",
                   tts_provider: str = "", user_id: str = "",
                   provider_call_id: str = "") -> str:
    """Create the session header row (idempotent on (vendor_id, id)). Returns session_id.
    Fail-closed on blank tenant. NEVER raises."""
    if not _ok(tenant_id) or not (session_id or "").strip():
        return session_id or ""
    row = {
        "id": session_id, "vendor_id": tenant_id, "user_id": user_id or "",
        "channel": channel or "phone", "provider_call_id": provider_call_id or "",
        "caller_phone": caller_phone or "", "status": "active",
        "started_at": _now(), "ended_at": "", "transcript_text": "",
        "stt_provider": stt_provider or "", "tts_provider": tts_provider or "",
        "llm_provider": llm_provider or "", "metadata": {},
        "recording_status": "none", "recording_key": "", "recording_url": "",
        "recording_bucket": "", "recording_provider": "", "recording_egress_id": "",
        "recording_started_at": "", "recording_ended_at": "", "recording_duration_s": 0,
        "outcome": "", "n_actions": 0, "created_at": _now(),
    }
    eng = _engine()
    if eng is not None:
        _PgSessions().create(eng, row)
    _SESS.create(row)
    return session_id


def end_session(tenant_id: str, session_id: str, *, status: str = "completed",
                transcript_text: str = "", outcome: str = "", n_actions: int = 0) -> None:
    """Close the session row with the terminal status + transcript snapshot + outcome.
    No-op on blank tenant / unknown session. NEVER raises."""
    if not _ok(tenant_id) or not (session_id or "").strip():
        return
    fields = {"status": status or "completed", "ended_at": _now(),
              "outcome": outcome or "", "n_actions": _as_int(n_actions, 0)}
    if transcript_text:
        fields["transcript_text"] = transcript_text
    eng = _engine()
    if eng is not None:
        _PgSessions().patch(eng, tenant_id, session_id, fields)
    _SESS.patch(tenant_id, session_id, fields)


def add_turn(tenant_id: str, session_id: str, role: str, text: str, *, seq: int = 0) -> None:
    """Append a transcript turn (ai_manager_session_turns). PIN/OTP digits never reach
    here (the secret span is collected out-of-band and masked). NEVER raises."""
    if not _ok(tenant_id) or not (session_id or "").strip() or not (text or "").strip():
        return
    turn = {"id": _new_id("trn_"), "vendor_id": tenant_id, "session_id": session_id,
            "seq": _as_int(seq, 0), "role": role or "agent", "text": text,
            "command_id": "", "metadata": {}, "created_at": _now()}
    eng = _engine()
    if eng is not None:
        _PgSessions().add_turn(eng, turn)
    _SESS.add_turn(turn)


def _session_public(row: dict) -> dict:
    """List-row projection: the keys caller.py + the panel read."""
    rec_status = row.get("recording_status", "") or ""
    return {
        "id": row.get("id", ""),
        "vendor_id": row.get("vendor_id", ""),
        "user_id": row.get("user_id", ""),
        "channel": row.get("channel", ""),
        "caller_phone": row.get("caller_phone", ""),
        "provider_call_id": row.get("provider_call_id", ""),
        "status": row.get("status", ""),
        "started_at": row.get("started_at", ""),
        "ended_at": row.get("ended_at", ""),
        "outcome": row.get("outcome", ""),
        "n_actions": _as_int(row.get("n_actions"), 0),
        "recording_status": rec_status,
        "recording_duration_s": _as_int(row.get("recording_duration_s"), 0),
        "has_recording": rec_status in ("stored", "uploaded"),
        "llm_provider": row.get("llm_provider", ""),
        "stt_provider": row.get("stt_provider", ""),
        "tts_provider": row.get("tts_provider", ""),
    }


def list_sessions(tenant_id: str, *, limit: int = 50, offset: int = 0,
                  channel: str = "", status: str = "") -> list[dict]:
    """Newest-first page of session header rows for the tenant. Fail-closed → [].
    NEVER raises. (caller.py passes channel='voice'/limit=200; the panel passes
    limit/offset/channel/status.)"""
    if not _ok(tenant_id):
        return []
    try:
        eng = _engine()
        rows = _PgSessions().scan(eng, tenant_id) if eng is not None else _SESS.scan(tenant_id)
        if channel:
            rows = [r for r in rows if (r.get("channel") or "") == channel]
        if status:
            rows = [r for r in rows if (r.get("status") or "") == status]
        rows.sort(key=lambda r: (r.get("started_at", ""), r.get("id", "")), reverse=True)
        off = max(0, _as_int(offset, 0))
        lim = _clamp(limit, 1, 500, 50)
        return [_session_public(r) for r in rows[off:off + lim]]
    except Exception:  # noqa: BLE001
        return []


def get_session(tenant_id: str, session_id: str) -> Optional[dict]:
    """Full session detail: header + turns + commands + recording_* fields. RLS:
    cross-tenant session_id → None. NEVER raises (None on any error)."""
    if not _ok(tenant_id) or not (session_id or "").strip():
        return None
    try:
        eng = _engine()
        if eng is not None:
            pg = _PgSessions()
            row = pg.get(eng, tenant_id, session_id)
            if not row:
                return None
            turns = pg.turns(eng, tenant_id, session_id)
        else:
            row = _SESS.get(tenant_id, session_id)
            if not row:
                return None
            turns = _SESS.turns(tenant_id, session_id)
        cmds = list_commands(tenant_id, session_id=session_id, limit=200)
        out = dict(row)
        out["turns"] = [{
            "seq": _as_int(t.get("seq"), 0),
            "role": t.get("role", ""),
            "text": t.get("text", ""),
            "command_id": t.get("command_id", "") or "",
            "created_at": t.get("created_at", ""),
        } for t in turns]
        out["commands"] = cmds
        # recording_* fields the caller + panel read (with safe defaults)
        out.setdefault("recording_bucket", "")
        out.setdefault("recording_key", "")
        out.setdefault("recording_status", "")
        out.setdefault("recording_duration_s", 0)
        out.setdefault("recording_egress_id", "")
        out.setdefault("recording_url", "")
        out["recording_duration_s"] = _as_int(out.get("recording_duration_s"), 0)
        out["has_recording"] = (out.get("recording_status") or "") in ("stored", "uploaded")
        out.setdefault("caller_phone", "")
        out.setdefault("status", "")
        out.setdefault("started_at", "")
        return _jsonify(out)
    except Exception:  # noqa: BLE001
        return None


def set_recording(tenant_id: str, session_id: str, *, status: str, key: str = "",
                  duration_s: int = 0, bucket: str = "", egress_id: str = "",
                  provider: str = "") -> None:
    """Persist the reconciled terminal recording state (finalize-on-read from caller.py).
    No-op on blank tenant / unknown session. NEVER raises."""
    if not _ok(tenant_id) or not (session_id or "").strip():
        return
    fields: dict = {"recording_status": status or ""}
    if key:
        fields["recording_key"] = key
    if duration_s:
        fields["recording_duration_s"] = _as_int(duration_s, 0)
    if bucket:
        fields["recording_bucket"] = bucket
    if egress_id:
        fields["recording_egress_id"] = egress_id
    if provider:
        fields["recording_provider"] = provider
    if (status or "") in ("stored", "uploaded", "failed", "disabled"):
        fields["recording_ended_at"] = _now()
    eng = _engine()
    if eng is not None:
        _PgSessions().patch(eng, tenant_id, session_id, fields)
    _SESS.patch(tenant_id, session_id, fields)


# =========================================================================== #
# COMMANDS
# =========================================================================== #
def make_idempotency_key(tenant_id: str, session_id: str, tool: str, args: Any) -> str:
    """Stable hash of (tenant, session, tool, sorted args) — a retried turn resolves to
    the SAME command row (no double-execute). NEVER raises."""
    try:
        payload = json.dumps(args or {}, sort_keys=True, default=str, ensure_ascii=False)
    except Exception:  # noqa: BLE001
        payload = str(args)
    raw = "\x1f".join([tenant_id or "", session_id or "", tool or "", payload])
    return "idem_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def create_command(tenant_id: str, *, session_id: str = "", user_id: str = "",
                   raw_text: str = "", normalized_text: str = "", detected_intent: str = "",
                   action_type: str = "", action_payload: Any = None, risk_level: int = 0,
                   status: str = "pending", idempotency_key: str = "") -> str:
    """Create a command row (pre-mint cmd_<uuid>). Idempotent on (vendor_id,
    idempotency_key): a non-empty key that already exists returns the EXISTING id.
    Fail-closed on blank tenant (returns ''). NEVER raises."""
    if not _ok(tenant_id):
        return ""
    command_id = _new_id("cmd_")
    row = {
        "id": command_id, "session_id": session_id or "", "vendor_id": tenant_id,
        "user_id": user_id or "", "raw_text": raw_text or "",
        "normalized_text": normalized_text or "", "detected_intent": detected_intent or "",
        "action_type": action_type or "", "action_payload": dict(action_payload or {}),
        "risk_level": _as_int(risk_level, 0), "status": status or "pending",
        "confirmation_required": False, "confirmation_status": "",
        "pin_required": False, "pin_verified": False, "permission_result": {},
        "cost_estimate": {}, "execution_result": {}, "error_message": "",
        "idempotency_key": idempotency_key or "",
        "created_at": _now(), "updated_at": _now(),
    }
    eng = _engine()
    if eng is not None:
        existing = _PgCommands().insert(eng, row)
        # mirror to InMemory regardless (so reads stay consistent even mid-degrade)
        _CMDS.insert(row)
        return existing or command_id
    return _CMDS.insert(row)


_CMD_PATCHABLE = {"status", "confirmation_required", "confirmation_status", "pin_required",
                  "pin_verified", "permission_result", "cost_estimate", "execution_result",
                  "error_message", "action_type", "action_payload", "risk_level",
                  "detected_intent", "normalized_text"}


def update_command(tenant_id: str, command_id: str, **fields: Any) -> None:
    """Patch allowed columns on a command; bumps updated_at. No-op if not found /
    cross-tenant / blank tenant. NEVER raises."""
    if not _ok(tenant_id) or not (command_id or "").strip():
        return
    patch = {k: v for k, v in fields.items() if k in _CMD_PATCHABLE}
    if "risk_level" in patch:
        patch["risk_level"] = _as_int(patch["risk_level"], 0)
    if not patch:
        return
    eng = _engine()
    if eng is not None:
        _PgCommands().patch(eng, tenant_id, command_id, patch)
    _CMDS.patch(tenant_id, command_id, patch)


def _command_public(row: dict) -> dict:
    """Shape-stable command projection (matches list_commands output)."""
    return {
        "id": row.get("id", ""),
        "command_id": row.get("id", ""),
        "session_id": row.get("session_id", "") or "",
        "vendor_id": row.get("vendor_id", ""),
        "user_id": row.get("user_id", "") or "",
        "raw_text": row.get("raw_text", ""),
        "normalized_text": row.get("normalized_text", ""),
        "command_text": row.get("raw_text", "") or row.get("normalized_text", ""),
        "detected_intent": row.get("detected_intent", ""),
        "intent": row.get("detected_intent", ""),
        "action_type": row.get("action_type", ""),
        "action_payload": row.get("action_payload", {}) or {},
        "risk_level": _as_int(row.get("risk_level"), 0),
        "status": row.get("status", ""),
        "confirmation_required": bool(row.get("confirmation_required")),
        "confirmation_status": row.get("confirmation_status", "") or "",
        "pin_required": bool(row.get("pin_required")),
        "pin_verified": bool(row.get("pin_verified")),
        "permission_result": row.get("permission_result", {}) or {},
        "cost_estimate": row.get("cost_estimate", {}) or {},
        "execution_result": row.get("execution_result", {}) or {},
        "error_message": row.get("error_message", "") or "",
        "idempotency_key": row.get("idempotency_key", "") or "",
        "created_at": row.get("created_at", ""),
        "updated_at": row.get("updated_at", ""),
    }


def get_command(tenant_id: str, command_id: str) -> Optional[dict]:
    """One command row (RLS-scoped). None on blank tenant / not found / cross-tenant."""
    if not _ok(tenant_id) or not (command_id or "").strip():
        return None
    try:
        eng = _engine()
        row = _PgCommands().get(eng, tenant_id, command_id) if eng is not None \
            else _CMDS.get(tenant_id, command_id)
        return _jsonify(_command_public(row)) if row else None
    except Exception:  # noqa: BLE001
        return None


def list_commands(tenant_id: str, *, status: str = "", action_type: str = "",
                  session_id: str = "", user_id: str = "", since: str = "", until: str = "",
                  limit: int = 50, offset: int = 0, is_admin: bool = False) -> list[dict]:
    """Newest-first page of command rows for the tenant (schema-contract §5a). Filters:
    status/action_type/session_id/user_id exact-match; since/until ISO bounds on
    created_at. Clamp limit→[1,200], offset→>=0. admin GUC → cross-tenant. Fail-closed:
    blank tenant with is_admin=False → []. NEVER raises → [] on error."""
    if not _ok(tenant_id) and not is_admin:
        return []
    try:
        eng = _engine()
        rows = (_PgCommands().scan(eng, tenant_id, is_admin=is_admin) if eng is not None
                else _CMDS.scan(tenant_id, is_admin=is_admin))
        if status:
            rows = [r for r in rows if (r.get("status") or "") == status]
        if action_type:
            rows = [r for r in rows if (r.get("action_type") or "") == action_type]
        if session_id:
            rows = [r for r in rows if (r.get("session_id") or "") == session_id]
        if user_id:
            rows = [r for r in rows if (r.get("user_id") or "") == user_id]
        if since:
            rows = [r for r in rows if _iso_ge(r.get("created_at", ""), since)]
        if until:
            rows = [r for r in rows if _iso_lt(r.get("created_at", ""), until)]
        rows.sort(key=lambda r: (r.get("created_at", ""), r.get("id", "")), reverse=True)
        off = max(0, _as_int(offset, 0))
        lim = _clamp(limit, 1, 200, 50)
        return [_jsonify(_command_public(r)) for r in rows[off:off + lim]]
    except Exception:  # noqa: BLE001
        return []


# =========================================================================== #
# AUDIT (immutable — INSERT + SELECT only)
# =========================================================================== #
def record_audit_log(tenant_id: str, *, event_type: str, severity: str = "info",
                     session_id: str = "", command_id: str = "", message: str = "",
                     metadata: Any = None) -> str:
    """INSERT-only audit row. Scrubs secret-shaped keys in metadata before persist
    ({pin,otp,secret,code,token,step_up_token,...}→'***'). Returns the audit id.
    Fail-closed on blank tenant (returns ''). NEVER raises."""
    if not _ok(tenant_id):
        return ""
    audit_id = _new_id("aud_")
    # Normalize severity aliases to the canonical bucket set so dashboard_summary's by_severity
    # roll-up never silently drops a row (e.g. callers that say 'warning' for 'warn') — audit finding #4.
    sev = (severity or "info").strip().lower()
    sev = {"warning": "warn", "err": "error", "crit": "critical", "fatal": "critical"}.get(sev, sev)
    if sev not in _AUDIT_SEVERITIES:
        sev = "info"
    row = {
        "id": audit_id, "vendor_id": tenant_id, "user_id": "",
        "session_id": session_id or "", "command_id": command_id or "",
        "event_type": event_type or "", "severity": sev,
        "message": message or "", "metadata": _scrub(dict(metadata or {})),
        "created_at": _now(),
    }
    eng = _engine()
    if eng is not None:
        _PgAudit().insert(eng, row)
    _AUDIT.insert(row)
    return audit_id


def _audit_public(row: dict) -> dict:
    return {
        "id": row.get("id", ""),
        "vendor_id": row.get("vendor_id", ""),
        "user_id": row.get("user_id", "") or "",
        "session_id": row.get("session_id", "") or "",
        "command_id": row.get("command_id", "") or "",
        "event_type": row.get("event_type", ""),
        "severity": row.get("severity", "info"),
        "message": row.get("message", ""),
        "metadata": row.get("metadata", {}) or {},
        "created_at": row.get("created_at", ""),
    }


def list_audit(tenant_id: str, *, session_id: str = "", command_id: str = "",
               limit: int = 100, is_admin: bool = False) -> list[dict]:
    """Newest-first audit rows for the tenant. Fail-closed → []. NEVER raises."""
    if not _ok(tenant_id) and not is_admin:
        return []
    try:
        eng = _engine()
        rows = (_PgAudit().scan(eng, tenant_id, is_admin=is_admin) if eng is not None
                else _AUDIT.scan(tenant_id, is_admin=is_admin))
        if session_id:
            rows = [r for r in rows if (r.get("session_id") or "") == session_id]
        if command_id:
            rows = [r for r in rows if (r.get("command_id") or "") == command_id]
        rows.sort(key=lambda r: (r.get("created_at", ""), r.get("id", "")), reverse=True)
        lim = _clamp(limit, 1, 1000, 100)
        return [_jsonify(_audit_public(r)) for r in rows[:lim]]
    except Exception:  # noqa: BLE001
        return []


# =========================================================================== #
# ACTION RUNS
# =========================================================================== #
def create_action_run(tenant_id: str, *, command_id: str, action_type: str,
                      target_module: str, status: str = "queued", input: Any = None,
                      job_id: str = "") -> str:
    """Create an action-run record (queue→terminal). Returns run id. Fail-closed on
    blank tenant (returns ''). NEVER raises."""
    if not _ok(tenant_id):
        return ""
    run_id = _new_id("run_")
    started = _now() if (status or "") == "running" else ""
    row = {
        "id": run_id, "command_id": command_id or "", "vendor_id": tenant_id,
        "action_type": action_type or "", "target_module": target_module or "",
        "status": status or "queued", "job_id": job_id or "",
        "input": dict(input or {}), "output": {}, "error": {},
        "started_at": started, "completed_at": "", "created_at": _now(),
    }
    eng = _engine()
    if eng is not None:
        _PgRuns().insert(eng, row)
    _RUNS.insert(row)
    return run_id


def finish_action_run(tenant_id: str, run_id: str, *, status: str, output: Any = None,
                      error: Any = None) -> None:
    """Patch a run to a terminal state with output/error + completed_at. No-op if not
    found / cross-tenant. NEVER raises."""
    if not _ok(tenant_id) or not (run_id or "").strip():
        return
    fields = {"status": status or "succeeded", "completed_at": _now()}
    if output is not None:
        fields["output"] = dict(output) if isinstance(output, dict) else {"value": output}
    if error is not None:
        fields["error"] = dict(error) if isinstance(error, dict) else {"error": str(error)}
    eng = _engine()
    if eng is not None:
        _PgRuns().patch(eng, tenant_id, run_id, fields)
    _RUNS.patch(tenant_id, run_id, fields)


def _run_public(row: dict) -> dict:
    return {
        "id": row.get("id", ""),
        "command_id": row.get("command_id", "") or "",
        "vendor_id": row.get("vendor_id", ""),
        "action_type": row.get("action_type", ""),
        "target_module": row.get("target_module", ""),
        "status": row.get("status", ""),
        "job_id": row.get("job_id", "") or "",
        "input": row.get("input", {}) or {},
        "output": row.get("output", {}) or {},
        "error": row.get("error", {}) or {},
        "started_at": row.get("started_at", "") or "",
        "completed_at": row.get("completed_at", "") or "",
        "created_at": row.get("created_at", ""),
    }


def list_action_runs(tenant_id: str, *, command_id: str = "", limit: int = 100,
                     is_admin: bool = False) -> list[dict]:
    """Newest-first action-run rows for the tenant. Fail-closed → []. NEVER raises."""
    if not _ok(tenant_id) and not is_admin:
        return []
    try:
        eng = _engine()
        rows = (_PgRuns().scan(eng, tenant_id, is_admin=is_admin) if eng is not None
                else _RUNS.scan(tenant_id, is_admin=is_admin))
        if command_id:
            rows = [r for r in rows if (r.get("command_id") or "") == command_id]
        rows.sort(key=lambda r: (r.get("created_at", ""), r.get("id", "")), reverse=True)
        lim = _clamp(limit, 1, 1000, 100)
        return [_jsonify(_run_public(r)) for r in rows[:lim]]
    except Exception:  # noqa: BLE001
        return []


# =========================================================================== #
# DASHBOARD SUMMARY  (zero-filled — every enum bucket present; §5b)
# =========================================================================== #
def _zero_summary(window_since: str) -> dict:
    return {
        "window_since": window_since or "",
        "commands": {
            "total": 0,
            "by_status": {s: 0 for s in _CMD_STATUSES},
            "by_risk_level": {"0": 0, "1": 0, "2": 0, "3": 0, "4": 0},
            "pin_required": 0,
            "blocked": 0,
        },
        "sessions": {
            "total": 0,
            "by_status": {s: 0 for s in _SESSION_STATUSES},
            "by_channel": {c: 0 for c in _SESSION_CHANNELS},
            "with_recording": 0,
            "total_actions": 0,
        },
        "action_runs": {
            "total": 0,
            "by_status": {s: 0 for s in _RUN_STATUSES},
        },
        "audit": {
            "total": 0,
            "by_severity": {s: 0 for s in _AUDIT_SEVERITIES},
        },
    }


def dashboard_summary(tenant_id: str, *, since: str = "", is_admin: bool = False) -> dict:
    """One roll-up for /ai-manager/dashboard/summary. Every enum bucket present + 0-filled
    so the Overview renders dormant-safe. Fail-closed → the zero summary on blank tenant /
    error. NEVER raises."""
    summary = _zero_summary(since)
    if not _ok(tenant_id) and not is_admin:
        return summary
    try:
        # ---- commands ----
        for r in list_commands(tenant_id, since=since, limit=200, is_admin=is_admin):
            c = summary["commands"]
            c["total"] += 1
            st = r.get("status", "")
            if st in c["by_status"]:
                c["by_status"][st] += 1
            lvl = str(_as_int(r.get("risk_level"), 0))
            if lvl in c["by_risk_level"]:
                c["by_risk_level"][lvl] += 1
            if r.get("pin_required"):
                c["pin_required"] += 1
            if st == "denied" or _as_int(r.get("risk_level"), 0) >= 4:
                c["blocked"] += 1
        # ---- sessions ----
        eng = _engine()
        srows = (_PgSessions().scan(eng, tenant_id) if eng is not None
                 else _SESS.scan(tenant_id))
        if since:
            srows = [r for r in srows if _iso_ge(r.get("started_at", ""), since)]
        s = summary["sessions"]
        for r in srows:
            s["total"] += 1
            st = r.get("status", "")
            if st in s["by_status"]:
                s["by_status"][st] += 1
            ch = r.get("channel", "")
            if ch in s["by_channel"]:
                s["by_channel"][ch] += 1
            if (r.get("recording_status") or "") in ("stored", "uploaded"):
                s["with_recording"] += 1
            s["total_actions"] += _as_int(r.get("n_actions"), 0)
        # ---- action_runs ----
        ar = summary["action_runs"]
        for r in list_action_runs(tenant_id, limit=1000, is_admin=is_admin):
            if since and not _iso_ge(r.get("created_at", ""), since):
                continue
            ar["total"] += 1
            st = r.get("status", "")
            if st in ar["by_status"]:
                ar["by_status"][st] += 1
        # ---- audit ----
        au = summary["audit"]
        for r in list_audit(tenant_id, limit=1000, is_admin=is_admin):
            if since and not _iso_ge(r.get("created_at", ""), since):
                continue
            au["total"] += 1
            sev = r.get("severity", "info")
            if sev in au["by_severity"]:
                au["by_severity"][sev] += 1
        return summary
    except Exception:  # noqa: BLE001
        return _zero_summary(since)


# =========================================================================== #
# PROFILES  (frontend Setup page)
# =========================================================================== #
def get_profile(tenant_id: str) -> dict:
    """The vendor's AI-Manager profile (zero-filled defaults when no row). Fail-closed →
    defaults on blank tenant. NEVER raises."""
    if not _ok(tenant_id):
        return _profile_defaults(tenant_id or "")
    try:
        eng = _engine()
        row = _PgProfiles().get(eng, tenant_id) if eng is not None else _PROFILES.get(tenant_id)
        return _jsonify(row) if row else _profile_defaults(tenant_id)
    except Exception:  # noqa: BLE001
        return _profile_defaults(tenant_id)


def upsert_profile(tenant_id: str, fields: dict) -> dict:
    """Create-or-patch the vendor profile (writable fields only). Returns the updated
    row. Fail-closed → defaults on blank tenant. NEVER raises."""
    if not _ok(tenant_id):
        return _profile_defaults(tenant_id or "")
    try:
        clean = {k: v for k, v in (fields or {}).items() if k in _PROFILE_WRITABLE}
        eng = _engine()
        if eng is not None:
            row = _PgProfiles().upsert(eng, tenant_id, clean)
            _PROFILES.upsert(tenant_id, clean)
            return _jsonify(row)
        return _jsonify(_PROFILES.upsert(tenant_id, clean))
    except Exception:  # noqa: BLE001
        return _profile_defaults(tenant_id)


# =========================================================================== #
# AUTHORIZED USERS  (frontend Users page; pin_hash NEVER returned)
# =========================================================================== #
def list_users(tenant_id: str) -> list[dict]:
    """The vendor's authorized users (has_pin bool only; pin_hash never exposed).
    Fail-closed → []. NEVER raises."""
    if not _ok(tenant_id):
        return []
    try:
        eng = _engine()
        rows = _PgUsers().scan(eng, tenant_id) if eng is not None else _USERS.scan(tenant_id)
        rows.sort(key=lambda r: (r.get("created_at", ""), r.get("id", "")))
        return [_jsonify(_user_public(r)) for r in rows]
    except Exception:  # noqa: BLE001
        return []


def get_user(tenant_id: str, user_id: str) -> Optional[dict]:
    """One authorized-user row (has_pin only). None on blank tenant / not found /
    cross-tenant. NEVER raises."""
    if not _ok(tenant_id) or not (user_id or "").strip():
        return None
    try:
        eng = _engine()
        row = _PgUsers().get(eng, tenant_id, user_id) if eng is not None \
            else _USERS.get(tenant_id, user_id)
        return _jsonify(_user_public(row)) if row else None
    except Exception:  # noqa: BLE001
        return None


def create_user(tenant_id: str, fields: dict) -> dict:
    """Create an authorized user. Returns the created row (has_pin only). Fail-closed →
    {} on blank tenant. NEVER raises."""
    if not _ok(tenant_id):
        return {}
    try:
        f = dict(fields or {})
        row = {
            "id": _new_id("aimu_"), "vendor_id": tenant_id,
            "user_id": f.get("user_id", "") or "",
            "name": f.get("name", "") or "",
            "phone_number": f.get("phone_number", "") or "",
            "normalized_phone_number": f.get("normalized_phone_number", "") or "",
            "role": f.get("role", "member") or "member",
            "permissions": f.get("permissions", []) or [],
            "is_active": bool(f.get("is_active", True)),
            "pin_hash": None, "pin_set_at": None,
            "failed_pin_attempts": 0, "locked_until": None,
            "created_at": _now(), "updated_at": _now(),
        }
        eng = _engine()
        if eng is not None:
            _PgUsers().insert(eng, row)
        _USERS.insert(row)
        return _jsonify(_user_public(row))
    except Exception:  # noqa: BLE001
        return {}


def update_user(tenant_id: str, user_id: str, fields: dict) -> dict:
    """Patch a user (writable fields only; pin_hash never patched here). Returns the
    updated row (has_pin only), or {} if not found / cross-tenant. NEVER raises."""
    if not _ok(tenant_id) or not (user_id or "").strip():
        return {}
    try:
        patch = {k: v for k, v in (fields or {}).items() if k in _USER_WRITABLE}
        if not patch:
            existing = get_user(tenant_id, user_id)
            return existing or {}
        eng = _engine()
        if eng is not None:
            _PgUsers().patch(eng, tenant_id, user_id, patch)
        row = _USERS.patch(tenant_id, user_id, patch)
        return _jsonify(_user_public(row)) if row else {}
    except Exception:  # noqa: BLE001
        return {}


def set_user_active(tenant_id: str, user_id: str, active: bool) -> dict:
    """Activate / deactivate a user. Returns the updated row, or {} if not found.
    NEVER raises."""
    return update_user(tenant_id, user_id, {"is_active": bool(active)})


# =========================================================================== #
# Pg BACKENDS — best-effort, lazy; mirror grow/store.py. Each method takes the
# resolved engine module. On ANY failure they log + degrade (callers also mirror
# to InMemory so reads stay coherent). ZERO sqlalchemy at import.
# =========================================================================== #
class _PgSessions:
    def create(self, eng, row: dict) -> None:
        try:
            with eng.session(tenant_id=row["vendor_id"], is_admin=False) as s:
                s.execute(_text(
                    "INSERT INTO ai_manager_sessions (id,vendor_id,user_id,channel,"
                    " provider_call_id,caller_phone,status,llm_provider,stt_provider,"
                    " tts_provider) VALUES (:id,:org,:uid,:ch,:pcid,:cp,'active',:llm,:stt,:tts) "
                    "ON CONFLICT (id) DO NOTHING"
                ), {"id": row["id"], "org": row["vendor_id"], "uid": row.get("user_id") or None,
                    "ch": row.get("channel", "phone"), "pcid": row.get("provider_call_id") or None,
                    "cp": row.get("caller_phone", ""), "llm": row.get("llm_provider", ""),
                    "stt": row.get("stt_provider", ""), "tts": row.get("tts_provider", "")})
        except Exception as exc:  # noqa: BLE001
            log.info("ai_manager_sessions create failed: %r", exc)

    def patch(self, eng, tenant_id: str, session_id: str, fields: dict) -> None:
        if not fields:
            return
        try:
            sets, params = [], {"org": tenant_id, "sid": session_id}
            for i, (k, v) in enumerate(fields.items()):
                p = f"p{i}"
                sets.append(f"{k} = :{p}")
                params[p] = v
            with eng.session(tenant_id=tenant_id, is_admin=False) as s:
                s.execute(_text(
                    f"UPDATE ai_manager_sessions SET {', '.join(sets)} "
                    "WHERE id = :sid AND vendor_id = :org"
                ), params)
        except Exception as exc:  # noqa: BLE001
            log.info("ai_manager_sessions patch failed: %r", exc)

    _SEL = ("SELECT id,vendor_id,user_id,channel,provider_call_id,caller_phone,status,"
            "started_at,ended_at,outcome,n_actions,recording_status,recording_key,"
            "recording_url,recording_provider,recording_duration_s,transcript_text,"
            "llm_provider,stt_provider,tts_provider FROM ai_manager_sessions")

    def _row(self, r) -> dict:
        m = r._mapping if hasattr(r, "_mapping") else dict(zip(self._cols(), r))
        d = dict(m)
        d.setdefault("recording_bucket", "")
        d.setdefault("recording_egress_id", "")
        return d

    def _cols(self):
        return ["id", "vendor_id", "user_id", "channel", "provider_call_id", "caller_phone",
                "status", "started_at", "ended_at", "outcome", "n_actions", "recording_status",
                "recording_key", "recording_url", "recording_provider", "recording_duration_s",
                "transcript_text", "llm_provider", "stt_provider", "tts_provider"]

    def get(self, eng, tenant_id: str, session_id: str) -> Optional[dict]:
        try:
            with eng.session(tenant_id=tenant_id, is_admin=False) as s:
                r = s.execute(_text(self._SEL + " WHERE id=:sid AND vendor_id=:org"),
                              {"sid": session_id, "org": tenant_id}).fetchone()
                return self._row(r) if r else None
        except Exception as exc:  # noqa: BLE001
            log.info("ai_manager_sessions get failed: %r", exc)
            return None

    def scan(self, eng, tenant_id: str) -> list[dict]:
        try:
            with eng.session(tenant_id=tenant_id, is_admin=False) as s:
                rows = s.execute(_text(
                    self._SEL + " WHERE vendor_id=:org ORDER BY started_at DESC LIMIT 1000"
                ), {"org": tenant_id}).fetchall()
                return [self._row(r) for r in rows]
        except Exception as exc:  # noqa: BLE001
            log.info("ai_manager_sessions scan failed: %r", exc)
            return []

    def add_turn(self, eng, turn: dict) -> None:
        try:
            with eng.session(tenant_id=turn["vendor_id"], is_admin=False) as s:
                s.execute(_text(
                    "INSERT INTO ai_manager_session_turns (id,vendor_id,session_id,seq,role,text)"
                    " VALUES (:id,:org,:sid,:seq,:role,:text) "
                    "ON CONFLICT (vendor_id,session_id,seq) DO NOTHING"
                ), {"id": turn["id"], "org": turn["vendor_id"], "sid": turn["session_id"],
                    "seq": int(turn.get("seq", 0)), "role": turn.get("role", "agent"),
                    "text": turn.get("text", "")})
        except Exception as exc:  # noqa: BLE001
            log.info("ai_manager_session_turns insert failed: %r", exc)

    def turns(self, eng, tenant_id: str, session_id: str) -> list[dict]:
        try:
            with eng.session(tenant_id=tenant_id, is_admin=False) as s:
                rows = s.execute(_text(
                    "SELECT seq,role,text,created_at FROM ai_manager_session_turns "
                    "WHERE vendor_id=:org AND session_id=:sid ORDER BY seq ASC LIMIT 5000"
                ), {"org": tenant_id, "sid": session_id}).fetchall()
                out = []
                for r in rows:
                    m = r._mapping if hasattr(r, "_mapping") else None
                    if m is not None:
                        out.append({"seq": m["seq"], "role": m["role"], "text": m["text"],
                                    "created_at": m["created_at"], "command_id": ""})
                    else:
                        out.append({"seq": r[0], "role": r[1], "text": r[2],
                                    "created_at": r[3], "command_id": ""})
                return out
        except Exception as exc:  # noqa: BLE001
            log.info("ai_manager_session_turns scan failed: %r", exc)
            return []


class _PgCommands:
    def insert(self, eng, row: dict) -> str:
        try:
            with eng.session(tenant_id=row["vendor_id"], is_admin=False) as s:
                if (row.get("idempotency_key") or "").strip():
                    existing = s.execute(_text(
                        "SELECT id FROM ai_manager_commands WHERE vendor_id=:org "
                        "AND idempotency_key=:ik"
                    ), {"org": row["vendor_id"], "ik": row["idempotency_key"]}).fetchone()
                    if existing:
                        return existing[0]
                s.execute(_text(
                    "INSERT INTO ai_manager_commands (id,session_id,vendor_id,user_id,raw_text,"
                    " normalized_text,detected_intent,action_type,action_payload,risk_level,"
                    " status,idempotency_key) VALUES (:id,:sid,:org,:uid,:rt,:nt,:di,:at,"
                    " CAST(:ap AS jsonb),:rl,:st,:ik) ON CONFLICT (id) DO NOTHING"
                ), {"id": row["id"], "sid": row.get("session_id") or None, "org": row["vendor_id"],
                    "uid": row.get("user_id") or None, "rt": row.get("raw_text", ""),
                    "nt": row.get("normalized_text", ""), "di": row.get("detected_intent", ""),
                    "at": row.get("action_type", ""),
                    "ap": json.dumps(row.get("action_payload", {}) or {}),
                    "rl": int(row.get("risk_level", 0)), "st": row.get("status", "pending"),
                    "ik": row.get("idempotency_key", "")})
                return row["id"]
        except Exception as exc:  # noqa: BLE001
            log.info("ai_manager_commands insert failed: %r", exc)
            return row["id"]

    _JSONB_COLS = {"permission_result", "cost_estimate", "execution_result", "action_payload"}

    def patch(self, eng, tenant_id: str, command_id: str, fields: dict) -> None:
        if not fields:
            return
        try:
            sets, params = [], {"org": tenant_id, "cid": command_id}
            for i, (k, v) in enumerate(fields.items()):
                p = f"p{i}"
                if k in self._JSONB_COLS:
                    sets.append(f"{k} = CAST(:{p} AS jsonb)")
                    params[p] = json.dumps(v or {})
                else:
                    sets.append(f"{k} = :{p}")
                    params[p] = v
            sets.append("updated_at = now()")
            with eng.session(tenant_id=tenant_id, is_admin=False) as s:
                s.execute(_text(
                    f"UPDATE ai_manager_commands SET {', '.join(sets)} "
                    "WHERE id = :cid AND vendor_id = :org"
                ), params)
        except Exception as exc:  # noqa: BLE001
            log.info("ai_manager_commands patch failed: %r", exc)

    _SEL = ("SELECT id,session_id,vendor_id,user_id,raw_text,normalized_text,detected_intent,"
            "action_type,action_payload,risk_level,status,confirmation_required,"
            "confirmation_status,pin_required,pin_verified,permission_result,cost_estimate,"
            "execution_result,error_message,idempotency_key,created_at,updated_at "
            "FROM ai_manager_commands")

    def _row(self, r) -> dict:
        m = r._mapping if hasattr(r, "_mapping") else None
        return dict(m) if m is not None else {}

    def get(self, eng, tenant_id: str, command_id: str) -> Optional[dict]:
        try:
            with eng.session(tenant_id=tenant_id, is_admin=False) as s:
                r = s.execute(_text(self._SEL + " WHERE id=:cid AND vendor_id=:org"),
                              {"cid": command_id, "org": tenant_id}).fetchone()
                return self._row(r) if r else None
        except Exception as exc:  # noqa: BLE001
            log.info("ai_manager_commands get failed: %r", exc)
            return None

    def scan(self, eng, tenant_id: str, *, is_admin: bool = False) -> list[dict]:
        try:
            # Full tenant isolation: never honor an admin RLS bypass for operational rows —
            # always confine to the caller's own vendor_id regardless of the is_admin arg.
            with eng.session(tenant_id=tenant_id, is_admin=False) as s:
                rows = s.execute(_text(
                    self._SEL + " WHERE vendor_id = :org ORDER BY created_at DESC, id DESC LIMIT 2000"
                ), {"org": tenant_id}).fetchall()
                return [self._row(r) for r in rows]
        except Exception as exc:  # noqa: BLE001
            log.info("ai_manager_commands scan failed: %r", exc)
            return []


class _PgAudit:
    def insert(self, eng, row: dict) -> None:
        try:
            with eng.session(tenant_id=row["vendor_id"], is_admin=False) as s:
                s.execute(_text(
                    "INSERT INTO ai_manager_audit_logs (id,vendor_id,user_id,session_id,"
                    " command_id,event_type,severity,message,metadata) VALUES (:id,:org,:uid,"
                    " :sid,:cid,:et,:sev,:msg,CAST(:md AS jsonb))"
                ), {"id": row["id"], "org": row["vendor_id"], "uid": row.get("user_id") or None,
                    "sid": row.get("session_id") or None, "cid": row.get("command_id") or None,
                    "et": row.get("event_type", ""), "sev": row.get("severity", "info"),
                    "msg": row.get("message", ""),
                    "md": json.dumps(row.get("metadata", {}) or {})})
        except Exception as exc:  # noqa: BLE001
            log.info("ai_manager_audit_logs insert failed: %r", exc)

    def scan(self, eng, tenant_id: str, *, is_admin: bool = False) -> list[dict]:
        try:
            # Full tenant isolation: confine to the caller's own vendor_id, never admin-bypass.
            with eng.session(tenant_id=tenant_id, is_admin=False) as s:
                rows = s.execute(_text(
                    "SELECT id,vendor_id,user_id,session_id,command_id,event_type,severity,"
                    "message,metadata,created_at FROM ai_manager_audit_logs "
                    "WHERE vendor_id = :org "
                    "ORDER BY created_at DESC, id DESC LIMIT 2000"
                ), {"org": tenant_id}).fetchall()
                return [dict(r._mapping) for r in rows if hasattr(r, "_mapping")]
        except Exception as exc:  # noqa: BLE001
            log.info("ai_manager_audit_logs scan failed: %r", exc)
            return []


class _PgRuns:
    def insert(self, eng, row: dict) -> None:
        try:
            with eng.session(tenant_id=row["vendor_id"], is_admin=False) as s:
                s.execute(_text(
                    "INSERT INTO ai_manager_action_runs (id,command_id,vendor_id,action_type,"
                    " target_module,status,job_id,input) VALUES (:id,:cid,:org,:at,:tm,:st,:jid,"
                    " CAST(:inp AS jsonb)) ON CONFLICT (id) DO NOTHING"
                ), {"id": row["id"], "cid": row.get("command_id", ""), "org": row["vendor_id"],
                    "at": row.get("action_type", ""), "tm": row.get("target_module", ""),
                    "st": row.get("status", "queued"), "jid": row.get("job_id") or None,
                    "inp": json.dumps(row.get("input", {}) or {})})
        except Exception as exc:  # noqa: BLE001
            log.info("ai_manager_action_runs insert failed: %r", exc)

    def patch(self, eng, tenant_id: str, run_id: str, fields: dict) -> None:
        if not fields:
            return
        try:
            sets, params = [], {"org": tenant_id, "rid": run_id}
            for i, (k, v) in enumerate(fields.items()):
                p = f"p{i}"
                if k in ("output", "error"):
                    sets.append(f"{k} = CAST(:{p} AS jsonb)")
                    params[p] = json.dumps(v or {})
                else:
                    sets.append(f"{k} = :{p}")
                    params[p] = v
            with eng.session(tenant_id=tenant_id, is_admin=False) as s:
                s.execute(_text(
                    f"UPDATE ai_manager_action_runs SET {', '.join(sets)} "
                    "WHERE id = :rid AND vendor_id = :org"
                ), params)
        except Exception as exc:  # noqa: BLE001
            log.info("ai_manager_action_runs patch failed: %r", exc)

    def scan(self, eng, tenant_id: str, *, is_admin: bool = False) -> list[dict]:
        try:
            # Full tenant isolation: confine to the caller's own vendor_id, never admin-bypass.
            with eng.session(tenant_id=tenant_id, is_admin=False) as s:
                rows = s.execute(_text(
                    "SELECT id,command_id,vendor_id,action_type,target_module,status,job_id,"
                    "input,output,error,started_at,completed_at,created_at "
                    "FROM ai_manager_action_runs WHERE vendor_id = :org "
                    "ORDER BY created_at DESC, id DESC LIMIT 2000"
                ), {"org": tenant_id}).fetchall()
                return [dict(r._mapping) for r in rows if hasattr(r, "_mapping")]
        except Exception as exc:  # noqa: BLE001
            log.info("ai_manager_action_runs scan failed: %r", exc)
            return []


class _PgProfiles:
    def get(self, eng, tenant_id: str) -> Optional[dict]:
        try:
            with eng.session(tenant_id=tenant_id, is_admin=False) as s:
                r = s.execute(_text(
                    "SELECT id,vendor_id,enabled,ai_manager_phone_number,language_preference,"
                    "default_voice_provider,require_pin_for_level,daily_spend_limit,"
                    "monthly_spend_limit,max_bulk_leads_without_pin,allowed_call_start_time,"
                    "allowed_call_end_time,timezone,created_at,updated_at "
                    "FROM ai_manager_profiles WHERE vendor_id=:org"
                ), {"org": tenant_id}).fetchone()
                return dict(r._mapping) if (r is not None and hasattr(r, "_mapping")) else None
        except Exception as exc:  # noqa: BLE001
            log.info("ai_manager_profiles get failed: %r", exc)
            return None

    def upsert(self, eng, tenant_id: str, fields: dict) -> dict:
        try:
            base = _profile_defaults(tenant_id)
            base.update({k: v for k, v in fields.items() if k in _PROFILE_WRITABLE})
            with eng.session(tenant_id=tenant_id, is_admin=False) as s:
                s.execute(_text(
                    "INSERT INTO ai_manager_profiles (id,vendor_id,enabled,"
                    "ai_manager_phone_number,language_preference,default_voice_provider,"
                    "require_pin_for_level,daily_spend_limit,monthly_spend_limit,"
                    "max_bulk_leads_without_pin,allowed_call_start_time,allowed_call_end_time,"
                    "timezone) VALUES (:id,:org,:en,:ph,:lang,:vp,:rpl,:dsl,:msl,:mbl,:cst,:cet,"
                    ":tz) ON CONFLICT (vendor_id) DO UPDATE SET enabled=:en,"
                    "ai_manager_phone_number=:ph,language_preference=:lang,"
                    "default_voice_provider=:vp,require_pin_for_level=:rpl,daily_spend_limit=:dsl,"
                    "monthly_spend_limit=:msl,max_bulk_leads_without_pin=:mbl,"
                    "allowed_call_start_time=:cst,allowed_call_end_time=:cet,timezone=:tz,"
                    "updated_at=now()"
                ), {"id": base["id"], "org": tenant_id, "en": bool(base["enabled"]),
                    "ph": base["ai_manager_phone_number"], "lang": base["language_preference"],
                    "vp": base["default_voice_provider"], "rpl": int(base["require_pin_for_level"]),
                    "dsl": base["daily_spend_limit"], "msl": base["monthly_spend_limit"],
                    "mbl": int(base["max_bulk_leads_without_pin"]),
                    "cst": base["allowed_call_start_time"], "cet": base["allowed_call_end_time"],
                    "tz": base["timezone"]})
            got = self.get(eng, tenant_id)
            return got or base
        except Exception as exc:  # noqa: BLE001
            log.info("ai_manager_profiles upsert failed: %r", exc)
            return _profile_defaults(tenant_id)


class _PgUsers:
    _SEL = ("SELECT id,vendor_id,user_id,name,phone_number,normalized_phone_number,role,"
            "permissions,is_active,pin_hash,pin_set_at,failed_pin_attempts,locked_until,"
            "created_at,updated_at FROM ai_manager_authorized_users")

    def insert(self, eng, row: dict) -> None:
        try:
            with eng.session(tenant_id=row["vendor_id"], is_admin=False) as s:
                s.execute(_text(
                    "INSERT INTO ai_manager_authorized_users (id,vendor_id,user_id,name,"
                    "phone_number,normalized_phone_number,role,permissions,is_active) VALUES "
                    "(:id,:org,:uid,:nm,:ph,:nph,:role,CAST(:perm AS jsonb),:act) "
                    "ON CONFLICT (id) DO NOTHING"
                ), {"id": row["id"], "org": row["vendor_id"], "uid": row.get("user_id") or None,
                    "nm": row.get("name", ""), "ph": row.get("phone_number", ""),
                    "nph": row.get("normalized_phone_number", ""), "role": row.get("role", "member"),
                    "perm": json.dumps(row.get("permissions", []) or []),
                    "act": bool(row.get("is_active", True))})
        except Exception as exc:  # noqa: BLE001
            log.info("ai_manager_authorized_users insert failed: %r", exc)

    def patch(self, eng, tenant_id: str, user_id: str, fields: dict) -> None:
        if not fields:
            return
        try:
            sets, params = [], {"org": tenant_id, "uid": user_id}
            for i, (k, v) in enumerate(fields.items()):
                p = f"p{i}"
                if k == "permissions":
                    sets.append(f"{k} = CAST(:{p} AS jsonb)")
                    params[p] = json.dumps(v or [])
                else:
                    sets.append(f"{k} = :{p}")
                    params[p] = v
            sets.append("updated_at = now()")
            with eng.session(tenant_id=tenant_id, is_admin=False) as s:
                s.execute(_text(
                    f"UPDATE ai_manager_authorized_users SET {', '.join(sets)} "
                    "WHERE id = :uid AND vendor_id = :org"
                ), params)
        except Exception as exc:  # noqa: BLE001
            log.info("ai_manager_authorized_users patch failed: %r", exc)

    def get(self, eng, tenant_id: str, user_id: str) -> Optional[dict]:
        try:
            with eng.session(tenant_id=tenant_id, is_admin=False) as s:
                r = s.execute(_text(self._SEL + " WHERE id=:uid AND vendor_id=:org"),
                              {"uid": user_id, "org": tenant_id}).fetchone()
                return dict(r._mapping) if (r is not None and hasattr(r, "_mapping")) else None
        except Exception as exc:  # noqa: BLE001
            log.info("ai_manager_authorized_users get failed: %r", exc)
            return None

    def scan(self, eng, tenant_id: str) -> list[dict]:
        try:
            with eng.session(tenant_id=tenant_id, is_admin=False) as s:
                rows = s.execute(_text(
                    self._SEL + " WHERE vendor_id=:org ORDER BY created_at ASC LIMIT 1000"
                ), {"org": tenant_id}).fetchall()
                return [dict(r._mapping) for r in rows if hasattr(r, "_mapping")]
        except Exception as exc:  # noqa: BLE001
            log.info("ai_manager_authorized_users scan failed: %r", exc)
            return []
