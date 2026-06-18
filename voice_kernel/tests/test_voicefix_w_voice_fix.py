"""test_voicefix_w_voice_fix — the W-VOICE-FIX regression gate.

Covers the four founder-reported outbound regressions + the cross-path AI-self-
label ban, ALL on the branch (no live calls):

  1. NO "AI assistant" / AI-self-label in the rendered opener/prompt across many
     campaign field shapes (Unit A), AND a campaign-supplied banned ai_disclosure
     is SCRUBBED (cannot reach the prompt).
  2. EXACTLY ONE greeting — the default (OPENER_ALREADY_SAID) renders the
     "already opened, do NOT re-greet" instruction and NO fresh-greeting OPENER
     section, so turn-1 cannot become a second greeting (Unit B).
  3. NEUTRAL prosody — the kernel filler injection is OFF by default and the
     speech planner does not prepend verbal-nod fillers; EL/Sarvam neutral
     defaults are asserted at the source (Unit D).
  4. Hinglish GRAMMAR smoke — the OUTBOUND prompt pins first-person ("मैंने/हमने
     call किया") and explicitly forbids the inbound "आपने call किया" error (Unit C).
  5. REPO-WIDE grep — no SHIPPED voice path emits an AI-self-label as a SPOKEN
     line (only negative guards / meta-instructions may name the banned token).

The kernel disclosure builder is also asserted clean + guardrail-reconciled
(MISS #2). Tests that need the legacy prompt skip gracefully if droplet_work is
absent (CI checkout without it).
"""
from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

from voice_kernel.brain_packs.disclosure import (
    DisclosureConfig,
    DisclosureTier,
    build_disclosure_str,
    contains_banned_phrase,
    strip_guardrail,
)
from voice_kernel.speech.prosody import apply_prosody

from .conftest import load_legacy_prompt_module

_REPO_ROOT = Path(__file__).resolve().parents[2]


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _legacy_prompt():
    mod = load_legacy_prompt_module()
    if mod is None:
        pytest.skip("droplet_work/prompt.py not present (CI checkout without droplet_work)")
    return mod


def _legacy_prompt_with_env(opener_already_said: str | None):
    """Fresh-load droplet_work/prompt.py with OPENER_ALREADY_SAID set/unset BEFORE
    load (the OPENER section is decided at render-time from os.getenv, so we set the
    env then load a fresh module object — no importlib.reload, which can't find the
    privately-named isolated module)."""
    prev = os.environ.get("OPENER_ALREADY_SAID")
    if opener_already_said is None:
        os.environ.pop("OPENER_ALREADY_SAID", None)
    else:
        os.environ["OPENER_ALREADY_SAID"] = opener_already_said
    try:
        mod = load_legacy_prompt_module()
        if mod is None:
            pytest.skip("droplet_work/prompt.py not present")
        return mod.build_system_prompt(mod.GODREJ_FIELDS)
    finally:
        if prev is None:
            os.environ.pop("OPENER_ALREADY_SAID", None)
        else:
            os.environ["OPENER_ALREADY_SAID"] = prev


# A spread of campaign field shapes — covers: no disclosure, custom-clean,
# custom-BANNED (must be scrubbed), male voice, English campaign, minimal fields.
_FIELD_SHAPES = [
    {},  # absolute minimum -> falls back to GODREJ defaults
    {"company_name": "AGARO", "product_name": "Regal 800W Vacuum"},
    {"company_name": "Shapoorji", "product_name": "Joyville", "voice_gender": "male"},
    {"company_name": "Acme", "product_name": "Widget", "disclose_ai": False},
    {"company_name": "Acme", "product_name": "Widget",
     "ai_disclosure": "Acme की एक AI assistant"},  # BANNED custom -> must be scrubbed
    {"company_name": "Acme", "product_name": "Widget",
     "ai_disclosure": "Acme की Riya"},  # clean custom -> may pass through
    {"company_name": "Globex", "product_name": "Plan X", "primary_language": "English"},
]


# --------------------------------------------------------------------------- #
# 1. NO AI self-label in the rendered opener / prompt (Unit A)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("shape", _FIELD_SHAPES)
def test_rendered_prompt_has_no_ai_self_label(shape):
    p = _legacy_prompt()
    fields = {**p.GODREJ_FIELDS, **shape}
    rendered = p.build_system_prompt(fields)
    # The SPOKEN-surface tokens must never appear as a self-label. (The prompt may
    # legitimately NAME these as PROHIBITIONS — "कभी 'AI'/'assistant' मत कहना" — so
    # we scan for the AFFIRMATIVE self-label token, not the bare word "AI".)
    for banned in ("AI assistant", "की एक AI assistant", "AI असिस्टेंट",
                   "एक AI assistant हो", "एक AI assistant है"):
        assert banned not in rendered, f"AI self-label leaked into prompt for {shape!r}: {banned!r}"


def test_banned_custom_disclosure_is_scrubbed():
    p = _legacy_prompt()
    fields = {**p.GODREJ_FIELDS, "company_name": "Acme",
              "ai_disclosure": "Acme की एक AI assistant"}
    rendered = p.build_system_prompt(fields)
    assert "की एक AI assistant" not in rendered
    # the clean brand-human framing should be present instead
    assert "की तरफ़ से" in rendered


def test_godrej_default_ai_disclosure_is_empty():
    p = _legacy_prompt()
    assert p.GODREJ_FIELDS["ai_disclosure"] == "", "default ai_disclosure must be empty (never bake the banned phrase)"


def test_opener_verbs_carry_no_ai_label():
    p = _legacy_prompt()
    for g in ("male", "female"):
        v = p._opener_verbs(g)
        assert not contains_banned_phrase(v["ex_role"]), f"_opener_verbs[{g}] ex_role is a banned label: {v['ex_role']!r}"


def test_prompt_banned_check_reuses_kernel_blocklist():
    """prompt.py's scrubber must agree with the kernel block-list (single source)."""
    p = _legacy_prompt()
    assert p._contains_banned_self_label("Acme की एक AI assistant") is True
    assert p._contains_banned_self_label("I am an AI") is True
    assert p._contains_banned_self_label("Acme की तरफ़ से Riya") is False


# --------------------------------------------------------------------------- #
# 2. EXACTLY ONE greeting — no double (Unit B)
# --------------------------------------------------------------------------- #
def test_default_renders_already_opened_no_regreet():
    # default (no env) = OPENER_ALREADY_SAID effective -> "already opened" note,
    # NO fresh-greeting OPENER section.
    rendered = _legacy_prompt_with_env(None)
    assert "तुम पहले ही OPEN कर चुकी/चुके हो" in rendered, "missing 'already opened' instruction"
    assert "=== OPENER (पहला turn" not in rendered, "legacy fresh-greeting OPENER section still rendered by default"


def test_flag_off_restores_legacy_opener_but_still_no_ai_label():
    rendered = _legacy_prompt_with_env("0")
    assert "=== OPENER (पहला turn" in rendered, "legacy OPENER section not restored when flag off"
    # even the legacy greeting path must carry NO AI self-label
    assert "AI assistant" not in rendered


def test_flow_step1_has_no_fresh_greeting_verb_by_default():
    rendered = _legacy_prompt_with_env(None)
    # FLOW step-1 must CONFIRM IDENTITY, not instruct a fresh "नमस्ते/greet".
    assert "CONFIRM IDENTITY" in rendered
    assert "दोबारा 'नमस्ते'/greeting मत करना" in rendered, "FLOW step-1 still instructs a fresh greeting"


# --------------------------------------------------------------------------- #
# 3. NEUTRAL prosody bounds (Unit D)
# --------------------------------------------------------------------------- #
def test_fillers_off_by_default():
    os.environ.pop("VOICE_FILLERS", None)
    sents = ("Bilkul.", "Yeh ek accha option hai.", "Aap kya sochte hain.", "Theek hai.")
    out = apply_prosody(sents, hinglish=True)
    # no sentence should have gained a prepended verbal-nod filler
    for s in out:
        assert not s.lower().startswith(("haan,", "achha,", "toh,", "dekhiye,")), f"filler leaked: {s!r}"


def test_fillers_can_be_forced_on():
    sents = ("Yeh ek accha option hai.", "Aap kya sochte hain.", "Bahut log lete hain.", "Theek hai.")
    out = apply_prosody(sents, hinglish=True, fillers=True)
    assert any(s.lower().startswith(("haan,", "achha,", "toh,", "dekhiye,")) for s in out), \
        "forcing fillers on produced no filler"


def test_el_and_sarvam_defaults_are_neutral_in_source():
    """The in-code TTS defaults must be the NEUTRAL values (so a fresh deploy is
    neutral even without the systemd drop-in)."""
    agent_src = (_REPO_ROOT / "droplet_work" / "agent.py")
    if agent_src.exists():
        txt = agent_src.read_text(encoding="utf-8")
        assert 'os.getenv("EL_STABILITY", "0.65")' in txt, "EL_STABILITY default not neutral 0.65"
        assert 'os.getenv("EL_SPEED", "1.0")' in txt, "EL_SPEED default not neutral 1.0"
        assert 'os.getenv("EL_STABILITY", "0.45")' not in txt, "old expressive EL_STABILITY 0.45 still default"
    sarvam_src = (_REPO_ROOT / "src" / "agent.py")
    if sarvam_src.exists():
        st = sarvam_src.read_text(encoding="utf-8")
        assert 'os.getenv("SARVAM_TTS_PACE", "1.0")' in st, "SARVAM pace default not neutral 1.0"


# --------------------------------------------------------------------------- #
# 4. Hinglish grammar smoke — first-person outbound, never "aapne call kiya" (Unit C)
# --------------------------------------------------------------------------- #
def test_outbound_prompt_pins_first_person_and_forbids_aapne():
    p = _legacy_prompt()
    rendered = p.build_system_prompt(p.GODREJ_FIELDS)
    # OUTBOUND framing present
    assert "OUTBOUND" in rendered
    # explicit anti-pattern: never "aapne call kiya"
    assert "आपने call किया" in rendered, "missing the 'never say आपने call किया' anti-pattern"
    assert "मत कहना" in rendered  # the forbidding verb near the anti-pattern


# --------------------------------------------------------------------------- #
# 5. KERNEL disclosure clean + guardrail reconciled to "never admit" (MISS #2)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("tier", [DisclosureTier.BRAND_IDENTITY,
                                  DisclosureTier.ASSISTANT_CUE,
                                  DisclosureTier.EXPLICIT_AI])
@pytest.mark.parametrize("lang", ["hinglish", "english"])
def test_kernel_disclosure_spoken_is_clean(tier, lang):
    cfg = DisclosureConfig(tier=tier, language=lang)
    s = build_disclosure_str("AGARO", "vacuum cleaner offer", cfg)
    spoken = strip_guardrail(s)
    assert not contains_banned_phrase(spoken), f"kernel disclosure SPOKEN tripped block-list: {spoken!r}"


def test_kernel_guardrail_is_never_admit_not_honest_disclose():
    """MISS #2: the guardrail must instruct 'do NOT admit', NOT 'answer honestly'."""
    for lang in ("english", "hinglish"):
        s = build_disclosure_str("AGARO", "offer", DisclosureConfig(language=lang))
        guard = s.split("GUARDRAIL:", 1)[1] if "GUARDRAIL:" in s else ""
        low = guard.lower()
        # English must say "do NOT admit"; hinglish must say "never call yourself AI"
        # ("khud ko AI ... mat batana"), NOT the inverted "AI hone se inkaar mat karna"
        # (= "do not DENY being AI" = admit), which was a red-team residue.
        if lang == "english":
            assert "do not admit" in low, f"guardrail not 'never admit' (english): {guard!r}"
        else:
            assert "mat batana" in low or "sweekar mat" in low, f"guardrail not 'never admit' (hinglish): {guard!r}"
            assert "inkaar mat karna" not in low, (
                "hinglish guardrail says 'AI hone se inkaar mat karna' = do-not-DENY-being-AI "
                "(inverted = admit); founder rule is NEVER admit"
            )
        assert "answer briefly and honestly" not in low, "guardrail still honest-discloses (MISS #2 unreconciled)"
        assert "chhota sa sach bata kar" not in low, "guardrail still honest-discloses (hinglish)"


def test_kernel_rejects_banned_vendor_disclosure():
    cfg = DisclosureConfig(vendor_script_disclosure="Acme की एक AI assistant")
    s = build_disclosure_str("Acme", "offer", cfg)
    assert not contains_banned_phrase(strip_guardrail(s)), "banned vendor disclosure was not rejected"


# --------------------------------------------------------------------------- #
# 6. REPO-WIDE: no SHIPPED voice path emits an AI-self-label as a SPOKEN line
# --------------------------------------------------------------------------- #
# A SPOKEN line is one passed to session.say(...)/sess.say(...) OR an opener/
# greeting string literal. We scan the live agent files for an AFFIRMATIVE AI
# self-label inside a spoken-string literal. Negative guards ("NEVER say you are
# an AI") and meta-instructions are allowed and excluded by requiring the token
# to NOT be preceded by a negation within the same line.
_SPOKEN_FILES = [
    _REPO_ROOT / "droplet_work" / "agent.py",
    _REPO_ROOT / "droplet_work" / "aim_voice_agent.py",
    _REPO_ROOT / "droplet_work" / "prompt.py",
]

# affirmative self-label tokens that must never be SPOKEN
_AFFIRMATIVE_SELF_LABEL = re.compile(
    r"(your ai manager|the ai manager for|"
    r"मैं .{0,12}AI assistant|की एक AI assistant|"
    r"i am an ai assistant|i'm an ai assistant)",
    re.IGNORECASE,
)
# negation / non-spoken cues — if present on the line, the token is a PROHIBITION
# or a block-list DEFINITION (the detector's own banned-phrase tuple), NOT a spoken
# self-label. Block-list definitions (e.g. prompt.py's _BANNED_SELF_LABELS tuple)
# legitimately list the banned tokens so the scrubber can catch them.
_NEGATION = re.compile(
    r"(never|not |n't|do not|don't|मत |नहीं|kabhi|inkaar|overrid|guardrail|banned|"
    r"prohibit|block.?list|self.?label|_banned|phrases|contains_banned)",
    re.IGNORECASE,
)


def test_no_shipped_path_speaks_an_ai_self_label():
    offenders: list[str] = []
    for fp in _SPOKEN_FILES:
        if not fp.exists():
            continue
        lines = fp.read_text(encoding="utf-8").splitlines()
        in_blocklist = False
        for i, line in enumerate(lines, 1):
            # Track a multi-line block-list/tuple definition (e.g. _BANNED_SELF_LABELS = (...)).
            # Lines inside such a tuple list the banned tokens for DETECTION, never speak them.
            low = line.lower()
            if re.search(r"(_banned|banned_phrases|self.?label).{0,40}[=(]|block.?list", low):
                in_blocklist = True
            if in_blocklist and ")" in line and "(" not in line:
                in_blocklist = False  # tuple closes on this line
                continue
            if in_blocklist:
                continue
            if _AFFIRMATIVE_SELF_LABEL.search(line) and not _NEGATION.search(line):
                offenders.append(f"{fp.name}:{i}: {line.strip()[:120]}")
    assert not offenders, "AI self-label found on a non-negated (spoken) line:\n" + "\n".join(offenders)
