"""voice_ops.telephony.config — TelephonyOpsConfig: flags + Sales-OS knobs.

Default OFF / safe everywhere (mirrors voice_ops.booking.config + voice_ops.callback.config).
The whole package is inert until a founder-signed seam wave flips `TELEPHONY_OPS_ENABLED`.
Until then the dial loop never calls through these seams and the live path is byte-identical.

Flag pattern is the codebase-native one (agent.py:451 OPENER_ALREADY_SAID style):
    os.getenv("NAME", "0") in ("1","true","True","yes","on")
No new config framework.

ENV (all under the box .env):
  TELEPHONY_OPS_ENABLED        "1" to arm the Sales-OS seams              (default OFF)
  TELEPHONY_PER_NUMBER_DAILY_CAP   per-number daily dial cap               (default 250)
  TELEPHONY_PER_NUMBER_CONCURRENCY max concurrent calls on one number      (default 2)
  TELEPHONY_COOLDOWN_SECONDS   min gap between dials on the SAME number     (default 8)
  TELEPHONY_ANSWER_RATE        planning assumption: fraction answered       (default 0.30)
  TELEPHONY_AVG_CALL_SECONDS   planning assumption: avg connected seconds   (default 90)
  TELEPHONY_DIAL_OVERHEAD_SEC  planning: ring + setup + wrap per dial slot  (default 45)
  TELEPHONY_HEALTH_WINDOW_SEC  rolling window for the spam scorer (seconds) (default 3600)
  TELEPHONY_HEALTH_MIN_SAMPLES min outcomes before a score is trusted       (default 8)
  TELEPHONY_HEALTH_DEGRADE_AT  health score (0..1) below which a number is throttled (default 0.45)
  TELEPHONY_HEALTH_QUARANTINE_AT  health score below which a number is rested        (default 0.20)
  TELEPHONY_HEALTH_RECOVER_AT  health score at/above which a throttled number reopens (default 0.65)
  TELEPHONY_QUARANTINE_MINUTES rest duration for a quarantined number        (default 90)
  TELEPHONY_LEAD_LOCK_TTL_SEC  per-lead dial-lock lease (self-heals a crashed worker) (default 300)
  TELEPHONY_DEFAULT_TZ         IANA tz for window planning                   (default Asia/Kolkata)
"""
from __future__ import annotations

import os
from dataclasses import dataclass

_TRUE = ("1", "true", "True", "yes", "on")


def _flag(name: str, default: str = "0") -> bool:
    v = os.getenv(name, default)
    return (v or "").strip() in _TRUE


def _int(name: str, default: int) -> int:
    try:
        return int(str(os.getenv(name, str(default))).strip() or default)
    except (TypeError, ValueError):
        return default


def _float(name: str, default: float) -> float:
    try:
        return float(str(os.getenv(name, str(default))).strip() or default)
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class TelephonyOpsConfig:
    """Immutable snapshot of the telephony Sales-OS knobs. Build with `from_env()`
    in production; construct directly in tests."""

    enabled: bool = False                  # TELEPHONY_OPS_ENABLED — master OFF default
    per_number_daily_cap: int = 250
    per_number_concurrency: int = 2
    cooldown_seconds: int = 8
    # capacity-planning assumptions
    answer_rate: float = 0.30
    avg_call_seconds: int = 90
    dial_overhead_seconds: int = 45
    # spam-reputation health
    health_window_seconds: int = 3600
    health_min_samples: int = 8
    health_degrade_at: float = 0.45
    health_quarantine_at: float = 0.20
    health_recover_at: float = 0.65
    quarantine_minutes: int = 90
    # lead lock
    lead_lock_ttl_seconds: int = 300
    default_tz: str = "Asia/Kolkata"

    @classmethod
    def from_env(cls) -> "TelephonyOpsConfig":
        return cls(
            enabled=_flag("TELEPHONY_OPS_ENABLED"),
            per_number_daily_cap=_int("TELEPHONY_PER_NUMBER_DAILY_CAP", 250),
            per_number_concurrency=_int("TELEPHONY_PER_NUMBER_CONCURRENCY", 2),
            cooldown_seconds=_int("TELEPHONY_COOLDOWN_SECONDS", 8),
            answer_rate=_float("TELEPHONY_ANSWER_RATE", 0.30),
            avg_call_seconds=_int("TELEPHONY_AVG_CALL_SECONDS", 90),
            dial_overhead_seconds=_int("TELEPHONY_DIAL_OVERHEAD_SEC", 45),
            health_window_seconds=_int("TELEPHONY_HEALTH_WINDOW_SEC", 3600),
            health_min_samples=_int("TELEPHONY_HEALTH_MIN_SAMPLES", 8),
            health_degrade_at=_float("TELEPHONY_HEALTH_DEGRADE_AT", 0.45),
            health_quarantine_at=_float("TELEPHONY_HEALTH_QUARANTINE_AT", 0.20),
            health_recover_at=_float("TELEPHONY_HEALTH_RECOVER_AT", 0.65),
            quarantine_minutes=_int("TELEPHONY_QUARANTINE_MINUTES", 90),
            lead_lock_ttl_seconds=_int("TELEPHONY_LEAD_LOCK_TTL_SEC", 300),
            default_tz=(os.getenv("TELEPHONY_DEFAULT_TZ") or "Asia/Kolkata").strip(),
        )
