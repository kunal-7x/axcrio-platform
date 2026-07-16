"""grow.config — immutable env snapshot for Haptica Grow (FEATURE_GROW gate + CAPI creds).

OFF + SHADOW by default (fail-safe). The module mounts only when FEATURE_GROW=1, and even
then the Signal Loop runs in SHADOW MODE (logs the would-send CAPI payload, never POSTs)
until real Meta/Google conversion creds are present — exactly the ElevateX plan's "build
the CAPI integration in Phase 1, even crudely" without risking a bad upload or needing
the founder-gated Ads OAuth. stdlib-only; `from_env()` reads os.environ once.
"""
from __future__ import annotations

import os
from dataclasses import dataclass


def _flag(name: str, default: str = "0") -> bool:
    return (os.getenv(name, default) or default).strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class GrowConfig:
    enabled: bool = False
    # --- L5 scoring ---
    pack: str = "real_estate"          # industry pack id (KPI defaults, angle library)
    hot_threshold: int = 70            # score >= => HOT (also the QualifiedLead ladder gate)
    warm_threshold: int = 40           # score in [warm,hot) => WARM
    junk_threshold: int = 25           # score < => JUNK
    # --- PII-min ---
    hash_salt: str = "grow-dev-salt"   # SALTED at-rest identity (NOT used for CAPI match keys)
    # --- L7 Signal Loop (CAPI / Enhanced Conversions) ---
    shadow_mode: bool = True           # True => never POST; log the would-send (default safe)
    meta_pixel_id: str = ""            # a.k.a. dataset id for CAPI
    meta_capi_token: str = ""          # system-user access token
    meta_capi_test_event_code: str = ""  # routes events to Test Events tab (no live impact)
    meta_graph_version: str = "v21.0"
    google_customer_id: str = ""       # Enhanced Conversions for Leads
    google_conversion_action: str = ""
    dispatch_timeout_s: int = 8

    @property
    def meta_live(self) -> bool:
        """Live Meta CAPI possible only with a dataset id + token AND shadow OFF."""
        return bool(self.meta_pixel_id and self.meta_capi_token) and not self.shadow_mode

    @property
    def google_live(self) -> bool:
        return bool(self.google_customer_id and self.google_conversion_action) and not self.shadow_mode

    @classmethod
    def from_env(cls) -> "GrowConfig":
        def _int(name: str, dflt: int) -> int:
            try:
                return int(os.getenv(name, "") or dflt)
            except (TypeError, ValueError):
                return dflt

        # shadow stays ON unless explicitly turned off AND a token exists.
        shadow = not _flag("GROW_SIGNALS_LIVE", "0")
        return cls(
            enabled=_flag("FEATURE_GROW", "0"),
            pack=(os.getenv("GROW_PACK", "real_estate") or "real_estate").strip(),
            hot_threshold=_int("GROW_HOT_THRESHOLD", 70),
            warm_threshold=_int("GROW_WARM_THRESHOLD", 40),
            junk_threshold=_int("GROW_JUNK_THRESHOLD", 25),
            hash_salt=(os.getenv("GROW_HASH_SALT")
                       or os.getenv("COMPLIANCE_HASH_SALT")
                       or "grow-dev-salt").strip(),
            shadow_mode=shadow,
            meta_pixel_id=(os.getenv("META_CAPI_PIXEL_ID") or os.getenv("META_PIXEL_ID") or "").strip(),
            meta_capi_token=(os.getenv("META_CAPI_TOKEN") or "").strip(),
            meta_capi_test_event_code=(os.getenv("META_CAPI_TEST_EVENT_CODE") or "").strip(),
            meta_graph_version=(os.getenv("META_GRAPH_VERSION") or "v21.0").strip(),
            google_customer_id=(os.getenv("GOOGLE_ADS_CUSTOMER_ID") or "").strip(),
            google_conversion_action=(os.getenv("GOOGLE_CONVERSION_ACTION") or "").strip(),
            dispatch_timeout_s=_int("GROW_DISPATCH_TIMEOUT_S", 8),
        )

    def status(self) -> dict:
        """Dormant-safe status surface (no secrets) for GET /grow/health."""
        return {
            "enabled": self.enabled, "pack": self.pack,
            "thresholds": {"hot": self.hot_threshold, "warm": self.warm_threshold,
                           "junk": self.junk_threshold},
            "signals": {
                "shadow_mode": self.shadow_mode,
                "meta_live": self.meta_live, "google_live": self.google_live,
                "meta_configured": bool(self.meta_pixel_id and self.meta_capi_token),
                "meta_test_mode": bool(self.meta_capi_test_event_code),
                "google_configured": bool(self.google_customer_id and self.google_conversion_action),
            },
        }
