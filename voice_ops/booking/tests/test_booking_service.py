"""Tests for voice_ops.booking — book_site_visit persists + emits W8 event + lifecycle +
tenant isolation, driven by a dict-backed FAKE engine (no Postgres, no droplet_work, no SDK).

Also covers the warm-transfer planner: exactly ONE short ack line + the correct dial/exit step
sequence, and the transfer state log (requested/started/completed/failed) emitting W8 events.
"""
from __future__ import annotations

import asyncio
import datetime as _dt

import pytest

from voice_ops.booking import (
    BookingOpsConfig,
    BookingService,
    detect_transfer_intent,
    plan_transfer,
    store,
)
from voice_ops.booking.transfer import TransferLog, TransferState
from voice_kernel.events import InMemoryEventBus


# --------------------------------------------------------------------------- #
# A minimal dict-backed fake of droplet_work/booking/core.py's surface. Enforces
# the anti-double-book + tenant scoping so the service tests are realistic.
# --------------------------------------------------------------------------- #
class FakeEngine:
    def __init__(self):
        self.rows: dict = {}          # bk_id -> booking dict
        self.events: list = []        # immutable audit
        self._seq = 0

    def _nid(self, p):
        self._seq += 1
        return f"{p}{self._seq:06d}"

    def book(self, org_id, resource_id, phone, *, slot_start, slot_end=None, name="", title="",
             notes="", source="", campaign_id="", is_admin=False):
        # anti-double-book: one active booking per (org, resource, slot_start)
        for b in self.rows.values():
            if (b["org_id"] == org_id and b["resource_id"] == resource_id
                    and b["slot_start"] == slot_start and b["status"] in ("booked", "rescheduled")):
                return {"ok": False, "status": "conflict", "reason": "slot_taken"}
        bk = self._nid("bk_")
        booking = {"id": bk, "org_id": org_id, "resource_id": resource_id, "phone_display": phone,
                   "name": name, "status": "booked", "slot_start": slot_start, "slot_end": slot_end,
                   "title": title, "notes": notes, "source": source, "campaign_id": campaign_id,
                   "calendar_event_id": ""}
        self.rows[bk] = booking
        self.events.append({"booking_id": bk, "org_id": org_id, "event_type": "booked"})
        return {"ok": True, "status": "ok", "booking": dict(booking)}

    def reschedule(self, org_id, booking_id, *, new_slot_start, new_slot_end=None, is_admin=False):
        old = self.rows.get(booking_id)
        if old is None or old["org_id"] != org_id:
            return {"ok": False, "status": "error", "reason": "booking_not_found"}
        for b in self.rows.values():
            if (b["org_id"] == org_id and b["resource_id"] == old["resource_id"]
                    and b["slot_start"] == new_slot_start and b["status"] in ("booked", "rescheduled")):
                return {"ok": False, "status": "conflict", "reason": "new_slot_taken"}
        old["status"] = "cancelled"
        nid = self._nid("bk_")
        nb = dict(old); nb.update({"id": nid, "status": "rescheduled", "slot_start": new_slot_start,
                                   "slot_end": new_slot_end, "reschedule_of": booking_id})
        self.rows[nid] = nb
        self.events.append({"booking_id": nid, "org_id": org_id, "event_type": "rescheduled"})
        return {"ok": True, "status": "ok", "booking": dict(nb)}

    def cancel(self, org_id, booking_id, *, reason="", is_admin=False):
        b = self.rows.get(booking_id)
        if b is None or b["org_id"] != org_id or b["status"] not in ("booked", "rescheduled"):
            return {"ok": True, "status": "noop", "reason": "already_inactive_or_missing"}
        b["status"] = "cancelled"
        self.events.append({"booking_id": booking_id, "org_id": org_id, "event_type": "cancelled"})
        return {"ok": True, "status": "ok", "booking_id": booking_id, "new_status": "cancelled"}

    def mark_completed(self, org_id, booking_id, *, is_admin=False):
        b = self.rows.get(booking_id)
        if b is None or b["org_id"] != org_id or b["status"] not in ("booked", "rescheduled"):
            return {"ok": False, "status": "noop", "booking_id": booking_id}
        b["status"] = "completed"
        self.events.append({"booking_id": booking_id, "org_id": org_id, "event_type": "completed"})
        return {"ok": True, "status": "ok", "booking_id": booking_id}

    def get_booking(self, org_id, booking_id, *, is_admin=False):
        b = self.rows.get(booking_id)
        if b is None or b["org_id"] != org_id:  # TENANT ISOLATION: org A can't read org B's row
            return {"status": "error", "reason": "booking_not_found"}
        return {"status": "ok", "booking": dict(b)}

    def list_bookings(self, org_id, *, contact_id="", status="", limit=100, is_admin=False):
        out = [dict(b) for b in self.rows.values()
               if b["org_id"] == org_id and (not status or b["status"] == status)]
        return {"status": "ok", "bookings": out, "count": len(out)}

    def list_events(self, org_id, booking_id, *, limit=200, is_admin=False):
        out = [e for e in self.events if e["org_id"] == org_id and e["booking_id"] == booking_id]
        return {"status": "ok", "events": out, "count": len(out)}


@pytest.fixture
def fake_engine():
    eng = FakeEngine()
    store.set_engine_for_tests(eng)
    yield eng
    store.set_engine_for_tests(None)


@pytest.fixture
def cfg():
    return BookingOpsConfig(enabled=True, default_resource_id="site_visit", default_tz="Asia/Kolkata")


def _collect(bus: InMemoryEventBus, tenant: str):
    """All events emitted for a tenant (the bus's own test helper, no blocking)."""
    return bus.all_events(tenant)


# =========================================================================== #
# book_site_visit
# =========================================================================== #
def test_book_site_visit_persists_and_emits(fake_engine, cfg):
    bus = InMemoryEventBus()
    svc = BookingService(cfg, event_bus=bus)
    res = asyncio.run(svc.book_site_visit(
        org_id="orgA", call_id="call1", phone="+919876543210",
        when="kal subah 10 baje", name="Ramesh", campaign_id="camp7", notes="3BHK interested",
    ))
    assert res["ok"] is True
    assert res["status"] == "booked"
    assert res["say"]  # exactly one spoken line present
    # persisted in the engine
    assert len(fake_engine.rows) == 1
    booking = next(iter(fake_engine.rows.values()))
    assert booking["org_id"] == "orgA"
    assert booking["campaign_id"] == "camp7"
    assert booking["source"] == "voice"
    # W8 site_visit_booked emitted on orgA's stream
    evs = _collect(bus, "orgA")
    assert any(e.name == "site_visit_booked" for e in evs)
    booked = [e for e in evs if e.name == "site_visit_booked"][0]
    assert booked.tenant_id == "orgA"
    assert booked.payload.get("booking_id") == booking["id"]


def test_book_site_visit_slot_taken_reasks(fake_engine, cfg):
    svc = BookingService(cfg, event_bus=InMemoryEventBus())
    first = asyncio.run(svc.book_site_visit(org_id="orgA", call_id="c1", phone="+91999",
                                            when="2026-06-20T10:00:00+00:00"))
    assert first["ok"] is True
    second = asyncio.run(svc.book_site_visit(org_id="orgA", call_id="c2", phone="+91888",
                                             when="2026-06-20T10:00:00+00:00"))
    assert second["ok"] is False
    assert second["status"] == "slot_taken"
    assert "time" in second["say"].lower() or "koi aur" in second["say"].lower()


def test_book_site_visit_unresolved_time_reasks(fake_engine, cfg):
    svc = BookingService(cfg, event_bus=None)
    res = asyncio.run(svc.book_site_visit(org_id="orgA", call_id="c1", phone="+91999",
                                          when="something vague with no time"))
    assert res["ok"] is False
    assert res["status"] == "unresolved_time"
    assert res["say"]


def test_book_site_visit_disabled_is_graceful():
    store.set_engine_for_tests(FakeEngine())
    try:
        svc = BookingService(BookingOpsConfig(enabled=False), event_bus=None)
        res = asyncio.run(svc.book_site_visit(org_id="orgA", call_id="c", phone="+91",
                                              when="kal 10 baje"))
        assert res["ok"] is False
        assert res["status"] == "disabled"
        assert res["say"]
    finally:
        store.set_engine_for_tests(None)


def test_book_site_visit_dormant_engine_graceful(cfg):
    # No engine injected AND force the lazy loader off -> not_configured, never raises.
    store.set_engine_for_tests(None)
    store.reset_engine_cache()
    # monkeypatch the loader to return None (simulate CI without the gitignored core)
    import voice_ops.booking.store as st
    orig = st._load_core
    st._load_core = lambda: None
    try:
        svc = BookingService(cfg, event_bus=None)
        res = asyncio.run(svc.book_site_visit(org_id="orgA", call_id="c", phone="+91",
                                              when="kal 10 baje"))
        assert res["ok"] is False
        assert res["status"] == "not_configured"
        assert res["say"]
    finally:
        st._load_core = orig
        st.reset_engine_cache()


# =========================================================================== #
# lifecycle transitions (manual + AI-driven)
# =========================================================================== #
def test_lifecycle_complete_cancel_reschedule(fake_engine, cfg):
    bus = InMemoryEventBus()
    svc = BookingService(cfg, event_bus=bus)
    booked = asyncio.run(svc.book_site_visit(org_id="orgA", call_id="c1", phone="+91999",
                                             when="2026-06-25T09:00:00+00:00"))
    bk = booked["booking"]["id"]

    # reschedule -> new active row, old cancelled
    resc = asyncio.run(svc.reschedule(org_id="orgA", booking_id=bk,
                                      when="2026-06-26T11:00:00+00:00"))
    assert resc["ok"] is True
    new_bk = resc["booking"]["id"]
    assert fake_engine.rows[bk]["status"] == "cancelled"
    assert fake_engine.rows[new_bk]["status"] == "rescheduled"

    # complete the rescheduled one
    done = asyncio.run(svc.complete(org_id="orgA", booking_id=new_bk))
    assert done["ok"] is True
    assert fake_engine.rows[new_bk]["status"] == "completed"


def test_lifecycle_cancel(fake_engine, cfg):
    svc = BookingService(cfg, event_bus=InMemoryEventBus())
    booked = asyncio.run(svc.book_site_visit(org_id="orgA", call_id="c1", phone="+91999",
                                             when="2026-07-01T09:00:00+00:00"))
    bk = booked["booking"]["id"]
    res = asyncio.run(svc.cancel(org_id="orgA", booking_id=bk, reason="changed mind"))
    assert res["ok"] is True and res["status"] == "ok"
    assert fake_engine.rows[bk]["status"] == "cancelled"


# =========================================================================== #
# tenant isolation
# =========================================================================== #
def test_tenant_isolation(fake_engine, cfg):
    svc = BookingService(cfg, event_bus=InMemoryEventBus())
    booked = asyncio.run(svc.book_site_visit(org_id="orgA", call_id="c1", phone="+91999",
                                             when="2026-08-01T09:00:00+00:00"))
    bk = booked["booking"]["id"]
    # orgB must NOT see or mutate orgA's booking
    assert svc.get(org_id="orgB", booking_id=bk)["status"] == "error"
    assert svc.list(org_id="orgB")["count"] == 0
    assert svc.list(org_id="orgA")["count"] == 1
    # empty org_id fails closed
    assert store.book("", "site_visit", "+91", slot_start="2026-08-01T09:00:00+00:00")["reason"] == "empty_org_id"


# =========================================================================== #
# warm transfer planner + state log
# =========================================================================== #
def test_transfer_plan_one_line_and_sequence():
    p = plan_transfer(handoff_numbers=["+919876543210", "+919812345678"], dial_who="team")
    # exactly ONE ack line, no phone numbers spoken in it
    assert p.ack_line == "Theek hai sar, main aapko team se connect kar raha hoon."
    assert "9876543210" not in p.ack_line and "+91" not in p.ack_line
    # one short fallback line
    assert p.fallback_line and len(p.fallback_line.split(".")) <= 2
    # correct dial/exit choreography in order
    assert p.steps == ("log_requested", "speak_ack", "start_hold_music", "log_started",
                       "dial_into_same_room", "on_answer_stop_music", "log_completed",
                       "ai_exit_session_shutdown")
    assert p.same_room is True
    assert p.ai_exit_after_bridge is True
    assert p.delete_room_on_close is False  # room stays alive for caller+human
    assert p.play_hold_music is True
    assert p.dial_numbers == ("+919876543210", "+919812345678")


def test_transfer_plan_no_target_still_one_line():
    p = plan_transfer(handoff_numbers=[], dial_who="team")
    assert not p.has_target
    assert p.play_hold_music is False
    assert p.ack_line  # still exactly one short line
    assert "speak_ack" in p.steps and "close" in p.steps


def test_transfer_plan_handles_dict_handoff_list():
    p = plan_transfer(handoff_numbers=[{"phone": "+919876543210"}, {"number": "+919812345678"}],
                      dial_who="manager")
    assert p.dial_numbers == ("+919876543210", "+919812345678")
    assert "manager" in p.ack_line


def test_transfer_log_lifecycle_emits_events():
    bus = InMemoryEventBus()
    tlog = TransferLog(call_id="callX", tenant_id="orgA", reason="wants_human", event_bus=bus)
    assert tlog.state == TransferState.REQUESTED
    asyncio.run(tlog.requested())
    asyncio.run(tlog.started("+919876543210"))
    assert tlog.state == TransferState.STARTED
    asyncio.run(tlog.connecting())
    assert tlog.state == TransferState.CONNECTING
    asyncio.run(tlog.completed(agent="+919876543210"))
    assert tlog.state == TransferState.COMPLETED
    # history records each transition with timestamps
    states = [h["state"] for h in tlog.history]
    assert states == ["requested", "started", "connecting", "completed"]
    evs = _collect(bus, "orgA")
    assert any(e.name == "handoff_requested" for e in evs)
    assert any(e.name == "handoff_done" for e in evs)


def test_transfer_log_failed_path_emits_done():
    bus = InMemoryEventBus()
    tlog = TransferLog(call_id="callY", tenant_id="orgB", reason="wants_human", event_bus=bus)
    asyncio.run(tlog.requested())
    asyncio.run(tlog.started("+91999"))
    asyncio.run(tlog.failed(reason="no_human_answered"))
    assert tlog.state == TransferState.FAILED
    evs = _collect(bus, "orgB")
    done = [e for e in evs if e.name == "handoff_done"]
    assert done and done[0].payload.get("outcome") == "failed"


def test_detect_transfer_intent():
    assert detect_transfer_intent("mujhe team se baat karni hai")
    assert detect_transfer_intent("I want to buy this property now")
    assert detect_transfer_intent("can I talk to a human")
    assert detect_transfer_intent("connect me to the manager")
    assert not detect_transfer_intent("what is the price")
    assert not detect_transfer_intent("tell me about the location")
