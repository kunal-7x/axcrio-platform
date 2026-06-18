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
  - defang_fences(): re-exported from the leaf `voice_kernel.fences` module (the
    SINGLE source of truth, shared with packet.FencedText.render so the render
    choke point and the save-time pass can never drift). Neutralizes any forged
    fence open/close tag a vendor might paste to break OUT of its CAMPAIGN_BRIEF/
    vendor_script fence. The platform safety layer always sits ABOVE the fence by
    position (C3), and the vendor's content can never re-open the fence to
    escalate to instructions.

Pure-stdlib only (unicodedata / re). Idempotent.
"""
from __future__ import annotations

import unicodedata

# defang_fences lives in the leaf module so packet.py (which is imported BY
# context/, so it cannot import back into context/ without a cycle) and this
# save-time pass share ONE implementation. Re-exported here for back-compat.
from ..fences import defang_fences  # noqa: F401  (re-exported)

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


def sanitize(s: object) -> str:
    """The full hygiene pass for any untrusted vendor text BEFORE it is fenced:
    normalize then defang. LOSSLESS (no truncation) — preserves the full brief
    verbatim so W3's dual-layer "preserve raw" guarantee holds."""
    return defang_fences(normalize(s))
