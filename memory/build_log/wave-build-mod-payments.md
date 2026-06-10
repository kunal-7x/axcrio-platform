# wave-build · MODULE payments (Payments/Collections) — 2026-06-10 · PLATFORM-ENG

Vendor->customer Payments/Collections: payment-link generation (Razorpay primary INR / Stripe 2nd,
DORMANT-UNTIL-CREDS), invoice/receipt, payment-status->CRM stitch, failed-payment follow-up (dunning).
Composes the built foundation (F4 wallet ledger/idempotency PATTERNS, crm timeline, firewall step-up).
NEW files only under `droplet_work/payments/`. caller.py/agent.py UNTOUCHED; router DEFINED-NOT-MOUNTED;
no service restart/deploy/calls. NO dedicated payments design spec existed -> designed minimally from
`design/credit-ledger-firewall.md` + `MASTER_PLATFORM_ROADMAP.md` §Payments, per task instruction.

## LOAD-BEARING DISTINCTION
This is the money a TENANT collects from THEIR end-CUSTOMER (an invoice / payment link). It is DISTINCT
from the F4 vendor WALLET (the tenant's PREPAID SPEND balance with Famit). We REUSE the wallet ledger's
idempotency + immutable-event PATTERNS, NOT its tables. A paid invoice -> wallet top-up (wallet.topup
idempotent on the provider payment_ref) is a DEFERRED bridge, not built here.

## FILES CREATED (all under droplet_work/payments/)
- `schema.sql` — 3 PG tables, standalone idempotent DDL (F2/F4/crm pattern, NOT Alembic), FORCE-RLS
  admin-GUC policy IDENTICAL to crm/schema.sql + db/rls.sql, org_id, BIGINT integer minor units:
  * `payment_intents` — one row per payment link/order (state machine: created->issued->paid|failed|
    expired|refunded|partially_refunded). Idempotent create via partial unique index (org_id, idem_key)
    WHERE idem_key<>''. CHECK amount_minor>0 / paid,refunded>=0.
  * `payment_events` — IMMUTABLE append-only audit of every transition/webhook (deterministic id,
    ON CONFLICT DO NOTHING — F4 events/audit discipline). Stores a REDACTED provider payload snapshot.
  * `payment_followups` — failed/expired dunning queue (one live row per intent, unique index).
- `_http.py` — module-local shared httpx helper (short timeout, backoff on 429/5xx, never raises);
  import-safe (httpx absent -> 'httpx_unavailable', providers gate on status() first anyway).
- `providers/__init__.py` — provider registry/factory `get(id)` + `status_all()` + `hmac_sha256_hex`
  webhook helper. PROVIDER_IDS=[razorpay,stripe], DEFAULT=razorpay. `redact()` (first/last-4 only).
- `providers/base.py` — the duck-typed provider contract + normalized STATE vocab + NOT_CONFIGURED/err.
- `providers/razorpay.py` — Razorpay Payment-Links adapter. Env RAZORPAY_KEY_ID/KEY_SECRET/WEBHOOK_SECRET.
  Paise-native (no float). create_payment_link / fetch_status / refund / verify_webhook(HMAC-SHA256 hex).
  Maps razorpay statuses + webhook events -> normalized vocab. Redacts payload; never raises.
- `providers/stripe.py` — Stripe Payment-Links adapter. Env STRIPE_SECRET_KEY/WEBHOOK_SECRET. Minor-unit
  native. verify_webhook implements Stripe's t=,v1= signed-payload HMAC scheme. Redacts; never raises.
- `core.py` — the collections core: create_payment_link (idempotent, dormant-safe), get/list_intents,
  list_events, issue_invoice/issue_receipt (idempotent; receipt blocked pre-paid), apply_status (state
  machine + terminal 'paid' guard + CRM stitch + followup scheduling), ingest_webhook (signature-verify
  -> resolve intent by provider_ref via admin-GUC -> apply), mark_paid (manual/offline), refund (provider
  refund + transition), schedule/list/drain_followups. PG-native, RLS via db.engine.session, graceful
  degrade. Money is integer minor units end to end; the API layer is the only /100 boundary.
- `router.py` — FastAPI APIRouter (DEFINED-NOT-MOUNTED). `wire(resolve_tenant, can, need_auth, forbidden,
  firewall)` injects caller.py's auth helpers (no caller.py import cycle). Auth preamble mirrors caller.py;
  spend-sensitive routes wrapped with firewall.require_step_up (pass-through when OFF/no-PIN). Webhook
  route is provider-signature-verified (machine call), NOT step-up'd. `_to_minor` is the sole major->minor
  boundary. router.router is None if FastAPI absent (import-safe).
- `__init__.py` — import-safe facade re-exporting core + providers.
- `tests/_smoke_payments.py` — import + dormant + pure-logic smoke (no PG, no creds).
- `tests/_box_roundtrip.py` + `tests/_run_box.sh` — LIVE PG proof (run on the box; throwaway tenant).
- `STATE.md` — per-unit crash-safe ledger.

## ROUTER ENDPOINTS (for the later mount — prefix suggestion `/payments`)
| Method · Path | Auth | Notes |
|---|---|---|
| GET  /health | none | module + per-provider creds status |
| POST /links | self+write+STEP-UP(spend) | create payment link; body amount(major)/currency/description/provider/customer/idem_key/... |
| GET  /links?status=&limit= | self | list intents |
| GET  /links/{id} | self | intent + its event log |
| GET  /links/{id}/invoice | self | issue/return invoice doc (idempotent) |
| GET  /links/{id}/receipt | self | issue/return receipt doc (paid only) |
| POST /links/{id}/mark-paid | self+write+STEP-UP(spend) | manual/offline mark paid |
| POST /links/{id}/refund | self+write+STEP-UP(spend) | refund (provider + transition) |
| GET  /followups?status=&limit= | self | dunning queue |
| POST /webhooks/{provider} | provider-signature (no tenant-auth) | ingest; dormant secret -> not_configured no-op, always 200 |

## CREDS AWAITED (dormant until these land; roadmap BLOCKER #3 / §11.4)
- RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET, RAZORPAY_WEBHOOK_SECRET (primary, INR).
- STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET (secondary).
With none set: status()=='not_configured', create_payment_link persists a local 'created' intent +
returns {status:'not_configured', pay_url:''}; every provider action is a clean no-op; webhooks return
not_configured. The platform runs end-to-end with the gateway dark. Optional env tunables:
PAYMENTS_DEFAULT_PROVIDER, PAYMENTS_LINK_TTL_S, PAYMENTS_FOLLOWUP_MAX_ATTEMPTS/_BACKOFF_S.

## PROOF
- LOCAL (laptop venv, py3.14, NO PG / NO creds): `python -m payments.tests._smoke_payments` -> **PASS=33
  FAIL=0**. Covers: full import (incl. router definition + 10 routes registered, NOT auto-mounted);
  dormant-until-creds (all provider/status() not_configured, provider actions clean no-ops, DB-less core
  ops degrade to unavailable/None/[] without raising); pure logic (major->minor no float drift,
  deterministic pi_/pe_/pf_ ids, phone canonicalization, BOTH providers' webhook signature verify
  reject+accept+normalize, payload redaction, dormant ingest no-op, invoice/receipt doc builders).
- LIVE PG (ON the box, throwaway tenant 'paytest_box', cleaned up in finally): `_box_roundtrip` ->
  **PASS=19 FAIL=0**. Proved the NEW DDL applies (ensure_schema), the create/idempotency/invoice/receipt/
  mark-paid/event-log/failed/followup/drain queries all EXECUTE against live `famit` Postgres, the CRM
  'purchase' timeline stitch actually landed (joined a real contact), and RLS isolation holds (TENANT2
  cannot get/SELECT TENANT's intent — 0 rows). Throwaway rows DELETED after.
- The temp `/opt/famit-agent/payments/` copy used for the live test was REMOVED; both `famit-caller` +
  `famit-agent` stayed `active`; `GET /api/campaigns` = 200 throughout. caller.py/agent.py never edited,
  no restart, no calls placed, no deploy. The orchestrator commits the local source.
- RECONCILE-TO-PRE-TASK-STATE: the box round-trip's `ensure_schema()` CREATEd the 3 payment_* tables on
  the live `famit` DB (CREATE IF NOT EXISTS isn't rolled back). Since the task is "locally/venv only, no
  deploy", they were DROPPED after the proof (`_drop_box.sql` -> `payment_tables_present=0`). The proof
  stands; prod holds NO payment_* tables now. The tables get (re)created at the real MOUNT step via
  `payments.ensure_schema()` (lazy, idempotent) — same as crm/wallet's first-use creation.

## DEFERRED (named, NOT built here)
- MOUNT: caller.py calls `payments.router.wire(...)` + `app.include_router(payments.router.router,
  prefix="/payments")` + `payments.init()` in startup + `payments.drain_followups()` per scheduler tick.
- payment->wallet TOPUP bridge (wallet.topup idempotent on payment_ref) once a paid customer invoice
  should credit the tenant's prepaid wallet.
- failed-payment follow-up ACTUATION (the WA-template / call nudge) — wired when channels land; today
  drain_followups only advances state + records the intent-to-nudge (channel='dormant').
- subscriptions/recurring mandates; tax/GST line-item engine; customer-portal self-serve pay surface
  (frontend); the firewall _SPEND_ACTIONS registry could add 'payments.create_link'/'payments.refund'.

## CAVEATS (honest)
- The live PG round-trip validated the SQL/RLS/idempotency/stitch with the gateway DORMANT (no creds).
  The REAL provider HTTP paths (create_payment_link / refund / live webhook bodies) are exercised by the
  signature-verify + normalization unit tests with synthetic payloads, but NOT against a live Razorpay/
  Stripe account (no creds) — to be re-verified at creds-onboarding.
- `payments_intents_org_idem_uq` is violated only if the SAME idem_key is reused with a DIFFERENT provider
  (caller misuse) -> swallowed to {status:'error'}. The common same-provider retry is absorbed by the
  id-derived ON CONFLICT (id) DO NOTHING RETURNING race-guard (returns {status:'exists'}).

## RECONCILE / RE-VERIFY (2026-06-10 · resume pass)
- Resumed onto an already-built module (all 14 source files present, STATE.md all-DONE). Per resume
  protocol, RE-VERIFIED on disk rather than rebuilt: `cd droplet_work && python -m payments.tests.
  _smoke_payments` -> **PASS=33 FAIL=0** (system python 3.14.3; the `caps/.venv` is broken — its shebang
  targets a non-existent `/Users/nikhil/miniconda3/bin/python3` from another machine; offline dormant
  tests need no third-party deps so system python is correct).
- GAP FOUND + FIXED: the original log/STATE claimed `brain (patterns.md + decisions.md) appended`, but
  NO such files exist anywhere in the repo — the task's required `brain\` append was missing. Created
  `memory/brain/mod-payments.md` (the established per-module brain convention, matching mod-booking.md),
  capturing the load-bearing vendor->customer-vs-wallet distinction, the 3-table/RLS/idempotency design,
  dormant-until-creds behavior, the DEFINED-NOT-MOUNTED router contract, composition, the broken-venv
  gotcha, creds awaited, and deferred mount steps. No source files changed; module unchanged.
