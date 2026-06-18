"""W16 — voice_ops.whatsapp tests (mock storage / PG / WA).

Covers the founder's full ask + the earner-safe contracts:
  - media upload / validate / reuse / replace / preview / archive / delete
  - audience resolves the CORRECT lead sets (hot/warm/cold/dead, campaign, agent,
    requested-brochure, follow-up-pending, segment, explicit, fail-closed-empty)
  - send is DORMANT-without-creds but fully WIRED (records skipped_no_config),
    and DISPATCHES when creds are active
  - delivery events tracked (sent -> delivered -> read; failed; opted-out; forward-only)
  - TENANT ISOLATION across every store

No Postgres / boto3 / WA creds — InMemory backends + a fake storage + stub sender.
"""
from __future__ import annotations

import pytest

from voice_ops.whatsapp import (
    MediaLibrary, AudienceResolver, DeliveryTracker, SendOrchestrator,
    MediaStore, DeliveryStore, InMemoryMediaBackend, InMemoryDeliveryBackend,
    MediaKind, DeliveryStatus, AudienceSpec,
)
from voice_ops.whatsapp.store import MediaStore as _MS
from voice_ops.reporting.store import ReportingStore
from voice_ops.reporting.model import FactCall, LeadStatus


PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
PDF = b"%PDF-1.7\n" + b"\x00" * 64
MP4 = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 64


# --------------------------------------------------------------------------- #
# Fake W9 storage (records put/presign/delete; no boto3)
# --------------------------------------------------------------------------- #
class FakeStorage:
    def __init__(self):
        self.objects = {}

    def tier(self, name="primary"):
        class _T:
            bucket = "test-bucket"
        return _T()

    def _client(self, tier):
        store = self.objects

        class _C:
            def put_object(self, Bucket, Key, Body, ContentType):
                store[Key] = (Body, ContentType)

        return _C()

    def presign_get(self, key, *, tier="primary", expires_s=3600):
        return f"https://cdn.test/{key}?sig=abc" if key in self.objects else ""

    def delete(self, key, *, tier="primary"):
        return self.objects.pop(key, None) is not None

    def usage(self, *, tier="primary", prefix=""):
        objs = [k for k in self.objects if k.startswith(prefix)]
        return {"objects": len(objs), "bytes": sum(len(self.objects[k][0]) for k in objs)}


@pytest.fixture
def lib():
    return MediaLibrary(store=MediaStore(InMemoryMediaBackend()), storage=FakeStorage())


# =========================================================================== #
# MEDIA LIBRARY
# =========================================================================== #
def test_media_upload_image_stores_bytes_and_metadata(lib):
    r = lib.upload("t1", kind="image", filename="banner.png", content_type="image/png",
                   data=PNG, title="Launch banner")
    assert r.ok and r.asset is not None
    a = r.asset
    assert a.kind == MediaKind.IMAGE and a.size_bytes == len(PNG)
    assert a.storage_key.startswith("wa_media/t1/") and a.storage_key.endswith(".png")
    assert r.preview_url.startswith("https://cdn.test/")
    # round-trips through the store
    got = lib.get("t1", a.id)
    assert got is not None and got.title == "Launch banner"


def test_media_brochure_is_its_own_kind_and_requires_pdf(lib):
    ok = lib.upload("t1", kind="brochure", filename="b.pdf", content_type="application/pdf",
                    data=PDF, page_count=12)
    assert ok.ok and ok.asset.kind == MediaKind.BROCHURE and ok.asset.media_type == "document"
    # a non-PDF masquerading as PDF is rejected (magic-byte check)
    bad = lib.upload("t1", kind="brochure", filename="x.pdf", content_type="application/pdf",
                     data=b"not a pdf at all")
    assert not bad.ok and "PDF" in bad.error


def test_media_video_kind(lib):
    r = lib.upload("t1", kind="video", filename="reel.mp4", content_type="video/mp4",
                   data=MP4, duration_s=30)
    assert r.ok and r.asset.kind == MediaKind.VIDEO and r.asset.media_type == "video"


def test_media_validation_rejects_wrong_mime_and_oversize(lib):
    wrong = lib.upload("t1", kind="image", filename="a.pdf", content_type="application/pdf", data=PDF)
    assert not wrong.ok and "image/" in wrong.error
    big = lib.upload("t1", kind="image", filename="big.png", content_type="image/png",
                     data=b"\x89PNG" + b"\x00" * (6 * 1024 * 1024))
    assert not big.ok and "too large" in big.error
    empty = lib.upload("t1", kind="image", filename="e.png", content_type="image/png", data=b"")
    assert not empty.ok


def test_media_reuse_and_replace_keeps_id(lib):
    r = lib.upload("t1", kind="image", filename="v1.png", content_type="image/png", data=PNG, title="v1")
    aid = r.asset.id
    # replace IN PLACE — same id, references survive
    r2 = lib.upload("t1", kind="image", filename="v2.png", content_type="image/png",
                    data=PNG + b"x", title="v2", replace_id=aid)
    assert r2.ok and r2.asset.id == aid and r2.asset.title == "v2"
    assert lib.get("t1", aid).size_bytes == len(PNG) + 1
    # only ONE row (reuse, not duplicate)
    assert len(lib.list("t1")) == 1


def test_media_list_filter_by_kind_and_organize(lib):
    lib.upload("t1", kind="banner", filename="b.png", content_type="image/png", data=PNG)
    lib.upload("t1", kind="image", filename="i.png", content_type="image/png", data=PNG)
    br = lib.upload("t1", kind="brochure", filename="d.pdf", content_type="application/pdf", data=PDF)
    assert len(lib.list("t1")) == 3
    assert len(lib.list("t1", kind="brochure")) == 1
    # organize: rename + tag
    assert lib.rename("t1", br.asset.id, "Floor plan brochure")
    assert lib.retag("t1", br.asset.id, ["q3", "premium"])
    got = lib.get("t1", br.asset.id)
    assert got.title == "Floor plan brochure" and "premium" in got.tags


def test_media_archive_and_delete(lib):
    r = lib.upload("t1", kind="image", filename="i.png", content_type="image/png", data=PNG)
    aid = r.asset.id
    assert lib.archive("t1", aid)
    assert len(lib.list("t1")) == 0          # archived hidden by default
    assert lib.store.list("t1", include_archived=True)
    assert lib.delete("t1", aid)
    assert lib.get("t1", aid) is None


def test_media_usage_accounting(lib):
    lib.upload("t1", kind="image", filename="a.png", content_type="image/png", data=PNG)
    lib.upload("t1", kind="image", filename="b.png", content_type="image/png", data=PNG)
    u = lib.usage("t1")
    assert u["objects"] == 2 and u["bytes"] == 2 * len(PNG)


def test_media_dormant_storage_still_persists_metadata():
    # no storage injected and ObjectStorage import will yield a None client -> bytes
    # not stored, but metadata row MUST persist (panel shows 'preparing').
    lib = MediaLibrary(store=MediaStore(InMemoryMediaBackend()), storage=None)
    # force storage to resolve to None deterministically
    lib._storage = type("NS", (), {
        "tier": lambda self, n="primary": type("T", (), {"bucket": "b"})(),
        "_client": lambda self, t: None,
        "presign_get": lambda self, k, **kw: "",
        "delete": lambda self, k, **kw: False,
        "usage": lambda self, **kw: {"objects": 0, "bytes": 0},
    })()
    r = lib.upload("t1", kind="image", filename="a.png", content_type="image/png", data=PNG)
    assert r.ok and r.preview_url == "" and lib.get("t1", r.asset.id) is not None


def test_media_tenant_isolation(lib):
    a = lib.upload("t1", kind="image", filename="a.png", content_type="image/png", data=PNG)
    assert lib.get("t2", a.asset.id) is None      # cross-tenant read returns nothing
    assert lib.list("t2") == []
    assert not lib.delete("t2", a.asset.id)        # cross-tenant delete is a no-op
    assert lib.get("t1", a.asset.id) is not None   # owner still sees it


# =========================================================================== #
# AUDIENCE RESOLVER
# =========================================================================== #
# The W14 FactCall is keyed per-call (no lead_id column); the resolver derives a
# stable per-lead key from the MASKED PHONE. So in these fixtures the lead "id" the
# resolver returns IS the masked phone string. We use readable masked-phone labels.
L_HOT, L_WARM, L_COLD, L_DEAD, L_X = "L-hot", "L-warm", "L-cold", "L-dead", "L-x"


def _seed_reporting():
    rs = ReportingStore()
    rs.upsert(FactCall(tenant_id="t1", call_id="c-hot", ts_iso="2026-06-10T10:00:00Z",
                       lead_name="Hot Asha", lead_phone_masked=L_HOT,
                       lead_status=LeadStatus.HOT, campaign_id="camp-A", agent="riya"))
    rs.upsert(FactCall(tenant_id="t1", call_id="c-warm", ts_iso="2026-06-10T11:00:00Z",
                       lead_name="Warm Ben", lead_phone_masked=L_WARM,
                       lead_status=LeadStatus.WARM, campaign_id="camp-A", agent="arjun",
                       callback_scheduled=True))
    rs.upsert(FactCall(tenant_id="t1", call_id="c-cold", ts_iso="2026-06-10T12:00:00Z",
                       lead_name="Cold Cara", lead_phone_masked=L_COLD,
                       lead_status=LeadStatus.COLD, campaign_id="camp-B", agent="riya"))
    rs.upsert(FactCall(tenant_id="t1", call_id="c-dead", ts_iso="2026-06-10T13:00:00Z",
                       lead_name="Dead Dan", lead_phone_masked=L_DEAD,
                       lead_status=LeadStatus.DEAD, campaign_id="camp-B", agent="arjun"))
    # other-tenant noise (must never leak)
    rs.upsert(FactCall(tenant_id="t2", call_id="c-x", ts_iso="2026-06-10T13:00:00Z",
                       lead_phone_masked=L_X, lead_status=LeadStatus.HOT, campaign_id="camp-A"))
    return rs


def test_audience_temperature_sets():
    r = AudienceResolver(_seed_reporting())
    hot = r.resolve("t1", AudienceSpec(temps=("hot",)))
    assert hot.lead_ids == ("L-hot",)
    hw = r.resolve("t1", AudienceSpec(temps=("hot", "warm")))
    assert set(hw.lead_ids) == {"L-hot", "L-warm"}
    dead = r.resolve("t1", AudienceSpec(temps=("dead",)))
    assert dead.lead_ids == ("L-dead",)


def test_audience_campaign_and_agent_filters():
    r = AudienceResolver(_seed_reporting())
    campA = r.resolve("t1", AudienceSpec(campaign_id="camp-A"))
    assert set(campA.lead_ids) == {"L-hot", "L-warm"}
    riya = r.resolve("t1", AudienceSpec(agent="riya"))
    assert set(riya.lead_ids) == {"L-hot", "L-cold"}
    # AND across filters: campaign-B AND agent arjun -> only L-dead
    both = r.resolve("t1", AudienceSpec(campaign_id="camp-B", agent="arjun"))
    assert both.lead_ids == ("L-dead",)


def test_audience_follow_up_pending_and_requested_brochure():
    rs = _seed_reporting()

    def signals(tenant):
        return {"L-cold": {"requested_brochure"}} if tenant == "t1" else {}

    r = AudienceResolver(rs, signal_hook=signals)
    # follow_up_pending = callback_scheduled & not booked -> the warm lead
    fup = r.resolve("t1", AudienceSpec(follow_up_pending=True))
    assert fup.lead_ids == ("L-warm",)
    # requested_brochure comes from the signal hook -> the cold lead
    rb = r.resolve("t1", AudienceSpec(requested_brochure=True))
    assert rb.lead_ids == ("L-cold",)


def test_audience_named_segment_via_hook():
    rs = _seed_reporting()

    def signals(tenant):
        return {"L-hot": {"vip"}, "L-dead": {"vip"}}

    r = AudienceResolver(rs, signal_hook=signals)
    vip = r.resolve("t1", AudienceSpec(segment="vip"))
    assert set(vip.lead_ids) == {"L-hot", "L-dead"}


def test_audience_explicit_ids_union():
    r = AudienceResolver(_seed_reporting())
    res = r.resolve("t1", AudienceSpec(lead_ids=("L-hot", "L-cold")))
    assert set(res.lead_ids) == {"L-hot", "L-cold"}


def test_audience_empty_spec_is_fail_closed():
    r = AudienceResolver(_seed_reporting())
    assert r.resolve("t1", AudienceSpec()).count == 0      # NEVER 'send to all'
    # include_all is the only escape hatch
    assert r.resolve("t1", AudienceSpec(include_all=True)).count == 4


def test_audience_excludes_opted_out():
    r = AudienceResolver(_seed_reporting(), opted_out_hook=lambda t: {"L-warm"})
    hw = r.resolve("t1", AudienceSpec(temps=("hot", "warm")))
    assert hw.lead_ids == ("L-hot",)        # opted-out warm lead dropped


def test_audience_tenant_isolation():
    r = AudienceResolver(_seed_reporting())
    assert r.resolve("t2", AudienceSpec(include_all=True)).lead_ids == ("L-x",)
    assert r.resolve("", AudienceSpec(include_all=True)).count == 0    # fail-closed empty tenant


def test_audience_preview_breakdown():
    r = AudienceResolver(_seed_reporting())
    p = r.preview("t1", AudienceSpec(temps=("hot", "warm", "cold")))
    assert p["count"] == 3
    assert p["breakdown"]["hot"] == 1 and p["breakdown"]["warm"] == 1 and p["breakdown"]["cold"] == 1


# =========================================================================== #
# DELIVERY TRACKING
# =========================================================================== #
class FakeBus:
    def __init__(self):
        self.events = []

    async def emit(self, event):
        self.events.append(event)


def test_delivery_funnel_sent_delivered_read():
    bus = FakeBus()
    tr = DeliveryTracker(DeliveryStore(InMemoryDeliveryBackend()), event_bus=bus)
    tr.seed("t1", "m1", campaign_id="c", template="welcome", phone_masked="••••1", active=True)
    assert tr.on_status("t1", "m1", "delivered")
    assert tr.on_status("t1", "m1", "read")
    row = tr.store.get("t1", "m1")
    assert row.status == DeliveryStatus.READ and row.read_at > 0 and row.delivered_at > 0
    names = [e.name for e in bus.events]
    assert "whatsapp_delivered" in names and "whatsapp_read" in names


def test_delivery_is_forward_only():
    tr = DeliveryTracker(DeliveryStore(InMemoryDeliveryBackend()))
    tr.seed("t1", "m1", active=True)
    tr.on_status("t1", "m1", "read")
    # a LATE 'delivered' webhook must NOT regress a read
    assert not tr.on_status("t1", "m1", "delivered")
    assert tr.store.get("t1", "m1").status == DeliveryStatus.READ


def test_delivery_failed_and_opted_out():
    bus = FakeBus()
    tr = DeliveryTracker(DeliveryStore(InMemoryDeliveryBackend()), event_bus=bus)
    tr.seed("t1", "m1", active=True)
    assert tr.on_status("t1", "m1", "failed", reason="131047: re-engagement message")
    assert tr.store.get("t1", "m1").reason.startswith("131047")
    tr.seed("t1", "m2", active=True)
    assert tr.on_status("t1", "m2", "opted_out")
    names = [e.name for e in bus.events]
    assert "whatsapp_failed" in names and "whatsapp_opted_out" in names


def test_delivery_summary_counts():
    tr = DeliveryTracker(DeliveryStore(InMemoryDeliveryBackend()))
    for i in range(5):
        tr.seed("t1", f"m{i}", campaign_id="c", active=True)
    tr.on_status("t1", "m0", "delivered")
    tr.on_status("t1", "m1", "read")
    tr.on_status("t1", "m2", "read")
    tr.on_status("t1", "m3", "failed")
    s = tr.summary("t1", campaign_id="c")
    assert s["sent_total"] == 4          # 4 went out (m0..m2 + m4 still 'sent'); m3 failed
    assert s["read"] == 2 and s["failed"] == 1
    assert 0.0 < s["read_rate"] <= 1.0


def test_delivery_tenant_isolation():
    tr = DeliveryTracker(DeliveryStore(InMemoryDeliveryBackend()))
    tr.seed("t1", "m1", active=True)
    tr.seed("t2", "m1", active=True)
    assert tr.store.get("t2", "m1") is not None
    assert len(tr.list("t1")) == 1 and len(tr.list("t2")) == 1
    # a status on t2 must not touch t1's identically-named message
    tr.on_status("t2", "m1", "read")
    assert tr.store.get("t1", "m1").status == DeliveryStatus.SENT


# =========================================================================== #
# SEND ORCHESTRATOR — dormant-without-creds but WIRED
# =========================================================================== #
def _orch(active=False, sender=None, bus=None):
    rs = _seed_reporting()
    lib = MediaLibrary(store=MediaStore(InMemoryMediaBackend()), storage=FakeStorage())
    return lib, SendOrchestrator(
        media=lib,
        audience=AudienceResolver(rs),
        tracker=DeliveryTracker(DeliveryStore(InMemoryDeliveryBackend()), event_bus=bus),
        profile_hook=(lambda t: (active, "" if active else "no creds")),
        sender=sender, event_bus=bus)


def test_send_is_dormant_without_creds_but_records_plan():
    lib, orch = _orch(active=False)
    res = orch.send("t1", campaign_id="camp-A", template="welcome",
                    audience_spec=AudienceSpec(temps=("hot", "warm")))
    assert res.active is False
    assert res.queued == 2 and res.dispatched == 0 and res.skipped_no_config == 2
    assert "no creds" in res.reason
    # the rows EXIST so the panel shows what WOULD be sent
    rows = orch.tracker.list("t1", campaign_id="camp-A")
    assert len(rows) == 2 and all(r.status == DeliveryStatus.SKIPPED_NO_CONFIG for r in rows)


def test_send_dispatches_when_creds_active():
    sent = []

    def sender(plan, lead_id):
        mid = f"wamid.{lead_id}"
        sent.append((lead_id, mid))
        return mid

    bus = FakeBus()
    lib, orch = _orch(active=True, sender=sender, bus=bus)
    res = orch.send("t1", campaign_id="camp-A", template="welcome",
                    audience_spec=AudienceSpec(temps=("hot", "warm")))
    assert res.active is True and res.dispatched == 2 and res.skipped_no_config == 0
    assert set(res.message_ids) == {"wamid.L-hot", "wamid.L-warm"}
    rows = orch.tracker.list("t1", campaign_id="camp-A")
    assert all(r.status == DeliveryStatus.SENT for r in rows)
    assert "whatsapp_sent" in [e.name for e in bus.events]


def test_send_attaches_media_and_bumps_used_count():
    lib, orch = _orch(active=False)
    a = lib.upload("t1", kind="brochure", filename="b.pdf", content_type="application/pdf", data=PDF)
    res = orch.send("t1", campaign_id="camp-A", template="welcome", media_ids=[a.asset.id],
                    audience_spec=AudienceSpec(temps=("hot",)))
    assert res.queued == 1
    rows = orch.tracker.list("t1")
    assert rows[0].media_count == 1
    assert lib.get("t1", a.asset.id).used_count == 1     # 'used in N campaigns'


def test_send_drops_missing_media_ids():
    lib, orch = _orch(active=False)
    p = orch.plan("t1", template="welcome", media_ids=["does-not-exist"],
                  audience_spec=AudienceSpec(temps=("hot",)))
    assert p.media_ids == ()                  # phantom media silently dropped


def test_send_empty_audience_is_refused():
    lib, orch = _orch(active=True, sender=lambda p, l: "x")
    res = orch.send("t1", template="welcome", audience_spec=AudienceSpec())  # fail-closed
    assert res.queued == 0 and "empty audience" in res.reason


def test_send_tenant_isolation():
    lib, orch = _orch(active=False)
    res = orch.send("t1", campaign_id="c", template="x", audience_spec=AudienceSpec(include_all=True))
    assert res.queued == 4                    # only t1's 4 leads, never t2's
    assert orch.tracker.list("t2") == []
