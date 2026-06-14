"""kb — Platform Knowledge Base + RAG corpus module (design/platform-knowledge-rag.md).

The single tenant-scoped truth store every AI worker answers from. This package owns:
  * the canonical pgvector+FTS corpus (kb_sources / kb_documents / kb_chunks — kb/schema.sql),
  * a section-aware chunker,
  * an ingest path (chunk -> fts -> optional-embed -> upsert, RLS-scoped),
  * a hybrid retrieve core (FTS sparse leg = CORE/keyless; dense vector leg = dormant-until-embedder).

Import-safe-degrade: if Postgres (db.engine) is unavailable, every entry point no-ops
(available()->False, retrieve()->[], ingest()-> {ok:False, reason:'pg_unavailable'}). The live site is
untouched. The embedder is independently dormant: absent -> chunks store with embedding=NULL and
retrieval still works via FTS.

NOTHING in the live voice hot path imports this. Voice-path wiring (precompute-at-dial) is a later,
latency-budgeted unit (per platform-knowledge-rag §4.5 / §11).
"""
from __future__ import annotations

from .core import (  # noqa: F401
    available,
    chunk_text,
    ensure_schema,
    ingest,
    log_query,
    purge_query_log,
    retrieve,
    status,
)

# `_global` telecaller-corpus seeder (RAG W2). Import-safe: pulls in only stdlib + this package; the
# corpus JSON is read lazily inside seed(). Exposed as `kb.seed_global_corpus(...)` for the endpoint.
from .seed_global import seed as seed_global_corpus  # noqa: F401
