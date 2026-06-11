# BRAIN — Creative Studio UI design (front-end of the AI Asset Service)

Append, never delete. Durable facts for the Creative Studio FRONTEND wave.

## WHAT / WHERE
- Spec written: `design/creative-studio-ui.md` (screen-by-screen S1–S11 + WhatsApp upgrade W1 +
  the ⭐ liquid loading-animation spec §9 + endpoint wiring + build order). READ-ONLY design wave.
- It is the UI HEAD of an already-fully-designed backend: engine `design/creative-image-banner-studio.md`
  (endpoints `/creatives/*`, `BatchSpec`/`ImageBrief`/`BatchResult`, budget gate, FIX 1 = this never
  gates ad spend), asset gallery `design/creative-asset-library.md`, engine layer `memory/brain/media-gen.md`.

## KEY DESIGN DECISIONS (so we don't re-derive)
- Route group `app/creative/` in famit-panel; sidebar group "Creative Studio" with children
  Studio(`/creative`) · Library(`/creative/library`) · Brand Kit(`/creative/brand`). Insights + Performance
  fold INTO Asset Detail + Library (fewer pages — founder rule).
- Flagship = S1 Studio: 2-col HomePage grammar. col-left = Create hero (S2) + Generation card (S4 liquid
  queue → S5 variant grid); col-right = Campaign Context (S3) + Recent assets.
- ONE primary CTA per screen (Generate). Model/provider/count/size/language hide under "Advanced",
  default "Auto" — model-agnostic, vendor never has to choose a provider.
- Asset Detail (S6) = right slide-over `Modal isSlidePanel`, ports Customers DetailsPage. Holds the
  ⭐ natural-language EDIT box (every edit = NEW VERSION, original kept) + quick-chip pills.
- Variant cards (S5) = ported `GridProduct` (Products/DraftsPage/Grid), angle-labelled Badge, score, status.
  SAME card reused in Library (S9) and WhatsApp browser (W1) — one card component everywhere.

## ⭐ THE LIQUID LOADING ANIMATION (the founder headline ask)
- ONLY genuinely new component = `components/CreativeSkeleton` (everything else is a ported reference
  component). Token-built (CSS keyframes in globals.css), NO new npm dep, dark-mode-free via semantic vars.
- 4 states matching engine variant status: queued (pulse+spinner+angle label) · generating (liquid
  diagonal-gradient sweep + breathe + progress hairline) · ready (300ms clip-path/opacity dissolve →
  real image, "develops like a photo") · error (muted frame + retry). Cards morph IN PLACE in the grid
  slot (no reflow). Respect prefers-reduced-motion. Animate only background-position/opacity/transform.
  Colours = primary-01 @ low opacity + b-surface1/2; zero raw hex. "Like ChatGPT image gen."

## WHATSAPP UPGRADE (W1)
- Today `app/whatsapp/page.tsx` = 2 cards + DEPRECATED `PageHeader` (L7,96–100) + raw `<table>` (L125)
  + raw-hex amber banner (L112–114). Target = HomePage 2-col multi-card: col-right = Creative-asset
  browser (ExploreCreatorsPage grid + Filters + Search, click→preview→attach); col-left = Compose
  (To/Template/Editor + attached-banner preview + live WhatsApp-bubble preview + "Ask AI to write this"
  + deep-link "Make a poster for hot leads"→S1) + Sent log ported to Table/TableRow. Remove PageHeader,
  tokenize the banner, kill the raw table.

## HARD RULES THAT GOVERNED THIS (from ui-design-principles.md / spec-core2-reuse-map.md)
- PORT, DON'T APPROXIMATE. Reference kit IS at `core-2-dashboard-builder-react` (has templates/ +
  components/ — verified). The Core_2-Capsy path is only `…/extracted/__MACOSX` junk; use the builder-react dir.
- No PageHeader/eyebrow/subtitle; one title via `<Layout title>`; everything in a `Card`; Inter Display;
  zero raw hex (semantic @theme tokens); ≤2 saturated colours; one decisive brand blue (primary-01).
- Real loading/empty/error on every surface (Spinner / NoFound / one token banner).
- Vendor-simple: campaign + one NL instruction + Generate = the whole happy path. Jargon (BatchSpec,
  job_type, variant_id, provider) stays out of the vendor's face — tooltips/advanced only.

## ⭐ GENERATIONLOADER — the dot-matrix hero loader (spec written 2026-06-11)
- NEW spec `design/cs-loading-component.md` for `components/GenerationLoader` (PHASE2_SPEC §1): the full-area
  charcoal-on-black card with the **dot-matrix neural-energy field** ("Thinking" + bold "Creating image/banner"
  + cycling lines Understanding campaign → Designing visual direction → Composing layout → Rendering creative →
  Finalizing output). This is the SECOND new component, DISTINCT from `CreativeSkeleton` (§9): GenerationLoader =
  batch-level "engine thinking" hero; CreativeSkeleton = per-card "this slot is developing". They COMPOSE
  (loader collapses → grid of skeleton cards stream in).
- RENDER DECISION: lightweight **2D `<canvas>` particle field** (~133 dots, cap 220, 7 rings, radial size+opacity
  falloff, 4 layered motions breathe/pulse/drift/twinkle + a centre ripple) — chosen over a CSS dot-grid because
  200 animated DOM nodes jank on mid-range Android; one canvas is GPU-cheap. Pure helper `field.ts`
  (buildField/drawFrame, unit-testable). **CSS fallback** `.gl-field--css` (radial-gradient dot mask + 1 breathe
  keyframe) for prefers-reduced-motion / no-canvas / lowPower.
- TOKEN-PURE: dots read `--gl-dot`/`--gl-dot-soft` (aliases of shade-10/shade-07) via getComputedStyle — zero raw
  hex in JS; brand-blue (primary-01) ONLY on the Thinking dot + the real-progress hairline (field stays grey→white,
  calm). Reuses .surface/.card/.meter/Button/Spinner + the existing reduced-motion block.
- HONESTY: phase prop maps 1:1 to backend `ai_generation_jobs.phase`; real SSE drives the line, timer is fallback.
  Progress hairline (.meter) shows ONLY with a real `progress.total` — NEVER a fabricated %. Component does ZERO
  network I/O (onRetry/onCancel/onCompleted callbacks); page owns `useGenerationJob(jobId)` over
  `GET /api/assets/jobs/{id}/stream`. States: loading/completed(collapse→result)/failed/retry/(optional)cancelled.
  Full props API + 8-step build order in the doc.

## OPEN / DEFERRED
- Front-end build runs AFTER the in-flight UI-overhaul + Control-Layer waves (design ON TOP of their look).
- Provider/model list in the Model selector comes from `GET /creatives/status` `configured_providers`
  (dormant-until-creds — shows "Auto" + whatever keys are pasted).
- The memory file the brief named (`memory/creative-studio-asset-service.md`) and
  `memory/ai-manager-dedicated-service.md` / `ui-reuse-core2-never-from-scratch.md` do NOT exist on disk
  at those paths (those live in the projects-dir MEMORY.md index, not the repo memory/ tree). Logged here instead.

## ⭐ FINAL WORKSPACE DESIGN SHIPPED (2026-06-11) → `design/cs-workspace-final.md`
- The screen-by-screen FINAL premium-WORKSPACE design (S1–S11 + W1), refining `creative-studio-ui.md` and
  binding every surface to the REAL BUILT/FROZEN backend. ⚠ CONTRACT FIX (load-bearing): base is
  **`/api/assets/*`** (frontend-box nginx → :8310), NOT the old draft `/creatives/*`. `POST /api/assets/generate`
  →`{job_id,state,est_cost}`; poll `GET /api/assets/jobs/{id}`; stream `…/jobs/{id}/stream` (SSE); edit/regen/
  approve/reject/attach = `/api/assets/{id}/*`; upload=`/variation-from-upload`; brand=`/brand-kits`; un-gated
  probe=`GET /api/assets/status`. 18 frozen routes (backend §8 / brain A3) are the contract every screen wires to.
- ⚠ TWO loaders, not one: this doc DEFERS the full loader spec to the parallel `design/cs-loading-component.md`
  (canvas `field.ts` dot-matrix). My §9 is the WORKSPACE-PLACEMENT view only: `GenerationLoader` (batch "engine
  thinking" hero) COLLAPSES → grid of `CreativeSkeleton` (per-card "developing") that morph in place as SSE
  variants land. Both are the only hand-built bricks; everything else PORTS Core-2 (all components/templates
  named were VERIFIED on disk: Modal isSlidePanel, Card headContent, Button isBlack/isStroke/isCircle,
  GridProduct, ExploreCreatorsPage, SettingsPage, Customers/DetailsPage, Products/DraftsPage/Grid).
- W1 = full **WhatsApp Campaign Builder** (Phase-2 §2): campaign→AI-generate template→browse/attach creative→
  live WA-bubble preview→audience/schedule→send→analytics→reuse winners. Out-of-box (§19) DEFERS to
  `design/cs-out-of-box-features.md`. Dormant-safe: whole API 503-gated by `AIASSET_ENABLED` except `/status` →
  every screen renders a calm dormant state. READ-ONLY design wave (no app code / no git this wave).
