"""voice_ops.gcal.oauth — Google Calendar OAuth 2.0 server-side flow (TRACKED, dormant-safe).

The vendor connects their Google Calendar ONCE from the panel. This module owns the three
server-side steps (research §B):

  1. `authorization_url(org_id)` — the consent URL the vendor visits. access_type=offline +
     prompt=consent => Google returns a long-lived REFRESH TOKEN; a signed `state` carries the
     tenant id + a CSRF nonce so the callback can verify it came from us and bind the result to
     the right tenant.
  2. `exchange_code(org_id, code, state)` — the callback handler: verify state, POST the code to
     Google's token endpoint, get {access_token, refresh_token, expires_in}, ENCRYPT the refresh
     token (vault) and persist it under the tenant. The refresh token is the only thing stored;
     access tokens are short-lived and re-minted on demand.
  3. `refresh(org_id)` — mint a fresh access token from the stored refresh token. On Google
     `invalid_grant` (token revoked / expired) it flips the vault row to 'revoked' so the panel
     prompts a reconnect (the reconnect-on-expiry requirement).

DORMANT-SAFE: with no client id/secret every entry point returns {"status":"not_configured"} and
NEVER hits the network. HTTP is via the stdlib `urllib` (lazy import) — no new dependency, no
google SDK required for the OAuth dance. `state` is HMAC-signed with the platform master secret.

NEVER logs tokens. The access token is returned transiently to the immediate caller (sync) only.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import time
import urllib.parse
from typing import Optional

from . import vault
from .config import GCalConfig

log = logging.getLogger("voice_ops.gcal.oauth")

_NOT_CONFIGURED = {"status": "not_configured", "reason": "calendar_not_configured"}
_STATE_TTL_S = 600  # the consent round-trip must complete within 10 minutes


def _state_secret() -> str:
    for env in ("FAMIT_KEYSTORE_SECRET", "PROVIDER_KEYSTORE_SECRET", "GCAL_VAULT_SECRET"):
        v = (os.environ.get(env) or "").strip()
        if v:
            return v
    return ""


def _sign_state(org_id: str, nonce: str, issued_at: int) -> str:
    """HMAC-SHA256 over (org|nonce|issued_at). Returns a compact urlsafe state string."""
    secret = _state_secret()
    payload = f"{org_id}|{nonce}|{issued_at}"
    sig = hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()[:32]
    raw = json.dumps({"o": org_id, "n": nonce, "t": issued_at, "s": sig}, separators=(",", ":"))
    return urllib.parse.quote(raw)


def _verify_state(state: str) -> Optional[str]:
    """Verify a returned state -> the org_id it was minted for, or None (invalid/expired/forged)."""
    try:
        raw = urllib.parse.unquote(state or "")
        d = json.loads(raw)
        org_id, nonce, issued_at, sig = d["o"], d["n"], int(d["t"]), d["s"]
    except Exception:  # noqa: BLE001
        return None
    if (int(time.time()) - issued_at) > _STATE_TTL_S:
        return None
    expect = hmac.new(_state_secret().encode("utf-8"),
                      f"{org_id}|{nonce}|{issued_at}".encode("utf-8"),
                      hashlib.sha256).hexdigest()[:32]
    if not hmac.compare_digest(expect, sig):
        return None
    return org_id


class GoogleOAuth:
    """Stateless OAuth orchestrator. Construct with a GCalConfig (defaults from env)."""

    def __init__(self, cfg: Optional[GCalConfig] = None):
        self.cfg = cfg or GCalConfig.from_env()

    # ----------------------------------------------------- step 1: URL #
    def authorization_url(self, org_id: str) -> dict:
        """Build the consent URL for a tenant. Dormant-safe (not_configured when no client)."""
        if not self.cfg.client_ready:
            return dict(_NOT_CONFIGURED)
        if not (org_id or "").strip():
            return {"status": "error", "reason": "empty_org_id"}
        nonce = hashlib.sha256(os.urandom(16)).hexdigest()[:16]
        state = _sign_state(org_id, nonce, int(time.time()))
        params = {
            "client_id": self.cfg.client_id,
            "redirect_uri": self.cfg.redirect_uri,
            "response_type": "code",
            "scope": self.cfg.scope,
            "access_type": "offline",       # => refresh token
            "prompt": "consent",            # force consent so a refresh token is always returned
            "include_granted_scopes": "true",
            "state": state,
        }
        url = self.cfg.auth_endpoint + "?" + urllib.parse.urlencode(params)
        return {"status": "ok", "url": url, "state": state}

    # ------------------------------------------ step 2: code exchange #
    def exchange_code(self, code: str, state: str, *, is_admin: bool = False) -> dict:
        """Callback handler: verify state, exchange the code, store the encrypted refresh token.

        Returns {status:'ok', org_id, account_email} or an error. Dormant-safe; NEVER returns a
        token. The org_id is taken from the verified state, NOT from any caller-supplied body —
        a forged state cannot bind a connection to another tenant."""
        if not self.cfg.client_ready:
            return dict(_NOT_CONFIGURED)
        org_id = _verify_state(state)
        if not org_id:
            return {"status": "error", "reason": "bad_state"}
        if not (code or "").strip():
            return {"status": "error", "reason": "missing_code"}
        try:
            tok = self._post_token({
                "code": code,
                "client_id": self.cfg.client_id,
                "client_secret": self.cfg.client_secret,
                "redirect_uri": self.cfg.redirect_uri,
                "grant_type": "authorization_code",
            })
        except Exception as exc:  # noqa: BLE001
            log.info("gcal code exchange failed: %r", exc)
            return {"status": "error", "reason": "token_exchange_failed"}
        refresh_token = tok.get("refresh_token", "")
        if not refresh_token:
            # No refresh token => the user previously consented without prompt=consent. We forced
            # prompt=consent so this is rare; surface it so the panel re-runs the flow.
            return {"status": "error", "reason": "no_refresh_token",
                    "detail": "re-run consent (prompt=consent) to obtain a refresh token"}
        account_email = self._extract_email(tok)
        try:
            blob = vault.encrypt_token(org_id, refresh_token, key_version=self.cfg.key_version)
        except vault.VaultError as exc:
            log.info("gcal token encrypt failed: %r", exc)
            return {"status": "error", "reason": "vault_unavailable"}
        saved = vault.upsert_blob(org_id, blob, account_email=account_email, is_admin=is_admin)
        if saved.get("status") not in ("ok",):
            return {"status": "error", "reason": saved.get("reason", "store_failed")}
        return {"status": "ok", "org_id": org_id, "account_email": account_email}

    # ------------------------------------------------ step 3: refresh #
    def refresh(self, org_id: str, *, is_admin: bool = False) -> dict:
        """Mint a fresh ACCESS token from the stored refresh token. Returns
        {status:'ok', access_token, expires_in} (transient — not stored) or an error.

        On Google invalid_grant (revoked/expired refresh token) flips the vault row to 'revoked'
        so the panel prompts the vendor to reconnect (reconnect-on-expiry)."""
        if not self.cfg.client_ready:
            return dict(_NOT_CONFIGURED)
        row = vault.read_blob(org_id, is_admin=is_admin)
        if row is None:
            return {"status": "not_connected", "reason": "no_stored_token"}
        if row.get("status") == "revoked":
            return {"status": "revoked", "reason": "reconnect_required"}
        try:
            refresh_token = vault.decrypt_token(org_id, row["ciphertext"], row["key_version"])
        except Exception as exc:  # noqa: BLE001
            log.info("gcal token decrypt failed (tamper/key): %r", exc)
            return {"status": "error", "reason": "decrypt_failed"}
        try:
            tok = self._post_token({
                "refresh_token": refresh_token,
                "client_id": self.cfg.client_id,
                "client_secret": self.cfg.client_secret,
                "grant_type": "refresh_token",
            })
        except _TokenError as exc:
            if exc.invalid_grant:
                vault.set_status(org_id, "revoked", is_admin=is_admin)
                return {"status": "revoked", "reason": "reconnect_required"}
            return {"status": "error", "reason": "refresh_failed", "detail": str(exc)[:120]}
        except Exception as exc:  # noqa: BLE001
            log.info("gcal refresh failed: %r", exc)
            return {"status": "error", "reason": "refresh_failed"}
        return {"status": "ok", "access_token": tok.get("access_token", ""),
                "expires_in": int(tok.get("expires_in", 0) or 0),
                "calendar_id": row.get("calendar_id", "primary")}

    # --------------------------------------------------------- helpers #
    def _post_token(self, form: dict) -> dict:
        """POST to Google's token endpoint via stdlib urllib (lazy). Raises _TokenError on a 4xx
        with the parsed error (so refresh can detect invalid_grant). Test seam: overridable."""
        import urllib.request

        data = urllib.parse.urlencode(form).encode("utf-8")
        req = urllib.request.Request(self.cfg.token_endpoint, data=data, method="POST",
                                     headers={"Content-Type": "application/x-www-form-urlencoded"})
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:  # nosec - fixed Google endpoint
                body = resp.read().decode("utf-8")
            return json.loads(body)
        except urllib.error.HTTPError as exc:  # type: ignore[attr-defined]
            try:
                err = json.loads(exc.read().decode("utf-8"))
            except Exception:  # noqa: BLE001
                err = {}
            raise _TokenError(err.get("error", "http_error"),
                              invalid_grant=(err.get("error") == "invalid_grant")) from exc

    @staticmethod
    def _extract_email(tok: dict) -> str:
        """Best-effort: decode the id_token (if present) for the account email. NEVER raises."""
        idt = tok.get("id_token", "")
        if not idt or idt.count(".") != 2:
            return ""
        try:
            import base64
            payload = idt.split(".")[1]
            payload += "=" * (-len(payload) % 4)
            claims = json.loads(base64.urlsafe_b64decode(payload).decode("utf-8"))
            return str(claims.get("email", ""))
        except Exception:  # noqa: BLE001
            return ""


class _TokenError(RuntimeError):
    def __init__(self, msg: str, *, invalid_grant: bool = False):
        super().__init__(msg)
        self.invalid_grant = invalid_grant
