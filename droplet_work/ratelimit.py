"""ratelimit — the box-wide per-tenant / per-IP request limiter (denial-of-wallet guard).

caller.py imports this module at startup (`import ratelimit as _rl_mod`) and runs `allow(key, class)`
in an `@app.middleware("http")` choke point BEFORE routing. Until this module existed the import
fell to `None` and the limiter was DISABLED (fail-OPEN) — the unauth ad-ingest surface
(`/ads/webhooks/*`, `/ads/leads/form`, OAuth callbacks, …) had NO per-IP ceiling, so an attacker
could hammer it to force dials / CAPI emits / vault writes => denial-of-wallet (BLINDSPOTS B18 / the
security-clearance residual R1). This module closes that hole.

CONTRACT (exactly what caller.py calls — do not change the signatures):
  * init()                         -> str   backend name ("redis" | "inproc" | "disabled")
  * allow(key, route_class)        -> (bool, dict)  (allowed?, {limit, remaining, reset_in})
  * route_class(method, path)      -> str   classify a request into a limit class (caller delegates)

FAIL-CLOSED on the STRICT public classes, FAIL-OPEN on the normal ones (earner-safe):
  * The STRICT classes (`public-ingest`, `public-oauth`, `auth`) protect UNAUTH / brute-forceable
    surfaces. If the limiter ever cannot make a clean decision for one of these, `allow` returns
    (False, …) -> the request is DENIED (429). It NEVER raises, so caller.py's own try/except (which
    fails OPEN on an exception) can't accidentally re-open a strict class.
  * The normal classes (`read`/`write`/`default`) protect the authenticated app + the LIVE earner.
    Their ceilings are set deliberately HIGH (a human/dashboard never hits them) and on any internal
    error they FAIL-OPEN — a limiter bug must never throttle the live voice/agent spine.

EARNER-SAFE / REVERTIBLE: one env kill switch `RATELIMIT_ENABLED=0` makes init() return "disabled"
and the middleware becomes a pure passthrough (resting behaviour byte-identical to "module absent").
Every ceiling is env-tunable. ZERO I/O at import; never raises into the request path.

Backend: a self-contained in-process fixed-window counter is ALWAYS available (so a strict-class
decision can always be made locally — there is no "backend down => can't decide" hole). Redis is used
opportunistically for cross-process accuracy when `RATELIMIT_REDIS_URL`/`REDIS_URL` is set and the
`redis` client imports + pings; any Redis error degrades to the local counter (still enforcing).
"""
from __future__ import annotations

import os
import threading
import time
from collections import defaultdict, deque
from typing import Deque, Dict, Tuple

# --------------------------------------------------------------------------- config
_WINDOW_S = 60.0  # all ceilings are "per minute".

# Per-class ceilings (requests per 60s window). Normal classes are intentionally GENEROUS so the
# authenticated app + the live earner are never throttled; the STRICT classes bound the unauth
# denial-of-wallet surface. Every value is env-overridable.
_DEFAULT_LIMITS = {
    # normal (fail-OPEN) — high ceilings, here only to bound a pathological flood.
    "read": 6000,
    "write": 3000,
    "default": 6000,
    # strict (fail-CLOSED) — unauth / brute-forceable surfaces.
    "auth": 60,             # login / token refresh, keyed by IP (brute-force guard).
    "public-ingest": 120,   # /ads/webhooks/*, /ads/leads/form|import, /ads/creative/upload (per IP).
    "public-oauth": 30,     # OAuth callbacks / connect start (human-paced; per IP).
}

# The classes whose UNCERTAINTY must FAIL CLOSED (deny). Everything else fails open.
_STRICT_CLASSES = frozenset({"auth", "public-ingest", "public-oauth"})

# Path prefixes that are the UNAUTH public ad-ingest surface -> the strict `public-ingest` class.
# Hammering any of these with no auth is the denial-of-wallet vector, so they get the low ceiling
# keyed by client IP (the middleware keys by IP when no tenant resolves).
_PUBLIC_INGEST_PREFIXES = (
    "/ads/webhooks/",        # meta leadgen + ctwa inbound (HMAC-verified downstream, still bound here)
    "/ads/leads/form",       # own-landing form post (form-token gated)
    "/ads/leads/import",     # consented bulk import (step-up gated)
    "/ads/creative/upload",  # asset upload
)
# OAuth connect handshake surface (start builds a URL; callback lands a token) -> `public-oauth`.
_PUBLIC_OAUTH_SUFFIXES = ("/start", "/callback")
_PUBLIC_OAUTH_PREFIX = "/ads/connect/"

_AUTH_PATHS = frozenset({"/login", "/auth/login", "/auth/refresh"})


def _limit_for(route_class: str) -> int:
    env_key = "RATELIMIT_" + route_class.replace("-", "_").upper() + "_PER_MIN"
    raw = os.getenv(env_key, "")
    if raw.strip():
        try:
            v = int(raw)
            if v > 0:
                return v
        except Exception:  # noqa: BLE001
            pass
    return int(_DEFAULT_LIMITS.get(route_class, _DEFAULT_LIMITS["default"]))


def _enabled() -> bool:
    return (os.getenv("RATELIMIT_ENABLED", "1") or "1").strip().lower() not in (
        "0", "false", "no", "off")


# --------------------------------------------------------------------------- in-proc backend
_LOCK = threading.Lock()
# (key, route_class) -> deque of recent request timestamps within the window.
_HITS: Dict[Tuple[str, str], Deque[float]] = defaultdict(deque)
_HITS_KEY_CAP = 50000  # crude bound on the key space (drop oldest-inserted on overflow).

_BACKEND = "inproc"
_redis = None  # type: ignore


def init() -> str:
    """Pick the backend ONCE at startup. Returns 'redis' | 'inproc' | 'disabled'. Never raises."""
    global _BACKEND, _redis
    if not _enabled():
        _BACKEND = "disabled"
        return _BACKEND
    url = (os.getenv("RATELIMIT_REDIS_URL") or os.getenv("REDIS_URL") or "").strip()
    if url:
        try:
            import redis  # type: ignore
            client = redis.Redis.from_url(url, socket_connect_timeout=0.5, socket_timeout=0.5)
            client.ping()
            _redis = client
            _BACKEND = "redis"
            return _BACKEND
        except Exception:  # noqa: BLE001 — no/unreachable redis -> the always-available local counter.
            _redis = None
    _BACKEND = "inproc"
    return _BACKEND


def _deny(route_class: str, reset_in: int = 1) -> Tuple[bool, dict]:
    return False, {"limit": _limit_for(route_class), "remaining": 0, "reset_in": int(reset_in)}


def _allow_inproc(key: str, route_class: str, limit: int) -> Tuple[bool, dict]:
    now = time.time()
    cutoff = now - _WINDOW_S
    with _LOCK:
        if len(_HITS) > _HITS_KEY_CAP:
            for k in list(_HITS.keys())[: _HITS_KEY_CAP // 2]:
                _HITS.pop(k, None)
        dq = _HITS[(key, route_class)]
        while dq and dq[0] < cutoff:
            dq.popleft()
        if len(dq) >= limit:
            reset_in = max(1, int(dq[0] + _WINDOW_S - now)) if dq else 1
            return False, {"limit": limit, "remaining": 0, "reset_in": reset_in}
        dq.append(now)
        return True, {"limit": limit, "remaining": max(0, limit - len(dq)), "reset_in": int(_WINDOW_S)}


def _allow_redis(key: str, route_class: str, limit: int) -> Tuple[bool, dict]:
    # Fixed-window counter in Redis; the first hit of a window sets the TTL. Any Redis error raises
    # to the caller, which decides fail-open/closed by class.
    bucket = int(time.time() // _WINDOW_S)
    rkey = f"rl:{route_class}:{key}:{bucket}"
    pipe = _redis.pipeline()  # type: ignore[union-attr]
    pipe.incr(rkey, 1)
    pipe.expire(rkey, int(_WINDOW_S) + 1)
    count = int(pipe.execute()[0])
    if count > limit:
        return False, {"limit": limit, "remaining": 0, "reset_in": int(_WINDOW_S)}
    return True, {"limit": limit, "remaining": max(0, limit - count), "reset_in": int(_WINDOW_S)}


def allow(key: str, route_class: str) -> Tuple[bool, dict]:
    """Is this request within the ceiling for (key, route_class)? Returns (allowed, info).

    NEVER raises. STRICT classes fail CLOSED (deny) on any uncertainty; normal classes fail OPEN
    (allow) so a limiter glitch can never throttle the live earner.
    """
    rc = str(route_class or "default")
    strict = rc in _STRICT_CLASSES
    try:
        if _BACKEND == "disabled":
            return True, {"limit": 0, "remaining": 0, "reset_in": 0}
        limit = _limit_for(rc)
        if limit <= 0:  # an explicit 0/negative ceiling disables this class.
            return True, {"limit": 0, "remaining": 0, "reset_in": 0}
        k = str(key or "anon")
        if _BACKEND == "redis" and _redis is not None:
            try:
                return _allow_redis(k, rc, limit)
            except Exception:  # noqa: BLE001 — redis blip: fall back to the LOCAL counter (still enforces).
                return _allow_inproc(k, rc, limit)
        return _allow_inproc(k, rc, limit)
    except Exception:  # noqa: BLE001
        # Strict classes must NOT silently re-open on an internal error -> deny. Normal -> allow.
        if strict:
            return _deny(rc)
        return True, {"limit": _limit_for(rc), "remaining": 0, "reset_in": 0}


def route_class(method: str, path: str) -> str:
    """Classify a request into a limit class. caller.py delegates to this so the STRICT public-ingest
    path list is single-sourced HERE (git-tracked), not scattered. Never raises.

    Order matters: the unauth ad-ingest + OAuth surfaces are matched BEFORE the generic read/write
    split so they always get the strict (low) ceiling regardless of HTTP method.
    """
    try:
        p = str(path or "")
        m = (method or "GET").upper()
        if p in _AUTH_PATHS:
            return "auth"
        for pre in _PUBLIC_INGEST_PREFIXES:
            if p.startswith(pre):
                return "public-ingest"
        if p.startswith(_PUBLIC_OAUTH_PREFIX) and p.endswith(_PUBLIC_OAUTH_SUFFIXES):
            return "public-oauth"
        if m in ("POST", "PUT", "PATCH", "DELETE"):
            return "write"
        return "read"
    except Exception:  # noqa: BLE001
        return "default"


def snapshot() -> dict:
    """Diagnostic (never a secret): backend + active key count. Never raises."""
    try:
        with _LOCK:
            return {"backend": _BACKEND, "keys": len(_HITS), "enabled": _enabled()}
    except Exception:  # noqa: BLE001
        return {"backend": _BACKEND}
