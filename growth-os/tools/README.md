# tools/ — build & dev tooling

| tool | purpose |
|------|---------|
| `codegen/` | The contracts→code pipeline (P1). `generate.mjs` (umbrella) runs `generate-types.mjs` (JSON Schemas → `@growth-os/events` typed surface) + `generate-sdk.mjs` (OpenAPI 3.1 → `@growth-os/sdk` types). `validate-schemas.mjs` ajv-validates every schema (2020-12) + negative controls. `build-registry.mjs --write/--check` is the **contract-drift mechanism** (sha256 over LF-normalized bytes; CI fails on drift). `lib.mjs` = shared helpers. |
| `scaffold/` | `make-placeholders.mjs` — idempotently creates the §20 service/agent/app README placeholders (never overwrites). |
| `demo-phase0/` | Phase-0 acceptance demo: publish `campaign.requested` → consume → ledger entry → trace (lands with `services/core`). |
| `seed/` | Tenant-Zero + dev seed data (the Origin Connection for the live Famit platform). Phase-0 placeholder. |
| `sandbox-fixtures/` | Golden platform payloads / sandbox fixtures for connector CI (§22). Phase-0 placeholder. |

```bash
pnpm codegen            # types + SDK from /contracts
pnpm contracts:validate # ajv 2020-12 + negative controls
pnpm contracts:drift    # CI gate: fail on any frozen-schema drift
pnpm contracts:snapshot # re-freeze after an intentional, version-bumped change
```
