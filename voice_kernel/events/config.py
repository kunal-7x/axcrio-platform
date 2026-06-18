"""voice_kernel.events.config — EventBusConfig: knobs for the Redis-Streams bus.

Default OFF / safe everywhere (mirrors voice_kernel.config). The bus itself is
inert until something registers a RedisEventBus AND the LATER seam wave flips
EVENTBUS_ENABLED (default OFF -> NullEventBus -> zero behavior change). This
object only carries tunables; the enable gate lives at the emit-site (the seam),
exactly like KERNEL_OUTBOUND.

Values are the researched defaults (RESEARCH-DECISIONS.md §6/§7):
  emit_timeout_s = 0.25   emit NEVER blocks the dial loop beyond this
  block_ms       = 2000   blocking consumer read window
  maxlen         = 100_000 bounded stream (O(1) approx trim)
  min_idle_ms    = 60_000 XAUTOCLAIM reclaim threshold
  claim_count    = 50      reclaim batch size
  max_deliveries = 3       poison -> DLQ after N deliveries
"""
from __future__ import annotations

import os
from dataclasses import dataclass

_TRUE = ("1", "true", "True")

# Stream-key namespace. Per-tenant stream = f"{STREAM_PREFIX}{tenant_id}"
# (hard isolation — never a wildcard, mirrors the RLS rule). DLQ adds ":dlq".
STREAM_PREFIX = "vk:events:"
DEDUP_PREFIX = "vk:dedup:"


def _flag(name: str, default: str = "0") -> bool:
    return os.getenv(name, default) in _TRUE


@dataclass(frozen=True)
class EventBusConfig:
    enabled: bool = False              # EVENTBUS_ENABLED — master OFF default
    url: str = "redis://localhost:6379/0"
    emit_timeout_s: float = 0.25       # emit() hard deadline (never block the call)
    block_ms: int = 2000               # consumer BLOCK read window
    maxlen: int = 100_000              # bounded stream (approx trim)
    min_idle_ms: int = 60_000          # XAUTOCLAIM idle threshold
    claim_count: int = 50              # reclaim batch
    max_deliveries: int = 3            # -> DLQ after this many deliveries
    dedup_ttl_s: int = 86_400          # consumer-side dedup key TTL (24h)

    @classmethod
    def from_env(cls) -> "EventBusConfig":
        return cls(
            enabled=_flag("EVENTBUS_ENABLED"),
            url=os.getenv("EVENTBUS_REDIS_URL", os.getenv("REDIS_URL", "redis://localhost:6379/0")),
            emit_timeout_s=float(os.getenv("EVENTBUS_EMIT_TIMEOUT_S", "0.25")),
            block_ms=int(os.getenv("EVENTBUS_BLOCK_MS", "2000")),
            maxlen=int(os.getenv("EVENTBUS_MAXLEN", "100000")),
            min_idle_ms=int(os.getenv("EVENTBUS_MIN_IDLE_MS", "60000")),
            claim_count=int(os.getenv("EVENTBUS_CLAIM_COUNT", "50")),
            max_deliveries=int(os.getenv("EVENTBUS_MAX_DELIVERIES", "3")),
            dedup_ttl_s=int(os.getenv("EVENTBUS_DEDUP_TTL_S", "86400")),
        )

    def stream_for(self, tenant_id: str) -> str:
        """Per-tenant stream key. Fail-closed: an empty tenant_id is refused (we
        must NEVER write to a wildcard/shared key — that is the RLS rule)."""
        t = (tenant_id or "").strip()
        if not t:
            raise ValueError("EventBusConfig.stream_for: empty tenant_id (fail-closed, no shared stream)")
        return f"{STREAM_PREFIX}{t}"

    def dlq_for(self, tenant_id: str) -> str:
        return self.stream_for(tenant_id) + ":dlq"

    def dedup_key(self, tenant_id: str, group: str, iid: str) -> str:
        return f"{DEDUP_PREFIX}{tenant_id}:{group}:{iid}"
