# UI OVERHAUL — Page-by-Page Build Plan (PORT the reference kit)

Status: EXECUTION PLAN (synthesis of the 4 read-only design docs). This is the
single build runbook. It supersedes nothing in the design docs — it sequences
them into waves with owners, parallelization, the acceptance gate, and
build/deploy/verify steps.

THE ONE RULE (founder, repeated, non-negotiable): **PORT, DON'T APPROXIMATE.**
For every page, find the matching reference page/template FIRST, copy its real
JSX + Tailwind, and swap only our data/labels. Never hand-build a lookalike.
Every "premium" thing we invented from scratch (the Signal `PageHeader`, the
AI-Manager pill-rail, Gilroy) is exactly what the founder is rejecting — delete it.

### Inputs (read these before touching code)
- Reference kit (authoritative LOOK), READ-ONLY source to copy from:
  `C:\Users\kunal\Desktop\core-2-dashboard-builder-react`
- Our app to port onto it: `C:\Users\kunal\Desktop\caps\famit-panel`
  (pages `app/*`, shell `components/*`, tokens `app/globals.css`,
  nav `contstants/navigation.tsx`).
- Design docs (the bar): `design/ui-ref-kit-inventory.md` (copy-from spec),
  `design/ui-page-port-map.md` (per-route port), `design/ui-design-principles.md`
  (10 rules + acceptance checklist), `design/ui-font-heading-plan.md` (font/heading).
- Secondary kit (fallback if a component is missing from the reference):
  `C:\Users\kunal\Desktop\Core_2-Capsy-Dashboard`.

### ⛔ SCHEDULING GATE — runs AFTER the Control Layer build
This UI build and the **Control Layer build BOTH edit `famit-panel` and BOTH
deploy** to panel.famit.in. They **cannot overlap** (merge conflicts in
`app/globals.css`, `layout.tsx`, `contstants/navigation.tsx`, and a single
deploy pipeline). **Do not start W1 until the Control Layer build is merged +
deployed.** First action of this build = rebase onto the post-control-layer
`main` (or the live `feat/premium-ui` tip), then branch `feat/ui-overhaul-port`.

---

## THE THREE GLOBAL ROOT-CAUSE FIXES (all 4 docs independently confirm)

These are W1. They are the reason the founder still sees "no change / too complex."

1. **FONT — "it didn't change" is a missing-weights fallback, not a cache bug.**
   `app/layout.tsx:33-52` loads Gilroy with only Light(300)+ExtraBold(800); only
   those 2 `.otf` exist in `public/fonts/`. Our type scale requests 400/500/600/700
   everywhere (body 400, captions 500, buttons/sub-titles 600, headings 600), so
   ~95% of text falls through Gilroy → InterDisplay. **FIX: drop Gilroy entirely;
   adopt Inter Display app-wide** (the reference's only font; its 5 woff2 300-700
   are ALREADY in our `public/fonts/`). Then the change is visible everywhere.
2. **HEADINGS — strip every subtitle/eyebrow.** Reference renders the page title
   ONCE, as `text-h4 max-lg:text-h5` in the sticky `Header`, via `<Layout title>`
   — no eyebrow, no glyph, no accent bar, no subtitle. Our `components/PageHeader`
   invents all of those (`globals.css:740-760`). **FIX: simplify `PageHeader` to
   `{title, actions}` and sweep every caller to drop `subtitle=`/`eyebrow=`.**
3. **FEWER PAGES / LESS JARGON.** Collapse Billing's 5 leaves and AI-Manager's
   7 sub-routes; cut the 4 "Create Studio" coming-soon stubs and the duplicate
   Vendors entry from nav; rename jargon to plain nouns (glossary below).

---

## WAVE 1 — DESIGN-SYSTEM FOUNDATION (shared, serial, ONE owner, do FIRST)

W1 touches the GLOBAL files every page depends on, so it is **single-owner,
sequential, and must land + build-green before any page work**. No page-port
agent may start until W1 is committed (otherwise they collide on `globals.css`/
`layout.tsx`/`PageHeader`/nav and inherit the old font).

**Owner files (one agent, one branch, commit per numbered unit):**
- `famit-panel/app/layout.tsx`
- `famit-panel/app/globals.css`
- `famit-panel/components/PageHeader/index.tsx`
- `famit-panel/contstants/navigation.tsx`
- shell reconcile: `components/Layout`, `components/Sidebar`, `components/Sidebar/Dropdown`,
  `components/NavLink`, `components/Header`, `components/Card`, `components/Logo`
  (these are ALREADY ported from the older kit — reconcile against the NEW
  `core-2-dashboard-builder-react` shell, do not rebuild).

**Units (each: edit → `npm run build` green → commit):**
1. **Font swap.** Delete the `gilroy = localFont({...})` block + `${gilroy.variable}`
   from `<body>` in `layout.tsx`; keep only `interDisplay`. In `globals.css`:
   `--font-inter: var(--font-inter-display);` (line ~204) and drop `var(--font-gilroy)`
   from the `html { font-family }` stack (line ~283). Body className keeps
   `font-inter`. (Gilroy `.otf` may stay on disk for a future wordmark-only face;
   nothing in the cascade references it.)
2. **Type tokens → reference ramp.** Align `--text-h*` to the reference values so
   headings match pixel-for-pixel: `h1` 6rem/300, `h2` 3.75rem/500, `h3` 3rem/500,
   `h4` 2rem/600 (lh 1.45), `h5` 1.5rem/500, `h6` 1.25rem/600; plus `sub-title-1`
   1rem/600, `body-1` 1rem/400, `body-2` 0.875rem/400, `button` 0.875rem/600,
   `caption` 0.75rem/400, `overline` 0.625rem/500. (Copy verbatim from reference
   `globals.css @theme`.)
3. **Clean PageHeader.** Reduce `components/PageHeader/index.tsx` to `{title,
   actions, className}` only — `<h1 className="text-h4 max-lg:text-h5 text-t-primary">`
   + right-aligned actions slot. Remove eyebrow/signal-glyph/accent-bar markup and
   the `.page-head*` CSS (`globals.css:740-760`). (Preferred end-state: page title
   lives in `<Layout title>`/Header; `PageHeader` remains only as a thin actions
   row where a page needs a top-right button.)
4. **Shell reconcile + Logo.** Diff our shell components against the new reference
   shell; align any drift (Header `text-h4` title, Card `h-12` head + `text-h6`
   title + `pt-3`, Sidebar `gradient-menu` active pill). Point `components/Logo`
   light+dark at our real HD logo (drop the eq/waveform glyph).
5. **Nav simplification** (`contstants/navigation.tsx`): apply the glossary +
   consolidation (below). Cut "Create Studio" stubs + the duplicate Vendors;
   collapse Billing to ONE entry; collapse AI-Manager to ONE entry (optionally 3
   children). Target ~7-8 groups, ≤5 children each, plain nouns.

**Jargon → plain glossary (apply in nav AND in-page labels):**
`Suppression`→**Do-Not-Call list** · `Cost Explorer`→**Spending** · `Plan & Ledger`→**Plan**
· `Capabilities`→**What it can do** (fold into Setup) · `Command Center`→**remove**
· `Command History`→**History** · `Authorized Users`→**Team** · `Test Console`→**Try it**
· `Create Studio` (4 stubs)→**remove from nav**.

**W1 gate (must pass before W2 starts):**
- `npm run build` green; app boots; sidebar renders the simplified nav.
- Visual: body + 600-weight headings now render Inter Display (no Inter-fallback
  gap); ONE clean `text-h4` page title, zero subtitle/eyebrow anywhere.
- Commit each unit; push the W1 branch tip.

---

## WAVE 2 — PAGE PORTS (parallel, partitioned by directory)

Precondition: W1 merged. Each page-port agent **branches off the W1 tip**, owns a
disjoint set of `app/*` directories (NO two agents touch the same dir or any
shared file), ports its reference template per the map, passes the acceptance
checklist, builds green, commits per page, and pushes. ONE agent per group.

### Partitioning (5 parallel groups — disjoint dirs, no shared-file overlap)

| Group | Owner dirs (`app/*`) | Reference templates leaned on | Model |
|---|---|---|---|
| **G1 Dashboards & Analytics** | `page.tsx` (Dashboard), `analytics`, `campaigns`, `funnels`, `ads` | `Customers/OverviewPage`, `Income/StatementsPage`, `Products/OverviewPage`, `PromotePage` | sonnet |
| **G2 Lists & CRM** | `leads`, `crm` (+`[id]`), `calls`, `callbacks`, `suppression`, `payments` | `Customers/CustomerList` (+`DetailsPage`), `Income/Payouts/Earning`, `Notifications` | sonnet |
| **G3 Conversations & Booking** | `whatsapp`, `support`, `booking` | `MessagesPage`, `Products/ScheduledPage` | sonnet |
| **G4 Billing & Settings & Admin** | `billing/*`, `settings`, `vendors`, `webhooks`, `login` | `Income/*` (Earning/Statements/Payouts/UpgradeToPro), `SettingsPage`, `components/Login` | sonnet |
| **G5 Hard / NEEDS-COMPOSE** (founder-flagged) | `ai-manager/*`, `run`, `workflows`, `forms` (+`[id]`) | `OverviewPage`+`MessagesPage`+`SettingsPage` (AIM), `CustomerList`+`FieldFiles`+`Modal` (run), React Flow reskin (workflows), `Products/NewProductPage` (forms) | **opus** |

Rules: G5 (the 3 NEEDS-COMPOSE + Forms — the "too complex" offenders) gets opus;
the REUSE-DIRECT/ADAPT groups get sonnet (mechanical port + data swap). No agent
edits `globals.css`/`layout.tsx`/`navigation.tsx`/`PageHeader` (W1 owns those).
If two pages must share a new helper, build it in W1 or sequence in main — never
two agents on one file.

### Per-page port table (route → reference → action → data swap)

Action classes: **REUSE-DIRECT** (port as-is, swap data) · **ADAPT** (closest
layout, minor change) · **NEEDS-COMPOSE** (compose from named reference components).
Counts: REUSE-DIRECT 11 · ADAPT 12 · NEEDS-COMPOSE 3.

**G1 — Dashboards & Analytics**
| Route | Reference source | Action | Data swap |
|---|---|---|---|
| `/` Dashboard | `Customers/OverviewPage` (stat tiles + `TrafficChannel` + `ActiveTimes` + right-col `CardChartPie`/`Countries`/`Messages`) | REUSE-DIRECT | KPIs→Calls today/Connect rate/Leads/Spend; TrafficChannel→call-outcome bars; ActiveTimes→volume-by-hour; pie→connected/voicemail/failed; Countries→top campaigns; Messages→recent callbacks. Drop tabs+eyebrow. |
| `/analytics` | `Income/StatementsPage` (Statistics chart + Transactions) | ADAPT | One chart (calls/leads/spend trend) + one table (per-campaign rows). Kill jargon tabs. |
| `/campaigns` | `Products/OverviewPage` (`Products` list + `ProductActivity`) | ADAPT | List→campaign cards (name, status `Badge`, calls, connect%, created); activity feed→campaign activity. |
| `/funnels` | `PromotePage` `Insights`+`List`, or `StatementsPage` Statistics | ADAPT | Funnel stages as stepped `Range`/bar viz + one stage-conversion table. |
| `/ads` | `PromotePage` (`Insights` KPI band + `List` + `Engagement` + `Interactions`) | ADAPT | Insights→ad-spend/ROAS KPIs; List→campaigns/ad-sets; charts→impressions/clicks. |

**G2 — Lists & CRM**
| Route | Reference source | Action | Data swap |
|---|---|---|---|
| `/leads` | `Customers/CustomerList/CustomerListPage` | REUSE-DIRECT | Leads (name, phone, status, source, last-contact); Search + Tabs(All/Hot/Warm/Cold) + `useSelection` bulk bar + row→detail. |
| `/crm` (+`[id]`) | List=`CustomerList`; `[id]`=`CustomerList/DetailsPage` | ADAPT | List→CRM contacts; `[id]`→profile card + activity/notes tabs (master-detail). |
| `/calls` | `Income/EarningPage`→`Transactions` (dense table) | REUSE-DIRECT | Rows→call log (time, number, campaign, outcome `Badge`, duration, cost, recording); row→detail. |
| `/callbacks` | `Notifications` (list + `Filter`), or `CustomerList` | ADAPT | Rows→scheduled callbacks (who/when/campaign/status); filter by date/status. |
| `/suppression` (Do-Not-Call) | `Customers/CustomerList` (search + table + bulk delete) | REUSE-DIRECT | Suppressed numbers; Search; `FieldFiles` bulk-upload DNC; `DeleteItems` bulk-remove. |
| `/payments` | `Income/PayoutsPage` | REUSE-DIRECT | Payments (amount, method, status `Badge`, date); reuse table + chips. |

**G3 — Conversations & Booking**
| Route | Reference source | Action | Data swap |
|---|---|---|---|
| `/whatsapp` | `MessagesPage` (conversation list + thread `Details`) | REUSE-DIRECT | WhatsApp threads (contact list left, chat right, composer=`Message`/`Editor`). Closest 1:1 — port as-is. |
| `/support` | `MessagesPage` (same chat shell), or `Notifications` for tickets | ADAPT | Ticket list→list; thread→Details. Same chat shell as WhatsApp for consistency. |
| `/booking` | `Products/ScheduledPage` (`ScheduleProduct` + `DateAndTime`) | ADAPT | Scheduled list→bookings (customer, service, slot via `DateAndTime`, status `Badge`). |

**G4 — Billing & Settings & Admin**
| Route | Reference source | Action | Data swap |
|---|---|---|---|
| `/billing/overview` | `Income/EarningPage` (`Balance` + `RecentEarnings` + `Transactions` + `Countries`) | REUSE-DIRECT | Balance→wallet/credit + spend KPIs; RecentEarnings→spend chart; Transactions→recent charges; Countries→spend-by-vendor. |
| `/billing/explorer` (Spending) | `Income/StatementsPage` (Statistics + Transactions) | REUSE-DIRECT | Statistics→cost-over-time (`Filters`/`Range` date range); Transactions→line-item costs. |
| `/billing/audit` | `Income/StatementsPage`→`Transactions` | REUSE-DIRECT | Immutable audit events (ts, actor, action, channel, result). Read-only, no bulk. |
| `/billing/vendors` | `Income/EarningPage`→`Countries` ranked list, or `Products/OverviewPage` | ADAPT | Vendors (ElevenLabs/Groq/Sarvam/Vobiz) with spend, share %, status; `Percentage` trend. |
| `/billing/plan` (Plan) | `UpgradeToProPage` (`Pricing` cards + `Faq`) | ADAPT | Pricing→current plan + tiers; below it a `Transactions` ledger. |
| `/settings` | `SettingsPage` (anchored Menu + sections) | REUSE-DIRECT | Port wholesale; sections→Profile/Password/Notifications/Billing/Team. |
| `/vendors` (admin) | `SettingsPage` sectioned config, or `Products/OverviewPage` list | ADAPT | Per-vendor keys/limits as `Field`/`Switch`/`Select` sections. Admin-gated. |
| `/webhooks` | `SettingsPage` section pattern (`Field`+`Switch`+`Button`) | ADAPT | Each webhook = a settings card (URL, events, secret, enabled, test). |
| `/login` | `components/Login` | REUSE-DIRECT | Port reference `Login`; swap real HD logo; wire our auth. Single clean card. |
| (Billing consolidation) | `Tabs` inside one Billing page | — | Prefer one Billing page with internal Tabs (Overview/Spending/Vendors/Plan/Audit); if routes kept, each maps 1:1 to its `Income/*` template and strips subtitles. |

**G5 — Hard / NEEDS-COMPOSE (the founder-flagged "too complex")**
| Route | Reference source | Action | Plan |
|---|---|---|---|
| `/ai-manager/*` (7 sub-routes) | `Customers/OverviewPage` + `MessagesPage` + `SettingsPage` | NEEDS-COMPOSE (collapse 7→3) | **ONE title "AI Manager", THREE plain `Tabs`, no pill-rail, no Command Center, no eyebrow.** (1) **Home** = 2-col: left "Recent activity" `Table` + ≤3-KPI `Overview` strip; right "Pending approvals" `Card` (approve/deny inline) + "Try a command" entry (merges Overview+Command-Center+History+Approvals). (2) **Try it** = one `Card` input+send+response (was Test Console). (3) **Setup** = anchored sections: what it can do + Team + PIN/risk thresholds (folds Capabilities+Authorized-Users). Delete `_shared.tsx` pill-rail + `AimHeader`; delete the `/ai-manager` spinner redirect (Home becomes index). Show **Safe / Needs approval / Blocked** badges, never raw L0-L4 (keep L-code in tooltip only). |
| `/run` (Run a Campaign) | `CustomerList` + `FieldFiles` + `Modal` | NEEDS-COMPOSE | **ONE screen, 3 `Tabs`: Source → Pick leads → Launch.** Source=`FieldFiles` (CSV/XLSX) + saved-list `Select`; Pick=`CustomerList` selectable table (`useSelection`) filtered hot/warm via `Tabs`; Launch=`Button`+`Modal` confirm with "selected N → Run" bar. No multi-page wizard. |
| `/workflows` (node builder) | React Flow + reference chrome | NEEDS-COMPOSE | **Keep React Flow canvas; reskin all chrome** with reference tokens/components: node=`card`, inspector=`SettingsPage`-style `Field` stack, toolbar/save=`Button`. Title via `<Layout title="Workflows">`, no subtitle. |
| `/forms` (+`[id]`) | List=`Products/OverviewPage` grid; `[id]`=`Products/NewProductPage` | ADAPT | List→forms grid (name, submissions, status); `[id]` editor reuses NewProductPage field stack (`Field`/`Editor`/`FieldImage`/`Switch`); `CreateFormModal`→reference `Modal`. |

### W2 acceptance checklist — the GATE every ported page must pass
(from `design/ui-design-principles.md` §7; an agent may not mark a page done until ALL pass)
- **Reuse:** a matching reference template was found and its structure ported (not re-derived); reference components used (`Card`/`Table`/`Tabs`/`Select`/`Search`/`Field`/`Button`/`NoFound`/`Spinner`/`Badge`) — nothing rebuilt.
- **Layout:** wrapped in `Layout` with a single `title`; sections are `Card`s (`text-h6` title, `pt-3`); two-column `col-left`/`col-right` rhythm, stacks on mobile.
- **Headings/type:** NO `PageHeader` eyebrow/accent/subtitle; reference type ramp only; nothing bigger than `text-h4` in content; no two stacked headings; font renders Inter Display.
- **Color:** zero raw hex (only `@theme` tokens); ≤2 saturated colors; color reserved for one primary action + status badges; shadows/radii token-based.
- **Content:** plain-language labels (glossary); ≤3-4 primary sections (overflow behind a tab/row click); tabular data is a `Table`, not a card-grid.
- **States:** loading=`Spinner`; empty=`NoFound` (icon + one line + one action); error=one token-based inline banner; no raw "undefined"/null flashes; numbers/dates formatted.
- **Nav:** the page earns its nav slot (no stub, no duplicate); active state correct.

---

## WAVE 3 — BUILD-GREEN + DEPLOY + VERIFY

Done by main thread (or one release agent) after all W2 groups have pushed.

1. **Integrate:** merge G1-G5 branches onto the W1 tip in order; resolve any
   incidental conflicts (should be near-zero given disjoint dirs).
2. **Build green:** `cd famit-panel && npm ci && npm run build` — zero TS/ESLint
   errors. Fix forward; do not disable checks. Run any existing tests.
3. **Self-review pass:** run `frontend-design` skill review + the §7 checklist
   over each changed page; spot-fix token/heading/state violations.
4. **Visual QA (local):** boot `npm run dev`; click every route. Confirm: one
   clean `text-h4` title + no subtitle anywhere; Inter Display throughout
   (compare side-by-side to the reference); AI-Manager = 3 tabs; Run = 3-tab one
   screen; Billing consolidated; nav has no stubs/jargon; empty/loading states
   render. Screenshot the 8 founder-flagged pages for the before/after.
5. **Deploy:** ship to panel.famit.in via the existing pipeline (same recipe as
   prior premium-UI waves; the frontend droplet is `famit-panel-2 143.110.247.249`
   per FORTRESS — follow `fortress/FORTRESS_DEPLOY.md` / the panel deploy recipe).
   Do NOT deploy concurrently with any Control-Layer deploy.
6. **Verify live:** load panel.famit.in, hard-refresh (bust font cache), confirm
   Inter Display + clean headings on the live pages, no console errors. Notify
   founder with the 8-page before/after screenshots.

### Crash-safe protocol (every wave)
- Commit per verified unit (W1) / per ported page (W2); push before the next.
- Keep a `STATE.md` per branch with the one IN-PROGRESS item flipped to DONE on
  verify. On resume: read WORKLOG.md + `git status` + STATE, verify the last unit
  builds, then continue — never restart the whole wave.

---

## SUMMARY — order of operations
1. **GATE:** wait for Control-Layer build to merge+deploy; branch off its tip.
2. **W1 (serial, 1 owner):** Inter Display app-wide · reference type tokens ·
   clean `{title,actions}` PageHeader · shell reconcile + real Logo · simplified
   nav. Build green, commit per unit.
3. **W2 (5 parallel groups, disjoint dirs):** port all 27 routes per the table
   (REUSE-DIRECT 11 / ADAPT 12 / NEEDS-COMPOSE 3); G5 = opus for the 4 hard pages,
   rest sonnet; every page passes the §7 checklist gate.
4. **W3:** integrate → build green → frontend-design review → local visual QA →
   deploy to panel.famit.in (not concurrent with Control Layer) → verify live.
