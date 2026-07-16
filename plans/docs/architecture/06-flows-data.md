# 06 — End-to-End Flows & Data Model

> **Audience:** a new teammate (also on Claude Code) onboarding to Famit / Axcrio.
> **Scope:** the five load-bearing journeys as Mermaid **sequence diagrams**, plus the
> Postgres **data model** (per-module tables + RLS) as a Mermaid **erDiagram**.
> Every box/edge is grounded in real code (`file:line`). Diagrams render on GitHub.

**Ground-truth roots**
- Backend monolith: `caps/droplet_work/caller.py` (FastAPI, ~5,386 lines) + `agent.py` (LiveKit voice worker, ~874 lines) + per-module packages.
- Frontend: `caps/famit-panel` (Next.js). API base = `NEXT_PUBLIC_API_BASE || "/api"` → nginx → backend `:8209` (`famit-panel/lib/api.ts:2`).
- Future microservices monorepo (mostly scaffold today): `caps/growth-os` + `/contracts`.

**Live boxes**
| Box | priv IP | runs |
|---|---|---|
| backend `famit@168.144.153.145` | 10.122.0.4 | `famit-caller(:8209)`, `famit-agent` (voice), `famit-bridge`, `famit-aiasset(:8310)`, Postgres, LiveKit, Vobiz SIP |
| frontend `root@143.110.247.249` | 10.122.0.2 | `famit-panel(:3001)` + nginx |
| hatchet | 10.122.0.3 | `hatchet-lite` durable orchestration (F3) |

---

## 0. Service / box context map (who talks to whom)

```mermaid
graph LR
    subgraph FE["Frontend box (10.122.0.2)"]
        Panel["famit-panel :3001<br/>Next.js"]
        Nginx["nginx /api -> backend"]
    end
    subgraph BE["Backend box (10.122.0.4)"]
        Caller["caller.py :8209<br/>FastAPI monolith"]
        Agent["agent.py<br/>LiveKit voice worker 'capsy'"]
        AIAsset["ai_asset :8310<br/>Creative Studio service"]
        Bridge["famit-bridge<br/>CDR/usage join"]
        LK["LiveKit + Vobiz SIP"]
        PG[("Postgres<br/>RLS by app.tenant_id")]
    end
    Hatchet["hatchet-lite (10.122.0.3)<br/>durable jobs"]
    subgraph EXT["External vendors"]
        Meta["Meta WhatsApp Cloud API"]
        OR["OpenRouter<br/>gemini-2.5-flash-image"]
        Voice["Groq / Sarvam / ElevenLabs"]
        Spaces["DO Spaces"]
    end

    Panel -->|X-Auth token| Nginx --> Caller
    Caller --> PG
    Caller -->|create room + dispatch + SIP| LK
    LK --> Agent
    Agent -->|STT/LLM/TTS| Voice
    Agent -->|per-room transcript + usage files| Bridge
    Bridge --> Caller
    Caller -->|template send| Meta
    Caller -.proxy.-> AIAsset
    AIAsset --> OR
    AIAsset --> Spaces
    AIAsset --> PG
    Caller -.async actions.-> Hatchet
    AIAsset -.heavy render.-> Hatchet
```

The platform is a **modular monolith**: `caller.py` is the FastAPI app; every module
(`ai_manager`, `ai_asset`, `crm`, `booking`, `funnels`, `forms_surveys`, `payments`,
`support`, `workforce`, `whatsapp_builder`, `ads_engine`, `workflow-studio`, `kb`,
`lifecycle_segmentation`) is an import-safe package with its **own standalone SQL schema**
applied via a lazy `ensure_schema()` — deliberately **off** the P1 Alembic `0001/0002`
keystone chain so a module's blast radius never touches the live core migration
(`crm/schema.sql:6-13`, `ai_manager/schema.sql:6-11`, `ai_asset/schema.sql:6-10`).

---

## 1. The closed revenue loop (Ad → Lead → AI voice call → WhatsApp → appointment → revenue)

This is the macro journey; sections 2–5 zoom into the heavy legs.

```mermaid
sequenceDiagram
    autonumber
    actor Buyer as Prospect
    participant Ads as Meta Ads (ads_engine)
    participant Lead as leads (PG)
    participant Run as caller.py /run + run_job
    participant Agent as agent.py (voice)
    participant Fin as _finalize_call
    participant WA as WhatsApp (Meta)
    participant Book as booking
    participant CRM as contact_timeline (CRM)
    participant Rev as revenue / payments

    Buyer->>Ads: clicks ad / fills lead form
    Ads->>Lead: lead lands (form_submissions / leads upsert)
    Note over Run: tenant runs a campaign over those leads
    Run->>Agent: dial (LiveKit room + SIP) — see Flow 2
    Agent-->>Fin: per-room transcript + usage files
    Fin->>Fin: _charge_call (ledger + balance)
    Fin->>Lead: _update_lead_after_call (score/hot/status)
    Fin->>WA: _send_whatsapp / _wa_ai_followup (gated wa_followup)
    Fin->>CRM: timeline row (call) projected
    WA-->>Buyer: follow-up template / AI reply
    Buyer->>Book: books appointment (booking.core)
    Book->>CRM: timeline row (booking)
    Buyer->>Rev: pays (payments.payment_intents)
    Rev->>CRM: timeline row (purchase, amount/currency)
    Note over CRM: contact spine unifies every touch by canonical phone
```

**Anchors:** `_finalize_call` orchestrates the post-call fan-out
(`caller.py:1872`): charge (`_charge_call`), lead update (`_update_lead_after_call`
`caller.py:1273`), WhatsApp follow-up (`_send_whatsapp` `:1351`, `_wa_ai_followup` `:1600`,
gated by per-campaign `wa_followup` flag `:1421`), suppression on opt-out, callback retry
enqueue, and `call.completed` / `lead.qualified` webhooks. The **CRM contact spine**
(`crm/schema.sql:25` `contacts`, `:87` `contact_timeline`) is a read-model projection that
stitches calls/WA/bookings/payments by canonical phone — it is the loop's single pane of glass.

---

## 2. Run-a-Campaign → dial → agent.py voice → transcript / billing

```mermaid
sequenceDiagram
    autonumber
    actor User as Tenant (famit-panel)
    participant API as caller.py POST /run
    participant Job as run_job (asyncio task)
    participant LK as LiveKit API
    participant SIP as Vobiz SIP trunk
    participant Agent as agent.py entrypoint
    participant Vend as Groq/Sarvam/ElevenLabs
    participant Files as var/transcripts + usage_events_raw
    participant Fin as _finalize_call
    participant PG as PG (calls, ledger, usage_events)

    User->>API: POST /run (campaign_id, leads/CSV/XLSX, RC2 selectors)
    API->>API: resolve_tenant + can(write)
    API->>API: caps gate — monthly minutes, prepaid balance, concurrency clamp
    API->>Job: JOBS[job_id]=queued; asyncio.create_task(run_job)
    API-->>User: {job_id, count, suppressed_count, breakdown}
    loop dial loop (per lead, honouring window/caps/suppression)
        Job->>LK: create_room(name=famit-<num>-<rand>)
        Job->>LK: create_dispatch(agent_name="capsy", metadata={campaign_id,lead_name,variant})
        Job->>SIP: create_sip_participant(trunk, sip_call_to=num)
        Job->>PG: record_call(status="calling", sip_call_id)
        SIP-->>Agent: call answered -> job assigned to room
        Agent->>Agent: load campaign brain (build_system_prompt) + recap (cross-call memory)
        loop conversation turns
            Vend-->>Agent: STT (Sarvam) -> LLM (Groq) -> TTS (ElevenLabs)
        end
        Agent->>Files: write var/transcripts/<room>.json + usage_events_raw/<room>.json
        Job->>LK: _phone_present(room)? -> false when hung up
        Job->>Fin: _finalize_call(it, tenant, campaign)
        Fin->>PG: _charge_call (ledger + balance), record_call(done), usage fold
        Fin->>PG: _update_lead_after_call (score/hot/status)
        Fin-->>User: WhatsApp follow-up + webhooks (Flow 1)
    end
```

**Anchors:** `POST /run` (`caller.py:3071`) — gates: monthly-minutes cap `:3097`, prepaid
balance 402 `:3102`, RC2 composable audience selectors `:3113`, concurrency clamp `:3140`.
`run_job` dial loop (`caller.py:1971`): per-lead window/cap/suppression gates `:2004-2040`,
`create_room`/`create_dispatch`/`create_sip_participant` `:2056-2062`, `record_call` `:2073`.
`agent.py entrypoint` (`agent.py:419`): metadata parse `:427`, `build_system_prompt` from
campaign fields `:443`, cross-call recap `:466`, per-call vendor usage counters `:489`
(ElevenLabs chars, Groq tokens, Sarvam STT seconds). **Bridge:** agent writes per-room files
that `caller.py` folds into `usage_events.json` by joining on `room`
(`caller.py:1806-1825`), then the Vobiz CDR is joined into `cost_ledger.json`
(`caller.py:4542`). Voice plugins: `elevenlabs, groq, sarvam, silero` (`agent.py:23`) with
per-call Groq(6)/Sarvam(5) key round-robin (`agent.py:95-127`).

---

## 3. AI Manager command → NLU → PIN → execute → result

The AI Manager is a **dedicated command brain** with a strict, code-decided state machine
(`ai_manager/state_machine.py:3-5`): **S0 CONNECT → S1 VERIFY → S2 AUTHENTICATE → S3 CONTEXT
→ S4 CAPTURE INTENT → S5 PERMISSION → S6 STEP-UP → S7 CONFIRM → S8 DELEGATE+EXECUTE → S9
REPORT**. Invariant: *the LLM only fills slots; it never authorizes* (`:5`).

```mermaid
sequenceDiagram
    autonumber
    actor Mgr as Authorized manager (voice/WA/dashboard)
    participant SM as CommandMachine (state_machine.py)
    participant ID as identity (caller-ID -> authorized_users)
    participant NLU as nlu / intent (slot fill)
    participant FW as firewall (PIN/OTP step-up)
    participant Del as delegate.execute
    participant Mod as target module (campaigns/ads/leads/wa/workflows)
    participant DB as ai_manager_* (PG, immutable audit)

    Mgr->>SM: S0 connect (channel=phone|whatsapp|dashboard)
    SM->>ID: S1 verify caller-ID (HINT only)
    SM->>FW: S2 authenticate human — fresh PIN/OTP (anti-spoof)
    FW-->>SM: ok (lockout after N fails, per number)
    SM->>Del: S3 read_context (read-only business state)
    loop S4..S9 command loop
        Mgr->>NLU: utterance
        NLU-->>SM: intent + slots (match)
        SM->>SM: S5 map_intent_to_action -> tool + risk; permits(role,grants,tool)?
        alt not permitted
            SM->>DB: command status=denied + audit(permission_denied)
        else permitted
            SM->>DB: create_command (vendor_id, idempotency_key UNIQUE)
            opt risky action (S6 STEP-UP, fresh + scoped)
                SM->>FW: per-action PIN; on fail -> cancel this command
            end
            SM->>Mgr: S7 CONFIRM (amount read back)
            Mgr-->>SM: "yes"
            SM->>DB: status=executing; create_action_run
            SM->>Del: S8 execute(action, step_up_token) — runner re-enforces caps/kill-switch
            Del->>Mod: side effect (campaigns.run / ads.set_budget / ...)
            Mod-->>Del: status="done" (ground truth)
            SM->>DB: finish_action_run + command succeeded/failed + immutable audit_log
            SM->>Mgr: S9 report result
        end
    end
```

**Anchors:** `CommandMachine.run` / `_run_inner` (`state_machine.py:122,139`); S1 verify
`:146-158`, S2 authenticate `:170-177`, S3 `read_context` `:178`. Command loop S5–S9
(`:205-300`): `map_intent_to_action` `:206`, `is_risky` `:209`, idempotency key + `create_command`
`:214-219`, `permits()` deny path `:221-230`, S6 step-up `:235-251`, S7 confirm-with-readback
`:253-267`, S8 `create_action_run` + `delegate.execute` + `executed = status=="done"` ground
truth `:270-297`. Persistence/security: 7 `ai_manager_*` tables (`ai_manager/schema.sql`),
`(vendor_id, idempotency_key)` UNIQUE = **no double-execute** (`:128`), `ai_manager_audit_logs`
**IMMUTABLE** via REVOKE UPDATE/DELETE (`:266-273`). Per-user PIN = Argon2id, never raw (`:61`).
Profile gates: `require_pin_for_level`, `daily/monthly_spend_limit`, calling-window
(`schema.sql:34-40`). HTTP surface = `ai_manager` router (`endpoints.py:343`, prefix
`/ai-manager`, **defined-not-mounted** — FE calls it directly per `_lib.ts:5-9`).

---

## 4. Creative Studio generate → AI Asset service → banner → Spaces

```mermaid
sequenceDiagram
    autonumber
    actor User as Tenant (Creative Studio UI)
    participant API as ai_asset POST /generate
    participant Sub as jobs.submit
    participant Wal as wallet (hold)
    participant Job as ai_asset_generation_jobs (PG)
    participant Run as jobs._run (inline or Hatchet)
    participant Pipe as pipeline.generate
    participant OR as OpenRouter (gemini-2.5-flash-image)
    participant Ver as ai_asset_versions + Spaces/box-fs
    participant Score as creative score

    User->>API: POST /generate (platform,type,count,instruction,model,campaign_id)
    API->>Sub: submit(vendor_id, context, spec, idempotency_key)
    Sub->>Job: insert job (idempotency UNIQUE -> retry = SAME job)
    Sub->>Wal: reserve hold (est_cost_minor); insufficient -> over_budget (no silent render)
    Sub->>Run: _enqueue (Hatchet if AIASSET_HATCHET_HOST_PORT else inline)
    Note over Run: phase: queued->reading_campaign->building_prompts->rendering->scoring->storing->done
    Run->>Pipe: generate(context, spec)
    Pipe->>Pipe: stage 1 build prompts (brand kit + campaign ctx)
    Pipe->>OR: stage 2 render each variant (router picks openrouter)
    OR-->>Pipe: banner bytes
    Run->>Ver: store immutable version (local | DO Spaces); URL + sha256 + dims
    Run->>Score: creative score per version (rule/llm)
    Run->>Wal: settle hold (actual_cost_minor) or release on fail
    Run->>Job: state=succeeded; n_succeeded
    User->>API: GET /jobs/{id}/stream (poll/SSE) -> assets in library
    User->>API: POST /assets/{id}/attach-whatsapp (-> ai_asset_usage)
```

**Anchors:** routes (`ai_asset/endpoints.py`): `/generate` `:107`, `/jobs/{id}` `:144`,
`/jobs/{id}/stream` `:154`, `/assets` `:181`, `/assets/{id}/raw` `:207`, `/edit` `:230`,
`/regenerate` `:234`, `/approve|reject` `:265-269`, `/attach-whatsapp` `:344`,
`/variation-from-upload` `:315`, `/brand-kits` `:349`. `jobs.submit` `:77` (idempotency
`:89`, hold/over_budget `:106`), `_enqueue` Hatchet-vs-inline `:152-161`, `_run` with
idempotent re-entry guard `:186-194`. `pipeline.generate` stage-1 prompts + stage-2
OpenRouter render `:39-150`. **Money lives in `wallet.py` (integer paise), never float**;
large binaries go to **box-fs / DO Spaces**, never PG — only URL + metadata persist
(`ai_asset/schema.sql:15-16`). 8 `ai_asset_*` tables; versions are immutable (regen/edit =
new version, original never overwritten — `schema.sql:133-159`).

---

## 5. Control Layer entitlement check (admin toggle → /me/entitlements → middleware HIDE/LOCK)

```mermaid
sequenceDiagram
    autonumber
    actor Admin as Super-admin
    participant AdminAPI as caller.py /admin/* (role-gated)
    participant Ent as entitlements.py
    participant PG as control tables (PG)
    actor Tenant as Tenant (famit-panel)
    participant ME as GET /me/entitlements
    participant MW as _enforce_entitlement_mw
    participant Route as governed route

    Admin->>AdminAPI: toggle feature (set_override / set_plan / set_status)
    AdminAPI->>Ent: set_override(tenant, feature_key, mode)
    Ent->>PG: write tenant_entitlements + entitlement_audit + bump_version
    Note over PG: events ledger (channel="control") = tamper-proof source of truth

    Tenant->>ME: GET /me/entitlements (If-None-Match: ent-version)
    ME->>Ent: entitlements_payload(tenant) {modes,status,plan,version}
    Ent-->>Tenant: 200 {modes...} OR 304 (version unchanged) — FE HIDEs nav items
    Note over ME: CORE route — bypasses enforcement (anti-lockout)

    Tenant->>MW: request to a governed route
    MW->>MW: CONTROL_ENABLED? path -> feature_key (longest-prefix)
    MW->>MW: is_core? -> pass (login/settings/wallet-pay never hidden)
    MW->>Ent: evaluate(tenant, feature_key)
    alt mode == hidden
        MW-->>Tenant: 404 not_found (no existence leak)
    else mode == locked
        MW-->>Tenant: 402 {locked, upgrade:true}
    else mode == on
        MW->>Route: proceed
    end
```

**Resolution layering** (`entitlements.resolve_modes` `:288`): per-tenant override
(`tenant_entitlements`) > plan (`plan_entitlements`) > global default
(`feature_registry.default_mode`), cached by `(tenant_id, ent_version)` and invalidated by
`bump_version` `:426` on any control write. **Anchors:** middleware `_enforce_entitlement_mw`
(`caller.py:366`): master gate off = byte-identical passthrough `:374`, path→key `:386`,
core floor `:392`, tenant from TOKEN `:401`, admin bypass `:412`, `evaluate` `:414`,
HIDDEN→404 `:422` / LOCKED→402 `:424`, **fail-closed** on post-key error `:418`.
`/me/entitlements` (`caller.py:3919`) is ETag/304 + a **core route that bypasses the
choke-point** (anti-lockout). DDL (`control/db/ddl_control.sql`): global catalog
`feature_registry/plans/plan_entitlements/plan_limits` (**no RLS**, admin-only writes),
tenant-scoped `tenant_entitlements` + `tenant_status` (**FORCE-RLS**), `entitlement_audit`
mirror of the immutable PG `events` leg.

---

## 6. The Postgres data model (RLS-isolated)

**Tenancy invariant.** `caller.py:resolve_tenant` (`:551`) resolves the tenant from the
**auth token, never the request body**. Every per-op DB session does
`SET LOCAL app.tenant_id = <tenant>` (and `app.is_admin='1'` for admin ops) via
`db/engine.py session()`. Every tenant-scoped table has the **same admin-GUC FORCE-RLS
policy**:
`USING (current_setting('app.is_admin')='1' OR <key> = current_setting('app.tenant_id'))`
(`db/ddl_wallet.sql:94-117`, `crm/schema.sql:46-53`, `ai_manager/schema.sql:197-258`, …).
`famit_app` is `NOSUPERUSER/NOBYPASSRLS`, so FORCE binds even the table owner. The tenant
key column is `org_id` in the P1 core + CRM and `tenant_id`/`vendor_id` in the standalone
modules — all bound to the **same** `app.tenant_id` GUC.

### 6a. Core OLTP + billing + audit (`db/models.py` — 17 RLS tables on the Alembic chain)

```mermaid
erDiagram
    ORGS ||--o{ USERS : has
    ORGS ||--o{ MEMBERSHIPS : has
    ORGS ||--o{ CAMPAIGNS : owns
    ORGS ||--o{ LEADS : owns
    CAMPAIGNS ||--o{ CALLS : produces
    LEADS ||--o{ CALLS : "dialed as"
    CALLS ||--o{ LEDGER : "billed by"
    CALLS ||--o{ USAGE_EVENTS : "metered by"
    CALLS ||--o{ COST_LEDGER : "costed by"
    ORGS ||--o{ SUPPRESSION : "DNC list"
    ORGS ||--o{ RETRY_QUEUE : "callbacks"
    ORGS ||--o{ WEBHOOKS : "fan-out"
    ORGS ||--o{ WA_THREADS : "wa convos"
    ORGS ||--|| BILLING : "plan+balance"
    ORGS ||--o{ EVENTS : "immutable audit"

    ORGS { text id PK "==tenant_id" }
    USERS { text id PK "org_id, email, role, is_admin" }
    CAMPAIGNS { text id PK "org_id, name, voice_id, fields jsonb, system_prompt" }
    LEADS { text id PK "org_id, phone UQ, status, score, hot, last_outcome" }
    CALLS { text id PK "org_id, campaign_id, phone, outcome, answered, interest, room, sip_call_id, duration_s" }
    BILLING { text org_id PK "plan, rate_per_min, balance, included_minutes" }
    LEDGER { text id PK "org_id, call_id, cost, outcome, at" }
    USAGE_EVENTS { text id PK "org_id, call_id, room, vendor, units, cost" }
    COST_LEDGER { text id PK "org_id, call_id, total_cost, by_vendor jsonb" }
    EVENTS { text id PK "org_id, actor, action, object_type, channel, at — sha256(line)" }
```

The 17 RLS tables list is the authoritative `RLS_TABLES` (`db/models.py:355-360`):
`orgs, users, memberships, campaigns, leads, calls, suppression, retry_queue, webhooks,
webhook_log, wa_log, wa_threads, billing, ledger, usage_events, cost_ledger, events`.
`events` is the **immutable cross-module audit ledger** (PG leg, not JSONL) — every module's
`audit.record(channel=...)` lands here.

### 6b. Money — wallet (integer paise, ACID) (`db/ddl_wallet.sql`)

```mermaid
erDiagram
    WALLET_ACCOUNTS ||--o{ WALLET_TRANSACTIONS : "append-only trail"
    WALLET_ACCOUNTS ||--o{ WALLET_HOLDS : "open reservations"
    WALLET_HOLDS ||--o| WALLET_TRANSACTIONS : "settle/release"
    WALLET_IDEMPOTENCY }o--|| WALLET_ACCOUNTS : "safe retry"

    WALLET_ACCOUNTS { text tenant_id PK "currency PK, available_minor, held_minor, lifetime_*" }
    WALLET_TRANSACTIONS { bigserial id PK "tenant_id, kind, amount_minor, held_delta_minor, balance_after_minor" }
    WALLET_HOLDS { bigserial id PK "tenant_id, amount_minor, state, resource_type, resource_id, expires_at" }
    WALLET_IDEMPOTENCY { text idem_key PK "tenant_id, op, result jsonb" }
```

Money is **BIGINT minor units (paise), never float**. Invariant (proven in
`tests/test_wallet_concurrency.py`): `available_minor + held_minor == SUM(amount_minor)`
(`ddl_wallet.sql:46-50`). A `hold` is net-zero to total; `charge` removes spent amount.
This is the single wallet that the AI Asset job hold, WhatsApp-AI bundle hold, and ads-engine
hold all reserve against (note: prepaid `billing.balance` ≠ `wallet_accounts` — separate
balances by plan).

### 6c. AI Manager (`ai_manager/schema.sql` — 7 tables, vendor_id RLS)

```mermaid
erDiagram
    AI_MANAGER_PROFILES ||--o{ AI_MANAGER_AUTHORIZED_USERS : "who may command"
    AI_MANAGER_PROFILES ||--o{ AI_MANAGER_SESSIONS : "voice/WA/chat"
    AI_MANAGER_SESSIONS ||--o{ AI_MANAGER_COMMANDS : "S12 lifecycle"
    AI_MANAGER_COMMANDS ||--o{ AI_MANAGER_ACTION_RUNS : "dispatched exec"
    AI_MANAGER_COMMANDS ||--o{ AI_MANAGER_AUDIT_LOGS : "immutable trail"
    AI_MANAGER_COMMANDS }o--|| AI_MANAGER_IDEMPOTENCY : "no double-execute"

    AI_MANAGER_PROFILES { text id PK "vendor_id UQ, enabled, require_pin_for_level, daily_spend_limit, call window" }
    AI_MANAGER_AUTHORIZED_USERS { text id PK "vendor_id, normalized_phone UQ, role, pin_hash(argon2id), locked_until" }
    AI_MANAGER_SESSIONS { text id PK "vendor_id, channel, caller_phone(masked), transcript_text" }
    AI_MANAGER_COMMANDS { text id PK "vendor_id, detected_intent, action_type, risk_level, status, idempotency_key" }
    AI_MANAGER_ACTION_RUNS { text id PK "vendor_id, command_id, target_module, status, job_id(hatchet)" }
    AI_MANAGER_AUDIT_LOGS { text id PK "vendor_id, event_type, severity — INSERT/SELECT-only" }
    AI_MANAGER_IDEMPOTENCY { text vendor_id PK "key PK, status, result jsonb" }
```

### 6d. Creative / AI Asset (`ai_asset/schema.sql` — 8 tables + registry)

```mermaid
erDiagram
    AI_ASSET_PROVIDERS }o--o{ AI_ASSET_VERSIONS : "model used"
    AI_ASSET_BRAND_KITS ||--o{ AI_ASSET_GENERATION_JOBS : "brand memory"
    AI_ASSET_GENERATION_JOBS ||--o{ AI_ASSET_ASSETS : "produces"
    AI_ASSET_ASSETS ||--o{ AI_ASSET_VERSIONS : "immutable history"
    AI_ASSET_VERSIONS ||--o{ AI_ASSET_CREATIVE_SCORES : "scored"
    AI_ASSET_ASSETS ||--o{ AI_ASSET_USAGE : "used in WA/ads/workflow"
    AI_ASSET_GENERATION_JOBS }o--|| AI_ASSET_IDEMPOTENCY : "no double-submit"

    AI_ASSET_PROVIDERS { text provider_id PK "model_id PK, capabilities, cost_minor — GLOBAL, read-all" }
    AI_ASSET_BRAND_KITS { text id PK "vendor_id, palette, fonts, tone, do_not_use" }
    AI_ASSET_GENERATION_JOBS { text id PK "vendor_id, request, state, phase, hold_id, est/actual_cost_minor, idem UQ" }
    AI_ASSET_ASSETS { text id PK "vendor_id, campaign_id, kind, platform, current_version_id, status, metrics" }
    AI_ASSET_VERSIONS { text id PK "asset_id, version_no UQ, provider/model, url(spaces), sha256, dims" }
    AI_ASSET_CREATIVE_SCORES { text id PK "version_id, scores jsonb, overall" }
    AI_ASSET_USAGE { text id PK "asset_id, channel(whatsapp/meta_ads/workflow), ref_id, metrics" }
```

### 6e. AI WhatsApp builder (`whatsapp_builder/db/ddl_ai_wa.sql` — 4 tables, tenant_id RLS)

```mermaid
erDiagram
    AI_WA_SUGGESTION_BUNDLES ||--o{ AI_WA_TEMPLATES : "generation run"
    AI_WA_TEMPLATES ||--o{ AI_WA_VARIATIONS : "angle alternatives"
    AI_WA_TEMPLATES ||--o{ AI_WA_PERSONALIZATION : "{{n}} token plan"

    AI_WA_SUGGESTION_BUNDLES { text bundle_id PK "tenant_id, campaign_id, model, credit_hold_id" }
    AI_WA_TEMPLATES { text template_id PK "tenant_id, name, category, header/body/buttons jsonb, status, meta_template_id" }
    AI_WA_VARIATIONS { text variation_id PK "tenant_id, template_id, angle, body_text({{n}}), cta_text" }
    AI_WA_PERSONALIZATION { text plan_id PK "tenant_id, template_id, position, token, lead_field, fallback" }
```

### 6f. Control / entitlements (`control/db/ddl_control.sql`)

```mermaid
erDiagram
    FEATURE_REGISTRY ||--o{ PLAN_ENTITLEMENTS : "overridden per plan"
    PLANS ||--o{ PLAN_ENTITLEMENTS : "bundles"
    PLANS ||--o{ PLAN_LIMITS : "caps"
    FEATURE_REGISTRY ||--o{ TENANT_ENTITLEMENTS : "per-vendor override"
    TENANT_STATUS }o--|| PLANS : "assigned plan"
    TENANT_STATUS ||--o{ ENTITLEMENT_AUDIT : "control actions"

    FEATURE_REGISTRY { text key PK "kind, nav_href, api_prefixes, default_mode(on/hidden/locked), is_core — GLOBAL no-RLS" }
    PLANS { text plan_id PK "is_default — GLOBAL no-RLS" }
    PLAN_ENTITLEMENTS { text plan_id PK "feature_key PK, mode" }
    PLAN_LIMITS { text plan_id PK "limit_key PK, value" }
    TENANT_ENTITLEMENTS { text tenant_id PK "feature_key PK, mode, set_by — FORCE-RLS" }
    TENANT_STATUS { text tenant_id PK "status, plan_id, ent_version(real-time invalidation) — FORCE-RLS" }
    ENTITLEMENT_AUDIT { bigserial id PK "actor_user, action, target_tenant — mirror of events leg" }
```

### 6g. CRM person-spine + the rest (per-module standalone schemas)

```mermaid
erDiagram
    CONTACTS ||--o{ CONTACT_IDENTITY : "aliases (phone/email/ext)"
    CONTACTS ||--o{ CONTACT_TIMELINE : "unified history"
    CONTACTS { text id PK "org_id, phone_key UQ, stage(derived), score(mirror leads), consent_call/wa" }
    CONTACT_IDENTITY { text org_id PK "kind PK, value PK, contact_id" }
    CONTACT_TIMELINE { text id PK "org_id, contact_id, kind(call/whatsapp/booking/purchase), amount, at" }
```

**Other module tables (all FORCE-RLS, standalone schemas, same admin-GUC policy):**

| Module | File | Tables |
|---|---|---|
| Booking | `booking/models.py` + `booking/rls.sql` | `booking_resources, bookings, booking_reminders, booking_reminder_fires, booking_events` |
| Funnels | `funnels/schema.sql` | `funnels` |
| Forms/Surveys | `forms-surveys/schema.sql` | `forms, form_submissions` |
| Payments | `payments/schema.sql` | `payment_intents, payment_events, payment_followups` |
| Support | `support/schema.sql` + `support/rls.sql` | `support_tickets, support_messages` |
| Ads Engine | `ads_engine/schema.sql` | `ads_campaigns` (provider meta/google, wallet_hold_id, daily/lifetime caps) |
| Workforce | `workforce/schema.sql` | `agent_runs, agent_steps, agent_approvals, agent_tool_grants, agent_roles` |
| Lifecycle / Segmentation | `lifecycle_segmentation/schema.sql` | `segments, segment_members, lifecycle_rules, lifecycle_fires` |
| Knowledge Base (RAG) | `kb/schema.sql` | `kb_sources, kb_documents, kb_chunks` |
| Workflow Studio | `workflow-studio/workflow/schema.sql` | `wf_definitions, wf_versions, wf_runs, wf_node_runs, wf_triggers, wf_schedules` |

The CRM `contacts` table is a **PG-native projection** (like `kb_chunks`/`wallet_accounts`),
not a JSON-mirror store — truth stays reconstructable from `leads + calls + wa_threads`
(`crm/schema.sql:16-18`). The `ads_campaigns.wallet_hold_id` and `ai_wa_*.credit_hold_id`
columns are the cross-module edges into the single **wallet** (6b).

---

## 7. How a request flows top-to-bottom (the choke points to remember)

```mermaid
graph TD
    Req["HTTP request (famit-panel -> /api)"] --> RL["P0 rate-limit MW (fail-open)"]
    RL --> ENT["_enforce_entitlement_mw (Control, fail-closed)"]
    ENT -->|hidden->404 / locked->402| Block["blocked"]
    ENT -->|on / ungoverned| RT["route handler"]
    RT --> TEN["resolve_tenant (from TOKEN, never body)"]
    TEN --> CAN["can(tenant, 'write'/'read') role gate"]
    CAN --> SESS["db.engine.session(SET LOCAL app.tenant_id)"]
    SESS --> RLS["Postgres FORCE-RLS policy enforces isolation"]
    RT -.money.-> WAL["wallet hold/settle (idempotent, paise)"]
    RT -.audit.-> EV["audit.record -> events ledger (immutable)"]
```

This is the spine every module rides: **rate-limit → entitlement → tenant-from-token →
role → RLS session → (wallet + immutable audit)**. New modules plug in by registering a
`feature_registry` key, exposing a router, applying a standalone `ensure_schema()`, and
reusing `wallet.py` / `audit.py` / `firewall.py` rather than re-implementing money, audit,
or step-up.
