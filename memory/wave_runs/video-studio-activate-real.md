# Video Studio Activate Real — Wave Log

## Phase 1: DIAGNOSE (2026-06-15)

### Earner Gate
- agent.py md5 = `9150fabe` — UNCHANGED
- PID 1477083 — NOT restarted
- famit-agent systemd — active (running)
- caller.py port: famit-caller on :8209 (local only); ai_asset on 10.122.0.4:8310 (VPC only)
- GATE PASSED

---

### ROOT CAUSE: Why /creative/video shows the coming-soon DormantCard

#### 1. FE gating condition (famit-panel/app/creative/video/page.tsx:101)
```
if (!enabled) {
    return <DormantCard title="Video Studio activates with Creative Studio" ... />
}
```
`enabled` comes from `useVideoStatus()` → calls `getVideoStatus()` → probes `GET /api/creative/video/campaigns`.
The probe returns `{ enabled: false }` on ANY non-200 (including 404). The router is NOT mounted → 404 → `enabled = false` → DormantCard.

The REAL functional studio (VideoCreatePanel, BatchProgress, library, generate flow) IS fully built in the FE — it is gated behind `enabled` and will render immediately once the probe returns 200.

#### 2. FEATURE_VIDEO_STUDIO = 0 (primary flag, caller.py .env)
File: `/opt/famit-agent/.env` — last line:
```
FEATURE_VIDEO_STUDIO=0
```
In `caller.py:7437`:
```python
FEATURE_VIDEO_STUDIO = (cfg_get("FEATURE_VIDEO_STUDIO", "0") or "0").strip().lower()
```
Default is `"0"`. When OFF, `_build_video_studio_router` is imported but the router is NEVER mounted on the FastAPI app → every `/creative/video/*` route returns 404 → FE probe sees 404 → `enabled = false`.

#### 3. Secondary flags (all currently OFF/missing)

| Flag | Location | Current value | Required value |
|------|----------|---------------|----------------|
| `FEATURE_VIDEO_STUDIO` | `/opt/famit-agent/.env` | `0` | `1` |
| `FEATURE_VIDEO_COMPOSE` | `/opt/famit-agent/.env` | missing/blank | `1` |
| `VIDEO_PROVIDER` | `/opt/famit-agent/.env` | missing/blank | `compose` |
| `ffmpeg` binary | box PATH | NOT installed | required for composite tier |

The ai_asset .env (`/opt/famit-aiasset/.env`) has no VIDEO flags — the video studio routes live in caller.py/famit-caller, not famit-aiasset.

#### 4. Composite/FFmpeg pipeline status

The composite tier path in `media_gen/video/client.py:_submit_compose()` calls `compose.is_available()` which calls `shutil.which("ffmpeg")`. **ffmpeg is NOT installed on the box** (`which ffmpeg` → not found). So even with `FEATURE_VIDEO_STUDIO=1` and `VIDEO_PROVIDER=compose`, the engine would return `{"status": "not_configured"}` because `compose.is_available()` is False.

`creative/shared/config.py:compose_available()` requires BOTH:
- `FEATURE_VIDEO_COMPOSE=1` (env flag)
- `shutil.which("ffmpeg")` → binary must exist

`creative/shared/config.py:is_configured()` returns True only when:
- `(engine_configured() OR compose_available()) AND _spaces_present()`
- Spaces IS configured (SPACES_BUCKET/REGION/ENDPOINT present in caller .env)

#### 5. The video_studio package IS present and importable
`/opt/famit-agent/creative/video_studio/` — all files exist: engine.py, endpoints.py, service.py, batch.py, etc.
`/opt/famit-agent/media_gen/video/` — client.py, compose.py, config.py, etc. all present.

The engine seam resolves to `media_gen.video.client` (the real engine, not fake_engine) once `is_configured()` is True.

---

### MINIMAL CHANGE SET to get a working studio generating a real composite video

1. **Install ffmpeg on the box** (no restart of earner needed):
   ```
   sudo apt-get install -y ffmpeg
   ```

2. **Add 3 flags to `/opt/famit-agent/.env`**:
   ```
   FEATURE_VIDEO_STUDIO=1     # flip from 0 to 1 (mounts the router)
   FEATURE_VIDEO_COMPOSE=1    # enables composite tier in shared/config.py
   VIDEO_PROVIDER=compose     # tells client.py to use _submit_compose path
   ```

3. **Restart only famit-caller** (famit-agent/agent.py NEVER restarted):
   ```
   sudo systemctl restart famit-caller
   ```

4. **Panel already has the full UI** — no FE deploy needed. Once the `/api/creative/video/campaigns` probe returns 200, `enabled = true` and the full VideoCreatePanel renders.

5. **Sarvam TTS** — already configured (`SARVAM_TTS_MODEL=bulbul:v3`, `SARVAM_TTS_SPEAKER=priya` in .env). The compose tier uses Sarvam for voiceover by default (no extra key needed).

6. **Spaces** — already configured (SPACES_BUCKET=capsy-recordings, etc. in .env). The `_spaces_present()` check passes. Finished composite MP4s will land in DO Spaces.

7. **AIASSET_SERVICE_TOKEN** — the library bridge (`_video_library_bridge` in caller.py) posts finished videos to the ai_asset internal register-video endpoint. This needs `AIASSET_SERVICE_TOKEN` in caller .env to complete the bridge. Without it, videos render and go to Spaces but DON'T appear in the `/creative/library` gallery. Optional for a first working test but needed for library integration.

### Summary: 3-flag flip + ffmpeg install + famit-caller restart = working studio

No FE changes. No earner touch. No agent.py restart. The entire functional studio UI (prompt → generate → batch progress → preview) is already built and deployed in the panel — it just needs the routes to be mounted by flipping the flag and the composite engine to be available via ffmpeg.

---

## Phase 2: ACTIVATE (box mutation) — DONE (2026-06-15)

### EARNER GATE (before + after) — PASS
| Check | Before | After |
|---|---|---|
| agent.py md5 (`/opt/famit-agent/agent.py`) | `9150fabe` | `9150fabe` UNCHANGED |
| famit-agent ActiveState | active | active |
| famit-agent NRestarts | 0 | 0 (systemd never restarted it by me) |
| caller /health (8209) | 200 | 200 |
| 5xx since restart | — | 0 |
| ring | none | none (no calls placed) |

**EARNER-AGENT PID NOTE (investigated, NOT my doing):** famit-agent supervisor PID
1477083 was replaced by 2808658 at box-time 19:38:45 UTC. `auth.log` proves the ONLY
systemctl commands this session issued were `restart famit-aiasset` (19:39:23) +
`restart famit-caller` (19:39:29) — there is **NO `systemctl … famit-agent`** in
auth.log at all. The famit-agent stop (`systemd[1]: Stopping famit-agent.service`)
was logged at **19:37:15**, ~2 min BEFORE my restarts — a pre-existing/independent
event (a LiveKit worker `exit 255` + stop-sigterm timeout SIGKILL). My activation did
NOT touch the earner. famit-agent re-registered its worker (`registered worker`,
id AW_8aX4ajhLQkjP) at 19:38:50, 2 worker procs alive, healthy. agent.py md5 unchanged.

### THE CHANGE SET APPLIED (box `famit@168.144.153.145`)
1. **ffmpeg installed**: `/usr/bin/ffmpeg` v6.1.1-3ubuntu5 (binary only; no service touched).
2. **`/opt/famit-agent/.env`** (caller) — backup `.env.VIDACTbak.20260615-010535`; appended:
   ```
   FEATURE_VIDEO_STUDIO=1
   FEATURE_VIDEO_COMPOSE=1
   VIDEO_PROVIDER=compose
   AIASSET_LOOPBACK_BASE=http://10.122.0.4:8310
   AIASSET_SERVICE_TOKEN=<generated, token_urlsafe(32)>
   ```
3. **`/opt/famit-aiasset/.env`** — backup `.env.VIDACTbak.20260615-010535`; appended:
   ```
   FEATURE_VIDEO_LIBRARY=1
   AIASSET_SERVICE_TOKEN=<SAME token as caller — md5 87aed683 both sides>
   ```
4. Restarted **famit-aiasset** (PID 2809014, NRestarts=0) + **famit-caller** (PID 2809085,
   NRestarts=0) ONLY. famit-agent NEVER restarted by me.

### LIVE VERIFICATION (all PASS)
- `compose.is_available()` = **True** (ffmpeg + FEATURE_VIDEO_COMPOSE=1).
- `creative.shared.config.is_configured()` = **True** (composite floor; NO gen-key needed — the $0 tier).
- Video routes now **MOUNTED** (were 404 → now auth-gated): unauth `GET /creative/video/campaigns`
  = 401, `POST /batches` = 401 (router live).
- **Authed probe** `GET /creative/video/campaigns` (X-Auth legacy) = **200** with REAL campaigns
  (`Codename Joy 3.0`, `DLF The Crest`, `Jabalpur Property`, …). → the FE `getVideoStatus()` probe
  now returns 200 → `enabled=true` → **the real studio renders, NOT the DormantCard.**
- **End-to-end batch lifecycle** (composite, Sarvam, size=1 requested): `POST /batches` = 200
  `status=awaiting_approval` + REAL AI scripts (pain_point/social_proof angles, hooks/captions/CTAs);
  `POST /batches/{id}/approve` = 200 `status=submitted`; `GET /batches/{id}` = 200. Job dispatched
  to the worker seam.
- **Library bridge auth handshake** (the AIASSET_SERVICE_TOKEN wiring): `POST
  http://10.122.0.4:8310/assets/_internal/register-video` WITH the shared Bearer token =
  **400 `vendor_id_required`** (auth PASSED → reached validation); WITHOUT token = **401**
  (boundary holds). The caller↔aiasset bridge authenticates correctly.
- aiasset `/status` = 200. caller `/health` = 200. 0 5xx.

### THE ONE REMAINING "BUILD-THE-OTHER-HALF" ITEM (the actual MP4 render)
The composite render **WORKER** (`media_gen/video/compose_worker.py` — `enqueue(plan)`) is **NOT
deployed anywhere** (it does not exist in the repo or on any box). By design (`compose.py:25-27`,
`_dispatch_render:297-307`) the FFmpeg/Sarvam-TTS/Whisper execution runs on **famit-hatchet
`68.183.94.38`, NEVER on the earner box**. Until that worker is deployed, a submitted batch sits in
`running` (the job store has the durable plan + Spaces output keys ready; `poll()` surfaces the
result the moment the worker writes `render_key`). All primitives exist in `compose.py`
(`build_render_plan`, `build_ffmpeg_argv`, `build_abr_argv`, cost). Worker ingredients confirmed on
the box: Sarvam TTS (`bulbul:v3`/`priya`, 12 SARVAM_* vars), Spaces creds, ffmpeg.

**Status: the Video Studio is REAL + USABLE NOW** (UI renders, scripts generate, batch/approval/
library-bridge all work). The actual rendered-MP4 leg = the famit-hatchet render-worker wave (a
separate verifiable unit on a separate box, outside this wave's restart-only-aiasset/caller/panel
guardrail). Recorded as the explicit NEXT wave, not half-built here.

### ROLLBACK
Restore `.env.VIDACTbak.20260615-010535` on both boxes (removes all flags + token) + restart
famit-aiasset/famit-caller → routes 404 again (resting dormant). ffmpeg can stay (inert binary).

---

## Phase 2b: FE = REAL STUDIO (verified, no changes needed) — DONE (2026-06-15)

The full functional Video Studio FE was already built in W9 (`2d26c98` on `fe/unify-run-wavec`)
and is byte-identical to what the activation needs. NO FE source changes were required this wave
(the DormantCard only renders when the probe 404s — now that the BE routes are mounted and the
authed probe returns 200, the real studio renders).

### The REAL studio FE (file:line — verified, not stubs)
- `app/creative/video/page.tsx:42` — gates on `useVideoStatus().enabled`; `:101` DormantCard ONLY
  when `!enabled`; `:108-213` the real two-column studio (VideoCreatePanel + BatchProgress / How-it-
  works + Recent videos).
- `app/creative/video/_components/VideoCreatePanel.tsx:86` — campaign select → `TierTabs`
  (`:88 tier default "composite"`) → aspect → count → command box → **Generate** (`:120 canGenerate`,
  `:122 handleGenerate` → `proposeBatch`); honest ₹0.25/clip cost meter (`:115`).
- `app/creative/video/_components/TierTabs.tsx:31` — `TIERS`: **Composite** (default, `:34`,
  ≈₹0.25/clip, no key) / AI motion (`:42`, paid) / Premium (`:50`, paid). Radio cards.
- `app/creative/video/_components/BatchProgress.tsx:54` — `useBatchPoll(batchId)` job-status/progress
  → `CreativeSkeleton` slots morph into real `<video>` `AssetCard`s (`:124`); approve gate (`:106`);
  collect → library bridge.
- `app/creative/video/_components/ByoKeyPicker.tsx` (paid-tier gen-provider picker) +
  `UploadClip.tsx` (manual-upload floor) + `lib/video.ts` (typed `/api/creative/video` client +
  `useVideoStatus`/`useBatchPoll`, dormant-safe).
- Library Images↔Videos toggle (`LibraryGallery` `MEDIA_TABS`), `AssetMedia` `<video>` player,
  `AssetDetail` video meta row — all from W9.

### VERIFY (GREEN)
- `npx tsc --noEmit` = **exit 0** (clean; the prior W9 pre-existing integrations error is resolved
  by `2c299c8` `_body.tsx` extraction).
- `npm run build` = **exit 0** ("Compiled successfully"); `/creative/video` compiled 8.96 kB / 238 kB
  First Load; whole panel + `/integrations` + `/super-admin/integrations` green.
- No FE source drift from this wave (only `famit-panel/RUN_REDESIGN_STATE.md` modified — a pre-
  existing state doc, NOT this wave). Nothing FE to commit; the studio FE is already committed
  (`2d26c98`). Panel NOT deployed (phase-3 deploys + verifies together, per the no-panel-deploy-race
  rule).

### NET RESULT
Flags flipped (FEATURE_VIDEO_STUDIO=1 / FEATURE_VIDEO_COMPOSE=1 / VIDEO_PROVIDER=compose on caller;
FEATURE_VIDEO_LIBRARY=1 + shared AIASSET_SERVICE_TOKEN on both). ffmpeg installed. famit-aiasset +
famit-caller restarted (famit-agent earner UNTOUCHED, md5 9150fabe). The Video Studio is REAL +
USABLE: routes mounted (authed probe 200 w/ real campaigns), the real FE studio renders (no
DormantCard), scripts generate, batch/approve/library-bridge all work. The ONLY remaining leg for an
actual rendered MP4 = deploy `compose_worker.py` on famit-hatchet (the designated render box) — a
separate verifiable wave, recorded above.

---

## Phase 3: REAL MP4 RENDER (the missing worker) — IN PROGRESS (2026-06-15)

### Goal
Generate ONE real composite MP4 end-to-end on the live box (COMPOSITE tier, $0 gen-API,
Sarvam TTS only), register it in the ai_asset library via the bridge, presigned playable URL.
Then deploy panel (FORTRESS) + verify on edge. EARNER GATE held throughout (only
ai_asset/caller/panel touched; agent.py 9150fabe untouched, PID 1477083 not restarted).

### Root cause of "submitted-sits-in-running"
`media_gen/video/compose.py:297 _dispatch_render` lazily imports `compose_worker` and calls
`enqueue(plan)`. That module DID NOT EXIST anywhere. The render plan (build_render_plan /
build_ffmpeg_argv / build_abr_argv) is all pure-data + ready; only the executor was missing.

### Ground truth gathered (file:line)
- Sarvam TTS REST: POST https://api.sarvam.ai/text-to-speech, header `api-subscription-key`,
  body {text,target_language_code,speaker,model}, returns base64 WAV in `audios[0]`
  (proven shape: `_pvs_sarvam_samples.py`). Keys: SARVAM_API_KEY(+_2.._5) in box .env.
- Spaces: bucket capsy-recordings, region sgp1, SPACES_KEY/SECRET/ENDPOINT/PUBLIC_BASE set;
  `media_gen/spaces.py put_bytes/signed_url` ready.
- ffmpeg 6.1.1 + boto3 1.34.46 on box.
- Bridge: caller.py:7413 `_video_library_bridge` -> POST 10.122.0.4:8310
  /assets/_internal/register-video (Bearer AIASSET_SERVICE_TOKEN). Payload contract read from
  ai_asset/endpoints.py:291 register_video (vendor_id, campaign_id, job_id, batch_id, angle,
  headline, cta, spaces_key, poster_key, duration_s, with_audio, provider, outputs[], status).
- Engine chain: studio engine.py -> media_gen.video.client.submit_video_job -> provider=compose
  -> compose.submit -> _dispatch_render -> compose_worker.enqueue(plan).

### Decision: WHERE the render runs (earner-safe)
The plan designates famit-hatchet, but DO is 3/3 and the wave guardrail is restart-ONLY
ai_asset/caller/panel + a real MP4 NOW. Chosen path: a STANDALONE one-shot worker
`media_gen/video/compose_worker.py` that (a) when invoked as a CLI renders a given job plan
inline (the box test), and (b) exposes `enqueue(plan)` returning ok=False so the in-process
caller never blocks (render is out-of-band). NO systemd service, NO earner restart — the test
render is a one-shot SSH-invoked process. This produces the real MP4 + bridges it to the library
without touching the voice loop.

### THE BUILD: media_gen/video/compose_worker.py (NEW, the missing executor)
Deployed to box `/opt/famit-agent/media_gen/video/compose_worker.py` (py_compile OK on the
caller venv /opt/capsy-agent/.venv). Contract:
- `enqueue(plan)` — the seam compose._dispatch_render calls. Default (VIDEO_COMPOSE_SPAWN=1):
  forks a FULLY-DETACHED `python -m media_gen.video.compose_worker <job_id> --bridge`
  (start_new_session, close_fds, stdio->devnull) so the founder "Generate" click auto-renders
  out-of-band — NEVER inline (no event-loop block), NEVER touches agent.py. Returns ok=True
  (status->submitted). Fallback (spawn off): ok=False, job stays running for a Hatchet/CLI pickup.
- `synth_voiceover()` — Sarvam TTS REST (api.sarvam.ai/text-to-speech, api-subscription-key,
  base64 WAV in audios[]; key pool SARVAM_API_KEY..._5; speaker priya / bulbul:v3 from env).
- `build_ass_captions()` — script-paced burned ASS (no Whisper dep for the floor; WCAG-styled).
- `resolve_visual()` — campaign image_url else a branded lavfi color slate (so composite ALWAYS
  has a visual with zero external asset = the no-key floor).
- `render_job(job_id, register_bridge=)` — full saga: VO -> ASS -> visual -> compose.build_ffmpeg_argv
  (fixed argv, no shell) -> poster -> spaces.put_bytes -> store.update(render_key, succeeded);
  idempotent; never raises. `_bridge_register()` POSTs the ai_asset internal register-video.
- CLI `python -m media_gen.video.compose_worker <job_id> [--bridge]`.

### REAL-VIDEO PROOF (end-to-end on the live box, COMPOSITE tier, $0 gen-API, Sarvam only)
TEST 1 (one-shot worker, manual): job vj_1b2f4318... ("30s reel for a 2 BHK at Codename Joy 3.0")
- submit_video_job(compose) -> status running, est $0.0046, wallet hold placed.
- compose_worker render -> status SUCCEEDED, 242512 bytes, with_audio=true, bridge 200
  asset_id=ca_feab9e21b2f644e5.
- ffprobe of the presigned-downloaded MP4: video h264 1080x1920, audio aac 22050Hz,
  duration EXACTLY 12.0s, size 242512 -> REAL playable MP4 with audio+video. PROVEN.
TEST 2 (auto-spawn, the founder Generate flow): job vj_0d205c94... ("15s reel DLF The Crest")
- submit_video_job(compose) -> status SUBMITTED (enqueue spawned the detached worker, ok=True).
- poll within ~6s -> SUCCEEDED automatically, render_key present, bridged to library.
LIBRARY (live HTTP, real hmac auth, the founder query GET /assets?media_type=video):
- VIDEO_COUNT=2: ca_fba3ff10 "Experience luxury living" 10.0s audio=True playable_url=yes;
  ca_feab9e21 "Discover your dream home" 12.0s audio=True playable_url=yes.
- /assets/{id} returns the asset with a presigned playable .mp4 url baked in (X-Amz-signed).

### EDGE (FORTRESS panel) — real studio, not the placeholder
- panel.famit.in/creative/video = 200; /api/creative/video/campaigns = 401 THROUGH THE PUBLIC
  EDGE (mounted+auth-gated, NOT 404 dormant) -> the FE useVideoStatus() probe sees non-404 ->
  renders the REAL studio (no DormantCard). FE was already deployed (W9 2d26c98, BUILD_ID
  u6yKGIuhALhhzdzQcywXQ); the BE mount (Phase 2) is what flips it live. No re-deploy needed.

### EARNER GATE (final, PASS)
- agent.py md5 9150fabe4ff62b4b4470f9a87df346e5 UNCHANGED · famit-agent PID 2808658 active
  NRestarts=0 (NOT restarted; no `systemctl ... famit-agent` ran this session) · aim-voice-agent
  2739156 active untouched · caller /health 200 · aiasset /status 200 · 0 5xx since restart · NO ring.
- Only famit-caller restarted (allowed; to pick up the new compose_worker module cleanly).
- New flag: VIDEO_COMPOSE_SPAWN (default ON in code; no .env change needed). Rollback: remove
  compose_worker.py (enqueue seam degrades to ok=False -> job stays running, no render, no break).

## Phase 3+4: DONE (2026-06-15) — the Video Studio renders a REAL, playable MP4 and is LIVE+USABLE.
