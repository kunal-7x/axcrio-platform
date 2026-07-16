# CREATIVE STUDIO — FRONTEND BUILD PLAN (synthesis)

> **Role:** the single page/component build plan for the Creative Studio FRONTEND, synthesized from the
> four design docs below into build waves/groups, owner files, the frontend-design acceptance bar, and the
> top-5 out-of-box features.
> **READ-ONLY design wave — this doc is a plan; no app code, no deploy, no git here.**
>
> **⚠ SEQUENCING (non-negotiable):** this BUILD runs **AFTER the UI-overhaul build clears the `famit-panel`
> frontend lane** (and after the Control-Layer frontend wave). The UI-overhaul owns `globals.css`,
> `layout.tsx`, `Sidebar`, the `@theme` tokens and Inter Display — Creative Studio is designed to land **on
> top of that finished look**, never to race it. This is "Wave B" of `CREATIVE_STUDIO_EXECUTION_PLAN.md`,
> expanded into parallelizable groups.
>
> **Source docs (do not re-derive — cite, don't copy):**
> - `design/cs-loading-component.md` — `GenerationLoader` (the dot-matrix neural-field hero loader).
> - `design/cs-workspace-final.md` — the Studio workspace S1–S11 + W1 (screen-by-screen, route-bound).
> - `design/cs-asset-library.md` — the Asset Library L1–L10 + cross-platform reuse.
> - `design/cs-out-of-box-features.md` — the 15-feature catalogue + the prioritized top-5.
> - Backend contract it binds to: `design/asset-service-backend.md` §8 (the FROZEN `/api/assets/*` routes,
>   built in parallel at `127.0.0.1:8310`; whole surface 503-gated by `AIASSET_ENABLED` except `GET /status`).

---

## 0. THE ONE-LINE GOAL

Build the Creative Studio panel UI — workspace + asset library + the top-5 out-of-box features — by
**porting `core-2-dashboard-builder-react` verbatim** and binding every surface to the real, frozen AI
Asset Service API. **Exactly TWO components are hand-built** (`GenerationLoader`, then `CreativeSkeleton`);
**everything else is a named reference port**. The signature feel: "I tell it what I need → the engine
thinks (dot-matrix hero) → cards develop in place → I pick, edit, approve, and reuse the asset everywhere."

---

## 1. ⚠ RECONCILIATION WITH THE EXISTING EXECUTION PLAN (read this first)

`CREATIVE_STUDIO_EXECUTION_PLAN.md` (authored earlier) names **only `CreativeSkeleton`** as the new
component. The loader spec `cs-loading-component.md` was authored AFTER it and **adds a SECOND new
component, `GenerationLoader`**, which the workspace doc §9 then composes WITH `CreativeSkeleton`. This
plan is the authoritative reconciliation:

- **There are TWO new components, not one.** `GenerationLoader` = the batch-level "engine thinking" hero
  (dot-matrix neural field, charcoal-on-black). `CreativeSkeleton` = the per-card "slot developing"
  placeholder. **They COMPOSE:** the loader collapses inward → a grid of skeleton cards streams in → each
  skeleton morphs into a real variant card as SSE lands. Build the loader FIRST (it is reusable across
  image/banner/ad-creative/brochure/video-thumbnail generation, platform-wide).
- Everything else in this plan refines (does not contradict) Wave B of the execution plan: same frontend
  lane, same "after UI-overhaul + Control-Layer" gate, same reference-port-only discipline, same dormant
  `/status` guard on every screen.

---

## 2. COMPONENT / PAGE BUILD ORDER (the spine)

Build in this order; each numbered item is a small verifiable unit (commit per unit, dormant-first).

| # | Unit | Owner file(s) | New or PORT | Verify-before-next |
|---|------|---------------|-------------|--------------------|
| **1** | `app/creative/` route group + nav entry + `<Layout>` shells (S1/S9/S7) with `/status` dormant guard + empty `NoFound` states | `famit-panel/app/creative/{layout.tsx,page.tsx,library/page.tsx,brand-kit/page.tsx}`, `contstants/navigation.tsx` | scaffold | renders; nav active-state correct; **byte-identical when `/status` says dormant** |
| **2** | **`GenerationLoader`** (the dot-matrix hero) — `globals.css` `gl-*` tokens/keyframes → `field.ts` pure canvas module → `index.tsx` mount/RAF/DPR/ResizeObserver → status-line cycle → `phase`/`progress` real-binding → states (completed-collapse / failed-retry / cancel / fullscreen) → reduced-motion CSS fallback | `components/GenerationLoader/{index.tsx,field.ts}` + `app/globals.css` (`@layer components` `gl-*` block) | **NEW #1** | 60fps on throttled mobile (4× CPU); crisp on retina DPR; **no fabricated %**; calm reduced-motion `.gl-field--css`; clean collapse-to-result exit |
| **3** | **`CreativeSkeleton`** (per-card liquid/wave placeholder) + `globals.css` keyframes | `components/CreativeSkeleton/index.tsx` + `app/globals.css` keyframes | **NEW #2** | 4 states (queued→generating→ready→error); CSS-only 60fps; reduced-motion fallback; dark-mode; morphs in place, **no reflow**; **loader-collapse → skeleton-grid compose proven** |
| **4** | **S2 Create panel** — campaign Select + asset-type Tabs + platform + MODEL (Advanced) + hero command box + Generate → `POST /api/assets/generate` | `app/creative/_components/CreatePanel.tsx` (PORT `NewProductPage` head grammar + `Field`/`Select`/`Tabs`/`Editor`) | PORT | submit returns `{job_id,state,est_cost}`; Advanced disclosure; the live credit estimate shows (F11) |
| **5** | **S3 Campaign Context** — provenance-dot facts + brand chips | `app/creative/_components/CampaignContext.tsx` (PORT `PopularProducts`/`Details` rows) | PORT | reads job `campaign_ctx` + `GET /brand-kits`; filled vs hollow provenance dots render the no-invent guarantee |
| **6** | **S4 Generation Queue + SSE** — `GenerationLoader` bound to `GET /api/assets/jobs/{id}/stream` via a thin `useGenerationJob(jobId)` hook | `app/creative/_hooks/useGenerationJob.ts` + `app/creative/_components/GenerationQueue.tsx` | wire | SSE drives real phase line; loader collapses → `CreativeSkeleton` grid; no fake % when `progress.total` absent |
| **7** | **S5 Variants Grid** — angle-labelled rich cards | `app/creative/_components/VariantGrid.tsx` (PORT `Products/DraftsPage/Grid` + `GridProduct`) | PORT | skeleton → variant morph in place; angle/status `Badge`, score `Percentage`, hover actions |
| **8** | **S6 Asset Detail + NL edit** — slide-over with editable copy, score, status control, the ⭐ NL edit box, version strip | `app/creative/_components/AssetDetail.tsx` (PORT `Modal isSlidePanel` + `Customers/DetailsPage`) | PORT | `/edit` → NEW version (original kept); status control; quick-chip pills; version strip = lineage (F5) |
| **9** | **S1 Studio Workspace (flagship)** — 2-col assembly of #4–#8 | `app/creative/page.tsx` (PORT `HomePage` 2-col) | PORT+assemble | col-left Create+Generation; col-right Campaign Context + Recent assets; everything composes |
| **10** | **S9 / L1–L4 Asset Library** — gallery + filter rail + asset card + bulk bar | `app/creative/library/page.tsx` + `_components/{LibraryGallery,FilterRail,AssetCard,BulkBar}.tsx` (PORT `Products/DraftsPage` {index,Grid,List} + `ExploreCreatorsPage`/`Filters` + `GridProduct` + `useSelection`) | PORT | `GET /api/assets` with all 8 facets as query params; grid/list toggle; status Tabs quick-filters; removable filter chips; full loading(`CreativeSkeleton`)/empty/filtered-empty/error states |
| **11** | **L5 / L6 Library detail + version timeline** — detail drawer (Details/Versions/Performance tabs) + horizontal lineage + Compare | `app/creative/library/_components/{AssetDrawer,VersionTimeline}.tsx` (PORT `Modal isSlidePanel` + `Customers/CustomerList/DetailsPage`) | PORT | `GET /api/assets/{id}` owner-checked (404 cross-tenant); Restore flips `current_version_id`; side-by-side Compare |
| **12** | **L7–L9 / S11 cross-platform reuse** — "Use this →" picker + attach + embedded `selectMode="pick"` gallery | `app/creative/_components/{UsePicker,AttachWhatsApp}.tsx` + `library` `selectMode` prop | PORT | one verb `POST /api/assets/{id}/attach {channel,ref_id}`; approved-only gate; WA-template pick/AI-write + bubble preview; embedded picker reuses the SAME gallery |
| **13** | **S7 Brand Kit** + **S8 Performance** | `app/creative/brand-kit/page.tsx` (PORT `SettingsPage`) + `AssetDetail` Performance tab + Library "Winners" facet | PORT | `GET/POST /brand-kits`; Performance honest-empty until the ads loop reports (reports only, never moves budget) |
| **14** | **S10 Upload-reference** — "make this kind of banner" | `app/creative/_components/UploadReference.tsx` (PORT `file_upload` chrome) | PORT | `POST /variation-from-upload`; wallet estimate→hold→settle gate |
| **15** | **W1 WhatsApp Campaign Builder** — premium 2-col multi-card (replaces the 2-card page) | `famit-panel/app/whatsapp/page.tsx` (PORT `Table`/bubble preview; remove `PageHeader`) | PORT | AI-generate template + browse/attach creative (reuses #12 picker) + live WA-bubble preview; raw table + raw-hex removed |
| **16** | **Acceptance pass** — run the §6 bar per page | all of the above | gate | every page green; dormant `/status` path verified on every screen |

> The §16 features (F1–F5) attach to existing units — they add **zero new pages and only one additive
> endpoint** (F1). See §4.

---

## 3. BUILD WAVES / GROUPS (parallelization — by component/page, zero shared files)

The whole thing is **Wave B** of the execution plan, expanded. Within it, partition by file so multiple
agents never touch the same file. The hard serialization edges are: **scaffold (G0) → everything**;
**loaders (G1) → the screens that compose them**; **the gallery/card (G3) → the embedded picker + W1
(G5)**.

```
                 ┌──────────────────────────────────────────────┐
   PRECONDITION  │  UI-OVERHAUL build clears the famit-panel lane │  (this BUILD starts only after)
                 │  + Control-Layer frontend wave landed          │
                 └───────────────────────┬──────────────────────┘
                                         │
                                   ┌─────▼─────┐
                                   │  G0 SCAFFOLD │  route group + nav + Layout shells + /status guard
                                   └─────┬─────┘
                 ┌───────────────────────┼───────────────────────────┐
            ┌────▼────┐             ┌────▼────┐                  ┌────▼────┐
            │ G1 LOADERS│  (opus)    │ G2 CREATE │  (opus)         │ G3 LIBRARY│  (sonnet)
            │ GenLoader │            │ S2+S3+    │                 │ L1–L6     │
            │ + Skeleton│            │ context   │                 │ gallery/  │
            │ (2 new)   │            │ + estimate│                 │ card/     │
            └────┬─────┘            └────┬────┘                  │ filter/   │
                 │                       │                       │ drawer/   │
                 │                       │                       │ versions  │
                 └──────────┬────────────┘                       └────┬─────┘
                       ┌────▼────┐                                    │
                       │ G4 GENERATE│  (opus)  S1 flagship assembly    │
                       │ S4 SSE +   │  ← needs G1 (loaders) + G2       │
                       │ S5 grid +  │    (create) + G3 card            │
                       │ S6 detail/ │                                  │
                       │ NL edit    │                                  │
                       │ S1 assemble│                                  │
                       └────┬──────┘                                  │
                            └───────────────┬────────────────────────┘
                                       ┌────▼────┐
                                       │ G5 REUSE  │  (sonnet)
                                       │ L7–L9/S11 │  ← needs G3 gallery/card
                                       │ attach +  │    (embedded picker) + G4 detail
                                       │ picker    │
                                       └────┬────┘
                       ┌────────────────────┼────────────────────┐
                  ┌────▼────┐          ┌────▼────┐          ┌────▼────┐
                  │ G6 BRAND  │ (sonnet)│ G7 UPLOAD │ (sonnet)│ G8 WHATSAPP│ (sonnet)
                  │ S7 + S8   │         │ S10        │         │ W1 builder │  ← needs G5 picker
                  └─────────┘          └─────────┘          └─────────┘
                                       ┌────▼────┐
                                       │ G9 ACCEPTANCE │  §6 bar per page → green
                                       └──────────┘
```

**Group ownership (one agent per group; non-overlapping files):**

| Group | Owns (files) | Depends on | Model | Why parallel-safe |
|-------|--------------|------------|-------|-------------------|
| **G0 Scaffold** | route group, nav, `Layout` shells | UI-overhaul lane clear | sonnet | foundation; everything waits on it |
| **G1 Loaders** | `components/GenerationLoader/*`, `components/CreativeSkeleton/*`, the `gl-*`/skeleton blocks in `globals.css` | G0 | **opus** | self-contained, zero page deps; the two NEW components |
| **G2 Create** | `_components/CreatePanel,CampaignContext`, `useGenerationJob` hook stub, F11 estimator | G0 | **opus** | own files; binds `/generate` + `/brand-kits` |
| **G3 Library** | `library/page.tsx`, `_components/{LibraryGallery,FilterRail,AssetCard,BulkBar,AssetDrawer,VersionTimeline}` | G0 | sonnet | own dir; the `GridProduct`/`DraftsPage`/`Filters` ports; produces the reusable card + embedded-picker base |
| **G4 Generate** | `_components/{GenerationQueue,VariantGrid,AssetDetail}`, `page.tsx` (S1 assembly) | G1+G2+G3-card | **opus** | the orchestration heart; composes loaders + create + card |
| **G5 Reuse** | `_components/{UsePicker,AttachWhatsApp}`, `library` `selectMode` | G3+G4 | sonnet | the single `attach` verb surfaced everywhere |
| **G6 Brand/Perf** | `brand-kit/page.tsx`, Performance tab/facet | G0 (+G3 facet) | sonnet | `SettingsPage` port; honest-empty perf |
| **G7 Upload** | `_components/UploadReference` | G0 | sonnet | isolated `variation-from-upload` flow |
| **G8 WhatsApp** | `app/whatsapp/page.tsx` (Wave C of exec plan) | G5 picker | sonnet | reuses the embedded picker; same lane, runs last |
| **G9 Acceptance** | none (read+verify) | all | sonnet | the §6 gate |

**Maximum concurrency:** after G0, **G1 ∥ G2 ∥ G3** run together (three different file sets, zero
collisions). Then **G4** joins (needs the three). Then **G5 ∥ G6 ∥ G7** (G5 needs G3+G4; G6/G7 need only
G0). **G8** last (needs G5). **G9** closes. Per global rule: never run two agents on the same file; share
state via the frozen API contract only.

---

## 4. THE TOP-5 OUT-OF-BOX FEATURES (where each one plugs in)

All five reuse existing Core_2 components + the frozen API; **the entire top-5 needs zero new tables and
zero new columns — only F1 adds one additive endpoint.** Full rationale: `design/cs-out-of-box-features.md`.

| # | Feature | UI home | API / data | Effort | Build slot |
|---|---------|---------|-----------|--------|-----------|
| **F1** | **Brand-Kit Auto-Extraction** — drop a logo / paste a website or IG URL → auto-fill palette/logo/tone/CTA | S7 Brand Kit panel (**G6**) | **NEW** additive `POST /brand-kits/extract` (logo-color path = zero model spend) | M | G6 |
| **F2** | **One-Click "Make All Sizes"** — fan an approved creative to the full platform size matrix (re-laid-out, not cropped) | S11 Resize / S6 footer (**G5**/G4) | existing `BatchSpec` cross-product → new `ai_asset_versions` (no schema change) | M | G4/G5 |
| **F3** | **In-UI A/B Creative Test** — turn an angle-labelled variant set into a tracked experiment + per-angle leaderboard + "promote winner → 5 more" | S5 select + S8 Performance (**G4**/G6) | reuses `attach` → `ads_engine` → `metrics`; reports only, never moves budget | M | G4 + G6 |
| **F4** | **Model-Comparison (2 models side-by-side)** — same brief on two providers, paired cards, learn per-tenant best model | S2 Advanced (**G2**) | `/generate` with two `model` selections; `/providers` lists options | M | G2 |
| **F5** | **Asset Version Timeline** — horizontal lineage of every edit/regenerate + compare-any-two + roll-back | S6 / L6 (**G4**/G3) | pure VIEW of `ai_asset_versions` already stored; Restore flips `current_version_id` | S | G3 + G4 |

**Bundle-free riders (ship inline, trivial):** **F11** live smart credit estimator (ships with G2's S2),
**F12** "From this →" remix (ships with G3/G7's S9/S10).

**Rejected / explicitly out (keep it un-bloated):** manual canvas/layer/font/color editor; stickers/
filters/memes; stock-photo bank; video/brochure/landing builders (route to other services); silent
auto-ad-spend; cross-tenant template marketplace (F15 — Phase-3+, breaks per-tenant FORCE-RLS).

---

## 5. DATA WIRING — every surface → the FROZEN backend (base `/api/assets/*`)

Bind to the REAL built/frozen routes (`design/asset-service-backend.md` §8; brain A3). **Do NOT invent
`/creatives/*`** — that was a draft prefix; transport base is `/api/assets/*` via the frontend-box nginx
`location /api/assets/ → :8310`. The whole surface is **503-gated by `AIASSET_ENABLED`** except
`GET /status` — so every screen must call `/status` first and render its dormant state when disabled
(byte-identical-to-live guarantee).

- Create/Generate: `POST /api/assets/generate` → `{job_id,state,est_cost}` · `GET /jobs` · `GET /jobs/{id}` ·
  `GET /jobs/{id}/stream` (SSE, drives `GenerationLoader.phase`) · `POST /jobs/{id}/cancel`.
- Assets: `GET /assets` (all 8 facets as query params, token-scoped, paginated) · `GET /assets/{id}`
  (owner-checked → 404 cross-tenant) · `GET /assets/{id}/raw` (streams bytes; never exposes `local_path`).
- Mutate (each = a wallet spend, except approve/reject/attach): `POST /assets/{id}/edit` (→ new version) ·
  `/regenerate` · `/approve` · `/reject` · `/attach {channel,ref_id}` (→ `ai_asset_usage`; **approved-only**,
  409 if not) · `/attach-whatsapp` · `POST /variation-from-upload`.
- Brand: `GET`+`POST /brand-kits` (+ **F1** additive `POST /brand-kits/extract`).
- Providers/Status: `GET /providers` · `GET /status` (the only un-gated route — the dormant guard).

---

## 6. FRONTEND-DESIGN ACCEPTANCE BAR (every page must pass)

Per the frontend-design skill + `ui-design-principles.md` §7 + the four docs' acceptance sections:

1. **Inter Display app-wide**, single-line clean headings, **no subtitle**; one `<Layout title>` per page,
   **no `PageHeader`**.
2. **Zero raw hex anywhere** — `@theme`/semantic tokens only (the loader reads `--gl-dot`/`--gl-dot-soft`
   via `getComputedStyle`; brand-blue only on the Thinking dot + progress hairline).
3. **Dark-mode correct** in both themes; the loader is a deliberate charcoal-on-black "engine" moment.
4. **Reference-port-only** — every brick maps to a NAMED `core-2-dashboard-builder-react` component
   (verified on disk); the ONLY hand-built components are `GenerationLoader` + `CreativeSkeleton`.
5. **Real states everywhere** — loading (`CreativeSkeleton`/`GenerationLoader`) / empty / filtered-empty /
   error / dormant; **never a fabricated %** (progress hairline shows only with a real `progress.total`).
6. **Plain language**, vendor-simple; progressive disclosure (model/advanced hidden under "Advanced").
7. **Dormant-safe** — `/status` guard on every screen; with `AIASSET_ENABLED=0` the panel is
   byte-identical-to-live.
8. **No-invent honoured** — copy surfaces inherit the §20 validator; provenance dots make "the AI won't
   make up facts" VISIBLE (filled = real fact, hollow = AI will ask).
9. **Approval + wallet gates VISIBLE** — only `approved` assets can attach; every generate/edit shows the
   credit estimate (F11) before spend.
10. **Performance:** 60fps loader on mid-range Android (throttled 4× CPU); crisp on retina; no reflow on
    skeleton→card morph; RAF pauses on tab-hidden/off-screen.

---

## 7. SOURCES / GROUND TRUTH

- `design/cs-loading-component.md` (loader §1–§13) · `design/cs-workspace-final.md` (S1–S11, W1, §16–§20) ·
  `design/cs-asset-library.md` (L1–L10, §12 wiring) · `design/cs-out-of-box-features.md` (F1–F15, top-5).
- Backend: `design/asset-service-backend.md` §8 (frozen routes) · brain `memory/brain/creative-studio.md`
  (A1/A2/A3 — service LIVE+DORMANT, 18 frozen routes, the `/api/assets/*` vs `/creatives/*` reconciliation).
- Reference kit (ports verified on disk): `core-2-dashboard-builder-react/templates/Products/DraftsPage/
  {index,Grid,List}.tsx`, `templates/ExploreCreatorsPage/{index,Filters}.tsx`, `templates/HomePage`,
  `templates/NewProductPage`, `templates/SettingsPage`, `templates/Customers/.../DetailsPage`,
  `components/{GridProduct,Modal,Button,Badge,Percentage,Field,Select,Tabs}`, `hooks/useSelection.ts`.
- Plan parent: `CREATIVE_STUDIO_EXECUTION_PLAN.md` Wave B/C (this doc expands B into G0–G9). **This BUILD
  runs AFTER the UI-overhaul build clears the frontend lane.**
