"""Offline tests for grow.budget (Budget Governor). No network. Run:
    cd droplet_work && python -m grow.tests.test_budget
"""
from __future__ import annotations

from grow.budget import BudgetGovernor, BudgetTree


def test_admit_within_caps():
    g = BudgetGovernor(BudgetTree(daily_cap_minor=500000))
    v = g.admit_spend(spent_today_minor=100000, proposed_minor=50000)
    assert v.allow is True and v.reason == "within_caps"
    assert v.headroom_minor == 350000 and v.stamp.startswith("gov:ok")


def test_admit_blocks_daily_cap():
    g = BudgetGovernor(BudgetTree(daily_cap_minor=500000))
    v = g.admit_spend(spent_today_minor=480000, proposed_minor=50000)
    assert v.allow is False and v.reason == "daily_cap_exceeded"
    assert v.headroom_minor == 20000


def test_admit_blocks_monthly_cap():
    g = BudgetGovernor(BudgetTree(workspace_monthly_minor=1000000, daily_cap_minor=500000))
    v = g.admit_spend(spent_today_minor=0, proposed_minor=50000, spent_month_minor=990000)
    assert v.allow is False and v.reason == "monthly_cap_exceeded"


def test_runaway_detection():
    g = BudgetGovernor(BudgetTree(daily_cap_minor=300000, adsets=3))  # per-adset 100000
    assert g.is_runaway(spent_today_minor=350000) is True   # > 3x 100000
    assert g.is_runaway(spent_today_minor=250000) is False


def test_anomaly_velocity_red():
    g = BudgetGovernor()
    v = g.detect_anomaly(spend_velocity=4000, velocity_norm=1000)
    assert v.anomaly is True and v.severity == "red"
    assert any("velocity" in r for r in v.reasons)


def test_anomaly_none():
    g = BudgetGovernor()
    v = g.detect_anomaly(spend_velocity=1500, velocity_norm=1000, cpm=100, cpm_norm=90)
    assert v.anomaly is False and v.severity == "none"


def test_anomaly_emq_collapse():
    g = BudgetGovernor()
    v = g.detect_anomaly(spend_velocity=0, velocity_norm=0, emq_collapsed=True)
    assert v.anomaly is True


def test_month_forecast_over_cap():
    g = BudgetGovernor(BudgetTree(workspace_monthly_minor=1000000))
    f = g.month_forecast(spent_month_minor=600000, day_of_month=10, days_in_month=30)
    assert f["projected_minor"] == 1800000 and f["over_cap"] is True
    assert 0 < f["suggested_throttle"] < 1


def test_month_forecast_under_cap():
    g = BudgetGovernor(BudgetTree(workspace_monthly_minor=1000000))
    f = g.month_forecast(spent_month_minor=100000, day_of_month=10, days_in_month=30)
    assert f["over_cap"] is False and f["suggested_throttle"] == 1.0


def test_kill_switch():
    k = BudgetGovernor().kill_switch("spike")
    assert k["action"] == "pause_all" and k["reversible"] is True


def test_unbounded_when_no_caps():
    v = BudgetGovernor().admit_spend(spent_today_minor=999999999, proposed_minor=999999999)
    assert v.allow is True  # no caps configured => unbounded (caller sets caps)


def _run():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"PASS grow.tests.test_budget ({len(fns)} tests)")


if __name__ == "__main__":
    _run()
