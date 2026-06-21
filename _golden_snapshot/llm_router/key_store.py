"""llm_router/key_store.py — SECURE, HOT-RELOADABLE provider key-store.

Stores PLATFORM provider keys (Groq / Sarvam / SambaNova / OpenRouter) added by the super-admin
in the panel. Encrypted-at-rest (Fernet/AES) with a master key in .env; root/famit-readable only;
NEVER in git (lives under the gitignored var/). Atomic writes bump the file mtime so the live pool
reloads the new key on the very next pick() — true hot-reload, no restart.

Decrypted shape:
    {
      "groq":       [{"id","key","label","enabled","added_at","last_ok_at","cooling_until"}, ...],
      "sarvam":     [...],
      "sambanova":  [...],
      "openrouter": [...]
    }

DEGRADE-SAFE: if `cryptography` is missing OR PROVIDER_KEYSTORE_SECRET is unset, falls back to a
0600 PLAINTEXT json file (still root-only, still out of git). Either way the API + pool work.
A missing/corrupt file => empty stores (the .env seed keys still feed the pool, so never keyless).
"""
from __future__ import annotations

import json
import os
import threading
import time
import uuid

# ── config ──────────────────────────────────────────────────────────────────────
_VAR_DIR = os.getenv("FAMIT_VAR", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "var"))
_STORE_ENC = os.path.join(_VAR_DIR, "provider_keys.json.enc")
_STORE_PLAIN = os.path.join(_VAR_DIR, "provider_keys.json")
_PROVIDERS = ("groq", "sarvam", "sambanova", "openrouter")

_LOCK = threading.RLock()
_CACHE: dict | None = None
_CACHE_MTIME: float = -1.0
_CACHE_PATH: str = ""

# ── encryption (optional) ─────────────────────────────────────────────────────────
def _fernet():
    """Return a Fernet instance if cryptography + secret are available, else None (plaintext mode)."""
    secret = (os.getenv("PROVIDER_KEYSTORE_SECRET") or "").strip()
    if not secret:
        return None
    try:
        import base64
        import hashlib
        from cryptography.fernet import Fernet
    except Exception:  # noqa: BLE001
        return None
    # Derive a stable 32-byte urlsafe key from the secret (so the secret can be any string).
    digest = hashlib.sha256(secret.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def _store_path() -> str:
    """Encrypted path if encryption is active, else the plaintext path."""
    return _STORE_ENC if _fernet() is not None else _STORE_PLAIN


def mask(key: str) -> str:
    """gsk_xxxx…AB12 — never expose the full secret to the UI/logs."""
    k = (key or "").strip()
    if len(k) <= 10:
        return (k[:3] + "…") if k else ""
    return f"{k[:4]}…{k[-4:]}"


# ── low-level read/write ───────────────────────────────────────────────────────────
def _empty() -> dict:
    return {p: [] for p in _PROVIDERS}


def _decrypt_load(path: str) -> dict:
    try:
        with open(path, "rb") as fh:
            raw = fh.read()
    except FileNotFoundError:
        return _empty()
    except Exception:  # noqa: BLE001
        return _empty()
    if not raw:
        return _empty()
    f = _fernet()
    try:
        if f is not None and path == _STORE_ENC:
            raw = f.decrypt(raw)
        data = json.loads(raw.decode("utf-8"))
    except Exception:  # noqa: BLE001 — corrupt/garbled => empty (seed keys still work)
        return _empty()
    out = _empty()
    if isinstance(data, dict):
        for p in _PROVIDERS:
            v = data.get(p)
            if isinstance(v, list):
                out[p] = [x for x in v if isinstance(x, dict) and x.get("key")]
    return out


def _atomic_write(path: str, data: dict) -> None:
    os.makedirs(_VAR_DIR, exist_ok=True)
    payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
    f = _fernet()
    if f is not None and path == _STORE_ENC:
        payload = f.encrypt(payload)
    tmp = f"{path}.tmp.{os.getpid()}.{uuid.uuid4().hex[:6]}"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(payload)
            fh.flush()
            os.fsync(fh.fileno())
    except Exception:
        try:
            os.close(fd)
        except Exception:  # noqa: BLE001
            pass
        raise
    os.replace(tmp, path)          # atomic; bumps mtime => loader reloads on next get_keys()
    try:
        os.chmod(path, 0o600)
    except Exception:  # noqa: BLE001
        pass


def _load_cached() -> dict:
    """mtime-cached decrypt. stat() is microseconds — safe to call per pick()."""
    global _CACHE, _CACHE_MTIME, _CACHE_PATH
    path = _store_path()
    try:
        mtime = os.stat(path).st_mtime
    except FileNotFoundError:
        mtime = 0.0
    except Exception:  # noqa: BLE001
        mtime = 0.0
    with _LOCK:
        if _CACHE is not None and mtime == _CACHE_MTIME and path == _CACHE_PATH:
            return _CACHE
        data = _decrypt_load(path)
        _CACHE = data
        _CACHE_MTIME = mtime
        _CACHE_PATH = path
        return data


# ── public API ─────────────────────────────────────────────────────────────────────
def get_keys(provider: str) -> list[dict]:
    """Return the stored key dicts for a provider (hot-reloaded via mtime cache)."""
    p = (provider or "").strip().lower()
    if p not in _PROVIDERS:
        return []
    return list(_load_cached().get(p, []))


def list_all_masked() -> dict:
    """For the GET /admin/provider-keys route — raw key NEVER returned, only masked."""
    data = _load_cached()
    out: dict = {}
    for p in _PROVIDERS:
        out[p] = [{
            "id": x.get("id"),
            "label": x.get("label", ""),
            "enabled": bool(x.get("enabled", True)),
            "added_at": x.get("added_at", ""),
            "last_ok_at": x.get("last_ok_at", 0),
            "masked": mask(x.get("key", "")),
        } for x in data.get(p, [])]
    return out


def add_key(provider: str, key: str, label: str = "") -> dict:
    """Add a key. Trims; dedups by exact value within the provider; returns {id, provider, masked}."""
    p = (provider or "").strip().lower()
    if p not in _PROVIDERS:
        raise ValueError("unknown provider")
    k = (key or "").strip()
    if not k:
        raise ValueError("empty key")
    with _LOCK:
        data = _decrypt_load(_store_path())   # read fresh (avoid stale cache on write)
        existing = data.setdefault(p, [])
        for x in existing:
            if x.get("key") == k:
                return {"id": x.get("id"), "provider": p, "masked": mask(k), "deduped": True}
        kid = uuid.uuid4().hex[:12]
        existing.append({
            "id": kid, "key": k, "label": (label or "").strip(),
            "enabled": True, "added_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "last_ok_at": 0, "cooling_until": 0,
        })
        _atomic_write(_store_path(), data)
    return {"id": kid, "provider": p, "masked": mask(k)}


def update_key(key_id: str, enabled=None, label=None) -> dict:
    """Toggle enabled / relabel by id (never edits the secret)."""
    kid = (key_id or "").strip()
    found = False
    with _LOCK:
        data = _decrypt_load(_store_path())
        for p in _PROVIDERS:
            for x in data.get(p, []):
                if x.get("id") == kid:
                    if enabled is not None:
                        x["enabled"] = bool(enabled)
                    if label is not None:
                        x["label"] = str(label).strip()
                    found = True
        if found:
            _atomic_write(_store_path(), data)
    return {"ok": found, "id": kid}


def delete_key(key_id: str) -> dict:
    kid = (key_id or "").strip()
    deleted = False
    with _LOCK:
        data = _decrypt_load(_store_path())
        for p in _PROVIDERS:
            before = len(data.get(p, []))
            data[p] = [x for x in data.get(p, []) if x.get("id") != kid]
            if len(data[p]) != before:
                deleted = True
        if deleted:
            _atomic_write(_store_path(), data)
    return {"ok": deleted, "deleted": deleted, "id": kid}
