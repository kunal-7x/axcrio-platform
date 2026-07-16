# `aimanager` — Autonomous AI Ops-Manager Meta-Agent — Execution-Ready Design Spec

**Status:** READY-TO-BUILD design. No code shipped yet. Verified against live source on disk
2026-06-09. All new code lives under `droplet_work/automation/aimanager/` only.
**Hard rule honored:** does NOT touch `caller.py` / `agent.py` (the backend spine). All wiring
into the spine is delivered as a *written, un-applied diff* (`caller_wiring.diff`) for the
orchestrator to apply later when "final wiring" is un-deferred.
**Dormancy invariant:** every external integration (LLM driver + each ad platform) is
provider-agnostic and DORMANT-UNTIL-CREDS — import-safe, never raises, and returns
`{"status": "not_configured"}` until keys are pasted, exactly like the existing `whatsapp.py`
module (the canonical pattern in this repo).

---

## 0. WHAT THIS IS (one paragraph, honest)

`aimanager` is an autonomous **operations manager** for the Famit revenue funnel: a meta-agent
that decides *which campaigns to run, which leads to call/message, and how much ad budget to
spend where* — then executes those decisions by calling the existing Famit API surface
(`/campaigns`, `/run`, `/leads`, `/billing`, `/whatsapp/send`, …) and, optionally, third-party
ad platforms (Google Ads, Meta). It runs a **plan → approve → execute** loop with **hard spend
caps, a mandatory human approval gate above a money threshold, a global kill-switch, and an
immutable audit trail**. The LLM that does the reasoning is pluggable and dormant until a key is
provided. **Real-vs-hype (stated up front):** this does NOT "replace the ad team" autonomously.
It is *augmentation with approval gates* — the agent proposes a funded plan; a human approves
anything that spends real money above the threshold; everything is logged and reversible where
the underlying platform allows it. Below the threshold (internal call/WhatsApp actions, which
draw on the already-metered credit ledger) it can act autonomously.

---

## 1. GROUND TRUTH — what already exists on disk (cite before trusting memory)

Verified 2026-06-09 against `C:\Users\kunal\Desktop\caps\droplet_work\`.

| Asset | Path | What aimanager reuses |
|---|---|---|
| Dormant-until-creds template | `whatsapp.py` | EXACT pattern: `_cfg()` reads env, `is_configured()`, no-op returns `{"status":"not_configured"}`, never raises, sync + async variants, `redact()`-style secret hygiene. **Copy this shape for the LLM driver and every ad adapter.** |
| Vendor adapter conventions | `vendors/__init__.py`, `vendors/vobiz.py`, `vendors/_http.py` | `DISPLAY_NAMES` map, `redact(secret)` (first/last 4 only), `status() -> configured|not_configured|error`, short timeout + backoff on 429/5xx, import-safe. |
| Immutable audit log | `audit.py` | `audit.record(actor, action, object_type, object_id, ..., meta)` — append-only JSONL, never raises, `tail()` for reads. **aimanager writes here with new action names; does NOT reinvent.** |
| API surface (the agent's hands) | `caller.py` routes (`@app.get/post/...`) | 60+ endpoints incl. `/campaigns`, `/campaigns/{cid}`, `/leads`, `/leads/hot`, `/run`, `/status`, `/calls`, `/stats`, `/analytics`, `/billing`, `/billing/ledger`, `/billing/overview`, `/usage`, `/suppression`, `/whatsapp/send`, `/audit`, `/webhooks`. Each becomes a *tool* (§5). |
| DB models | `db/models.py` | `Campaign`, `Lead`, `Call`, `Billing`, `Ledger`, `UsageEvent`, `CostLedger`, `Event`. aimanager READS these via the API/tools; adds NO columns to the spine. |
| Spend/credit firewall design | `design/credit-ledger-firewall.md` | aimanager's spend guardrail composes with this — internal actions debit the existing credit ledger; ad spend is a *separate, external-money* cap (§7). |
| Orchestration design | `design/orchestration-hatchet.md` | aimanager's loop can later be driven as a Hatchet/cron task; for now it ships with a self-contained tick runner + a deferred cron hook. |

**Net:** aimanager is a thin new module that *orchestrates existing primitives*. It introduces
no new datastore in the spine, no new spine endpoints (its own endpoints are additive and
mounted via the deferred diff), and one new env-gated LLM dependency.

---

## 2. CHOSEN TOOLS & WHY (web-researched, 2026-active, cited)

### 2.1 Agent framework: **thin hand-rolled tool-use loop** (NOT CrewAI / LangGraph)

The Famit backend is deliberately lean and hand-rolled (no LangChain, no agent framework
anywhere in `droplet_work/`). Dropping a heavy, opinionated multi-agent framework in would be a
foreign body: extra dependency surface, hidden control flow, and a fight with our hard
requirements (approval gates, immutable audit, deterministic offline test). 2026 guidance
agrees that frameworks earn their keep only when you need their durability/graph features —
otherwise a thin loop is preferred for transparency and control.

- **Decision:** implement the agent loop ourselves (≈150 lines) — a *manual* tool-use loop with
  an explicit approval interrupt. This is the pattern the Anthropic SDK documents for
  "human-in-the-loop approval before each tool execution," and it's the only pattern that lets
  us gate side-effecting tools.
- **Optional structured-output layer:** **Pydantic AI** is the one library we may pull in, used
  *only* to validate the LLM's emitted plan/tool-args against a schema (it ships a lightweight
  built-in agent loop with decorator-based tool registration and type-safe inputs). It is NOT
  required for the offline path. If we'd rather avoid the dependency, plain `pydantic` (already
  transitively present via SQLAlchemy/FastAPI stack) + manual JSON-schema validation suffices.
- **Rejected:** CrewAI (role-play multi-agent; wrong shape — we have one decision-maker, not a
  crew), LangGraph (durable graphs; overkill, heavy), smolagents (code-writing agent; we want
  structured tool calls, not arbitrary code-gen for a money-spending agent).

Sources: [Firecrawl — best open-source agent frameworks 2026](https://www.firecrawl.dev/blog/best-open-source-agent-frameworks),
[JetBrains/PyCharm — top agentic frameworks 2026](https://blog.jetbrains.com/pycharm/2026/06/top-agentic-frameworks-for-building-applications-2026/),
[Pydantic AI — production guide 2026](https://www.youngju.dev/blog/ai-platform/2026-04-12-pydanticai-practical-guide.en),
[ZenML — Pydantic AI vs CrewAI](https://www.zenml.io/blog/pydantic-ai-vs-crewai).

### 2.2 LLM driver: **provider-agnostic, dormant-until-creds** (default Claude or Groq)

The reasoning LLM is swappable behind one interface (`llm/driver.py`), exactly mirroring how
`whatsapp.py` abstracts the WhatsApp BSP. Two first-class providers are documented; both
dormant until their key is present:

- **`claude`** (recommended for the *autonomous funnel manager* role — highest reasoning):
  Anthropic SDK, model `claude-opus-4-8`, **adaptive thinking** (`thinking={"type":"adaptive"}`),
  `output_config={"effort":"high"}`. **Do NOT** send `budget_tokens`, `temperature`, `top_p`,
  `top_k` — these 400 on Opus 4.8. Use the **manual agentic loop** (not the SDK tool-runner) so
  we can interrupt for the approval gate; structured plans via `output_config={"format":{...}}`.
  Tool descriptions must be *prescriptive about when to call* (Opus 4.8 under-reaches for tools
  by default). Key: `ANTHROPIC_API_KEY`.
- **`groq`** (cheapest, already integrated in this repo via `vendors/groq_meter.py` + key
  round-robin from the fortress work): OpenAI-compatible chat-completions with tool calls. Key:
  `GROQ_API_KEY` (round-robin `GROQ_API_KEY_1..N` already supported elsewhere).
- **`none`** (default when no key set): the driver is a no-op that returns
  `{"status":"not_configured"}`; the **StubPlanner** (§8) is used instead so the whole loop,
  gates, and audit remain exercisable offline.

Selection: `AIMANAGER_LLM_PROVIDER = claude | groq | none` (default `none`). The driver exposes a
single method `propose(context, tools) -> Plan` and never leaks provider specifics upward.

### 2.3 Ad-platform adapters: **provider-agnostic, dormant, one file each**

`ads/google_ads.py`, `ads/meta_ads.py` (LinkedIn stubbed as `ads/linkedin_ads.py`, design-only).
Each mirrors `whatsapp.py`: `is_configured()`, no-op `{"status":"not_configured"}` when blank,
short timeout, redacted logs, never raises. They expose a tiny, intentionally **narrow** verb
set (`create_campaign`, `set_budget`, `pause_campaign`, `get_spend`) — narrow on purpose so the
harness can gate/audit each money action (per Anthropic agent-design guidance: promote
hard-to-reverse actions to dedicated, typed tools rather than a generic bash/HTTP escape hatch).

### 2.4 Scheduling: reuse, don't reinvent

The tick loop is a plain function `run_tick()` callable from (a) the new `POST /aimanager/tick`
endpoint, (b) a cron/Hatchet task per `design/orchestration-hatchet.md`, or (c) the offline
test harness. No new scheduler is introduced.

---

## 3. ARCHITECTURE & DIRECTORY LAYOUT (all new; nothing else edited)

```
droplet_work/automation/aimanager/
├── __init__.py            # package marker; exports run_tick, status
├── config.py             # env reads: thresholds, caps, provider selection, kill-switch
├── orchestrator.py       # the plan→approve→execute loop (run_tick); the brain wiring
├── planner_stub.py       # DETERMINISTIC StubPlanner — no LLM, no network (offline test path)
├── store.py              # aimanager's OWN append-only JSONL state (plans, approvals, decisions)
├── guardrails.py         # spend caps, approval-threshold check, idempotency, kill-switch
├── audit_bridge.py       # thin wrapper over droplet_work/audit.py (new action names)
├── tools/
│   ├── __init__.py       # ToolRegistry: name -> ToolSpec(schema, fn, side_effecting, money)
│   ├── api_tools.py      # in-process adapters that call the Famit API operations (campaigns, leads, run, billing, whatsapp)
│   └── ad_tools.py       # adapters that call the ad-platform modules below
├── llm/
│   ├── __init__.py
│   └── driver.py         # provider-agnostic LLM: claude | groq | none (dormant)
├── ads/
│   ├── __init__.py       # DISPLAY_NAMES, redact(), status() — mirrors vendors/__init__.py
│   ├── google_ads.py     # dormant-until-creds Google Ads adapter
│   ├── meta_ads.py       # dormant-until-creds Meta Marketing adapter
│   └── linkedin_ads.py   # design-only stub (returns not_configured)
├── endpoints.py          # FastAPI APIRouter (additive) — mounted via the DEFERRED diff
├── caller_wiring.diff    # the un-applied 6-line diff that mounts endpoints.py into caller.py
└── tests/
    └── test_offline.py   # the offline acceptance test (§9) — runs with ZERO keys, ZERO network
```

### 3.1 The four tensions, resolved explicitly

1. **"Tool-calling over the API" vs "do not edit caller.py".**
   Resolved by a **tool-registry abstraction**: each tool is a Python function in
   `tools/api_tools.py` that performs the *same operation* a route performs, behind a stubbable
   `ToolSpec.fn` interface. **The transport behind that interface is the one open design point,
   and it depends on a code-shape fact verified on disk 2026-06-09:** `campaign.py` exposes **no
   top-level callable functions** (its business logic lives inside `caller.py` route bodies), and
   `store.py` requires a runtime `init(read_fn, write_fn, awrite_fn, lock, config)` call with
   spine-injected dependencies before `read()`/`write()` work. So a *pure* in-process "call
   `campaign.py`/`store.py` directly" path is **not cleanly available without either extracting
   logic from `caller.py` (forbidden) or duplicating it (drift risk on a money path).** Therefore:
   - **Primary transport = authenticated localhost HTTP loopback.** Each `api_tools.fn` issues a
     request to `http://127.0.0.1:<port>/<route>` with a service auth token. This touches NOTHING
     in the spine, reuses the spine's existing auth/validation/store wiring verbatim (no
     duplication, no drift), and is the most robust answer to "do not edit caller.py."
   - **In-process fast-path (optional, opportunistic):** for any operation whose logic *is*
     cleanly callable without request context (read-only aggregations, future extracted helpers),
     the same `ToolSpec.fn` may call it directly — a pure optimization behind the unchanged
     interface, not an architectural commitment.
   Either way the interface is identical and **swapping the registry for `StubTools` is what makes
   the offline test possible** (no socket, no auth token, no network). The *exposure* of aimanager
   itself (`/aimanager/*` endpoints) is delivered as a **written, un-applied diff**
   (`caller_wiring.diff`) — matching the project's "final wiring deferred" stance. Nothing in
   `caller.py`/`agent.py` is modified by this work.

2. **Offline acceptance of an LLM-driven agent.**
   The loop never *requires* an LLM. When `AIMANAGER_LLM_PROVIDER=none` (default), the
   orchestrator uses `planner_stub.StubPlanner`, a deterministic rule-based planner that emits a
   canned, valid `Plan`. The test (§9) drives a full plan→approve→execute cycle, an over-budget
   rejection, and audit writes — with **zero keys and zero network**. This proves the
   load-bearing machinery (gates, idempotency, audit, kill-switch) independent of any model.

3. **The LLM driver is itself a dormant integration.**
   `llm/driver.py` follows the `whatsapp.py` contract: import-safe, `is_configured()`, no-op
   `{"status":"not_configured"}` when blank. Provider-agnostic; Claude and Groq are documented
   adapters. Default is `none`.

4. **State/persistence stays self-contained.**
   aimanager keeps its plan/approval/decision state in its OWN append-only JSONL
   (`store.py`, mirroring `audit.py`) under `var/aimanager_state.jsonl`. It also calls
   `audit.record(...)` with new action names (`aimanager.plan`, `aimanager.approve`,
   `aimanager.reject`, `aimanager.execute`, `aimanager.killswitch`) so every decision lands in
   the existing immutable audit too. **No new columns in `db/models.py`.** (A future migration to
   a Postgres `aimanager_decisions` table is noted as optional, not required — same posture
   `audit.py` takes about its own JSONL→Postgres move.)

---

## 4. DATA MODEL (aimanager's own JSONL records — no spine schema change)

### 4.1 `Plan` (one tick's proposed actions)

```json
{
  "plan_id": "pl_<uuid>",
  "tenant_id": "<org_id>",
  "created_at": "2026-06-09T18:00:00+05:30",
  "objective": "maximize qualified leads under daily budget",
  "rationale": "lead velocity down 20% vs 7d avg; campaign C2 CTR best; budget headroom ₹1,800",
  "actions": [
    {
      "action_id": "ac_1",
      "tool": "ads.set_budget",
      "args": {"platform": "google", "campaign_ref": "g_123", "daily_budget_inr": 1500},
      "side_effecting": true,
      "money": true,
      "est_spend_inr": 1500,
      "reversible": "pause_only"
    },
    {
      "action_id": "ac_2",
      "tool": "leads.enqueue_calls",
      "args": {"segment": "hot", "max": 50, "campaign_id": "C2"},
      "side_effecting": true,
      "money": false,
      "est_spend_inr": 0,
      "reversible": "yes"
    }
  ],
  "est_total_spend_inr": 1500,
  "requires_approval": true,
  "status": "proposed"   // proposed | approved | rejected | executed | partially_executed | killed
}
```

### 4.2 `Decision` (the gate outcome, one per money/over-threshold plan)

```json
{
  "decision_id": "dc_<uuid>", "plan_id": "pl_...", "tenant_id": "...",
  "decided_by": "<user_id|auto>", "decision": "approve|reject",
  "reason": "", "at": "...", "spend_authorized_inr": 1500
}
```

### 4.3 `ExecutionRecord` (idempotent result of running one action)

```json
{
  "exec_id": "ex_<uuid>", "plan_id": "pl_...", "action_id": "ac_1",
  "idempotency_key": "<plan_id>:<action_id>",
  "result": {"ok": true, "status": "sent:200", "provider": "google", ...},
  "actual_spend_inr": 1500, "at": "..."
}
```

All three are append-only JSONL lines in `var/aimanager_state.jsonl`; the matching audit event
is written via `audit_bridge`.

---

## 5. TOOL REGISTRY — the agent's hands (in-process adapters over the API)

`tools/__init__.py` defines a `ToolSpec`:

```python
@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str          # prescriptive "call this when…" (Opus 4.8 needs trigger conditions)
    input_schema: dict        # JSON Schema, strict (additionalProperties: false)
    fn: Callable[[dict, Ctx], dict]
    side_effecting: bool      # read-only tools can run without a gate
    money: bool               # True => external irreversible spend => always gated
```

`ToolRegistry.all()` returns the list passed to the LLM driver as the tool catalog. Swapping the
registry for `StubTools` (same names, in-memory effects) is what makes the offline test possible.

### 5.1 Tool catalog (maps 1:1 to existing API operations / ad adapters)

| Tool | Backs | side_effecting | money | Gate |
|---|---|---|---|---|
| `analytics.read` | `GET /stats`, `/analytics`, `/calls`, `/leads/hot` | no | no | none (read) |
| `billing.read` | `GET /billing/overview`, `/billing/ledger`, `/usage` | no | no | none (read) |
| `campaigns.list` / `campaigns.get` | `GET /campaigns`, `/campaigns/{cid}` | no | no | none |
| `campaigns.create` | `POST /campaigns` | yes | no | audit only |
| `campaigns.update` | `POST /campaigns/{cid}` (status, budget pacing) | yes | no | audit only |
| `leads.enqueue_calls` | `POST /run` (start dialer for a segment) | yes | no* | credit-ledger debit; audit |
| `whatsapp.send` | `POST /whatsapp/send` | yes | no* | credit-ledger debit; audit |
| `suppression.add` | `POST /suppression` | yes | no | audit |
| `ads.create_campaign` | `ads/*` adapter | yes | **yes** | **approval gate** |
| `ads.set_budget` | `ads/*` adapter | yes | **yes** | **approval gate** |
| `ads.pause_campaign` | `ads/*` adapter | yes | no | audit (de-risking action; allowed autonomously) |
| `ads.get_spend` | `ads/*` adapter | no | no | none (read) |

`*` Internal call/WhatsApp actions cost *metered credits*, not external money — they debit the
existing credit ledger (per `credit-ledger-firewall.md`) and are allowed autonomously up to a
configurable per-tick action cap. Only **external ad spend** trips the human approval gate.

---

## 6. THE LOOP — `orchestrator.run_tick(tenant_id, mode)` (plan → approve → execute)

```
run_tick(tenant_id, mode="auto"):
  0. KILL-SWITCH: if guardrails.killed(tenant_id): audit('aimanager.killswitch'); return {status:"halted"}
  1. CONTEXT: ctx = gather_context(tenant_id)   # via read-only tools: stats, billing, hot leads
  2. PROPOSE:
       if llm.is_configured(): plan = llm.propose(ctx, registry.all())   # manual tool-use loop
       else:                   plan = StubPlanner().propose(ctx, registry.all())
       plan = validate_plan(plan)                # pydantic/JSON-schema; reject malformed
       store.append(plan); audit('aimanager.plan', meta=plan.summary())
  3. GUARDRAILS (pre-exec, deterministic):
       guardrails.check(plan):
         - sum(money actions) <= remaining daily/weekly external-spend cap?  else REJECT/trim
         - any single money action <= per-action cap?                         else REJECT/trim
         - external-spend in plan == 0  OR  approval present?                  else PARK for approval
         - kill-switch not set
  4. APPROVAL GATE (only if plan has money>0 above AIMANAGER_APPROVAL_THRESHOLD_INR):
       - mode=="auto": set plan.status="proposed"; PARK; notify approver (PushNotification/webhook); return
       - mode=="approved" (called after a human POST /aimanager/plans/{id}/approve): proceed
       - on reject: store Decision(reject); audit('aimanager.reject'); return
  5. EXECUTE (idempotent, per-action):
       for action in plan.actions:
         key = f"{plan.plan_id}:{action.action_id}"
         if store.already_executed(key): continue            # idempotent re-run safety
         result = registry[action.tool].fn(action.args, ctx) # dormant adapters no-op if unconfigured
         store.append(ExecutionRecord(key, result, actual_spend))
         guardrails.record_spend(tenant_id, actual_spend)     # decrement cap atomically
         audit('aimanager.execute', object_id=action.action_id, meta=result)
         if not result.get("ok") and action.money: HALT remaining money actions (fail-safe)
  6. RETURN {status, plan_id, executed, parked_for_approval, spend_authorized, spend_actual}
```

**Key safety properties baked in:** read-only context first; deterministic guardrails run
*before* any side effect; money actions above threshold cannot execute without a recorded human
approval; every action is idempotent by `(plan_id, action_id)`; a failed money action halts the
rest of the money actions in that plan (fail-safe, not fail-open); the kill-switch short-circuits
at step 0 and is checked again before each money action.

---

## 7. SPEND / APPROVAL / AUDIT GUARDRAILS (the highest-risk surface)

Ad-platform budget is **real, irreversible money paid to third parties** — categorically
different from the internal metered credit ledger. The guardrail design treats it as the most
dangerous thing in the system.

### 7.1 Spend caps (deterministic, enforced in code — never delegated to the LLM)

`guardrails.py` reads, per tenant, from env/config (overridable per-org in the JSONL config):

| Cap | Env | Default | Meaning |
|---|---|---|---|
| Per-action external spend | `AIMANAGER_MAX_ACTION_INR` | `2000` | No single ad action may set/spend more than this |
| Daily external spend | `AIMANAGER_MAX_DAILY_INR` | `5000` | Sum of all ad spend authorized in a rolling 24h |
| Weekly external spend | `AIMANAGER_MAX_WEEKLY_INR` | `25000` | Rolling 7-day ceiling |
| Approval threshold | `AIMANAGER_APPROVAL_THRESHOLD_INR` | `0` | Any plan whose external spend exceeds this needs a human approve. Default `0` = **all external spend is human-approved** (safest default; raise to grant autonomy) |
| Per-tick action cap | `AIMANAGER_MAX_ACTIONS_PER_TICK` | `25` | Bounds internal (call/WhatsApp) action fan-out |

Spend is tracked in `store.py` as append-only debits; `remaining = cap − sum(window)`. Caps are
checked **before** execution and a debit is recorded **after** each actual spend. **Concurrency
caveat (load-bearing — this is the money path):** plain append-only JSONL gives NO atomic
read-modify-write, so a cron tick and a manual `POST /aimanager/tick` running concurrently could
both read `remaining=5000` and both authorize — a double-authorize, the exact failure we most
want to prevent on irreversible spend. `audit.py`'s in-process `threading.Lock` does not cover a
second process. The spend ledger therefore **must use a real single-writer guarantee**, in order
of preference: (a) a Postgres row with `SELECT … FOR UPDATE` / an atomic `UPDATE … WHERE
remaining >= :amount RETURNING` decrement (the recommended production form — the optional
`aimanager` table noted in §3.1); or, while file-backed, (b) an OS advisory file lock
(`fcntl.flock` / `msvcrt.locking`) around the *check-and-debit* critical section, or (c) a
single-writer execution model (only the cron tick may authorize spend; manual ticks are
`dry_run` only). The check-and-debit is wrapped as one critical section — checking the cap and
writing the debit must not be separable. If the LLM proposes more than the cap, the plan is
**trimmed or rejected deterministically** inside that section — the model cannot override a cap.

### 7.2 Approval gate (mandatory human-in-the-loop above threshold)

- Plans with `est_total_spend_inr > AIMANAGER_APPROVAL_THRESHOLD_INR` are **parked** in
  `proposed` status and surfaced to a human via `GET /aimanager/plans?status=proposed`, a
  `PushNotification`, and/or a registered webhook.
- A human approves with `POST /aimanager/plans/{plan_id}/approve` (or rejects). Only an
  authenticated manager/admin role may approve (enforced when the deferred diff mounts the router
  behind the existing auth dependency). The approval writes a `Decision` + audit event and
  authorizes *exactly* the spend in the plan — re-running cannot escalate it (idempotency).

### 7.3 Kill-switch & dry-run

- **Kill-switch:** `POST /aimanager/killswitch {on:true}` (and env `AIMANAGER_KILLSWITCH=1` as a
  break-glass). When on, `run_tick` halts at step 0 and **no adapter is called**. Checked again
  before every money action.
- **Dry-run / idempotent execute:** every adapter call carries an idempotency key
  `(plan_id, action_id)`; re-execution is a no-op. `mode="dry_run"` runs the full loop and
  guardrails but routes every side-effecting tool to its Stub (no real spend), returning the plan
  that *would* run — used for previews and the offline test.

### 7.4 Immutable audit (reuse `audit.py`, do not reinvent)

Every state transition writes an `audit.record(...)`:
`aimanager.plan`, `aimanager.approve`, `aimanager.reject`, `aimanager.execute`,
`aimanager.killswitch`, `aimanager.cap_block`. `actor` = approving user (or `system` for
autonomous internal actions), `tenant_id` = org, `meta` = redacted action summary + actual spend.
Because `audit.py` is append-only JSONL and never rewrites lines, the spend/approval trail is
tamper-evident by construction. aimanager additionally keeps its richer plan/decision/exec
records in its own JSONL store.

---

## 8. THE DORMANT-UNTIL-CREDS MODULES (files / interfaces / endpoints / data)

### 8.1 LLM driver `llm/driver.py` (mirrors `whatsapp.py`)

```python
def _cfg() -> dict:               # reads AIMANAGER_LLM_PROVIDER + provider keys from env
def is_configured() -> bool:      # True only if provider != none AND its key is present
def status() -> str:              # "configured" | "not_configured" | "error"
def propose(ctx: dict, tools: list[ToolSpec]) -> dict:
    # provider=none -> {"status":"not_configured"}  (caller falls back to StubPlanner)
    # provider=claude -> Anthropic manual tool-use loop, model claude-opus-4-8,
    #                    thinking={"type":"adaptive"}, output_config={"effort":"high",
    #                    "format": PLAN_JSON_SCHEMA}; NO budget_tokens/temperature.
    # provider=groq   -> OpenAI-compatible chat.completions with tools=[...] (round-robin keys)
    # NEVER raises; on any provider error returns {"status":"error:<redacted>"}
```

Approval-gate integration: the Claude path uses the **manual** loop (stop on `tool_use`, do NOT
auto-execute) so the orchestrator decides per-tool whether to gate; only after guardrails pass
does the orchestrator actually call the tool fn and feed the `tool_result` back.

### 8.2 Ad adapters `ads/google_ads.py`, `ads/meta_ads.py` (mirror `whatsapp.py`)

Each exposes:
```python
def is_configured() -> bool
def status() -> str
def create_campaign(spec: dict) -> dict     # {"ok":bool,"status":"...","provider":"google","ref":...}
def set_budget(campaign_ref: str, daily_inr: float) -> dict
def pause_campaign(campaign_ref: str) -> dict
def get_spend(campaign_ref: str, window: str) -> dict
```
All return `{"status":"not_configured"}` and perform NO network call until their creds exist.
Google uses the Ads API REST/gRPC; Meta uses Graph Marketing API
(`https://graph.facebook.com/v21.0/act_<AD_ACCOUNT_ID>/campaigns`). Currency assumed INR;
amounts passed in account currency minor units where the platform requires (Meta budgets are in
account-currency cents → multiply ₹ by 100; documented in each adapter header like `whatsapp.py`).

### 8.3 Additive endpoints `endpoints.py` (FastAPI `APIRouter` — mounted via deferred diff)

| Method | Path | Purpose | Auth |
|---|---|---|---|
| `POST` | `/aimanager/tick` | Run one plan→(gate)→execute cycle | admin/system |
| `GET`  | `/aimanager/plans` | List plans (filter `?status=proposed`) | manager+ |
| `GET`  | `/aimanager/plans/{id}` | Plan detail + decisions + execs | manager+ |
| `POST` | `/aimanager/plans/{id}/approve` | Human approval gate | manager/admin |
| `POST` | `/aimanager/plans/{id}/reject` | Human rejection | manager/admin |
| `POST` | `/aimanager/killswitch` | Halt all autonomous action | admin |
| `GET`  | `/aimanager/status` | Config/dormancy + caps + remaining spend + provider | manager+ |
| `GET`  | `/aimanager/audit` | aimanager-scoped audit (proxy to `audit.tail(action_prefix="aimanager")`) | manager+ |

`caller_wiring.diff` (the only thing that ever touches `caller.py`, and it's delivered un-applied):

```diff
+ from automation.aimanager.endpoints import router as aimanager_router
  ...
+ app.include_router(aimanager_router)   # mount aimanager (additive; behind existing auth deps)
```

The orchestrator passes the same auth/role dependencies the rest of `caller.py` uses, so
approval is restricted to manager/admin once mounted.

---

## 9. OFFLINE ACCEPTANCE TEST (`tests/test_offline.py`) — ZERO keys, ZERO network

Run: `python -m pytest droplet_work/automation/aimanager/tests/test_offline.py -q`
Must pass with **no env keys set and no network access**. Asserts:

1. **Import-safe & dormant:** `import automation.aimanager`; `driver.status()=="not_configured"`,
   `google_ads.is_configured() is False`, `meta_ads.status()=="not_configured"`; no exception.
2. **Dormant adapters no-op:** `google_ads.set_budget("x", 100) == {"status":"not_configured", ...}`
   and made **no** HTTP call.
3. **Stub plan flows end-to-end:** with `AIMANAGER_LLM_PROVIDER` unset, `run_tick(tenant, "dry_run")`
   produces a valid `Plan`, runs guardrails, executes against `StubTools`, and writes plan +
   exec + audit records.
4. **Approval gate blocks money:** a plan with external spend `> threshold` is **parked**
   (`status=="proposed"`, nothing executed); after `approve_plan(plan_id, user)`, a second
   `run_tick(..., "approved")` executes it; audit shows `aimanager.plan` → `aimanager.approve`
   → `aimanager.execute` in order.
5. **Over-budget rejected deterministically:** a plan whose action exceeds
   `AIMANAGER_MAX_ACTION_INR` is trimmed/rejected by `guardrails.check` *before* any execute, with
   an `aimanager.cap_block` audit row; the cap was enforced by code, not the model.
6. **Kill-switch halts:** with kill-switch on, `run_tick` returns `status=="halted"` and zero
   adapter calls / zero new exec records.
7. **Idempotency:** running the same approved plan twice yields exactly one `ExecutionRecord`
   per action (no double-spend).

A second tiny self-test (`selftest_bad_plan`) feeds the validator a malformed plan and asserts it
is rejected — proving the schema gate works without an LLM. (Mirrors the existing
`eval/selftest_bad_model.py` convention in this repo.)

---

## 10. EXACT CREDENTIALS / ACCOUNTS THE FOUNDER MUST PROVIDE

Nothing here is needed to build or to pass the offline test. These activate dormant modules.
**All are server-side only — paste into the droplet's env/secret store, never the frontend, never
git.** Until pasted, each module stays a graceful no-op.

### A. LLM reasoning (pick ONE; or leave all blank to run on the deterministic stub)
- **Claude (recommended):** `ANTHROPIC_API_KEY` — from console.anthropic.com → API Keys.
  Set `AIMANAGER_LLM_PROVIDER=claude`.
- **Groq (cheapest; already used here):** `GROQ_API_KEY` (or the existing round-robin
  `GROQ_API_KEY_1..N`) — from console.groq.com. Set `AIMANAGER_LLM_PROVIDER=groq`.

### B. Google Ads (verified 2026; ad-spend autonomy) — env prefix `GOOGLE_ADS_`
- `GOOGLE_ADS_DEVELOPER_TOKEN` — 22-char token, from your Google Ads **manager (MCC)** account
  → API Center (requires Basic/Standard access approval).
- `GOOGLE_ADS_CLIENT_ID` and `GOOGLE_ADS_CLIENT_SECRET` — an **OAuth 2.0 Desktop/Web client** in
  Google Cloud Console (APIs & Services → Credentials).
- `GOOGLE_ADS_REFRESH_TOKEN` — generated once via the OAuth consent flow for the account that
  manages the ads. ⚠️ **2026 change:** generating a *new* refresh token after **2026-04-21**
  requires MFA on the Google account; existing tokens keep working.
- `GOOGLE_ADS_CUSTOMER_ID` — the 10-digit Ads account id, **hyphens removed**
  (`123-456-7890` → `1234567890`). Optionally `GOOGLE_ADS_LOGIN_CUSTOMER_ID` (the MCC id) if
  managing via a manager account.

### C. Meta / Facebook Marketing (verified 2026; ad-spend autonomy) — env prefix `META_ADS_`
- `META_ADS_APP_ID` and `META_ADS_APP_SECRET` — from a Meta app at developers.facebook.com
  (App → Settings → Basic).
- `META_ADS_SYSTEM_USER_TOKEN` — a **System User** token (business.facebook.com → Business
  Settings → Users → System Users → generate token). Non-expiring; assign the System User to the
  ad account as **Admin**. Required permissions: **`ads_management`, `ads_read`,
  `business_management`**.
- `META_ADS_AD_ACCOUNT_ID` — the ad account id (the numeric part; the adapter prefixes `act_`).
- Optional `META_ADS_API_VERSION` (default `v21.0`).

### D. LinkedIn Ads (design-only stub today) — env prefix `LINKEDIN_ADS_`
- `LINKEDIN_ADS_CLIENT_ID`, `LINKEDIN_ADS_CLIENT_SECRET`, `LINKEDIN_ADS_ACCESS_TOKEN`,
  `LINKEDIN_ADS_AD_ACCOUNT_URN` (e.g. `urn:li:sponsoredAccount:123456789`). Adapter ships as a
  no-op stub; wire up only if LinkedIn becomes a channel.

### E. Guardrail / approval config (optional — sane defaults shipped; tune to taste)
`AIMANAGER_LLM_PROVIDER`, `AIMANAGER_APPROVAL_THRESHOLD_INR` (default `0` = approve all spend),
`AIMANAGER_MAX_ACTION_INR` (`2000`), `AIMANAGER_MAX_DAILY_INR` (`5000`),
`AIMANAGER_MAX_WEEKLY_INR` (`25000`), `AIMANAGER_MAX_ACTIONS_PER_TICK` (`25`),
`AIMANAGER_KILLSWITCH` (`0`).

---

## 11. HONEST REAL-VS-HYPE

| Claim | Reality |
|---|---|
| "Replaces the ad/marketing team" | **No.** It is a *funnel ops manager that proposes and executes under gates*. Above the spend threshold a human approves; the default threshold is `0`, i.e. **every rupee of external ad spend is human-approved** until you deliberately grant autonomy. It genuinely automates the *internal* funnel (which leads to call/WhatsApp, campaign pacing) against the already-metered ledger. |
| "Fully autonomous money spending" | Only within hard, code-enforced caps the model cannot override, and only above a threshold you set. Fail-safe: a failed money action halts the rest. |
| "Ad actions are reversible" | Partly. `pause_campaign` stops future spend; **already-spent budget is not refundable**. The system minimizes exposure (small caps, dry-run preview, idempotency) but cannot undo spend. |
| "The LLM decides budgets" | The LLM *proposes*; deterministic `guardrails.py` decides what's allowed. Caps, threshold, and kill-switch are pure code. |
| "Works offline" | The orchestration, gates, audit, and idempotency work fully offline on the StubPlanner. The *reasoning quality* obviously needs a real LLM key; the *safety machinery* does not. |
| "Multi-platform today" | Google + Meta adapters are real (dormant); LinkedIn is a design-only stub. Internal API tools are real. |

---

## 12. BUILD ORDER (suggested, each a verifiable unit)

1. `config.py` + `store.py` + `audit_bridge.py` + `guardrails.py` (pure, no deps) → unit test caps/kill-switch.
2. `tools/` registry + `StubTools` + `planner_stub.py` → unit test a stub plan validates.
3. `orchestrator.run_tick` (plan→gate→execute) wired to stubs → **offline acceptance test (§9) green.**
4. `llm/driver.py` (dormant; `none` path first, then `claude`, then `groq`) → status() test.
5. `ads/google_ads.py`, `ads/meta_ads.py`, `ads/linkedin_ads.py` (dormant) → dormancy test.
6. `endpoints.py` + `caller_wiring.diff` (un-applied) → router import test only.

Ship 1–3 first: that delivers the entire safety spine, fully tested, with no external dependency.
4–6 light up reasoning and real spend once the founder pastes keys and the orchestrator applies
the wiring diff.

---

## RED-TEAM FIXES (folded)

Adversarial review 2026-06-09. Every in-repo on-disk claim was re-verified against
`C:\Users\kunal\Desktop\caps\droplet_work\` and held: `whatsapp.py` is the exact dormant-until-creds
no-op pattern (`{"status":"not_configured"}`, never raises, sync+async, Meta Graph `v21.0`);
`campaign.py` has **zero** top-level `def`/`class` (confirms the "no clean in-process path" premise);
`store.py` defines `init(read_fn, write_fn, awrite_fn, lock, config)` at L371 and its `read()/write()`
are dead until that spine-injected call runs; `audit.py` exposes `record(actor, action, object_type,
object_id, …, meta)` (L60) and `tail(…, action_prefix="")` (L102) with an in-process `threading.Lock`
only (L31); `eval/selftest_bad_model.py` exists; and **every** route the tool catalog maps to is
present in `caller.py` (`/run`, `/whatsapp/send`, `/billing/overview`, `/billing/ledger`, `/campaigns`,
`/campaigns/{cid}`, `/leads`, `/leads/hot`, `/stats`, `/analytics`, `/suppression`, `/usage`, `/audit`).
Web-verified externals: Pydantic AI is active (v1.106.0, 2026-06-05, weekly cadence); Groq is active
(OpenAI-compatible chat-completions + tool calls); Meta System-User token + `ads_management`/`ads_read`/
`business_management` is the correct posture; Google Ads MFA-after-2026-04-21 is real. The following
gaps/corrections are now folded in and are **build-blockers where marked**:

1. **(BUILD-BLOCKER — transport auth) No service/system token exists in the spine.** `caller.py`
   resolves credentials per-tenant from Basic / `Authorization: Bearer` / `X-Auth` (L358-373); there is
   **no** internal/service-token concept. The "authenticated localhost loopback with a service auth
   token" therefore has no token to present today. **Fix:** the loopback path MUST authenticate as a
   real tenant — reuse an existing **admin/manager tenant access token** minted via `auth.issue_pair()`
   and injected into aimanager's env (`AIMANAGER_SERVICE_TOKEN`, dormant-until-set, server-side only,
   never logged/committed). Until that token is present, the live tool registry returns
   `{"status":"not_configured"}` and the orchestrator runs on `StubTools` (preserves the dormancy
   invariant). Do **not** add a new bypass auth path to the spine — that would be a security regression
   and would touch `caller.py`. This keeps every action correctly tenant-scoped and audited under a real
   actor rather than an anonymous "system" identity on the money path.

2. **(CORRECTION — Google Ads activation) "existing tokens keep working" is misleading.** Verified:
   existing refresh tokens still mint access tokens, **but Google Ads API *calls* fail with
   `TWO_STEP_VERIFICATION_NOT_ENROLLED` unless the underlying Google account has 2-Step Verification
   enrolled** (rollout began 2026-04-21; BigQuery transfer flows 2026-05-07). **Fix to §10.B:** the
   founder MUST enable 2FA on the Google account that owns the refresh token *before* Google Ads goes
   live, regardless of token age. The `google_ads.py` adapter MUST treat a `TWO_STEP_VERIFICATION_NOT_
   ENROLLED` (or any auth-class) response as a non-raising `{"status":"error:auth_2fa_required"}` and
   surface it via `/aimanager/status` so a failed activation is visible, not silent. Prefer a **Google
   Cloud service-account / OAuth flow that is unaffected by the user-auth MFA rule** where the Ads
   account structure allows it.

3. **(CORRECTION — Meta API version) `v21.0` default is stale.** Meta deprecates versions on a rolling
   ~2-year schedule; current GA is ~v23–v25 and `v21.0` (released ~late-2024) is at/near end-of-life by
   mid-2026, risking silent fallback to the oldest-supported version or hard rejection. **Fix to §8.2 /
   §10.C:** change the shipped default `META_ADS_API_VERSION` to a then-current GA version (e.g.
   `v23.0`/`v24.0`) and keep it env-overridable (already specified). The adapter MUST log the resolved
   version and treat an "unsupported/deprecated version" response as a non-raising
   `{"status":"error:api_version_deprecated"}` surfaced via `/aimanager/status`. (Note: `whatsapp.py`
   also hardcodes `v21.0`; out of scope to edit the spine here, but the same drift exists there and
   should be tracked separately.)

4. **(HARDENING — spend ledger, already half-addressed) Pick ONE single-writer mechanism now; do not
   ship the JSONL-only path.** §7.1 already names the double-authorize race correctly. Resolve it
   concretely for build: since the spine is Postgres-backed (`db/engine.py`), the **money/spend ledger
   uses the Postgres atomic decrement** `UPDATE … SET remaining = remaining - :amt WHERE tenant_id=:t
   AND remaining >= :amt RETURNING remaining` inside one transaction — this is the *only* sanctioned
   path for the external-spend cap. The JSONL store may hold the audit/plan/exec narrative, but it MUST
   NOT be the authority for "remaining spend." If Postgres is somehow unavailable at run time, the cap
   check FAILS CLOSED (treat remaining=0, park for approval) rather than reading a non-atomic file.
   File-lock (fcntl/msvcrt) is acceptable ONLY for a strictly single-host file-backed fallback and must
   wrap the *entire* check-and-debit critical section.

5. **(SAFETY — approval gate field mismatch) Gate on the same field caps are computed from.** §6 step 4
   parks when "`money>0 above threshold`", §7.2 parks when `est_total_spend_inr > THRESHOLD`, and the
   `Plan` schema (§4.1) carries BOTH per-action `est_spend_inr` and top-level `est_total_spend_inr`
   plus a self-asserted `requires_approval`. The model-supplied `requires_approval`/`est_*` fields are
   **advisory only** and MUST NOT be trusted. **Fix:** guardrails recomputes total external spend from
   the *resolved tool + args* of each `money:true` action (ignoring the model's numbers), and the gate
   compares THAT against `AIMANAGER_APPROVAL_THRESHOLD_INR`. A plan that under-reports its spend cannot
   slip the gate. Add an offline test asserting a plan with `requires_approval:false` but real
   `money` actions above threshold is still parked.

6. **(SAFETY — default threshold semantics) `THRESHOLD=0` must mean "approve all spend > 0", not ">=".**
   With default `AIMANAGER_APPROVAL_THRESHOLD_INR=0`, any external spend of even ₹0.01 must park. Ensure
   the comparison is strict-greater on a value that, at the default, captures *all positive* spend
   (i.e. `external_spend > 0` when threshold is 0). A boundary bug here silently grants autonomy the
   spec promises is off-by-default. Covered by an explicit offline boundary test.

7. **(ROBUSTNESS — kill-switch race) Re-check kill-switch and re-decrement cap inside the same critical
   section as each money action**, not just at step 0 and "before each money action" as prose. Flipping
   the switch mid-tick must abort the *next* money action deterministically; fold the kill-switch read
   into the Postgres/file critical section from fix #4 so it cannot be raced by a concurrent tick.

8. **(MINOR — idempotency key durability) The idempotency key `(plan_id, action_id)` is only as strong
   as the executed-set's atomicity.** With the JSONL store, `already_executed(key)` then `append(...)`
   is itself a read-then-write race under concurrent ticks. Record the execution row in the **same
   Postgres transaction** that decrements spend (fix #4), keyed UNIQUE on `idempotency_key`, so a
   duplicate execute is rejected by the DB, not by a best-effort file scan.

**Residual risks accepted (not blockers):** (a) already-spent ad budget is irreversible — mitigated by
small caps + dry-run + ₹0 default threshold, never eliminated; (b) reasoning quality depends on the LLM
key and is unverified offline by design (only the safety machinery is); (c) provider API drift (Meta
version cadence, Google auth policy) is ongoing — the `/aimanager/status` surface + non-raising error
states make drift *visible* but cannot prevent a provider-side breaking change; (d) LinkedIn remains a
design-only stub. **Verdict: GO**, conditional on fixes #1, #4, #5 landing before any live external-spend
activation (they are the money-safety core); fixes #2, #3, #6–#8 land before flipping the corresponding
adapter/threshold live. The dormant-until-creds + non-breaking + "never touch caller.py/agent.py"
invariants are upheld throughout.

---

## Sources
- [Firecrawl — Best open-source agent frameworks 2026](https://www.firecrawl.dev/blog/best-open-source-agent-frameworks)
- [JetBrains/PyCharm — Top agentic frameworks for building applications 2026](https://blog.jetbrains.com/pycharm/2026/06/top-agentic-frameworks-for-building-applications-2026/)
- [Pydantic AI — practical production guide 2026](https://www.youngju.dev/blog/ai-platform/2026-04-12-pydanticai-practical-guide.en)
- [ZenML — Pydantic AI vs CrewAI for production workflows](https://www.zenml.io/blog/pydantic-ai-vs-crewai)
- [Google Ads API — OAuth overview](https://developers.google.com/google-ads/api/docs/oauth/overview) and [Generate user credentials](https://developers.google.com/google-ads/api/samples/generate-user-credentials)
- [Google Ads API MFA requirement (Apr 21, 2026)](https://almcorp.com/blog/google-ads-api-multi-factor-authentication/)
- [Meta Marketing API — Authentication](https://developers.facebook.com/documentation/ads-commerce/marketing-api/get-started/authentication) and [Access Token guide](https://developers.facebook.com/docs/facebook-login/guides/access-tokens/)
- Anthropic claude-api skill (in-repo): model `claude-opus-4-8`, adaptive thinking, manual tool-use loop for human-in-the-loop approval, `output_config.format`, no `budget_tokens`/`temperature` on Opus 4.8.
- In-repo prior art: `droplet_work/whatsapp.py` (dormant-until-creds pattern), `vendors/__init__.py` (adapter conventions), `audit.py` (immutable audit), `design/credit-ledger-firewall.md` (spend firewall), `design/orchestration-hatchet.md` (scheduling).
