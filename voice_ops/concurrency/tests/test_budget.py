"""TokenBucket — the denial-of-wallet rate guard. Deterministic clock."""
from __future__ import annotations

from voice_ops.concurrency.budget import TokenBucket


class Clock:
    def __init__(self, t=0.0):
        self.t = t

    def __call__(self):
        return self.t

    def advance(self, dt):
        self.t += dt


def test_starts_full_and_drains():
    b = TokenBucket(capacity=3, refill_per_sec=0.0, _now=Clock())
    assert b.available == 3
    assert b.take(1) and b.take(1) and b.take(1)
    assert not b.take(1)  # drained, no refill -> hard cap


def test_refills_at_rate():
    clk = Clock()
    b = TokenBucket(capacity=2, refill_per_sec=1.0, _now=clk)  # 1 token/sec
    assert b.take(2)
    assert not b.take(1)
    clk.advance(1.0)
    assert b.take(1)        # one token refilled
    assert not b.take(1)
    clk.advance(10.0)
    assert b.available == 2  # capped at capacity, never overflows


def test_per_minute_factory_groq_rpm():
    clk = Clock()
    b = TokenBucket.per_minute(rpm=30, burst=10, now=clk)  # 30/min = 0.5/s, burst 10
    assert b.capacity == 10
    # burn the burst
    for _ in range(10):
        assert b.take(1)
    assert not b.take(1)
    clk.advance(2.0)         # +1 token at 0.5/s
    assert b.take(1)
    assert not b.take(1)


def test_take_zero_is_free():
    b = TokenBucket(capacity=0, refill_per_sec=0.0, _now=Clock())
    assert b.take(0)         # zero cost always admitted
    assert not b.take(1)     # capacity 0 always refuses a real take


def test_give_back_rolls_a_reservation():
    b = TokenBucket(capacity=5, refill_per_sec=0.0, _now=Clock())
    assert b.take(3)
    assert b.available == 2
    b.give_back(3)
    assert b.available == 5  # rolled back, clamped to capacity
    b.give_back(10)
    assert b.available == 5  # never exceeds capacity


def test_denial_of_wallet_cap_holds_under_burst():
    """A runaway tenant cannot drain past the bucket: only `capacity` calls go
    through before refill, no matter how many times take() is hammered."""
    b = TokenBucket(capacity=4, refill_per_sec=0.0, _now=Clock())
    admitted = sum(1 for _ in range(1000) if b.take(1))
    assert admitted == 4
