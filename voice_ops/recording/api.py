"""voice_ops.recording.api — the get-recording status CONTRACT for the panel.

This is the SHAPE the panel reads (the EXPLORE contract for
`GET /contacts/{phone}/recordings` and `GET /calls/{call_id}/recording`). The
panel's `toRecording()` normalizer and `RecordingRow` renderer already handle the
staged states; this module is the single place that BUILDS that dict from a stored
recording row + a live storage/egress check, so the seam (caller.py) just calls
`build_recording_view(...)` and returns it — no shape drift.

It does NOT own a database. The caller passes the stored row fields (whatever it
has) and this module:
  1. self-heals a stuck `recording_status` via a cheap HEAD on the deterministic
     key (the outbound-auto-egress fix — no egress_id needed),
  2. mints a presigned `recording_presigned_url` only when the object is playable,
  3. returns the exact field set the panel reads.

NEVER raises — any storage miss degrades to recording_status='recording' with no
url (panel shows 'preparing'), never a 500.

Panel-read field set (the frozen contract):
  call_id, direction, phone, started_at, duration_s, status,
  recording_status, has_recording, playable, recording_presigned_url
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from .config import RecordingConfig, object_key

log = logging.getLogger("voice_ops.recording.api")

# recording_status values the panel understands.
RECORDING = "recording"
COMPLETED = "completed"     # finalize poller terminal-good (synonym the panel treats as uploaded)
UPLOADED = "uploaded"       # legacy synonym for completed (panel renders the player on either)
PENDING = "pending"
FAILED = "failed"
DISABLED = "disabled"

_IN_PROGRESS = {RECORDING, PENDING, "uploading"}


def build_recording_view(
    *,
    call_id: str,
    tenant_id: str,
    phone: str = "",
    direction: str = "outbound",
    started_at: Optional[str] = None,
    duration_s: Optional[int] = None,
    status: str = "",                  # call-level status (calling/done/failed)
    recording_status: str = RECORDING,
    recording_key: str = "",
    cfg: Optional[RecordingConfig] = None,
    storage: Any = None,               # ObjectStorage; None -> no self-heal/presign
    presign_ttl_s: int = 3600,
) -> dict:
    """Build the panel-shaped recording view, self-healing a stuck status and
    minting a presigned url when the object is verifiably playable. NEVER raises.

    Self-heal rule (the core fix on the READ side): if the stored status is still
    'recording'/'pending' BUT a HEAD on the (deterministic) key shows a playable
    object, flip the returned status to 'completed' and attach the url — so the
    panel plays instantly even if the finalize event was missed."""
    cfg = cfg or RecordingConfig.from_env()
    rstatus = (recording_status or RECORDING).strip().lower()
    key = (recording_key or "").strip()
    if not key and rstatus != DISABLED:
        try:
            key = object_key(tenant_id, call_id, prefix=cfg.key_prefix)
        except Exception:  # noqa: BLE001
            key = ""

    playable = False
    url = ""
    if storage is not None and key and rstatus != DISABLED:
        try:
            if storage.playable(key):
                playable = True
                url = storage.presign_get(key, expires_s=presign_ttl_s) or ""
                # SELF-HEAL: a verified-playable object means completed, regardless
                # of the stale stored status.
                if rstatus in _IN_PROGRESS:
                    rstatus = COMPLETED
            elif rstatus in (COMPLETED, UPLOADED):
                # claimed done but the object isn't playable -> demote so the panel
                # shows 'preparing' rather than a player that plays silence.
                rstatus = PENDING
        except Exception as exc:  # noqa: BLE001
            log.info("build_recording_view storage check failed call=%s: %r", call_id, exc)

    has_recording = bool(key) and rstatus != DISABLED
    return {
        "call_id": call_id,
        "direction": direction,
        "phone": phone,
        "started_at": started_at,
        "duration_s": duration_s,
        "status": (status or "").lower(),
        "recording_status": rstatus,
        "has_recording": has_recording,
        "playable": playable,
        # panel toRecording() reads url|presigned_url|recording_presigned_url|recording_url
        "recording_presigned_url": url,
    }


def recordings_envelope(views: list, *, phone: str = "") -> dict:
    """Wrap a list of recording views in the list-endpoint envelope the panel reads
    for `GET /contacts/{phone}/recordings`: totals + the items array."""
    items = list(views or [])
    return {
        "phone": phone,
        "recordings": items,
        "total": len(items),
        "with_recording": sum(1 for v in items if v.get("has_recording")),
        "with_playable": sum(1 for v in items if v.get("playable")),
    }
