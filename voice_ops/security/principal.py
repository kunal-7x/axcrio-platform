"""voice_ops.security.principal — the auth-RESULT vocabulary (TRACKED, droplet-free).

This is the small, frozen type system the W20 legacy-token retirement is built on. It mirrors the
classification caller.py already does inline (`_auth_method` at caller.py:706 returns one of
"jwt" / "legacy_pw" / None) but as an EXPLICIT, testable, importable contract instead of three
string literals scattered through one mega-file.

WHY A SEPARATE TYPE: the live retirement decision is "is this principal authenticated by the legacy
static password, or by a real revocable credential (JWT / Logto)?". Today that decision is a string
compare buried in the request path. By naming it (`AuthMethod`) and carrying the verdict
(`Principal.is_legacy`) we can (a) unit-test the gate with mock auth and zero droplet imports, and
(b) hand caller.py a drop-in PATCH that swaps its inline literals for this vocabulary 1:1.

IMPORT ISOLATION: pure stdlib. `import voice_ops.security.principal` pulls ZERO droplet_work, ZERO
caller.py/auth.py, ZERO crypto/sqlalchemy — safe on any host / in CI.

SECURITY: a Principal NEVER carries the secret/password/token bytes. It carries the *method* and the
resolved tenant/role only. `repr` is safe to log.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Optional


class AuthMethod(str, enum.Enum):
    """How a request proved who it is. Closed set — mirrors caller.py `_auth_method`."""

    JWT = "jwt"               # real, revocable, short-TTL token (auth.py HS256 / Logto)
    LOGTO = "logto"           # Logto-issued OIDC access token (the target end-state)
    SERVICE = "service"       # a provisioned service credential (AIM loopback, cron, Hatchet)
    LEGACY_PW = "legacy_pw"   # the static CALLER_PASS bearer — THE thing W20 retires
    NONE = "none"             # nothing valid presented -> 401

    @property
    def is_real(self) -> bool:
        """A 'real' credential is revocable + rotatable + non-static. Everything EXCEPT legacy_pw
        and none. These are the methods that survive the W20 flip."""
        return self in (AuthMethod.JWT, AuthMethod.LOGTO, AuthMethod.SERVICE)


@dataclass(frozen=True)
class Principal:
    """The resolved identity of a request — the RESULT of authentication, never the credential.

    `method` is the load-bearing field for W20. `tenant_id`/`role`/`is_admin` are the resolved
    attributes a route uses for authorization (kept so the gate can express 'legacy may never reach
    /admin/*' as a pure data assertion in tests)."""

    method: AuthMethod
    tenant_id: Optional[str] = None
    role: str = ""
    is_admin: bool = False
    # purely informational; NEVER the secret. e.g. a key fingerprint or 'sub' claim id.
    credential_ref: str = ""
    claims: dict = field(default_factory=dict)

    # --- the verdicts W20 turns on -------------------------------------------------- #
    @property
    def is_legacy(self) -> bool:
        return self.method is AuthMethod.LEGACY_PW

    @property
    def is_authenticated(self) -> bool:
        return self.method is not AuthMethod.NONE

    @property
    def is_real_auth(self) -> bool:
        """True iff authenticated by a credential that survives the legacy retirement."""
        return self.method.is_real

    def __repr__(self) -> str:  # safe-to-log: no secret material ever
        return (
            f"Principal(method={self.method.value}, tenant={self.tenant_id!r}, "
            f"role={self.role!r}, admin={self.is_admin})"
        )


# Canonical singletons / helpers -------------------------------------------------------- #
ANONYMOUS = Principal(method=AuthMethod.NONE)


def jwt_principal(tenant_id: str, *, role: str = "", is_admin: bool = False, sub: str = "") -> Principal:
    return Principal(AuthMethod.JWT, tenant_id=tenant_id, role=role, is_admin=is_admin, credential_ref=sub)


def logto_principal(tenant_id: str, *, role: str = "", is_admin: bool = False, sub: str = "") -> Principal:
    return Principal(AuthMethod.LOGTO, tenant_id=tenant_id, role=role, is_admin=is_admin, credential_ref=sub)


def service_principal(tenant_id: str, *, ref: str = "") -> Principal:
    return Principal(AuthMethod.SERVICE, tenant_id=tenant_id, role="service", credential_ref=ref)


def legacy_principal(tenant_id: str, *, is_admin: bool = True) -> Principal:
    """The principal the legacy static password resolves to (the admin tenant). Constructing one is
    fine; the GATE decides whether it is ALLOWED to proceed."""
    return Principal(AuthMethod.LEGACY_PW, tenant_id=tenant_id, role="admin", is_admin=is_admin)
