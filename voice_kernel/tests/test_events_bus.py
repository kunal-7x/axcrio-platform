"""W8 EventBus tests (no real Redis): emit -> consumable, idempotent re-emit
deduped, tenant-scoped (no cross-tenant), fire-and-forget never blocks/raises,
registration via build_kernel(cfg, event_bus=impl), and the consumer dedup path.

The InMemoryEventBus faithfully models the load-bearing Redis semantics (per-
tenant streams, per-group cursor, iid dedup, fire-and-forget emit), so these
assertions are meaningful for the production bus too. The Redis-specific
serde/version/XADD-IDMP path is covered by mock-Redis tests in
test_events_redis.py.

Async tests use the repo convention: asyncio.run() inside a sync test (matches
test_rag_runtime.py / test_contracts.py — no asyncio_mode config needed).
"""
from __future__ import annotations

import asyncio

from voice_kernel.config import KernelConfig
from voice_kernel.contracts import Event, EventBus
from voice_kernel.kernel import build_kernel
from voice_kernel.events import (
    EventBusConfig,
    EventName,
    InMemoryEventBus,
    SinkConsumer,
    call_ended,
    call_started,
    lead_classified,
)
from voice_kernel.events.taxonomy import daily_report
from voice_kernel.events.serde import idempotency_id


def test_inmemory_conforms_to_protocol():
    bus = InMemoryEventBus()
    assert isinstance(bus, EventBus)  # runtime_checkable structural conformance


def test_emit_then_consumable():
    async def _run():
        bus = InMemoryEventBus()
        await bus.emit(call_started("c1", "tenantA", direction="outbound"))
        await bus.emit(call_ended("c1", "tenantA", duration_s=42))
        return bus.all_events("tenantA")

    got = asyncio.run(_run())
    names = [e.name for e in got]
    assert names == [EventName.CALL_STARTED.value, EventName.CALL_ENDED.value]
    assert got[1].payload["duration_s"] == 42


def test_idempotent_reemit_deduped():
    async def _run():
        bus = InMemoryEventBus()
        ev = call_started("c1", "tenantA", direction="outbound")
        # Same logical event object emitted twice -> identical iid -> one row.
        await bus.emit(ev)
        await bus.emit(ev)
        first = len(bus.all_events("tenantA"))
        # A genuinely different fact on the same call is NOT deduped.
        await bus.emit(call_ended("c1", "tenantA", duration_s=10))
        return first, len(bus.all_events("tenantA"))

    first, second = asyncio.run(_run())
    assert first == 1
    assert second == 2


def test_tenant_scoped_no_cross_tenant_bleed():
    async def _run():
        bus = InMemoryEventBus()
        await bus.emit(call_started("c1", "tenantA"))
        await bus.emit(call_started("c2", "tenantB"))
        return bus

    bus = asyncio.run(_run())
    a = bus.all_events("tenantA")
    b = bus.all_events("tenantB")
    assert [e.call_id for e in a] == ["c1"]
    assert [e.call_id for e in b] == ["c2"]
    # Streams are physically distinct keys (mirrors the RLS isolation rule).
    keys = set(bus.stream_keys())
    assert "vk:events:tenantA" in keys and "vk:events:tenantB" in keys
    # A tenantA cursor never advances over tenantB's stream.
    assert all(e.tenant_id == "tenantA" for e in bus.drain("tenantA"))


def test_empty_tenant_dropped_failclosed():
    async def _run():
        bus = InMemoryEventBus()
        # An event with no tenant must NOT land on any shared/wildcard stream.
        await bus.emit(Event(name="call_started", call_id="cX", tenant_id="", ts_iso="2026-06-18T19:00:00Z", payload={}))
        return bus.stream_keys()

    assert asyncio.run(_run()) == []


def test_emit_never_raises_on_broken_bus():
    """Fire-and-forget contract: even a bus whose internals are sabotaged must
    not propagate an exception to the (dial-loop) caller."""
    async def _run():
        bus = InMemoryEventBus()

        class Boom(set):
            def __contains__(self, k):  # break the dedup set lookup path
                raise RuntimeError("redis down")

        bus._seen["vk:events:tenantA"] = Boom()
        # Must swallow and return None — the call can never crash on an emit.
        return await bus.emit(call_started("c1", "tenantA"))

    assert asyncio.run(_run()) is None


def test_subscribe_delivers_and_autoacks():
    async def _run():
        bus = InMemoryEventBus(EventBusConfig(block_ms=50))
        await bus.emit(call_started("c1", "tenantA"))
        await bus.emit(lead_classified("c1", "tenantA", "hot", conversion_prob=0.91))
        received: list[Event] = []

        async def consume():
            async for ev in bus.subscribe("vk:events:tenantA", "dashboard"):
                received.append(ev)
                if len(received) == 2:
                    bus.close()
                    return

        await asyncio.wait_for(consume(), timeout=2.0)
        return received

    received = asyncio.run(_run())
    assert [e.name for e in received] == [EventName.CALL_STARTED.value, EventName.LEAD_HOT.value]
    assert received[1].payload["conversion_prob"] == 0.91


def test_two_groups_read_independently():
    async def _run():
        bus = InMemoryEventBus(EventBusConfig(block_ms=50))
        await bus.emit(call_started("c1", "tenantA"))
        return bus

    bus = asyncio.run(_run())
    # Each sink (group) has its own cursor: both see the event.
    assert len(bus.drain("tenantA", group="dashboard")) == 1
    assert len(bus.drain("tenantA", group="crm")) == 1
    # And each only once (cursor advanced).
    assert len(bus.drain("tenantA", group="dashboard")) == 0


def test_sink_consumer_dedup_and_handler():
    async def _run():
        bus = InMemoryEventBus(EventBusConfig(block_ms=50))
        cfg = bus.cfg
        handled: list[str] = []

        async def handler(ev: Event):
            handled.append(ev.name)

        consumer = SinkConsumer(bus, cfg, "tenantA", "analytics", handler)
        # Emit two distinct + one duplicate of the first (same iid).
        e1 = call_started("c1", "tenantA")
        await bus.emit(e1)
        await bus.emit(e1)  # stream-level dedup drops this
        await bus.emit(call_ended("c1", "tenantA", duration_s=5))

        task = asyncio.create_task(consumer.run())
        await asyncio.sleep(0.2)
        consumer.stop()
        bus.close()
        await asyncio.wait_for(task, timeout=2.0)
        return handled

    handled = asyncio.run(_run())
    # call_started handled once (dup collapsed), call_ended once.
    assert handled.count(EventName.CALL_STARTED.value) == 1
    assert handled.count(EventName.CALL_ENDED.value) == 1


def test_build_kernel_registers_event_bus_via_frozen_spec():
    """EARNER-LAW frozen contract: register via build_kernel(cfg, event_bus=impl)."""
    bus = InMemoryEventBus()
    kernel = build_kernel(KernelConfig(), event_bus=bus)
    assert kernel.svc.events is bus
    # The field-name and alias forms also work (additive).
    assert build_kernel(KernelConfig(), events=bus).svc.events is bus
    assert build_kernel(KernelConfig(), eventbus=bus).svc.events is bus


def test_handler_failure_redelivers_not_drops():
    """BLOCKER-1 regression: a handler that raises must NOT advance/ack the entry
    — it stays "in PEL" and is REDELIVERED until it succeeds (at-least-once),
    never silently dropped (at-most-once)."""
    async def _run():
        bus = InMemoryEventBus(EventBusConfig(block_ms=50))
        attempts: list[int] = []

        async def flaky(ev: Event):
            attempts.append(1)
            if len(attempts) < 3:  # fail the first two deliveries
                raise RuntimeError("transient sink error (DB blip)")
            # third delivery succeeds

        consumer = SinkConsumer(bus, bus.cfg, "tenantA", "crm", flaky)
        await bus.emit(call_started("c1", "tenantA"))
        task = asyncio.create_task(consumer.run())
        await asyncio.sleep(0.2)
        consumer.stop()
        bus.close()
        await asyncio.wait_for(task, timeout=2.0)
        return len(attempts)

    n = asyncio.run(_run())
    # Delivered 3x (2 failures left it in PEL + 1 success) — proves no drop.
    assert n >= 3


def test_idempotency_id_stable_and_distinct():
    e1 = call_started("c1", "tenantA", ts_iso="2026-06-18T19:00:00Z")
    e2 = call_started("c1", "tenantA", ts_iso="2026-06-18T19:00:00Z")
    assert idempotency_id(e1) == idempotency_id(e2)  # same content -> same id
    e3 = call_ended("c1", "tenantA", ts_iso="2026-06-18T19:00:00Z")
    assert idempotency_id(e1) != idempotency_id(e3)  # different fact -> different id


def test_daily_report_idempotent_per_tenant_day():
    """FIX-NOW 3 regression: two daily-report rollups for the SAME (tenant, day)
    collapse to ONE iid (no wall-clock in the id), so a re-run / double-trigger
    dedupes. A different day must differ."""
    a = daily_report("tenantA", report_date="2026-06-18")
    b = daily_report("tenantA", report_date="2026-06-18")
    c = daily_report("tenantA", report_date="2026-06-19")
    assert idempotency_id(a) == idempotency_id(b)  # same (tenant, day) -> dedupes
    assert idempotency_id(a) != idempotency_id(c)  # different day -> distinct
    assert a.ts_iso == "2026-06-18T00:00:00Z"      # pinned, not wall-clock
