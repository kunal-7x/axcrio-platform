# Run-Campaign Upgrade — Full UX + Core_2 Reuse + Backend Plan

Status: DESIGN (read-only). Target page: `famit-panel/app/run/page.tsx`.
Design source of truth: Core_2-Capsy-Dashboard CODE (Figma is unreadable/binary).
IRON RULE: every visual piece below is a PORT of a real Core_2 component already
present in `famit-panel/components/` — nothing invented from scratch. We only
compose the existing primitives and rewire our data onto the Signal tokens
(b-/t-/s-) used everywhere else in the panel.

---

## 0. What's wrong today (current `app/run`)

- Just **2 plain cards**: a left "Start a Call Run" config card (campaign `<select>`,
  a leads `<textarea>`, a "use stored" checkbox, 3 number inputs) + a right "Live
  Status" table.
- WHO to call is binary: paste text OR tick "Use stored leads" (= ALL stored). No
  way to pick a subset, no temperature filter, no per-file choice, no preview of
  who gets dialed.
- The campaign picker is a raw `<select>` (line 181) — the "ugly dropdown" the
  founder called out.
- Only **one** CSV file at a time; **no Excel (.xlsx)** support anywhere.

Goal: a richer, scrollable, multi-card **Audience Builder** giving full,
composable control over WHO to call, with a live preview/count before launch.

---

## 1. New page layout (the card/section list)

Two-column shell kept (`flex gap-6 max-lg:flex-col`), but the LEFT column becomes
a **scrollable stack of audience cards** and the RIGHT stays the live-status table.
Left column wrapped in `max-h-[calc(100vh-...)] overflow-y-auto pr-1` so many cards
scroll independently (founder asked for "multiple scrollable cards").

Card / section list (top → bottom, left column):

1. **Campaign card** — the beautiful Select (replaces the raw `<select>`), agent
   voice/preview chip, calling-window hint. PORT: `components/Select`.
2. **Audience Source tabs** — a pill Tab bar choosing the SOURCE mode:
   `All stored` | `By temperature` | `By upload/file` | `Pick manually`.
   These are **composable filters layered on one base set**, not exclusive screens
   (see §3). PORT: `components/Tabs`.
3. **Lead Source / Upload card** — drag-drop zone accepting **CSV + XLSX**, a list
   of previously-uploaded batches (file A = 10 leads, file B = 20…), each a
   selectable row with a checkbox + count + uploaded-at. Vendor ticks one or many
   files. PORT: `components/FieldFiles` (dropzone) + `components/Table`/`TableRow`
   (batch list with select) + `components/Checkbox`.
4. **Temperature filter card** — segmented multi-select chips Hot / Warm / Cold /
   Custom-tag, each showing a live count from the loaded set; optional score
   `Range` slider for "custom". PORT: the segmented-pill pattern from
   `app/leads` `SegBtn` + `components/Checkbox` + `components/Range` (for the
   custom score band) + `components/Select` (for the tag dropdown).
5. **Manual lead-picker card** — searchable data table of the resolved candidate
   leads with a **select-all header checkbox + per-row checkbox** (exact Core_2
   Customers list pattern), name/phone/score/status columns, ScoreBadge. Vendor
   hand-picks specific leads. PORT: `components/Table` + `components/TableRow` +
   `components/Search` + `lib/badges` (ScoreBadge/StatusBadge).
6. **Pacing & caps card** — concurrency / hourly cap / daily cap (the 3 existing
   number inputs, restyled into a clean `Field` group). PORT: `components/Field`.
7. **Audience Preview / Launch bar** (sticky bottom of left column) — big "**N leads
   will be called**" counter, a breakdown chip row (e.g. "12 hot · 8 warm · 3
   excluded DND"), and the `Start Calling` button. Reuses the existing
   suppressed/queued toast logic. PORT: `components/Badge` + `components/Button` +
   existing `KpiCard` style for the count.
8. **Right column — Live Status** card: UNCHANGED (keep current polling table).

All cards use the existing `components/Card` wrapper so headers/spacing match the
rest of the panel.

---

## 2. Exact Core_2 components to PORT (already in `famit-panel/components/`)

Good news: the **entire Core_2 component set is already ported** into our panel
(`components/Select`, `Tabs`, `Checkbox`, `Table`, `TableRow`, `FieldFiles`,
`Field`, `Search`, `Range`, `Dropdown`, `Badge`, `Filters`), and
`@headlessui/react@^2.2.0` is already a dependency. So this is a COMPOSE job, not a
new-component job. Mapping:

| UI piece (this spec) | Core_2 component (file to reuse) | Notes / rewire |
|---|---|---|
| Beautiful campaign dropdown | `components/Select/index.tsx` (Headless `Listbox`) | replaces raw `<select>` at run/page.tsx:181. Feed `Campaign[]`→`SelectOption{id,name}`. `types/select.ts` already exists. |
| Source-mode pill tabs | `components/Tabs/index.tsx` | `types/tabs.ts` exists. items = All/Temp/Upload/Manual. |
| Drag-drop CSV+XLSX dropzone | `components/FieldFiles/index.tsx` | widen `accept` to `.csv,.xlsx,...`; show file size + remove btn (already built in). |
| Uploaded-file batch list w/ select | `components/Table` + `components/TableRow` | the `selectAll`/`onRowSelect`/`selectedRows` props already wire row checkboxes. |
| Per-row + select-all checkboxes | `components/Checkbox/index.tsx` (Headless) | used internally by Table/TableRow — reuse as-is. |
| Manual lead-picker table | `templates/Customers/CustomerList/.../List/index.tsx` pattern → built on `components/Table`+`TableRow` | copy the selectedRows[]/onRowSelect/selectAll/onSelectAll state pattern verbatim, swap Customer→Lead columns. |
| In-table search | `components/Search/index.tsx` (or the inline search already in app/leads) | client-side filter over loaded leads. |
| Custom score band slider | `components/Range/index.tsx` | min/max score 0–100, used in Filters template already. |
| Temperature chips | `app/leads` `SegBtn` segmented pattern (already in-repo) + `components/Badge` | multi-select variant. |
| Pacing inputs | `components/Field/index.tsx` | restyle the 3 number inputs. |
| Preview counts / breakdown | `components/Badge` + `components/KpiCard` | big N + tone chips. |
| Launch button | `components/Button/index.tsx` (`isBlack`) | unchanged. |
| (Optional) "Advanced filters" modal | `components/Filters/index.tsx` | exact Modal+Select+Range+Switch combo if we want a single filter modal instead of inline cards. |

Reference template for the multi-card-on-left + table-on-right + row-select page
shape: **`templates/Customers/CustomerList/CustomerListPage`** (its `List` child is
the canonical row-select table) and **`templates/Products`** for the multi-card
scrollable left rail look.

---

## 3. Composable filter model (the core UX idea)

The four "source" tabs are NOT four separate screens — they are **layers that
compose** into one final audience set, evaluated client-side over a fetched
candidate pool, then sent to the backend as an explicit lead-id list (preferred)
or a filter spec.

```
BASE POOL
  = (stored leads from /leads)  ∪  (leads from selected uploaded batches)
        ↓ apply
TEMPERATURE FILTER  (hot ≥70 / warm 40–69 / cold <40 / tag=… / custom score band)
        ↓ apply
MANUAL OVERRIDE     (if vendor hand-picked rows → use exactly those;
                     else use everything that passed the filters)
        ↓ minus
SUPPRESSION (DND)   (backend already pre-filters; show excluded count)
        ↓
PREVIEW: "N leads will be called"  →  Start
```

Temperature thresholds reuse the EXACT bands already in `app/leads/page.tsx`:
hot `score ≥ 70`, warm `40–69`, cold `< 70`/unscored. "Custom" = `Range` band +
tag Select.

Because the preview is computed on the client from real lead rows, the count is
always truthful (consistent with the leads page's "never fabricate" rule). We then
send the resolved **`lead_ids`** to `/run` so the server dials exactly that set.

---

## 4. Data flow / frontend wiring

State on `app/run/page.tsx`:
- `campaign: SelectOption` (was `campaignId`).
- `sourceMode: TabsOption`.
- `batches: UploadBatch[]` (from new `GET /leads/batches`), `selectedBatchIds: Set`.
- `temps: Set<'hot'|'warm'|'cold'|'custom'>`, `customBand:[lo,hi]`, `tag`.
- `candidates: Lead[]` = `useMemo` over stored leads + selected-batch leads.
- `filtered: Lead[]` = candidates after temp/tag/band.
- `manualSelected: Set<leadId>` (empty ⇒ "all filtered").
- `audience: Lead[]` = manualSelected.size ? pick(manualSelected) : filtered.
- Preview KPI = `audience.length`, breakdown = counts by temp + suppressed.

On Start: call `run({ campaign_id, lead_ids: audience.map(id), use_stored:false,
concurrency, hourly_cap, daily_cap, force })`. Keep the existing
queued-out-of-window / insufficient-balance / Start-anyway toast logic verbatim.

New `lib/api.ts` additions:
- extend `RunPayload` with `lead_ids?: string[]` (sent as repeated form field or
  CSV string) and keep `csv`/`leads` for backward-compat ad-hoc paste.
- `getLeadBatches(): Promise<{batches: UploadBatch[]}>` → `GET /leads/batches`.
- extend `addLeads` upload to accept xlsx (just the file; parsing is server-side)
  and return the created `batch_id` + filename.
- `Lead` type: add optional `tags?: string[]`, `batch_id?: string`,
  `source_file?: string`.

---

## 5. Backend changes (caller.py @ root@168.144.153.145:/opt/famit-agent/caller.py)

Current reality (verified on box):
- Leads live in a JSON store (`LEADS_FILE`), each row
  `{id, tenant_id, name, phone, status, added_at, score?, last_outcome?}`.
  **No batch/source/tag fields.**
- `parse_leads(text, csv_bytes)` (caller.py:776) uses stdlib `csv` only — **no xlsx**.
- `POST /leads` (:2550) takes `leads` text + single `csv` UploadFile.
- `POST /run` (:2592) takes `leads` text + single `csv` + `use_stored` (=ALL).
  **No `lead_ids`, no temperature filter, no per-file selection.**
- Neither `openpyxl` nor `pandas` is installed in the venv (`/opt/capsy-agent/.venv`).

Required deltas:

1. **Excel parsing lib** — `pip install openpyxl` into `/opt/capsy-agent/.venv`
   (lightweight, pure-py, read-only `.xlsx`; avoid pandas — too heavy for this box).
   Add an `parse_xlsx(bytes)->rows` helper mirroring `parse_leads`'s phone/name
   column sniffing; route by uploaded filename/content-type in `add_leads` and in
   `parse_leads` (accept `.xlsx` → openpyxl, else csv reader). CSV stays papaparse-
   free server-side (Python `csv` already works); xlsx is the only new dep.

2. **Lead schema additions (additive, back-compat)** — when a lead is added via a
   file, stamp `batch_id` (uuid8), `source_file` (original filename), and allow an
   optional `tags: []`. Existing rows without these keep working (default `[]`/`""`).

3. **`GET /leads/batches`** — return distinct upload batches for the tenant:
   `[{batch_id, source_file, count, added_at}]`, derived by grouping
   `_leads_for(t)` on `batch_id`. (No new storage needed — group the JSON store.)

4. **`POST /run` — accept an explicit audience**:
   - new optional form field `lead_ids` (comma-sep or repeated). When present,
     resolve to that tenant's leads by id (BOLA-guard: only own leads), build the
     dial list from those, IGNORE `use_stored`. This is the primary path for the
     new UI (preview == what dials).
   - keep `leads`/`csv`/`use_stored` for the ad-hoc/legacy path.
   - (optional convenience, can be done purely client-side instead) accept
     `temps=hot,warm` + `batch_ids=...` server-side filters; client-side is simpler
     and keeps preview truthful, so **prefer client resolves → sends lead_ids**.

5. **`POST /leads` xlsx** — widen to parse `.xlsx`; return `{added, total,
   batch_id, source_file}` so the UI can show the new batch immediately.

6. **Tags (temperature "custom")** — optional `POST /leads/{id}/tags` or a bulk
   `tags` field on add; lets vendors label hot/warm beyond score. Low priority;
   score-based temp works day one without it.

Storage: stays the existing JSON lead store (no new DB). Uploaded raw files do NOT
need persisting — we parse on upload into lead rows tagged with `batch_id`; the
"batch" is a logical group, not a stored blob. (If raw-file re-download is ever
wanted, drop files under `~/leads/uploads/<batch_id>.<ext>`.)

No change to the dial loop, billing gate, suppression pre-filter, window gate, or
status polling — those all operate on the resolved `JOBS[job_id]["leads"]` list,
which we simply populate from `lead_ids`.

---

## 6. Build order (per crash-safe protocol)

1. Backend: `openpyxl` install + `parse_xlsx` + xlsx routing in `add_leads`
   (verify: upload a .xlsx, leads appear). Commit/back up `caller.py` first.
2. Backend: `batch_id`/`source_file` stamping + `GET /leads/batches` (verify json).
3. Backend: `/run` `lead_ids` path (verify a 2-id run dials exactly 2).
4. Frontend: swap raw `<select>`→`components/Select` (smallest visible win).
5. Frontend: Tabs + FieldFiles(xlsx) + batch list.
6. Frontend: temperature chips + Range + manual picker table (Customers pattern).
7. Frontend: preview/launch bar wired to `lead_ids`; live-test on panel.famit.in.

Deploy via the standard tar→scp→backup→build→restart recipe for the frontend box;
backend via in-place edit + `systemctl restart` of the uvicorn `caller:app`.
