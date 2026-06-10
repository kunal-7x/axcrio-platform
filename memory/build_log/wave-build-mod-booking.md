# WAVE BUILD — MODULE: Booking / Appointments / Site-Visit engine

Date: 2026-06-10. Built under `droplet_work/booking/` (NEW files only). NOT mounted, NOT deployed,
NOT git-committed (orchestrator commits). Live box untouched (read-only for shared patterns).

## WHAT IT IS
Postgres-native Booking engine: resource availability + ATOMIC slot booking + reminders +
reschedule/cancel + no-show follow-up, tied to the CRM contact spine and (later) Google Calendar.
Booking is in roadmap Section D (Engage, row 107) + P8 (Revenue engine). The primary spec
`design/platform-crm-core.md` is about CONTACTS, not booking — so designed minimally from
MASTER_PLATFORM_ROADMAP.md (rows 107 "Calendar + reminders via Hatchet", 147 Inventory/Capacity,
231 P8, cred row 295 Google Calendar OAuth).

## FILES CREATED (all under droplet_work/booking/)
- `__init__.py` — package marker + composition doc.
- `config.py` — env reads (calendar creds, flags) at call time; `is_configured()` (== calendar ready),
  `pg_available()` (core-booking gate), `status()` REDACTED booleans-only (never echoes a secret).
- `models.py` — OWN SQLAlchemy `Base` (NOT shared db.models.Base — avoids Alembic 0002 collision with
  the parallel crm-core module). 5 tables: `booking_resources`, `bookings`, `booking_reminders`,
  `booking_reminder_fires`, **`booking_events`** (the IMMUTABLE append-only F4 audit leg). Status
  constants + `RLS_TABLES` single source.
- `rls.sql` — ENABLE+FORCE RLS + org_id policy (P1 §5 verbatim) for the 5 tables + the anti-double-book
  PARTIAL UNIQUE INDEX `bookings_active_slot_uq (org_id,resource_id,slot_start) WHERE status IN
  ('booked','rescheduled')` + famit_app grants. Applied at the DEFERRED mount migration.
- `identity.py` — local `canonical_phone` (digits-only `91XXXXXXXXXX`, crm-core §1.1) + `contact_id`
  (`ct_+sha1(org|key)[:16]`, identical to crm.contact_id) computed WITHOUT a DB/caller import; lazy
  `record_booking_timeline` writes a `crm.record_timeline(kind='booking')` row ONLY when crm importable.
- `core.py` — the engine. PURE availability math (enumerate_slots/overlap/is_due/is_no_show — DB-free,
  unit-testable) + atomic `book` (ON CONFLICT DO NOTHING) + `reschedule`/`cancel`/`mark_completed` +
  `get_availability`/`get_booking`/`list_bookings` + `tick` (reminders + no-show, ENQUEUE-ONLY).
- `calendar_sync.py` — Google Calendar port (push/update/cancel/pull_busy), DORMANT-until-creds no-op
  returning `{status:"not_configured"}`; provider-agnostic seam.
- `router.py` — FastAPI `APIRouter(prefix="/booking")`, DEFINED not mounted; injectable `get_ctx`
  tenant/RBAC seam (overridden at mount via `app.dependency_overrides`); 10 endpoints; `ENDPOINTS` list.
- `tests/` (conftest.py + test_booking.py) — 21 tests, fully OFFLINE.
- `STATE.md` — crash-safe build ledger.

## WHAT IT COMPOSES (all LAZY / import-guarded — none imported at top level)
- F1 P1-Postgres: RLS via `db.engine.session(tenant_id, is_admin)` GUC contract; degrades to
  `{status:"not_configured"}` when PG down (live site never affected).
- F2 CRM contacts: bookings link to the deterministic `contact_id`; booking event written to the
  pre-cut `kind='booking'` timeline slot (crm-core §3.3) when crm/ ships. No-op until then.
- F4 Firewall: risky reminder actuation gates on `firewall.check_pin` (FAIL-CLOSED when absent/unset).
- F4 Wallet: spend-gated reminders reserve via `wallet.reserve(resource_type='booking_reminder',
  idem_key='booking_reminder:<rid>')` — no double-spend (single atomic conditional UPDATE + idem).
- F4 Audit (IMMUTABLE): `booking_events` is an APPEND-ONLY ledger of every lifecycle transition
  (booked / rescheduled / cancelled / completed / no_show / reminder_fired). Deterministic id from the
  NATURAL key `be_+sha1(org|booking|type|discriminator)[:24]` — NEVER wall-clock — so ON CONFLICT (id)
  DO NOTHING is REAL replay-idempotency AND two reminder fires for one booking get distinct ids
  (discriminator=reminder_id; every other type is single-occurrence per booking). NEVER UPDATE/DELETE.
  Emitted IN-TXN (ATOMIC, not best-effort): it runs inside the transition's `with eng.session()` block,
  so a failed audit insert rolls the transition back — no booking mutation without its audit row, none
  without the mutation (same discipline as payments). `core.list_events(org, booking_id)` reads the
  trail (newest-first). The `bookings` row is mutated in place; this is the only immutable who/when trace.
- Never top-level `import caller` (circular-import guard, crm-core RTF-4): identity reuses caller.norm
  via a function-local import with a local fallback.

## ROUTER ENDPOINTS (for the deferred mount — `app.include_router(booking.router.router)`)
- GET  /booking/status
- POST /booking/resources
- GET  /booking/availability?resource_id=&day=
- POST /booking/book
- GET  /booking/bookings?contact_id=&status=&limit=
- GET  /booking/bookings/{booking_id}
- POST /booking/bookings/{booking_id}/reschedule
- POST /booking/bookings/{booking_id}/cancel
- POST /booking/bookings/{booking_id}/complete
- POST /booking/tick?dry_run=1  (dry_run default; dry_run=0 actuates through firewall+wallet gates)

## SAFETY INVARIANTS (the load-bearing ones)
1. NO DOUBLE-BOOK: `book()`/`reschedule()` claim a slot with a SINGLE `INSERT ... ON CONFLICT
   (org_id,resource_id,slot_start) WHERE status IN ('booked','rescheduled') DO NOTHING RETURNING id`.
   0 rows == slot_taken. NEVER read-check-write. Proven by test_concurrent_same_slot_only_one_wins.
2. BOOKING IS FREE, SPEND IS GATED: creating/rescheduling/cancelling spends nothing, needs no PIN.
   Only ACTUATING a reminder/no-show nudge is risky -> firewall PIN (fail-closed) + wallet.reserve +
   idempotent `booking_reminder_fires` dedup, then ENQUEUE into the existing gated dial path.
3. tick(dry_run=True) DEFAULT: previews the would-fire set, enqueues NOTHING. require_pin reminder on
   an unattended sweep (no PIN) -> NEVER actuates (stays dark until a PIN is presented).
4. DORMANT-SAFE: no PG / no creds => every entry point returns not_configured, never raises.
5. SECRET REDACTION: config.status() / calendar_sync.status() are booleans only.
6. IMMUTABLE AUDIT: every lifecycle transition appends a `booking_events` row in the SAME txn
   (deterministic id, ON CONFLICT DO NOTHING, never UPDATE/DELETE). A no-op cancel writes NO event.
   Proven by test_lifecycle_writes_immutable_audit_events + the deterministic-id / no-op-cancel tests.

## SCOPE DECISIONS (designed minimally, per task)
- Capacity > 1 per slot is REJECTED with `{reason:"multi_capacity_not_supported"}` (NOT silently
  clamped — a clamp would hide an oversell). Multi-capacity belongs to the Inventory/Capacity
  Management module (roadmap §147) which gates Booking. The `capacity` column is retained
  reserved-for-future so Inventory can light it up with no migration.
- No recurring-rule engine, no timezone gymnastics (store timestamptz + IANA tz, offset computed via
  zoneinfo with an IST fallback). Availability windows live in `resources.data.windows` (jsonb).
- AVAILABILITY IS ADVISORY, `book()` is a RAW CLAIM (deliberate, not an oversight): `get_availability`
  computes legal in-window slots, but `book()` claims whatever `slot_start` it's handed without
  re-checking window membership / past-time / blackout. Rationale: the anti-double-book constraint is
  the load-bearing safety guarantee; window enforcement is a UX/validation concern the frontend +
  availability endpoint own. If a hard server-side "must be a real free slot" gate is wanted later, add
  a window/past/blackout check in `book()` before the INSERT — a localized follow-up, named here so the
  next reader knows it's a decision.

## SMOKE / TEST (green in venv: python 3.14, fastapi 0.115, sqlalchemy 2.0, pytest 9)
`python -m pytest booking/tests/ -q` => **25 passed** (2026-06-10: 21 prior + 4 new audit-leg tests).
Covers: import-safe, dormant-no-PG, identity (+91/91/raw/leading-0 collapse to ONE contact), pure
availability math, ATOMIC CLAIM (single + concurrent + cancel-rebook + reschedule), capacity>1
rejection, IMMUTABLE AUDIT (book->cancel appends events; natural-key deterministic id; no-op cancel
writes none; TWO due reminders on one booking -> TWO distinct reminder_fired rows, no id collision),
tick dry-run-enqueues-nothing + require-pin-fail-closed + enqueue-once-then-idempotent, router defined
+ includes into a fresh app with NO caller.

⚠ SQLITE CAVEAT (honest): the offline suite proves LOGIC + CONSTRAINT SEMANTICS via a SQLite engine
wrapped to honour the `db.engine.session()` contract, with a thin Postgres->SQLite SQL rewriter
(`::jsonb`->'', `now()`->CURRENT_TIMESTAMP, strip `FOR UPDATE`, interval-arith->precomputed compare,
`jsonb_set`->`json_set`). SQLite DOES support the partial unique index + `ON CONFLICT DO NOTHING`,
so the anti-double-book invariant is exercised against a real DB. BUT Postgres-specific SQL
(`(:grace || ' minutes')::interval`, real `jsonb_set`, `FOR UPDATE` row locking, ON CONFLICT
partial-index inference) executes for real ONLY at the deferred mount migration. The rewriter masks
any PG-syntax error — so the mount step must run the migration + an on-box smoke before flipping flags.

## CREDS AWAITED (dormant until present)
- Google Calendar OAuth client (`GOOGLE_CALENDAR_CLIENT_ID` + `_CLIENT_SECRET`) + a per-tenant token
  (`_REFRESH_TOKEN` or `_ACCESS_TOKEN`) + `BOOKING_CALENDAR_SYNC=1` (roadmap P8 / cred row 295).
  Until then calendar_sync is a no-op; core booking works fully on Postgres alone (no cred needed).
- `BOOKING_REMINDERS_ENABLED` (default OFF) — master switch for reminder actuation.

## DEFERRED (orchestrator sequential steps, NOT done here)
1. Create the Alembic revision (e.g. `0003_booking`) that runs `booking.models.Base.metadata.
   create_all()` THEN applies `booking/rls.sql` on the raw psycopg2 cursor (mirror 0001_init). Run
   it on the box + an on-box smoke BEFORE flipping any flag.
2. Mount the router: `from booking.router import router as booking_router; app.include_router(
   booking_router)` and override `get_ctx` -> `app.dependency_overrides[get_ctx] = <resolve_tenant +
   can() RBAC>` so production auth/RBAC binds.
   ⚠ HARD WARNING: the DEFAULT `get_ctx`/`Ctx.can()` is permissive (returns True) and trusts an
   `X-Tenant-Id` header — this is INTENTIONAL only because mounting is deferred + the smoke needs a
   self-contained router. The mount step MUST override `get_ctx`, or every booking endpoint is
   UNAUTHENTICATED + header-trusting (an auth bypass). Do not mount without the override.
3. Replace the `tick` enqueue STUB (`job_id = "stub_<rid>"`) with the real `_spawn_retry_job` /
   WhatsApp enqueue into caller.py's gated dispatch (one-line change, zero new dispatcher), and add a
   cheap `booking.core.tick()` pass to the existing 60s `scheduler_loop`.
4. crm timeline link goes live automatically when crm/ ships (already wired, currently no-op).
5. Wire Google Calendar SDK credential construction in `calendar_sync._client()` when creds land.
