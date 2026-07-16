"""ai_manager.recorder — call-audio recording seam for the AI-Manager voice plane (spec §F).

DORMANT-BY-DEFAULT. With no recording env (`AIM_RECORDING_ENABLED` off / `AIM_SPACES_*`
absent) and/or no `livekit` / `boto3` on the box, every surface degrades cleanly:
  * build_recorder()      -> NullRecorder (no-op start/stop/pause/resume)
  * finalize(egress_id)   -> {complete:False, key:"", duration_s:0, status:"disabled"}
  * presign(bucket, key)  -> ""  (panel shows "recorded, link unavailable")

Two recorders:
  * NullRecorder           — the default; every op is a no-op so the agent path is
                             byte-identical to pre-recording.
  * LiveKitEgressRecorder  — server-side LiveKit room-composite egress (audio-only OGG ->
                             DO Spaces via S3Upload), lazy `livekit.api`; armed ONLY when
                             config.recording_active(). Egress UPLOADS to Spaces directly,
                             so the recorder itself needs no boto3 for the write side.

The READ side (presign-on-detail in endpoints, finalize-on-read in caller.py) reconciles the
terminal egress state via lazy `livekit.api` ListEgress and mints presigned playback URLs via
lazy `boto3` — both fully optional. NOTHING here imports a heavy dep at module load, does any
I/O at import, or raises out of a public function. Secrets (Spaces key/secret) are read but
NEVER logged or returned.

Mirrors AIM_CALL_LOGGING_STATE.md (LiveKitEgressRecorder design): RoomComposite audio-only
OGG -> S3Upload; finalize() via ListEgress; presign() for read.
"""
from __future__ import annotations

import logging
from typing import Optional

log = logging.getLogger("ai_manager.recorder")


# --------------------------------------------------------------------------- #
# lazy config (sibling module; import NEVER raises even if config is half-built)
# --------------------------------------------------------------------------- #
def _config():
    """Lazy-import the package config. Returns the module or None (never raises)."""
    try:
        from . import config as _cfg
        return _cfg
    except Exception:  # noqa: BLE001
        return None


def _recording_active() -> bool:
    """True only when AIM_RECORDING_ENABLED is truthy AND all AIM_SPACES_* are set.
    Read at call time via config; absent/broken config -> dormant (False)."""
    cfg = _config()
    if cfg is None:
        return False
    try:
        return bool(cfg.recording_active())
    except Exception:  # noqa: BLE001
        return False


def _spaces_creds() -> dict:
    """{bucket, region, endpoint, key, secret} from config; {} when unavailable."""
    cfg = _config()
    if cfg is None:
        return {}
    try:
        creds = cfg.spaces_creds()
        return creds if isinstance(creds, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def _lk_conn() -> dict:
    """LiveKit connection params for the egress ListEgress reconcile. Read at call time from
    the platform LIVEKIT_* env (the box's canonical names). Empty url -> caller treats as
    dormant. Never raises."""
    import os
    return {
        "url": (os.environ.get("LIVEKIT_URL", "") or "").strip(),
        "api_key": (os.environ.get("LIVEKIT_API_KEY", "") or "").strip(),
        "api_secret": (os.environ.get("LIVEKIT_API_SECRET", "") or "").strip(),
    }


# --------------------------------------------------------------------------- #
# recorders
# --------------------------------------------------------------------------- #
class NullRecorder:
    """The default recorder: every operation is a no-op. Returned by build_recorder() unless
    recording is fully configured. Safe to start/stop/pause/resume in any order; the agent
    path stays byte-identical to pre-recording."""

    active = False

    def start(self, room_name: str = "", session_id: str = "", *args, **kwargs) -> str:
        return ""

    def stop(self, *args, **kwargs) -> dict:
        return {"complete": False, "key": "", "duration_s": 0, "status": "disabled",
                "egress_id": "", "bucket": ""}

    def pause(self, *args, **kwargs) -> None:
        return None

    def resume(self, *args, **kwargs) -> None:
        return None


class LiveKitEgressRecorder:
    """Server-side LiveKit room-composite egress -> DO Spaces (audio-only OGG via S3Upload).

    DORMANT unless config.recording_active(). `start()` kicks off the egress and returns the
    egress id; `stop()` reconciles the terminal state via finalize(). All heavy deps
    (`livekit.api`) are imported LAZILY inside the methods, each guarded so an absent livekit
    or any RPC error degrades to a Null-equivalent result instead of raising. The egress
    uploads to Spaces directly, so the WRITE side needs no boto3."""

    active = True

    def __init__(self) -> None:
        self._egress_id: str = ""
        self._bucket: str = ""
        self._key: str = ""

    # -- write side (voice agent start/stop). Never raises. --
    def start(self, room_name: str = "", session_id: str = "", *args, **kwargs) -> str:
        """Begin a room-composite audio-only egress -> Spaces. Returns the egress id, or ""
        when dormant / livekit absent / any RPC error (call proceeds unrecorded)."""
        if not _recording_active():
            return ""
        room = (room_name or "").strip()
        if not room:
            return ""
        creds = _spaces_creds()
        bucket = (creds.get("bucket") or "").strip()
        if not bucket:
            return ""
        key = self._build_key(session_id or room)
        try:
            import asyncio

            from livekit import api  # type: ignore

            async def _run() -> str:
                conn = _lk_conn()
                lk = api.LiveKitAPI(url=conn["url"], api_key=conn["api_key"],
                                    api_secret=conn["api_secret"])
                try:
                    file_out = api.EncodedFileOutput(
                        file_type=api.EncodedFileType.OGG,
                        filepath=key,
                        s3=api.S3Upload(
                            access_key=(creds.get("key") or ""),
                            secret=(creds.get("secret") or ""),
                            bucket=bucket,
                            region=(creds.get("region") or "us-east-1"),
                            endpoint=(creds.get("endpoint") or ""),
                            force_path_style=True,
                        ),
                    )
                    req = api.RoomCompositeEgressRequest(
                        room_name=room, audio_only=True, file_outputs=[file_out])
                    info = await lk.egress.start_room_composite_egress(req)
                    return (getattr(info, "egress_id", "") or "")
                finally:
                    try:
                        await lk.aclose()
                    except Exception:  # noqa: BLE001
                        pass

            egress_id = _run_sync(_run)
        except Exception as exc:  # noqa: BLE001
            log.warning("ai-manager egress start failed (call unrecorded): %r", exc)
            return ""
        self._egress_id = egress_id or ""
        self._bucket = bucket
        self._key = key
        return self._egress_id

    def stop(self, *args, **kwargs) -> dict:
        """Stop + reconcile the terminal state of the running egress. Best-effort:
        returns the finalize() dict augmented with this recorder's egress_id/bucket."""
        if not self._egress_id:
            return {"complete": False, "key": self._key, "duration_s": 0,
                    "status": "disabled", "egress_id": "", "bucket": self._bucket}
        out = finalize(self._egress_id)
        out["egress_id"] = self._egress_id
        out["bucket"] = self._bucket
        if not out.get("key"):
            out["key"] = self._key
        return out

    def pause(self, *args, **kwargs) -> None:
        return None

    def resume(self, *args, **kwargs) -> None:
        return None

    @staticmethod
    def _build_key(session_id: str) -> str:
        """Spaces object key for this session's recording (audio-only OGG)."""
        sid = (session_id or "").strip() or "session"
        return f"ai-manager/recordings/{sid}.ogg"


def build_recorder():
    """Return the active recorder: LiveKitEgressRecorder when recording is fully configured,
    else NullRecorder (the dormant default). Never raises."""
    try:
        if _recording_active():
            return LiveKitEgressRecorder()
    except Exception:  # noqa: BLE001
        pass
    return NullRecorder()


# --------------------------------------------------------------------------- #
# read side: finalize-on-read (caller.py) + presign (endpoints)
# --------------------------------------------------------------------------- #
def finalize(egress_id: str) -> dict:
    """Reconcile the authoritative terminal recording state for `egress_id` via LiveKit
    ListEgress. Single positional `egress_id` (NOT a session id / bucket / key).

    Returns `{complete: bool, key: str, duration_s: int, status: str}`:
      * complete   -> the egress reached EGRESS_COMPLETE (a playable object exists).
      * key        -> the Spaces object key of the uploaded file ("" if not yet known).
      * duration_s -> recording duration in whole seconds (0 if unknown).
      * status     -> "uploaded" (complete), "failed"/"aborted", "recording" (in progress),
                      or "disabled" when recording is dormant / livekit is absent / not found.

    Dormant (recording off), livekit absent, no egress_id, or ANY RPC error ->
    `{complete:False, key:"", duration_s:0, status:"disabled"}`. NEVER raises."""
    disabled = {"complete": False, "key": "", "duration_s": 0, "status": "disabled"}
    egress_id = (egress_id or "").strip()
    if not egress_id:
        return disabled
    if not _recording_active():
        return disabled
    conn = _lk_conn()
    if not conn["url"] or not conn["api_key"] or not conn["api_secret"]:
        return disabled
    try:
        import asyncio  # noqa: F401  (drives the async LiveKit client)

        from livekit import api  # type: ignore

        async def _run() -> Optional[object]:
            lk = api.LiveKitAPI(url=conn["url"], api_key=conn["api_key"],
                                api_secret=conn["api_secret"])
            try:
                req = api.ListEgressRequest(egress_id=egress_id)
                res = await lk.egress.list_egress(req)
                items = getattr(res, "items", None) or []
                return items[0] if items else None
            finally:
                try:
                    await lk.aclose()
                except Exception:  # noqa: BLE001
                    pass

        info = _run_sync(_run)
    except Exception as exc:  # noqa: BLE001
        log.warning("ai-manager finalize(%s) ListEgress failed: %r", egress_id, exc)
        return disabled
    if info is None:
        return disabled
    return _interpret_egress(info)


def _interpret_egress(info: object) -> dict:
    """Map a livekit EgressInfo onto the {complete,key,duration_s,status} contract. Tolerant
    of enum-vs-int status and the file-result shape across livekit.api versions. Never raises."""
    try:
        status_raw = getattr(info, "status", None)
        status_name = ""
        try:
            status_name = str(getattr(status_raw, "name", "") or "")
        except Exception:  # noqa: BLE001
            status_name = ""
        if not status_name:
            status_name = str(status_raw if status_raw is not None else "")
        sname = status_name.upper()

        # locate the file result (first file output) for key + duration
        key = ""
        duration_ns = 0
        file_results = getattr(info, "file_results", None) or []
        if not file_results:
            # older shape: a single .file
            single = getattr(info, "file", None)
            if single is not None:
                file_results = [single]
        if file_results:
            f0 = file_results[0]
            key = (getattr(f0, "filename", "") or getattr(f0, "location", "") or "")
            try:
                duration_ns = int(getattr(f0, "duration", 0) or 0)
            except Exception:  # noqa: BLE001
                duration_ns = 0
        duration_s = int(duration_ns // 1_000_000_000) if duration_ns else 0

        if "COMPLETE" in sname:
            return {"complete": True, "key": key, "duration_s": duration_s,
                    "status": "uploaded"}
        if "FAILED" in sname or "ABORTED" in sname:
            return {"complete": False, "key": key, "duration_s": duration_s,
                    "status": "failed"}
        # ACTIVE / STARTING / ENDING — still in progress
        return {"complete": False, "key": key, "duration_s": duration_s,
                "status": "recording"}
    except Exception:  # noqa: BLE001
        return {"complete": False, "key": "", "duration_s": 0, "status": "disabled"}


def presign(bucket: str, key: str, *, expires_s: int = 3600) -> str:
    """Mint a short-lived presigned GET URL for a Spaces object via lazy boto3 (read side).
    Returns "" on ANY absence/error (boto3 missing, no creds, blank bucket/key) so the panel
    degrades to "recorded, link unavailable" instead of a broken player. NEVER raises.

    Creds come from config.spaces_creds() (AIM_SPACES_*). The secret is used to sign but is
    NEVER logged or returned."""
    bucket = (bucket or "").strip()
    key = (key or "").strip()
    if not bucket or not key:
        return ""
    creds = _spaces_creds()
    s3key = (creds.get("key") or "").strip()
    s3secret = (creds.get("secret") or "").strip()
    endpoint = (creds.get("endpoint") or "").strip()
    region = (creds.get("region") or "us-east-1").strip()
    if not s3key or not s3secret or not endpoint:
        return ""
    try:
        exp = int(expires_s)
    except Exception:  # noqa: BLE001
        exp = 3600
    if exp <= 0:
        exp = 3600
    try:
        import boto3  # type: ignore
        from botocore.config import Config as _BotoConfig  # type: ignore

        client = boto3.client(
            "s3",
            region_name=region,
            endpoint_url=endpoint,
            aws_access_key_id=s3key,
            aws_secret_access_key=s3secret,
            config=_BotoConfig(signature_version="s3v4", s3={"addressing_style": "path"}),
        )
        return client.generate_presigned_url(
            "get_object", Params={"Bucket": bucket, "Key": key}, ExpiresIn=exp) or ""
    except Exception as exc:  # noqa: BLE001
        log.warning("ai-manager presign failed (boto3/creds absent or error): %r", exc)
        return ""


# --------------------------------------------------------------------------- #
# sync<-async bridge (LiveKit's api client is asyncio-only)
# --------------------------------------------------------------------------- #
def _run_sync(coro_factory):
    """Run an async coroutine-factory to completion from a SYNC caller and return its result.

    finalize()/start() are called from sync contexts (caller.py's _inbound_rec_items, the
    voice agent's sync finally-block). We spin a dedicated event loop on a worker thread when
    a loop is already running in THIS thread (so we never re-enter a live loop), otherwise we
    drive a fresh loop inline. Best-effort: any failure propagates to the caller's guard."""
    import asyncio

    try:
        running = asyncio.get_running_loop()
    except RuntimeError:
        running = None

    if running is None:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro_factory())
        finally:
            try:
                loop.close()
            except Exception:  # noqa: BLE001
                pass

    # a loop is already running on this thread: drive the coroutine on a worker thread.
    import threading

    box: dict = {}

    def _worker() -> None:
        loop = asyncio.new_event_loop()
        try:
            box["result"] = loop.run_until_complete(coro_factory())
        except Exception as exc:  # noqa: BLE001
            box["error"] = exc
        finally:
            try:
                loop.close()
            except Exception:  # noqa: BLE001
                pass

    th = threading.Thread(target=_worker, daemon=True)
    th.start()
    th.join()
    if "error" in box:
        raise box["error"]
    return box.get("result")
