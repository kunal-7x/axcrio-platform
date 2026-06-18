"""voice_ops.reporting.store — the tenant-scoped read-model store (W14).

Holds the FactCall rows the consumer materializes and the service queries. The
backend is INJECTABLE so the package never hard-depends on Postgres:

  * default = `InMemoryReportingBackend` — a dependency-free dict keyed by
    (tenant_id, call_id). CI + the resting build use this; it is also a perfectly
    good live cache when Redis/PG is absent (degrade, never crash).
  * a PG-backed backend can be injected on the box later (lazy import there,
    mirroring voice_ops/booking/store.py) — this module imports ZERO psycopg/sqlalchemy.

Every method is TENANT-SCOPED and fail-closed on an empty tenant_id (never a
cross-tenant read/write). The store is a thin facade; aggregation lives in
aggregate.py so the store stays a dumb, swappable persistence seam.
"""
from __future__ import annotations

import logging
import threading
from typing import Iterable, Optional, Protocol, runtime_checkable

from .model import FactCall

log = logging.getLogger("voice_ops.reporting.store")


@runtime_checkable
class ReportingBackend(Protocol):
    """The persistence contract a backend must satisfy. Tenant-scoped, latest-wins
    upsert by (tenant_id, call_id), and a tenant-scoped scan the service filters."""

    def upsert(self, fact: FactCall) -> None: ...

    def get(self, tenant_id: str, call_id: str) -> Optional[FactCall]: ...

    def scan(self, tenant_id: str) -> Iterable[FactCall]: ...

    def clear(self, tenant_id: str = "") -> None: ...


class InMemoryReportingBackend:
    """Thread-safe in-memory read-model. (tenant_id, call_id) -> FactCall."""

    def __init__(self) -> None:
        self._rows: dict[tuple[str, str], FactCall] = {}
        self._lock = threading.RLock()

    def upsert(self, fact: FactCall) -> None:
        key = (fact.tenant_id, fact.call_id)
        with self._lock:
            self._rows[key] = fact

    def get(self, tenant_id: str, call_id: str) -> Optional[FactCall]:
        with self._lock:
            return self._rows.get((tenant_id, call_id))

    def scan(self, tenant_id: str) -> list[FactCall]:
        with self._lock:
            return [f.copy() for (t, _c), f in self._rows.items() if t == tenant_id]

    def clear(self, tenant_id: str = "") -> None:
        with self._lock:
            if not tenant_id:
                self._rows.clear()
                return
            for key in [k for k in self._rows if k[0] == tenant_id]:
                del self._rows[key]


class ReportingStore:
    """Tenant-scoped facade over a ReportingBackend. Fail-closed on empty tenant."""

    def __init__(self, backend: Optional[ReportingBackend] = None) -> None:
        self.backend: ReportingBackend = backend or InMemoryReportingBackend()

    @staticmethod
    def _ok(tenant_id: str) -> bool:
        return bool((tenant_id or "").strip())

    def upsert(self, fact: FactCall) -> bool:
        """Persist (latest-wins) one FactCall. Drops a row with no tenant_id or no
        call_id (fail-closed — never a rootless/cross-tenant write). Returns True
        if stored."""
        if not self._ok(fact.tenant_id) or not (fact.call_id or "").strip():
            log.warning("ReportingStore.upsert dropped: missing tenant/call id")
            return False
        try:
            self.backend.upsert(fact)
            return True
        except Exception as exc:  # noqa: BLE001 — a store error must not crash ingest
            log.warning("ReportingStore.upsert failed (non-fatal): %r", exc)
            return False

    def get(self, tenant_id: str, call_id: str) -> Optional[FactCall]:
        if not self._ok(tenant_id):
            return None
        try:
            return self.backend.get(tenant_id, call_id)
        except Exception as exc:  # noqa: BLE001
            log.warning("ReportingStore.get failed (non-fatal): %r", exc)
            return None

    def scan(self, tenant_id: str) -> list[FactCall]:
        """All FactCall rows for ONE tenant (the service then range-filters +
        aggregates). Empty tenant -> [] (never a cross-tenant scan)."""
        if not self._ok(tenant_id):
            return []
        try:
            return list(self.backend.scan(tenant_id))
        except Exception as exc:  # noqa: BLE001
            log.warning("ReportingStore.scan failed (non-fatal): %r", exc)
            return []

    def clear(self, tenant_id: str = "") -> None:
        try:
            self.backend.clear(tenant_id)
        except Exception as exc:  # noqa: BLE001
            log.debug("ReportingStore.clear failed: %r", exc)
