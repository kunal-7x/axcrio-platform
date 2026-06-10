# `ai-workforce` — The Agent Framework Spine — Execution-Ready Design Spec

> **What this is:** the ONE reusable agentic system that powers every AI role in the OS
> (AI Telecaller, WhatsApp Salesperson, Support Agent, Campaign Strategist, Creative Producer,
> Ad Operator, CRM Manager, Booking Assistant, Billing Manager, Analytics Manager, Ops Manager),
> the voice-first **AI Manager** command center, and the **Workflow Studio** `AI-Agent` node.
> Design it once; reuse it everywhere. An agent role becomes a **row of config**, not a new module.
>
> **Status:** READY-TO-BUILD design. No code shipped. Verified 2026-06-09 against live source under
> `C:\Users\kunal\Desktop\caps\droplet_work\` and the settled design docs in `caps\design\`.
> **Posture (inherited, non-negotiable):** STRANGLE & EVOLVE. Non-breaking, behind flags,
> crash-safe per unit, dormant-until-creds. The live system at `panel.famit.in` keeps earning.
> **Hard rule honored:** does NOT modify `caller.py` / `agent.py` business logic. All exposure into
> the spine is delivered as a written, *un-applied* `caller_wiring.diff`, exactly like `aimanager`.

---

## RED-TEAM FIXES (folded)

> Adversarial review 2026-06-09 against live source (`auth.py`, `caller.py`) and the **sibling settled
> specs** (`platform-ai-manager.md`, `credit-ledger-firewall.md`, `orchestration-hatchet.md`). Verdict:
> **GO** — the core correctly reuses the head-start (per-run per-tenant token verified on disk, roles-as-data
> over one runner, guardrails composed on the existing wallet/firewall, DB idempotency, honest dormancy). The
> issues found were all bounded and are folded below; none rebuilds the head-start or is unsound. The four
> previously-folded advisor fixes (per-run token §3.1/§14; `InMemoryStoreBackend` §3.1#4; "roles are data"
> made precise §4/§5; `agent_roles` table) stand. These additional fixes supersede the conflicting prose
> elsewhere in this doc.

**RT-1 — DO NOT re-implement the voice AI Manager; DELEGATE to the settled `platform-ai-manager.md`.**
The voice command center is **already a settled, separately-owned module** (`platform-ai-manager.md`, locked
2026-06-09). It owns: phone-number registration, the deterministic call state machine
(`VERIFY→CONTEXT→INTENT→PERMIT→PIN→CONFIRM→DELEGATE→REPORT`), intent parsing, **PIN/OTP step-up over the
voice channel** (including the spoken-PIN audio-leak mitigation, its §6.5), and — load-bearing — the
**cross-plane transport reality that the voice box is NOT the API box** (its §3.2: authenticated HTTP to
`AIM_VOICE_API_BASE`, PIN verified only on the API box). That spec explicitly reserved this seam: *"when the
workforce-of-roles layer is later designed, the voice layer's `delegate.py` target swaps behind the same
interface."* This spec IS that layer, so it must land **in** that seam, not around it.
- **Therefore §9 and `aiwf/manager/` are REDEFINED as a thin delegation target, not a re-implementation.**
  `aiwf/manager/intent.py` and `aiwf/manager/voice_cmd.py` are **deleted from this package** (number
  registration, intent parsing, the call state machine, and voice PIN live in `platform-ai-manager.md`).
  Only `aiwf/manager/delegate.py` survives — and it is just "given a *verified, permissioned, PIN-backed*
  `Intent` handed over by `platform-ai-manager.md`'s `delegate.py`, select the right `RoleSpec` and call
  `AgentRunner.run(...)`." The `manager` role stays one `ROLE_REGISTRY` row (the meta-delegator).
- **Endpoint change:** `POST /aiwf/manager/numbers` and `POST /aiwf/manager/command` are **removed** from §13
  (they belong to `platform-ai-manager.md`'s router). The workforce surface keeps only `POST /aiwf/runs`
  (which the voice spec's API box calls after it has already verified identity + permission + step-up).
- **Why this matters:** the original §9 claimed "the existing LiveKit voice plane handles the audio; the AI
  Manager is the brain" as if same-box — which **contradicts** the settled §3.2 cross-plane decision and
  would silently re-open the spoken-PIN leak the voice spec already closed. Deferring fixes all of it.

**RT-2 — Idempotency key MUST be resource-stable, not sequence/action-id-based (money-path correctness).**
The doc is internally inconsistent: §4 proposes `'<run_id>:<seq>'` *or* `'<run_id>:<tool>:<resource>'`, while
§6's loop uses `f"{run.id}:{action.id}"`. Under **Hatchet at-least-once replay** (the settled durability
plane, `orchestration-hatchet.md` §5), if `seq`/`action.id` is regenerated when the step re-executes after a
crash, the UNIQUE index sees a *brand-new key* and the guard **double-executes / double-spends** — the exact
bug it exists to prevent. Offline test #10 only proves "the DB rejects a duplicate key handed to it," NOT
"a durable replay reproduces the same key." **Fold (binding):**
- For every `side_effecting`/`money:true` tool, `idempotency_key = "<run_id>:<tool>:<business_resource_id>"`
  where `business_resource_id` is a **deterministic function of the run + the target resource** (e.g.
  `lead_id`, `campaign_id`, recipient msisdn, invoice_id) — NOT `seq` and NOT a freshly-minted `action.id`.
  It must be byte-identical across a Hatchet retry of the same logical action.
- §6's `f"{run.id}:{action.id}"` and the wallet idem keys (`aiwf:{run.id}:{action.id}`,
  `settle:…`, `release:…`) are corrected to use this resource-stable key.
- Add offline test **#10b**: simulate a replay by calling the same action with a *regenerated* `action.id`
  and assert ONE `tool_result` (proves stability across re-derivation, not just within one in-memory pass).

**RT-3 — `tenant_of_run` provenance is the isolation guarantee; pin it to the authenticated trigger.**
The per-run token fix (§3.1) is only as strong as where `org_id_of_run` comes from: the runner holds the
`var/secret` signing key and can mint a valid token for *any* tenant via `auth.issue_pair`. **Binding rule:**
`org_id_of_run` and `actor` are set **once, at `store.create_run`, exclusively from the authenticated
trigger** (the verified voice caller's tenant, the workflow's owning tenant, or the JWT on `POST /aiwf/runs`)
— and are **never** read from the LLM plan, from `trigger_ref`, or from any model-supplied field. The runner
mints the loopback token from *that* pinned `org_id` only. (Defense-in-depth with the existing default-deny
`policy.resolve` and `auth.can`, which already cap a run at the human actor's RBAC.)

**RT-4 — Residual (non-blocking) risks, recorded:**
- **Ad-spend reserve vs. accrual mismatch.** `wallet.reserve` is an *instantaneous hold*, but `ads.set_budget`
  sets a multi-day external *ceiling* that accrues spend over time at the ad network — not an instant debit.
  The reserve↔accrual mapping for the `ad`/`ops` roles is **unspecified here**; it must be resolved against
  `automation-ads.md` (CDR/spend-callback reconciliation) before the `ad` role spends live. Until then, `ad`
  ships `propose`-only (every spend human-approved), which the §14 defaults already enforce.
- **`wallet.py` / `firewall.py` are spec, not yet source.** They are build-units 2 & 4 of
  `credit-ledger-firewall.md` (the doc labels this honestly in §1/§14). Build-order dependency is therefore
  hard: **the live money path of this spine cannot activate until those two units are built and deployed.**
  The offline spine (units 1–5, §15) has no such dependency and is buildable now.
- **Roles-as-data is structural, not a quality claim.** A new role being "a config row" guarantees the
  *safety machinery* is reused; it does NOT guarantee the role *reasons* well — that still needs the LLM key,
  a tuned prompt, and an eval-harness pass (§12) per role. Honest scope, restated.

---

## 0. WHY THIS EXISTS (one paragraph, honest)

The `aimanager` spec (`design/automation-aimanager.md`) already designed a single plan→approve→execute
agent loop with spend caps, an approval gate, a kill-switch, and an immutable audit trail. **That loop
is the prototype; this spec extracts and generalizes it into a framework.** Instead of hand-coding a
second loop for the WhatsApp salesperson, a third for support, an eleventh for ops — and re-deriving the
guardrails each time — we build ONE `AgentRunner` parameterized by a `RoleSpec` (who the agent is) and a
scoped `ToolRegistry` (what it may touch). Every role, the AI Manager, and every Workflow-Studio AI node
run on this same spine, so the safety machinery — **scoped permissions, the approval/PIN/budget gates,
the immutable audit-of-decisions ledger, human handover** — is written, tested, and reasoned about
*once*. `aimanager` then becomes one registered role (`ops_manager`) instead of a bespoke module. This is
the load-bearing decision: roles are **data**, guardrails are **shared code**, and nothing in the voice
spine is touched.

**Real-vs-hype, stated up front:** this is *augmentation under hard, code-enforced gates*, not an
unsupervised workforce spending real money. Read-only and internal-metered actions can run autonomously;
anything that spends external money, sends in bulk, deletes, exports, refunds, changes price, or violates
DND/calling-window is **deterministically gated** (budget node + approval/PIN) and **immutably audited**.
The LLM proposes; deterministic Python decides what is allowed. The whole safety machinery is exercisable
**offline with zero keys** on a deterministic stub planner.

---

## 1. GROUND TRUTH — what already exists (cite before trusting memory)

Verified 2026-06-09 against `droplet_work/` and the cross-referenced design specs. The framework
**composes these primitives**; it adds no new datastore concept the foundation lacks.

| Asset | Path / spec | What `ai-workforce` reuses |
|---|---|---|
| Single agent loop prototype | `design/automation-aimanager.md` | The `plan → guardrails → approval → execute` shape, `ToolSpec` dataclass, StubPlanner offline path, dormant LLM driver. **We generalize it; `aimanager` becomes the `ops_manager` role.** |
| Dormant-until-creds template | `droplet_work/whatsapp.py` | EXACT pattern for the LLM driver + any new adapter: `_cfg()`, `is_configured()`, `status()`, no-op `{"status":"not_configured"}`, never raises, redact secrets. |
| Immutable audit ledger | `droplet_work/audit.py` + `events` table (`p1-postgres.md` §3.6) | `audit.record(actor, action, object_type, object_id, …, meta)` append-only JSONL **and** the dual-mirrored `events` PG table. The **decision-of-record** ledger. We add new action names; we do NOT reinvent. |
| Wallet ACID firewall | `design/credit-ledger-firewall.md` (`wallet.py`) | `reserve()/settle()/release()/balance()` atomic conditional-UPDATE budget gate. The **BUDGET node** and every `money:true` tool reserve against this. No double-spend, no oversell. |
| Action Firewall (PIN/step-up) | `design/credit-ledger-firewall.md` (`firewall.py`) | `mint_step_up()/require_step_up(scope)` HS256 step-up token (`amr:pin`, `sub`-bound). The **APPROVAL/PIN node** and risky-action gate reuse this verbatim. |
| Storage seam + RLS/GUC | `design/p1-postgres.md` (`store.py`, `db/engine.py`, `db/rls.sql`) | `session(tenant_id, is_admin)` / `asession(...)` ctx-managers that `SET LOCAL app.tenant_id`. Every agent table is tenant-scoped with FORCE RLS. Per-store MODE router for non-breaking mirror. |
| Durable orchestration | `design/orchestration-hatchet.md` | Long-running / multi-step agent runs become Hatchet durable tasks (`@hatchet.durable_task`, `ctx.aio_sleep_for`, at-least-once + idempotency keys). The AI workforce **is a Hatchet workload**. |
| API surface (the hands) | `caller.py` routes (60+ endpoints) | Each operation (`/campaigns`, `/leads`, `/run`, `/whatsapp/send`, `/billing`, `/suppression`, `/audit`, …) becomes a *tool*. Transport = authenticated localhost loopback (the verified "don't touch caller.py" answer). |
| Service-token minting | `droplet_work/auth.py` (`issue_pair()`, HS256, `var/secret`, `can(tenant, action)`) | Loopback tools authenticate as a real admin/manager tenant token (`AIWF_SERVICE_TOKEN`); RBAC via the existing `can()`. No new bypass-auth path. |
| Eval / replay gate | `design/eval-harness.md` | The offline harness that gates prompt/model swaps. Agent **roles** get the same treatment: a role's prompt+tools change must pass an offline eval before it goes live. |
| Dynamic context / RAG | `design/dynamic-context-rag.md` | The Business Brain / Knowledge Base retrieval the agent reads as context (precomputed, never per-turn on the voice hot path). Agents read the SAME corpus. |

**Net:** `ai-workforce` is a thin new package (`droplet_work/aiwf/`) that *generalizes* the `aimanager`
loop and *orchestrates existing primitives*. No new spine endpoints touch `caller.py` (additive router
mounted via a deferred diff); no new datastore concept; one env-gated LLM dependency it shares with
`aimanager`.

---

## 2. CHOSEN APPROACH & WHY (web-researched, 2026-active, cited)

### 2.1 Framework shape: **one thin hand-rolled runner, role-parameterized** (NOT CrewAI / LangGraph)

`aimanager` already settled this for its single loop: a ~150-line manual tool-use loop, **not** a heavy
multi-agent framework, because the hard requirements (per-tool approval interrupt, immutable audit,
deterministic offline test, money-path control) are exactly what opinionated frameworks fight. 2026
guidance is consistent: frameworks earn their keep only for durability/graph features we already get from
**Hatchet**; otherwise a thin loop wins on transparency and control. We extend that decision from *one
loop* to *one runner that takes a `RoleSpec`*:

- **Decision:** a single `AgentRunner.run(role_spec, task, ctx)` implementing the manual tool-use loop
  with an explicit per-tool guardrail/approval interrupt — the pattern the Anthropic SDK documents for
  "human-in-the-loop approval before each tool execution." This is the only pattern that lets us gate
  side-effecting tools deterministically.
- **Durability/multi-step:** delegated to **Hatchet** (already the settled orchestration plane), not to a
  framework's in-house graph engine. A multi-day agent workflow (e.g. a nurture sequence) is a Hatchet
  `durable_task` whose steps each call `AgentRunner`. We do not add LangGraph's persistence layer on top
  of a system that already has Postgres + Hatchet.
- **Optional structured-output layer:** **Pydantic AI** *may* be pulled in solely to validate the LLM's
  emitted plan/tool-args against a schema (lightweight, decorator tool registration, type-safe). It is
  NOT required for the offline path — plain `pydantic` (already present via the SQLAlchemy/FastAPI stack)
  + manual JSON-Schema validation suffices and keeps the dependency surface minimal.
- **Rejected:** CrewAI (role-play crews — wrong shape; our "crew" is a typed multi-agent *workflow* in
  Hatchet, not free-form delegation), LangGraph (durable graphs — Hatchet already owns durability),
  smolagents/code-agents (arbitrary code-gen is the wrong primitive for a money/PII-touching agent — we
  want narrow typed tools, per Anthropic's "promote hard-to-reverse actions to dedicated typed tools").

Sources: [Anthropic — Building effective agents / writing tools for agents](https://www.anthropic.com/engineering/building-effective-agents),
[Anthropic — Code execution & tool use with MCP](https://www.anthropic.com/engineering/code-execution-with-mcp),
[Firecrawl — best open-source agent frameworks 2026](https://www.firecrawl.dev/blog/best-open-source-agent-frameworks),
[JetBrains/PyCharm — top agentic frameworks 2026](https://blog.jetbrains.com/pycharm/2026/06/top-agentic-frameworks-for-building-applications-2026/),
[Pydantic AI — production guide 2026](https://www.youngju.dev/blog/ai-platform/2026-04-12-pydanticai-practical-guide.en),
[Hatchet docs — durable tasks](https://docs.hatchet.run).

### 2.2 LLM driver: **provider-agnostic, dormant-until-creds** (shared with `aimanager`)

ONE driver, `aiwf/llm/driver.py`, mirroring `whatsapp.py`'s dormancy contract — **the same module
`aimanager` specifies**, lifted up so all roles share it. Two first-class providers, both dormant until
their key is present:
- **`claude`** (recommended for reasoning-heavy roles — strategist, ops-manager, support): Anthropic SDK,
  model `claude-opus-4-8`, `thinking={"type":"adaptive"}`, `output_config={"effort":"high"}`. **Do NOT**
  send `budget_tokens`/`temperature`/`top_p`/`top_k` (they 400 on Opus 4.8). Use the **manual** agentic
  loop (not the SDK auto-runner) so we interrupt for the guardrail/approval gate. Tool descriptions must
  be *prescriptive about when to call* (Opus 4.8 under-reaches for tools by default). Key `ANTHROPIC_API_KEY`.
- **`groq`** (cheapest; already integrated via `vendors/groq_meter.py` + round-robin keys from the
  fortress work): OpenAI-compatible chat-completions with tool calls. Key `GROQ_API_KEY` (round-robin
  `GROQ_API_KEY_1..N` supported).
- **`none`** (default): no-op `{"status":"not_configured"}`; the **StubPlanner** drives the loop so all
  gates, audit, and orchestration remain exercisable offline.

Per-role override of provider/model is allowed (a cheap role like "tag this lead" can pin Groq; a
strategist can pin Claude) via the `RoleSpec.model` field — but the **driver interface is identical** and
never leaks provider specifics upward. Selection precedence: `RoleSpec.model` → `AIWF_LLM_PROVIDER` →
`none`.

> **Note on the in-repo `claude-api` skill:** model id `claude-opus-4-8`, adaptive thinking, manual
> tool-use loop for human-in-the-loop approval, `output_config.format` for structured plans, and the
> "no `budget_tokens`/`temperature` on Opus 4.8" rule are all sourced from that skill and from
> `automation-aimanager.md`'s already-verified guidance — not from memory.

---

## 3. ARCHITECTURE & DIRECTORY LAYOUT (all new; spine untouched)

```
droplet_work/aiwf/                      # the AI Workforce framework package
├── __init__.py                 # exports: run_agent, AgentRunner, registry, status
├── config.py                   # env: provider, global caps, kill-switch, service token, flags
├── runner.py                   # AgentRunner.run(role, task, ctx) — the manual tool-use loop (the SPINE)
├── roles.py                    # RoleSpec dataclass + ROLE_REGISTRY (the 11 roles + ops_manager + manager)
├── policy.py                   # Policy resolver: which scopes/tools/caps a (role, tenant, actor) gets
├── guardrails.py               # deterministic gates: scope check, budget, approval-threshold, DND/window,
│                               #   bulk/rate caps, kill-switch, idempotency  (NEVER delegated to the LLM)
├── handover.py                 # human-handover: park run, emit AI summary, route to inbox/notify
├── store.py                    # agent_runs / agent_steps / approvals / tool_grants persistence (PG via db/engine)
├── audit_bridge.py             # thin wrapper over droplet_work/audit.py (new aiwf.* action names)
├── planner_stub.py             # DETERMINISTIC StubPlanner — no LLM, no network (the offline path)
├── context.py                  # gather_context(role, tenant, task): Business Brain + Knowledge Base + state
├── tools/
│   ├── __init__.py             # ToolRegistry: name -> ToolSpec(schema, fn, scopes, side_effecting, money)
│   ├── transport.py            # authenticated localhost-loopback client to caller.py /api (AIWF_SERVICE_TOKEN)
│   ├── catalog.py              # the full tool catalog mapping 1:1 to existing /api ops + adapters
│   └── stub_tools.py           # in-memory StubTools (same names, no socket) — makes offline test possible
├── llm/
│   ├── __init__.py
│   └── driver.py               # provider-agnostic LLM: claude | groq | none (dormant)  [shared w/ aimanager]
├── manager/                    # the voice-first AI MANAGER command center
│   ├── intent.py               # NL command -> structured intent (verify intent + permission + risk class)
│   ├── voice_cmd.py            # phone-number registration, command session, PIN/OTP step-up for risky ops
│   └── delegate.py             # routes a verified intent to the right RoleSpec + AgentRunner
├── workflow/                   # Workflow Studio binding
│   └── node.py                 # AI-Agent node: run a RoleSpec as a workflow step; BUDGET/APPROVAL node hooks
├── endpoints.py                # FastAPI APIRouter (additive) — mounted via the DEFERRED diff
├── caller_wiring.diff          # the un-applied diff that mounts endpoints.py + service-token init into caller.py
└── tests/
    └── test_offline.py         # the offline acceptance test (§11) — ZERO keys, ZERO network
```

### 3.1 The four tensions, resolved (inherited from `aimanager`, now framework-wide)

1. **"Tool-calling over the API" vs "do not edit caller.py".** Resolved by the **tool-registry
   abstraction + authenticated localhost loopback** (the answer `aimanager` §3.1 already verified on
   disk: `campaign.py` has no top-level callables and `store.py` needs spine-injected deps, so a pure
   in-process path is not cleanly available without duplication/drift). Each tool `fn` issues an
   authenticated request to `http://127.0.0.1:<port>/<route>`.
   **⚠ CRITICAL — per-run, per-tenant token, NOT a single admin token (verified against live source):**
   `resolve_tenant` (`caller.py:371`) derives the request's tenant from the **token's `sub`** —
   `auth._make_access` (`auth.py:103`) sets `sub = tenant["tenant_id"]` and embeds `is_admin`. So a single
   global `AIWF_SERVICE_TOKEN` (an admin token) would make EVERY loopback call resolve to the admin tenant
   with `is_admin=1` → the RLS GUC is set to admin → a `telecaller` run for tenant A would mis-scope its
   writes (admin/all-tenant) instead of A. That is a cross-tenant isolation bug on the exact money path
   this spine exists to make impossible. **Therefore the runner mints a fresh per-run access token via
   `auth.issue_pair(tenant_of_run)`** (an existing function — takes a tenant dict, `sub` = that tenant's
   id, `is_admin=false`), and `transport.py` presents THAT token on the loopback call. `resolve_tenant`
   then scopes the call to exactly `org_id_of_run` under RLS, with the actor's RBAC honored by `can()`.
   The only env credential is the bootstrap identity used to *mint* per-run tokens (a manager/admin tenant
   record + the `var/secret` signing key the spine already holds) — `AIWF_SERVICE_TOKEN` is reframed as
   "service identity for token minting," dormant-until-set; until present, the live registry returns
   `not_configured` and the runner uses `StubTools`. This reuses the spine's auth/validation/RLS/store
   wiring **verbatim** — no duplication, no money-path drift, no new bypass-auth path in `caller.py`.
   Swapping the registry for `StubTools` is what makes the offline test possible.
2. **Offline acceptance of an LLM-driven framework.** The runner never *requires* an LLM. With
   `AIWF_LLM_PROVIDER=none` the runner uses `StubPlanner`; the offline test drives a full
   plan→guard→approve→execute cycle, an over-budget rejection, a DND block, a handover, and audit writes —
   **zero keys, zero network**. This proves the load-bearing machinery independent of any model.
3. **The LLM driver is itself a dormant integration.** `llm/driver.py` follows the `whatsapp.py`
   contract: import-safe, `is_configured()`, no-op when blank. Default `none`.
4. **State/persistence is real Postgres in production (the upgrade over `aimanager`'s JSONL), behind a
   backend interface so the offline test stays truly offline.** Because `ai-workforce` is the spine for
   the *money path* across many roles and the Phase-2 multi-instance topology, agent run/step/approval
   state lives in **Postgres tables** (§4) with RLS in production — so two app instances + a Hatchet
   worker share one source of truth and idempotency is DB-enforced. To keep the §11 acceptance test
   "zero network, nothing new" claim **honest**, `aiwf/store.py` exposes ONE interface
   (`create_run/add_step/create_approval/already_executed/...`) with TWO backends behind it: a
   **`PgStoreBackend`** (production — the §4 tables via `db/engine.py`) and an **`InMemoryStoreBackend`**
   (the test/offline path — a dict-backed store enforcing the same `idempotency_key` uniqueness + tenant
   scope checks in Python). The offline test selects `InMemoryStoreBackend` and asserts the SAME semantics
   (#10 idempotency, #11 tenant binding) at the interface level; it does NOT depend on Postgres, `jsonb`,
   `timestamptz`, or the partial-unique index porting to SQLite. The full RLS/UNIQUE DDL semantics are
   proven separately in build-unit 1's PG-integration test (§15). `aimanager`'s own JSONL narrative is
   fine for its single ops loop; the *framework* tables are the production authority. Every decision ALSO
   writes `audit.record(...)` into the immutable ledger.

---

## 4. DATA MODEL (new PG tables; tenant-scoped; FORCE RLS — `aiwf/store.py` + Alembic `000N`)

All tables follow the `p1-postgres.md` conventions: `text` PKs matching app id style (`uuid4().hex[:N]`),
`org_id text NOT NULL` (== tenant_id), `data jsonb` catch-all, `ENABLE` + `FORCE ROW LEVEL SECURITY`,
the per-table `org_id`-isolation policy with the `app.is_admin='1'` escape hatch (identical DDL pattern to
`db/rls.sql` §5). App connects as restricted `famit_app` (NOSUPERUSER, NOBYPASSRLS); every query runs
inside `db.session(tenant_id, is_admin)` with `SET LOCAL app.tenant_id`.

```sql
-- One agent invocation (a role doing one task). The unit of work + audit anchor.
CREATE TABLE agent_runs (
  id            text PRIMARY KEY,                 -- run_<hex10>
  org_id        text NOT NULL,                    -- tenant
  role          text NOT NULL,                    -- telecaller|whatsapp|support|strategist|creative|ad|
                                                  --   crm|booking|billing|analytics|ops|manager
  trigger       text NOT NULL DEFAULT '',         -- manager_voice|workflow|api|cron|lifecycle|handover_return
  trigger_ref   text NOT NULL DEFAULT '',         -- workflow_run_id / node_id / command_id
  actor         text NOT NULL DEFAULT 'system',   -- user_id who triggered (or 'system' for autonomous)
  objective     text NOT NULL DEFAULT '',
  status        text NOT NULL DEFAULT 'running',  -- running|awaiting_approval|handover|done|failed|killed|rejected
  llm_provider  text NOT NULL DEFAULT 'none',
  model         text NOT NULL DEFAULT '',
  est_spend_minor   bigint NOT NULL DEFAULT 0,    -- INTEGER paise (never float) — matches wallet
  actual_spend_minor bigint NOT NULL DEFAULT 0,
  created_at    timestamptz NOT NULL DEFAULT now(),
  ended_at      timestamptz,
  data          jsonb NOT NULL DEFAULT '{}'       -- full task input + final result summary
);
CREATE INDEX agent_runs_org_idx ON agent_runs (org_id, created_at DESC);
CREATE INDEX agent_runs_org_status_idx ON agent_runs (org_id, status);

-- Each tool call / decision inside a run. The fine-grained, immutable decision trail.
CREATE TABLE agent_steps (
  id            text PRIMARY KEY,                 -- step_<hex10>
  org_id        text NOT NULL,
  run_id        text NOT NULL REFERENCES agent_runs(id) ON DELETE CASCADE,
  seq           integer NOT NULL,                 -- ordinal within the run
  kind          text NOT NULL,                    -- plan|tool_call|tool_result|gate|approval|handover|final
  tool          text NOT NULL DEFAULT '',         -- the tool name for tool_call/result
  args          jsonb NOT NULL DEFAULT '{}',      -- resolved args (redacted of secrets)
  gate          text NOT NULL DEFAULT '',         -- '' | allowed | blocked:budget | blocked:scope |
                                                  --   blocked:dnd | parked:approval | blocked:killswitch
  reason        text NOT NULL DEFAULT '',         -- the WHY (model rationale or deterministic gate reason)
  result        jsonb NOT NULL DEFAULT '{}',
  idempotency_key text NOT NULL DEFAULT '',       -- '<run_id>:<seq>' or '<run_id>:<tool>:<resource>'
  spend_minor   bigint NOT NULL DEFAULT 0,
  at            timestamptz NOT NULL DEFAULT now(),
  data          jsonb NOT NULL DEFAULT '{}'
);
CREATE INDEX agent_steps_run_idx ON agent_steps (run_id, seq);
CREATE UNIQUE INDEX agent_steps_idem_uq ON agent_steps (idempotency_key) WHERE idempotency_key <> '';
-- The UNIQUE idempotency index is the DB-enforced no-double-execute guard (a duplicate tool exec is
-- rejected by the DB inside the same txn that records spend — not by a best-effort file scan).

-- Human approval gate records (one per parked risky/over-threshold step).
CREATE TABLE agent_approvals (
  id            text PRIMARY KEY,                 -- apr_<hex10>
  org_id        text NOT NULL,
  run_id        text NOT NULL,
  step_id       text NOT NULL DEFAULT '',
  scope         text NOT NULL,                    -- spend|bulk|destructive|export|dnd_override|price|refund
  amount_minor  bigint NOT NULL DEFAULT 0,        -- the spend this approval authorizes (exact; idempotent)
  state         text NOT NULL DEFAULT 'pending',  -- pending|approved|rejected|expired
  required_amr  text NOT NULL DEFAULT 'pin',      -- pin|otp (step-up factor needed)
  requested_at  timestamptz NOT NULL DEFAULT now(),
  decided_by    text NOT NULL DEFAULT '',
  decided_at    timestamptz,
  data          jsonb NOT NULL DEFAULT '{}'
);
CREATE INDEX agent_approvals_org_state_idx ON agent_approvals (org_id, state);

-- Per-(role, tenant) capability grant: which tool-scopes a role may use, and its caps.
-- Default-deny: a role gets ONLY the scopes listed here. Admin sets these per tenant; defaults seeded.
CREATE TABLE agent_tool_grants (
  org_id        text NOT NULL,
  role          text NOT NULL,
  scopes        jsonb NOT NULL DEFAULT '[]',      -- ["leads.read","leads.enqueue_calls","whatsapp.send",...]
  daily_spend_cap_minor   bigint NOT NULL DEFAULT 0,   -- 0 => no autonomous external spend (safest default)
  approval_threshold_minor bigint NOT NULL DEFAULT 0,  -- spend above this needs human approval (0 => all)
  max_actions_per_run     integer NOT NULL DEFAULT 25,
  max_bulk_targets        integer NOT NULL DEFAULT 50,  -- bulk msg/call fan-out cap before approval
  autonomy_level  text NOT NULL DEFAULT 'propose',      -- propose|approve_below_cap|autonomous_internal
  enabled       boolean NOT NULL DEFAULT true,
  updated_at    timestamptz NOT NULL DEFAULT now(),
  data          jsonb NOT NULL DEFAULT '{}',
  PRIMARY KEY (org_id, role)
);

-- OPTIONAL: admin-defined CUSTOM roles (Industry Packs / tenant-specific personas). Built-in roles
-- live in the code ROLE_REGISTRY; this table only holds tenant-authored ones. roles.resolve(role,tenant)
-- reads here first, then falls back to the code registry. Same shape as RoleSpec (§5).
CREATE TABLE agent_roles (
  org_id        text NOT NULL,
  role          text NOT NULL,                    -- the custom role name
  display       text NOT NULL DEFAULT '',
  system_prompt text NOT NULL DEFAULT '',
  default_scopes jsonb NOT NULL DEFAULT '[]',     -- subset of the global tool catalog (cannot widen it)
  model         text NOT NULL DEFAULT '',
  autonomy      text NOT NULL DEFAULT 'propose',
  context_packs jsonb NOT NULL DEFAULT '[]',
  handover_on   jsonb NOT NULL DEFAULT '[]',
  enabled       boolean NOT NULL DEFAULT true,
  created_at    timestamptz NOT NULL DEFAULT now(),
  data          jsonb NOT NULL DEFAULT '{}',
  PRIMARY KEY (org_id, role)
);
```

> **Why these are PG, not JSONL (the upgrade over `aimanager`):** the framework is the spine of the
> *money path* across roles and survives the Phase-2 two-instance + Hatchet-worker topology. The
> `agent_steps` UNIQUE idempotency index + the wallet's atomic decrement are the only sanctioned
> no-double-execute / no-double-spend guards (a JSONL `already_executed()` then `append()` is a
> read-then-write race across processes — the exact bug `aimanager` §7 and `orchestration-hatchet` §5
> call out). The immutable narrative also lands in `audit.py` (JSONL) + the `events` table.

---

## 5. RoleSpec & the ROLE REGISTRY — roles are DATA, not modules

The whole point: the 11 AI-workforce roles + the AI Manager + the Ops Manager are **rows of config**, not
eleven hand-written loops. `aiwf/roles.py`:

```python
@dataclass(frozen=True)
class RoleSpec:
    name: str                       # "telecaller","whatsapp","support","strategist","creative",
                                    #   "ad","crm","booking","billing","analytics","ops","manager"
    display: str                    # "AI Telecaller", "WhatsApp Salesperson", ...
    system_prompt: str              # role persona + operating rules (reads Business Brain at runtime)
    default_scopes: tuple[str, ...] # the tool-scopes this role may use (subset of the global catalog)
    model: str = ""                 # "" => provider default; per-role override (Groq for cheap, Claude for hard)
    autonomy: str = "propose"       # propose | approve_below_cap | autonomous_internal
    context_packs: tuple[str, ...] = ()   # which Business-Brain/KB packs to load (campaigns, pricing, faq...)
    handover_on: tuple[str, ...] = ()     # conditions that force human handover (e.g. "refund_request","legal")

ROLE_REGISTRY: dict[str, RoleSpec] = { ... }   # the 11 + ops + manager, seeded; admin can extend per tenant
```

**Effective capability = intersection of three layers (default-deny, narrowest wins):**
1. `RoleSpec.default_scopes` (what the role *type* is designed to do),
2. `agent_tool_grants` for `(org_id, role)` (what the *tenant admin* permits — this can only narrow or
   set caps, never widen beyond the catalog),
3. the resolved actor's RBAC via the existing `auth.can(tenant, action)` (a manager-triggered run can
   never exceed the human's own permissions).

`policy.resolve(role, tenant, actor) -> ResolvedPolicy{allowed_tools, caps, autonomy, threshold}` computes
this once per run. **The LLM is given only `allowed_tools`** — it cannot even *propose* a tool it lacks
scope for, and `guardrails.py` re-checks scope at execution (defense in depth; the model's self-asserted
fields are advisory only, per `aimanager` RED-TEAM fix #5).

Example role rows (abbreviated):

| Role | default_scopes (illustrative) | money? | typical autonomy | handover_on |
|---|---|---|---|---|
| `telecaller` | `leads.read`, `leads.enqueue_calls`, `calls.read`, `suppression.add` | no (metered credit) | autonomous_internal | `human_requested` |
| `whatsapp` | `leads.read`, `whatsapp.send`, `wa.thread.read`, `suppression.add` | no (metered) | approve_below_cap (bulk gated) | `opt_out`, `needs_human` |
| `support` | `tickets.read/write`, `kb.read`, `whatsapp.send`, `bookings.read` | no | autonomous_internal | `refund_request`, `legal`, `angry` |
| `strategist` | `analytics.read`, `campaigns.create/update`, `ads.read` | no (proposes; ad spend gated) | propose | — |
| `ad` | `ads.read`, `ads.pause`, `ads.set_budget`, `ads.create_campaign` | **yes** | propose (all spend approved) | — |
| `crm` | `leads.read/write`, `contacts.read/write`, `segments.write` | no | autonomous_internal | — |
| `booking` | `bookings.read/write`, `calendar.read`, `whatsapp.send` | no | autonomous_internal | `reschedule_conflict` |
| `billing` | `billing.read`, `wallet.read`, `invoices.create` | **yes (refund gated)** | propose | `refund_request` |
| `analytics` | `analytics.read`, `billing.read` | no | autonomous_internal (read-only) | — |
| `ops` (== `aimanager`) | the `aimanager` catalog (campaigns/leads/run/whatsapp/ads) | **yes** | propose | — |
| `manager` (AI Manager) | meta: may *delegate* to any role within the caller's RBAC | n/a (delegates) | per delegated role | risky → PIN |

> **Precise claim (not overstated):** the 11 built-in roles + `ops` + `manager` are entries in the code
> `ROLE_REGISTRY` (a `RoleSpec` per role) — they ship in the package; adding a *built-in* role is one
> registry entry + a default `agent_tool_grants` seed, and crucially **NO new runner/guardrail/loop code**
> (the spine is unchanged — that is the reuse win). What is genuinely *per-tenant data* is the
> `agent_tool_grants` row (scopes/caps/autonomy an admin tunes). **Admin-defined CUSTOM roles** (a tenant
> inventing its own role with a custom prompt/scope set, e.g. Industry Packs) need a per-tenant **`roles`
> table** — `(org_id, role, system_prompt, default_scopes jsonb, model, autonomy, …)` mirroring `RoleSpec`
> — which `roles.resolve(role, tenant)` reads, falling back to `ROLE_REGISTRY` for built-ins. So: built-in
> roles = code rows (no new code path beyond the entry); tenant-custom roles = a data row in `roles` +
> `agent_tool_grants`, still over the one unchanged `AgentRunner`. Either way, **no new loop is written.**

---

## 6. THE RUNNER — `AgentRunner.run(role, task, ctx)` (the spine loop)

The generalized `aimanager` loop. Same safety properties, now parameterized by `ResolvedPolicy`.

```
run(role_spec, task, ctx) -> AgentRunResult:
  policy = policy.resolve(role_spec, ctx.tenant, ctx.actor)        # default-deny capability set
  run = store.create_run(role, tenant, actor, trigger, objective)  # status=running; audit aiwf.run.start
  0. KILL-SWITCH: if guardrails.killed(tenant, role): finalize(killed); return
  1. CONTEXT: c = context.gather(role_spec, tenant, task)           # Business Brain + KB + run state
  2. LOOP (bounded by policy.max_steps):
       plan = llm.propose(c, policy.allowed_tools) if llm.is_configured()
              else StubPlanner().propose(c, policy.allowed_tools)   # offline path
       plan = validate(plan)                                        # pydantic/JSON-schema; reject malformed
       store.add_step(run, kind="plan", reason=plan.rationale); audit('aiwf.plan')
       for action in plan.actions:
         # ---- DETERMINISTIC GATES (never delegated to the LLM) ----
         g = guardrails.check(policy, action, run)                  # scope? budget? bulk? dnd/window? threshold?
         store.add_step(run, kind="gate", tool=action.tool, gate=g.verdict, reason=g.reason)
         if g.verdict == "blocked": audit('aiwf.gate_block'); continue          # cannot run; record + skip
         if g.verdict == "parked":                                              # needs human approval
              store.create_approval(run, action, scope=g.scope, amount=g.amount)
              set run.status="awaiting_approval"; handover.notify_approver(...); return PARKED
         if g.verdict == "handover":                                            # role/handover_on tripped
              handover.escalate(run, action, ai_summary=summarize(run))
              set run.status="handover"; return HANDOVER
         # ---- BUDGET RESERVE (money actions reserve against the wallet BEFORE acting) ----
         hold = wallet.reserve(tenant, action.est_spend_minor, resource_type=action.tool,
                               resource_id=action.id, idem_key=f"aiwf:{run.id}:{action.id}") if action.money else None
         if action.money and hold is None: audit('aiwf.gate_block:no_funds'); continue
         # ---- EXECUTE (idempotent; DB-unique on idempotency_key) ----
         try:
           result = registry[action.tool].fn(action.args, ctx)     # dormant adapters no-op if unconfigured
           store.add_step(run, kind="tool_result", tool=action.tool, idempotency_key=f"{run.id}:{action.id}",
                          result=result, spend=result.actual_spend_minor)        # UNIQUE => exactly-once
           if hold: wallet.settle(hold, result.actual_spend_minor, idem_key=f"settle:aiwf:{run.id}:{action.id}")
           audit('aiwf.execute', object_id=action.id, meta=redact(result))
         except DuplicateStep: pass                                 # DB rejected a re-run => already done
         except Exception as e:
           if hold: wallet.release(hold, idem_key=f"release:aiwf:{run.id}:{action.id}")
           if action.money: break                                   # fail-safe: halt remaining money actions
       if plan.done: break
  3. finalize(run, status="done"); audit('aiwf.run.end')
  4. return AgentRunResult{run_id, status, steps, spend_authorized, spend_actual, parked, handover}
```

**Safety properties baked in (identical guarantees to `aimanager`, now role-generalized):** read-only
context first; deterministic gates run *before* any side effect; money actions reserve against the
ACID wallet and cannot exceed caps the LLM can't override; over-threshold actions park for human approval;
every tool exec is idempotent by `(run_id, action_id)` enforced by the DB UNIQUE index; a failed money
action halts the rest (fail-safe); the kill-switch short-circuits and is re-checked inside each money
gate. Multi-step / long-running roles wrap this loop in a Hatchet `durable_task` so it survives restarts.

---

## 7. GUARDRAILS — the safety surface (deterministic Python, never the LLM)

`aiwf/guardrails.py` composes the foundation's firewalls into one `check(policy, action, run) -> Gate`.
Each gate is pure code; the model's `requires_approval`/`est_*` are **advisory only** and recomputed from
the resolved tool+args (per `aimanager` RED-TEAM fix #5 — a plan that under-reports its spend cannot slip).

| Gate | Mechanism (reuses) | Verdict |
|---|---|---|
| **Scope** | `action.tool`'s declared `scopes ⊆ policy.allowed_tools`; else **blocked:scope**. Default-deny. | blocked |
| **Budget** | for `money:true`: recompute external spend from args; check `daily_spend_cap` window via `wallet.balance`/spend ledger; the `wallet.reserve` atomic conditional-UPDATE is the real no-oversell gate (`credit-ledger-firewall.md` INV-1). Over remaining cap → **blocked:budget**. | blocked / allowed |
| **Approval threshold** | external spend `> approval_threshold_minor` (default 0 = approve ALL spend) → **parked:approval** (strict-greater; `THRESHOLD=0` parks any spend > 0 — `aimanager` RED-TEAM fix #6). | parked |
| **Bulk / rate** | fan-out targets (`leads.enqueue_calls.max`, `whatsapp.send` recipient count) `> max_bulk_targets` → **parked:approval** (`scope=bulk`). Per-run action count `> max_actions_per_run` → **blocked**. | parked / blocked |
| **DND / consent / window** | call/WhatsApp targets checked against the existing suppression set + the campaign calling-window (`caller.py` `_in_window`/`_suppressed_set`); a target in suppression or out-of-window → **blocked:dnd** unless an explicit `dnd_override` approval exists. | blocked |
| **Destructive / export / price / refund** | tools tagged `scope ∈ {destructive,export,price,refund}` → **parked:approval** with `required_amr=pin` (step-up via `firewall.require_step_up`). | parked |
| **Kill-switch** | `agent_tool_grants.enabled=false` for the role, or global `AIWF_KILLSWITCH=1`, or per-tenant kill → **blocked:killswitch** at loop top AND re-checked inside each money gate (race guard, `aimanager` RED-TEAM fix #7). | blocked |
| **Handover** | role `handover_on` condition matched (e.g. support sees `refund_request`/`legal`/`angry`) → **handover**. | handover |

**The platform-level SAFETY mandate, satisfied point-by-point:** RBAC/least-privilege = `policy.resolve`
default-deny + `auth.can`; PIN/OTP for risky AI-Manager/workflow actions = `firewall.require_step_up`
(scope-bound, `sub`-bound per `credit-ledger-firewall.md` SECURITY F3); approval + budget gates = the
`parked` verdict + the wallet reserve; immutable audit of every AI decision (with reason) = `agent_steps`
+ `audit.record` (every gate writes its `reason`); DND/consent/window = the DND gate; secrets mgmt =
dormant-until-creds + `redact()`; least-privilege per role = `default_scopes ∩ grants ∩ rbac`.

---

## 8. HUMAN HANDOVER (exception-only, with AI summary) — `aiwf/handover.py`

When a gate returns `handover` (role condition) or a parked approval is escalated, the run does NOT
silently stall:
1. `run.status = "handover"`; the step records why.
2. `summarize(run)` produces a concise **AI summary** (what the agent was doing, what it found, the
   recommended next action, the exact blocked/parked action) — generated by the LLM driver, or a
   deterministic template under `none`.
3. The summary + run link are routed to the **Omnichannel Inbox** (a `handover` item) and a
   **PushNotification**/registered webhook fires to the assigned human (manager/admin per RBAC).
4. A human resolves via `POST /aiwf/runs/{id}/approve|reject|takeover`. `approve` (with step-up where the
   scope requires PIN) authorizes *exactly* the parked amount (idempotent — re-running cannot escalate)
   and resumes the run from the parked step (a fresh `agent_runs` continuation row with
   `trigger=handover_return`, preserving the immutable original). `takeover` marks the run human-owned and
   closes it; subsequent actions are human, logged under the human actor.

This is the "exception-only, with AI summary" requirement: agents act autonomously within their grant and
escalate *only* on a gate trip or a `handover_on` condition, handing a human a one-glance summary rather
than a raw transcript.

---

## 9. THE AI MANAGER (voice-first command center) — `aiwf/manager/`

The AI Manager is **the `manager` role + an intent front-end**, not a separate engine. It reuses the
entire runner/guardrail/audit spine; its only additions are NL→intent parsing, voice-command session
handling, and delegation.

- **Registration:** a vendor registers phone number(s) (`POST /aiwf/manager/numbers`, admin, audited);
  an inbound call from a registered, tenant-bound number opens a **command session** (the existing
  LiveKit voice plane handles the audio; the AI Manager is the *brain* the session talks to).
- **Intent (`intent.py`):** the spoken command ("call all hot leads", "launch a campaign for my 2BHK",
  "increase budget on the best ad", "today's revenue report") is parsed by the LLM driver into a
  structured `Intent{verb, role, args, risk_class}`. `risk_class ∈ {read, internal_action, risky}`
  (risky = spend/bulk/launch/pause-ads/mass-call/price/refund/export/delete).
- **Permission + risk verification:** the AI Manager **verifies intent + permission** (`auth.can` for the
  caller's identity) and, for `risk_class=risky`, **requires a preset 4-digit PIN/OTP** before delegating
  — `firewall.mint_step_up`/`require_step_up` over the voice channel (DTMF PIN or spoken OTP), the SAME
  step-up token the dashboard uses. No PIN → the command is parked as an approval the vendor can confirm
  in-app.
- **Delegation (`delegate.py`):** a verified intent is routed to the right `RoleSpec` and an
  `AgentRunner.run(...)` is launched (a Hatchet run for anything long), `trigger=manager_voice`,
  `trigger_ref=command_id`. The AI Manager speaks back the result/plan summary; every command + delegation
  + PIN event is an `agent_steps`/`audit` row.
- **Net:** "controls every module, reduces dashboard dependency" = the manager role can delegate to any of
  the 11 roles, each of which already maps to the API/tool catalog — so a voice command reaches any module
  the caller is permitted to touch, under the same gates.

---

## 10. WORKFLOW STUDIO BINDING — `aiwf/workflow/node.py`

The Workflow Automation Studio's node types map onto this spine so a visual workflow and a role-agent
share one safety model:

| Studio node | Backed by |
|---|---|
| **AI-Agent node** | `AgentRunner.run(role_spec_from_node, task=node.input, ctx)` — pick a role + objective; the node's output is the run result. Multi-agent workflows = several AI-Agent nodes wired in the graph (Hatchet orchestrates). |
| **BUDGET node** | sets/decrements a per-workflow `daily_spend_cap` enforced by the SAME `guardrails` budget gate + `wallet.reserve`. A workflow cannot out-spend its budget node. |
| **APPROVAL node** | a `parked:approval` checkpoint — the workflow pauses (Hatchet `aio_wait_for_event`) until `POST /aiwf/runs/{id}/approve` (PIN where required). |
| **Trigger / Condition / Action / Delay / Data / Integration / Error** | existing Hatchet workflow primitives (`orchestration-hatchet.md`); the AI-Agent/BUDGET/APPROVAL nodes are the new ones this spec adds. |

**Hard safety rules (no bulk/spend/refund/DND-violation/out-of-hours/data-export without
approval+budget-node+audit)** are enforced *by the same `guardrails.check`* whether the action originates
from a role agent, the AI Manager, or a workflow node — there is exactly one gate, so a workflow can never
be a side-door around the firewall. Versioning/permissions/per-workflow analytics ride on the existing
workflow + `events` infrastructure.

---

## 11. OFFLINE ACCEPTANCE TEST (`tests/test_offline.py`) — ZERO keys, ZERO network

Run: `python -m pytest droplet_work/aiwf/tests/test_offline.py -q`
Must pass with **no env keys set and no network access** (mirrors `aimanager` §9, broadened to the
framework). Uses `StubTools` + `StubPlanner` + the **`InMemoryStoreBackend`** (§3.1 #4 — same interface as
`PgStoreBackend`, no Postgres/network dependency). Asserts:

1. **Import-safe & dormant:** `import aiwf`; `llm.driver.status()=="not_configured"`; no exception; all
   adapters report `not_configured`.
2. **Role registry + policy default-deny:** every role in `ROLE_REGISTRY` resolves a policy; a tool whose
   scope is NOT in the role's grant is **absent** from `policy.allowed_tools` AND is **blocked:scope** if
   forced into a plan.
3. **Stub run end-to-end:** `run("crm", task, ctx)` with provider unset produces a valid plan, runs gates,
   executes against `StubTools`, and writes `agent_runs` + `agent_steps` + audit rows in order
   (`aiwf.run.start → aiwf.plan → aiwf.gate → aiwf.execute → aiwf.run.end`).
4. **Budget gate blocks over-cap:** a money action exceeding `daily_spend_cap_minor` is **blocked:budget**
   *before* any execute, with an audit row; the cap was enforced by code, not the model. The model's
   under-reported `est_spend` is ignored (recomputed from args).
5. **Approval gate parks money:** an external-spend action `> approval_threshold` (default 0) is **parked**
   (`run.status==awaiting_approval`, nothing executed); after `approve_run(run_id, user)` a resume executes
   it; audit shows plan → approval → execute. Boundary test: `threshold=0` parks spend of even 1 paise.
6. **DND/window blocks:** a `leads.enqueue_calls`/`whatsapp.send` to a suppressed number → **blocked:dnd**,
   no execute, audit row; an explicit `dnd_override` approval flips it to allowed.
7. **Bulk gate parks fan-out:** a bulk action above `max_bulk_targets` → **parked:approval** (`scope=bulk`).
8. **Handover:** a `support` run hitting a `refund_request` condition → `run.status==handover`, an AI
   summary is produced, no autonomous refund happens; audit shows `aiwf.handover`.
9. **Kill-switch halts:** with the role's grant `enabled=false` (or `AIWF_KILLSWITCH=1`), `run(...)`
   returns `status=="killed"` and zero adapter calls / zero exec steps.
10. **Idempotency (DB-enforced):** replaying the same run's same action twice yields exactly ONE
    `tool_result` step (the UNIQUE `idempotency_key` index rejects the duplicate) — no double-execute,
    no double-spend.
11. **Step-up identity binding:** an approval token minted for tenant A cannot approve tenant B's run
    (`sub`-bound check — `credit-ledger-firewall.md` SECURITY F3); mismatch → rejected.
12. **AI Manager intent → delegation (offline):** a canned command string parses (stub intent) to an
    `Intent`, risk-classifies, and (for a `risky` intent without a step-up) PARKS rather than executes.

A second tiny self-test (`selftest_bad_plan`) feeds the validator a malformed/over-scoped plan and asserts
rejection — proving the schema + scope gate work without an LLM (mirrors the repo's
`eval/selftest_bad_model.py` convention).

---

## 12. HOW IT SITS ON THE SETTLED FOUNDATION (REUSE vs ADD)

| Concern | REUSES (existing / other specs) | ADDS (this spec) |
|---|---|---|
| Agent loop | `aimanager` loop shape, `ToolSpec`, StubPlanner | `AgentRunner` (role-parameterized), `RoleSpec` + registry, `policy.resolve` |
| Persistence | `db/engine.py` `session()`/RLS/GUC, `store.py` MODE router, Alembic | 4 tables: `agent_runs`, `agent_steps`, `agent_approvals`, `agent_tool_grants` |
| Money / budget | `wallet.py` `reserve/settle/release/balance` (ACID, no-oversell) | the BUDGET gate + per-role/per-workflow caps wired to it |
| Risky-action gate | `firewall.py` `mint_step_up/require_step_up` (PIN/OTP, `sub`-bound) | the APPROVAL/PIN node + voice-channel step-up |
| Audit | `audit.py` JSONL + `events` table (dual-mirrored) | `aiwf.*` action names; every gate writes its `reason` |
| Transport (the hands) | `caller.py` `/api` 60+ routes; `auth.issue_pair`/`can` | localhost-loopback tool client + tool catalog; `AIWF_SERVICE_TOKEN` (dormant) |
| Orchestration | Hatchet durable tasks, idempotency keys, concurrency | role runs wrapped as durable tasks; multi-agent workflows |
| Reasoning LLM | `whatsapp.py` dormancy pattern; `vendors/groq_meter.py`; claude-api skill | one shared `llm/driver.py` (claude/groq/none) |
| Context | `dynamic-context-rag.md` Business Brain / KB corpus (precomputed) | `context.gather(role, …)` role-scoped context assembly |
| Quality gate | `eval-harness.md` offline replay/judge | a role's prompt/tool change must pass the eval before live |
| Exposure | the deferred-diff pattern (`aimanager` `caller_wiring.diff`) | `endpoints.py` + `caller_wiring.diff` (un-applied) |

**Nothing in `caller.py`/`agent.py` business logic is edited.** The only spine touch is the un-applied
`caller_wiring.diff` that `app.include_router(aiwf_router)` and initializes the service token — applied
by the orchestrator when "final wiring" is un-deferred, exactly as `aimanager` specified.

---

## 13. ENDPOINTS (additive `APIRouter`, mounted via deferred diff)

| Method · Path | Purpose | Auth |
|---|---|---|
| `POST /aiwf/runs` | start an agent run `{role, objective, args}` | manager+ (role within caller RBAC) |
| `GET /aiwf/runs` | list runs (`?status=awaiting_approval&role=`) | manager+ |
| `GET /aiwf/runs/{id}` | run detail + steps + approvals + spend | manager+ |
| `POST /aiwf/runs/{id}/approve` | human approval (step-up PIN where scope requires) | manager/admin |
| `POST /aiwf/runs/{id}/reject` | human rejection | manager/admin |
| `POST /aiwf/runs/{id}/takeover` | human takeover (handover resolution) | manager/admin |
| `GET /aiwf/roles` | list roles + this tenant's grants | manager+ |
| `POST /aiwf/grants/{role}` | set a role's scopes/caps/autonomy for the tenant | admin |
| `POST /aiwf/killswitch` | halt all (or one role's) autonomous action | admin |
| `GET /aiwf/status` | config/dormancy + provider + per-role caps + remaining spend | manager+ |
| `POST /aiwf/manager/numbers` | register AI-Manager command phone number(s) | admin |
| `POST /aiwf/manager/command` | submit an NL command (text or transcribed voice) → intent → delegate | manager+ (PIN for risky) |
| `GET /aiwf/audit` | aiwf-scoped audit (proxy to `audit.tail(action_prefix="aiwf")` + `events`) | manager+ |

The router mounts behind the existing auth dependency (so approval is restricted to manager/admin), uses
the same `can()` RBAC, and is tenant-scoped via the same GUC session — no new auth concept.

---

## 14. DEPENDENCIES (what's needed to build vs to activate)

**To build + pass the offline test:** nothing new. Pure Python over `pydantic` (already present) + the
`InMemoryStoreBackend` (§3.1 #4) — the offline test needs no Postgres, no keys, no network. (The
production `PgStoreBackend` uses the existing `db/engine.py`; its real RLS/UNIQUE semantics are proven in
build-unit 1's separate PG-integration test, §15 — not in the offline suite.)

**To activate (dormant-until-creds — server-side only, never frontend, never git):**
- **LLM reasoning (pick one, or run on the stub):** `ANTHROPIC_API_KEY` (set `AIWF_LLM_PROVIDER=claude`)
  or `GROQ_API_KEY`/`GROQ_API_KEY_1..N` (`AIWF_LLM_PROVIDER=groq`).
- **Service identity (for the live tool registry):** `AIWF_SERVICE_TOKEN` is the bootstrap service
  identity used to **mint per-run, per-tenant tokens** — the runner calls `auth.issue_pair(tenant_of_run)`
  so each loopback tool call is scoped to that run's `org_id` under RLS (see §3.1; a single admin token
  would mis-scope writes — verified against `caller.py:371` / `auth.py:103`). Injected into the box env,
  server-side only. Until set, the live tool registry returns `not_configured` and the runner uses
  `StubTools` (preserves dormancy).
- **Postgres provisioned** (P1 U1: db `famit` + restricted role `famit_app` + `PG_DSN`/`PG_DSN_ASYNC`) —
  the only hard infra prerequisite for the *live* path (the framework tables need it). If PG is
  unavailable at runtime, the firewall/budget gates **fail CLOSED** (treat remaining spend as 0 → park
  for approval), never fail-open on money.
- **Wallet + Firewall** (`credit-ledger-firewall.md`) provisioned for any role that spends or does risky
  actions. **Ad adapters** (`aimanager` §10: Google Ads / Meta creds) only to make the `ad`/`ops` roles
  actually spend externally — dormant no-ops until pasted.
- **Guardrail config (optional; safe defaults shipped):** `AIWF_LLM_PROVIDER`, `AIWF_KILLSWITCH=0`, and
  per-role grants seeded with `daily_spend_cap_minor=0` (no autonomous external spend),
  `approval_threshold_minor=0` (all external spend human-approved) until an admin deliberately grants
  autonomy.

---

## 15. BUILD ORDER (each a verifiable unit; ships safety-spine first)

1. `config.py` + `store.py` (4 tables, Alembic `000N`, RLS) + `audit_bridge.py` → unit-test schema + RLS isolation.
2. `roles.py` (RoleSpec + registry) + `policy.py` (default-deny resolver) → unit-test intersection/least-privilege.
3. `guardrails.py` (scope/budget/approval/bulk/DND/killswitch/handover) wired to wallet+firewall stubs → unit-test each verdict.
4. `tools/` registry + `stub_tools.py` + `planner_stub.py` → unit-test stub plan validates + scope-gated.
5. `runner.py` (`AgentRunner.run`) on stubs → **offline acceptance test (§11) GREEN.** (Ships the entire safety spine, fully tested, no external dep.)
6. `handover.py` + `tools/transport.py` (loopback) + `catalog.py` (real tools) → dormant until `AIWF_SERVICE_TOKEN`.
7. `llm/driver.py` (none → claude → groq) → status() test (dormant).
8. `manager/` (intent → delegate, voice step-up) → offline intent/risk test.
9. `workflow/node.py` (AI-Agent/BUDGET/APPROVAL nodes) → Hatchet integration test.
10. `endpoints.py` + `caller_wiring.diff` (un-applied) → router import test only.

Ship 1–5 first: the entire framework + every guardrail, offline-tested, with zero external dependency.
6–10 light up real tools, reasoning, voice, and workflows once the founder pastes keys/token and the
orchestrator applies the wiring diff.

---

## 16. HONEST REAL-VS-HYPE

| Claim | Reality |
|---|---|
| "An autonomous AI workforce replacing teams" | It is *augmentation under hard gates*. Read-only + internal-metered actions can run autonomously per the role's grant; **every** external-spend / bulk / destructive / export / price / refund / DND action is deterministically gated (budget + approval/PIN) and immutably audited. Defaults ship with **zero autonomous external spend** until an admin grants it. |
| "One framework powers all 11 roles + AI Manager + Workflow nodes" | True structurally — roles are config rows over one `AgentRunner`; the AI Manager is the `manager` role + intent front-end; workflow AI-nodes call the same runner. The *reasoning quality* per role obviously depends on the LLM key + prompt; the *safety machinery* does not. |
| "The LLM decides budgets / who to call" | The LLM *proposes*; deterministic `guardrails.py` + the ACID wallet decide what's allowed. Caps, thresholds, scope, DND, and kill-switch are pure code the model cannot override. |
| "Works offline" | The orchestration, all gates, audit, idempotency, handover, and intent-risk classification work fully offline on the stub. Reasoning needs a key; safety doesn't. |
| "Touches nothing in the live voice spine" | Correct — additive package + un-applied `caller_wiring.diff`; `caller.py`/`agent.py` business logic unchanged; dormant until creds. |
| "Multi-agent / multi-step is solid" | Durability comes from Hatchet (settled plane), not an unproven in-house graph engine; idempotency is DB-enforced, not best-effort. |

---

## 17. WHAT THIS UNBLOCKS (modules powered by this spine)

Directly enables the AI-worker behavior in: **AI Manager** (voice command center), **Workflow Builder**
(AI-Agent/BUDGET/APPROVAL nodes), **AI Voice Calls** (telecaller role over the existing voice plane),
**WhatsApp Automation** (whatsapp role), **Customer Support** (support role + handover), **Campaigns** /
**Ad Automation** (strategist + ad roles, spend-gated), **CRM** / **Leads** / **Contacts** (crm role),
**Booking/Appointments** (booking role), **Billing/Collections** (billing role, refund-gated),
**Analytics/Reports** (analytics role, read-only), **Creative Studio** (creative role), **Sales Pipeline**,
**Lifecycle Trigger Engine**, **Human Handover**, **AI Task Manager**, **AI Quality Review** (eval gate per
role), and **Compliance/DND/Consent** (the DND gate is enforced here, not per-feature). It is the literal
spine of the "AI revenue workforce" — every module that says "AI does X" calls `AgentRunner.run(role, …)`.

---

## Sources
- In-repo design specs (verified 2026-06-09): `design/automation-aimanager.md` (the prototype loop +
  dormant LLM driver + Google/Meta adapter posture), `design/credit-ledger-firewall.md` (wallet ACID +
  firewall PIN/step-up + the F1/F2/F3 fixes folded here), `design/p1-postgres.md` (RLS/GUC, store MODE
  router, schema conventions), `design/orchestration-hatchet.md` (durable tasks + idempotency),
  `design/dynamic-context-rag.md` (Business Brain/KB context), `design/eval-harness.md` (role-change gate).
- In-repo live source: `droplet_work/whatsapp.py` (dormant-until-creds), `droplet_work/audit.py`
  (immutable ledger), `droplet_work/auth.py` (`issue_pair`, `can`, HS256/`var/secret`),
  `droplet_work/vendors/__init__.py` (adapter conventions).
- Anthropic — [Building effective agents](https://www.anthropic.com/engineering/building-effective-agents),
  [Writing tools for agents / code execution with MCP](https://www.anthropic.com/engineering/code-execution-with-mcp);
  in-repo `claude-api` skill (model `claude-opus-4-8`, adaptive thinking, manual tool-use loop, no
  `budget_tokens`/`temperature` on Opus 4.8).
- [Firecrawl — Best open-source agent frameworks 2026](https://www.firecrawl.dev/blog/best-open-source-agent-frameworks),
  [JetBrains/PyCharm — Top agentic frameworks 2026](https://blog.jetbrains.com/pycharm/2026/06/top-agentic-frameworks-for-building-applications-2026/),
  [Pydantic AI — production guide 2026](https://www.youngju.dev/blog/ai-platform/2026-04-12-pydanticai-practical-guide.en),
  [Hatchet docs — durable execution](https://docs.hatchet.run).
```
