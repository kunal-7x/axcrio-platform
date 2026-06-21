"""voice_ops.booking.config — BookingOpsConfig: flags + the booking-engine seam knobs.

Default OFF / safe everywhere (mirrors voice_ops.recording.config + voice_kernel.config).
The whole package is a tracked, droplet-free LAYER over the (gitignored) booking schema in
`droplet_work/booking/`. It is inert until a founder-signed seam wave flips
`BOOKING_OPS_ENABLED` — until then `book_site_visit` degrades to a benign "not_configured"
return (the live call path is never affected; the AI simply says it will confirm the time later).

Flag pattern is the codebase-native one (agent.py:451 OPENER_ALREADY_SAID style):
    os.getenv("NAME", "0") in ("1","true","True","yes","on")
No new config framework.

ENV (all under the box .env):
  BOOKING_OPS_ENABLED       "1" to arm the AI booking tool        (default OFF)
  BOOKING_DEFAULT_RESOURCE  the site-visit resource id the AI books into (default "site_visit")
  BOOKING_DEFAULT_TZ        IANA tz for date/time resolution      (default "Asia/Kolkata")
  BOOKING_DEFAULT_SLOT_MIN  slot length minutes                   (default 30)
  BOOKING_SOURCE_VOICE      source tag on AI-created bookings      (default "voice")
"""
from __future__ import annotations

import os
from dataclasses import dataclass

_TRUE = ("1", "true", "True", "yes", "on")


def _flag(name: str, default: str = "0") -> bool:
    v = os.getenv(name, default)
    return (v or "").strip() in _TRUE


@dataclass(frozen=True)
class BookingOpsConfig:
    """Immutable snapshot of the booking-ops knobs. Build with `from_env()` in
    production; construct directly in tests."""

    enabled: bool = False                  # BOOKING_OPS_ENABLED — master OFF default
    default_resource_id: str = "site_visit"
    default_tz: str = "Asia/Kolkata"
    default_slot_minutes: int = 30
    source_voice: str = "voice"

    @classmethod
    def from_env(cls) -> "BookingOpsConfig":
        return cls(
            enabled=_flag("BOOKING_OPS_ENABLED"),
            default_resource_id=(os.getenv("BOOKING_DEFAULT_RESOURCE") or "site_visit").strip(),
            default_tz=(os.getenv("BOOKING_DEFAULT_TZ") or "Asia/Kolkata").strip(),
            default_slot_minutes=int(os.getenv("BOOKING_DEFAULT_SLOT_MIN", "30") or "30"),
            source_voice=(os.getenv("BOOKING_SOURCE_VOICE") or "voice").strip(),
        )
