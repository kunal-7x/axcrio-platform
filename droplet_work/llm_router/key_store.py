"""llm_router/key_store.py — SECURE store for the PLATFORM provider-key pool.

The founder-managed keys for the BUILT-IN providers (groq / sarvam / sambanova / openrouter) that the
super-admin adds in the Service Control Center (/super-admin/services). Backs the four
/admin/provider-keys* routes in caller.py; the live AIM rotation HOT-RELOADS these (no redeploy) via
the KeyPool in __init__.py (env-seed keys are blended in there — this store holds ONLY the managed keys).

SIBLING of custom_providers.py — SAME Fernet/AES scheme + the SAME master secret env
(PROVIDER_KEYSTORE_SECRET) + 0600 + out of git (var/). Degrades to 0600 plaintext if
cryptography/secret are unavailable. A missing/corrupt file => empty store. The raw key is NEVER
returned by the masked listing — only a `masked` value; the pool reads secrets internally via
store_keys() (caller.py never calls that).

Stored shape (decrypted): {"keys": [{id, provider, label, key, enabled, added_at, last_ok_at}, ...]}
"""
from __future__ import annotations

import contextlib
import json
import logging
import os
import threading
import time
import uuid

_log = logging.getLogger("llm_router.key_store")

_VAR_DIR = os.getenv("FAMIT_VAR", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "var"))
_STORE_ENC = os.path.join(_VAR_DIR, "provider_keys.json.enc")
_STORE_PLAIN = os.path.join(_VAR_DIR, "provider_keys.json")
_LOCK_FILE = os.path.join(_VAR_DIR, "provider_keys.lock")
# The built-in providers the panel manages. Must mirror caller.py:_PK_PROVIDERS.
PROVIDERS = ("groq", "sarvam", "sambanova", "openrouter")

_LOCK = threading.RLock()
_CACHE: list | None = None
_CACHE_SIG = None  # (st_mtime_ns, st_size) of the last-loaded store file
_CACHE_PATH: str = ""


@contextlib.contextmanager
def _file_lock():
    """Best-effort cross-process EXCLUSIVE lock (POSIX flock on a sidecar file) for the
    read-modify-write in the CRUD ops, so two backend workers can't clobber each other. Always
    acquired INSIDE the thread _LOCK (ordering thread->file is fixed → no deadlock). No-ops where
    fcntl is unavailable; never raises."""
    fd = None
    try:
        import fcntl
        os.makedirs(_VAR_DIR, exist_ok=True)
        fd = os.open(_LOCK_FILE, os.O_RDWR | os.O_CREAT, 0o600)
        fcntl.flock(fd, fcntl.LOCK_EX)
    except Exception:  # noqa: BLE001
        if fd is not None:
            try:
                os.close(fd)
            except Exception:  # noqa: BLE001
                pass
            fd = None
    try:
        yield
    finally:
        if fd is not None:
            try:
                import fcntl
                fcntl.flock(fd, fcntl.LOCK_UN)
            except Exception:  # noqa: BLE001
                pass
            try:
                os.close(fd)
            except Exception:  # noqa: BLE001
                pass


def _fernet():
    secret = (os.getenv("PROVIDER_KEYSTORE_SECRET") or "").strip()
    if not secret:
        return None
    try:
        import base64
        import hashlib
        from cryptography.fernet import Fernet
    except Exception:  # noqa: BLE001
        return None
    digest = hashlib.sha256(secret.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def _store_path() -> str:
    return _STORE_ENC if _fernet() is not None else _STORE_PLAIN


def mask(key: str) -> str:
    k = (key or "").strip()
    if len(k) <= 10:
        return (k[:3] + "…") if k else ""
    return f"{k[:4]}…{k[-4:]}"


def _decrypt_load(path: str) -> list:
    try:
        with open(path, "rb") as fh:
            raw = fh.read()
    except FileNotFoundError:
        return []
    except Exception:  # noqa: BLE001
        return []
    if not raw:
        return []
    f = _fernet()
    try:
        if f is not None and path == _STORE_ENC:
            raw = f.decrypt(raw)
        data = json.loads(raw.decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        # Present-but-unreadable almost always means PROVIDER_KEYSTORE_SECRET was rotated. Don't let
        # the keys vanish without a trace — leave an audit breadcrumb (we still degrade to empty).
        _log.warning("provider key-store %s unreadable (%s) — treating as EMPTY; if "
                     "PROVIDER_KEYSTORE_SECRET was changed, restore the prior secret to recover keys.",
                     path, type(exc).__name__)
        return []
    items = data.get("keys") if isinstance(data, dict) else data
    if not isinstance(items, list):
        return []
    return [x for x in items if isinstance(x, dict) and x.get("id") and x.get("provider")]


def _atomic_write(path: str, items: list) -> None:
    os.makedirs(_VAR_DIR, exist_ok=True)
    payload = json.dumps({"keys": items}, ensure_ascii=False).encode("utf-8")
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
    os.replace(tmp, path)
    try:
        os.chmod(path, 0o600)
    except Exception:  # noqa: BLE001
        pass


def _load_cached() -> list:
    global _CACHE, _CACHE_SIG, _CACHE_PATH
    path = _store_path()
    try:
        st = os.stat(path)
        sig = (st.st_mtime_ns, st.st_size)  # ns + size: two writes in the same second still invalidate
    except Exception:  # noqa: BLE001
        sig = (0, 0)
    with _LOCK:
        if _CACHE is not None and sig == _CACHE_SIG and path == _CACHE_PATH:
            return _CACHE
        data = _decrypt_load(path)
        _CACHE = data
        _CACHE_SIG = sig
        _CACHE_PATH = path
        return data


# ── public API consumed by caller.py /admin/provider-keys* routes ───────────────────────────────
def list_all_masked() -> dict:
    """{provider: [{id,label,enabled,added_at,last_ok_at,masked}, ...]} — store keys only (managed,
    deletable). Env-seeded keys are server-config and surface only in the pool snapshot, not here.
    Raw key NEVER returned."""
    out: dict = {p: [] for p in PROVIDERS}
    for x in _load_cached():
        p = x.get("provider")
        if p in out:
            out[p].append({
                "id": x.get("id"),
                "label": x.get("label", ""),
                "enabled": bool(x.get("enabled", True)),
                "added_at": x.get("added_at", ""),
                "last_ok_at": x.get("last_ok_at", 0),
                "masked": mask(x.get("key", "")),
            })
    return out


def add_key(provider: str, key: str, label: str = "") -> dict:
    """Add a managed key. Returns {id, provider, masked, deduped}. Dedups on exact secret per
    provider (re-adding the same key is a no-op that returns the existing id). Raises ValueError on
    bad input."""
    p = (provider or "").strip().lower()
    ky = (key or "").strip()
    if p not in PROVIDERS:
        raise ValueError("unknown provider")
    if not ky:
        raise ValueError("empty key")
    with _LOCK, _file_lock():
        items = _decrypt_load(_store_path())
        for x in items:
            if x.get("provider") == p and (x.get("key") or "").strip() == ky:
                return {"id": x.get("id"), "provider": p, "masked": mask(ky), "deduped": True}
        kid = "pk_" + uuid.uuid4().hex[:10]
        items.append({
            "id": kid, "provider": p, "label": (label or "").strip(), "key": ky,
            "enabled": True, "added_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "last_ok_at": 0,
        })
        _atomic_write(_store_path(), items)
    return {"id": kid, "provider": p, "masked": mask(ky), "deduped": False}


def update_key(key_id: str, enabled=None, label=None) -> dict:
    """Toggle enabled / relabel by id. Never edits the secret. Returns {ok, id}."""
    kid = (key_id or "").strip()
    found = False
    with _LOCK, _file_lock():
        items = _decrypt_load(_store_path())
        for x in items:
            if x.get("id") == kid:
                if enabled is not None:
                    x["enabled"] = bool(enabled)
                if label is not None:
                    x["label"] = str(label).strip()
                found = True
        if found:
            _atomic_write(_store_path(), items)
    return {"ok": found, "id": kid}


def delete_key(key_id: str) -> dict:
    """Delete a managed key by id. Returns {ok, deleted, id}."""
    kid = (key_id or "").strip()
    deleted = False
    with _LOCK, _file_lock():
        items = _decrypt_load(_store_path())
        before = len(items)
        items = [x for x in items if x.get("id") != kid]
        if len(items) != before:
            deleted = True
            _atomic_write(_store_path(), items)
    return {"ok": deleted, "deleted": deleted, "id": kid}


# ── internal: the pool reads decrypted store keys (WITH secret). NOT an API route. ───────────────
def store_keys(provider: str) -> list:
    """[{id,label,key,enabled,added_at,last_ok_at}, ...] for one provider — secret included.
    Used ONLY by the in-process KeyPool (llm_router/__init__.py). Never exposed over HTTP."""
    p = (provider or "").strip().lower()
    return [dict(x) for x in _load_cached() if x.get("provider") == p]
