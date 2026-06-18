"""voice_kernel.rag.config — RagConfig: the rag-package flag/knob reader.

Same flag pattern as voice_kernel.config (codebase-native, default-safe). NONE
of these flags enable retrieval into the LIVE prompt — that gate is the kernel's
KERNEL_ENABLED + the LATER precompute-at-dial wiring wave (see design/W4-RAG-SEAM.md).
These only configure the module's own behaviour (cache TTL, k, deadline, dense).

Tenant-scoped cache keys are built HERE (`cache_key`) so every store/runtime uses
the identical namespacing rule: a key ALWAYS carries the tenant_id first, so an
L0/Redis lookup can never cross tenants even on a key collision.
"""
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass

_TRUE = ("1", "true", "True", "yes", "on")


def _flag(name: str, default: str = "0") -> bool:
    return os.getenv(name, default) in _TRUE


@dataclass(frozen=True)
class RagConfig:
    """Immutable snapshot of the rag knobs. Build with `from_env()` in prod;
    construct directly in tests."""

    # retrieval shape
    top_k: int = 3  # snippets returned to the TurnLayer (packet clamps to <=3)
    fanout: int = 6  # candidates pulled from the corpus before fuse/clamp
    retrieve_timeout_s: float = 0.03  # HARD per-turn deadline (kernel also enforces)

    # cache
    cache_ttl_s: int = 300  # hot-cache entry TTL
    cache_namespace: str = "vkrag"

    # dense leg — OFF by default. dense=True is PRECOMPUTE-ONLY (never on the hot
    # retrieve path); the runtime forces dense=False inside retrieve() regardless.
    dense_enabled: bool = False

    # the `_global` shared telecaller corpus UNION (playbook). Mirrors KB_INCLUDE_GLOBAL.
    include_global: bool = True

    @classmethod
    def from_env(cls) -> "RagConfig":
        return cls(
            top_k=int(os.getenv("RAG_TOP_K", "3") or 3),
            fanout=int(os.getenv("RAG_FANOUT", "6") or 6),
            retrieve_timeout_s=float(os.getenv("RAG_RETRIEVE_TIMEOUT_S", "0.03") or 0.03),
            cache_ttl_s=int(os.getenv("RAG_CACHE_TTL_S", "300") or 300),
            cache_namespace=os.getenv("RAG_CACHE_NS", "vkrag") or "vkrag",
            dense_enabled=_flag("RAG_DENSE_ENABLED"),
            include_global=os.getenv("RAG_INCLUDE_GLOBAL", "1").strip().lower() not in ("0", "false", "no", "off", ""),
        )

    def cache_key(self, tenant_id: str, store: str, stage: str, query: str, campaign_id: str = "") -> str:
        """Tenant-FIRST cache key. The tenant_id is the leading, un-hashed segment
        so a key can NEVER be reused across tenants (cross-tenant cache-bleed
        guard). The volatile (query) tail is hashed for bounded key length."""
        qh = hashlib.sha1((query or "").strip().lower().encode("utf-8")).hexdigest()[:16]
        return f"{tenant_id}|{campaign_id}|{store}|{stage}|{qh}"
