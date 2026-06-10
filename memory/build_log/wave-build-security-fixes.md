# WAVE BUILD — Tenant-Isolation Security Fixes (3 modules)

Date: 2026-06-10. Scope: apply the 3 tenant-isolation SECURITY FIXES from
`REMAINING_MODULES_BUILD_STATE.md` to the NEW module routers — booking, media-gen, funnels.
Each read `tenant_id` from the request **body / spoofable header** = cross-tenant holes.
NO `caller.py`/`agent.py` edit · NO deploy · NO git (orchestrator commits) · funnels mount-diff NOT applied.

## THE HOLE (all three, same class)
- **booking** (`booking/router.py`): default `get_ctx` read `X-Tenant-Id` header (spoofable) → `Ctx.tenant_id`.
- **media-gen** (`media_gen/router.py`): video submit/image-gen read `tenant_id` from the body brief;
  `get/poll/approve/reject/cancel` took a `job_id` with NO ownership check; module-level
  `router = build_router()` (no-arg).
- **funnels** (`funnels/endpoints.py`): every route `tenant_id=payload.get("tenant_id","")` from the body;
  because a funnel COMPILES DOWN to the workflow engine, the body tenant flowed straight into
  `workflow.publish/run` — delegating to the engine does NOT save it.

## THE FIX — token-deriving `build_router(...)` (the settled platform pattern)
Refactored each module to expose `build_router(resolve_tenant, can, need_auth, forbidden, firewall=None)`,
mirroring `workflow-studio/workflow/endpoints.py` + `forms-surveys/endpoints.py`:
- tenant := `resolve_tenant(request)['tenant_id']` (token-derived, RT-3) — **NEVER** the body/header.
- mutating routes enforce `can(t, "write")` (the WHOLE resolved-tenant dict is the 1st arg, matching
  workflow-studio — NOT `(tenant_id, action)`); reads enforce `can(t,"read")` where the module had it.
- `need_auth()` / `forbidden()` are no-arg (workflow-studio convention).
- missing token → `need_auth()` (401); no perm → `forbidden()` (403).
- **`is_admin` is NEVER body-derived.** booking hardcodes `is_admin=False` into every `core.*` call
  (it feeds `db.engine.session(tenant_id, is_admin)` where `is_admin=1` BYPASSES RLS — a 2nd hole closed).

### Per-module specifics
- **media-gen** — the no-arg module-level `router = build_router()` would have **broken import-smoke** the
  moment `build_router` gained required auth params (TypeError at `import media_gen.router`). FIX: the old
  no-auth body-reading router is renamed `_bare_router()` (kept ONLY for the 12-endpoint route-introspection
  smoke, marked DO-NOT-MOUNT) and `router = _bare_router()`; the NEW `build_router(...)` is the authenticated
  mountable surface. Video submit **OVERWRITES** `brief["tenant_id"] = token_tenant` (not setdefault) so a
  body tenant can't win. By-`job_id` routes (get/poll/approve/reject/cancel) now load via `store.read` and
  enforce `rec["tenant_id"] == token_tenant` else `error:no_such_job` (store.read does NOT filter by tenant).
  `/video/webhook` stays UNAUTHENTICATED on both surfaces (provider-signed, matched by external_id).
- **booking** — added `build_router(...)`; kept the bare `router` + default `get_ctx` (decoupled-for-test).
  The risky `/tick` spend still flows through `core.tick`'s own firewall(PIN, fail-closed)+wallet gates with
  the body-supplied `pin` (pin legitimately stays in the body — only tenant/is_admin move to the token).
- **funnels** — added `build_router(...)`; kept the bare `router`. Updated the module docstring to say
  DO NOT mount the bare router and DO NOT apply `funnel_wiring.diff`. `published_by`/`actor` default to the
  token's actor. `/validate` (pure body-validate, no persistence) is gated behind auth but needs no tenant scope.

## WHAT STAYED IN THE BODY (intentional — only tenant_id + is_admin moved to the token)
`pin`, `approver`, `published_by`, `actor`, `slot_start/end`, `name`, `stages`, `guards`, `seed`,
`industry_pack`, `to_spaces`, the video/image brief fields — all legitimately remain body fields.

## FILES CHANGED (3; routers only — NO core/caller/agent edits)
- `droplet_work/media_gen/router.py`  — `build_router` is now authenticated; old body-router → `_bare_router()`.
- `droplet_work/booking/router.py`     — added `build_router(...)`; bare `router`/`get_ctx` untouched.
- `droplet_work/funnels/endpoints.py`  — added `build_router(...)`; bare `router` untouched; docstring hardened.

## VERIFICATION (fastapi 0.115.6 / py3.14 present, so the discriminating test was run)
- **Import-smoke** — all three import clean; media-gen bare router still exposes 12 routes.
- **Discriminating security test** (resolve_tenant→"A", attacker body/header tenant_id="B"): asserted the
  core/store layer is invoked with **"A"** in all three —
  - booking `/book`: spoofed `X-Tenant-Id:B` + body B → `core.book` saw `A`, `is_admin=False`. PASS.
  - media-gen `/video/jobs`: body B → `submit_video_job` brief saw `A`. PASS. Cross-tenant `job_id` read
    (A reading a B-owned job) → `error:no_such_job`. PASS.
  - funnels `/{id}/run`: body B → `_run` saw `A`. PASS.
  - missing token → 401 (all three); no `write` perm → 403 (funnels). PASS.
- **Regression suites (files I edited are imported by these):** booking 25/25 · funnels 8/8 (PYTHONPATH
  `.;workflow-studio`) · media-gen 19/19. `py_compile` clean on all three.

## MOUNT NOTES FOR THE ORCHESTRATOR (the deferred caller.py step)
- booking: mount `build_router(...)` — supersedes the `REMAINING_MODULES_BUILD_STATE.md` "override get_ctx"
  instruction (a clean token-deriving surface now exists; do NOT mount the bare `router`/header-trust ctx).
- media-gen: mount `build_router(resolve_tenant, can, need_auth, forbidden)` — supersedes the no-arg
  `build_router()` row; do NOT mount the module-level `router` (`_bare_router`, test-only).
- funnels: mount `build_router(...)` — the row-9 build-blocker is RESOLVED; still mount workflow-studio FIRST
  and keep `droplet_work/workflow-studio` on PYTHONPATH; do NOT apply `funnel_wiring.diff`.
- All three keep the `firewall=None` 5th param for signature-uniformity with workflow-studio/payments/support.
