# WAVE BUILD — MOUNT: funnels router into caller.py (sequential spine) — PLATFORM-ENG

Date: 2026-06-10 (crash-recovery pass). Scope: mount ONLY (build_router include), behind an import-guard +
FEATURE flag DEFAULT-OFF. Source of truth: LIVE box `famit@168.144.153.145:/opt/famit-agent/`
(venv `/opt/capsy-agent/.venv`, py3.12). NO git. THE LIVE EARNER — reconcile-first + dormant-by-flag.
Result: **funnels: mounted + gate GREEN (flag OFF). The checklist's BLOCKED row #9 is RESOLVED.**

## ⚠ SECURITY: the "BLOCKED" status was STALE — the token-deriving build_router ALREADY EXISTS
REMAINING_MODULES_BUILD_STATE.md row #9 marked funnels BLOCKED because, when written, funnels only had a
bare `router` that reads `tenant_id=payload.get("tenant_id")` FROM THE BODY (endpoints.py L63-122) and the
shipped `funnel_wiring.diff` mounted THAT bare router = cross-tenant hole. SINCE THEN the 2026-06-10
security fix ADDED a CLEAN `build_router(resolve_tenant, can, need_auth, forbidden, firewall)` to
funnels/endpoints.py (L132) — the SAME shape as workflow-studio/forms-surveys. Verified by Read (L158-268):
EVERY route does `t = resolve_tenant(request); if not t: return need_auth()`, tenant_id is ALWAYS `_tid(t)`
= `t["tenant_id"]` (token-derived, NEVER body), writes enforce `can(t,"write") else forbidden()`.
Because publish/run DELEGATE to the workflow engine, deriving tenant from the TOKEN here is exactly what
stops an attacker body-tenant from flowing into workflow.publish/run.
**WE MOUNTED build_router, NOT the bare router. WE DID NOT APPLY funnel_wiring.diff** (it mounts the bare
body-tenant router = the hole; it is inert text in the package, ignored). This is the build-state §9 must-fix
SATISFIED, not bypassed.

## NO init()/ensure_schema TO DEFER
`make_store()` defaults to the IN-MEMORY backend unless `FUNNELS_STORE=pg` (config.store_mode default
"memory"), so even flag-ON the live PG is NOT touched. No DDL. `config.killswitch()` (FUNNELS_KILLSWITCH) is
a separate runtime break-glass, NOT this mount flag. funnels lazy-`import workflow` to delegate publish/run;
the workflow package is already on the box (mounted prior wave), so it resolves for free — mounted AFTER
workflow-studio as required.

## WHAT WAS DONE
1. Reconcile-first: local `droplet_work/caller.py` md5 == box md5 `5cc2d6b4aac874831d7afca9d4867986`
   (4361 LOC, post-ai-manager HEAD) BEFORE editing. grep proved NO pre-existing funnels/FEATURE_FUNNELS/
   `/funnels` refs (clean slate). `funnels/` package NOT yet on box.
2. Read funnels/endpoints.py build_router (L132-268) + __init__.py + config/store — confirmed token-derived,
   in-memory default, lazy workflow import. __init__ does NOT re-export build_router → import from endpoints.
3. Deployed `funnels/` to `/opt/famit-agent/funnels/` via pyc-stripped tarball. Verified ZERO .pyc on box.
   (funnel_wiring.diff ships inside the pkg as inert text — NOT applied.)
4. BARE UNGUARDED import smoke in the BOX venv (py3.12, load-bearing): `from funnels.endpoints import
   build_router` resolved CLEAN; build_router(stubs) → prefix `/funnels`, 11 route objects; `import funnels`
   + `funnels.status()` resolved AND `funnels._workflow()` found the workflow engine (workflow_engine.status
   = full workflow-studio descriptor, in_process, store=memory) → delegation path works; store=memory.
5. MOUNT BLOCK appended at END of caller.py (AFTER the ai-manager block, AFTER workflow), mirroring the
   workflow-studio build_router block:
   - import-guard: `try: from funnels.endpoints import build_router as _build_funnels_router / except: None`
   - `FEATURE_FUNNELS = (cfg_get("FEATURE_FUNNELS","0") or "0").strip().lower() in (...)` DEFAULT OFF
   - `if FEATURE_FUNNELS and _build_funnels_router is not None:` → `_build_funnels_router(resolve_tenant,
     can, need_auth, _forbidden, firewall=_firewall_mod)` → `app.include_router(...)`, all try/except-guarded
     (mount failure logs "funnels router mount failed", never crashes the spine).
   - NO .env change at rest: default-OFF from cfg_get default → resting deployed state unchanged.
6. Backup BEFORE scp of edited file: box `caller.py.MNTbak2.1781081810` (md5 `5cc2d6b4...` = clean
   post-ai-manager rollback target).

## INSTANTIATE-SMOKE (box venv, from /opt/famit-agent, BEFORE restart) — PASS
- `py_compile caller.py` OK (local + box venv).
- SPINE smoke `import caller`, BOTH flag states (`caller.__file__=/opt/famit-agent/caller.py`):
  - flag OFF (default): 0 /funnels paths, **total 79** (== pre-mount HEAD) → byte-identical.
  - `FEATURE_FUNNELS=1`: **10 unique /funnels paths** (11 route objs — GET+POST collapse on /funnels),
    total 90: /funnels,/funnels/status,/templates,/templates/{id}/instantiate,/validate,/{id},
    /{id}/analytics,/{id}/publish,/{id}/run,/{id}/validate.

## DEPLOY + RESTART
- scp edited caller.py → box; md5 box==local `bb87bd18b49c9dea152728fb7e92af60` (4404 LOC, +43 vs HEAD).
- `sudo systemctl restart famit-caller`. New PID 1377579: "Application startup complete", "Uvicorn running
  on 0.0.0.0:8209". No ImportError/ModuleNotFound/Traceback/"funnels router mount failed". Both
  famit-caller + famit-agent active.

## REGRESSION GATE — GREEN (legacy `X-Auth: FamitCall2026`, loopback 127.0.0.1:8209)
- `/me` 200 · `/campaigns` 200 · `/leads` 200 · `/contacts` 200 · `/billing/overview` 200.
- `/funnels/status` = **404** · `/funnels` = **404** (flag OFF → correctly NOT mounted; behavior unchanged).
- **/run DISPATCH GATE (no paid call):** pre-seed `+910000000068` into suppression, then
  `POST /run campaign_id=c17e55e9f3 leads=+910000000068` (form) → 200
  `{"job_id":"3c8a706e8c","count":1,"suppressed_count":1}`. count=1 ⇒ dispatch works; suppressed_count=1 ⇒
  dial loop dials NOBODY ⇒ NO paid call.
- ZERO 5xx/traceback in the post-restart window. Final md5 box==local `bb87bd18b49c9dea152728fb7e92af60`.

## ROLLBACK RECIPE (if ever needed)
`cp /opt/famit-agent/caller.py.MNTbak2.1781081810 /opt/famit-agent/caller.py && sudo systemctl restart famit-caller`
(restores the post-ai-manager original `5cc2d6b4...`; the funnels/ package is inert when not mounted).

## TO GO LIVE LATER (DEFERRED — founder action)
Set `FEATURE_FUNNELS=1` in `/opt/famit-agent/.env` + restart → 10 /funnels paths mount (authed,
token-derived, delegates to the workflow engine). REQUIRES `FEATURE_WORKFLOWS=1` to be useful (publish/run
delegate to workflow; with workflow off, funnels publish/run return not_configured). Persistence: in-memory
unless `FUNNELS_STORE=pg`. Optional dormant integrations `FUNNELS_LANDING_API_KEY`, `FUNNELS_REVIEW_API_KEY`.
Break-glass `FUNNELS_KILLSWITCH=1`.

## MOUNT ORDER NOW — ALL 9 MODULES MOUNTED (caller.py tail, all flag-gated DEFAULT-OFF)
ads-engine → media-gen → booking → payments → support → forms-surveys → workflow-studio → ai-manager →
**funnels**. THE MOUNT CHECKLIST IS COMPLETE (9/9). Resting state = 79 routes, byte-identical.
