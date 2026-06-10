# WAVE BUILD — MOD lifecycle-segmentation (Lifecycle Trigger Engine + Customer Segmentation)

Built 2026-06-10. Deferred-from-crm-core module (design/platform-crm-core.md §3.4/§3.5, §5, §6 +
MASTER_PLATFORM_ROADMAP "Lifecycle Trigger Engine" / "Customer Segmentation"). ADDITIVE, dormant-until-
creds, defined-not-mounted, NO git (orchestrator commits), NO caller.py/agent.py edit, NO service restart.

## WHAT IT COMPOSES (built foundation, not reinvented)
- **crm-core** (`crm/` — contacts/contact_timeline read-model): segments compile to ONE parameterized
  `SELECT id FROM contacts WHERE ...`; lifecycle reuses `consent_call`/`stage`/`last_activity_at`.
- **F4 firewall.py** (PIN/step-up): `lifecycle._pin_ok` calls `firewall.check_pin` / `verify_step_up_token`
  — fail-closed (firewall absent / not-enrolled / wrong-PIN / unattended-tick => 0 enqueue).
- **F4 wallet.py** (spend gate): per-tick `budget_cap_minor` truncates the batch vs an estimated cost
  (wallet hooks available for a future hard ledger lock; the admission_gate owns the live spend check).
- **F4 audit.py** (immutable): every fire writes `audit.record(action="lifecycle.triggered")`.
- **caller `_admission_gate` (RTF-1)** — INJECTED (not edited in): the spec's fix is "extract
  `_admission_gate` from /run"; we're forbidden that edit, so the module OWNS the spend check by
  composition — `lifecycle.init(admission_gate=..., enqueue=...)` injects it; both FAIL-CLOSED when absent.
- **P1 RLS pattern**: all 4 new tables ENABLE+FORCE RLS, admin-GUC-OR-org_id policy (db/rls.sql shape),
  every read/write through `db.engine.session(tenant_id, is_admin)`.
- **workforce/endpoints `build_router(...)`** injection shape — same defined-not-mounted, flag-gated router.

## FILES CREATED (all NEW, under droplet_work/lifecycle_segmentation/)
- `schema.sql` — 4 tables: `segments`, `segment_members`, `lifecycle_rules`, `lifecycle_fires`. FORCE
  RLS + admin-GUC policy each. Standalone (NOT Alembic — F2/F4/crm-core precedent; off the P1 keystone
  chain). Idempotent CREATE IF NOT EXISTS. `lifecycle_fires` PK (org,rule,contact,cycle_key) = the
  idempotency guard (a 60s re-tick fires <=once per contact per cycle).
- `segments.py` — the AST compiler (`compile_predicate`: injection-safe, values ALWAYS bound, field+op
  allow-list, `data.<key>` guarded `^[a-z0-9_]+$`), the 5 NAMED builtin templates
  (hot/warm/repeat/churn_risk/high_value), segment CRUD + `eval_segment`/`materialize_segment` (no-op
  without PG). `repeat`+`high_value` flagged `dormant=true` (rely on purchase/amount timeline slots).
- `lifecycle.py` — the engine. `lifecycle_tick(org_id=None, dry_run=True)` ENQUEUE-ONLY, batched (RTF-2,
  one bounded job not N), multi-tenant per-tenant-GUC. Gate chain (order load-bearing):
  consent (fail-closed) -> idempotency (cycle_key) -> cooldown -> PIN/step-up -> admission_gate
  (injected) -> budget_cap (truncate) -> enqueue (injected) -> record fires + audit + webhook.
  `init(admission_gate, enqueue, firewall, wallet, audit, webhook_emit)` injects all foundation deps.
  `cycle_key()` PURE (offline-testable). Rule CRUD + trigger/action allow-lists.
- `scheduler.py` — `run_pass(org_id=None)`: the 2 cheap recurring passes (segment-materialize +
  lifecycle-tick) any driver calls (Hatchet cron / the 60s scheduler_loop / manual endpoint).
  Hard-imports NO driver (Hatchet is cross-box + unwired). Never raises (won't stall caller's loop).
- `endpoints.py` — `build_router(resolve_tenant, can, need_auth, forbidden)` -> APIRouter, DEFINED NOT
  MOUNTED. Flag LIFECYCLE_ENABLED default OFF => every route {not_enabled} 503 (include is byte-safe).
- `__init__.py` — import-safe facade + re-exports + `build_router` lazy wrapper.
- `tests/test_lifecycle_segmentation.py` — 45 offline checks (no PG/creds), all PASS.

## SMOKE / PROOF (offline, no PG, no creds, no calls, no spend)
- `python lifecycle_segmentation/tests/test_lifecycle_segmentation.py` => **45/45 PASS**:
  AST injection guard (malicious jsonb key / off-list field / off-list op / older_than_days-on-non-ts
  all -> SegmentError); values bound-not-inlined; 5 named builtins present + compile; repeat+high_value
  dormant; cycle_key stable+bucketed (60s re-tick = same bucket, next cycle = new); PIN fail-closed
  (absent/not-enrolled/wrong/unattended => False); fire_rule no-admission => 0 enqueue + mock never
  called; admission refusal => 0 enqueue; budget truncation; tick no-PG => 0; every PG fn no-ops
  without PG; status leaks no secrets (presence booleans only) + reports actuation_armed=false.
- Import + router build: `import lifecycle_segmentation` OK; `build_router(...)` -> 10 routes;
  `available()=False`, `init()->False` (fail-closed) without PG. No top-level caller/agent import; db lazy.

## ROUTER ENDPOINTS (for the later mount — app.include_router(ls.build_router(...)))
- GET    /segments
- POST   /segments                    {name, definition, description?}  (SegmentError -> 400)
- POST   /segments/seed-builtins
- GET    /segments/{id}/members
- DELETE /segments/{id}               (builtins deactivate, not delete)
- GET    /lifecycle/rules
- POST   /lifecycle/rules             {name, trigger, action, segment_id?, enabled?, require_pin?,
                                        budget_cap_minor?, max_targets?, cooldown_days?}
- DELETE /lifecycle/rules/{id}
- POST   /lifecycle/tick              {dry_run=1 default, rule_id?}  (dry_run=0 needs write + X-Step-Up)
- GET    /lifecycle/status

## CREDS / DEPS AWAITED (dormant-until-wired)
1. **caller-side wiring (deferred sequential step)** — `app.include_router(ls.build_router(resolve_tenant,
   can, need_auth, forbidden))` + `ls.init(admission_gate=caller._admission_gate_or_extract,
   enqueue=<batch single-job enqueuer in the /run shape>, firewall=firewall, wallet=wallet, audit=audit,
   webhook_emit=<existing webhook emit>)`. Until injected: actuation_armed=false, tick previews only.
   NOTE (RTF-1): caller has NO standalone `_admission_gate` yet (the balance/monthly gate lives inline in
   POST /run). The orchestrator extracts it (pure refactor, regression-safe) OR passes an equivalent
   admission callable. Module fail-closes (0 enqueue) until then — never an un-gated spend.
2. **LIFECYCLE_ENABLED=1** flag to expose the routes (default OFF).
3. **FIREWALL_ENABLED=1 + a tenant PIN enrolled** for risky (spend) lifecycle actuation; else require_pin
   rules stay dark (correct fail-closed default).
4. **Hatchet cross-box wiring** (orchestration-hatchet brain) for durable cron firing — interim driver is
   the 60s scheduler_loop pass. No Hatchet hard-dep in this module.

## DEFERRED (named later units, NOT built here)
- The caller.py mount + `ls.init(...)` injection (the deferred sequential wiring step — orchestrator).
- A real `enqueue` that builds ONE bounded multi-lead job in the /run shape (re-enters run_job's gate
  chain) — the module defines the contract + fail-closes without it.
- `segment_entered` lifecycle trigger live wiring (predicate + scope built; needs the segment-diff feed).
- Frontend Segmentation workspace + Lifecycle rule builder UI (Sell/Automate sections).
- Purchase/amount timeline slots lighting up `repeat`/`high_value` (Booking/Payments modules).
- LLM-enriched NBA for re-engagement copy (CRM_NBA_LLM; rule-based only today).

## DEVIATIONS (documented, fix-wins per F4 precedent)
- Package name `lifecycle_segmentation` (underscore) where the brief said "lifecycle-segmentation"
  (a hyphen is not a valid Python identifier — `import` + the later mount both need the underscore).
- Standalone schema.sql, not Alembic 0002 (matches crm/kb/wallet/workforce; off the P1 keystone chain).
- Module OWNS the spend admission check by COMPOSITION (injected, fail-closed) rather than editing
  caller's /run (forbidden) — folds RTF-1 without the forbidden edit.

---

## 2026-06-10 · RE-ISSUE RECONCILE (orchestrator re-ran this as "the 1 module that failed earlier")
The build above was ALREADY complete + green from the prior session. Per the crash-safe RESUME protocol
this re-issue was RECONCILED (verified), NOT rebuilt (rebuilding green code regresses verified work).
- **Files on disk (7):** `__init__.py`, `schema.sql`, `segments.py` (22KB), `lifecycle.py` (30KB),
  `scheduler.py`, `endpoints.py`, `tests/test_lifecycle_segmentation.py`. All present.
- **Independent re-proof:** `python lifecycle_segmentation/tests/test_lifecycle_segmentation.py` => **45/45
  PASS**; `python -m pytest lifecycle_segmentation/tests/ -q` => **12 passed**. Fresh import-smoke:
  `import lifecycle_segmentation` clean; `available()`/`init()` => False (fail-closed, no PG); injection
  guard raises SegmentError on a SQL-laden field; 5 builtins (hot/warm/repeat/churn_risk/high_value) present;
  `lifecycle_tick(dry_run=False)` with no deps => 0 enqueued; `build_router(...)` => 10 route objects / 8 paths.
- **NOT-MOUNTED invariant PROVEN:** `grep -c lifecycle_segmentation caller.py` == **0** (run path imports
  nothing). Router derives tenant from the TOKEN (`t["tenant_id"]`), never the request body → already avoids
  the workflow-studio/funnels body-tenant cross-tenant hole by construction. Flag `LIFECYCLE_ENABLED` OFF.
- **Foundation legs TICKED one-by-one** (the booking-missing-audit discipline): F1 RLS ✓ · CRM contacts ✓ ·
  F4 firewall (real `verify_step_up_token`, sub-bound, fail-closed) ✓ · F4 audit IMMUTABLE
  (`audit.record(action="lifecycle.triggered")` on every fire — present, unlike booking's silent skip) ✓ ·
  F4 wallet (injected + budget_cap truncation; a direct `wallet.reserve` hard-lock is NAMED-deferred per
  spec residual-risk-3, not silent) ✓ · workforce build_router-injection shape ✓.
- **CAVEAT (honest, unchanged):** offline laptop proof exercises IMPORT / DEGRADE / LOGIC / gate-chain /
  injection-guard / fail-closed only — the real PG DDL + RLS isolation + ON-CONFLICT idempotency + the live
  caller `admission_gate`/`enqueue` injection are box-verifiable later (like payments 19/19), NOT proven by
  the green local run. No caller.py/agent.py edit, no .env change, no deploy, no calls, no git this pass.
- **VERDICT: already complete; reconciled green. No code changes needed.** Deferred items unchanged (see
  DEFERRED above): the caller.py mount + `ls.init(...)` injection, the real bounded-batch enqueue, Hatchet
  durable cron, segment_entered live diff feed, frontend, purchase/amount slots (Booking/Payments), LLM NBA copy.
