"""RecordingConfig defaults OFF; deterministic object key; fail-closed tenant."""
from __future__ import annotations

import pytest

from voice_ops.recording.config import RecordingConfig, StorageTier, object_key


def test_default_off_no_env(monkeypatch):
    for k in (
        "RECORDING_FINALIZE_ENABLED", "RECORDING_SEGMENTED",
        "R2_BUCKET", "R2_ENDPOINT", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY",
        "B2_BUCKET", "B2_ENDPOINT", "B2_ACCESS_KEY_ID", "B2_SECRET_ACCESS_KEY",
    ):
        monkeypatch.delenv(k, raising=False)
    cfg = RecordingConfig.from_env()
    assert cfg.enabled is False
    assert cfg.segmented is False
    assert cfg.retention_days == 30
    assert cfg.storage_ready is False  # no creds


def test_storage_tier_complete(monkeypatch):
    monkeypatch.setenv("R2_BUCKET", "famit-calls")
    monkeypatch.setenv("R2_ENDPOINT", "https://acct.r2.cloudflarestorage.com")
    monkeypatch.setenv("R2_ACCESS_KEY_ID", "ak")
    monkeypatch.setenv("R2_SECRET_ACCESS_KEY", "sk")
    cfg = RecordingConfig.from_env()
    assert cfg.primary.complete is True
    assert cfg.storage_ready is True
    assert cfg.archive.complete is False  # B2 not set


def test_object_key_deterministic_and_tenant_partitioned():
    k1 = object_key("tenant-a", "room-123", ts=0)  # ts pinned -> stable day
    k2 = object_key("tenant-a", "room-123", ts=0)
    assert k1 == k2, "same (tenant, call) must map to the same key"
    assert k1.startswith("recordings/tenant-a/")
    assert k1.endswith("room-123.ogg")
    # different tenant -> different partition (hard isolation)
    kb = object_key("tenant-b", "room-123", ts=0)
    assert "/tenant-a/" not in kb and "/tenant-b/" in kb


def test_object_key_fail_closed_empty_tenant():
    with pytest.raises(ValueError):
        object_key("", "room-1")


def test_object_key_custom_prefix_and_ext():
    k = object_key("t", "c", prefix="archive", ext="m4a", ts=0)
    assert k.startswith("archive/t/") and k.endswith("c.m4a")
