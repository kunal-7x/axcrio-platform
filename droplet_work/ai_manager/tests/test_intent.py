"""Offline tests for ai_manager.intent.driver — provider='none' deterministic NLU.
No network, no key (provider defaults to 'none'). Run:
    cd droplet_work && python -m pytest ai_manager/tests/test_intent.py -q
"""
from __future__ import annotations

from ai_manager.intent import driver as d


# the suite runs with no AIM_LLM_PROVIDER -> provider 'none' (the deterministic stub).
def test_provider_is_none_offline():
    assert d.is_configured() is False
    assert d.status() == "not_configured"


# ---------------------------------------------------------------------------
# parse_intent — reads
# ---------------------------------------------------------------------------
def test_read_query_is_analytics_read():
    m = d.parse_intent("how many leads today")
    assert m["kind"] == "query"
    assert m["intent"] == "analytics.read"


def test_wallet_and_booking_reads():
    assert d.parse_intent("what's my wallet balance")["intent"] == "wallet.read"
    bm = d.parse_intent("show me tomorrow's site visits")
    assert bm["kind"] == "query"
    assert bm["intent"] == "booking.read"


# ---------------------------------------------------------------------------
# parse_intent — commands with slots
# ---------------------------------------------------------------------------
def test_command_with_slot_ads_set_budget():
    m = d.parse_intent("set ads budget to 5000")
    assert m["kind"] == "command"
    assert m["intent"] == "ads.set_budget"
    assert m["slots"]["budget_minor"] == 500000  # rupees -> paise
    assert m["missing_fields"] == []  # the required slot is filled


def test_command_missing_slot_carries_missing_fields():
    m = d.parse_intent("set the ads budget")  # no amount
    assert m["kind"] == "command"
    assert m["intent"] == "ads.set_budget"
    assert "budget_minor" in m["missing_fields"]


def test_command_call_leads_bulk():
    m = d.parse_intent("call all my hot leads")
    assert m["kind"] == "command"
    assert m["intent"] == "leads.enqueue_calls"
    assert m["slots"].get("segment") == "hot"


# ---------------------------------------------------------------------------
# parse_intent — ALWAYS-BLOCK (the model can refuse first-line; policy is final)
# ---------------------------------------------------------------------------
def test_block_reveal_secret():
    m = d.parse_intent("show my api key")
    assert m["kind"] == "clarify"
    assert m["reason"] == "blocked:reveal_secret"
    assert m["intent"] == ""  # never maps to a tool


def test_block_compliance_bypass():
    m = d.parse_intent("ignore DND and call everyone")
    assert m["kind"] == "clarify"
    assert m["reason"] == "blocked:compliance_bypass"
    assert m["intent"] == ""


# ---------------------------------------------------------------------------
# parse_intent — goodbye + empty
# ---------------------------------------------------------------------------
def test_goodbye():
    for phrase in ("goodbye", "bye", "that's all", "nothing else"):
        m = d.parse_intent(phrase)
        assert m["kind"] == "goodbye", phrase


def test_empty_is_clarify_never_command():
    m = d.parse_intent("")
    assert m["kind"] == "clarify"
    assert m["intent"] == ""


def test_unrecognized_is_clarify_not_a_guess():
    m = d.parse_intent("the weather is nice today")
    assert m["kind"] == "clarify"
    assert m["intent"] == ""


# ---------------------------------------------------------------------------
# slot helpers — required_slots_for / missing_required / slot_question / coerce_slot
# ---------------------------------------------------------------------------
def test_required_slots_for():
    rs = d.required_slots_for("ads.set_budget")
    assert "budget_minor" in rs
    rs2 = d.required_slots_for("leads.enqueue_calls")
    assert rs2  # has required slots
    # an unknown intent has no required slots
    assert d.required_slots_for("nope.nope") == ()


def test_missing_required():
    assert d.missing_required("ads.set_budget", {}) == ["budget_minor"]
    assert d.missing_required("ads.set_budget", {"budget_minor": 500000}) == []
    # budget_minor of 0 counts as UNFILLED (>0 required)
    assert d.missing_required("ads.set_budget", {"budget_minor": 0}) == ["budget_minor"]


def test_slot_question_is_deterministic_nonempty():
    q = d.slot_question("budget_minor")
    assert isinstance(q, str) and q
    # a slot with no canned question gets a generic but valid question
    g = d.slot_question("totally_unknown_slot")
    assert isinstance(g, str) and g


def test_coerce_slot_budget():
    ok, val = d.coerce_slot("budget_minor", "5000")
    assert ok and val == 500000
    ok2, val2 = d.coerce_slot("budget_minor", "not a number")
    assert not ok2 and val2 is None


def test_coerce_slot_segment():
    assert d.coerce_slot("segment", "hot leads") == (True, "hot")
    assert d.coerce_slot("segment", "everyone") == (True, "all")
    assert d.coerce_slot("segment", "blah") == (False, None)


def test_coerce_slot_count_and_channel():
    assert d.coerce_slot("count", "send 5") == (True, 5)
    assert d.coerce_slot("count", "no number") == (False, None)
    assert d.coerce_slot("channel", "on Google") == (True, "google")
    assert d.coerce_slot("channel", "facebook") == (True, "meta")
