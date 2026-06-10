# WAVE-BUILD-AI-WORKFORCE — THE AGENT FRAMEWORK SPINE (PLATFORM-ENG)

Spec: `design/platform-ai-workforce.md` (followed; RED-TEAM fixes RT-1..RT-4 fold-win on conflict).
Roadmap: `MASTER_PLATFORM_ROADMAP.md` (AI Workforce runtime = FOUNDATIONAL). Composes F4 (wallet/
firewall/audit), F2 (brain/kb), CRM. Box: famit@168.144.153.145 `/opt/famit-agent/`, venv
`/opt/capsy-agent/.venv` (py3.12), svc famit-caller(:8209)+famit-agent. SSH `...\do-blr-test\id_ed25519`.
Mode: ADDITIVE, non-breaking, NO run-path edit, NO git (orchestrator commits). STATE:
`droplet_work/WORKFORCE_STATE.md`.

## TASK-vs-SPEC overrides (both honored; documented)
- Package dir = `droplet_work/workforce/` (task) — spec uses `aiwf/`. Task wins.
- Endpoint = `POST /workforce/run` (task) — spec §13 `POST /aiwf/runs`. Task wins. Full §13 surface
  shipped under the `/workforce/*` prefix.

## RECONCILE (2026-06-10 start)
- caller.py box md5 `6478885b` == local (CRM-wave baseline) — ZERO drift. Both svcs active. PG 16 up.
- NO `workforce/`, NO `aiwf/` dir (clean slate). venv has jwt 2.13.0 + fastapi 0.136.3 + pydantic.
- Read F4 (wallet.py reserve/settle/release/balance; firewall.py mint_step_up/verify_step_up_token/
  check_pin/set_pin/classify — sub-bound F3; audit.py record(channel=,tenant_id=,meta=) + PG events
  mirror), F2 (brain.resolve_worker_context/retrieve), CRM (crm.list_contacts). auth.issue_pair(tenant)
  mints a per-tenant access token (sub=tenant_id). caller.can(t,action) = read/write/manage_tenants.

## THE LOAD-BEARING DECISION (advisor-greenlit; the divergence from F4/F2/CRM muscle memory)
**DO NOT edit caller.py.** Exposure ships as an UN-APPLIED `workforce_wiring.diff`. Payoff: the
regression gate is green BY CONSTRUCTION — caller.py byte-identical ⇒ every legacy/JWT route + /run
dispatch is unchanged. This is the spec's blessed `caller_wiring.diff` posture (§12/RT-1), and it makes
the box work shrink to: reconcile md5, sync the inert package, run the offline test in the box venv
(doubles as instantiate-smoke + deploy proof), one regression curl. No /run re-dial, no JWT mint.

## ITEM 1 — TOOL REGISTRY (scoped tools over the existing API; read-only vs risky)
`workforce/tools/__init__.py` — `ToolSpec(name,description,scopes,fn,side_effecting,money,risk_class,
schema)` + `ToolRegistry` (register/get/for_scopes/describe). risk_class ∈ {safe, risky}.
- `tools/catalog.py` (LIVE) — each tool maps 1:1 to an EXISTING caller.py route over the authenticated
  loopback (transport.py): contacts.read→GET /contacts, leads.read→GET /leads, analytics.read→GET
  /analytics, brain.retrieve→GET /brain/retrieve, billing.read→GET /billing/overview, whatsapp.send→POST
  /whatsapp/send, leads.enqueue_calls→POST /run, ads.set_budget→POST /ads/budget, leads.delete→DELETE
  /leads/{id}, contacts.write→PUT /contacts/{phone}, suppression.add→POST /suppression. NO business logic
  duplicated. DORMANT until AIWF_SERVICE_TOKEN (transport.available()==False → live registry inert).
- `tools/transport.py` — authenticated localhost-loopback client. The runner mints a FRESH per-run
  per-tenant token via `auth.issue_pair(tenant_of_run)` so each call resolves to exactly the run's org_id
  under RLS (a single admin token would mis-scope writes — spec §3.1, verified vs caller.py:404
  resolve_tenant + auth._make_access sub=tenant_id). Import-safe (requests|httpx; degrade if absent).
- `tools/stub_tools.py` (OFFLINE) — in-memory mirror, SAME names/scopes/risk_class, deterministic
  results, a CALL_LOG so the test asserts a RISKY tool did NOT execute when a gate blocks/parks.
- **RISK CLASSES.** safe = read-only / internal (contacts.read, leads.read, analytics.read,
  brain.retrieve, billing.read, contacts.write, suppression.add). risky = side-effecting/spend/bulk/
  destructive (whatsapp.send, leads.enqueue_calls [bulk], ads.set_budget [money], ads.pause, leads.delete
  [destructive]). money:true (EXTERNAL spend) = ads.set_budget, ads.create_campaign, invoices.create —
  these reserve against the wallet. Internal-metered (call/WA credit) is NOT money:true here (the wallet
  meters those at execute; the external-spend gate governs ad budget/invoices).

## ITEM 2 — AGENT ORCHESTRATOR (the spine loop, firewall/wallet/audit composed)
`workforce/runner.py` — `AgentRunner.run(role, task, ctx) -> AgentRunResult`. The generalized aimanager
loop, parameterized by `ResolvedPolicy`. DI bundle `Deps(store, registry, planner, wallet, firewall,
audit, llm, suppressed_check, in_window_check)` makes it fully offline-testable. Flow:
  policy.resolve(role,ctx) → store.create_run (org_id+actor PINNED from ctx — RT-3) → audit run.start →
  KILL-SWITCH short-circuit → context.gather (read-only Brain+KB) → planner.propose (LLM if configured
  else StubPlanner) → validate(plan, allowed_tools) → per action: guardrails.check → record gate+reason →
  {blocked: skip · handover: summarize+notify+return · parked: create_approval+notify+return
  awaiting_approval · allowed: wallet.reserve (money) → execute tool → store tool_result (UNIQUE idem key)
  → wallet.settle/release → audit execute} → finalize done.
- **GUARDRAILS** (`workforce/guardrails.py`, deterministic, NEVER the LLM): one `check(policy,action,...)`
  → Gate(allowed|blocked|parked|handover). Order: killswitch → scope(default-deny) → handover(handover_on
  signal) → DND(suppression/window) → destructive/export/price/refund(park) → bulk(>max_bulk_targets
  park) → action-cap(block) → budget(money: recompute spend from args [model's est is ADVISORY], daily
  cap, wallet fail-CLOSED if unavailable) → approval-threshold(spend > threshold, strict-greater; 0 parks
  ANY spend>0). Composes REAL firewall (PIN/step-up for parked spend/destructive) + REAL wallet (reserve =
  the ACID no-oversell gate).
- **SAFE tools execute freely; RISKY tools MUST pass the firewall + wallet FIRST**; EVERY decision logs to
  the immutable audit ledger with a reason (`audit_bridge.py` → REAL audit.py, channel="ai", `aiwf.*`
  prefix → queryable via F4's existing GET /audit?channel=ai + the PG events mirror).
- **Tenant/org-scoped throughout**: policy resolves per (role,org,actor); store is org-scoped (RLS
  analogue in-memory, FORCE-RLS in PG); transport mints a per-run per-tenant token.
- **RT-2 idempotency** = RESOURCE-STABLE key `<run_id>:<tool>:<resource_id>` (NOT seq/action.id) so a
  Hatchet at-least-once retry **of the SAME durable run** (run_id stable → key stable) re-derives the SAME
  key → the UNIQUE guard rejects the double-execute/double-spend. (This is a DIFFERENT scenario from a
  human-driven NEW-run resubmit-after-approval, where run_id changes → key differs → the idem key alone
  would NOT stop it, which is exactly why approvals are single-use + action-bound — see the firewall-seam
  section. The two claims are complementary, not contradictory.) planner_stub.PlannedAction.
  _derive_resource() builds resource_id deterministically (lead_id/campaign_id/msisdn/sorted-target-set).
- **LLM driver** (`workforce/llm/driver.py`) — provider-agnostic claude|groq|none, DORMANT default
  (whatsapp.py contract: import-safe, is_configured(), status() not_configured, no key → StubPlanner
  drives). claude = opus-4-8 adaptive-thinking manual tool-loop, NO budget_tokens/temperature (400 on Opus
  4.8), prescriptive tool descriptions (Opus under-reaches). groq round-robin GROQ_API_KEY[_1..N]. The
  live propose() body is the LATER activation unit (returns None now → stub).
- **Store** (`workforce/store.py`) — ONE interface, two backends: InMemoryStoreBackend (offline; enforces
  idem-key uniqueness + tenant-scope in Python) + PgStoreBackend (production, lazy db/engine.py; SQL
  mirrors the §4 tables 1:1). `make_store()` defaults to memory; WORKFORCE_STORE=pg only if db.engine up.
- **schema.sql** — the 4 PG tables (agent_runs/agent_steps[UNIQUE idem partial idx]/agent_approvals/
  agent_tool_grants + agent_roles) FORCE-RLS admin-GUC shape. INERT this unit (apply = later live-PG unit,
  the F2/F4 standalone-schema precedent, off the P1 Alembic chain).

## ITEM 3 — ROLE PROFILES (roles are DATA, not modules)
`workforce/roles.py` — `RoleSpec(name,display,system_prompt,default_scopes,model,autonomy,context_packs,
handover_on)` + `ROLE_REGISTRY` = 12 rows: telecaller, whatsapp, support, strategist, creative, ad, crm,
booking, billing, analytics, ops(==aimanager), manager(AI-Manager meta-delegator). Each = system prompt +
allowed tool-set + risk policy; all read the Business Brain + KB (F2) via context.gather. `default_grant`
seeds the SAFE posture (daily_spend_cap=0, approval_threshold=0 → all external spend human-approved).
`workforce/policy.py` — `resolve(role,org,actor) -> ResolvedPolicy` = `default_scopes ∩ agent_tool_grants
∩ caller.can(actor)` (default-deny, narrowest wins; grant can only NARROW + cap, never widen; actor RBAC
drops any scope the human couldn't perform). The LLM is given ONLY allowed_tools; guardrails re-check
scope at execute (defense in depth — model self-asserted fields advisory only).

## ENDPOINTS (additive APIRouter, mounted via the UN-APPLIED diff, flag-gated default OFF)
`workforce/endpoints.py` `build_router(resolve_tenant,can,need_auth,forbidden)` — injects caller.py's
EXACT auth helpers (no new auth path). Routes (WORKFORCE_ENABLED off → 503 not_enabled, so mounting is
byte-safe): POST /workforce/run · GET /workforce/runs/{id} · POST .../approve · .../reject · GET
/workforce/roles · POST /workforce/grants/{role}(admin) · POST /workforce/killswitch(admin) · GET
/workforce/status. org_id ALWAYS t["tenant_id"] (RT-3/RT-5). `workforce_wiring.diff` = +1 import-guarded
import block + app.include_router, both purely additive (anchors: caller.py:110 after crm import, :171
after app=FastAPI; need_auth@436, _forbidden, can@641, resolve_tenant@404 all exist).

## ⭐ THE FIREWALL-GATED AUTHORIZATION SEAM (advisor-caught + fixed — load-bearing correctness fix)
First cut had the firewall as THEATER: the proof verified a step-up token in isolation then authorized
execution via a client-supplied `task["pre_approved"]` bool — so "ALLOWED with a PIN" wasn't proven AND a
caller could `POST /workforce/run {pre_approved:{tool:true}}` to bypass the gate (violating RT-5 advisory-
fields + RT-3). FIXED — the firewall is now IN the authorization path:
- `resume_approved(run_id, approval_id, ctx, step_up_token)` calls the **REAL**
  `firewall.verify_step_up_token(token, scope=apr.scope, expected_sub=ctx.org_id)` and only flips the
  approval to 'approved' if it passes (PIN-gated scopes = spend/destructive/refund/price/export; a bulk
  park needs a human click, no PIN). A denied/missing/wrong-tenant token → stays awaiting_approval +
  audit `aiwf.approval.stepup_denied`.
- The runner's `has_approval` for a risky action comes ONLY from a STORED approval row in state
  'approved' (`_approved_approvals`/`_match_approval`) — NEVER a client/model field. A resubmit carries
  `resume_run_id` = the original parked run; the runner reads THAT run's stored approvals. The client
  `pre_approved` field is DELETED from the endpoint. `/approve` reads the token from `X-Step-Up`.
- **SINGLE-USE + ACTION/AMOUNT-BOUND approvals (advisor fix #2 — a second blocking gap in the same
  money class).** Bug: the approval was scope-matched only + never consumed, and a resubmit mints a FRESH
  run_id so the idem key `{rid}:tool:resource` does NOT reject a replay → ONE PIN became a reusable bearer
  token for unlimited same-scope spend (replay, amount-escalation `999999` vs approved `200000`, and
  ad_2-vs-ad_1 resource substitution) — and in the default posture `daily_spend_cap=0` SKIPS the budget
  cap, so it was bounded only by wallet balance. FIX: the approval row now stores `data{tool,resource_id}`
  + `amount_minor`; `_match_approval` authorizes EXACTLY this (tool, resource_id) up to amount_minor; the
  runner CONSUMES it (`set_approval_state(state='used')`) after the execute + drops it from the in-run
  pool. The false "idem key rejects double-execute on resubmit / cannot escalate" claim was corrected in
  the docstring. New tests: single-use (2nd resubmit re-parks, CALL_LOG stays 1, wallet debited once) +
  no amount/resource escalation (999999 and ad_2 both re-park, never execute).

## ⭐ THE GATED-TOOL PROOF — OFFLINE ACCEPTANCE TEST 15/15 GREEN (local AND box venv)
`workforce/tests/test_offline.py` — ZERO keys, ZERO network, ZERO Postgres. Uses InMemoryStoreBackend +
StubTools + StubPlanner + an in-memory WALLET-FAKE + the **REAL firewall.py** (PIN/step-up/sub-binding) +
the **REAL audit.py** (via an audit spy that wraps audit_bridge — environment-independent because the box
disables the JSONL leg in favour of the PG events mirror; the spy still calls through the real path).
The task PROVE bullets, each asserted with the firewall genuinely in the path:
- **A — SAFE runs FREE:** crm run of `contacts.read{hot:true}` → status done, tool_result present, audit
  aiwf.run.start/execute/run.end.
- **B — RISKY BLOCKED without step-up + wallet:** ops run of `ads.set_budget{budget_minor:200000}` with
  approval_threshold=0 → awaiting_approval, parked scope="spend", **CALL_LOG empty (RISKY tool did NOT
  execute)**, audit aiwf.gate.* + aiwf.approval.pending, gate reason carries "threshold".
- **C-without (the DISCRIMINATING half) — approve WITHOUT a valid step-up STAYS BLOCKED:** resume_approved
  token="" → firewall verify None → stays awaiting_approval (error step_up_required_or_invalid); a
  resubmit STILL parks; **CALL_LOG empty, wallet unmoved**; audit aiwf.approval.stepup_denied. Proves the
  firewall IS the gate.
- **C-with — approve WITH a valid sub-bound step-up EXECUTES:** set_pin(orgA,1357) → mint_step_up(spend) →
  resume_approved WITH token → approved → resubmit (resume_run_id) → STORED approval lets it through →
  done, spend_authorized=200000, **wallet debited 200000**, ads.set_budget EXECUTED, audit
  aiwf.approval.approved + aiwf.execute.
- **D — CROSS-TENANT scoping holds (load-bearing):** orgB parks a spend; orgA mints a VALID token for
  ITSELF and tries to approve orgB's run → REJECTED (resume_approved verifies expected_sub==orgB; A's
  token sub=orgA) → stays awaiting_approval. + raw sub-binding (A-token verify sub=orgB → None) +
  InMemory store get_run/list_steps cross-tenant → None/[].
- Plus: scope default-deny + plan-validation reject, budget-cap block-before-execute, DND/suppression
  block, bulk fan-out park, support handover on refund_request, kill-switch halt, idempotency (one
  tool_result on the resource-stable key).
Run: `python workforce/tests/test_offline.py`. PyJWT installed locally; box venv had it.

## ⭐ REGRESSION GATE — GREEN (caller.py byte-identical → green by construction)
- caller.py box md5 `6478885b` UNCHANGED (we never touched it). Both svcs active throughout.
- Legacy X-Auth (CALLER_PASS): /me /campaigns /leads /billing/overview /contacts → **200**. /run
  bad-campaign → **202** (dispatches; NO paid call — nonexistent campaign, no real dial). /workforce/status
  → **404** (diff un-applied; route not mounted — proves additive-only). ZERO 5xx in the window.
- md5 local==box for __init__/runner/guardrails/store/roles/policy/endpoints/stub_tools (zero drift).
- Offline acceptance 15/15 GREEN in the BOX venv against live modules + live PG (doubles as
  instantiate-smoke: `import workforce` clean, default_deps wires REAL wallet+firewall, endpoints
  build_router importable). JWT-200 leg N/A in-shell (auth._SECRET Doppler-only — CRM lesson); but
  resolve_tenant byte-unchanged ⇒ JWT path intact by construction.

## NON-BREAKING / ROLLBACK
- 100% additive: a NEW `workforce/` package (the live voice path imports NOTHING from it). caller.py
  UNCHANGED. NO .env change (all flags default OFF/dormant: WORKFORCE_ENABLED off, AIWF_LLM_PROVIDER none,
  no AIWF_SERVICE_TOKEN → live tools dormant/StubTools, AIWF_KILLSWITCH 0, grants cap=0/threshold=0). The
  4 PG tables are NOT applied this unit (schema.sql inert).
- ROLLBACK: `rm -rf /opt/famit-agent/workforce` — nothing else references it; caller untouched; no svc
  restart needed. The wiring diff is un-applied (no caller.py backup needed — it was never modified).

## DEFERRED (named later units — the next builder doesn't chase ghosts)
1. **Apply the diff + restart** (orchestrator's "final wiring" step) — mounts /workforce/* live.
2. **manager/voice layer (RT-1)** — number registration, the call state machine, intent parsing, voice
   PIN/OTP step-up are OWNED by `platform-ai-manager.md`; only its `delegate.py` calls AgentRunner.run.
   The `manager` role row + the `delegate` scope are in place; the voice front-end is NOT built here.
3. **workflow/node.py** — the Workflow-Studio AI-Agent/BUDGET/APPROVAL nodes over the same runner.
4. **Hatchet durable-task wrap** — long/multi-step role runs become @hatchet.durable_task (idempotency
   keys already resource-stable for at-least-once replay).
5. **Live claude/groq** — driver.propose() body (manual tool-use loop + structured-plan validation); the
   stub path proves the spine without it.
6. **Live-PG unit (spec §15 unit 1)** — apply schema.sql + the RLS/UNIQUE concurrency integration test
   (the offline suite proves the semantics; the live DDL behaviour is proven there, F2/F4 precedent).
7. **AIWF_SERVICE_TOKEN activation** — lights up the loopback catalog (live tools) + per-run token mint.
8. **Per-role live wiring** — telecaller over the voice plane, whatsapp/support over the WA pipeline, ad
   adapters (Google/Meta creds; ad ships propose-only until reserve↔accrual reconciled — RT-4), etc.
9. **brain.write firewall scope** for any AI-Manager Brain-write (F2 RT-2 prereq).

## ARTIFACTS (local SoT droplet_work/workforce/, box==local md5)
- config.py, store.py, audit_bridge.py, schema.sql(inert), roles.py, policy.py, guardrails.py,
  context.py, handover.py, planner_stub.py, runner.py, __init__.py, endpoints.py, workforce_wiring.diff.
- tools/{__init__,catalog,transport,stub_tools}.py · llm/{__init__,driver}.py · tests/test_offline.py.
- STATE: droplet_work/WORKFORCE_STATE.md.
