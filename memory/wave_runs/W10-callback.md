# W10 — Smart Callback/Retry CADENCE engine (BUILD wave)

**Wave:** W10-callback (build + test only; NOTHING wired to live)
**Status:** ✅ SUCCESS — `voice_ops/callback/` built + 21 W10 tests + 254 total green
(`voice_ops/` + `voice_kernel/`). Engine is INERT (default OFF) until the seam wave.
**VERIFY+COMMIT (W10, red-team folded):** 21/21 callback + 254/254 suite green; agent.py
md5 `98655dbf` unchanged; caller.py untouched; gitleaks staged = 0; zero droplet/livekit/
boto3/asyncpg/redis imports in the package. Red-team blocker FIXED (see below).

## RED-TEAM FOLD (one real runaway vector found + fixed)
**Blocker:** priority `call me at X` callbacks bypassed the attempts cap entirely
(`scheduler.py:106` exempted `priority=True` with no other ceiling) → a stale/repeatedly-
resupplied `callback_at` re-armed a priority entry every tick → unbounded dials (a
priority-gated re-incarnation of the killed runaway-spam bug). **Fix:** added absolute
`max_priority_dials` ceiling (default 3, env `CALLBACK_MAX_PRIORITY_DIALS`, tenant-clamped)
enforced in `fire_due` (`scheduler.py:106-109`, `config.py:92/107`); storm now caps at 3 →
EXPIRED. **Defense-in-depth:** `config.for_tenant` clamps so a tenant override can only make
cadence SAFER (min_gap never below base, max_retries/max_priority_dials never above base).
Two new permanent regressions: `test_priority_callback_storm_is_bounded`,
`test_tenant_override_cannot_widen_into_spam`.
**Branch:** fix/realtime-voice-kernel-v2
**Earner gate:** `droplet_work/agent.py` md5 = `98655dbf` UNCHANGED; `caller.py` NOT
edited (patch DOC only). Auto-dial scheduler stays KILLED (`RETRY_SCHEDULER_ENABLED=0`,
caller.py:273) until the founder-signed wiring wave in `design/W10-CALLBACK-SEAM.md`.

---

## What this closes (the runaway-spam hotfix 6aa1f32)

The old flat `var/retry_queue.json` scheduler redialed ~every 2h, 10-11×/night,
even after pickup. The 6 root bugs (EXPLORE map) and how the rebuild kills each:

| # | caller.py | Bug | Fix in voice_ops/callback |
|---|-----------|-----|----------------------------|
| A | :2756 | callback_at enqueued on ANY outcome incl answered | outcome guard → REACHED ⇒ mark CALLED, schedule nothing |
| B | :2755+:1637 | attempts read from it["attempt"]=0; upsert reset → infinite | attempts live in store, ++ only via record_attempt (monotonic); upsert NEVER resets |
| C | :7285 | recon sweep same as A | same outcome guard via enqueue_smart(from_reconcile=True) |
| D | :7294 | recon hardcoded attempts=1 every 60s tick | idempotent re-enqueue preserves attempts; recon can't reset |
| E | :7241 | dial loop no attempts<max guard | fire_due caps at max_retries → EXPIRED (hard loop end) |
| F | :2754/:7284 | backoff [120,360,1440], every-2h | warm cadence [0,1440,4320,10080,20160,43200] = D0/1/3/7/14/30 |

## Files built (git-tracked, disjoint from gitignored droplet_work/)

- `voice_ops/callback/config.py` — `CallbackConfig` (env + per-tenant `for_tenant`);
  cadence D0/1/3/7/14/30, `max_retries=2`, busy 25min/1-per-day, DND 21-09 IST,
  min_gap 120, master flag `CALLBACK_CADENCE_ENABLED` (default OFF).
- `voice_ops/callback/store.py` — `CallbackStore` Protocol + `InMemoryCallbackStore`:
  dedup key (tenant,phone), idempotent upsert (no attempts reset), monotonic
  `record_attempt`, sticky terminal (CALLED/EXPIRED/OPT_OUT), per-lead TTL lock.
- `voice_ops/callback/intent.py` — `parse_callback_time` ("5pm"/"tomorrow"/"4 baje"/
  "sunday" → exact ISO IST→UTC, or None → fall back to cadence).
- `voice_ops/callback/cadence.py` — `enqueue_smart`: the post-call state machine
  (outcome guard, attempts-from-store, dedup, DND, context carry, emit callback_scheduled).
- `voice_ops/callback/scheduler.py` — `fire_due` (due + max-retries + terminal + lock
  + DND defer + priority order; returns DialJob w/ last_summary) + `release`.
- `voice_ops/callback/__init__.py` — public surface.
- `voice_ops/tests/{__init__,conftest}.py` + `test_callback_cadence.py` — 21 tests.
- `design/W10-CALLBACK-SEAM.md` — the caller.py 3-point patch DOC + re-enable order.

## Tests (21, all green)
cadence advances D1→D3 anchored to arrival; never exceeds max_retries (drives the
FULL fire_due loop → EXPIRED, dialed ≤ max_retries); fire_due caps+expires;
no-redial-after-answer (incl recon tick on CALLED); answered + "call me at X" still
honored; "5pm" → 17:00 IST + fires first (priority); natural-time parse (5pm/tomorrow/
4 baje→16:00/past-rolls-tomorrow/sunday/garbage→None); ISO passthrough; busy → ~25min
short reschedule (not 120) + capped per day → 2nd busy falls to cadence; dedup single
entry; lead-lock single dialer under concurrent ticks; opt-out terminal (callback_at
can't re-open); **REGRESSION: 50 recon ticks → attempts monotonic → EXPIRED (old
reset-to-1 loop structurally impossible)**; disabled engine = no-op; tenant disable +
tenant tune via callback_overrides; DND pushes into business hours; fire_due defers in
quiet hours.

## Isolation proof
`import voice_ops.callback` pulls only stdlib + voice_kernel — ZERO droplet/agent/
caller/livekit/boto3/asyncpg/redis at module load (verified programmatically).

## Reuse
- W8 EventBus: emits `callback_scheduled` (taxonomy factory) via the injected bus.
- W8 timeutil: all timestamps UTC-canonical; DND window computed in IST (Asia/Kolkata
  with fixed +05:30 fallback).
- W7 continuity: `DialJob.last_summary` carries prior-call context into the callback
  (the seam maps it to caller.py's `recap`/_build_sales_instructions path).

## Next (NOT this wave)
1. Wiring wave per `design/W10-CALLBACK-SEAM.md` (3 caller.py delegation points +
   singletons; flags in systemd drop-in; smoke a real ring before/after; flip cadence
   first, scheduler second; revert = flags→0).
2. `PgCallbackStore` (FORCE-RLS `callback_queue`, mirrors wallet.py) for durability
   across restarts — same Protocol, engine unchanged.
3. Frontend: replace the raw `retryBackoff` box (campaigns/page.tsx:456-482) with a
   warm-cadence control writing `callback_overrides` (tenant tune/disable, full CRUD).
