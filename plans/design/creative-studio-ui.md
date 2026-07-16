# DESIGN SPEC — CREATIVE STUDIO (UI / Frontend) + WhatsApp page upgrade

> **READ-ONLY DESIGN WAVE.** This doc is the screen-by-screen, component-mapped build brief for the
> **Creative Studio** front-end (the premium creative WORKSPACE) and the **WhatsApp page upgrade**.
> It conforms to `CREATIVE_STUDIO_MASTER_PROMPT.md` (§36–38, §52–53) and is the UI head of the already-
> designed backend: AI Asset Service engine (`design/creative-image-banner-studio.md`), Asset Library
> (`design/creative-asset-library.md`), media-gen engine layer (`memory/brain/media-gen.md`).
>
> **THE IRON RULE (founder, repeated; `design/ui-design-principles.md`, `design/spec-core2-reuse-map.md`):**
> PORT, DON'T APPROXIMATE. Reuse the reference-kit COMPONENTS verbatim and swap our data. The LAYOUTS
> are intentionally composed per workflow (Apple-like rich multi-card placement) — but every brick is a
> reference component. **No bespoke `PageHeader`, no eyebrow, no subtitle, zero raw hex, one heading via
> `<Layout title>`, everything inside a `Card`, Inter Display, semantic tokens only.**
>
> **Reference kit (CODE = source of truth):** `C:\Users\kunal\Desktop\core-2-dashboard-builder-react`
> (verified on disk: `components/*`, `templates/*` below). Our app: `C:\Users\kunal\Desktop\caps\famit-panel`.
>
> **Build timing:** this front-end is built AFTER the in-flight UI-overhaul + Control-Layer waves land
> (per the project brief). Design ON TOP of the reference look they establish.

---

## 0. THE ONE PRINCIPLE THAT SHAPES EVERY SCREEN

> **"I tell what I need, AI creates it."** Not a design tool. The vendor never touches a layer, a font
> picker, a canvas, or a colour wheel. They pick a **campaign**, type or speak one **instruction**, and
> watch banners stream in. Everything else (product, audience, copy, CTA, size, style, angle) the AI
> infers from campaign data (master §3–6, §17). The UI's whole job is to make that feel **inevitable and
> premium** — a hero command bar, a context panel proving the AI already knows the business, a liquid
> live-generation state, and rich angle-labelled result cards. Complexity (model routing, providers,
> spend, scoring) is present but **tucked into progressive disclosure**, never in the vendor's face.

This maps directly to the master spec's UX mandate (§36): *premium creative WORKSPACE, not a form.*

---

## 1. WHERE IT LIVES (route + nav)

- **Route group:** `app/creative/` in `famit-panel` (NEW). Sidebar **single group "Creative Studio"**
  (plain noun, no jargon — per `ui-design-principles.md` §4). Phase-1 children (only what's real;
  coming-soon stays out of nav per principle §8):
  - **Studio** → `/creative` (the create + generate + variants workspace — the flagship screen).
  - **Library** → `/creative/library` (the filterable gallery of all assets).
  - **Brand Kit** → `/creative/brand` (logo/colours/tone the AI uses).
  - *(Insights folds INTO the Asset Detail panel + Library, not a separate page in Phase 1.)*
- Nav item added to `contstants/navigation.tsx` (`{title:"Creative Studio", icon:"image", list:[…]}`).
  Icon: reuse an existing path from `components/Icon` dictionary (`image` / `camera` / `grid`); add one
  SVG path if none fits (per `ui-ref-kit-inventory.md` §0 — icons are a path dictionary).
- Every screen is wrapped in `<Layout title="Creative Studio">` (title rendered once by `Header` as
  `text-h4`; **no PageHeader**). Sub-screens set their own title (`"Asset Library"`, `"Brand Kit"`).

---

## 2. SCREEN LIST (what we are designing — the deliverable index)

| # | Screen / surface | Route | Primary reference template to PORT |
|---|---|---|---|
| **S1** | **Studio workspace** (Create Banner hero + Campaign Context + Queue + Variants) | `/creative` | `HomePage` 2-col (`col-left`/`col-right`) + `NewProductPage` form-card grammar |
| **S2** | **Create Banner panel** (campaign + asset-type + platform + MODEL selector + command box) | inside S1 col-left top | `Field`, `Select`, `Tabs`, `Button` (`NewProductPage` head pattern) |
| **S3** | **Campaign Context panel** ("what the AI is using") | inside S1 col-right | `PopularProducts`/`Details` card pattern |
| **S4** | **Generation Queue + LIQUID live-loading state** (the signature animation) | inside S1 col-left | NEW `CreativeSkeleton` (token-built; spec §9) over `GridProduct` cards |
| **S5** | **Generated Variants Grid** (rich angle-labelled cards) | inside S1 col-left | `Products/DraftsPage/Grid` + `GridProduct` |
| **S6** | **Asset Detail panel** (preview/headline/CTA/angle/score/status + NL edit box) | right slide-`Modal` from S5/Library | `Customers/CustomerList/DetailsPage` + `Modal isSlidePanel` |
| **S7** | **Brand Kit panel** | `/creative/brand` | `SettingsPage` (anchor-section form) |
| **S8** | **Performance Insight panel** | inside S6 (a tab) + Library facet | `Products/OverviewPage` stat-card + `CardChartPie` |
| **S9** | **Asset Library** (filterable gallery) | `/creative/library` | `ExploreCreatorsPage` grid + `Filters` + `Search` + `Customers/CustomerList` head |
| **S10** | **Upload-reference → "make this kind of banner"** flow | inside S2 (+ Library "from this" action) | `FieldImage` dropzone → S2 command box |
| **S11** | **Approve / regenerate / resize quick-actions** | row actions on S5/S6 | `Button isStroke`/`isCircle`, `Dropdown`, `Badge` |
| **W1** | **WhatsApp page upgrade** (2 cards → premium multi-card: browse/preview/search/filter assets, attach, build template, send) | `/whatsapp` | `HomePage` 2-col + `ExploreCreatorsPage` grid + `MessagesPage` compose |

Below: each screen's exact layout, the reference components it ports, its data, and its states.

---

## 3. S1 — THE STUDIO WORKSPACE (flagship)

**Goal:** one screen where the vendor commands a generation and watches it happen. Apple-like: a calm
hero, a context proof, a live queue, a rich result wall. **Two-column reference rhythm** (`flex
max-lg:block` → `col-left` ~2/3, `col-right` ~1/3 — `HomePage/index.tsx`, principle §6).

```
┌─ Layout title="Creative Studio" ───────────────────────────────────────────────┐
│  COL-LEFT (≈66%)                                  COL-RIGHT (≈33%)               │
│  ┌─ Card: "Create" (S2 hero command) ─────────┐   ┌─ Card: "Campaign context" S3┐│
│  │ campaign Select | asset-type Tabs | platform│   │ business · product · offer  ││
│  │ Select | model Select (advanced, collapsed) │   │ audience · CTA · brand chips││
│  │ ┌ command box (Field textarea, big) ──────┐ │   │ "AI will use this" proof    ││
│  │ │ "Create 5 ad banners for this campaign" │ │   └─────────────────────────────┘│
│  │ └─────────────────────────────────────────┘ │   ┌─ Card: "Recent assets" ─────┐│
│  │ [Upload reference ▸ S10]   [Generate ▸blk] │   │ mini grid, link → Library   ││
│  │ est: "≈ 30 credits · 5 banners"  (master §34)│   └─────────────────────────────┘│
│  └─────────────────────────────────────────────┘                                  │
│  ┌─ Card: "Generation" (S4 queue + S5 grid) ──────────────────────────────────┐  │
│  │  [Generating…]  liquid skeleton cards  ▸  stream into ▸  variant cards (S5) │  │
│  └────────────────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────────────────┘
```

- **Empty state (first visit, nothing generated):** the "Generation" card shows `NoFound`-style block
  (`components/NoFound`) — one line "Pick a campaign and tell me what to make" + a primary `Button`
  that focuses the command box. (principle §9: real empty states.)
- **Cards used:** `components/Card` (title `text-h6`, `.card` = rounded-3xl + shadow-depth). No bare divs.

---

## 4. S2 — CREATE BANNER (the hero command bar)

Ports the **`NewProductPage` head grammar** (a row of selectors above a primary input) but composed as
ONE calm command surface. All reference components — nothing invented.

| Control | Reference component | Data / behaviour |
|---|---|---|
| **Campaign** selector | `components/Select` (`{id,name}[]`, label "Campaign") | from `lib/api` campaigns; selecting it drives S3 context + enables Generate. **#1 input** (master §6 campaign-based DNA). |
| **Asset type** | `components/Tabs` (pill segmented: Banner · Social · Story · Poster · Logo) | maps to engine `job_type` (`creative-image-banner-studio.md` §3 `BatchSpec.job_type`). |
| **Platform** | `components/Select` (Meta · WhatsApp · IG Story · Google · Hero · Custom) | maps to engine `sizes` per platform (master §7,§14). Default inferred from campaign; vendor can override. |
| **MODEL** selector | `components/Select`, label "Model", **`isBlack` styling, collapsed under an "Advanced" `Dropdown`** | model-agnostic: lists providers from `GET /creatives/status` `configured_providers` (Auto · Ideogram · GPT-Image · FLUX · Recraft). Default **"Auto (recommended)"** so the vendor never has to choose (master arch: OpenRouter = one provider, not the architecture). Shown small + secondary — power-user affordance, not a demand. |
| **Command box** | `components/Field` as `textarea` (`react-textarea-autosize` is already a kit dep) — large, hero | natural-language instruction. Placeholder rotates examples (master §38 commands): "Create 5 ad banners for this campaign" / "WhatsApp poster for hot leads, Hinglish" / "Make it premium, no price". |
| **Upload reference** | `components/Button isStroke icon="upload"` → opens S10 `FieldImage` | the "make this kind of banner" flow (master §38, §53). |
| **Generate** | `components/Button isBlack` (the ONE primary CTA on the screen) | calls `POST /creatives/batch` (`BatchSpec`). Disabled until a campaign is picked. |
| **Credit estimate line** | muted `text-body-2 text-t-secondary` under the button + `Badge` | "≈ 30 credits · 5 banners. Continue?" — the wallet-hold confirmation (master §34; engine §6 budget gate). On click, if `status:"over_budget"` or `"pending_approval"` returns, show an inline token banner (principle §9), never a raw error. |

**Progressive disclosure:** only Campaign + command box + Generate are prominent. Asset-type/platform/model
sit in a single quieter row; "Advanced" (model, count, sizes, language Hinglish/Hindi toggle, brand-colour
toggle) hides behind a `Dropdown`/disclosure. This is the "keep it SIMPLE for the vendor" mandate.

---

## 5. S3 — CAMPAIGN CONTEXT PANEL ("what the AI is using")

The trust surface — proves the AI already knows the business so the vendor doesn't re-spec (master §6,§17;
"don't re-ask what's already there"). Ports the **`PopularProducts` / `DetailsPage` Details** card pattern
(label + value rows, chips).

- **Card title:** "Campaign context" (`text-h6`). Renders when a campaign is selected; before that, a
  `NoFound` micro-state "Pick a campaign to see what I'll use."
- **Rows** (label `text-caption text-t-tertiary` / value `text-body-2 text-t-primary`): Business · Product ·
  Offer/Price · Location · Audience · Goal → CTA · Language. Each pulled by the engine's `context.enrich`
  (`creative-image-banner-studio.md` §8). A value the AI will INVENT nothing for (price/RERA/phone) is shown
  only if present in campaign data (master §20 text-accuracy guardrail) — missing ones render as a subtle
  "AI will ask if needed" chip, not a blank.
- **Brand chips:** logo thumbnail + colour swatches + tone, each a `Badge`/swatch; "Edit in Brand Kit" link
  → S7. (master §13 brand memory.)
- **Style hint:** a single `Select` "Style" (Premium · Local · Bold offer · Emotional · Trust · Minimal)
  pre-set from business+goal, overridable (master §10–12).

---

## 6. S4 — GENERATION QUEUE + THE LIQUID LIVE-LOADING STATE  ⭐ (the signature)

This is the founder's headline ask: a **premium live "liquid/wave" loading state — an animated placeholder
until the image streams in, like ChatGPT image generation** (master §36–37). Full animation spec in **§9**.

**Layout:** inside the "Generation" `Card` (S1 col-left bottom). On Generate, immediately render N
**skeleton cards** (N = requested count) in the SAME grid the variants will occupy (`Products/DraftsPage/Grid`
shape), so cards don't jump — they **transform in place** from liquid-skeleton → finished variant.

**Per-card lifecycle (each maps to a `BatchResult` variant status; engine §3,§5):**
1. **`queued`** — soft pulsing placeholder, angle label already shown ("Variant 2 · Urgency") with a small
   spinner (`components/Spinner`) — the vendor sees *what* is coming before it arrives.
2. **`generating`** — the **liquid wave** fills the card (§9): an animated gradient/shimmer sweeping the
   frame, like paint settling. A thin progress hairline + "Generating…" caption.
3. **`ready`** — the wave **dissolves** (300ms fade/clip-reveal) into the real image; the card snaps to the
   full S5 variant card (headline, angle badge, score, actions appear).
4. **`error`/`over_budget`** — card flips to a token-styled inline state (small red/amber `Badge` + retry
   `Button isCircle icon="repeat"`), never a blank or a thrown error (principle §9).

**Polling:** the page polls `GET /creatives/batch/{batch_id}` (engine §5 poll surface) and updates each
card's status; finished variants stream in as their `result.json` lands (engine §5 — "results return
automatically via the filesystem store"). A header strip shows "3 of 5 ready" + total credits spent.

**Header of the Generation card:** `headContent` slot (`Card` supports it) = a `Tabs` to flip the grid
between **All / Approved / Drafts** once results exist; a `Select` to sort (Newest · Best score).

---

## 7. S5 — GENERATED VARIANTS GRID (rich angle-labelled cards)

Ports **`templates/Products/DraftsPage/Grid` + `components/GridProduct`** (responsive image-card grid).
Each card is a finished `GridProduct`-style card, reskinned to creative data (master §8–9, §26 variant DNA).

**Card anatomy (top→bottom):**
- **Preview image** (the banner), object-cover, `rounded-3xl` top; `LikeButton`-style favourite in corner.
- **Angle badge** — `components/Badge` top-left over the image: "Price Focus" / "Urgency" / "Trust" /
  "Location" / "Offer" (master §8 — 5 DIFFERENT marketing angles, labelled clearly).
- **Headline** (`text-sub-title-1`) + **CTA** chip (`Badge`, e.g. "Book Site Visit") (master §10–11).
- **Meta row** (`text-caption text-t-tertiary`): platform · size (e.g. "Meta · 1080×1080") + **creative
  Score** as a small `Percentage`/`CardChartPie` dot (master §29 score: clarity/readability/CTA/brand-fit…).
- **Status `Badge`** (master §27): Draft · Needs review · Approved · Used · Rejected — one semantic colour
  map (success/warning/danger/neutral) reused from the kit, no raw hex.
- **Row actions** (on hover, `Button isCircle`): **Approve** (✓) · **Edit** (opens S6) · **Regenerate /
  5 more like this** (`Dropdown`) · **Resize** (`Dropdown` of sizes) · **Use →** (send to WhatsApp / Ads /
  Workflow). (master §26,§30,§32.)
- **Click anywhere** → opens **S6 Asset Detail** slide-panel.

Grid: `grid grid-cols-2 max-md:grid-cols-1 2xl:grid-cols-3 gap-4` (reference grid spacing, principle §10).
Variants are clearly labelled so the vendor reads them as a **testing set**, not random images (master §9 —
each carries a testing hypothesis for Adbot).

---

## 8. S6 — ASSET DETAIL PANEL (preview + NL edit)

The deep-edit surface, opened as a **right slide-over** (`components/Modal isSlidePanel` — the kit's
side-panel variant) so the vendor never leaves the workspace. Structurally ports the
**`Customers/CustomerList/DetailsPage`** master-detail "Details" pane.

**Left/top:** large preview of the banner (zoomable). **Right/below:** detail stack inside the panel:
- **Editable fields** (`components/Field`): Headline · Subheadline · CTA — inline-editable, each a real
  text layer the AI re-renders (master §10, engine §10 "render copy as a real text layer").
- **Meta block** (`Details` rows): Angle · Platform · Size · Language · Model used · Cost · Created.
- **Creative Score** card (`CardChartPie` mini or score bars) — the §29 sub-scores (readability, CTA,
  brand-match, platform-fit) with a one-line "why" (master §29). This is the **Performance/score** lens
  inline; live ad metrics (S8) appear here as a second `Tabs` panel once the asset is "Used".
- **Status control:** a `Select`/`Tabs` to set Draft → Needs review → Approved → Rejected (master §27;
  only Approved flows to Adbot). Rejecting prompts an optional reason → teaches the system (master §30).
- **⭐ NATURAL-LANGUAGE EDIT BOX** (master §26 — the differentiator): a `Field` textarea + Send. The vendor
  types plain edits: "make it premium", "remove price", "add my logo", "change CTA to Book Site Visit",
  "story size", "Hinglish", "5 more like this". Each edit creates a **NEW VERSION** (original kept — master
  §26) → fires a fresh `POST /creatives/generate` with the edit instruction + parent `variant_id`; the new
  version appears as a **version strip** (thumbnail row) at the bottom of the panel (a small `Tabs`/swiper of
  versions). Quick-chips above the box surface the common edits as one-tap `Button isStroke` pills (premium /
  simpler / remove price / add logo / story size / Hinglish / 5 more) so the vendor barely types.
- **Footer actions:** `Button isBlack` "Use this" (→ destination picker: WhatsApp / Ads / Workflow / Download),
  `Button isStroke` "Duplicate & edit", `Button isCircle` favourite.

---

## 9. ⭐ THE LIQUID / WAVE LOADING ANIMATION — full spec (token-built, no new dep)

The single most important "premium feel" detail. Built as ONE new component
`components/CreativeSkeleton/index.tsx` (the ONLY genuinely new component — everything else is ported),
styled entirely with **`@theme` tokens + a CSS keyframe in `globals.css`** so it inherits light/dark and
the brand blue. **No new npm package** (framer-motion is already a kit dep if JS-driven motion is wanted,
but CSS is sufficient and cheaper).

**Visual model (the "liquid"):** a card-sized rounded frame (`rounded-3xl`, same dims as the variant card)
filled with a **slow diagonal shimmer wave** — a moving linear-gradient band sweeping across a muted
`b-surface2`→`b-surface1` base, evoking paint/liquid settling, exactly the ChatGPT image-gen placeholder
feel. Layered:
1. **Base:** `bg-b-surface2`, `rounded-3xl`, subtle inner `shadow-depth`.
2. **Wave layer:** a `::before` with a 3-stop linear-gradient using `primary-01`(blue) at ~8% opacity →
   transparent, `background-size: 200% 200%`, animated `@keyframes liquid-sweep { 0%{background-position:0% 0%} 100%{background-position:200% 200%} }`, `~2.2s ease-in-out infinite`. Diagonal direction (135deg) reads as
   "liquid", not a flat skeleton sweep.
3. **Breathing layer:** a second `::after` soft radial highlight that slowly scales/opacity-pulses
   (`@keyframes liquid-breathe`, ~3s) so the surface looks alive, not a static bar.
4. **Foreground hints (so it's informative, not just pretty):** the **angle label** and a small
   `components/Spinner` are shown immediately (per S4 step-1), and a thin **progress hairline** at the
   bottom (`primary-01`, width animates queued→generating→90% then completes on `ready`).
5. **Reveal transition (`generating`→`ready`):** a 300ms **clip-path/opacity dissolve** — the wave layer
   fades + the real `<Image>` clip-reveals top-to-bottom (a "develops like a photo" feel). Use a CSS
   `transition` on `clip-path` + opacity; gate behind `prefers-reduced-motion` (fall back to a plain
   cross-fade) for accessibility.

**Tokens only:** colours = `primary-01` / `b-surface1` / `b-surface2`; radius `rounded-3xl`; shadow
`shadow-depth`. **Zero raw hex.** Dark mode "just works" because the base + accent are semantic vars.

**States the component renders** (driven by a `status` prop matching engine variant status): `queued`
(pulse + spinner + label) · `generating` (full liquid wave + progress) · `ready` (dissolve→image) ·
`error` (static muted frame + retry). One component, four states — drop-in inside the S4 grid.

**Acceptance:** sits in the exact grid slot a finished card will, animates smoothly at 60fps with CPU-cheap
CSS (no layout thrash — animate `background-position`/`opacity`/`transform` only), respects reduced-motion,
and morphs into the real card without a reflow/jump. This is the "like ChatGPT image gen" bar.

---

## 10. S7 — BRAND KIT PANEL

Ports **`templates/SettingsPage`** (left sticky anchor `Menu` + stacked section `Card`s via `react-scroll`).
`<Layout title="Brand Kit">`. Sections (each a `Card`, master §13 brand memory):
- **Logo** — `components/FieldImage` upload (the real HD logo); shown at the size the AI composites it.
- **Colours** — palette swatches (add/remove); the AI's "use my brand colour" source (master §38).
- **Tone & language** — `Select` (English/Hindi/Hinglish/Gujarati-local) + tone chips (master §13–14).
- **Preferred CTA** per goal — small editable list (master §11).
- **Do-not-use** — words/styles the AI must avoid (e.g. "no cheap discount look for a premium brand",
  master §13,§20). A simple `react-tagsinput` (kit dep).
- **Approved / best-performing styles** — read-only gallery the system learns from (master §13,§31).

This is one calm settings page; the vendor sets it once and the AI honours it everywhere.

---

## 11. S8 — PERFORMANCE INSIGHT PANEL

Phase-1 lives as a **tab inside S6** (per asset) + a **facet/sort in S9 Library** ("Best performing"),
NOT a separate page (principle §8 — fewer pages). Ports **`Products/OverviewPage`** stat-card grid +
`components/CardChartPie` / `Percentage`.
- **Per asset (S6 tab "Performance"):** impressions · clicks · CTR · leads · CPL · WA replies · bookings ·
  spend — stat tiles + a small trend chart (master §31). Honest empty state until the asset is "Used" and
  the ads/analytics loop reports back (`creative-image-banner-studio.md` §8 — metrics keyed by `variant_id`).
- **Library facet:** sort/filter by score & performance; a "Winners" row surfaces best assets → one-tap
  "5 more like this winner" (master §9,§30 Adbot loop). **Honesty note (engine FIX 1):** this panel only
  *reports* ad performance; it never moves ad budget — autonomous ad-spend caps live in the ads module.

---

## 12. S9 — ASSET LIBRARY (filterable gallery)

`<Layout title="Asset Library">`. The canonical gallery of every asset (master §28; backend
`design/creative-asset-library.md`). Ports **`templates/ExploreCreatorsPage`** (responsive card grid +
`templates/ExploreCreatorsPage/Filters`) with the **`Customers/CustomerList/CustomerListPage`** head row.

```
┌─ Card head ──────────────────────────────────────────────────────────────┐
│ "Asset Library"  | <Search isGray> | <Filters> | <Tabs: All·Approved·     │
│                                                   Drafts·Used·Winners> |   │
│                                                   <Button isBlack "Create">│ → S1
├─ Filter rail (Filters component) ────────────────────────────────────────┤
│ Campaign | Platform | Asset type | Status | Size | Vertical | Angle | Date│  (master §28 facets)
├─ Grid (ExploreCreatorsPage grid) ────────────────────────────────────────┤
│  [GridProduct cards — preview · angle badge · platform/size · status ·    │
│   score · used-in chips · hover actions]  …  responsive 2/3/4-up          │
└──────────────────────────────────────────────────────────────────────────┘
```

- **Cards** = same S5 `GridProduct` variant card (one card component, reused) so Studio and Library look
  identical — consistency is premium.
- **Filters** = `components/Filters` + `Select`s, facets per master §28 (campaign/platform/type/status/
  best-performing/date/size/vertical/angle). **Search** = `components/Search`. **Tabs** = status segments.
- **Data:** `GET /creatives?limit&offset&filters` (engine §9 / library search) — newest-first, tenant-scoped,
  paginated (same shape as `audit.tail`).
- **Row/card click** → S6 Asset Detail slide-over. **Empty/loading/error** → `NoFound` / `Spinner` / token
  banner (principle §9).
- **"From this →"** action on any card → opens S2 with that asset pre-loaded as the reference image (S10) +
  "make this kind of banner" — the reuse loop.

---

## 13. S10 — UPLOAD-REFERENCE → "MAKE THIS KIND OF BANNER"

The founder's explicit upload flow (master §38, §53). Entry points: the **Upload reference** button in S2,
and the **"From this →"** action on any Library/variant card.
- **Dropzone:** `components/FieldImage` (the kit's image dropzone) inside a small `Modal` or inline under
  the command box. Accepts a reference image (a competitor banner, a past creative, a product photo).
- **On upload:** a thumbnail pins above the command box with a removable `Badge`; the command box placeholder
  switches to "Make this kind of banner for [campaign] — Meta, premium". The reference image is passed as
  `ImageBrief.reference_image` (engine §3 `ImageBrief.reference_image`) to the generation.
- **Vendor mental model:** "here's the vibe I want, make it for my campaign" — zero design jargon.
- **Guardrail surface:** if the reference looks like a copyrighted/celebrity image, the engine's safety
  prefilter (engine §6) returns `blocked` → show a calm inline note, not an error dump (master §41 NEVER).

---

## 14. S11 — APPROVE / REGENERATE / RESIZE / USE (quick-action grammar)

Consistent action vocabulary across S5 cards, S6 panel, and S9 library — all reference components:
- **Approve / Reject** → status `Badge` toggle (master §27); `Button isCircle icon="check"/"close"`.
- **Regenerate / "5 more like this"** → `Dropdown` (same angle · new layout · new size · new CTA · new
  language · cleaner · new angle · 5-more-like-winner — master §26). Each spawns S4 liquid cards again.
- **Resize** → `Dropdown` of platform sizes (1:1 · 4:5 · 9:16 · 16:9 · Google · WA square/vertical · hero ·
  thumbnail — master §15). Produces a new version.
- **Use →** → `Dropdown`/Modal destination picker: **WhatsApp** (→ W1) · **Ads** (manual launch only, per
  engine FIX 1) · **Workflow** (asset-gen node, master §33) · **Download**.
All write through the engine endpoints (§9) and re-poll. No destructive overwrite — every edit is a new
version (master §41 "never overwrite old assets").

---

## 15. W1 — WHATSAPP PAGE UPGRADE (2 cards → premium multi-card)

**Today** (`app/whatsapp/page.tsx`): exactly 2 cards (a "Sent Log" table + a "Send a Message" form) and it
still uses the **deprecated `PageHeader`** (lines 7, 96–100) which the design principles say to DELETE.
**Target** (master §52–53): a premium, Apple-like multi-card layout where the vendor can **browse / preview
/ search / filter Creative Studio assets, attach one to a template, build the text template, and send** —
"no manual banner management."

**New layout — `HomePage` 2-col grammar (`col-left` ~2/3 / `col-right` ~1/3), title via `<Layout
title="WhatsApp">` only, PageHeader removed:**

```
┌─ Layout title="WhatsApp" ─────────────────────────────────────────────────────┐
│ COL-LEFT                                          COL-RIGHT                     │
│ ┌─ Card: "Compose" (build + attach + send) ───┐  ┌─ Card: "Creative assets" ──┐│
│ │ To (Field) | Template Select | text Editor   │  │ <Search> <Filters: campaign││
│ │ ┌ attached banner preview (or "Attach ▸") ─┐ │  │  · platform · status>      ││
│ │ │  [banner thumb]  headline · CTA  [change] │ │  │ ┌ asset grid (GridProduct)┐││
│ │ └───────────────────────────────────────────┘ │  │ │ [thumb][thumb][thumb]  │││
│ │ live WhatsApp-bubble PREVIEW (text+image)     │  │ │  click → preview/attach │││
│ │ [Send ▸ isBlack]   est/credits if any         │  │ └────────────────────────┘││
│ └───────────────────────────────────────────────┘  │ "AI: make a poster for     ││
│ ┌─ Card: "Sent log" (Table) ──────────────────┐    │  hot leads" → S1 (deep-link)││
│ │ when · phone · template · kind · status Badge│    └────────────────────────────┘│
│ └──────────────────────────────────────────────┘                                 │
└───────────────────────────────────────────────────────────────────────────────────┘
```

**Card-by-card (all reference components):**
- **"Creative assets" browser (col-right)** — ports `ExploreCreatorsPage` grid + `Filters` + `Search`. Shows
  Creative-Studio assets (`GET /creatives?filters`) filterable by campaign/platform/status; click a card →
  preview popover → **"Attach to message"**. This is the browse/preview/search/filter requirement (master §52).
- **"Compose" (col-left)** — the upgraded send surface:
  - **To** (`Field`), **Template** (`Select` of approved WA templates), **message text** (`components/Editor`
    or `Field` textarea) — "build the text template" (master §52). Params via `Field`/tagsinput.
  - **Attached banner** — a preview block; "Attach" pulls the selected asset from the right rail; "Change"
    swaps it. (Asset stays linked to its originating campaign for performance tracking — master §53.)
  - **AI-build-template affordance** — a `Button isStroke` "Ask AI to write this" → pre-fills text from the
    campaign (master §52 "AI can create the template from the campaign + attach the banner"). For NEW banners,
    a deep-link `Button` "Make a poster for hot leads" → opens S1 Studio with WhatsApp platform + the lead
    segment pre-set, then returns to attach.
  - **Live WhatsApp-bubble preview** — a small chat-bubble mock (token-styled, the `MessagesPage` chat bubble
    pattern) showing exactly how the image+text lands. Premium, reassuring.
  - **Send** — `Button isBlack` → existing `sendWhatsApp` (`lib/api`), keeping the current not-configured
    banner (creds dormant) but using a **token-based** banner, not the raw-hex one at current lines 112–114.
- **"Sent log" (col-left bottom)** — keep the existing log but port to `components/Table`/`TableRow` (not the
  raw `data-table`) + `Badge` for status, per the reuse map (no raw `<table>`).

**What changes vs today (concrete):** remove `PageHeader` import + usage; replace the 2-card flat layout with
the 2-col multi-card grammar; ADD the asset browser + attach + live-preview + AI-build; convert the raw
`<table>`/`.data-table` to `Table`/`TableRow`; replace raw-hex amber banner with token classes
(`primary-05`/`b-surface`). Net: it becomes a real creative-aware messaging console, not a form.

---

## 16. CROSS-CUTTING UI RULES (every screen must pass — the acceptance bar)

From `ui-design-principles.md` §7 checklist, applied to Creative Studio:
- [ ] Each screen wrapped in `Layout` with ONE `title`; **no `PageHeader`, no eyebrow, no subtitle.**
- [ ] Every section is a `components/Card` (`text-h6` title, `pt-3` body). No bare custom panels.
- [ ] Two-column rhythm (`col-left`/`col-right`) on S1 & W1; reference grids on S5/S9; stacks on mobile.
- [ ] Reference components ONLY (`Card`, `Tabs`, `Select`, `Field`, `Button`, `GridProduct`, `Filters`,
      `Search`, `Modal`, `Table`, `Badge`, `NoFound`, `Spinner`, `CardChartPie`, `Percentage`,
      `FieldImage`, `Editor`, `Dropdown`). The ONLY new component is `CreativeSkeleton` (§9), token-built.
- [ ] **Zero raw hex** — semantic `@theme` tokens only (`primary-01` brand blue, status colours; surfaces
      `b-surface1/2`; text `t-primary/secondary/tertiary`). Brand = ONE decisive blue; ≤2 saturated colours.
- [ ] Inter Display throughout; type ramp tokens only; nothing bigger than `text-h4` in content.
- [ ] Real loading (`Spinner` + the §9 liquid state) / empty (`NoFound`) / error (one token banner) on every
      data surface. No raw "undefined", no blank flashes.
- [ ] Plain language — "Create / Library / Brand Kit / Approve / Use", no internal jargon (no "BatchSpec",
      "job_type", "variant_id", "provider" in the vendor's face — those stay in tooltips/advanced).
- [ ] Progressive disclosure: model/provider/count/sizes/language under "Advanced"; default "Auto".
- [ ] Vendor-simple: campaign + one instruction + Generate is the whole happy path.

---

## 17. DATA WIRING (which endpoint each surface calls — engine §9 / library §7)

| Surface | Endpoint | Returns |
|---|---|---|
| Model selector, provider readiness, budget snapshot | `GET /creatives/status` | `configured_providers`, `default_provider`, `budget` |
| Generate (S2) | `POST /creatives/batch` (`BatchSpec`) | `{batch_id, status:"accepted"}` |
| Queue poll / variants stream (S4/S5) | `GET /creatives/batch/{batch_id}` | `BatchResult` + variant manifest (status per variant) |
| NL edit / regenerate / resize (S6/S11) | `POST /creatives/generate` (`ImageBrief` w/ edit + parent `variant_id`) | new-version `ImageResult` |
| Approve hold-gated batch (if approval on) | `POST /creatives/batch/{id}/approve` | `BatchResult` |
| Asset bytes (previews) | `GET /creatives/{job_id}/asset/{i}` | image bytes |
| Library list/filter (S9, W1 browser) | `GET /creatives?limit&offset&filters` | newest-first tenant-scoped list |
| Single asset detail (S6) | `GET /creatives/{job_id}` | `result.json` |
| WhatsApp send (W1) | `sendWhatsApp` (existing `lib/api`) | send status |

All tenant-scoped + auth via the existing middleware (engine §9). The UI never sees a provider key.

---

## 18. BUILD ORDER (for the later front-end wave — small verifiable units)

1. Add `app/creative/` route group + nav entry; `<Layout title="Creative Studio">` shells for S1/S9/S7
   (empty `NoFound` states first) → renders, nav active state correct.
2. **`components/CreativeSkeleton`** (§9) + `globals.css` keyframes → the liquid state in isolation
   (Storybook-style page) → 60fps, reduced-motion fallback, dark mode.
3. S2 Create hero (selectors + command box + Generate wired to `POST /creatives/batch`).
4. S3 Campaign context (reads campaign + `context.enrich`).
5. S4 queue poll + S5 variant grid (skeleton → variant morph) against `GET /creatives/batch/{id}`.
6. S6 Asset Detail slide-over + NL edit (new-version flow) + status control.
7. S9 Library (grid + filters + search) against `GET /creatives`.
8. S7 Brand Kit (SettingsPage port). S8 performance tab (honest empty until ads loop reports).
9. S10 upload-reference flow. S11 use→destination picker.
10. **W1 WhatsApp upgrade** (remove PageHeader, 2-col multi-card, asset browser + attach + preview, Table port).
11. Run against the reference acceptance checklist (§16) per page → green.

Each unit reuses a named reference template/component; nothing is hand-built except `CreativeSkeleton`.

---

## 19. SOURCES / GROUND TRUTH (file evidence)

- Master spec: `CREATIVE_STUDIO_MASTER_PROMPT.md` §2,§7–17,§26–38,§41,§52–53.
- Backend engine + endpoints + statuses: `design/creative-image-banner-studio.md` §3,§5,§6,§8,§9,§10 + FIX 1.
- Asset library backend (gallery data): `design/creative-asset-library.md` §0–2,§7.
- Engine layer: `memory/brain/media-gen.md`.
- UI rules / reuse / acceptance: `design/ui-design-principles.md` (10 rules + §7 checklist),
  `design/ui-ref-kit-inventory.md` (components, tokens, templates), `design/spec-core2-reuse-map.md`
  (6 archetypes + exact `C2/templates/*` source paths).
- Reference components verified on disk: `core-2-dashboard-builder-react/components/{Card,Tabs,Select,
  Field,Button,GridProduct,Filters,Search,Modal,Table,TableRow,Badge→via labels,NoFound,Spinner,
  CardChartPie,Percentage,FieldImage,Editor,Dropdown,Layout,Sidebar,Header}` + `templates/{HomePage,
  ExploreCreatorsPage,MessagesPage,SettingsPage,Customers/CustomerList/DetailsPage,Products/*}`.
- Current WhatsApp page to upgrade: `famit-panel/app/whatsapp/page.tsx` (2 cards + deprecated PageHeader
  L7,96–100; raw `<table>` L125; raw-hex banner L112–114).
```
