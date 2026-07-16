# Foundation Control Layer — Execution-Ready Architecture + Build Plan

> Tier-0 Super-Admin control center. Source spec: `caps/Z.MD`. Cross-referenced against the
> LIVE backend (multi-tenant Postgres + forced RLS, Logto orgs/RBAC, wallet/firewall/audit,
> the `/api` contract in `memory/HANDOFF.md`) and the Core_2 code kit (the ONLY allowed UI source).
>
> **Status: DESIGN ONLY.** No code shipped. This file is the blueprint + unit-by-unit build plan
> + agent/order map. Read it, then execute the units in order, one verified commit at a time.
>
> **IRON UI RULE:** never invent UI. Every admin page below is a port of a named Core_2 template
> (paths cited) with our data rewired. Our panel already has the needed primitives ported
> (`components/{Switch,Tabs,Badge,KpiCard,Card,PageHeader,Table,Modal,Search,Select}`).

---

## 0. WHAT THE FOUNDER ASKED FOR (distilled from Z.MD, no loss)

A **Super-Admin Control Center** — visible ONLY to the main admin — that gives total, real-time,
no-deploy control over every vendor (tenant):

1. A new **Super-Admin sidebar section**: Overview · Vendors · Feature Flags · Plans · System Health ·
   Usage Analytics · Audit Logs · Support · Global Settings. Hidden from all vendors.
2. **Vendor list** → click a vendor → **Vendor Workspace**: overview (company/owner/email/phone/
   created/plan/status), executive usage (leads/campaigns/calls/minutes/WhatsApp/billing), health
   (last login/campaign/call/activity), and a **permissions panel**.
3. **Two control modes per item — HIDE and LOCK:**
   - **HIDE** = item vanishes everywhere — nav, search, URLs, APIs, menus, shortcuts. Not CSS.
     Permission-controlled; direct URL / API hit is denied.
   - **LOCK** = item stays visible but sits behind a disabled "upgrade" overlay; zero interaction,
     creates curiosity/upsell ("Should I pay for this?").
4. **Hierarchical scope:** module → page → feature → action/component → workflow trigger → AI agent →
   integration → API access → usage limit → credits → future capabilities.
5. **Global toggle vs per-vendor toggle.** Global flag = baseline for everyone; per-vendor override wins.
6. **Plans** (Plan A / Plan B / Enterprise / Trial) — bundles of flags + limits; assignable to a vendor.
7. **Vendor status:** Active / Trial / Suspended / Disabled / Expired. Suspended/Disabled = cannot log
   in, call, or create — **but data is preserved.**
8. **Real-time propagation** across active sessions (no logout/redeploy).
9. **Everything audit-logged** (who changed what, for whom, when).
10. **AI Copilot honors the same permission layer** ("Your account does not have access to Billing").
11. **Enforced on BOTH frontend and backend** — hidden/locked can't be reached via URL, API, browser
    devtools, or client bypass.

---

## 1. KEY INSIGHT — WE ARE 60% THERE ALREADY (reuse, don't rebuild)

The live platform already ships the spine this control layer needs. The control layer is mostly a
**new entitlement engine + an admin UI**, NOT a new auth/tenancy system.

| Founder ask | Already live (reuse) | Gap to build |
|---|---|---|
| Multi-tenant isolation | `tenants.json`→P1 Postgres, **forced RLS** on every table; every campaign/lead/call carries `tenant_id`; admin sees all, vendor sees own | Nothing — it's the foundation |
| Admin-over-tenants | `GET/POST /tenants` (admin-only, `403` for vendors); `is_admin` flag; seeded admin tenant | Extend with control routes |
| Roles | `role: admin\|manager\|agent`; nav `roles:` gating in `contstants/navigation.tsx`; `lib/auth.ts` `isAdmin/canWrite`; Sidebar `resolveNav` drops gated items | Add a SECOND, orthogonal axis: **entitlements** (what the tenant's PLAN/flags allow) vs **roles** (what the USER may do) |
| Usage/limits | `GET /usage`, `/usage/all` (admin), `POST /tenants/{id}/limits`; per-tenant `max_concurrency/daily_call_cap/monthly_minutes_cap` | Surface in UI; add credits/wallet control |
| Credits/wallet | `wallet.py` ACID ledger (no-double-spend PROVEN), `/wallet*` routes, `firewall.py` PIN+step-up | Admin top-up/freeze + entitlement gate |
| Audit | immutable PG `events` leg, `GET /audit?channel=` | Add `control` channel + admin audit page |
| Suspension | tenant record + caps | Add `status` field + login/run gates |
| Auth/orgs/RBAC | Logto self-hosted (1 tenant ⇔ 1 org, typed org-roles, M2M) — engine UP, caller.py integration is a LATER gated unit | Bind admin-org membership = super-admin authority |

**Conclusion:** build a **central Entitlement Engine** (`entitlements.py`) that every page/API/nav/AI
checks, fed by a 3-layer resolution (global flag → plan → per-vendor override), plus the admin UI.
Do NOT scatter `if vendor == x`. One engine; everything plugs in.

---

## 2. DATA MODEL (additive; lands as Postgres tables, RLS-shaped like P1; JSON-first allowed per the F2/F4 precedent)

> Pattern: ship JSON-first under `var/control/` (per-file, fast to land, reversible), then strangle to
> Postgres tables as a later unit — exactly how Brain (F2) and Wallet (F4) landed. The Postgres DDL is
> the target end-state; the engine reads through a `store.py`-style MODE router so the cutover is a flag.

### 2.1 `feature_registry` — the catalog of every controllable thing (seeded from nav + module map)
```
feature_registry(
  key            TEXT PRIMARY KEY,      -- canonical dot-path, e.g. "engage.calls", "engage.calls.export"
  kind           TEXT,                  -- module | page | feature | action | integration | ai_agent | api
  parent_key     TEXT NULL,             -- hierarchy (module→page→feature→action)
  label          TEXT,                  -- "Call Logs"
  nav_href       TEXT NULL,             -- "/calls" if it maps to a route (for HIDE to drop the nav item)
  api_prefixes   TEXT[] ,               -- ["/calls","/calls/"]  (for backend enforcement)
  default_mode   TEXT DEFAULT 'on',     -- on | hidden | locked  (the GLOBAL baseline)
  min_role       TEXT NULL,             -- optional: still respects admin/manager/agent
  is_core        BOOLEAN DEFAULT false  -- core (login/settings) — cannot be hidden, guards a lockout
)
```
The registry is the SINGLE SOURCE OF TRUTH for "what exists". New modules self-register here, so every
future feature auto-plugs into control (founder's explicit requirement).

### 2.2 `plans` + `plan_entitlements` — reusable bundles
```
plans(plan_id PK, name, description, is_default, created_at)
plan_entitlements(plan_id FK, feature_key FK, mode TEXT)   -- on|hidden|locked per feature per plan
plan_limits(plan_id FK, limit_key TEXT, value BIGINT)      -- max_concurrency, daily_call_cap, monthly_minutes_cap, monthly_credits, seats...
```
Seed plans: **Trial, Plan A (Starter), Plan B (Growth), Enterprise.** Mirrors the caps already on the
tenant record so plan-assignment writes those caps.

### 2.3 `tenant_entitlements` — per-vendor OVERRIDES (the highest-priority layer)
```
tenant_entitlements(
  tenant_id FK, feature_key FK,
  mode TEXT,                 -- on | hidden | locked  (overrides plan + global)
  set_by TEXT, set_at TIMESTAMPTZ, reason TEXT NULL,
  PRIMARY KEY(tenant_id, feature_key)
)
```
Empty row set = "inherit from plan/global". A row = an explicit per-vendor decision (the founder
clicking a toggle on a specific vendor).

### 2.4 Tenant record extensions (additive columns on the existing tenant store)
```
status        TEXT DEFAULT 'active'   -- active | trial | suspended | disabled | expired
plan_id       TEXT NULL               -- FK to plans
trial_ends_at TIMESTAMPTZ NULL
suspended_reason TEXT NULL
-- (credits handled by existing wallet_accounts; control adds admin top-up/freeze, not a new balance)
```

### 2.5 `control_audit` — every super-admin action (rides the EXISTING immutable `events` leg, channel="control")
```
event = { channel:"control", actor_tenant, actor_user, action, target_tenant, feature_key,
          old_value, new_value, reason, ip, ts }
```
Reuses the proven append-only `events` table (F4) — no new audit infra. `GET /audit?channel=control`
already filters by channel.

### THE RESOLUTION RULE (the heart of the engine — deterministic, fail-closed)
For a (tenant, feature_key) the effective mode is computed **most-specific-wins**:
```
1. tenant.status in (suspended,disabled,expired)  → EVERYTHING hidden except `is_core` (login/settings/billing-pay)
2. tenant_entitlements[feature_key].mode          → if present, WINS  (per-vendor override)
3. plan_entitlements[tenant.plan_id][feature_key] → plan baseline
4. feature_registry[feature_key].default_mode     → global baseline
5. parent rolldown: if a parent module is `hidden`, all children are `hidden` (a hidden module can't expose a child page)
=> effective_mode ∈ {on, hidden, locked}.  Unknown/missing feature → `hidden` (FAIL-CLOSED).
```

---

## 3. THE ENTITLEMENT ENGINE (`entitlements.py` on the live box) — the central plug

A single module, imported by caller.py, that exposes:
```
resolve_modes(tenant_id) -> { feature_key: "on"|"hidden"|"locked", ... }   # the whole map, cached
mode_for(tenant_id, feature_key) -> "on"|"hidden"|"locked"
assert_access(tenant_id, feature_key)  # raises 404 if hidden, 402/"locked" if locked, else passes
effective_limits(tenant_id) -> {max_concurrency, daily_call_cap, monthly_minutes_cap, monthly_credits}
```
- Reads through `store.py` MODE router (json|dual|pg) — same strangler as P1.
- **Cached per-tenant** (in-proc dict + version stamp); a control write bumps the version → cache
  invalidates → real-time propagation (see §6).
- **Tenant-derived only**: `tenant_id` comes from the auth token (never from the request body), exactly
  like every existing seam. RLS still enforces row isolation underneath.

### Backend enforcement (the load-bearing half — frontend HIDE is cosmetic without this)
A FastAPI **dependency / middleware** maps the request path → `feature_key` via `feature_registry.
api_prefixes`, then calls `assert_access(tenant, key)`:
- `hidden` → **404** (indistinguishable from "doesn't exist" — no information leak).
- `locked` → **402 Payment Required** `{error:"locked", feature, upgrade:true}` (UI renders the overlay).
- `on` → proceed. Core routes (`/login`,`/me`,`/health`,`/settings`,wallet-pay) bypass (else lockout).
This is ONE choke point; every `/api/*` route inherits enforcement without per-route edits.

---

## 4. API SURFACE — new admin-only routes (all under the EXISTING `is_admin` gate + `403` for vendors)

> All secured the same way `/tenants` already is: admin-tenant only, `X-Auth` token-derived, and (when
> Logto integration lands) additionally gated on **admin-org membership + `manage_tenants` scope**. The
> wallet/credit mutations additionally require the **firewall step-up token** (`firewall.py`) — money &
> destructive control must clear the PIN gate.

**Registry / catalog**
- `GET /admin/features` → the full `feature_registry` tree (for the Feature Flags + per-vendor UI).

**Global flags**
- `GET /admin/flags` → global `default_mode` per feature.
- `PUT /admin/flags/{feature_key}` form `mode=on|hidden|locked` → sets the global baseline. (audit)

**Plans**
- `GET /admin/plans` ; `POST /admin/plans` ; `PUT /admin/plans/{id}` (entitlements + limits) ; `DELETE`.

**Vendor control (the Vendor Workspace)**
- `GET /admin/vendors` → list: `{tenant_id,name,email,plan,status,created_at, usage_summary, health}`.
  (Joins existing `/usage/all` + last-activity from calls/leads — executive view, not full analytics.)
- `GET /admin/vendors/{id}` → full profile + **resolved entitlement map** (effective mode per feature,
  showing global/plan/override provenance) + usage + health + wallet balance.
- `PUT /admin/vendors/{id}/entitlements/{feature_key}` form `mode` , `reason?` → per-vendor override. (audit)
- `DELETE /admin/vendors/{id}/entitlements/{feature_key}` → clear override (revert to plan/global). (audit)
- `PUT /admin/vendors/{id}/plan` form `plan_id` → assign plan (writes plan limits to caps). (audit)
- `PUT /admin/vendors/{id}/status` form `status`,`reason?` → active/suspended/disabled/expired/trial. (audit)
- `PUT /admin/vendors/{id}/limits` → already exists as `POST /tenants/{id}/limits`; keep, surface in UI.
- `POST /admin/vendors/{id}/credits` form `amount`,`reason` (+ **firewall step-up**) → wallet top-up/freeze. (audit)
- `POST /admin/vendors/{id}/impersonate` (+ **firewall step-up**) → see §8 (act-as), returns a scoped,
  short-TTL, `act_as`-stamped token. (audit — both start and stop)

**Self-serve entitlement read (consumed by the vendor's OWN frontend + AI Copilot)**
- `GET /me/entitlements` → `{modes:{feature_key:mode}, status, plan, version}` for the logged-in tenant.
  The vendor panel calls THIS on load to render nav (hide/lock) and gate pages. The AI Copilot calls
  the same map to refuse locked/hidden features in-conversation.

---

## 5. FRONTEND — ADMIN PAGES (every page = a named Core_2 template port; our data rewired)

> Reuse map. Core_2 root = `C:\Users\kunal\Desktop\Core_2-Capsy-Dashboard\extracted\core-2-dashboard-builder-react\`.
> Our panel already ported `Switch`, `Tabs`, `Badge`, `KpiCard`, `Card`, `PageHeader`, `Table`, `Modal`,
> `Search`, `Select`, `Layout` — use them; do not re-derive.

New nav: add an **"H+ Super Admin"** collapsible group in `contstants/navigation.tsx`, every child
`roles:"admin"` so only the super-admin sees it (the Sidebar `resolveNav` already drops admin-only
groups for vendors). Children: Control Overview · Vendors · Feature Flags · Plans · Usage · Audit Logs ·
System Health · Global Settings.

| Admin page | Route | Core_2 template to PORT | What we rewire |
|---|---|---|---|
| **Control Overview** | `/admin` | `templates/HomePage` (KPI tiles + chart + recent list) | tiles = #vendors, active/suspended, calls today, minutes, credits burned; recent = last control-audit events |
| **Vendor list** | `/admin/vendors` | `templates/Customers/CustomerList/CustomerListPage` (+ `/List`) | rows = vendors; columns name/plan/status/last-active/usage; row click → workspace. (Our `app/vendors/page.tsx` already does the create-form + table in our Signal style — keep that, extend columns.) |
| **Vendor Workspace** | `/admin/vendors/[id]` | `templates/Customers/CustomerList/DetailsPage` (left **`/Customer`** profile card + right **`/Details`** tabbed body) | left = vendor identity/plan/status/credits + status actions; right Tabs = **Overview · Usage · Permissions · Billing · Audit** |
| → Permissions tab | (in workspace) | `templates/SettingsPage` **`/Menu`** (sticky section list) + `components/Switch` rows | the feature tree; each row = a **3-state control** (On / Lock / Hide) using `Switch` + a small segmented control; provenance pill (global/plan/override) |
| **Feature Flags (global)** | `/admin/flags` | `templates/SettingsPage` (sectioned `Card` list) + `Switch` | global `default_mode` per feature, grouped by module |
| **Plans** | `/admin/plans` | `templates/Products` list + `templates/Products/NewProductPage` (create/edit form with sections) OR `UpgradeToProPage` cards | plan cards; editor = entitlement checkboxes + limit fields |
| **Usage Analytics** | `/admin/usage` | `templates/Customers/OverviewPage` (charts + `Overview/Item` stat tiles + country/traffic blocks) | per-vendor executive metrics from `/usage/all` + `/analytics` |
| **Audit Logs** | `/admin/audit` | `templates/Notifications` (filterable feed) or `components/Table` rows | `GET /audit?channel=control`; filter by vendor/action/date |
| **System Health** | `/admin/health` | `templates/HomePage` tiles + `components/Table` | service up/down, queue depth, error rate (from a health endpoint) |
| **Global Settings** | `/admin/settings` | `templates/SettingsPage` full | platform-wide defaults |

### The 3-state permission control (the founder's HIDE vs LOCK, per feature)
A single reusable row component `components/EntitlementToggle` (NEW, but assembled from EXISTING
`Switch` + `Badge` + segmented buttons — NOT from scratch):
- visual: feature label · provenance pill (`global`/`plan A`/`override`) · segmented **[ On | Lock | Hide ]**.
- On = green; Lock = amber (overlay preview icon); Hide = grey.
- writes `PUT /admin/vendors/{id}/entitlements/{key}`; optimistic, with a toast on failure (the existing
  toast pattern in `app/vendors/page.tsx`).

### Vendor-side enforcement (what the VENDOR sees) — reuse the EXISTING role plumbing
- `lib/entitlements.ts` (NEW, mirrors `lib/auth.ts`): `useEntitlements()` loads `GET /me/entitlements`
  once, caches in `localStorage['famit_ent']`, exposes `modeOf(key)`.
- **Nav HIDE:** extend `Sidebar/resolveNav` (`components/Sidebar/index.tsx`) — it already filters by
  `roles`; add an entitlement filter: a child whose `feature_key` resolves to `hidden` is dropped
  exactly like an out-of-role child. ONE-line conceptual change to an existing, tested function.
- **Nav LOCK:** a `locked` child renders like the EXISTING `comingSoon` pattern in `Sidebar/Dropdown`
  (dimmed, non-link, a "Locked" pill instead of "Soon") — the pattern is already in the codebase.
- **Page LOCK overlay:** `components/LockOverlay` (NEW, but it's just a `Card` + blur + the existing
  `state-block`/`Modal` styles): renders the page chrome blurred behind an upsell panel; no interaction.
- **Page HIDE / direct-URL:** the route's page component calls `assertEntitled(key)` from
  `lib/entitlements`; `hidden` → redirect to `/` (same shape as `AuthGuard` in `app/providers.tsx`).
  **This is cosmetic only — the BACKEND 404/402 (§3) is the real lock.**

---

## 6. REAL-TIME PROPAGATION (founder: "applied instantly across active sessions")

- Each tenant's entitlement map carries a monotonically increasing `version`. A control write bumps it.
- **Cheap, robust default (ship first):** the vendor panel **polls** `GET /me/entitlements` on an
  interval (e.g. 20–30 s) + on every route change + on tab-focus; if `version` changed, it re-renders
  nav/pages and (on a downgrade to hidden/locked of the CURRENT page) bounces the user. No socket infra.
- The BACKEND is already real-time (it reads the live store every request via the cached engine, cache
  invalidated by the version bump) — so even a 30 s-stale client can NEVER actually USE a revoked
  feature; the API denies it immediately. The poll is purely for UI freshness.
- **Upgrade later (optional):** push via SSE/WebSocket or piggyback on a Hatchet event when a true
  instant UX is wanted. Not required for correctness — the API is the enforcement boundary.

---

## 7. MULTI-TENANT ISOLATION GUARANTEES (what makes this safe)

1. **Row isolation:** every data table already has **FORCED RLS** (P1) keyed on `tenant_id` from the
   admin-GUC; a vendor physically cannot read another vendor's rows even with a forged body. Control
   adds NO new cross-tenant read path.
2. **Tenant derivation:** `tenant_id` ALWAYS comes from the verified token, never the request body —
   the existing, isolation-probe-PASSED invariant. Control routes keep it.
3. **Admin authority is explicit & narrow:** `is_admin` today; **admin-org membership + `manage_tenants`
   scope** once Logto lands. Admin reads cross-tenant ONLY through the dedicated `/admin/*` routes,
   which are themselves audited. No vendor token can reach `/admin/*` (403).
4. **Fail-closed entitlements:** unknown feature, missing plan, suspended status → `hidden`. A bug
   defaults to LESS access, never more.
5. **Core-route floor:** `is_core` features can't be hidden → a misconfiguration can't lock the admin
   (or a paying vendor) out of login/settings/billing-pay. Guards against self-inflicted lockout.
6. **Two orthogonal axes never conflate:** ROLE (what a USER may do: admin/manager/agent) vs
   ENTITLEMENT (what the TENANT's plan/flags allow). A page must pass BOTH. This prevents "manager at a
   downgraded vendor" from acting beyond the plan.

---

## 8. GAPS / EDGE-CASES / SECURITY THE FOUNDER DID NOT MENTION (call these out)

1. **Self-lockout.** Hiding `settings`/`login`/`billing-pay` would brick a vendor (or the admin).
   → `is_core` floor (§2.1, §7.5) makes those un-hideable; UI greys them out.
2. **In-flight jobs on suspend.** Suspending a vendor mid-campaign: do running calls keep dialing?
   → Decision: **status=suspended stops NEW dials at the run-loop gate but lets in-flight calls finish**
   (data integrity + no half-charged calls); `disabled` is harder (also blocks login). Document it.
3. **HIDE must not leak via error codes.** A hidden feature returns **404** (not 403) so a vendor can't
   even confirm it exists. Locked returns 402 (intentional curiosity). Spelled out in §3.
4. **Impersonation / act-as is dangerous.** The founder implied "see vendor data" — impersonation needs:
   firewall step-up (PIN), short TTL token stamped `act_as=<tenant>` + `real_admin=<id>`, a hard
   **read-only-by-default** mode, a persistent on-screen "You are viewing as X" banner, and BOTH
   enter+exit audited. Writes while impersonating are audited as the admin, never silently as the vendor.
5. **Plan downgrade vs existing data.** Downgrading below current usage (e.g. 2000 leads on a 1000 cap):
   don't delete — **freeze new creation**, keep existing readable. (Mirrors the wallet "data remains".)
6. **AI Copilot bypass.** The Copilot must call `GET /me/entitlements` and refuse hidden/locked features
   IN THE PROMPT/TOOL layer — otherwise it becomes a side-channel to locked data. (Founder noted this.)
7. **Direct API / token replay.** Frontend HIDE is cosmetic; a saved token hitting `/calls` directly
   must 404 if hidden. The §3 middleware is the real boundary — do NOT ship HIDE as frontend-only.
8. **Cache staleness window.** A 30 s poll means UI can lag a revoke by ≤30 s — acceptable because the
   API denies immediately (§6). Document the SLA; don't claim "instant" UI without the poll.
9. **Admin audit of the admin.** Super-admin actions are logged, but who watches the admin? → all
   `/admin/*` writes are append-only in the immutable `events` leg (can't be edited/deleted), and the
   audit page is read-only. For a multi-admin future, add `set_by` (already in schema) + optional
   second-admin approval on destructive ops (suspend/credit-freeze).
10. **Migration of existing tenants.** On rollout, every existing tenant gets `status=active`, the
    default plan, and an EMPTY override set (= inherit global = today's behavior). Zero behavior change
    on day one (the F2/F4 "resting state byte-identical" discipline).
11. **Feature registry drift.** A new module that forgets to self-register is invisible to control →
    defaults to `on` and ungoverned. → CI check: every nav `href` and every mounted router prefix MUST
    have a `feature_registry` row, else fail the build.
12. **Trial expiry automation.** `status=trial` + `trial_ends_at` needs a sweep to flip to `expired` —
    fold into the EXISTING 60 s `scheduler_loop` (don't add infra).

---

## 9. TOP 3 SECURITY CONSIDERATIONS (the ones that can sink this)

1. **Backend is the ONLY real boundary — never frontend-only.** HIDE/LOCK enforced in the UI is
   theatre; the §3 middleware (path→feature_key→`assert_access`, 404 for hidden / 402 for locked, at ONE
   choke point) is what actually stops a saved token, a curl, or devtools. Fail-closed: unknown/missing →
   denied. Without this, every "hidden" feature is one F12 away.
2. **Privilege-boundary integrity of `/admin/*` + impersonation.** Cross-tenant power lives only behind
   `is_admin` (→ admin-org + `manage_tenants` scope with Logto) and is unreachable by any vendor token
   (403). Impersonation is the sharpest knife: PIN step-up, short-TTL `act_as` token, read-only default,
   persistent banner, both-ends audited, writes attributed to the admin. A leaked admin token or a
   sloppy act-as is a full-platform compromise — treat it like root.
3. **Tenant-derivation + RLS must stay inviolable under the new write paths.** Every control route keeps
   `tenant_id` token-derived (never body), and the new `tenant_entitlements`/`plans` tables ship with
   the same FORCED RLS shape as P1, so even a control-layer bug can't cross tenants at the row level. Re-
   run the isolation probe (forge tenant B in the body while authed as A → stays A-scoped) against every
   new `/admin/*` and `/me/entitlements` route before flipping it on.

---

## 10. UNIT-BY-UNIT BUILD PLAN (crash-safe; one verified commit per unit; agent + model per unit)

> Order respects dependencies. Each unit: mark IN PROGRESS in a STATE file → build → run its test →
> commit → flip DONE. Resting state stays byte-identical until a flag flips (F2/F4 discipline). Backend
> units serialize on `caller.py` (ONE agent at a time on that file). Frontend units partition by page.

| # | Unit | Deliverable + test (must pass before commit) | Agent / model |
|---|---|---|---|
| **C0** | **Feature registry + seed** | `feature_registry` rows for every nav `href` + module prefix; `entitlements.py` `resolve_modes` with the §2 resolution rule + fail-closed; unit test: resolution precedence (global<plan<override<status) + parent-rolldown + unknown→hidden. JSON-first under `var/control/`. | backend — **opus** (it's the core logic; get it right) |
| **C1** | **Tenant status + plans store** | additive tenant columns (`status`,`plan_id`,`trial_ends_at`); `plans`/`plan_entitlements`/`plan_limits`; seed Trial/A/B/Enterprise; migration sets all existing tenants active+default+empty-overrides; test: existing `/campaigns /leads /me` byte-identical (resting state proof). | backend — **sonnet** |
| **C2** | **Admin API routes** | all §4 `/admin/*` + `/me/entitlements`; admin-gated (403 for vendors), token-derived, audited to `events` channel=`control`; wallet/impersonate behind firewall step-up. Test: vendor token → 403 on every `/admin/*`; isolation probe (forge body tenant) PASS; audit row written. | backend — **opus** (security-critical) |
| **C3** | **Backend enforcement middleware** | the §3 path→feature_key→`assert_access` choke point; hidden→404, locked→402, core bypass. Test: with a feature set `hidden`, a direct token hit on its route → 404; `locked` → 402; `on` → 200; `/login`/`/me`/wallet-pay always pass. | backend — **opus** (the real security boundary) |
| **C4** | **Real-time version + cache** | per-tenant `version` bump on control write; engine cache invalidation; `/me/entitlements` returns `version`. Test: write flips a flag → next `/me/entitlements` shows new version+mode; API denies immediately. | backend — **sonnet** |
| **C5** | **Suspend/trial sweep** | run-loop gate honors `status` (suspended → no new dials, in-flight finish); trial→expired sweep folded into the 60 s `scheduler_loop`. Test: suspend a tenant → `/run` blocked, existing call record untouched. | backend — **sonnet** |
| **C6** | **Vendor-side entitlement plumbing (FE)** | `lib/entitlements.ts` (`useEntitlements`, `modeOf`, poll+focus refresh); extend `Sidebar/resolveNav` to drop `hidden` children + render `locked` like `comingSoon`; `components/LockOverlay`; per-page `assertEntitled`. Test: `npm run build` exit 0; with a flag hidden, the nav item is gone + URL redirects; locked shows overlay. | frontend — **sonnet** (port, don't invent) |
| **C7** | **Admin Vendor list + Workspace (FE)** | port Customers `CustomerListPage` + `DetailsPage` (Customer + Details tabs); wire `/admin/vendors` + `/admin/vendors/{id}`; status actions. Test: build exit 0; list renders real vendors; workspace tabs render. | frontend — **sonnet** |
| **C8** | **Permissions tab + EntitlementToggle (FE)** | `components/EntitlementToggle` from existing `Switch`+`Badge`; SettingsPage `Menu` section layout; 3-state On/Lock/Hide writing `/admin/vendors/{id}/entitlements/{key}` with provenance pill. Test: build exit 0; toggling a feature persists + reflects in `/me/entitlements`. | frontend — **sonnet** |
| **C9** | **Global Flags + Plans + Usage + Audit pages (FE)** | port SettingsPage (flags), Products/UpgradeToPro (plans editor), Customers OverviewPage (usage), Notifications/Table (audit `channel=control`). Test: build exit 0; each page loads real data. | frontend — **sonnet** (can be 2 sub-agents partitioned by page; never same file) |
| **C10** | **AI Copilot entitlement gate** | Copilot loads `/me/entitlements`; refuses hidden/locked features in tool/prompt layer with the upsell line. Test: with billing locked, "show billing" → polite refusal, no data. | backend — **sonnet** |
| **C11** | **Impersonation / act-as** | firewall step-up → short-TTL `act_as` token, read-only default, persistent banner, enter+exit audited. Test: admin act-as vendor → sees vendor view read-only; banner present; both audit rows written; token expires. | backend+frontend — **opus** (highest blast radius) |
| **C12** | **CI registry-drift guard + isolation re-probe + deploy** | CI: every nav href + router prefix has a registry row else fail; re-run isolation probe on all new routes; FORTRESS deploy recipe (backup `/opt/famit-panel` + `/opt/famit-agent` first). Test: full smoke (admin sees `/admin/*` 200, vendor 403/404, resting modules byte-identical). | mixed — **opus** (final gate) |

**Orchestration notes (per the founder's delegation mandate):**
- **One agent per file/domain.** C0–C5,C10,C11(backend) all touch `caller.py`/box modules → run
  **sequentially**, one agent at a time, each committing before the next. Never two agents on `caller.py`.
- **Frontend C6–C9 partition by page/component** → can parallelize across DIFFERENT files, but C6 (the
  shared `Sidebar`/`lib`) lands FIRST and alone (shared file).
- **Model routing:** the entitlement engine, the enforcement middleware, the admin-auth routes, and
  impersonation are **opus** (security-load-bearing). Everything else (stores, page ports, sweeps) is
  **sonnet**. Mechanical seeds can be **haiku**.
- Each agent returns conclusions only (file:line, pass/fail), commits in small units, and updates a
  `caps/CONTROL_LAYER_STATE.md` ledger with the one IN-PROGRESS line (crash-safe resume).

---

## 11. RESTING-STATE / ROLLBACK DISCIPLINE (non-negotiable, per F2/F4 precedent)

- Ships **default-OFF**: with the engine present but every tenant on the default plan + empty overrides +
  `status=active`, `resolve_modes` returns `on` for everything → **behavior byte-identical to today**.
- The enforcement middleware is behind a `CONTROL_ENABLED` flag (default off) until C12's smoke passes.
- Rollback = restore the `caller.py`/`.env` backups + restart (drops the routes; control tables are
  additive and harmless). Frontend rollback = restore `/opt/famit-panel.bak.<ts>`.
- NEVER touch the voice run-path (`agent.py` hot loop) — control is read at the API/run-gate layer only.
```
