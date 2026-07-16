# AI MANAGER — PLATFORM REUSE INVENTORY + EXECUTION-ADAPTER MAP

> READ-ONLY design wave (2026-06-10). Maps EXACTLY what the AI Manager reuses and how every intent group
> in `AI_MANAGER_MASTER_PROMPT.md` executes against REAL existing code on the live box
> `famit@168.144.153.145:/opt/famit-agent/` (API uvicorn `:8209`, public `https://panel.famit.in/api`).
> Verified by reading the on-disk source, not memory. Nothing here is built/changed.

---

## 0. THE BIG FINDING — the AI Manager is NOT greenfield; ~80% is ALREADY built on the box

The brief said "there is ALREADY a thin /ai-manager module (numbers/status)". That UNDERSTATES it. The live
box carries a **full AI Manager control-plane package** `ai_manager/` (1908 LOC, 6 build units DONE) +
the **AI-Workforce execution engine** `workforce/` (2252 LOC) it delegates into. The execution-adapter
layer the founder spec asks for **already exists** as `workforce/tools/catalog.py` — each tool maps 1:1 to
a real caller.py route over an authenticated loopback. The AI Manager's job is NOT to re-architect this;
it is to (a) ACTIVATE it (flags + service token + PIN enrollment + a DID), (b) wire the LiveKit voice
front-end, and (c) FILL THE GAPS (intents with no adapter yet: creative/workflow/booking/full-billing).

**Two-plane architecture, both already on disk, composed IN-PROCESS (not cross-HTTP yet):**
```
 CALLER (phone/chat)
   -> ai_manager.state_machine.CommandMachine.run()      [S0..S9 deterministic spine, LLM only fills slots]
        S1 identity.resolve(caller_id)  -> ai_manager.registry (var/aim_numbers.jsonl)
        S2 firewall_bridge.authenticate -> firewall.check_pin            (LOGIN PIN, anti-spoof)
        S5 identity.permits(role,grants,tool)                            (RBAC default-deny pre-filter)
        S6 firewall_bridge.authenticate(scope) -> firewall.mint_step_up  (FRESH per-action step-up token)
        S7 spoken CONFIRM (amount read back)
        S8 delegate.execute(tenant, action, step_up_token)
              -> workforce.run_agent(role=<worker>, task, ctx)          [the runner = defense-in-depth]
                   guardrails.check()  -> scope/DND/destructive/bulk/budget/approval verdict
                   wallet.reserve()    -> ACID hold for money actions
                   tool.fn(args, ctx)  -> workforce.tools.catalog        [THE EXECUTION ADAPTER]
                        transport.call(METHOD, PATH, run_token) -> caller.py /api  (RLS-scoped per run)
        S9 REPORT (deterministic speech)  + audit_bridge.record on EVERY transition
```

**`ai_manager/AI_MANAGER_STATE.md` corrections to the master spec (advisor-greenlit, already applied):**
1. Composition is **IN-PROCESS** (`import firewall/audit/workforce`), NOT cross-plane HTTP. The HTTP
   loopback (`transport.py`) exists but is DORMANT until `AIWF_SERVICE_TOKEN`. The spec's "dedicated
   service calling /api over the network" is REALISED as a loopback HTTP client on the SAME box (extractable
   later) — the design's coarse-service boundary holds, the wire is just localhost today.
2. Real firewall symbols: `check_pin(tid,pin)` (NOT `verify_pin`), `mint_step_up(tid,scope)->dict|None`,
   `verify_step_up_token(token,scope,expected_sub)`, `has_pin`, `set_pin`. `verify_otp` returns not_configured.
3. The AI Manager delegates to a **WORKER role** (telecaller/whatsapp/ad/strategist/ops/analytics), NEVER
   `role="manager"` (that role has only a no-op `delegate` scope).
4. Action vocabulary = **workforce tool-scope names** (`ads.set_budget`, `leads.enqueue_calls`,
   `whatsapp.send`, `analytics.read`), NOT firewall.classify's vocabulary.

---

## 1. EXECUTION-ADAPTER TABLE  (intent -> real adapter fn -> real /api endpoint -> payload -> gates)

The single source of truth for "how does intent X execute". `fn(args, ctx)` lives in
`workforce/tools/catalog.py` (live) mirrored by `workforce/tools/stub_tools.py` (offline). `ctx.run_token`
is the per-run per-tenant token (`auth.issue_pair`) so the loopback call is **RLS-scoped to the run's org_id**.
Cost column = `actual_spend_minor` the runner settles against a wallet hold.

| Master-spec intent group | NLU intent (closed enum) | Adapter fn (catalog.py) | REAL endpoint (caller.py:line) | Method + payload | Risk (identity.classify_risk) | Auth gate | Cost/wallet | Compliance |
|---|---|---|---|---|---|---|---|---|
| **analytics** (today/campaign/lead/cost summary) | `analytics.read` | `_analytics_read` | `GET /analytics` (:2996) | params `{campaign_id,from,to}` -> `{dialed,connected,answered,interested,callback,qualified,opted_out,voicemail,no_answer,funnel[]}` | **safe** | login PIN only (S2); RBAC `analytics` family | 0 | none |
| analytics — read leads/scores | `leads.read` (query) | `_leads_read` | `GET /leads` (:2680) `GET /leads/hot` (:4252) | params `{hot,sort}` -> `{leads[]}` | safe | login PIN | 0 | none |
| analytics — contacts/CRM 360 | `contacts.read` (query) | `_contacts_read` | `GET /contacts` (:2047) | params `{stage,hot,q,sort,limit}` | safe | login PIN | 0 | none |
| analytics — grounding facts | `brain.retrieve` | `_brain_retrieve` | `GET /brain/retrieve` (:2028) | params `{q,limit}` (FTS, keyless) | safe | login PIN | 0 | none |
| **billing** (balance/usage/breakdown) | `billing.read` (query) | `_billing_read` | `GET /billing/overview` (:3338) | -> overview JSON | safe | login PIN; RBAC `billing` family | 0 | none |
| billing — wallet credit balance | `wallet.read`* | (NOT in catalog yet — GAP) | `GET /wallet` (:2206) `GET /wallet/ledger` (:2230) | -> `{available_minor,held_minor}` | safe | login PIN | 0 | — |
| **call** (call hot leads / start bulk / retry) | `leads.enqueue_calls` | `_leads_enqueue_calls` | `POST /run` (:2826) | json `{campaign_id,lead_ids[]\|use_stored,leads,concurrency,...}` -> `{job_id,count,suppressed_count}` | **bulk** | S6 step-up PIN (scope `spend`) + S7 confirm | metered call credit (wallet at execute; NOT external-spend) | **DND/suppression + calling-window enforced in `/run` `_resolve_audience` AND re-checked in guardrails `_DND_SCOPES`** |
| call — single lead / retry / stop | (via `leads.enqueue_calls` w/ 1 id) | same | `POST /run` (single id) | same | bulk | step-up if bulk; single may pass cap | metered | DND |
| call — add number to DND | `suppression.add` | `_suppression_add` | `POST /suppression` (:3094) | json `{numbers}` | safe | login PIN | 0 | this IS the compliance write |
| **whatsapp** (send brochure/followup/bulk) | `whatsapp.send` | `_whatsapp_send` | `POST /whatsapp/send` (:3644) | json `{phone\|recipients[],template,...}` | **bulk** | S6 step-up PIN + S7 confirm | metered WA credit (wallet at execute) | DND + opt-out (`_DND_SCOPES`); bulk fan-out cap (`max_bulk_targets`) |
| **lead** (update stage / add note / assign) | `contacts.write` | `_contacts_write` | `PUT /contacts/{phone}` (:2126) | json `{tags,stage,name}` (NEVER writes leads) | safe (side-effecting) | login PIN; RBAC `contacts` family | 0 | none |
| lead — export | `data.export`* | (NOT in catalog — GAP, by design) | — | — | **destructive** -> always PARK + PIN | step-up `export` | 0 | export-consent / L3 |
| lead — delete | `leads.delete` | `_leads_delete` | `DELETE /leads/{id}` (:2765) | path id | **destructive** -> always PARK + PIN | step-up `destructive` | 0 | L3 audit |
| **campaign** (create/launch draft) | `campaigns.create` | (NOT in catalog yet — GAP) | `POST /campaigns` (:2446) | form `fields_json` -> `{id,name}` | **money** (launch) / safe (draft) | step-up if launch | 0 (creation); launch=spend later | none |
| campaign — pause/resume/budget/kill-losers | `ads.set_budget`/`ads.pause`/`ads.create_campaign` | `_ads_set_budget` / `_ads_pause` | `POST /ads/budget` / `POST /ads/pause` (**DORMANT — only exist when FEATURE_ADS=1; ads_engine real routes are `/ads/campaigns/propose|{id}/approve|{id}/pause|optimize`**) | json `{campaign_id,budget_minor}` | **money** (`recompute_spend_minor` from `budget_minor`) | S6 step-up PIN + S7 confirm + runner PARK if > approval_threshold | **wallet.reserve(hold) BEFORE act -> settle(actual) -> release leftover; daily_spend_cap; fail-CLOSED if no wallet** | none |
| **creative** (banner/video/brochure/pack) | `creative.generate_*`* | (NOT in catalog — GAP) | `media_gen`: `POST /media/video/jobs` (:90), `POST /media/image/generate` (:150) [DORMANT, FEATURE_MEDIA off] | json job spec -> `{job_id}` (async, poll) | money (metered gen) | step-up if billable | wallet meter on gen | none |
| **workflow** (create draft / activate) | `workflow.create_draft`* | (NOT in catalog — GAP) | `workflow`: `POST /workflows` create, `POST /workflows/{id}/publish` (:156), `/run` (:161), `/runs/{id}/approve` (:115) [FEATURE_WORKFLOWS] | json graph DSL -> draft; publish/activate = PIN | safe (draft) / risky (activate) | step-up on activate | per-node BUDGET hold at run | DND re-checked per node |
| **booking** (today/tomorrow/create/reschedule) | `booking.*`* | (NOT in catalog — GAP) | `booking`: `GET /booking/availability` (:98), `POST /booking/book` (:106), `/{id}/reschedule` (:132) [FEATURE_BOOKING] | json slot/resource -> `{booking_id}` | safe (booking is FREE) | login PIN | 0 (reminder actuation metered) | slot-uniqueness (no double-book) |

`*` = intent named in the master spec's §11 taxonomy but **NOT yet present** in `intent/driver.py`'s
`COMMAND_INTENTS`/`QUERY_INTENTS` AND with **no catalog adapter** — the gap list in §5.

---

## 2. THE REUSABLE PRIMITIVES — precise signatures (verified on disk)

### 2.1 Logto auth + `is_admin` + tenant resolution (the tenant-scoping seam)
- **`caller.resolve_tenant(request)`** (caller.py:~404 per memory) — the SINGLE tenant seam. Tries JWT
  bearer (HS256, `var/secret`), then legacy `X-Auth: FamitCall2026` -> **admin** tenant, then
  `tenant_id.hmac`. Returns a tenant dict `{tenant_id, role, is_admin, ...}`. **The AI Manager NEVER reads
  tenant from a body field** — `ai_manager.endpoints` calls `_resolve_tenant(request)` (lazy `import caller`)
  exactly so it inherits this seam. The per-run loopback mints a FRESH per-tenant token via
  `auth.issue_pair(tenant_of_run)` (`workforce/tools/transport.mint_run_token`) so every catalog call
  re-authenticates AS the run's org under RLS — a single admin token would mis-scope writes.
- **`caller.can(tenant, action)`** — RBAC predicate (`manage_tenants`->admin, `write`->admin|manager).
  `ai_manager.endpoints._can` lazy-imports it with a conservative fallback.
- Logto (self-hosted OIDC) is provisioned on the hatchet box but **caller.py auth still runs legacy
  HS256/HMAC**; Logto JWT verification is a later wiring unit. The AI Manager composes `resolve_tenant`,
  so it gets Logto for free the day caller.py switches.

### 2.2 firewall.py (PIN + step-up) — `ai_manager/firewall_bridge.py` wraps it
- `firewall.has_pin(tid)` / `firewall.set_pin(tid,pin)` / **`firewall.check_pin(tid,pin)->bool`** (salted
  sha256, `var/pins.json`; raw PIN consumed in-memory, NEVER logged/persisted).
- **`firewall.mint_step_up(tid, scope)->{step_up_token,expires_in,scope}|None`** (HS256, `var/secret`,
  sub-bound to tid, short TTL). None if firewall not init'd.
- **`firewall.verify_step_up_token(token, scope, expected_sub)->claims|None`** — asserts sig+exp+type+scope
  **AND `sub == expected_sub`** (anti-replay: a leaked tenant-A token is rejected for tenant-B). This is the
  load-bearing approval gate; `workforce.runner.resume_approved` calls it with `expected_sub=ctx.org_id`.
- `firewall.require_step_up(request, scope, tenant)` — raises `StepUpDenied(403)` on miss; **pass-through
  when `FIREWALL_ENABLED` OFF / tenant has NO PIN** (non-breaking). The AI Manager router's
  `_require_step_up` catches it. **HOW TO REQUIRE A PIN for a new risky route:** call
  `firewall.require_step_up(request, "<spend|destructive>", t)` at the top of the handler (mirrors
  ai_manager.endpoints `set_grants`/`revoke`), OR (voice path) let the state machine's S6 `_step_up` mint
  the token and carry it on `delegate.execute(..., step_up_token=...)`.
- **Bridge entry the state machine calls (S2 + S6):** `firewall_bridge.authenticate(tid, secret, *, scope,
  method)-> {ok, step_up: dict|None, reason}`. scope="" => login-only (no token); scope!="" => also mints a
  scoped step-up token. **Fail-CLOSED** (firewall absent => deny).

### 2.3 wallet.py (CostGuard holds/settle) — composed by `workforce.runner`, NOT directly by ai_manager
- `wallet.reserve(org_id, amount_minor, *, resource_type, resource_id, idem_key, is_admin)-> hold` — ONE
  atomic conditional `UPDATE ... WHERE available>=amt RETURNING` (no oversell; returns None on no funds).
- `wallet.settle(hold, actual_minor, *, idem_key, is_admin)` — captures min(actual,reserved), refunds
  remainder, CLOSES the hold (so settle ONCE on terminal, never per-poll).
- `wallet.release(hold, *, idem_key)` — release a hold on failure/skip.
- Runner usage (`runner.py:_reserve/_settle/_release`): money action -> `idem=f"aiwf:{rid}:{tool}:{rid}"`
  reserve BEFORE execute -> settle `actual_spend_minor` after -> release on exec error/duplicate-idem.
  **A money gate with no wallet FAILS CLOSED (treat funds as 0 -> block)** — never fail-open on money.
- ⚠ Two SEPARATE balances by plan: `billing.json.balance` (prepaid) vs `wallet_accounts` (prepaid_wallet)
  — the gate branches on plan, NEVER sums. Internal metered actions (call/WA credit) are NOT `money:true`
  in guardrails (the wallet meters those at execute); only EXTERNAL spend (ads/invoices) is `money:true`.

### 2.4 audit.py / immutable events ledger — `ai_manager/audit_bridge.py` wraps it
- **`audit.record(actor, action, object_type, object_id, channel, tenant_id, meta)`** — append-only JSONL
  `var/audit_log.jsonl` DUAL-mirrored to the immutable PG `events` table (content-hash PK, INSERT ON
  CONFLICT DO NOTHING). Queryable via `GET /audit?channel=` (caller.py:2158).
- AI Manager writes via `audit_bridge.record(action, actor, tenant_id, ...)` -> prefixes
  **`aimanager_voice.`**, channel **`ai`**. Every S0..S9 transition audits (call_start/authed/auth_fail/
  permission_denied/stepup_ok/stepup_fail/cancelled/execute/call_end). **Actor = the verified TENANT,
  never "system"** (tamper-evident spend trail). meta is redacted (PIN/OTP/token -> `***`).
- **HOW TO WRITE AN IMMUTABLE LOG from a new action:** call `audit.record(...)` once after the
  authoritative write — the chokepoint dual-mirrors it to PG `events`; do NOT write a new JSONL.

### 2.5 RLS pattern for new `ai_manager_*` tables (FORCED RLS)
- Today the AI Manager registry/sessions are **JSONL** (`var/aim_numbers.jsonl`, `var/aim_sessions.jsonl`)
  with **tenant scoping enforced IN-CODE** on every read (rows filtered by `tenant_id`). This is the F2/F4
  "ship-first" posture.
- The master spec's `ai_manager_*` PG tables (profiles/authorized_users/sessions/commands/audit_logs/
  action_runs) get FORCED RLS via the **standalone idempotent `schema.sql`** pattern (mirror
  `crm/schema.sql` / `kb/schema.sql` / wallet `db/ddl_wallet.sql` byte-for-byte), NOT an Alembic rev:
  ```sql
  ALTER TABLE ai_manager_x ENABLE ROW LEVEL SECURITY;
  ALTER TABLE ai_manager_x FORCE ROW LEVEL SECURITY;
  CREATE POLICY p ON ai_manager_x USING
    (current_setting('app.is_admin',true)='1' OR org_id=current_setting('app.tenant_id',true))
    WITH CHECK (current_setting('app.is_admin',true)='1' OR org_id=current_setting('app.tenant_id',true));
  ```
  Applied via a lazy `ensure_schema()` on first PG use. All I/O via `db.engine.session(tenant_id=, is_admin=)`
  (param is `tenant_id=` even though the column is `org_id` — the GUC is `app.tenant_id`). Column `org_id`
  (P1 convention). This is the EXACT shape crm/payments/booking already use; copy it.

### 2.6 Voice stack (LiveKit + VoBiz/SIP + Sarvam STT + Groq LLM + Sarvam TTS)
- The OUTBOUND dialer voice agent is `agent.py` (livekit-agents, agent_name `capsy`), dispatched by
  `caller.run_job` with metadata `{campaign_id, lead_name}`. STT Sarvam `saarika:v2.5` `language="unknown"`,
  LLM Groq `llama-4-scout-17b-16e-instruct` (`max_completion_tokens`, NOT max_tokens), TTS ElevenLabs Flash
  v2.5 (`hi`/`en` only — degrade Gujarati to Hindi). Trunk TCP `ST_fmtVmNJmpzKa`, RTP via iptables.
- **AI Manager INBOUND seam = `ai_manager/inbound_agent.py` (DEFERRED stub today).** The state machine is
  **channel-agnostic**: it drives an injected `Transport` (`speak/listen/collect_secret`) + optional
  `recorder` (pause/resume for PIN audio hygiene). A LiveKit voice adapter and a chat adapter are THIN
  wrappers over `state_machine.run_command_offline(...)`. The inbound webhook -> session-create -> streaming
  STT -> machine -> TTS reply is the unbuilt LiveKit wire (needs a dedicated DID `AIM_VOICE_DID` +
  `AIM_VOICE_SIP_TRUNK_ID` — founder blocker). PIN is collected via `collect_secret` with the recorder
  PAUSED so digits never hit the transcript (`****` masked).

### 2.7 workflow-studio (React Flow graph JSON + create/publish API)
- Module `workflow/` mounted at `/workflows` (FEATURE_WORKFLOWS). A Workflow JSON DSL -> static validator/
  dominator -> ONE durable interpreter on the Hatchet spine. Endpoints: `POST /workflows` (create/draft),
  `PUT /workflows/{id}`, `POST /workflows/{id}/publish` (:156), `POST /workflows/{id}/run` (:161),
  `POST /workflows/runs/{id}/approve` (PIN, :115). **Spec Flow-6 ("voice -> create workflow DRAFT, never
  auto-activate")** = the AI Manager emits a graph JSON + calls create (draft), activation = the publish/run
  route behind a step-up. **No catalog adapter exists yet** — see GAP §5.

### 2.8 creative / media-gen (the async job API)
- Module `media_gen/` mounted at `/media` (FEATURE_MEDIA, DORMANT). `POST /media/video/jobs` (:90),
  `GET /media/video/jobs/{id}/poll` (:104), `POST /media/image/generate` (:150). Async: returns `{job_id}`,
  poll for completion, approve/reject. **Spec Flow-5 (creative asset pack)** maps here. **No catalog adapter
  yet** — see GAP §5. The "launch ads after creative = separate high-risk PIN" is the `ads.set_budget`
  money gate above.

---

## 3. THE EXISTING /ai-manager MODULE — what it is + the path to supersede it

`ai_manager/endpoints.py` mounts `app.include_router(router)` (caller.py:4616, `FEATURE_AI_MANAGER`, default
OFF) — a **plain include_router is SAFE** because every route derives tenant from `caller.resolve_tenant`,
NEVER a body field (unlike media-gen/booking/funnels which needed `build_router`). The **9 management routes**
(spec §7), all `prefix=/ai-manager`:

| Route | Auth | Purpose | State today |
|---|---|---|---|
| `GET /ai-manager/status` | manager+ | dormancy/config snapshot | LIVE (returns `enabled:false` until AIM_ENABLED) |
| `POST /ai-manager/numbers` | manager+ (`write`) | register a manager phone (+ dormant ownership OTP) | LIVE (OTP dormant) |
| `POST /ai-manager/numbers/{id}/verify` | manager+ | confirm ownership -> verified=True | LIVE (OTP check dormant) |
| `GET /ai-manager/numbers` | manager+ | list registered numbers + grants + status | LIVE |
| `GET /ai-manager/numbers/lookup?phone=` | **service token** | caller-ID resolution hop (voice worker) | DORMANT (401 until AIM_SERVICE_TOKEN) |
| `POST /ai-manager/numbers/{id}/grants` | admin + **step-up** | set per-number capability allow-list | LIVE (step-up via firewall) |
| `POST /ai-manager/numbers/{id}/revoke` | admin + **step-up** | revoke/lock a number | LIVE |
| `POST /ai-manager/sessions` | **service token** | voice worker ships a completed PIN-masked session | DORMANT |
| `GET /ai-manager/sessions` | manager+ | list recent sessions (transcripts, PIN masked) | LIVE |

**This IS the new service's management surface — it does NOT need superseding, it needs EXTENDING.** The
master spec's §10 API surface (`/profile`, `/authorized-users`, `/pin/*`, `/commands*`, `/dashboard/*`,
`/voice/*`, `/whatsapp/inbound`) is a SUPERSET. Path to evolve, additively:
1. **Activate**: `FEATURE_AI_MANAGER=1` + `AIM_ENABLED=1` + `AIM_SERVICE_TOKEN` (+ `AIWF_SERVICE_TOKEN` +
   `WORKFORCE_ENABLED=1` to light the execution catalog) in `.env` + restart `famit-caller`. Enroll a PIN
   (`PUT /firewall/pin`). Numbers register via the existing routes.
2. **Add the missing management routes** (`/ai-manager/profile`, `/authorized-users`, `/pin/set|reset`,
   `/commands` history, `/commands/test` = dashboard chat into the SAME `state_machine`, `/dashboard/summary`,
   `/audit-logs`, `/action-runs`) — additive to the SAME router, same `resolve_tenant`/`can` seam.
3. **Migrate JSONL -> `ai_manager_*` PG tables** with FORCED RLS (§2.5) when the spec's richer command/
   session/action_run models are needed (registry already keys by `tenant_id` so migration is mechanical).
4. **Wire the voice front** (`inbound_agent.py` LiveKit adapter -> `state_machine`) once a DID lands.
5. **Test Console FIRST** (spec §26): `POST /commands/test` driving the chat Transport into the live
   `state_machine` — proves the WHOLE spine (intent->permission->PIN->delegate->execute->audit) with no
   telephony. This already works offline (`run_command_offline` with a ScriptedTransport).

---

## 4. ACTIVATION / DORMANCY MATRIX (what flag lights what)

| Capability | Flag / env | Default | Effect when set |
|---|---|---|---|
| AI Manager router mounted | `FEATURE_AI_MANAGER=1` | OFF | 9 mgmt routes appear |
| AI Manager command center | `AIM_ENABLED=1` | OFF | engine active (else endpoints not_enabled posture) |
| Voice-worker service hop | `AIM_SERVICE_TOKEN=<rand>` | unset | `/numbers/lookup` + `POST /sessions` accept the worker |
| Workforce execution catalog | `WORKFORCE_ENABLED=1` + `AIWF_SERVICE_TOKEN` | OFF/unset | live catalog (real /api calls) vs StubTools |
| LLM intent parser | `AIM_LLM_PROVIDER=groq\|claude` + key | none (keyword stub) | LLM slot-fill (still no authorize) |
| OTP ownership verify | `AIM_OTP_PROVIDER=...` | none (spoken PIN) | OTP send/verify live |
| Inbound DID | `AIM_VOICE_DID` + `AIM_VOICE_SIP_TRUNK_ID` | unset | LiveKit inbound seam (FOUNDER BLOCKER) |
| Action firewall enforcement | `FIREWALL_ENABLED=1` | OFF | step-up actually enforced (else pass-through) |
| Kill-switch | `AIWF_KILLSWITCH=1` | OFF | halts ALL autonomous action |
| Loopback base | `AIWF_LOOPBACK_BASE` | `http://127.0.0.1:8209` | where catalog reaches caller.py |

---

## 5. GAPS — master-spec intents with NO execution adapter yet (the build list)

These §11 intent groups are NAMED in the spec but have NEITHER an `intent/driver.py` enum entry NOR a
`catalog.py` adapter. They PARK/clarify safely today (default-deny), so nothing is unsafe — they're just
not wired. Each needs: (a) a `COMMAND_INTENTS` enum entry, (b) a deterministic risk class in
`identity.py`, (c) a catalog adapter fn mapping to the REAL module route below, (d) a role in `delegate.py`.

| Gap intent group | Real endpoint to adapt to | Module status | Build note |
|---|---|---|---|
| `creative.generate_banner/video/brochure/pack` | `POST /media/video/jobs`, `POST /media/image/generate` | `media_gen` mounted, FEATURE_MEDIA off | async job: respond "started, will notify"; role `creative` |
| `workflow.create_draft/activate/pause/run_now` | `POST /workflows` (draft), `/{id}/publish`, `/{id}/run`, `/runs/{id}/approve` | `workflow` mounted, FEATURE_WORKFLOWS off | DRAFT first (never auto-activate); activate=step-up; role new `workflow`/`ops` |
| `booking.today/create/reschedule/cancel/reminder` | `GET /booking/availability`, `POST /booking/book`, `/{id}/reschedule\|cancel` | `booking` mounted, FEATURE_BOOKING off | booking is FREE (no step-up); role `booking` |
| `campaign.create_draft/launch/kill_losers/scale_winners` | `POST /campaigns` (draft), ads_engine `POST /ads/campaigns/propose\|{id}/approve\|{id}/pause\|optimize` | campaigns LIVE; ads_engine FEATURE_ADS off | launch=money gate; the catalog's `/ads/budget`/`/ads/pause` are PLACEHOLDER paths — real ads_engine routes differ |
| `billing.usage_today/usage_month/cost_breakdown/low_balance` | `GET /usage` (:3200), `GET /wallet` (:2206), `GET /billing/ledger` (:3293) | LIVE | add `wallet.read`/`usage.read` safe adapters |
| `lead.export`, `whatsapp.template_status`, `call.get_recording` | `/leads` export (TBD), WA template route (TBD), LiveKit Egress recording (deferred §4) | partial | export=destructive PIN; recording deferred |

**⚠ Catalog path mismatch to fix at wiring:** `catalog._ads_set_budget`/`_ads_pause` call `POST /ads/budget`
and `POST /ads/pause`, but the **real `ads_engine` routes are `/ads/campaigns/propose`, `/ads/campaigns/{id}/
approve`, `/ads/campaigns/{id}/pause`, `/ads/optimize`** (and only mount when FEATURE_ADS=1). The catalog
was written against placeholder paths; the ad adapter must be re-pointed to the real ads_engine surface (or
ads_engine must expose `/ads/budget`) before the ads intent group goes live. This is the one concrete
incorrectness in the otherwise-1:1 catalog.

---

## 6. SECURITY INVARIANTS ALREADY ENFORCED (do not regress; reuse, don't re-derive)

1. **Caller-ID is a HINT only** — `identity.resolve` returns a registered+verified+active number or None;
   the human is proven by a FRESH PIN (S2) BEFORE any business data is spoken.
2. **Every risky action gets its OWN fresh scoped step-up** (S6) — one login PIN can't authorize ten budget
   bumps. The runner's approval is **single-use, action+amount-bound** (`_match_approval`): kills replay,
   amount-escalation, tool-substitution.
3. **The LLM never authorizes** — `intent/driver.py` only fills slots over a CLOSED enum; risk is the
   DETERMINISTIC `identity.classify_risk` table; the runner re-runs `guardrails.check` (defense in depth).
   A model that self-labels its action "safe" is IGNORED.
4. **Tenant is ALWAYS token-derived** (`resolve_tenant`), never a body field — every catalog call re-auths
   AS the run's org under RLS via a per-run minted token.
5. **PIN never persisted/logged** — consumed in-memory, masked `****` in transcripts/sessions;
   `_sanitize_session` strips secret-shaped keys at the API box as defense in depth.
6. **Money fails CLOSED** — no wallet => block; daily_spend_cap + approval_threshold 0 => ALL external
   spend human-approved by default. **DND/window re-checked** on every recipient-touching action.
7. **Everything audited** to the immutable PG `events` leg with the verified tenant as actor.

---

## 7. KEY FILE INDEX (absolute box paths, for the builder)

- Control plane: `/opt/famit-agent/ai_manager/{state_machine,delegate,identity,registry,firewall_bridge,
  audit_bridge,config,endpoints}.py` + `intent/driver.py` + `otp/sender.py` + `inbound_agent.py` (stub).
- Execution engine: `/opt/famit-agent/workforce/{runner,guardrails,roles,policy,config}.py` +
  `tools/{catalog,stub_tools,transport}.py`.
- Foundation: `/opt/famit-agent/{firewall,wallet,audit,auth}.py`, `db/engine.py`, `caller.py` (resolve_tenant
  ~404, all /api routes), `agent.py` (voice).
- Modules to adapt: `/opt/famit-agent/{media_gen,workflow,booking,ads_engine}/`.
- STATE: `ai_manager/AI_MANAGER_STATE.md`, `workforce/WORKFORCE_STATE.md`.
- Build logs: `memory/build_log/wave-build-mod-ai-manager.md`, `wave-build-mod-ai-workforce.md`.
