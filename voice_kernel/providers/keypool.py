"""voice_kernel.providers.keypool — health-scored API-key pool.

A small, deterministic, dependency-free key rotator. Each provider (sarvam / groq
/ elevenlabs) has N keys; on a 429 (rate-limit) or transport error we DEMOTE the
key's health and rotate to the next HEALTHY key. Keys recover after a cooldown.
This is the fail-LOUD replacement for the live round-robin that rotated blindly.

Pure stdlib; the time source is injectable so tests are deterministic.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional


@dataclass
class _KeyState:
    key: str
    healthy: bool = True
    fails: int = 0
    cooldown_until: float = 0.0


@dataclass
class KeyPool:
    """Round-robin over HEALTHY keys with cooldown-based recovery."""

    provider: str
    keys: tuple[str, ...]
    cooldown_s: float = 30.0
    fail_threshold: int = 1  # demote on the first 429 (then rotate)
    _now: Callable[[], float] = field(default=None, repr=False)  # type: ignore[assignment]
    _states: list[_KeyState] = field(default_factory=list, repr=False)
    _idx: int = 0

    def __post_init__(self) -> None:
        if self._now is None:
            import time

            self._now = time.monotonic
        self._states = [_KeyState(k) for k in self.keys if k]

    # -------------------------------------------------------------- queries -- #
    def _refresh(self) -> None:
        t = self._now()
        for s in self._states:
            if not s.healthy and s.cooldown_until and t >= s.cooldown_until:
                s.healthy = True
                s.fails = 0
                s.cooldown_until = 0.0

    @property
    def healthy_count(self) -> int:
        self._refresh()
        return sum(1 for s in self._states if s.healthy)

    def pick(self) -> Optional[str]:
        """Return the next HEALTHY key, or None if the pool is exhausted (all
        keys cooling down). None is an explicit, loud signal — the router turns it
        into a logged fallback, never a silent default."""
        self._refresh()
        n = len(self._states)
        if n == 0:
            return None
        for off in range(n):
            i = (self._idx + off) % n
            if self._states[i].healthy:
                self._idx = (i + 1) % n
                return self._states[i].key
        return None

    # ------------------------------------------------------------- mutation -- #
    def report_failure(self, key: str, code: int) -> None:
        """Demote a key after a 429 / transport error. 400-class (bad request)
        does NOT demote the key — it's a request bug, not a key problem."""
        if 400 <= code < 429 and code != 408:
            return
        for s in self._states:
            if s.key == key:
                s.fails += 1
                if s.fails >= self.fail_threshold:
                    s.healthy = False
                    s.cooldown_until = self._now() + self.cooldown_s
                return

    def report_success(self, key: str) -> None:
        for s in self._states:
            if s.key == key:
                s.healthy = True
                s.fails = 0
                s.cooldown_until = 0.0
                return
