# BRAIN — Foundation Control Layer (Super-Admin control center, Tier-0)

Durable facts for the control-layer subsystem. Append, never delete.
Founder spec: `caps/Z.MD`. Full architecture + unit build plan: `caps/design/spec-control-layer.md`.

## WHAT IT IS
Super-Admin-only control center giving the main admin total, real-time, no-deploy control over every
vendor (tenant): per-vendor (and global) HIDE/LOCK of any module/page/feature/action, plans, status
(active/trial/suspended/disabled/expired), credits, usage limits — all audited, enforced FE+BE.

## KEY DESIGN DECISIONS (locked)
- **We are ~60% there.** Reuse the LIVE spine: forced-RLS multi-tenancy (P1), `is_admin`+`/tenants`
  admin gate, `role:` nav gating (`contstants/navigation.tsx` + `lib/auth.ts` + `Sidebar/resolveNav`),
  `/usage*`+caps, wallet (F4), immutable `events` audit, Logto orgs/RBAC. Do NOT rebuild tenancy/auth.
- **Central Entitlement Engine** `entitlements.py` (NOT scattered `if vendor==x`). Resolution =
  most-specific-wins: status → per-vendor override → plan → global default → parent-rolldown; unknown =
  HIDDEN (fail-closed). New tables: `feature_registry`, `plans/plan_entitlements/plan_limits`,
  `tenant_entitlements`; JSON-first under `var/control/` then strangle to PG (F2/F4 pattern).
- **Backend is the ONLY real boundary.** ONE middleware: path→feature_key→`assert_access`; HIDDEN→404
  (no info leak), LOCKED→402, core routes bypass (anti-lockout). Frontend HIDE/LOCK is cosmetic.
- **TWO orthogonal axes:** ROLE (user: admin/manager/agent) vs ENTITLEMENT (tenant plan/flags). Both must pass.
- **Real-time = poll `/me/entitlements` (version stamp) every ~20-30s + on focus/route-change.** API
  denies revoked features immediately regardless, so poll is UI-freshness only (no socket infra needed).
- **Resting state byte-identical / default-OFF** (`CONTROL_ENABLED` flag) until smoke passes. Never touch
  the voice run-path; control reads at the API/run-gate layer only.

## UI REUSE (IRON RULE — port Core_2, don't invent). Our panel already ported Switch/Tabs/Badge/KpiCard/
Card/PageHeader/Table/Modal/Search/Select.
- Vendor list → `templates/Customers/CustomerList/CustomerListPage`. Vendor Workspace →
  `.../DetailsPage` (left `Customer` profile card + right `Details` tabs). Permissions tab →
  `templates/SettingsPage/Menu` + `Switch`. Global flags → `SettingsPage`. Plans → `Products`/
  `UpgradeToProPage`. Usage → `Customers/OverviewPage`. Audit → `Notifications`/`Table`. Overview → `HomePage`.
- New nav group "Super Admin", all children `roles:"admin"`. LOCK nav child reuses the EXISTING
  `comingSoon` dimmed-pill pattern in `Sidebar/Dropdown`.

## TOP SECURITY (do not regress)
1. Backend middleware is the real lock (404 hidden / 402 locked, fail-closed) — never ship FE-only.
2. `/admin/*` cross-tenant power only behind `is_admin`(→Logto admin-org+`manage_tenants`); vendor token=403.
   Impersonation = firewall PIN step-up + short-TTL `act_as` token + read-only default + banner + both-ends audit.
3. tenant_id ALWAYS token-derived (never body); new tables ship FORCED RLS (P1 shape); re-run isolation probe.

## BUILD ORDER (12 units, see spec §10): C0 registry+engine(opus) → C1 status+plans → C2 admin routes(opus)
→ C3 enforcement middleware(opus) → C4 version/cache → C5 suspend/trial sweep → C6 FE entitlement plumbing
→ C7 vendor list+workspace → C8 permissions tab → C9 flags/plans/usage/audit pages → C10 AI Copilot gate
→ C11 impersonation(opus) → C12 CI drift-guard + isolation re-probe + deploy. One agent per file on caller.py
(serialize); FE partition by page (C6 shared-file lands first/alone). Ledger: `caps/CONTROL_LAYER_STATE.md`.

## BUILD STATUS — CL-B1 (C0+C1) SHIPPED ✅ 2026-06-10 (default-OFF, resting byte-identical)
Engine + tables + seed LIVE on box (`famit@168.144.153.145:/opt/famit-agent/`), CONTROL_ENABLED still OFF.
NEW files (caller.py UNTOUCHED): `entitlements.py` (engine + OpenFeature facade), `db/ddl_control.sql`
(7 tables: feature_registry/plans/plan_entitlements/plan_limits/entitlement_audit GLOBAL no-RLS,
tenant_entitlements+tenant_status FORCE-RLS P1 shape), `var/control/registry.json` (91 keys, default
ON, 6 core), `var/control/plans.json` (trial/plan_a-default/plan_b/enterprise). Resolution §2 PROVEN:
43/43 local logic checks + PG smoke (FORCE-RLS confirmed, T8 isolation floor proven, override/status/
core honored). Service venv = `/opt/capsy-agent/.venv` (NOT famit-agent/.venv — no sqlalchemy there).
GOTCHA: a literal `%` ANYWHERE in DDL (even a comment) breaks psycopg2 exec_driver_sql → 0 tables; keep
ddl percent-free (SECURITY INVARIANT #4 is also functional). Full log: `memory/build_log/wave-build-
control-layer.md`. State ledger: `caps/CONTROL_LAYER_STATE.md`. NEXT = C2 admin routes (serialize on caller.py).

## BUILD STATUS — 🟢 LIVE + ENFORCING IN PRODUCTION ✅ 2026-06-11 (CL-ACT, full stack activated)
ALL 12 units shipped (CL-B1..B4 backend + CL-F0..F3 frontend) + ACTIVATED end-to-end. `CONTROL_ENABLED=1`
+ `FIREWALL_ENABLED=true` set in `/opt/famit-agent/.env` (backup `.env.CLbak.20260610-195647`); caller.py
md5 `dd872d9` UNCHANGED (only .env edited). Super Admin UI deployed to the FORTRESS panel box
(root@143.110.247.249:/opt/famit-panel, backup `/opt/famit-panel.CLbak.1781120589`) — built ON-BOX (node20),
famit-panel active, /super-admin/* live behind SuperAdminGuard + nav roles:"admin".
- **LIVE T1-T18 re-run over REAL HTTP** vs the running uvicorn (NOT in-proc): **18 PASS / 0 FAIL / T18 N/A**.
  HIDE->404, LOCK->402+upsell, restore->200, SUSPEND->non-core 404 floor + login-block + JWT-revoke + data
  preserved + restore, audit before/after on PG events leg, act-as step-up (id-bound, read-only, can't climb/
  target-admin, both-ends audited), no cross-tenant cache bleed, resting byte-identical. Legacy `FamitCall2026`
  -> 403 on /admin/* (also verified through Cloudflare). Voice agent.py UNTOUCHED (0 control refs; latency moat).
  Zero 5xx; both services active; box pristine.
- **RESIDUAL** (recorded, not a blocker): panel /login mints a STATELESS hmac token (no jti) so revoke_all
  (JWT-refresh only) can't cryptographically kill a held hmac bearer — suspension is enforced by the STATUS
  FLOOR (non-core 404) + login-block instead (T15 PASSES; vendor fully neutralized). Same class as the
  legacy-password finding. Harden later via JWT-only panel login or an hmac token-epoch.
- **DEFERRED**: C10 AI Copilot entitlement gate (T18 N/A — no copilot tool route in caller.py yet).
- Ledger: `caps/CONTROL_ACTIVATION_STATE.md`. Full activation report: `memory/build_log/wave-build-control-layer.md` (CL-ACT).
- ROLLBACK: backend restore .env.CLbak + restart; frontend restore /opt/famit-panel.CLbak.1781120589 + restart famit-panel.
