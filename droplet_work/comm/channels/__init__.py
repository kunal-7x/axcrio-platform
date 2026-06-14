"""comm.channels — the channel adapters behind the one ChannelAdapter contract.

Wave 1 = Telegram only. Email (W3) + SMS (W5) add a sibling module each, behind the SAME
base.ChannelAdapter contract — adding a channel is one new adapter file + one provider_def
row, zero new crypto, zero engine change.

Pure import surface (the dataclasses + the Telegram adapter). Importing does ZERO I/O and
NEVER raises (httpx is lazy inside the adapter) — the resting-byte-identical guarantee.
"""
from __future__ import annotations

from .base import (  # noqa: F401
    Button,
    ChannelAdapter,
    MediaItem,
    SendEnvelope,
    SendResult,
)
from .telegram import TelegramAdapter  # noqa: F401

__all__ = [
    "Button",
    "ChannelAdapter",
    "MediaItem",
    "SendEnvelope",
    "SendResult",
    "TelegramAdapter",
]
