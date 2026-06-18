"""voice_ops.telephony.number_pool — multi-number POOL management (W12 #2).

The fleet of phone numbers a tenant dials FROM. The founder adds numbers from the UI;
the pool distributes calls across them, enforces per-number cooldown + concurrency +
daily caps, and tracks usage so no single number is overloaded (the +918071583488
death-pattern: one number hammered until the carrier blocks it).

Shape mirrors the rest of voice_ops: a `NumberPoolStore` Protocol + a real,
dependency-free `InMemoryNumberPoolStore` (used by tests AND as the documented local
fallback). A LATER seam wave adds a `PgNumberPoolStore` against the FORCE-RLS
`phone_number_pool` table (DDL in the seam doc + db/ddl_number_pool.sql) — the engine
depends only on the Protocol, so swapping in Postgres is a drop-in. EVERY method is
tenant-scoped and fail-closes on empty tenant_id (never a cross-tenant / rootless read).

A pool number record:
  number          E.164 CLI the call originates from (the trunk DID).
  trunk_id        which SIP trunk carries this DID (handed to create_sip_participant).
  status          'active' | 'paused' | 'disabled'  (founder/admin control).
  series          '140' | '160' | '1600' | '' (unknown) — the compliance CLI-series tag.
  daily_cap       per-number daily dial cap (0 -> use config default).
  concurrency     max concurrent live calls on this number.
  cooldown_s      min seconds between dials on THIS number (0 -> config default).
  used_today      dials placed today (resets on day-roll, UTC date).
  in_flight       live concurrent calls right now.
  last_dial_ts    monotonic ts of the last dial (cooldown gate).

The pool answers the router's two questions: `available_numbers(tenant)` (numbers that
can take a call RIGHT NOW — active, under cap, under concurrency, off cooldown) and the
lease/return pair `lease(tenant, number)` / `release(tenant, number, answered, dur)`
that increments/decrements in_flight + used_today atomically. Reputation (health.py)
is layered ON TOP by the router (the pool tracks capacity; health tracks spam-risk).

PURE: stdlib only; NO droplet_work / asyncpg / livekit at module load; NEVER raises
into the dial loop (degrades to an empty pool when unconfigured).
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field, replace
from typing import Callable, Dict, List, Optional, Protocol, runtime_checkable

from .config import TelephonyOpsConfig

log = logging.getLogger("voice_ops.telephony.number_pool")

ACTIVE = "active"
PAUSED = "paused"
DISABLED = "disabled"


def _utc_date() -> str:
    import datetime as _dt
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%d")


@dataclass
class PoolNumber:
    """One number in a tenant's outbound fleet (mirror of a phone_number_pool row)."""
    tenant_id: str
    number: str
    trunk_id: str = ""
    status: str = ACTIVE
    series: str = ""                  # '140' | '160' | '1600' | '' (compliance CLI tag)
    daily_cap: int = 0                # 0 -> config per_number_daily_cap
    concurrency: int = 0              # 0 -> config per_number_concurrency
    cooldown_s: int = 0               # 0 -> config cooldown_seconds
    used_today: int = 0
    used_day: str = ""                # YYYY-MM-DD (UTC) of used_today
    in_flight: int = 0
    last_dial_mono: float = 0.0       # monotonic ts of last dial (cooldown gate)
    created_at: str = ""
    updated_at: str = ""

    def is_dialable_state(self) -> bool:
        return self.status == ACTIVE


@runtime_checkable
class NumberPoolStore(Protocol):
    """Store contract. The InMemory test impl + a future PgNumberPoolStore (FORCE-RLS)
    both satisfy this; the NumberPool facade depends only on this surface."""

    def add(self, num: PoolNumber) -> PoolNumber: ...
    def remove(self, tenant_id: str, number: str) -> bool: ...
    def set_status(self, tenant_id: str, number: str, status: str) -> bool: ...
    def get(self, tenant_id: str, number: str) -> Optional[PoolNumber]: ...
    def list(self, tenant_id: str) -> List[PoolNumber]: ...
    def lease(self, tenant_id: str, number: str, *, cap: int, conc: int) -> bool: ...
    def release(self, tenant_id: str, number: str) -> None: ...


class InMemoryNumberPoolStore:
    """Thread-safe, dependency-free NumberPoolStore. Faithful to the load-bearing
    semantics a real RLS store must guarantee: tenant-partitioned keys, atomic
    lease (cap + concurrency check under one lock), day-roll cap reset, no negative
    in_flight. A test passing here is meaningful."""

    def __init__(self, *, clock: Optional[Callable[[], float]] = None,
                 date_fn: Optional[Callable[[], str]] = None):
        self._rows: Dict[str, PoolNumber] = {}      # "tenant::number" -> PoolNumber
        self._lock = threading.RLock()
        self._clock = clock or time.monotonic
        self._date = date_fn or _utc_date

    @staticmethod
    def _key(tenant_id: str, number: str) -> str:
        t = (tenant_id or "").strip()
        if not t:
            raise ValueError("number_pool: empty tenant_id (fail-closed)")
        return f"{t}::{(number or '').strip()}"

    def _roll_day(self, row: PoolNumber) -> None:
        today = self._date()
        if row.used_day != today:
            row.used_day = today
            row.used_today = 0

    def add(self, num: PoolNumber) -> PoolNumber:
        with self._lock:
            key = self._key(num.tenant_id, num.number)
            existing = self._rows.get(key)
            if existing is not None:
                merged = replace(existing,
                                 trunk_id=num.trunk_id or existing.trunk_id,
                                 series=num.series or existing.series,
                                 daily_cap=num.daily_cap or existing.daily_cap,
                                 concurrency=num.concurrency or existing.concurrency,
                                 cooldown_s=num.cooldown_s or existing.cooldown_s,
                                 status=num.status or existing.status)
                self._rows[key] = merged
                return replace(merged)
            self._rows[key] = replace(num, used_day=self._date())
            return replace(self._rows[key])

    def remove(self, tenant_id: str, number: str) -> bool:
        with self._lock:
            return self._rows.pop(self._key(tenant_id, number), None) is not None

    def set_status(self, tenant_id: str, number: str, status: str) -> bool:
        with self._lock:
            row = self._rows.get(self._key(tenant_id, number))
            if row is None:
                return False
            row.status = status
            return True

    def get(self, tenant_id: str, number: str) -> Optional[PoolNumber]:
        with self._lock:
            row = self._rows.get(self._key(tenant_id, number))
            if row is None:
                return None
            self._roll_day(row)
            return replace(row)

    def list(self, tenant_id: str) -> List[PoolNumber]:
        t = (tenant_id or "").strip()
        if not t:
            raise ValueError("number_pool: empty tenant_id (fail-closed)")
        prefix = f"{t}::"
        with self._lock:
            out = []
            for k, row in self._rows.items():
                if k.startswith(prefix):
                    self._roll_day(row)
                    out.append(replace(row))
            return out

    def lease(self, tenant_id: str, number: str, *, cap: int, conc: int) -> bool:
        """Atomically reserve one dial slot on `number`: increments in_flight +
        used_today iff active, under daily cap, AND under concurrency. Returns False
        if the number can't take a call right now (caller picks another)."""
        with self._lock:
            row = self._rows.get(self._key(tenant_id, number))
            if row is None or row.status != ACTIVE:
                return False
            self._roll_day(row)
            eff_cap = row.daily_cap or cap
            eff_conc = row.concurrency or conc
            if eff_cap > 0 and row.used_today >= eff_cap:
                return False
            if eff_conc > 0 and row.in_flight >= eff_conc:
                return False
            row.in_flight += 1
            row.used_today += 1
            row.last_dial_mono = self._clock()
            return True

    def release(self, tenant_id: str, number: str) -> None:
        with self._lock:
            row = self._rows.get(self._key(tenant_id, number))
            if row is None:
                return
            row.in_flight = max(0, row.in_flight - 1)

    # test peek
    def snapshot(self, tenant_id: str) -> List[PoolNumber]:
        return self.list(tenant_id)


class NumberPool:
    """Tenant-scoped facade over a NumberPoolStore. Adds the config defaults + the
    cooldown gate (the store tracks last_dial; the pool decides if enough time passed)
    + the 'available right now' query the router consumes. Construct once per process."""

    def __init__(self, cfg: Optional[TelephonyOpsConfig] = None, *,
                 store: Optional[NumberPoolStore] = None,
                 clock: Optional[Callable[[], float]] = None):
        self.cfg = cfg or TelephonyOpsConfig.from_env()
        self._clock = clock or time.monotonic
        self.store = store or InMemoryNumberPoolStore(clock=self._clock)

    # ----------------------------------------------------- CRUD (UI) #
    def add_number(self, tenant_id: str, number: str, *, trunk_id: str = "",
                   series: str = "", daily_cap: int = 0, concurrency: int = 0,
                   cooldown_s: int = 0, status: str = ACTIVE) -> PoolNumber:
        """Add (or update) a number in the tenant's fleet — the UI 'add number' action."""
        if not (number or "").strip():
            raise ValueError("add_number: empty number")
        return self.store.add(PoolNumber(
            tenant_id=tenant_id, number=number.strip(), trunk_id=trunk_id, series=series,
            daily_cap=int(daily_cap or 0), concurrency=int(concurrency or 0),
            cooldown_s=int(cooldown_s or 0), status=status,
        ))

    def remove_number(self, tenant_id: str, number: str) -> bool:
        return self.store.remove(tenant_id, number)

    def pause(self, tenant_id: str, number: str) -> bool:
        return self.store.set_status(tenant_id, number, PAUSED)

    def resume(self, tenant_id: str, number: str) -> bool:
        return self.store.set_status(tenant_id, number, ACTIVE)

    def disable(self, tenant_id: str, number: str) -> bool:
        return self.store.set_status(tenant_id, number, DISABLED)

    def list_numbers(self, tenant_id: str) -> List[PoolNumber]:
        return self.store.list(tenant_id)

    # ----------------------------------------------------- gates #
    def _cooldown_ok(self, row: PoolNumber) -> bool:
        cd = row.cooldown_s or self.cfg.cooldown_seconds
        if cd <= 0 or row.last_dial_mono <= 0.0:
            return True
        return (self._clock() - row.last_dial_mono) >= cd

    def can_dial(self, tenant_id: str, number: str) -> bool:
        """Is this specific number eligible RIGHT NOW (active, under cap+concurrency,
        off cooldown)? Read-only — does not lease."""
        row = self.store.get(tenant_id, number)
        if row is None or not row.is_dialable_state():
            return False
        eff_cap = row.daily_cap or self.cfg.per_number_daily_cap
        eff_conc = row.concurrency or self.cfg.per_number_concurrency
        if eff_cap > 0 and row.used_today >= eff_cap:
            return False
        if eff_conc > 0 and row.in_flight >= eff_conc:
            return False
        return self._cooldown_ok(row)

    def available_numbers(self, tenant_id: str, *, avoid: Optional[List[str]] = None) -> List[PoolNumber]:
        """All numbers that can take a call right now, least-loaded first (used_today
        then in_flight), skipping any in `avoid` (the router passes unhealthy numbers).
        This is what the AdaptiveRouter ranks."""
        avoid = set(avoid or [])
        out: List[PoolNumber] = []
        for row in self.store.list(tenant_id):
            if row.number in avoid:
                continue
            if self.can_dial(tenant_id, row.number):
                out.append(row)
        out.sort(key=lambda r: (r.used_today, r.in_flight, r.number))
        return out

    # ----------------------------------------------------- lease / release #
    def lease(self, tenant_id: str, number: str) -> bool:
        """Reserve a dial slot (atomic cap+concurrency check in the store). The
        cooldown gate is checked here first (the store doesn't know the cooldown)."""
        if not self._cooldown_ok_by_number(tenant_id, number):
            return False
        return self.store.lease(tenant_id, number,
                                cap=self.cfg.per_number_daily_cap,
                                conc=self.cfg.per_number_concurrency)

    def _cooldown_ok_by_number(self, tenant_id: str, number: str) -> bool:
        row = self.store.get(tenant_id, number)
        return bool(row) and self._cooldown_ok(row)

    def release(self, tenant_id: str, number: str) -> None:
        """Free a dial slot when the call finalizes (decrements in_flight)."""
        self.store.release(tenant_id, number)
