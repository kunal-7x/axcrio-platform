"""AutoscaleSignal — the worker-pool scale recommendation + W8 emit."""
from __future__ import annotations

import asyncio

from voice_ops.concurrency.autoscale import HOLD, SCALE_DOWN, SCALE_UP, AutoscaleSignal
from voice_ops.concurrency.config import ConcurrencyConfig


def _cfg(**kw):
    base = dict(worker_slot_cap=20, worker_count=1, scale_up_cpu=0.55,
                scale_down_cpu=0.30, warm_pool_min=2)
    base.update(kw)
    return ConcurrencyConfig(**base)


def test_scale_up_when_cpu_over_target_before_load_threshold():
    sig = AutoscaleSignal(_cfg())
    # cpu 0.60 >= 0.55 (and below LiveKit load_threshold 0.70) -> add capacity early
    rec = sig.recommend(active_calls=12, current_workers=1, cpu=0.60)
    assert rec.action == SCALE_UP
    assert rec.desired_workers > rec.current_workers


def test_scale_up_when_utilisation_high_even_if_cpu_low():
    sig = AutoscaleSignal(_cfg(worker_slot_cap=10))
    rec = sig.recommend(active_calls=9, current_workers=1, cpu=0.10)  # util 0.90
    assert rec.action == SCALE_UP


def test_hold_in_target_band():
    sig = AutoscaleSignal(_cfg())
    rec = sig.recommend(active_calls=5, current_workers=1, cpu=0.40)  # util 0.25, cpu mid
    assert rec.action == HOLD


def test_scale_down_only_when_both_low_and_above_warm_pool():
    sig = AutoscaleSignal(_cfg(warm_pool_min=2))
    rec = sig.recommend(active_calls=2, current_workers=4, cpu=0.10)  # util low, cpu low
    assert rec.action == SCALE_DOWN
    assert rec.desired_workers == 3


def test_never_scales_below_warm_pool():
    sig = AutoscaleSignal(_cfg(warm_pool_min=2))
    rec = sig.recommend(active_calls=0, current_workers=2, cpu=0.0)
    assert rec.desired_workers >= 2
    assert rec.action == HOLD  # already at warm floor


def test_clamped_to_hard_max():
    sig = AutoscaleSignal(_cfg(worker_slot_cap=1), hard_max_workers=3)
    rec = sig.recommend(active_calls=100, current_workers=3, cpu=0.95)
    assert rec.desired_workers <= 3


def test_emit_is_fire_and_forget_safe():
    class _DeadBus:
        async def emit(self, ev):
            raise RuntimeError("down")

    sig = AutoscaleSignal(_cfg(), event_bus=_DeadBus())
    rec = sig.recommend(active_calls=12, current_workers=1, cpu=0.60)
    # must not raise even with a dead bus
    asyncio.run(sig.emit(rec))


def test_emit_payload_carries_recommendation():
    class _Bus:
        def __init__(self):
            self.events = []

        async def emit(self, ev):
            self.events.append(ev)

    bus = _Bus()
    sig = AutoscaleSignal(_cfg(), event_bus=bus)
    rec = sig.recommend(active_calls=12, current_workers=1, cpu=0.60)
    asyncio.run(sig.emit(rec))
    assert len(bus.events) == 1
    ev = bus.events[0]
    assert ev.name == "autoscale_signal"
    assert ev.payload["action"] == SCALE_UP
    assert ev.payload["desired_workers"] == rec.desired_workers
