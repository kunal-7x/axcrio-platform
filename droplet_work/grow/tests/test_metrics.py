"""Offline tests for grow.metrics (L8 funnel + ROI). No network. Run:
    cd droplet_work && python -m grow.tests.test_metrics
"""
from __future__ import annotations

from grow.config import GrowConfig
from grow.loop import GrowLoop
from grow.model import ChannelResult, ChannelStatus

CFG = GrowConfig()


def _fire(_c, _j):
    return ChannelResult("whatsapp", ChannelStatus.FIRED, ref="x")


def _seed():
    """3 captured leads (channels fired); 2 scored HOT (qualified), 1 JUNK."""
    loop = GrowLoop(config=CFG, whatsapp_sender=_fire, voice_caller=_fire)
    ids = ["919800000001", "919800000002", "919800000003"]
    srcs = ["meta", "google", "meta"]
    for lid, src in zip(ids, srcs):
        loop.on_lead_captured("t1", lid, phone="+" + lid, source_platform=src)
    # qualify the first two (HOT), trash the third (junk)
    hot = dict(call_answered=True, call_duration_s=190, budget_mentioned=True,
               timeline_mentioned=True, decision_authority=True, site_visit_ready=True,
               interest_score=85)
    loop.on_call_outcome("t1", ids[0], phone="+" + ids[0], source_platform="meta", **hot)
    loop.on_call_outcome("t1", ids[1], phone="+" + ids[1], source_platform="google", **hot)
    loop.on_call_outcome("t1", ids[2], phone="+" + ids[2], source_platform="meta",
                         call_answered=False, last_outcome="not_interested")
    return loop


def test_funnel_counts():
    m = _seed().metrics
    f = m.funnel("t1")
    assert f["captured"] == 3
    assert f["qualified"] == 2
    by_key = {s["key"]: s["count"] for s in f["stages"]}
    assert by_key["captured"] == 3
    assert by_key["contacted"] == 3        # all fired a channel
    assert by_key["scored"] == 3
    assert by_key["qualified"] == 2
    assert by_key["signal_qualified"] == 2 # QualifiedLead fired for the 2 hot
    assert by_key["booked"] == 0


def test_funnel_drop_off_ratios():
    f = _seed().metrics.funnel("t1")
    qualified = [s for s in f["stages"] if s["key"] == "qualified"][0]
    assert qualified["of_captured"] == 0.6667  # 2/3


def test_tier_distribution():
    d = _seed().metrics.tier_distribution("t1")
    assert d["hot"] == 2 and d["junk"] == 1


def test_by_source():
    bs = _seed().metrics.by_source("t1")
    assert bs["meta"]["leads"] == 2 and bs["meta"]["qualified"] == 1
    assert bs["google"]["leads"] == 1 and bs["google"]["qualified"] == 1


def test_sla():
    s = _seed().metrics.sla("t1")
    assert s["fired"] == 3 and s["sla_met"] == 3 and s["sla_met_rate"] == 1.0
    assert s["avg_latency_ms"] >= 0


def test_roi_with_spend():
    r = _seed().metrics.roi("t1", spend_minor=120000)  # ₹1,200
    assert r["spend_connected"] is True
    assert r["leads"] == 3 and r["qualified"] == 2
    assert r["cpl_minor"] == 40000          # 120000/3
    assert r["cpql_minor"] == 60000         # 120000/2  (north star)
    assert r["north_star"] == "cpql_minor"


def test_roi_without_spend_is_not_connected():
    r = _seed().metrics.roi("t1", spend_minor=0)
    assert r["spend_connected"] is False
    assert r["cpql_minor"] == 0 and r["qualified"] == 2


def test_summary_has_all_sections():
    s = _seed().metrics.summary("t1", spend_minor=120000)
    for k in ("funnel", "tier_distribution", "by_source", "sla", "roi", "signal_health"):
        assert k in s


def test_empty_tenant_is_zeros():
    m = GrowLoop(config=CFG).metrics
    f = m.funnel("t-empty")
    assert f["captured"] == 0 and f["qualified"] == 0
    r = m.roi("t-empty", spend_minor=5000)
    assert r["cpql_minor"] == 0  # no qualified -> no divide-by-zero


def _run():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"PASS grow.tests.test_metrics ({len(fns)} tests)")


if __name__ == "__main__":
    _run()
