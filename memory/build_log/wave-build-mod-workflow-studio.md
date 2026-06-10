# WAVE BUILD — MODULE workflow-studio (Workflow Automation Studio engine)

Built 2026-06-10. Local-only (no git, no deploy, no service restart). Spec:
`design/platform-workflow-studio.md` (primary) + `design/orchestration-hatchet.md` (Hatchet substrate).
All NEW files under `droplet_work/workflow-studio/`. Importable inner package = `workflow/` (matches the
spec's `from workflow.endpoints import router`). Offline acceptance test 11/11 GREEN, zero creds/network.

## WHAT IT IS
The connective tissue of the Autonomous Business OS: a durable, multi-tenant, crash-safe visual-automation
engine. A vendor / the AI Manager / a template wires Trigger -> Condition -> AI-Agent/Action/Integration
steps with Budget/Approval/Delay/Wait/Data/Error nodes; it runs on Hatchet (when configured) or the SAME
interpreter in-process (when dormant), with HARD code-enforced safety rails. "n8n UX, native engine" —
MIT React-Flow canvas is a deferred frontend follow-up (this wave = engine + node lib + router).

## FILES CREATED (all under droplet_work/workflow-studio/)
- `workflow/__init__.py`     — public surface: validate / publish / run / resume / reject / cancel /
                               killswitch_tenant / instantiate_template / workflow_analytics / status;
                               default_deps() wires the live F4 wallet + firewall + workforce registry.
- `workflow/dsl.py`          — the Workflow JSON DSL (Pydantic-optional stdlib validator): Node/Edge/
                               WorkflowDefinition + parse_definition (shape validation). 10 node types.
- `workflow/sandbox.py`      — the restricted expression evaluator (ast allow-list, NO eval, NO attribute
                               access, NO imports) for condition/`when`/`expr` (spec §7.4).
- `workflow/compiler.py`     — static validate + the DOMINATOR safety check (every money/bulk/destructive/
                               export node must be dominated by a BUDGET node, and money/destructive/export
                               by an APPROVAL node, on every path) + expr sandbox + cycle check (delay/wait-
                               gated only) + freeze_version (immutable snapshot + sha256 hash).
- `workflow/nodes.py`        — the 10 node executors + the per-node gates (budget reserve, money recompute-
                               from-resolved-args + cap-block + settle, approval park/step-up, DND/window,
                               dormant-integration no-op). RunCtx + NodeResult. Wallet/firewall duck-typed.
- `workflow/interpreter.py`  — the ONE generic durable orchestrator (run_workflow): walks the graph,
                               write-ahead CLAIM per (run_id,node_id,attempt) => replay-safe / no double-
                               spend, kill-switch (top + per-node), max_actions cap, budget-hold release,
                               immutable audit per node, park/resume contract, edge routing.
- `workflow/engine.py`       — Hatchet binding, DORMANT-UNTIL-CREDS: get_hatchet() -> None w/o token;
                               build_durable_task() registers the single `wf-run` @hatchet.durable_task
                               (input_validator=, brain learning) injecting ctx.aio_sleep_for / aio_wait_
                               for_event into the interpreter; run_in_process() = the always-available path.
- `workflow/store.py`        — dual backend (InMemoryStoreBackend + PgStoreBackend) over the 6 tables;
                               RLS via db.engine.session(); claim_key UNIQUE = write-ahead idempotency.
- `workflow/schema.sql`      — the 6 PG tables (wf_definitions/versions/runs/node_runs/triggers/schedules)
                               + RLS admin-GUC policies (db/rls.sql shape). INERT until the live-PG unit.
- `workflow/events.py`       — the Lifecycle Trigger bridge: spine emit -> workflow event run, deduped by
                               (workflow_id,event_id). attach_event_bridge() DEFINED-not-called.
- `workflow/analytics.py`    — deterministic per-workflow roll-up over wf_runs + wf_node_runs (no new write).
- `workflow/templates.py`    — industry-pack JSON loader + instantiate-into-draft.
- `workflow/packs/real_estate_hot_lead_nurture.json` — a sample template (budget+approval over a money node).
- `workflow/config.py`       — dormancy/creds/kill-switch snapshot (booleans only — secrets redacted).
- `workflow/audit_bridge.py` — redacting helpers over the live F4 audit.record (degrade to in-mem ring).
- `workflow/endpoints.py`    — the additive FastAPI APIRouter (16 routes, prefix /workflows). DEFINED, NOT
                               mounted. router=None if FastAPI absent. Zero import side effects.
- `workflow/tests/test_offline.py` — the §12 acceptance test (9 invariants + advisory-flag + selftest-bad).
- `workflow/_smoke_workflow.py` — import + dormant + router-defined + logic + safety smoke (exits non-zero
                               on failure).
- `WORKFLOW_STUDIO_STATE.md` — the per-unit crash-safe ledger.

## WHAT IT COMPOSES (reuse, verified on disk 2026-06-10)
- F4 `wallet.py`  — BUDGET node = wallet.reserve(hold per run); money nodes settle against it; leftover
                    released at completion/failure/cancel. Fail-CLOSED if wallet unavailable.
- F4 `firewall.py`— APPROVAL node = firewall.verify_step_up_token(token, scope, expected_sub==tenant) to
                    resume a parked run. Self-asserted requires_approval is advisory (recomputed server-side).
- F4 `audit.py`   — every node start/end + gate decision -> audit.record(channel="workflow"), secrets redacted.
- F2 workforce `ToolRegistry`/`ToolSpec` — Action/AI-Agent/Integration nodes call the SAME gated, audited,
                    dormant-until-creds tools; the dominator risk-classification reads the ToolSpec money
                    flag, NEVER the tenant JSON.
- F3 Hatchet      — the durable substrate (HATCHET_CLIENT_HOST_PORT=10.122.0.3:7077, tenant
                    707d0855-…). The studio is a thin compiler+interpreter layer ON Hatchet, not a 2nd engine.
- P1 `db.engine`  — RLS sessions (SET LOCAL app.tenant_id / app.is_admin); the 6 tables FORCE RLS.

## ROUTER ENDPOINTS (for the deferred mount via workflow_wiring.diff — spec §9)
prefix `/workflows`:
  GET /status ; GET "" (list) ; POST "" (create draft) ; GET /{id} ; PUT /{id} ;
  POST /{id}/validate ; POST /{id}/publish ; POST /{id}/run ; POST /{id}/hook ;
  GET /{id}/analytics ; GET /runs?status= ; GET /runs/{run_id} ;
  POST /runs/{run_id}/approve (X-Step-Up header) ; POST /runs/{run_id}/reject ; POST /runs/{run_id}/cancel ;
  POST /killswitch ; GET /templates ; POST /templates/{tid}/instantiate.
Deferred wiring (NOT applied — touches caller.py, out of scope):
  `from workflow.endpoints import router as workflow_router` ; `app.include_router(workflow_router)` ;
  `from workflow.events import attach_event_bridge` ; `attach_event_bridge(app)`.

## CREDS AWAITED (dormant until present; build + offline test need NONE)
- HATCHET_CLIENT_TOKEN + HATCHET_CLIENT_HOST_PORT (10.122.0.3:7077) + TLS_STRATEGY=none -> durable on the
  F3 spine; absent => SAME interpreter runs in-process.
- WORKFLOW_STORE=pg + PG_DSN -> Postgres+RLS; absent => in-memory store.
- AIWF_SERVICE_TOKEN (workforce live registry) -> live tool catalog; absent => StubTools.
- Per-integration adapter creds (ads/WA/payment) -> live money/send; absent => {"status":"not_configured"}.

## DEFERRED (not this wave)
- The React-Flow canvas + run-inspector in famit-panel (@xyflow/react, MIT) — frontend follow-up.
- Mounting the router into caller.py + attaching the event bridge (the un-applied workflow_wiring.diff).
- Applying workflow/schema.sql on the live PG (the live-PG integration unit) + proving live RLS/UNIQUE.
- Registering the `wf-run` durable task on the famit-orchestrator worker (deferred worker wiring).
- The AI-Manager `workflows.create/publish/run` tools (voice-commanded authoring).

## VERIFICATION (local/venv only — NO deploy, NO calls)
- `python -m unittest workflow.tests.test_offline` => 11/11 OK (all §12 items + advisory + selftest-bad).
- `python -m pytest workflow/tests/test_offline.py -q` => 11 passed.
- `python workflow/_smoke_workflow.py` => SMOKE PASS (imports / dormant / router-defined / logic / safety),
  both standalone (dormant) AND with the live tree on path (real wallet/firewall/audit/workforce composed).
