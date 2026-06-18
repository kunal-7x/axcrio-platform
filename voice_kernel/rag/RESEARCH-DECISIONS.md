# W4 voice_kernel/rag — RESEARCH DECISIONS (stage-aware low-latency RAG)

Branch: fix/realtime-voice-kernel-v2. Binds FROZEN contracts in voice_kernel/contracts.py
(Protocol RagRuntime async/timeout-bounded/degrade-to-empty; RagSnippet; FencedText/
fence(SourceTrust.RETRIEVED_KNOWLEDGE); KernelSession tenant scoping; build_kernel(cfg, rag=impl)).
EARNER LAW: do NOT edit agent.py/caller.py/aim_voice_agent.py/kb/ — build NEW logic here; wrap kb/.

## 0. The seam we bind to (already frozen in code — do not change)
- `RagRuntime.precompute(ctx: CallContext) -> None` — WARM, at dial. Warms a room/turn cache.
- `RagRuntime.retrieve(turn, k=3, timeout_s=0.03) -> TurnLayer` — per-turn, MUST be <=timeout,
  MUST degrade to empty TurnLayer on timeout/error, NEVER raise. Kernel runs it PARALLEL to a
  preemptive LLM start (kernel.py:183 retrieve_turn_layer wraps it in asyncio.wait_for) and only
  appends L5 if it returns within deadline. So: retrieve is best-effort enrichment, not a gate.
- Output is `TurnLayer.rag_snippets: tuple[RagSnippet,...]` (<=3), each RagSnippet.text clamped
  to 120 chars, fenced as SourceTrust.RETRIEVED_KNOWLEDGE (packet.py already does the fence+clamp).

## 1. FOUR RETRIEVAL CLASSES (stage/dialogue-mode aware) — decided
Map each class to WHEN it is fetched and HOW, by latency tolerance:
| Class | Content | Fetched | Path | Latency tolerance |
|---|---|---|---|---|
| campaign-facts | product/price/USP/objection-answers (the L3 card overflow + brochure/FAQ) | PRECOMPUTE at dial (warm) + speculative prefetch per turn | dense+sparse hybrid, cached | high (off hot path) |
| playbook | telecaller technique per stage (objection rebuttal patterns, closing lines, push-without-pushy) | PRECOMPUTE per (use_case,stage) at dial — small, static, mode-keyed | mostly sparse/keyword on a small curated corpus; can be a static dict, not even vector | high |
| lead-memory | this lead's prior-call facts | already a SEPARATE contract (MemoryService L4, one PG row at dial). NOT in RagRuntime. | — | n/a (W7 owns) |
| analytics-archive | aggregate "what worked across calls" | NEVER on hot path; offline → feeds playbook/card tuning | batch | n/a |
DECISION: RagRuntime owns campaign-facts + playbook ONLY. lead-memory stays in MemoryService
(don't duplicate). analytics-archive is offline and feeds the corpus, never queried live.

## 2. PER-DIALOGUE-MODE retrieval (stage-aware) — decided
- The query is built from `turn.stage` (Stage enum) + `turn.user_text`, not user_text alone.
  Stage biases the class: OBJECTION/QUALIFY stage → weight playbook + objection-answers;
  BOOKING/CLOSE → weight closing-lines + price/offer facts; GREET/INTRO → usually EMPTY (no
  retrieval needed, return empty fast — saves the budget).
- Precompute at dial fans out the *predictable* stages: for a SALES call we know the stage path
  (greet→qualify→objection→booking→close), so precompute warms the cache for each stage's likely
  queries ONCE, off the hot path. This is the VoiceAgentRAG "Slow Thinker predicts 3-5 follow-up
  topics, embeds, searches, caches" pattern — done at dial + opportunistically between turns.

## 3. HYBRID dense+sparse — decided (pgvector HNSW now, Qdrant RRF later)
- NOW: pgvector. Sparse = Postgres FTS (tsvector + GIN, `plainto_tsquery` + `ts_rank_cd`).
  Dense = pgvector HNSW. Index params (researched): `WITH (m=16, ef_construction=200)`; runtime
  `SET hnsw.ef_search = 40..100` (40 default; raise only if recall short). HNSW ~1.5x faster than
  tuned IVFFlat at equal recall and needs less tuning → HNSW is the default for a low-latency RAG.
  Partial/filtered index per tenant via `WHERE tenant_id=...` or metadata filter + pre-filter by
  distance; use `hnsw.iterative_scan='strict_order'` for filtered queries so the tenant filter
  doesn't blow recall.
- FUSION: Reciprocal Rank Fusion (RRF), `score = Σ 1/(k+rank)`, k=60. RRF fuses dense+sparse on
  RANK not score (avoids score-incompatibility), rewards cross-retriever agreement. Hybrid is
  +8-15% accuracy over either alone.
- LATER: Qdrant native hybrid (server-side RRF) when corpus/scale warrants — the RRF contract
  stays identical, only the backend swaps. The Protocol does not change.

## 4. RERANKING — decided: OFF on the hot path, by default
- Cross-encoder rerank is +precision but adds a model RTT (tens-hundreds of ms) → blows the 30ms
  retrieve budget. DECISION: NO live cross-encoder in retrieve(). Ranking = RRF only on the hot
  path. Reranking, if ever, runs in PRECOMPUTE (off hot path) to pre-order the cached candidate
  set, so the per-turn read is already ranked. Keep a flag `RAG_RERANK_PRECOMPUTE` default OFF.

## 5. REDIS HOT-CACHE <50ms (precompute-while-user-speaks) — decided
- Two-tier, mirrors VoiceAgentRAG dual-agent (Slow Thinker=precompute, Fast Talker=retrieve):
  - L0 in-process dict keyed by (tenant,campaign,stage,query_hash) — FAISS/IndexFlatIP-style or
    just exact+near-dup key match. Cache HIT = sub-ms (paper: 0.35ms vs 110ms DB = 316x).
  - L1 Redis (shared across workers; survives) — vector/semantic cache, median ~40ms, classify
    20-50ms. Similarity threshold for a semantic hit 0.7-0.95 (use ~0.9 for facts — high
    precision, never serve a wrong fact). Dedup near-dup at >0.95.
- PRECOMPUTE-WHILE-SPEAKING: the kernel already starts the LLM preemptively and runs retrieve in
  parallel with a 30ms deadline. We ADD: speculative prefetch — while STT is still streaming the
  user's utterance (and between turns), `precompute`/an opportunistic warm task predicts the next
  stage's queries and fills Redis, so the per-turn retrieve is a cache HIT (sub-ms), not a DB hop.
  Target warm-cache hit rate 75-86% by turn 5+ (paper). The 30ms `timeout_s` is the HARD ceiling;
  a cache miss simply returns empty (degrade-to-empty) and the turn proceeds with no L5 — no dead
  air, no blocking.

## 6. LATENCY BUDGET (the per-turn voice budget; our slice)
Total natural voice budget ~200ms ideal / <800ms enterprise ceiling. Our retrieve slice:
- HARD ceiling = `timeout_s=0.03` (30ms) — kernel enforces via asyncio.wait_for; over → empty.
- Cache HIT (L0 dict): <1ms. Cache HIT (Redis): ~5-15ms LAN. Cache MISS: do NOT pay the 50-300ms
  DB+embed cost on the hot path — return empty, let precompute fill it for next turn. The DB/embed
  cost (embed ~200ms remote, pgvector 2-300ms) is ONLY ever paid in precompute (off hot path) or
  behind a spoken filler (the lookup-tool seam), NEVER inside retrieve()'s 30ms window.
- This matches the existing earner law (RAG-MASTER-PLAN C-2/C-3): no live embed/PG on the per-turn
  reply path; dense is connect/precompute-only; FTS-only on any reply-path fallback.

## 7. DEGRADE-TO-EMPTY (the safety contract) — already enforced, we honor it
- retrieve() returns `TurnLayer(stage, detected_lang)` with empty rag_snippets on ANY of: timeout,
  Redis down, embedder unset, corpus empty, tenant mismatch. NEVER raises. Kernel logs + drops L5.
- precompute() is fire-and-forget; failure is non-fatal (kernel.py:162-167 already swallows).
- Tenant isolation: every query carries KernelSession.tenant_id; cache keys are tenant-scoped;
  PG read is the caller's own is_admin=False GUC + explicit `tenant_id=... OR tenant_id='_global'`
  (never `%`, never is_admin=True) — same rule the live kb hardening (W1) already proved.

## 8. EMBEDDING / STORE CHOICES — decided
- Embedding: OpenAI text-embedding-3-small (256d to cut index size + distance cost; 1536d is the
  default but 256d is the cost/latency pick and is FOUNDER-SIGNED/Phase-2 per master plan). Embed
  is PRECOMPUTE-only. Until EMBED key is set, dense is OFF → FTS-only → still works (degrade).
- Store now: pgvector HNSW + FTS in the same Postgres (one round trip, RLS isolation). Wrap the
  existing kb/ corpus read-only; build NEW ranking/cache logic in voice_kernel/rag/.
- Hot cache: in-proc dict (L0) + Redis (L1, reuse the EventBus Redis). FAISS optional for L0 if
  we want semantic (not exact) in-proc hits.

## 9. SEAM NOTE (for the LATER flag-gated precompute-at-dial wave — do NOT wire now)
- precompute() should be called by caller.py run_job at DIAL (the last caller-owned moment), result
  delivered to the agent via a per-call file/Redis key the agent already reads, injected ONCE at
  the recap seam — exactly the dynamic-context-rag.md pattern. That wiring is a SEPARATE
  founder-signed wave; here we BUILD+TEST the module against the Protocol with the null/Redis
  backends, write this note, and DO NOT touch the earner files.
