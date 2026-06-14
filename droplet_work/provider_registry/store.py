"""provider_registry.store — tenant-scoped reads of the registry tables (W3).

Spec: design/PROVIDER-FRAMEWORK-PLAN.md §4 ("store.py — tenant reads, is_admin=False HARDCODED
(RLS-scoped); list/get/create/update/delete") + §5 (the 3 tables + RLS policies) + §3 (the
strangler: a registry MISS falls back to legacy, so a store read NEVER raises — it returns
[]/None and the caller degrades).

THE RLS DISCIPLINE (mirrors ai_manager/store.py + crm/core.py + ads_engine/store.py): every read
runs inside `db.engine.session(tenant_id=<token-derived tenant>, is_admin=False)`. The GUC is set
`SET LOCAL` INSIDE the txn (engine.session does this), so:
  * provider_definitions: the policy returns the tenant's OWN rows + the platform-shared `_global`
    rows (read-share) — never another tenant's rows.
  * provider_credentials: STRICTLY the tenant's own rows (no `_global` read-share — creds are
    always tenant-private).
  * is_admin is HARDCODED False here — this module is the NON-privileged surface. The super-admin
    surface is admin_store.py (is_admin=True), mounted only under require_super_admin.

NEVER returns a plaintext secret. A credential read returns the ciphertext row (ProviderCred);
the plaintext is produced ONLY by credentials.decrypt_credential behind the get_secret seam.

import-safe: db.engine is imported lazily; if it is absent (local build box) or PG is down,
available() is False and every read returns the empty/None degrade (the live site / video render
falls back to the legacy env path — the strangler guarantee).
"""
from __future__ import annotations

import logging
from typing import Any, List, Optional

from .schema import GLOBAL_TENANT, ProviderCred, ProviderDef

_log = logging.getLogger("provider_registry.store")

# is_admin is HARDCODED False on this surface (§4). The privileged reads live in admin_store.py.
_IS_ADMIN = False


# ---------------------------------------------------------------------------
# engine / availability (mirrors ai_manager/store.py:40-54)
# ---------------------------------------------------------------------------
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


def _query(tenant_id: str, sql: str, params: dict, *, is_admin: bool = _IS_ADMIN) -> List[dict]:
    """Run a SELECT under the tenant GUC; return a list of dict rows (never raises -> [])."""
    if not available():
        return []
    eng = _engine()
    try:
        from sqlalchemy import text
        with eng.session(tenant_id=tenant_id or "", is_admin=is_admin) as s:  # type: ignore
            res = s.execute(text(sql), params)
            cols = list(res.keys())
            return [dict(zip(cols, row)) for row in res.fetchall()]
    except Exception as exc:  # noqa: BLE001 — a read failure degrades to empty (strangler)
        _log.warning("provider_registry.store._query failed: %r", exc)
        return []


# ---------------------------------------------------------------------------
# provider_definitions reads (RLS returns own + `_global`).
# ---------------------------------------------------------------------------
# Column projection — kept explicit so a future column add never changes the read shape silently.
_DEF_COLS = (
    "id, tenant_id, slug, display_name, provider_type, capabilities, base_url, auth_scheme, "
    "auth_header_name, auth_value_tmpl, transform_type, named_provider, request_field_map, "
    "response_field_map, model_default, cost_per_unit_micros, cost_unit, health_check_path, "
    "health_interval_s, priority, rate_limit_rpm, is_enabled, is_platform_default, created_by, "
    "created_at, updated_at"
)


def list_definitions(tenant_id: str, *, capability: str = "", enabled_only: bool = False) -> List[ProviderDef]:
    """List the provider definitions VISIBLE to this tenant (own + `_global`, via RLS), optionally
    filtered to one capability (jsonb containment) and/or enabled. Ordered by priority asc
    (lower priority value = earlier in the fallback chain, §2f), then is_platform_default desc."""
    where = ["1=1"]
    params: dict = {}
    if capability:
        # jsonb @> '["video_gen"]' — the capabilities array contains this capability.
        where.append("capabilities @> CAST(:cap_json AS jsonb)")
        import json as _json
        params["cap_json"] = _json.dumps([capability])
    if enabled_only:
        where.append("is_enabled = true")
    sql = (f"SELECT {_DEF_COLS} FROM provider_definitions WHERE {' AND '.join(where)} "
           "ORDER BY priority ASC, is_platform_default DESC, created_at ASC")
    rows = _query(tenant_id, sql, params)
    return [d for d in (ProviderDef.from_any(r) for r in rows) if d is not None]


def get_definition(tenant_id: str, provider_def_id: str) -> Optional[ProviderDef]:
    """Fetch one definition by id (RLS-scoped: own or `_global`; else None)."""
    if not provider_def_id:
        return None
    sql = f"SELECT {_DEF_COLS} FROM provider_definitions WHERE id = CAST(:id AS uuid) LIMIT 1"
    rows = _query(tenant_id, sql, {"id": str(provider_def_id)})
    return ProviderDef.from_any(rows[0]) if rows else None


def get_definition_by_slug(tenant_id: str, slug: str) -> Optional[ProviderDef]:
    """Fetch one definition by slug (RLS-scoped). Prefers the tenant's OWN row over a `_global`
    row of the same slug (the tenant's override wins)."""
    if not slug:
        return None
    sql = (f"SELECT {_DEF_COLS} FROM provider_definitions WHERE slug = :slug "
           "ORDER BY (tenant_id = :tid) DESC LIMIT 1")
    rows = _query(tenant_id, sql, {"slug": slug, "tid": tenant_id or ""})
    return ProviderDef.from_any(rows[0]) if rows else None


# ---------------------------------------------------------------------------
# provider_credentials reads (STRICTLY tenant-private; no `_global` read-share).
# ---------------------------------------------------------------------------
_CRED_COLS = (
    "id, tenant_id, provider_def_id, ciphertext, wrapped_dek, key_aad, key_version, kek_version, "
    "scope, last_rotated_at, expires_at, is_active, created_at"
)


def get_active_credential(tenant_id: str, provider_def_id: str) -> Optional[ProviderCred]:
    """Fetch the active credential row for (tenant, provider_def). RLS makes this strictly the
    tenant's OWN credential — tenant A can NEVER read tenant B's credential, even for a `_global`
    provider def (creds are always per-tenant). Returns ProviderCred (ciphertext only) or None.

    Returns the HIGHEST key_version active, non-expired credential (rotation-aware)."""
    if not provider_def_id:
        return None
    sql = (f"SELECT {_CRED_COLS} FROM provider_credentials "
           "WHERE provider_def_id = CAST(:id AS uuid) AND is_active = true "
           "AND (expires_at IS NULL OR expires_at > now()) "
           "ORDER BY key_version DESC LIMIT 1")
    rows = _query(tenant_id, sql, {"id": str(provider_def_id)})
    return ProviderCred.from_any(rows[0]) if rows else None


def list_credentials_masked(tenant_id: str) -> List[ProviderCred]:
    """List this tenant's credential rows (ciphertext only — the caller masks for the UI). RLS
    keeps it strictly the tenant's own rows. NEVER decrypts here."""
    sql = (f"SELECT {_CRED_COLS} FROM provider_credentials WHERE is_active = true "
           "ORDER BY created_at DESC")
    rows = _query(tenant_id, sql, {})
    return [c for c in (ProviderCred.from_any(r) for r in rows) if c is not None]


# ---------------------------------------------------------------------------
# WRITES (W4) — create / update / delete provider definitions; upsert a credential;
# append a health-log row. ALL run inside engine.session(tenant_id, is_admin), so:
#   * the RLS WITH-CHECK enforces the §5 anti-privilege-escalation rule (a non-admin tenant
#     can write only its OWN rows and is BLOCKED from inserting a `_global` row);
#   * tenant_id is ALWAYS the token-derived tenant the endpoint passes (NEVER a body field);
#   * a write under is_admin=True (super-admin path) sets app.is_admin='1' so a super-admin may
#     create/edit `_global` platform-shared definitions.
# A write FAILURE raises (so the endpoint maps it to a clean error) — UNLIKE the read path which
# degrades to empty. We deliberately surface write errors (the user must know the create failed),
# but never leak the underlying SQL/secret in the message.
# ---------------------------------------------------------------------------
class StoreWriteError(RuntimeError):
    """A registry write failed (PG down / RLS denied / constraint). Carries NO secret."""


def _exec_write(tenant_id: str, sql: str, params: dict, *, is_admin: bool = _IS_ADMIN,
                returning: bool = False) -> Optional[dict]:
    """Run a write under the tenant (or admin) GUC inside a committed txn. Returns the first
    RETURNING row as a dict when `returning`, else None. Raises StoreWriteError on failure."""
    if not available():
        raise StoreWriteError("registry datastore unavailable")
    eng = _engine()
    try:
        from sqlalchemy import text
        with eng.session(tenant_id=tenant_id or "", is_admin=is_admin) as s:  # type: ignore
            res = s.execute(text(sql), params)
            row = None
            if returning:
                cols = list(res.keys())
                fetched = res.fetchone()
                if fetched is not None:
                    row = dict(zip(cols, fetched))
            return row
    except Exception as exc:  # noqa: BLE001 — surface a write failure (but never the raw secret)
        _log.warning("provider_registry.store._exec_write failed: %r", type(exc).__name__)
        raise StoreWriteError(f"write failed: {type(exc).__name__}") from exc


# Columns a tenant/admin may set on create/update (a curated whitelist — never the id/timestamps,
# never a raw secret; credentials live in the separate provider_credentials table).
_DEF_WRITE_COLS = (
    "slug", "display_name", "provider_type", "capabilities", "base_url", "auth_scheme",
    "auth_header_name", "auth_value_tmpl", "transform_type", "named_provider",
    "request_field_map", "response_field_map", "model_default", "cost_per_unit_micros",
    "cost_unit", "health_check_path", "health_interval_s", "priority", "rate_limit_rpm",
    "is_enabled", "is_platform_default",
)
# jsonb columns must be CAST so a Python dict/list binds correctly.
_DEF_JSONB_COLS = {"capabilities", "request_field_map", "response_field_map"}


def _coerce_def_value(col: str, value):
    """Normalize a write value: enums -> their string; jsonb dict/list -> JSON text."""
    if hasattr(value, "value"):  # an enum member
        value = value.value
    if col in _DEF_JSONB_COLS:
        import json as _json
        if value is None:
            return None
        return _json.dumps(value)
    return value


def create_definition(tenant_id: str, fields: dict, *, created_by: str = "",
                      is_admin: bool = _IS_ADMIN) -> Optional[dict]:
    """INSERT a provider definition owned by `tenant_id` (the token-derived owner, or `_global`
    only on the super-admin is_admin=True path — RLS WITH CHECK enforces this). Returns the new
    row (the projected _DEF_COLS). Raises StoreWriteError on RLS-denied / constraint / PG-down."""
    cols, placeholders, params = [], [], {}
    for c in _DEF_WRITE_COLS:
        if c in fields:
            cols.append(c)
            placeholders.append(f"CAST(:{c} AS jsonb)" if c in _DEF_JSONB_COLS else f":{c}")
            params[c] = _coerce_def_value(c, fields[c])
    # tenant_id + created_by are server-set (never from the body whitelist).
    cols = ["tenant_id", "created_by"] + cols
    placeholders = [":_tid", ":_cby"] + placeholders
    params["_tid"] = tenant_id or ""
    params["_cby"] = created_by or ""
    sql = (f"INSERT INTO provider_definitions ({', '.join(cols)}) "
           f"VALUES ({', '.join(placeholders)}) RETURNING {_DEF_COLS}")
    return _exec_write(tenant_id, sql, params, is_admin=is_admin, returning=True)


def update_definition(tenant_id: str, provider_def_id: str, fields: dict,
                      *, is_admin: bool = _IS_ADMIN) -> Optional[dict]:
    """UPDATE a definition the tenant owns (RLS scopes the row; `_global` only via is_admin=True).
    Only whitelisted columns are settable. Returns the updated row, or None if no row matched
    (RLS-invisible / wrong owner). Raises StoreWriteError on failure."""
    sets, params = [], {"_id": str(provider_def_id)}
    for c in _DEF_WRITE_COLS:
        if c in fields:
            if c in _DEF_JSONB_COLS:
                sets.append(f"{c} = CAST(:{c} AS jsonb)")
            else:
                sets.append(f"{c} = :{c}")
            params[c] = _coerce_def_value(c, fields[c])
    if not sets:
        # nothing whitelisted to change — return the current row unchanged (no-op, not an error).
        cur = get_definition(tenant_id, provider_def_id)
        return cur.__dict__ if cur is not None else None
    sets.append("updated_at = now()")
    sql = (f"UPDATE provider_definitions SET {', '.join(sets)} "
           f"WHERE id = CAST(:_id AS uuid) RETURNING {_DEF_COLS}")
    return _exec_write(tenant_id, sql, params, is_admin=is_admin, returning=True)


def delete_definition(tenant_id: str, provider_def_id: str, *, is_admin: bool = _IS_ADMIN) -> bool:
    """DELETE a definition the tenant owns (cascades its credentials + health rows via FK).
    Returns True if a row was deleted (RLS made it visible + owned), False otherwise."""
    sql = ("DELETE FROM provider_definitions WHERE id = CAST(:_id AS uuid) "
           "RETURNING id")
    row = _exec_write(tenant_id, sql, {"_id": str(provider_def_id)}, is_admin=is_admin,
                      returning=True)
    return row is not None


def upsert_credential(tenant_id: str, provider_def_id: str, enc: dict, *, scope: str = "integration",
                     expires_at=None, is_admin: bool = _IS_ADMIN) -> Optional[dict]:
    """Store an encrypted credential for (tenant, provider_def). `enc` is the dict returned by
    credentials.encrypt_credential ({ciphertext, key_aad, key_version}). Deactivates any prior
    active rows for this (tenant, def) then inserts the new active one (rotation-aware). RLS keeps
    the write strictly tenant-private. Returns the new credential row metadata (NO ciphertext echo).
    Raises StoreWriteError on failure."""
    kv = int(enc.get("key_version", 1) or 1)
    # deactivate prior active versions (rotation), then insert the new active row, in ONE txn.
    sql = (
        "WITH deact AS ("
        "  UPDATE provider_credentials SET is_active = false "
        "  WHERE provider_def_id = CAST(:_pdid AS uuid) AND is_active = true "
        "  RETURNING 1"
        ") "
        "INSERT INTO provider_credentials "
        "  (tenant_id, provider_def_id, ciphertext, key_aad, key_version, scope, expires_at, "
        "   is_active, last_rotated_at) "
        "VALUES (:_tid, CAST(:_pdid AS uuid), :_ct, :_aad, :_kv, :_scope, :_exp, true, now()) "
        "RETURNING id, tenant_id, provider_def_id, key_version, scope, is_active, created_at"
    )
    params = {
        "_tid": tenant_id or "", "_pdid": str(provider_def_id), "_ct": enc.get("ciphertext"),
        "_aad": enc.get("key_aad", ""), "_kv": kv, "_scope": scope, "_exp": expires_at,
    }
    return _exec_write(tenant_id, sql, params, is_admin=is_admin, returning=True)


def write_health_row(tenant_id: str, provider_def_id: str, is_healthy: bool,
                    latency_ms: int = 0, error_code: str = "",
                    *, is_admin: bool = _IS_ADMIN) -> None:
    """Append a health-log row (best-effort; append-only table). Swallows failure (the in-memory
    breaker is the source of truth — §2f). NEVER raises into the caller."""
    if not available():
        return
    sql = ("INSERT INTO provider_health_log "
           "  (tenant_id, provider_def_id, is_healthy, latency_ms, error_code) "
           "VALUES (:_tid, CAST(:_pdid AS uuid), :_h, :_lat, :_err)")
    params = {"_tid": tenant_id or "", "_pdid": str(provider_def_id),
              "_h": bool(is_healthy), "_lat": int(latency_ms or 0), "_err": (error_code or "")[:200]}
    try:
        _exec_write(tenant_id, sql, params, is_admin=is_admin, returning=False)
    except Exception:  # noqa: BLE001 — best-effort log; never affects the breaker/caller
        pass


def status() -> dict:
    """Diagnostic — never echoes a secret."""
    return {"pg_available": available(), "surface": "tenant", "is_admin": _IS_ADMIN}
