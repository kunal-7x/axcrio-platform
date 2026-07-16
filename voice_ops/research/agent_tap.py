"""voice_ops.research.agent_tap — the LiveKit audio tap that feeds the realtime arousal worker.

The ONLY live-agent-touching piece, and it is built to be invisible when off and harmless when on:
  * Gated by FAMIT_RESEARCH_REALTIME (default OFF → maybe_start returns None, nothing is spawned).
  * Opens a SECOND, independent rtc.AudioStream on the caller's mic track (LiveKit's FFI decodes the
    Opus once and fans int16 PCM to both consumers, so the agent's own STT stream is untouched).
  * The consume loop only copies frames into a small ring buffer (<1 ms); the GIL-heavy inference runs
    in RealtimeAffectWorker's separate PROCESS — never on the agent event loop.
  * Everything is try/except wrapped: a failure (incl. the python-sdks #690 SIP-silence regression,
    where a 2nd AudioStream on a transcoded SIP track can return zero PCM) logs and no-ops; the call
    proceeds exactly as today. Validate on a real Vobiz call (scripts/validate_research_tap) before trust.

Agent integration is two guarded lines (see README): after connect → `tap = maybe_start(room)`; in
`on_user_turn_completed` → `info = tap.on_user_turn(call_id, turn_num)` and attach `info["ssl_arousal"]`.
"""
from __future__ import annotations

import logging
from collections import deque
from typing import Optional

from .realtime import RealtimeAffectWorker, enabled

logger = logging.getLogger("research.agent_tap")


class ResearchAudioTap:
    def __init__(self, sample_rate: int = 16000, window_s: float = 2.0, ring_s: float = 4.0) -> None:
        self.sr = sample_rate
        self.window_n = int(sample_rate * window_s)
        self.ring_n = int(sample_rate * ring_s)
        self._ring = deque(maxlen=self.ring_n)        # float32 samples (ring buffer of recent audio)
        self._worker = RealtimeAffectWorker()
        self._task = None
        self._stream = None
        self._last = None                             # latest (arousal, conf, source)
        self._silent_frames = 0
        self._got_audio = False

    # -- lifecycle ----------------------------------------------------------- #
    def start(self, room) -> bool:
        try:
            import asyncio
            if not self._worker.start():
                return False
            self._task = asyncio.create_task(self._run(room))
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning("research tap start failed: %r", exc)
            return False

    async def _run(self, room) -> None:
        try:
            from livekit import rtc  # lazy: the tap is the only place rtc is needed
            track = await self._resolve_caller_track(room, rtc)
            if track is None:
                logger.info("research tap: no caller mic track; tap idle")
                return
            self._stream = rtc.AudioStream(track, sample_rate=self.sr, num_channels=1)
            import numpy as np
            async for ev in self._stream:
                try:
                    frame = ev.frame
                    samples = np.frombuffer(frame.data, dtype=np.int16).astype(np.float32) / 32768.0
                    if samples.size:
                        self._ring.extend(samples.tolist())
                        self._got_audio = self._got_audio or bool(np.any(np.abs(samples) > 1e-3))
                except Exception:  # noqa: BLE001
                    continue
        except Exception as exc:  # noqa: BLE001 — SIP #690 / API drift / teardown: log + no-op
            logger.warning("research tap loop ended: %r", exc)

    async def _resolve_caller_track(self, room, rtc, timeout_s: float = 8.0):
        """Find the remote participant's microphone audio track, waiting briefly for subscription."""
        import asyncio
        deadline = timeout_s
        while deadline > 0:
            try:
                for p in list(getattr(room, "remote_participants", {}).values()):
                    for pub in list(getattr(p, "track_publications", {}).values()):
                        tr = getattr(pub, "track", None)
                        if tr is not None and getattr(pub, "kind", None) == rtc.TrackKind.KIND_AUDIO:
                            return tr
            except Exception:  # noqa: BLE001
                pass
            await asyncio.sleep(0.25)
            deadline -= 0.25
        return None

    # -- called from the agent's on_user_turn_completed hook ----------------- #
    def on_user_turn(self, call_id: str, turn_num: int) -> Optional[dict]:
        """Submit the last `window_s` of caller audio for inference and return the MOST RECENT result
        (one turn of lag is fine — it lands on the next event). Non-blocking; never raises."""
        try:
            if self._ring:
                window = list(self._ring)[-self.window_n:]
                self._worker.submit(call_id, turn_num, window, self.sr)
            for (_cid, _tn, arousal, conf, source) in self._worker.poll():
                self._last = {"ssl_arousal": round(arousal, 4), "ssl_conf": round(conf, 4), "ssl_source": source}
            return self._last
        except Exception:  # noqa: BLE001
            return self._last

    def healthy(self) -> bool:
        return self._got_audio

    def stop(self) -> None:
        try:
            if self._task is not None:
                self._task.cancel()
            self._worker.stop()
        except Exception:  # noqa: BLE001
            pass


def maybe_start(room, **kw) -> Optional[ResearchAudioTap]:
    """Entry point for the agent. Returns a live tap, or None when disabled / on any failure."""
    if not enabled():
        return None
    try:
        tap = ResearchAudioTap(**kw)
        return tap if tap.start(room) else None
    except Exception as exc:  # noqa: BLE001
        logger.warning("research tap maybe_start failed: %r", exc)
        return None
