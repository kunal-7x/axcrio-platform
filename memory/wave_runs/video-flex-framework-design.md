## Phase: RESEARCH [provider-registry-patterns] — production pluggable provider/model registry patterns

**Date:** 2026-06-14

### THE CORE QUESTION
How do production AI gateways make providers config-addable at runtime (base_url + auth scheme + request/response field-mapping) WITHOUT a code deploy?

---

### FINDING 1 — LiteLLM: the gold standard for config-driven runtime provider registration

**Source:** https://docs.litellm.ai/docs/proxy/model_management + https://docs.litellm.ai/docs/proxy/configs

**Two-tier model list:** LiteLLM proxy separates "Config Models" (from `config.yaml`, read at startup) from "DB Models" (added via UI or API at runtime, stored in Postgres). `store_model_in_db` enables the DB path. DB models are live immediately — no restart.

**Runtime model add — POST /model/new (no restart):**
```json
{
  "model_name": "<user-facing alias>",
  "litellm_params": {
    "model": "<provider>/<model-id>",
    "api_key": "<key or os.environ/VAR>",
    "api_base": "<base_url for self-hosted or OAI-compat endpoint>",
    "rpm": 60
  },
  "model_info": { "any": "metadata" }
}
```

**Provider type taxonomy (critical design input):**
1. **OpenAI-compatible (config-only, zero code):** Any endpoint that speaks OAI chat-completions format. Just `api_base` + `api_key`. Covers Ollama, vLLM, Together, Fireworks, Anyscale, any self-hosted model with an OAI-compat server.
2. **Non-OAI-compatible (code-required for LiteLLM):** Needs a custom class with `validate_environment`, `get_complete_url`, `transform_request`, `transform_response`, streaming wrappers. **For Famit:** we replace this with a DB-stored JSONB field-map, applied at call time in Python — zero code deploy.

**Routing / fallback config (YAML→DB):**
```yaml
model_list:
  - model_name: my-model
    litellm_params: { model: openai/gpt-4o, api_key: os.environ/KEY, rpm: 100 }
  - model_name: my-model           # same alias = load-balanced
    litellm_params: { model: azure/gpt-4o-eu, api_base: https://..., rpm: 200 }
router_settings:
  routing_strategy: latency-based-routing
  allowed_fails: 3
litellm_settings:
  fallbacks: [{"my-model": ["fallback-model"]}]
```

**Health checks:** proxy polls each model's health endpoint; failing models are cooled down after `allowed_fails`. No restart required.

---

### FINDING 2 — OpenRouter: per-request provider routing via JSON body

**Source:** https://openrouter.ai/docs/guides/routing/provider-selection + https://openrouter.ai/docs/guides/overview/auth/byok + https://openrouter.ai/docs/guides/routing/private-models

Request-level `provider` object controls routing:
```json
{
  "model": "openai/gpt-4o",
  "provider": {
    "order": ["anthropic", "openai"],
    "allow_fallbacks": true,
    "sort": "price",
    "max_price": { "prompt": 5, "completion": 15 },
    "data_collection": "deny"
  }
}
```

**BYOK:** Per-user keys tried in priority order → OR-managed endpoints → fallback keys. This is the multi-tenant key injection pattern.

**Private Models (beta):** Route to self-hosted/fine-tuned endpoints through OR's API surface via config-driven named slug. Zero code.

**KEY INSIGHT FOR FAMIT:** The `provider` object maps to our framework's `routing_hint` on the Job row — the caller specifies capability preference; the registry resolves.

---

### FINDING 3 — Kong AI Proxy Advanced: the most complete per-target field-mapping config

**Source:** https://developer.konghq.com/plugins/ai-proxy-advanced/

`config.targets[]` — each target is a full provider spec:
```yaml
targets:
  - model:
      provider: openai         # or azure, anthropic, bedrock, gemini, huggingface, custom
      name: gpt-4o
      options: { temperature: 0.7 }
    auth: { allow_override: true }
    route_type: llm/v1/chat
```

**`llm_format` field:** Set to `anthropic|bedrock|cohere|gemini|huggingface` to pass natively (no OAI transformation). Set to `openai` (default) for OAI normalization. This is exactly our `transform_type` field.

**Load balancing algorithms:** round-robin, consistent-hashing, least-connections, lowest-latency, lowest-usage, semantic (by prompt similarity), priority (tiered failover).

**Failover criteria:** define which HTTP error codes trigger cascade to next target.

**Partials (v3.13+):** Shared `vectordb`, `embeddings`, `model` configs referenced across targets — equivalent of provider definition reuse.

---

### FINDING 4 — Bifrost: virtual keys + access profiles (best multi-tenant pattern)

**Source:** https://www.getmaxim.ai/articles/top-5-llm-gateways-in-2025-the-definitive-guide-for-production-ai-applications/ + https://github.com/maximhq/bifrost

Hierarchy:
```
Organization
  └── Access Profiles (provider + model + budget + rate-limit + MCP tools)
        └── Virtual Keys (per-tenant, distinct budget/RPM, auto-allocated)
```

Virtual keys = tenant-scoped tokens that inherit a profile's provider config but have own budget/RPM. When used, Bifrost resolves the actual provider key from vault — tenant never sees the real key.

**Health-aware routing:** adaptive LB on real-time latency, error rates, throughput. Circuit breaking removes failing providers automatically. 11µs overhead (Golang).

**KEY INSIGHT FOR FAMIT:** `provider_definitions` (the profile) + `provider_credentials` (per-tenant key binding) + `get_secret()` (key resolution) = Bifrost's architecture in our stack.

---

### FINDING 5 — Portkey: runtime-fetched secret references

**Source:** https://portkey.ai/blog/secret-references-ai-api-key-management/

Keys never stored in Portkey — store a pointer (vault path, auth method). At request time, the data plane fetches from AWS Secrets Manager / Azure Key Vault / HashiCorp Vault, uses it, caches 5 min. Workspace-scoped references enable per-tenant isolation.

**KEY INSIGHT FOR FAMIT:** This IS the `get_secret(tenant_id, key_type)` seam from the Vault plan. For now: AES-256-GCM in PG. Later: seam routes to HashiCorp/AWS without changing callers.

---

### FINDING 6 — SSRF: the #1 security risk for user-supplied endpoints

**Sources:** https://www.redveil.ai/additional-resources/vulnerabilities/preventing-ssrf-vulnerabilities + CVE-2025-59146 (authenticated LLM gateway SSRF → cloud metadata exfiltration) + CVE-2025-53767 (Azure OpenAI SSRF, CVSS 10.0)

CVE-2025-59146: An LLM gateway allowed arbitrary user-supplied `base_url` without validation → attackers exfiltrated cloud metadata tokens. **This is EXACTLY what our "add any self-hosted endpoint" feature will expose.**

**REQUIRED mitigations (defense in depth):**
1. **URL parse + normalize BEFORE validation** — `urllib.parse.urlparse()` + DNS resolve before comparing IP; prevents `http://evil.com@169.254.169.254/` tricks
2. **IP denylist (checked AFTER DNS resolution):**
   - Loopback: `127.0.0.0/8`, `::1`
   - RFC1918 private: `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`
   - Link-local / cloud metadata: `169.254.0.0/16`
   - This-network: `0.0.0.0/8`
3. **Protocol allowlist:** `https://` only for external; `http://` only if VPC-internal, gated separately
4. **Scheme allowlist:** reject `file://`, `ftp://`, `gopher://`, `dict://`
5. **DNS rebinding protection:** resolve hostname at validation AND at call time; if IP changes, reject
6. **Disable redirects:** `requests(allow_redirects=False)`; re-validate redirect target through same pipeline
7. **Content-Type + size limit** on responses (prevent exfiltration via large payload)
8. **PIN/firewall step-up gate** on "add provider endpoint" action (super-admin OR tenant PIN)
9. **Prompt injection guard:** user-supplied field-mapping strings treated as UNTRUSTED data; never `eval()`; use declarative jmespath only

---

### FINDING 7 — Three-tier field-mapping / request-response transformation model

**Synthesized from:** LiteLLM custom provider class, Kong `llm_format`, IBM mcp-context-forge adapter, strongdm/attractor unified LLM spec

**Tier 1 — OpenAI-compatible (zero transform, config-only):**
Provider speaks OAI chat-completions at `base_url`. No field mapping. Just `{base_url, api_key, auth_scheme: bearer}`. Covers Ollama, vLLM, Together, Fireworks, Fal.ai OAI-compat mode, Replicate OAI-compat endpoint, self-hosted LLaMA/Mistral/Qwen via text-generation-webui. This is ~90% of the 2025-2026 market.

**Tier 2 — Native format, known provider (named transform, one-dict-entry):**
Provider has a known documented format (Anthropic Messages, Google Gemini, AWS Bedrock). Gateway has built-in transform logic keyed by `provider_type` enum. Add a new known type = add one entry to `PROVIDER_TYPE_TRANSFORMS` dict. This IS a code deploy, but a trivial one (1 function, 1 test, 1 deploy).

**Tier 3 — Alien/custom format (JSONB field-map, fully config-driven, zero code deploy):**
Store `request_field_map: {model: "$.inputs.model", messages: "$.inputs.prompt", ...}` + `response_field_map: {content: "$.generated_text[0]", finish_reason: "$.details.finish_reason"}` as JSONB in PG. At call time: read map, apply jmespath transforms. Zero code deploy — the field map IS the code.

**The Famit framework supports all three tiers**, identified by `transform_type: openai_compat | named_provider | custom_field_map`.

---

### FINDING 8 — DB schema (synthesized canonical registry pattern)

**Sources:** LiteLLM model_list DB, Portkey virtual keys, Bifrost access profiles, glama.ai LLM credentials migration schema

```sql
-- Provider definition (reusable, _global or tenant-scoped)
CREATE TABLE provider_definitions (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id       TEXT NOT NULL,          -- '_global' for super-admin shared providers
  slug            TEXT NOT NULL,          -- e.g. 'openai-gpt4o', 'my-ollama'
  display_name    TEXT NOT NULL,
  provider_type   TEXT NOT NULL,          -- 'hosted_api' | 'self_hosted'
  capability      TEXT[] NOT NULL,        -- ['text_gen','video_gen','image_gen','embed','tts','stt']
  base_url        TEXT NOT NULL,          -- SSRF-validated on write
  auth_scheme     TEXT NOT NULL,          -- 'bearer' | 'api_key_header' | 'basic' | 'oauth2_cc' | 'none'
  auth_header_name TEXT,                  -- e.g. 'X-Api-Key' for non-standard headers
  transform_type  TEXT NOT NULL,          -- 'openai_compat' | 'named_provider' | 'custom_field_map'
  named_provider  TEXT,                   -- e.g. 'anthropic'|'gemini'|'bedrock'
  request_field_map  JSONB,              -- JMESPath map (custom_field_map tier only)
  response_field_map JSONB,
  cost_per_unit   NUMERIC(12,6),          -- USD per token/second/generation
  cost_unit       TEXT,                   -- 'per_1k_tokens'|'per_second'|'per_generation'
  health_check_url TEXT,
  health_check_interval_s INT DEFAULT 60,
  priority        INT DEFAULT 100,        -- lower = higher priority in fallback chain
  max_rpm         INT,
  is_enabled      BOOLEAN DEFAULT TRUE,
  created_at      TIMESTAMPTZ DEFAULT now(),
  updated_at      TIMESTAMPTZ DEFAULT now(),
  UNIQUE(tenant_id, slug)
);

-- Per-tenant encrypted credential binding
CREATE TABLE provider_credentials (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id           TEXT NOT NULL,
  provider_def_id     UUID REFERENCES provider_definitions(id) ON DELETE CASCADE,
  encrypted_api_key   BYTEA NOT NULL,     -- AES-256-GCM, AAD-bound
  key_nonce           BYTEA NOT NULL,
  key_aad             TEXT NOT NULL,      -- 'tenant_id||provider_def_id||version'
  key_version         INT DEFAULT 1,
  last_rotated_at     TIMESTAMPTZ,
  expires_at          TIMESTAMPTZ,
  is_active           BOOLEAN DEFAULT TRUE,
  created_at          TIMESTAMPTZ DEFAULT now()
);

-- Health log (circuit breaker input, FORCE-RLS, append-only)
CREATE TABLE provider_health_log (
  id              BIGSERIAL PRIMARY KEY,
  provider_def_id UUID REFERENCES provider_definitions(id),
  checked_at      TIMESTAMPTZ DEFAULT now(),
  is_healthy      BOOLEAN,
  latency_ms      INT,
  error_code      TEXT
);

-- RLS policies on all three tables (FORCE ROW LEVEL SECURITY)
-- _global providers: USING (tenant_id = current_setting OR tenant_id = '_global')
-- WITH CHECK: write-locked from '_global' by non-admin
```

---

### FINDING 9 — Capability system (consumer-facing contract)

Consumers declare a capability, not a provider name:
- `text_gen` — LLM chat/completions (voice brain, RAG grounding)
- `image_gen` — image generation (Creative Studio)
- `video_gen` — video generation (Video Studio — FIRST consumer)
- `tts` — text-to-speech
- `stt` — speech-to-text / transcription
- `embed` — text embeddings (RAG dense retrieval)
- `rerank` — reranking
- `tool_call` — function-calling capable model

`registry.get_provider(tenant_id, capability='video_gen', routing_hint=None)` → returns enabled provider(s), resolves credential via `get_secret()`, applies routing/fallback → returns a `ProviderClient`. This is the **universal connector seam**: Video Studio is the first consumer; every future consumer plugs in by declaring a capability.

---

### FINDING 10 — "No code deploy" — what it actually means (the hard limit)

**95% case — zero code deploy:**
- Any OAI-compat provider (90%+ of 2025-2026 market): pure config, `base_url` + `api_key`
- Any alien API: `custom_field_map` JSONB, admin fills in the jmespath map via UI form
- New tenant, new key, new capability binding: UI form → DB row → live

**5% case — one trivial code deploy:**
- Brand-new `named_provider` transform (alien API schema not covered by OAI-compat or existing named providers): add one dict entry to `PROVIDER_TYPE_TRANSFORMS`, 1 function, 1 test, deploy
- New capability enum value (e.g. `video_edit`): product decision + schema migration

---

### FINDING 11 — Health check + circuit breaker pattern

**Synthesized from:** Bifrost adaptive LB, LiteLLM `allowed_fails`+cooldown, Kong `failover_criteria`

1. Background task polls `health_check_url` every `health_check_interval_s` (default 60s). Result → `provider_health_log`.
2. Circuit breaker: N consecutive failures (default 3) → mark `is_circuit_open=True` in memory (not PG, to avoid write storms). Backoff: 60s → 120s → 240s (exponential).
3. Router skips open-circuit providers. After backoff, probe once — if healthy, close circuit.
4. Fallback chain: if primary circuit-open, try next provider with same capability (ordered by `priority` field).
5. All circuit events logged to `provider_health_log` (append-only, FORCE-RLS).

---

### CONCLUSION — the design synthesis

Production AI gateways (LiteLLM, OpenRouter, Kong AI Proxy Advanced, Bifrost, Portkey) converge on:

1. **PG-backed registry table** (not YAML) — runtime-addable, no restart, UI-driven via POST /model/new or equivalent
2. **Three-tier transform model:** OAI-compat (zero code) / named_provider (1 dict entry) / custom_field_map (JSONB jmespath, zero code)
3. **Capability-based consumer interface** — consumers request a capability, not a named provider; registry resolves + routes
4. **Envelope-encrypted credential storage** — AES-256-GCM, AAD-bound (tenant_id||provider_def_id||version), keyed by `get_secret()` seam
5. **SSRF prevention as first-class build requirement** — URL parse+normalize+DNS-resolve, RFC1918+link-local denylist, scheme allowlist, PIN step-up gate on endpoint add
6. **Health check + in-memory circuit breaker** — background probe, N-fail threshold, exponential backoff, fallback chain
7. **Virtual key / access profile hierarchy** (Bifrost model) — `provider_definitions` (profile) + `provider_credentials` (per-tenant key binding) + `capability` routing

**For Famit specifically:**
- Video Studio = first consumer of the universal capability interface; all future consumers (WhatsApp AI, voice LLM, email AI) plug in by declaring a capability
- `get_secret()` seam (Vault plan §C11) = the key resolution contract; for now AES-256-GCM in PG; Vault slots in without consumer changes
- SSRF guard is MANDATORY before any "add self-hosted endpoint" UI ships (CVE-2025-59146 is direct precedent)
- `custom_field_map` JSONB gives vendors true "connect any future tool" power without a code deploy

**Sources verified:**
- LiteLLM model management: https://docs.litellm.ai/docs/proxy/model_management
- LiteLLM proxy configs: https://docs.litellm.ai/docs/proxy/configs
- LiteLLM provider registration: https://docs.litellm.ai/docs/provider_registration/
- LiteLLM DB store setting: https://docs.litellm.ai/docs/proxy/ui_store_model_db_setting
- OpenRouter provider routing: https://openrouter.ai/docs/guides/routing/provider-selection
- OpenRouter BYOK: https://openrouter.ai/docs/guides/overview/auth/byok
- OpenRouter private models: https://openrouter.ai/docs/guides/routing/private-models
- Kong AI Proxy Advanced: https://developer.konghq.com/plugins/ai-proxy-advanced/
- Bifrost gateway: https://www.getmaxim.ai/articles/top-5-llm-gateways-in-2025-the-definitive-guide-for-production-ai-applications/
- Portkey secret references: https://portkey.ai/blog/secret-references-ai-api-key-management/
- SSRF prevention: https://www.redveil.ai/additional-resources/vulnerabilities/preventing-ssrf-vulnerabilities
- CVE-2025-59146 LLM gateway SSRF: https://cvefeed.io/vuln/detail/CVE-2025-59146
- PG column_encrypt v4.0: https://vibhorkumar.wordpress.com/2026/04/12/column_encrypt-v4-0-a-simpler-safer-model-for-column-level-encryption-in-postgresql/

---

## Phase: RESEARCH [byo-key-security]

### Verdict: Securely storing user-supplied API keys + self-hosted creds in a multi-tenant SaaS

Sources verified: OWASP SSRF Prevention Cheat Sheet, pgsodium GitHub, AWS RLS blog, Auth0 step-up docs,
OWASP LLM01:2025, envelope encryption deep-dives (tarangchikhalia/medium), Vault docs, GitGuardian 2025.

---

#### A. ENCRYPTION AT REST — 3-LAYER ENVELOPE (AAD-BOUND)

**The pattern (confirmed industry standard, not a draft)**:

```
KEK-0  (root, env-injected, 32 random bytes; absent/<32B → 503, NEVER plaintext)
  └─ wraps ─► KEK-1  per-tenant AES-256 key (stored encrypted in vault_keys table)
                └─ wraps ─► DEK  per-secret random AES-256 key
                              └─ AES-256-GCM encrypts ─► ciphertext (12-byte nonce prepended)
                                                          AAD = tenant_id ‖ secret_id ‖ version  ← MANDATORY
```

**AAD binding is the critical cross-tenant defense below RLS**: copying tenant-A's `encrypted_value`
into tenant-B's row → `InvalidTag` on decrypt (defends SQLi / box-level DB-write attacker).

**Key derivation options (sourced)**:
- Production: HKDF-SHA256 (RFC 5869) — constant-time, no iteration tuning needed, suitable for
  per-tenant key derivation from KEK-0. `info = b"famit-kek1:" + tenant_id.encode()`.
- Alternative for password-derived KEK: PBKDF2HMAC-SHA256 (100k iterations) or Argon2id
  (m=64MB, t=3) — Argon2id is recommended by OWASP for password hashing but adds ~200ms latency.
  Argon2id MAY wrap the DEK at rest for user-supplied keys in a premium vault; NEVER on the PIN
  or voice path.
- For PostgreSQL-native crypto: **pgsodium** (extension, libsodium wrapper) supports
  `derive_key(key_id bigint, len int, context bytea)` — deterministic derivation from a
  server-held root key; per-tenant context = 8-byte context ID. TCE (Transparent Column
  Encryption) automates encrypt-on-INSERT / decrypt-via-view. Key IDs live in DB; root key
  never accessible to SQL. This is the cleanest path for Postgres-resident secrets.

**Cipher**: AES-256-GCM (`cryptography.hazmat.primitives.ciphers.aead.AESGCM` in Python;
libsodium `crypto_aead_aes256gcm` on hardware-AES-capable boxes — DO KVM supports AES-NI).

**BYOK / Enterprise**:
- Standard tier: Platform-managed KEK-0 (env-injected, backed by DO encrypted volume + future KMS).
- Enterprise tier: Customer-managed KEK (BYOK via AWS KMS / Azure Key Vault). The DEK is wrapped
  under the customer's KMS key. Platform never sees the plaintext KEK — only wrap/unwrap API calls.
- This maps to the get_secret() seam: `vault.get_secret(tenant, key_type, scope)` calls the
  correct KEK unwrap path (platform vs BYOK) transparently.

---

#### B. PER-TENANT ISOLATION — POSTGRES RLS + FORCE-RLS

**Confirmed canonical pattern (AWS RLS blog, oneuptime, supabase)**:

```sql
ALTER TABLE vault_secrets FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_iso ON vault_secrets
  USING (tenant_id = current_setting('app.tenant_id', true));
```

Critical nuances:
1. `FORCE ROW LEVEL SECURITY` bypasses the table-owner exemption. Without it, the app role
   (which may own the table) sees all rows.
2. `current_setting('app.tenant_id', true)` is set per-connection via `SET app.tenant_id = ...`
   before any query — driven by `resolve_tenant()` from JWT (never request body).
3. PostgreSQL superuser and `BYPASSRLS` roles bypass all policies. App role must be NOSUPERUSER +
   NOBYPASSRLS (confirmed in Famit live `db/rls.sql` pattern).
4. pgsodium extends this: each row stores its `key_id` (UUID referencing `pgsodium.key`), and
   pgsodium derives the actual key from the root server key + key_id at decrypt time. Even a full
   DB dump is inert without the server root key.

**Separate read path for super-admin** (anti-C9 pattern from VAULT-MASTER-PLAN):
- Tenant reads in `store.py` with `is_admin=False` HARDCODED.
- Super-admin reads in a separate `admin_store.py`, mounted ONLY under `require_super_admin`.
- A tenant route physically cannot import the admin reader — prevents privilege escalation via
  import or parameter manipulation.

---

#### C. PIN-GATED / STEP-UP AUTH FOR REVEAL

**Pattern (Auth0 docs + Famit live firewall.py)**:

1. User requests a sensitive action (e.g. REVEAL plaintext key, ROTATE, REVOKE).
2. System issues a step-up challenge → user provides PIN (or TOTP / FIDO2 for higher tier).
3. Successful challenge → server mints a short-lived, narrow-scope step-up token:
   - HS256, sub=caller_id, scope=`vault.reveal`, aud=`secret_id` (binds reveal to ONE secret),
   - TTL=60s (not 300s — reduce replay window), jti=random UUID.
4. The step-up token is consumed atomically in `vault_used_jti` (PG table, PRIMARY KEY on jti)
   on first REVEAL use → `INSERT OR CONFLICT → denied` pattern, no Redis dependency.
5. REVEAL returns plaintext only over TLS. Response is NOT cached. Logged immediately.

**Rate limiting on step-up mint** (anti-brute-force, anti-C10):
- Per-tenant, per-scope, 5-attempt / 15-minute window in Redis or PG (reuse existing wallet
  idempotency pattern).

**PIN storage**:
- Live Famit: SHA-256 salted (firewall.py:95). Acceptable for a 6-digit numeric PIN only IF
  the rate-limit is enforced. For longer passphrases or higher-security tiers, upgrade to
  Argon2id (m=64MB, t=3) on the PIN hash column — additive, no schema break.

**Step-up token upgrade path**:
- Phase 1 MVP: TOTP (HMAC-SHA1, RFC 6238) via any authenticator app — no FIDO2 device required.
- Phase 2: FIDO2 / WebAuthn — phishing-resistant, private key never leaves device. Preferred for
  enterprise admin / super-admin reveal of master credentials.

---

#### D. SSRF + PROMPT INJECTION GUARDS ON USER-SUPPLIED ENDPOINTS

This is the highest-severity novel attack surface in the Provider Framework (self-hosted models).

**SSRF — 5 defense layers (sourced: OWASP SSRF Cheat Sheet)**:

Layer 1 — Input parsing (never trust user URL):
- Do NOT accept raw URLs. Accept `host` + `port` + `path` as SEPARATE validated fields.
  Reassemble server-side from validated components.
- `host`: validate with `validators.domain` (Python) or equivalent; reject if resolves to
  RFC1918 (10/8, 172.16/12, 192.168/16), loopback (127/8, ::1), link-local (169.254/16),
  or cloud metadata (169.254.169.254).
- `port`: allowlist only 80, 443, and user-configured custom port within 1024–65535.
- `protocol`: allowlist HTTP and HTTPS ONLY.

Layer 2 — DNS validation (anti-DNS-rebinding):
- Resolve the domain in-process using `ipaddress.ip_address(socket.getaddrinfo(...))`.
- Check ALL A + AAAA records against the denylist (not just the first).
- Disable automatic HTTP redirects in the outbound client (requests: `allow_redirects=False`).
- On redirect: re-validate the target URL through the same pipeline.

Layer 3 — Network egress (infra):
- The provider-framework worker/runner process must run in a network namespace with a firewall
  rule that ONLY allows outbound to: (a) explicitly registered vendor endpoints, (b) the Famit
  internal backend. Block all RFC1918 and metadata endpoints at the firewall level regardless
  of application validation.

Layer 4 — Health-check sandbox:
- When a vendor/super-admin registers a new self-hosted endpoint, the system runs a
  health-check probe in a sandboxed worker (separate process, separate network namespace,
  10s timeout). Health-check only sends a minimal payload (model metadata request). Full
  inference calls are blocked until health-check passes.

Layer 5 — Prompt injection through model responses:
- Responses from user-registered models are UNTRUSTED. They must NOT be passed directly into
  subsequent system prompts, tool calls, or database writes without sanitization.
- Techniques (OWASP LLM01:2025): spotlighting (wrap external content with clear delimiters:
  `<external_model_response>...</external_model_response>`), output schema validation
  (response must conform to expected JSON schema; reject non-conforming outputs), least-privilege
  (the provider-framework worker has read-only access to secrets; it cannot write to vault,
  trigger calls, or access other tenants' data).
- For connector configs (request/response field mappings): treat all user-supplied field-mapping
  strings as UNTRUSTED data, not as code. Never `eval()`. Use declarative JSONPath / jmespath
  mappings only.

---

#### E. AUDIT LOGGING FOR SECRET ACCESS

**Requirements (sourced: Vault docs, GitGuardian, IBM Secrets API)**:

Every secret access event MUST log:
- `who`: accessor_id (JWT sub), accessor_ip, user-agent
- `what`: action (READ|WRITE|ROTATE|REVOKE|REVEAL|HEALTH_CHECK|FREEZE), secret_name, key_type
- `when`: at (timestamptz, nanosecond-sourced primary key hash)
- `result`: OK | DENIED | ERROR (NEVER the plaintext value)
- `context`: request_id, tenant_id, version, step_up_jti (for REVEAL)

**Append-only enforcement (two layers)**:
1. `REVOKE UPDATE, DELETE ON vault_access_log FROM famit_app` — PG RBAC.
2. `BEFORE UPDATE OR DELETE ... RAISE EXCEPTION 'vault_access_log is append-only'` — PG trigger
   (guards against a future role escalation that bypasses RBAC).

**SIEM export**: Hatchet job exports `vault_access_log` rows >24h old to DO Spaces (NDJSON, gzip),
for SOC2 compliance and incident forensics. The export job runs with super-admin credentials and
logs its own run to the audit ledger.

**Cross-tenant log isolation**: `vault_access_log` FORCE-RLS — tenant sees only their own rows.
Super-admin sees all via `is_admin=True` path (admin_store.py only).

---

#### F. THE get_secret() SEAM (Vault-backed, swappable)

**The clean abstraction** (allows swapping Vault → AWS Secrets Manager → HashiCorp Vault → env-fallback):

```python
# vault/seam.py  — the ONLY import consumers use
async def get_secret(
    tenant_id: str,
    key_type: str,        # enum: ai_provider | self_hosted | database | ...
    scope: str,           # calling context: 'llm_router' | 'video_worker' | 'wa_connector'
    is_admin: bool = False,
) -> str:
    """
    Returns decrypted plaintext. Raises SecretNotFound | SecretRevoked | VaultDisabled.
    NEVER returns None — callers must handle exceptions explicitly (fail-closed).
    """
    backend = _resolve_backend()   # reads VAULT_BACKEND env: 'local' | 'hashicorp' | 'aws' | 'azure'
    return await backend.get(tenant_id, key_type, scope, is_admin)
```

**Backend implementations** (all implement the same `SecretsBackend` ABC):

| Backend | When to use | Notes |
|---|---|---|
| `LocalVaultBackend` | Default (Famit today) | AES-256-GCM envelope, PG store, per-tenant KEK-1 |
| `HashiCorpVaultBackend` | Self-hosted enterprise | KV v2 at `secret/tenants/{tenant_id}/{key_type}` |
| `AWSSecretsBackend` | AWS-native tenants | `/{tenant_id}/{key_type}` path, IAM-role access |
| `EnvFallbackBackend` | CI / dev / migration | Reads `.env` — DISABLED in production (VAULT_BACKEND=local rejects fallback) |

**Vault slot-in**: When the Vault product is built (Wave #10), `VAULT_BACKEND=local` continues to
point to `LocalVaultBackend` — the seam is already there. Migrating a consumer to Vault = changing
`VAULT_BACKEND` env and running the migration job; zero consumer code changes.

**Failure posture**: `get_secret()` raises, never returns empty string or None. Every caller must
handle `SecretNotFound` and fail-closed (abort the job, do not proceed with empty credential).
`VaultDisabled` → return 503 to the end user (not 500; it's a configuration state, not a bug).

---

#### G. KEY FINDINGS — ADVERSARIAL VERIFICATION

Claim: "AES-256-GCM is sufficient without AAD for per-tenant isolation."
Verdict: REFUTED. Without AAD bound to `(tenant_id, secret_id, version)`, a ciphertext is
portable — an attacker who writes to another tenant's row (SQLi) can swap ciphertexts and decrypt
under a different tenant's KEK. AAD is mandatory. [Source: VAULT-MASTER-PLAN §C6, AES-GCM spec]

Claim: "RLS alone is sufficient; no application-layer tenant check needed."
Verdict: REFUTED. RLS requires `FORCE ROW LEVEL SECURITY` to cover the table owner. Superuser
bypasses ALL policies. Defense-in-depth requires: RLS + `resolve_tenant()` JWT check +
NOSUPERUSER app role. [Source: AWS RLS blog, pgsodium docs]

Claim: "A 300-second step-up token with no jti consume is acceptable."
Verdict: REFUTED. A leaked step-up token is replayable for 5 minutes. For REVEAL (plaintext
key returned), this is catastrophic. Required: 60s TTL + single-use jti consumption + scope
bound to specific secret_id. [Source: VAULT-MASTER-PLAN §C3, Auth0 step-up pattern]

Claim: "SSRF can be prevented by blocking 127.0.0.1 and 169.254.169.254 in the application."
Verdict: PARTIALLY REFUTED. DNS rebinding and alternative IP representations (hex, octal, dword,
IPv6 encoded) bypass naive denylist checks. Correct approach: validate + resolve + re-check
all A+AAAA records for RFC1918/metadata + disable redirects + network-level egress firewall.
[Source: OWASP SSRF Cheat Sheet]

Claim: "Prompt injection from a user-supplied model endpoint is low risk."
Verdict: REFUTED. LLM SSRF is OWASP LLM01:2025 #1. A malicious model endpoint can inject
instructions into the response that propagate into subsequent tool calls, DB writes, or
other tenants' contexts. Responses from user-registered models are UNTRUSTED data.
[Source: OWASP LLM01:2025, invicti OWASP Top 10 LLM 2025]

---

#### H. DESIGN DECISIONS FOR THIS CODEBASE

1. Reuse `cryptography` package (already in venv via `key_store.py:48`) — no new dep for AES-GCM.
2. Reuse `firewall.py` step-up — add `vault.reveal` to `_DESTRUCTIVE_ACTIONS`, reduce TTL to 60s,
   add `aud=secret_id` claim, add `vault_used_jti` consume table.
3. Reuse `engine.session(is_admin=False)` GUC pattern — all vault store reads are is_admin=False.
4. The `get_secret()` seam lives in `droplet_work/vault/seam.py` — Video Studio worker,
   LLM router, WA connector, RAG pipeline all import from here and nowhere else.
5. SSRF guard lives in `droplet_work/vault/ssrf_guard.py` — a pure function
   `validate_endpoint(host, port, protocol) -> bool` called by the provider-registry write path.
6. pgsodium is the preferred path IF the PG version and DO managed DB support it; otherwise
   the Python AES-256-GCM envelope in `crypto.py` is equivalent and self-contained.

---

## Phase: RESEARCH [self-hosted-serving]

**Topic:** Self-hosting inference servers — endpoint contracts, health-check, registration flow, field-mapping for the Universal Provider Registry.
**Date:** 2026-06-14. All claims adversarially verified. Sources cited inline.

---

### ENDPOINT CONTRACTS BY SERVER

**vLLM**
- Default port: 8000. Base URL: `http://<host>:8000`
- OpenAI-compat routes: `POST /v1/chat/completions`, `POST /v1/completions`, `POST /v1/embeddings`, `GET /v1/models`
- Auth: `--api-key <secret>` flag or `VLLM_API_KEY` env → `Authorization: Bearer <key>` on ALL `/v1/*` paths
- Health: `GET /health` → 200 when model loaded. CRITICAL VERIFIED FACT: `/health` is UNAUTHENTICATED even when `--api-key` is set. The auth middleware only intercepts paths starting with `/v1`. Use `/health` as the liveness probe; use `GET /v1/models` (with Bearer) as the readiness probe. Known production bug: production-stack router issue #631 — health checks fail when API key is set if the probe uses a `/v1/*` path.
- Metrics: `GET /metrics` → Prometheus
- Field coverage vs OpenAI: streaming function calls NOT supported as of v0.8.0; otherwise full parity
- `model` field: set to whatever name was passed at server launch; vLLM serves only what it loaded

**Ollama**
- Default port: 11434. Base URL: `http://<host>:11434`
- Health: `GET /` → 200 + body `"Ollama is running"`; `GET /api/ps` → loaded models + VRAM
- Native routes:
  - `GET /api/tags` → `{models:[{name,size,digest,modified_at}]}` — list pulled models (capability probe)
  - `POST /api/chat` → `{model,messages[],stream,options}` → `{message:{role,content},done,total_duration,eval_count}`
  - `POST /api/generate` → `{model,prompt,stream,options}` → `{response,done,eval_count}`
  - `POST /api/embeddings` → `{model,prompt}` → `{embedding:float[]}`
  - `POST /api/pull` → streaming download progress
  - `GET /api/ps` → running models with VRAM usage
- OpenAI-compat route: `POST /v1/chat/completions` → full OpenAI shape (VERIFIED working 2025)
- Auth: NONE built-in. Any `api_key` value is accepted/ignored. MUST use reverse proxy for external exposure.
- KEY QUIRK: models must be pre-pulled. Framework must probe `GET /api/tags` on registration to enumerate available models.

**TGI (HuggingFace Text Generation Inference)**
- STATUS: IN MAINTENANCE MODE as of Nov 2025 (confirmed by HF team tweet + docs). Only minor bugfixes. Recommended migration: vLLM or SGLang. Include in framework for legacy support only.
- Default port: 3000 (Docker default). Base URL: `http://<host>:3000`
- Native routes:
  - `POST /generate` → `{inputs:string, parameters:{max_new_tokens,temperature,top_k,top_p,return_full_text,details,seed}}` → `{generated_text:string}`
  - `POST /generate_stream` → same request, SSE stream
  - `GET /health` → 200 when healthy
  - `GET /info` → `{model_id,model_sha,max_concurrent_requests,max_input_length,max_total_tokens,...}`
  - `GET /metrics` → Prometheus
  - `GET /docs` → Swagger UI (live authoritative spec)
- OpenAI-compat (v1.4.0+): `POST /v1/chat/completions` → full OpenAI shape; model field = `"tgi"` placeholder
- Auth: none built-in; `--huggingface-hub-token` for gated model download only. Secure via reverse proxy.
- Field-mapping required (native path): `inputs` ← our `prompt`; `generated_text` → our `content`

**AUTOMATIC1111 / stable-diffusion-webui**
- Default port: 7860. Base URL: `http://<host>:7860`
- MUST launch with `--api` flag. Also `--listen` for non-localhost. `--api-auth user:pass` for basic auth (cleartext — enforce TLS).
- Routes:
  - `POST /sdapi/v1/txt2img` → `{prompt,negative_prompt,steps,width,height,cfg_scale,sampler_name,seed,override_settings:{sd_model_checkpoint}}` → `{images:[base64_png],parameters:{},info:string_json}`
  - `POST /sdapi/v1/img2img` → same + `{init_images:[base64],denoising_strength}`
  - `GET /sdapi/v1/sd-models` → `[{title,model_name,hash,sha256,filename}]` (capability + readiness probe)
  - `GET /sdapi/v1/samplers` → sampler list
  - `POST /sdapi/v1/options` → change active checkpoint (slow; use `override_settings` per-request instead)
  - `GET /docs` → Swagger UI (live spec — use as authoritative reference)
- Health: NO dedicated `/health`. Use `GET /sdapi/v1/sd-models` → 200 when fully loaded (returns 503 or hangs when model loading)
- Response images: base64-encoded PNG strings in `images[]` array. Decode + upload to Spaces.

**ComfyUI**
- Default port: 8188. Base URL: `http://<host>:8188`
- NO built-in auth. ACTIVELY EXPLOITED (GHOST botnet crypto-miner campaign targeting exposed ComfyUI servers, 2025). MUST run localhost-only + reverse proxy with auth for any production deployment.
- Core routes:
  - `POST /prompt` → `{prompt:workflow_graph_json, client_id?:uuid, extra_data?:any, front?:bool}` → `{prompt_id:uuid, number:int, node_errors:{}}`; 400 on validation failure with per-node errors
  - `GET /queue` → `{queue_running:[...], queue_pending:[...]}` — also works as liveness probe
  - `GET /history/{prompt_id}` → `{}` (pending/unknown) OR `{prompt_id:{outputs:{node_id:{images:[{filename,subfolder,type}]}}, status:{status_str:"success"|"error"}}}`
  - `POST /upload/image` → multipart → `{name,subfolder,type}`
  - `GET /view?filename=&subfolder=&type=output` → raw image/video bytes (for retrieval after completion)
  - `GET /object_info` → full node catalogue JSON (10–50 MB; cache on framework startup)
  - `GET /object_info/{node_class}` → 404 if missing (CAPABILITY PROBE: `WanVideoWrapper`, `LTXVideoSampler`, `MochiSampler`)
  - `GET /system_stats` → `{os,python_version,cuda,devices:[{name,type,total_vram,free_vram}]}` (health/readiness probe)
  - `GET /models/{type}` → filenames for checkpoints/loras/vae/controlnet/etc.
  - `POST /free` → `{unload_models:bool,free_memory:bool}`
- Async completion pattern:
  1. `POST /prompt` → get `prompt_id`
  2. Poll `GET /history/{prompt_id}` every 2–3s until non-empty OR
  3. Connect WebSocket `ws://host:8188/ws?clientId=<uuid>` → listen for `executing` event with `data.node=null` and matching `prompt_id` → complete. Also emits `progress`, `execution_error`, `execution_interrupted`.
- Workflow JSON format: graph where keys = node IDs (strings), values = `{class_type:string, inputs:{field:value|[node_id,output_slot]}}`. Must be exported in "API Format" (developer mode in UI).

---

### VIDEO GENERATION (Wan2.1 / LTX-Video / Mochi) — self-hosted API

These models do NOT ship with their own HTTP servers. Two options:

**Option A: ComfyUI as HTTP gateway (dominant production pattern)**
- Install model weights + custom nodes (WanVideoWrapper for Wan2.1, LTX-Video nodes, Mochi nodes) on the ComfyUI instance.
- Submit video-generation workflow JSON via `POST /prompt`.
- Poll `/history/{prompt_id}` for output video filename.
- Fetch video via `GET /view?filename=...&type=output` → MP4/WebM bytes → upload to DO Spaces.
- Capability probing: `GET /object_info/WanVideoWrapper` (Wan2.1), `GET /object_info/LTXVideoSampler` (LTX), `GET /object_info/MochiSampler` (Mochi). 404 = not installed; 200 = available.
- Hardware gates: Wan2.1 1.3B = 8GB VRAM; 14B = 40–80GB VRAM. LTX-Video = ~8GB. Mochi 1 = 24GB.
- The framework `GET /system_stats` probe gives `free_vram` before submission.

**Option B: Custom FastAPI wrapper (for headless serving without ComfyUI)**
- Pattern: wrap the Diffusers pipeline in FastAPI. `POST /generate` → `{prompt,duration_s,...}` → async job_id assigned → Redis queue → GPU worker → MP4 bytes or presigned URL.
- No standard protocol — each deployment is bespoke. Framework must support `provider_type=self_hosted_generic` with `request_field_map` + `response_field_map` JSONB config.

---

### HEALTH-CHECK STRATEGY PER PROVIDER TYPE

| Provider | Liveness probe | Readiness probe |
|---|---|---|
| vLLM | `GET /health` (unauthenticated, always safe) | `GET /v1/models` with Bearer token |
| Ollama | `GET /` → "Ollama is running" | `GET /api/tags` → check model name in list |
| TGI | `GET /health` → 200 | `GET /info` → `model_id` field |
| A1111 | `GET /sdapi/v1/sd-models` → 200 | Same — lists models when fully loaded |
| ComfyUI | `GET /queue` → 200 | `GET /system_stats` → devices list with VRAM |
| Generic | Configurable `health_path` field in registry | Configurable `ready_path` + `ready_json_probe` |

---

### UI REGISTRATION FLOW (derived from Open WebUI + LiteLLM patterns)

Form fields per self-hosted provider registration:
- `provider_type`: enum (self_hosted_openai_compat | self_hosted_comfyui | self_hosted_a1111 | self_hosted_tgi_native | self_hosted_generic)
- `base_url`: `http://host:port` — NO trailing slash, NO /v1 suffix (appended by adapter)
- `api_key`: optional, encrypted at rest
- `model_name`: the `model=` field value for openai-compat; for comfyui: ignored (node-based)
- `capabilities`: multiselect (text_gen | image_gen | video_gen | embeddings)
- `workflow_json`: ComfyUI only — the API-format workflow graph (text field, large)
- `request_field_map`/`response_field_map`: JSONB, generic tier only
- `health_path`: overridable (defaults by type as table above)
- `cost_per_unit`: decimal; `cost_unit`: enum

**Test Connection validation steps (on button click):**
1. SSRF guard (reject private IPs unless super-admin + `allow_private_networks=true`; scheme allowlist)
2. `GET {base_url}{health_path}` → must return 2xx within 5s
3. Type-specific readiness probe (as table above)
4. Capability probe (OpenAI: `/v1/models`; ComfyUI: `/object_info/{node_class}`; A1111: `/sdapi/v1/sd-models`)
5. Show result: "Connected — model X ready — VRAM Y GB free" or error with raw HTTP status

---

### FIELD-MAPPING ADAPTER LAYER

Standard internal request envelope (our framework always sends this):
```
capability: text_gen|image_gen|video_gen|embed
prompt: string
negative_prompt: string
model: string
params: {max_tokens, temperature, width, height, steps, duration_s}
```

Per-provider wire translation:

| Our field | vLLM/Ollama (openai-compat) | A1111 | TGI native | ComfyUI |
|---|---|---|---|---|
| `prompt` | `messages[user].content` | `prompt` | `inputs` | workflow node text input |
| `model` | `model` | `override_settings.sd_model_checkpoint` | ignored ("tgi") | node class_type |
| `max_tokens` | `max_tokens` | n/a | `parameters.max_new_tokens` | node param |
| `temperature` | `temperature` | n/a | `parameters.temperature` | node param |
| `width`/`height` | n/a | `width`/`height` | n/a | `EmptyLatentImage` node inputs |
| `duration_s` | n/a | n/a | n/a | video sampler node param |

Standard internal response envelope (every adapter returns this):
```
text, image_url, video_url, embedding[], usage:{input_tokens,output_tokens}, cost_minor, latency_ms, provider_job_id
```

---

### ADVERSARIAL VERIFY RESULTS

| Claim | Verdict |
|---|---|
| vLLM `/health` is unauthenticated even with `--api-key` set | CONFIRMED — middleware only fires on `/v1/*` prefix; production-stack issue #631 documents this |
| TGI is in maintenance mode | CONFIRMED — HF team tweet Nov 2025; HF docs state "maintenance mode"; migrate to vLLM/SGLang |
| Ollama `/v1/chat/completions` works with OpenAI SDK | CONFIRMED — official Ollama docs + 2025 guides |
| ComfyUI ships with zero auth | CONFIRMED — SECURITY.md + GHOST botnet active exploitation 2025 |
| A1111 requires `--api` flag at launch | CONFIRMED — GitHub wiki + multiple 2025 deployment guides |

---

### SOURCES

- vLLM security/auth: https://docs.vllm.ai/en/stable/usage/security/
- vLLM health unauthenticated (production-stack issue #631): https://github.com/vllm-project/production-stack/issues/631
- Ollama REST API reference: https://mljourney.com/ollama-rest-api-reference-every-endpoint-with-examples/
- Ollama OpenAI compat: https://docs.ollama.com/api/openai-compatibility
- TGI Messages API: https://huggingface.co/docs/text-generation-inference/en/messages_api
- TGI HTTP API reference: https://huggingface.co/docs/text-generation-inference/en/reference/api_reference
- TGI maintenance mode: https://x.com/LysandreJik/status/1999137874378125436
- A1111 API wiki: https://github.com/AUTOMATIC1111/stable-diffusion-webui/wiki/API
- ComfyUI REST API reference (DeepWiki): https://deepwiki.com/Comfy-Org/ComfyUI/7.1-rest-api-reference
- ComfyUI production API guide: https://www.runflow.io/blog/comfyui-api-endpoints
- ComfyUI GHOST botnet exploitation: https://www.ppln.co/en/post/comfyui-security-japan-ghost-eng
- Open WebUI image generation registration: https://docs.openwebui.com/troubleshooting/image-generation/
- Video model self-hosted serving (AMD ROCm): https://rocm.blogs.amd.com/artificial-intelligence/serving-videogen-v1/README.html
- ComfyUI Wan2.1 workflow: https://docs.comfy.org/tutorials/video/wan/wan-video
- Self-hosted OAI-compatible guide: https://gigagpu.com/openai-compatible-api-self-hosted-guide/

*Appended by: deep-research subagent, 2026-06-14*

---

## Phase: RESEARCH [connector-integration-framework]

**Topic:** How n8n, Zapier, Pipedream, Workato, LiteLLM model "connect to any tool" — credential types,
OAuth vs API-key vs self-hosted, action/trigger schemas, field-mapping, security (encryption at rest,
SSRF guards, injection protection, tenant isolation), health-check patterns, cost/rate-limit handling.
What Famit adopts for its config-driven universal provider registry.
**Date:** 2026-06-14.

---

### A. n8n — the reference open-source credential + node descriptor model

**Node descriptor JSON (`INodeTypeDescription`)** — fully serializable, transferred to frontend for UI rendering:
- `name`: `packageName.nodeName` (e.g. `n8n-nodes-base.httpRequest`)
- `displayName`, `description`, `version`
- `properties`: `INodeProperties[]` — declares every UI input field (type, options, default, display conditions)
- `credentials`: `INodeCredentialDescription[]` — which auth slots the node requires
- `inputs`/`outputs`: data-flow connectors

**`ICredentialType` — the credential blueprint class:**
- `authenticate` property: declarative `generic` mode maps fields → HTTP headers / query params / basic-auth.
  OAuth1 → `OAuth1CredentialController`; OAuth2 → `@n8n/client-oauth2` (PKCE, JWE token decryption).
- `test` property: lightweight GET to `/me` or `/status` — runs on credential save (built-in health-check on registration).
- Sensitive fields: `typeOptions: { password: true }` → redacted as `***` (CREDENTIAL_BLANKING_VALUE) in all
  frontend transfers and logs. `redact`/`unredact` methods in `CredentialsService`.
- `extends = ['oAuth2Api']`: inherit n8n's native OAuth2 handler.

**Encryption at rest:**
- `N8N_ENCRYPTION_KEY` env var: AES encrypts credential values before DB write; decrypted only at run-time
  in process memory, then passed to node. Without this var → stored plain text (production risk).
- Enterprise: `validateExternalSecretsPermissions` → injectable via AWS Secrets Manager / Vault at runtime.
  Decouples key from filesystem.
- Key rotation: documented procedure for rotating `N8N_ENCRYPTION_KEY` without losing credential access.

**Multi-tenant isolation:**
- `@ProjectScope('credential:read')` decorator — Tenant A cannot read Tenant B's credentials.
- `findAllGlobalCredentials`: admin-only path for platform-level shared credentials.

**Sources:** [n8n Credential System](https://deepwiki.com/n8n-io/n8n/4.4-credential-system-for-nodes) |
[n8n Node Type System](https://deepwiki.com/n8n-io/n8n/4.1-node-type-system-and-registration) |
[n8n Encryption Key Guide](https://rolandsoftwares.com/content/n8n-encryption-key-guide/) |
[n8n Encryption Key Rotation](https://docs.n8n.io/hosting/securing/encryption-key-rotation/)

---

### B. Zapier — auth-type taxonomy + server-side injection model

Developer declares ONE auth type at app registration:
1. **OAuth 2.0 Authorization Code** — state param mandatory (anti-CSRF, cannot be disabled). Zapier manages
   token store + refresh. User authenticates on 3rd-party site; no password ever shared.
2. **API Key** — static key; scope options (read-only / write / read-write); multiple keys for selective revocation.
3. **Session Auth** — username/password → exchanged for session token server-side.
4. **Basic Auth** — not recommended for new apps.

Hybrid is valid: GitHub uses OAuth for 3rd-party apps + personal access tokens for devs.

**Credential store architecture:**
- Zapier stores + refreshes keys centrally. App code never receives raw credentials — injected at
  request-build time entirely server-side. Raw key never crosses the wire to the app developer.
- OAuth2 scope granularity: user sees exactly what data Zapier requests on auth screen.

**Sources:** [Zapier Engineering — API Authentication](https://zapier.com/engineering/api-authentication/) |
[Zapier OAuth v2 Docs](https://docs.zapier.com/platform/build/oauth) |
[Switch Labs — OAuth Security in Zapier](https://www.switchlabs.dev/resources/mastering-oauth-authentication-in-zapier-webhooks-for-enhanced-security)

---

### C. Pipedream — component-as-descriptor + runtime-only auth injection

```js
export default defineComponent({
  type: "action",   // omit for sources/triggers
  props: {
    myApp: { type: "app", app: "slack" },        // managed auth: Pipedream handles OAuth + storage
    myParam: { type: "string", label: "..." },
    secret: { type: "string", secret: true }      // encrypted in DB, decrypted at exec only
  },
  async run({ steps, $ }) {
    const token = this.myApp.$auth.oauth_access_token;  // injected at runtime, NOT held in memory
  }
})
```
- `type: "app"` prop: Pipedream manages full OAuth flow, token storage/refresh; injects `$auth` into
  execution context only. Component never stores the raw token beyond request scope.
- `secret: true` on string props: encrypted in DB, decrypted only at runtime. Not logged, not returned to client.
- Prop size limit: 64KB (prevents abuse). Env vars NOT accessible within sources/actions (prevents leakage).
- Multi-tenant (Pipedream Connect): scoped by `external_user_id` — credentials are per-user-per-app.
  Leaking between tenants = breach, not a bug. SOC 2 Type II, HIPAA, GDPR compliant.
- External secret backends supported: Nango, AWS Secrets Manager, HashiCorp Vault, Doppler, or custom DB.

**Sources:** [Pipedream Component API](https://pipedream.com/docs/components/api) |
[Pipedream Connect](https://pipedream.com/connect) |
[Truto Blog — MCP Platforms 2026](https://truto.one/blog/best-mcp-server-platform-for-ai-agents-connecting-to-enterprise-saas/)

---

### D. Workato — universal connector by protocol type

Four connector paradigms driven by API protocol:
1. **HTTP Connector** — any REST, handles auth models + content types
2. **OpenAPI Universal Connector** — upload spec → auto-generate actions/triggers
3. **GraphQL Universal Connector**
4. **SOAP/WSDL Universal Connector**

Custom actions declare `auth_type` once at connector level; reused across all actions in that connector.
OpenAPI spec import is the highest-leverage pattern: upload a spec, auto-generate action schema
(endpoint, params, request/response field mapping). Connector handles authorization flow, developer
focuses on HTTP request/response shape only.

**Source:** [Workato Universal Connectors](https://docs.workato.com/developing-connectors.html)

---

### E. LiteLLM — config-driven AI provider registry (closest analogue for Famit's provider_registry)

Full coverage in prior `RESEARCH [self-hosted-serving]` and `CONCLUSION` phases above. Summary here:
```yaml
model_list:
  - model_name: "gpt4-alias"              # user-facing name / alias
    litellm_params:
      model: "openai/gpt-4o"              # provider/model-id
      api_base: "https://custom.host/v1"  # self-hosted endpoint override
      api_key: "os.environ/OPENAI_KEY"    # env-var reference, NEVER hardcoded
      rpm: 100                             # rate limit: requests/minute
      tpm: 50000                           # rate limit: tokens/minute
```
Key architecture decisions: `api_base` for any self-hosted endpoint; `os.environ/VAR` decouples secrets
from config; virtual keys per tenant with budget tracking; `model_info.access_groups` for access control;
`credential_list` prevents cross-tenant leakage.

**Sources:** [LiteLLM Proxy Config](https://docs.litellm.ai/docs/proxy/configs) |
[LiteLLM OpenAI-Compatible](https://docs.litellm.ai/docs/providers/openai_compatible)

---

### F. SSRF — new confirmed exploits (additional evidence for the framework design)

The prior `RESEARCH [byo-key-security]` phase (§D above) covers the 5-layer defense. This phase adds
confirmed 2025-2026 real-world exploits:

- **LiteLLM RAG endpoint (May 2026):** `file_url` accepted without validation. Attacker caused LiteLLM
  server to fetch arbitrary internal URLs. No allowlist, no scheme restriction, no DNS validation.
  [Security Boulevard 2026-05-xx]
- **LangChain `APIChain`:** `api_url` retrieved from LLM output, passed directly to HTTP client — SSRF.
  [GitHub langchain-ai/langchain #6224]
- **`mcp-from-openapi`:** `$ref` dereferencing in untrusted OpenAPI specs fetches arbitrary URLs at init.
  [GitLab CVE-2026-26013]
- **`ChatOpenAI.get_num_tokens_from_messages()`:** `image_url` field fetched without validation → SSRF.

**Portkey AI Gateway SSRF fix (PR #1372) — production reference implementation:**
```
# TRUSTED_CUSTOM_HOSTS env var: comma-separated allowlist
TRUSTED_CUSTOM_HOSTS=api.openai.com,api.anthropic.com,my-self-hosted.internal
```
- Header `x-portkey-custom-host` validated against allowlist.
- Regex detects alternative IP representations (hex, octal, decimal-encoded bypass attempts).
- Private ranges (127.x, 10.x, 172.16-31.x, 192.168.x, ::1) blocked by default.
- Validation at two points: request middleware + provider context (defense in depth).

**Famit-specific SSRF rules derived:**
1. `base_url` field in provider record: allowlist-only. Default: deny all non-allowlisted.
2. Scheme must be `https://` (no http://, no file://, no ftp://).
3. Block RFC1918 + loopback + link-local + cloud metadata ranges at both app and network layers.
4. DNS resolve at save-time AND at request-time (anti-DNS-rebinding: check both moments).
5. Super-admin: can add to platform allowlist (PIN-gated F3 step-up). Tenant: hosted-API only, no self-hosted.
6. Hard timeout: 10s connect + 60s read. No infinite hangs from malicious slow endpoints.

**Sources:** [Portkey Gateway PR #1372](https://github.com/Portkey-AI/gateway/pull/1372) |
[Security Boulevard — SSRF in LiteLLM](https://securityboulevard.com/2026/05/how-escape-ai-pentesting-exploited-ssrf-in-litellm/) |
[LangChain SSRF #6224](https://github.com/langchain-ai/langchain/issues/6224) |
[CVE-2026-26013](https://api.osv.dev/v1/vulns/CVE-2026-26013)

---

### G. Envelope Encryption — DEK/KEK pattern confirmed (synthesized with prior phase)

Prior `RESEARCH [byo-key-security]` §A covers the full 3-layer KEK-0/KEK-1/DEK model. This phase
confirms it as the universal industry standard (Google Cloud KMS, AWS KMS, HashiCorp Vault all implement it).

**Core pattern:**
```
wrapped_dek:  AES-KWP(KEK, DEK)           # DEK encrypted by master KEK, stored in DB alongside ciphertext
ciphertext:   AES-256-GCM(plaintext, DEK)
aad:          tenant_id || provider_id      # GCM binding — ciphertext non-portable across tenants/fields
kek_version:  "v3"                          # enables rolling rotation without decrypting all records
```

Key rotation: re-wrap DEK under new KEK version; ciphertext unchanged. `kek_version` enables progressive
rotation without decrypting all records at once.

BYOK (enterprise): customer-managed KEK via AWS KMS / Azure Key Vault. Platform never sees plaintext KEK —
only wrap/unwrap API calls. Slots in via `VAULT_BACKEND` env without consumer code changes.

**Sources:** [Google Cloud Envelope Encryption](https://docs.cloud.google.com/kms/docs/envelope-encryption) |
[Ubiq Key Wrapping Best Practices](https://dev.ubiqsecurity.com/docs/key-mgmt-best-practices) |
[DevSecOps School — Envelope Encryption 2026](http://devsecopsschool.com/blog/envelope-encryption/)

---

### H. Health-Check Patterns (synthesized with n8n + self-hosted-serving phase)

n8n `test` property on credential save = the standard lightweight pattern. For Famit's provider registry:
- On registration save: lightweight probe (GET `/health` or `/models`) — must return 2xx < 5s.
- Background job: every 5 minutes. Degrade provider if 2/3 consecutive checks fail.
- Store: `last_checked_at`, `last_status` (ok/degraded/down), `latency_ms`, `error_message` on provider record.
- UI: health badge (green/amber/red) in real-time on Provider Registry page.
- Per-provider-type probe endpoints: detailed in `RESEARCH [self-hosted-serving]` §HEALTH-CHECK table.
- For hosted-API providers: use a list-models endpoint, NOT a generation endpoint (avoids cost).

**Sources:** [Microsoft Health Endpoint Monitoring Pattern](https://learn.microsoft.com/en-us/azure/architecture/patterns/health-endpoint-monitoring) |
[microservices.io Health Check API](https://microservices.io/patterns/observability/health-check-api.html)

---

### I. Famit Provider Registry — Consolidated Schema Decisions

**`provider_registry` table (new, sourced from n8n + LiteLLM + Zapier patterns):**
```sql
id, tenant_id (NULL = platform-default),
name, display_name,
type: enum('hosted-api' | 'self-hosted' | 'platform-builtin'),
base_url: varchar,                 -- SSRF-validated, https-only, allowlisted for self-hosted
auth_scheme: enum('bearer' | 'api-key-header' | 'api-key-query' | 'basic' | 'oauth2'),
auth_header_name: varchar,         -- e.g. 'Authorization', 'x-api-key'
auth_value_template: varchar,      -- e.g. 'Bearer {key}' — {key} = ONLY interpolation token
credential_ref: uuid,              -- FK into provider_credentials encrypted store (never raw key)
capabilities: jsonb,               -- ["text-generation","image-generation","video","tts","embeddings"]
request_field_map: jsonb,          -- validated JSONPath only, no eval, max depth 5
response_field_map: jsonb,         -- e.g. {"text": "$.choices[0].message.content"}
cost_per_unit: numeric, cost_unit: varchar,
rate_limit_rpm: int, rate_limit_tpm: int,
health_check_endpoint: varchar, health_check_method: varchar,
last_health_status: enum('ok'|'degraded'|'down'|'unknown'), last_health_at: timestamptz,
is_active: bool, is_platform_default: bool,
created_by: uuid, created_at, updated_at
-- FORCE ROW LEVEL SECURITY: tenant_id = current_setting('app.current_tenant') OR tenant_id IS NULL
```

**`provider_credentials` table (tighter RLS, accessed only via vault/seam.py):**
```sql
id, provider_id FK, tenant_id,
ciphertext: bytea, wrapped_dek: bytea, iv: bytea, auth_tag: bytea,
kek_version: varchar, aad: varchar   -- aad = tenant_id || provider_id (GCM binding)
created_at, rotated_at
-- FORCE ROW LEVEL SECURITY. Never queried directly in app code.
```

**Auth injection at runtime (Pipedream `$auth` pattern translated to Python):**
1. `get_secret(tenant_id, provider_id, scope="llm_router")` → AES-GCM decrypt → raw key string.
2. Inject into HTTP request headers via `auth_header_name` + `auth_value_template.replace("{key}", raw_key)`.
3. Raw key lives only in request-scoped local variable. Not logged, not returned to client.

**SSRF governance (Portkey + prior byo-key-security §D patterns):**
- Tenant admin: `hosted-api` type only. Hostnames must match platform allowlist.
- Super-admin: can add any domain to allowlist (PIN-gated F3 step-up, audited).
- Self-hosted: requires super-admin approval + SSRF validation pass + health-check sandbox pass.

---

### J. What to Adopt vs Skip (final decision table)

| Pattern | Decision | Rationale |
|---|---|---|
| n8n `ICredentialType` declarative `authenticate` descriptor | ADOPT | Type-safe, UI-generatable, extensible |
| Zapier auth-type enum (bearer/api-key-header/oauth2/basic) | ADOPT | Covers >95% of AI providers |
| Pipedream runtime-only `$auth` injection (key request-scope only) | ADOPT | Key never in process memory beyond request |
| LiteLLM `model_list` + `api_base` + `os.environ/VAR` | ADOPT as template for provider_registry schema | Direct analogue |
| Portkey SSRF allowlist + private-range block | ADOPT natively in ssrf_guard.py | Mandatory for self-hosted endpoints |
| DEK/KEK AES-256-GCM envelope per tenant | ADOPT (seam from byo-key-security phase) | Vault slots in later without consumer changes |
| OpenAPI spec import → auto-generate field mapping | DEFER to v2 | Power feature; core registry ships first |
| Health-check `test` property on registration save | ADOPT | Immediate feedback; n8n proven pattern |
| Response field mapping as validated JSONPath (no eval) | ADOPT | No injection surface |
| Response field mapping as Jinja/template strings/eval | REJECT | Injection risk |
| LiteLLM full proxy as Famit auth layer | SKIP | Overkill; implement patterns natively |
| n8n full node registry system | SKIP | Famit is not a workflow engine |
| Pipedream Connect external-user OAuth | SKIP | Famit manages its own tenant keys |

**Persisted:** 2026-06-14. Phase: RESEARCH [connector-integration-framework].

---

## Phase: DESIGN [crazy-ui-security]

**Date:** 2026-06-14. READ-ONLY design. Grounds: real files inspected — super-admin/api-keys/page.tsx,
api-keys/_custom-providers.tsx, Icon registry, components/*, app/creative/_components/*. The existing
_custom-providers.tsx (name+kind+base_url+model+key, Fernet-encrypted, masked, Switch/delete) IS the seed
the Universal Provider Registry extends — NOT a from-scratch build.

### A. GLYPH GROUND-TRUTH (load-bearing — a missing name renders an invisible empty <path>, no error)
Registered & SAFE: lock clock-1 info block check check-circle check-circle-fill upload magic-pencil chain
chain-think link link-1 plus trash dots chevron arrow search filters video camera-video camera camera-stroke
bell list grid send layers heart star-fill chart. camera-video AND video BOTH exist -> Video Studio nav glyph
= camera-video; Providers/Integrations nav glyph = chain (connector) or link-1.
ABSENT (NEVER reference — silent break): shield, eye, copy, key, refresh, download, plug, server, globe, play,
pause. Reveal=lock; Rotate=clock-1; Health=Badge dot; Copy/Export/Test=text buttons; self-hosted=chain;
play-overlay on video poster=camera-video (no play glyph).

### B. PAGE 1 — UNIVERSAL CONNECTOR / PROVIDERS and INTEGRATIONS  app/integrations/page.tsx
Title once via Layout title="Integrations". Sub-nav pill-strip (ported from AdminHeader, NOT Tabs):
Providers / Self-hosted / Health / Audit. Per-tenant by default; super-admin twin at
app/super-admin/integrations/page.tsx shows the _global platform catalogue + a tenant fleet table.
EntitlementGuard featureKey="integrations.providers" wraps the page (HIDE->redirect / LOCK->overlay = the FE
flag; the backend choke-point is the real boundary). Super-admin twin wraps in SuperAdminGuard.

PROVIDERS tab — verbatim port of api-keys ProviderCard + KeyRow + AddKeyModal, GENERALISED:
- One Card per registered provider; shows display_name, Badge capability chips (text/image/video/tts/stt/embed),
  a masked credential row (row.masked, font-mono), a VaultHealthBadge (clone StatusPill: green=ok dot /
  amber=degraded / grey=down, fed by /integrations/health poll every 30s — NOT 5s; health is cheap-but-not-free),
  an enable Switch, two-step confirm-delete (existing Confirm/Cancel), and a "Test connection" text-button that
  POSTs the test-connection route and renders the result inline ("Connected — model X — 14 GB VRAM free" / raw
  HTTP error + hint).
- ADD-PROVIDER modal (extends AddCustomModal): display_name / capability multiselect / type Select (Hosted API /
  Self-hosted) / base_url (or host+port for self-hosted, SSRF-decomposed) / auth_scheme Select (Bearer / API-key
  header / Basic / None) / auth_header_name (shown only for api-key-header) / model / transform_type Select
  (OpenAI-compatible[default,zero-config] / Named provider / Custom field-map) / api_key (type=password, never
  prefilled) / cost_per_unit + cost_unit. transform=Custom field-map -> reveal request/response JSON textareas
  with a JSONPath-only helper + live validate (depth<=5, no eval). "Test connection" runs BEFORE save is enabled
  for self-hosted (health-sandbox gate). Form rendered from a serializable descriptor (n8n ICredentialType
  pattern) so new auth types are data, not code.

SELF-HOSTED tab — same card grammar; add-modal pre-selects Self-hosted, accepts host+port as SEPARATE validated
fields (SSRF layer-1), exposes provider_type sub-enum (openai-compat / ComfyUI / A1111 / TGI-native / generic)
-> conditionally shows workflow_json textarea (ComfyUI) or field-maps (generic). PIN/step-up firewall gate on
the "Add self-hosted endpoint" action (reuse firewall.py step-up). Per-type health probe shown as readiness
detail (vLLM /health, Ollama /, ComfyUI /queue, A1111 /sdapi/v1/sd-models, TGI /health).

HEALTH tab — Table (Provider / Type / Capabilities / Status pill / latency_ms / last_checked / circuit-state)
+ ok/degraded/down count strip. AUDIT tab — append-only access/health/add/rotate/test events Table + Export
CSV/NDJSON text-button (SIEM/SOC-2); right Modal isSlidePanel drawer for a single event detail.

PIN-gated REVEAL — ai_provider/platform-scope credentials: NO reveal/rotate/update surfaced (masked metadata +
health only) per Vault section-9 trust model. integration/custom-scope (vendor's own key): Reveal/Rotate/Update
shown, each behind the inline PIN pad (port _reveal-pin.tsx — PIN pad + 30s countdown ring; plaintext in useRef
wiped on unmount/timeout; copy-without-revealing; never useState).

### C. PAGE 2 — VIDEO STUDIO  app/creative/video/page.tsx (first consumer of the registry)
Matches VIDEO-STUDIO-MASTER-PLAN section-10. Layout title="Video Studio", two-col HomePage grammar.
- COL-LEFT: Card "Create video" (Campaign Select / TierTabs Composite[default,"Rs0.25/clip / no key"]/AI motion/
  Premium / Aspect Tabs 9:16/1:1/16:9 / count Stepper / big Field textarea / [Upload your clip][Generate batch
  isBlack] / cost-meter line). Card "Generation" = liquid CreativeSkeleton -> morph -> variant
  video poster controls preload="none" cards + Tabs(All/Approved/Drafts).
- COL-RIGHT: Card "Campaign context" (CampaignContext reuse) + Card "Recent videos" (mini AssetMedia grid).
- Advanced Dropdown: model id / duration / voiceover voice / captions on-off / BYO-key picker (which registered
  video provider — reads PAGE 1 registry; composite needs none).
NEW leaves app/creative/video/_components/: TierTabs (Tabs clone), BatchProgress (reuse GenerationQueue +
CreativeSkeleton), UploadClip (FieldImage->multipart). Provider picker = Select from
useIntegrations(capability="video_gen").

### D. LIBRARY = ONE LIBRARY, Images<->Videos toggle (the differentiator)
AssetImage.tsx -> split to AssetMedia.tsx (media_type==="video" -> video preload="none" poster controls
playsInline + duration pill + camera-video play-overlay; else img; keep onError + shimmer). AssetCard/
AssetDetail use AssetMedia. FilterRail KIND_OPTS += {id:8,name:"Video"}. LibraryGallery += mediaType state +
binary Images<->Videos segmented Tabs in head. lib/assets.ts Asset += media_type,duration_s,with_audio,
poster_url,outputs[],ab_group; AssetQuery += media_type. preload="none" MANDATORY (egress — network tab must
show posters only, not every clip).

### E. THE MOST-SECURE MODEL (FE surface of the BE security)
- Keys encrypted-at-rest: AES-256-GCM envelope, AAD=tenant_id||provider_id||version (cross-tenant ciphertext
  swap -> InvalidTag). FE NEVER receives a raw key — only masked; add input type=password, never prefilled.
- get_secret(tenant,key_type,scope,is_admin=False) seam = the ONLY read path; Vault slots in by env, zero FE
  change. Platform(ai_provider): vendor masked-only. Tenant(integration): PIN-gated reveal/rotate.
- SSRF (self-hosted add): host+port separate fields, scheme https-allowlist, DNS-resolve all A/AAAA ->
  RFC1918+loopback+link-local+169.254 denylist, redirects off, network-egress firewall, health-sandbox, PIN
  step-up on add. Field-maps = validated JSONPath only (depth<=5, no eval). Model responses = untrusted.
- Audit: append-only (REVOKE UPDATE/DELETE + BEFORE-trigger), FORCE-RLS, who/what/when/result(never plaintext).
- Entitlement: integrations.providers + vault.secrets + video.studio feature_keys -> HIDE(404)/LOCK(402)/
  suspend through the unchanged entitlements.py choke-point. Registry prefix MUST be literal /integrations
  /vault /creative (never /x* — the matcher is p==pr or startswith(pr+"/"); a literal * silently bypasses).

### F. FILES (decision-ready)
NEW FE: app/integrations/{page,_sub-nav,_provider-card,_add-provider-modal,_selfhost-modal,_test-conn,
_health-table,_audit-drawer,_reveal-pin}.tsx / app/super-admin/integrations/page.tsx (+1 ADMIN_TABS line) /
lib/integrations.ts (typed fetchers + useIntegrations/useProviderHealth hooks).
NEW FE (video, section-10): app/creative/video/page.tsx + _components/{TierTabs,BatchProgress,UploadClip}.tsx /
_components/AssetMedia.tsx (split from AssetImage). EDIT: AssetCard, AssetDetail, FilterRail, LibraryGallery,
lib/assets.ts, contstants/navigation.tsx (+Video Studio child under Creative, +Integrations top-level).
NEW BE: provider_registry/{__init__,registry,adapter,ssrf_guard,health,transforms}.py +
db/ddl_provider_registry.sql (provider_definitions / provider_credentials / provider_health_log, all FORCE-RLS)
+ vault/seam.py (get_secret). Mount under caller.py FEATURE_INTEGRATIONS flag (default OFF).
REUSE VERBATIM: api-keys ProviderCard/KeyRow/AddKeyModal, _custom-providers CRUD, _shared (SuperAdminGuard/
ToastView/ghostBtnCls/StatusPill), EntitlementGuard, Card/Tabs/Select/Field/Switch/Badge/Modal/Button/Spinner.

### G. FLAG / ACCEPTANCE / ROLLBACK
Flags (default OFF, resting byte-identical): FEATURE_INTEGRATIONS, FEATURE_VIDEO_STUDIO, FEATURE_VIDEO_COMPOSE,
VAULT_ENABLED(seam). Entitlement keys = the FE flags.
ACCEPTANCE: (1) flags OFF -> route table + render byte-identical, golden exit 0, earner gate before+after.
(2) add hosted OpenAI-compat provider via UI -> Test-connection 2xx -> live, masked-only, zero raw key in any
response/log. (3) add self-hosted -> 169.254.169.254 / 10.x / redirect-to-metadata -> SSRF guard 403, never hits
net (probe). (4) reveal on ai_provider row -> button absent; reveal on integration row without PIN -> 403 toast;
with PIN -> plaintext once, masks at 30s, never in react-state. (5) cross-tenant: A cannot read B provider/
credential (RLS probe 0 rows). (6) Video: Images<->Videos toggle filters; video preload="none" (network=posters
only); tsc+build+gitleaks=0; zero hex; every Icon name registered; dark-mode + reduced-motion safe. (7) custom
field-map textarea rejects non-JSONPath / depth>5 / eval-shaped string at validate.
ROLLBACK: flags->0 (instant, no deploy). PG additive (image rows untouched, media_type defaults image). FE =
delete app/integrations + app/creative/video + revert ADMIN_TABS/nav lines. FORTRESS backups before any box
write. agent.py NEVER touched (md5 9150fabe); composite worker = separate process.

### H. FOUNDER-UNNAMED FE FEATURES (the 1% -> 100%)
1. One Integrations page = universal connector (providers+self-hosted+health+audit); Video Studio is just the
   first capability consumer; WhatsApp-AI / voice-LLM / RAG plug in by declaring a capability.
2. Live "Test connection" with VRAM/model readout before save (n8n test-property) — stops dead registrations.
3. Capability chips + transform-type wizard — a non-dev adds ANY future tool via a form (OAI-compat=zero config),
   no code deploy; custom field-map=JSONPath, the connect-anything lever, injection-safe.
4. Real-time health badges + circuit-state (green/amber/red) — the trust signal on every provider.
5. Inline PIN-pad countdown-ring reveal + copy-without-revealing (ported from Vault) — plaintext never in state.
6. Per-tenant BYO-key picker inside Video Studio wired to the registry — vendor's own gen budget, sellable tier;
   composite tier needs none (cost floor).
7. Cost-truth labels ("Rs0 gen-API + metered TTS/Whisper", "Composite Rs0.25/clip / no key") — no hidden EL bill.
8. Audit + Export CSV/NDJSON on integrations — SOC-2 / B2B-procurement gate.
9. Likeness/consent checkbox on person-image/founder-voice video briefs (legal exposure on a shared key).

### I. RISKS (honest)
- R1 Glyph traps: shield/eye/copy/key/refresh/download DON'T exist -> invisible buttons. Use lock/clock-1/chain
  + text buttons (this design does).
- R2 SSRF is the #1 attack surface (CVE-2025-59146) — the self-hosted add MUST ship the 5-layer guard + PIN
  step-up BEFORE enable; never trust a raw URL string.
- R3 Reveal-policy half-gate: showing Reveal on ai_provider rows = security theater; server rejects by category,
  FE hides as defense-in-depth not the boundary.
- R4 Egress: an autoplay video grid blows the bill — preload="none" + poster-only + ABR mandatory.
- R5 Serialization: Integrations/Video/Vault all edit caller.py+registry+nav — ONE touches caller.py at a time
  (Vault section-17). Order: registry BE+seam -> Integrations FE -> Video consumer FE.
- R6 Entitlement prefix literal /integrations not /integrations* or LOCK/suspend silently bypass.

**Persisted:** 2026-06-14. Phase: DESIGN [crazy-ui-security].

---

## Phase: DESIGN [video-studio-on-framework]

**Date:** 2026-06-14. READ-ONLY design. Writes: `design/PROVIDER-FRAMEWORK-PLAN.md` (NEW) +
`design/VIDEO-STUDIO-MASTER-PLAN.md` §9b/§10d/§12 enhancement + this ledger.

**Deliverable 1 — `design/PROVIDER-FRAMEWORK-PLAN.md` (the Universal Flexible Provider/Connector Registry):**
The 100% design for the founder's mandate (add ANY hosted model+key / SELF-HOST any model / connect ANY future
tool, entirely via UI, most-secure, pluggable). Grounded in 3 already-built abstractions (video function-switch
`media_gen/video/providers.py`+`config._key_for` per-tenant override; image Protocol-ABC; LLM Fernet pool
`key_store.py:48`+custom_providers CRUD) — UNIFIED by strangler, not rip-and-replace.

- **Core decision = PG-backed registry (not YAML, LiteLLM `store_model_in_db`) + 3-tier transform:**
  `openai_compat` (zero code, ~90% market) / `named_provider` (1 dict entry — the EXISTING video builders are
  registered here, not thrown away) / `custom_field_map` (JSONPath-only, depth≤5, NO eval — the "connect any
  future tool via UI" lever).
- **Capability-keyed seam** `registry.get_provider(tenant, capability='video_gen', routing_hint)` — Video is
  the FIRST consumer; voice LLM router / RAG / image / WA AI plug in next by capability (structural promise).
- **3 PG tables, FORCE-RLS** (`db/ddl_provider_registry.sql`): `provider_definitions` (`_global` write-locked
  to super-admin GUC), `provider_credentials` (AAD=`tenant‖def‖version` AES-256-GCM, `scope` col = platform
  `ai_provider` masked-only vs vendor `integration` revealable — the Vault §9 trust model in one column),
  append-only `provider_health_log`.
- **Most-secure:** AAD-bound encryption (cross-tenant ciphertext → InvalidTag), FORCE-RLS + JWT tenant + sep
  `admin_store.py`, PIN step-up reveal (60s, aud=def_id, single-use jti, mint rate-limit — closes live firewall
  jti gap), `ssrf_guard.validate_endpoint` (host+port split, DNS-resolve-ALL, RFC1918/metadata denylist,
  hex/octal/IPv6/rebind/redirect-deny, network-egress backstop), JSONPath-injection guard, audit. SSRF = a GATE
  before any self-hosted register (CVE-2025-59146 precedent).
- **Vault seam = the clean swap:** `credentials.py` imports ONLY `vault.seam.get_secret(...)`; interim Fernet,
  Vault back-end = flip `VAULT_BACKEND`, zero consumer change.
- **Self-hosted contracts baked into type presets** (vLLM/Ollama/TGI/A1111/ComfyUI readiness+capability probes).
- **NEW pkg** `droplet_work/provider_registry/` (12 files) + FE `app/super-admin/providers` +
  `app/settings/byo-keys` + the one new `FieldMapper` drag-to-map component.
- **Flags:** `PROVIDER_REGISTRY_ENABLED` (mount) + per-consumer sub-flags `REGISTRY_FOR_{VIDEO,IMAGE,LLM}`
  (independent strangler cut-over + independent revert). Build F1–F9 (DDL→guard/adapter→resolve→mount→video
  cut-over FIRST→image/LLM→FE→Vault-swap→soak). Earner-safe (rides caller.py/AI-asset, never agent.py; LLM
  router cache-first = 0ms/turn). Serialized vs RAG/Vault/Video on caller.py.

**Deliverable 2 — Video Studio as FIRST consumer (`VIDEO-STUDIO-MASTER-PLAN.md` §9b):** Video resolves every
render (composite/hosted/self-hosted) via `registry.get_provider(tenant,'video_gen',tier)`; cut-over =
framework F5 (`REGISTRY_FOR_VIDEO`, rewire `client._resolve_key` :304-318, byte-identical both ways). `compose`
needs no key (always-available floor). §10d BYO-key card = thin view over framework `scope='integration'`
creds. Video ships composite + manual + env-keyed-gen WITHOUT waiting on the framework (legacy fallback the
strangler preserves); framework upgrades the key story in-place when it lands.

**Risks:** caller.py serialization (only ONE of RAG/Vault/Video/Registry at a time); strangler regression
(per-consumer sub-flag + byte-diff, video cut FIRST=lowest-risk, LLM-router LAST=cache-first); SSRF sharpest
knife (guard ships+tested before any self-host register); Vault-not-built (interim Fernet AAD-bound, Vault-
shaped seam).

→ FINAL phase of video-flex-framework-design. Both plans on disk, decision-ready, earner-safe, RLS,
cost-capped, most-secure, sellable.

---

## Phase: DESIGN [provider-framework]

**Date:** 2026-06-14. READ-ONLY design. Output = `design/PROVIDER-FRAMEWORK-PLAN.md` (already on disk, 510 lines,
verified complete + grounded in live file:line). This phase's deliverable: the UNIVERSAL FLEXIBLE PROVIDER /
CONNECTOR FRAMEWORK — the config-driven registry Video Studio is the FIRST consumer of.

### THE DECISION (one line)
Net-new pkg `droplet_work/provider_registry/` + `db/ddl_provider_registry.sql` (3 PG tables, FORCE-RLS) +
3-tier transform adapter + SSRF guard + `get_secret()` Vault seam + health/circuit-breaker, mounted via the
PROVEN `build_router(resolve_tenant, can, need_auth, _forbidden, firewall=_firewall_mod)` → `app.include_router`
shape (verified `caller.py:7291-7303` FEATURE_MEDIA), under `PROVIDER_REGISTRY_ENABLED` (default OFF → resting
byte-identical). agent.py (md5 9150fabe) NEVER imported.

### HAVE → unify (verified, do NOT rebuild)
3 live model-agnostic abstractions are the seed: VIDEO function-switch (`media_gen/video/providers.py:51-411` +
`config.py:67-115` `_key_for` per-tenant override), IMAGE Protocol-ABC (`creative/image_banner_studio/
providers/base.py:19-38`), LLM least-used pool + Fernet CRUD (`llm_router/provider_pool.py:51-150` +
`custom_providers.py` + `key_store.py:30-227`). The framework adds the ONE missing layer (registry + field-map
adapter + SSRF + AAD creds + health) and rewires the 3 THROUGH it by STRANGLER (per-consumer sub-flags
REGISTRY_FOR_VIDEO/IMAGE/LLM, each independently revertible; legacy env/Fernet path is the fallback on a miss).

### THE 4 LOAD-BEARING CHOICES
1. **Capability-keyed resolution** — consumers call `registry.get_provider(tenant, capability)` (video_gen /
   text_gen / image_gen / tts / stt / embed / rerank / tool_call / webhook / storage), NEVER a provider name.
   This is the structural guarantee that "Video Studio is just the first consumer" — every future tool plugs in
   for free by declaring a capability.
2. **3-tier transform** = the only way "add via UI, no code deploy" is TRUE for ~95%: Tier-1 `openai_compat`
   (90% of market, zero map) · Tier-2 `named_provider` (1 dict entry; the existing fal/replicate/luma builders
   ARE these, registered not rewritten) · Tier-3 `custom_field_map` (validated JSONPath JSONB, depth≤5, NEVER
   eval — the "connect ANY future tool" lever).
3. **`get_secret()` Vault seam** — `credentials.py` imports ONLY `vault.seam.get_secret(tenant, key_type, scope,
   is_admin=False)`; interim routes to the Fernet key_store, Vault ships = flip `VAULT_BACKEND`, ZERO consumer
   change. Vault is a SEPARATE deferred build (per the mandate).
4. **SSRF guard is a hard GATE, not a nicety** — CVE-2025-59146 direct precedent. host+port+scheme as separate
   validated fields → DNS-resolve ALL A/AAAA → RFC1918+metadata+loopback+link-local denylist + hex/octal/IPv6/
   rebind detection → scheme allowlist → redirects-off → network-egress firewall → health-sandbox → PIN step-up.
   Self-hosted = super-admin-only; tenant BYO = hosted-API only.

### SCHEMA (3 tables, all FORCE-RLS, additive, idempotent, manual-apply)
`provider_definitions` (the reusable spec; `_global` read-shared, write-locked from non-admin) · `provider_
credentials` (AES-256-GCM, **AAD = tenant_id‖provider_def_id‖version** MANDATORY; `scope` column = `ai_provider`
platform-masked-only vs `integration` vendor-revealable — the Vault §9 trust model in one column) · `provider_
health_log` (circuit-breaker input, REVOKE UPDATE/DELETE append-only). INTEGER micro-USD cost (never float).
Cost metered on the existing wallet ledger; audit on the immutable `events` table (`channel='providers'`).

### SECURITY (most-secure, the founder's explicit ask)
AAD-bound encryption (cross-tenant ciphertext swap → InvalidTag) · FORCE-RLS + tenant from JWT never body ·
PIN step-up reveal (60s, aud=provider_def_id, single-use jti — closes the live firewall jti-replay gap for this
path) · reveal-POLICY (ai_provider masked-only / integration revealable) · field-map = JSONPath-only no-eval +
untrusted-response schema-validation · append-only audit · legacy-pw FamitCall2026 → 403.

### UI (crazy best-of-best, Core_2, zero hex, registered glyphs only)
One **Integrations** page (Providers / Self-hosted / Health / Audit sub-nav) = the universal connector;
super-admin twin + tenant BYO-key view. Verbatim port of api-keys ProviderCard/KeyRow/AddKeyModal +
_custom-providers CRUD + Vault PIN-pad reveal. ONE new leaf = the visual **FieldMapper** (drag-to-map → JSONPath
JSONB). Glyph ground-truth banked (shield/eye/copy/key/refresh ABSENT → lock/clock-1/chain + text buttons; full
FE design = the `DESIGN [crazy-ui-security]` phase above). Live "Test connection" with model/VRAM readout
(n8n test-property) before save; real-time health badges; cost-truth labels.

### EARNER-SAFE / FLAGS / ROLLBACK
Rides caller.py + AI-asset service (`:8310`), NEVER agent.py. The ONE latency-sensitive consumer (voice LLM
router) is cache-first (warm in-memory map, reconcile on timer → ~0ms per turn, the W2 pattern). All flags
default OFF (byte-identical resting); per-consumer sub-flags revert independently; 3 tables additive (drop-safe).
Serialize the caller.py mount against {RAG, Vault, Video} — only ONE edits caller.py at a time.

### BUILD ORDER (F1→F9, earner-gated per wave)
F1 DDL+pkg shell → F2 ssrf_guard+adapter+named_transforms+credentials → F3 store/admin_store/registry/health →
F4 mount endpoints (serialized) → F5 strangler VIDEO first (async, lowest risk) → F6 IMAGE then LLM (LLM last,
cache-first, inbound-proven) → F7 frontend (panel-exclusive) → F8 Vault seam swap (config flip) → F9 integrated
soak + THREE_PRODUCTS_ROLLBACK. GATED: real hosted-gen (founder keys), self-host GPU (DO 3/3 full), Vault backend
(deferred product). Registry + Tier-1 OAI-compat + composite-video consumer work TODAY on interim Fernet, no new box.

### FOUNDER-UNNAMED (1%→100%)
3-tier transform (the no-deploy lever) · capability-keyed resolution · strangler per-consumer sub-flags ·
`scope` column = BYO-key-but-never-leak-platform-key · SSRF as first-class gate · health/circuit-breaker +
fallback chain · visual FieldMapper · cache-first 0ms voice-router · clean get_secret Vault seam · jti
single-use reveal + SOC-2 audit.

**Output files:** `design/PROVIDER-FRAMEWORK-PLAN.md` (the plan) + `design/VIDEO-STUDIO-MASTER-PLAN.md` §9b/§10d/
§12.7 (Video = first consumer). **Persisted:** 2026-06-14. Phase: DESIGN [provider-framework].

---

## Phase: SYNTHESIZE [unified-roadmap]

**Date:** 2026-06-14. **DESIGN-ONLY** — no box/code/earner mutation; agent.py md5 `9150fabe` never read/imported, no restart, no ring.

**What this phase did:** merged the whole read-only wave (HAVE: provider-abstraction / keystore-security / video-plan · RESEARCH: provider-registry-patterns / byo-key-security / self-hosted-serving / connector-integration-framework · DESIGN: provider-framework / video-studio-on-framework / crazy-ui-security) into the universal-flexible-provider framing on the two master plans + ONE unified earner-safe build roadmap.

**Deliverable 1 — `design/PROVIDER-FRAMEWORK-PLAN.md` enhanced with §14 (THE NEW SYNTHESIS):** the UNIFIED cross-product W1–W12 build roadmap merging the framework's F1–F9 + Video's U1–U10 into one sequenced, table-form plan (each wave: scope · files/schema · flag · acceptance · rollback). The order honors the founder: **framework FIRST → Video Studio on it → composite tier ships with ZERO paid key.** Hard rule baked in: **caller.py serialization — only ONE of {RAG, Vault, Registry, Video} edits caller.py at a time.** RAG W3 is LIVE+DEPLOYED → the registry mount (W4) is the NEXT caller.py edit, the video mount (W8) follows — never concurrent. BE on Opus (DDL/RLS/crypto/SSRF/adapter/mount), FE on Sonnet + frontend-design. The first 3 waves (W1 DDL+pkg shell · W2 SSRF+adapter+named-transforms+AAD-creds · W3 resolve+health+reveal — all local/offline before W4) are spelled out, launchable now after RAG W3.

**Deliverable 2 — `design/VIDEO-STUDIO-MASTER-PLAN.md`:** §9b/§10d/§12.7 already wire Video as the framework's first consumer (verified this pass, not re-touched — would have churned shipped design).

**Pointers appended (this phase's required writes):**
- `NEXT-BIG-BUILDS.md` — new item **#8b** (Universal Provider Framework, build BEFORE Video Studio) + #9 (Video Studio) cross-linked to the unified §14 roadmap (which supersedes the standalone U1–U10 execution order).
- `ORCHESTRATOR.md` — synthesis wave entry prepended (newest on top); OPEN/NEXT = W1.
- `WORKFLOW_LEDGER.md` — final one-line ledger entry appended (newest on top).

**The framework in one screen (carried from the DESIGN phases):** net-new pkg `droplet_work/provider_registry/` (12 files) + `db/ddl_provider_registry.sql` (3 FORCE-RLS tables: `provider_definitions` `_global`-read-shared/write-locked · `provider_credentials` AAD-bound AES-256-GCM + a `scope` column = ai_provider-platform-masked vs integration-vendor-revealable, the Vault §9 trust model in one field · `provider_health_log` append-only). 3-tier transform (openai_compat zero-config ~90% · named_provider 1-dict-entry, existing fal/replicate/luma builders REGISTERED not rewritten · custom_field_map JSONPath-only-no-eval). Capability-keyed `get_provider(tenant,capability)`. `get_secret()` Vault seam (interim Fernet → flip VAULT_BACKEND). SSRF guard hard-gate (CVE-2025-59146). STRANGLER per-consumer sub-flags. Earner-safe (rides caller.py/AI-asset `:8310`, never agent.py; voice-router cache-first = 0ms/turn); multi-tenant FORCE-RLS; cost-capped (free composite default + 1-paid-test choke-point + per-tenant cap on the paise ledger); most-secure; sellable/differentiated. All flags default OFF = byte-identical resting; rollback = flags→0 (additive tables, drop-safe).

**WAVE COMPLETE.** All 10 phases (3 HAVE + 4 RESEARCH + 3 DESIGN) + this SYNTHESIZE are persisted and decision-ready. No open forks. NEXT BUILD = W1 (framework DDL + package shell).
