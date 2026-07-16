"""voice_ops.research.live — one bundled, defensive handle for the IN-CALL research loop.

So the live agent wiring is exactly TWO guarded lines (not a risky multi-edit of the 2000-line agent):

    # after ctx.connect():
    _research = live.maybe_start(ctx.room, tenant_id=tid, call_id=cid, llm=_affect_llm)   # None if flags off
    ...
    # at the END of on_user_turn_completed (inside its existing try), with a thread-safe TTS apply:
    if _research:
        _research.on_turn(txt, apply_prosody=_threadsafe_prosody_apply)

This handle owns: the parallel PCM tap (learned arousal, separate process), a LIGHTWEIGHT live
AffectTracker (the same multimodal filter, microseconds/turn), and the adaptive-TTS controller. It runs
entirely off the response path except the optional `apply_prosody(speed, stability)` callback, which the
agent routes through the SAME thread-safe, cache-safe update_options pattern proven for language
switching — and which is gated by FAMIT_RESEARCH_ADAPTIVE_TTS (default OFF). With both flags off,
maybe_start returns None and the agent is byte-identical to today.

Everything is best-effort; on_turn NEVER raises into the agent.
"""
from __future__ import annotations

import logging
from typing import Callable, Optional

from .adaptive_tts import AdaptiveTtsController, enabled as tts_enabled
from .affect_filter import AffectConfig, AffectTracker
from .agent_tap import ResearchAudioTap
from .llm_affect import llm_affect_for_turn
from .realtime import enabled as tap_enabled

logger = logging.getLogger("research.live")


class LiveResearchSession:
    def __init__(self, tenant_id: str, call_id: str, *, llm: Optional[Callable[[str], str]] = None) -> None:
        self.tenant_id = tenant_id
        self.call_id = call_id
        self.llm = llm
        self.tap: Optional[ResearchAudioTap] = None
        self.tracker = AffectTracker(AffectConfig())
        self.tts = AdaptiveTtsController()
        self.turn = 0
        self._ctx: list = []
        self.last_state = None

    def start(self, room) -> bool:
        if tap_enabled():
            try:
                t = ResearchAudioTap()
                self.tap = t if t.start(room) else None
            except Exception as exc:  # noqa: BLE001
                logger.warning("live tap start failed: %r", exc)
                self.tap = None
        return True

    def on_turn(self, transcript: str, *, apply_prosody: Optional[Callable[[float, float], None]] = None):
        """Run one live research turn: tap→arousal, LLM/heuristic→friction, filter→state, adaptive TTS.
        Returns the AffectState (for telemetry) or None. Never raises into the agent."""
        try:
            self.turn += 1
            feats = {}
            if self.tap is not None:
                info = self.tap.on_user_turn(self.call_id, self.turn) or {}
                if info.get("ssl_arousal") is not None:
                    feats["ssl_arousal"] = info["ssl_arousal"]
                    feats["ssl_conf"] = info.get("ssl_conf", 0.8)
            la = llm_affect_for_turn(transcript or "", context="\n".join(self._ctx), llm=self.llm)
            feats["llm_friction_z"] = la["llm_friction_z"]
            feats["llm_conf"] = la["llm_conf"]
            state = self.tracker.update(feats)
            self.last_state = state
            if tts_enabled():
                self.tts.step(state, apply_fn=apply_prosody)
            self._ctx.append(f"customer: {(transcript or '')[:120]}")
            self._ctx = self._ctx[-4:]
            return state
        except Exception as exc:  # noqa: BLE001
            logger.warning("live on_turn failed (no-op): %r", exc)
            return self.last_state

    def stop(self) -> None:
        try:
            if self.tap is not None:
                self.tap.stop()
        except Exception:  # noqa: BLE001
            pass


def maybe_start(room, *, tenant_id: str, call_id: str, llm: Optional[Callable[[str], str]] = None
                ) -> Optional[LiveResearchSession]:
    """Returns a live session only if SOME in-call research feature is enabled; else None (zero
    overhead, agent unchanged). Never raises."""
    if not (tap_enabled() or tts_enabled()):
        return None
    try:
        s = LiveResearchSession(tenant_id, call_id, llm=llm)
        s.start(room)
        return s
    except Exception as exc:  # noqa: BLE001
        logger.warning("live maybe_start failed: %r", exc)
        return None
