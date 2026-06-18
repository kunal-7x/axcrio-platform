"""Unit tests for voice_kernel.language.mirror — the per-turn mirror decision
({reply_language, tts_lang_code, changed, instruction}). Asserts it is ADAPTIVE
(no hardcoded language) and mirrors across a Hindi->English->Hindi->Hinglish call.
"""
from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from voice_kernel.language import detector as ld
from voice_kernel.language import mirror as mr


def test_mirror_decision_dict_shape():
    d = mr.mirror_once("नमस्ते", "hindi")
    out = d.as_dict()
    assert set(out.keys()) == {"reply_language", "tts_lang_code", "changed", "instruction"}
    assert out["reply_language"] == "hindi"
    assert out["tts_lang_code"] == "hi"
    assert isinstance(out["changed"], bool)
    assert isinstance(out["instruction"], str) and out["instruction"].strip()


def test_mirror_once_english_turn():
    d = mr.mirror_once("yes please tell me the price and details", "hindi")
    assert d.reply_language == "english"
    assert d.tts_lang_code == "en"
    assert d.changed is True  # flipped from the active hindi seed


def test_mirror_once_is_adaptive_not_hardcoded():
    # Same English utterance, different active seeds -> reply mirrors the UTTERANCE,
    # never a fixed default. (changed flag depends on the seed.)
    eng = "what is the location and budget please"
    d_from_hi = mr.mirror_once(eng, "hindi")
    d_from_en = mr.mirror_once(eng, "english")
    assert d_from_hi.reply_language == "english"
    assert d_from_en.reply_language == "english"
    assert d_from_hi.changed is True    # hindi -> english = a switch
    assert d_from_en.changed is False   # already english = no switch


def test_mirror_turn_full_call_sequence_adaptive():
    """The founder scenario: speaks Hindi, switches to English mid-call, switches
    back to Hindi, then Hinglish. The mirror must follow EVERY turn."""
    tracker = ld.LanguageTracker(default="hindi")

    # Turn 1: Hindi -> reply hindi, tts hi.
    d1 = mr.mirror_turn("हाँ बताइए मुझे जानकारी चाहिए", tracker)
    assert d1.reply_language == "hindi"
    assert d1.tts_lang_code == "hi"

    # Turn 2: English mid-call -> reply english, tts en, CHANGED.
    d2 = mr.mirror_turn("can you please tell me the price and details", tracker)
    assert d2.reply_language == "english"
    assert d2.tts_lang_code == "en"
    assert d2.changed is True

    # Turn 3: switch BACK to Hindi -> reply hindi, tts hi, CHANGED.
    d3 = mr.mirror_turn("नहीं हिंदी में बात करिए", tracker)
    assert d3.reply_language == "hindi"
    assert d3.tts_lang_code == "hi"
    assert d3.changed is True

    # Turn 4: Hinglish code-mix -> reply hinglish, tts hi.
    d4 = mr.mirror_turn("मुझे property visit करनी है site पर", tracker)
    assert d4.reply_language == "hinglish"
    assert d4.tts_lang_code == "hi"


def test_mirror_gujarati_speaks_hindi_not_silence():
    d = mr.mirror_once("કેમ છો તમે મજામાં", "hindi")
    assert d.reply_language == "gujarati"
    assert d.tts_lang_code == "hi"  # NEVER 'gu' (dead-air fix)


def test_mirror_never_raises_on_garbage():
    tracker = ld.LanguageTracker(default="hinglish")
    d = mr.mirror_turn(None, tracker)  # type: ignore[arg-type]
    assert d.reply_language == "hinglish"
    assert d.changed is False
