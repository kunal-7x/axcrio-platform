"""Offline tests for grow.scoring (L5). No network, no creds. Run:
    cd droplet_work && python -m grow.tests.test_scoring
"""
from __future__ import annotations

from grow.config import GrowConfig
from grow.model import LeadTier, ScoringInput
from grow.scoring import LeadScorer

CFG = GrowConfig()  # defaults: hot=70 warm=40 junk=25
SCORER = LeadScorer(CFG)


def test_invalid_phone_is_junk():
    s = SCORER.score(ScoringInput(tenant_id="t1", lead_id="l1", phone_valid=False))
    assert s.tier == LeadTier.JUNK
    assert "invalid_phone" in s.reasons
    assert not s.sales_ready


def test_dnc_outcome_is_junk_even_with_signals():
    s = SCORER.score(ScoringInput(tenant_id="t1", lead_id="l2", call_answered=True,
                                  call_duration_s=200, budget_mentioned=True,
                                  last_outcome="not_interested"))
    assert s.tier == LeadTier.JUNK
    assert any("hard_disqualify" in r for r in s.reasons)


def test_no_engagement_is_junk():
    s = SCORER.score(ScoringInput(tenant_id="t1", lead_id="l3"))
    assert s.score < CFG.junk_threshold
    assert s.tier == LeadTier.JUNK


def test_strong_buyer_is_hot():
    s = SCORER.score(ScoringInput(
        tenant_id="t1", lead_id="l4", phone="+919876543210", call_answered=True,
        call_duration_s=190, budget_mentioned=True, timeline_mentioned=True,
        decision_authority=True, site_visit_ready=True, interest_score=80))
    assert s.score >= CFG.hot_threshold, s.score
    assert s.tier == LeadTier.HOT
    assert s.sales_ready
    assert s.reasons  # has the "why"
    assert s.phone_masked.endswith("3210") and "9876543210" not in s.phone_masked


def test_booking_made_pushes_hot():
    s = SCORER.score(ScoringInput(tenant_id="t1", lead_id="l5", call_answered=True,
                                  call_duration_s=70, booking_made=True, budget_mentioned=True))
    assert s.tier in (LeadTier.HOT, LeadTier.INVESTOR)
    assert s.sales_ready


def test_investor_intent_routes_investor():
    s = SCORER.score(ScoringInput(
        tenant_id="t1", lead_id="l6", phone="+919812345678", call_answered=True,
        call_duration_s=120, budget_mentioned=True, investor_intent=True, interest_score=70))
    assert s.tier == LeadTier.INVESTOR
    assert s.sales_ready  # investors route to sales too


def test_mid_engagement_is_warm():
    s = SCORER.score(ScoringInput(tenant_id="t1", lead_id="l7", call_answered=True,
                                  call_duration_s=65, timeline_mentioned=True,
                                  interest_score=40))
    assert CFG.warm_threshold <= s.score < CFG.hot_threshold, s.score
    assert s.tier in (LeadTier.WARM, LeadTier.END_USER)
    assert not s.sales_ready


def test_end_user_persona_when_warm():
    s = SCORER.score(ScoringInput(tenant_id="t1", lead_id="l8", call_answered=True,
                                  call_duration_s=65, timeline_mentioned=True,
                                  end_user_intent=True, interest_score=40))
    assert s.tier == LeadTier.END_USER


def test_deterministic():
    a = SCORER.score(ScoringInput(tenant_id="t1", lead_id="l9", call_answered=True,
                                  call_duration_s=120, budget_mentioned=True))
    b = SCORER.score(ScoringInput(tenant_id="t1", lead_id="l9", call_answered=True,
                                  call_duration_s=120, budget_mentioned=True))
    assert a.score == b.score and a.tier == b.tier and a.reasons == b.reasons


def test_confidence_grows_with_evidence():
    thin = SCORER.score(ScoringInput(tenant_id="t1", lead_id="lc1", call_answered=True))
    rich = SCORER.score(ScoringInput(tenant_id="t1", lead_id="lc2", call_answered=True,
                                     call_duration_s=190, budget_mentioned=True,
                                     timeline_mentioned=True, decision_authority=True,
                                     site_visit_ready=True))
    assert rich.confidence > thin.confidence


def test_features_stored_with_score():
    s = SCORER.score(ScoringInput(tenant_id="t1", lead_id="lf", call_answered=True,
                                  call_duration_s=120, budget_mentioned=True))
    assert s.features.get("budget") is True
    assert "raw_points" in s.features


def _run():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"PASS grow.tests.test_scoring ({len(fns)} tests)")


if __name__ == "__main__":
    _run()
