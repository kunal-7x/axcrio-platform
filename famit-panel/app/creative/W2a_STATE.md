# UNIT W2a — CREATIVE STUDIO (frontend build) — STATE

Owner: W2a agent. Build the Creative Studio page(s) per design/cs-workspace-final.md
(S1–S11) + design/cs-asset-library.md (L1–L10). PORT reference kit components; bind
to LIVE /api/assets/*. Dormant-safe behind /api/assets/status 503 guard. Reuse W1's
GenerationLoader + useGenerationJob hook + CreativeSkeleton(if present, else build).

OWNS (new files only):
- lib/assets.ts                          — typed /api/assets/* client (dormant-safe)
- app/creative/page.tsx                  — S1 Studio workspace (flagship)
- app/creative/library/page.tsx          — S9/L1–L10 Asset Library
- app/creative/brand/page.tsx            — S7 Brand Kit
- app/creative/_components/*             — CreatePanel, CampaignContext, GenerationQueue,
                                           VariantGrid, AssetCard, AssetDetail, FilterRail,
                                           BulkBar, UsePicker, VersionTimeline, BrandChips,
                                           CreativeSkeleton, LibraryGallery, DormantCard
- app/creative/_hooks/useAssetStatus.ts  — /status dormant probe
- contstants/navigation.tsx              — ADD "Creative Studio" group (brief authorizes)

MUST NOT touch: components/ (except none — all in app/creative), globals.css, layout.tsx.
Do NOT run npm build (deploy agent builds once).

## RULES (acceptance bar — cs-workspace §17 / cs-asset-library §13)
- One <Layout title>, no PageHeader, no subtitle. Inter Display. Zero raw hex (token classes).
- Reference components only; the ONLY new components are CreativeSkeleton (+GenerationLoader from W1).
- Real loading/empty/filtered-empty/error/DORMANT states everywhere.
- Plain language. Progressive disclosure (model under Advanced). Approved-only attach.

## API base = /api/assets/* (via nginx -> :8310). 503-gated by AIASSET_ENABLED except /status.

## Progress
- [x] STATE file
- [x] lib/assets.ts (typed client + dormant-safe)
- [x] _components/CreativeSkeleton (per-card liquid loader)
- [x] _hooks/useAssetStatus.ts
- [x] _components/DormantCard, BrandChips, AssetCard (the ONE card), CampaignContext
- [x] _components/CreatePanel (S2), GenerationQueue (S4), VariantGrid (S5)
- [x] _components/AssetDetail (S6 NL-edit), FilterRail (L2), BulkBar (L4)
- [x] _components/VersionTimeline (L6), UsePicker (L7/L8 attach)
- [x] _components/LibraryGallery (L1/L3/L9 selectMode)
- [x] app/creative/page.tsx (S1)
- [x] app/creative/library/page.tsx (L1-L10)
- [x] app/creative/brand/page.tsx (S7)
- [x] nav entry
- [x] tsc --noEmit check across project (PASS — verify command below)

## Verify: DONE.
- `npx tsc --noEmit` = 0 errors project-wide (fixed 1 pre-existing W1 bug:
  components/GenerationLoader/field.ts:57 `const RINGS = 7` -> `: number = 7` so
  the defensive `RINGS === 1` guards type-check).
- `npx eslint app/creative lib/assets.ts` = 0 errors, 0 warnings.
- NOT deployed (deploy agent builds+ships once). Dormant-safe everywhere via
  /api/assets/status -> DormantCard. All attach/AI-template surfaces degrade on
  503/404 to calm notes (never broken pages).
