"""pmodel.schema — the canonical *semantic* floor-plan contract + helpers.

Two data shapes flow through this module:

  PropertyLayout  (semantic, plan-space)   <- analyzer output (LLM or demo)
  ----------------------------------------------------------------------------
  {
    "units": "meters",
    "scale_m_per_px": float | null,   # plan px -> meters; null => infer
    "rooms":    [ Room, ... ],
    "walls":    [ Wall, ... ],
    "openings": [ Opening, ... ],
    "meta":     { "title"?, "bedrooms"?, "baths"?, "total_area_sqft"? }
  }

  Room    = { "name": str, "type"?: str, "polygon": [[x,y], ...], "floor"?: int }
  Wall    = { "a": [x,y], "b": [x,y], "height_m"?: float, "thickness_m"?: float }
  Opening = { "type": "door"|"window"|"arch", "on_wall": int, "t": 0..1,
              "width_m"?: float, "sill_m"?: float, "head_m"?: float }

`builder.build_scene()` turns a *normalized* PropertyLayout into a render-ready
SceneSpec (world-metres, Y-up) that the R3F viewer consumes.

This module is pure-python (no network, no heavy deps) so it imports safely even
when the vision model / Spaces are not configured.
"""
from __future__ import annotations

import re
from typing import Any

# ----------------------------------------------------------------------------- defaults
WALL_H = 2.7          # default storey height (m)
WALL_T = 0.12         # default interior wall thickness (m)
DOOR_W = 0.9          # default door clear width (m)
DOOR_H = 2.05         # default door height (m)
WIN_W = 1.2           # default window width (m)
WIN_SILL = 0.9        # default window sill height (m)
WIN_HEAD = 2.1        # default window head height (m)

# Keyword -> canonical room type. Order matters (first hit wins).
_ROOM_TYPES: list[tuple[str, tuple[str, ...]]] = [
    ("kitchen",  ("kitchen", "kit", "pantry", "cook")),
    ("bath",     ("bath", "toilet", "wc", "washroom", "powder", "ensuite", "en-suite", "shower")),
    ("bedroom",  ("bed", "master", "guest room", "kids", "child")),
    ("living",   ("living", "lounge", "hall", "drawing", "family", "great room", "sitting")),
    ("dining",   ("dining", "diner", "breakfast")),
    ("office",   ("office", "study", "work", "den", "library")),
    ("balcony",  ("balcony", "deck", "terrace", "patio", "veranda", "porch")),
    ("entry",    ("entry", "foyer", "lobby", "vestibule", "mudroom")),
    ("corridor", ("corridor", "passage", "hallway", "stair", "landing")),
    ("utility",  ("utility", "laundry", "store", "storage", "closet", "wardrobe", "garage")),
]


def infer_room_type(name: str, given: str | None = None) -> str:
    """Best-effort canonical room type from a label."""
    if given:
        g = given.strip().lower()
        for canon, _ in _ROOM_TYPES:
            if g == canon:
                return canon
    n = (name or "").strip().lower()
    for canon, keys in _ROOM_TYPES:
        if any(k in n for k in keys):
            return canon
    return "room"


# ----------------------------------------------------------------------------- geometry helpers
def polygon_area(poly: list[list[float]]) -> float:
    """Unsigned shoelace area."""
    n = len(poly)
    if n < 3:
        return 0.0
    s = 0.0
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        s += x1 * y2 - x2 * y1
    return abs(s) * 0.5


def polygon_centroid(poly: list[list[float]]) -> list[float]:
    """Area-weighted centroid (falls back to vertex mean for degenerate polys)."""
    n = len(poly)
    if n == 0:
        return [0.0, 0.0]
    if n < 3:
        cx = sum(p[0] for p in poly) / n
        cy = sum(p[1] for p in poly) / n
        return [cx, cy]
    a = 0.0
    cx = 0.0
    cy = 0.0
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        cross = x1 * y2 - x2 * y1
        a += cross
        cx += (x1 + x2) * cross
        cy += (y1 + y2) * cross
    if abs(a) < 1e-9:
        cx = sum(p[0] for p in poly) / n
        cy = sum(p[1] for p in poly) / n
        return [cx, cy]
    a *= 0.5
    return [cx / (6 * a), cy / (6 * a)]


def _num(v: Any, default: float) -> float:
    try:
        f = float(v)
        if f != f or f in (float("inf"), float("-inf")):  # NaN / inf guard
            return default
        return f
    except Exception:
        return default


def _pt(v: Any) -> list[float] | None:
    if isinstance(v, (list, tuple)) and len(v) >= 2:
        return [_num(v[0], 0.0), _num(v[1], 0.0)]
    return None


# ----------------------------------------------------------------------------- normalization
def normalize_layout(raw: dict | None) -> dict:
    """Coerce a (possibly messy) LLM/JSON payload into a clean PropertyLayout.

    Tolerant by design: drops malformed entries instead of raising, fills sane
    defaults, infers room types, and guarantees the shape `build_scene` expects.
    """
    raw = raw if isinstance(raw, dict) else {}

    scale = raw.get("scale_m_per_px")
    scale = _num(scale, 0.0) if scale not in (None, "", "null") else None
    if scale is not None and scale <= 0:
        scale = None

    rooms: list[dict] = []
    for r in (raw.get("rooms") or []):
        if not isinstance(r, dict):
            continue
        poly = [p for p in (_pt(v) for v in (r.get("polygon") or [])) if p is not None]
        if len(poly) < 3:
            continue
        name = str(r.get("name") or "Room").strip()[:48]
        rooms.append({
            "name": name,
            "type": infer_room_type(name, r.get("type")),
            "polygon": poly,
            "floor": int(_num(r.get("floor"), 0)),
        })

    walls: list[dict] = []
    for w in (raw.get("walls") or []):
        if not isinstance(w, dict):
            continue
        a = _pt(w.get("a"))
        b = _pt(w.get("b"))
        if a is None or b is None or a == b:
            continue
        walls.append({
            "a": a,
            "b": b,
            "height_m": _num(w.get("height_m"), WALL_H),
            "thickness_m": _num(w.get("thickness_m"), WALL_T),
        })

    # If the model gave rooms but no walls, derive perimeter walls from polygons.
    if rooms and not walls:
        walls = _walls_from_rooms(rooms)

    n_walls = len(walls)
    openings: list[dict] = []
    for o in (raw.get("openings") or []):
        if not isinstance(o, dict):
            continue
        try:
            wi = int(o.get("on_wall"))
        except Exception:
            continue
        if wi < 0 or wi >= n_walls:
            continue
        kind = str(o.get("type") or "door").strip().lower()
        if kind not in ("door", "window", "arch"):
            kind = "door"
        t = min(0.98, max(0.02, _num(o.get("t"), 0.5)))
        is_win = kind == "window"
        openings.append({
            "type": kind,
            "on_wall": wi,
            "t": t,
            "width_m": _num(o.get("width_m"), WIN_W if is_win else DOOR_W),
            "sill_m": _num(o.get("sill_m"), WIN_SILL if is_win else 0.0),
            "head_m": _num(o.get("head_m"), WIN_HEAD if is_win else DOOR_H),
        })

    meta = raw.get("meta") if isinstance(raw.get("meta"), dict) else {}
    return {
        "units": "meters",
        "scale_m_per_px": scale,
        "rooms": rooms,
        "walls": walls,
        "openings": openings,
        "meta": {
            "title": str(meta.get("title") or "").strip()[:80],
            "bedrooms": int(_num(meta.get("bedrooms"), sum(1 for r in rooms if r["type"] == "bedroom"))),
            "baths": int(_num(meta.get("baths"), sum(1 for r in rooms if r["type"] == "bath"))),
            "total_area_sqft": _num(meta.get("total_area_sqft"), 0.0),
        },
    }


def _walls_from_rooms(rooms: list[dict]) -> list[dict]:
    """Generate one wall per polygon edge (dedupes near-identical shared edges)."""
    seen: set[tuple] = set()
    walls: list[dict] = []
    for r in rooms:
        poly = r["polygon"]
        n = len(poly)
        for i in range(n):
            a = poly[i]
            b = poly[(i + 1) % n]
            key = tuple(sorted([(round(a[0], 2), round(a[1], 2)),
                                (round(b[0], 2), round(b[1], 2))]))
            if key in seen:
                continue
            seen.add(key)
            walls.append({"a": list(a), "b": list(b), "height_m": WALL_H, "thickness_m": WALL_T})
    return walls


def layout_bounds(layout: dict) -> tuple[float, float, float, float]:
    """(min_x, min_y, max_x, max_y) over rooms+walls in plan space."""
    xs: list[float] = []
    ys: list[float] = []
    for r in layout.get("rooms", []):
        for p in r["polygon"]:
            xs.append(p[0]); ys.append(p[1])
    for w in layout.get("walls", []):
        xs += [w["a"][0], w["b"][0]]
        ys += [w["a"][1], w["b"][1]]
    if not xs:
        return (0.0, 0.0, 1.0, 1.0)
    return (min(xs), min(ys), max(xs), max(ys))


def infer_scale(layout: dict) -> float:
    """Return metres-per-unit. Honours an explicit scale; otherwise guesses so the
    plan reads as a believable dwelling (longer side ~ 12 m, or sized from sqft)."""
    s = layout.get("scale_m_per_px")
    if isinstance(s, (int, float)) and s > 0:
        return float(s)
    min_x, min_y, max_x, max_y = layout_bounds(layout)
    span = max(max_x - min_x, max_y - min_y) or 1.0
    sqft = (layout.get("meta") or {}).get("total_area_sqft") or 0.0
    if sqft and sqft > 0:
        # area in current units -> scale^2 * area_units = area_m2 ; area_m2 = sqft*0.0929
        area_units = sum(polygon_area(r["polygon"]) for r in layout.get("rooms", [])) or (span * span)
        target_m2 = float(sqft) * 0.092903
        if area_units > 0:
            return (target_m2 / area_units) ** 0.5
    # Heuristic: if coordinates already look metric (span 4..40) keep ~1; else map to 12 m.
    if 4.0 <= span <= 40.0:
        return 1.0
    return 12.0 / span


# ----------------------------------------------------------------------------- demo layouts
def demo_layout(kind: str = "apartment_2bhk") -> dict:
    """Hand-authored, metre-space sample plans so the studio renders beautifully
    with zero configuration. Coordinates are already in metres (scale = 1)."""
    fn = _DEMOS.get(kind) or _DEMOS["apartment_2bhk"]
    return normalize_layout(fn())


def demo_catalog() -> list[dict]:
    return [
        {"kind": "apartment_2bhk", "title": "2 BHK Apartment", "desc": "Compact urban flat — living, kitchen, 2 beds, 2 baths."},
        {"kind": "studio", "title": "Studio Loft", "desc": "Open-plan studio with kitchenette + bath."},
        {"kind": "villa_3bhk", "title": "3 BHK Villa", "desc": "Spacious villa — great room, dining, 3 beds, balcony."},
    ]


def _demo_2bhk() -> dict:
    # A tidy ~10.5 x 8 m, 2-bed flat. Rooms as rectangles (metres).
    rooms = [
        {"name": "Living Room", "polygon": [[0, 0], [5.4, 0], [5.4, 4.2], [0, 4.2]]},
        {"name": "Kitchen", "polygon": [[5.4, 0], [9.2, 0], [9.2, 3.0], [5.4, 3.0]]},
        {"name": "Dining", "polygon": [[5.4, 3.0], [9.2, 3.0], [9.2, 4.2], [5.4, 4.2]]},
        {"name": "Master Bedroom", "polygon": [[0, 4.2], [4.4, 4.2], [4.4, 8.0], [0, 8.0]]},
        {"name": "Bedroom 2", "polygon": [[4.4, 4.7], [7.6, 4.7], [7.6, 8.0], [4.4, 8.0]]},
        {"name": "Bathroom", "polygon": [[7.6, 5.6], [9.2, 5.6], [9.2, 8.0], [7.6, 8.0]]},
        {"name": "Bath 2", "polygon": [[7.6, 4.2], [9.2, 4.2], [9.2, 5.6], [7.6, 5.6]]},
        {"name": "Hallway", "polygon": [[4.4, 4.2], [7.6, 4.2], [7.6, 4.7], [4.4, 4.7]]},
    ]
    walls = _walls_from_rooms([{"name": r["name"], "type": infer_room_type(r["name"]),
                                "polygon": r["polygon"], "floor": 0} for r in rooms])
    # Openings: front door into Living (wall 0 = living bottom edge), a few interior doors + windows.
    openings = [
        {"type": "door", "on_wall": 0, "t": 0.5, "width_m": 1.0},
        {"type": "window", "on_wall": 3, "t": 0.5, "width_m": 1.6},   # living left wall
        {"type": "window", "on_wall": 5, "t": 0.5, "width_m": 1.2},   # kitchen top
        {"type": "window", "on_wall": 18, "t": 0.5, "width_m": 1.4},  # master left
    ]
    return {"scale_m_per_px": 1.0, "rooms": rooms, "walls": walls, "openings": openings,
            "meta": {"title": "2 BHK Apartment", "bedrooms": 2, "baths": 2}}


def _demo_studio() -> dict:
    rooms = [
        {"name": "Studio", "polygon": [[0, 0], [6.0, 0], [6.0, 5.0], [0, 5.0]]},
        {"name": "Kitchenette", "polygon": [[6.0, 0], [8.4, 0], [8.4, 2.6], [6.0, 2.6]]},
        {"name": "Bathroom", "polygon": [[6.0, 2.6], [8.4, 2.6], [8.4, 5.0], [6.0, 5.0]]},
    ]
    walls = _walls_from_rooms([{"name": r["name"], "type": infer_room_type(r["name"]),
                                "polygon": r["polygon"], "floor": 0} for r in rooms])
    openings = [
        {"type": "door", "on_wall": 0, "t": 0.3, "width_m": 1.0},
        {"type": "window", "on_wall": 3, "t": 0.5, "width_m": 2.0},
        {"type": "window", "on_wall": 2, "t": 0.5, "width_m": 1.6},
    ]
    return {"scale_m_per_px": 1.0, "rooms": rooms, "walls": walls, "openings": openings,
            "meta": {"title": "Studio Loft", "bedrooms": 0, "baths": 1}}


def _demo_villa() -> dict:
    rooms = [
        {"name": "Great Room", "polygon": [[0, 0], [7.0, 0], [7.0, 5.5], [0, 5.5]]},
        {"name": "Dining", "polygon": [[7.0, 0], [11.0, 0], [11.0, 3.2], [7.0, 3.2]]},
        {"name": "Kitchen", "polygon": [[7.0, 3.2], [11.0, 3.2], [11.0, 5.5], [7.0, 5.5]]},
        {"name": "Master Bedroom", "polygon": [[0, 5.5], [5.0, 5.5], [5.0, 10.0], [0, 10.0]]},
        {"name": "Bedroom 2", "polygon": [[5.0, 6.2], [8.0, 6.2], [8.0, 10.0], [5.0, 10.0]]},
        {"name": "Bedroom 3", "polygon": [[8.0, 6.2], [11.0, 6.2], [11.0, 10.0], [8.0, 10.0]]},
        {"name": "Master Bath", "polygon": [[5.0, 5.5], [8.0, 5.5], [8.0, 6.2], [5.0, 6.2]]},
        {"name": "Balcony", "polygon": [[0, 10.0], [11.0, 10.0], [11.0, 11.5], [0, 11.5]]},
    ]
    walls = _walls_from_rooms([{"name": r["name"], "type": infer_room_type(r["name"]),
                                "polygon": r["polygon"], "floor": 0} for r in rooms])
    openings = [
        {"type": "door", "on_wall": 0, "t": 0.5, "width_m": 1.4},
        {"type": "window", "on_wall": 3, "t": 0.5, "width_m": 2.0},
        {"type": "window", "on_wall": 1, "t": 0.5, "width_m": 1.6},
    ]
    return {"scale_m_per_px": 1.0, "rooms": rooms, "walls": walls, "openings": openings,
            "meta": {"title": "3 BHK Villa", "bedrooms": 3, "baths": 2}}


_DEMOS = {
    "apartment_2bhk": _demo_2bhk,
    "studio": _demo_studio,
    "villa_3bhk": _demo_villa,
}
