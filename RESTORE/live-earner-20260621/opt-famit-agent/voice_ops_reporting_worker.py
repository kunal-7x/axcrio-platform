#!/usr/bin/env python3
"""voice_ops_reporting_worker.py — the W14 real-time reporting consumer daemon.

Tails the per-tenant Redis streams `vk:events:{tenant_id}` (the W8 app bus) and
materializes the reporting read-model (ReportingStore) so the panel `/report*`
routes + AI-Manager serve LIVE numbers. This is a SEPARATE long-running process,
NEVER inside the voice agent (W8 RESEARCH-DECISIONS §9 / W14 §4).

Earner law: this worker imports ONLY voice_kernel.events + voice_ops.reporting.
It NEVER imports / touches agent.py / caller.py and never places a call. It is a
pure consumer + in-memory read-model.

Tenant resolution: the live `calls` table keys tenants as `org_id` (this codebase
equates org_id == the event-bus tenant_id; see caller.py run_job
`tenant_id = job.get("tenant_id", ADMIN_ID)` and the `org_id is ALWAYS
t["tenant_id"]` comment). We therefore resolve the active tenant set from
`SELECT DISTINCT org_id FROM calls` (the W14 §4 "active tenants" intent; the doc's
literal `tenant_id` column does not exist on `calls`), UNION the canonical
`tenant_status` registry, and ALWAYS include the admin/default tenant so at least
one consumer is running on a fresh box. The set is RE-RESOLVED on a timer so a
brand-new tenant's first call gets a consumer with no restart.

Config (systemd drop-in / EnvironmentFile):
  EVENTBUS_REDIS_URL   redis://127.0.0.1:6380/0   (the app bus)
  EVENTBUS_ENABLED     1                          (informational; the worker always consumes)
  REPORTING_ENABLED    1                          (gates the read-model fill)
  PG_DSN               postgresql+psycopg2://...  (tenant resolution; SQLAlchemy URL ok)
  REPORTING_DEFAULT_TENANT   admin                (fallback default tenant)
  REPORTING_TENANT_REFRESH_S 60                   (tenant re-resolution interval)
  REPORTING_RECLAIM_S        30                   (XAUTOCLAIM / DLQ janitor interval)
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import signal

from voice_kernel.events import (
    EventBusConfig,
    RedisEventBus,
    SinkConsumer,
    reclaim_and_dlq,
)
from voice_ops.reporting import (
    ReportingStore,
    ReportingConfig,
    build_consumer_handler,
)

logging.basicConfig(
    level=os.getenv("REPORTING_LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s reporting-worker %(message)s",
)
log = logging.getLogger("voice_ops_reporting_worker")

DEFAULT_TENANT = (os.getenv("REPORTING_DEFAULT_TENANT", "admin") or "admin").strip()
TENANT_REFRESH_S = int(os.getenv("REPORTING_TENANT_REFRESH_S", "60"))
RECLAIM_S = int(os.getenv("REPORTING_RECLAIM_S", "30"))


# --------------------------------------------------------------- tenants #
def _libpq_dsn(dsn: str) -> str:
    """Normalize a SQLAlchemy URL (postgresql+psycopg2://...) to a libpq URL that
    psycopg2.connect accepts. A plain postgresql:// URL passes through unchanged."""
    dsn = (dsn or "").strip()
    return re.sub(r"^postgres(ql)?\+\w+://", "postgresql://", dsn)


def resolve_active_tenants() -> set[str]:
    """Active tenant set = DISTINCT org_id from calls (the W14 'active tenants'
    intent — `calls` keys tenants by org_id, which IS the event-bus tenant_id)
    UNION the tenant_status registry, ALWAYS including the admin/default tenant.
    Never raises: on any DB error we fall back to {DEFAULT_TENANT} so a consumer
    is always running."""
    tenants: set[str] = {DEFAULT_TENANT} if DEFAULT_TENANT else set()
    dsn = _libpq_dsn(os.getenv("PG_DSN", ""))
    if not dsn:
        log.warning("PG_DSN not set; using default tenant set %s", tenants)
        return tenants
    try:
        import psycopg2  # lazy

        conn = psycopg2.connect(dsn)
        try:
            cur = conn.cursor()
            cur.execute("SELECT DISTINCT org_id FROM calls WHERE org_id IS NOT NULL")
            tenants.update((r[0] or "").strip() for r in cur.fetchall() if r[0])
            # canonical registry (richer than calls on a fresh box)
            try:
                cur.execute(
                    "SELECT DISTINCT tenant_id FROM tenant_status WHERE tenant_id IS NOT NULL"
                )
                tenants.update((r[0] or "").strip() for r in cur.fetchall() if r[0])
            except Exception:  # noqa: BLE001 — table optional
                conn.rollback()
        finally:
            conn.close()
    except Exception as exc:  # noqa: BLE001
        log.warning("tenant resolution failed (%r); using %s", exc, tenants)
    tenants.discard("")
    return tenants


# ----------------------------------------------------------- consumers #
class ConsumerSupervisor:
    """Runs one SinkConsumer + a reclaim/DLQ janitor per tenant, and spawns new
    ones as tenants appear (re-resolved on a timer). Tenants are never removed
    while running (a stream may still hold history); this is additive."""

    def __init__(self, bus: RedisEventBus, cfg: EventBusConfig, store: ReportingStore, group: str):
        self.bus = bus
        self.cfg = cfg
        self.store = store
        self.group = group
        self.handler = build_consumer_handler(store)
        self._tasks: dict[str, asyncio.Task] = {}
        self._stop = asyncio.Event()

    async def _sleep_or_stop(self, seconds: float) -> None:
        """Sleep up to `seconds`, but wake IMMEDIATELY if stop is requested, so
        SIGTERM -> systemd restart/stop is prompt (no 60s shutdown stall)."""
        try:
            await asyncio.wait_for(self._stop.wait(), timeout=seconds)
        except asyncio.TimeoutError:
            pass

    def _start_tenant(self, tenant_id: str) -> None:
        if tenant_id in self._tasks and not self._tasks[tenant_id].done():
            return
        log.info("starting consumer+janitor for tenant=%s group=%s", tenant_id, self.group)
        self._tasks[tenant_id] = asyncio.create_task(self._run_tenant(tenant_id))

    async def _run_tenant(self, tenant_id: str) -> None:
        consumer = SinkConsumer(self.bus, self.cfg, tenant_id, self.group, self.handler)
        janitor = asyncio.create_task(self._janitor(tenant_id))
        try:
            # SinkConsumer.run() blocks forever (drains PEL, then live-tails).
            # If Redis is momentarily down it raises; we restart it with backoff.
            while not self._stop.is_set():
                try:
                    await consumer.run()
                    break  # clean stop
                except asyncio.CancelledError:
                    raise
                except Exception as exc:  # noqa: BLE001
                    log.warning("consumer[%s] crashed (%r); restart in 3s", tenant_id, exc)
                    await asyncio.sleep(3)
        finally:
            janitor.cancel()
            try:
                await janitor
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass

    async def _janitor(self, tenant_id: str) -> None:
        """Every RECLAIM_S: XAUTOCLAIM crashed-peer PEL + route poison -> DLQ."""
        while not self._stop.is_set():
            try:
                await self._sleep_or_stop(RECLAIM_S)
                if self._stop.is_set():
                    break
                n = await reclaim_and_dlq(self.bus, self.cfg, tenant_id, self.group)
                if n:
                    log.info("janitor[%s] reclaimed/dlq'd %d", tenant_id, n)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                log.warning("janitor[%s] error (%r)", tenant_id, exc)

    async def run(self) -> None:
        # initial fan-out
        for t in resolve_active_tenants():
            self._start_tenant(t)
        if not self._tasks:
            log.warning("no tenants resolved; nothing to consume (will retry)")
        # periodic re-resolution: spawn consumers for newly-appeared tenants
        while not self._stop.is_set():
            try:
                await self._sleep_or_stop(TENANT_REFRESH_S)
                if self._stop.is_set():
                    break
                for t in resolve_active_tenants():
                    self._start_tenant(t)
            except asyncio.CancelledError:
                break
            except Exception as exc:  # noqa: BLE001
                log.warning("tenant refresh error (%r)", exc)

    def stop(self) -> None:
        self._stop.set()
        for task in self._tasks.values():
            task.cancel()


# ----------------------------------------------------------------- main #
async def main() -> None:
    cfg = EventBusConfig.from_env()  # EVENTBUS_REDIS_URL
    bus = RedisEventBus(cfg)
    store = ReportingStore()  # default in-memory backend (rebuilt from stream replay)
    rcfg = ReportingConfig(enabled=True)  # REPORTING_ENABLED gates the route; the read-model always fills
    log.info(
        "reporting worker up: redis=%s group=%s default_tenant=%s refresh=%ss reclaim=%ss reporting_enabled=%s",
        cfg.url,
        rcfg.consumer_group,
        DEFAULT_TENANT,
        TENANT_REFRESH_S,
        RECLAIM_S,
        rcfg.enabled,
    )
    sup = ConsumerSupervisor(bus, cfg, store, rcfg.consumer_group)

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, sup.stop)
        except NotImplementedError:  # pragma: no cover
            pass

    await sup.run()
    log.info("reporting worker shutting down")


if __name__ == "__main__":
    asyncio.run(main())
