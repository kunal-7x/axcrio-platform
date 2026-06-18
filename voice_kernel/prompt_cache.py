"""voice_kernel.prompt_cache — Groq prompt-cache helper (stabilize the prefix).

GROUND TRUTH (W1-KERNEL-ARCH §0): the live model is Groq
`meta-llama/llama-4-scout-17b-16e-instruct`, and Groq prompt-caching does NOT
support llama-4-scout today. So "context packet" (a smaller prompt) and "prompt
caching" (a model move) are TWO INDEPENDENT levers. The kernel captures lever 1
NOW (small, layered, stable-prefix packet). Lever 2 is a separate, earner-gated
model decision (W5/G3), NOT assumed here.

What this helper does TODAY, safely:
  1. `is_cacheable_model(model)` — encode the known fact (scout = not cacheable)
     so callers branch correctly instead of guessing.
  2. `cache_breakpoint(prefix)` — return a stable fingerprint of the stable
     prefix. Even WITHOUT provider-side caching, a stable fingerprint lets the
     kernel ASSERT the prefix is byte-identical across turns (the whole point of
     the L0..L3 / suffix split) and lets a future cache key off it.
  3. `split_for_cache(prefix, suffix)` — return the (cacheable_prefix,
     volatile_suffix) pair in the shape a cache-aware sender expects, so when a
     cacheable model lands (lever 2) the wiring is already correct.

Pure-stdlib (hashlib), no provider SDK import — import-safe on the hot path.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

# Models known to support Groq automatic prompt caching. Conservative allowlist:
# we only claim caching for models we have VERIFIED, and explicitly exclude
# llama-4-scout (the live model) per arch §0.
_CACHEABLE_MODELS: frozenset[str] = frozenset()  # none verified yet; scout is NOT here.

_NON_CACHEABLE_MARKERS = ("llama-4-scout",)


def is_cacheable_model(model: str) -> bool:
    """True only for models VERIFIED to support Groq prompt caching. Returns
    False for llama-4-scout (the live model) and anything unverified — so a
    caller never assumes caching it doesn't have."""
    m = (model or "").lower()
    if any(mark in m for mark in _NON_CACHEABLE_MARKERS):
        return False
    return m in _CACHEABLE_MODELS


def cache_breakpoint(prefix: str) -> str:
    """Stable content fingerprint of the cacheable prefix. Same prefix → same
    key, every turn — this is the invariant the L0..L3/suffix split exists to
    preserve."""
    return hashlib.sha256((prefix or "").encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class CacheSplit:
    cacheable_prefix: str
    volatile_suffix: str
    prefix_key: str
    model_supports_cache: bool


def split_for_cache(prefix: str, suffix: str, model: str) -> CacheSplit:
    """Return the (cacheable_prefix, volatile_suffix) pair + the prefix key, in
    the shape a cache-aware message builder expects. Works today (model_supports
    _cache=False for scout) and is correct the moment a cacheable model lands."""
    return CacheSplit(
        cacheable_prefix=prefix or "",
        volatile_suffix=suffix or "",
        prefix_key=cache_breakpoint(prefix),
        model_supports_cache=is_cacheable_model(model),
    )
