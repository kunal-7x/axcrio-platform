"""Offline tests for grow.optimizer (Draft/Trash/Promote brain). No network/RNG. Run:
    cd droplet_work && python -m grow.tests.test_optimizer
"""
from __future__ import annotations

from grow.optimizer import Arm, Optimizer

OPT = Optimizer()
TARGET = 70000  # ₹700 target CPqL (minor units)


def test_g6_policy_quarantine_first():
    d = OPT.evaluate(Arm("a", spend_minor=999999, qualified_leads=0, delivery_error=True), TARGET)
    assert d.rule == "G6" and d.decision == "quarantine"


def test_g1_runaway():
    d = OPT.evaluate(Arm("a", spend_minor=40000), TARGET, daily_share_minor=10000)
    assert d.rule == "G1" and d.decision == "pause_now"
    assert d.explanation.confidence == "high"


def test_g2_zero_qualified_trash():
    # spend 2.5x+ target, 0 qualified
    d = OPT.evaluate(Arm("a", name="Diwali-Static-2", spend_minor=200000, qualified_leads=0,
                         leads=11), TARGET)
    assert d.rule == "G2" and d.decision == "trash"
    assert "0 qualified" in d.explanation.summary_en


def test_g3_adset_fail_statistical():
    d = OPT.evaluate(Arm("a", spend_minor=600000, qualified_leads=1, leads=2), TARGET)
    assert d.rule == "G3" and d.decision == "pause_adset" and d.scope == "adset"


def test_g4_junk_trap():
    d = OPT.evaluate(Arm("a", spend_minor=50000, qualified_leads=0, leads=10, junk_leads=7), TARGET)
    assert d.rule == "G4" and d.decision == "trash"


def test_g5_fatigue_rotate():
    d = OPT.evaluate(Arm("a", spend_minor=50000, qualified_leads=2, leads=4, days_running=5,
                         frequency_7d=3.0), TARGET)
    assert d.rule == "G5" and d.decision == "rotate"


def test_promote_winner():
    d = OPT.evaluate(Arm("a", name="Question-Hook-Video-1", spend_minor=400000,
                         qualified_leads=10, leads=12, days_running=5, frequency_7d=1.2,
                         ctr_now=0.02, ctr_peak_7d=0.02), TARGET)
    assert d.rule == "promote" and d.decision == "promote"
    assert "+20%" in d.explanation.summary_en


def test_hold_when_thin():
    d = OPT.evaluate(Arm("a", spend_minor=20000, qualified_leads=1, leads=2, days_running=1), TARGET)
    assert d.rule == "hold" and d.decision == "hold"


def test_every_decision_has_explanation():
    d = OPT.evaluate(Arm("a", spend_minor=20000, qualified_leads=1), TARGET)
    e = d.explanation
    assert e and e.summary_en and isinstance(e.evidence, list) and e.reversible is True


def test_p_cpql_exceeds_is_low_for_winner_high_for_loser():
    # a CLEAR winner (₹8000 spend, 20 qualified -> ₹400 CPqL) so the data dominates the
    # ₹2000 cold-start prior; a clear loser (₹6000 spend, 1 qualified).
    winner = Arm("w", spend_minor=800000, qualified_leads=20)
    loser = Arm("l", spend_minor=600000, qualified_leads=1)
    assert OPT.p_cpql_exceeds_target(winner, TARGET) < 0.2
    assert OPT.p_cpql_exceeds_target(loser, TARGET) > 0.85


def test_allocate_favors_winner_and_bounded():
    winner = Arm("w", spend_minor=300000, qualified_leads=12)
    loser = Arm("l", spend_minor=300000, qualified_leads=1)
    alloc = OPT.allocate([winner, loser], TARGET)
    assert alloc["w"] > alloc["l"]
    assert abs(sum(alloc.values()) - 1.0) < 0.001
    assert alloc["l"] >= 0.09  # always exploring (min_explore floor before renorm)


def test_allocate_skips_errored_arms():
    a = Arm("a", spend_minor=100000, qualified_leads=5)
    bad = Arm("b", spend_minor=100000, qualified_leads=5, delivery_error=True)
    alloc = OPT.allocate([a, bad], TARGET)
    assert "b" not in alloc and "a" in alloc


def _run():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"PASS grow.tests.test_optimizer ({len(fns)} tests)")


if __name__ == "__main__":
    _run()
