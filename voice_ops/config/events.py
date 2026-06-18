"""voice_ops.config.events — fire-and-forget config-changed emission over the W8 EventBus.

Every config WRITE (vendor profile, provider keys, retention) emits ONE `config_changed` event on
the tenant's stream so push-based consumers (dashboards, AI-Manager, other workers) refresh
INSTANTLY instead of polling. This is the "suspenders" to the store's version-poll "belt".

The emit is ALWAYS fire-and-forget + fail-soft: a missing/slow/dead bus must NEVER break a config
write (the founder must be able to save a setting even if Redis is down — the version bump already
persisted, push is best-effort, poll still catches it). Mirrors the EventBus.emit contract (LEARNINGS
§4: an event must never be the thing that breaks the system).

An EventBus is INJECTED by the caller (the seam wires the real RedisEventBus; tests inject
InMemoryEventBus; default is no bus = silent no-op, i.e. NullEventBus behavior). Importing this
module pulls ZERO redis and ZERO droplet code.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

log = logging.getLogger("voice_ops.config.events")

# the process-wide bus the config layer publishes on. None => no-op (poll still works).
_bus = None


def set_event_bus(bus) -> None:
    """Wire the EventBus the config layer emits on (RedisEventBus in prod, InMemoryEventBus in tests,
    None to disable push). Structural: any object with an async `emit(Event)`."""
    global _bus
    _bus = bus


def get_event_bus():
    return _bus


def _emit(event) -> None:
    """Schedule a fire-and-forget emit. Never raises, never blocks the writer. If we're inside a
    running event loop we schedule a task; otherwise we run it to completion on a throwaway loop
    (so a synchronous worker/scheduler write still pushes). A failure is logged, never propagated."""
    bus = _bus
    if bus is None:
        return
    try:
        coro = bus.emit(event)
    except Exception as exc:  # noqa: BLE001  (a sync raise from a bad bus impl)
        log.warning("config event emit setup failed (non-fatal): %r", exc)
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop is not None:
        # inside an async context (worker/agent) — schedule + swallow result.
        task = loop.create_task(_guard(coro))
        # prevent "task was never retrieved" noise; we deliberately don't await.
        task.add_done_callback(lambda t: t.exception() if not t.cancelled() else None)
        return
    # synchronous context (a cron/scheduler script) — run to completion, time-boxed by the bus.
    try:
        asyncio.run(_guard(coro))
    except Exception as exc:  # noqa: BLE001
        log.warning("config event emit failed (non-fatal): %r", exc)


async def _guard(coro) -> None:
    try:
        await coro
    except Exception as exc:  # noqa: BLE001
        log.warning("config event emit failed (non-fatal): %r", exc)


# --------------------------------------------------------------------------- #
# typed emitters — thin wrappers over the W8 taxonomy factories.
# --------------------------------------------------------------------------- #
def emit_config_changed(tenant_id: str, namespace: str, version: Optional[int], updated_by: str = "") -> None:
    from voice_kernel.events import config_changed
    _emit(config_changed(tenant_id, namespace=namespace, version=version, updated_by=updated_by))


def emit_provider_key_added(tenant_id: str, provider: str, fingerprint: str) -> None:
    from voice_kernel.events import provider_key_added
    _emit(provider_key_added(tenant_id, provider=provider, fingerprint=fingerprint))


def emit_provider_key_revoked(tenant_id: str, provider: str, fingerprint: str) -> None:
    from voice_kernel.events import provider_key_revoked
    _emit(provider_key_revoked(tenant_id, provider=provider, fingerprint=fingerprint))


def emit_key_pool_exhausted(tenant_id: str, provider: str) -> None:
    from voice_kernel.events import key_pool_exhausted
    _emit(key_pool_exhausted(tenant_id, provider=provider))
