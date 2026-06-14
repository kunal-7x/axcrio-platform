"""trunk_registry.concurrency — IN-PROCESS per-trunk concurrency + velocity throttle (T2, NEW).

Spec: design/TELEPHONY-INDEPENDENCE-PLAN.md §2.4 (per-trunk concurrency is IN-PROCESS, NOT
Redis) + §3 red-team A1/A2/C-rel + §2.5 velocity throttle + §3 A4 (box-global cap).

WHY IN-PROCESS, NOT REDIS (the red-team C-rel correction — load-bearing):
  The box runs uvicorn `--workers 1` (ratelimit.py:13), so the in-proc ACTIVE_CALLS dict
  (caller.py:535) is ALREADY the authoritative, correct counter. The rate-limiter's `:6380`
  Redis is FAIL-OPEN — a hard channel cap on it would silently VANISH on a Redis hiccup and
  storm 486s. So the per-trunk counter lives here, in-process, behind a threading.Lock:
    * NO A1 leak: acquire/release are paired in a try/finally at the call site, so a channel
      can never get stuck "full" on a crash/raise.
    * NO A2 TOCTOU race: acquire() checks-and-increments ATOMICALLY under the lock (not
      check-then-incr), so a burst can never oversell the cap.
  Redis is introduced ONLY if/when the box goes multi-worker, and THEN fail-CLOSED for the cap.

WHAT IT ENFORCES (all under one lock, all atomic):
  1. per-trunk `max_concurrency` channel cap (GSM = #SIMs hard 1/SIM; SIP = the elastic ceiling).
  2. a BOX-GLOBAL cap (red-team A4) — the sum of in-flight calls across ALL trunks in this
     process never exceeds ~90 (below the LiveKit RTP ceiling ~100) regardless of per-trunk caps.
  3. a VELOCITY throttle (red-team velocity — the STRONGER spam signal than daily volume):
       * per-DID minimum inter-call spacing (default 8s) — refuses to fire two calls on one DID
         closer than the spacing,
       * a per-DID calls/hour ceiling (default 200).

USAGE (the dial loop, T5 — behind the flag):
    lease = concurrency.acquire(tenant_id, trunk_id, did, max_concurrency=trunk.max_concurrency)
    if not lease.ok:
        ... skip this trunk/DID this tick (reason: 'trunk_full'|'box_full'|'velocity'|'gsm_did_busy')
    else:
        try:
            ... place the call ...
        finally:
            concurrency.release(lease)

This module holds ZERO PG / network state and NEVER raises. A test can inject a fake clock.
"""
from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Callable, Deque, Dict, Optional, Tuple

from .config import registry_config


# ---------------------------------------------------------------------------
# in-process state (one worker -> authoritative). All access under _LOCK.
# ---------------------------------------------------------------------------
_LOCK = threading.Lock()

# per-trunk active channel count: trunk_key -> in-flight count.
_TRUNK_ACTIVE: Dict[str, int] = {}
# per-DID active count (a GSM SIM must be 1-in-flight; red-team A3): did_key -> in-flight count.
_DID_ACTIVE: Dict[str, int] = {}
# box-global in-flight (sum across all trunks in THIS process).
_BOX_ACTIVE: int = 0
# per-DID recent call start timestamps (a rolling deque for the velocity throttle).
_DID_STARTS: Dict[str, Deque[float]] = {}

_VELOCITY_WINDOW_S = 3600  # the velocity ceiling is "per hour"


def _tkey(tenant_id: str, trunk_id: str) -> str:
    return f"{tenant_id or ''}::{trunk_id or ''}"


def _dkey(tenant_id: str, trunk_id: str, did: str) -> str:
    return f"{tenant_id or ''}::{trunk_id or ''}::{did or ''}"


@dataclass
class Lease:
    """The handle returned by acquire(). `ok` is the ONLY thing the dial loop branches on.
    On ok=True the caller MUST release(lease) in a finally. On ok=False, `reason` says why
    (the loop skips this trunk/DID this tick) — NO channel was reserved."""
    ok: bool
    reason: str = ""
    tenant_id: str = ""
    trunk_id: str = ""
    did: str = ""
    _tkey: str = field(default="", repr=False)
    _dkey: str = field(default="", repr=False)
    _counted_did: bool = field(default=False, repr=False)  # did this lease take a _DID_ACTIVE slot?


def acquire(
    tenant_id: str,
    trunk_id: str,
    did: str = "",
    *,
    max_concurrency: int = 1,
    is_gsm: bool = False,
    now_fn: Callable[[], float] = time.time,
) -> Lease:
    """Atomically check-and-reserve ONE channel on (tenant, trunk[, did]). Enforces, in order,
    all under one lock (so a burst can never oversell — red-team A2):
      1. velocity: per-DID min spacing + per-DID calls/hour ceiling,
      2. GSM per-DID in-flight == 0 (a single SIM is 1 call — red-team A3),
      3. per-trunk max_concurrency cap,
      4. box-global cap (red-team A4).
    Returns Lease(ok=True) with a reserved channel (caller MUST release), or Lease(ok=False,
    reason=...) with NOTHING reserved. NEVER raises."""
    global _BOX_ACTIVE
    cfg = registry_config()
    box_cap = int(cfg["box_global_concurrency"])
    min_spacing = float(cfg["velocity_min_spacing_s"])
    per_hour = int(cfg["velocity_calls_per_hour"])
    tkey = _tkey(tenant_id, trunk_id)
    dkey = _dkey(tenant_id, trunk_id, did)
    now = now_fn()

    with _LOCK:
        # 1) velocity throttle (per DID) — only if a DID is given.
        if did:
            starts = _DID_STARTS.get(dkey)
            if starts:
                # prune the rolling hour window
                while starts and (now - starts[0]) > _VELOCITY_WINDOW_S:
                    starts.popleft()
                if starts and (now - starts[-1]) < min_spacing:
                    return Lease(ok=False, reason="velocity_spacing", tenant_id=tenant_id,
                                 trunk_id=trunk_id, did=did)
                if per_hour > 0 and len(starts) >= per_hour:
                    return Lease(ok=False, reason="velocity_hourly_cap", tenant_id=tenant_id,
                                 trunk_id=trunk_id, did=did)

        # 2) GSM: a single SIM/DID can only carry ONE call (red-team A3).
        counted_did = False
        if did:
            in_flight_did = _DID_ACTIVE.get(dkey, 0)
            if is_gsm and in_flight_did >= 1:
                return Lease(ok=False, reason="gsm_did_busy", tenant_id=tenant_id,
                             trunk_id=trunk_id, did=did)

        # 3) per-trunk concurrency cap.
        cap = max(1, int(max_concurrency or 1))
        if _TRUNK_ACTIVE.get(tkey, 0) >= cap:
            return Lease(ok=False, reason="trunk_full", tenant_id=tenant_id, trunk_id=trunk_id,
                         did=did)

        # 4) box-global cap.
        if box_cap > 0 and _BOX_ACTIVE >= box_cap:
            return Lease(ok=False, reason="box_full", tenant_id=tenant_id, trunk_id=trunk_id,
                         did=did)

        # ---- reserve (all checks passed) ----
        _TRUNK_ACTIVE[tkey] = _TRUNK_ACTIVE.get(tkey, 0) + 1
        _BOX_ACTIVE += 1
        if did:
            _DID_ACTIVE[dkey] = _DID_ACTIVE.get(dkey, 0) + 1
            counted_did = True
            dq = _DID_STARTS.setdefault(dkey, deque())
            dq.append(now)
            # keep the deque bounded to the velocity window (memory hygiene)
            while dq and (now - dq[0]) > _VELOCITY_WINDOW_S:
                dq.popleft()
        return Lease(ok=True, reason="ok", tenant_id=tenant_id, trunk_id=trunk_id, did=did,
                     _tkey=tkey, _dkey=dkey, _counted_did=counted_did)


def release(lease: Optional[Lease]) -> None:
    """Release a channel reserved by acquire(). Idempotent + safe to call with a not-ok / None
    lease (a no-op). Paired with acquire in a try/finally so a channel can NEVER leak (red-team
    A1). NEVER raises."""
    global _BOX_ACTIVE
    if lease is None or not lease.ok:
        return
    with _LOCK:
        tkey = lease._tkey
        if tkey:
            _TRUNK_ACTIVE[tkey] = max(0, _TRUNK_ACTIVE.get(tkey, 0) - 1)
            if _TRUNK_ACTIVE[tkey] == 0:
                _TRUNK_ACTIVE.pop(tkey, None)
        _BOX_ACTIVE = max(0, _BOX_ACTIVE - 1)
        if lease._counted_did and lease._dkey:
            _DID_ACTIVE[lease._dkey] = max(0, _DID_ACTIVE.get(lease._dkey, 0) - 1)
            if _DID_ACTIVE[lease._dkey] == 0:
                _DID_ACTIVE.pop(lease._dkey, None)
        # mark released so a double-release is a no-op
        lease.ok = False


def snapshot(tenant_id: str = "", trunk_id: str = "") -> dict:
    """A JSON-able, non-secret diagnostic for the /telephony concurrency gauge. With a trunk_id
    given, returns that trunk's in-flight + cap context; else the box-global view."""
    with _LOCK:
        out = {"box_active": _BOX_ACTIVE, "box_cap": int(registry_config()["box_global_concurrency"])}
        if trunk_id:
            tkey = _tkey(tenant_id, trunk_id)
            out["trunk_active"] = _TRUNK_ACTIVE.get(tkey, 0)
        return out


def reset_all() -> None:
    """Test helper: clear ALL in-memory concurrency state (no production caller)."""
    global _BOX_ACTIVE
    with _LOCK:
        _TRUNK_ACTIVE.clear()
        _DID_ACTIVE.clear()
        _DID_STARTS.clear()
        _BOX_ACTIVE = 0
