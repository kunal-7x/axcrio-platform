# WAVE BUILD — MOUNT: ads-engine router into caller.py (sequential spine) — PLATFORM-ENG

Date: 2026-06-10. Scope: mount ONLY (router include), behind an import-guard + FEATURE flag DEFAULT-OFF.
Source of truth: LIVE box `famit@168.144.153.145:/opt/famit-agent/`. NO git (orchestrator commits).
Result: **ads-engine: mounted + gate GREEN (flag OFF).**

## WHAT WAS DONE
1. Reconcile-first: confirmed caller.py local==box md5 `6478885b9b7fbd6d14c49d79ca070106` (4006 LOC)
   BEFORE editing; grep proved NO pre-existing ads_engine/ads_router/FEATURE_ADS/`/ads` refs in caller.py
   (clean slate, no concurrent spine edit). `ads_engine/` package was NOT yet on the box.
2. Decision (advisor-confirmed): ads-engine router is **bare-OK / TOKEN-DERIVED** — `endpoints._auth_helpers()`
   lazily imports `caller.resolve_tenant/need_auth/can`; org_id ALWAYS from `t["tenant_id"]` (token), NEVER
   body/header. So a plain `app.include_router` is safe (no cross-tenant hole). The task's tenant-isolation
   warning + "build a token-deriving build_router" applies to booking/media-gen/funnels (which read tenant
   from body), NOT to ads-engine. Did NOT build a build_router for ads (not needed, would be dead code).
3. MOUNT BLOCK appended at END of caller.py (after all routes + helpers exist — neutralizes circular import):
   - import-guard (house pattern): `try: from ads_engine.endpoints import router as _ads_router / except: None`
   - `FEATURE_ADS = (cfg_get("FEATURE_ADS","0") or "0").strip().lower() in ("1","true","yes","on")` — DEFAULT OFF
   - `if FEATURE_ADS and _ads_router is not None: app.include_router(_ads_router)` (try/except-guarded)
   - NO scheduler `poll_and_enforce` tick (explicitly DEFERRED — scope = router mount only).
   - NO .env change: default-OFF comes from the cfg_get default, so the resting deployed state is unchanged.
4. Local backup `caller.py.MNTbak.1781068234`; box backup `caller.py.MNTbak.1781068286`
   (md5 of box backup == `6478885b...` = the unmodified original = clean rollback target).
5. Deployed: scp `ads_engine/` package + new caller.py. New caller.py md5 box==local `8c0ab9e31349a637f98051d667c7a22f`.

## INSTANTIATE-SMOKE (the REAL venv = `/opt/capsy-agent/.venv/bin/python`, NOT famit-agent's .venv)
- Package smoke: `import ads_engine.endpoints` in venv -> APIRouter prefix `/ads`, 7 routes, healthcheck dict. OK.
- SPINE smoke (`import caller`, BEFORE restart), both flag states:
  - flag OFF (default): caller imports clean; `_ads_router` LOADED but NOT mounted; `/ads` routes ABSENT
    (`FEATURE_ADS=False`) -> byte-identical behavior.
  - `FEATURE_ADS=1`: caller imports clean; all 7 `/ads` routes PRESENT; total routes 86.
  This single pair proved BOTH "mounts when flagged on" AND "byte-identical default" WITHOUT toggling the
  live service. (Also catches any syntax/circular/import error the package-only smoke could not.)

## DEPLOY + RESTART
- `sudo systemctl restart famit-caller`. New PID started: "Application startup complete", "Uvicorn running
  on 0.0.0.0:8209". `/health` = 200. No ImportError/ModuleNotFound/Traceback.

## REGRESSION GATE — GREEN (legacy X-Auth = `X-Auth: FamitCall2026`, loopback 127.0.0.1:8209)
- `/me` 200 · `/campaigns` 200 · `/leads` 200 · `/contacts` 200 · `/billing/overview` 200.
- `/ads/health` = **404** (flag OFF -> correctly NOT mounted; live behavior unchanged).
- **/run DISPATCH GATE (no paid call)** — used the build-log-proven method: PRE-SEED `+910000000066` into
  suppression FIRST (POST /suppression 200), THEN POST /run campaign=`c17e55e9f3` leads=`+910000000066`
  -> 200 `{"job_id":"034d10f10b","count":1,"suppressed_count":1}`. suppressed_count=1 => dial loop dials
  NOBODY. Confirmed: newest /calls record for the test number = `status=suppressed outcome=suppressed`
  (NOT "calling"). NO paid call placed. (Older `done/voicemail` records are the prior P1-wave artifact,
  not this run.)
- Both services active: `famit-caller` + `famit-agent`. ZERO 5xx / traceback in the post-restart window.
- Final md5 box==local: `8c0ab9e31349a637f98051d667c7a22f`.

## ROLLBACK RECIPE (if ever needed)
`cp /opt/famit-agent/caller.py.MNTbak.1781068286 /opt/famit-agent/caller.py && sudo systemctl restart famit-caller`
(restores the unmodified original; the ads_engine/ package is inert when not mounted, leave or remove).

## TO GO LIVE LATER (founder action)
Set `FEATURE_ADS=1` in `/opt/famit-agent/.env` + restart famit-caller -> /ads routes mount. Module stays
DORMANT/no-op (`/ads/health` -> not_configured providers) until Meta/Google creds + LLM_ROUTER_URL land
(see REMAINING_MODULES_BUILD_STATE.md §D ads-engine). Scheduler poll tick is still DEFERRED (separate unit).
