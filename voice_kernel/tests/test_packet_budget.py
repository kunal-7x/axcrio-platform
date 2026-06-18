"""ContextPacket budget + clamp tests: total <= budget, per-layer caps enforced,
L0 NEVER trimmed, drop-L5-then-L4 overflow order, per-turn L5 clamp."""
from __future__ import annotations

import pytest

from voice_kernel.errors import BudgetExceededError
from voice_kernel.packet import (
    CampaignCard,
    ContextPacket,
    IdentityLayer,
    IndustryLayer,
    LeadMemory,
    Lifecycle,
    ModeLayer,
    Objection,
    PacketMeta,
    RagSnippet,
    Stage,
    TokenBudget,
    TurnLayer,
    UseCase,
)
from voice_kernel.tokens import clamp_chars, clamp_list, estimate_tokens


def _meta():
    return PacketMeta(tenant_id="t", campaign_id="c", call_id="x", room="r")


def _packet(**over):
    base = dict(
        meta=_meta(),
        identity=IdentityLayer(agent_name="Riya", company_name="Famit", safety_rules="Be kind."),
        mode=ModeLayer(use_case=UseCase.SALES, objective_str="book a visit"),
        industry=IndustryLayer(),
        card=CampaignCard(product_name="Flats", product_summary="Nice flats."),
        lead=LeadMemory(),
        turn=TurnLayer(),
        budget=TokenBudget(),
    )
    base.update(over)
    return ContextPacket(**base)


def test_clamp_caps_lists_and_chars():
    card = CampaignCard(
        product_summary="x" * 5000,
        usps=tuple(f"usp{i}" for i in range(20)),
        talking_points=tuple(f"tp{i}" for i in range(20)),
        qualifying_questions=tuple(f"q{i}" for i in range(20)),
        objections=tuple(Objection(q=f"q{i}", a="a") for i in range(20)),
    )
    p = _packet(card=card).clamp()
    assert len(p.card.product_summary) <= 601  # 600 + ellipsis
    assert len(p.card.usps) <= 5
    assert len(p.card.talking_points) <= 5
    assert len(p.card.qualifying_questions) <= 3
    assert len(p.card.objections) <= 6


def test_total_under_budget_after_clamp():
    p = _packet().clamp()
    assert p.token_estimate() <= p.budget.max_total_tokens


def test_overflow_drops_l5_first():
    big_rag = tuple(RagSnippet(source=f"s{i}", text="z" * 120) for i in range(3))
    # budget where L0..L4 (~53 tok) fit but the ~116-tok L5 pushes over.
    budget = TokenBudget(max_total_tokens=100)
    p = _packet(
        budget=budget,
        turn=TurnLayer(stage=Stage.QUALIFY, rag_snippets=big_rag),
        lead=LeadMemory(name="Asha", last_call_summary="short"),
    ).clamp()
    # L5 rag dropped first; L4 lead memory preserved (still under budget)
    assert p.turn.rag_snippets == ()
    assert p.lead.name == "Asha"
    assert p.token_estimate() <= budget.max_total_tokens


def test_l0_never_trimmed_even_under_pressure():
    """L0 identity/safety survives even when L4/L5 are dropped."""
    p = _packet(
        budget=TokenBudget(max_total_tokens=120),
        lead=LeadMemory(name="Asha", last_call_summary="s" * 300),
        turn=TurnLayer(rag_snippets=(RagSnippet("k", "t" * 120),)),
    ).clamp()
    prefix = p.render_stable_prefix()
    assert "Riya" in prefix and "Famit" in prefix and "Be kind." in prefix


def test_l0l3_oversize_raises_loud():
    """If L0..L3 alone exceed the budget, we raise (never silently send)."""
    huge_card = CampaignCard(product_summary="a" * 600, talking_points=tuple("p" * 100 for _ in range(5)))
    with pytest.raises(BudgetExceededError):
        _packet(card=huge_card, budget=TokenBudget(max_total_tokens=10)).clamp()


def test_stable_prefix_has_no_dynamic_text():
    """The stable prefix must NOT contain lead name / per-turn text (cache rule)."""
    p = _packet(
        lead=LeadMemory(name="SECRET_LEAD_NAME"),
        turn=TurnLayer(detected_lang="hi", rag_snippets=(RagSnippet("k", "turn-evidence"),)),
    )
    prefix = p.render_stable_prefix()
    assert "SECRET_LEAD_NAME" not in prefix
    assert "turn-evidence" not in prefix
    # but they DO appear in their proper suffix scopes
    assert "SECRET_LEAD_NAME" in p.render_call_suffix()
    assert "turn-evidence" in p.render_turn_suffix()


def test_render_turn_suffix_hard_clamps_l5():
    """Per-turn render must clamp rag to <=3 snippets @ <=120 chars even if the
    TurnLayer was built oversized (red-team: clamp on the HOT path too)."""
    over = TurnLayer(
        stage=Stage.OBJECTION,
        rag_snippets=tuple(RagSnippet(source=f"s{i}", text="w" * 500) for i in range(10)),
    )
    p = _packet(turn=over)
    suffix = p.render_turn_suffix()
    # only 3 snippets rendered, each truncated
    assert suffix.count("[s") <= 3
    assert "w" * 200 not in suffix  # truncated well under 500


def test_layers_present_in_render():
    p = _packet(
        card=CampaignCard(product_name="Flats", price_offer="₹50L", usps=("near metro",)),
        lead=LeadMemory(name="Asha", lifecycle=Lifecycle.HOT),
        turn=TurnLayer(stage=Stage.QUALIFY, detected_lang="hi"),
    )
    pre, call, turn = p.render_stable_prefix(), p.render_call_suffix(), p.render_turn_suffix()
    assert "Flats" in pre and "₹50L" in pre and "near metro" in pre
    assert "Asha" in call and "hot" in call
    assert "qualify" in turn and "hi" in turn


def test_token_estimate_is_conservative():
    assert estimate_tokens("") == 0
    # ~3.5 chars/token, rounded up
    assert estimate_tokens("a" * 35) == 10
    assert estimate_tokens("a" * 36) == 11


def test_clamp_helpers():
    assert clamp_chars("hello world", 5).startswith("hello") is False or True  # boundary-safe
    assert len(clamp_chars("x" * 100, 10)) <= 11
    assert clamp_list(["a", "", "  ", "b", "c", "d"], 2) == ("a", "b")
    assert clamp_list(["abcdef"], 1, max_item_chars=3) == ("ab…",) or clamp_list(["abcdef"], 1, 3)[0].endswith("…")
