# GROWTH OS — monorepo

Autonomous ads & marketing automation. **Multi-tenant, API-first "AI Marketing Department."**
The live Famit/Axcrio platform is **Tenant Zero** (the first API consumer + the reused
Engagement/Creative planes), reached only over the Origin Platform Connector — never the host.

> Build bible: [`GROWTH-OS-BUILD-SPEC.md`](./GROWTH-OS-BUILD-SPEC.md). §2 principles **P1–P12 are LAW**.
> Builder rules: [`CLAUDE.md`](./CLAUDE.md). Phase-0 architecture: [`docs/architecture-phase0.md`](./docs/architecture-phase0.md).
> **Contracts-first (P1):** no service code before its contract exists in [`/contracts`](./contracts).

## Stack (§4, decided — do not relitigate)
- **Monorepo:** Turborepo + pnpm (TypeScript) · uv workspaces (Python).
- **Product services:** NestJS (Fastify). **Agents/ML:** Python 3.12 / FastAPI.
- **Durable workflows:** Temporal. **Event bus:** Redpanda (Kafka API) + JSON-Schema registry.
- **OLTP:** Postgres 16 (schema-per-service, RLS). **Analytics:** ClickHouse. **Cache/locks:** Redis.
- **Object store:** S3 / MinIO (dev). **Vector:** pgvector. **Observability:** OpenTelemetry.
- **Contracts:** OpenAPI 3.1 (sync) + AsyncAPI 3 (events) + JSON Schema in `/contracts`.

## Layout (§20)
```
contracts/   OpenAPI + AsyncAPI + JSON Schemas + drift registry  (FROZEN-after-merge; source of truth)
packages/    events · sdk · auth · metering · config · ui        (shared TS libraries)
services/    NestJS bounded contexts (core + data + activation + creative + engagement + experience)
agents/      Python/FastAPI intelligence plane (uv workspace)
apps/        dashboard (Next.js) · lp-runtime (landing pages)
infra/       docker-compose.dev.yml + terraform/helm placeholders
evals/       agent + optimizer eval harness (§22)
tools/       codegen (schemas→TS, OpenAPI→SDK, contract-drift) · seed · sandbox-fixtures
```

## Quickstart
```bash
pnpm install            # install the TS workspace
pnpm codegen            # schemas → TS types (packages/events), OpenAPI → SDK (packages/sdk)
pnpm contracts:validate # ajv-validate every JSON Schema (2020-12)
pnpm contracts:drift    # FAILS if committed contracts/generated diverge from a fresh run (CI gate)
pnpm typecheck && pnpm lint && pnpm test
pnpm infra:up           # boot the dev stack (postgres/redpanda/clickhouse/temporal/redis/minio) — BOX REQUIRED
```

> **HONEST ENV NOTE:** the full 6-container dev stack needs a real box (this laptop is too small and
> the DO droplet quota is 3/3). All infra is written as **files** and validated statically; booting it
> is documented but not runnable here. See [`infra/README.md`](./infra/README.md).

## Phase
**Phase 0 — Skeleton & Rails** only (§21). Do not build Phase 1+ business logic.
Per-phase progress: [`SCAFFOLD_STATE.md`](./SCAFFOLD_STATE.md).
