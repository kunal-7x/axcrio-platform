# spec-workflow-builder.md — Rich node-based Workflow Builder (React Flow on @xyflow/react)

**Date:** 2026-06-10 · **Role:** WORKFLOW-BUILDER DESIGNER · **Status:** design spec (READ-ONLY planning; no code written this wave).

**The problem (founder):** our current Workflow Studio canvas is "cheap". The existing
`famit-panel/app/workflows/_canvas.tsx` is a hand-rolled, dependency-free SVG renderer that **renders a
static sample DSL read-only** — you cannot drop nodes, connect them, or edit a node's values; positions
never persist; nothing saves to the backend. The founder wants a **real node editor** (referenced the
Flowaxon kit, which we cannot read): drop nodes on a canvas, connect them, click a node to edit its
config in an inspector, save/load the graph, publish + run it.

**The opportunity (huge — already mostly built):** the **entire backend engine already exists** and is
production-grade. `droplet_work/workflow-studio/workflow/` ships the DSL (`dsl.py`), the static
validator+dominator compiler (`compiler.py`), the 10 node executors with money/approval/DND gates
(`nodes.py`), the durable interpreter (`interpreter.py`), the 6-table RLS Postgres store (`store.py` +
`schema.sql`), and a complete **16-route FastAPI router** (`endpoints.py`, `build_router(...)`). The DSL
graph JSON is **already the exact contract** between canvas → API → compiler → interpreter → audit. So
this is **purely a frontend job**: swap the read-only SVG canvas for a real @xyflow/react editor that
emits/consumes the SAME DSL JSON, plus wire the existing endpoints. Do NOT touch the engine or invent a
new graph format.

---

## 1. Library choice + install

**Library: `@xyflow/react` (React Flow v12, MIT licence).** This is the industry standard for node-based
editors, it is the library the backend build-log + memory already earmarked, and it works with React 19 /
Next 15 (our stack: `react ^19.0.0`, `next 15.2.0`). MIT means **no fair-code / reseller landmine** (the
exact reason we did NOT use n8n for the engine — same constraint applies to the canvas, and React Flow is
clean). It gives us, out of the box, everything the hand-rolled canvas faked or lacked: pan/zoom, drag,
**real edge-dragging between handles**, multi-select, `MiniMap`, `Controls`, `Background`, change-tracking
(`onNodesChange`/`onEdgesChange`), connection validation (`isValidConnection`), and `screenToFlowPosition`
for palette drag-drop.

**Install (React-19 peer-dep rule from CLAUDE.md — ALWAYS `--legacy-peer-deps`):**
```
cd famit-panel
npm install @xyflow/react --legacy-peer-deps
```
Import its stylesheet ONCE at the top of the canvas client component (NOT in globals.css):
`import "@xyflow/react/dist/style.css";` then override its CSS variables to our tokens (see §4).

**Why not keep the dependency-free SVG canvas:** it cannot edit, connect, or persist — it was an honest
*preview* of a dormant engine, never an editor. The engine is no longer the blocker; the editor is. React
Flow is ~30 KB gz and removes hundreds of lines of bespoke pan/drag/bezier math we'd otherwise maintain.

---

## 2. Node taxonomy (mapped 1:1 to the REAL backend — never invent types)

The DSL hard-codes **exactly these node `type`s** (`workflow/dsl.py` `NODE_TYPES`). The palette MUST expose
these and only these; unknown types are rejected at validation. Grouping + accents already exist in
`app/workflows/_lib.ts` `NODE_META`/`NODE_GROUPS` — REUSE that table (it is the design source of truth for
icon/accent/blurb/gate per type). Each row below = palette item → DSL node + its inspector fields (§3) +
real backend capability.

| Palette group | DSL `type` | Maps to backend capability | Key `config` fields the inspector edits |
|---|---|---|---|
| **Flow** | `trigger` | entry node; `trigger_kind` ∈ `manual\|schedule\|event\|webhook\|wait`; `event` ∈ `lead.created, lead.replied, call.completed, lead.qualified, payment.received, form.submitted, booking.made` | `trigger_kind` (Select), `event` (Select, when kind=event), `cron`/`segment` (Field) |
| **Flow** | `condition` | sandboxed boolean branch (`sandbox.py`); emits `when:"true"/"false"` edges | `expr` (Field/textarea, e.g. `lead.interest >= 7 && !lead.opted_out`) |
| **Flow** | `delay` | durable real-time sleep (`exec_delay`) | `after_hours` / `after_minutes` (Field number) |
| **Flow** | `wait` | durable wait-for-event (`exec_wait`) | `event_key` (Field), `timeout_hours` (Field) |
| **Workforce** | `ai_agent` | delegate to an AI-workforce role; reads Brain/KB; runs a registry tool gated like an action | `role` (Select: ai_telecaller, campaign_strategist, …), `tool` (Select from registry), `args` (key/val) |
| **Workforce** | `action` | ONE deterministic registry tool call (`leads.enqueue_calls`, `whatsapp.send`, `crm.*`, `booking.*`) | `tool` (Select), `args` (key/val editor) |
| **Workforce** | `integration` | dormant-until-creds external adapter (ads/email/BSP/calendar/webhook) | `tool` (Select), `args`, `money` (Switch — advisory only; runtime recomputes) |
| **Safety** | `budget` | reserves a run-scoped wallet hold (`exec_budget`); REQUIRED to dominate every money node | `cap_inr` (Field ₹→paise), `on_exceed` (Select: park_for_approval\|reject), `threshold_inr` (Field) |
| **Safety** | `approval` | PIN/firewall step-up gate (`exec_approval`); dominates money>threshold + bulk>cap | `require` (Select: pin\|otp), `role` (Select), `threshold_inr` (Field), `timeout_h` (Field), `on_timeout` (Select) |
| **Safety** | `error` | failure sink (`exec_error`) | `action` (Select: terminate\|notify\|handover\|retry), `reason` (Field) |
| **Data** | `data` | read/write run bag + read-only Brain/KB (`exec_data`) | `set` (key/val), `read_tool` (Select), `bag_key` (Field) |

**The `tool` Select options** come from the AI-Manager / workforce tool registry. For v1, ship a curated
static option list (the tools the engine already names — `leads.enqueue_calls`, `whatsapp.send`,
`ads.set_budget`, `crm.update_lead`, `booking.create`, `payments.create_invoice`, `brain.retrieve`) and
later hydrate from `GET /workflows/status` registry signal or a registry list endpoint. **The advisory
`money` flag is editable but cosmetic** — the runtime recomputes spend from the resolved tool+args (RTF-5),
so never let the UI imply it controls spend; surface it as a "this step can spend" badge only.

---

## 3. Inspector + palette UX — built from OUR ported Core_2 components (REUSE, never from scratch)

Our `famit-panel/components/` is **already a direct port of the Core_2 kit** (identical component names:
`Field`, `Select`, `Switch`, `Modal`, `Dropdown`, `Card`, `Button`, `Tabs`, `Badge`, `Icon`). So "reuse
Core_2" = compose these existing components — zero new form primitives. Verified signatures:
- `Field` — `{label, tooltip, type, textarea, value, onChange, placeholder, …}` → every text/number config.
- `Select` — `{label, value:{id,name}, onChange, options:[{id,name}], isBlack, placeholder}` → every enum
  (`trigger_kind`, `tool`, `role`, `on_exceed`, `on_timeout`, error `action`).
- `Switch` — `{checked, onChange}` → the advisory `money` flag + guard toggles (respect_dnd/consent).
- `Modal` — `{open, onClose, isSlidePanel, children}` — **`isSlidePanel` is exactly the right-hand inspector
  flyout** (slide-in panel from the right when a node is selected). Template preview uses the centered Modal.
- `Card` / `PageHeader` / `Badge` / `Layout` — the page shell (already used by the current `page.tsx`).

**Three-region editor layout** (replaces today's preview-only `StudioTab`):

1. **Left — Node Palette rail.** Keep the existing `NODE_GROUPS` rail markup from `page.tsx` (Flow /
   Workforce / Safety / Data, each item = accent chip + label + gate caption) but make each item
   **draggable**: `onDragStart` sets `dataTransfer` to the node `type`; the canvas `onDrop` uses
   `screenToFlowPosition` to place a new DSL node at the cursor. Reuse the exact `lift`/`bg-b-surface2`/
   `ring-s-subtle` classes already there.

2. **Center — React Flow canvas.** `<ReactFlow nodes edges onNodesChange onEdgesChange onConnect>` with
   `<Background variant="dots">`, `<Controls>`, `<MiniMap>`. **Custom node type** `wfNode` renders the SAME
   card visual the current `NodeCard` already paints (accent left-bar, icon chip in `meta.accent`, group
   eyebrow + label, money pill) — port that JSX into a `nodeTypes={{ wfNode: WfNodeView }}` component with
   `<Handle type="target" position={Left}>` + `<Handle type="source" position={Right}>`. Condition nodes
   get two labelled source handles (`true`/`false`). Selecting a node opens the inspector; `onConnect`
   appends an edge (validated by §2 rules via `isValidConnection`).

3. **Right — Node Inspector (Modal `isSlidePanel`).** On node-select, slide in a panel whose body is built
   from `Field`/`Select`/`Switch` driven by the **per-type field schema in §2**. A small `INSPECTOR_FIELDS:
   Record<WfNodeType, FieldDef[]>` map (new, tiny, in `_lib.ts`) declares each type's fields; the inspector
   renders them generically and writes back into the selected node's `config` via `setNodes`. Header reuses
   the existing inspector header (icon chip + label + close). Footer: "Delete node" + per-type help blurb.
   An **args key/value sub-editor** (repeatable `Field`+`Field` rows with add/remove) handles `action`/
   `ai_agent`/`integration` `args` and `data.set`.

**Top toolbar** (reuse the existing pill tab-strip + PageHeader actions): `Validate` (→ POST
`/{id}/validate`, paint offending `node_ids` red), `Save` (→ PUT `/{id}`), `Publish` (→ POST
`/{id}/publish`, blocked if validate fails), `Run` (→ POST `/{id}/run`). Keep the existing **Runs** and
**Templates** tabs from `page.tsx` as-is — they already work against the same router. Template "Use"
already calls `instantiateTemplate`; after the editor lands, "Edit" opens that draft in the canvas.

---

## 4. Graph schema (canvas state ⇄ DSL JSON — a thin, lossless mapping)

The canvas state is React Flow's `Node[]`/`Edge[]`; the persisted/executed format is the **DSL JSON**
(`WfDefinition` — already typed in `_lib.ts`, identical to `workflow/dsl.py`). Map both ways:

**RF Node → DSL node** (`toDefinition(nodes, edges, meta) → WfDefinition`):
```
RF node.id            → dsl node_id            (validated /^[A-Za-z0-9_\-]{1,64}$/)
RF node.type          = "wfNode" (single custom type; the DSL type lives in data.wfType)
RF node.data.wfType   → dsl type               (trigger|condition|…)
RF node.data.label    → dsl (label, studio-only)
RF node.data.config   → dsl config             (the inspector-edited object)
RF node.data.role     → dsl role               (ai_agent)
RF node.data.tool     → dsl tool               (action/ai_agent/integration; OR config.tool)
RF node.data.money    → dsl money              (advisory)
RF node.position{x,y} → dsl x,y                (layout metadata — NOT execution semantics)
```
**RF Edge → DSL edge:** `{source→from, target→to, sourceHandle "true"/"false"→when, data.error→ via
node.on_error}`. (The DSL routes errors through node-level `on_error`, not an edge flag; the canvas stores
the error target as the source node's `on_error` and draws a styled edge for it — mirror the existing
`_canvas.tsx` `edgeColor` semantics: `when:"true"`→green, `"false"`→pink, error→amber.)

The **trigger** is the single node with `wfType:"trigger"` (exactly one — the DSL enforces it). On load
(`fromDefinition`), reverse the mapping; place nodes by their stored `x,y` (auto-lay left-to-right if a
template has none, reusing `_lib.ts` `defOf` auto-layout). **Token-economy note:** the canvas owns
`x,y`; the engine ignores them — so layout never affects execution and we never round-trip-corrupt a graph.

Styling: import RF's CSS then override its vars to our Signal tokens in the canvas wrapper, e.g.
`--xy-background-color → var(--b-surface1)`, `--xy-edge-stroke → var(--color-s-highlight)`,
`--xy-node-border-radius`, handle colour → `var(--primary-01)`. Background dots reuse the existing
`radial-gradient(var(--color-s-subtle) …)` look. Result reads as our app, not stock React Flow.

---

## 5. Backend wiring — save / validate / publish / run (endpoints ALREADY exist)

The page already has a thin client in `app/workflows/_lib.ts` (mirrors `lib/api.ts` auth: `BASE` =
`NEXT_PUBLIC_API_BASE||"/api"`, `X-Auth` from `localStorage.famit_token`, 401→/login, **404/501/503 ⇒
dormant** premium "coming soon" — never an error wall). EXTEND it with the editor mutations the router
already serves (`workflow/endpoints.py build_router`, mounted via the deferred `workflow_wiring.diff`):

| UI action | Method + route (existing) | Client fn to add to `_lib.ts` |
|---|---|---|
| Create draft | `POST /workflows` `{name,industry_pack,draft}` | `createWorkflow` (exists) |
| Load editor | `GET /workflows/{id}` → `{definition, versions}` | `getWorkflow(id)` (add) |
| Save canvas | `PUT /workflows/{id}` `{draft: WfDefinition}` | `saveWorkflow(id, def)` (add) |
| Validate | `POST /workflows/{id}/validate` → `{ok, code, node_ids}` | `validateWorkflow(id, def)` (add) |
| Publish | `POST /workflows/{id}/publish` (refused unless dominator-valid) | `publishWorkflow(id)` (add) |
| Run | `POST /workflows/{id}/run` `{seed}` → `{run_id}` | `runWorkflow` (exists) |
| Runs / approve / reject / cancel | `GET /workflows/runs…`, `POST …/approve\|reject\|cancel` | exist |

**Tenant safety is already handled server-side** — `build_router` derives `tenant_id` from the token
(NEVER body), enforces `can(role,"write")` on every mutation, and `approve` verifies a firewall step-up
token bound to the tenant. The frontend sends NO `tenant_id`. **Compilation to the engine is automatic:**
`PUT` stores the draft JSON; `validate`/`publish` run `compiler.compile_and_validate` (DSL shape +
graph-dominator: every money/bulk/destructive node must be dominated by a `budget` node on every path, and
money>threshold only via an `approval` — publish REJECTS with offending `node_ids`); `run` hands the frozen
version to the single durable interpreter (`interpreter.py`) on the Hatchet spine. **The canvas never
compiles or executes anything — it only edits the DSL JSON and calls these routes.** Surface validate's
`node_ids` by painting those RF nodes red + a toast with the `code` (e.g. `money_not_dominated`).

**Dormancy reality:** until the orchestrator applies `workflow_wiring.diff` (mounts `build_router` +
`attach_event_bridge`) and Postgres/Hatchet creds land, every route 404s. The client's existing
404⇒dormant path means the editor degrades gracefully: the canvas is fully editable **locally**
(in-memory DSL, "Save"/"Publish" show the premium "engine not configured yet" toast) so the founder sees a
real, premium editor TODAY, and it lights up to full save/run the moment the diff is applied — zero
frontend change needed at cutover.

---

## 6. Build units (crash-safe, one verified deliverable each — for the implementation wave)

- **U1 — install + canvas shell.** `npm i @xyflow/react --legacy-peer-deps`; new `app/workflows/_editor.tsx`
  with `<ReactFlow>` + Background/Controls/MiniMap, tokens overridden (§4). Verify: `npm run build` clean,
  empty canvas pans/zooms.
- **U2 — custom `wfNode` + handles + palette drag-drop.** Port `NodeCard` JSX → `WfNodeView`; condition
  dual handles; left palette draggable → `onDrop`+`screenToFlowPosition` creates a typed DSL node. Verify:
  drop each of the 10 types, connect two, condition emits true/false handles.
- **U3 — inspector (Modal `isSlidePanel`) + `INSPECTOR_FIELDS`.** Per-type `Field`/`Select`/`Switch` from
  §2/§3 incl. args key/val sub-editor; writes back to `node.data.config`. Verify: edit each type, values
  persist in canvas state.
- **U4 — `toDefinition`/`fromDefinition` mapping (§4).** Round-trip the existing `SAMPLE_WORKFLOW` →
  canvas → DSL → canvas with zero loss. Verify: deep-equal except layout.
- **U5 — backend client + toolbar.** Add `getWorkflow/saveWorkflow/validateWorkflow/publishWorkflow` to
  `_lib.ts`; wire Save/Validate/Publish/Run; paint validate `node_ids` red; keep 404⇒dormant. Verify:
  against a local stub or the dormant path (toasts), and live once the diff is applied.
- **U6 — replace `StudioTab` preview with the editor**, keep Runs/Templates tabs + Templates "Edit→canvas".
  Verify: `npm run build`, manual click-through, then deploy per the standard famit-panel recipe.

**Files touched (route-local + one dep):** `package.json` (+`@xyflow/react`), `app/workflows/_editor.tsx`
(new), `app/workflows/_lib.ts` (+client fns +`INSPECTOR_FIELDS`), `app/workflows/page.tsx` (Studio tab →
editor). The old `_canvas.tsx` SVG renderer can be retired or kept for the read-only template preview.
**No backend file changes** — the engine, DSL, compiler, interpreter, and router already exist.

---

## 7. Hard rules carried in (do not regress)
- REUSE Core_2-ported components (`Field`/`Select`/`Switch`/`Modal`/`Card`/`Badge`/`Icon`) — never hand-roll
  form/card UI. React Flow is the ONE new dep (MIT — reseller-safe, the n8n landmine reason).
- The DSL JSON (`dsl.py` / `_lib.ts WfDefinition`) is the immutable contract — canvas emits it verbatim; do
  NOT invent a new graph format or a second node-type list. 10 types, exactly.
- The canvas NEVER compiles or runs anything; safety (dominator, budget hold, approval step-up, DND, bulk
  cap) is enforced in backend code, not the UI. UI only edits JSON + calls routes + shows the verdict.
- `--legacy-peer-deps` on every install (React 19). Tenant comes from the token server-side; the client
  sends no `tenant_id`. 404/501/503 ⇒ premium dormant, never an error wall.
