"""voice_ops.recording.config — RecordingConfig + the deterministic object key.

Default OFF / safe everywhere (mirrors voice_kernel.config + ai_manager.recorder).
The whole package is inert until a founder-signed seam wave flips
`RECORDING_FINALIZE_ENABLED` AND wires real R2/B2 creds — until then every entry
point degrades to a no-op (the live recording path stays exactly as today).

Flag pattern is the codebase-native one (agent.py:451 OPENER_ALREADY_SAID style):
    os.getenv("NAME", "0") in ("1","true","True","yes","on")
No new config framework.

THE FOUNDER BUG this whole package fixes: after a call the recording takes
20-60min (or never) and can't play; transcript/summary missing. Root cause is a
fire-and-forget egress finalize with no completion polling — `recording_status`
is stamped 'recording' at room-create and NEVER updated. The fix is real-time
ListEgress polling -> `recording_status=completed` + a `recording_ready` event,
staged transcript/summary events, durable object storage with a DETERMINISTIC
key, and retention/cleanup/audit.

ENV (all under the box .env; reuses the existing LIVEKIT_* the agent has):
  RECORDING_FINALIZE_ENABLED   "1" to arm the finalize poller (default OFF)
  RECORDING_POLL_INTERVAL_S    seconds between ListEgress polls   (default 10)
  RECORDING_POLL_TIMEOUT_S     give-up deadline for one poll loop (default 120)
  RECORDING_KEY_PREFIX         object-key prefix                  (default "recordings")
  RECORDING_SEGMENTED          "1" = HLS segmented near-live      (default OFF)
  RECORDING_SEGMENT_DURATION_S HLS segment length seconds         (default 4)
  RECORDING_RETENTION_DAYS     raw-recording TTL in days          (default 30)
  RECORDING_MIN_PLAYABLE_BYTES HEAD-verify floor for "playable"   (default 2048)

  -- R2 (primary / hot playback tier) --
  R2_BUCKET / R2_REGION / R2_ENDPOINT / R2_ACCESS_KEY_ID / R2_SECRET_ACCESS_KEY
  -- B2 (archive / cold tier) --
  B2_BUCKET / B2_REGION / B2_ENDPOINT / B2_ACCESS_KEY_ID / B2_SECRET_ACCESS_KEY
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Optional

_TRUE = ("1", "true", "True", "yes", "on")


def _flag(name: str, default: str = "0") -> bool:
    v = os.getenv(name, default)
    return (v or "").strip() in _TRUE


@dataclass(frozen=True)
class StorageTier:
    """One S3-compatible bucket (R2 or B2). All fields stripped; `complete` is
    True only when bucket + endpoint + key + secret are all present."""

    name: str = ""          # logical tier name ("r2" | "b2")
    bucket: str = ""
    region: str = "auto"
    endpoint: str = ""
    access_key: str = ""
    secret_key: str = ""
    force_path_style: bool = True

    @property
    def complete(self) -> bool:
        return all((self.bucket, self.endpoint, self.access_key, self.secret_key))

    @classmethod
    def from_env(cls, prefix: str, name: str) -> "StorageTier":
        g = lambda k, d="": (os.getenv(f"{prefix}_{k}") or d).strip()  # noqa: E731
        return cls(
            name=name,
            bucket=g("BUCKET"),
            region=g("REGION", "auto"),
            endpoint=g("ENDPOINT"),
            access_key=g("ACCESS_KEY_ID"),
            secret_key=g("SECRET_ACCESS_KEY"),
            force_path_style=_flag(f"{prefix}_FORCE_PATH_STYLE", "1"),
        )


@dataclass(frozen=True)
class RecordingConfig:
    """Immutable snapshot of the recording-finalize knobs. Build with
    `RecordingConfig.from_env()` in production; construct directly in tests."""

    enabled: bool = False                 # RECORDING_FINALIZE_ENABLED — master OFF default
    poll_interval_s: float = 10.0
    poll_timeout_s: float = 120.0
    key_prefix: str = "recordings"
    segmented: bool = False               # HLS near-live segmented output
    segment_duration_s: int = 4
    retention_days: int = 30
    min_playable_bytes: int = 2048
    primary: StorageTier = field(default_factory=StorageTier)   # R2 (hot)
    archive: StorageTier = field(default_factory=StorageTier)   # B2 (cold)

    @classmethod
    def from_env(cls) -> "RecordingConfig":
        return cls(
            enabled=_flag("RECORDING_FINALIZE_ENABLED"),
            poll_interval_s=float(os.getenv("RECORDING_POLL_INTERVAL_S", "10")),
            poll_timeout_s=float(os.getenv("RECORDING_POLL_TIMEOUT_S", "120")),
            key_prefix=(os.getenv("RECORDING_KEY_PREFIX") or "recordings").strip().strip("/"),
            segmented=_flag("RECORDING_SEGMENTED"),
            segment_duration_s=int(os.getenv("RECORDING_SEGMENT_DURATION_S", "4")),
            retention_days=int(os.getenv("RECORDING_RETENTION_DAYS", "30")),
            min_playable_bytes=int(os.getenv("RECORDING_MIN_PLAYABLE_BYTES", "2048")),
            primary=StorageTier.from_env("R2", "r2"),
            archive=StorageTier.from_env("B2", "b2"),
        )

    @property
    def storage_ready(self) -> bool:
        """At least the primary (R2) tier must be wired for finalize to do real
        object work. The poller can still update status from LiveKit without it,
        but playback/HEAD-verify needs the primary tier."""
        return self.primary.complete


def object_key(
    tenant_id: str,
    call_id: str,
    *,
    prefix: str = "recordings",
    ext: str = "ogg",
    ts: Optional[float] = None,
) -> str:
    """DETERMINISTIC object key — the SAME (tenant, call) always maps to the SAME
    key, so the row can store it BEFORE egress confirms and the read side can HEAD
    / presign it later with no egress_id needed (the outbound-auto-egress fix).

    Shape: <prefix>/<tenant>/<YYYY/MM/DD>/<call_id>.<ext>

    Tenant is part of the path (hard per-tenant partition, mirrors the RLS rule —
    a presign for tenant A can never address tenant B's object by guessing a key).
    Fail-closed: an empty tenant_id raises (never a shared/rootless key)."""
    t = (tenant_id or "").strip()
    if not t:
        raise ValueError("object_key: empty tenant_id (fail-closed, no shared key)")
    cid = (call_id or "").strip() or "unknown"
    # path-safe: strip slashes from the segments we control
    t_safe = t.replace("/", "_")
    cid_safe = cid.replace("/", "_")[:80]
    day = time.strftime("%Y/%m/%d", time.gmtime(ts if ts is not None else time.time()))
    pfx = (prefix or "recordings").strip("/")
    return f"{pfx}/{t_safe}/{day}/{cid_safe}.{ext}"
