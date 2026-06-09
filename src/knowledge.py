from __future__ import annotations

import math
import os
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path


SUPPORTED_EXTENSIONS = {".md", ".txt", ".csv"}
TOKEN_RE = re.compile(r"[\w\u0900-\u097F]+", re.UNICODE)
IGNORED_FILENAMES = {"readme.md", "_readme.md"}
STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "for",
    "from",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "the",
    "to",
    "with",
    "hai",
    "hain",
    "ho",
    "ka",
    "ke",
    "ki",
    "ko",
    "kya",
    "me",
    "mein",
    "mujhe",
    "se",
    "है",
    "हैं",
    "का",
    "के",
    "की",
    "को",
    "में",
    "से",
}


@dataclass(frozen=True)
class KnowledgeHit:
    source: str
    heading: str
    text: str
    score: float


@dataclass(frozen=True)
class KnowledgeChunk:
    source: str
    heading: str
    text: str
    tokens: tuple[str, ...]
    term_counts: Counter[str]


def env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    return int(value)


def env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None:
        return default
    return float(value)


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def tokenize(text: str) -> list[str]:
    return TOKEN_RE.findall(text.casefold())


def _query_terms(query: str) -> list[str]:
    terms = [token for token in tokenize(query) if len(token) > 1 and token not in STOP_WORDS]
    return terms or tokenize(query)


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _split_long_text(text: str, max_chars: int) -> list[str]:
    if len(text) <= max_chars:
        return [text]

    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + max_chars, len(text))
        split_at = max(text.rfind(". ", start, end), text.rfind("? ", start, end))
        if split_at <= start + max_chars // 2:
            split_at = end
        else:
            split_at += 1
        chunks.append(text[start:split_at].strip())
        start = split_at
    return [chunk for chunk in chunks if chunk]


def _make_chunk(source: str, heading: str, text: str) -> KnowledgeChunk:
    tokens = tuple(tokenize(f"{heading} {text}"))
    return KnowledgeChunk(
        source=source,
        heading=heading,
        text=_clean_text(text),
        tokens=tokens,
        term_counts=Counter(tokens),
    )


def _section_chunks(source: str, text: str, chunk_chars: int) -> list[KnowledgeChunk]:
    heading = Path(source).stem.replace("_", " ").replace("-", " ").strip() or source
    current_heading = heading
    paragraphs: list[str] = []
    chunks: list[KnowledgeChunk] = []

    def flush() -> None:
        nonlocal paragraphs
        if not paragraphs:
            return

        buffer = ""
        for paragraph in paragraphs:
            paragraph = _clean_text(paragraph)
            if not paragraph:
                continue
            if len(paragraph) > chunk_chars:
                for part in _split_long_text(paragraph, chunk_chars):
                    chunks.append(_make_chunk(source, current_heading, part))
                continue
            candidate = f"{buffer}\n{paragraph}".strip() if buffer else paragraph
            if len(candidate) > chunk_chars and buffer:
                chunks.append(_make_chunk(source, current_heading, buffer))
                buffer = paragraph
            else:
                buffer = candidate

        if buffer:
            chunks.append(_make_chunk(source, current_heading, buffer))
        paragraphs = []

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line.startswith("#"):
            flush()
            current_heading = line.lstrip("#").strip() or heading
            continue
        if not line:
            paragraphs.append("\n")
            continue
        paragraphs.append(line)

    flush()
    return chunks


class KnowledgeBase:
    def __init__(self, chunks: list[KnowledgeChunk]) -> None:
        self.chunks = chunks
        self._doc_freq: Counter[str] = Counter()
        for chunk in chunks:
            self._doc_freq.update(set(chunk.tokens))

    @classmethod
    def from_env(cls) -> KnowledgeBase:
        if not env_bool("KNOWLEDGE_ENABLED", True):
            return cls([])
        return cls.from_dir(
            os.getenv("KNOWLEDGE_DIR", "knowledge"),
            chunk_chars=env_int("KNOWLEDGE_CHUNK_CHARS", 900),
        )

    @classmethod
    def from_dir(cls, directory: str | os.PathLike[str], *, chunk_chars: int = 900) -> KnowledgeBase:
        root = Path(directory)
        if not root.exists():
            return cls([])

        chunks: list[KnowledgeChunk] = []
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                continue
            if path.name.casefold() in IGNORED_FILENAMES or path.name.startswith("_"):
                continue

            text = path.read_text(encoding="utf-8", errors="ignore")
            source = str(path.relative_to(root))
            chunks.extend(_section_chunks(source, text, chunk_chars))

        return cls(chunks)

    def search(self, query: str, *, limit: int = 3) -> list[KnowledgeHit]:
        terms = _query_terms(query)
        if not terms or not self.chunks:
            return []

        query_counts = Counter(terms)
        query_numbers = {term for term in terms if term.isdigit()}
        needs_exact_sector = "sector" in terms and bool(query_numbers)
        total_chunks = len(self.chunks)
        scored: list[KnowledgeHit] = []

        for chunk in self.chunks:
            searchable_text = f"{chunk.source} {chunk.heading} {chunk.text}".casefold()
            if needs_exact_sector and not any(
                f"sector {number}" in searchable_text
                or f"sector-{number}" in searchable_text
                or f"sector{number}" in searchable_text
                for number in query_numbers
            ):
                continue

            score = 0.0
            heading_tokens = set(tokenize(chunk.heading))
            source_tokens = set(tokenize(chunk.source))

            for term, query_count in query_counts.items():
                term_count = chunk.term_counts.get(term, 0)
                if not term_count:
                    continue

                idf = math.log((1 + total_chunks) / (1 + self._doc_freq[term])) + 1.0
                score += idf * min(term_count, 3) * min(query_count, 2)
                if term in heading_tokens:
                    score += idf * 0.5
                if term in source_tokens:
                    score += idf * 0.25

            if score <= 0:
                continue

            score = score / math.sqrt(max(len(chunk.tokens), 1))
            scored.append(
                KnowledgeHit(
                    source=chunk.source,
                    heading=chunk.heading,
                    text=chunk.text,
                    score=score,
                )
            )

        scored.sort(key=lambda hit: hit.score, reverse=True)
        return scored[:limit]

    def context_for(
        self,
        query: str,
        *,
        limit: int | None = None,
        max_chars: int | None = None,
    ) -> str:
        limit = limit if limit is not None else env_int("KNOWLEDGE_TOP_K", 3)
        max_chars = max_chars if max_chars is not None else env_int("KNOWLEDGE_MAX_CHARS", 1200)
        hits = self.search(query, limit=limit)
        min_score = env_float("KNOWLEDGE_MIN_SCORE", 0.45)
        hits = [hit for hit in hits if hit.score >= min_score]
        if not hits:
            return ""

        lines = [
            "Relevant business knowledge for this caller turn:",
            "Use this only when it helps answer the caller. If the answer is not present here, ask one short follow-up question instead of inventing details.",
        ]
        remaining = max_chars - sum(len(line) for line in lines)

        for hit in hits:
            snippet = _clean_text(hit.text)
            label = f"{hit.source}"
            if hit.heading and hit.heading != Path(hit.source).stem:
                label = f"{label} - {hit.heading}"
            prefix = f"- {label}: "
            available = remaining - len(prefix) - 1
            if available <= 80:
                break
            if len(snippet) > available:
                snippet = snippet[: available - 3].rstrip() + "..."
            line = prefix + snippet
            lines.append(line)
            remaining -= len(line)

        return "\n".join(lines) if len(lines) > 2 else ""
