# Fix: Workflow Builder v2 — LIVE-reproduced root cause + exact fix

Standard this wave: a fix is DONE only when the FOUNDER FLOW works in the browser
(add a node on the canvas + RUN it). This doc is grounded in a LIVE reproduction of
the deployed UI→backend chain on 2026-06-11, NOT the API-bypassing prior reports.

Boxes:
- Frontend: `root@143.110.247.249:/opt/famit-panel` (Next.js `famit-panel.service`, served via nginx, panel.famit.in).
- Backend: `famit@168.144.153.145` `/opt/famit-agent/caller.py` + the `workflow/` package; service `famit-caller` runs `uvicorn caller:app --port 8209`. Reach with `-i ~/.ssh/do-blr-test/id_ed25519`, `X-Auth: FamitCall2026`.

---

## 0. WHAT IS ACTUALLY DEPLOYED (verified on disk + in built chunks)

The frontend is NOT old — the v2 build IS live. `/opt/famit-panel/app/workflows/`
holds the new `page.tsx` (blankDefinition / Load sample / `_preview` import), `_editor.tsx`
(click-to-add `addNode`, drag, fullscreen portal, Esc), `_lib.ts` (blankDefinition, saveDraftLocal),
`_preview.tsx`. The served chunk `/.next/static/chunks/app/workflows/page-4e37b6fb…js` + the
editor chunk `1a258343-…js` contain `screenToFlowPosition` and the palette — React Flow IS wired and
click-to-add IS compiled in. BUILD_ID `Aq1SzYOymmEWqdFIMzVYh`, built Jun 11 09:45, service up.
(One harmless leftover: stale `_canvas.tsx` still on the box; local deleted it. Not imported — dead.)

So "can't add a node" is NOT an old-UI problem on the canvas itself. Add-node works in the editor.
The founder-facing failures are the RUN/SAVE chain (backend contract mismatches), detailed below.

Backend IS mounted: `caller.py` L5249 `FEATURE_WORKFLOWS` and the live `.env` has `FEATURE_WORKFLOWS=1`,
so `app.include_router(_workflow_router)` (L5257) is active. `GET /workflows/status` → **200**
(not dormant). `/workflows`, `/workflows/runs`, `/workflows/templates` all 200. The router from
`workflow.endpoints.build_router` is the authed surface (resolve_tenant → tenant `admin`).

---

## 1. ROOT CAUSES (each LIVE-reproduced; founder-facing)

**B1 — Run is PERMANENTLY DISABLED: status-shape mismatch (THE headline bug).**
The Run button is `disabled={!engineLive}` (`_editor.tsx` L421). `engineLive` (page.tsx L168) is:
```
!!st && st.enabled && st.engine === "configured" && st.store === "configured"
```
But the live backend `status()` (`workflow/__init__.py` L308) returns:
```
{"module":"workflow-studio","engine":{<object>},"config":{…},"store":"memory","templates":1,"registry_tools":[…]}
```
i.e. **no `enabled` field**, `engine` is an OBJECT (not the string `"configured"`), `store` is
`"memory"` (not `"configured"`). So `engineLive` is ALWAYS false → Run is greyed out forever, and
the page never shows "Engine live". The founder literally cannot click Run. This is the #1 reason
"cannot RUN it." It is a pure FE↔BE contract mismatch — the engine itself responds 200.

**B2 — Save silently no-ops server-side: the FE never CREATEs the row before PUT.**
`blankDefinition()` mints a client-side `workflow_id = wf_<rand>` but the FE `doSave()` →
`saveWorkflow(id,def)` issues only **PUT** `/workflows/{id}` (`_lib.ts` L1125). The backend PUT
(`endpoints.py` `_update`) calls `store.update_draft(workflow_id,…)`, and `update_draft`
(`store.py` L82-84) returns `None` when `self.defs.get(workflow_id)` is missing — i.e. it REQUIRES a
pre-existing row. There is NO POST `/workflows` to create that row first. Reproduced live:
`PUT /workflows/diag1 → {"ok":false,"definition":null}`. The FE ignores this (it isn't even reached
while dormant — `doSave` returns early on `!engineLive`), so the user is told "saved" but nothing
persisted. Validate then reads the stored draft and fails `no_trigger` because no draft was stored.
Net: from-scratch workflows never persist server-side, so they can never be published or run.

**B3 — In-process run QUEUES but never DRAINS (engine binding gap).**
After the corrected chain (POST create → PUT to that id → validate `ok` → publish `ok, version 1,
hash`), `POST /workflows/{id}/run` returned `{"error":"not_found"}` yet a run row WAS created
(`/workflows/runs` shows `wfr_…` `status:"queued" steps:0`). `run()` (`__init__.py` L151) creates the
run (L161), tries durable `engine.dispatch` (dormant → not dispatched), then in-process
`_load_published_definition` (L171→L142 `store.get_version`) before `engine.run_in_process`.
The published-version lookup raises / the in-process executor returns `not_found`, so the run is
left `queued` with `steps:0` and never executes. `status().engine` confirms `engine:"in_process",
available:false, store_mode:"memory"` — the durable Hatchet engine isn't bound and the in-process
fallback drain is faulting. So even a correctly-authored, published workflow does not actually execute.

**B4 — Store is in-memory + NON-persistent (`WORKFLOW_STORE` unset).**
`.env` has no `WORKFLOW_STORE`, so `make_store()` defaults to the in-memory backend (`store_mode:"memory"`).
Every `famit-caller` restart wipes all workflows/runs. Fine for a demo, fatal for "the founder saved a
workflow yesterday." The PG store + `schema.sql` exist (`store.py` L313 PG `update_draft`) but are not
selected and the schema is not applied on live PG.

---

## 2. EXACT FIX (smallest change that makes ADD-NODE + a BASIC TEMPLATE + a REAL RUN work)

Two FE units (small, this session) + two BE units. The canvas add-node already works; do NOT rebuild it.

### FE-1 (CRITICAL, 1-line-ish) — make `engineLive` match the real status shape.
`app/workflows/page.tsx` L168. The backend never sends `enabled`/`"configured"` strings; it sends an
`engine` object with `available` + a `store` mode string. Change to read what the server actually emits:
```ts
const eng = (st as any)?.engine;
const engineLive = !!st && (
  // durable engine bound, OR in-process interpreter present (runs synchronously)
  (typeof eng === "object" ? (eng.available === true || eng.engine === "in_process") : eng === "configured")
);
```
Recommended: treat `engine.engine === "in_process"` as RUN-CAPABLE (the in-process interpreter is a
real executor once BE-3 lands), so Run is enabled. Also update the `WfStatus` type in `_lib.ts` (L128)
so `engine` is `string | { engine:string; available:boolean; store_mode:string; … }` and `enabled`/
`store`/`registry` are optional — the current type lies about the contract.
Verify: `GET /workflows/status` → page shows "Engine live", Run button enabled.

### FE-2 (CRITICAL) — CREATE the row before PUT-saving (so saves persist + publish/run can find it).
`app/workflows/_lib.ts` `saveWorkflow` (L1125) and `_editor.tsx` `doSave` (L302). On first save of a
from-scratch workflow, POST `/workflows` (passing `name` + `draft: def` — the backend `_create` accepts
`draft`, `endpoints.py` L85; `create_def` honors a passed `workflow_id`, `store.py` L65, so pass
`workflow_id: def.workflow_id` to keep the client id), THEN PUT. Simplest: make `saveWorkflow`
upsert — try PUT; if `{ok:false}` (or 404), POST create with the same id, then it exists for next time.
Cleaner: POST `/workflows {name, industry_pack, workflow_id, draft}` once for a brand-new id, mark it
created, PUT thereafter. Remove the `!engineLive` early-return in `doSave` that skips the server call
entirely (it should still server-save once FE-1 reports engine live). Keep the localStorage draft as a
belt-and-braces fallback.
Verify (UI): New workflow → add a node → Save → reload → workflow is in `GET /workflows`, Validate `ok`,
Publish `ok`.

### BE-3 (CRITICAL) — make `_run` actually drain in-process (so Run executes).
`workflow/__init__.py` `run()` L171-176 + `_load_published_definition` L142. Reproduce the
`version_not_found` / `not_found`: after publish, `store.get_version(workflow_id, current_version,
is_admin=True)` must return the frozen snapshot that `publish()` wrote via `put_version` (L114). The
live run returned `not_found` despite a successful publish in the SAME process — debug `get_version`'s
tenant/key match (publish writes with `tenant_id=tenant_id`; `_load_published_definition` reads with
`is_admin=True` which should bypass — verify the `(workflow_id, int(version))` key and that
`current_version` is set on the def by `set_def_status` L116). Then ensure `engine.run_in_process`
executes the queued run to `completed` (or `awaiting_approval`) and persists `steps`/`status` back on
the run row, instead of leaving it `queued steps:0`. Acceptance: `POST /{id}/run` → run reaches a
terminal/parked status, visible in `/workflows/runs`, with `ok:true,run_id` (not `{"error":"not_found"}`).

### BE-4 (IMPORTANT, persistence) — select the PG store + apply schema, so saves survive restarts.
Apply `workflow/schema.sql` on live PG (the 6 tables, RLS), set `.env` `WORKFLOW_STORE=pg`, restart
`famit-caller`. Verify `status().store == "pg"` and a saved workflow survives a service restart. Until
then, B4 means every restart wipes the founder's work — call this out. (Optional staged: ship FE-1/FE-2/
BE-3 on the in-memory store first to make the demo flow work end-to-end, then BE-4 for durability.)

### Basic template (already present, just confirm it instantiates).
`GET /workflows/templates` → `templates:1` live; the FE also ships a 6-item static `TEMPLATES` library
(`_lib.ts` L888) rendered in the Templates tab. "Use template" → `POST /workflows/templates/{id}/
instantiate` (`endpoints.py` L98) creates a draft row — this is the create path that ALSO fixes B2 for
the template flow. After FE-1, confirm in the UI that "Use template" yields a draft that opens on the
canvas and can be published + run.

---

## 3. BUILD ORDER + REGRESSION GATE
1. FE-1 status-shape fix (Run un-disabled).            (FE, this session)
2. FE-2 create-before-PUT (saves persist).             (FE, this session)
3. BE-3 in-process run drain (Run executes).           (BE owner)
4. BE-4 PG store + schema (survives restart).          (BE owner)

After FE units: `npx tsc --noEmit` + `npx next lint --dir app/workflows` clean; build; FORTRESS-deploy
to `/opt/famit-panel` (BACKUP `app/workflows/` first). Regression gate (already GREEN read-only this
diagnosis): core `/me /campaigns /leads` → 200, services `famit-caller`/`famit-bridge`/`famit-agent`
active, zero 5xx in the caller journal. Founder acceptance = in the BROWSER: New workflow → click a
palette node (it appears) → wire an edge → Save → Publish → **Run** → the run shows in the Runs tab
with a non-queued status. Rollback the deployed `app/workflows/` backup on any failure.
