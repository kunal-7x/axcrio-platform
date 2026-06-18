"""voice_kernel.events.fake — InMemoryEventBus: a REAL, dependency-free EventBus.

Structurally conforms to the frozen `voice_kernel.contracts.EventBus` Protocol
(emit + subscribe). Used by tests (no Redis needed) and as a documented local
fallback. It faithfully models the load-bearing semantics the RedisEventBus also
guarantees, so a test that passes here is meaningful:

  - per-tenant streams (a subscriber to tenant A NEVER sees tenant B's events);
  - per-(stream, group) consumer cursor (each sink reads independently);
  - at-least-once + idempotency: a re-emit of the SAME logical event (same iid)
    is deduped at the stream level;
  - fire-and-forget emit: emit() never blocks meaningfully and never raises.

It is intentionally NOT durable across process restarts — that is Redis's job.
"""
from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import AsyncIterator

from ..contracts import Event
from .config import EventBusConfig
from .serde import idempotency_id

log = logging.getLogger("voice_kernel.events.fake")


class InMemoryEventBus:
    """Async, fire-and-forget, tenant-scoped, idempotent in-memory stream bus."""

    def __init__(self, cfg: EventBusConfig | None = None):
        self.cfg = cfg or EventBusConfig()
        # stream_key -> list[(iid, Event)] (append-only log)
        self._streams: dict[str, list[tuple[str, Event]]] = defaultdict(list)
        # stream_key -> set[iid] seen (stream-level producer dedup)
        self._seen: dict[str, set[str]] = defaultdict(set)
        # (stream_key, group) -> next index to deliver (per-group cursor)
        self._cursor: dict[tuple[str, str], int] = defaultdict(int)
        # wakeups for blocked subscribers, per stream
        self._events: dict[str, asyncio.Event] = defaultdict(asyncio.Event)
        self.closed = False

    # ----------------------------------------------------------- producer #
    async def emit(self, event: Event) -> None:
        """Fire-and-forget append. Never raises; an empty tenant_id is dropped
        (fail-closed: no shared/wildcard stream), exactly like the Redis bus."""
        try:
            tenant = (event.tenant_id or "").strip()
            if not tenant:
                log.warning("InMemoryEventBus.emit dropped: empty tenant_id (%s)", event.name)
                return
            stream = self.cfg.stream_for(tenant)
            iid = idempotency_id(event)
            if iid in self._seen[stream]:
                log.debug("InMemoryEventBus.emit dedup %s (iid=%s)", event.name, iid)
                return
            self._seen[stream].add(iid)
            self._streams[stream].append((iid, event))
            self._wake(stream)
        except Exception as exc:  # emit must NEVER break the caller
            log.warning("InMemoryEventBus.emit failed (non-fatal): %r", exc)
            return None

    def _wake(self, stream: str) -> None:
        ev = self._events[stream]
        ev.set()

    # ----------------------------------------------------------- consumer #
    async def subscribe(self, stream: str, group: str) -> AsyncIterator[Event]:
        """Yield events on `stream` for consumer `group` from its own cursor.
        Mirrors XREADGROUP: each group advances independently; new emits wake a
        blocked subscriber. Auto-acks by advancing the cursor after a SUCCESSFUL
        yield (matches the Redis consumer's auto-XACK-on-success contract). If the
        consumer `.athrow()`s the bus's `_AckSkip` sentinel back in (handler
        failed), we do NOT advance the cursor — so the SAME event is redelivered
        on the next iteration, faithfully modelling at-least-once leave-in-PEL."""
        from .bus import _AckSkip
        key = (stream, group)
        while not self.closed:
            log = self._streams.get(stream, [])
            idx = self._cursor[key]
            if idx < len(log):
                _iid, event = log[idx]
                try:
                    yield event
                except _AckSkip:
                    # handler failed -> leave "in PEL": do NOT advance the cursor.
                    continue
                # auto-ack: only advance after the consumer's body completed OK.
                self._cursor[key] = idx + 1
                continue
            # caught up: wait for the next emit (or close).
            self._events[stream].clear()
            try:
                await asyncio.wait_for(self._events[stream].wait(), timeout=self.cfg.block_ms / 1000.0)
            except asyncio.TimeoutError:
                # loop again; in tests this lets `close()` end the iterator.
                continue

    def close(self) -> None:
        self.closed = True
        for ev in self._events.values():
            ev.set()

    # ----------------------------------------------------- test helpers #
    def drain(self, tenant_id: str, group: str = "_drain") -> list[Event]:
        """Synchronously return all events for a tenant from `group`'s cursor and
        advance it. Convenience for assertions in tests (no await needed)."""
        stream = self.cfg.stream_for(tenant_id)
        key = (stream, group)
        log = self._streams.get(stream, [])
        idx = self._cursor[key]
        out = [e for _iid, e in log[idx:]]
        self._cursor[key] = len(log)
        return out

    def all_events(self, tenant_id: str) -> list[Event]:
        """Every event ever emitted for a tenant (ignores cursors). Test-only."""
        stream = self.cfg.stream_for(tenant_id)
        return [e for _iid, e in self._streams.get(stream, [])]

    def stream_keys(self) -> list[str]:
        return list(self._streams.keys())
