"""ads_engine.store_pg — the Postgres FORCE-RLS backend behind store.py's accessor API (V2 W2).

This is the STRANGLER backend: it implements the SAME generic storage primitives store.py's
public accessors call (get_collection / put_row / delete_row / cas_row / list_tenant_ids /
get_tenant_file / append_tenant_row / put_tenant_file / page-map), so NOTHING else in ads_engine
changes. Selected by `ADS_STORE_BACKEND=postgres` (default `json` => this module is never touched
=> resting behavior byte-identical).

ISOLATION IS INFRASTRUCTURAL HERE (the whole reason W2 exists): every read/write runs inside a
transaction that does `set_config('app.tenant_id', <tenant>, true)` (SET LOCAL), and the tables in
db/ddl_ads_engine.sql are FORCE ROW LEVEL SECURITY. So:
  * a cross-tenant SELECT returns 0 rows (the USING policy filters by the GUC), and
  * a forged tenant_id write is blocked by the WITH CHECK policy (column tenant_id MUST equal the
    GUC) — on TOP of store.py server-stamping the tenant_id. Two independent guards.

ENGINE: prefers the box's pooled `db.engine` (the same engine provider_registry uses) when present;
otherwise builds a self-contained psycopg3 engine from `ADS_PG_DSN` (or `DATABASE_URL`). Both expose
the identical `session(tenant_id, is_admin)` transaction contract. import-cheap + crash-proof: this
module imports NO driver at module load (psycopg is imported lazily inside the engine), so importing
it on a box without psycopg never crashes the live caller spine.

`VersionConflict` / `PageOwnershipConflict` are imported FROM store.py so the exception identity is
shared (a caller's `except store.VersionConflict` catches a PG conflict too).
"""

from __future__ import annotations

import logging
import os
import threading
from contextlib import contextmanager
from typing import Any, Iterator, Optional

_log = logging.getLogger("ads_engine.store_pg")


# ---------------------------------------------------------------------------
# Engine — box pooled engine first, self-contained psycopg3 fallback second.
# Both provide: .available() -> bool ; .session(tenant_id, is_admin) -> ctx(conn).
# ---------------------------------------------------------------------------
def _box_engine():
    """The live box's shared engine (db.engine), or None when absent (this worktree / no PG)."""
    try:
        from db import engine  # type: ignore
        return engine
    except Exception:  # noqa: BLE001
        return None


class _LocalEngine:
    """Self-contained psycopg3 engine used when db.engine is absent (tests / standalone).

    A single lazily-opened connection (autocommit OFF) guarded by a lock — sufficient for the
    detached single-process ads tick + the offline smokes. `session()` opens a txn, sets the
    RLS GUCs LOCAL to that txn (so they reset on commit), yields the connection, and commits;
    any error rolls back. A dropped connection is transparently reopened on the next session.
    """

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        self._conn = None
        self._lock = threading.RLock()

    def available(self) -> bool:
        try:
            self._ensure_conn()
            return True
        except Exception as exc:  # noqa: BLE001
            _log.warning("ads_engine.store_pg: PG unavailable: %r", type(exc).__name__)
            return False

    def _ensure_conn(self):
        import psycopg  # lazy — never imported at module load
        conn = self._conn
        if conn is not None:
            try:
                if not conn.closed:
                    return conn
            except Exception:  # noqa: BLE001
                pass
        self._conn = psycopg.connect(self._dsn, autocommit=False)
        return self._conn

    @contextmanager
    def session(self, tenant_id: str = "", is_admin: bool = False) -> Iterator[Any]:
        with self._lock:
            conn = self._ensure_conn()
            try:
                with conn.cursor() as cur:
                    # set_config(..., true) == SET LOCAL: scoped to THIS txn, resets on commit.
                    cur.execute("SELECT set_config('app.tenant_id', %s, true)", (str(tenant_id or ""),))
                    cur.execute("SELECT set_config('app.is_admin', %s, true)", ("1" if is_admin else "0",))
                yield conn
                conn.commit()
            except Exception:
                try:
                    conn.rollback()
                except Exception:  # noqa: BLE001
                    pass
                raise


_LOCAL_ENGINE: Optional[_LocalEngine] = None
_ENGINE_LOCK = threading.Lock()


def _dsn() -> str:
    return (os.getenv("ADS_PG_DSN") or os.getenv("DATABASE_URL") or "").strip()


def _engine():
    """Return the active engine (box pooled, else self-contained), or None if neither works."""
    box = _box_engine()
    if box is not None:
        return box
    global _LOCAL_ENGINE
    dsn = _dsn()
    if not dsn:
        return None
    if _LOCAL_ENGINE is None:
        with _ENGINE_LOCK:
            if _LOCAL_ENGINE is None:
                _LOCAL_ENGINE = _LocalEngine(dsn)
    return _LOCAL_ENGINE


def available() -> bool:
    """True iff a Postgres engine is reachable (so store.py can fail loud when postgres is
    explicitly requested but PG is down — never silently fall back to the non-RLS json store)."""
    eng = _engine()
    try:
        return bool(eng and eng.available())
    except Exception:  # noqa: BLE001
        return False


def _json(value):
    """psycopg3 jsonb adapter for a dict/list."""
    from psycopg.types.json import Jsonb
    return Jsonb(value)


# ---------------------------------------------------------------------------
# The Backend — the 11 generic primitives store.py dispatches to. Validation
# (_safe / COLLECTION_FILES / PER_TENANT_FILES membership) is done by store.py
# BEFORE it calls these, so both backends share identical validation behavior.
# ---------------------------------------------------------------------------
class PgBackend:
    """Postgres FORCE-RLS implementation of store.py's storage primitives."""

    name = "postgres"

    def __init__(self, engine) -> None:
        self._eng = engine

    # --- collection (tenant-keyed dict) primitives -------------------------
    def get_collection(self, tid: str, name: str) -> dict:
        with self._eng.session(tid, is_admin=False) as conn:
            rows = conn.execute(
                "SELECT row_id, data FROM ads_rows WHERE collection = %s", (name,)
            ).fetchall()
        out: dict = {}
        for row_id, data in rows:
            out[str(row_id)] = data if isinstance(data, dict) else {}
        return out

    def put_row(self, tid: str, name: str, row_id: str, row: dict) -> dict:
        stored = dict(row or {})
        stored["tenant_id"] = tid  # server-stamped, ALWAYS (mirrors the json backend)
        ver = int(stored.get("version", 0) or 0)
        with self._eng.session(tid, is_admin=False) as conn:
            conn.execute(
                "INSERT INTO ads_rows (tenant_id, collection, row_id, data, version, updated_at) "
                "VALUES (%s, %s, %s, %s, %s, now()) "
                "ON CONFLICT (tenant_id, collection, row_id) "
                "DO UPDATE SET data = EXCLUDED.data, version = EXCLUDED.version, updated_at = now()",
                (tid, name, str(row_id), _json(stored), ver),
            )
        return stored

    def delete_row(self, tid: str, name: str, row_id: str) -> bool:
        with self._eng.session(tid, is_admin=False) as conn:
            res = conn.execute(
                "DELETE FROM ads_rows WHERE collection = %s AND row_id = %s RETURNING row_id",
                (name, str(row_id)),
            ).fetchone()
        return res is not None

    def cas_row(self, tid: str, name: str, row_id: str,
                expected_version, row: dict, version_conflict_cls) -> dict:
        # bump on the INCOMING row's version (mirrors store._bump_version exactly).
        stored = dict(row or {})
        try:
            stored["version"] = int(stored.get("version", 0) or 0) + 1
        except Exception:  # noqa: BLE001
            stored["version"] = 1
        stored["tenant_id"] = tid
        with self._eng.session(tid, is_admin=False) as conn:
            existing = conn.execute(
                "SELECT version FROM ads_rows WHERE collection = %s AND row_id = %s FOR UPDATE",
                (name, str(row_id)),
            ).fetchone()
            if existing is not None and expected_version is not None:
                cur_v = int(existing[0] or 0)
                if cur_v != int(expected_version):
                    raise version_conflict_cls(
                        f"version mismatch on {name}/{row_id}: have {cur_v}, expected {expected_version}"
                    )
            conn.execute(
                "INSERT INTO ads_rows (tenant_id, collection, row_id, data, version, updated_at) "
                "VALUES (%s, %s, %s, %s, %s, now()) "
                "ON CONFLICT (tenant_id, collection, row_id) "
                "DO UPDATE SET data = EXCLUDED.data, version = EXCLUDED.version, updated_at = now()",
                (tid, name, str(row_id), _json(stored), int(stored["version"])),
            )
        return stored

    def list_tenant_ids(self, name: str) -> list:
        """The ONE cross-tenant enumeration (the privileged tick sweep). Runs under the ADMIN
        GUC (RLS would otherwise hide other tenants). Returns ONLY tenant ids, never row data.
        Default-safe: [] on any error (the tick must never crash)."""
        try:
            with self._eng.session("", is_admin=True) as conn:
                rows = conn.execute(
                    "SELECT DISTINCT tenant_id FROM ads_rows WHERE collection = %s", (name,)
                ).fetchall()
            return [str(r[0]) for r in rows if r and r[0] is not None]
        except Exception as exc:  # noqa: BLE001
            _log.warning("ads_engine.store_pg.list_tenant_ids failed: %r", type(exc).__name__)
            return []

    # --- per-tenant LIST file primitives -----------------------------------
    def get_tenant_file(self, tid: str, name: str) -> list:
        with self._eng.session(tid, is_admin=False) as conn:
            rows = conn.execute(
                "SELECT data FROM ads_tenant_rows WHERE collection = %s ORDER BY id ASC", (name,)
            ).fetchall()
        return [r[0] if isinstance(r[0], dict) else {} for r in rows]

    def append_tenant_row(self, tid: str, name: str, row: dict) -> dict:
        stored = dict(row or {})
        stored["tenant_id"] = tid
        with self._eng.session(tid, is_admin=False) as conn:
            conn.execute(
                "INSERT INTO ads_tenant_rows (tenant_id, collection, data) VALUES (%s, %s, %s)",
                (tid, name, _json(stored)),
            )
        return stored

    def put_tenant_file(self, tid: str, name: str, rows: list) -> None:
        with self._eng.session(tid, is_admin=False) as conn:
            conn.execute(
                "DELETE FROM ads_tenant_rows WHERE collection = %s", (name,)
            )
            for r in (rows or []):
                rr = dict(r or {})
                rr["tenant_id"] = tid
                conn.execute(
                    "INSERT INTO ads_tenant_rows (tenant_id, collection, data) VALUES (%s, %s, %s)",
                    (tid, name, _json(rr)),
                )

    # --- page_id -> tenant trust-root (GLOBAL, admin-GUC) ------------------
    def get_tenant_for_page(self, page_id: str) -> Optional[str]:
        """Pre-auth read (no tenant yet) => admin GUC. Default-safe: None on any error."""
        try:
            with self._eng.session("", is_admin=True) as conn:
                res = conn.execute(
                    "SELECT tenant_id FROM ads_page_tenant_map WHERE page_id = %s", (page_id,)
                ).fetchone()
            return str(res[0]) if res and res[0] else None
        except Exception as exc:  # noqa: BLE001
            _log.warning("ads_engine.store_pg.get_tenant_for_page failed: %r", type(exc).__name__)
            return None

    def link_page_to_tenant(self, tid: str, page_id: str, actor: str,
                            evidence: Optional[dict], page_conflict_cls) -> dict:
        """Bind page->tenant under the admin GUC (must detect a cross-tenant existing owner for
        the anti-hijack check). UNIQUENESS: a different existing owner => PageOwnershipConflict."""
        import time as _t
        ev = None
        if isinstance(evidence, dict):
            ev = {k: v for k, v in evidence.items()
                  if k in ("oauth_flow", "connected_by", "business_id")}
        with self._eng.session("", is_admin=True) as conn:
            existing = conn.execute(
                "SELECT tenant_id, linked_at FROM ads_page_tenant_map WHERE page_id = %s", (page_id,)
            ).fetchone()
            if existing is not None and existing[0] and str(existing[0]) != tid:
                raise page_conflict_cls(f"page_id {page_id} already linked to a different tenant")
            conn.execute(
                "INSERT INTO ads_page_tenant_map (page_id, tenant_id, actor, evidence, linked_at, updated_at) "
                "VALUES (%s, %s, %s, %s, now(), now()) "
                "ON CONFLICT (page_id) "
                "DO UPDATE SET tenant_id = EXCLUDED.tenant_id, actor = EXCLUDED.actor, "
                "evidence = EXCLUDED.evidence, updated_at = now()",
                (page_id, tid, str(actor or "")[:128], _json(ev) if ev is not None else None),
            )
        return {"page_id": page_id, "tenant_id": tid, "actor": str(actor or "")[:128],
                "updated_at": _t.time(), **({"evidence": ev} if ev is not None else {})}

    def unlink_page(self, tid: str, page_id: str) -> bool:
        """Ownership-checked delete (a tenant may only unlink its OWN page). Admin GUC + explicit
        tenant_id predicate = the same ownership rule the json store enforces in app logic."""
        with self._eng.session("", is_admin=True) as conn:
            res = conn.execute(
                "DELETE FROM ads_page_tenant_map WHERE page_id = %s AND tenant_id = %s RETURNING page_id",
                (page_id, tid),
            ).fetchone()
        return res is not None


# ---------------------------------------------------------------------------
# Backend factory — store.py asks for this once and memoizes it.
# ---------------------------------------------------------------------------
def make_backend() -> Optional[PgBackend]:
    """Return a PgBackend if a Postgres engine is reachable, else None.

    store.py calls this when ADS_STORE_BACKEND=postgres. A None return there is treated as a
    HARD ERROR (postgres explicitly requested but unreachable) — store.py never silently
    downgrades to the non-RLS json store."""
    eng = _engine()
    if eng is None:
        return None
    try:
        if not eng.available():
            return None
    except Exception:  # noqa: BLE001
        return None
    return PgBackend(eng)
