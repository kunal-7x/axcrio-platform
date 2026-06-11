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
