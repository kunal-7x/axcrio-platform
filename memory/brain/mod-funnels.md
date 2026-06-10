# BRAIN — Funnel builder (module funnels)

Durable facts + hard-won learnings. Append, never delete.
Spec: MASTER_PLATFORM_ROADMAP row 79 / P9 (over design/platform-workflow-studio.md — no separate funnels
section; designed minimally over the settled workflow engine). Build log:
`memory/build_log/wave-build-mod-funnels.md`. Code: `droplet_work/funnels/`. STATE: `funnels/STATE.md`.

## WHAT IT IS / SCOPE
- Funnel builder: connect ad->landing->lead->call->whatsapp->booking->payment->review as ONE funnel
  definition OVER the workflow-studio engine, with per-STAGE conversion analytics. THIN layer — a funnel
  COMPILES DOWN to the §3 workflow DSL; publish/run delegate to workflow.publish/run; analytics RE-PROJECT
  workflow.analytics. Re-implements NOTHING (engine/wallet/firewall/audit/dominator/sandbox = workflow-studio).
- Status: BUILT + offline-tested (8/8 unittest + smoke). NOT deployed, NOT mounted (router defined-not-
  mounted, funnel_wiring.diff un-applied), schema NOT applied on live PG. All deferred (sequential).

## THE SHAPE (settled, advisor-confirmed — do not re-litigate)
- A funnel = ordered STAGES (subset/prefix of the 8 canonical, order preserved). compiler.compile_funnel
  lowers it to a LINEAR workflow DSL spine (trigger -> [budget] -> stages... -> error sink), stamping
  config.stage on every node (the attribution map analytics buckets by). PURE/engine-free.
- workflow imported LAZILY (lives under sibling top-dir `workflow-studio/`, NOT importable as a subpackage)
  + degrade-safe: absent => {"status":"not_configured"}, never raises. Smoke/test PYTHONPATH needs BOTH
  `droplet_work` AND `droplet_work/workflow-studio`.
- augmented_registry() = workforce.make_registry() + funnel tools (funnels.landing.publish/review.request);
  passed to workflow.validate/run so funnel stages resolve.

## THE LOAD-BEARING LEARNING — gate BULK, not just money (this bit us)
- workflow's compiler classifies leads.enqueue_calls + whatsapp.send as BULK (`_BULK_HINTS`
  'enqueue_calls'/'send'); ToolRef.needs_budget = money OR bulk OR destructive. So a lead->call->whatsapp
  funnel (NO external money) STILL needs a dominating BUDGET node or publish fails `no_budget_dominator`.
- FIX: linear spine => inject ONE budget node after the trigger if ANY stage needs_budget (dominates all),
  + ONE approval node before the first money/destructive stage. needs_budget/needs_approval are DECLARED in
  stages.STAGE_MAP (keeps compile_funnel pure — never resolve via the registry at compile time).
- CAP TRICK (offline-completes AND static-passes): the dominator check is a PRESENCE check (never inspects
  the cap). cap = money-stage cap if an `ad` stage exists, ELSE cap_minor=0 for a bulk-only funnel. WHY 0:
  exec_budget (workflow/nodes.py ~156) treats cap<=0 as "no autonomous external spend" => no wallet touch,
  NEVER parks. A cap>0 budget node PARKS offline (wallet.available()=False w/o PG => fail-closed). Bulk
  nodes carry money=False so the runtime money gate is skipped + bulk_count(1)<max_bulk_targets(50) => no
  park => the funnel RUNS TO COMPLETION offline. Over-declare = harmless cap=0 gate; under-declare = LOUD
  rejection at publish (workflow.validate is the authoritative backstop). Negative-control test strips the
  one budget node -> `no_budget_dominator`, proving the gate is structural.

## OTHER HARD-WON LEARNINGS
- In-memory backend: `workflow.make_store()` returns a FRESH InMemoryStoreBackend each call. funnels.publish
  + funnels.run each made their own => a published wf invisible to the runner. FIX: process-shared
  `funnels._WF_STORE` (mirrors workflow.endpoints._STORE); publish/run/analytics share it. Tests reset it +
  may pass an explicit wf_store. Moot for PG (one shared DB).
- wait nodes (booking/payment) run offline: exec_wait with wait_for_event=None does NOT block — returns
  done {waited:False}. Compile to event_key=<EVENT_NAME> + timeout_hours (the keys exec_wait reads; the
  human-readable `event` tag is cosmetic). booking.made / payment.received are valid DSL EVENT_NAMES.
- landing/review stages compile to INERT `data` placeholders today (Website/Landing + Reviews siblings not
  built). The dormant funnel TOOLS exist in tools.py ready to swap in (flip STAGE_MAP node_type ->
  integration + tool name) with ZERO interpreter change when the siblings + creds ship.
- Per-stage `reached` = per_node[primary_nid].runs, EXCLUDING injected gate nodes (config.injected_by==
  'funnels'). conversion[i]=reached(i+1)/reached(i); drop_off = lowest-ratio transition. No second tracker.
- model.py FunnelSpec.skip_money_gate is ADVISORY-IGNORED by the compiler (RTF-5: tenant JSON can never
  disarm a gate).

## VERIFY (local/venv ONLY — never deploy/place calls)
- `set PYTHONPATH=.;workflow-studio && python -m unittest funnels.tests.test_offline`  (8/8 OK)
- `set PYTHONPATH=.;workflow-studio && python funnels\_smoke_funnels.py`  (SMOKE PASS)

## CREDS AWAITED
- FUNNELS_LANDING_API_KEY (landing), FUNNELS_REVIEW_API_KEY (review) — both dormant; sibling modules pending.
- Durable/money plane creds are the workflow engine's (HATCHET/PG/wallet/firewall), owned by workflow-studio.

## MOUNT-TIME GOTCHA (document, don't re-engineer now)
- `funnels._WF_STORE` and `workflow.endpoints._STORE` are SEPARATE module-level instances. Once both routers
  mount, a funnel published via POST /funnels/{id}/publish lands in funnels._WF_STORE, while GET
  /workflows/runs/{run_id} (the run-inspector to reuse) reads workflow.endpoints._STORE — so funnel runs are
  invisible to the workflow inspector on the in-memory backend. MOOT on Postgres (one shared DB, RLS-scoped).
  FIX AT MOUNT: make funnels._wf_store prefer workflow.endpoints._store() when available, else wf.make_store().
- analytics `reached`/conversion: offline a single run touches every node (wait no-ops) => trivially
  100% — the projection WIRING is verified, real per-stage conversion only shows across many live runs.
- minor cleanup: compiler hardcodes trigger config.stage="lead" even for funnels with no lead stage
  (harmless — analytics only reads stages in the ordered list).

## NEXT (deferred, in order)
1. Apply funnels/schema.sql on live PG + prove RLS (live-PG unit).
2. Mount the router via funnel_wiring.diff (touches caller.py) — wire funnels._wf_store to
   workflow.endpoints._store() so the shared run-inspector sees funnel runs (see MOUNT-TIME GOTCHA).
3. Light up landing/review when siblings ship (one-line STAGE_MAP edit).
4. React-Flow funnel canvas in famit-panel (reuse workflow-studio canvas).
5. AI-Manager funnels.create/publish/run tools (voice-commanded authoring).

## SECURITY FIX (2026-06-10) — token-deriving build_router added
- Hole: `funnels/endpoints.py` read `tenant_id=payload.get("tenant_id")` from the body; since a funnel
  COMPILES DOWN to the workflow engine, the body tenant flowed into workflow.publish/run (delegating did
  NOT save it). The shipped `funnel_wiring.diff` mounts the bare router = the cross-tenant hole.
- Fix: added `build_router(resolve_tenant, can, need_auth, forbidden, firewall=None)` (mirrors
  workflow-studio): tenant := token, writes enforce `can(t,"write")` (whole tenant dict as 1st arg).
  Kept the bare `router` for offline test/introspection (DO-NOT-MOUNT). Verified: token A flows into
  `_run`, not body B; 401 no-token / 403 no-write; 8/8 tests still pass (PYTHONPATH `.;workflow-studio`).
  MOUNT `build_router(...)`, NOT the bare router; do NOT apply `funnel_wiring.diff`.
