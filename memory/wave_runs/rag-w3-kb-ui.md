
## W3-BACKEND — KB management endpoints (caller.py)

IN PROGRESS — DO BACKEND. Earner gate baseline: agent.py md5 9150fabe4ff62b4b4470f9a87df346e5 UNCHANGED;
famit-agent MainPID=1477083; caller (uvicorn pid 2679442, port 8209) /health=200; 0 5xx; NO ring.
Box dir = /opt/famit-agent (WorkingDirectory; uvicorn binary lives in /opt/capsy-agent/.venv).
Goldens pulled: caller.py.LIVEBOX be3a68a26bc12c1eaee1a12dee4a2e77, kb/core.py.LIVEBOX,
kb/__init__.py.LIVEBOX, kb/schema.sql.LIVEBOX (42c14591).
Building 4 token-derived, RLS (is_admin=False) endpoints after /kb/seed-telecaller (caller.py:3346):
GET /kb/sources, POST /kb/upload (text|PDF via pypdf graceful-degrade), POST /kb/test-retrieve, GET /kb/gaps.

### DONE+DEPLOYED (2026-06-14)
4 KB-management endpoints added to caller.py (after /kb/seed-telecaller), all token-derived + RLS
(engine.session(tenant_id=t["tenant_id"], is_admin=False)), all heavy work via asyncio.to_thread:

- **GET /kb/sources** (caller.py ~3382) — lists this tenant's kb_sources + shared `_global`, each with
  live chunk count (subquery on kb_chunks), status, kb_version, is_shared flag; optional
  ?scope_campaign_id filter. Read-only. Returns {sources:[...], total, global_count}.
- **POST /kb/upload** (caller.py ~3447) — multipart: text=Form OR pdf=File. PDF parsed via pypdf
  (pure-python, INSTALLED into /opt/capsy-agent/.venv; graceful-degrade -> reason pdf_parser_unavailable
  if absent, never 500). Size guards (PDF 20MB, text 200k chars), %PDF sniff, 300-page cap.
  Chunks+FTS+upserts via kb.ingest under tenant GUC (is_admin=False -> RLS WITH CHECK pins write to
  tenant; `_global` write impossible). Optional scope_campaign_id -> scope='campaign:<id>'. write-gated
  (can(t,"write")); audited. Returns {ok, source_id, document_id, chunks, embedded, reason, title}.
- **POST /kb/test-retrieve** (caller.py ~3550) — body {query, channel?, campaign?, top_k?}. Runs
  kb.retrieve(dense=False, include_global=True) — SAME FTS-only path the live voice `lookup` uses (C-3:
  ZERO embed RTT). Returns the firing chunks {id(=source_id), source_id, document_id, section, snippet
  (280c), score, leg} + grounded flag. Also kb.log_query(grounded=...) so the gap loop learns from probes.
- **GET /kb/gaps** (caller.py ~3620) — ?days=&limit=. Aggregates kb_query_log WHERE grounded=false
  (STRICTLY per-tenant, no `_global` share) grouped by lower(btrim(query)) -> {gaps:[{query,count,
  last_seen,channels}], total, window_days}. "Questions your AI couldn't answer."

DEPLOY: box /opt/famit-agent (WorkingDirectory). Backup caller.py.W3bak.20260614-124353. pypdf 6.13.2
installed into caller venv. scp + md5-gate (local==box 52c59291584d948e258d264cd50206ae) + box py_compile
OK. Atomic swap. famit-caller restarted ONLY (MainPID 2685432). NOT famit-agent.

VERIFY: all 4 routes 401-unauth (mounted, not 404). Authed (admin via CALLER_PASS) E2E PASS:
sources lists tenant+_global w/ chunk counts; upload text -> ok 1 chunk fts_only; test-retrieve
"registration charge" -> grounded true 6 chunks (sparse); true no-hit "zxqwvbbb" -> grounded false ->
appears in /kb/gaps (count 1). Smoke data cleaned (1 source/doc/chunk + 3 qlog rows deleted under admin GUC).

EARNER GATE: agent.py md5 9150fabe4ff62b4b4470f9a87df346e5 UNCHANGED; famit-agent MainPID 1477083
NOT restarted; caller /health 200; 0 5xx; NO ring (DID resting, no calls placed).

ROLLBACK: cp caller.py.W3bak.20260614-124353 -> caller.py + restart famit-caller. (pypdf install is
additive/harmless; routes degrade to 503 if kb absent.)

## W3-FRONTEND — /knowledge KB management UI (famit-panel)

### DONE (2026-06-14) commit 5275473 on fe/unify-run-wavec

3 new files:
  famit-panel/app/knowledge/_lib.ts   — typed API client (getKbSources, uploadKbText, uploadKbPdf,
                                         testRetrieve, getKbGaps); X-Auth JWT; handle401 redirect;
                                         dormant-safe (every call has its own error state, never throws
                                         into a blank screen).
  famit-panel/app/knowledge/page.tsx  — "use client" 3-tab page: Sources / Test Answers / Knowledge Gaps.
  famit-panel/contstants/navigation.tsx — "Knowledge Base" → /knowledge added under Intelligence section.

UX summary (5 lines):
  1. Sources tab: lists tenant sources + shared _global sources (chunk count, status badge, kind icon);
     Upload card toggles between text-paste and PDF-file upload with optional campaign scope.
  2. Test Answers tab: founder types a question → POST /kb/test-retrieve → renders each chunk that fires
     with BM25 score visualized as a progress bar + snippet; grounded/not-grounded verdict banner in green/red.
  3. Knowledge Gaps tab: GET /kb/gaps with 7/30/90-day window picker via Card's built-in selectOptions;
     gap rows show ask-count (red), last-seen, channel badges, hover clipboard action.
  4. All sections are dormant-safe: loading skeletons + calm empty states (no error walls, no blank screens).
  5. All icons from the Core_2 icon set; zero raw hex; Inter Display via Tailwind `font-inter`; token-only classes.

Build: tsc --noEmit = 0 errors; npm run build = green; /knowledge listed at 5.57 kB.
gitleaks = 0 leaks. Earner gate: agent.py + famit-agent untouched (frontend-only commit).

## W3-DEPLOY — FORTRESS panel deploy (2026-06-14)

LOCAL BUILD: npm run build EXIT 0. BUILD_ID = YV9obkLRRD0U5oX-CPOCH.

DEPLOY METHOD: prebuilt .next artifacts (no cache, 4MB tgz) + 3 source files shipped via scp → atomic swap on FORTRESS box 143.110.247.249. On-box npm build SIGKILL'd twice (OOM-transient on 1.9GB box); switched to local-build-ship-artifacts strategy (pattern from wave-build-REC-C-recordings-api.md).

BOX STEPS:
1. Backup /opt/famit-panel/.next → /opt/famit-panel/.next.W3bak.20260614-133740
2. Extracted fp_next.tgz (4MB, .next excl cache + 3 source files)
3. Atomic rm -rf .next && mv staged/.next /opt/famit-panel/.next
4. Source files: app/knowledge/_lib.ts, app/knowledge/page.tsx, contstants/navigation.tsx installed
5. chown -R deployuser:deployuser /opt/famit-panel
6. systemctl restart famit-panel → active

VERIFY (loopback:3001): /login:200 /knowledge:200 /run:200 /crm:200
VERIFY (CF edge panel.famit.in): /login:200 /knowledge:200 /run:200 /crm:200 /ai-manager:200 /workflows:200
CONTENT: "Knowledge Base" + BUILD_ID YV9obkLRRD0U5oX-CPOCH confirmed in live HTML.

KB BACKEND (unchanged from W3-backend deploy): /kb/sources:401 /kb/test-retrieve:401 (mounted, auth-gated). famit-caller: active.

EARNER GATE: agent.py md5=9150fabe UNCHANGED · famit-agent PID=1477083 NOT restarted · /health=200 · famit-caller active · 0 5xx · NO ring (NO calls placed).

ROLLBACK: cp -a /opt/famit-panel/.next.W3bak.20260614-133740 /opt/famit-panel/.next && systemctl restart famit-panel.

RAG IS NOW FEATURE-COMPLETE-FOR-NOW. NEXT PRODUCT = VIDEO STUDIO.
