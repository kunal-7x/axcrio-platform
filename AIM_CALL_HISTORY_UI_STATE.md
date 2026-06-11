# AIM Call History UI — panel-side (famit-panel app/ai-manager)

GOAL: Add a "Call History" / "Sessions" view in app/ai-manager that consumes the P1
backend (`GET /ai-manager/sessions` + `/sessions/{id}`): list of inbound AI Manager
calls (caller, time, duration, outcome, #commands, recording indicator) -> click a
session -> full transcript (turn by turn) + executed commands + results + PIN/risk
badges + an audio player for the recording (presigned URL).

## BACKEND CONTRACT (verified live 2026-06-12 on famit@168.144.153.145)
- `GET /ai-manager/sessions?limit&offset&channel&status` -> `{sessions:[row], source}`
  row = {id, vendor_id, user_id, channel, provider_call_id, caller_phone, status,
         started_at, ended_at, outcome, n_actions, llm_provider, stt_provider,
         tts_provider, recording_status, recording_duration_s, has_recording(bool)}
- `GET /ai-manager/sessions/{id}` -> `{session: row+detail, source}`  ⚠ NESTED under `session`
  detail adds: transcript_text, recording_egress_id, recording_bucket, recording_key,
    recording_url, recording_duration_s, metadata,
    turns:[{seq, role(agent|user), text, command_id, created_at}],
    commands:[{id, raw_text, detected_intent, action_type, risk_level, status,
      confirmation_status, pin_required, pin_verified, execution_result,
      error_message, created_at}],
    recording_presigned_url (minted by endpoint; '' when boto3 missing/no recording)
- Recording is DORMANT today: AIM_RECORDING_ENABLED not set, boto3 not on capsy venv
  -> presigned URL will be '' -> UI must show "recorded, link unavailable" / "no recording".

## DEPLOY
- Target: root@143.110.247.249:/opt/famit-panel (NOT a git repo — rsync'd dir).
- Service: famit-panel.service (systemd, Next.js standalone behind nginx :80).
- modelslab wave changes are in app/creative — they ARE in my local tree (AssetImage.tsx
  ?? new, several _components M). Deploy from local tree => won't clobber. Backup .next first.
- Recipe: rsync app/ai-manager + lib + components changes -> npm install --legacy-peer-deps
  -> npm run build (EXIT 0) -> systemctl restart famit-panel -> curl public 200.

## PLAN / UNITS
- [DONE] U0 recon: backend shape + types + deploy mechanism verified.
- [DONE] U1 _lib.ts: AimSession list type + getAimSessions(filters) + sessionId/sessionCaller
  helpers + getAimSessionDetail unwraps {session} + recording fields on AimSessionDetail/AimTurn.
- [DONE] U2 _calls.tsx: Call History list (caller/time/duration/outcome/#cmds/rec badge,
  channel+status filters, desktop table + mobile cards, dormant/empty states).
- [DONE] U3 page.tsx: added "Calls" tab (Home/Calls/Try it/Setup).
- [DONE] U4 sessions/[id]/page.tsx: inline <audio> player on presigned URL + Download,
  graceful "link unavailable"/"in progress"/no-recording; turns sorted by seq, created_at fallback.
- [DONE] U5 tsc --noEmit EXIT 0. Fixed pre-existing _tryit getAimSessions(20)->({limit:20}).
- [DONE] U5b local next build EXIT 0 (/ai-manager 16.5kB, sessions/[id] 4.27kB).
- [DONE] U6 DEPLOYED to root@143.110.247.249:/opt/famit-panel.
  Backups: /opt/famit-panel/.next.aimcallhist.20260612-011348 + /opt/famit-panel/_ai-manager.bak.20260612-011348
  scp'd ONLY 5 ai-manager files (_lib.ts,_calls.tsx,page.tsx,_tryit.tsx,sessions/[id]/page.tsx);
  app/creative NEVER touched -> modelslab AssetImage.tsx intact, /creative=200.
  Box build OOM'd at 2GB RAM -> added temp 4G swap (then removed) + NODE_OPTIONS=--max-old-space-size=2048;
  ⚠ gotcha: backup dir under app/ got compiled as stray routes -> moved to _ai-manager.bak.* and rebuilt clean.
  Restarted famit-panel only. VERIFIED public 200: /ai-manager, /ai-manager/sessions/[id], /creative.
  Outbound earner famit-agent untouched: active, NRestarts=0.

## STATUS: COMPLETE + LIVE. Recording playback dormant until founder sets AIM_RECORDING_ENABLED + boto3.

## NOTES
- Design system: Layout title only, reference Tabs/Card/Badge/Icon, Inter Display,
  Signal tokens. Risk in plain language (Safe/Needs approval/Blocked) via parseRiskLabel.
- Do NOT touch app/creative. NO git on the deploy box.
