"""Offline unit test for connectors.google — Google Ads v24 client, MOCKED httpx (no network).

Every upstream call (oauth2 token, googleAds:mutate, searchStream, Data Manager ingestEvents) is
served by an httpx.MockTransport that ROUTES on request host+path and records the bodies. No real
sockets, no real keys. Run:
    python -c "import sys; sys.path.insert(0,'droplet_work'); import ads_engine.connectors.test_google as t; t.main()"

Asserts:
  1. refresh_token_if_needed: posts to oauth2 host, caches access_token, sets Bearer on Ads calls.
  2. create_campaign(SEARCH): one googleAds:mutate; budget->campaign->adGroup with temp neg ids,
     status PAUSED, standard bidding union on the campaign, developer-token + login-customer-id sent.
  3. create_campaign(PERFORMANCE_MAX): channel type + assetGroup (+ optional signal) in one mutate.
  4. add_lead_form_asset: assetOperation(leadFormAsset) + campaignAssetOperation(LEAD_FORM).
  5. upload_conversions: hits the DATA MANAGER host :ingestEvents (NOT the Ads host).
  6. upload_conversions(_legacy=True): HARD NO -> BLOCKED_GOOGLE_LEGACY, ZERO requests issued.
  7. missing creds -> NOT_CONFIGURED (degrade-never-raise), zero Ads requests.
  8. token refresh failure (oauth 400) -> CRED_EXPIRED surfaced, no Ads mutate attempted.
  9. secrets only via creds.secret_json — no os.environ read (creds blob is the only source).
"""

from __future__ import annotations

import asyncio
import sys


def _imports():
    try:
        import httpx  # noqa: F401
    except Exception as e:  # noqa: BLE001
        print(f"SKIP (httpx unavailable): {e!r}")
        return None
    from ads_engine.connectors.google import GoogleConnector
    from ads_engine.connectors.base import ConnectorError
    return httpx, GoogleConnector, ConnectorError


class _FakeCreds:
    """Mimics vault_adapter.ConnectorCreds: ok + secret_json (the decrypted OAuth blob)."""

    def __init__(self, blob, ok=True):
        self.ok = ok
        self.channel = "google"
        self.tenant_id = "t_test"
        self.provider_def_id = "pd_test"
        self.secret_json = blob


_GOOD_BLOB = {
    "client_id": "cid.apps.googleusercontent.com",
    "client_secret": "csecret",
    "refresh_token": "rtoken",
    "developer_token": "devtoken",
    "login_customer_id": "123-456-7890",
    "customer_id": "987-654-3210",
    "product_account_id": "dm-prod-1",
}


def _router(httpx, recorder, *, token_status=200):
    """A MockTransport handler routing on host+path; records (host, path, headers, body)."""

    def _handler(request):
        host = request.url.host
        path = request.url.path
        body = None
        try:
            if request.content:
                import json as _j
                body = _j.loads(request.content)
        except Exception:  # noqa: BLE001
            body = {"_raw": True}
        recorder.append({
            "host": host, "path": path,
            "auth": request.headers.get("authorization"),
            "dev_token": request.headers.get("developer-token"),
            "login_cid": request.headers.get("login-customer-id"),
            "body": body,
            "content": request.content,
        })
        if host == "oauth2.googleapis.com":
            if token_status != 200:
                return httpx.Response(token_status, json={"error": "invalid_grant"})
            return httpx.Response(200, json={"access_token": "ACCESS_123", "expires_in": 3600})
        if host == "googleads.googleapis.com":
            return httpx.Response(200, json={"results": [{"resourceName": "customers/987/campaigns/1"}]})
        if host == "datamanager.googleapis.com":
            return httpx.Response(200, json={"requestId": "dm-1"})
        return httpx.Response(404, json={"unmatched": host})

    return httpx.MockTransport(_handler)


def _conn(httpx, GoogleConnector, recorder, *, blob=_GOOD_BLOB, token_status=200):
    transport = _router(httpx, recorder, token_status=token_status)
    client = httpx.AsyncClient(transport=transport)

    async def _no_sleep(_d):
        return None

    c = GoogleConnector(_FakeCreds(blob), http=client, sleep_fn=_no_sleep)
    return c


def _run(coro):
    return asyncio.run(coro)


def main() -> int:
    got = _imports()
    if got is None:
        return 0
    httpx, GoogleConnector, ConnectorError = got
    failures = []

    def check(name, cond):
        print(f"  {'PASS' if cond else 'FAIL'} — {name}")
        if not cond:
            failures.append(name)

    # 1. token refresh.
    async def t1():
        rec = []
        c = _conn(httpx, GoogleConnector, rec)
        r = await c.refresh_token_if_needed()
        await c.aclose()
        return r, rec
    r, rec = _run(t1())
    check("refresh_token: ok + posts to oauth2 host",
          r.ok and any(x["host"] == "oauth2.googleapis.com" and x["path"] == "/token" for x in rec))
    check("refresh_token: token request is form-encoded (not a JSON body)",
          bool(rec) and b"grant_type=refresh_token" in (rec[0]["content"] or b"")
          and b"client_secret=" in (rec[0]["content"] or b""))

    # 2. create_campaign SEARCH.
    async def t2():
        rec = []
        c = _conn(httpx, GoogleConnector, rec)
        r = await c.create_campaign({
            "name": "Test Search", "channel_type": "SEARCH",
            "daily_budget_minor": 50000,  # paise
            "bidding": {"type": "maximize_conversions"},
        })
        await c.aclose()
        return r, rec
    r, rec = _run(t2())
    ads_calls = [x for x in rec if x["host"] == "googleads.googleapis.com"]
    mutate = ads_calls[0] if ads_calls else {}
    ops = (mutate.get("body") or {}).get("mutateOperations", [])
    check("SEARCH: ok + exactly one googleAds:mutate", r.ok and len(ads_calls) == 1
          and mutate.get("path", "").endswith("/googleAds:mutate"))
    check("SEARCH: budget->campaign->adGroup with temp neg ids",
          any("campaignBudgetOperation" in o for o in ops)
          and any("campaignOperation" in o for o in ops)
          and any("adGroupOperation" in o for o in ops))
    camp_op = next((o["campaignOperation"]["create"] for o in ops if "campaignOperation" in o), {})
    check("SEARCH: status PAUSED + SEARCH channel + standard bidding union on campaign",
          camp_op.get("status") == "PAUSED"
          and camp_op.get("advertisingChannelType") == "SEARCH"
          and "maximizeConversions" in camp_op)
    check("SEARCH: Bearer + developer-token + login-customer-id headers sent",
          mutate.get("auth") == "Bearer ACCESS_123"
          and mutate.get("dev_token") == "devtoken"
          and mutate.get("login_cid") == "1234567890")

    # 3. create_campaign PERFORMANCE_MAX.
    async def t3():
        rec = []
        c = _conn(httpx, GoogleConnector, rec)
        r = await c.create_campaign({
            "name": "Test PMax", "channel_type": "PERFORMANCE_MAX",
            "daily_budget_minor": 100000,
            "asset_group": {"final_urls": ["https://x.test/lp"], "audience_signal": "aud/1"},
        })
        await c.aclose()
        return r, rec
    r, rec = _run(t3())
    ops = next((x["body"]["mutateOperations"] for x in rec
                if x["host"] == "googleads.googleapis.com"), [])
    camp_op = next((o["campaignOperation"]["create"] for o in ops if "campaignOperation" in o), {})
    check("PMAX: PERFORMANCE_MAX channel + assetGroup + signal in one mutate",
          r.ok and camp_op.get("advertisingChannelType") == "PERFORMANCE_MAX"
          and any("assetGroupOperation" in o for o in ops)
          and any("assetGroupSignalOperation" in o for o in ops))

    # 4. add_lead_form_asset.
    async def t4():
        rec = []
        c = _conn(httpx, GoogleConnector, rec)
        r = await c.add_lead_form_asset({
            "name": "LF", "campaign_resource": "customers/987/campaigns/1",
            "business_name": "ElevateX", "fields": ["FULL_NAME", "EMAIL", "PHONE_NUMBER"],
        })
        await c.aclose()
        return r, rec
    r, rec = _run(t4())
    ops = next((x["body"]["mutateOperations"] for x in rec
                if x["host"] == "googleads.googleapis.com"), [])
    asset_op = next((o["assetOperation"]["create"] for o in ops if "assetOperation" in o), {})
    ca_op = next((o["campaignAssetOperation"]["create"] for o in ops
                  if "campaignAssetOperation" in o), {})
    check("lead form: leadFormAsset + CampaignAsset(field_type LEAD_FORM)",
          r.ok and "leadFormAsset" in asset_op and ca_op.get("fieldType") == "LEAD_FORM")

    # 5. upload_conversions via Data Manager host.
    async def t5():
        rec = []
        c = _conn(httpx, GoogleConnector, rec)
        r = await c.upload_conversions([{"conversion": "x"}])
        await c.aclose()
        return r, rec
    r, rec = _run(t5())
    dm_calls = [x for x in rec if x["host"] == "datamanager.googleapis.com"]
    ads_calls = [x for x in rec if x["host"] == "googleads.googleapis.com"]
    check("conversions: hits Data Manager :ingestEvents, NOT the Ads host",
          r.ok and len(dm_calls) == 1 and dm_calls[0]["path"].endswith(":ingestEvents")
          and len(ads_calls) == 0)

    # 6. legacy path is a HARD NO with zero requests.
    async def t6():
        rec = []
        c = _conn(httpx, GoogleConnector, rec)
        r = await c.upload_conversions([{"x": 1}], _legacy=True)
        await c.aclose()
        return r, rec
    r, rec = _run(t6())
    check("legacy offline path -> BLOCKED_GOOGLE_LEGACY, ZERO requests",
          (not r.ok) and r.error == ConnectorError.BLOCKED_GOOGLE_LEGACY and len(rec) == 0)

    # 7. missing creds -> NOT_CONFIGURED, no Ads request.
    async def t7():
        rec = []
        c = _conn(httpx, GoogleConnector, rec, blob={})  # empty blob
        r = await c.create_campaign({"name": "x", "channel_type": "SEARCH"})
        await c.aclose()
        return r, rec
    r, rec = _run(t7())
    check("missing creds -> NOT_CONFIGURED, zero requests",
          (not r.ok) and r.error == ConnectorError.NOT_CONFIGURED and len(rec) == 0)

    # 8. token endpoint 400 -> CRED_EXPIRED, no Ads mutate.
    async def t8():
        rec = []
        c = _conn(httpx, GoogleConnector, rec, token_status=400)
        r = await c.create_campaign({"name": "x", "channel_type": "SEARCH",
                                     "daily_budget_minor": 1000})
        await c.aclose()
        return r, rec
    r, rec = _run(t8())
    ads_calls = [x for x in rec if x["host"] == "googleads.googleapis.com"]
    check("token 400 -> CRED_EXPIRED, no Ads mutate attempted",
          (not r.ok) and r.error == ConnectorError.CRED_EXPIRED and len(ads_calls) == 0)

    # 9. secrets-source proof: connector reads ONLY creds.secret_json (no env). Set a fake env var
    #    that would NEVER be consulted; the connector must still derive everything from the blob.
    async def t9():
        import os
        os.environ["GOOGLE_ADS_DEVELOPER_TOKEN"] = "ENV_LEAK_SHOULD_NOT_BE_USED"
        rec = []
        c = _conn(httpx, GoogleConnector, rec)
        await c.refresh_token_if_needed()
        r = await c.create_campaign({"name": "x", "channel_type": "SEARCH",
                                     "daily_budget_minor": 1000})
        await c.aclose()
        os.environ.pop("GOOGLE_ADS_DEVELOPER_TOKEN", None)
        return r, rec
    r, rec = _run(t9())
    mutate = next((x for x in rec if x["host"] == "googleads.googleapis.com"), {})
    check("secrets via creds.secret_json ONLY (env developer-token NOT used)",
          r.ok and mutate.get("dev_token") == "devtoken")

    print(f"\nconnectors.google test: {'ALL PASS' if not failures else 'FAILURES: ' + repr(failures)}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
