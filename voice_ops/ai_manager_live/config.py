"""voice_ops.ai_manager_live.config — knobs for the live AI-Manager adapter."""
from __future__ import annotations

from dataclasses import dataclass

from voice_kernel.events.timeutil import VENDOR_TZ_NAME


@dataclass(frozen=True)
class AIManagerLiveConfig:
    """AI-Manager live-data knobs.

    * `vendor_tz` — render zone for human-facing report text + "today".
    * `default_preset` — the range a bare "send the report" command means ("today").
    * `hot_lead_limit` — how many hot-lead names the executive summary lists.
    * `summary_max_leads_detail` — how many hot leads get a per-lead detail line
      (the rest are summarized as "+N more").
    * `business_name` — used in the summary header + WhatsApp greeting (the tenant's
      brand; defaults to a neutral label).
    """

    vendor_tz: str = VENDOR_TZ_NAME
    default_preset: str = "today"
    hot_lead_limit: int = 25
    summary_max_leads_detail: int = 8
    business_name: str = "your business"
