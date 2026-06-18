"""voice_ops.callback — the SMART callback/retry CADENCE engine (W10).

The disjoint, git-tracked rebuild of the callback/retry scheduler that the
runaway-spam hotfix (commit 6aa1f32) had to KILL (RETRY_SCHEDULER_ENABLED=0,
caller.py:273). The old flat `retry_queue.json` redialed leads ~every 2h, 10-11x a
night, even after a successful pickup, because:
  * callback_at was enqueued on ANY outcome incl ANSWERED (caller.py:2756);
  * `attempts` was read from the dial's `it["attempt"]` (always 0) and the upsert
    RESET it every tick, so the `attempts < max` guard never tripped -> infinite;
  * the recon sweep hardcoded attempts=1 every 60s for lingering calls.

This package is the smart rebuild, as a cohesive state machine that owns every
anti-spam guard in ONE place:
  1. WARM-LEAD cadence Day 0/1/3/7/14/30, hard-capped by max_retries (default 2);
  2. NO redial after a connected/answered call;
  3. busy -> ONE short reschedule (not a 120-min loop);
  4. "call me at 5pm/tomorrow/Sunday" -> EXACT-time, highest-priority callback;
  5. dedup + per-lead LOCK (a lead is never double-dialed / dialed by 2 numbers);
  6. continue-from-prior-context (carry the last summary into the callback);
  7. tenant-tunable + per-tenant disable, idempotent enqueue, W8 event emit.

DISJOINT + additive: imports ONLY from voice_kernel (events/timeutil) — never from
droplet_work, agent.py, or caller.py. Every heavy/box import is LAZY. Inert until a
founder-signed seam wave flips CALLBACK_CADENCE_ENABLED (default OFF). The exact
caller.py splice + re-enable recipe is design/W10-CALLBACK-SEAM.md.

Public surface:
  - CallbackConfig            — cadence + anti-spam knobs (env + per-tenant override)
  - CallbackStore (Protocol)  — the durable store contract
  - InMemoryCallbackStore     — dep-free store (tests + local fallback)
  - CallbackEntry             — one lead's pending-callback record
  - enqueue_smart             — the post-call decide+persist state machine
  - fire_due                  — the dial-side: due-check + every guard, returns DialJobs
  - DialJob                   — one ready-to-dial job (carries last_summary)
  - parse_callback_time       — "call me at X" -> ISO instant
  - status constants          — PENDING / IN_FLIGHT / CALLED / EXPIRED / OPT_OUT
"""
from __future__ import annotations

from .cadence import enqueue_smart
from .config import DEFAULT_CADENCE_MINS, CallbackConfig
from .intent import parse_callback_time
from .scheduler import DialJob, fire_due, release
from .store import (
    CALLED,
    EXPIRED,
    IN_FLIGHT,
    OPT_OUT,
    PENDING,
    TERMINAL,
    CallbackEntry,
    CallbackStore,
    InMemoryCallbackStore,
    lead_key,
)

__all__ = [
    "CallbackConfig",
    "DEFAULT_CADENCE_MINS",
    "CallbackStore",
    "InMemoryCallbackStore",
    "CallbackEntry",
    "enqueue_smart",
    "fire_due",
    "release",
    "DialJob",
    "parse_callback_time",
    "lead_key",
    "PENDING",
    "IN_FLIGHT",
    "CALLED",
    "EXPIRED",
    "OPT_OUT",
    "TERMINAL",
]
