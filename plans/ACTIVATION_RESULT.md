# ACTIVATION RESULT — Backend Secure-Activation (6 cred-free modules)

Date: 2026-06-10. Box: famit@168.144.153.145 (SSH port 22; app port 8209). venv: /opt/capsy-agent/.venv/bin/python. Services: famit-caller + famit-agent. NO git, NO paid calls.

## STABILIZE: PASS — caller.py AST_OK+IMPORT_OK, both services active, /campaigns /leads /me 200, /run 405, no restore needed.

## RESULT MATRIX

| Module | Phase A seam | Phase B | Isolation probe | Health | Core still 200 | 5xx |
|---|---|---|---|---|---|---|
| forms-surveys | ALREADY-SECURE (build_router, token) | ACTIVATED (was already on) | PASS (body tenant_id=B forged -> stored A; B sees nothing) | CRUD ok (status route-shadow 404) | yes | none |
| support | ALREADY-SECURE (wire+resolve_tenant, RLS) | ACTIVATED | PASS (body org_id=B forged -> stored A; B sees nothing) | /support/health 200 | yes | none |
| ai-manager | ALREADY-SECURE (lazy caller.resolve_tenant) | ACTIVATED | PASS (body forged -> stored A; B []; /numbers/lookup w/o service token -> 401) | /ai-manager/status 200 | yes | none |
| workflow-studio | ALREADY-SECURE (build_router, token) | ACTIVATED | PASS (body tenant_id=B forged -> stored A; B []) | /workflows/status 200 | yes | none |
| booking | ALREADY-SECURE — concern RESOLVED (build_router mounted, NOT header-trust get_ctx) | ACTIVATED | PASS (body tenant_id=B AND X-Tenant-Id:B BOTH forged -> stored A; B []) | /booking/status 200 | yes | none |
| funnels | ALREADY-SECURE — discrepancy RESOLVED (token build_router mounted, NOT bare body router) | ACTIVATED | PASS (body tenant_id=B forged -> stored A; B []) | /funnels/status 200 | yes | none |

## SEAM SECURITY VERDICT
ALL 6 seams were ALREADY token-derived as mounted. NO spoofable seam found; caller.py NOT edited.
- Booking concern (default get_ctx reads X-Tenant-Id): RESOLVED in code — caller.py mounts booking.router.build_router(resolve_tenant,...), and the X-Tenant-Id header forge was empirically REJECTED (stored org_id = the token's tenant). The dependency_overrides workaround was unnecessary.
- Funnels discrepancy (bare router reads body tenant_id): RESOLVED in code — caller.py mounts funnels.endpoints.build_router(resolve_tenant,...), the bare body-tenant router is NOT mounted, funnel_wiring.diff NOT applied. Body forge empirically REJECTED.

## FIXES APPLIED (2 real bugs, surfaced only on activation; both backed up *.ACTbak.<ts>)
1. support/router.py `_json`: datetime/Decimal -> JSON-safe (was a 500 on /support/tickets list with real rows). Backup support/router.py.ACTbak.1781088107.
2. funnels/endpoints.py: added `from fastapi import APIRouter, Request` (was /openapi.json 500 — ForwardRef `"Request"` unresolved). Backup funnels/endpoints.py.ACTbak.1781089187.

## SCHEMA PROVISIONED (these ship deferred/lazy DDL to stay byte-identical when OFF)
- support: ensure_schema() applied schema.sql + RLS.
- booking: Base.metadata.create_all (5 tables) + rls.sql via RAW psycopg2 cursor (rls.sql %I format must bypass SQLAlchemy paramstyle). RLS ENABLED + FORCED on all booking tables.

## NO-PAID-CALL PROOF
/run with a SUPPRESSED lead (+910000000000 pre-added to suppression) -> suppressed_count:1, run_job skips dial (caller.py:1722), ZERO dial/create_sip log lines. No call billed.

## FINAL POSTURE
- .env flags ON: FEATURE_FORMS, FEATURE_SUPPORT, FEATURE_WORKFLOWS, FEATURE_BOOKING, FEATURE_FUNNELS, FEATURE_AI_MANAGER = 1. AIM_SERVICE_TOKEN = generated (secrets.token_urlsafe(32), 43 chars).
- Both services ACTIVE. Core endpoints 200. openapi 200 (118 paths). Zero 5xx.
- Probe data cleaned (suppression number + PG support/booking probe rows deleted; in-memory probe rows ephemeral + tenant-scoped).
- .env backups: .env.ACTbak.1781087755 / .1781088107. caller.py backup .ACTbak.1781088107 (not edited).

## STAYS FOUNDER-BLOCKED (leave OFF; need external accounts)
- ads (Meta), payments (Razorpay/Stripe), media-gen (DO Spaces + video provider). All remain unset => default OFF.

## ROLLBACK (per module, if ever needed)
Set the module's FEATURE_* back to 0 in /opt/famit-agent/.env and `sudo systemctl restart famit-caller`. To revert a code fix: restore the .ACTbak file and restart. Booking/support schema is additive (idempotent) and harmless when the flag is OFF.
