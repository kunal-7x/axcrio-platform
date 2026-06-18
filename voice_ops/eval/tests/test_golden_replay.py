"""W17 — golden-conversation REPLAY + cross-vertical no-leak.

Replays every shipped golden conversation turn-by-turn THROUGH THE KERNEL (WARM
prefix once, then HOT on_turn per caller utterance) and asserts the founder's
per-conversation invariants end-to-end: no AI self-label, single greeting, vendor
hook present, brief lossless+fenced, and language adapts to the caller every turn
(never cold-forces English). Also proves the call-replay scaffold can ingest a
recorded transcript shape (transcripts/{room}.json / ai_manager_sessions turns).
"""
from __future__ import annotations

import pytest

from voice_ops.eval.replay import (
    RecordedCall,
    recorded_call_from_golden,
    recorded_call_from_transcript,
    replay_all_goldens,
    replay_conversation,
)
from voice_ops.eval.verticals import all_goldens


@pytest.mark.parametrize("g", all_goldens(), ids=[g.name for g in all_goldens()])
def test_replay_each_golden_passes_all_invariants(g):
    res = replay_conversation(recorded_call_from_golden(g))
    assert res.passed, f"{g.name} replay failed: {res.failures()} | notes={res.notes}"
    # the prompt is a real, non-trivial kernel assembly (not the legacy sentinel).
    assert "__LEGACY_SHOULD_NOT_APPEAR__" not in res.prompt
    assert len(res.prompt) > 200


def test_replay_all_goldens_green():
    results = replay_all_goldens()
    assert results, "no goldens replayed"
    failed = [(r.name, r.failures()) for r in results if not r.passed]
    assert not failed, f"golden replays failed: {failed}"


def test_replay_language_adapts_both_ways():
    """The real-estate sales golden switches Hindi -> English -> (filler keeps prior)
    -> Hindi. Replay must track every switch and NEVER cold-force English."""
    g = next(x for x in all_goldens() if x.name == "real_estate_sales_lean_sarvam")
    res = replay_conversation(recorded_call_from_golden(g))
    langs = [t.reply_lang for t in res.turns]
    assert langs[0] == "hindi"
    assert langs[1] == "english"
    assert langs[2] == "english"  # 1-word "ok" KEEPS prior, not a flip
    assert res.turns[2].lang_switched is False
    assert langs[3] == "hindi"


def test_replay_from_recorded_transcript_shape():
    """The scaffold ingests a stored transcript ([{role,text,lang}]) — the shape
    outbound transcripts and inbound session turns use — extracts the caller turns,
    and replays them through the kernel."""
    transcript = [
        {"role": "agent", "text": "Namaste, Riya from Skyline Realty."},
        {"role": "user", "text": "हाँ बताइए", "lang": "hi-IN", "expect_lang": "hindi"},
        {"role": "agent", "text": "..."},
        {"role": "user", "text": "what is the price", "lang": "", "expect_lang": "english"},
    ]
    fields = {
        "agent_name": "Riya", "company_name": "Skyline Realty", "product_name": "Heights",
        "plan": "lean", "use_case": "sales", "industry": "real_estate",
        "raw_script": "STAGE GREET: say VENDORHOOKWORD_SKY.",
        "product_summary": "BRIEFMARKER_T full brief.",
    }
    call = recorded_call_from_transcript("replay_transcript", fields, transcript)
    assert len(call.turns) == 2  # only the 2 caller turns
    res = replay_conversation(call)
    assert res.passed, f"recorded-transcript replay failed: {res.failures()}"
    assert res.turns[0].reply_lang == "hindi"
    assert res.turns[1].reply_lang == "english"


# --------------------------------------------------------------------------- #
# CROSS-VERTICAL NO-LEAK — the support/insurance/clinic/fintech goldens must not
# carry real-estate vocabulary; the non-selling modes must not push a sale.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "g",
    [x for x in all_goldens() if x.industry != "real_estate"],
    ids=[x.name for x in all_goldens() if x.industry != "real_estate"],
)
def test_no_real_estate_leak_in_non_re_verticals(g):
    from voice_ops.eval.regression_gates import assemble_prompt, kernel_outbound_on
    from voice_ops.eval.verticals import REAL_ESTATE_TERMS

    with kernel_outbound_on():
        out = assemble_prompt(g.fields).lower()
    if "vertical terms:" in out:
        terms_block = out.split("vertical terms:", 1)[1][:400]
        leaked = [t for t in REAL_ESTATE_TERMS if t.lower() in terms_block]
        assert not leaked, f"{g.name} ({g.industry}) leaked real-estate terms: {leaked}"


@pytest.mark.parametrize(
    "g",
    [x for x in all_goldens() if not x.pushes_sale],
    ids=[x.name for x in all_goldens() if not x.pushes_sale],
)
def test_non_selling_modes_do_not_push_sales(g):
    from voice_ops.eval.regression_gates import _SALES_PUSH_CUES, assemble_prompt, kernel_outbound_on

    with kernel_outbound_on():
        out = assemble_prompt(g.fields).lower()
    leaked = [c for c in _SALES_PUSH_CUES if c in out]
    assert not leaked, f"{g.name} ({g.use_case}) is a non-selling mode but pushes a sale: {leaked}"
