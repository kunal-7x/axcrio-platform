"""ads_engine.connectors — the connector registry + the shared async HTTP base.

GUARDED LAZY IMPORTS (binding crash-proofness, ARCH_SKELETON f.4): importing this package must
NEVER crash, even if a single platform connector module is missing or half-built or imports a
dep that isn't on this box. So the four platform modules (meta/google/whatsapp/telephony) are
imported LAZILY + individually-guarded inside `get_connector` — a broken `google.py` can never
take down `meta`, and an httpx-less build still imports the package. The base substrate (`base.py`)
is the only thing imported eagerly, and it too imports httpx lazily.

`get_connector(tenant_id, channel)` resolves creds via vault_adapter.get_connector_creds and
returns the right subclass pinned to config's version. `None` (or an ok=False creds envelope) =>
the channel is dormant; the caller renders not_configured, never a crash.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

# base.py is safe to import eagerly (httpx is lazy inside it).
from .base import BaseConnector, ConnectorError, ConnectorResult  # noqa: F401

_log = logging.getLogger("ads_engine.connectors")

__all__ = [
    "BaseConnector",
    "ConnectorError",
    "ConnectorResult",
    "get_connector",
    "available_channels",
]

# channel -> (module attr, class name). Imported lazily + guarded; absent = channel dormant.
_CONNECTOR_CLASSES = {
    "meta": ("meta", "MetaConnector"),
    "google": ("google", "GoogleConnector"),
    "whatsapp": ("whatsapp", "WhatsAppConnector"),
    "telephony": ("telephony", "TelephonyConnector"),
}


def _load_class(channel: str):
    """Lazily import the connector class for a channel. Returns the class or None (never raises).

    A missing module, a broken module, or a missing class all degrade to None — a single bad
    connector can never crash the package or the other connectors."""
    spec = _CONNECTOR_CLASSES.get(channel)
    if spec is None:
        return None
    mod_name, cls_name = spec
    try:
        import importlib
        mod = importlib.import_module(f"{__name__}.{mod_name}")
    except Exception as exc:  # noqa: BLE001 — connector module absent/broken -> dormant
        _log.warning("ads_engine.connectors: %s connector unavailable: %r",
                     channel, type(exc).__name__)
        return None
    cls = getattr(mod, cls_name, None)
    if cls is None:
        _log.warning("ads_engine.connectors: %s connector class %s missing", channel, cls_name)
    return cls


def available_channels() -> list:
    """Which connector modules actually import on this box (for diagnostics/health). Never raises."""
    return [ch for ch in _CONNECTOR_CLASSES if _load_class(ch) is not None]


def _version_for(channel: str) -> str:
    """The pinned API version for a channel (from config). None-safe."""
    try:
        from .. import config
    except Exception:  # noqa: BLE001
        return ""
    return {
        "meta": getattr(config, "META_API_VERSION", ""),
        "google": getattr(config, "GOOGLE_ADS_VERSION", ""),
        "whatsapp": getattr(config, "WHATSAPP_GRAPH_VERSION", ""),
        "telephony": "",
    }.get(channel, "")


def get_connector(tenant_id: str, channel: str, *, http: Any = None) -> Optional[BaseConnector]:
    """Resolve a ready connector for (tenant, channel), or None if dormant. NEVER raises.

    Steps: load the class (guarded) -> resolve creds via vault_adapter -> construct pinned to the
    config version. A missing class, missing creds, or any error -> None (the caller renders the
    channel not_configured). `http` is an optional injected httpx client (tests pass a mock one).
    """
    cls = _load_class(channel)
    if cls is None:
        return None
    try:
        from .. import vault_adapter
    except Exception:  # noqa: BLE001
        return None
    try:
        creds = vault_adapter.get_connector_creds(tenant_id, channel)
    except Exception as exc:  # noqa: BLE001 — degrade-never-raise
        _log.warning("ads_engine.connectors.get_connector creds failed (%s): %r",
                     channel, type(exc).__name__)
        return None
    if creds is None or not getattr(creds, "ok", False):
        return None
    try:
        return cls(creds, version=_version_for(channel), http=http)
    except Exception as exc:  # noqa: BLE001 — a broken __init__ must not crash the spine
        _log.warning("ads_engine.connectors.get_connector construct failed (%s): %r",
                     channel, type(exc).__name__)
        return None
