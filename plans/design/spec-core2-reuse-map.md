# Core_2 REUSE MAP + UI-OVERHAUL PLAN — famit-panel

**Author:** Core_2 reuse-map planner agent · **Date:** 2026-06-10
**Iron rule:** NEVER invent UI from scratch. Port Core_2's ACTUAL JSX/Tailwind page
templates + components and only rewire our data/props. Approximating ≠ reusing.

Design source of truth (CODE, readable):
`C:\Users\kunal\Desktop\Core_2-Capsy-Dashboard\extracted\core-2-dashboard-builder-react`
(abbreviated below as **C2/**). Our app: `C:\Users\kunal\Desktop\caps\famit-panel`
(abbreviated **FP/**).

---

## 0. ROOT-CAUSE DIAGNOSIS (why the founder says "looks bad / doesn't match")

famit-panel **IS** the Core_2 Capsy template — and the WHOLE component library is
already ported under `FP/components/*` (verified: Card, Table, TableRow, Tabs,
Search, Select, Dropdown, NoFound, Modal, Filters, Switch, Range, Percentage,
NewCustomers, RefundRequests, PopularProducts, CardChartPie + `hooks/useSelection`
+ all `mocks/*`). The shell (Layout/Sidebar/Header/Logo/Button/Field/Icon) is also
Core_2-derived.

**The problem is the PAGES, not the kit.** Two prior "premium UI" waves rebuilt
each page with BESPOKE structures that DO NOT EXIST in Core_2:
- `components/PageHeader` (`.page-head` masthead) — **not a Core_2 pattern**.
- `components/KpiCard` + hand-rolled hero KPI grids (`grid grid-cols-4 … <KpiCard>`)
  — **not a Core_2 pattern**.
- Raw `<table className="data-table">` with custom `<thead>/<tbody>` — **bypasses**
  Core_2's `Table`/`TableRow` components.
- `.state-block` empty states — **bypasses** Core_2's `NoFound`.
- Bespoke segmented filters (`SegBtn`) + ad-hoc search `<input>` — **bypasses**
  Core_2's `Tabs` + `Search` + `Dropdown` chrome.

So every page is a from-scratch lookalike sitting on top of the real kit. That is
exactly the "from-scratch looks bad / doesn't match" the founder rejects. **The fix
is mechanical: replace the bespoke page bodies with Core_2's real template
structures (which are already importable), keeping our `lib/api` data wiring.**

### THE 6 CANONICAL CORE_2 PAGE ARCHETYPES (every FP page maps to one)
1. **Dashboard archetype** — `Layout` + `flex max-lg:block` → `col-left` /
   `col-right`; left = `Overview` tabbed-metric `Card` + chart cards; right =
   `PopularProducts`/`RefundRequests`-style list cards. Source: `C2/templates/HomePage`,
   `C2/templates/Customers/OverviewPage`, `C2/templates/Income/EarningPage`.
2. **List/Table archetype** — single `card` whose head row is
   `[title] + <Search isGray> + <Tabs>/<Dropdown> + <Button isBlack>`, body is
   `<Table cellsThead=…><TableRow>…` with `useSelection` for bulk + `NoFound` when
   empty. Source: `C2/templates/Income/StatementsPage/Transactions`,
   `C2/templates/Customers/CustomerList/CustomerListPage`,
   `C2/templates/Products/OverviewPage/Products`.
3. **Overview+Table archetype** (KPI strip ON TOP of a table) — `Overview` card
   (horizontal scroll of `Item` metric tiles via `C2/templates/Products/OverviewPage/Overview`)
   then the List archetype below. Source: `C2/templates/Products/OverviewPage`.
4. **Two-pane archetype** (list rail + detail) — `card p-0 overflow-hidden` →
   left search+rows rail, right `Details` pane. Source: `C2/templates/MessagesPage`
   (+ `C2/templates/Customers/CustomerList/DetailsPage` for a record detail).
5. **Section-form archetype** (left sticky menu + anchored sections) —
   `Menu` + `react-scroll` `Element` sections of `Card`s. Source:
   `C2/templates/SettingsPage`; multi-column creator form
   `C2/templates/Products/NewProductPage`.
6. **Pricing/Plan archetype** — centered `card` with `Pricing` toggle + tier cards
   + `Faq`. Source: `C2/templates/UpgradeToProPage`.

**Rewire rule for ALL pages:** keep `Layout title=…` and our `lib/api` fetches +
`lib/auth` RBAC + `lib/badges`. REPLACE the bespoke body with the archetype JSX.
Map our status/score/outcome → Core_2's `label label-green/-yellow/-red` OR keep
`lib/badges` `<Badge>` (already token-clean — acceptable). Swap fake KPI hero grids
for the real `Overview`/`Item` metric-tile card. Swap `data-table` for `Table`+
`TableRow`. Swap `state-block` for `NoFound`. Swap `SegBtn`/ad-hoc input for
`Tabs`+`Search`. DROP `PageHeader` (use the `card` head row title like Core_2 does)
OR keep it as a thin masthead — but the IN-CARD chrome must become Core_2's.

---

## 1. SHARED SHELL MAPPING (do FIRST — lifts every page at once)

| Shell piece | Core_2 source | FP target | Rewire notes |
|---|---|---|---|
| App frame | `C2/components/Layout` | `FP/components/Layout` (already ported) | Keep. Ensure pages use `Layout`'s `col-left`/`col-right`/`center-with-sidebar` globals, not custom grids. |
| Sidebar | `C2/components/Sidebar` (+ `Sidebar/Dropdown`) | `FP/components/Sidebar` | Keep our `contstants/navigation.tsx` 8-section IA. Verify group expand/`comingSoon`/role-gating match C2 Dropdown behavior. |
| Header | `C2/components/Header` (+ `User`) | `FP/components/Header` | Already stripped of dead template links. Keep the "Run a Campaign" primary + ThemeButton. |
| Logo / wordmark | `C2/components/Logo` | `FP/components/Logo` | Keep token wordmark; ensure Gilroy applies. |
| **Card** (the #1 reuse) | `C2/components/Card` — `title` + `headContent` + `selectOptions` | `FP/components/Card` | THE wrapper for nearly every block. Head row = title + `headContent` (Tabs/Search/Button) + optional `Select`. Pages must wrap content in this, not hand-rolled card divs. |
| Button | `C2/components/Button` (`isBlack/isWhite/isGray/isStroke/isCircle`) | `FP/components/Button` | Keep. Use `isBlack` for primary, `isStroke` for secondary, `isCircle`+`icon` for icon buttons — STOP hand-rolling `<button className=…>`. |
| **Table + TableRow** | `C2/components/Table`, `C2/components/TableRow` | `FP/components/Table`, `FP/components/TableRow` | REPLACE every `<table className="data-table">`. `cellsThead` = `tableHead.map(h=><th>)`; rows = `<TableRow>` (gives hover lift, checkbox col, responsive hide classes). |
| Tabs (segmented) | `C2/components/Tabs` | `FP/components/Tabs` | REPLACE bespoke `SegBtn`. Use for All/Hot, status filters, time ranges. Pair with `Dropdown` for mobile. |
| Search | `C2/components/Search` (`isGray`) | `FP/components/Search` | REPLACE ad-hoc search `<input>`s in card heads. |
| Select / Dropdown | `C2/components/Select`, `C2/components/Dropdown` | `FP/components/Select`,`/Dropdown` | Period pickers, mobile tab fallback. |
| Empty state | `C2/components/NoFound` | `FP/components/NoFound` | REPLACE `.state-block`. (Add an icon prop if richer empties wanted, but reuse the component.) |
| Badges/labels | C2 `.label label-green/-yellow/-red` (e.g. in `…/StatementsPage/Transactions`) | `FP/lib/badges` + `FP/components/Badge` | Already token-clean & centralized — KEEP. Ensure all pages route through it (no raw bg-green-100). |
| Modal | `C2/components/Modal` | `FP/components/Modal` | Use for call-detail / record-detail / confirm — replace hand-rolled overlays. |
| Filters | `C2/components/Filters` (Modal+Select+Range+Switch) | `FP/components/Filters` | Reuse for any advanced-filter popover (leads, calls, billing explorer). |
| Bulk select | `C2/hooks/useSelection` | `FP/hooks/useSelection` | Wire into list pages for select-all + `DeleteItems` bulk bar (campaigns, leads, suppression). |
| KPI metric tile | `C2/templates/Products/OverviewPage/Overview` + `…/Overview/Item`; `C2/templates/HomePage/Overview` (tabbed) | (port as `FP/components/Overview` + `Item`) | THE replacement for `KpiCard` hero grids. Horizontal metric strip inside a `Card`, real numbers + `Percentage`. |

**Font:** install Gilroy via `next/font/local` (from `D:\Downloads\gilroy-font.zip`)
in `FP/app/layout.tsx`, set as app-wide default — independent of this map but
required for the "match" the founder wants.

---

## 2. PER-PAGE REUSE MAP

Format: **FP page** → archetype → **Core_2 source template(s) + components** → rewire notes.

### Command
- **`FP/app/page.tsx` (Dashboard)** → Dashboard archetype →
  `C2/templates/HomePage` (+ `HomePage/Overview` tabbed metric card, `HomePage/OverviewSlider`)
  and `C2/templates/Customers/OverviewPage` (for the chart-card right rail).
  **Rewire:** left `col-left` = `Overview` tabbed card (tab1 Calls, tab2 Answer-rate)
  fed by `getStats()`; chart card = our recharts area on `stats.series`; right
  `col-right` = a `PopularProducts`-shaped "Hot Leads" list card (`getLeads({hot})`)
  + a `RefundRequests`-shaped "Recent Calls" list. DROP the bespoke `kpi` hero
  grid + `KpiCard` row → use C2 `Overview/Item` metric strip. Keep recent-calls as
  `Table`+`TableRow`, not `data-table`.
- **`FP/app/ai-manager/page.tsx`** → Overview+Table OR Dashboard archetype →
  `C2/templates/Products/OverviewPage` (Overview strip + activity) + `…/HomePage/Comments`
  for an AI-activity feed. **Rewire:** Overview tiles = model/agent health; feed =
  AI decisions/escalations from our API; wrap in `Card`.

### Grow
- **`FP/app/campaigns/page.tsx`** → List/Table archetype →
  `C2/templates/Customers/CustomerList/CustomerListPage` (head: title+Search+Tabs+
  bulk bar via `useSelection`+`DeleteItems`) + `C2/…/Products` for status tabs.
  **Rewire:** rows from `getCampaigns()`; status → `label`/`Badge`; "Create
  Campaign" → `Button isBlack` opening a `Modal` (or the New-Product section-form
  for a richer builder). Replace current `data-table`+`state-block`.
- **`FP/app/ads/page.tsx`** → Dashboard archetype → `C2/templates/PromotePage`
  (`Insights` KPI band + `List` of posts/campaigns + `Engagement`/`Interactions`
  side cards). **Rewire:** Promote's social-post list → ad-campaign list; Insights
  tiles → spend/impressions/ROAS; gate writes by `canWrite`. (Backend ads is
  founder-blocked → keep read/empty states via `NoFound`.)
- **`FP/app/funnels/page.tsx`** → Overview+Table / Dashboard →
  `C2/templates/PromotePage` (`Insights`+`Interactions`) or `Customers/OverviewPage`
  (`TrafficСhannel` + funnel-ish bars). **Rewire:** funnel stages = our funnel API;
  reuse `ProgressBar`/`Legend` from `C2/…/Products/ProductsStatistics`.
- **`FP/app/forms/page.tsx` + `forms/[id]/page.tsx`** → List + Section-form →
  list via `Customers/CustomerList/CustomerListPage`; builder via
  `C2/templates/Products/NewProductPage` (multi-section: `ProductDetails`/`Price`/
  `Highlights` → form-meta/fields/CTA) using `FP/components/Field`,`Editor`,`Select`.
  **Rewire:** form list rows + per-form section editor; submissions table = `Table`.

### Sell
- **`FP/app/leads/page.tsx`** → Overview+Table archetype →
  Overview strip from `C2/templates/Products/OverviewPage/Overview` (+`Item`) for
  Total/Hot/Avg-score/Contacted; list from `Customers/CustomerList/CustomerListPage`
  (Search + `Tabs` All/Hot + `useSelection` bulk + `NoFound`). **Rewire:** REPLACE
  the bespoke 4×`KpiCard` grid with C2 `Overview/Item` tiles; REPLACE `SegBtn` with
  `Tabs`; REPLACE search `<input>` with `Search isGray`; REPLACE `data-table` with
  `Table`+`TableRow`; REPLACE `state-block` with `NoFound`. Keep `addLeads`
  CSV/paste panel but reuse `C2/components/FieldFiles`/`FieldImage` dropzone styling.
- **`FP/app/crm/page.tsx` + `crm/[id]/page.tsx`** → Two-pane + record-detail →
  list/360 via `C2/templates/Customers/OverviewPage`; record via
  `C2/templates/Customers/CustomerList/DetailsPage` (`Customer` header +
  `Details/Contacts` + `Details/PurchaseHistory`). **Rewire:** map purchase-history
  → call/interaction history; contacts → lead contact block; reuse `Message`/`Chat`
  from `MessagesPage` if a conversation thread is shown.

### Engage
- **`FP/app/run/page.tsx`** → Section-form archetype →
  `C2/templates/Products/NewProductPage` (two-column: left detail sections, right
  config rail). **Rewire:** left = campaign/script select + audience source
  (`FieldFiles` CSV/Excel dropzone, lead-type filter via `Select`/`Tabs`, manual
  multi-select via `useSelection` table); right rail = run config (concurrency,
  schedule via `DateAndTime`, voice `Select`) + a `Button isBlack` "Start run". This
  is the founder's explicit "multi-card scrollable, CSV+Excel upload, filter by
  file / lead-type / manual select, beautiful dropdown" ask → it IS NewProductPage.
- **`FP/app/calls/page.tsx` (Call Logs)** → Overview+Table archetype →
  Overview strip (`Products/OverviewPage/Overview`) + list
  (`Income/StatementsPage/Transactions` is the closest table w/ download + period
  Select). Detail = `C2/components/Modal`. **Rewire:** KPI strip = total/answered/
  avg-duration/cost from `getStats`+`getCalls`; `Table`+`TableRow` rows; period
  `Select`; "Export" `Button isBlack`; call-detail `Modal` (transcript bubbles reuse
  `MessagesPage/Details/Chat`).
- **`FP/app/callbacks/page.tsx`** → List/Table → `Customers/CustomerList/CustomerListPage`.
  **Rewire:** scheduled-callback rows + `Tabs` (pending/done) + `NoFound`.
- **`FP/app/whatsapp/page.tsx`** → Two-pane archetype → `C2/templates/MessagesPage`
  (`Message` rail + `Details/Chat`). **Rewire:** chats list + thread; template/
  broadcast composer = `Card`+`Field`+`Editor`. (Backend dormant → `NoFound` empty.)
- **`FP/app/support/page.tsx`** → Two-pane OR Overview+Table →
  `C2/templates/MessagesPage` (ticket rail + thread `Chat`) with an Overview KPI
  strip. **Rewire:** tickets list → `Message`-style rows; thread bubbles =
  `Details/Chat`; SLA/queue tiles = `Overview/Item`. Replace current
  `data-table is-clickable`.
- **`FP/app/booking/page.tsx`** → List/Table OR Dashboard →
  `Customers/CustomerList/CustomerListPage` for the bookings table +
  `C2/components/DateAndTime` for the slot picker. **Rewire:** bookings rows +
  status `Tabs` + a "New booking" `Modal`.

### Automate
- **`FP/app/workflows/page.tsx`** → List/Table (catalog) + node editor →
  catalog via `Customers/CustomerList/CustomerListPage`; node builder = React Flow
  (Flowaxon style) — NOT in Core_2, build with React Flow but wrap chrome
  (`Card`/`Button`/`Modal`/side `Select` config) from Core_2. **Rewire:** workflow
  list rows + enable `Switch`; "New workflow" → React Flow canvas page.
- **`FP/app/webhooks/page.tsx`** → List/Table → `Customers/CustomerList/CustomerListPage`.
  **Rewire:** endpoint rows + status `label`; "Add endpoint" `Modal` w/ `Field`;
  delivery log = second `Table`.

### Money
- **`FP/app/payments/page.tsx`** → Overview+Table OR Pricing →
  `C2/templates/Income/EarningPage` (Balance tiles + `Transactions` table +
  `RecentEarnings`). **Rewire:** balance/MTD tiles = `EarningPage/Balance`;
  transactions = `Income/StatementsPage/Transactions` table. (Payments backend
  founder-blocked → `NoFound`.)
- **`FP/app/billing/overview/page.tsx`** → Dashboard/Overview →
  `C2/templates/Income/EarningPage` (Balance + Countries → vendor split) +
  `Customers/OverviewPage` cards. **Rewire:** grand-total/MTD = `Balance/Item`
  tiles; per-vendor cards = `Countries`/`PopularProducts` list shape. Keep
  `_shared.tsx` `BillingHeader` but make its tab strip use `Tabs`.
- **`FP/app/billing/vendors/page.tsx` + `vendors/[id]/page.tsx`** → List + detail →
  `Customers/CustomerList/CustomerListPage` (vendor list) + `…/DetailsPage` (vendor
  detail w/ usage history table). **Rewire:** vendor rows + cost `label`; detail =
  `Statistics` + `Transactions`-style cost log.
- **`FP/app/billing/explorer/page.tsx` (Cost Explorer)** → Overview+chart →
  `C2/components/CardChartPie` + `Income/EarningPage` charts + `Filters` popover.
  **Rewire:** cost breakdown pie + time series; `Filters` (Modal+Select+Range) for
  vendor/date.
- **`FP/app/billing/audit/page.tsx`** → List/Table →
  `Income/StatementsPage/Transactions`. **Rewire:** immutable audit rows + period
  `Select` + `Search`; `NoFound` empty.
- **`FP/app/billing/plan/page.tsx` (Plan & Ledger)** → Pricing + Table →
  `C2/templates/UpgradeToProPage` (`Pricing` tiers + `Faq`) for plan; ledger =
  `Transactions` table. **Rewire:** current-plan card + tier toggle; ledger rows
  from wallet API.

### Intelligence
- **`FP/app/analytics/page.tsx`** → Dashboard archetype (chart-heavy) →
  `C2/templates/Customers/OverviewPage` (`TrafficСhannel`, `ActiveTimes`,
  `Countries`, `CardChartPie` Devices/Gender) + `Products/OverviewPage/ProductActivity`.
  **Rewire:** funnel = `ProductsStatistics/ProgressBar` (already recolored
  brand-blue — keep); channel/time/geo cards map 1:1 to our analytics API. This is
  the single biggest "look" win — Core_2's analytics cards are its showpiece.

### Foundation
- **`FP/app/suppression/page.tsx` (Do-Not-Call)** → List/Table →
  `Customers/CustomerList/CustomerListPage` (+ `useSelection`+`DeleteItems` for bulk
  remove). **Rewire:** suppressed-number rows + `Search` + "Add" `Modal` + `NoFound`.
- **`FP/app/vendors/page.tsx` (Admin Vendors)** → List/Table →
  `Customers/CustomerList/CustomerListPage`. **Rewire:** vendor/key rows + status
  `Switch` + admin-gated `Button isBlack`.
- **`FP/app/settings/page.tsx`** → Section-form archetype →
  `C2/templates/SettingsPage` EXACTLY (`Menu` sticky nav + `react-scroll` `Element`
  sections: ProfileInformation/YourShop→Org/Password/Notifications/Payment).
  **Rewire:** map sections to Account/Org/Security/Notifications/Billing; reuse
  `FP/components/Field`,`Switch`,`Select`. Replace current flat `Card` stack.
- **`FP/app/login/page.tsx`** → `C2/components/Login` (`SignIn`/`CreateAccount`/
  `ResetPassword`). **Rewire:** keep our `login()` logic; adopt C2 Login split
  layout + `Field` inputs. (Already partly done — align to C2 `Login` structure.)

---

## 3. EXECUTION ORDER (highest-impact first, shell before pages)

1. **Shell + font** (Section 1): Gilroy via next/font/local; confirm Card/Table/
   TableRow/Tabs/Search/NoFound/Select are the ONLY chrome pages use. Port
   `Overview`+`Item` metric-tile component from `C2/templates/Products/OverviewPage/Overview`.
2. **Analytics** (showpiece — biggest visual delta, Core_2's strongest cards).
3. **Dashboard** (most-seen; swap KPI hero grid → C2 Overview strip + col-left/right).
4. **Leads** (Overview+Table; kill `KpiCard`/`SegBtn`/`data-table`/`state-block`).
5. **Run** (NewProductPage section-form — the founder's named upgrade ask).
6. Then sweep remaining List/Table pages (campaigns, calls, callbacks, suppression,
   vendors, webhooks, billing/*) — they all share ONE archetype, so do them as a
   batch once the List pattern is locked.

**Per-page verify:** `npx tsc --noEmit` + `next build` EXIT 0; visual diff vs the
Core_2 template it was ported from; dark+light. Commit per page (branch
`feat/premium-ui`). NON-BREAKING: zero `lib/api`/route/handler change.
