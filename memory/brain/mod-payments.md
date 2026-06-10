# BRAIN — Payments / Collections (vendor->customer payments)

Durable facts + hard-won learnings. Append, never delete.

## WHAT IT IS / WHERE
- Package: `droplet_work/payments/` (NEW files only; router DEFINED-NOT-MOUNTED; not deployed). No
  dedicated payments design spec existed -> designed minimally from `design/credit-ledger-firewall.md`
  (reuse the wallet ledger PATTERNS) + MASTER_PLATFORM_ROADMAP.md §Payments, per task instruction.
- Payment-link generation (Razorpay primary INR / Stripe 2nd, DORMANT-UNTIL-CREDS), invoice/receipt,
  payment-status->CRM stitch, failed-payment follow-up (dunning). PG-native over the shared `famit` DB.

## LOAD-BEARING DISTINCTION (do not relearn — the single most important fact)
This is the money a TENANT collects from THEIR end-CUSTOMER (an invoice / payment link). It is DISTINCT
from the F4 vendor WALLET (the tenant's PREPAID SPEND balance with Famit). We REUSE the wallet ledger's
idempotency + immutable-event PATTERNS, NOT its `wallet_*` tables. A paid customer invoice -> tenant
wallet top-up (`wallet.topup` idempotent on the provider `payment_ref`) is a DEFERRED bridge, not built
here. Conflating the two = charging the wrong ledger. The schema/STATE/init docstring all repeat this.

## LOAD-BEARING DESIGN (do not relearn)
- **3 tables, standalone idempotent DDL (`payments/schema.sql`), DELIBERATELY NOT Alembic.** Kept OUT of
  the P1 0001/0002 keystone chain so blast radius never touches the live migration — same call kb/schema.sql
  (F2), db/ddl_wallet.sql (F4), crm/schema.sql all made. Applied via `payments.ensure_schema()` (LAZY,
  first-use, NEVER raises) or `psql -f`. Re-runnable (`CREATE TABLE IF NOT EXISTS`).
  * `payment_intents` — one row per link/order. State machine
    `created -> issued -> paid|failed|expired|refunded|partially_refunded`. id =
    `pi_<sha1(org|provider|ref-or-nonce)[:20]>`. Idempotent create via partial unique index
    `(org_id, idem_key) WHERE idem_key<>''`. CHECK `amount_minor>0`, paid/refunded `>=0`.
  * `payment_events` — IMMUTABLE append-only audit of every transition/webhook (F4 events/audit
    discipline). id = `pe_<sha1(...)[:24]>`, `ON CONFLICT DO NOTHING`. Stores a REDACTED provider payload.
  * `payment_followups` — failed/expired dunning queue, one live row per intent (unique index).
- **Money = INTEGER MINOR UNITS (paise), BIGINT, end to end. NEVER float** (same discipline as wallet).
  The API layer is the SOLE major<->minor boundary: `router._to_minor` converts on input exactly once;
  the response divides by 100. `_to_minor(19.99)==1999` with NO float drift (string-decimal path).
- **RLS shape IDENTICAL to db/rls.sql / crm/schema.sql:** FORCE RLS, policy = admin-GUC OR `org_id` match,
  `WITH CHECK`. Column is `org_id` (consistent with crm/leads), but the `db.engine.session(tenant_id=...)`
  helper SETs `app.tenant_id` — the policy compares that GUC to the `org_id` column. RLS isolation
  live-proven on the box (TENANT2 gets 0 rows for TENANT's intent).
- **PROVIDER-AGNOSTIC + DORMANT-UNTIL-CREDS.** With no keys, `create_payment_link` records a `'created'`
  intent LOCALLY and returns `{"status":"not_configured","pay_url":""}` — the platform runs end-to-end
  with the gateway dark; nothing raises. When keys land, the SAME path creates a real link. Every provider
  action gates on `status()=='not_configured'` first -> clean no-op. Providers redact payloads
  (first/last-4 only); secrets never echoed.
- **STATUS -> CRM is BEST-EFFORT, never breaks the payment path.** On `'paid'`, write a crm `'purchase'`
  timeline row (the crm schema's amount/currency columns exist for exactly this). A CRM outage is swallowed.
- **FAILED-PAYMENT FOLLOW-UP actuation is DORMANT.** `drain_followups()` is a deterministic scheduler-tick
  helper (like crm rebuild / aidecision drain). Today it only advances state + records the intent-to-nudge
  (`channel='dormant'`); the real WA-template/call nudge is wired when channels land.
- **Webhook ingest is provider-signature-verified (HMAC-SHA256), NOT tenant-auth'd / step-up'd** (machine
  call). Razorpay uses raw hex HMAC; Stripe implements the `t=,v1=` signed-payload scheme. Dormant secret
  -> `not_configured` no-op, ALWAYS returns 200 (a 4xx makes the provider retry-storm).

## ROUTER (DEFINED-NOT-MOUNTED — wiring is the deferred step)
- `router.wire(resolve_tenant, can, need_auth, forbidden, firewall)` injects caller.py's auth helpers so
  the module has NO caller.py import cycle (same pattern booking/crm use). `router.router` is `None` if
  FastAPI is absent (import-safe). Before `wire()`, every route FAILS CLOSED (503 "not wired").
- Spend-sensitive routes (create-link / refund / manual mark-paid) wrapped with
  `firewall.require_step_up(request,"spend",tenant)` — PASS-THROUGH when FIREWALL_ENABLED off / no PIN
  (non-breaking), 403 challenge when active. `org_id` is ALWAYS the resolved tenant, never a spoofable
  body/query param.
- Endpoints (prefix suggestion `/payments`): `GET /health`, `POST /links`, `GET /links`,
  `GET /links/{id}`, `GET /links/{id}/invoice`, `GET /links/{id}/receipt`, `POST /links/{id}/mark-paid`,
  `POST /links/{id}/refund`, `GET /followups`, `POST /webhooks/{provider}`. 10 routes, NOT auto-mounted.

## COMPOSITION (all lazy / import-guarded)
db.engine (RLS sessions) · crm.core (`'purchase'` timeline, best-effort) · firewall (require_step_up,
spend scope) · providers/ (razorpay+stripe adapters + module-local `_http.py` httpx helper) · config.
None imported at top level except own package. Dormant everywhere: no PG or no creds =>
`{status:"not_configured"}`/`unavailable`/None/[], never raises. The live voice path imports NONE of this.

## SMOKE / TEST LEARNINGS
- LOCAL smoke green re-verified on disk: `cd droplet_work && python -m payments.tests._smoke_payments`
  -> **PASS=33 FAIL=0** (system python 3.14.3, NO PG, NO creds). Covers full import + 10 routes registered
  (not auto-mounted), dormant-until-creds (all providers not_configured, provider actions clean no-ops,
  DB-less core ops degrade without raising), and pure logic (major->minor no float drift, deterministic
  pi_/pe_/pf_ ids, phone canon, BOTH providers' webhook signature verify reject+accept+normalize, payload
  redaction, dormant ingest no-op, invoice/receipt doc builders).
- LIVE PG proof (`tests/_box_roundtrip.py`, throwaway tenant, cleaned in finally) -> **PASS=19/0**: NEW
  DDL applies, create/idempotency/invoice/receipt/mark-paid/event-log/failed/followup/drain all EXECUTE
  against live `famit` PG, the crm `'purchase'` stitch lands on a real contact, RLS isolation holds.
- **GOTCHA — the `caps/.venv` is BROKEN** (created on another machine; its `bin/python` shebang points at
  `/Users/nikhil/miniconda3/bin/python3`). Use the SYSTEM python (3.14.3) for offline smokes — the
  dormant tests need no third-party deps. The box venv is py3.12.

## CREDS AWAITED (roadmap BLOCKER #3 / §11.4)
- RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET, RAZORPAY_WEBHOOK_SECRET (primary, INR).
- STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET (secondary).
With none set, the gateway stays dark (intents persist locally, no link, webhooks no-op). Optional env
tunables: PAYMENTS_DEFAULT_PROVIDER, PAYMENTS_LINK_TTL_S (48h), PAYMENTS_FOLLOWUP_MAX_ATTEMPTS (3),
PAYMENTS_FOLLOWUP_BACKOFF_S (1d).

## DEFERRED (orchestrator)
MOUNT: `payments.router.wire(...)` + `app.include_router(payments.router.router, prefix="/payments")` +
`payments.init()` in startup + `payments.drain_followups()` per scheduler tick · the payment->wallet
TOPUP bridge (`wallet.topup` idem on `payment_ref`) · failed-payment follow-up ACTUATION (WA/call nudge)
when channels land · subscriptions/recurring mandates · tax/GST line-item engine · customer-portal
self-serve pay surface (frontend) · add `payments.create_link`/`payments.refund` to firewall's spend
registry. CAVEAT: real Razorpay/Stripe HTTP paths are unit-tested with synthetic payloads only (no creds)
— re-verify at creds-onboarding.

## MOUNTED (2026-06-10) — caller.py spine, flag-gated DEFAULT-OFF. See build_log/wave-build-mount-payments.md
- Router IS NOW MOUNTED behind `FEATURE_PAYMENTS` (default OFF) at the END of caller.py (after booking
  block). Pattern = wire-then-include (checklist row #5), NOT build_router. Box+local md5
  `e4cbcad565d5e94f131a268ed910d191` (4156 LOC). Rollback target (post-booking-mount, clean) =
  `dad2997f0338f8c38c55358e13c93779`, box backup `caller.py.MNTbak.1781072982`.
- ⚠ GOTCHA — `wire()` is **KEYWORD-ONLY**: `wire(resolve_tenant=, can=, need_auth=, forbidden=, firewall=)`.
  Positional args TypeError. (booking/media-gen's build_router took positional — payments does NOT.)
- ⚠ The module-level `router` has NO internal prefix (unlike ads_engine's built-in `/ads`) — prefix
  `/payments` is applied at `include_router(..., prefix="/payments")`. Health path = `/payments/health`
  (NOT /status). 10 route objects / 9 unique paths (GET+POST /links collapse).
- ⚠ `payments.init()` is DELIBERATELY NOT in startup: it calls `ensure_schema()` (touches PG/DDL) and
  would run with the flag OFF → breaks byte-identical-when-OFF. ensure_schema() is LAZY (first-use,
  `_schema_ready`-guarded, never raises) and routes self-degrade (PG down→unavailable, no creds→
  not_configured), so init() is NOT a route prerequisite. When activating: gate init() INSIDE the flag-on
  block, never module top-level. drain_followups() scheduler tick also DEFERRED (like booking's tick).
- Verified flag OFF→0 /payments paths (byte-identical), flag ON→9 paths, in box venv WITHOUT restarting
  live service. Regression gate GREEN (legacy /me,/campaigns,/leads,/contacts,/billing/overview=200;
  /payments/*=404 flag-off; /run dispatches job_id w/ suppressed lead → no paid call; zero 5xx).
- TO GO LIVE: `FEATURE_PAYMENTS=1` in /opt/famit-agent/.env + restart famit-caller. Tables materialize
  lazily on first authed call (idempotent FORCE-RLS DDL, not Alembic). Then creds (Razorpay/Stripe).
