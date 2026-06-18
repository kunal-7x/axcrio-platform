"""StagedPipeline: recording_ready -> transcript_ready -> summary_ready, IN ORDER.
Each artifact emits its own typed W8 event as it becomes ready; empty stages are
skipped, never reordered. Repo convention: asyncio.run() inside a sync test.
"""
from __future__ import annotations

import asyncio

from voice_ops.recording.config import RecordingConfig
from voice_ops.recording.egress import EgressClient
from voice_ops.recording.poller import FinalizePoller
from voice_ops.recording.pipeline import StagedPipeline
from voice_kernel.events import InMemoryEventBus, EventName

from .conftest import FakeEgressInfo, FakeFileResult, FakeLiveKitClient, FakeStorage


async def _noop_sleep(_s):
    return None


def _cfg():
    return RecordingConfig(enabled=True, poll_interval_s=0.0, poll_timeout_s=1.0, min_playable_bytes=2048)


def _poller(bus, storage):
    egress = EgressClient(client=FakeLiveKitClient([[
        FakeEgressInfo(egress_id="EG", room_name="room-1", status=3,
                       file_results=[FakeFileResult(duration=8_000_000_000, size=40_000,
                                                    filename="recordings/t/x/room-1.ogg")]),
    ]]))
    return FinalizePoller(_cfg(), bus=bus, egress=egress, storage=storage, sleep=_noop_sleep)


def test_all_three_stages_emit_in_order():
    bus = InMemoryEventBus()
    storage = FakeStorage(objects={"recordings/t/x/room-1.ogg": 40_000})

    def transcript_provider(tenant, call):
        return {"turns": [{"role": "user", "text": "hi"}, {"role": "agent", "text": "namaste"}], "text": "hi namaste"}

    async def summary_provider(tenant, call, transcript):  # async provider supported
        assert transcript.get("text")  # got the transcript from stage 2
        return {"summary": "interested", "lifecycle": "hot", "conversion_prob": 0.8}

    pipe = StagedPipeline(
        _cfg(), bus=bus, poller=_poller(bus, storage),
        transcript_provider=transcript_provider, summary_provider=summary_provider,
    )
    res = asyncio.run(pipe.run(call_id="room-1", tenant_id="t", room_name="room-1"))

    assert res.stages_emitted == ["recording_ready", "transcript_ready", "summary_ready"]
    assert res.has_transcript and res.transcript_turns == 2
    assert res.has_summary and res.lifecycle == "hot"

    # the BUS observed them in the same canonical order
    names = [e.name for e in bus.all_events("t")]
    order = [n for n in names if n in (
        EventName.RECORDING_READY.value, EventName.TRANSCRIPT_READY.value, EventName.SUMMARY_READY.value)]
    assert order == [
        EventName.RECORDING_READY.value, EventName.TRANSCRIPT_READY.value, EventName.SUMMARY_READY.value,
    ]


def test_empty_transcript_skips_transcript_and_summary():
    bus = InMemoryEventBus()
    storage = FakeStorage(objects={"recordings/t/x/room-1.ogg": 40_000})
    pipe = StagedPipeline(
        _cfg(), bus=bus, poller=_poller(bus, storage),
        transcript_provider=lambda t, c: {"turns": [], "text": ""},   # empty
        summary_provider=lambda t, c, tr: {"summary": "x", "lifecycle": "warm"},
    )
    res = asyncio.run(pipe.run(call_id="room-1", tenant_id="t", room_name="room-1"))
    # recording still finalized + emitted; transcript skipped; summary may still run independently
    assert "recording_ready" in res.stages_emitted
    assert "transcript_ready" not in res.stages_emitted
    assert res.has_transcript is False


def test_no_providers_only_recording_stage():
    bus = InMemoryEventBus()
    storage = FakeStorage(objects={"recordings/t/x/room-1.ogg": 40_000})
    pipe = StagedPipeline(_cfg(), bus=bus, poller=_poller(bus, storage))  # no providers
    res = asyncio.run(pipe.run(call_id="room-1", tenant_id="t", room_name="room-1"))
    assert res.stages_emitted == ["recording_ready"]
    assert res.has_transcript is False and res.has_summary is False


def test_summary_emits_even_if_recording_not_playable():
    bus = InMemoryEventBus()
    storage = FakeStorage(objects={"recordings/t/x/room-1.ogg": 50})  # tiny -> not playable
    pipe = StagedPipeline(
        _cfg(), bus=bus, poller=_poller(bus, storage),
        transcript_provider=lambda t, c: {"turns": [{"x": 1}], "text": "hi"},
        summary_provider=lambda t, c, tr: {"summary": "ok", "lifecycle": "warm"},
    )
    res = asyncio.run(pipe.run(call_id="room-1", tenant_id="t", room_name="room-1"))
    # artifacts are independent: recording not playable, but transcript + summary still emit, in order
    assert res.stages_emitted == ["recording_ready", "transcript_ready", "summary_ready"]
    assert res.recording.playable is False
