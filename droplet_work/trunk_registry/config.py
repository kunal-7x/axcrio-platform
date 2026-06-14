"""trunk_registry.config — env reads for the telephony trunk registry (T2).

Spec: design/TELEPHONY-INDEPENDENCE-PLAN.md §2 (the package) + §5 (T2: flag OFF) + §2.4
(IN-PROCESS concurrency, NOT the fail-open Redis) + §2.5 (rotation / velocity throttle).

A column-for-column TWIN of provider_registry/config.py: every value is read from os.environ
at CALL TIME, never cached at import, so:
  * an empty environment imports cleanly and yields safe defaults (flag OFF),
  * a flag flip takes effect on the next read with NO restart of THIS module's import,
  * nothing here ever raises at import (the master design law: resting byte-identical).

The single load-bearing flag is TRUNK_REGISTRY_ENABLED (default OFF). With it OFF the registry
is dormant: no endpoints mounted (T3), no trunk resolution, no LiveKit-sync, no I/O. The
caller.py dial loop keeps using the hardcoded `TRUNK` env (byte-identical). This module only
*reads* config — it does not act on it (that is the behavioural modules).
"""
from __future__ import annotations

import os
from typing import List

# The master flag. Default OFF -> the whole registry is dormant + the platform rests
# byte-identical (caller.py:184 TRUNK env path unchanged). Mounted (T3) + consulted by the
# strangler dial-loop cut (T5) ONLY when '1'.
FLAG_ENV = "TRUNK_REGISTRY_ENABLED"


def _truthy(val: str | None) -> bool:
    """Lenient truthy parse (mirrors how the rest of the box reads boolean flags:
    '1' / 'true' / 'yes' / 'on', case-insensitive). Empty / unset -> False."""
    if val is None:
        return False
    return val.strip().lower() in ("1", "true", "yes", "on", "y", "t")


def is_enabled() -> bool:
    """Is the trunk registry turned ON? Read at call time; default OFF.

    With this False, the registry must be fully dormant — no mount, no resolution, no
    LiveKit-sync, no network I/O. This is the resting-byte-identical guarantee."""
    return _truthy(os.environ.get(FLAG_ENV))


def _int_env(key: str, default: int) -> int:
    """Read an int env var; fall back to default on unset/garbage (never raises)."""
    raw = os.environ.get(key)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw.strip())
    except (TypeError, ValueError):
        return default


def _float_env(key: str, default: float) -> float:
    raw = os.environ.get(key)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw.strip())
    except (TypeError, ValueError):
        return default


def _csv_env(key: str) -> List[str]:
    """Read a comma-separated env var into a clean list (empty -> [])."""
    raw = os.environ.get(key) or ""
    return [part.strip() for part in raw.split(",") if part.strip()]


def registry_config() -> dict:
    """Snapshot of the registry's runtime config, computed fresh from os.environ.

    Returns plain JSON-able values only — NEVER a secret. Safe to surface in a /health
    style diagnostic. The behavioural modules consume these knobs.

      * enabled                  -> the master flag.
      * box_global_concurrency   -> the hard ceiling on TOTAL in-flight calls across all trunks
                                     in THIS process (red-team A4: never exceed the box RTP ceiling).
      * health_interval_s        -> default background-probe cadence.
      * health_fail_threshold    -> consecutive fails before the circuit opens (=3).
      * health_backoff_base_s    -> circuit-open backoff base (60 -> 120 -> 240).
      * ringout_burst_window_s   -> rolling window (s) over which zero-duration ring-outs are counted
                                     for the spam-reputation guard (red-team B-rel).
      * ringout_burst_threshold  -> # of zero-duration ring-outs in the window that QUARANTINES a DID.
      * quarantine_minutes       -> how long a DID/trunk is rested when quarantined.
      * trunk_disable_quarantines-> red-team B3: # of quarantines on ONE trunk that DISABLES it
                                     (stop rotating + loud alert; do NOT silently burn the pool).
      * velocity_min_spacing_s   -> per-DID minimum seconds between calls (velocity throttle; the
                                     STRONGER flag signal than daily volume — red-team velocity).
      * velocity_calls_per_hour  -> per-DID calls/hour ceiling (velocity throttle).
      * ssrf_allow_hosts         -> optional host allowlist for SIP hosts (empty = allow any public).
      * vault_backend            -> the get_secret() seam backend ('local' interim Fernet -> 'vault').
    """
    return {
        "enabled": is_enabled(),
        "box_global_concurrency": _int_env("TRUNK_BOX_GLOBAL_CONCURRENCY", 90),
        "health_interval_s": _int_env("TRUNK_HEALTH_INTERVAL_S", 60),
        "health_fail_threshold": _int_env("TRUNK_HEALTH_FAIL_THRESHOLD", 3),
        "health_backoff_base_s": _int_env("TRUNK_HEALTH_BACKOFF_BASE_S", 60),
        "ringout_burst_window_s": _int_env("TRUNK_RINGOUT_BURST_WINDOW_S", 600),
        "ringout_burst_threshold": _int_env("TRUNK_RINGOUT_BURST_THRESHOLD", 5),
        "quarantine_minutes": _int_env("TRUNK_QUARANTINE_MINUTES", 120),
        "trunk_disable_quarantines": _int_env("TRUNK_DISABLE_QUARANTINES", 3),
        "velocity_min_spacing_s": _float_env("TRUNK_VELOCITY_MIN_SPACING_S", 8.0),
        "velocity_calls_per_hour": _int_env("TRUNK_VELOCITY_CALLS_PER_HOUR", 200),
        "ssrf_allow_hosts": _csv_env("TRUNK_SSRF_ALLOW_HOSTS"),
        "vault_backend": (os.environ.get("VAULT_BACKEND") or "local").strip().lower(),
    }
