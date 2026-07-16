# DESIGN SPEC — WHATSAPP CAMPAIGN BUILDER ▸ **FRONTEND** (premium campaign WORKSPACE)

> **Status:** EXECUTION-READY FRONTEND DESIGN (READ-ONLY wave — writes NO app code, edits no
> `caller.py`/`page.tsx`, does NO git, does NOT deploy). It specifies the **premium multi-card WhatsApp
> Campaign Builder UI** that replaces today's 2-card `app/whatsapp/page.tsx` — an Apple-like campaign
> WORKSPACE (not a form), per `CREATIVE_STUDIO_PHASE2_SPEC.md §2`.
>
> **Authoritative parents:** `CREATIVE_STUDIO_PHASE2_SPEC.md` (§2 the founder ask) +
> `CREATIVE_STUDIO_MASTER_PROMPT.md` (the 42-section DNA, NO-INVENT guardrails) +
> `design/creative-studio-integrations.md` (§2 the WhatsApp seam — the `creative.*` contract this UI calls).
> **UI rule (non-negotiable, [[ui-reuse-core2-never-from-scratch]]):** PORT the reference kit
> `C:\Users\kunal\Desktop\core-2-dashboard-builder-react` COMPONENTS verbatim; layouts are intentional per
> workflow. Inter Display app-wide; single `Layout title` (NO subtitle/eyebrow per the shipped W1 shell);
> zero raw hex (Signal tokens only); consult the `frontend-design` skill (restraint IS the design).
>
> **WhatsApp is now LIVE end-to-end** (real send proven; webhook GET/POST `/whatsapp/inbound` + POST
> `/whatsapp/send`; report `WHATSAPP_GOLIVE.md`). So this UI is NOT dormant-first: the send/log path is
> real today; the AI-template-gen + creative-attach + analytics surfaces degrade to a premium
> `not_configured` state until the LLM/Asset-Service/Meta-template creds land (master §dormant-safe).

Design date: 2026-06-11. Verified against `app/whatsapp/page.tsx` (current 2-card page), the reference
kit's `templates/` + `components/`, and the already-ported `famit-panel/components/*`.

---

## 0. THE ONE-SCREEN MODEL (read first)

The WhatsApp page becomes **one route, `/whatsapp`, driven by a horizontal STEP RAIL** (a `Tabs`-style
stepper, NOT a wizard that hides state) over an **11-step campaign pipeline**. The default landing view is
a **dashboard/launchpad** (campaign cards + KPIs + winning-template gallery); selecting a campaign drives
the pipeline left-to-right. Every step is a stack of **`card`s composed from already-ported reference
components** — never a bespoke widget. The user always sees a **live WhatsApp phone PREVIEW** pinned to the
right column from Template Preview onward (the `ProductView`/`Message` pattern re-skinned as a phone mock).
The whole thing reuses the **3-archetype layout** the kit already ships: dashboard 2-col (`HomePage`),
list+detail master-detail (`MessagesPage`), and card-grid gallery (`Products/DraftsPage`).

```
 /whatsapp  ── Layout title="WhatsApp campaigns"
 ┌──────────────────────────────────────────────────────────────────────────────────┐
 │  STEP RAIL  (Tabs, horizontal, scrollable):                                        │
 │  ① Launchpad → ② Campaign → ③ AI Templates → ④ Creative → ⑤ Banner Studio →        │
 │  ⑥ Preview → ⑦ Approval → ⑧ Audience → ⑨ Schedule → ⑩ Delivery → ⑪ Analytics       │
 ├──────────────────────────────────────────────────────────────────────────────────┤
 │  col-left  (workspace / cards)                  │  col-right  (phone PREVIEW +     │
 │  ── step body: card grid / list / form ──       │   campaign-context / AI-suggest) │
 └──────────────────────────────────────────────────────────────────────────────────┘
```

The pipeline maps **1:1 to the founder flow** (§2 of the spec): Campaign Selection → AI Template
Generation → Creative Selection → Banner Generation/Selection → Template Preview → Approval → Audience
Selection → Scheduling → WhatsApp Delivery → Analytics → Optimization/Reuse. **Optimization is not a step**
— it lives as "winning template" reuse cards surfaced on ① Launchpad and ⑪ Analytics (clone/repurpose),
matching the master's learning-loop ("surface winning templates").

---

## 1. REFERENCE-KIT REUSE MAP (the copy-from spec — exact components/templates per surface)

All listed components ALREADY exist in `famit-panel/components/` (ported in W1) unless flagged **(compose)**
= assemble from existing primitives, no new design language. Templates are the reference layout to port.

| Builder surface | PORT reference template | Reuse these ported components |
|---|---|---|
| **Page shell + step rail** | `templates/MessagesPage` card-shell + `Tabs` stepper | `Layout` (single title), `Tabs`, `Card`, `Search`, `Button`, `Icon` |
| **① Launchpad (dashboard)** | `templates/HomePage` (2-col `Overview`+`OverviewSlider`+`Comments`) | `Card`, `KpiCard`, `Percentage`, `Sparkline`, `CardChartPie`, `Product`, `Button`, `Tabs`, `Badge` |
| **② Campaign Selection** | `templates/Customers/CustomerList` (searchable list+select) | `Card`, `Search`, `Table`/`TableRow`, `Badge`, `Filters`, `useSelection` hook, `Product` (campaign card), `Modal` |
| **③ AI Template Generation** | `templates/PromotePage` `Insights`+`List` (recommendation cards) | `Card`, **AI-suggestion card (compose** from `Card`+`Badge`+`Button`+`Icon`), `Tabs`, `Editor` (copy edit), `Tooltip` |
| **④ Creative Selection (gallery)** | `templates/Products/DraftsPage` `Grid` (card-grid + view toggle) | `GridProduct`, `Product`, `Image`, `Search`, `Filters`, `Tabs` (grid/list), `useSelection`, `Badge`, `NoFound` |
| **⑤ Banner Studio (gen/select)** | `templates/Products/NewProductPage` `Images`/`CoverImage` 2-col | `FieldImage`, `FieldFiles`, `Card`, `Button`, `Modal`, **AI-loader (compose**, §6 of PHASE2), `Image`, `Range` |
| **⑥ Template Preview (phone mock)** | `templates/MessagesPage` `Message`+`Details` (chat bubble) | **Phone mock (compose** from `Card`+`Image`+`Message` bubble), `Switch`, `Tabs`, `Button`, `Tooltip` |
| **⑦ Approval** | `templates/Products/CommentsPage` review row + `Modal` confirm | `Card`, `Badge`, `Button`, `Modal`, `Switch`, `Tooltip`, `LockOverlay`/`EntitlementGuard` (gate) |
| **⑧ Audience Selection** | `templates/Customers/CustomerList` + `PromotePage` `Insights` | `Table`/`TableRow`, `Filters`, `Search`, `useSelection`, `Checkbox`, `KpiCard`, `Percentage`, `CardChartPie` (segment donut) |
| **⑨ Scheduling** | `templates/Products/ScheduledPage` + `ScheduleProduct` | `ScheduleProduct`, `DateAndTime`, `Card`, `Switch`, `Select`, `Button` |
| **⑩ Delivery (live)** | `templates/Income/StatementsPage` (status table) | `Card`, `Table`/`TableRow`, `Badge`, `Spinner`, `Percentage`, `Sparkline`, `Search` |
| **⑪ Analytics + Optimization** | `templates/Income/EarningPage` + `Products/OverviewPage` (`ProductActivity`) | `KpiCard`, `CardChartPie`, `Sparkline`, `Percentage`, `Card`, `Table`/`TableRow`, `Product` (winning-template reuse cards), `Tabs` |

**Net-new = ZERO new component families.** The only "compose" pieces (AI-suggestion card, phone mock,
AI-generation loader) are assemblies of existing primitives + the §6 PHASE2 loader — no new design DNA.
The phone mock is a `Card` with a fixed `w-90` aspect frame wrapping the `Message` chat bubble re-styled to
WhatsApp green-tick chrome; it does NOT introduce a new component, it RESTYLES `Message`.

---

## 2. THE 11 STEPS (screen-by-screen — what each card shows, which component, which `creative.*`/WA call)

### ① LAUNCHPAD — the campaign home (default view, NO campaign selected yet)
**Layout:** `HomePage` 2-col. **Top row** = 4 `KpiCard`s (Active campaigns · Messages sent (30d) ·
Avg read-rate · Avg reply-rate) each with `Sparkline`+`Percentage`. **col-left** = "Your WhatsApp
campaigns" `Product`-style cards (a grid of campaign cards: name, objective `Badge`, last-sent, mini
read/reply bars) + a primary `Button isBlack` "New campaign". **col-right** = two stacked cards:
**"Winning templates"** (the optimization/reuse surface — `Product` cards of top-performing template+banner
combos with a "Clone" `Button`, master "surface winning templates") and **"Needs approval"** (a short list
of drafts awaiting the ⑦ gate, deep-links into the pipeline). Selecting a campaign card → advances to ②
pre-filled. Empty state = `NoFound`-style "Create your first campaign".
**Calls:** `getCampaigns()` (existing CRM/campaign API), `creative.search(status=winner|approved, sort=top_ctr)`.

### ② CAMPAIGN SELECTION — pick the campaign the message is FOR
**Layout:** `CustomerList`. A searchable, `Filters`-able `Table` of campaigns (Name · Objective · Audience
size · Stage hot/warm · Last activity) with single-select (`useSelection`). col-right = a **Campaign
Context card** (the master's "Campaign Context Panel" — what data the AI will use: business name, product,
location, price, offer, audience, goal, brand style, language) rendered read-only from the campaign record
so the user SEES the inputs before AI runs. A `Button isBlack` "Generate templates →" advances to ③.
**No-invent reminder rendered inline:** a muted note "AI uses only your campaign's real data — never
invents price, offer, or claims" (master §20).
**Calls:** `getCampaigns()`; on select, hydrate the Context card from the campaign record.

### ③ AI TEMPLATE GENERATION — AI auto-writes the templates
**Layout:** `PromotePage` (`Insights` strip + `List`). On entry, fires the LLM (Groq/OpenRouter via the
service) → returns **3–5 AI template SUGGESTION cards** (compose: `Card`+`Badge` angle label+`Button`s).
Each card shows: a **template name**, the **WhatsApp body copy** (with `{{1}}` personalization tokens
highlighted), **CTA button label**, a **marketing-angle `Badge`** (Price / Urgency / Trust / Offer …,
master §8), **media recommendation** ("pair with a WhatsApp poster"), and **inline `Editor`** to tweak copy.
Card actions: **Use this** (→ ④/⑥), **Regenerate** (`creative.regenerate`-style for copy), **More variations**.
A top `Insights`-style strip shows AI rationale ("Built from: objective=site-visit, audience=hot, language=Hinglish").
**Loader:** while generating, show the §6-PHASE2 **dot-matrix AI loader** ("Understanding campaign →
Writing message → Designing CTA → Finalizing") — NOT a spinner. Respect `prefers-reduced-motion`.
**Dormant:** no LLM key → cards show a premium "AI templates coming soon — write one manually" state
(falls back to today's free-text/template `Field` form, which is LIVE).
**Calls:** `POST /whatsapp/templates/generate` (new, LLM) or `creative.generate(kind=wa_text_template)`; per master NO-INVENT.

### ④ CREATIVE SELECTION — browse the Asset Library, pick a banner
**Layout:** `Products/DraftsPage` `Grid` (card-grid + grid/list `Tabs` toggle). The **asset gallery**:
`GridProduct`/`Product` cards of existing approved banners (`creative.search(platform=whatsapp,
status=approved, campaign_id, kind=wa_poster|banner)`), each with preview `Image`, angle `Badge`, creative
**score**, and "used in N campaigns". `Search` + `Filters` (campaign / platform / angle / status / size /
top-performing — master §29 facets). Select one (`useSelection`) → it attaches to the template (→ ⑥). Two
contextual `Button`s at top: **"Generate a new banner"** (→ ⑤ Banner Studio) and **"Use no image"** (text-only
template). **Version compare:** a card's overflow → `Modal` showing version lineage side-by-side (master
"browse/preview/search/filter/compare versions"). Empty/cold → `NoFound` "No banners yet → Generate one".
**Calls:** `creative.search` (integrations §2.1) — the browse/attach seam; NO manual upload.

### ⑤ BANNER STUDIO — generate or refine the banner (deep Creative Studio launch)
**Layout:** `NewProductPage` 2-col (`Images`/`CoverImage` pattern). **col-left** = a compact Creative-Studio
panel launched IN-CONTEXT (not a route jump): instruction `Field`/command box, platform/asset-type/size
`Select`s pre-filled to WhatsApp poster, model `Select`, **Generate** `Button`. **col-right** = the
**generated-variants grid** (`GridProduct`) + the **§6-PHASE2 dot-matrix loader** occupying each pending
tile until the image streams in (the founder's #1 loading ask — "Creating banner" charcoal card, breathing
dot-field, status lines "Understanding campaign → Designing visual direction → Composing layout →
Rendering → Finalizing"). NL-edit chips ("make it premium", "remove price", "Hinglish", "story size") =
`Button isStroke` row → `creative.edit` (new version). On select → asset auto-stores in the library and
returns to ④/⑥ attached (integrations §2.2). **Credit gate:** before a large gen, a `Modal` "Generating
5 banners ≈ 15 credits. Continue?" (master §35, wallet reserve). `FieldImage`/`FieldFiles` also allow the
"upload a reference → make this kind of banner" flow (master §36).
**Calls:** `creative.generate(kind=wa_poster, campaign_id, n)` → `job_id` poll; `creative.edit`; wallet reserve→settle.

### ⑥ TEMPLATE PREVIEW — the real WhatsApp message PREVIEW (phone mock)
**Layout:** master-detail (`MessagesPage`). **col-right phone mock** (compose: `Card` `w-90` frame +
restyled `Message` bubble) renders the EXACT message as WhatsApp shows it: header media (the attached
banner `Image`), body copy with tokens RESOLVED to sample values, CTA buttons as WhatsApp quick-reply/URL
chips, timestamp + double-blue-tick chrome. A `Switch` toggles **"Sample data ↔ Real lead"** to preview
personalization. **col-left** = the editable template: body `Editor`, CTA `Field`, attached-banner
thumbnail with "Change" (→ ④) / "Edit" (→ ⑤), header/footer `Field`s, language `Select` (English / Hindi /
Hinglish / Gujarati, master §14). A "Looks good → Send for approval" `Button isBlack` → ⑦.
**Calls:** none new (client-side render of the assembled template); `creative.get` for the banner bytes.

### ⑦ APPROVAL — the content-policy gate (two gates, in order)
**Layout:** review card (`CommentsPage` row) + `Modal`. Shows the assembled template + banner one more time
with a **creative-quality checklist** (readable text · brand-match · no-invented-claims · platform-fit —
master §30 score surfaced as a `Percentage`/badge row). Two explicit gates rendered as a 2-state flow
(integrations §2.3): **(a) Asset approval** — flip the banner `draft→approved` (`creative.approve`), and
**(b) Send approval** — the WhatsApp send gate (`WA_CREATIVE_REQUIRE_APPROVAL`). Money/destructive →
`LockOverlay`/step-up `Modal` (PIN) for non-writers (`EntitlementGuard` + `canWrite`). On approve → ⑧.
Note: **Meta template approval stays Meta's gate** — show its status `Badge` (Pending/Approved/Rejected),
do not fake it (integrations §2.2).
**Calls:** `creative.approve`; the WA approval toggle; surface Meta template status.

### ⑧ AUDIENCE SELECTION — who receives it (with insights)
**Layout:** `CustomerList` (list+select) + `PromotePage` `Insights` strip. **col-left** = a `Filters`-able
`Table` of leads with `useSelection` + select-all (`Checkbox`), filter by stage (hot/warm/cold/existing),
source, last-contact, campaign, do-not-call-excluded. **col-right** = **audience-insight cards**: a
`CardChartPie` segment donut (hot/warm/cold split), `KpiCard`s (reachable count · suppressed/DNC excluded ·
est. cost), and an **AI-suggestion card** ("Hot leads reply 3× more — start with 142 hot leads?"
`Button` applies the filter). Master §21/§25 stage-awareness drives a recommended default segment.
**Calls:** `getLeads()`/CRM API with filters; suppression list (DNC) auto-excluded server-side.

### ⑨ SCHEDULING — when to send
**Layout:** `ScheduledPage` + `ScheduleProduct`. A `DateAndTime` picker, **"Send now" vs "Schedule"**
`Switch`/`Tabs`, optional **send-window** (`Select` business-hours / throttle rate to respect WA limits),
and a **batch/drip** option `Switch` (master learning-loop friendly). A summary card restates: N recipients
· template · banner · est. cost · send time. `Button isBlack` "Schedule send" / "Send now".
**Calls:** `POST /whatsapp/send` (LIVE today, batched) or a scheduled-job submit (Hatchet) when present.

### ⑩ DELIVERY — live send status
**Layout:** `Income/StatementsPage` status table. A live `Table` (`TableRow`) of the send run: recipient ·
status (`Badge`: queued/sent/delivered/read/replied/failed) · timestamp, with a `Spinner` while in
flight and a top KPI strip (`KpiCard`+`Sparkline`+`Percentage`: sent / delivered / read / replied,
updating from the status webhook). `Search` to find a number. This is the existing **message-log table
elevated** (today's `app/whatsapp/page.tsx` log) into a campaign-scoped delivery view.
**Calls:** `getWhatsAppLog()` (LIVE) scoped to the run; webhook-driven status updates.

### ⑪ ANALYTICS + OPTIMIZATION — performance + reuse winners
**Layout:** `Income/EarningPage` + `Products/OverviewPage` `ProductActivity`. **Top** = KPI strip
(delivered · read-rate · reply-rate · click/booking · CPL — `KpiCard`+`Percentage`). **Charts** =
`CardChartPie` (funnel: sent→delivered→read→replied→booked) + `Sparkline` trend. **Per-variant table**
(`Table`) = each template/banner combo with its read/reply/conversion + a **`set_status(winner)`** action.
**Optimization cards** (the learning loop): **"Winning combo"** `Product` cards with **Clone / Make more
like this** (`creative.regenerate(more_like_winner)`) and **"Reuse this template for another campaign"** —
closing the master §30/§31 loop. Metrics write back to the asset via `creative.update_metrics`
(integrations §2.4, §7).
**Calls:** `creative.search(sort=top_ctr)`, `update_metrics` (writeback happens server-side from the webhook),
`set_status(winner)`, `regenerate`.

---

## 3. THE PINNED PHONE PREVIEW (the founder's "real WhatsApp message preview", always visible)

From ③ onward, the **right column pins a WhatsApp phone mock** that updates live as the user edits copy /
swaps banner / changes language. It is a `Card` framed to a phone aspect (`w-90 max-3xl:w-76`), a fixed
WhatsApp-chrome header (contact name + green online dot), and the **`Message` component restyled as a
WhatsApp bubble** (media header `Image` → body text → CTA chips → timestamp + double-tick). Tokens render
with sample values; a `Switch` swaps to a real selected lead. This is the single most important "feels real"
surface — it reuses `Message` + `Image` + `Card`, introduces NO new component, and gives the Apple-like
"see exactly what your customer sees" moment. Mobile: the preview moves to a top sticky card.

---

## 4. "OUT OF THE BOX" PROACTIVE ADDITIONS (founder §4 — proposed + prioritized)

| # | Addition | Where it lives | Priority | Why |
|---|---|---|---|---|
| 1 | **AI copy+banner co-generation** — generate the template AND its matching poster in one click | ③→⑤ bridge | **P0** | The flagship "tell it, it builds it" moment; both already exist, just chain them |
| 2 | **A/B template testing** — pick 2 variants, split the audience, surface the winner in ⑪ | ⑧+⑪ | **P0** | Directly serves the learning loop; `useSelection` multi-pick already there |
| 3 | **One-click "reuse winner for new campaign"** — clone a winning combo onto another campaign | ① + ⑪ | **P1** | Master "reuse winning templates"; pure clone, no new gen |
| 4 | **Brand-kit auto-apply** — banner uses the campaign's logo/colors/tone automatically | ⑤ | **P1** | Master §13 brand memory; surfaces as a "Brand kit ✓" `Badge` on gen |
| 5 | **Send-time optimizer** — AI suggests the best send window from past read-times | ⑨ | **P2** | Light, additive; a single AI-suggestion card |
| 6 | **Template marketplace** — starter WhatsApp templates per industry pack | ③ | **P2** | Cold-start help; static industry-pack cards (master §21) |
| 7 | **Auto-regenerate winners** — when a combo wins, queue "5 more like it" for the next round | ⑪ | **P2** | The flywheel (integrations §3.4); one `Button`, gated |

P0/P1 ship inside the 11-step build (they're chained existing surfaces). P2 are additive cards, no bloat.

---

## 5. STATES, GATES, RESPONSIVENESS (the acceptance bar)

- **Live vs dormant per surface:** send/log/delivery (⑨⑩) are LIVE today; AI-gen (③⑤) + creative-attach
  (④) + analytics (⑪) degrade to a premium `not_configured`/coming-soon card (NOT an error wall) until
  LLM/Asset-Service/Meta creds land — matching today's `anyUnconfigured` banner pattern in `page.tsx`.
- **Gates:** non-writers (`canWrite(me)===false`) see read-only cards + a `LockOverlay`; money/destructive
  steps (⑤ generate, ⑦ approve, ⑨ send) route through `EntitlementGuard`/step-up `Modal`. Mirrors the
  existing `writable` gate on the current send form.
- **Loading:** the §6-PHASE2 **dot-matrix AI loader** for ALL generation (③ copy, ⑤ banner) — never a bare
  `Spinner`; `Spinner` stays only for fast list loads (⑩). `prefers-reduced-motion` → calm static field.
- **Tokens/type:** Inter Display app-wide; single `Layout title="WhatsApp campaigns"`, no subtitle; all
  color via Signal/`b-*`/`t-*`/`s-*` tokens, ZERO raw hex; cards `rounded-4xl`, 1.5px border (W1 shell).
- **Responsive:** desktop = 2-col (workspace + pinned preview); tablet = step rail scrolls, preview drops
  under the workspace; mobile = single column, preview as a sticky top card, step rail becomes a `Select`.
- **No-invent everywhere:** every AI surface renders the master §20 guardrail note; the UI never shows a
  price/offer/claim the campaign didn't provide.

---

## 6. BUILD ORDER (deferred — orchestrator wires after the UI-overhaul lane clears)

1. **Shell + step rail** (`Layout`+`Tabs` stepper, ① Launchpad from `HomePage`) — verifiable: renders,
   nav between steps works, no raw hex. *No backend needed.*
2. **② Campaign + ⑥ Preview + phone mock** — the spine the founder feels first; campaign select + live
   phone preview from sample data. *Uses existing campaign API; preview is client-side.*
3. **⑩ Delivery + ⑨ Schedule** — elevate the LIVE send/log into the campaign view (real today).
4. **③ AI Templates + ④ Creative gallery + ⑤ Banner Studio** — wire the `creative.*` contract +
   §6-PHASE2 loader; dormant-safe until creds. *Per integrations §9 seams.*
5. **⑦ Approval + ⑧ Audience + ⑪ Analytics** — the gates + insights + the learning-loop reuse cards.
6. **§4 out-of-box P0/P1** chained in (co-gen, A/B, reuse-winner).

Each step is one verifiable unit; none edits the spine destructively; the LIVE send path is never broken.

---

## 15-LINE SUMMARY (for the orchestrator)

1. The WhatsApp page becomes **ONE route** `/whatsapp` = a premium campaign WORKSPACE driven by a
   horizontal **11-step rail** (Tabs stepper), replacing today's 2-card form (`app/whatsapp/page.tsx`).
2. The 11 steps map 1:1 to the founder flow: **Launchpad → Campaign → AI Templates → Creative → Banner
   Studio → Preview → Approval → Audience → Schedule → Delivery → Analytics/Optimization**.
3. **ZERO new component families** — everything ports already-shipped reference components
   (`Layout/Card/Tabs/Table/GridProduct/Product/Message/Modal/FieldImage/KpiCard/Sparkline/CardChartPie/
   Percentage/Filters/NoFound/useSelection`); only 3 "compose" assemblies (AI-suggest card, phone mock, loader).
4. Layouts port 3 kit archetypes: **dashboard 2-col (`HomePage`)**, **master-detail (`MessagesPage`)**,
   **card-grid gallery (`Products/DraftsPage`)** — intentional per step, never blind reuse.
5. A **pinned WhatsApp phone PREVIEW** (right column from step ③) renders the real message — restyled
   `Message` bubble + `Image` header + CTA chips + double-tick — live-updating as copy/banner/language change.
6. **③ AI Template Generation** auto-writes 3–5 template suggestion cards (copy + CTA + angle `Badge` +
   personalization tokens + media rec) from the campaign via the LLM, with the §6-PHASE2 dot-matrix loader.
7. **④ Creative Selection** is the Asset-Library gallery (`GridProduct`) — browse/search/filter/compare/
   **attach** approved banners via `creative.search`; NO manual upload (integrations §2.1).
8. **⑤ Banner Studio** launches Creative Studio in-context (`NewProductPage` 2-col) — generate/edit
   variants via `creative.generate/edit`, the premium dot-matrix loader, NL-edit chips, credit-gate Modal.
9. **⑦ Approval** renders the two gates in order — asset-approval (`creative.approve`) then WA send-approval
   — with the quality checklist; Meta template status shown, never faked; step-up for money/destructive.
10. **⑧ Audience** = lead list+select (`CustomerList`) with **audience-insight cards** (segment donut,
    reachable/suppressed KPIs, AI-suggestion to target hot leads); DNC auto-excluded.
11. **⑨ Schedule / ⑩ Delivery** elevate the **LIVE** send + message-log into a campaign-scoped status table
    (`Income/StatementsPage`) with webhook-driven KPI strip — real today, not dormant.
12. **⑪ Analytics + Optimization** = KPI strip + funnel `CardChartPie` + per-variant table with
    `set_status(winner)` + **reuse-winner / "5 more like this"** cards closing the master learning loop.
13. **Out-of-the-box (§4):** P0 AI copy+banner co-generation, P0 A/B template test, P1 reuse-winner +
    brand-kit auto-apply; P2 send-time optimizer, template marketplace, auto-regen winners — proposed+prioritized.
14. **Live/dormant per surface, gated, responsive:** LIVE send/delivery; AI/creative/analytics degrade to a
    premium coming-soon card (not an error); `canWrite`+`EntitlementGuard` gates; 2-col→single-col responsive;
    every AI surface shows the NO-INVENT guardrail; Inter Display, single title, zero raw hex.
15. **Build order** (deferred): shell+rail → spine (campaign+preview) → live delivery → AI/creative seams →
    gates+insights+learning cards → out-of-box chains; each a verifiable unit, the LIVE send path never broken.

### THE SCREEN / STEP LIST (one line each)
- **① Launchpad** — campaign cards + KPI strip + winning-template reuse gallery + needs-approval (`HomePage` 2-col).
- **② Campaign Selection** — searchable campaign list+select + read-only Campaign Context panel (`CustomerList`).
- **③ AI Template Generation** — 3–5 AI suggestion cards (copy/CTA/angle/tokens/media rec) + dot-matrix loader (`PromotePage`).
- **④ Creative Selection** — Asset-Library gallery: browse/search/filter/compare/attach approved banners (`DraftsPage` Grid).
- **⑤ Banner Studio** — in-context Creative Studio gen/edit, variants grid, premium loader, NL-edit chips, credit gate (`NewProductPage`).
- **⑥ Template Preview** — pinned WhatsApp phone mock (real message) + editable copy/CTA/banner/language (`MessagesPage`).
- **⑦ Approval** — two gates (asset-approve → WA send-approve) + quality checklist + Meta status; step-up (`CommentsPage`+`Modal`).
- **⑧ Audience Selection** — lead list+select + audience-insight cards (segment donut, KPIs, AI target suggestion) (`CustomerList`+`Insights`).
- **⑨ Scheduling** — send-now/schedule, date-time, send-window/throttle, batch summary (`ScheduledPage`+`ScheduleProduct`).
- **⑩ Delivery** — live per-recipient status table + delivery KPI strip (LIVE send/log) (`Income/StatementsPage`).
- **⑪ Analytics + Optimization** — KPI strip + funnel chart + per-variant table + reuse-winner/"more like this" cards (`EarningPage`+`ProductActivity`).
