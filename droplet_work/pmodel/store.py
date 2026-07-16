"""pmodel.store — durable, tenant-scoped project store (JSON files, atomic write).

Mirrors the campaigns JSON-store convention in caller.py. One file per project at
FAMIT_VAR/pmodel/{id}.json. No DB needed. Tenant isolation is enforced by the
router (every read/write filters on tenant_id); this layer just persists.
"""
from __future__ import annotations

import json
import os
import secrets
import tempfile
import time
import uuid
from pathlib import Path

VAR = Path(os.getenv("FAMIT_VAR", "/opt/famit-agent/var"))
PDIR = VAR / "pmodel"


def _safe(pid: str) -> str:
    return "".join(c for c in (pid or "") if c.isalnum() or c in "-_")[:48]


def _path(pid: str) -> Path:
    PDIR.mkdir(parents=True, exist_ok=True)
    return PDIR / f"{_safe(pid)}.json"


def new_project(tenant_id: str, name: str, source: str = "") -> dict:
    pid = uuid.uuid4().hex[:10]
    rec = {
        "id": pid,
        "tenant_id": tenant_id,
        "name": (name or "Untitled property").strip()[:80],
        "source": source,            # "image" | "text" | "sample"
        "state": "draft",            # draft | ready | failed
        "plan_key": "",              # Spaces key of the source plan image (if any)
        "scene_key": "",             # Spaces key of the scene JSON (if any)
        "schema": None,              # normalized PropertyLayout
        "scene": None,               # render-ready SceneSpec
        "share_token": secrets.token_urlsafe(9),
        "public": False,
        "created_at": time.time(),
        "updated_at": time.time(),
    }
    save(rec)
    return rec


def get(pid: str) -> dict | None:
    p = _path(pid)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text("utf-8"))
    except Exception:
        return None


def get_by_token(token: str) -> dict | None:
    token = (token or "").strip()
    if not token:
        return None
    PDIR.mkdir(parents=True, exist_ok=True)
    for f in PDIR.glob("*.json"):
        try:
            r = json.loads(f.read_text("utf-8"))
        except Exception:
            continue
        if r.get("share_token") == token:
            return r
    return None


def save(rec: dict) -> None:
    rec["updated_at"] = time.time()
    p = _path(rec["id"])
    fd, tmp = tempfile.mkstemp(dir=str(p.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(rec, f, indent=2)
        os.replace(tmp, str(p))  # atomic
    finally:
        if os.path.exists(tmp):
            try:
                os.unlink(tmp)
            except Exception:
                pass


def delete(pid: str) -> bool:
    p = _path(pid)
    if p.exists():
        try:
            p.unlink()
            return True
        except Exception:
            return False
    return False


def _summary(r: dict) -> dict:
    sc_meta = (r.get("scene") or {}).get("meta") or {}
    return {
        "id": r.get("id"),
        "name": r.get("name"),
        "source": r.get("source", ""),
        "state": r.get("state"),
        "public": bool(r.get("public")),
        "share_token": r.get("share_token", ""),
        "rooms": sc_meta.get("rooms", 0),
        "area_sqft": sc_meta.get("area_sqft", 0),
        "created_at": r.get("created_at"),
        "updated_at": r.get("updated_at"),
    }


def list_for(tenant_id: str, is_admin: bool = False) -> list[dict]:
    PDIR.mkdir(parents=True, exist_ok=True)
    out: list[dict] = []
    for f in PDIR.glob("*.json"):
        try:
            r = json.loads(f.read_text("utf-8"))
        except Exception:
            continue
        if is_admin or r.get("tenant_id") == tenant_id:
            out.append(_summary(r))
    return sorted(out, key=lambda x: x.get("updated_at", 0), reverse=True)
