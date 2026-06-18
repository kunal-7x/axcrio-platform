# W9 — Recording / Transcript / Summary real-time finalize (voice_ops/recording)

Branch: `fix/realtime-voice-kernel-v2`
Earner law: live agent.py md5=98655dbf — NEVER edit/import/restart. caller.py / aim_voice_agent.py live = patch DOC only.
Disjoint tracked package: `voice_ops/recording/` (NOT in gitignored droplet_work).

## Founder bug (root cause, audited)
After a call, recording takes 20-60min (or never) + cannot play; transcript/summary missing.
ROOT CAUSE: LiveKit egress finalize is fire-and-forget (caller.py:2715, ai_manager/recorder.py:200) —
no completion polling; `recording_status` set to 'recording' at room-create and never updated.

## FIX (this wave)
1. Egress-finalize poller — ListEgress -> on EGRESS_COMPLETE set recording_status=completed + emit recording_ready via W8 EventBus. Outbound + inbound.
2. Staged pipeline recording -> transcript -> AI summary, each emitting its event in order.
3. Object-storage adapter (R2 primary playback + B2 archive, S3-compatible) with a deterministic key.
4. Retention-TTL + cleanup + storage-usage accounting + a deletion audit (raw deleted, summary/lead-intel preserved).
5. get-recording status API contract for the panel.

Wrap (do not edit) LiveKit egress + caller.py. Reuse voice_kernel/events EventBus.
0 droplet/agent imports at load (lazy). pytest mock LiveKit/S3/Redis.

## Build units — ALL DONE ✅
- [x] U1 config.py — RecordingConfig flags (default OFF), deterministic tenant-partitioned key, R2/B2 creds
- [x] U2 storage.py — S3-compatible adapter (R2 primary + B2 archive), HEAD-verify, presign, archive-copy, usage; lazy boto3
- [x] U3 egress.py — LAZY LiveKit ListEgress wrapper -> EgressView (status enum->string, real dur/size/key); outbound room-filter + inbound egress_id
- [x] U4 poller.py — FinalizePoller: poll to EGRESS_COMPLETE -> status=completed + emit ONE recording_ready (idempotent, content-pinned ts)
- [x] U5 pipeline.py — StagedPipeline: recording->transcript->summary, each emits its event IN ORDER; injected providers (sync/async)
- [x] U6 retention.py — TTL + archive-then-delete + usage accounting + immutable deletion audit; NEVER deletes summary/lead intel; force override
- [x] U7 api.py — build_recording_view (panel status contract, self-heal stuck status via HEAD) + recordings_envelope
- [x] U8 __init__.py — public surface, all lazy
- [x] U9 tests — 32 green: finalize flips+emits (outbound+inbound), failed/timeout no-emit, tiny-file-not-playable, idempotent dedup, staged-in-order, retention preserve+force+tenant-scoped, api self-heal, IMPORT-ISOLATION (0 droplet/livekit/boto3/redis at load)
- [x] U10 design/W9-RECORDING-SEAM.md — caller.py:2715 _finalize_call + :5317 read self-heal + recorder.py inbound patch DOC (file:line, flag)
- [x] VERIFY: python -m pytest voice_ops/recording/ voice_kernel/ = 389 passed; agent.py md5 98655dbf UNCHANGED (earner law preserved)

## Outcome
Real-time recording fix built as disjoint tracked package voice_ops/recording/ (5 modules + 6 test files).
Reuses voice_kernel.events W8 bus + recording_ready/transcript_ready/summary_ready factories.
SEAM is patch-DOC only — NO live file edited. Idempotency: recording_ready carries the DURABLE key (not the
volatile presigned url) + a content-derived stable ts_iso pin, so a re-finalize dedups on the bus.
NOTE: a SEPARATE session's voice_ops/tests/test_callback_cadence.py has 6 pre-existing tz/now-injection
failures (negative timedelta) — NOT this wave's code; voice_ops/recording/ is disjoint and 32/32 green.

## Notes / learnings
- Baseline: voice_kernel/ = 357 passed (clean).
- Reuse: voice_kernel.events (InMemoryEventBus, recording_ready/transcript_ready/summary_ready factories, EventBusConfig).
- Mirror import-isolation: every livekit/boto3/redis import is LAZY inside a function; module top-level imports nothing heavy.
