"""voice_ops.security.keys.purpose — the KEY-PURPOSE vocabulary (W23, TRACKED, droplet-free).

THE W23 FINDING (design/control-security.md:327-329 + the W18 sweep): ONE shared signing secret
(`var/secret`) currently signs FOUR distinct token families with the SAME key —

    family                         minted at                       (the live seam)
    ----------------------------   -----------------------------   -------------------------------
    legacy HMAC panel token        caller.py `_make_token()`       caller.py:622-623
    JWT access token  (HS256)      auth.py  `_make_access()`       auth.py:104-115
    JWT refresh token (HS256)      auth.py  `_make_refresh()`      auth.py:118-126   (opaque id today)
    firewall step-up token         firewall.py `mint_step_up()`    firewall.py:267-274
    provider-reveal step-up token  firewall.py `mint_reveal_*()`   firewall.py:419-434

All resolve `_SECRET` = `SECRET` loaded once at caller.py:584 and handed identically to
`auth.init(secret=SECRET)` (caller.py:1062) and `firewall.init(secret=SECRET)` (caller.py:1085).

WHY THAT IS A VULNERABILITY: a single key for all purposes means a leak (or forgery capability) in
ONE family is a leak in ALL of them. Anyone who can sign a step-up token can also sign an access JWT
and a legacy HMAC bearer. The CONTAINMENT property W23 buys: split the key by PURPOSE so that
"I can sign a step-up token" does NOT imply "I can forge an access JWT" — a step-up-key compromise
is contained to the step-up surface.

This module is the CLOSED ENUM of purposes + the load-bearing invariant they encode. It carries NO
secret material — only the *name* of each key purpose and its domain-separation label. `import` pulls
pure stdlib, ZERO droplet/caller/auth/firewall, ZERO crypto.

The actual per-purpose key derivation + sign/verify live in keyring.py; this file is the vocabulary
both that module and the patch DOC (design/W-SEC-keys-SEAM.md) pin to 1:1.
"""
from __future__ import annotations

import enum


class KeyPurpose(str, enum.Enum):
    """WHAT a key is allowed to sign/protect. Closed set — every signer in the platform must name
    exactly one. The string value is the domain-separation label fed into the key-derivation HKDF
    `info` so two purposes ALWAYS derive different bytes from the same master."""

    JWT_ACCESS = "jwt-access"          # auth.py access JWT (HS256, 15-min TTL, sub/role/is_admin/jti)
    JWT_REFRESH = "jwt-refresh"        # auth.py refresh token signing (distinct from access)
    LEGACY_HMAC = "legacy-hmac"        # caller.py `tenant_id.hmac` panel token — to be RETIRED (W20)
    STEP_UP = "step-up"                # firewall.py generic PIN/OTP step-up token (scope-bound)
    REVEAL_STEP_UP = "reveal-step-up"  # firewall.py single-use provider-reveal step-up (aud-bound)
    SERVICE = "service"                # short-lived scoped inter-service token (AIM/cron/Hatchet loop)

    @property
    def label(self) -> str:
        """The domain-separation label. NEVER reuse one label for two purposes — that would collapse
        the split."""
        return self.value

    @property
    def is_privileged(self) -> bool:
        """Step-up / reveal / service keys gate money + secret-reveal + cross-service calls. A leak of
        one of these is higher-blast-radius than an access key — flagged so the runbook prioritises
        their rotation."""
        return self in (KeyPurpose.STEP_UP, KeyPurpose.REVEAL_STEP_UP, KeyPurpose.SERVICE)


# The exact live seam each purpose maps to — used by the patch DOC + tests so the split lands 1:1 on
# the real signers. file:line refs are documentation, never imported.
LIVE_SEAM = {
    KeyPurpose.JWT_ACCESS: "auth.py:_make_access (104-115) / resolve_token (153) / access_claims (169)",
    KeyPurpose.JWT_REFRESH: "auth.py:_make_refresh (118-126)",
    KeyPurpose.LEGACY_HMAC: "caller.py:_make_token (622-623)  [W20-retired]",
    KeyPurpose.STEP_UP: "firewall.py:mint_step_up (267-274) / verify_step_up_token (284) / require_step_up (329)",
    KeyPurpose.REVEAL_STEP_UP: "firewall.py:mint_reveal_step_up (419-434) / verify (453)",
    KeyPurpose.SERVICE: "NEW — no live signer yet; this module IS the signer (service_tokens.py)",
}

# The purposes that today collide on the single `var/secret`. Splitting these is the whole point of
# W23. (REFRESH is opaque-random today, not HS256-signed, so it does not strictly collide — but it
# gets its own purpose for when it becomes a signed JWT.)
COLLIDING_TODAY = (
    KeyPurpose.JWT_ACCESS,
    KeyPurpose.LEGACY_HMAC,
    KeyPurpose.STEP_UP,
    KeyPurpose.REVEAL_STEP_UP,
)


def all_purposes() -> tuple[KeyPurpose, ...]:
    return tuple(KeyPurpose)
