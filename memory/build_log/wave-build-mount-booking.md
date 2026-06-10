# WAVE BUILD — MOUNT: booking router into caller.py (sequential spine) — PLATFORM-ENG

Date: 2026-06-10. Scope: mount ONLY (router include), behind an import-guard + FEATURE flag DEFAULT-OFF.
Source of truth: LIVE box `famit@168.144.153.145:/opt/famit-agent/` (venv `/opt/capsy-agent/.venv`). NO git.
Result: **booking: mounted + gate GREEN (flag OFF).**

## WHY THIS DIFFERS (the tenant-isolation must-fix)
booking is a HEADER-TENANT module on its bare surface: its module-level `router` + default `get_ctx`
trust the `X-Tenant-Id` header (spoofable) → cross-tenant hole. Per the build state, we mounted the
token-deriving AUTHENTICATED surface instead:
`build_router(resolve_tenant, can, need_auth, forbidden, firewall=None)` (added by the 2026-06-10
security fix, supersedes the old "override get_ctx" instruction). This surface derives tenant ONLY from
the token (`resolve_tenant(request)["tenant_id"]`), enforces `can(t,"write")` on writes / `can(t,"read")`
on reads, and HARDCODES `is_admin=False` into every `core.*` call (is_admin feeds
`db.engine.session(tenant_id, is_admin)` where is_admin=1 BYPASSES RLS — never body/header/claim-derived).
The risky `/tick` reminder spend self-gates in `core.tick` (firewall PIN fail-closed + wallet, body pin).
Did NOT mount the bare `router`/header-trust ctx.

## WHAT WAS DONE
1. Reconcile-first: local caller.py md5 == box md5 `4a92b5145dbf7d856db444c423602cc3` (post-media-gen-mount
   state) BEFORE editing. grep proved NO pre-existing booking/FEATURE_BOOKING/`/booking` refs (clean slate).
   `booking/` package was NOT yet on the box.
2. Verified the injected helpers exist with matching signatures (same as media-gen mount):
   `resolve_tenant(request)->dict|None` (L404), `need_auth()->Response` (L436), `can(tenant,action)->bool`
   (L641), `_forbidden(msg="...")->JSONResponse` (L653 — default arg covers the zero-arg call build_router
   makes), `_firewall_mod` (L105 import-guard — passed for signature-uniformity; risky tick self-gates in core).
3. Deployed `booking/` package to `/opt/famit-agent/booking/` via tar (7 core .py + tests + rls.sql;
   `__pycache__`/`*.pyc` stripped so no py3.14 .pyc leaks into the py3.12 venv). Verified NO .pyc on box.
4. BARE UNGUARDED import smoke in the BOX venv (py3.12) — the advisor-flagged must-do (the import-guard
   would otherwise SILENTLY set `_build_booking_router=None` and mount nothing on a hidden ImportError).
   `import booking.router` resolved CLEAN; `build_router(stubs)` produced prefix `/booking`, **10 route
   objects / 10 unique paths** (no GET+POST path collapse — unlike media-gen's /video/jobs).
5. MOUNT BLOCK appended at END of caller.py (after the media-gen block; app+helpers fully defined → no
   circular import), mirroring the media-gen block EXACTLY:
   - import-guard: `try: from booking.router import build_router as _build_booking_router / except: None`
   - `FEATURE_BOOKING = (cfg_get("FEATURE_BOOKING","0") or "0").strip().lower() in ("1","true","yes","on")` DEFAULT OFF
   - `if FEATURE_BOOKING and _build_booking_router is not None:` → `build_router(resolve_tenant, can,
     need_auth, _forbidden, firewall=_firewall_mod)` → `app.include_router(...)`, all try/except-guarded
     (a mount failure logs `"booking router mount failed"`, never crashes the spine).
   - NO .env change at rest: default-OFF comes from the cfg_get default → resting deployed state unchanged.
6. Backups (advisor backup-ordering): box backup `caller.py.MNTbak.1781072100` (md5 `4a92b514...` = clean
   rollback target = post-media-gen-mount original) taken BEFORE scp of the edited file.

## INSTANTIATE-SMOKE (box venv `/opt/capsy-agent/.venv/bin/python`, BEFORE restart)
- `py_compile caller.py` OK.
- SPINE smoke `import caller`, BOTH flag states (running service unaffected until restart → safe):
  - flag OFF (default): caller imports clean; `_build_booking_router` LOADED but NOT mounted; `/booking`
    routes mounted = **0** → byte-identical behavior.
  - `FEATURE_BOOKING=1`: caller imports clean; **10 `/booking` unique paths** mounted.
  Proves mounted-vs-absent WITHOUT toggling the live service.
- NOTE: box logs `[db.engine] Postgres available` — PG IS up. So with the flag ON, booking endpoints
  would hit PG, but the booking tables DO NOT EXIST yet (Alembic 0003_booking + rls.sql apply is the
  DEFERRED next step, NOT part of this mount). That is exactly why the flag stays OFF. The mount is
  correct: dormant-by-flag, no schema touched on the live earner.

## DEPLOY + RESTART
- scp edited caller.py → box; md5 box==local `dad2997f0338f8c38c55358e13c93779` (post-booking-mount).
- `sudo systemctl restart famit-caller`. "Application startup complete", "Uvicorn running on 0.0.0.0:8209".
  No ImportError/ModuleNotFound/Traceback. Both `famit-caller` + `famit-agent` active.

## REGRESSION GATE — GREEN (legacy `X-Auth: FamitCall2026`, loopback 127.0.0.1:8209)
- `/me` 200 · `/campaigns` 200 · `/leads` 200 · `/contacts` 200 · `/billing/overview` 200.
- `/booking/status` = **404** · `/booking/bookings` = **404** (flag OFF → correctly NOT mounted; unchanged).
- **/run DISPATCH GATE (no paid call) — proven form-field recipe (NOT JSON; /run+/suppression take Form()):**
  1. `POST /suppression numbers=+910000000068` (`--data-urlencode`) → `{"added":0,"total":2}`; GET /suppression
     confirms `910000000068` present (suppressed).
  2. `POST /run campaign_id=c17e55e9f3 leads=+910000000068` (form) → 200
     `{"job_id":"453fff2e84","count":1,"suppressed_count":1}`. count=1 ⇒ lead ENTERED pipeline (dispatch works);
     suppressed_count=1 ⇒ the only lead was suppressed ⇒ dial loop dials NOBODY ⇒ NO paid call.
  3. Newest /calls record TRACEABLE: `id=6b37eface0 phone=+910000000068 status=suppressed outcome=suppressed
     answered=false duration_s=0 campaign_id=c17e55e9f3` (not `calling`). /run dispatches (job_id minted) w/o a call.
- ZERO 5xx / traceback in the post-restart window. Final md5 box==local `dad2997f0338f8c38c55358e13c93779`.

## ROLLBACK RECIPE (if ever needed)
`cp /opt/famit-agent/caller.py.MNTbak.1781072100 /opt/famit-agent/caller.py && sudo systemctl restart famit-caller`
(restores the post-media-gen-mount original `4a92b514...`; the booking/ package is inert when not mounted).

## TO GO LIVE LATER (DEFERRED — orchestrator/founder action)
1. Set `FEATURE_BOOKING=1` in `/opt/famit-agent/.env` + restart famit-caller → 10 `/booking` routes mount
   (authed, token-derived, is_admin hardcoded False).
2. ⚠ PREREQUISITE before flag-ON is useful: apply the booking schema — Alembic `0003_booking` revision that
   `create_all()`s booking/models.py (its OWN SQLAlchemy Base — NOT shared db.models.Base) + applies
   `booking/rls.sql` (ENABLE+FORCE RLS + anti-double-book partial unique index + grants). Until then the
   booking tables don't exist; endpoints would error on missing-table. (DEFERRED in mod-booking brain.)
3. Reminder loop: `BOOKING_REMINDERS_ENABLE=1` + add a `core.tick` pass to scheduler_loop + replace the
   `stub_<rid>` enqueue with the real gated dial/WhatsApp job. Calendar: GOOGLE_CALENDAR_* + sync flag.

## DEFERRED (not in this mount; per build state + mod-booking brain)
- Alembic 0003_booking revision + rls.sql apply (+ on-box schema smoke) — the schema prereq above.
- Replace tick stub job_id with real _spawn_retry_job/WhatsApp enqueue + add tick pass to scheduler_loop.
- Google Calendar SDK credential wiring (dormant port).
