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
- [ ] VERIFY tsc --noEmit EXIT 0 + next build EXIT 0
- [ ] DEPLOY FORTRESS backup-first; restart famit-panel ONLY; confirm 200s
- [ ] COMMIT

## NOTES
- AIM player at app/ai-manager/sessions/[id]/page.tsx:274-308 = reference (audio controls preload=none + Download <a download>).
- recordings rows: {call_id, direction, phone, started_at, duration_s, status} + presigned url.
- Premium Core_2, Inter Display, zero raw hex (Signal tokens). Icon is a REGISTRY (no whatsapp/phone; use camera-video/download/mobile/chat/clock).
- Deploy box root@143.110.247.249:/opt/famit-panel (FORTRESS, no agent dir -> can't touch earner).
