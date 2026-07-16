# Control Layer — Platform Explore + Feature Registry Catalog

> READ-ONLY exploration output for the Foundation Control Layer (Tier-0 Super-Admin).
> Companion to `design/spec-control-layer.md` (the architecture) and `Z.MD` (the founder spec).
> This file = (A) the **reuse map** — exactly what entitlement scaffolding already exists on the
> LIVE box + panel, with `file:line` — and (B) the **full feature_registry catalog** — every
> controllable entity the Super-Admin can HIDE/LOCK, each with a stable `feature_key`, parent,
> nav route, and API prefix(es).
>
> Probed live: backend `famit@168.144.153.145:/opt/famit-agent` (caller.py 4664 lines), panel
> `caps/famit-panel`. Date 2026-06-10.

---

## A. REUSE MAP — what already exists to build ON TOP of (do NOT rebuild)

### A.1 Auth + tenant resolution (the spine entitlements bolt onto)

| Capability | Where (file:line) | Notes for the engine |
|---|---|---|
| **Tenant resolution from token** (never body) | `caller.py:404` `resolve_tenant(request)` | Single choke point. Order: JWT access → bare-PW (admin) → `tenant_id.hmac`. The entitlement middleware wraps THIS-derived `tenant_id`. Token-derived invariant already holds. |
| Credential extraction | `caller.py` `_extract_cred()` (called at `:417`) | Bearer / `X-Auth` header. |
| **JWT access tokens** (HS256, claims `sub/role/is_admin/jti`) | `auth.py:103` `_make_access`, `:128` `issue_pair`, `:141` `resolve_token` | Add a `version`/`act_as` claim here later for real-time + impersonation. Same `var/secret` as hmac. |
| Refresh-token rotation + revoke | `auth.py:117/187/211/224` | `revoke_all(tenant_id)` exists → useful on suspend/disable. |
| Login endpoints | `caller.py:1881` `/login`, `:1908` `/auth/login`, `:1921` `/auth/refresh`, `:1937` `/auth/logout` | `/login`,`/me` must stay **core** (un-hideable). |
| `/me` (returns role + is_admin) | `caller.py:1947` | Panel calls this on load (`lib/auth.ts:71`). `/me/entitlements` is the NEW sibling the panel + Copilot read. |

### A.2 Admin authority + role gating (the `is_admin` axis to reuse, plus the NEW entitlement axis)

| Capability | Where (file:line) | Notes |
|---|---|---|
| **`is_admin` flag** on tenant record | tenant dict throughout; seeded admin `caller.py:345-355` | The super-admin gate. All `/admin/*` control routes reuse this exact `if not t.get("is_admin"): 403` pattern (see `/tenants` below). |
| **Role model** `admin\|manager\|agent` | `caller.py:616` `_role_of`, `:641` `can(tenant, action)`; `ROLES` set | `can(t,"manage_tenants")` == admin-only — REUSE for control writes. ROLE axis (what a USER does) is **orthogonal** to ENTITLEMENT axis (what the TENANT's plan allows); a request must pass BOTH. |
| `403` forbidden helper | `caller.py:653` `_forbidden()` | Reuse for vendor → `/admin/*`. |
| **BOLA ownership guard** | `caller.py` `_owns()` (~`:660`), `require_object()` (~`:679`) | Cross-tenant object access already 404s. Control adds no new cross-tenant read path except the audited `/admin/*`. |
| Admin tenant list (cross-tenant read, admin-only) | `caller.py:3038` `GET /tenants`, `:3052` `POST /tenants` | **The exact template** for every `/admin/vendors*` route (admin gate + audit). |
| Password verify for JWT | `caller.py` `_verify_password_for_auth` (~`:690`) | salted hash; admin-PW path. |

**Panel side (role gating already shipped):**
| Capability | Where (file:line) |
|---|---|
| `useMe()` + localStorage cache | `lib/auth.ts:65` (`ME_KEY="famit_me"`) — **mirror this for `lib/entitlements.ts` / `famit_ent`** |
| `isAdmin()` / `canWrite()` / `isReadOnly()` | `lib/auth.ts:49/54/60` |
| **Sidebar role filter** `resolveNav()` | `components/Sidebar/index.tsx:46` — filters group CHILDREN by `roles`, drops a group with no visible children. **Extend HERE**: add an entitlement filter (drop `hidden` children, mark `locked`). One-line conceptual change. |
| `navVisible()` per-item gate | `components/Sidebar/index.tsx:23` |
| **`comingSoon` dimmed-pill pattern** (the LOCK visual precedent) | `components/Sidebar/Dropdown/index.tsx:77-87` — renders a non-`<Link>` dimmed row + "Soon" pill. **LOCK reuses this exact shape** (dimmed row + "Locked" pill instead of "Soon"). |
| Nav source of truth | `contstants/navigation.tsx:41` `navigation[]` (8 groups) + `:164` `navigationUser[]` (Settings) |

### A.3 Usage / limits / caps (surface in admin UI; plans write these)

| Capability | Where (file:line) | Notes |
|---|---|---|
| Per-tenant usage | `caller.py:3200` `GET /usage` (today/month + limits + active_now) | Vendor Workspace "Usage" tab + executive analytics. |
| **Cross-tenant usage (admin)** | `caller.py:3217` `GET /usage/all` | Powers the Vendor LIST usage column + Usage Analytics page. |
| **Set per-tenant limits (admin)** | `caller.py:3237` `POST /tenants/{tid}/limits` | `max_concurrency / daily_call_cap / monthly_minutes_cap`. Plan-assignment writes these. Already admin-gated + STORE_LOCK. |
| Default caps (admin vs vendor) | `caller.py:592-598` (admin 20/100000/1000000; vendor 3/500/5000) | Plan limit defaults derive from here. |
| Analytics | `caller.py:2996` `GET /analytics`, `:2969` `/stats` | Executive per-vendor metrics. |

### A.4 Wallet / credits + firewall step-up (credit control + step-up gate)

| Capability | Where (file:line) | Notes |
|---|---|---|
| Wallet balance / ledger / holds | `caller.py:2206/2230/2248` `GET /wallet*` | Admin top-up/freeze surfaces here; admin sees all via `is_admin` arg. |
| **Admin top-up** | `caller.py:2266` `POST /wallet/topup/{tenant_id}` | Reuse for `/admin/vendors/{id}/credits`. |
| **Firewall step-up (PIN, HS256, sub-bound)** | `firewall.py`; `caller.py:2301/2315/2334` `/firewall/*`; `_step_up_guard()` (~`:2390`) | **Gate money + impersonation control writes through this.** Non-breaking pass-through when OFF. |
| ACID no-double-spend ledger | `wallet.py` (F4, PROVEN) | Credits are an existing balance; control adds top-up/freeze, not a new balance. |

### A.5 Audit (immutable trail — control rides channel="control")

| Capability | Where (file:line) | Notes |
|---|---|---|
| **One-line audit wrapper** | `caller.py:756` `_audit(request, tenant, action, object_type, object_id, channel, meta)` | Every control mutation calls this with `channel="control"`. Already best-effort, captures actor/role/ip. |
| Audit record core | `audit.py:60` `record(...)` (actor, action, object_type, object_id, ip, channel, tenant_id, actor_role, meta) | Append-only. |
| **Audit read (admin sees all, vendor sees own)** | `caller.py:2158` `GET /audit?channel=&action=&limit=&offset=` + `audit.py:112` `tail()` | Admin Audit Logs page = `GET /audit?channel=control`. Already paginated + scoped. |
| Storage | `var/audit_log.jsonl` (json mode) + Postgres `events` table | `events` has **FORCE RLS** (`db/rls.sql:20`). Immutable leg already proven (F4). |

### A.6 Multi-tenant isolation primitives (what makes control safe)

| Capability | Where (file:line) | Notes |
|---|---|---|
| **Forced RLS** on all tenant tables | `db/rls.sql:20-23` (`billing,ledger,usage_events,cost_ledger,events` + more) ENABLE+FORCE | New `tenant_entitlements`/`plans` tables ship with the SAME RLS shape. |
| Tenant store | `caller.py:146` `TENANTS_FILE = var/tenants.json`; `:334` `_read_tenants()`, `:339` `_write_tenants()` | **JSON store today** → status/plan_id columns are additive. P1 strangler ready (next). |
| **P1 store-mode router (strangler)** | `caller.py:294` `store.py` MODE router (`json\|dual\|pg`); `:474` shims | Control store (`var/control/`) follows the SAME json→pg cutover discipline (F2/F4 precedent). |
| Var dir (json stores) | `var/` (tenants.json, audit_log.jsonl, billing.json, leads.json, campaigns/, ...) | Control JSON-first lands under `var/control/`. |

### A.7 NOT yet wired (gaps the spec already names — confirm before relying on them)

- **Logto orgs/RBAC:** engine is UP on the hatchet box, but **caller.py does NOT import/call Logto** (grep `logto` in caller.py = 0 hits). Today's authority = `is_admin` + JWT/hmac/PW. So C2's admin gate uses `is_admin` NOW; the "admin-org + `manage_tenants` scope" binding is a LATER unit, not a present dependency.
- **No `feature_registry`, `plans`, `tenant_entitlements`, `status`, `entitlements.py`** exist yet — all NEW (this is the build). No `var/control/` dir yet.
- **No backend enforcement middleware** — the §3 path→feature_key choke point is NEW.
- **No real-time version stamp** on entitlements — NEW.

---

## B. FEATURE REGISTRY CATALOG — every controllable entity (HIDE/LOCK targets)

**Schema** (per `spec-control-layer.md §2.1`): `key` (canonical dot-path, PK) · `kind`
(module/page/feature/action/integration/ai_agent/api/limit) · `parent_key` · `label` · `nav_href`
(route HIDE drops) · `api_prefixes` (backend 404/402 enforcement) · `default_mode` (global baseline:
on) · `is_core` (un-hideable floor).

**Resolution** (spec §2.6): `status-floor → tenant_override → plan → global default → parent-rolldown`;
unknown/missing → **hidden** (fail-closed). A `hidden` parent rolls down to all children.

**Mapping derivation:** `feature_key` ← `contstants/navigation.tsx` groups/children + `app/**/page.tsx`
routes; `api_prefixes` ← caller.py `@app.*` decorators + mounted sub-routers (`/ads`,`/funnels`,
`/workflows`,`/payments` prefixed, `/support` prefixed, `/booking`, `/ai-manager`, forms-surveys
`/forms`). All confirmed live this session.

> Legend: `[CORE]` = `is_core=true` (cannot be hidden — self-lockout floor). `[m]` next to a page = the
> nav child carries `roles:"manager"` today (ROLE axis); `[admin]` = `roles:"admin"`.

### B.0 Platform-core (un-hideable floor — guards against lockout)

| feature_key | kind | parent | label | nav_href | api_prefixes | core |
|---|---|---|---|---|---|---|
| `core.auth` | feature | — | Login / Session | /login | `/login`,`/auth/login`,`/auth/refresh`,`/auth/logout`,`/me` | [CORE] |
| `core.settings` | page | — | Settings | /settings | `/settings` (panel-local) | [CORE] |
| `core.me_entitlements` | api | — | Entitlement self-read | — | `/me/entitlements` | [CORE] |
| `core.health` | api | — | Health / Metrics | — | `/health`,`/metrics` | [CORE] |
| `core.wallet_pay` | feature | — | Wallet pay/balance read | — | `/wallet`,`/firewall/verify-pin` | [CORE] |

### B.1 Module: Command  (`mod.command`)

| feature_key | kind | parent | label | nav_href | api_prefixes |
|---|---|---|---|---|---|
| `mod.command` | module | — | Command | — | — |
| `command.dashboard` | page | mod.command | Dashboard | / | `/stats`,`/status`,`/leads/hot` |

### B.2 Module: AI Manager  (`mod.ai_manager`) `[m]`

| feature_key | kind | parent | label | nav_href | api_prefixes |
|---|---|---|---|---|---|
| `mod.ai_manager` | module | — | AI Manager | — | `/ai-manager` |
| `ai_manager.overview` | page | mod.ai_manager | Overview | /ai-manager/overview | `/ai-manager/status` |
| `ai_manager.test` | page | mod.ai_manager | Test Console | /ai-manager/test | `/ai-manager/sessions` |
| `ai_manager.commands` | page | mod.ai_manager | Command History | /ai-manager/commands | `/ai-manager/sessions` |
| `ai_manager.approvals` | page | mod.ai_manager | Pending Approvals | /ai-manager/approvals | `/ai-manager/sessions` |
| `ai_manager.capabilities` | page | mod.ai_manager | Capabilities | /ai-manager/capabilities | `/ai-manager/status` |
| `ai_manager.setup` | page | mod.ai_manager | Setup | /ai-manager/setup | `/ai-manager/numbers` |
| `ai_manager.users` | page | mod.ai_manager | Authorized Users | /ai-manager/users | `/ai-manager/numbers/{id}/grants`,`/ai-manager/numbers/{id}/revoke` |
| `ai_manager.copilot` | ai_agent | mod.ai_manager | AI Copilot (assistant) | — | `/ai-manager/sessions` | 
| `ai_manager.register_number` | action | ai_manager.setup | Register/verify number | — | `/ai-manager/numbers` (POST) |

> **AI Copilot must honor `/me/entitlements`** (spec §8.6): it refuses any feature whose mode is hidden/locked.

### B.3 Module: Grow  (`mod.grow`)

| feature_key | kind | parent | label | nav_href | api_prefixes |
|---|---|---|---|---|---|
| `mod.grow` | module | — | Grow | — | — |
| `grow.campaigns` | page | mod.grow | Campaigns | /campaigns | `/campaigns`,`/campaigns/{cid}`,`/campaigns/{cid}/ab` |
| `grow.campaigns.create` | action | grow.campaigns | Create campaign | — | `/campaigns` (POST) |
| `grow.campaigns.delete` | action | grow.campaigns | Delete campaign | — | `/campaigns/{cid}` (DELETE) |
| `grow.campaigns.abtest` | feature | grow.campaigns | A/B testing | — | `/campaigns/{cid}/ab` |
| `grow.ads` | page | mod.grow | Ad Automation `[m]` | /ads | `/ads`,`/ads/campaigns`,`/ads/optimize` |
| `grow.ads.propose` | action | grow.ads | Propose ad campaign | — | `/ads/campaigns/propose` (POST) |
| `grow.ads.approve` | action | grow.ads | Approve/launch ad | — | `/ads/campaigns/{id}/approve` (POST) |
| `grow.funnels` | page | mod.grow | Funnels | /funnels | `/funnels`,`/funnels/{id}` |
| `grow.funnels.publish` | action | grow.funnels | Publish funnel | — | `/funnels/{id}/publish` (POST) |
| `grow.forms` | page | mod.grow | Form Builder | /forms | `/forms`,`/forms/{id}` |
| `grow.forms.public` | feature | grow.forms | Public form intake | — | `/f/{public_token}`,`/f/{public_token}/submit` |

### B.4 Module: Sell  (`mod.sell`)

| feature_key | kind | parent | label | nav_href | api_prefixes |
|---|---|---|---|---|---|
| `mod.sell` | module | — | Sell | — | — |
| `sell.leads` | page | mod.sell | Leads | /leads | `/leads`,`/leads/batches`,`/leads/{lead_id}` |
| `sell.leads.import` | action | sell.leads | Import/create leads | — | `/leads` (POST) |
| `sell.leads.delete` | action | sell.leads | Delete lead | — | `/leads/{lead_id}` (DELETE) |
| `sell.crm` | page | mod.sell | CRM | /crm | `/contacts`,`/contacts/{phone}`,`/leads/hot` |
| `sell.crm.timeline` | feature | sell.crm | Contact timeline/NBA | — | `/contacts/{phone}/timeline`,`/contacts/{phone}/nba` |
| `sell.crm.edit` | action | sell.crm | Edit contact | — | `/contacts/{phone}` (PUT) |

### B.5 Module: Engage  (`mod.engage`)

| feature_key | kind | parent | label | nav_href | api_prefixes |
|---|---|---|---|---|---|
| `mod.engage` | module | — | Engage | — | — |
| `engage.run` | page | mod.engage | Run a Campaign | /run | `/run`,`/run/preview` |
| `engage.run.dial` | action | engage.run | Launch dial run | — | `/run` (POST) — **also gated by tenant.status (suspend)** |
| `engage.calls` | page | mod.engage | Call Logs | /calls | `/calls`,`/calls/{call_id}` |
| `engage.callbacks` | page | mod.engage | Callbacks | /callbacks | `/callbacks`,`/callbacks/{rid}` |
| `engage.whatsapp` | page | mod.engage | WhatsApp `[m]` | /whatsapp | `/whatsapp/send`,`/whatsapp/log`,`/whatsapp/threads` |
| `engage.whatsapp.send` | action | engage.whatsapp | Send WhatsApp msg | — | `/whatsapp/send` (POST) |
| `engage.whatsapp.inbound` | integration | engage.whatsapp | Inbound webhook | — | `/whatsapp/inbound` |
| `engage.support` | page | mod.engage | Customer Support | /support | `/support/tickets`,`/support/inbound` |
| `engage.support.reply` | action | engage.support | Reply/resolve ticket | — | `/support/tickets/{id}/reply`,`/support/tickets/{id}/resolve` |
| `engage.booking` | page | mod.engage | Booking | /booking | `/booking`,`/booking/availability`,`/booking/bookings` |
| `engage.booking.book` | action | engage.booking | Create booking | — | `/booking/book` (POST) |

### B.6 Module: Automate  (`mod.automate`)

| feature_key | kind | parent | label | nav_href | api_prefixes |
|---|---|---|---|---|---|
| `mod.automate` | module | — | Automate | — | — |
| `automate.workflows` | page | mod.automate | Workflows | /workflows | `/workflows`,`/workflows/{id}`,`/workflows/runs` |
| `automate.workflows.publish` | action | automate.workflows | Publish workflow | — | `/workflows/{id}/publish` (POST) |
| `automate.workflows.run` | action | automate.workflows | Run/trigger workflow | — | `/workflows/{id}/run`,`/workflows/{id}/hook` |
| `automate.workflows.approve` | action | automate.workflows | Approve run | — | `/workflows/runs/{id}/approve` (POST) |
| `automate.workflows.killswitch` | action | automate.workflows | Killswitch | — | `/workflows/killswitch` (POST) |
| `automate.webhooks` | page | mod.automate | Webhooks `[m]` | /webhooks | `/webhooks`,`/webhooks/{wid}` |
| `automate.webhooks.create` | action | automate.webhooks | Create webhook | — | `/webhooks` (POST) |

### B.7 Module: Money  (`mod.money`)

| feature_key | kind | parent | label | nav_href | api_prefixes |
|---|---|---|---|---|---|
| `mod.money` | module | — | Money | — | — |
| `money.payments` | page | mod.money | Payments `[m]` | /payments | `/payments/links`,`/payments/followups` |
| `money.payments.create_link` | action | money.payments | Create payment link | — | `/payments/links` (POST) |
| `money.payments.refund` | action | money.payments | Refund | — | `/payments/links/{id}/refund` (POST) |
| `money.billing_overview` | page | mod.money | Billing Overview | /billing/overview | `/billing/overview`,`/billing` |
| `money.billing_vendors` | page | mod.money | Billing Vendors | /billing/vendors | `/billing/vendors`,`/billing/vendor/{vid}` |
| `money.billing_explorer` | page | mod.money | Cost Explorer | /billing/explorer | `/billing/explorer` |
| `money.billing_audit` | page | mod.money | Billing Audit | /billing/audit | `/billing/audit` |
| `money.billing_plan` | page | mod.money | Plan & Ledger | /billing/plan | `/billing/ledger`,`/billing/{tenant_id}` |

### B.8 Module: Intelligence  (`mod.intelligence`)

| feature_key | kind | parent | label | nav_href | api_prefixes |
|---|---|---|---|---|---|
| `mod.intelligence` | module | — | Intelligence | — | — |
| `intelligence.analytics` | page | mod.intelligence | Analytics | /analytics | `/analytics`,`/stats` |

### B.9 Module: Foundation  (`mod.foundation`)

| feature_key | kind | parent | label | nav_href | api_prefixes |
|---|---|---|---|---|---|
| `mod.foundation` | module | — | Foundation | — | — |
| `foundation.suppression` | page | mod.foundation | Do-Not-Call | /suppression | `/suppression`,`/optout` |
| `foundation.vendors` | page | mod.foundation | Vendors (legacy admin) `[admin]` | /vendors | `/tenants` |

### B.10 Cross-cutting: Integrations / Brain / Voice (sub-controllable surfaces)

| feature_key | kind | parent | label | nav_href | api_prefixes |
|---|---|---|---|---|---|
| `integ.voice` | integration | — | Voice / telephony (Vobiz) | — | `/run`,`/voices`,`/extract` |
| `integ.whatsapp` | integration | — | WhatsApp (Meta) | — | `/whatsapp/*` |
| `integ.webhooks` | integration | — | Outbound webhooks | — | `/webhooks/*` |
| `integ.ads` | integration | — | Ads platforms | — | `/ads/*` |
| `integ.payments` | integration | — | Payment providers | — | `/payments/webhooks/{provider}` |
| `feature.brain` | feature | — | Brain / knowledge base | — | `/brain`,`/brain/knowledge`,`/brain/retrieve` |

### B.11 Usage limits + credits (numeric entitlements, attach to plans)

| feature_key | kind | parent | label | source api |
|---|---|---|---|---|
| `limit.max_concurrency` | limit | — | Max concurrent calls | `POST /tenants/{id}/limits` |
| `limit.daily_call_cap` | limit | — | Daily call cap | `POST /tenants/{id}/limits` |
| `limit.monthly_minutes_cap` | limit | — | Monthly minutes cap | `POST /tenants/{id}/limits` |
| `limit.monthly_credits` | limit | — | Monthly credit allowance | wallet `/wallet/topup/{id}` |
| `limit.seats` | limit | — | User seats | `/tenants` (count) |

### B.12 Super-Admin section itself (admin-only; NOT vendor-controllable — gated by `is_admin`)

> These are NEW admin pages (spec §5). They are **not** in the per-vendor toggle tree — they exist only
> for the founder and are gated by `is_admin` (403 for any vendor token), like `/tenants` today.

| feature_key | kind | label | nav_href | api_prefixes |
|---|---|---|---|---|
| `admin.overview` | admin_page | Control Overview | /admin | `/admin/features` |
| `admin.vendors` | admin_page | Vendors | /admin/vendors | `/admin/vendors` |
| `admin.vendor_workspace` | admin_page | Vendor Workspace | /admin/vendors/[id] | `/admin/vendors/{id}` |
| `admin.flags` | admin_page | Feature Flags (global) | /admin/flags | `/admin/flags` |
| `admin.plans` | admin_page | Plans | /admin/plans | `/admin/plans` |
| `admin.usage` | admin_page | Usage Analytics | /admin/usage | `/usage/all` |
| `admin.audit` | admin_page | Audit Logs | /admin/audit | `/audit?channel=control` |
| `admin.health` | admin_page | System Health | /admin/health | `/health`,`/admin/store-status` |
| `admin.support` | admin_page | Support | /admin/support | `/support` (admin view) |
| `admin.settings` | admin_page | Global Settings | /admin/settings | `/admin/flags` |

---

## C. CATALOG SUMMARY

- **Modules:** 9 (Command, AI Manager, Grow, Sell, Engage, Automate, Money, Intelligence, Foundation).
- **Vendor-controllable pages:** ~38 (incl. 7 AI-Manager sub-pages, 5 Billing sub-pages).
- **Vendor-controllable feature/action/integration/limit keys:** ~50 (actions, sub-features, integrations, brain, voice, 5 limits).
- **Core (un-hideable) keys:** 5.
- **Super-Admin admin-only pages (not in vendor tree):** 10.
- **Total catalog entries:** **~120 feature_keys** (≈105 vendor-controllable + 5 core + 10 admin-only).
- **Every nav `href` in `contstants/navigation.tsx` has a row** (the §8.11 registry-drift CI guard can assert this) — including the 4 `comingSoon` Create-Studio children, which map to `create_studio.*` keys with `default_mode='hidden'` (no route yet, so no API prefix).

## D. KEY FINDINGS / WATCH-OUTS FOR THE BUILD

1. **`is_admin` is the real super-admin gate today; Logto is NOT wired into caller.py** (0 grep hits). Build `/admin/*` on `is_admin` now; treat the Logto-org binding as a later hardening unit, not a blocker.
2. **Tenant store is JSON (`var/tenants.json`)** — `status` / `plan_id` / `trial_ends_at` are additive fields; no migration risk. P1 store-mode router (`caller.py:294`) is the cutover path to Postgres later.
3. **One choke point already exists for enforcement:** every request resolves tenant at `caller.py:404`. The new entitlement middleware wraps that — path→`feature_key` via `api_prefixes`, then `assert_access`. Hidden→404, locked→402, core bypass.
4. **Audit is free:** `_audit(...,channel="control")` (`caller.py:756`) + `GET /audit?channel=control` (`:2158`) already give the immutable trail + the read API for the Audit Logs page. No new audit infra.
5. **LOCK + HIDE visuals already have a precedent:** `comingSoon` dimmed pill (`Dropdown:77`) = the LOCK row; `resolveNav` child-drop (`Sidebar:46`) = the HIDE drop. Extend, don't invent.
6. **`api_prefixes` need path-param normalization:** routes like `/campaigns/{cid}` must match the registry prefix `/campaigns/` by first path segment — the middleware maps `/campaigns/abc` → `grow.campaigns`. Document the longest-prefix match (so `/leads/hot`→`sell.crm`/`command.dashboard` not `sell.leads`) — a few routes are intentionally shared and need an explicit map, not naive prefix.
7. **Sub-routers mount conditionally** (`app.include_router` guarded at `caller.py:4290+`): if a module router fails to import it simply isn't mounted → its `api_prefixes` 404 naturally. The registry must not assume a route exists; enforcement is additive over whatever IS mounted.
