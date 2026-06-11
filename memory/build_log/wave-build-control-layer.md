# wave-build-control-layer.md — Foundation Control Layer build log (append-only)

Box: `famit@168.144.153.145:/opt/famit-agent/` (SOURCE OF TRUTH). Service venv `/opt/capsy-agent/.venv`
(NOT `/opt/famit-agent/.venv` — the latter lacks sqlalchemy). Service: `uvicorn caller:app :8209`,
WorkingDirectory `/opt/famit-agent`. Restart: `sudo systemctl restart famit-caller famit-agent`.
Resting discipline: ships behind `CONTROL_ENABLED` (currently OFF/unset); additive-only.

---

## UNIT CL-B1 — DATA MODEL + ENGINE + SEED  (= plan units C0 + C1)  ✅ DONE 2026-06-10

### What shipped (all NEW files; caller.py UNTOUCHED — routes are C2)
- `db/ddl_control.sql` — 7 additive tables, idempotent (`CREATE TABLE IF NOT EXISTS`), applied lazily by
  `entitlements.ensure_schema()` as the app role (admin GUC). Mirrors `crm/schema.sql` exactly.
  - GLOBAL (no RLS — shared catalog): `feature_registry`, `plans`, `plan_entitlements`, `plan_limits`,
    `entitlement_audit` (append-only read-mirror; the immutable PG `events` leg is the source of truth).
  - TENANT-SCOPED + FORCE-RLS (P1 shape, explicit per-table policy, ZERO percent-format markers):
    `tenant_entitlements` (per-vendor HIDE|LOCK|ON override), `tenant_status` (status/plan/trial +
    `ent_version` for real-time invalidation). Policy: `app.is_admin='1' OR tenant_id=app.tenant_id`.
- `var/control/registry.json` — 91-key feature catalog seeded 1:1 from `design/control-explore.md §B`
  (the source of truth that works pre-PG). default_mode=`on` for EVERY key → resting byte-identical (T17).
  6 `is_core` floor keys: core.auth, core.settings, core.me_entitlements, core.health, core.wallet_pay,
  money.billing_overview.
- `var/control/plans.json` — 4 plans: trial / **plan_a "Growth" (is_default)** / plan_b "Scale" /
  enterprise. Empty `entitlements` (full access by default = resting safe); `limits` carry the cap
  defaults from `caller.py:592-598` (vendor 3/500/5000 on plan_a; admin 20/100000/1000000 on enterprise).
- `entitlements.py` — the engine, mirrors `crm/core.py`: lazy `ensure_schema()`, import-safe `available()`
  degrade (PG down → all reads empty → all-default `on` → live site untouched), `db.engine.session` GUC.
  - `resolve_modes(tenant)` = datamodel §2 two-pass algorithm: PASS A status-gate ▸ override ▸ plan ▸
    global default ▸ garbage→hidden ▸ core-floor; PASS B parent-rolldown (strictest ancestor wins,
    hidden>locked>on, is_core exempt). Cached by `(tenant, ent_version)`.
  - `mode_for` (unknown key → hidden), `assert_access` (hidden→404, locked→402, on→pass — raises
    fastapi.HTTPException, ValueError fallback for smoke), `effective_limits`, `entitlements_payload`
    (the `/me/entitlements` body shape), `feature_key_for_path` (longest-prefix-wins + explicit shared
    map for `/leads/hot`,`/stats`,`/status`→command.dashboard), `bump_version`/`invalidate` (C4 hooks).
  - OpenFeature-style facade: `EntitlementProvider` + `set_provider`/`get_provider`/`evaluate` — call-sites
    use `evaluate()` so the backing store is swappable (flagd/Flagsmith) later without editing caller.py.

### GATES — ALL PASS
- LOCAL pure-logic smoke `_smoke_entitlements.py` (no PG): **43/43 PASS** — resting all-on (T17),
  global default, plan layer, override-beats-plan, parent rolldown (hide module → subtree hidden; lock
  module → subtree locked; child-on-under-hidden-parent → hidden), is_core floor (hidden→on, lock allowed),
  status gate (suspended/disabled/expired hide non-core, keep core+wallet_pay+billing), unknown→hidden,
  garbage→hidden, assert_access 200/404/402, path→key longest-prefix + shared map, effective_limits,
  facade parity, payload shape.
- PG-side smoke on the box (capsy venv): **ALL PASS** — `ensure_schema` applies 7 tables; FORCE-RLS
  confirmed on tenant_entitlements + tenant_status (`relforcerowsecurity=true`), OFF on global catalog
  tables; both isolation policies present; resolution vs REAL PG rows (override→locked/hidden,
  suspended→hidden, unknown tenant→on); **T8 RLS isolation floor PROVEN** — tenant-GUC (non-admin) session
  sees ONLY its own rows, 0 cross-tenant in tenant_entitlements/tenant_status; `bump_version` 1→2; smoke
  rows cleaned afterward (box pristine).
- REGRESSION: `caller.py` untouched (0 entitlements refs), imports clean; services restarted → both
  `active`; core endpoints `/me`/`/campaigns`/`/leads` → 200, `/run/preview` → 405 (POST-only, correct);
  **ZERO 5xx**. CONTROL_ENABLED stays OFF.

### Gotcha logged for the next unit
- psycopg2 `exec_driver_sql(ddl)` treats a literal `%` in the SQL as a parameter marker →
  `TypeError: immutabledict is not a sequence` and the schema silently fails (0 tables). My DDL's ONLY
  `%` was inside a COMMENT (ironically the "ZERO %" invariant note). FIX = keep ddl_control.sql 100%
  percent-free. SECURITY INVARIANT #4 ("zero-% DDL") is therefore also a *functional* requirement, not
  just a style rule. CRM's schema.sql has zero `%` and applies fine — match that.
- Catalog truth lives in `var/control/*.json` (canonical), NOT in the PG `feature_registry` table yet
  (PG rows = 0 by design in CL-B1). A later sync unit (or /admin/flags writes) populates the PG catalog;
  the engine reads the JSON seed so it works identically pre- and post-PG-cutover.

### Files on box
NEW: `entitlements.py`, `db/ddl_control.sql`, `var/control/registry.json`, `var/control/plans.json`,
`_smoke_entitlements.py` (kept for re-verification). No backups needed (no existing file overwritten).

---

## UNIT CL-B2 — require_super_admin + FAIL-CLOSED ENFORCEMENT MIDDLEWARE  (= plan C2-gate + C3)  ✅ DONE 2026-06-10

### What shipped (caller.py — SERIALIZED, one agent; backup `caller.py.CLbak.20260610-180847`)
- **`_auth_method(request) -> jwt|legacy_pw|hmac|none`** — re-classifies HOW the caller authed using the
  SAME precedence as `resolve_tenant` (JWT via `_auth_mod.resolve_token` ▸ `cred==PW` legacy ▸ `_verify_token`
  hmac). NON-MUTATING: `resolve_tenant`'s return contract is untouched (it's used in dozens of readers); this
  is a cheap separate re-derive so the admin gate can exclude the static password without a ripple edit.
- **`_is_super_admin(t,request)` / `require_super_admin(request)`** — the ONE centralized `/admin/*` gate.
  Phase-1 predicate = `is_admin AND _auth_method != 'legacy_pw'` → **THE #1 FINDING closed**: the legacy
  static password (`CALLER_PASS` / "FamitCall2026"), a permanent un-revocable admin bearer, is rejected from
  the admin plane even though it still authenticates vendor-grade routes (residual-risk #1, flagged).
  `require_super_admin` returns the admin tenant dict on success, else a `JSONResponse` (**403** non-admin —
  admin-plane existence isn't secret, control-security §1.4; **401** unauth). Usage:
  `t=require_super_admin(request); if isinstance(t,JSONResponse): return t`. Mirrors the `/tenants:3043` shape.
- **`_enforce_entitlement_mw` = `@app.middleware("http")`** — THE real boundary (control-security §1.3).
  path → `entitlements.feature_key_for_path` (longest-prefix + shared map) → `_ent_mod.evaluate(tid,key)` →
  **hidden=404** (no existence leak) / **locked=402** `{error:locked,feature,upgrade:true}` / on=pass. It
  **RETURNS** a JSONResponse for a block, **never raises** — the researched Starlette gotcha is that raising
  HTTPException inside a custom middleware runs OUTSIDE ExceptionMiddleware and leaks a 500; the existing
  `_rate_limit_mw` already follows return-don't-raise, matched here. (We use middleware not per-route
  `Depends` because the monolith has ~hundreds of un-decorated routes — a single choke-point can't be
  forgotten on one route, the more fail-closed shape for this codebase.) Bypass/pass rules: CORE keys
  (login/me/settings/health/wallet-pay) ALWAYS pass (anti-lockout); `/admin/*` + infra/docs (`/ /health
  /metrics /favicon.ico /docs /openapi.json /redoc`) exempt (role-gated, not entitlement-gated → never
  404/402 here); unmapped legacy path passes (CI drift-guard closes later); admin tenants not gated;
  tenant=None passes through (route owns its 401 — don't mask auth as not-found). FAIL-CLOSED: an unexpected
  error AFTER a governed key resolved → deny 404. **GATED behind `CONTROL_ENABLED` (default OFF)** → at the
  top of the mw the function returns before any work → resting byte-identical (T17).
- `import entitlements as _ent_mod` (import-safe) + `CONTROL_READY = _ent_mod.init()` at startup (loads the
  seed catalog/plans + best-effort applies the schema; NEVER raises). `CONTROL_ENABLED` flag added by
  `LEGACY_TOKEN_ENABLED`.

### GATES — ALL PASS (`_smoke_clb2.py`, capsy venv, real vendor `21d0a13603da`, control-rows-only + cleanup)
- **CONTROL_ENABLED=1 (throwaway):** require_super_admin — legacy-pw→**403**, vendor→**403**, no-creds→**401**,
  JWT-admin→pass (returns tenant). Middleware via TestClient — `GET /calls` (override hidden)→**404**,
  `GET /campaigns` (override locked)→**402** with `upgrade:true`, `GET /me` (core)→not 404/402 (route owns it),
  `GET /health` (exempt)→200. Engine resolution + `feature_key_for_path` (incl. `/leads/hot`→`command.dashboard`
  shared map, `/me`→`core.auth`, unknown→None) all PASS. **25/25.**
- **CONTROL_ENABLED off (default):** middleware is a pure no-op — `/health`→200, `/calls`→not blocked. ALL PASS.
- **LIVE regression (CONTROL_ENABLED absent in .env → OFF):** restarted famit-caller+famit-agent (both active);
  `/health /me /campaigns /leads /calls /tenants /billing/overview`→**200**, `POST /run/preview`→**200**,
  **ZERO 5xx** in journal. `CONTROL_READY=True, CONTROL_ENABLED=False`, 91 registry keys. Box pristine
  (0 control rows). Live caller.py == staged (md5 f36a666...).

### Decisions / gotchas
- Middleware (return-don't-raise) chosen over `Depends(enforce_entitlement)` despite the plan's C3 wording:
  the monolith's routes are un-decorated `@app.get` handlers, not an `/api` `APIRouter` with shared
  `dependencies=[...]`; a single middleware is impossible to forget on a new route (fail-closed by
  construction) and avoids retrofitting hundreds of signatures. The 500-leak risk is sidestepped by
  RETURNING the response (never raising), exactly as the live rate-limiter does.
- `_me/entitlements` route NOT added in CL-B2 (it's C2/C4) → currently 404. Its registry key
  `core.me_entitlements` is `is_core` so the moment C2 adds the handler it auto-bypasses enforcement.
- `_is_super_admin` returns **403** (not 404) for a vendor — deliberate split: admin-plane EXISTENCE is not
  a secret; only hidden FEATURES return 404 (so vendors can't enumerate withheld features). control-security §1.4.

### Files on box (CL-B2)
MODIFIED: `caller.py` (backup `caller.py.CLbak.20260610-180847`). NEW: `_smoke_clb2.py` (re-runnable gate).
ROLLBACK: `cp caller.py.CLbak.20260610-180847 caller.py && sudo systemctl restart famit-caller famit-agent`.

### NEXT (per CONTROL_LAYER_EXECUTION_PLAN §5) — all SERIALIZE on caller.py, one agent at a time
- **C2:** the full `/admin/*` route surface + `/me/entitlements` handler (use `require_super_admin` as the
  router gate; token-derived target `{id}`; audit each write to the PG `events` leg channel=control with
  old/new; wallet/impersonate behind firewall step-up). T1/T2/T3/T14 gate it.
- **C4:** `ent_version` bump on every control write (→ in-proc cache invalidation, already wired via
  `entitlements.bump_version`) + `/me/entitlements` ETag/If-None-Match (304).
- **C5:** suspend/run-gate (`auth.revoke_all` on suspend + status floor in the run loop).

---

## UNIT CL-B3 — /admin API + /me/entitlements + ACT-AS + SUSPENSION  (= plan C2 + C4 + C11 + login-block)  ✅ DONE 2026-06-10

SERIALIZED on caller.py (one agent). Backups on box: `caller.py|auth.py|entitlements.py.CLbak.20260610-232358`.
Diff vs backups: caller.py = 0 lines removed (purely additive); auth.py = 1 docstring reword; entitlements.py
= 0 removed. Resting discipline intact (`CONTROL_ENABLED` unset → byte-identical).

### What shipped
- **`entitlements.py` — engine WRITE helpers** (admin-GUC PG writes + `bump_version` + `entitlement_audit`
  mirror; never raise → `{ok,before,after}`): `set_override`/`clear_override` (per-vendor HIDE/LOCK/ON),
  `set_status` (active/trial/suspended/disabled/expired; preserves plan_id), `set_plan`, `set_global_flag`
  (in-proc catalog + PG `feature_registry.default_mode`, refuses to hide a core key, drops ALL caches),
  `resolved_with_provenance` (per-key effective mode + provenance global/plan/override/status — the
  Permissions-tab view), `vendor_detail`, `registry_tree`, `plans_detail`, `_exec_admin`, `_mirror_audit`.
- **`auth.py` — act-as token** (`make_act_as`/`act_as_claims`, `ACT_AS_TTL_SECONDS=600`): dedicated access
  JWT `sub=vendor` (rides proven RLS), `act_as`, `real_admin`, `scope=read_only|read_write`, `amr=act_as`,
  `is_admin=False` (can't climb). `resolve_token` resolves it to the vendor by design.
- **`caller.py` — the /admin/* block** (all `require_super_admin`-gated, target = path `{id}` never body,
  every write audited to PG `events` channel=control via `_control_audit` with old/new + mirror):
  `GET /admin/features`, `GET/PUT /admin/flags[/{key}]`, `GET/POST /admin/plans` + `PUT /admin/plans/{id}`
  (JSON ents+limits), `GET /admin/vendors`, `GET /admin/vendors/{id}` (resolved map+provenance+usage+health+
  wallet), `PUT/DELETE /admin/vendors/{id}/entitlements/{key}`, `PUT .../plan`, `PUT .../status`
  (suspend/disable → `auth.revoke_all` instant token kill + status floor; disabled needs step-up),
  `POST .../credits` (step-up, rides F4 wallet), `POST .../impersonate` (step-up, can't target an admin,
  read-only default, `X-Act-As` resp header), `POST /admin/act-as/exit` (audited).
- **`GET /me/entitlements`** (vendor-facing, core key → bypasses enforcement): `{modes,status,plan,version}`
  + ETag = `W/"ent-<tid>-<ver>"`; `If-None-Match` → 304 (C4 poll). Token-derived only (no `?tenant_id`).
- **Act-as read-only WRITE BLOCK** (`_act_as_readonly_block`): ALWAYS-ON middleware step (independent of
  `CONTROL_ENABLED` — impersonation is a live capability) — a `read_only` act-as token may only GET/HEAD/
  OPTIONS; any mutation → 403 (except `/admin/act-as/exit`, `/firewall/verify-pin`).
- **Suspension login block** (`_login_blocked_by_status`, gated by CONTROL_ENABLED): suspended/disabled
  vendor → `/login` + `/auth/login` return 403 "account suspended"; admins never blocked.

### GATE — `_smoke_clb3.py` (capsy venv, CONTROL_ENABLED=1, real vendor 21d0a13603da, control-rows-only, cleaned)
ALL PASS (~38 checks): 13 routes registered; **T1** vendor→403 on all 12 /admin/* (GET+mutating);
**T2** legacy_pw→403, no-creds→401; /me/entitlements 200+ETag, If-None-Match→304, **T3** ignores
?tenant_id; admin writes (JWT admin) — override hidden→reflected in vendor /me/entitlements + ent_version
bumped, clear→reverts, **T15** suspend hides non-core + keeps core on + login-block True + restore,
set_plan plan_b, vendor detail w/ provenance, /admin/features non-empty; **T11** act-as→/admin/*→403,
**T10** read-only act-as POST→403 / GET not blocked, **T12** impersonate-an-admin→403. **T14** verified
separately: control writes land on the IMMUTABLE PG `events` leg (channel=control) with non-null old/new,
actor, target, feature, real_admin, auth_method=jwt (note: `events.id` is a hash, NOT monotonic — order by
`at`, not id). Box left pristine: 0 tenant_entitlements / 0 tenant_status / 0 entitlement_audit rows.

### LIVE
`CONTROL_ENABLED` absent in .env (OFF). Restarted famit-caller+famit-agent (both active). Regression on
:8209 via X-Auth: core /health /me /campaigns /leads /calls /tenants /billing/overview /usage → 200,
POST /run/preview → 200; **T2 LIVE** legacy admin → 403 on /admin/{vendors,features,flags,plans};
/me/entitlements → 200 (all-on resting map). Journal since restart: 16×200 + 4×403, ZERO 5xx / tracebacks.
16 admin routes registered, CONTROL_READY=True, CONTROL_ENABLED=False.

### Notes / deferred
- C5 run-loop suspend gate (no NEW dials at the dial loop, in-flight finish, per-lead status re-read) is the
  ONE remaining backend piece — the API-layer instant kill (revoke_all → next call 401) + status floor +
  login block already ship here; the run-loop gate is a small follow-up unit.
- C10 (AI Copilot entitlement gate) + the frontend (C6–C9, C11-FE banner) are separate units, gated on this.
- `events.id` hash-ordering gotcha recorded above (don't `ORDER BY id` to get "latest" on the events leg).

---

## UNIT CL-B4 — T1–T18 ISOLATION/IMPERSONATION PROBE SUITE + DORMANT VERIFY  ✅ DONE 2026-06-10

Dedicated consolidated verification pass over the LIVE control-layer backend (CL-B1/B2/B3). One probe
script `_probe_t1_t18.py` run IN-PROCESS against `caller.app` (fastapi TestClient + direct engine/firewall
predicate calls + direct PG `events`-leg SELECTs). `CONTROL_ENABLED` was forced ON **inside the probe
process only** (`caller.CONTROL_ENABLED=True`) for the enforcement probes (T4–T7) and back OFF for the
resting proof (T17); the live `.env` was NEVER edited and the systemd service was NEVER restarted (the
running uvicorn kept its OFF env throughout). Real non-admin vendor `21d0a13603da` (+ second vendor
`ae1ba3017296` for T16); only CONTROL rows touched + deleted; box left pristine.

### T1–T18 PASS/FAIL TABLE (all PASS; T18 N/A)
| # | Probe | Result | Evidence |
|---|---|---|---|
| T1 | Vendor → `/admin/*` denied | **PASS** | vendor hmac token → 403 on ALL 12 `/admin/*` routes (GET + mutating). |
| T2 | Legacy password excluded from admin plane | **PASS** | `FamitCall2026` → 403 on `/admin/vendors` (auth_method=legacy_pw rejected); no-creds → 401. **#1 finding closed.** |
| T3 | Forge-tenant-B-as-A | **PASS** | `/me/entitlements?tenant_id=B` ETag = `ent-A-…` (token-derived, query ignored); A sees only A's override; forged-body write scoped to token tenant. |
| T4 | Hidden → 404 (raw token) | **PASS** | `GET /calls` (override hidden) → 404 via saved hmac token, no frontend. |
| T5 | Locked → 402 | **PASS** | `GET /campaigns` (override locked) → 402 `{error:locked,feature:grow.campaigns,upgrade:true}`. |
| T6 | Core floor un-hideable | **PASS** | `/me` not 404/402, `/health` 200; engine refuses to hide `core.settings`. |
| T7 | Fail-closed on unknown | **PASS** | unregistered key → `mode_for`='hidden'; `assert_access` raises 404. Never 200. |
| T8 | RLS floor under the app | **PASS** | FORCE-RLS=true on tenant_entitlements + tenant_status; a different-tenant non-admin GUC sees 0 of A's rows; admin GUC sees all. |
| T9 | Act-as enter needs step-up + identity-bound | **PASS** | firewall armed (FIREWALL_ENABLED + admin PIN): no `X-Step-Up` → StepUpDenied; step-up token bound to a DIFFERENT sub → "step-up identity mismatch" (F3 anti-replay). |
| T10 | Act-as read-only blocks writes | **PASS** | read_only act-as token (sub=vendor, real_admin=admin, is_admin=False): POST → 403; GET /me not act-as-blocked. |
| T11 | Act-as can't climb to admin | **PASS** | act-as token → `/admin/vendors` → 403. |
| T12 | Act-as can't target an admin | **PASS** | `POST /admin/vendors/<admin>/impersonate` → 403. |
| T13 | Act-as audited both ends (PG leg) | **PASS** | enter→200 (`X-Act-As: vendor` hdr) + exit→200; TWO new `events` rows (control.impersonate.start/stop) on the IMMUTABLE PG leg with actor=admin, target=vendor, real_admin=admin. |
| T14 | Permission change audited before/after, INSERT-only | **PASS** | override write → PG `events` row (channel=control) with non-null old/new (new='locked'); events owner=famit_app, no app-code DELETE path (read-only `/audit`). |
| T15 | Suspension kills tokens + status floor + data preserved | **PASS** | suspend → non-core hidden, core stays on, `_login_blocked_by_status`=True (revoke_all kills tokens), admin still reads vendor rows; restore → active + features back on. Data never deleted. |
| T16 | Entitlement cache not cross-tenant | **PASS** | flip vendor B's flag → vendor A's version + resolved modes UNCHANGED (no shared-cache bleed). |
| T17 | Resting-state byte-identical | **PASS** | with `CONTROL_ENABLED` OFF + clean box, `/me`+`/campaigns`+`/leads` md5 identical before vs after the whole probe run. |
| T18 | AI Copilot honors entitlements | **N/A** | C10 (Copilot entitlement gate) NOT built/deployed yet — no copilot route in caller.py. `/me/entitlements` foundation exists; gate is a deferred unit. Out of scope for the CL-B4 backend probe. |

### DORMANT VERIFY (live service, after the probe run)
- **caller.py md5 `dd872d999be79813441c2c7eb59b1ff2` byte-stable** (auth.py `a4397f78…`, entitlements.py
  `9e483325…`) — the probe never wrote a byte to the live source.
- `.env` has **NO `CONTROL_ENABLED` line (OFF/default)**; both `famit-caller` + `famit-agent` **active**.
- LIVE HTTP via `X-Auth: FamitCall2026`: `/health /me /campaigns /leads /calls /tenants /billing/overview
  /usage` → **200**, `POST /run/preview` → **200**, `/me/entitlements` → **200** (resting all-on map).
  Note `/calls` + `/campaigns` are 200 LIVE even though the probe made them 404/402 in-process — proving
  the live uvicorn is NOT enforcing (resting), and the in-process flag flip was fully isolated.
- **ZERO 5xx / tracebacks** in the journal since the run.
- **Mutable control tables PRISTINE**: tenant_entitlements=0, tenant_status=0. The 43 `events`(channel=
  control) rows are intentional append-only audit history (T14 INSERT-only — cannot/should not be deleted).

### Gotchas logged
- **T9 enforcement is conditional**: `firewall.require_step_up` is a pass-through unless `FIREWALL_ENABLED`
  AND the acting admin has a PIN enrolled (security spec §2.2 already mandates FIREWALL_ENABLED ON for the
  admin plane). The probe arms the firewall + a throwaway admin PIN to exercise the REAL gate, then disarms
  + removes the PIN. So: **before flipping CONTROL_ENABLED, also set `FIREWALL_ENABLED=true` so act-as enter
  actually requires step-up in production** — otherwise impersonate would mint a token without a PIN gate.
- **PG events mirror needs a running loop**: `store.mirror_event` schedules the PG insert via
  `loop.run_in_executor`, so audit rows only reach the immutable PG leg when written from within the app
  loop (TestClient/route handler) — a bare sync script writes JSONL only. T13/T14 trigger the audit via the
  HTTP route (loop present) then SELECT from PG; a ~1.2s drain lets the executor land the insert.
- **In-proc resolution cache** is keyed by `(tenant, ent_version)` and only auto-invalidates on the version
  bump that a control WRITE performs; a test harness asserting `mode_for` synchronously right after a status
  flip should `ent.invalidate(tid)` (prod self-heals via the `/me/entitlements` ETag poll). Also: a STANDING
  override masks the status effect — test the suspension status-floor on a key with NO active override.

### GATE — ✅ T1–T17 ALL PASS, T18 N/A (deferred unit), resting byte-identical, zero 5xx, box pristine.
CONTROL_ENABLED left OFF. The suite gates `CONTROL_ENABLED=true` at C12 (final deploy gate). Probe script
kept at `caps/droplet_work/control/_probe_t1_t18.py` (re-runnable); removed from the box after the run.

---

## CL-F0 — ENTITLEMENT CLIENT + SHELL (frontend shared plumbing) — DONE 2026-06-10

The shared entitlement plumbing (panel side), built BEFORE any admin page. `npm run build` EXIT 0, no
errors/warnings, 41/41 pages generated. NOT deployed (per unit scope). All COSMETIC — backend 404/402
choke-point remains the only real boundary (spec §9.1).

Files:
- `famit-panel/lib/api.ts` — added `getEntitlements(etag)` + `EntitlementMode`/`EntitlementsPayload`/
  `EntitlementsFetch` types. Conditional GET `/me/entitlements` with `If-None-Match`; 304 -> notModified
  no-op; 404 -> permissive all-on map (resting-state parity for the older/CONTROL-off box); 401 -> existing
  handle401 redirect.
- `famit-panel/lib/entitlements.ts` (NEW) — ONE module-level store + pub/sub (single source of truth, no N
  pollers). `EntitlementProvider` (mount-once: initial revalidate + 25s ETag short-poll [`NEXT_PUBLIC_ENT_POLL_MS`,
  floor 5s] + on-`visibilitychange` refresh). `useEntitlement(key) -> "ON"|"LOCK"|"HIDE"` (primary API, via
  `useSyncExternalStore` w/ SSR snapshot). `useEntitlements()` (full payload + status/version/plan/loading).
  `revalidateEntitlements()` (de-duped via inFlight) + `onAccessSignal(status)` (self-heal on 401/402/404 from
  any page fetch). localStorage cache `famit_ent`/`famit_ent_etag` (advisory; instant first paint; fail-soft).
  Kept `.ts` (not `.tsx`) via `createElement(Fragment,...)` as the design names it.
- `famit-panel/components/LockOverlay/index.tsx` (NEW) — page LOCK upsell: children rendered blurred +
  `inert` (React 19 native) behind a centered `.card` panel (amber lock medallion, "Locked" Badge, Upgrade
  isBlack -> `/billing/plan`, Contact isStroke -> `/support`). Built from Card/Modal styles + Button + Badge +
  Icon("lock"), not from scratch.
- `famit-panel/components/EntitlementGuard/index.tsx` (NEW) — per-page route guard (sibling to AuthGuard).
  HIDE -> `router.replace("/")` (only after `loaded`, no first-paint flicker-bounce) + render null; LOCK ->
  wrap in LockOverlay; ON/loading -> render children optimistically. Revalidates on route change. Usage:
  `<EntitlementGuard featureKey="engage.calls" featureLabel="Call Logs">…page…</EntitlementGuard>` (added per
  page in LATER waves, NOT this unit).
- `famit-panel/components/Sidebar/index.tsx` — `resolveNav` now takes an `entOf` resolver: a group whose own
  `feature_key` -> HIDE is dropped; a child -> HIDE is dropped like an out-of-role child; a child -> LOCK
  survives flagged `locked:true`. Empty-group rule unchanged. Sidebar reads `useEntitlements().payload` and
  passes `modeOfIn(payload, key)`. Map defaults permissive until loaded -> nav never flickers items away.
- `famit-panel/components/Sidebar/Dropdown/index.tsx` — `locked` child reuses the `comingSoon` dimmed non-link
  branch with a "Locked" pill (`.nav-locked`) instead of "Soon" + a title tooltip. Cosmetic.
- `famit-panel/app/globals.css` — added `.nav-locked` utility (amber, mirrors `.nav-soon` shape).
- `famit-panel/app/providers.tsx` — mounts `<EntitlementProvider>` once inside AuthGuard for all authed
  routes (skipped on `/login` to avoid an unauth request loop).

NOTE for later waves: nav children get gated by adding a `feature_key` to the node in `contstants/navigation.tsx`
(none added this unit — purely additive plumbing, resting behaviour byte-identical with the map empty/all-on).
Did NOT touch any `app/<feature>` page (per scope). EntitlementGuard/LockOverlay are opt-in per page later.

---

## UNIT CL-ACT — INTEGRATE + ACTIVATE + DEPLOY + LIVE VERIFY (= plan C12 final gate) ✅ DONE 2026-06-11

The control layer is now **LIVE and ENFORCING** in production. Frontend Super Admin UI deployed; backend
flag flipped ON; full live E2E + T1-T18 re-run against the running service over real HTTP; all PASS.

### (1) FRONTEND DEPLOY (FORTRESS box root@143.110.247.249:/opt/famit-panel)
- Local `npm run build` EXIT 0 (Next 15.2.0; all 7 /super-admin/* routes compiled).
- Box backup: `/opt/famit-panel.CLbak.1781120589` (1.1G, full tree). Source synced via tarball+rsync
  (excluded node_modules/.next/.git/.env.local). `npm install --legacy-peer-deps` EXIT 0 + `npm run build`
  EXIT 0 ON THE BOX (node v20.20.2 — matches the `next start` runtime; built on-box to avoid arch mismatch).
  super-admin pages now present on box (were absent in the prior deploy).
- `systemctl restart famit-panel` -> active. Local 127.0.0.1:3001 root/login/super-admin = 200.
  Public panel.famit.in login/super-admin = 200, /api/health = 200.
- FE gating verified: `SuperAdminGuard` bounces a non-admin to "/" + renders null; nav group `roles:"admin"`
  (whole Super Admin section hidden in sidebar for non-admins). Cosmetic — backend 403 is the real boundary.

### (2) ACTIVATE (backend box famit@168.144.153.145:/opt/famit-agent/)
- `.env` backup `.env.CLbak.20260610-195647`. Set `CONTROL_ENABLED=1` + `FIREWALL_ENABLED=true`. Restarted
  famit-caller + famit-agent (both active). caller.py md5 `dd872d999be79813441c2c7eb59b1ff2` UNCHANGED (only
  .env edited — no code touched).
- FIREWALL_ENABLED=true is SAFE: `firewall.require_step_up` pass-throughs for any tenant with NO PIN enrolled
  (firewall.py:~194). Only the `admin` tenant has a PIN (pre-existing) so ONLY act-as step-up is gated; live
  vendor wallet/destructive routes are unaffected.
- Resting unharmed under the flag: vendor A all-core 200 + /me/entitlements all-on modes map; admin core 200;
  /run/preview 200.

### (3) LIVE E2E + (4) T1-T18 LIVE — `_probe_live_e2e.py` (on box, capsy venv, real HTTP to running :8209,
###     CONTROL_ENABLED=1 actually set in .env — NOT in-process TestClient like CL-B4). 18 PASS / 0 FAIL / T18 N/A.

| # | Probe | Result | Evidence (live HTTP vs running uvicorn) |
|---|---|---|---|
| T1 | vendor -> /admin/* | PASS | vendor hmac token -> 403 on ALL 12 /admin/* (GET + mutating, valid form bodies supplied so the gate is what rejects). |
| T2 | legacy pw excluded | PASS | `FamitCall2026` -> 403 on /admin/vendors; no-creds -> 401. #1 finding closed at the LIVE boundary (also verified through Cloudflare: panel.famit.in/api/admin/vendors legacy -> 403). |
| T3 | forge tenant-B-as-A | PASS | GET /me/entitlements?tenant_id=B as A -> ETag `ent-21d0a13603da-N` (token-derived, query ignored). |
| T4 | HIDE -> 404 | PASS | admin PUT entitlements/engage.calls=hidden -> vendor GET /calls -> **404** (raw token, no FE); /me(core)->200; /me/entitlements shows engage.calls=hidden. |
| T5 | LOCK -> 402 | PASS | admin set grow.campaigns=locked -> vendor GET /campaigns -> **402** `{error:locked,upgrade:true}`. |
| RESTORE | clear -> ON | PASS | DELETE both overrides -> /calls & /campaigns -> 200 (restored). |
| T6 | core floor | PASS | /me & /health -> 200; engine refuses to hide core.settings (mode stays 'on'). |
| T7 | fail-closed unknown | PASS | unknown key mode_for='hidden'; assert_access raises 404. Never 200. |
| T8 | RLS floor | PASS | FORCE-RLS=true; other-tenant non-admin GUC sees 0 of A's tenant_entitlements rows; admin GUC sees them. |
| T9 | act-as needs step-up + id-bound | PASS | no X-Step-Up -> 403; wrong-admin (different sub) step-up -> 403 identity-mismatch; correct destructive-scope step-up -> 200 enter. |
| T10 | act-as read-only | PASS | act-as token GET /me -> 200; POST /leads -> 403 (read-only block). |
| T11 | act-as can't climb | PASS | act-as token -> /admin/vendors -> 403. |
| T12 | act-as can't target admin | PASS | POST /admin/vendors/admin/impersonate (valid step-up) -> 403. |
| T13 | act-as audited both ends | PASS | impersonate start+stop events on the IMMUTABLE PG events leg (channel=control) for the vendor, actor=admin (>=2). |
| T14 | perm change audited before/after | PASS | override write -> PG events row action=control.override.set, old=None new=locked, actor=admin (INSERT-only). |
| T15 | suspension | PASS | suspend -> non-core /campaigns,/leads -> **404** (status floor) + login_blocked=True + JWT-refresh revoked; /me(core)->200 (anti-lockout, nothing actionable); admin still reads vendor rows (DATA PRESERVED); restore -> 200. |
| T16 | cache not cross-tenant | PASS | flip vendor B's flag -> vendor A's version + resolved modes UNCHANGED. |
| T17 | resting byte-identical | PASS | no overrides + active status -> /me,/campaigns,/leads all 200 == pre-control behavior. |
| T18 | AI Copilot gate | N/A | C10 not built/deployed (no copilot tool route). Deferred unit. |

### (5) RESTING PLATFORM UNHARMED (post-activation, post-probe)
- Both services active. Core+module endpoints (/health /me /campaigns /leads /calls /tenants /billing/overview
  /usage /me/entitlements) -> 200; POST /run/preview -> 200. **ZERO 5xx / tracebacks** in the journal.
- **VOICE UNTOUCHED**: agent.py has 0 entitlement/CONTROL refs (hot loop clean, latency moat intact),
  mtime 2026-06-09 (predates this work). caller.py md5 dd872d9 byte-stable. Control read only at the API
  choke-point + /run gate + per-lead status floor — never the per-turn voice loop.
- Box pristine: 0 residual tenant_entitlements / 0 non-active tenant_status (probe cleaned up). Probe script
  removed from box. The 50+ events(channel=control) rows are intentional append-only audit history (T14).

### KNOWN RESIDUAL (recorded; not a blocker; T15 still PASSES)
- The live panel `/login` issues a STATELESS hmac token (tenant_id.hmac, no jti) -> `auth.revoke_all` (which
  revokes JWT *refresh* tokens) cannot cryptographically kill a held hmac bearer. Suspension is enforced in
  SUBSTANCE by the STATUS FLOOR (every non-core route 404) + login-block + JWT-refresh-revoke; core.* stays
  200 by anti-lockout (exposes nothing actionable). Same residual class as the legacy-password #1 finding
  (stateless auth = not individually revocable). Hardening path: migrate panel to /auth/login (JWT) OR add a
  per-tenant token-epoch to the hmac sig. The vendor is fully neutralized today regardless.

### ROLLBACK (if ever needed)
- Backend: restore `.env.CLbak.20260610-195647` (or set CONTROL_ENABLED=0 + FIREWALL_ENABLED=false) + restart
  famit-caller famit-agent. Additive control tables are harmless when OFF.
- Frontend: restore `/opt/famit-panel.CLbak.1781120589` + `systemctl restart famit-panel`.

### FILES
- Local probe (re-runnable): `caps/droplet_work/control/_probe_live_e2e.py` (live-HTTP variant; removed from box).
- State ledger: `caps/CONTROL_ACTIVATION_STATE.md`.

## CONTROL LAYER STATUS: 🟢 LIVE + ENFORCING IN PRODUCTION (2026-06-11). Deferred: C10 AI Copilot gate (T18).
