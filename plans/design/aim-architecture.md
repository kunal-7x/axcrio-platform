# AI Manager — DEDICATED SERVICE Architecture + DB Schema (`aim-architecture.md`)

> **Wave role:** SERVICE ARCHITECTURE + DB SCHEMA. READ-ONLY DESIGN — this file is the
> single source of truth for the dedicated AI Manager service. No app code edited, no deploy, no git.
> **Conforms to:** `AI_MANAGER_MASTER_PROMPT.md` (28-section founder spec) — §8 DB models,
> §9 service decomposition, §10 APIs, §11 intents, §12 lifecycle, §6 risk L0–L4, §7 security, §20 multi-tenancy.
> **Supersedes-by-absorption:** the in-process `droplet_work/ai_manager/` module + `design/platform-ai-manager.md`
> (those treat AIM as a thin in-process front-door; the founder/orchestrator DECISION is a dedicated SERVICE).
> **Reuses, never rebuilds:** `db.engine` GUC/RLS, `firewall.py`, `wallet.py`, `audit.py`, Hatchet (F3),
> the voice stack, the monolith `/api`. Verified against live source on disk 2026-06-10.

---

## 0. GROUND TRUTH (cited; do not trust memory)

| Asset | Path / fact | How the new service uses it |
|---|---|---|
| Monolith API spine | `caller.py` `:8209`, header `X-Auth`, token-derived tenant (`resolve_tenant`) | The service **calls it over the network** to execute every real action (campaigns/leads/run/whatsapp/wallet/…). |
| RLS pattern | `db/rls.sql` L26-36 — admin-GUC policy `current_setting('app.is_admin')='1' OR <scope>=current_setting('app.tenant_id')`, FORCE RLS, `famit_app` NOSUPERUSER/NOBYPASSRLS | **Copied verbatim** for every `ai_manager_*` table (scope col = `vendor_id`). |
| Schema posture | `crm/schema.sql`, `db/ddl_wallet.sql` — standalone `IF NOT EXISTS` DDL applied as `famit_app` via lazy `ensure_schema()`, NOT an Alembic revision (off the live P1 0001/0002 chain) | `ai_manager/schema.sql` follows this exact posture (own schema namespace `ai_manager_*`). |
| GUC session | `db/engine.py` `session(tenant_id, is_admin)` / `asession(...)` — `SET LOCAL app.tenant_id/app.is_admin` inside the txn (PgBouncer-safe) | The service's own DB layer mirrors this contract for its own engine. |
| Idempotency table | `wallet_idempotency` (`db/ddl_wallet.sql` L86-92) — PK idem_key, stored `result` JSONB replayed | `ai_manager_idempotency` is the identical shape; +`ai_manager_commands.idempotency_key` UNIQUE. |
| Action Firewall | `firewall.py` — `set_pin/check_pin/has_pin` (salted-hash `var/pins.json`), `mint_step_up(tenant,scope)`/`verify_step_up_token(token,scope,sub)` (HS256, sub-bound), `classify(action)`, `require_step_up` | **The PIN/step-up engine.** Reused via a thin AuthService adapter (see §3.5, §6 deploy note on shared-lib vs HTTP). |
| Wallet ledger | `wallet.py` — `reserve(...)→hold_id`, `settle(hold_id,actual)`, `release(hold_id)`, `balance()`, `topup()` — INTEGER paise, ACID, idempotent, no-double-spend PROVEN | **CostGuard** reserves/settles via these (over `/api/wallet*` network calls, never re-implements money math). |
| Immutable audit | `audit.py` — `record(actor,action,object_type,object_id,...,meta)` append-only JSONL + PG `events` leg, never raises; `tail(action_prefix)` | AuditService writes `ai_manager.*` events here **and** the local `ai_manager_audit_logs` table (dual: cross-module trail + tenant-scoped queryable history). |
| Existing in-process AIM | `droplet_work/ai_manager/` — `registry.py` (numbers), `identity.py` (`canonical_phone`), `state_machine.py`, `intent/driver.py`, `otp/`, `endpoints.py` (9 routes, mounted in caller.py, dormant) | **Absorbed**: `canonical_phone`, number-registry logic, the offline state-machine tests, the intent driver, OTP sender are MOVED/PORTED into the service. caller.py's `/ai-manager/*` becomes a **dumb nginx proxy** to the service (see §1.4 cutover). |
| Hatchet F3 | `infra/hatchet/hello_world.py` pattern (`hatchet.workflow`, `@wf.task`, `worker.start()`); engine `famit-hatchet` priv `10.122.0.3:7077`, token on box | **action_runs** = Hatchet workflows; the service is a Hatchet **client+worker** for long-running/async execution. |
| Voice stack | `agent.py` (LiveKit + Sarvam STT + Groq LLM + Sarvam TTS), trunk `ST_fmtVmNJmpzKa`, SIP | VoiceSessionService registers a SECOND LiveKit worker persona ("manager") + inbound webhook → service. |

**Net architecture in one line:** a standalone FastAPI app (`/opt/famit-aimanager/`, own venv, own port `:8290`,
own systemd unit `famit-aimanager`, own Postgres schema `ai_manager_*` FORCE-RLS) that owns the
**understand→verify→authorize→execute→audit** brain and **calls the monolith `/api` over the VPC** to do the work.
Co-located on the backend box NOW (droplet limit 3/3); extractable to its own droplet by changing two env URLs.

---

## 1. PROCESS / DEPLOY MODEL

### 1.1 Where it runs (now vs later)
- **NOW (co-located):** new dir `/opt/famit-aimanager/` on the backend box `168.144.153.145`, **own venv**
  `/opt/famit-aimanager/.venv` (NOT the caller venv — independent dependency set: fastapi, uvicorn,
  sqlalchemy, psycopg2, httpx, hatchet-sdk, pydantic, pyjwt). Listens on **`127.0.0.1:8290`** (localhost-only;
  never world-exposed). Talks to its **own Postgres schema** in the SAME PG cluster the monolith uses
  (separate logical namespace `ai_manager_*`, same `famit_app` role + RLS) — no second DB server now.
- **LATER (extracted):** copy `/opt/famit-aimanager/` to a new droplet, point `AIM_MONOLITH_BASE_URL`
  at the backend box's private IP and `AIM_PG_DSN` at the shared/managed PG. **Zero code change** — only
  three env values move (monolith URL, PG DSN, Hatchet host). The service was network-call-only from day one.

### 1.2 systemd unit (`/etc/systemd/system/famit-aimanager.service`)
```ini
[Unit]
Description=Famit AI Manager (dedicated command-brain service)
After=network-online.target postgresql.service
[Service]
User=famit
WorkingDirectory=/opt/famit-aimanager
EnvironmentFile=/opt/famit-aimanager/.env
ExecStart=/opt/famit-aimanager/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8290 --workers 2
Restart=on-failure
RestartSec=3
[Install]
WantedBy=multi-user.target
```
A SECOND unit `famit-aimanager-worker.service` runs the Hatchet worker
(`ExecStart=…/.venv/bin/python -m app.workers.hatchet_worker`) — the async executor (see §4).
A THIRD (deferred, dormant) unit `famit-aimanager-voice.service` runs the LiveKit manager-persona worker (§3.6).

### 1.3 How the service authenticates to the monolith `/api`
- Reuses the EXISTING **`AIM_SERVICE_TOKEN`** (already generated in `/opt/famit-agent/.env` per the
  activation wave). Every outbound call to `caller.py` carries `Authorization: Bearer <AIM_SERVICE_TOKEN>`.
- **Tenant impersonation, the safe way:** the service never invents identity. For a verified caller it asks
  the monolith to mint a **short-lived tenant access token** (the monolith's `auth.issue_pair(tenant)` via a
  new thin `POST /api/internal/mint-scoped-token` that ONLY the service token may call), then executes each
  module action **as that tenant token** (`X-Auth: <tenant_token>`). The monolith's own RLS + `resolve_tenant`
  then enforce tenant scope on the EXECUTING side too — defense in depth (master spec §20). The service token
  is reserved only for the mint hop + the caller-ID lookup hop; it is NEVER used to execute a vendor action.
- **Mutual constraint:** the service is localhost/VPC-only; the monolith's ufw already allows `:8209` only
  from the VPC. No new public surface.

### 1.4 How the panel reaches the service (nginx proxy + cutover of the old `/ai-manager`)
- New nginx location on the frontend box vhost:
  `location /api/ai-manager/ { proxy_pass http://<backend-priv-ip>:8290/; proxy_set_header X-Auth $http_x_auth; … }`
  — the panel calls `/api/ai-manager/*` exactly like every other `/api/*` route; nginx routes THIS prefix to
  the new service instead of `caller.py`. The panel keeps sending the same `X-Auth` tenant token; the service
  validates it by calling the monolith `GET /api/me` (or verifying the HMAC token shape locally with the shared SECRET).
- **Cutover of the dormant in-process module:** caller.py currently mounts `ai_manager.endpoints` at
  `/ai-manager/*`. Once the service is live, the nginx `/api/ai-manager/` location wins (it never reaches
  caller.py), so the in-process router becomes dead weight — left mounted but unreached, removed in a later
  caller.py cleanup unit. **No flag flip on caller.py is needed to cut over; it's an nginx routing change.**
  The service IMPORTS/PORTS the in-process module's pure logic (registry, identity, state-machine, intent) so
  nothing is lost.

### 1.5 Resting state / flag gate (ships dormant + safe) — see §7
- The whole service is gated by `AIM_ENABLED` (default `0`). When `0`: the service still starts and serves
  `GET /ai-manager/status` (returns `{"enabled":false,...}`) and `GET /health`, but **every command/execute
  endpoint returns `{"status":"not_configured","enabled":false}` 200** and performs **zero** side effects.
- nginx need not even route to it until the founder enables — i.e. shipping the unit + schema is safe because
  nothing calls it. Activation = `AIM_ENABLED=1` + creds (DID, Hatchet token) + nginx location reload.

---

## 2. DATABASE SCHEMA — `ai_manager_*` (FORCE RLS by `vendor_id`)

> **Posture:** standalone `ai_manager/schema.sql`, applied as `famit_app` via lazy `ensure_schema()`
> (mirrors `crm/schema.sql` + `wallet_*`). **NOT** an Alembic revision — kept off the live P1 chain.
> Every table: `vendor_id text NOT NULL` (== the existing tenant/org id), `ENABLE`+`FORCE ROW LEVEL SECURITY`,
> the **identical admin-GUC isolation policy** from `db/rls.sql`. Money never lives here (wallet owns it).
> Raw PIN never lives here (firewall `var/pins.json` owns the salted hash). 6 spec tables + 1 idempotency.

### 2.1 `ai_manager/schema.sql` (CREATE TABLE)
```sql
-- ai_manager/schema.sql — dedicated AI Manager service schema. Additive, idempotent, famit_app-owned.
-- Posture: applied standalone (IF NOT EXISTS) via aim.db.ensure_schema(), NOT an Alembic revision —
-- off the live P1 0001/0002 migration chain (same as crm/schema.sql, db/ddl_wallet.sql).
-- RLS shape == db/rls.sql (admin-GUC OR vendor_id match), scope column = vendor_id. FORCE RLS binds owner.

-- 8.1 profiles — one row per vendor: AIM config, spend caps, calling-window, PIN policy.
CREATE TABLE IF NOT EXISTS ai_manager_profiles (
    id                          text PRIMARY KEY,                 -- aimp_<sha1(vendor)[:16]>
    vendor_id                   text NOT NULL,
    enabled                     boolean NOT NULL DEFAULT false,
    ai_manager_phone_number     text NOT NULL DEFAULT '',         -- the inbound DID this vendor's managers dial
    language_preference         text NOT NULL DEFAULT 'hinglish',
    default_voice_provider      text NOT NULL DEFAULT 'sarvam',
    require_pin_for_level        integer NOT NULL DEFAULT 3,       -- risk level at/above which PIN is mandatory (L3 default)
    daily_spend_limit_minor      bigint  NOT NULL DEFAULT 0,       -- paise; 0 = use plan default
    monthly_spend_limit_minor    bigint  NOT NULL DEFAULT 0,
    max_bulk_leads_without_pin   integer NOT NULL DEFAULT 0,
    allowed_call_start_time      text NOT NULL DEFAULT '09:00',    -- IST HH:MM
    allowed_call_end_time        text NOT NULL DEFAULT '21:00',
    timezone                     text NOT NULL DEFAULT 'Asia/Kolkata',
    created_at                   timestamptz NOT NULL DEFAULT now(),
    updated_at                   timestamptz NOT NULL DEFAULT now(),
    UNIQUE (vendor_id)
);

-- 8.2 authorized_users — who may command AIM for a vendor (multiple managers/phones). PIN HASH is NOT here
-- (firewall var/pins.json holds the salted hash, keyed by vendor+user); pin_set_at/failed/lock are metadata.
CREATE TABLE IF NOT EXISTS ai_manager_authorized_users (
    id                      text PRIMARY KEY,                     -- aimu_<rand>
    vendor_id               text NOT NULL,
    user_id                 text NOT NULL DEFAULT '',             -- optional link to platform user
    name                    text NOT NULL DEFAULT '',
    phone_number            text NOT NULL DEFAULT '',
    normalized_phone_number text NOT NULL DEFAULT '',             -- canonical_phone() 91XXXXXXXXXX (caller-ID match key)
    role                    text NOT NULL DEFAULT 'manager',      -- admin|manager|operator|viewer
    permissions             jsonb NOT NULL DEFAULT '{}',          -- per-action allow-list / grants
    is_active               boolean NOT NULL DEFAULT true,
    pin_set                 boolean NOT NULL DEFAULT false,       -- mirror flag; raw/hash NEVER stored here
    pin_set_at              timestamptz,
    failed_pin_attempts     integer NOT NULL DEFAULT 0,
    locked_until            timestamptz,
    last_used_at            timestamptz,
    created_at              timestamptz NOT NULL DEFAULT now(),
    updated_at              timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS aim_users_vendor_norm_idx ON ai_manager_authorized_users (vendor_id, normalized_phone_number);
CREATE INDEX IF NOT EXISTS aim_users_vendor_active_idx ON ai_manager_authorized_users (vendor_id, is_active);

-- 8.3 sessions — one inbound voice/chat/whatsapp conversation.
CREATE TABLE IF NOT EXISTS ai_manager_sessions (
    id                text PRIMARY KEY,                           -- aims_<rand>
    vendor_id         text NOT NULL,
    user_id           text NOT NULL DEFAULT '',                   -- authorized_users.id once identified
    channel           text NOT NULL DEFAULT 'phone',              -- phone|whatsapp|dashboard
    provider_call_id  text NOT NULL DEFAULT '',                   -- LiveKit room / SIP call id
    caller_phone      text NOT NULL DEFAULT '',
    status            text NOT NULL DEFAULT 'active',             -- active|completed|failed|blocked
    started_at        timestamptz NOT NULL DEFAULT now(),
    ended_at          timestamptz,
    transcript_text   text NOT NULL DEFAULT '',                   -- full transcript (PIN/OTP masked before write)
    stt_provider      text NOT NULL DEFAULT '',
    tts_provider      text NOT NULL DEFAULT '',
    llm_provider      text NOT NULL DEFAULT '',
    metadata          jsonb NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS aim_sessions_vendor_time_idx ON ai_manager_sessions (vendor_id, started_at DESC);

-- 8.4 commands — one parsed instruction inside a session. The lifecycle row (§12).
CREATE TABLE IF NOT EXISTS ai_manager_commands (
    id                    text PRIMARY KEY,                       -- aimc_<rand>
    session_id            text NOT NULL DEFAULT '',
    vendor_id             text NOT NULL,
    user_id               text NOT NULL DEFAULT '',
    raw_text              text NOT NULL DEFAULT '',
    normalized_text       text NOT NULL DEFAULT '',
    detected_intent       text NOT NULL DEFAULT '',               -- e.g. campaign.update_budget (§11)
    action_type           text NOT NULL DEFAULT '',               -- the executor verb (maps to a module adapter)
    action_payload        jsonb NOT NULL DEFAULT '{}',
    risk_level            integer NOT NULL DEFAULT 0,             -- 0..4 (§6)
    status                text NOT NULL DEFAULT 'pending',        -- pending|needs_confirmation|needs_pin|executing|succeeded|failed|denied|cancelled
    confirmation_required boolean NOT NULL DEFAULT false,
    confirmation_status   text NOT NULL DEFAULT '',               -- ''|confirmed|rejected
    pin_required          boolean NOT NULL DEFAULT false,
    pin_verified          boolean NOT NULL DEFAULT false,
    permission_result     jsonb NOT NULL DEFAULT '{}',            -- policy-engine verdict {allow,reason,caps,...}
    cost_estimate         jsonb NOT NULL DEFAULT '{}',            -- {minor, currency, basis}
    execution_result      jsonb NOT NULL DEFAULT '{}',
    error_message         text NOT NULL DEFAULT '',
    idempotency_key       text NOT NULL DEFAULT '',               -- UNIQUE per vendor (see partial index)
    created_at            timestamptz NOT NULL DEFAULT now(),
    updated_at            timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS aim_cmd_session_idx ON ai_manager_commands (vendor_id, session_id, created_at);
CREATE INDEX IF NOT EXISTS aim_cmd_status_idx  ON ai_manager_commands (vendor_id, status);
-- idempotency: a given (vendor, key) executes ONCE. Partial so blank keys don't collide.
CREATE UNIQUE INDEX IF NOT EXISTS aim_cmd_idem_uq ON ai_manager_commands (vendor_id, idempotency_key)
    WHERE idempotency_key <> '';

-- 8.5 audit_logs — IMMUTABLE per-vendor event trail (mirrors cross-module audit.py events; queryable here).
CREATE TABLE IF NOT EXISTS ai_manager_audit_logs (
    id          bigserial PRIMARY KEY,
    vendor_id   text NOT NULL,
    user_id     text NOT NULL DEFAULT '',
    session_id  text NOT NULL DEFAULT '',
    command_id  text NOT NULL DEFAULT '',
    event_type  text NOT NULL DEFAULT '',                        -- ai_manager.command.received|risk.classified|pin.fail|executed|denied|...
    severity    text NOT NULL DEFAULT 'info',                    -- info|warn|error|critical
    message     text NOT NULL DEFAULT '',
    metadata    jsonb NOT NULL DEFAULT '{}',                     -- NEVER raw pin/otp/secret (scrubbed at write)
    created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS aim_audit_vendor_time_idx ON ai_manager_audit_logs (vendor_id, created_at DESC);
CREATE INDEX IF NOT EXISTS aim_audit_command_idx     ON ai_manager_audit_logs (vendor_id, command_id);
-- IMMUTABILITY: famit_app gets SELECT+INSERT only (no UPDATE/DELETE grant) on this table (see grants block).

-- 8.6 action_runs — async/long-running executions (Hatchet-backed). One per dispatched job (§4).
CREATE TABLE IF NOT EXISTS ai_manager_action_runs (
    id            text PRIMARY KEY,                               -- aimr_<rand>
    command_id    text NOT NULL DEFAULT '',
    vendor_id     text NOT NULL,
    action_type   text NOT NULL DEFAULT '',
    target_module text NOT NULL DEFAULT '',                      -- campaigns|leads|calls|whatsapp|creative|workflow|ads|analytics
    status        text NOT NULL DEFAULT 'queued',                -- queued|running|succeeded|failed|retried|cancelled
    job_id        text NOT NULL DEFAULT '',                      -- Hatchet workflow run id
    input         jsonb NOT NULL DEFAULT '{}',
    output        jsonb NOT NULL DEFAULT '{}',
    error         jsonb NOT NULL DEFAULT '{}',
    started_at    timestamptz,
    completed_at  timestamptz,
    created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS aim_runs_vendor_status_idx ON ai_manager_action_runs (vendor_id, status, created_at DESC);
CREATE INDEX IF NOT EXISTS aim_runs_command_idx        ON ai_manager_action_runs (vendor_id, command_id);

-- 8.7 idempotency — generic op-level idempotency (reserve/settle/execute replay), shape == wallet_idempotency.
CREATE TABLE IF NOT EXISTS ai_manager_idempotency (
    idem_key    text PRIMARY KEY,                                -- e.g. "execute:cmd:<command_id>"
    vendor_id   text NOT NULL,
    op          text NOT NULL,                                  -- execute | reserve | settle | dispatch
    result      jsonb NOT NULL,                                 -- stored response to replay
    created_at  timestamptz NOT NULL DEFAULT now()
);
```

### 2.2 `ai_manager/rls.sql` (FORCE RLS + grants — IDENTICAL admin-GUC shape as `db/rls.sql`)
```sql
-- ai_manager/rls.sql — FORCE RLS by vendor_id on every ai_manager_* table. admin-GUC escape hatch
-- (current_setting('app.is_admin')='1') so an admin op can act cross-vendor in-txn with no superuser conn.
-- Re-runnable (drop-then-create). Applied by ensure_schema() right after schema.sql, as famit_app.
DO $rls$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY[
    'ai_manager_profiles','ai_manager_authorized_users','ai_manager_sessions',
    'ai_manager_commands','ai_manager_audit_logs','ai_manager_action_runs','ai_manager_idempotency'
  ] LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY;', t);
    EXECUTE format('ALTER TABLE %I FORCE  ROW LEVEL SECURITY;', t);
    EXECUTE format('DROP POLICY IF EXISTS %1$s_isolation ON %1$I;', t);
    EXECUTE format($f$
      CREATE POLICY %1$s_isolation ON %1$I
      USING (
        current_setting('app.is_admin', true) = '1'
        OR vendor_id = current_setting('app.tenant_id', true)
      )
      WITH CHECK (
        current_setting('app.is_admin', true) = '1'
        OR vendor_id = current_setting('app.tenant_id', true)
      );
    $f$, t);
  END LOOP;
END $rls$;

-- grants: famit_app owns the tables. Most get full DML; audit_logs is INSERT/SELECT ONLY (immutability).
GRANT SELECT, INSERT, UPDATE, DELETE ON
    ai_manager_profiles, ai_manager_authorized_users, ai_manager_sessions,
    ai_manager_commands, ai_manager_action_runs, ai_manager_idempotency TO famit_app;
GRANT SELECT, INSERT ON ai_manager_audit_logs TO famit_app;   -- NO update/delete => append-only
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO famit_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO famit_app;
```

**Tenant-isolation invariant (master spec §20, tested):** every service DB call opens `db.session(vendor_id=…)`
which `SET LOCAL app.tenant_id`; FORCE RLS hides every other vendor's rows. A forged `vendor_id` in a request
body is IGNORED — the vendor is always derived from the authenticated token. Cross-vendor probe (auth as A,
forge B) → 0 rows, on BOTH the service tables AND the monolith side (because we execute as a scoped tenant token).

---

## 3. SERVICE DECOMPOSITION (master spec §9) — file layout + interfaces

### 3.1 File skeleton (`/opt/famit-aimanager/`)
```
/opt/famit-aimanager/
  app/
    main.py                 # FastAPI app factory; mounts routers; AIM_ENABLED gate; ensure_schema() on startup
    config.py               # env reader (dormant-until-key pattern); URLs/tokens; never raises at import
    db/
      engine.py             # own SQLAlchemy engine + session(vendor_id,is_admin) GUC ctx (mirrors monolith db.engine)
      schema.sql            # §2.1 CREATE TABLE
      rls.sql               # §2.2 FORCE RLS + grants
      bootstrap.py          # ensure_schema(): apply schema.sql + rls.sql idempotently as famit_app
      repo.py               # typed CRUD over ai_manager_* (profiles/users/sessions/commands/runs/audit) — all vendor-scoped
    engine/
      command_engine.py     # AIManagerCommandEngine — the orchestrator (§12 lifecycle)
      nlu.py                # AIManagerNLU — text+context -> strict JSON (§22 schema), provider-agnostic
      policy.py             # AIManagerPolicyEngine — permissions, risk rules, spend caps, compliance, blocked-actions
      auth_service.py       # AIManagerAuthService — caller-ID match, phone-normalize, PIN verify (firewall), lockout
      router_exec.py        # AIManagerExecutionRouter — dispatch to module adapters
      cost_guard.py         # AIManagerCostGuard — estimate -> reserve(hold) -> settle/release (wallet)
      audit_service.py      # AIManagerAuditService — dual write: audit.py events + ai_manager_audit_logs
    adapters/
      __init__.py           # ModuleAdapter ABC + REGISTRY
      monolith_client.py    # httpx client to caller.py /api (service token + scoped tenant token); retries; timeouts
      campaigns.py leads.py calls.py whatsapp.py creative.py workflow.py ads.py analytics.py billing.py booking.py support.py
    providers/
      llm.py                # LLMProvider ABC + GroqLLM + MockLLM (dev/no-key)
      stt.py tts.py         # STTProvider/TTSProvider ABC + SarvamSTT/SarvamTTS + Mock
      telephony.py          # TelephonyProvider ABC + LiveKitSIP + Mock
    voice/
      session_service.py    # AIManagerVoiceSessionService — inbound webhook, session lifecycle, streaming events
      manager_agent.py      # LiveKit "manager" persona worker entrypoint (DEFERRED/dormant; own systemd unit)
    workers/
      hatchet_worker.py     # registers AIM workflows; worker.start() (async executor, §4)
      workflows.py          # the Hatchet workflow + task defs (bulk_call, send_report, creative_pack, ...)
    api/
      profile.py users.py pin.py sessions.py commands.py execution.py webhooks_voice.py webhooks_wa.py dashboard.py
    identity.py             # canonical_phone() etc. (ported from ai_manager/identity.py)
    nlu_prompt.py           # the §22 NLU system prompt (strict-JSON, never-execute)
  tests/
    test_phone_norm.py test_caller_match.py test_pin_lockout.py test_risk_classify.py test_nlu_json.py
    test_policy_caps.py test_tenant_isolation.py test_idempotent_exec.py test_offline_lifecycle.py
  .env  .venv/  requirements.txt
  systemd/ famit-aimanager.service  famit-aimanager-worker.service  famit-aimanager-voice.service
```

### 3.2 AIManagerCommandEngine (`engine/command_engine.py`) — orchestrator
```python
class CommandEngine:
    def __init__(self, repo, nlu, policy, auth, router, cost, audit): ...
    async def run_command(self, *, identity: Identity, session_id: str, raw_text: str,
                          channel: str, idempotency_key: str = "") -> CommandResult:
        # the full §12 lifecycle (see §5). Returns {command_id, status, user_facing_summary, needs:{confirm|pin}}.
    async def confirm(self, command_id, identity) -> CommandResult        # advances a needs_confirmation cmd
    async def submit_pin(self, command_id, identity, pin) -> CommandResult # verifies via auth_service, advances
    async def cancel(self, command_id, identity) -> CommandResult
    async def execute(self, command_id, identity) -> CommandResult        # terminal dispatch (router/cost/audit)
```
Channel-agnostic: voice/chat/whatsapp are thin adapters that build an `Identity` + `raw_text` and call this.

### 3.3 AIManagerNLU (`engine/nlu.py`)
```python
class NLU:
    def __init__(self, llm: LLMProvider): ...
    async def parse(self, *, raw_text: str, context: VendorContext) -> NLUResult
    # context = {active_campaigns[], recent_leads[], available_modules[], vendor_policy}
    # NLUResult = strict JSON (§22): {intent, action_type, confidence, risk_level, requires_confirmation,
    #   requires_pin, entities{}, missing_fields[], assumptions[], user_facing_summary,
    #   safe_to_execute:false, block_reason|null}. Output is VALIDATED against a pydantic schema; a parse
    #   failure -> safe_to_execute=false + block_reason="llm_parse_failure" (never executes on bad JSON).
```
Provider-agnostic (reuses the Groq abstraction); `MockLLM` returns deterministic JSON keyed on keywords so
offline acceptance runs with zero keys (ports `ai_manager/intent/driver.py`'s keyword matcher as the mock).

### 3.4 AIManagerPolicyEngine (`engine/policy.py`)
```python
class PolicyEngine:
    def evaluate(self, *, identity, nlu: NLUResult, profile: Profile,
                 cost_estimate: CostEstimate | None) -> PolicyVerdict
    # PolicyVerdict = {allow:bool, reason, risk_level(final), confirmation_required, pin_required,
    #   blocked(bool), block_reason, caps:{daily,monthly,bulk}, compliance:{window_ok,dnd_ok,consent_ok}}
```
Deterministic. Holds: role→permission map, vendor policy (`require_pin_for_level`, spend caps, bulk thresholds,
calling window), L0–L4 risk rules, L4 blocked-action set (delete vendor, reveal secrets/keys/PIN, bypass DND/STOP,
spend>limit, transfer ownership, disable audit). **NLU risk is advisory; policy is authoritative** (never trust
the LLM — master spec §22, §27). PIN requirement = `final_risk >= profile.require_pin_for_level`.

### 3.5 AIManagerAuthService (`engine/auth_service.py`)
```python
class AuthService:
    def identify_caller(self, caller_phone, channel) -> Identity | None  # canonical_phone -> authorized_users match
    def normalize(self, phone) -> str                                    # ports identity.canonical_phone
    def verify_pin(self, identity, pin) -> PinResult                     # -> firewall.check_pin + lockout bookkeeping
    def is_locked(self, identity) -> bool
    def mint_scoped_tenant_token(self, identity) -> str                  # monolith POST /api/internal/mint-scoped-token
```
**PIN reuse:** delegates to `firewall.check_pin(vendor_id, pin)` / `firewall.has_pin` / `firewall.set_pin`
(co-located → direct import of the monolith's `firewall.py` as a shared lib; extracted → a thin
`POST /api/firewall/verify-pin` network call — **interface identical**, see §6 deploy note). Lockout
(`failed_pin_attempts`, `locked_until`) is tracked in `ai_manager_authorized_users` + reuses `ratelimit.py`.
**Never stores/logs raw PIN.** Step-up token minted via `firewall.mint_step_up(vendor_id, scope)` and attached
to the executing action so the monolith re-verifies (defense in depth).

### 3.6 AIManagerVoiceSessionService (`voice/session_service.py`) + `voice/manager_agent.py`
```python
class VoiceSessionService:
    async def on_inbound(self, webhook) -> dict     # SIP/LiveKit inbound -> create ai_manager_sessions row, identify caller
    async def on_event(self, event) -> dict         # streaming STT partials/finals -> feed CommandEngine
    async def on_status(self, status) -> dict        # ringing/answered/ended
    async def on_recording(self, rec) -> dict
    async def finalize(self, session_id) -> dict     # save masked transcript, status=completed
```
Reuses LiveKit + Sarvam STT/Groq/Sarvam TTS via the `providers/` ABCs; `manager_agent.py` registers a SECOND
LiveKit worker `agent_name="manager"` (the outbound telecaller `capsy` persona is untouched). **DEFERRED/dormant**
(own systemd unit, off until the inbound DID lands). The COMMAND core is reachable via chat/test-console with zero telephony.

### 3.7 AIManagerExecutionRouter (`engine/router_exec.py`) + adapters
```python
class ExecutionRouter:
    async def route(self, *, command, identity, scoped_token) -> ExecResult
    # action_type -> ModuleAdapter; sync adapters execute inline, long-running ones create an action_run (Hatchet, §4)
```
Each adapter implements the `ModuleAdapter` ABC (§5) and calls `monolith_client` against the real `/api`.

### 3.8 AIManagerCostGuard (`engine/cost_guard.py`)
```python
class CostGuard:
    def estimate(self, action_type, payload) -> CostEstimate            # deterministic per-action pricing
    async def reserve(self, vendor_id, estimate, resource) -> Hold      # wallet.reserve (via /api/wallet)
    async def settle(self, hold, actual_minor) -> None                  # wallet.settle
    async def release(self, hold, reason) -> None                       # wallet.release on fail
```
Branches on plan: **prepaid (billing.balance) vs prepaid_wallet (wallet_accounts) are SEPARATE balances — never
summed** (per the F4 wallet learning). Reserve BEFORE execute; settle actual after; release on failure.

### 3.9 AIManagerAuditService (`engine/audit_service.py`)
Dual write: (a) `audit.record(actor=vendor:user, action="ai_manager.<event>", object_type, object_id, meta)` →
the cross-module immutable trail; (b) `repo.append_audit(...)` → `ai_manager_audit_logs` (tenant-scoped, queryable
for the Command-History/Session-Detail UI). Both scrub secret-shaped keys (`pin/otp/secret/code/token`) before write.

---

## 4. ASYNC / LONG-RUNNING via Hatchet (reuse F3) — `action_runs`

- Long-running/bulk/idempotent-retry actions (bulk call queue, send-report, creative pack, kill-losers across many
  campaigns, bulk WhatsApp) are NOT executed inline. The ExecutionRouter creates an `ai_manager_action_runs` row
  (`status=queued`) and **triggers a Hatchet workflow** (the service is a Hatchet client; `AIM_HATCHET_HOST_PORT`
  → `10.122.0.3:7077`, token on box, `TLS_STRATEGY=none`).
- `workers/workflows.py` defines one workflow per long-running action (pattern from `hello_world.py`):
  ```python
  bulk_call_wf = hatchet.workflow(name="aim-bulk-call", input_validator=BulkCallInput)
  @bulk_call_wf.task()
  def dispatch(input, ctx):   # calls monolith /api/run with scoped token; updates action_run via repo
  ```
- `workers/hatchet_worker.py` registers all AIM workflows and runs the worker (own systemd unit). On task
  start/finish it updates the `ai_manager_action_runs` row (`running→succeeded/failed`, `job_id`, `output/error`,
  `started_at/completed_at`). Durable: a worker crash resumes from Hatchet's Postgres broker (F3 proven durable).
- The dashboard `GET /ai-manager/action-runs` reads these rows; the voice/chat reply for an async action is
  *"started, X queued, I'll notify when done"* (master spec §16/§18 behavior).
- **Resting state:** if Hatchet env is unset, `route` falls back to a bounded inline executor for small jobs and
  marks large jobs `status=failed, error={not_configured: hatchet}` — never blocks, never crashes.

---

## 5. PROVIDER-AGNOSTIC ADAPTER INTERFACES (master spec rule 13/14)

### 5.1 `ModuleAdapter` ABC (`adapters/__init__.py`)
```python
class ModuleAdapter(ABC):
    module: str                          # "campaigns" | "leads" | ...
    actions: set[str]                    # action_types it handles (subset of §11 taxonomy)
    is_async: bool = False               # True => route via Hatchet action_run
    @abstractmethod
    def estimate_cost(self, action_type, payload) -> CostEstimate: ...
    @abstractmethod
    async def execute(self, *, action_type, payload, scoped_token, idem_key) -> ExecResult: ...
    # ExecResult = {ok, resource_ids[], summary, provider_response_summary, actual_cost_minor|None, error|None}
```
Every adapter calls `monolith_client` → the real `/api` (campaigns→`POST /api/campaigns`,
leads/call→`POST /api/run`, whatsapp→`/api/whatsapp/*`, analytics→`GET /api/analytics`, etc. — the §10 mapping).
A missing module/cred → adapter returns `{ok:false, error:{status:"not_configured"}}` (clean interface, NO fake
business logic — rule 14). A `MockAdapter` set backs offline tests.

### 5.2 Provider ABCs (`providers/`)
```python
class LLMProvider(ABC):   async def complete(self, *, system, user, schema=None) -> str
class STTProvider(ABC):   async def stream(self, audio) -> AsyncIterator[Transcript]
class TTSProvider(ABC):   async def synthesize(self, text, voice) -> bytes
class TelephonyProvider(ABC):  async def answer/hangup/transfer(...)
```
Concrete: `GroqLLM`, `SarvamSTT`, `SarvamTTS`, `LiveKitSIP` — each `is_configured()` gated; `Mock*` for
dev/no-key. Selection via `config.py` env (`AIM_LLM_PROVIDER`, `AIM_STT_PROVIDER`, …). Same dormant-until-key
shape as `whatsapp.py`/`vendors/embeddings.py` (never raises at import).

---

## 6. COMMAND LIFECYCLE (master spec §12) — as code flow

`CommandEngine.run_command()` executes, persisting state to `ai_manager_commands` at EVERY hop:
1. **receive** → create `ai_manager_sessions` row (if new) + `ai_manager_commands` row (`status=pending`); audit `command.received`.
2. **identify** → `AuthService.identify_caller(caller_phone)`; unknown → `status=denied`, audit `caller.unknown`, speak "cannot identify". (Known: pin scoped tenant token.)
3. **parse intent** → `NLU.parse(raw_text, context)` → fill `detected_intent/action_type/action_payload/entities/risk(advisory)`; bad JSON → denied.
4. **policy** → `PolicyEngine.evaluate()` → authoritative `risk_level`, `confirmation_required`, `pin_required`, blocked? L4 blocked → `status=denied`, audit `blocked`, speak refusal.
5. **estimate cost** (if billable) → `CostGuard.estimate()` → `cost_estimate`; insufficient balance → denied with "low balance".
6. **confirm** (if required) → `status=needs_confirmation`; speak summary "should I continue?"; wait for `confirm()`.
7. **PIN** (if required) → `status=needs_pin`; speak "apna PIN boliye"; on `submit_pin()` → `AuthService.verify_pin()` → wrong/locked → audit `pin.fail`, **never** reveal data, deny; right → `pin_verified=true` + mint step-up.
8. **reserve** → `CostGuard.reserve()` → wallet hold (idempotent on `idem_key`).
9. **create action_run** → if `adapter.is_async`: `ai_manager_action_runs` row + Hatchet trigger; else inline.
10. **execute** → `ExecutionRouter.route()` → adapter → `/api` with scoped token; `status=executing→succeeded/failed`.
11. **settle/release** → success: `CostGuard.settle(actual)`; failure: `CostGuard.release()`.
12. **audit + respond** → write `execution_result`, audit `executed`/`failed`, speak short summary.

**Idempotency:** step 1 enforces `(vendor_id, idempotency_key)` UNIQUE → a replayed command returns the stored
result (no double-execute, no double-spend) — same guarantee as `wallet_idempotency`. **No action bypasses this chain.**

> **Deploy note (shared-lib NOW vs network LATER) — the only co-location coupling:** while co-located, AuthService/
> CostGuard/AuditService reuse `firewall.py`/`wallet.py`/`audit.py` by **direct import** (same box, same venv-visible
> path or a `sys.path` add to `/opt/famit-agent`). On extraction these three become **network calls** to the
> already-existing monolith routes (`/api/firewall/verify-pin`, `/api/wallet/*`, `/api/audit`) — the AuthService/
> CostGuard/AuditService method signatures are written to be transport-agnostic (a `_mode = "lib"|"http"` switch in
> `config.py`), so extraction flips one env value, not the call sites. Everything ELSE (module execution) is HTTP
> from day one.

---

## 7. RESTING STATE / FLAG GATE (ships dormant + safe)

- `AIM_ENABLED=0` default. Service starts, `ensure_schema()` runs (idempotent, additive — only creates
  `ai_manager_*` tables, touches nothing live), `/health` + `/ai-manager/status` answer, every command/execute
  endpoint short-circuits to `{"status":"not_configured","enabled":false}` with **zero** side effects.
- Schema apply is gated too: `ensure_schema()` is a no-op unless `AIM_PG_DSN` is set AND `db.available()`.
- Voice worker + Hatchet worker are SEPARATE systemd units, installed `disabled` — they don't run until enabled.
- nginx `/api/ai-manager/` location is added but can be left commented until cutover. **Until the founder sets
  `AIM_ENABLED=1` + pastes the DID/Hatchet token + reloads nginx, the live platform is byte-for-byte unchanged.**
- Per-vendor double gate: even with `AIM_ENABLED=1`, a vendor's `ai_manager_profiles.enabled=false` → that
  vendor's AIM is off. Founder rolls it out vendor-by-vendor.

---

## 8. API SURFACE (master spec §10) — served by the service under the `/ai-manager` prefix

`GET/PUT /profile` · `GET/POST /authorized-users` · `PATCH/DELETE /authorized-users/:id` ·
`POST /pin/set|verify|reset/request|reset/confirm` (never returns raw) ·
`GET /sessions|/sessions/:id|/commands|/commands/:id` · `POST /commands/test` (dashboard chat → same engine) ·
`POST /commands/:id/confirm|/cancel|/execute` ·
`POST /voice/inbound|/voice/events|/voice/status|/voice/recording` (signature-verified webhooks) ·
`POST /whatsapp/inbound|/whatsapp/status` ·
`GET /dashboard/summary|/audit-logs|/action-runs` · `GET /status` · `GET /health`.
All vendor-scoped from the token; webhooks are service-token + signature verified; PIN endpoints never expose raw.

---

## 9. CRASH-SAFE BUILD UNITS (C-A1 … C-A14) — model + order

> Each unit is ONE verifiable deliverable with its own test, committed before the next (per the crash-safe
> protocol). Order respects dependencies; the SAFETY machinery (schema/RLS, auth, policy) lands before any
> real execution; the live platform stays untouched until C-A14 wiring.

| Unit | Deliverable | Verify (test) | Model |
|---|---|---|---|
| **C-A1** | Package skeleton: `/opt/famit-aimanager/` dir, `app/main.py` factory + `AIM_ENABLED` gate, `config.py` (dormant-until-key), venv + requirements, 3 systemd unit files, `/health`+`/status`. | service boots; `/health`=200; `/status` `{enabled:false}`; no live touch. | sonnet |
| **C-A2** | `db/schema.sql` (§2.1) + `db/rls.sql` (§2.2) + `db/engine.py` (own engine, GUC session) + `db/bootstrap.ensure_schema()`. | apply on a scratch PG → 7 tables, FORCE RLS on all, audit_logs INSERT/SELECT-only; re-run = no-op. | sonnet |
| **C-A3** | `db/repo.py` typed vendor-scoped CRUD over all 7 tables (every read/write opens `session(vendor_id)`). | `test_tenant_isolation.py`: auth A, forge B → 0 rows both ways. | sonnet |
| **C-A4** | `identity.py` (port `canonical_phone`) + `engine/auth_service.py` caller-ID match + lockout (NO PIN yet). | `test_phone_norm.py` (+91/raw-10/91 collapse), `test_caller_match.py`, unknown-caller→None. | sonnet |
| **C-A5** | PIN/lockout in AuthService via `firewall.py` (lib mode) + lockout bookkeeping in `authorized_users`. | `test_pin_lockout.py`: hash verify, wrong-PIN increments, lock after N, never logs raw. | sonnet |
| **C-A6** | `providers/llm.py` (ABC + GroqLLM + MockLLM) + `nlu_prompt.py` (§22) + `engine/nlu.py` (strict-JSON validate). | `test_nlu_json.py`: schema valid; bad JSON → safe_to_execute=false; mock deterministic, zero keys. | sonnet |
| **C-A7** | `engine/policy.py` — role/risk/caps/compliance/blocked-set; PIN-by-level; L4 refuse. | `test_risk_classify.py` + `test_policy_caps.py`: money/bulk/export→L3+, secrets/DND→blocked. | **opus** (risk matrix correctness) |
| **C-A8** | `engine/cost_guard.py` — estimate + reserve/settle/release via `wallet.py` (lib) ; prepaid-vs-wallet branch. | reserve→hold, settle actual, release on fail; idempotent; no double-spend (reuse wallet proof harness). | sonnet |
| **C-A9** | `adapters/` ABC + `monolith_client.py` (service token + scoped tenant token mint) + analytics+leads+campaigns adapters (the safe/common ones first). | mock `/api` → adapters call right routes; `not_configured` clean on missing module. | sonnet |
| **C-A10** | `engine/audit_service.py` (dual write, secret-scrub) + `engine/command_engine.py` (full §6 lifecycle) + `test_offline_lifecycle.py` + `test_idempotent_exec.py`. | offline: receive→identify→parse→policy→confirm→pin→execute→audit deterministic, zero net; replay = once. | **opus** (orchestrator) |
| **C-A11** | `api/*` routers (profile/users/pin/sessions/commands/execution/dashboard) + Test Console endpoint `POST /commands/test`. | each route vendor-scoped; PIN never raw; dashboard chat drives the real engine. | sonnet |
| **C-A12** | `workers/workflows.py` + `workers/hatchet_worker.py` + async adapters (bulk_call/send_report/creative_pack) → `action_runs`. | Hatchet trigger updates run row queued→succeeded; worker crash resumes (F3 durable); dormant if unset. | sonnet |
| **C-A13** | `voice/session_service.py` + `voice/manager_agent.py` (LiveKit "manager" persona) + voice/wa webhooks (signature-verified). | inbound webhook → session+identify; manager worker registers (2nd persona, telecaller untouched); dormant unit. | **opus** (voice safety + barge-in) |
| **C-A14** | Wiring + cutover (un-applied diffs): systemd install, nginx `/api/ai-manager/`→`:8290`, monolith `POST /api/internal/mint-scoped-token` (service-token only), retire in-process `ai_manager/` router. Founder HOWTO (DID, Hatchet token, `AIM_ENABLED=1`). | staged diffs; with `AIM_ENABLED=0` live platform byte-identical; enable → real call test. | **opus** (live wiring) |

**Build-unit count: 14** (C-A1 … C-A14). Safety-first ordering: schema/RLS/isolation (C-A2/3) and
auth/PIN/policy (C-A4/5/7) precede any real execution; nothing touches the live platform until C-A14, which
ships as un-applied diffs + a founder HOWTO and stays dormant behind `AIM_ENABLED`.

---

## 10. TABLE LIST (7)
`ai_manager_profiles` · `ai_manager_authorized_users` · `ai_manager_sessions` · `ai_manager_commands` ·
`ai_manager_audit_logs` (immutable, INSERT/SELECT-only) · `ai_manager_action_runs` (Hatchet-backed) ·
`ai_manager_idempotency`. All FORCE-RLS by `vendor_id` (admin-GUC escape hatch).

## 11. OPEN FORKS (founder-side / later waves, recorded — not blocking design)
- Inbound **DID/phone number** on VoBiz/SIP (blocks live Flow-1 voice; chat/test-console works without it).
- **Hatchet cross-box reachability** (open `hatchet-fw` tcp/7077 from backend box priv IP + set
  `SERVER_GRPC_BROADCAST_ADDRESS=10.122.0.3:7077`) — needed before the worker connects from the backend box.
- **DO droplet limit (3/3)** — blocks true extraction to its own box; co-located until raised.
- **Reasoning LLM key** (paid Groq/Cerebras) for NLU latency — dormant MockLLM until set.
- WhatsApp Cloud API creds (WA channel + send-report) — dormant until set.
```
