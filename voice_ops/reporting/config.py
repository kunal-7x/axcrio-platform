"""voice_ops.reporting.config — knobs for the reporting layer.

Pure dataclass, stdlib only. No env read at import time (the seam wave reads env
and constructs this); defaults make the resting build inert + safe.
"""
from __future__ import annotations

from dataclasses import dataclass

from voice_kernel.events.timeutil import VENDOR_TZ_NAME


@dataclass(frozen=True)
class ReportingConfig:
    """Reporting knobs.

    * `vendor_tz` — the wall-clock zone used for date-range windows + day-grouping
      (Asia/Kolkata). Storing UTC + rendering in this zone is the off-by-one fix.
    * `enabled` — when False the consumer/service are inert (default OFF until the
      seam wave registers a bus + a backend). The query API still works against an
      empty store, so a dashboard sees zeros rather than an error.
    * `consumer_group` — the W8 consumer-group name the reporting sink subscribes
      under (one group, separate from CRM/analytics groups so each gets every event).
    * `default_preset` — the founder's default landing range ("today").
    * `hot_lead_limit` — how many hot-lead names a daily summary lists by default.
    """

    vendor_tz: str = VENDOR_TZ_NAME
    enabled: bool = False
    consumer_group: str = "reporting"
    default_preset: str = "today"
    hot_lead_limit: int = 25
