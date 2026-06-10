# BRAIN — MOD lifecycle-segmentation (Lifecycle Trigger Engine + Customer Segmentation)

Durable facts + hard-won learnings. Append, never delete.
Spec: `design/platform-crm-core.md` (§3.4/§3.5 segments+lifecycle, §5 actuation safety, §6 AST).
Build log: `memory/build_log/wave-build-mod-lifecycle-segmentation.md`.
Code: `droplet_work/lifecycle_segmentation/` (segments.py, lifecycle.py, scheduler.py, endpoints.py, schema.sql).

## WHAT IT IS / SCOPE
- Sits ON TOP of crm-core's `contacts` read-model. Two halves:
  - **Segmentation** — saved JSON predicate ASTs compiled to ONE parameterized `SELECT id FROM contacts
    WHERE ...`. Powers campaigns + lifecycle targeting + analytics. NOT a query language (fixed allow-list).
  - **Lifecycle Trigger Engine** — proactive re-engagement by service cycle (salon 30d, clinic follow-up,
    real-estate re-check) on a timer. ENQUEUE-ONLY through the existing gated dial path; NEVER a 2nd dialer.
- ADDITIVE, dormant-until-creds, defined-not-mounted. Built but NOT wired (deferred sequential step).

## THE 5 NAMED SEGMENTS (builtin templates, seeded per-tenant on demand)
`hot` (score>=70) · `warm` (engaged/contacted, score<=69, reachable) · `repeat` (has purchase — DORMANT)
· `churn_risk` (was engaged/qualified + last_activity older_than_days N + reachable) · `high_value`
(high spend — DORMANT). `repeat`/`high_value` rely on purchase/amount timeline slots that ship with
Booking/Payments — predicate defined now, lights up with zero schema change.

## HARD-WON / LOAD-BEARING (do not relearn)
- **Package name MUST be underscore** `lifecycle_segmentation`, never the brief's hyphenated
  "lifecycle-segmentation" — a hyphen is not a valid Python identifier; `import` + the later
  `app.include_router` mount both break on a hyphen dir. Repo's mounted packages (`ads_engine`,
  `ai_manager`, `media_gen`) all use underscores. Deviation documented in the build log.
- **The spend gate is OWNED by COMPOSITION, not by editing caller.** Spec RTF-1's fix is "extract
  `_admission_gate` from POST /run" because `run_job` does NOT re-apply balance/monthly on the enqueue
  path. We're forbidden to edit caller, so `lifecycle.init(admission_gate=..., enqueue=...)` INJECTS
  those callables; BOTH fail-closed (absent => 0 enqueue). Caller has NO standalone `_admission_gate`
  yet (it's inline in /run) — the orchestrator extracts it OR passes an equivalent callable at wire time.
- **Gate order is load-bearing** (test enforces it): consent (fail-closed, reads contacts.consent_call +
  stage!=opted_out) -> idempotency (lifecycle_fires cycle_key) -> cooldown -> PIN/step-up -> admission_gate
  -> budget_cap (truncate batch, RTF-2) -> ENQUEUE one bounded job (NOT N) -> record fires + audit + webhook.
- **PIN is fail-closed via F4 firewall** (firewall.py now EXISTS — spec RTF-3 "PIN unbuilt" is stale).
  `_pin_ok` False when: firewall not wired / not available / tenant not enrolled / wrong PIN / unattended
  tick (pin=''). A require_pin rule on a scheduler/Hatchet tick (no interactive PIN) NEVER enqueues. Good.
- **cycle_key is the idempotency bucket** — PK `lifecycle_fires(org,rule,contact,cycle_key)`. PURE fn so
  it tests offline. cycle_days -> day-ordinal//value bucket; dormant_days -> ISO week; stage_age -> month;
  segment_entered -> day. A 60s re-tick within a cycle = identical key = ON CONFLICT DO NOTHING = no storm.
- **AST injection safety**: values ALWAYS bound params; only allow-listed COLUMN names + a
  `^[a-z0-9_]+$`-validated jsonb key are ever inlined. `older_than_days`/`newer_than_days` only on ts
  fields. Off-list field/op/key -> SegmentError -> endpoint 400. Proven by the malicious-key test.
- **Multi-tenant tick runs per-tenant with the tenant GUC set** — `lifecycle_tick(org_id=None)` reads the
  distinct enabled orgs under admin GUC, then fires each tenant under ITS OWN GUC. Never one admin GUC for
  the fire/membership writes (would cross-pollinate segments across tenants).
- **No driver hard-import.** `scheduler.run_pass()` is the one fn Hatchet cron / the 60s scheduler_loop /
  the manual endpoint all call. Hatchet is cross-box + unwired (orchestration-hatchet brain) — never
  imported here. Interim driver = the existing scheduler_loop pass.
- **Standalone schema.sql** (not Alembic) — F2/F4/crm-core precedent; off the P1 0001/0002 keystone chain.
  `ensure_schema()` lazy first-use. 4 tables, all FORCE RLS + admin-GUC-OR-org_id policy.

## SMOKE (offline, repeatable, no creds)
`python lifecycle_segmentation/tests/test_lifecycle_segmentation.py` => 45/45 PASS. Covers AST injection,
the 5 builtins, cycle_key idempotency, the full gate chain via mocks (enqueue mock never called on a
fail-closed path = the proof there's zero un-gated spend), and no-op-without-PG for every PG fn.

## NEXT (deferred wiring — the orchestrator's sequential step)
1. `app.include_router(ls.build_router(resolve_tenant, can, need_auth, forbidden))` in caller.py.
2. `ls.init(admission_gate=<extracted /run gate>, enqueue=<bounded single-job /run-shape enqueuer>,
   firewall=firewall, wallet=wallet, audit=audit, webhook_emit=<existing emit>)` after store.init.
3. Add `ls.scheduler.run_pass()` (try/except) to scheduler_loop (2 cheap passes; enqueue-only).
4. Flip LIFECYCLE_ENABLED=1; risky actuation also needs FIREWALL_ENABLED=1 + a tenant PIN.
Until then: actuation_armed=false, tick previews only, NO spend possible (fail-closed everywhere).
