"""RetentionManager: deletes EXPIRED raw media (archive R2->B2 then delete),
PRESERVES summary/lead intel, refuses to delete when intel is not preserved,
produces an immutable deletion audit, and reports tenant-scoped storage usage.
"""
from __future__ import annotations

from datetime import timedelta

from voice_ops.recording.config import RecordingConfig, StorageTier
from voice_ops.recording.retention import RetentionCandidate, RetentionManager
from voice_kernel.events.timeutil import now_utc, _to_z

from .conftest import FakeStorage


def _iso_days_ago(n: int) -> str:
    return _to_z(now_utc() - timedelta(days=n))


def _cfg(retention_days=30, with_archive=True):
    archive = StorageTier(name="b2", bucket="arc", endpoint="https://b2", access_key="a", secret_key="s") if with_archive else StorageTier()
    return RecordingConfig(
        enabled=True, retention_days=retention_days, key_prefix="recordings",
        primary=StorageTier(name="r2", bucket="hot", endpoint="https://r2", access_key="a", secret_key="s"),
        archive=archive,
    )


def test_expired_raw_archived_then_deleted_intel_preserved():
    storage = FakeStorage(objects={"recordings/t/x/old.ogg": 10_000})
    rm = RetentionManager(_cfg(), storage=storage, archive_first=True)
    cands = [RetentionCandidate(
        call_id="c1", tenant_id="t", key="recordings/t/x/old.ogg",
        created_iso=_iso_days_ago(40), summary_preserved=True,
    )]
    rep = rm.sweep(cands)
    assert rep.archived == 1 and rep.deleted == 1
    assert rep.bytes_reclaimed == 10_000
    assert storage.archived == ["recordings/t/x/old.ogg"]
    assert "recordings/t/x/old.ogg" not in storage.objects  # raw gone
    assert len(rep.audit) == 1
    a = rep.audit[0]
    assert a.action == "archived_then_deleted"
    assert a.intel_preserved is True and a.deleted is True


def test_not_expired_is_skipped():
    storage = FakeStorage(objects={"recordings/t/x/new.ogg": 10_000})
    rm = RetentionManager(_cfg(), storage=storage)
    rep = rm.sweep([RetentionCandidate(
        call_id="c2", tenant_id="t", key="recordings/t/x/new.ogg",
        created_iso=_iso_days_ago(5), summary_preserved=True,
    )])
    assert rep.deleted == 0 and rep.skipped == 1
    assert "recordings/t/x/new.ogg" in storage.objects  # untouched
    assert rep.audit[0].action == "skipped_not_expired"


def test_refuse_delete_when_intel_not_preserved():
    storage = FakeStorage(objects={"recordings/t/x/risky.ogg": 10_000})
    rm = RetentionManager(_cfg(), storage=storage)
    rep = rm.sweep([RetentionCandidate(
        call_id="c3", tenant_id="t", key="recordings/t/x/risky.ogg",
        created_iso=_iso_days_ago(99), summary_preserved=False,  # intel NOT saved
    )])
    # FAIL-SAFE: never destroy the only copy of the business signal
    assert rep.deleted == 0 and rep.skipped == 1
    assert "recordings/t/x/risky.ogg" in storage.objects
    assert rep.audit[0].action == "skipped_no_intel"
    assert rep.audit[0].intel_preserved is False


def test_force_overrides_intel_guard():
    storage = FakeStorage(objects={"recordings/t/x/risky.ogg": 10_000})
    rm = RetentionManager(_cfg(), storage=storage)
    rep = rm.sweep(
        [RetentionCandidate(call_id="c4", tenant_id="t", key="recordings/t/x/risky.ogg",
                            created_iso=_iso_days_ago(99), summary_preserved=False)],
        force=True,
    )
    assert rep.deleted == 1
    assert "recordings/t/x/risky.ogg" not in storage.objects


def test_delete_without_archive_tier():
    storage = FakeStorage(objects={"recordings/t/x/old.ogg": 5_000})
    rm = RetentionManager(_cfg(with_archive=False), storage=storage, archive_first=True)
    rep = rm.sweep([RetentionCandidate(
        call_id="c5", tenant_id="t", key="recordings/t/x/old.ogg",
        created_iso=_iso_days_ago(40), summary_preserved=True,
    )])
    assert rep.archived == 0 and rep.deleted == 1
    assert rep.audit[0].action == "deleted"


def test_storage_usage_is_tenant_scoped():
    storage = FakeStorage(objects={
        "recordings/t/a/1.ogg": 1000,
        "recordings/t/b/2.ogg": 2000,
        "recordings/OTHER/c/3.ogg": 9999,  # different tenant, must NOT count
    })
    rm = RetentionManager(_cfg(), storage=storage)
    u = rm.storage_usage("t")
    assert u["objects"] == 2 and u["bytes"] == 3000
    assert u["tenant_id"] == "t"


def test_bad_timestamp_is_not_expired_failsafe():
    rm = RetentionManager(_cfg(), storage=FakeStorage(objects={"k": 1}))
    assert rm.is_expired("not-a-date") is False  # never delete on a parse error
