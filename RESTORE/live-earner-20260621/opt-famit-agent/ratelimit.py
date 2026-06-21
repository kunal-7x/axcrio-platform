"""ratelimit.py — Famit P0 per-tenant token-bucket rate limiter (ADDITIVE, fail-open).

Per-tenant, per-route-class token bucket. Backed by Redis IF reachable, else an
in-process fallback. CRITICAL DESIGN RULE: this must NEVER block real traffic by
mistake — on ANY internal error (Redis hiccup, bad config, etc.) it FAILS OPEN
(allows the request). It is a guard rail, not a hard gate.

Backend selection (decided once at init):
  * If REDIS reachable at RATELIMIT_REDIS_URL (default redis://127.0.0.1:6380/0 —
    a DEDICATED redis-server on port 6380, NOT LiveKit's redis on 6379) -> use a
    Redis fixed-window counter (atomic INCR + EXPIRE). Shared across workers.
  * Else -> in-process per-tenant counters (best-effort; per-worker only). Still
    useful for a single-worker uvicorn (the live config: --workers 1).

Route classes + default limits (requests / window seconds). Tunable via env
RATELIMIT_<CLASS>=<count>/<seconds>:
  * auth   : 20 / 60     (login/refresh — brute-force guard)
  * write  : 120 / 60    (create/update/delete/run/optout/whatsapp/etc.)
  * read   : 600 / 60    (GET endpoints)
  * default: 300 / 60

Globally toggle with RATELIMIT_ENABLED=false (default true). When disabled, or
when no backend is available AND RATELIMIT_REQUIRE_REDIS is not set, allow() is a
no-op that always returns allowed.
"""
from __future__ import annotations

import os
import time
import threading
from typing import Optional, Tuple

try:
    import redis as _redis_lib
except Exception:  # noqa: BLE001
    _redis_lib = None


# ---- config ----
def _env_bool(key: str, default: bool) -> bool:
    v = os.getenv(key)
    if v is None:
        return default
    return v.strip().lower() not in ("0", "false", "no", "off")


def _parse_limit(spec: str, fallback: Tuple[int, int]) -> Tuple[int, int]:
    """'count/seconds' -> (count, seconds). Bad input -> fallback."""
    try:
        c, s = spec.split("/")
        return max(1, int(c)), max(1, int(s))
    except Exception:  # noqa: BLE001
        return fallback


_DEFAULTS = {
    "auth": (20, 60),
    "write": (120, 60),
    "read": (600, 60),
    "default": (300, 60),
}

ENABLED = _env_bool("RATELIMIT_ENABLED", True)
REDIS_URL = os.getenv("RATELIMIT_REDIS_URL", "redis://127.0.0.1:6380/0")

LIMITS = {cls: _parse_limit(os.getenv(f"RATELIMIT_{cls.upper()}", ""), dflt)
          for cls, dflt in _DEFAULTS.items()}

_redis = None
_backend = "disabled"     # disabled | redis | memory
_mem_lock = threading.Lock()
_mem: dict = {}           # key -> (window_start_epoch, count)


def init() -> str:
    """Pick a backend once. Returns the backend name ('redis'|'memory'|'disabled')."""
    global _redis, _backend
    if not ENABLED:
        _backend = "disabled"
        return _backend
    # Try Redis first.
    if _redis_lib is not None:
        try:
            client = _redis_lib.Redis.from_url(REDIS_URL, socket_connect_timeout=0.5,
                                               socket_timeout=0.5)
            client.ping()
            _redis = client
            _backend = "redis"
            return _backend
        except Exception:  # noqa: BLE001 — Redis absent/unreachable -> fall back
            _redis = None
    _backend = "memory"
    return _backend


def backend() -> str:
    return _backend


def status() -> dict:
    return {"enabled": ENABLED, "backend": _backend, "redis_url": REDIS_URL,
            "limits": {k: f"{v[0]}/{v[1]}s" for k, v in LIMITS.items()}}


def _limit_for(route_class: str) -> Tuple[int, int]:
    return LIMITS.get(route_class, LIMITS["default"])


def allow(tenant_id: str, route_class: str = "default") -> Tuple[bool, dict]:
    """Consume one token for (tenant, route_class) in the current fixed window.
    Returns (allowed, info). FAILS OPEN: any error -> (True, ...). `info` carries
    limit/remaining/reset_in for optional X-RateLimit-* headers / 429 bodies."""
    if not ENABLED or _backend == "disabled":
        return True, {"backend": "disabled"}
    limit, window = _limit_for(route_class)
    tenant_id = tenant_id or "anon"
    now = int(time.time())
    win_start = now - (now % window)
    reset_in = (win_start + window) - now
    key = f"rl:{tenant_id}:{route_class}:{win_start}"

    # ---- Redis backend ----
    if _backend == "redis" and _redis is not None:
        try:
            pipe = _redis.pipeline()
            pipe.incr(key, 1)
            pipe.expire(key, window + 1)
            count = int(pipe.execute()[0])
            allowed = count <= limit
            return allowed, {"backend": "redis", "limit": limit,
                             "remaining": max(0, limit - count), "reset_in": reset_in,
                             "route_class": route_class}
        except Exception:  # noqa: BLE001 — never block on a Redis problem
            return True, {"backend": "redis_error_failopen"}

    # ---- in-process backend ----
    try:
        with _mem_lock:
            ws, count = _mem.get(key, (win_start, 0))
            if ws != win_start:
                ws, count = win_start, 0
            count += 1
            _mem[key] = (ws, count)
            # opportunistic cleanup of stale windows to bound memory
            if len(_mem) > 4096:
                for k in [k for k, (s, _) in _mem.items() if s < win_start - window]:
                    _mem.pop(k, None)
        allowed = count <= limit
        return allowed, {"backend": "memory", "limit": limit,
                         "remaining": max(0, limit - count), "reset_in": reset_in,
                         "route_class": route_class}
    except Exception:  # noqa: BLE001
        return True, {"backend": "memory_error_failopen"}
