# W24 — Concurrency Admission Control (W18 / C1-NEW-W24)

Branch: `fix/realtime-voice-kernel-v2`. Status: BUILT + RED-TEAM-FOLDED + GREEN +
COMMITTED. Earner untouched (0 droplet/agent imports; default-OFF flag; local agent.py
snapshot md5 `98655dbf` unchanged). Tracked, disjoint code under
`voice_ops/concurrency/`.

## The problem (W18 critical)
The "replace 500 telecallers" thesis is a CONCURRENCY claim the live dial loop never
modeled. A single LiveKit worker = ~10-25 concurrent jobs; the box is single-worker →
perfect on call #1, silently saturates ~call #20-50. The dial loop checks per-job /
per-tenant caps at the 4s tick but NEVER: reserves LLM quota, reserves a TTS slot,
checks worker load, queues/paces when saturated, or bounds GLOBAL cross-tenant
concurrency. First sign of LLM/TTS exhaustion = a 429 mid-call (conversation dies).

## What was built
`voice_ops/concurrency/` (all 0 droplet/livekit/redis at import, lazy heavy imports):
- `config.py` — `ConcurrencyConfig`, master `CONCURRENCY_ENABLED` default-OFF,
  `effective_global_cap()` = worker_slot_cap × worker_count.
- `budget.py` — `TokenBucket` (atomic lazy-refill; per-tenant + per-key LLM rate/burst
  = the denial-of-wallet guard; `per_minute(rpm,burst)`; `give_back` for rollback).
- `slots.py` — `SlotPool` (atomic TTL-leased counting semaphore; idempotent
  acquire/release never-negative; TTL self-heals a crashed worker like the lead-lock).
- `admission.py` — `AdmissionController.reserve()` ALL-OR-NOTHING pre-dial gate:
  global → tenant → worker → tenant-LLM-budget → per-key-LLM-budget → per-key-TTS-slot;
  any refusal rolls back everything (no leak), returns QUEUE (capacity) / PACE (rate).
  `release()` on call end. Routes to healthiest key via W13 `.pick()`. Emits
  `call_admitted`/`call_paced`/`call_released` on W8 (fire-and-forget, dead-bus-safe).
- `autoscale.py` — `AutoscaleSignal.recommend()` (util + CPU → scale_up at cpu≥0.55
  BELOW the 0.70 load_threshold, or util≥0.80; scale_down at cpu<0.30 & util<0.50,
  floor warm_pool_min) + `emit()` an `autoscale_signal` on W8.
- `load_harness.py` — 50/100/200-concurrent SYNTHETIC harness (mock providers/workers,
  NO PSTN): asserts no oversubscription, graceful pacing, p50/p95/max admission
  latency. Runnable `python -m voice_ops.concurrency.load_harness 50 100 200`.

## Reuse (as mandated)
W8 EventBus (`voice_kernel.events`), W13 `HealthScoredKeyPool.pick()`
(`voice_ops.config.keyhealth`), W12 `NumberPool`/`CapacityPlanner` (complementary
number-side gate), W5 `ProviderRouter` (which triple). No new frameworks; codebase-
native flag + config patterns.

## Tests / verification
- `voice_ops/concurrency/` = **52 tests green** (48 build + 4 red-team-fold:
  2 renew/heartbeat + 2 honest-harness binding-overflow).
- Full regression `pytest voice_ops/ voice_kernel/` = **611 passed** (no transient
  failures from concurrent waves' uncommitted edits — scope proven independently green).
- Load harness HARD gate (capacity 20): 50→max_live 20 / 0 err / p95 0.15ms;
  100→max_live 20 / 0 err / p95 0.08ms; 200→max_live 20 / 0 err / p95 0.09ms — PASS.
- Import isolation proven (no droplet/livekit/boto3/redis/psutil at module load).

## Red-team folds (VERIFY+RED-TEAM-FOLD)
Adversarial review (design/W24-CONCURRENCY-SEAM.md §7) found 3 issues; the 2 reachable
folded here (none block this tracked merge; all block the later caller.py seam wave):
1. **Dishonest harness gate** — default huge tenant/LLM/TTS caps meant the 50/100/200
   ladder only exercised the GLOBAL worker slot; a leaked per-key/per-tenant slot would
   pass green. FOLD: `_LiveCounter` samples `controller.snapshot()` per-admit and records
   PEAK in_flight per tenant + per TTS-key pool; `LoadResult.binding_overflow` +
   `oversubscribed`/`ok` now fail on ANY per-pool breach, not just the aggregate.
2. **TTL-sweep → oversubscription** — `SlotPool.renew()` existed but the controller had
   no heartbeat, so a call > reserve_ttl_s got swept while live and the freed slot
   re-admitted another call. FOLD: `AdmissionController.renew(reservation)` extends every
   held slot's TTL (idempotent; False once released/swept); seam §3c2 heartbeat task.
3. **Per-key TTS teardown wiring** — residual is wiring heartbeat+release around the live
   run_job lifecycle (caller.py, earner-gated) → deferred to the seam wave (checklist).

## Seam + deploy (DOC, not applied)
`design/W24-CONCURRENCY-SEAM.md` — exact caller.py reserve/release seam points
(run_job inner loop before create_sip_participant `~:2282`, ACTIVE_CALLS dec `~:2267`,
/run `~:3479`), the agent.py `load_fnc`/`load_threshold` change (earner-gated, NOT in
this wave), the multi-worker horizontal deploy, and the HARD load gate. All seam
points additive + `CONCURRENCY_ENABLED`-gated (OFF = live path byte-identical).

## Recommended worker count for 500-team scale
500 telecallers ≈ 250-300 simultaneous live conversations at peak (~50-60% talk
utilisation). Per-process wall ~20 concurrent (conservative). → ceil(300/20)=15
workers; with autoscale headroom (keep util <~0.65) target **~20 worker processes**
(range 16-24, autoscaled), 20 slots each → `effective_global_cap = 400` concurrent,
warm_pool_min ≥ 2. This is a FLEET sizing — the single-worker box must scale
horizontally, which the admission gate + autoscale signal now make safe + observable.

## Learnings
- `effective_global_cap` = worker_slot_cap × worker_count means in a single-worker
  config the GLOBAL gate fires at/before the WORKER gate — correct, but tests that
  want to isolate the worker gate must set a higher `global_call_cap`.
- Tokens are NOT given back on a NORMAL release (a consumed LLM/TTS request is spent;
  tokens refill by time) — only SLOT capacity frees on call end. give_back is ONLY
  for the all-or-nothing rollback of a refused admission.
- No pytest-asyncio in the repo → async tests drive coroutines with `asyncio.run`,
  matching the codebase's no-extra-plugin posture.
