# BRAIN — Form/Lead-Capture builder + Survey/Feedback engine (module forms-surveys)

Durable facts + hard-won learnings. Append, never delete.
Build log: `memory/build_log/wave-build-mod-forms-surveys.md`.
Code: `droplet_work/forms-surveys/` (hyphen per the path rule; importable alias `forms_surveys`).

## WHAT IT IS / WHERE
- Package `droplet_work/forms-surveys/` (NEW files only; NOT mounted, NOT deployed). Designed minimally
  from MASTER_PLATFORM_ROADMAP rows 44/79-81/139 — the primary spec `design/platform-crm-core.md` is
  CONTACTS, not forms, so it does not cover this module.
- form/survey DEFINITION -> PUBLIC submit -> CRM contact (`crm.upsert_contact`) + stored submission ->
  (deferred/injected) leads-store write + workflow trigger ; survey responses -> deterministic insights.
- Forms are FREE (no spend/wallet). The risky surface is the UN-AUTHENTICATED public submit endpoint.

## LOAD-BEARING DESIGN (do not relitigate)
- **Public submit INVERTS the org_id invariant — org is SERVER-DERIVED.** No authenticated tenant on the
  public path, so org_id comes from the form record resolved by an unguessable `public_token`
  (`secrets.token_urlsafe(24)`, globally UNIQUE). `resolve_public` selects ONLY by token (admin-scoped,
  leaks nothing else) -> all writes under `session(tenant_id=resolved_org)`. Org is NEVER a request param.
- **Anti-abuse on the unauth endpoint is MANDATORY, not optional:** per-(token,IP) ratelimit.allow +
  raw-body cap pre-parse + field count/len caps + honeypot (filled hidden field -> silent ok-drop,
  stores nothing) + allow-list schema validation (unknown keys + injection-shaped keys rejected,
  `^[a-z0-9_]+$`) + sha256(ip+token) forensics (NO raw PII IP) + tenant-scoped audit.
- **NEVER write the leads table.** A captured lead becomes a CRM CONTACT via the PUBLIC
  `crm.upsert_contact` (read-model-safe). leads is dual-mirrored through store.py; a direct PG INSERT
  drifts the shadow mirror (crm-core build log healed exactly that). The authoritative leads write + the
  workflow-trigger emission are INJECTED hooks (`core.init(emit_lead=, emit_workflow=)`, default None =
  dormant), wired at mount — like booking's stub job_id. Never inlined into caller.py here.
- **`crm.record_timeline` is NOT public** (only the session-bound private `_record_timeline` exists).
  booking's brain cites the public name but it would AttributeError / force editing crm (forbidden). Link
  by the deterministic `crm.contact_id` (public, pure, no DB) + `crm.upsert_contact`; defer timeline-surfacing.
- **Survey insights = deterministic aggregation** (NPS promoter9-10/passive7-8/detractor0-6, CSAT 4-5/3/1-2,
  per-question counts/avg in Python/SQL). LLM summarization behind `FORMS_INSIGHTS_LLM` (default OFF) and
  NEVER on submit or the insights read hot path (CRM_NBA_LLM discipline).
- **Standalone `schema.sql` (NOT Alembic).** kb/booking/crm precedent — avoids the 0002 multiple-heads
  collision. Lazy `ensure_schema()` (first-use) or psql -f. ENABLE+FORCE RLS, admin-GUC-OR-org_id policy.

## COMPOSITION (all lazy / import-guarded; top level imports NONE of them)
db.engine (RLS sessions) · crm.upsert_contact/contact_id (F2; read-model-safe) · audit.record (F4 immutable;
public-submit audit written INSIDE core where org_id is in scope -> tenant-scoped, never leaks to caller) ·
ratelimit.allow (public-route gate) · config. Dormant everywhere: no PG / no creds => {status:not_configured},
never raises. config.status() = BOOLEANS only, never echoes a secret.

## ROUTER (defined, NOT mounted — `endpoints.build_router(resolve_tenant,can,need_auth,forbidden,ratelimit=,audit=)`)
AUTHED: GET/POST /forms · GET/PUT /forms/{id} · POST /forms/{id}/rotate-token · GET /forms/{id}/submissions ·
GET /forms/{id}/insights · GET /forms/status.  PUBLIC (path `/f/...`, no auth): GET /f/{token} (render-only,
strips internals) · POST /f/{token}/submit.

## SMOKE / TEST (local/venv ONLY)
- `cd droplet_work/forms-surveys/tests && python -m pytest test_forms.py -q --import-mode=importlib` => 14 passed.
- `python droplet_work/forms-surveys/_smoke_forms.py` => SMOKE PASS, 18 checks.
- Local env py3.14 (fastapi 0.115). Box venv py3.12.

## HARD-WON LEARNINGS (do not relearn)
- **HYPHENATED PACKAGE GOTCHA** (the next hyphen-named module WILL hit this): `forms-surveys` is not a
  legal Python module name. pytest cannot collect from inside the dir (imports `forms-surveys/__init__.py`
  as module `forms-surveys` -> "relative import with no known parent package"). FIX: `_bootstrap.load()`
  (`spec_from_file_location('forms_surveys', __init__, submodule_search_locations=[pkgdir])` registers the
  alias) + REMOVE `tests/__init__.py` + run from `tests/` with `--import-mode=importlib`; conftest does the
  bootstrap. booking/ avoided this by having no hyphen — prefer no-hyphen dirs for future modules.
- **RLS isolation is proven BY-SHAPE only offline** (SQLite has no RLS; conftest `_ConnShim._rls` simulates
  the FORCE-RLS WHERE-org_id filter). Core adds NO org_id filter in list reads — it RELIES on Postgres
  FORCE-RLS (crm/kb pattern). Real RLS + schema.sql syntax validated ONLY at the deferred on-box mount.
- **Dormant-stub contract:** an unimplemented verifier (captcha) must return 'skipped', NEVER a false
  'passed'. A no-op that claims it checked is worse than no check.

## CREDS AWAITED (core needs ONLY Postgres)
FORMS_CAPTCHA_SECRET (+FORMS_CAPTCHA_PROVIDER) — captcha (stub; provider verify wired at mount) ·
FORMS_NOTIFY_ENABLED + sender — on-submit notify · FORMS_INSIGHTS_LLM — LLM insight summary (off hot path).

## DEFERRED (orchestrator)
Mount (alias-load + init(hooks,audit) + build_router; confirm per-route auth, exclude `/f/` from X-Auth) ·
apply schema.sql on live PG + prove RLS/UNIQUE · wire injected leads-write + workflow-emit hooks · captcha
provider verify · notify sender · LLM insights · timeline-surfacing of submissions · frontend builder + render page.

## MOUNTED 2026-06-10 (flag OFF) -- build log wave-build-mount-forms-surveys.md
- caller.py md5 babf0494...(pre) -> 68218dfa...(post). Box backup caller.py.MNTbak.1781076772.
  `FEATURE_FORMS` default OFF: 0 routes mounted (TOTAL 79, byte-identical); =1 -> 8 paths (TOTAL 89,
  6 authed /forms* + 2 public /f/*). Regression gate GREEN; /run dispatch no-paid-call GREEN.
- **TRAP 1 (advisor-caught):** forms `build_router` has **NO firewall param** (forms are FREE). Unlike
  media-gen/booking which take `firewall=_firewall_mod`. Pass ONLY `(resolve_tenant, can, need_auth,
  _forbidden)`. A stray `firewall=` kwarg = TypeError swallowed by the except -> flag-on mounts NOTHING
  while the gate looks green. ratelimit/audit fall back to the router's own `import ratelimit/audit`
  (both importable in box venv).
- **TRAP 2:** `core.init()` calls `ensure_schema()` (DDL) -- box PG is UP, so init() with flag OFF would
  touch live PG. NOT called this wave (same as payments/support/booking). build_router stands alone;
  ensure_schema is lazy/first-use. init(emit_lead=, emit_workflow=) deferred -> gate INSIDE flag-on block.
- **HYPHENATED-DIR IMPORT:** `forms-surveys` is not a legal module name. Mount block registers the alias
  `forms_surveys` in sys.modules INLINE via `importlib.util.spec_from_file_location('forms_surveys',
  __init__, submodule_search_locations=[pkgdir])` -- self-contained, NOT via the package's own _bootstrap.py
  (which lives in the same hyphenated dir). Idempotent (reuses sys.modules if present).
- **No global auth middleware in caller.py** -- both `@app.middleware("http")` are rate-limit + metrics
  only. So the public `/f/{token}` routes are reachable with no global gate (mod build-log Q#4 RESOLVED).
- Deploy hygiene: tar `--exclude=__pycache__ --exclude=*.pyc` (no py3.14 pyc into py3.12 venv). Run the
  spine smoke FROM /opt/famit-agent (stale /tmp/caller.py shadow lesson). md5-verify after EVERY scp.
