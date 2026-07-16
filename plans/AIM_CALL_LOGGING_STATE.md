# AIM CALL LOGGING + RECORDING + SESSION STORE (P1) — STATE

BOX: famit@168.144.153.145 key C:\Users\kunal\.ssh\do-blr-test\id_ed25519
Live API venv = /opt/capsy-agent/.venv (famit-caller:8209 + aim-voice-agent run from here).
db.engine wired at startup via store.init() -> store.available()=True in live process.
Live DB: all 7 ai_manager_* tables present. sessions=0 rows (calls crashed pre-persist).

## FACTS
- ai_manager_sessions has transcript_text but NO recording_url + NO turns table.
- state_machine accumulates res.turns IN MEMORY; persists only final transcript via end_session (and not even passing transcript_text). JSONL mirror via endpoints._append_session.
- /ai-manager/sessions read API reads JSONL, not PG. No /sessions/{id} detail.
- recorder=None in aim_voice_agent.py (egress dormant). capsy venv HAS livekit.api 1.1.0 w/ RoomCompositeEgressRequest+EncodedFileOutput+S3Upload. NO boto3 (not needed; egress uploads to Spaces directly).
- No DO Spaces creds in .env yet -> recording wired env-gated dormant (AIM_RECORDING_ENABLED + AIM_SPACES_*).
- RLS: vendor_id = app.tenant_id GUC set by engine.session(tenant_id=vendor_id, is_admin). admin GUC bypass.
- resolve_tenant -> {tenant_id, is_admin, role,...} from TOKEN. endpoints use t["tenant_id"] only.

## PLAN — ALL DONE + DEPLOYED + VERIFIED (2026-06-11 19:23 UTC)
1. [DONE] schema.sql: ai_manager_sessions + recording_* / outcome / n_actions (idempotent ALTER), + ai_manager_session_turns table + RLS. APPLIED LIVE via ensure_schema() (8 cols + table + policy verified).
2. [DONE] store.py: add_turn(), set_recording(), list_sessions()/get_session() PG read, end_session passes transcript/outcome/n_actions.
3. [DONE] recorder.py NEW: LiveKitEgressRecorder (RoomComposite audio-only OGG -> DO Spaces S3Upload), presign() for read; env-gated DORMANT (NullRecorder until AIM_RECORDING_ENABLED + AIM_SPACES_*). never raises.
4. [DONE] state_machine: _persist_turn on every _say/_hear (seq monotonic), _flatten_transcript on end. run(session_id=) added.
5. [DONE] aim_voice_agent: pre-mint sid, build+start recorder (worker thread), pass to machine, stop+set_recording in finally. uuid import added.
6. [DONE] endpoints: GET /sessions PG-first (+jsonl fallback, filters channel/status/offset), GET /sessions/{id} (header+turns+commands+presigned URL). _jsonify for datetime/Decimal/jsonb.
7. [DONE] caller.py mount: include_router already covers the new {id} route (no caller.py change needed).
8. [DONE] DEPLOY: backed up 5 files (.P1Lbak.20260611-191900), restarted famit-caller + aim-voice-agent ONLY. earner famit-agent NEVER touched (active before+after). NRestarts=0, worker re-registered agent_name=manager.

## VERIFICATION (all PASS)
- schema: 8 new session cols + turns table (9 cols) + RLS policy live.
- store e2e: list/get correct; CROSS-TENANT get_session=None + list excludes -> RLS isolation proven.
- live HTTP w/ admin auth: GET /sessions source=pg (has_recording/n_actions/recording_status), GET /sessions/{id} -> turns+commands+rec_key, presigned='' (boto3 absent, graceful).
- routes 401 unauth (exist), famit-caller no errors, all 4 services active.

## REMAINING (founder steps to ACTIVATE recording — currently dormant/safe)
- Set in /opt/famit-agent/.env: AIM_RECORDING_ENABLED=1, AIM_SPACES_BUCKET, AIM_SPACES_REGION, AIM_SPACES_ENDPOINT, AIM_SPACES_KEY, AIM_SPACES_SECRET (DO Spaces). Restart aim-voice-agent. Then real call audio -> Spaces -> session.recording_key.
- For presigned playback URLs: `pip install boto3` into /opt/capsy-agent/.venv (read side only). Without it the panel shows "recorded, link unavailable".

## REGRESSION GATE (before+after)
- famit-agent (outbound earner) MUST stay active. Never restart it.
- curl famit-caller :8209 /health or a known route 200 before+after.
