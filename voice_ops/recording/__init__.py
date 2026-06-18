"""voice_ops.recording — real-time recording finalize + staged artifacts (W9).

THE FOUNDER BUG this package fixes: after a call the recording takes 20-60 min (or
never) and can't play; transcript/summary missing. ROOT CAUSE (audited): LiveKit
egress finalize is fire-and-forget (caller.py:2715 outbound,
ai_manager/recorder.py:200 inbound) — no completion polling; `recording_status`
is stamped 'recording' at room-create and never transitions to a terminal state.

THE FIX (this package, all default-OFF + droplet-free + earner-safe):
  1. config       RecordingConfig (flags + R2/B2 creds) + the DETERMINISTIC key.
  2. storage      ObjectStorage — S3-compatible R2 (hot) + B2 (archive), HEAD-verify,
                  presign, archive-copy, usage accounting (lazy boto3).
  3. egress       EgressClient — LAZY LiveKit ListEgress wrapper -> EgressView
                  (status enum -> string, real duration/size/key). Outbound + inbound.
  4. poller       FinalizePoller — polls to EGRESS_COMPLETE, flips status to
                  'completed', emits ONE `recording_ready` (W8 EventBus) the instant
                  the object lands. The core real-time fix.
  5. pipeline     StagedPipeline — recording_ready -> transcript_ready ->
                  summary_ready, each emitted IN ORDER as its artifact is ready.
  6. retention    RetentionManager — raw-media TTL (archive R2->B2 then delete),
                  storage accounting, immutable deletion audit; NEVER deletes the
                  summary / lead intelligence.
  7. api          build_recording_view / recordings_envelope — the panel status
                  CONTRACT, self-healing a stuck status via a HEAD on the
                  deterministic key + minting a presigned url when playable.

WRAPS (never edits / never imports) the live agent.py / caller.py / the existing
LiveKit egress + ai_manager.recorder. Reuses `voice_kernel.events` (the W8 EventBus
+ recording_ready/transcript_ready/summary_ready factories). IMPORT ISOLATION:
importing this package pulls ZERO droplet_work, ZERO livekit, ZERO boto3, ZERO
redis at module load — every such import is LAZY inside a function.

The seam (where caller.py / recorder.py call into this) is documented patch-only in
design/W9-RECORDING-SEAM.md — no live file is edited by this wave.
"""
from __future__ import annotations

from .api import build_recording_view, recordings_envelope
from .config import RecordingConfig, StorageTier, object_key
from .egress import EgressClient, EgressView
from .pipeline import PipelineResult, StagedPipeline
from .poller import FinalizePoller, FinalizeResult
from .retention import (
    DeletionAuditRecord,
    RetentionCandidate,
    RetentionManager,
    RetentionReport,
)
from .storage import ObjectStorage

__all__ = [
    # config
    "RecordingConfig",
    "StorageTier",
    "object_key",
    # storage
    "ObjectStorage",
    # egress
    "EgressClient",
    "EgressView",
    # poller
    "FinalizePoller",
    "FinalizeResult",
    # pipeline
    "StagedPipeline",
    "PipelineResult",
    # retention
    "RetentionManager",
    "RetentionCandidate",
    "RetentionReport",
    "DeletionAuditRecord",
    # api
    "build_recording_view",
    "recordings_envelope",
]
