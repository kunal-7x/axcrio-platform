"""trunk_registry.admin_store — the SUPER-ADMIN (is_admin=True) read surface (T2).

Spec: design/TELEPHONY-INDEPENDENCE-PLAN.md §2.1 (admin_store.py — super-admin path) + §2.2
(the `current_setting('app.is_admin')='1'` RLS leg) + §3 (red-team D: a super-admin can manage
the `_global` Vobiz trunk — soft-disable, set DLT fields — but the DB trigger STILL refuses a
DELETE of the un-deletable row even under the admin GUC).

A column-for-column TWIN of provider_registry/admin_store.py. Runs
db.engine.session(is_admin=True) -> `SET LOCAL app.is_admin='1'`, satisfying the admin leg of
every RLS policy, so a super-admin can read ANY tenant's trunks, the `_global` rows, and (for
the audited reveal path) any tenant's SIP-credential ciphertext. It is the ONLY module that
passes is_admin=True; it MUST be mounted exclusively behind `require_super_admin` in caller.py
(T3). The legacy static-password bearer is excluded from /trunk-registry/* at the route layer
(control-security #1), NOT here.

Same import-safe / never-raises / degrade-to-empty discipline as store.py. NEVER returns
plaintext (the reveal endpoint decrypts via credentials.decrypt_credential behind the seam,
then audits + returns once — admin_store only fetches the ciphertext row).
"""
from __future__ import annotations

import logging
from typing import List, Optional

from . import store as _tenant_store
from .schema import SipTrunk, SipTrunkCred

_log = logging.getLogger("trunk_registry.admin_store")

_IS_ADMIN = True


def available() -> bool:
    return _tenant_store.available()


def _admin_query(sql: str, params: dict) -> List[dict]:
    """Run a SELECT under the ADMIN GUC (is_admin=True). tenant_id is "" — the admin leg of the
    policy authorizes the read regardless of tenant. Never raises -> []."""
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
        _log.warning("trunk_registry.admin_store._admin_query failed: %r", exc)
        return []


def list_all_trunks(*, direction: str = "", tenant_id: str = "") -> List[SipTrunk]:
    """List trunks ACROSS all tenants (+ `_global`) for the super-admin console."""
    where = ["1=1"]
    params: dict = {}
    if direction:
        where.append("(direction = :dir OR direction = 'both')")
        params["dir"] = direction
    if tenant_id:
        where.append("tenant_id = :owner")
        params["owner"] = tenant_id
    sql = (f"SELECT {_tenant_store._TRUNK_COLS} FROM sip_trunks "
           f"WHERE {' AND '.join(where)} ORDER BY tenant_id, priority ASC, created_at ASC")
    rows = _admin_query(sql, params)
    return [t for t in (SipTrunk.from_any(r) for r in rows) if t is not None]


def get_any_trunk(trunk_id: str) -> Optional[SipTrunk]:
    """Fetch any trunk by id (admin GUC — any tenant or `_global`)."""
    if not trunk_id:
        return None
    sql = f"SELECT {_tenant_store._TRUNK_COLS} FROM sip_trunks WHERE id = CAST(:id AS uuid) LIMIT 1"
    rows = _admin_query(sql, {"id": str(trunk_id)})
    return SipTrunk.from_any(rows[0]) if rows else None


def get_any_credential(trunk_id: str, *, owner_tenant_id: str = "") -> Optional[SipTrunkCred]:
    """Fetch a SIP-credential ciphertext row for the AUDITED super-admin reveal/rotate path (any
    tenant). `owner_tenant_id` narrows to one owner when supplied. NEVER decrypts here — the
    endpoint decrypts behind the seam, then audits + returns once. Highest active key_version."""
    if not trunk_id:
        return None
    where = ["trunk_id = CAST(:id AS uuid)", "is_active = true"]
    params: dict = {"id": str(trunk_id)}
    if owner_tenant_id:
        where.append("tenant_id = :owner")
        params["owner"] = owner_tenant_id
    sql = (f"SELECT {_tenant_store._CRED_COLS} FROM sip_trunk_credentials "
           f"WHERE {' AND '.join(where)} ORDER BY key_version DESC LIMIT 1")
    rows = _admin_query(sql, params)
    return SipTrunkCred.from_any(rows[0]) if rows else None


def status() -> dict:
    return {"pg_available": available(), "surface": "super_admin", "is_admin": _IS_ADMIN}
