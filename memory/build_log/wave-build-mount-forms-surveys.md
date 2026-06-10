# WAVE BUILD -- MOUNT: forms-surveys router into caller.py (sequential spine) -- PLATFORM-ENG

Date: 2026-06-10. Scope: mount ONLY (build_router include), behind an import-guard + FEATURE flag
DEFAULT-OFF. Source of truth: LIVE box `famit@168.144.153.145:/opt/famit-agent/` (venv
`/opt/capsy-agent/.venv`, py3.12.3). NO git. THE LIVE EARNER -- reconcile-first + dormant-by-flag.
Result: **forms-surveys: mounted + gate GREEN (flag OFF).**

## PATTERN = build_router (checklist row #4) -- like media-gen/booking, NOT wire() like payments/support
forms-surveys ships a CLEAN token-deriving surface: `build_router(resolve_tenant, can, need_auth,
forbidden, *, ratelimit=None, audit=None)`. Authed CRUD (`/forms*`) resolves tenant ONLY from the token
via the injected `resolve_tenant`; org_id = the resolved tenant_id (NEVER a body/query param); writes
enforce `can(t,"write")`, reads `can(t,"read")`; is_admin token-derived (feeds db.engine.session -> RLS).
PUBLIC routes `/f/{public_token}` (render) + `/f/{public_token}/submit` are intentionally UNAUTHENTICATED
by design -- no authenticated tenant on the public path, so org_id is SERVER-DERIVED from the form record
resolved by the unguessable public_token (secrets.token_urlsafe). Anti-abuse on the unauth endpoint lives
in router/core (per-(token,IP) ratelimit, raw-body cap pre-parse, honeypot silent-drop, allow-list schema
validation, sha256(ip+token) forensics, tenant-scoped audit written INSIDE core where org_id is in scope).
Router has NO prefix -- paths are absolute, so `app.include_router(_forms_router)` (no prefix arg).

## TWO LOAD-BEARING TRAPS THAT THE ADVISOR CAUGHT BEFORE WRITING
1. **forms build_router has NO `firewall` param** (forms are FREE -- no spend/wallet). media-gen/booking
   (the adjacent blocks) call `_build_*(rt, can, na, _forbidden, firewall=_firewall_mod)`. Copying that
   `firewall=` kwarg into forms = TypeError -> swallowed by the except -> flag-on SILENTLY mounts nothing
   while the gate looks green. We pass ONLY the 4 positional auth helpers:
   `_build_forms_router(resolve_tenant, can, need_auth, _forbidden)`. ratelimit/audit fall back to the
   router's own import-guarded `import ratelimit`/`import audit` (both confirmed importable in box venv).
2. **init() DELIBERATELY DEFERRED (byte-identical-when-OFF trap, same as payments/support/booking).**
   `core.init()` (line 63-79) calls `ensure_schema()` (line 76) which applies DDL when PG is reachable --
   and box PG IS up (`[db.engine] Postgres available`). Calling init() with the flag OFF would touch the
   live PG. So init() is NOT called this wave. `build_router` stands alone: routes call `core.*` directly;
   `ensure_schema()` is LAZY (first-use, `_schema_ready`-guarded, never raises) so schema applies only on
   the first authed call AFTER the flag is on. The deferred `emit_lead`/`emit_workflow` hooks
   (init(emit_lead=, emit_workflow=)) are likewise DEFERRED (per the mod build log).

## HYPHENATED-PACKAGE IMPORT (the forms-specific wrinkle vs support/payments)
The dir is `forms-surveys` -- not a legal Python identifier, so a plain `from forms_surveys... import`
cannot find it. The mount block registers the package under the alias `forms_surveys` in sys.modules via
`importlib.util.spec_from_file_location('forms_surveys', __init__, submodule_search_locations=[pkgdir])`
INLINE (self-contained -- no dependency on the package's own `_bootstrap.py`, which itself lives in the
hyphenated dir and would have the same import problem). Idempotent: reuses `sys.modules['forms_surveys']`
if already loaded. Then `_build_forms_router = _fs_pkg.build_router`. All inside the import-guard try/except
(-> None on any failure -> mounts nothing, never crashes startup).

## WHAT WAS DONE
1. Reconcile-first: local caller.py md5 == box md5 `babf0494480e9a1395e578f9e721ed21` (post-support-mount
   HEAD) BEFORE editing. grep proved NO pre-existing FEATURE_FORMS / forms_surveys / forms-surveys refs.
   Both services active. forms-surveys/ package NOT yet on box.
2. Read `forms-surveys/endpoints.py` (build_router signature -- POSITIONAL 4 auth helpers + KEYWORD-ONLY
   ratelimit/audit; NO firewall param; need_auth()/forbidden() called no-arg; resolve_tenant(request)),
   `__init__.py` (re-exports build_router + init + status), `_bootstrap.py` (alias loader), `core.init()`
   (calls ensure_schema -> deferred). Confirmed caller.py's two `@app.middleware("http")` handlers are
   rate-limit + metrics ONLY (no global auth wall) -> the public `/f/` routes are reachable as designed
   (the mod build-log's open mount-time question #4 -- RESOLVED: per-route auth, no global gate).
3. Deployed `forms-surveys/` to `/opt/famit-agent/forms-surveys/` via tar
   (`--exclude=__pycache__ --exclude=*.pyc` -- the support .pyc-leak lesson). Verified ZERO .pyc/
   __pycache__ on box. Files: __init__/core/endpoints/identity/config/_bootstrap + schema.sql + tests.
4. BARE UNGUARDED import smoke in the BOX venv (py3.12.3, load-bearing -- the guarded spine import goes
   green even if the package is broken = false pass): alias import OK; `build_router(stubs)` = **10 route
   objects / 8 unique paths** (6 authed /forms* + 2 public /f/*); `core.status()` returned without raising
   (`configured:False, pg_available:False, audit_wired:True`); `audit` + `ratelimit` both IMPORTABLE in
   the box venv (the build_router fallback path works).
5. MOUNT BLOCK appended at END of caller.py (after the support block; app+helpers fully defined -> no
   circular import), pure ASCII. import-guard -> FEATURE_FORMS default OFF -> `if FEATURE_FORMS and
   _build_forms_router is not None:` -> `_build_forms_router(resolve_tenant, can, need_auth, _forbidden)`
   -> `app.include_router(_forms_router)`, all try/except-guarded (mount failure logs
   "forms-surveys router mount failed", never crashes the spine). NO .env change at rest.
6. Backups BEFORE scp of the edited file: local `caller.py.MNTbak.1781076772` + box
   `caller.py.MNTbak.1781076772` (both md5 `babf0494...` = clean post-support rollback target).

## INSTANTIATE-SMOKE (box venv, from /opt/famit-agent, BEFORE restart) -- PASS
Ran the spine smoke FROM `/opt/famit-agent` (NOT /tmp -- the stale-/tmp/caller.py shadow lesson).
- `py_compile caller.py` OK (local + box venv on the REAL deployed file).
- flag OFF (default): `import caller` clean; `caller.__file__=/opt/famit-agent/caller.py`; TOTAL **79**
  routes (== pre-mount support state -> byte-identical); **0** /forms paths; `_build_forms_router` LOADED
  (import-guard did NOT null it -> alias import works in the real spine); legacy /me,/campaigns,/leads,
  /contacts,/run,/billing/overview all present.
- `FEATURE_FORMS=1`: imports clean; **8** /forms* + /f/* paths mounted (TOTAL **89** = 79+10 route objs):
  /forms, /forms/status, /forms/{id}, /forms/{id}/insights, /forms/{id}/rotate-token,
  /forms/{id}/submissions, /f/{token}, /f/{token}/submit.
- NOTE: box logs `[db.engine] Postgres available` -- PG IS up. With the flag ON, forms routes would hit
  PG, but forms/form_submissions apply LAZILY via ensure_schema() on first use (idempotent FORCE-RLS DDL,
  NOT Alembic). Flag stays OFF: dormant-by-flag, no schema touched on the live earner.

## DEPLOY + RESTART
- scp edited caller.py -> box; md5 box==local `68218dfa17bf7171602ec67ac09512e3` (+72 LOC vs support state).
- `sudo systemctl restart famit-caller`. New PID 1361386: "Application startup complete", "Uvicorn running
  on 0.0.0.0:8209". No ImportError/ModuleNotFound/Traceback/"forms-surveys router mount failed". Both
  famit-caller + famit-agent active.

## REGRESSION GATE -- GREEN (legacy `X-Auth: FamitCall2026`, loopback 127.0.0.1:8209)
- `/me` 200 . `/campaigns` 200 . `/leads` 200 . `/contacts` 200 . `/billing/overview` 200.
- `/forms` = **404** . `/forms/status` = **404** . `/f/NONEXISTENTTOKEN` = **404** (flag OFF -> correctly
  NOT mounted; unchanged).
- **/run DISPATCH GATE (no paid call)** -- pre-seed `+910000000068` into suppression
  (`{"added":0,"total":2}`), then `POST /run campaign_id=c17e55e9f3 leads=+910000000068` (form) -> 200
  `{"job_id":"2ef0785035","count":1,"suppressed_count":1}`. count=1 => lead ENTERED pipeline (dispatch
  works); suppressed_count=1 => the only lead was suppressed => dial loop dials NOBODY => NO paid call.
- ZERO 5xx/traceback in the post-restart window. Final md5 box==local `68218dfa17bf7171602ec67ac09512e3`.

## ROLLBACK RECIPE (if ever needed)
`cp /opt/famit-agent/caller.py.MNTbak.1781076772 /opt/famit-agent/caller.py && sudo systemctl restart
famit-caller` (restores the post-support-mount original `babf0494...`; the forms-surveys/ package is inert
when not mounted).

## TO GO LIVE LATER (DEFERRED -- orchestrator/founder action)
1. Set `FEATURE_FORMS=1` in `/opt/famit-agent/.env` + restart famit-caller -> 8 /forms* + /f/* routes
   mount (authed CRUD token-derived, org_id = resolved tenant; public /f/ unauth, org server-derived
   from the public_token).
2. Schema: `ensure_schema()` applies forms/form_submissions LAZILY on first authed call (idempotent
   ENABLE+FORCE RLS admin-GUC-OR-org_id DDL, NOT Alembic -- kept out of the P1 keystone chain). No manual
   migration. (Optional: psql -f forms-surveys/schema.sql to apply eagerly + prove RLS/UNIQUE on the box.)
3. Wire the DEFERRED injected hooks (call `forms.core.init(emit_lead=, emit_workflow=, audit=audit)` INSIDE
   the flag-on block when activated): the authoritative leads-store write (via the EXISTING lead writer,
   NOT a direct leads INSERT -- leads is dual-mirrored; a stray PG write drifts the shadow mirror) + the
   workflow-trigger emission (into the workflow-studio event bridge once workflow is mounted).
4. Creds (dormant-until-set): captcha `FORMS_CAPTCHA_PROVIDER`+`FORMS_CAPTCHA_SECRET` (stub fail-open until
   provider HTTP verify wired -- an unwired verifier NEVER returns 'passed'); `FORMS_NOTIFY_ENABLED`+sender
   for on-submit notify; `FORMS_INSIGHTS_LLM` for LLM survey-insight summary (default OFF, never on the
   submit/insights hot path -- insights are deterministic SQL/Python).
5. Frontend form/survey builder + public hosted render page (Section B/G sidebar surfaces).

## MOUNT ORDER NOW (caller.py tail, all flag-gated DEFAULT-OFF)
ads-engine -> media-gen -> booking -> payments -> support -> **forms-surveys** (this wave). Remaining
checklist rows: workflow-studio (build_router + attach_event_bridge, BEFORE funnels), ai-manager (bare-OK
include_router, token-derived), funnels (BLOCKED -- needs a token-deriving build_router BUILT first; do
NOT apply funnel_wiring.diff as-is; mount AFTER workflow on PYTHONPATH).
