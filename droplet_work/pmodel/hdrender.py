"""pmodel.hdrender — enqueue HD render jobs for a separate GPU Blender worker.

PURE PYTHON, no `bpy` import → safe on the API box (which has no Blender). Converts
a SceneSpec into a flat, rotation-aware box list the worker rasterizes with Cycles,
writes the job JSON to a shared queue dir, and reads back the worker's `.done` marker.

DORMANT unless FEATURE_PMODEL_HDRENDER + HDRENDER_QUEUE_DIR are set. Coordinate note:
the viewer/SceneSpec is **Y-up** (three.js); Blender is **Z-up**, so a three point
[x, y, z] maps to Blender [x, z, y] and a rotation about three-Y maps to Blender-Z.
"""
from __future__ import annotations

import json
import math
import os
import time
import uuid
from pathlib import Path


def _queue_dir() -> str:
    return (os.getenv("HDRENDER_QUEUE_DIR") or "").strip()


def enabled() -> bool:
    flag = (os.getenv("FEATURE_PMODEL_HDRENDER", "0") or "0").strip().lower() in ("1", "true", "yes", "on")
    return flag and bool(_queue_dir())


def _hex_to_rgb(h: str) -> list[float]:
    h = (h or "#cccccc").lstrip("#")
    if len(h) != 6:
        return [0.8, 0.8, 0.8]
    try:
        return [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    except Exception:
        return [0.8, 0.8, 0.8]


# approximate furniture footprints [w, h, d] (metres), three-space, for box stand-ins
_FURN = {
    "bed": [1.7, 0.6, 2.05], "nightstand": [0.5, 0.45, 0.42], "wardrobe": [1.8, 2.0, 0.6],
    "sofa": [2.1, 0.8, 0.95], "coffee_table": [1.0, 0.45, 0.55], "tv_unit": [1.7, 1.2, 0.4],
    "dining_table": [1.7, 0.75, 1.0], "fridge": [0.72, 1.8, 0.7], "counter": [2.2, 0.9, 0.6],
    "toilet": [0.5, 0.7, 0.6], "sink": [0.55, 0.85, 0.42], "tub": [1.7, 0.55, 0.75],
    "shower": [0.95, 1.9, 0.95], "desk": [1.4, 0.75, 0.7], "chair": [0.45, 0.85, 0.45],
    "shelf": [0.9, 2.0, 0.32], "console": [1.0, 0.8, 0.35], "plant": [0.45, 0.95, 0.45],
    "rug": [2.3, 0.02, 1.7], "lamp": [0.4, 1.5, 0.4],
}


def scene_to_job(scene: dict) -> dict:
    """SceneSpec (three, Y-up) -> {id, boxes:[{pos,size,rot,color}], camera, result_key}.
    pos/size/camera are already in Blender (Z-up) space."""
    boxes: list[dict] = []
    pal = scene.get("palette", {})
    wall_col = _hex_to_rgb(pal.get("wall", "#e9ebf2"))
    floor_pal = pal.get("floor", {}) if isinstance(pal.get("floor"), dict) else {}

    # walls (panels carry three world pos [x,y,z], size [len,height,thick], rotationY)
    for w in scene.get("walls", []):
        for p in w.get("panels", []):
            px, py, pz = p["position"]
            sx, sy, sz = p["size"]
            boxes.append({
                "pos": [px, pz, py],             # three[x,y,z] -> blender[x,z,y]
                "size": [sx, sz, sy],            # [along-wall, thickness, height]
                "rot": p.get("rotationY", 0.0),  # about blender-Z
                "color": wall_col,
            })

    # floors -> thin slabs from their bounding box (color by material)
    for fl in scene.get("floors", []):
        poly = fl.get("polygon", [])
        if len(poly) < 3:
            continue
        xs = [pt[0] for pt in poly]
        zs = [pt[1] for pt in poly]
        cx, cz = (min(xs) + max(xs)) / 2, (min(zs) + max(zs)) / 2
        w_, d_ = (max(xs) - min(xs)), (max(zs) - min(zs))
        col = _hex_to_rgb(floor_pal.get(fl.get("material", "wood"), "#caa472"))
        boxes.append({"pos": [cx, cz, 0.02], "size": [w_, d_, 0.04], "rot": 0.0, "color": col})

    # furniture -> bounding boxes
    for f in scene.get("furniture", []):
        size = _FURN.get(f.get("kind"), [0.6, 0.6, 0.6])
        x, _y, z = f["position"]
        boxes.append({
            "pos": [x, z, size[1] / 2],
            "size": [size[0], size[2], size[1]],
            "rot": f.get("rotationY", 0.0),
            "color": [0.62, 0.55, 0.47],
        })

    cam = scene.get("cameras", {}).get("dollhouse", {}).get("position", [9, 9, 9])
    camera = [cam[0], cam[2], cam[1]]  # three -> blender
    return {"boxes": boxes, "camera": camera}


def enqueue(scene: dict) -> dict | None:
    if not enabled():
        return None
    qd = Path(_queue_dir())
    try:
        qd.mkdir(parents=True, exist_ok=True)
    except Exception:
        return None
    job_id = uuid.uuid4().hex[:12]
    job = scene_to_job(scene)
    job["id"] = job_id
    job["result_key"] = f"{(os.getenv('HDRENDER_RESULT_PREFIX') or 'pmodel/renders').strip('/')}/{job_id}.png"
    job["created_at"] = time.time()
    try:
        tmp = qd / f"{job_id}.json.tmp"
        tmp.write_text(json.dumps(job), encoding="utf-8")
        os.replace(tmp, qd / f"{job_id}.json")
    except Exception:
        return None
    return {"job": job_id, "state": "queued", "result_key": job["result_key"]}


def status(job_id: str) -> dict:
    job_id = "".join(c for c in (job_id or "") if c.isalnum())[:32]
    if not enabled() or not job_id:
        return {"state": "unknown"}
    qd = Path(_queue_dir())
    done = qd / f"{job_id}.done"
    if done.exists():
        try:
            d = json.loads(done.read_text("utf-8"))
        except Exception:
            d = {}
        if d.get("ok"):
            return {"state": "done", "result_key": f"{(os.getenv('HDRENDER_RESULT_PREFIX') or 'pmodel/renders').strip('/')}/{job_id}.png"}
        return {"state": "failed", "error": d.get("error", "render_failed")}
    if (qd / f"{job_id}.json").exists():
        return {"state": "running"}
    return {"state": "unknown"}
