"""voice_ops.security.legacy_gate — the LEGACY-TOKEN rejection layer + the LEGACY_TOKEN_ENABLED gate.

THE W20 FINDING (design/control-security.md #1; W18 MD1/NEW-W20): the legacy static password
(`CALLER_PASS`) is a PERMANENT, UN-REVOCABLE bearer token. Today it authenticates EVERY vendor route
platform-wide (caller.py `resolve_tenant` accepts it), AND it can be EXCHANGED for a real JWT at
`/auth/login` or an hmac panel token at `/login`. So every new W8–W16 operational route is born
reachable by it. SCOPE OF OFF (honest): OFF retires the password as a direct bearer AND closes the
password→token mints (/auth/login admin-by-pw + /login); it does NOT invalidate hmac/JWT tokens
ALREADY minted — only Phase-3 HMAC-secret rotation does that. It must be retired: flip the
kill-switch toward OFF, reject the legacy password
EVERYWHERE (not just /admin/*), and force real JWT/Logto auth — flag-gated + reversible.

THIS MODULE is the pure-logic decision engine for that flip. It is droplet-free and importable in CI;
caller.py adopts it via a 1:1 PATCH (see PATCH-caller-auth.md) — we NEVER edit the live file here.

DEFAULT TOWARD OFF — the safe end-state. The founder's transition reality (the panel + AIM loopback
still present the legacy password until their migration ships) is honored by an explicit
`TRANSITION` mode that lets legacy through BUT stamps every use as a deprecated, audited fact so the
flip can be made with eyes open. The three modes:

    OFF        legacy_pw -> REJECT (401) everywhere. JWT/Logto/service still pass. The target.
    TRANSITION legacy_pw -> ALLOW but emit `auth.legacy_token_used` (deprecated) every time. Migration.
    ON         legacy_pw -> ALLOW silently. The pre-W20 status quo (do not ship as the end-state).

Resolution precedence (so a typo can't accidentally re-open the door):
    explicit `mode=` arg  >  LEGACY_TOKEN_MODE env  >  LEGACY_TOKEN_ENABLED env  >  default(OFF in the
    library; the live .env starts at TRANSITION during cutover then flips to OFF — see the runbook).

EARNER SAFETY: this is additive logic only. Nothing here imports/restarts/edits any box. The /admin/*
plane was ALREADY legacy-excluded (require_super_admin); this extends that exclusion to the whole
surface — but only when the operator sets the mode, which the runbook gates behind a real access smoke.

IMPORT ISOLATION: pure stdlib + a lazy event factory. ZERO droplet/caller/auth imports at load.
"""
from __future__ import annotations

import asyncio
import enum
import logging
import os
from dataclasses import dataclass
from typing import Optional

from .principal import AuthMethod, Principal

log = logging.getLogger("voice_ops.security.legacy_gate")

# the LIBRARY default. Conservative: a fresh import with no env set REJECTS legacy.
# (The live .env carries it through TRANSITION during cutover; the runbook flips it to OFF.)
_LIBRARY_DEFAULT = "off"


class LegacyMode(str, enum.Enum):
    OFF = "off"               # reject legacy_pw everywhere (target end-state)
    TRANSITION = "transition"  # allow but audit each use as deprecated (migration window)
    ON = "on"                 # allow silently (pre-W20 status quo)


class LegacyTokenRejected(PermissionError):
    """Raised by the gate when a legacy_pw request must be refused. The caller maps this to HTTP 401.

    Carries NO secret. `code` is the stable machine reason; `http_status` is the recommended status."""

    def __init__(self, message: str = "legacy static password is retired; use a JWT/Logto token",
                 *, code: str = "legacy_token_retired", http_status: int = 401):
        super().__init__(message)
        self.code = code
        self.http_status = http_status


@dataclass(frozen=True)
class GateDecision:
    """The verdict for one request. `allowed` False -> caller must 401. `deprecated` True -> the
    request proceeded on legacy auth during the transition window and was audited."""

    allowed: bool
    mode: LegacyMode
    method: AuthMethod
    deprecated: bool = False
    reason: str = ""


# --------------------------------------------------------------------------- #
# mode resolution
# --------------------------------------------------------------------------- #
def _truthy(v: Optional[str]) -> Optional[bool]:
    if v is None:
        return None
    t = v.strip().lower()
    if t in ("1", "true", "yes", "on"):
        return True
    if t in ("0", "false", "no", "off"):
        return False
    return None


def resolve_mode(mode: Optional[str | LegacyMode] = None, *, env: Optional[dict] = None) -> LegacyMode:
    """Resolve the effective legacy mode. Precedence:
        explicit `mode` arg  >  LEGACY_TOKEN_MODE  >  LEGACY_TOKEN_ENABLED  >  library default (OFF).
    An UNRECOGNISED value fails CLOSED to OFF (never silently re-opens the door). `env` is injectable
    for tests; defaults to os.environ."""
    if isinstance(mode, LegacyMode):
        return mode
    if isinstance(mode, str) and mode.strip():
        try:
            return LegacyMode(mode.strip().lower())
        except ValueError:
            log.warning("unknown legacy mode arg %r -> failing closed to OFF", mode)
            return LegacyMode.OFF
    e = os.environ if env is None else env
    raw_mode = (e.get("LEGACY_TOKEN_MODE") or "").strip().lower()
    if raw_mode:
        try:
            return LegacyMode(raw_mode)
        except ValueError:
            log.warning("unknown LEGACY_TOKEN_MODE=%r -> failing closed to OFF", raw_mode)
            return LegacyMode.OFF
    # back-compat with the existing caller.py flag (caller.py:151 LEGACY_TOKEN_ENABLED).
    enabled = _truthy(e.get("LEGACY_TOKEN_ENABLED"))
    if enabled is True:
        # the existing flag being "true" maps to TRANSITION (allow + audit), NOT silent ON — so even
        # leaving the old flag set produces the deprecation trail instead of the old silent accept.
        return LegacyMode.TRANSITION
    if enabled is False:
        return LegacyMode.OFF
    return LegacyMode(_LIBRARY_DEFAULT)


# --------------------------------------------------------------------------- #
# fail-soft deprecation audit emit (mirrors voice_ops.config.events posture)
# --------------------------------------------------------------------------- #
_bus = None


def set_event_bus(bus) -> None:
    """Inject the W8 EventBus the gate emits the deprecation fact on (RedisEventBus in prod,
    InMemoryEventBus in tests, None = no-op). Structural: any object with an async `emit(Event)`."""
    global _bus
    _bus = bus


def _legacy_used_event(tenant_id: str, route: str):
    """Build the `auth.legacy_token_used` fact via the generic W8 factory. We do NOT widen the closed
    EventName enum (that file stays untouched) — make_event accepts a plain str name, so this is a
    disjoint, additive event that still rides the same bus/serde/idempotency path."""
    from voice_kernel.events.taxonomy import make_event
    return make_event(
        "auth.legacy_token_used",
        call_id=f"legacy:{route or '?'}",
        tenant_id=tenant_id or "",
        payload={"route": route or None, "deprecated": True, "auth_method": "legacy_pw"},
    )


def _emit(event) -> None:
    """Fire-and-forget, fail-soft. An audit emit must NEVER break a live request (LEARNINGS §4)."""
    bus = _bus
    if bus is None:
        return
    try:
        coro = bus.emit(event)
    except Exception as exc:  # noqa: BLE001
        log.warning("legacy-use audit emit setup failed (non-fatal): %r", exc)
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop is not None:
        task = loop.create_task(_guard(coro))
        task.add_done_callback(lambda t: t.exception() if not t.cancelled() else None)
        return
    try:
        asyncio.run(_guard(coro))
    except Exception as exc:  # noqa: BLE001
        log.warning("legacy-use audit emit failed (non-fatal): %r", exc)


async def _guard(coro) -> None:
    try:
        await coro
    except Exception as exc:  # noqa: BLE001
        log.warning("legacy-use audit emit failed (non-fatal): %r", exc)


# --------------------------------------------------------------------------- #
# THE GATE
# --------------------------------------------------------------------------- #
def evaluate(
    method: AuthMethod | str,
    *,
    mode: Optional[str | LegacyMode] = None,
    tenant_id: str = "",
    route: str = "",
    is_admin_route: bool = False,
    env: Optional[dict] = None,
    audit: bool = True,
) -> GateDecision:
    """The pure decision. Given how a request authenticated, decide whether it may proceed.

    Rules:
      * Any REAL method (jwt/logto/service) -> ALWAYS allowed (W20 changes nothing for them).
      * method == none -> not allowed (the route's own auth already 401s; we just classify).
      * method == legacy_pw:
          - on an /admin/* route -> ALWAYS rejected, in EVERY mode (the plane was already excluded;
            we never regress that even in ON).
          - mode OFF        -> rejected.
          - mode TRANSITION -> allowed, marked deprecated, audited (fire-and-forget).
          - mode ON         -> allowed silently.
    Never raises here — returns the verdict. Use `enforce()` for the raise-or-pass wrapper."""
    m = method if isinstance(method, AuthMethod) else AuthMethod(str(method))
    eff = resolve_mode(mode, env=env)

    if m.is_real:
        return GateDecision(True, eff, m, deprecated=False, reason="real_auth")
    if m is AuthMethod.NONE:
        return GateDecision(False, eff, m, deprecated=False, reason="unauthenticated")

    # m is LEGACY_PW from here.
    if is_admin_route:
        return GateDecision(False, eff, m, deprecated=False, reason="legacy_excluded_from_admin")
    if eff is LegacyMode.OFF:
        return GateDecision(False, eff, m, deprecated=False, reason="legacy_retired")
    if eff is LegacyMode.TRANSITION:
        if audit:
            _emit(_legacy_used_event(tenant_id, route))
        return GateDecision(True, eff, m, deprecated=True, reason="legacy_transition_deprecated")
    # ON
    return GateDecision(True, eff, m, deprecated=False, reason="legacy_on_legacy")


def enforce(
    principal: Principal,
    *,
    mode: Optional[str | LegacyMode] = None,
    route: str = "",
    is_admin_route: bool = False,
    env: Optional[dict] = None,
    audit: bool = True,
) -> Principal:
    """The raise-or-pass wrapper a route guard uses. Returns the principal unchanged when allowed;
    raises LegacyTokenRejected (-> HTTP 401) when a legacy_pw request must be refused. This is the
    one-liner caller.py's `resolve_tenant`/`need_auth` adopts via the PATCH (see PATCH-caller-auth.md)."""
    decision = evaluate(
        principal.method, mode=mode, tenant_id=principal.tenant_id or "",
        route=route, is_admin_route=is_admin_route, env=env, audit=audit,
    )
    if not decision.allowed:
        if principal.method is AuthMethod.LEGACY_PW:
            raise LegacyTokenRejected(
                "legacy static password is retired for this route; present a JWT/Logto token",
                code="legacy_token_retired", http_status=401,
            )
        # unauthenticated -> same 401 (the route normally 401s first; this is belt-and-suspenders).
        raise LegacyTokenRejected("unauthenticated", code="unauthenticated", http_status=401)
    if decision.deprecated:
        log.warning(
            "DEPRECATED legacy_pw auth accepted in TRANSITION mode for route=%r tenant=%r — migrate "
            "this caller to a JWT/Logto token before the W20 flip to OFF.", route, principal.tenant_id,
        )
    return principal


def is_enabled(*, env: Optional[dict] = None) -> bool:
    """Convenience for the old call sites: True iff legacy_pw is accepted at all (TRANSITION or ON)."""
    return resolve_mode(env=env) is not LegacyMode.OFF


# --------------------------------------------------------------------------- #
# password -> TOKEN mint gate (the /login + /auth/login leg — PATCH §2 / §2b)
# --------------------------------------------------------------------------- #
def legacy_login_mint_allowed(
    *, mode: Optional[str | LegacyMode] = None, env: Optional[dict] = None
) -> bool:
    """Decide whether the LEGACY STATIC PASSWORD may be EXCHANGED FOR A TOKEN right now.

    This is the second, easily-missed leg of the retirement (red-team W20 BLOCKER 1+2): besides being a
    direct bearer (handled by `evaluate`/`enforce`), the password can be POSTed to caller.py's
    `/auth/login` (`_verify_password_for_auth` -> a real admin JWT) or `/login` (-> an hmac panel
    token). A JWT is `is_real`, so once minted the bearer gate ALWAYS allows it — meaning OFF is NOT
    achieved unless these mint paths are also closed. The PATCH (§2/§2b) calls THIS at those sites.

    Returns False at mode OFF (the password may not mint any token); True at TRANSITION/ON (it still
    may, and the call site logs the deprecation). It does NOT touch real per-user credentials — only
    the legacy-password branch is gated.

    NOTE on scope (do NOT overstate): returning False closes NEW mints. Tokens ALREADY minted from the
    password before the flip keep validating until the HMAC signing secret is rotated (rotation.py /
    runbook Phase 3) — that rotation is the only thing that retires path (d)."""
    return resolve_mode(mode, env=env) is not LegacyMode.OFF
