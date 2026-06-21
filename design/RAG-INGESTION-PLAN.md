# 📚 RAG-INGESTION-PLAN — Corpus Build for the Voice-Brain RAG (W4-RAG)

> **What this is:** the corpus-build half of W4-RAG. The retrieval path is already wired and live
> (`RAG-MASTER-PLAN.md` §0) — it is inert because `kb_chunks` has 0 rows. This plan specifies HOW the
> corpus gets filled: (1) the shared `_global` telecaller-behaviour corpus, (2) the per-tenant product
> collateral ingestion pipeline (paste/PDF/DOCX/URL → chunk → FTS → optional-embed → upsert), (3)
> freshness/reindex, (4) observability. Earner-safe, RLS-isolated, cost-real, idempotent.
>
> **Status:** READY TO BUILD (design only). Companion to `RAG-MASTER-PLAN.md` + `RAG-EVAL-SPEC.md`.
> **Grounded in LIVE source:** `kb/core.py` (`ingest`/`chunk_text`/`retrieve`), `kb/schema.sql` (3
> tables, FORCE-RLS, vector provisioned 2026-06-10), `caller.py:3293` (`/brain/knowledge`).
> 2026-06-14.

---

## 0. WHAT EXISTS vs WHAT THIS WAVE ADDS

| Capability | Status | file:line |
|---|---|---|
| Chunker (markdown-heading-aware, Devanagari-safe `[\wऀ-ॿ]+`, ~200-tok/30-overlap, sentence-split overflow) | ✅ LIVE | `kb/core.py:chunk_text:114` |
| Ingest (chunk → FTS `to_tsvector('simple')` → optional-embed → upsert, idempotent by sha256 checksum, RLS-scoped) | ✅ LIVE | `kb/core.py:ingest:209` |
| Ingest endpoint (`POST /brain/knowledge`, `asyncio.to_thread`-wrapped, tenant from token) | ✅ LIVE | `caller.py:3293` |
| 3 tables FORCE-RLS + HNSW(empty, fills on embed) + GIN(active) + scope index | ✅ LIVE | `kb/schema.sql` |
| Embedder (swappable, import-safe, `status()='not_configured'` → FTS-only) | ✅ code-ready, dormant | `vendors/embeddings.py` (per `dynamic-context-rag.md §3`) |
| **`_global` telecaller corpus + seed endpoint** | ✗ THIS WAVE | `kb/seed_global.py` + `POST /kb/seed-telecaller` |
| **Per-campaign collateral ingest trigger (on save)** | ✗ THIS WAVE | `caller.py` save handlers |
| **PDF/DOCX/URL parsing before ingest** | ✗ THIS WAVE (paste-only today) | ingest pre-parse |
| **Freshness / reindex / dead-chunk cron** | ✗ THIS WAVE | Hatchet cron |
| **Ingest observability (Langfuse/log)** | ✗ THIS WAVE | hatchet box |

---

## 1. THE `_global` TELECALLER CORPUS (the differentiator — sellable moat)

**Why it exists:** the per-tenant KB holds PRODUCT facts. The `_global` corpus holds TELECALLER
BEHAVIOUR — how a 30-year human telecaller handles objections, stalls, polite refusals, price
negotiation, backchannels, and re-engagement — language/business-neutral, curated ONCE, shared
read-only across every tenant. This is what makes the AI sound like a real telecaller, not a chatbot
(`VOICE-BRAIN-MASTER-PLAN.md §3C`, `MASTER_DNA_PLAN.md §G.C #176`). It complements, never duplicates,
the per-tenant product KB.

### 1.1 Corpus spec (~150-300 chunks, quality-barred)

**Categories + target chunk counts (balanced Hindi / English / Hinglish):**

| Category | Chunks | What it covers |
|---|---|---|
| Price objection | 25-35 | "bahut mehenga hai", "discount?", "EMI", "budget nahi hai", competitor-cheaper — REBUTTAL patterns (frame value, anchor, defer-to-callback), never a specific number |
| Trust / "is this real" objection | 15-20 | "kaun ho aap", "company genuine hai?", "spam to nahi", RERA/registration reassurance pattern |
| Timing / stall | 20-25 | "abhi busy hoon", "baad mein", "sochke batata hoon", "call me later" → soft re-engagement + callback-booking pattern |
| Polite refusal / DND | 12-15 | "interested nahi", "mat call karo", "remove my number" → graceful exit + consent-respect (compliance-aligned) |
| Backchannel / rapport | 20-25 | natural Hinglish acknowledgements, empathy beats, "haan ji bilkul", "samajh sakta hoon", bridge markers ("toh basically", "actually dekho") |
| Discovery / qualification | 20-25 | open questions that surface budget/intent/timeline without interrogating; "self-use ya investment?", "kab tak shift karna chahte ho?" |
| Close / next-step | 15-20 | soft site-visit / callback / WhatsApp-share asks; assumptive-but-gentle close patterns |
| Re-engagement (returning lead) | 12-15 | "pichhli baar aapne bola tha…", continuing-not-restarting patterns (pairs with the W3 recap) |

**Quality bar (every chunk):**
- Behaviour PATTERN, never a hardcoded product fact, number, price, or company name (those are
  tenant-specific; a `_global` chunk with a specific price would poison every tenant).
- Self-contained 1-3 sentence move with an implicit "when to use it" cue in the text (so FTS surfaces it
  on the matching objection).
- Tagged `section` = the category above (the chunker preserves `#`-heading → section, so author the
  corpus as a markdown doc with `# Price objection` headings → free section tags).
- `doc_type='objection'` for rebuttal chunks, `'script'` for flow/close patterns.
- Reviewed by a human (the founder or a telecaller) before seeding — this is curated content, the moat.

### 1.2 The seed endpoint (super-admin only, idempotent)

```
POST /kb/seed-telecaller    (super-admin; require_super_admin gate)
  body: { content: <the full markdown corpus>, dry_run?: bool }
  → asyncio.to_thread(kb.ingest, tenant_id="_global", content, kind="paste",
                      doc_type="objection", channel_scope="all", is_admin=True)
  → idempotent by sha256 (re-seeding the same content = no-op, "duplicate_checksum")
  → returns { source_id, chunks, embedded, reason }
```

- `tenant_id="_global"` + `is_admin=True` is the ONLY write path to `_global` (the F2 write-lock: no
  tenant request path can write a `_global` row → no cross-tenant poisoning).
- `dry_run=true` → chunk + count only, no insert (lets the founder preview the chunking before seeding).
- The corpus markdown lives in `kb/seed_global.py` as a versioned constant (or a `kb/seed_global.md`
  asset read at seed time) so it is in git, reviewable, and re-seedable.
- Re-seed flow (corpus edit): the new content has a new checksum → ingest creates a NEW source/document
  + chunks; the OLD `_global` source must be deleted first (the seed endpoint deletes prior `_global`
  sources under `is_admin=True` before re-ingesting → clean replace, not accumulate).

### 1.3 Retrieval fusion (one query, no 2× cost)

`kb.retrieve(tenant_id, q, include_global=True)` ORs `tenant_id IN (:tid, '_global')` into the SAME
FTS/dense WHERE (`RAG-MASTER-PLAN.md §4`, `kb/core.py:retrieve` extension). RRF (k=60) fuses tenant +
`_global` hits in ONE round-trip — the per-turn `lookup` and the connect-prefetch each stay a single
query. The `_global` objection chunk and the tenant's product chunk co-rank; the agent gets both the
*pattern* (how to rebut) and the *fact* (the actual price) in one grounding block.

---

## 2. PER-TENANT COLLATERAL INGESTION (the "upload your brochure" feature)

### 2.1 The non-duplication rule (HARD — enforced at ingest)

The per-tenant KB ingests SUPPLEMENTARY collateral ONLY — brochures, FAQ sheets, pricing tables,
amenity lists, RERA/legal docs, policy docs, objection banks the script didn't cover. It must **NOT**
re-ingest `fields["raw_script"]` (W1 — already the inbound KNOWLEDGE PACK in the prompt). Duplicating it
wastes the grounding budget and double-injects the same facts.

**Enforcement:** the campaign-save ingest trigger ingests only the *collateral* field(s), never
`raw_script`. Guard: if the submitted collateral `sha256 == sha256(raw_script)` → skip + warn
(`reason="is_raw_script_skip"`). The chunker's idempotency (checksum dedupe, `kb/core.py:255`) also
prevents accidental double-ingest of the same doc.

### 2.2 The campaign-save trigger (off the request loop)

On `POST /campaigns` + `POST /campaigns/{id}` (anchors `save_campaign:1466` / `update_campaign:4095` —
the same handlers W2 hooks for cache invalidation):

```python
# AFTER save_campaign(...) returns (sync), best-effort, off the loop:
collateral = fields.get("knowledge") or fields.get("collateral") or ""
if collateral.strip() and sha256(collateral) != sha256(fields.get("raw_script","")):
    asyncio.create_task(asyncio.to_thread(
        kb.ingest, tenant_id, collateral,
        kind="paste", doc_type="brochure", channel_scope="all",
        scope_campaign_id=cid, is_admin=False))   # tenant-scoped, RLS-checked
```

- Best-effort: a KB failure must NOT 500 the campaign save (the to_thread + create_task already
  decouples it; swallow + log).
- `scope_campaign_id=cid` so retrieval can scope to the campaign (`kb.retrieve(scope_campaign_id=cid)`,
  already wired in `_kb_retrieve` at `DEPLOYED.py:456`).
- The collateral field is accepted in `fields_json` (the existing `_coerce_fields` passes unknown keys
  through — `dynamic-context-rag.md F7`); add a `knowledge`/`collateral` normalize line for hygiene.

### 2.3 Parsed inflow (PDF / DOCX / URL → text → ingest)

Today `POST /brain/knowledge` takes pasted text only. The full ingestion adds a parse step BEFORE
chunking. **Where it runs matters (event-loop safety):**

| kind | parser | licence note |
|---|---|---|
| `paste` | none (raw text) | — |
| `file` (.pdf) | **pdfplumber** (MIT) — NOT PyMuPDF (AGPL; `platform-knowledge-rag.md §9` licence risk) | MIT, safe |
| `file` (.docx) | python-docx | MIT |
| `file` (.csv/.md/.txt) | stdlib | — |
| `url` | trafilatura (main-content extraction) | Apache-2.0 |

- Parse + chunk + embed run in `asyncio.to_thread` (paste) or, when the Hatchet spine is live, as a
  durable `kb-ingest-document` workflow off the box (`platform-knowledge-rag.md §3` — the worker process
  has the model resident, off the live voice box per F5). A PDF parse on the request thread freezes the
  monolith for all tenants — NEVER inline.
- For W4 (no Hatchet dependency required), paste + the campaign-save trigger are the V1 path; file/URL
  parse is a fast-follow that reuses the same `kb.ingest` core (just adds the parse front-end).

### 2.4 Chunking strategy (already correct, doc-type routed)

`chunk_text` (`kb/core.py:114`) is recursive-character at ~200 tokens with 30-overlap, markdown-heading
→ section, sentence-split on overflow, Devanagari-safe. Research (`RAG-MASTER-PLAN` brief §4) confirms
recursive (69% acc) beats semantic (54%) for product docs. Doc-type routing (config, not new code):
- FAQ → keep sentence-tight (the existing sentence-split handles it).
- brochure/manual → recursive ~200-400 tok (the existing default).
- compliance/legal → keep whole sections (heading-bounded blocks already preserved).

No chunker change needed for W4; the live `chunk_text` is the right shape.

---

## 3. EMBEDDING (FTS-only V1; dense deferred Phase 2)

**V1 (W4): FTS-only. $0 embedding cost.** The embedder stays `not_configured` → `kb.ingest` stores
chunks with `embedding=NULL` + populated `fts` → `kb.retrieve` runs the sparse leg alone, RLS-scoped,
GIN-indexed (2-8ms). This proves the whole ingest→retrieve→ground→eval path with zero external
credential and zero GPU box (`VOICE-BRAIN-MASTER-PLAN.md §5`: "FTS-only V1 avoids a ~$200-400/mo GPU
box").

**Phase 2 (deferred, gated on `EMBED_API_KEY`): dense `text-embedding-3-small` 256d.**
- Matryoshka 256d retains 93-95% quality at ~$0.02/1M tokens; storage ~2GB/1M chunks vs 12GB at 1536d.
- Embed at INGEST time, batched, off-thread (Hatchet worker or `asyncio.to_thread`) — NEVER inline,
  NEVER in the voice loop. Query-embed (~40-80ms) only on the connect-prefetch (inside the connect
  window) and only when cached.
- One-time backfill of existing FTS-only chunks: `re-ingest` or a batch `UPDATE kb_chunks SET embedding
  = embed(content)` off-thread. Cost: 10k chunks × 400 tok = 4M tok = ~$0.08 one-time.
- Sarvam has NO embeddings API (confirmed `dynamic-context-rag.md §3`). Do NOT use OpenRouter for
  embeddings (founder's paid-credit rule, MEMORY). `text-embedding-3-small` via a direct OpenAI key, OR
  self-hosted BGE-M3 in a dedicated off-box `embed-svc` (the residency path, `platform-knowledge-rag.md
  §4.4`) — decided at the Phase-2 gate, not W4.

---

## 4. FRESHNESS / REINDEX / DEAD-CHUNK MONITORING

1. **Source edit → reindex.** The collateral field changing on a campaign save = a new checksum →
   `kb.ingest` (the idempotency dedupes unchanged content; changed content needs a delete-then-insert by
   `(tenant_id, scope_campaign_id)` to avoid orphaned old chunks). **Add to `kb.ingest`: when re-ingesting
   a campaign's collateral, delete the prior `kb_chunks` for that `(tenant_id, scope_campaign_id)` before
   insert** (atomic, in the same RLS txn) so an edited brochure replaces, not accumulates. Bump
   `kb_sources.kb_version` (cache-bust → the grounding cache key `(tenant,campaign,stage,kb_version)`
   auto-misses, `RAG-MASTER-PLAN §3`).
2. **Time-boxed offers/pricing.** `kb_documents.effective_to` (schema field) → the retriever adds
   `AND (effective_to IS NULL OR effective_to > now())` so a stale price/offer auto-expires from
   retrieval — no stale number ever spoken. A daily Hatchet cron flags expired docs.
3. **Dead-chunk / drift monitor (weekly Hatchet cron, off-box):** report per tenant — #sources, #chunks,
   embed-coverage %, last-ingest age, and the `kb_query_log` ungrounded-rate (the % of `lookup` calls
   that missed). A rising ungrounded-rate = the corpus has a gap → surface in the KB UI as "questions
   your AI couldn't answer" (the knowledge-gap loop, `RAG-MASTER-PLAN §7.1`).

---

## 5. OBSERVABILITY (the corpus is only as good as you can see it)

- **`kb_query_log`** (platform schema, `platform-knowledge-rag.md §2d`): every retrieve writes
  `{channel, query, top_ids[+scores+leg], grounded, latency_ms}`. This is the corpus-health feed AND the
  knowledge-gap source. For W4, the inbound `lookup` MISS/HIT logs (`DEPLOYED.py:1678,1687`) are already
  emitted to the journal; wire them into `kb_query_log` for durable querying.
- **Langfuse on the hatchet box** (`68.183.94.38`, localhost-only, the existing Hatchet/Logto Docker
  host): trace each ingest run (parse → chunk-count → embed-count → upsert) + each retrieval
  (query → top chunks → grounded?). Off the live voice box, zero earner impact. Deferred-but-named: the
  weekly RAGAS audit (`RAG-EVAL-SPEC.md`) reads from `kb_query_log` + Langfuse traces.
- **A `GET /kb/status` health surface** (per tenant: #sources/#chunks/embed%/grounded-rate) feeds the
  KB management UI (`RAG-MASTER-PLAN §7.5`) + the founder dashboard.

---

## 6. COST ENVELOPE (real numbers)

| Item | Cost |
|---|---|
| `_global` corpus seed (FTS-only, ~250 chunks, one-time) | **$0** (pure Postgres) |
| Per-campaign collateral ingest (FTS-only) | **$0** per ingest (CPU only) |
| Per-call retrieval (connect-prefetch + lookups, FTS) | **~$0** — 1-2 PG queries/call, GIN-indexed |
| Dense embedding (Phase 2, `text-embedding-3-small` 256d) | ~$0.08 one-time for 10k chunks; ~$0.002/day query-embed at 100k retrievals/day — negligible |
| GPU box for self-hosted embeddings | **$0 in V1** (FTS-only); ~$200-400/mo ONLY if Phase-2 self-hosting is chosen over the API |

FTS-only V1 is the cost-disciplined default. Dense is a gated upgrade, not a V1 dependency.

---

## 7. ACCEPTANCE (ingestion-specific; full gate in `RAG-EVAL-SPEC.md`)

1. **`_global` seed:** `POST /kb/seed-telecaller` (super-admin) → `psql -c "SELECT count(*),
   count(DISTINCT section) FROM kb_chunks WHERE tenant_id='_global'"` → 150-300 chunks across 8
   sections. Re-seed same content → idempotent (count stable). Re-seed CHANGED content → old `_global`
   replaced, not doubled.
2. **`_global` write-lock (security):** a TENANT request (`POST /brain/knowledge` with a forged
   `tenant_id='_global'`) CANNOT write a `_global` row (tenant is resolved from the token, not the body
   — `caller.py:resolve_tenant`; and the seed path is `require_super_admin`). Probe must show 0 `_global`
   rows attributable to a tenant.
3. **Collateral ingest on save:** `POST /campaigns` with a `knowledge` blob → `psql -c "SELECT count(*)
   FROM kb_chunks WHERE scope_campaign_id='<cid>'"` > 0; embeddings NULL (FTS-only), `fts` populated.
   Re-save same collateral → idempotent (no doubling). Save with `knowledge == raw_script` → skipped
   (0 new chunks, `reason=is_raw_script_skip`).
4. **No raw_script duplication:** ingest a campaign with both `raw_script` and `knowledge` → the
   `raw_script` text does NOT appear as a `kb_chunk` (only the collateral does).
5. **Concurrent-load (event-loop safety):** while a `POST /campaigns` with a LARGE collateral blob is
   ingesting, fire ~20 parallel `GET /api/stats` → every response stays fast (p95 < 0.3s, no
   multi-second stall) → proves the ingest ran off the loop (`asyncio.to_thread`), not inline.
6. **FTS retrieval correctness:** seed a known pricing chunk → `GET /brain/retrieve?q=registration
   charge` returns it (sparse leg, exact-term via the OR-tsquery); a `_global` objection query surfaces
   the matching `_global` rebuttal chunk fused in.
7. **RLS isolation:** as Tenant A, retrieve returns only A's collateral + `_global`; a raw `SELECT …
   WHERE tenant_id='B'` under A's GUC returns 0 rows.

---

## 8. STEP ORDER (maps to `RAG-MASTER-PLAN §9` steps 1-3)

| # | Unit | Box-mutating | Model |
|---|---|---|---|
| I1 | `kb/seed_global.py` corpus (the ~250-chunk markdown) + curation review | none (asset) | opus (curation) |
| I2 | `POST /kb/seed-telecaller` (super-admin, idempotent, replace-on-reseed) + seed `_global` to box DB | caller.py + DB | opus |
| I3 | campaign-save collateral ingest trigger (raw_script-skip + delete-then-insert reindex + kb_version bump) | caller.py save handlers | opus |
| I4 (fast-follow) | file/URL parse front-end (pdfplumber/python-docx/trafilatura) → `kb.ingest` | caller.py / worker | sonnet |
| I5 (deferred) | dense embedding backfill + `EMBED_API_KEY` flip + HNSW activation | DB batch | opus |
| I6 | `kb_query_log` wiring (lookup HIT/MISS → durable rows) + `GET /kb/status` + weekly Hatchet drift cron | caller.py + hatchet box | sonnet |

Each unit: backup-first, deploy, acceptance, build_log, commit. The earner (`agent.py`/famit-agent) is
never restarted; ingestion is caller-side + DB only.
