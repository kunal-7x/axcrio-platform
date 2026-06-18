"""build_recording_view: the panel status contract. Self-heals a stuck status via
a HEAD on the deterministic key, mints a presigned url only when playable, and
returns exactly the field set the panel reads.
"""
from __future__ import annotations

from voice_ops.recording.config import RecordingConfig, StorageTier
from voice_ops.recording.api import build_recording_view, recordings_envelope

from .conftest import FakeStorage


_PANEL_FIELDS = {
    "call_id", "direction", "phone", "started_at", "duration_s", "status",
    "recording_status", "has_recording", "playable", "recording_presigned_url",
}


def _cfg():
    return RecordingConfig(
        enabled=True, key_prefix="recordings",
        primary=StorageTier(name="r2", bucket="hot", endpoint="https://r2", access_key="a", secret_key="s"),
    )


def test_view_has_exact_panel_field_set():
    v = build_recording_view(call_id="c1", tenant_id="t", cfg=_cfg(), storage=FakeStorage())
    assert set(v.keys()) == _PANEL_FIELDS


def test_self_heal_stuck_recording_when_object_playable():
    cfg = _cfg()
    # the deterministic key for (t, c1) — object exists + playable
    from voice_ops.recording.config import object_key
    key = object_key("t", "c1", prefix="recordings")
    storage = FakeStorage(objects={key: 50_000})
    v = build_recording_view(
        call_id="c1", tenant_id="t", recording_status="recording",  # STUCK
        cfg=cfg, storage=storage,
    )
    assert v["recording_status"] == "completed"   # self-healed
    assert v["playable"] is True
    assert v["recording_presigned_url"].startswith("https://fake.r2/")
    assert v["has_recording"] is True


def test_in_progress_stays_when_no_object():
    v = build_recording_view(
        call_id="c2", tenant_id="t", recording_status="recording",
        cfg=_cfg(), storage=FakeStorage(),  # no objects
    )
    assert v["recording_status"] == "recording"
    assert v["playable"] is False
    assert v["recording_presigned_url"] == ""


def test_claimed_done_but_unplayable_demoted_to_pending():
    from voice_ops.recording.config import object_key
    key = object_key("t", "c3", prefix="recordings")
    storage = FakeStorage(objects={key: 100})  # below floor
    v = build_recording_view(
        call_id="c3", tenant_id="t", recording_status="completed",
        cfg=_cfg(), storage=storage,
    )
    assert v["recording_status"] == "pending"  # demoted, no broken player
    assert v["playable"] is False


def test_disabled_recording_no_key_no_url():
    v = build_recording_view(
        call_id="c4", tenant_id="t", recording_status="disabled",
        cfg=_cfg(), storage=FakeStorage(),
    )
    assert v["recording_status"] == "disabled"
    assert v["has_recording"] is False
    assert v["recording_presigned_url"] == ""


def test_envelope_totals():
    cfg = _cfg()
    from voice_ops.recording.config import object_key
    k1 = object_key("t", "c1", prefix="recordings")
    storage = FakeStorage(objects={k1: 50_000})
    v1 = build_recording_view(call_id="c1", tenant_id="t", phone="+91999", recording_status="recording", cfg=cfg, storage=storage)
    v2 = build_recording_view(call_id="c2", tenant_id="t", phone="+91999", recording_status="recording", cfg=cfg, storage=FakeStorage())
    env = recordings_envelope([v1, v2], phone="+91999")
    assert env["total"] == 2
    assert env["with_playable"] == 1   # only v1's object is playable
    # both derive a deterministic key (not disabled) -> both have_recording=True
    assert env["with_recording"] == 2


def test_no_storage_degrades_gracefully():
    v = build_recording_view(call_id="c5", tenant_id="t", recording_status="recording", cfg=_cfg(), storage=None)
    assert v["recording_status"] == "recording"
    assert v["playable"] is False
