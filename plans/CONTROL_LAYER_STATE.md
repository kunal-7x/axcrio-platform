# CONTROL LAYER — BUILD STATE (crash-safe ledger)

Backend box: `famit@168.144.153.145:/opt/famit-agent/` (SOURCE OF TRUTH). Local staging:
`C:\Users\kunal\Desktop\caps\droplet_work\control\` → scp to box.
Resting discipline: ships behind `CONTROL_ENABLED=0`; additive-only; rollback = restore `*.CLbak.<ts>`.

## UNIT CL-B1 (= plan C0 + C1): DATA MODEL + ENGINE + SEED

- [DONE] Build `db/ddl_control.sql` — feature_registry (GLOBAL, no RLS), plans/plan_entitlements/
  plan_limits (GLOBAL), tenant_entitlements + tenant_status (FORCE-RLS, P1 shape), entitlement_audit
  (append-only mirror; events leg is truth). Zero `%`/`format('%I')` — explicit per-table DDL.
- [DONE] Seed `var/control/registry.json` — 91 keys from explore §B, default ON; 6 core keys.
- [DONE] Seed `var/control/plans.json` (Trial / plan_a=Growth default / plan_b / Enterprise).
- [DONE] Build `entitlements.py` — mirrors crm/core.py: lazy ensure_schema(), import-safe degrade,
  db.engine.session GUC; resolve_modes/mode_for/assert_access/effective_limits per datamodel §2;
  OpenFeature-style facade (swappable store). feature_key_for_path (longest-prefix + shared map).
- [DONE] LOCAL smoke: 43/43 resolution checks PASS (_smoke_entitlements.py) — precedence, rolldown,
  core floor, status gate, unknown→hidden, path→key. NO caller.py edit in CL-B1 (engine+tables only).
- [DONE] Deploy to box + PG-side schema/RLS smoke. 7 tables applied; FORCE-RLS confirmed on the 2
  tenant tables (off on globals); T8 isolation floor PROVEN (tenant-GUC sees 0 cross-tenant rows);
  PG resolution honors override/status/core. Smoke rows cleaned.
- [DONE] CONTROL_ENABLED stays OFF; restarted famit-caller+famit-agent (both active); core
  /me /campaigns /leads → 200, /run/preview → 405 (POST-only), ZERO 5xx. caller.py untouched.
- [DONE] build_log → memory/build_log/wave-build-control-layer.md.

## UNIT CL-B1 — ✅ COMPLETE 2026-06-10. Next: C2 (admin routes) — SERIALIZE on caller.py.

## UNIT CL-B2 (= plan C2 gate + C3 choke-point): require_super_admin + FAIL-CLOSED MIDDLEWARE

- [DONE 2026-06-10] caller.py patched (SERIALIZE — one agent). Backup `caller.py.CLbak.20260610-180847`.
  1. `_auth_method(request)` — re-derives jwt|legacy_pw|hmac from the cred (non-mutating; resolve_tenant
     return contract UNCHANGED). 2. `_is_super_admin`/`require_super_admin(request)` = is_admin AND
     auth_method != legacy_pw (EXCLUDES the static CALLER_PASS/"FamitCall2026" bearer; mirrors /tenants:3043,
     returns 403 not 404 — admin-plane existence isn't secret). 3. `_enforce_entitlement_mw` =
     `@app.middleware("http")` that RETURNS (never raises -> no 500-leak; matches the _rate_limit_mw
     return-pattern) 404 hidden / 402+upsell locked via entitlements.feature_key_for_path + evaluate();
     CORE keys + unmapped legacy paths + /admin/* + infra/docs all pass; admin tenants not gated; tenant
     resolved from TOKEN; tenant=None passes through (route owns its 401). Gated behind CONTROL_ENABLED
     (default 0 = byte-identical no-op). + entitlements import (`_ent_mod`) + `_ent_mod.init()` at startup
     (CONTROL_READY). 4. `CONTROL_ENABLED` flag near LEGACY_TOKEN_ENABLED.
  - SMOKE `_smoke_clb2.py` (capsy venv, real vendor 21d0a13603da, control-rows-only, cleaned): with
    CONTROL_ENABLED=1 -> require_super_admin {legacy_pw->403, vendor->403, no-creds->401, JWT-admin->pass};
    middleware {GET /calls hidden->404, /campaigns locked->402+upgrade, /me core->not-blocked, /health->200}.
    With CONTROL_ENABLED off -> middleware no-op (all pass). 25/25 PASS. Box pristine (0 control rows).
  - LIVE: CONTROL_ENABLED absent in .env (defaults OFF). Restarted famit-caller+famit-agent (both active).
    Regression: /health /me /campaigns /leads /calls /tenants /billing/overview ->200, POST /run/preview->200,
    ZERO 5xx in journal. CONTROL_READY=True, CONTROL_ENABLED=False, 91 registry keys. Live caller==staged.
  - NOTE: /me/entitlements route itself NOT added here (that is C2/C4) -> currently 404; its core key
    core.me_entitlements already bypasses enforcement so it's wired the moment C2 adds the handler.

## UNIT CL-B2 — ✅ COMPLETE 2026-06-10. Next: C2 (full /admin/* + /me/entitlements routes), C4 (ent_version
## bump on writes + ETag), C5 (suspend/run-gate). All SERIALIZE on caller.py.

## UNIT CL-B3 (= plan C2 admin API + /me/entitlements + C4 ETag + C11 act-as) — ✅ COMPLETE 2026-06-10
- Engine WRITE helpers in entitlements.py: set_override/clear_override/set_status/set_plan/set_global_flag
  (PG write as admin GUC + bump_version + entitlement_audit mirror); resolved_with_provenance/vendor_detail/
  registry_tree/plans_detail for the admin UI; act_as token mint/verify in auth.py (ACT_AS_TTL=600,
  sub=vendor, real_admin, scope, is_admin=False). All audited to events channel=control (old/new).
- caller.py /admin/* block (require_super_admin gate, token-derived target=path id, audited via
  _control_audit -> PG events leg + mirror): /admin/features /admin/flags(+PUT) /admin/plans(+POST/PUT)
  /admin/vendors(+/{id}) /admin/vendors/{id}/entitlements/{key}(PUT/DELETE) /plan /status(suspend=
  revoke_all instant-kill + status floor + login-block; disabled=step-up) /credits(step-up) /impersonate
  (step-up, no-admin-target, read-only default, X-Act-As hdr) + /admin/act-as/exit + GET /me/entitlements
  (ETag/304). + always-on act-as read-only write block (_act_as_readonly_block, independent of
  CONTROL_ENABLED). Backups *.CLbak.20260610-232358. caller.py 0 lines removed (additive).
- GATE _smoke_clb3.py (CONTROL_ENABLED=1, real vendor, cleaned): ALL PASS — 13 routes registered;
  T1 vendor->403 all /admin/*; T2 legacy_pw->403/no-creds->401; /me/entitlements map+ETag+304; T3
  token-derived; override/status(T15 suspend+login-block)/plan writes reflected+ent_version bump;
  T10 read-only act-as POST->403; T11 act-as->/admin/*->403; T12 impersonate-admin->403. T14 verified:
  control writes on IMMUTABLE events leg w/ old/new+actor+target+real_admin (events.id is HASH not serial,
  order by `at`). LIVE: CONTROL_ENABLED off, restarted, core 200, POST /run/preview 200, T2-live legacy
  admin->403 on /admin/*, /me/entitlements 200 all-on; ZERO 5xx. Box pristine (0 control rows). 16 admin
  routes, CONTROL_READY=True.

## UNIT CL-B3 — ✅ COMPLETE 2026-06-10. Next: C5 run-loop suspend gate (dial loop no-new-dials +
## per-lead status re-read) — small follow-up; then C10 Copilot gate; then FE wave C6-C9/C11-banner.

## UNIT CL-B4 — T1–T18 ISOLATION/IMPERSONATION PROBES + DORMANT VERIFY — ✅ COMPLETE 2026-06-10
- Consolidated probe `_probe_t1_t18.py` (local: caps/droplet_work/control/, removed from box after run).
  Run in-process vs caller.app (TestClient + firewall predicate + PG events-leg SELECT). CONTROL_ENABLED
  forced ON in-process for T4–T7, OFF for T17; live .env NEVER edited, service NEVER restarted.
- RESULT: **T1–T17 ALL PASS, T18 N/A** (C10 Copilot gate not built/deployed — deferred unit). Real vendor
  21d0a13603da (+ ae1ba3017296 for T16); CONTROL rows only, deleted; box pristine.
- DORMANT VERIFY: caller.py md5 dd872d9… byte-stable; CONTROL_ENABLED absent/OFF; FIREWALL_ENABLED=false
  (pre-existing, untouched); both services active; live HTTP core+module routes 200 (incl /calls /campaigns
  which the probe made 404/402 in-process only → live NOT enforcing, isolation proven); POST /run/preview
  200; /me/entitlements 200 all-on; ZERO 5xx; mutable control tables 0/0 (43 events.control rows = immutable
  append-only audit history, T14 INSERT-only).
- Full T1–T18 table + gotchas in memory/build_log/wave-build-control-layer.md (CL-B4 section).
- GATE for C12: before flipping CONTROL_ENABLED=true, ALSO set FIREWALL_ENABLED=true (admin-plane step-up).

### Decisions
- entitlements.py = PG-native projection module (like crm/core.py + wallet.py), NOT in store.py JSON
  mirror seam. Reads catalog from var/control/*.json (the seed/source of truth) so it works even before
  PG cutover; tenant rows resolve from PG when available, fail-closed/all-default when not.
- Catalog uses the explore §B feature_keys (mod.command, command.dashboard, ...) — the richer ~120-key
  set, superset of datamodel §0. is_core floor: core.auth/core.settings/core.me_entitlements/core.health/
  core.wallet_pay.
