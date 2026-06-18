"""The CORE fix: FinalizePoller polls ListEgress -> on EGRESS_COMPLETE flips
recording_status to 'completed' AND emits exactly one recording_ready on the W8
EventBus. Works for outbound (room filter) + inbound (egress_id). Tenant-scoped.

Async tests use the repo convention: asyncio.run() inside a sync test (matches
voice_kernel/tests/test_events_bus.py — no asyncio_mode config needed).
"""
from __future__ import annotations

import asyncio

from voice_ops.recording.config import RecordingConfig
from voice_ops.recording.egress import EgressClient
from voice_ops.recording.poller import FinalizePoller
from voice_kernel.events import InMemoryEventBus, EventName

from .conftest import FakeEgressInfo, FakeFileResult, FakeLiveKitClient, FakeStorage


async def _noop_sleep(_s):  # instant — no real waiting in tests
    return None


def _cfg(**kw):
    base = dict(enabled=True, poll_interval_s=0.0, poll_timeout_s=1.0, min_playable_bytes=2048)
    base.update(kw)
    return RecordingConfig(**base)


def _completed_egress(room="room-1", eid="EG_1", dur_ns=12_000_000_000, size=50_000, key="recordings/t/x/room-1.ogg"):
    return FakeEgressInfo(
        egress_id=eid, room_name=room, status=3,
        file_results=[FakeFileResult(duration=dur_ns, size=size, filename=key)],
    )


def test_outbound_finalize_flips_to_completed_and_emits():
    bus = InMemoryEventBus()
    storage = FakeStorage(objects={"recordings/t/x/room-1.ogg": 50_000})
    # outbound: first poll STILL active (status=1), second poll COMPLETE.
    scripted = [
        [FakeEgressInfo(egress_id="EG_1", room_name="room-1", status=1)],
        [_completed_egress()],
    ]
    poller = FinalizePoller(
        _cfg(), bus=bus, egress=EgressClient(client=FakeLiveKitClient(scripted)),
        storage=storage, sleep=_noop_sleep,
    )
    res = asyncio.run(poller.finalize(call_id="room-1", tenant_id="t", room_name="room-1", direction="outbound"))

    assert res.recording_status == "completed"
    assert res.duration_s == 12
    assert res.playable is True
    assert res.url.startswith("https://fake.r2/")
    assert res.emitted_ready is True
    assert res.polls >= 2  # had to poll past the active state

    events = bus.all_events("t")
    ready = [e for e in events if e.name == EventName.RECORDING_READY.value]
    assert len(ready) == 1
    assert ready[0].tenant_id == "t" and ready[0].call_id == "room-1"
    assert ready[0].payload.get("duration_s") == 12
    assert ready[0].payload.get("playable") is True
    # the durable event carries the KEY, not the volatile signed url (sink presigns on read)
    assert ready[0].payload.get("key") == "recordings/t/x/room-1.ogg"
    assert ready[0].payload.get("url", "") == ""


def test_inbound_finalize_by_egress_id():
    bus = InMemoryEventBus()
    storage = FakeStorage(objects={"aim/2026/x/sess.ogg": 30_000})
    scripted = [[_completed_egress(room="aim-room", eid="EG_IN", key="aim/2026/x/sess.ogg")]]
    poller = FinalizePoller(
        _cfg(), bus=bus, egress=EgressClient(client=FakeLiveKitClient(scripted)),
        storage=storage, sleep=_noop_sleep,
    )
    res = asyncio.run(poller.finalize(
        call_id="sess-1", tenant_id="t2", room_name="aim-room",
        egress_id="EG_IN", direction="inbound",
    ))
    assert res.recording_status == "completed"
    assert res.emitted_ready is True
    assert res.key == "aim/2026/x/sess.ogg"
    ready = [e for e in bus.all_events("t2") if e.name == EventName.RECORDING_READY.value]
    assert len(ready) == 1
    assert ready[0].payload.get("direction") == "inbound"


def test_failed_egress_no_ready_event():
    bus = InMemoryEventBus()
    scripted = [[FakeEgressInfo(egress_id="EG_F", room_name="room-x", status=4)]]  # FAILED
    poller = FinalizePoller(
        _cfg(), bus=bus, egress=EgressClient(client=FakeLiveKitClient(scripted)),
        storage=FakeStorage(), sleep=_noop_sleep,
    )
    res = asyncio.run(poller.finalize(call_id="room-x", tenant_id="t", room_name="room-x"))
    assert res.recording_status == "failed"
    assert res.emitted_ready is False
    assert bus.all_events("t") == []  # no recording_ready for a failed recording


def test_timeout_when_never_completes():
    bus = InMemoryEventBus()
    # always active, never completes -> deadline hit
    scripted = [[FakeEgressInfo(egress_id="EG_A", room_name="room-z", status=1)]]
    poller = FinalizePoller(
        _cfg(poll_interval_s=0.0, poll_timeout_s=0.0), bus=bus,
        egress=EgressClient(client=FakeLiveKitClient(scripted)),
        storage=FakeStorage(), sleep=_noop_sleep,
    )
    res = asyncio.run(poller.finalize(call_id="room-z", tenant_id="t", room_name="room-z"))
    assert res.recording_status == "timeout"
    assert res.emitted_ready is False


def test_completed_but_tiny_file_not_playable():
    bus = InMemoryEventBus()
    # COMPLETE egress but the object is below the playable floor (486-busy / empty)
    storage = FakeStorage(objects={"recordings/t/x/room-1.ogg": 100})  # < 2048
    scripted = [[_completed_egress(size=100)]]
    poller = FinalizePoller(
        _cfg(), bus=bus, egress=EgressClient(client=FakeLiveKitClient(scripted)),
        storage=storage, sleep=_noop_sleep,
    )
    res = asyncio.run(poller.finalize(call_id="room-1", tenant_id="t", room_name="room-1"))
    assert res.recording_status == "completed"   # egress did complete
    assert res.playable is False                  # but not a playable artifact
    assert res.url == ""
    # still emits recording_ready (completed) so the panel updates, but with playable=False
    ready = [e for e in bus.all_events("t") if e.name == EventName.RECORDING_READY.value]
    assert len(ready) == 1 and ready[0].payload.get("playable") is False


def test_fail_closed_empty_tenant():
    poller = FinalizePoller(_cfg(), bus=InMemoryEventBus(), egress=EgressClient(client=FakeLiveKitClient([])), sleep=_noop_sleep)
    res = asyncio.run(poller.finalize(call_id="c", tenant_id="", room_name="c"))
    assert res.recording_status == "failed"
    assert res.emitted_ready is False


def test_reemit_is_idempotent_on_bus():
    bus = InMemoryEventBus()
    storage = FakeStorage(objects={"recordings/t/x/room-1.ogg": 50_000})
    scripted = [[_completed_egress()]]
    poller = FinalizePoller(
        _cfg(), bus=bus, egress=EgressClient(client=FakeLiveKitClient(scripted)),
        storage=storage, sleep=_noop_sleep,
    )
    asyncio.run(poller.finalize(call_id="room-1", tenant_id="t", room_name="room-1"))
    # second finalize for the SAME completed egress -> same event -> deduped
    poller2 = FinalizePoller(
        _cfg(), bus=bus, egress=EgressClient(client=FakeLiveKitClient([[_completed_egress()]])),
        storage=storage, sleep=_noop_sleep,
    )
    asyncio.run(poller2.finalize(call_id="room-1", tenant_id="t", room_name="room-1"))
    ready = [e for e in bus.all_events("t") if e.name == EventName.RECORDING_READY.value]
    assert len(ready) == 1, "identical recording_ready must dedup on the bus (idempotent)"
