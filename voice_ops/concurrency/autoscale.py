"""voice_ops.concurrency.autoscale — AutoscaleSignal: the worker-pool scale signal.

The W18 gap names a missing "worker-pool autoscale SIGNAL (CPU ~60-70%, warm pool)".
This module turns the live AdmissionController snapshot + a CPU sample into a
`ScaleRecommendation` and EMITS it on the W8 EventBus so an external autoscaler
(DO/k8s HPA, a cron, or the founder's panel) can add/remove worker processes BEFORE
the single worker hits its LiveKit `load_threshold` (0.70) and starts silently
refusing dispatches.

The recommendation logic (design/W24-CONCURRENCY-SEAM.md §autoscale):
  - utilisation = active_calls / total_worker_capacity
  - SCALE UP when CPU >= scale_up_cpu (default 0.55 — BELOW the 0.70 load_threshold,
    so capacity is added before the worker rejects) OR utilisation >= 0.80.
  - SCALE DOWN when CPU < scale_down_cpu (0.30) AND utilisation < 0.50, never below
    `warm_pool_min` warm workers (a burst must never hit zero-warm).
  - desired_workers is derived from utilisation headroom and clamped to
    [warm_pool_min, hard_max].

This is ADVISORY (like W12 CapacityPlanner): it never blocks a call. CPU is supplied
by the caller (lazy psutil read at the seam) so this module imports nothing heavy.
Pure stdlib; zero droplet_work / livekit / redis at module load.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Optional

from .config import ConcurrencyConfig

log = logging.getLogger("voice_ops.concurrency.autoscale")

SCALE_UP = "scale_up"
SCALE_DOWN = "scale_down"
HOLD = "hold"


@dataclass(frozen=True)
class ScaleRecommendation:
    """Advisory verdict for the worker fleet."""

    action: str                 # scale_up | scale_down | hold
    current_workers: int
    desired_workers: int
    active_calls: int
    capacity: int
    utilisation: float          # active / capacity, [0,1]
    cpu: float                  # observed CPU load [0,1]
    warm_pool_min: int
    reason: str = ""

    @property
    def delta(self) -> int:
        return self.desired_workers - self.current_workers


class AutoscaleSignal:
    """Stateless recommender + W8 emitter. Construct once; call `recommend(...)` on a
    schedule (every N seconds) with the AdmissionController snapshot + a CPU sample."""

    def __init__(
        self,
        cfg: Optional[ConcurrencyConfig] = None,
        *,
        event_bus: Optional[object] = None,
        hard_max_workers: int = 50,
    ) -> None:
        self.cfg = cfg or ConcurrencyConfig.from_env()
        self.event_bus = event_bus
        self.hard_max_workers = max(1, int(hard_max_workers))

    def recommend(
        self,
        *,
        active_calls: int,
        current_workers: Optional[int] = None,
        cpu: float = 0.0,
        per_worker_cap: Optional[int] = None,
    ) -> ScaleRecommendation:
        """Compute the scale verdict. `active_calls` + `cpu` are the live signals;
        defaults come from config. Inputs are clamped to safe floors; never raises."""
        c = self.cfg
        cur = max(1, int(current_workers if current_workers is not None else c.worker_count))
        pcap = max(1, int(per_worker_cap if per_worker_cap is not None else c.worker_slot_cap))
        active = max(0, int(active_calls))
        cpu = max(0.0, min(1.0, float(cpu)))
        capacity = cur * pcap
        util = (active / capacity) if capacity > 0 else 1.0

        warm = max(1, c.warm_pool_min)
        action, reason = HOLD, "within target band"
        desired = cur

        # SCALE UP: add capacity BEFORE the worker hits load_threshold (0.70).
        if cpu >= c.scale_up_cpu or util >= 0.80:
            # size to keep utilisation under ~0.65 of capacity at this load.
            need_by_util = int(math.ceil(active / max(1, int(pcap * 0.65)))) if active else cur
            need_by_cpu = cur + 1 if cpu >= c.scale_up_cpu else cur
            desired = max(cur + 1, need_by_util, need_by_cpu)
            action = SCALE_UP
            reason = (f"cpu={cpu:.2f}>=up({c.scale_up_cpu}) or util={util:.2f}>=0.80 "
                      f"-> add capacity before load_threshold")
        # SCALE DOWN: only when BOTH CPU and utilisation are low; never below warm pool.
        elif cpu < c.scale_down_cpu and util < 0.50 and cur > warm:
            desired = max(warm, cur - 1)
            action = SCALE_DOWN if desired < cur else HOLD
            reason = (f"cpu={cpu:.2f}<down({c.scale_down_cpu}) and util={util:.2f}<0.50 "
                      f"-> shed one (floor warm_pool={warm})")

        desired = max(warm, min(self.hard_max_workers, desired))
        if desired == cur and action != HOLD:
            action, reason = HOLD, reason + " (already at desired)"

        return ScaleRecommendation(
            action=action, current_workers=cur, desired_workers=desired,
            active_calls=active, capacity=capacity, utilisation=round(util, 3),
            cpu=round(cpu, 3), warm_pool_min=warm, reason=reason,
        )

    async def emit(self, rec: ScaleRecommendation, tenant_id: str = "_fleet") -> None:
        """Fire-and-forget W8 emit of the recommendation (fleet-scoped). NEVER blocks/
        raises — a dead bus just means no autoscale telemetry this tick. Uses a
        fleet pseudo-tenant stream so the signal is isolated from per-tenant call data."""
        bus = self.event_bus
        if bus is None:
            return
        try:
            from voice_kernel.contracts import Event
            from voice_kernel.events.timeutil import now_utc_iso
            ev = Event(
                name="autoscale_signal", call_id=f"fleet:{rec.action}",
                tenant_id=(tenant_id or "_fleet"), ts_iso=now_utc_iso(),
                payload={
                    "action": rec.action, "current_workers": rec.current_workers,
                    "desired_workers": rec.desired_workers, "delta": rec.delta,
                    "active_calls": rec.active_calls, "capacity": rec.capacity,
                    "utilisation": rec.utilisation, "cpu": rec.cpu,
                    "warm_pool_min": rec.warm_pool_min, "reason": rec.reason,
                },
            )
            await bus.emit(ev)
        except Exception as exc:
            log.debug("autoscale emit non-fatal: %r", exc)

    @staticmethod
    def sample_cpu() -> float:
        """Best-effort CPU load in [0,1] (LAZY psutil import; 0.0 if unavailable).
        The seam calls this at the box; unit tests inject cpu directly so this is
        never on the test path. Returns a 1-core-normalised load average."""
        try:
            import os
            import psutil  # lazy: never imported at module load
            return max(0.0, min(1.0, psutil.cpu_percent(interval=None) / 100.0))
        except Exception:
            try:
                import os
                la = os.getloadavg()[0]  # 1-min load average
                ncpu = os.cpu_count() or 1
                return max(0.0, min(1.0, la / ncpu))
            except Exception:
                return 0.0
