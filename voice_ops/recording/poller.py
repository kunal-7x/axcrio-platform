"""voice_ops.recording.poller — the egress-finalize POLLER (the core fix).

THE FOUNDER BUG, root cause: LiveKit egress finalize is fire-and-forget
(caller.py:2715 outbound, ai_manager/recorder.py:200 inbound). `recording_status`
is stamped 'recording' at room-create and NEVER transitions, so a recording that
actually completed in seconds shows 'recording' for 20-60 min (until some
incidental read self-heals it) — or forever. There is NO completion polling.

THE FIX (this module): after a call ends, poll LiveKit `ListEgress` on a short
interval until the egress reaches EGRESS_COMPLETE (status==3) with a real file,
then INSTANTLY:
  1. flip recording_status -> "completed",
  2. HEAD-verify the object is playable (size >= floor) and mint a presigned url,
  3. emit ONE `recording_ready` event on the W8 EventBus (tenant-scoped),
so the dashboard / CRM / panel update in real time from a single source of truth
instead of polling stale rows. On give-up (deadline) or FAILED/ABORTED egress it
records a terminal non-'recording' status WITHOUT emitting recording_ready (a
failed recording must not advertise a playable url).

WORKS FOR BOTH directions:
  - outbound (no egress_id at room-create): filter by `room_name`;
  - inbound (egress_id known): filter by egress_id.

EARNER-SAFETY: every public coroutine NEVER raises and NEVER blocks the call —
it is meant to run as a detached `asyncio.create_task` AFTER hangup (the seam doc
shows exactly where). A dead Redis drops the event (the bus already guarantees
fire-and-forget); a dead LiveKit just times out and leaves the row at the last
known status. Sleep is injectable so tests run instantly (no real waiting).
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional

from .config import RecordingConfig, object_key
from .egress import EgressClient, EgressView

log = logging.getLogger("voice_ops.recording.poller")


@dataclass
class FinalizeResult:
    """Outcome of one finalize poll loop (also the staged-pipeline seed)."""

    call_id: str
    tenant_id: str
    direction: str = "outbound"
    recording_status: str = "recording"   # recording | completed | failed | timeout
    duration_s: int = 0
    size: int = 0
    key: str = ""
    url: str = ""
    playable: bool = False
    emitted_ready: bool = False
    polls: int = 0


# A sleep coroutine factory so tests can inject a no-op (instant) sleeper.
SleepFn = Callable[[float], Awaitable[None]]


async def _real_sleep(s: float) -> None:
    await asyncio.sleep(s)


class FinalizePoller:
    """Polls egress to completion and emits recording_ready. Construct with the
    config, the W8 EventBus (any object with async `emit(Event)` — Null/InMemory/
    Redis all conform), an EgressClient (inject a fake in tests), and an
    ObjectStorage (for HEAD-verify + presign). Sleep is injectable."""

    def __init__(
        self,
        cfg: Optional[RecordingConfig] = None,
        *,
        bus: Any = None,             # voice_kernel.contracts.EventBus (emit/subscribe)
        egress: Optional[EgressClient] = None,
        storage: Any = None,         # voice_ops.recording.storage.ObjectStorage
        sleep: Optional[SleepFn] = None,
    ):
        self.cfg = cfg or RecordingConfig.from_env()
        self.bus = bus
        self.egress = egress or EgressClient()
        self.storage = storage
        self._sleep: SleepFn = sleep or _real_sleep

    # --------------------------------------------------------- one view #
    async def _poll_view(self, *, egress_id: str, room_name: str) -> Optional[EgressView]:
        """Return the most-relevant egress view for this call, or None. Prefers an
        egress_id lookup (inbound); falls back to room filter (outbound)."""
        if egress_id:
            v = await self.egress.finalize_one(egress_id)
            if v is not None:
                return v
        views = await self.egress.list_egress_for_room(room_name) if room_name else []
        if not views:
            return None
        # Pick the completed one if present, else the first.
        for v in views:
            if v.complete:
                return v
        return views[0]

    # --------------------------------------------------------- finalize #
    async def finalize(
        self,
        *,
        call_id: str,
        tenant_id: str,
        room_name: str = "",
        egress_id: str = "",
        direction: str = "outbound",
        ext: str = "ogg",
    ) -> FinalizeResult:
        """Poll until the egress completes (or the deadline), then flip status to
        'completed' + emit recording_ready. NEVER raises. Returns a FinalizeResult
        (the seed the staged pipeline consumes). `room_name` defaults to call_id
        for the outbound room convention.

        Idempotent on the wire: recording_ready carries a stable iid (the bus
        dedups a re-emit of the identical event), so re-running finalize for the
        same completed egress collapses to one event."""
        room = (room_name or call_id or "").strip()
        result = FinalizeResult(call_id=call_id, tenant_id=tenant_id, direction=direction)
        if not (tenant_id or "").strip() or not (call_id or "").strip():
            log.warning("finalize: empty tenant/call — refusing (fail-closed)")
            result.recording_status = "failed"
            return result
        try:
            view = await self._poll_loop(egress_id=egress_id, room_name=room, result=result)
        except Exception as exc:  # never raise into the post-call task
            log.warning("finalize poll loop crashed (-> timeout): %r", exc)
            view = None
        if view is None:
            result.recording_status = "timeout"
            return result

        # Terminal mapping.
        result.duration_s = view.duration_s
        result.size = view.size
        # Prefer the egress-reported file key; else our deterministic key.
        result.key = (view.key or "").strip() or self._deterministic_key(tenant_id, call_id, ext)

        if view.recording_status == "failed":
            result.recording_status = "failed"
            return result
        if not view.complete:
            result.recording_status = "timeout"
            return result

        # COMPLETE -> verify object + presign + emit.
        result.recording_status = "completed"
        await self._verify_and_present(result)
        await self._emit_ready(result)
        return result

    async def _poll_loop(self, *, egress_id: str, room_name: str, result: FinalizeResult) -> Optional[EgressView]:
        """Poll on the interval up to the timeout. Returns the FIRST view that is
        terminal (complete OR failed), or the last seen view at deadline."""
        interval = max(0.0, float(self.cfg.poll_interval_s))
        deadline = max(interval, float(self.cfg.poll_timeout_s))
        elapsed = 0.0
        last: Optional[EgressView] = None
        while True:
            result.polls += 1
            view = await self._poll_view(egress_id=egress_id, room_name=room_name)
            if view is not None:
                last = view
                if view.complete or view.recording_status == "failed":
                    return view
            if elapsed >= deadline:
                return last
            await self._sleep(interval)
            elapsed += interval if interval > 0 else deadline  # interval 0 -> single extra pass then exit

    def _deterministic_key(self, tenant_id: str, call_id: str, ext: str) -> str:
        try:
            return object_key(tenant_id, call_id, prefix=self.cfg.key_prefix, ext=ext)
        except Exception:  # noqa: BLE001
            return ""

    async def _verify_and_present(self, result: FinalizeResult) -> None:
        """HEAD-verify the object is playable and mint a presigned url. Storage is
        OPTIONAL — without it (no creds / CI) we still mark completed but leave
        playable=False/url="" so the panel shows 'preparing', never a broken
        player. Runs the blocking boto3 calls in a thread so the event loop is not
        stalled."""
        if self.storage is None or not (result.key or "").strip():
            return
        try:
            playable = await asyncio.to_thread(self.storage.playable, result.key)
            result.playable = bool(playable)
            if playable:
                result.url = await asyncio.to_thread(self.storage.presign_get, result.key)
        except Exception as exc:  # noqa: BLE001
            log.info("verify/presign failed (-> not playable): %r", exc)

    def _stable_ts(self, result: FinalizeResult) -> str:
        """A deterministic ISO timestamp derived ONLY from stable recording
        identity (key + duration), so two finalize runs for the SAME completed
        recording stamp the SAME ts and collapse to one event on the bus. Not a
        real wall-clock time — it is a dedup anchor (the daily_report trick). We
        map a stable 8-hex digest of (key|duration) onto a fixed epoch-offset
        ISO string so it parses cleanly anywhere."""
        import hashlib
        from datetime import datetime, timezone, timedelta

        seed = f"{result.key}|{result.duration_s}|{result.call_id}".encode("utf-8")
        # offset seconds in a stable, bounded range from a fixed anchor date.
        off = int(hashlib.sha1(seed).hexdigest()[:8], 16) % 1_000_000
        anchor = datetime(2020, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=off)
        return anchor.isoformat().replace("+00:00", "Z")

    async def _emit_ready(self, result: FinalizeResult) -> None:
        """Emit ONE recording_ready event (W8). Fire-and-forget by contract — the
        bus owns its own timeout and never raises; we additionally guard so a
        missing/None bus is simply a no-op. Carries url+duration+playable so the
        sink updates the row in one shot."""
        if self.bus is None:
            return
        try:
            from voice_kernel.events import recording_ready

            # IDEMPOTENCY: pin ts_iso to a STABLE, content-derived marker so the
            # SAME completed recording always produces the SAME idempotency id and
            # a re-finalize dedups on the bus (the daily_report pattern). The wall
            # clock is NOT part of the identity — "recording ready for this call's
            # object" is one logical fact, however many times finalize runs. The
            # marker is derived from the durable object key (stable per recording),
            # falling back to call_id; it deliberately EXCLUDES the volatile
            # presigned url, which re-presigns to a new string each read.
            ts_pin = self._stable_ts(result)
            # The event carries the DURABLE object key + playable flag, NOT the
            # short-lived presigned url (which re-presigns to a fresh string every
            # read and would defeat dedup). The sink mints the url on read via
            # api.build_recording_view(key) — exactly the proven inbound pattern.
            ev = recording_ready(
                call_id=result.call_id,
                tenant_id=result.tenant_id,
                url="",  # durable event: never the volatile signed url
                duration_s=result.duration_s or None,
                playable=result.playable,
                key=result.key or None,
                direction=result.direction,
                ts_iso=ts_pin,
            )
            await self.bus.emit(ev)
            result.emitted_ready = True
        except Exception as exc:  # noqa: BLE001
            log.warning("emit recording_ready failed (non-fatal): %r", exc)
