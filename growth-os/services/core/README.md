# `@growth-os/core` — Phase-0 modular core app

ONE modular NestJS (Fastify) app (architecture decision **D1**) bundling the Phase-0 core
planes as internal modules — not 7 separate deploys. Contracts-first (P1): every endpoint
maps to a committed OpenAPI surface under `../../contracts/openapi`, and the ledger entry IS
the frozen `action_plan.schema.json` artifact.

## Modules (→ contract)

| Module | Endpoints | Contract |
|---|---|---|
| `gateway` | `GET /healthz`, `GET /readyz`, `POST /auth/token` (dev stub D5), `GET /session`, `GET /feed` (SSE) | `gateway.yaml` |
| `tenants` | `GET /me/permissions`, workspaces/members/invites CRUD, `GET /entitlements` | `tenants.yaml` |
| `flags` | `GET/PUT /policy-config`, `GET /policy-config/history`, `GET /flags`, `PUT /flags/{key}` | `flags.yaml` |
| `ledger` ★ | `POST /actions`, `POST /actions/{id}/sign`, `GET /actions`, `GET /actions/{id}`, `GET /actions/verify` | `ledger.yaml` + `action_plan.schema.json` |
| `notify` | channels/templates/`POST /notify/send` (console driver), preferences | `notify.yaml` |
| `billing` | `GET /billing/consumption` (stub; **no money path** — D6) | §7.5 |

All routes are under base path `/v1` (matches the OpenAPI `servers`).

## The load-bearing pieces

- **Hash-chained Action Ledger** (`src/modules/ledger/hash-chain.ts`): append-only, per-tenant
  chain. `hash(n) = sha256(prev_hash || canonical_bytes(plan_n))`; genesis `prev_hash` = 64
  zeros. Canonicalization sorts object keys recursively and **excludes** `ledger` + `signatures`
  (chain linkage + post-hash additions) so the `proposed → signed` flip and signature appends
  never invalidate the hash. `verifyChain()` recomputes the chain → tamper-evident (§5.5).
- **Tenant isolation (P6)**: tenant comes from the verified TOKEN (`@growth-os/auth`), never a
  request body. Every query runs inside `DbService.withTenant()`, which opens a txn and sets the
  txn-local GUC `app.current_tenant`; Postgres **RLS (enabled + FORCED on every table)** keys off
  it (migration `0001_init.sql`). A NULL tenant matches no rows (fail-closed).
- **Events (P2)**: writes emit canonical envelopes via `@growth-os/events` (validated against the
  committed JSON Schemas before they hit the bus). Phase-0 bus = in-memory (no broker, D8).
- **Money is structurally impossible (D6)**: there is no connector/executor; the ledger reaches
  only `proposed`/`signed`. Spend-changing plans additionally require a Budget-Governor stamp +
  step-up + `confirm_money` to be signable (P4) — enforced, but nothing executes in Phase 0.

## Run

```bash
pnpm --filter @growth-os/core typecheck   # green
pnpm --filter @growth-os/core test        # ledger hash-chain + service tests
pnpm --filter @growth-os/core build        # -> dist/

# Boots on the laptop with NO db/bus (degraded mode; contract surface live):
pnpm --filter @growth-os/core dev
```

## ⚠ Box / CI required to fully boot

The laptop (D8) can typecheck, lint, test, and build everything, and the HTTP surface boots in
degraded mode (no DB → DB-backed endpoints error; in-memory bus). To run the **DB-backed** paths
(RLS, ledger persistence, the publish→consume→ledger demo) you need real infra from
`../../infra/docker-compose.dev.yml` (postgres + redpanda):

```bash
# on a capable box / in CI ephemeral services:
docker compose -f ../../infra/docker-compose.dev.yml up -d postgres redpanda
export DATABASE_URL=postgres://growthos:growthos@localhost:5432/growthos
pnpm --filter @growth-os/core migrate   # applies 0001_init.sql (DDL + RLS)
pnpm --filter @growth-os/core start
```

See `.env.example` for all config.
