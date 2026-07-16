# PERF DIAGNOSIS + MULTI-PHASE OPTIMIZATION PLAN (READ-ONLY, 2026-06-14)

> Founder's #1 pain: the WHOLE app (panel.famit.in) is slow — every tab/click 10-20s,
> pages load EVERYTHING at once (call logs load all rows, no pagination). Evidence-based,
> no edits made. Earner box `168.144.153.145` / `agent.py` md5 `9150fabe…` NEVER touched.
> Panel = FORTRESS `143.110.247.249`; caller.py port 8209 over VPC 10.122.0.4.

## RANKED ROOT CAUSES (with evidence)

### R1 — NO client caching layer; every navigation re-fetches from scratch (BIGGEST)
- `famit-panel/package.json` has **no SWR / react-query / @tanstack** dependency. Subagent grep across `app/` + `lib/` = 0 imports. Only `cache:` directive anywhere is `cache:"no-store"` (lib/api.ts:174, entitlements).
- Every page fetches in a mount `useEffect`; switching tabs and coming back = full uncached re-fetch. CRM list/detail refetch on every filter/tab change (crm/page.tsx:69 keyed `[stage,hotOnly,segmentId]`; crm/[id]/page.tsx:125 keyed `[id,kind,detail]`).
- Edge confirms it can't be cached: `Cf-Cache-Status: DYNAMIC`, `Cache-Control: private,no-cache,no-store` on `/`.

### R2 — All 53 pages are `'use client'`; zero RSC/streaming; nothing code-split
- Subagent: **53/53 `page.tsx` start with `'use client'`**. `next/dynamic` used **0 times**. So the browser downloads JS, hydrates, THEN starts fetching — classic client-render waterfall, blank/frozen until the fetch returns.
- Heavy deps statically bundled (not split): `@xyflow/react` (workflows/_editor.tsx:38), `@tiptap` ×5 (components/Editor/index.tsx:1-5), recharts (components/CardChartPie), framer-motion + WebGL Aurora (components/GenerationLoader). Aurora is NOT global (good) — scoped to creative/whatsapp steps — but it's static-imported into those bundles.

### R3 — List endpoints return unbounded / first-N-only payloads, no real pagination
- **`getLeads()` sends NO limit → loads ALL leads** (lib/api.ts:487-499). Hit on leads/page.tsx:56, run/page.tsx:123, crm/page.tsx:56.
- **`getCalls()` → `/calls?limit=200`** hard cap, no offset, no `total` (lib/api.ts:625). Backend `/calls` (caller.py:4193) returns `rows[:limit]` with NO `total`, NO offset → real pagination/infinite-scroll is impossible without a backend change.
- `getCampaigns()` / `getVoices()` no limit (api.ts:438, 667).

### R4 — Backend `/calls` reads the WHOLE call history into RAM + O(N) Python scans (scales badly)
- `CALLS: list = _read(CALLS_FILE, [])` (caller.py:1062) — entire `var/calls.json` loaded at startup into a module list.
- `/calls` filters via Python list-comprehensions (`calls_for` caller.py:1283) then slices. `/calls/{id}` does a linear `next()` scan (caller.py:4219). Lead-stitch loops ALL CALLS (caller.py:1824).
- `outcome` filter = N+1 per-row transcript file read `_read(TRANSCRIPT_DIR/{room}.json)` (caller.py:4206).
- Calls are JSON-file-backed (not a queryable indexed table) → every list/filter gets slower as volume grows.

### R5 — CRM lead-detail open is expensive: rebuild + 3 serial DB hits per open
- `/contacts/{phone}` (caller.py:3039) runs `project_contact` → `rebuild_timeline` (full rebuild from leads+calls+wa) → `get_timeline(500)` → then the route also calls `get_timeline(50)` + `next_best_action`, all serial (crm/core.py:335, 354; caller.py:3056-3057). Multiple PG round-trips + a full timeline rebuild on EVERY lead click.
- (The CRM **list** `list_contacts` IS properly paginated — PG `LIMIT` + `total`, RLS-indexed, caller.py:3032 / core.py:423. The list is fine; the **detail rebuild** is the slow one.)

### R6 — EDGE: no gzip/brotli on the /api proxy; no proxy caching; analytics 30s poll
- nginx panel config (fortress/nginx-panel.conf) has **no `gzip`/`brotli` directive** and **no `proxy_cache`** on `location /api/`. HTML is brotli'd by Cloudflare, but large API JSON travels uncompressed origin→edge. (Cloudflare may gzip on the way to the browser, but origin→CF and the un-cacheable dynamic JSON are the cost.)
- `app/analytics/page.tsx:67-70` `setInterval(load,30000)` with no visibility gate; `app/run/page.tsx:157-175` polls getStatus every 3s. Background drain.
- Backend reject RTT is fine: `/api/calls` 401 round-trips ~0.29-0.55s through the edge → slowness is payload + re-fetch, not raw network latency.

## MULTI-PHASE OPTIMIZATION PLAN (impact-first, each a buildable wave)
> SAFE: panel (FORTRESS box) + caller.py/ai_asset (earner box, caller-only) — NEVER agent.py.
> SEQUENCES AFTER the running Model/Voice-switcher wave (shares panel + caller.py — no stacking).

- **Phase 1 — React-Query cache + skeletons (panel-only, biggest perceived win).** Add `@tanstack/react-query`, wrap providers, convert every list/detail fetch to `useQuery` with `staleTime` (e.g. 30-60s) + keep-previous-data. Effect: tab→back is INSTANT (served from cache, revalidate in bg = stale-while-revalidate). Add dimension-matched skeletons so first paint is never blank. No backend change. Highest ROI.
- **Phase 2 — Server pagination + keyset on /calls + virtualized lists (backend + panel).** caller.py: add `offset`/keyset (`before_id`/cursor) + `total` to `/calls` (and `/leads`); ai_asset already paginates. Panel: infinite-scroll/"load more" + react-window/virtua virtualization on call-logs, leads, CRM list so only ~30 rows mount at once. Effect: call logs stop loading everything; large lists scroll at 60fps.
- **Phase 3 — Code-split heavy components (panel-only).** `next/dynamic` (ssr:false) the workflow editor (@xyflow), the @tiptap Editor, recharts cards, and the Aurora/GenerationLoader; prefetch the import on hover/focus for high-probability clicks. Shrinks the main bundle → faster hydrate/first-interaction.
- **Phase 4 — CRM lead-detail speedup (backend caller-only).** Make `rebuild_timeline` lazy/cached (rebuild on write, not on every read) + run the detail's 3 reads in parallel (asyncio.gather) instead of serial; add a short per-contact projection cache. Cuts the lead-open from multi-roundtrip to one fast read.
- **Phase 5 — Backend calls store → indexed/queryable + payload trimming (backend caller-only).** Stop O(N) RAM scans: index calls by tenant/id; trim list payloads to the fields the table needs (drop heavy transcript/meta from list rows; fetch on row-open). Drop the N+1 transcript read on the `outcome` filter (precompute outcome onto the row).
- **Phase 6 — Edge/transport (FORTRESS nginx, needs FE-box root).** Add `gzip`/`brotli` on the `/api/` proxy in nginx-panel.conf; set sane `Cache-Control` for static `_next/*`; gate the analytics 30s poll on `document.visibilityState` + back off run-status poll. Cheap, safe, real bytes saved.
- **Phase 7 (stretch) — Selective RSC/streaming.** Convert the heaviest read-only pages (analytics, dashboards) to server components with per-widget Suspense streaming so each panel fills in independently behind a skeleton. Larger refactor; do last.

## TWO QUICK FRONTEND FIXES to fold into the next panel wave
- **(a) CRM lead-recordings player = timer runs, NO AUDIO.** Both players are identical markup (`<audio controls preload="none" src={url}>` — AIM sessions/[id]/page.tsx:282-285 vs CRM crm/[id]/page.tsx:617-620). The CRM mapper DOES map the URL (client.ts:359 `firstUrl("url","presigned_url","recording_presigned_url","recording_url")`, backend field is `recording_presigned_url`). So it's NOT a missing-URL bug. ROOT CAUSE: the AIM player only ever plays an INBOUND session that went through REC-A finalize-on-read (always a terminal, fully-uploaded OGG). The CRM list also serves OUTBOUND items from the JSON CALLS store (REC-B auto-egress) whose object may not have fully landed (or is a brief `486 Busy` near-empty OGG) — duration shows from `recording_duration_s` but the bytes 404/aren't decodable → timer advances, no audio. FIX: in `/contacts/{phone}/recordings` apply the same finalize/HEAD-verify-object-exists-and-nonzero before presigning outbound items, and only render `<audio>` when a verified playable object exists (else "preparing"). (Backend caller-only.)
- **(b) CALL-LOGS transcript looks "anonymous".** calls/page.tsx:282-314 ALREADY has bubbles + L/R alignment, BUT it keys on `turn.role === "agent"` only (line 283-284). The backend `/calls/{call_id}/transcript` normalizes roles to **`ai`** / **`customer`** → `=== "agent"` is never true → EVERY turn falls to the else branch (right, "L" avatar) = all same side = anonymous. FIX (keep the existing window UI): map roles like CRM's ChatBubble — `ai|assistant|agent` → LEFT (`bg-b-surface2`, "AI" label), `customer|user|caller|lead` → RIGHT (`bg-primary-01/12`, "Customer"/lead-name label). Frontend-only.

## SAFETY + SEQUENCING
- All phases touch ONLY the panel (FORTRESS) and caller.py/ai_asset (caller-only). agent.py / trunks / firewall / SIP UNTOUCHED. No outbound test calls (DID resting). Earner-gated by md5 + process + /health, never a ring.
- MUST sequence AFTER the running Model/Voice-switcher wave — it edits the same panel + caller.py; do not stack two box-mutating waves on shared files.
