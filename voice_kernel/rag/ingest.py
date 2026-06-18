"""voice_kernel.rag.ingest — the INGESTION contract (PDF -> chunk -> embed -> index).

The founder's bug is two-sided: (a) uploaded PDFs are not RETRIEVED at call time
(the runtime fixes that), and (b) the upload path's success/failure was opaque —
a "green" upload could leave the corpus empty. This module makes ingestion a
typed contract with an EXPLICIT status that separates the two failure classes:

    IndexStatus.INDEXED        chunks landed in the corpus, retrievable.
    IndexStatus.EMPTY          extracted text had no chunks (bad/scanned PDF).
    IndexStatus.EXTRACT_FAILED could not get text out of the source.
    IndexStatus.INDEX_FAILED   text extracted + chunked, but the corpus write failed.
    IndexStatus.SKIPPED        duplicate (already indexed by checksum) — a no-op success.

This is the INDEXING side. RETRIEVAL failure is a SEPARATE concern (the runtime's
degrade-to-empty), and the two are never conflated — a future test UI must be
able to tell "your PDF never indexed" apart from "indexed fine, nothing matched".

PDF text extraction is pluggable (`TextExtractor`) and LAZY — importing this
module pulls in no PDF library. If no extractor is available, a PDF degrades to
EXTRACT_FAILED with a clear reason (never a crash). Plain-text/markdown ingestion
needs no extractor.

Indexing delegates to a CorpusBackend (kb/core.py in production), so chunking +
embedding + the FTS/pgvector write reuse the proven kb pipeline — we never
re-implement the store. We only own the typed status + the extract step.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional, Protocol, runtime_checkable

from .backends import CorpusBackend

log = logging.getLogger("voice_kernel.rag.ingest")


class IndexStatus(str, Enum):
    INDEXED = "indexed"
    SKIPPED = "skipped"  # duplicate checksum — already present (success, no-op)
    EMPTY = "empty"  # extracted but produced zero chunks
    EXTRACT_FAILED = "extract_failed"  # could not extract text from the source
    INDEX_FAILED = "index_failed"  # corpus write failed


@dataclass(frozen=True)
class IngestResult:
    """The typed outcome of one ingestion. `ok` is True only for INDEXED/SKIPPED.
    `retrievable` is True only when chunks are actually in the corpus now."""

    status: IndexStatus
    source_id: str = ""
    chunks: int = 0
    embedded: int = 0
    reason: str = ""
    title: str = ""

    @property
    def ok(self) -> bool:
        return self.status in (IndexStatus.INDEXED, IndexStatus.SKIPPED)

    @property
    def retrievable(self) -> bool:
        return self.status in (IndexStatus.INDEXED, IndexStatus.SKIPPED)

    def as_dict(self) -> dict:
        return {
            "status": self.status.value,
            "ok": self.ok,
            "retrievable": self.retrievable,
            "source_id": self.source_id,
            "chunks": self.chunks,
            "embedded": self.embedded,
            "reason": self.reason,
            "title": self.title,
        }


@runtime_checkable
class TextExtractor(Protocol):
    """Turns a raw source (bytes/path) into plain text. Pluggable + mockable.
    `extract` returns "" (never raises) when it cannot extract."""

    def supports(self, kind: str) -> bool: ...

    def extract(self, data: Any, *, kind: str) -> str: ...


class PlainTextExtractor:
    """Default extractor for text/markdown/already-extracted content. Handles
    str directly and bytes via utf-8 (errors ignored). Refuses PDFs (a PDF
    extractor must be injected) so a PDF without a real extractor surfaces
    EXTRACT_FAILED, not silent garbage."""

    def supports(self, kind: str) -> bool:
        return (kind or "").lower() in ("text", "txt", "md", "markdown", "paste", "")

    def extract(self, data: Any, *, kind: str) -> str:
        try:
            if isinstance(data, bytes):
                return data.decode("utf-8", errors="ignore")
            return str(data or "")
        except Exception as exc:  # noqa: BLE001
            log.warning("PlainTextExtractor.extract degraded: %r", exc)
            return ""


@dataclass
class Ingestor:
    """The ingestion pipeline: extract -> (delegate chunk+embed+index to the
    CorpusBackend) -> typed status. Holds a list of extractors tried in order.

    Production: `Ingestor(corpus=KbCorpusBackend(), extractors=[PdfExtractor(), PlainTextExtractor()])`.
    The kb backend does the chunk/embed/FTS/pgvector write (we reuse it); the
    Ingestor only owns extraction + the typed status mapping.
    """

    corpus: CorpusBackend
    extractors: list[TextExtractor] = field(default_factory=lambda: [PlainTextExtractor()])

    def _extract(self, data: Any, kind: str) -> str:
        if isinstance(data, str) and data.strip() and (kind or "").lower() in ("", "text", "paste", "md", "markdown"):
            return data
        for ex in self.extractors:
            try:
                if ex.supports(kind):
                    txt = ex.extract(data, kind=kind)
                    if txt and txt.strip():
                        return txt
            except Exception as exc:  # noqa: BLE001
                log.warning("extractor %s failed (try next): %r", type(ex).__name__, exc)
        return ""

    def ingest(
        self,
        tenant_id: str,
        data: Any,
        *,
        title: str = "",
        kind: str = "text",
        doc_type: str = "generic",
        scope: str = "business",
        channel_scope: str = "all",
        scope_campaign_id: str = "",
        scope_product_id: str = "",
    ) -> IngestResult:
        """Run one ingestion. NEVER raises — every failure is a typed status."""
        if not tenant_id:
            return IngestResult(IndexStatus.INDEX_FAILED, reason="no_tenant", title=title)

        text = self._extract(data, kind)
        if not text or not text.strip():
            return IngestResult(IndexStatus.EXTRACT_FAILED, reason=f"no_text_from_kind:{kind}", title=title)

        try:
            res = self.corpus.ingest(
                tenant_id,
                text,
                title=title,
                kind=kind,
                scope=scope,
                doc_type=doc_type,
                channel_scope=channel_scope,
                scope_campaign_id=scope_campaign_id,
                scope_product_id=scope_product_id,
            )
        except Exception as exc:  # noqa: BLE001
            return IngestResult(IndexStatus.INDEX_FAILED, reason=f"error:{type(exc).__name__}", title=title)

        return self._classify(res, title)

    @staticmethod
    def _classify(res: dict, title: str) -> IngestResult:
        """Map a kb/core.ingest() result dict to the typed IngestResult."""
        res = res or {}
        if not res.get("ok"):
            reason = str(res.get("reason", "unknown"))
            if reason in ("empty_content", "no_chunks"):
                return IngestResult(IndexStatus.EMPTY, reason=reason, title=title)
            return IngestResult(IndexStatus.INDEX_FAILED, reason=reason, title=title)
        reason = str(res.get("reason", ""))
        if reason == "duplicate_checksum":
            return IngestResult(
                IndexStatus.SKIPPED, source_id=str(res.get("source_id", "")), reason=reason, title=title
            )
        return IngestResult(
            IndexStatus.INDEXED,
            source_id=str(res.get("source_id", "")),
            chunks=int(res.get("chunks", 0) or 0),
            embedded=int(res.get("embedded", 0) or 0),
            reason=reason or "indexed",
            title=title,
        )
