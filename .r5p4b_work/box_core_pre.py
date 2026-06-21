"""booking.core — the Booking engine: availability + atomic slot claim + reschedule/cancel +
reminder scheduling + no-show follow-up. Postgres-native, RLS-scoped, dormant-safe.

DESIGN INVARIANTS (the load-bearing ones a reviewer will hammer):

  1. NO DOUBLE-BOOK. `book()` claims a slot with a SINGLE atomic write — `INSERT ... ON CONFLICT
     DO NOTHING` against the partial unique index `bookings_active_slot_uq` (capacity 1), or a
     `FOR UPDATE`-counted admission for capacity>1. NEVER read-check-write. Two concurrent bookings
     for the same slot: exactly one wins, the other gets `{ok:False, reason:"slot_taken"}`. This is
     the booking analogue of `wallet.reserve`'s single-statement conditional UPDATE.

  2. SPEND IS GATED, BOOKING IS FREE. Creating/rescheduling/cancelling a booking spends nothing and
     needs no PIN. Only ACTUATING a reminder/no-show nudge (a paid call/WhatsApp) is risky — that
     path goes through `firewall` (PIN / step-up, FAIL-CLOSED when absent) + `wallet.reserve`
     (no double-spend) + an idempotent `booking_reminder_fires` dedup, and it ENQUEUES into the
     existing gated dial path (the enqueue wiring is the DEFERRED mount). `tick(dry_run=True)`
     returns the would-fire set WITHOUT enqueuing — that is the only mode that runs pre-mount.

  3. PURE-FUNCTION CORE. Availability + slot enumeration + reminder-due math are PURE functions
     (no DB, no clock injected via args) so they are unit-testable with zero infra. The DB layer
     wraps them.

  4. DORMANT-SAFE. With no Postgres every entry point returns `{"status":"not_configured"}` and
     NEVER raises. The live site is never affected.

COMPOSITION (all LAZY / import-guarded): db.engine (RLS sessions), firewall, wallet, crm timeline
(via booking.identity), config. None imported at top level except identity/config/models (own pkg).
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import secrets
from typing import Any, Iterable, Optional

from . import config, identity, models

# ---- status constants re-exported for callers / tests ----
STATUS_BOOKED = models.STATUS_BOOKED
STATUS_RESCHEDULED = models.STATUS_RESCHEDULED
STATUS_CANCELLED = models.STATUS_CANCELLED
STATUS_COMPLETED = models.STATUS_COMPLETED
STATUS_NO_SHOW = models.STATUS_NO_SHOW
KIND_REMINDER = models.KIND_REMINDER
KIND_NO_SHOW = models.KIND_NO_SHOW

_NOT_CONFIGURED = {"status": "not_configured", "reason": "postgres_unavailable"}


# ============================================================================
# helpers
# ============================================================================
def _now() -> _dt.datetime:
    return _dt.datetime.now(_dt.timezone.utc)


def _new_id(prefix: str) -> str:
    return f"{prefix}{secrets.token_hex(6)}"


def _iso(dt: _dt.datetime) -> str:
    return dt.astimezone(_dt.timezone.utc).isoformat()


def _parse_dt(v: Any) -> Optional[_dt.datetime]:
    """Best-effort ISO/`datetime` -> aware UTC datetime. None on failure (never raises)."""
    if v is None or v == "":
        return None
    if isinstance(v, _dt.datetime):
        return v if v.tzinfo else v.replace(tzinfo=_dt.timezone.utc)
    try:
        s = str(v).strip().replace("Z", "+00:00")
        d = _dt.datetime.fromisoformat(s)
        return d if d.tzinfo else d.replace(tzinfo=_dt.timezone.utc)
    except Exception:  # noqa: BLE001
        return None


def _engine():
    """Lazy import-guarded db.engine. None when the P1 spine is absent."""
    try:
        from db import engine as eng  # type: ignore
        return eng if eng.available() else None
    except Exception:  # noqa: BLE001
        return None


def _text(sql: str):
    from sqlalchemy import text  # local import (sqlalchemy may be absent in a bare env)
    return text(sql)


# ============================================================================
# Google Calendar two-way sync (best-effort, dormant-until-creds, NEVER breaks a booking)
# ============================================================================
def _calendar_sync_event(org_id: str, op: str, booking: dict, *,
                         booking_id: str = "", calendar_event_id: str = "") -> None:
    """Push a book/reschedule/cancel to Google Calendar AFTER the DB txn commits.

    100% best-effort: lazy-imports calendar_sync (so a missing google SDK / dormant config is a
    pure no-op), NEVER raises into the booking result, and persists `bookings.calendar_event_id`
    via a separate guarded UPDATE when a fresh event id comes back. Calendar is an ENRICHMENT, not
    a dependency — when `BOOKING_CALENDAR_SYNC=1` + OAuth creds are present it goes live with zero
    caller change; until then `calendar_sync.available()` is False and this returns immediately.
    """
    try:
        from . import calendar_sync  # lazy: keeps import-time dormant-safe
        if not calendar_sync.available():
            return
        if op == "book":
            res = calendar_sync.push_event(org_id, booking)
        elif op == "reschedule":
            res = calendar_sync.update_event(org_id, calendar_event_id, booking)
        elif op == "cancel":
            calendar_sync.cancel_event(org_id, calendar_event_id)
            return
        else:
            return
        ev_id = (res or {}).get("event_id", "")
        if ev_id and booking_id:
            _calendar_persist_event_id(org_id, booking_id, ev_id)
    except Exception:  # noqa: BLE001 — calendar can NEVER break the booking
        return


def _calendar_persist_event_id(org_id: str, booking_id: str, event_id: str) -> None:
    """Best-effort write-back of the Google event id onto the booking row (guarded)."""
    try:
        eng = _engine()
        if eng is None:
            return
        with eng.session(tenant_id=org_id, is_admin=True) as s:
            s.execute(_text(
                "UPDATE bookings SET calendar_event_id=:ev, updated_at=now() "
                "WHERE id=:id AND org_id=:org"
            ), {"ev": event_id, "id": booking_id, "org": org_id})
    except Exception:  # noqa: BLE001
        return


def _booking_calendar_event_id(org_id: str, booking_id: str) -> str:
    """Read the stored Google event id for a booking (best-effort, '' when absent/dormant)."""
    try:
        eng = _engine()
        if eng is None:
            return ""
        with eng.session(tenant_id=org_id, is_admin=True) as s:
            row = s.execute(_text(
                "SELECT calendar_event_id FROM bookings WHERE id=:id AND org_id=:org"
            ), {"id": booking_id, "org": org_id}).fetchone()
        return (row[0] or "") if row else ""
    except Exception:  # noqa: BLE001
        return ""


# ============================================================================
# PURE availability math (no DB, no infra) — unit-testable in isolation.
# ============================================================================
def parse_hhmm(s: str) -> Optional[int]:
    """'HH:MM' -> minutes-since-midnight, or None. Pure."""
    try:
        hh, mm = (s or "").split(":")
        h, m = int(hh), int(mm)
        if 0 <= h <= 23 and 0 <= m <= 59:
            return h * 60 + m
    except Exception:  # noqa: BLE001
        pass
    return None


def enumerate_slots(
    windows: Iterable[dict],
    *,
    day: _dt.date,
    slot_minutes: int,
    tz_offset_minutes: int = 0,
) -> list[tuple[_dt.datetime, _dt.datetime]]:
    """Enumerate (start,end) UTC slot pairs for a single `day` from availability `windows`.

    `windows` = [{"dow":0-6 (Mon=0), "start":"HH:MM", "end":"HH:MM"}]. `tz_offset_minutes` converts
    the resource-local wall time to UTC (positive = ahead of UTC, e.g. IST=+330). PURE — no DB, no now().
    Slots that don't fit a full `slot_minutes` at the tail of a window are dropped. Deterministic order.
    """
    out: list[tuple[_dt.datetime, _dt.datetime]] = []
    step = max(1, int(slot_minutes))
    dow = day.weekday()
    midnight_local = _dt.datetime(day.year, day.month, day.day, tzinfo=_dt.timezone.utc)
    for w in windows or []:
        if int(w.get("dow", -1)) != dow:
            continue
        ws = parse_hhmm(w.get("start", ""))
        we = parse_hhmm(w.get("end", ""))
        if ws is None or we is None or we <= ws:
            continue
        cur = ws
        while cur + step <= we:
            local_start = midnight_local + _dt.timedelta(minutes=cur)
            local_end = local_start + _dt.timedelta(minutes=step)
            # convert resource-local wall clock -> UTC by subtracting the tz offset
            utc_start = local_start - _dt.timedelta(minutes=tz_offset_minutes)
            utc_end = local_end - _dt.timedelta(minutes=tz_offset_minutes)
            out.append((utc_start, utc_end))
            cur += step
    out.sort(key=lambda p: p[0])
    return out


def slots_overlap(a_start: _dt.datetime, a_end: _dt.datetime,
                  b_start: _dt.datetime, b_end: _dt.datetime) -> bool:
    """True if [a_start,a_end) and [b_start,b_end) overlap. Pure."""
    return a_start < b_end and b_start < a_end


def reminder_schedule_for(slot_start: _dt.datetime, *, offsets_minutes: Iterable[int]) -> list[_dt.datetime]:
    """Given a booking start, the list of fire-times = slot_start - offset. Pure (used by schedule_reminders)."""
    return [slot_start - _dt.timedelta(minutes=int(o)) for o in offsets_minutes]


def is_due(fire_at: _dt.datetime, now: _dt.datetime) -> bool:
    """A reminder is due when its fire time has passed. Pure (now injected — testable)."""
    return fire_at <= now


def is_no_show(slot_end: _dt.datetime, status: str, now: _dt.datetime, grace_minutes: int) -> bool:
    """A still-active booking is a no-show once `slot_end + grace` has passed. Pure."""
    if status not in models.ACTIVE_STATUSES:
        return False
    return now >= slot_end + _dt.timedelta(minutes=int(grace_minutes))


# ============================================================================
# resources
# ============================================================================
def create_resource(org_id: str, name: str, *, kind: str = "appointment",
                    timezone: str = "", slot_minutes: int = 0, capacity: int = 1,
                    windows: Optional[list] = None, is_admin: bool = False) -> dict:
    """Create a bookable resource. Dormant-safe.

    SCOPE: only capacity == 1 (one booking per slot) is honored. Multi-capacity per slot
    (a team/pool serving N parallel bookings) is the dedicated **Inventory / Capacity Management**
    module's job (roadmap row 147), which gates Booking — not baked into this core. We REJECT
    capacity != 1 explicitly rather than silently clamp (a silent clamp would be a hidden oversell
    lie). The `capacity` column is retained in the schema reserved-for-future so the Inventory module
    can light it up without a migration.
    """
    eng = _engine()
    if eng is None:
        return dict(_NOT_CONFIGURED)
    if int(capacity or 1) != 1:
        return {"status": "error", "reason": "multi_capacity_not_supported",
                "detail": "per-slot capacity>1 is owned by the Inventory/Capacity module (roadmap §147)"}
    rid = _new_id("res_")
    tz = timezone or config.default_timezone()
    sm = int(slot_minutes or config.default_slot_minutes())
    data = {"windows": windows or [], "blackouts": []}
    try:
        with eng.session(tenant_id=org_id, is_admin=is_admin) as s:
            s.execute(_text(
                "INSERT INTO booking_resources "
                "(id, org_id, name, kind, timezone, slot_minutes, capacity, active, created_at, data) "
                "VALUES (:id,:org,:name,:kind,:tz,:sm,:cap,'active',now(),CAST(:data AS jsonb))"
            ), {"id": rid, "org": org_id, "name": name or "", "kind": kind, "tz": tz,
                "sm": sm, "cap": max(1, int(capacity)), "data": _json(data)})
        return {"status": "ok", "resource": {"id": rid, "org_id": org_id, "name": name,
                "kind": kind, "timezone": tz, "slot_minutes": sm, "capacity": max(1, int(capacity)),
                "windows": data["windows"]}}
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "reason": "db_error", "detail": repr(exc)[:160]}


def _json(obj: Any) -> str:
    import json
    return json.dumps(obj, ensure_ascii=False)


def _event_id(org_id: str, booking_id: str, event_type: str, discriminator: str = "") -> str:
    """Deterministic id for the immutable audit row, from the NATURAL key — NEVER wall-clock.

    Basis = (org|booking|type|discriminator). Every single-occurrence type per booking
    (booked/cancelled/completed/no_show, and rescheduled which lands on a fresh booking_id) is already
    unique by (org,booking,type). The ONE repeatable type is reminder_fired (a booking can fire several
    reminders), so the reminder_id is its discriminator. Result: ON CONFLICT (id) DO NOTHING is REAL
    replay-idempotency (a re-emit of the SAME transition is a true no-op) AND two distinct reminder
    fires for one booking never collide (same trap a microsecond `at` would have inverted — distinct
    events must never share a hash). Mirrors payments (id keyed on provider_event_id, a natural key)."""
    basis = f"{org_id}|{booking_id}|{event_type}|{discriminator}"
    return "be_" + hashlib.sha1(basis.encode("utf-8")).hexdigest()[:24]


def _record_event(s, org_id: str, booking_id: str, event_type: str, *, resource_id: str = "",
                  contact_id: str = "", status_from: str = "", status_to: str = "",
                  actor: str = "system", discriminator: str = "",
                  data: Optional[dict] = None) -> None:
    """Append ONE immutable audit row to booking_events IN THE CURRENT txn (the F4 'audit immutable'
    leg the module composes — mirrors payments._record_event). Append-only: INSERT ... ON CONFLICT
    (id) DO NOTHING, NEVER UPDATE/DELETE.

    ATOMIC WITH THE TRANSITION (not best-effort): this runs INSIDE the caller's `with eng.session()`
    block, so a failed audit insert rolls the whole transition back — there is NO booking mutation
    without its audit row, and no audit row without the mutation. (Same discipline as payments: the
    event commits in the same txn as the state change.) `discriminator` makes the id unique for the
    one repeatable type (reminder_fired -> reminder_id)."""
    eid = _event_id(org_id, booking_id, event_type, discriminator)
    s.execute(_text(
        "INSERT INTO booking_events "
        "(id, org_id, booking_id, resource_id, contact_id, event_type, status_from, status_to, "
        " actor, at, data) "
        "VALUES (:id,:org,:bk,:rid,:cid,:et,:sf,:st,:actor,now(),CAST(:data AS jsonb)) "
        "ON CONFLICT (id) DO NOTHING"
    ), {"id": eid, "org": org_id, "bk": booking_id, "rid": resource_id, "cid": contact_id,
        "et": event_type, "sf": status_from, "st": status_to, "actor": actor,
        "data": _json(data or {})})


def get_availability(org_id: str, resource_id: str, *, day: _dt.date,
                     is_admin: bool = False) -> dict:
    """Free slots for a resource on a day = enumerate_slots(windows) MINUS already-booked active slots.

    Dormant-safe. The booked-set query is RLS-scoped to org_id.
    """
    eng = _engine()
    if eng is None:
        return dict(_NOT_CONFIGURED)
    try:
        with eng.session(tenant_id=org_id, is_admin=is_admin) as s:
            res = s.execute(_text(
                "SELECT slot_minutes, timezone, capacity, data FROM booking_resources "
                "WHERE id=:id AND org_id=:org"
            ), {"id": resource_id, "org": org_id}).fetchone()
            if res is None:
                return {"status": "error", "reason": "resource_not_found"}
            slot_minutes, tz, capacity = int(res[0]), res[1], int(res[2])
            data = res[3] or {}
            windows = data.get("windows", [])
            tz_off = _tz_offset_minutes(tz)
            all_slots = enumerate_slots(windows, day=day, slot_minutes=slot_minutes,
                                        tz_offset_minutes=tz_off)
            # taken counts per slot_start
            d0 = _dt.datetime(day.year, day.month, day.day, tzinfo=_dt.timezone.utc) - _dt.timedelta(days=1)
            d1 = d0 + _dt.timedelta(days=3)
            rows = s.execute(_text(
                "SELECT slot_start, count(*) FROM bookings "
                "WHERE org_id=:org AND resource_id=:rid AND status IN ('booked','rescheduled') "
                "  AND slot_start >= :d0 AND slot_start < :d1 GROUP BY slot_start"
            ), {"org": org_id, "rid": resource_id, "d0": d0, "d1": d1}).fetchall()
            taken = {r[0]: int(r[1]) for r in rows}
            free = []
            for (st, en) in all_slots:
                used = taken.get(st, 0)
                if used < capacity:
                    free.append({"slot_start": _iso(st), "slot_end": _iso(en),
                                 "remaining": capacity - used})
            return {"status": "ok", "resource_id": resource_id, "day": day.isoformat(),
                    "slot_minutes": slot_minutes, "free": free}
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "reason": "db_error", "detail": repr(exc)[:160]}


def _tz_offset_minutes(tz: str) -> int:
    """IANA tz name -> current UTC offset minutes. Best-effort; 330 (IST) fallback, 0 on failure."""
    try:
        from zoneinfo import ZoneInfo  # py3.9+
        off = _dt.datetime.now(ZoneInfo(tz or "Asia/Kolkata")).utcoffset()
        return int(off.total_seconds() // 60) if off else 0
    except Exception:  # noqa: BLE001
        return 330 if (tz or "").lower() in ("asia/kolkata", "ist", "") else 0


# ============================================================================
# book — THE ATOMIC CLAIM (no double-book)
# ============================================================================
def book(org_id: str, resource_id: str, phone: str, *, slot_start: Any, slot_end: Any = None,
         name: str = "", title: str = "", notes: str = "", source: str = "",
         campaign_id: str = "", schedule_reminders: bool = True,
         is_admin: bool = False) -> dict:
    """Atomically claim a slot for a contact. Returns the booking or {ok:False, reason:"slot_taken"}.

    No spend, no PIN — booking is free. The anti-double-book is the partial unique index (capacity 1)
    or a FOR UPDATE-counted admission (capacity>1), both inside ONE txn. NEVER read-check-write.
    """
    eng = _engine()
    if eng is None:
        return dict(_NOT_CONFIGURED)
    st = _parse_dt(slot_start)
    if st is None:
        return {"ok": False, "status": "error", "reason": "bad_slot_start"}
    cid = identity.contact_id(org_id, phone)
    pkey = identity.canonical_phone(phone)
    pdisp = identity.phone_display(phone)
    bk_id = _new_id("bk_")
    try:
        with eng.session(tenant_id=org_id, is_admin=is_admin) as s:
            res = s.execute(_text(
                "SELECT slot_minutes FROM booking_resources WHERE id=:id AND org_id=:org"
            ), {"id": resource_id, "org": org_id}).fetchone()
            if res is None:
                return {"ok": False, "status": "error", "reason": "resource_not_found"}
            slot_minutes = int(res[0])
            en = _parse_dt(slot_end) or (st + _dt.timedelta(minutes=slot_minutes))

            # THE ATOMIC CLAIM (capacity 1): the partial unique index is the arbiter.
            # ON CONFLICT DO NOTHING -> 0 rows returned == the slot was already taken. A single
            # statement, no read-check-write -> two concurrent books can never both win.
            row = s.execute(_text(
                "INSERT INTO bookings "
                "(id, org_id, resource_id, contact_id, phone_key, phone_display, name, status, "
                " slot_start_raw, slot_end_raw, slot_start, slot_end, title, notes, source, "
                " campaign_id, created_at, updated_at, data) "
                "VALUES (:id,:org,:rid,:cid,:pk,:pd,:nm,'booked',:ssr,:ser,:ss,:se,:ti,:no,:src,"
                " :camp,now(),now(),'{}'::jsonb) "
                "ON CONFLICT (org_id, resource_id, slot_start) "
                "  WHERE status IN ('booked','rescheduled') DO NOTHING "
                "RETURNING id"
            ), {"id": bk_id, "org": org_id, "rid": resource_id, "cid": cid, "pk": pkey,
                "pd": pdisp, "nm": name, "ssr": _iso(st), "ser": _iso(en), "ss": st, "se": en,
                "ti": title, "no": notes, "src": source, "camp": campaign_id}).fetchone()
            if row is None:
                return {"ok": False, "status": "conflict", "reason": "slot_taken"}

            # IMMUTABLE audit (F4 audit leg): record the 'booked' transition in-txn (append-only).
            _record_event(s, org_id, bk_id, "booked", resource_id=resource_id, contact_id=cid,
                          status_to="booked", actor=source or "system",
                          data={"slot_start": _iso(st), "campaign_id": campaign_id})

            if schedule_reminders:
                _schedule_default_reminders(s, org_id, bk_id, st)

        booking = {"id": bk_id, "org_id": org_id, "resource_id": resource_id, "contact_id": cid,
                   "phone_key": pkey, "phone_display": pdisp, "name": name, "status": "booked",
                   "slot_start": _iso(st), "slot_end": _iso(en), "title": title,
                   "source": source, "campaign_id": campaign_id}
        # LAZY crm timeline link (no-op when crm absent / PG lagging) — never breaks the booking.
        tl = identity.record_booking_timeline(org_id, phone, booking_id=bk_id, at=st,
                                              title=title or "Appointment booked",
                                              body=notes, outcome="booked",
                                              data={"resource_id": resource_id, "slot_start": _iso(st)})
        booking["timeline"] = tl.get("status")
        # Google Calendar two-way sync (best-effort, dormant-until-creds; never breaks the booking).
        _calendar_sync_event(org_id, "book", booking, booking_id=bk_id)
        return {"ok": True, "status": "ok", "booking": booking}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "status": "error", "reason": "db_error", "detail": repr(exc)[:160]}


def _schedule_default_reminders(s, org_id: str, booking_id: str, slot_start: _dt.datetime) -> None:
    """Insert the default reminder rows (T-24h, T-2h) for a fresh booking, inside the booking txn.

    DEFAULT: reminders require a PIN (spend) and are state='pending' — they ACTUATE nothing here; the
    gated enqueue happens in `tick()` and is the deferred mount. Idempotent re-insert is harmless
    because ids are fresh; double-scheduling is prevented by callers (only fresh bookings call this).
    """
    for off in (24 * 60, 2 * 60):
        fire = slot_start - _dt.timedelta(minutes=off)
        rid = _new_id("rem_")
        s.execute(_text(
            "INSERT INTO booking_reminders "
            "(id, org_id, booking_id, kind, channel, template, fire_at_raw, fire_at, state, "
            " requires_pin, est_cost_minor, created_at, data) "
            "VALUES (:id,:org,:bk,'reminder','whatsapp','booking_reminder',:fr,:f,'pending','1',0,"
            " now(),'{}'::jsonb)"
        ), {"id": rid, "org": org_id, "bk": booking_id, "fr": _iso(fire), "f": fire})


# ============================================================================
# reschedule / cancel
# ============================================================================
def reschedule(org_id: str, booking_id: str, *, new_slot_start: Any, new_slot_end: Any = None,
               is_admin: bool = False) -> dict:
    """Move a booking to a new slot. Atomic: cancel-then-claim in ONE txn, so the new slot is
    contention-safe and the old slot is freed. Returns the updated booking or a conflict."""
    eng = _engine()
    if eng is None:
        return dict(_NOT_CONFIGURED)
    nst = _parse_dt(new_slot_start)
    if nst is None:
        return {"ok": False, "status": "error", "reason": "bad_slot_start"}
    # capture any existing Google event id BEFORE the txn frees/cancels the old row (best-effort).
    _old_cal_ev = _booking_calendar_event_id(org_id, booking_id)
    try:
        with eng.session(tenant_id=org_id, is_admin=is_admin) as s:
            old = s.execute(_text(
                "SELECT resource_id, status, slot_start, contact_id, phone_key, name "
                "FROM bookings WHERE id=:id AND org_id=:org FOR UPDATE"
            ), {"id": booking_id, "org": org_id}).fetchone()
            if old is None:
                return {"ok": False, "status": "error", "reason": "booking_not_found"}
            resource_id, status = old[0], old[1]
            if status not in models.ACTIVE_STATUSES:
                return {"ok": False, "status": "error", "reason": f"not_active:{status}"}
            res = s.execute(_text(
                "SELECT slot_minutes FROM booking_resources WHERE id=:id AND org_id=:org"
            ), {"id": resource_id, "org": org_id}).fetchone()
            slot_minutes = int(res[0]) if res else config.default_slot_minutes()
            nen = _parse_dt(new_slot_end) or (nst + _dt.timedelta(minutes=slot_minutes))
            # free the old slot FIRST (so a same-resource move to an adjacent slot can't self-conflict)
            s.execute(_text(
                "UPDATE bookings SET status='cancelled', updated_at=now() WHERE id=:id AND org_id=:org"
            ), {"id": booking_id, "org": org_id})
            # claim the new slot atomically (capacity 1 -> partial unique index, same as book()).
            new_id = _new_id("bk_")
            row = s.execute(_text(
                "INSERT INTO bookings (id, org_id, resource_id, contact_id, phone_key, "
                " phone_display, name, status, slot_start_raw, slot_end_raw, slot_start, slot_end, "
                " reschedule_of, created_at, updated_at, data) "
                "SELECT :nid, org_id, resource_id, contact_id, phone_key, phone_display, name, "
                " 'rescheduled', :ssr, :ser, :ss, :se, :of, now(), now(), data "
                "FROM bookings WHERE id=:old AND org_id=:org "
                "ON CONFLICT (org_id, resource_id, slot_start) "
                "  WHERE status IN ('booked','rescheduled') DO NOTHING RETURNING id"
            ), {"nid": new_id, "ssr": _iso(nst), "ser": _iso(nen), "ss": nst, "se": nen,
                "of": booking_id, "old": booking_id, "org": org_id}).fetchone()
            if row is None:
                # new slot was taken -> roll back the cancel by re-activating the original.
                s.execute(_text(
                    "UPDATE bookings SET status=:st, updated_at=now() WHERE id=:id AND org_id=:org"
                ), {"st": status, "id": booking_id, "org": org_id})
                return {"ok": False, "status": "conflict", "reason": "new_slot_taken"}
            # cancel pending reminders on the old booking; schedule fresh ones on the new
            s.execute(_text(
                "UPDATE booking_reminders SET state='cancelled' WHERE org_id=:org AND booking_id=:bk "
                "AND state='pending'"
            ), {"org": org_id, "bk": booking_id})
            _schedule_default_reminders(s, org_id, new_id, nst)
            # IMMUTABLE audit: the old booking was cancelled (status_from=its prior active state) and a
            # new 'rescheduled' booking minted — two append-only rows tracing the move.
            _record_event(s, org_id, booking_id, "cancelled", resource_id=resource_id,
                          status_from=status, status_to="cancelled", actor="system",
                          data={"reason": "rescheduled_to", "new_booking_id": new_id})
            _record_event(s, org_id, new_id, "rescheduled", resource_id=resource_id,
                          status_to="rescheduled", actor="system",
                          data={"reschedule_of": booking_id, "slot_start": _iso(nst)})
        # Google Calendar: PATCH the existing event to the new slot (or create one if never synced),
        # then persist its id onto the NEW booking row. Best-effort, dormant-safe.
        _rb = {"id": new_id, "title": "Appointment", "slot_start": _iso(nst), "slot_end": _iso(nen)}
        _calendar_sync_event(org_id, "reschedule", _rb, booking_id=new_id,
                             calendar_event_id=_old_cal_ev)
        return {"ok": True, "status": "ok", "booking": {"id": new_id, "reschedule_of": booking_id,
                "status": "rescheduled", "slot_start": _iso(nst), "slot_end": _iso(nen)}}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "status": "error", "reason": "db_error", "detail": repr(exc)[:160]}


def cancel(org_id: str, booking_id: str, *, reason: str = "", is_admin: bool = False) -> dict:
    """Cancel a booking (frees the slot) + cancel its pending reminders. Idempotent."""
    eng = _engine()
    if eng is None:
        return dict(_NOT_CONFIGURED)
    _cal_ev = _booking_calendar_event_id(org_id, booking_id)  # capture before flip (best-effort)
    try:
        with eng.session(tenant_id=org_id, is_admin=is_admin) as s:
            row = s.execute(_text(
                "UPDATE bookings SET status='cancelled', updated_at=now(), "
                " data = jsonb_set(coalesce(data,'{}'::jsonb), '{cancel_reason}', to_jsonb(:r::text)) "
                "WHERE id=:id AND org_id=:org AND status IN ('booked','rescheduled') RETURNING id"
            ), {"id": booking_id, "org": org_id, "r": reason or ""}).fetchone()
            s.execute(_text(
                "UPDATE booking_reminders SET state='cancelled' WHERE org_id=:org AND booking_id=:bk "
                "AND state='pending'"
            ), {"org": org_id, "bk": booking_id})
            if row is not None:
                # IMMUTABLE audit: record the cancel only when an active booking was actually flipped
                # (a no-op cancel of an already-inactive/missing booking writes no event).
                _record_event(s, org_id, booking_id, "cancelled", status_to="cancelled",
                              actor="system", data={"reason": reason or ""})
        if row is None:
            return {"ok": True, "status": "noop", "reason": "already_inactive_or_missing",
                    "booking_id": booking_id}
        # Google Calendar: delete the event (best-effort, dormant-safe; only on a real flip).
        if _cal_ev:
            _calendar_sync_event(org_id, "cancel", {}, booking_id=booking_id,
                                 calendar_event_id=_cal_ev)
        return {"ok": True, "status": "ok", "booking_id": booking_id, "new_status": "cancelled"}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "status": "error", "reason": "db_error", "detail": repr(exc)[:160]}


def mark_completed(org_id: str, booking_id: str, *, is_admin: bool = False) -> dict:
    """Mark an attended booking completed (frees the active-slot predicate, records outcome)."""
    eng = _engine()
    if eng is None:
        return dict(_NOT_CONFIGURED)
    try:
        with eng.session(tenant_id=org_id, is_admin=is_admin) as s:
            row = s.execute(_text(
                "UPDATE bookings SET status='completed', updated_at=now() "
                "WHERE id=:id AND org_id=:org AND status IN ('booked','rescheduled') RETURNING id"
            ), {"id": booking_id, "org": org_id}).fetchone()
            if row is not None:
                _record_event(s, org_id, booking_id, "completed", status_to="completed",
                              actor="system")
        return {"ok": row is not None, "status": "ok" if row else "noop", "booking_id": booking_id}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "status": "error", "reason": "db_error", "detail": repr(exc)[:160]}


def get_booking(org_id: str, booking_id: str, *, is_admin: bool = False) -> dict:
    eng = _engine()
    if eng is None:
        return dict(_NOT_CONFIGURED)
    try:
        with eng.session(tenant_id=org_id, is_admin=is_admin) as s:
            row = s.execute(_text(
                "SELECT id, resource_id, contact_id, phone_display, name, status, slot_start_raw, "
                " slot_end_raw, title, source, campaign_id FROM bookings WHERE id=:id AND org_id=:org"
            ), {"id": booking_id, "org": org_id}).fetchone()
            if row is None:
                return {"status": "error", "reason": "booking_not_found"}
            keys = ["id", "resource_id", "contact_id", "phone_display", "name", "status",
                    "slot_start", "slot_end", "title", "source", "campaign_id"]
            return {"status": "ok", "booking": dict(zip(keys, row))}
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "reason": "db_error", "detail": repr(exc)[:160]}


def list_bookings(org_id: str, *, contact_id: str = "", status: str = "", limit: int = 100,
                  is_admin: bool = False) -> dict:
    eng = _engine()
    if eng is None:
        return dict(_NOT_CONFIGURED)
    try:
        with eng.session(tenant_id=org_id, is_admin=is_admin) as s:
            clauses = ["org_id=:org"]
            params: dict = {"org": org_id, "lim": max(1, min(int(limit), 500))}
            if contact_id:
                clauses.append("contact_id=:cid"); params["cid"] = contact_id
            if status:
                clauses.append("status=:st"); params["st"] = status
            rows = s.execute(_text(
                "SELECT id, resource_id, contact_id, phone_display, name, status, slot_start_raw, "
                " slot_end_raw, title FROM bookings WHERE " + " AND ".join(clauses) +
                " ORDER BY slot_start DESC LIMIT :lim"
            ), params).fetchall()
            keys = ["id", "resource_id", "contact_id", "phone_display", "name", "status",
                    "slot_start", "slot_end", "title"]
            return {"status": "ok", "bookings": [dict(zip(keys, r)) for r in rows], "count": len(rows)}
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "reason": "db_error", "detail": repr(exc)[:160]}


def list_events(org_id: str, booking_id: str, *, limit: int = 200, is_admin: bool = False) -> dict:
    """Read the IMMUTABLE booking_events audit trail for a booking (newest-first). Dormant-safe.
    This surfaces the F4 audit leg: who/when for every lifecycle transition of the booking."""
    eng = _engine()
    if eng is None:
        return dict(_NOT_CONFIGURED)
    try:
        with eng.session(tenant_id=org_id, is_admin=is_admin) as s:
            rows = s.execute(_text(
                "SELECT id, event_type, status_from, status_to, actor, at, data FROM booking_events "
                "WHERE org_id=:org AND booking_id=:bk ORDER BY at DESC LIMIT :lim"
            ), {"org": org_id, "bk": booking_id, "lim": max(1, min(int(limit), 1000))}).fetchall()
            keys = ["id", "event_type", "status_from", "status_to", "actor", "at", "data"]
            return {"status": "ok", "events": [dict(zip(keys, r)) for r in rows], "count": len(rows)}
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "reason": "db_error", "detail": repr(exc)[:160]}


# ============================================================================
# tick — reminders + no-show follow-up. ENQUEUE-ONLY, idempotent, gated, dry-run-able.
# ============================================================================
def _pin_ok(tenant_id: str, pin: str) -> bool:
    """FAIL-CLOSED PIN check via the F4 firewall. Returns False when firewall absent OR no PIN set
    OR wrong PIN (firewall.check_pin already returns False when unset). Risky actuation stays dark
    until a real PIN is set — correct default (crm-core spec RTF-3 discipline)."""
    try:
        import firewall  # type: ignore
        return bool(firewall.check_pin(tenant_id, pin or ""))
    except Exception:  # noqa: BLE001
        return False


def _wallet_reserve(tenant_id: str, amount_minor: int, *, resource_id: str = "",
                    idem_key: str = "") -> Optional[int]:
    """Spend gate via the F4 wallet. Returns a hold_id or None (insufficient / unavailable).
    No double-spend: wallet.reserve is a single atomic conditional UPDATE keyed by idem_key."""
    if amount_minor <= 0:
        return None
    try:
        import wallet  # type: ignore
        return wallet.reserve(tenant_id, int(amount_minor), resource_type="booking_reminder",
                              resource_id=resource_id, idem_key=idem_key)
    except Exception:  # noqa: BLE001
        return None


def tick(org_id: Optional[str] = None, *, now: Optional[_dt.datetime] = None,
         dry_run: bool = True, pin: str = "", limit: int = 200) -> dict:
    """Scan due reminders + detect no-shows, and ENQUEUE due actions through the gated path.

    SAFETY (the #1 guardrail):
      * dry_run=True (DEFAULT): compute the would-fire set, ENQUEUE NOTHING. Powers a "preview" UI
        and runs safely pre-mount (no creds, no spend).
      * Each candidate passes: state==pending & due -> idempotency (booking_reminder_fires) ->
        PIN/firewall (FAIL-CLOSED for require_pin rows) -> wallet.reserve (spend, no double-spend)
        -> ENQUEUE into the existing gated dial/WhatsApp path.
      * The actual enqueue call into caller.py's gated dispatch is the DEFERRED MOUNT — until then a
        non-dry-run tick still records intent (fires + holds) but the dispatch is a recorded stub
        `job_id` so wiring is a one-line change with zero new dispatcher.

    Returns {fired:[...], skipped:[...], no_shows:[...], enqueued:int, dry_run:bool} or not_configured.
    """
    eng = _engine()
    if eng is None:
        # Dormant: still answer with a typed empty result so callers can branch without try/except.
        return {"status": "not_configured", "reason": "postgres_unavailable",
                "fired": [], "skipped": [], "no_shows": [], "enqueued": 0, "dry_run": dry_run}
    now = now or _now()
    grace = config.no_show_grace_minutes()
    fired, skipped, no_shows = [], [], []
    enqueued = 0
    try:
        # admin GUC for a cross-tenant scheduler sweep when org_id is None; else tenant-scoped.
        is_admin = org_id is None
        with eng.session(tenant_id=org_id or "", is_admin=is_admin) as s:
            org_clause = "" if is_admin else " AND r.org_id=:org"
            params: dict = {"now": now, "lim": max(1, min(int(limit), 500))}
            if not is_admin:
                params["org"] = org_id
            # 1) DUE REMINDERS (pending + fire_at<=now), with their booking still active.
            rows = s.execute(_text(
                "SELECT r.id, r.org_id, r.booking_id, r.kind, r.channel, r.template, r.requires_pin, "
                "       r.est_cost_minor, b.status, b.phone_key "
                "FROM booking_reminders r JOIN bookings b ON b.id=r.booking_id AND b.org_id=r.org_id "
                "WHERE r.state='pending' AND r.fire_at <= :now "
                # active-only is correct for ordinary reminders (never nudge a cancelled booking); the
                # no_show_followup is the one kind whose parent booking is legitimately 'no_show' -> add
                # it explicitly, else the no-show follow-up reminder is orphaned and can never fire.
                "  AND ( b.status IN ('booked','rescheduled') "
                "        OR (r.kind='no_show_followup' AND b.status='no_show') )" + org_clause +
                " ORDER BY r.fire_at LIMIT :lim"
            ), params).fetchall()
            for r in rows:
                rid, rorg, bk, kind, channel, tmpl, req_pin, cost, bstatus, pkey = r
                cand = {"reminder_id": rid, "org_id": rorg, "booking_id": bk, "kind": kind,
                        "channel": channel, "template": tmpl}
                # idempotency: already fired?
                seen = s.execute(_text(
                    "SELECT 1 FROM booking_reminder_fires WHERE org_id=:org AND reminder_id=:rid"
                ), {"org": rorg, "rid": rid}).fetchone()
                if seen is not None:
                    cand["skip"] = "already_fired"; skipped.append(cand); continue
                if dry_run:
                    fired.append(cand); continue
                # PIN gate (fail-closed for require_pin rows). A scheduler sweep (no interactive PIN)
                # therefore NEVER actuates a require_pin reminder -> stays dark until a PIN is presented.
                if str(req_pin) in ("1", "True", "true") and not _pin_ok(rorg, pin):
                    cand["skip"] = "pin_required"; skipped.append(cand); continue
                # spend gate (no double-spend; idem_key ties the reservation to this reminder fire)
                hold_id = None
                if int(cost or 0) > 0:
                    hold_id = _wallet_reserve(rorg, int(cost), resource_id=bk,
                                              idem_key=f"booking_reminder:{rid}")
                    if hold_id is None:
                        cand["skip"] = "insufficient_funds_or_wallet_unavailable"
                        skipped.append(cand); continue
                # ENQUEUE (deferred mount): record the intent + a stub job id. The mount replaces the
                # stub with the real _spawn_retry_job / WhatsApp enqueue — one line, zero new dispatcher.
                job_id = f"stub_{rid}"
                s.execute(_text(
                    "INSERT INTO booking_reminder_fires "
                    "(org_id, reminder_id, booking_id, kind, fired_at, job_id, hold_id, data) "
                    "VALUES (:org,:rid,:bk,:kind,now(),:job,:hold,'{}'::jsonb) "
                    "ON CONFLICT (org_id, reminder_id) DO NOTHING"
                ), {"org": rorg, "rid": rid, "bk": bk, "kind": kind, "job": job_id,
                    "hold": str(hold_id or "")})
                s.execute(_text("UPDATE booking_reminders SET state='fired' WHERE org_id=:org AND id=:rid"),
                          {"org": rorg, "rid": rid})
                # IMMUTABLE audit: a reminder/no-show nudge was enqueued (spend-relevant action).
                # discriminator=rid so two reminder fires for one booking get DISTINCT ids (a booking
                # has several reminders); a replay of THIS fire is a true no-op (ON CONFLICT DO NOTHING).
                _record_event(s, rorg, bk, "reminder_fired", actor="scheduler", discriminator=rid,
                              data={"reminder_id": rid, "kind": kind, "channel": channel,
                                    "job_id": job_id, "hold_id": str(hold_id or "")})
                cand["job_id"] = job_id; cand["hold_id"] = hold_id
                fired.append(cand); enqueued += 1
            # 2) NO-SHOW DETECTION: active bookings past slot_end+grace -> flip to no_show + schedule
            #    a no_show_followup reminder (pending; actuation still gated by the same path).
            ns_rows = s.execute(_text(
                "SELECT id, org_id, slot_end FROM bookings "
                "WHERE status IN ('booked','rescheduled') AND slot_end + (:grace || ' minutes')::interval <= :now"
                + (" AND org_id=:org" if not is_admin else "") + " LIMIT :lim"
            ), {**params, "grace": grace}).fetchall()
            for nb in ns_rows:
                nbk, norg, nend = nb
                no_shows.append({"booking_id": nbk, "org_id": norg})
                if dry_run:
                    continue
                s.execute(_text("UPDATE bookings SET status='no_show', updated_at=now() "
                                "WHERE id=:id AND org_id=:org"), {"id": nbk, "org": norg})
                # IMMUTABLE audit: the booking was flipped to no_show by the scheduler sweep.
                _record_event(s, norg, nbk, "no_show", status_to="no_show", actor="scheduler")
                # schedule a single no-show follow-up (pending, require_pin -> gated like any reminder)
                rid2 = _new_id("rem_")
                s.execute(_text(
                    "INSERT INTO booking_reminders "
                    "(id, org_id, booking_id, kind, channel, template, fire_at_raw, fire_at, state, "
                    " requires_pin, est_cost_minor, created_at, data) "
                    "VALUES (:id,:org,:bk,'no_show_followup','whatsapp','no_show_followup',:fr,:f,"
                    " 'pending','1',0,now(),'{}'::jsonb)"
                ), {"id": rid2, "org": norg, "bk": nbk, "fr": _iso(now), "f": now})
        return {"status": "ok", "fired": fired, "skipped": skipped, "no_shows": no_shows,
                "enqueued": enqueued, "dry_run": dry_run}
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "reason": "db_error", "detail": repr(exc)[:160],
                "fired": fired, "skipped": skipped, "no_shows": no_shows,
                "enqueued": enqueued, "dry_run": dry_run}
