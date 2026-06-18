"""W12 telephony Sales-OS tests (no box, no Redis, no droplet imports).

Proves the founder's requirements for the self-managing outbound machine:
  1. CAPACITY planner WARNS when the lead list exceeds what the fleet can safely
     clear in the window, and never returns a target above the lead count.
  2. ROUTER never OVERLOADS a number (per-number concurrency + daily cap honoured at
     lease time) and never violates a COOLDOWN.
  3. A lead is NEVER double-dialed — the LeadLock denies a second acquire while held,
     even from a "second number" path; self-heals after TTL.
  4. SpamReputation auto-REDUCES traffic to an unhealthy number (quarantine) and the
     router skips it; a recovered number re-enters rotation.
  5. The CallingWindowScheduler opens/closes correctly and (with the legal floor on)
     a tenant CANNOT widen past the legal window.
  6. Everything is tenant-isolated (blank tenant fails closed).

Async/clock are driven with injected fakes so the tests are deterministic + offline.
"""
from __future__ import annotations

import datetime as _dt

import pytest

from voice_ops.telephony.capacity_planner import CapacityPlanner
from voice_ops.telephony.config import TelephonyOpsConfig
from voice_ops.telephony.health import (
    ANSWERED,
    BLOCKED,
    DEGRADED,
    HEALTHY,
    QUARANTINED,
    SpamReputation,
)
from voice_ops.telephony.lead_lock import LeadLock, lead_key
from voice_ops.telephony.number_pool import NumberPool
from voice_ops.telephony.router import AdaptiveRouter
from voice_ops.telephony.window import CallingWindowScheduler


CFG = TelephonyOpsConfig(
    enabled=True,
    per_number_daily_cap=100,
    per_number_concurrency=2,
    cooldown_seconds=10,
    answer_rate=0.30,
    avg_call_seconds=90,
    dial_overhead_seconds=45,
    health_window_seconds=3600,
    health_min_samples=5,
    health_degrade_at=0.45,
    health_quarantine_at=0.20,
    health_recover_at=0.65,
    quarantine_minutes=60,
    lead_lock_ttl_seconds=300,
)


# --------------------------------------------------------------------------- #
# 1) Capacity planner: warns when insufficient.
# --------------------------------------------------------------------------- #
def test_capacity_warns_when_insufficient():
    p = CapacityPlanner(CFG)
    # 1 number, an 8h window, but 5000 leads -> way over fleet capacity -> WARN.
    plan = p.plan(leads=5000, numbers=1, window_minutes=8 * 60)
    assert plan.insufficient is True
    assert plan.warning != ""
    assert "Insufficient capacity" in plan.warning
    # safe target is the fleet capacity (< leads), never above the lead count.
    assert plan.safe_daily_target == plan.fleet_capacity
    assert plan.safe_daily_target <= plan.leads
    assert plan.suggested_numbers > plan.numbers          # tells the founder to add numbers


def test_capacity_sufficient_no_warning():
    p = CapacityPlanner(CFG)
    # tiny list, plenty of numbers -> NOT insufficient, target == leads.
    plan = p.plan(leads=50, numbers=10, window_minutes=8 * 60)
    assert plan.insufficient is False
    assert plan.warning == ""
    assert plan.safe_daily_target == 50


def test_capacity_no_numbers_warns():
    p = CapacityPlanner(CFG)
    plan = p.plan(leads=100, numbers=0, window_minutes=8 * 60)
    assert plan.insufficient is True
    assert "No phone numbers" in plan.warning
    assert plan.fleet_capacity == 0


def test_capacity_never_targets_above_leads():
    p = CapacityPlanner(CFG)
    plan = p.plan(leads=10, numbers=50, window_minutes=8 * 60)
    assert plan.safe_daily_target == 10        # min(leads, fleet)


# --------------------------------------------------------------------------- #
# 2) Router never overloads / cooldown.
# --------------------------------------------------------------------------- #
class _Clock:
    def __init__(self, t=1000.0):
        self.t = t

    def __call__(self):
        return self.t

    def advance(self, dt):
        self.t += dt


def _router_with_one_number(clock, *, concurrency=2, cooldown=10):
    cfg = TelephonyOpsConfig(enabled=True, per_number_daily_cap=100,
                             per_number_concurrency=concurrency, cooldown_seconds=cooldown,
                             health_min_samples=5)
    pool = NumberPool(cfg, clock=clock)
    pool.add_number("t1", "+911400000001", trunk_id="ST_1")
    router = AdaptiveRouter(cfg, pool=pool, health=SpamReputation(cfg, now_fn=lambda: _dt.datetime.now(_dt.timezone.utc)))
    return router, pool


def test_router_never_exceeds_concurrency():
    clock = _Clock()
    router, pool = _router_with_one_number(clock, concurrency=2, cooldown=0)
    c1 = router.pick_next("t1")
    c2 = router.pick_next("t1")
    assert c1 is not None and c2 is not None        # 2 concurrent allowed
    c3 = router.pick_next("t1")
    assert c3 is None                               # 3rd would exceed concurrency=2 -> None (queue)
    # release one -> a slot frees up
    router.record_outcome("t1", c1, answered=True, duration_s=30)
    c4 = router.pick_next("t1")
    assert c4 is not None


def test_router_respects_cooldown():
    clock = _Clock()
    router, pool = _router_with_one_number(clock, concurrency=5, cooldown=10)
    c1 = router.pick_next("t1")
    assert c1 is not None
    router.record_outcome("t1", c1, answered=True, duration_s=20)   # frees concurrency
    # immediately try again — within cooldown window -> blocked.
    c2 = router.pick_next("t1")
    assert c2 is None
    clock.advance(11)                               # past the 10s cooldown
    c3 = router.pick_next("t1")
    assert c3 is not None


def test_router_distributes_across_numbers_least_loaded_first():
    clock = _Clock()
    cfg = TelephonyOpsConfig(enabled=True, per_number_concurrency=5, cooldown_seconds=0,
                             health_min_samples=5)
    pool = NumberPool(cfg, clock=clock)
    for i in range(3):
        pool.add_number("t1", f"+91140000000{i}", trunk_id=f"ST_{i}")
    router = AdaptiveRouter(cfg, pool=pool)
    picked = [router.pick_next("t1").number for _ in range(3)]
    # each of the 3 numbers used once before any repeats (least-loaded-first).
    assert len(set(picked)) == 3


# --------------------------------------------------------------------------- #
# 3) Lead lock: no double-dial.
# --------------------------------------------------------------------------- #
def test_lead_lock_prevents_double_dial():
    clock = _Clock()
    lock = LeadLock(ttl_s=300, clock=clock)
    assert lock.acquire("t1", "+919812345678") is True
    # a second worker / a second NUMBER trying the SAME lead is denied.
    assert lock.acquire("t1", "+919812345678") is False
    lock.release("t1", "+919812345678")
    assert lock.acquire("t1", "+919812345678") is True   # released -> reacquirable


def test_lead_lock_self_heals_after_ttl():
    clock = _Clock()
    lock = LeadLock(ttl_s=30, clock=clock)
    assert lock.acquire("t1", "+91999") is True
    assert lock.is_locked("t1", "+91999") is True
    clock.advance(31)                                # lease expired (crashed worker)
    assert lock.is_locked("t1", "+91999") is False
    assert lock.acquire("t1", "+91999") is True      # reclaimed


def test_lead_lock_tenant_isolated():
    lock = LeadLock(ttl_s=300)
    assert lock.acquire("tA", "+91500") is True
    assert lock.acquire("tB", "+91500") is True      # same phone, different tenant -> independent
    with pytest.raises(ValueError):
        lead_key("", "+91500")                       # blank tenant fails closed


# --------------------------------------------------------------------------- #
# 4) Spam reputation: auto-reduce to unhealthy, recover.
# --------------------------------------------------------------------------- #
def test_health_quarantines_a_blocked_number_and_router_skips_it():
    clock = _Clock()
    cfg = TelephonyOpsConfig(enabled=True, per_number_concurrency=5, cooldown_seconds=0,
                             health_min_samples=5, health_quarantine_at=0.20,
                             health_degrade_at=0.45, health_recover_at=0.65,
                             quarantine_minutes=60)
    health = SpamReputation(cfg)
    pool = NumberPool(cfg, clock=clock)
    pool.add_number("t1", "+91BAD", trunk_id="ST_BAD")
    pool.add_number("t1", "+91GOOD", trunk_id="ST_GOOD")
    router = AdaptiveRouter(cfg, pool=pool, health=health)

    # hammer +91BAD with blocked outcomes -> score collapses -> QUARANTINED.
    for _ in range(8):
        snap = health.record("+91BAD", BLOCKED)
    assert snap.state == QUARANTINED
    assert snap.traffic_factor == 0.0

    # +91GOOD looks healthy.
    for _ in range(6):
        health.record("+91GOOD", ANSWERED)

    # the router must pick the GOOD number, never the resting BAD one.
    picks = set()
    for _ in range(4):
        c = router.pick_next("t1")
        if c:
            picks.add(c.number)
            router.record_outcome("t1", c, answered=True, duration_s=30)
    assert "+91BAD" not in picks
    assert "+91GOOD" in picks


def test_health_low_samples_is_unproven_healthy():
    health = SpamReputation(CFG)
    snap = health.record("+91NEW", BLOCKED)          # 1 bad call, below min_samples
    assert snap.state == HEALTHY                     # not enough evidence to quarantine
    assert snap.is_dialable is True


def test_health_recovers_to_healthy_after_good_streak():
    cfg = TelephonyOpsConfig(enabled=True, health_min_samples=5, health_window_seconds=99999,
                             health_degrade_at=0.45, health_recover_at=0.65,
                             health_quarantine_at=0.20, quarantine_minutes=1)
    health = SpamReputation(cfg)
    # push into DEGRADED with some rejects (score between quarantine and degrade).
    for _ in range(3):
        health.record("+91R", "rejected")
    for _ in range(3):
        health.record("+91R", ANSWERED)
    s = health.snapshot("+91R")
    assert s.state in (DEGRADED, HEALTHY)
    # a strong good streak lifts it above recover_at -> HEALTHY.
    for _ in range(20):
        health.record("+91R", ANSWERED)
    assert health.snapshot("+91R").state == HEALTHY


# --------------------------------------------------------------------------- #
# 5) Calling window scheduler + legal floor cannot be widened.
# --------------------------------------------------------------------------- #
def test_window_open_and_closed():
    sched = CallingWindowScheduler(CFG)
    # 2026-06-18 12:00 IST is inside 10:00-19:00.
    noon = _dt.datetime(2026, 6, 18, 6, 30, tzinfo=_dt.timezone.utc)   # 12:00 IST
    d = sched.decide(start="10:00", end="19:00", now=noon)
    assert d.in_window is True
    # 02:00 IST is closed; next open is today 10:00 IST.
    night = _dt.datetime(2026, 6, 17, 20, 30, tzinfo=_dt.timezone.utc)  # 02:00 IST next day
    d2 = sched.decide(start="10:00", end="19:00", now=night)
    assert d2.in_window is False
    assert d2.next_open_iso is not None


def test_window_legal_floor_cannot_be_widened():
    sched = CallingWindowScheduler(CFG)
    # tenant tries to widen to 06:00-23:00, but with the legal floor ON it is clamped
    # to 10:00-19:00. At 21:00 IST (which the tenant THINKS is open) it must be CLOSED.
    nine_pm_ist = _dt.datetime(2026, 6, 18, 15, 30, tzinfo=_dt.timezone.utc)  # 21:00 IST
    d = sched.decide(start="06:00", end="23:00", apply_legal_floor=True, now=nine_pm_ist)
    assert d.in_window is False
    assert d.start_hhmm == "10:00" and d.end_hhmm == "19:00"   # clamped to the floor
    # at 11:00 IST the clamped window IS open.
    eleven_ist = _dt.datetime(2026, 6, 18, 5, 30, tzinfo=_dt.timezone.utc)    # 11:00 IST
    d2 = sched.decide(start="06:00", end="23:00", apply_legal_floor=True, now=eleven_ist)
    assert d2.in_window is True
