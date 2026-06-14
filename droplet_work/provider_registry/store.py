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


def status() -> dict:
    """Diagnostic — never echoes a secret."""
    return {"pg_available": available(), "surface": "tenant", "is_admin": _IS_ADMIN}
