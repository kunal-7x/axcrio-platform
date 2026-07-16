"""ai_manager — the voice/chat AI-Manager control plane (business execution brain).

A vendor calls (or chats) the AI Manager and tells it what to do ("send today's report",
"set Meta budget ₹500", "call all hot leads after 5 PM"). The package UNDERSTANDS the
instruction (intent.driver NLU), VERIFIES the caller (identity + registry + firewall PIN),
checks PERMISSIONS + RISK (identity/PolicyEngine, deterministic — the LLM never authorizes),
EXECUTES via the workforce adapters (delegate -> tools/catalog over an authenticated loopback),
and AUDITS everything (store + audit_bridge). The channel-agnostic state_machine drives the
voice path; endpoints.py serves the dashboard Test-Console + management API under /ai-manager.

DESIGN LAW (mirrors provider_registry / grow):
  * ADDITIVE + flag-gated. caller.py mounts endpoints.router only when FEATURE_AI_MANAGER=1;
    AIM_ENABLED=0 is the instant kill-switch. Importing this package does ZERO I/O and NEVER
    raises — an empty-env / key-less box loads it cleanly and every surface degrades DORMANT
    (store -> InMemory, recorder -> Null, NLU -> deterministic stub, transport -> dormant,
    schema -> no-op). The live platform rests byte-identical.
  * EARNER-SAFE. Rides caller.py (separate process). NEVER imports agent.py (the live voice
    earner), the SIP trunk, or any live-call machinery.

Import-guarded surface: a broken/half-deployed submodule can NEVER break `import ai_manager`
or `ai_manager.status()` — the shell (config + status) always loads; behavioural modules are
guarded; the FastAPI router is guarded and falls to None when FastAPI is absent.
"""
from __future__ import annotations

# --- shell: always importable, empty-env safe, never raises. ---
from . import config  # noqa: F401

# --- behavioural surface (lazy db.engine / wallet / firewall inside; import does no I/O). ---
# All-or-nothing guard per layer so a missing optional dep degrades the whole package to its
# dormant shell rather than crashing the monolith mount.
try:  # core persistence + identity + execution brain
    from . import store, identity, registry, delegate, audit_bridge, firewall_bridge  # noqa: F401
    _CORE_LOADED = True
except Exception:  # noqa: BLE001 — never let a core import failure break the shell
    _CORE_LOADED = False

try:  # recorder (livekit/boto3 optional)
    from . import recorder  # noqa: F401
    _REC_LOADED = True
except Exception:  # noqa: BLE001
    _REC_LOADED = False

try:  # NLU + tool catalog
    from .intent import driver  # noqa: F401
    from . import tools  # noqa: F401
    _NLU_LOADED = True
except Exception:  # noqa: BLE001
    _NLU_LOADED = False

try:  # the channel-agnostic command state machine
    from . import state_machine  # noqa: F401
    _SM_LOADED = True
except Exception:  # noqa: BLE001
    _SM_LOADED = False

# --- mount surface: the FastAPI router. Guarded — FastAPI is optional at scaffold time
# (endpoints sets router=None when it's absent), and a failure here can NEVER break the shell
# or the live spine. caller.py mounts it ONLY when FEATURE_AI_MANAGER=1. ---
try:  # pragma: no cover - all-or-nothing mount surface
    from . import endpoints  # noqa: F401
    router = getattr(endpoints, "router", None)
    _ENDPOINTS_LOADED = router is not None
except Exception:  # noqa: BLE001 — never let an endpoints import failure break the shell
    router = None  # type: ignore
    _ENDPOINTS_LOADED = False


if _ENDPOINTS_LOADED and _CORE_LOADED:
    __version__ = "1.0.0"
elif _CORE_LOADED:
    __version__ = "0.9.0-core"
else:
    __version__ = "0.1.0-shell"


def status() -> dict:
    """Dormancy/config snapshot for `GET /ai-manager/status` (endpoints calls this via
    `from . import status as _pkg_status`). BOOLEANS ONLY — never echoes a secret/key.
    Never raises (every probe is guarded)."""
    snap: dict = {"module": "ai_manager", "version": __version__}
    try:
        snap.update(config.snapshot())
    except Exception:  # noqa: BLE001
        pass
    try:
        snap["store_available"] = bool(_CORE_LOADED and store.available())
    except Exception:  # noqa: BLE001
        snap["store_available"] = False
    try:
        from .intent import driver as _d
        snap["nlu"] = _d.status()
    except Exception:  # noqa: BLE001
        snap["nlu"] = "not_configured"
    snap["loaded"] = {
        "core": _CORE_LOADED, "recorder": _REC_LOADED, "nlu": _NLU_LOADED,
        "state_machine": _SM_LOADED, "endpoints": _ENDPOINTS_LOADED,
    }
    # `enabled` is the founder-facing master truth: feature flag AND runtime enable.
    try:
        snap["enabled"] = config.is_enabled()
    except Exception:  # noqa: BLE001
        snap["enabled"] = False
    return snap


__all__ = ["config", "status", "router", "__version__"]
