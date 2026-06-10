# WAVE BUILD — MOUNT: payments router into caller.py (sequential spine) — PLATFORM-ENG

Date: 2026-06-10. Scope: mount ONLY (wire + router include), behind an import-guard + FEATURE flag
DEFAULT-OFF. Source of truth: LIVE box `famit@168.144.153.145:/opt/famit-agent/` (venv
`/opt/capsy-agent/.venv`, py3.12). NO git. ⚠ THE LIVE EARNER — handled with reconcile-first + dormant-by-flag.
Result: **payments: mounted + gate GREEN (flag OFF).**

## WHY THIS DIFFERS FROM booking/media-gen (wire-then-include, not build_router)
payments is checklist row #5: `payments.router.wire(...)` injects caller.py's auth helpers into the
module's globals, THEN `app.include_router(payments.router.router, prefix="/payments")`. Unlike
booking/media-gen there is NO body/header-tenant bare router to avoid — the shipped module-level `router`
is already the CLEAN token-deriving surface: tenant ONLY from the injected `resolve_tenant(request)`,
`can(t,"write")` on mutating routes (create-link/mark-paid/refund), org_id = resolved tenant_id (never a
spoofable body/query param), spend routes pass through `firewall.require_step_up` (PASS-THROUGH when
FIREWALL off/no PIN → non-breaking; 403 when active). `/payments/webhooks/{provider}` is intentionally
UNAUTHENTICATED (provider-signature-verified inside core.ingest_webhook, always 200 → no retry-storm).
KEY GOTCHA: `wire()` takes **KEYWORD-ONLY** args — `wire(resolve_tenant=, can=, need_auth=, forbidden=,
firewall=)`. Positional would TypeError. Router has NO internal prefix → prefix applied at include time.

## init()/drain DELIBERATELY DEFERRED (advisor-flagged — protects byte-identical-when-OFF)
The mod-payments brain DEFERRED list says mount = wire+include **+ payments.init() in startup +
drain_followups() per scheduler tick**. We did NOT add init() to the unconditional startup path:
`core.init()` calls `ensure_schema()` (touches PG / applies DDL) and would run with the flag OFF, breaking
the byte-identical guarantee. Verified `ensure_schema()` is LAZY (first-use, `_schema_ready`-guarded,
NEVER raises) and every `core.*` route degrades on its own (PG down → `unavailable`; no creds →
`not_configured`), so init() is NOT a route prerequisite. **DEFERRED: payments.init() at startup +
drain_followups() scheduler dunning tick** — exactly as booking deferred its reminder tick. To activate
later, gate init() INSIDE the flag-on block (never module top-level).

## WHAT WAS DONE
1. Reconcile-first: local caller.py md5 == box md5 `dad2997f0338f8c38c55358e13c93779` (4111 LOC,
   post-booking-mount state) BEFORE editing. grep proved NO pre-existing payments/FEATURE_PAYMENTS/
   `/payments` refs (clean slate). `payments/` package NOT yet on box.
2. Read `payments/router.py` + `payments/core.py` init/status/ensure_schema. Confirmed `wire()` keyword-only,
   module-level `router` (None if FastAPI absent), no internal prefix; init() optional/deferred (above).
3. Deployed `payments/` package to `/opt/famit-agent/payments/` via tar (router/core/_http/__init__/
   providers{razorpay,stripe,base}/schema.sql/tests; `__pycache__`/`*.pyc` STRIPPED so no py3.14 .pyc leaks
   into the py3.12 venv). Verified NO .pyc on box.
4. BARE UNGUARDED import smoke in the BOX venv (py3.12) — the advisor-flagged must-do (a silent ImportError
   would null `_payments_router` and mount nothing while the gate still goes green = false pass).
   `from payments.router import router, wire` resolved CLEAN; `wire(stubs)` succeeded; router = **10 route
   objects / 9 unique paths** (GET+POST `/links` collapse, as predicted).
5. MOUNT BLOCK appended at END of caller.py (after the booking block; app+helpers fully defined → no
   circular import), mirroring the house pattern adapted for wire-then-include:
   - import-guard: `try: from payments.router import router as _payments_router, wire as _payments_wire /
     except: both None`
   - `FEATURE_PAYMENTS = (cfg_get("FEATURE_PAYMENTS","0") or "0").strip().lower() in (...)` DEFAULT OFF
   - `if FEATURE_PAYMENTS and _payments_router is not None and _payments_wire is not None:` →
     `_payments_wire(resolve_tenant=resolve_tenant, can=can, need_auth=need_auth, forbidden=_forbidden,
     firewall=_firewall_mod)` → `app.include_router(_payments_router, prefix="/payments")`, all
     try/except-guarded (mount failure logs `"payments router mount failed"`, never crashes the spine).
   - NO .env change at rest: default-OFF comes from the cfg_get default → resting deployed state unchanged.
6. Backups (advisor backup-ordering — BEFORE scp of edited file): local `caller.py.MNTbak.1781072877`
   (md5 `dad2997f...`) + box `caller.py.MNTbak.1781072982` (md5 `dad2997f...` = clean rollback target =
   post-booking-mount original).

## INSTANTIATE-SMOKE (box venv `/opt/capsy-agent/.venv/bin/python`, BEFORE restart)
- `py_compile caller.py` OK (local + box venv).
- SPINE smoke `import caller`, BOTH flag states (running service unaffected until restart → safe):
  - flag OFF (default): caller imports clean; `_payments_router` + `_payments_wire` BOTH LOADED (import-guard
    did NOT null them — no silent failure) but **0 `/payments` paths** mounted → byte-identical behavior.
  - `FEATURE_PAYMENTS=1`: caller imports clean; **9 `/payments/*` unique paths** mounted (all correctly
    prefixed: /payments/health, /links, /links/{id}{,/invoice,/receipt,/mark-paid,/refund}, /followups,
    /webhooks/{provider}).
  Proves mounted-vs-absent WITHOUT toggling the live service.
- NOTE: box logs `[db.engine] Postgres available` — PG IS up. With the flag ON, payments routes would hit
  PG, but the payment_intents/events/followups tables apply LAZILY via `ensure_schema()` on first use
  (idempotent DDL, not Alembic). Flag stays OFF: dormant-by-flag, no schema touched on the live earner.

## DEPLOY + RESTART
- scp edited caller.py → box; md5 box==local `e4cbcad565d5e94f131a268ed910d191` (4156 LOC, +45 vs prior).
- `sudo systemctl restart famit-caller`. "Application startup complete", "Uvicorn running on 0.0.0.0:8209".
  No ImportError/ModuleNotFound/Traceback/"payments router mount failed". Both famit-caller + famit-agent active.

## REGRESSION GATE — GREEN (legacy `X-Auth: FamitCall2026`, loopback 127.0.0.1:8209)
- `/me` 200 · `/campaigns` 200 · `/leads` 200 · `/contacts` 200 · `/billing/overview` 200.
- `/payments/health` = **404** · `/payments/links` = **404** (flag OFF → correctly NOT mounted; unchanged).
- **/run DISPATCH GATE (no paid call) — proven form-field + suppression recipe:**
  1. `POST /suppression numbers=+910000000068` (--data-urlencode form) → 200 `{"added":0,"total":2}`
     (already suppressed from prior mount gates).
  2. `POST /run campaign_id=c17e55e9f3 leads=+910000000068` (form) → 200
     `{"job_id":"105e0ee346","count":1,"suppressed_count":1}`. count=1 ⇒ lead ENTERED pipeline (dispatch
     works); suppressed_count=1 ⇒ the only lead was suppressed ⇒ dial loop dials NOBODY ⇒ NO paid call.
- ZERO 5xx/traceback/exception in the post-restart window. Final md5 box==local `e4cbcad565d5e94f131a268ed910d191`.

## ROLLBACK RECIPE (if ever needed)
`cp /opt/famit-agent/caller.py.MNTbak.1781072982 /opt/famit-agent/caller.py && sudo systemctl restart famit-caller`
(restores the post-booking-mount original `dad2997f...`; the payments/ package is inert when not mounted).

## TO GO LIVE LATER (DEFERRED — orchestrator/founder action)
1. Set `FEATURE_PAYMENTS=1` in `/opt/famit-agent/.env` + restart famit-caller → 9 `/payments` routes mount
   (authed, token-derived, org_id = resolved tenant, spend routes firewall-step-up-gated).
2. Module stays DORMANT/`not_configured` until creds land: Razorpay `RAZORPAY_KEY_ID`/`RAZORPAY_KEY_SECRET`/
   `RAZORPAY_WEBHOOK_SECRET` (primary INR); Stripe `STRIPE_SECRET_KEY`/`STRIPE_WEBHOOK_SECRET` (2nd); select
   via `PAYMENTS_DEFAULT_PROVIDER`. Tunables: `PAYMENTS_LINK_TTL_S`, `PAYMENTS_FOLLOWUP_*`.
3. Schema: `ensure_schema()` applies payment_intents/payment_events/payment_followups LAZILY on first use
   (idempotent `CREATE TABLE IF NOT EXISTS` + FORCE-RLS, NOT Alembic — kept out of the P1 keystone chain).
   No manual migration needed; first authed call materializes the tables.
4. AUTH CONTRACT CONFIRMED (verified this session — flag-ON safe): `caller.can(tenant: dict, action: str)`
   (L641) takes the tenant DICT (calls `_role_of(tenant)`), exactly what `payments/router.py` passes
   (`_can(t,"write")`, `t` = resolved tenant dict). NO dict-vs-string mismatch — at flag-ON, write routes
   (create-link/mark-paid/refund) correctly authorize admin/manager → allow, agent/read-only → 403.

## DEFERRED (not in this mount; per build state + mod-payments brain)
- payments.init() at startup + drain_followups() per scheduler tick (gate INSIDE flag-on block when activated).
- payment→wallet TOPUP bridge (`wallet.topup` idem on provider `payment_ref`).
- Failed-payment follow-up ACTUATION (WA/call nudge) when channels land.
- Add `payments.create_link`/`payments.refund` to the firewall spend registry (defence-in-depth).
- Real Razorpay/Stripe HTTP paths are unit-tested with synthetic payloads only — re-verify at creds-onboarding.
