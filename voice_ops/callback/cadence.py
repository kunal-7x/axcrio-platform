"""voice_ops.callback.cadence — the SMART cadence state machine (enqueue side).

This replaces caller.py's `_finalize_call` enqueue block (2752-2768) and the
reconciliation-sweep enqueue (7282-7297). It is the brain that decides, after a
call ends (or a recon sweep finds an un-reconciled call), WHETHER and WHEN to
schedule the next touch — applying every anti-spam rule the old flat queue lacked.

THE OUTCOME GUARD (closes bugs A & C): a connected/answered/interested outcome
means the lead was REACHED. We do NOT schedule a cadence redial — `no-redial
after pickup`. The ONLY thing that survives a pickup is an explicit "call me at X"
commitment (customer intent), which becomes a high-priority exact-time callback.

THE ATTEMPTS RULE (closes bugs B & D): `attempts` lives ONLY in the store and is
incremented ONLY by `record_attempt` (in the scheduler, at dial time). enqueue
NEVER writes attempts — so a re-enqueue / recon tick can never reset it to 0/1 and
re-arm the infinite loop. The next cadence offset is derived from the PERSISTED
attempts, not from the current dial's `it["attempt"]`.

THE CAP (closes bug E + F): a lead that has used up `max_cadence_touches` with no
connect is TERMINATED (EXPIRED) instead of re-queued — the loop has a hard end.
Offsets come from the warm-lead cadence array, never a flat 120-min backoff.

Emits `callback_scheduled` via the W8 EventBus (fire-and-forget, never raises).
Carries `last_summary` for W7 continuity. ZERO droplet_work / agent imports; the
event bus + store are passed in (or lazily built), so importing this module is
cheap and box-free.
"""
from __future__ import annotations

import logging
from typing import Optional

from voice_kernel.events.timeutil import now_utc, now_utc_iso, parse_iso

from .config import CallbackConfig
from .intent import parse_callback_time
from .store import (
    CALLED,
    EXPIRED,
    OPT_OUT,
    PENDING,
    CallbackEntry,
    CallbackStore,
)

log = logging.getLogger("voice_ops.callback.cadence")

# Outcomes that mean the lead was REACHED -> no cadence redial (no-redial rule).
# Mirrors caller.py's notion of a "real conversation"; kept here so the engine is
# self-contained and does not import the live module's constants.
REACHED_OUTCOMES = frozenset({
    "answered", "connected", "completed", "interested", "qualified",
    "booked", "converted", "callback",  # "callback" outcome already reached + scheduled
})
# Outcomes that mean we never call again.
OPT_OUT_OUTCOMES = frozenset({"opted_out", "opt_out", "dnd", "do_not_call", "unsubscribed"})
# Busy -> ONE short reschedule (not a cadence attempt).
BUSY_OUTCOMES = frozenset({"busy", "line_busy"})
# Technical failures -> short technical retry (not a cadence attempt).
TECH_OUTCOMES = frozenset({"failed", "sip_error", "network_error", "error"})
# No-answer family -> advance the warm-lead cadence.
NO_ANSWER_OUTCOMES = frozenset({"no_answer", "noanswer", "ring_timeout", "missed", "voicemail"})


async def _emit_scheduled(bus, entry: CallbackEntry) -> None:
    """Emit `callback_scheduled` (W8). The bus's own emit() is fire-and-forget +
    self-timeouts + never-raises (RedisEventBus contract); we await it (cheap) so
    the event is durably enqueued before we return, and wrap it in try/except so
    an event can NEVER break the call path (LEARNINGS §4)."""
    if bus is None:
        return
    try:
        from voice_kernel.events import callback_scheduled
        ev = callback_scheduled(
            entry.lead_id or entry.phone,
            entry.tenant_id,
            preferred_ts=entry.next_attempt_at,
            attempts=entry.attempts,
            priority=entry.priority,
            reason=entry.reason,
        )
        res = bus.emit(ev)
        import asyncio
        if asyncio.iscoroutine(res):
            await res
    except Exception as exc:  # an event must never break the call (LEARNINGS §4)
        log.debug("callback_scheduled emit skipped (non-fatal): %r", exc)


async def enqueue_smart(
    tenant_id: str,
    campaign_id: str,
    rec: dict,
    tr: dict,
    outcome: str,
    attempt_hint: int,                 # caller.py's it["attempt"] — used ONLY as a floor, never authoritative
    camp_fields: Optional[dict] = None,
    *,
    store: CallbackStore,
    config: Optional[CallbackConfig] = None,
    bus=None,
    from_reconcile: bool = False,
    now: Optional[str] = None,
) -> Optional[CallbackEntry]:
    """Decide + persist the next callback for this lead. Returns the upserted
    entry, or None if nothing was scheduled (reached / disabled / capped / opted
    out). Idempotent: re-running for the same finalized call yields the same state
    (the store upsert preserves attempts; a terminal status is sticky).

    Args mirror the caller.py seam so the splice is a 1-line delegation:
        await enqueue_smart(tenant_id, cid, rec, tr, outcome,
                            int(it.get("attempt", 0)), camp_fields,
                            store=_STORE, config=_CFG, bus=_BUS)
    """
    cfg = (config or CallbackConfig.from_env())
    # tenant-tunable / disable: layer the tenant's panel overrides on top.
    cfg = cfg.for_tenant((camp_fields or {}).get("callback_overrides"))
    if not cfg.enabled:
        return None

    tid = (tenant_id or "").strip()
    phone = (rec.get("phone") or rec.get("to") or rec.get("number") or "").strip()
    if not tid or not phone:
        log.debug("enqueue_smart skipped: blank tenant/phone")
        return None

    oc = (outcome or "").strip().lower()
    lead_id = str(rec.get("id") or rec.get("lead_id") or "")
    summary = (tr.get("summary") or tr.get("last_call_summary") or rec.get("summary") or "").strip()
    now_iso = now or now_utc_iso()

    # Load existing state (single source of truth for attempts / terminal).
    existing = await store.load(tid, phone)

    # ---- 0. HARD-TERMINAL: OPT_OUT / EXPIRED never re-open (not even an explicit
    #         'call me at X' — a lead who opted out is off-limits, full stop). ---- #
    if existing and existing.status in (OPT_OUT, EXPIRED):
        return None

    # ---- 1. OPT-OUT: terminate, never call again --------------------------- #
    if oc in OPT_OUT_OUTCOMES:
        if existing is None:
            # no row yet -> create a sticky terminal row so a later tick can't dial.
            await store.upsert(CallbackEntry(
                tenant_id=tid, phone=phone, campaign_id=str(campaign_id or ""),
                lead_id=lead_id, status=OPT_OUT, reason="opt_out",
                last_summary=summary, last_outcome=oc, created_at=now_iso,
            ))
        else:
            await store.terminate(tid, phone, OPT_OUT)
        return None

    # ---- 2. EXPLICIT 'call me at X' (HIGHEST PRIORITY) --------------------- #
    # Honored even if the call was answered/CALLED — it is the customer's own
    # intent. (OPT_OUT/EXPIRED already returned above, so this can only re-open a
    # PENDING / IN_FLIGHT / CALLED lead — exactly the intended exception.)
    cb_raw = (tr.get("callback_at") or rec.get("callback_at") or "").strip()
    if cb_raw:
        when = parse_callback_time(cb_raw, now=parse_iso(now_iso), tz_name=cfg.tz_name)
        if when:
            entry = CallbackEntry(
                tenant_id=tid, phone=phone, campaign_id=str(campaign_id or ""),
                lead_id=lead_id, status=PENDING,
                touch_index=(existing.touch_index if existing else 0),
                next_attempt_at=when, priority=True, reason="callback",
                last_summary=summary or (existing.last_summary if existing else ""),
                last_outcome=oc,
                created_at=(existing.created_at if existing else now_iso),
            )
            saved = await store.upsert(entry)
            await _emit_scheduled(bus, saved)
            return saved
        # couldn't parse a concrete time -> fall through to normal handling.

    # ---- 2b. Already CALLED (clean pickup, no new commitment) -> no redial. -- #
    # A recon tick / late no-answer finalize on an already-reached lead must NOT
    # re-enqueue (the answered-then-recon path).
    if existing and existing.status == CALLED:
        return None

    # ---- 3. REACHED -> no redial after pickup ------------------------------ #
    if oc in REACHED_OUTCOMES:
        # Mark CALLED so the cadence loop can never redial a reached lead. (An
        # explicit 'call me at X' above already returned; this is a clean pickup.)
        if existing and existing.status not in (CALLED,):
            await store.terminate(tid, phone, CALLED)
        elif not existing:
            # create a sticky CALLED row so a later recon tick can't re-enqueue.
            await store.upsert(CallbackEntry(
                tenant_id=tid, phone=phone, campaign_id=str(campaign_id or ""),
                lead_id=lead_id, status=CALLED, reason="reached",
                last_summary=summary, last_outcome=oc,
            ))
        return None

    # ---- 4. BUSY -> ONE short reschedule (not a cadence attempt) ----------- #
    if oc in BUSY_OUTCOMES:
        # how many busy reschedules have we ALREADY used today? (0 for a new lead).
        used = (existing.busy_today if (existing and existing.busy_day == now_iso[:10]) else 0)
        if used < cfg.max_busy_per_day:
            # ensure a row exists, then BUMP the per-day busy counter (the row's
            # busy_today must reflect THIS reschedule so the next busy is capped).
            if existing is None:
                await store.upsert(CallbackEntry(
                    tenant_id=tid, phone=phone, campaign_id=str(campaign_id or ""),
                    lead_id=lead_id, status=PENDING, last_summary=summary,
                    last_outcome=oc, created_at=now_iso, busy_day=now_iso[:10],
                ))
            await store.record_busy(tid, phone)
            cur = await store.load(tid, phone)
            when = (parse_iso(now_iso) + _mins(cfg.busy_retry_mins)).isoformat().replace("+00:00", "Z")
            when = _apply_dnd(when, cfg)
            entry = CallbackEntry(
                tenant_id=tid, phone=phone, campaign_id=str(campaign_id or ""),
                lead_id=lead_id, status=PENDING,
                touch_index=(cur.touch_index if cur else 0), next_attempt_at=when,
                reason="busy", last_summary=summary or (cur.last_summary if cur else ""),
                last_outcome=oc,
            )
            saved = await store.upsert(entry)
            await _emit_scheduled(bus, saved)
            return saved
        # busy cap hit -> treat as a no-answer cadence advance (fall through).

    # ---- 5. TECHNICAL failure -> short technical retry (not a cadence attempt) #
    if oc in TECH_OUTCOMES:
        when = (parse_iso(now_iso) + _mins(max(5, cfg.busy_retry_mins // 3))).isoformat().replace("+00:00", "Z")
        when = _apply_dnd(when, cfg)
        cur = existing
        entry = CallbackEntry(
            tenant_id=tid, phone=phone, campaign_id=str(campaign_id or ""),
            lead_id=lead_id, status=PENDING,
            touch_index=(cur.touch_index if cur else 0), next_attempt_at=when,
            reason="technical", last_summary=summary or (cur.last_summary if cur else ""),
            last_outcome=oc,
        )
        saved = await store.upsert(entry)
        await _emit_scheduled(bus, saved)
        return saved

    # ---- 6. NO-ANSWER (or busy-cap-exhausted) -> advance the warm cadence -- #
    # MODEL: `attempts` = cadence RETRY dials already completed by the scheduler
    # (fire_due is the ONLY place attempts increments). The initial T0 dial is
    # placed by the live campaign loop, NOT counted here. So:
    #   * a brand-new lead's first no-answer (store attempts=0) schedules retry #1
    #     at cadence offset index 1 (D1);
    #   * after fire_due dials it (attempts->1), the next no-answer schedules
    #     retry #2 at index 2 (D3); and so on.
    # The authoritative count is the PERSISTED store value, NEVER the dial's
    # attempt_hint (reading it["attempt"] was the old reset-to-0 bug B).
    attempts = existing.attempts if existing else 0
    # HARD CAP: max_retries scheduler retries after T0. Once used up -> EXPIRED
    # (the hard end of the loop — no infinite redial).
    if attempts >= cfg.max_retries:
        if existing:
            await store.terminate(tid, phone, EXPIRED)
        return None

    # Next cadence slot index = attempts + 1 (index 0 is T0, already dialed live).
    # Anchor offsets to lead ARRIVAL (created_at) so the cadence is Day-0/1/3/7/14/30
    # from FIRST contact, not from "now of this tick".
    next_touch = attempts + 1
    offset_min = cfg.offset_for(next_touch)
    anchor = parse_iso(existing.created_at) if existing else parse_iso(now_iso)
    when_dt = anchor + _mins(offset_min)
    # never schedule into the past; and never closer than the hard min-gap.
    floor = parse_iso(now_iso) + _mins(cfg.min_gap_mins)
    if when_dt < floor:
        when_dt = floor
    when = _apply_dnd(when_dt.isoformat().replace("+00:00", "Z"), cfg)

    entry = CallbackEntry(
        tenant_id=tid, phone=phone, campaign_id=str(campaign_id or ""),
        lead_id=lead_id, status=PENDING, touch_index=next_touch,
        next_attempt_at=when, reason="cadence",
        last_summary=summary or (existing.last_summary if existing else ""),
        last_outcome=oc,
        # Anchor the cadence on the REFERENCE clock so offsets are stable across
        # ticks: a fresh lead's arrival == now_iso; an existing lead keeps its
        # original arrival (upsert preserves it, but pass it for a no-row path).
        created_at=(existing.created_at if existing else now_iso),
    )
    saved = await store.upsert(entry)
    await _emit_scheduled(bus, saved)
    return saved


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _mins(n):
    from datetime import timedelta
    return timedelta(minutes=int(n))


def _apply_dnd(iso_utc: str, cfg: CallbackConfig) -> str:
    """If the scheduled UTC instant falls inside the vendor's quiet hours
    (default 21:00-09:00 IST), push it forward to the next dnd_end_hour (09:00)
    in the vendor tz. Returns a UTC 'Z' ISO. This is the TRAI 09-21 compliance
    guard — a call is NEVER scheduled into the night."""
    from datetime import timedelta, timezone
    from voice_kernel.events.timeutil import _tz, parse_iso

    tz = _tz(cfg.tz_name)
    local = parse_iso(iso_utc).astimezone(tz)
    start, end = cfg.dnd_start_hour, cfg.dnd_end_hour
    h = local.hour
    # quiet window wraps midnight when start > end (e.g. 21..09).
    in_quiet = (h >= start or h < end) if start > end else (start <= h < end)
    if in_quiet:
        target = local.replace(hour=end, minute=0, second=0, microsecond=0)
        if start > end and h >= start:   # late evening -> 09:00 NEXT day
            target = target + timedelta(days=1)
        local = target
    return local.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
