
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
