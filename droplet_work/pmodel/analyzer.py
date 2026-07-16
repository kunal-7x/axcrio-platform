"""pmodel.analyzer — turn a 2D floor plan (image) or a text brief into a
PropertyLayout (semantic schema). Uses OpenRouter (true vision) via direct
async httpx, mirroring droplet_work/script_gen.py.

The Provider Registry's Tier-1 adapter is text-only today (it can't carry an
image content block), so vision deliberately bypasses it. See the integration
brief for the verification.

Errors are surfaced as RuntimeError with a stable code the router maps to HTTP:
  - "vision_not_configured" / "llm_not_configured"  -> 503 (dormant)
  - "analyze_failed"                                -> 502 (upstream)
"""
from __future__ import annotations

import base64
import json
import os
import re

import httpx

from . import vision_providers as _vp

_OPENROUTER = "https://openrouter.ai/api/v1/chat/completions"
# Vision-capable defaults; override per-deploy. Claude Sonnet supports image input.
_VISION_MODEL = os.getenv("PMODEL_VISION_MODEL", "anthropic/claude-sonnet-4.6")
_TEXT_MODEL = os.getenv("PMODEL_TEXT_MODEL", _VISION_MODEL)

_SCHEMA_HINT = (
    "Return ONLY a single JSON object, no prose, no markdown fences. Schema:\n"
    "{\n"
    '  "scale_m_per_px": <number|null>,  // metres per coordinate unit; estimate so '
    "a standard interior door is ~0.9m and the home is life-sized\n"
    '  "rooms": [ { "name": <string>, "type": <"living"|"bedroom"|"kitchen"|"bath"|'
    '"dining"|"office"|"balcony"|"entry"|"corridor"|"utility">, '
    '"polygon": [[x,y], ...] } ],   // CLOSED room footprint, clockwise, plan coords (x right, y down)\n'
    '  "walls": [ { "a": [x,y], "b": [x,y], "height_m": 2.7, "thickness_m": 0.12 } ],\n'
    '  "openings": [ { "type": <"door"|"window">, "on_wall": <wall index>, '
    '"t": <0..1 position along that wall>, "width_m": <number> } ],\n'
    '  "meta": { "title": <string>, "bedrooms": <int>, "baths": <int>, "total_area_sqft": <number|null> }\n'
    "}\n"
    "Rules: use ONE consistent coordinate system for every point; rooms must be "
    "non-self-intersecting polygons; walls should roughly trace room boundaries; "
    "index openings into the walls array by position; never invent rooms not shown."
)

_VISION_SYSTEM = (
    "You are a precise architectural floor-plan vectorizer. You convert a 2D plan "
    "image into structured geometry. " + _SCHEMA_HINT
)
_TEXT_SYSTEM = (
    "You are an architect. From a short brief you design a believable, well-proportioned "
    "single-storey floor plan as structured geometry (metres). Lay rooms out on a grid so "
    "walls align and rooms do not overlap. " + _SCHEMA_HINT
)


def _key() -> str:
    return (os.getenv("OPENROUTER_API_KEY") or "").strip()


def _headers(key: str) -> dict:
    h = {"Authorization": "Bearer " + key, "content-type": "application/json"}
    ref = os.getenv("OPENROUTER_REFERER", "").strip()
    if ref:
        h["HTTP-Referer"] = ref
        h["X-Title"] = "Haptica Property Studio"
    return h


def _extract_json(text: str) -> dict:
    """Robustly pull a JSON object out of an LLM reply (handles ```json fences,
    leading prose, trailing commentary)."""
    if not text:
        raise RuntimeError("analyze_failed")
    s = text.strip()
    # strip code fences
    if s.startswith("```"):
        s = re.sub(r"^```[a-zA-Z]*\s*", "", s)
        s = re.sub(r"\s*```$", "", s).strip()
    try:
        return json.loads(s)
    except Exception:
        pass
    # fall back to the outermost {...}
    start = s.find("{")
    end = s.rfind("}")
    if start >= 0 and end > start:
        try:
            return json.loads(s[start:end + 1])
        except Exception:
            pass
    raise RuntimeError("analyze_failed")


async def _chat(model: str, system: str, user_content, max_tokens: int = 4000) -> dict:
    # Provider switch: GLM / MiniMax are OpenAI-compatible alternates; default stays
    # OpenRouter (untouched). All paths produce choices[0].message.content JSON.
    alt = _vp.resolve()  # None unless PMODEL_VISION_PROVIDER=glm|minimax with a key
    if alt is not None:
        url, model, headers, extra, send_json = alt
    elif _vp.select() in ("glm", "minimax"):
        raise RuntimeError("vision_not_configured")  # alternate chosen but no key
    else:
        key = _key()
        if not key:
            raise RuntimeError("vision_not_configured")
        url, headers, extra, send_json = _OPENROUTER, _headers(key), {}, True

    body = {
        "model": model,
        "max_tokens": max_tokens,
        "temperature": 0.1,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user_content},
        ],
        **extra,
    }
    if send_json:
        body["response_format"] = {"type": "json_object"}

    async with httpx.AsyncClient(timeout=120.0) as c:
        r = await c.post(url, headers=headers, json=body)
    if r.status_code in (401, 403):
        raise RuntimeError("vision_not_configured")
    r.raise_for_status()
    try:
        content = r.json()["choices"][0]["message"]["content"]
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError("analyze_failed") from exc
    return _extract_json(content)


async def analyze_floorplan(image_bytes: bytes, mime: str = "image/jpeg") -> dict:
    """2D plan image -> raw PropertyLayout dict (un-normalized; builder normalizes)."""
    if not image_bytes:
        raise RuntimeError("analyze_failed")
    if not mime or not mime.startswith("image/"):
        mime = "image/jpeg"
    b64 = base64.b64encode(image_bytes).decode("ascii")
    data_url = f"data:{mime};base64,{b64}"
    user = [
        {"type": "image_url", "image_url": {"url": data_url}},
        {"type": "text", "text":
            "Vectorize this floor plan. Extract every room polygon, the walls that "
            "bound them, and door/window openings. " + _SCHEMA_HINT},
    ]
    return await _chat(_VISION_MODEL, _VISION_SYSTEM, user)


async def layout_from_text(prompt: str) -> dict:
    """Free-text brief (e.g. '3BHK 1200 sqft, south-facing living') -> raw PropertyLayout."""
    prompt = (prompt or "").strip()
    if not prompt:
        raise RuntimeError("analyze_failed")
    if not _key():
        raise RuntimeError("llm_not_configured")
    user = ("Design a floor plan for this brief and return it as the JSON schema. "
            "Brief:\n" + prompt[:2000])
    return await _chat(_TEXT_MODEL, _TEXT_SYSTEM, user)


def vision_configured() -> bool:
    return _vp.configured()
