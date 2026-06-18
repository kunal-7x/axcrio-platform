"""voice_ops.telephony.capacity_planner — the Campaign Capacity Planner (W12 #1).

Answers ONE founder question before a campaign runs: *given these leads, these phone
numbers, this calling window, this concurrency, and a realistic answer-rate — how
many calls can I SAFELY place today, and will I run out of capacity?* It returns a
`CapacityPlan` with a safe daily target + a WARNING when the lead list exceeds what
the configured numbers/window/concurrency can deliver.

This is ADVISORY (the seam attaches the plan to the job dict + logs it; it never
blocks a dial — that is the compliance engine's job). The math is pure + offline:

  per-number throughput in the window
    = floor( window_seconds / seconds_per_dial_slot ) capped by the per-number daily cap,
      where seconds_per_dial_slot accounts for concurrency:
        effective_dial_seconds = answer_rate*avg_call_seconds + dial_overhead_seconds
        slot_seconds           = effective_dial_seconds / max(1, per_number_concurrency)
  fleet capacity = sum over numbers of per-number throughput
  safe_daily_target = min(leads, fleet_capacity)
  insufficient    = leads > fleet_capacity

PURE module: stdlib + the package config only. NO I/O, NO droplet_work, NEVER raises
into the caller (clamps bad input to safe floors). A test pins the assumptions and
asserts: warns when insufficient, sizes the fleet, never returns a target > leads.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import List, Optional

from .config import TelephonyOpsConfig

log = logging.getLogger("voice_ops.telephony.capacity_planner")


@dataclass(frozen=True)
class CapacityPlan:
    """The planner's verdict. `safe_daily_target` is min(leads, fleet_capacity).
    `insufficient` is True when the lead list cannot be cleared today with the given
    numbers/window. `warning` is a human one-liner for the panel/log when insufficient
    (else '')."""

    leads: int
    numbers: int
    window_minutes: int
    fleet_capacity: int                 # max safe dials the fleet can place in the window
    per_number_capacity: int            # max safe dials ONE number can place in the window
    safe_daily_target: int              # min(leads, fleet_capacity)
    insufficient: bool
    days_to_clear: int                  # ceil(leads / fleet_capacity), >=1
    suggested_numbers: int              # numbers needed to clear the leads in ONE window
    warning: str = ""
    reasons: List[str] = field(default_factory=list)


class CapacityPlanner:
    """Stateless planner. Construct once (cheap): `CapacityPlanner(cfg)`."""

    def __init__(self, cfg: Optional[TelephonyOpsConfig] = None):
        self.cfg = cfg or TelephonyOpsConfig.from_env()

    # ----------------------------------------------------------------- math #
    def _slot_seconds(self, *, answer_rate: float, avg_call_seconds: int,
                      dial_overhead_seconds: int, per_number_concurrency: int) -> float:
        """Seconds one number 'spends' per dial slot, amortised by concurrency.
        A dial slot is the answer-weighted talk time plus the ring/setup/wrap
        overhead, divided across the lines the number can run at once."""
        eff = (max(0.0, min(1.0, answer_rate)) * max(1, avg_call_seconds)
               + max(0, dial_overhead_seconds))
        conc = max(1, per_number_concurrency)
        return max(1.0, eff / conc)

    def per_number_capacity(self, *, window_minutes: int,
                            answer_rate: Optional[float] = None,
                            avg_call_seconds: Optional[int] = None,
                            dial_overhead_seconds: Optional[int] = None,
                            per_number_concurrency: Optional[int] = None,
                            per_number_daily_cap: Optional[int] = None) -> int:
        """Safe number of dials ONE number can place inside `window_minutes`, capped
        by its per-number daily cap. All assumptions default to the config."""
        c = self.cfg
        ar = c.answer_rate if answer_rate is None else answer_rate
        acs = c.avg_call_seconds if avg_call_seconds is None else avg_call_seconds
        doh = c.dial_overhead_seconds if dial_overhead_seconds is None else dial_overhead_seconds
        conc = c.per_number_concurrency if per_number_concurrency is None else per_number_concurrency
        cap = c.per_number_daily_cap if per_number_daily_cap is None else per_number_daily_cap

        window_seconds = max(0, int(window_minutes)) * 60
        slot = self._slot_seconds(answer_rate=ar, avg_call_seconds=acs,
                                  dial_overhead_seconds=doh, per_number_concurrency=conc)
        by_time = int(math.floor(window_seconds / slot)) if slot > 0 else 0
        return max(0, min(by_time, max(0, int(cap))))

    # ----------------------------------------------------------------- plan #
    def plan(
        self,
        *,
        leads: int,
        numbers: int,
        window_minutes: int,
        answer_rate: Optional[float] = None,
        avg_call_seconds: Optional[int] = None,
        dial_overhead_seconds: Optional[int] = None,
        per_number_concurrency: Optional[int] = None,
        per_number_daily_cap: Optional[int] = None,
    ) -> CapacityPlan:
        """Compute the safe daily target + warn-if-insufficient. Inputs are clamped to
        safe floors (negative/None -> 0/defaults); NEVER raises."""
        leads = max(0, int(leads or 0))
        numbers = max(0, int(numbers or 0))
        window_minutes = max(0, int(window_minutes or 0))

        per_num = self.per_number_capacity(
            window_minutes=window_minutes, answer_rate=answer_rate,
            avg_call_seconds=avg_call_seconds, dial_overhead_seconds=dial_overhead_seconds,
            per_number_concurrency=per_number_concurrency,
            per_number_daily_cap=per_number_daily_cap,
        )
        fleet = per_num * numbers
        safe = min(leads, fleet)
        insufficient = leads > fleet
        days_to_clear = max(1, int(math.ceil(leads / fleet))) if fleet > 0 else (1 if leads == 0 else 9999)
        suggested = (max(numbers, int(math.ceil(leads / per_num)))
                     if per_num > 0 else (numbers if leads == 0 else 9999))

        reasons: List[str] = []
        warning = ""
        if numbers == 0 and leads > 0:
            insufficient = True
            warning = ("No phone numbers in the pool — add at least one number before running "
                       f"this campaign ({leads} leads waiting).")
            reasons.append("no_numbers")
        elif window_minutes == 0 and leads > 0:
            insufficient = True
            warning = "Calling window is zero-length — widen the window before running."
            reasons.append("zero_window")
        elif insufficient:
            shortfall = leads - fleet
            warning = (
                f"Insufficient capacity: {leads} leads but the fleet can safely place only "
                f"~{fleet} calls in this {window_minutes//60}h{window_minutes%60:02d}m window "
                f"({numbers} number(s) × ~{per_num} each). {shortfall} leads will spill — "
                f"add ~{max(0, suggested - numbers)} more number(s) to clear in one window, "
                f"or expect ~{days_to_clear} day(s) to clear at this size."
            )
            reasons.append("fleet_capacity_exceeded")

        plan = CapacityPlan(
            leads=leads, numbers=numbers, window_minutes=window_minutes,
            fleet_capacity=fleet, per_number_capacity=per_num,
            safe_daily_target=safe, insufficient=insufficient,
            days_to_clear=days_to_clear, suggested_numbers=suggested,
            warning=warning, reasons=reasons,
        )
        if insufficient:
            log.info("capacity plan WARN: %s", warning)
        return plan
