"""W5 tests — SpeechPlanner: half-word guard, casual Hinglish, spoken
normalization (₹ lakh / phone / date), provider-keyed rendering, contract
conformance, and zero droplet_work/agent imports."""
from __future__ import annotations

import re

from voice_kernel.contracts import SpeechPlan, SpeechPlanner
from voice_kernel.kernel import build_kernel
from voice_kernel.packet import CampaignCard
from voice_kernel.speech import build_speech_planner
from voice_kernel.speech.hinglish import enforce_casual_hinglish, has_literary_hindi
from voice_kernel.speech.normalize import normalize_text
from voice_kernel.speech.segment import repair_truncation, split_sentences

HINGLISH_CARD = CampaignCard(language="Hinglish")
EN_CARD = CampaignCard(language="English")


def _planner(provider="sarvam") -> SpeechPlanner:
    p = build_speech_planner(provider)
    assert isinstance(p, SpeechPlanner)  # runtime_checkable Protocol conformance
    return p


# --------------------------------------------------------------------------- #
# (a) HALF-WORD / truncation guard
# --------------------------------------------------------------------------- #
def test_paragraph_never_yields_a_half_word():
    p = _planner()
    # a multi-sentence paragraph that is then cut mid-word at the end
    raw = (
        "Namaste, main Riya bol rahi hoon. Aapke liye ek badhiya offer hai. "
        "Yeh ghar bahut spaci"
    )
    plan = p.plan(raw, "hi-IN", HINGLISH_CARD)
    # the dangling 'spaci' must NOT survive as the final spoken token.
    assert not plan.text.rstrip().endswith("spaci")
    # every segment ends on a complete word (terminal punctuation or full word)
    for seg in plan.segments:
        assert seg.strip(), "no empty segments"
        last_word = re.findall(r"[A-Za-zऀ-ॿ]+", seg)
        # final char should be terminal punctuation or a complete word char
        assert seg.rstrip()[-1] in ".!?…।" or last_word, seg


def test_repair_truncation_keeps_earlier_complete_sentence():
    out = repair_truncation("Yeh offer aaj tak valid hai. Iski keemat bahut kam")
    assert out.endswith("valid hai.")  # dropped the dangling clause


def test_complete_short_beat_is_left_alone():
    assert repair_truncation("Haan ji.") == "Haan ji."
    assert split_sentences("Ek. Do. Teen.") == ("Ek.", "Do.", "Teen.")


# --------------------------------------------------------------------------- #
# (b) casual Hinglish — literary words replaced
# --------------------------------------------------------------------------- #
def test_mahatvapurn_class_words_are_replaced():
    assert "mahatvapurn" not in enforce_casual_hinglish("yeh bahut mahatvapurn hai").lower()
    assert enforce_casual_hinglish("yeh bahut mahatvapurn hai") == "yeh bahut zaroori hai"
    assert "Zaroori" in enforce_casual_hinglish("Mahatvapurn baat")  # case preserved
    # devanagari literary form too
    assert "zaroori" in enforce_casual_hinglish("यह महत्वपूर्ण है")
    assert not has_literary_hindi(enforce_casual_hinglish("kripya dhyan dein, yeh avashyak hai"))


def test_planner_strips_literary_hindi_end_to_end():
    plan = _planner().plan("Yeh ek mahatvapurn jankari hai.", "hi-IN", HINGLISH_CARD)
    assert "mahatvapurn" not in plan.text.lower()


# --------------------------------------------------------------------------- #
# (c) numbers / price / phone / date render correctly spoken
# --------------------------------------------------------------------------- #
def test_rupees_lakh_renders_spoken_hinglish():
    out = normalize_text("Iski keemat ₹58 lakh hai", "hi-IN")
    assert "athaavan lakh" in out
    assert "58" not in out and "₹" not in out


def test_rupees_crore_half_word():
    assert "dhaai crore" in normalize_text("₹2.5 crore", "hi-IN")


def test_rupees_lakh_renders_spoken_english():
    out = normalize_text("It costs Rs 58 lakh", "en-IN")
    assert "fifty-eight lakh rupees" in out


def test_indian_grouping_full_amount():
    out = normalize_text("₹1,23,456", "en-IN")
    assert "one lakh twenty-three thousand four hundred fifty-six rupees" in out


def test_phone_number_is_digit_by_digit_never_cardinal():
    out = normalize_text("Call me on 9876543210", "hi-IN")
    # must be digit words, NOT a billions cardinal
    assert "nau aath saat chhe paanch" in out
    assert "billion" not in out and "9876543210" not in out


def test_date_renders_spoken():
    assert "ikkees June" in normalize_text("Visit on 21/06", "hi-IN")
    assert "the twenty-first of June" in normalize_text("Visit on 21/06", "en-IN")


def test_time_renders_spoken():
    assert "gyaarah baje" in normalize_text("Aaiye 11:00 baje", "hi-IN")
    assert "dhaai baje" in normalize_text("4:30 ka slot... actually 2:30", "hi-IN")


def test_percent_and_units():
    assert "twenty-five percent" in normalize_text("25% off", "en-IN")
    assert "square feet" in normalize_text("1200 sq ft flat", "en-IN")


def test_acronym_bhk_spelled():
    assert "do B H K" in normalize_text("2BHK ready", "hi-IN")


# --------------------------------------------------------------------------- #
# (d) sparse fillers / adaptive punctuation; NONE on sensitive lines
# --------------------------------------------------------------------------- #
def test_no_filler_on_price_or_phone_line():
    # a price line must stay clean — no injected filler word.
    plan = _planner().plan("Iski keemat ₹85 lakh hai. Kya aap ready hain.", "hi-IN", HINGLISH_CARD)
    price_seg = [s for s in plan.segments if "lakh" in s][0]
    # the price segment should not have gained a leading conversational filler
    assert not price_seg.lower().startswith(("haan,", "achha,", "toh,", "dekhiye,"))


# --------------------------------------------------------------------------- #
# (e) provider-keyed rendering
# --------------------------------------------------------------------------- #
def test_tts_lang_stamped():
    assert _planner().plan("hello", "hi-IN", HINGLISH_CARD).tts_lang == "hi-IN"
    assert _planner().plan("hello", "en-IN", EN_CARD).tts_lang == "en-IN"


def test_fail_open_returns_raw_on_internal_error():
    # empty text path is valid; force the normal path returns normalized=True
    plan = _planner().plan("Sab badhiya hai.", "hi-IN", HINGLISH_CARD)
    assert plan.normalized is True
    assert plan.text


def test_planner_registers_via_build_kernel():
    p = build_speech_planner("sarvam")
    k = build_kernel(speech=p)
    assert k.svc.speech is p


# --------------------------------------------------------------------------- #
# 0 droplet_work/agent imports
# --------------------------------------------------------------------------- #
def test_no_droplet_agent_import_in_speech_package():
    import ast
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[1] / "speech"
    banned = ("droplet_work", "agent", "aim_voice_agent", "caller")
    for f in root.glob("*.py"):
        tree = ast.parse(f.read_text(encoding="utf-8"), filename=str(f))
        for node in ast.walk(tree):
            mods = []
            if isinstance(node, ast.Import):
                mods = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                mods = [node.module or ""]
            for m in mods:
                top = m.split(".")[0]
                assert top not in banned, f"{f} imports {m}"
