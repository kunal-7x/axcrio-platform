# DESIGN SPEC — Hatchet Self-Hosted Durable Orchestration (Phase 3, STRANGLE & EVOLVE)

> **Status:** EXECUTION-READY. A build agent implements this verbatim, one UNIT at a time,
> committing + acceptance-testing each before the next. **NON-BREAKING + crash-safe per unit.**
> The live system (`panel.famit.in`, voice agent `capsy`) keeps earning throughout.
> **Verdict is settled** (master plan §VERDICT): modular monolith, evolve behind flags, do not rebuild.

---

## 0. CONTEXT, SCOPE, AND THE ONE HARD DEPENDENCY

### 0.1 What we are replacing (the in-RAM orchestration surface)
All orchestration today lives **inside the uvicorn process** (`caller.py` on `famit-livekit
168.144.153.145`, systemd `famit-caller`, venv `/opt/capsy-agent/.venv` py3.12.3):

| In-RAM thing | `caller.py` location | Role | Hatchet replacement |
|---|---|---|---|
| `JOBS: dict = {}` | `caller.py:139` | live campaign-run state | Hatchet **runs** (`campaign-run` workflow) |
| `async def run_job(job_id)` | `caller.py:1571` | the dial loop | `campaign-run` workflow → fan-out to `dial-lead` task |
| inline dial block | `caller.py:1642–1682` | create_room+dispatch+SIP | extracted `dial_one_lead()` activity (idempotent) |
| `async def _finalize_call(...)` | `caller.py:1472` | classify→score→retry→suppress→WA→webhook | `finalize-call` activity (reused as-is, made idempotent) |
| `ACTIVE_CALLS: dict = {}` | `caller.py:254` | per-tenant concurrency cap | Hatchet **concurrency key** (CEL `input.tenant_id`) |
| `async def scheduler_loop()` (60s) | `caller.py:3298` | retries + vendor-sync + reconcile sweep | split into 3 Hatchet crons |
| `_spawn_retry_job(r)` | `caller.py:3283` | single-lead retry job | `retry-callback` durable workflow (delayed run) |
| `retry_queue.json` (`RETRY_FILE`) | `caller.py:116` | next_attempt_at polling store | Hatchet **durable sleep** / scheduled run |
| `_enqueue_retry` / `_remove_retry` | `caller.py:927` / `:951` | retry queue CRUD | superseded by durable workflow state |

### 0.2 What Hatchet is (pinned facts, from current docs — DO NOT design from memory)
Source: context7 `/websites/hatchet_run` (docs.hatchet.run), pulled 2026-06-09. **Pin engine `V1`.**
- **Self-hosted topology (V1):** a docker-compose stack of `postgres` + `rabbitmq` + `migration` +
  `setup-config` (`hatchet-admin quickstart`) + `hatchet-engine` (gRPC) + `hatchet-dashboard` (web UI).
  A lighter single-container `hatchet-lite` image also exists (`8888` API/dashboard, `7077` gRPC) and
  **is what we deploy** (lower footprint on the latency-critical voice box) + its own `postgres` +
  `rabbitmq`. RabbitMQ **is required** by the V1 engine.
- **Python SDK (V1, function/task API — NOT the old `@hatchet.step` class API):**
  - Client: `from hatchet_sdk import Hatchet; hatchet = Hatchet()` (reads `HATCHET_CLIENT_TOKEN`,
    `HATCHET_CLIENT_HOST_PORT` / `HATCHET_CLIENT_TLS_STRATEGY=none` for self-host insecure gRPC).
  - Workflow: `wf = hatchet.workflow(name="...", input_validator=PydModel, on_crons=["*/1 * * * *"])`.
  - Task: `@wf.task(retries=3, backoff_factor=2.0, backoff_max_seconds=60, concurrency=...)`.
  - Durable (multi-day): `@hatchet.durable_task(...)` with `ctx.aio_sleep_for(timedelta(...))` /
    `ctx.aio_wait_for_event("key")` — **survives worker restarts in real time** (the WhatsApp cadence).
  - Worker: `w = hatchet.worker("famit-orchestrator", workflows=[...]); w.start()`.
  - Trigger from FastAPI: `wf.run_no_wait(input=..., additional_metadata={...}, key="<dedup>")`
    returns a run ref with `.workflow_run_id`. **`key` (a.k.a. `child_key`) deduplicates runs** —
    our idempotency lever.
  - Concurrency: `@wf.task(concurrency=ConcurrencyExpression(expression="input.tenant_id",
    max_runs=N, limit_strategy=ConcurrencyLimitStrategy.GROUP_ROUND_ROBIN))`. An `int` is shorthand
    for a constant limit with GROUP_ROUND_ROBIN.

### 0.3 THE ONE HARD DEPENDENCY (read this twice)
> ⚠️ **OVERRIDDEN/EXTENDED by RTF-1 + RTF-5 (see RED-TEAM FIXES at end):** the write-set gated here is
> bigger than `calls/leads/suppression/retry` — it also includes `billing`, `ledger`, `wa_log`,
> `wa_threads`, `webhook_log`; and `_emit_webhook` is NOT idempotent on re-run. Read those before flipping
> any write-path workflow.
Today `run_job` + `scheduler_loop` are **asyncio tasks in one process**, and **`_STORE_LOCK =
asyncio.Lock()` (`caller.py:259`) serializes all JSON writes** to `calls.json`/`leads.json`/
`suppression.json`/`retry_queue.json`. **A Hatchet worker is a SEPARATE PROCESS.** An `asyncio.Lock`
does not span processes. The instant a worker process runs `record_call` / `_finalize_call` /
`_enqueue_retry` while uvicorn also writes those files → **lost updates / corrupted JSON on the live
box.**

**Therefore:** any workflow whose activities WRITE a shared store (`dial-lead`→`record_call`→
`calls.json`; `finalize-call`→`calls.json`/`leads.json`/`suppression.json`) **MUST NOT cut over until
P1 (Postgres strangler) has migrated that store to `pg`/`dual` mode** (cross-process-safe via DB
transactions + row locks). Per `P1_FOUNDATION_STATE.md`, P1 migrates `leads → calls → suppression →
retry`. **The cutover ORDER below is gated on this**, and is the reason `campaign-run` (which writes
`calls.json`) is LAST, while `vendor-sync` (writes only `usage_events.json`/`cost_ledger.json`/
`daily_rollups.json`, single-writer, idempotent rebuild) is FIRST.

> Build-agent guard: before flipping any write-path workflow to Hatchet, assert
> `GET /admin/store-status` (P1 U8) reports the relevant store in `dual` or `pg` mode. If P1 is not
> there yet, that workflow stays `legacy` — ship only the read-only / net-new workflows.

### 0.4 SECOND cross-process hazard: process-GLOBAL in-memory state (not just files)
The worker does `import caller` to reuse funcs. Several reused funcs read/write **module-global
in-RAM state**, and a separate worker process gets its OWN copies:
- `CALLS` (module-global list; `record_call` appends to it, the reconcile sweep does `for c in
  list(CALLS)`), `LEADS`, and `ACTIVE_CALLS` (`caller.py:254`).
- **Consequence:** even with P1 PG, if any read path uses these globals as an in-RAM cache instead of
  re-reading PG, the worker's `CALLS` and uvicorn's `CALLS` silently DIVERGE → stale `/calls`,
  double-processed sweep, wrong concurrency accounting.
- **Spec:**
  1. `ACTIVE_CALLS` is REPLACED by the Hatchet CEL concurrency key (§4.4) — not shared at all.
  2. For `CALLS`/`LEADS`: in the worker's activities, every read MUST come from PG (P1 `pg`/`dual`),
     never from the in-RAM module global. UNIT 6/7 adds an explicit check: confirm `record_call` /
     `_finalize_call` / the sweep operate on PG rows (or re-read the file) inside the worker, not on a
     divergent in-process list. If a func caches in `CALLS`, refactor that read to go through the
     Store seam (P1 `store.py`) so both processes see one source of truth.
  3. **Good news (note so the agent doesn't worry):** `scheduler_loop` will NOT double-start in the
     worker — it is registered via `@app.on_event("startup")` (`caller.py:3402`), which fires only
     under uvicorn. `import caller` in the worker does not boot the FastAPI startup hooks. The worker
     runs ONLY the Hatchet workflows it registers.

---

## 1. ARCHITECTURE DECISIONS (locked)

1. **Hatchet engine + its Postgres + RabbitMQ run in Docker on `famit-livekit`** (same box as the
   voice agent), under **strict cpu/mem limits** (the voice path is priority #1; the master plan names
   noisy-neighbor on this box as the FIRST scale concern). `hatchet-lite` image to minimize footprint.
2. **Hatchet's metadata DB is a LOGICAL DB** (`hatchet` in its own dockerized Postgres), already
   physically separate from the app's `famit` Postgres (P1) and from the JSON stores. The master-plan
   "separate orchestration DB" trigger (**>60k calls/day OR p95 lead-memory read >50ms**) means
   *promote Hatchet's Postgres to a managed/separate instance* — spec'd in §9, NOT done now.
3. **The worker is a NEW process:** systemd `famit-orchestrator`, `/opt/capsy-agent/.venv`, importing
   the SAME `caller.py` module (and `vendors/`, `whatsapp.py`) so it reuses every well-factored func.
   It does **not** serve HTTP. uvicorn (`famit-caller`) keeps serving `/api`; it only gains the ability
   to *trigger* Hatchet runs.
4. **Per-workflow feature flags, not one global switch.** A single `ORCHESTRATOR=legacy|hatchet`
   contradicts "one workflow type at a time." We use a global default **plus** per-workflow override
   (see §3). Flip one workflow, leave the rest legacy.
5. **Reuse existing funcs as activities; do NOT rewrite business logic.** `_finalize_call`,
   `_classify_outcome`, `_update_lead_after_call`, `_charge_call`, `_send_whatsapp`/`_wa_ai_followup`,
   `_emit_webhook`, `vendor_sync`, `rebuild_cost_ledger`, `_drain_usage_raw` are reused verbatim. The
   only refactor is **extracting the inline dial block** (`caller.py:1642–1682`) into `dial_one_lead()`
   so BOTH legacy `run_job` and the Hatchet `dial-lead` activity call ONE code path.
6. **Idempotency is mandatory** (Hatchet is at-least-once; steps re-run on crash). Every
   side-effecting activity gets a deterministic dedup key + a pre-check. The lethal case is double-
   dialing; §5 specifies the guard.
7. **`/status` contract is preserved.** The Run page calls `GET /status?job=<id>` →
   `{state, leads:[{name,num,status}]}` (`caller.py:2176`). When a run is Hatchet-backed, `/status`
   reads run state back from Hatchet and **re-shapes to the identical contract** (§6).

---

## 2. FILES TO CREATE / EDIT (exact paths)

All local sources under `C:\Users\kunal\Desktop\caps\droplet_work\`; deploy targets on
`famit@168.144.153.145:/opt/famit-agent/`.

### CREATE
| Path | Purpose | Model |
|---|---|---|
| `droplet_work\orchestration\__init__.py` | package marker | haiku |
| `droplet_work\orchestration\client.py` | `get_hatchet()` singleton + import-safe degrade (returns `None` if SDK/token absent) | sonnet |
| `droplet_work\orchestration\flags.py` | `orchestrator_for(workflow_name) -> "legacy"\|"hatchet"` reading env | sonnet |
| `droplet_work\orchestration\models.py` | Pydantic inputs: `CampaignRunInput`, `DialLeadInput`, `FinalizeInput`, `RetryInput`, `WaCadenceInput`, `VendorSyncInput` | sonnet |
| `droplet_work\orchestration\workflows.py` | the 5 workflows + their tasks; thin wrappers calling reused `caller.py` funcs | **opus** |
| `droplet_work\orchestration\worker.py` | builds `Hatchet().worker("famit-orchestrator", workflows=[...])`, `.start()`; honors flags (registers only flag-eligible workflows) | sonnet |
| `infra\hatchet\docker-compose.hatchet.yml` | hatchet-lite + postgres + rabbitmq, cpu/mem-limited | sonnet |
| `infra\hatchet\.env.hatchet.example` | compose env template (no secrets committed) | haiku |
| `infra\systemd\famit-orchestrator.service` | worker unit | sonnet |
| `droplet_work\ORCHESTRATION_STATE.md` | per-unit task ledger (IN PROGRESS/DONE), crash-safe | (agent maintains) |
| `droplet_work\orchestration\_smoke_orch.py` | instantiates client+workflows (import + AST + plugin-instantiate smoke, mirrors `_smoke_pool.py`) | haiku |

### EDIT (surgical, additive, flag-gated)
| Path | Edit | Model |
|---|---|---|
| `droplet_work\caller.py` | (a) extract inline dial → `async def dial_one_lead(...)`; `run_job` calls it (behavior identical). (b) `POST /run` (`:2117`): if `orchestrator_for("campaign-run")=="hatchet"` → `campaign_run_wf.run_no_wait(...)`, store returned `workflow_run_id` in a `RUN_INDEX` map, return same JSON. else legacy `JOBS`/`run_job`. (c) `GET /status` (`:2176`): if job id is Hatchet-backed → read run state, re-shape. (d) `scheduler_loop` (`:3298`): guard each of its 3 duties by its flag (skip the duty when that workflow is `hatchet`). (e) `_finalize_call`/`dial_one_lead`/`vendor_sync`: add idempotency pre-checks (§5). | **opus** |

> **No other file changes.** `agent.py`, `prompt.py`, `langdetect.py`, `memory.py`, `vendors/*`,
> `whatsapp.py` are untouched (the workflows IMPORT and call them; they do not edit them).

---

## 3. FEATURE FLAGS (per-workflow routing) — `orchestration/flags.py`

Read once per call (env, cheap). Pattern mirrors `config.py` import-safe philosophy.

```python
# orchestration/flags.py
import os
_WORKFLOWS = {"vendor-sync", "wa-cadence", "retry-callback", "campaign-run"}
_DEFAULT = os.getenv("ORCHESTRATOR", "legacy").strip().lower()   # global default

def orchestrator_for(name: str) -> str:
    """Return 'legacy' or 'hatchet' for a workflow. Per-workflow env overrides the
    global default. Fails CLOSED to 'legacy' on any bad value (never break live)."""
    if name not in _WORKFLOWS:
        return "legacy"
    env_key = "ORCH_" + name.upper().replace("-", "_")        # ORCH_VENDOR_SYNC, etc.
    val = os.getenv(env_key, _DEFAULT).strip().lower()
    return "hatchet" if val == "hatchet" else "legacy"

def hatchet_available() -> bool:
    from .client import get_hatchet
    return get_hatchet() is not None
```

**Env vars** (append empty/`legacy` to `/opt/famit-agent/.env`; default keeps everything legacy):
```
ORCHESTRATOR=legacy                 # global default
ORCH_VENDOR_SYNC=legacy             # flip to hatchet first
ORCH_WA_CADENCE=legacy
ORCH_RETRY_CALLBACK=legacy
ORCH_CAMPAIGN_RUN=legacy            # flip LAST (after P1 calls/leads in dual/pg)
HATCHET_CLIENT_TOKEN=               # from Hatchet dashboard; empty => worker no-ops, flags forced legacy
HATCHET_CLIENT_HOST_PORT=127.0.0.1:7077
HATCHET_CLIENT_TLS_STRATEGY=none
```

**Safety interlock (in `flags.py` consumers):** every `/run` and `scheduler_loop` branch calls BOTH
`orchestrator_for(name)=="hatchet"` AND `hatchet_available()`. If the token/SDK is missing or the
engine is unreachable, the code path **silently stays legacy** — a flipped flag can never take the
site down.

---

## 4. THE WORKFLOWS (wrap existing funcs as activities)

`orchestration/workflows.py` imports the live module: `import caller` (so `dial_one_lead`,
`_finalize_call`, `vendor_sync`, etc. are the SAME objects uvicorn uses). Pydantic inputs in
`models.py`. Pin `retries`/`backoff` per the docs API.

### 4.1 `vendor-sync` (FIRST — read-only, no calls placed)
> ⚠️ **OVERRIDDEN by RTF-4:** NOT a clean single-writer cutover — the LIVE `POST /billing/sync` endpoint
> also calls `vendor_sync()` in-process. When `ORCH_VENDOR_SYNC=hatchet`, that handler MUST route through
> Hatchet (worker = sole writer) or this corrupts `cost_ledger/daily_rollups/vendor_snapshots`. See RTF-4.
Replaces `scheduler_loop`'s vendor duties (`caller.py:3304–3317`: `_drain_usage_raw` + every-30-min
`vendor_sync` + per-tick `rebuild_cost_ledger`).
```python
vendor_sync_wf = hatchet.workflow(name="vendor-sync", on_crons=["*/1 * * * *"])

@vendor_sync_wf.task(retries=2, backoff_factor=2.0, backoff_max_seconds=60,
                     execution_timeout=timedelta(minutes=5))
async def tick(input: VendorSyncInput, ctx) -> dict:
    await caller._drain_usage_raw()                  # idempotent ingest
    if caller._vendor_sync_due():                    # NEW helper: 30-min gate moved off in-RAM global
        await caller.vendor_sync()                   # ElevenLabs + Vobiz CDR sync + rebuild
    else:
        caller.rebuild_cost_ledger()                 # cheap deterministic rebuild
    return {"ok": True}
```
- **Idempotency:** `_drain_usage_raw` consumes per-room files then deletes them (already
  at-most-once per file); `rebuild_cost_ledger` is a pure deterministic rebuild; `vendor_sync` pulls
  vendor CDRs and overwrites snapshots → safe to re-run. The only in-RAM state is the 30-min throttle
  `_LAST_VENDOR_SYNC` (`caller.py:3308`) — move it to a tiny `var/vendor_sync_last.txt` timestamp via
  helper `_vendor_sync_due()` so it survives across worker restarts (single-writer file, safe).

### 4.2 `wa-cadence` (SECOND — NET-NEW, additive, nothing to break)
Multi-day WhatsApp follow-up cadence — a textbook durable workflow. Today only a *single* post-call
follow-up exists (`_send_whatsapp`/`_wa_ai_followup` in `_finalize_call`); a true **multi-day cadence
does not exist in legacy**, so there is no legacy path to preserve → **build directly in Hatchet,**
gated only by `wa_followup` campaign flag + WA creds (dormant until Meta creds land, per WAVE A2).
```python
@hatchet.durable_task(name="wa-cadence", retries=2,
                      execution_timeout=timedelta(days=7))   # MUST be a decorator (doc-confirmed)
async def wa_cadence(input: WaCadenceInput, ctx: DurableContext) -> dict:
    # APP-LEVEL dedup gate (see Idempotency note): refuse a second cadence for this lead.
    if not caller._wa_cadence_claim(input.tenant_id, input.phone, input.campaign_id):   # NEW marker, §4.5
        return {"stopped": "already_running"}
    # Day 0 immediate recap already fired in finalize; this owns Day 1..N nudges.
    for step in input.schedule:            # e.g. [{"after_hours":24,"template":"nudge1"}, {"after_hours":72,...}]
        await ctx.aio_sleep_for(timedelta(hours=step["after_hours"]))   # DURABLE real-time sleep (doc-confirmed)
        thread = caller._wa_thread_read(input.phone)        # EXISTING accessor, caller.py:1052
        if thread.get("status") in ("opted_out", "needs_human"):
            return {"stopped": thread["status"]}                        # stop cadence
        await caller._wa_send_followup_step(input.tenant_id, input.phone, step["template"], input)  # NEW thin helper (see §4.5)
    return {"completed": True}
```
- **Trigger:** in `_finalize_call`, where the single follow-up fires, ALSO (when
  `orchestrator_for("wa-cadence")=="hatchet"` and campaign has a `wa_cadence` schedule) call
  `wa_cadence.run_no_wait(input=...)`. (Top-level triggers; see idempotency note below.)
- **Idempotency (CORRECTED — verified against docs):** `run_no_wait`'s caller-supplied dedup param is
  **`child_key`** and the docs scope it to *child* runs — there is **no documented top-level-run dedup
  by a caller key.** So a duplicate `_finalize_call` could otherwise start TWO multi-day cadences.
  Therefore the dial-claim backstop does NOT cover this path (no call is placed). Guard it at the
  **application level**: `_wa_cadence_claim(tenant,phone,campaign_id)` (NEW, §4.5) atomically creates a
  `var/wa_cadence_claims/<key>.json` (or a PG row once P1) and returns False if one already exists →
  the second run early-returns. `aio_sleep_for` is durable, so a worker restart RESUMES the same
  sleep within the one running cadence (not a new one).

### 4.3 `retry-callback` (THIRD — replaces next_attempt_at polling)
Replaces `scheduler_loop`'s retry dispatch (`caller.py:3318–3326`) + `_spawn_retry_job` +
`retry_queue.json` polling with a **durable delayed run**. `_finalize_call` already computes the next
attempt time (`caller.py:1509–1525`); instead of writing `RETRY_FILE`, schedule a delayed Hatchet run.
```python
@hatchet.durable_task(name="retry-callback", retries=1,
                      execution_timeout=timedelta(days=2))   # MUST be a decorator (doc-confirmed)
async def retry_callback(input: RetryInput, ctx: DurableContext) -> dict:
    # sleep until the scheduled attempt (callback time or backoff), durably
    await ctx.aio_sleep_for(_until(input.next_attempt_at))    # _until -> timedelta (NEW glue)
    # re-check guards that scheduler_loop enforced (window + suppression)
    fields = (caller.get_campaign(input.campaign_id) or {}).get("fields", {}) or {}
    if not caller._in_window(fields)[0]:                 # EXISTING gate, caller.py:437
        # reschedule to next window open (durable) instead of dropping.
        # `_clamp_to_window` EXISTS (caller.py:447) and returns the next in-window datetime;
        # use it to compute the next open instead of a NEW `_next_window_open`.
        await ctx.aio_sleep_for(_until(caller._clamp_to_window(caller.now_ist(), fields).isoformat()))
    if caller.norm(input.phone) in caller._suppressed_set(input.tenant_id):
        return {"skipped": "suppressed"}
    # ONE-lead dial via the SAME extracted path (no second code path)
    return await caller.dial_one_lead(_single_lead_ctx(input))
```
- **Trigger:** `_finalize_call`'s retry/callback branch, when flag=hatchet, calls
  `retry_callback.run_no_wait(input=...)` instead of `_enqueue_retry`. On flag=legacy it still writes
  `RETRY_FILE` exactly as today.
- **Idempotency (CORRECTED):** do NOT rely on a `run_no_wait` caller key here (same `child_key`-only
  limitation as §4.2). Safety instead comes from **`dial_one_lead`'s dial-claim** keyed on
  `(campaign_id,phone,attempt)` (§5): even if a duplicate finalize spawns two `retry-callback` runs for
  the same attempt, BOTH hit the same claim and exactly ONE real call is placed. The suppression
  re-check after the sleep is an additional guard. (A call IS placed on this path, so the dial claim —
  not an app marker — is the correct backstop.)

### 4.4 `campaign-run` (LAST — gated on P1 calls/leads in dual/pg)
The dial loop. **Do NOT carry the `JOBS` dict forward** — Hatchet runs ARE the job state. Pattern:
a parent task fans out one `dial-lead` child per lead (Hatchet concurrency control enforces the
per-tenant cap that `ACTIVE_CALLS` used to), then a `finalize-batch`/per-call finalize.
```python
campaign_run_wf = hatchet.workflow(name="campaign-run", input_validator=CampaignRunInput)

@campaign_run_wf.task(execution_timeout=timedelta(hours=12))
async def fan_out(input: CampaignRunInput, ctx) -> dict:
    leads = _filter_suppressed(input)                # NEW helper wrapping the EXISTING inline
                                                     # suppression pre-filter logic at caller.py:2149-2151
                                                     # (`_suppressed_set` exists; the filter is inline today)
    items = [dial_lead_wf.create_bulk_run_item(
                input=DialLeadInput(**lead, campaign_id=input.campaign_id,
                                    tenant_id=input.tenant_id, attempt=0),
                key=f"dial:{input.campaign_id}:{lead['phone']}:0")     # idempotent per lead+attempt
             for lead in leads]
    return {"results": await dial_lead_wf.aio_run_many(items)}

# child workflow — the actual call; concurrency-limited per tenant
@dial_lead_wf.task(
    concurrency=ConcurrencyExpression(expression="input.tenant_id",
                                      max_runs=DEFAULT_TENANT_CONC,    # resolved from tenant cap
                                      limit_strategy=ConcurrencyLimitStrategy.GROUP_ROUND_ROBIN),
    retries=0,                                          # NEVER auto-retry a dial (idempotency guard handles it)
    execution_timeout=timedelta(minutes=10))
async def dial_lead(input: DialLeadInput, ctx) -> dict:
    return await caller.dial_one_lead(input.as_legacy_item())   # SAME path legacy uses
```
- **Window gate:** keep `_in_window`; the parent re-checks per batch (or the dial task early-returns
  `out_of_window` and is re-scheduled), preserving the 09:00–21:00 behavior.
- **Concurrency:** `ACTIVE_CALLS` (`caller.py:254`, in-mem) is REPLACED by the CEL concurrency key on
  `dial-lead`. `max_runs` = the tenant's `max_concurrency` (the dial task resolves it; for the v1
  cut, use a constant `DEFAULT_TENANT_CONC` and tighten to per-tenant via a dynamic key in a
  follow-up — note both in `ORCHESTRATION_STATE.md`).
- **Finalize:** each `dial-lead` enqueues / directly calls `finalize-call` (the reused
  `_finalize_call`). The **reconciliation sweep** (`scheduler_loop:3327–3393`) for late transcripts is
  KEPT as a cron during transition (transcripts still land async from the agent); it can later become
  a durable "wait-for-transcript-then-finalize" event (§9, not now).

### 4.5 REUSED vs NEW funcs (exact — do not invent; cite before you call)
The workflows must call the REAL functions. The table below is authoritative; anything marked NEW the
agent CREATES (thin wrapper, no new business logic). Verified against `caller.py` 2026-06-09.

| Name used in workflows | Status | Real location / basis |
|---|---|---|
| `caller.dial_one_lead(...)` | **NEW (UNIT 6)** | extracted from inline dial block `caller.py:1642-1682` |
| `caller._finalize_call(...)` | EXISTING | `caller.py:1472` |
| `caller._classify_outcome(...)` | EXISTING | `caller.py:862` |
| `caller._update_lead_after_call(...)` | EXISTING (non-regressing) | `caller.py:881` |
| `caller._charge_call(...)` | EXISTING — **add idempotency guard (§5)** | `caller.py:1336` |
| `caller._emit_webhook(...)` | EXISTING (`_wh_completed` guarded) | used `caller.py:1538` |
| `caller._send_whatsapp(...)` / `caller._wa_followup(...)` | EXISTING | `caller.py:959` / `:1017` |
| `caller._wa_thread_read(phone)` | EXISTING accessor | `caller.py:1052` (NOT `_wa_thread_get`) |
| `caller._wa_thread_write(...)` | EXISTING | `caller.py:1056` |
| `caller._in_window(fields)` | EXISTING | `caller.py:437` |
| `caller._clamp_to_window(dt, fields)` | EXISTING (use for "next window open") | `caller.py:447` (NO `_next_window_open` exists) |
| `caller._suppressed_set(tenant_id)` | EXISTING | used `caller.py:2150` |
| `caller.vendor_sync()` / `caller.rebuild_cost_ledger()` / `caller._drain_usage_raw()` | EXISTING | called in `scheduler_loop` `:3304-3315` |
| `caller.get_campaign(cid)` / `caller.norm(phone)` / `caller.now_ist()` | EXISTING | throughout |
| `_vendor_sync_due()` | **NEW** | replaces in-RAM `_LAST_VENDOR_SYNC` (`caller.py:263`) with a `var/vendor_sync_last.txt` timestamp gate |
| `_filter_suppressed(input)` | **NEW** | wraps inline pre-filter `caller.py:2149-2151` |
| `_wa_send_followup_step(...)` | **NEW** | thin wrapper over `whatsapp.py` send + `_wa_thread_write` |
| `_wa_cadence_claim(tenant,phone,cid)` | **NEW** | atomic `var/wa_cadence_claims/<key>.json` (or PG row) creator; returns False if it already exists — app-level dedup for `wa-cadence` (§4.2), since `run_no_wait` has no top-level caller-key dedup |
| dial-claim helper (write/check `var/dial_claims/<key>.json`) | **NEW** | the §5 dial idempotency guard inside `dial_one_lead` |
| `_until(iso)` / `_single_lead_ctx(input)` / `as_legacy_item()` | **NEW** (local glue) | compute sleep duration; build the `item` dict `run_job` passes to `dial_one_lead` |

---

## 5. IDEMPOTENCY (mandatory — Hatchet is at-least-once)

The reused funcs were written assuming `run_job` calls them **exactly once**. Hatchet re-runs steps on
crash. Audit + guard each side effect:

| Side effect | Risk on re-run | Guard (spec) |
|---|---|---|
| **dial** (`dial_one_lead`, ex-`caller.py:1642`) | **places a SECOND real call** (worst case) | Before `create_room`/`create_sip_participant`, check a per-`(campaign_id,phone,attempt)` claim: a `var/dial_claims/<key>.json` marker written under `_STORE_LOCK` (or a `dial_claims` PG row once P1) recording `room`+`sip_call_id`. If a claim exists → return the existing record, do NOT dial. Also pass Hatchet `key=dial:{cid}:{phone}:{attempt}` so Hatchet itself dedups the run. `retries=0` on the dial task (never auto-retry a dial). |
| `record_call` | duplicate call row | record_call keys by `id`; with the dial claim it runs once. If P1 PG: upsert by `(campaign_id,phone,attempt)`. |
| `_charge_call` (ledger + prepaid debit) | **double-bill** | Make `_charge_call` idempotent: it already appends a ledger row per `call_id`; add a guard — skip if a ledger row with this `call_id` exists (check before append + debit). EDIT in `caller.py`. |
| `_emit_webhook` (call.completed / lead.qualified) | duplicate webhook | already guarded by `_wh_completed` / `_reconciled` flags on the call rec (`caller.py:1536`,`:3377`) — verify the flag is set BEFORE the activity can re-run (set+persist, then emit). |
| `_send_whatsapp` / `_wa_ai_followup` | duplicate WA message | add a per-`(phone,template,call_id)` sent-marker in `wa_log` check before send (the cadence workflow's `key` covers the multi-day path). |
| `_update_lead_after_call` | regress lead score | already non-regressing (keeps MAX interest + MOST-RECENT outcome, `caller.py:881`) → re-run safe. |
| `vendor_sync` / `rebuild_cost_ledger` | none (deterministic) | safe. |

> **Build-agent rule:** the dial claim is the single most important guard. Implement + test it FIRST
> within the `campaign-run` unit, with a forced-retry test (kill the worker mid-dial; confirm exactly
> one SIP call to the test number).

---

## 6. `/status` READ-BACK (preserve the frontend contract)

`GET /status?job=<id>` must keep returning `{state, leads:[{name,num,status}]}` (Run page depends on
it). Spec:
- Maintain `RUN_INDEX: dict[str, str]` mapping our returned `job_id` → Hatchet `workflow_run_id`
  (populated in `/run` when flag=hatchet). Persist it to `var/run_index.json` (single-writer from
  uvicorn) so it survives a `famit-caller` restart.
- In `/status`: if `job` is in `RUN_INDEX`, fetch run status via the SDK and **map** Hatchet states →
  `queued|calling|done|failed` and child dial states → per-lead `status`. If `job` is a legacy `JOBS`
  id, return as today. Suggested map: `RUNNING`→`calling`, `SUCCEEDED`/`COMPLETED`→`done`,
  `FAILED`→`failed`, `QUEUED`/`SCHEDULED`/`PENDING`→`queued`.
- **⚠️ VERIFY-BEFORE-IMPLEMENT (not yet confirmed in docs):** the exact SDK accessor to read a run +
  its child-run states by `workflow_run_id` was NOT in the doc pulls (candidates seen elsewhere:
  `hatchet.runs.get(...)`, the REST `GET /api/v1/.../workflow-runs/{id}`, or the `TaskRunRef`
  returned by `run_no_wait`). Before writing UNIT 7's `/status`, the agent MUST re-query context7
  (`/websites/hatchet_run`, query "Python read workflow run status and child task run states by
  run_id") and use the confirmed call. Do NOT ship the read-back from memory.
- Acceptance: the Run page shows live progress for a Hatchet-backed run identical in shape to legacy.

---

## 7. STEP ORDER (each unit: mark IN PROGRESS → implement → ACCEPTANCE TEST → commit → mark DONE)

> Cutover ORDER = by **blast radius**, NOT the task's list order. Read-only/net-new first; the
> call-placing write path last. Each unit is independently shippable; the flag stays `legacy` until
> its acceptance test passes, so a half-done unit cannot affect the live site.

### UNIT 0 — Baseline + pin (no behavior change) — **sonnet**
- Confirm `famit-caller`+`famit-agent` active; `md5 caller.py` local==deployed; record a real call's
  eou/TTFT baseline from logs (for the no-regression gate). Write `ORCHESTRATION_STATE.md`.
- **ACCEPT:** services active; baseline latency numbers recorded; `git status` clean.

### UNIT 1 — Deploy Hatchet engine (Docker, resource-limited) — **sonnet**
- Add `infra\hatchet\docker-compose.hatchet.yml` (hatchet-lite + postgres + rabbitmq), with
  `deploy.resources.limits` (e.g. engine `cpus: "0.75", memory: 768M`; postgres `cpus:"0.5",
  memory:512M`; rabbitmq `memory:384M`) so it can never starve the voice agent. Bind dashboard to
  `127.0.0.1:8888` (NOT public; reach via SSH tunnel). gRPC `127.0.0.1:7077`.
- `docker compose -f docker-compose.hatchet.yml up -d`. Create an API token in the dashboard →
  `HATCHET_CLIENT_TOKEN`. **`ORCHESTRATOR` stays `legacy`.**
- **ACCEPT (prove on the box, non-breaking):**
  - `docker ps` shows hatchet-lite+postgres+rabbitmq healthy; `curl 127.0.0.1:8888/api/ready` ok.
  - Dashboard reachable via tunnel; **0 workflows registered yet.**
  - **No voice regression:** place ONE real test call to `6375548830`, confirm transcript+summary and
    eou/TTFT within baseline (compare to UNIT 0). `systemctl is-active famit-agent famit-caller` both
    active. `docker stats` shows Hatchet containers within limits.
  - Rollback: `docker compose down` removes Hatchet entirely; site untouched (nothing references it yet).

### UNIT 2 — Worker scaffold + client + flags + smoke (no workflow live) — **sonnet**
- Create `orchestration/{__init__,client,flags,models,workflows,worker}.py` + `_smoke_orch.py`.
  `client.get_hatchet()` returns `None` if token/SDK absent (import-safe degrade). `pip install
  hatchet-sdk` into `/opt/capsy-agent/.venv`. Add `infra/systemd/famit-orchestrator.service`.
- **ACCEPT:** `python _smoke_orch.py` instantiates client+all 5 workflow objects without error;
  `systemctl start famit-orchestrator` → worker connects (dashboard shows worker, **registers 0
  flag-eligible workflows** because all flags=legacy); `famit-caller`/`famit-agent` untouched;
  importing `orchestration` into `caller.py` (lazy, behind flag) does not change any `/api` response
  (`md5`-stable behavior; smoke all 200s). Rollback: `systemctl stop famit-orchestrator`.

### UNIT 3 — `vendor-sync` cutover (FIRST live workflow; no calls placed) — **sonnet**
- Implement `vendor-sync` workflow (§4.1) + `_vendor_sync_due()` file-timestamp helper. Worker
  registers it when `ORCH_VENDOR_SYNC=hatchet`. Guard `scheduler_loop`'s vendor duties to **skip**
  when the flag is hatchet (no double-run).
- Flip `ORCH_VENDOR_SYNC=hatchet`; restart `famit-orchestrator` + `famit-caller`.
- **ACCEPT (durability + correctness, zero dial impact):**
  - Dashboard shows `vendor-sync` running each minute; `var/cost_ledger.json` + `daily_rollups.json`
    keep updating; `GET /billing/overview` + `/billing/audit` unchanged in shape, values fresh.
  - **Durability proof:** `docker restart` the engine / `systemctl restart famit-orchestrator`
    mid-tick → next tick resumes, no duplicate snapshots, ledger consistent.
  - `scheduler_loop` no longer runs the vendor duty (log shows the skip); retries+reconcile sweep
    STILL run in legacy (untouched). No call placed. Voice unaffected.
  - **Rollback:** `ORCH_VENDOR_SYNC=legacy` + restart → `scheduler_loop` resumes vendor duty; identical to before.

### UNIT 4 — `wa-cadence` (NET-NEW durable; dormant until WA creds) — **sonnet**
- Implement §4.2 + helpers `_wa_thread_get`, `_wa_send_followup_step` (thin wrappers over existing
  `whatsapp.py` + `wa_threads` store). Trigger from `_finalize_call` behind `ORCH_WA_CADENCE=hatchet`
  AND campaign `wa_cadence` schedule present. Default OFF (no schedule, no creds → no-op).
- **ACCEPT:** with a TEST campaign carrying a short cadence (`after_hours` set to minutes for the
  test via an override) and WA in `not_configured`, trigger a finalize → dashboard shows a
  `wa-cadence` run sleeping durably; restart worker → same run resumes the SAME sleep (not a new one);
  on `opted_out` thread status the run stops. Because WA is dormant, no message actually sends
  (logged `not_configured`). **Idempotency:** fire the trigger twice with the same `key` → ONE run.
  Rollback: `ORCH_WA_CADENCE=legacy`.

### UNIT 5 — `retry-callback` cutover (delayed runs replace polling) — **sonnet→opus** (opus for the finalize edit)
> ⚠️ **OVERRIDDEN by RTF-1 + RTF-5 + RTF-11:** pre-req is the FULL finalize write-set in `dual`/`pg` (not
> just `retry`), `_emit_webhook` must be made idempotent, and the dial-claim must be the atomic
> write-ahead version. This unit is **NO-GO until P1 (currently U1) migrates that set.**
- **Pre-req (per RTF-1):** P1 has `retry`, `calls`, `leads`, `suppression` **AND** `billing`, `ledger`,
  `wa_log`, `wa_threads`, `webhook_log` in `dual`/`pg` (the finalize chain writes ALL of these
  cross-process). Assert via `/admin/store-status`. P1 is at U1 today → this is a real block, not theoretical.
- Implement §4.3. In `_finalize_call`, the retry/callback branch: flag=hatchet →
  `retry_wf.run_no_wait(key=...)`; flag=legacy → `_enqueue_retry` (unchanged). Guard
  `scheduler_loop`'s retry-dispatch to skip when flag=hatchet.
- **ACCEPT:** trigger a finalize that schedules a callback 2 min out (test) → dashboard shows a
  durable `retry-callback` sleeping; at T+2min it re-checks window+suppression then dials via
  `dial_one_lead` (the SAME path). Add the number to suppression mid-sleep → run returns
  `skipped:suppressed`, no call. Restart worker mid-sleep → run resumes. **Idempotency:** duplicate
  finalize (same attempt) → ONE retry run. Legacy retry path verified still works when flag=legacy.
  Rollback: `ORCH_RETRY_CALLBACK=legacy`.

### UNIT 6 — Extract `dial_one_lead()` (refactor; behavior identical) — **opus**
- Extract `caller.py:1642–1682` into `async def dial_one_lead(item, *, tenant_id, cid, cname,
  camp_fields, lk, variant pool ctx...) -> dict`. `run_job` (legacy) now CALLS it — **legacy behavior
  must be byte-for-byte unchanged.** Add the §5 dial-claim idempotency guard INSIDE `dial_one_lead`
  (no-op on the legacy single-process path since claims are written+checked the same).
- **ACCEPT:** `ORCHESTRATOR` still `legacy`; run a real campaign via `/run` (legacy `run_job`) to the
  test number → identical dial behavior, one call, record written, `/status` shows progress. Diff:
  the refactor changes structure only (prove with a legacy `/run` end-to-end call). Commit as a pure
  refactor BEFORE wiring Hatchet to it.
- **ALSO (process-global audit, §0.4):** enumerate every `caller.py` global the worker's activities
  will touch (`CALLS`, `LEADS`, `ACTIVE_CALLS`, `_LAST_VENDOR_SYNC`) and confirm each is either
  (a) replaced (ACTIVE_CALLS→CEL key, _LAST_VENDOR_SYNC→file), or (b) read through the P1 Store seam
  so uvicorn and the worker share one source of truth. Record the audit in `ORCHESTRATION_STATE.md`.

### UNIT 7 — `campaign-run` cutover (LAST; the call-placing write path) — **opus**
> ⚠️ **OVERRIDDEN by RTF-1 + RTF-5 + RTF-8 + RTF-11:** pre-req is the FULL finalize write-set (not just
> calls/leads/suppression); webhook emits must be idempotent; the dial-claim must be atomic write-ahead
> (the spec's stated #1 guard is currently broken — RTF-11); and ACCEPT must add webhook-fires-once,
> cross-process record-visibility, and a CONCURRENT double-fire test. **NO-GO until all fold + P1 done.**
- **Pre-req (HARD, per RTF-1):** P1 has `calls`, `leads`, `suppression` **AND** `billing`, `ledger`,
  `wa_log`, `wa_threads`, `webhook_log` in `dual`/`pg`. Assert `/admin/store-status`. If not → STOP, leave
  `ORCH_CAMPAIGN_RUN=legacy`, record the block in `ORCHESTRATION_STATE.md`.
- Implement §4.4 (fan_out + dial-lead child with CEL concurrency + finalize). `POST /run`: flag=hatchet
  → `campaign_run_wf.run_no_wait`, populate `RUN_INDEX`, return same JSON; flag=legacy → `JOBS`/
  `run_job`. `GET /status` read-back (§6). Keep the reconciliation sweep as a cron.
- **ACCEPT (the big one):**
  - Flip `ORCH_CAMPAIGN_RUN=hatchet`. `POST /run` (test campaign, the test number) → returns
    `{job_id,count}`; dashboard shows a `campaign-run` run + child `dial-lead`; ONE real call lands.
  - **Idempotency / crash-safety:** `systemctl restart famit-orchestrator` MID-CAMPAIGN → **no lost
    leads, no double-dial** (verify exactly one SIP call per number via Vobiz CDR / dial-claim files).
  - **Concurrency:** launch >cap leads for one tenant → never more than `max_runs` concurrent
    `dial-lead` runs (dashboard + `_phone_present` checks).
  - `_finalize_call` runs once per call (classify/score/retry/WA/webhook correct); `/billing` not
    double-charged; transcript+summary present.
  - `/status` shows identical shape to legacy. Voice latency within baseline. Legacy path verified by
    flipping back.
  - **Rollback:** `ORCH_CAMPAIGN_RUN=legacy` + restart `famit-caller` → in-flight finishes on Hatchet,
    new `/run` uses legacy `JOBS`; site fully functional.

### UNIT 8 — Decommission-in-place guards + docs — **sonnet**
- Once all four flags are `hatchet` and stable for N days: `scheduler_loop` becomes a thin
  reconciliation-only cron (or itself a Hatchet `reconcile` cron); `JOBS`/`RETRY_FILE` left as legacy
  fallback (do NOT delete — they are the rollback). Update `HANDOFF.md` + `ORCHESTRATION_STATE.md`.
- **ACCEPT:** a full restart of `famit-caller` mid-campaign loses nothing (all durable in Hatchet);
  flipping any flag back to legacy still works (rollback intact).

---

## 8. ACCEPTANCE-TEST COMMANDS (reusable; run from the box / via SSH)

```bash
# Services + no-regression
ssh -i C:\Users\kunal\.ssh\do-blr-test\id_ed25519 famit@168.144.153.145 \
  'systemctl is-active famit-agent famit-caller famit-orchestrator; docker ps --format "{{.Names}} {{.Status}}"'

# Hatchet health + container resource ceiling (voice-box guard)
ssh famit@168.144.153.145 'curl -s 127.0.0.1:8888/api/ready; docker stats --no-stream \
  --format "{{.Name}} cpu={{.CPUPerc}} mem={{.MemUsage}}"'

# API contract unchanged (run before+after each unit; must all be 200 + same shape)
for p in stats campaigns leads "calls?limit=5" billing/overview billing/audit me usage; do
  curl -s -o /dev/null -w "%{http_code} /$p\n" -H "X-Auth: FamitCall2026" https://panel.famit.in/api/$p; done

# Live metered test call (the universal end-to-end gate)
curl -H "X-Auth: FamitCall2026" -X POST https://panel.famit.in/api/run \
  -F campaign_id=66c3b656af -F "leads=Kunal Kumar, 6375548830" -F concurrency=1
#   → then GET /api/status?job=<id> shows progress; user answers; transcript+summary+₹cost appear.

# Dial-idempotency proof (UNIT 7): during the call, restart the worker, then count SIP calls
ssh famit@168.144.153.145 'systemctl restart famit-orchestrator; ls /opt/famit-agent/var/dial_claims/'
#   + cross-check Vobiz CDR count for the number == 1.
```

**Global gate after EVERY unit** (master plan §Verification): login/campaigns/leads/run/calls/billing
unaffected; `famit-caller`/`famit-agent`/`famit-panel` active; one real metered call yields
transcript+summary+₹cost; per-unit backup + build_log + commit so a crash costs ≤ one unit.

---

## 9. SEPARATE ORCHESTRATION DB (the named scale trigger — spec now, execute later)

Master plan: **at >60k calls/day OR p95 lead-memory read >50ms**, separate the Hatchet/orchestration
DB from the OLTP/voice-read DB (FIRST scale trigger — noisy-neighbor guard).
- **Now:** Hatchet's Postgres is a dockerized logical DB on `famit-livekit`, already isolated from the
  app `famit` DB and JSON stores, with cpu/mem limits.
- **Trigger action:** provision a **DO Managed Postgres (blr)** instance dedicated to Hatchet (or a
  separate droplet's Postgres); point hatchet-lite/engine `DATABASE_URL` at it; migrate the `hatchet`
  schema (Hatchet's own migrate image handles DDL). The app `famit` DB (P1) and the voice read path
  are untouched — the whole point is removing Hatchet's write load from the voice box.
- **Watch metric:** Hatchet Postgres CPU + RabbitMQ depth + the voice agent's eou/TTFT; if Hatchet
  containers approach their cpu limit, that is the early signal to split BEFORE 60k/day.
- Also at this tier: the reconciliation sweep → durable "wait-for-transcript event" so finalize is
  fully event-driven (retire the polling sweep).

---

## 10. ROLLBACK SUMMARY (per layer)
| Layer | Rollback |
|---|---|
| Any single workflow | set its `ORCH_*` flag back to `legacy` + restart `famit-caller`(+worker); the matching `scheduler_loop`/`JOBS`/`RETRY_FILE` legacy path resumes (never deleted). |
| Whole orchestrator | `ORCHESTRATOR=legacy` (all per-workflow unset) + `systemctl stop famit-orchestrator`; uvicorn is 100% legacy. |
| Hatchet infra | `docker compose -f docker-compose.hatchet.yml down`; nothing in `/api` references it when flags=legacy. |
| Code | each unit is a separate commit; `git revert <sha>` of one unit; `caller.py.*bak.<ts>` box backups per deploy (existing recipe). |

## 11. DEPENDENCIES
- **P1 Postgres strangler** (`P1_FOUNDATION_STATE.md`) — HARD pre-req for `retry-callback` (UNIT 5)
  and `campaign-run` (UNIT 7): `calls`/`leads`/`suppression`/`retry` in `dual`/`pg` (cross-process
  write safety). `vendor-sync` + `wa-cadence` do NOT need it.
- **pip:** `hatchet-sdk` (pin a version) into `/opt/capsy-agent/.venv`.
- **Docker + docker compose** on `famit-livekit` (verify installed; LiveKit already runs in docker).
- **WA creds (Meta)** — only to make `wa-cadence` actually send (it is dormant/no-op until then).
- **No new founder credentials** required for UNITs 0–4 (mirrors the plan: Phase 0–3 need none).

## 12. MODEL ROUTING (for the implementing agent)
- **opus:** orchestration design glue in `workflows.py`; idempotency + `dial_one_lead` extraction
  (UNIT 6); `_finalize_call` edits (UNIT 5); `campaign-run` cutover + `/status` read-back (UNIT 7).
  (Matches the master plan's Phase-3 = opus.)
- **sonnet:** compose + systemd + deploy (UNIT 1); worker/client/flags scaffold (UNIT 2);
  `vendor-sync` (UNIT 3); `wa-cadence` (UNIT 4); decommission guards (UNIT 8).
- **haiku:** mechanical acceptance-script scaffolding, `__init__.py`, `_smoke_orch.py`,
  `.env.hatchet.example`.

## 13. OPEN RISKS / WATCH-ITEMS
1. **Hatchet footprint on the voice box** — even resource-limited, RabbitMQ+Postgres+engine add load
   to the latency-critical box. Mitigation: strict limits + the no-regression call gate per unit +
   the §9 split is pre-specified. If eou/TTFT regress at UNIT 1, STOP and move Hatchet to its own
   droplet before proceeding.
2. **P1 timing** — if P1 hasn't migrated `calls`/`leads` when this work reaches UNIT 7, `campaign-run`
   is BLOCKED (cross-process JSON corruption). UNITs 0–4 proceed regardless; record the block.
3. **Dial double-fire** — the single highest-severity correctness risk. The **app-level dial-claim
   guard** (§5, `var/dial_claims/<cid:phone:attempt>`) + `retries=0` on the dial task are the
   backstop; the forced-worker-restart test in UNIT 7 is the proof gate. Do NOT lean on a Hatchet
   caller-key for this — `run_no_wait` only exposes `child_key` (child-run dedup), confirmed in docs;
   top-level triggers have no caller-key dedup. `create_bulk_run_item(key=...)` in the fan-out IS
   doc-confirmed and helps, but the dial claim is the authoritative guard. Do not ship UNIT 7 without it.
8. **Top-level run dedup gap (wa-cadence)** — because no caller-key dedup exists for top-level
   `run_no_wait`, a duplicate `_finalize_call` could start two multi-day WhatsApp cadences; the
   `_wa_cadence_claim` app marker (§4.2/§4.5) is required and its double-trigger test is in UNIT 4.
4. **`/status` semantics drift** — the Run page is unforgiving about shape; map Hatchet states
   carefully (§6) and diff against a legacy run before flipping.
5. **SDK version pin** — Hatchet's API moved (V0 `@step` → V1 task). Pin the SDK + engine `V1`; if a
   newer SDK changes signatures, re-pull context7 docs before editing (do not code from memory).
6. **Concurrency granularity** — v1 uses a constant `max_runs`; per-tenant dynamic cap (CEL on
   `input.tenant_id` with the tenant's real `max_concurrency`) is a fast-follow; note in STATE.
```

---

## RED-TEAM FIXES (folded) — principal review 2026-06-09

Adversarial review against live source (`caller.py` md5 `a60b8a9e…`, 3422 lines — citations re-verified,
all accurate), `P1_FOUNDATION_STATE.md` (**P1 is at U1 IN PROGRESS — `store.py` does NOT exist yet, NO
store migrated**), the master plan, and current Hatchet docs. SDK + line-cite claims VERIFIED — do not
redo them. The fixes below are **binding overrides** to the sections named; where they conflict with
body text, these win.

### RTF-1 (BLOCKING, changes UNIT 7 gate) — the P1 write-set gate in §0.3 is UNDER-SCOPED
`_finalize_call` (the `finalize-call` activity) writes **far more than `calls/leads/suppression/retry`**,
all under the cross-process-blind `_STORE_LOCK`, and **uvicorn writes the SAME files from live
endpoints**:
| Store written in the finalize chain | line | also written by LIVE uvicorn endpoint |
|---|---|---|
| `BILLING_FILE` + `ledger/<tid>.json` (`_charge_call`) | 1312/1360/1365 | `POST /billing/{tenant_id}` (2768→2800), `POST /billing/sync` |
| `wa_log.json` (`_send_whatsapp`/`_wa_ai_followup`) | 989/1003 | `POST /whatsapp/send` (2807) |
| `wa_threads/<phone>.json` (`_wa_thread_write`) | 1056 | `POST /whatsapp/inbound` (2900, **no-auth Meta webhook**) |
| `webhook_log.json` (`_emit_webhook`) | 1285 | webhook delivery from any emit path |
| `calls.json` (`record_call`/`_write(CALLS_FILE, CALLS)`) | 814/1493/1505 | (worker writes the WHOLE in-RAM `CALLS` list → can clobber uvicorn's) |

**FIX:** UNIT 7 (and UNIT 5, which also runs the finalize chain via `dial_one_lead`→retry) pre-req is
upgraded: P1 must have `calls, leads, suppression, retry` **AND `billing`, `ledger`, `wa_log`,
`wa_threads`, `webhook_log`** in `dual`/`pg` (or otherwise single-writer cross-process). If any of those
stores is still file-`json` with a live uvicorn writer, finalize-on-the-worker can corrupt it. Update
§0.3, §11, and the UNIT 5/7 `/admin/store-status` assertion to enumerate the FULL set. *(Note: P1's
current U-list, `P1_FOUNDATION_STATE.md`, only plans `leads→calls→suppression→retry`; billing/wa/webhook
PG migration is NOT yet in P1 scope → either P1 grows or these stay legacy. Surface this to the P1 owner.)*

### RTF-2 (BLOCKING — security hole on a box already compromised once) — Hatchet container ports
§1/§UNIT 1 bind only the **dashboard `8888`** and **gRPC `7077`** to `127.0.0.1`, and are SILENT on
**Postgres `5432`, RabbitMQ AMQP `5672`, and the RabbitMQ management UI `15672`**. Docker `ports:`
publishes to `0.0.0.0` **and inserts its own DOCKER-USER iptables rule that BYPASSES ufw** — on
`famit-livekit` (the box whose sibling `famit-voice-2` was deleted for outbound DDoS, per the FORTRESS
report), an exposed AMQP/management/Postgres port is a live attack surface.
**FIX (mandatory in `docker-compose.hatchet.yml`):** every published port MUST be `127.0.0.1`-bound
(`"127.0.0.1:5432:5432"`, `"127.0.0.1:5672:5672"`, `"127.0.0.1:15672:15672"`, `"127.0.0.1:8888:8888"`,
`"127.0.0.1:7077:7077"`) **or — preferred — declare NO `ports:` at all** and let the engine/worker reach
postgres+rabbitmq over the compose-internal network (only `7077` and `8888` need host exposure, both
loopback). UNIT 1 ACCEPT gains a step: `ss -tlnp | grep -E '5432|5672|15672|7077|8888'` shows **only
`127.0.0.1`** bindings, and `iptables -L DOCKER-USER -n` confirms no `0.0.0.0` Hatchet publish slipped in.
Disable the RabbitMQ management plugin entirely if not needed.

### RTF-3 (BLOCKING pre-flight; recommend default change) — co-locating Hatchet on the voice box
The master plan names **noisy-neighbor on this exact box as the FIRST scale trigger**, voice as priority
#1, and **infra cost as "a rounding error."** The spec stacks `hatchet-lite + postgres + rabbitmq`
(~1.66 GB of declared limits: 768+512+384 M) onto a box ALREADY running LiveKit server+SIP+redis (docker)
+ `famit-agent` + `famit-caller` + `famit-bridge`. A "stop if eou/TTFT regress" gate is a *weaker*
substitute for not gambling the earning box, because OOM/CPU-steal manifests under call LOAD, not during
a single idle test call.
**FIX:**
1. **HARD pre-flight in UNIT 1 (else it fails on the real box):** query free RAM/CPU on `famit-livekit`
   **before** `compose up` — `ssh … 'free -m; nproc; docker stats --no-stream'` — and abort co-location
   if headroom < (sum of limits + 30% voice burst). Record the numbers in `ORCHESTRATION_STATE.md`.
2. **Recommended default: put Hatchet on its OWN cheap droplet (blr, same VPC) from UNIT 1**, not on
   `famit-livekit`. This removes the single largest risk in this whole plan (voice regression) for ~$6/mo,
   matches the plan's noisy-neighbor-first principle and "cost is a rounding error," and makes RTF-2 moot
   (Hatchet ports never touch the voice box; worker connects over the private VPC `10.x`, ufw-allowed).
   The §9 "separate orchestration DB" trigger then only concerns the DB tier, not the engine. If the
   founder insists on co-location, the §UNIT 1 RAM gate + a **load** test (≥cap concurrent calls, not one)
   is the minimum bar. Update §1.1 to make a separate droplet the DEFAULT and co-location the override.

### RTF-4 (BLOCKING for cutover ORDER) — `vendor-sync` is NOT a clean read-only first cutover
The spec's whole ordering rests on "`vendor-sync` is single-writer + idempotent → safe FIRST." **False on
the live box:** `POST /billing/sync` (line 2748, a LIVE admin endpoint behind the Billing "Refresh now"
button) calls `vendor_sync()` (2759), which writes `COST_LEDGER_FILE` (3176), `DAILY_ROLLUPS_FILE` (3194)
and `VENDOR_SNAPSHOTS_FILE` (3269) — **the exact files the Hatchet `vendor-sync` cron will own.** Admin
clicks Refresh while the worker tick runs `vendor_sync` ⇒ two processes, two non-shared locks, one
`cost_ledger.json` ⇒ corruption. Same hazard for `record_usage_event`→`usage_events.json` (1396/1457) and
the agent's `usage_events_raw` drop drained by `_drain_usage_raw` (the agent is a THIRD process already
writing raw files — fine, it's at-most-once per file — but the drain must have exactly one owner).
**FIX (UNIT 3):** when `ORCH_VENDOR_SYNC=hatchet`, the **`POST /billing/sync` handler MUST NOT call
`vendor_sync()` in-process** — it must trigger the Hatchet workflow (`vendor_sync_wf.run_no_wait(...)`,
or enqueue a one-shot run) so the worker remains the **sole writer** of
`cost_ledger/daily_rollups/vendor_snapshots/usage_events`. **Frontend-contract guard:** the WAVE-A
"Refresh now" button expects `POST /billing/sync` → `{ok, synced_at, vendors}`. Do NOT silently change it
to `{queued:true}` — either keep returning the last on-disk snapshot in that exact shape (trigger the run,
then read+return the current `vendor_snapshots`) or update the frontend in lockstep. Breaking that shape
is a live UI regression. Add this branch to the §2 `caller.py` EDIT
list and to §4.1. UNIT 3 ACCEPT gains: with the flag hatchet, hit `POST /billing/sync` AND let a cron
tick fire concurrently → confirm no JSON corruption and a single writer (grep the logs; the in-process
path must be skipped). Until that branch exists, `vendor-sync` is **NOT** safe-first.

### RTF-5 (BLOCKING idempotency hole the spec claims is already closed) — webhooks double-fire on re-run
§5 asserts `_emit_webhook` is "already guarded by `_wh_completed`/`_reconciled` … verify the flag is set
BEFORE the activity can re-run." **The live code does NOT satisfy this.** In `_finalize_call`:
- `call.completed` is emitted **unconditionally** at line 1538 — there is **no `if not
  rec.get("_wh_completed")` guard around it.** `_wh_completed` (set at 1537) only gates the *reconciliation
  sweep's* later re-emit (in `scheduler_loop`), **not** a re-run of `_finalize_call` itself.
- `lead.qualified` (1546) and `lead.opted_out` (1506) are likewise unconditional per finalize invocation.

So under Hatchet at-least-once, a crashed-then-retried `finalize-call` **sends duplicate
`call.completed` + `lead.qualified` to the tenant's CRM** (and a duplicate WhatsApp via `_send_whatsapp`
at 1527, whose only "guard" is the cadence key on a *different* path).
**FIX (UNIT 5/7, `caller.py` EDIT):** make the emit idempotent at the source. Persist a per-event sent
marker on the call rec **before** emitting and gate on it: e.g. guard each emit with
`if not rec.get("_wh_completed"): … set rec["_wh_completed"]=True; persist; emit`, and add
`_wh_qualified`, and a per-`(phone,call_id)` WA-sent marker (matches §5's WA row). Set-and-persist BEFORE
the network call so a re-run sees the marker. Add an explicit ACCEPT to UNIT 7: **force a finalize
re-run (kill worker after charge, before return) and assert EXACTLY ONE `call.completed` and ONE
`lead.qualified` were delivered** (capture at a test webhook sink). This test is currently MISSING — the
spec only checks "not double-charged."

### RTF-6 (correctness — refactor boundary) — `dial_one_lead` is NOT "byte-for-byte unchanged"
The inline block `1642–1682` mutates loop-local state that Hatchet has no equivalent for: `variant_idx`
(1648), `active`/`started_ts`/`hourly`/`daily` (1675), `ACTIVE_CALLS[tenant]` (1674), and `idx` was
already bumped at 1641. You cannot extract all of that and keep legacy "byte-for-byte" — the legacy loop
NEEDS that bookkeeping; the Hatchet path REPLACES it with the concurrency key.
**FIX (UNIT 6):** define a clean seam — `dial_one_lead(item, *, tenant_id, cid, cname, camp_fields, lk,
variant_pool, variant_idx) -> (rec | None)` does ONLY `{variant pick → create_room → create_dispatch →
create_sip_participant → build rec → record_call → return rec (with room/sip_call_id)}`. **Each caller
owns its own concurrency/loop accounting**: legacy `run_job` keeps the `ACTIVE_CALLS`/`active`/`started_ts`
mutations around the call; the Hatchet `dial-lead` task relies on the CEL key and writes nothing
loop-local. Restate §1.5/§4.4/UNIT 6 as "behavior-preserving extraction of the *dialing* steps" (NOT the
loop control), and UNIT 6 ACCEPT must include a **legacy `/run` end-to-end diff** (one real call, record
identical) before any Hatchet wiring. The dial-claim (§5) goes INSIDE this seam so both callers share it.

### RTF-7 (worker import-safety) — prove `import caller` is side-effect-free in a bare process
The worker runs under `/opt/capsy-agent/.venv` python but `import caller` from `/opt/famit-agent`;
`caller.py` builds the FastAPI `app` and runs `CALLS = _read(CALLS_FILE, [])` (line 683) **at import
time**. The §0.4 note that `@app.on_event("startup")` (3402) won't fire in the worker is CORRECT and
verified — but import itself must not hang, bind a port, or fork the scheduler.
**FIX (UNIT 2 ACCEPT):** in a bare non-uvicorn process, `python -c "import caller"` must complete with
**no port bind, no hang, no background task**, and pin systemd `WorkingDirectory=/opt/famit-agent` (so
`VAR`/relative paths resolve to the same `var/` uvicorn uses — otherwise the worker reads/writes a
DIFFERENT `var/` and §0.4 divergence is guaranteed, not merely possible). Confirm `EnvironmentFile`
points at the SAME `/opt/famit-agent/.env`.

### RTF-8 (acceptance gap) — cross-process record VISIBILITY is audited but never tested
§0.4 audits the `CALLS`/`LEADS` divergence but no test proves it's actually closed.
**FIX:** add to UNIT 7 ACCEPT — **write a call row via the worker (a real dial-lead), then `GET /calls`
on uvicorn and confirm the row is present and identical.** This is the only test that proves the worker
and uvicorn share one source of truth (P1 `pg`/`dual` working end-to-end across processes), rather than
each mutating its own in-RAM `CALLS` list. If it fails, UNIT 7 is not done regardless of dashboard state.

### RTF-9 (scope honesty, not blocking) — `wa-cadence` (UNIT 4) is NET-NEW feature work, not a strangle
A multi-day cadence "does not exist in legacy" (§4.2 says so). Therefore UNIT 4 is **new Phase-7 product
surface**, not a like-for-like migration of an in-RAM thing — it adds build surface and a fresh idempotency
gate (`_wa_cadence_claim`) to what is otherwise an infra cutover, and it's dormant until Meta creds.
**FIX:** label it explicitly as net-new scope (not migration) and make it **deferrable** — the orchestrator
cutover (UNITs 0–3, 5–7) does not depend on it. Recommend sequencing it AFTER `campaign-run` is stable, or
splitting it into the Phase-7 WhatsApp track entirely. No correctness objection to the durable-task design
itself (verified against docs); this is a scope/sequencing flag.

### RTF-11 (BLOCKING for UNIT 7 GO) — the dial-claim mechanism in §5 is itself broken (two ways)
§5 calls the dial-claim "the single most important guard" against double-dialing, then specifies it as
`var/dial_claims/<key>.json` **"written under `_STORE_LOCK`,"** recording `room+sip_call_id`. Both halves
defeat the purpose:
1. **`_STORE_LOCK` is precisely the primitive §0.3 proves does NOT span processes.** Guarding the
   double-dial claim with it gives **zero** mutual exclusion for the two races that matter:
   worker-vs-uvicorn (legal during rollback/flag-flip — §10 explicitly allows "in-flight finishes on
   Hatchet, new `/run` uses legacy," so both processes can dial concurrently) and worker-vs-worker
   (horizontal Hatchet workers are the entire point). An `asyncio.Lock` serializes only coroutines in ONE
   event loop.
2. **The claim records `sip_call_id`, i.e. it is written AFTER the dial → the crash window still
   double-dials.** Sequence: check (no claim) → `create_sip_participant` → **crash before writing claim**
   → re-run: check (still no claim) → **dials again.** The existing "kill worker mid-dial → exactly one
   SIP call" ACCEPT (UNIT 7) only exercises *sequential* recovery and would PASS while this race stays open.
**FIX:** make the claim **write-ahead + atomic with an OS primitive, not `_STORE_LOCK`:**
`fd = os.open(path, os.O_CREAT|os.O_EXCL|os.O_WRONLY)` (atomic create-if-absent on the local fs) keyed on
`(cid,phone,attempt)` **BEFORE `create_room`**; on `FileExistsError` → skip/return the existing record; on
success, dial, then update the file with `room/sip_call_id`. Once P1 lands, replace with a PG row under a
**UNIQUE(`cid,phone,attempt`)** constraint (insert-then-dial; unique-violation = already claimed) — the
only cross-process-safe version. `_wa_cadence_claim` (§4.5) has the **identical flaw**; apply the same
O_EXCL/unique-constraint fix. Add to UNIT 7 blockers; add a **concurrent** (not just sequential) double-fire
test: trigger two dial-lead runs for the same `(cid,phone,attempt)` simultaneously → exactly one SIP call.
Legacy stays byte-for-byte: O_EXCL always succeeds first-time per lead+attempt, so `run_job` behaves
identically; the claim file is a new side-artifact in `var/` (keep UNIT 6's diff scoped to the call RECORD,
not `var/` contents).

### RTF-10 (minor, fold opportunistically)
- **`on_failure_task` exists** (doc-confirmed) and is the clean place to release a failed `dial-lead`'s
  resources / emit a `dial.failed` signal — the spec doesn't use it. Optional, not required for v1.
- **`durable_task` default `retries=0`** (doc-confirmed) — the spec's explicit `retries=0` on the dial
  task is therefore redundant-but-correct (keep as documentation of intent).
- **§13 risk list numbering is broken** (1,2,3,**8**,4,5,6) and the trailing ` ``` ` fence wraps prose —
  cosmetic; renumber when next editing.
- **`/status` read-back accessor** is honestly flagged VERIFY-BEFORE-IMPLEMENT (§6) — the doc pull here
  also did not surface a confirmed `runs.get(...)` by `workflow_run_id`; keep that gate, do not ship from
  memory. The `key=` dedup on `create_bulk_run_item` IS confirmed; the no-top-level-caller-key limitation
  the spec relies on for §4.2/§4.3 is consistent with what docs expose (dedup is on the child/bulk item).

### REVISED GO / NO-GO (by unit)
- **UNIT 0** (baseline) — **GO.**
- **UNIT 1** (deploy Hatchet) — **GO, conditional on RTF-2 (loopback-only ports) + RTF-3 (RAM pre-flight;
  STRONGLY prefer separate droplet).**
- **UNIT 2** (scaffold/worker, 0 live workflows) — **GO, conditional on RTF-7 (import-safety + WorkingDirectory).**
- **UNIT 3** (`vendor-sync`) — **GO, conditional on RTF-4 (route `POST /billing/sync` through Hatchet so
  the worker is sole writer).** Without RTF-4 it is NOT safe-first.
- **UNIT 4** (`wa-cadence`) — **DEFER (RTF-9).** GO only if the founder wants the Phase-7 feature now;
  not on the cutover critical path.
- **UNIT 5** (`retry-callback`) — **NO-GO / BLOCKED** until P1 migrates the FULL finalize write-set
  (RTF-1), not just `retry`. Design is sound; gate is the blocker. RTF-5 (webhook idempotency) must ship
  in the same unit.
- **UNIT 6** (extract `dial_one_lead`) — **GO as a pure refactor** once restated per RTF-6 (extract dialing
  steps only, not loop control) with the legacy `/run` diff in ACCEPT. Independent of P1.
- **UNIT 7** (`campaign-run`) — **NO-GO / BLOCKED** until P1 full write-set (RTF-1) + RTF-5 + **RTF-11
  (atomic write-ahead dial-claim — the spec's stated #1 guard is currently broken)** + the new ACCEPT
  tests (RTF-5 webhook-once, RTF-8 cross-process visibility, RTF-11 CONCURRENT double-fire). Highest
  blast radius; do not flip `ORCH_CAMPAIGN_RUN=hatchet` before all of these.
- **UNIT 8** (decommission guards) — **GO** after 0–7 stable.

**Net:** the design is architecturally sound and unusually well-grounded; no rebuild, flags fail-closed,
reuse-over-rewrite is right. But **3 "safe" claims are false on the live box** (vendor-sync sole-writer,
webhook idempotency, finalize write-set scope) and **2 security/latency holes** (open Hatchet ports,
voice-box co-location) must close first. With RTF-1…RTF-8 folded, **GO for the infra+read-path half
(UNITs 0–3,6); the call-placing/finalize half (UNITs 5,7) stays BLOCKED on P1 — which is at U1, so that
block is real today, not theoretical.**

