"""voice_ops.security — W20 LEGACY STATIC-TOKEN RETIREMENT (TRACKED, droplet-free).

The W18/MD1 finding (per design/control-security.md #1): the legacy static password
(`CALLER_PASS`) is a PERMANENT, UN-REVOCABLE bearer token. It authenticates EVERY vendor route
platform-wide, so every new W8–W16 operational route is BORN reachable by it.

RETIREMENT — TWO LEGS (do NOT conflate; this is the honest invariant):
  1. gate OFF  -> retires the password as a DIRECT BEARER token on resolve_tenant AND on the
     password-minting /auth/login + /login paths (so OFF stops new privileged tokens being minted
     from the legacy password). Flag-gated + reversible.
  2. ROTATE the HMAC signing SECRET (Phase 3) -> the ONLY thing that invalidates already-minted
     HMAC/panel tokens (incl. any minted from the legacy password before the flip). The credential
     is FULLY retired only AFTER this rotation — OFF alone does not reach existing hmac tokens.
This GATES the safe deploy of the operational route surface. Plus: rotate CALLER_PASS, scrub docs.

This package is the disjoint, tracked, CI-importable implementation of that retirement:

  principal.py          The auth-RESULT vocabulary — AuthMethod (jwt/logto/service/legacy_pw/none) +
                        Principal (the verdict, never the credential). Names the decision caller.py
                        does inline so it's testable + patchable 1:1.

  legacy_gate.py        THE rejection layer + the LEGACY_TOKEN_ENABLED / LEGACY_TOKEN_MODE gate
                        (library default OFF). evaluate()/enforce(): real auth always passes; legacy_pw
                        is rejected at mode OFF, allowed-but-audited (deprecated) at TRANSITION, and
                        always excluded from /admin/*. Deprecation use emits a fail-soft W8 fact.

  route_auth_assert.py  The executable invariant: every NEW W8–W16 operational route requires real
                        tenant auth (resolve_tenant) and NEVER accepts legacy_pw. Ships the W8–W16
                        route manifest as the regression pin + the legacy-reachable route list.

  rotation.py           Secret-ROTATION helper (CSPRNG) — generates a fresh CALLER_PASS + a fresh HMAC
                        signing secret, NEVER printing/logging/persisting the plaintext (only
                        fingerprint+mask), plus the 'old token no longer validates' verify for the
                        runbook's after-smoke.

  docs_scrub.py         The docs-scrub target list (paths + actions) — by reference + fingerprint,
                        NEVER reproducing the secret literal.

caller.py / auth.py are NOT edited here — their changes ship as a PATCH DOC (PATCH-caller-auth.md) and
the gated-flip runbook (design/W20-LEGACY-TOKEN-RETIREMENT.md).

IMPORT ISOLATION: `import voice_ops.security` pulls ZERO droplet_work, ZERO caller.py/auth.py, ZERO
heavy SDK at module load. The single W8 event factory used by the gate is imported LAZILY inside the
emit path. Safe on any host / in CI.
"""
from __future__ import annotations

from . import docs_scrub, legacy_gate, principal, rotation, route_auth_assert
from .docs_scrub import SCRUB_TARGETS, ScrubTarget, legacy_secret_fingerprint, scrub_list
from .legacy_gate import (
    GateDecision,
    LegacyMode,
    LegacyTokenRejected,
    enforce,
    evaluate,
    is_enabled,
    legacy_login_mint_allowed,
    resolve_mode,
)
from .legacy_gate import set_event_bus as set_gate_event_bus
from .principal import (
    ANONYMOUS,
    AuthMethod,
    Principal,
    jwt_principal,
    legacy_principal,
    logto_principal,
    service_principal,
)
from .rotation import (
    RotationResult,
    hmac_token,
    rotate_caller_pass,
    rotate_hmac_signing_secret,
    token_valid_under,
    verify_rotation_invalidates,
)
from .route_auth_assert import (
    ADMIN_ROUTES,
    W8_W16_OPERATIONAL_ROUTES,
    RouteAuthViolation,
    RouteSpec,
    all_routes,
    assert_legacy_rejected_when_off,
    assert_real_auth_passes,
    assert_route_safe,
    assert_surface_safe,
    legacy_reachable_route_paths,
)

__all__ = [
    # sub-packages
    "principal", "legacy_gate", "route_auth_assert", "rotation", "docs_scrub",
    # principal
    "AuthMethod", "Principal", "ANONYMOUS", "jwt_principal", "logto_principal",
    "service_principal", "legacy_principal",
    # gate
    "LegacyMode", "GateDecision", "LegacyTokenRejected", "evaluate", "enforce",
    "resolve_mode", "is_enabled", "legacy_login_mint_allowed", "set_gate_event_bus",
    # route assertion
    "RouteSpec", "RouteAuthViolation", "W8_W16_OPERATIONAL_ROUTES", "ADMIN_ROUTES",  # gitleaks:allow (public symbol name, not a secret)
    "all_routes", "assert_route_safe", "assert_surface_safe",
    "assert_legacy_rejected_when_off", "assert_real_auth_passes", "legacy_reachable_route_paths",
    # rotation
    "RotationResult", "rotate_caller_pass", "rotate_hmac_signing_secret",
    "verify_rotation_invalidates", "hmac_token", "token_valid_under",
    # docs scrub
    "ScrubTarget", "SCRUB_TARGETS", "scrub_list", "legacy_secret_fingerprint",
]
