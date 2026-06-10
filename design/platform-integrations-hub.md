# DESIGN SPEC — INTEGRATIONS HUB (the connector framework) — execution-ready

> **What this is.** The FOUNDATIONAL connector layer that every outward-facing module sits on:
> ad platforms (Meta / Google), WhatsApp BSP, email/SMS, payment gateways, Google Calendar,
> Shopify / WordPress, generic outbound webhooks, inbound webhooks, and MCP tool servers. It owns
> **(a)** the credential vault (OAuth2 + API-key + per-connection secrets, encrypted at rest),
> **(b)** the provider-agnostic **connector interface** every adapter implements,
> **(c)** the **inbound webhook router** (verify-signature → normalize → dispatch),
> **(d)** the **outbound event bus** (sign → deliver → retry → log) generalizing today's `_emit_webhook`,
> **(e)** the **MCP tool bridge** (external MCP servers surfaced as gated tools).
> It does NOT itself launch ads, send WhatsApp, or charge cards — it is the *plumbing* those modules
> call. Ads / Payments / Booking / Forms / Marketing read their connection + token FROM the hub.
>
> **Verdict (settled, do not relitigate):** STRANGLE & EVOLVE on the modular monolith. Additive only.
> **NO git** (orchestrator commits). **NEW files only** under `droplet_work/integrations/` + a small
> `db/` migration; **DO NOT edit `caller.py` / `agent.py`** business logic — wiring into the spine is a
> *written, un-applied diff* (`integrations_wiring.diff`) the orchestrator applies when final wiring is
> un-deferred. **DORMANT-UNTIL-CREDS + PROVIDER-AGNOSTIC**: every adapter is import-safe, never raises,
> returns `{"status":"not_configured"}` until the founder pastes/authorizes creds — exactly like
> `whatsapp.py`. **Verifiable fully OFFLINE** (zero live external calls in the acceptance suite).
>
> Research date: 2026-06-09. All chosen OSS/SDKs verified ACTIVE (release dates cited inline, §1).
> A build agent implements this verbatim, ONE UNIT at a time (§8), committing + acceptance-testing each.

---

## 0. GROUND TRUTH — what already exists on disk (cite before trusting memory)

Verified 2026-06-09 against `C:\Users\kunal\Desktop\caps\droplet_work\caller.py` and the design corpus.
The hub does NOT reinvent these; it **generalizes and unifies** them.

| Existing primitive | Location | What the hub does with it |
|---|---|---|
| Dormant-until-creds adapter template | `whatsapp.py` (`_cfg()`, `is_configured()`, no-op `{"status":"not_configured"}`, never raises, sync+async, `redact()`) | The **canonical shape** every connector adapter copies. The WhatsApp adapter is REFACTORED to *register* through the hub (back-compat shim keeps `whatsapp.py` callable). |
| Vendor adapter conventions | `vendors/__init__.py`, `vendors/vobiz.py`, `vendors/_http.py` (`DISPLAY_NAMES`, `redact` first/last-4, `status()→configured\|not_configured\|error`, short timeout + 429/5xx backoff) | The hub's `_http.py` reuses these exactly; connector `status()` returns the same enum. |
| **Outbound webhooks** | `caller.py:1300 _emit_webhook(tenant_id,event,payload)` — HMAC-SHA256 sign (`X-Famit-Signature`,`X-Famit-Event`), 3× retry w/ backoff, `webhook_log` append; store `WEBHOOK_FILE=var/webhooks.json` (`:119`); CRUD `GET/POST/DELETE /webhooks` (`:3109/3128/3143`) | The hub's **outbound event bus** SUBSUMES this. `_emit_webhook` becomes a thin shim calling `integrations.outbound.emit(...)`. The `webhooks`/`webhook_log` tables (P1 §3.3) are REUSED unchanged; the bus adds `connection_id`, delivery idempotency + a dead-letter table. |
| **Inbound webhook verify+parse** | `caller.py:3002 _verify_meta_signature` (HMAC `X-Hub-Signature-256`, dormant→accept), `:3017 _parse_meta_inbound` | The hub's **inbound router** generalizes signature verification per-provider; the Meta path becomes one registered `verify`/`normalize` pair. |
| Auth / tenant resolution | `caller.py:341 resolve_token` (`tenant_id.hmac`), `:366 resolve_tenant`, `auth.py` JWT (HS256, `var/secret`) | Hub endpoints resolve tenant the SAME way. OAuth `state` is signed with the SAME `var/secret`. **Do NOT rewire `resolve_tenant`.** |
| **Action Firewall (step-up)** | `design/credit-ledger-firewall.md` → `firewall.py` `mint_step_up(tenant,scope)` / `require_step_up(request,scope)` (HS256 `amr:pin`, short TTL); flag `FIREWALL_ENABLED` | Risky hub actions (connect a *money-moving* provider, rotate/reveal a secret, disconnect a live payment connector) require `require_step_up(scope="integrations")`. Pass-through when flag OFF / no PIN (nothing breaks today). |
| Immutable audit | `audit.py` `record(actor,action,object_type,object_id,...,meta)` append-only JSONL (mirrored to `events` table, P1 §3.6) | EVERY connect / disconnect / token-refresh / secret-reveal / inbound-receive / outbound-deliver writes here with new `integration.*` action names. Reinvents nothing. |
| **Postgres + RLS** | `db/models.py`, `db/engine.py` `session(tenant_id,is_admin)` (`SET LOCAL app.tenant_id`), per-store MODE router `store.py` (P1) | Hub tables are NEW (migrate no existing JSON), tenant-scoped with the SAME `(org_id,…)` + FORCE-RLS pattern. Default store MODE = `json` (dormant), promotable to `dual`/`pg` exactly like P1. |
| **Hatchet durable orchestration** | `design/orchestration-hatchet.md` (`hatchet.workflow`, `durable_task`, crons, `run_no_wait(key=…)`, CEL concurrency) | Token-refresh, webhook redelivery, and long sync jobs (Shopify backfill) run as Hatchet crons/durable tasks when present; **fall back to the existing `scheduler_loop` 60 s tick** when Hatchet is `legacy` (import-safe degrade). |
| **AI-Manager tool registry** | `automation-aimanager.md` `tools/__init__.py` `ToolSpec{name,schema,fn,side_effecting,money}`, `ad_tools.py` | Hub connectors EXPOSE their operations as `ToolSpec`s the registry imports. **One money-path, one gate, one audit** — the hub is the *substrate*, the registry is a *consumer*. No second tool surface. |
| **Workflow-Studio Integration node** | `platform-workflow-studio.md` §4.9 `integration` node | Calls hub adapters via the SAME `ToolSpec` interface. The hub is exactly the "dormant-until-creds adapters the AI Manager already uses" that §4.9 names. |
| **Ads module adapters** | `automation-ads.md` / `automation-aimanager.md` `ads/google_ads.py`, `ads/meta_ads.py` | These KEEP their business logic; they obtain `access_token`/`refresh_token`/account-id **from the hub's connection** instead of reading raw env. The hub owns OAuth + refresh; ads owns spend. Clean seam. |

> **Net:** the hub is a thin new module that *unifies plumbing that already exists in five places*
> into one credential vault + one connector interface + one inbound router + one outbound bus + one MCP
> bridge. It introduces ONE new dependency surface (OAuth + crypto for secret encryption) and a handful
> of additive tables. The spine is untouched until the deferred diff is applied.

---

## 1. CHOSEN TOOLS & WHY (web-researched 2026-06; ACTIVE, none abandoned, cited)

> Principle (from `automation-ads.md` §0): **compose official SDKs + thin OSS, don't adopt a fat
> "integration platform."** We deliberately do NOT embed n8n/Pipedream/Nango-server as a runtime
> dependency — they are heavyweight separate services that would fight our hand-rolled, audited,
> RLS-scoped money-path. We take the *interface ideas* (Nango's "one OAuth model, provider config as
> data") but implement them in ~600 lines we own and can offline-test.

### 1.1 OAuth2 — `authlib` (Python)
- PyPI **Authlib 1.6.x** (latest release 2026-05-06, Python ≥3.10, "Production/Stable" — actively
  maintained; the de-facto OSS OAuth/OIDC lib for Python). Used ONLY for the OAuth2 **client** flows
  (auth-code + PKCE S256, client-credentials, refresh-token grant) and JOSE helpers. Critically it ships
  **`authlib.integrations.httpx_client.AsyncOAuth2Client`** — an *async* OAuth client over httpx, which
  matches our async event-loop + the `vendors/_http.py` httpx convention exactly (no requests dep). We do
  NOT run its server pieces. Import-safe-wrapped (`try: import authlib … except: None` → connector flows
  that need it return `error:oauth_lib_unavailable`, never crash import). If we want zero new deps, the
  auth-code + refresh dance is ~80 lines of `httpx` POSTs against the provider token endpoint — Authlib
  mainly buys PKCE + token-introspection correctness. **Decision: depend on Authlib but keep the manual
  fallback path documented (§4.3) so the module is degradable.** Ref: pypi.org/project/Authlib,
  docs.authlib.org/en/latest/client.

### 1.2 Provider catalog — **config-as-data** (our own `catalog.yaml`; Nango's `providers.yaml` as a *reference*)
- Nango (`nangohq/nango`, very active 2025-2026) maintains a community **`providers.yaml`**
  (`packages/providers/providers.yaml`) describing 600+ providers' OAuth endpoints (authorize URL, token
  URL, scopes, refresh semantics, auth modes: `OAUTH2`/`OAUTH2_CC`/`API_KEY`/`APP`/`SIGNATURE`/…). **⚠
  LICENSE CHECK (verified 2026-06-09): Nango ships under the *Elastic License*, NOT Apache/MIT — so we do
  NOT vendor their YAML file verbatim.** Instead we **hand-author our own**
  `integrations/providers/catalog.yaml` for the ~10 providers we actually support, using Nango's public
  file (and each provider's official OAuth docs) only as a *cross-reference* to get the endpoints/scopes
  right. The schema (auth-mode enum, authorize/token URLs, scopes, signature scheme) mirrors the
  well-trodden shape; the *data is ours*, owning zero Nango runtime and respecting their license.
- Each catalog entry is overridable by env (URLs/scopes rot; same lesson as `META_ADS_API_VERSION` /
  `GOOGLE_ADS_API_VERSION` in `automation-ads.md` §1). Refs: Nango public `providers.yaml`
  (github.com/NangoHQ/nango) + each provider's OAuth docs.

### 1.3 Secret encryption at rest — `cryptography` (Fernet)
- PyPI **cryptography** (ubiquitous, maintained). Connection secrets (client secrets, access/refresh
  tokens, API keys, webhook signing secrets) are stored **encrypted** with **Fernet (AES-128-CBC +
  HMAC)** under a master key `INTEGRATIONS_ENC_KEY` (32-byte urlsafe-b64, env/Doppler). Rationale: P1
  stores raw JSON/`data jsonb`; tokens must NOT sit in plaintext in Postgres `data` or a JSON file.
  Envelope is simple Fernet now; a KMS/`age` upgrade is a noted future seam (§12). Import-safe; if the
  lib or key is absent → the vault refuses to STORE a secret (returns `error:vault_unavailable`) but the
  rest of the hub (read-only listing, dormant adapters) still imports and runs.

### 1.4 Payments — official gateway SDKs, dormant
- **Razorpay** (`razorpay` PyPI, maintained — primary for the India/INR base, matches the billing
  currency in P1 §3.5) and **Stripe** (`stripe` PyPI) as the provider-agnostic second. The hub owns the
  **OAuth/connect + webhook-signature** plumbing (Razorpay `X-Razorpay-Signature` HMAC-SHA256; Stripe
  `Stripe-Signature` t+v1 scheme). Charging/refunds live in the **Payments/Collections module**, not
  here — the hub just hands it an authenticated client + verified inbound events.

### 1.5 Commerce / CMS — official SDKs, dormant
- **Shopify** (`ShopifyAPI` PyPI / Admin GraphQL) — OAuth (offline access token) + HMAC webhook verify
  (`X-Shopify-Hmac-Sha256`, base64). **WordPress** — REST + Application Passwords (no OAuth dance) or
  WP.com OAuth; the hub supports BOTH an `api_key`-style "application password" connection and OAuth.
- **Google Calendar** — `google-api-python-client` + `google-auth-oauthlib` (Google's own libs; already
  in the family used by `google-ads`). OAuth offline + refresh handled by the hub.

### 1.6 Email / SMS — reuse the marketing module's choices; hub owns the *connection*
- `automation-marketing.md` already picks Listmonk (email) + an SMS provider seam. The hub does NOT
  re-pick; it stores those connections (SMTP creds / provider API key) and exposes a uniform
  `messaging.send` ToolSpec. Provider-agnostic.

### 1.7 MCP tool bridge — official **`mcp` Python SDK** (Anthropic), dormant
- The Model Context Protocol Python SDK (`mcp` on PyPI, Anthropic-maintained, active 2025-2026) lets the
  hub connect to an external **MCP server** (stdio or streamable-HTTP) and surface its tools as
  `ToolSpec`s. Import-safe; if `mcp` absent or no server URL configured → the bridge lists zero tools and
  the rest of the hub is unaffected. This is how third-party MCP tools enter the AI-Manager/Workflow
  surface **through the same gate + audit** as native connectors (no ungoverned tool backdoor).
  > LLM/agent note: MCP is the Anthropic standard; tool definitions surfaced here are consumed by the
  > AI-Manager's pluggable LLM driver (default Claude/Groq), so MCP-sourced tools obey the same
  > `side_effecting`/`money` gating as native ones.

### 1.8 What we deliberately REJECT (real-vs-hype, stated up front)
- **No n8n / Pipedream / Nango-server / Supabase as a runtime service.** They are separate stateful
  services duplicating our spine (auth, DB, audit) and would break the "one money-path, one gate, one
  audit" invariant. We borrow Nango's *provider data* only.
- **No generic "iPaaS engine."** The Workflow Studio (`platform-workflow-studio.md`) is our automation
  engine; the hub is its connector library, not a competing flow engine.
- **No storing OAuth client secrets per-tenant by default.** App-level OAuth *client* credentials
  (the Famit app's Meta/Google app id+secret) are platform secrets in env/Doppler; tenants authorize
  AGAINST them and the hub stores only the resulting per-tenant *tokens*. (Bring-your-own-app is a
  documented advanced mode, §4.6.)

---

## 2. CORE CONCEPTS & DATA MODEL

Four nouns. Everything else composes them.

1. **Provider** — a static catalog entry (`meta`, `google`, `whatsapp`, `razorpay`, `stripe`,
   `shopify`, `wordpress`, `google_calendar`, `listmonk`, `webhook`, `mcp:<name>`). Defines: auth kind
   (`oauth2` | `api_key` | `app_password` | `signature_only`), OAuth endpoints/scopes, capabilities
   (the operations it exposes), whether it is **money-moving**, inbound-webhook signature scheme.
   Data, not rows — lives in `catalog.yaml` (§1.2), overridable by env.
2. **Connection** — a *tenant's* authorized link to a provider (`org_id` + `provider` + optional
   `account_ref` e.g. ad-account id / shop domain / page id). Holds status, scopes granted, and a
   pointer to its **encrypted secret bundle**. A tenant can have N connections to the same provider
   (two ad accounts, two shops). **This is the row the ads/payments/booking modules look up.**
3. **Secret bundle** — the Fernet-encrypted blob for a connection: `{access_token, refresh_token,
   expires_at, client_secret?, api_key?, webhook_secret, signing_secret, extra{}}`. NEVER returned over
   the API in plaintext (reveal is a separate step-up-gated, audited action; default is redacted).
4. **Event** — an inbound (received from a provider) or outbound (delivered to a subscriber) webhook
   delivery record. Reuses P1's `webhooks`/`webhook_log` for outbound; adds inbound + dead-letter.

### 2.1 Schema (Alembic `000N_integrations.py`; SQLAlchemy 2.0 in `db/models.py`)

Follows P1 conventions exactly (§3 of `p1-postgres.md`): `text` PKs == app ids, `org_id text NOT NULL`,
promote-only-what-you-index, full record in `data jsonb`, `*_raw` for byte-faithful timestamps,
`(org_id,…)` composite indexes, **FORCE ROW LEVEL SECURITY** per table (add all four to the RLS array in
`db/rls.sql`).

```sql
-- A tenant's authorized link to a provider.
CREATE TABLE integration_connections (
  id            text PRIMARY KEY,                 -- uuid4().hex[:12]
  org_id        text NOT NULL,
  provider      text NOT NULL,                    -- meta|google|whatsapp|razorpay|stripe|shopify|...
  account_ref   text NOT NULL DEFAULT '',         -- ad-account id / shop domain / page id / calendar id
  display_name  text NOT NULL DEFAULT '',
  status        text NOT NULL DEFAULT 'not_configured', -- not_configured|pending|connected|expired|revoked|error
  auth_kind     text NOT NULL DEFAULT '',         -- oauth2|api_key|app_password|signature_only
  scopes        jsonb NOT NULL DEFAULT '[]',
  is_money      boolean NOT NULL DEFAULT false,   -- denormalized from provider catalog (gate hint)
  secret_id     text NOT NULL DEFAULT '',         -- FK→integration_secrets.id (the encrypted bundle)
  expires_at    timestamptz,                      -- token expiry (drives refresh cron)
  last_ok_at    timestamptz,
  last_error    text NOT NULL DEFAULT '',
  created_at_raw text NOT NULL DEFAULT '',
  created_at    timestamptz NOT NULL DEFAULT now(),
  data          jsonb NOT NULL DEFAULT '{}'
);
CREATE INDEX ic_org_idx        ON integration_connections (org_id);
CREATE INDEX ic_org_provider_idx ON integration_connections (org_id, provider);
CREATE UNIQUE INDEX ic_org_provider_account_uq
  ON integration_connections (org_id, provider, account_ref);   -- dedupe a re-connect of the same account
CREATE INDEX ic_expiry_idx     ON integration_connections (expires_at) WHERE status='connected';  -- refresh cron scan

-- Encrypted secret bundle (Fernet ciphertext only; NEVER plaintext at rest).
CREATE TABLE integration_secrets (
  id            text PRIMARY KEY,
  org_id        text NOT NULL,
  connection_id text NOT NULL,
  ciphertext    text NOT NULL,                    -- Fernet token of the JSON bundle
  key_version   integer NOT NULL DEFAULT 1,       -- for INTEGRATIONS_ENC_KEY rotation
  created_at    timestamptz NOT NULL DEFAULT now(),
  updated_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX is_conn_idx ON integration_secrets (connection_id);
-- RLS: org-scoped like every table. The ciphertext is useless without INTEGRATIONS_ENC_KEY anyway —
-- defense in depth (RLS + envelope encryption).

-- In-flight OAuth handshakes (CSRF state + PKCE verifier), short-lived.
CREATE TABLE integration_oauth_states (
  state         text PRIMARY KEY,                 -- HMAC-signed nonce (var/secret); ALSO row for replay-block
  org_id        text NOT NULL,
  provider      text NOT NULL,
  account_hint  text NOT NULL DEFAULT '',
  pkce_verifier text NOT NULL DEFAULT '',
  redirect_uri  text NOT NULL DEFAULT '',
  created_at    timestamptz NOT NULL DEFAULT now(),
  consumed      boolean NOT NULL DEFAULT false    -- one-time use (replay guard)
);
CREATE INDEX ios_created_idx ON integration_oauth_states (created_at);  -- TTL sweep (10 min)

-- Inbound webhook deliveries (received from providers), normalized + dispatched.
CREATE TABLE integration_inbound (
  id            text PRIMARY KEY,                 -- DETERMINISTIC = sha256(provider|raw-body|provider-event-id) → idempotent
  org_id        text NOT NULL DEFAULT '',         -- resolved from the connection (may be '' pre-resolution)
  connection_id text NOT NULL DEFAULT '',
  provider      text NOT NULL DEFAULT '',
  event_type    text NOT NULL DEFAULT '',         -- normalized: message.received|payment.captured|order.created|...
  verified      boolean NOT NULL DEFAULT false,   -- signature passed
  dispatched    boolean NOT NULL DEFAULT false,   -- handed to the consuming module
  status        text NOT NULL DEFAULT 'received', -- received|verified|dispatched|rejected|error
  received_at   timestamptz NOT NULL DEFAULT now(),
  raw           jsonb NOT NULL DEFAULT '{}',       -- the provider's raw payload (audit/debug)
  normalized    jsonb NOT NULL DEFAULT '{}'        -- the canonical Famit event shape
);
CREATE INDEX ii_org_at_idx  ON integration_inbound (org_id, received_at DESC);
CREATE INDEX ii_conn_idx    ON integration_inbound (connection_id);
CREATE INDEX ii_undispatched_idx ON integration_inbound (dispatched) WHERE dispatched=false;

-- Outbound delivery dead-letter (the existing webhook_log holds the happy path; this holds give-ups).
CREATE TABLE integration_outbound_dlq (
  id            text PRIMARY KEY,                 -- == the webhook_log row id that finally failed
  org_id        text NOT NULL DEFAULT '',
  url           text NOT NULL DEFAULT '',
  event         text NOT NULL DEFAULT '',
  body          jsonb NOT NULL DEFAULT '{}',
  attempts      integer NOT NULL DEFAULT 0,
  last_status   text NOT NULL DEFAULT '',
  next_retry_at timestamptz,                      -- redelivery cron picks these up
  created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX odlq_due_idx ON integration_outbound_dlq (next_retry_at);
```

> **REUSE, don't recreate:** `webhooks` (subscriptions) and `webhook_log` (outbound happy-path log) are
> the P1 tables (§3.3) — the bus writes them as today. The hub ADDS `connection_id` to outbound
> subscriptions via the `data jsonb` column (no schema break) and adds the four tables above. JSON
> fallback files (dormant mode): `var/integrations/connections.json`, `secrets.json`,
> `inbound.jsonl`, `oauth_states.json`, `outbound_dlq.json` — registered in `store.py` with default MODE
> `json` (byte-identical pass-through; promotable to `dual`/`pg` exactly like every P1 store).

---

## 3. FILE LAYOUT (NEW files only, under `droplet_work/integrations/`)

```
droplet_work/integrations/
├── __init__.py            # package marker + version
├── config.py              # env reads via config.get(): INTEGRATIONS_ENABLED, INTEGRATIONS_ENC_KEY,
│                          #   OAUTH_REDIRECT_BASE, per-provider app id/secret, MCP server URLs. Import-safe.
├── vault.py               # Fernet encrypt/decrypt of secret bundles; get_secret/put_secret/rotate;
│                          #   import-safe degrade (no key → store refuses, reads of plaintext-absent → not_configured)
├── catalog.py             # loads providers/catalog.yaml (+ env overrides) → Provider objects; capabilities map
├── connections.py         # Connection CRUD over the store seam (RLS-scoped); status transitions; dedupe
├── oauth.py               # auth-code + PKCE + client-credentials + refresh-token flows (authlib, manual fallback)
├── connector.py           # the ABSTRACT Connector interface (§4.1) + BaseConnector (dormant defaults)
├── registry.py            # provider → Connector class map; .get(provider) → connector; lists ToolSpecs
├── inbound.py             # inbound router: verify(provider,raw,headers,secret) → normalize() → dispatch()
├── outbound.py            # outbound event bus: emit(org,event,payload) → sign → deliver → retry → DLQ
│                          #   (the generalization of caller.py:_emit_webhook; the shim points here)
├── mcp_bridge.py          # connect external MCP server(s) → surface tools as ToolSpecs (dormant)
├── tools.py               # build ToolSpec list from connected connectors (consumed by AI-Manager registry)
├── _http.py               # shared httpx client (reuses vendors/_http conventions: timeout, 429/5xx backoff)
├── router.py              # DEFERRED FastAPI APIRouter (§6) — mounted via integrations_wiring.diff, NOT imported by caller now
├── providers/
│   ├── catalog.yaml       # curated subset of Nango providers.yaml (Apache-2.0, attributed) + env-override notes
│   ├── meta.py            # Meta (ads + WhatsApp BSP + page webhooks) connector
│   ├── google.py         # Google (Ads + Calendar) connector
│   ├── whatsapp.py       # WhatsApp BSP connector (wraps/registers the existing whatsapp.py)
│   ├── razorpay.py       # Razorpay connector (OAuth/keys + X-Razorpay-Signature verify)
│   ├── stripe.py         # Stripe connector (Stripe-Signature verify)
│   ├── shopify.py        # Shopify connector (OAuth offline + X-Shopify-Hmac-Sha256)
│   ├── wordpress.py      # WordPress (app-password / WP.com OAuth)
│   ├── gcal.py           # Google Calendar connector
│   ├── messaging.py      # email/SMS connection wrapper (delegates to marketing module choices)
│   └── webhook.py        # generic outbound-webhook "connector" (no auth dance; just a signed subscription)
├── _smoke_integrations.py # offline import + AST + instantiate-every-connector smoke (mirrors _smoke_pool.py)
└── integrations_wiring.diff  # the un-applied caller.py diff (mount router; point _emit_webhook shim; register stores)
```

`db/models.py` gains the 4 models; `db/rls.sql` gains the 4 table names in its FORCE-RLS array;
`migrations/versions/000N_integrations.py` creates them. **No business-logic edit to `caller.py`/`agent.py`.**

---

## 4. THE CONNECTOR INTERFACE (the heart of provider-agnosticism)

### 4.1 Abstract `Connector` (`connector.py`)

Every provider adapter subclasses this. The dormant default behavior lives in `BaseConnector` so a
half-implemented or unconfigured connector is automatically safe.

```python
@dataclass
class ConnResult:
    ok: bool
    status: str                 # "not_configured" | "connected" | "error:<reason>" | provider status
    provider: str
    data: dict = field(default_factory=dict)

class Connector(Protocol):
    provider: str
    auth_kind: str              # "oauth2"|"api_key"|"app_password"|"signature_only"
    is_money: bool              # money-moving → step-up + approval on connect/disconnect
    capabilities: list[str]     # operation names this provider can do (→ ToolSpecs)

    # --- lifecycle (all import-safe, never raise, dormant-until-creds) ---
    def status(self, conn: Connection | None) -> ConnResult: ...
    def begin_oauth(self, org_id, account_hint) -> ConnResult:  # → {authorize_url, state}
    def complete_oauth(self, org_id, code, state) -> ConnResult: # exchange → store secret bundle
    def connect_api_key(self, org_id, secrets: dict) -> ConnResult:  # api_key/app_password path
    def refresh(self, conn: Connection) -> ConnResult:          # refresh-token grant
    def disconnect(self, conn: Connection) -> ConnResult:       # revoke + delete secret

    # --- inbound ---
    def verify_inbound(self, raw: bytes, headers: dict, secret: str) -> bool:  # signature check
    def normalize_inbound(self, payload: dict) -> list[dict]:   # → canonical Famit events

    # --- the operations exposed as ToolSpecs (read + side-effecting) ---
    def tools(self, conn: Connection) -> list[ToolSpec]: ...
    def call(self, conn: Connection, op: str, args: dict) -> ConnResult:  # execute an operation
```

`BaseConnector` defaults: `status→not_configured`, every method returns
`ConnResult(ok=False, status="not_configured", provider=self.provider)`, `verify_inbound→True` only when
no secret is configured (matches `_verify_meta_signature` dormant behavior), `tools→[]`, `call→
not_configured`. **A provider file overrides only what it implements; everything else stays safely
dormant.** This is the `whatsapp.py` pattern made formal.

### 4.2 Registry (`registry.py`)
- `register(provider, ConnectorClass)`; `get(provider) -> Connector`; `all_providers()`.
- `tools_for_tenant(org_id) -> list[ToolSpec]` — iterates the tenant's **connected** connections, asks
  each connector for its `tools(conn)`, returns the union. This is the EXACT list the AI-Manager
  `tools/__init__.py` and the Workflow-Studio Integration node consume. The `money`/`side_effecting`
  flags on each `ToolSpec` carry through so the existing gate (§5) applies unchanged.

### 4.3 OAuth flow (`oauth.py`) — auth-code + PKCE, manual-fallback documented
1. `begin_oauth(org, provider, account_hint)`:
   - generate `state` = `b64(nonce)`, signed: store an `integration_oauth_states` row + a detached HMAC
     of the nonce with `var/secret` (so a forged callback is rejected even if the row is gone). Generate
     PKCE `code_verifier`/`challenge`. Build `authorize_url` from the catalog entry (scopes from catalog,
     env-overridable). Return `{authorize_url, state}` → frontend redirects the founder.
2. Provider redirects back to `OAUTH_REDIRECT_BASE/integrations/oauth/callback?code=…&state=…`.
3. `complete_oauth(org, code, state)`:
   - verify state signature + the row is **unconsumed + unexpired** (10 min TTL), then mark `consumed=true`
     (replay guard). POST the token endpoint (Authlib, or manual `httpx` POST) with `code`+`code_verifier`.
     Receive `access_token`/`refresh_token`/`expires_in` → **Fernet-encrypt into a secret bundle** →
     create/update the `integration_connections` row to `status='connected'`, set `expires_at`. Audit
     `integration.connected`.
- **Manual fallback (no Authlib):** the auth-code + refresh exchange is plain token-endpoint POSTs; PKCE
  is `sha256(verifier)` b64url. Documented so the module degrades if Authlib is unavailable.
- **⚠ RLS BOOTSTRAP (the callback runs with NO authenticated tenant).** The provider redirects the
  *browser* back to `/integrations/oauth/callback?code&state` — there is no tenant JWT/HMAC on that
  request. But `integration_oauth_states` is FORCE-RLS, so a default-scoped session (`app.tenant_id=''`,
  `app.is_admin='0'`) reads **zero rows** and OAuth completion silently fails. **FIX (mandatory, matches
  P1's whole-file-mirror precedent which reads cross-tenant via `is_admin=True` GUC):** the state lookup
  in `complete_oauth` runs in an **admin-GUC session** (`db.session(tenant_id='', is_admin=True)`) to
  read the `integration_oauth_states` row and learn `org_id` from it. The `state` HMAC signature (signed
  with `var/secret`) + the one-time `consumed` flag are what make this admin read SAFE — an attacker can't
  forge a state, and admin scope is used ONLY for the signed-state lookup. The subsequent connection
  upsert + secret store then run **scoped to the resolved `org_id`** (normal tenant GUC), so the new
  connection lands under the right tenant and RLS holds from there on.

### 4.4 Token refresh (cron, durable)
- A cron scans `integration_connections WHERE status='connected' AND expires_at < now()+10min`, calls
  `connector.refresh(conn)`, re-encrypts the new bundle, updates `expires_at`. On refresh failure →
  `status='expired'` + audit + (optional) Telegram/PushNotification alert to the founder to re-auth.
- **When Hatchet present** (`orchestration-hatchet.md`): a `integration-token-refresh` cron workflow
  (`on_crons=["*/5 * * * *"]`). **When absent:** the existing `scheduler_loop` 60 s tick (`caller.py:3298`)
  calls `integrations.refresh_due()` (added in the deferred diff, flag-gated). Either way, idempotent
  (refresh is safe to re-run; a just-refreshed token simply isn't due).

### 4.5 Inbound router (`inbound.py`)
- Single deferred endpoint family `POST /integrations/hooks/{provider}/{connection_id?}` (§6).
- Flow: read raw body + headers → `connector.verify_inbound(raw, headers, secret)` (secret pulled from
  the connection's bundle; dormant → accept, matching `_verify_meta_signature`) → write an
  `integration_inbound` row (id = deterministic sha256 → **idempotent**, a provider re-delivery is a
  no-op `ON CONFLICT DO NOTHING`) → `connector.normalize_inbound()` → **dispatch** the canonical events
  to the consuming module via a registered in-process handler (e.g. `message.received` →
  `caller._handle_inbound_wa`; `payment.captured` → payments module; `order.created` → CRM lead create).
  Dispatch is best-effort + logged; redelivery handles transient consumer failure.
- **⚠ RLS BOOTSTRAP (the hook caller is a provider, not a tenant).** Like the OAuth callback, an inbound
  `POST /integrations/hooks/{provider}/{connection_id?}` arrives with NO tenant credential — yet it must
  read `integration_connections` + `integration_secrets` (both FORCE-RLS) to fetch the signing secret and
  resolve `org_id`. **FIX (same precedent):** the secret/connection LOOKUP runs in an **admin-GUC
  session** keyed by `connection_id` (and/or `provider` + the provider's account ref parsed from the
  payload). The signature verification (`verify_inbound`) is the trust gate: an attacker who doesn't know
  the per-connection `webhook_secret` can't forge a verified event, so the admin lookup is bounded and
  safe. Once `org_id` is resolved + the signature passes, the `integration_inbound` write + dispatch run
  **scoped to that `org_id`**. (When `connection_id` is absent from the URL — e.g. a shared Meta app
  webhook — resolution falls back to matching the parsed account/page id against connections via the
  admin session, then scopes down.)
- **Reuses** `_parse_meta_inbound` logic for the WhatsApp/Meta connector's `normalize_inbound`. The
  generic `webhook` connector + this inbound path are ALSO what powers **Forms / Lead-Capture**: a
  third-party form post (or a provider's `order.created`/`lead.created`) verifies → normalizes →
  dispatches `lead.created` into the CRM/Leads store — forms need no bespoke ingestion, they ride this
  router.

### 4.6 Bring-your-own-app (advanced, documented, not default)
- Default: tenants authorize against the Famit platform's OAuth *app* (one Meta app, one Google app);
  the hub stores only per-tenant tokens. Advanced tenants (agencies/white-label, per `MASTER_VISION`)
  may supply their OWN `client_id`/`client_secret` per connection — stored encrypted in the bundle, used
  for that connection's flows. The schema already supports it (`client_secret?` in the bundle). Gated +
  audited; documented as a later toggle, not built into the v1 acceptance path.

---

## 5. SAFETY & GUARDRAILS (defense-in-depth, reuse existing gates)

1. **RLS isolation** — all 4 tables FORCE RLS on `org_id` (P1 §5). A tenant can never read another's
   connection/secret/inbound rows. The OAuth `state` row is org-scoped too. **Acceptance proof = the P1
   RLS proof, extended to these tables** (§8 U-RLS). **The TWO public, tenant-less endpoints (oauth
   callback, inbound hook) are the ONLY admin-GUC readers** (§4.3, §4.5): they do a single bounded lookup
   under `is_admin=True` to resolve `org_id` (gated by the signed one-time `state` / the per-connection
   `webhook_secret`), then immediately scope down to that tenant for every write. No tenant-facing
   endpoint ever uses admin scope — that flag is set only from the resolved tenant's `is_admin`, never
   from a vendor token (P1 §5 rule, preserved).
2. **Secrets encrypted at rest** — Fernet envelope (§1.3). Even an RLS bypass / raw DB dump yields
   ciphertext. `INTEGRATIONS_ENC_KEY` lives in env/Doppler, never in the DB. Key rotation supported via
   `key_version` + a re-encrypt sweep.
3. **Secrets never leave the building in plaintext** — the API returns secrets **redacted** (first/last
   4, `vendors.redact`). A literal reveal is a SEPARATE endpoint gated by `require_step_up(scope=
   "integrations")` + audited `integration.secret.revealed`. Default UI never shows raw tokens.
4. **Step-up (PIN) on risky connect/disconnect** — connecting or disconnecting a **money-moving**
   provider (`is_money`: razorpay/stripe/meta-ads/google-ads), rotating a secret, or revealing one
   requires `require_step_up(scope="integrations")` when `FIREWALL_ENABLED` and the tenant has a PIN
   (pass-through otherwise — nothing breaks today). Reuses `firewall.py` verbatim.
5. **Money-moving gate carries to the tools** — every `ToolSpec` a money connector emits has
   `money=true`; the AI-Manager / Workflow-Studio BUDGET+APPROVAL gate fires exactly as for native
   `ads.*` tools (`platform-workflow-studio.md` §4.9). **The hub does not invent a new gate — it sets the
   flag the existing gate reads.**
6. **Inbound signature verification** — per-provider HMAC (`_verify_meta_signature` generalized). Dormant
   (no secret) → accept so the pipeline is exercisable offline; configured → strict, reject on mismatch
   (audited `integration.inbound.rejected`).
7. **Replay protection** — OAuth `state` is one-time (`consumed`), TTL 10 min; inbound rows are
   deterministically id'd → duplicate deliveries collapse.
8. **Immutable audit on every edge** — `integration.connected | disconnected | refreshed | refresh.failed
   | secret.revealed | secret.rotated | inbound.received | inbound.rejected | outbound.delivered |
   outbound.deadlettered`. Append-only via `audit.py`. No silent credential change.
9. **Rate-limit** — reuse `ratelimit.py` on the inbound + oauth-callback endpoints (public-facing).
10. **Kill-switch** — `INTEGRATIONS_ENABLED=false` (default during rollout) → the hub imports and the
    deferred router 404s/no-ops; nothing in the live `/api` references it. Per-provider disable via a
    connection `status='revoked'`.
11. **Outbound SSRF guard** — outbound webhook URLs are validated (https, public host, no internal/
    metadata IPs) before delivery — the bus must not be a pivot to internal services.

---

## 6. API SURFACE (DEFERRED router; mounted via `integrations_wiring.diff`)

All additive, tenant-resolved via `resolve_tenant` (same as the spine). Mounted ONLY when the diff is
applied; never imported by `caller.py` today. Secrets always redacted unless the reveal endpoint.

| Endpoint | Auth | Body / params | Returns |
|---|---|---|---|
| `GET  /integrations/providers` | self | — | catalog: `[{provider, auth_kind, is_money, capabilities}]` |
| `GET  /integrations/connections` | self | — | tenant's connections (status, provider, account_ref; **secrets redacted**) |
| `POST /integrations/connect/{provider}` | self (+step-up if money) | `account_hint?` (oauth) OR `secrets{}` (api_key) | oauth → `{authorize_url,state}`; api_key → `{connection_id,status}` |
| `GET  /integrations/oauth/callback` | public (state-signed) | `code,state` | redirect to panel `?connected=…` (`complete_oauth`) |
| `POST /integrations/connections/{id}/refresh` | self | — | `{status, expires_at}` |
| `POST /integrations/connections/{id}/disconnect` | self (+step-up if money) | — | `{status:'revoked'}` |
| `POST /integrations/connections/{id}/secret/reveal` | self **+ step-up** | — | `{secrets:{…plaintext…}}` (audited) |
| `POST /integrations/connections/{id}/secret/rotate` | self **+ step-up** | `secrets{}` | `{ok:true}` |
| `GET  /integrations/connections/{id}/test` | self | — | live ping (dormant→`not_configured`) |
| `POST /integrations/hooks/{provider}/{connection_id?}` | public (sig-verified) | raw provider body | `200` (verify→store→normalize→dispatch) |
| `GET  /integrations/hooks/{provider}/{connection_id?}` | public | `hub.challenge` | echo (Meta/WhatsApp verify handshake) |
| `GET  /integrations/inbound` | self | `?limit` | recent normalized inbound events |
| `GET  /integrations/tools` | self | — | `ToolSpec` list for this tenant's connected providers |
| `POST /integrations/tools/{name}/call` | self (+gate per tool flags) | `args{}` | tool result (read tools ungated; side-effecting/money gated) |
| `--- outbound (REUSES existing /webhooks CRUD) ---` | | | |
| `GET/POST/DELETE /webhooks` | self | EXISTING (`caller.py:3109/3128/3143`) | unchanged; bus now backs delivery |
| `GET  /integrations/outbound/dlq` | self | — | dead-lettered deliveries (for retry/inspection) |
| `POST /integrations/outbound/dlq/{id}/retry` | self | — | re-enqueue a delivery |

---

## 7. HOW IT SITS ON THE FOUNDATION (Postgres / Hatchet / planes / existing code)

- **Control-plane API (modular monolith).** The hub is a module *inside* the monolith — its deferred
  `APIRouter` mounts on the existing FastAPI app (`caller.py`). No new service. Matches the settled
  "modular monolith, scale by replicate+shard" verdict (`ARCHITECTURE_DECISION.md`).
- **Postgres + RLS (P1).** 4 new tables via Alembic, RLS-forced, registered in `store.py` with default
  MODE `json` (dormant byte-identical), promotable to `dual`/`pg` later — identical to every P1 store. The
  hub depends on P1's `db/engine.session(tenant_id)` for scoped access. **Until P1's tables land, the hub
  runs entirely on JSON files** (the default), so it is not blocked on P1.
- **Hatchet (P3).** Token-refresh + outbound-redelivery + long sync backfills are Hatchet crons/durable
  tasks WHEN Hatchet is `hatchet`-flagged; otherwise the `scheduler_loop` tick + the existing
  `_emit_webhook` 3×-retry cover it. Import-safe degrade both ways — the hub never *requires* Hatchet.
- **Voice plane / worker-spine.** Untouched. The hub adds no load to the latency-critical voice box; its
  inbound/oauth endpoints serve from the control-plane API, its crons run on the worker-spine.
- **REUSE vs ADD ledger:**
  - **REUSE:** `whatsapp.py` (registered as a connector + back-compat shim), `vendors/_http.py` +
    `redact`, `_emit_webhook`→`outbound.emit` shim, `webhooks`/`webhook_log` tables, `_verify_meta_
    signature`/`_parse_meta_inbound` (Meta connector), `auth.py`/`var/secret` (state signing), `firewall.py`
    (step-up), `audit.py`, `ratelimit.py`, `db/engine.py`+`store.py` (P1), the AI-Manager `ToolSpec` +
    registry, the ads module's `google_ads.py`/`meta_ads.py` (they consume hub tokens).
  - **ADD:** the connector interface + registry, the credential vault (Fernet), `oauth.py`, the inbound
    router, the outbound bus generalization + DLQ, the MCP bridge, the provider catalog + 10 connector
    files, 4 tables, the deferred router.

---

## 8. BUILD UNITS (each: mark IN PROGRESS → implement → OFFLINE ACCEPTANCE → commit → mark DONE)

> Crash-safe, additive, flag-gated. `INTEGRATIONS_ENABLED=false` throughout until U-final. Each unit is
> independently shippable; a half-done unit cannot affect the live site (router not mounted).

- **U0 — Scaffold + config + vault** (sonnet). `integrations/{__init__,config,vault,_http}.py`,
  `providers/catalog.yaml` (curated subset). **ACCEPT:** `python _smoke_integrations.py` imports the
  package under an EMPTY env without raising; `vault.put_secret`/`get_secret` round-trips a bundle with a
  test key; with no `INTEGRATIONS_ENC_KEY`, `put_secret`→`error:vault_unavailable` (no crash). Catalog
  loads + lists providers.
- **U1 — Connector interface + registry + BaseConnector** (sonnet). `connector.py`, `registry.py`,
  `tools.py`. **ACCEPT:** a stub connector subclass registers; `registry.get('x').status(None)` →
  `not_configured`; `tools_for_tenant` returns `[]` for a tenant with no connections. AST: every method
  of `BaseConnector` returns a dormant `ConnResult` and never raises.
- **U2 — Connections CRUD + store registration** (sonnet). `connections.py` + register the JSON stores in
  `store.py` (MODE json). **ACCEPT (offline):** create/list/disconnect a connection through the store
  seam; RLS proof (extend P1 U-RLS) — tenant A cannot see tenant B's connection rows; secrets redacted in
  list output.
- **U3 — OAuth flows** (opus). `oauth.py` (authlib + manual fallback). **ACCEPT (offline, no live
  provider):** `begin_oauth` returns a well-formed `authorize_url` + a state row; a forged/expired/replayed
  `state` is rejected; `complete_oauth` with a MOCKED token endpoint (monkeypatched httpx) stores an
  encrypted bundle + flips status to `connected`; audit rows present.
- **U4 — Inbound router + Meta/WhatsApp connector** (opus). `inbound.py`, `providers/meta.py`,
  `providers/whatsapp.py` (wraps existing). **ACCEPT (offline):** a signed test payload (HMAC with a test
  secret) verifies; a tampered one is rejected; verified payload normalizes via `_parse_meta_inbound` →
  one `integration_inbound` row; a re-delivery (same body) is idempotent (no dup row); dispatch handler
  invoked. Dormant (no secret) → accept (matches today).
- **U5 — Outbound bus + DLQ + `_emit_webhook` shim** (opus). `outbound.py`. **ACCEPT (offline):**
  `emit(org,event,payload)` against a MOCKED subscriber (monkeypatched httpx) signs (`X-Famit-Signature`)
  + logs to `webhook_log` IDENTICALLY to today (byte-compatible body); a 500-forever subscriber lands in
  `integration_outbound_dlq` after retries; SSRF guard rejects an internal-IP URL. **Regression gate:** the
  existing `_emit_webhook` call sites produce identical output when routed through the shim.
- **U6 — Money connectors (Razorpay/Stripe/Shopify) + step-up gating** (opus). Payment + commerce
  connectors: OAuth/key connect, inbound signature verify (Razorpay/Stripe/Shopify schemes), `is_money=
  true`. **ACCEPT (offline):** connect a money provider WITHOUT step-up (FIREWALL_ENABLED, PIN set) → 403
  `step-up required`; with `X-Step-Up` → proceeds; each provider's webhook signature verifies a known test
  vector and rejects a bad one; emitted ToolSpecs carry `money=true`.
- **U7 — Google (Ads+Calendar) + WordPress + messaging connectors** (sonnet). Round out the catalog.
  **ACCEPT:** each connector instantiates dormant, exposes its capability ToolSpecs, `connect_api_key`/
  `begin_oauth` paths offline-test with mocks.
- **U8 — MCP bridge** (sonnet). `mcp_bridge.py`. **ACCEPT (offline):** with no MCP server configured →
  zero tools, no crash; with a MOCK in-process MCP server, tools are listed as `ToolSpec`s carrying
  `side_effecting`/`money` flags and route through the same gate.
- **U9 — Token-refresh cron + Hatchet/scheduler glue** (sonnet). `refresh_due()` + Hatchet workflow +
  scheduler fallback. **ACCEPT (offline):** a connection with `expires_at` in the past is selected;
  `refresh` with a mocked token endpoint updates `expires_at`; a failing refresh flips `status='expired'`
  + audits; idempotent on re-run.
- **U10 — Deferred wiring diff + AI-Manager/Workflow-Studio binding** (opus). Write
  `integrations_wiring.diff` (mount router, point `_emit_webhook` shim, register stores, add
  `refresh_due()` to the scheduler tick). Document the `tools_for_tenant` binding the AI-Manager registry
  + Workflow Studio Integration node import. **ACCEPT:** the diff applies cleanly against a pinned
  `caller.py` snapshot in a scratch copy; with `INTEGRATIONS_ENABLED=true` in that scratch, the full
  offline suite (U0–U9) passes end-to-end; with it `false`, `/api` is byte-identical to today.

---

## 9. OFFLINE ACCEPTANCE TEST (the single command gate — zero live external calls)

`integrations/_smoke_integrations.py` + a `pytest` suite that runs with an **empty/dummy env** and
**all external HTTP monkeypatched**. The gate, in order:

1. **Import-safe:** `import integrations` and every `providers/*.py` under a bare env → no exception;
   `_smoke` instantiates every connector → all `status(None) == not_configured`.
2. **Vault round-trip:** with a test `INTEGRATIONS_ENC_KEY`, `put_secret`→`get_secret` returns the bundle;
   ciphertext at rest != plaintext; wrong key → decrypt fails closed (no crash, `error`).
3. **Connection lifecycle (mocked):** connect (api_key) → list (redacted) → disconnect; RLS isolates two
   tenants; audit rows for connect/disconnect.
4. **OAuth (mocked token endpoint):** begin→authorize_url+state; replay/expiry/forgery rejected;
   complete→encrypted bundle + `connected`.
5. **Inbound:** good HMAC verifies + normalizes + 1 row + dispatched; bad HMAC rejected; re-delivery
   idempotent.
6. **Outbound:** signed delivery to a mock subscriber matches today's `_emit_webhook` body byte-for-byte;
   permanent-failure → DLQ; internal-IP URL → SSRF-rejected.
7. **Gating:** a money connector connect without step-up (firewall on) → 403; money ToolSpec has
   `money=true`; a read ToolSpec runs ungated.
8. **Refresh:** expired connection refreshes (mock) / fails→expired; idempotent.
9. **Kill-switch:** `INTEGRATIONS_ENABLED=false` → router no-ops; the spine smoke (the P0/P1 `/api`
   contract checks) is byte-identical.

**Pass = all green offline, no network, spine `/api` unchanged.** Mirrors the house gate: every unit
backed by a build_log entry + commit so a crash costs ≤ one unit.

---

## 10. DEPENDENCIES
- **pip (into `/opt/capsy-agent/.venv`, pinned):** `authlib`, `cryptography`, `mcp`; provider SDKs are
  **lazy/optional** (`razorpay`, `stripe`, `ShopifyAPI`, `google-api-python-client`,
  `google-auth-oauthlib`) — imported defensively, absent → that connector returns `not_configured`.
- **P1 Postgres** — for `dual`/`pg` mode of the hub tables (NOT required for the dormant JSON default;
  the hub ships and offline-tests without P1).
- **Hatchet (P3)** — optional; refresh/redelivery degrade to `scheduler_loop` when absent.
- **`firewall.py`** (`credit-ledger-firewall.md`) — for step-up gating (pass-through when its flag is OFF).
- **Founder credentials:** NONE to build/ship dormant. To ACTIVATE a provider the founder pastes that
  provider's app id/secret (env/Doppler) + authorizes via the OAuth UI — exactly the dormant-until-creds
  model. `INTEGRATIONS_ENC_KEY` (one platform secret) must be generated before any real secret is stored.

## 11. MODEL ROUTING (for the implementing agent)
- **opus:** OAuth flows (U3), inbound router + Meta (U4), outbound bus + shim (U5), money connectors +
  gating (U6), wiring diff + binding (U10).
- **sonnet:** scaffold/vault (U0), interface/registry (U1), connections/store (U2), remaining connectors
  (U7), MCP bridge (U8), refresh cron (U9).
- **haiku:** `catalog.yaml` transcription, `__init__.py`, `_smoke_integrations.py`, acceptance scaffolding.

## 12. OPEN RISKS / FUTURE SEAMS
1. **Provider API/scope rot + signature schemes** — Meta/Google ship quarterly+; catalog URLs/scopes are
   env-overridable and the connector API-version is a knob (same discipline as `automation-ads.md`). The
   inbound signature schemes cited from memory (`X-Hub-Signature-256`/HMAC-SHA256 hex for Meta — already
   live in `caller.py:3002`; `X-Razorpay-Signature` HMAC-SHA256; Stripe `Stripe-Signature` `t=`+`v1=`
   scheme; Shopify `X-Shopify-Hmac-Sha256` base64) and the `mcp` Python SDK API are **verify-at-implement**
   items — the build agent confirms each against the provider's current webhook docs (and context7 for
   `mcp`) when writing that connector, exactly like the `META_ADS_API_VERSION` discipline. Each connector
   ships a known test vector in its offline acceptance (§9.5) so a scheme drift is caught immediately.
2. **Encryption upgrade** — Fernet now; KMS / `age` / per-tenant DEK is the documented next step
   (`key_version` already in schema). Not v1.
3. **OAuth client-secret custody** — platform-level app secrets in Doppler; bring-your-own-app (§4.6) is
   advanced/opt-in, audited.
4. **Inbound dispatch coupling** — dispatch handlers are in-process today; at scale they become Hatchet
   events (the §9 "wait-for-event" seam in the orchestration spec).
5. **MCP trust** — only allow-listed MCP servers; their tools obey the same gate, but a malicious server
   could mislead the LLM — keep MCP behind an explicit per-tenant allow-list + the money/side-effecting
   gate, and audit every MCP tool call.

---

## RED-TEAM FIXES (folded)

> Adversarial review 2026-06-09. Verified against on-disk `droplet_work/` (caller.py, whatsapp.py,
> store.py, db/engine.py, db/rls.sql, vendors/) and the peer design corpus (`automation-aimanager.md`,
> `platform-ai-workforce.md`, `credit-ledger-firewall.md`, `p1-postgres.md`). The architecture is sound
> and the foundation is accurately characterized — but three precision defects would bite a build agent
> on day one, and one of them is a real spend-safety hole. Fixed in place below; the body above is
> authoritative once these overrides are read.

### RTF-1 — (BLOCKING, spend-safety) The `tools/call` endpoint must NOT become a second money-path that bypasses the BUDGET gate.

**Defect.** §5.5 asserts "the hub does not invent a new gate — it sets the flag the existing gate reads,"
and §5.4 wires **PIN step-up** on money connect/disconnect. But `platform-ai-workforce.md` (lines 100,
108-109, 125-126) is explicit that a money action has **TWO independent gates, not one**:
**(a) the BUDGET node = `wallet.reserve()`** against the ACID credit ledger (`credit-ledger-firewall.md`
`wallet.py`), and **(b) the APPROVAL/PIN node = `require_step_up`**. The hub only ever wires (b) (PIN) and
the `money=true` flag — it never reserves budget. Worse, §6 exposes
`POST /integrations/tools/{name}/call` described only as "side-effecting/money gated," which is a **direct
tool-execution path that does not route through the AI-Manager/Workflow-Studio runner that owns the budget
reserve + human-approval interrupt.** A `money=true` connector op invoked through this endpoint would
satisfy PIN step-up yet **spend with no budget cap and no approval gate** — exactly the "second money-path"
the hub's own "one money-path, one gate, one audit" invariant forbids.

**Fix (mandatory).**
- `POST /integrations/tools/{name}/call` **MUST reject any tool whose `ToolSpec.money == true`** with
  `409 use_managed_runner` (or, equivalently, restrict the endpoint to `side_effecting==false` read tools
  + non-money side-effecting tools). Money tools are callable **only** through the AI-Manager runner /
  Workflow-Studio BUDGET→APPROVAL→execute path, which is the sole owner of `wallet.reserve()` +
  the approval interrupt. The hub is the *substrate that supplies the tool*, never the executor of a
  money tool.
- The hub therefore enforces, for money ops, **PIN step-up on connect/disconnect/reveal/rotate** (its own
  surface) and **carries `money=true` so the runner applies BUDGET+APPROVAL** — it must NOT offer an
  execution shortcut around the runner. Add to §9 acceptance (new **§9.10**): "a `money=true` ToolSpec
  POSTed to `/integrations/tools/{name}/call` returns `409 use_managed_runner`; only the managed runner
  can execute it (proving the budget+approval gate cannot be bypassed)."
- §5.5 wording is corrected to: "money tools carry `money=true`; **execution of a money tool is reserved
  to the managed runner (wallet BUDGET reserve + approval/PIN), and the hub's direct `tools/call` endpoint
  refuses them.** The hub adds no execution path that skips the budget reserve."

### RTF-2 — (BLOCKING, seam bug) Step-up `scope` mismatch: the firewall cannot mint `scope="integrations"`.

**Defect.** §4/§5.3/§5.4 require `require_step_up(scope="integrations")`. But the Action Firewall as
designed (`credit-ledger-firewall.md`:361) **hardcodes the minted token to `scope:"spend"`**
(`jwt.encode({...,"scope":"spend",...})`), with `"destructive"` as the only other minted scope. A token
minted by `/firewall/step-up` therefore carries `scope="spend"`, and the hub's check for
`scope="integrations"` would **never pass** — every money connect/disconnect/reveal is permanently 403,
or (if mis-wired) silently un-gated. The function name is fine (`require_step_up(request, scope)` does
exist, :364); the **scope value is unsatisfiable**.

**Fix (mandatory).** The hub does NOT invent a new scope. It reuses the firewall's existing minted scopes:
- **money connect / disconnect** → `require_step_up(scope="spend")` (it is a money-moving action; same
  scope as a spend).
- **secret reveal / rotate / disconnect of a live payment connector** → `require_step_up(scope=
  "destructive")`.

Replace every `scope="integrations"` in §4.x, §5.3, §5.4, §6 (reveal/rotate/disconnect rows), and §8 U6
with `scope="spend"` (money connect) / `scope="destructive"` (reveal/rotate/disconnect). *(Only if the
firewall is later parameterized to mint arbitrary scopes may a dedicated `"integrations"` scope be
introduced — but that is a firewall change, not a hub assumption; until then the hub uses the two scopes
the firewall actually mints.)*

### RTF-3 — (non-blocking, citation) §0 ground-truth mis-cites the auth primitive.

**Defect.** §0 cites `caller.py:341 resolve_token (tenant_id.hmac)`. There is **no `resolve_token`** in
`caller.py`. The actual function is **`_verify_token` at `caller.py:340`** —
`token == tenant_id.hmac(tenant_id, SECRET)`, verified with `hmac.compare_digest` (lines 340-347). The
mechanism the spec relies on (HMAC `tenant_id.sig`, signed with `SECRET`/`var/secret`) is **real and
correctly described** — only the symbol name/line are wrong.

**Fix.** §0 row "Auth / tenant resolution" reads: `caller.py:371 resolve_tenant` (correct) +
`caller.py:340 _verify_token` (HMAC `tenant_id.sig`, `var/secret`) — **not** `resolve_token:341`. OAuth
`state` is signed with the SAME `SECRET`/`var/secret` used by `_verify_token`. No behavioral change.

### RTF-4 — (residual risk, dependency ordering) The hub's guardrails are INERT until peer specs land.

Not a defect in the design, but state it plainly: `firewall.py` (PIN step-up), `wallet.py` (budget
reserve), and the AI-Manager `ToolSpec` registry / managed runner **do not yet exist on disk** — they are
peer design-stage specs in the same corpus (verified: `Grep` for `ToolSpec`/`require_step_up`/`wallet` in
`droplet_work/` returns nothing). This is legitimate forward-referencing for a design doc, BUT it means:
- Until `credit-ledger-firewall.md` ships, **`require_step_up` is a no-op** (and is anyway pass-through
  when `FIREWALL_ENABLED=false`, the default) — so money step-up gating is INERT.
- Until the AI-Manager runner + `wallet.py` ship, **there is no BUDGET reserve at all** — so the only
  thing protecting a money connector pre-firewall/pre-wallet is RTF-1's refusal of money tools on the
  direct endpoint (which IS enforceable hub-locally and must therefore ship in v1, not deferred).
- **Build-order constraint (add to §8):** the hub may ship dormant connectors + vault + OAuth + inbound/
  outbound BEFORE firewall/wallet/runner exist, **but money connectors (U6) and the `tools/call`
  endpoint must not go live (`INTEGRATIONS_ENABLED=true` for a money provider) until `firewall.py` AND
  the wallet/runner BUDGET gate are deployed and their acceptance proofs pass.** The RTF-1 `409` refusal
  is the hub-local safety that holds in the interim. Track this as an explicit gate in `STATE.md`.

### Things checked and found SOUND (no change needed)
- **RLS admin-GUC bootstrap (§4.3/§4.5)** — the most security-sensitive decision — is correct:
  `db/engine.py:160 session(tenant_id, is_admin)` issues `SET LOCAL app.is_admin`, and `db/rls.sql`
  policy honors `app.is_admin='1'` (USING + WITH CHECK). The signed one-time `state` / per-connection
  `webhook_secret` correctly bound the admin read. ✔
- **Dormant-until-creds canonical shape** — `whatsapp.py` (`_cfg`, `is_configured`,
  `{"status":"not_configured"}`, never raises) is exactly as described; the `BaseConnector` default is a
  faithful formalization. ✔
- **Store MODE router** — `store.py` (`json|dual|pg`, default `json`, byte-identical pass-through,
  import-safe degrade when `db.engine.available()` is False) matches the spec verbatim; the four new
  stores slot in cleanly. ✔
- **Outbound/inbound/webhook primitives** — `_emit_webhook:1300`, `webhook_log`/`WEBHOOK_FILE:119`,
  `/webhooks` CRUD `:3109/3128/3143`, `_verify_meta_signature:3002`, `_parse_meta_inbound:3017` all exist
  at the cited lines; the SUBSUME-via-shim plan is non-breaking and offline-regression-testable (§9.6). ✔
- **`ToolSpec{name,schema,fn,side_effecting,money}`** is correctly defined in `automation-aimanager.md`
  (:264-274, money/side_effecting flags); the hub's `money`-flag handoff is the right seam — RTF-1 only
  closes the *execution* bypass, the *flag* plumbing is correct. ✔

### Verdict after folding: **GO.**
Additive, dormant-until-creds, offline-verifiable, sits on the settled modular-monolith + P1-RLS
foundation without spine edits, and accurately reuses the real on-disk primitives. The two blocking
defects (RTF-1 spend-bypass, RTF-2 scope) are seam corrections, not redesigns, and are folded above.
Ship in the §8 unit order with the RTF-4 build-order gate enforced.
