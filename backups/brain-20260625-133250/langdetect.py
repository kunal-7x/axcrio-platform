"""langdetect.py — cheap, per-turn language detection for the Famit voice agent (P2).

Goal: detect the caller's language each turn from the STT transcript and let the agent
MIRROR it — steer the LLM to reply in that language AND set the ElevenLabs TTS language.

HARD CONSTRAINT: this runs on the per-turn hot path, so it must be allocation-cheap and
do NO network / model call. It is pure Unicode-script ratio + a small Hinglish marker
lexicon. A confidence floor + hysteresis (N consecutive agreeing turns) stop it flapping.

Languages: "hindi" | "english" | "hinglish" | "gujarati" (gujarati = BETA).
Default / fallback stays "hinglish".

Public API:
    classify_text(text) -> (lang, confidence)         # stateless single-shot
    LanguageTracker()                                  # stateful, hysteresis-gated
        .update(text) -> (active_lang, switched: bool)
        .active                                        # current sticky language
    tts_language_code(lang) -> ElevenLabs language code ("hi"|"en"|"gu")
    is_beta(lang) -> bool

Everything is wrapped so a failure NEVER breaks a call (caller falls back to default).
"""

from __future__ import annotations

import re

DEFAULT_LANG = "hinglish"

# Unicode blocks.
_DEVANAGARI = (0x0900, 0x097F)   # Hindi/Marathi
_GUJARATI = (0x0A80, 0x0AFF)     # Gujarati
# Latin a-z (we only count letters, ignore digits/punct/space).

# Hinglish / romanized-Hindi marker words (lowercased). If Latin text is full of these,
# it's Hinglish, not English. Kept small + high-signal to stay cheap.
_HINGLISH_MARKERS = frozenset("""
hai haan han nahi nahin kya kyu kyun kaise kaha kahan kab kaun kitna kitni acha accha
theek thik bhai bhaiya ji sahab sahib haanji nahiji matlab abhi baad pehle phir chalo
chaliye bilkul zaroor zarur namaste namaskar dhanyavaad shukriya bataye batao bolo boliye
karenge karunga karungi karna karne hoga hogi rahega rahegi suniye suno dekhiye dekho
paisa rupaye lakh crore ghar makaan property site visit chahiye chahta chahti milega
samajh samjha samjhe achha bas thoda zyada kam mast badiya yaar arre arrey
""".split())

# Common English function words — presence (without Hinglish markers) → English.
_ENGLISH_MARKERS = frozenset("""
the is are was were have has had will would can could should you your yours i me my we
our they them this that these those and but or for with from about please thanks thank
yes no okay ok sure right what when where why how which who price details call talk
interested not now later property house flat budget visit location office meeting
""".split())

_WORD_RE = re.compile(r"[a-zA-Z]+")


def _script_counts(text: str):
    """Return (devanagari, gujarati, latin) letter counts. Cheap single pass."""
    dev = guj = lat = 0
    for ch in text:
        o = ord(ch)
        if _DEVANAGARI[0] <= o <= _DEVANAGARI[1]:
            dev += 1
        elif _GUJARATI[0] <= o <= _GUJARATI[1]:
            guj += 1
        elif 0x41 <= o <= 0x5A or 0x61 <= o <= 0x7A:
            lat += 1
    return dev, guj, lat


def classify_text(text: str):
    """Single-shot classify. Returns (lang, confidence 0..1). Never raises."""
    try:
        if not text or not text.strip():
            return DEFAULT_LANG, 0.0
        dev, guj, lat = _script_counts(text)
        total = dev + guj + lat
        if total == 0:
            return DEFAULT_LANG, 0.0

        # --- Gujarati: any meaningful Gujarati-script presence wins (rare script) ---
        if guj >= 2 and guj >= 0.30 * total:
            return "gujarati", min(1.0, guj / total + 0.2)

        # --- Mixed Devanagari + Latin => Hinglish ---
        if dev > 0 and lat > 0:
            # Both scripts present in the same utterance = code-mixing = Hinglish.
            minor = min(dev, lat) / total
            return "hinglish", min(1.0, 0.6 + minor)

        # --- Pure Devanagari => Hindi ---
        if dev > 0 and lat == 0:
            return "hindi", min(1.0, dev / total)

        # --- Pure Latin: disambiguate English vs romanized Hinglish via lexicon ---
        words = [w.lower() for w in _WORD_RE.findall(text)]
        if not words:
            return DEFAULT_LANG, 0.0
        hin = sum(1 for w in words if w in _HINGLISH_MARKERS)
        eng = sum(1 for w in words if w in _ENGLISH_MARKERS)
        nw = len(words)
        hin_ratio = hin / nw
        eng_ratio = eng / nw
        if hin >= 1 and hin_ratio >= eng_ratio:
            # any romanized-Hindi signal, and it's not dominated by English markers
            return "hinglish", min(1.0, 0.5 + hin_ratio)
        if eng >= 1 and eng_ratio > hin_ratio:
            return "english", min(1.0, 0.4 + eng_ratio)
        # Latin text with no strong markers (names, "ok", numbers) — low confidence English.
        return "english", 0.25
    except Exception:
        return DEFAULT_LANG, 0.0


# ElevenLabs language codes (ISO-639-1). Hinglish speaks fine as Hindi 'hi'
# (Devanagari + Latin mix, which is what the LLM emits).
#
# ⚠️ HARD CONSTRAINT (verified LIVE 2026-06-05): the realtime TTS model
# `eleven_flash_v2_5` SUPPORTS `hi` and `en` but does NOT support `gu` (Gujarati) —
# sending language_code='gu' returns `unsupported_language` (code 1008), the TTS
# websocket dies and the agent goes SILENT (dead air) for the rest of the call,
# because update_options() is sticky. So we NEVER emit a code flash can't speak.
# Gujarati (and any other non-hi/en language) DEGRADES to Hindi 'hi': we still
# UNDERSTAND the caller (STT auto-detect) but REPLY in Hindi audio (a Gujarati/
# Marathi/Bengali speaker in India understands Hindi) — audible beats silent.
# Real Gujarati TTS = a separate infra decision (different model+voice+latency
# re-test); do NOT switch models here (flash_v2_5 chosen for latency).
_TTS_CODE = {
    "hindi": "hi",
    "hinglish": "hi",
    "english": "en",
    "gujarati": "hi",   # flash_v2_5 has NO 'gu' → speak Hindi (don't go silent)
}

# Codes the realtime flash model can actually SPEAK. Any detect that maps outside
# this set is clamped to 'hi' (see safe_tts_language_code). Overridable via env at
# the call site (SUPPORTED_TTS_LANGS) — keep in sync with the deployed TTS model.
SPEAKABLE_TTS = frozenset({"hi", "en"})

# Languages flash can't speak natively → we understand them but reply in Hindi.
# (Used to steer the LLM to a SPEAKABLE language instead of emitting unspeakable script.)
_DEGRADE_TO_HINDI = frozenset({"gujarati"})

_BETA = frozenset({"gujarati"})

# Human-readable instruction the agent injects into the LLM to mirror the language.
LANG_REPLY_INSTRUCTION = {
    "hindi": "इस turn का जवाब शुद्ध Hindi (Devanagari) में दो। English तभी जब ज़रूरी technical/business शब्द हो।",
    "english": "Reply to this turn in clear, natural English. The caller is speaking English — mirror them.",
    "hinglish": "इस turn का जवाब बोलचाल की Hinglish में दो (Hindi Devanagari + ज़रूरी English शब्द) — caller को mirror करो।",
    # NOTE: our realtime TTS can't SPEAK Gujarati, so we must NOT reply in Gujarati
    # script (it would come out silent/garbled). Understand the Gujarati caller but
    # reply in simple Hindi/Hinglish — a Gujarati speaker understands Hindi.
    "gujarati": "Caller अभी Gujarati में बोला है। तुम उसे समझ गई/गया हो — पर जवाब साफ़, आसान Hindi (Devanagari) में दो, Gujarati script में नहीं। गर्मजोशी से, उसी बात पर।",
}


def tts_language_code(lang: str) -> str:
    return _TTS_CODE.get(lang, "hi")


def safe_tts_language_code(lang: str, speakable=SPEAKABLE_TTS) -> str:
    """The TTS code we are SAFE to send to the realtime model: map the language,
    then clamp anything the model can't speak down to Hindi 'hi' (never silence)."""
    code = _TTS_CODE.get(lang, "hi")
    return code if code in speakable else "hi"


def is_speakable(lang: str) -> bool:
    """True if flash can natively speak this language; False → degrade-to-Hindi."""
    return _TTS_CODE.get(lang, "hi") in SPEAKABLE_TTS and lang not in _DEGRADE_TO_HINDI


def degrades_to_hindi(lang: str) -> bool:
    return lang in _DEGRADE_TO_HINDI


def is_beta(lang: str) -> bool:
    return lang in _BETA


def reply_instruction(lang: str) -> str:
    return LANG_REPLY_INSTRUCTION.get(lang, LANG_REPLY_INSTRUCTION["hinglish"])


class LanguageTracker:
    """Sticky language with hysteresis so we don't flap on a single noisy turn.

    Switch the active language ONLY when `min_streak` consecutive turns agree on the
    same non-default candidate above `conf_floor`. This makes a confident, sustained
    language change flip the agent, while a stray English word inside Hinglish does not.
    """

    def __init__(self, default: str = DEFAULT_LANG, conf_floor: float = 0.45,
                 min_streak: int = 1):
        self.active = default
        self.default = default
        self.conf_floor = conf_floor
        self.min_streak = max(1, min_streak)
        self._cand = default
        self._streak = 0

    def update(self, text: str):
        """Feed a caller transcript turn. Returns (active_lang, switched_bool)."""
        try:
            lang, conf = classify_text(text)
            # Low-confidence or empty → keep current, no streak progress.
            if conf < self.conf_floor:
                return self.active, False
            if lang == self._cand:
                self._streak += 1
            else:
                self._cand = lang
                self._streak = 1
            switched = False
            if lang != self.active and self._streak >= self.min_streak:
                self.active = lang
                switched = True
            return self.active, switched
        except Exception:
            return self.active, False
