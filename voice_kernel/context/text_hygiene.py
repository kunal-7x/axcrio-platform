"""voice_kernel.context.text_hygiene — self-contained text normalization +
injection-defense for vendor-supplied campaign content.

This MIRRORS the live `droplet_work/prompt.py` hardening (`_clean_render_text`,
`_escape_vendor_script_render`) but imports NOTHING from droplet_work — the
voice_kernel isolation guarantee (test asserts zero droplet imports). Keeping a
disjoint copy is deliberate: the kernel must stay importable by
aim_voice_agent.py without dragging in the live agent.

Responsibilities:
  - normalize(): NFKC + strip zero-width + drop control chars (keep \t\n\r).
    This is hardening, NOT lossy compression — length is preserved (no clamp
    here; lossless preservation is the whole point of W3's dual-layer fix).
  - defang_fences(): neutralize any forged fence open/close tag a vendor might
    paste to break OUT of its CAMPAIGN_BRIEF/vendor_script fence. The platform
    safety layer always sits ABOVE the fence by position (C3), and the vendor's
    content can never re-open the fence to escalate to instructions.

Pure-stdlib only (unicodedata / re). Idempotent.
"""
from __future__ import annotations

import re
import unicodedata

# The exact zero-width / bidi set the live prompt.py strips. Keeping it
# byte-identical means a brief cleaned here renders identically to the live path.
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

# Any forged fence tag a vendor could paste to escape its container. We defang
# the OPENING bracket of any of our typed fences (campaign_brief, vendor_script,
# vendor_data, retrieved_knowledge, lead_memory, caller_utterance) AND of a raw
# `vendor_*` tag — turning `<` into the full-width `＜` so it can never be parsed
# as a real tag, while staying human-readable in a trace.
_FENCE_NAMES = (
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

    LOSSLESS hardening — does NOT truncate. Returns "" for None/empty.
    """
    if not s:
        return ""
    text = unicodedata.normalize("NFKC", str(s))
    text = text.translate(_ZW_TABLE)
    text = "".join(ch for ch in text if ch in ("\t", "\n", "\r") or ord(ch) >= 0x20)
    return text


def defang_fences(text: str) -> str:
    """Neutralize any forged fence open/close tag so vendor content cannot break
    out of the fence the renderer wraps it in. Idempotent. Self-contained."""
    if not text:
        return text or ""
    return _FORGED_TAG_RE.sub(lambda m: "＜" + m.group(1), text)


def sanitize(s: object) -> str:
    """The full hygiene pass for any untrusted vendor text BEFORE it is fenced:
    normalize then defang. LOSSLESS (no truncation) — preserves the full brief
    verbatim so W3's dual-layer "preserve raw" guarantee holds."""
    return defang_fences(normalize(s))
