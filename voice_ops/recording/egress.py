"""voice_ops.recording.egress — a thin, LAZY wrapper over the LiveKit Egress API.

This WRAPS (never edits / never imports) the live egress that caller.py +
ai_manager/recorder.py already start. It exposes exactly two reads the finalize
poller needs:

  - list_egress_for_room(room)  -> [EgressView, ...]   (outbound auto-egress: no
                                   egress_id is returned at room-create, so we
                                   filter by room_name — the proven outbound gap)
  - finalize_one(egress_id)     -> EgressView           (inbound: egress_id known)

An EgressView is a SMALL frozen dataclass (status enum -> our string, real file
duration/size/key) so no LiveKit type ever leaks out of this module — the poller,
pipeline, and tests deal in plain values. This is the same status mapping
ai_manager/recorder.finalize() already proved correct, lifted into the tracked
package and made injectable for tests (the `client` arg / `_run` indirection).

LiveKit EgressStatus enum (canonical):
  0 STARTING, 1 ACTIVE, 2 ENDING, 3 COMPLETE, 4 FAILED, 5 ABORTED, 6 LIMIT_REACHED
Egress file `duration` is reported in NANOSECONDS.

IMPORT ISOLATION: `from livekit import api` is LAZY, inside the async worker. A
host without the livekit SDK (CI) gets an empty result, never an ImportError at
load. Tests inject a fake client via `EgressClient(client=fake)` and never touch
the SDK at all.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any, List, Optional

log = logging.getLogger("voice_ops.recording.egress")

# EgressStatus enum -> our coarse recording_status string.
_STATUS_COMPLETE = 3
_STATUS_FAILED = (4, 5)  # FAILED / ABORTED
# everything else (0,1,2,6) is still in-flight


@dataclass(frozen=True)
class EgressView:
    """The droplet-free projection of one LiveKit EgressInfo."""

    egress_id: str = ""
    room_name: str = ""
    status_code: int = -1
    recording_status: str = "recording"   # recording | completed | failed
    duration_s: int = 0
    size: int = 0
    key: str = ""

    @property
    def complete(self) -> bool:
        """COMPLETE means EGRESS_COMPLETE *and* a non-empty file landed — a
        complete egress with a zero-byte file is NOT a playable recording."""
        return self.status_code == _STATUS_COMPLETE and (self.size > 0 or self.duration_s > 0)


def _project(item: Any) -> EgressView:
    """Map a LiveKit EgressInfo (or a fake with the same attrs) to an EgressView.
    Tolerant of missing attrs — a partial item degrades to 'recording', never
    raises."""
    try:
        st = int(getattr(item, "status", -1) or -1)
    except Exception:  # noqa: BLE001
        st = -1
    files = list(getattr(item, "file_results", None) or [])
    f = files[0] if files else None
    dur_ns = int(getattr(f, "duration", 0) or 0) if f is not None else 0
    duration_s = int(dur_ns / 1_000_000_000) if dur_ns > 0 else 0
    size = int(getattr(f, "size", 0) or 0) if f is not None else 0
    key = (getattr(f, "filename", "") or "") if f is not None else ""
    if st == _STATUS_COMPLETE:
        rstatus = "completed"
    elif st in _STATUS_FAILED:
        rstatus = "failed"
    else:
        rstatus = "recording"
    return EgressView(
        egress_id=str(getattr(item, "egress_id", "") or ""),
        room_name=str(getattr(item, "room_name", "") or ""),
        status_code=st,
        recording_status=rstatus,
        duration_s=duration_s,
        size=size,
        key=key,
    )


class EgressClient:
    """Reads LiveKit egress state. Inject `client` in tests (anything with an
    async `egress.list_egress(req)` returning `.items`); in production a real
    livekit.api.LiveKitAPI is built lazily per call from the box LIVEKIT_* env."""

    def __init__(self, client: Any = None):
        self._client = client  # test-injected fake or None (build a real one lazily)

    async def _list(self, *, egress_id: str = "", room_name: str = "") -> List[EgressView]:
        """Async list. Uses the injected client if present; otherwise builds a
        real LiveKitAPI lazily. NEVER raises — returns [] on any error/absence."""
        if self._client is not None:
            return await self._list_with(self._client, egress_id=egress_id, room_name=room_name)
        try:
            from livekit import api  # LAZY — no SDK import at module load
        except Exception as exc:  # noqa: BLE001
            log.info("livekit SDK absent -> empty egress list: %r", exc)
            return []
        lkapi = api.LiveKitAPI(
            url=os.environ.get("LIVEKIT_URL", ""),
            api_key=os.environ.get("LIVEKIT_API_KEY", ""),
            api_secret=os.environ.get("LIVEKIT_API_SECRET", ""),
        )
        try:
            return await self._list_with(lkapi, egress_id=egress_id, room_name=room_name, _api=api)
        finally:
            try:
                await lkapi.aclose()
            except Exception:  # noqa: BLE001
                pass

    async def _list_with(self, client: Any, *, egress_id: str = "", room_name: str = "", _api: Any = None) -> List[EgressView]:
        try:
            if _api is not None:
                req = _api.ListEgressRequest(egress_id=egress_id) if egress_id else _api.ListEgressRequest(room_name=room_name)
            else:
                # Fake client path: pass a plain dict the fake can read.
                req = {"egress_id": egress_id, "room_name": room_name}
            resp = await client.egress.list_egress(req)
            items = list(getattr(resp, "items", None) or [])
            return [_project(it) for it in items]
        except Exception as exc:  # noqa: BLE001
            log.info("list_egress failed (egress_id=%s room=%s): %r", egress_id, room_name, exc)
            return []

    # ------------------------------------------------------------ reads #
    async def list_egress_for_room(self, room_name: str) -> List[EgressView]:
        """Outbound auto-egress has NO egress_id at room-create, so we filter by
        room. Returns all egresses for the room (usually one)."""
        if not (room_name or "").strip():
            return []
        return await self._list(room_name=room_name)

    async def finalize_one(self, egress_id: str) -> Optional[EgressView]:
        """Inbound path: the egress_id is known (recorder.start returned it).
        Returns the single EgressView, or None if not found."""
        if not (egress_id or "").strip():
            return None
        views = await self._list(egress_id=egress_id)
        return views[0] if views else None
