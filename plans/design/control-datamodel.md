# Control Layer — Entitlement DATA MODEL + RESOLUTION ALGORITHM + API

> **Role of this doc (READ-ONLY design, no code/deploy/git).** The *what-it-controls* blueprint +
> *admin UI* live in `design/spec-control-layer.md`. THIS doc is the engine's spine: exact **DDL**
> for every table, the **resolution algorithm** as precise fail-closed pseudocode, the **/admin +
> /me API contract**, and how it **plugs into the live `Sidebar/resolveNav` + the backend middleware**.
>
> **Grounded in the LIVE box** (`famit@168.144.153.145:/opt/famit-agent/`, verified from brain):
> P1 forced-RLS multi-tenancy with `db.engine.session(tenant_id=)` admin-GUC, `wallet.reserve/settle`,
> `firewall.check_pin(tid,pin)` + `mint_step_up(tid,scope)` + `verify_step_up_token(token,scope,
> expected_sub)`, `audit.record(actor,action,object_type,object_id,channel,tenant_id,meta)` →
> immutable PG `events`, the `store.py`-style `json|dual|pg` MODE router (P1/F2/F4 strangler), and the
> FE `contstants/navigation.tsx` 8-section IA + `components/Sidebar/index.tsx::resolveNav`.
>
> **Discipline (F2/F4 precedent):** additive-only; ships **default-OFF** (`CONTROL_ENABLED`); resting
> state byte-identical until the flag flips; rollback = restore backups + restart (tables are inert).

---

## 0. CANONICAL FEATURE KEYS (derived 1:1 from the live nav — the seed source of truth)

`feature_registry` is seeded directly from `contstants/navigation.tsx` so the catalog == what exists.
Key = `section.page[.feature[.action]]` (dot-path). Section codes match the IA comment in the nav file.

| key | kind | parent_key | label | nav_href | api_prefixes | default | core |
|---|---|---|---|---|---|---|---|
| `command` | module | — | Command | — | — | on | ✔ |
| `command.dashboard` | page | `command` | Dashboard | `/` | `/analytics/summary` | on | ✔ |
| `ai_manager` | module | — | AI Manager | — | `/ai-manager` | on | |
| `ai_manager.overview` | page | `ai_manager` | Overview | `/ai-manager/overview` | `/ai-manager/dashboard` | on | |
| `ai_manager.test` | page | `ai_manager` | Test Console | `/ai-manager/test` | `/ai-manager/commands/test` | on | |
| `ai_manager.commands` | page | `ai_manager` | Command History | `/ai-manager/commands` | `/ai-manager/commands` | on | |
| `ai_manager.approvals` | page | `ai_manager` | Pending Approvals | `/ai-manager/approvals` | `/ai-manager/approvals` | on | |
| `ai_manager.capabilities` | page | `ai_manager` | Capabilities | `/ai-manager/capabilities` | `/ai-manager/capabilities` | on | |
| `ai_manager.setup` | page | `ai_manager` | Setup | `/ai-manager/setup` | `/ai-manager/profile` | on | |
| `ai_manager.users` | page | `ai_manager` | Authorized Users | `/ai-manager/users` | `/ai-manager/authorized-users` | on | |
| `grow` | module | — | Grow | — | — | on | |
| `grow.campaigns` | page | `grow` | Campaigns | `/campaigns` | `/campaigns` | on | |
| `grow.campaigns.create` | action | `grow.campaigns` | Create campaign | — | `POST /campaigns` | on | |
| `grow.ads` | page | `grow` | Ad Automation | `/ads` | `/ads` | on | |
| `grow.funnels` | page | `grow` | Funnels | `/funnels` | `/funnels` | on | |
| `grow.forms` | page | `grow` | Form Builder | `/forms` | `/forms` | on | |
| `sell` | module | — | Sell | — | — | on | |
| `sell.leads` | page | `sell` | Leads | `/leads` | `/leads`,`/contacts` | on | |
| `sell.leads.export` | action | `sell.leads` | Export leads | — | `/leads/export` | on | |
| `sell.crm` | page | `sell` | CRM | `/crm` | `/crm` | on | |
| `engage` | module | — | Engage | — | — | on | |
| `engage.run` | page | `engage` | Run a Campaign | `/run` | `POST /run`,`/run/preview` | on | |
| `engage.calls` | page | `engage` | Call Logs | `/calls` | `/calls` | on | |
| `engage.callbacks` | page | `engage` | Callbacks | `/callbacks` | `/callbacks` | on | |
| `engage.whatsapp` | page | `engage` | WhatsApp | `/whatsapp` | `/whatsapp` | on | |
| `engage.support` | page | `engage` | Customer Support | `/support` | `/support` | on | |
| `engage.booking` | page | `engage` | Booking | `/booking` | `/booking` | on | |
| `automate` | module | — | Automate | — | — | on | |
| `automate.workflows` | page | `automate` | Workflows | `/workflows` | `/workflows` | on | |
| `automate.webhooks` | page | `automate` | Webhooks | `/webhooks` | `/webhooks` | on | |
| `money` | module | — | Money | — | — | on | |
| `money.payments` | page | `money` | Payments | `/payments` | `/payments` | on | |
| `money.billing` | page | `money` | Billing | `/billing/overview` | `/billing` | on | ✔ |
| `money.billing.pay` | action | `money.billing` | Pay / wallet | — | `/wallet`,`/wallet/` | on | ✔ |
| `intelligence` | module | — | Intelligence | — | — | on | |
| `intelligence.analytics` | page | `intelligence` | Analytics | `/analytics` | `/analytics` | on | |
| `foundation` | module | — | Foundation | — | — | on | ✔ |
| `foundation.suppression` | page | `foundation` | Do-Not-Call | `/suppression` | `/suppression` | on | |
| `foundation.settings` | page | `foundation` | Settings | `/settings` | `/settings`,`/me` | on | ✔ |
| `integration.elevenlabs` | integration | `money` | ElevenLabs (TTS) | — | — | on | |
| `integration.groq` | integration | `money` | Groq (LLM) | — | — | on | |
| `integration.sarvam` | integration | `money` | Sarvam (STT) | — | — | on | |
| `integration.vobiz` | integration | `engage` | VoBiz (telephony) | — | — | on | |

> `is_core` keys (login/`/me`, settings, dashboard, billing+pay) can **never** be HIDDEN — the engine
> refuses (§3 guard) so a misconfig can't lock a tenant out. Admin-only nav (`foundation.vendors`,
> the whole `H+ Super Admin` group) is gated by **role**, not entitlement, and is excluded from the
> registry (a vendor's entitlement map never references it).

---

## 1. DDL — additive Postgres tables (RLS-shaped like P1; JSON-first via `store.py` MODE router)

> Land **JSON-first** under `var/control/*.json` (per-file, reversible, fast — the F2/F4 path), reading
> through the `json|dual|pg` MODE router, then strangle to these tables as a later unit. The DDL below
> is the **target end-state**. Tenant-scoped tables carry **FORCE ROW LEVEL SECURITY** with the same
> `app.current_tenant` / `app.is_admin` GUC policy as every P1 table (copy `crm/schema.sql`).

```sql
-- ════════════════════════════════════════════════════════════════════════
-- 1.1  feature_registry — the catalog of every controllable thing (GLOBAL, not tenant-scoped)
--      Single source of truth for "what exists". New modules self-register here.
-- ════════════════════════════════════════════════════════════════════════
CREATE TABLE feature_registry (
  key            TEXT PRIMARY KEY,                 -- canonical dot-path "engage.calls.export"
  kind           TEXT NOT NULL                     -- module|page|feature|action|integration|ai_agent|api
                  CHECK (kind IN ('module','page','feature','action','integration','ai_agent','api')),
  parent_key     TEXT REFERENCES feature_registry(key) ON DELETE CASCADE,
  label          TEXT NOT NULL,
  nav_href       TEXT,                             -- "/calls" if it maps to a route (HIDE drops the nav item)
  api_prefixes   TEXT[]      NOT NULL DEFAULT '{}',-- ["/calls","/calls/"] for backend path→key mapping
  default_mode   TEXT NOT NULL DEFAULT 'on'        -- GLOBAL baseline
                  CHECK (default_mode IN ('on','hidden','locked')),
  min_role       TEXT,                             -- optional extra role floor (admin|manager|agent), orthogonal
  is_core        BOOLEAN NOT NULL DEFAULT false,   -- login/settings/billing-pay — CANNOT be hidden
  sort_order     INTEGER NOT NULL DEFAULT 0,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_registry_parent ON feature_registry(parent_key);
-- GLOBAL table: NO RLS (it's a shared catalog). Writable only via /admin/flags (admin-gated).

-- ════════════════════════════════════════════════════════════════════════
-- 1.2  plans + plan_entitlements + plan_limits — reusable bundles (GLOBAL)
-- ════════════════════════════════════════════════════════════════════════
CREATE TABLE plans (
  plan_id     TEXT PRIMARY KEY,                    -- 'trial','plan_a','plan_b','enterprise'
  name        TEXT NOT NULL,
  description TEXT,
  is_default  BOOLEAN NOT NULL DEFAULT false,      -- exactly one default (new/unknown tenant lands here)
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE plan_entitlements (
  plan_id     TEXT NOT NULL REFERENCES plans(plan_id) ON DELETE CASCADE,
  feature_key TEXT NOT NULL REFERENCES feature_registry(key) ON DELETE CASCADE,
  mode        TEXT NOT NULL CHECK (mode IN ('on','hidden','locked')),
  PRIMARY KEY (plan_id, feature_key)
);
-- A plan ONLY lists features it overrides off-default; absent row => inherit feature_registry.default_mode.

CREATE TABLE plan_limits (
  plan_id   TEXT NOT NULL REFERENCES plans(plan_id) ON DELETE CASCADE,
  limit_key TEXT NOT NULL,                         -- max_concurrency|daily_call_cap|monthly_minutes_cap|
  value     BIGINT NOT NULL,                       --   monthly_credits|seats|max_leads|max_campaigns ...
  PRIMARY KEY (plan_id, limit_key)
);

-- ════════════════════════════════════════════════════════════════════════
-- 1.3  tenant_entitlements — per-vendor OVERRIDES (highest-priority layer, TENANT-SCOPED + FORCE-RLS)
-- ════════════════════════════════════════════════════════════════════════
CREATE TABLE tenant_entitlements (
  tenant_id   TEXT NOT NULL,
  feature_key TEXT NOT NULL REFERENCES feature_registry(key) ON DELETE CASCADE,
  mode        TEXT NOT NULL CHECK (mode IN ('on','hidden','locked')),
  set_by      TEXT NOT NULL,                       -- admin user who clicked it
  set_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  reason      TEXT,
  PRIMARY KEY (tenant_id, feature_key)
);
-- No row => inherit plan/global. A row => an explicit per-vendor decision.
ALTER TABLE tenant_entitlements ENABLE ROW LEVEL SECURITY;
ALTER TABLE tenant_entitlements FORCE ROW LEVEL SECURITY;       -- forced: even table owner is filtered
CREATE POLICY te_isolation ON tenant_entitlements USING (
  current_setting('app.is_admin', true) = '1'                  -- admin GUC sees all (for /admin/*)
  OR tenant_id = current_setting('app.current_tenant', true)   -- vendor sees only own (for /me/*)
);

-- ════════════════════════════════════════════════════════════════════════
-- 1.4  tenant_status — status/plan/trial + a per-tenant entitlement VERSION (TENANT-SCOPED + FORCE-RLS)
--      (additive sidecar to the existing tenant store — does NOT alter the live tenants table)
-- ════════════════════════════════════════════════════════════════════════
CREATE TABLE tenant_status (
  tenant_id        TEXT PRIMARY KEY,
  status           TEXT NOT NULL DEFAULT 'active'
                    CHECK (status IN ('active','trial','suspended','disabled','expired')),
  plan_id          TEXT REFERENCES plans(plan_id),
  trial_ends_at    TIMESTAMPTZ,
  suspended_reason TEXT,
  ent_version      BIGINT NOT NULL DEFAULT 1,      -- bumped on ANY control write → real-time invalidation
  updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_by       TEXT
);
ALTER TABLE tenant_status ENABLE ROW LEVEL SECURITY;
ALTER TABLE tenant_status FORCE ROW LEVEL SECURITY;
CREATE POLICY ts_isolation ON tenant_status USING (
  current_setting('app.is_admin', true) = '1'
  OR tenant_id = current_setting('app.current_tenant', true)
);
-- Credits/balance stay in the existing F4 wallet_accounts — control adds top-up/freeze, NOT a new balance.

-- ════════════════════════════════════════════════════════════════════════
-- 1.5  entitlement_audit — every super-admin action.
--      PRIMARY sink = the EXISTING immutable PG `events` leg via audit.record(channel='control').
--      This optional projection table is a fast queryable mirror for the Audit page; events is truth.
-- ════════════════════════════════════════════════════════════════════════
CREATE TABLE entitlement_audit (
  id             BIGSERIAL PRIMARY KEY,
  actor_user     TEXT NOT NULL,                    -- the super-admin (real_admin even under impersonation)
  actor_tenant   TEXT NOT NULL,                    -- admin tenant
  action         TEXT NOT NULL,                    -- 'set_override'|'set_flag'|'set_plan'|'set_status'|
                                                   --   'credit_topup'|'credit_freeze'|'impersonate_start'|
                                                   --   'impersonate_stop'|'plan_edit'
  target_tenant  TEXT,                             -- the vendor acted upon (NULL for a global flag)
  feature_key    TEXT,
  old_value      TEXT,
  new_value      TEXT,
  reason         TEXT,
  ip             TEXT,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- Append-only by convention; no UPDATE/DELETE route. The events leg is the tamper-proof copy.
```

---

## 2. THE RESOLUTION ALGORITHM (the heart — deterministic, most-specific-wins, FAIL-CLOSED)

`entitlements.py` computes the effective mode of every feature for a tenant. **Most-specific-wins**;
anything unknown or unreachable resolves to **`hidden`** (deny). Two passes: (A) raw per-key resolution,
then (B) **parent rolldown** so a hidden/locked parent forces its subtree.

```python
# ── inputs (all read through store.py MODE router; tenant rows are RLS-scoped) ──
#   registry      : { key -> {parent_key, default_mode, is_core, kind} }   # GLOBAL catalog
#   plan_ent      : { feature_key -> mode }   for tenant.plan_id            # plan layer
#   overrides     : { feature_key -> mode }   for tenant                    # per-vendor layer
#   status        : 'active'|'trial'|'suspended'|'disabled'|'expired'
#
# Output: { feature_key -> 'on'|'hidden'|'locked' } for EVERY key in registry.

MODES = {'on', 'hidden', 'locked'}

def resolve_modes(tenant_id) -> dict[str, str]:
    registry  = load_registry()                         # cached; the catalog
    status    = load_status(tenant_id)                  # default 'active' if absent (new tenant)
    plan_id   = load_plan_id(tenant_id) or default_plan_id()
    plan_ent  = load_plan_entitlements(plan_id)         # {} if plan unknown
    overrides = load_overrides(tenant_id)               # {} if none

    eff = {}

    # ── PASS A: per-key, most-specific-wins ────────────────────────────────
    for key, meta in registry.items():

        # (1) STATUS GATE — suspended/disabled/expired = everything HIDDEN except is_core.
        #     (is_core stays reachable so the tenant can log in, see settings, and PAY to reactivate.)
        if status in ('suspended', 'disabled', 'expired'):
            eff[key] = 'on' if meta['is_core'] else 'hidden'
            continue

        # (2) PER-VENDOR OVERRIDE — wins outright if present.
        m = overrides.get(key)
        # (3) PLAN ENTITLEMENT — next most specific.
        if m is None:
            m = plan_ent.get(key)
        # (4) GLOBAL DEFAULT — registry baseline.
        if m is None:
            m = meta['default_mode']
        # (5) UNKNOWN/garbage value → FAIL-CLOSED.
        if m not in MODES:
            m = 'hidden'

        # CORE FLOOR — a core feature can never be hidden (anti-lockout); demote hidden→on.
        #   (LOCK on a core feature is still allowed: e.g. billing visible-but-locked is acceptable;
        #    HIDE is not, because it removes the only path back in.)
        if meta['is_core'] and m == 'hidden':
            m = 'on'

        eff[key] = m

    # ── PASS B: PARENT ROLLDOWN (a hidden parent hides its whole subtree; locked parent locks it) ──
    #   Walk from each key up its parent chain; the STRICTEST ancestor state wins.
    #   strictness: hidden > locked > on. A hidden module ⇒ children hidden (can't expose a child of a
    #   hidden module). A locked module ⇒ children locked (unless already hidden). is_core children are
    #   exempt from a hidden rolldown (kept reachable), matching the status gate.
    STRICT = {'on': 0, 'locked': 1, 'hidden': 2}
    for key, meta in registry.items():
        strictest = eff[key]
        anc = meta['parent_key']
        while anc is not None and anc in registry:
            if STRICT[eff[anc]] > STRICT[strictest]:
                strictest = eff[anc]
            anc = registry[anc]['parent_key']
        if registry[key]['is_core'] and strictest == 'hidden':
            strictest = eff[key] if eff[key] != 'hidden' else 'on'   # core never rolled-down to hidden
        eff[key] = strictest

    return eff   # cached per-tenant, keyed by tenant_status.ent_version (a control write bumps version → recompute)


def mode_for(tenant_id, feature_key) -> str:
    # A feature NOT in the registry is UNGOVERNED → FAIL-CLOSED to 'hidden' (registry-drift safety).
    return resolve_modes(tenant_id).get(feature_key, 'hidden')


def assert_access(tenant_id, feature_key):
    m = mode_for(tenant_id, feature_key)
    if m == 'hidden':  raise HTTPException(404)                       # indistinguishable from "doesn't exist"
    if m == 'locked':  raise HTTPException(402, {'error':'locked',    # intentional upsell signal
                                                 'feature': feature_key, 'upgrade': True})
    # m == 'on' → return (proceed)


def effective_limits(tenant_id) -> dict:
    # plan_limits for the tenant's plan, with any per-tenant cap override layered on top
    # (the existing POST /tenants/{id}/limits writes these). Used by the run-loop / wallet gate.
    base = load_plan_limits(load_plan_id(tenant_id) or default_plan_id())
    return {**base, **load_tenant_limit_overrides(tenant_id)}
```

**Precedence summary (highest → lowest):** `status gate` ▸ `per-vendor override` ▸ `plan entitlement`
▸ `global default` ▸ then `parent rolldown` tightens ▸ unknown/missing ▸ **hidden**. `is_core` is a
floor that survives all of it (never hidden). This is the §2 rule in `spec-control-layer.md`, made
exact, with the rolldown and core-floor edge-cases pinned down.

---

## 3. API SURFACE — `/admin/*` (super-admin only) + `/me/entitlements` (vendor self-serve)

> All `/admin/*` share the **existing `is_admin` gate** (`403` for any vendor token, exactly like the
> live `/tenants`), `tenant_id` **token-derived never body**, and **every write is audited** via
> `audit.record(channel='control')`. Money/destructive writes (credits, status→disabled, impersonate)
> additionally require a **firewall step-up token** (`firewall.mint_step_up`/`verify_step_up_token`,
> sub-bound to the admin). When Logto lands, the gate tightens to **admin-org membership +
> `manage_tenants` scope**.

| Method & path | Purpose | Auth | Audited |
|---|---|---|---|
| `GET /admin/features` | Full `feature_registry` tree (catalog for the Feature-Flags + per-vendor UI). | admin | — |
| `GET /admin/flags` | Global `default_mode` per feature. | admin | — |
| `PUT /admin/flags/{feature_key}` `{mode}` | Set the GLOBAL baseline for a feature (all vendors). Bumps every tenant's `ent_version`. | admin | ✔ `set_flag` |
| `GET /admin/plans` | List plans + their entitlements + limits. | admin | — |
| `POST /admin/plans` `{plan_id,name,...}` | Create a plan. | admin | ✔ `plan_edit` |
| `PUT /admin/plans/{id}` `{entitlements[],limits[]}` | Edit plan bundle. Bumps `ent_version` of every tenant ON that plan. | admin | ✔ `plan_edit` |
| `DELETE /admin/plans/{id}` | Delete a non-default plan (reassign its tenants first). | admin | ✔ `plan_edit` |
| `GET /admin/vendors` | Vendor list: `{tenant_id,name,email,plan,status,created_at,usage_summary,health}` (joins `/usage/all` + last-activity). | admin | — |
| `GET /admin/vendors/{id}` | Full profile + **resolved entitlement map** (effective mode + provenance global/plan/override) + usage + health + wallet balance. | admin | — |
| `PUT /admin/vendors/{id}/entitlements/{feature_key}` `{mode,reason?}` | Per-vendor override (HIDE/LOCK/ON). Bumps that tenant's `ent_version`. | admin | ✔ `set_override` |
| `DELETE /admin/vendors/{id}/entitlements/{feature_key}` | Clear override → revert to plan/global. Bumps `ent_version`. | admin | ✔ `set_override` |
| `PUT /admin/vendors/{id}/plan` `{plan_id}` | Assign plan (writes plan_limits → existing caps). Bumps `ent_version`. | admin | ✔ `set_plan` |
| `PUT /admin/vendors/{id}/status` `{status,reason?}` | active/trial/suspended/disabled/expired. `disabled` needs step-up. Bumps `ent_version`. | admin (+step-up for disabled) | ✔ `set_status` |
| `PUT /admin/vendors/{id}/limits` | Per-tenant cap override (== existing `POST /tenants/{id}/limits`; surfaced in UI). | admin | ✔ `set_status` |
| `POST /admin/vendors/{id}/credits` `{amount,reason}` | Wallet top-up / freeze (→ `wallet.reserve/credit`). | admin + **step-up** | ✔ `credit_topup`/`credit_freeze` |
| `POST /admin/vendors/{id}/impersonate` | Mint short-TTL read-only `act_as=<tenant>`+`real_admin=<id>` token (see spec §8). | admin + **step-up** | ✔ `impersonate_start` + `_stop` |
| `GET /me/entitlements` | **Vendor-facing.** `{modes:{key:mode}, status, plan, version}` for the logged-in tenant. The vendor panel + AI Copilot both read THIS. | any authed tenant | — |

**Versioning of `/me/entitlements`:** the response carries `version` = `tenant_status.ent_version`.
The client stores it; on each poll/route-change/tab-focus it re-requests, and if `version` changed it
re-renders nav + re-gates the current page (bouncing on a downgrade-to-hidden of the current route).
Any control write bumps `ent_version`, which also invalidates the in-proc engine cache → the API denies
a revoked feature **immediately** even while a ≤30 s-stale client still shows it (UI lag only, never an
enforcement gap — the API is the boundary).

### Backend enforcement (the load-bearing half — ONE choke point, not per-route)
A FastAPI dependency/middleware maps `request.path → feature_key` via `feature_registry.api_prefixes`
(longest-prefix-wins), then calls `assert_access(tenant, key)`:
- `hidden` → **404** (no information leak — looks like the route doesn't exist).
- `locked` → **402** `{error:"locked", feature, upgrade:true}` (UI renders the LockOverlay).
- `on` → proceed.
- `is_core` paths (`/login`,`/me`,`/health`,`/settings`,`/wallet*` pay) **bypass** (anti-lockout).
- a path matching NO registry prefix → **pass** (ungoverned legacy route; CI registry-drift guard
  (spec §8.11) ensures every mounted prefix eventually has a row, closing this gap).
Behind `CONTROL_ENABLED` (default off) until smoke passes → resting state byte-identical.

---

## 4. HOW IT PLUGS INTO THE LIVE FRONTEND + BACKEND (minimal, surgical seams)

**Sidebar (`components/Sidebar/index.tsx::resolveNav`) — one orthogonal filter added next to `roles`.**
Each nav child gains an optional `feature_key`. A new `lib/entitlements.ts` (`useEntitlements()` →
loads `GET /me/entitlements` once, caches `localStorage['famit_ent']`, exposes `modeOf(key)`, polls +
refreshes on focus/route-change). `resolveNav` is extended so that for each surviving (by `roles`)
child it also checks `modeOf(child.feature_key)`:

```ts
// inside resolveNav, after the existing roles filter:
const m = child.feature_key ? modeOf(child.feature_key) : 'on';
if (m === 'hidden') return DROP_CHILD;          // exactly like an out-of-role child → vanishes from nav
if (m === 'locked') child = { ...child, locked: true };  // kept, flagged for the dimmed pill
// (a group with no surviving children is dropped, same as today)
```

- **HIDE** → child dropped from `list` (group auto-collapses if empty) — identical mechanism to the
  existing `roles` drop. Gone from nav, search, and (with the page-guard below) URL.
- **LOCK** → child rendered by `Sidebar/Dropdown` like the **existing `comingSoon` pattern** (dimmed,
  non-`<Link>`, a **"Locked"** pill instead of "Soon") → clicking routes to a `LockOverlay`. Zero new
  rendering machinery; reuse the proven dimmed-pill path.

**Page guard (cosmetic; the backend 404/402 is the real lock).** Each gated route calls
`assertEntitled(feature_key)` from `lib/entitlements`: `hidden` → redirect `/` (AuthGuard shape);
`locked` → render `components/LockOverlay` (a `Card`+blur+upsell, no interaction). Direct-URL/token/
devtools bypass is caught by the §3 middleware regardless.

**AI Copilot** reads the SAME `GET /me/entitlements` map and refuses any `hidden`/`locked` feature in
its tool/prompt layer ("Your plan does not include Billing") — closing the Copilot side-channel.

**Real-time:** poll `/me/entitlements` (20–30 s) + on route-change + on tab-focus; re-render on a
`version` change. Backend is already instant (cache invalidated by the `ent_version` bump). Optional
SSE/Hatchet push later for sub-second UX; not required for correctness.

---

## 5. RESTING-STATE / ROLLBACK (F2/F4 discipline)

- Ships **default-OFF** (`CONTROL_ENABLED=0`): with every tenant on the default plan + empty overrides
  + `status=active`, `resolve_modes` returns `on` for everything → behavior **byte-identical to today**.
- Migration on rollout: every existing tenant → `tenant_status(status='active', plan_id=default,
  ent_version=1)`, **zero** `tenant_entitlements` rows. No behavior change day one.
- Tables are additive/inert; rollback = restore `caller.py`/`.env` backups + restart (routes drop;
  tables harmless). Never touches the `agent.py` voice hot-loop — control is read at the API/run-gate
  layer only.
