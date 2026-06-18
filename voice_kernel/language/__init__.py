"""voice_kernel.language — SELF-CONTAINED per-turn adaptive language mirror.

Ports the LIVE OUTBOUND earner's proven per-turn language mirror
(droplet_work/langdetect.py + agent.py:_MirrorAgent.on_user_turn_completed) into
the SHARED kernel so BOTH inbound + outbound get identical, adaptive behaviour:
mirror the caller's language EVERY turn (Hindi->Hindi, English->English,
switch-back->switch), never hardcoded to one language.

Zero droplet_work imports, zero network — fully self-contained + unit-testable.

  detector  — classify_text / LanguageTracker / TTS-code mapping (script-ratio +
              lexicon + hysteresis).
  mirror    — mirror_turn() -> {reply_language, tts_lang_code, changed,
              instruction} (the per-turn decision the integrations wire in).
"""
from __future__ import annotations

from .detector import (
    DEFAULT_LANG,
    LANG_REPLY_INSTRUCTION,
    SPEAKABLE_TTS,
    LanguageTracker,
    classify_text,
    degrades_to_hindi,
    is_beta,
    is_speakable,
    reply_instruction,
    safe_tts_language_code,
    tts_language_code,
)
from .mirror import MirrorDecision, mirror_once, mirror_turn

__all__ = [
    # detector
    "DEFAULT_LANG",
    "SPEAKABLE_TTS",
    "LANG_REPLY_INSTRUCTION",
    "LanguageTracker",
    "classify_text",
    "tts_language_code",
    "safe_tts_language_code",
    "is_speakable",
    "degrades_to_hindi",
    "is_beta",
    "reply_instruction",
    # mirror
    "MirrorDecision",
    "mirror_turn",
    "mirror_once",
]
