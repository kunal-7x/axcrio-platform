"""voice_ops.compliance.config — ComplianceConfig: the gate flags + legal knobs.

Default OFF / safe. The master flag `COMPLIANCE_ENABLED` is DEFAULT OFF because turning
the gate on BEFORE DLT + number-series are actually registered would block 100% of dials
(design/W26 §7). When OFF, `preflight` returns `allow` with `compliance_unenforced=true`.

The LEGAL WINDOW FLOOR is the load-bearing constant: commercial calls 10:00–19:00
recipient-local; BFSI/collections 08:00–19:00 (design/W26 §3.4 / Tier A #4). A tenant
window is INTERSECTED with this — a tenant can only NARROW, never widen.

Flag pattern is the codebase-native one (agent.py:451 style):
    os.getenv("NAME", "0") in ("1","true","True","yes","on")

ENV:
  COMPLIANCE_ENABLED            "1" to ARM the dial-time gate              (default OFF)
  COMPLIANCE_WINDOW_START       legal floor window open  "HH:MM"          (default 10:00)
  COMPLIANCE_WINDOW_END         legal floor window close "HH:MM"          (default 19:00)
  COMPLIANCE_BFSI_WINDOW_START  BFSI/collections floor open               (default 08:00)
  COMPLIANCE_DISCLOSURE_TIER    default disclosure tier 0|1|2             (default 0)
  COMPLIANCE_RECORDING_NOTICE   "1" -> include record cue in disclosure   (default ON)
  COMPLIANCE_EXPLICIT_CONSENT_DAYS  explicit-txn consent validity days    (default 7)
  COMPLIANCE_DND_REFRESH_DAYS   max DND-cache age before re-scrub          (default 30)
  COMPLIANCE_RECORDING_TTL_DAYS recording retention TTL                    (default 90)
  COMPLIANCE_TRANSCRIPT_TTL_DAYS transcript retention TTL                  (default 180)
  COMPLIANCE_AUDIT_TTL_DAYS     compliance-audit retention (UCC >=6mo)     (default 180)
  COMPLIANCE_NUMBER_HASH_SALT   salt for hashing phones at rest (PII-min)  (default '')
  COMPLIANCE_DEFAULT_TZ         recipient tz default                       (default Asia/Kolkata)
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


@dataclass(frozen=True)
class ComplianceConfig:
    """Immutable snapshot of the compliance knobs. `from_env()` in prod; construct
    directly in tests."""

    enabled: bool = False                      # COMPLIANCE_ENABLED — master OFF default
    window_start: str = "10:00"                # legal floor (commercial)
    window_end: str = "19:00"
    bfsi_window_start: str = "08:00"           # BFSI/collections floor open
    bfsi_window_end: str = "19:00"
    disclosure_tier: int = 0
    recording_notice: bool = True
    explicit_consent_days: int = 7
    dnd_refresh_days: int = 30
    recording_ttl_days: int = 90
    transcript_ttl_days: int = 180
    audit_ttl_days: int = 180
    number_hash_salt: str = ""
    default_tz: str = "Asia/Kolkata"

    @classmethod
    def from_env(cls) -> "ComplianceConfig":
        return cls(
            enabled=_flag("COMPLIANCE_ENABLED"),
            window_start=(os.getenv("COMPLIANCE_WINDOW_START") or "10:00").strip(),
            window_end=(os.getenv("COMPLIANCE_WINDOW_END") or "19:00").strip(),
            bfsi_window_start=(os.getenv("COMPLIANCE_BFSI_WINDOW_START") or "08:00").strip(),
            bfsi_window_end=(os.getenv("COMPLIANCE_BFSI_WINDOW_END") or "19:00").strip(),
            disclosure_tier=_int("COMPLIANCE_DISCLOSURE_TIER", 0),
            recording_notice=_flag("COMPLIANCE_RECORDING_NOTICE", "1"),
            explicit_consent_days=_int("COMPLIANCE_EXPLICIT_CONSENT_DAYS", 7),
            dnd_refresh_days=_int("COMPLIANCE_DND_REFRESH_DAYS", 30),
            recording_ttl_days=_int("COMPLIANCE_RECORDING_TTL_DAYS", 90),
            transcript_ttl_days=_int("COMPLIANCE_TRANSCRIPT_TTL_DAYS", 180),
            audit_ttl_days=_int("COMPLIANCE_AUDIT_TTL_DAYS", 180),
            number_hash_salt=(os.getenv("COMPLIANCE_NUMBER_HASH_SALT") or "").strip(),
            default_tz=(os.getenv("COMPLIANCE_DEFAULT_TZ") or "Asia/Kolkata").strip(),
        )
