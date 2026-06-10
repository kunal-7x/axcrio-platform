# BRAIN — media-gen (provider-agnostic media-generation ENGINE layer)

Durable facts + hard-won learnings. Append, never delete.

## WHAT IT IS
- Package: **`droplet_work/media_gen/`** (UNDERSCORE — "media-gen" is the orchestrator/build-log
  display label only; a hyphen is not an importable Python name and would fail import-smoke).
- The LOWER ENGINE layer the already-built `creative/*` STUDIO layers wait on: turns a media brief
  into an async provider job, cost-gates it, lands the artifact in DO Spaces.
- Spec: `design/automation-video.md` (primary) + `automation-image.md` + `automation-threed.md`.
- Build log: `memory/build_log/wave-build-mod-media-gen.md`. NOT wired into caller.py.

## THE LAYERING (critical — don't rebuild what exists)
- **VIDEO was the only real gap.** No video provider shapes existed anywhere. Built complete under
  `media_gen/video/` (providers/client/store/schema/cost/approval/safety/pricing/audit_hook).
  Exposes `submit_video_job` / `poll_video_job` — the EXACT names
  `creative/video_studio/engine.py:_real_engine()` resolves via `from automation.video import client`.
- **IMAGE + 3D already have complete engines** under `creative/image_banner_studio/` and
  `creative/threed_model/`. `media_gen.image` / `media_gen.threed` are THIN re-export wrappers that
  DELEGATE — never duplicate them. The only value media_gen adds at image/3D is optional Spaces
  relocation of a finished artifact.
- **DO Spaces writer** (`media_gen/spaces.py`) is the one shared engine-owned artifact store
  (boto3 S3-compat, dormant when `SPACES_*` unset, used by all 3 media types).

## ⭐ THE #1 WIRING DELTA (deferred orchestrator action)
`creative/video_studio/engine.py` expects `automation.video.client`. media_gen builds
`media_gen.video.client` with the same surface. Orchestrator REPOINTS that import. Until then the
studio falls back to `fake_engine` (the dormant contract working correctly). DO NOT edit engine.py.

## ⭐ HARD-WON LEARNING — silent-no-op seam bug (nearly shipped; advisor caught it)
A best-effort `try/except` import seam can hide a SIGNATURE mismatch that silently no-ops, and a
green test bar over the FALLBACK proves nothing about the real path.
- F4 `wallet.py` is: `reserve(tenant_id, amount_minor:int, resource_type, resource_id, idem_key,
  currency='INR', actor) -> hold_id:int|None`. Money is **INTEGER PAISE (INR)**, returns an int,
  `available()`==False when PG down. A naive `reserve(tenant_id, usd_str, meta=...)` expecting a
  dict is DEAD IN EVERY CASE (TypeError caught -> always falls to JSON shim). 17 tests stayed green
  because the JSON shim handled all smoke. `spend_backend:"wallet_firewall"` was a LIE (import !=
  functional).
- FIX pattern (now in `media_gen/video/cost.py`): USD->INR-paise CEIL (never under-reserve, via
  the `IMAGE_USD_INR` FX seam default 87); correct signatures; handle `Optional[int]`; flow
  `idem_key` (the REAL no-double-spend primitive); TAG `hold_backend` ("wallet"|"json") on the job
  so settle/release dispatch to the SAME minting backend (a JSON `hold_<hex>` must never hit
  `wallet.settle(int)`); `wallet.release(hold_id)` takes NO amount; `wallet_backend()` reports what
  would ACTUALLY execute (a PG-live `available()` check), not importability.
- GUARD: `test_seam_signatures_compatible` asserts `wallet.reserve` has `amount_minor`+`idem_key`
  and `audit.record` has the kwargs `audit_hook.log` passes. Run this whenever a spine module moves.
- `audit.record(actor, action, object_type='', object_id='', ip='', channel='api', tenant_id=None,
  actor_role='', meta=None)` — `audit_hook.log` IS compatible (verified). Immutable PG events
  ledger when present.

## COMPOSED FOUNDATION
- Spend: cost.py -> F4 `wallet.py` when PG-live, else `creative/shared/cost.py` JSON hold-store
  (RTF-3 pre-Postgres contract). Engine OWNS the per-model pricing table (`video/pricing.py`,
  per_second + per_generation modes — Wan bills flat per-gen, RTF-5).
- Caps: engine `VIDEO_DAILY/MONTHLY_CAP_USD` authoritative FIRST, shared studio shim 2nd.
  NOTE: the shared `creative.shared.cost.check_caps` keys off `VIDEO_STUDIO_*` env names, NOT the
  engine's `VIDEO_*` — that mismatch is why the engine enforces its own caps first.
- Firewall/approval are TWO separate gates. Endpoints are auth-less by design; orchestrator binds
  RBAC + `firewall.require_step_up` at the route layer.

## GUARDRAILS (automation-video §7 + red-team fixes, all offline-tested)
license gate (selfhost Apache-2.0 allowlist wan/cogvideox/ltx/mochi; Hunyuan REFUSED for commercial
ad output) · content + likeness screen BEFORE spend (RTF-1 shared-key AUP protection) · per-tenant
key isolation `<ENV>__<tenant_id>` · per-provider webhook verify (replicate HMAC-SHA256 Svix; fal
ED25519/JWKS fail-closed without an injected verifier; shared HMAC selfhost/generic — RTF-4) ·
idempotency replay · never-raises on httpx throw (whatsapp.py contract).

## HOW TO RUN (offline, zero network)
From inside `droplet_work/`: `python -m pytest media_gen/tests -q` -> 19 passed. The dormant no-op
path uses no network; "configured" cases monkeypatch `client._request_json`. py3.14 local works.

## STATUS / OPEN
- All units built + offline-verified (19 tests + import-smoke + mocked happy-path + py_compile +
  router 12 endpoints). DEFERRED: repoint automation.video.client; mount router into caller.py;
  activate live wallet (PG + FX); verify non-fal provider paths + fal ED25519 verifier at enable;
  video selfhost_worker.py (Wan 2.2 DO GPU, breakeven-gated). See build log for the full list.

## SECURITY FIX (2026-06-10) — token-deriving build_router added
- Hole: `media_gen/router.py` read tenant from the body brief + by-`job_id` routes had NO ownership check;
  module-level `router = build_router()` (no-arg) would BREAK import-smoke once auth params became required.
- Fix: old body-router renamed `_bare_router()` (12-endpoint introspection, DO-NOT-MOUNT); NEW
  `build_router(resolve_tenant, can, need_auth, forbidden, firewall=None)` is the authed mount surface.
  Video submit OVERWRITES `brief["tenant_id"]=token_tenant`; by-job_id routes enforce
  `rec["tenant_id"]==token` else `error:no_such_job`; `/video/webhook` stays unauth (provider-signed).
  `can(t,action)` takes the WHOLE tenant dict. Verified: token A beats body B; 19/19 tests still pass.
  Mount `build_router(...)`, NOT the module-level `router`. Build log: build_log/wave-build-security-fixes.md.
- IMAGE dual-channel trap: `/image/generate` passes tenant BOTH as `_image.generate(..., tenant_id=token)`
  kwarg AND inside the brief dict. The underlying creative/image engine may read tenant from the brief, so
  the body value could win via that channel. FIX: also `body["tenant_id"]=token` before the call (like the
  video path). Verified token A forced on BOTH kwarg and brief.
