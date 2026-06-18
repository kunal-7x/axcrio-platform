# W9 — Real-Time Recording Finalize + Staged Artifacts: the flag-gated SEAM

Status: **SEAM NOTE ONLY — NOTHING WIRED.** This wave built + tested the
`voice_ops/recording/` package (disjoint, tracked, droplet-free). The earner is
byte-identical: `droplet_work/agent.py` md5 = `98655dbf` (unchanged);
`caller.py` / `aim_voice_agent.py` / `ai_manager/recorder.py` untouched.

This file is the precise, file:line recipe for the SEPARATE, founder-signed
wiring wave — one box-mutating change, real-flow smoke, revert path.

---

## 0. The founder problem this closes

"After a call the recording takes 20-60 min (or never) + cannot play;
transcript/summary missing."

ROOT CAUSE (audited): LiveKit egress finalize is **fire-and-forget** —
`caller.py:2715` (`_finalize_call`, outbound) and `ai_manager/recorder.py:200`
(`stop()`, inbound) never poll for completion. `recording_status` is stamped
`"recording"` at room-create (`caller.py:2969`) and **never transitions**. The
row is only ever self-healed incidentally when something reads it
(`caller.py:5370` inbound). So the panel shows nothing for tens of minutes — or
forever — and transcript/summary (written async by `agent.py:535-553`) arrive on
their own uncoupled timeline.

FIX (this package): poll `ListEgress` to `EGRESS_COMPLETE` the instant the call
ends, flip `recording_status="completed"`, emit `recording_ready`; then stage
`transcript_ready` and `summary_ready` as each artifact lands; store in object
storage (R2 hot / B2 archive) under a deterministic key; retention-TTL + cleanup +
usage accounting + immutable deletion audit; and a panel status API that
self-heals a stuck row on read.

## 1. What exists now (the built, tested surface)

`voice_ops/recording/` — 32 tests green (`python -m pytest voice_ops/recording/`):
- `config.py` — `RecordingConfig.from_env()` (master flag `RECORDING_FINALIZE_ENABLED`
  default OFF; R2/B2 `StorageTier`s) + `object_key(tenant, call)` (DETERMINISTIC,
  tenant-partitioned, fail-closed on empty tenant).
- `storage.py` — `ObjectStorage` (S3-compatible R2 primary + B2 archive; `head`,
  `playable`, `presign_get`, `copy_to_archive`, `delete`, `usage`; lazy boto3,
  never raises).
- `egress.py` — `EgressClient` (LAZY LiveKit `ListEgress` wrapper) -> `EgressView`
  (status enum -> `recording|completed|failed`, real duration/size/key).
  `list_egress_for_room(room)` (outbound, no egress_id) + `finalize_one(egress_id)`
  (inbound). Test-injectable `client=`.
- `poller.py` — `FinalizePoller.finalize(...)` polls to completion, flips status,
  emits ONE `recording_ready`. Injectable `bus` / `egress` / `storage` / `sleep`.
  Idempotent (stable, content-derived `ts_iso` pin -> bus dedup).
- `pipeline.py` — `StagedPipeline.run(...)` runs finalize -> transcript -> summary,
  emitting `recording_ready` -> `transcript_ready` -> `summary_ready` IN ORDER.
  `transcript_provider` / `summary_provider` are INJECTED (sync or async).
- `retention.py` — `RetentionManager.sweep(candidates)` (archive R2->B2 then delete
  expired raw; NEVER deletes summary/lead intel; refuses delete when intel not
  preserved unless `force`; immutable `DeletionAuditRecord` per delete) +
  `storage_usage(tenant)` (tenant-scoped).
- `api.py` — `build_recording_view(...)` (panel status contract; self-heals a
  stuck status via HEAD on the deterministic key; presigns only when playable) +
  `recordings_envelope(views)`.

Reuses `voice_kernel.events`: the W8 `EventBus` (Null/InMemory/Redis all conform),
the `recording_ready/transcript_ready/summary_ready` factories, and
`timeutil.parse_iso` for retention expiry. IMPORT ISOLATION proven by
`tests/test_import_isolation.py`: importing the package pulls ZERO
droplet_work/livekit/boto3/redis at load.

## 2. The gate (default OFF — stays OFF until the wiring wave)

`RecordingConfig.enabled` reads `RECORDING_FINALIZE_ENABLED` (default `"0"`).
Place it in the **systemd drop-in** of the box being wired, **never the shared
`.env`** (LEARNINGS §2: a shared-.env flag leaks across inbound + the outbound
earner on restart). R2/B2 creds + `EVENTBUS_REDIS_URL` likewise on the box.
With the flag OFF every entry point is a no-op and the live recording path is
exactly as today.

## 3. OUTBOUND seam — `caller.py::_finalize_call` (PATCH, do not apply now)

`droplet_work/caller.py:2715 async def _finalize_call(it, now_t, tenant_id, cid, camp_fields)`
is the single post-call touch-point. After the existing
`_write(CALLS_FILE, CALLS)` (~`:2736`), schedule a DETACHED finalize task — it must
NOT block the dial loop, must never raise (the package guarantees both):

```python
# --- W9 recording finalize (behind RECORDING_FINALIZE_ENABLED) -------------
try:
    from voice_ops.recording import RecordingConfig, StagedPipeline, EgressClient, ObjectStorage
    from voice_ops.recording.poller import FinalizePoller
    _rcfg = RecordingConfig.from_env()
    if _rcfg.enabled:
        _bus = _get_event_bus()          # the SAME singleton W8 bus the emit-site builds (§ W8 seam)
        _storage = ObjectStorage(_rcfg)
        _poller = FinalizePoller(_rcfg, bus=_bus, egress=EgressClient(), storage=_storage)
        _pipe = StagedPipeline(
            _rcfg, bus=_bus, poller=_poller,
            transcript_provider=_w9_transcript_provider,   # reads TRANSCRIPT_DIR/<room>.json (see §5)
            summary_provider=_w9_summary_provider,          # reads the transcript json's summary fields
        )
        # room_name == cid for the outbound room convention; no egress_id on auto-egress.
        asyncio.create_task(_pipe.run(
            call_id=cid, tenant_id=tenant_id, room_name=cid, direction="outbound",
        ))
except Exception as _e:
    log.warning("W9 finalize schedule failed (non-fatal): %r", _e)
```

The detached task polls `ListEgress(room_name=cid)` (auto-egress has no egress_id),
flips the row when complete, and emits the staged events. The existing
reconciliation sweep at `caller.py:7251-7314` stays as the safety net; W9 makes the
common path real-time instead of relying on that sweep.

OUTBOUND read self-heal — `caller.py:5317 _outbound_rec_item`: replace the
status passthrough with `build_recording_view(...)` so a row still stuck at
`"recording"` is HEAD-verified against the deterministic key and flipped to
`"completed"` + presigned on read (no egress_id needed). Mirror of the inbound
self-heal that already exists at `caller.py:5370`.

## 4. INBOUND seam — `ai_manager/recorder.py` + the read path

Inbound already stores `egress_id` (`recorder.start()` returns it) and already has
a working `recorder.finalize(egress_id)` (`recorder.py:288`). W9 ADDS the *poll
loop* + the *staged events* the inbound path lacks:

At inbound hangup (where `recorder.stop()` is called, `recorder.py:200` caller
site in `aim_voice_agent.py`'s shutdown), schedule the same detached
`StagedPipeline.run(..., egress_id=<stored egress_id>, direction="inbound")`. The
poller prefers the `egress_id` lookup (`EgressClient.finalize_one`) and falls back
to the room filter. The existing read self-heal at `caller.py:5370-5388` can be
left as-is OR replaced with `build_recording_view(...)` for one shared code path.

## 5. Provider bindings (the box wires these; package stays droplet-free)

The pipeline's transcript/summary providers are INJECTED so the package never
imports droplet code. On the box, bind them to the artifacts that ALREADY exist:

```python
def _w9_transcript_provider(tenant_id, call_id):
    tr = _read(TRANSCRIPT_DIR / f"{call_id}.json", {})   # caller.py:2725 already reads this
    if not tr:
        return None
    return {"turns": tr.get("turns", []), "text": tr.get("summary", "")}

def _w9_summary_provider(tenant_id, call_id, transcript):
    tr = _read(TRANSCRIPT_DIR / f"{call_id}.json", {})   # written by agent.py:535-553 (_summarize)
    if not tr.get("summary") and not tr.get("outcome"):
        return None
    return {
        "summary": tr.get("summary", ""),
        "lifecycle": tr.get("outcome", ""),               # map outcome -> lifecycle as needed
        "conversion_prob": tr.get("interest"),
    }
```

No new summarization is introduced — W9 SEQUENCES + EMITS the existing transcript
file + Groq `_summarize` output. If the file is not yet written (agent shutdown
callback still running), the stage is skipped (no empty event) and the
reconciliation sweep / a later finalize picks it up.

## 6. Object-storage egress config (OPTIONAL upgrade, separate sub-wave)

Today both paths use `EncodedFileOutput(OGG)` to DO Spaces. To move to R2 hot /
B2 archive + near-live HLS, swap the egress request's `S3Upload` to the R2 creds
(`config.StorageTier` shape) and optionally add `SegmentedFileOutput`
(`playlistName=full.m3u8`, `livePlaylistName=live.m3u8`, `segment_duration=4`) for
~8s-latency live monitoring. This is an egress-REQUEST change in `caller.py:214
_build_outbound_egress` / `recorder.py:129 start()` — independent of the finalize
poller (which works against whatever bucket the egress writes to). Keep the
deterministic `object_key(...)` so the read side can HEAD/presign without an
egress_id.

## 7. Retention cron (separate, non-box-mutating)

`RetentionManager.sweep(candidates)` is pure-Python over a candidate list the cron
builds from the recordings table (this package owns NO DB). Schedule it daily; it
archives + deletes raw media older than `RECORDING_RETENTION_DAYS` (30), preserves
all summary/lead intel, and returns an audit the cron persists to the immutable
`events`/audit leg. `force` is the admin-purge override.

## 8. Verify + revert

- Tests: `python -m pytest voice_ops/recording/` (32 green) +
  `python -m pytest voice_kernel/` (357 green, unchanged).
- Real-flow smoke (wiring wave): place ONE outbound call, confirm
  `recording_status` flips to `completed` within seconds (not minutes) and the
  panel plays it; confirm `recording_ready`->`transcript_ready`->`summary_ready`
  on the tenant's stream in order; confirm an unrelated outbound call still rings
  (earner regression gate).
- Revert: remove the `RECORDING_FINALIZE_ENABLED` drop-in line + restart. The
  package going unused changes nothing (it is additive + flag-gated).

EARNER LAW preserved: no live file edited this wave; `agent.py` md5 `98655dbf`
unchanged.
```
