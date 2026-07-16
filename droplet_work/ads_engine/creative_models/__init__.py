"""ads_engine.creative_models — the creative model-adapter pack (image gen + compose).

ONE adapter per model over a shared base (submit -> poll -> store), keys via the injected
`get_secret_json` seam, OFFLINE/mocked httpx (no keys). Imported ONLY by `creative.py`.

HARD RULES (binding — design/creative.md §1):
  * Import is CHEAP + CRASH-PROOF: `__init__` imports NOTHING heavy at module load. The
    adapter modules are pulled in LAZILY by `get_model_class()` inside a try/except, so a
    broken/half-built adapter can never crash the package import (the mount guard stays intact).
  * MODEL_REGISTRY maps a creative KIND -> an ordered [default, fallback...] of pinned model
    ids. The pins are single-sourced from `config.MODEL_PINS`; `_EOL` blocks the EOL list.
  * resolve_model() does the per-tenant OVERRIDE: a tenant's chosen slug is tried first, then
    the kind's default chain — but an EOL model is REFUSED at resolve time (never instantiated).

The registry returns a *class*; `creative.py` instantiates it with the tenant-bound
`get_secret_json` closure + provider_def_id + (in tests) an injected mock http client.
"""

from __future__ import annotations

from typing import Optional, Type

# Re-export the request/result value objects so creative.py can build them via the package
# namespace (creative_models.GenRequest). These are cheap dataclasses — base imports only the
# connector substrate (httpx stays lazy), so this stays crash-proof at package import.
from .base import GenRequest, PollResult, SubmitResult  # noqa: E402

# Kind -> ordered list of pinned model ids (default first, then fallback).
# These mirror design/creative.md §3 and stay off every EOL id.
MODEL_REGISTRY = {
    "headline_image": ["ideogram-v3", "gemini-3-pro-image-preview"],
    "bulk_image": ["gemini-2.5-flash-image", "gpt-image-1-mini"],
    "vector_badge": ["recraft-v3"],
    "property_shot": ["flux-2-max", "flux-2-pro"],
    "multi_size": ["bannerbear", "placid"],
}

# model id -> (module name, builder fn name) for LAZY import. Only loaded on demand.
_MODEL_MODULES = {
    "ideogram-v3": ("ideogram", "build"),
    "gemini-2.5-flash-image": ("nano_banana", "build"),
    "gemini-3-pro-image-preview": ("nano_banana", "build"),
    "recraft-v3": ("recraft", "build"),
    "flux-2-max": ("flux", "build"),
    "flux-2-pro": ("flux", "build"),
    "bannerbear": ("bannerbear", "build"),
}


def _eol_blocklist() -> set:
    """The EOL/blocked model ids (config single-source), degrade-safe."""
    try:
        from .. import config
        bl = getattr(config, "MODEL_PINS", {}).get("_eol_blocklist")
        if isinstance(bl, list):
            return {str(x) for x in bl}
    except Exception:  # noqa: BLE001
        pass
    return {"gpt-image-1", "veo-3.0", "veo-3.0-fast", "veo-3.0-generate-001"}


def is_eol(model_id: str) -> bool:
    """True iff `model_id` is a known EOL model that MUST NOT be used (design §11.6)."""
    return str(model_id) in _eol_blocklist()


def get_model_class(model_id: str) -> Optional[Type]:
    """LAZY-import the adapter builder for a model id. None if unknown / import fails / EOL.

    Crash-proof: a missing httpx / a broken adapter module returns None (the caller degrades to
    the next fallback / not_configured), never raises into the package import or the job machine.
    """
    if is_eol(model_id):
        return None
    spec = _MODEL_MODULES.get(str(model_id))
    if spec is None:
        return None
    mod_name, fn_name = spec
    try:
        import importlib
        mod = importlib.import_module(f".{mod_name}", __name__)
        return getattr(mod, fn_name, None)
    except Exception:  # noqa: BLE001 — broken adapter import must never crash the package
        return None


def resolve_chain(kind: str, *, override: str = "") -> list:
    """The ordered model-id chain to try for `kind`, honoring a per-tenant `override` slug.

    The override (a model id) is tried FIRST, then the kind's default chain. EOL ids are
    filtered OUT at resolve time so an EOL model is never even instantiated (design §11.6).
    """
    chain = []
    if override:
        chain.append(str(override))
    chain.extend(MODEL_REGISTRY.get(kind, []))
    # dedupe preserving order + drop EOL.
    seen = set()
    out = []
    for m in chain:
        if m in seen or is_eol(m):
            continue
        seen.add(m)
        out.append(m)
    return out


def resolve_model(kind: str, *, override: str = "", **build_kwargs):
    """Build the FIRST usable adapter for `kind` (override first, then defaults).

    Returns (model_id, adapter) or (None, None) if nothing in the chain is buildable. EOL models
    are skipped (refused). `build_kwargs` (get_secret_json, provider_def_id, http, sleep_fn) are
    forwarded to the adapter builder. The `model_id` baked into multi-id modules (nano/flux) is
    passed through so the right pinned id is set.
    """
    for mid in resolve_chain(kind, override=override):
        builder = get_model_class(mid)
        if builder is None:
            continue
        try:
            kw = dict(build_kwargs)
            # nano_banana + flux take a model_id arg to pick the exact pinned id.
            if mid in ("gemini-3-pro-image-preview", "gemini-2.5-flash-image",
                       "flux-2-max", "flux-2-pro"):
                kw["model_id"] = mid
            return mid, builder(**kw)
        except Exception:  # noqa: BLE001 — try the next fallback, never raise
            continue
    return None, None


__all__ = [
    "MODEL_REGISTRY", "is_eol", "get_model_class",
    "resolve_chain", "resolve_model",
    "GenRequest", "PollResult", "SubmitResult",
]
