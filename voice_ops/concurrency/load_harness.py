"""voice_ops.concurrency.load_harness — the synthetic concurrency LOAD HARNESS (W24).

Promotes the founder's "replace 500 telecallers" concurrency claim from eval-DEBT to
a HARD, runnable deploy gate. It drives the AdmissionController with 50 / 100 / 200
SIMULATED concurrent calls — NO real PSTN, NO real LiveKit, NO real provider keys —
and asserts the three properties that make the thesis true:

  1. NO OVERSUBSCRIPTION — at no instant do admitted-and-live calls exceed the
     configured worker/global/tenant capacity. (The whole point: the box must never
     accept call #N+1 when only N slots exist.)
  2. GRACEFUL PACING — excess demand is QUEUED/PACED (a clean refusal the dial loop
     retries), NEVER failed mid-stream and NEVER errored. Offered load >> capacity
     still drains: every call eventually admits as earlier calls release.
  3. ADMISSION LATENCY — reports p50 / p95 / max admission decision latency so a
     regression in the gate's hot path is visible. The gate is pure-memory so this is
     microseconds; the assert is a generous ceiling that only a real bug trips.

A "call" is a coroutine: reserve() -> (if admitted) hold for a simulated talk-time ->
release(); (if queued/paced) back off and retry until admitted or a deadline. A
LiveCounter tracks the live admitted set and records the running max so
oversubscription is detected the instant it would happen.

This module is importable+runnable as a library (pytest calls `run_load`) AND as a
script (`python -m voice_ops.concurrency.load_harness 100`). Pure asyncio + stdlib;
mock providers; zero droplet_work / livekit / redis. Deterministic enough to gate CI.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import List, Optional

from .admission import ADMITTED, AdmissionController
from .config import ConcurrencyConfig

log = logging.getLogger("voice_ops.concurrency.load_harness")


# --------------------------------------------------------------------------- #
# Mock W13 key pool: always returns a healthy key (never the bottleneck here so
# the harness measures the SLOT/WORKER gate, not key exhaustion). A second profile
# can return None to exercise the LOUD pool-exhausted -> PACE path.
# --------------------------------------------------------------------------- #
class _MockKeyPool:
    def __init__(self, fp: str = "fp-mock", exhausted: bool = False):
        self._fp = fp
        self._exhausted = exhausted

    def pick(self) -> Optional[str]:
        return None if self._exhausted else self._fp


class _LiveCounter:
    """Tracks the live admitted set and the running max concurrency observed —
    asyncio is single-threaded so increments/decrements are atomic between awaits.

    Red-team fold (W24, finding #1): the global `max_live` alone is a DISHONEST gate
    when the binding constraint is a per-key/per-tenant pool — a leaked per-key TTS
    slot or per-tenant slot would never exceed the (huge) global cap. So at every
    admit we also sample the controller's snapshot and record the PEAK in_flight of
    every per-tenant slot pool and every per-TTS-key slot pool. `binding_overflow`
    later asserts each peak stayed within ITS pool's capacity, not just the aggregate."""

    def __init__(self, ctrl: Optional["AdmissionController"] = None) -> None:
        self.live = 0
        self.max_live = 0
        self._ctrl = ctrl
        # resource_name -> {"cap": int, "peak": int}
        self.peak_by_pool: dict = {}

    def _sample(self) -> None:
        """Record peak per-pool in_flight from the live controller snapshot."""
        if self._ctrl is None:
            return
        snap = self._ctrl.snapshot()
        for group in ("tenants", "tts_keys"):
            for name, s in (snap.get(group) or {}).items():
                key = f"{group}:{name}"
                cur = self.peak_by_pool.get(key)
                inflight = int(s.get("in_flight", 0))
                cap = int(s.get("capacity", 0))
                if cur is None:
                    self.peak_by_pool[key] = {"cap": cap, "peak": inflight}
                elif inflight > cur["peak"]:
                    cur["peak"] = inflight

    def enter(self) -> None:
        self.live += 1
        if self.live > self.max_live:
            self.max_live = self.live
        self._sample()  # capture per-pool peaks at the moment a call goes live

    def leave(self) -> None:
        self.live = max(0, self.live - 1)

    def binding_overflow(self) -> list:
        """Return [(pool, peak, cap)] for every per-key/per-tenant pool whose peak
        in_flight EXCEEDED its own capacity. Empty list = honest green."""
        return [
            (k, v["peak"], v["cap"])
            for k, v in self.peak_by_pool.items()
            if v["cap"] > 0 and v["peak"] > v["cap"]
        ]


@dataclass
class LoadResult:
    """The harness verdict for one (concurrency, capacity) run."""

    offered: int
    capacity: int
    completed: int               # calls that ultimately admitted + ran + released
    admitted_first_try: int
    paced_events: int            # total QUEUE/PACE refusals across all retries
    errored: int                 # calls that raised or never admitted before deadline
    max_observed_live: int       # peak simultaneous live calls (MUST be <= capacity)
    p50_admit_ms: float
    p95_admit_ms: float
    max_admit_ms: float
    duration_s: float
    # red-team fold #1: per-key/per-tenant pool overflows — [(pool, peak, cap), ...].
    # NON-empty = a per-resource leak the global max_live gate would have hidden.
    binding_overflow: list = field(default_factory=list)

    @property
    def oversubscribed(self) -> bool:
        # honest: aggregate ceiling breached OR any per-key/per-tenant pool breached.
        return self.max_observed_live > self.capacity or bool(self.binding_overflow)

    @property
    def ok(self) -> bool:
        """The HARD gate: every call drained, none errored, never oversubscribed
        (aggregate AND every per-tenant / per-TTS-key pool stayed within ITS cap)."""
        return (not self.oversubscribed) and self.errored == 0 and self.completed == self.offered

    def summary(self) -> str:
        ov = f" OVERFLOW={self.binding_overflow}" if self.binding_overflow else ""
        return (
            f"offered={self.offered} cap={self.capacity} completed={self.completed} "
            f"admit1st={self.admitted_first_try} paced={self.paced_events} "
            f"errored={self.errored} max_live={self.max_observed_live} "
            f"p50={self.p50_admit_ms:.3f}ms p95={self.p95_admit_ms:.3f}ms "
            f"max={self.max_admit_ms:.3f}ms dur={self.duration_s:.2f}s{ov} "
            f"{'OK' if self.ok else 'FAIL'}"
        )


def _percentile(values: List[float], pct: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    k = max(0, min(len(s) - 1, int(round((pct / 100.0) * (len(s) - 1)))))
    return s[k]


async def run_load(
    offered: int,
    *,
    cfg: Optional[ConcurrencyConfig] = None,
    controller: Optional[AdmissionController] = None,
    talk_time_s: float = 0.01,
    retry_backoff_s: float = 0.001,
    deadline_s: float = 20.0,
    tenants: int = 1,
    provider_tts: str = "elevenlabs",
    provider_llm: str = "groq",
) -> LoadResult:
    """Fire `offered` simulated concurrent calls at the AdmissionController and assert
    the gate holds. Returns a LoadResult; raises nothing (the gate must absorb load).

    talk_time_s simulates how long an admitted call holds its slots; retry_backoff_s
    is how long a paced call waits before re-offering (the harness's stand-in for the
    dial loop's 4s tick, compressed). deadline_s caps total per-call retry time."""
    cfg = cfg or ConcurrencyConfig(
        worker_slot_cap=20, worker_count=1, tenant_call_cap=10_000,
        global_call_cap=0, llm_rpm=10_000_000, llm_burst=10_000_000,
        tts_slots_per_key=10_000,
    )
    # Default profile isolates the WORKER/global slot gate (huge tenant/llm/tts caps)
    # so the harness measures the physical-wall behaviour the W18 thesis is about.
    ctrl = controller or AdmissionController(cfg)
    capacity = cfg.effective_global_cap()
    counter = _LiveCounter(ctrl)  # sample per-pool peaks so the gate is honest (fold #1)

    admit_latencies: List[float] = []
    paced_total = 0
    admitted_first = 0
    completed = 0
    errored = 0
    stats_lock = asyncio.Lock()

    async def one_call(i: int) -> None:
        nonlocal paced_total, admitted_first, completed, errored
        tenant = f"t{i % max(1, tenants)}"
        call_id = f"call-{i}"
        start = time.perf_counter()
        first = True
        deadline = start + deadline_s
        try:
            while True:
                t0 = time.perf_counter()
                decision = await ctrl.reserve(tenant, call_id,
                                              provider_tts=provider_tts, provider_llm=provider_llm)
                dt_ms = (time.perf_counter() - t0) * 1000.0
                async with stats_lock:
                    admit_latencies.append(dt_ms)
                if decision.outcome == ADMITTED:
                    if first:
                        async with stats_lock:
                            admitted_first += 1
                    counter.enter()
                    try:
                        await asyncio.sleep(talk_time_s)  # simulated talk time
                    finally:
                        counter.leave()
                        await ctrl.release(decision.reservation)
                    async with stats_lock:
                        completed += 1
                    return
                # QUEUE / PACE -> back off and retry (the dial loop's behaviour)
                async with stats_lock:
                    paced_total += 1
                first = False
                if time.perf_counter() > deadline:
                    async with stats_lock:
                        errored += 1  # never drained within deadline = a real failure
                    return
                await asyncio.sleep(retry_backoff_s)
        except Exception as exc:  # the gate must never raise into a call
            log.warning("load call %s raised: %r", call_id, exc)
            async with stats_lock:
                errored += 1

    t_start = time.perf_counter()
    await asyncio.gather(*(one_call(i) for i in range(offered)))
    duration = time.perf_counter() - t_start

    return LoadResult(
        offered=offered, capacity=capacity, completed=completed,
        admitted_first_try=admitted_first, paced_events=paced_total, errored=errored,
        max_observed_live=counter.max_live,
        p50_admit_ms=_percentile(admit_latencies, 50),
        p95_admit_ms=_percentile(admit_latencies, 95),
        max_admit_ms=max(admit_latencies) if admit_latencies else 0.0,
        duration_s=duration,
        binding_overflow=counter.binding_overflow(),
    )


async def run_suite(levels=(50, 100, 200), **kw) -> List[LoadResult]:
    """Run the standard 50/100/200 ladder; return all results. Each level uses a
    FRESH controller so a run starts from a clean capacity slate."""
    out: List[LoadResult] = []
    for n in levels:
        res = await run_load(n, **kw)
        log.info("LOAD %d -> %s", n, res.summary())
        out.append(res)
    return out


def main(argv: Optional[List[str]] = None) -> int:
    import sys
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = argv if argv is not None else sys.argv[1:]
    levels = tuple(int(a) for a in args) if args else (50, 100, 200)
    results = asyncio.run(run_suite(levels))
    all_ok = all(r.ok for r in results)
    for r in results:
        print(r.summary())
    print("HARD GATE:", "PASS" if all_ok else "FAIL")
    return 0 if all_ok else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
