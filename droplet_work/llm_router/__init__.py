"""llm_router — platform LLM/STT provider-key rotation (LPR).

Exposes the per-provider KeyPool singletons the live AIM agent rotates through
(GROQ_POOL / SARVAM_POOL / SAMBANOVA_POOL / OPENROUTER_POOL) + get_pool() for the super-admin
/admin/provider-keys/status + /providers routes, and re-exports the key_store submodule.

A pool blends ENV-seeded keys (BASE, BASE_2..BASE_20 — source='env', server-config, always enabled)
with HOT-RELOADED store keys (source='store', founder-managed via the panel). pick() returns the
least-used, not-cooling key; a 429 puts a key on a short cooldown so it is skipped instantly instead
of stalling a call. Store keys are re-read on every access (mtime-cached in key_store) — adding a key
in the panel goes live with no redeploy.

BULLETPROOF AT IMPORT: every name binding here is guarded so a hiccup can NEVER break
`from llm_router import custom_providers / tiers / key_store` (which the earner & caller.py need).
The KeyPool itself only manipulates strings + an in-memory dict, so it cannot raise at build time.
"""
from __future__ import annotations

import os
import threading
import time

try:
    from . import key_store  # noqa: F401  (pure stdlib + guarded crypto — safe to import)
except Exception:  # noqa: BLE001  — never let a key_store hiccup break the package import
    key_store = None  # type: ignore

# Default 429 cooldown (s). A rate-limited key is skipped for this long, then auto-returns to rotation.
_COOLDOWN_S = 60.0
try:
    _COOLDOWN_S = float(os.getenv("LPR_COOLDOWN_S", "60") or 60)
except Exception:  # noqa: BLE001
    _COOLDOWN_S = 60.0


def _env_keys(base: str) -> list:
    """BASE, BASE_2 .. BASE_20 — mirrors aim_voice_agent._collect_keys (multi-account env seed)."""
    out: list = []
    for name in [base] + [f"{base}_{i}" for i in range(2, 21)]:
        v = (os.getenv(name) or "").strip()
        if v and v not in out:
            out.append(v)
    return out


def _mask(k: str) -> str:
    if key_store is not None:
        try:
            return key_store.mask(k)
        except Exception:  # noqa: BLE001
            pass
    k = (k or "").strip()
    if len(k) <= 10:
        return (k[:3] + "…") if k else ""
    return f"{k[:4]}…{k[-4:]}"


class KeyPool:
    """Runtime rotation view over one provider's keys (env-seed + managed store). Thread-safe.
    Stats (pick_count / cooldown / last_ok / last_429) live in memory keyed by the secret, so they
    survive store reloads and never persist a secret-derived value to disk."""

    def __init__(self, provider: str, env_base: str):
        self.provider = provider
        self.env_base = env_base
        self._lock = threading.RLock()
        self._stats: dict = {}  # secret -> {pick_count, last_ok_at, last_429_at, cooling_until}

    # -- membership: env keys first (server-config), then managed store keys; deduped by secret --
    def _members(self) -> list:
        seen: set = set()
        members: list = []
        for i, k in enumerate(_env_keys(self.env_base)):
            if k in seen:
                continue
            seen.add(k)
            eid = f"env:{self.env_base}" if i == 0 else f"env:{self.env_base}_{i + 1}"
            members.append({"id": eid, "label": "server-config", "key": k, "enabled": True, "source": "env"})
        if key_store is not None:
            try:
                for x in key_store.store_keys(self.provider):
                    k = (x.get("key") or "").strip()
                    if not k or k in seen:
                        continue
                    seen.add(k)
                    members.append({
                        "id": x.get("id"), "label": (x.get("label") or "") or "managed",
                        "key": k, "enabled": bool(x.get("enabled", True)), "source": "store",
                    })
            except Exception:  # noqa: BLE001
                pass
        return members

    def _secret_for(self, key_or_id: str):
        """Resolve a pick()-returned secret OR a member id to its secret. None if it matches no
        current member — mark_ok/mark_429 then no-op, so a buggy/stale caller can't grow _stats
        unbounded with junk entries."""
        if not key_or_id:
            return None
        for m in self._members():
            if m["key"] == key_or_id or m["id"] == key_or_id:
                return m["key"]
        return None

    def _is_cooling(self, secret: str, now: float) -> bool:
        st = self._stats.get(secret)
        return bool(st and st.get("cooling_until", 0) > now)

    def pick(self):
        """Least-used, not-cooling enabled key -> {id, key, source, label}. If every key is cooling,
        return the least-used enabled key anyway (a throttled key beats dead air). None if no keys."""
        now = time.time()
        with self._lock:
            members = self._members()
            ready = [m for m in members if m["enabled"] and not self._is_cooling(m["key"], now)]
            pool = ready or [m for m in members if m["enabled"]]
            if not pool:
                return None
            pool.sort(key=lambda m: self._stats.get(m["key"], {}).get("pick_count", 0))
            chosen = pool[0]
            st = self._stats.setdefault(chosen["key"], {})
            st["pick_count"] = st.get("pick_count", 0) + 1
            return {"id": chosen["id"], "key": chosen["key"], "source": chosen["source"], "label": chosen["label"]}

    def available_count(self) -> int:
        now = time.time()
        with self._lock:
            return sum(1 for m in self._members() if m["enabled"] and not self._is_cooling(m["key"], now))

    def mark_ok(self, key_or_id: str) -> None:
        try:
            with self._lock:
                sec = self._secret_for(key_or_id)
                if sec is None:
                    return
                st = self._stats.setdefault(sec, {})
                st["last_ok_at"] = int(time.time())
                st["cooling_until"] = 0  # a success clears any cooldown
        except Exception:  # noqa: BLE001
            pass

    def mark_429(self, key_or_id: str, cooldown_s: float | None = None) -> None:
        try:
            with self._lock:
                sec = self._secret_for(key_or_id)
                if sec is None:
                    return
                now = time.time()
                st = self._stats.setdefault(sec, {})
                st["last_429_at"] = int(now)
                st["cooling_until"] = now + float(cooldown_s if cooldown_s is not None else _COOLDOWN_S)
        except Exception:  # noqa: BLE001
            pass

    def reload(self) -> None:
        """No-op: _members() re-reads the store (mtime-cached) on every call, so the pool is always
        live. Present for callers that expect an explicit refresh hook."""
        return None

    def snapshot(self) -> list:
        """Per-key live status for /admin/provider-keys/status (matches ProviderKeyStatusRow).
        Masked only — no raw secret."""
        now = time.time()
        out: list = []
        with self._lock:
            for m in self._members():
                st = self._stats.get(m["key"], {})
                cu = float(st.get("cooling_until", 0) or 0)
                cooling = cu > now
                out.append({
                    "id": m["id"], "label": m["label"], "masked": _mask(m["key"]), "source": m["source"],
                    "enabled": bool(m["enabled"]),
                    "available": bool(m["enabled"] and not cooling),
                    "cooling": cooling,
                    "cooling_until": cu,
                    "cooldown_remaining_s": max(0.0, cu - now),
                    "pick_count": int(st.get("pick_count", 0)),
                    "last_ok_at": int(st.get("last_ok_at", 0)),
                    "last_429_at": int(st.get("last_429_at", 0)),
                })
        return out


def _build_pools() -> dict:
    try:
        return {
            "groq": KeyPool("groq", "GROQ_API_KEY"),
            "sarvam": KeyPool("sarvam", "SARVAM_API_KEY"),
            "sambanova": KeyPool("sambanova", "SAMBANOVA_API_KEY"),
            "openrouter": KeyPool("openrouter", "OPENROUTER_API_KEY"),
        }
    except Exception:  # noqa: BLE001
        return {}


_POOLS = _build_pools()
GROQ_POOL = _POOLS.get("groq")
SARVAM_POOL = _POOLS.get("sarvam")
SAMBANOVA_POOL = _POOLS.get("sambanova")
OPENROUTER_POOL = _POOLS.get("openrouter")


def get_pool(provider: str):
    """KeyPool for a built-in provider id (groq/sarvam/sambanova/openrouter) or None."""
    return _POOLS.get((provider or "").strip().lower())


__all__ = [
    "key_store", "KeyPool", "get_pool",
    "GROQ_POOL", "SARVAM_POOL", "SAMBANOVA_POOL", "OPENROUTER_POOL",
]
