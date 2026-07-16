# DESIGN SPEC — Dynamic JSON Context + pgvector RAG + Structured Lead-Memory

> Replaces the static mega-prompt with: structured per-lead memory (key-loaded), a pgvector
> knowledge corpus (campaign brochures/FAQ + objection bank), retrieval **precomputed at dial
> time** (never per turn), injected into the voice prompt **once** at the existing recap seam —
> all behind a feature flag, byte-identical when off. STRANGLE & EVOLVE; live system keeps earning.

Status: READY TO BUILD. Owner of execution: build agent (model routing per step below).
Author: staff-eng design pass, grounded in live source under `droplet_work/`.
Last updated: 2026-06-09.

---

## 0. THE ONE LOAD-BEARING CONSTRAINT (read first — the whole design follows from it)

**The voice agent process (`agent.py`, systemd `famit-agent`) must NEVER do a live
Postgres / pgvector / embedding call on the call hot path.**

Reasons, all from live source + plan:
1. `agent.py` runs as a **separate process** from `caller.py` and does not own the PG pool
   (P1 architecture: `caller.py` owns Postgres; the agent reads campaign JSON off disk and
   writes transcripts — `P1_FOUNDATION_STATE.md:23` "NEVER put an agent-read store in pg").
2. The Groq prompt-cache lesson is already paid for in blood: per-turn
   `agent.update_instructions(...)` caused **2.5 s TTFT spikes** and was REMOVED
   (`agent.py:526-535`, HANDOFF VOICEFIX). Anything that mutates the prompt per turn — including
   a per-turn vector search — reintroduces that regression.
3. The master plan mandates: *"precompute/cache per lead-stage (NOT per turn), a MEASURED number
   in the budget, gated behind the p95 target"* (plan line 50, HUMAN-VOICE-PATH item 3).

**Therefore the architecture is, by elimination:**
- **INDEX** (embed → pgvector) happens **offline** in `caller.py` on `POST /campaigns`
  create/update (+ a one-time backfill). Never on a call.
- **RETRIEVE + PRECOMPUTE the prompt blob** happens in `caller.py` **`run_job` at DIAL time**
  (`caller.py:1642-1658`), the LAST caller-owned moment before the agent connects. Cache it.
  (Dial time, not agent-connect: agent-connect is the wrong process AND adds to
  time-to-first-utterance.)
- **DELIVER** the precomputed blob to the agent via a channel it ALREADY reads — a per-call file
  `var/rag_context/<room>.json` (mirrors the existing `var/campaigns/<id>.json` pattern the agent
  already loads at `agent.py:120,339`).
- **INJECT** in `agent.py` by appending the blob **once** into `base_instructions` at the
  **existing recap seam** (`agent.py:372-378`), right beside `mem.build_recap`. Never via
  `update_instructions`, never per turn.

This makes the change **non-breaking by construction**: the only hot-path cost is a slightly
longer (but static, cache-friendly) prompt prefix-suffix. Flag off ⇒ blob is empty ⇒ `instructions`
is byte-identical to today.

---

## 1. PROMPT-CACHE RULE (sharper than "append once")

`build_system_prompt(fields)` (`prompt.py:253`) is the **STABLE PREFIX** — identical across every
lead of a campaign. Groq caches it. **Do NOT inject per-lead RAG or per-lead memory inside
`build_system_prompt`** — that would vary the cached prefix per lead and destroy cross-call cache
reuse (the entire latency moat).

Everything per-lead / per-stage / retrieved goes strictly in the **SUFFIX**, assembled once in
`agent.py` after `build_system_prompt(...)` returns. The code already does this for lead-name +
recap (`agent.py:372-378`); RAG rides the **same rail**, appended after the recap block.

Ordering of the assembled `instructions` string (top = cached prefix, bottom = per-call suffix):

```
[ build_system_prompt(fields) ]      <- STABLE, shared, Groq-cached  (prompt.py)
[ LEAD NAME: <name> ]                <- per-call  (agent.py:373-374, unchanged)
[ === PICHHLI BAAT === <recap> ]     <- per-call  (agent.py:375-377, unchanged)
[ === RELEVANT CONTEXT (RAG) === ]   <- NEW per-call suffix, this spec, flag-gated
[ === LEAD PROFILE (structured) === ]<- NEW per-call suffix, this spec, flag-gated
```

The suffix is built ONCE before `_MirrorAgent(instructions=instructions)` (`agent.py:700`) and
never touched again. The per-turn language nudge (`agent.py:667-694`) stays exactly as-is — it adds
a transient per-turn *system message to turn_ctx*, NOT a prompt rewrite, so it is cache-safe and
out of scope here.

---

## 2. DATA MODEL — don't over-vectorize

Three distinct stores, deliberately different shapes:

### 2a. `lead_memory` — STRUCTURED rows, key-loaded (NOT a vector store)
You load a lead's OWN history by exact key; you never similarity-search it. The plan lists
"structured Postgres lead-memory" separately from pgvector for exactly this reason.

**CRITICAL CORRECTNESS + SECURITY FIX baked in:** today `memory.py` keys by **phone only**
(`_path_for(phone)` → `<digits>.json`, `memory.py:48-50`) with **no tenant_id**. Two tenants
dialing the same number share memory = **cross-tenant bleed**. Plan Phase 1 explicitly requires
"memory re-keyed by tenant_id". `lead_memory` MUST key on **(tenant_id, phone)**.

```sql
CREATE TABLE lead_memory (
    tenant_id      text        NOT NULL,
    phone          text        NOT NULL,            -- normalized digits
    name           text        DEFAULT '',
    -- rolling structured profile (typed, queryable):
    last_outcome   text        DEFAULT '',          -- interested|callback|voicemail|opt_out|...
    interest_score int         DEFAULT 0,           -- 0..100 (mirrors lead.score)
    stage          text        DEFAULT 'new',       -- new|contacted|qualifying|interested|booked|...
    summary        text        DEFAULT '',          -- last call's AI summary (<= 600 chars)
    facts          jsonb       DEFAULT '{}'::jsonb, -- {budget, config, self_use_vs_invest, objections_raised[], preferred_time, ...}
    last_call_at   timestamptz,
    call_count     int         DEFAULT 0,
    updated_at     timestamptz DEFAULT now(),
    PRIMARY KEY (tenant_id, phone)
);
ALTER TABLE lead_memory ENABLE ROW LEVEL SECURITY;
ALTER TABLE lead_memory FORCE  ROW LEVEL SECURITY;
CREATE POLICY lead_memory_tenant ON lead_memory
    USING (tenant_id = current_setting('app.tenant_id', true))
    WITH CHECK (tenant_id = current_setting('app.tenant_id', true));   -- explicit write-scope (F2)
```

### 2b. `campaign_knowledge_chunks` — pgvector (the REAL RAG win)
A vendor pastes/uploads a big brochure / FAQ / price sheet that is far too large to dump into every
prompt. We chunk it, embed it, and retrieve only the **stage-relevant slice** per lead. This is the
primary RAG value — it lets the agent answer deep questions (loan, floor plans, comparisons, legal)
without bloating the cached prefix.

```sql
-- ⚠️ RED-TEAM F1: this line is SUPERUSER-ONLY (pgvector is untrusted) and `famit_app` is NOSUPERUSER.
-- It must NOT live in rag_schema.sql / ensure_schema(). Run it as `postgres` at PROVISION time (fold
-- into P1 U1 _provision_pg.sh). rag_schema.sql below = tables+RLS+HNSW only (famit_app owns those).
CREATE EXTENSION IF NOT EXISTS vector;     -- (provision-time, as postgres — see RED-TEAM FIXES §F1)

CREATE TABLE campaign_knowledge_chunks (
    id            bigserial PRIMARY KEY,
    tenant_id     text NOT NULL,
    campaign_id   text NOT NULL,
    chunk_idx     int  NOT NULL,
    content       text NOT NULL,                 -- the raw chunk (what gets injected)
    section       text DEFAULT '',               -- optional heading (pricing|amenities|legal|loan|location|faq)
    tokens        int  DEFAULT 0,
    embedding     vector(1024),                  -- dim = EMBED_DIM (BGE-M3 dense = 1024); see vendors/embeddings.py
    created_at    timestamptz DEFAULT now(),
    UNIQUE (tenant_id, campaign_id, chunk_idx)
);
ALTER TABLE campaign_knowledge_chunks ENABLE ROW LEVEL SECURITY;
ALTER TABLE campaign_knowledge_chunks FORCE  ROW LEVEL SECURITY;
CREATE POLICY ckc_tenant ON campaign_knowledge_chunks
    USING (tenant_id = current_setting('app.tenant_id', true))
    WITH CHECK (tenant_id = current_setting('app.tenant_id', true));   -- explicit write-scope (F2)
-- ANN index (cosine). HNSW (pgvector >= 0.5). Build AFTER backfill for speed.
CREATE INDEX ckc_embed_hnsw ON campaign_knowledge_chunks
    USING hnsw (embedding vector_cosine_ops);
CREATE INDEX ckc_campaign ON campaign_knowledge_chunks (tenant_id, campaign_id);
```

### 2c. `objection_vectors` — pgvector, but used for PRELOAD not per-turn search
The per-campaign objection bank is small and is ALREADY injected wholesale into the prompt
(`prompt.py:286-287` builds `objs`, rendered at `prompt.py:358`). So we do NOT vectorize a
campaign's own objections for per-turn retrieval (per-turn retrieval is off the table by §0).
We vectorize objections only for two future-facing uses, both off the hot path:
1. a **GLOBAL learned objection corpus** (`campaign_id = ''` = cross-campaign best rebuttals
   harvested from transcripts), retrieved at dial time and folded into the precomputed blob;
2. anticipatory per-stage preload.

```sql
CREATE TABLE objection_vectors (
    id            bigserial PRIMARY KEY,
    tenant_id     text NOT NULL,                 -- '' = global/shared corpus
    campaign_id   text DEFAULT '',               -- '' = applies to all campaigns of the tenant
    q             text NOT NULL,                 -- objection / question
    a             text NOT NULL,                 -- approved rebuttal
    embedding     vector(1024),
    source        text DEFAULT 'manual',         -- manual|learned
    created_at    timestamptz DEFAULT now()
);
ALTER TABLE objection_vectors ENABLE ROW LEVEL SECURITY;
ALTER TABLE objection_vectors FORCE  ROW LEVEL SECURITY;
-- ⚠️ RED-TEAM F2: USING may read own+global, but WITH CHECK must be OWN-ONLY (no `OR ''`) or any
-- tenant could INSERT a global ('') row visible to ALL tenants (shared-corpus poisoning). Globals are
-- seeded out-of-band as the schema owner (Phase-3 harvester), never via a tenant request path.
CREATE POLICY ov_tenant ON objection_vectors
    USING (tenant_id = current_setting('app.tenant_id', true) OR tenant_id = '')
    WITH CHECK (tenant_id = current_setting('app.tenant_id', true));   -- own-only writes (F2)
CREATE INDEX ov_embed_hnsw ON objection_vectors
    USING hnsw (embedding vector_cosine_ops);
```

> Phase-1 scope note: ship **2a (lead_memory)** and **2b (campaign_knowledge_chunks)** fully.
> **2c (objection_vectors)** ships as DDL + an empty-corpus no-op retrieval path (wired but inert)
> so the learned-objection loop (Phase 3 eval harness) has a home without adding hot-path risk now.

---

## 3. EMBEDDER — `vendors/embeddings.py` (swappable, import-safe-degrade)

**Verified fact (2026-06-09):** Sarvam's public API exposes `/chat/completions`, `/translate`,
`/speech-to-text`, `/text-to-speech`, `/transliterate`, `/detect-language` — **NO text-embeddings
endpoint** (checked `docs.sarvam.ai/api-reference-docs/introduction`). So "Sarvam India-hosted
embeddings" (plan) cannot be taken literally today.

**The plan's actual intent is DATA RESIDENCY (India) + cost, NOT voice latency** — because
retrieval is precomputed off the hot path, the embedder is not latency-critical. So:

- **Default embedder = self-hosted `BAAI/bge-m3` (dense mode, 1024-dim)**, run in-process in
  `caller.py`'s box (blr) via `sentence-transformers`. BGE-M3 is multilingual (100+ langs incl.
  Hindi), strong on Hindi-BEIR, Apache-2.0, no API key, no data leaves the box → meets the
  residency bar the plan wanted from Sarvam. (Indic-specialist alternative if recall is weak:
  `NLLB-E5`; both are config-swappable.)
- Build `vendors/embeddings.py` as a **provider-pluggable** module mirroring the existing vendor
  pattern (`vendors/sarvam_meter.py`, `vendors/groq_meter.py`): a `status()` + `embed(texts)`
  surface, env-driven, **import-safe-degrade** (if the model/lib is missing or unconfigured,
  `status()=="not_configured"` and `embed()` returns `[]` → indexing + retrieval become clean
  no-ops → the system behaves exactly like today). Never throws into a call.
- `EMBED_PROVIDER` ∈ {`bge` (default, local), `sarvam` (reserved — wired to `/chat/completions`
  fallback or flipped on the day Sarvam ships embeddings), `openai_compatible` (escape hatch)}.
- `EMBED_DIM` (default 1024) is config-driven so the `vector(n)` column and the model stay in lock-step.

> ⚠️ **EVENT-LOOP SAFETY (mandatory, not optional).** `embed()` runs a CPU torch `encode()` —
> **seconds** for a multi-chunk brochure. `caller.py` is a single uvicorn async loop serving ALL
> tenants. Calling `encode()` inline (in the `POST /campaigns` handler or in async `run_job`) parks
> that loop → the **entire live panel freezes for every tenant** for the encode duration = a
> NON-BREAKING violation. A few-ms PG SELECT is fine to run sync (P1's rationale); a torch encode is
> NOT. So `embed()` itself stays a plain sync function, but **every caller-side call site MUST run it
> off the loop**:
> - dial-time (`run_job`, §4b): `vecs = await loop.run_in_executor(None, embeddings.embed, texts)`.
> - index-time (`/campaigns` save, §4a): do NOT embed inline in the handler — hand the whole
>   `index_campaign(...)` to a background thread / task (`asyncio.create_task(asyncio.to_thread(...))`
>   or a small worker), so the save returns immediately and embedding happens off-thread.
> The **voice hot path is already safe** because the agent only reads a JSON file (no embed, no DB).
> Single-`curl` regression CANNOT see an event-loop stall — Step 3/5 acceptance MUST include a
> CONCURRENT-load check (below).

```python
# vendors/embeddings.py  (sketch — full impl by build agent)
"""Swappable text-embedding provider. Import-safe: if unconfigured/unavailable, every
call is a clean no-op (status='not_configured', embed()=[]). NEVER raises into a call path.
Default = self-hosted BAAI/bge-m3 (1024-dim, multilingual incl. Hindi) -> data stays in blr."""
from __future__ import annotations
import os, logging
logger = logging.getLogger(__name__)

EMBED_PROVIDER = os.getenv("EMBED_PROVIDER", "bge")
EMBED_MODEL    = os.getenv("EMBED_MODEL", "BAAI/bge-m3")
EMBED_DIM      = int(os.getenv("EMBED_DIM", "1024"))

_model = None  # lazy singleton

def status() -> str:
    try:
        return "configured" if _ensure() is not None else "not_configured"
    except Exception:  # noqa: BLE001
        return "not_configured"

def _ensure():
    global _model
    if _model is not None:
        return _model
    if EMBED_PROVIDER == "bge":
        try:
            from sentence_transformers import SentenceTransformer
            _model = SentenceTransformer(EMBED_MODEL, device=os.getenv("EMBED_DEVICE", "cpu"))
        except Exception as exc:  # noqa: BLE001
            logger.warning("embeddings unavailable: %r", exc)
            _model = None
    return _model

def embed(texts: list[str]) -> list[list[float]]:
    """Return one EMBED_DIM vector per input. [] on any failure (no-op degrade)."""
    if not texts:
        return []
    m = _ensure()
    if m is None:
        return []
    try:
        import time as _t; t0 = _t.time()
        vecs = m.encode(texts, normalize_embeddings=True)  # cosine-ready
        logger.info("embed n=%d dim=%d %.0fms", len(texts), len(vecs[0]), (_t.time()-t0)*1000)
        return [list(map(float, v)) for v in vecs]
    except Exception as exc:  # noqa: BLE001
        logger.warning("embed failed: %r", exc)
        return []
```

---

## 4. RETRIEVAL DESIGN (precompute per lead-stage, cache, NOT per turn)

New module **`rag.py`** (in `droplet_work/`, imported by `caller.py` only — agent never imports it).
Owns: a **sync** psycopg connection (matches P1's "`_read` is sync"), the chunker, the index writer,
the retriever, and the blob builder. Import-safe-degrade: if `PG_DSN` unset or pgvector unreachable
→ `rag_enabled()` returns False → every entry point no-ops.

### 4a. Indexing (offline, on campaign save)
`rag.index_campaign(tenant_id, campaign_id, fields)`:
1. Gather the knowledge text = `product_summary` + `talking_points` + `usps` + a NEW optional
   `knowledge` field (the big pasted brochure/FAQ; see §6 caller wiring) + objections.
2. Chunk: ~`CHUNK_TOKENS=180` tokens, ~`CHUNK_OVERLAP=30`, split on blank lines / sentence
   boundaries (cheap; tiktoken-free char≈token heuristic ok). Tag `section` when a heading is found.
3. `embeddings.embed([chunk...])`. If `[]` (degraded) → skip (no rows; retrieval no-ops).
4. Upsert into `campaign_knowledge_chunks` under `SET LOCAL app.tenant_id` (delete-then-insert by
   `(tenant_id, campaign_id)` for idempotency).
This runs in `POST /campaigns` and `POST /campaigns/{id}` **off the event loop** (per the
EVENT-LOOP SAFETY box in §3): after the JSON save succeeds, fire
`asyncio.create_task(asyncio.to_thread(rag.index_campaign, tenant_id, cid, fields))` (or enqueue to a
worker) — the handler returns immediately; the multi-second embed never blocks the loop. Best-effort:
a failure must NOT 500 the save and must be swallowed/logged.

### 4b. Retrieval + blob precompute (at DIAL time, in `run_job`)
`rag.build_context_blob(tenant_id, campaign_id, lead_name, phone, stage) -> str`:
1. **Query string** = stage-aware seed: `lead_memory.facts/summary` for a returning lead, else the
   campaign's qualification question + product. (For a brand-new lead with no signal, retrieve the
   campaign's "overview/pricing" sections — the most likely first questions.)
2. `qvec = (await loop.run_in_executor(None, embeddings.embed, [query]))[0]` — **run_in_executor**,
   never a bare `embed()` call (event-loop safety, §3). On degrade `embed()` returns `[]` → "" blob.
3. `SELECT content, section FROM campaign_knowledge_chunks
    WHERE tenant_id = $1 AND campaign_id = $2
    ORDER BY embedding <=> $qvec LIMIT RAG_TOP_K`   (`RAG_TOP_K` default 4), under `SET LOCAL
    app.tenant_id`. (Optional global objection rows folded similarly.)
4. Assemble the blob, **hard token-capped at `RAG_MAX_TOKENS` (default 350)** — this cap is the
   latency lever (§5). Format:
   ```
   === RELEVANT CONTEXT (इस lead/सवालों के लिए — ज़रूरत पड़े तो इस्तेमाल करो, सब मत बोलो) ===
   - <chunk 1 content>
   - <chunk 2 content>
   ...
   ```
5. Return "" if degraded/empty (→ agent injects nothing → byte-identical to today).

**Caching, per lead-stage (NOT per turn, NOT per call necessarily)** — and the cache KEY matters for
safety at scale:
- **New lead (stage='new', no `lead_memory.facts`):** the query is *identical for every new lead in
  the campaign* (qualification + product). So key the blob by **`(tenant_id, campaign_id, stage='new')`
  — NO phone**. This is the high-value collapse: a fresh 1,000-lead campaign launch goes from 1,000
  cache misses (1,000 sequential embeds hammering the loop) to **exactly ONE** embed; the other 999
  dials are instant cache hits. Without this, the new-lead path is precisely the event-loop-stall
  scenario the §3 box warns about.
- **Returning lead (has real `lead_memory.facts`):** the query is personalized, so key by
  **`(tenant_id, campaign_id, phone, stage)`** to get the per-lead blob.
Cache file `var/rag_cache/<key>.json` with TTL (`RAG_CACHE_TTL_S`, default 86400). `run_job` checks
the cache first; only embeds+queries on miss (and only off the loop, §4b step 2). Re-indexing a
campaign busts its cache (bump a campaign `kb_version`). Net: retrieval cost is paid ~once per
*distinct* (campaign, stage[, lead]) and is entirely off the voice critical path.

### 4c. Delivery to the agent
In `run_job`, immediately before/after building `md_obj` (`caller.py:1644-1654`), write the
precomputed blob + the structured lead profile to **`var/rag_context/<room>.json`**:
```json
{ "rag": "<blob string, <=RAG_MAX_TOKENS>", "lead_profile": "<structured one-paragraph profile>",
  "stage": "interested", "kb_version": 7 }
```
Do **NOT** inline a large blob into `create_dispatch` metadata (`md`): dispatch metadata is small and
already carries `{campaign_id, lead_name, variant...}`. The per-room file (same pattern the agent
already uses for campaigns) has no size limit and decouples the two processes. `md_obj` gains only a
tiny boolean/flag if needed; the agent finds the file by `room`.

### 4d. Agent-side consumption (the injection)
In `agent.py`, at the recap seam (after line 377, before `instructions = base_instructions`):
```python
# DYNAMIC CONTEXT (RAG + structured lead profile) — precomputed by the caller at dial time,
# injected ONCE here (never per turn -> Groq prompt cache safe). Flag-gated; missing file -> no-op.
if os.getenv("RAG_INJECT_ENABLED", "0") not in ("0", "false", "False"):
    try:
        rc = _load_rag_context(room_name)   # reads var/rag_context/<room>.json, never raises
        if rc.get("lead_profile"):
            base_instructions += "\n\n=== LEAD PROFILE (structured) ===\n" + rc["lead_profile"]
        if rc.get("rag"):
            base_instructions += "\n\n" + rc["rag"]
        if rc.get("rag") or rc.get("lead_profile"):
            logger.info("rag context injected room=%s rag_chars=%d prof_chars=%d",
                        room_name, len(rc.get("rag","")), len(rc.get("lead_profile","")))
    except Exception as exc:  # noqa: BLE001
        logger.warning("rag context load failed (ignored): %r", exc)
```
`_load_rag_context` is a ~10-line helper added to `agent.py` (stdlib json only, mirrors
`_load_campaign` at `agent.py:120`). The agent imports **nothing new** (no DB, no embeddings) — it
just reads a JSON file. This is what keeps the change non-breaking.

---

## 5. MEASURED LATENCY BUDGET (gate on p95, ship only if under threshold)

The ONLY hot-path cost of this subsystem is: a longer (static) prompt → marginally higher Groq
**TTFT** (time-to-first-token). Everything else (embed, vector search, blob build, cache) is off the
critical path (bounded by "completes before `create_sip_participant`").

**What to measure:** the existing `llm_ttft` telemetry already logged per call by the **`famit-agent`
process** (BRAIN notes). ⚠️ **RED-TEAM F4:** `/metrics` does **NOT** expose `llm_ttft` — obs.py exports
only `famit_request_latency_seconds{method,route}` (HTTP latency on the caller, a different process).
So measure p95 `llm_ttft` by **parsing the `famit-agent` log lines on the box** (journalctl/grep), NOT
by curling `/metrics`. Run a fixed set of calls (same campaign, same script via the test harness) and
compare **p95 `llm_ttft` flag-OFF vs flag-ON** from those logs.

**Budget / gate (acceptance):**
- `RAG_MAX_TOKENS` default **350**, `lead_profile` default **<=120 tokens** ⇒ suffix adds **<=~470
  tokens** to a ~1600-token prompt (~30% growth, all in the cache-friendly suffix).
- **SHIP GATE:** p95 `llm_ttft` regression (ON − OFF) must be **< 150 ms**, AND p95 end-of-utterance
  → first-audio (`tts_ttfb` unaffected; eou path unchanged) shows **no regression**. The plan's
  human-voice target is sub-700–800 ms total; current measured llm_ttft is 0.37–0.86 s
  (HANDOFF BRAIN). If the gate fails, **lower `RAG_TOP_K`/`RAG_MAX_TOKENS`** until it passes; if it
  still fails, keep the flag OFF and ship indexing/precompute only (no injection) — the corpus is
  then ready for a later tuning pass without any live risk.
- Precompute budget (NOT gated on voice p95, but bounded so a campaign run isn't slowed): a cache
  MISS dial should add **< 400 ms** to that lead's dispatch (embed + 1 ANN query). Cache HIT ≈ 0.
  If embed-on-CPU is slow, set `EMBED_DEVICE` or precompute the blob in the `scheduler_loop` ahead
  of the dial. Cache hits make this a non-issue at scale.

Record the actual measured numbers in `build_log/` when the gate runs (the plan demands "a MEASURED
number in the budget", not a guess).

---

## 6. EXACT FILES + EDITS

### CREATE
| Path | Purpose | Notes |
|---|---|---|
| `droplet_work/vendors/embeddings.py` | swappable embedder (§3) | import-safe-degrade; default bge-m3/1024 |
| `droplet_work/rag.py` | sync PG+pgvector: chunk, index, retrieve, blob, cache (§4) | imported by caller.py ONLY; `rag_enabled()` gate |
| `droplet_work/rag_schema.sql` | the 3 tables + RLS + HNSW indexes (§2) | idempotent (`IF NOT EXISTS`); applied via psql or `rag.ensure_schema()` |
| `droplet_work/backfill_rag.py` | one-time: index every existing campaign; migrate `var/memory/*.json` → `lead_memory` keyed (tenant_id, phone) | idempotent; dedupe by key |
| `droplet_work/lead_memory.py` | structured-profile read/write helper (sync, used by caller.py) OR extend `memory.py` | see §7 |

### EDIT
| Path | Edit | Anchor |
|---|---|---|
| `droplet_work/caller.py` | (a) on `POST /campaigns` + `POST /campaigns/{id}`: after JSON save, best-effort `rag.index_campaign(...)`; accept a new optional `knowledge` field in fields. (b) in `run_job`: at dial, compute stage, `rag.build_context_blob(...)`, write `var/rag_context/<room>.json`. (c) in `_finalize_call`: upsert `lead_memory` (tenant_id, phone) structured row. | save handlers; `caller.py:1644-1654`; `_finalize_call` |
| `droplet_work/agent.py` | (a) add `_load_rag_context(room_name)` helper (~line 120, beside `_load_campaign`). (b) inject blob at recap seam (§4d) behind `RAG_INJECT_ENABLED`. | `agent.py:120`, `agent.py:377` |
| `droplet_work/memory.py` | re-key to (tenant_id, phone): `_path_for(tenant_id, phone)` OR delegate to `lead_memory.py`. Keep phone-only as legacy read fallback so existing `var/memory/*.json` still recap until backfilled (never lose data). | `memory.py:48-50` |
| `/opt/famit-agent/.env` (box) | append (all default-safe): `RAG_INJECT_ENABLED=0`, `EMBED_PROVIDER=bge`, `EMBED_MODEL=BAAI/bge-m3`, `EMBED_DIM=1024`, `EMBED_DEVICE=cpu`, `RAG_TOP_K=4`, `RAG_MAX_TOKENS=350`, `RAG_CACHE_TTL_S=86400`, `RAG_DB_ENABLED=0`. (`PG_DSN` comes from P1.) | env |

> The agent's stored campaign render path (`agent.py:347-351`, `build_system_prompt` preferred over
> stored prompt) is UNCHANGED — do not touch it (HANDOFF P2 "KEY ARCHITECTURE FIX": do not revert to
> stored-prompt-wins).

---

## 7. STRUCTURED LEAD-MEMORY MIGRATION (the tenant re-key)

Today: `memory.py` writes `var/memory/<phone>.json` `{phone,last_call_at,summary,history[]}`
(`memory.py:108-116`), keyed phone-only, called from `agent.py:402,610` (`_persist_memory`).

Target: a typed `lead_memory(tenant_id, phone, ...)` row (§2a) that is the structured profile, PLUS
keep the lightweight transcript-recap file for the conversational recap text.

Plan:
1. `lead_memory.py`: `load_profile(tenant_id, phone)` (key SELECT) + `upsert_profile(tenant_id,
   phone, **fields)` (sync, RLS-scoped). Import-safe-degrade → if PG down, fall back to the JSON
   recap only (today's behavior).
2. `caller.py._finalize_call` already computes outcome/interest/score/summary per call — write those
   into `lead_memory` there (caller owns tenant_id + PG; the agent does not). This is the right
   process for the structured write.
3. The **recap text** the agent injects (`mem.build_recap`) keeps working off the per-phone JSON for
   now (no agent PG dependency); the structured `lead_profile` paragraph is built by the caller at
   dial time and delivered via `var/rag_context/<room>.json` (§4c). So the agent reads ONE extra
   file and still never touches PG.
4. `backfill_rag.py` migrates existing `var/memory/*.json` into `lead_memory` under the **admin**
   tenant (matches P1's "legacy records → admin tenant"), preserving summaries (never lose data).
5. Note for later (out of scope, voice-only here): `var/wa_threads/<digits>.json` shares the
   phone-only key bug — same re-key applies when WhatsApp is migrated.

---

## 8. STEP ORDER (each = ONE verifiable unit; deploy + acceptance + build_log + commit; never batch)

> DEPENDENCY GATE: Steps 2–6 require **Postgres + `vector` extension + the restricted RLS role**
> provisioned on the box. That is **P1 Unit 1** (`P1_FOUNDATION_STATE.md` U1). RAG needs ONLY P1 U1
> (provisioning); it does **NOT** need P1 U3+ (the `store.py` `_read/_write` cutover). `rag.py` opens
> its OWN sync psycopg connection off `PG_DSN` and applies `rag_schema.sql` independently of P1's
> alembic. If P1 U1 is not done, Step 1 still ships (no DB), and Steps 2+ block on U1.

| # | Unit (one deliverable) | Depends on | Model |
|---|---|---|---|
| 1 | `vendors/embeddings.py` — swappable embedder; install `sentence-transformers`+`BAAI/bge-m3` in caller venv | none | **sonnet** |
| 2 | `rag_schema.sql` + `rag.ensure_schema()` — 3 tables, RLS, HNSW; apply to box DB | P1 U1 | **sonnet** |
| 3 | `rag.py` indexing: chunk + embed + upsert `campaign_knowledge_chunks`; wire `POST /campaigns(/{id})` best-effort; add optional `knowledge` field | 1,2 | **opus** |
| 4 | `backfill_rag.py` — index all existing campaigns; migrate `var/memory/*` → `lead_memory` (admin tenant) | 1,2,3 | **sonnet** |
| 5 | `rag.py` retrieval + blob + per-(lead,stage) cache; write `var/rag_context/<room>.json` in `run_job`; `lead_memory` upsert in `_finalize_call` | 3 | **opus** |
| 6 | `agent.py` `_load_rag_context` + inject-at-recap-seam behind `RAG_INJECT_ENABLED`; `memory.py` re-key | 5 | **opus** |
| 7 | **p95 latency gate** (§5): measure llm_ttft OFF vs ON over fixed call set; tune `RAG_TOP_K`/`RAG_MAX_TOKENS`; flip `RAG_INJECT_ENABLED=1` only if gate passes | 6 | **opus** |

Steps 1–2 can proceed in parallel with P1 if P1 U1 is done; 3→7 are strictly sequential.
One agent owns this whole subsystem (touches caller.py + agent.py + new files) — do NOT run a second
agent on caller.py/agent.py concurrently (the global rule: one agent per file).

---

## 9. PER-STEP ACCEPTANCE TESTS (prove on the live box WITHOUT breaking it)

Global regression (run after EVERY step — same as P1's gate):
`curl -H "X-Auth: FamitCall2026" https://panel.famit.in/api/stats` → 200; `/campaigns`,`/leads`,
`/billing/overview`,`/me` → 200; `/run` dispatches; `ssh famit@168.144.153.145 'systemctl is-active
famit-caller famit-agent'` → active/active; `md5sum` local == deployed for any edited file.

- **Step 1:** `python -c "import vendors.embeddings as e; v=e.embed(['नमस्ते, ये property कहाँ है?','what is the price?']); print(len(v), len(v[0]) if v else 0, e.status())"`
  → prints `2 1024 configured`. With `EMBED_PROVIDER=none` → `0 0 not_configured` (no-op proven).
  No service restart needed (caller doesn't import it yet). Regression gate green.
- **Step 2:** `psql $PG_DSN -c "\dt"` shows the 3 tables + `\d campaign_knowledge_chunks` shows
  `vector(1024)` + HNSW index. RLS proof: as the restricted role with `SET app.tenant_id='t1'`, a
  `SELECT` over a row with `tenant_id='t2'` returns **0 rows** (cross-tenant blocked). DDL-only → no
  behavior change → regression gate green.
- **Step 3:** `POST /campaigns` with a `knowledge` blob → 200, returns id; then
  `psql -c "SELECT count(*), max(chunk_idx) FROM campaign_knowledge_chunks WHERE campaign_id='<id>'"`
  → rows > 0 with non-null embeddings. Re-`POST /campaigns/{id}` → idempotent (count stable, not
  doubled). Force embeddings degraded (`EMBED_PROVIDER=none`) → save still 200, 0 chunks (no 500 —
  prove the best-effort path). Existing campaigns/`/extract`/`/run` unchanged. Regression green.
  **CONCURRENT-LOAD CHECK (mandatory — a single curl cannot see an event-loop stall):** while a
  `POST /campaigns` carrying a LARGE `knowledge` blob (many chunks) is indexing, fire ~20 parallel
  reads — `seq 20 | xargs -P20 -I_ curl -s -o /dev/null -w '%{time_total}\n' -H "X-Auth:
  FamitCall2026" https://panel.famit.in/api/stats`. **Every** response must stay fast (p95
  `time_total` < ~0.3 s, no multi-second stalls). A stall = the embed ran inline on the loop → the
  off-thread fix (§4a) is wrong → BLOCK and fix. This is the only test that proves the live panel does
  not freeze for all tenants during indexing.
- **Step 4:** `python backfill_rag.py` → prints counts; `psql -c "SELECT count(*) FROM lead_memory"`
  == number of `var/memory/*.json` files (admin tenant); re-run → counts stable (idempotent);
  spot-check 3 leads' summaries match their JSON. No existing data lost.
- **Step 5:** trigger a `/run` for a known campaign+lead → confirm `var/rag_context/<room>.json` is
  written with non-empty `rag` (cache MISS path), AND a second dial of the same lead/stage is a
  cache HIT (log shows hit, no embed call). After a real metered test call to 6375548830,
  `psql -c "SELECT * FROM lead_memory WHERE phone LIKE '%6375548830%'"` shows updated
  outcome/interest/stage. **`RAG_INJECT_ENABLED` still 0** → agent ignores the file → transcript +
  summary + cost identical to today (prove non-breaking BEFORE turning injection on). Regression green.
  **CONCURRENT-LAUNCH CHECK (mandatory):** `/run` a campaign with **many NEW leads at once** while
  firing parallel `GET /stats` (as in Step 3). Confirm (a) the responses stay fast (no loop stall →
  proves `run_in_executor`, §4b, is in place), AND (b) the logs show **ONE** embed for the whole
  new-lead batch with the rest cache HITs (proves the new-lead cache key collapses to
  `(tenant_id, campaign_id, 'new')`, §4b — NOT one embed per phone).
- **Step 6:** with `RAG_INJECT_ENABLED=0`, dump the assembled `instructions` (add a one-shot debug
  log) for a returning lead and confirm it is **byte-identical** to the pre-change assembly (no RAG,
  no profile appended). Flip a NON-PROD/test campaign to `=1` and confirm the blob appears in the log
  AFTER the recap block, prefix unchanged. `famit-agent` active; a test call completes with
  transcript. Regression green.
- **Step 7 (the gate):** place N (>=10) test calls flag-OFF, record p95 `llm_ttft` (from
  `/metrics` histogram or logs); flip `RAG_INJECT_ENABLED=1`, repeat; **p95 delta < 150 ms** AND no
  `tts_ttfb`/eou regression AND a real call to 6375548830 still yields transcript+summary+₹cost AND
  the agent demonstrably USES retrieved context. **Calibrate the "uses context" probe:** retrieval is
  pre-call and stage-seeded by design (§4b — not per-turn), so the blob holds chunks for the
  *predicted* stage, not an arbitrary question. The test question MUST align with the seeded
  stage/sections (e.g. for a new-lead call, ask an overview/pricing/loan question that the seeded
  chunks cover) — only answerable from the `knowledge` blob, NOT from the base campaign fields. An
  off-stage question correctly misses and is NOT a RAG failure; if you want broad coverage in the
  test, raise `RAG_TOP_K`/section breadth first. If pass → leave `=1`. If fail → tune or leave `=0`
  (indexing stays, injection off). Record measured numbers in `build_log/`.

---

## 10. FEATURE FLAGS + ROLLBACK

Two independent kill switches, both default OFF/safe:
- `RAG_DB_ENABLED` (caller side): gates ALL `rag.py` DB work (index + retrieve + lead_memory). OFF or
  PG unreachable ⇒ `rag.py` no-ops ⇒ caller behaves exactly as today (no rag_context files written).
- `RAG_INJECT_ENABLED` (agent side): gates ONLY the prompt injection. OFF ⇒ agent ignores any
  rag_context file ⇒ `instructions` byte-identical to today. This is the **voice-path** switch.

**Rollback (per layer, instant, no redeploy):**
- Voice misbehaves / latency regresses → set `RAG_INJECT_ENABLED=0` + `systemctl restart famit-agent`.
  Prompt instantly reverts to today's (campaign brain + recap). Corpus/precompute keep running
  harmlessly.
- Caller side misbehaves → `RAG_DB_ENABLED=0` + `systemctl restart famit-caller`. Indexing/retrieval
  stop; campaign save + run + finalize fall back to pure-JSON behavior. No data lost (JSON stores
  untouched; PG is additive).
- Hard rollback → restore `caller.py`/`agent.py` from the per-unit box backup
  (`*.<unit>bak.<ts>`, per the standing deploy recipe) + restart. The 3 PG tables are additive and
  can be left in place (or `DROP` — nothing else reads them).

**Crash-safety:** each step is one verified unit with its own backup + build_log + commit, so an
interruption costs at most one unit. The DB tables are additive (a half-applied schema is re-runnable
via `IF NOT EXISTS`). JSON stores remain authoritative for the live flow throughout — PG is a
parallel, additive index, never the source of truth for a call until a future explicit cutover.

---

## 11. DEPENDENCIES

- **P1 Unit 1** (Postgres + `vector` extension + restricted RLS role on `168.144.153.145`) — hard
  dependency for Steps 2+. Steps 1 ships without it.
- Python (caller venv `/opt/capsy-agent/.venv`): `sentence-transformers` (+ its torch dep — CPU
  wheel; ~size/RAM check on the box, BGE-M3 ≈ 2.3 GB model + torch — **verify box RAM headroom before
  Step 1**, mirror the plan's semantic-turn-detector pre-flight caution), `psycopg[binary]` (sync;
  P1 also pulls this), `pgvector` server extension. No new vendor credentials (Sarvam key already in
  `.env`; BGE-M3 needs none).
- No frontend dependency for the voice subsystem. (A later UI to paste the `knowledge` blob into a
  campaign is a small Create-Campaign textarea — out of scope here; the backend accepts `knowledge`
  in `fields_json` today once Step 3 lands.)

---

## 12. MODEL ROUTING (for the implementing agent) — summary
- **sonnet**: Steps 1 (embedder module), 2 (DDL/schema apply), 4 (backfill script) — mechanical,
  well-specified.
- **opus**: Steps 3 (indexing wiring into the live save path), 5 (dial-time retrieval/cache/blob +
  lead_memory finalize), 6 (agent hot-path injection — the cache-safety-critical edit), 7 (the
  measured latency gate + tuning) — these touch the live earning path and the latency moat.
- One opus pass to review the whole diff before flipping `RAG_INJECT_ENABLED=1` in prod.

---

## 13. OPEN RISKS (surfaced, with mitigation)
0. **[BLOCKING IF IGNORED] Synchronous torch `encode()` freezing the caller's async event loop.**
   `caller.py` is one uvicorn loop serving ALL tenants; a multi-second brochure embed run inline (in
   the `/campaigns` handler or `run_job`) parks the loop → the whole live panel freezes for every
   tenant = NON-BREAKING violation. The single-curl regression gate CANNOT see this. **Mitigation
   (mandatory, baked into §3/§4a/§4b):** dial-time embed via `await loop.run_in_executor(None,
   embeddings.embed, texts)`; index-time embed off-thread via
   `asyncio.create_task(asyncio.to_thread(rag.index_campaign, ...))`; new-lead cache key collapsed to
   `(tenant_id, campaign_id, 'new')` so a batch launch = 1 embed not N; and the CONCURRENT-LOAD
   checks in §9 Steps 3 & 5 are the gates that prove it. The voice hot path is already safe (agent
   only reads JSON).
1. **BGE-M3 footprint on the box** (~torch + 2.3 GB model, CPU embed latency). Mitigation: pre-flight
   RAM/CPU check (Step 1); cache makes embed cost a rare event; can move embed into `scheduler_loop`
   ahead of dial, or host the embedder as a tiny separate blr service if the caller process can't
   carry torch. Decision gate at Step 1.
2. **Retrieval recall on Hinglish/Devanagari code-mix.** BGE-M3 is multilingual but the corpus is
   messy code-mix. Mitigation: `EMBED_MODEL` swappable (NLLB-E5 Hindi-specialist fallback); §9 Step 7
   includes a "deep question answered from knowledge" acceptance check that catches poor recall.
3. **Sarvam embeddings absent** (confirmed). Mitigation already in design: self-hosted bge default
   meets the residency intent; `sarvam` provider reserved for the day they ship it.
4. **Prompt growth eroding Groq cache hit-rate** if the suffix accidentally varies the prefix.
   Mitigation: §1 rule is explicit (RAG strictly in suffix); Step 6 byte-identical-when-off check +
   Step 7 p95 gate catch any regression.
5. **Stage classification quality** (drives which chunks retrieve). v1 uses a cheap rule
   (lead_memory.stage / outcome). Mitigation: a wrong stage just retrieves slightly-less-relevant
   chunks (graceful); the eval harness (Phase 3) later improves it.
6. **P1 U1 not yet done** → Steps 2+ block. Mitigation: Step 1 proceeds; the schema is independent of
   P1's store.py so the moment U1 lands, Steps 2+ run.

---

## RED-TEAM FIXES (folded) — AUTHORITATIVE; overrides the body where they conflict

Adversarial principal review, 2026-06-09. Every load-bearing anchor in §0/§1/§2/§4/§6 was
re-verified against live source and is **correct** (caller-generated `room` precedes dispatch →
the file-delivery channel is sound; recap seam at `agent.py:372-378`; `_load_campaign` at
`agent.py:120`; `build_system_prompt` at `prompt.py:253`; phone-only memory bleed at
`memory.py:48-50` is real; `update_instructions`/2.5s-TTFT lesson at `agent.py:526-535` confirmed,
independently corroborated by `brain/mistakes.md:103`). The **core architecture survives review
unchanged.** The fixes below are correctness/security/real-box defects in the *mechanics*, not the
design. **Verdict was NO-GO as written; GO once F1–F4 are applied.** F1–F4 BLOCK; F5–F7 are
required-but-non-blocking.

### F1 [BLOCKING — would fail on the real box]: `CREATE EXTENSION vector` is superuser-only; the app role is NOSUPERUSER.
Verified in `droplet_work/_provision_pg.sh`: `famit_app` is created `NOSUPERUSER NOCREATEDB
NOCREATEROLE NOBYPASSRLS` (line 28). `pgvector` is **not** a trusted extension, so
`CREATE EXTENSION vector` requires the `postgres` superuser. The spec currently bundles it into
`rag_schema.sql` (§2b line 120) and says §6 applies that "via psql OR `rag.ensure_schema()`",
implying the app role can run it. **It cannot — `ensure_schema()` as `famit_app` dies on line 1.**
- **However** (correcting an over-broad reading): `famit_app` **owns** the DB and `public` schema
  (`createdb -O famit_app`, `ALTER SCHEMA public OWNER TO famit_app`), so it **CAN**
  `CREATE TABLE`/`CREATE INDEX`. Only `CREATE EXTENSION` is the problem.
- **FIX:** Split the DDL. `CREATE EXTENSION IF NOT EXISTS vector;` becomes a **provision-time step
  run as `postgres`** — fold it into **P1 U1** (`_provision_pg.sh`, alongside the role/db creation:
  `sudo -u postgres psql -d famit -c 'CREATE EXTENSION IF NOT EXISTS vector;'`). `rag_schema.sql`
  contains **only** the 3 tables + RLS + HNSW indexes (all ownable by `famit_app`).
  `rag.ensure_schema()` may create tables/indexes but **must NOT attempt CREATE EXTENSION** (assume
  the extension is pre-provisioned; if `vector` type is missing, degrade: log + `rag_enabled()`→False).
- **Acceptance add (Step 2):** as `famit_app`, `CREATE EXTENSION vector` must be shown to **fail**
  (proves least-privilege intact); as `postgres` it succeeds; then the table DDL as `famit_app` succeeds.

### F2 [BLOCKING — cross-tenant write hole]: RLS policies have no `WITH CHECK`; `objection_vectors` lets any tenant INSERT a global (`tenant_id=''`) row.
All three policies (§2a/§2b/§2c) are `USING(...)`-only. For a permissive `ALL` policy, the omitted
`WITH CHECK` **defaults to the USING expression**. For `lead_memory` and `campaign_knowledge_chunks`
the USING is `tenant_id = current_setting(...)`, so the implicit write-check is adequate. But
`objection_vectors` USING is `(tenant_id = current_setting(...) OR tenant_id = '')` → the implicit
insert-check **also permits `tenant_id=''`**, so **any tenant can write a global row visible to
every tenant** = shared-corpus poisoning (e.g. a malicious rebuttal injected into all tenants'
prompts). Ships inert, but the **DDL ships now** (§2c table is created in Phase 1) and the Phase-3
learned-objection loop will write to it.
- **FIX:** State `WITH CHECK` **explicitly on all three** for auditability, and for
  `objection_vectors` make the write-check **strictly the tenant's own id (no `OR ''`)**:
  ```sql
  -- lead_memory & campaign_knowledge_chunks: read==write scope
  CREATE POLICY lead_memory_tenant ON lead_memory
      USING (tenant_id = current_setting('app.tenant_id', true))
      WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
  -- objection_vectors: READ own+global, but WRITE only own (globals seeded by superuser/owner offline)
  CREATE POLICY ov_tenant ON objection_vectors
      USING (tenant_id = current_setting('app.tenant_id', true) OR tenant_id = '')
      WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
  ```
  Global/shared objection rows are populated **out-of-band as the schema owner** (the Phase-3
  harvester runs privileged), never by a tenant request path.
- **Acceptance add (Step 2):** as `famit_app` with `SET app.tenant_id='t1'`, an
  `INSERT INTO objection_vectors(tenant_id,...) VALUES ('','...')` must be **rejected**; an INSERT
  with `tenant_id='t1'` succeeds; a SELECT still **reads** the `''` global rows.

### F3 [BLOCKING — concurrency/RLS correctness]: "rag.py owns a sync psycopg connection" is unsafe; `SET LOCAL` only scopes inside a transaction.
§4 says rag.py "owns a **sync** psycopg connection." `caller.py` runs many coroutines (parallel dials
in `run_job`, concurrent `/campaigns` saves). A **single shared connection** reused across coroutines
is not safe, and `SET LOCAL app.tenant_id` is scoped to the **current transaction only** — on a shared
conn, interleaved tenants mean RLS is scoped to "whoever `SET` last" → wrong-tenant reads/writes. P1's
own STATE flags exactly this ("pooled-conn GUC leak guard", `P1_FOUNDATION_STATE.md:19`).
- **FIX:** Mandate **connection-per-operation** (open → use → close) OR a tiny bounded pool
  (`psycopg_pool`), and wrap **every** index/retrieve/upsert in an explicit transaction that does
  `SET LOCAL app.tenant_id = %s` as the **first statement**, then the SELECT/UPSERT, then commit.
  Never `SET app.tenant_id` (session-level) on a pooled/long-lived conn. Pseudocode invariant:
  ```python
  with _connect() as conn:                 # fresh conn or pool.getconn()
      with conn.transaction():             # explicit txn
          conn.execute("SET LOCAL app.tenant_id = %s", (tenant_id,))
          ...                              # all SELECT/UPSERT for THIS tenant only
  ```
  Because dial-time embeds already go through `run_in_executor` (§4b), running the (short) PG query
  on that same worker thread with its own conn is consistent and keeps the event loop free.
- **Acceptance add (Step 5 concurrent-launch check):** the existing parallel-dial test must include
  **two different tenants dialing concurrently** and assert each call's `rag_context` contains only
  its own tenant's chunks (no bleed) — proves the per-op conn + `SET LOCAL`-in-txn discipline.

### F4 [BLOCKING — wrong test instrument; Step 7 gate is unmeasurable as written]: `/metrics` exposes NO `llm_ttft` histogram.
Verified in `obs.py`: the only histogram is `famit_request_latency_seconds{method,route}` — that is
**HTTP request latency on the caller**, NOT the voice LLM TTFT. `llm_ttft` is a **log line emitted by
the `famit-agent` process** (LiveKit `LLMMetrics` → `logger.info`), in a **separate process** from the
caller that owns `/metrics`. §5 and Step 7 both say "from `/metrics` histogram or logs" — the
"/metrics histogram" path **does not exist**; a build agent that curls `/metrics` for `llm_ttft` finds
nothing.
- **FIX:** Step 7's instrument is **log-parse only**: grep the `famit-agent` journal/log on the box
  for the per-call `llm_ttft` lines and compute p95 OFF vs ON, e.g.
  `ssh famit@168.144.153.145 "journalctl -u famit-agent --since ... | grep -oE 'llm_ttft[=: ]+[0-9.]+'"`
  → collect → p95. (Confirm the exact log key/format the agent emits before the run; do NOT assume.)
  **Do NOT** add a TTFT Histogram to obs.py — that is cross-process scope creep (the metric is in the
  agent, the registry is in the caller); the log-parse is the executable path and matches how the
  HANDOFF/BRAIN numbers (llm_ttft 0.37–0.86s) were obtained.
- Everywhere §5/§9-Step7 say "/metrics histogram or logs", read **"agent log lines"**.

### F5 [required, non-blocking — RAM co-location on the LIVE VOICE BOX]: bias Step 1 toward an off-box embedder.
The real risk is not "can `famit-caller` import torch" — it is that a **~2.3 GB resident BGE-M3 + torch
loads on `168.144.153.145`, the SAME box running the live `famit-agent` voice process** (the earning
hot path). Memory pressure / CPU contention there can degrade live-call latency — the exact thing §0
protects. Since the **only** driver for self-hosting is data-residency (retrieval is off the hot path,
§3), in-process torch on the voice box buys nothing and adds risk.
- **FIX (sharpen the Step-1 decision gate):** default the decision **toward hosting the embedder as a
  tiny separate blr service** (the §13-risk-1 fallback) and have `vendors/embeddings.py` call it over
  localhost/VPC HTTP, rather than loading torch in-process beside the live agent. In-process torch is
  acceptable **only if** the Step-1 pre-flight shows comfortable RAM/CPU headroom AND a soak test shows
  zero live-call latency regression while the model is resident. State this bias explicitly so the
  build agent does not default to `SentenceTransformer(...)` inside the caller process.

### F6 [required, non-blocking — stale RAG after a brochure edit]: cache key omits `kb_version`.
§4b keys the blob cache by `(tenant_id, campaign_id, stage[, phone])` with no `kb_version`, but §4c's
payload and §4 prose claim a re-index "busts its cache (bump `kb_version`)". With a 24h TTL
(`RAG_CACHE_TTL_S`), a vendor who edits their knowledge sees **stale retrieved context for up to a
day**.
- **FIX:** Put `kb_version` **in the cache filename** (`var/rag_cache/<tenant>_<campaign>_<stage>[_<phone>]_kb<version>.json`)
  so a version bump is an automatic cache miss; OR have `index_campaign` **delete** that campaign's
  `var/rag_cache/*` files on every successful re-index. (Either is fine; the filename approach is
  self-healing and needs no delete sweep.) Store the campaign's current `kb_version` on the campaign
  record so `build_context_blob` can read it.

### F7 [required, non-blocking — lock the prefix-purity invariant for `knowledge`]: verified safe today, guard it.
Verified: `_coerce_fields` (`caller.py:1829`) does `out = dict(fields)` and only normalizes known keys
— it does **NOT** whitelist/drop unknowns, so a new `knowledge` field **passes through and persists**
(no coercion change strictly needed, though adding a `knowledge` string-normalize line is harmless and
recommended for BOM/whitespace hygiene). And `build_system_prompt` (`prompt.py`) provably never reads
`knowledge` today → it cannot enter the Groq-cached prefix. The risk is a **future** edit bloating the
prefix.
- **FIX:** (a) add `knowledge` to the string-normalize loop in `_coerce_fields` (hygiene, optional);
  (b) **lock the invariant** in §1: `knowledge` (and any RAG/chunk content) MUST NEVER be referenced
  inside `build_system_prompt`/the cached prefix — only chunked into `campaign_knowledge_chunks` and
  injected via the suffix. (c) **Strengthen the Step-6 byte-identical check:** assert it on a campaign
  that **has a non-empty `knowledge` field** (not just any campaign) — i.e. prove the cached prefix is
  byte-identical *even when knowledge is present*, catching any accidental prefix contamination.

### Anchor precision (non-blocking, fix for the build agent)
- §0 / §4c: move the dial-site anchor up to **`caller.py:1642`** — `room = f"famit-{num[1:]}-{...}"`
  is the variable the **entire** file-delivery channel depends on, and it sits **one line above** the
  cited `1644-1654` `md_obj` block. The write of `var/rag_context/<room>.json` must happen in the
  **1642→1656 window (BEFORE `create_dispatch`/`create_sip_participant`)** and be **awaited /
  synchronous, NOT fire-and-forget**, so the file is guaranteed on disk before the agent connects and
  reads it (no race). (Embedding for that write is still off-loop via the cache/`run_in_executor`
  path; only the tiny final file-write is in-line.)
- §4a indexing hook: the campaign-save handler is `async def create_campaign` /
  `async def update_campaign`, but the actual persist is the **synchronous** `save_campaign(fields,
  tenant_id)` (`caller.py:1924`). Fire the off-thread `index_campaign(...)` in the **async handler
  AFTER** `save_campaign(...)` returns (not inside `save_campaign`) — exactly as §4a says; just noting
  `save_campaign` itself is sync so don't `await` it.
- `_finalize_call` (`caller.py:1472`) is `async def` with `(it, now_t, tenant_id, cid, camp_fields)`
  in scope and `rec["phone"]` available → the §6(c) `lead_memory` upsert fits as one more best-effort
  `await` at the end (mirror the existing `_charge_call`/`_update_lead_after_call` calls); wrap in
  try/except so it never breaks finalize.

### Net acceptance-test deltas (add these to §9)
- **Step 2:** (i) `famit_app` cannot `CREATE EXTENSION vector` (F1); (ii) `objection_vectors` rejects an
  `INSERT` of a `tenant_id=''` row under a tenant GUC but allows reading globals (F2).
- **Step 5:** concurrent-launch check spans **two tenants**; assert no cross-tenant chunk bleed in the
  written `rag_context` files (F3).
- **Step 6:** byte-identical-when-off check runs on a campaign **carrying a `knowledge` blob** (F7).
- **Step 7:** p95 `llm_ttft` is computed by **parsing `famit-agent` logs**, not `/metrics` (F4).
