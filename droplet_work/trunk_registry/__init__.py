"""trunk_registry — Telephony / SIP Trunk Registry (T2, flag OFF).

Spec: design/TELEPHONY-INDEPENDENCE-PLAN.md §2 (the package) + §5 (T1 DDL + T2 package,
flag `TRUNK_REGISTRY_ENABLED` default OFF) + §3 red-team B1/B-rel/C-rel/D.

A TWIN of provider_registry: same FORCE-RLS / `_global` write-lock / AAD AES-256-GCM
creds / append-only health / in-process concurrency / rotation / livekit_sync.

DESIGN LAW (non-negotiable):
  * ADDITIVE + flag-gated. Reads TRUNK_REGISTRY_ENABLED (default OFF) at CALL TIME,
    never at import — so an empty env imports cleanly and the platform rests
    byte-identical. The live caller.py TRUNK env path is UNCHANGED.
  * EARNER-SAFE. NEVER imports agent.py. Importing this package does ZERO network I/O
    and NEVER raises (resting-byte-identical guarantee).
  * MOUNTED ONLY at T3 (deferred — cross-product serialization vs the running video wave).
    Until T3, the package sits dormant on disk: py_compile-clean, gitleaks-clean.

T2 scope = this __init__ + all modules: config / schema / credentials / ssrf_guard /
health / store / admin_store / registry / concurrency / rotation / livekit_sync.
NO caller.py edit. NO service restart. NO calls.
"""
from __future__ import annotations

# --- Core surface: always importable, empty-env safe, never raises. ---
from .config import (  # noqa: F401
    FLAG_ENV,
    is_enabled,
    registry_config,
)
from .schema import (  # noqa: F401
    GLOBAL_TENANT,
    TrunkType,
    Direction,
    Transport,
    Encryption,
    DltStatus,
    RotationStrategy,
    CredentialScope,
    Purpose,
    SipTrunk,
    SipTrunkCred,
    SipTrunkHealth,
)

# --- Behavioural surface (shared primitives + store/registry/concurrency/rotation).
# Import-guarded: a missing dep never breaks the core shell (resting-byte-identical).
# NONE of these are mounted until T3 wires caller.py endpoints.
try:
    from . import ssrf_guard, credentials, health  # noqa: F401
    from .ssrf_guard import validate_endpoint  # noqa: F401
    from .credentials import (  # noqa: F401
        encrypt_credential,
        decrypt_credential,
        compute_aad,
        CredentialError,
    )
    _CRED_LOADED = True
except Exception:  # noqa: BLE001
    _CRED_LOADED = False

try:
    from . import store, admin_store, registry  # noqa: F401
    from .registry import get_trunk, TrunkChoice, resolve_status  # noqa: F401
    _STORE_LOADED = True
except Exception:  # noqa: BLE001
    _STORE_LOADED = False

try:
    from . import concurrency, rotation  # noqa: F401
    from .concurrency import acquire, release  # noqa: F401
    _CONC_LOADED = True
except Exception:  # noqa: BLE001
    _CONC_LOADED = False

try:
    from . import livekit_sync  # noqa: F401
    from .livekit_sync import (  # noqa: F401
        build_outbound_trunk_request,
        build_inbound_trunk_request,
        build_dispatch_rule_request,
        is_protected_trunk_id,
    )
    _LK_LOADED = True
except Exception:  # noqa: BLE001
    _LK_LOADED = False

if _STORE_LOADED and _CONC_LOADED and _LK_LOADED and _CRED_LOADED:
    __version__ = "0.2.0-t2"
elif _STORE_LOADED and _CRED_LOADED:
    __version__ = "0.2.0-t2-partial"
elif _CRED_LOADED:
    __version__ = "0.1.0-t2-cred-only"
else:
    __version__ = "0.1.0-t2-schema-only"

__all__ = [
    # flag
    "FLAG_ENV",
    "is_enabled",
    "registry_config",
    # schema
    "GLOBAL_TENANT",
    "TrunkType",
    "Direction",
    "Transport",
    "Encryption",
    "DltStatus",
    "RotationStrategy",
    "CredentialScope",
    "Purpose",
    "SipTrunk",
    "SipTrunkCred",
    "SipTrunkHealth",
    # credentials
    "encrypt_credential",
    "decrypt_credential",
    "compute_aad",
    "CredentialError",
    # ssrf
    "validate_endpoint",
    # registry
    "get_trunk",
    "TrunkChoice",
    "resolve_status",
    # concurrency
    "acquire",
    "release",
    # livekit_sync
    "build_outbound_trunk_request",
    "build_inbound_trunk_request",
    "build_dispatch_rule_request",
    "is_protected_trunk_id",
    # version
    "__version__",
]
