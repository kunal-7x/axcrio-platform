"""llm_router/custom_providers.py — SECURE store for CUSTOM (bring-your-own) providers.

PHASE-1 SAFE, ADDITIVE, ISOLATED. This is a SEPARATE store from key_store.py — it deliberately does
NOT overload the live provider-key pool that feeds the earner. A custom provider is a tenant/admin-
registered endpoint: {name, kind(stt|llm|tts), base_url, model, key}. Phase 1 persists + lists +
deletes them and surfaces them in GET /providers so the UI can offer them; actually ROUTING an
outbound call through a custom provider is PHASE-2 / OB-PROV (gated, agent.py edit).

Encrypted-at-rest with the SAME Fernet/AES scheme + the SAME master secret env
(PROVIDER_KEYSTORE_SECRET) as key_store.py; 0600; out of git (var/). Degrades to 0600 plaintext if
cryptography/secret are unavailable. A missing/corrupt file => empty list. Cannot crash the earner
(imported only by caller.py super-admin routes + GET /providers).

Stored shape (decrypted): {"custom": [{id,name,kind,base_url,model,key,enabled,added_at}, ...]}
"""
from __future__ import annotations

import json
import os
import threading
import time
import uuid

_VAR_DIR = os.getenv("FAMIT_VAR", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "var"))
_STORE_ENC = os.path.join(_VAR_DIR, "custom_providers.json.enc")
_STORE_PLAIN = os.path.join(_VAR_DIR, "custom_providers.json")
# Service categories the founder can register. Beyond the three voice-pipeline roles
# (stt/llm/tts) we accept the full set of AI service kinds so ANY provider can be added
# from the control center; the voice agent only consumes stt/llm/tts today, the rest are
# stored for routing/integration use (embeddings, rerank, VAD, telephony/SIP, realtime,
# webhooks, etc.). "other" is the catch-all.
_KINDS = ("stt", "llm", "tts", "embedding", "rerank", "vad", "telephony", "realtime", "webhook", "other")

_LOCK = threading.RLock()
_CACHE: list | None = None
_CACHE_MTIME: float = -1.0
_CACHE_PATH: str = ""


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
    except Exception:  # noqa: BLE001
        return []
    items = data.get("custom") if isinstance(data, dict) else data
    if not isinstance(items, list):
        return []
    return [x for x in items if isinstance(x, dict) and x.get("id")]


def _atomic_write(path: str, items: list) -> None:
    os.makedirs(_VAR_DIR, exist_ok=True)
    payload = json.dumps({"custom": items}, ensure_ascii=False).encode("utf-8")
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
    global _CACHE, _CACHE_MTIME, _CACHE_PATH
    path = _store_path()
    try:
        mtime = os.stat(path).st_mtime
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


def list_masked() -> list:
    """Raw key NEVER returned — only masked. For GET /admin/custom-providers + GET /providers."""
    out = []
    for x in _load_cached():
        out.append({
            "id": x.get("id"),
            "name": x.get("name", ""),
            "kind": x.get("kind", ""),
            "base_url": x.get("base_url", ""),
            "model": x.get("model", ""),
            "enabled": bool(x.get("enabled", True)),
            "added_at": x.get("added_at", ""),
            "logo_url": x.get("logo_url", ""),
            "masked": mask(x.get("key", "")),
            "available": bool(x.get("enabled", True)) and bool((x.get("key") or "").strip()),
        })
    return out


def add(name: str, kind: str, base_url: str, model: str, key: str = "", logo_url: str = "") -> dict:
    """Register a custom provider. Returns {id, name, kind, masked}. Raises ValueError on bad input."""
    nm = (name or "").strip()
    k = (kind or "").strip().lower()
    bu = (base_url or "").strip()
    md = (model or "").strip()
    ky = (key or "").strip()
    if not nm:
        raise ValueError("name required")
    if k not in _KINDS:
        raise ValueError("kind must be one of " + "|".join(_KINDS))
    if not bu:
        raise ValueError("base_url required")
    # model is OPTIONAL — some STT/TTS providers have no model id; store "" when absent.
    with _LOCK:
        items = _decrypt_load(_store_path())
        cid = "cp_" + uuid.uuid4().hex[:10]
        items.append({
            "id": cid, "name": nm, "kind": k, "base_url": bu, "model": md, "key": ky,
            "logo_url": (logo_url or "").strip(),
            "enabled": True, "added_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        })
        _atomic_write(_store_path(), items)
    return {"id": cid, "name": nm, "kind": k, "model": md, "masked": mask(ky)}


def update(cid: str, enabled=None, label=None, base_url=None, model=None, key=None) -> dict:
    """Toggle enabled / update base_url|model|key|name by id."""
    cid = (cid or "").strip()
    found = False
    with _LOCK:
        items = _decrypt_load(_store_path())
        for x in items:
            if x.get("id") == cid:
                if enabled is not None:
                    x["enabled"] = bool(enabled)
                if label is not None:
                    x["name"] = str(label).strip() or x.get("name", "")
                if base_url is not None and str(base_url).strip():
                    x["base_url"] = str(base_url).strip()
                if model is not None and str(model).strip():
                    x["model"] = str(model).strip()
                if key is not None and str(key).strip():
                    x["key"] = str(key).strip()
                found = True
        if found:
            _atomic_write(_store_path(), items)
    return {"ok": found, "id": cid}


def delete(cid: str) -> dict:
    cid = (cid or "").strip()
    deleted = False
    with _LOCK:
        items = _decrypt_load(_store_path())
        before = len(items)
        items = [x for x in items if x.get("id") != cid]
        if len(items) != before:
            deleted = True
            _atomic_write(_store_path(), items)
    return {"ok": deleted, "deleted": deleted, "id": cid}
