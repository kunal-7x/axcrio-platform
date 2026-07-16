"""Offline tests for grow.signals (L7 CAPI Signal Loop) + grow.loop. Shadow-only; no
network, no creds. Run:  cd droplet_work && python -m grow.tests.test_signals
"""
from __future__ import annotations

from grow.config import GrowConfig
from grow.loop import GrowLoop
from grow.model import (Journey, Ladder, ScoredLead, SignalStatus, capi_hash,
                        normalize_phone)
from grow.scoring import LeadScorer
from grow.signals import SignalDispatcher
from grow.store import SignalStore

CFG = GrowConfig()  # shadow_mode=True by default => never POSTs


def _journey():
    return Journey(tenant_id="t1", journey_id="j_abc", phone_masked="••••• 3210",
                   source_platform="meta", ctwa_clid="ctwa_xyz")


def _hot():
    return ScoredLead(tenant_id="t1", lead_id="l1", journey_id="j_abc", score=82, tier="hot")


def test_event_id_is_deterministic_and_per_step():
    d = SignalDispatcher(CFG, SignalStore())
    j = _journey()
    e1 = d.emit(j, _hot(), Ladder.LEAD, raw_phone="+919876543210")
    e2 = d.emit(j, _hot(), Ladder.QUALIFIED, raw_phone="+919876543210")
    assert e1.event_id == capi_hash("j_abc|Lead")
    assert e2.event_id == capi_hash("j_abc|QualifiedLead")
    assert e1.event_id != e2.event_id


def test_shadow_mode_never_marks_live():
    d = SignalDispatcher(CFG, SignalStore())
    e = d.emit(_journey(), _hot(), Ladder.LEAD, raw_phone="+919876543210")
    assert e.status == SignalStatus.SHADOW
    assert e.reason in ("shadow_mode", "meta_creds_absent")


def test_value_is_lead_score_on_lead():
    d = SignalDispatcher(CFG, SignalStore())
    e = d.emit(_journey(), _hot(), Ladder.LEAD, raw_phone="+919876543210")
    assert e.value == 82


def test_purchase_value_overrides_score():
    d = SignalDispatcher(CFG, SignalStore())
    e = d.emit(_journey(), _hot(), Ladder.PURCHASE, value=5500000, raw_phone="+919876543210")
    assert e.value == 5500000


def test_match_keys_are_types_not_raw_pii():
    d = SignalDispatcher(CFG, SignalStore())
    e = d.emit(_journey(), _hot(), Ladder.LEAD, raw_phone="+919876543210",
               raw_email="buyer@example.com", raw_name="Asha Verma")
    # the ledger row holds key TYPES only — never the raw or even hashed phone value
    assert "ph" in e.match_keys and "em" in e.match_keys and "ctwa_clid" in e.match_keys
    blob = repr(e.public())
    assert "9876543210" not in blob and "919876543210" not in blob
    assert "buyer@example.com" not in blob


def test_dedup_idempotent_resend():
    store = SignalStore()
    d = SignalDispatcher(CFG, store)
    j = _journey()
    first = d.emit(j, _hot(), Ladder.LEAD, raw_phone="+919876543210")
    second = d.emit(j, _hot(), Ladder.LEAD, raw_phone="+919876543210")
    assert first.status == SignalStatus.SHADOW
    assert second.status == SignalStatus.DEDUPED
    # only one unique row persisted
    rows = store.list("t1")
    assert len([r for r in rows if r.event_name == "Lead"]) == 1


def test_emq_estimate_rewards_strong_keys():
    d = SignalDispatcher(CFG, SignalStore())
    weak = d.emit(Journey(tenant_id="t1", journey_id="j_weak"), _hot(), Ladder.LEAD)
    strong = d.emit(_journey(), _hot(), Ladder.LEAD, raw_phone="+919876543210",
                    raw_email="b@x.com")
    assert strong.emq_estimate > weak.emq_estimate


def test_qualified_gate():
    d = SignalDispatcher(CFG, SignalStore())
    assert d.should_emit_qualified(_hot()) is True
    cold = ScoredLead(tenant_id="t1", lead_id="lc", score=30, tier="junk")
    assert d.should_emit_qualified(cold) is False


def test_signal_health_card():
    store = SignalStore()
    d = SignalDispatcher(CFG, store)
    d.emit(_journey(), _hot(), Ladder.LEAD, raw_phone="+919876543210")
    d.emit(_journey(), _hot(), Ladder.QUALIFIED, raw_phone="+919876543210")
    h = d.health("t1")
    assert h["total"] == 2
    assert h["mode"] == "shadow"
    assert h["ladder_coverage"].get("Lead") == 1
    assert 0.0 <= h["click_id_coverage"] <= 1.0


# ---- loop end-to-end (shadow) ----
def test_loop_on_call_outcome_scores_and_signals():
    loop = GrowLoop(config=CFG)  # fresh InMemory stores
    out = loop.on_call_outcome(
        "t1", "lead-100", phone="+919876543210", name="Asha", source_platform="meta",
        ctwa_clid="ctwa_1", call_answered=True, call_duration_s=190, budget_mentioned=True,
        timeline_mentioned=True, decision_authority=True, site_visit_ready=True,
        interest_score=85)
    assert out["ok"] is True
    assert out["scored"]["tier"] == "hot"
    # both Lead and QualifiedLead fired (hot)
    names = [s["event_name"] for s in out["signals"]]
    assert "Lead" in names and "QualifiedLead" in names
    # persisted + journey threaded
    assert loop.scores.get("t1", "lead-100") is not None
    j = loop.journeys.get("t1", out["journey_id"])
    assert j is not None and j.status == "qualified"


def test_loop_journey_id_is_stable():
    loop = GrowLoop(config=CFG)
    a = loop.journey_id_for("t1", "lead-x")
    b = loop.journey_id_for("t1", "lead-x")
    assert a == b and a.startswith("j_")


def test_loop_swallows_bad_input():
    loop = GrowLoop(config=CFG)
    out = loop.on_call_outcome("", "")  # missing tenant/lead
    assert out["ok"] is False


def test_normalize_phone_india():
    assert normalize_phone("9876543210") == "919876543210"
    assert normalize_phone("+91 98765-43210") == "919876543210"
    assert normalize_phone("0919876543210") == "919876543210"


def _run():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"PASS grow.tests.test_signals ({len(fns)} tests)")


if __name__ == "__main__":
    _run()
