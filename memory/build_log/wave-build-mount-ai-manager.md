# WAVE BUILD — MOUNT: ai-manager router into caller.py (sequential spine) — PLATFORM-ENG

Date: 2026-06-10 (crash-recovery pass). Scope: mount ONLY (router include), behind an import-guard +
FEATURE flag DEFAULT-OFF. Source of truth: LIVE box `famit@168.144.153.145:/opt/famit-agent/`
(venv `/opt/capsy-agent/.venv`, py3.12). NO git. THE LIVE EARNER — reconcile-first + dormant-by-flag.
Result: **ai-manager: mounted + gate GREEN (flag OFF).**

## PATTERN = bare include_router (BARE-OK / TOKEN-DERIVED — same class as ads-engine, checklist row #1)
ai_manager.endpoints derives tenant ONLY from the authenticated request via a LAZY
`import caller; caller.resolve_tenant(request)` (endpoints.py L42-47); tenant_id is ALWAYS t["tenant_id"]
(token), NEVER a body/query field (verified by Read: L116/119/131/139/155/165/182 all use t["tenant_id"]).
So `app.include_router(router)` is safe — no cross-tenant hole, NO build_router needed (would be dead code).
Reads enforce can(t,"read"), writes can(t,"write"); /numbers/{id}/grants + /revoke require
can(t,"manage_tenants") + firewall step-up (`_require_step_up`, pass-through when firewall off). The two
SERVICE-TOKEN routes (/numbers/lookup, POST /sessions) are DORMANT until AIM_SERVICE_TOKEN set (else 401).
Module-level `router = APIRouter(prefix="/ai-manager")`; None when FastAPI absent (guarded).

## NO init()/ensure_schema TO DEFER
ai-manager persists sessions as JSONL on the control plane (config.sessions_file) — NO PG, NO DDL. Nothing
schema-side to gate; the live PG is never touched, flag ON or OFF. The LiveKit voice front
(inbound_agent.py) + SIP dispatch are a SEPARATE later wire that does NOT pass through caller.py.

## WHAT WAS DONE
1. Reconcile-first: local `droplet_work/caller.py` md5 == box md5 `943bff85fc4cd2f79f1fe43ba0000869`
   (4324 LOC, post-workflow-mount HEAD) BEFORE editing. grep proved NO pre-existing ai_manager/
   FEATURE_AI_MANAGER / `/ai-manager` refs (clean slate). `ai_manager/` package NOT yet on box.
2. Read endpoints.py + __init__.py — confirmed token-derived (lazy caller.resolve_tenant, never body),
   router prefix /ai-manager, `status()` package export (endpoints L109 `from . import status`).
3. Deployed `ai_manager/` to `/opt/famit-agent/ai_manager/` via pyc-stripped tarball
   (`--exclude=__pycache__ --exclude=*.pyc`). Verified ZERO .pyc/__pycache__ on box.
4. BARE UNGUARDED import smoke in the BOX venv (py3.12) — the load-bearing check (a silent ImportError
   would null `_ai_manager_router` and mount nothing while the gate goes green = false pass):
   `from ai_manager.endpoints import router` resolved CLEAN; prefix `/ai-manager`, 9 route objects;
   `ai_manager.status()` returned without raising (11 keys incl firewall/intent_llm/otp).
5. MOUNT BLOCK appended at END of caller.py (AFTER the workflow block; app+helpers fully defined → no
   circular import), mirroring the ads-engine bare-include pattern:
   - import-guard: `try: from ai_manager.endpoints import router as _ai_manager_router / except: None`
   - `FEATURE_AI_MANAGER = (cfg_get("FEATURE_AI_MANAGER","0") or "0").strip().lower() in (...)` DEFAULT OFF
   - `if FEATURE_AI_MANAGER and _ai_manager_router is not None: app.include_router(_ai_manager_router)`
     (try/except-guarded; mount failure logs "ai-manager router mount failed", never crashes the spine).
   - NO .env change at rest: default-OFF from cfg_get default → resting deployed state unchanged.
6. Backup BEFORE scp of edited file: box `caller.py.MNTbak2.1781081110` (md5 `943bff85...` = clean
   post-workflow rollback target).

## INSTANTIATE-SMOKE (box venv, from /opt/famit-agent, BEFORE restart) — PASS
- `py_compile caller.py` OK (local + box venv).
- SPINE smoke `import caller`, BOTH flag states (`caller.__file__=/opt/famit-agent/caller.py`):
  - flag OFF (default): 0 /ai-manager paths, **total 79** (== pre-mount HEAD) → byte-identical.
  - `FEATURE_AI_MANAGER=1`: **7 unique /ai-manager paths** (9 route objs — GET+POST collapse on /numbers
    and /sessions), total 88: /ai-manager/status,/numbers,/numbers/lookup,/numbers/{id}/verify,
    /numbers/{id}/grants,/numbers/{id}/revoke,/sessions.

## DEPLOY + RESTART
- scp edited caller.py → box; md5 box==local `5cc2d6b4aac874831d7afca9d4867986` (4361 LOC, +37 vs HEAD).
- `sudo systemctl restart famit-caller`. New PID 1376500: "Application startup complete", "Uvicorn running
  on 0.0.0.0:8209". No ImportError/ModuleNotFound/Traceback/"ai-manager router mount failed". Both
  famit-caller + famit-agent active.

## REGRESSION GATE — GREEN (legacy `X-Auth: FamitCall2026`, loopback 127.0.0.1:8209)
- `/me` 200 · `/campaigns` 200 · `/leads` 200 · `/contacts` 200 · `/billing/overview` 200.
- `/ai-manager/status` = **404** · `/ai-manager/numbers` = **404** (flag OFF → correctly NOT mounted).
- **/run DISPATCH GATE (no paid call):** pre-seed `+910000000068` into suppression (`{"added":0,"total":2}`),
  then `POST /run campaign_id=c17e55e9f3 leads=+910000000068` (form) → 200
  `{"job_id":"172ae93855","count":1,"suppressed_count":1}`. count=1 ⇒ dispatch works; suppressed_count=1 ⇒
  dial loop dials NOBODY ⇒ NO paid call.
- ZERO 5xx/traceback in the post-restart window. Final md5 box==local `5cc2d6b4aac874831d7afca9d4867986`.

## ROLLBACK RECIPE (if ever needed)
`cp /opt/famit-agent/caller.py.MNTbak2.1781081110 /opt/famit-agent/caller.py && sudo systemctl restart famit-caller`
(restores the post-workflow-mount original `943bff85...`; the ai_manager/ package is inert when not mounted).

## TO GO LIVE LATER (DEFERRED — founder action)
Set `FEATURE_AI_MANAGER=1` in `/opt/famit-agent/.env` + restart → 7 /ai-manager paths mount (authed,
token-derived). Module stays DORMANT until creds: `AIM_SERVICE_TOKEN` (voice-worker lookup/sessions),
`AIM_VOICE_DID`/`AIM_VOICE_SIP_TRUNK_ID`/`AIM_VOICE_AGENT_NAME` (voice front), `AIM_OTP_PROVIDER`,
`AIM_LLM_PROVIDER`. LiveKit inbound_agent.py + SIP dispatch = separate later wire (not via caller.py).

## MOUNT ORDER NOW (caller.py tail, all flag-gated DEFAULT-OFF)
ads-engine → media-gen → booking → payments → support → forms-surveys → workflow-studio → **ai-manager**.
Remaining checklist row: funnels (BLOCKED — needs a token-deriving build_router BUILT first; do NOT apply
funnel_wiring.diff as-is; requires `import workflow`, now resolvable).
