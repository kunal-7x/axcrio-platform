"""W-LANG-PROPER unit tests — voice_kernel.language.

Proves the ADAPTIVE per-turn language seam (the founder's correct spec, after the
heavy LanguageTracker forcing was reverted for causing English-only):

  * Hindi turn  -> hindi  + hi-IN
  * English turn -> english + en-IN
  * switch back  -> hindi  + hi-IN
  * uncertain / short utterance -> KEEPS the prior language, NEVER forces English
  * seed is Hinglish (NEVER English) so a cold/uncertain first turn is hi-IN
  * pure: zero droplet_work / agent imports at module load.
"""
from __future__ import annotations

import sys

from voice_kernel.language import (
    DEFAULT_LANG,
    ENGLISH,
    GUJARATI,
    HINDI,
    HINGLISH,
    ResolvedLang,
    TurnLanguageResolver,
    classify_text,
    normalize_lang,
    tts_lang_code,
)


# --------------------------------------------------------------------------- #
# IMPORT ISOLATION — the kernel guarantee
# --------------------------------------------------------------------------- #
def test_zero_droplet_or_agent_imports_at_load():
    assert "voice_kernel.language" in sys.modules
    bad = [m for m in sys.modules if m.startswith("droplet_work") or m == "agent" or m.endswith(".agent")]
    assert bad == [], f"language module pulled forbidden modules: {bad}"


# --------------------------------------------------------------------------- #
# classify_text — script ratio + marker lexicon
# --------------------------------------------------------------------------- #
def test_classify_pure_devanagari_is_hindi():
    lang, conf = classify_text("मुझे यह घर पसंद है")
    assert lang == HINDI and conf >= 0.45


def test_classify_codemix_is_hinglish():
    lang, conf = classify_text("मुझे price बताओ please")
    assert lang == HINGLISH and conf >= 0.45


def test_classify_clear_english():
    lang, conf = classify_text("what is the price and how does it work")
    assert lang == ENGLISH and conf >= 0.45


def test_classify_romanized_hindi_is_hinglish_not_english():
    lang, _ = classify_text("haan bhai kitne ka hai ye ghar")
    assert lang == HINGLISH


def test_classify_gujarati():
    lang, conf = classify_text("મને આ ઘર ગમે છે")
    assert lang == GUJARATI and conf >= 0.45


def test_classify_short_or_empty_is_low_confidence():
    # short marker-less utterances must be LOW confidence so the resolver keeps prior.
    for txt in ("", "ok", "hmm", "123", "  "):
        _, conf = classify_text(txt)
        assert conf < 0.45, f"{txt!r} should be uncertain, got conf={conf}"


# --------------------------------------------------------------------------- #
# normalize_lang — Sarvam/ISO code mapping
# --------------------------------------------------------------------------- #
def test_normalize_lang_codes():
    assert normalize_lang("hi-IN") == HINDI
    assert normalize_lang("hi") == HINDI
    assert normalize_lang("en-IN") == ENGLISH
    assert normalize_lang("en") == ENGLISH
    assert normalize_lang("gu-IN") == GUJARATI


def test_normalize_lang_autodetect_placeholder_is_blank():
    # 'unknown' is the Sarvam auto-detect default — NOT a real language this turn.
    for raw in ("", "unknown", "auto", "und", "  ", "zz-XX"):
        assert normalize_lang(raw) == "", f"{raw!r} must be treated as uncertain"


# --------------------------------------------------------------------------- #
# tts_lang_code — SPEAKABLE telephony codes (gu degrades to hi)
# --------------------------------------------------------------------------- #
def test_tts_lang_codes_speakable():
    assert tts_lang_code(HINDI) == "hi-IN"
    assert tts_lang_code(HINGLISH) == "hi-IN"
    assert tts_lang_code(ENGLISH) == "en-IN"
    assert tts_lang_code(GUJARATI) == "hi-IN"  # flash can't speak gu -> hi audio
    assert tts_lang_code("") == "hi-IN"  # never empty, never English by default


# --------------------------------------------------------------------------- #
# TurnLanguageResolver — the adaptive both-ways + keep-prior behaviour
# --------------------------------------------------------------------------- #
def test_resolver_seeds_hinglish_not_english():
    r = TurnLanguageResolver()
    assert r.current == DEFAULT_LANG == HINGLISH
    # a totally uncertain first turn keeps the hi-seed, NEVER becomes english.
    out = r.resolve(stt_lang="", user_text="hmm")
    assert out.lang != ENGLISH
    assert out.tts_lang == "hi-IN"
    assert out.source == "carried"


def test_resolver_stt_code_is_authoritative():
    r = TurnLanguageResolver()
    out = r.resolve(stt_lang="en-IN", user_text="मुझे चाहिए")  # STT wins over text
    assert out.lang == ENGLISH and out.tts_lang == "en-IN" and out.source == "stt"
    assert out.confidence == 1.0


def test_resolver_adapts_both_ways():
    r = TurnLanguageResolver(seed_locale="hi-IN")
    # Hindi
    a = r.resolve(stt_lang="hi-IN", user_text="मुझे price बताइए")
    assert a.lang == HINDI and a.tts_lang == "hi-IN"
    # -> English (text classify, no STT code)
    b = r.resolve(stt_lang="", user_text="what is the price and how does it work")
    assert b.lang == ENGLISH and b.tts_lang == "en-IN" and b.switched is True
    # -> back to Hindi
    c = r.resolve(stt_lang="hi-IN", user_text="हाँ ठीक है")
    assert c.lang == HINDI and c.tts_lang == "hi-IN" and c.switched is True


def test_resolver_keeps_prior_on_uncertain_never_english():
    r = TurnLanguageResolver(seed_locale="hi-IN")
    r.resolve(stt_lang="hi-IN", user_text="मुझे चाहिए")  # establish hindi
    # uncertain short turns must NOT flip to english.
    for txt in ("ok", "hmm", "123", ""):
        out = r.resolve(stt_lang="", user_text=txt)
        assert out.lang == HINDI, f"{txt!r} should keep hindi, got {out.lang}"
        assert out.tts_lang == "hi-IN"
        assert out.source == "carried"
        assert out.switched is False


def test_resolver_returns_resolvedlang_dataclass():
    r = TurnLanguageResolver()
    out = r.resolve(stt_lang="hi-IN", user_text="haan")
    assert isinstance(out, ResolvedLang)
    assert set(("lang", "tts_lang", "source", "switched", "confidence")) <= set(vars(out))


def test_resolver_never_raises_on_garbage():
    r = TurnLanguageResolver()
    out = r.resolve(stt_lang=None, user_text=None)  # type: ignore[arg-type]
    assert out.tts_lang in ("hi-IN", "en-IN")  # degraded-but-valid, never crashes
