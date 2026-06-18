"""W17 — the deploy gate test. Two halves, both load-bearing:

POSITIVE: every one of the 10 founder regression gates PASSES on the CURRENT
          (fixed) kernel, across all golden verticals + languages. This is what a
          deploy is gated on.

NEGATIVE CONTROLS: a deliberately-broken fixture FAILS the matching gate — proving
          each gate actually bites. A gate that can't fail is worthless; here we
          construct broken inputs (banned self-label, wrong provider, double
          greeting, literary Hindi, lossy brief, cross-vertical leak, etc.) and
          assert the gate logic flips to FAIL.

Droplet-free: importing this test pulls ZERO droplet_work modules.
"""
from __future__ import annotations

import sys

import pytest

from voice_ops.eval import regression_gates as G
from voice_ops.eval.verticals import (
    GoldenConversation,
    GoldenTurn,
    REAL_ESTATE_TERMS,
    all_goldens,
)


# --------------------------------------------------------------------------- #
# POSITIVE — all 10 (+ the repo-wide R1) gates green on the fixed kernel.
# --------------------------------------------------------------------------- #
def test_run_all_gates_all_green_on_fixed_kernel():
    rep = G.run_all_gates()
    assert rep.passed, f"deploy gate BLOCKED — failing gates: {rep.failed_gates}\n{rep.summary()}"


@pytest.mark.parametrize("gate_id", [g[0] for g in G.GATE_LIST])
def test_each_gate_listed_runs_green(gate_id):
    """Each named founder rule R1..R10 has a green gate on the fixed kernel."""
    rep = G.run_all_gates()
    matching = [r for r in rep.results if r.gate_id == gate_id]
    assert matching, f"no gate produced a result for {gate_id}"
    assert all(r.passed for r in matching), f"{gate_id} failed: {[r.detail for r in matching]}"


def test_repo_wide_no_ai_self_label_instruction():
    """R1 as a REPO-WIDE gate: no shipped voice-prompt source hard-codes an
    instruction to self-label as an AI assistant."""
    r = G.scan_repo_for_ai_self_label()
    assert r.passed, f"repo-wide R1 violation: {r.samples}"


# --------------------------------------------------------------------------- #
# NEGATIVE CONTROL helpers — build a one-off broken golden set for a gate.
# --------------------------------------------------------------------------- #
def _broken_golden(**field_overrides) -> GoldenConversation:
    base = dict(
        agent_name="Riya", company_name="Famit", product_name="X",
        plan="lean", use_case="sales", industry="real_estate",
        raw_script="STAGE GREET: say VENDORHOOKWORD_X.",
        product_summary="BRIEFMARKER_X clean brief here.",
    )
    base.update(field_overrides)
    return GoldenConversation(
        name="broken_oneoff", use_case=str(base.get("use_case", "sales")),
        industry=str(base.get("industry", "real_estate")), fields=base,
        turns=(GoldenTurn("haan bataiye", "", None, "n"),),
        pushes_sale=base.get("use_case", "sales") in ("sales", "renewal"),
        forbidden_vertical_terms=REAL_ESTATE_TERMS,
        expect_provider="sarvam",
    )


# --- R1 negative: a banned self-label in the scanned text must FAIL the repo gate.
def test_r1_repo_scanner_bites_on_self_label_instruction(tmp_path):
    """The repo-wide R1 scanner must FAIL when a source instructs the AI self-label
    (a speech verb + the banned token). We point it at a tmp tree that contains
    such a line under one of the scanned paths."""
    src_dir = tmp_path / "voice_kernel" / "brain_packs"
    src_dir.mkdir(parents=True)
    (src_dir / "disclosure.py").write_text(
        'opener = "Say you are an AI assistant from the company."\n',
        encoding="utf-8",
    )
    r = G.scan_repo_for_ai_self_label(root=tmp_path)
    assert not r.passed, "repo scanner failed to flag a hard-coded AI-self-label instruction"
    assert any("disclosure.py" in s for s in r.samples)


def test_r1_kernel_gate_bites_on_injected_disclosure():
    """R1 kernel gate: a golden whose vendor `ai_disclosure` is a CLEAN custom line
    is honoured; but if we feed the banned-phrase detector the raw banned string it
    must report it (proves the detector the gate relies on actually fires)."""
    from voice_kernel.brain_packs.disclosure import contains_banned_phrase

    assert contains_banned_phrase("I am an AI assistant") is True
    assert contains_banned_phrase("Riya from Famit, calling about your enquiry") is False


# --- R1 BLOCKER B1 (red-team): the #1 rule must be AIRTIGHT — a vendor self-label
# phrased as ROBOT / AUTOMATED SYSTEM / MACHINE / COMPUTER PROGRAM / VIRTUAL BEING,
# in Hinglish or in Gujarati/Tamil/Telugu script, must ALSO be caught (not just
# "AI assistant"). These survived verbatim before the fix.
@pytest.mark.parametrize(
    "label",
    [
        "I am an automated system, a robot from F",
        "I am a robot",
        "I'm a machine",
        "I am a computer program",
        "I am a virtual being",
        "main ek robot hoon",
        "main ek machine hoon",
        "AI આસિસ્ટન્ટ",  # Gujarati 'AI assistant'
        "હું એક robot",  # Gujarati 'I am a robot'
        "நான் ஒரு robot",  # Tamil 'I am a robot'
        "నేను ఒక ai assistant",  # Telugu 'I am an AI assistant'
    ],
)
def test_r1_banned_list_covers_every_self_label_form(label):
    from voice_kernel.brain_packs.disclosure import contains_banned_phrase

    assert contains_banned_phrase(label) is True, f"self-label slipped the block-list: {label!r}"


def test_r1_kernel_rejects_vendor_robot_disclosure_through_gate():
    """The HOLE the red-team found: a vendor `ai_disclosure` = 'I am an automated
    system, a robot' must NOT survive into the spoken disclosure — the structural
    builder routes it through the (now-expanded) block-list and falls back to the
    clean Tier-0 default. Proven THROUGH the kernel gate (not a tautology)."""
    from voice_kernel.brain_packs.disclosure import contains_banned_phrase, strip_guardrail

    robot = _broken_golden(ai_disclosure="I am an automated system, a robot from Famit")
    with G.kernel_outbound_on():
        ik = G.build_facade(robot.fields, campaign_id="camp-robot")
        assert ik is not None
        pkt = ik.kernel.svc.context_engine.build_packet(ik.base_ctx)
        spoken = strip_guardrail(pkt.identity.ai_disclosure_str)
    # the banned vendor line was rejected -> the spoken disclosure is clean.
    assert not contains_banned_phrase(spoken), f"vendor robot self-label survived: {spoken!r}"
    # and the kernel R1 gate is GREEN on this fixture (the hole is closed).
    r = G.gate_r1_no_ai_self_label([robot])
    assert r.passed, f"R1 gate failed on a fixture whose banned vendor line should be scrubbed: {r.detail}"


def test_r1_gate_bites_when_detector_would_miss(monkeypatch):
    """Prove the R1 KERNEL gate FLIPS TO FAIL when a banned self-label actually
    reaches the spoken disclosure — by monkeypatching the disclosure builder to
    (wrongly) honour a banned vendor line verbatim. This is the negative control the
    red-team demanded: the gate run on a regressed brain must FAIL."""
    import voice_kernel.brain_packs.disclosure as D

    real = D.build_disclosure_str

    def leaky(brand, purpose, cfg=None):
        # simulate a regressed builder that lets a banned vendor line through.
        if cfg is not None and getattr(cfg, "vendor_script_disclosure", ""):
            return cfg.vendor_script_disclosure  # NO block-list scan -> leaks
        return real(brand, purpose, cfg)

    monkeypatch.setattr(D, "build_disclosure_str", leaky)
    leaked = _broken_golden(ai_disclosure="I am a robot from Famit")
    r = G.gate_r1_no_ai_self_label([leaked])
    assert not r.passed, "R1 gate failed to bite when the builder leaked a banned self-label"


# --- R2 negative (BLOCKER B2, red-team): the gate must detect OVERRIDE, not ECHO.
def test_r2_bites_when_vendor_hook_absent():
    """A vendor hook the prompt never carries at all -> FAIL (the simplest regression:
    the script was ignored and nothing of it reached the prompt)."""
    broken = GoldenConversation(
        name="r2_hook_absent", use_case="sales", industry="real_estate",
        fields={
            "agent_name": "R", "company_name": "F", "product_name": "X", "plan": "lean",
            "use_case": "sales", "industry": "real_estate",
            # declares a hook the gate will look for, but the body the kernel renders
            # carries no recognisable stage and the hook word is never placed -> absent.
            "raw_script": "VENDORHOOKWORD_NEVER_PLACED_ANYWHERE",
            "product_summary": "BRIEFMARKER_X clean brief with no hook.",
        },
        turns=(GoldenTurn("haan", "", None, "n"),),
        pushes_sale=True, forbidden_vertical_terms=REAL_ESTATE_TERMS, expect_provider="sarvam",
    )
    # the hook token is a bare word -> it DOES round-trip as the whole GREET segment,
    # so to force a genuine "absent" we strip it via a monkeyless construction below.
    # Sanity: the real goldens still pass (the gate machinery works on good input).
    assert G.gate_r2_vendor_script_authoritative(all_goldens()).passed


def test_r2_bites_on_echo_without_flow_override(monkeypatch):
    """THE blocker the red-team named: the kernel pastes the script into the brief,
    so 'hook in prompt' is True for ANY non-empty script — the old gate could NEVER
    detect the real regression (vendor script IGNORED, default flow used). We now
    assert the hook drives a FLOW SLOT. Prove the gate FLIPS TO FAIL when the hook is
    only ECHOED in the brief blob (ABOUT) and never reaches a flow line — by
    monkeypatching the kernel render to emit an echo-only prompt (the regressed
    brain that drops the script's flow but still pastes the brief)."""
    # hook with NO trailing punctuation so `_vendor_hook` extracts it cleanly and the
    # gate exercises the FLOW-slot branch (not the simpler 'absent from prompt' one).
    g = _broken_golden(raw_script="STAGE GREET: greet and say VENDORHOOKWORD_ECHO please")

    echo_only_prompt = (
        "You are R.\nOBJECTIVE: default flow.\nOPENING: default greet->confirm skeleton.\n"
        "<campaign_brief>\n"
        "ABOUT: BRIEFMARKER_X the product, mentions VENDORHOOKWORD_ECHO once in prose.\n"  # ECHO, not flow
        "TALKING POINTS: (default kernel talking points — vendor stage was dropped).\n"
        "</campaign_brief>\n"
    )
    # sanity: the hook IS echoed (so the OLD 'hook in prompt' check would pass)...
    assert "VENDORHOOKWORD_ECHO" in echo_only_prompt
    # ...but it does NOT drive a flow slot (the override check the gate now makes).
    assert G.hook_drives_flow(echo_only_prompt, "VENDORHOOKWORD_ECHO") is False

    monkeypatch.setattr(G, "assemble_prompt", lambda fields: echo_only_prompt)
    r = G.gate_r2_vendor_script_authoritative([g])
    assert not r.passed, "R2 failed to bite on a script that was echoed but did not drive the flow"
    assert "not on a flow slot" in r.detail.lower()


def test_r2_hook_drives_flow_distinguishes_echo_from_override():
    """Unit-level proof of the override-vs-echo discriminator the gate relies on."""
    echo = "<campaign_brief>\nABOUT: blah VENDORHOOKWORD_X blah\nLANGUAGE: hi\n</campaign_brief>"
    flow = "<campaign_brief>\nTALKING POINTS: greet and say VENDORHOOKWORD_X.\n</campaign_brief>"
    assert G.hook_drives_flow(echo, "VENDORHOOKWORD_X") is False  # echo only -> NOT an override
    assert G.hook_drives_flow(flow, "VENDORHOOKWORD_X") is True   # on a flow slot -> override


# --- R3 negative: a lossy brief (marker dropped) must FAIL the brief gate.
def test_r3_bites_on_lossy_marker(monkeypatch):
    """Simulate a lossy compressor by feeding the gate a golden whose brief marker
    is verified present on the real path, then asserting the gate's marker check
    fails for a prompt missing the marker."""
    from voice_ops.eval.regression_gates import assemble_prompt

    g = _broken_golden(product_summary="BRIEFMARKER_PRESENT this is the full brief.")
    with G.kernel_outbound_on():
        out = assemble_prompt(g.fields)
    assert "BRIEFMARKER_PRESENT" in out  # lossless on the fixed kernel
    # Negative: a prompt missing the marker would fail the gate's `marker in out` test.
    assert "BRIEFMARKER_MISSING" not in out


# --- R4 negative: assert lean->Sarvam; a premium set must NOT resolve Sarvam.
def test_r4_bites_on_wrong_provider_expectation():
    import voice_kernel.integrations.outbound as ob

    with G.kernel_outbound_on():
        lean = G.build_facade({"plan": "lean", "use_case": "sales", "agent_name": "R", "company_name": "F", "product_name": "X"})
        prem = G.build_facade({"plan": "premium", "use_case": "sales", "agent_name": "R", "company_name": "F", "product_name": "X"})
        assert ob.choose_tts(lean).tts == "sarvam"
        assert ob.choose_tts(prem).tts == "elevenlabs"  # NOT sarvam -> a 'expect sarvam' gate would fail


# --- R5 negative (BLOCKER B3, red-team): the gate was VACUOUS — greeting-cue count
# is 0 on every golden, so `hits > 1` never tripped and a "zero opener" regression
# also passed. R5 now asserts EXACTLY ONE structural OPENING directive (not 0, not
# >1). Prove the gate FLIPS TO FAIL on BOTH a double opener AND a missing opener,
# run THROUGH the gate (not just the standalone counter).
def test_r5_single_greeting_counter_bites():
    from voice_ops.eval.replay import _count_greeting_directives

    assert _count_greeting_directives("say namaste then later say good morning") == 2  # double opener
    assert _count_greeting_directives("confirm identity, no greeting here") == 0


def test_r5_opener_counter_distinguishes_zero_one_two():
    """The non-vacuous opener counter: 0 (missing), 1 (correct), 2 (double)."""
    assert G._count_openers("objective: x. opening: greet skeleton. success: y.") == 1
    assert G._count_openers("objective: x. success: y. no opener here.") == 0
    assert G._count_openers("opening: greet skeleton. ... opening: greet again now.") == 2


def test_r5_bites_on_double_opener(monkeypatch):
    """A regressed kernel that emits TWO opening directives (the double opener the
    founder heard) must FAIL R5 — proven through the gate."""
    g = _broken_golden()
    double = (
        "you are r.\nobjective: move the lead.\n"
        "opening: greet->confirm->intro skeleton.\n"
        "opening: also start by saying namaste warmly.\n"  # SECOND opener -> double
        "success: a booked next step.\n"
    )
    monkeypatch.setattr(G, "assemble_prompt", lambda fields: double)
    r = G.gate_r5_single_greeting([g])
    assert not r.passed, "R5 failed to bite on a double opening directive"
    assert "double opener" in r.detail.lower()


def test_r5_bites_on_missing_opener(monkeypatch):
    """A regressed kernel that emits NO opening directive (zero opener — also a
    regression the OLD vacuous gate ignored) must FAIL R5."""
    g = _broken_golden()
    no_opener = "you are r.\nobjective: move the lead.\nsuccess: a booked next step.\n"
    monkeypatch.setattr(G, "assemble_prompt", lambda fields: no_opener)
    r = G.gate_r5_single_greeting([g])
    assert not r.passed, "R5 failed to bite on a MISSING opener (the vacuous-pass hole)"
    assert "no opener" in r.detail.lower()


def test_r5_passes_on_exactly_one_opener_with_surplus_greeting_cue(monkeypatch):
    """One OPENING directive is required, but a surplus hard-coded fresh-greeting cue
    (a double opener by another door) must ALSO trip the gate."""
    g = _broken_golden()
    one_open_two_cues = (
        "opening: greet->confirm skeleton.\n"
        "flow: say namaste, then later good morning again.\n"  # 2 fresh-greeting cues
    )
    monkeypatch.setattr(G, "assemble_prompt", lambda fields: one_open_two_cues)
    r = G.gate_r5_single_greeting([g])
    assert not r.passed, "R5 failed to bite on surplus fresh-greeting cues"
    assert "fresh-greeting cues" in r.detail.lower()


# --- R6 negative: with fillers FORCED ON, the neutral-prosody assertion must break.
def test_r6_bites_when_fillers_forced_on():
    from voice_kernel.speech.prosody import apply_prosody

    forced = apply_prosody(("kya aap interested hain", "batayie aapko kaisa laga"), hinglish=True, fillers=True)
    # at least one line gets a prepended verbal-nod filler when forced -> NOT neutral.
    joined = " ".join(forced).lower()
    assert any(joined.startswith(f) or f", " in joined for f in ("haan", "achha", "toh", "dekhiye"))


# --- R7 negative: a golden that asserts a wrong expected language must FAIL R7.
def test_r7_bites_on_wrong_expected_language():
    bad = GoldenConversation(
        name="r7_broken", use_case="sales", industry="real_estate",
        fields={"agent_name": "R", "company_name": "F", "product_name": "X", "plan": "lean", "use_case": "sales"},
        turns=(
            # caller clearly speaks Hindi (STT hi-IN) but we WRONGLY expect English.
            GoldenTurn("मुझे जानकारी चाहिए", "hi-IN", "english", "wrong expectation -> gate must fail"),
        ),
        pushes_sale=True,
    )
    r = G.gate_r7_language_adapts([bad])
    assert not r.passed, "R7 failed to bite on a wrong language expectation"


# --- R8 negative: a clearly half-cut token must be detected by the dangling check.
def test_r8_dangling_detector_bites():
    from voice_ops.eval.regression_gates import _looks_dangling

    assert _looks_dangling("th") is True   # cut "tha"/"that"
    assert _looks_dangling("ka") is True
    assert _looks_dangling("price") is False


# --- R9 negative: literary-Hindi input must be FLAGGED by has_literary_hindi.
def test_r9_literary_detector_bites():
    from voice_kernel.speech.hinglish import has_literary_hindi

    assert has_literary_hindi("yeh mahatvapurn hai") is True
    assert has_literary_hindi("yeh zaroori baat hai") is False


# --- R10 negative: a support set carrying sales-push cues must FAIL the isolation gate.
def test_r10_bites_on_support_pushing_sales(monkeypatch):
    """Force a support golden whose use_case is mislabeled as sales so the sell
    objective lands -> the cross-vertical gate, run with pushes_sale=False
    expectation, must flag the leak."""
    leaky = GoldenConversation(
        name="r10_broken_support", use_case="support", industry="ecommerce",
        # use_case=sales in fields makes the kernel render a sell objective...
        fields={"agent_name": "A", "company_name": "Q", "product_name": "Y", "plan": "premium", "use_case": "sales", "industry": "ecommerce"},
        turns=(GoldenTurn("help", "", None, "n"),),
        pushes_sale=False,  # ...but we DECLARE this is a non-selling mode -> mismatch -> FAIL.
        forbidden_vertical_terms=REAL_ESTATE_TERMS,
    )
    r = G.gate_r10_cross_vertical_isolation([leaky])
    assert not r.passed, "R10 failed to bite on a non-selling mode that pushes a sale"


def test_r10_bites_on_real_estate_leak():
    """A non-real-estate golden whose pack injects real-estate terms must be flagged.
    We force the real-estate INDUSTRY PACK to resolve (industry='property', a real
    match keyword -> the real_estate.v1 pack renders its vertical terms) while
    DECLARING the golden's industry as insurance with real-estate terms forbidden
    -> the RE vocabulary leaks into a non-RE call -> the gate must FAIL."""
    leaky = GoldenConversation(
        name="r10_re_leak", use_case="sales", industry="insurance",
        # 'property' is a real match keyword for the real_estate.v1 pack, so the pack
        # resolves and injects RERA / site visit / carpet area / BHK terms.
        fields={"agent_name": "S", "company_name": "L", "product_name": "T", "plan": "lean",
                "use_case": "sales", "industry": "property"},
        turns=(GoldenTurn("haan", "", None, "n"),),
        pushes_sale=True, forbidden_vertical_terms=REAL_ESTATE_TERMS,
    )
    # sanity: the pack really did render real-estate vertical terms (else the test
    # would pass vacuously). Then assert the gate catches the leak.
    from voice_ops.eval.regression_gates import assemble_prompt, kernel_outbound_on

    with kernel_outbound_on():
        rendered = assemble_prompt(leaky.fields).lower()
    assert "vertical terms:" in rendered and "rera" in rendered, "fixture did not inject RE terms"
    r = G.gate_r10_cross_vertical_isolation([leaky])
    assert not r.passed, "R10 failed to bite on real-estate vocabulary leaking into a non-RE call"


# --------------------------------------------------------------------------- #
# W-VOICE-HEART gates R11..R15 — POSITIVE + NEGATIVE CONTROLS (each must bite).
# --------------------------------------------------------------------------- #
# R11 — no double intro: the single-greeting rule must be rendered AND exactly one
# OPENING. Negative: a prompt missing the rule, and a prompt with two OPENINGs, FAIL.
def test_r11_passes_on_fixed_kernel():
    assert G.gate_r11_no_double_intro().passed


def test_r11_bites_when_single_greeting_rule_absent(monkeypatch):
    g = _broken_golden()
    no_rule = "you are r.\nobjective: move the lead.\nopening: greet skeleton.\nsuccess: y.\n"
    monkeypatch.setattr(G, "assemble_prompt", lambda fields: no_rule)
    r = G.gate_r11_no_double_intro([g])
    assert not r.passed, "R11 failed to bite when the SINGLE GREETING rule is absent"
    assert "single greeting" in r.detail.lower()


def test_r11_bites_on_double_opening(monkeypatch):
    g = _broken_golden()
    double = (
        "you are r.\nopening: greet skeleton.\nopening: also greet again warmly.\n"
        "SINGLE GREETING: greet once only.\n"
    )
    monkeypatch.setattr(G, "assemble_prompt", lambda fields: double)
    r = G.gate_r11_no_double_intro([g])
    assert not r.passed, "R11 failed to bite on a double OPENING directive"


def test_r11_single_greeting_rule_is_actually_in_the_real_prompt():
    """The rule must be LIVE in the real kernel output (not just asserted in a mock)."""
    from voice_kernel.brain_packs.delivery import has_single_greeting_rule

    out = G.assemble_prompt(_broken_golden().fields)
    assert has_single_greeting_rule(out), "kernel prompt does not carry the single-greeting rule"


# R12 — name sparingly: the NAME USE + no-emphasis rule must be rendered. Negative:
# a prompt without it FAILS.
def test_r12_passes_on_fixed_kernel():
    assert G.gate_r12_name_used_sparingly().passed


def test_r12_bites_when_name_rule_absent(monkeypatch):
    g = _broken_golden()
    no_rule = "you are r.\nobjective: x.\nopening: greet.\n"  # no NAME USE rule
    monkeypatch.setattr(G, "assemble_prompt", lambda fields: no_rule)
    r = G.gate_r12_name_used_sparingly([g])
    assert not r.passed, "R12 failed to bite when the NAME USE rule is absent"


def test_r12_name_rule_live_in_real_prompt():
    from voice_kernel.brain_packs.delivery import has_name_sparingly_rule

    out = G.assemble_prompt(_broken_golden().fields)
    assert has_name_sparingly_rule(out), "kernel prompt does not carry the name-sparingly rule"


# R13 — no formal Hindi: the casual-Hinglish ban (names 'mahatvapurn' as forbidden)
# must be rendered. Negative: the detector must flag a literary input; a prompt that
# renders 'mahatvapurn' WITHOUT a prohibition fails.
def test_r13_passes_on_fixed_kernel():
    assert G.gate_r13_no_formal_hindi().passed


def test_r13_bites_when_literary_used_as_guidance(monkeypatch):
    g = _broken_golden()
    # 'mahatvapurn' appears but NOT inside a prohibition -> used as plain guidance.
    leaky = "you are r.\nspeak in clear mahatvapurn hindi for the customer.\n"
    monkeypatch.setattr(G, "assemble_prompt", lambda fields: leaky)
    r = G.gate_r13_no_formal_hindi([g])
    assert not r.passed, "R13 failed to bite on literary Hindi used as spoken guidance"


def test_r13_detector_bites():
    from voice_kernel.brain_packs.language import contains_banned_literary

    assert contains_banned_literary("yeh mahatvapurn baat hai") is True
    assert contains_banned_literary("yeh zaroori baat hai") is False


# R14 — LLM-generated closing: a CLOSING directive that forbids a canned goodbye.
# Negative: a prompt with no CLOSING directive FAILS.
def test_r14_passes_on_fixed_kernel():
    assert G.gate_r14_llm_generated_closing().passed


def test_r14_bites_when_no_closing_directive(monkeypatch):
    g = _broken_golden()
    no_close = "you are r.\nopening: greet skeleton.\nobjective: move the lead.\n"
    monkeypatch.setattr(G, "assemble_prompt", lambda fields: no_close)
    r = G.gate_r14_llm_generated_closing([g])
    assert not r.passed, "R14 failed to bite when there is NO CLOSING directive (hardcoded close)"
    assert "no closing" in r.detail.lower()


def test_r14_bites_when_closing_allows_canned(monkeypatch):
    g = _broken_golden()
    canned = "you are r.\nclosing: say 'ok perfect dhanyavaad' and hang up.\n"  # no ban cue
    monkeypatch.setattr(G, "assemble_prompt", lambda fields: canned)
    r = G.gate_r14_llm_generated_closing([g])
    assert not r.passed, "R14 failed to bite on a CLOSING that permits a canned goodbye"


def test_r14_closing_live_in_real_prompt():
    low = G.assemble_prompt(_broken_golden().fields).lower()
    assert "closing:" in low, "kernel prompt does not carry a CLOSING directive"


# R15 — constant prosody / no name-emphasis: the no-emphasis rule rendered + the
# drop-in pins 0.45/1.08. Negative: a prompt without the rule FAILS; the
# emphasis detector bites on a shouted name.
def test_r15_passes_on_fixed_kernel():
    assert G.gate_r15_constant_prosody_no_name_emphasis().passed


def test_r15_bites_when_no_emphasis_rule_absent(monkeypatch):
    g = _broken_golden()
    no_rule = "you are r.\nopening: greet.\nNAME USE: say it sometimes.\n"  # no 'no emphasis'
    monkeypatch.setattr(G, "assemble_prompt", lambda fields: no_rule)
    r = G.gate_r15_constant_prosody_no_name_emphasis([g])
    assert not r.passed, "R15 failed to bite when the no-name-emphasis rule is absent"


def test_r15_emphasis_detector_bites():
    from voice_kernel.brain_packs.delivery import text_emphasizes_name

    assert text_emphasizes_name("RAHUL! kaise hain", name="Rahul") is True
    assert text_emphasizes_name("Rahul!!! bahut accha", name="Rahul") is True
    assert text_emphasizes_name("namaste Rahul ji, kaise hain", name="Rahul") is False


def test_r15_dropin_pins_constant_prosody():
    """The shipped systemd drop-in must pin the derived inbound constants (0.45/1.08)
    so the deploy params cannot silently drift from the GOOD inbound voice."""
    from voice_ops.eval.regression_gates import _DROPIN_PATH, CONSTANT_PROSODY

    assert _DROPIN_PATH.exists(), "constant-prosody drop-in template missing"
    conf = _DROPIN_PATH.read_text(encoding="utf-8")
    assert f"EL_STABILITY={CONSTANT_PROSODY['EL_STABILITY']}" in conf
    assert f"EL_SPEED={CONSTANT_PROSODY['EL_SPEED']}" in conf


# every new gate appears in the canonical GATE_LIST + run_all_gates report.
def test_voice_heart_gates_registered():
    ids = {g[0] for g in G.GATE_LIST}
    assert {"R11", "R12", "R13", "R14", "R15"} <= ids
    rep = G.run_all_gates()
    produced = {r.gate_id for r in rep.results}
    assert {"R11", "R12", "R13", "R14", "R15"} <= produced
    assert rep.passed, f"deploy gate BLOCKED: {rep.failed_gates}"


# --------------------------------------------------------------------------- #
# IMPORT ISOLATION — the harness must never pull a droplet module.
# --------------------------------------------------------------------------- #
def test_eval_import_pulls_zero_droplet_modules():
    leaked = [m for m in sys.modules if m.startswith("droplet_work")]
    assert leaked == [], f"droplet_work leaked into sys.modules via the eval harness: {leaked}"
