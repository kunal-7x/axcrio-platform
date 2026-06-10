# WAVE BUILD — MOUNT: media-gen router into caller.py (sequential spine) — PLATFORM-ENG

Date: 2026-06-10. Scope: mount ONLY (router include), behind an import-guard + FEATURE flag DEFAULT-OFF.
Source of truth: LIVE box `famit@168.144.153.145:/opt/famit-agent/` (venv `/opt/capsy-agent/.venv`). NO git.
Result: **media-gen: mounted + gate GREEN (flag OFF).**

## WHY THIS DIFFERS FROM ads-engine (the tenant-isolation must-fix)
media-gen is a BODY-TENANT module: its bare module-level `media_gen.router.router` (`_bare_router()`)
reads `tenant_id` from the request body/query → mounting THAT is a cross-tenant hole. Per the build state,
we mounted the token-deriving AUTHENTICATED surface instead:
`build_router(resolve_tenant, can, need_auth, forbidden, firewall=None)`. This surface (already present in
`media_gen/router.py` from the 2026-06-10 security fix) derives tenant ONLY from the token
(`resolve_tenant(request)["tenant_id"]`), OVERWRITES `body["tenant_id"]` on video-submit + image-generate,
and enforces `rec["tenant_id"]==token` ownership on every by-job_id route. Video webhook is intentionally
unauthenticated (provider-signed, fail-closed, matched by external_id). Did NOT apply any bad bare diff.

## WHAT WAS DONE
1. Reconcile-first: local caller.py md5 == box md5 `8c0ab9e31349a637f98051d667c7a22f` (4033 LOC, post-ads-mount
   state) BEFORE editing. grep proved NO pre-existing media_gen/FEATURE_MEDIA/`/media` refs (clean slate).
   `media_gen/` package was NOT yet on the box.
2. Verified the injected helpers exist with matching signatures in caller.py:
   `resolve_tenant(request)->dict|None` (L404), `need_auth()->Response` (L436), `can(tenant,action)->bool`
   (L641), `_forbidden(msg="...")->JSONResponse` (L653 — passed as the `forbidden` callable; build_router calls
   it with zero args, default arg covers it), `_firewall_mod` (L103 import-guard — passed for forward-compat;
   firewall is reserved/not-yet-wired in build_router, so functionally inert today).
3. Deployed `media_gen/` package to `/opt/famit-agent/media_gen/` (18 .py files; __pycache__ stripped so no
   py3.14 .pyc leaks into the py3.12 venv).
4. BARE UNGUARDED import smoke in the BOX venv (py3.12) — `import media_gen.router` resolved CLEAN (the
   transitive `creative/*` + boto3 absences degrade gracefully: image/threed try/except → not_configured,
   boto3/httpx lazy-imported inside calls). `build_router(stubs)` produced prefix `/media`, 12 route objects.
   This was the advisor-flagged must-do: media_gen (unlike httpx-only ads_engine) has transitive deps, so a
   silent import-guard no-op was the risk — verified it does NOT trip.
5. MOUNT BLOCK appended at END of caller.py (after ads block, app+helpers fully defined → no circular import):
   - import-guard: `try: from media_gen.router import build_router as _build_media_router / except: None`
   - `FEATURE_MEDIA = (cfg_get("FEATURE_MEDIA","0") or "0").strip().lower() in ("1","true","yes","on")` DEFAULT OFF
   - `if FEATURE_MEDIA and _build_media_router is not None:` → `build_router(resolve_tenant, can, need_auth,
     _forbidden, firewall=_firewall_mod)` → `app.include_router(...)`, all try/except-guarded (a mount failure
     logs, never crashes the spine).
   - NO .env change at rest: default-OFF comes from the cfg_get default → resting deployed state unchanged.
6. Backups: local+box `caller.py.MNTbak.1781071064` (md5 `8c0ab9e3...` = clean rollback target = the
   post-ads-mount original). Local edited backup also at `caller.py.MNTbak.1781068286` lineage preserved.

## INSTANTIATE-SMOKE (box venv `/opt/capsy-agent/.venv/bin/python`, BEFORE restart)
- `py_compile caller.py` OK.
- SPINE smoke `import caller`, BOTH flag states:
  - flag OFF (default): caller imports clean; `_build_media_router` LOADED but NOT mounted; `/media` routes
    ABSENT (`FEATURE_MEDIA=False`) → byte-identical behavior.
  - `FEATURE_MEDIA=1`: caller imports clean; **12 `/media` route objects (11 unique paths)** present;
    GET+POST both mounted on `/media/video/jobs` (the one path that collapses two route objects).
  Proves mounted-vs-absent WITHOUT toggling the live service.

## DEPLOY + RESTART
- scp edited caller.py → box; md5 box==local `4a92b5145dbf7d856db444c423602cc3` (4070 LOC).
- `sudo systemctl restart famit-caller`. "Application startup complete", "Uvicorn running on 0.0.0.0:8209".
  No ImportError/ModuleNotFound/Traceback. `/health` = 200. Both `famit-caller` + `famit-agent` active.

## REGRESSION GATE — GREEN (legacy `X-Auth: FamitCall2026`, loopback 127.0.0.1:8209)
- `/me` 200 · `/campaigns` 200 · `/leads` 200 · `/contacts` 200 · `/billing/overview` 200.
- `/media/status` = **404** · `/media/video/jobs` = **404** (flag OFF → correctly NOT mounted; behavior unchanged).
- **/run DISPATCH GATE (no paid call) — the documented proven signal, traceable:**
  ⚠ `/run` AND `/suppression` take **FORM fields** (caller.py L2593 `campaign_id`/`leads` = `Form()`; L2834
  `numbers` = `Form()`), NOT JSON. A JSON body is silently ignored (first attempt gave a misleading
  `count=0`; corrected to `--data-urlencode`). Correct run:
  1. `POST /suppression numbers=+910000000068` (form) → 200; GET /suppression confirms `contains: True`.
  2. `POST /run campaign_id=c17e55e9f3 leads=+910000000068` (form) → 200
     `{"job_id":"1a99aaa360","count":1,"suppressed_count":1}`. count=1 ⇒ lead ENTERED the pipeline;
     suppressed_count=1 ⇒ it was suppressed ⇒ the dial loop dials NOBODY ⇒ NO paid call.
  3. Newest /calls record TRACEABLE to this run: `phone=+910000000068 status=suppressed outcome=suppressed
     campaign_id=c17e55e9f3` (not `calling`). /run dispatches (job_id minted) without placing a call.
- ZERO 5xx / traceback in the post-restart window. Final md5 box==local `4a92b5145dbf7d856db444c423602cc3`.

## ROLLBACK RECIPE (if ever needed)
`cp /opt/famit-agent/caller.py.MNTbak.1781071064 /opt/famit-agent/caller.py && sudo systemctl restart famit-caller`
(restores the post-ads-mount original `8c0ab9e3...`; the media_gen/ package is inert when not mounted).

## TO GO LIVE LATER (founder action)
Set `FEATURE_MEDIA=1` in `/opt/famit-agent/.env` + restart famit-caller → 12 `/media` routes mount (authed,
token-derived). Module stays DORMANT/`not_configured` until creds land: artifacts `SPACES_*`; video
`VIDEO_PROVIDER`+`VIDEO_API_KEY` (or REPLICATE/LUMA/HIGGSFIELD/SELFHOST token). creative/image_banner_studio +
creative/threed_model are NOT on the box → image/threed report not-importable (dormant contract) until those
packages are deployed. firewall step-up on approve is DEFERRED (reserved seam, not yet wired).

## DEFERRED (not in this mount; per build state)
- Repoint `creative/video_studio/engine.py` `automation.video.client` import → `media_gen.video.client`.
- Deploy creative/* re-export targets (image_banner_studio, threed_model) for live image/3D.
- Wire firewall.require_step_up on /media/video/jobs/{id}/approve (defence-in-depth).
- video selfhost_worker.py (Wan 2.2 DO GPU, breakeven-gated).
