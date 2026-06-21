"""context_store.py — W2: full-context campaign cache + version-stamp invalidation (inbound, earner-safe).

WHAT THIS IS
------------
The inbound voice brain (aim_voice_agent.py / voice_tools.py) needs the vendor's FULL campaign context
(the `fields` dict + the rendered `system_prompt`) at call-connect. Today every connect re-reads it over
HTTP/disk. This module gives a tenant-scoped, in-process LRU cache (TTL 300s) keyed `(tenant_id, cid)`
that holds that full context, loaded ONCE at connect during the 200-400ms SIP window so per-turn cost is
~0 (turn-2+ never re-fetches). A campaign edit invalidates the cache IMMEDIATELY via a **version stamp**
(Redis :6380 bus + a disk-mtime fallback), NOT just the 300s TTL — so a compliance-line edit is never
served stale for 5 minutes.

THE THREE TIERS (research §3-B, red-team-corrected)
---------------------------------------------------
  L1  in-process LRU dict (TTL 300s, keyed (tenant_id, cid))      -> sub-µs per-turn read
  L2  Redis :6380 version-stamp bus (cross-process invalidation)  -> NOT the store; only "is my copy stale?"
  L3  PG / disk file (the authoritative campaign record)          -> the loader on a miss

The Redis/version tier is justified for CROSS-PROCESS INVALIDATION ON EDIT, not hot-path latency
(turn-2+ never re-fetches regardless). Redis-down still self-corrects on the next disk-mtime read.

EARNER-SAFE / FLAG-GATED
------------------------
EVERYTHING here is gated behind the `CTX_CACHE` env flag (default "0" -> OFF). When OFF, `is_enabled()`
returns False and the only public consumer contract (`get_campaign_context`) returns None so callers take
TODAY's direct read path, byte-identical. The module has NO import side-effects (no Redis connect at
import; the client is built lazily and only when the flag is on). It NEVER raises into a caller: every
public function swallows and returns a safe value. It NEVER imports caller.py/agent.py/prompt.py/SIP —
the loader is injected by the caller (a plain callable) so this module stays a leaf with zero coupling
to the earner.

INVALIDATION (version stamp — the load-bearing design)
------------------------------------------------------
  * Redis key `ctxver:{tenant_id}:{cid}` = a monotonically-INCR'd integer, bumped on every campaign save.
  * A cache entry records the (redis_ver, disk_mtime_ns) it was built with.
  * `get()` compares the cached stamp to the LIVE stamp (cheap Redis GET + os.stat); if EITHER moved, the
    entry is treated as stale -> miss -> reload via the injected loader. So an edit invalidates on the
    very next connect, independent of the 300s TTL.
  * Redis unreachable -> the disk-mtime leg alone still invalidates on any file rewrite (save_campaign
    does an atomic temp+rename, which changes mtime), so correctness NEVER depends on Redis being up.

TENANT ISOLATION
----------------
Every cache key and every Redis version key is prefixed with `tenant_id` (red-team break #5 — a phone- or
cid-only key recreates the cross-tenant leak). A miss reloads ONLY the (tenant_id, cid) the caller asked
for; the injected loader is responsible for tenant-ownership (it reads the tenant-scoped campaign record).
"""
from __future__ import annotations

import os
import threading
import time
from typing import Any, Callable, Optional, Tuple

try:
    import redis as _redis  # type: ignore
except Exception:  # noqa: BLE001 — redis optional; module must import without it
    _redis = None  # type: ignore


# ───────────────────────── config / flag ─────────────────────────
def _env(name: str, default: str = "") -> str:
    return (os.getenv(name, default) or default).strip()


def is_enabled() -> bool:
    """Master flag. DEFAULT OFF -> the whole module is dormant and callers take today's direct path.
    Read live (not cached at import) so a flag flip is picked up on the next process start."""
    return _env("CTX_CACHE", "0").lower() in ("1", "true", "yes", "on")


_TTL_S = float(_env("CTX_CACHE_TTL", "300") or "300")          # entry freshness ceiling (belt; version is the real gate)
_MAX_ENTRIES = int(_env("CTX_CACHE_MAX", "512") or "512")      # LRU cap (per process; campaigns are small)
_REDIS_URL = _env("RATELIMIT_REDIS_URL", "redis://127.0.0.1:6380/0") or "redis://127.0.0.1:6380/0"
_VER_PREFIX = _env("CTX_CACHE_VER_PREFIX", "ctxver") or "ctxver"


# ───────────────────────── lazy Redis (version bus only) ─────────────────────────
_RC_LOCK = threading.Lock()
_RC: Any = None          # the redis client (or None if unavailable)
_RC_TRIED = False        # built once; if it fails we stop retrying every call


def _redis_client() -> Any:
    """Lazily build ONE redis client for the version bus. Returns None if redis lib is absent or the
    connection can't be made — callers MUST tolerate None (disk-mtime leg covers invalidation). Never
    raises. Short timeouts so a slow/dead Redis can't stall a voice connect."""
    global _RC, _RC_TRIED
    if _redis is None:
        return None
    rc = _RC
    if rc is not None:
        return rc
    with _RC_LOCK:
        if _RC is not None:
            return _RC
        if _RC_TRIED:
            return None
        _RC_TRIED = True
        try:
            cli = _redis.from_url(
                _REDIS_URL,
                socket_connect_timeout=0.5,
                socket_timeout=0.5,
                decode_responses=True,
            )
            cli.ping()
            _RC = cli
            return _RC
        except Exception:  # noqa: BLE001 — Redis optional; fall back to disk-mtime leg
            _RC = None
            return None


def _ver_key(tenant_id: str, cid: str) -> str:
    return f"{_VER_PREFIX}:{tenant_id}:{cid}"


def bump_version(tenant_id: str, cid: str) -> bool:
    """Invalidate (tenant_id, cid) across ALL processes by INCR'ing its Redis version stamp.
    Called by caller.py on campaign create/edit. Idempotent-safe (monotonic counter). Never raises;
    returns True if the bump landed in Redis, False if Redis is down (the disk-mtime leg still
    invalidates locally on the next read, so a False here is non-fatal)."""
    if not (tenant_id and cid):
        return False
    cli = _redis_client()
    if cli is None:
        return False
    try:
        cli.incr(_ver_key(tenant_id, cid))
        return True
    except Exception:  # noqa: BLE001
        return False


def _live_redis_version(tenant_id: str, cid: str) -> Optional[int]:
    """Current Redis version stamp for (tenant_id, cid), or None if Redis is unreachable / unset.
    None means 'no Redis signal' -> the disk-mtime leg decides freshness. Never raises."""
    cli = _redis_client()
    if cli is None:
        return None
    try:
        v = cli.get(_ver_key(tenant_id, cid))
        return int(v) if v is not None else 0
    except Exception:  # noqa: BLE001
        return None


def _disk_mtime_ns(disk_path: Optional[str]) -> int:
    """mtime of the authoritative campaign file in ns (0 if unknown/missing). save_campaign writes via
    atomic temp+rename, which bumps mtime -> this leg invalidates on any rewrite even with Redis down."""
    if not disk_path:
        return 0
    try:
        return os.stat(disk_path).st_mtime_ns
    except Exception:  # noqa: BLE001
        return 0


# ───────────────────────── the LRU cache (L1) ─────────────────────────
# entry value: {"ctx": <full context dict>, "redis_ver": int|None, "mtime": int, "at": float}
_CACHE_LOCK = threading.Lock()
_CACHE: "dict[Tuple[str, str], dict]" = {}
_ORDER: list = []  # LRU recency, most-recent last


def _touch(key: Tuple[str, str]) -> None:
    try:
        _ORDER.remove(key)
    except ValueError:
        pass
    _ORDER.append(key)


def _evict_if_needed() -> None:
    while len(_CACHE) > _MAX_ENTRIES and _ORDER:
        oldest = _ORDER.pop(0)
        _CACHE.pop(oldest, None)


def _stamp_matches(entry: dict, tenant_id: str, cid: str, disk_path: Optional[str]) -> bool:
    """Is the cached entry still the live version? Compares BOTH legs:
      * Redis version: if Redis is reachable AND the live stamp differs from the cached one -> STALE.
        (If Redis is unreachable now, this leg is skipped — disk-mtime decides.)
      * disk mtime: if the authoritative file was rewritten since we cached -> STALE.
    Either leg moving => stale. This is what makes an edit invalidate IMMEDIATELY, not after the TTL."""
    live_redis = _live_redis_version(tenant_id, cid)
    if live_redis is not None and entry.get("redis_ver") is not None:
        if live_redis != entry.get("redis_ver"):
            return False
    live_mtime = _disk_mtime_ns(disk_path)
    if live_mtime and entry.get("mtime") and live_mtime != entry.get("mtime"):
        return False
    return True


def get_campaign_context(
    tenant_id: str,
    cid: str,
    loader: Callable[[], Optional[dict]],
    disk_path: Optional[str] = None,
) -> Optional[dict]:
    """THE public consumer contract. Returns the full campaign context dict for (tenant_id, cid),
    served from the in-process LRU when fresh, else (re)loaded via `loader` and cached.

    EARNER-SAFE: when CTX_CACHE is OFF, returns None immediately so the caller takes today's direct
    read path (byte-identical). When ON and the loader yields nothing, also returns None (caller falls
    back). NEVER raises.

    Args:
      tenant_id : owning tenant (every cache + version key is prefixed with it — isolation).
      cid       : campaign id.
      loader    : a zero-arg callable the CALLER provides that returns the full context dict (the
                  tenant-scoped campaign record: its `fields` + `system_prompt`). Called only on a
                  miss/stale. Keeps this module a leaf — no import of caller.py/prompt.py.
      disk_path : optional path to the authoritative campaign JSON file; enables the disk-mtime
                  invalidation leg (works even when Redis is down).
    """
    if not is_enabled():
        return None
    if not (tenant_id and cid):
        return None
    key = (tenant_id, cid)
    now = time.time()
    # ---- L1 hit path (fast): entry exists, within TTL, and version stamp still matches ----
    try:
        with _CACHE_LOCK:
            entry = _CACHE.get(key)
            if entry is not None and (now - entry.get("at", 0.0)) <= _TTL_S:
                fresh = _stamp_matches(entry, tenant_id, cid, disk_path)
                if fresh:
                    _touch(key)
                    return entry.get("ctx")
                # stale -> drop and reload below (outside the lock so the loader can't deadlock)
                _CACHE.pop(key, None)
                try:
                    _ORDER.remove(key)
                except ValueError:
                    pass
    except Exception:  # noqa: BLE001 — cache must never break a connect
        pass
    # ---- miss / stale -> reload via the injected loader (L3), then cache with the CURRENT stamps ----
    try:
        ctx = loader()
    except Exception:  # noqa: BLE001 — a loader failure must not raise into the connect path
        ctx = None
    if not ctx:
        return None
    try:
        redis_ver = _live_redis_version(tenant_id, cid)
        if redis_ver is None:
            redis_ver = 0  # Redis down at load -> record 0; if it comes back the disk-mtime leg covers us
        mtime = _disk_mtime_ns(disk_path)
        with _CACHE_LOCK:
            _CACHE[key] = {"ctx": ctx, "redis_ver": redis_ver, "mtime": mtime, "at": time.time()}
            _touch(key)
            _evict_if_needed()
    except Exception:  # noqa: BLE001
        pass
    return ctx


def invalidate(tenant_id: str, cid: str) -> None:
    """Drop the local L1 entry AND bump the cross-process Redis version. Caller.py calls this on a
    campaign save so this process (and every other) reloads on the next connect. Never raises."""
    try:
        key = (tenant_id, cid)
        with _CACHE_LOCK:
            _CACHE.pop(key, None)
            try:
                _ORDER.remove(key)
            except ValueError:
                pass
    except Exception:  # noqa: BLE001
        pass
    bump_version(tenant_id, cid)


def stats() -> dict:
    """Lightweight introspection for a health/debug endpoint. Never raises."""
    try:
        with _CACHE_LOCK:
            n = len(_CACHE)
        return {"enabled": is_enabled(), "entries": n, "max": _MAX_ENTRIES,
                "ttl_s": _TTL_S, "redis": _redis_client() is not None}
    except Exception:  # noqa: BLE001
        return {"enabled": is_enabled(), "entries": 0, "max": _MAX_ENTRIES, "ttl_s": _TTL_S, "redis": False}


def _reset_for_tests() -> None:
    """Test-only: clear the L1 cache and force the Redis client to rebuild."""
    global _RC, _RC_TRIED
    with _CACHE_LOCK:
        _CACHE.clear()
        _ORDER.clear()
    with _RC_LOCK:
        _RC = None
        _RC_TRIED = False
