"""voice_kernel.brain_packs.language — the casual-Hinglish layer (W6 §E).

The live bug: the brain spoke literary/Sanskritised Hindi ("mahatvapurn") and
sounded alien. This module encodes the "stop sounding like a textbook" rules as
BEHAVIOR guidance (banned literary words -> preferred spoken equivalents,
rendering rules, language-mirroring rule). It ships NO campaign content.

Pure stdlib. Imports ZERO droplet_work modules.
"""
from __future__ import annotations

import re

# BANNED literary / Sanskritised tokens (never use). Each maps to a preferred
# casual spoken equivalent. The brain is told to AVOID the left and PREFER the
# right; this is guidance text, not a find-replace on the model output.
BANNED_LITERARY: dict[str, str] = {
    "महत्वपूर्ण": "important / kaafi sahi / kaam ka",
    "mahatvapurn": "important / kaafi sahi / kaam ka",
    "अत्यंत": "kaafi / bahut",
    "atyant": "kaafi / bahut",
    "उत्कृष्ट": "badhiya / top",
    "utkrisht": "badhiya / top",
    "श्रेष्ठ": "sabse achha",
    "shreshth": "sabse achha",
    "विशेष": "khaas",  # in the stiff sense
    "vishesh": "khaas",
    "धन्यवाद": "thank you / shukriya",  # stiff mid-sales 'dhanyavaad'
    "आपकी सुविधा हेतु": "(drop — bureaucratic)",
    "कृपया अवगत कराएं": "(drop — bureaucratic)",
    "निवेदन है कि": "(drop — bureaucratic)",
}

# English-native nouns to KEEP in English inside Hindi sentences (never translate).
KEEP_ENGLISH_NOUNS: tuple[str, ...] = (
    "project", "site visit", "booking", "EMI", "budget", "location",
    "brochure", "loan", "option", "offer", "plan", "demo", "appointment",
)

# Everyday connectors that make speech sound human.
PREFERRED_CONNECTORS: tuple[str, ...] = (
    "achha", "theek hai", "dekhiye", "ji bilkul", "haan", "ek minute",
)

# Rendering rules (behavioral, always-on for the language layer).
RENDERING_RULES: tuple[str, ...] = (
    "Speak casual urban spoken Hinglish; render Devanagari that reads like SPEECH, not a formal letter.",
    "Keep names, company names and English product nouns un-translated inside Hindi sentences.",
    "Mirror the lead's exact register: rough/casual -> match it; cleaner English -> stay in English.",
    "Switch language turn-by-turn following the lead's LAST utterance; never lock to one language for the whole call.",
    "Numbers as natural speech: 'pachaasi lakh' not '85,00,000'; say times like 'gyaarah baje' not '11:00'.",
    "COMPLETE every sentence — naturalness comes from prosody/pacing, never from dropping the last word.",
)


def language_directive() -> str:
    """A compact casual-Hinglish directive block for the prompt language layer.

    Intentionally does NOT enumerate vertical-specific example nouns (e.g.
    'site visit', 'BHK') — that would leak one vertical's vocabulary into every
    mode. It states the RULE ('keep English product nouns in English') so the
    model applies it to whatever vertical the campaign is actually in."""
    banned = ", ".join(sorted(set(k for k in BANNED_LITERARY if _is_latin(k))))
    rules = " ".join(RENDERING_RULES)
    return (
        f"LANGUAGE: casual urban Hinglish, mirror the lead turn-by-turn. "
        f"NEVER use literary/Sanskritised words (e.g. {banned}); prefer everyday spoken forms. "
        f"Keep names, company names and common English product nouns un-translated inside Hindi sentences. {rules}"
    )


def _is_latin(s: str) -> bool:
    return bool(re.match(r"^[\x00-\x7f]+$", s or ""))


def contains_banned_literary(text: str) -> bool:
    """True if `text` contains any banned literary token (case-insensitive for
    latin; exact for Devanagari). Used by tests / the eval harness."""
    if not text:
        return False
    low = str(text).lower()
    for tok in BANNED_LITERARY:
        if _is_latin(tok):
            if re.search(rf"\b{re.escape(tok.lower())}\b", low):
                return True
        elif tok in text:
            return True
    return False
