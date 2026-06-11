# Workflow Builder — live-verified fix (FE owner)

## Live reproduction (2026-06-11, panel.famit.in/api, real UI->BE contract)
- `GET /workflows/status` returns: `engine` = OBJECT `{engine:"in_process",available:false,store_mode:"memory",...}`, `store:"memory"`, NO `enabled` field. => FE `engineLive` (`st.enabled && st.engine==="configured" && st.store==="configured"`) is ALWAYS false => Run permanently disabled. **B1 = real, FE-only.**
- `PUT /workflows/{newid}` with no prior POST => `{"ok":false,"definition":null}`. **B2 = real, FE-only.**
- `POST /workflows {name}` => `{"ok":true,"workflow_id":"wf_<server>"}`. **CRITICAL: server MINTS its own id and IGNORES any client workflow_id.** FE must adopt the returned id for all later PUT/validate/publish/run.
- Full happy path PROVEN live with a budget-gated graph (trigger->budget->action):
  - POST create -> PUT draft -> validate `ok:true` -> publish `ok:true version 1 hash` -> **run `ok:true run_id engine:in_process status:awaiting_approval steps:2`**.
  - => **BE run engine DRAINS + executes. BE-3 is NOT broken** (doc's "queued steps:0" was a transient transport timeout). Runs list shows prior `completed` (steps:2) + `awaiting_approval` runs.
- Validate enforces real safety: `whatsapp.send` is `bulk:true` => needs a BUDGET dominator on every path, else `no_budget_dominator`. This is the rail working, not a bug. Founder must drop a Budget node before a money/bulk action.
- `store_mode:"memory"` (B4) = durability only (restart wipes). BE owner's job; NOT required for founder run-flow. Out of my scope (FE).

## Fix (FE only — I own app/workflows*; do NOT touch lib/ or other pages)
- FE-1 (page.tsx L168 + _lib.ts WfStatus type): `engineLive` reads real shape — treat `engine.engine==="in_process"` (or `available===true`) as run-capable.  [DONE]
- FE-2 (_lib.ts + _editor.tsx): first save POSTs `/workflows` to create the row, ADOPTS server id, then PUTs. Subsequent saves/validate/publish/run use that id. Remove the `!engineLive` early-return that skipped server save.  [DONE]
- Template path: instantiateTemplate returns server id; "Edit on canvas" should open the created draft id so it can publish/run.  [check]

## Verify — DONE
- `npx tsc --noEmit` => 0 errors (whole project). `npx next lint --dir app/workflows` => clean.
- Build NOT run (per task). Deploy via FORTRESS to /opt/famit-panel (backup app/workflows first) — pending.
- LIVE backend chain proven (panel.famit.in/api): budget-gated graph -> POST create -> PUT -> validate ok -> publish (v1 then v2 on re-publish) -> run `ok:true status:awaiting_approval steps:2` (parks at Budget: budget_no_funds = wallet empty on test tenant = rail working). Repeat publish+run = new run at top of Runs list. **BE run engine executes in-process; NOT broken.**

## Files changed (FE only)
- app/workflows/_lib.ts: new WfStatus/WfEngineInfo shape + isEngineLive(); upsertWorkflow() (create-row-then-PUT, adopts server id, persists created-ids in localStorage); loadServerWorkflow() (lift server draft); ValidateResult/publish/run return types match live { errors:[...] } / { status, reason }.
- app/workflows/page.tsx: engineLive = isEngineLive(st); dependency board reads real shape (engine obj, store_mode, registry_tools); ConfigPill optional label; template "Use template" instantiates -> loads server draft -> opens on canvas (publish/run-ready).
- app/workflows/_editor.tsx: serverId state (adopts server id on first save); ensureSaved(); doSave uses upsertWorkflow; doRun = one-click validate->save->publish->run with live error surfacing; validate/publish error arrays surfaced + bad nodes painted.

## NOT my scope (BE owner)
- B4 store_mode:"memory" => WORKFLOW_STORE=pg + apply schema.sql for cross-restart durability. Founder run-flow works WITHOUT it.
