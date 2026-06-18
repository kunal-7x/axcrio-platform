"""voice_ops.callback.store — the callback queue STORE (state + lead-lock).

This is the single source of truth for "what callback is pending for which lead",
the attempts counter, and the per-lead LOCK that guarantees a lead is never
double-dialed (the dedup + lead-locking requirement). It replaces the flat
`var/retry_queue.json` upsert in caller.py whose `_enqueue_retry` RESET `attempts`
on every write (bug B/D) and had no lock.

Two pieces:
  * `CallbackEntry`  — one immutable-ish record (the lead's pending callback).
  * `CallbackStore`  — the Protocol (load/upsert/record_attempt/terminate/lock).
  * `InMemoryCallbackStore` — a REAL, dependency-free, async-safe implementation
    used by tests AND as the documented local fallback. A LATER seam wave can add
    a Postgres-backed `PgCallbackStore` implementing the same Protocol against a
    FORCE-RLS `callback_queue` table (mirrors wallet.py); the engine never changes.

KEY INVARIANTS (the anti-runaway contract — enforced HERE, at write time):
  * dedup key = (tenant_id, phone). ONE pending entry per lead. upsert NEVER
    resets `attempts` (only `record_attempt` increments it) — kills bugs B & D.
  * a TERMINAL status (CALLED / EXPIRED / OPT_OUT) is sticky: once set, upsert
    refuses to re-open it (no re-enqueue after a successful pickup or opt-out).
  * `try_lock` is a per-lead mutex with a TTL lease: only ONE worker can hold a
    lead at a time, so two SIP numbers can never dial the same lead concurrently.

Pure-stdlib + voice_kernel.events.timeutil (UTC). ZERO droplet_work / agent
imports. No livekit / boto3 / asyncpg at module load.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field, replace
from typing import Optional, Protocol, runtime_checkable

from voice_kernel.events.timeutil import now_utc, now_utc_iso, parse_iso

# --------------------------------------------------------------------------- #
# Status taxonomy — terminal states are sticky (never re-enqueued).
# --------------------------------------------------------------------------- #
PENDING = "PENDING"        # scheduled, waiting for its due time
IN_FLIGHT = "IN_FLIGHT"    # a worker holds the lock + is dialing right now
CALLED = "CALLED"          # connected/answered -> DONE, no more cadence redials
EXPIRED = "EXPIRED"        # exhausted MAX_RETRIES with no connect
OPT_OUT = "OPT_OUT"        # lead asked not to be called -> never again

TERMINAL = frozenset({CALLED, EXPIRED, OPT_OUT})


def lead_key(tenant_id: str, phone: str) -> str:
    """The dedup / lock key. Tenant-partitioned so two tenants sharing a phone
    are distinct. Fail-closed: blank tenant raises (never a shared key)."""
    t = (tenant_id or "").strip()
    if not t:
        raise ValueError("lead_key: empty tenant_id (fail-closed, no shared key)")
    p = (phone or "").strip()
    return f"{t}::{p}"


@dataclass
class CallbackEntry:
    """One pending callback for a lead. `attempts` is the number of cadence dials
    ALREADY fired (T0 counts). `touch_index` is the next cadence slot. `priority`
    True = an explicit 'call me at X' (jumps the queue, honored after pickup).
    `last_summary` carries prior context for continuity (W7)."""

    tenant_id: str
    phone: str
    campaign_id: str = ""
    lead_id: str = ""
    status: str = PENDING
    attempts: int = 0                      # cadence dials already done (++ only via record_attempt)
    busy_today: int = 0                    # short busy reschedules used today
    busy_day: str = ""                     # YYYY-MM-DD of the busy_today counter
    touch_index: int = 0                   # next cadence slot to use
    next_attempt_at: str = ""              # ISO UTC; when fire_due may pick it up
    priority: bool = False                 # explicit 'call me at X' commitment
    reason: str = "cadence"                # cadence | callback | busy | technical
    last_summary: str = ""                 # prior-call summary -> continuity
    last_outcome: str = ""
    created_at: str = field(default_factory=now_utc_iso)
    updated_at: str = field(default_factory=now_utc_iso)

    def due(self, now_iso: Optional[str] = None) -> bool:
        if self.status not in (PENDING,):
            return False
        if not self.next_attempt_at:
            return True
        now = parse_iso(now_iso) if now_iso else now_utc()
        return parse_iso(self.next_attempt_at) <= now


@runtime_checkable
class CallbackStore(Protocol):
    """The store contract. A LATER Postgres impl (FORCE-RLS callback_queue) and the
    InMemory test impl both satisfy this; the cadence/scheduler engine depends only
    on this surface — never on a concrete store."""

    async def load(self, tenant_id: str, phone: str) -> Optional[CallbackEntry]: ...
    async def upsert(self, entry: CallbackEntry) -> CallbackEntry: ...
    async def record_attempt(self, tenant_id: str, phone: str) -> int: ...
    async def record_busy(self, tenant_id: str, phone: str) -> int: ...
    async def terminate(self, tenant_id: str, phone: str, status: str) -> None: ...
    async def due_entries(self, now_iso: Optional[str] = None) -> list[CallbackEntry]: ...
    async def try_lock(self, tenant_id: str, phone: str, ttl_s: int = 300) -> bool: ...
    async def unlock(self, tenant_id: str, phone: str) -> None: ...


class InMemoryCallbackStore:
    """Async-safe, dependency-free CallbackStore. Faithful to the load-bearing
    semantics a real RLS/Redis store must guarantee, so a test passing here is
    meaningful: idempotent upsert (no attempts reset), sticky terminal status,
    per-lead TTL lock (single dialer), monotonic attempts."""

    def __init__(self) -> None:
        self._rows: dict[str, CallbackEntry] = {}
        self._locks: dict[str, float] = {}          # key -> lock-lease expiry (monotonic)
        self._guard = asyncio.Lock()                # protects the dicts

    # ------------------------------------------------------------- reads #
    async def load(self, tenant_id: str, phone: str) -> Optional[CallbackEntry]:
        async with self._guard:
            r = self._rows.get(lead_key(tenant_id, phone))
            return replace(r) if r else None        # hand back a copy (no aliasing)

    async def due_entries(self, now_iso: Optional[str] = None) -> list[CallbackEntry]:
        async with self._guard:
            out = [replace(r) for r in self._rows.values() if r.due(now_iso)]
        # priority (explicit 'call me at X') first, then soonest-due.
        out.sort(key=lambda e: (not e.priority, e.next_attempt_at or ""))
        return out

    # ------------------------------------------------------------ writes #
    async def upsert(self, entry: CallbackEntry) -> CallbackEntry:
        """Idempotent UPSERT. If a row exists:
          * a TERMINAL existing status is sticky -> the upsert is refused (returns
            the existing terminal row) UNLESS the new entry is a higher-priority
            explicit commitment AND the terminal status is not OPT_OUT/EXPIRED.
            (A 'call me at X' AFTER a CALLED pickup is still honored — customer
            intent wins — but never re-opens an OPT_OUT or a hard EXPIRED.)
          * otherwise we MERGE: schedule fields update, but `attempts` / `busy_*`
            are PRESERVED from the existing row (never reset — this is the fix for
            bugs B & D). attempts only ever moves via `record_attempt`."""
        key = lead_key(entry.tenant_id, entry.phone)
        async with self._guard:
            cur = self._rows.get(key)
            if cur is not None:
                if cur.status in (OPT_OUT, EXPIRED):
                    return replace(cur)             # hard-sticky: never re-open
                if cur.status == CALLED and not entry.priority:
                    return replace(cur)             # no redial after pickup
                # merge: keep monotonic counters, take new schedule/priority/ctx.
                merged = replace(
                    cur,
                    campaign_id=entry.campaign_id or cur.campaign_id,
                    lead_id=entry.lead_id or cur.lead_id,
                    status=PENDING if entry.status == PENDING else entry.status,
                    next_attempt_at=entry.next_attempt_at or cur.next_attempt_at,
                    touch_index=max(entry.touch_index, cur.touch_index),
                    priority=entry.priority or cur.priority,
                    reason=entry.reason or cur.reason,
                    last_summary=entry.last_summary or cur.last_summary,
                    last_outcome=entry.last_outcome or cur.last_outcome,
                    updated_at=now_utc_iso(),
                    # attempts / busy_today / busy_day deliberately PRESERVED:
                    attempts=cur.attempts,
                    busy_today=cur.busy_today,
                    busy_day=cur.busy_day,
                )
                self._rows[key] = merged
                return replace(merged)
            fresh = replace(entry, updated_at=now_utc_iso())
            self._rows[key] = fresh
            return replace(fresh)

    async def record_attempt(self, tenant_id: str, phone: str) -> int:
        """The ONLY path that increments `attempts`. Returns the new count.
        Monotonic — a re-enqueue can never undo it, so the `attempts < max` guard
        is reliable (closes the infinite-loop root cause)."""
        key = lead_key(tenant_id, phone)
        async with self._guard:
            cur = self._rows.get(key)
            if cur is None:
                return 0
            cur.attempts += 1
            cur.touch_index = max(cur.touch_index, cur.attempts)
            cur.status = IN_FLIGHT
            cur.updated_at = now_utc_iso()
            return cur.attempts

    async def record_busy(self, tenant_id: str, phone: str) -> int:
        """Bump the per-day busy counter (resets when the day rolls). Returns the
        new busy-today count. Busy reschedules are NOT cadence attempts."""
        key = lead_key(tenant_id, phone)
        async with self._guard:
            cur = self._rows.get(key)
            if cur is None:
                return 0
            today = now_utc_iso()[:10]
            if cur.busy_day != today:
                cur.busy_day = today
                cur.busy_today = 0
            cur.busy_today += 1
            cur.updated_at = now_utc_iso()
            return cur.busy_today

    async def terminate(self, tenant_id: str, phone: str, status: str) -> None:
        """Set a sticky terminal status (CALLED/EXPIRED/OPT_OUT). Idempotent."""
        if status not in TERMINAL:
            raise ValueError(f"terminate: {status!r} is not a terminal status")
        key = lead_key(tenant_id, phone)
        async with self._guard:
            cur = self._rows.get(key)
            if cur is None:
                return
            cur.status = status
            cur.updated_at = now_utc_iso()

    # ---------------------------------------------------------- lead lock #
    async def try_lock(self, tenant_id: str, phone: str, ttl_s: int = 300) -> bool:
        """Acquire the per-lead dial lock with a TTL lease. Returns False if a
        live (non-expired) lease is already held — so a second worker (or a second
        SIP number) can NEVER dial the same lead concurrently. The TTL means a
        crashed worker's lock self-heals."""
        key = lead_key(tenant_id, phone)
        async with self._guard:
            now = asyncio.get_event_loop().time()
            exp = self._locks.get(key)
            if exp is not None and exp > now:
                return False
            self._locks[key] = now + max(1, ttl_s)
            return True

    async def unlock(self, tenant_id: str, phone: str) -> None:
        key = lead_key(tenant_id, phone)
        async with self._guard:
            self._locks.pop(key, None)

    # --------------------------------------------------------- test peek #
    def snapshot(self) -> list[CallbackEntry]:
        return [replace(r) for r in self._rows.values()]
