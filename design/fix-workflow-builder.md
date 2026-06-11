# Fix: Workflow Builder — current state + exact rebuild spec

Owner scope: `famit-panel/app/workflows/*` only (+ already-present dep `@xyflow/react`).
Do NOT touch shared `components/`, `globals.css`, or `lib/api.ts`. Reuse the ported
Core_2 kit + the reference kit at `C:\Users\kunal\Desktop\core-2-dashboard-builder-react`.

---

## 1. CURRENT STATE — what's actually there (the founder's claims, verified)

React Flow IS installed and IS wired — the founder's "old card UI / React Flow not
there" is partly outdated, but his FUNCTIONAL complaints are all real:

Files (already exist, all dated 2026-06-10/11):
- `app/workflows/page.tsx` (l.124 `WorkflowStudioPage`) — 3 tabs: Canvas Studio /
  Runs / Templates. Studio tab embeds the editor inside a `<Card>` (l.424).
- `app/workflows/_editor.tsx` (484 l.) — a REAL `@xyflow/react` v12 editor:
  `ReactFlow` + `Background`/`Controls`/`MiniMap`, drag-from-palette (l.355-380),
  `onConnect` (l.134) with `isValidConnection` gate, click-to-select + inspector,
  delete, and a toolbar wired to Validate/Save/Publish/Run.
- `app/workflows/_lib.ts` (1100+ l.) — DSL `WfDefinition` (10 node types),
  `to/fromDefinition` lossless RF<->DSL map, `NODE_GROUPS` palette, and the
  `read`/`write` API client.
- `app/workflows/_nodes/WfNodeView.tsx` + `NodeInspector.tsx` — custom node + flyout.
- `app/workflows/_canvas.tsx` — the OLD read-only SVG preview (still imported by
  page.tsx l.27 for the Templates tab preview; the founder may be seeing THIS).

ROOT CAUSES of "broken / can't add / can't run / no fullscreen":

- **R1 — Engine is DORMANT (can't run).** `_lib.ts` l.5-9: the `/workflows` router is
  "DEFINED-NOT-MOUNTED" on the live backend. Every Save/Validate/Publish/Run hits a
  404 and silently degrades to a toast (`runWorkflow` l.1060). So Run genuinely does
  nothing end-to-end. This is the #1 reason "cannot run it." (Probe from dev box could
  not reach `168.144.153.145:8000/workflows/status` — SSH-only; matches dormant.)
- **R2 — "New" never gives a blank canvas (can't build from scratch).** page.tsx
  l.281 `onNewWorkflow={() => openInEditor(SAMPLE_WORKFLOW)}` re-loads the pre-filled
  SAMPLE every time. There is no empty-graph factory. So "build from scratch" is
  impossible — he always gets the demo graph.
- **R3 — Add-node is drag-DROP ONLY (can't add a node).** Palette items are HTML5
  `draggable` (l.360); the canvas relies on `onDrop`+`screenToFlowPosition`. HTML5
  DnD onto an RF pane is notoriously flaky (drop often doesn't register, esp. trackpad
  / touch / certain zoom states). No click-to-add fallback exists → "cannot add a new
  node."
- **R4 — No fullscreen.** Canvas is locked in a `<Card>` at fixed `h-[560px]`
  (_editor l.392), inside the dashboard shell + sidebar. No fullscreen toggle anywhere.
- **R5 — Premium-UI mismatch.** Studio tab is a KPI-strip + a "coming soon" explainer
  + the editor crammed in a card — not the Core_2 full-canvas builder feel the founder
  expects; Templates tab still renders the old SVG `_canvas.tsx`.

---

## 2. REBUILD SPEC — exact target

Keep the GOOD parts (DSL map, validation gate, inspector, custom node, API client).
Rebuild the SHELL + interaction model. Net new code is small.

### A. Full-screen canvas (R4) — primary deliverable
- Add a `fullscreen` boolean state in the editor. A "Fullscreen"/"Exit" toggle button
  in the toolbar (icon `maximize`/`minimize`).
- When on: render the whole editor into a fixed overlay `fixed inset-0 z-[60]
  bg-b-surface1` (escape the Card + sidebar), canvas grows to `h-full`. Esc key exits.
  Use `react-dom` portal to `document.body` so the sidebar/Layout never clips it.
- When off: keep the embedded card view but bump min height to `h-[70vh]`.
- Reuse Core_2 token classes; do NOT touch globals.css (scoped `<style>` already in
  `_editor.tsx` l.451).

### B. Click-to-add + keep drag (R3)
- Make every palette item ALSO clickable: on click, insert the node at canvas center
  (`screenToFlowPosition` of the pane centre, or a stepped offset so repeats don't
  stack) and auto-select it. Keep the existing drag path as a bonus.
- Extract the node-factory out of `onDrop` into one `addNode(wfType, position?)` so
  both click and drop call it (single source of truth, keeps the one-trigger rule).

### C. Blank "New workflow" (R2)
- Add `blankDefinition()` in `_lib.ts`: a fresh `workflow_id` (`wf_<rand>`), `name:
  "Untitled workflow"`, `status: "draft"`, default `guards`, and ONLY a single Trigger
  node (manual) — no other nodes/edges.
- page.tsx: `onNewWorkflow` → `openInEditor(blankDefinition())`. Add a separate
  "Load sample" affordance for the demo graph so the showcase isn't lost.
- Make `name`/`industry_pack` editable (an inline title field in the editor header
  that patches `editDef`), so a from-scratch workflow can be named before save.

### D. Run / Save / Publish — honest wiring (R1)
- Backend `/workflows/*` router must be MOUNTED on `caller.py` (or the workflow-studio
  service) and reachable via panel nginx, exactly like AI Manager was lit
  (`AIM_ENABLED`). Gate behind `WORKFLOWS_ENABLED`. This is a BACKEND unit — file it as
  a server task; the frontend already speaks the contract (`_lib.ts` l.1043-1100:
  status/list/runs/templates/save/validate/publish/run/approve/reject/cancel).
- Until mounted: keep the graceful 404→toast, but change the Run toast copy from a
  success-y "Run started" to an honest "Engine not live yet — saved locally" when the
  call returned `kind:"dormant"` (don't imply a run happened). `engineLive` (page.tsx
  l.197) already distinguishes live vs dormant — surface it on the Run button (disabled
  + tooltip when dormant).
- When live: Run → POST `/workflows/{id}/run`, then auto-switch to the Runs tab and
  poll that run; Save → PUT; Publish → validate-then-publish (already coded).

### E. Core_2 chrome (R5)
- Studio tab: collapse the KPI strip into a slim top bar (engine pill + node/edge
  count + toolbar). Give the canvas the screen. Move the "coming soon" explainer to a
  dismissible inline note, shown only while `moduleDormant`.
- Templates tab: replace the old SVG `_canvas.tsx` preview with a small read-only
  `ReactFlow` (interactive=false) so the whole app uses ONE canvas renderer. Then
  `_canvas.tsx` can be deleted.
- Palette / inspector / node card: keep — they already use the ported Core_2 kit.

### F. Save/load the graph (persistence)
- Live: server is source of truth (PUT save / GET load by id).
- Dormant fallback: persist the current `WfDefinition` to `localStorage`
  (`wf_draft_<id>`) on Save so a from-scratch graph survives reload before the engine
  is live. Hydrate on mount if present.

---

## 3. BUILD ORDER (units, each independently verifiable: `npx tsc --noEmit` clean)
1. `_lib.ts`: `blankDefinition()` + extract `addNode` helper signature.
2. `_editor.tsx`: click-to-add + shared `addNode` (R3, R2 wiring).
3. `_editor.tsx`: fullscreen portal + toggle + Esc (R4).
4. `_editor.tsx`: editable name/pack header + localStorage draft (C, F).
5. `_editor.tsx`/page.tsx: honest Run/Save copy + `engineLive`-gated Run button (R1 FE).
6. page.tsx: Studio chrome slimming + Templates RF preview, delete `_canvas.tsx` (R5).
7. BACKEND (separate owner): mount `/workflows/*` router behind `WORKFLOWS_ENABLED`,
   expose via nginx, smoke-test status/save/run. Then flip Run to live.

Regression gate before deploy: core `/campaigns /leads /me` 200, services active
(incl. famit-bridge voice), zero 5xx, `npx tsc --noEmit` + `next lint` clean on all
workflow files. Backup `app/workflows/` first; rollback on failure.
