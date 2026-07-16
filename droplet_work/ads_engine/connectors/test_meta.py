"""Offline unit test for connectors.meta — MOCKED httpx, NO real network, NO real keys.

Every request is served by an httpx.MockTransport that RECORDS the outgoing request (method, url,
body) so we can assert the exact v25 payload SHAPE — especially the HOUSING Special Ad Category
fields and the geo-radius targeting whitelist. Sleep is stubbed. Run:
    python -c "import sys; sys.path.insert(0,'droplet_work'); import ads_engine.connectors.test_meta as t; t.main()"

Asserts:
  1. create_campaign -> POST .../v25.0/act_123/campaigns with special_ad_categories=["HOUSING"]
     + special_ad_category_country=["IN"] + objective OUTCOME_LEADS + status PAUSED.
  2. geo-radius targeting builder: custom_locations radius bumped to >=25km, age 18/65, both
     genders, and NO zip/interests/exclusions/lookalike keys anywhere.
  3. create_adset posts the targeting verbatim + daily_budget (minor units) + CTWA destination.
  4. batch helper: <=50 guard, dependency-chained publish ops, version-less root URL.
  5. leadgen webhook: subscribe path + HMAC verify FAIL-CLOSED (good sig pass, bad/missing fail)
     + parse_leadgen extracts leadgen_id/page_id/form_id.
  6. get_lead / reconcile_leads paths + fields.
  7. insights pull path + fields.
  8. CAPI: user_data SHA-256 hashed (em/ph) but fbp/ctwa_clid plaintext; event shape; /events path.
  9. auth: Bearer system_user_token injected; token never in url.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import sys
import asyncio


def _imports():
    try:
        import httpx  # noqa: F401
    except Exception as e:  # noqa: BLE001
        print(f"SKIP (httpx unavailable): {e!r}")
        return None
    from ads_engine.connectors.meta import MetaConnector
    from ads_engine.connectors.base import ConnectorError
    return httpx, MetaConnector, ConnectorError


class _FakeCreds:
    """Stand-in for vault_adapter.ConnectorCreds — secret blob lives on secret_json (never .env)."""
    ok = True
    channel = "meta"
    tenant_id = "tnt_test"
    provider_def_id = "pdef_1"

    def __init__(self, blob):
        self.secret_json = blob


_BLOB = {
    "system_user_token": "SYSU_TESTTOKEN",
    "ad_account_id": "123",          # no act_ prefix on purpose -> connector should normalize
    "page_id": "PAGE_99",
    "dataset_id": "DS_77",
    "app_secret": "APPSECRET_XYZ",
    "business_id": "BIZ_5",
}


def _make(httpx, MetaConnector):
    """Build a MetaConnector with a recording MockTransport. Returns (conn, records)."""
    records: list = []

    def _handler(request):
        body = None
        try:
            raw = request.content
            if raw:
                txt = raw.decode("utf-8", "replace")
                # JSON body or form body — record raw; tests parse as needed.
                body = txt
        except Exception:  # noqa: BLE001
            body = None
        records.append({
            "method": request.method,
            "url": str(request.url),
            "headers": dict(request.headers),
            "body": body,
        })
        return httpx.Response(200, json={"id": "RESP_ID_1"})

    transport = httpx.MockTransport(_handler)
    client = httpx.AsyncClient(transport=transport)

    async def _sleep(d):
        pass

    conn = MetaConnector(_FakeCreds(_BLOB), version="v25.0", http=client, sleep_fn=_sleep)
    return conn, records


def _run(coro):
    return asyncio.run(coro)


def main() -> int:
    got = _imports()
    if got is None:
        return 0
    httpx, MetaConnector, ConnectorError = got
    failures = []

    def check(name, cond):
        print(f"  {'PASS' if cond else 'FAIL'} — {name}")
        if not cond:
            failures.append(name)

    # ---- 1. create_campaign HOUSING fields ------------------------------------------------
    async def t1():
        conn, rec = _make(httpx, MetaConnector)
        plan = {"name": "Prestige Lakeside — Leads", "objective": "OUTCOME_LEADS"}
        res = await conn.create_campaign(plan, housing=True)
        await conn.aclose()
        return res, rec
    res, rec = _run(t1())
    r0 = rec[0]
    body = json.loads(r0["body"])
    check("create_campaign POST to /v25.0/act_123/campaigns",
          res.ok and r0["method"] == "POST"
          and r0["url"].endswith("/v25.0/act_123/campaigns"))
    check("campaign special_ad_categories == ['HOUSING']",
          body.get("special_ad_categories") == ["HOUSING"])
    check("campaign special_ad_category_country == ['IN']",
          body.get("special_ad_category_country") == ["IN"])
    check("campaign objective OUTCOME_LEADS + status PAUSED",
          body.get("objective") == "OUTCOME_LEADS" and body.get("status") == "PAUSED")
    check("auth Bearer system_user_token injected, token NOT in url",
          r0["headers"].get("authorization") == "Bearer SYSU_TESTTOKEN"
          and "SYSU_TESTTOKEN" not in r0["url"])

    # bad/ASC objective coerced to safe default; non-housing still sends REQUIRED [] array.
    conn2 = MetaConnector(_FakeCreds(_BLOB), version="v25.0")
    camp_asc = conn2.build_campaign_payload(name="x", objective="OUTCOME_APP_PROMOTION",
                                            housing=True)
    check("unknown/ASC objective coerced to OUTCOME_LEADS default",
          camp_asc["objective"] == "OUTCOME_LEADS")
    camp_none = conn2.build_campaign_payload(name="x", objective="OUTCOME_TRAFFIC",
                                             housing=False)
    check("non-housing campaign still carries REQUIRED special_ad_categories array",
          "special_ad_categories" in camp_none
          and isinstance(camp_none["special_ad_categories"], list))

    # ---- 2. geo-radius targeting whitelist ------------------------------------------------
    targ = conn2.build_geo_radius_targeting(latitude=12.9716, longitude=77.5946,
                                            radius_km=5, housing=True)
    cl = targ["geo_locations"]["custom_locations"][0]
    check("radius bumped UP to >=25km floor (5 -> 25)", cl["radius"] >= 25)
    check("custom_locations carries lat/lng + kilometer unit",
          abs(cl["latitude"] - 12.9716) < 1e-6 and cl["distance_unit"] == "kilometer")
    check("HOUSING age locked 18..65", targ.get("age_min") == 18 and targ.get("age_max") == 65)
    check("HOUSING all genders [1,2]", targ.get("genders") == [1, 2])
    flat = json.dumps(targ).lower()
    forbidden = ["zip", "interest", "flexible_spec", "exclusion", "lookalike", "behavior"]
    check("NO zip/interests/exclusions/lookalike/behavior keys in targeting",
          not any(w in flat for w in forbidden))

    # ---- 3. create_adset posts targeting verbatim + budget + CTWA -------------------------
    async def t3():
        conn, rec = _make(httpx, MetaConnector)
        plan = {
            "targeting": targ,
            "budget_daily_minor": 120000,
            "destination_type": "WHATSAPP",
            "promoted_object": {"page_id": "PAGE_99"},
        }
        res = await conn.create_adset(plan, "CAMP_1")
        await conn.aclose()
        return res, rec
    res, rec = _run(t3())
    b = json.loads(rec[0]["body"])
    check("create_adset POST to /v25.0/act_123/adsets",
          rec[0]["url"].endswith("/v25.0/act_123/adsets"))
    check("adset campaign_id + daily_budget(minor) passed through",
          b.get("campaign_id") == "CAMP_1" and b.get("daily_budget") == 120000)
    check("adset targeting posted verbatim (age 18/65 preserved)",
          b["targeting"].get("age_min") == 18 and b["targeting"].get("age_max") == 65)
    check("CTWA destination_type WHATSAPP", b.get("destination_type") == "WHATSAPP")

    # adset refuses when targeting missing (won't post an open audience).
    async def t3b():
        conn, rec = _make(httpx, MetaConnector)
        res = await conn.create_adset({"budget_daily_minor": 1}, "C")
        await conn.aclose()
        return res, rec
    res, rec = _run(t3b())
    check("create_adset refuses missing targeting (no open audience)",
          (not res.ok) and res.error == ConnectorError.INVALID_REQUEST and len(rec) == 0)

    # ---- 4. batch helper ------------------------------------------------------------------
    ops = conn2.build_publish_batch(
        {"name": "P", "objective": "OUTCOME_LEADS", "targeting": targ,
         "budget_daily_minor": 120000},
        creatives=[{"headline": "H1", "primary_text": "P1"},
                   {"headline": "H2", "primary_text": "P2"}],
        housing=True)
    names = [o.get("name") for o in ops]
    check("batch ops dependency-chained (campaign->adset->creatives->ads)",
          names[0] == "create_campaign" and names[1] == "create_adset"
          and "create_ad_0" in names and "create_ad_1" in names)
    camp_op_body = ops[0]["body"]
    check("batch campaign sub-request carries HOUSING (form-encoded)",
          "HOUSING" in camp_op_body)
    check("batch adset depends_on create_campaign + references its id",
          ops[1].get("depends_on") == "create_campaign"
          and "{result=create_campaign:$.id}" in ops[1]["body"])

    async def t4():
        conn, rec = _make(httpx, MetaConnector)
        res = await conn.batch(ops)
        await conn.aclose()
        return res, rec
    res, rec = _run(t4())
    # batch posts to the version-less root.
    check("batch POST to graph root (version-less), <=50 ok",
          res.ok and rec[0]["url"].rstrip("/").endswith("graph.facebook.com"))

    async def t4b():
        conn, rec = _make(httpx, MetaConnector)
        res = await conn.batch([{"method": "GET", "relative_url": "me"}] * 51)
        await conn.aclose()
        return res
    res = _run(t4b())
    check("batch >50 rejected (INVALID_REQUEST, no network)",
          (not res.ok) and res.error == ConnectorError.INVALID_REQUEST)

    # ---- 5. leadgen webhook: subscribe + HMAC verify fail-closed + parse ------------------
    async def t5():
        conn, rec = _make(httpx, MetaConnector)
        res = await conn.subscribe_leadgen()
        await conn.aclose()
        return res, rec
    res, rec = _run(t5())
    check("subscribe_leadgen POST /v25.0/PAGE_99/subscribed_apps?subscribed_fields=leadgen",
          rec[0]["url"].endswith("/v25.0/PAGE_99/subscribed_apps?subscribed_fields=leadgen")
          or ("/v25.0/PAGE_99/subscribed_apps" in rec[0]["url"]
              and "subscribed_fields=leadgen" in rec[0]["url"]))

    raw = b'{"object":"page","entry":[]}'
    good = "sha256=" + hmac.new(b"APPSECRET_XYZ", raw, hashlib.sha256).hexdigest()
    check("HMAC verify accepts a correct signature",
          conn2.verify_webhook_signature("APPSECRET_XYZ", raw, good) is True)
    check("HMAC verify rejects a forged signature (fail-closed)",
          conn2.verify_webhook_signature("APPSECRET_XYZ", raw, "sha256=deadbeef") is False)
    check("HMAC verify fail-closed on missing secret",
          conn2.verify_webhook_signature("", raw, good) is False)
    check("HMAC verify fail-closed on missing header",
          conn2.verify_webhook_signature("APPSECRET_XYZ", raw, "") is False)

    payload = {"entry": [{"id": "PAGE_99", "changes": [
        {"field": "leadgen", "value": {"leadgen_id": "LG1", "form_id": "F1",
                                       "ad_id": "AD1", "page_id": "PAGE_99"}}]}]}
    leads = MetaConnector.parse_leadgen(payload)
    check("parse_leadgen extracts leadgen_id/form_id/page_id",
          len(leads) == 1 and leads[0]["leadgen_id"] == "LG1"
          and leads[0]["form_id"] == "F1" and leads[0]["page_id"] == "PAGE_99")
    check("parse_leadgen tolerant of malformed payload (no raise)",
          MetaConnector.parse_leadgen({"bad": 1}) == [])

    # ---- 6. get_lead / reconcile_leads ----------------------------------------------------
    async def t6():
        conn, rec = _make(httpx, MetaConnector)
        await conn.get_lead("LG1")
        await conn.reconcile_leads("F1", since=1700000000)
        await conn.aclose()
        return rec
    rec = _run(t6())
    check("get_lead GET /v25.0/LG1?fields=field_data,...",
          "/v25.0/LG1" in rec[0]["url"] and "field_data" in rec[0]["url"])
    check("reconcile_leads GET /v25.0/F1/leads with time filter",
          "/v25.0/F1/leads" in rec[1]["url"] and "filtering" in rec[1]["url"])

    # ---- 7. insights ----------------------------------------------------------------------
    async def t7():
        conn, rec = _make(httpx, MetaConnector)
        await conn.pull_insights(level="campaign")
        await conn.aclose()
        return rec
    rec = _run(t7())
    check("pull_insights GET /v25.0/act_123/insights with fields",
          "/v25.0/act_123/insights" in rec[0]["url"] and "spend" in rec[0]["url"])

    # ---- 8. CAPI hashing + send -----------------------------------------------------------
    ud = {"em": "Test@Example.com", "ph": "+91 99999 88888",
          "fbp": "fb.1.123.456", "ctwa_clid": "CTWACLID_1"}
    hashed = MetaConnector.hash_user_data(ud)
    exp_em = hashlib.sha256("test@example.com".encode()).hexdigest()
    check("CAPI em SHA-256 hashed (lowercased/trimmed)", hashed["em"] == exp_em)
    check("CAPI ph SHA-256 hashed (64-hex)", len(hashed["ph"]) == 64)
    check("CAPI fbp/ctwa_clid kept PLAINTEXT",
          hashed["fbp"] == "fb.1.123.456" and hashed["ctwa_clid"] == "CTWACLID_1")

    ev = conn2.build_capi_event(event_name="Lead", event_time=1700000000,
                                action_source="business_messaging", user_data=ud,
                                event_id="dedup_1")
    check("CAPI event shape (event_name/time/action_source/event_id/user_data hashed)",
          ev["event_name"] == "Lead" and ev["event_time"] == 1700000000
          and ev["action_source"] == "business_messaging" and ev["event_id"] == "dedup_1"
          and ev["user_data"]["em"] == exp_em)

    async def t8():
        conn, rec = _make(httpx, MetaConnector)
        res = await conn.send_capi([ev], test_event_code="TEST123")
        await conn.aclose()
        return res, rec
    res, rec = _run(t8())
    cb = json.loads(rec[0]["body"])
    check("send_capi POST /v25.0/DS_77/events with data[] + test_event_code",
          rec[0]["url"].endswith("/v25.0/DS_77/events")
          and isinstance(cb.get("data"), list) and cb.get("test_event_code") == "TEST123")

    # ---- 9. ad-account normalization (act_ prefix added) ----------------------------------
    check("ad_account_id normalized to act_123", conn2._ad_account() == "act_123")

    print(f"\nconnectors.meta test: {'ALL PASS' if not failures else 'FAILURES: ' + repr(failures)}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
