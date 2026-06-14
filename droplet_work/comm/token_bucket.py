"""comm.token_bucket — per-bot async token-bucket rate limiter (Wave 3, guard #6).

Spec: communication/COMMUNICATION-MASTER-PLAN.md §6 — "Per-bot-token async token-bucket (30 msg/s
global, 1 msg/s per chat) — the journey blast + post-call trickle + founder-alert burst SHARE one
budget; founder/hot-lead alerts get a priority lane."

THE MODEL (classic token bucket, asyncio-native, NEVER blocks the event loop):
  * One GLOBAL bucket per bot (keyed by provider_def_id), refilling at bucket_global_rate (30/s),
    capacity == rate (a 1s burst). EVERY send acquires 1 global token.
  * One PER-CHAT bucket per (bot, chat_id), refilling at bucket_per_chat_rate (1/s). A send to a
    specific chat ALSO acquires 1 per-chat token. A burst to one chat is paced; other chats are
    unaffected (one chat can never starve the global budget for everyone else).
  * PRIORITY LANE: a founder/hot-lead alert (priority=True) is granted a global token even when
    the bucket is momentarily empty (it borrows against the next refill, capped) so a journey
    blast can never delay the alert the founder must see now. Priority sends still pace per-chat
    (so we don't flood the founder's own chat) but never wait on the GLOBAL bucket.

EARNER / SAFETY:
  * acquire() awaits at most bucket_max_wait_s (default 3s, << the per-channel send_timeout) then
    returns False (the send is dropped/deferred by the caller) — it NEVER hangs.
  * disabled (token_bucket_enabled() False) -> acquire() returns True instantly (no pacing).
  * in-process (per worker); a restart resets buckets. Acceptable for a pacing limiter whose job
    is to smooth a burst within a process (the durable per-tenant ledger is cost_guards).
  * NEVER raises; ZERO I/O at import; no agent.py import.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Dict, Tuple

from . import config

_log = logging.getLogger("comm.token_bucket")


class _Bucket:
    """A single token bucket. `tokens` floats up to `capacity` at `rate` tokens/sec."""
    __slots__ = ("rate", "capacity", "tokens", "ts")

    def __init__(self, rate: float, capacity: float):
        self.rate = max(0.0001, float(rate))
        self.capacity = max(1.0, float(capacity))
        self.tokens = self.capacity
        self.ts = time.monotonic()

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self.ts
        if elapsed > 0:
            self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
            self.ts = now

    def try_take(self, n: float = 1.0) -> bool:
        """Take n tokens if available (refilling first). Returns True iff taken."""
        self._refill()
        if self.tokens >= n:
            self.tokens -= n
            return True
        return False

    def take_priority(self, n: float = 1.0) -> None:
        """Borrow n tokens unconditionally (priority lane) — may drive tokens slightly negative,
        bounded to -capacity so a flood of priority sends still settles. NEVER waits."""
        self._refill()
        self.tokens = max(-self.capacity, self.tokens - n)

    def seconds_until(self, n: float = 1.0) -> float:
        """Seconds until n tokens will be available (0 if already)."""
        self._refill()
        if self.tokens >= n:
            return 0.0
        return (n - self.tokens) / self.rate


# Module-global registries (guarded by a lock; asyncio is single-threaded but a sync guard
# keeps it safe under a thread-pool worker too).
_LOCK = asyncio.Lock()
_GLOBAL: Dict[str, _Bucket] = {}                 # provider_def_id -> global bucket
_PER_CHAT: Dict[Tuple[str, str], _Bucket] = {}   # (provider_def_id, chat_id) -> per-chat bucket
_PER_CHAT_CAP_KEYS = 50000


def _global_bucket(bot_key: str) -> _Bucket:
    b = _GLOBAL.get(bot_key)
    if b is None:
        rate = config.bucket_global_rate()
        b = _Bucket(rate=rate, capacity=rate)   # capacity == 1s of rate
        _GLOBAL[bot_key] = b
    return b


def _chat_bucket(bot_key: str, chat_id: str) -> _Bucket:
    key = (bot_key, chat_id)
    b = _PER_CHAT.get(key)
    if b is None:
        if len(_PER_CHAT) > _PER_CHAT_CAP_KEYS:
            for k in list(_PER_CHAT.keys())[: _PER_CHAT_CAP_KEYS // 2]:
                _PER_CHAT.pop(k, None)
        rate = config.bucket_per_chat_rate()
        # a small burst capacity (2 messages) so a legit back-to-back pair isn't paced to a crawl.
        b = _Bucket(rate=rate, capacity=max(2.0, rate))
        _PER_CHAT[key] = b
    return b


async def acquire(bot_key: str, chat_id: str = "", *, priority: bool = False) -> bool:
    """Acquire one send slot for (bot_key, chat_id). Returns True if granted (caller may send),
    False if the bounded wait elapsed without a token (caller drops/defers). NEVER raises.

      * disabled -> True instantly.
      * priority -> borrows a GLOBAL token immediately (never waits on global); still paces per-chat
        with a bounded wait so the founder's own chat isn't flooded.
      * normal -> waits up to bucket_max_wait_s for BOTH a global and a per-chat token.
    """
    try:
        if not config.token_bucket_enabled():
            return True
        bot_key = bot_key or "_default"
        max_wait = config.bucket_max_wait_s()
        deadline = time.monotonic() + max(0.0, max_wait)

        # --- GLOBAL lane ---
        if priority:
            async with _LOCK:
                _global_bucket(bot_key).take_priority(1.0)
        else:
            while True:
                async with _LOCK:
                    if _global_bucket(bot_key).try_take(1.0):
                        break
                    wait = _global_bucket(bot_key).seconds_until(1.0)
                if time.monotonic() >= deadline:
                    return False
                await asyncio.sleep(min(max(wait, 0.005), max(0.0, deadline - time.monotonic())))

        # --- PER-CHAT lane (priority paces here too, but still bounded) ---
        if chat_id:
            while True:
                async with _LOCK:
                    if _chat_bucket(bot_key, chat_id).try_take(1.0):
                        return True
                    wait = _chat_bucket(bot_key, chat_id).seconds_until(1.0)
                if time.monotonic() >= deadline:
                    # per-chat budget exhausted within the wait; priority still proceeds (the
                    # global token was already taken) — a founder alert must not be dropped.
                    return True if priority else False
                await asyncio.sleep(min(max(wait, 0.005), max(0.0, deadline - time.monotonic())))
        return True
    except Exception as exc:  # noqa: BLE001 — a pacing limiter must never block a send by crashing
        _log.warning("comm.token_bucket.acquire degraded: %r", type(exc).__name__)
        return True


def _reset_for_tests() -> None:
    """Test hook only — clear the in-process buckets so each suite starts clean."""
    _GLOBAL.clear()
    _PER_CHAT.clear()


def snapshot(bot_key: str = "") -> dict:
    """Diagnostic — current token levels (never a secret). NEVER raises."""
    try:
        g = _GLOBAL.get(bot_key or "_default")
        return {
            "global_tokens": (round(g.tokens, 2) if g else None),
            "global_keys": len(_GLOBAL),
            "per_chat_keys": len(_PER_CHAT),
        }
    except Exception:  # noqa: BLE001
        return {}
