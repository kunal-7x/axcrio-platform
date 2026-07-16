"""verticals.overlay — optional, no-deploy JSON overrides for the registries.

Mirrors the estate's live-tunable config idiom (VAR/tier_overrides.json deep-merged
over static defaults): an operator/panel can drop a JSON file to ADD or tweak
verticals, sub-options, personas or languages WITHOUT a code deploy.

Resolution order for the file path (first that exists wins):
  1. env ``VERTICALS_OVERRIDES_PATH``  (explicit file path)
  2. ``$HAPTICA_VAR/verticals_overrides.json``
  3. ``$FAMIT_VAR/verticals_overrides.json``

Shape (all keys optional; deep-merged over the static registries):
  {
    "fields":    { "<vertical_key>": { ...FIELD fields..., "sub_options": {...} } },
    "personas":  { "<persona_key>":  { ...PERSONA fields... } },
    "languages": { "<lang_code>":    { ...LANGUAGE fields... } }
  }

Best-effort and defensive: a missing/invalid file yields NO overrides (the static
registries are used verbatim). Never raises. Cached by (path, mtime) so a live edit
is picked up on the next call without a restart, at ~zero cost otherwise.
"""

from __future__ import annotations

import json
import os

_cache: dict = {"path": None, "mtime": None, "data": {}}


def _path() -> str:
    p = (os.getenv("VERTICALS_OVERRIDES_PATH") or "").strip()
    if p:
        return p
    for var in ("HAPTICA_VAR", "FAMIT_VAR"):
        base = (os.getenv(var) or "").strip()
        if base:
            return os.path.join(base, "verticals_overrides.json")
    return ""


def raw() -> dict:
    """Parsed overlay dict (or {}). (path, mtime)-cached; never raises."""
    path = _path()
    if not path or not os.path.isfile(path):
        return {}
    try:
        mtime = os.path.getmtime(path)
    except Exception:  # noqa: BLE001
        return {}
    if _cache["path"] == path and _cache["mtime"] == mtime:
        return _cache["data"]
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict):
            data = {}
    except Exception:  # noqa: BLE001 — bad JSON must never break a call
        data = {}
    _cache.update({"path": path, "mtime": mtime, "data": data})
    return data


def _deep_merge(base: dict, over: dict) -> dict:
    """Return a new dict = base deep-merged with over (dicts merge, others replace)."""
    out = dict(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _merged(section: str, static: dict) -> dict:
    over = raw().get(section)
    if not isinstance(over, dict) or not over:
        return static
    try:
        return _deep_merge(static, over)
    except Exception:  # noqa: BLE001
        return static


def fields(static: dict) -> dict:
    return _merged("fields", static)


def personas(static: dict) -> dict:
    return _merged("personas", static)


def languages(static: dict) -> dict:
    return _merged("languages", static)
