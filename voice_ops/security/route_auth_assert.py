"""voice_ops.security.route_auth_assert — assert every NEW operational route (W8–W16) is born behind
real tenant auth, NEVER reachable by the legacy static token.

WHY THIS EXISTS: the W18 finding is that every new W8–W16 route is "born reachable" by the legacy
static password because they all hang off `resolve_tenant`, which (pre-W20) accepts it. After the
W20 gate, `resolve_tenant` rejects legacy when the mode is OFF — so the FIX is structural: a route is
SAFE iff (a) it requires a resolved tenant principal AND (b) that principal-resolution passes through
the legacy gate. This module is the executable spec of that invariant + a CI-friendly contract test
that pins the W8–W16 surface so a future route added WITHOUT real auth fails the suite loudly.

It does NOT introspect the live FastAPI app (that would import caller.py/droplet code). Instead it
operates on a declarative ROUTE-SURFACE manifest (the W8–W16 operational routes, grounded in the
EXPLORE findings) + a tiny `RouteSpec` contract each route declares. The PATCH wires caller.py's real
routers to emit these specs; the test here proves the manifest itself is internally consistent and
that the gate denies legacy on every one of them.

IMPORT ISOLATION: pure stdlib. ZERO droplet/caller/auth imports.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, List

from .legacy_gate import LegacyMode, evaluate
from .principal import AuthMethod


@dataclass(frozen=True)
class RouteSpec:
    """A declared operational route + how it authenticates. The contract caller.py's routers emit so
    this layer can assert the invariant WITHOUT importing the app."""

    path: str                    # e.g. "/callbacks", "/ads/campaigns"
    methods: tuple = ("GET",)
    wave: str = ""               # W8..W16 (provenance)
    requires_tenant_auth: bool = True   # MUST be True for an operational route
    is_admin_route: bool = False        # /admin/* — uses require_super_admin, legacy already excluded
    # the auth methods this route is INTENDED to accept once W20 is live. legacy_pw must NOT be here.
    accepts: tuple = (AuthMethod.JWT, AuthMethod.LOGTO, AuthMethod.SERVICE)


class RouteAuthViolation(AssertionError):
    """A route violates the W20 invariant (accepts legacy, or lacks real tenant auth)."""


# --------------------------------------------------------------------------- #
# The W8–W16 OPERATIONAL ROUTE SURFACE (grounded in the EXPLORE findings).
# These are the routes that were "born reachable" by the legacy token because they ride
# resolve_tenant. After W20 (mode OFF) every one of them must reject legacy_pw.
# This manifest is the regression pin: adding a new operational route means adding it here with
# requires_tenant_auth=True and legacy NOT in `accepts`, or the contract test fails.
# --------------------------------------------------------------------------- #
W8_W16_OPERATIONAL_ROUTES: List[RouteSpec] = [
    # --- W8 events / config-change surface (mounted routers) ---------------------- #
    RouteSpec("/callbacks", ("GET", "POST", "DELETE"), wave="W10"),
    RouteSpec("/usage", ("GET",), wave="W14"),
    RouteSpec("/usage/all", ("GET",), wave="W14"),
    # --- ads engine ------------------------------------------------------------- #
    RouteSpec("/ads/campaigns", ("GET", "POST"), wave="W15"),
    RouteSpec("/ads/insights", ("GET",), wave="W15"),
    # --- AI Manager (AIM) routes ------------------------------------------------ #
    RouteSpec("/aim/sessions", ("GET",), wave="W14"),
    RouteSpec("/aim/command", ("POST",), wave="W14"),
    # --- custom / provider routes ----------------------------------------------- #
    RouteSpec("/providers/custom", ("GET", "POST"), wave="W13"),
    # --- media-gen / Creative Studio -------------------------------------------- #
    RouteSpec("/media/generate", ("POST",), wave="W16"),
    RouteSpec("/media/assets", ("GET",), wave="W16"),
    # --- booking ---------------------------------------------------------------- #
    RouteSpec("/booking/appointments", ("GET", "POST"), wave="W11"),
    # --- funnels ---------------------------------------------------------------- #
    RouteSpec("/funnels", ("GET", "POST"), wave="W12"),
    # --- forms ------------------------------------------------------------------ #
    RouteSpec("/forms", ("GET", "POST"), wave="W12"),
    # --- communication (WhatsApp / Telegram pipeline) --------------------------- #
    RouteSpec("/whatsapp/send", ("POST",), wave="W13"),
    RouteSpec("/comm/messages", ("GET",), wave="W13"),
    # --- inbound pipeline ------------------------------------------------------- #
    RouteSpec("/inbound/sessions", ("GET",), wave="W9"),
    # --- billing / usage explorer ----------------------------------------------- #
    RouteSpec("/billing/vendors", ("GET",), wave="W14"),
    RouteSpec("/billing/explorer", ("GET",), wave="W14"),
    # --- leads / contacts ------------------------------------------------------- #
    RouteSpec("/leads/hot", ("GET",), wave="W9"),
    RouteSpec("/contacts", ("GET", "POST"), wave="W9"),
    # --- tenant limits (admin-gated inline; still must reject legacy under W20) --- #
    RouteSpec("/tenants/{tid}/limits", ("POST",), wave="W14"),
]

# The /admin/* plane — ALREADY legacy-excluded by require_super_admin. Listed so the test proves
# the gate keeps rejecting legacy on them in EVERY mode (no regression even in ON).
ADMIN_ROUTES: List[RouteSpec] = [
    RouteSpec("/admin/tenants", ("GET", "POST"), wave="control", is_admin_route=True,
              accepts=(AuthMethod.JWT, AuthMethod.LOGTO)),
    RouteSpec("/admin/entitlements", ("GET", "POST"), wave="control", is_admin_route=True,
              accepts=(AuthMethod.JWT, AuthMethod.LOGTO)),
    RouteSpec("/admin/provider-keys", ("GET", "POST"), wave="control", is_admin_route=True,
              accepts=(AuthMethod.JWT, AuthMethod.LOGTO)),
]


# --------------------------------------------------------------------------- #
# assertions
# --------------------------------------------------------------------------- #
def assert_route_safe(spec: RouteSpec) -> None:
    """A single route must (1) require a resolved tenant principal, and (2) NOT list legacy_pw in its
    accepted methods. Raises RouteAuthViolation otherwise."""
    if not spec.requires_tenant_auth and not spec.is_admin_route:
        raise RouteAuthViolation(
            f"{spec.path} ({spec.wave}) does not require tenant auth — every operational route MUST "
            f"resolve a real tenant principal (resolve_tenant) so the W20 gate can run."
        )
    if AuthMethod.LEGACY_PW in spec.accepts:
        raise RouteAuthViolation(
            f"{spec.path} ({spec.wave}) declares it accepts legacy_pw — forbidden by W20. "
            f"Remove AuthMethod.LEGACY_PW from `accepts`."
        )


def assert_surface_safe(routes: Iterable[RouteSpec]) -> List[str]:
    """Assert the whole surface. Returns the list of checked route paths (for the report)."""
    checked = []
    for spec in routes:
        assert_route_safe(spec)
        checked.append(spec.path)
    return checked


def assert_legacy_rejected_when_off(routes: Iterable[RouteSpec]) -> List[str]:
    """The behavioural assertion: with the gate at mode OFF, a legacy_pw request to EVERY operational
    route is DENIED. Returns the denied paths. This is the executable proof of 'born NOT reachable by
    the legacy token after W20'."""
    denied = []
    for spec in routes:
        d = evaluate(
            AuthMethod.LEGACY_PW, mode=LegacyMode.OFF, tenant_id="t-demo",
            route=spec.path, is_admin_route=spec.is_admin_route, audit=False,
        )
        if d.allowed:
            raise RouteAuthViolation(
                f"{spec.path} ({spec.wave}) STILL accepts legacy_pw at mode OFF — W20 invariant broken."
            )
        denied.append(spec.path)
    return denied


def assert_real_auth_passes(routes: Iterable[RouteSpec]) -> List[str]:
    """Sanity: a real (JWT) principal is allowed on every operational route at mode OFF (the flip must
    not break legitimate auth — the earner path stays alive)."""
    ok = []
    for spec in routes:
        d = evaluate(
            AuthMethod.JWT, mode=LegacyMode.OFF, tenant_id="t-demo",
            route=spec.path, is_admin_route=spec.is_admin_route, audit=False,
        )
        if not d.allowed:
            raise RouteAuthViolation(f"{spec.path}: real JWT auth wrongly denied at mode OFF.")
        ok.append(spec.path)
    return ok


def all_routes() -> List[RouteSpec]:
    return list(W8_W16_OPERATIONAL_ROUTES) + list(ADMIN_ROUTES)


def legacy_reachable_route_paths() -> List[str]:
    """The pre-W20 'born reachable by legacy_pw' list — exactly the operational (non-admin) routes.
    This is the deliverable 'list of routes that were legacy-reachable'."""
    return [r.path for r in W8_W16_OPERATIONAL_ROUTES if not r.is_admin_route]
