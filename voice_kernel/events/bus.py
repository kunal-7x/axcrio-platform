"""voice_kernel.events.bus — RedisEventBus: the Redis-Streams EventBus impl (W8).

Structurally conforms to the FROZEN `voice_kernel.contracts.EventBus` Protocol
(emit + subscribe). It is the production backbone behind the founder's
"nothing updates in real time" fix: ONE durable append per meaningful action,
fanned out to N independent sinks (dashboard / CRM / analytics / reports) via
consumer groups, each with its own replayable cursor.

Earner-safety core (RESEARCH-DECISIONS §7): emit() is fire-and-forget with a hard
`asyncio.wait_for(..., emit_timeout_s)` and a catch-all — a dead/slow Redis makes
emit DROP the event (exactly like NullEventBus), it can NEVER block or crash the
dial loop.

Topology (§2): one stream PER TENANT (`vk:events:{tenant_id}`) — hard isolation,
a consumer for tenant A literally cannot read B's stream (never a wildcard,
mirrors the proven RLS rule). Consumer-group-per-sink on that stream.

Durability (§4): at-least-once via XREADGROUP `>` -> PEL -> XACK only after the
sink succeeds. Idempotency: producer-side native dedup on Redis 8.6+ (version
probed) PLUS always-on consumer-side dedup on `iid`.

This module does NOT require redis at import time (so the package imports on a
host without redis); the client is created lazily on first emit/subscribe.
"""
from __future__ import annotations

import asyncio
import logging
from typing import AsyncIterator, Optional

from ..contracts import Event
from .config import EventBusConfig
from .serde import encode, idempotency_id

log = logging.getLogger("voice_kernel.events.bus")


class _AckSkip(Exception):
    """Sentinel the consumer `.athrow()`s back into the `subscribe` generator to
    say "this entry's handler FAILED — do not XACK, leave it in the PEL". Caught
    inside `_read` at the yield point; never escapes the bus. (BLOCKER-1 fix.)"""


class RedisEventBus:
    """Redis-Streams EventBus. Construct with a config and optionally an injected
    async redis client (tests inject a fake/mock); otherwise a real
    redis.asyncio client is created lazily from `cfg.url`."""

    def __init__(self, cfg: Optional[EventBusConfig] = None, client=None, consumer_client=None):
        self.cfg = cfg or EventBusConfig.from_env()
        self._client = client                 # producer connection
        self._consumer_client = consumer_client  # separate conn for BLOCK reads (§7)
        self._idmp_supported: Optional[bool] = None  # lazily probed (Redis 8.6+)

    # ------------------------------------------------------------- client #
    async def _get_client(self):
        if self._client is None:
            from redis import asyncio as aioredis  # lazy import (no hard dep at import)
            self._client = aioredis.from_url(self.cfg.url, decode_responses=True)
        return self._client

    async def _get_consumer_client(self):
        if self._consumer_client is None:
            # A SEPARATE connection for blocking reads so a long BLOCK never
            # starves the fire-and-forget producer path (§7).
            from redis import asyncio as aioredis
            self._consumer_client = aioredis.from_url(self.cfg.url, decode_responses=True)
        return self._consumer_client

    async def _supports_idmp(self, client) -> bool:
        """Probe once: native producer dedup (XADD ... IDMP) needs Redis 8.6+."""
        if self._idmp_supported is not None:
            return self._idmp_supported
        try:
            info = await client.info("server")
            ver = str(info.get("redis_version", "0")).split(".")
            major, minor = int(ver[0]), int(ver[1]) if len(ver) > 1 else 0
            self._idmp_supported = (major, minor) >= (8, 6)
        except Exception:
            self._idmp_supported = False
        return self._idmp_supported

    # -------------------------------------------------------------- emit #
    async def emit(self, event: Event) -> None:
        """Fire-and-forget durable append. NEVER blocks beyond emit_timeout_s and
        NEVER raises — a dead Redis drops the event like NullEventBus (§7).
        Fail-closed on empty tenant_id (no shared/wildcard stream)."""
        try:
            await asyncio.wait_for(self._emit_inner(event), timeout=self.cfg.emit_timeout_s)
        except asyncio.TimeoutError:
            log.warning("EventBus.emit timed out (%.0fms) — dropping %s", self.cfg.emit_timeout_s * 1000, event.name)
        except Exception as exc:
            log.warning("EventBus.emit failed (non-fatal) %s: %r", event.name, exc)
        return None

    async def _emit_inner(self, event: Event) -> None:
        tenant = (event.tenant_id or "").strip()
        if not tenant:
            log.warning("EventBus.emit dropped: empty tenant_id (%s)", event.name)
            return
        stream = self.cfg.stream_for(tenant)
        client = await self._get_client()
        fields = encode(event)
        if await self._supports_idmp(client):
            # Native producer dedup: pid=tenant, iid=the logical-event id.
            try:
                await client.execute_command(
                    "XADD", stream, "IDMP", "pid", tenant, "iid", fields["iid"],
                    "MAXLEN", "~", str(self.cfg.maxlen), "*",
                    *(_kv for pair in fields.items() for _kv in pair),
                )
                return
            except Exception as exc:
                # Any IDMP incompatibility -> fall through to plain XADD (never lose the event for a syntax quirk).
                log.debug("XADD IDMP failed, falling back to plain XADD: %r", exc)
        await client.xadd(stream, fields, maxlen=self.cfg.maxlen, approximate=True)

    # --------------------------------------------------------- subscribe #
    async def subscribe(self, stream: str, group: str, consumer: str = "c1") -> AsyncIterator[Event]:
        """Consume `stream` as consumer `group`. Two-phase start (FULLY drain
        this consumer's PEL with id '0' — looping over ALL pending batches, not
        just the first `claim_count` — then live '>'), auto-XACK on a SUCCESSFUL
        yield only. The consumer signals a handler FAILURE by `.athrow(_AckSkip)`
        back into this generator at the yield point: that skips the XACK so the
        entry stays in the PEL for XAUTOCLAIM redelivery / DLQ (at-least-once).
        Idempotent group create (swallow BUSYGROUP)."""
        client = await self._get_consumer_client()
        await self._ensure_group(client, stream, group)
        # Phase 1: re-deliver anything already pending for THIS consumer.
        async for ev in self._read(client, stream, group, consumer, start_id="0"):
            yield ev
        # Phase 2: live tail.
        async for ev in self._read(client, stream, group, consumer, start_id=">"):
            yield ev

    async def _ensure_group(self, client, stream: str, group: str) -> None:
        try:
            await client.xgroup_create(stream, group, id="$", mkstream=True)
        except Exception as exc:
            if "BUSYGROUP" not in str(exc):
                raise  # a real error (auth/conn) must surface to the consumer process

    async def _read(self, client, stream: str, group: str, consumer: str, start_id: str) -> AsyncIterator[Event]:
        from .serde import decode  # local import keeps module import light
        while True:
            resp = await client.xreadgroup(
                group, consumer, {stream: start_id},
                count=self.cfg.claim_count, block=self.cfg.block_ms,
            )
            if not resp:
                if start_id == "0":
                    return  # PEL fully drained for THIS consumer -> move to live phase
                continue     # live phase: keep blocking
            saw_entry = False
            for _stream_key, entries in resp:
                if not entries and start_id == "0":
                    return  # empty '0' batch -> PEL drained -> live phase
                for entry_id, fields in entries:
                    saw_entry = True
                    # At-least-once: XACK ONLY when the consumer's body resumed
                    # WITHOUT raising. SinkConsumer.athrow()s a handler failure back
                    # into this yield, so on failure we skip the xack and the entry
                    # stays in the PEL for XAUTOCLAIM redelivery (BLOCKER-1 fix —
                    # never degrade to at-most-once-then-drop). RESEARCH §8.
                    try:
                        yield decode(fields)
                    except _AckSkip:
                        # consumer signalled handler failure: leave in PEL, no ack.
                        continue
                    try:
                        await client.xack(stream, group, entry_id)
                    except Exception as exc:
                        log.warning("xack failed (will be reclaimed): %r", exc)
            # BLOCKER-2 fix: do NOT flip to '>' after the first PEL batch. A
            # restarted consumer may own MANY pending entries (> claim_count);
            # keep re-reading with '0' until a '0' read comes back empty (handled
            # at the top / empty-entries branch), THEN the loop returns and the
            # caller switches to the live '>' phase. While start_id stays '0' we
            # simply loop again here and read the NEXT PEL batch.
            if start_id == "0" and not saw_entry:
                return

    async def close(self) -> None:
        for c in (self._client, self._consumer_client):
            if c is not None:
                try:
                    await c.aclose()
                except Exception:
                    pass
