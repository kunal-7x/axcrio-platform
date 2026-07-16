"""verticals.languages — the supported-language registry.

A PURE, stdlib-only catalogue of languages the agent can converse in. It carries,
per language:

  * ``tts_code``          — the ElevenLabs/Sarvam language code (raw).
  * ``el_speakable``      — can ElevenLabs flash_v2_5 actually SPEAK it? (hi/en only)
  * ``sarvam_speakable``  — can Sarvam Bulbul v2 speak it? (most Indic languages)
  * ``sarvam_lang``       — the ``xx-IN`` code Sarvam expects.
  * ``reply``             — a one-line reply directive to steer the LLM.
  * ``native``/``name``   — display strings.

WHY the split: the runtime already CLAMPS spoken TTS to a speakable set to avoid the
"dead-air" failure (a code the engine can't speak kills the TTS websocket). This
registry declares speakability PER PROVIDER so a caller can pick a genuinely
speakable voice — it NEVER instructs the runtime to bypass its clamp. The LLM is
multilingual and mirrors the caller's language in TEXT for *every* language here;
whether it is also SPOKEN depends on the active TTS provider's ``*_speakable`` flag.

Nothing here touches the network or a heavy wheel; safe to import anywhere.
"""

from __future__ import annotations

# code -> descriptor.  el_speakable is deliberately conservative (hi/en) to respect
# the live dead-air clamp; sarvam_speakable reflects Bulbul v2's Indic coverage.
LANGUAGES: dict[str, dict] = {
    "hi": {
        "name": "Hindi", "native": "हिन्दी", "tts_code": "hi",
        "el_speakable": True, "sarvam_speakable": True, "sarvam_lang": "hi-IN",
        "reply": "caller ki Hindi mein hi jawab do (Devanagari).",
        "greeting": "नमस्ते",
    },
    "en": {
        "name": "English", "native": "English", "tts_code": "en",
        "el_speakable": True, "sarvam_speakable": True, "sarvam_lang": "en-IN",
        "reply": "reply in clear, simple Indian English.",
        "greeting": "Hello",
    },
    "hinglish": {
        "name": "Hinglish", "native": "Hinglish", "tts_code": "hi",
        "el_speakable": True, "sarvam_speakable": True, "sarvam_lang": "hi-IN",
        "reply": "natural Hinglish (Hindi + roz-marra English words) mein jawab do.",
        "greeting": "नमस्ते",
    },
    "bn": {
        "name": "Bengali", "native": "বাংলা", "tts_code": "bn",
        "el_speakable": False, "sarvam_speakable": True, "sarvam_lang": "bn-IN",
        "reply": "caller ki Bangla mein jawab do.",
        "greeting": "নমস্কার",
    },
    "ta": {
        "name": "Tamil", "native": "தமிழ்", "tts_code": "ta",
        "el_speakable": False, "sarvam_speakable": True, "sarvam_lang": "ta-IN",
        "reply": "reply in the caller's Tamil.",
        "greeting": "வணக்கம்",
    },
    "te": {
        "name": "Telugu", "native": "తెలుగు", "tts_code": "te",
        "el_speakable": False, "sarvam_speakable": True, "sarvam_lang": "te-IN",
        "reply": "reply in the caller's Telugu.",
        "greeting": "నమస్కారం",
    },
    "kn": {
        "name": "Kannada", "native": "ಕನ್ನಡ", "tts_code": "kn",
        "el_speakable": False, "sarvam_speakable": True, "sarvam_lang": "kn-IN",
        "reply": "reply in the caller's Kannada.",
        "greeting": "ನಮಸ್ಕಾರ",
    },
    "ml": {
        "name": "Malayalam", "native": "മലയാളം", "tts_code": "ml",
        "el_speakable": False, "sarvam_speakable": True, "sarvam_lang": "ml-IN",
        "reply": "reply in the caller's Malayalam.",
        "greeting": "നമസ്കാരം",
    },
    "mr": {
        "name": "Marathi", "native": "मराठी", "tts_code": "mr",
        "el_speakable": False, "sarvam_speakable": True, "sarvam_lang": "mr-IN",
        "reply": "caller ki Marathi mein jawab do.",
        "greeting": "नमस्कार",
    },
    "gu": {
        "name": "Gujarati", "native": "ગુજરાતી", "tts_code": "gu",
        "el_speakable": False, "sarvam_speakable": True, "sarvam_lang": "gu-IN",
        "reply": "caller ni Gujarati ma jawab aapo.",
        "greeting": "નમસ્તે",
    },
    "pa": {
        "name": "Punjabi", "native": "ਪੰਜਾਬੀ", "tts_code": "pa",
        "el_speakable": False, "sarvam_speakable": True, "sarvam_lang": "pa-IN",
        "reply": "caller di Punjabi vich jawab dyo.",
        "greeting": "ਸਤ ਸ੍ਰੀ ਅਕਾਲ",
    },
    "od": {
        "name": "Odia", "native": "ଓଡ଼ିଆ", "tts_code": "od",
        "el_speakable": False, "sarvam_speakable": True, "sarvam_lang": "od-IN",
        "reply": "reply in the caller's Odia.",
        "greeting": "ନମସ୍କାର",
    },

    # ── INTERNATIONAL (world) languages — spoken natively by ElevenLabs flash_v2_5 ──
    # el_speakable=True unlocks them; sarvam can't speak them (sarvam_speakable=False). The
    # runtime runs these as a FIXED-language call (pinned code + langdetect mirroring off).
    "es": {"name": "Spanish", "native": "Español", "tts_code": "es", "el_speakable": True, "sarvam_speakable": False, "sarvam_lang": "", "international": True, "reply": "Responde SIEMPRE en español.", "greeting": "Hola"},
    "fr": {"name": "French", "native": "Français", "tts_code": "fr", "el_speakable": True, "sarvam_speakable": False, "sarvam_lang": "", "international": True, "reply": "Réponds TOUJOURS en français.", "greeting": "Bonjour"},
    "de": {"name": "German", "native": "Deutsch", "tts_code": "de", "el_speakable": True, "sarvam_speakable": False, "sarvam_lang": "", "international": True, "reply": "Antworte IMMER auf Deutsch.", "greeting": "Hallo"},
    "it": {"name": "Italian", "native": "Italiano", "tts_code": "it", "el_speakable": True, "sarvam_speakable": False, "sarvam_lang": "", "international": True, "reply": "Rispondi SEMPRE in italiano.", "greeting": "Ciao"},
    "pt": {"name": "Portuguese", "native": "Português", "tts_code": "pt", "el_speakable": True, "sarvam_speakable": False, "sarvam_lang": "", "international": True, "reply": "Responda SEMPRE em português.", "greeting": "Olá"},
    "nl": {"name": "Dutch", "native": "Nederlands", "tts_code": "nl", "el_speakable": True, "sarvam_speakable": False, "sarvam_lang": "", "international": True, "reply": "Antwoord ALTIJD in het Nederlands.", "greeting": "Hallo"},
    "pl": {"name": "Polish", "native": "Polski", "tts_code": "pl", "el_speakable": True, "sarvam_speakable": False, "sarvam_lang": "", "international": True, "reply": "Odpowiadaj ZAWSZE po polsku.", "greeting": "Cześć"},
    "tr": {"name": "Turkish", "native": "Türkçe", "tts_code": "tr", "el_speakable": True, "sarvam_speakable": False, "sarvam_lang": "", "international": True, "reply": "HER ZAMAN Türkçe cevap ver.", "greeting": "Merhaba"},
    "ru": {"name": "Russian", "native": "Русский", "tts_code": "ru", "el_speakable": True, "sarvam_speakable": False, "sarvam_lang": "", "international": True, "reply": "Отвечай ВСЕГДА на русском языке.", "greeting": "Здравствуйте"},
    "ar": {"name": "Arabic", "native": "العربية", "tts_code": "ar", "el_speakable": True, "sarvam_speakable": False, "sarvam_lang": "", "international": True, "reply": "أجب دائماً باللغة العربية.", "greeting": "مرحباً"},
    "zh": {"name": "Chinese (Mandarin)", "native": "中文", "tts_code": "zh", "el_speakable": True, "sarvam_speakable": False, "sarvam_lang": "", "international": True, "reply": "请始终用中文回答。", "greeting": "你好"},
    "ja": {"name": "Japanese", "native": "日本語", "tts_code": "ja", "el_speakable": True, "sarvam_speakable": False, "sarvam_lang": "", "international": True, "reply": "常に日本語で答えてください。", "greeting": "こんにちは"},
    "ko": {"name": "Korean", "native": "한국어", "tts_code": "ko", "el_speakable": True, "sarvam_speakable": False, "sarvam_lang": "", "international": True, "reply": "항상 한국어로 대답하세요.", "greeting": "안녕하세요"},
    "id": {"name": "Indonesian", "native": "Bahasa Indonesia", "tts_code": "id", "el_speakable": True, "sarvam_speakable": False, "sarvam_lang": "", "international": True, "reply": "Selalu jawab dalam Bahasa Indonesia.", "greeting": "Halo"},
    "fil": {"name": "Filipino", "native": "Filipino", "tts_code": "fil", "el_speakable": True, "sarvam_speakable": False, "sarvam_lang": "", "international": True, "reply": "Laging sumagot sa Filipino.", "greeting": "Kumusta"},
    "uk": {"name": "Ukrainian", "native": "Українська", "tts_code": "uk", "el_speakable": True, "sarvam_speakable": False, "sarvam_lang": "", "international": True, "reply": "Відповідай ЗАВЖДИ українською.", "greeting": "Вітаю"},
    "vi": {"name": "Vietnamese", "native": "Tiếng Việt", "tts_code": "vi", "el_speakable": True, "sarvam_speakable": False, "sarvam_lang": "", "international": True, "reply": "Luôn trả lời bằng tiếng Việt.", "greeting": "Xin chào"},
    "sv": {"name": "Swedish", "native": "Svenska", "tts_code": "sv", "el_speakable": True, "sarvam_speakable": False, "sarvam_lang": "", "international": True, "reply": "Svara ALLTID på svenska.", "greeting": "Hej"},
    "ro": {"name": "Romanian", "native": "Română", "tts_code": "ro", "el_speakable": True, "sarvam_speakable": False, "sarvam_lang": "", "international": True, "reply": "Răspunde ÎNTOTDEAUNA în română.", "greeting": "Bună"},
    "el": {"name": "Greek", "native": "Ελληνικά", "tts_code": "el", "el_speakable": True, "sarvam_speakable": False, "sarvam_lang": "", "international": True, "reply": "Απάντα ΠΑΝΤΑ στα ελληνικά.", "greeting": "Γεια σας"},
    "cs": {"name": "Czech", "native": "Čeština", "tts_code": "cs", "el_speakable": True, "sarvam_speakable": False, "sarvam_lang": "", "international": True, "reply": "Odpovídej VŽDY česky.", "greeting": "Ahoj"},
    "da": {"name": "Danish", "native": "Dansk", "tts_code": "da", "el_speakable": True, "sarvam_speakable": False, "sarvam_lang": "", "international": True, "reply": "Svar ALTID på dansk.", "greeting": "Hej"},
    "fi": {"name": "Finnish", "native": "Suomi", "tts_code": "fi", "el_speakable": True, "sarvam_speakable": False, "sarvam_lang": "", "international": True, "reply": "Vastaa AINA suomeksi.", "greeting": "Hei"},
    "ms": {"name": "Malay", "native": "Bahasa Melayu", "tts_code": "ms", "el_speakable": True, "sarvam_speakable": False, "sarvam_lang": "", "international": True, "reply": "Sentiasa jawab dalam Bahasa Melayu.", "greeting": "Helo"},
}

# Free-text / legacy aliases -> canonical code. Accepts the values that already flow
# through the campaign ``language`` field (e.g. "Hinglish", "Hindi") plus xx-IN codes.
_ALIASES: dict[str, str] = {
    "hindi": "hi", "hi-in": "hi", "हिन्दी": "hi", "हिंदी": "hi",
    "english": "en", "en-in": "en", "eng": "en", "angrezi": "en",
    "hinglish": "hinglish", "hindi+english": "hinglish", "mixed": "hinglish",
    "bengali": "bn", "bangla": "bn", "bn-in": "bn",
    "tamil": "ta", "ta-in": "ta",
    "telugu": "te", "te-in": "te",
    "kannada": "kn", "kn-in": "kn",
    "malayalam": "ml", "ml-in": "ml",
    "marathi": "mr", "mr-in": "mr",
    "gujarati": "gu", "gu-in": "gu",
    "punjabi": "pa", "panjabi": "pa", "pa-in": "pa",
    "odia": "od", "oriya": "od", "od-in": "od",
    # international
    "spanish": "es", "español": "es", "espanol": "es", "castellano": "es",
    "french": "fr", "français": "fr", "francais": "fr",
    "german": "de", "deutsch": "de",
    "italian": "it", "italiano": "it",
    "portuguese": "pt", "português": "pt", "portugues": "pt", "pt-br": "pt", "brazilian": "pt",
    "dutch": "nl", "nederlands": "nl",
    "polish": "pl", "polski": "pl",
    "turkish": "tr", "türkçe": "tr", "turkce": "tr",
    "russian": "ru", "русский": "ru",
    "arabic": "ar", "عربي": "ar", "العربية": "ar",
    "chinese": "zh", "mandarin": "zh", "中文": "zh", "zh-cn": "zh",
    "japanese": "ja", "日本語": "ja", "nihongo": "ja",
    "korean": "ko", "한국어": "ko",
    "indonesian": "id", "bahasa": "id",
    "filipino": "fil", "tagalog": "fil",
    "ukrainian": "uk", "українська": "uk",
    "vietnamese": "vi", "tiếng việt": "vi",
    "swedish": "sv", "svenska": "sv",
    "romanian": "ro", "română": "ro",
    "greek": "el", "ελληνικά": "el",
    "czech": "cs", "čeština": "cs",
    "danish": "da", "dansk": "da",
    "finnish": "fi", "suomi": "fi",
    "malay": "ms",
}


def canonical_code(value, source: dict | None = None) -> str:
    """Normalise a free-text language value to a canonical code, or '' if unknown."""
    table = source if source is not None else LANGUAGES
    v = str(value or "").strip().lower()
    if not v:
        return ""
    if v in table:
        return v
    if v in _ALIASES:
        return _ALIASES[v]
    # tolerate a display name with a parenthetical, e.g. "Chinese (Mandarin)" -> "chinese"
    base = v.split("(")[0].strip()
    if base and base != v:
        if base in table:
            return base
        return _ALIASES.get(base, "")
    return ""


def get_language(value, source: dict | None = None) -> dict | None:
    """Return the language descriptor for a code/name/alias, or None.

    ``source`` lets the composer pass an overlay-merged LANGUAGES table.
    """
    table = source if source is not None else LANGUAGES
    code = canonical_code(value, table)
    if not code or code not in table:
        return None
    d = dict(table[code])
    d["code"] = code
    return d


def reply_instruction(value) -> str:
    lang = get_language(value)
    return lang["reply"] if lang else ""


def spoken_code(value, tts_provider: str = "elevenlabs") -> str:
    """The code the given provider can ACTUALLY speak for this language.

    Respects the same conservative policy as the runtime clamp: if the provider
    cannot speak the language, fall back to 'hi' (never a code that would dead-air).
    """
    lang = get_language(value)
    if not lang:
        return "hi"
    prov = str(tts_provider or "").strip().lower()
    if prov == "sarvam":
        return lang["tts_code"] if lang.get("sarvam_speakable") else "hi"
    return lang["tts_code"] if lang.get("el_speakable") else "hi"


def is_international(value, source: dict | None = None) -> bool:
    """True for a world (non-Indic) language that runs as a fixed-language call."""
    lang = get_language(value, source)
    return bool(lang and lang.get("international"))


def list_languages() -> list[dict]:
    out = []
    for code, d in LANGUAGES.items():
        out.append({
            "code": code, "name": d["name"], "native": d["native"],
            "el_speakable": d["el_speakable"], "sarvam_speakable": d["sarvam_speakable"],
            "international": bool(d.get("international")),
        })
    return out
