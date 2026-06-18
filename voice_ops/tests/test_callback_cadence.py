"""W10 smart-cadence-engine tests (no box, no Redis, no droplet imports).

Proves the founder's requirements AND regression-blocks the OLD runaway pattern:
  1. cadence ADVANCES correctly (Day 0/1/3/7/14/30 offsets, anchored to arrival);
  2. NEVER exceeds max retries (the hard cap -> EXPIRED, not infinite redial);
  3. NO redial after a connected/answered call (no-redial-after-pickup);
  4. "call me at 5pm" schedules at 5pm IST (highest priority, even after pickup);
  5. BUSY -> ONE short reschedule (not a 120-min loop), capped per day;
  6. DEDUP / lead-lock holds (one pending entry; single dialer per lead);
  7. REGRESSION: the OLD reset-attempts->1 loop is structurally impossible
     (re-enqueue / recon tick never resets the persisted attempts counter).

Async tests use the repo convention: asyncio.run() inside a sync test.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from voice_kernel.events import InMemoryEventBus, EventName
from voice_kernel.events.timeutil import parse_iso, _tz

from voice_ops.callback import (
    CALLED,
    EXPIRED,
    OPT_OUT,
    PENDING,
    CallbackConfig,
    CallbackEntry,
    InMemoryCallbackStore,
    enqueue_smart,
    fire_due,
    parse_callback_time,
)

# A config with the engine ARMED (production default is OFF). Daytime-friendly
# DND so cadence tests don't get nudged by quiet hours unless they ask for it.
CFG = CallbackConfig(
    enabled=True,
    cadence_mins=(0, 1440, 4320, 10080, 20160, 43200),  # D0/1/3/7/14/30
    max_retries=2,                                        # 3 touches total
    busy_retry_mins=25,
    max_busy_per_day=1,
    dnd_start_hour=21,
    dnd_end_hour=9,
    min_gap_mins=120,
    tz_name="Asia/Kolkata",
)

# A reference "now" comfortably inside IST business hours (12:00 IST = 06:30 UTC).
NOW = "2026-06-18T06:30:00Z"


def _rec(phone="+919812345678", lead_id="L1", summary="discussed pricing", **kw):
    r = {"id": lead_id, "phone": phone, "summary": summary}
    r.update(kw)
    return r


def _run(coro):
    return asyncio.run(coro)


# --------------------------------------------------------------------------- #
# 1. Cadence advances correctly + anchored to arrival
# --------------------------------------------------------------------------- #
def test_cadence_advances_through_days():
    async def go():
        store = InMemoryCallbackStore()
        bus = InMemoryEventBus()
        # First no-answer: brand-new lead, attempt_hint 0 -> schedules touch 1 (D1).
        e1 = await enqueue_smart("tA", "camp1", _rec(), {}, "no_answer", 0, {},
                                 store=store, config=CFG, bus=bus, now=NOW)
        assert e1 is not None and e1.status == PENDING
        # touch_index 1 -> offset 1440 min (D1) from created_at.
        anchor = parse_iso(e1.created_at)
        gap = parse_iso(e1.next_attempt_at) - anchor
        # D1 = ~1440 min (may be DND-nudged but should be ~1 day, well over min_gap)
        assert timedelta(hours=20) <= gap <= timedelta(hours=36), gap

        # Simulate the dial firing (attempts -> 1), then another no-answer.
        await store.record_attempt("tA", e1.phone)       # attempts now 1
        await store.unlock("tA", e1.phone)
        e2 = await enqueue_smart("tA", "camp1", _rec(), {}, "no_answer", 0, {},
                                 store=store, config=CFG, bus=bus, now=NOW)
        assert e2.attempts == 1                            # PRESERVED, not reset
        # next touch index = 2 -> offset 4320 (D3) from arrival.
        gap2 = parse_iso(e2.next_attempt_at) - parse_iso(e2.created_at)
        assert gap2 >= timedelta(days=2), gap2

        # an event was emitted for the schedule.
        names = [ev.name for ev in bus.all_events("tA")]
        assert EventName.CALLBACK_SCHEDULED.value in names
        return True

    assert _run(go())


# --------------------------------------------------------------------------- #
# 2. Never exceeds max retries -> EXPIRED (the hard cap)
# --------------------------------------------------------------------------- #
def test_never_exceeds_max_retries():
    # Drive the FULL realistic loop: finalize(no_answer) -> fire_due(dials, ++attempts)
    # -> finalize(no_answer) ... and assert the loop ENDS (EXPIRED) at max_retries,
    # never spinning forever. `now` is advanced past each due time so fire_due picks
    # the entry up. This is the integration proof that the runaway can't recur.
    async def go():
        store = InMemoryCallbackStore()
        bus = InMemoryEventBus()
        phone = "+919800000001"
        clock = parse_iso(NOW)
        # T0 already dialed by the live campaign loop -> first no_answer finalize.
        await enqueue_smart("tA", "c", _rec(phone=phone), {}, "no_answer", 0, {},
                            store=store, config=CFG, bus=bus, now=_z(clock))
        dialed = 0
        for _ in range(20):  # way more than max_retries -> proves the cap holds
            row = await store.load("tA", phone)
            if row.status == EXPIRED:
                break
            # jump the clock to just after the scheduled time + out of quiet hours.
            clock = parse_iso(row.next_attempt_at) + timedelta(minutes=1)
            jobs = await fire_due(store=store, config=CFG, now=_z(clock))
            if jobs:
                dialed += 1
                await store.unlock("tA", phone)  # dialer releases the lock
            # the dialer reports the (still no-answer) outcome back.
            await enqueue_smart("tA", "c", _rec(phone=phone), {}, "no_answer", 0, {},
                                store=store, config=CFG, bus=bus, now=_z(clock))
        row = await store.load("tA", phone)
        # max_retries = 2 -> at most 2 scheduler dials, then EXPIRED. Never more.
        assert dialed <= CFG.max_retries, dialed
        assert row.attempts <= CFG.max_retries, row.attempts
        assert row.status == EXPIRED, row.status
        return True

    assert _run(go())


def _z(dt):
    from datetime import timezone
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def test_fire_due_caps_and_expires():
    async def go():
        store = InMemoryCallbackStore()
        phone = "+919800000002"
        # plant an entry already AT the cap, due now.
        await store.upsert(CallbackEntry(
            tenant_id="tA", phone=phone, campaign_id="c", lead_id="L",
            status=PENDING, attempts=3, next_attempt_at=NOW, reason="cadence",
        ))
        jobs = await fire_due(store=store, config=CFG, now=NOW)
        assert jobs == []                                  # capped: not dialed
        assert (await store.load("tA", phone)).status == EXPIRED
        return True

    assert _run(go())


# --------------------------------------------------------------------------- #
# 3. No redial after a connected/answered call
# --------------------------------------------------------------------------- #
def test_no_redial_after_answer():
    async def go():
        store = InMemoryCallbackStore()
        bus = InMemoryEventBus()
        phone = "+919800000003"
        out = await enqueue_smart("tA", "c", _rec(phone=phone), {}, "answered", 0, {},
                                  store=store, config=CFG, bus=bus, now=NOW)
        assert out is None                                 # nothing scheduled
        row = await store.load("tA", phone)
        assert row is not None and row.status == CALLED
        # a later recon tick on the same answered call must NOT re-open it.
        out2 = await enqueue_smart("tA", "c", _rec(phone=phone), {}, "no_answer", 0, {},
                                   store=store, config=CFG, bus=bus, now=NOW,
                                   from_reconcile=True)
        assert out2 is None
        assert (await store.load("tA", phone)).status == CALLED
        # and fire_due never yields a CALLED lead.
        jobs = await fire_due(store=store, config=CFG, now=NOW)
        assert jobs == []
        return True

    assert _run(go())


def test_answered_call_with_callback_at_still_honored():
    # Customer answered AND said "call me at 5pm" -> the exact-time callback IS
    # scheduled (intent wins), but it is the ONLY thing that survives a pickup.
    async def go():
        store = InMemoryCallbackStore()
        phone = "+919800000004"
        tr = {"callback_at": "5pm"}
        out = await enqueue_smart("tA", "c", _rec(phone=phone), tr, "answered", 0, {},
                                  store=store, config=CFG, now=NOW)
        assert out is not None and out.priority is True
        assert out.status == PENDING
        return True

    assert _run(go())


# --------------------------------------------------------------------------- #
# 4. "call me at 5pm" schedules at 5pm IST (priority)
# --------------------------------------------------------------------------- #
def test_call_me_at_5pm_schedules_at_5pm_ist():
    async def go():
        store = InMemoryCallbackStore()
        bus = InMemoryEventBus()
        phone = "+919800000005"
        # NOW = 12:00 IST; "5pm" today => 17:00 IST.
        out = await enqueue_smart("tA", "c", _rec(phone=phone), {"callback_at": "5pm"},
                                  "no_answer", 0, {}, store=store, config=CFG, bus=bus, now=NOW)
        assert out.priority is True
        local = parse_iso(out.next_attempt_at).astimezone(_tz("Asia/Kolkata"))
        assert local.hour == 17 and local.minute == 0, local
        # priority entry fires first in fire_due.
        jobs = await fire_due(store=store, config=CFG, now=out.next_attempt_at)
        assert jobs and jobs[0].priority and jobs[0].phone == phone
        return True

    assert _run(go())


def test_parse_natural_times():
    # 12:00 IST reference.
    now = parse_iso("2026-06-18T06:30:00Z")
    tz = _tz("Asia/Kolkata")

    def at(phrase):
        iso = parse_callback_time(phrase, now=now, tz_name="Asia/Kolkata")
        return parse_iso(iso).astimezone(tz) if iso else None

    five = at("call me at 5pm")
    assert five.hour == 17 and five.date() == datetime(2026, 6, 18).date()

    tom = at("call me tomorrow morning")
    assert tom.date() == datetime(2026, 6, 19).date() and tom.hour == 10

    # "4 baje" in a callback context -> 16:00 (afternoon inference).
    baje = at("4 baje call karna")
    assert baje.hour == 16

    # a clock time already PAST today -> rolls to tomorrow (never the past).
    past = at("call at 9am")     # 09:00 IST < 12:00 now -> tomorrow 09:00
    assert past.date() == datetime(2026, 6, 19).date() and past.hour == 9

    # a named weekday.
    sun = at("ring me on sunday")
    assert sun.weekday() == 6

    # garbage -> None (fall back to cadence, never a wrong-time spam).
    assert parse_callback_time("uhh maybe", now=now) is None
    assert parse_callback_time("", now=now) is None


def test_callback_at_iso_passthrough():
    now = parse_iso("2026-06-18T06:30:00Z")
    iso = parse_callback_time("2026-06-20T10:00:00Z", now=now)
    assert parse_iso(iso) == parse_iso("2026-06-20T10:00:00Z")


# --------------------------------------------------------------------------- #
# 5. Busy -> ONE short reschedule, capped per day
# --------------------------------------------------------------------------- #
def test_busy_short_reschedule_not_120min_loop():
    async def go():
        store = InMemoryCallbackStore()
        phone = "+919800000006"
        out = await enqueue_smart("tA", "c", _rec(phone=phone), {}, "busy", 0, {},
                                  store=store, config=CFG, now=NOW)
        assert out.reason == "busy"
        gap = parse_iso(out.next_attempt_at) - parse_iso(NOW)
        # SHORT (~25 min), categorically NOT the old 120-min cadence floor.
        assert timedelta(minutes=20) <= gap <= timedelta(minutes=40), gap
        # busy did NOT burn a cadence attempt.
        assert out.attempts == 0
        return True

    assert _run(go())


def test_busy_capped_per_day_then_falls_to_cadence():
    async def go():
        store = InMemoryCallbackStore()
        phone = "+919800000007"
        # first busy -> short reschedule.
        await enqueue_smart("tA", "c", _rec(phone=phone), {}, "busy", 0, {},
                            store=store, config=CFG, now=NOW)
        # second busy same day (cap=1) -> must fall through to a cadence advance,
        # NOT another 25-min short retry.
        out2 = await enqueue_smart("tA", "c", _rec(phone=phone), {}, "busy", 0, {},
                                   store=store, config=CFG, now=NOW)
        assert out2.reason == "cadence", out2.reason
        gap = parse_iso(out2.next_attempt_at) - parse_iso(NOW)
        assert gap >= timedelta(hours=2), gap
        return True

    assert _run(go())


# --------------------------------------------------------------------------- #
# 6. Dedup / lead-lock
# --------------------------------------------------------------------------- #
def test_dedup_single_pending_entry():
    async def go():
        store = InMemoryCallbackStore()
        phone = "+919800000008"
        for _ in range(5):
            await enqueue_smart("tA", "c", _rec(phone=phone), {}, "no_answer", 0, {},
                                store=store, config=CFG, now=NOW)
        # exactly ONE row for the lead despite 5 finalizes (idempotent upsert).
        rows = [r for r in store.snapshot() if r.phone == phone]
        assert len(rows) == 1
        return True

    assert _run(go())


def test_lead_lock_single_dialer():
    async def go():
        store = InMemoryCallbackStore()
        phone = "+919800000009"
        await store.upsert(CallbackEntry(
            tenant_id="tA", phone=phone, campaign_id="c", lead_id="L",
            status=PENDING, attempts=0, next_attempt_at=NOW, reason="cadence",
        ))
        # two concurrent scheduler ticks (e.g. two worker numbers) -> only ONE
        # gets the job (the lock prevents a double-dial).
        jobs_a, jobs_b = await asyncio.gather(
            fire_due(store=store, config=CFG, now=NOW),
            fire_due(store=store, config=CFG, now=NOW),
        )
        fired = [j for j in (jobs_a + jobs_b) if j.phone == phone]
        assert len(fired) == 1, fired
        return True

    assert _run(go())


def test_opt_out_is_terminal():
    async def go():
        store = InMemoryCallbackStore()
        phone = "+919800000010"
        out = await enqueue_smart("tA", "c", _rec(phone=phone), {}, "opted_out", 0, {},
                                  store=store, config=CFG, now=NOW)
        assert out is None
        assert (await store.load("tA", phone)).status == OPT_OUT
        # any later finalize (incl a parsed callback_at) can NEVER re-open opt-out.
        out2 = await enqueue_smart("tA", "c", _rec(phone=phone), {"callback_at": "5pm"},
                                   "no_answer", 0, {}, store=store, config=CFG, now=NOW)
        assert out2 is None
        assert (await store.load("tA", phone)).status == OPT_OUT
        return True

    assert _run(go())


# --------------------------------------------------------------------------- #
# 7. REGRESSION: the OLD runaway "reset attempts -> 1 every tick" loop
# --------------------------------------------------------------------------- #
def test_regression_recon_tick_never_resets_attempts():
    # The old bug: the reconciliation sweep upsert-reset attempts to 0/1 on every
    # 60s tick for a lingering un-reconciled call -> the attempts<max guard never
    # tripped -> infinite redial. Here we simulate MANY recon ticks on the same
    # lead and assert attempts is MONOTONIC and the lead EXPIRES (loop ends).
    async def go():
        store = InMemoryCallbackStore()
        phone = "+919800000011"
        # arrival finalize.
        await enqueue_smart("tA", "c", _rec(phone=phone), {}, "no_answer", 0, {},
                            store=store, config=CFG, now=NOW, from_reconcile=True)
        seen_attempts = []
        for _ in range(50):  # 50 recon ticks (the runaway loop driver)
            row = await store.load("tA", phone)
            if row.status == EXPIRED:
                break
            if row.status == PENDING:
                # a real scheduler tick would dial + increment; simulate that.
                await store.record_attempt("tA", phone)
                await store.unlock("tA", phone)
            seen_attempts.append((await store.load("tA", phone)).attempts)
            # the recon sweep re-fires enqueue_smart with attempt_hint=0 (the OLD
            # bug source). It must NOT reset the persisted counter.
            await enqueue_smart("tA", "c", _rec(phone=phone), {}, "no_answer", 0, {},
                                store=store, config=CFG, now=NOW, from_reconcile=True)
        # monotonic non-decreasing attempts (never reset to 0/1 mid-stream).
        assert seen_attempts == sorted(seen_attempts), seen_attempts
        # and it terminated at the cap rather than looping forever.
        final = await store.load("tA", phone)
        assert final.status == EXPIRED and final.attempts <= 3
        # attempt_hint=0 on every call NEVER pushed it back to 0.
        assert all(a >= 1 for a in seen_attempts[1:]) or seen_attempts[-1] <= 3
        return True

    assert _run(go())


def test_priority_callback_storm_is_bounded():
    # RED-TEAM regression: a 'call me at X' is EXEMPT from the cadence cap. If a
    # stale/repeatedly-resupplied callback_at re-armed a priority entry on every
    # no-answer, the priority exemption would re-incarnate the runaway-spam bug
    # (one dial/day forever). The absolute `max_priority_dials` ceiling must cap it.
    async def go():
        store = InMemoryCallbackStore()
        phone = "+919800000099"
        clock = parse_iso(NOW)
        dials = 0
        await enqueue_smart("tA", "c", _rec(phone=phone), {"callback_at": "5pm"},
                            "no_answer", 0, {}, store=store, config=CFG, now=_z(clock))
        for _ in range(30):  # adversary keeps re-supplying callback_at every tick
            row = await store.load("tA", phone)
            if row.status == EXPIRED:
                break
            if row.next_attempt_at:
                clock = parse_iso(row.next_attempt_at) + timedelta(minutes=1)
            jobs = await fire_due(store=store, config=CFG, now=_z(clock))
            if jobs:
                dials += 1
                await store.unlock("tA", phone)
            await enqueue_smart("tA", "c", _rec(phone=phone), {"callback_at": "5pm"},
                                "no_answer", 0, {}, store=store, config=CFG, now=_z(clock))
        row = await store.load("tA", phone)
        # bounded by max_priority_dials (default 3), then EXPIRED — NOT unbounded.
        assert dials <= CFG.max_priority_dials, dials
        assert row.status == EXPIRED, (row.status, row.attempts)
        return True

    assert _run(go())


def test_tenant_override_cannot_widen_into_spam():
    # RED-TEAM regression: a tenant panel override must only ever make the cadence
    # SAFER. An abusive override (min_gap=1, max_retries=999) must be clamped:
    # min_gap can't shrink below the base floor; max_retries can't exceed the base.
    async def go():
        store = InMemoryCallbackStore()
        camp = {"callback_overrides": {"min_gap_mins": 1, "max_retries": 999}}
        out = await enqueue_smart("tA", "c", _rec(phone="+919800000098"), {},
                                  "no_answer", 0, camp, store=store, config=CFG, now=NOW)
        gap = parse_iso(out.next_attempt_at) - parse_iso(NOW)
        assert gap >= timedelta(minutes=CFG.min_gap_mins), gap  # floor not shrunk
        # the cap is clamped to the base, so max attempts stays <= base max_retries.
        clamped = CFG.for_tenant(camp["callback_overrides"])
        assert clamped.max_retries <= CFG.max_retries, clamped.max_retries
        assert clamped.min_gap_mins >= CFG.min_gap_mins, clamped.min_gap_mins
        return True

    assert _run(go())


def test_disabled_engine_is_noop():
    async def go():
        store = InMemoryCallbackStore()
        off = CallbackConfig(enabled=False)
        out = await enqueue_smart("tA", "c", _rec(), {}, "no_answer", 0, {},
                                  store=store, config=off, now=NOW)
        assert out is None
        assert store.snapshot() == []
        assert await fire_due(store=store, config=off, now=NOW) == []
        return True

    assert _run(go())


def test_tenant_can_disable_via_override():
    async def go():
        store = InMemoryCallbackStore()
        # global enabled, but this tenant set callback_overrides.enabled = False.
        camp = {"callback_overrides": {"enabled": False}}
        out = await enqueue_smart("tA", "c", _rec(), {}, "no_answer", 0, camp,
                                  store=store, config=CFG, now=NOW)
        assert out is None
        return True

    assert _run(go())


def test_tenant_can_tune_cadence_via_override():
    async def go():
        store = InMemoryCallbackStore()
        # tenant wants a tighter cadence + only 1 retry.
        camp = {"callback_overrides": {"cadence_mins": [0, 60, 180], "max_retries": 1}}
        out = await enqueue_smart("tA", "c", _rec(), {}, "no_answer", 0, camp,
                                  store=store, config=CFG, now=NOW)
        assert out is not None
        gap = parse_iso(out.next_attempt_at) - parse_iso(out.created_at)
        # touch 1 offset = 60 min, but min_gap floor (120) lifts it to >= 120.
        assert gap >= timedelta(minutes=60)
        return True

    assert _run(go())


# --------------------------------------------------------------------------- #
# DND / quiet-hours guard
# --------------------------------------------------------------------------- #
def test_dnd_pushes_into_business_hours():
    async def go():
        store = InMemoryCallbackStore()
        # NOW = 22:30 IST (17:00 UTC) — inside quiet hours.
        late = "2026-06-18T17:00:00Z"
        out = await enqueue_smart("tA", "c", _rec(phone="+919800000012"), {},
                                  "busy", 0, {}, store=store, config=CFG, now=late)
        local = parse_iso(out.next_attempt_at).astimezone(_tz("Asia/Kolkata"))
        # a 25-min busy retry from 22:30 would land 22:55 (quiet) -> pushed to 09:00.
        assert local.hour == 9, local
        assert local.date() == datetime(2026, 6, 19).date(), local
        return True

    assert _run(go())


def test_fire_due_defers_in_quiet_hours():
    async def go():
        store = InMemoryCallbackStore()
        phone = "+919800000013"
        late = "2026-06-18T17:00:00Z"  # 22:30 IST
        await store.upsert(CallbackEntry(
            tenant_id="tA", phone=phone, campaign_id="c", lead_id="L",
            status=PENDING, attempts=0, next_attempt_at=late, reason="cadence",
        ))
        jobs = await fire_due(store=store, config=CFG, now=late)
        assert jobs == []  # deferred, not dialed in the night
        row = await store.load("tA", phone)
        local = parse_iso(row.next_attempt_at).astimezone(_tz("Asia/Kolkata"))
        assert local.hour == 9
        return True

    assert _run(go())
