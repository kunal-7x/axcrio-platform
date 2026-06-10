# WAVE-BUILD-P1 — POSTGRES KEYSTONE (DB-ARCHITECT)

Spec: `design/p1-postgres.md` (follow verbatim). Decision context: `ARCHITECTURE_DECISION.md`
(modular-monolith control plane). STATE: `droplet_work/P1_FOUNDATION_STATE.md`.
Box: famit@168.144.153.145 (/opt/famit-agent/), svc famit-caller (uvicorn :8209) + famit-agent.
venv /opt/capsy-agent/.venv (py3.12). SSH key C:\Users\kunal\.ssh\do-blr-test\id_ed25519.
Mode of work: non-breaking strangler; DEFAULT every store MODE=json (deploy changes nothing);
JSON authoritative until shadow_diff==0. Per-unit deploy→verify→rollback. NO git (orchestrator commits).

## RECONCILE (2026-06-09, session start)
- caller.py local==box md5 `a60b8a9e...` (clean base, no drift). memory.py/auth.py/config.py local==box.
- ⚠ agent.py DRIFT: local `1a154ea1...` != box `9150fabe...` (another session voice-tuned box agent.py).
  → For U4, pull BOX agent.py as base before the 3 memory-rekey edits. Do NOT ship stale local.
- Postgres 16.14 already installed + active on box (PG>=14 → SCRAM; B3 PgBouncer fix applies).
- db `famit` EXISTS; role `famit_app` EXISTS (NOSUPERUSER f, NOBYPASSRLS f, canlogin t). 0 tables.
- venv deps (sqlalchemy/asyncpg/...) NOT yet installed at start. PG_DSN/STORE_MODES NOT in .env yet.
- So U1 = partially done (PG+db+role); remaining = deps + .env vars + dual-driver connect proof.

## SEQUENCING DECISION (logged per advisor, orchestrator please note)
1. **Modularization (caller.py → per-domain APIRouters) is DEFERRED to its own wave AFTER the storage
   seam.** Rationale: the verified spec (p1-postgres.md) scopes caller.py to SURGICAL edits only and
   never specifies a router split. The U3 byte-identical/md5 regression gate is the live-earner safety
   net; restructuring a 153KB file in the same wave makes md5 comparison meaningless (can't tell seam
   regression from refactor regression). Land the storage seam (verified, critical-path, report-gating)
   first; modularize as a separate wave with contract-level verification. ARCHITECTURE_DECISION names it
   part of this seam, but verified-spec + safety-net both say sequence-after. This is the explicit call.
2. **No-paid-call OVERRIDES §9 U4's "real metered test call".** Verify memory rekey by two-tenant FILE
   test + code path; confirm /run DISPATCHES (enqueues) only — never complete a billable call.
3. Critical path to the report gate (leads shadow_diff==0): **U1 → U2 → U3 → U5 → U6.** U4 + other-store
   dual flips (U9) are real but NOT report-gating; do them safe/documented, don't let them block leads.

## UNITS

### [DONE] U1 PROVISION (2026-06-09)
- PG 16.14 + db `famit` + role `famit_app` (NOSUPERUSER/NOBYPASSRLS/login) were pre-existing from
  earlier _provision_pg.sh run. Completed the remainder:
- Backed up `.env` → `/opt/famit-agent/.env.P1bak.1781013966`.
- pip into /opt/capsy-agent/.venv: sqlalchemy[asyncio]>=2.0 (got 2.0.50), asyncpg 0.31.0,
  psycopg2-binary, alembic, greenlet → DEPS_OK.
- Dual-driver TCP connect proof as famit_app: PSYCOPG2_OK + ASYNCPG_OK (not just psql CLI).
- Appended 5 vars to .env: PG_DSN (psycopg2), PG_DSN_ASYNC (asyncpg), STORE_MODES= (EMPTY → all json),
  STORE_PG_TIMEOUT_MS=800, MEMORY_TENANT_SCOPED=1. Password = famit_p1_localpw (localhost-only).
- config.get loads all 5 (N2 Doppler-overlay check: PG_DSN_loads True, no shadow).
- NO caller restart (nothing reads these until store.init U3). Regression gate GREEN: famit-caller +
  famit-agent active, legacy X-Auth /campaigns 200, caller.py md5 a60b8a9e unchanged.

### [DONE] U2 SCHEMA (2026-06-09)
- Created db/__init__.py, db/engine.py (import-safe two-engine factory: sync psycopg2 + async asyncpg
  NullPool/stmt-cache-0; bounded 2s startup probe; session()/asession() set LOCAL app.tenant_id/is_admin
  in-txn GUC; available()/status()), db/models.py (SQLAlchemy 2.0, 17 tables per §3, *_raw + timestamptz
  + data jsonb catch-all, functional unique idx lower(email), all §3 indexes), db/rls.sql (§5 FORCE RLS
  + per-table isolation policy + grants).
- alembic.ini + migrations/env.py (resolves PG_DSN via config.get; NullPool) + script.py.mako +
  versions/0001_init.py (create_all from Base.metadata -> RLS via RAW psycopg2 cursor).
- 3 migration fixes (each rolled back atomically — transactional DDL, zero partial state):
  (1) op.execute/text() mangled rls.sql %1$s/%2$I postgres format() placeholders -> switched to raw cursor.
  (2) exec_driver_sql passed immutabledict params -> psycopg2 reject -> use bind.connection.connection cursor.
  (3) ALTER DATABASE famit SET app.tenant_id='' DENIED for non-superuser owner famit_app -> set the two
      db-level GUC defaults (app.tenant_id='', app.is_admin='0') ONCE as postgres superuser; removed the
      ALTER DATABASE from rls.sql. Fail-closed still holds even without it (current_setting(...,true)=NULL
      -> org_id=NULL is NULL not TRUE -> rows hidden).
- alembic upgrade head exit 0. VERIFIED: 18 tables (17 + alembic_version); leads relrowsecurity=t
  relforcerowsecurity=t; 17 policies; leads indexes (org_idx, org_phone_uq, org_score_idx, pkey);
  alembic_version=0001_init. Zero app code changed; app still pure json (PG idle).
- Regression gate GREEN: famit-caller+famit-agent active, legacy /campaigns 200, caller md5 a60b8a9e unchanged.
- One-time superuser provisioning step for any rebuild: `ALTER DATABASE famit SET app.tenant_id='';
  ALTER DATABASE famit SET app.is_admin='0';` as postgres (documented; not in the famit_app migration).

## RECONCILE (2026-06-09, SESSION 2 — crash recovery, new DB-ARCHITECT)
Prior P1 agent died on a socket error (~72 calls, no report). STABILIZE first found the box
ALREADY HEALTHY — no rollback needed:
- famit-caller + famit-agent both `active` (not crash-looping). caller.py imports clean; startup log
  `[db.engine] Postgres available (sync ok, async=ok)`. /campaigns,/leads,/calls,/stats all 200.
- Box has db/{__init__,engine,models,rls.sql} + store.py (17636B) DEPLOYED. caller.py md5
  `32c447d6` (the seam-rewired version, NOT pre-P1 `a60b8a9e`) — U3 STORE SEAM is DONE on box.
- store.py md5 `50f81a14`. LOCAL droplet_work copies == box for caller.py + store.py (no drift,
  no stale-deploy risk). db/engine `7c4538b1`, db/models `0f092a64`. P1bak backup present (14:25).
- .env: `STORE_MODES=` EMPTY → every store json (behavior byte-identical to pre-P1). Confirmed
  seam shims (caller.py:444-471) guard `_store is not None` and pass-through to *_raw in json mode.
- leads live at `var/leads.json` (5 leads, all non-empty ids: bc356f71/71b9e9a2/94179590/eb113249/
  e960661a; tenants admin×3-distinct-phones + ae1ba3017296 + 21d0a13603da). PG leads table = 0 rows.

WHAT THE DEAD AGENT FINISHED vs THE GAP:
- DONE on box: U1 PROVISION, U2 SCHEMA, U3 STORE SEAM (store.py + caller seam rewire, deployed,
  healthy, all-json). These were already verified live.
- GAP (this session): backfill.py + shadow_diff.py did NOT exist anywhere (local or box); leads never
  flipped to dual; PG never seeded. = spec-U5 (leads→dual) + spec-U6 (backfill+shadow_diff).

### [DONE] U-scripts: backfill.py + shadow_diff.py (2026-06-09 S2)
- shadow_diff.py: `python shadow_diff.py <entity>` → exit 0 iff PG matches JSON. Compares COUNT +
  id-set (+only_json/+only_pg) + per-id `data jsonb` normalized BOTH sides with
  `json.dumps(sort_keys=True,ensure_ascii=False)`. Promoted columns deliberately NOT compared
  (mapper coerces them → false drift). Admin GUC read (whole-store spans tenants).
- backfill.py: `python backfill.py <entity> [--commit]` (dry-run default). Idempotent UPSERT by id,
  EXACT column list + `CAST(:data AS jsonb)` copied from store._pg_reconcile_leads → rows byte-
  identical to the live mirror. Admin GUC. UPSERT-only (no delete-by-omission — that's the mirror's job).
- Both REUSE store._leads_rows/_lead_key (NOT a caller.py import — avoids re-triggering
  _migrate_to_admin/CALLS=_read at import). Both inert (nothing in the service imports them) =
  deploying them changes nothing about the running service. md5 local==box
  (shadow_diff `d16b85c7`, backfill `9d62e8eb`).
- FREE CORRECTNESS TEST (still all-json, zero service risk): `shadow_diff leads` →
  `json=5 pg=0 ... shadow_diff=5` exit 1 (correctly DETECTS drift + lists 5 ids). `backfill leads`
  dry-run → `json=5 pg=0 upserted=0` no write, exit 0. Proves connect/import/mapper/detection.
- No service restart, no .env change → regression gate trivially green (caller md5 unchanged).

### [DONE] U5 LEADS→DUAL + U6 BACKFILL — REPORT GATE GREEN (2026-06-09 S2)  ⭐ shadow_diff==0
- Backed up `.env` → `.env.P1bak.1781015967`. Flipped `STORE_MODES=` → `STORE_MODES=leads:dual`
  (.env-ONLY change; caller.py/store.py byte-identical, md5 `32c447d6`/`50f81a14` unchanged).
- Restarted famit-caller: came up clean, `[db.engine] Postgres available`, both services active.
- `python backfill.py leads --commit` → `BACKFILL leads: json=5 pg=5 upserted=5` (run at quiescence,
  zero /run traffic). Spot-check 2 leads: PG `data jsonb` == JSON object byte-for-byte (True/True).
- ⭐ `python shadow_diff.py leads` → `json=5 pg=5 only_json=0 only_pg=0 field_drift=0 => shadow_diff=0`
  EXIT 0. THE REPORT GATE. leads is fully converged JSON↔PG.
- LIVE DUAL-MIRROR FIRE PROOF (reversible, no residue): POST /leads throwaway lead (phone
  +910000000099, unique → no org_phone_uq collision) → JSON total=6; within 2s the async coalescing
  worker mirrored it to PG (id 112b0023 present). DELETE /leads/112b0023 → JSON back to 5; mirror's
  delete-by-omission removed it from PG; shadow_diff leads → 0 again. Proves the live dual write→
  enqueue→worker→reconcile path fires on BOTH add and delete and self-heals to 0. (So "left at dual"
  genuinely means the mirror works — not just a one-shot backfill seed.)
- FINAL REGRESSION GATE GREEN: famit-caller+famit-agent active; /campaigns /leads /stats /me
  /billing/overview all 200 (legacy X-Auth); ZERO 5xx in window (incl. through the mirror test);
  caller/store md5 unchanged. JWT /auth/login route structurally intact (returns clean
  `invalid credentials`, not 5xx) — admin uses pass_hash+salt; real plaintext NOT guessed/brute-forced
  (gate's "service not broken" intent met; .env flip cannot touch auth anyway).

## STEADY STATE AT END OF SESSION 2
- Store MODEs: **leads=dual** (PG-mirrored, shadow_diff==0). ALL OTHER stores=json (unchanged,
  STORE_MODES lists only `leads:dual`). PG `leads` table = 5 rows == JSON.
- This is the spec's acceptable P1 steady state. leads→pg (spec-U7) DEFERRED: needs the §6.6
  per-request tenant contextvar wired first (store.py `_LEADS_PG_TENANT_WIRED=False` gates it; pg
  would auto-cap to dual until then anyway).
- NOT TOUCHED (next waves): spec-U4 MEMORY RE-KEY (carries forbidden metered call), U7 leads→pg,
  U8 /admin/store-status+/admin/shadow-diff, U9 backfill-rest+dual-flips, U10 RLS proof+PgBouncer,
  caller.py→APIRouter modularization (deferred post-seam per S1 sequencing note above).
- ROLLBACK (if ever needed): `cp .env.P1bak.1781015967 .env` (restores STORE_MODES empty → all json)
  + restart famit-caller. backfill.py/shadow_diff.py are inert (no service import) — leave or remove freely.

### [DONE] RLS CROSS-TENANT PROOF (2026-06-09 S2, read-only, zero service risk)
- leads PG now holds 3 distinct tenants (admin×3 rows, ae1ba3017296×1, 21d0a13603da×1) → proof is cheap.
- `engine.session(tenant_id, is_admin)` + `SELECT count(*) FROM leads`:
  admin GUC (is_admin=1) → 5 (all); ae1ba3017296 → 1 (own); 21d0a13603da → 1 (own); admin vendor → 3 (own);
  nonexistent tenant → 0 (fail-closed isolation). FORCE-RLS + SET LOCAL app.tenant_id GUC isolation HOLDS.
- This is the §5 security keystone proven on real data — the U10 RLS-proof item is effectively done for leads.

### BRAIN UPDATED (2026-06-09 S2)
- Appended P1 storage-seam + crash-recovery learnings to
  `C:\Users\kunal\.claude\projects\C--Users-kunal-desktop-caps\memory\brain\mistakes.md` (NOTE: brain
  lives under the .claude projects memory root, NOT desktop\caps\memory — two separate roots).
- HANDOFF.md (same .claude root) given a P1-status banner. STATE = droplet_work/P1_FOUNDATION_STATE.md.

## SESSION 3 (2026-06-09) — U9 BATCH: NEXT CORE STORES json→dual (DB-ARCHITECT)
Scope from orchestrator: flip campaigns, calls, suppression, retry_queue, callbacks, webhooks to dual
the proven leads way. RECONCILE at start: box==local md5 for store/backfill/shadow_diff/models/caller
(50f81a14/9d62e8eb/d16b85c7/0f092a64/32c447d6, no drift). STORE_MODES=leads:dual. Both svcs active.

### SCOPE RESOLUTION (2 of the 6 named are deliberately N-A, not dropped):
- **callbacks**: NOT a separate store. Spec §3.3: callbacks live INSIDE retry_queue, discriminated by
  reason=='callback'. The retry_queue flip IS the callbacks flip. No table, no separate flip.
- **campaigns**: written per-id as `var/campaigns/<id>.json` via direct `.write_text` (caller.py:824/2069),
  NOT a whole-file `_write`. The store.py seam keys by file `.name` + does whole-file-snapshot reconcile —
  structurally cannot mirror a per-id-file store. §3.2 also mandates campaigns=json-only in P1 (agent reads
  campaigns/<id>.json). DEFERRED: needs a different per-id-upsert mirror = its own unit (NOT this batch).
- So this batch flips the 4 that fit the proven whole-file-snapshot pattern: **calls, suppression,
  retry_queue, webhooks**. NO Alembic needed — all 4 tables + RLS already exist from U2.

### [DONE] STORE.PY GENERALIZED + DEPLOYED INERT (2026-06-09 S3)
- store.py: StoreSpec gained `cols`/`key_cols`/`order_by`; added mappers `_calls_rows`/`_suppression_rows`/
  `_retry_rows`/`_webhooks_rows` + keys `_id_key`/`_orgphone_key`. `_pg_reconcile_leads` (name kept for
  call-site stability) is now SPEC-DRIVEN over any table via new `build_upsert_sql(spec)` +
  `_delete_by_omission_sql(spec)` (row-tuple `(k..) NOT IN unnest(:kc_*)` — works for id-PK AND
  (org_id,phone) composite PK). B1 coalescing worker + B2 empty-snapshot guard unchanged & reused.
  Registered specs: leads(pg-cap), calls/suppression/retry_queue/webhooks(dual-cap). campaigns NOT registered.
- backfill.py + shadow_diff.py: generalized to resolve any StoreSpec from store._SPECS by entity name
  (reuse build_upsert_sql + mapper + key → byte-identical rows). shadow_diff PG side now `SELECT data`
  only (NOT `SELECT id,data`) and re-derives the key via the spec mapper → suppression's composite key
  no longer errors (the headline fix; `SELECT id` would have thrown on the no-id table).
- Deployed (box md5 store=252ebbf9 backfill=a500e583 shadow_diff=6e2d6729, local==box). Backups
  `*.P1bak.1781017154`. Restarted famit-caller → `[db.engine] Postgres available`; both svcs active.
- REFACTOR REGRESSION (the check HTTP gate can't catch): `shadow_diff leads` STILL ==0 (json=5 pg=5)
  → generalization didn't break the working leads path. HTTP gate green (campaigns/leads/stats/
  billing-overview/me all 200). DRY-RUN shadow_diff each new store ran cleanly (suppression composite-key
  SQL valid); calls correctly detects 78 only_json (pre-backfill drift) → detection proven.
- STORE_MODES UNCHANGED (still leads:dual) at this step → all 4 new specs inert (mode=json pass-through).

### [DONE] calls → DUAL ⭐ shadow_diff==0 (2026-06-09 S3)  [the real proof: 78 rows]
- .env backup `.env.P1bak.1781017247`. STORE_MODES=leads:dual → `leads:dual,calls:dual`. Restart caller; both svcs active.
- `backfill.py calls --commit` → `BACKFILL calls: json=78 pg=78 upserted=78`. ⭐ `shadow_diff calls` →
  `json=78 pg=78 only_json=0 only_pg=0 field_drift=0 => shadow_diff=0` (exit 0). 78 records mirrored byte-identical.
- calls is dual-CAPPED (max_safe=dual, NEVER pg — in-RAM CALLS cache + record_call). Regression gate GREEN
  (campaigns/leads/stats/billing-overview/me all 200); zero 5xx/traceback in window.

### ⚠ B2 BUG FOUND + FIXED MID-BATCH (2026-06-09 S3) — empty-snapshot prune for dual mode
- During the suppression fire-proof, DELETE-to-empty left a STALE PG row (shadow_diff=1, only_pg=1).
  ROOT CAUSE: the B2 empty-snapshot guard ("skip delete-by-omission when incoming key-set empty & PG
  non-empty") was mis-scoped to BOTH dual+pg. But in DUAL mode the mirror snapshot IS the payload
  `_write_raw` just wrote authoritatively to the JSON file (NOT a re-read that could fail) → an empty
  snapshot is GROUND TRUTH (JSON==[]), so PG MUST be pruned. The guard belongs ONLY to pg mode (no
  JSON backstop → empty-wipe = real data loss). Without the fix, EVERY empty-prone store (suppression,
  retry_queue, webhooks) silently drifts to shadow_diff>0 the first time it clears in prod → the gate
  becomes a lie. (calls/leads unaffected — non-empty incoming never hits the empty branch.)
- FIX (store.py `_pg_reconcile_leads` empty branch): `if incoming: delete-by-omission; elif mode=='pg':
  skip (B2); else (dual): DELETE FROM <table>` (plain DELETE also dodges the empty-array unnest cast).
  Redeployed store.py (box md5 e2a24fc9, local==box), restarted. Backup store.py.P1bak.b2fix.*.
- VERIFIED: cleaned orphan (admin-GUC DELETE, 1 row — note: plain psql as famit_app can't see it, RLS
  hides org_id=admin without the admin GUC). Re-ran fire-proof: ADD → json=1 pg=1 shadow_diff=0; DELETE
  → mirror AUTO-PRUNED to json=0 pg=0 shadow_diff=0 (no manual cleanup). leads(5)+calls(78) still ==0
  after the shared-file change (no regression).

### [DONE] suppression → DUAL ⭐ shadow_diff==0 (2026-06-09 S3) [composite (org_id,phone) PK]
- .env backup `.env.P1bak.1781017<...>`. STORE_MODES += `suppression:dual`. Restart; both svcs active.
- backfill suppression --commit → json=0 pg=0 (empty store). shadow_diff suppression → 0.
- ⭐ LIVE FIRE-PROOF (composite key, reversible, post-B2-fix): POST /suppression +910000000088 → mirror
  writes (json=1 pg=1, diff 0); DELETE → mirror auto-prunes (json=0 pg=0, diff 0). The composite-key
  reconcile (`(org_id,phone) NOT IN unnest(:kc_org_id,:kc_phone)` + dual empty-prune) fires on add+delete.
- shadow_diff.py composite-key fix proven: PG side `SELECT data` only + re-derive key via spec mapper
  (the old `SELECT id,data` would have ERRORED on the no-id suppression table). Regression gate GREEN.

### [DONE] retry_queue → DUAL ⭐ shadow_diff==0 (2026-06-09 S3) [INCLUDES callbacks: reason=='callback']
- .env backup `.env.P1bak.*`. STORE_MODES += `retry_queue:dual`. Restart; both svcs active.
- backfill retry_queue --commit → json=0 pg=0 (empty store). shadow_diff retry_queue → 0.
- ⭐ RECONCILE FIRE-PROOF (synthetic, separate process via the LIVE `store._pg_reconcile_leads`):
  upsert one callback record (reason=='callback') → pg=1; empty snapshot → dual prune → pg=0;
  shadow_diff retry_queue → 0. retry mapper (id-PK) + upsert + dual empty-prune all fire. Left PG clean.
- This is the **callbacks** flip too (no separate store/table — §3.3). `/callbacks` endpoint (reads
  retry_queue, filters reason=='callback') → 200. Regression gate GREEN; zero 5xx.

### [DONE] webhooks → DUAL ⭐ shadow_diff==0 (2026-06-09 S3) [strongest proof: live app→worker path]
- .env backup `.env.P1bak.*`. STORE_MODES += `webhooks:dual`. Restart; both svcs active.
- backfill webhooks --commit → json=0 pg=0 (empty store). shadow_diff webhooks → 0.
- ⭐ LIVE FIRE-PROOF through the FULL running app + coalescing worker (webhooks has clean REST add/del):
  POST /webhooks (real url+secret, id 53e24d5d30) → worker mirrored (json=1 pg=1, diff 0); DELETE
  /webhooks/{id} → worker auto-pruned PG (json=0 pg=0, diff 0). This is the actual live B1 worker path,
  not a synthetic reconcile — the strongest convergence proof of the batch.

## ⭐ BATCH COMPLETE — STEADY STATE (end S3, 2026-06-09)
- STORE_MODES = `leads:dual,calls:dual,suppression:dual,retry_queue:dual,webhooks:dual`.
- 5 stores at DUAL, ALL shadow_diff==0: leads(5), calls(78), suppression(0), retry_queue(0), webhooks(0).
  PG mirrors JSON exactly; JSON remains authoritative (rollback = drop store from STORE_MODES + restart).
- callbacks = COVERED (inside retry_queue). campaigns = DEFERRED (per-id files, json-only §3.2 — own unit).
- All max_safe=dual (calls/suppression/retry_queue/webhooks NEVER pg); leads max_safe=pg but gated→dual.
- FINAL GATE GREEN: legacy X-Auth 200 on campaigns/leads/stats/billing-overview/me/callbacks/suppression/
  webhooks; JWT /auth/login 401 (clean reject, not 5xx); both svcs active; zero 5xx in window.
- ⭐ /run DISPATCH GATE (the named gate item, no-paid-call): added throwaway +910000000066 to suppression,
  then POST /run campaign=c17e55e9f3 leads=+910000000066 → HTTP 200 `{"job_id":"b8d139d878","count":1,
  "suppressed_count":1}`. The ONLY input number was suppressed → dial loop dialed NOBODY (no call log,
  no paid call), AND suppressed_count=1 proves /run reads suppression-in-DUAL correctly (JSON-authoritative
  via _read_raw). Cleaned up the suppression entry → auto-pruned to shadow_diff==0.
- BONUS live proof: that /run created a real call record → the calls DUAL mirror auto-mirrored it through
  the actual app+coalescing-worker (calls went json=78→79, pg=78→79) and STAYED shadow_diff==0. Live
  high-frequency calls mirror under a real /run is proven, not just backfill-seeded.
- ⚠ ORCHESTRATOR NOTE (non-blocking, for U10): calls is the only high-write store flipped; under live
  campaign load every call-state _write enqueues a full-snapshot reconcile (≤2000-row INSERT loop + 2000-
  elem delete). Coalescing keeps it off the request path + converges at quiescence, but it IS real write-
  amplification — the U10 per-table autovacuum tuning is meant to absorb it. Can't load-test without paid calls.
- DEPLOYED ARTIFACTS (box md5 == local): store.py e2a24fc9 (generalized + B2-dual-prune fix),
  backfill.py a500e583, shadow_diff.py 6e2d6729. db/models.py UNCHANGED 0f092a64 (all 4 tables + RLS
  pre-existed from U2 — no Alembic this batch). caller.py UNTOUCHED 32c447d6.
- ROLLBACK: restore any `.env.P1bak.*` (latest pre-batch was .env.P1bak.1781017247-era) + restart caller.
  Code is import-guarded; reverting STORE_MODES to `leads:dual` makes the 4 new stores inert json again.
- NEXT UNIT (deferred, do NOT over-reach this batch): campaigns per-id-file mirror (own mechanism),
  billing/ledger/usage_events/cost_ledger/events/wa_log dual flips, orgs/users/memberships backfill,
  leads→pg cutover (+ per-request tenant contextvar), /admin/store-status+/admin/shadow-diff (U8),
  PgBouncer+autovacuum (U10), caller.py→APIRouter modularization.

## SESSION 4 (2026-06-09) — PART A: BILLING/USAGE STORES json→dual + PART B: campaigns (DB-ARCHITECT)
Scope: bring the REMAINING data stores onto PG. (A) billing/ledger/usage_events/cost_ledger/wa_log dual
flips the proven way; (B) campaigns per-id mirror (deferred special case). RECONCILE at start: box==local
md5 store/backfill/shadow_diff/models/caller (e2a24fc9/a500e583/6e2d6729/0f092a64/32c447d6, no drift).
STORE_MODES=leads/calls/suppression/retry_queue/webhooks:dual. Both svcs active. PG had 5 tables for
Part A pre-existing (billing/ledger/usage_events/cost_ledger/wa_log all relforcerowsecurity=t from U2 — no Alembic).

### STORE STRUCTURE TRIAGE (the load-bearing distinction — verified on box)
- **billing.json** = a DICT keyed by org_id->record (NOT a list), whole-file _write (caller 1359/1412/2847).
  PK=org_id. Needs a DICT-AWARE mapper (`_billing_rows` iterates .items()) + shadow_diff dict-store path
  (reads `org_id,data`, wraps `{org_id:data}` to re-derive key). Plain isinstance(list) guard returns []
  on a dict → would wipe the mirror via empty-prune. New `dict_store` flag on StoreSpec marks it.
- **usage_events/cost_ledger/wa_log** = flat lists with NO natural id. Whole-file _write (1443/1504, 3223,
  1036/1050). PK = DETERMINISTIC content-hash `sha256(json.dumps(rec,sort_keys,ensure_ascii=False))`
  computed INSIDE the mapper (`_content_id`), so backfill + live mirror + shadow_diff's per-row
  `to_rows([data])` ALL derive the identical id → bijection. ⚠ PRE-FLIP COLLISION CHECK (the gate-killer):
  on the live box distinct sha256 == total count for all three (usage 171/171, cost 246/246, wa_log 3/3)
  → plain content-hash is SAFE now. These are NOT append-only (usage caps 50k, wa_log caps 2k, cost_ledger
  fully REBUILT each write) → the whole-file UPSERT+delete-by-omission reconcile is correct (an append-only
  mirror would retain evicted/stale rows → drift). All 5 Part-A stores are dual-only (max_safe=dual).
- **ledger/** = PER-TENANT files `var/ledger/<tid>.json` (caller 1407). NOT whole-file, NOT one `.name`.
  Records have NO tenant_id inside (only the filename does) + each _write is a SINGLE-tenant snapshot →
  admin-wide delete-by-omission would WIPE other tenants. = own scoped-reconcile unit (see PART B notes).

### [DONE] billing → DUAL ⭐ shadow_diff==0 (2026-06-09 S4) [dict-store, org_id PK]
- store.py: added `_content_id` + `_billing_rows`(dict-aware)/`_wa_log_rows`/`_usage_events_rows`/
  `_cost_ledger_rows` mappers + `_orgid_key`; StoreSpec gained `dict_store` flag; registered 4 Part-A
  specs (billing dict_store=True). backfill.py + shadow_diff.py: `_load_json_store` loads list OR dict
  (no list-coercion); shadow_diff PG side branches on `dict_store` to re-derive billing's org_id key.
  Deployed INERT first (box md5 store=45ffdd25 backfill=527d15f5 shadow_diff=5458f7ba, local==box);
  backups *.P1bak.partA.1781018917. Restart → `[db.engine] Postgres available`. REFACTOR REGRESSION:
  existing 5 dual stores STILL shadow_diff==0 (leads5/calls79/supp0/retry0/webhooks0) → generalization
  safe. Local mapper/SQL/re-derivation unit-tested (content-hash deterministic across re-derive).
- .env backup `.env.P1bak.billing.*`. STORE_MODES += `billing:dual`. Restart; both svcs active.
- `backfill.py billing --commit` → `BACKFILL billing: json=3 pg=3 upserted=3`. ⭐ `shadow_diff billing` →
  `json=3 pg=3 only_json=0 only_pg=0 field_drift=0 => shadow_diff=0` (exit 0). dict-store key derivation
  (3 org_ids: admin/21d0a13603da/ae1ba3017296) verified both JSON + PG side.
- Regression gate GREEN: legacy X-Auth 200 on /campaigns /leads /billing/overview /me; /auth/login 401
  (clean reject); both svcs active; zero 5xx/traceback in window.

### [DONE] wa_log → DUAL ⭐ shadow_diff==0 (2026-06-09 S4) [content-hash PK]
- .env backup `.env.P1bak.walog.*`. STORE_MODES += `wa_log:dual`. Restart; both svcs active.
- `backfill wa_log --commit` → json=3 pg=3 upserted=3. ⭐ `shadow_diff wa_log` → shadow_diff=0 (exit 0).
  Deterministic content-hash id (sha256 canonical) derived identically backfill↔shadow_diff. Gate GREEN.

### [DONE] usage_events → DUAL ⭐ shadow_diff==0 (2026-06-09 S4) [content-hash PK, 171 rows]
- .env backup `.env.P1bak.usage.*`. STORE_MODES += `usage_events:dual`. Restart; both svcs active.
- `backfill usage_events --commit` → json=171 pg=171 upserted=171. ⭐ `shadow_diff usage_events` →
  shadow_diff=0 (exit 0). 171 content-hash ids all distinct (verified pre-flip) → bijection holds. Gate GREEN.

### [DONE] cost_ledger → DUAL ⭐ shadow_diff==0 (2026-06-09 S4) [content-hash PK, 246 rows]
- .env backup `.env.P1bak.cost.*`. STORE_MODES += `cost_ledger:dual`. Restart; both svcs active.
- `backfill cost_ledger --commit` → json=246 pg=246 upserted=246. ⭐ `shadow_diff cost_ledger` →
  shadow_diff=0 (exit 0). cost_ledger is fully REBUILT each _write (whole-file snapshot) → the
  UPSERT+delete-by-omission reconcile keeps PG==JSON even as old rows drop out. Gate GREEN.

### [DONE] BILLING LIVE-MIRROR FIRE-PROOF (2026-06-09 S4) — the dict-snapshot path backfill can't prove
- ⚠ backfill writes PG DIRECTLY (bypasses the live write()→_enqueue_mirror→worker→_pg_reconcile_leads
  path). For wa_log/usage/cost that path is identical to the 5 proven stores (only the mapper differs,
  and the mapper is backfill-proven). BUT billing's snapshot is a DICT — a payload shape NO prior store
  pushed through the live reconcile, and no real billing write had fired (all 3 tenants already had
  records → _billing_for never wrote; /billing/overview is read-only). So the dict path was unexercised.
- SYNTHETIC FIRE-PROOF (side process, LIVE `store._pg_reconcile_leads`, touches PG only, billing.json
  untouched): reconcile the real 3-key dict + a throwaway org → PG=4 (dict-iterating UPSERT fires); then
  reconcile the real 3-key dict → org_id delete-by-omission PRUNES the throwaway → PG=3 (no zzz). ⭐
  shadow_diff billing back to 0, billing.json org_ids unchanged. PROVES dict-snapshot UPSERT + org_id
  delete-by-omission through the actual mirror code, not just a direct backfill seed.

## ⭐ PART A COMPLETE — STEADY STATE (S4, 2026-06-09)  [4 of 5 named stores; ledger deferred]
- STORE_MODES = `leads:dual,calls:dual,suppression:dual,retry_queue:dual,webhooks:dual,billing:dual,
  wa_log:dual,usage_events:dual,cost_ledger:dual` → **9 stores at DUAL, ALL shadow_diff==0**:
  leads5, calls79, suppression0, retry_queue0, webhooks0, billing3, wa_log3, usage_events171, cost_ledger246.
- All 9 are dual-CAPPED (max_safe=dual except leads=pg-but-gated→dual). PG mirrors JSON exactly; JSON
  authoritative. Rollback = drop a store from STORE_MODES + restart (→ inert json). Backups: .env.P1bak.{billing,walog,usage,cost}.*
- DEPLOYED ARTIFACTS (box md5 == local): store.py 45ffdd25 (+ Part-A mappers + dict_store flag),
  backfill.py 527d15f5 (_load_json_store list|dict), shadow_diff.py 5458f7ba (dict-store key re-derive).
  db/models.py UNCHANGED 0f092a64 (all 5 Part-A tables + RLS pre-existed from U2 — NO Alembic). caller.py
  UNTOUCHED 32c447d6 (Part A is store.py + scripts + .env ONLY — the env-only safety net held all batch).
- Code backups: store/backfill/shadow_diff `*.P1bak.partA.1781018917`.

## ⛔ DEFERRED THIS BATCH (precise "what's needed" — do NOT half-do near the call limit)

### ledger (per-tenant files var/ledger/<tid>.json) — DEFERRED, store.py-only but NOT trivial
WHY deferred: it does NOT fit the whole-file-snapshot mirror keyed by one file `.name`, and forcing it
in risks the 9 green stores (shared B1 worker / shared `_pg_reconcile_leads`). Specifically:
  1. **Registry match**: the seam keys by `Path(path).name` = `<tid>.json` (dynamic), so `_SPECS.get(name)`
     never matches → ledger never enters the seam today. Need parent-dir match (e.g. if `path.parent.name
     == 'ledger'` → ledger spec) in `_name`/`mode_of`/`read`/`write` — a change to the seam HOT PATH that
     every _read/_write hits → must re-prove byte-identical pass-through for the 9 stores.
  2. **B1 coalescing collision**: the worker is ONE depth-1 queue per SPEC, but ledger is one spec over N
     tenant files. Writing admin.json then ae1….json would COALESCE across tenants → DROP a tenant's
     snapshot (silent mirror loss). Need either a per-(spec,tenant_stem) queue/worker, OR carry the stem
     in the enqueued payload and key the worker map by stem.
  3. **org_id source**: ledger records have NO tenant_id inside (only the filename does). `to_rows(data)`
     cannot produce org_id → must thread the file stem → org_id into the mapper + reconcile.
  4. **Tenant-SCOPED delete-by-omission**: each _write is a SINGLE-tenant snapshot. Admin-wide
     `DELETE … id NOT IN(snapshot)` would WIPE every OTHER tenant's ledger rows. Must be
     `DELETE FROM ledger WHERE org_id=:stem AND id NOT IN (snapshot ids)` (+ empty-snapshot: prune only
     that tenant's rows, never all).
  5. **backfill**: iterate `var/ledger/*.json`, org_id = file stem, UPSERT by id (records have id).
     shadow_diff: union over all ledger files vs PG (admin GUC), id-keyed.
RISK: medium; isolated to ledger IF the seam parent-dir match + per-tenant worker are added without
touching the 9-store path semantics. = its own unit. ledger.json records on box: id-PK, 3 tenant files
(admin 56, 21d0a13603da, ae1ba3017296), all have `id`.

### campaigns (per-id files var/campaigns/<id>.json) — DEFERRED, needs the FIRST caller.py edit in P1
WHY deferred: campaigns BYPASS `_write` entirely — written via direct `.write_text` at caller.py:824
(create/save) and :2069 (edit), deleted via `unlink` at caller.py:2088. The store seam (which only wraps
_read/_write/_awrite) STRUCTURALLY cannot see them. §3.2 also mandates campaigns json-only in P1 (agent
reads campaigns/<id>.json). To dual-mirror them needs a per-id mirror hook (NOT the whole-file snapshot):
  - **Write hook** at 824 + 2069: after the `.write_text`, call a new `store.mirror_campaign_upsert(rec)`
    (id-PK UPSERT of one campaign row; org_id = rec['tenant_id'] — VERIFIED top-level on disk: campaign
    file keys = company/created_at/fields/id/name/product/status/system_prompt/tenant_id). Best-effort,
    off-path, swallow failures (same B1 worker discipline, but per-id, NO delete-by-omission).
  - **Delete hook** at 2088: after `unlink`, call `store.mirror_campaign_delete(cid)` (DELETE one row).
  - **Backfill**: iterate `var/campaigns/*.json` (skip *.bak/*.P2bak), UPSERT by id. shadow_diff: glob
    campaign files vs `campaigns` PG table, id-keyed (adapt — not a single JSON file). 9 real campaigns
    on box (+ some .bak/.winrestore.bak to skip).
  - **MODE**: campaigns dual-only, NEVER pg (agent reads the file; freezing it would break the agent).
COST/RISK: this is the FIRST caller.py edit in P1 → breaks the env-only / caller-md5-unchanged safety
net every batch so far has ridden on. Requires: caller.py md5 RE-BASELINE + full caller regression (a
crash mid-edit near the call limit leaves caller.py half-broken on the LIVE earner). The campaign
create/edit/delete paths are live-revenue-critical — must NOT break them. = its own carefully-scoped
unit with a clean checkpoint, not an end-of-batch add-on. DOCUMENTED, not attempted (task explicitly
blesses "leave campaigns=json + document precisely what's needed" if risky/large).

## SESSION 5 (2026-06-09) — SAFE-REMAINDER BATCH: identity backfill + /admin/store-status + ledger
Scope (orchestrator): 3 SAFE items, ONE at a time, build_log after each. NO caller.py modularization.
RECONCILE at start: box==local md5 store=45ffdd25 backfill=527d15f5 shadow_diff=5458f7ba caller=32c447d6
models=0f092a64 engine=7c4538b1 (ZERO drift). STORE_MODES = 9 stores dual (unchanged). Both svcs active.
ADVISOR REORDERED to B→C→A (bank the safe/certain wins before the risky shared-seam mutation A=ledger).
tenants.json = flat LIST of 4 (admin/21d0a13603da/ae1ba3017296/013a13841fd5), each tenant_id/name/email/
is_admin/role/pass_hash/salt, all 4 emails distinct (no lower(email) uq collision). orgs/users/memberships
tables EMPTY (0 rows) at start, columns == §3.1.

### [DONE] ITEM B — orgs/users/memberships BACKFILL ⭐ parity shadow_diff==0 (2026-06-09 S5)
- These are NOT a file→table StoreSpec mirror — they're a 1→3 FAN-OUT derived from tenants.json (§3.1/§5
  ADDITIVE mirror): each tenant → 1 org (id==tenant_id) + 1 user (id==org_id==tenant_id, role/is_admin/
  email/pass_hash/salt carried verbatim) + 1 membership (org_id==user_id==tenant_id). So a DEDICATED path,
  NOT the spec machinery. Added `backfill_identity()` + `_load_tenants()` to backfill.py (3 idempotent
  UPSERTs by PK in order orgs→users(FK org_id)→memberships(FK both), admin GUC); `python backfill.py
  identity [--commit]`. Added `diff_identity()` to shadow_diff.py (custom parity: count tenants==orgs==
  users==memberships + every tid present as org.id/user.id/(org,user) membership + user.org_id==tenant_id
  + no orphan/extra rows); `python shadow_diff.py identity`.
- Deployed INERT (nothing in the service imports backfill/shadow_diff). Box backups *.P1bak.identity.<ts>.
  md5 local==box: backfill=e4397776 shadow_diff=efcf567e. caller.py + store.py UNTOUCHED (32c447d6/45ffdd25).
- `backfill identity --commit` → `tenants=4 orgs=4 users=4 memberships=4 upserted 4/4/4`. ⭐ `shadow_diff
  identity` → `missing_org=0 missing_user=0 missing_mem=0 bad_user_org=0 extra_org=0 extra_user=0 =>
  shadow_diff=0` EXIT 0. IDEMPOTENT: re-ran --commit → still 4/4/4, parity 0 (no dups). Users verified:
  admin(role=admin,is_admin=t), 3× manager, all id==org_id==tenant_id, all pass_hash mirrored.
- LEGACY AUTH UNCHANGED (the §5 invariant): tenants.json untouched, auth still reads it. /auth/login bad
  creds → clean 401 (not 5xx). Regression gate GREEN: legacy X-Auth 200 on campaigns/leads/stats/billing-
  overview/me; both svcs active; existing dual stores UNAFFECTED (leads5/calls79 still shadow_diff==0).
- ROLLBACK (if ever needed): `TRUNCATE memberships,users,orgs` via admin GUC (nothing reads them) +
  restore backfill/shadow_diff backups. Zero live impact — these tables are write-only mirrors in P1.

### [DONE] ITEM C — GET /admin/store-status (U8) ⭐ FIRST caller.py edit in P1 (2026-06-09 S5)
- ⚠ This ENDED the env-only / caller-md5-unchanged streak every batch rode on — DELIBERATELY, additive
  route ONLY (new `@app.get("/admin/store-status")` after billing_sync ~2813; ZERO change to any existing
  route or seam logic). caller.py md5 32c447d6 → **fc9abbbd** (re-baselined; box==local). Backup on box
  `caller.py.P1bak.storestatus.1781020318` (= the old 32c447d6).
- Endpoint (admin-only, RBAC `manage_tenants`): returns `store.status()` (per-store mode/max_safe/
  pg_writes_ok/fail/last_error/worker) ENRICHED with LIVE counts computed IN the handler — `json_count`
  = len(authoritative JSON file via _read_raw), `pg_count` = admin-GUC `SELECT count(*)`. (last_shadow_diff
  is ALWAYS None — shadow_diff.py runs out-of-process, can't write the live spec object; the live
  json_count==pg_count IS the meaningful convergence/drift indicator instead.) Plus an `identity` block
  (orgs/users/memberships counts) and `db` status + `at`. Best-effort per store (errors → that store's
  `error` field, never 500s).
- SAFETY DISCIPLINE (the crash lesson): scp deploy → **INSTANTIATE smoke test in venv BEFORE restart**
  (`importlib exec_module` of caller.py → IMPORT_OK, app present, /admin/store-status route registered,
  _store wired) → ONLY THEN `systemctl restart famit-caller`. Service came up clean (`[db.engine] Postgres
  available`), both svcs active.
- VERIFIED LIVE: admin X-Auth → 200, all 9 stores json==pg (leads5/5 calls79/79 supp0/0 retry0/0 webhooks
  0/0 billing3/3 wa_log3/3 usage171/171 cost246/246), identity orgs/users/memberships 4/4/4. No-auth →
  401. The 403 (authed non-admin) leg: the gate is BYTE-IDENTICAL to the live billing_sync preamble; the
  predicate proven directly via the live `can()` — manager→False, admin→True for `manage_tenants`. (A real
  vendor-JWT HTTP 403 couldn't be minted in-shell: `auth._SECRET` comes from the Doppler overlay (N2), not
  .env, so standalone _make_access yields no token — dead end, not needed; predicate proof is decisive.)
- REGRESSION GATE GREEN: legacy X-Auth 200 on campaigns/leads/stats/billing-overview/me; /auth/login bad
  creds → clean 401; both svcs active; zero 5xx in window. Existing dual stores unaffected.
- ROLLBACK: `cp caller.py.P1bak.storestatus.1781020318 caller.py && systemctl restart famit-caller`
  (back to 32c447d6, all-9-stores-dual still works — STORE_MODES untouched). The route is purely additive.

### [DONE] ITEM A — ledger PER-TENANT scoped mirror → DUAL ⭐ shadow_diff==0 (2026-06-09 S5) [the risky one]
- The deferred-since-S4 hard case: ledger is `var/ledger/<stem>.json`, ONE file PER TENANT, org_id==stem
  (records carry NO tenant_id), reconciled via the SHARED seam hot path + shared B1 worker. All 4 build_log
  risks addressed WITHOUT touching the 9-store path:
  1. **Parent-dir registry match (new `_resolve(path)->(spec,stem)`)**: tries `_SPECS.get(Path.name)` FIRST
     (9 stores hit the IDENTICAL fast path, return (spec,"") — NEVER reach ledger code); only on a name MISS
     tests `path.parent.name=='ledger'` → (_LEDGER_SPEC, stem). mode_of/read/write/awrite all route via it.
  2. **Per-STEM queue/worker** (new `multi_file` flag + `_queues`/`_workers` dicts on StoreSpec): ledger
     enqueues to `spec._queues[stem]` with a worker per stem, so tenant A's snapshot can NEVER coalesce
     with tenant B's in one depth-1 queue (the silent-mirror-loss the build_log flagged). Single-file
     stores use spec._queue/_worker unchanged (stem="" everywhere → byte-equivalent path).
  3. **org_id from STEM, column ONLY** (`_ledger_rows(data, stem)`): org_id promoted into the column; the
     `data` jsonb stays the VERBATIM record (no org_id injected) → backfill + live mirror + shadow_diff all
     derive `data` identically → true 0.
  4. **Tenant-SCOPED deletes (BOTH branches)**: delete-by-omission `WHERE org_id=:stem AND id NOT IN(...)`
     (new `org_scoped` arg on `_delete_by_omission_sql`); the dual EMPTY branch is `DELETE FROM ledger
     WHERE org_id=:stem` (NOT bare `DELETE FROM ledger` — that would wipe every other tenant). status()
     + /admin/store-status extended to surface ledger (multi_file worker-liveness = any stem worker live).
- KEYSTONE STATIC PROOF (no paid call can trigger a live ledger write — it fires on call-completion =
  billable): grepped caller.py — ledger written ONLY at :1407 `_write(_ledger_path(tid), ledger)` where
  `ledger=_read_ledger(tid)` (whole tenant list) `.insert(0,entry); del ledger[5000:]` → through the
  `_write` SHIM, whole-tenant-list RMW, NOT .write_text/unlink/partial-list. Read via `_read` (:1373).
  Single writer + single reader, both via the shim. So the live dual path is structurally proven.
- DEPLOY DISCIPLINE: store/backfill/shadow_diff deployed INERT (ledger NOT in STORE_MODES) → INSTANTIATE
  smoke (caller imports new store.py clean, _resolve routes leads→(leads,""), ledger/admin→(ledger,"admin"),
  campaigns/abc→None) → restart → ⭐ REFACTOR REGRESSION: ALL 9 stores STILL shadow_diff==0 (the check the
  HTTP gate can't catch — proves the seam mutation is byte-equivalent for the 9). Box md5 store=77d0fcf0
  backfill=c4c47ede shadow_diff=ed8eda11. Backups *.P1bak.ledger.1781021290.
- Pre-flip global id-distinctness: union 63 rows == 63 distinct (collision-free → id-PK won't merge tenants).
- FLIP: .env STORE_MODES += `ledger:dual` (backup .env.P1bak.ledger.*); restart. `backfill ledger --commit`
  → `files=3 json=63 pg=63 upserted=63`. ⭐ `shadow_diff ledger` → `files=3 json=63 pg=63 only_json=0
  only_pg=0 field_drift=0 => shadow_diff=0` EXIT 0 (admin56 + 21d…1 + ae1…6).
- ⭐ ORG-SCOPE FIRE-PROOF (side-process via LIVE `store._pg_reconcile_leads(_LEDGER_SPEC, snap, stem)`,
  PG-ONLY, throwaway stem "zzztest" — touches no JSON file): real tenants admin56/21d…1/ae1…6 throughout.
  (a) reconcile [X,Y] stem=zzztest → zzztest=2, real UNCHANGED (per-stem UPSERT); (b) reconcile [X] →
  zzztest=1 (Y pruned), real UNCHANGED (org-scoped delete-by-omission does NOT wipe other tenants);
  (c) reconcile [] → zzztest GONE, real UNCHANGED (org-scoped EMPTY branch, NOT bare DELETE). Left PG
  clean; shadow_diff ledger STILL 0 (no residue). This is THE new risk (wiping other tenants) — disproven.
  ⚠ HONEST: the live-APP worker trigger (a real `_write(_ledger_path,...)` → enqueue → per-stem worker)
  is UNPROVEN without a paid call. The proof = the static grep (live path goes through the shim) + the
  org-scoped reconcile SQL fire-proofed here + the per-stem worker being the SAME proven pattern as the 9
  stores, just keyed by stem. /admin/store-status now shows ledger mode=dual json_count=63 pg_count=63.
- caller.py got a SECOND tiny additive edit (store-status ledger count: sum across var/ledger/*.json + add
  "ledger"→"ledger" to _table_for). md5 fc9abbbd→6833803267 (box==local). INSTANTIATE-smoke-tested.
- ⭐ LIVE-WORKER PROOF (advisor-caught gap: the refactor changed _enqueue_mirror(+stem) AND _mirror_worker
  (now (spec,stem,q) params) for ALL 10 stores; shadow_diff==0 with no writes in the window only proved
  STATIC persistence, not that the new worker signature FIRES). Closed with the S3-style webhooks round-trip
  (no paid call): POST /webhooks (form-encoded throwaway) → worker mirrored (json=1 pg=1 diff 0); DELETE
  /webhooks/{id} → worker auto-pruned (json=0 pg=0 diff 0). store-status: webhooks worker=True
  pg_writes_ok=2 pg_writes_fail=0 → the new _enqueue_mirror→_mirror_worker→_pg_reconcile_leads path fires
  end-to-end on a REAL app write→worker cycle. Single-file seam path proven LIVE, not just static.
- LEDGER LIVE-PATH caveat partially CLOSED: the ledger _write @caller.py:1407 is inside `async def
  _charge_call` (1383), `await`ed at :1542 (async handler) → runs WITH a running loop → _enqueue_mirror
  fires the per-stem worker (NOT the no-loop skip). So the live ledger mirror WILL fire; only an actual
  billable call to populate it is unrun (the org-scoped reconcile + per-stem worker are otherwise proven).
- FINAL GATE GREEN: legacy X-Auth 200 on campaigns/leads/stats/billing-overview/me/callbacks; /auth/login
  clean 401; both svcs active; ZERO 5xx/traceback in window; 9 stores + ledger ALL shadow_diff==0.
- ⚠ SCALE NOTE (for U10): multi_file `_queues[stem]`/`_workers[stem]` are created per tenant and the
  `while True` worker never exits → at thousands of tenants this is a slow accrual of idle asyncio tasks.
  Fine at 4 tenants; add idle-worker reaping when tenant count grows (one-line note, not fixed now).
- ROLLBACK: drop `ledger:dual` from STORE_MODES (restore .env.P1bak.ledger.*) + restart → ledger inert
  json (store.py code is import-guarded; the new _resolve/_LEDGER_SPEC are no-ops when mode=json).

## ⭐ S5 BATCH COMPLETE — STEADY STATE (2026-06-09)
- STORE_MODES = `leads,calls,suppression,retry_queue,webhooks,billing,wa_log,usage_events,cost_ledger,
  ledger : dual` → **10 stores at DUAL, ALL shadow_diff==0**: leads5 calls79 suppression0 retry0 webhooks0
  billing3 wa_log3 usage171 cost246 ledger63. All dual-capped (none pg). PG mirrors JSON exactly.
- IDENTITY mirror seeded: orgs/users/memberships = 4/4/4 (parity 0). Legacy auth UNCHANGED.
- NEW admin endpoint: GET /admin/store-status (admin-only) — per-store mode/json_count/pg_count + identity.
- DEPLOYED md5 (box==local): store.py 77d0fcf0, backfill.py c4c47ede, shadow_diff.py ed8eda11,
  caller.py 6833803267 (TWO additive edits this batch: store-status route + ledger-count; env-only streak
  ended at item C, deliberately, additive-only). db/models.py UNCHANGED 0f092a64 (all tables pre-existed).
- NEXT UNITS (deferred, NOT attempted): campaigns per-id mirror (the OTHER FIRST-class caller.py hook unit:
  .write_text/unlink bypass _write — needs write/delete hooks at caller.py:824/2069/2088), events/audit_log
  jsonl backfill, leads→pg cutover (+ per-request tenant contextvar), PgBouncer+autovacuum (U10 RLS+infra),
  caller.py→APIRouter modularization (its own dedicated wave).

## SESSION 6 (2026-06-09/10) — ITEM A: events/audit_log → DUAL + ITEM B: campaigns per-id mirror (DB-ARCHITECT)
Scope (orchestrator): the remaining data stores, ONE at a time. RECONCILE at start: box==local md5 ZERO drift
store=77d0fcf0 backfill=c4c47ede shadow_diff=ed8eda11 caller=6833803267 models=0f092a64 engine=7c4538b1;
STORE_MODES=10-stores-dual; both svcs active; audit_log.jsonl=40 lines; 8 campaign json files.
ADVISOR (start): Item A is NOT backfill-only — "at dual" REQUIRES the live mirror hook (audit.record fires on
every mutating action incl. the Item-B regression gate's own campaign.create/edit → backfill-only would
fake-green then break its own gate). Events bypasses _write (open-"a" append) exactly like campaigns → NOT a
StoreSpec/snapshot store → standalone append path, NOT the coalescing depth-1 worker (replace-on-full = drops
unique append-only events). Hook = audit.record lazy-import store.mirror_event → ZERO caller.py edit for A.

### [DONE] ITEM A — events/audit_log → DUAL ⭐ shadow_diff==0 (2026-06-09 S6) [append-only, content-hash PK]
- store.py (ADDITIVE only — new fns, existing path byte-unchanged): `_event_row`/`_events_rows` mappers
  (PK=_content_id of the PARSED dict, NOT the raw line — audit.record writes json.dumps(ev) WITHOUT
  sort_keys so the raw line isn't canonical; backfill+live-hook+shadow_diff ALL re-derive from the dict →
  bijection). `build_events_insert_sql` = INSERT ... ON CONFLICT (id) DO NOTHING (idempotent, NO update/
  delete/snapshot — §3.6 insert+select only). `mirror_event(ev)` = best-effort live hook: gated on db-up
  AND events∈STORE_MODES (else no-op → keeps the flag contract), runs the blocking INSERT off the loop via
  run_in_executor (NOT the coalescing worker), get_running_loop guard (no loop → skip, backfill heals).
  `_events_mode()` + `_EVENTS_STATE` counters + events block in status(). org_id==event tenant_id; meta
  promoted; full event in data jsonb; `at` left to col DEFAULT now() (shadow_diff compares only data).
- audit.py (the ONLY hooked file — isolated 5KB module, record() already swallows all): after the JSONL
  append, `try: import store; store.mirror_event(ev) except: pass`. ZERO caller.py edit (advisor: isolates
  the whole caller.py blast-radius to Item B). Local==box pre-edit (md5 15f1d4c0).
- backfill.py: `backfill_events` reads var/audit_log.jsonl (+ rotated .1) → store._events_rows → append
  INSERT, counts rowcount (ON CONFLICT DO NOTHING → 0 for dups). shadow_diff.py: `diff_events` JSONL vs PG
  `data`, id re-derived via store._event_row both sides. `events`/`audit`/`audit_log` aliases in both mains.
- PRE-FLIGHT collision check (the S4 gate-killer): 40 lines → 40 distinct content-hashes (collision-free).
- DEPLOY DISCIPLINE: deployed 4 files INERT (events NOT yet in STORE_MODES → mirror_event no-op, new code
  dormant) → INSTANTIATE-smoke (caller exec_module clean, _store wired, mirror_event callable, events_mode=
  json) → restart caller → ⭐ REFACTOR REGRESSION: ALL 10 dual stores + identity STILL shadow_diff==0 (the
  check the HTTP gate can't catch — proves the additive store.py is byte-equivalent for the existing path).
  Box md5==local: store=0f4f6b59 audit=d2420471 backfill=e8d6b30c shadow_diff=588f993f. caller.py UNTOUCHED
  6833803267, models UNCHANGED. Backups *.P1bak.events.1781029239 + .env.P1bak.events.1781029358.
- FLIP: .env STORE_MODES += `events:dual`; restart. `backfill events --commit` → `json=40 pg=40 inserted=40`.
  ⭐ `shadow_diff events` → `json=40 pg=40 only_json=0 only_pg=0 field_drift=0 => shadow_diff=0` EXIT 0.
- ⭐ LIVE-MIRROR PROOF (the advisor's key point — backfill writes PG directly, bypassing audit.record→
  mirror_event): fired 2 audited HTTP actions (POST+DELETE /suppression → audit lines suppression.add/
  suppression.delete) → JSONL grew 40→42 → live hook mirrored both → events json=42 pg=42 shadow_diff STILL
  0. The LIVE uvicorn process's /admin/store-status showed `events: mode=dual pg_writes_ok=2 pg_writes_fail=0`
  — exactly the 2 fired, proving the hook fired end-to-end IN the running app (not the smoke process, which
  has its own module state showing 0). Append-only/immutable → NO prune of test events (unlike snapshot
  stores); shadow_diff stays 0 by PG tracking growth, not deletion.
- FINAL GATE GREEN: legacy X-Auth 200 on campaigns/leads/stats/billing-overview/me/callbacks/suppression;
  /auth/login bad-creds clean 401; both svcs active; ZERO 5xx in window. /run dispatched (job fefe8318e2,
  count=1) — see ⚠ note. After the /run, events grew 42→45 (3 more audit lines) all live-mirrored,
  shadow_diff STILL 0 → live mirror proven under real app activity too.
- ⚠ /run GATE HONESTY: this batch's /run used +910000000066 but suppressed_count=0 (the suppression POST
  hadn't propagated to the dial loop's read in time — unlike S3 which PRE-SEEDED the number). So /run DID
  dispatch a SIP attempt to the invalid number → call 7dbe8a2b07 status=calling→done outcome=voicemail/
  no_answer answered=False duration_s=24. NO human reached, NO billable conversation (invalid/unallocated
  number → carrier no-answer). LESSON (brain): to prove /run-dispatches-nobody with no paid call, PRE-SEED
  the number into suppression and CONFIRM suppressed_count>0 BEFORE trusting it; suppressed_count=0 means it
  actually dialed. Use the side-process reconcile for any further mirror proof, NOT another /run.
- ⚠ CALLS DRIFT (benign, NOT the events work, DISPROVEN as a bug): the test call state-transitioned calls →
  shadow_diff calls=1 (field_drift on 7dbe8a2b07: PG had `_wh_completed:true`, JSON didn't). NOT R8 transient
  lag (persisted at quiescence). ROOT: the UPSERT does data=EXCLUDED.data, so PG retained an intermediate
  webhook-completion snapshot a later JSON RMW dropped (pre-existing caller.py in-RAM-CALLS non-monotonic
  write). PROVEN benign via side-process `store._pg_reconcile_leads(calls_spec, current calls.json)` (PG-only,
  no file touch) → calls shadow_diff back to 0. The next live calls _write self-heals it. Events untouched by
  this (separate table; store.py edits purely additive; all 10 stores were 0 pre-test-call).
- ROLLBACK: drop `events:dual` from STORE_MODES (restore .env.P1bak.events.*) + restart → mirror_event no-op
  (gated on events∈STORE_MODES), events code dormant, JSONL authoritative + audited as before. backfill/
  shadow_diff inert. audit.py hook is import-guarded + swallows → harmless even with events back to json.

### [DONE] ITEM B — campaigns PER-ID mirror → DUAL ⭐ shadow_diff==0 (2026-06-09 S6) [the risky FIRST FUNCTIONAL caller.py edit in P1]
- The deferred-since-S4 hard case: campaigns are written PER-ID as var/campaigns/<id>.json via DIRECT
  .write_text (create @save_campaign:824, edit @update_campaign:2069) + .unlink (delete @delete_campaign:2090)
  — BYPASSING _write entirely, so the store seam STRUCTURALLY can't see them (§3.2 also mandates campaigns
  json-authoritative in P1: the live voice agent reads campaigns/<id>.json, so campaigns is dual-only, NEVER
  pg). RE-GREPPED the sites on the LIVE caller.py (advisor flag — md5 shifted S5): the S5 store-status route
  landed at ~2831 AFTER these, so 824/2069/2090 were UNCHANGED — but verified, not trusted. 8 real campaign
  files (the *.json glob excludes *.json.P2bak/*.json.winrestore.bak by extension; backfill+diff ALSO skip
  any name containing .bak/winrestore). All 8 have id + tenant_id top-level.
- MECHANISM (per-id UPSERT/DELETE, NOT the snapshot seam, NOT the coalescing worker): store.py ADDITIVE only —
  `_campaign_row` mapper (org_id==rec['tenant_id']; fields+full record into jsonb; created_at/voice_id to
  defaults), `build_campaign_upsert_sql` (INSERT ... ON CONFLICT (id) DO UPDATE — NO delete-by-omission:
  per-id writes have no whole-file snapshot to reconcile), `mirror_campaign_upsert(rec)` +
  `mirror_campaign_delete(cid)` (best-effort, gated on db-up AND campaigns∈STORE_MODES, off-loop
  run_in_executor, get_running_loop guard, swallow-all — MUST NOT break the live earner), `_campaigns_mode()`
  (capped dual, never pg) + `_CAMPAIGN_STATE` counters + campaigns block in status().
- caller.py — THE FIRST FUNCTIONAL P1 EDIT (3 minimal additive hooks, each `try: if _store is not None:
  _store.mirror_campaign_*(...) except: pass` immediately AFTER the existing .write_text/.unlink, NEVER
  replacing the JSON write): @824 (create, mirrors `rec`), @2070 (edit, mirrors `d`), @2090 (delete, mirrors
  `cid`). md5 6833803267 → **50afb2e1** (re-baselined; box==local). _migrate_to_admin's import-time campaign
  rewrite (524-528) deliberately NOT hooked (pre-loop → no-loop skip anyway; backfill seeds all 8 regardless).
- backfill.py: `backfill_campaigns` globs var/campaigns/*.json (skip .bak), per-id UPSERT via the SAME mapper+
  SQL as the live hook. shadow_diff.py: `diff_campaigns` dir-files vs PG `data` (id-keyed; only_pg flags a
  stale row a missed delete would leave). `campaigns` alias in both mains.
- DEPLOY DISCIPLINE (the crash lesson, sharpened for a caller.py edit): deployed 4 files INERT (campaigns NOT
  yet in STORE_MODES → all 3 hooks no-op, dormant) → INSTANTIATE-smoke (caller exec_module CLEAN, _store
  wired, /campaigns + /campaigns/{cid} + /admin/store-status routes present, mirror fns callable,
  campaigns_mode=json) → ONLY THEN restart → ⭐ REFACTOR REGRESSION (campaigns still json): leads/calls/supp/
  billing/events/ledger/identity ALL STILL shadow_diff==0 (the caller.py edit is byte-equivalent for the
  existing path). Box md5==local store=2b2b0774 caller=50afb2e1 backfill=cfd53d38 shadow_diff=679afb08.
  Backups caller.py.P1bak.campaigns.1781030158 + {store,backfill,shadow_diff}.P1bak.campaigns.1781030208.
- ⭐ HARD CAMPAIGN-LIFECYCLE GATE (the live earner — task-mandated): in json mode FIRST, full CREATE
  (id=4daeb6ed97) → EDIT (name→WidgetX-EDITED, persisted) → DELETE (deleted) all 200 → hooks are harmless
  no-ops while json. THEN flipped campaigns:dual (.env backup .env.P1bak.campaigns.1781030294), restart.
- FLIP: `backfill campaigns --commit` → `json=8 pg=8 upserted=8`. ⭐ `shadow_diff campaigns` →
  `json=8 pg=8 only_json=0 only_pg=0 field_drift=0 => shadow_diff=0` EXIT 0.
- ⭐ LIVE-MIRROR PROOF (all 3 hooks end-to-end through the RUNNING app — backfill bypasses them): CREATE
  +910… campaign 2aa6fc9323 → PG 8→9, row present (org_id=admin name=product=LiveWidget) [upsert hook fired];
  EDIT product→LiveWidget-EDITED → PG row refreshed, count stayed 9 [ON CONFLICT DO UPDATE fired]; DELETE →
  PG 9→8, row gone [delete hook fired]; ⭐ shadow_diff campaigns BACK TO 0 (no residue). The LIVE uvicorn
  /admin/store-status showed `campaigns: mode=dual pg_writes_ok=3 pg_writes_fail=0` (exactly create+edit+
  delete) AND `events: pg_writes_ok=3` (each campaign action also wrote an audit line → the events mirror
  fired too — the cross-feature interaction the advisor predicted, working, 0 fail). Strongest proof: full
  create→edit→delete round-trip with self-healing convergence, NOT a backfill seed.
- FINAL GATE GREEN: legacy X-Auth 200 on campaigns/leads/stats/billing-overview/me/callbacks; /auth/login
  bad-creds clean 401; both svcs active; ZERO 5xx in window; ⭐ FULL SWEEP: ALL 12 stores + identity
  shadow_diff==0 (leads5 calls79 supp0 retry0 webhooks0 billing3 wa_log3 usage171 cost246 ledger63 events45
  campaigns8). Campaign create/edit/delete (the live revenue path) PROVEN intact + mirroring.
- ⚠ store-status json_count/pg_count are None for events+campaigns (cosmetic): the S5 count-enrichment in
  the route only knows single-JSON-file stores via _table_for; events(jsonl) + campaigns(dir) aren't file-
  keyed there. NON-BLOCKING — shadow_diff (==0) + the live pg_writes_ok counters are the real indicators.
  (A 1-line route fix to count var/campaigns/*.json + audit_log.jsonl lines is a trivial future polish.)
- ROLLBACK: drop `campaigns:dual` from STORE_MODES (restore .env.P1bak.campaigns.*) + restart → all 3 hooks
  no-op (gated on campaigns∈STORE_MODES), campaigns code dormant, files authoritative + agent-read as before.
  The caller.py hooks are import-guarded (`_store is not None`) + swallow-all → harmless even back at json.
  Deeper code rollback: restore caller.py.P1bak.campaigns.1781030158 (= 6833803267) + restart.

## ⭐ S6 BATCH COMPLETE — STEADY STATE (2026-06-09/10)
- STORE_MODES = `leads,calls,suppression,retry_queue,webhooks,billing,wa_log,usage_events,cost_ledger,
  ledger,events,campaigns : dual` → **12 stores at DUAL, ALL shadow_diff==0** (10 prior + events45 +
  campaigns8). + identity 4/4/4 (parity 0). PG mirrors JSON exactly; JSON authoritative; all dual-capped
  (events/campaigns NEVER pg by design — append-only / agent-read).
- TWO NEW STORE SHAPES proven this batch, BOTH bypassing the _write snapshot seam (hence dedicated paths,
  NOT StoreSpec): events = append-only JSONL via the audit.record CHOKEPOINT hook (ZERO caller.py edit);
  campaigns = per-id files via 3 functional caller.py hooks (the FIRST functional P1 caller.py edit).
- DEPLOYED md5 (box==local): store.py 2b2b0774, audit.py d2420471, backfill.py cfd53d38, shadow_diff.py
  679afb08, caller.py 50afb2e1 (campaign hooks; 6833803267→50afb2e1). db/models.py UNCHANGED 0f092a64
  (events+campaigns tables + RLS pre-existed from U2 — NO Alembic this batch).

### ⚠ SCHEMA COVERAGE — HONEST ACCOUNTING (advisor-caught overclaim corrected)
§3 defines 17 tables. NOW MIRRORED (15): orgs/users/memberships (identity fan-out) + campaigns/leads/calls
+ suppression/retry_queue/webhooks + wa_log + billing/ledger/usage_events/cost_ledger + events.
NOT YET MIRRORED (2) — the seam is NOT "every store"; precisely:
  • **webhook_log (var/webhook_log.json) — a GENUINE MISS, the immediate next item (NOT a deferral
    decision).** Distinct store (`WEBHOOK_LOG_FILE`=var/webhook_log.json @caller.py:120; webhook DELIVERY
    log; read/written via `_read`/`_write` @caller.py:1336 — a WHOLE-FILE list, so unlike events/campaigns
    it FITS the StoreSpec snapshot seam DIRECTLY). Same content-hash/append shape as wa_log (flipped S4).
    File doesn't exist yet on box (no webhook has fired) → PG webhook_log table = 0 rows; NOT in _SPECS;
    NOT in STORE_MODES. TO DO (trivial, ~the wa_log recipe): add `_webhook_log_rows` (content-hash PK:
    {tenant_id,event,url,status,at}) + register a dual-capped StoreSpec keyed "webhook_log.json" + flip
    `webhook_log:dual` → backfill → shadow_diff. ⚠ pre-flight the distinct-hash==count collision check.
  • **wa_threads (var/wa_threads/<phone>.json) — json-only by DESIGN (§3.4): live WhatsApp inbound path;
    the (org_id,phone) PK + the U4 per-tenant dir re-key encode the bleed fix at the schema level. Stays
    json this phase by spec.** (Empty dir on box now.)
- OTHER NEXT UNITS (deferred): leads→pg cutover (+ per-request tenant contextvar, R1/U7), PgBouncer +
  per-table autovacuum (U10 infra), the §5 raw-SQL RLS proof for the remaining tables (leads proven S2),
  caller.py→APIRouter modularization (own post-seam wave), store-status json_count/pg_count for events/
  campaigns (1-line polish). U4 memory-rekey deferred (forbidden metered call).
- ⚠ TWO PARITY NOTES (log-only, same class as leads added_at deferral): (1) events `at` column = backfill/
  insert time (DEFAULT now()), NOT the event ts (which is in `data.ts`) — shadow_diff passes (compares only
  `data`) but `events_org_at_idx` orders backfilled rows by backfill time. Parse `at` from data.ts when
  analytics needs it. (2) audit.record's mirror_event uses run_in_executor (default thread pool) per event
  — fine + non-blocking, but a burst of mutating actions could saturate the pool with blocking inserts; a
  U10 scale note (same flavor as the multi_file idle-worker accrual note).
