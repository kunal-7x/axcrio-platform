"""ads_engine.oauth — Meta Login-for-Business + Google OAuth2 connect handshake (BLINDSPOTS B4).

The vendor clicks "Connect with Meta / Google"; the engine builds a provider authorize URL, the
vendor authenticates in Meta/Google, and the provider redirects back to our callback with a `code`.
The callback exchanges the code for a long-lived token (Meta System-User token / Google refresh
token) and LANDS it straight into the per-tenant vault blob (`vault_adapter.write_channel_blob`) —
so the vendor never hand-mints or pastes a token.

EARNER-SAFE + OFFLINE-TESTABLE by construction:
  * NOTHING here spends money or touches the live earner (agent.py/voice untouched).
  * The real token exchange (network) runs ONLY when `ADS_OAUTH_LIVE` is ON *and* httpx + the app
    creds (client id/secret) are present. Otherwise `exchange_code` returns a SIMULATED, clearly-
    flagged result (`simulated=True`, NO token) so the whole flow is testable offline and never
    fabricates a credential into the vault.
  * `state` is HMAC-signed (ADS_OAUTH_STATE_SECRET) and single-use (the route consumes a stored
    nonce) — CSRF + replay safe. The tenant is recovered from the SIGNED state on the callback
    (the browser redirect carries no auth header), never from a query param.

This module is pure logic (URL build + state sign/verify + best-effort token POST). The route
(`connect_routes.py`) owns auth, nonce storage/consume, and the vault write.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import time
import uuid
from typing import Any, Optional

from . import config

_log = logging.getLogger("ads_engine.oauth")

# --------------------------------------------------------------------------- provider matrix
# field = the vault blob key the minted token lands under (vault-connectors.md §1.2 / §4).
_PROVIDERS = {
    "meta": {
        "channel": "meta",
        "authorize_url": "https://www.facebook.com/{version}/dialog/oauth",
        "token_url": "https://graph.facebook.com/{version}/oauth/access_token",
        "scopes": "ads_management,leads_retrieval,pages_show_list,pages_manage_metadata,business_management",
        "token_field": "system_user_token",
        "client_id_key": "META_APP_ID",
        "client_secret_key": "META_APP_SECRET",
        # Login-for-Business uses a `config_id` (a saved business-login configuration) instead of scopes.
        "config_id_key": "META_LOGIN_CONFIG_ID",
    },
    "google": {
        "channel": "google",
        "authorize_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "https://oauth2.googleapis.com/token",
        "scopes": "https://www.googleapis.com/auth/adwords",
        "token_field": "refresh_token",
        "client_id_key": "GOOGLE_OAUTH_CLIENT_ID",
        "client_secret_key": "GOOGLE_OAUTH_CLIENT_SECRET",
        "config_id_key": "",
    },
}

_STATE_TTL_S = 600  # a connect handshake must complete within 10 minutes


def is_supported(provider: str) -> bool:
    return (provider or "").strip().lower() in _PROVIDERS


def supported_providers() -> list:
    return list(_PROVIDERS.keys())


def token_field(provider: str) -> str:
    return _PROVIDERS.get((provider or "").strip().lower(), {}).get("token_field", "")


def live_enabled() -> bool:
    """The real network token-exchange path is armed (flag ON). Default OFF (earner-safe)."""
    return config._flag("ADS_OAUTH_LIVE", "0")


def _cfg(key: str, default: str = "") -> str:
    try:
        return str(config.cfg(key, default) or default)
    except Exception:  # noqa: BLE001
        return default


_MIN_SECRET_LEN = 16  # a real signing key; below this we treat state as UNCONFIGURED (fail-closed).


def _state_secret() -> bytes | None:
    """The HMAC key for the OAuth `state`. FAIL-CLOSED (routes-auth / isolation CRIT-1 standard): we
    NEVER fall back to an in-source literal — a hardcoded key would let an attacker forge `state` and
    bind a victim tenant to the attacker's authorization code (ad-channel takeover). Returns the key
    bytes ONLY when a real >=16-char secret is configured, else None. The minter
    (build_authorize_url) then refuses to start the flow (reason=oauth_state_not_configured) and the
    verifier (verify_state) returns None, exactly like the firewall/form-token fail-closed posture."""
    s = (_cfg("ADS_OAUTH_STATE_SECRET") or _cfg("SECRET_KEY") or _cfg("JWT_SECRET") or "").strip()
    if len(s) < _MIN_SECRET_LEN:
        return None
    return s.encode("utf-8")


def state_configured() -> bool:
    """True iff a real OAuth-state signing secret is present (the flow can be started safely)."""
    return _state_secret() is not None


def redirect_uri(provider: str) -> str:
    """The provider redirect target. Single-sourced off ADS_OAUTH_REDIRECT_BASE so it matches the
    URI allow-listed in the Meta/Google app console (a mismatch is the #1 OAuth failure)."""
    base = _cfg("ADS_OAUTH_REDIRECT_BASE", "https://panel.famit.in/api").rstrip("/")
    return f"{base}/ads/connect/{provider}/callback"


# --------------------------------------------------------------------------- state (CSRF + bind)
def sign_state(tenant_id: str, provider: str, nonce: str) -> str:
    """Opaque, tamper-evident state: base64url(payload).hmac. Binds tenant+provider+nonce+exp.

    Returns "" when no real signing secret is configured (fail-closed): an UNSIGNED state must never
    be issued — the caller treats "" as oauth_state_not_configured and refuses to start the flow."""
    secret = _state_secret()
    if secret is None:
        return ""
    payload = {
        "t": tenant_id, "p": (provider or "").lower(), "n": nonce,
        "exp": int(time.time()) + _STATE_TTL_S,
    }
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    body = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
    sig = hmac.new(secret, body.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{body}.{sig}"


def verify_state(state: str) -> Optional[dict]:
    """Verify the HMAC + expiry. Returns the payload {t,p,n,exp} or None. NEVER raises. The route
    must ALSO consume the stored nonce (single-use) to defeat replay."""
    secret = _state_secret()
    if secret is None:  # fail-closed: no real key => no state can be trusted (CRIT-1 standard).
        return None
    try:
        body, sig = str(state or "").split(".", 1)
    except ValueError:
        return None
    try:
        expected = hmac.new(secret, body.encode("ascii"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, sig):
            return None
        pad = "=" * (-len(body) % 4)
        payload = json.loads(base64.urlsafe_b64decode(body + pad))
        if not isinstance(payload, dict):
            return None
        if int(payload.get("exp", 0) or 0) < int(time.time()):
            return None
        return payload
    except Exception:  # noqa: BLE001
        return None


def new_nonce() -> str:
    return uuid.uuid4().hex


# --------------------------------------------------------------------------- authorize URL
def build_authorize_url(tenant_id: str, provider: str, nonce: str) -> dict:
    """Return { ok, authorize_url, state, redirect_uri, reason }. `reason=app_not_configured` when
    the Meta/Google app client_id is absent (founder must register the app first) — the UX still
    renders, just disabled. NEVER raises."""
    p = (provider or "").strip().lower()
    cfgp = _PROVIDERS.get(p)
    if not cfgp:
        return {"ok": False, "reason": "unsupported_provider"}
    client_id = _cfg(cfgp["client_id_key"])
    ruri = redirect_uri(p)
    state = sign_state(tenant_id, p, nonce)
    if not state:
        # FAIL-CLOSED: no real ADS_OAUTH_STATE_SECRET => we will NOT issue an unsigned state (a
        # forgeable state is an ad-channel-takeover vector). The UX renders disabled until configured.
        return {"ok": False, "reason": "oauth_state_not_configured", "redirect_uri": ruri}
    if not client_id:
        return {"ok": False, "reason": "app_not_configured", "state": state, "redirect_uri": ruri}
    version = getattr(config, "META_API_VERSION", "v25.0")
    base = cfgp["authorize_url"].format(version=version)
    params = {
        "client_id": client_id,
        "redirect_uri": ruri,
        "state": state,
        "response_type": "code",
    }
    if p == "meta":
        cfg_id = _cfg(cfgp["config_id_key"])
        if cfg_id:
            # Login-for-Business: a saved config drives the permission set.
            params["config_id"] = cfg_id
            params["override_default_response_type"] = "true"
        else:
            params["scope"] = cfgp["scopes"]
    else:  # google — refresh-token flow needs offline access + consent prompt.
        params["scope"] = cfgp["scopes"]
        params["access_type"] = "offline"
        params["prompt"] = "consent"
        params["include_granted_scopes"] = "true"
    from urllib.parse import urlencode
    return {"ok": True, "authorize_url": f"{base}?{urlencode(params)}", "state": state,
            "redirect_uri": ruri, "reason": "ok"}


# --------------------------------------------------------------------------- code -> token
async def exchange_code(provider: str, code: str) -> dict:
    """Exchange an authorization `code` for a long-lived token.

    Returns { ok, token, token_field, simulated, reason }. SECRET note: `token` is returned ONLY to
    the in-process route, which immediately writes it to the vault and NEVER echoes it to the client.

    LIVE path (ADS_OAUTH_LIVE + httpx + app creds) does the real provider token POST. Otherwise a
    SIMULATED result (simulated=True, token=None, reason="dry_run") — so the handshake is fully
    offline-testable and a missing flag/creds can NEVER fabricate a credential. NEVER raises."""
    p = (provider or "").strip().lower()
    cfgp = _PROVIDERS.get(p)
    if not cfgp:
        return {"ok": False, "simulated": False, "reason": "unsupported_provider", "token": None,
                "token_field": ""}
    field = cfgp["token_field"]
    client_id = _cfg(cfgp["client_id_key"])
    client_secret = _cfg(cfgp["client_secret_key"])
    if not live_enabled():
        return {"ok": False, "simulated": True, "reason": "dry_run", "token": None,
                "token_field": field}
    if not (client_id and client_secret and code):
        return {"ok": False, "simulated": False, "reason": "app_not_configured", "token": None,
                "token_field": field}
    try:
        import httpx  # noqa: F401
    except Exception:  # noqa: BLE001
        return {"ok": False, "simulated": True, "reason": "httpx_unavailable", "token": None,
                "token_field": field}
    version = getattr(config, "META_API_VERSION", "v25.0")
    ruri = redirect_uri(p)
    try:
        import httpx
        async with httpx.AsyncClient(timeout=20.0) as client:
            if p == "meta":
                url = cfgp["token_url"].format(version=version)
                resp = await client.get(url, params={
                    "client_id": client_id, "client_secret": client_secret,
                    "redirect_uri": ruri, "code": code})
                data = resp.json() if resp.status_code < 500 else {}
                tok = (data or {}).get("access_token")
                if resp.status_code == 200 and tok:
                    # NOTE (founder-gate): a short-lived user token is returned here; the production
                    # flow then mints a long-lived System-User token via the Business API. We persist
                    # what the exchange returns; the long-lived swap is documented in remaining[].
                    return {"ok": True, "simulated": False, "reason": "ok", "token": str(tok),
                            "token_field": field}
            else:  # google
                resp = await client.post(cfgp["token_url"], data={
                    "client_id": client_id, "client_secret": client_secret,
                    "redirect_uri": ruri, "code": code, "grant_type": "authorization_code"})
                data = resp.json() if resp.status_code < 500 else {}
                tok = (data or {}).get("refresh_token")
                if resp.status_code == 200 and tok:
                    return {"ok": True, "simulated": False, "reason": "ok", "token": str(tok),
                            "token_field": field}
        return {"ok": False, "simulated": False, "reason": "exchange_failed", "token": None,
                "token_field": field}
    except Exception as exc:  # noqa: BLE001 — never raise into the route
        _log.warning("ads_engine.oauth.exchange_code(%s) failed: %r", p, type(exc).__name__)
        return {"ok": False, "simulated": False, "reason": "transport_error", "token": None,
                "token_field": field}
