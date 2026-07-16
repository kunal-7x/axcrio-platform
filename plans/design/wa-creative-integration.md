# DESIGN SPEC — **WhatsApp Campaign Builder ⇄ Creative Studio** DEEP INTEGRATION

> **Status:** EXECUTION-READY UI + SEAM DESIGN (READ-ONLY wave — this doc writes NO app code, edits no
> `caller.py`/`agent.py`/`whatsapp.py`, does NO git, does NO deploy). It specifies the **deep, no-manual-
> upload integration** between the WhatsApp Campaign Builder (the WhatsApp module page) and the AI Asset
> Service (Creative Studio): **launch Creative Studio directly from a WhatsApp banner step → generate/edit
> an asset → it auto-stores in the Asset Library → it is IMMEDIATELY browseable/searchable/compare-able/
> attachable in the WhatsApp template builder WITHOUT manual upload → the attached image becomes the
> WhatsApp template HEADER MEDIA (Meta media upload + template).** Every asset stays linked to its campaign.
>
> **Date:** 2026-06-11. WhatsApp is **LIVE end-to-end** (real send proven; webhook connected;
> `WHATSAPP_GOLIVE.md`). OpenRouter image-gen key proven (real PNG). DO Spaces creds proven (PUT/GET/DELETE).
>
> **Parents (cite, do not relitigate or duplicate):**
> `CREATIVE_STUDIO_MASTER_PROMPT.md` (42-section DNA + architecture decision),
> `CREATIVE_STUDIO_PHASE2_SPEC.md` §2 (the WhatsApp Campaign Builder + §1 the premium AI-gen LOADING UI),
> `design/creative-studio-integrations.md` §1 (the `creative.*` contract), §2 (the WhatsApp seam at the
> architecture level), §6 (the library as the cross-plane store).
> **Siblings this doc binds to (own the mechanics — cite, do not re-spec):**
> `design/creative-whatsapp-creative.md` (the WhatsApp transport/`media_upload.py`/template send shapes),
> `design/creative-asset-library.md` (the canonical `AssetRef` + `creative.search` facets + DO Spaces),
> `design/creative-studio-ui.md` / `creative-image-banner-studio.md` (the Creative Studio workspace + §1 loader),
> `design/platform-workflow-studio.md` (the Action-node "banner step" in a flow).
>
> **What THIS doc uniquely owns (the gap the parents leave):** the **front-end seam** — the exact
> launch-from-builder UX, the in-builder asset PICKER (browse/preview/search/filter), the **version-compare
> UI**, the one-click ATTACH flow, and the precise **attached-image → Meta media-upload → template-header**
> mechanics. The integrations doc owns the *architecture* of the seam; this doc owns the *flow + UI + API
> calls* a build agent implements.

---

## 0. THE ONE-PARAGRAPH MODEL (read first)

The WhatsApp Campaign Builder never asks the founder to find, download, or upload a file. When a template
needs a banner, the **Banner step** of the builder offers two doors to the **same** Asset Library: **"Pick
from Library"** (browse/search/filter/preview/compare-versions the assets already generated for this
campaign) and **"Create New"** (launch Creative Studio **in-context, as a drawer/modal over the builder**,
pre-seeded with this campaign + `kind=wa_poster`). Either door ends the same way: a chosen `AssetRef`
(tenant-scoped, `status=approved`, linked to `campaign_id`) is **ATTACHED** to the template's header slot.
Attach does NOT copy bytes into the builder — it stores the `asset_id` on the draft template. At **send/
submit** time the WhatsApp plane resolves that `asset_id` → uploads the bytes to Meta **once**
(`POST /{phone_id}/media` → `media_id`, cached by `(phone_number_id, file_sha)`) → builds the **template
with an IMAGE header component** carrying that `media_id` → submits for Meta approval / sends. Because the
asset carries `campaign_id`+`batch_id`+`variant_id`, every delivery/read/click/booking signal flows back to
the **exact poster** via `creative.update_metrics`, and that performance becomes a generation input next
round. Two surfaces only (the `creative.*` contract + the Asset Library); no second money-path, no manual
upload, no per-plane asset store. Everything is **dormant-safe**: no OpenRouter key → "Create New" shows
the coming-soon/activation panel; no Meta template → attach still works and the send parks at `pending_template`.

---

## 1. WHERE THIS LIVES — THE WHATSAPP CAMPAIGN BUILDER (UI placement)

The current WhatsApp page is **2 cards**; per the founder it becomes an **Apple-like multi-card campaign
WORKSPACE** (`CREATIVE_STUDIO_PHASE2_SPEC.md` §2). **Reuse design-system COMPONENTS, intentional layout**
(`ui-reuse-core2-never-from-scratch.md`). The builder is a **single page, stepped** (mirrors the
Run-Campaign "one screen, 3 Tabs" pattern the port map prescribes) — NOT a wizard with page reloads:

```
WhatsApp Campaign Builder  (app/whatsapp/page.tsx — Layout title "WhatsApp", NO PageHeader subtitle)
 ┌ Tab: Campaign ───────────────────────────────────────────────────────────────┐
 │ • Campaign selector (Select)  → AI reads objective/audience/offer/product/brand│
 │ • AI-generated template suggestions (card grid) + message variations + CTAs    │
 └────────────────────────────────────────────────────────────────────────────────┘
 ┌ Tab: Creative (THE BANNER STEP — this doc's core) ─────────────────────────────┐
 │ • Header-media slot card:  [ Pick from Library ]   [ Create New ▸ Creative Studio ]│
 │ • Attached preview (or empty state)  • "Compare versions" • "Change" • "Remove" │
 └────────────────────────────────────────────────────────────────────────────────┘
 ┌ Tab: Template ─────────────────────────────────────────────────────────────────┐
 │ • Live WhatsApp phone-mockup PREVIEW (header media + body + buttons)            │
 │ • Body text + personalization tokens + CTA-URL button  • Template category      │
 └────────────────────────────────────────────────────────────────────────────────┘
 ┌ Tab: Audience + Send ──────────────────────────────────────────────────────────┐
 │ • Audience selection (hot/warm/cold segments)  • Schedule  • Submit/Send        │
 │ • Two gates surfaced: asset-approved? + template-approved-by-Meta?              │
 └────────────────────────────────────────────────────────────────────────────────┘
```

**Reference-kit composition (port, don't invent):**
- Page shell: `components/Layout` (single `title="WhatsApp"`), `components/Tabs`, `components/Card`,
  `components/Button` (`isWhite|isStroke|isBlack`).
- Asset picker: `components/Modal` (or a right `Drawer` composed from Card), `components/Search`,
  `components/Filters`/`Select` for facets, `components/GridProduct` cards for the asset thumbnails
  (the `Products/DraftsPage` card-grid archetype), `components/Image`, `components/Checkbox` for
  multi-select-to-compare.
- Banner step / Creative Studio launch: a full-height **drawer** (Modal variant) so the builder stays
  mounted behind it — the founder never loses their campaign context.
- Live preview: a small bespoke phone-mockup card (the one genuinely new lockup) reusing `Card` + `Image`.

---

## 2. THE TWO DOORS — DETAILED UX

### 2.1 Door A — "Create New" (launch Creative Studio FROM the WhatsApp builder)

Clicking **Create New** opens Creative Studio **as a drawer over the builder**, NOT a route change — so
the campaign/template draft stays alive behind it. The drawer is the full Creative Studio workspace
(`creative-studio-ui.md`) but **pre-seeded and scoped** by the builder's context:

- **Pre-seed payload** (the builder passes this into the drawer): `{campaign_id, kind:"wa_poster",
  platform:"whatsapp", segment:<hot|warm|cold from the audience tab if chosen>, language, brand}`. The
  master DNA then infers product/price/audience/CTA/style from the campaign — **the founder doesn't re-spec**.
- **Generate:** the drawer calls `POST /creative/generate` (the §1 contract); it returns
  `{job_id, batch_id, estimate_minor}`. The **premium AI-gen LOADING UI** (`PHASE2_SPEC.md` §1 — the
  charcoal card + animated dot-matrix field, cycling "Understanding campaign → Designing visual direction →
  Composing layout → Rendering creative → Finalizing output") fills the drawer while the Hatchet job runs.
  No fake percentage; `prefers-reduced-motion` degrades to a calm static state.
- **Edit / regenerate (in-drawer):** NL edits ("make it premium", "remove price", "Hinglish", "story size")
  → `POST /creative/assets/{id}/edit` → a **NEW VERSION** (original kept — master §41 never overwrite).
  "5 more like this" → `POST /creative/assets/{id}/regenerate`.
- **Approve:** `POST /creative/assets/{id}/approve` flips `draft→approved` (the gate that lets the asset
  leave the studio). The drawer shows the approve action prominently because **only approved assets are
  attachable** (§5.2).
- **Auto-store:** generation already wrote the `AssetRef` to the Asset Library (the service's job — library
  `put()`), tagged `campaign_id`/`batch_id`/`variant_id`/`kind=wa_poster`/`platform=whatsapp`. **There is no
  separate "save" step** — the asset exists in the library the instant the job completes.
- **Use-this:** a **"Use in this template"** button on the chosen asset closes the drawer and ATTACHES it
  (§5) — the founder lands back on the Creative tab with the header slot now filled. (If the asset is still
  `draft`, "Use" first prompts approve, or attaches as a *pending* attach that blocks submit until approved.)

> **Dormant-safe:** no OpenRouter/provider key → `creative.generate` returns `{"status":"not_configured"}`;
> the drawer renders the calm Creative-Studio activation panel ("Creative engine not yet configured") and
> the founder can still use **Door A's fallback = Door B** (pick an already-made asset, or an uploaded one).

### 2.2 Door B — "Pick from Library" (browse/preview/search/filter/compare WITHOUT upload)

Clicking **Pick from Library** opens the **in-builder asset PICKER** (a Modal/Drawer) reading the **same**
Asset Library via one call: `GET /creative/assets` (= `creative.search`, the library's canonical endpoint).

**Default scope (the founder sees the RIGHT assets first, zero effort):**
`creative.search({ campaign_id:<current>, platform:"whatsapp", kind:["wa_poster","banner"],
status:"approved", sort:"top_ctr" })` — the campaign's approved WhatsApp-shaped assets, best-performers first.

**Picker UI (reference-kit card grid):**
- **Search bar** (`components/Search`) → free-text over `title`/`tags`/`text_snippet`.
- **Filter row** (`components/Filters`/`Select`): **Campaign** (default current, can widen to "all my
  campaigns"), **Kind** (wa_poster/banner/offer_image), **Status** (approved default; show draft toggle),
  **Angle** (price/urgency/trust/…), **Format** (png/jpg), **Performance** (sort: top_ctr / top_roi /
  newest). Facet values come from `GET /creative/assets/facets`.
- **Asset cards** (`GridProduct` archetype): thumbnail (`thumb_url`), title, angle badge, status pill
  (draft/approved/winner), a tiny metrics strip (CTR / delivered / clicks when present), and a **version
  count badge** ("v3") when the asset has an edit lineage.
- **Per-card actions:** **Preview** (opens the Asset Detail panel — full image + headline/CTA/angle/score/
  campaign/version history), **Compare** (checkbox → adds to the compare tray, §3), **Attach** (the
  one-click attach, §5).
- **Empty state** (`components/NoFound`): "No banners yet for this campaign — Create one" → routes to Door A.
- **Founder-uploaded assets are first-class here too** (the library's `ingest_upload` source) — so a logo
  or a hand-made poster the founder uploaded shows in the SAME picker, no separate upload step inside the
  builder. (The picker is the only "upload" surface, via the library's `POST /creative/assets/upload`; the
  builder itself never takes a raw file.)

---

## 3. THE VERSION-COMPARE UI (this doc owns the spec)

Because `creative.edit`/`regenerate` create **new versions, never overwrites** (library §2 / master §41),
an asset is really a **lineage**: `v1 → v2 (edit "remove price") → v3 (regenerate "more premium")`. The
founder must be able to **compare versions side-by-side and pick the one to attach**.

### 3.1 Version lineage data (no new store — derived from existing `AssetRef` fields)
Each edit/regenerate sets, on the new `AssetRef.meta`, a `parent_asset_id` and a `root_asset_id` (the
lineage head) + a `version` integer and an `edit_label` (the NL instruction, e.g. "remove price"). The
library already keeps every version as its own `AssetRef`; the lineage is reconstructed by
`creative.search({ root_asset_id:<root> })` (a `meta` facet filter) ordered by `version`. **No new
endpoint needed** — it is a scoped search. (Build note: add `root_asset_id`/`parent_asset_id`/`version`/
`edit_label` to the `meta` block the service writes on edit/regenerate; the library's additive-schema rule
allows this with zero migration.)

### 3.2 Compare UI (two modes — reuse-first)
- **A) Side-by-side compare (the primary, for picking the winner):** the **Compare tray** at the bottom of
  the picker collects 2–4 selected versions (or even unrelated candidates). **Compare** opens a modal with
  the images **in a row**, each with its **version label + edit_label + angle + status + key metrics**
  (CTR/delivered/clicks/score) beneath. A single **"Attach this"** button per column. A **diff strip**
  shows what changed between adjacent versions (the `edit_label`: "remove price", "Hinglish", "story size")
  so the founder sees *why* v3 differs from v2 without eyeballing pixels.
- **B) Version timeline (on the Asset Detail panel):** a horizontal **timeline rail** of thumbnails
  (v1…vN) with the edit_label under each; clicking a node previews that version; a **"Restore/attach this
  version"** action attaches the selected version (older versions stay valid `AssetRef`s — restore =
  attach an older one, it never deletes newer ones). This is the founder-asked **"asset version timeline"**
  (PHASE2_SPEC §4 out-of-the-box list).

### 3.3 Reuse + a11y
- Compose from `components/Modal`, `components/Image`, `components/Card`, `components/Percentage`/metrics
  chips, `components/Checkbox` (multi-select), `components/Tabs` (Side-by-side | Timeline). **No bespoke
  carousel lib** — a flex row of equal cards.
- Performance metrics shown are read straight off `AssetRef.metrics`; when an asset has never run, show
  "Not yet tested" (honest — never invent a CTR), matching the integrations-doc "learning biases, never
  fabricates" honesty bar.

---

## 4. THE API CALLS (WhatsApp builder ⇄ AI Asset Service :8310 ⇄ Asset Library)

All routes are the **§1 `creative.*` contract** (`creative-studio-integrations.md`) — the builder adds **no
new backend surface**; it consumes the already-designed endpoints. **The frontend talks to the panel's
`/api/...` proxy** (nginx strips `/api` → backend), which fronts both the monolith and the dedicated AI
Asset Service on `:8310` (localhost loopback, scoped tenant token; tenant from TOKEN never body — §8).

| Builder action | HTTP call (via panel `/api`) | Service | Returns |
|---|---|---|---|
| Open picker (default scope) | `GET /creative/assets?campaign_id&platform=whatsapp&kind=wa_poster,banner&status=approved&sort=top_ctr` | Asset Library | `SearchPage{items:[AssetRef], total}` |
| Search / filter in picker | `GET /creative/assets?...&text=&angle=&format=&sort=` | Asset Library | `SearchPage` |
| Filter dropdown values | `GET /creative/assets/facets` | Asset Library | `{campaigns[],kinds[],platforms[],angles[]}` |
| Preview one asset | `GET /creative/assets/{id}` | Asset Library | `AssetRef` |
| Version lineage (compare) | `GET /creative/assets?root_asset_id={root}&sort=version` | Asset Library | `SearchPage` (all versions) |
| Image bytes for thumbnail/preview | `GET /creative/assets/{id}/raw` (local-serve) **or** 302→Spaces/CDN `url` | Asset Library | image bytes |
| **Create New** → generate | `POST /creative/generate {campaign_id,kind:"wa_poster",platform:"whatsapp",n,segment,language}` | AI Asset Service :8310 | `{job_id,batch_id,estimate_minor}` |
| Poll generation | `GET /creative/jobs/{job_id}` | AI Asset Service | `{status,assets:[AssetRef]}` |
| NL edit (new version) | `POST /creative/assets/{id}/edit {instruction}` | AI Asset Service | `{job_id}` → new `AssetRef` |
| Regenerate ("5 more") | `POST /creative/assets/{id}/regenerate {n,mode}` | AI Asset Service | `{job_id,batch_id}` |
| Approve (unlock attach) | `POST /creative/assets/{id}/approve` | AI Asset Service | `AssetRef{status:"approved"}` |
| **Attach** to template | *(builder-local — stores `asset_id` on the draft; see §5)* | panel/WA module | draft updated |
| Upload (founder file) | `POST /creative/assets/upload` (multipart) | Asset Library | `AssetRef` |
| Submit/send (resolve→Meta) | `POST /whatsapp-creatives/send` *or* the WA template-submit route (§6) | WhatsApp plane | `{status,media_id?,template?,message_ids?}` |
| Performance writeback | `POST /creative/assets/{id}/metrics` (from WA status webhook) | Asset Library | `AssetRef` |

**Credit gate (generation only):** `creative.generate/edit/regenerate` are `spend`-class — the service does
`wallet.reserve → (Hatchet job) → settle/release` (F4, INR paise, idempotent), surfacing the master §35
"Generating N banners ≈ X credits. Continue?" confirm in the drawer **before** the job starts. **Attach and
send carry NO generation charge** (the WhatsApp send has its own per-message meter, §6 / `whatsapp-creative`
spec §6) — never double-charged.

---

## 5. THE ATTACH FLOW (the heart of "no manual upload") — step by step

**Attach = bind an `asset_id` to the draft template's header slot. It moves NO bytes at attach time.** Byte
resolution + Meta upload happens lazily at **submit/send** (§6), so attaching is instant and reversible.

```
ATTACH FLOW
───────────
1. Founder picks an asset (Door A "Use in this template" OR Door B card "Attach"/compare "Attach this").
2. Pre-attach gate (builder-side):
     • assert AssetRef.tenant_id == token tenant           (ownership — server re-checks too, §8)
     • assert AssetRef.status ∈ {approved, winner}         (only approved assets leave the studio, §5.2)
         └─ if status=="draft": offer "Approve & attach" → POST /creative/assets/{id}/approve, then continue
     • assert kind ∈ {wa_poster, banner, offer_image, image} and format ∈ {png,jpg,jpeg}
         └─ WhatsApp header media must be an image; reject pdf/video here with a clear message
            (a brochure/video attaches as a DOCUMENT/VIDEO body part, not the header — out of this slot's scope)
3. Bind on the draft template (builder local state + persisted on the WA draft record):
     template.header = { type:"image",
                         source:"asset",
                         asset_id:<id>,
                         campaign_id, batch_id, variant_id,   ← carried so performance links back
                         version, root_asset_id,              ← which version is attached
                         preview_url:<AssetRef.url> }         ← for the live preview only (not the send payload)
4. UI updates instantly:
     • Creative tab header slot shows the attached preview + "Compare versions" + "Change" + "Remove".
     • Template tab phone-mockup re-renders with the image header.
5. Attach is logged: audit channel="creative", action="creative.attach_to_whatsapp",
     object_id=asset_id, meta={campaign_id, template_draft_id, variant_id}.   (no money, safe class)
6. Reversible: "Remove" clears template.header; "Change" reopens the picker; "Compare versions" opens §3
     pre-loaded with this asset's lineage so the founder can swap to another version in one click.
```

### 5.1 Why store `asset_id`, not bytes (the design rule)
Storing the `asset_id` (not a copied file or a frozen URL) means: (a) **no manual upload** ever — the
library owns the bytes; (b) the attached header **stays linked to its campaign/variant** for performance
attribution (master §29); (c) choosing a different **version** is just swapping the `asset_id`/`version`;
(d) the **same asset is reusable** across many templates/campaigns with one upload-once `media_id` cache
(§6.3); (e) the live preview uses `AssetRef.url`, but the **send** re-resolves bytes fresh, so a re-rendered
or re-hosted asset is always current.

### 5.2 The two gates (composed, in order — never bypassed)
1. **Asset-approval gate (Creative Studio's):** attach is refused for non-approved assets. `creative.approve`
   is the irreversible "this may now spend money / face platform review downstream" gate
   (integrations §1.1 — classed `destructive`).
2. **WhatsApp send-approval gate (the WA plane's):** independent — `WA_CREATIVE_REQUIRE_APPROVAL` +
   suppression + rate caps + per-message metering (whatsapp-creative §6) fire at **send**, plus **Meta's own
   template approval** (§6.4). The builder **surfaces both** as status chips on the Audience+Send tab:
   `Asset: approved ✓` and `Template: pending Meta approval ⧖`. The Asset Service never re-implements WA's
   gates; it just refuses to surface/attach an unapproved asset.

---

## 6. ATTACHED IMAGE → WHATSAPP TEMPLATE HEADER MEDIA (Meta upload + template) — the mechanics

This is the **last mile**: how the bound `asset_id` becomes a real WhatsApp message header. **Owner of the
transport:** `creative-whatsapp-creative.md` (`media_upload.py`, `transports/meta.py`, the template send
shapes). This doc states the **end-to-end resolution** the builder triggers.

### 6.1 Two Meta paths — and why a TEMPLATE (not a free-form image) is the default for campaigns
WhatsApp business-initiated campaign sends to a list are **cold** (no open 24h session) → Meta **requires an
approved TEMPLATE** to open the conversation (`WHATSAPP_GOLIVE.md` confirmed: only `hello_world` is approved
today; production needs a **real approved template**). A template can carry an **IMAGE HEADER component**.
The free-form image message (`type:"image"`) only works to a contact with an **open session** (someone who
messaged the number) — that path exists (for replies/“open session” sends) but is **not** the campaign path.
So the builder's primary output is a **media-header TEMPLATE**.

### 6.2 The resolve-and-build sequence (at Submit/Send)
```
ON SUBMIT (Audience+Send tab):
1. Resolve bytes:  GET /creative/assets/{asset_id}/raw  (or 302→Spaces/CDN url) → image bytes + mime.
       └─ re-assert tenant ownership on the by-id route (§8).
2. Upload to Meta ONCE (the media_upload.py seam):
       POST https://graph.facebook.com/v21.0/{phone_number_id}/media
            (multipart: messaging_product=whatsapp, file=<bytes>, type=image/png)
       → { "id": "<media_id>" }            (Meta stores media 90 days)
       └─ CACHE by (phone_number_id, file_sha256) so re-sends / re-uses of the SAME asset DON'T re-upload.
3a. CREATE the template (one-time per template design — Meta approval is async, hours):
       POST https://graph.facebook.com/v21.0/{waba_id}/message_templates
       {
         "name":"campaign_<slug>", "language":"en", "category":"MARKETING"|"UTILITY",
         "components":[
           { "type":"HEADER", "format":"IMAGE",
             "example": { "header_handle":[ "<resumable-upload-handle>" ] } },   ← see 6.2-note
           { "type":"BODY", "text":"<body with {{1}} tokens>",
             "example":{"body_text":[[ ... ]]} },
           { "type":"BUTTONS", "buttons":[ {"type":"URL","text":"Book now","url":"<booking_url>"} ] }
         ]
       }
       → template enters Meta review → status PENDING → APPROVED/REJECTED (webhook or poll).
3b. SEND using the approved template (per recipient, at delivery time):
       POST https://graph.facebook.com/v21.0/{phone_number_id}/messages
       {
         "messaging_product":"whatsapp", "to":"<E164>", "type":"template",
         "template":{
           "name":"campaign_<slug>", "language":{"code":"en"},
           "components":[
             { "type":"header", "parameters":[ {"type":"image","image":{"id":"<media_id>"}} ] },
             { "type":"body",   "parameters":[ {"type":"text","text":"<personalized>"} ] }
           ]
         }
       }
       → 200 + { "messages":[{ "id":"wamid...." }] }     (the proven live shape, WHATSAPP_GOLIVE TEST 1)
4. Meter + audit + writeback wiring: per-message category meter (service/marketing/utility), audit
   channel=whatsapp, and tag the send with the asset's campaign_id/batch_id/variant_id (§7).
```

> **6.2-note (the one subtlety a build agent MUST get right):** Meta's **template CREATION** validates the
> header image via a **resumable upload `header_handle`** (the Graph **Resumable Upload API** —
> `/{app_id}/uploads` → returns a file handle), which is **separate** from the **per-message** `media_id`
> from `/{phone_id}/media`. So an IMAGE-header template uses **two** media references: a `header_handle`
> (sample image, at template-create time) and a `media_id` (the actual image, at each send). The builder's
> resolve step produces both from the SAME asset bytes: the handle once at template-create, the `media_id`
> (cached) at send. (Verify the exact handle field against current Graph docs at wire-time — Meta versions
> this; the design is correct regardless of the field name.)

### 6.3 Upload-once cache (cost + latency)
The `media_id` (and the template `header_handle`) are cached keyed by `(phone_number_id, file_sha256)` per
the WhatsApp-creative spec — so attaching the SAME asset to many recipients (a blast) or reusing it across
templates uploads **once**. `media_id` is scoped to the sending `phone_number_id`, so the key includes it
(safe under future multi-number multi-tenant).

### 6.4 Honest gates the builder must surface (no overclaim)
- **Meta template approval is Meta's gate** — the builder can CREATE+submit a template but cannot conjure an
  APPROVED one. Until APPROVED, the campaign **parks** at `pending_template`; the Audience+Send tab shows
  `Template: pending Meta approval ⧖` and disables "Send to list" (it may still send to **open-session**
  contacts via the free-form image path, §6.1). This is the `WHATSAPP_GOLIVE` reality, stated plainly.
- **Category honesty:** MARKETING ≈ ₹0.86 vs UTILITY ≈ ₹0.11–0.145 (India 2026); the category must reflect
  genuine message intent (mis-categorizing to dodge cost is itself a Meta violation — whatsapp-creative §B4).
  The builder defaults a promotional banner template to MARKETING and flags the cost in the send confirm.
- **Box `.env` token note:** `WHATSAPP_GOLIVE.md` records the live box still holds the OLD token — the
  in-app send path needs the new `EAA…` token + `FEATURE_WHATSAPP` + a real approved template before
  production list-sends work. This is an orchestrator/founder wiring task, not a builder-UI task.

---

## 7. THE ASSET STAYS LINKED TO ITS CAMPAIGN (performance attribution loop)

Every attach binds `campaign_id`+`batch_id`+`variant_id` onto the template header (§5 step 3); every send
carries them (the WA spec already tags sends this way). When delivery/read/click/booking signals return on
the **existing** `caller.py /whatsapp/inbound` status webhook, the WhatsApp plane calls
`creative.update_metrics(asset_id, {delivered, read, clicks, bookings, synced_at})` → the **library record
of the exact poster** accumulates its WhatsApp performance. Then:
- The picker's default `sort:"top_ctr"` surfaces the best poster first next time.
- The compare UI (§3) shows real CTR/delivered/clicks per version, so the founder picks the proven version.
- The service's stage-1 prompt-builder reads `library.performance_summary(tenant, industry, campaign)` so
  the next `creative.generate` over-weights the winning angle — **biases style, never fabricates a fact**
  (integrations §7). This is the founder's **"learn which combinations yield the highest engagement → surface
  winning templates"** (PHASE2_SPEC §2 learning loop) realized as a deterministic feedback read, not magic.

---

## 8. THE WORKFLOW "BANNER STEP" (launch Creative Studio from an automated flow, not just the UI)

The founder asked to "launch Creative Studio DIRECTLY from the WhatsApp **workflow** (a banner step)". Two
faces of the same seam:
- **Interactive (the builder UI):** §2 Door A — a human launches the drawer.
- **Automated (the Workflow Studio):** the `creative.*` tools are registered `ToolSpec`s, so a **banner step
  is an Action node** wrapping `creative.generate(kind="wa_poster", campaign_id)` — no new node type
  (`platform-workflow-studio.md` §6.4 / integrations §5). The live workflow builder
  (`app/workflows/_lib.ts`) already has an **`action`** node and the Budget/Approval guard nodes. The
  founder's **Flow B** ships as a template:
  ```
  Trigger(lead.stage=hot) → Condition(has approved hot-lead poster?)
     ─yes→ Action(creative.search status=approved kind=wa_poster segment=hot) → pick
     ─no →  [BUDGET] → Action(creative.generate kind=wa_poster segment=hot campaign_id) → [APPROVAL]
     → Action(creative.send_to_whatsapp to=lead) → Delay(1d) → Action(whatsapp.send reminder)
  ```
  The compiler's **dominator check** forces a BUDGET node over the money `creative.generate` and an
  APPROVAL node over the send — the SAME safety the engine enforces for any money tool (read from the
  `ToolSpec`, never tenant JSON). So "banner step in a workflow" and "Create New in the builder" hit the
  **identical `creative.*` contract + gates** — one seam, two front doors.

---

## 9. SECURITY / ISOLATION (the seam every call respects — inherited, restated for the UI)

- **Tenant from TOKEN, never body.** Every `creative.*` call (picker search, generate, attach, send)
  derives tenant from the authenticated token; by-id routes (`/assets/{id}`, `/assets/{id}/raw`, attach,
  resolve-at-send) **re-assert `AssetRef.tenant_id == token tenant`**. The negative control: a forged
  `vendor_id` in a body must FAIL to surface another tenant's asset (the `media-gen.md` dual-channel trap).
- **FORCE-RLS `ai_asset_*`** — the picker's search runs inside the tenant GUC; a search never leaks another
  tenant's asset; the attach handoff re-checks ownership server-side (the client gate in §5 is convenience,
  not security).
- **Approval = the content-policy firewall** — only `approved` assets attach/leave; the default biases safe
  (human-approved, no auto-launch — master §41).
- **One money-path** — generation credits via `wallet.py` (idempotent, no-double-spend); WhatsApp send cost
  via the per-message meter. Attach is free; the builder never opens a second creative spend door.
- **Immutable audit** — generate/edit/approve/attach/send/metric-writeback all row to `audit.py` (PG `events`
  leg when present); secrets redacted; never raises.
- **Dormant-until-creds** — no provider key → "Create New" shows the activation panel and the picker still
  works on existing/uploaded assets; no approved Meta template → attach works, send parks at `pending_template`;
  no DO Spaces → bytes serve from the local store (`/creative/assets/{id}/raw`). Nothing crashes.

---

## 10. OUT-OF-THE-BOX ADDITIONS (founder invited proactive features — proposed + prioritized)

| # | Feature | Where it slots (no bloat) | Priority |
|---|---|---|---|
| 1 | **One-click "make all WA sizes"** from an attached banner (square + story-card) via `regenerate(resize)` | Picker per-card action + drawer | P1 |
| 2 | **AI copy + image co-generation** — generating the poster ALSO drafts the body text + CTA from the same campaign (the Template tab pre-fills) | drawer "Use this" hands back caption+CTA, not just the image | P1 |
| 3 | **A/B template testing surfaced in-UI** — attach 2 versions to a split template; the compare UI's metrics drive an auto-"promote winner" once data lands | Compare UI §3 + writeback §7 | P1 |
| 4 | **Asset version timeline** (already specced §3.2) — the founder-asked timeline rail | Asset Detail panel | P1 (in this doc) |
| 5 | **Reuse winning template** — clone an approved template+attached-winner as a new draft for another campaign | Campaign tab "Reuse winner" card | P2 |
| 6 | **Brand-kit auto-attach** — the logo/palette/font from the library auto-seed every generate so brand consistency is default | drawer pre-seed | P2 |
| 7 | **Suppression/opt-out preview** — show how many of the chosen audience will be skipped (opted-out) BEFORE send | Audience+Send tab | P2 |
| 8 | **"Send to open-session contacts now"** fast path (free SERVICE image) while the cold-list template awaits Meta approval | Audience+Send tab, gated on session detection | P3 |

All are `creative.*`/library/WA-plane calls already in the contract — **no new media engine, no new node
type, no new store** — they are UI compositions over the existing seam.

---

## 11. HONEST REAL-vs-HYPE (the builder's claims, bounded)

| Claim | Reality |
|---|---|
| "No manual upload, ever" | **True** for library/generated/uploaded assets — the builder binds an `asset_id` and resolves bytes itself. The ONLY file-intake is the library's own upload surface (logos/product photos), surfaced inside the picker — still no builder-side file handling. |
| "Create a banner and send it in one flow" | The flow **generates a draft + builds the template**; a human (or explicit auto-mode) **approves the asset**, and **Meta approves the template** before a cold-list send. Open-session sends can go immediately. |
| "Versions compare side-by-side" | **True** — every edit/regenerate is a real `AssetRef` version; compare reads existing records; metrics shown are real or honestly "not yet tested". |
| "The attached image becomes the WhatsApp header" | **True** via Meta media upload (`media_id` per send + `header_handle` per template-create) → an IMAGE-header template. Bounded by Meta's async template approval (cannot be conjured). |
| "It learns which creative wins" | It **biases** generation toward historically winning angles/styles and surfaces top performers first — a real deterministic loop. It does **not** guarantee a winner and never invents a metric or a claim. |
| "Works dormant / offline" | The picker, attach, version-compare, gating, RLS, audit, and library reads are pure logic and offline-provable; only generation *quality* needs a provider key and real *delivery* needs the new Meta token + an approved template. |

---

## 12. BUILD/WIRING SEQUENCE (deferred — orchestrator wires; this doc only contracts the FE seam)

Each is a small verifiable FE unit; none edits the spine; all reuse the §4 contract + reference-kit components.
1. **WhatsApp builder shell** — port the 2-card page → the 4-tab multi-card workspace (Layout/Tabs/Card/
   Button), Campaign + Creative + Template + Audience tabs, dormant-safe via the existing `./api` sentinel
   pattern (like `app/booking/`). *Test: renders dormant with calm activation panels; build green.*
2. **The picker (Door B)** — Modal/Drawer + Search + Filters + GridProduct cards over
   `GET /creative/assets`/`facets`; default scope; preview; attach. *Test: search/filter/scope correct;
   tenant-scoped; empty state.*
3. **Attach flow (§5)** — bind `asset_id` on the draft, the two-gate pre-check, instant preview, reversible
   Change/Remove, audit. *Test: draft asset blocks attach until approved; ownership re-check; remove clears.*
4. **Version-compare UI (§3)** — Compare tray + side-by-side modal + version timeline over
   `search(root_asset_id)`. *Test: lineage ordered by version; attach-this-version swaps the bound id.*
5. **Create-New drawer (Door A)** — Creative Studio in a drawer pre-seeded by campaign, the §1 PHASE2 loader,
   generate/edit/regenerate/approve, "Use this template". *Test: dormant → activation panel; loader cycles;
   approve unlocks "Use".*
6. **Template tab + live preview** — phone-mockup with image header + body tokens + CTA-URL button. *Test:
   re-renders on attach/remove; tokens render.*
7. **Submit/Send resolve (§6)** — wire the resolve→Meta-upload→template-create/send path through the
   WhatsApp plane's `media_upload`/transport (orchestrator owns the spine wiring + the new token +
   approved-template registration; the FE only triggers + reflects status chips). *Test: send shape matches
   `WHATSAPP_GOLIVE` TEST 1; pending-template parks; metrics writeback links to asset.*

---

## 13. CREDENTIALS / FOUNDER TASKS (inherited — nothing net-new for THIS seam)

The seam itself needs **no new cred** — it composes already-proven pieces. The founder-side prerequisites
(all already tracked) for full production:
- **Meta `EAA…` token** updated on the box `.env` (the live box still has the OLD token — `WHATSAPP_GOLIVE` #1).
- **One real approved Meta MARKETING/UTILITY template** with an **IMAGE header** (only `hello_world` exists
  today; can't be used on the real number). Template approval is Meta's async gate.
- **OpenRouter (or other provider) key** for "Create New" generation (proven working — `WHATSAPP_GOLIVE`).
- **DO Spaces** (proven PUT/GET/DELETE) for durable/CDN asset bytes; until then local-serve works.
- `FEATURE_WHATSAPP`/`WHATSAPP_ENABLED` flag set on the box for the in-app send path.

---

## 14. THE ATTACH FLOW (canonical, one-screen — the return value the orchestrator asked for)

```
WHATSAPP BUILDER · BANNER STEP                          AI ASSET SERVICE (:8310) + ASSET LIBRARY
──────────────────────────────                          ─────────────────────────────────────────
Creative tab  ── [Pick from Library] ──►  GET /creative/assets?campaign_id&platform=whatsapp
                                          &kind=wa_poster,banner&status=approved&sort=top_ctr
                 (browse · search · filter · preview · COMPARE VERSIONS via ?root_asset_id)
              ── [Create New ▸] ───────►  drawer: POST /creative/generate {campaign_id,kind:wa_poster}
                                          → job_id → §1 LOADER → edit/regenerate (new versions)
                                          → POST /assets/{id}/approve  (draft→approved)
                                          → "Use in this template"
                         │
                         ▼  pick an AssetRef (status∈{approved,winner}, image, owned)
              ATTACH:  bind { asset_id, campaign_id, batch_id, variant_id, version } on the draft header
                       (NO bytes moved · instant preview · reversible · audited)
                         │
                         ▼  Audience+Send tab — gates surfaced: [Asset ✓] [Template ⧖ Meta]
              SUBMIT:  GET /creative/assets/{id}/raw  → bytes
                       POST /{phone_id}/media          → media_id   (cache by phone_id+sha)
                       POST /{waba_id}/message_templates (IMAGE header via resumable header_handle) → PENDING→APPROVED
                       POST /{phone_id}/messages  type=template, header.parameters=[{image:{id:media_id}}] → wamid
                         │
                         ▼  status webhook (delivered/read/click/booking)
              WRITEBACK: POST /creative/assets/{id}/metrics → AssetRef.metrics  (asset stays campaign-linked)
                         → next picker sort=top_ctr surfaces this poster · prompt-builder over-weights its angle
```
