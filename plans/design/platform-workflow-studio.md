# `workflow-studio` — Workflow Automation Studio Engine — Execution-Ready Design Spec

> **Status:** READY-TO-BUILD design (PLANNING ONLY — no code shipped, no live deploy here).
> Verified against the settled foundation docs on disk 2026-06-09: `design/orchestration-hatchet.md`
> (Hatchet durable engine), `design/credit-ledger-firewall.md` (wallet + firewall + audit),
> `design/automation-aimanager.md` (AI-Manager plan→approve→execute + tool registry),
> `design/automation-marketing.md` §1.1 (the n8n-license verdict), `design/p0-foundation.md` /
> `design/p1-postgres.md` (Postgres strangler), and the live panel (`famit-panel/`, Next.js 15 + React 19).
> **Settled-architecture invariant honored:** coarse services (voice plane / Hatchet worker-spine /
> modular-monolith control-plane API / panel) + modular monolith; scale by replicate+shard; OSS-composed;
> dormant-until-creds; self-host on DigitalOcean. **This is the FOUNDATIONAL system** that the 34 sidebar
> modules + AI workforce + AI Manager all compose on top of — it is the connective tissue.

---

## 0. THE DECISION — self-host n8n vs build native (SETTLED: BUILD NATIVE on Hatchet + React Flow)

The task asks me to decide. **Verdict: build native.** Three independent forcing functions, each decisive:

### 0.1 Licensing — n8n is a landmine for a *reseller/multi-tenant* product (already settled in this repo)
`design/automation-marketing.md` §1.1 (verified 2026-06-09) already ruled on this for the sequencer, and
the ruling applies *a fortiori* to a customer-facing visual studio: **n8n ships under the Sustainable Use
License (fair-code), which restricts "using the software's automation as a value proposition to
external/3rd-party users." Famit's entire business is selling automation to client tenants — that is
*precisely* the restricted case.** Self-hosting n8n for *internal* ops is fine; **baking it into the
product surface that tenants build workflows on is the restricted usage and a licensing landmine.** A
visual workflow builder is the single most "automation-as-the-product" surface imaginable, so n8n is OUT
for the studio. (Windmill AGPLv3 / Activepieces MIT were the OSS alternatives flagged there; see 0.3.)

### 0.2 The safety nodes CANNOT live in a third-party engine
The hard-spec node types — **BUDGET** (spend caps) and **APPROVAL** (human/PIN gate) — must compose with
Famit-native primitives that no off-the-shelf engine knows about:
- BUDGET reserves/settles against the **Postgres wallet ledger** (`wallet.py` atomic conditional
  `UPDATE … WHERE remaining >= :amt RETURNING`, holds reserve→settle→release) — `credit-ledger-firewall.md`.
- APPROVAL mints/verifies the **HS256 step-up token** (`firewall.py`, `amr:pin`, short TTL) and routes the
  pause to the existing AI-Manager approval surface — `credit-ledger-firewall.md` §4 + `automation-aimanager.md` §7.2.
- Every node decision writes the **immutable AI-decision audit** (`audit.py` append-only JSONL, money-mutating
  rows in the SAME DB transaction as the charge) — `credit-ledger-firewall.md` §0.3.
- AI-AGENT nodes call the **AI-Manager tool registry** (`automation/aimanager/tools/`) — the exact same
  gated, audited, dormant-until-creds adapters the AI Manager already uses.

Embedding n8n/Windmill would mean *re-implementing* these inside a foreign engine OR letting a foreign
engine spend real money outside our firewall — both unacceptable on the money path. The studio's value is
*the safety nodes*, and those are ours.

### 0.3 We already own a durable execution engine; a second one is the wrong altitude
`design/orchestration-hatchet.md` deploys **Hatchet** (Postgres + RabbitMQ, durable tasks, `aio_sleep_for`,
`aio_wait_for_event`, CEL concurrency, at-least-once + idempotency, fan-out) as the Famit worker-spine.
A workflow studio is *exactly* a graph of durable steps with delays, waits-for-event, branches, and
sub-workflows — which is what Hatchet's `durable_task` is built for ("an AI agent that picks its next
action based on a model response, or a pipeline that branches and spawns sub-workflows" — Hatchet docs,
2026). Standing up a *second* stateful service (n8n/Windmill, each with its own Postgres + queue to
operate, secure, and scale) to do what Hatchet already does on the box is redundant infra, a second
noisy-neighbor on the voice box (the master plan's #1 scale concern), and a second audit/secret surface.
**The studio is a thin compiler + interpreter layer ON Hatchet, not a new engine.**

### 0.4 What "build native" concretely means (the shape)
| Layer | Choice | Why |
|---|---|---|
| **Visual canvas (frontend)** | **`@xyflow/react` (React Flow) v12.10.x, MIT** | MIT = safe to ship to tenants (the n8n problem inverted); de-facto standard node-based UI lib (v12.10.2, 2026-03-27); drops into the existing Next.js 15 + React 19 panel. |
| **Definition format** | **Famit Workflow JSON DSL** (our schema, §3) | engine-agnostic, versionable, diffable, offline-testable; NOT n8n's proprietary format. |
| **Execution engine** | **Hatchet durable tasks** (already on the spine) | durable sleep/wait-for-event, at-least-once + our idempotency, CEL concurrency, fan-out — `orchestration-hatchet.md`. |
| **The "compiler"** | `workflow/compiler.py` — DSL graph → a Hatchet `workflow` with one durable orchestrator task that interprets the node graph | one engine, no codegen-per-workflow; safe, inspectable. |
| **Node action layer** | reuse the **AI-Manager tool registry** + Famit API loopback | Action/AI-Agent/Integration nodes = existing gated, audited, dormant adapters. |
| **Safety** | BUDGET→wallet holds, APPROVAL→firewall step-up, audit on every node | Famit-native, cannot be bypassed. |

> **Rejected:** self-host n8n (license), self-host Windmill *as the studio engine* (second engine, second
> Postgres, AGPL service we'd have to keep unmodified — and it still can't run our BUDGET/APPROVAL nodes
> natively). **Windmill/Activepieces remain a *deferred internal-ops* option** (run unmodified over REST,
> AGPL-safe per `automation-marketing.md` §1.1) — never the tenant-facing product engine.
> **Sources:** [React Flow / xyflow (MIT)](https://reactflow.dev/) · [@xyflow/react npm v12.10.2](https://www.npmjs.com/package/@xyflow/react) · [Hatchet durable execution](https://docs.hatchet.run/home/durable-execution) · [n8n Sustainable Use License](https://docs.n8n.io/sustainable-use-license/) · [n8n vs Activepieces vs Windmill licenses (Boolean&Beyond 2026)](https://www.booleanbeyond.com/en/insights/n8n-vs-activepieces-vs-windmill-open-source-automation).

---

## 1. WHAT THIS IS (one paragraph, honest)

`workflow-studio` is Famit's **n8n-style visual automation layer** that lets a vendor (or the AI Manager,
or a template) wire **Triggers → Conditions → AI-Agent/Action/Integration steps → with Budget/Approval/
Delay/Data/Error nodes** into a durable, multi-tenant, crash-safe automation — and runs it on the Hatchet
spine with **hard, code-enforced safety rails** (no bulk/spend/refund/DND-violation/out-of-hours/data-export
without an approval node + a budget node + an audit row). It is the **connective tissue** that turns the 34
modules + the AI workforce from isolated features into composable, founder-designed (or AI-Manager-designed)
revenue pipelines. It REUSES the Hatchet engine, the wallet ledger, the firewall, the audit log, the
AI-Manager tool registry, Postgres + RLS, and the panel — and ADDS: a workflow JSON DSL, a graph compiler/
interpreter on Hatchet, a React-Flow canvas, a template library, versioning, and per-workflow analytics.
**Real-vs-hype:** it does NOT let tenants spend money or blast messages unsupervised — every money/bulk/
destructive node is gated by a BUDGET cap + (above threshold) a human/PIN APPROVAL, exactly like the AI
Manager. It is *governed* automation, not a foot-gun.

---

## 2. GROUND TRUTH — what already exists (REUSE) vs what this ADDS (cite before trusting memory)

### 2.1 REUSE (the head-start — do not rebuild)
| Asset | Where | What workflow-studio reuses |
|---|---|---|
| **Hatchet durable engine** | `orchestration-hatchet.md`; box `famit-livekit`/own droplet (RTF-3) | the execution substrate: `hatchet.workflow()`, `@hatchet.durable_task`, `ctx.aio_sleep_for` (Delay node), `ctx.aio_wait_for_event` (wait-for-event Trigger/lead-reply), CEL concurrency, `run_no_wait(key=…)`, at-least-once semantics. The studio adds NO new engine. |
| **Idempotency discipline** | `orchestration-hatchet.md` §5 + RTF-11 (atomic `O_EXCL` / PG `UNIQUE` claim) | every side-effecting node reuses the write-ahead claim pattern keyed `(run_id, node_id, attempt)`. |
| **Wallet ledger (ACID)** | `credit-ledger-firewall.md` (`wallet.py`: reserve/settle/release, atomic decrement, holds, idempotency) | the **BUDGET node** = a wallet hold scoped to the run; spend nodes settle against it; leftover released on completion. |
| **Action Firewall (PIN/OTP step-up)** | `credit-ledger-firewall.md` (`firewall.py`: `mint_step_up`/`verify_step_up`, HS256 `amr:pin`) | the **APPROVAL node** = a firewall step-up requirement gating resumption of a paused run. |
| **Immutable AI-decision audit** | `credit-ledger-firewall.md` (`audit.py` JSONL; money rows in same txn) + `aidecision.py` | every node start/finish/decision/gate writes an audit row with the *reason*; the spec's "immutable audit of every AI decision". |
| **AI-Manager tool registry** | `automation-aimanager.md` §5 (`tools/__init__.py` `ToolSpec{name,schema,fn,side_effecting,money}`, `api_tools.py`, `ad_tools.py`) | **Action / AI-Agent / Integration nodes** call these EXACT gated, audited, dormant-until-creds tools — one money-path, one gate, one audit. No second tool surface. |
| **AI-Manager guardrails + kill-switch** | `automation-aimanager.md` §7 (`guardrails.py`, deterministic caps, kill-switch, fail-safe halt) | the studio's per-run/per-tenant kill-switch + the deterministic recompute-from-resolved-args spend check (RTF-5 there) are reused verbatim. |
| **Postgres + RLS + multi-tenant + RBAC + JWT** | `p1-postgres.md`, `p0-foundation.md`, `auth.py` (`can()`, `issue_pair()`) | workflow defs/runs/node-states live in Postgres with RLS by `tenant_id`; permissions reuse `can(role, action)`. |
| **Loopback service auth** | `automation-aimanager.md` RTF-1 (`AIMANAGER_SERVICE_TOKEN`, real admin tenant token) | the worker's Action nodes call the Famit API over authenticated localhost loopback with the same service token — no new bypass auth. |
| **Panel (Next.js 15 + React 19)** | `famit-panel/` (`src/app/*`) | the canvas mounts as a new `/workflows` route group; reuses the panel's auth, layout, providers, UI kit. |
| **Notifications / approval surface** | AI-Manager `/aimanager/plans?status=proposed`, `PushNotification` | APPROVAL-node pauses surface in the SAME approval inbox the AI Manager uses. |

### 2.2 ADD (net-new, this spec)
- `workflow/` Python package: DSL schema + validator, graph compiler, the durable Hatchet interpreter,
  the node executors, per-workflow analytics roll-up, template loader, versioning.
- **6 Postgres tables** (workflow defs, versions, runs, node-runs, triggers, schedules) — brand-new, no
  JSON migration (like the wallet tables, they need none of P1's dual/shadow machinery; only Postgres
  provisioned).
- The **React-Flow canvas** + node palette + run-inspector in the panel (`@xyflow/react`).
- An **additive `APIRouter`** (`/workflows/*`) mounted via a deferred un-applied diff (the project's
  "final wiring deferred" stance — never edits `caller.py`/`agent.py` directly).
- A **template library** (industry packs) shipped as workflow JSON files.
- The **offline acceptance test** (§12) — zero keys, zero network.

---

## 3. THE WORKFLOW JSON DSL (the definition format — engine-agnostic, versionable)

A workflow is a **directed graph** of nodes + edges, stored as one JSON document (validated by Pydantic).
This is the contract between the canvas (frontend), the API, the compiler, the engine, and the audit.

```jsonc
{
  "schema_version": 1,
  "workflow_id": "wf_<uuid>",
  "tenant_id": "<org_id>",
  "name": "Hot-lead 5-touch nurture",
  "version": 7,                      // monotonic; an immutable published snapshot
  "status": "draft",                 // draft | published | archived
  "industry_pack": "real_estate",    // optional template provenance
  "trigger": {                        // exactly ONE entry trigger (the graph root)
    "node_id": "n_trigger",
    "type": "trigger",
    "trigger_kind": "lead.created",   // see §4.1 trigger kinds
    "config": { "segment": "hot" }
  },
  "nodes": [
    {
      "node_id": "n1",
      "type": "ai_agent",             // see §4 node types
      "role": "ai_telecaller",        // which AI-workforce role (reads Business Brain + KB)
      "config": { "tool": "leads.enqueue_calls", "args": {"campaign_id":"C2","max":1} },
      "money": false,
      "on_error": "n_err"             // optional per-node error edge (Error-Handling)
    },
    {
      "node_id": "n_budget",
      "type": "budget",
      "config": { "cap_inr": 2000, "window": "run", "on_exceed": "park_for_approval" }
    },
    {
      "node_id": "n_approval",
      "type": "approval",
      "config": { "threshold_inr": 0, "require": "pin", "role": "manager", "timeout_h": 24,
                  "on_timeout": "reject" }
    },
    { "node_id": "n_delay", "type": "delay", "config": { "after_hours": 24 } },
    {
      "node_id": "n_cond",
      "type": "condition",
      "config": { "expr": "lead.interest >= 7 && !lead.opted_out" }  // safe sandboxed expr (§7.4)
    },
    {
      "node_id": "n_action",
      "type": "action",
      "config": { "tool": "whatsapp.send", "args": {"template":"nudge1"} },
      "money": false
    }
  ],
  "edges": [
    { "from": "n_trigger", "to": "n_budget" },
    { "from": "n_budget", "to": "n1" },
    { "from": "n1", "to": "n_delay" },
    { "from": "n_delay", "to": "n_cond" },
    { "from": "n_cond", "to": "n_action", "when": "true" },
    { "from": "n_cond", "to": "n_approval", "when": "false" }
  ],
  "guards": {                          // workflow-level HARD safety (defaults applied if absent — §7)
    "max_actions": 500,
    "calling_window": "09:00-21:00 IST",
    "respect_dnd": true,
    "respect_consent": true,
    "kill_switch": false
  }
}
```

**DSL invariants (validated, reject on violation):** exactly one `trigger`; acyclic except for explicit
`delay`-gated loops capped by `max_actions`; every `money:true` node MUST be dominated by a `budget` node
on every path to it (graph-dominator check, §7.1); every node referenced by an edge exists; `on_error`
targets exist; no node config references a tool not in the registry; `expr`/`when` parse under the safe
evaluator (§7.4). **A workflow that fails validation cannot be published.**

---

## 4. NODE TYPES (the 10 hard-spec types + executors)

Each node type has: a JSON `config` schema, a Python executor `execute(node, ctx) -> NodeResult`, a
`side_effecting` flag, a `money` flag, and a gate. Executors live in `workflow/nodes/`. `ctx` is the
durable run context (carries `run_id`, `tenant_id`, the per-run **data bag**, the Hatchet `DurableContext`,
the wallet hold handle, the tool registry, and the audit bridge).

### 4.1 `trigger` — the entry point (one per workflow)
Fires a run. Trigger kinds and how they bind to Hatchet:
| `trigger_kind` | Binds to | Notes |
|---|---|---|
| `manual` | `POST /workflows/{id}/run` | founder/AI-Manager kicks it. |
| `schedule` (cron) | Hatchet `on_crons=[…]` on the compiled workflow | per-tenant cron, stored in `wf_schedules`. |
| `event` (`lead.created`,`lead.replied`,`call.completed`,`lead.qualified`,`payment.received`,`form.submitted`,`booking.made`) | the spine emits these to a Hatchet **event** → `wf.run_no_wait(key=…)` | the Lifecycle Trigger Engine. Dedup key = `(workflow_id, event_id)`. |
| `webhook` | the additive `/workflows/{id}/hook` endpoint | inbound integrations. |
| `wait` (re-entry) | `ctx.aio_wait_for_event("lead_reply:<phone>")` inside a run | used by a *running* workflow to await a reply. |

> **Event plumbing reuse:** the spine already emits webhooks (`_emit_webhook`) and has the
> `_finalize_call` outcome pipeline; the studio subscribes to those emit points (a thin
> `workflow/events.py` bridge) rather than re-instrumenting the spine. Per `orchestration-hatchet.md`,
> emits MUST be idempotent (RTF-5) before they fan into workflow runs.

### 4.2 `condition` — branch (no side effect, no gate)
Evaluates a **sandboxed boolean expression** (§7.4) over the run data bag + the lead/campaign/billing
context (read via read-only tools). Routes to the `when:"true"`/`when:"false"` out-edges. Pure → safe to
re-run.

### 4.3 `ai_agent` — delegate to an AI-workforce role (gated by the tool it calls)
The studio's headline node. `role` selects an AI-workforce persona (`ai_telecaller`, `whatsapp_salesperson`,
`support_agent`, `campaign_strategist`, `creative_producer`, `ad_operator`, `crm_manager`,
`booking_assistant`, `analytics_manager`, …). The executor:
1. Builds context (Business Brain + Knowledge Base via read-only tools — reuses the AI-Manager
   `gather_context` + RAG seam, `dynamic-context-rag.md`).
2. Calls the AI-Manager **LLM driver** (`llm/driver.py`, dormant-until-creds; StubPlanner offline) to
   produce a tool call, OR runs a deterministic role-default action when no LLM key (so it works offline).
3. Executes the chosen **registry tool** — which carries its OWN `money`/`side_effecting`/gate metadata.
   If the tool is `money:true`, the BUDGET + APPROVAL machinery applies exactly as for an `action` node.
**Re-run safety:** the chosen action is idempotency-claimed `(run_id, node_id, attempt)`; the LLM
proposal is *advisory* — guardrails recompute spend from the resolved args (never trust the model's
numbers; `automation-aimanager.md` RTF-5).

### 4.4 `action` — a single deterministic registry tool call (gate per tool metadata)
Wraps one `ToolSpec` (`leads.enqueue_calls`, `whatsapp.send`, `campaigns.create`, `suppression.add`,
`ads.set_budget`, …). `side_effecting`/`money` inherited from the `ToolSpec`. Internal (credit-debited)
actions run autonomously up to the per-tick cap; **external money actions (`ads.*`) ALWAYS require a
BUDGET reservation + (above threshold) an APPROVAL** — identical policy to the AI Manager. Idempotent by
`(run_id, node_id, attempt)`; dormant adapters no-op `{"status":"not_configured"}`.

### 4.5 `budget` — spend cap (reserve a wallet hold for the run)
**Famit-native, cannot be in a 3rd-party engine.** On entry, calls `wallet.reserve(tenant_id,
amount=cap_inr*100, hold_key=run_id)` — an atomic conditional decrement (`credit-ledger-firewall.md`).
Downstream money nodes `wallet.settle()` against this hold; the run's leftover hold is `release()`d at
completion (and on failure/cancel). `on_exceed` ∈ {`park_for_approval`, `reject`, `trim`}. If the wallet
is unavailable or the tenant is postpaid, the BUDGET node FAILS CLOSED (treat remaining=0 → park) rather
than reading a non-atomic value (RTF-4 there). **No money node may execute without a satisfied BUDGET hold
on its path** (enforced at validation by the dominator check, §7.1, AND at runtime by the settle call
failing if no hold).

### 4.6 `approval` — human / PIN gate (pause until step-up)
**Famit-native.** Pauses the durable run: writes an `approval_request` (reusing the AI-Manager approval
surface — surfaces in `/workflows/runs?status=awaiting_approval` and the same inbox as `/aimanager/plans?
status=proposed`), then `await ctx.aio_wait_for_event("wf_approval:<run_id>:<node_id>")` (durable — survives
worker restarts). Resumption requires a **firewall step-up token** (`firewall.verify_step_up(scope=
"wf_approval", role)`) — i.e. the approver must present a valid PIN/OTP. `on_timeout` after `timeout_h`
∈ {`reject`, `proceed_low_risk`(only if money==0)}. Every approve/reject writes audit
(`workflow.approve`/`workflow.reject`) with actor + reason. **The threshold/require/role are recomputed
server-side from the resolved plan — the definition's self-asserted `requires_approval` is advisory only.**

### 4.7 `delay` / `wait` — durable time/event pause
`delay`: `await ctx.aio_sleep_for(timedelta(...))` — durable real-time sleep (survives restarts; the
`wa-cadence` pattern, `orchestration-hatchet.md` §4.2). `wait`: `await ctx.aio_wait_for_event(key,
timeout=...)` — await a lead reply / payment / external signal. Both are pure control-flow (no spend, no
gate); idempotent by construction (the durable context resumes the SAME sleep/wait, not a new one).

### 4.8 `data` / `memory` — read/write the run data bag (+ Business Brain) (no money)
Reads/writes the per-run JSON **data bag** (passed through `ctx`) and may read/write **Business Brain /
Knowledge Base** entries via gated tools. Writes to tenant memory are `side_effecting` (audited) but
`money:false`. Used to carry lead state, computed segments, AI outputs between nodes.

### 4.9 `integration` — call a dormant-until-creds external adapter (gate per adapter)
A specialization of `action` whose tool is an external integration (ad platforms, email/Listmonk,
WhatsApp BSP, payment, calendar). Every adapter follows the `whatsapp.py` dormant pattern: import-safe,
`{"status":"not_configured"}` until creds, never raises. Money-moving integrations (`ads.*`, paid
sends) carry `money:true` → BUDGET+APPROVAL apply.

### 4.10 `error` (Error-Handling) — catch + route failures
A node referenced by another node's `on_error` edge (or the workflow's default error sink). On a node
exception (after Hatchet retries exhausted) or a tool `{"ok":false}`, the run routes here. The error node
can: notify (`PushNotification`/webhook), open a Human-Handover ticket (with an AI summary), retry with
backoff (bounded), or terminate the run as `failed`. **Money fail-safe (reused from AI Manager §6):** a
failed `money:true` node HALTS all remaining money nodes in the run (fail-safe, not fail-open) and routes
to the error node.

> **Node→gate matrix (the safety contract at a glance):**
> | Node | side_effecting | money | Gate |
> |---|---|---|---|
> | trigger / condition / delay / wait / data(read) | no | no | none |
> | data(write) / suppression.add / campaigns.* | yes | no | audit |
> | ai_agent / action / integration (internal credit) | yes | no* | credit debit + audit |
> | ai_agent / action / integration (external `ads.*`, paid) | yes | **yes** | **BUDGET hold + APPROVAL(>threshold) + audit** |
> | budget | (control) | — | reserves the hold |
> | approval | (control) | — | firewall step-up to resume |
> | error | varies | no | audit |
> `*` internal actions cost metered credits (debit the wallet/ledger), allowed autonomously up to the
> per-run action cap; only **external money** trips the human APPROVAL.

---

## 5. THE COMPILER + DURABLE INTERPRETER (how the graph runs on Hatchet)

**Decision: ONE generic durable orchestrator workflow that *interprets* the graph — NOT codegen-per-workflow.**
Codegen-per-workflow (compile each DSL into a bespoke Hatchet workflow file) would mean shipping
tenant-authored code into the worker — a security and operability nightmare on a money path. Instead:

```python
# workflow/compiler.py + workflow/interpreter.py  (NEW)
wf_engine = hatchet.workflow(name="wf-run", input_validator=WfRunInput)

@hatchet.durable_task(name="wf-run", retries=1, execution_timeout=timedelta(days=14))
async def run_workflow(input: WfRunInput, ctx: DurableContext) -> dict:
    defn = load_published_def(input.workflow_id, input.version)     # immutable snapshot from PG
    if guards_killed(defn, input.tenant_id):                        # kill-switch / DND / window
        return _audit_halt(ctx, "killed")
    bag   = dict(input.seed)                                        # the run data bag
    node  = defn.trigger.node_id
    steps = 0
    while node is not None:
        if steps >= defn.guards["max_actions"]: return _audit_halt(ctx, "max_actions")
        steps += 1
        n = defn.node(node)
        # idempotent claim (write-ahead, atomic) keyed (run_id,node_id,attempt) — RTF-11 pattern
        if not claim(ctx.run_id, node, attempt=ctx.attempt):
            res = load_existing_node_result(ctx.run_id, node)      # re-run safety: replay, don't redo
        else:
            audit("workflow.node.start", run=ctx.run_id, node=node, reason=n.summary())
            res = await NODE_EXECUTORS[n.type].execute(n, ctx, bag) # may DURABLY sleep / wait / pause
            persist_node_run(ctx.run_id, node, res)                 # PG row (status, output, spend)
            audit("workflow.node.end", run=ctx.run_id, node=node, meta=res.redacted())
        bag.update(res.bag_updates)
        node = pick_next_edge(defn, node, res, bag)                 # condition/when/on_error routing
    settle_and_release_holds(ctx.run_id)                            # release leftover BUDGET hold
    return {"status": "completed", "steps": steps}
```

Why this is correct on the settled foundation:
- **Durable.** `run_workflow` is a single `@hatchet.durable_task`; its `aio_sleep_for`/`aio_wait_for_event`
  inside DELAY/WAIT/APPROVAL nodes survive worker restarts (the proven `wa-cadence`/`retry-callback`
  pattern). A crash mid-run resumes at the SAME node, replaying completed nodes from their persisted
  `node_run` rows (the `claim()` → `load_existing_node_result` branch) — at-least-once made
  exactly-once-effect by the claim, exactly as `orchestration-hatchet.md` §5 demands.
- **Concurrency.** Per-tenant fan-out (a trigger that targets many leads) uses Hatchet CEL concurrency on
  a child `wf-node-batch` task keyed `input.tenant_id` — the same mechanism that replaced `ACTIVE_CALLS`.
- **One engine, inspectable.** No tenant code in the worker; the worker only interprets a validated,
  immutable JSON snapshot whose every tool is a vetted registry entry.
- **Scheduling.** `schedule`-trigger workflows register a thin per-tenant Hatchet cron that calls
  `wf_engine.run_no_wait(input=…, key="sched:<wf>:<tick>")`; `event`-trigger workflows are kicked from
  the `workflow/events.py` bridge on spine emits.

**Compiler responsibilities (`compiler.py`):** validate the DSL (§3 invariants + dominator check §7.1),
resolve every tool reference against the registry, freeze an immutable `version` snapshot to `wf_versions`,
register/refresh the Hatchet cron for schedule triggers, and subscribe event triggers in the event bridge.
It does NOT emit Python — it emits a *validated record* the single interpreter consumes.

---

## 6. DATA MODEL — 6 Postgres tables (brand-new; RLS by tenant; no JSON migration)

Like the wallet tables, these are **net-new** → they need none of P1's dual/shadow-diff machinery, only
Postgres provisioned (P1 U1). All carry `tenant_id` + an RLS policy `USING (tenant_id = current_setting
('app.tenant_id'))` (the P1 multi-tenant pattern). Money/spend on a node-run row writes in the SAME txn as
the wallet settle (the `credit-ledger-firewall.md` discipline).

| Table | Key columns | Purpose |
|---|---|---|
| `wf_definitions` | `workflow_id PK, tenant_id, name, status, current_version, industry_pack, created_by, updated_at` | the editable head of each workflow. |
| `wf_versions` | `(workflow_id, version) PK, tenant_id, definition JSONB, published_at, published_by, hash` | **immutable** published snapshots (versioning + rollback + audit). `definition` = the full §3 DSL. |
| `wf_runs` | `run_id PK, workflow_id, version, tenant_id, trigger_kind, trigger_ref, status, seed JSONB, hold_id, started_at, ended_at` | one row per execution. `status` ∈ queued/running/awaiting_approval/sleeping/completed/failed/killed. `hold_id` → wallet hold. |
| `wf_node_runs` | `(run_id, node_id, attempt) PK, tenant_id, type, status, output JSONB, spend_minor BIGINT, claim_key, started_at, ended_at` | per-node execution state — the replay/idempotency source. UNIQUE on `claim_key` (the write-ahead claim, RTF-11). |
| `wf_triggers` | `id PK, workflow_id, tenant_id, trigger_kind, event_name, config JSONB, active` | event/webhook subscriptions the bridge reads. |
| `wf_schedules` | `id PK, workflow_id, tenant_id, cron, tz, active, last_fired_at` | cron-trigger registry (mirrors the Hatchet cron). |

**Per-workflow analytics** are a **deterministic roll-up** over `wf_runs` + `wf_node_runs` (no new write
path): runs started/completed/failed, conversion (runs reaching a goal node), per-node success rate +
p50/p95 duration, total credits + external spend, approval latency, drop-off node. Exposed at
`GET /workflows/{id}/analytics` and rendered on the canvas (per-node badges) — the "per-workflow analytics"
requirement, fed by the same rows the interpreter writes, so it can never drift from reality.

---

## 7. SAFETY / GUARDRAILS (the highest-risk surface — the hard rules, enforced in CODE)

The task's hard rule: **no bulk / spend / refund / DND-violation / out-of-hours / data-export without
approval-node + budget-node + audit.** This is enforced at THREE layers (defence in depth):

### 7.1 Publish-time (static) — the dominator check + classification
A workflow **cannot be published** unless, on the workflow graph, **every `money:true` (or bulk/destructive/
export-classified) node is dominated by a `budget` node AND (if its recomputed spend > threshold) reachable
only through an `approval` node** on *every* path from the trigger. This is a standard graph-dominator
analysis in `compiler.py`. Node risk classification is derived from the **`ToolSpec` metadata**
(`money`, plus new `bulk`/`destructive`/`export` flags on the registry — e.g. `whatsapp.send` to a segment
> N = bulk; `leads.export` = export; `billing.refund` = destructive+money), NOT from the
tenant-authored JSON. A definition that wires a money node with no dominating budget node is **rejected at
publish with the exact offending node ids.** (Refund/export/delete tools are gated identically.)

### 7.2 Run-time (dynamic) — recompute-from-resolved-args + wallet + firewall
At execution, NOTHING trusts the definition's self-reported numbers (`automation-aimanager.md` RTF-5):
- **Spend** is recomputed from the *resolved tool + args* of each money node; the BUDGET hold
  (`wallet.reserve`/`settle`, atomic, fail-closed) is the authority; the cap the model/JSON claims is
  ignored if smaller-than-real.
- **Approval** threshold/role/PIN are recomputed server-side; resumption requires a fresh firewall
  step-up token. The kill-switch + DND + calling-window + consent guards are re-checked inside the same
  critical section as each money/bulk action (RTF-7 there) so a mid-run flip aborts the NEXT risky node.
- **DND / consent / window:** `respect_dnd`/`respect_consent`/`calling_window` re-check the existing
  suppression set + consent store + `_in_window` before any call/message node — reusing
  `caller._suppressed_set`, `_in_window`, `_clamp_to_window`. An out-of-window action durably sleeps to
  the next window open (the `retry-callback` pattern) rather than firing — never violates the window.

### 7.3 Audit (immutable) — every node + every gate
Every node start/end, every gate decision (`workflow.node.start/end`, `workflow.budget.reserve/settle`,
`workflow.approve/reject`, `workflow.cap_block`, `workflow.killswitch`, `workflow.dnd_block`) writes an
`audit.record(...)` with `actor`, `tenant_id`, `reason`, redacted `meta`. Money-mutating rows are written
in the SAME DB txn as the wallet movement (tamper-evident; `credit-ledger-firewall.md` §0.3). This IS the
"immutable audit log of every AI decision (with reason)".

### 7.4 The expression sandbox (condition/`when`/`expr`) — no arbitrary code
Tenant-authored expressions are the one place untrusted input reaches evaluation. They are evaluated by a
**restricted, allow-listed evaluator** (a tiny `simpleeval`-style AST walker — no `eval`, no attribute
access beyond a whitelisted context, no imports, no calls except a fixed safe function set), operating only
on the read-only context (lead/campaign/billing fields + data bag). Anything outside the grammar fails
validation at publish. This closes the "tenant-authored automation → code execution" hole that a generic
engine would open.

### 7.5 RBAC + per-run kill-switch
Publishing, approving, and editing workflows reuse `auth.can(role, action)` — only manager/admin may
publish or approve; per-workflow + per-tenant kill-switch (`guards.kill_switch` + a global
`WORKFLOW_KILLSWITCH=1` break-glass env) halts at the interpreter's top, checked again before each risky
node. Workflow defs/runs are RLS-scoped so one tenant can never see/trigger another's.

---

## 8. FRONTEND — the React-Flow canvas (in the Next.js panel)

- **Lib:** `@xyflow/react` (React Flow) v12.10.x, **MIT** — added to `famit-panel/package.json`. Mounts as
  a new route group `src/app/workflows/` (`/workflows` list, `/workflows/[id]` editor, `/workflows/[id]/runs`
  run-inspector) — reusing the panel's existing auth/layout/providers/UI kit (Next 15, React 19).
- **Editor:** node palette (the 10 node types, grouped), drag-to-canvas, typed edge connections,
  per-node config panels (driven by each node's JSON Schema → form), live validation (calls
  `POST /workflows/{id}/validate` → shows the dominator/safety errors inline before publish), version
  history + diff, publish button (gated by RBAC).
- **Run inspector:** replays a run by reading `wf_node_runs` — colours each node by status, shows per-node
  output/spend/duration, the approval-pause banner with an inline PIN step-up to resume, and the analytics
  badges (§6). The canvas is a *thin view*; ALL safety logic is server-side (the frontend can render a
  bad workflow but the server refuses to publish/run it).
- **AI-Manager integration:** the AI Manager can author a workflow by emitting the §3 DSL (a
  `workflows.create`/`workflows.publish` tool added to its registry) — voice command "build me a hot-lead
  nurture" → a draft workflow the founder reviews on the canvas and publishes. Approval pauses surface in
  the same inbox as AI-Manager plans.

---

## 9. ENDPOINTS (additive `APIRouter`, mounted via a DEFERRED un-applied diff — never edits `caller.py`)

| Method | Path | Purpose | Auth |
|---|---|---|---|
| `GET` | `/workflows` | list defs (RLS) | member+ |
| `POST` | `/workflows` | create draft | manager+ |
| `GET` | `/workflows/{id}` | def + versions | member+ |
| `PUT` | `/workflows/{id}` | edit draft | manager+ |
| `POST` | `/workflows/{id}/validate` | static validation (dominator/safety/expr) → errors | manager+ |
| `POST` | `/workflows/{id}/publish` | freeze version, register triggers/cron | manager/admin |
| `POST` | `/workflows/{id}/run` | manual trigger → `wf_engine.run_no_wait(key=…)` | manager+ |
| `POST` | `/workflows/{id}/hook` | inbound webhook trigger | signed/scoped |
| `GET` | `/workflows/runs?status=…` | runs (incl. `awaiting_approval`) | member+ |
| `GET` | `/workflows/runs/{run_id}` | run + node-runs (the inspector) | member+ |
| `POST` | `/workflows/runs/{run_id}/approve` | firewall step-up → resume (`emit wf_approval` event) | manager/admin + PIN |
| `POST` | `/workflows/runs/{run_id}/reject` | reject a paused run | manager/admin |
| `POST` | `/workflows/runs/{run_id}/cancel` | cancel + release holds | manager/admin |
| `POST` | `/workflows/killswitch` | halt all runs (tenant) | admin |
| `GET` | `/workflows/{id}/analytics` | per-workflow roll-up | member+ |
| `GET` | `/workflows/templates` | template library | member+ |
| `POST` | `/workflows/templates/{tid}/instantiate` | clone a template into a draft | manager+ |

`workflow_wiring.diff` (the ONLY thing that touches `caller.py`, delivered un-applied):
```diff
+ from workflow.endpoints import router as workflow_router
+ from workflow.events import attach_event_bridge
  ...
+ app.include_router(workflow_router)          # additive; behind existing auth deps
+ attach_event_bridge(app)                     # subscribe spine emits → workflow event triggers
```

---

## 10. SERVICES & WHERE IT SITS ON THE SETTLED FOUNDATION

| Plane (settled) | What workflow-studio adds there |
|---|---|
| **Panel** (Next.js) | the React-Flow canvas + run inspector (`/workflows/*`). |
| **Modular-monolith control-plane API** (`caller.py` + additive routers) | the `/workflows/*` router (loopback-callable), the event bridge, the validator/compiler entry. |
| **Hatchet worker-spine** (the `famit-orchestrator` worker) | the `wf-run` durable interpreter + `wf-node-batch` fan-out are registered as NEW workflows on the SAME worker (one more set of durable tasks; no new service). Schedule triggers add per-tenant Hatchet crons. |
| **Voice plane** | untouched. Workflows can *trigger* calls (via `leads.enqueue_calls` → `/run` → the existing campaign-run path) but add nothing to the latency-critical voice loop. |
| **Postgres** | the 6 new tables (RLS), alongside the wallet tables; reuses the P1 engine + the §9 orchestration-DB split trigger applies equally (workflow run volume rides the same scale signal). |

**Module-monolith fit:** `workflow/` is a new top-level package next to `automation/aimanager/`, sharing
the same conventions (dormant-until-creds, additive router via deferred diff, own JSONL/PG state, reuse of
`audit.py`/`auth.py`/`wallet.py`/`firewall.py`). It is **service-extractable** later (it already talks to
the API over loopback and to the engine over Hatchet) but ships *in* the monolith — matching the settled
"modular monolith, extract only at a named scale trigger" verdict.

---

## 11. DEPENDENCIES

- **HARD pre-reqs:** Hatchet engine live (`orchestration-hatchet.md` UNITs 0–2) for the durable
  interpreter; Postgres provisioned (P1 U1) for the 6 tables; `wallet.py` + `firewall.py` + `audit.py`
  (`credit-ledger-firewall.md`) for BUDGET/APPROVAL/audit nodes; the AI-Manager tool registry
  (`automation-aimanager.md`) for Action/AI-Agent/Integration nodes (the studio can ship with a *subset*
  of registry tools if the AI Manager isn't fully built — the node executors only need the `ToolSpec`
  interface).
- **pip (new):** none required for the engine beyond what's already pinned (`hatchet-sdk`, `pydantic`,
  `asyncpg`); the expression sandbox is a tiny vendored evaluator (or `simpleeval`, MIT, optional).
- **npm (new):** `@xyflow/react` (MIT) in the panel.
- **Dormant-until-creds:** every Integration adapter follows the `whatsapp.py` pattern; the LLM driver
  for AI-Agent nodes is the AI-Manager driver (dormant; StubPlanner offline). **Zero founder credentials
  needed to BUILD or to pass the offline test.**
- **Soft order:** wallet + firewall + a minimal tool registry SHOULD land before money/external nodes go
  live; the canvas + control-flow nodes (trigger/condition/delay/wait/data/condition) + internal-credit
  actions can ship first and are independently useful.

---

## 12. OFFLINE ACCEPTANCE TEST (`workflow/tests/test_offline.py`) — ZERO keys, ZERO network

Run: `python -m pytest workflow/tests/test_offline.py -q` — must pass with **no env keys and no network**
(StubTools + StubPlanner + an in-memory wallet/firewall/audit fake, mirroring `automation-aimanager`'s
offline test). Asserts:

1. **DSL validation:** a valid §3 workflow validates; a workflow with a `money:true` node NOT dominated by
   a `budget` node is **rejected at publish** with the offending node id (the dominator check); a cyclic
   non-delay graph and an unknown-tool reference are rejected.
2. **Expression sandbox:** a `condition` with a whitelisted expr evaluates; an expr containing `__import__`
   / attribute escape / a call to a non-whitelisted name is **rejected at validation** (no code executes).
3. **Interpreter happy path:** publish → `run` a trigger→condition→action(internal)→delay→action graph on
   StubTools; assert node-run rows written in order, data bag threaded, run `completed`, audit rows
   (`workflow.node.start/end`) present.
4. **BUDGET gate:** a money node draws a hold from the fake wallet; an over-cap money action is
   **trimmed/parked deterministically** before any execute, with a `workflow.cap_block` audit row — the cap
   enforced by code, not the model.
5. **APPROVAL gate:** a money plan > threshold **pauses** (`status=awaiting_approval`, nothing executed);
   a resume WITHOUT a valid step-up token is refused; with a valid (fake) step-up token the run resumes and
   executes; audit shows `workflow.node.start → workflow.approve → workflow.node.end` in order. A plan with
   self-asserted `requires_approval:false` but real money > threshold is STILL parked (advisory-field test,
   RTF-5).
6. **Idempotency / crash-replay:** simulate a re-run of the durable task at a mid-graph node (re-enter
   `run_workflow` with the same `run_id`) → completed nodes REPLAY from `wf_node_runs` (no duplicate
   execute, no double-spend); exactly one execution record per `(run_id, node_id, attempt)`.
7. **DND / window:** a call/message node with the lead in the suppression set is **skipped**
   (`workflow.dnd_block`); an out-of-window action defers (durable sleep) rather than firing.
8. **Kill-switch:** with the kill-switch on, `run_workflow` returns `status=killed` and zero node
   executes / zero new node-run rows.
9. **Dormant integrations:** an `integration` node whose adapter is unconfigured returns
   `{"status":"not_configured"}` and makes NO network call.

A second tiny self-test feeds the validator a malformed definition and asserts rejection (mirrors the
repo's `selftest_bad_*` convention).

---

## 13. BUILD ORDER (each a verifiable unit; ship the safety spine first)

1. **DSL + validator + compiler (static)** — `workflow/dsl.py`, `compiler.py` (dominator check, expr
   sandbox), the 6 PG tables (DDL, idempotent) → unit-test validation/rejection. *(no engine yet)*
2. **Interpreter + control-flow nodes** on Hatchet — `interpreter.py` + trigger/condition/delay/wait/data
   executors + StubTools → **offline test §12 items 1–3,6 green.** *(internal-only, no money)*
3. **BUDGET + APPROVAL + audit nodes** — wire `wallet.py`/`firewall.py`/`audit.py` → §12 items 4,5,8 green.
   **This delivers the entire safety spine, fully tested, no external dependency.**
4. **Action / AI-Agent / Integration nodes** — wire the AI-Manager tool registry + LLM driver (dormant) +
   loopback service auth → §12 items 7,9 green.
5. **Endpoints + `workflow_wiring.diff` (un-applied) + event bridge** → router import test.
6. **React-Flow canvas + run inspector** in the panel (`@xyflow/react`).
7. **Template library** (industry-pack workflow JSONs) + per-workflow analytics roll-up.

Ship 1–3 first: the governed-execution core, fully offline-tested, before any node can touch money or a
network. 4–7 light up the AI workforce, the canvas, and templates once the registry/creds/canvas land.

---

## 14. WHAT THIS UNBLOCKS (modules that compose on this foundation)

This is the connective tissue. Directly unblocks / powers:
- **Workflow Builder** (the module itself) — IS this spec.
- **Lifecycle Trigger Engine** — event triggers + durable delays = proactive re-engagement by service cycle.
- **AI Manager** — gains `workflows.create/publish/run` tools → voice-commanded automation authoring.
- **Funnels, Campaigns, Sales Pipeline** — wired as workflows (lead→call→WA→qualify→book→pay).
- **WhatsApp Automation, AI Voice Calls, Customer Support** — become nodes orchestrated end-to-end.
- **Booking, Payments/Collections, Reviews/Referral** — post-conversion workflow stages.
- **Industry Packs / Template Library / Marketplace** — shipped as workflow JSON; the marketplace surface.
- **Ad Automation, Creative Studio** — gated money/creative nodes inside campaign workflows.
- **AI Task Manager, Human Handover, Revenue Attribution** — error/approval nodes + audit feed these.
The 11 AI-workforce roles all become `ai_agent` nodes reading the Business Brain + Knowledge Base; the
hard safety rules (BUDGET/APPROVAL/audit/DND) make tenant- and AI-authored automation *safe to ship*.

---

## 15. HONEST REAL-VS-HYPE

| Claim | Reality |
|---|---|
| "n8n in a box" | **No** — native engine. Same *UX* (visual node graph), but durable on Hatchet, money-safe via our wallet/firewall, MIT-licensed canvas, no fair-code landmine, no second stateful service. |
| "Tenants automate anything unsupervised" | **No.** Money/bulk/destructive/export nodes are code-gated: a dominating BUDGET node is required to publish, and spend > threshold pauses for a PIN-verified human APPROVAL. Default threshold 0 = every external rupee approved until autonomy is deliberately granted. |
| "Fully autonomous" | The graph executes autonomously *within* hard, code-enforced caps the definition cannot override; a failed money node halts the rest (fail-safe). |
| "Works offline" | The engine, gates, audit, idempotency, and validation work fully offline (StubTools/StubPlanner/fakes). AI-Agent *reasoning quality* needs an LLM key; the *safety machinery* does not. |
| "Visual builder = no-code safety" | The canvas can render an unsafe graph; the SERVER refuses to publish/run it (dominator check + expr sandbox + RBAC). Safety is server-side, not UI-side. |
| "Replaces ops/dev for automation" | It removes the need to hand-code drip/funnel logic and lets non-devs (and the AI Manager) compose pipelines — within governance. It does not remove the human approval on real spend. |

---

## Sources
- In-repo settled foundation (verified 2026-06-09): `design/orchestration-hatchet.md` (Hatchet durable
  engine, idempotency RTF-11, durable sleep/wait, CEL concurrency), `design/credit-ledger-firewall.md`
  (wallet ACID ledger + firewall step-up + immutable audit), `design/automation-aimanager.md`
  (plan→approve→execute, tool registry, guardrails, kill-switch, RTF-1/4/5), `design/automation-marketing.md`
  §1.1 (the n8n Sustainable-Use-License verdict — build native), `design/p0-foundation.md` /
  `design/p1-postgres.md` (Postgres strangler + RLS + import-safety), `famit-panel/` (Next.js 15 + React 19).
- [React Flow / xyflow — node-based UI, MIT](https://reactflow.dev/) · [@xyflow/react v12.10.2 (npm, 2026-03-27)](https://www.npmjs.com/package/@xyflow/react)
- [Hatchet — durable execution (Postgres, drop-in Temporal replacement)](https://docs.hatchet.run/home/durable-execution) · [Hatchet architecture](https://docs.hatchet.run/home/architecture)
- [n8n Sustainable Use License (fair-code; restricts automation-as-value-to-3rd-parties)](https://docs.n8n.io/sustainable-use-license/) · [n8n vs Activepieces vs Windmill licenses — Boolean & Beyond 2026](https://www.booleanbeyond.com/en/insights/n8n-vs-activepieces-vs-windmill-open-source-automation)
