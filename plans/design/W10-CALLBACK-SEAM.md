# W10 — Smart Callback/Retry CADENCE engine: the caller.py SEAM + re-enable

Status: **SEAM NOTE ONLY — NOTHING WIRED.** This wave built + tested the
`voice_ops/callback/` cadence engine against an in-memory store (19 W10 tests +
422 total green across `voice_ops/` + `voice_kernel/`). The earner is
byte-identical: `droplet_work/agent.py` md5 = `98655dbf` (unchanged); `caller.py`
NOT edited. The auto-dial scheduler stays **KILLED** (`RETRY_SCHEDULER_ENABLED=0`,
caller.py:273) until the founder-signed wiring wave below.

This file is the precise, file:line recipe for that SEPARATE wiring wave — one
box-mutating change, real-flow smoke, immediate revert.

---

## 0. The founder problem this closes

The old flat `var/retry_queue.json` scheduler redialed leads ~every 2h, 10-11×
a night, even after a successful pickup. Root causes (from the EXPLORE bug map):

| # | caller.py | Bug |
|---|-----------|-----|
| A | `:2756-2759` | `callback_at` enqueued on ANY outcome incl `answered` — redial after pickup |
| B | `:2755`+`:1637` | `attempts` read from `it["attempt"]` (always 0); upsert RESET it each tick → `attempts<max` never tripped → infinite |
| C | `:7285-7289` | recon sweep: same as A — no outcome guard on `callback_at` |
| D | `:7294-7296` | recon sweep hardcoded `attempts=1` every 60s tick for lingering calls |
| E | `:7241-7250` | dial loop: no `attempts < max` guard before firing `_spawn_retry_job` |
| F | `:2754`/`:7284` | backoff `[120,360,1440]` — every-2h first retry, no warm cadence |

The fix is ONE cohesive state machine in `voice_ops/callback/` that owns every
guard in one place — `caller.py` gains only **3 import + delegation points**, no
logic.

---

## 1. What exists now (the built surface)

`voice_ops/callback/` (git-tracked, disjoint from gitignored `droplet_work/`,
ZERO droplet/agent imports — verified):

- `config.py` — `CallbackConfig` (env + per-tenant `for_tenant(overrides)`):
  cadence `[0,1440,4320,10080,20160,43200]` (D0/1/3/7/14/30 mins from arrival),
  `max_retries=2`, `busy_retry_mins=25`, `max_busy_per_day=1`, DND 21:00-09:00
  IST, `min_gap_mins=120`. Master flag `CALLBACK_CADENCE_ENABLED` (default OFF).
- `store.py` — `CallbackStore` Protocol + `InMemoryCallbackStore`. Dedup key
  `(tenant_id, phone)`; idempotent upsert that **never resets `attempts`**;
  `record_attempt` is the ONLY ++ path (monotonic); sticky terminal status
  (`CALLED`/`EXPIRED`/`OPT_OUT`); per-lead TTL **lock** (single dialer). A LATER
  wave adds `PgCallbackStore` (FORCE-RLS `callback_queue`, mirrors `wallet.py`)
  implementing the SAME Protocol — the engine never changes.
- `intent.py` — `parse_callback_time("5pm" | "tomorrow morning" | "4 baje" |
  "sunday")` → exact ISO UTC instant (in IST), or `None` (→ fall back to
  cadence, never a wrong-time spam).
- `cadence.py` — `enqueue_smart(...)`: the post-call decide+persist state machine
  (outcome guard, attempts from store, dedup, DND, context carry, emit
  `callback_scheduled`).
- `scheduler.py` — `fire_due(...)`: the dial-side; due-check + max-retries guard +
  terminal guard + lead-lock + DND defer + priority ordering; returns
  `DialJob`s carrying `last_summary` for W7 continuity. `release(...)` unlocks.

### The behavior, vs the 6 bugs
1. **No-redial after pickup (A,C):** a `REACHED` outcome (`answered/connected/
   completed/interested/qualified/booked/converted`) marks the lead `CALLED`
   (sticky) and schedules **nothing**. A recon tick on a `CALLED` lead returns
   `None`. fire_due never yields a `CALLED` lead.
2. **Monotonic attempts (B,D):** `attempts` lives only in the store, ++ only by
   `record_attempt` (called in fire_due at dial time). `enqueue_smart` reads the
   PERSISTED count, never `it["attempt"]`; a re-enqueue / recon tick CANNOT reset
   it. Regression-locked by `test_regression_recon_tick_never_resets_attempts`
   (50 recon ticks → attempts monotonic → `EXPIRED`, not infinite).
3. **Hard cap (E,F):** after `max_retries` scheduler dials with no connect the
   lead is `EXPIRED` (the loop's hard end). Offsets come from the warm cadence
   array, never a flat 120-min backoff.
4. **Busy → ONE short reschedule:** `busy` → `busy_retry_mins` (25), capped at
   `max_busy_per_day`; busy is NOT a cadence attempt; a 2nd same-day busy falls
   through to the cadence advance.
5. **"Call me at X" = highest priority:** parsed to an exact-time, `priority=True`
   callback — honored even after a pickup (customer intent), exempt from the
   cadence cap, but still obeys the lock + DND. Never re-opens `OPT_OUT`/`EXPIRED`.
6. **Dedup + lock:** one pending entry per `(tenant,phone)`; `try_lock` makes a
   concurrent two-number race yield exactly one dial.

---

## 2. The gate (default OFF — stays OFF until the wiring wave)

`CallbackConfig.from_env()` reads `CALLBACK_CADENCE_ENABLED` (default `"0"`). The
delegation points below ALSO sit behind the existing `RETRY_SCHEDULER_ENABLED`
gate (caller.py:273) so BOTH must be `1` to dial. Put both flags in the **systemd
drop-in** for the voice box, **never the shared `.env`** (LEARNINGS §2: a
shared-`.env` flag leaks across inbound + the outbound earner on restart).

Re-enable order (the safe sequence):
1. Wire the 3 seam points below + a module-level singleton store/config/bus.
2. Deploy caller.py to the box (root-owned: scp → `sudo cp` → restart).
3. Confirm a real outbound call RINGS (earner regression gate) with both flags
   still `0` — proves the additive code is inert.
4. Flip `CALLBACK_CADENCE_ENABLED=1` first (engine schedules, but
   `RETRY_SCHEDULER_ENABLED=0` means nothing dials) — watch the queue fill
   CORRECTLY (cadence times, no answered-call entries, attempts monotonic).
5. Only then flip `RETRY_SCHEDULER_ENABLED=1` to let `fire_due` dial. Watch the
   first cadence dial fire at the RIGHT time (D1, not +2h), and a pickup leave
   `CALLED` with no redial.

Revert = both flags back to `0` + restart → `_STORE`/`fire_due` never engage →
byte-identical to today. (caller.py backup `caller.py.bak.20260616-041519` on box.)

---

## 3. Module-level singletons (top of caller.py, NOT inside the loop)

```python
# near the other singletons in caller.py:
from voice_ops.callback import (CallbackConfig, InMemoryCallbackStore,
                                 enqueue_smart, fire_due, release)  # type: ignore
_CB_CFG = CallbackConfig.from_env()
# V1 store = the in-memory impl (process-local). A LATER wave swaps in
# PgCallbackStore(engine) for durability across restarts — same Protocol.
_CB_STORE = InMemoryCallbackStore() if _CB_CFG.enabled else None
# reuse the W8 event bus singleton if EVENTBUS_ENABLED, else None (no emits).
_CB_BUS = _EVBUS if 'globals().get("_EVBUS")' else None
```

---

## 4. Patch 1 — `_finalize_call` enqueue block (caller.py:2752-2768)

REPLACE the existing `cb = tr.get("callback_at")` / `_enqueue_retry(...)` block
(bugs A + B) with ONE delegation. `outcome` is already set at :2731-2732; pass it.

```python
# OLD (delete bugs A+B): the unguarded callback_at enqueue + attempts=it["attempt"].
# NEW:
if _CB_STORE is not None:
    try:
        await enqueue_smart(
            tenant_id, cid, rec, tr, outcome,
            int(it.get("attempt", 0)),         # hint only; store count is authoritative
            camp_fields,
            store=_CB_STORE, config=_CB_CFG, bus=_CB_BUS,
        )
    except Exception:
        pass   # an enqueue can NEVER break the call-finalize path
```

`rec` must carry `phone` (it does — the dial record) and ideally `id`/`summary`.
The engine reads `tr.get("callback_at")` for the "call me at X" intent and
`tr.get("summary")`/`rec.get("summary")` for W7 continuity carry-over.

---

## 5. Patch 2 — `scheduler_loop` dial block (caller.py:7241-7250)

REPLACE the `due = [...] ; for r in due: _spawn_retry_job(r); _remove_retry(...)`
block (bug E) with the guarded `fire_due` (it owns due-check, max-retries,
terminal skip, lock, DND, priority order):

```python
if RETRY_SCHEDULER_ENABLED and _CB_STORE is not None:
    try:
        for job in await fire_due(store=_CB_STORE, config=_CB_CFG, bus=_CB_BUS):
            # hand the job to the EXISTING dialer. Map DialJob -> _spawn_retry_job's
            # dict shape; carry last_summary so the agent opens with continuity (W7).
            _spawn_retry_job({
                "id": f"{job.tenant_id}:{job.phone}",
                "tenant_id": job.tenant_id, "campaign_id": job.campaign_id,
                "phone": job.phone, "name": "", "attempt": job.attempt,
                "reason": job.reason, "recap": job.last_summary,
            })
    except Exception:
        pass
```

`fire_due` has ALREADY incremented `attempts` (record_attempt) and flipped the
lead to `IN_FLIGHT` + locked it before returning the job — so a concurrent tick or
recon can't re-pick it. The dialer's own finalize (Patch 1) reports the outcome
back through `enqueue_smart`, and MUST call `release(_CB_STORE, tenant_id, phone)`
in a `finally` after the dial completes (the lock TTL also self-heals).

---

## 6. Patch 3 — reconciliation-sweep enqueue (caller.py:7282-7297)

REPLACE the recon-sweep `cb = tr.get("callback_at")` / `no_answer`
`_enqueue_retry(...attempts=1...)` block (bugs C + D) with the SAME delegation as
Patch 1, flagged `from_reconcile=True`:

```python
if _CB_STORE is not None:
    try:
        await enqueue_smart(
            tid, cid, c, tr, outcome, 0, camp_fields,
            store=_CB_STORE, config=_CB_CFG, bus=_CB_BUS, from_reconcile=True,
        )
    except Exception:
        pass
```

The engine is idempotent: re-running for the same finalized call yields the same
state (attempts preserved, terminal sticky), so a recon tick can NEVER reset the
counter or re-enqueue an answered/opted-out lead. This is the exact path the old
attempts→1 loop lived in; it is now structurally impossible.

---

## 7. Frontend control (tenant-tunable + disable)

The panel already has bare `retryMax` / `retryBackoff` fields on the campaign edit
drawer (`famit-panel/app/campaigns/page.tsx:456-482`). The tenant-tuning path is a
`callback_overrides` dict on the campaign `fields` (or a tenant-level default),
read by `CallbackConfig.for_tenant(overrides)` at enqueue time:

```json
{ "callback_overrides": {
    "enabled": false,                       // tenant disables auto-callback entirely
    "cadence_mins": [0, 1440, 4320],        // tenant's custom warm cadence
    "max_retries": 1,                       // tenant caps retries
    "busy_retry_mins": 30, "max_busy_per_day": 1,
    "dnd_start_hour": 21, "dnd_end_hour": 9
} }
```

A broken/missing override is fail-safe — bad values fall back to the base config
(a tenant setting can NEVER widen the cadence into spam). The matching frontend
wave should replace the raw `retryBackoff` text box with a proper "Follow-up
cadence" control (preset warm-lead curve + per-day cap + DND window + a master
on/off), persisted into `callback_overrides`. This delivers the founder's
"tenant can tune/disable" requirement with full CRUD.

---

## 8. Smoke + revert (the wiring wave's DoD)

- Real outbound call RINGS before AND after (the earner regression gate).
- `/proc/<pid>/environ` shows `CALLBACK_CADENCE_ENABLED` only on the voice box.
- With cadence ON + scheduler ON: a no-answer schedules the NEXT dial at **D1**
  (not +2h); a pickup leaves the lead `CALLED` with **zero** redials; "call me at
  5pm" dials at ~17:00 IST; a 2nd dial never fires before the min-gap; the lead
  `EXPIRES` after `max_retries` (queue does not refill).
- `agent.py` md5 still `98655dbf`; caller.py diff = only the 3 delegation blocks +
  the singleton lines.
- Revert = both flags → `0` + restart (or restore the box caller.py backup) →
  byte-identical to today.

---

## 9. Quick file map (what to read for the splice)
- `voice_ops/callback/cadence.py::enqueue_smart` — Patches 1 + 3
- `voice_ops/callback/scheduler.py::fire_due` / `release` — Patch 2
- `voice_ops/callback/config.py::CallbackConfig.for_tenant` — §7 tenant tuning
- `voice_ops/callback/intent.py::parse_callback_time` — "call me at X"
- `voice_ops/callback/store.py::CallbackStore` — the Protocol a `PgCallbackStore`
  must implement for durability (FORCE-RLS `callback_queue`, mirrors `wallet.py`)
- `voice_ops/tests/test_callback_cadence.py` — the 19 behavioral proofs
- `CALLBACK_SCHEDULER_REBUILD_STATE.md` — the kill-switch + box deploy/revert recipe
