"""voice_kernel.speech.hinglish — casual-Hinglish enforcement.

Founder complaint (b): the agent speaks FORMAL / literary Hindi ("mahatvapurn",
"avashyak", "kripya") which sounds like a news anchor, not a telecaller. This
module rewrites the literary register to the casual spoken register a real Indian
telecaller uses, and keeps common English loan-words in LATIN script (so the
Sarvam Devanagari path doesn't transliterate "site visit" into clumsy Devanagari).

Pure, deterministic, stdlib-only. Word-boundary, case-preserving replacement so
"Mahatvapurn" -> "Zaroori" and "mahatvapurn" -> "zaroori".
"""
from __future__ import annotations

import re

# literary / Sanskritized Hindi -> casual spoken Hinglish (Latin).
# Covers both Latin-transliteration and Devanagari spellings the LLM emits.
_LITERARY_TO_CASUAL = {
    # the headline offender from the founder complaint
    "mahatvapurn": "zaroori",
    "mahatvapoorn": "zaroori",
    "महत्वपूर्ण": "zaroori",
    "avashyak": "zaroori",
    "आवश्यक": "zaroori",
    "kripya": "please",
    "कृपया": "please",
    "dhanyavaad": "thank you",
    "धन्यवाद": "thank you",
    "sambhav": "possible",
    "संभव": "possible",
    "uplabdh": "available",
    "उपलब्ध": "available",
    "vishesh": "khaas",
    "विशेष": "khaas",
    "prastut": "ready",
    "प्रस्तुत": "ready",
    "sahaayata": "help",
    "सहायता": "help",
    "vikalp": "option",
    "विकल्प": "option",
    "suvidha": "facility",
    "सुविधा": "facility",
    "abhi tatkaal": "abhi",
    "tatkaal": "turant",
    "तत्काल": "turant",
    "sampark": "contact",
    "संपर्क": "contact",
    "nivedan": "request",
    "निवेदन": "request",
    "anurodh": "request",
    "अनुरोध": "request",
    "pradan": "de",
    "प्रदान": "de",
    "lagbhag": "karib",
    "लगभग": "karib",
}

# English concepts the agent should keep in LATIN even on the Sarvam Devanagari
# path (transliterating these reads worse). We don't force-insert them; we just
# protect them from a Devanagari pass downstream by tagging via the loanword set.
LATIN_LOANWORDS = frozenset({
    "site", "visit", "booking", "offer", "price", "EMI", "loan", "WhatsApp",
    "location", "demo", "appointment", "callback", "discount", "balcony",
    "parking", "BHK", "ready", "possession", "registry", "token", "amount",
})


def _preserve_case(src: str, repl: str) -> str:
    if src.isupper():
        return repl.upper()
    if src[:1].isupper():
        return repl[:1].upper() + repl[1:]
    return repl


# precompile a single alternation, longest-key-first so multi-word keys win.
_KEYS = sorted(_LITERARY_TO_CASUAL, key=len, reverse=True)
# Devanagari block (letters + matras/signs/nukta). `\b` is ASCII-only in `re`, so
# a raw Devanagari key would match INSIDE a longer word (आवश्यक inside आवश्यकता ->
# "zarooriता"). We emulate a Devanagari word-boundary with lookaround: the key
# must NOT be flanked by another Devanagari character.
_DEVA = r"ऀ-ॿ"
_DEVA_LB = rf"(?<![{_DEVA}])"   # no Devanagari char immediately before
_DEVA_LA = rf"(?![{_DEVA}])"    # no Devanagari char immediately after
_PATTERN = re.compile(
    "|".join(
        (r"\b" + re.escape(k) + r"\b") if k.isascii()
        else (_DEVA_LB + re.escape(k) + _DEVA_LA)
        for k in _KEYS
    ),
    re.IGNORECASE,
)


def enforce_casual_hinglish(text: str) -> str:
    """Replace literary-Hindi words with their casual spoken equivalents,
    preserving case. Idempotent and fail-safe (returns input on any error)."""
    if not text:
        return text
    try:
        def repl(m: re.Match) -> str:
            found = m.group(0)
            casual = _LITERARY_TO_CASUAL.get(found.lower())
            if casual is None:
                return found
            return _preserve_case(found, casual) if found.isascii() else casual

        return _PATTERN.sub(repl, text)
    except Exception:  # noqa: BLE001 — fail-open
        return text


def has_literary_hindi(text: str) -> bool:
    """True if any banned literary-Hindi word is present (diagnostic/test aid)."""
    return bool(_PATTERN.search(text or ""))
