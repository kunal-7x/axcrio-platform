# W16 — WhatsApp Media Library + Campaign Builder SEAM

Status: BUILT (backend + frontend), TESTED, dormant-until-WA-creds. Branch
`fix/realtime-voice-kernel-v2`. EARNER-SAFE: zero droplet/agent/box imports; backend
is a NEW tracked package `voice_ops/whatsapp/` (lazy DB + lazy storage); frontend is
ADDITIVE to the existing 11→13-step `/whatsapp` builder (W15 shell reused, not rebuilt).

## Founder ask → what shipped
1. **MEDIA LIBRARY** — upload/store/preview/reuse/replace/organize banner, image,
   video, and PDF brochure. Brochure is its OWN kind + its OWN builder step (PDFs are
   critical in real estate).
2. **Multi-step CAMPAIGN BUILDER** — template → banner → images → video → brochure →
   audience → send, supporting BOTH new uploads + saved assets.
3. **AUDIENCE TARGETING** — Hot/Warm/Cold/Dead, custom segment, campaign-X, agent-Y,
   requested-brochure, follow-up-pending (NOT "send to all").
4. **DELIVERY TRACKING** — sent/delivered/read/failed/opt-out.
5. **FUTURE-READY** — blank cred fields, dormant until WA creds land (reuses the W13
   `WhatsAppConfig.is_active` gate); activates with zero code change.

---

## A. BACKEND — `voice_ops/whatsapp/`

All modules import ONLY voice_ops.{config,recording,reporting} + voice_kernel — every
heavy dep (boto3 / sqlalchemy / redis) is lazy inside a function. `import voice_ops.whatsapp`
pulls ZERO droplet/heavy modules (verified).

| File | Role | Key reuse |
|---|---|---|
| `model.py` | MediaAsset, MediaKind (banner/image/video/brochure), AudienceSpec, DeliveryRow, DeliveryStatus, SendPlan/SendResult; per-kind MIME+size rules | mirrors `reporting.model` flat-dataclass posture |
| `store.py` | MediaStore + DeliveryStore; InMemory + lazy `_Pg*` backends, tenant-scoped, fail-closed | mirrors `config.store` (RLS GUC per session, `db.engine`) |
| `media.py` | MediaLibrary: validate → put bytes on **W9 ObjectStorage** (`wa_media/<tenant>/`) → persist FORCE-RLS row; preview presign, reuse/replace (same id), rename/retag/archive/delete, usage | **reuses `voice_ops.recording.storage.ObjectStorage`** (presign/head/delete/usage) |
| `audience.py` | AudienceResolver over the **W14 reporting read-model**; resolves temps/campaign/agent/requested-brochure/follow-up-pending/segment/explicit; fail-closed empty spec; opted-out subtraction | reads `reporting.store` FactCall rows — never re-classifies (W7 lifecycle) |
| `delivery.py` | DeliveryTracker: seed at dispatch, `on_status` webhook ingest (forward-only funnel), emits **W8** whatsapp_delivered/read/failed/opted_out | rides W8 EventBus fire-and-forget (mirrors `config.events`) |
| `send.py` | SendOrchestrator: plan(template+media→audience) → dispatch OR dormant-record; gated on `profile_hook` (W13 creds); injected `sender` does the Meta call | ties media+audience+delivery+events together |

### Persistence — `voice_ops/db/ddl_whatsapp_media.sql`
Two FORCE-RLS tables (`org_id = current_setting('app.tenant_id')` OR is_admin), applied
at mount alongside config/booking/gcal DDL:
- `wa_media` — one row per asset (kind, media_type, storage_key, size, page_count, tags,
  used_count, status).
- `wa_delivery` — one row per message, latest-wins by message_id (status, reason,
  sent/delivered/read/failed timestamps).

### Future-ready / dormant gate
`SendOrchestrator.is_active(tenant)` calls the injected `profile_hook` (wraps
`WhatsAppConfig.is_active(has_whatsapp_key)`). Default = DORMANT (no hook → never sends).
A dormant send STILL resolves the audience + creates `skipped_no_config` delivery rows, so
the panel shows exactly what WOULD be sent. The moment WA creds are added to the W13 key
store + vendor profile, the same `send()` call dispatches — zero code change.

### Events (W8) — `voice_kernel/events/taxonomy.py`
Added to the closed taxonomy (append-only): `whatsapp_delivered`, `whatsapp_read`,
`whatsapp_failed`, `whatsapp_opted_out` (+ factories, re-exported from `voice_kernel.events`).
`call_id` = the WhatsApp message id so the delivery store keys latest-wins per message.

### Mount checklist (when WA creds land — NOT done in this wave; seam only)
1. Apply `ddl_whatsapp_media.sql` (FORCE-RLS).
2. Mount panel routes: `GET/POST/DELETE /api/whatsapp/media`, `POST .../media` (multipart),
   `GET /api/whatsapp/audience/preview`, `POST /api/whatsapp/send`, and wire the Meta status
   webhook → `DeliveryTracker.on_status`.
3. Inject `profile_hook` (W13), `sender` (live `whatsapp.py` Meta Cloud-API call), Pg backends,
   RedisEventBus.

---

## B. FRONTEND — `famit-panel/app/whatsapp/` (additive)

Rail grew 11 → 13 steps. New: **Media** (banner+images+video) and **Brochure** (PDF), both
between Banner Studio and Preview. W15 shell + Tabs stepper + StepCtx pattern reused verbatim.

| File | Role |
|---|---|
| `_lib/types.ts` | +StepKey `media`/`brochure`; +`WaMedia`/`WaMediaKind`; +`TemplateDraft.media[]` + `.brochure` |
| `_lib/wamedia.ts` | **DORMANT-SAFE** client for `/api/whatsapp/media` — list/upload/delete; per-kind validate; on any 404/503/network failure falls back to a LOCAL object-URL preview (`configured:false`) so the builder works today |
| `_lib/targeting.ts` | W16 targeting (Hot/Warm/Cold/**Dead**, requested-brochure, follow-up-pending, campaign, agent, segment); derives signals from existing Lead fields; fail-closed (no positive target ⇒ empty, never "all") |
| `_components/MediaUploader.tsx` | Reusable Core_2 upload + saved-library picker (used by both new steps): upload from device, preview thumb, pick saved to reuse, detach, delete |
| `_steps/MediaStep.tsx` | Banner (single) + Images (multi) + Video (single) → ordered `draft.media` |
| `_steps/BrochureStep.tsx` | PDF brochure → `draft.brochure`, with preview |
| `_steps/AudienceStep.tsx` | REWRITTEN to the rich targeting + **reuses the W15 `LeadBadge`**; temp chips + signal chips + campaign/agent selects + quick targets; truthful client-side preview |
| `_steps/DeliveryStep.tsx` | Funnel KPIs (Sent/Delivered/**Read**/Read-rate/Failed/**Opted out**) + per-row **Delivery** stage badge + Detail (Meta reason / read time) |
| `page.tsx` | wires `media`/`brochure` into STEP_COMPONENTS |
| `lib/api.ts` | `WhatsAppLogEntry` +funnel fields (delivery_status/delivered_at/read_at/failed_at/opted_out/campaign_id) — additive, back-compat |

Reuse honored: W15 shell + GlobalFilters-ready + LeadBadge + Core_2 (Card/Button/Select/
Table/KpiCard/CardChartPie/Image/Badge/Spinner). NO from-scratch UI.

---

## Tests — `voice_ops/tests/test_whatsapp_media.py` (30 PASS)
Media: upload/validate(MIME+size+PDF-magic)/reuse-replace/list-by-kind/organize/archive/
delete/usage/dormant-storage-still-persists-metadata/tenant-isolation. Audience: temps,
campaign, agent, AND-composition, follow-up-pending, requested-brochure, named segment,
explicit-union, fail-closed-empty, opted-out exclusion, tenant-isolation, preview breakdown.
Delivery: sent→delivered→read funnel + events, forward-only (no regression), failed+opted-out
+events, summary counts, tenant-isolation. Send: dormant-records-plan, dispatches-when-active,
media-attach+used_count, drops-missing-media, empty-audience-refused, tenant-isolation.

## Verification
- `pytest voice_ops/tests/test_whatsapp_media.py` → 30 passed; events suite green (92 total).
- `import voice_ops.whatsapp` → ZERO heavy/droplet modules (asserted).
- `tsc --noEmit` clean; `next build` → ✓ Compiled successfully (59/59 pages), `/whatsapp` 35.4 kB.
- agent.py / caller.py / any box: UNTOUCHED.
