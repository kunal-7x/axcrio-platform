"""Unit tests for voice_kernel.language.detector — the self-contained PORT of the
live outbound earner's langdetect. Asserts the script-ratio + lexicon detection,
the TTS-code mapping (gu clamps to hi, never silence), and the hysteresis tracker.
"""
from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import pytest

from voice_kernel.language import detector as ld


# --------------------------------------------------------------------------- #
# classify_text — script ratio + lexicon
# --------------------------------------------------------------------------- #
def test_pure_devanagari_is_hindi():
    lang, conf = ld.classify_text("नमस्ते मैं ठीक हूँ")
    assert lang == "hindi"
    assert conf > 0.5


def test_pure_english_function_words_is_english():
    lang, conf = ld.classify_text("yes I am interested please tell me the price")
    assert lang == "english"
    assert conf >= ld.classify_text("the is are")[1] - 1  # sane confidence


def test_short_english_is_english():
    # "Hello" / "ok" type short turns must still resolve to english (mid-call switch).
    assert ld.classify_text("Hello")[0] == "english"
    assert ld.classify_text("ok sure")[0] == "english"


def test_romanized_hindi_is_hinglish():
    lang, _ = ld.classify_text("haan bhai bilkul theek hai")
    assert lang == "hinglish"


def test_devanagari_plus_latin_is_hinglish_codemix():
    lang, conf = ld.classify_text("मुझे property visit करनी है site पर")
    assert lang == "hinglish"
    assert conf >= 0.6


def test_gujarati_script_is_gujarati():
    # Gujarati script characters (U+0A80..U+0AFF).
    lang, _ = ld.classify_text("કેમ છો તમે મજામાં")
    assert lang == "gujarati"


def test_empty_text_is_default():
    lang, conf = ld.classify_text("")
    assert lang == ld.DEFAULT_LANG
    assert conf == 0.0


def test_digits_punct_only_is_default():
    lang, conf = ld.classify_text("12345 ... ???")
    assert lang == ld.DEFAULT_LANG
    assert conf == 0.0


# --------------------------------------------------------------------------- #
# TTS code mapping — gu clamps to hi (the dead-air fix)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("lang,code", [
    ("hindi", "hi"), ("hinglish", "hi"), ("english", "en"), ("gujarati", "hi"),
])
def test_tts_language_code(lang, code):
    assert ld.tts_language_code(lang) == code


def test_safe_tts_code_never_emits_unspeakable():
    # gujarati maps to hi, and anything outside {hi,en} clamps to hi.
    assert ld.safe_tts_language_code("gujarati") == "hi"
    assert ld.safe_tts_language_code("hindi") == "hi"
    assert ld.safe_tts_language_code("english") == "en"
    assert ld.safe_tts_language_code("klingon") == "hi"  # unknown -> hi
    for lang in ("hindi", "english", "hinglish", "gujarati", "unknown"):
        assert ld.safe_tts_language_code(lang) in ld.SPEAKABLE_TTS


def test_is_speakable_and_beta():
    assert ld.is_speakable("hindi") is True
    assert ld.is_speakable("english") is True
    assert ld.is_speakable("gujarati") is False  # degrade-to-hindi
    assert ld.degrades_to_hindi("gujarati") is True
    assert ld.is_beta("gujarati") is True
    assert ld.is_beta("hindi") is False


def test_reply_instruction_strings_present():
    for lang in ("hindi", "english", "hinglish", "gujarati"):
        s = ld.reply_instruction(lang)
        assert isinstance(s, str) and s.strip()
    # English instruction is English; Hindi/Hinglish instructions carry Devanagari.
    assert "English" in ld.reply_instruction("english")
    assert any(0x0900 <= ord(c) <= 0x097F for c in ld.reply_instruction("hindi"))


# --------------------------------------------------------------------------- #
# LanguageTracker — hysteresis + adaptive switching
# --------------------------------------------------------------------------- #
def test_tracker_default_v2_config():
    t = ld.LanguageTracker(default="hindi")
    assert t.active == "hindi"
    assert t.conf_floor == 0.30  # V2 inbound floor (short English turns)
    assert t.min_streak == 1     # one confident turn flips


def test_tracker_switches_hindi_to_english_in_one_turn():
    t = ld.LanguageTracker(default="hindi")
    active, switched = t.update("yes I am interested please share the details")
    assert active == "english"
    assert switched is True


def test_tracker_switch_back_to_hindi():
    t = ld.LanguageTracker(default="hindi")
    t.update("can you tell me the price please")      # -> english
    assert t.active == "english"
    active, switched = t.update("नहीं भाई हिंदी में बताओ")  # -> hindi
    assert active == "hindi"
    assert switched is True


def test_tracker_no_switch_on_steady_state():
    t = ld.LanguageTracker(default="hindi")
    a1, s1 = t.update("ठीक है मैं समझ गया")
    assert a1 == "hindi" and s1 is False  # already hindi, no switch
    a2, s2 = t.update("और बताओ")
    assert a2 == "hindi" and s2 is False


def test_tracker_low_confidence_does_not_flap():
    t = ld.LanguageTracker(default="hindi", conf_floor=0.9)  # very high floor
    # "kitne ka hai" -> hinglish conf ~0.83 < 0.9 floor -> stays hindi, no switch.
    active, switched = t.update("kitne ka hai")
    assert active == "hindi"
    assert switched is False


def test_tracker_never_raises_on_garbage():
    t = ld.LanguageTracker(default="hinglish")
    active, switched = t.update(None)  # type: ignore[arg-type]
    assert active == "hinglish"
    assert switched is False


# --------------------------------------------------------------------------- #
# ISOLATION — zero droplet_work imports at load
# --------------------------------------------------------------------------- #
def test_no_droplet_import_on_load():
    # Importing the module must not pull droplet_work into sys.modules.
    import importlib

    import voice_kernel.language  # noqa: F401
    import voice_kernel.language.detector  # noqa: F401
    import voice_kernel.language.mirror  # noqa: F401

    assert not any(m == "droplet_work" or m.startswith("droplet_work.")
                   for m in sys.modules), "language module must be droplet-free"
