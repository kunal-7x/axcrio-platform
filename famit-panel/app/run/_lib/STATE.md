# Run-Campaign Audience Builder — build state

Owner: run-campaign frontend agent. Scope = `app/run/**` + additive `lib/api.ts`.
Spec = `design/spec-run-campaign.md`. IRON RULE: compose ported Core_2 components only.

## Plan (compose-only, no new components)
1. [DONE] `_lib/audience.ts` — temperature bands (reuse leads page: hot>=70 / warm 40-69 / cold<40),
   composable resolve (base pool -> temp filter -> manual override), breakdown counts. Pure fns.
2. [DONE] `_lib/types.ts` — UploadBatch, SOURCE tabs, TEMP defs.
3. [DONE] `lib/api.ts` additive — RunPayload.lead_ids, getLeadBatches(), addLeads xlsx accept,
   Lead.tags/batch_id/source_file. Graceful fallback if backend lacks endpoints.
4. [DONE] `page.tsx` rebuilt: Select (campaign) + Tabs (source) + FieldFiles (csv/xlsx) +
   batch Table/TableRow/Checkbox + temp SegBtn chips + Range + manual picker Table +
   Field pacing + sticky preview/launch bar. Right = live status (kept).

## Backend dependency (NOT my scope — deploy/backend agent)
- GET /leads/batches (optional) — UI falls back to empty batch list if 404.
- POST /run lead_ids form field — UI sends it; backend must resolve. If backend
  ignores lead_ids it falls back to use_stored/leads text (graceful).
- POST /leads xlsx parsing (openpyxl) — UI sends the file as-is; server parses.

## Verify
- [DONE] `npx tsc --noEmit` — ZERO errors in app/run/** + lib/api.ts. The only
  tsc error in the repo is pre-existing `@xyflow/react` missing in app/workflows
  (NOT my domain). No build run (deploy agent builds).

## NOTE for deploy agent
- FieldFiles (components/, no-touch) renders <input type=file> with NO `accept`
  attr — so CSV+XLSX are both selectable (OS shows all files); server routes by
  extension. Its placeholder text says "product file" (cosmetic, can't fix
  without editing the no-touch component).
- All new /run params degrade gracefully if backend lacks them (see below).
