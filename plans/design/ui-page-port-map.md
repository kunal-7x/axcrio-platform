# UI Page-Port Map — famit-panel → core-2-dashboard-builder-react

READ-ONLY DESIGN. This is the authoritative page-by-page port plan. For EVERY
famit-panel route it names the EXACT reference page/template to port, the action
class, and the data to swap in. Build wave executes this verbatim — do NOT
hand-build lookalikes.

- OUR APP: `C:\Users\kunal\Desktop\caps\famit-panel` (pages `app/*`, shell
  `components/*`, tokens `app/globals.css`, nav `contstants/navigation.tsx`).
- REFERENCE (authoritative look): `C:\Users\kunal\Desktop\core-2-dashboard-builder-react`
  (pages `app/*` thin wrappers → `templates/*`, components `components/*`,
  mocks `mocks/*`, types `types/*`, hooks `hooks/*`).

---

## 0. GLOBAL FIXES (apply once, before any page) — founder's three complaints

### 0.1 FONT — the real reason "it didn't change" (HIGH PRIORITY)
- **The reference font is `Inter Display`, NOT Gilroy.** Reference loads 5 weights
  via `next/font/local` (`app/layout.tsx`): `InterDisplay-{Light300,Regular400,
  Medium500,SemiBold600,Bold700}.woff2`, exposed as `--font-inter-display`, body
  class `font-inter`. The type scale (`globals.css` `--text-h1..h6--font-weight`)
  uses weights 300–700.
- **Our bug:** `famit-panel/app/layout.tsx:33-50` ALSO loads `Gilroy` (`--font-gilroy`)
  — but Gilroy free ships only Light(300)+ExtraBold(800). Every 400/500/600/700
  text has no Gilroy weight, so it falls back → looks like Inter → founder sees
  "no change," and anything forced to Gilroy 800 looks heavy/wrong.
- **FIX (visible + correct):** DROP Gilroy entirely. Standardize app-wide on
  Inter Display (the reference's font). Our `famit-panel` already has the 5
  `InterDisplay-*.woff2` loaded — just remove the `gilroy` localFont block + the
  `${gilroy.variable}` from the body className, keep `font-inter`. This makes the
  app pixel-match the reference's typography. (If brand insists on Gilroy later,
  buy the full 6-weight family first; do NOT ship a 2-weight font as the default.)

### 0.2 HEADINGS — strip ALL subtitles/eyebrows (founder: "no description below heading")
- **Reference has NO page subtitle and NO eyebrow.** The heading is just
  `<Layout title="...">` rendered once by `components/Header`. That's it.
- **Our divergence:** `famit-panel/components/PageHeader/index.tsx` adds an
  `eyebrow` (signal-glyph + overline), a big `<h1 page-head-title>`, AND a
  `subtitle` (`page-head-sub`). This is the jargon/clutter the founder hates.
- **FIX:** Stop using PageHeader for masthead text. Every page already passes its
  name via `<Layout title=...>` (we ported reference Layout) → that single H1 is
  the heading. Remove every `<PageHeader ... subtitle=... eyebrow=.../>` masthead
  call (keep only the `actions` slot where a page needs a top-right button —
  move those buttons into the page body like the reference does, e.g. the
  CustomerList "Customers + Search + Tabs + button" card row). Net: one clean
  heading per page, no subtitle, no eyebrow — matches reference exactly.

### 0.3 FEWER PAGES / LESS JARGON
- The 8-section collapsible IA in `contstants/navigation.tsx` is fine to KEEP
  (it mirrors reference's grouped sidebar). The problem is page DENSITY + jargon
  INSIDE pages (AI Manager 7 sub-routes, Billing 5, multi-tab dashboards). Per
  page below, NEEDS-COMPOSE/ADAPT entries call out collapsing sub-routes and
  renaming jargon to the reference's plain labels (e.g. "Overview", "Customer
  list", "Earning", "Transactions").

### 0.4 Reference building blocks available to compose from (all already in our `components/`)
`Layout` (title heading + sidebar), `Card`, `Table`/`TableRow`/`TableProductCell`,
`Tabs`, `Search`, `Dropdown`/`Select`, `Filters`, `Button`, `Badge`, `Switch`,
`Range`, `CardChartPie`, `Percentage`, `Field`/`FieldFiles`/`FieldImage`,
`Modal`, `DeleteItems`, `NoFound`, `Spinner`, `Tooltip`, `PopularProducts`,
`RefundRequests`, `Message`, `Editor`. Charts via `recharts`. Selection via
`hooks/useSelection`. Reference page recipe = `<Layout title>` + `flex` with
`col-left`/`col-right`, each column a stack of `card`s.

---

## 1. PORT MAP (our route → reference source → action → data swap)

Action classes:
- **REUSE-DIRECT** — a reference page matches; port it as-is, swap data only.
- **ADAPT** — closest reference layout, minor change.
- **NEEDS-COMPOSE** — no single match; compose from named reference components.

| # | Our route | Reference source (template path) | Action | Data / props to swap |
|---|-----------|----------------------------------|--------|----------------------|
| 1 | `/` (Dashboard) `app/page.tsx` | `templates/Customers/OverviewPage` (the KPI+charts dashboard) — its `Overview` (stat tiles), `TrafficСhannel`, `ActiveTimes`, plus right-col `CardChartPie`, `Countries`, `Messages` | **REUSE-DIRECT** | Swap stat tiles → Calls today / Connect rate / Leads / Spend. TrafficChannel→call-outcome bars. ActiveTimes→call-volume-by-hour. CardChartPie "Devices"→outcome split (connected/voicemail/failed). Countries→top campaigns. Messages→recent callbacks. Drop subtitle. |
| 2 | `/analytics` `app/analytics/page.tsx` | `templates/Income/StatementsPage` (Statistics + Transactions) OR reuse the Customers Overview chart stack | **ADAPT** | `Statistics` chart → calls/leads/spend trend; `Transactions` table → per-campaign analytics rows. Keep ONE chart + ONE table; remove jargon tabs. |
| 3 | `/campaigns` `app/campaigns/page.tsx` | `templates/Products/OverviewPage` (`Products` list card + `ProductActivity`) | **ADAPT** | Product grid/list → campaign cards (name, status badge, calls, connect%, created). `ProductActivity`→campaign activity feed. Status via `Badge`. |
| 4 | `/run` (Run a Campaign) `app/run/page.tsx` + `_lib/` | **NEEDS-COMPOSE** — base on `templates/Customers/CustomerList/CustomerListPage` (Search+Tabs+selectable List+bulk action bar) for the lead-pick step; wrap step flow with `Tabs`. Upload via `components/FieldFiles`. | **NEEDS-COMPOSE** | Compose: Step1 source = `FieldFiles` (CSV/XLSX) + saved-list `Select`; Step2 = CustomerList selectable table (`useSelection`) filtered by hot/warm via `Tabs`; Step3 = launch `Button` + `Modal` confirm. Reuse reference's selection bar (`DeleteItems`-style) for "selected N → Run". This is the founder's flagship Run-Campaign upgrade — keep it to ONE screen with 3 tabs, not many pages. |
| 5 | `/leads` `app/leads/page.tsx` | `templates/Customers/CustomerList/CustomerListPage` | **REUSE-DIRECT** | Swap `mocks/customers` → leads (name, phone, status, source, last-contact). Keep Search + Tabs(All/Hot/Warm/Cold) + `useSelection` bulk bar + row → detail. Plain "Leads" heading, no subtitle. |
| 6 | `/crm` `app/crm/page.tsx` (+ `[id]`, `_ui.tsx`) | List = `Customers/CustomerList`; Detail `[id]` = `templates/Customers/CustomerList/DetailsPage` | **ADAPT** | List swap → CRM contacts. `[id]` detail → contact profile + activity timeline (reference Details layout: left profile card + right tabs of activity/notes). Map our CRM fields onto reference profile blocks. |
| 7 | `/calls` (Call Logs) `app/calls/page.tsx` | `templates/Income/EarningPage`→`Transactions`, or `Income/StatementsPage`→`Transactions` (the dense transactions table) | **REUSE-DIRECT** | Transactions table → call log rows (time, number, campaign, outcome `Badge`, duration, cost, recording link). Reuse `Table`/`TableRow`. Row→call detail. |
| 8 | `/callbacks` `app/callbacks/page.tsx` | `templates/Notifications` (`Notification` list + `Filter`) OR `Customers/CustomerList` | **ADAPT** | Notification rows → scheduled callbacks (who, when, campaign, status). `Filter`→by date/status. Simple list, one heading. |
| 9 | `/whatsapp` `app/whatsapp/page.tsx` | `templates/MessagesPage` (conversation list + thread `Details`) | **REUSE-DIRECT** | Swap message mocks → WhatsApp threads (contact list left, chat thread right, composer = reference `Message`/`Editor`). Closest possible match — port as-is. |
| 10 | `/support` (Customer Support) `app/support/page.tsx` + `api.ts` | `templates/MessagesPage` (same chat layout) OR `Notifications` for ticket list | **ADAPT** | Ticket list → MessagesPage list; ticket thread → Details. Or list-only via Notifications if no live chat. Reuse same chat shell as WhatsApp for consistency. |
| 11 | `/booking` `app/booking/page.tsx` + `api.ts` | `templates/Products/ScheduledPage` (uses `ScheduleProduct` + `DateAndTime` calendar/date components) | **ADAPT** | Scheduled list → bookings (customer, service, slot via `DateAndTime`, status `Badge`). Reuse `ScheduleProduct` card + `DateAndTime` picker. |
| 12 | `/billing/overview` `app/billing/overview` | `templates/Income/EarningPage` (`Balance` hero + `RecentEarnings` + `Transactions` + `Countries`) | **REUSE-DIRECT** | Balance→wallet/credit balance + spend KPIs. RecentEarnings→recent spend chart. Transactions→recent charges. Countries→spend-by-vendor. Strip subtitle. |
| 13 | `/billing/vendors` | `templates/Products/OverviewPage`→`Products` list, OR `Income/EarningPage`→`Countries` (ranked list) | **ADAPT** | Ranked list → vendors (ElevenLabs/Groq/Sarvam/Vobiz) with spend, share %, status. `Percentage` for trend. |
| 14 | `/billing/explorer` (Cost Explorer) | `templates/Income/StatementsPage` (`Statistics` chart + `Transactions`) | **REUSE-DIRECT** | Statistics→cost-over-time chart with date range (`Filters`/`Range`); Transactions→line-item cost rows. |
| 15 | `/billing/audit` | `templates/Income/StatementsPage`→`Transactions` (immutable list) | **REUSE-DIRECT** | Transactions table → audit events (ts, actor, action, channel, result). Read-only, no bulk. |
| 16 | `/billing/plan` (Plan & Ledger) | `templates/UpgradeToProPage` (`Pricing` cards + `Faq`) | **ADAPT** | Pricing cards → current plan + upgrade tiers; below it a `Transactions` ledger. Faq→billing FAQ (optional). |
| 17 | `/payments` `app/payments/page.tsx` + `_api.ts` | `templates/Income/PayoutsPage` (payout/transaction tables) | **REUSE-DIRECT** | Payouts/transactions → customer payments (amount, method, status `Badge`, date). Reuse table + status chips. |
| 18 | `/vendors` (admin) `app/vendors/page.tsx` | `templates/SettingsPage`-style sectioned config, OR `Products/OverviewPage` list | **ADAPT** | Admin vendor config = sectioned cards (per-vendor keys/limits) using `Field`/`Switch`/`Select` like SettingsPage sections. Admin-gated. |
| 19 | `/suppression` (Do-Not-Call) `app/suppression/page.tsx` | `templates/Customers/CustomerList` (search + table + bulk delete) | **REUSE-DIRECT** | List → suppressed numbers; Search by number; `FieldFiles` to bulk-upload DNC list; `DeleteItems` bulk-remove. |
| 20 | `/webhooks` `app/webhooks/page.tsx` | `templates/SettingsPage` section pattern (`Field` + `Switch` + `Button`) | **ADAPT** | Each webhook = a settings card: URL `Field`, events `Switch`/checkboxes, secret, enabled `Switch`, test `Button`. List of these cards. |
| 21 | `/ads` (Ad Automation) `app/ads/page.tsx` + `_lib.ts` | `templates/PromotePage` (`Insights` KPI band + `List` + `Engagement` + `Interactions`) | **ADAPT** | Insights→ad-spend/ROAS KPIs; List→campaigns/ad-sets with status; Engagement/Interactions→impressions/clicks charts. PromotePage is the natural ads analog. |
| 22 | `/funnels` `app/funnels/page.tsx` + `_lib.ts` | `templates/PromotePage`→`Insights`+`List`, or `Income/StatementsPage` Statistics for the funnel chart | **ADAPT** | Funnel stages as a stepped bar/`Range` viz + stage conversion table. Keep ONE funnel chart + ONE stage table. |
| 23 | `/forms` (Form Builder) `app/forms/page.tsx` (+ `[id]`, `CreateFormModal.tsx`, `_ui.tsx`) | List = `Products/OverviewPage` grid; Editor `[id]` = `templates/Products/NewProductPage` (the field-by-field builder with `Field`/`Editor`/`FieldImage`/`Switch`) | **ADAPT** | Forms list → product-grid of forms (name, submissions, status). `[id]` builder reuses NewProductPage's field stack to add/edit form fields. `CreateFormModal`→reference `Modal`. |
| 24 | `/workflows` (node builder) `app/workflows/page.tsx` (+ `_canvas`,`_editor`,`_nodes`) | **NEEDS-COMPOSE** — no reference node-editor. Shell from `Layout`; canvas = React Flow (Flowaxon style per memory); side `_editor` panel reuses `Field`/`Select`/`Switch`/`Modal` | **NEEDS-COMPOSE** | Keep React-Flow canvas. Restyle the chrome (toolbar, node cards, inspector panel) with reference tokens/components: node = `card`, inspector = SettingsPage-style `Field` stack, save bar = `Button`. Heading via `Layout title="Workflows"`, no subtitle. |
| 25 | `/settings` `app/settings/page.tsx` | `templates/SettingsPage` (Menu + ProfileInformation + Password + Notifications + Payment, react-scroll anchored) | **REUSE-DIRECT** | Port wholesale. Swap sections → Profile / Password / Notifications / Billing / Team. Reuse the anchored `Menu` + `Field` sections verbatim. |
| 26 | `/login` `app/login/page.tsx` | `components/Login` (reference's login component) | **REUSE-DIRECT** | Port the reference `Login` component; swap brand logo (real HD logo, drop eq glyph per memory) + wire our auth. Single clean card. |
| 27 | `/ai-manager` (group, 7 sub-routes) | See §2 — heaviest simplification. Base on `Customers/OverviewPage` (overview) + `MessagesPage` (test/chat) + `Notifications` (history/approvals) + `SettingsPage` (setup/users/capabilities) | **NEEDS-COMPOSE** (collapse 7→3) | See §2. |

### AI Manager sub-routes (current — the "too complex" offender)
| Our route | Reference source | Action | Notes |
|-----------|------------------|--------|-------|
| `/ai-manager/overview` | `Customers/OverviewPage` (KPI tiles + activity) | ADAPT | Becomes the ONE landing page: status, today's actions, recent commands. |
| `/ai-manager/test` (Test Console) | `MessagesPage` (chat thread) | REUSE-DIRECT | A single chat box to talk to the manager — the simplest possible surface. |
| `/ai-manager/commands` (History) | `Notifications` (list + Filter) | ADAPT | Command history as a notification-style feed. MERGE with approvals. |
| `/ai-manager/approvals` (Pending Approvals) | `Notifications` rows w/ approve/reject `Button` | ADAPT | MERGE into the History feed as a "Pending" tab. |
| `/ai-manager/capabilities` | `SettingsPage` `Switch` sections | ADAPT | What the AI may do = toggles. MERGE into Setup. |
| `/ai-manager/setup` | `SettingsPage` sectioned `Field`/`Switch` | REUSE-DIRECT | Setup + capabilities + authorized users all become ONE settings page with anchored sections. |
| `/ai-manager/users` (Authorized Users) | `SettingsPage`→Team section / `Customers/CustomerList` | ADAPT | MERGE into Setup as a "Authorized users" section. |

---

## 2. WORST PAGES (founder-flagged "very bad / too complex") — heaviest simplification

1. **AI Manager (whole module, 7 sub-routes)** → COLLAPSE to **3 pages**:
   `Overview` (`Customers/OverviewPage`), `Test/Chat` (`MessagesPage`), `Setup`
   (`SettingsPage` anchored sections — folds in Capabilities + Authorized Users +
   Approvals). Command History + Pending Approvals become **tabs on Overview**.
   Kill all jargon ("Command Center", "Capabilities matrix"); use plain labels.
2. **Run a Campaign `/run`** → ONE screen, 3 `Tabs` (Source → Pick leads → Launch),
   composed from `CustomerList` + `FieldFiles` + `Modal`. No multi-page wizard.
3. **Billing (5 sub-routes)** → keep routes but each maps 1:1 to an `Income/*`
   template (Earning/Statements/Payouts/UpgradeToPro) so they look identical to
   the reference's money pages; strip all subtitles.
4. **Dashboard `/`** → port `Customers/OverviewPage` exactly; remove our bespoke
   multi-tab/eyebrow masthead.
5. **CRM `/crm` + `[id]`** → `CustomerList` + `DetailsPage`; drop custom layout.
6. **Workflows** → keep React Flow but re-skin all chrome with reference
   components (was looking "from scratch").
7. **Forms builder `[id]`** → reuse `Products/NewProductPage` field stack instead
   of a bespoke builder.
8. **Analytics `/`** → collapse multi-chart jargon dashboard to ONE
   `Income/StatementsPage` (Statistics + Transactions).

Cross-cutting on ALL of the above: delete `PageHeader` eyebrow+subtitle, use
`<Layout title>` heading only; drop Gilroy → Inter Display.

---

## 3. CLASS COUNTS
- **REUSE-DIRECT: 11** — #1 Dashboard, #5 Leads, #7 Calls, #9 WhatsApp, #12 Billing-Overview,
  #14 Cost-Explorer, #15 Audit, #17 Payments, #19 Suppression, #25 Settings, #26 Login.
- **ADAPT: 12** — #2 Analytics, #3 Campaigns, #6 CRM, #8 Callbacks, #10 Support,
  #11 Booking, #13 Billing-Vendors, #16 Billing-Plan, #18 Vendors, #20 Webhooks,
  #21 Ads, #22 Funnels, #23 Forms. (note: 13 lines — Forms split list/editor.)
- **NEEDS-COMPOSE: 3** — #4 Run-Campaign, #24 Workflows, #27 AI-Manager module.

(AI Manager's 7 internal sub-routes collapse into the 3-page set in §2.)
</content>
