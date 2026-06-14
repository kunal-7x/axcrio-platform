"""trunk_registry.store — tenant-scoped reads/writes of the trunk tables (T2).

Spec: design/TELEPHONY-INDEPENDENCE-PLAN.md §2.1 (store.py / admin_store.py — RLS reads/writes
for sip_trunks/credentials; is_admin=False tenant path) + §2.2 (the 3 tables + RLS policies) +
§3 (red-team B1: the campaign gate is a DB-derived column the store FILTERS on, not prose; D:
soft-disable, the un-deletable trigger is the DB backstop).

A column-for-column TWIN of provider_registry/store.py with the sip_trunks columns. Same RLS
discipline: every read/write runs inside `db.engine.session(tenant_id=<token-derived>,
is_admin=False)`; the GUC is SET LOCAL inside the txn so:
  * sip_trunks: the policy returns the tenant's OWN rows + the shared `_global` rows (so flag-on
    dials the live Vobiz trunk) — never another tenant's rows.
  * sip_trunk_credentials / sip_trunk_health_log: STRICTLY the tenant's own rows (no `_global`
    read-share — SIP passwords + health are tenant-private).
  * is_admin is HARDCODED False here (the NON-privileged surface). The super-admin surface is
    admin_store.py (is_admin=True), mounted only under require_super_admin.

NEVER returns a plaintext SIP password. A credential read returns the ciphertext row
(SipTrunkCred); the plaintext is produced ONLY by credentials.decrypt_credential behind the
get_secret seam.

import-safe: db.engine is imported lazily; if it is absent (local build box) or PG is down,
available() is False and every read returns the empty/None degrade — the dial loop falls back
to the legacy `TRUNK` env path (the strangler guarantee, flag OFF anyway).
"""
from __future__ import annotations

import logging
from typing import Any, List, Optional

from .schema import GLOBAL_TENANT, SipTrunk, SipTrunkCred  # noqa: F401

_log = logging.getLogger("trunk_registry.store")

# is_admin is HARDCODED False on this surface. The privileged reads live in admin_store.py.
_IS_ADMIN = False


# ---------------------------------------------------------------------------
# engine / availability (mirrors provider_registry/store.py).
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
        _log.warning("trunk_registry.store._query failed: %r", exc)
        return []


# ---------------------------------------------------------------------------
# sip_trunks reads (RLS returns own + `_global`).
# Explicit projection — a future column add never silently changes the read shape.
# ---------------------------------------------------------------------------
_TRUNK_COLS = (
    "id, tenant_id, slug, display_name, trunk_type, provider_vendor, direction, "
    "sip_host, sip_port, transport, encryption, auth_username, allowed_addresses, did_pool, "
    "caller_id, max_concurrency, cost_per_minute_paise, is_140_series, dlt_entity_id, "
    "dlt_status, per_did_daily_cap, priority, rotation_strategy, is_enabled, is_test_verified, "
    "quarantined_until, is_undeletable, livekit_trunk_id, is_campaign_eligible, created_by, "
    "created_at, updated_at"
)


def list_trunks(tenant_id: str, *, direction: str = "", enabled_only: bool = False,
                campaign_eligible_only: bool = False,
                exclude_quarantined: bool = False) -> List[SipTrunk]:
    """List the trunks VISIBLE to this tenant (own + `_global`, via RLS), optionally filtered.

      * direction              -> 'outbound' | 'inbound' | 'both' (a 'both' row matches either).
      * enabled_only           -> is_enabled = true.
      * campaign_eligible_only -> RED-TEAM B1: is_campaign_eligible = true (the DB-derived gate;
                                  a campaign dial filters on THIS, never on prose/UI).
      * exclude_quarantined    -> quarantined_until IS NULL OR < now() (spam-rest, §2.5).
    Ordered by priority asc (lower = earlier in the selection/fallback chain), then created_at."""
    where = ["1=1"]
    params: dict = {}
    if direction:
        where.append("(direction = :dir OR direction = 'both')")
        params["dir"] = direction
    if enabled_only:
        where.append("is_enabled = true")
    if campaign_eligible_only:
        where.append("is_campaign_eligible = true")
    if exclude_quarantined:
        where.append("(quarantined_until IS NULL OR quarantined_until < now())")
    sql = (f"SELECT {_TRUNK_COLS} FROM sip_trunks WHERE {' AND '.join(where)} "
           "ORDER BY priority ASC, created_at ASC")
    rows = _query(tenant_id, sql, params)
    return [t for t in (SipTrunk.from_any(r) for r in rows) if t is not None]


def get_trunk(tenant_id: str, trunk_id: str) -> Optional[SipTrunk]:
    """Fetch one trunk by id (RLS-scoped: own or `_global`; else None)."""
    if not trunk_id:
        return None
    sql = f"SELECT {_TRUNK_COLS} FROM sip_trunks WHERE id = CAST(:id AS uuid) LIMIT 1"
    rows = _query(tenant_id, sql, {"id": str(trunk_id)})
    return SipTrunk.from_any(rows[0]) if rows else None


def get_trunk_by_slug(tenant_id: str, slug: str) -> Optional[SipTrunk]:
    """Fetch one trunk by slug (RLS-scoped). Prefers the tenant's OWN row over a `_global` row
    of the same slug (the tenant's override wins)."""
    if not slug:
        return None
    sql = (f"SELECT {_TRUNK_COLS} FROM sip_trunks WHERE slug = :slug "
           "ORDER BY (tenant_id = :tid) DESC LIMIT 1")
    rows = _query(tenant_id, sql, {"slug": slug, "tid": tenant_id or ""})
    return SipTrunk.from_any(rows[0]) if rows else None


# ---------------------------------------------------------------------------
# sip_trunk_credentials reads (STRICTLY tenant-private; no `_global` read-share).
# ---------------------------------------------------------------------------
_CRED_COLS = (
    "id, tenant_id, trunk_id, ciphertext, wrapped_dek, key_aad, key_version, kek_version, "
    "scope, last_rotated_at, expires_at, is_active, created_at"
)


def get_active_credential(tenant_id: str, trunk_id: str) -> Optional[SipTrunkCred]:
    """Fetch the active SIP credential row for (tenant, trunk). RLS makes this strictly the
    tenant's OWN credential — A can NEVER read B's SIP password, even for a `_global` trunk.
    Returns the highest active, non-expired key_version (rotation-aware) or None."""
    if not trunk_id:
        return None
    sql = (f"SELECT {_CRED_COLS} FROM sip_trunk_credentials "
           "WHERE trunk_id = CAST(:id AS uuid) AND is_active = true "
           "AND (expires_at IS NULL OR expires_at > now()) "
           "ORDER BY key_version DESC LIMIT 1")
    rows = _query(tenant_id, sql, {"id": str(trunk_id)})
    return SipTrunkCred.from_any(rows[0]) if rows else None


def list_credentials_masked(tenant_id: str) -> List[SipTrunkCred]:
    """List this tenant's credential rows (ciphertext only — the caller masks for the UI). RLS
    keeps it strictly the tenant's own rows. NEVER decrypts here."""
    sql = (f"SELECT {_CRED_COLS} FROM sip_trunk_credentials WHERE is_active = true "
           "ORDER BY created_at DESC")
    rows = _query(tenant_id, sql, {})
    return [c for c in (SipTrunkCred.from_any(r) for r in rows) if c is not None]


# ---------------------------------------------------------------------------
# sip_trunk_health_log reads (per-DID reputation; append-only — writes go via write_health_row).
# ---------------------------------------------------------------------------
def recent_did_ringouts(tenant_id: str, trunk_id: str, did: str, window_s: int) -> int:
    """Count zero-duration ring-out events for a DID within the last `window_s` seconds. This is
    the spam-reputation signal (red-team B-rel): caller.py never captures the 486, so the burst
    of zero-duration ring-outs IS the detectable pattern. RLS-scoped to the tenant's own rows."""
    if not trunk_id:
        return 0
    sql = ("SELECT count(*) AS n FROM sip_trunk_health_log "
           "WHERE trunk_id = CAST(:id AS uuid) AND event = 'ring_out' "
           "AND (:did = '' OR did = :did) "
           "AND checked_at > now() - make_interval(secs => :win)")
    rows = _query(tenant_id, sql, {"id": str(trunk_id), "did": did or "", "win": int(window_s)})
    return int(rows[0]["n"]) if rows else 0


def count_trunk_quarantines(tenant_id: str, trunk_id: str, window_s: int) -> int:
    """Count 'quarantine' events on a trunk within the window — the escalation signal (red-team
    B3): >= K quarantines -> the trunk is DISABLED + alerted, not silently rotated past."""
    if not trunk_id:
        return 0
    sql = ("SELECT count(*) AS n FROM sip_trunk_health_log "
           "WHERE trunk_id = CAST(:id AS uuid) AND event = 'quarantine' "
           "AND checked_at > now() - make_interval(secs => :win)")
    rows = _query(tenant_id, sql, {"id": str(trunk_id), "win": int(window_s)})
    return int(rows[0]["n"]) if rows else 0


# ---------------------------------------------------------------------------
# WRITES — create / update / soft-disable a trunk; upsert a credential; quarantine; append a
# health row. ALL run inside engine.session(tenant_id, is_admin), so the RLS WITH-CHECK enforces
# the §2.2 anti-privilege-escalation rule (a non-admin tenant can write only its OWN rows,
# BLOCKED from inserting/updating a `_global` row). tenant_id is ALWAYS token-derived, never a
# body field. A write FAILURE raises (the endpoint maps it to a clean error); the read path
# degrades to empty.
# ---------------------------------------------------------------------------
class StoreWriteError(RuntimeError):
    """A registry write failed (PG down / RLS denied / constraint / un-deletable trigger).
    Carries NO secret."""


def _exec_write(tenant_id: str, sql: str, params: dict, *, is_admin: bool = _IS_ADMIN,
                returning: bool = False) -> Optional[dict]:
    if not available():
        raise StoreWriteError("trunk registry datastore unavailable")
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
    except Exception as exc:  # noqa: BLE001 — surface a write failure (never the raw secret)
        _log.warning("trunk_registry.store._exec_write failed: %r", type(exc).__name__)
        raise StoreWriteError(f"write failed: {type(exc).__name__}") from exc


# Columns a tenant/admin may set on create/update (curated whitelist — NEVER id/timestamps,
# NEVER is_campaign_eligible (it is a GENERATED column), NEVER a raw secret; the SIP password
# lives in sip_trunk_credentials). is_undeletable is admin/seed-only and intentionally NOT here.
_TRUNK_WRITE_COLS = (
    "slug", "display_name", "trunk_type", "provider_vendor", "direction", "sip_host", "sip_port",
    "transport", "encryption", "auth_username", "allowed_addresses", "did_pool", "caller_id",
    "max_concurrency", "cost_per_minute_paise", "is_140_series", "dlt_entity_id", "dlt_status",
    "per_did_daily_cap", "priority", "rotation_strategy", "is_enabled", "is_test_verified",
    "livekit_trunk_id",
)
_TRUNK_JSONB_COLS = {"allowed_addresses", "did_pool"}


def _coerce_trunk_value(col: str, value):
    if hasattr(value, "value"):  # an enum member
        value = value.value
    if col in _TRUNK_JSONB_COLS:
        import json as _json
        if value is None:
            return None
        return _json.dumps(value)
    return value


def create_trunk(tenant_id: str, fields: dict, *, created_by: str = "",
                 is_admin: bool = _IS_ADMIN) -> Optional[dict]:
    """INSERT a trunk owned by `tenant_id` (or `_global` only on the super-admin is_admin=True
    path — RLS WITH CHECK enforces this). is_campaign_eligible is DB-derived (never set here).
    Raises StoreWriteError on RLS-denied / constraint / PG-down."""
    cols, placeholders, params = [], [], {}
    for c in _TRUNK_WRITE_COLS:
        if c in fields:
            cols.append(c)
            placeholders.append(f"CAST(:{c} AS jsonb)" if c in _TRUNK_JSONB_COLS else f":{c}")
            params[c] = _coerce_trunk_value(c, fields[c])
    cols = ["tenant_id", "created_by"] + cols
    placeholders = [":_tid", ":_cby"] + placeholders
    params["_tid"] = tenant_id or ""
    params["_cby"] = created_by or ""
    sql = (f"INSERT INTO sip_trunks ({', '.join(cols)}) "
           f"VALUES ({', '.join(placeholders)}) RETURNING {_TRUNK_COLS}")
    return _exec_write(tenant_id, sql, params, is_admin=is_admin, returning=True)


def update_trunk(tenant_id: str, trunk_id: str, fields: dict,
                 *, is_admin: bool = _IS_ADMIN) -> Optional[dict]:
    """UPDATE a trunk the tenant owns (RLS scopes the row; `_global` only via is_admin=True).
    Only whitelisted columns are settable. Returns the updated row, or None if no row matched."""
    sets, params = [], {"_id": str(trunk_id)}
    for c in _TRUNK_WRITE_COLS:
        if c in fields:
            if c in _TRUNK_JSONB_COLS:
                sets.append(f"{c} = CAST(:{c} AS jsonb)")
            else:
                sets.append(f"{c} = :{c}")
            params[c] = _coerce_trunk_value(c, fields[c])
    if not sets:
        cur = get_trunk(tenant_id, trunk_id)
        return cur.__dict__ if cur is not None else None
    sets.append("updated_at = now()")
    sql = (f"UPDATE sip_trunks SET {', '.join(sets)} "
           f"WHERE id = CAST(:_id AS uuid) RETURNING {_TRUNK_COLS}")
    return _exec_write(tenant_id, sql, params, is_admin=is_admin, returning=True)


def soft_disable_trunk(tenant_id: str, trunk_id: str, *, is_admin: bool = _IS_ADMIN) -> Optional[dict]:
    """Set is_enabled=false (the DEFAULT 'delete' — red-team D). Works on any trunk, including an
    un-deletable `_global` one (the un-deletable trigger blocks DELETE, NOT this disable)."""
    return update_trunk(tenant_id, trunk_id, {"is_enabled": False}, is_admin=is_admin)


def set_quarantine(tenant_id: str, trunk_id: str, until_iso, *,
                   is_admin: bool = _IS_ADMIN) -> Optional[dict]:
    """Set quarantined_until (spam-rest, §2.5). `until_iso` is a timestamptz value / ISO string;
    None releases the quarantine. NOT in the write whitelist on purpose (it is a system action,
    not a user field) — so it has its own dedicated, audited write path here."""
    sql = ("UPDATE sip_trunks SET quarantined_until = :_q, updated_at = now() "
           "WHERE id = CAST(:_id AS uuid) RETURNING id, slug, quarantined_until, is_enabled")
    return _exec_write(tenant_id, sql, {"_id": str(trunk_id), "_q": until_iso},
                       is_admin=is_admin, returning=True)


def delete_trunk(tenant_id: str, trunk_id: str, *, is_admin: bool = _IS_ADMIN) -> bool:
    """HARD-DELETE a trunk (cascades creds + health via FK). The DB trigger REFUSES a delete of
    an is_undeletable row (red-team D) — that raises StoreWriteError, which the caller surfaces.
    The package DEFAULT for the UI 'remove' action is soft_disable_trunk, NOT this; a genuine
    hard-delete is PIN-gated + audited at the endpoint layer (T3). Returns True iff a row went."""
    sql = "DELETE FROM sip_trunks WHERE id = CAST(:_id AS uuid) RETURNING id"
    row = _exec_write(tenant_id, sql, {"_id": str(trunk_id)}, is_admin=is_admin, returning=True)
    return row is not None


def upsert_credential(tenant_id: str, trunk_id: str, enc: dict, *, scope: str = "integration",
                      expires_at=None, is_admin: bool = _IS_ADMIN) -> Optional[dict]:
    """Store an encrypted SIP password for (tenant, trunk). `enc` is the dict from
    credentials.encrypt_credential ({ciphertext, key_aad, key_version}). Deactivates any prior
    active rows for this (tenant, trunk) then inserts the new active one (rotation-aware). RLS
    keeps the write strictly tenant-private. Returns metadata (NO ciphertext echo)."""
    kv = int(enc.get("key_version", 1) or 1)
    sql = (
        "WITH deact AS ("
        "  UPDATE sip_trunk_credentials SET is_active = false "
        "  WHERE trunk_id = CAST(:_tid_trunk AS uuid) AND is_active = true "
        "  RETURNING 1"
        ") "
        "INSERT INTO sip_trunk_credentials "
        "  (tenant_id, trunk_id, ciphertext, key_aad, key_version, scope, expires_at, "
        "   is_active, last_rotated_at) "
        "VALUES (:_tid, CAST(:_tid_trunk AS uuid), :_ct, :_aad, :_kv, :_scope, :_exp, true, now()) "
        "RETURNING id, tenant_id, trunk_id, key_version, scope, is_active, created_at"
    )
    params = {
        "_tid": tenant_id or "", "_tid_trunk": str(trunk_id), "_ct": enc.get("ciphertext"),
        "_aad": enc.get("key_aad", ""), "_kv": kv, "_scope": scope, "_exp": expires_at,
    }
    return _exec_write(tenant_id, sql, params, is_admin=is_admin, returning=True)


def write_health_row(tenant_id: str, trunk_id: str, *, event: str = "probe",
                     did: str = "", is_healthy: Optional[bool] = None, sip_code: Optional[int] = None,
                     latency_ms: int = 0, error_code: str = "",
                     is_admin: bool = _IS_ADMIN) -> None:
    """Append a per-DID health/reputation row (best-effort; append-only table). Swallows failure
    (the in-memory breaker + the quarantine column are the sources of truth). NEVER raises."""
    if not available():
        return
    sql = ("INSERT INTO sip_trunk_health_log "
           "  (tenant_id, trunk_id, did, event, is_healthy, sip_code, latency_ms, error_code) "
           "VALUES (:_tid, CAST(:_trunk AS uuid), :_did, :_event, :_h, :_sip, :_lat, :_err)")
    params = {"_tid": tenant_id or "", "_trunk": str(trunk_id), "_did": (did or "") or None,
              "_event": event, "_h": is_healthy, "_sip": sip_code,
              "_lat": int(latency_ms or 0), "_err": (error_code or "")[:200]}
    try:
        _exec_write(tenant_id, sql, params, is_admin=is_admin, returning=False)
    except Exception:  # noqa: BLE001 — best-effort log; never affects the caller
        pass


def status() -> dict:
    return {"pg_available": available(), "surface": "tenant", "is_admin": _IS_ADMIN}
