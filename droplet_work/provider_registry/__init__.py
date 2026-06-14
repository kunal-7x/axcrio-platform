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

# --- W2 behavioural surface: guard + adapter + named-transforms + creds. ---
# Import-guarded so a box that somehow lacks a W2 file (or `cryptography`) still imports the
# W1 shell cleanly. These modules are PURE/local + empty-env safe; importing them does ZERO
# network I/O and NEVER raises (the resting-byte-identical guarantee). Not mounted until W4.
try:  # pragma: no cover - all-or-nothing W2 surface
    from . import ssrf_guard, adapter, named_transforms, credentials  # noqa: F401
    from .ssrf_guard import validate_endpoint, revalidate_redirect_location  # noqa: F401
    from .adapter import (  # noqa: F401
        build_request,
        parse_response,
        validate_field_map,
        FieldMapError,
    )
    from .credentials import (  # noqa: F401
        encrypt_credential,
        decrypt_credential,
        compute_aad,
        CredentialError,
    )
    _W2_LOADED = True
except Exception:  # noqa: BLE001 — never let a W2 import failure break the W1 shell
    _W2_LOADED = False

# --- W3 behavioural surface: store + admin_store + registry + health (resolve/fallback/breaker).
# Import-guarded like W2 — these modules import db.engine lazily (never at module import) and
# NEVER do network I/O on import, so an empty-env box loads them cleanly (resting byte-identical).
# Not mounted until W4. registry.get_provider is the single capability-keyed resolution point.
try:  # pragma: no cover - all-or-nothing W3 surface
    from . import store, admin_store, registry, health  # noqa: F401
    from .registry import get_provider, ProviderClient, resolve_status  # noqa: F401
    _W3_LOADED = True
except Exception:  # noqa: BLE001 — never let a W3 import failure break the W1/W2 shell
    _W3_LOADED = False

if _W3_LOADED:
    __version__ = "0.3.0-w3"
elif _W2_LOADED:
    __version__ = "0.2.0-w2"
else:
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
    # W2 behavioural surface
    "validate_endpoint",
    "revalidate_redirect_location",
    "build_request",
    "parse_response",
    "validate_field_map",
    "FieldMapError",
    "encrypt_credential",
    "decrypt_credential",
    "compute_aad",
    "CredentialError",
    # W3 behavioural surface
    "get_provider",
    "ProviderClient",
    "resolve_status",
    "__version__",
]
