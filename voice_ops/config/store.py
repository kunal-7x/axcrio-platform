"""voice_ops.config.store — the VERSIONED, cache-invalidating, tenant-scoped real-time config store.

This is the backbone that makes "add a key / change a setting in the panel → live everywhere with NO
redeploy" true. The mechanism (the founder's whole ask) is:

  1. Every tenant's config carries a monotonically increasing `version` integer.
  2. A WRITE bumps `version` (single atomic UPDATE), persists to the FORCE-RLS `config_state` table,
     and stamps an in-process invalidation marker.
  3. Every READ on the hot path (worker / scheduler / agent-adjacent code) is a `get(tenant_id)`
     that checks the cheap version marker; a stale cached snapshot is dropped and refetched. Polling
     the version is one tiny SELECT (or one Redis GET via the seam), NOT the whole blob — so a
     reader picks up a change within one poll interval WITHOUT a restart, and a hot loop that already
     has the current version pays ~nothing.
  4. A `config_changed` event is emitted on the W8 bus on every write, so push-based consumers
     (dashboards, the AI-Manager, other workers subscribed to the tenant stream) refresh INSTANTLY
     rather than waiting for the next poll. Belt (poll) AND suspenders (event).

The store owns NO domain shape — it persists an opaque JSON `doc` per (tenant, namespace). The
vendor-profile model + the key store sit on top. It is the single place that knows about versions,
the RLS table, and cache invalidation.

DB is LAZY + import-guarded (CI / no-Postgres safe); an injectable in-memory store backs tests.
Importing this module pulls ZERO droplet/agent code and ZERO sqlalchemy at module load.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

log = logging.getLogger("voice_ops.config.store")


# --------------------------------------------------------------------------- #
# FORCE-RLS table — the tracked source of truth (applied at mount, alongside
# booking/rls.sql + gcal RLS_DDL). One row per (org_id, namespace); the JSON doc
# is opaque to the store. `version` is the cache-invalidation cursor.
# --------------------------------------------------------------------------- #
RLS_DDL = """
-- voice_ops.config real-time config state. FORCE-RLS, tenant-isolated.
CREATE TABLE IF NOT EXISTS config_state (
    org_id      text NOT NULL,
    namespace   text NOT NULL,                 -- 'vendor_profile' | 'provider_keys' | ...
    version     bigint NOT NULL DEFAULT 1,
    doc         jsonb  NOT NULL DEFAULT '{}'::jsonb,
    updated_by  text   NOT NULL DEFAULT '',
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (org_id, namespace)
);
ALTER TABLE config_state ENABLE ROW LEVEL SECURITY;
ALTER TABLE config_state FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS config_state_rls ON config_state;
CREATE POLICY config_state_rls ON config_state
    USING (org_id = current_setting('app.tenant_id', true)
           OR current_setting('app.is_admin', true) = 'true')
    WITH CHECK (org_id = current_setting('app.tenant_id', true)
           OR current_setting('app.is_admin', true) = 'true');
""".strip()


_NOT_CONFIGURED = {"status": "not_configured", "reason": "postgres_unavailable"}


@dataclass
class ConfigSnapshot:
    """An immutable read of one (tenant, namespace) config doc at a known version."""

    tenant_id: str
    namespace: str
    version: int
    doc: dict = field(default_factory=dict)
    updated_by: str = ""

    def is_stale(self, current_version: int) -> bool:
        return self.version < current_version


# --------------------------------------------------------------------------- #
# pluggable backend: a real Postgres backend (lazy) OR an injected in-memory one
# for tests. Both honor tenant isolation; the in-memory one enforces it explicitly
# so a test proves cross-tenant reads return nothing.
# --------------------------------------------------------------------------- #
class InMemoryBackend:
    """Dict-backed, tenant-checked backend for tests / no-Postgres hosts. Thread-safe."""

    def __init__(self) -> None:
        self._rows: dict[tuple[str, str], dict] = {}
        self._lock = threading.Lock()

    def read(self, tenant_id: str, namespace: str, *, is_admin: bool = False) -> Optional[dict]:
        with self._lock:
            row = self._rows.get((tenant_id, namespace))
            return dict(row) if row else None

    def read_version(self, tenant_id: str, namespace: str, *, is_admin: bool = False) -> int:
        with self._lock:
            row = self._rows.get((tenant_id, namespace))
            return int(row["version"]) if row else 0

    def upsert_bump(self, tenant_id: str, namespace: str, doc: dict, updated_by: str,
                    *, is_admin: bool = False) -> int:
        with self._lock:
            row = self._rows.get((tenant_id, namespace))
            version = (int(row["version"]) + 1) if row else 1
            self._rows[(tenant_id, namespace)] = {
                "org_id": tenant_id, "namespace": namespace, "version": version,
                "doc": json.loads(json.dumps(doc)), "updated_by": updated_by,
            }
            return version

    def all_tenants(self) -> list[str]:  # admin/cron helper (tests only)
        with self._lock:
            return sorted({k[0] for k in self._rows})


class _PostgresBackend:
    """Lazy, RLS-honoring Postgres backend riding the P1 db.engine spine."""

    def _engine(self):
        try:
            from db import engine as eng  # type: ignore
            return eng if eng.available() else None
        except Exception:  # noqa: BLE001
            return None

    def _text(self, sql: str):
        from sqlalchemy import text
        return text(sql)

    def read(self, tenant_id: str, namespace: str, *, is_admin: bool = False) -> Optional[dict]:
        eng = self._engine()
        if eng is None:
            return None
        try:
            with eng.session(tenant_id=tenant_id, is_admin=is_admin) as s:
                row = s.execute(self._text(
                    "SELECT version, doc, updated_by FROM config_state "
                    "WHERE org_id=:org AND namespace=:ns"
                ), {"org": tenant_id, "ns": namespace}).fetchone()
                if row is None:
                    return None
                doc = row[1]
                if isinstance(doc, str):
                    doc = json.loads(doc)
                return {"org_id": tenant_id, "namespace": namespace, "version": int(row[0]),
                        "doc": doc or {}, "updated_by": row[2] or ""}
        except Exception as exc:  # noqa: BLE001
            log.info("config_state read failed: %r", exc)
            return None

    def read_version(self, tenant_id: str, namespace: str, *, is_admin: bool = False) -> int:
        eng = self._engine()
        if eng is None:
            return 0
        try:
            with eng.session(tenant_id=tenant_id, is_admin=is_admin) as s:
                row = s.execute(self._text(
                    "SELECT version FROM config_state WHERE org_id=:org AND namespace=:ns"
                ), {"org": tenant_id, "ns": namespace}).fetchone()
                return int(row[0]) if row else 0
        except Exception as exc:  # noqa: BLE001
            log.info("config_state read_version failed: %r", exc)
            return 0

    def upsert_bump(self, tenant_id: str, namespace: str, doc: dict, updated_by: str,
                    *, is_admin: bool = False) -> int:
        eng = self._engine()
        if eng is None:
            return 0
        try:
            with eng.session(tenant_id=tenant_id, is_admin=is_admin) as s:
                # atomic UPSERT that bumps version in a SINGLE statement (no read-then-write race).
                row = s.execute(self._text(
                    "INSERT INTO config_state (org_id, namespace, version, doc, updated_by, "
                    " created_at, updated_at) "
                    "VALUES (:org,:ns,1, CAST(:doc AS jsonb), :by, now(), now()) "
                    "ON CONFLICT (org_id, namespace) DO UPDATE SET "
                    " version = config_state.version + 1, doc = CAST(:doc AS jsonb), "
                    " updated_by = :by, updated_at = now() "
                    "RETURNING version"
                ), {"org": tenant_id, "ns": namespace, "doc": json.dumps(doc), "by": updated_by or ""}).fetchone()
                return int(row[0]) if row else 0
        except Exception as exc:  # noqa: BLE001
            log.info("config_state upsert failed: %r", exc)
            return 0


# Injectable backend (tests inject InMemoryBackend); default = lazy Postgres.
_backend = None


def set_backend_for_tests(b) -> None:
    """Inject a backend (InMemoryBackend) for tests; None resets to lazy Postgres."""
    global _backend
    _backend = b
    # a backend swap invalidates every cached snapshot.
    ConfigStore.invalidate_all()


def _get_backend():
    global _backend
    if _backend is None:
        _backend = _PostgresBackend()
    return _backend


# --------------------------------------------------------------------------- #
# ConfigStore — the public, versioned, cache-invalidating read/write surface.
# --------------------------------------------------------------------------- #
class ConfigStore:
    """Versioned config store with a per-process snapshot cache that self-invalidates on version
    change. One instance per process is enough; it is created lazily by the package facade.

    `get` returns a cached ConfigSnapshot if its version still matches the backend's current version
    (one tiny read), else refetches. `put` performs the atomic version-bumping UPSERT, refreshes the
    cache, and returns the new ConfigSnapshot so the caller can emit the config_changed event."""

    # class-level cache so set_backend_for_tests can flush every instance.
    _cache: dict[tuple[str, str], ConfigSnapshot] = {}
    _cache_lock = threading.Lock()
    _last_version_poll: dict[tuple[str, str], tuple[float, int]] = {}
    version_poll_ttl_s: float = 1.0  # don't hammer the version SELECT more than 1x/sec per key

    @classmethod
    def invalidate_all(cls) -> None:
        with cls._cache_lock:
            cls._cache.clear()
            cls._last_version_poll.clear()

    def invalidate(self, tenant_id: str, namespace: str) -> None:
        with self._cache_lock:
            self._cache.pop((tenant_id, namespace), None)
            self._last_version_poll.pop((tenant_id, namespace), None)

    def _current_version(self, tenant_id: str, namespace: str, is_admin: bool) -> int:
        key = (tenant_id, namespace)
        now = time.monotonic()
        cached = self._last_version_poll.get(key)
        if cached and now - cached[0] < self.version_poll_ttl_s:
            return cached[1]
        v = _get_backend().read_version(tenant_id, namespace, is_admin=is_admin)
        self._last_version_poll[key] = (now, v)
        return v

    def get(self, tenant_id: str, namespace: str, *, is_admin: bool = False) -> Optional[ConfigSnapshot]:
        """Cache-aware read. Returns None if the tenant has no doc in this namespace yet."""
        if not (tenant_id or "").strip():
            return None
        key = (tenant_id, namespace)
        cur = self._current_version(tenant_id, namespace, is_admin)
        with self._cache_lock:
            snap = self._cache.get(key)
        if snap is not None and not snap.is_stale(cur) and cur != 0:
            return snap
        row = _get_backend().read(tenant_id, namespace, is_admin=is_admin)
        if row is None:
            return None
        snap = ConfigSnapshot(tenant_id=tenant_id, namespace=namespace, version=int(row["version"]),
                              doc=dict(row.get("doc") or {}), updated_by=row.get("updated_by", ""))
        with self._cache_lock:
            self._cache[key] = snap
            self._last_version_poll[key] = (time.monotonic(), snap.version)
        return snap

    def put(self, tenant_id: str, namespace: str, doc: dict, *, updated_by: str = "",
            is_admin: bool = False) -> ConfigSnapshot:
        """Atomic version-bumping write. Refreshes the cache and returns the new snapshot. A failed
        persist (no Postgres) returns a version-0 snapshot so the caller can still proceed in a
        dormant/no-DB environment without crashing (the seam treats v0 as 'not persisted')."""
        if not (tenant_id or "").strip():
            raise ValueError("config put requires a tenant_id (fail-closed)")
        version = _get_backend().upsert_bump(tenant_id, namespace, doc, updated_by, is_admin=is_admin)
        snap = ConfigSnapshot(tenant_id=tenant_id, namespace=namespace, version=int(version),
                              doc=dict(doc), updated_by=updated_by)
        key = (tenant_id, namespace)
        with self._cache_lock:
            self._cache[key] = snap
            self._last_version_poll[key] = (time.monotonic(), snap.version)
        return snap
