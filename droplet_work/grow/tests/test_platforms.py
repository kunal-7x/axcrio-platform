"""Offline tests for grow.platforms (multi-platform aggregator) + grow.advisor.
No network/creds. Run:  cd droplet_work && python -m grow.tests.test_platforms
"""
from __future__ import annotations

from grow import advisor as adv
from grow import platforms as pf
from grow.platforms import AdsAggregator, PlatformMetrics, fetch_platform


def test_platform_metrics_derived():
    m = PlatformMetrics(platform="google", spend_minor=1_000_000, impressions=100_000,
                        clicks=2000, conversions=100)
    assert m.ctr == 0.02                       # 2000/100000
    assert m.cpc_minor == 500                  # 1_000_000/2000
    assert m.cpm_minor == 10000                # 1_000_000/100000*1000
    assert m.cpi_minor == 10000                # 1_000_000/100
    assert m.cvr == 0.05                       # 100/2000


def test_fetch_no_creds_when_no_demo_no_fetcher():
    pf.clear_fetchers()
    m = fetch_platform("t1", "google", demo=False)
    assert m.status == "no_creds"


def test_fetch_demo_is_populated_and_deterministic():
    pf.clear_fetchers()
    a = fetch_platform("t1", "facebook", demo=True)
    b = fetch_platform("t1", "facebook", demo=True)
    assert a.status == "demo" and a.spend_minor > 0 and a.impressions > 0
    assert a.spend_minor == b.spend_minor and a.conversions == b.conversions  # deterministic
    assert a.by_location and a.by_device and a.top_ads


def test_unknown_platform_is_error():
    assert fetch_platform("t1", "myspace", demo=True).status == "error"


def test_registered_fetcher_is_live():
    pf.clear_fetchers()
    pf.register_platform_fetcher("google", lambda tid, p, period: PlatformMetrics(
        platform="google", spend_minor=500000, impressions=50000, clicks=1000, conversions=40))
    m = fetch_platform("t1", "google")
    assert m.status == "live" and m.spend_minor == 500000
    pf.clear_fetchers()


def test_aggregator_snapshot_demo():
    pf.clear_fetchers()
    snap = AdsAggregator().snapshot("t1", demo=True)
    assert len(snap["platforms"]) == len(pf.PLATFORMS)
    s = snap["summary"]
    assert s["active_platforms"] == len(pf.PLATFORMS)   # all demo-populated
    assert s["total_spend_minor"] > 0 and s["total_conversions"] > 0
    assert s["cheapest_cpi"] and "platform" in s["cheapest_cpi"]
    assert s["best_ctr"] and s["top_spender"]
    assert isinstance(s["same_type_ads"], list) and len(s["same_type_ads"]) >= 1  # shared concepts


def test_snapshot_empty_without_demo():
    pf.clear_fetchers()
    snap = pf.snapshot("t1", demo=False)
    assert snap["summary"]["active_platforms"] == 0
    assert snap["summary"]["total_spend_minor"] == 0


# ---- advisor ----
def _snap():
    pf.clear_fetchers()
    return pf.snapshot("t1", demo=True)


def test_recommend_min_cost():
    r = adv.recommend(_snap(), goal="min_cost")
    assert r["goal"] == "min_cost"
    assert r["recommendations"] and any(x["action"] == "shift_budget" for x in r["recommendations"])
    assert r["allocation"] and abs(sum(a["share"] for a in r["allocation"]) - 1.0) < 0.01
    assert r["summary_text"]


def test_recommend_max_conversions():
    r = adv.recommend(_snap(), goal="max_conversions")
    assert r["goal"] == "max_conversions"
    assert any(x["action"] == "scale" for x in r["recommendations"])


def test_recommend_diversify_on_same_type():
    r = adv.recommend(_snap(), goal="min_cost")
    assert any(x["action"] == "diversify" for x in r["recommendations"])


def test_chat_cheapest():
    out = adv.chat(_snap(), "which platform is the cheapest?")
    assert out["intent"] == "cheapest" and "cheapest" in out["answer"].lower()


def test_chat_total_spend():
    out = adv.chat(_snap(), "how much have we spent in total?")
    assert out["intent"] == "total_spend" and "Total spend" in out["answer"]


def test_chat_recommend():
    out = adv.chat(_snap(), "what should I do to get more conversions?")
    assert out["intent"] == "recommend" and out["answer"]


def test_chat_best_ctr():
    out = adv.chat(_snap(), "which has the best ctr?")
    assert out["intent"] == "best_ctr"


def test_chat_empty_and_fallback():
    assert adv.chat(_snap(), "")["intent"] == "empty"
    fb = adv.chat(_snap(), "tell me something interesting")
    assert fb["answer"]


def _run():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    pf.clear_fetchers()
    print(f"PASS grow.tests.test_platforms ({len(fns)} tests)")


if __name__ == "__main__":
    _run()
