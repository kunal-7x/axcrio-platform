# PHASE 0 — Monorepo Scaffold STATE

Owner: scaffold subagent. Task: Turborepo + pnpm (TS) + uv (Py) monorepo per §20.
Contracts already exist (frozen, sha256 drift). DO NOT touch contracts/. NO git.

## PARALLEL-SESSION PARTITION (reconciled on disk, not assumed)
A SEPARATE "services/core" session is active in this same monorepo. It OWNS:
`packages/{events,auth,config,otel}`, `services/core`, and the core codegen scripts
`tools/codegen/{lib,validate-schemas,build-registry,generate-types}.mjs`.
To avoid a write race I did NOT touch any of those. My partition (below) is disjoint.

## MY UNITS (scaffold) — all DONE + verified
- [DONE] U1 root dotfiles: .editorconfig, .gitignore, .npmrc, .nvmrc, .prettierrc.json,
  .prettierignore, eslint.config.mjs (flat), README.md, pyproject.toml (uv workspace root).
  Extended existing root package.json (added codegen/sdk/lint/format scripts + devDeps:
  json-schema-to-typescript, openapi-typescript, ajv(+formats), js-yaml, @redocly/cli, eslint,
  typescript-eslint, prettier). Existing turbo.json/tsconfig.base/pnpm-workspace kept as-is.
- [DONE] U2 packages I own: sdk (OpenAPI types + typed fetch client), metering (cost meters port,
  INR paise), ui (cn()+tokens, react peer). Each: package.json+tsconfig+src+README. (events/auth/
  config/otel = core agent.)
- [DONE] U3 service/agent/app skeleton via tools/scaffold/make-placeholders.mjs (idempotent, never
  overwrites): 35 service READMEs (all §20 except core), 8 agent READMEs + uv pyproject + src/__init__,
  2 app READMEs, plane READMEs (services/agents/apps), evals/ + tools/ READMEs. 59 files created.
- [DONE] U4 infra/docker-compose.dev.yml (postgres16, redpanda+console, redis, clickhouse,
  temporal+UI, minio — pinned tags) + .env.example + infra/README (BOX-REQUIRED note) +
  terraform/helm placeholders.
- [DONE] U5 tools/codegen additions: generate-sdk.mjs (OpenAPI 3.1 -> packages/sdk/src/generated via
  openapi-typescript) + generate.mjs (umbrella runs types+sdk). (types/validate/registry = core agent.)
- [DONE] U6 .github/workflows/ci.yml: 3 jobs — contracts(validate+drift+codegen-fresh+redocly),
  typescript(lint+typecheck+test via turbo), python(uv ruff+mypy). working-directory: growth-os.
- [DONE] U7 install + verify (see below).

## VERIFICATION (all green for MY deliverables)
- `pnpm install` + `pnpm install --frozen-lockfile` PASS (9 workspace projects; lockfile refreshed).
- `pnpm contracts:validate` PASS (25 schemas, 6/6 negative controls).
- `pnpm contracts:drift` PASS (25 frozen schemas match snapshot).
- `pnpm codegen` PASS (24 event/artifact types -> events; 6 OpenAPI modules -> sdk). SDK gen idempotent.
- `pnpm lint:root` (eslint flat) PASS — 0 errors, 0 warnings.
- typecheck PASS for @growth-os/{sdk,metering,ui} (my packages).
- redocly lint on contracts/openapi/*.yaml PASS (valid; warnings only).
- uv workspace resolves (fastapi/uvicorn/ruff/starlette) — Python workspace valid.

## ⚠ BLOCKER (NOT mine to fix — core agent's domain) -> reported to orchestrator
`@growth-os/events` BUILD FAILS. Core agent's tools/codegen/generate-types.mjs emits
`packages/events/src/generated/catalog.ts` importing `<Name>Payload` (e.g. LeadScoredPayload) but
`payloads.ts` exports `<Name>` (LeadScored) — because json-schema-to-typescript uses each schema's
`title` instead of the passed typeName. Also DUPLICATE `Explanation` + `CreativeDNA` interfaces
(declared per referencing schema -> TS2300). Fix (core agent): in generate-types.mjs either strip
`title` before compile / pass `{ ... , title:undefined }`, or set declareExternallyReferenced once +
name the export with the Payload suffix consistently, and dedupe shared $ref'd types. Until then the
CI `typescript` job (whole-workspace typecheck) will fail — correctly surfacing the break.

## RUNTIME NOTE (honest, D8)
docker-compose.dev.yml + uv workspace are written + statically validated but the 6-container stack
is NOT booted here (laptop too small; DO droplets 3/3). Prod = box/limit-raise or managed
(Postgres+ClickHouse+Kafka-API+Temporal-Cloud). Documented in infra/README.md.
