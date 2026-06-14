"""comm — the Communication package (Telegram now; Email/SMS later). Wave 1.

Spec: communication/COMMUNICATION-MASTER-PLAN.md (the whole plan) + §8 WAVE 1.

The channel registry IS the provider registry: a bot token is a provider_credentials row,
read + decrypted through the LIVE AAD-bound AES-256-GCM vault (ZERO new crypto). Adding a
channel = one adapter file + one provider_def row.

DESIGN LAW (non-negotiable, mirrors provider_registry/__init__):
  * ADDITIVE + flag-gated. Every flag (COMM_ENABLED / COMM_TELEGRAM_ENABLED /
    FEATURE_TELEGRAM_FOUNDER_ALERT / FEATURE_TELEGRAM_FOLLOWUP) is read at CALL TIME, default
    OFF -> the platform rests byte-identical (no send, no I/O, no route active when off).
  * EARNER-SAFE. This package rides caller.py (a separate box process). It NEVER imports
    agent.py (the live voice earner). Importing it does ZERO network I/O and NEVER raises.
    Every contact-facing send is asyncio.create_task'd by the caller.py hook (NEVER awaited on
    the dial loop) and bounded by a per-channel asyncio.wait_for inside the engine.

W1 surface = config (flags) + channels (the base contract + the Telegram adapter) + vault_read
(the credential bridge) + send_log (the comm_send_log writer) + engine (the dispatch seam).
The caller.py _finalize_call insertions (founder_alert / post_call) + the router mount land in
the NEXT phase, under the CALLER_EDIT_LOCK.
"""
from __future__ import annotations

# --- config (always importable, empty-env safe, never raises). ---
from .config import (  # noqa: F401
    comm_enabled,
    telegram_enabled,
    founder_alert_enabled,
    followup_enabled,
    config_snapshot,
)

# --- behavioural surface: the contract, the Telegram adapter, the bridges, the engine.
# Import-guarded so a box missing an optional dep (httpx / db.engine / provider_registry) still
# imports the config shell cleanly. These modules are PURE/local + empty-env safe; importing
# them does ZERO network I/O and NEVER raises (the resting-byte-identical guarantee).
try:  # pragma: no cover - all-or-nothing behavioural surface
    from .channels.base import (  # noqa: F401
        Button,
        ChannelAdapter,
        MediaItem,
        SendEnvelope,
        SendResult,
    )
    from .channels.telegram import TelegramAdapter  # noqa: F401
    from . import vault_read, send_log, engine  # noqa: F401
    _BEHAVIOURAL_LOADED = True
except Exception:  # noqa: BLE001 — never let an optional-dep import break the config shell
    _BEHAVIOURAL_LOADED = False

__version__ = "0.1.0-w1" if _BEHAVIOURAL_LOADED else "0.1.0-w1-shell"

__all__ = [
    # config
    "comm_enabled",
    "telegram_enabled",
    "founder_alert_enabled",
    "followup_enabled",
    "config_snapshot",
    # behavioural surface (present when deps are available)
    "Button",
    "ChannelAdapter",
    "MediaItem",
    "SendEnvelope",
    "SendResult",
    "TelegramAdapter",
    "__version__",
]
