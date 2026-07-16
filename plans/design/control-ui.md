# Super Admin Control Center — UI PORT MAP (Core_2 → famit-panel)

**Author:** Super Admin UI design agent · **Date:** 2026-06-10 · **Status: DESIGN ONLY** (no app code, no deploy, no git).
**Companion docs:** `design/spec-control-layer.md` (architecture/engine/API), `design/spec-core2-reuse-map.md` (the 6 archetypes).
This doc is the **screen-by-screen UI blueprint**: every Super-Admin page → the exact Core_2 template to port → the components
to assemble it from → the 3-state HIDE/LOCK/ON toggle UX → the vendor-side LockOverlay. Backend contract = `spec-control-layer.md §3–4`.

> **IRON UI RULE (founder, non-negotiable):** never invent UI from scratch. Every page below is a PORT of a *named* Core_2
> template (path cited) with our data rewired. famit-panel already ships every primitive needed — verified present under
> `FP/components/{Switch,Tabs,Badge,Card,Modal,Search,Select,Table,TableRow,Dropdown,NoFound,Button,Field,Layout,KpiCard,Sparkline}`
> + `FP/hooks/useSelection`. The ONLY net-new components are 3 thin assemblies (`EntitlementToggle`, `LockOverlay`, `StatusPill`)
> built FROM those primitives — not from scratch.

**Path keys:** `C2/` = `C:\Users\kunal\Desktop\Core_2-Capsy-Dashboard\extracted\core-2-dashboard-builder-react\`  ·
`FP/` = `C:\Users\kunal\Desktop\caps\famit-panel\`.

---

## 0. THE TWO SURFACES THIS WAVE DESIGNS

1. **Admin surface** — the Super-Admin Control Center: a new admin-only sidebar section + 8 pages. Visible ONLY to the
   founder/super-admin (gated `roles:"admin"` — the existing `Sidebar/resolveNav` already drops admin groups for vendors).
2. **Vendor surface** — what a normal tenant experiences when a feature is HIDE'd or LOCK'd: nav item removed (HIDE) or a
   premium locked overlay with upsell (LOCK). Both are PORTS of patterns already in the codebase.

The admin clicks a toggle in surface #1; surface #2 reflects it (backend is the real boundary — `spec-control-layer.md §3`).

---

## 1. ADMIN SIDEBAR SECTION (admin-only group) — PORT of the existing nav pattern

**Source pattern (already in our code):** `FP/contstants/navigation.tsx` collapsible-group shape +
`FP/components/Sidebar/Dropdown/index.tsx`. **Do NOT build new sidebar UI** — add ONE group object.

Add as the LAST group in `navigation.tsx`, every entry mirroring how `Foundation → Vendors` is gated `roles:"admin"`:

```ts
{
  title: "Super Admin",
  icon: "shield",                 // or "lock" — an existing Icon glyph; admin-distinct
  roles: "admin",                 // whole group hidden for every vendor (resolveNav drops it)
  list: [
    { title: "Control Overview", href: "/admin",          roles: "admin" },
    { title: "Vendors",          href: "/admin/vendors",   roles: "admin" },
    { title: "Feature Flags",    href: "/admin/flags",     roles: "admin" },
    { title: "Plans",            href: "/admin/plans",     roles: "admin" },
    { title: "Usage Analytics",  href: "/admin/usage",     roles: "admin" },
    { title: "Audit Logs",       href: "/admin/audit",     roles: "admin" },
    { title: "System Health",    href: "/admin/health",    roles: "admin" },
    { title: "Global Settings",  href: "/admin/settings",  roles: "admin" },
    { title: "Support",          href: "/admin/support",   roles: "admin" },
  ],
}
```

Why this works untouched: `resolveNav` (Sidebar/index.tsx:46) already (a) drops a whole group when `roles:"admin"` and the
user isn't admin, and (b) filters children by their own `roles`. A vendor literally never receives this group in their nav
tree. **Zero new sidebar component.** (The deeper admin↔Logto `manage_tenants` scope binding is `spec-control-layer.md §7.3`.)

---

## 2. ADMIN PAGES — PAGE → CORE_2 SOURCE → COMPONENTS → REWIRE

Routes live under `FP/app/admin/*`. Every page wraps `Layout title="…"`. Data from the `/admin/*` API (`spec-control-layer.md §4`).

### 2.1 Control Overview — `/admin/page.tsx`
- **Archetype:** Dashboard (fleet KPIs + recent feed).
- **Core_2 source:** `C2/templates/HomePage` (KPI strip + chart) + `C2/templates/Customers/OverviewPage` (stat cards).
- **Components to PORT:** `C2/templates/Products/OverviewPage/Overview` + `…/Overview/Item` (the metric-tile strip),
  `C2/components/CardChartPie`, `FP/components/Card`, `FP/components/Table`+`TableRow`, `FP/components/Sparkline`.
- **Rewire:** Overview/Item tiles = **# vendors · active · suspended · calls today · minutes · credits burned · open alerts**
  (from `GET /admin/vendors` aggregate). Chart card = fleet calls/minutes 30-day series. Recent list (`Table`+`TableRow`) =
  last 10 `control_audit` events (`GET /audit?channel=control`). Alert tiles use `Badge variant="danger"` for breaches.

### 2.2 Vendors list — `/admin/vendors/page.tsx`
- **Archetype:** List/Table with search + status tabs.
- **Core_2 source:** `C2/templates/Customers/CustomerList/CustomerListPage` (+ its `/List`). Header row =
  `title + Search isGray + Tabs + Button`. **This is the spec's `Customers → vendor list` mapping.**
- **Components:** `FP/components/Search` (isGray), `FP/components/Tabs` (status filter), `FP/components/Table`+`TableRow`,
  `FP/components/Badge` (status), `FP/hooks/useSelection` (optional bulk), `FP/components/NoFound` (empty/no-match),
  `FP/components/Dropdown` (mobile tab fallback — exactly as CustomerListPage:56).
- **Rewire:** rows from `GET /admin/vendors`. Columns: **Vendor (name+email) · Plan · Status (StatusPill) · Last active ·
  Calls(30d) · Minutes · Credits · →**. Status `Tabs` items = `All / Active / Trial / Suspended / Disabled / Expired`.
  `Search` filters name/email/phone. Row click → `/admin/vendors/[id]`. Reuse the existing `app/vendors/page.tsx` toast pattern
  for any inline action. (Our current `FP/app/vendors/page.tsx` already does create-form+table in Signal style — KEEP it,
  this `/admin/vendors` is the richer control list.)

### 2.3 Vendor Workspace — `/admin/vendors/[id]/page.tsx`  ⭐ THE CORE SCREEN
- **Archetype:** Two-pane (profile rail + tabbed detail body).
- **Core_2 source:** `C2/templates/Customers/CustomerList/DetailsPage` — the `card p-0 overflow-hidden` → left **`/Customer`**
  identity rail + right **`/Details`** tabbed body. **This is the spec's `DetailsPage → Vendor Workspace` mapping.**
- **Components:** left rail ports `C2/.../DetailsPage/Customer` (identity card) → vendor identity. Right body uses
  `FP/components/Tabs` for the 5 tabs + per-tab content below. Plus `FP/components/Badge`, `FP/components/Button`,
  `FP/components/Select` (status dropdown), `FP/components/Modal` (confirm suspend / credit top-up), `Overview/Item` tiles.
- **Left rail (identity + actions):** avatar/initial, **company · owner · email · phone · created · plan · status**,
  wallet/credit balance, and the **status control** (a `Select` or `Dropdown`: Active/Trial/Suspended/Disabled/Expired →
  `PUT /admin/vendors/{id}/status`, opens a `Modal` to capture `reason`, see §5). Plan re-assign `Select` →
  `PUT /admin/vendors/{id}/plan`. "Top-up credits" `Button isBlack` → `Modal` (firewall step-up, `spec §4`).
- **Right body — 5 Tabs (`FP/components/Tabs`):**
  | Tab | Core_2 sub-source | Content |
  |---|---|---|
  | **Overview** | `C2/templates/Customers/OverviewPage` stat cards + `DetailsPage/Details` block | profile recap + health (last login / last campaign / last call / last activity) as `Overview/Item`-style tiles |
  | **Usage** | `C2/templates/Products/OverviewPage/Overview` strip + `CardChartPie` | active leads/campaigns · calls · minutes · WhatsApp sends · billing/spend; from `/usage` + `/admin/vendors/{id}` |
  | **Permissions** | `C2/templates/SettingsPage/Menu` (sticky section list) + `FP/components/Switch` rows | **the entitlement matrix — see §3.** Every `feature_registry` item as an `EntitlementToggle` row |
  | **Billing** | `C2/templates/Income/EarningPage` (`Balance` tiles + `Transactions` table) | wallet balance, top-up history, plan limits vs usage |
  | **Audit** | `C2/templates/Notifications` feed OR `Table`+`TableRow` | this vendor's `control_audit` slice (`/audit?channel=control&tenant={id}`) |
- **Rewire:** `GET /admin/vendors/{id}` returns profile + **resolved entitlement map (effective mode + provenance)** + usage +
  health + wallet — one fetch feeds the whole workspace.

### 2.4 Feature Flags (GLOBAL) — `/admin/flags/page.tsx`
- **Archetype:** Section-form (sectioned card list of toggles).
- **Core_2 source:** `C2/templates/SettingsPage` (the `Menu` sticky nav + `react-scroll` `Element` sections of `Card`s).
  **This is the spec's `Settings/Menu+Switch → global toggles` mapping.**
- **Components:** `C2/templates/SettingsPage/Menu` (left section index = the module groups: Command/Grow/Sell/Engage/…),
  `FP/components/Card` per module section, and **`EntitlementToggle`** rows (§3) — but here writing the GLOBAL baseline.
- **Rewire:** grouped by `feature_registry.kind=module`; each feature row = a 3-state On/Lock/Hide setting the GLOBAL
  `default_mode` via `PUT /admin/flags/{feature_key}`. Core (`is_core`) rows render **On + disabled** (can't be hidden — the
  self-lockout floor, `spec §8.1`). A small caption per row: "applies to ALL vendors unless overridden".

### 2.5 Plans — `/admin/plans/page.tsx` (+ optional `/admin/plans/[id]`)
- **Archetype:** Pricing/tier cards + an editor form.
- **Core_2 source:** `C2/templates/UpgradeToProPage` (`Pricing` tier cards + `Faq`) for the plan GALLERY; editor form ports
  `C2/templates/Products/NewProductPage` section-form (left detail sections + right config rail). **Spec: `UpgradeToPro/NewProduct`.**
- **Components:** `C2/templates/UpgradeToProPage/Pricing` (tier cards), `FP/components/Card`, `FP/components/Field` (limit
  inputs), `FP/components/Switch`/`EntitlementToggle` (per-feature entitlement in the plan), `FP/components/Button`.
- **Rewire:** cards = **Trial / Plan A (Starter) / Plan B (Growth) / Enterprise** (`GET /admin/plans`). Editing a plan opens a
  NewProductPage-style form: left = **entitlement checkboxes/3-state per feature**, right rail = **usage limits**
  (`max_concurrency`, `daily_call_cap`, `monthly_minutes_cap`, `monthly_credits`, `seats`) as `Field` inputs →
  `POST/PUT /admin/plans/{id}`. Assigning a plan to a vendor happens in the Workspace rail (§2.3).

### 2.6 Usage Analytics — `/admin/usage/page.tsx`
- **Archetype:** Dashboard (chart-heavy executive view).
- **Core_2 source:** `C2/templates/Customers/OverviewPage` (`Overview` tabbed metric card, `TrafficСhannel`, `ActiveTimes`,
  `Countries`, `CardChartPie`) — Core_2's showpiece analytics cards. **Spec: `Overview → executive usage`.**
- **Components:** `C2/templates/Customers/OverviewPage/Overview` (+ `/Chart`, `/Item`), `FP/components/CardChartPie`,
  a per-vendor selector `FP/components/Select`, `FP/components/Table` for the per-vendor leaderboard.
- **Rewire:** executive metrics per vendor — **revenue / spend / leads / calls / conversions / active campaigns /
  last-activity** — from `/usage/all` + `/analytics`. A `Select` picks one vendor or "All vendors (fleet)".

### 2.7 Audit Logs — `/admin/audit/page.tsx`
- **Archetype:** Filterable feed.
- **Core_2 source:** `C2/templates/Notifications` (the `Tabs` + feed + right `Filter` rail; `Modal` filter on mobile).
  **Spec: `Notifications → audit feed`.** (Or a `Table`+`TableRow` variant for a denser ledger — both acceptable.)
- **Components:** `C2/templates/Notifications/Notification` (one row), `C2/templates/Notifications/Filter` (right rail:
  by vendor / action / date), `FP/components/Tabs` (Recent/Earlier), `FP/components/Modal` (mobile filter),
  `FP/components/Badge` (action type), `FP/components/Search`.
- **Rewire:** rows from `GET /audit?channel=control` — **who · action · target vendor · feature · old→new · reason · ts · ip**.
  Read-only (immutable `events` leg, `spec §8.9`). Filter rail = vendor `Select` + action `Select` + date `Range`.

### 2.8 System Health — `/admin/health/page.tsx`
- **Archetype:** Dashboard tiles + status table.
- **Core_2 source:** `C2/templates/HomePage` KPI tiles + `FP/components/Table`+`TableRow`.
- **Components:** `Overview/Item` tiles (service up/down, queue depth, error rate, latency), `Badge` (up=success/down=danger),
  `Sparkline` for trend.
- **Rewire:** service health from a health endpoint (`/health` + box metrics). Tiles = API/voice/DB/queue; table = per-service
  detail.

### 2.9 Global Settings — `/admin/settings/page.tsx`
- **Archetype:** Section-form.
- **Core_2 source:** `C2/templates/SettingsPage` in full (Menu + scroll sections).
- **Components:** `SettingsPage/Menu`, `Card` sections, `Field`, `Switch`, `Select`.
- **Rewire:** platform-wide defaults — default plan for new tenants, trial length, global rate caps, alert thresholds,
  feature-registry drift toggles. (`Support` `/admin/support` reuses the Audit/Notifications feed shape for ticket triage.)

---

## 3. THE 3-STATE PERMISSION CONTROL — `components/EntitlementToggle` (NEW assembly, not from scratch)

The founder's HIDE vs LOCK, per feature, as ONE reusable row. Used in: Workspace **Permissions** tab (per-vendor override),
**Feature Flags** (global default), and **Plans** editor (plan entitlement). Built ONLY from existing primitives.

**Built from:** `FP/components/Switch` (the rounded headless toggle, verified at `C2/components/Switch`), `FP/components/Badge`
(provenance pill), `FP/components/Tooltip`, `FP/components/Icon`, and a 3-segment button group styled like `FP/components/Tabs`
(the segmented pill row already in the kit — reuse its `border-s-stroke2 / text-t-primary` active style).

**Row anatomy (left→right):**
```
[feature label + kind chip]   [provenance pill]            [ On | Lock | Hide ]  segmented
 "Call Logs"  (page)           global · plan A · override    ▲ 3-state segmented control
```
- **Provenance pill** (`Badge`): `neutral` "global" / `info` "Plan A" / `warning` "override" — tells the admin WHERE the
  current effective mode comes from (the resolution chain, `spec §2 resolution rule`). An explicit per-vendor row shows
  "override" + a tiny **Reset** (`Button isStroke`) → `DELETE /admin/vendors/{id}/entitlements/{key}` (revert to plan/global).
- **3-state segmented control** (styled like `Tabs`, 3 items):
  - **On** — green active (`pill-success` accent / `--primary-02`). Feature fully available.
  - **Lock** — amber active (`pill-warning` / `--primary-03`), a small lock `Icon`. Visible-but-locked (upsell overlay).
  - **Hide** — grey active (`pill-neutral`). Gone everywhere.
  Implementation note: 3-state ≠ a boolean `Switch`, so the **segmented group is the primary control**; `Switch` is reused
  only for plain on/off limit toggles elsewhere. (Keeping `Switch` in the kit honors "reuse"; the segmented row is the
  minimal new assembly the 3-state requirement forces.)
- **Write:** `PUT /admin/vendors/{id}/entitlements/{key}` body `mode=on|locked|hidden` (+ optional `reason`). **Optimistic
  update** + a toast on failure (reuse the toast pattern already in `FP/app/vendors/page.tsx`). On success the provenance pill
  flips to "override".
- **Core rows** (`is_core`: login/settings/billing-pay): render the segmented control with Lock/Hide **disabled** + a tooltip
  "Core feature — cannot be hidden" (the self-lockout floor, `spec §8.1`).
- **Hierarchy:** rows are grouped by module via the `SettingsPage/Menu` section index; a `hidden` parent module visually
  dims+disables its child rows (parent-rolldown, `spec §2 resolution rule` step 5) with a caption "hidden by parent module".

**Layout host:** the matrix sits in a `Card` per module, with the `SettingsPage/Menu` sticky left index for fast jump —
i.e. it literally IS the SettingsPage archetype with `EntitlementToggle` rows instead of profile fields.

---

## 4. VENDOR-SIDE EXPERIENCE — HIDE removes nav, LOCK shows a premium overlay

What the NON-admin tenant sees. Driven by `GET /me/entitlements` (`spec §4`) via a new `FP/lib/entitlements.ts`
(`useEntitlements()` / `modeOf(key)`, mirrors `FP/lib/auth.ts`; polls per `spec §6` for real-time). **Frontend is cosmetic —
the backend 404/402 is the real lock (`spec §3, §9.1`).**

### 4.1 HIDE = nav item removed (PORT of resolveNav, one filter added)
- **Source:** `FP/components/Sidebar/index.tsx` `resolveNav` (line 46) — it ALREADY filters children and drops empty groups by
  `roles`. **Add a parallel entitlement filter:** a child whose `feature_key` resolves to `hidden` is dropped exactly like an
  out-of-role child. Conceptually a one-line addition to a tested function — no new component.
- A direct URL hit on a hidden route: the page calls `assertEntitled(key)` from `lib/entitlements`; `hidden` → redirect to `/`
  (same shape as the existing `AuthGuard` in `FP/app/providers.tsx`). The BACKEND returns **404** regardless (`spec §3`).

### 4.2 LOCK in nav = dimmed "Locked" pill (PORT of the existing `comingSoon` pattern — already in our code)
- **Source:** `FP/components/Sidebar/Dropdown/index.tsx` lines **77–87** — the `comingSoon` branch ALREADY renders a child as a
  dimmed, non-`<Link>` row with a "Soon" pill (`nav-soon`). **A `locked` child reuses this exact branch**, swapping the label
  to a **"Locked"** pill (a `Badge variant="warning"` or a `nav-locked` sibling utility of `nav-soon`). Zero new mechanism —
  the dimmed-non-link pattern the founder wants for LOCK is already shipped for `comingSoon`.

### 4.3 LOCK on a page = `components/LockOverlay` (NEW assembly from `Modal`/`Card` styles — the upsell overlay)
- **Founder ask:** "visible but a disabled overlay with upsell messaging ('Should I pay for this?'), no interaction."
- **Built from:** `FP/components/Card` (the panel), `FP/components/Modal` styles (`bg-shade-04/90` backdrop + `shadow-depth`
  rounded-3xl panel — copy the `Modal` `DialogPanel` look without trapping focus so the page chrome shows through blurred),
  `FP/components/Button` (`isBlack` "Upgrade" CTA), `FP/components/Badge`, `FP/components/Icon` (lock glyph).
- **Behavior:** renders the real page component **blurred + `pointer-events-none`** behind a centered upsell `Card`:
  lock icon · headline ("This feature is locked") · sub ("Upgrade your plan to unlock Call Logs") · **Upgrade** `Button isBlack`
  → routes to the vendor's plan page · a secondary "Contact us" `Button isStroke`. The premium curiosity/upsell the spec wants
  (`spec §5 Page LOCK overlay`, `spec-control-layer.md` HIDE-vs-LOCK §0.3). NO interaction reaches the page beneath.
- **Page wiring:** each gated page reads `modeOf(key)`: `on` → render normally; `locked` → wrap in `<LockOverlay feature=…>`;
  `hidden` → redirect (§4.1). The server still 402s the underlying API so even a devtools-removed overlay yields no data.

### 4.4 AI Copilot honors the SAME map
- The Copilot calls `GET /me/entitlements` and refuses hidden/locked features in its tool/prompt layer with the upsell line
  ("Your plan doesn't include Billing — want to upgrade?"). UI-wise it surfaces the same `LockOverlay` copy. (`spec §8.6`,
  build unit C10.)

---

## 5. STATUS / SUSPENSION CONTROL — `components/StatusPill` + Select + confirm Modal

- **StatusPill** (NEW, trivial — just a `Badge` map): `active→success · trial→info · suspended→warning · disabled→danger ·
  expired→neutral`. Used in the vendor list (§2.2) and workspace rail (§2.3).
- **The control** (workspace rail): a `FP/components/Select` (or `Dropdown`) of the 5 statuses → on change opens a
  `FP/components/Modal` capturing a **reason** (required for suspend/disable) → `PUT /admin/vendors/{id}/status`. Suspended/
  Disabled = vendor can't login/call/create but **data preserved** (`spec §8.2` — in-flight calls finish, new dials gated).
  Both the change and reason are audited (`control` channel).

---

## 6. NET-NEW COMPONENTS (the ONLY new files — all assemblies of existing primitives)

| New file | Built from (existing) | Purpose |
|---|---|---|
| `FP/components/EntitlementToggle/index.tsx` | `Switch` + `Badge` + `Tooltip` + `Icon` + Tabs-style segmented buttons | the 3-state On/Lock/Hide row (§3) |
| `FP/components/LockOverlay/index.tsx` | `Card` + `Modal` styles + `Button` + `Badge` + `Icon` | vendor page LOCK upsell overlay (§4.3) |
| `FP/components/StatusPill/index.tsx` | `Badge` (variant map) | vendor status pill (§5) |
| `FP/lib/entitlements.ts` | mirrors `FP/lib/auth.ts` (fetch+cache+poll) | `useEntitlements()` / `modeOf(key)` / `assertEntitled(key)` (§4) |

Everything else is a **straight port** of a named Core_2 template with our data rewired. No other new UI primitives.

---

## 7. PAGE LIST (the deliverable index)

| # | Admin page | Route | Core_2 template ported | Key components |
|---|---|---|---|---|
| 1 | Sidebar "Super Admin" group | (nav) | `navigation.tsx` group + `Sidebar/Dropdown` | resolveNav (`roles:"admin"`) |
| 2 | Control Overview | `/admin` | `HomePage` + `Customers/OverviewPage` | Overview/Item, CardChartPie, Table, Sparkline |
| 3 | Vendors list | `/admin/vendors` | `Customers/CustomerList/CustomerListPage` | Search, Tabs, Table/TableRow, Badge, NoFound |
| 4 | Vendor Workspace | `/admin/vendors/[id]` | `Customers/CustomerList/DetailsPage` (Customer+Details) | Tabs, Select, Modal, Overview/Item, EntitlementToggle |
| 5 | Feature Flags (global) | `/admin/flags` | `SettingsPage` (Menu + sections) | SettingsPage/Menu, Card, EntitlementToggle |
| 6 | Plans | `/admin/plans` | `UpgradeToProPage/Pricing` + `Products/NewProductPage` | Pricing cards, Field, Switch, EntitlementToggle |
| 7 | Usage Analytics | `/admin/usage` | `Customers/OverviewPage` (Traffic/ActiveTimes/Countries) | Overview/Chart/Item, CardChartPie, Select, Table |
| 8 | Audit Logs | `/admin/audit` | `Notifications` (feed + Filter) | Notification, Filter, Tabs, Modal, Badge, Search |
| 9 | System Health | `/admin/health` | `HomePage` tiles + Table | Overview/Item, Badge, Sparkline, Table |
| 10 | Global Settings (+ Support) | `/admin/settings` (`/admin/support`) | `SettingsPage` full (Support = Notifications feed) | Menu, Card, Field, Switch, Select |

**Vendor-side (surface #2):**
| Item | Source ported | Note |
|---|---|---|
| HIDE nav removal | `Sidebar/resolveNav` + entitlement filter | one filter added to a tested fn |
| LOCK nav pill | `Sidebar/Dropdown` comingSoon branch (lines 77–87) | reuse → "Locked" pill |
| LOCK page overlay | `components/LockOverlay` from `Card`+`Modal` | blurred page + upsell CTA |
| HIDE direct-URL | `lib/entitlements.assertEntitled` + `AuthGuard` shape | redirect; backend 404 is the real lock |

---

## 8. BUILD-ORDER NOTE (for the later code wave — this wave writes design only)

Matches `spec-control-layer.md §10` frontend units: **C6** lands the shared plumbing FIRST and ALONE (`lib/entitlements.ts`,
`Sidebar/resolveNav` filter, `LockOverlay`, `StatusPill`) — it touches the shared Sidebar/lib. Then **C7** (Vendors list +
Workspace), **C8** (Permissions tab + `EntitlementToggle`), **C9** (Flags + Plans + Usage + Audit — partitionable across 2
agents by page, never same file). Per-page verify = `npm run build` exit 0 + visual diff vs the ported Core_2 template,
dark+light. Backend (`/admin/*`, enforcement middleware) is the load-bearing half and lands per `spec §10 C0–C5` — **HIDE/LOCK
are theatre without it.**
