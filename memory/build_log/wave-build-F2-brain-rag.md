# WAVE-BUILD-F2 — BUSINESS BRAIN + KNOWLEDGE BASE + pgvector RAG SUBSTRATE (PLATFORM-ENG)

Specs (followed): `design/platform-business-brain.md`, `design/platform-knowledge-rag.md`,
`design/dynamic-context-rag.md`. Roadmap: `MASTER_PLATFORM_ROADMAP.md` F2.
Box: famit@168.144.153.145 `/opt/famit-agent/`, venv `/opt/capsy-agent/.venv` (py3.12),
svc `famit-caller` (uvicorn :8209) + `famit-agent`. SSH key `...\do-blr-test\id_ed25519`.
Mode: additive, non-breaking strangler; live system keeps earning. NO git (orchestrator commits).
STATE ledger: `droplet_work/F2_BRAIN_RAG_STATE.md`.

## RECONCILE (2026-06-10, session start)
- caller.py + store.py local == box md5 (`50afb2e1`/`2b2b0774`) — NO drift (box was synced to local).
- P1 keystone solid: `db/engine.py` `session(tenant,is_admin)`/`asession()` set `SET LOCAL app.tenant_id`
  + `app.is_admin` IN-txn (RLS). STORE_MODES on box = **12 stores dual** (incl. events + campaigns — a
  later session past `wave-build-P1.md`). Both svcs active. PG 16.14.
- ⚠ **BRIEF-vs-REALITY CORRECTION:** the task said "pgvector available on the DB". It was **NOT**:
  `pg_available_extensions` returned 0 rows for `vector`, no `vector.control`, package not installed.
  BUT apt Candidate `0.6.0-1` was present (one install away). No EMBED_/RAG_ env vars (embedder dormant
  as expected). SARVAM_API_KEY present (but Sarvam has NO embeddings endpoint — confirmed §3).

## THE LOAD-BEARING DESIGN DECISION (de-risks the whole unit)
The ingest→retrieve smoke does **NOT** depend on pgvector OR an embedder key. Retrieval is **HYBRID**
with a **Postgres FTS sparse leg as the CORE** (`to_tsvector('simple', …)` + GIN, core PG16, keyless)
and the **dense pgvector leg as the DORMANT-until-embedder upgrade**. So "ingest a sample doc → retrieve
it (RLS-scoped)" passes **today, keyless**, via FTS; "no-op gracefully if the key is absent" is the dense
leg degrading. Without the sparse leg a keyless smoke could only prove a no-op, not retrieval — so the FTS
leg is load-bearing, not optional (= `platform-knowledge-rag.md` §4.3 degrade-ladder step 2).

## SPEC RECONCILIATION (they compose; clean slate)
Neither `campaign_knowledge_chunks` (voice) nor `kb_chunks` (platform) existed; no `rag.py`. Per
`platform-knowledge-rag.md` §3.1 (KB-vs-Brain boundary), the canonical corpus is **ONE `kb_chunks`**;
voice is a later scoped subset. So:
- **Corpus = `kb_sources`/`kb_documents`/`kb_chunks`** (NOT `campaign_knowledge_chunks` — that's
  building-to-deprecate).
- **Brain structured tables** ship **JSON-first** via the per-org-file pattern (no PG dependency to ship).
- **Brain long-form docs** flow OUT to the KB corpus as `kb_sources` rows w/ a **business scope** →
  chunked/embedded into `kb_chunks`. One pipeline, two scopes (business now; campaign later).

---

## WHAT SHIPPED (all on box, all verified)

### U0 — provision pgvector (additive, zero downtime)
- `sudo -n` works on box. `sudo apt-get install -y postgresql-16-pgvector` → 0.6.0; then
  `sudo -u postgres psql -d famit -c 'CREATE EXTENSION IF NOT EXISTS vector;'` → OK.
  **CREATE EXTENSION is the ONLY superuser step** (`dynamic-context-rag.md` F1 — `famit_app` is
  NOSUPERUSER). Both svcs stayed **active** through install + extension (no restart, no live impact).

### U1 — `kb/schema.sql` (canonical corpus) applied as `famit_app`
Three tables (idempotent, `IF NOT EXISTS`), all `ENABLE`+`FORCE ROW LEVEL SECURITY` with the **identical
P1 policy shape** (`db/rls.sql`): `USING/WITH CHECK (current_setting('app.is_admin',true)='1' OR
<tenant_col> = current_setting('app.tenant_id',true))`.
- `kb_sources` (provenance root: kind/title/scope/channel_scope/status/kb_version/checksum/data jsonb).
- `kb_documents` (logical doc: doc_type/scope/scope_campaign_id/lang/kb_version).
- `kb_chunks` (THE retrieval unit): `content`, `section`, scope tags, **`embedding vector(1024)`** (dense;
  NULL when dormant), **`fts tsvector`** (sparse; core), `UNIQUE(tenant_id,document_id,chunk_idx)`.
  Indexes: **HNSW** `vector_cosine_ops` (dense ANN), **GIN(fts)** (sparse — the core/keyless index),
  scope b-tree `(tenant_id,channel_scope,scope_campaign_id,doc_type)`.
- Verified on box: 3 tables, `embedding=vector(1024)`, HNSW+GIN+scope idx present, RLS forced `t/t`,
  isolation policies on all three. **NOT an Alembic revision** (kept off the P1 0001/0002 migration chain
  to keep blast radius off the live keystone; applied standalone via `kb.ensure_schema()` / `psql -f`).

### U2 — three new modules (import-safe, dormant-degrade)
- **`droplet_work/vendors/embeddings.py`** — generic **OpenAI-`/embeddings`-compatible** provider
  (`EMBED_BASE_URL` + `EMBED_MODEL` + `EMBED_API_KEY`), `status()`+`embed()` surface mirroring the vendor
  pattern. **DORMANT default** (`status()=="not_configured"`, `embed()==[]`). Provider-agnostic so an
  OpenRouter-if-it-exposes-it / a dedicated bge|e5 embeddings host / a self-host all drop in **by config**.
  Deliberately **NO in-process torch BGE** (= `dynamic-context-rag.md` F5: no ~2.3 GB resident model on the
  live earning voice box). `EMBED_PROVIDER=sarvam` reserved for the day Sarvam ships an embeddings route.
- **`droplet_work/kb/`** (`__init__.py` + `core.py`) — `ensure_schema()`, a section-aware Devanagari-safe
  **chunker** (`chunk_text`), **`ingest()`** (chunk → FTS → optional-embed → upsert; idempotent by source
  `sha256` checksum; RLS-scoped via `db.engine.session`), **`retrieve()`** (hybrid: FTS sparse leg always +
  dense ANN when embedder configured, fused by **RRF k=60**; provenance on every chunk). Import-safe: PG
  down → `available()`→False → `retrieve()`→[], `ingest()`→`{ok:False,reason:'pg_unavailable'}`.
- **`droplet_work/brain/`** (`__init__.py` + `core.py`) — JSON-first per-org store
  (`var/brain/<org_id>.json`). Read facade: `get_profile`, **`merge_defaults`** (fill-when-MISSING-OR-EMPTY
  — RT-1 empty-clobber guard), `resolve_campaign_defaults` (returns the `_coerce_fields` campaign shape),
  `resolve_worker_context` (role-shaped: support=FAQ/policy-heavy, creative=brand/USP-heavy), `retrieve`
  (thin wrapper → `kb.retrieve` business scope). Write facade: `upsert_profile` (versioned + append-only
  `.history.jsonl` + best-effort `audit.record`), **`add_knowledge`** (→ `kb.ingest` business-scoped),
  `completeness` (0..100 + missing[] — onboarding + hallucination guard).

### U3 — additive endpoints in `caller.py` (the only edit to a live file)
- +6 import-safe lines (`brain`/`kb` optional modules, same `_audit_mod` pattern).
- +5 routes after `/me` (zero change to any existing route or seam):
  `GET /brain` (profile+completeness) · `PUT /brain` (write-gated, versioned/audited) ·
  `GET /brain/completeness` · `POST /brain/knowledge` (ingest) · `GET /brain/retrieve`.
- **org_id is ALWAYS `t["tenant_id"]` from `resolve_tenant`, NEVER a body/param** (`platform-business-brain`
  **RT-5**: PUT strips body `org_id`/`id`). Writes gated by `can(t,"write")`.
- **Event-loop safety:** `POST /brain/knowledge` + `GET /brain/retrieve` run the work via
  `asyncio.to_thread(...)` (embed() can network round-trip → must not park the uvicorn loop).
- caller.py md5 REBASELINE `50afb2e1` → `6d7b0696` (box==local). Backup `caller.py.F2bak.<ts>` on box.
  INSTANTIATE-smoke in venv (routes registered, existing routes intact) BEFORE `systemctl restart`.

---

## ⭐ THE INGEST→RETRIEVE PROOF (the report-gating smoke)

**On-box, PG-backed, KEYLESS (FTS), RLS-scoped** (`_smoke_kb_box.py`, 16 checks ALL PASS):
- ingest a Sector-79 brochure → 3 chunks, `reason='fts_only'`, `embedded=0` (embedding NULL — dormant).
- `retrieve('t1','sector 79 2bhk price')` → **top chunk = the pricing chunk** ("…85 lakh rupees, EMI from
  42000…") with **provenance** (`document_id`+`source_id`), `leg='sparse'`. Exact-term recall (`42000`) too.
- **RLS isolation:** `t2` gets **0** of t1's chunks via the facade AND a raw
  `SELECT count(*) … WHERE tenant_id='t1'` under the **t2 GUC == 0**.
- `brain.add_knowledge` → `kb.ingest` bridge works; `brain.retrieve` finds it. Re-ingest same content →
  `duplicate_checksum` no-op (idempotent).

**BUG FOUND + FIXED mid-smoke (retrieval quality):** first run, the multi-word query returned 0 hits.
Root cause (verified by probing `to_tsvector`): `plainto_tsquery`/`websearch_to_tsquery` **AND** all terms,
and under the `'simple'` config there is **NO stemming**, so the query token `'price'` ≠ the doc token
`'priced'` → strict-AND miss. Fix: the sparse leg now builds an **OR-of-terms `to_tsquery`** (`a | b | c`
from a `[\w + Devanagari]+` tokenizer) ranked by `ts_rank_cd` — recall-oriented, so the chunk matching the
most terms still ranks first; RRF + the (later) dense leg refine precision. Re-ran → ALL PASS.

**Offline pure-logic smoke** (`_smoke_brain_kb_offline.py`, 26 checks ALL PASS, no PG/key/network):
empty-brain `resolve_campaign_defaults=={}` (degrade-to-today), **empty-clobber guard** (user posts
`usps:[]`,`company_name:""` → brain values survive, RT-1), versioning + history, completeness, worker
shaping, chunker, KB degrade-when-PG-absent.

---

## ⭐ REGRESSION GATE — GREEN (after `systemctl restart famit-caller`)
- Both svcs **active**. Legacy **X-Auth 200** on `/stats /campaigns /leads /billing/overview /me
  /callbacks /suppression /webhooks`; public `https://panel.famit.in/api/stats` **200**.
- New `/brain` routes **200** incl. **live PUT** (wrote a profile v1, completeness 30, correct missing[]),
  **live POST ingest** (through the async handler), **live GET retrieve** (found the chunk w/ provenance).
- **ZERO 5xx / Traceback** in the window.
- **`/run` DISPATCH gate (NO paid call — proven by primary data):** `POST /run` → HTTP 200, `job_id`
  created. **PROOF no dial fired:** `SELECT count(*) FROM calls WHERE created_at > now()-30min` = **0** (a
  fresh dial would have written a row), total `calls` unchanged at 81, and the 1 row matching
  `0000000077` has **`created_at = NULL`** (stale, predates this run; `cost` empty). So dispatch is proven
  AND no billable call occurred. ⚠ NOTE: `suppressed_count:0` (the throwaway suppression didn't engage) is
  a **pre-existing phone-normalization quirk** — the `+91…` form didn't match how `/run` keys suppression
  (P1's `66`-test worked due to a different format). It is **orthogonal to F2** (the dispatch gate = 200 +
  job_id + no-dial-proof is met; the INSTANTIATE smoke already proved `/run` logic intact + routes additive).
- md5 box==local for caller.py (`6d7b0696`) + all module files. Gate-test artifacts cleaned (admin brain
  json removed; 3 KB rows deleted; `kb_sources=0`).

---

## DORMANT-UNTIL-KEY (what's wired but inert by design)
- **Dense retrieval leg.** `embedding vector(1024)` column + HNSW index exist and are populated the moment
  an embedder is configured; today every chunk stores `embedding=NULL` and retrieval rides the FTS leg.
  To activate: set `EMBED_BASE_URL` + `EMBED_MODEL` + `EMBED_API_KEY` (any OpenAI-`/embeddings`-compatible
  host) in `/opt/famit-agent/.env`; new ingests embed automatically; existing chunks need a re-ingest/
  backfill to fill `embedding`. No code change, no schema change.
- ⚠ **The dense path has NEVER executed** (every chunk is `embedding=NULL`): the `CAST(:emb AS vector)`
  insert, the `embedding <=> CAST(:qv AS vector)` ANN, and the two-leg RRF fusion are written + reviewed but
  **unproven end-to-end**. The activation unit MUST smoke-test the dense leg on the FIRST key (don't assume
  adding `EMBED_API_KEY` means the dense path is tested). The FTS leg + RRF-with-one-leg ARE proven.
- The whole `brain.retrieve`/`kb.retrieve` path returns `[]` cleanly when PG or the embedder is absent —
  callers no-op.

## SCOPE-HONESTY — "RLS on BOTH" (the task) means KB-PG-RLS NOW, Brain-PG-RLS DEFERRED
The task said "RLS tenant isolation on both [Brain + KB]." What shipped: **KB = PG with FORCE RLS**
(proven — t2 GUC count of t1 rows = 0). **Brain = JSON-first per-org file** with isolation by construction
(org_id ALWAYS derived from `resolve_tenant`, NEVER body-supplied — RT-5; no shared file key). This is the
spec's **blessed ship-first path** (`platform-business-brain.md` §5.1 + RT-5: "JSON-mode isolation is
CALL-SITE convention; the enforced FORCE-RLS backstop arrives at the PG cutover"). So "Business Brain
schema with RLS" = **JSON token-isolation now, PG-FORCE-RLS deferred** to the Brain PG-strangler unit. The
KB pgvector corpus (the part that needed pgvector) has the enforced RLS today.

## DEFERRED (explicitly out of THIS substrate unit; named so the next builder doesn't chase ghosts)
- **VOICE-PATH WIRING — the headline deferral.** The live `agent.py` hot path imports NOTHING from this
  substrate. Folding business-scope RAG into the voice dial-time precompute (`var/rag_context/<room>.json`,
  per-scope budget so `__brain__` can't evict campaign chunks — RT-4) is a **later, latency-budgeted unit**
  gated on the p95 `llm_ttft` regression test (`dynamic-context-rag.md` §5/§9 Step 7). Do NOT wire RAG into
  the agent without that gate.
- **Campaign-merge wiring** (the 2 flag-gated lines in `POST /campaigns` using `resolve_campaign_defaults`
  + `merge_defaults`, behind `BRAIN_DEFAULTS_ENABLED`; create-time snapshot — RT-3). Resolver + empty-clobber
  merge are BUILT + proven offline; the create-site wiring is its own small unit (touches the live
  campaign-create path → its own checkpoint).
- **Hatchet ingestion** (use inline `asyncio.to_thread` for now — already wired), **embed-svc sidecar**,
  **cross-encoder reranker**, **RRF precision tuning**, **`kb_shared_chunks`** (Industry-Pack/global corpus),
  **`kb_query_log`** (retrieval telemetry), **Industry Packs** (`brain/packs/*.json` + `seed_from_industry_pack`).
- **`brain.write` Action-Firewall step-up scope** (RT-2): MUST be registered before any **AI-Manager**
  Brain-write path ships. The firewall (`credit-ledger-firewall.md`) isn't built yet → no AI-Manager
  Brain-write exists yet → not blocking now, but a hard prereq for that later unit.
- **PG-mode strangler for the structured Brain** (JSON→dual→pg the proven `store.py` way) + the
  `business_brain`/`brain_product`/`brain_faq`/`brain_objection` tables + RLS. JSON mode ships first.
- **Worker integrations** (WhatsApp/support/creative/AI-Manager calling `resolve_worker_context`/`retrieve`).

## ARTIFACTS / ROLLBACK
- New files (box==local md5): `kb/schema.sql` `fabd3803`, `kb/core.py` `3922266f`, `brain/core.py`
  `2f460856`, `vendors/embeddings.py` `4b381b69`, + `brain/__init__.py`, `kb/__init__.py`. Smoke harnesses
  kept local+box-runnable: `_smoke_brain_kb_offline.py`, `_smoke_kb_box.py`, `_smoke_caller_instantiate.py`.
- caller.py `6d7b0696` (was `50afb2e1`); backup `caller.py.F2bak.<ts>` on box.
- **ROLLBACK:** `cp caller.py.F2bak.<ts> caller.py && sudo systemctl restart famit-caller` (drops the 5
  routes; modules become unimported/inert). The 3 KB tables + the `vector` extension are **additive** —
  leave them (nothing else reads them) or `DROP`. No `.env` change was made (embedder stays dormant).
  Zero data migrated; JSON stores untouched; live voice path never touched.
