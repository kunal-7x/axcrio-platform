# @growth-os/sdk

Typed client SDK. `GrowthOsClient` (tiny typed fetch wrapper) + per-surface OpenAPI types
generated from `/contracts/openapi/*` into `src/generated/` via `pnpm codegen:sdk`.

- Auth: dev JWT (user) or service token (origin/svc-to-svc), Bearer. Tenant resolved from the
  token server-side — never sent in the body (P6).
- Mutations carry an `Idempotency-Key` (P3).
- Event payload types are re-exported from `@growth-os/events` (single source of truth, P1).

Generated files are committed so the contract-drift CI gate can compare a fresh run.
