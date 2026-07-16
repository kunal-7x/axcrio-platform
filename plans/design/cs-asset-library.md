# DESIGN SPEC — CREATIVE STUDIO · ASSET LIBRARY + CROSS-PLATFORM REUSE (UI)

> **READ-ONLY DESIGN WAVE (2026-06-11).** Screen-by-screen, component-mapped build brief for the
> **Asset Library** — the reusable store at the heart of Creative Studio — and the **cross-platform reuse**
> surfaces (pick an asset into a WhatsApp template / ad / funnel / workflow). This is the dedicated deep doc
> the parent `design/creative-studio-ui.md` §12 (S9) only sketched. It is the UI head of the already-designed
> backend `design/asset-service-backend.md` (the `ai_asset_*` PG schema + the authed `/api/assets/*` API).
>
> **THE IRON RULE (founder, repeated — `memory/ui-reuse-core2-never-from-scratch.md` 2026-06-10/11):**
> PORT, DON'T APPROXIMATE. Reuse the reference-kit COMPONENTS verbatim and swap our data; layouts are
> intentionally composed per workflow (Apple-like rich multi-card placement), but every brick is a reference
> component. **No bespoke `PageHeader`, no eyebrow, no subtitle, zero raw hex, ONE heading via `<Layout
> title>`, everything inside a `Card`, Inter Display, semantic `@theme` tokens only, dark-mode by default.**
>
> **Reference kit (CODE = source of truth, verified on disk):**
> `C:\Users\kunal\Desktop\core-2-dashboard-builder-react`. Our app: `C:\Users\kunal\Desktop\caps\famit-panel`.
> **Build timing:** the Creative Studio FRONTEND build runs AFTER the UI-overhaul build clears the frontend
> lane (per the project brief). Design ON TOP of the reference look that wave establishes.
>
> **Status: DESIGN ONLY.** No app code, no deploy, no git in this wave.

---

## 0. WHAT THE ASSET LIBRARY IS (the one idea that shapes every screen)

> **The Library is the reusable STORE, not a folder.** Every banner the AI generates lands here ONCE and is
> then PICKED — over and over — into WhatsApp templates, ads, funnels, landing pages and workflows. The
> vendor's mental model is *"I have a wall of my best creatives; I drop the right one wherever I need it."*
> Generation happens in the **Studio** (`creative-studio-ui.md` S1–S8); the **Library** is where assets
> **live, get filtered, compared across versions, organised in bulk, and reused cross-platform**. Reuse is
> the product — not an afterthought button.

Three jobs, in priority order:
1. **FIND** the right asset fast — a filterable visual GALLERY (the founder's named filters: campaign /
   platform / asset-type / status / best-performing / date / size / angle).
2. **JUDGE** an asset — the rich card + the detail drawer (preview / campaign / type / platform / size /
   angle / headline / CTA / status / score / cost / used-in / performance) and the **version timeline**
   (every edit is a version; nothing is overwritten — backend §2 `ai_asset_versions`).
3. **REUSE** an asset — bulk actions on many, and the **cross-platform ATTACH** of one (the "attach to
   WhatsApp template" action + ads / funnel / workflow).

Maps to master spec §28 (asset library + filter facets), §26 (versioning), §27 (status lifecycle), §31
(performance), §32–33 (Adbot / workflow reuse), §52–53 (WhatsApp attach). Conforms to backend
`design/asset-service-backend.md` §2 (schema), §7 (integrations/attach), §8 (the `/api/assets/*` API).

---

## 1. WHERE IT LIVES (route + nav)

- **Route:** `app/creative/library/page.tsx` → **`/creative/library`**, child of the single sidebar group
  **"Creative Studio"** (plain noun, no jargon). Siblings: Studio (`/creative`), Brand Kit (`/creative/brand`).
- **Heading:** `<Layout title="Asset Library">` — rendered ONCE by `Header` as `text-h4`. **No `PageHeader`,
  no subtitle, no eyebrow, no accent bar** (the neutralised-PageHeader rule, `ui-reuse-core2…` 2026-06-11).
- **Entry points INTO the Library (it is a hub, reached many ways):**
  - sidebar nav · Studio "Recent assets" card "View all →" (`creative-studio-ui.md` S1 col-right) ·
  - the **WhatsApp** page's "Creative assets" rail "Browse all →" (a *scoped, embedded* Library view, §9) ·
  - the **Ads / Workflow** "pick a creative" pickers (the same embedded gallery, §9) ·
  - "From this →" on any card (re-enters Studio with the asset as a reference image).
- **Icon:** reuse an existing `components/Icon` dictionary path (`image` / `grid` / `gallery`); add ONE SVG
  path only if none fits (icons are a path dictionary, not a lib — `ui-ref-kit-inventory.md` §0).

---

## 2. SCREEN / SURFACE INDEX (the deliverable list)

| # | Surface | Where | Primary reference template/component to PORT |
|---|---|---|---|
| **L1** | **Library gallery** (filterable visual wall + head + view toggle) | `/creative/library` | `Products/DraftsPage` (head↔bulk-bar swap + grid/list toggle) + `ExploreCreatorsPage` grid rhythm |
| **L2** | **Filter rail** (campaign/platform/type/status/best-performing/date/size/angle) | slide-over from L1 | `ExploreCreatorsPage/Filters` (`Modal isSlidePanel` + `Select`/`Switch`/`Field`) |
| **L3** | **Asset card** (the rich gallery tile — full anatomy) | inside L1 grid | `components/GridProduct` (corner `Checkbox` + hover-reveal `actions` + `Badge`/`label`) |
| **L4** | **Bulk-action bar** (head swaps when ≥1 selected) | top of L1 | `DraftsPage` selected-state head + `useSelection` hook + `Button`/`DeleteItems` |
| **L5** | **Asset detail drawer** (preview + meta + score + used-in + actions) | right slide-over from L1/L3 | `Modal isSlidePanel` (w-114) + `Customers/CustomerList/DetailsPage` detail stack |
| **L6** | **Version timeline** (edits-as-versions, rollback) | a tab/strip inside L5 | `Tabs` + a horizontal thumbnail strip (`Image` cards) + `Badge` "current" |
| **L7** | **Cross-platform ATTACH picker** ("Use this →" → WhatsApp / Ads / Funnel / Workflow / Download) | `Dropdown`→`Modal` from L3/L5/L4 | `Dropdown` + centered `Modal` + `Select`/destination cards |
| **L8** | **"Attach to WhatsApp template" flow** (the headline reuse path) | from L7 / the WA page | `Modal` + `Select` (template) + the `MessagesPage` chat-bubble preview |
| **L9** | **Embedded Library picker** (the gallery reused inside WhatsApp/Ads/Workflow as a chooser) | a prop-mode of L1 | same L1 grid + L2 filters, `selectMode="pick"` |
| **L10** | **List/table view** (dense alternative to the grid) | view toggle in L1 | `DraftsPage/List` → `Table`/`TableRow`/`TableProductCell` |

Below: each surface's exact layout, the reference components it ports, its data, and its states.

---

## 3. L1 — THE LIBRARY GALLERY (the filterable visual wall)

**Goal:** a calm, premium wall of creative tiles the vendor can scan, filter, and act on. **Ports the
`Products/DraftsPage` page shell verbatim** — the single best 1:1 match in the kit: one `.card`, a head row
that **swaps to a bulk-action bar the moment a tile is selected**, a grid/list view toggle, and a `NoFound`
empty state. Grid rhythm borrows `ExploreCreatorsPage`'s responsive wrap.

```
┌─ Layout title="Asset Library" ─────────────────────────────────────────────────────────┐
│ ┌─ .card ────────────────────────────────────────────────────────────────────────────┐ │
│ │  HEAD (no selection):                                                                │ │
│ │  [ "Assets" text-h6 ] [ Search isGray ] [ status Tabs ] ······· [ Filters ] [ ▥▤ ] [ + Create ]│
│ │    All · Approved · Drafts · Used · Winners                       (view toggle)  → /creative│
│ │  HEAD (≥1 selected) → swaps to L4 bulk-bar:                                           │ │
│ │  [ "7 assets selected" ] [ Deselect ] ···· [ Approve ] [ Add to campaign ] [ Use → ] [ Archive ]│
│ ├──────────────────────────────────────────────────────────────────────────────────────┤ │
│ │  GRID (L3 cards, responsive wrap)            │  …or LIST (L10 Table) when ▤ toggled    │ │
│ │  [tile][tile][tile][tile][tile]              │  ┌ select-all ┬ Asset ┬ Campaign ┬ … ┐  │ │
│ │  [tile][tile][tile][tile][tile]   …          │  └────────────┴───────┴──────────┴───┘  │ │
│ └──────────────────────────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────────────────────────┘
```

- **Page shell (PORT `DraftsPage/index.tsx` 1:1):** one `<div className="card">`; the head is the
  `selectedRows.length === 0 ? (browse head) : (bulk-bar)` ternary — reuse it verbatim, only relabel
  ("Products"→"Assets", "Publish"→"Approve", swap the action set to ours). The grid/list body sits in
  `<div className="p-1 pt-3">`.
- **Head, browse state (left→right):** `text-h6` "Assets" · `components/Search isGray` (placeholder
  "Search assets") · status **`Tabs`** (All · Approved · Drafts · Used · Winners) · push-right · the **L2
  `Filters`** button (`Button isWhite isCircle` + `Icon name="filters"`) · a **view-toggle `Tabs isOnlyIcon`**
  (grid ▥ / list ▤, the `DraftsPage` `views` pattern) · `Button isBlack` **"Create"** → deep-links to Studio
  `/creative`.
- **Search behaviour (PORT):** when `search !== ""`, hide the view toggle and render `NoFound` if zero hits
  (the exact `DraftsPage` behaviour). Server-side search = the `q` param on `GET /api/assets`.
- **Grid body (L3 cards):** the `flex flex-wrap` of `GridProduct`-style tiles. **Card width must match the
  kit's responsive ramp** — use `ExploreCreatorsPage`/`GridProduct` widths so it never jumps:
  `w-[calc(20%-1.5rem)] max-4xl:w-[calc(25%…)] max-[1539px]:33% max-lg:50% max-md:100%` (5→4→3→2→1 up).
- **Data:** `GET /api/assets?limit&offset&campaign&platform&kind&status&angle&size&from&to&sort&q`
  (backend §8 — `AssetQuery` facets) → newest-first, **tenant-scoped by the token** (never a body tenant —
  backend §9 isolation), paginated. Infinite-scroll/"Load more" via `offset` + a trailing `components/Spinner`
  (the `ExploreCreatorsPage` trailing-spinner pattern).
- **States (every data surface — acceptance rule):** **loading** = grid of L3 cards in their `loading`
  shimmer (the same `CreativeSkeleton` token-shimmer from `creative-studio-ui.md` §9, reused — NOT a new
  loader); **empty** = `components/NoFound` "No assets yet — create your first in the Studio" + a primary
  `Button` → `/creative`; **filtered-empty** = `NoFound` "No assets match these filters" + a "Clear filters"
  `Button isStroke`; **error** = ONE token-styled inline banner (`primary-05`/`b-surface`), never a raw throw.

---

## 4. L2 — FILTER RAIL (the founder's named facets)

**Ports `ExploreCreatorsPage/Filters` verbatim** — a right **`Modal isSlidePanel`** (`classWrapper="!w-85"`)
opened by the head's filter button, a scrollable stack of `Select`s + a `Switch`, and a Reset / Apply footer
(`Button isStroke` / `Button isBlack`). Only the facet set is swapped to ours.

| Facet (founder-named §28) | Reference control | Options / source |
|---|---|---|
| **Campaign** | `components/Select` | tenant's campaigns from `lib/api` (`{id,name}[]`); "All campaigns" default. The #1 facet — every asset is campaign-linked (backend §2 `ai_assets.campaign_id`). |
| **Platform** | `Select` | All · Meta · WhatsApp · IG Story · Google · Carousel · Hero (`ai_assets.platform`). |
| **Asset type** | `Select` | All · Banner · Image · Social · Offer · Poster · Product · Logo (`ai_assets.kind`). |
| **Status** | `Select` (mirrors the head `Tabs`) | Draft · Needs review · Approved · Rejected · Used · Archived (`ai_assets.status`, §27). |
| **Best-performing** | `components/Switch` "Winners only" | filters to assets with top `metrics.ctr`/`leads` (backend §10 perf write-back); pairs with the **Sort = Best score / Best CTR** select. |
| **Date** | a small **range** (two `Field type=date` or a `DateAndTime` pair) | `from`/`to` on `created_at` (newest-first default). |
| **Size** | `Select` | All · 1:1 (1080×1080) · 4:5 · 9:16 (story) · 16:9 · Google display · WA square/vertical · Hero · Thumbnail (`ai_assets.size`, §15). |
| **Angle** | `Select` | All · Price · Location · Emotion · Urgency · Trust · Problem-solution · Benefit · Offer · Retargeting · Comparison (`ai_assets.angle`, §8). |
| **Sort** | `Select` (top of the rail) | Newest · Oldest · Best score · Best CTR · Most used · Cheapest. |

- **Applied-filter chips:** active filters echo as removable `Badge` chips in a row UNDER the head (a small
  `flex flex-wrap gap-2`), each with an ×; "Clear all" `Button isStroke` at the end. Chips are token-styled
  (`label-gray`), so the vendor always sees the active query without re-opening the rail.
- **Wiring:** Apply maps each facet to a `GET /api/assets` query param (backend §8). The rail is pure UI
  state → one fetch on Apply (not per-keystroke). "Winners only" + "Best CTR" surface the §10 performance
  signal that the backend already writes back from the Adbot loop.
- **Quick-filter shortcuts (out-of-the-box, §4 of the phase-2 spec):** the head status `Tabs` ARE the common
  filters one-tap (All/Approved/Drafts/Used/Winners) so 90% of filtering needs zero rail-opening; the rail is
  the power-user deep filter.

---

## 5. L3 — THE ASSET CARD (the rich gallery tile) ⭐

The unit of the whole Library — **ports `components/GridProduct` verbatim** (corner `Checkbox` that appears
on hover/selection, the `Image` preview, a hover-reveal `actions` row, and a default info row). We swap the
product data for the full creative record the founder listed. **The SAME card renders in Studio variants
(S5), the Library (L1), and every embedded picker (L9)** — one card component, reused everywhere, so the
product looks identical and premium throughout.

**Card anatomy (top→bottom), all reference primitives:**
- **Preview** — `components/Image` `object-cover rounded-3xl`, the banner render
  (`GET /api/assets/{id}/raw` or the version `thumb_url`; `local_path` NEVER exposed — backend §8/§9).
- **Corner `Checkbox`** (top-left, the `GridProduct` pattern) — invisible until hover/selected → drives L4
  bulk selection via `useSelection`.
- **Angle `Badge`** (top-left over the image) — "Price Focus" / "Urgency" / "Trust" / "Location" / "Offer"
  (`ai_assets.angle`, §8 — the testing-angle label, so a wall of variants reads as a *test set* not noise).
- **Status pip `Badge`** (top-right over the image) — one semantic colour map reused from the kit (no raw
  hex): Approved = `label-green`, Needs review = `label-yellow`, Draft = `label-gray`, Rejected =
  `label-red`, Used = brand `primary`, Archived = muted. (`ai_assets.status`, §27.)
- **Title row** — `text-sub-title-1` **headline** (the banner's headline copy) + a right-aligned **score**
  chip rendered as `components/Percentage` or a tiny `CardChartPie` dot (the §30 creative score `overall`,
  0–100). (The kit's `price` slot is repurposed to the score chip.)
- **Default info row** (`text-caption text-t-secondary`, the `GridProduct` `children` slot): **platform ·
  size** ("Meta · 1080×1080") + a `Icon name="clock"` **date**; on **Winners**, a small green ▲ **CTR/CPL**
  stat replaces the date (backend §10 `metrics`).
- **"Used-in" chips** (a second caption line / tooltip): tiny channel `Badge`s — `WA` / `Meta` / `Funnel` /
  `Flow` — from `ai_asset_usage` (backend §2/§7), so the vendor sees at a glance WHERE a creative is already
  live. Zero-usage assets show nothing (no clutter).
- **Hover-reveal `actions` row** (the `GridProduct` `actions` slot — `flex flex-wrap gap-2`, `button.action`
  / `Button isCircle`): **Approve** (`Icon check`) · **Edit** (→ Studio S6 / opens L5) · **Versions** (→ L6)
  · **Use →** (→ L7 cross-platform picker) · **More** (`Dropdown`: Duplicate · Resize · Regenerate ·
  Archive). On mobile the row is tap-revealed (the `visible` state in `GridProduct`).
- **Click anywhere (not on a control)** → opens **L5 detail drawer**.

**Card data → fields the founder named:** preview ✓ · campaign (in L5 + filter) ✓ · type ✓ · platform ✓ ·
size ✓ · angle ✓ · headline ✓ · CTA (chip in L5; on the card it's the angle `Badge` + headline) ✓ · status
✓ · score ✓ · cost (in L5 meta) ✓ · used-in ✓ · performance (Winners stat + L5 tab) ✓. The card surfaces the
scan-critical few; L5 holds the full record so the tile stays calm.

**Token discipline:** every colour is a semantic class (`label-green/yellow/red/gray`, `primary-*`,
`t-primary/secondary/tertiary`, `b-surface1/2`); radius `rounded-3xl`; **zero raw hex**; dark mode "just
works". Nothing bigger than `text-sub-title-1` on a tile.

---

## 6. L4 — BULK-ACTION BAR + MULTI-SELECT (organise many at once)

**Ports the `DraftsPage` selected-state head + the `hooks/useSelection` hook verbatim.** When
`selectedRows.length > 0`, the L1 head **swaps in place** to the bulk bar (no layout jump — the exact kit
behaviour); the corner `Checkbox` on each L3 card drives selection; a **select-all** lives in the L10 list
view header (`Table selectAll/onSelectAll`).

**Bulk bar (left→right):** `"{n} assets selected"` (`text-h6`) · `Button isStroke` **Deselect**
(`handleDeselect`) · push-right · the bulk actions:

| Bulk action | Reference control | What it does (backend) |
|---|---|---|
| **Approve** | `Button isBlack` | `POST /api/assets/{id}/approve` per selected id (status→approved; gates Adbot/WhatsApp, §27). Confirm count in the button ("Approve 7"). |
| **Add to campaign** | `Button isStroke` → `Modal` + `Select` | re-tag the selected assets' `campaign_id` (organise/reuse); writes via the asset update path. |
| **Use →** (cross-platform) | `Button isStroke` → **L7** | open the destination picker for the whole selection (e.g. attach 5 creatives to one ad experiment as a test set — each carries its §9 hypothesis). |
| **Tag** | `Dropdown` | add/remove `ai_assets.tags` in bulk (light organisation). |
| **Archive** | `DeleteItems`-style confirm `Button` | status→archived (NOT a hard delete — backend §2 grants no `DELETE`; lifecycle is status flips, §41 "never overwrite/lose"). Label it **Archive**, never "Delete". |

- **Crucial reuse note:** the founder's spec has **no hard delete** — assets are archived (recoverable),
  never destroyed (master §41; backend §2.3 "NO `DELETE` grant"). So the kit's `DeleteItems` component is
  reused **for its confirm-dialog chrome only**, relabelled **"Archive"**, and wired to the status flip — we
  do NOT call a delete endpoint (there isn't one).
- **Select-all scope:** select-all selects the **current filtered page**; a subtle "Select all N matching"
  link extends to the full filtered set (so "approve all drafts in this campaign" is one gesture). Idempotent
  per-id calls (backend `approve` is a simple status flip) make a partial failure safe to retry.
- **`useSelection` extension:** the kit hook keys on numeric `id`; our asset ids are `ca_<hex>` strings —
  the only change is `useSelection<Asset>` over `string` ids (a one-line generic widen, noted for the build
  agent; everything else ports unchanged).

---

## 7. L5 — ASSET DETAIL DRAWER (the full record + actions)

Opened as a **right slide-over** — **`components/Modal isSlidePanel`** (`w-114`, slides from right, dim
backdrop, fixed close button — all provided by the kit `Modal`) so the vendor never leaves the gallery.
Structurally ports the **`Customers/CustomerList/DetailsPage`** master-detail "Details" stack.

```
┌─ Modal isSlidePanel (w-114, right) ─────────────────────────┐
│  [✕]                                                          │
│  ┌ large preview (zoomable Image, rounded-3xl) ────────────┐ │
│  │                  [banner render]                         │ │
│  └──────────────────────────────────────────────────────────┘ │
│  Headline  · Angle Badge · Status Badge                        │
│  ┌ Tabs: Details · Versions(L6) · Performance(S8) ──────────┐ │
│  │ DETAILS (Details rows: label / value):                    │ │
│  │   Campaign · Type · Platform · Size · Angle · Language     │ │
│  │   Headline · Subhead · CTA · Model used · Cost · Created   │ │
│  │   Score (CardChartPie mini + sub-bars) · Used-in (chips)   │ │
│  └──────────────────────────────────────────────────────────┘ │
│  ── footer (sticky) ──                                          │
│  [ Approve / Reject (Select status) ]                          │
│  [ Use this → (L7) isBlack ]  [ Edit in Studio isStroke ]  [♥] │
└──────────────────────────────────────────────────────────────┘
```

- **Preview** — `components/Image`, large, `rounded-3xl`, click-to-zoom (centered `Modal`). Source =
  current version `url` (`GET /api/assets/{id}/raw`).
- **Tabs** (`components/Tabs`): **Details** · **Versions** (L6) · **Performance** (the S8 panel from
  `creative-studio-ui.md` §11 — honest empty until the asset is "Used" and the ads/analytics loop reports).
- **Details rows** (`DetailsPage` label/value grammar — `text-caption text-t-tertiary` / `text-body-2
  text-t-primary`): Campaign · Type · Platform · Size · Angle · Language · Headline · Subhead · CTA · Model
  used · **Cost** (`actual_cost_minor`→credits) · Created · Source (generated/uploaded). **No-invent
  honesty:** a field the AI had no real value for (price/RERA/phone) is simply absent, never a fabricated
  value (master §20; backend §3.1 guardrail) — the UI shows the real record, nothing invented.
- **Score block** — `components/CardChartPie` mini (the `overall`) + a short bar list of the §30 sub-scores
  (clarity / readability / CTA / brand-match / platform-fit / quality / conversion / relevance / text-amount
  / offer-visibility), with a one-line "why". Data from `ai_creative_scores` (backend §2, denormalised on
  `ai_assets.score`).
- **Used-in** — a row of channel `Badge`s linking to each placement (`ai_asset_usage`: WhatsApp template /
  Meta experiment / workflow run / funnel) so reuse is fully traceable (backend §7/§2).
- **Status control** — a `Select`/segmented `Tabs`: Draft → Needs review → Approved → Rejected → Archived
  (§27). **Reject** opens a small reason `Field` → `POST /api/assets/{id}/reject` (the reason teaches
  brand-memory `do_not_use` — backend §10).
- **Footer actions** (sticky): `Button isBlack` **"Use this →"** (→ L7) · `Button isStroke` **"Edit in
  Studio"** (deep-links to the Studio S6 NL-edit surface — `creative-studio-ui.md` §8; edits live there, the
  Library stays read+organise+reuse) · `LikeButton`-style favourite. Bulk-context: when opened from a
  multi-select, the footer also offers "Use all selected →".
- **Data:** `GET /api/assets/{id}` (backend §8) → current version + all versions + score + status + usage +
  metrics, in one payload (owner-checked; `404` on cross-tenant by-id — backend §9 isolation).

---

## 8. L6 — VERSION TIMELINE (edits as versions, rollback) ⭐

The founder's explicit ask: **"the version timeline (edits as versions)."** Backend already models it —
`ai_asset_versions` is append-only, every edit/regenerate makes a NEW immutable version, the original is
**never overwritten**, and approval/rollback flips `ai_assets.current_version_id` (backend §2). The UI just
exposes that history honestly.

**Layout — a tab inside L5** (`Tabs` → "Versions") rendering a **horizontal thumbnail strip** of versions,
newest-left, each a small `Image` card (token-built, ports the `MessagesPage`/swiper thumbnail rhythm):

```
Versions  ▸  [ v4 ●current ]  [ v3 ]  [ v2 ]  [ v1 original ]      ← horizontal strip, scrollable
            "remove price"     "premium"  "Hinglish"  (generated)   ← the NL edit_instruction that spawned it
            ┌ selected version detail ─────────────────────────┐
            │ preview · prompt/edit · model · cost · created    │
            │ [ Restore this version ]  [ Compare to current ]  │
            └───────────────────────────────────────────────────┘
```

- **Each version chip:** thumbnail (`thumb_url`) + version no (`v1…vN`) + a `Badge` "current" on the live
  one + the **`edit_instruction`** caption that produced it ("make it premium" / "remove price" / "Hinglish"
  / "story size") — so the history reads as a story, not opaque ids (backend §2 `ai_asset_versions.
  edit_instruction` + `parent_version_id` lineage).
- **Select a version** → shows that version's preview + provenance (prompt, model, cost, created) in the
  detail slot below the strip.
- **Restore** — `Button isStroke` "Restore this version" → flips `current_version_id` to the chosen version
  (the original is still there; restore is itself non-destructive — backend §2/§9). Confirm inline.
- **Compare** — `Button isStroke` "Compare to current" → a centered `Modal` showing the two previews
  **side-by-side** (token-built two-column, `Image` × 2) with their headline/CTA/score diffs beneath — the
  "which edit was better" view (supports the §31 learning loop visually).
- **Lineage clarity:** a faint connector under the strip shows `parent_version_id` branches (an edit of v2
  vs an edit of current) so a vendor who regenerated from an old winner sees the tree, not a flat list.
- **Data:** the versions array comes inside `GET /api/assets/{id}`; Restore = the approve/rollback path
  (backend §8 — status/version flips, no new endpoint). **No edit happens here** (edits are a Studio spend
  action behind step-up, `creative-studio-ui.md` §8) — the Library timeline is **read + restore + compare**,
  keeping the spend surface in one place.

---

## 9. L7 / L8 — CROSS-PLATFORM ATTACH (the reuse engine) ⭐⭐

This is the founder's headline for THIS doc: **"how assets are PICKED into WhatsApp templates / ads / funnels
/ workflows (the cross-platform attach + the 'attach to WhatsApp template' action)."** The backend exposes
ONE verb — `POST /api/assets/{id}/attach {channel, ref_id}` → writes an `ai_asset_usage` row + a
`handoff.jsonl` drain to the target channel (backend §7). The UI gives that verb a premium, consistent
**"Use this →" picker** that appears identically on the L3 card, the L5 drawer, and the L4 bulk bar.

### 9.1 L7 — the destination picker (`Dropdown` → `Modal`)
"Use this →" opens a `Dropdown` (quick) or a centered `Modal` (rich) of **destination cards** — one
consistent action vocabulary everywhere (master §32–33, §52):

| Destination | What attach does | Backend |
|---|---|---|
| **WhatsApp template** ⭐ | → **L8** (pick/create a template + attach the banner) | `attach {channel:"whatsapp", ref_id:template_id}` (§7) |
| **Ad campaign (Meta)** | register the asset's variants (each with its §9 hypothesis) into an ads experiment as a test set — **manual launch only**, never auto-spend (backend §6 RED-TEAM caveat) | `attach {channel:"meta_ads", ref_id:experiment_id}` (§7) |
| **Funnel** | drop the creative into a funnel step (hero/section image) | `attach {channel:"landing", ref_id:funnel_step_id}` (§7) |
| **Workflow** | bind the asset to a workflow asset-node (e.g. "lead hot → send this poster") | `attach {channel:"workflow", ref_id:node_id}` (§7) |
| **Download** | export the raw render (`GET /api/assets/{id}/raw`) | no usage row (local export) |

- **Approved-only gate:** only `status:approved` assets attach to a live channel (master §27; backend §7).
  A draft's "Use this →" first prompts **"Approve & use?"** (one tap = approve then attach) so the vendor
  isn't blocked but the gate holds.
- **Bulk attach (from L4):** the picker accepts a SELECTION → attach N assets to one destination (the ad
  test-set case). Each attach is an idempotent per-id call; a partial failure is safe to retry.
- **Every attach keeps the campaign link:** the asset stays bound to its originating `campaign_id` so
  performance flows back (`ai_asset_usage.metrics` → `ai_assets.metrics`) and the §31 learning loop closes
  (master §53; backend §10).

### 9.2 L8 — "Attach to WhatsApp template" (the named flow)
The deepest reuse path (master §52–53; phase-2 spec §2). A centered `Modal` (or, when reached FROM the
WhatsApp page, inline in its Compose card — `creative-studio-ui.md` W1):

```
┌─ Modal "Attach to WhatsApp" ─────────────────────────────────┐
│  [ selected banner thumb ]  headline · CTA · campaign         │
│  Template  ▸ [ Select: existing approved WA templates ]       │
│            ▸ [ + Ask AI to write a template from this campaign]│  ← master §52 AI-build
│  ┌ live WhatsApp-bubble PREVIEW (image + text, token-styled) ┐│
│  │  [banner]                                                  ││
│  │  "Hi {{name}}, …"   [ Book Site Visit ]                    ││
│  └────────────────────────────────────────────────────────────┘│
│            [ Cancel isStroke ]      [ Attach & continue isBlack ]│
└──────────────────────────────────────────────────────────────┘
```

- **Pick or create the template:** a `Select` of existing approved WA templates, OR a `Button isStroke`
  **"Ask AI to write a template from this campaign"** → the backend builds the copy from `CampaignContext`
  (with the §20 no-invent guardrails — no fabricated price/offer) and pre-fills it (master §52; backend §3).
- **Live bubble preview:** the `MessagesPage` chat-bubble pattern (token-styled, NOT raw hex) shows exactly
  how the image+text lands in WhatsApp — reassuring, premium, no surprises.
- **Attach** → `POST /api/assets/{id}/attach {channel:"whatsapp", ref_id:template_id}` → an `ai_asset_usage`
  row (status `attached`) + the handoff drain to the WA path (backend §7; the WA client is never imported).
  The asset's status flips to **Used** and the "used-in" chip `WA` appears on its card — the loop is visible.
- **No manual upload, ever** (the founder's hard rule §52): the banner travels by reference from the Library;
  the vendor browses/previews/filters/attaches — they never re-upload a file.

### 9.3 L9 — the embedded Library picker (reuse the gallery as a chooser)
The Library is **the same component in two modes**: a full page (L1) and an **embedded picker** dropped into
the WhatsApp Compose card, the Ads "pick creative" step, and the Workflow asset-node config. `selectMode`
prop:
- `selectMode="browse"` (default) → click a card opens L5 (the full library).
- `selectMode="pick"` → click a card **selects** it and returns it to the host (WA Compose / Ads / Flow),
  with the L2 filters scoped to the host's campaign by default (e.g. the WhatsApp page pre-filters to the
  current campaign + `platform=whatsapp`). Same `GridProduct` cards, same filters — **one gallery, reused as
  the cross-platform chooser**, so the picker looks identical to the Library (consistency = premium, and zero
  new components).

This is precisely the founder's "browse/preview/search/filter and directly ATTACH Creative Studio assets to
templates" requirement (master §52) — satisfied by REUSING L1/L2/L3, not building a second gallery.

---

## 10. L10 — LIST / TABLE VIEW (dense alternative)

The view-toggle's second mode (`DraftsPage/List` → `Table`/`TableRow`/`TableProductCell`), for vendors who
want a dense, sortable, select-all-able table over the visual wall. **Ports `DraftsPage/List` verbatim;** only
the columns change:

| Column | Cell | Source |
|---|---|---|
| **Asset** | `TableProductCell` (thumb + headline + details) | preview + headline + campaign |
| **Campaign** | `td` + `Icon` | `campaign_id`→name |
| **Platform / Size** | `td` | `platform` · `size` |
| **Angle** | `td` + `Badge` | `angle` |
| **Status** | `td` + status `label` | `status` (the §27 colour map) |
| **Score** | `td` + `Percentage` | `score.overall` |
| **Used-in** | `td` + channel `Badge`s | `ai_asset_usage` |
| **Created** | `td text-t-secondary` | `created_at` |

- **Select-all** lives in the table header (`Table selectAll/onSelectAll`) → feeds the SAME L4 bulk bar.
- **Row click** → L5 drawer. Row hover-actions (`TableProductCell` action buttons) = Edit / Use → / More,
  identical verbs to L3 — one action vocabulary across grid and list.
- The grid (L3) is the default (premium, visual — it's a *creative* library); the list is the power tool.

---

## 11. OUT-OF-THE-BOX ADDITIONS (founder §4 of phase-2 spec invites these)

Proposed + prioritised; each REUSES existing components and the existing API — no bloat, no new backend:

1. **Winners row / "5 more like this winner"** (HIGH) — a pinned `Tabs` "Winners" segment surfaces top-CTR
   assets (backend §10); each card's "More" `Dropdown` offers "5 more like this winner" → deep-links to
   Studio regenerate biased to that brief (master §9/§30; backend §10). Pure reuse of the L3 card + a
   deep-link.
2. **"Make all sizes" one-click** (HIGH) — on any approved asset, a `Dropdown` action "All platform sizes"
   → one Studio regenerate batch across 1:1 / 4:5 / 9:16 / 16:9 / Google / hero (master §15). Surfaces the
   resize the backend already supports as one gesture.
3. **A/B compare in the timeline** (MED) — the L6 "Compare to current" view, extended to compare any two
   versions side-by-side with score/CTR deltas (the §31 learning made visible). Already drafted in L6.
4. **Collections / boards** (MED) — light `tags`-based grouping ("Diwali set", "Hot-lead posters") shown as
   filter chips; reuses `ai_assets.tags` + the L2 filter (no schema change).
5. **Asset cost roll-up** (LOW) — a tiny stat strip on L1 ("142 assets · 38 approved · ₹X spent this month")
   from the `metrics`/`cost` already on each row — a `Products/OverviewPage` stat tile, reused.
6. **Reference-from-Library** (LOW) — "From this →" on any card re-enters Studio with the asset as the
   reference image ("make this kind of banner") — closes the reuse loop (master §38/§53).

Each is a one-component or one-deep-link add; none requires a new endpoint or a new gallery.

---

## 12. DATA WIRING (which surface calls which `/api/assets/*` route — backend §8)

| Surface | Endpoint | Returns |
|---|---|---|
| L1 gallery list + L2 filters + L9 picker | `GET /api/assets?limit&offset&campaign&platform&kind&status&angle&size&from&to&sort&q` | newest-first tenant-scoped list (`AssetQuery` facets) |
| L3 card preview / L5 large preview | `GET /api/assets/{id}/raw` (or version `thumb_url`) | image bytes (`local_path` never exposed) |
| L5 detail drawer + L6 versions + score + used-in | `GET /api/assets/{id}` | current version + all versions + score + status + usage + metrics |
| L4 Approve (bulk + single) / L5 status | `POST /api/assets/{id}/approve` | status→approved |
| L5 Reject (+ reason) | `POST /api/assets/{id}/reject` | status→rejected (teaches brand-memory) |
| L4 Archive | the status path (NO delete endpoint) | status→archived (recoverable) |
| L6 Restore version / rollback | the approve/version path | flips `current_version_id` |
| L7 / L8 / L9 attach (WhatsApp / Ads / Funnel / Workflow) | `POST /api/assets/{id}/attach {channel, ref_id}` | `ai_asset_usage` row + handoff |
| L8 "Ask AI to write template" | `POST /api/assets/{id}/attach` after AIM template-build (backend §3/§7) | template copy from `CampaignContext` |
| Create (head button) / Edit in Studio / Regenerate / Resize | Studio surfaces (`creative-studio-ui.md` S2/S6/S11) — spend, behind step-up | new job / new version |

Every route is **token-derived tenant** (never a body tenant), by-id routes are **owner-checked → `404` on
cross-tenant** (backend §9 isolation), and the whole surface is feature-gated `AIASSET_ENABLED` → `503`
(the UI's dormant state, except the un-gated `GET /api/assets/status` readiness probe). The UI never sees a
provider key.

---

## 13. CROSS-CUTTING ACCEPTANCE BAR (every surface must pass — `ui-design-principles.md` §7)

- [ ] Wrapped in `<Layout title="Asset Library">` — ONE `text-h4` title, **no `PageHeader`, no eyebrow, no
      subtitle, no accent bar.**
- [ ] Every section is a `components/Card`/`.card` (`text-h6` head). No bare custom panels.
- [ ] **Reference components ONLY** — `Card`, `Search`, `Tabs`, `Select`, `Switch`, `Field`, `Button`,
      `GridProduct`, `Filters`(`Modal isSlidePanel`), `Checkbox`, `Image`, `Badge`/`label`, `Table`,
      `TableRow`, `TableProductCell`, `Modal`, `Dropdown`, `Percentage`, `CardChartPie`, `NoFound`,
      `Spinner`, `DeleteItems`(relabelled Archive), `LikeButton`, `hooks/useSelection`. The page shells PORT
      `DraftsPage` + `ExploreCreatorsPage` + `Customers/CustomerList/DetailsPage`. **Zero genuinely-new
      components** (the liquid loader is the already-specced `CreativeSkeleton`, reused).
- [ ] **Zero raw hex** — semantic `@theme` tokens only (status `label-green/yellow/red/gray`, brand
      `primary-*`, surfaces `b-surface1/2`, text `t-primary/secondary/tertiary`). ≤2 saturated colours.
- [ ] Inter Display throughout; type ramp tokens only; nothing bigger than `text-h4`/`text-sub-title-1` in
      content.
- [ ] Real loading (`CreativeSkeleton`/`Spinner`) / empty (`NoFound`) / filtered-empty / error (one token
      banner) on every data surface. No raw "undefined", no blank flashes.
- [ ] Plain language — "Assets / Approve / Use → / Versions / Archive", no internal jargon (no
      "ai_asset_usage", "current_version_id", "channel", "provider" in the vendor's face).
- [ ] **No hard delete** — Archive (status flip, recoverable) only; nothing is destroyed (master §41).
- [ ] **No manual upload to reuse** — attach travels by reference from the Library (master §52).
- [ ] Tenant isolation is the BACKEND's job (token-derived, RLS) — the UI never sends a body tenant and never
      shows another tenant's asset (by-id `404`).

---

## 14. BUILD ORDER (for the later front-end wave — small verifiable units)

1. **L1 shell** — port `DraftsPage` into `app/creative/library/page.tsx`; head + status `Tabs` + view
   toggle + `NoFound` empty; wire `GET /api/assets` (newest-first) → renders, nav active state correct.
2. **L3 card** — port `GridProduct` → the creative tile (angle/status `Badge`, score chip, used-in chips,
   hover actions); the SAME card used in Studio S5 (single source).
3. **L2 filter rail** — port `ExploreCreatorsPage/Filters`; the 8 founder facets + sort → query params +
   applied-filter chips.
4. **L4 bulk bar + `useSelection`** — head↔bulk-bar swap; Approve / Add-to-campaign / Use → / Archive;
   widen the hook to string ids.
5. **L5 detail drawer** — `Modal isSlidePanel` + `DetailsPage` stack + score block + used-in; `GET
   /api/assets/{id}`.
6. **L6 version timeline** — `Tabs` "Versions" strip + restore + compare modal.
7. **L7 destination picker** + **L8 attach-to-WhatsApp** (template select / AI-build + bubble preview) →
   `POST /api/assets/{id}/attach`.
8. **L9 embedded picker** — `selectMode="pick"` mode of L1/L2/L3, dropped into WhatsApp/Ads/Workflow.
9. **L10 list view** — port `DraftsPage/List` columns; select-all → L4.
10. **Out-of-the-box** (§11) — Winners row, "make all sizes", A/B compare, collections — as they fit.
11. Run the §13 acceptance checklist per surface → green.

Each unit reuses a NAMED reference template/component; nothing is hand-built.

---

## 15. SOURCES / GROUND TRUTH (file evidence)

- Master spec: `caps/CREATIVE_STUDIO_MASTER_PROMPT.md` §8 (angles), §15 (sizes), §26 (versioning), §27
  (status lifecycle), §28 (library + filter facets), §30 (score), §31 (performance learning), §32–33
  (Adbot/workflow reuse), §41 (never delete/overwrite), §52–53 (WhatsApp attach, no manual upload).
- Phase-2: `caps/CREATIVE_STUDIO_PHASE2_SPEC.md` §2 (WhatsApp attach + creative-selection), §4
  (out-of-the-box additions).
- Backend (the API this UI calls): `caps/design/asset-service-backend.md` §2 (`ai_asset_*` schema:
  `ai_assets`, `ai_asset_versions`, `ai_asset_usage`, `ai_creative_scores`), §7 (attach/integrations), §8
  (`/api/assets/*` API surface), §9 (isolation), §10 (perf learning).
- Companion UI doc (Studio/generation/detail/brand-kit — do not duplicate): `caps/design/creative-studio-ui.md`
  (S5 card, S6 detail, S9 library sketch, §9 `CreativeSkeleton` loader).
- UI rules / reuse / acceptance: `memory/ui-reuse-core2-never-from-scratch.md` (2026-06-10/11 updates — Inter
  Display, no subtitle, port don't approximate), `caps/design/ui-design-principles.md` (§7 checklist),
  `caps/design/ui-ref-kit-inventory.md` (components/tokens/templates).
- Reference components verified on disk (`core-2-dashboard-builder-react`): `templates/Products/DraftsPage/
  {index,Grid,List}.tsx` (head↔bulk-bar + grid/list), `templates/ExploreCreatorsPage/{index,Filters}.tsx`
  (gallery + filter slide-panel), `components/GridProduct/index.tsx` (the card), `hooks/useSelection.ts`
  (multi-select), `components/Modal/index.tsx` (`isSlidePanel` drawer), `templates/Customers/CustomerList/
  DetailsPage` (master-detail stack), `components/{Table,TableRow,TableProductCell,Badge→labels,Percentage,
  CardChartPie,NoFound,Spinner,Dropdown,Select,Switch,Field,Search,Checkbox,Image,Button}`.
```
