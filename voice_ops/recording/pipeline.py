"""voice_ops.recording.pipeline — the STAGED post-call artifact pipeline.

The founder wants three artifacts to appear, IN ORDER, each updating the panel in
real time the moment it is ready:

    recording_ready  ->  transcript_ready  ->  summary_ready

Today these are coupled and racy: the transcript is read inline at finalize
(caller.py:2725) and is often empty because agent.py writes it on an ASYNC
shutdown callback; the summary is generated only inside that callback; and the
recording status never follows at all. The panel therefore shows nothing for
20-60 min. This module sequences the three stages explicitly and emits one typed
W8 event per stage AS IT COMPLETES, so each artifact lights up independently.

ORDERING GUARANTEE: stages run strictly in sequence — transcript is only emitted
after recording is finalized; summary only after transcript. A later stage that
has no input (e.g. an empty transcript) is SKIPPED, not failed, and never blocks
or reorders an earlier emitted event. This is what the test asserts: the events
observed on the bus for a call appear in the canonical order.

EARNER-SAFETY: NEVER raises; meant to run as a detached post-call task. The
transcript reader + summarizer are INJECTED callables (the seam binds them on the
box to the existing transcript file + the existing Groq `_summarize`), so this
module imports ZERO droplet code and is fully unit-testable with fakes.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional, Sequence

from .config import RecordingConfig
from .poller import FinalizePoller, FinalizeResult

log = logging.getLogger("voice_ops.recording.pipeline")

# Injected providers (bound on the box; faked in tests). Both may be sync OR async
# and BOTH may be None (stage skipped). Return None/empty -> stage skipped.
#   transcript provider: (tenant_id, call_id) -> {"turns": [...], "text": str} | None
#   summary provider:    (tenant_id, call_id, transcript) -> {"summary","lifecycle","conversion_prob",...} | None
TranscriptProvider = Callable[[str, str], Any]
SummaryProvider = Callable[[str, str, dict], Any]


@dataclass
class PipelineResult:
    call_id: str
    tenant_id: str
    direction: str = "outbound"
    recording: Optional[FinalizeResult] = None
    transcript_turns: int = 0
    has_transcript: bool = False
    has_summary: bool = False
    lifecycle: str = ""
    stages_emitted: list = field(default_factory=list)  # ordered event names emitted


async def _maybe_await(value: Any) -> Any:
    """Allow injected providers to be sync or async."""
    if asyncio.iscoroutine(value):
        return await value
    return value


class StagedPipeline:
    """Runs finalize -> transcript -> summary, emitting one W8 event per stage in
    order. Reuses a FinalizePoller for stage 1 (so finalize + recording_ready stay
    one code path). Stages 2 + 3 read from injected providers and emit
    transcript_ready / summary_ready."""

    def __init__(
        self,
        cfg: Optional[RecordingConfig] = None,
        *,
        bus: Any = None,
        poller: Optional[FinalizePoller] = None,
        transcript_provider: Optional[TranscriptProvider] = None,
        summary_provider: Optional[SummaryProvider] = None,
    ):
        self.cfg = cfg or RecordingConfig.from_env()
        self.bus = bus
        self.poller = poller or FinalizePoller(self.cfg, bus=bus)
        self.transcript_provider = transcript_provider
        self.summary_provider = summary_provider

    async def run(
        self,
        *,
        call_id: str,
        tenant_id: str,
        room_name: str = "",
        egress_id: str = "",
        direction: str = "outbound",
    ) -> PipelineResult:
        """Execute all three stages in order. NEVER raises. A stage with no
        input/provider is skipped; later stages still run (e.g. a summary can be
        produced even if the recording object isn't playable yet — they are
        independent artifacts that only share ORDERING, not success-dependency)."""
        res = PipelineResult(call_id=call_id, tenant_id=tenant_id, direction=direction)

        # --- STAGE 1: recording finalize (+ recording_ready) -----------------
        try:
            fin = await self.poller.finalize(
                call_id=call_id, tenant_id=tenant_id,
                room_name=room_name, egress_id=egress_id, direction=direction,
            )
            res.recording = fin
            if fin.emitted_ready:
                res.stages_emitted.append("recording_ready")
        except Exception as exc:  # noqa: BLE001
            log.warning("pipeline stage1 (finalize) failed: %r", exc)

        # --- STAGE 2: transcript (+ transcript_ready) ------------------------
        transcript: dict = {}
        try:
            transcript = await self._stage_transcript(call_id, tenant_id, direction, res)
        except Exception as exc:  # noqa: BLE001
            log.warning("pipeline stage2 (transcript) failed: %r", exc)

        # --- STAGE 3: summary (+ summary_ready) ------------------------------
        try:
            await self._stage_summary(call_id, tenant_id, direction, transcript, res)
        except Exception as exc:  # noqa: BLE001
            log.warning("pipeline stage3 (summary) failed: %r", exc)

        return res

    # ----------------------------------------------------- stage 2 #
    async def _stage_transcript(self, call_id: str, tenant_id: str, direction: str, res: PipelineResult) -> dict:
        if self.transcript_provider is None:
            return {}
        data = await _maybe_await(self.transcript_provider(tenant_id, call_id))
        if not data:
            return {}
        if not isinstance(data, dict):
            data = {"text": str(data)}
        turns = data.get("turns") or []
        n = len(turns) if isinstance(turns, (list, tuple)) else int(data.get("turns_count", 0) or 0)
        text = str(data.get("text", "") or "")
        if n == 0 and not text:
            return {}  # genuinely empty -> skip emit (no transcript yet)
        res.has_transcript = True
        res.transcript_turns = n
        await self._emit("transcript_ready", call_id, tenant_id, {"turns": n or None, "direction": direction})
        res.stages_emitted.append("transcript_ready")
        return data

    # ----------------------------------------------------- stage 3 #
    async def _stage_summary(self, call_id: str, tenant_id: str, direction: str, transcript: dict, res: PipelineResult) -> None:
        if self.summary_provider is None:
            return
        summary = await _maybe_await(self.summary_provider(tenant_id, call_id, transcript or {}))
        if not summary:
            return
        if not isinstance(summary, dict):
            summary = {"summary": str(summary)}
        text = str(summary.get("summary", "") or "")
        lifecycle = str(summary.get("lifecycle", "") or "")
        conv = summary.get("conversion_prob")
        if not text and not lifecycle:
            return  # nothing meaningful -> skip
        res.has_summary = True
        res.lifecycle = lifecycle
        await self._emit(
            "summary_ready", call_id, tenant_id,
            {"lifecycle": lifecycle or None, "conversion_prob": conv, "direction": direction},
        )
        res.stages_emitted.append("summary_ready")

    # ----------------------------------------------------- emit #
    async def _emit(self, factory_name: str, call_id: str, tenant_id: str, payload: dict) -> None:
        """Emit one staged event via the matching W8 factory. Fire-and-forget; a
        missing bus is a no-op; never raises."""
        if self.bus is None:
            return
        try:
            from voice_kernel.events import transcript_ready, summary_ready

            factory = {"transcript_ready": transcript_ready, "summary_ready": summary_ready}[factory_name]
            ev = factory(call_id=call_id, tenant_id=tenant_id, **{k: v for k, v in payload.items() if v is not None})
            await self.bus.emit(ev)
        except Exception as exc:  # noqa: BLE001
            log.warning("emit %s failed (non-fatal): %r", factory_name, exc)
