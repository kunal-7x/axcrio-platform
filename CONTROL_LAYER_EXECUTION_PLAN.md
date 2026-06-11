# FOUNDATION CONTROL LAYER — EXECUTION PLAN (Tier-0 Super-Admin Control Center)

> **Chief-architect synthesis** of six design docs (`design/control-{explore,oss-research,realtime-enforcement,security,ui,datamodel}.md`)
> + the parent spec (`design/spec-control-layer.md`) + founder spec (`Z.MD`), reconciled into ONE
> buildable, secure, crash-safe build plan.
>
> **Status: DESIGN/PLAN ONLY.** No app code, no deploy, no git. This is the blueprint the build wave executes.
>
> **The one-line thesis:** the live platform is ~60% there (forced-RLS multi-tenancy, `is_admin`+`/tenants`,
> `resolve_tenant()` choke point, `/usage`+caps, wallet/firewall F4, immutable `events` audit, Sidebar
> `resolveNav` + `comingSoon` dimmed-pill). We add ONE home-grown **Entitlement Engine** + a thin admin UI on
> top. **The backend enforcement choke-point is the only real boundary and MUST ship + be isolation-proven
> BEFORE any frontend that depends on it.**

---

## 1. FINAL VERDICTS (the reconciled decisions — these are settled, do not relitigate mid-build)

| Decision | VERDICT | Why (reconciled across the six docs) |
|---|---|---|
| **Build vs adopt the engine** | **BUILD** a home-grown table-set + `entitlements.py` (~150 LOC) over Postgres+RLS as the single source of truth. | OSS doc: the load-bearing logic (tri-state HIDE/LOCK, plan→limits bundles, 5-rule fail-closed precedence, 404/402 gate, status floor, Copilot gate) is PRODUCT logic NO OSS tool ships. A flag platform (Unleash/Flagsmith/GrowthBook) models environments/segments, not tenants+plans+HIDE/LOCK, and adds a 4th service + 2nd admin UI for zero work removed. A PDP (Cerbos/OPA/Casbin/Oso) solves the right half but is heavier than a 30-line precedence over one tenant's rows. Droplet cap (3 used) + egress-lock + "own everything" posture decisively favor zero-new-service. |
| **Swap-safety insurance** | **REUSE** OpenFeature (Python + JS) as a thin evaluation **facade** wrapping our engine. | Cheap insurance: standardizes call-sites, makes the backend swappable later (to Flagsmith/flagd) without touching a single call-site. Not an engine — an SDK + custom-provider hook. |
| **Trigger-gated upgrade paths (adopt NOTHING now)** | Hold **Casbin** (rule→real RBAC/ABAC), **Cerbos** (policy-as-code / air-gapped reviewable YAML), **OPAL** (ms-push real-time), **Flagsmith** (ready-made flag UI). REJECT Unleash, GrowthBook, Permit.io, Stripe Entitlements for this layer. | Each is a named, condition-gated future swap, not a present dependency. Permit (SaaS control plane) + Stripe (couples entitlement to external billing) FAIL the egress-locked posture. |
| **Real-time mechanism** | **Versioned `/me/entitlements` + ETag/`If-None-Match` short-poll (~25 s) + on-focus + on-route-change + on-401/402/404 refresh.** Per-tenant integer `ent_version` bumped on every control write. | WebSocket rejected (sticky sessions/heartbeat/proxy overhead for a one-way signal). The poll is **cosmetic** — the API choke-point denies a revoked feature on the NEXT request, so enforcement lag = 0; only UI freshness needs the poll. Stateless polling survives Cloudflare + the egress-locked box with zero config. **SSE is the named Phase-2 drop-in** (`/me/entitlements/stream` reusing the same bump signal + same client `revalidate()`). |
| **Enforcement implementation** | **ONE FastAPI `Depends(enforce_entitlement)` choke-point** on the `/api` router — **NOT `BaseHTTPMiddleware`.** | Researched gotcha (realtime doc §2.1): raising `HTTPException` inside a Starlette custom middleware runs OUTSIDE `ExceptionMiddleware` → leaks a 500. A router-level `Depends` lives INSIDE the exception boundary, already has the authed tenant (`Depends(resolve_tenant)`), and composes with the existing `can()`/`need_auth`. |
| **Codes** | HIDDEN → **404** (indistinguishable from "doesn't exist", no existence leak). LOCKED → **402** `{error:"locked",feature,upgrade:true}`. Unknown/non-core/resolver-error/suspended → **fail-closed 404**. `/admin/*` to a vendor → **403** (admin existence isn't secret; a hidden FEATURE is). | Two leak surfaces, two codes, deliberate (security doc §). A bug or unregistered module = LESS access, never more. |
| **Admin authority** | Phase 1: `is_admin` + **non-legacy auth-method** (exclude the static password — see §2). Phase 2 hardening: Logto admin-org + `manage_tenants` scope. | Explore doc finding #9: **Logto is NOT wired into caller.py** today; super-admin authority is `is_admin`+JWT/hmac/PW. Build `/admin/*` on `is_admin` NOW; the Logto-org binding is a later unit, not a present dependency. |
| **Data store** | 5 additive tables, **JSON-first under `var/control/` → Postgres** through the `store.py` MODE router (json\|dual\|pg), the proven F2/F4 strangler. New tables ship **FORCE-RLS** in the explicit P1 per-table shape (zero `%`/`DO format('%I')` — the silent-no-tables DDL trap). | Datamodel doc. DDL is the target end-state; the engine reads through the MODE router so the cutover is a flag. |

### THE #1 SECURITY FINDING (carry it into every backend unit)
**The legacy static password `FamitCall2026` (`caller.py:427`, `cred==PW → admin`) is a permanent, un-revocable,
un-audited admin bearer token.** It MUST be **excluded from the entire `/admin/*` control plane** (auth_method
`legacy_pw` → 403, even though it still authenticates vendor-grade routes today). Probe **T2** gates this. The
legacy password is slated for platform-wide retirement after the control layer ships.

---

## 2. THE RESOLUTION ALGORITHM (the heart — deterministic, fail-closed, most-specific-wins)

```
resolve_modes(tenant_id) -> { feature_key: 'on'|'hidden'|'locked' }   # for EVERY key in the registry

PASS A — per key, most-specific-wins:
  1. STATUS GATE   status ∈ {suspended,disabled,expired}  ⇒  'on' if is_core else 'hidden'   (skip rest)
  2. PER-VENDOR OVERRIDE   tenant_entitlements[key]            (wins outright if present)
  3. PLAN ENTITLEMENT      plan_entitlements[plan_id][key]     (next)
  4. GLOBAL DEFAULT        feature_registry[key].default_mode  (baseline)
  5. value ∉ {on,hidden,locked}  ⇒  'hidden'                  (FAIL-CLOSED)
     CORE FLOOR: is_core && mode=='hidden'  ⇒  'on'           (anti-lockout; LOCK on core is allowed)

PASS B — parent rolldown (strictness  hidden > locked > on):
  effective[key] = strictest( effective[key], effective[ancestor] up the parent chain )
  (a hidden module hides its whole subtree; a locked module locks it). is_core exempt from a hidden rolldown.

mode_for(key) = resolve_modes()[key]  ELSE 'hidden'   # a key NOT in the registry is ungoverned ⇒ deny

assert_access:  hidden→404 (no info leak) · locked→402 {error:locked,upgrade:true} · on→pass
cache keyed by tenant_status.ent_version  →  any control write bumps version  →  recompute  →  real-time
```

**Precedence (high→low):** status gate ▸ per-vendor override ▸ plan ▸ global default ▸ parent rolldown
tightens ▸ unknown ⇒ **hidden**. `is_core` is a floor that survives all of it (login, `/me`, `/me/entitlements`,
health, settings, wallet-pay are un-hideable).

**Catalog size:** ~120 feature_keys (≈105 vendor-controllable across 9 modules / ~38 pages incl. 7 AI-Manager +
5 Billing sub-pages, ~50 feature/action/integration/limit keys, + 5 core un-hideable + 10 admin-only Super-Admin
pages). Each registry entry carries `feature_key` + `parent_key` (hierarchy) + `nav_href` (HIDE drops it) +
`api_prefixes` (backend 404/402), seeded 1:1 from `contstants/navigation.tsx` + `app/**/page.tsx` + the caller.py
route surface. **WATCH-OUT:** `api_prefixes` need longest-prefix (prefix-trie) + path-param normalization; a few
shared routes (`/leads/hot`, `/stats`) need an explicit map, not naive prefix matching.

---

## 3. DATA MODEL (5 additive tables; FORCE-RLS in the P1 shape; JSON-first → PG via the MODE router)

```
feature_registry(key PK, kind, parent_key, label, nav_href, api_prefixes TEXT[],
                 default_mode DEFAULT 'on', min_role, is_core DEFAULT false)   -- GLOBAL catalog, no RLS
plans(plan_id PK, name, description, is_default, created_at)                    -- GLOBAL
plan_entitlements(plan_id FK, feature_key FK, mode)                             -- GLOBAL
plan_limits(plan_id FK, limit_key, value BIGINT)                               -- GLOBAL
tenant_entitlements(tenant_id FK, feature_key FK, mode, set_by, set_at, reason, -- PER-VENDOR, FORCE-RLS
                    PRIMARY KEY(tenant_id, feature_key))
tenant_status(tenant_id PK, status DEFAULT 'active', plan_id, trial_ends_at,    -- sidecar, FORCE-RLS
              suspended_reason, ent_version INT DEFAULT 1)
```
- **RLS** copies the proven crm/schema.sql shape: `app.is_admin='1' OR tenant_id=current_setting('app.current_tenant')`.
  Explicit per-table policy, ZERO `%`/`DO format('%I')`.
- **Audit** primary sink = the existing immutable `events` leg via `audit.record(channel='control')` (actor/target/
  action/old_value/new_value/reason/ip/ts, INSERT-only). An `entitlement_audit` mirror is a fast queryable read-copy
  ONLY — `events` is the source of truth. No new audit infra.
- **Credits** stay in F4 `wallet_accounts` (no new balance); control adds admin top-up/freeze behind firewall step-up.
- **Migration** sets every tenant `status='active'`, the default plan, empty overrides → **resting state byte-identical
  to today** (T17).

---

## 4. PARALLELIZATION & SERIALIZATION MAP (the critical orchestration constraint)

```
                    ┌─────────────────────────── SERIALIZE on caller.py (ONE agent at a time) ───────────────────────────┐
  BACKEND SPINE →   C0 ──► C1 ──► C2 ──► C3 ──► C4 ──► C5 ──► C10 ──► C11(be)
                    engine status  admin  ENFORCE rt    suspend copilot impersonate
                    +seed  +plans  routes CHOKE  ver    sweep   gate    step-up
                    (opus) (sonnet)(opus) (opus) (sonnet)(sonnet)(sonnet)(opus)
                                            │
                    ════════ HARD GATE: C3 SHIPPED + T1–T8 PASS ════════
                                            │  (no FE that depends on enforcement may start before this)
                                            ▼
  FRONTEND      →   C6 (Sidebar+lib, SHARED file, lands FIRST + ALONE) ──┐
  (after the                                                            ├─► C7 ║ C8 ║ C9  (PARALLEL — different files)
   gate)                                                                │     vendors  perms   flags/plans/usage/audit
                                                                        └─► C11(fe banner/guard)
                                            │
                    ════════ FINAL GATE: C12 (registry-drift CI + isolation re-probe T1–T18 + FORTRESS deploy) ════════
```

**RULES (founder's one-agent-per-file mandate, made concrete):**
- **`caller.py` + box modules (`entitlements.py`, `auth.py`, run-loop) SERIALIZE.** C0–C5, C10, C11-backend all touch
  the live box → run **sequentially, one agent at a time**, each committing + pushing before the next. **NEVER two
  agents on `caller.py`.** This is the longest critical path and the security spine.
- **The enforcement choke-point (C3) + the `/admin/*` routes (C2) are the only real boundary** — they ship and are
  **isolation-proven (T1–T8) BEFORE any frontend that depends on them.** Frontend HIDE/LOCK is cosmetic theatre; a
  saved token / curl / devtools must hit the SAME server 404/402. This gate is non-negotiable.
- **Frontend C6 lands FIRST and ALONE** — it edits the SHARED `components/Sidebar/index.tsx` (resolveNav) +
  `lib/entitlements.ts`. Do it in main or a single agent; do NOT parallelize anything that touches Sidebar/lib with it.
- **After C6, C7 / C8 / C9 parallelize** — they live in DIFFERENT route directories (`app/admin/vendors`, the
  Permissions tab + `components/EntitlementToggle`, and `app/admin/{flags,plans,usage,audit}`). One agent per
  directory; C9 may itself split into 2 sub-agents partitioned by page (never the same file).
- **C11 is split:** backend act-as (step-up token, read-only gate) serializes on the spine (opus); the FE banner +
  read-only guard rides the FE wave after C6.

---

## 5. UNIT-BY-UNIT BUILD PLAN (crash-safe; one verified commit per unit; gate per unit)

> Each unit: append a one-line "IN PROGRESS" to `caps/CONTROL_LAYER_STATE.md` → build → run the gate → commit+push →
> flip "DONE". Ships behind `CONTROL_ENABLED=false` (resting byte-identical) until C12's full smoke + T1–T18 pass.
> Backend rollback = restore `caller.py`/`.env` `*.controlbak.<ts>` + restart (drops routes; additive tables harmless).
> FE rollback = restore `/opt/famit-panel.bak.<ts>`. NEVER touch the voice `agent.py` hot loop — control is read at the
> API/run-gate layer only (latency moat).

| # | Unit | Owner file(s) | Model | Deliverable + GATE (must pass before commit) |
|---|---|---|---|---|
| **C0** | Feature registry + engine | `entitlements.py` (NEW), `var/control/*.json`, `store.py` (extend MODE router) | **opus** | `feature_registry` seeded 1:1 from nav+module map; `resolve_modes`/`mode_for`/`assert_access`/`effective_limits` with the §2 algorithm + OpenFeature facade. GATE: unit test — precedence (status>override>plan>global), parent-rolldown, unknown→hidden, is_core floor, longest-prefix path→key (incl. `/leads/hot`,`/stats` explicit map). |
| **C1** | Status + plans store | `entitlements.py`, `db/ddl_control.sql`, `var/tenants.json` (additive), `var/control/plans.json` | **sonnet** | Additive `status`/`plan_id`/`trial_ends_at`/`ent_version`; `plans`/`plan_entitlements`/`plan_limits`; seed Trial/A/B/Enterprise; migration → all tenants active+default+empty. GATE: **T17** `/campaigns /leads /me` byte-identical (resting-state proof). |
| **C2** | Admin API routes | `caller.py` (additive `/admin/*` + `/me/entitlements`), `auth.py` (auth_method tag) | **opus** | All §6-spec `/admin/*` + `/me/entitlements`; `require_super_admin` gate (`is_admin` + non-legacy); token-derived tenant; audited to `events` channel=control with old/new; wallet/impersonate behind firewall step-up. GATE: **T1** vendor→403 all; **T2** legacy-pw→403; **T3** forge-body-tenant on every new route PASS; **T14** audit row with before/after. |
| **C3** | Enforcement choke-point | `caller.py` (`Depends(enforce_entitlement)` on `/api` router), `entitlements.py` | **opus** | The §1 dependency choke-point (NOT BaseHTTPMiddleware): path→feature_key→assert_access; hidden→404, locked→402, core bypass, fail-closed deny. **THIS IS THE REAL SECURITY BOUNDARY.** GATE: **T4** hidden→404 via raw token; **T5** locked→402; **T6** core floor 200; **T7** unknown→404; behind `CONTROL_ENABLED`. ← **HARD GATE: no dependent FE starts until C3 ships + T1–T8 pass.** |
| **C4** | Real-time version + cache | `caller.py`, `entitlements.py` | **sonnet** | `ent_version` bump on every control write → in-proc cache invalidation; `/me/entitlements` returns `{modes,status,plan,version}` with ETag/`If-None-Match` (304 on hit, `Cache-Control: private, no-cache`). GATE: write flips flag → next conditional GET shows new version+mode (200) else 304; **T16** no cross-tenant cache bleed; API denies immediately. |
| **C5** | Suspend + trial sweep | `caller.py` (run-gate), `scheduler_loop` | **sonnet** | Run-loop gate honors `status` (suspended → no NEW dials, in-flight finish, re-read status per-lead); suspension revokes tokens (`auth.revoke_all` → next call 401); trial→expired sweep folded into the existing 60 s `scheduler_loop` (no new infra). GATE: **T15** suspend→`/run` blocked + next call 401 + in-flight record untouched + admin still reads rows; un-suspend restores. |
| **C6** | Vendor-side FE plumbing | `lib/entitlements.ts` (NEW), `components/Sidebar/index.tsx` (resolveNav), `components/Sidebar/Dropdown`, `components/LockOverlay` (NEW), `components/StatusPill` (NEW) | **sonnet** | `useEntitlements()` (ETag poll + on-focus + on-route-change + on-401/402/404, fail-close to core-only nav, `modeOf/isHidden/isLocked`); resolveNav drops `hidden` children (mirrors the `roles` filter) + renders `locked` via the EXISTING `comingSoon` dimmed-pill (swap "Soon"→"Locked"); `LockOverlay` (Card+blur+Modal styles, "Should I pay for this?"); per-page `EntitlementGuard` redirect. **SHARED FILE — lands FIRST + ALONE.** GATE: `npm run build` exit 0; hidden flag → nav item gone + URL redirects; locked → overlay; backend 404/402 still self-heals the UI. |
| **C7** | Admin Vendors list + Workspace | `app/admin/vendors/page.tsx`, `app/admin/vendors/[id]/page.tsx` | **sonnet** | Port Core_2 `Customers/CustomerList/{CustomerListPage,DetailsPage}` (Search+status Tabs+Table+StatusPill+NoFound; left `/Customer` identity+status rail + right `/Details` 5-Tabs: Overview·Usage·Permissions·Billing·Audit). Wire `/admin/vendors` + `/admin/vendors/{id}` + status actions. GATE: build exit 0; list renders real vendors; workspace tabs render. |
| **C8** | Permissions tab + EntitlementToggle | `components/EntitlementToggle` (NEW), `app/admin/vendors/[id]` Permissions tab, `app/admin/flags/page.tsx` | **sonnet** | `EntitlementToggle` = a Tabs-styled 3-segment [On green / Lock amber / Hide grey] (NOT a boolean Switch) + a `Badge` provenance pill (global/plan/override) + Reset; core rows render Lock/Hide disabled (self-lockout floor). Writes `PUT /admin/vendors/{id}/entitlements/{key}`. Global Feature Flags = port `SettingsPage/Menu` sticky section index. GATE: build exit 0; toggling persists + reflects in `/me/entitlements` version bump. |
| **C9** | Plans + Usage + Audit + Overview + Health (FE) | `app/admin/{plans,usage,audit,health,settings}/page.tsx`, `app/admin/page.tsx` | **sonnet** (split ≤2 sub-agents by page, never same file) | Plans → port `UpgradeToProPage/Pricing` + `Products/NewProductPage` editor; Usage → `Customers/OverviewPage`; Audit → `Notifications` feed (`/audit?channel=control`); Overview → `HomePage`+KPI tiles; Health/Settings/Support → `SettingsPage`+tiles. GATE: build exit 0; each page loads real data. |
| **C10** | AI Copilot entitlement gate | `caller.py` Copilot tool/prompt layer (actuates over `/api` loopback via `workforce/tools/transport.py`) | **sonnet** | Copilot loads `/me/entitlements` + refuses hidden/locked features in the prompt/tool layer with the upsell line ("Your account does not have access to Billing Meter"). Already gated for free at the `/api` choke-point; this closes the side-channel. GATE: **T18** billing locked → "show billing" → polite refusal, NO data. |
| **C11** | Impersonation / act-as | `caller.py` (`/admin/vendors/{id}/impersonate`, act-as token), `firewall.py` (reuse step-up), FE banner + read-only guard | **opus** (highest blast radius) | Firewall PIN step-up to enter (sub-bound, F3 anti-replay) → short-TTL `act_as` token (`sub=vendor`, `real_admin`, `scope`, `read_only` default), persistent on-screen banner, enter+exit BOTH audited (writes attributed to the admin). GATE: **T9** enter needs step-up + identity-bound; **T10** read-only blocks writes; **T11** can't climb to `/admin/*`; **T12** can't target an admin; **T13** two `events` rows on the PG leg. |
| **C12** | CI drift-guard + isolation re-probe + deploy | CI script, deploy recipe | **opus** (final gate) | CI: every nav `href` + every mounted router prefix MUST have a `feature_registry` row else fail the build (registry-drift guard). Re-run **T1–T18** against ALL new routes. FORTRESS deploy (backup `/opt/famit-panel` + `/opt/famit-agent` first, Telegram alert). Then flip `CONTROL_ENABLED=true`. GATE: full smoke — admin sees `/admin/*` 200, vendor 403/404, resting modules byte-identical (T17), all T1–T18 PASS. |

---

## 6. THE GATES THAT MATTER (regression + tenant-isolation + impersonation — copied verbatim from the security doc)

These T1–T18 probes are hard PASS/FAIL and gate `CONTROL_ENABLED=true`. The per-unit "GATE" column above maps each
probe to the unit that must satisfy it. **The forge-tenant-B-while-authed-as-A probe (T3) must PASS on every new
`/admin/*` and `/me/entitlements` route.**

- **T1** Vendor→`/admin/*` (GET+mutating) → **403** all. — gates C2
- **T2** Legacy password `FamitCall2026`→`/admin/vendors` → **403** (`auth_method=legacy_pw` rejected). — gates C2
- **T3** Forge-tenant-B-while-authed-as-A (canonical): B in body IGNORED or 403, stays A-scoped, on EVERY new route. — gates C2
- **T4** Hidden feature → **404** via raw saved token (curl, no FE). — gates C3
- **T5** Locked feature → **402** `{error:"locked",upgrade:true}`. — gates C3
- **T6** Core floor un-hideable: login/settings/auth/wallet-pay STILL 200; no self-lockout. — gates C3
- **T7** Fail-closed on unknown feature_key / resolver throw → **404**, never 200. — gates C3
- **T8** RLS floor: `famit_app` without admin GUC → 0 cross-tenant rows in `tenant_entitlements` (FORCE-RLS). — gates C1/C2
- **T9** Act-as enter requires step-up; wrong-admin step-up token → 403 identity mismatch. — gates C11
- **T10** Act-as read-only by default: any POST/PUT/DELETE → **403**; GET works. — gates C11
- **T11** Act-as can't climb: act-as token (sub=vendor) → `/admin/*` → **403**. — gates C11
- **T12** Act-as can't target an admin tenant. — gates C11
- **T13** Act-as audited both ends: TWO `events` rows (enter+exit) `actor=real_admin` on the IMMUTABLE PG leg. — gates C11
- **T14** Permission-change audited with non-null before/after; row INSERT-only. — gates C2
- **T15** Suspension kills tokens instantly (next call 401) + no new `/run` + in-flight untouched + data preserved. — gates C5
- **T16** Entitlement cache not cross-tenant (flip B → A's version/modes unchanged). — gates C4
- **T17** Resting-state byte-identical (`/campaigns /leads /me` vs pre-control). — gates C1, re-checked C12
- **T18** AI Copilot honors entitlements (billing locked → refusal, no data). — gates C10

---

## 7. FOUNDER BLOCKERS

**NONE.** This wave needs no external credentials, no new droplet (cap of 3 is fully used; everything rides the
existing box + Postgres + `events` leg + `wallet`/`firewall`), no Meta/Stripe/cloud-console step. Logto is NOT a
present dependency (build on `is_admin` now; the Logto-org binding is a later hardening unit). The only standing
founder-facing item is operational, not a blocker: the legacy static admin password retirement (post-ship), and the
firewall PIN must already be set for C11 impersonation step-up (it is, per F4).

---

## 8. RESTING-STATE / ROLLBACK DISCIPLINE (non-negotiable, F2/F4 precedent)

- Ships **default-OFF** (`CONTROL_ENABLED=false`): engine present, every tenant on default plan + empty overrides +
  `status=active` → `resolve_modes` returns `on` for everything → behavior byte-identical to today (T17).
- The enforcement choke-point returns immediately while the flag is off; `/me/entitlements` returns all-`on`.
- Backend rollback = restore `caller.py`/`.env` `*.controlbak.<ts>` + restart (drops routes; additive tables harmless).
  FE rollback = restore `/opt/famit-panel.bak.<ts>`.
- **NEVER touch the voice run-path (`agent.py` hot loop).** Control is read only at the API choke-point + the `/run`
  gate + per-lead status re-read — never per-turn (latency moat).
