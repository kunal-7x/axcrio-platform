"""llm_router — SMART provider key pool + secure hot-reloadable key-store (AIM-owned).

ADDITIVE + ISOLATED. Pure-stdlib pool (time/threading/itertools); cryptography only for the
encrypted key-store (degrades to 0600 plaintext if unavailable). This package is imported by
aim_voice_agent.py (the AIM voice path) and caller.py (the super-admin key CRUD routes) ONLY.

It does NOT touch agent.py (the outbound earner), trunks, firewall, or SIP. A failed import here
degrades the AIM voice path gracefully back to the legacy linear `_next_groq_key`/`_next_sarvam_key`
rotation — it can never crash the worker or the earner.

Public surface:
    from llm_router import get_pool, GROQ_POOL, SARVAM_POOL, SAMBANOVA_POOL, OPENROUTER_POOL
    from llm_router import key_store
"""
from .provider_pool import (  # noqa: F401
    ProviderPool,
    get_pool,
    GROQ_POOL,
    SARVAM_POOL,
    SAMBANOVA_POOL,
    OPENROUTER_POOL,
    DEFAULT_COOLDOWN,
    MAX_COOLDOWN,
)
from . import key_store  # noqa: F401

__all__ = [
    "ProviderPool", "get_pool", "GROQ_POOL", "SARVAM_POOL", "SAMBANOVA_POOL",
    "OPENROUTER_POOL", "DEFAULT_COOLDOWN", "MAX_COOLDOWN", "key_store",
]
