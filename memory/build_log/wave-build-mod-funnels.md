# WAVE BUILD — MOD funnels (Funnel builder over the workflow engine)

Built 2026-06-10. Roadmap row 79 / P9 ("Multi-step conversion funnels"; acquisition half of the loop) +
design/platform-workflow-studio.md (funnels compose ON the workflow-studio engine; the spec has no separate
funnels section, so designed minimally from the roadmap over the settled engine). ADDITIVE, dormant-until-
creds, defined-not-mounted, NO git (orchestrator commits), NO caller.py/agent.py edit, NO service restart,
build + import/smoke locally only.

RESUME NOTE: a prior session had created config.py/stages.py/model.py/compiler.py + an optimistic STATE.md
marking all units DONE, but store/analytics/core/__init__/router/tests/templates/schema.sql/smoke were
MISSING (dead-session artifact). This session reconciled (kept the 4 good files, fixed the gating bug in
compiler.py) and finished the module. STATE.md now reflects true state.

## WHAT IT COMPOSES (built foundation, NOT reinvented)
- **workflow-studio engine** (`droplet_work/workflow-studio/workflow/`): a funnel COMPILES DOWN to the §3
  workflow JSON DSL; `funnels.publish/run` delegate to `workflow.publish/run` (the single durable
  interpreter on Hatchet, else in-process offline). ALL safety inherited verbatim: the publish-time
  DOMINATOR check, the expr sandbox, the immutable audit, idempotent crash-replay, the F4 wallet/firewall
  gates. Funnels add NOTHING on the money path. `workflow` is imported LAZILY + degrade-safe (lives under a
  sibling top-dir `workflow-studio/`; absent => {"status":"not_configured"}, never raises).
- **F4 wallet/firewall/audit** — reached THROUGH the workflow engine's BUDGET/APPROVAL/audit nodes (the
  funnel never calls them directly; it emits budget/approval nodes the interpreter executes).
- **workforce tool registry** — `funnels.tools.augmented_registry()` = `workforce.make_registry()` (live
  loopback when AIWF_SERVICE_TOKEN, else offline StubTools) PLUS the funnel tools, passed to
  workflow.validate/run. Stage tools resolved: ads.set_budget(money), leads.enqueue_calls(bulk),
  whatsapp.send(bulk), all verified present in the OFFLINE StubTools registry (2026-06-10).
- **P1 RLS pattern** — the thin `funnels` table ENABLE+FORCE RLS, admin-GUC-OR-tenant_id policy (db/rls.sql
  shape, identical to workflow/schema.sql); every read/write via `db.engine.session(tenant_id, is_admin)`.
- **workflow.store / workflow.endpoints conventions** mirrored 1:1 (dual InMemory/Pg backend, module-level
  shared store handle, defined-not-mounted FastAPI router, dormant-until-creds).

## THE SHAPE (settled, advisor-confirmed — do not re-litigate)
A funnel = an ORDERED list of STAGES (ad->landing->lead->call->whatsapp->booking->payment->review). The
compiler LOWERS it to a linear workflow DSL spine; the workflow engine remains the SINGLE authority on
publishability + execution. Per-stage analytics = RE-PROJECTION of workflow.analytics' per-node rollup
through the stage->node attribution map (config.stage tags) — NO second tracker, NO second write path.

Stage->node lowering (stages.py STAGE_MAP, engine-free):
  ad      -> integration ads.set_budget (money)         [needs_budget + needs_approval]
  landing -> data placeholder (Website/Landing sibling not built; dormant)
  lead    -> data marker + the entry trigger kind=event (lead.created / form.submitted)
  call    -> ai_agent role=telecaller leads.enqueue_calls (BULK)   [needs_budget]
  whatsapp-> action whatsapp.send (BULK)                            [needs_budget]
  booking -> wait event_key=booking.made   (durable wait-for-event; no tool, no gate)
  payment -> wait event_key=payment.received (durable wait-for-event)
  review  -> data placeholder (Reviews sibling not built; dormant)

## THE LOAD-BEARING FIX — auto-gating for BULK (not just money)
The workflow compiler's `resolve_tool` classifies a tool as BULK via `_BULK_HINTS` ('enqueue_calls','send').
`ToolRef.needs_budget` is True for money OR bulk OR destructive, so leads.enqueue_calls + whatsapp.send
REQUIRE a dominating BUDGET node even though they move NO external money. The first build only gated money
stages => a lead->call->whatsapp funnel was rejected at publish with `no_budget_dominator`. FIX (compiler.py):
- Linear spine => inject ONE budget node right after the trigger when ANY stage needs_budget (dominates all),
  + ONE approval node immediately before the first money/destructive stage (dominates all money nodes).
- CAP TRICK (offline-completes AND static-passes): the dominator check is a PRESENCE check (never inspects
  the cap). Set the injected budget cap = the money stage's cap when an `ad` stage exists; for a BULK-ONLY
  funnel set **cap_minor=0** — `exec_budget` treats cap<=0 as "no autonomous external spend" (no wallet
  touch, NEVER parks), and bulk nodes carry money=False so the runtime money gate is skipped + bulk_count(1)
  < max_bulk_targets(50) so they don't park. Result: VALIDATES and RUNS to completion offline.
- needs_budget/needs_approval are DECLARED in STAGE_MAP (keeps compile_funnel pure/engine-free — never
  resolves via the registry at compile time). workflow.validate is the authoritative backstop: over-declare
  = a harmless cap=0 gate; under-declare = a LOUD `no_budget_dominator` at publish, never a silent unsafe
  publish. (Negative-control test strips the one budget node -> rejection, proving the gate is structural.)

## FILES CREATED (all NEW, under droplet_work/funnels/)
- `config.py` — dormancy/creds/store-mode/killswitch snapshot; landing/review creds (FUNNELS_LANDING_API_KEY
  / FUNNELS_REVIEW_API_KEY) dormant; redact(); status() booleans only (no secret leak); engine_status()
  delegates the durable-engine dormancy to the workflow module.
- `stages.py` — CANONICAL_STAGES (8) + STAGE_MAP (node_type/tool/role/event/money/needs_budget/
  needs_approval/placeholder/default_config) + accessors.
- `model.py` — FunnelSpec / FunnelStage (pure stdlib, no pydantic), parse_funnel; canonical-order enforce +
  dup-stage reject; skip_money_gate is ADVISORY-IGNORED (a money stage ALWAYS gets a gate, RTF-5).
- `compiler.py` — compile_funnel (lower spec -> DSL, the single-budget + single-approval auto-gating, stamp
  config.stage on every node, shared error sink); stage_node_map. Pure, engine-free.
- `tools.py` — DORMANT funnel integrations (funnels.landing.publish / funnels.review.request -> no-op
  {"status":"not_configured"}) + augmented_registry(base) (workforce registry + funnel tools; degrade to a
  local registry if workforce absent). Uses the real workforce ToolSpec when importable.
- `store.py` — thin `funnels` table, InMemory + Pg backends (lazy db.engine, RLS), make_store (FUNNELS_STORE
  =pg else in-memory). bind_workflow() links the funnel head to its compiled wf def + published version.
- `analytics.py` — funnel_analytics: per-stage reached (per_node[primary_nid].runs, EXCLUDING injected
  gates via config.injected_by=='funnels') + stage->stage conversion + drop-off; pure re-projection.
- `schema.sql` — the `funnels` table, FORCE RLS + admin-GUC policy (mirrors workflow/schema.sql). INERT;
  applied at the later live-PG unit. Off the P1 Alembic keystone chain.
- `__init__.py` — public surface: create/compile_spec/validate/publish/run/analytics/list_funnels/
  get_funnel/list_templates/instantiate_template/make_store/status. Lazy _workflow() + process-shared
  _WF_STORE so publish/run/analytics observe the same wf_runs/node_runs (in-memory backend requires it).
- `templates.py` — 3 starter funnels (real_estate_site_visit 8-stage, clinic_appointment, lead_to_call_
  nurture); pure data; instantiate -> FunnelSpec-shaped dict.
- `endpoints.py` — additive FastAPI APIRouter prefix=/funnels (11 routes), DEFINED not mounted; FastAPI
  optional (router=None if absent).
- `funnel_wiring.diff` — the deferred un-applied caller.py mount (the ONLY thing that touches caller.py).
- `tests/test_offline.py` (8 tests) + `_smoke_funnels.py` (SMOKE PASS).

## ROUTER ENDPOINTS (for the later mount via funnel_wiring.diff)
GET /funnels/status · GET /funnels/templates · POST /funnels/templates/{tid}/instantiate ·
GET /funnels · POST /funnels · POST /funnels/validate · GET /funnels/{id} ·
POST /funnels/{id}/validate · POST /funnels/{id}/publish · POST /funnels/{id}/run ·
GET /funnels/{id}/analytics

## VERIFY (local/venv ONLY — never deploy/place calls)
- set PYTHONPATH=.;workflow-studio && python -m unittest funnels.tests.test_offline   => 8/8 OK
- set PYTHONPATH=.;workflow-studio && python funnels\_smoke_funnels.py                 => SMOKE PASS
- PYTHONPATH=. (no engine) => imports clean; validate => {"status":"not_configured","compiled":true}; router defined.

## CREDS AWAITED (dormant-until-creds)
- FUNNELS_LANDING_API_KEY — hosted Landing/Website publisher (landing stage; sibling module also pending).
- FUNNELS_REVIEW_API_KEY  — Reviews/Reputation channel (review stage; sibling module also pending).
- (durable engine / money plane creds are the workflow engine's: HATCHET token, PG/wallet/firewall — owned
  + reported by workflow-studio, not funnels.)

## DEFERRED (sequential, orchestrator)
1. Apply funnels/schema.sql on live PG + prove RLS (live-PG unit; mirrors workflow/schema.sql).
2. Mount the router via funnel_wiring.diff (touches caller.py — out of scope this wave).
3. Light up landing/review when the Website/Landing + Reviews sibling modules ship — flip STAGE_MAP
   node_type to integration + tool name; tools.py adapters already dormant-ready (ZERO interpreter change).
4. React-Flow funnel canvas in famit-panel (reuse the workflow-studio canvas + run inspector).
5. AI-Manager funnels.create/publish/run tools (voice-commanded funnel authoring).
