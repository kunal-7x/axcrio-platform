"""voice_kernel.memory.cache — tenant-namespaced WARM lead-memory cache.

The dial-time prefetch cache for `LeadMemory`. The cascade-delete research is
explicit: cache keys MUST carry the tenant namespace so eviction is EXACT and a
sibling tenant's cache is never touched, and embeddings/caches are batched
per-tenant, never across (Steve Kinney "Memory Systems for AI Agents"; mem0).

So every key is `(tenant_id, lead_phone)` and we expose:
  * get / put           — normal read-through cache,
  * evict(tenant, phone)       — one lead (right-to-erasure),
  * evict_tenant(tenant)       — whole tenant offboarding.

Erasure (erasure.py) calls evict AFTER the DB delete commits, so the purged row
can never resurface from a warm cache. Conforms to the `Purgeable` protocol so
`erase_*` can drive it generically.

Pure-stdlib + voice_kernel only. Thread-safe via a simple lock (the WARM path is
async but the cache op is tiny/sync).
"""
from __future__ import annotations

import threading
import time
from typing import Optional

from ..packet import LeadMemory


class LeadMemoryCache:
    """In-process TTL cache keyed by (tenant_id, lead_phone). Tenant-namespaced
    so eviction is blast-radius-exact (no cross-tenant key)."""

    def __init__(self, ttl_s: float = 300.0, max_entries: int = 10_000):
        self._ttl = ttl_s
        self._max = max_entries
        self._store: dict[tuple[str, str], tuple[float, LeadMemory]] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _key(tenant_id: str, lead_phone: str) -> tuple[str, str]:
        return ((tenant_id or "").strip(), (lead_phone or "").strip())

    def get(self, tenant_id: str, lead_phone: str) -> Optional[LeadMemory]:
        k = self._key(tenant_id, lead_phone)
        with self._lock:
            hit = self._store.get(k)
            if not hit:
                return None
            ts, mem = hit
            if (time.monotonic() - ts) > self._ttl:
                self._store.pop(k, None)
                return None
            return mem

    def put(self, tenant_id: str, lead_phone: str, mem: LeadMemory) -> None:
        if not (tenant_id or "").strip():
            return  # never cache an un-namespaced (tenant-less) entry — fail-closed
        k = self._key(tenant_id, lead_phone)
        with self._lock:
            if len(self._store) >= self._max:
                # cheapest bounded eviction: drop the oldest entry.
                oldest = min(self._store.items(), key=lambda kv: kv[1][0])[0]
                self._store.pop(oldest, None)
            self._store[k] = (time.monotonic(), mem)

    # ---- Purgeable surface (erasure drives these) ------------------------- #
    def evict(self, tenant_id: str, lead_phone: str) -> int:
        """Evict ONE lead. Returns count removed (0 or 1)."""
        k = self._key(tenant_id, lead_phone)
        with self._lock:
            return 1 if self._store.pop(k, None) is not None else 0

    def evict_tenant(self, tenant_id: str) -> int:
        """Evict EVERY entry for a tenant (offboarding). Exact: only this
        tenant's namespace is touched."""
        t = (tenant_id or "").strip()
        with self._lock:
            keys = [k for k in self._store if k[0] == t]
            for k in keys:
                self._store.pop(k, None)
            return len(keys)

    # Purgeable protocol aliases (erasure.py calls delete_by_lead/_tenant).
    def delete_by_lead(self, tenant_id: str, lead_phone: str) -> int:
        return self.evict(tenant_id, lead_phone)

    def delete_by_tenant(self, tenant_id: str) -> int:
        return self.evict_tenant(tenant_id)

    def __len__(self) -> int:
        with self._lock:
            return len(self._store)

    def __bool__(self) -> bool:
        # A cache object is always truthy (an EMPTY cache must not read as falsy —
        # otherwise `cache or LeadMemoryCache()` would silently discard it).
        return True
