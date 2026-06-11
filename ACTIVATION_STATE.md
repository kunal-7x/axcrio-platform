# ACTIVATION — LIVE STATE LEDGER (cred-free module activation + frontend deploy)

Date: 2026-06-10. Box: famit@168.144.153.145 (key do-blr-test). App /opt/famit-agent/.
SERVICE PYTHON = /opt/capsy-agent/.venv/bin/python. Restart: sudo systemctl restart famit-caller famit-agent.
NO git. NO paid calls.

## CONTEXT LOADED (from memory)
- MOUNT WAVE 9/9 COMPLETE. caller.py box HEAD md5 bb87bd18b49c9dea152728fb7e92af60 (4404 LOC).
- ALL 9 FEATURE_* flags default OFF. Resting import caller = 79 routes, byte-identical.
- booking mounted via build_router (token-derived, is_admin hardcoded False) — NOT header-trust get_ctx.
- funnels mounted via token-deriving build_router (endpoints.py L132), NOT bare body-tenant router; funnel_wiring.diff NOT applied.
- Rollback chain: MNTbak2.1781081810 (5cc2d6b4 post-ai-manager) / .1781081110 (943bff85 post-workflow) / MNTbak.1781097663 (68218dfa post-forms).

## TARGET cred-free modules (in order): forms-surveys, support, ai-manager, workflow-studio, booking, funnels
## LEAVE OFF: ads, payments, media-gen (founder-blocked)

## PHASE A — SEAM SECURITY VERIFY (flags OFF, zero live change)
Per the mount logs, all 6 seams are token-derived at the MOUNTED surface. Verify on the live box code.
- forms-surveys: build_router(resolve_tenant,...) — VERIFY
- support: wire(resolve_tenant,...) — VERIFY
- ai-manager: bare-OK include_router, lazy resolve_tenant in routes — VERIFY
- workflow-studio: build_router(resolve_tenant,...) — VERIFY
- booking: build_router(resolve_tenant,...) is_admin=False — VERIFY (readiness get_ctx concern = stale)
- funnels: build_router(resolve_tenant,...) L132 — VERIFY (readiness body-hole concern = stale)

## PHASE B — ACTIVATE one at a time. funnels ALSO needs FEATURE_WORKFLOWS=1. ai-manager needs AIM_SERVICE_TOKEN=<random> in .env.
## PHASE C — DEPLOY FRONTEND to root@143.110.247.249:/opt/famit-panel (FORTRESS recipe).

## PHASE A RESULT — ALL 6 ALREADY-SECURE (verified in LIVE box code 2026-06-10). NO FIX needed.
Box md5 bb87bd18... matches HEAD. Services active, /campaigns 200.
- forms-surveys: build_router L43, authed routes resolve_tenant->need_auth, token-derived; /f/* public by design. SECURE.
- support: wire L49, _resolve_tenant(request) injected, token-derived. SECURE.
- ai-manager: lazy caller.resolve_tenant L42, tenant_id=t["tenant_id"]. SECURE (bare mount safe).
- workflow: build_router L183, _tid(t) token. Bare body-tenant surface NOT mounted. SECURE.
- booking: build_router L178, token-derived, is_admin HARDCODED False. Header-trust get_ctx NOT mounted. SECURE (readiness get_ctx concern STALE).
- funnels: build_router L132, _tid(t) token. Bare body-tenant router NOT mounted; funnel_wiring.diff NOT applied. SECURE (readiness body-hole concern STALE).
=> No caller.py/module edits, no *.ACTbak needed for Phase A. Flags stay OFF.

## PROGRESS
- [x] Phase A verify (all 6) — ALL ALREADY-SECURE, no fix
- [ ] Phase B activate forms / support / ai-manager / workflow / booking / funnels
- [ ] Phase C frontend deploy

## RESUME 2026-06-10 (session 2, backend-only role) — INDEPENDENTLY RE-CONFIRMED Phase A
Re-stabilized: ssh is PORT 22 (8209=app port, externally firewalled). caller.py AST_OK+IMPORT_OK, famit-caller+famit-agent ACTIVE, /campaigns /leads /me 200, /run 405. Backups present.
Independently re-read mount block + module internals; matches prior verdict EXACTLY:
- forms build_router@4267 | support wire@4197 (router.py:66-68 token) | ai_manager bare router@4358 but endpoints.py:42-46 imports caller.resolve_tenant, pins t[tenant_id] | workflow build_router@4315 firewall= | booking build_router@4104 (X-Tenant bare surface NOT mounted) | funnels build_router@4397 (body-tenant bare router NOT mounted, funnel_wiring.diff NOT applied).
=> Booking concern + funnels discrepancy BOTH resolved by code (build_router token-derive). No edit, no *.ACTbak for Phase A.
NOTE: FEATURE_FORMS=1 ALREADY in .env (forms pre-activated by prior agent) — will verify isolation, not re-activate.
Probe tokens (REAL provisioned non-admin tenants, 4 total incl admin):
  A=21d0a13603da.94415312358e02e846066aaf503d91a8d2b531ab531b564b997e237d8d68907f
  B=ae1ba3017296.dce32464e02d97192176e0a5a630ebee12d3fb91f5fa7217aff33443d6fc0690
Phase B order: forms(verify) -> support -> workflow -> booking -> funnels(+FEATURE_WORKFLOWS) -> ai_manager(+AIM_SERVICE_TOKEN). One at a time, rollback flag=0 on any fail.
.env backed up -> .env.ACTbak.1781087755 (and .1781088107 region). caller.py + support/router.py backed up -> *.ACTbak.1781088107.

### MODULE RESULTS
- [DONE] FORMS (already FEATURE_FORMS=1): 8 routes. Isolation PASS — A created form with body tenant_id=B forged -> stored org_id=A (token); B list empty. Core 200, no 5xx. /forms/status 404 quirk (route shadow), harmless.
- [DONE] SUPPORT (FEATURE_SUPPORT=1): 10 routes. ensure_schema applied (via caller-init engine). FIXED a real datetime-JSON 500 in support/router.py _json (DB rows had raw datetime). Patched _json to coerce datetime/date->ISO, Decimal->float (backup support/router.py.ACTbak.1781088107). AST_OK, import_OK, restarted. Isolation PASS — A opened ticket body org_id=B forged -> stored org_id=A; A list 200 sees it; B list empty. /support/health 200. Core 200. NO-PAID-CALL proof: added +910000000000 to suppression, /run that only number -> suppressed_count:1, zero dial lines in logs. No 5xx. Both svcs active.
- [DONE] WORKFLOW-STUDIO (FEATURE_WORKFLOWS=1): 16 routes. /workflows/status 200 (in-memory engine, hatchet dormant). Isolation PASS — A created wf with body tenant_id/org_id=B forged -> stored tenant_id=A, created_by=A; A list sees it; B list []. Core 200, no 5xx.
- [DONE] BOOKING (FEATURE_BOOKING=1): 10 routes. Tables were MISSING (deferred Alembic 0003). Provisioned booking own Base.metadata.create_all (5 tables) + applied booking/rls.sql via RAW psycopg2 cursor (rls.sql has %I format -> must NOT go through SQLAlchemy paramstyle). RLS enabled+FORCED on all tables. Isolation PASS (THE role concern) — A created resource with BOTH body tenant_id/org_id=B AND header X-Tenant-Id:B forged -> stored org_id=A. Both body+header spoof REJECTED (build_router derives from token, ignores X-Tenant-Id). A/B list no leak. Core 200, no 5xx.
- [DONE] FUNNELS (FEATURE_FUNNELS=1 + FEATURE_WORKFLOWS=1): 10 routes. FIXED a real openapi 500 bug: funnels/endpoints.py imported only `from fastapi import APIRouter` (NOT Request) while every route annotates `request: "Request"` (ForwardRef) -> with `from __future__ import annotations`, pydantic 2.13 couldnt resolve the name -> /openapi.json 500 (routes still served, but schema broke; frontend depends on it). Patched import to `APIRouter, Request` + `Request = None` fallback (matches workflow.endpoints proven pattern). Backup funnels/endpoints.py.ACTbak.1781089187. AST_OK, restart, openapi 200. Isolation PASS (THE role discrepancy) — A created funnel with body tenant_id/org_id=B forged -> stored tenant_id=A, created_by=A; A list sees it; B list []. Body-tenant spoof REJECTED => build_router (token) mounted, NOT bare body router. Core 200, no 5xx.
- [DONE] AI-MANAGER (FEATURE_AI_MANAGER=1 + AIM_SERVICE_TOKEN generated via secrets.token_urlsafe(32), 43 chars, in .env): 7 routes. /ai-manager/status 200 (all providers dormant). Isolation PASS (STRONGEST) — A registered number with body tenant_id/org_id=B forged -> stored tenant_id=A, registered_by=A; A list sees it; B list []. Body spoof REJECTED (lazy caller.resolve_tenant). SERVICE-TOKEN GATE: /numbers/lookup with normal tenant auth (no bearer) -> 401 "service token required". Core 200, no 5xx.

## PHASE B COMPLETE — ALL 6 ACTIVATED, ALL ISOLATION PROBES PASS, ZERO 5XX, BOTH SVCS ACTIVE
Founder-blocked ADS/PAYMENTS/MEDIA remain OFF (not set => default OFF).
Probe data cleaned: suppression +910000000000 deleted; PG support ticket+msg + booking resource deleted; in-memory forms/wf/funnel/aim probe rows ephemeral+tenant-scoped.
Code fixes applied (2 real bugs, both surfaced only on activation):
  1. support/router.py _json -> datetime/Decimal JSON coercion (was 500 on list with real rows). Backup support/router.py.ACTbak.1781088107.
  2. funnels/endpoints.py -> import Request (was openapi 500: ForwardRef unresolved). Backup funnels/endpoints.py.ACTbak.1781089187.
Schema provisioned: support (ensure_schema), booking (Base.metadata.create_all + rls.sql via raw psycopg2 cursor, RLS forced).
.env backups: .env.ACTbak.1781087755 / .1781088107. caller.py NOT edited (backup .ACTbak.1781088107 taken anyway).
- [x] Phase B activate ALL 6 — DONE
- [ ] Phase C frontend deploy (separate role; NOT this backend session)
</content>
</invoke>
