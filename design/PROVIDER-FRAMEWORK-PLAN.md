# 🔌 PROVIDER-FRAMEWORK-PLAN.md — the Universal Flexible Provider / Connector Registry (the 100% design)

> READ-ONLY DESIGN. NO box mutation, NO caller.py/agent.py edit by this pass. The ONLY writes are this
> file + the Video Studio plan enhancement + the wave_runs ledger pointers.
>
> FOUNDER MANDATE (treat his words as the 1% sketch; design the 100%): build a system so FLEXIBLE that a
> vendor/super-admin can, ENTIRELY VIA THE UI: (1) add ANY hosted model + its API key; (2) SELF-HOST any
> model and point to its endpoint; (3) connect ANY tool/service/sub-tool in the future. A config-driven
> provider registry (type=hosted-api|self-hosted, base_url, auth scheme, request/response field-mapping,
> cost, health-check, capabilities). MOST-SECURE: keys encrypted-at-rest per-tenant, PIN/firewall-gated
> reveal, full audit, prompt/SSRF-injection guards on user-supplied endpoints. Crazy best-of-best UI.
> Production-grade, scalable, pluggable. **Video Studio is the FIRST consumer, not the only one.**
>
> NOTE: the **Vault** product (secret store) is a SEPARATE deferred build. This framework consumes a
> `get_secret()` seam that Vault will back; for now it uses the existing Fernet key-store + firewall, with
> the seam designed cleanly so Vault slots in by flipping `VAULT_BACKEND` — zero consumer code change.
>
> Grounded in the LIVE tree (every file:line below verified on disk 2026-06-14), the prior
> `RESEARCH [provider-registry-patterns | self-hosted-serving | connector-integration-framework |
> byo-key-security]` phases (`memory/wave_runs/video-flex-framework-design.md`), `VAULT-MASTER-PLAN.md §8/§C11`,
> and `MASTER_DNA_PLAN.md §J/§L`.

---

## 0. ⚡ THE HEADLINE — what this is, and what is ALREADY half-built

The founder is asking for a **universal AI-gateway + connector layer** (a LiteLLM/Bifrost/Portkey-class
registry) that lives inside Famit, multi-tenant, most-secure, and UI-driven. The good news: **three
independent, model-agnostic provider abstractions already exist** on the box and are the foundation stones —
they just are not unified.

| Existing abstraction | file:line | What it already proves |
|---|---|---|
| **VIDEO** function-switch (6 backends) | `media_gen/video/providers.py:51-411` (`build_submit`/`parse_result`/`verify_webhook`) + `config.py:67-115` (`_key_for` per-tenant override) | per-tenant key override (`<ENV>__<tenant>`), per-provider request/response mapping, webhook sig-verify, dormant/never-raises, the **generic** catch-all provider already lets a new vendor be pointed in via env |
| **IMAGE** Protocol-ABC (9 adapters) | `creative/image_banner_studio/providers/base.py:19-38` | a clean `Provider` interface: `status()/estimate_cost()/generate()` that NEVER raises; sync+async |
| **LLM** least-used key pool + Fernet CRUD | `llm_router/provider_pool.py:51-150` + `custom_providers.py:35-150` + `key_store.py:30-227` | Fernet AES at rest (`key_store.py:48`), hot-reload mtime cache, **runtime add/list-masked/delete of a custom provider via UI**, least-used rotation + 429 cooldown |

**The GAP this plan closes (the unification):** there is NO single registry; each layer picks its provider a
different way (env var / router / pool). There is no config-driven request/response field-map (each provider
hardcodes its own `_<provider>_submit`). There is no SSRF guard for a user-supplied `base_url`. There is no
per-tenant encrypted credential table with AAD binding. There is no health-check/circuit-breaker. There is no
`get_secret()` seam. **This plan adds exactly that one missing layer — a PG-backed, FORCE-RLS, capability-keyed
provider registry with a 3-tier transform adapter, an SSRF guard, an encrypted per-tenant credential store
behind the Vault seam, a health/circuit-breaker, and a crazy-good super-admin + vendor UI — and rewires the
three existing abstractions to resolve THROUGH it** (strangler pattern: the old paths keep working until the
registry is proven, then become thin wrappers over `registry.get_provider(...)`).

**Design law (non-negotiable, from PLAYBOOK + the megaplan rule):** additive, flag-gated
(`PROVIDER_REGISTRY_ENABLED` default OFF → resting byte-identical), earner-safe (the registry rides
`caller.py` + the AI-asset service, NEVER imports `agent.py`; video is async by construction so it adds ZERO
to the voice loop), multi-tenant FORCE-RLS, cost-capped (free/composite default, 1-paid-test choke-point),
most-secure (AAD-bound AES-256-GCM, PIN step-up reveal, SSRF guard, append-only audit), one box-mutating wave
at a time, serialized against RAG/Vault/Video on `caller.py`.

---

## 1. THE PRODUCT — one paragraph (the 100% the founder didn't fully sketch)

A super-admin opens **Settings ▸ Providers** and sees a registry of every AI/tool provider the platform can
reach. They click **Add provider**, pick a **type** (Hosted API · Self-hosted · Tool/Connector), pick one or
more **capabilities** the provider serves (`video_gen`, `image_gen`, `text_gen`, `tts`, `stt`, `embed`,
`rerank`, `tool_call`, `webhook`, `storage`…), and fill a form: a friendly name, the **base_url**, an **auth
scheme** (Bearer · API-key header · Basic · OAuth2-CC · none), and — for an alien API — a **request/response
field-map** built in a visual mapper (no JSON hand-editing required). They paste the **API key** (encrypted at
rest the instant it leaves the form, never shown again — only a masked `gsk_…AB12`), click **Test
connection**, and the registry runs an SSRF-guarded health-check that returns "Connected — model X ready — VRAM
Y GB free" or a precise error. The provider is now **live for the chosen capabilities with no code deploy**. A
**vendor** sees a scoped view: they can bring **their own key** for a hosted provider (so their gen budget is
theirs), but they cannot reveal/rotate a **platform** key, and they cannot register a **self-hosted** endpoint
(that is super-admin-only, SSRF-validated, sandbox-probed). Every consumer in the platform — **Video Studio
first**, then the voice LLM router, RAG, the WhatsApp AI connector, the image studio, future email/ads tools —
stops asking "which env var holds the key?" and instead asks **`registry.get_provider(tenant_id,
capability='video_gen')`**; the registry resolves the enabled provider for that tenant + capability, fetches
the credential through the Vault `get_secret()` seam, applies the field-map adapter, handles fallback/circuit-
breaker, meters the spend on the same wallet ledger, and returns a ready client. With no providers configured
every surface is dormant (`not_configured`), spends nothing, never raises — byte-identical resting.

---

## 2. RESEARCH VERDICTS — the production pattern (folded, sourced)

The four research phases (LiteLLM, OpenRouter, Kong AI Proxy Advanced, Bifrost, Portkey, n8n, Zapier,
Pipedream, Workato + OWASP/CVE) **converge on one architecture**. Adopted decisions:

**2a. PG-backed registry table, not YAML (LiteLLM `store_model_in_db` + `POST /model/new`).** A DB row IS the
"code". Add a provider via UI form → DB row → live within seconds, no restart. This is the only way "add via
UI, no code deploy" is true.

**2b. The 3-tier transform model (THE critical design decision — it makes "no code deploy" real for ~95%):**
- **Tier 1 — OAI-compat (`transform_type=openai_compat`): zero code, zero deploy, ~90% of the 2025-26 market.**
  Provider speaks OpenAI chat-completions at `base_url`. No field map needed. Covers Ollama, vLLM, TGI v1.4+,
  Together, Fireworks, fal/Replicate OAI-compat, any self-hosted LLaMA/Mistral/Qwen.
- **Tier 2 — Named provider (`transform_type=named_provider`): one dict entry, a trivial code deploy (~5%).**
  Known non-OAI format (Anthropic Messages, Gemini, Bedrock, **and our existing fal/replicate/luma video
  builders**). One entry in `NAMED_TRANSFORMS` + 1 test + 1 SSH push. The existing `providers.py` per-provider
  builders ARE these named transforms — we register them as `named_provider` entries, not throwaway.
- **Tier 3 — Custom field-map (`transform_type=custom_field_map`): zero code, fully config-driven (the moat).**
  Store `request_field_map` + `response_field_map` as **validated JSONPath/jmespath** in JSONB. At call time:
  load map, apply. The map IS the code. **NEVER `eval()`, never Jinja** — declarative JSONPath only, max depth
  5 (OWASP LLM01:2025). This is the "connect ANY future tool via the UI" lever.

**2c. Capability-based consumer interface (the universal connector seam).** Consumers declare a **capability**,
not a provider name. `registry.get_provider(tenant_id, capability='video_gen', routing_hint=None)`. Video
Studio is the first consumer; every future consumer plugs in by declaring a capability — that is the whole
"Video Studio is just the first" promise, structurally enforced.

**2d. Envelope-encrypted credentials, AAD-bound (Portkey secret-refs + Bifrost virtual keys + OWASP).** Two
tables: `provider_definitions` (the reusable spec, `_global` for platform-shared or tenant-scoped) +
`provider_credentials` (per-tenant encrypted key). AES-256-GCM, **AAD = `tenant_id‖provider_def_id‖version`
MANDATORY** (copying ciphertext into another tenant's row → `InvalidTag`). Resolved ONLY through the
`get_secret()` seam.

**2e. SSRF is the #1 risk — CVE-2025-59146 / CVE-2025-53767 / LiteLLM-RAG-May-2026 are direct precedents.** An
authenticated gateway that accepts a user `base_url` without validation → cloud-metadata token exfiltration.
The "add self-hosted endpoint" feature has EXACTLY this surface. SSRF guard is a **gate, not a nicety** — it
ships before any self-hosted provider can be registered.

**2f. Health-check + in-memory circuit breaker (Bifrost adaptive LB + LiteLLM `allowed_fails` + Kong).**
Background probe every 60s → `provider_health_log`; 3 consecutive fails → circuit open (in memory, not PG, to
avoid write storms); exponential backoff 60→120→240s; fallback chain ordered by `priority`. Never use a
generation endpoint for health (cost) — use list-models / a status path.

---

## 3. ARCHITECTURE — the registry as the single resolution point

```
        ┌──────────────────────────── FRONTEND (famit-panel) ────────────────────────────┐
        │  app/super-admin/providers/*  (registry CRUD + visual field-mapper + Test-conn) │
        │  app/settings/byo-keys/*      (vendor: bring-own-key, scoped, no platform reveal)│
        └─────────────────────────────────────┬───────────────────────────────────────────┘
                                               │ /admin/providers/*  ·  /providers/byo/*  (caller.py)
                                               ▼
  CALLER.PY  ┌──────────────── provider_registry  (NEW pkg: droplet_work/provider_registry/) ───────────────┐
  flag       │  endpoints.py  (CRUD, test-connection, health)   registry.py  get_provider(tenant,capability) │
  PROVIDER_  │  ssrf_guard.py validate_endpoint(host,port,scheme)   adapter.py  3-tier transform              │
  REGISTRY_  │  store.py (is_admin=False) · admin_store.py (super-admin) · health.py circuit-breaker          │
  ENABLED    └───────┬───────────────────────────────────────┬───────────────────────┬──────────────────────┘
                     │ get_secret(tenant,key_type,scope)      │ resolve def+cred+route │ meter spend
                     ▼                                        ▼                        ▼
        ┌── vault.get_secret SEAM ──┐    ┌── provider_definitions / provider_credentials / provider_health_log ──┐
        │ VAULT_BACKEND=local|...   │    │ PG, FORCE-RLS, AAD-bound AES-256-GCM (interim Fernet key_store)        │
        │ Fernet now → Vault later  │    └────────────────────────────────────────────────────────────────────────┘
        └────────────┬──────────────┘
                     │  (the same seam every consumer imports — and nowhere else)
   ┌─────────────────┼──────────────────┬─────────────────┬──────────────────┬─────────────────────┐
   ▼                 ▼                  ▼                 ▼                  ▼                     ▼
 VIDEO STUDIO    voice LLM router      RAG             image studio       WA AI connector       future tool
 (1st consumer)  (provider_pool)     (kb/core)      (image providers)    (whatsapp_ai)        (capability only)
```

**The load-bearing decision: STRANGLER, not rip-and-replace.** The three existing abstractions keep working
exactly as today when `PROVIDER_REGISTRY_ENABLED=0`. When ON, each consumer's key-resolution call
(`client._resolve_key`, `provider_pool._env_seed`, image `provider.status()`) is rewired to first ask the
registry; on a registry miss it falls back to the legacy env/Fernet path. This means **zero behavioural change
at rest, incremental cut-over per consumer, and an instant flag rollback** — the platform invariant.

**Earner safety:** the registry package rides `caller.py` and the AI-asset service (`:8310`), both separate
box-processes. It NEVER imports `agent.py`. Video/RAG/image are async or non-voice-path. The voice LLM router
(`provider_pool`) is the ONE consumer on a latency-sensitive path → its registry lookup is **cache-first with
a warm in-memory map** (reconcile on a background timer, never a per-turn DB hit) so it adds ~0ms per turn
(the same pattern W2 used for the context cache).

---

## 4. THE PACKAGE — exact files (NEW `droplet_work/provider_registry/`)

```
droplet_work/provider_registry/
  __init__.py            # pkg gate; reads PROVIDER_REGISTRY_ENABLED; import-safe with empty env
  config.py              # env reads (flag, allowlist, health interval, SSRF policy) — call-time, never cached
  schema.py              # ProviderDef / ProviderCred / Capability / TransformType dataclasses + from_any
  store.py               # tenant reads, is_admin=False HARDCODED (RLS-scoped); list/get/create/update/delete
  admin_store.py         # super-admin reads (is_admin=True), mounted ONLY under require_super_admin
  ssrf_guard.py          # validate_endpoint(host, port, scheme) -> bool ; pure, no I/O at validate-time
  adapter.py             # 3-tier transform: openai_compat | named_provider | custom_field_map (JSONPath-only)
  named_transforms.py    # the dict of named providers — REGISTERS the existing video builders + anthropic/gemini
  registry.py            # get_provider(tenant, capability, routing_hint) -> ProviderClient ; resolve+route+meter
  health.py              # background probe + in-memory circuit breaker (3-fail, expo backoff) + health log write
  credentials.py         # encrypt/decrypt via the get_secret seam (interim Fernet) ; AAD-bound ; never echoes
  endpoints.py           # FastAPI APIRouter — CRUD + test-connection + health (built_router pattern, NOT mounted yet)
  tests/
    test_registry_offline.py     # resolve, fallback, dormant, RLS-shape (mocked, no network)
    test_ssrf_guard.py           # RFC1918 / metadata / hex-octal / IPv6 / DNS-rebind / redirect-deny
    test_adapter_fieldmap.py     # JSONPath apply, depth-limit, eval-refusal, named/oai-compat parity
db/ddl_provider_registry.sql     # 3 tables, FORCE-RLS, append-only health log; idempotent IF NOT EXISTS
```

**Reuse, don't reinvent:** `credentials.py` rides the existing `cryptography`/Fernet from `key_store.py:48`
(zero new dep). `endpoints.py` uses the SAME `build_router(resolve_tenant, can, need_auth, _forbidden,
firewall=…)` guarded-mount pattern as `media_gen/router.py:170`. The named transforms IMPORT the existing
`media_gen/video/providers.py` builders verbatim (no duplication). The step-up reveal reuses `firewall.py`
(add `provider.reveal` scope, 60s TTL, `aud=provider_def_id`, single-use jti).

---

## 5. DATABASE SCHEMA — 3 tables, FORCE-RLS, AAD-bound (the canonical registry)

`db/ddl_provider_registry.sql` (additive, idempotent, manual-apply behind the flag — the platform pattern;
INTEGER paise for any money, FORCE-RLS, zero-`%` policy, `tenant_id` ALWAYS from JWT never body):

```sql
-- 1. The reusable provider spec. '_global' tenant_id = platform-shared (super-admin owned).
CREATE TABLE IF NOT EXISTS provider_definitions (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id        text NOT NULL,                 -- '_global' for platform-shared, else the tenant uuid
  slug             text NOT NULL,                 -- 'fal-wan26', 'my-ollama', 'acme-llm'
  display_name     text NOT NULL,
  provider_type    text NOT NULL,                 -- 'hosted_api' | 'self_hosted' | 'tool_connector' | 'platform_builtin'
  capabilities     jsonb NOT NULL DEFAULT '[]'::jsonb,  -- ['video_gen','image_gen','text_gen','tts','stt','embed','rerank','tool_call','webhook','storage']
  base_url         text NOT NULL,                 -- SSRF-validated on write (self_hosted) ; https-only for hosted
  auth_scheme      text NOT NULL DEFAULT 'bearer',-- 'bearer'|'api_key_header'|'api_key_query'|'basic'|'oauth2_cc'|'none'
  auth_header_name text,                          -- e.g. 'Authorization' | 'x-api-key'
  auth_value_tmpl  text DEFAULT 'Bearer {key}',   -- {key} is the ONLY interpolation token
  transform_type   text NOT NULL DEFAULT 'openai_compat',  -- 'openai_compat'|'named_provider'|'custom_field_map'
  named_provider   text,                          -- 'fal'|'replicate'|'luma'|'anthropic'|'gemini'... (named_provider tier)
  request_field_map  jsonb,                       -- JSONPath map (custom_field_map tier ONLY) ; validated, depth<=5, no eval
  response_field_map jsonb,
  model_default    text,                          -- the model= value / route default
  cost_per_unit_micros bigint,                    -- INTEGER micro-USD, never float (founder law) ; e.g. 50000 = $0.05
  cost_unit        text,                          -- 'per_second'|'per_generation'|'per_1k_tokens'|'per_char'|'per_minute'
  health_check_path text,                         -- '/v1/models' | '/health' | '/queue' ... ; per type default if NULL
  health_interval_s int DEFAULT 60,
  priority         int DEFAULT 100,               -- lower = higher in the fallback chain
  rate_limit_rpm   int,
  is_enabled       boolean NOT NULL DEFAULT true,
  is_platform_default boolean NOT NULL DEFAULT false,
  created_by       text,
  created_at       timestamptz DEFAULT now(),
  updated_at       timestamptz DEFAULT now(),
  UNIQUE (tenant_id, slug)
);
ALTER TABLE provider_definitions ENABLE ROW LEVEL SECURITY;
ALTER TABLE provider_definitions FORCE ROW LEVEL SECURITY;
-- read: own rows OR the platform-shared '_global' rows OR super-admin GUC.
CREATE POLICY provdef_read ON provider_definitions FOR SELECT
  USING ( current_setting('app.is_admin', true)='1'
          OR tenant_id = current_setting('app.tenant_id', true)
          OR tenant_id = '_global' );
-- write: own rows only ('_global' write-locked to super-admin GUC) — anti-privilege-escalation.
CREATE POLICY provdef_write ON provider_definitions FOR ALL
  USING ( current_setting('app.is_admin', true)='1'
          OR tenant_id = current_setting('app.tenant_id', true) )
  WITH CHECK ( current_setting('app.is_admin', true)='1'
          OR (tenant_id = current_setting('app.tenant_id', true) AND tenant_id <> '_global') );

-- 2. Per-tenant encrypted credential binding (accessed ONLY via credentials.py / the get_secret seam).
CREATE TABLE IF NOT EXISTS provider_credentials (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id        text NOT NULL,
  provider_def_id  uuid NOT NULL REFERENCES provider_definitions(id) ON DELETE CASCADE,
  ciphertext       bytea NOT NULL,                -- AES-256-GCM(plaintext, DEK), 12-byte nonce prepended
  wrapped_dek      bytea,                          -- DEK wrapped under KEK-1 (Vault) ; NULL on interim Fernet path
  key_aad          text NOT NULL,                 -- 'tenant_id||provider_def_id||version' (GCM binding — MANDATORY)
  key_version      int NOT NULL DEFAULT 1,
  kek_version      text,                           -- enables rolling rotation
  scope            text NOT NULL DEFAULT 'integration',  -- 'integration'(vendor BYO, revealable) | 'ai_provider'(platform, masked-only)
  last_rotated_at  timestamptz,
  expires_at       timestamptz,
  is_active        boolean NOT NULL DEFAULT true,
  created_at       timestamptz DEFAULT now(),
  UNIQUE (tenant_id, provider_def_id, key_version)
);
ALTER TABLE provider_credentials ENABLE ROW LEVEL SECURITY;
ALTER TABLE provider_credentials FORCE ROW LEVEL SECURITY;
CREATE POLICY provcred_iso ON provider_credentials
  USING ( current_setting('app.is_admin', true)='1'
          OR tenant_id = current_setting('app.tenant_id', true) );

-- 3. Health log (circuit-breaker input ; append-only ; FORCE-RLS).
CREATE TABLE IF NOT EXISTS provider_health_log (
  id               bigserial PRIMARY KEY,
  tenant_id        text NOT NULL,
  provider_def_id  uuid NOT NULL REFERENCES provider_definitions(id) ON DELETE CASCADE,
  checked_at       timestamptz DEFAULT now(),
  is_healthy       boolean,
  latency_ms       int,
  error_code       text
);
ALTER TABLE provider_health_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE provider_health_log FORCE ROW LEVEL SECURITY;
CREATE POLICY provhealth_iso ON provider_health_log
  USING ( current_setting('app.is_admin', true)='1'
          OR tenant_id = current_setting('app.tenant_id', true) );
REVOKE UPDATE, DELETE ON provider_health_log FROM famit_app;  -- append-only (RBAC layer; trigger optional)
```

**Why `scope` on the credential, not the definition:** the same `_global` provider-def (e.g. "fal") can have a
**platform** credential (`scope='ai_provider'`, vendor sees masked-only, no reveal) AND a vendor's **own**
credential (`scope='integration'`, that vendor CAN reveal/rotate their own). This is the Vault §9 trust model
expressed in one column — it is the structural answer to "BYO-key but don't leak platform keys".

---

## 6. THE SECURITY MODEL — most-secure (the founder's explicit ask), red-team-folded

| Control | Design | Reuse / file |
|---|---|---|
| **Encryption at rest** | AES-256-GCM, **AAD = `tenant_id‖provider_def_id‖version`** (cross-tenant ciphertext non-portable) ; interim Fernet via `key_store.py`, Vault KEK-0/KEK-1/DEK envelope later — same `credentials.py` interface | `key_store.py:48`, VAULT §C6 |
| **Per-tenant isolation** | FORCE-RLS on all 3 tables ; `tenant_id` from `resolve_tenant(JWT)` never body ; app role NOSUPERUSER+NOBYPASSRLS ; `_global` write-locked from non-admin | `caller.py:404`, `db/rls.sql:44` |
| **Reveal gate (PIN step-up)** | REVEAL plaintext / ROTATE / REGISTER-self-hosted require a `firewall.py` step-up token: 60s TTL, `aud=provider_def_id`, **single-use jti** (`provider_used_jti` consume), per-tenant mint rate-limit 5/15min | `firewall.py:95,267-295` (+ close the live jti-replay gap) |
| **Reveal POLICY** | `scope='ai_provider'` (platform key) → vendor gets **masked-only, NO reveal/rotate** ; `scope='integration'` (vendor's own) → vendor CAN reveal/rotate. Super-admin reveal of any via `admin_store.py` only | VAULT §9 |
| **SSRF guard (self-hosted `base_url`)** | accept `host`+`port`+`scheme` as **separate validated fields**, reassemble server-side → DNS-resolve ALL A/AAAA → denylist `127/8 ::1 10/8 172.16/12 192.168/16 169.254/16 0/8` → scheme allowlist http/https → reject hex/octal/dword/IPv6-encoded → `allow_redirects=False` (re-validate any redirect) → 10s connect/60s read timeout → host allowlist for hosted, super-admin-only for self-hosted | `ssrf_guard.validate_endpoint`, CVE-2025-59146 |
| **Network egress (defense in depth)** | the registry worker's outbound is firewalled at the box to registered endpoints + internal backend only ; RFC1918/metadata blocked at infra layer regardless of app validation | DO firewall (FORTRESS) |
| **Health-check sandbox** | a NEW self-hosted endpoint is probed in an isolated worker (separate process, 10s timeout, list-models only — no inference) before it can serve a real call | `health.py` |
| **Field-map injection** | request/response maps are **declarative JSONPath ONLY**, validated at write-time (syntax + depth≤5), NEVER `eval()`/Jinja/template ; responses from user-registered endpoints are UNTRUSTED (schema-validated, spotlight-delimited before any downstream use) | OWASP LLM01:2025 |
| **Audit** | every CRUD + REVEAL + ROTATE + HEALTH event → append-only audit (who/what/when/result, **never the plaintext**) ; `provider_health_log` REVOKE UPDATE/DELETE | `audit_hook`, VAULT §E |
| **Legacy-pw exclusion** | the static `FamitCall2026` bearer → 403 on all `/admin/providers/*` | control-security #1 |

**The Vault seam (the clean swap point — designed now, Vault backs it later):**
```python
# credentials.py imports ONLY this — nowhere else reads a raw key:
from vault.seam import get_secret   # VAULT-MASTER-PLAN §8
key = await get_secret(tenant_id, key_type='ai_provider'|'integration'|'self_hosted',
                       scope='provider_registry', is_admin=False)
# interim: get_secret routes to the Fernet key_store. Vault ship = flip VAULT_BACKEND ; zero consumer change.
```

---

## 7. THE ADAPTER — the 3-tier transform (how "add any API" actually works)

`adapter.py` exposes ONE pair the registry calls: `build_request(def, cred, envelope) -> (url, headers, body)`
and `parse_response(def, raw) -> envelope`. The **internal envelope** is provider-neutral (the same shape the
existing `media_gen` `_common_input` already uses):

```python
# internal request envelope (the registry always speaks this):
{ "capability": "video_gen", "prompt": "...", "negative_prompt": "...", "model": "...",
  "params": {"duration_s": 5, "aspect_ratio": "9:16", "max_tokens": 512, "temperature": 0.7, ...} }
# internal response envelope (every adapter returns this):
{ "text": "", "image_url": "", "video_url": "", "embedding": [], "external_id": "",
  "status": "submitted|running|succeeded|failed", "usage": {"input_tokens":0,"output_tokens":0},
  "cost_micros": 0, "latency_ms": 0, "raw": {} }
```

- **Tier 1 `openai_compat`:** body = `{model, messages:[{role:user, content:prompt}], **params}`; headers from
  `auth_scheme`; response read from `$.choices[0].message.content`. Pure config — no per-provider code.
- **Tier 2 `named_provider`:** dispatch to `named_transforms.NAMED[def.named_provider]` — and the existing
  `media_gen/video/providers.build_submit/parse_result` ARE registered there (fal/replicate/luma/higgsfield/
  selfhost/generic), plus anthropic/gemini/bedrock for text. Adding a brand-new named format = 1 dict entry +
  1 test + 1 push.
- **Tier 3 `custom_field_map`:** apply `request_field_map` (JSONPath writes from the envelope into the wire
  body) and `response_field_map` (JSONPath reads from the raw response into the envelope). JSONPath-only,
  depth≤5, no eval. This is what lets a super-admin wire an unknown vendor entirely from the UI.

**Self-hosted server contracts baked into the type presets** (from `RESEARCH [self-hosted-serving]`): vLLM
(`/health` unauth liveness + `/v1/models` Bearer readiness), Ollama (`/` + `/api/tags`), TGI (legacy,
maintenance-mode — supported but not primary), A1111 (`/sdapi/v1/sd-models` readiness, base64-PNG decode),
ComfyUI (`POST /prompt` → poll `/history/{id}` → `/view`; capability via `/object_info/{node_class}`; the
Wan2.1/LTX/Mochi self-hosted-video path). Each `provider_type` preset ships a default `health_check_path`,
readiness probe, and capability probe so "Test connection" just works.

---

## 8. ENDPOINTS + FLAGS

**New flag `PROVIDER_REGISTRY_ENABLED` (default OFF → resting byte-identical).** Mounted via the guarded
`build_router(...)` pattern in `caller.py` (serialized against RAG/Vault/Video — only ONE edits caller.py at a
time).

| Method + path | Role | Behavior |
|---|---|---|
| `GET  /admin/providers` | super-admin | list all defs (masked creds) + health badge |
| `POST /admin/providers` | super-admin | create def (SSRF-validate self-hosted on write, PIN step-up) |
| `PUT/DELETE /admin/providers/{id}` | super-admin | update/disable (never edits the secret in place) |
| `POST /admin/providers/{id}/test` | super-admin | SSRF-guarded health + capability probe → "Connected — model X ready" |
| `POST /admin/providers/{id}/reveal` | super-admin | plaintext reveal (step-up jti single-use, audited) — `ai_provider` scope |
| `POST /admin/providers/{id}/rotate` | super-admin | rotate key (step-up, re-encrypt, audit) |
| `GET  /admin/providers/health` | super-admin | per-provider circuit state + latency |
| `GET  /providers/byo` | tenant | a vendor's own (scope=`integration`) provider list (masked) |
| `POST /providers/byo` | tenant | vendor adds their OWN hosted-API key (no self-hosted, no platform reveal) |
| `POST /providers/byo/{id}/reveal\|rotate` | tenant | reveal/rotate ONLY their own `integration` credential (step-up) |

Consumer-facing (internal, not HTTP): `registry.get_provider(tenant_id, capability, routing_hint=None)`.

---

## 9. FRONTEND — the crazy best-of-best Provider UI (Core_2 + Inter Display, zero hex)

**`app/super-admin/providers/page.tsx`** (`<Layout title="Providers">`): a registry table (display name ·
type pill · capability chips · **health badge** green/amber/red · masked key · enabled toggle), an **Add
provider** slide-over with: type segmented-tabs (Hosted · Self-hosted · Connector), capability multiselect,
auth-scheme Select, base_url Field (host+port split with live SSRF feedback), an **encrypted key paste** that
masks on blur, and a **visual field-mapper** (left = our envelope fields, right = the provider's wire fields,
drag-to-map → emits the JSONPath JSONB — no JSON hand-editing). A **Test connection** button runs the probe
and shows "Connected — model X ready — VRAM Y GB free" or a precise error with the raw HTTP status. A
**reveal** action opens the existing PIN-pad ring (reuse the api-keys secret-row + Vault reveal component).

**`app/settings/byo-keys/page.tsx`** (vendor-scoped): the same kit, but only Hosted-API, only their own keys,
reveal/rotate enabled for `integration` scope, platform keys shown masked-only with a "platform-managed" lock.

**Reuse verbatim:** `Card`, `Tabs`, `Select`, `Field`, `Button`, `Badge`, `Modal isSlidePanel`, `Dropdown`,
`Spinner`, `NoFound`, the api-keys secret-row + Vault PIN-pad reveal (`super-admin/api-keys/page.tsx:268-327`),
the health-badge grammar from the LLM pool status page. **One new component:** `FieldMapper` (the drag-to-map
JSONPath builder) — the single piece no existing page has.

---

## 10. FLAG / ACCEPTANCE / ROLLBACK

**Flags (all default OFF → resting byte-identical):** `PROVIDER_REGISTRY_ENABLED` (the registry + mount) ·
per-consumer cut-over sub-flags (`REGISTRY_FOR_VIDEO`, `REGISTRY_FOR_LLM`, `REGISTRY_FOR_IMAGE`) so each
consumer is strangled independently and reverts independently.

**Acceptance (offline-first, then live):**
1. **Resting byte-identical** — all flags OFF → caller.py route table + render identical; golden exit 0; earner
   gate (agent.py md5 9150fabe UNCHANGED, famit-agent PID NOT restarted, /health 200, 0 5xx) before+after.
2. **DDL** — 3 tables FORCE-RLS=t live; `provider_health_log` UPDATE/DELETE blocked; cross-tenant SELECT probe = 0 rows; tables in the live PG backup set.
3. **AAD** — a ciphertext copied from tenant A's row into tenant B's → `InvalidTag` on decrypt (no plaintext).
4. **SSRF** — `test_ssrf_guard.py`: 127.0.0.1 / 169.254.169.254 / 10.x / hex-octal-dword / IPv6-mapped / DNS-rebind / redirect-to-private ALL rejected; a public https host passes.
5. **Adapter** — openai_compat round-trips a mock OAI server; a named_provider (fal) matches the existing `providers.py` golden bytes; a custom_field_map applies JSONPath and REFUSES a non-JSONPath/eval string.
6. **Resolution** — `get_provider(A,'video_gen')` returns A's enabled provider, never B's (RLS probe via the seam); a disabled/circuit-open provider falls back by priority; no provider → `not_configured` (dormant).
7. **Reveal** — reveal returns plaintext once; replay of the jti → 403; `ai_provider` scope vendor reveal → 403; `integration` scope vendor reveal of THEIR key → 200; legacy-pw → 403.
8. **Health** — 3 consecutive probe fails → circuit open in memory; backoff 60→120→240; recovery closes it; events in `provider_health_log`.
9. **Strangler cut-over** — with `REGISTRY_FOR_VIDEO=1`, video resolves through the registry and renders; with it 0, the legacy env path renders identically (byte-diff).
10. **Frontend** — add/test/reveal/rotate flows work; FieldMapper emits valid JSONPath; `tsc --noEmit` 0, `npm run build` 0, gitleaks staged 0, zero hex, reduced-motion + dark-mode safe.
11. **Integrated soak (founder's #1 rule)** — inbound call wave + a registry-resolved composite video batch + library loads concurrently on the shared box: green-integrated, voice loop adds 0ms (LLM router cache-first), 0 5xx.

**Rollback:** flags → 0 (instant, no deploy — resting byte-identical). The 3 tables are additive (drop is
safe; no existing table altered). Each consumer reverts independently via its sub-flag. Backups per the
FORTRESS recipe before any box write. Folded into `THREE_PRODUCTS_ROLLBACK.md`.

---

## 11. BUILD ORDER (earner-safe, one box-mutating wave at a time, serialized vs RAG/Vault/Video)

> Earner gate before+after EVERY box-mutating wave: agent.py md5 9150fabe UNCHANGED + famit-agent PID NOT
> restarted + /health 200 + 0 5xx + golden byte-diff + NO ring. Restart ONLY famit-caller / the AI-asset
> service / the hatchet worker / famit-panel.

1. **F1 — DDL + package shell.** `db/ddl_provider_registry.sql` (3 tables, FORCE-RLS, append-only health) +
   `provider_registry/` import-guarded shell + `PROVIDER_REGISTRY_ENABLED` flag. *PG + local; flag OFF.*
2. **F2 — `ssrf_guard.py` + `adapter.py` + `named_transforms.py` (register the existing video builders) +
   `credentials.py` (interim Fernet via the get_secret seam, AAD-bound).** *Local + offline tests; no mount.*
3. **F3 — `store.py`/`admin_store.py`/`registry.py`/`health.py`** (resolve + fallback + circuit-breaker +
   reveal step-up). *Local + offline tests.*
4. **F4 — Mount `endpoints.py` in caller.py** under `PROVIDER_REGISTRY_ENABLED` (CRUD + test-connection +
   reveal/rotate + health). *caller.py (additive, flag OFF) — ⚠ serialize: only ONE of {RAG,Vault,Video,
   Registry} edits caller.py at a time.*
5. **F5 — Strangler cut-over: VIDEO first** (`REGISTRY_FOR_VIDEO`). `media_gen/video/client._resolve_key` →
   ask the registry, fall back to `config.fal_key(...)` on miss. Prove byte-identical render both ways. *This
   is the seam Video Studio's BYO-key (U9) consumes.*
6. **F6 — Strangler: IMAGE** (`REGISTRY_FOR_IMAGE`) then **LLM router** (`REGISTRY_FOR_LLM`, cache-first warm
   map, ~0ms per turn — the ONE latency-sensitive consumer, proven on inbound first). *one consumer per wave.*
7. **F7 — Frontend** (`super-admin/providers` + `settings/byo-keys` + the `FieldMapper`). *famit-panel only —
   launch ONLY when no other wave edits the panel; deploy FORTRESS once at the end.*
8. **F8 — Vault seam migration** (when Vault ships): flip `VAULT_BACKEND=local→vault`, migrate creds, run the
   RLS-via-seam probe. *config flip + migration job; zero consumer code change.*
9. **F9 — Integrated soak + rollback runbook** (fold into `THREE_PRODUCTS_ROLLBACK.md`). *verify-only.*

> ⛔ GATED (build the safe half, record the blocked half): real hosted-gen needs the founder's keys; real
> self-hosted needs a GPU box (DO limit 3/3 full) ; Vault seam back-end needs the Vault product (deferred).
> The registry + Tier-1 OAI-compat + the composite-video consumer all work TODAY with the interim Fernet
> store and zero new box.

---

## 12. FOUNDER-UNNAMED FEATURES I'm adding (the 100% he didn't sketch)

1. **The 3-tier transform** — "add any API via the UI with no code deploy" is only TRUE because of
   openai_compat (90%) + custom_field_map JSONPath (the long tail). He named "add a key + base_url"; the
   field-mapper is the part that makes arbitrary vendors work.
2. **Capability-keyed resolution** — consumers ask for a capability, not a provider. This is the structural
   guarantee that "Video Studio is just the first consumer" — every future tool plugs in for free.
3. **Strangler cut-over (per-consumer sub-flags)** — the three existing abstractions are rewired through the
   registry incrementally, each independently revertible. No big-bang, no churn of shipped code.
4. **`scope` on the credential (platform vs vendor BYO)** — one column delivers "bring your own key but never
   leak a platform key", the exact Vault §9 trust model.
5. **SSRF guard as a first-class gate** — the single feature that turns "add a self-hosted endpoint" from a
   CVE-2025-59146 into a safe action. He'd never have named it; it's mandatory.
6. **Health-check + in-memory circuit breaker + fallback chain** — a dead provider auto-degrades and the next
   by priority serves; the UI shows a live health badge.
7. **The visual FieldMapper UI** — drag-to-map instead of hand-editing JSONPath; the difference between a dev
   tool and a product a non-technical vendor can use.
8. **Cache-first LLM-router lookup** — the registry adds 0ms to the voice loop (the one place latency matters).
9. **The clean `get_secret()` Vault seam** — designed now so Vault is a config flip later, not a rewrite.
10. **Audit + reveal-policy + jti single-use** — closes the live firewall jti-replay gap for the registry's
    own reveal path; SOC2-grade access log for procurement.

---

## 13. RISKS (honest)

- **R1 — caller.py serialization.** Registry, RAG, Vault, Video all edit caller.py + the entitlement registry
  + nav. Only ONE at a time; ledger the mount order. (PLAYBOOK #5.)
- **R2 — strangler regression.** Rewiring `_resolve_key`/`provider_pool` could change a live resolution. Guard:
  per-consumer sub-flag, byte-identical render proof both ways, video cut over FIRST (async, lowest risk),
  LLM-router LAST (latency-sensitive) and only after inbound proves 0ms.
- **R3 — SSRF is the sharpest knife.** A miss = cloud-metadata exfiltration. `ssrf_guard` ships + is tested
  (hex/octal/IPv6/rebind/redirect) BEFORE any self-hosted provider can be registered; network-egress firewall
  is the defense-in-depth backstop.
- **R4 — field-map injection.** A user JSONPath string is untrusted. JSONPath-only, depth-limited, no eval,
  schema-validate the response. Never interpolate a user string into a URL except the single `{key}` token.
- **R5 — Vault not yet built.** Interim Fernet is weaker than the full AAD-envelope; mitigated by AAD-binding
  the Fernet ciphertext too and keeping `credentials.py` Vault-shaped, so the upgrade is a backend swap.
- **R6 — the LLM router is on the hot path.** A per-turn DB lookup would add latency. Mitigated by the
  cache-first warm map (reconcile on a timer), proven on inbound before the earner path is ever considered.

---

## 14. 🗺️ UNIFIED CROSS-PRODUCT BUILD ROADMAP — Framework FIRST, then Video Studio on it

> The single sequenced merge of this plan's **F1–F9** (the universal framework) and
> `VIDEO-STUDIO-MASTER-PLAN.md`'s **U1–U10** (the first consumer). The founder's order is honored:
> **build the FRAMEWORK first, then Video Studio on top of it, and the composite tier ships with ZERO
> paid key.** One box-mutating wave at a time. ⚠️ **caller.py serialization (PLAYBOOK #5):** only ONE of
> {RAG, Vault, **Registry**, Video} edits `caller.py` at a time — the ledgered mount order below.
> Sequencing context: **RAG W3 is LIVE+DEPLOYED (2026-06-14)**; Vault is deferred (its `caller.py` mount is
> NOT scheduled here). So the registry's `caller.py` mount (W4) is the **next** `caller.py` edit after RAG,
> and Video's `caller.py` mount (W9) follows it — never concurrent.

**Model routing (founder rule):** BE on **Opus** (the backend specialist — DDL/RLS/crypto/SSRF/adapter/the
caller.py mount); FE on **Sonnet + the `frontend-design` skill** (port Core_2, never approximate). One scoped,
testable deliverable per agent; commit per verified unit.

**Earner gate before+after EVERY box-mutating wave (non-negotiable):** `agent.py` md5
`9150fabe4ff62b4b4470f9a87df346e5` UNCHANGED · famit-agent PID `1477083` NOT restarted · caller `/health` 200 ·
0 real 5xx · golden byte-diff · NO ring. Restart ONLY famit-caller / the AI-asset service (`:8310`) / the
Hatchet worker / famit-panel. Backups per the FORTRESS recipe before any box write. `agent.py` is NEVER
imported by any wave (the registry rides caller.py + the AI-asset process; video is async by construction).

| # | Wave | Scope (deliverable) | Files / schema | Flag (default OFF) | Acceptance gate | Rollback |
|---|---|---|---|---|---|---|
| **W1** ✅ DONE | **FW: DDL + package shell** | 3 FORCE-RLS tables + import-guarded pkg skeleton; resting byte-identical | `db/ddl_provider_registry.sql`; `provider_registry/{__init__,config,schema}.py` | `PROVIDER_REGISTRY_ENABLED` | 3 tables FORCE-RLS=t live, health-log UPDATE/DELETE blocked, cross-tenant SELECT=0 rows, tables in PG backup set; pkg imports with empty env | drop tables (additive, nothing altered); flag→0 |
| **W2** ✅ DONE | **FW: guard + adapter + creds (offline)** | SSRF guard, 3-tier transform, named-transforms registering the EXISTING video builders, AAD-bound interim-Fernet creds behind the `get_secret` seam | `ssrf_guard.py`, `adapter.py`, `named_transforms.py`, `credentials.py` + `tests/*` | (none — local) | `test_ssrf_guard.py` rejects 127/169.254/10.x/hex-octal/IPv6/rebind/redirect, passes a public https host; openai_compat round-trips a mock; named `fal` matches `providers.py` golden bytes; custom_field_map applies JSONPath + REFUSES eval; AAD copy→`InvalidTag` | local only — revert commit |
| **W3** ✅ DONE | **FW: resolve + health + reveal (offline)** | `get_provider(tenant,capability)` resolve+fallback; in-memory circuit breaker; PIN step-up reveal (60s/aud=def_id/single-use jti) | `store.py`, `admin_store.py`, `registry.py`, `health.py` + tests | (none — local) | resolve returns own provider not B's (RLS via seam); disabled/circuit-open falls back by priority; no provider→`not_configured`; jti replay→403; `ai_provider` vendor reveal→403, `integration` own reveal→200 | local only — revert commit |
| **W4** | **FW: mount endpoints in caller.py** ⚠ caller.py | CRUD + test-connection + reveal/rotate + health via the proven `build_router(...)` guarded mount | `caller.py` (additive, flag OFF); `endpoints.py` | `PROVIDER_REGISTRY_ENABLED` | resting byte-identical (route table + golden exit 0); legacy-pw→403 on `/admin/providers/*`; test-connection SSRF-guarded; earner gate PASS | flag→0 (instant, no deploy) |
| **W5** | **FW: strangler cut-over — VIDEO first** | `media_gen/video/client._resolve_key` asks the registry, falls back to `config.fal_key(...)` on miss | `media_gen/video/client.py` (`:304-318`) | `REGISTRY_FOR_VIDEO` | hosted-gen video renders via `registry.get_provider(...)` (no raw env read in the render path); `REGISTRY_FOR_VIDEO=0` → legacy env path byte-identical render | sub-flag→0 |
| **W6** | **VID: seam fix + PG schema + live-library bridge** (U1+U2+U3) | 1-line `engine.py:51` seam fix; `ai_asset` video columns + `video_jobs` + `video_scripts` (FORCE-RLS); `register_video_asset` internal route on `:8310` + `?media_type=` + `/poster` | `creative/video_studio/engine.py`; `db/ddl_video.sql`; `ai_asset/endpoints.py` (NOT caller.py) | `FEATURE_VIDEO_LIBRARY` | `engine_name()`→`media_gen.video.client`; 19 offline tests green; a finished video shows in `GET /assets?media_type=video`; `/raw` 302-presigns the MP4; cross-tenant RLS probe PASS | flag→0; drop additive columns/tables |
| **W7** | **VID: composite tier + cost-truth** (U5) | `media_gen/video/compose.py` + `provider="compose"`; Hatchet saga (script→VO→caption→render→compose); Sarvam-default TTS (EL paid-gated), Whisper captions, ABR/H.265; pre-fan-out wallet hold | `media_gen/video/compose.py`; Hatchet worker on `famit-hatchet` | `FEATURE_VIDEO_COMPOSE` | a NO-gen-key composite batch renders 5 real MP4s (product+TTS+caption), pre-fan-out hold ≥ estimate, settles ~₹0.25/clip, ABR ladder present; EL forces BATCH_SIZE=1+founder-sign on first use | flag→0; stop the worker (no caller.py touch) |
| **W8** | **VID: mount studio + submit_gate** (U4) ⚠ caller.py | `creative.video_studio.endpoints` mounted; bind `list_campaigns`; `collect_batch`→bridge; every render through `submit_gate` (1-paid-test forcing + per-tenant `VIDEO_DAILY_CAP_USD` + pre-fan-out hold, H1/H2) | `caller.py` (additive, flag OFF); `creative/video_studio/endpoints.py` | `FEATURE_VIDEO_STUDIO` | resting byte-identical; `propose→approve→collect` E2E on the fake+compose engine; first paid render forced to BATCH_SIZE=1/≤6s/AUTO_APPROVE=0; per-tenant cap blocks A without touching B; earner gate PASS | flag→0 (instant) |
| **W9** | **VID: frontend** (U6) — FE only | Extend `Asset` type; split `AssetImage`→`AssetMedia` (`<video preload="none" poster>`); `FilterRail` Video facet; `LibraryGallery` Images↔Videos toggle; `app/creative/video/page.tsx` + TierTabs (composite default) + BatchProgress + UploadClip; nav | `famit-panel/lib/assets.ts`, `app/creative/_components/*`, `app/creative/video/*` | `FEATURE_VIDEO_STUDIO` (FE reads flag) | Images↔Videos toggle filters; `<video>` renders poster+controls; network tab shows posters only (`preload="none"`); `tsc --noEmit` 0, `npm run build` 0, gitleaks 0, zero hex, dark-mode + reduced-motion safe | revert FE deploy (FORTRESS `.next` backup) |
| **W10** | **FW+VID: remaining strangler + Signal-Loop + hardening** (F6 + U7 + U8) | FW: strangle IMAGE then LLM-router (cache-first, ~0ms/turn, inbound-proven LAST); VID: `ab_group`/`ai_generated`/disclosure lineage + Ads-handoff stub; reaper (H5) + output-moderation (H3) + destination-spec validator (H6) + Spaces lifecycle + R2 seam (H7) + alerts (H9) | `provider_pool.py`, image providers; AI-asset service + Hatchet worker (NOT caller.py) | `REGISTRY_FOR_IMAGE`, `REGISTRY_FOR_LLM`; (hardening flags) | LLM-router cache-first adds 0ms/turn (inbound soak); kill-worker-mid-saga → reaper releases hold + reconciles (no locked money/lost render); flagged-frame → quarantine not auto-publish; 90s clip → WhatsApp-status attach rejected with clear error | per-consumer sub-flags→0; hardening flags→0 |
| **W11** | **FW+VID: BYO-key UI + Vault-seam + multilingual/music** (F7 + U9) — FE + additive | FW: `app/super-admin/providers` + `app/settings/byo-keys` + the `FieldMapper`; VID: BYO-key card becomes a view over the registry (`scope='integration'`), multilingual fan-out (Sarvam-only default), royalty-free music library + provenance | `famit-panel/app/super-admin/providers/*`, `app/settings/byo-keys/*`; `media_gen/video/*` | `PROVIDER_REGISTRY_ENABLED` (FE) | add/test/reveal/rotate flows work; FieldMapper emits valid JSONPath; vendor reveals THEIR fal key (step-up) but platform key reveal→403; multilingual fan-out does NOT auto-multiply paid TTS | revert FE deploy; flags→0 |
| **W12** | **Vault seam swap + integrated soak + rollback runbook** (F8 + F9 + U10) — verify-only | flip `VAULT_BACKEND=local→vault` when Vault ships (zero consumer change); ONE shared-box soak (inbound call wave + a registry-resolved composite batch + library loads concurrently); `THREE_PRODUCTS_ROLLBACK.md` flips every flag OFF in order | (config flip + migration job); `THREE_PRODUCTS_ROLLBACK.md` | (env) | green-INTEGRATED (not just green-per-component — the founder's #1 rule); voice loop adds 0ms; 0 5xx; one-pass rollback confirms byte-identical resting | the rollback runbook IS the rollback |

> ⛔ **GATED (build the safe half, record the blocked half):** real hosted-gen needs the founder's `FAL_KEY`/
> `RUNWAY_KEY`; real self-hosted needs a GPU box (DO limit 3/3 full); real ad launch needs Meta/Google OAuth;
> the AI-asset nginx proxy repoint is FE-box-root-gated; the Vault back-end (W12) needs the Vault product
> (deferred). **What works TODAY with zero new box / zero paid key:** the registry + Tier-1 OAI-compat, the
> FFmpeg **composite** video tier, and manual-upload — ship those first; they need nothing from the founder.

**The first 3 waves, ready to launch after RAG W3 (spelled out):**
- **W1 — Framework DDL + package shell (BE/Opus, PG + local, flag OFF).** Write `db/ddl_provider_registry.sql`
  (the 3 FORCE-RLS tables in §5, idempotent `IF NOT EXISTS`, manual-apply, `_global` write-locked, append-only
  health log) and the import-guarded `provider_registry/{__init__,config,schema}.py` shell reading
  `PROVIDER_REGISTRY_ENABLED`. Acceptance: tables live with FORCE-RLS=t, health-log UPDATE/DELETE blocked,
  cross-tenant SELECT=0, added to the PG backup set; pkg imports cleanly with an empty env; resting
  byte-identical. NO caller.py edit. Rollback: drop the additive tables.
- **W2 — SSRF guard + 3-tier adapter + named-transforms + AAD creds (BE/Opus, local + offline tests, no mount).**
  `ssrf_guard.validate_endpoint(host,port,scheme)` (host/port split, DNS-resolve-all, RFC1918/metadata denylist,
  hex/octal/IPv6/rebind/redirect-deny); `adapter.build_request/parse_response` (openai_compat / named_provider /
  custom_field_map JSONPath depth≤5 no-eval); `named_transforms.py` REGISTERING the existing
  `media_gen/video/providers.build_submit/parse_result` (fal/replicate/luma — reused, not rewritten);
  `credentials.py` AAD-bound AES-256-GCM via the interim Fernet `get_secret` seam. Acceptance: the full
  `test_ssrf_guard.py` / `test_adapter_fieldmap.py` suites green; named-`fal` byte-matches the live
  `providers.py` golden; AAD cross-tenant copy → `InvalidTag`. Local only.
- **W3 — Resolve + health + reveal (BE/Opus, local + offline tests).** `registry.get_provider(tenant,capability,
  routing_hint)` (resolve → credential via seam → adapter → fallback by priority); `health.py` background probe +
  in-memory circuit breaker (3-fail, expo backoff 60→120→240); the PIN step-up reveal path (`firewall.py` scope
  `provider.reveal`, 60s TTL, `aud=provider_def_id`, single-use jti — closing the live jti-replay gap).
  Acceptance: A's resolve never returns B's provider (RLS via the seam); circuit-open falls back by priority; no
  provider → `not_configured` dormant; jti replay → 403; the `scope` reveal-policy matrix holds. Local only — and
  this is the last wave before the FIRST caller.py edit (W4), which must be serialized against RAG/Vault/Video.

---

*End PROVIDER-FRAMEWORK-PLAN.md. The founder's "add any model/endpoint/tool via the UI, most-secure,
pluggable" is designed to the 100%: a PG+FORCE-RLS capability-keyed registry, a 3-tier transform adapter
(openai_compat / named_provider / custom_field_map), an SSRF guard, AAD-bound per-tenant encrypted credentials
behind the Vault `get_secret` seam, health/circuit-breaker, and a crazy-good super-admin + vendor UI — with the
three existing provider abstractions rewired through it by strangler, each flag-revertible. Earner-safe (rides
caller.py / AI-asset, never agent.py; voice-router cache-first = 0ms), multi-tenant-RLS, cost-capped,
most-secure, sellable, differentiated. Video Studio is the first consumer; every future tool is free. One
box-mutating wave at a time, serialized against RAG/Vault/Video.*
