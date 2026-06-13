# WAVE — APP PERFORMANCE OVERHAUL — UNIT 7 INTEGRATED VERIFY (2026-06-14)

> Founder's #1 pain: every tab/click took 10-20s, pages loaded EVERYTHING at once, no caching.
> 7-unit perf wave (plan = `design/latency-diagnosis-v2-PERF-PLAN.md`). Units 1-6 shipped live across
> the earner box (caller.py only) + FORTRESS panel + FORTRESS nginx. UNIT 7 = honest integrated re-verify
> over REAL HTTP (no ring — DID resting per HARD RULE). RESULT: **6/6 units PASS**.

## EARNER GATE (before + after verification) — PASS
- agent.py md5 `9150fabe4ff62b4b4470f9a87df346e5` UNCHANGED (both checks)
- famit-agent MainPID `1477083` / ActiveEnter `2026-06-10 19:58:18 UTC` NEVER restarted
- famit-agent / famit-caller / famit-aiasset all `active`; caller `/health`=200; **0 5xx** in caller logs
- famit-panel current MainPID `256634` / ActiveEnter `2026-06-13 20:17:55 UTC`; **0 errors since that start**
  (the 7 journal "error" lines are all STALE — older PIDs 132222/169243/188199/239673, Jun 12-13, pre-deploy)
- NO `/run`, NO outbound call placed. Only read-only HTTP probes.

## PER-UNIT VERIFY (live, over real HTTP)

### UNIT-1 — backend pagination + payload trim + N+1 fix — PASS
- `/calls?limit=200` (legacy) → `{calls,total:264,offset,limit,next:200}` with FULL rows
  (recording_key/room/sip_call_id/_reconciled present) → backward-compatible.
- `/calls?order=desc&limit=5&offset=0&slim=1` → SLIM 12-field rows
  `{answered,campaign_id,campaign_name,duration_s,ended_at,id,interest,name,outcome,phone,started_at,status}`,
  newest-first, `next:5`. `offset=260` → `next:null`, 4 rows returned (last page).
- `/leads` legacy → `{leads,total:8,next:null}` (all 8); `/leads?limit=3&offset=0` → `next:3`.
- `outcome=voicemail` → `total:178` with NO per-row transcript reads (fast).

### UNIT-2 — CRM detail speedup + recordings playable-flag — PASS
- `/contacts/+918949906361/recordings` → `{recordings,total,with_recording:2,with_playable:2}`;
  real 58244B + 56916B OGGs → `playable:true` + URL set; the 0-byte (486-busy/near-empty) items →
  `playable:false` + NO url. (No more timer-with-no-sound.)
- CRM detail repeat-open: 68ms → 41ms → 41ms (TTL-gated rebuild). Response `{contact,timeline,nba}`;
  `_timeline` does NOT leak.

### UNIT-3 — FE react-query cache + skeletons — PASS (source + live)
- `lib/query-client.ts`: `staleTime 30_000`, `gcTime 5*60_000`, `refetchOnWindowFocus:false`
  (stale-while-revalidate → tab-back is a cache HIT, no full re-fetch).
- `app/providers.tsx` wraps `{children}` in `app/layout.tsx`. `lib/queries.ts` consumed by
  calls/campaigns/leads/dashboard pages. react-query present in box node_modules.

### UNIT-4 — FE infinite-scroll + row virtualization — PASS (source)
- `components/VirtualRows/index.tsx` (`useVirtualizer`) consumed by `app/calls/page.tsx` +
  `app/leads/page.tsx`. react-virtual present in box node_modules.

### UNIT-5 — FE code-split + prefetch + transcript L/R — PASS (source + live)
- `next/dynamic(ssr:false)` for @xyflow WorkflowEditor/MiniMap (`app/workflows/page.tsx`) + WebGL
  Aurora GenerationLoader (3 consumers: BannerStep/TemplatesStep/GenerationQueue) → off the global bundle.
- `components/NavLink/index.tsx`: `router.prefetch` on `onMouseEnter`/`onFocus`, once-per-mount, skips
  active link, best-effort try/catch.
- `app/calls/page.tsx` transcript: `customer|user|caller|lead` → RIGHT, AI → LEFT (mirrors CRM ChatBubble).

### UNIT-6 — EDGE (FORTRESS nginx) — PASS (live, measured)
- `/api/calls?limit=100&order=desc&slim=1`: `Accept-Encoding: gzip` → `Content-Encoding: gzip` +
  `Vary: Accept-Encoding`, **27425 → 2746 bytes on the wire = 90.0% reduction (10x)**;
  `Accept-Encoding: identity` → full 27425 (correct negotiation).
- `_next/static/chunks/*.js` → `Cache-Control: public, max-age=31536000, immutable` + `Cf-Cache-Status: HIT`.
- analytics 30s poll gated on `document.visibilityState` (`app/analytics/page.tsx`).

## LIVE STATE
- Box BUILD_ID `p6hSTJX9R46-NQdLf8Daw`; 200 on `/ /login /calls /crm /run /ai-manager /analytics`
  on BOTH loopback:3001 AND the panel.famit.in edge.
- Commits in history: `dfb663f` `7562913` `40caf3c` `0c28c76` `d42d130` `7068bd7` `d48ed46` `f6271e1` `c030ee4`.

## RESIDUAL (deferred, not blocking)
- **P7 (stretch) — selective RSC/streaming** on the heaviest read-only pages (analytics/dashboards) with
  per-widget Suspense. Larger refactor; explicitly deferred. All 6 shipped units cover R1-R6.
- Brotli is NOT in this nginx build (gzip only) — recompiling a hardened box is too risky; gzip already
  gives the 90% win.

## FOUNDER RECIPE (dead simple)
Open `panel.famit.in` →
1. Click between tabs (Calls → CRM → Run → AI Manager → back to Calls). The first visit loads; clicking
   BACK to a tab you've seen is now INSTANT (served from cache) instead of the old 10-20s reload.
2. Open Call Logs and scroll. It loads a page at a time and keeps scrolling smoothly — it no longer freezes
   trying to load every call at once.
3. Open a lead in CRM, click a recording. If it's a real recording it PLAYS; a broken/empty one shows
   "preparing" instead of a timer that ticks with no sound.
4. Open a call's transcript: the AI's lines are on the LEFT, the customer's on the RIGHT (no longer all
   on one side / "anonymous").
