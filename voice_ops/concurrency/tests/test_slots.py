"""SlotPool — atomic capacity-bounded slot counter with TTL self-heal."""
from __future__ import annotations

import threading

from voice_ops.concurrency.slots import SlotPool


class Clock:
    def __init__(self, t=0.0):
        self.t = t

    def __call__(self):
        return self.t

    def advance(self, dt):
        self.t += dt


def test_acquire_release_bounds():
    p = SlotPool("worker", capacity=2, clock=Clock())
    assert p.acquire("a") and p.acquire("b")
    assert p.free == 0
    assert not p.acquire("c")          # full -> refuse (pace)
    assert p.release("a")
    assert p.acquire("c")              # slot freed
    assert p.in_flight == 2


def test_release_is_idempotent_never_negative():
    p = SlotPool("worker", capacity=1, clock=Clock())
    assert p.acquire("a")
    assert p.release("a")
    assert not p.release("a")          # double release -> no-op
    assert not p.release("ghost")      # unknown id -> no-op
    assert p.in_flight == 0
    assert p.free == 1                 # never driven negative


def test_acquire_is_idempotent_for_same_lease():
    p = SlotPool("worker", capacity=1, clock=Clock())
    assert p.acquire("a")
    assert p.acquire("a")              # retry same call (index.lock-style) -> no double count
    assert p.in_flight == 1


def test_ttl_self_heals_crashed_worker():
    clk = Clock()
    p = SlotPool("worker", capacity=1, ttl_s=300.0, clock=clk)
    assert p.acquire("crashed")        # a worker reserves then dies
    assert not p.acquire("next")       # full
    clk.advance(301.0)                 # TTL elapses
    assert p.free == 1                 # lease reclaimed implicitly
    assert p.acquire("next")           # a new call can land


def test_renew_keeps_a_long_call_alive():
    clk = Clock()
    p = SlotPool("worker", capacity=1, ttl_s=100.0, clock=clk)
    assert p.acquire("long")
    clk.advance(60.0)
    assert p.renew("long")             # heartbeat
    clk.advance(60.0)                  # 120s total, but renewed at 60 -> still alive
    assert p.held("long")
    assert not p.acquire("other")


def test_sweep_reports_reclaimed():
    clk = Clock()
    p = SlotPool("tts", capacity=3, ttl_s=10.0, clock=clk)
    p.acquire("x"); p.acquire("y"); p.acquire("z")
    clk.advance(11.0)
    assert p.sweep() == 3


def test_zero_capacity_always_refuses():
    p = SlotPool("worker", capacity=0, clock=Clock())
    assert not p.acquire("a")


def test_thread_safe_no_oversubscription():
    """Hammer acquire from many threads on a small pool: never exceeds capacity."""
    p = SlotPool("worker", capacity=10, ttl_s=0.0)  # ttl 0 -> no expiry interference
    granted = []
    lock = threading.Lock()

    def worker(i):
        if p.acquire(f"call-{i}"):
            with lock:
                granted.append(i)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(200)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(granted) == 10           # exactly capacity, never oversubscribed
    assert p.in_flight == 10
