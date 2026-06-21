"""auth.py — Famit P0 JWT access + rotating refresh tokens (ADDITIVE).

Adds a modern token flow ON TOP of the existing auth without changing it:

  * Access token  = stateless JWT (HS256, signed with the SAME `var/secret` the
    legacy hmac tokens already use), 15-minute expiry, claims
    {sub: tenant_id, role, type:"access", iat, exp, jti}.
  * Refresh token = opaque random id stored server-side (var/refresh_tokens.json)
    so it can be REVOKED and ROTATED. Default lifetime 30 days. On /auth/refresh
    the presented refresh token is revoked and a NEW access+refresh pair issued
    (rotation). /auth/logout revokes the refresh token (and its whole session).

The existing legacy bare-password (`X-Auth: FamitCall2026` -> admin) and signed
`tenant_id.hmac` tokens KEEP working exactly as before — see `resolve_token()`
below, which caller.resolve_tenant() calls FIRST and which returns None for any
non-JWT credential so the legacy path can handle it unchanged.

caller.py wires this up by calling `init(...)` once with small callbacks into its
existing tenant store (no duplication of the user database).

pyjwt is required for the JWT path; if it is unavailable, init() degrades to a
NO-OP (access tokens are not issued; legacy auth is untouched) so the service
still starts. caller.py imports this module defensively.
"""
from __future__ import annotations

import json
import secrets
import time
from pathlib import Path
from typing import Any, Callable, Optional

try:
    import jwt as _jwt  # PyJWT
except Exception:  # noqa: BLE001
    _jwt = None

ALGO = "HS256"
ACCESS_TTL_SECONDS = 15 * 60            # 15 minutes (spec)
REFRESH_TTL_SECONDS = 30 * 24 * 3600    # 30 days
ACT_AS_TTL_SECONDS = 10 * 60           # CONTROL LAYER: act-as (impersonation) token, SHORTER than 15-min

# ---- injected from caller.py via init() ----
_SECRET: str = ""
_REFRESH_FILE: Optional[Path] = None
_TENANT_BY_ID: Callable[[str], Optional[dict]] = lambda _tid: None
_VERIFY_PASSWORD: Callable[[str, str], Optional[dict]] = lambda _e, _p: None
_ROLE_OF: Callable[[dict], str] = lambda _t: "manager"
_ready = False


def init(secret: str,
         refresh_file: Path,
         tenant_by_id: Callable[[str], Optional[dict]],
         verify_password: Callable[[str, str], Optional[dict]],
         role_of: Callable[[dict], str]) -> bool:
    """Wire auth.py to caller.py's existing stores. Returns True if the JWT path
    is available (pyjwt present), False if it degraded to NO-OP."""
    global _SECRET, _REFRESH_FILE, _TENANT_BY_ID, _VERIFY_PASSWORD, _ROLE_OF, _ready
    _SECRET = secret or ""
    _REFRESH_FILE = Path(refresh_file)
    _TENANT_BY_ID = tenant_by_id
    _VERIFY_PASSWORD = verify_password
    _ROLE_OF = role_of
    _ready = _jwt is not None and bool(_SECRET)
    return _ready


def available() -> bool:
    return _ready


# ---------------- refresh-token store (revocable) ----------------
def _read_refresh() -> dict:
    try:
        if _REFRESH_FILE and _REFRESH_FILE.exists():
            return json.loads(_REFRESH_FILE.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        pass
    return {}


def _write_refresh(data: dict) -> None:
    try:
        _REFRESH_FILE.parent.mkdir(parents=True, exist_ok=True)
        _REFRESH_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                                 encoding="utf-8")
        try:
            import os
            os.chmod(_REFRESH_FILE, 0o600)
        except Exception:  # noqa: BLE001
            pass
    except Exception:  # noqa: BLE001
        pass


def _prune(store: dict) -> dict:
    now = int(time.time())
    return {k: v for k, v in store.items()
            if isinstance(v, dict) and int(v.get("exp", 0)) > now}


# ---------------- token mint / verify ----------------
def _make_access(tenant: dict) -> str:
    now = int(time.time())
    payload = {
        "sub": tenant.get("tenant_id"),
        "role": _ROLE_OF(tenant),
        "is_admin": bool(tenant.get("is_admin")),
        "type": "access",
        "iat": now,
        "exp": now + ACCESS_TTL_SECONDS,
        "jti": secrets.token_hex(8),
    }
    return _jwt.encode(payload, _SECRET, algorithm=ALGO)


def _make_refresh(tenant_id: str) -> str:
    rid = secrets.token_urlsafe(32)
    now = int(time.time())
    store = _prune(_read_refresh())
    store[rid] = {"tenant_id": tenant_id, "iat": now,
                  "exp": now + REFRESH_TTL_SECONDS,
                  "session": secrets.token_hex(6)}
    _write_refresh(store)
    return rid


def issue_pair(tenant: dict) -> dict:
    """Mint a fresh access+refresh pair for an already-authenticated tenant."""
    return {
        "access_token": _make_access(tenant),
        "refresh_token": _make_refresh(tenant["tenant_id"]),
        "token_type": "Bearer",
        "expires_in": ACCESS_TTL_SECONDS,
        "tenant_id": tenant.get("tenant_id"),
        "role": _ROLE_OF(tenant),
        "is_admin": bool(tenant.get("is_admin")),
    }


def resolve_token(cred: str) -> Optional[dict]:
    """If `cred` is a valid Famit ACCESS JWT, return the tenant dict; otherwise
    return None (so the caller falls back to the legacy/hmac path). This NEVER
    raises and NEVER treats a legacy `tenant_id.hmac` token or bare password as a
    JWT (those fail jwt.decode and return None cleanly)."""
    if not _ready or not cred:
        return None
    # Fast reject things that obviously aren't a JWT (JWT has exactly 2 dots).
    if cred.count(".") != 2:
        return None
    try:
        payload = _jwt.decode(cred, _SECRET, algorithms=[ALGO])
    except Exception:  # noqa: BLE001 (expired/invalid/not-a-jwt)
        return None
    if payload.get("type") != "access":
        return None
    tid = payload.get("sub")
    if not tid:
        return None
    return _TENANT_BY_ID(tid)


def access_claims(cred: str) -> Optional[dict]:
    """Return the raw verified claims of an access JWT (for diagnostics/tests + the act-as check)."""
    if not _ready or not cred or cred.count(".") != 2:
        return None
    try:
        return _jwt.decode(cred, _SECRET, algorithms=[ALGO])
    except Exception:  # noqa: BLE001
        return None


# ---------------- CONTROL LAYER: act-as / impersonation token (CL-B3 / plan C11) ----------------
# A DEDICATED short-TTL access token an admin uses to view a vendor. NOT a normal vendor token:
#   sub        = the VENDOR tenant_id (so RLS + tenant-scoped readers naturally show vendor data;
#                we ride the proven isolation, inventing no new cross-tenant read path),
#   act_as     = the vendor tenant_id (explicit marker the middleware/admin-gate treat specially),
#   real_admin = the ADMIN tenant_id (WHO is really behind the wheel — for audit + write attribution),
#   scope      = "read_only" (DEFAULT) | "read_write",
#   amr        = "act_as", type = "access" (so resolve_token still resolves the vendor),
#   exp        = now + ACT_AS_TTL_SECONDS (<= 10 min — a tighter fuse than a normal token).
# resolve_token() returns the VENDOR tenant for this token (type=="access", sub=vendor) — by design.
# The act-as-specific guards (read-only block, can't-climb-to-admin) live in caller.py, which reads
# access_claims() to see the act_as / real_admin / scope markers.
def make_act_as(vendor_id: str, admin_id: str, scope: str = "read_only") -> Optional[str]:
    """Mint an act-as access token. Returns the JWT string or None if the JWT path is unavailable."""
    if not _ready or not vendor_id or not admin_id:
        return None
    if scope not in ("read_only", "read_write"):
        scope = "read_only"
    now = int(time.time())
    payload = {
        "sub": vendor_id,            # RLS/readers scope to the vendor
        "act_as": vendor_id,         # impersonation marker
        "real_admin": admin_id,      # the human actually behind the wheel
        "amr": "act_as",
        "scope": scope,
        "role": _ROLE_OF(_TENANT_BY_ID(vendor_id) or {"is_admin": False}),
        "is_admin": False,           # an act-as token NEVER carries admin (can't climb back up)
        "type": "access",
        "iat": now,
        "exp": now + ACT_AS_TTL_SECONDS,
        "jti": secrets.token_hex(8),
    }
    return _jwt.encode(payload, _SECRET, algorithm=ALGO)


def act_as_claims(cred: str) -> Optional[dict]:
    """If `cred` is a valid act-as token, return its claims (with act_as/real_admin/scope); else None.
    Used by caller.py to recognise an impersonation session and enforce read-only / no-climb."""
    c = access_claims(cred)
    if not c or c.get("amr") != "act_as" or not c.get("act_as") or not c.get("real_admin"):
        return None
    return c


# ---------------- endpoint helpers (called by caller.py routes) ----------------
def login(email: str, password: str) -> Optional[dict]:
    """Authenticate via the EXISTING tenant store (verify_password callback) and
    return a token pair, or None on bad credentials."""
    if not _ready:
        return None
    tenant = _VERIFY_PASSWORD(email, password)
    if not tenant:
        return None
    pair = issue_pair(tenant)
    pair["name"] = tenant.get("name", "")
    return pair


def refresh(refresh_token: str) -> Optional[dict]:
    """Rotate: validate the presented refresh token, REVOKE it, issue a new pair.
    Returns the new pair or None if the refresh token is unknown/expired/revoked."""
    if not _ready or not refresh_token:
        return None
    store = _prune(_read_refresh())
    rec = store.get(refresh_token)
    if not rec:
        # unknown/expired/already-rotated -> reject (and persist any pruning)
        _write_refresh(store)
        return None
    tenant = _TENANT_BY_ID(rec.get("tenant_id"))
    if not tenant:
        store.pop(refresh_token, None)
        _write_refresh(store)
        return None
    # rotation: invalidate the old refresh token before issuing a new one
    store.pop(refresh_token, None)
    _write_refresh(store)
    pair = issue_pair(tenant)
    pair["name"] = tenant.get("name", "")
    return pair


def logout(refresh_token: str) -> bool:
    """Revoke a refresh token (idempotent). Access tokens are short-lived and
    expire on their own. Returns True if a token was removed."""
    if not refresh_token:
        return False
    store = _read_refresh()
    existed = refresh_token in store
    if existed:
        store.pop(refresh_token, None)
        _write_refresh(store)
    return existed


def revoke_all(tenant_id: str) -> int:
    """Revoke every refresh token for a tenant (e.g. password reset). Returns count."""
    store = _read_refresh()
    victims = [k for k, v in store.items()
               if isinstance(v, dict) and v.get("tenant_id") == tenant_id]
    for k in victims:
        store.pop(k, None)
    if victims:
        _write_refresh(store)
    return len(victims)
