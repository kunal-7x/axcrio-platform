# Wave REC-A — AIM Recording Finalize Fix (SHIPPED 2026-06-13)

Granular re-run unit (wave `w7clsa0fz`, after `wimqqngha`/`wf_1ed8af82-3c9` network drops).
Box `famit@168.144.153.145` `/opt/famit-agent`. Additive, isolated, earner-regression-gated.
🟥 agent.py / earner / trunks / firewall / SIP / prompt.py-defaults UNTOUCHED.

## Problem
AIM recording rows stuck `recording_status='recording'` / `recording_duration_s=0` even though the
audio was fine. 14/15 recent rows stuck; only 1 (`vs_2dec15955ce4`) ever reached `uploaded`/96.

## Root cause (PROVEN, not guessed)
The egress always **COMPLETES** and the full OGG always lands in Spaces — verified via LiveKit
`ListEgress`: e.g. `EG_W9hFFGao8RLj` status=3 (EGRESS_COMPLETE) dur=117173963610ns (=117s) size=1.6MB,
`EG_pmG3A2BfSiNE` =102s/1.4MB. So audio capture is NOT the bug.
The bug is the **finalize WRITE**: `aim_voice_agent.py` `_SessionLogger.finish()` (which calls
`recorder.stop()` then `store.set_recording(status='uploaded', duration_s=...)`) is dispatched
fire-and-forget via `asyncio.run_coroutine_threadsafe(_slog.finish(...), _loop)` on the room
`"disconnected"` event (aim_voice_agent.py:2606-2612). That off-loop PG write almost always loses the
race against LiveKit worker-process teardown on SIP hangup → the `uploaded`+duration UPDATE never lands.
Also: LiveKit reports egress duration in **nanoseconds** (÷1e9), and the optimistic `stop()` used
wall-clock, not the authoritative file duration.

## Fix (2 files, both famit-caller/aim-voice-agent only; agent.py untouched)
- `ai_manager/recorder.py` — new `finalize(egress_id) -> {complete,status,duration_s,key,size}` helper:
  calls LiveKit `ListEgress(egress_id=...)`, maps EgressStatus (3=COMPLETE→`uploaded`, 4/5=FAILED/ABORTED
  →`failed`, else `recording`), converts `file_results[0].duration` ns→s, and returns the real object
  key from `filename`. NEVER raises (a 404 "egress does not exist" → `complete=False`, row left as-is).
- `ai_manager/endpoints.py` `GET /ai-manager/sessions/{id}` — **finalize-on-read self-heal**: when the row
  has a `recording_egress_id` but is not yet terminal (`status not in uploaded/failed/disabled` OR
  `duration_s<=0`), call `recorder.finalize()`; if complete, persist via `store.set_recording(
  status='uploaded', key, duration_s)` and reflect on the response row, THEN presign. This does not
  depend on the fragile teardown race — every read reconciles the truth, and it self-heals all existing
  stuck rows. The agent-side stop() leg was left unchanged (the read-side reconcile is authoritative).

## Deploy + gates
- Backups: `recorder.py.RECbak.20260613-184551`, `endpoints.py.RECbak.20260613-184551`.
- `py_compile` on `/opt/capsy-agent/.venv` = OK. Restarted **famit-caller + aim-voice-agent** only.
- EARNER GATE PASS: `agent.py` md5 `9150fabe4ff62b4b4470f9a87df346e5` UNCHANGED; `famit-agent` PID
  `1477083` never restarted (still its 2026-06-10 start); both restarted services `active`, no Traceback,
  aim worker re-registered clean (`agent_name=manager`, id `AW_c8iRik2Qkexz`).

## Proof
- FRESH/stuck row `vs_dee5eeef4141` (egress `EG_W9hFFGao8RLj`): one `GET /sessions/{id}` →
  DB now `uploaded`/`117` (persisted, re-queried in PG), presigned URL minted (360 chars), and the URL
  serves the OGG: `curl -r 0-1048575` → **HTTP 206**, `audio/ogg`, 1048576 bytes.
- FRESH row `vs_07c19d8f8b0b` (11:57 UTC call) → on read: `uploaded`/`102` + presigned.
- Batch self-heal of all stuck rows via the read endpoint: **17 rows now `uploaded`** (real durations
  11s–229s); the lone remaining `recording` row's egress `EG_m3vSoUx7AM3N` returns LiveKit 404
  "egress does not exist" (aged out of history) — correctly left untouched (no false `uploaded`).

## Residual / follow-ups (next units in the wave)
- REC-B: outbound calls (`caller.py:2525 run_job` CreateRoomRequest) are NOT recorded at all — add
  Auto-Egress on the room (caller.py only; agent.py untouched).
- REC-C: unify a recordings API (`/contacts/{phone}/recordings`, `/calls/{id}/recording`).
- The agent-side fire-and-forget finish() race remains (harmless now — read reconciles). A future belt:
  also reconcile inside `list_sessions` so the LIST view shows durations without opening each session.
