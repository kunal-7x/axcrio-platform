# BRAIN — Workflow Automation Studio engine (module workflow-studio)

Durable facts + hard-won learnings. Append, never delete.
Spec: `design/platform-workflow-studio.md` (+ `design/orchestration-hatchet.md`).
Build log: `memory/build_log/wave-build-mod-workflow-studio.md`.
Code: `droplet_work/workflow-studio/workflow/` (importable inner package `workflow`).

## WHAT IT IS / SCOPE
- The connective tissue: durable, multi-tenant, crash-safe visual-automation engine. 10 node types
  (Trigger/Condition/AI-Agent/Action/Budget/Approval/Delay/Wait/Data/Integration/Error) + a single generic
  durable interpreter on Hatchet (the F3 box) + hard, code-enforced safety rails.
- "n8n UX, native engine" — n8n is OUT (Sustainable-Use-License landmine for a reseller). MIT React-Flow
  canvas is a DEFERRED frontend follow-up; this wave = engine + node lib + defined-not-mounted router.
- Engine status today: BUILT + offline-tested locally. NOT deployed, NOT wired into caller.py, schema NOT
  applied on live PG, `wf-run` durable task NOT registered on the worker. All deferred (sequential).

## THE SHAPE (settled, do not re-litigate)
- ONE generic durable orchestrator INTERPRETS a validated immutable JSON snapshot. NOT codegen-per-workflow
  (shipping tenant code into the money-path worker is a security nightmare). The worker only runs vetted
  registry tools over a validated graph.
- The studio is a THIN compiler+interpreter layer ON Hatchet, NOT a second engine/Postgres/queue.
- Provider-agnostic + dormant-until-creds: with no HATCHET token the SAME interpreter runs in-process
  (instant sleep/wait); the durable engine binding only SWAPS in ctx.aio_sleep_for / aio_wait_for_event.

## SAFETY = THREE LAYERS (defence in depth; all enforced in CODE, never the LLM/JSON)
1. PUBLISH-TIME (static, compiler.py): the DOMINATOR check. Every money/bulk/destructive/export node MUST
   be dominated by a BUDGET node on EVERY path from the trigger; money/destructive/export ALSO by an
   APPROVAL node. Risk is read from the workforce ToolSpec (money/risk_class), NEVER the tenant JSON.
   Reject with the exact offending node ids. Also: expr sandbox + cycle-must-pass-a-delay/wait check.
2. RUN-TIME (dynamic, nodes.py): recompute spend from RESOLVED tool+args (ignore the JSON's number);
   wallet hold is the authority (atomic, fail-CLOSED if wallet down); approval threshold/sub recomputed
   server-side + a fresh firewall step-up token; kill-switch re-checked before each node; DND/window
   re-checked (suppressed=skip, out-of-window=durable defer, never violate).
3. AUDIT (immutable, audit_bridge -> audit.py): every node start/end + every gate writes a row with reason,
   secrets redacted (channel="workflow").

## REUSED FOUNDATION SIGNATURES (verified on disk 2026-06-10 — cite, don't guess)
- wallet.reserve(tenant_id, amount_minor, resource_type=, resource_id=, idem_key=, is_admin=) -> hold_id|None
- wallet.settle(hold_id, actual_minor, idem_key=, is_admin=) ; wallet.release(hold_id, idem_key=)
- firewall.verify_step_up_token(token, scope, expected_sub) -> claims|None  (sub MUST == tenant_id — F3)
- firewall.mint_step_up(tenant_id, scope) ; firewall.enabled()/available()
- audit.record(actor, action, object_type, object_id, channel, tenant_id, actor_role, meta)  (never raises)
- workforce ToolRegistry.get(name) -> ToolSpec(name, fn, money, side_effecting, risk_class, scopes, schema)
- db.engine.session(tenant_id, is_admin) ctx-mgr: SET LOCAL app.tenant_id / app.is_admin (RLS, in-txn).
- RLS policy shape: USING (current_setting('app.is_admin',true)='1' OR tenant_id=current_setting('app.tenant_id',true)).

## HARD-WON LEARNINGS (do not relearn)
- RESUME of a parked APPROVAL run must use a FRESH attempt number (max existing node-run attempt + 1), not
  a hardcoded attempt=1. A failed (wrong-token) resume claims the approval node at attempt N; the next
  (correct-token) resume at the SAME attempt would REPLAY the parked result and never verify. `_next_attempt`.
- The budget node's hold_id + cap_minor MUST be PERSISTED on the run (set_run_status hold_id=...) because a
  resumed run starts PAST the budget node; otherwise the downstream money node sees hold=None / cap=0 and
  fails `no_budget_hold` or false `cap_block`. Interpreter persists after a budget node; resume RECOVERS
  cap/threshold/hold from the persisted budget node-run.
- A satisfied APPROVAL node must set `_approval_satisfied` in the run data bag (bag_updates) so every money
  node it DOMINATES proceeds without re-parking at its own threshold check. That is the dominance contract.
- The write-ahead CLAIM keyed (run_id,node_id,attempt) is the idempotency/replay spine: an already-claimed
  node REPLAYS its persisted result (no re-execute, no double-spend). UNIQUE(claim_key) in PG / a set in mem.
- Pydantic is OPTIONAL: the DSL validator is pure-stdlib so the package imports + validates with ZERO
  third-party deps (the offline test needs no pydantic). Same invariants either way.
- hatchet-sdk 1.33.6 uses `input_validator=` (NOT `input_type=`) in hatchet.workflow(...) — confirmed in the
  F3 brain; the engine binding uses it.
- The studio's default_deps() composes the LIVE F4 wallet/firewall + workforce registry when on path; degrade
  to None/StubTools when absent. Verified: wallet/firewall = the real modules (available()=False w/o PG, i.e.
  correctly dormant); registry = 12 workforce tools; audit_bridge wires the real audit module.

## VERIFY COMMANDS (local/venv ONLY — never deploy/place calls)
- `set PYTHONPATH=droplet_work\workflow-studio && python -m unittest workflow.tests.test_offline`  (11/11)
- `python droplet_work\workflow-studio\workflow\_smoke_workflow.py`  (SMOKE PASS)

## NEXT (deferred, in order)
1. Apply `workflow/schema.sql` on live PG (live-PG unit) + prove RLS/UNIQUE.
2. Register the `wf-run` durable task on the famit-orchestrator worker (engine.build_durable_task).
3. Mount the router + attach the event bridge in caller.py (the un-applied workflow_wiring.diff).
4. React-Flow canvas + run-inspector in famit-panel (@xyflow/react MIT).
5. AI-Manager workflows.create/publish/run tools (voice-commanded authoring).
