"""voice_ops.security.keys.service_tokens — short-lived SCOPED inter-service tokens (W23).

THE GAP THIS CLOSES: inter-service calls today (AIM loopback, the retry/callback scheduler, Hatchet
worker -> caller.py) ride either the legacy static password or a long-lived bearer — a stolen one is
a permanent skeleton key across services. W23 replaces that with tokens that are:

  * PURPOSE-SCOPED  — signed under the SERVICE-purpose key only (keyring), so a leaked access/step-up
    key can't mint one and a leaked service key can't forge an access JWT.
  * SHORT-LIVED     — default 120s TTL (caller picks; capped at MAX_TTL). A stolen token dies fast.
  * AUDIENCE-BOUND  — `aud` names the ONE service allowed to accept it (e.g. "caller", "hatchet");
    presenting it to a different service fails (defence against a confused-deputy replay).
  * ACTION-SCOPED   — `scope` names the narrow capability (e.g. "dial", "schedule.enqueue"); the
    receiver checks the scope, so a token minted for one job can't drive another.
  * SINGLE-ISSUER   — `iss` names the minting service for audit.
  * REPLAY-CAPPED   — `jti` (random) lets a receiver optionally dedupe within the short TTL window.

This is a self-contained JWT-shape token (header.payload.mac) signed via the keyring's HMAC-SHA256
under KeyPurpose.SERVICE — it does NOT import PyJWT (keeps the module droplet/SDK-free) but is
verifiable by anyone holding the SERVICE key. The token NEVER carries a secret; claims are minimal.

SECURITY: verify is fail-closed (bad sig / wrong aud / wrong scope / expired / not-yet-valid / wrong
purpose-key all -> None). No plaintext secret ever in a claim, log, or repr.

IMPORT ISOLATION: stdlib only (json, time, base64, secrets) + keyring (stdlib-only). ZERO droplet.
"""
from __future__ import annotations

import base64
import json
import logging
import secrets
import time
from dataclasses import dataclass
from typing import Optional

from .keyring import Keyring
from .purpose import KeyPurpose

log = logging.getLogger("voice_ops.security.keys.service_tokens")

DEFAULT_TTL_SECONDS = 120
MAX_TTL_SECONDS = 600          # hard ceiling — an inter-service token must be short-lived
_CLOCK_SKEW = 30               # tolerated clock skew on nbf/exp


def _b64u(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64u_decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


class ServiceTokenError(ValueError):
    """A malformed mint request (empty aud/scope, TTL over the ceiling). NEVER carries key material."""


@dataclass(frozen=True)
class ServiceClaims:
    """The verified claims of an inter-service token — the RESULT of verify, never the secret."""

    iss: str
    aud: str
    scope: str
    sub: str          # the acting tenant/context, if any (may be "" for a tenant-agnostic job)
    jti: str
    iat: int
    exp: int

    def __repr__(self) -> str:  # safe-to-log
        return f"ServiceClaims(iss={self.iss!r}, aud={self.aud!r}, scope={self.scope!r}, sub={self.sub!r})"


def mint_service_token(
    keyring: Keyring,
    *,
    issuer: str,
    audience: str,
    scope: str,
    subject: str = "",
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
    version: Optional[int] = None,
) -> str:
    """Mint a short-lived, scoped, audience-bound inter-service token signed under the SERVICE key.

    Raises ServiceTokenError on empty issuer/audience/scope (fail-closed — no unscoped tokens) or a
    TTL over MAX_TTL_SECONDS. NEVER logs the token or any key bytes."""
    if not (issuer or "").strip():
        raise ServiceTokenError("issuer required (fail-closed — no anonymous service token)")
    if not (audience or "").strip():
        raise ServiceTokenError("audience required (fail-closed — a service token must name its target)")
    if not (scope or "").strip():
        raise ServiceTokenError("scope required (fail-closed — no unscoped/blanket service token)")
    ttl = int(ttl_seconds)
    if ttl <= 0:
        raise ServiceTokenError("ttl must be positive")
    if ttl > MAX_TTL_SECONDS:
        raise ServiceTokenError(f"ttl {ttl}s exceeds the {MAX_TTL_SECONDS}s ceiling for inter-service tokens")
    now = int(time.time())
    header = {"alg": "HS256", "typ": "svc", "kid": KeyPurpose.SERVICE.label}
    payload = {
        "iss": issuer.strip(),
        "aud": audience.strip(),
        "scope": scope.strip(),
        "sub": (subject or "").strip(),
        "jti": secrets.token_urlsafe(9),
        "iat": now,
        "nbf": now - _CLOCK_SKEW,
        "exp": now + ttl,
        "purpose": KeyPurpose.SERVICE.label,
    }
    h = _b64u(json.dumps(header, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    p = _b64u(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    signing_input = f"{h}.{p}"
    mac = keyring.sign(KeyPurpose.SERVICE, signing_input, version=version)
    return f"{signing_input}.{mac}"


def verify_service_token(
    keyring: Keyring,
    token: str,
    *,
    expected_audience: str,
    required_scope: str,
    version: Optional[int] = None,
    now: Optional[int] = None,
) -> Optional[ServiceClaims]:
    """Verify an inter-service token. Returns ServiceClaims iff: signature valid under the SERVICE key,
    aud == expected_audience, scope == required_scope, and now within [nbf-skew, exp]. Otherwise None
    (fail-closed). A token signed under any OTHER purpose key fails the signature check here — that is
    the W23 containment property in action."""
    if not token or token.count(".") != 2:
        return None
    h, p, mac = token.split(".")
    signing_input = f"{h}.{p}"
    # 1) signature under the SERVICE purpose key (NOT access/step-up — wrong key => reject)
    if not keyring.verify(KeyPurpose.SERVICE, signing_input, mac, version=version):
        return None
    # 2) decode claims
    try:
        payload = json.loads(_b64u_decode(p).decode("utf-8"))
    except Exception:  # noqa: BLE001
        return None
    if payload.get("purpose") != KeyPurpose.SERVICE.label:
        return None
    t = int(now if now is not None else time.time())
    # 3) temporal
    if t + _CLOCK_SKEW < int(payload.get("nbf", 0)):
        return None
    if t - _CLOCK_SKEW >= int(payload.get("exp", 0)):
        return None
    # 4) audience + scope binding (confused-deputy / over-broad-scope defence)
    if (payload.get("aud") or "") != (expected_audience or "").strip():
        return None
    if (payload.get("scope") or "") != (required_scope or "").strip():
        return None
    return ServiceClaims(
        iss=payload.get("iss", ""),
        aud=payload.get("aud", ""),
        scope=payload.get("scope", ""),
        sub=payload.get("sub", ""),
        jti=payload.get("jti", ""),
        iat=int(payload.get("iat", 0)),
        exp=int(payload.get("exp", 0)),
    )
