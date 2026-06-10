# WAVE-BUILD — MODULE "media-gen" (provider-agnostic media-generation ENGINE layer)

Built 2026-06-10. Local SoT `droplet_work/`. NO git (orchestrator commits). DID NOT edit
`caller.py`/`agent.py`, did not restart services, placed no calls. All offline-verified.

Primary spec: `design/automation-video.md` (+ `automation-image.md`, `automation-threed.md` read).
Package: **`droplet_work/media_gen/`** (UNDERSCORE — "media-gen" is the orchestrator display
label; a hyphen dir is not importable so cannot satisfy the import-smoke requirement).

## THE CORE INSIGHT (what this composes)
`media_gen` is the **lower ENGINE layer** the already-built `creative/*` STUDIO layers wait on.
- **VIDEO = the real gap.** No video provider shapes existed anywhere. `creative/video_studio/`
  is a studio whose `engine.py:_real_engine()` does `from automation.video import client` and
  checks `hasattr(eng,"submit_video_job"|"poll_video_job")` — that engine was never built.
  `media_gen.video` IS it. Built complete (providers/client/store/schema/cost/approval/safety/
  pricing/audit_hook).
- **IMAGE + 3D engines ALREADY EXIST** (`creative/image_banner_studio`, `creative/threed_model`
  — full providers + engine). `media_gen.image` / `media_gen.threed` are THIN re-export wrappers
  that delegate (NO duplication of ~1500 lines), adding one unified concern: Spaces relocation.
- **DO Spaces artifact writer = shared gap.** Built once: `media_gen/spaces.py` (boto3 S3-compat,
  dormant when `SPACES_*` unset, shared across all 3 media types).

## FILES CREATED (all NEW under media_gen/)
- `__init__.py` (redact, DISPLAY_NAME), `STATE.md`, `router.py` (unified FastAPI, build_router()
  behind `_HAVE_FASTAPI`, NOT mounted), `spaces.py` (shared artifact writer).
- `video/`: `__init__.py`, `schema.py` (VideoBrief schema-compatible w/ video_studio §5a + JobStatus),
  `config.py` (provider select, per-tenant key isolation RTF-1, guardrail knobs, redacted status),
  `store.py` (JSON job store + idempotency lookup), `providers.py` (PURE build_submit/parse_*/
  build_status/verify_webhook for fal|replicate|luma|higgsfield|selfhost|generic + license gate),
  `pricing.py` (per-model rate table, per_second + per_generation modes RTF-5), `safety.py`
  (pre-submit content/likeness screen RTF-1), `cost.py` (estimate + cap + reserve/settle/RELEASE),
  `approval.py` (human-approval gate), `audit_hook.py` (spine audit bridge), `client.py`
  (submit_video_job/poll_video_job orchestration).
- `image/__init__.py`, `threed/__init__.py` (thin reuse wrappers).
- `tests/test_video_offline.py` (19 tests, fully offline).

## ROUTER ENDPOINTS (for the later mount — prefix `/media`, NOT mounted)
GET /media/status · POST /media/video/jobs · GET /media/video/jobs · GET /media/video/jobs/{id}
· GET /media/video/jobs/{id}/poll · POST /media/video/jobs/{id}/{approve,reject,cancel}
· POST /media/video/webhook (no auth, per-provider signature verify, fail-closed) ·
GET /media/image/status · POST /media/image/generate · GET /media/threed/status.

## ⭐ THE WIRING DELTA (the #1 deferred orchestrator action — DO NOT do in build)
`creative/video_studio/engine.py` resolves `automation.video.client`. media_gen builds
`media_gen.video.client` exposing the SAME names. **Orchestrator repoints that import**
(`automation.video.client` -> `media_gen.video.client`). Until then the studio correctly falls
back to `fake_engine` (dormant contract working as designed). DO NOT edit engine.py.

## ⭐ HARD-WON LEARNING — the silent-no-op seam bug (advisor catch; nearly shipped)
The F4 `wallet.py` signature is RADICALLY different from a naive assumption:
`reserve(tenant_id, amount_minor:int, resource_type, resource_id, idem_key, currency='INR', ...)
-> hold_id:int|None` — money in INTEGER PAISE (INR), returns an int, `available()`==False when PG
down. My first cost.py passed string-USD + `meta=` kwarg + expected a dict -> the wallet call was
**DEAD IN EVERY CASE** (TypeError caught -> always fell to the JSON shim), yet 17 tests were green
(the shim handled all smoke). `spend_backend:"wallet_firewall"` was a LIE (import != functional).
FIX: USD->INR-paise (CEIL via `IMAGE_USD_INR` FX seam, never under-reserve); correct signatures;
handle `Optional[int]`; flow `idem_key` (the real no-double-spend primitive); TAG `hold_backend`
on the job so settle/release dispatch to the SAME minting backend (a JSON `hold_<hex>` string must
never hit `wallet.settle(int)`); `wallet_backend()` reports what would ACTUALLY execute (PG-live
check), not importability. Added `test_seam_signatures_compatible` to GUARD the whole seam class
(also verified `audit.record(actor,action,object_type,object_id,ip,channel,tenant_id,actor_role,
meta)` — our audit_hook IS compatible there). LESSON: a best-effort try/except import seam can hide
a signature mismatch that silently no-ops; a green bar over the fallback proves nothing about the
real path — assert the seam signature.

## COMPOSES THE FOUNDATION
- Spend: `cost.py` delegates reserve/settle/**release** (NOT refund, RTF-2) to F4 `wallet.py` when
  PG-live, else `creative/shared/cost.py` JSON hold-store (RTF-3 pre-Postgres contract). Engine
  supplies the real per-model PRICING TABLE (`pricing.price_hints` feeds the shared shim).
- Caps: engine `VIDEO_DAILY/MONTHLY_CAP_USD` authoritative ceiling FIRST, shared studio shim 2nd.
- Audit: best-effort `audit.record` via `audit_hook` (immutable PG events ledger when present).
- Firewall: spend/approval are TWO separate gates (matches platform pattern). The PIN/step-up
  `firewall.py` is wired by the orchestrator at the route layer (endpoints are auth-less by design).

## GUARDRAILS BAKED IN (automation-video §7 + RED-TEAM fixes)
license gate (selfhost Apache-2.0 allowlist wan/cogvideox/ltx/mochi; Hunyuan refused) · content +
likeness screen BEFORE spend (RTF-1 shared-key AUP protection) · per-tenant key isolation
`<ENV>__<tenant_id>` · estimate->cap->approval-park->reserve->submit (each fail-closed) · pricing
MODES per_second+per_generation (RTF-5 Wan flat-rate) · per-provider webhook verify (replicate
HMAC-SHA256 Svix; fal ED25519/JWKS fail-closed w/o injected verifier; shared HMAC for selfhost/
generic — RTF-4) · idempotency replay (no double-charge) · never-raises on httpx throw.

## VERIFICATION (offline, zero network)
`python -m pytest media_gen/tests -q` -> **19 passed**. Covers: dormant config/submit/poll,
provider-shape goldens (fal+replicate), parse goldens, pricing modes, license gate (blocks before
spend), content screen (blocks before spend), cap gate (no provider call), approval park +
idempotency replay, never-raises-on-http-throw, replicate-HMAC webhook verify + fal-fail-closed,
Spaces dormant, wallet-bridge honesty + seam-signature guard, malformed-brief fuzz.
Plus: full package import-smoke; configured-but-mocked submit->poll->SUCCEEDED happy path (2 HTTP
calls mocked, hold settled at actual cost, artifact extracted); `py_compile` clean; router builds
12 endpoints; audit_hook.log executes against real audit.record.

## CREDS AWAITED (dormant until set — automation-video §9)
TIER 1: `VIDEO_PROVIDER=fal`, `FAL_KEY`, `VIDEO_FAL_MODEL`, `SPACES_KEY/SECRET/BUCKET/REGION/
ENDPOINT`. TIER 2 (alt backends): `REPLICATE_API_TOKEN`, `LUMA_API_KEY`, `HIGGSFIELD_API_KEY/URL`,
`VIDEO_API_URL/KEY` (generic). TIER 3 (self-host): `VIDEO_SELFHOST_URL/TOKEN/MODEL` (Apache-2.0
only). Webhooks: `VIDEO_FAL_JWKS_URL`, `VIDEO_REPLICATE_WEBHOOK_SECRET` (whsec_), `VIDEO_WEBHOOK_
SECRET` (selfhost/generic). FX: `IMAGE_USD_INR` (default 87). Knobs: `VIDEO_APPROVAL_THRESHOLD_USD`
(1.00), `VIDEO_AUTO_APPROVE` (0), `VIDEO_DAILY/MONTHLY_CAP_USD` (20/300), `VIDEO_MAX_DURATION_S`
(10), `VIDEO_COST_SAFETY` (1.25), `VIDEO_MODERATION_URL` (optional hook).

## DEFERRED (orchestrator/later units)
1. **Repoint `automation.video.client` -> `media_gen.video.client`** in `creative/video_studio/
   engine.py` (the #1 wiring action) so the studio uses the real engine.
2. **Mount `media_gen.router.build_router()`** into `caller.py`, binding tenant/RBAC/audit deps +
   wiring `firewall.require_step_up` on spend/approve routes + the public webhook URL.
3. **Activate live F4 wallet**: needs PG up + the USD->INR FX confirmed; until then the JSON
   hold-store is the active backend (RTF-3). The bridge is correct + tagged; flip is data-only.
4. Verify exact non-fal provider paths (Replicate/Luma/Higgsfield) + fal ED25519 verifier injection
   against current vendor docs at enable-time (provider switch isolates the change).
5. `selfhost_worker.py` (Wan 2.2 on DO GPU) — dormant, breakeven-gated (automation-video §8), not
   built (3D/image self-host docs already exist under creative/*; video self-host is later).
