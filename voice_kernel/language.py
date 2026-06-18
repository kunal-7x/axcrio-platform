"""voice_kernel.language — adaptive, per-turn language detection + resolution.

The founder's CORRECT language spec (the prior heavy LanguageTracker "force a
fixed reply language" approach was WRONG — it caused English-only and was
reverted). The pipeline this module supports:

    Sarvam STT auto-detects the spoken language per utterance
        -> that detected language flows here
        -> we resolve it ADAPTIVELY (follow the user, both ways, every turn)
        -> the LLM is told (SOFT) "the caller is speaking <lang>; reply in <lang>"
        -> the TTS language code is set to that language.

This module is PURE: stdlib only, NO network, NO model call, NO droplet_work
import (the kernel import-isolation guarantee — the live agents inject nothing
here; importing this module pulls zero box modules). The script-ratio + marker
heuristic is the same one proven on 96 live calls in droplet_work/langdetect.py;
we port the CLASSIFIER, deliberately NOT the heavy sticky LanguageTracker that
forced a fixed reply language.

KEY ADAPTIVE RULES (these are the whole point):
  * NEVER hardcode / force a fixed reply language.
  * Follow the caller EACH turn, both directions (Hindi->English->Hindi mid-call).
  * If a turn is UNCERTAIN (blank STT lang AND low-confidence text, or a short
    "ok"/"haan"/number-only utterance), KEEP the PRIOR turn's language — do NOT
    default to English. This kills the English-only failure mode.
  * Seed the prior language from the call locale (default Hinglish), never English.

Public API:
    classify_text(text) -> (lang, confidence)        # stateless single-shot
    normalize_lang(raw) -> canonical lang | ""        # map a Sarvam/ISO code to a label
    tts_lang_code(lang) -> "hi-IN" | "en-IN"          # SPEAKABLE telephony code
    TurnLanguageResolver(seed_locale=...)             # per-call, turn-scoped, sticky-on-uncertain
        .resolve(stt_lang, user_text) -> ResolvedLang
        .current                                       # last resolved canonical label
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# Canonical labels this module speaks in. Default/fallback is Hinglish — NEVER
# English (forcing English is the exact regression we are killing).
HINDI = "hindi"
ENGLISH = "english"
HINGLISH = "hinglish"
GUJARATI = "gujarati"
DEFAULT_LANG = HINGLISH

# Confidence floor below which a turn is treated as UNCERTAIN -> keep prior lang.
_CONF_FLOOR = 0.45

# Unicode blocks.
_DEVANAGARI = (0x0900, 0x097F)  # Hindi/Marathi
_GUJARATI = (0x0A80, 0x0AFF)    # Gujarati

# Romanized-Hindi / Hinglish marker words (lowercased). Latin text dense with
# these is Hinglish, not English. Small + high-signal to stay HOT-path cheap.
_HINGLISH_MARKERS = frozenset("""
hai haan han nahi nahin kya kyu kyun kaise kaha kahan kab kaun kitna kitni acha accha
theek thik bhai bhaiya ji sahab sahib haanji nahiji matlab abhi baad pehle phir chalo
chaliye bilkul zaroor zarur namaste namaskar dhanyavaad shukriya bataye batao bolo boliye
karenge karunga karungi karna karne hoga hogi rahega rahegi suniye suno dekhiye dekho
paisa rupaye lakh crore ghar makaan property site visit chahiye chahta chahti milega
samajh samjha samjhe achha bas thoda zyada kam mast badiya yaar arre arrey aap mujhe
""".split())

# Common English function words — presence (without Hinglish markers) -> English.
_ENGLISH_MARKERS = frozenset("""
the is are was were have has had will would can could should you your yours i me my we
our they them this that these those and but or for with from about please thanks thank
yes no okay ok sure right what when where why how which who price details call talk
interested not now later property house flat budget visit location office meeting want
""".split())

_WORD_RE = re.compile(r"[a-zA-Z]+")


def _script_counts(text: str) -> tuple[int, int, int]:
    """(devanagari, gujarati, latin) letter counts. Single cheap pass."""
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


def classify_text(text: str) -> tuple[str, float]:
    """Single-shot classify a transcript turn. Returns (canonical_lang, conf 0..1).

    Never raises. A short / marker-less utterance returns a LOW confidence so the
    resolver keeps the prior language instead of flapping to English.
    """
    try:
        if not text or not text.strip():
            return DEFAULT_LANG, 0.0
        dev, guj, lat = _script_counts(text)
        total = dev + guj + lat
        if total == 0:
            return DEFAULT_LANG, 0.0

        # Gujarati script presence wins (rare script -> high signal).
        if guj >= 2 and guj >= 0.30 * total:
            return GUJARATI, min(1.0, guj / total + 0.2)

        # Devanagari + Latin in one utterance = code-mix = Hinglish.
        if dev > 0 and lat > 0:
            minor = min(dev, lat) / total
            return HINGLISH, min(1.0, 0.6 + minor)

        # Pure Devanagari -> Hindi.
        if dev > 0 and lat == 0:
            return HINDI, min(1.0, dev / total)

        # Pure Latin: disambiguate English vs romanized Hinglish via the lexicon.
        words = [w.lower() for w in _WORD_RE.findall(text)]
        if not words:
            return DEFAULT_LANG, 0.0
        nw = len(words)
        # SHORT-UTTERANCE DAMPENER: a 1-word Latin reply ("ok", "haan", "yes", a
        # name) is too thin to FLIP the whole call's language on — emit LOW
        # confidence so the resolver keeps the prior language (never force English).
        if nw < 2:
            return ENGLISH, 0.25
        hin = sum(1 for w in words if w in _HINGLISH_MARKERS)
        eng = sum(1 for w in words if w in _ENGLISH_MARKERS)
        hin_ratio = hin / nw
        eng_ratio = eng / nw
        if hin >= 1 and hin_ratio >= eng_ratio:
            return HINGLISH, min(1.0, 0.5 + hin_ratio)
        if eng >= 1 and eng_ratio > hin_ratio:
            return ENGLISH, min(1.0, 0.4 + eng_ratio)
        # Latin, multi-word but no strong markers (e.g. several proper nouns) ->
        # LOW-conf English so the resolver treats it as uncertain and keeps prior.
        return ENGLISH, 0.25
    except Exception:
        return DEFAULT_LANG, 0.0


# Map a raw STT / ISO-ish language code (what Sarvam puts on the result) to a
# canonical label. Sarvam emits codes like "hi-IN", "en-IN", "gu-IN", "hi", "en",
# or "" / "unknown" (auto-detect, language not surfaced this turn).
def normalize_lang(raw: str) -> str:
    """Canonicalise a raw STT language code to a label, or "" if not recognised
    (the caller then light-classifies the transcript text instead)."""
    if not raw:
        return ""
    s = raw.strip().lower()
    if s in ("unknown", "auto", "und", "mixed", "code-mix", "codemix"):
        return ""  # auto-detect placeholder — not a real language this turn
    if s.startswith("gu") or "gujarat" in s:
        return GUJARATI
    if s.startswith("hi") or "hindi" in s or "deva" in s:
        return HINDI
    if s.startswith("en") or "english" in s:
        return ENGLISH
    if "hing" in s:
        return HINGLISH
    return ""  # unrecognised -> uncertain (keep prior), never silently force English


# TTS telephony codes the realtime models can actually SPEAK.
#   hindi / hinglish -> hi-IN ; english -> en-IN.
#   gujarati DEGRADES to hi-IN audio (flash_v2_5 has no 'gu' -> would go silent),
#   matching droplet_work/langdetect.py: understand the caller, reply in Hindi.
_TTS_CODE = {
    HINDI: "hi-IN",
    HINGLISH: "hi-IN",
    ENGLISH: "en-IN",
    GUJARATI: "hi-IN",
}


def tts_lang_code(lang: str) -> str:
    """The SPEAKABLE TTS code for a canonical label. Never empty, never a code the
    realtime model can't speak (clamped to hi-IN)."""
    return _TTS_CODE.get((lang or "").strip().lower(), "hi-IN")


@dataclass(frozen=True)
class ResolvedLang:
    """The adaptive per-turn resolution result.

    lang       — canonical label the LLM should mirror this turn.
    tts_lang   — SPEAKABLE TTS code ("hi-IN" / "en-IN") for this turn.
    source     — "stt" (Sarvam surfaced it), "text" (light classify), or
                 "carried" (uncertain -> kept the prior turn's language).
    switched   — True if lang changed vs the previous resolved turn.
    confidence — 0..1 (1.0 when taken straight from a real STT code).
    """

    lang: str
    tts_lang: str
    source: str
    switched: bool
    confidence: float


class TurnLanguageResolver:
    """Per-call, turn-scoped, SOFT language resolver. One instance per call.

    Adaptive both ways: each turn it prefers the real STT-detected language; if
    the STT didn't surface one this turn it light-classifies the transcript; and
    if THAT is uncertain (low confidence / short utterance) it KEEPS the prior
    turn's language — it NEVER falls back to English. The seed is the call locale
    (default Hinglish), never English. There is NO "lock to one language" / no
    forced reply language — switching is immediate when the caller switches.
    """

    def __init__(self, seed_locale: str = "", conf_floor: float = _CONF_FLOOR) -> None:
        seeded = normalize_lang(seed_locale) or DEFAULT_LANG
        self.current = seeded  # last resolved canonical label (NEVER seeded to English implicitly)
        self.conf_floor = conf_floor

    def resolve(self, stt_lang: str = "", user_text: str = "") -> ResolvedLang:
        """Resolve THIS turn's language. Never raises.

        Priority:
          1. A real STT-surfaced language code (authoritative, confidence 1.0).
          2. Else light-classify the transcript text; accept it only if its
             confidence clears the floor.
          3. Else UNCERTAIN -> carry the prior turn's language (never English).
        """
        try:
            prev = self.current
            # 1) STT surfaced a real code this turn -> authoritative.
            stt = normalize_lang(stt_lang)
            if stt:
                switched = stt != prev
                self.current = stt
                return ResolvedLang(stt, tts_lang_code(stt), "stt", switched, 1.0)

            # 2) STT gave nothing usable -> light-classify the transcript text.
            lang, conf = classify_text(user_text or "")
            if conf >= self.conf_floor:
                switched = lang != prev
                self.current = lang
                return ResolvedLang(lang, tts_lang_code(lang), "text", switched, conf)

            # 3) UNCERTAIN -> KEEP the prior language. NEVER force English.
            return ResolvedLang(prev, tts_lang_code(prev), "carried", False, conf)
        except Exception:
            # Total failure -> keep prior; degraded-but-correct beats English-only.
            return ResolvedLang(self.current, tts_lang_code(self.current), "carried", False, 0.0)


__all__ = [
    "HINDI",
    "ENGLISH",
    "HINGLISH",
    "GUJARATI",
    "DEFAULT_LANG",
    "classify_text",
    "normalize_lang",
    "tts_lang_code",
    "ResolvedLang",
    "TurnLanguageResolver",
]
