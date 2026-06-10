# WAVE-BUILD-MOD-FORMS-SURVEYS — Form/Lead-Capture builder + Survey/Feedback engine (PLATFORM-ENG)

Designed minimally from MASTER_PLATFORM_ROADMAP.md (rows 44/79-81/139 — Form/Lead-Capture Builder,
Website/Landing, Survey/Feedback). Primary spec `design/platform-crm-core.md` is CONTACTS, not forms,
so it does not cover this module; the CRM-core build (contacts spine + `crm.upsert_contact` / `contact_id`)
is the foundation this composes onto. Mode: ADDITIVE, NEW files only under `droplet_work/forms-surveys/`,
NO caller.py/agent.py edit, NO deploy/restart, NO git (orchestrator commits). Local/venv build + smoke only.

## WHAT IT IS / THE PIPELINE
form/survey DEFINITION -> PUBLIC submit endpoint -> CRM contact (person spine) + stored submission
                       -> (deferred/injected) leads-store write + workflow trigger
survey responses       -> deterministic insights (NPS / CSAT / per-question rollups)
Forms are FREE (no spend, no wallet hold). The only risky surface is the UN-AUTHENTICATED public submit.

## FILES CREATED (droplet_work/forms-surveys/)
- `schema.sql` — 2 PG-native tables, standalone (NOT Alembic — kb/booking/crm precedent; avoids the
  0002 multiple-heads collision). `forms` (definition: kind form|survey, fields jsonb allow-list,
  high-entropy `public_token` UNIQUE, status, contact_map, settings) + `form_submissions` (validated
  answers, deterministic survey score+sentiment, sha256 ip-hash not raw IP, lead_emitted/workflow_emitted
  flags). ENABLE+FORCE RLS, admin-GUC-OR-org_id policy + WITH CHECK (identical to db/rls.sql + crm), all
  `IF NOT EXISTS`. org_id (not tenant_id) — consistent with leads/calls/contacts.
- `config.py` — env-at-call-time, dormant gate (`pg_available()` is the CORE gate; captcha/notify/insights-LLM
  are separate optional surfaces). `status()` = BOOLEANS ONLY, never echoes a secret (redaction binding).
- `identity.py` — canonical_phone / contact_id (pure hash, crm-core §1.1 VERBATIM, no DB, no top-level
  `import caller`), and `link_contact` -> calls the PUBLIC `crm.upsert_contact` (read-model-safe), NEVER a
  leads write. Dormant ({status:not_configured}) when crm absent / PG down.
- `core.py` — the engine: form CRUD, field-schema validation (allow-list), token resolution, the public
  submit pipeline, survey insights (deterministic), injected hooks. Import-safe / graceful-degrade.
- `endpoints.py` — DEFINED-not-mounted FastAPI `build_router(resolve_tenant, can, need_auth, forbidden,
  ratelimit=, audit=)`. Authed CRUD + public token routes. Import-guarded (returns None if fastapi absent).
- `__init__.py` — package facade + convenience re-exports (the alias-load story documented inline).
- `_bootstrap.py` — loads the hyphenated `forms-surveys` package under the importable alias `forms_surveys`
  (a hyphen is not a legal module name — see LEARNINGS).
- `tests/conftest.py` + `tests/test_forms.py` — 14 offline tests (SQLite FakeEngine, RLS-shape shim).
- `_smoke_forms.py` — 18-check standalone import/dormancy/logic/router smoke.

## WHAT IT COMPOSES (foundation reused — all LAZY / import-guarded, top level imports NONE)
- F1 P1-Postgres — RLS tenant-scoping via `db.engine.session(tenant_id, is_admin)` GUC-in-txn contract.
- F2 CRM contacts — `crm.upsert_contact` (public) makes a captured lead a CONTACT; links by deterministic
  `crm.contact_id`. NOT a leads write (leads is dual-mirrored; a stray PG write drifts the shadow mirror —
  crm-core build log documents healing exactly that). `crm.record_timeline` is NOT public (only the
  session-bound private `_record_timeline` exists — booking's brain cites the public name but it would
  AttributeError); timeline-surfacing is DEFERRED, the deterministic contact_id makes it zero-schema-change.
- F4 Audit (immutable) — every authed CRUD + every public submit (incl. honeypot drop) writes an audit row.
  The PUBLIC-submit audit is written INSIDE core.submit_public (org_id in scope, never leaks to the public
  caller) -> TENANT-SCOPED attribution. `audit.record(actor,action,object_type,object_id,channel='forms',
  tenant_id,meta)`.
- ratelimit.allow — gates the public routes per (token+IP); fail-open (the module fails open itself).

## THE LOAD-BEARING SECURITY DECISION — org is SERVER-DERIVED on the public path
Every authed module enforces "org_id is ALWAYS t['tenant_id'], NEVER a body/param." The public submit has
NO authenticated tenant. So org_id comes from the FORM RECORD, resolved by an unguessable `public_token`
(`secrets.token_urlsafe(24)`): `resolve_public` selects ONLY by token (admin-scoped, leaks nothing else),
THEN all writes run under `session(tenant_id=resolved_org)`. Org is never a request param. Anti-abuse on
the unauth endpoint is MANDATORY: per-(token,IP) rate limit + raw-body size cap (pre-parse) + field
count/length caps + honeypot (filled hidden field -> silent ok-drop, stores nothing) + allow-list schema
validation (unknown keys + injection-shaped keys `^[a-z0-9_]+$` rejected) + sha256(ip+token) forensics
(no raw PII IP stored) + tenant-scoped audit. `public_render` returns ONLY renderable fields (title,
field schema) — never org_id/settings/counts/token.

## ROUTER ENDPOINTS (for the later mount — DEFINED, NOT mounted into caller.py)
AUTHED (X-Auth via injected resolve_tenant + can(); org = t['tenant_id'], NEVER a param):
- `GET  /forms?kind=&status=`              -> {forms,total}
- `POST /forms` {kind,title,fields,settings,contact_map,status} -> {status, form}   (write)
- `GET  /forms/{form_id}`                  -> {form}
- `PUT  /forms/{form_id}` {…}              -> {status, form}                         (write)
- `POST /forms/{form_id}/rotate-token`     -> {public_token}  (abuse mitigation)     (write)
- `GET  /forms/{form_id}/submissions`      -> {submissions,total}
- `GET  /forms/{form_id}/insights`         -> deterministic NPS/CSAT/sentiment/per-question rollups
- `GET  /forms/status`                     -> redacted config snapshot
PUBLIC (NO auth; org server-derived from the token; path `/f/...` so trivially excluded from X-Auth at mount):
- `GET  /f/{public_token}`                 -> renderable fields only (public_render)
- `POST /f/{public_token}/submit`          -> {status, submission_id, contact_id}  (rate-limited, capped, honeypot)

## CREDS AWAITED (dormant-until-creds; core needs ONLY Postgres)
- `FORMS_CAPTCHA_SECRET` (+ `FORMS_CAPTCHA_PROVIDER` recaptcha|turnstile) — CAPTCHA on public submit.
  STUB today: the provider HTTP verify is wired at mount. CONTRACT: an UNWIRED verifier NEVER returns
  'passed' — no secret => skipped/not_configured (fail-open); secret set but unwired => skipped/
  verifier_not_wired (still fail-open, never a false 'passed'). status().captcha_verifier_wired=False.
- `FORMS_NOTIFY_ENABLED` + a sender — on-submit email/notify (deferred; reuses existing senders at mount).
- `FORMS_INSIGHTS_LLM` — LLM survey-insight summarization. DEFAULT OFF; even ON it NEVER runs on submit or
  the insights READ hot path (same discipline as CRM_NBA_LLM). Insights are deterministic SQL/Python.

## THE PROOF (local/venv ONLY — no PG, no creds, no network, no calls)
- pytest: `cd droplet_work/forms-surveys/tests && python -m pytest test_forms.py -q --import-mode=importlib`
  => **14 passed**. Covers: field allow-list (good/injection/dup/bad-type); submission allow-list
  (unknown/injection-key/missing-required/clean); honeypot silent-drop; survey scoring (NPS/CSAT buckets);
  DORMANT no-PG -> not_configured (no raise) + status redaction; (a) token->org resolution writes under the
  right org + wrong/absent token -> not_found + render-by-wrong-token None; public_render strips internals +
  unpublished form does not resolve; (d) cross-tenant isolation (A sees only A; A cannot read B's
  submissions); deterministic survey insights (NPS=0.0 for 2 prom/1 pass/2 detr, per-question counts);
  hooks dormant-by-default (no lead/workflow emit) + injected-hooks-fire; tenant-scoped submit audit
  (org_id server-derived, honeypot-drop also audited); captcha-unwired-never-passes; (e) router mountable
  (all routes present).
- smoke: `python _smoke_forms.py` => **SMOKE PASS, 18 checks** (alias import, dormancy, redaction, pure
  logic, router build).
- mount-shape: `core.init(emit_lead=, emit_workflow=, audit=)` returns False dormant, never raises;
  `build_router` import-guarded.

## HONESTY CAVEATS (do not overclaim — crm-core build-log bar)
1. **RLS isolation is proven BY-SHAPE via a simulated shim, NOT the real policy.** SQLite has no RLS, so
   `tests/conftest._ConnShim._rls` injects the `WHERE org_id` filter the FORCE-RLS policy would. The test
   proves the shim works; the real ENABLE+FORCE RLS is validated ONLY at the deferred on-box mount. The
   core code adds NO org_id filter in list_forms/list_submissions — it RELIES on Postgres FORCE-RLS (same
   as crm/kb). Do not read "RLS verified" into the green tests.
2. **schema.sql is never executed in the offline harness** (`exec_driver_sql` is a no-op; the FakeEngine
   hand-builds parallel tables; `_schema_ready=True` short-circuits ensure_schema). INSERT column lists
   were cross-checked against the CREATE TABLEs and align, but a Postgres-syntax error in schema.sql
   surfaces only at the deferred mount (`psql -f` / first ensure_schema on live PG).
3. **CAPTCHA is a STUB** — fail-open until the provider HTTP verifier is wired (see CREDS).
4. **Mount assumption:** the public `/f/` routes must bypass tenant auth. Workforce/booking use per-route
   `resolve_tenant` (no global middleware), so public routes simply don't call it — confirm caller.py's
   auth is per-route at mount; if any GLOBAL auth middleware exists, the public submit breaks and the
   `/f/` prefix must be explicitly excluded.
- Minor accepted trade-offs: public_render advertises the honeypot field name (a bot reading the JSON can
  skip it — honeypot is one layer of several); the rate-limit key is per (token+IP) combined, so an IP
  rotating across many valid tokens isn't globally capped (bounded by the strict 'auth' bucket per token).

## DEFERRED (orchestrator, sequential)
- Mount: add the alias-load + `forms.init(emit_lead=…, emit_workflow=…, audit=audit)` + `build_router(...)`
  in caller.py (confirm per-route auth; exclude `/f/` from X-Auth). Apply schema.sql on live PG + prove
  RLS/UNIQUE on the box.
- Wire the INJECTED hooks: the authoritative leads-store write (via the existing lead writer, NOT a direct
  leads INSERT) + the workflow-trigger emission (into the workflow-studio event bridge / webhook engine).
- CAPTCHA provider HTTP verify; on-submit notify sender; LLM insights summarization (off-hot-path).
- Timeline-surfacing of submissions (kind='form'/'survey') once a public crm timeline-append exists.
- Frontend form/survey builder + public hosted render page.

## ROLLBACK
All additive. DROP TABLE form_submissions, forms (source stores untouched). The package is inert wrt the
running service until mounted (caller.py unchanged this wave). No .env change required for core.

## LEARNINGS (append, never delete)
- HYPHENATED PACKAGE GOTCHA (next hyphen-named module will hit this): `forms-surveys` is not a legal
  Python module name. pytest CANNOT collect from inside the dir (it tries to import `forms-surveys/
  __init__.py` as module `forms-surveys` -> "relative import with no known parent package"). FIX: (1) a
  `_bootstrap.load()` that `spec_from_file_location('forms_surveys', __init__, submodule_search_locations=
  [pkgdir])` registers the package under the alias; (2) REMOVE `tests/__init__.py` (else tests become a
  sub-package of the illegal name); (3) run from `tests/` with `--import-mode=importlib`; conftest does the
  bootstrap so test files `import _bootstrap; fs = _bootstrap.load()`. booking/ avoided all this by having
  no hyphen.
- crm.record_timeline is NOT public (crm/__init__ exports `_record_timeline`? no — it's a private
  session-bound fn). Don't mirror booking's brain on this; link by `crm.contact_id` + `crm.upsert_contact`
  (both public) and defer timeline-surfacing.
- DORMANT-UNTIL-CREDS CONTRACT for a stub verifier: an unimplemented check must return 'skipped', NEVER a
  false 'passed' — a no-op claiming success is worse than no check.
