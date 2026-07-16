"""Offline W5 smoke for ads_engine.campaign — NO app boot, NO .env, NO network, NO caller.

Mocks the connector via an injected httpx MockTransport (records outgoing requests) and wires the
store onto a tempdir. Deterministic. Run:
  python -c "import sys; sys.path.insert(0,'droplet_work'); import ads_engine._smoke_w5 as s; s.main()"

Asserts (the W5 prompt's OFFLINE TESTS list):
  * sub-floor housing launch is HARD-blocked (propose -> blocked_insufficient_funds; approve refused)
  * HOUSING fields ALWAYS present + NO illegal targeting key reachable (by construction)
  * missing is_property -> housing campaign refused (single authoritative setter)
  * lifecycle transitions: propose(draft) -> approve(dry_run) ; warn needs step-up
  * plan_id idempotency at publish (re-approve same plan_id => no duplicate publish)
  * caps set at publish (Meta set_caps called; Google CampaignBudget amountMicros in the mutate)
  * viability clamps live in code (cpa_multiplier>=50, viability_block_ratio>=0.8)
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path


# ---------------------------------------------------------------------------
# Test wiring: a store on a tempdir + a mocked connectors module.
# ---------------------------------------------------------------------------
def _wire_store(tmp: Path):
    import ads_engine as pkg

    def _read(path, default):
        try:
            return json.loads(Path(path).read_text(encoding="utf-8"))
        except Exception:
            return default

    def _awj(path, data):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps(data), encoding="utf-8")

    pkg.wire(_read=_read, _write=lambda p, d: _awj(p, d),
             _atomic_write_json=_awj, var_dir=tmp)


class _RecordingConnectors:
    """Stand-in for ads_engine.connectors with a recording Meta/Google connector."""

    def __init__(self, httpx, channel="meta"):
        self.httpx = httpx
        self.channel = channel
        self.records: list = []

    def get_connector(self, tenant_id, channel, *, http=None):
        from ads_engine.connectors.meta import MetaConnector
        from ads_engine.connectors.google import GoogleConnector
        recs = self.records

        def _handler(request):
            body = None
            try:
                raw = request.content
                if raw:
                    body = raw.decode("utf-8", "replace")
            except Exception:
                body = None
            recs.append({"method": request.method, "url": str(request.url), "body": body})
            # Meta batch returns a list; single creates return {id}; google returns mutate results.
            if "datamanager" in str(request.url) or "oauth2" in str(request.url):
                return self.httpx.Response(200, json={"access_token": "AT", "expires_in": 3600})
            if str(request.url).endswith("/") or "batch" in (body or ""):
                return self.httpx.Response(200, json=[
                    {"code": 200, "body": json.dumps({"id": "CAMP_1"})},
                    {"code": 200, "body": json.dumps({"id": "ADSET_1"})},
                    {"code": 200, "body": json.dumps({"id": "CR_1"})},
                    {"code": 200, "body": json.dumps({"id": "AD_1"})},
                ])
            if "googleAds:mutate" in str(request.url):
                return self.httpx.Response(200, json={"mutateOperationResponses": [
                    {"campaignBudgetResult": {"resourceName": "customers/1/campaignBudgets/9"}},
                    {"campaignResult": {"resourceName": "customers/1/campaigns/8"}},
                ]})
            return self.httpx.Response(200, json={"id": "OBJ_1"})

        transport = self.httpx.MockTransport(_handler)
        client = self.httpx.AsyncClient(transport=transport)

        _tid = tenant_id

        class _Creds:
            ok = True
            channel = "meta"

            def __init__(self, blob):
                self.secret_json = blob
                self.tenant_id = _tid

        if channel == "google":
            blob = {"client_id": "ci", "client_secret": "cs", "refresh_token": "rt",
                    "developer_token": "dt", "customer_id": "111", "login_customer_id": "111"}
            return GoogleConnector(_Creds(blob), version="v24", http=client)
        blob = {"system_user_token": "TOK", "ad_account_id": "123", "page_id": "P", "dataset_id": "D"}
        return MetaConnector(_Creds(blob), version="v25.0", http=client)


def _housing_brief(**over):
    b = {
        "name": "Prestige Lakeside — Leads",
        "provider": "meta",
        "objective": "leads",
        "is_property": True,
        "geo_pin": {"lat": 12.9716, "lng": 77.5946},
        "radius_km": 5,                 # below floor -> must bump to >=25
        "budget_daily_minor": 500000,   # Rs5000/day
        "cpl_max_minor": 50000,         # Rs500 CPL
        "creatives": [{"variant_id": "v1", "headline": "H", "primary_text": "P",
                       "description": "D", "state": "approved"}],
        # hostile keys the single setter must strip / never reach:
        "audience": {"age_min": 25, "genders": [1], "interests": ["luxury"],
                     "zips": ["560001"], "lookalike_spec": {"x": 1}},
    }
    b.update(over)
    return b


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
def _t_clamps():
    from ads_engine import config as cfg
    # cpa_multiplier floored >=50 even if env tries to lower it.
    os.environ["ADS_CPA_MULTIPLIER"] = "1"
    os.environ["ADS_VIABILITY_BLOCK_RATIO"] = "0.0"
    m = cfg.cpa_multiplier()
    r = cfg.viability_block_ratio()
    rad = cfg.min_radius_km()
    os.environ.pop("ADS_CPA_MULTIPLIER", None)
    os.environ.pop("ADS_VIABILITY_BLOCK_RATIO", None)
    ok = m >= 50 and r >= 0.8 and rad >= 25.0
    return (f"viability clamps in code (cpa_mult={m}>=50, block_ratio={r}>=0.8, "
            f"min_radius={rad}>=25)", ok)


def _t_housing_fields_and_no_illegal(tmp):
    from ads_engine import campaign as cam
    plan = cam.build_plan("t_A", _housing_brief())
    t = plan["targeting"]
    fields_ok = (plan["special_ad_category"] == "HOUSING"
                 and plan["special_ad_categories"] == ["HOUSING"]
                 and plan["special_ad_category_country"] == ["IN"]
                 and t["age_min"] == 18 and t["age_max"] == 65
                 and sorted(t["genders"]) == [1, 2])
    # NO illegal key reachable anywhere on the emitted targeting.
    illegal = cam._ILLEGAL_HOUSING_TARGETING_KEYS
    no_illegal = not any(k in t for k in illegal)
    geo = t.get("geo_locations", {})
    geo_clean = ("custom_locations" in geo
                 and not any(k in geo for k in ("zips", "regions", "cities", "neighborhoods")))
    # radius bumped from 5 to >=25.
    radius_ok = geo["custom_locations"][0]["radius"] >= 25
    # brief's hostile keys recorded as stripped.
    stripped_ok = "interests" in plan["targeting_stripped"] and "zips" in plan["targeting_stripped"]
    ok = fields_ok and no_illegal and geo_clean and radius_ok and stripped_ok
    return (f"HOUSING fields present + no illegal targeting reachable "
            f"(fields={fields_ok}, no_illegal={no_illegal}, radius_ok={radius_ok}, "
            f"stripped={stripped_ok})", ok)


def _t_missing_is_property_refused(tmp):
    from ads_engine import campaign as cam
    res = cam.propose("t_A", _housing_brief(is_property=False))
    ok = (res["ok"] is False and res["status"] == "invalid_request"
          and "is_property" in res["reason"])
    return (f"missing is_property refused (status={res['status']})", ok)


def _t_subfloor_hard_block(tmp):
    from ads_engine import campaign as cam
    # Rs500 CPL x50 x(30/7) ~= Rs10.7L/mo floor. Budget Rs100/day -> Rs3000/mo -> far sub-floor.
    res = cam.propose("t_A", _housing_brief(budget_daily_minor=10000))  # Rs100/day
    v = res["viability"]
    blocked = (res["status"] == cam.ST_BLOCKED_FUNDS
               and v["verdict"] == "blocked_underfunded")
    # approve must refuse the blocked plan (no publish).
    appr = asyncio.run(cam.approve("t_A", res["plan_id"]))
    refused = appr["ok"] is False and appr["status"] == cam.ST_BLOCKED_FUNDS
    ok = blocked and refused
    return (f"sub-floor housing launch HARD-blocked (propose={res['status']}, "
            f"approve_refused={refused})", ok)


def _t_warn_needs_stepup(tmp):
    from ads_engine import campaign as cam
    # Budget between block-floor and full floor -> warn_underfunded.
    # floor ~Rs10.7L/mo; block ratio 0.8 -> hard floor ~Rs8.57L/mo (~Rs2857/day).
    # Pick Rs3500/day -> Rs10.5L/mo: above hard floor, below full floor -> warn.
    res = cam.propose("t_A", _housing_brief(budget_daily_minor=350000))
    v = res["viability"]
    is_warn = v["verdict"] == "warn_underfunded" and res["status"] == cam.ST_DRAFT
    no_stepup = asyncio.run(cam.approve("t_A", res["plan_id"], step_up=False))
    refused = no_stepup["ok"] is False and no_stepup["status"] == "blocked_not_approved"
    with_stepup = asyncio.run(cam.approve("t_A", res["plan_id"], step_up=True))
    launched = with_stepup["ok"] is True and with_stepup["status"] == cam.ST_DRY_RUN
    ok = is_warn and refused and launched
    return (f"warn_underfunded needs step-up override "
            f"(warn={is_warn}, refused_no_stepup={refused}, launched_with={launched})", ok)


def _t_lifecycle_dry_run(tmp):
    from ads_engine import campaign as cam
    res = cam.propose("t_B", _housing_brief())
    proposed_draft = res["status"] == cam.ST_DRAFT and res["viability"]["verdict"] == "ok"
    appr = asyncio.run(cam.approve("t_B", res["plan_id"]))
    dry = appr["ok"] and appr["status"] == cam.ST_DRY_RUN and appr["campaign_ref"].startswith("dry_")
    # pause transition.
    pz = asyncio.run(cam.pause("t_B", res["plan_id"], "manual"))
    paused = pz["ok"] and pz["status"] == cam.ST_PAUSED
    ok = proposed_draft and dry and paused
    return (f"lifecycle propose(draft)->approve(dry_run)->pause "
            f"(draft={proposed_draft}, dry={dry}, paused={paused})", ok)


def _t_idempotency_no_dup(tmp, connectors):
    from ads_engine import campaign as cam
    cam.bind(connectors=connectors)
    # turn OFF dry_run for a live (mocked) publish; idempotency on re-approve.
    os.environ["ADS_DRY_RUN"] = "0"
    try:
        res = cam.propose("t_C", _housing_brief())
        a1 = asyncio.run(cam.approve("t_C", res["plan_id"]))
        pub_calls_1 = len([r for r in connectors.records if r["method"] == "POST"
                           and r["url"].endswith("/")])
        a2 = asyncio.run(cam.approve("t_C", res["plan_id"]))  # re-approve same plan_id
        pub_calls_2 = len([r for r in connectors.records if r["method"] == "POST"
                           and r["url"].endswith("/")])
        active = a1["ok"] and a1["status"] == cam.ST_ACTIVE
        idem = a2["ok"] and a2.get("already") is True and a2["campaign_ref"] == a1["campaign_ref"]
        no_dup = pub_calls_2 == pub_calls_1  # no second batch publish
        ok = active and idem and no_dup
        return (f"plan_id idempotency: no duplicate publish "
                f"(active={active}, already={idem}, batch_calls {pub_calls_1}->{pub_calls_2})", ok)
    finally:
        os.environ["ADS_DRY_RUN"] = "1"


def _t_caps_at_publish_meta(tmp, connectors):
    from ads_engine import campaign as cam
    cam.bind(connectors=connectors)
    os.environ["ADS_DRY_RUN"] = "0"
    try:
        res = cam.propose("t_D", _housing_brief(daily_cap_minor=600000,
                                                lifetime_cap_minor=9000000))
        a = asyncio.run(cam.approve("t_D", res["plan_id"]))
        # set_caps is POST to /v25.0/ADSET_1 with daily_budget + lifetime_budget in the body.
        cap_calls = [r for r in connectors.records
                     if r["method"] == "POST" and r["url"].endswith("/ADSET_1")
                     and "daily_budget" in (r["body"] or "")]
        caps_ok = a["ok"] and a.get("caps_set") is True and len(cap_calls) >= 1
        body_has = cap_calls and "lifetime_budget" in (cap_calls[0]["body"] or "")
        ok = caps_ok and bool(body_has)
        return (f"Meta caps set at publish (caps_set={a.get('caps_set')}, "
                f"set_caps_calls={len(cap_calls)}, lifetime_in_body={bool(body_has)})", ok)
    finally:
        os.environ["ADS_DRY_RUN"] = "1"


def _t_caps_at_publish_google(tmp):
    from ads_engine import campaign as cam
    import httpx
    gconn = _RecordingConnectors(httpx, channel="google")

    class _GoogleOnly:
        records = gconn.records

        def get_connector(self, tenant_id, channel, *, http=None):
            return gconn.get_connector(tenant_id, "google")

    cam.bind(connectors=_GoogleOnly())
    os.environ["ADS_DRY_RUN"] = "0"
    try:
        res = cam.propose("t_E", _housing_brief(provider="google", channel_type="SEARCH",
                                                daily_cap_minor=600000))
        a = asyncio.run(cam.approve("t_E", res["plan_id"]))
        mutate = [r for r in gconn.records if "googleAds:mutate" in r["url"]]
        # the CampaignBudget amountMicros = 600000 paise * 10000 = 6_000_000_000 micros.
        has_micros = mutate and "6000000000" in (mutate[0]["body"] or "")
        ok = a["ok"] and a.get("caps_set") is True and bool(has_micros)
        return (f"Google CampaignBudget ceiling at publish (caps_set={a.get('caps_set')}, "
                f"micros_in_mutate={bool(has_micros)})", ok)
    finally:
        os.environ["ADS_DRY_RUN"] = "1"
        cam.bind(connectors=None)


def main() -> int:
    try:
        import httpx
    except Exception as e:  # noqa: BLE001
        print(f"SKIP (httpx unavailable): {e!r}")
        return 0

    tmp = Path(tempfile.mkdtemp(prefix="ads_w5_"))
    _wire_store(tmp)
    from ads_engine import campaign as cam
    cam.bind(connectors=None)  # default DRY-RUN tests use no connector

    connectors = _RecordingConnectors(httpx, channel="meta")

    checks = [
        _t_clamps(),
        _t_housing_fields_and_no_illegal(tmp),
        _t_missing_is_property_refused(tmp),
        _t_subfloor_hard_block(tmp),
        _t_warn_needs_stepup(tmp),
        _t_lifecycle_dry_run(tmp),
        _t_idempotency_no_dup(tmp, connectors),
        _t_caps_at_publish_meta(tmp, _RecordingConnectors(httpx, channel="meta")),
        _t_caps_at_publish_google(tmp),
    ]
    all_ok = True
    for label, ok in checks:
        print(f"[{'PASS' if ok else 'FAIL'}] {label}")
        all_ok = all_ok and ok
    print("RESULT:", "ALL PASS" if all_ok else "FAILURES")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
