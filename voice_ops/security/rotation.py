"""voice_ops.security.rotation — secret-ROTATION helper for the legacy token retirement (W20).

WHAT ROTATION BUYS YOU: flipping the gate to OFF stops legacy_pw being accepted as a *bearer token*,
but a holder of the old password can still POST `/login` (caller.py:3093/3106) and mint an HMAC panel
token, UNLESS the underlying signing secret is also rotated. Full retirement therefore has two legs:
    1. gate OFF        -> legacy_pw rejected as a bearer (legacy_gate.py).
    2. ROTATE secrets  -> (a) CALLER_PASS to a fresh non-guessable value (or remove the /login
                          bare-password branch), and (b) the HMAC signing secret (`var/secret`) so
                          every token EVER derived from the old secret is invalidated at once.

This module is the helper that GENERATES the new secrets, computes the verification fingerprints, and
produces the operator-runnable plan — WITHOUT ever printing, logging, returning-in-the-clear, or
persisting a plaintext secret value anywhere. The new secret bytes are written ONLY to the rotation
result object the operator pipes straight into the secret store / .env via the runbook; their
representation in any log/report/event is a NON-reversible fingerprint + mask.

SECURITY POSTURE (mirrors voice_ops.config.vault):
  * `secrets.token_urlsafe` CSPRNG for the new value (never time/PID-seeded).
  * the value is NEVER in __repr__, __str__, logs, or the audit event — only `fingerprint`+`mask`.
  * rotating the HMAC signing secret invalidates ALL existing tokens (intended: a full logout).
  * a verify helper proves an old token no longer validates under the new secret — the runbook's
    'after' smoke — using stdlib hmac only (no droplet import).

IMPORT ISOLATION: stdlib only (secrets, hmac, hashlib, base64). ZERO droplet/caller/auth imports.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import secrets
from dataclasses import dataclass, field
from typing import Optional

log = logging.getLogger("voice_ops.security.rotation")


def _fingerprint(value: str, *, domain: str = "famit-secret") -> str:
    """Stable, NON-reversible 12-hex id of a secret — lets the UI/runbook refer to 'the new
    CALLER_PASS' WITHOUT holding the plaintext. SHA-256 truncated, domain-salted (not a rainbow
    target)."""
    t = (value or "")
    if not t:
        return ""
    return hashlib.sha256((domain + "|" + t).encode("utf-8")).hexdigest()[:12]


def _mask(value: str) -> str:
    """Masked form for any UI/log — never the full secret."""
    t = (value or "").strip()
    if len(t) <= 10:
        return (t[:2] + "…") if t else ""
    return f"{t[:3]}…{t[-3:]}"


class _Secret:
    """A wrapper whose repr/str NEVER leak the value. The plaintext is reachable ONLY via the explicit
    `.reveal()` method the runbook pipes into the secret store — so it can't be accidentally logged."""

    __slots__ = ("_v",)

    def __init__(self, v: str):
        self._v = v

    def reveal(self) -> str:
        return self._v

    def __repr__(self) -> str:
        return f"<Secret fp={_fingerprint(self._v)} masked={_mask(self._v)!r}>"

    __str__ = __repr__


@dataclass(frozen=True)
class RotationResult:
    """The output of a rotation. SAFE to log / put in a report / emit as an event: it contains only
    fingerprints + masks. The actual new bytes live behind `new_secret.reveal()` and are NEVER in
    this object's repr."""

    target: str                       # "CALLER_PASS" | "HMAC_SIGNING_SECRET"
    new_secret: _Secret = field(repr=False)
    new_fingerprint: str = ""
    new_masked: str = ""
    old_fingerprint: str = ""         # fp of the OLD value (if provided) — to prove it changed
    invalidates_all_tokens: bool = False
    note: str = ""

    def env_line(self) -> str:
        """The .env line to set — REVEALS the value because the operator pipes this into the secret
        store directly (the runbook says: never echo this to a terminal/log/chat). Kept off __repr__."""
        return f"{self.target}={self.new_secret.reveal()}"


def rotate_caller_pass(old_value: Optional[str] = None, *, nbytes: int = 24) -> RotationResult:
    """Generate a fresh, non-guessable CALLER_PASS. The old static legacy password becomes
    meaningless. Does NOT print the new value — pull it via `.new_secret.reveal()` / `.env_line()`
    in the runbook only."""
    new_v = secrets.token_urlsafe(nbytes)
    return RotationResult(
        target="CALLER_PASS",
        new_secret=_Secret(new_v),
        new_fingerprint=_fingerprint(new_v),
        new_masked=_mask(new_v),
        old_fingerprint=_fingerprint(old_value) if old_value else "",
        invalidates_all_tokens=False,
        note=("rotates the static password so the legacy literal no longer authenticates "
              "ANYTHING; pair with gate=OFF. Distribute via the secret store, never via chat/log."),
    )


def rotate_hmac_signing_secret(old_value: Optional[str] = None, *, nbytes: int = 32) -> RotationResult:
    """Generate a fresh HMAC signing secret (the `var/secret` panel tokens are signed with). Rotating
    this INVALIDATES every existing panel/HMAC token — including any minted from the old password via
    /login — at the cost of logging everyone out (intended for a full retirement)."""
    new_v = base64.urlsafe_b64encode(secrets.token_bytes(nbytes)).decode("ascii").rstrip("=")
    return RotationResult(
        target="HMAC_SIGNING_SECRET",
        new_secret=_Secret(new_v),
        new_fingerprint=_fingerprint(new_v),
        new_masked=_mask(new_v),
        old_fingerprint=_fingerprint(old_value) if old_value else "",
        invalidates_all_tokens=True,
        note=("rotating the HMAC signing secret invalidates ALL existing panel/HMAC tokens at once "
              "(full logout) — this is what closes the /login residual after gate=OFF."),
    )


# --------------------------------------------------------------------------- #
# verification helpers for the runbook 'before/after' smoke (stdlib hmac only)
# --------------------------------------------------------------------------- #
def hmac_token(payload: str, secret: str) -> str:
    """The same HMAC-SHA256 shape a stateless panel token uses (hexdigest over payload). Used by the
    rotation verify to demonstrate that an old token does NOT validate under the new secret."""
    return hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()


def token_valid_under(payload: str, token: str, secret: str) -> bool:
    """Constant-time check that `token` is a valid HMAC of `payload` under `secret`."""
    return hmac.compare_digest(hmac_token(payload, secret), token or "")


def verify_rotation_invalidates(payload: str, old_secret: str, new_secret: str) -> bool:
    """Proof for the runbook: a token signed by the OLD secret must FAIL under the NEW secret, and a
    freshly-signed token under the NEW secret must pass. Returns True iff rotation truly invalidated
    the old token (the property the 'after' smoke asserts)."""
    old_token = hmac_token(payload, old_secret)
    old_still_valid = token_valid_under(payload, old_token, new_secret)
    new_token = hmac_token(payload, new_secret)
    new_valid = token_valid_under(payload, new_token, new_secret)
    return (not old_still_valid) and new_valid
