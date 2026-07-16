# CREATIVE STUDIO — FINAL WORKSPACE DESIGN (screen-by-screen, build-ready)

> **READ-ONLY DESIGN WAVE.** This is the FINAL, screen-by-screen design of the Creative Studio
> page(s) as a premium creative **WORKSPACE** (Apple-like rich multi-card, intentional placement).
> It refines `design/creative-studio-ui.md` and binds it to the **real, frozen backend API**
> (`design/asset-service-backend.md` §8 + `memory/brain/creative-studio.md` A3 — base `/api/assets/*`),
> the founder master spec (`CREATIVE_STUDIO_MASTER_PROMPT.md`), and Phase-2
> (`CREATIVE_STUDIO_PHASE2_SPEC.md` — the dot-matrix loader + WhatsApp Campaign Builder + "out-of-the-box"
> additions). Built per `design/ui-design-principles.md` (PORT, DON'T APPROXIMATE).
>
> **Reference kit (CODE = source of truth, verified on disk):**
> `C:\Users\kunal\Desktop\core-2-dashboard-builder-react` (`components/*`, `templates/*` confirmed).
> **Our app:** `C:\Users\kunal\Desktop\caps\famit-panel`. **The Creative Studio frontend build runs
> AFTER the UI-overhaul build clears the `famit-panel` frontend lane** (design ON TOP of that look).
>
> **⚠ CONTRACT RECONCILIATION (load-bearing — supersedes the old UI doc's `/creatives/*` names):**
> The backend is BUILT and FROZEN at base **`/api/assets/*`** (frontend-box nginx `location /api/assets/
> → 127.0.0.1:8310`). The OLD `creative-studio-ui.md` §17 calls (`/creatives/batch`, `BatchResult`,
> `batch_id`) map 1:1 to the real surface: **`POST /api/assets/generate` → `{job_id, state, est_cost}`**,
> poll **`GET /api/assets/jobs/{id}`**, stream **`GET /api/assets/jobs/{id}/stream` (SSE)**. Every wiring
> in §16 below uses the REAL frozen routes. The whole surface is `503`-gated by `AIASSET_ENABLED` except
> `GET /api/assets/status` (the dormancy probe) — so EVERY screen must render a calm dormant state.

---

## 0. THE PRODUCT IDEA IN ONE LINE

> **"I tell what I need, AI creates it."** A campaign-aware AI design engine (AI designer + AI copywriter
> + AI ad strategist), NOT a canvas tool and NOT a random image generator. The vendor picks a **campaign**,
> types/says ONE instruction, and watches angle-labelled banners stream in — built FROM their real campaign
> data (product, audience, offer, CTA, size, style all inferred; master §3–6, §17). The UI's only job is
> to make that feel **inevitable and premium**: a calm hero command bar, a Campaign Context panel that
> PROVES the AI already knows the business, the dot-matrix "neural" live-generation state, rich result
> cards read as a testing set, and a deep Asset Detail with a natural-language edit box. All complexity
> (model routing, providers, spend, scoring) is present but tucked under progressive disclosure — never in
> the vendor's face. This maps to master §36: *premium creative WORKSPACE, not a form.*

---

## 1. WHERE IT LIVES (route + nav)

- **Route group:** `app/creative/` in `famit-panel` (NEW). Sidebar **single group "Creative Studio"**
  (plain noun). Phase-1 children only (coming-soon stays out of nav, principles §8):
  - **Studio** → `/creative` — the flagship create + context + queue + variants workspace.
  - **Library** → `/creative/library` — the filterable gallery of every asset.
  - **Brand Kit** → `/creative/brand` — logo / colours / tone the AI uses.
  - *(Insights + Performance fold INTO Asset Detail + Library facets — no separate page, principles §8.)*
- Nav entry added to `contstants/navigation.tsx`: `{title:"Creative Studio", icon:"image", list:[…]}`;
  icon = existing `components/Icon` path (`image`/`grid`/`camera`), add ONE SVG path only if none fits.
- Every screen wrapped in `<Layout title="…">` (title rendered once by `Header` as `text-h4`; **NO
  PageHeader, no eyebrow, no subtitle**). Sub-screens set their own title ("Asset Library", "Brand Kit").

---

## 2. SCREEN / SECTION LIST (the deliverable index)

| # | Screen / surface | Route | Primary reference template/component to PORT |
|---|---|---|---|
| **S1** | **Studio workspace** (Create + Context + Queue + Variants) | `/creative` | `templates/HomePage` 2-col (`col-left`/`col-right`) + `templates/Products/NewProductPage` form-card grammar |
| **S2** | **Create panel** (campaign + asset-type + platform + **MODEL** + command box + Generate) | inside S1 col-left top | `components/Select` · `Tabs` · `Field` (textarea) · `Button` (NewProductPage head pattern) |
| **S3** | **Campaign Context panel** ("what data the AI is using") | inside S1 col-right | `components/PopularProducts` + `Customers/CustomerList/DetailsPage/Details` row pattern |
| **S4** | **Generation Queue + the loaders** (batch `GenerationLoader` hero ⊕ per-card `CreativeSkeleton`) ⭐ | inside S1 col-left | NEW `components/GenerationLoader` (batch) + NEW `components/CreativeSkeleton` (per-card) over `Products/DraftsPage/Grid` slots — see `design/cs-loading-component.md` |
| **S5** | **Variants Grid** (rich angle-labelled cards) | inside S1 col-left | `templates/Products/DraftsPage/Grid` + `components/GridProduct` |
| **S6** | **Asset Detail panel** (preview / headline / CTA / angle / platform / score / status + NL EDIT + regen/resize/approve) | right slide-over from S5/Library | `components/Modal isSlidePanel` + `Customers/CustomerList/DetailsPage` |
| **S7** | **Brand Kit panel** | `/creative/brand` | `templates/SettingsPage` (sticky anchor menu + section cards) |
| **S8** | **Performance Insight panel** | tab inside S6 + Library facet | `Products/OverviewPage` stat grid + `components/CardChartPie` + `Percentage` |
| **S9** | **Asset Library** (filterable gallery) | `/creative/library` | `templates/ExploreCreatorsPage` grid + `Filters` + `Search` + `Customers/CustomerList/CustomerListPage` head |
| **S10** | **Upload-reference → "make this kind of banner"** flow | inside S2 (+ Library "From this →") | `components/FieldImage` dropzone → S2 command box |
| **S11** | **Approve / Regenerate / Resize / Use** quick-action grammar | row actions on S5 / footer on S6 | `Button isCircle/isStroke` · `Dropdown` · `Badge` |
| **W1** | **WhatsApp Campaign Builder upgrade** (2 cards → premium multi-card workspace) | `/whatsapp` | `HomePage` 2-col + `ExploreCreatorsPage` grid + `MessagesPage` compose/bubble |

Below: each surface's exact layout, the reference bricks it ports, its API binding, and its dormant states.

---

## 3. S1 — THE STUDIO WORKSPACE (flagship)

**Goal:** one screen where the vendor commands a generation and watches it happen. Apple-like rhythm: a calm
hero, a context proof, a live queue, a rich result wall. **Two-column reference grammar** (`flex max-lg:block`
→ `col-left` ≈ 66 %, `col-right` ≈ 33 % — `templates/HomePage/index.tsx`, principles §6).

```
┌─ Layout title="Creative Studio" ───────────────────────────────────────────────────┐
│  COL-LEFT (≈66%)                                     COL-RIGHT (≈33%)                │
│  ┌─ Card "Create"  (S2 hero command) ─────────────┐  ┌─ Card "Campaign context" S3 ┐│
│  │ campaign Select | asset-type Tabs | platform   │  │ business · product · offer  ││
│  │ Select | [⚙ Advanced ▸ model/count/size/lang]  │  │ audience · goal→CTA · brand ││
│  │ ┌ command box (Field textarea, hero) ─────────┐ │  │ provenance chips · "AI uses ││
│  │ │ "Create 5 ad banners for this campaign"     │ │  │ this" proof  [Edit Brand ▸] ││
│  │ └─────────────────────────────────────────────┘ │  └─────────────────────────────┘│
│  │ [⤒ Upload reference ▸S10]      [Generate ▸blk] │  ┌─ Card "Recent assets" ──────┐│
│  │ est: "≈ 30 credits · 5 banners"  (master §34)  │  │ mini GridProduct row →Library││
│  └─────────────────────────────────────────────────┘  └─────────────────────────────┘│
│  ┌─ Card "Generation"  (S4 queue + S5 grid) ──────────────────────────────────────┐ │
│  │ headContent: Tabs[All·Approved·Drafts] · Select[Newest·Best score] · "3 of 5 ✓"│ │
│  │ [GenerationLoader dot-matrix cards] ─stream/morph in place→ [S5 variant cards]  │ │
│  └─────────────────────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────────────────────┘
```

- **Cards:** `components/Card` only (title `text-h6`, `.card` = `rounded-3xl` + `shadow-depth` + `p-4`).
  The "Generation" card uses its `headContent` slot for the segment Tabs + sort Select + progress strip.
- **First-visit empty state:** the Generation card renders a `components/NoFound` block — one line
  "Pick a campaign and tell me what to make" + a primary `Button` that focuses the command box (principles §9).
- **DORMANT state (`AIASSET_ENABLED=0` → `GET /api/assets/status` says `enabled:false`):** the Generate
  button is disabled with a calm token banner inside the Create card — "Creative Studio activates once your
  workspace is enabled" — and the Recent/Generation cards show `NoFound`. **No errors, no blank flashes** —
  every screen is dormant-safe because the whole API is 503-gated except `/status`.

---

## 4. S2 — CREATE PANEL (the hero command bar)

Ports the **`Products/NewProductPage` head grammar** (a row of selectors above a primary input), composed as
ONE calm command surface. All reference components — nothing invented.

| Control | Reference component | Data / behaviour / API |
|---|---|---|
| **Campaign** | `components/Select` (`{id,name}[]`, label "Campaign") | from `lib/api` campaigns; selecting it drives S3 + enables Generate. **#1 input** (master §6). |
| **Asset type** | `components/Tabs` (pill: Banner · Social · Story · Poster · Logo) | → `asset_type` in the generate body (master §7). |
| **Platform** | `components/Select` (Meta · WhatsApp · IG Story · Google · Hero · Custom) | → `platform`; default inferred from campaign, vendor can override (master §7,§14). |
| **MODEL** selector | `components/Select` label "Model", **collapsed under "Advanced" `Dropdown`** | model-AGNOSTIC: list from **`GET /api/assets/providers`** (`{provider_id, display_name, capabilities, cost_minor}`). Default **"Auto (recommended)"** so the vendor never picks a provider (master arch: OpenRouter = ONE provider, not the architecture). Small + secondary. |
| **Command box** | `components/Field` as `textarea` (`react-textarea-autosize` is a kit dep) — large, hero | the NL `instruction`. Placeholder rotates master-§38 examples: "Create 5 ad banners for this campaign" / "WhatsApp poster for hot leads, Hinglish" / "Make it premium, no price". |
| **Upload reference** | `components/Button isStroke icon="upload"` → opens **S10** | the "make this kind of banner" flow (master §38,§53) → **`POST /api/assets/variation-from-upload`**. |
| **Generate** | `components/Button isBlack` — the ONE primary CTA | **`POST /api/assets/generate`** body `{campaign_id?, platform, asset_type, count, instruction, language, model?, brand_kit_id?}` → `{job_id, state, est_cost}`. Disabled until a campaign is picked; idempotent (UI sends a client `idempotency_key` to dedupe double-click). |
| **Credit estimate line** | muted `text-body-2 text-t-secondary` + `Badge` under Generate | "≈ 30 credits · 5 banners. Continue?" — the wallet-hold confirmation (master §34). If generate returns `state:"over_budget"` (HTTP 402) → inline token banner (principles §9), never a raw error; `state:"needs_input"` → render the `clarify` chips (which campaign? premium or offer? include price?) inline, never a full re-spec. |

**Progressive disclosure (the "keep it SIMPLE" mandate):** only **Campaign + command box + Generate** are
prominent. Asset-type/platform sit in one quieter row. **"Advanced" `Dropdown`** hides model · count · sizes ·
language (Hinglish/Hindi/Gujarati toggle) · brand-colour toggle. Default everything to "Auto".

---

## 5. S3 — CAMPAIGN CONTEXT PANEL ("what data the AI is using")

The **trust surface** — proves the AI already knows the business so the vendor doesn't re-spec (master §6,§17;
"don't re-ask what's already there"). Ports the **`PopularProducts` / `DetailsPage/Details`** label-value-row +
chip pattern. Data comes from the job's resolved `campaign_ctx` snapshot (backend §4 Campaign Reader,
provenance-tagged `from_campaign | from_brand_kit | from_me | absent`).

- **Card title:** "Campaign context" (`text-h6`). Renders when a campaign is selected; before that a
  `NoFound` micro-state "Pick a campaign to see what I'll use."
- **Rows** (label `text-caption text-t-tertiary` / value `text-body-2 text-t-primary`): Business · Product ·
  Offer/Price · Location · Audience · Goal → CTA · Language. **A value the AI must NEVER invent (price / RERA
  / phone) renders ONLY if provenance ≠ `absent`** (master §20 / backend §3.1 no-invent). A missing key field
  shows a subtle **"AI will ask if needed"** chip, not a blank — and if generate returns `needs_input`, those
  chips light up as the clarify questions.
- **Provenance dots:** each row carries a tiny `Badge`-dot (filled = from real data, hollow = AI will ask) so
  the vendor SEES the AI is grounded in facts, not hallucinating — a premium trust cue + the §20 guarantee made
  visible.
- **Brand chips:** logo thumbnail + colour swatches + tone, each a `Badge`/swatch from `GET /api/assets/brand-kits`;
  **"Edit in Brand Kit" → S7** (master §13).
- **Style hint:** a single `Select` "Style" (Premium · Local · Bold offer · Emotional · Trust · Minimal),
  pre-set from business+goal, overridable; flows into the generate `instruction`/advanced (master §10–12).

---

## 6. S4 — GENERATION QUEUE + THE GenerationLoader  ⭐ (the signature)

The founder's headline ask (master §36–37; Phase-2 §1). **The TWO genuinely new components** (everything else
is a ported reference brick) are spec'd in detail in the companion doc **`design/cs-loading-component.md`** — this
section is the WORKSPACE-PLACEMENT view of how they sit inside S1/S4. Both are token-built (canvas + CSS
fallback), no new npm dep, dark-mode-free via semantic vars:
- **`components/GenerationLoader`** = the BATCH-level "engine thinking" HERO (charcoal card on near-black with
  the dot-matrix neural-energy field + cycling status lines). Shown while the job is in `reading_campaign /
  building_prompts` and as the overlay for a single large generation (Phase-2 §1).
- **`components/CreativeSkeleton`** = the PER-CARD "this slot is developing" loader that sits in each variant
  grid slot and morphs IN PLACE → the finished S5 card. (The old `creative-studio-ui.md` §9 liquid-wave is this
  one; the canvas dot-matrix in `cs-loading-component.md` upgrades the look.)
They **COMPOSE**: the GenerationLoader hero collapses → a grid of N CreativeSkeleton cards stream in. Full
animation/props/build-order spec = `design/cs-loading-component.md` (do NOT re-derive here; §9 below is the
placement summary).

**Layout:** inside the "Generation" `Card` (S1 col-left bottom). On Generate, immediately render N **loader
cards** (N = requested count) in the SAME grid the variants will occupy (`Products/DraftsPage/Grid` shape) so
cards **don't jump** — each **transforms in place** loader → finished variant.

**Per-card lifecycle (each maps to a real job/variant state — backend job machine
`queued→running→streaming→succeeded|partial|failed|cancelled`, `phase = reading_campaign|building_prompts|
rendering|scoring|storing|done`):**
1. **`queued` / `reading_campaign` / `building_prompts`** — the dot-matrix field breathes; the **angle label
   is already shown** ("Variant 2 · Urgency") with a small `components/Spinner` — the vendor sees *what* is
   coming before it arrives.
2. **`streaming` / `rendering`** — the full **dot-matrix neural field** animates (soft grey/white dots in a
   circular field, centre brighter/larger, outer faded, slowly pulsing/drifting); a charcoal card on a dark
   preview area with a small muted "Thinking" line and a bold title ("Creating banner"). Cycling status lines
   (Phase-2 §1): "Understanding campaign" → "Designing visual direction" → "Composing layout" → "Rendering
   creative" → "Finalizing output". **No fake percentage** — only show real progress if the job's `progress`
   JSON carries `{total, done}`; otherwise just the animated state.
3. **`succeeded` (this variant's bytes land)** — the field **dissolves** (300 ms fade/clip-reveal, "develops
   like a photo") into the real image; the card snaps to the full S5 variant card (headline, angle badge,
   score, actions appear).
4. **`failed` / `over_budget` / `cancelled`** — the card flips to a token-styled inline state (small
   danger/warning `Badge` + retry `Button isCircle icon="repeat"`) — never a blank, never a thrown error
   (principles §9).

**Live transport (real frozen API):** the page opens **`GET /api/assets/jobs/{job_id}/stream` (SSE)** and
updates each card as variants render and stream in; **`GET /api/assets/jobs/{job_id}`** is the single-shot
poll fallback for clients without SSE. A header strip (`headContent`) shows "3 of 5 ready" + total credits
spent (from the job's `actual_cost_minor`). On `partial`, the unfinished cards show the retry state and the
wallet auto-refunds the unrendered remainder (backend §6) — surfaced as a calm "2 didn't render — refunded"
note, never an error dump.

**Header of the Generation card (`headContent` slot):** `Tabs` to flip the grid **All / Approved / Drafts**
once results exist; a `Select` to sort **Newest · Best score**.

---

## 7. S5 — VARIANTS GRID (rich angle-labelled cards)

Ports **`templates/Products/DraftsPage/Grid` + `components/GridProduct`** (responsive image-card grid). Each
card is a finished `GridProduct`-style card reskinned to creative data (master §8–9, §26 variant DNA). **This
exact card component is reused in the Library (S9) and the WhatsApp asset browser (W1) — ONE card everywhere.**

**Card anatomy (top → bottom):**
- **Preview image** (the banner), object-cover, `rounded-3xl` top; `components/LikeButton` favourite in corner.
  Bytes from **`GET /api/assets/{id}/raw`** (`local_path` never exposed; ownership-checked).
- **Angle badge** — `components/Badge` top-left over the image: "Price Focus" / "Urgency" / "Trust" /
  "Location" / "Offer" (master §8 — 5 DIFFERENT marketing angles, labelled, not 5 random images).
- **Headline** (`text-sub-title-1`) + **CTA chip** (`Badge`, e.g. "Book Site Visit") (master §10–11).
- **Meta row** (`text-caption text-t-tertiary`): platform · size (e.g. "Meta · 1080×1080") + **creative
  Score** as a small `components/Percentage` / `CardChartPie` dot (master §29; the `ai_creative_scores`
  overall 0–100).
- **Status `Badge`** (master §27): Draft · Needs review · Approved · Used · Rejected — one semantic colour map
  (success `primary-02` / warning `primary-05` / danger `primary-03` / info `primary-01` / neutral), no raw hex.
- **Row actions** (hover, `Button isCircle`): **Approve** ✓ · **Edit** (opens S6) · **Regenerate / "5 more
  like this"** (`Dropdown`) · **Resize** (`Dropdown` of sizes) · **Use →** (WhatsApp / Ads / Workflow /
  Download). (master §26,§30,§32; the S11 grammar.)
- **Click anywhere** → opens **S6 Asset Detail** slide-panel.

Grid: `grid grid-cols-2 max-md:grid-cols-1 2xl:grid-cols-3 gap-4` (reference spacing, principles §10). The set
reads as a **testing set** — each variant carries a `hypothesis` for Adbot (master §9), shown in S6.

---

## 8. S6 — ASSET DETAIL PANEL (preview + NL edit + the full action surface)

The deep-edit surface, opened as a **right slide-over** (`components/Modal isSlidePanel` — verified prop) so the
vendor never leaves the workspace. Structurally ports **`Customers/CustomerList/DetailsPage`** master-detail
pane. Data from **`GET /api/assets/{id}`** (current version, all versions, score, status, usage, metrics).

**Top/left:** large zoomable preview (`GET /api/assets/{id}/raw`). **Right/below — detail stack inside the panel:**

- **Editable copy fields** (`components/Field`): Headline · Subheadline · CTA — inline-editable real text
  layers the AI re-renders (master §10).
- **Meta block** (`Details` rows): Angle · Platform · Size · Language · Model used · Cost · Created.
- **Creative Score** (`CardChartPie` mini or score bars) — the §29 sub-scores (clarity / readability / CTA /
  brand-match / platform-fit / quality / conversion / relevance / text-amount / offer-visibility) with a
  one-line "why". This is the inline score lens; **S8 Performance** appears here as a SECOND `Tabs` panel once
  the asset is "Used".
- **Status control:** a `Select`/`Tabs` Draft → Needs review → Approved → Rejected →
  **`POST /api/assets/{id}/approve`** / **`/reject`** (master §27; only Approved flows to Adbot/WhatsApp).
  Rejecting prompts an optional reason → appended to brand `do_not_use` (the system learns; master §30 / backend §10).
- **⭐ NATURAL-LANGUAGE EDIT BOX** (master §26 — the differentiator): a `Field` textarea + Send. The vendor
  types plain edits — "make it premium", "remove price", "add my logo", "change CTA to Book Site Visit",
  "story size", "Hinglish", "5 more like this". Each edit fires **`POST /api/assets/{id}/edit`** (or
  `/regenerate` for "more like this") → creates a **NEW VERSION** (`ai_asset_versions`, original NEVER
  overwritten — master §26/§41). The new version appears as a **version strip** (thumbnail swiper, a small
  `Tabs`) at the bottom; selecting a version + Approve flips `current_version_id` (rollback is free).
  **Quick-chip pills** above the box surface the common edits as one-tap `Button isStroke` (premium · simpler ·
  remove price · add logo · story size · Hinglish · 5 more) so the vendor barely types.
- **Footer actions (S11 grammar):** `Button isBlack` "Use this" → destination `Dropdown`/Modal (WhatsApp →W1 ·
  Ads · Workflow · Download) → **`POST /api/assets/{id}/attach`**; `Button isStroke` "Duplicate & edit";
  `Button isCircle` favourite.

---

## 9. ⭐ THE LOADERS — placement summary (FULL spec = `design/cs-loading-component.md`)

The single most important "premium feel" detail (Phase-2 §1; the founder's repeated headline). **Two new
components** — `GenerationLoader` (batch hero) + `CreativeSkeleton` (per-card) — fully spec'd (props, canvas
field, build order) in the companion doc `design/cs-loading-component.md`. This section ONLY describes how they
sit inside the S1/S4 workspace; it does **not** re-derive the animation. Both are token-pure (no raw hex), no
new npm dep, dark-mode-free, `prefers-reduced-motion`-safe.

**How they compose in S1's "Generation" card (the workflow placement):**
1. On Generate, the **GenerationLoader hero** appears INSTANTLY (the engine "thinking" state) while the job is
   `queued / reading_campaign / building_prompts` — charcoal card, dot-matrix neural field, cycling lines
   ("Understanding campaign → Designing visual direction → Composing layout → Rendering creative → Finalizing
   output"). It maps `phase` 1:1 to `ai_generation_jobs.phase` and shows a real progress hairline ONLY if the
   job's `progress.total` exists — **never a fabricated %**.
2. As the job hits `streaming` (prompts built, render fan-out), the hero **collapses** into a grid of **N
   `CreativeSkeleton` cards** (N = requested count) in the SAME `Products/DraftsPage/Grid` slots the variants
   will occupy — so cards **don't jump**. Each skeleton shows its **angle label + `Spinner` immediately**
   (informative) over the breathing field.
3. As each variant's bytes land (SSE `GET /api/assets/jobs/{id}/stream`), THAT skeleton **dissolves in place**
   (300 ms clip/opacity, "develops like a photo") into the finished S5 `GridProduct` card — headline, angle
   badge, score, actions appear. No reflow.
4. On `failed`/`over_budget`/`cancelled` a card flips to a token-styled retry state (danger/warning `Badge` +
   `Button isCircle icon="repeat"`) — never a blank, never a thrown error.

**Reusable primitive:** the same GenerationLoader is the overlay for ANY single large generation (image /
banner / ad-creative / brochure-cover / video-thumbnail — Phase-2 §1 quality bar). **Acceptance** (asserted in
`cs-loading-component.md`): 60 fps CPU-cheap canvas (CSS fallback for reduced-motion / no-canvas / low-power),
token-pure, morphs into the real card with no jump — "like ChatGPT image gen."

---

## 10. S7 — BRAND KIT PANEL

Ports **`templates/SettingsPage`** (left sticky anchor `Menu` + stacked section `Card`s via `react-scroll`).
`<Layout title="Brand Kit">`. Data via **`GET/POST/PUT /api/assets/brand-kits`** (`ai_brand_kits`). Sections
(each a `Card`, master §13 brand memory):

- **Logo** — `components/FieldImage` upload (real HD logo) → `logo_url`; shown at the composite size.
- **Colours** — palette swatches add/remove → `palette[]`; the AI's "use my brand colour" source (master §38).
- **Tone & language** — `Select` (English / Hindi / Hinglish / Gujarati-local) → `language_pref` + tone chips
  → `tone` (master §13–14).
- **Preferred CTA** per goal — small editable list → `default_cta` (master §11).
- **Do-not-use** — words/styles the AI must avoid ("no cheap discount look for a premium brand") →
  `do_not_use{words,styles,colors}` (master §13,§20). A `react-tagsinput` (kit dep).
- **Approved / best-performing styles** — read-only gallery the system learns from → `best_style` (master
  §13,§31; reject feeds `do_not_use`, win reinforces `best_style` — backend §10).
- **⭐ OUT-OF-THE-BOX: "Auto-extract brand kit"** — a `Button isStroke` "Extract from my website / a logo" that
  seeds palette + logo + tone from an uploaded asset or URL (Phase-2 §4 proactive add; wires to a future
  `POST /api/assets/brand-kits/extract`). Surfaced as optional, dormant-safe until built.

One calm settings page; the vendor sets it once and the AI honours it everywhere.

---

## 11. S8 — PERFORMANCE INSIGHT PANEL

Phase-1 lives as a **tab inside S6** (per asset) + a **facet/sort in S9 Library** ("Best performing"), NOT a
separate page (principles §8 — fewer pages). Ports **`Products/OverviewPage`** stat-card grid +
`components/CardChartPie` / `Percentage`.

- **Per asset (S6 tab "Performance"):** impressions · clicks · CTR · leads · CPL · WA replies · bookings ·
  spend — stat tiles + a small trend chart (master §31). Source = `ai_assets.metrics` / `ai_asset_usage.metrics`
  written back by Adbot (backend §10). **Honest empty state** until the asset is "Used" and the ads/analytics
  loop reports — never zeros pretending to be data (principles §9).
- **Library facet:** sort/filter by score & performance; a **"Winners"** row surfaces best assets → one-tap
  **"5 more like this winner"** (`POST /api/assets/{id}/regenerate`, master §9,§30). **Honesty note (engine FIX
  1, carried forward):** this panel only *reports* ad performance; it NEVER moves ad budget — autonomous
  ad-spend caps + kill-switch live in the ads module, not here.
- **⭐ OUT-OF-THE-BOX: A/B test surfacing** — when 2+ approved variants of a campaign go live, an "A/B" strip
  shows which angle is winning (Phase-2 §4). Read-only Phase-1; the regenerate-from-winner loop is the action.

---

## 12. S9 — ASSET LIBRARY (filterable gallery)

`<Layout title="Asset Library">`. The canonical gallery of every asset (master §28; backend `ai_assets`). Ports
**`templates/ExploreCreatorsPage`** grid + **`templates/ExploreCreatorsPage/Filters`** with the
**`Customers/CustomerList/CustomerListPage`** head row.

```
┌─ Card head ─────────────────────────────────────────────────────────────────┐
│ "Asset Library" | <Search isGray> | <Filters> | <Tabs All·Approved·Drafts·   │
│                                                   Used·Winners> | <Button blk │
│                                                   "Create"> → S1              │
├─ Filter rail (Filters) ──────────────────────────────────────────────────────┤
│ Campaign | Platform | Asset type | Status | Size | Vertical | Angle | Date    │  (master §28 facets)
├─ Grid (ExploreCreatorsPage) ─────────────────────────────────────────────────┤
│  [GridProduct cards — preview · angle badge · platform/size · status · score  │
│   · used-in chips · hover actions]  …  responsive 2/3/4-up                     │
└───────────────────────────────────────────────────────────────────────────────┘
```

- **Cards** = the same S5 `GridProduct` variant card (ONE card component) so Studio and Library look identical
  — consistency reads as premium.
- **Filters** = `components/Filters` + `Select`s (campaign / platform / type / status / best-performing / date
  / size / vertical / angle — master §28). **Search** = `components/Search`. **Tabs** = status segments.
- **Data:** **`GET /api/assets?limit&offset&campaign&platform&type&status&angle&size&date`** — newest-first,
  tenant-scoped, paginated. Card click → S6 slide-over. **Empty/loading/error** → `NoFound` / `Spinner` / one
  token banner.
- **"From this →"** action on any card → opens **S2** with that asset pre-loaded as the reference image (S10) +
  "make this kind of banner" — the reuse loop.

---

## 13. S10 — UPLOAD-REFERENCE → "MAKE THIS KIND OF BANNER"

The founder's explicit upload flow (master §38,§53; Phase-2 §3). Entry points: the **Upload reference** button
in S2, and **"From this →"** on any Library/variant card.
- **Dropzone:** `components/FieldImage` (the kit's image dropzone) inside a small `Modal` or inline under the
  command box. Accepts a reference (a competitor banner, a past creative, a product photo).
- **On upload:** a thumbnail pins above the command box with a removable `Badge`; the placeholder switches to
  "Make this kind of banner for [campaign] — Meta, premium." Generation goes through
  **`POST /api/assets/variation-from-upload`** (multipart; the reference image flows to the provider as the
  reference brief).
- **Vendor mental model:** "here's the vibe I want, make it for my campaign" — zero design jargon.
- **Guardrail surface:** if the reference trips the safety prefilter (copyright/celebrity likeness — backend
  §3.2) the response is `blocked` → a calm inline note, not an error dump (master §41 NEVER).

---

## 14. S11 — APPROVE / REGENERATE / RESIZE / USE (quick-action grammar)

Consistent action vocabulary across S5 cards, the S6 panel, and S9 library — all reference components, all
writing through the real frozen API and re-polling. **No destructive overwrite — every edit is a NEW version**
(master §41).
- **Approve / Reject** → `Button isCircle icon="check"/"close"` + status `Badge` → **`POST /api/assets/{id}/
  approve` | `/reject`** (master §27).
- **Regenerate / "5 more like this"** → `Dropdown` (same angle · new layout · new size · new CTA · new language
  · cleaner · new angle · 5-more-like-winner — master §26) → **`POST /api/assets/{id}/regenerate`**. Each spawns
  S4 GenerationLoader cards again.
- **Resize** → `Dropdown` of platform sizes (1:1 · 4:5 · 9:16 · 16:9 · Google · WA square/vertical · hero ·
  thumbnail — master §15) → an edit producing a new version. **⭐ OUT-OF-THE-BOX "Make all sizes"** (Phase-2 §4)
  = one click → a resize-set across the common platforms.
- **Use →** → destination `Dropdown`/Modal: **WhatsApp** (→W1) · **Ads** (manual launch only, FIX 1) ·
  **Workflow** (asset-gen node, master §33) · **Download** → **`POST /api/assets/{id}/attach`** (writes
  `ai_asset_usage`; approved-only).

---

## 15. W1 — WHATSAPP CAMPAIGN BUILDER UPGRADE (2 cards → premium multi-card workspace)

**Today** (`app/whatsapp/page.tsx`): exactly 2 cards (a "Sent Log" raw `<table>` + a "Send a Message" form),
still using the **deprecated `PageHeader`** (L7,96–100) and a raw-hex amber banner (L112–114). **Target**
(master §52–53; Phase-2 §2): an INTELLIGENT campaign builder, not a manual template editor — browse / preview /
search / filter Creative Studio assets, AI-generate the template from the campaign, attach a banner, preview the
real WhatsApp bubble, and send. The current 2-card page → an Apple-like multi-card layout.

**Layout — `HomePage` 2-col grammar (`col-left` ≈ 2/3 / `col-right` ≈ 1/3), title via `<Layout
title="WhatsApp">` only, PageHeader REMOVED:**

```
┌─ Layout title="WhatsApp" ───────────────────────────────────────────────────────┐
│ COL-LEFT                                            COL-RIGHT                     │
│ ┌─ Card "Compose" (AI build + attach + preview + send) ┐  ┌─ Card "Creative assets"┐│
│ │ Campaign Select → [Ask AI to write this ▸] (AI tmpl)   │  │ <Search><Filters camp ││
│ │ To (Field) | Template Select | text Editor             │  │ ·platform·status>      ││
│ │ ┌ attached banner (or "Attach ▸" / "Make a poster ▸S1")┐│  │ ┌ GridProduct grid ──┐ ││
│ │ │ [banner thumb] headline · CTA   [change]            ││  │ │ [thumb][thumb][thumb]│ ││
│ │ └──────────────────────────────────────────────────────┘│  │ │ click→preview→attach │ ││
│ │ ┌ live WhatsApp BUBBLE preview (image + text) ─────────┐ │  │ └─────────────────────┘ ││
│ │ │  [▮ banner ]  your message copy …  [Book Now]       │ │  │ "Make a poster for hot ││
│ │ └──────────────────────────────────────────────────────┘│  │  leads" → deep-link S1  ││
│ │ [Send ▸ isBlack]   audience · schedule (Phase-2 §2)     │  └────────────────────────┘│
│ └────────────────────────────────────────────────────────┘                            │
│ ┌─ Card "Sent log" (Table/TableRow + status Badge) ──────┐                            │
│ │ when · phone · template · kind · status                 │                            │
│ └──────────────────────────────────────────────────────────┘                            │
└─────────────────────────────────────────────────────────────────────────────────────────┘
```

**Card-by-card (all reference components):**
- **"Creative assets" browser (col-right)** — ports `ExploreCreatorsPage` grid + `Filters` + `Search`. Shows
  Creative-Studio assets via **`GET /api/assets?filters`** filterable by campaign/platform/status; click →
  preview popover → **"Attach to message"** → **`POST /api/assets/{id}/attach {channel:"whatsapp",template_id}`**.
  This is the browse/preview/search/filter requirement (master §52) — **no manual upload**.
- **"Compose" (col-left) — the intelligent builder (Phase-2 §2):**
  - **Campaign Select** drives everything; **"Ask AI to write this" `Button isStroke`** → AI auto-generates
    template copy / message variations / CTAs / personalization tokens from campaign data (reuse the LLM seam +
    master no-invent guardrails). For a NEW banner, a deep-link `Button` **"Make a poster for hot leads"** →
    opens **S1** with WhatsApp platform + the lead segment pre-set, then returns to attach.
  - **To** (`Field`), **Template** (`Select` of approved WA templates), **message text** (`components/Editor` /
    `Field` textarea) — "build the text template". Params via `Field`/tagsinput.
  - **Attached banner** — a preview block; "Attach" pulls the selected asset from the right rail, "Change" swaps
    it. The asset stays linked to its originating campaign for performance tracking (master §53).
  - **Live WhatsApp-bubble preview** — a token-styled chat-bubble mock (the `MessagesPage` bubble pattern)
    showing exactly how image+text lands. Premium, reassuring.
  - **Send** — `Button isBlack` → existing `sendWhatsApp` (`lib/api`); keep the current not-configured banner
    (creds dormant) but as a **token banner**, not the raw-hex one at L112–114.
- **"Sent log" (col-left bottom)** — port the existing log to `components/Table`/`TableRow` + `Badge` status
  (kill the raw `<table>`/`.data-table`).

**Concrete deltas vs today:** remove `PageHeader` import + usage; replace the 2-card flat layout with the 2-col
multi-card grammar; ADD the asset browser + attach + AI-template + live-bubble preview; convert raw `<table>` →
`Table`/`TableRow`; replace the raw-hex amber banner with `primary-05`/`b-surface` tokens. Net: a real
creative-aware messaging console. (Phase-2 §2 full flow — Campaign → AI template → creative → preview → audience
→ schedule → send → analytics → reuse winners — phases beyond send are dormant-safe stubs surfaced where they fit.)

---

## 16. DATA WIRING — every surface → the REAL frozen API (backend §8)

| Surface | Frozen route (base `/api/assets/*`) | Returns / note |
|---|---|---|
| Dormancy probe (every screen guard) | `GET /api/assets/status` | `{enabled, schema_ready, providers, wallet, hatchet}` — UN-gated; drives the dormant state |
| Model selector (S2 Advanced) | `GET /api/assets/providers` | model registry (id, display, capabilities, cost) — "Auto" default |
| Generate (S2) | `POST /api/assets/generate` | `{job_id, state, est_cost}`; `over_budget`→402, `needs_input`→clarify list; idempotent |
| Queue list (S4 / a "Jobs" view) | `GET /api/assets/jobs` | jobs by state |
| Live queue stream (S4) | `GET /api/assets/jobs/{id}/stream` (**SSE**) | per-variant render events + progress (the loader) |
| Queue poll fallback (S4) | `GET /api/assets/jobs/{id}` | one-shot job status + progress |
| Cancel a running job | `POST /api/assets/jobs/{id}/cancel` | releases the wallet hold |
| Library list/filter (S9, W1 browser) | `GET /api/assets?limit&offset&filters` | newest-first, tenant-scoped |
| Asset detail (S6) | `GET /api/assets/{id}` | current version + all versions + score + status + usage + metrics |
| Asset bytes (S5/S6/W1 previews) | `GET /api/assets/{id}/raw` | image bytes; `local_path` never exposed |
| NL edit (S6) | `POST /api/assets/{id}/edit` | NEW version (original kept) |
| Regenerate / "5 more" / resize (S5/S6/S11) | `POST /api/assets/{id}/regenerate` | new versions/assets |
| Approve / Reject (S6/S11) | `POST /api/assets/{id}/approve` · `/reject` | status flip; reject teaches brand-memory |
| Use → / attach (S11, W1) | `POST /api/assets/{id}/attach` | whatsapp \| meta_ads \| workflow → `ai_asset_usage` |
| Upload-reference gen (S10) | `POST /api/assets/variation-from-upload` | multipart; reference image → provider |
| Brand Kit CRUD (S7, S3 chips) | `GET/POST/PUT /api/assets/brand-kits` | logo/palette/tone/cta/language/do-not-use |
| WhatsApp send (W1) | `sendWhatsApp` (existing `lib/api`) | keeps the current dormant-banner behaviour |

**Auth/isolation (the platform's #1 rule):** tenant is **token-derived, NEVER read from the body**; by-id
routes are RLS-scoped (forge → 404, no field leak); spend/destructive routes pass the firewall step-up. **The UI
never sees a provider key.** Every screen MUST handle the 503 dormant gate gracefully (calm banner via `/status`).

---

## 17. CROSS-CUTTING ACCEPTANCE BAR (every screen must pass — principles §7)

- [ ] Each screen wrapped in `Layout` with ONE `title`; **no PageHeader, no eyebrow, no subtitle.**
- [ ] Every section is a `components/Card` (`text-h6` title, `pt-3` body); no bare custom panels.
- [ ] Two-column rhythm (`col-left`/`col-right`) on S1 & W1; reference grids on S5/S9; stacks on mobile.
- [ ] **Reference components ONLY** — `Card`, `Tabs`, `Select`, `Field`, `Button`, `GridProduct`, `Filters`,
      `Search`, `Modal`, `Table`, `TableRow`, `Badge`, `NoFound`, `Spinner`, `CardChartPie`, `Percentage`,
      `FieldImage`, `Editor`, `Dropdown`, `PopularProducts`, `LikeButton`. **The ONLY new components are the two
      loaders — `GenerationLoader` + `CreativeSkeleton` (§9 / `design/cs-loading-component.md`), token-built.**
- [ ] **Zero raw hex** — `@theme` tokens only (`primary-01` brand blue; status `primary-02/03/05`; surfaces
      `b-surface1/2`; text `t-primary/secondary/tertiary`). Brand = ONE decisive blue; ≤2 saturated colours.
- [ ] **Inter Display** app-wide; type ramp tokens only; nothing bigger than `text-h4` in content; no stacked
      headings.
- [ ] Real loading (`Spinner` + the §9 GenerationLoader) / empty (`NoFound`) / error (one token banner) on every
      data surface; **the dormant `/status` gate is honoured everywhere** (no raw "undefined", no blank flashes).
- [ ] Plain language — "Create / Library / Brand Kit / Approve / Use"; **no jargon** (`job_id`, `variant_id`,
      `provider`, `BatchSpec` stay in tooltips/advanced, never in the vendor's face).
- [ ] Progressive disclosure: model / count / sizes / language under "Advanced"; default "Auto".
- [ ] Vendor-simple: **campaign + one instruction + Generate** is the whole happy path.

---

## 18. BUILD ORDER (the later frontend wave — small verifiable units; runs AFTER the UI-overhaul lane clears)

1. `app/creative/` route group + nav entry; `<Layout>` shells for S1/S9/S7 (empty `NoFound` states + the
   `/status` dormant guard first) → renders, nav active state correct, byte-identical when dormant.
2. **`components/GenerationLoader`** + **`components/CreativeSkeleton`** (§9 / `design/cs-loading-component.md`)
   + `globals.css` keyframes + the canvas `field.ts` → the dot-matrix hero AND the per-card skeleton in
   isolation → 60 fps, reduced-motion CSS fallback, dark mode, hero-collapse → skeleton-grid compose.
3. S2 Create hero (selectors + command box + Generate → `POST /api/assets/generate`; Advanced disclosure).
4. S3 Campaign Context (reads the job `campaign_ctx` + brand chips from `/brand-kits`; provenance dots).
5. S4 SSE queue (`/jobs/{id}/stream`) + S5 variant grid (loader → variant morph in place).
6. S6 Asset Detail slide-over + NL edit (`/edit` new-version flow) + status control + version strip.
7. S9 Library (grid + Filters + Search) against `GET /api/assets`.
8. S7 Brand Kit (SettingsPage port). S8 Performance tab (honest empty until the ads loop reports).
9. S10 upload-reference (`/variation-from-upload`). S11 Use → destination picker (`/attach`).
10. **W1 WhatsApp Campaign Builder** (remove PageHeader, 2-col multi-card, asset browser + attach + AI-template
    + live-bubble preview, Table port).
11. Run the §17 acceptance bar per page → green; verify the dormant `/status` path on every screen.

Each unit reuses a NAMED reference template/component; nothing is hand-built except `GenerationLoader`.

---

## 19. ⭐ OUT-OF-THE-BOX ADDITIONS (Phase-2 §4 — FULL catalogue = `design/cs-out-of-box-features.md`)

The founder explicitly invited proactive high-value additions. The prioritized, architecture-fit catalogue
lives in the companion doc **`design/cs-out-of-box-features.md`**; the ones with a UI home in THIS workspace are
placed here (all dormant-safe, surfaced where they fit, honouring the no-invent + approval guardrails):

1. **The loaders as a platform primitive** (P0 — already core, §9) — reused across image/banner/ad/brochure-
   cover/video-thumbnail; the single premium-feel signature.
2. **Brand-kit auto-extraction** (P1, S7) — seed palette/logo/tone from a website URL or uploaded asset.
3. **"Make all sizes" one-click** (P1, S11) — a resize-set across common platforms from one approved variant.
4. **A/B creative testing surfaced in-UI** (P1, S8) — show which angle is winning once variants go live.
5. **Asset version timeline** (P1, S6) — the version strip becomes a lineage timeline (`parent_version_id`).
6. **Campaign-performance → auto-regenerate-winners** (P2) — "5 more like this winner" biased by metrics.
7. **AI copy + image co-generation** (P2, S2) — headline/CTA + visual proposed together.
8. **Template/creative reuse marketplace** (P3, W1) — clone/optimize/repurpose winning template+banner combos.

See `design/cs-out-of-box-features.md` for the complete list + prioritization rationale (do not re-derive here).

---

## 20. SOURCES / GROUND TRUTH

- Master + Phase-2 specs: `CREATIVE_STUDIO_MASTER_PROMPT.md`, `CREATIVE_STUDIO_PHASE2_SPEC.md`.
- Real frozen backend API + schema + pipeline: `design/asset-service-backend.md` §2,§3,§4,§6,§8,§9,§10;
  built-state truth `memory/brain/creative-studio.md` (A1/A2/A3 — base `/api/assets/*`, 18 frozen routes).
- Predecessor UI doc this refines: `design/creative-studio-ui.md` (S1–S11 + W1; `/creatives/*`→`/api/assets/*`).
- Companion design docs (authoritative on their topic — do NOT re-derive): `design/cs-loading-component.md`
  (the GenerationLoader + CreativeSkeleton full spec — canvas `field.ts`, props, build order) and
  `design/cs-out-of-box-features.md` (the full Phase-2 §4 out-of-the-box catalogue + prioritization).
- UI rules / reuse / acceptance: `design/ui-design-principles.md` (10 rules + §7 checklist).
- Reference kit verified on disk: `core-2-dashboard-builder-react/components/{Card,Tabs,Select,Field,Button,
  GridProduct,Filters,Search,Modal,Table,TableRow,Badge,NoFound,Spinner,CardChartPie,Percentage,FieldImage,
  Editor,Dropdown,PopularProducts,LikeButton,Layout,Header,Sidebar}` + `templates/{HomePage,ExploreCreatorsPage,
  MessagesPage,SettingsPage,Customers/CustomerList/DetailsPage,Customers/CustomerList/CustomerListPage,
  Products/DraftsPage/Grid,Products/NewProductPage,Products/OverviewPage}` (Modal `isSlidePanel`, Card
  `headContent`, Button `isBlack/isStroke/isCircle` all confirmed present).
- Current WhatsApp page to upgrade: `famit-panel/app/whatsapp/page.tsx` (2 cards + deprecated PageHeader
  L7,96–100; raw `<table>` L125; raw-hex banner L112–114).
