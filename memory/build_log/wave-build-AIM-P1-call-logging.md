# Wave build — AIM P1: Call Logging + Recording + Session Store (§logging)

Date: 2026-06-11 19:23 UTC. Box: famit@168.144.153.145 (/opt/famit-agent). DEPLOYED + LIVE.

## GOAL
Durable record of every inbound AI Manager call: session row + full per-turn TRANSCRIPT + executed
COMMANDS + OUTCOME (ai_manager_* RLS schema) + call AUDIO recording (LiveKit egress -> DO Spaces) +
a tenant-scoped READ API the panel lists/shows. Backup-first; restart only changed services; the
OUTBOUND EARNER (famit-agent/agent.py) was NEVER touched.

## WHAT WAS ALREADY THERE (reused, not rebuilt)
- ai_manager_sessions / _commands / _action_runs / _audit_logs tables + RLS (vendor_id = app.tenant_id GUC).
- store.create_session/end_session/create_command/update_command/create_action_run/record_audit_log.
- state_machine persists command lifecycle at every hop; accumulates res.turns IN MEMORY only.
- aim_voice_agent.py inbound worker (agent_name=manager, :8091) w/ recorder=None (egress dormant).
- endpoints.py GET /ai-manager/sessions read from a JSONL mirror (NOT PG); no detail route.
- Live API famit-caller:8209 + voice worker BOTH run from /opt/capsy-agent/.venv (has livekit.api 1.1.0
  with RoomCompositeEgressRequest/EncodedFileOutput/S3Upload; NO boto3). db.engine wired at startup.

## SCHEMA (ai_manager/schema.sql — idempotent, applied via store.ensure_schema())
- ai_manager_sessions += recording_status, recording_egress_id, recording_bucket, recording_key,
  recording_url, recording_duration_s, outcome, n_actions  (ADD COLUMN IF NOT EXISTS — no destructive
  migration; verified all 8 present live).
- NEW ai_manager_session_turns(id, vendor_id, session_id, seq, role[agent|user], text, command_id,
  created_at, metadata) — ONE row per turn = the durable transcript. RLS isolation policy identical to
  every other AIM table (admin GUC OR vendor_id match), FORCE RLS. Index (vendor_id, session_id, seq).
- Zero percent-signs (exec_driver_sql-safe). PIN/OTP digits NEVER reach turns (masked upstream).

## RECORDING WIRING (ai_manager/recorder.py NEW + aim_voice_agent.py)
- recorder.LiveKitEgressRecorder: StartRoomCompositeEgress(audio_only, EncodedFileType.OGG) with
  S3Upload(key/secret/bucket/region/endpoint, force_path_style) -> uploads DIRECTLY to DO Spaces (no
  local disk, no boto3 on the write side). start()->egress_id; stop()->StopEgress + duration. Sync
  facade over async LiveKit API (own event loop) so it never blocks the agent loop.
- DORMANT-UNTIL-CREDS: recorder.enabled() = AIM_RECORDING_ENABLED truthy AND all AIM_SPACES_* set;
  else recorder.build() returns a NullRecorder -> call runs EXACTLY as before. NEVER raises (a recording
  failure can never break/silence a live call).
- aim_voice_agent: pre-mints session_id so the egress object-key + the persisted session row share one
  id; starts egress in a worker thread on join; passes recorder + session_id into machine.run(); in the
  finally stops egress and store.set_recording(tenant, sid, status/egress/bucket/key/duration). The
  durable handle is bucket+key (object key); the panel mints a presigned URL on read.

## TRANSCRIPT PERSISTENCE (ai_manager/state_machine.py)
- _persist_turn() called from _say (agent) and _hear (user): store.add_turn(tenant, sid, role, text,
  seq) with a monotonic per-session seq. Best-effort, no-op until the session row exists (post-S1) and
  whenever PG is down. _flatten_transcript() sets the session.transcript_text snapshot at end_session,
  which now also writes outcome + n_actions. run(session_id=) added (voice adapter supplies the id).

## READ API (ai_manager/endpoints.py — tenant-scoped from TOKEN, RLS)
- GET /ai-manager/sessions  -> store.list_sessions (PG-first, source=pg), JSONL fallback when PG down.
  filters: limit/offset/channel/status. headers carry status/outcome/n_actions/has_recording/rec_status.
- GET /ai-manager/sessions/{session_id} -> store.get_session: header + ordered turns + commands +
  recording_presigned_url (recorder.presign via boto3 if installed, else '' -> graceful). 404 on a
  cross-tenant id (RLS). _jsonify() makes datetime/Decimal/jsonb JSON-safe. caller.py needed NO change
  (existing include_router covers the new route).
- tenant ALWAYS t["tenant_id"] from resolve_tenant (token), never a body/query field.

## VERIFICATION (all PASS)
- ensure_schema() live: 8 new session cols + turns table (9 cols) + RLS policy present.
- store e2e (real PG): write session/3 turns/command/recording -> list shows has_recording+n_actions;
  get_session returns turns+commands+rec_key. CROSS-TENANT: other tenant get_session=None, list excludes
  -> RLS isolation PROVEN.
- LIVE HTTP w/ admin auth: GET /sessions source=pg; GET /sessions/{id} -> 2 turns + 1 command + rec_key;
  presigned='' (boto3 absent on read side, graceful). Routes 401 unauth (exist). famit-caller no errors.
- Deploy: 5 files backed up (.P1Lbak.20260611-191900); restarted famit-caller + aim-voice-agent ONLY;
  earner famit-agent active BEFORE+AFTER (never restarted); voice worker re-registered agent_name=manager,
  NRestarts=0, no crash loop. All 4 services active.

## FOUNDER ACTIVATION (recording is dormant/safe until these)
1. .env: AIM_RECORDING_ENABLED=1 + AIM_SPACES_BUCKET/REGION/ENDPOINT/KEY/SECRET (DO Spaces) -> restart
   aim-voice-agent. Real call audio then lands in Spaces; session.recording_key set.
2. For presigned playback URLs: pip install boto3 into /opt/capsy-agent/.venv (read side only).

ROLLBACK: restore /opt/famit-agent/{ai_manager/{schema.sql,store.py,state_machine.py,endpoints.py},
aim_voice_agent.py}.P1Lbak.20260611-191900 + rm ai_manager/recorder.py + restart famit-caller +
aim-voice-agent. (Schema ALTERs are additive/idempotent — safe to leave even on rollback.)
