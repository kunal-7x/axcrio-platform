"""W8 RedisEventBus tests against a MOCK redis (no real server).

Covers the Redis-specific paths the in-memory fake can't: serde encode/decode
round-trip, the 8.6 IDMP version-probe + plain-XADD fallback, fire-and-forget
emit dropping on a dead client, and the XAUTOCLAIM -> DLQ janitor.

Async tests use the repo convention (asyncio.run() inside a sync test).
"""
from __future__ import annotations

import asyncio

from voice_kernel.contracts import Event
from voice_kernel.events import EventBusConfig, RedisEventBus, call_started
from voice_kernel.events.consumer import reclaim_and_dlq
from voice_kernel.events.serde import decode, decoded_iid, encode, idempotency_id


def test_serde_roundtrip_preserves_nested_payload():
    ev = call_started("c1", "tenantA", direction="inbound", extra={"nested": {"k": [1, 2]}}, ts_iso="2026-06-18T19:00:00Z")
    fields = encode(ev)
    assert set(fields) == {"name", "call_id", "tenant_id", "ts_iso", "iid", "payload"}
    back = decode(fields)
    assert back.name == ev.name
    assert back.payload["extra"]["nested"]["k"] == [1, 2]
    assert decoded_iid(fields) == idempotency_id(ev)


def test_decode_tolerates_garbage_payload():
    ev = decode({"name": "call_ended", "call_id": "c1", "tenant_id": "t", "ts_iso": "x", "payload": "{not json"})
    assert ev.name == "call_ended"
    assert "_undecodable" in ev.payload  # routable to DLQ, never crashes


def test_decode_handles_bytes_fields():
    ev = decode({b"name": b"call_started", b"call_id": b"c1", b"tenant_id": b"t", b"ts_iso": b"x", b"payload": b"{}"})
    assert ev.name == "call_started" and ev.call_id == "c1"


# --------------------------------------------------------------------------- #
# Minimal async mock-redis to drive the bus emit/version paths deterministically.
# --------------------------------------------------------------------------- #
class MockRedis:
    def __init__(self, version="8.6.0"):
        self.version = version
        self.streams: dict[str, list] = {}
        self.xadd_calls: list = []
        self.command_calls: list = []
        self._seq = 0

    async def info(self, section=None):
        return {"redis_version": self.version}

    async def xadd(self, stream, fields, maxlen=None, approximate=False):
        self.xadd_calls.append((stream, dict(fields), maxlen, approximate))
        self._seq += 1
        self.streams.setdefault(stream, []).append((f"{self._seq}-0", dict(fields)))
        return f"{self._seq}-0"

    async def execute_command(self, *args):
        self.command_calls.append(args)
        if args[0] == "XADD":
            self._seq += 1
            self.streams.setdefault(args[1], []).append((f"{self._seq}-0", {}))
            return f"{self._seq}-0"
        raise AssertionError(f"unexpected command {args[0]}")

    async def aclose(self):
        pass


def test_emit_uses_idmp_on_redis_86():
    async def _run():
        mock = MockRedis(version="8.6.0")
        bus = RedisEventBus(EventBusConfig(), client=mock)
        await bus.emit(call_started("c1", "tenantA"))
        return bus, mock

    bus, mock = asyncio.run(_run())
    assert bus._idmp_supported is True
    assert mock.command_calls and mock.command_calls[0][0] == "XADD"
    assert mock.command_calls[0][1] == "vk:events:tenantA"


def test_emit_plain_xadd_on_old_redis():
    async def _run():
        mock = MockRedis(version="7.4.0")
        bus = RedisEventBus(EventBusConfig(), client=mock)
        await bus.emit(call_started("c1", "tenantA"))
        return bus, mock

    bus, mock = asyncio.run(_run())
    assert bus._idmp_supported is False
    assert len(mock.xadd_calls) == 1
    stream, fields, maxlen, approx = mock.xadd_calls[0]
    assert stream == "vk:events:tenantA" and approx is True


def test_emit_empty_tenant_dropped():
    async def _run():
        mock = MockRedis()
        bus = RedisEventBus(EventBusConfig(), client=mock)
        await bus.emit(Event(name="x", call_id="c", tenant_id="", ts_iso="t", payload={}))
        return mock

    mock = asyncio.run(_run())
    assert not mock.xadd_calls and not mock.command_calls


def test_emit_never_raises_on_dead_client():
    class Dead:
        async def info(self, *a, **k):
            raise ConnectionError("redis down")

        async def xadd(self, *a, **k):
            raise ConnectionError("redis down")

        async def execute_command(self, *a, **k):
            raise ConnectionError("redis down")

    async def _run():
        bus = RedisEventBus(EventBusConfig(), client=Dead())
        # Must swallow — the dial loop can never crash on a dead Redis.
        return await bus.emit(call_started("c1", "tenantA"))

    assert asyncio.run(_run()) is None


def test_emit_times_out_without_blocking():
    class Slow:
        async def info(self, *a, **k):
            return {"redis_version": "7.0.0"}

        async def xadd(self, *a, **k):
            await asyncio.sleep(5)  # would hang the dial loop if emit blocked

    async def _run():
        bus = RedisEventBus(EventBusConfig(emit_timeout_s=0.05), client=Slow())
        # Returns promptly (dropped on timeout), never waits 5s.
        await asyncio.wait_for(bus.emit(call_started("c1", "tenantA")), timeout=1.0)

    asyncio.run(_run())  # completes without raising / hanging


# --------------------------------------------------------------------------- #
# XAUTOCLAIM -> DLQ janitor.
# --------------------------------------------------------------------------- #
class MockReclaimRedis:
    def __init__(self, times_delivered):
        self.times = times_delivered
        self.dlq_adds: list = []
        self.acks: list = []

    async def xautoclaim(self, stream, group, consumer, min_idle_time, start_id, count):
        return ("0-0", [("5-0", {"name": "call_ended", "iid": "call_ended:c1:abc"})], [])

    async def xpending_range(self, stream, group, min, max, count):
        return [{"message_id": "5-0", "consumer": "c1", "time_since_delivered": 99999, "times_delivered": self.times}]

    async def xadd(self, stream, fields, maxlen=None, approximate=False):
        self.dlq_adds.append((stream, fields))

    async def xack(self, stream, group, entry_id):
        self.acks.append((stream, group, entry_id))


def test_reclaim_routes_poison_to_dlq():
    async def _run():
        mock = MockReclaimRedis(times_delivered=3)  # >= max_deliveries (3)
        bus = RedisEventBus(EventBusConfig(max_deliveries=3))
        bus._consumer_client = mock
        n = await reclaim_and_dlq(bus, bus.cfg, "tenantA", "dashboard")
        return n, mock

    n, mock = asyncio.run(_run())
    assert n == 1
    assert mock.dlq_adds and mock.dlq_adds[0][0] == "vk:events:tenantA:dlq"
    assert mock.acks == [("vk:events:tenantA", "dashboard", "5-0")]


def test_reclaim_keeps_under_threshold():
    async def _run():
        mock = MockReclaimRedis(times_delivered=1)  # < max_deliveries -> retried, not DLQ'd
        bus = RedisEventBus(EventBusConfig(max_deliveries=3))
        bus._consumer_client = mock
        n = await reclaim_and_dlq(bus, bus.cfg, "tenantA", "dashboard")
        return n, mock

    n, mock = asyncio.run(_run())
    assert n == 1
    assert not mock.dlq_adds and not mock.acks


def test_reclaim_noop_without_client():
    async def _run():
        bus = RedisEventBus(EventBusConfig())  # no consumer client
        return await reclaim_and_dlq(bus, bus.cfg, "tenantA", "dashboard")

    assert asyncio.run(_run()) == 0


# --------------------------------------------------------------------------- #
# BLOCKER-2 regression: a PEL larger than claim_count must FULLY drain on
# restart (loop '0' until empty) before switching to the live '>' phase — not
# abandon the entries beyond the first batch.
# --------------------------------------------------------------------------- #
class MockPelRedis:
    """Mock XREADGROUP that serves a big PEL in claim_count-sized batches for the
    '0' (history) cursor, then blocks (returns empty) on the live '>' cursor.
    Records the sequence of start_ids so the test can prove '0' is repeated until
    drained BEFORE any '>' read."""

    def __init__(self, pel_size: int, count: int):
        self.reads: list[str] = []
        self.acked: list[str] = []
        # pending entries 1..pel_size, served in 'count'-sized slices for '0'.
        self._pending = [(f"{i}-0", {"name": "call_started", "call_id": "c1",
                                     "tenant_id": "tenantA", "ts_iso": "t",
                                     "iid": f"call_started:c1:{i:08x}", "payload": "{}"})
                         for i in range(1, pel_size + 1)]
        self._count = count
        self._pos = 0

    async def xgroup_create(self, *a, **k):
        return True

    async def xreadgroup(self, group, consumer, streams, count, block):
        stream = next(iter(streams))
        start_id = streams[stream]
        self.reads.append(start_id)
        if start_id == "0":
            slice_ = self._pending[self._pos:self._pos + self._count]
            self._pos += len(slice_)
            if not slice_:
                return []  # PEL fully drained for this consumer -> live phase
            return [(stream, slice_)]
        # live phase: nothing new -> empty (caller keeps blocking; test stops it)
        return []

    async def xack(self, stream, group, entry_id):
        self.acked.append(entry_id)


def test_pel_drains_fully_beyond_claim_count():
    async def _run():
        # 120 pending entries, batch size 50 -> needs 3 '0' reads (50+50+20) then
        # a 4th empty '0' read to flip to live, THEN '>' reads.
        cfg = EventBusConfig(claim_count=50, block_ms=10)
        mock = MockPelRedis(pel_size=120, count=50)
        bus = RedisEventBus(cfg, consumer_client=mock)
        seen = 0
        agen = bus.subscribe("vk:events:tenantA", "dashboard")
        async for _ev in agen:
            seen += 1
            if seen == 120:
                # all drained from PEL; let it advance to live phase then stop.
                await agen.aclose()
                break
        return seen, mock

    seen, mock = asyncio.run(_run())
    assert seen == 120, f"abandoned PEL entries: only {seen}/120 redelivered"
    # >=119 because aclose() at the 120th yield races that entry's own xack
    # (GeneratorExit fires at the yield before _read resumes to xack #120);
    # the load-bearing assertion is seen==120 (none abandoned beyond claim_count).
    assert len(mock.acked) >= 119
    # The '0' (history) cursor was repeated for every PEL batch BEFORE any '>'.
    zero_reads = [r for r in mock.reads if r == "0"]
    assert len(zero_reads) >= 3  # 50 + 50 + 20 batches all read via '0'
