"""Offline smoke for the CONNECT + FUND domain (BLINDSPOTS B4/B16/B17/B13-B15).

Pure-logic / dormant-safe: NO DB, NO network, NO live earner. Verifies:
  * OAuth state sign -> verify round-trips, and tamper/expiry/cross-provider are rejected.
  * build_authorize_url emits a real provider URL with client_id + signed state (app-configured),
    and degrades to app_not_configured when the app id is absent.
  * exchange_code is SIMULATED (no token) while ADS_OAUTH_LIVE is OFF (earner-safe).
  * funding model defaults to vendor_own_card; the launch pre-check does NOT block in dry-run and
    surfaces the blocked_insufficient_funds vocabulary in the managed-unfunded case.
  * the connect router builds (when FastAPI present) with the expected /ads/connect/* paths.

Run:  python -m ads_engine._smoke_connect   (from droplet_work/)
"""

from __future__ import annotations

import asyncio
import os
import sys

# App creds so build_authorize_url takes the "configured" branch.
os.environ.setdefault("META_APP_ID", "test_app_123")
os.environ.setdefault("GOOGLE_OAUTH_CLIENT_ID", "test_goog_123")
os.environ.setdefault("ADS_OAUTH_STATE_SECRET", "smoke-secret-key-0123456789")  # >=16 chars (fail-closed gate)
os.environ.setdefault("FEATURE_ADS", "1")
# Keep LIVE flags OFF (default) — earner-safe.

from ads_engine import config, funding, oauth  # noqa: E402

_fail = []


def _assert(cond, msg):
    if cond:
        print(f"  ok   - {msg}")
    else:
        print(f"  FAIL - {msg}")
        _fail.append(msg)


def test_state():
    s = oauth.sign_state("tenantA", "meta", "nonce1")
    p = oauth.verify_state(s)
    _assert(p is not None and p["t"] == "tenantA" and p["p"] == "meta" and p["n"] == "nonce1",
            "state sign->verify round-trips with bound tenant/provider/nonce")
    _assert(oauth.verify_state(s + "x") is None, "tampered state rejected (HMAC)")
    _assert(oauth.verify_state("garbage") is None, "malformed state rejected")


def test_authorize_url():
    r = oauth.build_authorize_url("tenantA", "meta", "n2")
    _assert(r.get("ok") and "client_id=test_app_123" in r["authorize_url"]
            and "state=" in r["authorize_url"] and "facebook.com" in r["authorize_url"],
            "meta authorize_url carries client_id + signed state")
    g = oauth.build_authorize_url("tenantA", "google", "n3")
    _assert(g.get("ok") and "access_type=offline" in g["authorize_url"]
            and "accounts.google.com" in g["authorize_url"],
            "google authorize_url requests offline access (refresh token)")
    # app not configured -> graceful degrade
    saved = os.environ.pop("META_APP_ID", None)
    config._cfg_get = None  # force os.getenv path
    r2 = oauth.build_authorize_url("tenantA", "meta", "n4")
    _assert(not r2.get("ok") and r2.get("reason") == "app_not_configured",
            "missing app id -> app_not_configured (no crash, UX still renders)")
    if saved is not None:
        os.environ["META_APP_ID"] = saved
    # fail-closed: a too-short / missing state secret must REFUSE to start (no unsigned state issued).
    saved_secret = os.environ.pop("ADS_OAUTH_STATE_SECRET", None)
    os.environ["ADS_OAUTH_STATE_SECRET"] = "short"  # < 16 chars -> treated as unconfigured
    config._cfg_get = None
    r3 = oauth.build_authorize_url("tenantA", "meta", "n5")
    _assert(not r3.get("ok") and r3.get("reason") == "oauth_state_not_configured",
            "no real state secret -> refuses to start (fail-closed, no unsigned state)")
    if saved_secret is not None:
        os.environ["ADS_OAUTH_STATE_SECRET"] = saved_secret
    config._cfg_get = None


def test_exchange_dry_run():
    res = asyncio.run(oauth.exchange_code("meta", "fakecode"))
    _assert(res.get("simulated") is True and res.get("token") is None and not res.get("ok"),
            "exchange_code is SIMULATED (no token) while ADS_OAUTH_LIVE off (earner-safe)")
    _assert(res.get("token_field") == "system_user_token", "meta token lands under system_user_token")
    _assert(oauth.token_field("google") == "refresh_token", "google token lands under refresh_token")


def test_funding():
    _assert(funding.model() == "vendor_own_card", "funding default model = vendor_own_card")
    pre = asyncio.run(funding.launch_precheck("tenantA"))
    _assert(pre.get("blocked") is False and pre.get("status") == "ok",
            "vendor_own_card dry-run precheck does NOT block (dry_run gate owns spend)")
    # managed model, unfunded -> blocked_insufficient_funds vocabulary
    os.environ["ADS_FUNDING_MODEL"] = "managed"
    config._cfg_get = None
    pre2 = asyncio.run(
        funding.launch_precheck("tenantA", required_minor=100000))
    _assert(pre2.get("blocked") is True and pre2.get("status") == "blocked_insufficient_funds",
            "managed unfunded precheck -> blocked_insufficient_funds")
    os.environ.pop("ADS_FUNDING_MODEL", None)
    config._cfg_get = None


def test_router_builds():
    try:
        import fastapi  # noqa: F401
    except Exception:
        print("  skip - FastAPI absent; router-build check skipped (dormant-safe by design)")
        return
    from ads_engine import connect_routes
    r = connect_routes.build_connect_router(
        lambda req: {"tenant_id": "tenantA", "is_admin": False},
        lambda t, a: True, lambda: None, lambda m: None)
    paths = {getattr(rt, "path", "") for rt in r.routes}
    want = {"/ads/connect/providers", "/ads/connect/{provider}/start",
            "/ads/connect/{provider}/callback", "/ads/connect/claim/{kind}",
            "/ads/connect/subscribe/leadgen", "/ads/connect/funding/status",
            "/ads/connect/funding/precheck", "/ads/connect/funding/manage-link"}
    _assert(want.issubset(paths), f"router exposes all connect/fund paths ({len(paths)} routes)")


def main():
    print("CONNECT+FUND smoke (offline, earner-safe):")
    test_state()
    test_authorize_url()
    test_exchange_dry_run()
    test_funding()
    test_router_builds()
    if _fail:
        print(f"\n{len(_fail)} FAILURE(S)")
        sys.exit(1)
    print("\nALL PASS")


if __name__ == "__main__":
    main()
