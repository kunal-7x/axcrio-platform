# RAG W1 — retrieval hardening (dense-gate + _global UNION + query-log RLS)

Wave log per WORKFLOW_LEDGER convention. Each phase appends its tight conclusion.
Scope: kb/core.py + kb/schema.sql + kb/__init__.py + aim_voice_agent.LIVEBOX.py (the
single _kb_retrieve chokepoint). Earner-safe, git-only this wave; box DDL deploys on
the NEXT aim-voice-agent restart via ensure_schema (separate box-mutating step).

## W1 build — DONE (commit 266f2c1 on fe/unify-run-wavec)

**Earner gate (before + after):** agent.py md5 `9150fabe4ff62b4b4470f9a87df346e5` UNCHANGED ·
famit-agent MainPID `1477083` NOT restarted · caller `/health` (127.0.0.1:8208) = 200 ·
0 5xx (last 1h) · NO ring (no calls placed; all box ops read-only / rollback-only).

### (1) dense-gate — kb/core.py
- `retrieve(tenant_id, query, *, top_k, scope, channel, scope_campaign_id, dense=False, include_global=True, is_admin=False)` (core.py:303-305 signature).
- The embed leg is now wrapped in `if dense:` (core.py:336-345). With `dense=False` (the
  reply-path DEFAULT) `embeddings.status()` and `embeddings.embed()` are NEVER called →
  ZERO network. `dense=True` is connect-prefetch-only (W4 grounding_cache).
- Env `KB_INCLUDE_GLOBAL` tunable added (core.py ~:37-39, default ON).

### (2) _global UNION SQL — kb/core.py + kb/schema.sql
- core.py builds `tenant_sql = " AND (tenant_id = :selftid OR tenant_id = '_global')"`
  (core.py ~:354-365), appended to BOTH legs' WHERE: sparse FTS (core.py ~:375-383) and
  dense (core.py ~:390-398). Explicit predicate, `selftid` bound to the caller's tenant,
  run under `is_admin=False`. **No `%` wildcard, never is_admin=True on a voice read.**
- For the predicate to surface `_global` under is_admin=False, the RLS USING policy must
  permit it: schema.sql kb_chunks / kb_sources / kb_documents USING now adds
  `OR tenant_id = '_global'` (read-shared); **WITH CHECK omits it (write-locked)** — a
  tenant request path can NEVER insert/update a `_global` row.
- `include_global=False` (or `KB_INCLUDE_GLOBAL=0`) → tenant-only (no `_global` predicate).

### (3) kb_query_log FORCE-RLS + TTL — kb/schema.sql + kb/core.py
- NEW table `kb_query_log` (schema.sql §2d): `ENABLE` + `FORCE ROW LEVEL SECURITY`,
  policy `kb_query_log_isolation` = admin-GUC OR own-tenant (USING+WITH CHECK). **STRICTLY
  per-tenant — NO `_global` read-share** (raw caller queries are the leakiest artifact).
  Indexes: `(tenant_id, grounded, created_at DESC)` for the gap loop + `(created_at)` for TTL.
- core.py `log_query(...)` (best-effort, tenant-scoped, off-hot-path) + `purge_query_log(ttl_days=KB_QUERY_LOG_TTL_DAYS default 90)` (admin-GUC sweep, `DELETE ... WHERE created_at < now() - make_interval(days => :d)`). Both re-exported in kb/__init__.py.

### (4) call-sites — aim_voice_agent.LIVEBOX.py
- All 3 grounding sites (connect-prefetch :2556, pick_campaign re-ground :1718, lookup :1769)
  funnel through the single `_kb_retrieve` chokepoint. That chokepoint's `_kb.retrieve(...)`
  call (LIVEBOX ~:534-536) now passes **`dense=False, include_global=True`** explicitly →
  voice reply path is FTS-only forever. (LIVEBOX golden md5 = box `8335d4ba`, W0-current.)

### Proofs
- **Offline 5/5 PASS** (stubbed db.engine + vendors.embeddings, zero infra): T1 dense=False →
  0 embed calls; T1b FTS rows returned with embedder configured-but-skipped; T2 dense=True →
  embedder touched; T3 explicit `OR tenant_id = '_global'` bound selftid, no `%`, is_admin=False;
  T4 include_global=False → tenant-only; T5 not_configured embedder + dense=False → FTS rows, 0 net.
  (scratch test deleted post-run, not committed.)
- **DDL rollback-validated on the LIVE box DB** (BEGIN…ROLLBACK, zero mutation): parses +
  idempotent (existing tables/indexes skip; kb_query_log + policy + 2 indexes CREATE clean) →
  `PSQL_RC=0`. `make_interval` valid.
- **py_compile** OK (core.py, __init__.py, aim_voice_agent.LIVEBOX.py). **gitleaks** staged = 0
  (+ pre-commit hook clean). kb/ force-added (was gitignored under `droplet_work/`; no secrets,
  per RECOVERY-STATE P3 follow-up).

### Flag-state truth report (verified, NOT flipped — founder rule)
- **CTX_CACHE (W2): DORMANT.** Absent from box `.env`; code default `"0"` (context_store.py:69
  `is_enabled()`=False). W2 code shipped; flag never added to live `.env`. Save path byte-identical.
- **INBOUND_PROV_LOCK (Wave A): DORMANT.** Absent from box `.env`; code default `False`
  (aim_voice_agent.py:2437 `_env_flag("INBOUND_PROV_LOCK", False)`). Provider-lock resolver
  exists but inbound does NOT enforce campaign-pinned provider/voice. Wave A committed "flip to
  1" but it was never written to live `.env`.
  → Both built-but-dormant. Do NOT flip without a dedicated earner-gated restart + proof.

### NOT done this wave (by design / next steps)
- Live RLS cross-tenant probe (act-as A → only A + `_global`, never B) deferred to W2 deploy time
  (needs a real 2nd tenant in DB; offline + rollback proofs stand in for now).
- W2: POST /kb/seed-telecaller + kb/seed_global.py corpus (next wave).

## W1 DEPLOY — DONE (2026-06-14, box 168.144.153.145)

**Files deployed:**
- `kb/core.py` box md5 `7010a77e` (was `3922266f`)
- `kb/__init__.py` box md5 `aa2b7c13` (was `f6ec3720`)
- `kb/schema.sql` box md5 `42c14591` (was `fabd3803`)
- `aim_voice_agent.py` box md5 `5c3936fa` from `aim_voice_agent.LIVEBOX.py` (was `8335d4ba`)

**Backups:** `/opt/famit-agent/kb/*.W1bak.20260614-171333`

**DDL apply (psql -f kb/schema.sql):** kb_sources/kb_documents/kb_chunks policies updated (DROP POLICY + CREATE POLICY); kb_query_log NEW table created + ENABLE+FORCE ROW LEVEL SECURITY + `kb_query_log_isolation` policy + `kb_query_log_tenant_idx` + `kb_query_log_ttl_idx`. No errors, no 5xx.

**DB FORCE-RLS live verify (pg_class):**
- kb_chunks: relrowsecurity=t, relforcerowsecurity=t
- kb_documents: relrowsecurity=t, relforcerowsecurity=t
- kb_query_log: relrowsecurity=t, relforcerowsecurity=t
- kb_sources: relrowsecurity=t, relforcerowsecurity=t
- All 4 isolation policies: `pg_policies` shows policyname + cmd=ALL + permissive=PERMISSIVE

**8/8 offline probes PASS (on box, pre-restart):**
- T1 dense=False default: PASS
- T1b retrieve embed guarded by if dense: PASS
- T2 _global UNION predicate: PASS
- T3 no % wildcard: PASS
- T4 aim_voice_agent call-site params: PASS
- T5 kb_query_log FORCE-RLS: PASS
- T6 WITH CHECK excludes _global (write-locked): PASS
- T7 log_query+purge exported in __init__: PASS

**aim-voice-agent restarted:** old PID 2660527 (W0) → new PID 2669239. active/running.

**Earner gate (post-deploy):**
- agent.py md5: `9150fabe4ff62b4b4470f9a87df346e5` UNCHANGED
- famit-agent PID: `1477083` NOT restarted
- caller /health: 200
- 0 5xx, NO ring

**Flag truth (confirmed absent from .env, NOT flipped):**
- CTX_CACHE (W2): DORMANT — absent from live /opt/famit-agent/.env
- INBOUND_PROV_LOCK (Wave A): DORMANT — absent from live /opt/famit-agent/.env

**NEXT:** W2 — POST /kb/seed-telecaller + kb/seed_global.py corpus (seeding _global shared KB).
