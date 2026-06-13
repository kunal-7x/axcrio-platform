# REC_UI_STATE — wimqqngha frontend (Handoff name + CRM Recordings)

Branch: feat/premium-ui. FRONTEND ONLY. Backend contract per the prompt (recordings
API `/contacts/{phone}/recordings` + `/calls/{id}/recording`; handoff entry gains `name`).
Backend NOT yet on box (verified) -> UI must be DORMANT-SAFE (no recordings/404 -> calm empty state).

## UNITS
- [x] 1a lib/api.ts: HandoffMember.name + toHandoffMember + addHandoffMember + saveHandoffOrder carry name — DONE
- [x] 1b _handoff.tsx: Name field (required) in add form + name leads in list rows (phone now uses mobile icon) — DONE
- [x] D1 crm/client.ts: Recording type + RecordingsResponse + getContactRecordings(phone) (dormant-safe, never throws) — DONE
- [x] D2 crm/[id]/page.tsx: "Recordings" card (left rail) + RecordingsCard/RecordingRow + player (preload=none, seek) + Download; mirrors AIM player — DONE
- [x] D3 AIM session player — already robust (audio controls preload=none + download, presigned). Playback issue was backend finalize (Unit A), not the player. No FE change needed. — DONE
- [x] VERIFY tsc --noEmit EXIT 0 + next build EXIT 0 — DONE (both EXIT 0; /crm/[id] 7.09kB, /run 12.4kB compiled)
- [x] DEPLOY FORTRESS backup-first; restart famit-panel ONLY; confirm 200s — DONE 2026-06-13
- [x] COMMIT — DONE (UI committed `68bbc63`; backend API `b06ef17`/`4cdd3e1`/`40daa27`)

## DEPLOY (2026-06-13, re-run after wimqqngha network-drop)
The UI was COMMITTED (`68bbc63`) but NEVER deployed (box was at old LPR BUILD_ID `WwBfbgcnCuH-Rzi9--YvE`;
box `_handoff.tsx`/`crm/client.ts` had NO `name`/`getContactRecordings`). Built LOCALLY (no on-box OOM
risk), shipped artifacts. Backups `*.RECUIbak.20260613-195539` (.next/app/lib). New BUILD_ID
`4aXNPr1rvAfpK4ku5dNa7`. famit-panel ONLY restarted (PID 239673, 14:34 UTC). Confirmed 200 + new
BUILD_ID served on BOTH loopback:3001 (/ /login /crm /crm/[id] /ai-manager /ai-manager/sessions/[id])
AND the panel.famit.in Cloudflare edge. EARNER N/A — FORTRESS box (143.110.247.249) has no agent dir;
earner box (168.144.153.145) NEVER touched this unit. ROLLBACK: restore the 3 RECUIbak dirs + restart.

## NOTES
- AIM player at app/ai-manager/sessions/[id]/page.tsx:274-308 = reference (audio controls preload=none + Download <a download>).
- recordings rows: {call_id, direction, phone, started_at, duration_s, status} + presigned url.
- Premium Core_2, Inter Display, zero raw hex (Signal tokens). Icon is a REGISTRY (no whatsapp/phone; use camera-video/download/mobile/chat/clock).
- Deploy box root@143.110.247.249:/opt/famit-panel (FORTRESS, no agent dir -> can't touch earner).
