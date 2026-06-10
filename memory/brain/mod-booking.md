# BRAIN — Booking / Appointments / Site-Visit engine

Durable facts + hard-won learnings. Append, never delete.

## WHAT IT IS / WHERE
- Package: `droplet_work/booking/` (NEW files only; not mounted, not deployed). Designed minimally
  from MASTER_PLATFORM_ROADMAP.md (rows 107/147/231/295) — the primary spec
  `design/platform-crm-core.md` is CONTACTS, not booking, so it does not cover this module.
- Postgres-native: resource availability + atomic slot booking + reminders + reschedule/cancel +
  no-show follow-up. Tied to the CRM contact spine; Google Calendar is the only dormant integration.

## LOAD-BEARING DESIGN (do not relearn)
- **Anti-double-book = a DB constraint, not app logic.** Partial unique index
  `bookings_active_slot_uq (org_id,resource_id,slot_start) WHERE status IN ('booked','rescheduled')`
  in `booking/rls.sql`. `core.book()`/`reschedule()` claim via `INSERT ... ON CONFLICT ... DO NOTHING
  RETURNING id`; 0 rows == slot_taken. NEVER read-check-write (same discipline as wallet.reserve's
  single-statement conditional UPDATE). Cancelled/no_show/completed rows fall out of the predicate ->
  the slot is freed for re-book.
- **Own SQLAlchemy Base in booking/models.py — NOT shared db.models.Base.** The crm-core sibling
  already claims Alembic `0002_crm_core` off `0001_init`; a 2nd `0002` would be a multiple-heads
  collision, and the path rule forbids editing shared files. Booking owns its DDL; the mount step
  creates a fresh revision (e.g. 0003) that does create_all() + applies booking/rls.sql.
- **Capacity > 1 is OUT OF SCOPE** — rejected with `multi_capacity_not_supported`, not clamped (a
  silent clamp hides an oversell). Multi-capacity per slot belongs to the Inventory/Capacity module
  (roadmap §147) which gates Booking. The `capacity` column stays reserved-for-future.
- **Identity is LOCAL + crm-compatible.** `contact_id = ct_+sha1(org|canonical_phone)[:16]`,
  canonical = digits-only `91XXXXXXXXXX` (crm-core §1.1). Computed with NO DB and NO top-level
  `import caller` (circular-import guard, crm-core RTF-4) — reuses caller.norm via a function-local
  import with a local fallback. So booking links to the contact spine even before crm/ ships.
- **Spend gating: booking is FREE, only reminder ACTUATION is risky.** `core.tick(dry_run=True)` is
  the default and enqueues nothing. Non-dry-run: idempotency (`booking_reminder_fires` PK
  (org,reminder)) -> firewall PIN (FAIL-CLOSED when absent) -> wallet.reserve (no double-spend,
  idem_key=`booking_reminder:<rid>`) -> ENQUEUE. A require_pin reminder on an unattended scheduler
  sweep NEVER actuates. The real enqueue into caller's gated dial path is a `stub_<rid>` job id today
  (deferred one-line mount).

## COMPOSITION (all lazy / import-guarded)
db.engine (RLS sessions) · firewall (check_pin) · wallet (reserve) · crm.record_timeline
(kind='booking', pre-cut slot crm-core §3.3) · config. None imported at top level except own package.
Dormant everywhere: no PG or no creds => `{status:"not_configured"}`, never raises.

## SMOKE / TEST LEARNINGS
- 20 offline tests green (`python -m pytest booking/tests/ -q`). Pure-math + identity + dormant +
  atomic-claim + tick-gating + router-mountable.
- **SQLite test harness gotchas** (conftest `_rewrite`): SQLite has no `SELECT ... FOR UPDATE`
  (strip it — SQLite serializes writers anyway, invariant preserved), no `::jsonb` literal
  (`->''`), no `now()` in this context (`CURRENT_TIMESTAMP`), no `jsonb_set` (`json_set`), and the
  `(:n || ' minutes')::interval` no-show arithmetic must be pre-rewritten to a precomputed-cutoff
  compare. SQLite DOES support partial unique indexes + `ON CONFLICT DO NOTHING`, so the
  no-double-book invariant is genuinely exercised. CAVEAT: the rewriter MASKS any Postgres-syntax
  error — Postgres-only SQL is validated for real only at the deferred mount migration + on-box smoke.
- Local env is python 3.14 (fastapi 0.115, sqlalchemy 2.0.48, pytest 9.0.3); box venv is py3.12.

## CREDS AWAITED
Google Calendar OAuth client id+secret + per-tenant token + `BOOKING_CALENDAR_SYNC=1` (P8, cred
row 295). `calendar_sync._client()` is import-guarded for `google-api-python-client` and stays
dormant until wired. Core booking needs NO creds (Postgres only).

## DEFERRED (orchestrator)
Alembic 0003_booking revision + rls.sql apply (+ on-box smoke) · mount router + override get_ctx with
resolve_tenant+can() · replace tick stub job_id with real _spawn_retry_job/WhatsApp enqueue + add a
tick pass to scheduler_loop · Google Calendar SDK credential wiring.

## FRONTEND (2026-06-10) — famit-panel/app/booking/
- `app/booking/page.tsx` + `app/booking/api.ts` (page-owned client; shared lib/api.ts NOT touched).
- Premium reuse: Layout, PageHeader(eyebrow="Engage"), Card(title/headContent), KpiCard, data-table,
  surface modal + backdrop-blur, pills (pill-info/success/warning/danger/neutral + pill-dot),
  state-block, toast, signal-glyph. RBAC via useMe/canWrite (mutations hidden for agent role).
- DORMANT-SAFE: api.ts safeGet/safePost resolve 404/501/503/network + engine {status:"not_configured"}
  to a `DORMANT` sentinel (isDormant()), never throws. pg_available=false => DormantPanel (calm
  activation checklist: Postgres / reminders / Google Calendar). Live data flows automatically once
  the router is mounted — zero FE change needed.
- Endpoint wiring: status/availability/book/bookings/reschedule/cancel/complete/tick(dry_run=1 preview).
  Router reads JSON Body(dict) (NOT FormData like legacy /campaigns) -> client sends JSON + Content-Type.
- Operations card calls tick(dry_run=true) = read-only preview of due reminders + no-shows, enqueues
  nothing (matches core.tick dry-run guarantee). Book modal: resource_id + day -> getAvailability free
  slots -> pick slot -> book (conflict => "slot just taken", reload slots).
- VERIFIED: `tsc --noEmit` clean (whole project, 0 errors) + eslint clean on both files + `next build`
  "✓ Compiled successfully" + "✓ Generating static pages (50/50)". The trailing `next build` ENOENT
  (.next/.../page.js.nft.json OR pages-manifest.json — location varies run-to-run) is a WINDOWS-ONLY
  build-trace/filesystem race, NOT a code error and never references the booking route; Linux ship box
  builds clean. Did NOT deploy (ship step owns nav + build + deploy).

## SECURITY FIX (2026-06-10) — token-deriving build_router added
- Hole: `booking/router.py` default `get_ctx` trusted the `X-Tenant-Id` header (spoofable).
- Fix: added `build_router(resolve_tenant, can, need_auth, forbidden, firewall=None)` (mirrors
  workflow-studio): tenant := `resolve_tenant(request)["tenant_id"]`, writes `can(t,"write")` / reads
  `can(t,"read")` (whole tenant dict as 1st arg). CRITICAL: `is_admin` HARDCODED False into every core call
  (it feeds `db.engine.session(tenant_id, is_admin)`; is_admin=1 BYPASSES RLS — never let it be body/header
  derived). `/tick` spend still flows through core.tick firewall(PIN)+wallet with the body `pin` (pin stays
  in body — only tenant/is_admin move to the token). Kept bare `router`+`get_ctx` (test-only). Verified:
  spoofed header B + body B → core saw A, is_admin False; 401 no-token; 25/25 tests still pass.
  MOUNT `build_router(...)` (supersedes the "override get_ctx" instruction). build_log/wave-build-security-fixes.md.

## MOUNTED (2026-06-10) — caller.py mount block, FLAG-GATED DEFAULT-OFF
- **booking: mounted + gate GREEN (flag OFF).** Mounted `build_router(resolve_tenant, can, need_auth,
  _forbidden, firewall=_firewall_mod)` at END of caller.py, mirroring the media-gen block EXACTLY.
  Gate `FEATURE_BOOKING` (cfg_get default "0" → OFF → byte-identical resting behavior). Import-guarded
  (missing/broken booking pkg → `_build_booking_router=None` → mounts nothing, never crashes spine).
- Box caller.py: `4a92b514...` (pre, = post-media-gen-mount) → `dad2997f0338f8c38c55358e13c93779` (post).
  Box backup (rollback target) `caller.py.MNTbak.1781072100` = `4a92b514...`. md5 box==local verified.
- build_router yields prefix `/booking`, **10 route objects = 10 unique paths** (no GET+POST collapse).
- INSTANTIATE-smoke (box py3.12 venv, before restart): flag OFF → 0 `/booking` routes mounted (unchanged);
  FEATURE_BOOKING=1 → 10 mounted. py_compile + `import caller` clean both states.
- REGRESSION GATE GREEN: legacy X-Auth /me,/campaigns,/leads,/contacts,/billing/overview = 200;
  /booking/* = 404 (flag OFF); /run dispatch (form fields + suppression pre-step) job_id minted +
  count=1/suppressed_count=1 = NO paid call, /calls newest = status=suppressed; zero 5xx; both svcs active.
- ⚠ DEPLOY GOTCHA (relearned): /run + /suppression take **Form()** fields, NOT JSON (a JSON body → count=0,
  misleading). Use `curl --data-urlencode`. SSH key path `C:/Users/kunal/.ssh/do-blr-test/id_ed25519` must
  use FORWARD slashes in the Bash tool (backslashes get mangled → publickey denied). Strip `__pycache__`
  on deploy (py3.14 .pyc must not leak into py3.12 box venv). Bare UNGUARDED import smoke before trusting
  the guard (else a hidden ImportError silently mounts nothing even flag-ON).
- ⚠ SCHEMA PREREQ before flag-ON is useful: PG IS up on the box (`[db.engine] Postgres available`) but the
  booking tables DON'T EXIST yet → Alembic 0003_booking (own Base create_all + rls.sql apply) is the
  DEFERRED next step. Flag stays OFF until that lands. This mount touched NO schema on the live earner.
