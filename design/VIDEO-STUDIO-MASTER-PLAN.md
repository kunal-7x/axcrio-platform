# 🎬 VIDEO-STUDIO-MASTER-PLAN.md — the 100% design (READ-ONLY; verified on disk 2026-06-14; red-team-hardened)

> FINAL SYNTHESIS: the cost/completeness/earner red-teams are folded in (§13b H1-H10 + the cost-truth meter §6
> + the 1-paid-test choke-point + reaper/moderation/lifecycle/alerts + cross-product seam discipline).

> One of the 3-PRODUCTS megaplan heart designs (RAG-voice-brain · **Video Studio** · Vault).
> READ-ONLY explore→research→design. NO box mutation, NO caller.py/agent.py edit by this pass.
> Treats the founder's brief as the 1% sketch; designs every feature/function/schema/UX/automation a
> production-grade, sellable, low-latency, multi-tenant-RLS, earner-safe version needs that he did NOT name.
> Grounded in the LIVE tree (every file:line below verified), the existing `design/creative-video-studio.md`
> + `design/creative-studio-ui.md` specs, `MASTER_DNA_PLAN.md §L/§N`, and the founder's compressed brief.

---

## 0. ⚡ THE HEADLINE CORRECTION — the brief's research is good, but its top "P0 gaps" are STALE

The compressed brief was written against an OLDER tree snapshot. I re-verified every "gap" on disk. **Three
of its P0/P1 claims are already DONE in the live code** — do not re-do them; the real gaps are narrower and
different. This matters because doing the stale "fixes" would CHURN already-shipped, already-correct code.

| Brief claim | Verified reality on disk | Verdict |
|---|---|---|
| **P0: `engine.py:46` import wrong** (`from automation.video import client` → `media_gen.video.client`) | `creative/video_studio/engine.py:51` already lazily imports `from automation.video import client`; that module is EMPTY on purpose. The real lower engine lives at `media_gen/video/client.py` and its docstring (`client.py:4-5`) explicitly says "wiring is a one-line import repoint `automation.video.client` → `media_gen.video.client`." | **REAL but mislocated.** The fix is a 1-line change at `engine.py:51` (the `try:` import line), NOT line 46. It's the studio→engine seam, and it ONLY matters if the upper `video_studio` orchestrator is mounted (it is NOT — see below). |
| **P0: media router not mounted in caller.py** | `caller.py:6968-6983` ALREADY mounts `media_gen.router.build_router(resolve_tenant, can, need_auth, _forbidden, firewall=…)` under `FEATURE_MEDIA` (default OFF). The token-deriving authenticated surface, the 12-endpoint table, the per-provider webhook signature-verify — all wired. | **ALREADY DONE.** The LOWER engine (submit/poll/approve/webhook) is mountable today. Only `FEATURE_MEDIA=1` + provider creds are missing (founder action). |
| **P2: new `video_presigned_cache` table needed** | The live AI-asset service `ai_asset/endpoints.py:221-256` already serves `/assets/{id}/raw` as a **302-redirect to a 24h presigned Spaces URL**; `/assets/{id}` returns versions "already presigned" (`:211`). `AssetImage.tsx` already documents+consumes this exact pattern. | **DON'T BUILD A NEW TABLE.** Mirror the proven 302-presign pattern. A presign *cache* is a perf nicety (re-signing is cheap, ~1ms), not a schema requirement. If wanted, cache in Redis (TTL < signed lifetime), never a PG table. |

**What is ACTUALLY missing (the true gap set, re-derived):**
1. The **UPPER orchestrator** (`creative/video_studio/*` — campaign→AI-script→BATCH fan-out→Asset Library) is
   built (`service.py`/`batch.py`/`endpoints.py` exist + 19 offline tests pass) but its `endpoints.py` is
   **NOT mounted** in caller.py, and its `engine.py:51` seam still points at the empty `automation.video`.
2. The studio's assets register into `creative/shared/library.py` (a **JSON store under `VAR/creative/`**) —
   **NOT** the live `ai_asset_*` PG schema the frontend `lib/assets.ts` reads. So a generated video would
   NOT appear in the live Asset Library the founder already uses. **This is the load-bearing integration gap
   the brief missed entirely** (§5).
3. **Frontend has zero video affordance:** `AssetImage.tsx` is `<img>`-only; `FilterRail KIND_OPTS` has no
   "Video"; `LibraryGallery` has no Images↔Videos toggle; there is no `app/creative/video/page.tsx`; the
   `Asset` type has no `duration_s`/`with_audio`/`poster_url`.
4. **No FFmpeg/Remotion composite path** — the brief's own research says this is the 100×-cheaper default for
   most ad creative, but neither the lower engine nor the studio has a `compose` provider. **This is the
   single biggest cost+differentiation lever and it is unbuilt** (§6).
5. **No Signal-Loop export** — `ab_group`/`ai_generated` lineage into the Meta CAPI path (§9).
6. **No DB tables at all for video** — the lower engine + studio are 100% JSON-file backed; nothing is in PG,
   so no RLS, no analytics, no multi-box durability (§7).

So the design below is: **(A) wire the already-built lower+upper engines, (B) bridge studio output into the
live `ai_asset_*` PG library so videos appear where images already do, (C) add the FFmpeg composite tier as
the cheap default, (D) the full frontend video surface, (E) the PG schema with RLS, (F) the Signal-Loop
export.** Each additive, flag-gated, earner-safe.

---

## 1. GROUND TRUTH — verified file:line map (cite before any build)

**Lower video ENGINE (the render primitive) — `droplet_work/media_gen/` (11 video .py, all present):**
- `media_gen/video/client.py:41` `submit_video_job(brief)` — 6-gate pipeline: idempotency replay → license
  gate (`:66`) → content+likeness screen (`:73,:79`) → estimate+cap (`:87`) → approval-park (`:97`) →
  reserve-hold+submit (`:105`). `poll_video_job(job)` `:215` — on succeeded settle+push-to-Spaces (`:269`),
  on failed release-hold (`:292`). NEVER raises (`:106`,`:265`).
- `media_gen/video/providers.py` — 6 backends (fal/replicate/luma/higgsfield/selfhost/generic) +
  `verify_webhook` (per-provider sig, fail-closed) + `license_ok` (Apache-2.0 self-host allowlist).
- `media_gen/video/cost.py` — `estimate_cost`/`check_caps`/`reserve`/`settle`/`release` (wallet seam, JSON
  hold-store degrade); `pricing.py` — USD→INR FX, `per_second`/`per_generation` modes.
- `media_gen/video/safety.py` — `screen()` (AUP denylist) + `likeness_gate(person_image, likeness_consent)`.
- `media_gen/video/store.py` — JSON job store; `schema.py` — `VideoBrief` (has `person_image`,
  `likeness_consent`, `idempotency_key`, `provider`, `model`), `JobStatus`, `new_job_record`.
- `media_gen/spaces.py` — shared S3 writer: `put_from_url` (`:99`), `put_bytes` (`:76`), **`signed_url(key,
  expires_s)` `:126`** (the presign primitive), dormant-until-`SPACES_*`.
- `media_gen/router.py` — `build_router(...)` `:170` (AUTH surface, token-derived tenant, `_owned()` by-id
  ownership check `:197`) + `_bare_router()` `:72` (TEST-ONLY, DO NOT MOUNT). Webhook unauth (provider-signed).
- `media_gen/tests/test_video_offline.py` — 19 offline tests (mocked, no network), all passing per brief.

**Upper ORCHESTRATOR (campaign→script→batch) — `droplet_work/creative/video_studio/` (11 .py):**
- `service.py` — pure callables: `propose_batch`/`approve_batch`/`reject_batch`/`cancel_batch`/`collect_batch`/
  `batch_status`/`list_batches`/`list_assets`/`promote_winner` + `_async` twins. `set_campaigns_source(fn)`
  injects the spine's `list_campaigns`. `_shape()` `:187` returns the API slice.
- `batch.py` — `generate_batch` fan-out (scripts → briefs → cost-gate → approval-gate → render_fn);
  `script.py` — 5 ANGLES (pain_point/social_proof/offer_led/urgency/founder_voice); `brief.py` — route map.
- **`engine.py:51`** — THE seam: `try: from automation.video import client` (the EMPTY path) `except:` →
  `fake_engine`. ⚠ **The 1-line fix: `from media_gen.video import client`.** `set_render_fn`/`set_poll_fn`
  allow orchestrator/test injection. `engine_name()` `:100` diagnostic.
- `endpoints.py` — FastAPI `APIRouter(prefix="/creative/video")` DEFINED, **NOT mounted** in caller.py.
- `creative/shared/library.py` — JSON Asset Library under `VAR/creative/assets/` (⚠ NOT the PG `ai_asset_*`).

**LIVE AI-asset service (where images already live) — `droplet_work/ai_asset/` at `10.122.0.4:8310`:**
- `endpoints.py:182` `GET /assets` (list), `:195` `GET /assets/{id}` (versions presigned), `:221`
  `GET /assets/{id}/raw` → **302 to 24h presigned Spaces URL** (`:246` `_spaces.presign(key, expires=86400)`).
  `:317` `/attach`, `:371` `/attach-whatsapp`, `:342` `/variation-from-upload`, `:376` brand-kits.
- `store.py` — `ai_asset_*` PG schema (FORCE-RLS), the canonical library the panel reads.
- nginx (FORTRESS): `/api/assets/` → `10.122.0.4:8310` (⚠ **stale proxy_pass — repoint is FE-box-root-gated**,
  `MASTER_DNA_PLAN §L`).

**FRONTEND — `famit-panel/app/creative/`:**
- `lib/assets.ts:167` `Asset` type (no `duration_s`/`with_audio`/`poster_url`/`media_type`). `AssetQuery:203`.
- `_components/AssetImage.tsx` — `<img>` only (presigned-URL aware, graceful onError). `AssetCard.tsx` —
  uses AssetImage; `Icon name="send"` is silently-empty (no glyph — per AGENT_LEARNINGS, keep as-is).
- `_components/FilterRail.tsx:53` `KIND_OPTS` — banner/image/social/offer/poster/product/logo, **no Video**.
- `_components/LibraryGallery.tsx` — grid/list toggle, status Tabs, NO mediaType/Images↔Videos toggle.
- `_components/AssetDetail.tsx` — slide-over, `Tabs(Details/Versions/Performance)`, `<img>` preview only.

---

## 2. THE PRODUCT (what the 100% version IS) — one paragraph

Vendor opens **Creative Studio ▸ Video Studio**, picks a **campaign**, and either (a) types one instruction
("5 vertical hook reels for hot leads, Hinglish, with my product shot") and watches the AI write **N
distinct-angle ad scripts** → render a **BATCH of variant clips** (the liquid-loading cards morph into real
`<video>` previews), or (b) uploads their own clip (manual path, works with zero gen-key). Most batches
render through the **FFmpeg/Remotion composite tier** (product image + AI script voiceover via Sarvam/EL +
Groq-Whisper burned captions + brand kit) at ~$0.003/clip; a **premium tier** routes to a real gen model
(Kling/Runway/Veo via fal) for AI b-roll/talking-head at ~$0.05–0.30/s, gated by a per-batch cost cap +
human approval. Finished MP4s land in the **same Asset Library** images already live in (one library, an
Images↔Videos toggle), each tagged to its campaign + angle + `ab_group`. From the library or detail drawer
the vendor **attaches a video to a WhatsApp template, to a Meta ad, or to a workflow** — and the winning
clip's `ab_group` + `ai_generated` lineage flows into the **Revenue-Truth Signal Loop** (CAPI), closing
ad→lead→call→WhatsApp→sale→signal. With no creds every surface is dormant (`not_configured`), spends nothing,
never raises — byte-identical resting.

---

## 3. RESEARCH VERDICTS — folded + re-validated (the brief's numbers, my adjudication)

The brief's provider research is **sound and I adopt it**, with these load-bearing additions/corrections. (The
existing `design/creative-video-studio.md §3,§15,RTX` already red-teamed the model claims — I inherit that:
treat every Elo/rank/price as **point-in-time, env-overridable via `VIDEO_ROUTE_*`**, never a guarantee.)

**3a. FFmpeg/Remotion composite is the DEFAULT tier — the brief said it, nobody built it (§6 builds it).**
Real numbers (brief + independent): text-overlay + product-image + voiceover compositing = **$0.002–$0.005/min
via FFmpeg/Remotion** vs Runway Gen-4 Turbo **$0.05/sec** (≈100× dearer). For the founder's actual ad
creative (most ads are NOT AI-generated talking heads — they're product shots + captions + a CTA), the
composite path is the cost-correct default and a **genuine moat** (no competitor ships a $0.003 composite +
$0.30 AI-gen tier under ONE toggle). **AI video gen is the premium lever, not the floor.**

**3b. Provider tiers (env-overridable route map; verify exact fal ids at deploy — they drift monthly):**
| Tier | Engine | Real cost | Use |
|---|---|---|---|
| **COMPOSITE (default)** | self-host FFmpeg/Remotion worker | ~$0.003/clip | product+caption+voiceover ad (the 80% case) |
| **STANDARD AI** | Kling 3.0 / Hailuo via fal | ~$0.029–0.045/s | AI b-roll, motion, batch |
| **PREMIUM AI** | Runway Gen-4 Turbo ($0.05/s, up to 30s) / Veo 3.1 / Seedance 2.0 | $0.05–0.30/s | hero spot, talking-head, premium |
| **SELF-HOST (dormant)** | Wan 2.7 (Apache-2.0) on DO GPU | ~$1.57/hr idle | only at sustained queue (≥30–40 clips/GPU-hr) |
**Gateway = fal.ai** (one key reaches Kling/Hailuo/Veo/Runway/Wan; US-based, PAYG, abstracts China-origin
supply risk behind the provider switcher). **Do NOT integrate** Higgsfield-as-model (it's a UX product),
Sora 2 (India-excluded), Pika (3-5s cap, enterprise-only).

**3c. Audio/caption/script sub-pipeline — reuse the live key pool, ZERO new vendor:**
- **Captions:** Groq Whisper (already in `agent.py` key pool) — ~0.3–0.5s for a 5-min file, cheaper than
  OpenAI Whisper $0.006/min. Output SRT (overlay) + ASS (burned-in, WCAG 2.2 / EAA-2025 compliance).
- **Voiceover:** Sarvam TTS (already in stack) for Hindi/regional default; ElevenLabs v3 (~$0.30/1K) premium.
  Audio quality is the critical path — below a perceptual floor, 15–25% completion-rate drop regardless of
  visuals (so the composite tier MUST use real TTS, not robotic).
- **Script gen:** Gemini Flash (~$0.00015/script, in the free-tier pool) OR the in-house `llm-router` seam —
  100× cheaper than GPT-4o for structured output, same quality. `creative/video_studio/script.py` already
  injects an LLM callable; wire it to llm-router.

**3d. Pipeline/infra (brief verdicts adopted):** **Hatchet** (live on `famit-hatchet`) for the multi-step
durable workflow (script→voiceover→caption→render→compose as ONE saga); NOT for 10K concurrent micro-jobs.
**Storage** DO Spaces today ($0.02/GB, $0.01/GB egress after 500GB free); at scale Cloudflare R2 (egress $0,
Famit already CF-fronted) — egress is 60–90% of the bill, the highest-leverage cost decision. **ABR from day
1** (3-5 rung HLS 1080/720/480/360 cuts egress 20–30%; H.265 saves 25–50% over H.264). **Cost model** (500
videos/mo, composite-only): ~$17–30/mo; +ElevenLabs → ~$90; +Runway per video → ~$800. AI gen is the cost
lever — which is exactly why it's gated behind a cap + approval, and why composite is the default.

---

## 4. ARCHITECTURE — the two-engine reuse + the live-library bridge (the decision)

```
                         ┌─────────────────────────────────────────────────────────────┐
  FRONTEND (famit-panel) │  app/creative/video/page.tsx  (Studio sub-page)             │
                         │  + Images↔Videos toggle in LibraryGallery + <video> in cards │
                         └───────────────┬──────────────────────────┬──────────────────┘
                                         │ POST /creative/video/*    │ GET /api/assets?media_type=video
                                         ▼                           ▼
  CALLER.PY (:8209)  ┌── creative.video_studio.endpoints (UPPER) ──┐  ┌── ai_asset (:8310, LIVE) ──┐
  flag FEATURE_VIDEO_STUDIO │ propose/approve/collect/list/promote │  │ GET /assets (media_type) │
                         └──────────────┬───────────────────────────┘  │ GET /assets/{id}/raw 302 │
                                        │ render_fn = media_gen.video.client.submit_video_job   │ presigned │
       flag FEATURE_MEDIA (already mounted, default OFF)               └────────┬──────────────────┘
                                        ▼                                       │ register_asset(kind=video)
  MEDIA_GEN (LOWER engine) ┌── media_gen.video.client ──┐   ┌── media_gen.compose (NEW §6) ──┐
                           │ providers: fal/replicate/  │   │ FFmpeg/Remotion worker:        │
                           │  luma/higgsfield/selfhost  │   │ product+TTS(Sarvam/EL)+Whisper │
                           │ + webhook sig-verify       │   │  captions+brandkit → MP4+ABR   │
                           └────────┬───────────────────┘   └────────┬───────────────────────┘
                                    └──────────────┬──────────────────┘
                                                   ▼ artifact → DO Spaces (media_gen.spaces)
                                  ┌── HATCHET saga (durable multi-step) ──┐
                                  │ script→voiceover→caption→render→compose│
                                  └────────────────────────────────────────┘
```

**The load-bearing architectural decision (the brief MISSED this):** the upper studio currently registers
assets into `creative/shared/library.py` (a JSON store under `VAR/creative/`). But the founder's live Asset
Library frontend reads the **`ai_asset_*` PG service at `:8310`**. **If we ship the studio as-is, generated
videos would NOT appear in the library the founder uses** — a silent dead-end. ⇒ **The studio's
`collect_batch` (on a finished render) must call the AI-asset service's `register_asset(kind="video", …)`
seam (a new thin internal endpoint), NOT only the JSON library.** One library, both media types. This is the
single most important integration choice and it is additive (the JSON library stays as the dormant/offline
fallback for the upper engine's own tests).

**Why two engines, not one fat module (settled):** the lower engine is reusable by image/3D + is
dollar/webhook-heavy infra; the upper studio is product UX + batch logic + the revenue loop. They couple at
exactly ONE seam (`engine.py` render_fn/poll_fn). This is already the codebase's chosen shape — we keep it.

---

## 5. THE LIVE-LIBRARY BRIDGE — make a generated video appear where images do (the missed integration)

**Problem:** `lib/assets.ts` Asset has `kind?: string` and the library reads `GET /api/assets`. A video must
be a first-class Asset there. **Solution (additive, RLS-scoped):**

1. **Extend the `ai_asset_*` asset row** with video columns (`media_type`, `duration_s`, `with_audio`,
   `poster_url`, `outputs JSONB` for the ABR ladder, `ab_group`) — §7 schema. A `media_type='image'` default
   keeps every existing row + the resting frontend byte-identical.
2. **New internal seam on the AI-asset service:** `register_video_asset(tenant, campaign_id, batch_id, angle,
   spaces_key, poster_key, duration_s, with_audio, model, ab_group)` → writes one `ai_asset` row with
   `media_type='video'`, presign-on-read (mirrors `/assets/{id}/raw:246`). Called by the studio's
   `collect_batch` over the VPC loopback (`AIASSET_LOOPBACK_BASE=http://10.122.0.4:8310`, the SAME base the
   AI-Manager already uses — `MASTER_DNA_PLAN §K`), authed with a minted `run_token` (the same pattern AIM
   uses to avoid the 401 the brief's sibling spec hit).
3. **`GET /assets` gains `media_type` filter** (`?media_type=video|image|all`, default `all` for back-compat).
4. **`/assets/{id}/raw` already 302-presigns** — works for MP4 unchanged (it presigns any key). For the
   **poster** (thumbnail), add `/assets/{id}/poster` → 302-presign the `poster_url` key. **No new presign
   table** (the brief's `video_presigned_cache` is unnecessary — re-signing is ~1ms; if cached, use Redis
   :6380 with TTL 3600 < the 86400 signed lifetime, never PG).

**Earner-safety:** the AI-asset service is a SEPARATE box-process (`:8310`), NOT the earner. Adding a column +
an internal route there never touches `agent.py`/the dial loop. The studio→AIasset call is VPC-internal,
flag-gated, best-effort (a failure leaves the asset in the JSON fallback + logs, never breaks a batch).

---

## 6. THE FFMPEG/REMOTION COMPOSITE TIER — the cheap default (biggest lever, unbuilt)

**Why this is the most important new build:** the brief's own research says composite is 100× cheaper and the
single white-space differentiator (nobody ships composite + AI-gen under one toggle). Today neither engine has
it. **Design:**

**New provider in the lower engine: `media_gen/video/compose.py` + `provider="compose"` in `providers.py`.**
It is a LOCAL render (no external API key) so it works the moment FFmpeg is on the box — **the composite tier
is NOT dormant-on-creds, it's the always-available floor** (huge: the founder can ship video WITHOUT any
gen-API key, exactly the "manual path works without a key" requirement, extended to AI-composited ads).

**Composite pipeline (one Hatchet saga, durable):**
1. **Script** (llm-router/Gemini-Flash) → N angle scripts (reuse `video_studio/script.py`).
2. **Voiceover** → Sarvam TTS (Hindi/regional) or EL (premium) → WAV in Spaces. Reuse the live key pool.
3. **Captions** → Groq Whisper on the voiceover → SRT + ASS (burned, WCAG/EAA). Reuse the pool.
4. **Visual track** → the product image(s) from the campaign/brand-kit (Ken-Burns pan/zoom) OR an uploaded
   clip OR (premium) an AI b-roll clip from the gen tier; brand logo + colour overlay from the brand-kit.
5. **Compose** → FFmpeg filtergraph: scale to aspect (9:16/1:1/16:9) → overlay captions (ASS) → mux voiceover
   → brand watermark → **ABR ladder** (HLS 1080/720/480/360, H.265) → MP4 + poster frame → Spaces.
6. **Register** → the live-library bridge (§5).

**Compute siting:** FFmpeg is CPU-light for composite (no GPU). Run it as a **Hatchet worker** on the
`famit-hatchet` box (or a small dedicated worker) — NEVER on the earner box (`168.144.153.145`) and NEVER
in-process in caller.py (a 30s render would block the event loop). The render is async by construction.

**⚠ COST-TRUTH (red-team #2 — the "$0.003/clip" headline is a LIE if it omits its inputs):** composite is
**$0 gen-API**, but it is NOT free — it pays real TTS + Whisper + worker-seconds. A 30s script ≈ 400 chars;
**ElevenLabs at $0.30/1K chars = $0.12/clip in TTS alone (40× the "$0.003" claim)**; a 5-variant ×
3-language fan-out on EL = ~$1.80 on one "free" batch, silently. So:
- **Sarvam is the ONLY default TTS** (in-stack, cheap, Hindi/regional). **ElevenLabs is gated EXACTLY like a
  paid gen-provider**: default OFF, explicit per-batch opt-in, and the FIRST EL render obeys the 1-paid-test
  rule (`VIDEO_STUDIO_BATCH_SIZE=1`, founder-signed).
- **Multilingual fan-out (`video_scripts.lang`) MUST NOT auto-multiply paid TTS.** Language fan-out defaults
  to Sarvam only; EL-per-language is an explicit, capped, per-language opt-in.
- **The cost meter is a HARD PRE-FAN-OUT WALLET HOLD**, not a post-hoc tally: composite spend = Sarvam/EL
  chars + Whisper minutes + worker-seconds, estimated and **held on the wallet BEFORE fan-out** (mirroring
  `client.py`'s reserve-hold), metered onto the SAME `usage_events.json`/ledger as Groq/EL/Vobiz (so
  cost-per-lead includes creative). Settle at actual on finalize.
- **Re-label every "$0.003/clip / ≈free" string** in the UI + plan to **"$0 gen-API + metered TTS/Whisper"**
  so the founder is never surprised by an EL bill on a "free" batch.

**Acceptance:** a composite batch with NO gen-API key + Sarvam TTS renders 5 real MP4s offline-of-fal
(product+TTS+caption), takes a pre-fan-out wallet hold ≥ estimate, registers them as video assets, settles
~₹0.25/clip. EL selection forces `BATCH_SIZE=1` + founder-sign on first use. This is the "video without
burning a paid gen key" win — with the TTS cost metered honestly, not hidden.

---

## 7. DATABASE SCHEMA — additive, RLS-scoped, presign-on-read (no `video_presigned_cache` table)

**Decision:** the lower engine + studio are JSON-file backed today. For production (multi-box durability,
analytics, RLS, the live-library bridge) the video state belongs in PG, FORCE-RLS, in the `ai_asset_*` schema
family (so it's ONE library). **Keep JSON as the dormant offline-test fallback for the upper engine.**

**Extend the existing `ai_asset` asset row (additive columns, default-safe):**
```sql
ALTER TABLE ai_asset ADD COLUMN IF NOT EXISTS media_type  text NOT NULL DEFAULT 'image';  -- image|video
ALTER TABLE ai_asset ADD COLUMN IF NOT EXISTS duration_s   numeric;                         -- video only
ALTER TABLE ai_asset ADD COLUMN IF NOT EXISTS with_audio   boolean;
ALTER TABLE ai_asset ADD COLUMN IF NOT EXISTS poster_key   text;                            -- thumbnail Spaces key
ALTER TABLE ai_asset ADD COLUMN IF NOT EXISTS outputs      jsonb DEFAULT '[]'::jsonb;       -- ABR rungs [{rung,key,bitrate}]
ALTER TABLE ai_asset ADD COLUMN IF NOT EXISTS ab_group     text;                            -- Signal-Loop lineage
-- existing RLS policy on ai_asset already covers these (same row); no new policy needed.
```
**New `video_jobs` (durable render job — additive, FORCE-RLS):**
```sql
CREATE TABLE IF NOT EXISTS video_jobs (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id     uuid NOT NULL,
  asset_id      uuid,                    -- FK ai_asset once succeeded
  batch_id      text,                    -- studio batch grouping
  job_type      text NOT NULL,           -- compose|gen|caption|voiceover
  provider      text,                    -- compose|fal|replicate|...
  status        text NOT NULL DEFAULT 'queued',  -- queued|running|succeeded|failed|cancelled
  params        jsonb DEFAULT '{}'::jsonb,
  result        jsonb DEFAULT '{}'::jsonb,
  progress      int  DEFAULT 0,
  attempts      int  DEFAULT 0,
  estimated_cost_minor int,             -- INTEGER PAISE, never float (founder law)
  actual_cost_minor    int,
  hold_id       text,                    -- wallet hold linkage
  error         text,
  created_at    timestamptz DEFAULT now(),
  updated_at    timestamptz DEFAULT now()
);
ALTER TABLE video_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE video_jobs FORCE ROW LEVEL SECURITY;
CREATE POLICY video_jobs_iso ON video_jobs USING (tenant_id = current_setting('app.tenant_id')::uuid);
-- admin escape via SET LOCAL app.is_admin='1' GUC (the platform pattern), same as wallet/ai_asset.
```
**New `video_scripts` (the AI ad-script + variant lineage — additive, FORCE-RLS):**
```sql
CREATE TABLE IF NOT EXISTS video_scripts (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id    uuid NOT NULL,
  asset_id     uuid, batch_id text,
  variant_key  text,                     -- angle: pain_point|social_proof|offer_led|urgency|founder_voice
  lang         text NOT NULL DEFAULT 'auto',  -- en|hi|hinglish|ta|… localization fan-out (Sarvam default)
  brief        jsonb,                    -- the VideoBrief
  script       jsonb,                    -- hook/script/caption/cta/lang (ScriptVariant)
  voiceover_key text, caption_key text, render_key text,
  tts_provider text DEFAULT 'sarvam',    -- sarvam (default/free-of-EL) | elevenlabs (paid, gated)
  ab_group     text,
  created_at   timestamptz DEFAULT now()
);
ALTER TABLE video_scripts ENABLE ROW LEVEL SECURITY;
ALTER TABLE video_scripts FORCE ROW LEVEL SECURITY;
CREATE POLICY video_scripts_iso ON video_scripts USING (tenant_id = current_setting('app.tenant_id')::uuid);
```
**Rules honored:** `tenant_id` ALWAYS from JWT (`caller.py:404` / AI-asset `auth.py`), never body; INTEGER
PAISE never float; FORCE-RLS + zero-`%` DDL; idempotent `IF NOT EXISTS` (manual apply, dual-mirror-safe);
admin via GUC. **NO `video_presigned_cache` table** — presign-on-read (§5). All migrations applied manually
on live PG (the platform pattern), behind the flag, never auto-run.

---

## 8. ENDPOINTS — what mounts, the flags, the order

**Already mounted (lower engine):** `media_gen.router.build_router` under `FEATURE_MEDIA` (caller.py:6968) —
`POST /media/video/jobs`, `/jobs/{id}/poll|approve|reject|cancel`, `/webhook`, `GET /media/status`. ✅ no work.

**To mount (upper studio) — NEW flag `FEATURE_VIDEO_STUDIO` (default OFF, byte-identical resting):**
| Method + path | Role | Behavior |
|---|---|---|
| `GET  /creative/video/campaigns` | read | dropdown source (binds spine `list_campaigns`) |
| `POST /creative/video/batches` | write | propose: scripts→briefs→cost-gate→approval-park OR fan-out. `not_configured` when no creds. |
| `GET  /creative/video/batches[/{id}]` | read | list / one batch incl. per-job status + asset links |
| `POST /creative/video/batches/{id}/approve|reject|cancel` | manager+ | approval gate (fan-out / release hold) |
| `POST /creative/video/collect/{id}` | read | idempotent poll → register finished → **live-library bridge (§5)** |
| `GET  /creative/video/assets` | read | studio's view (proxies `GET /assets?media_type=video`) |
| `POST /creative/video/assets/{id}/promote` | write | winner/paused/trashed |

**To mount (live-library bridge, on the AI-asset `:8310` service — NOT caller.py):** `POST
/assets/_internal/register-video` (VPC-only, run_token authed); `GET /assets?media_type=`; `GET
/assets/{id}/poster`. Flag `FEATURE_VIDEO_LIBRARY`.

**Mount fix prerequisite:** `creative/video_studio/engine.py:51` → `from media_gen.video import client` (the
1-line seam fix) so the upper studio drives the REAL lower engine, not the empty `automation.video`.

**Flag matrix (all default OFF → resting byte-identical, the platform invariant):**
`FEATURE_MEDIA` (lower engine, mounted) · `FEATURE_VIDEO_STUDIO` (upper orchestrator) · `FEATURE_VIDEO_LIBRARY`
(PG bridge) · `FEATURE_VIDEO_COMPOSE` (FFmpeg tier) · per-provider creds (`FAL_KEY` etc.).

---

## 9. SIGNAL-LOOP EXPORT — `ab_group` + `ai_generated` lineage into CAPI (the moat, missed)

Every studio asset is **100% AI-generated** and is a **node in the revenue loop** — but today no field carries
that into the ads/CAPI path. **Folded fixes (from the existing video spec RTX-2, now schema-backed):**
- **`media_type='video'` rows carry `ab_group`** (the variant/angle test group) + `meta.ai_generated=true` +
  optional `meta.disclosure_required_region[]` (Meta/Google now REQUIRE AI-content disclosure in multiple
  jurisdictions — set the platform AI-content flag at launch, or eat an ad rejection).
- The **Ads handoff** reads `ai_generated` → sets the platform disclosure flag; reads `ab_group` → the
  experiment runner launches variants at small budgets, auto-scales winners / pauses losers (platform-native
  auto-bidding + deterministic rules under a HARD cap, PAUSED-by-default human approval — `automation-ads.md`
  INVARIANT A/B; **no black-box agent moves spend**).
- The **winning clip's `ab_group`** + the resulting booking/sale flow into **CAPI as a quality-weighted
  conversion event** — closing ad→lead→call→WhatsApp→sale→signal with the creative attributed. This is the
  Revenue-Truth Signal Loop the whole product is built on; the Video Studio feeds it the creatives.

---

## 9b. VIDEO STUDIO AS THE FIRST CONSUMER OF THE UNIVERSAL PROVIDER FRAMEWORK (the founder's #1 ask)

> Companion plan: `design/PROVIDER-FRAMEWORK-PLAN.md` (the universal flexible provider/connector registry).
> Video Studio is its **FIRST consumer** — designed so the SAME registry later serves the voice LLM router,
> RAG, the image studio, the WhatsApp AI connector, and any future tool. This is the founder's explicit
> "add ANY hosted model + key / SELF-HOST any model / connect ANY tool, entirely via the UI" mandate. Video
> consumes it; the framework is the load-bearing layer.

**How Video resolves a provider (the seam):** every render — composite, hosted-gen, or self-hosted — asks the
registry, NOT a hardcoded env switch:
```python
client = registry.get_provider(tenant_id, capability='video_gen', routing_hint=tier)  # tier ∈ {composite, ai_motion, premium}
# registry resolves the enabled provider for THIS tenant + capability, fetches the key via the Vault
# get_secret() seam, applies the field-map adapter, handles fallback/circuit-breaker, returns a ready client.
```
The cut-over is **F5 in the framework plan** (`REGISTRY_FOR_VIDEO`): `media_gen/video/client._resolve_key`
(today a hardcoded `if provider=='fal': config.fal_key(...)` switch, `client.py:304-318`) is rewired to ask
the registry first and fall back to the legacy `config.*_key(tenant_id)` env path on a miss — byte-identical
render proven both ways. **The `compose` provider needs no key** (local FFmpeg render), so it works whether or
not the registry is populated — the always-available floor.

**What the registry gives Video that the brief's "add a key" wish only gestured at:**
- **Add ANY hosted gen model via the UI** — a super-admin/vendor registers `fal`/`runway`/`veo`/`kling` (or a
  brand-new vendor) as a `provider_definition` with `capability=['video_gen']`, pastes the key (encrypted at
  rest, AAD-bound, masked-only/reveal-gated by `scope`), and it is live for video with no code deploy. The
  existing `media_gen/video/providers.build_submit/parse_result` builders are registered as the
  `named_provider` transforms — they are NOT thrown away, they ARE the fal/replicate/luma adapters.
- **SELF-HOST any model and point to its endpoint** — register a `self_hosted` provider (Wan2.1 on a DO GPU via
  ComfyUI `/prompt`→`/history`→`/view`, or an LTX/Mochi node, or a custom FastAPI `/generate`) with the
  SSRF-guarded `base_url`; the registry's per-type presets supply the readiness + capability probe
  (`/object_info/{node_class}`) so "Test connection" just works. This is the founder's self-host requirement,
  delivered for video, reusable for image/LLM.
- **Connect ANY future tool** — the `custom_field_map` (Tier 3 JSONPath) lets a vendor wire an unknown
  video/audio/tool API entirely from the UI FieldMapper, no code deploy. Video Studio is the first proof; the
  next consumer (e.g. a music-generation tool for §13b-H4, or a captioning vendor) plugs in by declaring a
  capability.
- **Per-tenant BYO-key, securely** — §10d's "Video provider keys" card becomes a thin view over the framework's
  `scope='integration'` credentials: a vendor brings their own FAL/Runway budget, can reveal/rotate THEIR key
  (PIN step-up), but can NEVER reveal a platform key (`scope='ai_provider'` → masked-only). This replaces the
  interim ad-hoc Fernet switcher CRUD with the unified, audited registry.

**Sequencing:** the framework's F1–F4 (DDL + package + SSRF + adapter + mount) land BEFORE Video's U9
(BYO-key). Until then Video uses its existing env/`config.py` key path (the legacy fallback the strangler
preserves) — so Video Studio's composite + manual-upload + env-keyed hosted-gen all ship WITHOUT waiting on
the framework, and the framework upgrades Video's key story in-place when it lands. Earner-safe: video is async
(adds ZERO to the voice loop); the registry rides caller.py / the AI-asset service, never agent.py. The ONE
latency-sensitive consumer (the voice LLM router) is cut over LAST and cache-first (framework F6), never on the
video path.

**Acceptance addendum (folds into §11):** a hosted-gen video renders via `registry.get_provider(...)` with the
key resolved through the seam (never a raw env read in the render path); a self-hosted ComfyUI provider passes
the SSRF guard + sandbox health-probe before it can serve; a vendor reveals THEIR fal key (step-up) but a
platform key reveal → 403; with `REGISTRY_FOR_VIDEO=0` the legacy env path renders byte-identically.

---

## 10. FRONTEND — the crazy Video Studio UI (decision-ready component map, Core_2 + Inter Display, zero hex)

**Iron rule (founder, repeated):** PORT Core_2 components, don't approximate. One heading via `<Layout
title>`, every section a `Card`, Inter Display, semantic tokens only, zero raw hex, real loading/empty/error.

### 10a. New page — `app/creative/video/page.tsx` (`<Layout title="Video Studio">`)
Two-column `HomePage` grammar (col-left ~66% / col-right ~33%), mirrors the existing `app/creative/page.tsx`:
```
COL-LEFT                                              COL-RIGHT
┌ Card "Create video" (hero command) ──────────────┐ ┌ Card "Campaign context" ───────┐
│ Campaign Select │ Tier Tabs (Composite·AI·Premium)│ │ business·product·offer·audience │
│ Aspect Tabs (9:16·1:1·16:9) │ count Stepper        │ │ brand chips · "AI will use this"│
│ command box (Field textarea, big)                  │ └─────────────────────────────────┘
│ [Upload your clip ▸] [Generate batch ▸ isBlack]    │ ┌ Card "Recent videos" ──────────┐
│ est: "≈ 5 clips · ₹1.25 · composite"  (cost meter) │ │ mini <video> grid → Library     │
└────────────────────────────────────────────────────┘ └─────────────────────────────────┘
┌ Card "Generation" (queue + variant grid) ─────────────────────────────────────────────┐
│ liquid skeleton cards → morph in place → <video poster controls> variant cards          │
│ head: "3 of 5 ready · ₹0.75 spent" + Tabs(All·Approved·Drafts) + sort Select             │
└──────────────────────────────────────────────────────────────────────────────────────────┘
```
**Tier Tabs** is the key new control (the composite-vs-AI toggle no competitor has): **Composite (default,
"₹0.25/clip, no key needed")** · **AI motion (Kling/Hailuo)** · **Premium (Runway/Veo, approval-gated)**.
Advanced (model id, duration, voiceover voice, caption on/off, BYO-key) hides under a `Dropdown`.

### 10b. Component changes (exact files)
| File | Change | Why |
|---|---|---|
| `lib/assets.ts:167` | extend `Asset`: `media_type?: "image"\|"video"`, `duration_s?: number`, `with_audio?: boolean`, `poster_url?: string`, `outputs?: {rung:string;url:string}[]`, `ab_group?: string` | first-class video record |
| `lib/assets.ts:203` `AssetQuery` | add `media_type?: string` | filter videos |
| `_components/AssetImage.tsx` → split into `AssetMedia.tsx` | detect `asset.media_type==="video"` → render `<video src={presigned} poster={poster_url} controls preload="none" playsInline>`; else the existing `<img>`. Keep the graceful onError + shimmer. **`preload="none"`** so a grid of videos doesn't fetch every clip (egress!). | the `<video>` gap |
| `_components/AssetCard.tsx:107` | use `AssetMedia` instead of `AssetImage`; add a duration pill (`0:06`) + a play-glyph overlay on the poster | video tiles |
| `_components/AssetDetail.tsx:26` | `<video controls>` in the preview slot when `media_type==="video"`; add a "Captions/Voiceover" detail row | video detail |
| `_components/FilterRail.tsx:53` `KIND_OPTS` | add `{ id: 8, name: "Video" }` | filter facet |
| `_components/LibraryGallery.tsx` | add `mediaType` state + an **Images↔Videos segmented toggle** in the head (binary `Tabs`), pass `media_type` into the query | the one-library toggle (the differentiator) |
| `contstants/navigation.tsx` | add "Video Studio" child under Creative Studio (`/creative/video`) | nav |
| `app/creative/video/_components/*` | `TierTabs`, `BatchProgress` (reuse `GenerationQueue` + `CreativeSkeleton` liquid state), `UploadClip` (FieldImage → multipart) | studio surface |

### 10c. Reused verbatim (no new component except the above)
`Card`, `Tabs`, `Select`, `Field`, `Button`, `GridProduct`-grammar (AssetCard), `Filters`, `Search`, `Modal
isSlidePanel`, `Badge`, `NoFound`, `Spinner`, `CardChartPie`, `FieldImage`, `Dropdown`, the existing
`CreativeSkeleton` liquid-loading animation (S4), `CampaignContext`, `GenerationQueue`. **WhatsApp/Ads
attach** reuse the existing `UsePicker` + `attach-whatsapp` (`ai_asset/endpoints.py:371`) — a video attaches
the same way an image does.

### 10d. BYO-key entry (founder-named, sellable) — now a view over the Universal Provider Framework
A super-admin/vendor **"Video provider keys"** card. **This is a thin, video-scoped view over the universal
provider registry** (`design/PROVIDER-FRAMEWORK-PLAN.md` — `app/settings/byo-keys`, capability=`video_gen`):
paste `FAL_KEY`/`RUNWAY_KEY` per tenant, **encrypted at rest (AAD-bound AES-256-GCM via the Vault `get_secret`
seam)**, `scope='integration'` so a vendor reveals/rotates THEIR key (PIN step-up) but never a platform key.
A super-admin can also **add ANY hosted gen model, SELF-HOST a model (SSRF-guarded base_url + sandbox probe),
or wire a future tool via the visual FieldMapper** — all from the framework UI, no code deploy (§9b). The
composite tier needs no key. Legacy-pw → 403 (control-security). **Interim (pre-framework):** the existing
Fernet switcher CRUD (`MASTER_DNA_PLAN §J`) is the fallback the strangler preserves until framework F1–F4 land,
then this card upgrades in-place to the registry — Video Studio's keyed-gen ships without blocking on it.

---

## 11. FLAG / ACCEPTANCE / ROLLBACK

**Flags (all default OFF — resting byte-identical, the platform invariant):**
`FEATURE_MEDIA` (lower, already mounted) · `FEATURE_VIDEO_STUDIO` (upper) · `FEATURE_VIDEO_LIBRARY` (PG bridge)
· `FEATURE_VIDEO_COMPOSE` (FFmpeg tier) · `FAL_KEY`/`RUNWAY_KEY`/`SPACES_*` (provider creds).

**Acceptance (each unit, offline-first then live):**
1. **Resting byte-identical:** all flags OFF → caller.py route table + render identical; golden
   `verify_golden.py` exit 0; earner gate (md5/PID/health/0-5xx) before+after.
2. **Lower engine (already built):** 19 offline tests green; `media_gen.video.client` `not_configured` with no
   `FAL_KEY` (zero network).
3. **Seam fix:** `engine.py` `engine_name()` returns `media_gen.video.client` (not `fake_engine`) when
   configured + the import repointed; offline still falls back to `fake_engine`.
4. **Upper studio:** `propose_batch`→`approve`→`collect` end-to-end on the fake engine (5 scripts, 5 briefs,
   cost gate, hold, 5 assets, complete) — the existing 19 tests + the new bridge stub.
5. **Composite tier:** a composite batch with NO gen-key renders 5 real MP4s (product+TTS+Whisper-caption) on
   the Hatchet worker, registers as video assets, settles ~₹0.25/clip, ABR ladder present.
6. **Live-library bridge:** a finished video appears in `GET /assets?media_type=video`; `/raw` 302-presigns
   the MP4; cross-tenant isolation probe (tenant A can't read B's video) PASS (RLS).
7. **Frontend:** Images↔Videos toggle filters; `<video>` renders with poster+controls; `preload="none"`
   (network tab shows posters only, not every clip); reduced-motion safe; dark mode; `tsc --noEmit` exit 0 +
   `npm run build` exit 0; gitleaks staged 0.
8. **Signal-Loop:** `ab_group` + `ai_generated` present on the row; Ads handoff reads them (stub until OAuth).
9. **Cost-truth gate (H1/H2):** a fal/EL first-render is FORCED to `BATCH_SIZE=1`+`duration_s≤6`+`AUTO_APPROVE=0`
   + a wallet hold ≥ estimate (refuses otherwise); a Sarvam-only composite batch is NOT gated; the
   per-tenant `VIDEO_DAILY_CAP_USD` blocks tenant A without touching tenant B's ceiling; EL on a "free"
   composite batch surfaces the metered TTS cost pre-fan-out (no silent EL bill).
10. **Reaper (H5):** kill the worker mid-saga → the reaper releases the stale hold + reconciles the
    provider-side completion against `video_jobs` (no locked money, no lost paid render); idempotent re-submit
    charges once.
11. **Output-moderation (H3):** a brief that yields a flagged frame → asset lands in `moderation_status='blocked'`
    quarantine, never auto-published; person/founder-voice render requires human review.
12. **Destination-spec (H6):** a 90s clip → WhatsApp-status attach is rejected with a clear spec error, not a
    silent platform failure.

**Rollback:** flags → 0 (instant, no deploy needed — resting is byte-identical). The PG columns are additive
(`media_type` defaults `image`) so a rollback leaves existing image rows untouched. The composite worker is a
separate process — stop it without touching caller.py/agent.py. Backups per the FORTRESS recipe before any
box write.

---

## 12. FOUNDER-UNNAMED FEATURES I'm adding (the 100% he didn't sketch)

1. **The FFmpeg/Remotion composite tier as the DEFAULT** — video WITHOUT a paid gen-key, $0.003/clip (§6).
   *The single biggest cost + differentiation lever; he only named "add a key."*
2. **One library, Images↔Videos toggle** (the white-space no competitor ships) — videos appear where images
   already do, via the live-library bridge (§5), not a separate JSON dead-end.
3. **Real TTS voiceover (Sarvam Hindi/regional + EL premium) + Groq-Whisper burned captions (WCAG/EAA)** —
   reusing the live key pool, zero new vendor; audio quality is the completion-rate critical path.
4. **ABR/HLS ladder + H.265 from day 1** — cuts egress 20–50% (egress is 60–90% of the bill).
5. **PG + FORCE-RLS schema** (not JSON files) — multi-tenant isolation, durability, analytics.
6. **Signal-Loop lineage** (`ab_group`/`ai_generated`/disclosure-region) into CAPI — the actual moat.
7. **Video as the FIRST consumer of the Universal Provider Framework** (§9b, `PROVIDER-FRAMEWORK-PLAN.md`) —
   add ANY hosted model + key / SELF-HOST any model (SSRF-guarded) / connect ANY future tool, entirely via the
   UI, no code deploy; per-tenant BYO-key (AAD-encrypted, reveal-gated, scope-policed). The founder's #1 ask,
   delivered as a reusable layer (the voice LLM router, RAG, image studio all plug in next by capability).
8. **Hatchet durable saga** (script→VO→caption→render→compose) — a killed worker resumes, never a half-render.
9. **Cost meter on the same ledger** — cost-per-lead now includes creative spend (Billing Meter parity).
10. **Manual-upload path + AI-composite of the upload** — works with zero gen-key, the dormant-safe floor.
11. **Likeness/consent gate already in the engine** (`safety.likeness_gate`) — surfaced in the UI as a
    consent checkbox on person-image/founder-voice briefs (legal exposure on a shared key).

---

## 13. RISKS (honest)

- **R1 — Stale-brief churn.** The biggest risk is re-doing the 3 already-done items (router mount, engine
  import line, presign table). §0 is the guard: verify on disk first.
- **R2 — The live-library bridge is the integration linchpin.** If skipped, generated videos silently never
  appear in the founder's library → a "looks done, doesn't work" failure (the exact class the founder hates).
  Build §5 FIRST after the seam fix; verify a real video shows in `GET /assets?media_type=video`.
- **R3 — Composite worker siting.** Must NOT run in caller.py (blocks the loop) or on the earner box. Hatchet
  worker on `famit-hatchet` (or a small dedicated box — DO limit is 3/3 full, so reuse the hatchet box's
  spare CPU or queue on it). FFmpeg is CPU-only for composite (no GPU needed).
- **R4 — Egress cost.** A grid of autoplaying videos would blow egress. `preload="none"` + poster-only grid +
  ABR + (at scale) R2 are mandatory, not optional.
- **R5 — Provider id/price drift.** Every model id/price is point-in-time; the `VIDEO_ROUTE_*` env map makes a
  re-rank a one-string change. Re-verify fal ids at deploy.
- **R6 — Shared gen-key blast radius.** One `FAL_KEY` fronts all tenants; a non-consented face render can
  suspend the account for all. The likeness gate (§12.11) + per-tenant BYO-key (§10d) are the structural fix.
- **R7 — AI-disclosure compliance.** Meta/Google require AI-content disclosure; the `ai_generated` flag must
  ride the Ads handoff or an ad gets rejected (or worse, a regulator notice). §9.

---

## 13b. RED-TEAM HARDENING — the production layers the happy-path design missed (folded, mandatory)

The cost / completeness red-teams confirmed the design is earner-safe + RLS-correct, but flagged a class of
**lifecycle / compliance / spend-guardrail / cross-product-seam** gaps. These are NOT optional polish — a
buyer's security/procurement review probes exactly these. Each below is a roadmap item, baked into §14.

**H1 — ONE coded 1-paid-test choke-point (cost #3, replaces 3 scattered env vars).** Today the caps live
across `cost.py:113`, `shared/cost.py:94`, and three env vars; the 1-test rule is PROSE, not code. **Build a
single `submit_gate(tenant, brief)` choke-point** every render passes through: *if provider ∉
{compose, selfhost} AND `with_audio` uses a paid TTS, AND the tenant has NEVER had an approved paid render of
that class → force `BATCH_SIZE=1`, `duration_s≤6`, `AUTO_APPROVE=0`, and refuse unless a wallet hold ≥
estimate exists.* Applies uniformly to: first AI-gen clip, first ElevenLabs voiceover. `composite` is the
LITERAL default route so the expensive path is never the fallback.

**H2 — `VIDEO_DAILY_CAP_USD` is PER-TENANT, not global (cost #3).** A single global ceiling lets one tenant
drain it and starve every other tenant. The cap (default $20/day) is keyed per-tenant; a per-tenant
concurrent-render limit + a fair queue on the Hatchet worker stops a 50-clip batch starving neighbours
(completeness **C4**).

**H3 — OUTPUT-side moderation gate (completeness C1).** The engine screens the INPUT brief (`safety.screen`
AUP + likeness), but a clean prompt can still yield an off-brand / NSFW / defamatory / competitor-logo'd
frame → on a shared `FAL_KEY` that suspends the account for ALL tenants (R6 blast-radius, unmitigated on
output). **Add an output-side pass before `register_video_asset`:** sample N frames → a vision-model /
provider safety-webhook check; person/founder-voice renders require human review. Block → quarantine state,
never auto-publish.

**H4 — Music licensing / audio-rights (completeness C2).** Real ad creative needs background music; a
copyrighted track → DMCA/Meta takedown. Ship a **royalty-free/licensed music library** (or "BYO licensed
track + attestation" gate), and record the track's licence in the asset provenance for the disclosure path.

**H5 — Orphaned-hold + lost-render REAPER (completeness C3).** The saga reserves a wallet hold then renders;
if the worker dies after the provider POST but before settle → orphaned hold (tenant's money locked) + a
possibly-completed provider render nobody collected (paid-for, lost). Wallet/Vault have TTL sweeps; Video must
too. **A periodic reaper releases stale holds + reconciles provider-side completions against `video_jobs`**
(`video_jobs.attempts`/`updated_at` drive the sweep). Idempotency on submit already prevents double-charge;
the reaper closes the orphan-spend hole.

**H6 — Destination-spec validation (completeness C5).** Meta Reels / WhatsApp status / YouTube each have hard
duration/aspect/codec/size limits. A 90s clip attached to a 60s-max WhatsApp status = silent attach failure.
**A destination-spec validator at the attach seam** (`/attach`, `/attach-whatsapp`) rejects a non-conformant
clip with a clear error before the platform call.

**H7 — Storage lifecycle on dead variants (completeness C6).** Each batch = 5 variants × 4 ABR rungs × poster
≈ 25 Spaces objects; losers are never deleted → storage cost compounds. **A Spaces lifecycle rule
auto-expires non-promoted variants after N days** (keep only the winner + source script). Combined with the
storage-writer abstraction (do the `media_gen/spaces.py` R2 seam in V1 even though the bucket stays Spaces —
cost #5 — so the R2 egress-$0 cutover is a config flip, not a migration).

**H8 — Dense-embed / GPU discipline is N/A here but the FREE-DEFAULT law is enforced (cost #1/#4/#5).** Video
adds no embedder; the law it must honor: **composite default, Sarvam-TTS default, every paid provider
(fal/Runway/Veo/EL) OFF until an explicit founder-signed flip — the expensive path is NEVER the fallback.**
The +grounding-token tax is a RAG concern, not video; video adds ZERO to the voice loop (async by
construction).

**H9 — Alerts on the NEW failure modes (completeness E1).** The founder is non-technical and won't watch
dashboards. Wire the existing PushNotification / WhatsApp-alert path to the 3 truly-urgent video conditions:
(a) a stuck render holding money > T, (b) an output-moderation block, (c) daily-cap hit. Badges alone are
insufficient.

**H10 — Cross-product seam discipline (completeness A1/A2/A3 + E2/E3/E4).** Video, RAG, and Vault all edit
`caller.py` + the entitlement `registry.json` + nav. **Hard rules:** (i) only ONE of {RAG, Vault, Video}
touches `caller.py` at a time — serialize via the ORCHESTRATOR `caller.py` mount-order ledger; (ii) a
consolidated registry-seed with a reserved `sort_order` block (Video's Creative-child + `FEATURE_VIDEO_*`
must not collide with `mod.knowledge:18-21` / `vault.secrets`); (iii) Video's BYO-key (§10d) should consume
the **Vault read-seam `vault.get_secret(...)`** once it exists (completeness A1) rather than minting a 4th
Fernet store — until then the existing Fernet switcher CRUD is the interim, flagged for migration; (iv) the
new PG tables (`video_jobs`/`video_scripts` + `ai_asset` columns) MUST be in the live PG backup set, and a
restore test must pass the RLS probe (E2); (v) before declaring the wave done, ONE integrated soak — inbound
call wave + a composite batch + library loads concurrently on the shared box — proves "green per-component"
is also "green integrated" (E3, the founder's #1 rule); (vi) a single `THREE_PRODUCTS_ROLLBACK.md` flips
every video flag OFF in order and confirms byte-identical resting in one pass (E4).

**Schema deltas these add:** `video_jobs` already carries `hold_id`/`attempts`/`updated_at` (reaper-ready);
add `moderation_status text DEFAULT 'pending'` + `music_license text` to the asset/job row; `video_scripts`
gained `lang` + `tts_provider` (above). All additive, FORCE-RLS, INTEGER paise.

---

## 14. BUILD ORDER (earner-safe, inbound-first, one box-mutating wave at a time)

> Earner gate before+after EVERY box-mutating wave: agent.py md5 (re-baseline from box) UNCHANGED + famit-agent
> PID 1477083 NOT restarted + caller `/health` 200 + 0 5xx + golden byte-diff + NO ring. Restart ONLY
> famit-caller / the AI-asset service / the hatchet worker / famit-panel. Backups per FORTRESS recipe.

1. **U1 — Seam fix (1 line, lowest risk).** `creative/video_studio/engine.py:51` → `from media_gen.video
   import client`. Verify `engine_name()`; 19 offline tests stay green. *No box mutation (local + tests).*
2. **U2 — PG schema (additive, manual apply).** `media_type`+video columns on `ai_asset` (incl.
   `moderation_status`, `music_license`); `video_jobs` (`hold_id`/`attempts`/`updated_at` reaper-ready) +
   `video_scripts` (`lang`+`tts_provider`) FORCE-RLS. Idempotent `IF NOT EXISTS`. Cross-tenant isolation
   probe PASS + the new tables added to the live PG backup set (H10-iv). *PG only.*
3. **U3 — Live-library bridge (§5).** `register_video_asset` internal route on `:8310`; `GET
   /assets?media_type=`; `/assets/{id}/poster`. Flag `FEATURE_VIDEO_LIBRARY`. *AI-asset service, NOT caller.*
4. **U4 — Mount the upper studio + the `submit_gate` choke-point (H1).** `creative.video_studio.endpoints`
   under `FEATURE_VIDEO_STUDIO` in caller.py; bind `list_campaigns`; `collect_batch` calls the bridge; every
   render routes through `submit_gate(tenant,brief)` (1-paid-test forcing + per-tenant `VIDEO_DAILY_CAP_USD` +
   pre-fan-out wallet hold, H1/H2). *caller.py (additive, flag OFF) — ⚠ serialize: only ONE of {RAG,Vault,
   Video} edits caller.py at a time (H10-i).*
5. **U5 — FFmpeg composite tier (§6) + cost-truth meter.** `media_gen/video/compose.py` + `provider="compose"`;
   Hatchet saga; Sarvam-default TTS (EL paid-gated) + Whisper + ABR; pre-fan-out wallet hold = chars+min+
   worker-sec (H1). Flag `FEATURE_VIDEO_COMPOSE`. *Hatchet worker + media_gen (no earner).*
6. **U6 — Frontend (§10).** Extend Asset type; `AssetMedia` `<video preload="none">`; FilterRail Video;
   LibraryGallery toggle; `app/creative/video/page.tsx` + TierTabs (composite default, EL/AI labelled "paid")
   + BatchProgress + UploadClip; nav. *famit-panel only — launch ONLY when no other wave is editing the
   panel.* Deploy FORTRESS once at the end.
7. **U7 — Signal-Loop export (§9).** `ab_group`/`ai_generated`/disclosure on the row + the Ads handoff stub.
   (Real ad spend Ads-OAuth-gated.) *additive.*
8. **U8 — Hardening: reaper + output-moderation + lifecycle + alerts (H3/H5/H6/H7/H9).** Orphaned-hold +
   lost-render reaper (H5); output-side moderation gate before publish (H3); destination-spec validator at
   attach (H6); Spaces lifecycle rule on dead variants + the `media_gen/spaces.py` R2 seam (H7); PushNotif/WA
   alerts on stuck-render / moderation-block / cap-hit (H9). *Hatchet worker + AI-asset service (no earner).*
9. **U9 — BYO-key (§10d) + Vault read-seam consumer + multilingual + music (H4/H10-iii).** Per-tenant gen-key
   via the **Vault `get_secret` seam once it exists** (interim Fernet switcher CRUD, flagged for migration);
   multilingual fan-out (`lang`, Sarvam-only default — paid TTS per-lang is opt-in, H1); royalty-free music
   library + provenance (H4). *additive.*
10. **U10 — Integrated soak + rollback runbook (H10-v/vi).** ONE shared-box soak (inbound call wave + a
    composite batch + library loads concurrently) proving green-integrated, then `THREE_PRODUCTS_ROLLBACK.md`
    flips every video flag OFF in order → byte-identical resting in one pass. *verify-only.*

> ⛔ GATED (build the safe half, record the blocked half): real gen output needs `FAL_KEY`/`RUNWAY_KEY`
> (founder); real ad launch needs Meta/Google OAuth; the AI-asset nginx proxy repoint (one blocker to the
> clickable demo) is FE-box-root-gated; DO GPU for self-host Wan is DO-quota-gated (composite needs NO GPU).
> Composite + manual-upload work TODAY with zero gen-key — ship those first.

---

*End VIDEO-STUDIO-MASTER-PLAN.md. The brief's research is adopted; its stale "done already" P0s are corrected;
the real gaps (live-library bridge, FFmpeg composite default, PG+RLS, the video frontend, Signal-Loop lineage)
are designed to the 100%. Earner-safe, multi-tenant-RLS, cost-real, low-latency-irrelevant (video is async by
construction — adds ZERO to the voice loop), sellable, differentiated. One box-mutating wave at a time.*
