# W4-RAG-SEAM — the LATER flag-gated precompute-at-dial + recap-seam wiring

Status: **BUILD-ONLY this wave.** The `voice_kernel/rag/` module is built + tested
against the frozen `RagRuntime` Protocol with mock backends. It is **NOT wired**
into any live earner file. This doc records the EXACT wiring for the SEPARATE,
founder-signed integration wave so it can be done surgically, one box-mutating
change at a time, with a revert path.

EARNER LAW (unchanged): live `droplet_work/agent.py` md5 = `98655dbf`. The wiring
wave does NOT edit `agent.py`/`caller.py`/`aim_voice_agent.py`/`kb/` to BUILD; it
adds the seam behind a default-OFF flag and proves a real outbound call rings
before + after.

---

## 0. What is built (this wave) vs what wires it (LATER)

BUILT now (tracked, additive, import-safe, zero droplet imports):
- `voice_kernel/rag/runtime.py` — `StageAwareRagRuntime` (the `RagRuntime` impl):
  stage-aware, cache-only hot path, degrade-to-empty, tenant-scoped, fenced.
- `voice_kernel/rag/backends.py` — `KbCorpusBackend` (LAZY wrap of `kb/core.py`),
  `InProcHotCache` + `RedisHotCache` (L0/L1), `InMemoryCorpusBackend` (tests).
- `voice_kernel/rag/stores.py` — the 4 logical stores + `STAGE_STORES` policy.
- `voice_kernel/rag/ingest.py` — the ingestion contract (PDF->chunk->embed->index)
  with the typed `IndexStatus` (INDEXED/SKIPPED/EMPTY/EXTRACT_FAILED/INDEX_FAILED).
- `voice_kernel/rag/config.py` — `RagConfig` + tenant-first `cache_key`.
- `voice_kernel/rag/__init__.py` — `register_rag(kernel)` + `build_rag_runtime`.
- tests: `voice_kernel/tests/test_rag_runtime.py` (22) + full suite (104) green.

NOT wired (this doc): the precompute call at dial, the per-call blob delivery, and
the per-turn `retrieve_turn_layer` call in the agent. All behind a default-OFF flag.

---

## 1. The seam coordinates (verified against live source, read-only)

| Concern | File:line | Today | Wiring change (LATER) |
|---|---|---|---|
| Dial metadata is lossy | `droplet_work/caller.py:2931` | `md_obj = {"campaign_id": cid, "lead_name": it.get("name","")}` | unchanged — keep dispatch metadata SMALL; deliver the RAG blob via a file (row below), never in `md`. |
| Precompute window | `droplet_work/caller.py:1644-1654` (the `md_obj` build window inside `run_job`, `caller.py:2852`) | builds dispatch | BEFORE `create_dispatch`/`create_sip_participant`: `await rag.precompute(call_ctx)` then write `var/rag_context/<room>.json`. Off the hot path, inside the dial/connect window. |
| Blob delivery channel | `var/rag_context/<room>.json` | n/a | the agent reads this per-call file at the recap seam (the same rail `mem.build_recap` uses). The caller-generated `room` precedes dispatch, so the file is written before the agent loads. |
| Recap seam (inject once) | `droplet_work/agent.py:372-378` (recap block, beside `mem.build_recap`; `instructions = base_instructions` follows) | injects per-call recap | append the precomputed RAG blob AFTER the recap block, behind `RAG_INJECT_ENABLED` (default OFF). Prefix above it is byte-unchanged. |
| Per-turn retrieve | agent turn loop (the `on_user_turn` / LLM-start seam) | no RAG | OPTIONAL phase 2: `asyncio.create_task(kernel.retrieve_turn_layer(turn, timeout_s=0.03))` PARALLEL to the preemptive LLM start; append the returned L5 suffix only if it resolves in time. The kernel already enforces the deadline (`kernel.py:183 retrieve_turn_layer`). |

`run_job` entry: `droplet_work/caller.py:2852 async def run_job(job_id)`.
Recap seam: `droplet_work/agent.py:372-378` (`_load_campaign` helper at `agent.py:120`).

---

## 2. The flags (all default-OFF; placement matters)

- `KERNEL_ENABLED` (existing, `voice_kernel/config.py`) — master kernel switch.
  The rag runtime only ever feeds a LIVE prompt when the kernel is ON. With it
  OFF (default) `register_rag` changes the call NOT AT ALL (proven:
  `test_flag_off_byte_identity_10x`, `test_register_rag_does_not_alter_off_path`).
- `RAG_INJECT_ENABLED` (NEW, wiring wave) — gates the recap-seam injection in
  `agent.py`. Default OFF. Indexing + precompute can run with injection OFF (the
  corpus warms, nothing reaches the prompt) — the safe rollout step.
- `RAG_DENSE_ENABLED` (`voice_kernel/rag/config.py`) — dense (pgvector) leg.
  Default OFF; dense is PRECOMPUTE-ONLY, the hot retrieve forces `dense=False`.
- `RAG_RETRIEVE_TIMEOUT_S` (default 0.03), `RAG_CACHE_TTL_S` (default 300),
  `RAG_TOP_K` (default 3), `RAG_FANOUT` (default 6), `RAG_INCLUDE_GLOBAL` (default 1).
- `REDIS_URL` / `RAG_REDIS_URL` — if set + reachable, `RedisHotCache.from_env()`
  layers L1 Redis; otherwise it degrades to L0-only (never raises).

LEARNINGS §2: a kernel/inbound flag set in the SHARED `.env` leaks to the outbound
earner on its next restart. `RAG_INJECT_ENABLED` for inbound MUST be set via the
systemd drop-in (`voice_kernel/systemd/`), NOT the shared `.env`. Outbound live
injection stays gated on `KERNEL_ENABLED` (the human-gated G3 step).

---

## 3. The wiring code shape (LATER — illustrative, NOT applied here)

```python
# caller.py run_job, in the 1644-1654 dial window (BEFORE create_dispatch):
from voice_kernel import build_kernel, KernelConfig, KernelSession
from voice_kernel.contracts import CallContext
from voice_kernel.rag import register_rag
kernel = register_rag(build_kernel(KernelConfig.from_env()))   # production backends
session = KernelSession(tenant_id=tenant_id, call_id=room)      # server-stamped
call_ctx = CallContext(meta=meta, fields=fields, session=session)
await kernel.precompute(call_ctx)                              # WARM cache at dial
# (optionally) write var/rag_context/<room>.json for the agent to read.
```

```python
# agent.py recap seam (after agent.py:377), behind RAG_INJECT_ENABLED:
if os.getenv("RAG_INJECT_ENABLED", "0") in ("1","true","True"):
    blob = _load_rag_context(room_name)        # reads var/rag_context/<room>.json
    if blob:
        base_instructions = base_instructions + "\n\n" + blob   # append, prefix unchanged
```

The agent NEVER imports `voice_kernel` directly on the reply path beyond reading a
precomputed file — the heavy module stays caller-side. Per-turn `retrieve` is the
optional phase-2 task, parallel to the LLM start, deadline-bounded by the kernel.

---

## 4. Rollback

- Phase-1 (indexing+precompute, injection OFF): nothing reaches the prompt — revert
  is just `RAG_INJECT_ENABLED=0` (already the default) + restart. Corpus stays warm.
- Phase-2 (injection ON): flip `RAG_INJECT_ENABLED=0` → the prompt instantly reverts
  to today's (campaign brain + recap). No code revert needed; flag-only.
- Full revert: `KERNEL_ENABLED=0` (default) → the adapter returns the legacy string
  before any kernel/rag code runs. The earner is byte-identical to today.

---

## 5. Verification gate for the wiring wave (must pass before + after)

1. A REAL outbound call rings + completes (the earner) — before AND after the change.
2. `md5 droplet_work/agent.py` == `98655dbf` (BUILD-only; agent.py untouched to ship).
3. `python -m pytest voice_kernel/tests/` green (currently 104 passed).
4. With `RAG_INJECT_ENABLED=0`: prompt is byte-identical to today (the OFF identity).
5. A test PDF ingested via the `Ingestor` returns `IndexStatus.INDEXED` and a
   subsequent OBJECTION-stage retrieve surfaces its chunk (the founder's bug fixed).
