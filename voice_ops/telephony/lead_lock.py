"""voice_ops.telephony.lead_lock — per-lead dial LOCK (W12 #5: no double-dial).

GUARANTEE: a lead is NEVER dialed twice concurrently — not by two campaign workers,
not by a campaign + a retry job, and CRUCIALLY not by two different phone NUMBERS at
the same instant. The lock key is `(tenant_id, phone)`, tenant-partitioned (two
tenants sharing a phone are distinct, fail-closed on empty tenant). The lease has a
TTL so a crashed worker's lock self-heals — the seam sets TTL = 2× the min-call-floor
fence so a real in-flight call always outlives the time it takes to start dialing.

This is the SAME proven semantics as `voice_ops.callback.store.InMemoryCallbackStore`
`try_lock`/`unlock` (already shipped, already tested) — extracted into a standalone,
sync, dial-loop-callable primitive so the telephony seam can guard the inner dispatch
loop WITHOUT depending on the callback store. A LATER seam wave can swap this for a
Redis `SET NX PX` lock implementing the same surface (acquire/release/is_locked) for
cross-process safety; the in-process dict is authoritative for a single worker (the
live box runs one dial worker — same assumption trunk_registry.rotation makes).

PURE: stdlib only (threading + monotonic clock). NEVER raises into the dial loop;
acquire() returning False is the ONLY signal a lead is already held.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Callable, Dict, Optional

log = logging.getLogger("voice_ops.telephony.lead_lock")


def lead_key(tenant_id: str, phone: str) -> str:
    """The dial-lock key. Tenant-partitioned; fail-closed on blank tenant (never a
    shared key that could let one tenant's lock collide with another's)."""
    t = (tenant_id or "").strip()
    if not t:
        raise ValueError("lead_key: empty tenant_id (fail-closed, no shared lock key)")
    p = (phone or "").strip()
    return f"{t}::{p}"


class LeadLock:
    """In-process per-lead TTL mutex. Construct once per process: `LeadLock(ttl_s=...)`.
    Thread-safe; the monotonic clock is injectable for offline tests."""

    def __init__(self, ttl_s: int = 300, *, clock: Optional[Callable[[], float]] = None):
        self._ttl = max(1, int(ttl_s))
        self._clock = clock or time.monotonic
        self._lock = threading.Lock()
        self._held: Dict[str, float] = {}   # key -> lease-expiry (monotonic seconds)

    # ------------------------------------------------------------- acquire #
    def acquire(self, tenant_id: str, phone: str, ttl_s: Optional[int] = None) -> bool:
        """Try to take the lead's dial lock. Returns True if acquired (caller may
        dial), False if a LIVE (non-expired) lease is already held by someone else —
        the caller MUST skip this lead. An expired lease is reclaimed transparently
        (self-heal after a crash). NEVER raises except on a programming-error empty
        tenant (which must surface, never silently share a key)."""
        key = lead_key(tenant_id, phone)
        ttl = max(1, int(ttl_s if ttl_s is not None else self._ttl))
        with self._lock:
            now = self._clock()
            exp = self._held.get(key)
            if exp is not None and exp > now:
                return False                      # live lease held -> someone is dialing this lead
            self._held[key] = now + ttl
            return True

    def is_locked(self, tenant_id: str, phone: str) -> bool:
        """True iff a LIVE lease is currently held for this lead (read-only; does not
        acquire). Used by the seam's pre-dial guard."""
        key = lead_key(tenant_id, phone)
        with self._lock:
            exp = self._held.get(key)
            return exp is not None and exp > self._clock()

    def release(self, tenant_id: str, phone: str) -> None:
        """Release the lead's lock (call in `_finalize_call`). Idempotent; safe to call
        even if the lease already expired. NEVER raises (blank tenant -> no-op)."""
        try:
            key = lead_key(tenant_id, phone)
        except ValueError:
            return
        with self._lock:
            self._held.pop(key, None)

    def renew(self, tenant_id: str, phone: str, ttl_s: Optional[int] = None) -> bool:
        """Extend a held lease (for a long call that may outlive the default TTL).
        Returns True if WE still hold it (extended), False if the lease had already
        expired/been reclaimed (the caller should stop — it no longer owns the lead)."""
        key = lead_key(tenant_id, phone)
        ttl = max(1, int(ttl_s if ttl_s is not None else self._ttl))
        with self._lock:
            now = self._clock()
            exp = self._held.get(key)
            if exp is None or exp <= now:
                return False
            self._held[key] = now + ttl
            return True

    # ------------------------------------------------------------- ops #
    def held_count(self) -> int:
        with self._lock:
            now = self._clock()
            return sum(1 for e in self._held.values() if e > now)

    def reset(self) -> None:
        with self._lock:
            self._held.clear()
