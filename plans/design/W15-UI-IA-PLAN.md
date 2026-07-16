# W15 — UI Information-Architecture Plan (Consolidated, Core_2-Reuse)

**Branch:** `fix/realtime-voice-kernel-v2` · **Scope:** FRONTEND ONLY (`famit-panel/`) · **Date:** 2026-06-18
**Author:** W15 IA design agent · **No box deploy** (panel deploys to FORTRESS separately, later gated).
**Companion:** `design/spec-core2-reuse-map.md` (the per-page archetype/template map — this plan layers IA + consolidation on top of it).

> **IRON RULES (founder, hard):** (1) REUSE the Core_2 kit + the existing page layouts/components — they are GOOD. Rewire data + fix PLACEMENT. NEVER build UI from scratch. (2) Kill the SCATTER: each concern gets ONE obvious home. (3) Consistent typography/spacing/nav across every page. (4) Business-friendly lead badges (Hot/Warm/Cold/Dead/Booked/Callback/Interested) — NO raw scores. (5) Run-Campaign: clean, fast, readable. (6) Real-time data wired to the live APIs.

---

## 0. THE PROBLEM (ground truth from EXPLORE)

The same concern is shown in 2–4 different places, so the founder hops around:

| Scattered concern | Lives today in | Pain |
|---|---|---|
| **Calls** | Dashboard "Recent calls", `/calls`, `/analytics` funnel, `/ai-manager` Calls tab | 4 surfaces |
| **Lead scores / Hot leads** | Dashboard "Hot leads", `/leads`, `/crm` KPIs | 3 surfaces, raw numbers |
| **Analytics** | `/analytics` (isolated funnel) + Dashboard (volume chart) | same story, 2 chart UXs, no cross-link |
| **Usage / spend** | Dashboard "Usage" + `/billing/overview` + `/billing/explorer` | 3 slices, no link |
| **Leads vs CRM** | `/leads` (dial queue) + `/crm` (pipeline) | near-duplicate columns, no handoff link |
| **Callbacks** | `/callbacks` orphaned, no link back to `/calls` | manual hop |
| **AI Manager** | 9 sidebar children, most are dead redirects into one tabbed page | nav clutter |
| **PageHeader** | present on ~40% of pages only | header zone looks different page-to-page |
| **Lead badges** | `ScoreBadge` shows `"82 hot"` raw number; `StageBadge` Booked-language trapped inside CRM only | not business-friendly, inconsistent |
| **No global filter** | every data page re-rolls its own date/campaign/status filter (or has none) | inconsistent, no shared mental model |

**Root cause is the same as the reuse-map's:** the kit is fine; the PAGES place the same data in many homes with bespoke chrome. Fix = **consolidate to one home per concern + one shared filter bar + one badge language + uniform header**, all built from existing Core_2 components.

---

## 1. TARGET INFORMATION ARCHITECTURE (one home per concern)

**11 top-level destinations.** Nav collapses from 9 scattered groups (+ a 9-child AI-Manager) into a clean, flat-where-possible IA. Each row below is the ONE obvious home for its concern.

| # | Destination (route) | THE one job | Absorbs / merges | Core_2 archetype |
|---|---|---|---|---|
| 1 | **Dashboard** `/` | Today-first executive cockpit: summary + funnel + call/lead analytics CONSOLIDATED, with drill-down filters | merges `/analytics` (funnel + volume), Dashboard's own KPI hero, the "Usage" tile (links to Billing) | Dashboard archetype (`HomePage` + `Customers/OverviewPage` cards) |
| 2 | **Leads & CRM** `/crm` (Leads = a tab/filter, not a 2nd page) | The people: dialing queue + pipeline in ONE surface with Hot/Warm/Cold/Dead/Booked badges, filters, AI summary cards | merges `/leads` into `/crm` as a saved-view tab; cross-links to a contact's calls | Overview+Table → `/crm/[id]` Two-pane detail |
| 3 | **Call Logs** `/calls` | Every call: table with **Transcript \| Recording** columns + filters + callbacks as a sub-tab | absorbs `/callbacks` as a tab; cross-links contact → CRM | Overview+Table (`Transactions` table + `Modal` detail) |
| 4 | **Bookings** `/booking` | Appointments booked by the agent | — | List/Table + `DateAndTime` |
| 5 | **Knowledge Base** `/knowledge` | RAG sources / test / gaps | — | Tabbed `Card` (Sources/Test/Gaps) |
| 6 | **WhatsApp** `/whatsapp` | Conversations + templates/broadcast | folds `/communication` (omnichannel) in as a channel tab | Two-pane (`MessagesPage`) |
| 7 | **Creative Studio** `/creative` | AI banner/video/library/brand | — (already its own clean group) | existing studio + List/Library |
| 8 | **AI Manager** `/ai-manager` | Inbound command brain: Home/Live/Handoff/Calls/Try-it/Setup as TABS | collapses 9 sidebar children → 1 link with in-page tabs | Overview+Table + tabbed `Card` |
| 9 | **Reports** `/analytics` (relabeled "Reports") | Deep drill-down analytics the Dashboard links INTO (channel/time/geo/funnel detail, export) | becomes the deep-dive destination; the "Intelligence" group dissolves | Dashboard archetype (chart-heavy `Customers/OverviewPage` cards) |
| 10 | **Billing** `/billing/overview` (hub w/ tabs) | The whole money story in ONE hub: Overview / Spending / Vendor Costs / Audit / Plan / Payments as tabs | merges the 6-page Money group into one tabbed hub; Dashboard "Usage" links here | Overview+Table + `Tabs` + `CardChartPie` |
| 11 | **Settings** `/settings` | Account/Org/Security/Notifications + Do-Not-Call + Vendors(admin) + Workflows/Webhooks/Integrations(automate) as sections | folds the thin "Foundation" + "Automate" groups into grouped settings/utility sections | Section-form (`SettingsPage` `Menu` + `react-scroll`) |

**Super Admin** (`/super-admin/*`) stays a separate admin-only group (role-gated, unchanged — out of scope for consolidation).

### 1a. What MERGES (the scatter kill), explicitly

- **`/analytics` (funnel) + Dashboard volume chart → Dashboard** as the consolidated analytics home; `/analytics` survives as **"Reports"** = the deep drill-down the Dashboard's "View full report" links to. ONE chart experience, two depths.
- **`/leads` → `/crm`** as a "Leads / Dialing queue" tab (saved view). One people-surface. (Route `/leads` kept as a redirect/alias for muscle memory + deep links — no orphaned route.)
- **`/callbacks` → `/calls`** as a "Callbacks" tab. One call surface.
- **Money group (6 pages) → `/billing` hub** with `Tabs`: Overview · Spending · Vendor Costs · Audit · Plan · Payments. One money home. (Existing `/billing/*` routes kept as direct deep-links into the matching tab.)
- **`/communication` → `/whatsapp`** as channel tabs (WhatsApp · Telegram · Email/SMS-soon). One messaging home.
- **AI Manager 9 nav children → 1 link + in-page tabs.** The dead redirect routes (`/ai-manager/overview`, `/commands`, `/approvals`, `/capabilities`, `/setup`, `/users`) collapse into tabs inside `/ai-manager`; only `/ai-manager`, `/ai-manager/live`, `/ai-manager/handoff` remain real routes (live/handoff can also be tabs).
- **"Foundation" (Do-Not-Call, Vendors) + "Automate" (Workflows, Webhooks, Integrations) → utility sections** reachable from Settings + a slim "Build" nav group (Workflows is heavy enough to keep a top-level link). Net: the thin 1–2 item groups stop cluttering the rail.

**Non-breaking guarantee:** every previously-live route still resolves (as a tab anchor or a redirect alias). No page 404s; we only change WHERE the nav points and WHAT the page consolidates.

---

## 2. CONSISTENT TOP NAV (the rail)

Keep the existing `components/Sidebar` + `Sidebar/Dropdown` + `contstants/navigation.tsx` data module + the `feature_key`/`roles` entitlement gating — **rewire the DATA only** (founder rule: reuse, fix placement). New grouping:

```
WORK
  Dashboard            /            (Command — always present)
  Leads & CRM          /crm         (Leads = tab inside)
  Call Logs            /calls       (Callbacks = tab inside)
  Bookings             /booking
  AI Manager           /ai-manager  (manager-gated; tabs inside)
GROW
  Campaigns            /campaigns
  Run                  /run
  Creative Studio      /creative    (Studio/Video/Library/Brand)
  Ad Automation        /ads         (manager)
  Funnels              /funnels
  Forms                /forms
MESSAGE
  WhatsApp             /whatsapp    (manager; channels as tabs)
  Customer Support     /support
INTELLIGENCE
  Reports              /analytics
  Knowledge Base       /knowledge
MONEY
  Billing              /billing/overview   (tabbed hub: Overview/Spending/Vendors/Audit/Plan/Payments)
BUILD
  Workflows            /workflows
  Webhooks             /webhooks    (manager)
  Integrations         /integrations (manager)
SETTINGS  (navigationUser, footer)
  Settings             /settings    (+ Do-Not-Call, Vendors-admin as sections)
SUPER ADMIN (admin-only, unchanged)
```

- **No new Sidebar component** — same collapsible-group mechanism (`list` + no `href`). Preserve every `feature_key` and `roles` gate verbatim (move the keys with their children).
- The rail now reads in plain task language (WORK / GROW / MESSAGE / INTELLIGENCE / MONEY / BUILD) and each item has exactly one home.

---

## 3. SHARED GLOBAL FILTER BAR (reused on EVERY data page)

The single biggest consistency win. **NEW shared component `components/GlobalFilters`** — but built ENTIRELY by composing existing Core_2 primitives (NOT from scratch):

- **Date range** → `components/Select` (presets: Today (default) · Yesterday · Last 7 · Last 30 · This month · Custom) + `components/DateAndTime` for the Custom range. Reuses the same `Select`/`DateAndTime` already in the kit.
- **Campaign** → existing `components/CampaignSelect`.
- **Lead status** → `components/Tabs` or `components/Select` with the business badge labels (Hot/Warm/Cold/Dead/Booked/Callback/Interested).
- **Advanced** → existing `components/Filters` popover (`Modal`+`Select`+`Range`+`Switch`) for the long tail.

It renders as the `headContent` slot of the page's top `Card` (Core_2's native chrome row) so it sits exactly where Core_2 puts in-card chrome — **no new layout primitive**. State lives in URL query params (`?range=7d&campaign=…&status=hot`) so it persists across the Dashboard → Reports → Call Logs drill-down and is shareable.

**Pages that mount it:** Dashboard, Reports, Leads & CRM, Call Logs, Bookings, Billing. (Default range = **Today** everywhere, per founder.)

---

## 4. ONE BADGE LANGUAGE (business-friendly, everywhere)

Extend `lib/badges.tsx` (reuse the existing `Badge` component + token classes — no new visual system). Add ONE helper used on Dashboard, Leads&CRM, Call Logs:

```
LeadBadge(lead) → derives the tier and renders <Badge>:
  status opt_out / not_interested        → Dead     (muted red)
  stage booked / won                     → Booked   (green)
  outcome interested OR status interested→ Interested(green)
  status callback                        → Callback (blue)
  else by score:  ≥70 → Hot (green dot) · 40–69 → Warm (yellow) · 1–39 → Cold (neutral)
```

- **Replaces** the raw-number `ScoreBadge` (`"82 hot"`) on every customer-facing surface. Keep `ScoreBadge` available for the one admin/debug view if needed, but default UI shows the WORD.
- Promote the CRM-only `StageBadge` Booked/Won language up into this shared helper so Leads, Calls, and Dashboard all speak it. ONE label vocabulary across pages.

---

## 5. UNIFORM PAGE HEADER (consistent header zone)

Decision per reuse-map §0: **drop the bespoke `PageHeader` masthead; use the Core_2 in-`Card` head row (title + `headContent`)** as the canonical header on every page — OR keep a thin `PageHeader` but apply it to ALL pages so the zone is identical. **Chosen:** single clean `Layout title` + the top `Card` head row carries the eyebrow + `GlobalFilters`. This makes the header zone byte-identical across pages and removes the 40%/60% split. Mechanical: each currently-headerless page (`/analytics`,`/calls`,`/leads`/`crm`,`/run`,`/callbacks`,`/campaigns`,`/ai-manager`,`/knowledge`,`/whatsapp`,`/payments`) gets the same head-row pattern.

---

## 6. COMPONENT-REUSE MAPPING (per destination — NO from-scratch)

All imports from `@/components/*` (already ported). New work = composition + data rewire only.

| Destination | Reused Core_2 components | New (composition only) |
|---|---|---|
| **Dashboard** `/` | `Layout`, `Card` (+`headContent`), `Tabs`, `Select`, `Sparkline`/Recharts area, `CardChartPie`, `PopularProducts`-shape list, `Table`+`TableRow`, `Percentage`, `KpiCard`/new `Overview` metric strip, `NoFound` | `GlobalFilters` mount; funnel mini-card (links to Reports); `LeadBadge` |
| **Leads & CRM** `/crm` (+Leads tab) | `Card`, `Tabs` (Leads/All/Hot/Pipeline saved views), `Search`, `Table`+`TableRow`, `useSelection`+`DeleteItems`, `Filters`, `Modal`, `FieldFiles` (CSV upload), `NoFound` | `GlobalFilters`; `LeadBadge`; AI-summary card (reuses `Card` + `Message`); cross-link → call logs |
| **Call Logs** `/calls` (+Callbacks tab) | `Card`, `Tabs` (Calls/Callbacks), `Search`, `Select` (period), `Table`+`TableRow`, `Modal` (detail), `Message`/Chat (transcript bubbles), `Button isBlack` (export), `NoFound` | Transcript\|Recording columns; `GlobalFilters`; `LeadBadge`; contact→CRM link |
| **Bookings** `/booking` | `Card`, `Table`+`TableRow`, `Tabs` (status), `DateAndTime`, `Modal` (new booking), `NoFound` | `GlobalFilters` |
| **Knowledge** `/knowledge` | `Card`, `Tabs` (Sources/Test/Gaps), `Field`/`FieldFiles`, `Table`+`TableRow`, `NoFound` | — |
| **WhatsApp** `/whatsapp` | `Card`, `Tabs` (channels), `MessagesPage` rail + `Details/Chat`, `Field`+`Editor` (composer), `NoFound` | channel tabs fold in `/communication` |
| **Creative Studio** `/creative` | existing studio pages + `GridProduct`/`Product` library, `Card`, `Tabs` | — |
| **AI Manager** `/ai-manager` | `Card`, `Tabs` (Home/Live/Handoff/Calls/Try-it/Setup), `Table`+`TableRow`, `Modal`, `Switch` | collapse 9 routes → tabs |
| **Reports** `/analytics` | `Card`, `Customers/OverviewPage` cards (`TrafficChannel`/`ActiveTimes`/`Countries`), `CardChartPie`, `ProgressBar`/`Legend` (funnel), `Select`, export `Button` | `GlobalFilters` (shared params w/ Dashboard) |
| **Billing** `/billing/overview` | `Card`, `Tabs` (6 tabs), `Table`+`TableRow`, `CardChartPie`, `Filters`, `Select`, `Pricing`/`Faq` (Plan tab), `NoFound` | tabbed hub; `GlobalFilters` |
| **Settings** `/settings` | `SettingsPage` `Menu`+`react-scroll` `Element`, `Field`, `Switch`, `Select`, `Table` (Vendors/Do-Not-Call sections) | section grouping |
| **Sidebar / nav** | existing `Sidebar`, `Sidebar/Dropdown`, `NavLink`, `Logo` | navigation.tsx data rewire only |
| **Global filter bar** | `Select`, `DateAndTime`, `CampaignSelect`, `Tabs`, `Filters` | `GlobalFilters` wrapper |
| **Badges** | `Badge`, `lib/badges` | `LeadBadge` helper |

---

## 7. BUILD ORDER (shell first — highest leverage, crash-safe per unit)

Each unit: `npx tsc --noEmit` + `next build` EXIT 0, commit, then next. `index.lock` retry up to 6×. No `.py` touched. No box deploy.

1. **SHELL — nav rewire** (`contstants/navigation.tsx`): collapse to the §2 grouping (WORK/GROW/MESSAGE/INTELLIGENCE/MONEY/BUILD), AI-Manager 9→1, preserve every `feature_key`/`roles`. *Verify: rail renders, all gates intact, no dead links.*
2. **SHELL — `LeadBadge`** (`lib/badges.tsx`): add the business-friendly tier helper (§4). *Verify: renders Hot/Warm/Cold/Dead/Booked/Callback/Interested.*
3. **SHELL — `GlobalFilters`** (`components/GlobalFilters`): compose Select+DateAndTime+CampaignSelect+Tabs+Filters; URL-param state; Today default (§3). *Verify: mounts in a Card headContent, updates query params.*
4. **SHELL — uniform header** (§5): standardize the top-`Card` head-row pattern; remove PageHeader split. *Verify: identical header zone across 3 sample pages.*
5. **Dashboard** `/` — consolidate analytics (funnel + volume + KPI) + mount `GlobalFilters` + `LeadBadge`; "View full report" → Reports.
6. **Leads & CRM** `/crm` — fold `/leads` in as a tab; `LeadBadge`; AI-summary cards; `/leads` → redirect alias.
7. **Call Logs** `/calls` — Transcript\|Recording columns; fold `/callbacks` in as a tab; `LeadBadge`; contact→CRM link.
8. **Reports** `/analytics` — relabel; share filter params with Dashboard; deep-dive cards.
9. **Billing hub** `/billing/overview` — 6-tab hub; existing routes → tab deep-links.
10. **WhatsApp** `/whatsapp` — fold `/communication` channels in as tabs.
11. **AI Manager** `/ai-manager` — collapse 9 routes → tabs.
12. **Sweep** the remaining List/Table pages (Bookings, Knowledge, Campaigns, Run, Support, Workflows, Webhooks, Integrations, Settings sections) to the same head-row + `GlobalFilters` + `LeadBadge` standard, per the reuse-map archetypes.

**Per-unit done bar:** tsc+build green · dark+light · matches the Core_2 archetype it ports · zero `lib/api`/route/handler change · commit. Stop and write progress to disk between units (crash-safe).

---

## 8. NON-GOALS / GUARDRAILS

- No `.py` touched (concurrent voice wave owns `voice_kernel`/`voice_ops`).
- No box deploy (FORTRESS panel deploy is a later gated step).
- No new design system / no from-scratch components — compose the existing kit.
- No backend/API/route signature changes — data rewire + placement only.
- Every previously-live route still resolves (tab anchor or redirect alias) — zero orphans.
