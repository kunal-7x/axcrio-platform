# W16 — WhatsApp Media Library + Campaign Builder (wave run)

Date: 2026-06-18 · Branch `fix/realtime-voice-kernel-v2` · All-in-one (no sub-workflows).
EARNER LAW honored: agent.py / caller.py / box UNTOUCHED; backend = NEW tracked
`voice_ops/whatsapp/` (lazy DB/storage, 0 droplet imports); frontend ADDITIVE to the
existing `/whatsapp` builder (W15 shell reused). Never `git add -A`.

## What shipped
**Backend `voice_ops/whatsapp/`** (model/store/media/audience/delivery/send) + DDL
`voice_ops/db/ddl_whatsapp_media.sql` (FORCE-RLS `wa_media` + `wa_delivery`) + W8 events
(`whatsapp_delivered/read/failed/opted_out` in `voice_kernel/events/taxonomy.py`):
- MEDIA LIBRARY — upload/preview/reuse/replace/organize banner/image/video/**PDF brochure**
  (brochure = its own kind); bytes on **W9 ObjectStorage** under `wa_media/<tenant>/`.
- AUDIENCE RESOLVER — Hot/Warm/Cold/Dead + campaign + agent + requested-brochure +
  follow-up-pending + named segment + explicit; reads **W14 reporting** read-model (never
  re-classifies); fail-closed (empty spec ⇒ nothing, never "all"); opted-out subtraction.
- SEND ORCHESTRATOR — template+media → resolved audience; **DORMANT until WA creds**
  (W13 `WhatsAppConfig.is_active` via injected `profile_hook`) yet fully WIRED — a dormant
  send records `skipped_no_config` rows so the panel shows what WOULD send; flips live with
  zero code change; emits W8 events; bumps media used_count.
- DELIVERY TRACKER — one tenant row/message, forward-only funnel sent→delivered→read /
  failed / opted_out, fed by the Meta status webhook seam; emits W8 events.

**Frontend `famit-panel/app/whatsapp/`** (additive, 11→13 steps):
- New **Media** + **Brochure** steps (`MediaStep`/`BrochureStep`) on a shared, Core_2
  `MediaUploader` (upload-from-device, preview, pick-saved-to-reuse, detach, delete).
- `_lib/wamedia.ts` — dormant-safe client for `/api/whatsapp/media` (local object-URL
  preview fallback so it works before the API mounts).
- `_lib/targeting.ts` — rich targeting (+Dead +behavioural signals +campaign/agent/segment),
  fail-closed.
- `AudienceStep` rewritten to the rich targeting + **reuses W15 `LeadBadge`**.
- `DeliveryStep` — Sent/Delivered/**Read**/Read-rate/Failed/**Opted out** KPIs + per-row
  delivery stage + Meta-reason detail; `WhatsAppLogEntry` +funnel fields (back-compat).

## Verification (all green)
- `pytest voice_ops/tests/test_whatsapp_media.py` → **30 passed**; events suite green (92 total).
- `python -c import voice_ops.whatsapp` → ZERO heavy/droplet modules at load (asserted).
- `tsc --noEmit` clean; `next build` → ✓ Compiled successfully (59/59), `/whatsapp` 35.4 kB.

## Files
- Backend: `voice_ops/whatsapp/{__init__,model,store,media,audience,delivery,send}.py`,
  `voice_ops/db/ddl_whatsapp_media.sql`, `voice_ops/tests/test_whatsapp_media.py`.
- Events: `voice_kernel/events/taxonomy.py`, `voice_kernel/events/__init__.py` (4 factories).
- Frontend: `app/whatsapp/_lib/{types,wamedia,targeting}.ts`,
  `app/whatsapp/_components/MediaUploader.tsx`,
  `app/whatsapp/_steps/{MediaStep,BrochureStep,AudienceStep,DeliveryStep}.tsx`,
  `app/whatsapp/page.tsx`, `lib/api.ts`.
- Docs: `design/W16-WHATSAPP-MEDIA-SEAM.md`, this file, `W16_WHATSAPP_MEDIA_STATE.md`.

## Next (when WA creds land — seam only, NOT in this wave)
Apply the DDL, mount `/api/whatsapp/media|audience/preview|send` + the Meta status webhook
→ `DeliveryTracker.on_status`, inject `profile_hook`/`sender`/Pg-backends/RedisEventBus. The
frontend goes live with no UI change (the dormant-safe clients already target these routes).

## Learnings
- The panel icon registry (`components/Icon/index.tsx`) is a fixed name→path map; `file`,
  `play`, `eye`, `image`, `profile-bold` do NOT exist → used `feather`/`video`/`search`/
  `camera`/`profile`. Always grep the registry before using an icon name.
- `voice_ops.reporting.FactCall` is keyed per-CALL (no `lead_id` column); the audience
  resolver derives a stable per-lead key from the masked phone (two calls to one number =
  one lead). If a future wave adds `FactCall.lead_id`, the resolver already prefers it.
