"""voice_kernel.rag — the stage-aware, low-latency, degrade-to-empty RagRuntime.

W4. Fixes the founder's "uploaded PDFs are not retrieved at call time" bug by
giving the kernel a REAL RagRuntime impl (the kernel currently runs NullRagRuntime
-> always empty). This package is:

  * STAGE-AWARE   — retrieval store(s) chosen by dialogue Stage (stores.py); cheap
                    stages (greet/intro) retrieve nothing.
  * SELECTIVE     — per-turn retrieve reads the HOT CACHE only; the DB/embed cost
                    is paid in precompute (WARM, at dial), off the hot path.
  * 4 STORES      — campaign-facts / playbook / objection-bank / slots
                    (lead-memory is the separate MemoryService contract).
  * TENANT-SCOPED — tenant-first cache keys + is_admin=False corpus reads (RLS).
  * DEGRADE-EMPTY — any failure/timeout -> empty TurnLayer; NEVER raises/blocks.
  * FENCED        — results render as SourceTrust.RETRIEVED_KNOWLEDGE (untrusted).

It NEVER imports or edits droplet_work (agent.py/caller.py/kb): the production
corpus backend (KbCorpusBackend) wraps droplet_work/kb/core.py via a LAZY,
read-only file-path import, so `import voice_kernel.rag` pulls in zero droplet
modules and every backend is mockable in a test.

Register into the kernel:

    from voice_kernel import build_kernel, KernelConfig
    from voice_kernel.rag import build_rag_runtime, register_rag
    k = register_rag(build_kernel(KernelConfig()))          # production defaults
    # or, with explicit backends (tests / custom):
    k = build_kernel(KernelConfig(), rag=build_rag_runtime(corpus=my_corpus, cache=my_cache))

`register_rag` is OFF-safe: it only swaps the kernel's `rag` service; nothing is
retrieved into a LIVE prompt until KERNEL_ENABLED + the precompute-at-dial wiring
wave (see design/W4-RAG-SEAM.md). With the kernel OFF (default) the live call is
byte-identical regardless of whether a rag runtime is registered.
"""
from __future__ import annotations

from typing import Optional

from .backends import (
    CorpusBackend,
    CorpusHit,
    HotCache,
    InMemoryCorpusBackend,
    InProcHotCache,
    KbCorpusBackend,
    RedisHotCache,
)
from .config import RagConfig
from .ingest import (
    IndexStatus,
    IngestResult,
    Ingestor,
    PlainTextExtractor,
    TextExtractor,
)
from .runtime import RetrieveTrace, StageAwareRagRuntime, build_rag_runtime
from .stores import (
    STAGE_STORES,
    RagStore,
    StoreScope,
    is_retrieval_stage,
    scope_for,
    stores_for_stage,
)


def register_rag(kernel, *, corpus=None, cache=None, cfg: Optional[RagConfig] = None):
    """Swap the kernel's RagRuntime to the real stage-aware impl, in place.

    Returns the same kernel (so it can be chained). OFF-safe: the swap changes
    NOTHING about the live (KERNEL_ENABLED-OFF) path — the adapter returns the
    legacy string before any kernel service is touched. Only matters once the
    kernel is ON and the precompute-at-dial seam is wired (W4-RAG-SEAM.md).
    """
    kernel.svc.rag = build_rag_runtime(corpus=corpus, cache=cache, cfg=cfg)
    return kernel


__all__ = [
    # runtime
    "StageAwareRagRuntime",
    "build_rag_runtime",
    "register_rag",
    "RetrieveTrace",
    # config
    "RagConfig",
    # stores
    "RagStore",
    "StoreScope",
    "STAGE_STORES",
    "stores_for_stage",
    "is_retrieval_stage",
    "scope_for",
    # backends
    "CorpusBackend",
    "CorpusHit",
    "HotCache",
    "KbCorpusBackend",
    "InMemoryCorpusBackend",
    "InProcHotCache",
    "RedisHotCache",
    # ingestion
    "Ingestor",
    "IngestResult",
    "IndexStatus",
    "TextExtractor",
    "PlainTextExtractor",
]
