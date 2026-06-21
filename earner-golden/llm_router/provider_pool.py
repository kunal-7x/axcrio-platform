"""llm_router/provider_pool.py — SMART per-provider key pool.

Picks the LEAST-USED, not-in-cooldown key INSTANTLY (O(n) scan over ~15 keys = microseconds).
The moment a key 429s it is marked cooling (TTL from Retry-After) and SKIPPED — NO linear walk of
dead keys, so no added latency and no single key dies while others idle.

Sources of keys, merged on every pick():
  1. .env seed keys (GROQ_API_KEY, GROQ_API_KEY_2.., SARVAM_API_KEY.., SAMBANOVA_API_KEY..,
     OPENROUTER_API_KEY..) — so the system is NEVER keyless even if the store is empty.
  2. the secure hot-reloadable key-store (key_store.get_keys) — keys the founder adds in the panel.

State (cooling_until / pick_count / last_ok_at) is per-key in process memory and SURVIVES a reload:
keys are matched by their secret value, so a panel add/remove never resets a surviving key's cooldown.

Pure stdlib. Lock-guarded. Used by aim_voice_agent.py (LLM + STT) and caller.py (/status route).
NEVER touches agent.py / trunks / firewall / SIP.
"""
from __future__ import annotations

import hashlib
import os
import threading
import time
from typing import Optional

try:
    from . import key_store as _key_store
except Exception:  # noqa: BLE001 — pool still works on .env seed keys alone
    _key_store = None  # type: ignore

DEFAULT_COOLDOWN = float(os.getenv("PROVIDER_POOL_COOLDOWN", "60"))   # seconds, when no Retry-After
MAX_COOLDOWN = float(os.getenv("PROVIDER_POOL_MAX_COOLDOWN", "3600"))  # cap a wild Retry-After


def _env_seed(bases: list[str]) -> list[str]:
    """Collect seed keys from .env (BASE, BASE_2 .. BASE_20). Dedup, preserve order."""
    keys: list[str] = []
    for base in bases:
        for name in [base] + [f"{base}_{i}" for i in range(1, 21)]:
            v = (os.getenv(name) or "").strip()
            if v and v not in keys:
                keys.append(v)
    return keys


def _kid(key: str) -> str:
    """Stable short id for an .env-seed key (store keys carry their own id)."""
    return "env_" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:10]


class ProviderPool:
    """Cooldown-aware, least-used key selector for ONE provider."""

    def __init__(self, provider: str, env_bases: list[str]):
        self.provider = provider
        self.env_bases = env_bases
        self._lock = threading.Lock()
        # id -> state dict {key,id,label,enabled,cooling_until,pick_count,last_ok_at,last_429_at,source}
        self._keys: dict[str, dict] = {}
        self._reconcile()

    # ── reconcile env-seed + hot store into the live key map ──────────────────────
    def _reconcile(self) -> None:
        """Merge .env seed keys + key-store keys. Preserve cooldown/pick_count for surviving keys
        (matched on the secret value). Drop keys no longer present anywhere. Lock held by caller."""
        wanted: dict[str, dict] = {}   # id -> {key,label,enabled,source}

        # 1) .env seed keys — always present (system never keyless). enabled=True.
        for k in _env_seed(self.env_bases):
            wanted[_kid(k)] = {"key": k, "label": "env", "enabled": True, "source": "env"}

        # 2) hot store keys (panel-managed) — may disable/override. store id wins.
        if _key_store is not None:
            try:
                for x in _key_store.get_keys(self.provider):
                    k = (x.get("key") or "").strip()
                    if not k:
                        continue
                    wanted[x.get("id") or _kid(k)] = {
                        "key": k,
                        "label": x.get("label", ""),
                        "enabled": bool(x.get("enabled", True)),
                        "source": "store",
                    }
            except Exception:  # noqa: BLE001 — store glitch must never break the pool
                pass

        # carry over runtime state for keys that survive (match by secret value)
        # Per secret, keep the MOST-protective prior state: a secret may have 2 live copies
        # (env + store); on reconcile we must NOT lose a cooldown set on one of them, else a
        # 429'd key re-enters rotation immediately and the pool re-picks a dead key forever.
        by_value: dict[str, dict] = {}
        for st in self._keys.values():
            prev = by_value.get(st["key"])
            if (prev is None
                    or st["cooling_until"] > prev["cooling_until"]
                    or st["pick_count"] > prev["pick_count"]):
                by_value[st["key"]] = st
        new_map: dict[str, dict] = {}
        for kid, meta in wanted.items():
            prev = by_value.get(meta["key"])
            new_map[kid] = {
                "id": kid,
                "key": meta["key"],
                "label": meta["label"],
                "enabled": meta["enabled"],
                "source": meta["source"],
                "cooling_until": prev["cooling_until"] if prev else 0.0,
                "pick_count": prev["pick_count"] if prev else 0,
                "last_ok_at": prev["last_ok_at"] if prev else 0.0,
                "last_429_at": prev["last_429_at"] if prev else 0.0,
            }
        self._keys = new_map

    # ── selection ────────────────────────────────────────────────────────────────
    def pick(self) -> Optional[dict]:
        """Return the AVAILABLE key (enabled AND not cooling) with the LOWEST pick_count,
        tie-broken by oldest last_ok_at. Increments its pick_count. None if ALL cooling/disabled.
        Reconciles the hot store FIRST so a panel-added key enters rotation immediately."""
        with self._lock:
            self._reconcile()
            now = time.time()
            avail = [st for st in self._keys.values()
                     if st["enabled"] and now >= st["cooling_until"]]
            if not avail:
                return None
            avail.sort(key=lambda s: (s["pick_count"], s["last_ok_at"]))
            chosen = avail[0]
            chosen["pick_count"] += 1
            # shallow copy so callers can't mutate internal state
            return dict(chosen)

    def mark_429(self, key: str, retry_after: Optional[float] = None) -> None:
        """Mark a key cooling. cooling_until = now + (retry_after or DEFAULT), capped at MAX."""
        cool = DEFAULT_COOLDOWN
        if retry_after is not None:
            try:
                cool = max(1.0, min(float(retry_after), MAX_COOLDOWN))
            except Exception:  # noqa: BLE001
                cool = DEFAULT_COOLDOWN
        now = time.time()
        with self._lock:
            # cool EVERY copy of this secret (the same key may appear twice: env seed +
            # panel hot-store) so a re-pick can't land on an un-cooled twin of a dead key.
            for st in self._keys.values():
                if st["key"] == key:
                    st["cooling_until"] = now + cool
                    st["last_429_at"] = now

    def mark_ok(self, key: str) -> None:
        now = time.time()
        with self._lock:
            for st in self._keys.values():
                if st["key"] == key:
                    st["last_ok_at"] = now
                    # a success clears any lingering cooldown
                    if st["cooling_until"] > now:
                        st["cooling_until"] = 0.0
                    return

    def available_count(self) -> int:
        now = time.time()
        with self._lock:
            return sum(1 for st in self._keys.values()
                       if st["enabled"] and now >= st["cooling_until"])

    def snapshot(self) -> list[dict]:
        """Masked live status for the /admin/provider-keys/status route. No raw key."""
        now = time.time()
        with self._lock:
            self._reconcile()
            out = []
            for st in self._keys.values():
                masked = _key_store.mask(st["key"]) if _key_store else (st["key"][:4] + "…")
                out.append({
                    "id": st["id"],
                    "label": st["label"],
                    "masked": masked,
                    "source": st["source"],
                    "enabled": st["enabled"],
                    "available": st["enabled"] and now >= st["cooling_until"],
                    "cooling": st["cooling_until"] > now,
                    "cooling_until": round(st["cooling_until"], 1),
                    "cooldown_remaining_s": max(0, round(st["cooling_until"] - now, 1)),
                    "pick_count": st["pick_count"],
                    "last_ok_at": round(st["last_ok_at"], 1),
                    "last_429_at": round(st["last_429_at"], 1),
                })
            out.sort(key=lambda x: (not x["available"], x["pick_count"]))
            return out


# ── module-level singletons (one per provider) ─────────────────────────────────────
GROQ_POOL = ProviderPool("groq", ["GROQ_API_KEY"])
SARVAM_POOL = ProviderPool("sarvam", ["SARVAM_API_KEY"])
SAMBANOVA_POOL = ProviderPool("sambanova", ["SAMBANOVA_API_KEY", "SAMBACLOUD_API_KEY"])
OPENROUTER_POOL = ProviderPool("openrouter", ["OPENROUTER_API_KEY"])

_POOLS = {
    "groq": GROQ_POOL,
    "sarvam": SARVAM_POOL,
    "sambanova": SAMBANOVA_POOL,
    "openrouter": OPENROUTER_POOL,
}


def get_pool(provider: str) -> Optional[ProviderPool]:
    return _POOLS.get((provider or "").strip().lower())


def parse_retry_after(exc) -> Optional[float]:
    """Best-effort extract a Retry-After (seconds) from a Groq/OpenAI-style 429 exception.
    Looks at .response headers, then the message text ('try again in 14m12s' / '... in 3.5s')."""
    import re
    # 1) headers on the response object
    try:
        resp = getattr(exc, "response", None)
        if resp is not None:
            hdrs = getattr(resp, "headers", None) or {}
            for h in ("retry-after", "Retry-After", "x-ratelimit-reset-tokens",
                      "x-ratelimit-reset-requests"):
                v = hdrs.get(h) if hasattr(hdrs, "get") else None
                if v:
                    m = re.match(r"\s*([\d.]+)\s*(ms|s|m)?", str(v))
                    if m:
                        n = float(m.group(1))
                        unit = (m.group(2) or "s")
                        return n / 1000.0 if unit == "ms" else (n * 60.0 if unit == "m" else n)
    except Exception:  # noqa: BLE001
        pass
    # 2) message text: "Please try again in 14m12.3s" or "in 3.51s"
    try:
        msg = str(getattr(exc, "message", "") or exc)
        m = re.search(r"try again in\s+(?:(\d+)m)?([\d.]+)s", msg)
        if m:
            mins = float(m.group(1) or 0)
            secs = float(m.group(2) or 0)
            return mins * 60.0 + secs
    except Exception:  # noqa: BLE001
        pass
    return None


def is_429(exc) -> bool:
    """True if the exception looks like a rate-limit / 429 (provider-agnostic)."""
    try:
        code = getattr(exc, "status_code", None) or getattr(getattr(exc, "response", None), "status_code", None)
        if code == 429:
            return True
    except Exception:  # noqa: BLE001
        pass
    txt = (str(getattr(exc, "message", "") or "") + " " + str(exc)).lower()
    return "429" in txt or "rate limit" in txt or "rate_limit" in txt or "too many requests" in txt
