"""voice_ops.callback.scheduler — fire_due: the dial-side of the cadence engine.

This replaces caller.py's `scheduler_loop` due-block (7241-7250) whose only fault
was: NO `attempts < max` guard, and it re-enqueued via the buggy `_finalize_call`
so the entry came straight back (bug E). `fire_due` owns every guard the old loop
lacked, in ONE place:

  * MAX-ATTEMPTS guard — a lead at/over `max_cadence_touches` is TERMINATED
    (EXPIRED), never dialed again (the hard end of the loop);
  * TERMINAL guard — CALLED / OPT_OUT entries are skipped (no redial after pickup);
  * LEAD LOCK — `try_lock` ensures only ONE worker dials a given lead at a time,
    so the same lead is never dialed by two SIP numbers concurrently (dedup);
  * DND window — a due entry whose time is (now) inside quiet hours is re-deferred
    to the next 09:00 IST instead of dialed;
  * PRIORITY ordering — explicit 'call me at X' entries fire first;
  * CONTEXT CARRY — each fired job carries `last_summary` so the dialer can open
    with continuity (W7), never from zero.

`fire_due` does NOT itself place a SIP call. It returns a list of `DialJob`s the
caller.py seam hands to the existing `_spawn_retry_job` / dialer. record_attempt is
called HERE (the only attempts++ site) so the persisted counter is authoritative
and a re-enqueue can never reset it. Each fired lead is locked and marked IN_FLIGHT
before the job is returned; the dialer unlocks + reports the outcome back through
`enqueue_smart`, closing the loop.

ZERO droplet_work / agent imports. The store + config + bus are injected.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from voice_kernel.events.timeutil import now_utc, now_utc_iso, parse_iso

from .config import CallbackConfig
from .store import EXPIRED, IN_FLIGHT, PENDING, TERMINAL, CallbackStore

log = logging.getLogger("voice_ops.callback.scheduler")


@dataclass
class DialJob:
    """One ready-to-dial job handed back to the caller.py dialer seam. Mirrors the
    minimal fields `_spawn_retry_job` needs, PLUS `last_summary` for continuity."""

    tenant_id: str
    phone: str
    campaign_id: str
    lead_id: str
    attempt: int                 # the persisted, monotonic attempt number (post-increment)
    reason: str
    priority: bool
    last_summary: str            # carry prior context into the callback (W7)


async def fire_due(
    *,
    store: CallbackStore,
    config: Optional[CallbackConfig] = None,
    bus=None,
    now: Optional[str] = None,
    lock_ttl_s: int = 300,
    limit: int = 200,
) -> list[DialJob]:
    """Return the DialJobs that should be dialed right now. Enforces every guard.
    Safe to call on a fixed timer (the caller.py scheduler_loop tick). Idempotent
    within a tick window: a lead already IN_FLIGHT (locked) is skipped.

    The caller.py seam:
        if RETRY_SCHEDULER_ENABLED:
            for job in await fire_due(store=_STORE, config=_CFG, bus=_BUS):
                _spawn_retry_job(job)          # existing dialer
    """
    cfg = config or CallbackConfig.from_env()
    if not cfg.enabled:
        return []

    now_iso = now or now_utc_iso()
    jobs: list[DialJob] = []
    due = await store.due_entries(now_iso)

    for entry in due:
        if len(jobs) >= limit:
            break
        # per-tenant tuning (disable / custom cadence) layered in.
        # (the override dict isn't on the entry; tenant disable is handled at
        #  enqueue time + via cfg.enabled — here we honor the global/derived cfg.)

        # TERMINAL guard — never dial a reached / opted-out / expired lead.
        if entry.status in TERMINAL:
            continue
        if entry.status != PENDING:
            continue

        # MAX-ATTEMPTS guard — the hard end of the loop. `attempts` counts every
        # dial already completed (record_attempt is the single ++ site and fires
        # for BOTH cadence and priority dials). A normal cadence lead is EXPIRED at
        # `max_retries`. A priority 'call me at X' is EXEMPT from the *cadence* cap
        # (the customer asked for it explicitly) — BUT it is NOT unbounded: a stale
        # or repeatedly-resupplied callback_at would otherwise dial forever (a
        # priority-gated re-incarnation of the original runaway-spam bug). So a
        # priority lead is bounded by an ABSOLUTE ceiling `max_priority_dials`
        # (default 3). Past either cap -> EXPIRED, never dialed again. Both still
        # obey the lock + DND below.
        cap = cfg.max_priority_dials if entry.priority else cfg.max_retries
        if entry.attempts >= cap:
            await store.terminate(entry.tenant_id, entry.phone, EXPIRED)
            continue

        # DND window — if NOW is inside quiet hours, defer to next 09:00 IST and
        # do NOT dial this tick (re-persist the deferred time).
        if _in_quiet_now(cfg, now_iso):
            deferred = _next_window_open(cfg, now_iso)
            if deferred != entry.next_attempt_at:
                from .store import CallbackEntry
                await store.upsert(CallbackEntry(
                    tenant_id=entry.tenant_id, phone=entry.phone,
                    campaign_id=entry.campaign_id, lead_id=entry.lead_id,
                    status=PENDING, next_attempt_at=deferred,
                    touch_index=entry.touch_index, priority=entry.priority,
                    reason=entry.reason, last_summary=entry.last_summary,
                ))
            continue

        # LEAD LOCK — single dialer per lead (no double-dial / two-number race).
        if not await store.try_lock(entry.tenant_id, entry.phone, ttl_s=lock_ttl_s):
            continue

        # increment the AUTHORITATIVE attempts counter (the only ++ site) and
        # flip to IN_FLIGHT so a concurrent tick / recon can't re-pick it.
        new_attempts = await store.record_attempt(entry.tenant_id, entry.phone)

        jobs.append(DialJob(
            tenant_id=entry.tenant_id,
            phone=entry.phone,
            campaign_id=entry.campaign_id,
            lead_id=entry.lead_id,
            attempt=new_attempts,
            reason=entry.reason,
            priority=entry.priority,
            last_summary=entry.last_summary,
        ))

    return jobs


async def release(store: CallbackStore, tenant_id: str, phone: str) -> None:
    """Unlock a lead after the dialer finishes (success path calls enqueue_smart
    to set the next state; this just drops the dial lock). Always call in a
    finally so a crashed dial never leaves a lead permanently locked (the TTL also
    self-heals, but explicit release is faster)."""
    try:
        await store.unlock(tenant_id, phone)
    except Exception as exc:
        log.debug("release unlock skipped (non-fatal): %r", exc)


# --------------------------------------------------------------------------- #
# DND helpers (shared shape with cadence._apply_dnd, kept local to avoid a
# circular import; both compute the SAME window).
# --------------------------------------------------------------------------- #
def _in_quiet_now(cfg: CallbackConfig, now_iso: str) -> bool:
    from voice_kernel.events.timeutil import _tz
    tz = _tz(cfg.tz_name)
    h = parse_iso(now_iso).astimezone(tz).hour
    start, end = cfg.dnd_start_hour, cfg.dnd_end_hour
    return (h >= start or h < end) if start > end else (start <= h < end)


def _next_window_open(cfg: CallbackConfig, now_iso: str) -> str:
    from datetime import timedelta, timezone
    from voice_kernel.events.timeutil import _tz
    tz = _tz(cfg.tz_name)
    local = parse_iso(now_iso).astimezone(tz)
    start, end = cfg.dnd_start_hour, cfg.dnd_end_hour
    target = local.replace(hour=end, minute=0, second=0, microsecond=0)
    if start > end and local.hour >= start:
        target = target + timedelta(days=1)
    return target.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
