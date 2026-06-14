"""provider_registry.config — env reads for the registry (W1 shell).

Spec: design/PROVIDER-FRAMEWORK-PLAN.md §4 ("config.py — env reads (flag, allowlist,
health interval, SSRF policy) — call-time, never cached") + §8 (the flag) + §14 W1.

PATTERN (mirrors droplet_work/config.py): every value is read from os.environ at CALL
TIME, never cached at import, so:
  * an empty environment imports cleanly and yields safe defaults (flag OFF),
  * a flag flip takes effect on the next read with NO restart of THIS module's import,
  * nothing here ever raises at import (the master design law: resting byte-identical).

The single load-bearing flag is PROVIDER_REGISTRY_ENABLED (default OFF). With it OFF the
registry is dormant: no endpoints mounted (W4), no resolution, no I/O. This module only
*reads* config — it does not act on it (that is W2+).
"""
from __future__ import annotations

import os
from typing import List

# The master flag. Default OFF -> the whole registry is dormant + the platform rests
# byte-identical. Mounted (W4) and consulted by every consumer (W5+) only when '1'.
FLAG_ENV = "PROVIDER_REGISTRY_ENABLED"


def _truthy(val: str | None) -> bool:
    """Lenient truthy parse (mirrors how the rest of the box reads boolean flags:
    '1' / 'true' / 'yes' / 'on', case-insensitive). Empty / unset -> False."""
    if val is None:
        return False
    return val.strip().lower() in ("1", "true", "yes", "on", "y", "t")


def is_enabled() -> bool:
    """Is the provider registry turned ON? Read at call time; default OFF.

    With this False, the registry must be fully dormant — no mount, no resolution,
    no network I/O. This is the resting-byte-identical guarantee (§10)."""
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


def _csv_env(key: str) -> List[str]:
    """Read a comma-separated env var into a clean list (empty -> [])."""
    raw = os.environ.get(key) or ""
    return [part.strip() for part in raw.split(",") if part.strip()]


def registry_config() -> dict:
    """Snapshot of the registry's runtime config, computed fresh from os.environ.

    Returns plain JSON-able values only — NEVER a secret. Safe to surface in a /health
    style diagnostic. Behavioural modules (W2+) consume these knobs; W1 only exposes them.

      * enabled                -> the master flag.
      * health_interval_s      -> default background-probe cadence (per-def override in DDL).
      * health_fail_threshold  -> consecutive fails before the circuit opens (§2f = 3).
      * health_backoff_base_s  -> circuit-open backoff base (§2f = 60 -> 120 -> 240).
      * ssrf_allow_hosts       -> optional host allowlist for HOSTED providers (empty = allow any public).
      * ssrf_block_self_hosted -> if True, the self-hosted base_url path is disabled entirely
                                  (defense-in-depth kill switch; default False = allowed but
                                  super-admin-only + SSRF-guarded, built in W2).
      * vault_backend          -> the get_secret() seam backend ('local' interim Fernet -> 'vault' later).
    """
    return {
        "enabled": is_enabled(),
        "health_interval_s": _int_env("PROVIDER_HEALTH_INTERVAL_S", 60),
        "health_fail_threshold": _int_env("PROVIDER_HEALTH_FAIL_THRESHOLD", 3),
        "health_backoff_base_s": _int_env("PROVIDER_HEALTH_BACKOFF_BASE_S", 60),
        "ssrf_allow_hosts": _csv_env("PROVIDER_SSRF_ALLOW_HOSTS"),
        "ssrf_block_self_hosted": _truthy(os.environ.get("PROVIDER_SSRF_BLOCK_SELF_HOSTED")),
        "vault_backend": (os.environ.get("VAULT_BACKEND") or "local").strip().lower(),
    }
