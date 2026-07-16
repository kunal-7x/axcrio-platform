# W16 — WhatsApp Media Library + Campaign Builder — BUILD STATE

Branch: `fix/realtime-voice-kernel-v2` (EARNER LAW: never touch agent/box; backend = NEW tracked
`voice_ops/whatsapp/`; frontend additive to `famit-panel/app/whatsapp/`). NEVER `git add -A`.

## PLAN (units)
- [DONE] U0 explore + read reuse seams (W9 storage, W8 events, W13 config, W14 reporting, run audience)
- [DONE] U1 BACKEND voice_ops/whatsapp/ — media library (upload/store/preview/reuse), tenant FORCE-RLS
- [DONE] U2 BACKEND audience resolver (hot/warm/cold/dead/segment/campaign/agent/requested-brochure/follow-up-pending)
- [DONE] U3 BACKEND send-orchestrator (template+media -> audience; dormant w/o WA creds; emits W8 delivery events)
- [DONE] U4 BACKEND delivery tracking (sent/delivered/read/failed/opt-out)
- [DONE] U5 W8 events: add whatsapp_delivered/read/failed/opted_out factories + EventName entries
- [DONE] U6 pytest: media upload/reuse, audience sets, dormant-but-wired send, delivery tracked, tenant-isolated
- [DONE] U7 FRONTEND MediaLibraryStep + BrochureStep (upload device / pick saved / preview), reuse Core_2
- [DONE] U8 FRONTEND audience targeting signals + delivery read/failed/opt-out columns
- [DONE] U9 design/W16-WHATSAPP-MEDIA-SEAM.md + memory/wave_runs/W16-whatsapp.md
- [DONE] U10 verify: pytest green, npm run build + tsc green

## DECISIONS
- Backend mirrors voice_ops/config + voice_ops/reporting posture: lazy DB, InMemory backend for tests,
  FORCE-RLS DDL in voice_ops/db/ddl_whatsapp_media.sql, ZERO droplet/heavy imports at module load.
- Media storage reuses voice_ops.recording.storage.ObjectStorage (W9) — presign/head/usage; tenant prefix
  `wa_media/<tenant>/`. Brochure is its own asset_type=brochure (PDF).
- Send-orchestrator is DORMANT until WA creds present (W13 WhatsAppConfig.is_active) — wired, never sends blind.
- Delivery events ride W8 EventBus (fire-and-forget) + a tenant-scoped delivery store (latest-wins by msg_id).
- Frontend: ADD steps media + brochure to the existing 11-step rail (additive), enrich AudienceStep filters
  + DeliveryStep columns. REUSE LeadBadge + GlobalFilters + Core_2. No shell rebuild.

## STATUS: COMPLETE
