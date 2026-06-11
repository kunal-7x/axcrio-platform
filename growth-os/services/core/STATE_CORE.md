# services/core — Phase-0 SCAFFOLD STATE (crash-safe ledger)

Task: scaffold the CORE modular NestJS(Fastify) app against the committed contracts
(contracts-first, P1). Phase 0 ONLY. No ads/creative/signals. No git unless told.

## UNITS (flip IN PROGRESS -> DONE as each verifies)
- U1 monorepo root scaffold (turbo/pnpm workspace, tsconfig base, package.json) — DONE
- U2 packages/events (typed envelope + event types + envelope builder + ajv validator) — DONE
- U3 packages/auth (OIDC-shaped dev JWT stub + AuthContext) — DONE
- U4 packages/config (zod env loader) — DONE
- U5 core app skeleton (NestJS Fastify bootstrap, main.ts, app.module) — DONE
- U6 Postgres migrations: schema + RLS ON every table, tenant_id every row, hash-chain cols — DONE
- U7 db layer (pg pool + per-request RLS GUC set_config app.tenant_id) — DONE
- U8 gateway module (auth-token stub, /session, /healthz, /readyz, /feed SSE stub) — DONE
- U9 tenants module (workspaces/members/invites/entitlements + GET /me/permissions + RBAC map) — DONE
- U10 flags module (policy-config versioned + flags) — DONE
- U11 ledger module (★ hash-chain: POST /actions, /{id}/sign, GET /actions, /verify) — DONE
- U12 notify module (console driver send/templates/prefs) — DONE
- U13 billing stub (credit.consumed sink) — DONE
- U14 event bus port (Kafka producer iface + in-memory dev impl) + emit on writes — DONE
- U15 schema-validation wiring (responses validated vs committed schemas in tests) — DONE
- U16 typecheck green + ledger hash-chain unit test green — DONE

## RESULT (2026-06-11) — ALL GREEN
- typecheck: config/auth/events/core all clean (`pnpm typecheck` full workspace = 14/14 tasks ok).
- tests: events 6, core 16 (9 hash-chain + 7 ledger-service), auth 2, config 4 = 28 passing.
- core builds to dist (tsconfig.build excludes *.test.ts). README + .env.example written.
- box-required to BOOT db-backed paths (no Postgres on laptop) — documented in README.

## KEY DECISIONS
- Tenant from TOKEN never body (P6). RLS GUC `app.current_tenant` set per request txn.
- Ledger canonical-bytes = JSON.stringify over a STABLE key order of the plan MINUS
  {signatures, ledger}. hash = sha256(prev_hash + canonical). genesis prev_hash = 64 zeros.
- Money structurally impossible (D6): no connector/executor; ledger reaches proposed/signed only.
- Schemas are the source of truth: validate at the edge with ajv 2020 against /contracts/schemas.
