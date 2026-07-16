# Twenty CRM integration — STATE

Deeply integrates **Twenty** (https://twenty.com) as Haptica's relational sales-CRM
engine, surfaced as **Leads & CRM → Sales CRM** (`/crm/sales`). NO iframe: the panel
renders native Haptica UI over a normalized `/twenty/*` contract this module serves;
the workspace API key stays server-side.

## Why this shape
Twenty's frontend is a separate React app and its backend is a GraphQL/REST server.
Embedding its UI would mean an iframe (off the design system) and exposing the key to
the browser. Instead we use Twenty purely as the **CRM data engine** (its REST API +
flexible data model) behind Haptica's API, and build the UI natively in the Core
design system. This is the same "module behind caller.py" pattern as forms/workflow/
comm.

## Backend (`droplet_work/twenty_crm/`)
- `client.py` — async httpx client to Twenty's Core REST API. Handles auth (Bearer),
  the colon-form filter syntax, `depth`/`limit`/cursor paging, envelope unwrapping
  across versions, error mapping (401/403/404/429/timeout → `TwentyError`), and live
  stage-option discovery from the metadata API.
- `normalize.py` — record↔flat mappers for Twenty's composite fields (FullName,
  Emails, Phones, Links/`domainName`, Currency/`amountMicros`=major×1e6, Address) +
  the `body`/`bodyV2` rich-text drift.
- `store.py` — per-tenant connection settings (`{base_url, api_key}`) in
  `VAR/twenty_connections.json`. Key is secret: reads return only a masked tail.
  Resolution = tenant connection → env fallback (`TWENTY_API_URL`/`TWENTY_API_KEY`).
- `router.py` — `build_router(resolve_tenant, can, need_auth, forbidden, *, var_dir,
  env_url, env_key)`. Tenant-scoped (connection from token-derived `tenant_id`),
  writes gated by `can(t,"write")`, reads dormant-safe (`{connected:false}`+empty).
- `_smoke.py` — offline test (`python3 -m twenty_crm._smoke`): normalizers, envelope
  unwrap, store masking/isolation/env-fallback, the async client vs a mocked Twenty,
  and the full router via FastAPI TestClient (dormant → connect → write-gate → CRUD →
  stage-move → disconnect). 51 checks, all green.

### Endpoints (prefix `/twenty`)
`GET status` · `POST connect` (verifies creds before saving) · `POST disconnect` ·
`GET meta/stages` · companies/people/opportunities `GET list` (+search/cursor),
`POST`, `GET {id}` (detail+relations+activity), `PATCH {id}`, `DELETE {id}` ·
`GET opportunities?group=stage` (kanban columns) · `POST notes` / `POST tasks`
(attach via *Targets) · `POST sync/leads` (value bridge: voice leads → People +
pipeline Opportunities, ≤50/import, stage-mapped from lead status).

### Mount (caller.py, after the comm mount)
Import-guarded; `FEATURE_TWENTY_CRM` (default **1** — additive + dormant-safe; set 0
to unmount); passes `VAR` + the optional env fallback creds.

## Frontend (`famit-panel/app/crm/sales/`)
`client.ts` (dormant-safe typed client to `/api/twenty/*`), `_ui.tsx` (stage chips/
colors, money, avatar — reuses `app/crm/_ui`), `page.tsx` (hub: Connect state +
Pipeline/Companies/People tabs + drawer + modals), `_components/` (ConnectPanel,
PipelineBoard = drag-to-stage kanban, CompaniesView, PeopleView, RecordDrawer =
detail+notes+stage-move+delete, forms = create + Import-from-Leads).
Nav: a "Sales CRM" child under WORK (`feature_key: sell.crm`); `/crm` links across to
it ("Sales Pipeline"); the Sales page links back to Customer 360.

## Self-hosted, zero-touch mode (`provision.py`) — PRIMARY in prod
Twenty runs INSIDE Haptica (`deploy/docker-compose.twenty.yml`: server + worker +
its own Postgres + Redis, internal-only at `http://twenty:3000`). When
`TWENTY_SELF_HOST=1`, opening Sales CRM auto-provisions the tenant's OWN isolated
Twenty workspace — no API key, no clicks.

`provision.py` runs the headless chain (VERIFIED against Twenty **v2.14.4** — pin
`TWENTY_TAG`, the schema drifts between versions):
`signUp` → `signUpInNewWorkspace` (no args) →
`getAuthTokensFromLoginToken(origin=subdomainUrl)` → `activateWorkspace(data:{displayName})`
→ `getRoles` (admin role) → `createApiKey(input:{name,expiresAt,roleId})` →
`generateApiKeyToken` → durable per-tenant Bearer token (stored, `source:self_host`).
Identity is deterministic per tenant (email+password derived from
`TWENTY_PROVISION_SECRET`+tenant_id) so retries re-auth the same user.
`purge_seed_data()` drops Twenty's ~16 demo records so the client starts empty.

Router: `GET /twenty/status` adds `self_host`; `POST /twenty/provision` (idempotent,
per-tenant asyncio lock, write-gated) creates the workspace. Frontend `SetupPanel`
auto-fires provision for a writer ("Setting up your CRM…") and replaces the API-key
Connect form; read-only users poll until a teammate finishes.

**Cap:** a self-hosted Twenty server allows **5 workspaces** without an enterprise
key — `signUpInNewWorkspace` raises a capacity `ProvisionError` (HTTP 507) beyond
that; the panel shows "CRM capacity reached". Beyond 5 tenants: enterprise key or a
second Twenty server.

## Operating it
- **Self-hosted (prod default):** bring up `docker compose -f
  deploy/docker-compose.twenty.yml --env-file deploy/.env.deploy up -d`; set
  `TWENTY_SELF_HOST=1` + `TWENTY_INTERNAL_URL=http://twenty:3000` +
  `TWENTY_PROVISION_SECRET` on the backend, rebuild backend. Tenants just open Sales
  CRM → it provisions. Reset for a clean slate: `down` + drop `twenty-db-data` /
  `twenty-local-data` volumes + delete `FAMIT_VAR/twenty_connections.json` + `up`.
- **External (fallback):** `TWENTY_SELF_HOST` off → Connect form; paste Workspace
  URL + API key, or set `TWENTY_API_URL`/`TWENTY_API_KEY` env default.

## Verified
`py_compile` clean (module + caller.py); `_smoke` 57/57; provisioning identity
deterministic; frontend `tsc --noEmit` 0 errors; `next build` ✓ (`/crm/sales`).
LIVE on prod (v2.14.4): full chain provisions an isolated workspace per tenant,
per-tenant data isolation confirmed (a company in tenant A is invisible to tenant B),
seed-purge works, and the HTTP path (status→provision→pipeline) is green.
