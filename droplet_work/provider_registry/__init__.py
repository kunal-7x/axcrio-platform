"""provider_registry — the Universal Provider / Connector Registry (W1 shell).

Spec: design/PROVIDER-FRAMEWORK-PLAN.md §4 + §14 (W1 = DDL + package shell).

This package is the single resolution point for "which provider serves capability X
for tenant T", config-driven (PG-backed `provider_definitions` / `provider_credentials`
/ `provider_health_log`), multi-tenant FORCE-RLS, most-secure (AAD-bound AES-256-GCM via
the Vault `get_secret()` seam), with a 3-tier transform adapter, an SSRF guard, and a
health/circuit-breaker. Video Studio is the FIRST consumer; every future consumer plugs
in by declaring a capability.

DESIGN LAW (non-negotiable):
  * ADDITIVE + flag-gated. Reads PROVIDER_REGISTRY_ENABLED (default OFF) at CALL TIME,
    never at import — so an empty env imports cleanly and the platform rests
    byte-identical (nothing here is mounted/active until W4).
  * EARNER-SAFE. This package rides caller.py + the AI-asset service (separate box
    processes). It NEVER imports agent.py (the live voice earner). Importing this
    package must do ZERO network I/O and must NEVER raise.

W1 scope = the shell ONLY: this __init__, config.py (env reads), schema.py (the
dataclasses). The behavioural modules (ssrf_guard / adapter / named_transforms /
credentials / store / admin_store / registry / health / endpoints) land in W2+.
Importing a not-yet-built module is therefore guarded below so `from provider_registry
import is_enabled` works on a box that only has the W1 files.
"""
from __future__ import annotations

# --- W1 shell surface: always importable, empty-env safe, never raises. ---
from .config import (  # noqa: F401
    FLAG_ENV,
    is_enabled,
    registry_config,
)
from .schema import (  # noqa: F401
    Capability,
    TransformType,
    ProviderType,
    AuthScheme,
    CredentialScope,
    ProviderDef,
    ProviderCred,
)

__version__ = "0.1.0-w1"

__all__ = [
    # config
    "FLAG_ENV",
    "is_enabled",
    "registry_config",
    # schema
    "Capability",
    "TransformType",
    "ProviderType",
    "AuthScheme",
    "CredentialScope",
    "ProviderDef",
    "ProviderCred",
    "__version__",
]
