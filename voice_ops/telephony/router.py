"""voice_ops.telephony.router — the AdaptiveRouter (W12 #4: pick the next number).

The single decision the dial loop asks per call: *which phone number do I originate
THIS call from, right now?* The router combines three independent signals and returns
a number (with its trunk_id + chosen DID) or None (nothing safe is available — the
caller must queue the lead, never force a dial):

  1. CAPACITY (number_pool.available_numbers): only numbers that are active, under
     their daily cap, under their concurrency limit, and OFF cooldown. The pool returns
     these least-loaded-first.
  2. HEALTH (health.SpamReputation): QUARANTINED numbers are excluded entirely (added
     to the pool's `avoid` list); DEGRADED numbers are de-prioritised (only used when
     no HEALTHY number is free) so a spam-risk number gets auto-reduced traffic and a
     recovered one auto-increases.
  3. The atomic LEASE: the chosen number is leased in the pool (in_flight + used_today
     bumped under one lock) BEFORE it's returned — so two concurrent route calls can
     never both pick the same number past its concurrency limit (the no-overload
     invariant is enforced at lease time, not by hope).

NEVER overloads (capacity gate + atomic lease), NEVER violates a cooldown (pool gate),
NEVER dials a resting number (health gate). If the lease loses a race (another caller
took the last slot), the router falls through to the next candidate, then returns None.

PURE: stdlib + the sibling modules; NO droplet_work / livekit; NEVER raises into the
dial loop (returns None on any internal error, which the seam treats as 'queue lead').
The seam doc maps this onto caller.py's single SIP dial point (replacing the hard-wired
TRUNK) and shows how `record_outcome` feeds health + releases the pool slot.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List, Optional

from .config import TelephonyOpsConfig
from .health import DEGRADED, HEALTHY, SpamReputation
from .number_pool import NumberPool, PoolNumber

log = logging.getLogger("voice_ops.telephony.router")


@dataclass(frozen=True)
class RouteChoice:
    """The router's pick: which number/trunk to originate from. Returned ONLY after
    the number is atomically leased — the caller MUST call `record_outcome` (which
    releases the lease) when the call finalizes, even on failure."""
    number: str
    trunk_id: str
    health_state: str
    used_today: int
    in_flight: int


class AdaptiveRouter:
    """Stateful only via its injected pool + health scorer. Construct once per process:
    `AdaptiveRouter(cfg, pool=NumberPool(...), health=SpamReputation(...))`."""

    def __init__(self, cfg: Optional[TelephonyOpsConfig] = None, *,
                 pool: Optional[NumberPool] = None,
                 health: Optional[SpamReputation] = None):
        self.cfg = cfg or TelephonyOpsConfig.from_env()
        self.pool = pool or NumberPool(self.cfg)
        self.health = health or SpamReputation(self.cfg)

    # ------------------------------------------------------------- pick #
    def pick_next(self, tenant_id: str) -> Optional[RouteChoice]:
        """Choose + atomically LEASE the next number for this tenant. Returns a
        RouteChoice or None (queue the lead). Order: HEALTHY candidates first
        (least-loaded), then DEGRADED as last-resort; QUARANTINED never considered."""
        try:
            candidates = self._ranked_candidates(tenant_id)
        except Exception as exc:  # noqa: BLE001 — never raise into the dial loop
            log.info("router.pick_next ranking failed (queueing lead): %r", exc)
            return None

        for row in candidates:
            # Atomic lease — this is the no-overload fence. If we lose the race
            # (another route took the last slot/cap), try the next candidate.
            if self.pool.lease(tenant_id, row.number):
                snap = self.health.snapshot(row.number)
                # re-read the leased counts for an accurate choice (in_flight just bumped)
                leased = self.pool.store.get(tenant_id, row.number)
                return RouteChoice(
                    number=row.number,
                    trunk_id=(leased.trunk_id if leased else row.trunk_id),
                    health_state=snap.state,
                    used_today=(leased.used_today if leased else row.used_today),
                    in_flight=(leased.in_flight if leased else row.in_flight),
                )
        return None

    def _ranked_candidates(self, tenant_id: str) -> List[PoolNumber]:
        """Capacity-eligible numbers, health-filtered + health-ranked.
          * exclude QUARANTINED (resting) numbers via the pool's avoid list;
          * put HEALTHY before DEGRADED (DEGRADED = reduced traffic / last-resort);
          * within a band, the pool already ordered least-loaded-first."""
        # numbers the pool currently has, to ask health which are resting.
        all_nums = [r.number for r in self.pool.list_numbers(tenant_id)]
        resting = set(self.health.unhealthy_numbers(all_nums))
        avail = self.pool.available_numbers(tenant_id, avoid=list(resting))

        healthy: List[PoolNumber] = []
        degraded: List[PoolNumber] = []
        for row in avail:
            state = self.health.snapshot(row.number).state
            if state == DEGRADED:
                degraded.append(row)
            else:  # HEALTHY (or unproven, which scores HEALTHY)
                healthy.append(row)
        return healthy + degraded

    # --------------------------------------------------------- outcome #
    def record_outcome(self, tenant_id: str, choice_or_number, *, answered: bool,
                       duration_s: float = 0.0, outcome: str = "") -> None:
        """Feed a finalized call back: (1) release the pool lease (decrement in_flight),
        (2) record the outcome in the health scorer so the number's reputation + state
        update for the NEXT routing decision. Accepts a RouteChoice or a bare number.
        NEVER raises into the dial loop."""
        number = choice_or_number.number if isinstance(choice_or_number, RouteChoice) else str(choice_or_number)
        try:
            self.pool.release(tenant_id, number)
        except Exception as exc:  # noqa: BLE001
            log.info("router.record_outcome pool release failed: %r", exc)
        try:
            self.health.record(number, outcome, answered=answered, duration_s=duration_s)
        except Exception as exc:  # noqa: BLE001
            log.info("router.record_outcome health record failed: %r", exc)
