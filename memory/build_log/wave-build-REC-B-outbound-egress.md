# REC-B — Record EVERY outbound call (server-side LiveKit auto-egress)

Date: 2026-06-13. Unit of the `recordings` wave (after REC-A inbound finalize-fix).
INBOUND/earner UNTOUCHED — additive, server-side egress on the room, `agent.py` not edited.

## What shipped
Every OUTBOUND campaign call now records server-side to DO Spaces, with NO change to the
voice earner (`agent.py`). The recording is attached as **auto-egress on the room at create
time** in `caller.py run_job` — LiveKit's egress worker does the capture+upload; the agent
process never touches it.

## Files / box
- Box: `famit@168.144.153.145:/opt/famit-agent/caller.py`
- Backup: `/opt/famit-agent/caller.py.RECbak.20260613-185529`
- md5: `874d27e6…` (pre) → `e82ccbffa01824e23c3a8b9b3a89472b` (post, deployed + tracked mirror `droplet_work/caller.py`)
- venv `/opt/capsy-agent/.venv`; caller on **port 8209**, X-Auth `FamitCall2026`.

## The wiring (2 additions, both additive)
1. **Egress builder** (caller.py just after the LK config block, ~line 159):
   `_outbound_recording_enabled()` (arms only when `AIM_RECORDING_ENABLED` truthy AND the
   `AIM_SPACES_*` creds complete — DORMANT-UNTIL-CREDS, same posture as the inbound recorder,
   and it REUSES the exact same already-configured Spaces creds → bucket `capsy-recordings`,
   region `sgp1`); `_outbound_recording_key(call_id)` → deterministic
   `outbound-recordings/YYYY/MM/DD/<call_id>.ogg`; `_build_outbound_egress(call_id)` →
   `api.RoomEgress(room=api.RoomCompositeEgressRequest(audio_only=True,
   file_outputs=[api.EncodedFileOutput(OGG, filepath=key, s3=api.S3Upload(... force_path_style=True))]))`.
   Returns `(egress|None, key, bucket)`. **NEVER raises** — any build/disabled path returns
   `(None,"","")` so a paid outbound call ALWAYS dials, recorded or not (earner-safety).
2. **run_job** (~line 2528 `CreateRoomRequest`): the `call_id` is now chosen BEFORE
   `create_room` (so the call row id == the `<call_id>` in the object key); the egress is
   built and passed as `CreateRoomRequest(..., egress=_egress)`. The `rec` row gains
   3 additive fields: `recording_key`, `recording_bucket`, `recording_status`
   (`"recording"` when armed, `"disabled"` when dormant). The id source moved from an inline
   `uuid…` to the pre-computed `_call_id` — no other row field changed.

`egress_id` is intentionally NOT stored at create time: auto-egress returns no id at room
create. The **authoritative handle is the deterministic `recording_key`** — the object lands
there; a later finalize/reconcile (REC-C) can `ListEgress(room_name)` to fill duration/status,
exactly like REC-A's read-side self-heal.

## Store impact
`record_call(rec)` stores a free-form dict (CALLS_FILE JSON; PG-mode stores the dict as-is via
the store router). The 3 new keys are purely additive — NO schema migration.

## DEPLOY
local py_compile OK → scp `/tmp/caller.recb.py` (md5 match) → box-venv py_compile OK →
egress-object construction validated against the live `livekit.api` + box `.env`
(`enabled=True`, audio-only OGG, key `outbound-recordings/…`, bucket `capsy-recordings`,
sgp1 endpoint) → cp into place → `systemctl restart famit-caller` ONLY → `/health`=200,
0 Traceback/Error.

## PROOF (two real in-window outbound calls, 18:58 IST)
- Run #1 job `6e5075f615` → call row `8ac35e10d9` → SIP callID `SCL_vWxZbnWSArf4` trunk
  `ST_fmtVmNJmpzKa` +918071583488→+917861019021 (carrier reached: `486 Busy`/reason busy =
  real ring). Egress `EG_CkpWN2775XQY` **status=3 EGRESS_COMPLETE**, filename
  `outbound-recordings/2026/06/13/8ac35e10d9.ogg` **size 60436**.
- Run #2 job `9ca79fd03c` → call row `7856586d3a` → object `…/7856586d3a.ogg` **56131 bytes**.
- Spaces `capsy-recordings` prefix `outbound-recordings/2026/06/13/` = 4 objects (2 OGG +
  2 egress manifest JSON). `HEAD …/8ac35e10d9.ogg` → 60436 bytes, ContentType `audio/ogg`;
  presigned GET URL minted OK.
- Both call rows carry `recording_key` = the exact object key + `recording_status="recording"`.

## EARNER GATE — PASS (before + after)
- `agent.py` md5 `9150fabe4ff62b4b4470f9a87df346e5` UNCHANGED.
- famit-agent MainPID `1477083` / ActiveEnter 2026-06-10 19:58:18 — NEVER restarted.
- Only `famit-caller` restarted; famit-agent + aim-voice-agent untouched/active.
- 0 5xx / 0 Traceback in famit-caller since restart.
- Trunk/SIP/firewall/prompt.py defaults — NOT touched.

## NEXT (same wave, unbuilt)
REC-C unified recordings API (mount a list + `/calls/{id}/recording` presign that reconciles
via `ListEgress` like REC-A); CRM/AIM player UI for outbound recordings.
