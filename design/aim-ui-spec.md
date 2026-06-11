# AI Manager — FULL UI DESIGN SPEC (page list → Core_2 source → components → API binding)

**Author:** AI Manager UI design wave · **Date:** 2026-06-10 · **Status:** READ-ONLY DESIGN
(design doc only — no app code edited, no deploy, no git). Verified against live source on disk.

**Scope:** the complete, rich AI Manager dashboard — ALL master-spec §14 pages PLUS the founder
"more and more crazy" add-on pages — built by **PORTING Core_2 templates/components**, never from
scratch. Conforms to `C:\Users\kunal\Desktop\caps\AI_MANAGER_MASTER_PROMPT.md` (DB §8, intents §11,
risk L0–L4 §6, security §7, APIs §10, UI §14, acceptance §24). Pairs with the backend service spec
`design/platform-ai-manager.md` (voice front-door) + `design/automation-aimanager.md` (orchestrator)
+ `design/credit-ledger-firewall.md` (wallet/firewall). This doc owns ONLY the dashboard surface.

---

## 0. IRON RULES (inherited from `spec-core2-reuse-map.md` — do NOT violate)

1. **NEVER invent UI.** Port Core_2's actual JSX/Tailwind page templates + components; only rewire
   data/props. Approximating ≠ reusing. The founder repeatedly rejects from-scratch UI.
2. **Prefer the REAL Core_2 components** over the prior waves' bespoke lookalikes:
   - `Table` + `TableRow` (NOT raw `<table className="data-table">`)
   - `NoFound` (NOT `.state-block`) — for empty/dormant states
   - `Tabs` + `Search isGray` + `Dropdown`/`Select` in the `Card` head row (NOT `SegBtn`/ad-hoc input)
   - `Modal` (NOT hand-rolled overlays) — detail drawers, confirms, PIN prompts
   - `Card` (`title` + `headContent` + `selectOptions`) as the wrapper for nearly every block
   - `Filters` (Modal+Select+Range+Switch) for advanced-filter popovers
   - `Button` (`isBlack`/`isStroke`/`isWhite`/`isCircle`+`icon`) — NOT raw `<button className=…>`
   - KPI strip = port `C2/templates/Products/OverviewPage/Overview` + `Overview/Item` metric tiles
     (NOT the bespoke `kpi`/`KpiCard` hero grid)
   - `useSelection` hook for any bulk-select list
3. **6 canonical archetypes** (every page maps to exactly one): (1) Dashboard, (2) List/Table,
   (3) Overview+Table, (4) Two-pane (list rail + detail), (5) Section-form, (6) Pricing/Plan.
4. **Thin pages, logic in `_lib`/client.** No business logic in React components (master §27). Pages
   render archetype JSX + bind to the `_lib` client. The client owns auth headers, the `ReadResult`
   discriminated union, and the dormant→`NoFound` mapping.
5. **Dormant-safe by construction.** Backend `/api/ai-manager/*` is DEFINED-NOT-MOUNTED + flag-OFF
   today. Every read must degrade to a premium dormant view, never an error wall — same as the
   current page + `_lib.ts` already do (404/501/503/network → `{kind:"dormant"}` → render `NoFound`).

> **C2/** = `C:\Users\kunal\Desktop\Core_2-Capsy-Dashboard\extracted\core-2-dashboard-builder-react`
> **FP/** = `C:\Users\kunal\Desktop\caps\famit-panel` (the whole Core_2 component lib is already ported here)

---

## 1. SHELL + ROUTING (do FIRST — the `_shared.tsx` tab pattern, mirror Billing exactly)

The AI Manager becomes a **multi-route section** (like Billing) instead of one tabbed page. Mirror
`FP/app/billing/_shared.tsx` → create `FP/app/ai-manager/_shared.tsx` exporting a shared masthead
`AimHeader` (a `Card`-head/`PageHeader`-style title + a pill tab-rail of sub-routes) + shared helpers
(`fmt`, `riskVariant`, `statusVariant`, `RiskBadge`, `ErrorBanner`, `selectCls`/`btnCls`).

- **Routing:** `FP/app/ai-manager/<page>/page.tsx` thin route files, one per page below. Keep the
  existing `FP/app/ai-manager/page.tsx` as the **Overview** (or redirect `/ai-manager` → `/ai-manager/overview`).
- **Client/logic:** keep + extend `FP/app/ai-manager/_lib.ts` (already the right shape: BASE, auth
  headers, `ReadResult` union, `read`/`write`, dormant mapping). Add the new reads/writes for §10 APIs.
  Split into `_lib/client.ts` (transport) + `_lib/types.ts` (record shapes) + `_lib/intents.ts`
  (intent→risk catalog) if it grows large — logic stays OUT of pages.
- **Nav:** `FP/contstants/navigation.tsx` — promote the single "AI Manager" link in the **Command**
  group to a **collapsible group** (`{title:"AI Manager", icon:"grid", roles:"manager", list:[…]}`)
  with children = Overview / Test Console / Command History / Pending Approvals / Authorized Users /
  Setup (+ "crazy" pages as roles-gated children). Same group/`comingSoon`/role-gating mechanics the
  Billing group already uses. Children self-gate writes via `canWrite`/`isAdmin` from `FP/lib/auth`.
- **RBAC:** `useMe`/`canWrite`/`isAdmin` (`FP/lib/auth`) — reads broad; Setup + Authorized-Users +
  approve/execute/revoke are manager/admin only and additionally firewall-gated server-side.

---

## 2. PAGE LIST (master §14 core + founder "crazy" add-ons)

| # | Page (route) | Archetype | Core_2 source | Primary API (§10) | Priority |
|---|---|---|---|---|---|
| 1 | **Test Console** `/ai-manager/test` | Two-pane (chat) | `MessagesPage` + `MessagesPage/Details/Chat` | `POST /commands/test`, `/commands/:id/confirm`,`/execute`,`/cancel` | **BUILD FIRST** (master §14/§26) |
| 2 | Overview `/ai-manager/overview` | Dashboard | `HomePage` + `Products/OverviewPage/Overview` + `HomePage/Comments` | `GET /dashboard/summary`, `/status`, `/sessions` | High |
| 3 | Setup `/ai-manager/setup` | Section-form | `SettingsPage` (+ `Products/NewProductPage`) | `GET/PUT /profile` | High |
| 4 | Authorized Users `/ai-manager/users` | List/Table + Modal | `Customers/CustomerList/CustomerListPage` | `GET/POST/PATCH/DELETE /authorized-users`, `/pin/*` | High |
| 5 | Command History `/ai-manager/commands` | Overview+Table + Filters | `Income/StatementsPage/Transactions` + `Filters` | `GET /commands` (filtered) | High |
| 6 | Session Detail `/ai-manager/sessions/[id]` | Two-pane (record detail) | `Customers/CustomerList/DetailsPage` + `MessagesPage/Details/Chat` | `GET /sessions/:id`, `/audit-logs`, `/action-runs` | High |
| 7 | Pending Approvals `/ai-manager/approvals` | List/Table + Modal | `Products/CommentsPage` (+ `Income/Refunds/RefundsPage`) | `GET /commands?status=needs_*`, `confirm`/`execute`/`cancel` | High |
| 8 | **Live Command Stream** `/ai-manager/live` | Dashboard (feed) | `HomePage/Comments` + `Products/OverviewPage/ProductActivity` | `GET /sessions`+`/commands` (poll/SSE) | Add-on |
| 9 | **Risk & Audit Analytics** `/ai-manager/risk` | Dashboard (charts) | `Customers/OverviewPage` + `Products/OverviewPage/Products/ProductsStatistics` | `GET /audit-logs`, `/commands` (aggregate) | Add-on |
| 10 | **Capability Catalog** `/ai-manager/capabilities` | List/Table (browseable) | `Shop/ShopPage` (grid) + `UpgradeToProPage/Faq` | static §11 intent map + `/profile` grants | Add-on |
| 11 | **Spend Guard** `/ai-manager/spend` | Overview+Table | `Income/EarningPage` (Balance + Transactions + Countries) | `GET /dashboard/summary`,`/action-runs`,`/profile` (+ wallet) | Add-on |
| 12 | **Voice Session Player** `/ai-manager/sessions/[id]/play` | Two-pane (media) | `MessagesPage/Details` + `Products/NewProductPage/Demos` | `GET /sessions/:id`, `/voice/recording` | Add-on |
| 13 | Registered Numbers `/ai-manager/numbers` | List/Table + side form | (existing page tab) `CustomerListPage` + register form | `GET/POST /numbers`, `verify`/`grants`/`revoke` | Keep (absorb existing) |

> The current `FP/app/ai-manager/page.tsx` (3-tab: Command/Numbers/Sessions) is **superseded** —
> its Command tab → Overview (#2), Numbers tab → #13, Sessions tab → History (#5)/Detail (#6). Its
> `_lib.ts`, dormant pattern, `ConfigRow`, `CommandExample` and `RegisterForm` are **reused verbatim**.

---

## 3. PER-PAGE DESIGN (Core_2 port → components → API binding → loading/empty/error/dormant)

### ⭐ 1. TEST CONSOLE — `/ai-manager/test` (BUILD FIRST)
The dashboard chat that hits the **same command engine** (master §14 "Test Console FIRST", §3.3
wire to REAL API). This is the proof the engine works without a phone.

- **Archetype:** Two-pane (chat). **Core_2 source:** `C2/templates/MessagesPage` (list rail + detail)
  and especially **`C2/templates/MessagesPage/Details/Chat/index.tsx`** (the message thread + composer)
  — already ported as `FP/components/Message` + the MessagesPage template structure.
- **Components (FP/):** `Layout`, `_shared.tsx` `AimHeader`, `Card` (`p-0 overflow-hidden`),
  `Message` (per-turn bubble), `Field`/textarea composer + `Button isBlack` "Send", `Badge` (risk),
  `Modal` (the **step-up PIN prompt** — masked `Field type=password`, `Switch` for "remember session"),
  `Tabs` ("Chat" / "JSON trace"), `Dropdown` (act-as channel: dashboard/whatsapp/phone-sim),
  `Spinner` (engine thinking), `NoFound` (empty thread).
- **Layout:** left rail = past test sessions (port MessagesPage list rows, fed by `GET /sessions?channel=dashboard`);
  right = chat thread. Each USER bubble = raw utterance; each AI bubble shows the **NLU result card**
  (master §22 schema: intent · action_type · risk_level `Badge` · `requires_confirmation`/`requires_pin`
  · entities · missing_fields · `user_facing_summary` · `safe_to_execute`). When `requires_confirmation`
  → an inline **confirm/cancel** action row (Core_2 comment-answer action style). When `requires_pin`
  → open the PIN `Modal`. On execute → show `execution_result` + cost + linked `action_run`.
- **API binding (§10):** `POST /commands/test` (text→engine, returns the §22 JSON + a `command_id`);
  then `POST /commands/:id/confirm`, `POST /commands/:id/execute`, `POST /commands/:id/cancel`. PIN via
  `POST /pin/verify` (never sends raw PIN to logs; backend hashes). Streaming optional later.
- **States:** *loading* = composer disabled + `Spinner` "thinking"; *empty* = `NoFound` "Type a command
  to test the engine" + 4 example chips from master §23 ("Aaj ka report WhatsApp kar do", "Meta budget
  500 kar do", "Call all hot leads after 5 PM", "Wallet balance?"); *error* = `ErrorBanner` (engine
  parse failure, §21) inline, thread survives; *dormant* = `NoFound` "Engine not configured yet" + the
  static command-vocabulary preview (reuse existing `CommandExample` cards) so the page is alive offline.
- **Safety:** blocked intents (L4) render a red "Refused" bubble with `block_reason` (master §22), no
  execution. Wrong PIN → masked "PIN did not match" (§13), never reveals data.

### 2. OVERVIEW — `/ai-manager/overview`
Status, phone number, today/successful/failed-denied commands, pending approvals, credit impact,
recent sessions, recent risky actions, quick test input (master §14).

- **Archetype:** Dashboard. **Core_2 source:** `C2/templates/HomePage` (`col-left`/`col-right` frame +
  `HomePage/Overview` tabbed metric card + `HomePage/Comments` activity feed) and
  `C2/templates/Products/OverviewPage/Overview` (+ `Overview/Item`) for the KPI metric strip.
- **Components (FP/):** `Layout`, `AimHeader`, `Card`, ported `Overview`+`Item` metric tiles
  (Today / Succeeded / Failed-or-denied / Pending approvals / Credit impact ₹), `Percentage`,
  `PopularProducts`-shaped "Recent risky actions" list, `RefundRequests`-shaped "Recent sessions" list,
  `Badge` (status/risk), the existing `ConfigRow` board (SIP/LLM/OTP/cross-plane), a `Button isBlack`
  "Open Test Console" + inline quick-test `Field` (posts to `/commands/test`, deep-links to #1).
- **API binding (§10):** `GET /dashboard/summary` (counts + credit impact), `GET /status` (config
  pills — reuse existing `AimStatus`), `GET /sessions?limit=5`, `GET /commands?risk=L3&limit=5`.
- **States:** *loading* = `skeleton` tiles + 3-row list skeletons; *empty* = `NoFound` per list;
  *error* = `ErrorBanner` per card, others still render; *dormant* = the existing premium "coming soon"
  explainer (Verify→Authorize→Delegate `FlowStep`s) is reused verbatim as the primary state.

### 3. SETUP — `/ai-manager/setup`
Enable, phone, language, voice, confirm policy, require-PIN-from-level, daily/monthly spend limit,
calling hours, timezone (master §14, DB `ai_manager_profiles` §8).

- **Archetype:** Section-form. **Core_2 source:** `C2/templates/SettingsPage` (left sticky `Menu` +
  `react-scroll` anchored `Card` sections — `Password`/`Notifications`/`Payment` patterns) for the
  multi-section settings; field rows from `C2/templates/Products/NewProductPage/ProductDetails`.
- **Components (FP/):** `Layout`, `AimHeader`, sticky section `Menu`, `Card` per section, `Field`
  (phone, limits), `Select` (language, default voice provider, timezone), `Switch` (enabled,
  per-channel), a **risk-threshold `Select`** ("require PIN from level" L0–L4 → `require_pin_for_level`),
  `Range` (daily/monthly spend limit, `max_bulk_leads_without_pin`), `DateAndTime`/time `Select`
  (`allowed_call_start_time`/`end_time`), `Button isBlack` "Save". Save guarded behind a `Modal` confirm
  (changing spend caps is itself sensitive).
- **API binding (§10):** `GET /profile` (hydrate), `PUT /profile` (save). Spend-cap + PIN-threshold
  changes may trigger a server-side step-up (`Modal` PIN) — surface 403 as "needs step-up PIN".
- **States:** *loading* = section skeletons; *empty* = first-run defaults pre-filled; *error* =
  `ErrorBanner` + keep form values; *dormant* = read-only sections + "save once the service is live"
  banner (mirror existing `RegisterForm` disabled-state copy). PIN-from-level shows the §6 risk legend.

### 4. AUTHORIZED USERS — `/ai-manager/users`
Table: name/phone/role/permission/PIN-status/active/last-used/failed-attempts/lock; add/edit/disable/
reset-PIN/set-perms (master §14, DB `ai_manager_authorized_users` §8). Absorbs the existing
RegisterForm/numbers logic.

- **Archetype:** List/Table + Modal. **Core_2 source:** `C2/templates/Customers/CustomerList/CustomerListPage`
  (+ `…/CustomerListPage/List`) — head row `[title + Search isGray + Tabs + Button isBlack]`, body
  `Table`+`TableRow` with `useSelection`. Add/edit drawer = `C2/components/Modal`.
- **Components (FP/):** `Layout`, `AimHeader`, `Card`, `Search`, `Tabs` (All/Active/Locked), `Table`+
  `TableRow`, `Badge` (role, active, **PIN-set vs PIN-missing**, **locked-until**), `Modal` (add/edit
  user form — reuse the existing `RegisterForm` field set: phone, label, role `Select`, verify-mode,
  capability **grant chips**, permissions JSON via grant toggles), `Switch` (is_active),
  `Button isStroke` row actions: Reset PIN / Disable / Set Permissions, `NoFound` empty.
- **API binding (§10):** `GET /authorized-users`, `POST /authorized-users`, `PATCH/DELETE
  /authorized-users/:id`; PIN flows `POST /pin/set`,`/pin/reset/request`,`/pin/reset/confirm` (never
  show raw PIN — only `pin_set_at` / `failed_pin_attempts` / `locked_until` per §7).
- **States:** *loading* = row skeletons; *empty* = `NoFound` "No authorized users" + "Add" CTA;
  *error* = `ErrorBanner`; *dormant* = existing dormant copy ("register once backend provisioned").
  Reset-PIN / revoke are admin-only + firewall-gated (403 → "needs step-up PIN").

### 5. COMMAND HISTORY — `/ai-manager/commands`
Date, user/caller, channel, command text, intent, risk, status, result, cost, details; filters:
status/channel/risk/date/user/module (master §14, DB `ai_manager_commands` §8).

- **Archetype:** Overview+Table + Filters. **Core_2 source:** `C2/templates/Income/StatementsPage/Transactions`
  (table with period `Select` + download) for the table; KPI strip from `Products/OverviewPage/Overview`;
  advanced filter popover = `C2/components/Filters` (Modal+Select+Range+Switch).
- **Components (FP/):** `Layout`, `AimHeader`, ported `Overview`+`Item` (Total / Succeeded / Denied /
  Spend) KPI strip, `Card`, `Search` (command text), `Tabs` (status quick-filter), `Filters`
  (channel/risk/date-range/user/module), `Select` (period), `Table`+`TableRow`, `Badge` (risk via
  shared `riskVariant`, status), a per-row `Button isCircle icon="arrow"` → Session Detail (#6),
  `NoFound`, `Button isStroke` "Export CSV".
- **API binding (§10):** `GET /commands?status=&channel=&risk=&from=&to=&user=&module=&limit=` —
  server-filtered (multi-tenant scoped). Row → `GET /sessions/:id` via `session_id`.
- **States:** *loading* = KPI + row skeletons; *empty* = `NoFound` "No commands match these filters";
  *error* = `ErrorBanner`; *dormant* = `NoFound` "History appears once the engine runs" + sample
  legend. Filters persist in URL query so a filtered view is shareable.

### 6. SESSION DETAIL — `/ai-manager/sessions/[id]`
Full transcript, command chain, recording link, execution timeline, audit logs, provider metadata,
errors (master §14, DB `ai_manager_sessions`+`commands`+`audit_logs`+`action_runs` §8).

- **Archetype:** Two-pane (record detail). **Core_2 source:** `C2/templates/Customers/CustomerList/DetailsPage`
  (`Customer` header block + `Details` + `Details/PurchaseHistory` repurposed as the **command chain /
  execution timeline**) + **`C2/templates/MessagesPage/Details/Chat`** for the **transcript thread**.
- **Components (FP/):** `Layout`, `AimHeader` (with back link), `Card`, a header summary block (caller,
  channel `Badge`, auth method, outcome `Badge`, duration), **transcript** = `Message` bubbles
  (PIN-masked per §7), **command chain** = a vertical timeline (port PurchaseHistory rows: each command
  = intent · risk `Badge` · permission_result · pin_verified · status · cost · `execution_result`),
  **audit logs** = `Table`+`TableRow` (immutable events, severity `Badge`), **action runs** = status
  `Badge` rows with job_id/output/error, **recording** = `Button isStroke` "Open in Player" → #12,
  provider metadata strip (`stt/tts/llm_provider`).
- **API binding (§10):** `GET /sessions/:id` (transcript + command chain + provider meta),
  `GET /audit-logs?session_id=`, `GET /action-runs?command_id=`. Recording via `GET /voice/recording`.
- **States:** *loading* = header + pane skeletons; *empty* = `NoFound` "Session not found / no actions";
  *error* = `ErrorBanner`; *dormant* = `NoFound` (no sessions until live). PIN/secrets always masked (§7).

### 7. PENDING APPROVALS — `/ai-manager/approvals`
Commands needing approval/PIN/review (master §14). The human-in-the-loop queue.

- **Archetype:** List/Table + Modal. **Core_2 source:** `C2/templates/Products/CommentsPage`
  (+ `…/CommentsPage/List`/`Answer`) — the "items awaiting your action with inline approve/deny" pattern;
  alt `C2/templates/Income/Refunds/RefundsPage` (request-queue with accept/decline).
- **Components (FP/):** `Layout`, `AimHeader`, `Card`, `Tabs` (Needs confirm / Needs PIN / Needs review),
  list rows (each = utterance + intent + risk `Badge` + cost_estimate + requester), inline
  **Approve / Deny** `Button`s (Approve opens **PIN `Modal`** when `pin_required`), `Badge`,
  `NoFound` ("All clear — nothing pending"), `useSelection` for **bulk approve/deny** (each still PIN-gated).
- **API binding (§10):** `GET /commands?status=needs_confirmation,needs_pin` (+ a review status);
  `POST /commands/:id/confirm`, `POST /commands/:id/execute` (after PIN), `POST /commands/:id/cancel`.
- **States:** *loading* = row skeletons; *empty* = `NoFound` "Nothing pending"; *error* = `ErrorBanner`;
  *dormant* = `NoFound` "Approvals appear when commands need human sign-off". Badge count feeds the nav
  group (like the existing `pendingNumbers` pill).

---

## 4. FOUNDER "CRAZY" ADD-ON PAGES (rich, all Core_2-ported)

### 8. LIVE COMMAND STREAM — `/ai-manager/live`
A real-time wall of commands as they hit the engine (the "war room").
- **Archetype:** Dashboard (feed). **Core_2 source:** `C2/templates/HomePage/Comments` (live feed
  cards) + `C2/templates/Products/OverviewPage/ProductActivity` (activity timeline) + `HomePage/Overview`
  tabbed counters on top.
- **Components (FP/):** `Layout`, `AimHeader`, ported `Overview`/`Item` live counters (active sessions /
  commands-per-min / pending / blocked), feed cards (`Comments` shape: caller + utterance + risk `Badge`
  + live status `Badge` animating pending→executing→done via existing `rise-in`), `Spinner`, `NoFound`.
- **API binding:** poll `GET /sessions` + `GET /commands?limit=20` on an interval (SSE later via
  `/voice/events`). Pure read.
- **States:** *loading* = pulsing skeletons; *empty* = `NoFound` "Quiet right now"; *dormant* = `NoFound`
  "Live stream lights up when the voice line is on".

### 9. RISK & AUDIT ANALYTICS — `/ai-manager/risk`
Charts: commands by risk level, PIN-pass vs fail, blocked-action reasons, denials over time,
top intents, compliance blocks.
- **Archetype:** Dashboard (charts). **Core_2 source:** `C2/templates/Customers/OverviewPage`
  (`Overview/Chart` area chart + `TrafficСhannel` bars + `ActiveTimes` heat) +
  `C2/templates/Products/OverviewPage/Products/ProductsStatistics` (`ProgressBar`/`Legend` donut/bars).
- **Components (FP/):** `Layout`, `AimHeader`, `Card`, recharts (already a dep — see `_shared.tsx`)
  for area/bar/donut, `CardChartPie`, `Percentage`, `ProgressBar`/`Legend` ports, `Select` (period),
  `Badge`. Real aggregates only (no fabricated deltas — see `KpiCard` doctrine).
- **API binding:** `GET /audit-logs` + `GET /commands` aggregated client-side (or a `/dashboard/summary`
  rollup). Read-only.
- **States:** standard skeleton/`NoFound`/`ErrorBanner`/dormant.

### 10. CAPABILITY CATALOG — `/ai-manager/capabilities`
A browseable catalog of every intent the AI Manager can execute (master §11 taxonomy) — what the
vendor's number is allowed to do, by risk.
- **Archetype:** List/Table (browseable grid). **Core_2 source:** `C2/templates/Shop/ShopPage` (filterable
  grid of cards) + `C2/templates/UpgradeToProPage/Faq` (expandable "what does this do" rows).
- **Components (FP/):** `Layout`, `AimHeader`, `Card`, `Search` + `Tabs` (by module: analytics/campaign/
  creative/lead/call/whatsapp/workflow/billing/booking) + `Filters` (by risk L0–L4), capability cards
  (reuse existing `CommandExample` styling: example utterance + `maps:` intent code + risk `Badge` +
  "your grants allow ✓/✗"), `Badge`, `NoFound`.
- **API binding:** static §11 intent map (shipped in `_lib/intents.ts`) cross-referenced with the
  vendor's grants from `GET /profile` + authorized-user grants. Read-only; no execution from here.
- **States:** static so always renders; grant-state shows dormant gracefully (all "✗ — configure first").

### 11. SPEND GUARD — `/ai-manager/spend`
Money custody view: wallet balance, holds reserved by pending commands, settled spend by the AI
Manager, daily/monthly caps vs usage, low-balance alert (master §19, `credit-ledger-firewall.md`).
- **Archetype:** Overview+Table. **Core_2 source:** `C2/templates/Income/EarningPage` (`Balance` +
  `Transactions` + `Countries`/`RecentEarnings`) — the canonical money screen.
- **Components (FP/):** `Layout`, `AimHeader`, ported `Balance` hero (available / held / spent today /
  cap), the `_shared.tsx` `Sparkline`/`CostDonut`/`ShareRow` (spend by module), `meter` cap bars,
  `Table`+`TableRow` (recent billable action_runs: estimate vs actual), `Badge`, `Button isStroke`
  "Raise cap" (→ Setup #3), `NoFound`.
- **API binding:** `GET /dashboard/summary` (credit impact) + `GET /action-runs` (billable runs) +
  `GET /profile` (caps) + wallet balance (reuse the platform wallet read). Read; cap edits go to Setup.
- **States:** standard; *low-balance* = amber `ErrorBanner` "Top up to keep paid commands running" (§19).

### 12. VOICE SESSION PLAYER — `/ai-manager/sessions/[id]/play`
A media player that plays the call recording synced to the transcript + the command chain.
- **Archetype:** Two-pane (media). **Core_2 source:** `C2/templates/MessagesPage/Details` (thread pane)
  + `C2/templates/Products/NewProductPage/Demos` (media/preview block) for the player surface.
- **Components (FP/):** `Layout`, `AimHeader`, `Card p-0 overflow-hidden`, native `<audio>` player in a
  ported `Demos`-style frame, transcript `Message` bubbles that highlight in time-sync, a timeline rail
  marking where each command/PIN/execution fired (port PurchaseHistory rows), `Badge`, `NoFound`
  ("No recording for this session").
- **API binding:** `GET /sessions/:id` (transcript + timestamps) + `GET /voice/recording` (audio URL).
- **States:** *empty* = `NoFound` "Recording unavailable"; PIN always masked in transcript; *dormant*
  = `NoFound`.

### 13. REGISTERED NUMBERS — `/ai-manager/numbers` (absorb existing)
Keep the existing Numbers tab verbatim as its own route — table of command-authorized caller-IDs +
side register form (role + grants + verify-mode + verify/revoke).
- **Core_2 source:** `Customers/CustomerList/CustomerListPage` + the existing `RegisterForm`.
- **API:** existing `GET/POST /numbers`, `POST /numbers/:id/verify|grants|revoke` (already in `_lib.ts`).
- This overlaps Authorized Users (#4) conceptually; keep both — Numbers = caller-ID identity registry,
  Users = the people/roles/PINs. Cross-link them.

---

## 5. SHARED `_lib` CONTRACT (extend the existing `FP/app/ai-manager/_lib.ts`)

Keep the existing exports (`getAimStatus/Numbers/Sessions`, `register/verify/revoke`, `ReadResult`,
`KNOWN_GRANTS`, `AIM_ROLES`). ADD (all via the same `read`/`write` + dormant mapping):

- `getAimSummary()` → `GET /dashboard/summary` · `getAimProfile()`/`putAimProfile()` → `/profile`
- `getAimUsers()`/`createUser()`/`patchUser()`/`deleteUser()` → `/authorized-users[/:id]`
- `setPin()`/`requestPinReset()`/`confirmPinReset()` → `/pin/*` (raw PIN never logged/returned)
- `getCommands(filters)` → `GET /commands?…` · `getCommand(id)` → `/commands/:id`
- `getSession(id)` → `/sessions/:id` · `getAuditLogs(q)` → `/audit-logs` · `getActionRuns(q)` → `/action-runs`
- `testCommand(text, channel)` → `POST /commands/test` · `confirm/execute/cancel(id)` → `/commands/:id/*`
- `INTENT_CATALOG` (static §11 map) in `_lib/intents.ts` for the Capability Catalog.

Every read returns `ReadResult<T>` → page maps `dormant`→`NoFound`, `error`→`ErrorBanner`, `ok`→render.
Every write throws a friendly message; 403 → "needs permission or a step-up PIN" (already the pattern).

---

## 6. CROSS-CUTTING UI RULES

- **One header rhythm:** every page uses `_shared.tsx` `AimHeader` (eyebrow "AI Manager" + title +
  subtitle + the pill tab-rail), mirroring `BillingHeader`.
- **Risk colour language (single source):** L0 safe→`success`, L1 low→`info`, L2 medium→`warning`,
  L3 high→`danger`, L4 blocked→`danger`+lock glyph. Centralize `riskVariant()` in `_shared.tsx`.
- **PIN/secret masking everywhere** (master §7/§13): never render raw PIN; show pin_set/failed/locked
  only; wrong-PIN copy reveals nothing.
- **Multi-tenant:** all reads server-scoped by tenant; UI never builds cross-vendor links. (Tenant
  isolation is enforced backend per §20 — UI just consumes scoped data.)
- **Dormant-first:** ship every page so it looks premium with ZERO backend (flag OFF) via `NoFound` +
  static legends — exactly how the current page degrades. This is the acceptance bar until creds land.
- **No bespoke chrome:** no new `data-table`/`state-block`/`SegBtn` — use `Table`/`TableRow`/`NoFound`/
  `Tabs`/`Search`/`Filters`/`Modal`/`Button`. (The prior page's bespoke bits that DON'T have a Core_2
  equivalent — `ConfigRow`, `CommandExample`, `FlowStep`, the dormant explainer — are reused as-is.)

---

## 7. BUILD ORDER (master §26: Test Console FIRST)
1. `_shared.tsx` + `_lib` extension + nav group regroup (shell).  →  2. **Test Console** (#1, proves engine).
→ 3. Overview (#2). → 4. Command History (#5) + Session Detail (#6). → 5. Pending Approvals (#7).
→ 6. Setup (#3) + Authorized Users (#4) + Numbers (#13). → 7. Add-ons: Live (#8), Risk (#9),
Capabilities (#10), Spend Guard (#11), Player (#12). Each page is thin + dormant-safe + Core_2-ported;
verify it renders premium with the backend OFF before wiring the next.
