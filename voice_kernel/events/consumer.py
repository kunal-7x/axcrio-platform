"""voice_kernel.events.consumer — the sink-side consumer helper (W8).

A sink (dashboard / CRM / analytics / reports) is a SEPARATE process (systemd
unit, NEVER inside the voice process — RESEARCH-DECISIONS §9). It:
  - subscribes to ONE tenant stream as ONE consumer group;
  - runs a user `handler(event)` (async) per delivered event;
  - dedupes on `iid` (consumer-side, always-on — §4);
  - auto-XACKs on success; on handler exception, leaves the entry in the PEL;
  - periodically XAUTOCLAIMs stale PEL entries (crashed peer) and routes a
    poison entry (delivered >= max_deliveries) to the per-tenant DLQ stream.

This helper is generic over the bus (works with RedisEventBus or
InMemoryEventBus) for the success/dedup path; the reclaim/DLQ janitor is
Redis-specific and is a no-op when the bus has no redis client (the in-memory
fake handles redelivery via its own PEL-less cursor model, so tests exercise the
success + dedup + isolation paths here and the reclaim/DLQ paths against a mock
in test_consumer).
"""
from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable, Optional

from ..contracts import Event
from .config import EventBusConfig
from .serde import decode, decoded_iid

log = logging.getLogger("voice_kernel.events.consumer")

Handler = Callable[[Event], Awaitable[None]]


class SinkConsumer:
    """Drive a handler over one tenant stream + one consumer group, with
    consumer-side dedup. `bus` must expose `subscribe(stream, group)`."""

    def __init__(self, bus, cfg: EventBusConfig, tenant_id: str, group: str, handler: Handler, consumer: str = "c1"):
        self.bus = bus
        self.cfg = cfg
        self.tenant_id = tenant_id
        self.group = group
        self.handler = handler
        self.consumer = consumer
        self.stream = cfg.stream_for(tenant_id)
        self._seen: set[str] = set()  # local dedup mirror (Redis dedup-key is the durable one)
        self._stop = asyncio.Event()

    async def run(self) -> None:
        """Main loop: consume -> dedup -> handle -> ack-or-leave-in-PEL.

        Drives the bus's `subscribe(...)` async-generator MANUALLY (not `async
        for`) so that on a handler exception we can `.athrow(_AckSkip)` the
        failure BACK INTO the generator at its yield point — which makes the bus
        SKIP the XACK and leave the entry in the PEL for XAUTOCLAIM redelivery
        (BLOCKER-1 fix: at-least-once, never at-most-once-then-drop). On success
        the yield resumes normally and the bus auto-XACKs. Idempotent on iid so a
        redelivery after a crash/restart is harmless.

        A bus whose `subscribe` is a plain async-iterator without `athrow`
        (e.g. some fakes) is handled gracefully — we fall back to advancing past
        the failed entry (the in-memory fake has no PEL/redelivery anyway)."""
        agen = self.bus.subscribe(self.stream, self.group)
        try:
            event = await _anext(agen)
            while True:
                if self._stop.is_set():
                    break
                ok = await self._dispatch(event)
                try:
                    if ok:
                        event = await agen.asend(None)        # success -> bus XACKs, get next
                    else:
                        event = await _athrow(agen, _ack_skip())  # failure -> bus leaves in PEL
                except StopAsyncIteration:
                    break
        finally:
            aclose = getattr(agen, "aclose", None)
            if aclose is not None:
                try:
                    await aclose()
                except Exception:
                    pass

    async def _dispatch(self, event: Event) -> bool:
        """Dedup + handle one event. Returns True if it should be ACKed (handled
        or deduped), False if the handler raised (-> leave in PEL, retry)."""
        iid = _iid_of(event)
        if await self._is_dup(iid):
            log.debug("SinkConsumer[%s] dedup %s (iid=%s)", self.group, event.name, iid)
            return True  # already handled once -> safe to ack the redelivery
        try:
            await self.handler(event)
        except Exception as exc:
            # Do NOT mark seen -> the redelivery re-runs the handler.
            log.warning("SinkConsumer[%s] handler failed for %s: %r", self.group, event.name, exc)
            return False
        await self._mark_seen(iid)
        return True

    def stop(self) -> None:
        self._stop.set()

    # ------------------------------------------------------------- dedup #
    async def _is_dup(self, iid: str) -> bool:
        if not iid:
            return False
        if iid in self._seen:
            return True
        client = _redis_client(self.bus)
        if client is None:
            return False
        try:
            key = self.cfg.dedup_key(self.tenant_id, self.group, iid)
            exists = await client.exists(key)
            return bool(exists)
        except Exception:
            return False

    async def _mark_seen(self, iid: str) -> None:
        if not iid:
            return
        self._seen.add(iid)
        client = _redis_client(self.bus)
        if client is None:
            return
        try:
            key = self.cfg.dedup_key(self.tenant_id, self.group, iid)
            await client.set(key, "1", ex=self.cfg.dedup_ttl_s)
        except Exception as exc:
            log.debug("dedup set failed (non-fatal): %r", exc)


async def reclaim_and_dlq(bus, cfg: EventBusConfig, tenant_id: str, group: str, consumer: str = "janitor") -> int:
    """One janitor pass (call on a ~30s timer): XAUTOCLAIM stale PEL entries for
    the group; any entry delivered >= cfg.max_deliveries is moved to the DLQ
    stream and XACK'd on the source. Returns the number of entries reclaimed.

    No-op (returns 0) when the bus has no Redis client (the in-memory fake has no
    PEL). Redis 6.2+ XAUTOCLAIM."""
    client = _redis_client(bus, consumer_side=True)
    if client is None:
        return 0
    stream = cfg.stream_for(tenant_id)
    dlq = cfg.dlq_for(tenant_id)
    reclaimed = 0
    try:
        # XAUTOCLAIM <key> <group> <consumer> <min-idle> <start> COUNT n
        cursor, entries, _deleted = await client.xautoclaim(
            stream, group, consumer, min_idle_time=cfg.min_idle_ms, start_id="0-0", count=cfg.claim_count,
        )
    except Exception as exc:
        log.debug("xautoclaim no-op/failed: %r", exc)
        return 0
    for entry_id, fields in entries or []:
        reclaimed += 1
        try:
            pend = await client.xpending_range(stream, group, min=entry_id, max=entry_id, count=1)
            times = pend[0]["times_delivered"] if pend else 1
        except Exception:
            times = 1
        if times >= cfg.max_deliveries:
            # Poison -> DLQ, then ack the original so it stops being redelivered.
            try:
                await client.xadd(dlq, _normalize_fields(fields), maxlen=cfg.maxlen, approximate=True)
                await client.xack(stream, group, entry_id)
                log.warning("SinkConsumer[%s] poison -> DLQ %s (delivered %sx)", group, decoded_iid(fields), times)
            except Exception as exc:
                log.warning("DLQ route failed: %r", exc)
    return reclaimed


def _iid_of(event: Event) -> str:
    from .serde import idempotency_id
    return idempotency_id(event)


def _ack_skip() -> Exception:
    """The sentinel the bus's `_read` catches to skip the XACK (leave-in-PEL).
    Imported lazily so the consumer helper stays usable with the in-memory fake
    even if the Redis bus module weren't importable."""
    from .bus import _AckSkip
    return _AckSkip("handler failed — leave in PEL")


async def _anext(agen):
    """`anext()` for Py<3.10 compatibility (the repo's floor)."""
    return await agen.__anext__()


async def _athrow(agen, exc):
    """Throw `exc` back into the async-generator at its current yield. If the
    object isn't a real async-generator (a fake iterator without `athrow`), fall
    back to advancing past the entry — the in-memory fake has no PEL/redelivery,
    so there is nothing to leave-in-PEL anyway."""
    athrow = getattr(agen, "athrow", None)
    if athrow is None:
        return await agen.__anext__()
    return await athrow(exc)


def _normalize_fields(fields: dict) -> dict:
    out = {}
    for k, v in (fields or {}).items():
        kk = k.decode() if isinstance(k, (bytes, bytearray)) else str(k)
        vv = v.decode() if isinstance(v, (bytes, bytearray)) else v
        out[kk] = vv
    return out


def _redis_client(bus, consumer_side: bool = False):
    """Best-effort: pull the live redis client off a RedisEventBus, else None.
    Avoids creating a connection here (the bus owns lifecycle)."""
    if consumer_side:
        return getattr(bus, "_consumer_client", None)
    return getattr(bus, "_client", None)
