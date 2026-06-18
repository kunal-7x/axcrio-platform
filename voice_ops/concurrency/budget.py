"""voice_ops.concurrency.budget — TokenBucket: the denial-of-wallet rate guard.

A classic token bucket: `capacity` tokens, refilled at `refill_per_sec`. `take(n)`
consumes n tokens iff available (returns True) else refuses (returns False) — it
NEVER blocks. This bounds how fast a tenant (or a single provider key) can consume
paid LLM/TTS calls, so a runaway campaign or a hostile tenant cannot drain the
founder's provider quota / wallet (the "denial-of-wallet" attack the W18 gap names).

The seam wires ONE bucket per (tenant, resource) and per (provider, key) so the
guard is enforced at BOTH the tenant budget and the per-key rate limit — a tenant
can't exceed its plan, and no single API key can be hammered past its provider RPM.

Thread-safe (an RLock guards the refill+take), pure stdlib, injectable monotonic
clock so tests are deterministic. Importing this pulls ZERO heavy/droplet code.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Optional


@dataclass
class TokenBucket:
    """Lazy-refill token bucket. `capacity` = burst size; `refill_per_sec` =
    sustained rate. Tokens accrue continuously (not in discrete ticks) so a bucket
    that has been idle for `capacity / refill_per_sec` seconds is full again."""

    capacity: float
    refill_per_sec: float
    _tokens: float = field(default=None, repr=False)  # type: ignore[assignment]
    _last: float = field(default=0.0, repr=False)
    _now: Callable[[], float] = field(default=None, repr=False)  # type: ignore[assignment]
    _lock: threading.RLock = field(default_factory=threading.RLock, repr=False)

    def __post_init__(self) -> None:
        if self._now is None:
            self._now = time.monotonic
        self.capacity = max(0.0, float(self.capacity))
        self.refill_per_sec = max(0.0, float(self.refill_per_sec))
        if self._tokens is None:
            self._tokens = self.capacity  # start full (no cold-start penalty)
        self._last = self._now()

    @classmethod
    def per_minute(cls, rpm: int, burst: int, *, now: Optional[Callable[[], float]] = None) -> "TokenBucket":
        """Build from a requests-per-MINUTE rate + a burst capacity (the natural
        units for Groq RPM / a plan budget). burst<=0 falls back to rpm so a bucket
        always has at least one slot."""
        cap = float(burst if burst and burst > 0 else max(1, rpm))
        rate = max(0.0, float(rpm)) / 60.0
        return cls(capacity=cap, refill_per_sec=rate, _now=now)

    # ----------------------------------------------------------------- core #
    def _refill(self) -> None:
        t = self._now()
        elapsed = max(0.0, t - self._last)
        self._last = t
        if self.refill_per_sec > 0:
            self._tokens = min(self.capacity, self._tokens + elapsed * self.refill_per_sec)

    def take(self, n: float = 1.0) -> bool:
        """Consume `n` tokens iff available; never blocks. A capacity-0 bucket always
        refuses; a refill-0 bucket drains and never recovers (a hard cap)."""
        if n <= 0:
            return True
        with self._lock:
            self._refill()
            if self._tokens >= n:
                self._tokens -= n
                return True
            return False

    def give_back(self, n: float = 1.0) -> None:
        """Return `n` tokens (used when a reservation is rolled back because a LATER
        gate in the same admission failed — so a refused admit doesn't leak budget).
        Clamped to capacity."""
        if n <= 0:
            return
        with self._lock:
            self._tokens = min(self.capacity, self._tokens + n)

    @property
    def available(self) -> float:
        """Current token count (refills first). Read-only peek for snapshots/tests."""
        with self._lock:
            self._refill()
            return self._tokens

    def snapshot(self) -> dict:
        return {
            "available": round(self.available, 3),
            "capacity": self.capacity,
            "refill_per_sec": round(self.refill_per_sec, 4),
        }
