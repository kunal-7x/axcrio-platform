# WAVE BUILD — MOUNT: support router into caller.py (sequential spine) — PLATFORM-ENG

Date: 2026-06-10. Scope: mount ONLY (wire + router include), behind an import-guard + FEATURE flag
DEFAULT-OFF. Source of truth: LIVE box `famit@168.144.153.145:/opt/famit-agent/` (venv
`/opt/capsy-agent/.venv`, py3.12.3). NO git. ⚠ THE LIVE EARNER — reconcile-first + dormant-by-flag.
Result: **support: mounted + gate GREEN (flag OFF).**

## PATTERN = wire-then-include (IDENTICAL to payments, checklist row #6)
support is the payments twin: a CLEAN token-deriving surface — there is NO body/header-tenant bare
router to avoid (unlike media-gen/booking). `support.router.wire(...)` injects caller.py's auth helpers
into the module globals, THEN `app.include_router(support.router.router, prefix="/support")`. Tenant is
resolved ONLY from the token via the injected `resolve_tenant`; org_id = the resolved tenant_id (NEVER a
spoofable body/query param). Mutating routes (inbound/draft/reply/escalate/claim/resolve) enforce
`can(t,"write")`. support is NOT a money path → no blanket spend step-up; the ONLY step-up-gated route is
`/support/tickets/{id}/resolve` (scope `support_override`, a risky human force-close) — PASS-THROUGH when
FIREWALL off/no PIN (non-breaking), 403 when active. `/support/webhooks/{channel}` is intentionally
UNAUTHENTICATED (machine call) and today a dormant no-op `{"status":"not_configured"}` (200, no retry-storm).
KEY GOTCHA (same as payments): `wire()` is **KEYWORD-ONLY** — `wire(resolve_tenant=, can=, need_auth=,
forbidden=, firewall=)`. Router has NO internal prefix → `/support` applied at include time.

## init() DELIBERATELY DEFERRED (protects byte-identical-when-OFF — same call as payments)
`support.init()` calls `ensure_schema()` (touches PG / applies DDL) and would run with the flag OFF →
breaks byte-identical. Verified `ensure_schema()` is LAZY (first-use, `_schema_ready`-guarded, NEVER
raises) and routes self-degrade (PG down → `unavailable`; empty KB / no LLM creds → deterministic
extractive KB draft, grounded-or-escalate, never hallucinate). So init() is NOT a route prerequisite.
**DEFERRED: support.init() at startup** — gate it INSIDE the flag-on block when activated.

## WHAT WAS DONE
1. Reconcile-first: local caller.py md5 == box md5 `e4cbcad565d5e94f131a268ed910d191` (post-payments-mount
   HEAD) BEFORE editing. grep proved NO pre-existing support/FEATURE_SUPPORT/`/support` refs (clean slate).
   `support/` package NOT yet on box. Both services active. (Local `wc -l`=3702 vs box 4156 — md5 match is
   authoritative; line-count differs by CRLF counting, ignore.)
2. Read `support/router.py` — confirmed `wire()` keyword-only, module-level `router` (None if FastAPI
   absent), no internal prefix, 10 routes. `core.status()` never raises; `init()`/`ensure_schema()` lazy.
   Confirmed `models.py` declares its OWN SQLAlchemy `Base(DeclarativeBase)` (booking-style) but it is NOT
   in the router import path (`__init__`→core→agent→sentiment; core's top imports are stdlib+sentiment only).
3. Deployed `support/` package to `/opt/famit-agent/support/` via tar (`--exclude=__pycache__
   --exclude=*.pyc` so no py3.14 .pyc leaks into the py3.12 venv). Verified ZERO .pyc/__pycache__ on box.
   Files: __init__/core/agent/sentiment/router/config/escalation/identity/models + rls.sql/schema.sql + tests.
4. BARE UNGUARDED import smoke in the BOX venv (py3.12.3) — load-bearing (the build-log "48/48" predates
   escalation/identity/models/config, so the on-disk pkg was NOT the verified pkg; a silent ImportError
   would null `_support_router` and mount nothing while the gate still goes green = false pass).
   `from support.router import router, wire` resolved CLEAN; `wire(stubs)` succeeded; router = **10 route
   objects / 10 unique paths**; `support.status()` returned without raising.
5. MOUNT BLOCK appended at END of caller.py (after the payments block; app+helpers fully defined → no
   circular import), mirroring the payments block EXACTLY (pure ASCII — anchored the Edit on the ASCII-clean
   final payments line, NOT the em-dash comment line, to avoid the UTF-8 mojibake match-fail the advisor
   flagged):
   - import-guard: `try: from support.router import router as _support_router, wire as _support_wire /
     except: both None`
   - `FEATURE_SUPPORT = (cfg_get("FEATURE_SUPPORT","0") or "0").strip().lower() in (...)` DEFAULT OFF
   - `if FEATURE_SUPPORT and _support_router is not None and _support_wire is not None:` →
     `_support_wire(resolve_tenant=resolve_tenant, can=can, need_auth=need_auth, forbidden=_forbidden,
     firewall=_firewall_mod)` → `app.include_router(_support_router, prefix="/support")`, all
     try/except-guarded (mount failure logs `"support router mount failed"`, never crashes the spine).
   - NO .env change at rest: default-OFF comes from the cfg_get default → resting deployed state unchanged.
6. Backups (BEFORE scp of the edited file): local `caller.py.MNTbak.1781094726` + box
   `caller.py.MNTbak.1781094726` (md5 `e4cbcad5...` = clean post-payments rollback target).

## ⚠ GOTCHA HIT + RESOLVED — stale `/tmp/caller.py` shadowed the import (false-negative spine smoke)
First spine smoke showed `FEATURE_SUPPORT=1` → 0 `/support` paths AND all mount-block attrs MISSING
(FEATURE_ADS/_payments_router too). Root cause: a leftover `/tmp/caller.py` (3469-line PRE-mount version,
dated Jun 9) — because the smoke script lived in `/tmp`, Python put `/tmp` on `sys.path[0]` and
`import caller` resolved to the STALE `/tmp/caller.py`, NOT `/opt/famit-agent/caller.py`. Diagnosed via
`caller.__file__` (= `/tmp/caller.py`, 3469 lines). FIX: `rm /tmp/caller.py` + run the smoke FROM
`/opt/famit-agent` (so `sys.path[0]` is the right dir). LESSON for future mounts: run the spine smoke with
the script IN `/opt/famit-agent` (or set sys.path explicitly); never from `/tmp` if a stale caller.py may
linger. Also: scp `Connection reset` once mid-deploy left the box file UNCHANGED — md5-verify after EVERY
scp (caught it: box still showed `e4cbcad5` until the retry).

## INSTANTIATE-SMOKE (box venv, from /opt/famit-agent, BEFORE restart) — PASS
- `py_compile caller.py` OK (local + box venv on the REAL deployed file).
- SPINE smoke `import caller` (correct file, 4204 lines, `caller.__file__=/opt/famit-agent/caller.py`),
  BOTH flag states, service untouched (import doesn't start the server):
  - flag OFF (default): imports clean; `_support_router`+`_support_wire` LOADED (import-guard did NOT null
    them) but **0 `/support` paths** mounted (total 79 routes) → byte-identical. Legacy /me,/campaigns,
    /leads,/contacts present.
  - `FEATURE_SUPPORT=1`: imports clean; **10 `/support/*` paths** mounted (total 89 = 79+10): /support/
    health,/inbound,/tickets,/tickets/{id}{,/draft,/reply,/escalate,/claim,/resolve},/webhooks/{channel}.
- NOTE: box logs `[db.engine] Postgres available` — PG IS up. With the flag ON, support routes would hit
  PG, but support_tickets/support_messages apply LAZILY via `ensure_schema()` on first use (idempotent
  FORCE-RLS DDL, NOT Alembic). Flag stays OFF: dormant-by-flag, no schema touched on the live earner.

## DEPLOY + RESTART
- scp edited caller.py → box (after a retry past a transient `Connection reset`); md5 box==local
  `babf0494480e9a1395e578f9e721ed21` (+44 LOC vs payments-state).
- `sudo systemctl restart famit-caller`. New PID 1358685: "Application startup complete", "Uvicorn running
  on 0.0.0.0:8209". No ImportError/ModuleNotFound/Traceback/"support router mount failed". Both
  famit-caller + famit-agent active.

## REGRESSION GATE — GREEN (legacy `X-Auth: FamitCall2026`, loopback 127.0.0.1:8209)
- `/me` 200 · `/campaigns` 200 · `/leads` 200 · `/contacts` 200 · `/billing/overview` 200.
- `/support/health` = **404** · `/support/tickets` = **404** (flag OFF → correctly NOT mounted; unchanged).
- **/run DISPATCH GATE (no paid call)** — pre-seed `+910000000068` into suppression
  (`{"added":0,"total":2}`), then `POST /run campaign_id=c17e55e9f3 leads=+910000000068` (form) → 200
  `{"job_id":"b257df30b0","count":1,"suppressed_count":1}`. count=1 ⇒ lead ENTERED pipeline (dispatch
  works); suppressed_count=1 ⇒ the only lead was suppressed ⇒ dial loop dials NOBODY ⇒ NO paid call.
- ZERO 5xx/traceback in the post-restart window. Final md5 box==local `babf0494480e9a1395e578f9e721ed21`.

## ROLLBACK RECIPE (if ever needed)
`cp /opt/famit-agent/caller.py.MNTbak.1781094726 /opt/famit-agent/caller.py && sudo systemctl restart famit-caller`
(restores the post-payments-mount original `e4cbcad5...`; the support/ package is inert when not mounted).

## TO GO LIVE LATER (DEFERRED — orchestrator/founder action)
1. Set `FEATURE_SUPPORT=1` in `/opt/famit-agent/.env` + restart famit-caller → 10 `/support` routes mount
   (authed, token-derived, org_id = resolved tenant; /resolve firewall-step-up-gated).
2. Schema: `ensure_schema()` applies support_tickets/support_messages LAZILY on first authed call
   (idempotent FORCE-RLS DDL, NOT Alembic — kept out of the P1 keystone chain). No manual migration.
3. Module stays DORMANT until: KB content ingested (F2 — empty corpus → every question escalates);
   LLM key (`GROQ_API_KEY*`/`ANTHROPIC_API_KEY` via `AIWF_LLM_PROVIDER`) for generative drafts (extractive
   KB draft until then); channel creds (Meta WhatsApp BSP/email) to actually SEND replies + verify inbound
   webhook signatures (DRAFT-only today).
4. Tunables: `SUPPORT_AUTO_REPLY`, `SUPPORT_CONFIDENCE_FLOOR`, `SUPPORT_KB_TOP_K`, `SUPPORT_OPEN_WINDOW_S`,
   `FIREWALL_ENABLE`. Ingest tokens: `SUPPORT_VOICE_INGEST_TOKEN`, `SUPPORT_WEB_WIDGET_SECRET`.

## DEFERRED (not in this mount; per build state + mod-support build log)
- support.init() at startup (gate INSIDE flag-on block when activated).
- Runner integration: `tickets.read/write` + `kb.read` tool-catalog entries + /tickets loopback endpoints
  so `AgentRunner.run("support",...)` can ACTION tickets over the loopback.
- Channel send + inbound webhook signature verify (WhatsApp BSP/email adapters) — flips DRAFT→sent; lands
  with the Omnichannel Inbox + Meta-creds unit.
- crm 'support' TIMELINE row (the crm schema already declares kind='support'); SLA timers/CSAT/macros/merge.

## MOUNT ORDER NOW (caller.py tail, all flag-gated DEFAULT-OFF)
ads-engine → media-gen → booking → payments → **support** (this wave). Next checklist rows: forms-surveys
(build_router), workflow-studio (build_router + attach_event_bridge, BEFORE funnels), ai-manager (bare-OK),
funnels (BLOCKED — needs a token-deriving build_router built first; do NOT apply funnel_wiring.diff as-is).
