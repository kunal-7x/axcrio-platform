"""pmodel.assets3d — optional generative furniture: turn a furniture `kind` into a
realistic GLB mesh via a hosted text/image-to-3D API, cache it to Spaces (once per
kind, tenant-shared), and attach presigned GLB urls onto a SceneSpec so the viewer
can swap procedural primitives for real meshes.

DORMANT by default: without FEATURE_PMODEL_ASSETS3D + ASSETS3D_API_KEY nothing
generates and `resolve_urls` returns the scene untouched → the studio keeps its
procedural furniture. The provider adapter is intentionally swappable; the exact
endpoint paths/ids are VERIFY-BEFORE-SHIP for your chosen provider (Meshy/Tripo/…).
"""
from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path

import httpx

VAR = Path(os.getenv("FAMIT_VAR", "/opt/famit-agent/var"))
_REG = VAR / "pmodel" / "assets3d_registry.json"

# Human prompts per builder `kind` (matches Furniture.tsx switch cases). Unlisted
# kinds stay procedural.
_PROMPTS = {
    "sofa": "a modern 3-seat fabric sofa, neutral grey, realistic, game-ready, low-poly, centered",
    "bed": "a queen platform bed with headboard and two pillows, realistic, game-ready, centered",
    "wardrobe": "a tall two-door wooden wardrobe closet, realistic, game-ready, centered",
    "dining_table": "a wooden dining table with four chairs, realistic, game-ready, centered",
    "coffee_table": "a low wooden coffee table, realistic, game-ready, centered",
    "tv_unit": "a low media console cabinet with a flat-screen TV, realistic, game-ready, centered",
    "fridge": "a stainless steel double-door refrigerator, realistic, game-ready, centered",
    "nightstand": "a small wooden bedside nightstand with a drawer, realistic, game-ready",
    "desk": "a wooden office desk, realistic, game-ready, centered",
    "chair": "a single dining chair, wood and fabric, realistic, game-ready",
    "toilet": "a white ceramic toilet, realistic, game-ready",
    "sink": "a white pedestal bathroom sink with a faucet, realistic, game-ready",
    "plant": "a potted indoor plant in a ceramic pot, realistic, game-ready",
}


def enabled() -> bool:
    flag = (os.getenv("FEATURE_PMODEL_ASSETS3D", "0") or "0").strip().lower() in ("1", "true", "yes", "on")
    return flag and bool((os.getenv("ASSETS3D_API_KEY") or "").strip())


def _cfg() -> dict:
    return {
        "base": (os.getenv("ASSETS3D_BASE") or "https://api.meshy.ai").rstrip("/"),
        "key": (os.getenv("ASSETS3D_API_KEY") or "").strip(),
        "model": (os.getenv("ASSETS3D_MODEL") or "").strip(),
        "timeout": int(os.getenv("ASSETS3D_POLL_TIMEOUT_S", "180") or "180"),
        "prefix": (os.getenv("ASSETS3D_CACHE_PREFIX") or "pmodel/assets3d").strip("/"),
    }


def cache_key(kind: str) -> str:
    safe = "".join(c for c in (kind or "") if c.isalnum() or c == "_")[:32]
    return f"{_cfg()['prefix']}/{safe}.glb"


# ---- registry (tenant-shared: one GLB per kind, reused across projects) ----
def registry() -> dict:
    try:
        return json.loads(_REG.read_text("utf-8")) if _REG.exists() else {}
    except Exception:
        return {}


def _register(kind: str, key: str) -> None:
    _REG.parent.mkdir(parents=True, exist_ok=True)
    reg = registry()
    reg[kind] = key
    tmp = _REG.with_suffix(".tmp")
    tmp.write_text(json.dumps(reg, indent=2), encoding="utf-8")
    os.replace(tmp, _REG)


def kinds_in_scene(scene: dict | None) -> list[str]:
    out: list[str] = []
    for f in (scene or {}).get("furniture", []):
        k = f.get("kind")
        if k and k in _PROMPTS and k not in out:
            out.append(k)
    return out


def resolve_urls(scene: dict | None, presign, bucket: str) -> dict | None:
    """Attach a presigned `glb` url to each furniture item whose kind has a cached
    mesh. No-op (returns scene unchanged) when dormant or nothing is cached."""
    if not scene or not enabled() or not presign or not bucket:
        return scene
    reg = registry()
    if not reg:
        return scene
    cache: dict[str, str] = {}
    for f in scene.get("furniture", []):
        k = f.get("kind")
        key = reg.get(k)
        if not key:
            continue
        if k not in cache:
            try:
                cache[k] = presign(bucket, key, 86400) or ""
            except Exception:
                cache[k] = ""
        if cache[k]:
            f["glb"] = cache[k]
    return scene


# ---- generation (hosted text-to-3D; VERIFY endpoints for your provider) ----
async def _create_job(c: httpx.AsyncClient, base: str, key: str, model: str, prompt: str) -> str:
    body = {"mode": "preview", "prompt": prompt, "art_style": "realistic"}
    if model:
        body["model"] = model
    r = await c.post(f"{base}/v2/text-to-3d", headers={"Authorization": "Bearer " + key}, json=body)
    r.raise_for_status()
    j = r.json()
    return str(j.get("result") or j.get("id") or j.get("task_id") or "")


async def _poll(c: httpx.AsyncClient, base: str, key: str, job: str, deadline: float) -> str:
    while time.time() < deadline:
        r = await c.get(f"{base}/v2/text-to-3d/{job}", headers={"Authorization": "Bearer " + key})
        r.raise_for_status()
        j = r.json()
        st = (j.get("status") or "").upper()
        if st in ("SUCCEEDED", "COMPLETED", "SUCCESS"):
            urls = j.get("model_urls") or {}
            return urls.get("glb") or j.get("model_url") or ""
        if st in ("FAILED", "ERROR", "EXPIRED"):
            return ""
        await asyncio.sleep(3)
    return ""


async def generate_glb_bytes(kind: str) -> bytes | None:
    """GLB bytes for `kind`, or None on any failure (caller falls back to primitive)."""
    if not enabled():
        return None
    prompt = _PROMPTS.get(kind)
    if not prompt:
        return None
    cf = _cfg()
    deadline = time.time() + cf["timeout"]
    try:
        async with httpx.AsyncClient(timeout=60.0) as c:
            job = await _create_job(c, cf["base"], cf["key"], cf["model"], prompt)
            if not job:
                return None
            glb_url = await _poll(c, cf["base"], cf["key"], job, deadline)
            if not glb_url:
                return None
            blob = await c.get(glb_url, timeout=180.0)
            blob.raise_for_status()
            data = blob.content
            return data if data[:4] == b"glTF" else None  # GLB magic guard
    except Exception:
        return None


async def generate_for_scene(scene: dict | None, put) -> dict:
    """Generate + cache GLBs for any uncached furniture kinds in `scene`. `put(key,
    bytes, ctype)` is the injected best-effort Spaces uploader. Returns a summary."""
    if not enabled():
        return {"enabled": False, "generated": 0}
    reg = registry()
    todo = [k for k in kinds_in_scene(scene) if k not in reg]
    made = 0
    for k in todo:
        data = await generate_glb_bytes(k)
        if not data:
            continue
        key = put(cache_key(k), data, "model/gltf-binary")
        if key:
            _register(k, key)
            made += 1
    return {"enabled": True, "requested": len(todo), "generated": made, "kinds": registry()}
