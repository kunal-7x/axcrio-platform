"""provider_registry.admin_store — the SUPER-ADMIN (is_admin=True) read surface (W3).

Spec: design/PROVIDER-FRAMEWORK-PLAN.md §4 ("admin_store.py — super-admin reads (is_admin=True),
mounted ONLY under require_super_admin") + §5 (the `current_setting('app.is_admin')='1'` RLS leg)
+ §6 (legacy-pw exclusion + super-admin reveal of any scope).

This surface runs db.engine.session(is_admin=True), which sets `SET LOCAL app.is_admin='1'` —
satisfying the admin leg of every RLS policy, so a super-admin can read ANY tenant's definitions,
the `_global` rows, and (for the audited reveal path) any tenant's credential ciphertext. It is
the ONLY module that passes is_admin=True; it MUST be mounted exclusively behind
`require_super_admin` in caller.py (W4) — never on a tenant route. The legacy static-password
bearer is excluded from /admin/providers/* at the route layer (§6, control-security #1), NOT here.

Same import-safe / never-raises / degrade-to-empty discipline as store.py. NEVER returns plaintext
(the reveal endpoint decrypts via credentials.decrypt_credential behind the get_secret seam, then
audits + returns once — admin_store only fetches the ciphertext row).
"""
from __future__ import annotations

import logging
from typing import List, Optional

from . import store as _tenant_store
from .schema import ProviderCred, ProviderDef

_log = logging.getLogger("provider_registry.admin_store")

_IS_ADMIN = True


def available() -> bool:
    return _tenant_store.available()


def _admin_query(sql: str, params: dict) -> List[dict]:
    """Run a SELECT under the ADMIN GUC (is_admin=True). tenant_id is "" — the admin leg of the
    policy (`app.is_admin='1'`) authorizes the read regardless of tenant. Never raises -> []."""
    if not available():
        return []
    eng = _tenant_store._engine()
    try:
        from sqlalchemy import text
        with eng.session(tenant_id="", is_admin=_IS_ADMIN) as s:  # type: ignore
            res = s.execute(text(sql), params)
            cols = list(res.keys())
            return [dict(zip(cols, row)) for row in res.fetchall()]
    except Exception as exc:  # noqa: BLE001
        _log.warning("provider_registry.admin_store._admin_query failed: %r", exc)
        return []


def list_all_definitions(*, capability: str = "", tenant_id: str = "") -> List[ProviderDef]:
    """List provider definitions ACROSS all tenants (+ `_global`) for the super-admin console.
    Optional filters: a capability (jsonb containment) and/or a specific owning tenant_id."""
    where = ["1=1"]
    params: dict = {}
    if capability:
        import json as _json
        where.append("capabilities @> CAST(:cap_json AS jsonb)")
        params["cap_json"] = _json.dumps([capability])
    if tenant_id:
        where.append("tenant_id = :owner")
        params["owner"] = tenant_id
    sql = (f"SELECT {_tenant_store._DEF_COLS} FROM provider_definitions "
           f"WHERE {' AND '.join(where)} ORDER BY tenant_id, priority ASC, created_at ASC")
    rows = _admin_query(sql, params)
    return [d for d in (ProviderDef.from_any(r) for r in rows) if d is not None]


def get_any_definition(provider_def_id: str) -> Optional[ProviderDef]:
    """Fetch any definition by id (admin GUC — any tenant or `_global`)."""
    if not provider_def_id:
        return None
    sql = f"SELECT {_tenant_store._DEF_COLS} FROM provider_definitions WHERE id = CAST(:id AS uuid) LIMIT 1"
    rows = _admin_query(sql, {"id": str(provider_def_id)})
    return ProviderDef.from_any(rows[0]) if rows else None


def get_any_credential(provider_def_id: str, *, owner_tenant_id: str = "") -> Optional[ProviderCred]:
    """Fetch a credential ciphertext row for the AUDITED super-admin reveal/rotate path (any
    tenant). `owner_tenant_id` narrows to one owner when supplied (the usual case: reveal a
    specific tenant's key). NEVER decrypts here — the endpoint decrypts behind the seam, then
    audits + returns once. Returns the highest active key_version."""
    if not provider_def_id:
        return None
    where = ["provider_def_id = CAST(:id AS uuid)", "is_active = true"]
    params: dict = {"id": str(provider_def_id)}
    if owner_tenant_id:
        where.append("tenant_id = :owner")
        params["owner"] = owner_tenant_id
    sql = (f"SELECT {_tenant_store._CRED_COLS} FROM provider_credentials "
           f"WHERE {' AND '.join(where)} ORDER BY key_version DESC LIMIT 1")
    rows = _admin_query(sql, params)
    return ProviderCred.from_any(rows[0]) if rows else None


def status() -> dict:
    return {"pg_available": available(), "surface": "super_admin", "is_admin": _IS_ADMIN}
