"""voice_kernel.memory.hygiene — self-contained write-side text hygiene.

Mirrors `voice_kernel/context/text_hygiene.py` (NFKC + zero-width strip + fence
defang) but is SELF-CONTAINED so the memory module does NOT depend on the W3
`context` package's eager `__init__` (which has a load-order coupling that can
re-enter mid-import). Keeping a disjoint copy is the same deliberate isolation
choice W3 itself made vs droplet_work: a leaf module that any path can import
without dragging in a heavier package. Pure-stdlib (re / unicodedata). Idempotent.

S4 (W7 decisions): sanitize on WRITE so a prompt-injected prior call cannot
smuggle an invisible fence-breakout into the store. The packet renderer fences
the stored memory on READ (FencedText(SourceTrust.LEAD_MEMORY)); this is the
write leg.
"""
from __future__ import annotations

import re
import unicodedata

# The zero-width / bidi set the live prompt.py + W3 text_hygiene strip — kept
# byte-identical so a value cleaned here renders identically to the live path.
_ZERO_WIDTH = "".join(
    (
        "​",  # zero-width space
        "‌",  # zero-width non-joiner
        "‍",  # zero-width joiner
        "‎",  # LRM
        "‏",  # RLM
        "⁠",  # word joiner
        "﻿",  # BOM / zero-width no-break space
        "­",  # soft hyphen
        "᠎",  # Mongolian vowel separator
    )
)
_ZW_TABLE = {ord(c): None for c in _ZERO_WIDTH}

# Any forged fence tag a poisoned prior summary could paste to escape its
# LEAD_MEMORY container. Defang the OPENING bracket of any typed fence (and a raw
# vendor_* / platform tag) by turning `<` into full-width `＜` so it can never be
# parsed as a real tag, while staying human-readable in a trace.
_FENCE_NAMES = (
    "platform",
    "campaign_brief",
    "vendor_script",
    "vendor_data",
    "retrieved_knowledge",
    "lead_memory",
    "caller_utterance",
)
_FORGED_TAG_RE = re.compile(
    r"<(\s*/?\s*(?:vendor_\w+|" + "|".join(_FENCE_NAMES) + r")\b)",
    re.IGNORECASE,
)


def normalize(s: object) -> str:
    """NFKC-normalize + strip zero-width + drop control chars (keep \\t\\n\\r).
    LOSSLESS hardening (no truncation). Returns "" for None/empty."""
    if not s:
        return ""
    text = unicodedata.normalize("NFKC", str(s))
    text = text.translate(_ZW_TABLE)
    text = "".join(ch for ch in text if ch in ("\t", "\n", "\r") or ord(ch) >= 0x20)
    return text


def defang_fences(text: str) -> str:
    """Neutralize any forged fence open/close tag so stored memory cannot break
    out of the LEAD_MEMORY fence the renderer wraps it in. Idempotent."""
    if not text:
        return text or ""
    return _FORGED_TAG_RE.sub(lambda m: "＜" + m.group(1), text)


def sanitize(s: object) -> str:
    """Full write-side hygiene: normalize then defang. LOSSLESS (no truncation —
    the caller clamps separately)."""
    return defang_fences(normalize(s))
