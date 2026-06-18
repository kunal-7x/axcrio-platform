# W4 — voice_kernel RAG runtime (stage-aware, low-latency, degrade-to-empty)

Branch: fix/realtime-voice-kernel-v2. Binds FROZEN contracts (RagRuntime,
RagSnippet, FencedText/RETRIEVED_KNOWLEDGE, KernelSession tenant scoping,
build_kernel registration). EARNER LAW honored: NO edits to agent.py/caller.py/
aim_voice_agent.py/kb/. New logic in voice_kernel/rag/ only; kb/core.py WRAPPED
read-only via a lazy file-path import.

## Phase: BUILD

Built (all tracked, additive, import-safe, zero droplet imports):
- voice_kernel/rag/runtime.py — StageAwareRagRuntime (the RagRuntime impl).
  STAGE-AWARE (store per Stage), SELECTIVE (hot path = cache-only; DB cost in
  precompute), TENANT-SCOPED (tenant-first cache keys + is_admin=False reads),
  DEGRADE-TO-EMPTY (never raises/blocks), FENCED (RETRIEVED_KNOWLEDGE). Exposes
  retrieve_traced() = the retrieve-test entrypoint for a future test UI.
- voice_kernel/rag/backends.py — CorpusBackend + HotCache Protocols; KbCorpusBackend
  (lazy read-only wrap of droplet_work/kb/core.py), InProcHotCache (L0) +
  RedisHotCache (L0+L1, degrades to L0 if no Redis), InMemoryCorpusBackend (tests,
  tenant-isolated, no DB).
- voice_kernel/rag/stores.py — the 4 logical stores (CAMPAIGN_FACTS, PLAYBOOK,
  OBJECTION_BANK, SLOTS; lead-memory excluded = separate MemoryService contract)
  + STAGE_STORES policy (greet/permission/intro retrieve nothing).
- voice_kernel/rag/ingest.py — ingestion contract PDF->chunk->embed->index with
  typed IndexStatus separating INDEXING failure (EXTRACT_FAILED/INDEX_FAILED/EMPTY)
  from retrieval failure. Pluggable TextExtractor (PlainTextExtractor default;
  PDF extractor injectable). Delegates chunk/embed/write to the CorpusBackend (kb).
- voice_kernel/rag/config.py — RagConfig (knobs, all default-safe) + tenant-first
  cache_key (cross-tenant cache-bleed guard).
- voice_kernel/rag/__init__.py — register_rag(kernel) + build_rag_runtime factory.

Tests: voice_kernel/tests/test_rag_runtime.py — 22 tests, all green. Asserts:
stage-aware scoping (right store per stage; cheap stages empty), timeout -> empty
(not raise) via kernel deadline wrap, corpus/cache error -> empty, results fenced
RETRIEVED_KNOWLEDGE, tenant_id scopes retrieval (no cross-tenant bleed), flag-OFF
byte-identity 10/10, register_rag doesn't alter OFF path, 0 droplet imports, the
full ingestion status matrix, ingest->retrieve roundtrip, build_kernel registration
+ RagRuntime Protocol conformance. Full suite: 104 passed.

Seam doc: design/W4-RAG-SEAM.md — the LATER flag-gated precompute-at-dial
(caller.py:2852 run_job, 1644-1654 window) + recap-seam injection (agent.py:372-378)
with exact file:line + flags (KERNEL_ENABLED, RAG_INJECT_ENABLED default OFF) +
rollback + the wiring-wave verification gate. NOT wired this wave.

Surface registered via build_kernel: build_kernel(cfg, rag=build_rag_runtime(...))
or register_rag(build_kernel(cfg)). OFF-safe (live call byte-identical when
KERNEL_ENABLED off, proven).

## Phase: RED-TEAM (W4 RAG correctness attack)

Branch fix/realtime-voice-kernel-v2. Attacked the 3 brief vectors empirically
(throwaway probes, not committed):

1. STAGE-AWARE RELEVANCE — **BLOCKER FOUND + FIXED.** precompute() warmed the
   cache under key query=base_q (the product seed), but retrieve()'s turn-1
   fallback probes the SEED key query="" (`sha1("")[:16]=da39a3ee5e6b4b0d`).
   The two keys NEVER matched -> the entire precompute warm was DEAD and the
   FIRST objection/booking of every call returned EMPTY (RAG only kicked in
   turn 2+ via the background warm). FIX (runtime.py precompute): write the warm
   under the SEED key query="" for EVERY store of each retrieval stage (was only
   the top store), skip empty seeds (keeps miss->bg-warm alive). Corpus QUERY
   still uses base_q (relevance); only the cache SLOT changed. VERIFIED: first
   OBJECTION turn now hit=True n>=1 surfacing the objection answer; cold/unseeded
   tenant still degrades to empty (fallback intact).

2. PDF-uploaded-but-unanswered (indexing vs retrieval) — **HOLDS.** Ingestor
   returns EXTRACT_FAILED for a PDF with no extractor (not silent-empty), while a
   retrieve miss on an indexed-but-unmatched doc surfaces via the RetrieveTrace
   reason. The two failure classes are DISTINGUISHABLE (a test UI can tell "never
   indexed" from "indexed, no match"). No fix needed.

3. RAG is FALLBACK not every-turn — **HOLDS.** Hot-path retrieve() is cache-only:
   on a cold miss it returns EMPTY in <0.1ms with ZERO corpus calls on the hot
   path (verified by instrumenting backend.retrieve), then fires a background
   warm. Cheap stages (greet/permission/intro) retrieve nothing. RAG never
   blocks the reply.

Tests: test_rag_runtime.py 22/22 green; full kernel suite 169/169 green with
deterministic order (`-p no:randomly`). NOTE: under pytest-randomly shuffle,
test_w3_context.py shows order-dependent failures from a PRE-EXISTING W3 test-
isolation issue (global/import pollution between W3 and some earlier module) —
NOT caused by this RAG change (runtime.py is the only file touched; reverting it
does not change the W3 behaviour; RAG+W3 in fixed order = 37/37). Flagged for the
W3 owner; out of scope for this RAG red-team.

VERDICT: 1 RAG blocker found + FIXED + verified. SHIP the RAG module.
