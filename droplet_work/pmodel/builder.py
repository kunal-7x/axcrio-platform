"""pmodel.builder — PropertyLayout (semantic) -> SceneSpec (render-ready).

Pure, deterministic, no network. The geometry "intelligence" lives here so both
the studio viewer and the public share page render identical models from one
contract. The R3F viewer is a *dumb interpreter* of the SceneSpec below.

SceneSpec (world metres, Y-up, model centred on the origin):
{
  "units": "m",
  "meta":   { title, area_sqm, area_sqft, rooms, bedrooms, baths, eye_height },
  "bounds": { min:[x,z], max:[x,z], width, depth, center:[x,z] },
  "palette": { wall, trim, glass, floor:{<material>:hex}, ... },
  "walls":   [ { panels:[ {position:[x,y,z], size:[w,h,d], rotationY, kind} ] } ],
  "floors":  [ { name, type, material, area_sqm, polygon:[[x,z]], center:[x,z], y } ],
  "openings":[ { kind:"door"|"window"|"arch", position:[x,y,z], rotationY,
                 width, height, sill, thickness } ],
  "furniture":[ { kind, position:[x,y,z], rotationY, room } ],
  "lights":  [ { kind:"sun"|"ceiling", position:[x,y,z], intensity, color } ],
  "cameras": { dollhouse:{position,target}, waypoints:[ {name,position,target} ] }
}
"""
from __future__ import annotations

import math
from typing import Any

from . import schema as S

PALETTE = {
    "wall": "#e9ebf2",
    "trim": "#d4dae6",
    "glass": "#9ec6e6",
    "door": "#9c6b3f",
    "floor": {
        "wood":  "#caa472",
        "tile":  "#dfe3ea",
        "stone": "#c8ccd4",
        "deck":  "#b08c63",
        "carpet": "#b9b3ab",
    },
}

# floor material by canonical room type
_FLOOR_MAT = {
    "living": "wood", "bedroom": "wood", "dining": "wood", "office": "wood",
    "room": "wood", "entry": "stone", "corridor": "wood",
    "kitchen": "tile", "bath": "tile", "utility": "tile",
    "balcony": "deck",
}


def _floor_material(room_type: str) -> str:
    return _FLOOR_MAT.get(room_type, "wood")


def build_scene(layout_in: dict | None) -> dict:
    """Build a complete SceneSpec from a (raw or normalized) PropertyLayout."""
    layout = S.normalize_layout(layout_in)
    scale = S.infer_scale(layout)

    min_x, min_y, max_x, max_y = S.layout_bounds(layout)
    # scaled bounds -> centre the model on the origin
    sw = (max_x - min_x) * scale
    sd = (max_y - min_y) * scale
    cx = (min_x + max_x) * 0.5
    cy = (min_y + max_y) * 0.5

    def W(p: list[float]) -> tuple[float, float]:
        """plan point -> world (x, z), centred."""
        return ((p[0] - cx) * scale, (p[1] - cy) * scale)

    # ---- floors -------------------------------------------------------------
    floors: list[dict] = []
    total_area = 0.0
    for r in layout["rooms"]:
        wpoly = [list(W(p)) for p in r["polygon"]]
        area = S.polygon_area(wpoly)
        total_area += area
        cxz = S.polygon_centroid(wpoly)
        floors.append({
            "name": r["name"],
            "type": r["type"],
            "material": _floor_material(r["type"]),
            "area_sqm": round(area, 2),
            "polygon": [[round(x, 3), round(z, 3)] for x, z in wpoly],
            "center": [round(cxz[0], 3), round(cxz[1], 3)],
            "y": 0.0,
        })

    # ---- walls (with openings carved into panels) ---------------------------
    # group openings by wall index
    by_wall: dict[int, list[dict]] = {}
    for o in layout["openings"]:
        by_wall.setdefault(o["on_wall"], []).append(o)

    walls_out: list[dict] = []
    openings_out: list[dict] = []
    for i, w in enumerate(layout["walls"]):
        ax, az = W(w["a"])
        bx, bz = W(w["b"])
        L = math.hypot(bx - ax, bz - az)
        if L < 1e-4:
            continue
        theta = math.atan2(bz - az, bx - ax)
        rotY = -theta
        dirx, dirz = math.cos(theta), math.sin(theta)
        H = w["height_m"]
        T = w["thickness_m"]

        def panel(p0: float, p1: float, y0: float, y1: float, kind: str) -> dict:
            mid = (p0 + p1) * 0.5
            return {
                "position": [round(ax + dirx * mid, 3), round((y0 + y1) * 0.5, 3),
                             round(az + dirz * mid, 3)],
                "size": [round(max(p1 - p0, 0.001), 3), round(max(y1 - y0, 0.001), 3), round(T, 3)],
                "rotationY": round(rotY, 5),
                "kind": kind,
            }

        # opening spans along this wall (absolute metres along its length)
        spans: list[dict] = []
        for o in sorted(by_wall.get(i, []), key=lambda o: o["t"]):
            d = o["t"] * L
            half = min(o["width_m"], L * 0.95) * 0.5
            s0 = max(0.0, d - half)
            s1 = min(L, d + half)
            if s1 - s0 < 0.05:
                continue
            spans.append({**o, "s0": s0, "s1": s1, "d": d})

        panels: list[dict] = []
        cursor = 0.0
        for sp in spans:
            if sp["s0"] > cursor + 1e-3:
                panels.append(panel(cursor, sp["s0"], 0.0, H, "solid"))
            sill = sp.get("sill_m", 0.0)
            head = min(sp.get("head_m", S.DOOR_H), H)
            if sp["type"] == "window" and sill > 0.05:
                panels.append(panel(sp["s0"], sp["s1"], 0.0, sill, "sill"))
            if head < H - 0.02:
                panels.append(panel(sp["s0"], sp["s1"], head, H, "header"))
            cursor = max(cursor, sp["s1"])
            # opening render entry (door slab / window glass)
            openings_out.append({
                "kind": sp["type"],
                "position": [round(ax + dirx * sp["d"], 3),
                             round((sill + head) * 0.5, 3),
                             round(az + dirz * sp["d"], 3)],
                "rotationY": round(rotY, 5),
                "width": round(sp["s1"] - sp["s0"], 3),
                "height": round(head - sill, 3),
                "sill": round(sill, 3),
                "thickness": round(T, 3),
            })
        if cursor < L - 1e-3:
            panels.append(panel(cursor, L, 0.0, H, "solid"))

        walls_out.append({"panels": panels, "height": round(H, 3)})

    # ---- furniture ----------------------------------------------------------
    furniture: list[dict] = []
    lights: list[dict] = []
    for fl in floors:
        furniture += _furnish(fl)
        # warm ceiling light per room
        lights.append({
            "kind": "ceiling",
            "position": [fl["center"][0], 2.4, fl["center"][1]],
            "intensity": 0.5,
            "color": "#ffe9c8",
        })

    # one key "sun"
    span = max(sw, sd) or 6.0
    lights.append({
        "kind": "sun",
        "position": [span * 0.6, span * 1.1, span * 0.4],
        "intensity": 1.15,
        "color": "#fff4e0",
    })

    # ---- cameras ------------------------------------------------------------
    diag = math.hypot(sw, sd) or 8.0
    dollhouse = {
        "position": [sw * 0.55 + 2, diag * 0.75 + 2, sd * 0.65 + 4],
        "target": [0.0, 0.6, 0.0],
    }
    waypoints: list[dict] = []
    ordered = sorted(floors, key=lambda f: (-f["area_sqm"]))  # start in the largest room
    eye = 1.6
    for idx, fl in enumerate(ordered):
        nxt = ordered[(idx + 1) % len(ordered)] if len(ordered) > 1 else fl
        waypoints.append({
            "name": fl["name"],
            "position": [fl["center"][0], eye, fl["center"][1]],
            "target": [nxt["center"][0], eye, nxt["center"][1]],
        })

    meta_in = layout.get("meta", {})
    area_sqm = round(total_area, 1)
    return {
        "units": "m",
        "meta": {
            "title": meta_in.get("title") or "Property Model",
            "area_sqm": area_sqm,
            "area_sqft": round(area_sqm * 10.7639, 0),
            "rooms": len(floors),
            "bedrooms": int(meta_in.get("bedrooms") or sum(1 for f in floors if f["type"] == "bedroom")),
            "baths": int(meta_in.get("baths") or sum(1 for f in floors if f["type"] == "bath")),
            "eye_height": eye,
        },
        "bounds": {
            "min": [round(-sw / 2, 3), round(-sd / 2, 3)],
            "max": [round(sw / 2, 3), round(sd / 2, 3)],
            "width": round(sw, 3),
            "depth": round(sd, 3),
            "center": [0.0, 0.0],
        },
        "palette": PALETTE,
        "walls": walls_out,
        "floors": floors,
        "openings": openings_out,
        "furniture": furniture,
        "lights": lights,
        "cameras": {"dollhouse": dollhouse, "waypoints": waypoints},
    }


# ----------------------------------------------------------------------------- furnishing
def _bbox(poly: list[list[float]]) -> tuple[float, float, float, float]:
    xs = [p[0] for p in poly]
    zs = [p[1] for p in poly]
    return (min(xs), min(zs), max(xs), max(zs))


def _furnish(fl: dict) -> list[dict]:
    """Lay out a few signature pieces for a room from its world bbox + type.

    Rooms in real plans are mostly axis-aligned rectangles, so we place pieces
    axis-aligned against the room's bounding box with sensible insets. The viewer
    knows how to draw each `kind` from primitives."""
    rt = fl["type"]
    minx, minz, maxx, maxz = _bbox(fl["polygon"])
    cx, cz = fl["center"]
    w = maxx - minx
    d = maxz - minz
    if w < 0.8 or d < 0.8:
        return []
    horizontal = w >= d            # room is wider than deep
    items: list[dict] = []

    def add(kind: str, x: float, z: float, rot: float = 0.0) -> None:
        items.append({"kind": kind, "position": [round(x, 3), 0.0, round(z, 3)],
                      "rotationY": round(rot, 4), "room": fl["name"]})

    if rt == "bedroom":
        # bed headboard against the top (minz) wall, centred
        add("bed", cx, minz + 1.15, 0.0)
        add("nightstand", cx - 1.25, minz + 0.4, 0.0)
        add("nightstand", cx + 1.25, minz + 0.4, 0.0)
        add("wardrobe", maxx - 0.35, cz, math.pi / 2)
        add("rug", cx, cz + 0.4, 0.0)
    elif rt == "living":
        add("sofa", cx, maxz - 0.6, math.pi)            # back to bottom wall
        add("coffee_table", cx, cz + 0.1, 0.0)
        add("tv_unit", cx, minz + 0.35, 0.0)
        add("rug", cx, cz + 0.1, 0.0)
        add("plant", maxx - 0.5, maxz - 0.5, 0.0)
    elif rt == "kitchen":
        if horizontal:
            add("counter", cx, minz + 0.35, 0.0)
            add("fridge", maxx - 0.4, minz + 0.4, 0.0)
        else:
            add("counter", minx + 0.35, cz, math.pi / 2)
            add("fridge", minx + 0.4, maxz - 0.4, 0.0)
        if (w * d) > 8:
            add("dining_table", cx, maxz - 0.9, 0.0)
    elif rt == "dining":
        add("dining_table", cx, cz, 0.0 if horizontal else math.pi / 2)
        add("rug", cx, cz, 0.0)
    elif rt == "bath":
        add("toilet", minx + 0.45, minz + 0.5, math.pi / 2)
        add("sink", minx + 0.45, maxz - 0.5, math.pi / 2)
        if max(w, d) > 2.2:
            add("tub", maxx - 0.55, cz, math.pi / 2)
        else:
            add("shower", maxx - 0.5, maxz - 0.5, 0.0)
    elif rt == "office":
        add("desk", cx, minz + 0.5, 0.0)
        add("chair", cx, minz + 1.1, math.pi)
        add("shelf", maxx - 0.3, cz, math.pi / 2)
    elif rt == "balcony":
        add("plant", minx + 0.5, cz, 0.0)
        add("chair", cx, cz, 0.0)
        add("chair", cx + 0.8, cz, 0.0)
    elif rt == "entry":
        add("console", cx, minz + 0.3, 0.0)
        add("plant", maxx - 0.4, minz + 0.4, 0.0)
    # corridor / utility / generic room -> leave open
    return [it for it in items if it]
