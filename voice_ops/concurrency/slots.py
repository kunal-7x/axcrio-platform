"""voice_ops.concurrency.slots — SlotPool: atomic capacity-bounded slot counter.

A counting semaphore with NAMED, TTL'd leases. It models the scarce, countable
resources a call needs reserved BEFORE dialing:
  - worker slots  (one active-call slot per worker; capacity = worker_slot_cap * workers),
  - TTS slots     (per-provider-KEY concurrent synthesis channels),
  - per-tenant call slots (the per-tenant concurrency ceiling),
  - the GLOBAL call slot (cross-tenant fleet ceiling — the guard the dial loop lacks).

`acquire(lease_id)` reserves one slot iff `in_flight < capacity`, recording the lease
id + its expiry. `release(lease_id)` frees it (idempotent — releasing an unknown/
already-released id is a no-op, so a double-release can never drive the counter
negative). `sweep()` reclaims leases whose TTL elapsed — this self-heals a crashed
worker that reserved a slot and died before releasing (mirrors the lead-lock TTL),
so a dead call can never permanently consume a slot.

This is the SYNCHRONOUS, atomic core; the async AdmissionController composes several
SlotPools + TokenBuckets into one all-or-nothing reservation. Thread-safe (RLock),
pure stdlib, injectable clock. Importing this pulls ZERO heavy/droplet code.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, Optional


@dataclass
class _Lease:
    lease_id: str
    acquired_at: float
    expires_at: float


class SlotPool:
    """Capacity-bounded, TTL-leased slot counter. Construct one per named resource
    (e.g. ``SlotPool("worker", capacity=20)``)."""

    def __init__(
        self,
        name: str,
        capacity: int,
        *,
        ttl_s: float = 300.0,
        clock: Optional[Callable[[], float]] = None,
    ) -> None:
        self.name = name
        self.capacity = max(0, int(capacity))
        self.ttl_s = float(ttl_s)
        self._clock = clock or time.monotonic
        self._lock = threading.RLock()
        self._leases: Dict[str, _Lease] = {}

    # ----------------------------------------------------------- internals #
    def _expire(self) -> None:
        """Drop any lease whose TTL elapsed (a crashed worker that never released).
        Called under the lock before every capacity check so the count is live."""
        if self.ttl_s <= 0:
            return
        now = self._clock()
        dead = [lid for lid, l in self._leases.items() if l.expires_at <= now]
        for lid in dead:
            del self._leases[lid]

    # --------------------------------------------------------------- query #
    @property
    def in_flight(self) -> int:
        with self._lock:
            self._expire()
            return len(self._leases)

    @property
    def free(self) -> int:
        with self._lock:
            self._expire()
            return max(0, self.capacity - len(self._leases))

    def held(self, lease_id: str) -> bool:
        with self._lock:
            self._expire()
            return lease_id in self._leases

    # ------------------------------------------------------------- mutate #
    def acquire(self, lease_id: str, *, ttl_s: Optional[float] = None) -> bool:
        """Atomically reserve one slot under `lease_id`. Returns False when the pool
        is full (caller paces/queues — never fails the call). Re-acquiring an id that
        already holds a slot is a no-op success (idempotent retry-safe), so the dial
        loop's index.lock-style retries can't double-count the same call."""
        if self.capacity <= 0:
            return False
        with self._lock:
            self._expire()
            if lease_id in self._leases:
                return True  # idempotent: already holds the slot
            if len(self._leases) >= self.capacity:
                return False
            now = self._clock()
            ttl = self.ttl_s if ttl_s is None else float(ttl_s)
            self._leases[lease_id] = _Lease(lease_id, now, now + ttl)
            return True

    def release(self, lease_id: str) -> bool:
        """Free the slot held by `lease_id`. Idempotent: releasing an unknown or
        already-expired id returns False and changes nothing (a double-release can
        NEVER drive the counter negative). Returns True iff a live lease was freed."""
        with self._lock:
            return self._leases.pop(lease_id, None) is not None

    def renew(self, lease_id: str, *, ttl_s: Optional[float] = None) -> bool:
        """Extend a live lease's TTL (a long call heartbeats so its slot isn't
        swept out from under it). No-op False if the lease is gone."""
        with self._lock:
            self._expire()
            l = self._leases.get(lease_id)
            if l is None:
                return False
            ttl = self.ttl_s if ttl_s is None else float(ttl_s)
            l.expires_at = self._clock() + ttl
            return True

    def sweep(self) -> int:
        """Force a TTL reclaim pass; returns how many dead leases were reclaimed.
        (Normally implicit on every query/acquire; exposed for an ops sweeper task.)"""
        with self._lock:
            before = len(self._leases)
            self._expire()
            return before - len(self._leases)

    def snapshot(self) -> dict:
        with self._lock:
            self._expire()
            return {
                "name": self.name,
                "capacity": self.capacity,
                "in_flight": len(self._leases),
                "free": max(0, self.capacity - len(self._leases)),
            }
