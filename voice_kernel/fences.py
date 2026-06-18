"""voice_kernel.fences — the canonical forged-fence-tag defanger (leaf module).

This is the SINGLE SOURCE OF TRUTH for `defang_fences`. It lives at the package
ROOT (not under context/) so that BOTH:

  - `packet.py` (the renderer — imported BY context/, so it cannot import back into
    context/ without a circular import), and
  - `context/text_hygiene.py` (the save-time hygiene pass, which re-exports this),

can share one implementation with NO import cycle. Pure-stdlib (`re` only).

Why this matters (RED-TEAM finding): forged fence tags must be neutralized at the
RENDER choke point (FencedText.render in packet.py), not only at save-time. A
poisoned PDF page (RETRIEVED_KNOWLEDGE) or a legacy/unsanitized lead-memory row
(LEAD_MEMORY) reaches the prompt via the per-turn / per-call renderer, which is
BELOW any save-time sanitize. Defanging at render() closes every fence vector at
once and makes the FencedText type's promise ("untrusted content can never escape
its fence") structurally true rather than dependent on every upstream writer
remembering to sanitize.
"""
from __future__ import annotations

import re

# Every typed fence tag in the kernel. Defanging the OPENING bracket of any of
# these (open OR close form) turns `<` into the full-width `＜`, so a vendor /
# PDF / poisoned-memory payload can never inject a real `</fence>` to break out
# or a `<fence>` to re-open and escalate to instructions. Kept human-readable in
# a trace. MUST stay in sync with packet._FENCE_TAG keys.
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


def defang_fences(text: str) -> str:
    """Neutralize any forged fence open/close tag so untrusted content cannot
    break out of the fence the renderer wraps it in. Idempotent. Pure-stdlib.

    Replaces the ASCII `<` of any kernel fence tag (and any `vendor_*` tag) with
    the full-width `＜` (U+FF1C), so it can never be parsed as a real tag while
    remaining legible in a trace.
    """
    if not text:
        return text or ""
    return _FORGED_TAG_RE.sub(lambda m: "＜" + m.group(1), text)
