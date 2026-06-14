"""comm.lang — best-effort language detection for the brain's reply (Wave 2).

Spec: communication/COMMUNICATION-MASTER-PLAN.md §2.4 / WAVE 2 ("comm/lang.py (langdetect)").

The brain replies in natural Hinglish by default (Roman script), matching the voice earner's
persona. This module is an OPTIONAL hint: when the `langdetect` package is present we detect the
inbound language so a future wave can localise; when it is absent (the common box state) we
degrade to '' (no hint) and the brain's default Hinglish prompt stands.

EARNER / SAFETY LAW: ZERO I/O at import, NEVER raises, no agent.py import. The optional dep is
imported lazily inside detect() so importing this module never fails on a box without langdetect.
"""
from __future__ import annotations

import logging

_log = logging.getLogger("comm.lang")


def detect(text: str) -> str:
    """Return a best-effort BCP-47-ish language code for `text` (e.g. 'en', 'hi'), or '' when
    detection is unavailable / inconclusive. NEVER raises.

    Hinglish (Roman-script Hindi) typically detects as 'en' or a romance code — we do NOT act on
    that here (the brain's default prompt already handles Hinglish); this is purely a hint a later
    localisation wave can use. An empty / very short string -> '' (don't guess)."""
    t = (text or "").strip()
    if len(t) < 3:
        return ""
    try:
        from langdetect import detect as _ld  # type: ignore
    except Exception:  # noqa: BLE001 — optional dep absent -> no hint (the box default)
        return ""
    try:
        return str(_ld(t) or "")
    except Exception:  # noqa: BLE001 — LangDetectException etc. -> inconclusive
        return ""


def is_available() -> bool:
    """True iff the langdetect optional dep is importable (diagnostic only). NEVER raises."""
    try:
        import langdetect  # type: ignore  # noqa: F401
        return True
    except Exception:  # noqa: BLE001
        return False
