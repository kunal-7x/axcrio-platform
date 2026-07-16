# W24 — Concurrency Admission Control: caller.py SEAM + multi-worker deploy

Status: BUILT (tracked, disjoint, default-OFF). Seam = a DOC patch (this file).
NEVER edit live `caller.py` / `agent.py` directly. Branch `fix/realtime-voice-kernel-v2`.

This is the answer to the W18 / C1-NEW-W24 critical: the "replace 500 telecallers"
thesis is a CONCURRENCY claim the live dial loop never modeled. A single LiveKit
worker handles ~10-25 concurrent jobs, so the box is perfect on call #1 and silently
saturates ~call #20-50 with no graceful gate. This wave builds the missing layer:
per-call ADMISSION (reserve LLM quota + TTS slot + a worker slot BEFORE dialing; if
unavailable PACE/QUEUE not fail mid-call), per-tenant + per-provider-key
budget/rate-limit (subsumes denial-of-wallet), a worker-pool autoscale SIGNAL, and a
50/100/200-concurrent synthetic LOAD HARNESS promoted to a HARD deploy gate.

All code is in `voice_ops/concurrency/` (TRACKED, disjoint, 0 droplet/livekit/redis
at import). 85 tests green; full `voice_ops/` + `voice_kernel/` = 582 passed.

---

## 1. The current concurrency model (ground truth)

Mapped from `.boxwork/handoff/caller.py` + `agent.py` (the EXPLORE phase):

- **Single LiveKit worker** = the physical wall. `agent.py` starts a bare
  `WorkerOptions(entrypoint_fnc=..., port=8090)` — no `load_threshold`, no
  `num_idle_processes`, no `load_fnc`. In production mode LiveKit defaults to
  `load_threshold=0.70` (CPU) + `num_idle_processes=min(cpu_count,4)`. Each active
  call = one job = one LLM+TTS+STT chain. At ~0.70 CPU the worker marks itself
  UNAVAILABLE and new dispatch silently has nowhere to land. Practical ceiling
  ~10-25 concurrent on a 2 vCPU box; lower with ElevenLabs/Groq latency-holding
  coroutines. **Known LiveKit gotcha:** the load gate re-samples every ~500ms, so
  two job requests in one window can both pass — `load_fnc` alone is NOT a hard
  concurrency cap (GitHub livekit/agents #4884). Our admission gate is the hard cap.
- **Dial loop (`run_job`)** is a plain asyncio coroutine polling every 4s. Before
  each call it checks (all at the tick boundary, none as a reservation):
  per-job `concurrency` (default 3, clamp tenant `max_concurrency`, hard 20),
  `hourly_cap` (200), `daily_cap` (1000), `ACTIVE_CALLS[tenant] < max_conc`
  (3 default / 20 admin), `_tenant_usage().calls < daily_cap_tenant` (500),
  monthly minutes (checked once at `/run`), prepaid balance (once at `/run`),
  calling window, suppression set.
- **The W18 gap — what is NOT checked before dialing:**
  - No LLM quota reservation → Groq 429s mid-call, conversation dies mid-sentence.
  - No TTS slot reservation → at ≥10 concurrent all hitting ElevenLabs, cascading 429s.
  - No worker-load check → call #25 dispatched to a worker already UNAVAILABLE.
  - No queue when saturated → loop just `break`s + sleeps 4s; no pacing/back-pressure.
  - No GLOBAL cross-tenant concurrency guard → 5 tenants × 3 = 15 concurrent unbounded
    at the worker level.
- **W12 CapacityPlanner** = advisory math, never blocks a dial; models number-pool
  throughput only (no LLM/TTS quota). **W5 Router / W13 KeyPool** = provider-side,
  consulted at session start, never pre-call. **W8 EventBus** = post-fact telemetry.

So the number/SIP dimension has an atomic pre-dial gate (`NumberPool.lease`), but the
**provider + worker dimension has none**. W24 fills exactly that.

---

## 2. What W24 adds (`voice_ops/concurrency/`)

| Module | Role |
|---|---|
| `config.py` | `ConcurrencyConfig` — env knobs, master `CONCURRENCY_ENABLED` default-OFF, `effective_global_cap()` = worker_slot_cap × worker_count. |
| `budget.py` | `TokenBucket` — atomic lazy-refill bucket; per-tenant + per-key LLM rate/burst budget (denial-of-wallet guard). `per_minute(rpm, burst)`. |
| `slots.py` | `SlotPool` — atomic, TTL-leased counting semaphore (worker / global / tenant / per-TTS-key). Idempotent acquire+release (never negative); TTL self-heals a crashed worker (mirrors lead-lock TTL). |
| `admission.py` | `AdmissionController.reserve()` — the ALL-OR-NOTHING pre-dial gate. Order: global → tenant → worker → tenant-LLM-budget → per-key-LLM-budget → per-key-TTS-slot. Any refusal rolls back everything already taken (no leak) and returns QUEUE (capacity) or PACE (rate/key). `release()` on call end. Emits `call_admitted`/`call_paced`/`call_released` on W8 (fire-and-forget). Routes to healthiest key via W13 `.pick()`. |
| `autoscale.py` | `AutoscaleSignal.recommend()` — active/capacity utilisation + CPU → SCALE_UP (cpu≥0.55, BELOW the 0.70 load_threshold, or util≥0.80) / SCALE_DOWN (cpu<0.30 & util<0.50, floor warm_pool_min) / HOLD. `emit()` an `autoscale_signal` on W8 for an external autoscaler. |
| `load_harness.py` | the 50/100/200-concurrent synthetic harness (mock providers/workers, NO PSTN). Asserts no oversubscription, graceful pacing, p50/p95/max admission latency. Runnable `python -m voice_ops.concurrency.load_harness 50 100 200`; the pytest gate is `tests/test_load_harness.py`. |

Reuse seams: **W8** `voice_kernel.events` (EventBus / Event / now_utc_iso), **W13**
`voice_ops.config.keyhealth.HealthScoredKeyPool.pick()`, **W12**
`voice_ops.telephony.{NumberPool,CapacityPlanner}` (complementary number-side gate),
**W5** `voice_kernel.providers.router` (which provider triple).

---

## 3. The caller.py admission SEAM (apply later, founder-signed)

The seam is intentionally a DOC, not a code edit. When `CONCURRENCY_ENABLED=1`, wire
the controller at these EXACT points in `caller.py` (line refs from the handoff copy
`.boxwork/handoff/caller.py`; re-anchor by symbol before applying):

### 3a. Process-level: build ONE controller (module scope, near the EventBus singleton)
```python
# caller.py — module scope, lazy/once
_ADMISSION = None
def _admission():
    global _ADMISSION
    if _ADMISSION is None and os.getenv("CONCURRENCY_ENABLED","0") in ("1","true","True","yes","on"):
        from voice_ops.concurrency import AdmissionController, ConcurrencyConfig
        # reuse the live W13 pools + the W8 bus already constructed for the box
        _ADMISSION = AdmissionController(
            ConcurrencyConfig.from_env(),
            tts_keypools=_LIVE_TTS_KEYPOOLS,   # {"elevenlabs": HealthScoredKeyPool, "sarvam": ...}
            llm_keypools=_LIVE_LLM_KEYPOOLS,   # {"groq": HealthScoredKeyPool}
            event_bus=_event_bus(),            # the W8 RedisEventBus singleton
        )
    return _ADMISSION
```

### 3b. Per-call admission — `run_job` inner loop, BEFORE create_sip_participant
Reference: `caller.py:2282` (the `while` that launches calls) / `:2340` (ACTIVE_CALLS
increment). Replace the bare "if under caps: dial" with reserve-then-dial:
```python
adm = _admission()
if adm is not None:
    decision = await adm.reserve(tenant_id, call_id,
                                 provider_tts=choice.tts, provider_llm=choice.llm)
    if not decision.admitted:
        # PACE/QUEUE: do NOT dial; leave the lead for the next 4s tick (no mid-call fail)
        log.info("admission %s lead=%s (%s)", decision.outcome, lead, decision.reason)
        continue
    reservation = decision.reservation     # stash on the call's state
# ... existing create_sip_participant(...) / room dispatch ...
```

### 3c. Release on call end — `run_job` finalize / the ACTIVE_CALLS decrement
Reference: `caller.py:2267` (decrement). Pair every admitted reserve with a release:
```python
finally:
    if adm is not None and reservation is not None:
        await adm.release(reservation)     # frees worker/global/tenant/TTS slots
```

### 3c2. Heartbeat a long call — `run_job` keepalive (REQUIRED for calls > reserve_ttl_s)
A reservation lease auto-expires after `reserve_ttl_s` (300s) so a crashed worker can
never permanently hold a slot. But a *legitimately live* call longer than that window
would have its slots swept out from under it — then the freed slot re-admits another
call (oversubscription) and the original teardown frees the new occupant's lease. So
any call that can exceed `reserve_ttl_s` MUST heartbeat its reservation through the
controller on a timer shorter than the TTL:
```python
async def _heartbeat(adm, reservation, period_s=100.0):   # period < reserve_ttl_s
    while not reservation.released:
        await asyncio.sleep(period_s)
        if not adm.renew(reservation):    # False once released/swept -> stop
            break
# launched alongside the call; cancelled in the same finally that releases.
hb = asyncio.create_task(_heartbeat(adm, reservation))
```
`AdmissionController.renew(reservation)` extends the TTL of EVERY slot the reservation
holds (synchronous, idempotent, never raises). Pair it with the release in `finally`
(`hb.cancel()`). This closes red-team finding #2 (TTL-sweep → phantom-free slot →
oversubscription).

### 3d. `/run` endpoint pre-admission (optional, fail-fast)
Reference: `caller.py:3479` (`asyncio.create_task(run_job(job_id))`). Before launching
a job, a cheap `adm.snapshot()` check can surface "fleet saturated, campaign queued"
to the UI instead of starting a job that will immediately pace. Advisory only.

### 3e. agent.py worker load_fnc (separate, agent-box change — DOC only, NOT this wave)
Set an explicit `load_threshold` + a composite `load_fnc` so the worker refuses jobs
at capacity instead of silently failing:
```python
def _load_fnc(worker) -> float:
    import psutil
    cpu = psutil.cpu_percent(interval=None) / 100.0
    jobs = len(worker.active_jobs) / max(1, WORKER_SLOT_CAP)
    return max(cpu, jobs)              # whichever is hotter
WorkerOptions(..., load_fnc=_load_fnc, load_threshold=0.70,
              num_idle_processes=2)    # warm pool >=2 so a burst never cold-starts
```
This is an `agent.py` (earner) change → gated behind the earner-law (md5 unchanged
until a founder-signed, smoke-tested deploy). Documented here; NOT applied in W24.

**Earner-safety:** every seam point is additive + flag-gated (`CONCURRENCY_ENABLED`,
default OFF). With the flag OFF `_admission()` returns None and the live dial path is
byte-identical. The bus emits are fire-and-forget (a dead Redis never blocks a call).

---

## 4. Multi-worker deploy recommendation

LiveKit dispatch is naturally horizontal: run N identical worker processes (or
containers), all register against the same LiveKit server, server load-balances job
requests to the lowest-load worker. No sticky routing. **Single LiveKit node**
(your box) avoids the multi-node co-location gotcha (livekit #3645).

- Run workers as N systemd units / N containers on the voice box (or a small fleet),
  each its OWN process (so the GIL + the single-worker CPU wall is per-process).
- Set `CONCURRENCY_WORKER_COUNT=N` and `CONCURRENCY_WORKER_SLOT_CAP` per the measured
  per-process ceiling (start conservative at 20; raise only after the load harness +
  a real soak confirm CPU stays < 0.70 at that count).
- `effective_global_cap()` = `WORKER_SLOT_CAP × WORKER_COUNT` is the hard fleet
  ceiling the admission gate enforces (and the cross-tenant guard the loop lacks).
- Autoscale: feed `AutoscaleSignal.recommend(active_calls, current_workers, cpu)` on a
  10-30s schedule; act on `scale_up` at CPU≥0.55 (BEFORE the 0.70 reject threshold),
  `scale_down` at CPU<0.30, never below `warm_pool_min=2`. On managed infra map this
  to an HPA on the LiveKit `livekit_agent_job_count` / CPU metric.

---

## 5. The HARD load gate

`voice_ops/concurrency/tests/test_load_harness.py` IS the deploy gate. It drives the
real `AdmissionController` with 50/100/200 simulated concurrent calls (mock
providers/workers, no PSTN) and asserts:
1. `max_observed_live <= capacity` at every instant (NO oversubscription),
2. `errored == 0` and `completed == offered` (excess is PACED + drains, never failed),
3. `p95_admit_ms < 50ms` (the pure-memory gate stays microsecond-class).

Observed locally (capacity 20): 50→max_live 20 / 0 err / p95 0.10ms;
100→max_live 20 / 0 err / p95 0.13ms; 200→max_live 20 / 0 err / p95 0.11ms — PASS.

CI/deploy MUST run `pytest voice_ops/concurrency/` (and may run
`python -m voice_ops.concurrency.load_harness 50 100 200`, exit 0 = gate pass) before
flipping `CONCURRENCY_ENABLED=1` on the box.

---

## 6. Recommended worker count for 500-team scale

The thesis is "replace 500 telecallers". Concurrency, not total volume, is the wall.

**Assumptions (conservative, from W12 defaults + research):** a busy telecaller is on
a live call ~50-60% of the work-hour (the rest is dialing/no-answer/wrap). So 500
telecallers ≈ **250-300 simultaneous live conversations** at peak. Per-process ceiling
= 20 concurrent jobs (conservative single-worker wall; raise only after a measured
soak).

- **Peak concurrent calls needed ≈ 300.**
- **Workers = ceil(300 / 20) = 15**, plus headroom for the autoscale band (keep
  utilisation < ~0.65 of capacity so a burst doesn't hit the reject threshold):
  **target ~20-24 worker processes** for a comfortable 500-team peak, `warm_pool_min`
  ≥ 2, autoscaling between ~16 (off-peak) and ~24 (peak).
- Config: `CONCURRENCY_WORKER_COUNT=20`, `CONCURRENCY_WORKER_SLOT_CAP=20`
  → `effective_global_cap = 400` concurrent (comfortably above the ~300 peak with
  spillover paced, not failed). Per-tenant cap stays per plan tier.
- If a higher measured per-process ceiling (e.g. 25-40 with Sarvam Bulbul mulaw vs
  ElevenLabs streaming) is proven by the harness + soak, the worker count drops
  proportionally (e.g. 40/process → ceil(300/40)=8 workers + headroom ≈ 12).

**Bottom line: ~20 worker processes (range 16-24, autoscaled), 20 slots each
(global cap 400 concurrent), to safely stand in for a 500-telecaller floor.** This is
a fleet sizing, NOT a single-box claim — the single-worker box tops out ~20 concurrent
and must be scaled horizontally, which the admission gate + autoscale signal now make
safe and observable.

---

## 7. Red-team folds (W24 VERIFY+RED-TEAM)

Adversarial review found 3 issues; the 2 reachable ones are FOLDED in this wave
(tracked-disjoint, no earner edit). All block the later live caller.py seam wave, none
block this tracked merge.

1. **Dishonest harness gate for per-key/per-tenant resources — FOLDED.** The default
   harness cfg set huge tenant/LLM/TTS caps so the 50/100/200 ladder only exercised the
   GLOBAL worker slot; a leaked per-TTS-key or per-tenant slot would never breach the
   aggregate and would sail through green. Fix: `_LiveCounter` now samples
   `controller.snapshot()` at every admit and records the PEAK `in_flight` of every
   per-tenant and per-TTS-key pool; `LoadResult.binding_overflow` flags any pool whose
   peak exceeded ITS own capacity, and `oversubscribed`/`ok` now fail on a per-pool
   breach — not just the global ceiling. New tests:
   `test_per_tts_key_is_binding_and_never_oversubscribed` (TTS key the binding wall,
   held) + `test_binding_overflow_detects_a_leaked_per_key_slot` (negative control:
   over-cap per-key peak → `ok` False where the old gate passed).

2. **TTL-sweep + re-acquire → oversubscription — FOLDED.** `SlotPool.renew()` existed
   but the `AdmissionController` exposed no heartbeat, so a call > `reserve_ttl_s` (300s)
   had its leases swept while live; the freed slot re-admitted another call and the
   original teardown freed the new occupant. Fix: `AdmissionController.renew(reservation)`
   extends the TTL of every slot the reservation holds (idempotent; False once
   released/swept). Seam guidance added (§3c2: heartbeat task, period < TTL, cancelled in
   `finally`). New tests:
   `test_renew_keeps_a_long_call_from_being_swept_into_oversubscription` +
   `test_renew_is_noop_after_release_and_for_swept_lease`.

3. **Per-key TTS-slot teardown on call end (deferred to the seam wave).** A normal
   `release()` frees slot capacity correctly; the only residual is wiring the heartbeat
   + release exactly around the live `run_job` lifecycle (§3c/§3c2), which is a
   caller.py change gated behind the earner law. Tracked here as the seam-wave checklist
   item; the module-level contract is proven by the new tests above.

**Verdict: SHIP the tracked-disjoint module.** Earner untouched (agent.py local snapshot
md5 `98655dbf`; caller.py not edited), `CONCURRENCY_ENABLED` default-OFF, 52 module tests
+ full voice_ops/voice_kernel suite green, harness HARD GATE = PASS.
