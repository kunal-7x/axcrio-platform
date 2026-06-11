# Workflow Builder — build state (this wave)

Goal: replace read-only SVG `_canvas.tsx` preview with a REAL @xyflow/react node editor
(drag from palette, connect, inspect, save/load DSL JSON) per design/spec-workflow-builder.md.

OWN ONLY: famit-panel/app/workflows/* (+ package.json dep @xyflow/react). Do NOT touch components/, globals.css.

## Units
- U0 dep + structure ......... DONE (package.json +@xyflow/react; _editor/ dirs)
- U1 _lib graph mapping ...... DONE (toDefinition/fromDefinition/INSPECTOR_FIELDS + client fns)
- U2 custom WfNodeView ....... DONE (handles, condition dual true/false, money pill)
- U3 palette drag-drop ....... DONE
- U4 inspector slide panel ... DONE (Field/Select/Switch + args key/val sub-editor)
- U5 toolbar + backend wire .. DONE (Validate/Save/Publish/Run, 404=>dormant, paint bad nodes)
- U6 wire into page.tsx ...... DONE (Studio tab -> editor; Runs/Templates kept)

## VERIFIED
- `npx tsc --noEmit` -> 0 errors (whole project).
- `npx next lint` on all 5 workflow files -> "No ESLint warnings or errors".
- @xyflow/react installed (^12.11.0) with --legacy-peer-deps.
- Did NOT run `npm run build` (orchestrator owns deploy).

## Notes
- SelectOption.id is NUMBER -> string enums use an index-keyed adapter in _lib selOpts().
- DSL contract = WfDefinition in _lib.ts (10 types, exactly). Canvas emits it verbatim.
- Single RF custom type "wfNode"; DSL type lives in node.data.wfType.
- NEVER run npm build (orchestrator does deploy). RF css imported in _editor only.

## WAVE 2 — REBUILD per design/fix-workflow-builder.md (2026-06-11)
Fixes the founder's real complaints (R1 can't run, R2 can't build blank, R3 can't add,
R4 no fullscreen, R5 looks old). Backup at famit-panel/.wf-backup-workflows/.

- R3 click-to-add ........ DONE (_lib newNodeData() factory; _editor addNode(wfType, screenPos?)
  shared by click + drop; palette items are <button> click-to-add at canvas centre w/ stepped
  offset, drag path kept).
- R2 blank New ........... DONE (_lib blankDefinition() = fresh wf_<rand> + single manual Trigger;
  page onNewWorkflow -> blankDefinition(); separate "Load sample" button keeps the showcase).
- R4 fullscreen .......... DONE (_editor fullscreen state; toolbar toggle; createPortal to
  document.body -> fixed inset-0 z-[60] bg-b-surface1; canvas h-full; Esc exits. Embedded
  height bumped to h-[70vh]).
- R1 honest run/save ..... DONE (FE) (Run disabled+tooltip when !engineLive, honest toast copy;
  Save persists localStorage draft via saveDraftLocal() + honest "saved on this device" copy
  when dormant. Hydrate via loadDraftLocal on mount). BACKEND mount = separate owner unit.
- C editable name ........ DONE (_editor inline name field -> onRename patches editDef in page).
- R5 chrome + 1 renderer . DONE (Studio: 4-up KPI strip -> slim status bar; explainer dismissible.
  NEW _preview.tsx = read-only ReactFlow (interactive=false) replaces SVG preview in Templates.
  DELETED _canvas.tsx — ONE canvas renderer app-wide. Removed dead HeroStat/FlowStep).

### VERIFIED (wave 2)
- `npx tsc --noEmit` -> 0 errors (whole project).
- `npx next lint --dir app/workflows` -> "No ESLint warnings or errors".
- Dev-server route compile probe: see below.

### OPEN (separate owner)
- BACKEND: mount /workflows/* router behind WORKFLOWS_ENABLED + nginx, smoke status/save/run,
  then Run flips live automatically (FE already speaks the full contract). Until then the FE is
  honest-dormant (Run disabled, Save = local draft).
