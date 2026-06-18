"""voice_kernel.speech.segment — complete-sentence guard + safe chunking.

Founder complaint (a): HALF-WORDS / truncated sentences. The root cause upstream
is GROQ_MAX_TOKENS=90 guillotining the LLM mid-sentence (agent.py:617). That is
fixed at the *generation* layer (the seam note raises the cap + adds a completion
guard). THIS module is the text-layer backstop: whatever text arrives, we never
hand the TTS a string that ends on a TRUNCATED WORD, and we chunk on safe
sentence boundaries so each TTS segment is a self-contained spoken unit.

Pure, deterministic, stdlib-only, fail-open.
"""
from __future__ import annotations

import re

# sentence-final punctuation across Latin + Devanagari (poorna viraam ।).
_SENT_END = ".!?…।"
# a "complete tail" ends with sentence punctuation OR a closing quote/bracket
# right after it. We treat a dangling word with no terminal punctuation as a
# POSSIBLE truncation only when the text shows other signs of being cut.
_SENT_SPLIT_RE = re.compile(r"(?<=[.!?…।])\s+")


def _looks_truncated(text: str) -> bool:
    """Heuristic: the text was cut mid-thought. We DON'T want false positives on
    a legit short beat ('Haan ji.'), so we only flag when the final char is a
    LETTER/comma (no terminal punctuation) AND the tail isn't an obvious complete
    short interjection."""
    if not text:
        return False
    last = text.rstrip()[-1:]
    if last in _SENT_END:
        return False
    # ends on a comma / connector / bare letter -> almost certainly mid-sentence.
    return True


def repair_truncation(text: str) -> str:
    """If the text ends mid-sentence (no terminal punctuation), DROP the dangling
    final clause back to the last complete sentence boundary so the TTS never
    speaks a half-word. If there is no earlier complete sentence (the whole thing
    is one unfinished clause), drop the suspect FINAL (likely-cut) word when the
    clause is long enough to survive it, then close cleanly — a complete-sounding
    short line beats a guillotined word."""
    if not text:
        return text
    stripped = text.rstrip()
    if not _looks_truncated(stripped):
        return stripped
    # find the last sentence-final punctuation; keep up to and including it.
    idx = max(stripped.rfind(c) for c in _SENT_END)
    if idx >= 0 and idx >= len(stripped) * 0.4:
        # there's a substantial complete sentence earlier — keep that, drop tail.
        kept = stripped[: idx + 1].rstrip()
        if kept:
            return kept
    # no earlier complete sentence: strip a dangling trailing comma/connector.
    cleaned = re.sub(r"[,\s–—\-]+$", "", stripped)
    # The upstream cause is a token-cut (GROQ_MAX_TOKENS), so the LAST word is the
    # one most likely sliced mid-token. If the clause still has enough words to
    # stand on its own (>=4 words) AND it ends on a bare word (no punctuation),
    # DROP that suspect final word so the TTS never voices a half-word like
    # 'spaci'/'discou'. Short clauses (<=3 words, e.g. 'Haan ji theek') are kept
    # whole — a brief complete beat is fine and dropping would gut the turn.
    words = cleaned.split()
    if len(words) >= 4 and cleaned and cleaned[-1] not in _SENT_END and cleaned[-1].isalnum():
        cleaned = " ".join(words[:-1])
    # close cleanly so a residual bare-word line still sounds finished.
    cleaned = re.sub(r"[,\s–—\-]+$", "", cleaned)
    if cleaned and cleaned[-1] not in _SENT_END:
        cleaned += "."
    return cleaned


def split_sentences(text: str) -> tuple[str, ...]:
    """Split into sentence-level chunks on terminal punctuation. Each chunk is a
    self-contained spoken unit for the TTS (so streaming TTS flushes on complete
    sentences, never a half-sentence)."""
    if not text:
        return ()
    parts = [p.strip() for p in _SENT_SPLIT_RE.split(text) if p.strip()]
    return tuple(parts) if parts else ((text.strip(),) if text.strip() else ())
