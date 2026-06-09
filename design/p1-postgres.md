# PHASE 1 — POSTGRES MIGRATION (execution-ready build spec)

> STRANGLE & EVOLVE. Non-breaking, behind feature flags, crash-safe per unit. JSON stays AUTHORITATIVE
> until `shadow_diff == 0` per entity. The live site at https://panel.famit.in keeps earning the whole time.
> A build agent implements this VERBATIM. Read `droplet_work/P1_FOUNDATION_STATE.md` (locked decisions) +
> the master plan §PHASE 1 first. This spec supersedes / completes the U1–U9 sketch in that STATE file.

---

## 0. GROUND TRUTH (verified against live source — cite before you touch)

Box: `famit@168.144.153.145` (`/opt/famit-agent/`). Service `famit-caller` (uvicorn `caller:app` :8209) +
`famit-agent` (voice). venv `/opt/capsy-agent/.venv` (py3.12.3). SSH key
`C:\Users\kunal\.ssh\do-blr-test\id_ed25519`. Local working copy = `C:\Users\kunal\Desktop\caps\droplet_work\`.
Deploy = scp local → box → `sudo systemctl restart famit-caller` (and `famit-agent` only for the memory unit).

The storage seam (THE strangler insertion point) — all verified:
- `caller.py:412 _read(path, default)` — sync; reads JSON file, returns default on any error.
- `caller.py:421 _write(path, data)` — sync; `json.dumps(data, ensure_ascii=False, indent=2)`. **Byte format is load-bearing** (md5/shadow_diff depend on it).
- `caller.py:429 _awrite(path, data)` — async; `async with _STORE_LOCK: _write(...)`. Lock = `caller.py:259 _STORE_LOCK = asyncio.Lock()`.
- Store path constants: `caller.py:108-127` (`VAR`, `LEADS_FILE`, `CALLS_FILE`, `TENANTS_FILE`, `SUPPRESSION_FILE`, `RETRY_FILE`, `WEBHOOK_FILE`, `WEBHOOK_LOG_FILE`, `BILLING_FILE`, `LEDGER_DIR`, `USAGE_EVENTS_FILE`, `COST_LEDGER_FILE`, `DAILY_ROLLUPS_FILE`, `VENDOR_SNAPSHOTS_FILE`, `WA_LOG_FILE`, `WA_THREADS_DIR`, `CAMPAIGN_DIR`, `TRANSCRIPT_DIR`).
- `caller.py:683 CALLS: list = _read(CALLS_FILE, [])` — **in-RAM cache loaded once at import**; `record_call` (814) does `CALLS.insert(0,rec); _write(CALLS_FILE, CALLS)`. ⇒ **calls / campaigns / transcripts MUST NOT go to pure `pg` mode** (the freeze would diverge from the in-RAM list / the agent's file reads). leads is safe to reach `pg` (agent never reads leads.json; it gets lead via dispatch metadata).
- Tenant resolution: `caller.py:366 resolve_tenant(request)` → JWT (`auth.py:141 resolve_token`) → legacy PW→admin → `tenant_id.hmac`. **DO NOT rewire this. tenants.json stays authoritative for auth this phase.**
- Auth precedent module pattern (COPY IT): `auth.py` (P0) — `init(...)`, `available()`, import-safe, graceful no-op when dep/secret missing. `config.py` — same. Your `db/` + `store.py` follow this exact shape.

The cross-tenant memory bleed (the bug PHASE 1 must fix) — verified:
- `memory.py:48 _path_for(phone)` → `var/memory/<digits>.json`. **Keyed by phone ONLY.** Two tenants calling the same number SHARE memory → cross-tenant leak of prior-call summary/history.
- Agent reads/writes it: `agent.py:370 phone = mem.parse_phone(room_name)` → `mem.load_memory(phone)` (371), `mem.save_memory(phone, turns)` (402, 610).
- **The agent does NOT currently know tenant_id.** Dispatch metadata at `caller.py:1644` is `{"campaign_id", "lead_name"}` (+ optional A/B keys) — no tenant_id. The metering file `agent.py:410` literally has `"tenant_id": ""` ("caller joins tenant by room"). So the bleed fix has THREE coordinated edits: caller passes tenant_id in metadata → agent reads it → memory.py re-keys by it. Agent fallback: `agent.py:339 _load_campaign(...)` loads `campaigns/<id>.json` which DOES carry `tenant_id`, so the agent can recover tenant_id even if metadata is ever missing.
- WhatsApp threads have the SAME flat-by-phone keying: `caller.py:1047 _wa_thread_path(phone)` → `var/wa_threads/<digits>.json`. Records already carry `tenant_id` inside, but the FILE KEY is shared → same bleed. Fix in the same unit (caller-side only; tenant_id is in scope there).

Provisioning already drafted: `droplet_work/_provision_pg.sh` (idempotent; creates db `famit`, restricted role `famit_app` NOSUPERUSER/NOBYPASSRLS, prints `PROVISION_OK`). Reuse it as U1.

---

## 1. LOCKED ARCHITECTURE DECISIONS (do not relitigate)

1. **Two engines, one model set.** Sync SQLAlchemy 2.0 engine (psycopg2) for the `_read`/`_write` path
   (those run sync inside async handlers — a short blocking SELECT matches the blocking file IO already there).
   Async asyncpg engine for `_awrite`'s mirror. Rationale + confirmation in `P1_FOUNDATION_STATE.md` §ARCHITECTURE.
2. **Per-store MODE ∈ {json, dual, pg}, keyed by store NAME, DEFAULT `json` for every store.**
   - `json` — byte-identical to today (`_write` indent=2, ensure_ascii=False). Authoritative.
   - `dual` — read from JSON (authoritative); write to JSON (in `_STORE_LOCK`) **then** best-effort mirror to PG **outside** the lock with a hard timeout. PG failure is swallowed + counted, never breaks the request.
   - `pg` — read AND write Postgres; JSON file frozen. **Only ever for `leads`** in P1 (see §0). calls/campaigns/transcripts NEVER reach `pg` this phase.
3. **Import-safe degrade.** If `PG_DSN` unset OR Postgres unreachable at startup probe → FORCE every store to `json` regardless of config. The live site must never break because PG hiccups.
4. **RLS enforced for real.** App connects as restricted `famit_app` (NOSUPERUSER, NOBYPASSRLS); every table `ENABLE` **and** `FORCE ROW LEVEL SECURITY` (so even the table owner is filtered). Per-request `SET LOCAL app.tenant_id = '<tid>'` **inside the same txn** as the query (pooled-conn GUC-leak guard — `SET LOCAL` auto-resets at txn end).
5. **orgs/users/memberships = ADDITIVE mirror only.** `org_id == existing tenant_id` (string). Do NOT rewire `resolve_tenant`. tenants.json remains the auth source of record this phase. (Logto/Postgres-auth cutover is PHASE 4.)
6. **Backfill is idempotent** (UPSERT by natural id), JSON→PG only, re-runnable. **shadow_diff before any cutover.**
7. **Memory re-keyed by tenant_id** (`var/memory/<tenant_id>/<digits>.json`) with a legacy-flat-path READ fallback (zero data loss on existing memories) — the cross-tenant-bleed fix. WhatsApp threads re-keyed the same way.
8. **PgBouncer (transaction pooling) + autovacuum tuning** land in this phase as the scale-readiness floor (master plan names PgBouncer+autovacuum "stated at P1").

---

## 2. FILES TO CREATE / EDIT (paths)

CREATE (new, all under `C:\Users\kunal\Desktop\caps\droplet_work\`, deploy to `/opt/famit-agent/`):
- `db/__init__.py` — package marker.
- `db/engine.py` — sync + async engine factory, startup probe, `available()`, `session()`/`asession()` ctx-managers that `SET LOCAL app.tenant_id`. Import-safe (mirror `auth.py`).
- `db/models.py` — SQLAlchemy 2.0 declarative models for the full schema (§3). DDL source of truth.
- `db/rls.sql` — RLS policy DDL + restricted-grant DDL + GUC helper (applied by Alembic op, see §4).
- `store.py` — the per-store MODE router over `_read`/`_write`/`_awrite`. The ONLY file `caller.py` calls into for the seam.
- `backfill.py` — idempotent JSON→PG loader (per entity, UPSERT by id).
- `shadow_diff.py` — reads JSON store + PG table for an entity, reports row-count + per-id field drift, exits nonzero on drift.
- `alembic.ini` + `migrations/env.py` + `migrations/versions/0001_init.py` (+ later `0002_*` etc.) — schema versioning.
- `db/pgbouncer.ini` + `db/autovacuum.sql` — infra configs (applied on box, U10).

EDIT (surgical, cite line):
- `caller.py` — (a) import `store`; (b) route `_read`/`_write`/`_awrite` (412/421/429) through `store` when a path is registered, else unchanged; (c) call `store.init(...)` at startup; (d) add `tenant_id` to dispatch metadata at `1644`; (e) re-key `_wa_thread_path` (1047) by tenant_id; (f) add `GET /admin/store-status` + `GET /admin/shadow-diff`.
- `agent.py` — read `meta.get("tenant_id")` (near 336) and pass it to `mem.load_memory`/`mem.save_memory` (370/371/402/610); fallback to `camp.get("tenant_id")`.
- `memory.py` — `_path_for(tenant_id, phone)` with legacy-flat READ fallback; thread `tenant_id` through `load_memory`/`save_memory` signatures (keep old positional call working via default `tenant_id=""`).
- `.env` on box — append `PG_DSN`, `PG_DSN_ASYNC`, `STORE_MODES`, `STORE_PG_TIMEOUT_MS`, `MEMORY_TENANT_SCOPED` (all default-off / safe).

DO NOT TOUCH: `prompt.py`, `vendors/`, `whatsapp.py` send logic, `langdetect.py`, the voice/SIP path, `resolve_tenant`, the JWT/auth flow, nginx, frontend.

---

## 3. THE FULL SCHEMA (column types + indexes)

SQLAlchemy 2.0 in `db/models.py`; the canonical DDL is what Alembic `0001_init` emits. Conventions:
- Every tenant-scoped table has `org_id text NOT NULL` (== tenant_id) + an RLS policy on it (§5).
- `id` = the existing app id (string hex from `uuid4().hex[:10]`, phone, etc.) to make backfill a pure UPSERT-by-id and shadow_diff trivial. Use `text` PKs (NOT new uuids) — match JSON exactly.
- Timestamps stored `timestamptz`; but ALSO keep the original ISO string columns where the JSON has them, so shadow_diff is byte-comparable (don't reformat on the way in). Where JSON stores a naive `isoformat(timespec="seconds")`, store it verbatim in a `*_raw text` column AND parse into a `timestamptz` for indexing.
- `data jsonb` catch-all column on each table holds the FULL original record (so nothing is lost and shadow_diff can compare the whole object). Promoted columns are for indexing/RLS/query only.

> Rule: **promote to a real column only what we index, filter, or RLS on; everything else lives in `data jsonb`.** This keeps backfill lossless and forward-compatible.

### 3.1 Control / identity (additive mirror; auth stays on tenants.json)

```sql
CREATE TABLE orgs (
  id            text PRIMARY KEY,            -- == tenant_id
  name          text NOT NULL DEFAULT '',
  is_admin      boolean NOT NULL DEFAULT false,
  created_at    timestamptz NOT NULL DEFAULT now(),
  data          jsonb NOT NULL DEFAULT '{}'  -- full tenant record (limits, plan refs, etc.)
);

CREATE TABLE users (
  id            text PRIMARY KEY,            -- == tenant_id for the seeded 1-user-per-org case
  org_id        text NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
  email         text NOT NULL,
  name          text NOT NULL DEFAULT '',
  role          text NOT NULL DEFAULT 'manager',  -- admin|manager|agent
  is_admin      boolean NOT NULL DEFAULT false,
  pass_hash     text NOT NULL DEFAULT '',    -- mirror only; auth still reads tenants.json
  salt          text NOT NULL DEFAULT '',
  created_at    timestamptz NOT NULL DEFAULT now(),
  data          jsonb NOT NULL DEFAULT '{}'
);
CREATE UNIQUE INDEX users_email_uq ON users (lower(email));
CREATE INDEX users_org_idx ON users (org_id);

CREATE TABLE memberships (
  org_id        text NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
  user_id       text NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  role          text NOT NULL DEFAULT 'manager',
  created_at    timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (org_id, user_id)
);
```

### 3.2 Campaigns / leads / calls (the OLTP core)

```sql
CREATE TABLE campaigns (
  id            text PRIMARY KEY,
  org_id        text NOT NULL,
  name          text NOT NULL DEFAULT '',
  company       text NOT NULL DEFAULT '',
  product       text NOT NULL DEFAULT '',
  status        text NOT NULL DEFAULT 'active',
  voice_id      text NOT NULL DEFAULT '',
  created_at_raw text NOT NULL DEFAULT '',
  created_at    timestamptz,
  fields        jsonb NOT NULL DEFAULT '{}',  -- the whole campaign fields blob (incl variants, wa_*, window)
  system_prompt text NOT NULL DEFAULT '',
  data          jsonb NOT NULL DEFAULT '{}'   -- full original record
);
CREATE INDEX campaigns_org_idx ON campaigns (org_id);
-- MODE: json-only in P1 (agent reads campaigns/<id>.json). Mirror allowed in dual for read-replica analytics later; NEVER pg.

CREATE TABLE leads (
  id            text PRIMARY KEY,
  org_id        text NOT NULL,
  name          text NOT NULL DEFAULT '',
  phone         text NOT NULL DEFAULT '',      -- normalized (+91…)
  status        text NOT NULL DEFAULT 'new',
  score         integer NOT NULL DEFAULT 0,
  hot           boolean NOT NULL DEFAULT false,
  last_outcome  text NOT NULL DEFAULT '',
  last_call_at  text NOT NULL DEFAULT '',
  added_at_raw  text NOT NULL DEFAULT '',
  added_at      timestamptz,
  data          jsonb NOT NULL DEFAULT '{}'
);
CREATE INDEX leads_org_idx ON leads (org_id);
CREATE UNIQUE INDEX leads_org_phone_uq ON leads (org_id, phone);  -- matches "deduped within tenant"
CREATE INDEX leads_org_score_idx ON leads (org_id, score DESC);   -- /leads/hot, sort=score
-- MODE: the ONLY store that may reach pg in P1.

CREATE TABLE calls (
  id            text PRIMARY KEY,
  org_id        text NOT NULL,
  campaign_id   text NOT NULL DEFAULT '',
  campaign_name text NOT NULL DEFAULT '',
  name          text NOT NULL DEFAULT '',
  phone         text NOT NULL DEFAULT '',
  status        text NOT NULL DEFAULT '',       -- calling|done|failed|suppressed
  outcome       text NOT NULL DEFAULT '',
  answered      boolean NOT NULL DEFAULT false,
  interest      integer NOT NULL DEFAULT 0,
  variant_id    text NOT NULL DEFAULT '',
  variant_label text NOT NULL DEFAULT '',
  room          text NOT NULL DEFAULT '',
  sip_call_id   text NOT NULL DEFAULT '',
  duration_s    integer NOT NULL DEFAULT 0,
  started_at_raw text NOT NULL DEFAULT '',
  ended_at_raw  text NOT NULL DEFAULT '',
  started_at    timestamptz,
  data          jsonb NOT NULL DEFAULT '{}'
);
CREATE INDEX calls_org_started_idx ON calls (org_id, started_at DESC);
CREATE INDEX calls_org_campaign_idx ON calls (org_id, campaign_id);
CREATE INDEX calls_room_idx ON calls (room);            -- transcript/metering join by room
CREATE INDEX calls_org_outcome_idx ON calls (org_id, outcome);
-- MODE: json or dual only. NEVER pg (in-RAM CALLS list + record_call).
```

### 3.3 Suppression / retry / callbacks / webhooks

```sql
CREATE TABLE suppression (
  org_id        text NOT NULL,
  phone         text NOT NULL,                  -- normalized
  reason        text NOT NULL DEFAULT '',
  source        text NOT NULL DEFAULT '',
  added_at      timestamptz NOT NULL DEFAULT now(),
  data          jsonb NOT NULL DEFAULT '{}',
  PRIMARY KEY (org_id, phone)
);

CREATE TABLE retry_queue (
  id              text PRIMARY KEY,
  org_id          text NOT NULL,
  campaign_id     text NOT NULL DEFAULT '',
  name            text NOT NULL DEFAULT '',
  phone           text NOT NULL DEFAULT '',
  attempts        integer NOT NULL DEFAULT 0,
  max_attempts    integer NOT NULL DEFAULT 3,
  next_attempt_at timestamptz,
  next_attempt_raw text NOT NULL DEFAULT '',
  reason          text NOT NULL DEFAULT '',   -- VERIFIED discriminator: reason=='callback' ⇒ it's a callback, else a retry (caller.py:2417)
  created_at      timestamptz NOT NULL DEFAULT now(),
  data            jsonb NOT NULL DEFAULT '{}'
);
CREATE INDEX retry_org_due_idx ON retry_queue (org_id, next_attempt_at);
CREATE INDEX retry_due_idx ON retry_queue (next_attempt_at);  -- scheduler scans all-due (caller.py:3318)
CREATE INDEX retry_reason_idx ON retry_queue (org_id, reason);  -- GET /callbacks filters reason=='callback'
-- VERIFIED: callbacks live INSIDE retry_queue.json; the record (caller.py:946) has NO `kind` field — `reason` is the
-- discriminator (`GET /callbacks?all=` keeps only reason=='callback', caller.py:2417). One table; do NOT add a
-- `kind` column and do NOT invent a separate callbacks store. (The unrelated `kind=` matches in caller.py are WhatsApp-log kinds.)

CREATE TABLE webhooks (
  id            text PRIMARY KEY,
  org_id        text NOT NULL,
  url           text NOT NULL,
  secret        text NOT NULL DEFAULT '',
  events        jsonb NOT NULL DEFAULT '[]',
  active        boolean NOT NULL DEFAULT true,
  created_at    timestamptz NOT NULL DEFAULT now(),
  data          jsonb NOT NULL DEFAULT '{}'
);
CREATE INDEX webhooks_org_idx ON webhooks (org_id);

CREATE TABLE webhook_log (
  id            text PRIMARY KEY,                -- DETERMINISTIC = sha256(canonical json line); idempotent backfill via ON CONFLICT DO NOTHING
  org_id        text NOT NULL DEFAULT '',
  event         text NOT NULL DEFAULT '',
  url           text NOT NULL DEFAULT '',
  status        text NOT NULL DEFAULT '',
  at            timestamptz NOT NULL DEFAULT now(),
  data          jsonb NOT NULL DEFAULT '{}'
);
CREATE INDEX webhook_log_org_at_idx ON webhook_log (org_id, at DESC);
```

### 3.4 WhatsApp (log + threads)

```sql
CREATE TABLE wa_log (
  id            text PRIMARY KEY,                -- DETERMINISTIC = sha256(canonical json row); idempotent backfill via ON CONFLICT DO NOTHING
  org_id        text NOT NULL DEFAULT '',
  phone         text NOT NULL DEFAULT '',
  template      text NOT NULL DEFAULT '',
  kind          text NOT NULL DEFAULT '',        -- manual|auto_followup
  status        text NOT NULL DEFAULT '',
  ok            boolean NOT NULL DEFAULT false,
  at            timestamptz NOT NULL DEFAULT now(),
  data          jsonb NOT NULL DEFAULT '{}'
);
CREATE INDEX wa_log_org_at_idx ON wa_log (org_id, at DESC);

CREATE TABLE wa_threads (
  org_id        text NOT NULL,
  phone         text NOT NULL,                   -- digits
  name          text NOT NULL DEFAULT '',
  campaign_id   text NOT NULL DEFAULT '',
  campaign_name text NOT NULL DEFAULT '',
  status        text NOT NULL DEFAULT 'active',   -- active|opted_out|needs_human
  turns         jsonb NOT NULL DEFAULT '[]',
  created_at    timestamptz NOT NULL DEFAULT now(),
  updated_at    timestamptz NOT NULL DEFAULT now(),
  data          jsonb NOT NULL DEFAULT '{}',
  PRIMARY KEY (org_id, phone)
);
-- MODE: json-only in P1 (live WA inbound path). The (org_id, phone) PK encodes the bleed fix at the schema level.
```

### 3.5 Billing / ledger / usage / cost (metering)

```sql
CREATE TABLE billing (
  org_id           text PRIMARY KEY,
  plan             text NOT NULL DEFAULT 'postpaid',
  currency         text NOT NULL DEFAULT 'INR',
  rate_per_min     numeric(12,4) NOT NULL DEFAULT 0,
  rate_per_call    numeric(12,4) NOT NULL DEFAULT 0,
  balance          numeric(14,4) NOT NULL DEFAULT 0,
  included_minutes integer NOT NULL DEFAULT 0,
  data             jsonb NOT NULL DEFAULT '{}'
);

CREATE TABLE ledger (
  id            text PRIMARY KEY,
  org_id        text NOT NULL,
  call_id       text NOT NULL DEFAULT '',
  phone         text NOT NULL DEFAULT '',
  campaign_id   text NOT NULL DEFAULT '',
  duration_s    integer NOT NULL DEFAULT 0,
  cost          numeric(14,6) NOT NULL DEFAULT 0,
  currency      text NOT NULL DEFAULT 'INR',
  outcome       text NOT NULL DEFAULT '',
  at_raw        text NOT NULL DEFAULT '',
  at            timestamptz,
  data          jsonb NOT NULL DEFAULT '{}'
);
CREATE INDEX ledger_org_at_idx ON ledger (org_id, at DESC);
-- JSON is var/ledger/<tenant_id>.json (one file per tenant). Backfill iterates files; org_id from filename.

CREATE TABLE usage_events (
  id            text PRIMARY KEY,               -- synth from (room|call_id|vendor|hash) if JSON has none
  org_id        text NOT NULL DEFAULT '',
  call_id       text NOT NULL DEFAULT '',
  room          text NOT NULL DEFAULT '',
  vendor        text NOT NULL DEFAULT '',       -- groq|sarvam|elevenlabs|vobiz|livekit
  units         numeric(16,4) NOT NULL DEFAULT 0,
  unit_kind     text NOT NULL DEFAULT '',       -- chars|tokens_in|tokens_out|stt_sec|min
  cost          numeric(14,6) NOT NULL DEFAULT 0,
  at_raw        text NOT NULL DEFAULT '',
  at            timestamptz,
  data          jsonb NOT NULL DEFAULT '{}'
);
CREATE INDEX usage_org_at_idx ON usage_events (org_id, at DESC);
CREATE INDEX usage_room_idx ON usage_events (room);
CREATE INDEX usage_vendor_idx ON usage_events (vendor);

CREATE TABLE cost_ledger (
  id            text PRIMARY KEY,               -- per-call normalized cost row id (synth if absent)
  org_id        text NOT NULL DEFAULT '',
  call_id       text NOT NULL DEFAULT '',
  room          text NOT NULL DEFAULT '',
  campaign_id   text NOT NULL DEFAULT '',
  total_cost    numeric(14,6) NOT NULL DEFAULT 0,
  by_vendor     jsonb NOT NULL DEFAULT '{}',
  currency      text NOT NULL DEFAULT 'INR',
  ts_raw        text NOT NULL DEFAULT '',
  ts            timestamptz,
  data          jsonb NOT NULL DEFAULT '{}'
);
CREATE INDEX cost_org_ts_idx ON cost_ledger (org_id, ts DESC);
CREATE INDEX cost_room_idx ON cost_ledger (room);
```

### 3.6 Audit / events ledger

The audit store is `var/audit_log.jsonl` (append-only JSONL, P0 — see HANDOFF "AUDIT"). The events ledger == the same stream.

```sql
CREATE TABLE events (                            -- == audit ledger (append-only)
  id            text PRIMARY KEY,                -- DETERMINISTIC = sha256(raw JSONL line); idempotent backfill via ON CONFLICT DO NOTHING (re-runnable, no dup rows)
  org_id        text NOT NULL DEFAULT '',        -- actor tenant
  actor         text NOT NULL DEFAULT '',
  action        text NOT NULL DEFAULT '',
  object_type   text NOT NULL DEFAULT '',
  object_id     text NOT NULL DEFAULT '',
  ip            text NOT NULL DEFAULT '',
  channel       text NOT NULL DEFAULT '',
  at            timestamptz NOT NULL DEFAULT now(),
  meta          jsonb NOT NULL DEFAULT '{}',
  data          jsonb NOT NULL DEFAULT '{}'      -- full original JSONL line
);
CREATE INDEX events_org_at_idx ON events (org_id, at DESC);
CREATE INDEX events_action_idx ON events (action);
-- Append-only: backfill reads the JSONL; ongoing dual-write appends. No UPDATE/DELETE policy (insert+select only).
```

### 3.7 Indexing summary / rationale
- Every tenant query path has a `(org_id, …)` composite leading with org_id (RLS + tenant filter share it).
- `room` indexes (calls, usage_events, cost_ledger) back the transcript/metering join the agent's late-landing transcript needs.
- `leads_org_phone_uq` enforces the existing "dedupe within tenant" invariant at the DB level — backfill UPSERTs on it.
- No vector/pgvector tables here — that is PHASE 2 (RAG). P1 is OLTP only.

---

## 4. ALEMBIC + MIGRATION MECHANICS

- `alembic init migrations`; set `sqlalchemy.url` from `PG_DSN` (sync) in `env.py` (read via `config.get`).
- `migrations/versions/0001_init.py` — `upgrade()` creates all §3 tables + indexes. Then runs the RLS/grant DDL from `db/rls.sql` via `op.execute(open('db/rls.sql').read())` (or inline). `downgrade()` drops all tables.
- Migrations run as the DB **owner** (`famit_app` owns the db per `_provision_pg.sh:36`). Owner can create tables; FORCE RLS makes the owner still subject to policies at query time — that's intended.
- Apply: `cd /opt/famit-agent && /opt/capsy-agent/.venv/bin/alembic upgrade head`. **DDL only — zero behavior change** (app still 100% json mode; nothing reads PG yet).
- Every later schema change = a NEW `000N_*.py` revision (master plan: "DB-migration versioning (Alembic)"). Never edit a shipped revision.

---

## 5. RLS POLICIES + PER-REQUEST GUC (`db/rls.sql` + `db/engine.py`)

`db/rls.sql` (idempotent; applied by 0001):

```sql
-- 0) GUC default so a session without SET LOCAL sees NOTHING (fail-closed), except admin bypass below.
ALTER DATABASE famit SET app.tenant_id = '';

-- 1) For every tenant-scoped table: enable + FORCE rls, add an org_id policy.
--    Admin escape hatch: app.is_admin='1' sees all rows (the app sets it only for is_admin tenants).
DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY[
    'orgs','users','memberships','campaigns','leads','calls','suppression',
    'retry_queue','webhooks','webhook_log','wa_log','wa_threads',
    'billing','ledger','usage_events','cost_ledger','events'
  ] LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY;', t);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY;', t);
    EXECUTE format($f$
      CREATE POLICY %1$s_isolation ON %1$I
      USING (
        current_setting('app.is_admin', true) = '1'
        OR %2$I = current_setting('app.tenant_id', true)
      )
      WITH CHECK (
        current_setting('app.is_admin', true) = '1'
        OR %2$I = current_setting('app.tenant_id', true)
      );
    $f$, t, CASE WHEN t='orgs' THEN 'id' ELSE 'org_id' END);
  END LOOP;
END $$;
```
(`orgs` keys on `id`; `users` on `org_id`; everything else on `org_id`. `current_setting(...,true)` = missing_ok so a fresh conn doesn't error.)

`db/engine.py` session contract — **GUC is set INSIDE the txn that runs the query** (SET LOCAL resets at COMMIT/ROLLBACK, so a pooled conn can never leak tenant scope to the next checkout):

```python
@contextmanager
def session(tenant_id: str, is_admin: bool = False):
    with _SyncSessionLocal() as s:           # psycopg2 engine
        s.execute(text("SET LOCAL app.tenant_id = :tid"), {"tid": tenant_id or ""})
        s.execute(text("SET LOCAL app.is_admin = :adm"), {"adm": "1" if is_admin else "0"})
        yield s
        s.commit()

@asynccontextmanager
async def asession(tenant_id: str, is_admin: bool = False):
    async with _AsyncSessionLocal() as s:    # asyncpg engine
        await s.execute(text("SET LOCAL app.tenant_id = :tid"), {"tid": tenant_id or ""})
        await s.execute(text("SET LOCAL app.is_admin = :adm"), {"adm": "1" if is_admin else "0"})
        yield s
        await s.commit()
```
- **Never** open a query outside `session()/asession()`. The GUC and the SELECT/INSERT must share the txn.
- `is_admin` flag is set ONLY from the resolved tenant's `is_admin` (so admin pages keep seeing all data, matching today). A vendor token can never set it.

RLS proof (U-RLS acceptance): connect raw as `famit_app`, `SET app.tenant_id='vendorA'` (note: a plain `SET`, not within app), `SELECT * FROM leads` → returns only vendorA rows; switching to `'vendorB'` returns only B's; a cross-tenant `UPDATE` affects 0 rows. With `app.is_admin` unset/`'0'`. This proves isolation independent of app code.

---

## 6. `store.py` — THE PER-STORE MODE ROUTER (the riskiest unit)

Public surface (what caller.py calls):
```python
store.init(read_fn, write_fn, awrite_fn, lock, config)   # called once at startup from caller.py
store.read(path, default)        # used by the _read shim
store.write(path, data)          # used by the _write shim
await store.awrite(path, data)   # used by the _awrite shim
store.mode_of(path) -> "json"|"dual"|"pg"
store.status() -> {storename: {mode, last_shadow_diff, pg_writes_ok, pg_writes_fail, last_error}}
```

Design:
1. **Registry** maps each known `Path` (by `.name`, e.g. `"leads.json"`) → a `StoreSpec{name, table, mode, to_rows(json)->rows, key(row)->id}`. Only registered paths are ever touched; an unregistered path falls straight through to the original sync `_read`/`_write` (so untouched stores behave exactly as today — campaigns, transcripts, secret, etc.).
2. **Mode resolution.** Effective mode = `min(configured_mode, max_safe_mode_for_store)`. `max_safe` caps calls/campaigns/transcripts/wa_threads at `dual` (never `pg`); leads may be `pg`. If `db.available()` is False → mode forced `json` for ALL.
3. **read(path, default):**
   - `json`/`dual` → original `_read(path, default)` (JSON authoritative). 
   - `pg` (leads only) → `db.session(...)`-scoped SELECT with a **deterministic `ORDER BY added_at, id`** (a bare SELECT returns arbitrary row order; `_read` returns file/insertion order — without ORDER BY the list order silently drifts and any order-dependent caller or shadow compare breaks). Rebuild the list-of-dicts in the SAME shape `_read` returned (use the `data jsonb` column → exact original objects). On ANY error → fall back to `_read` (json) and flip the store to degraded-json + record error. **Never raise.**
4. **write(path, data):**
   - `json` → original `_write`. Nothing else. (Transparent pass-through.)
   - `dual` → original `_write` FIRST (authoritative, fast, unchanged), THEN fire a best-effort PG mirror. **TWO non-negotiable properties:**
     - **(a) FULL-SNAPSHOT RECONCILE, not bare upsert.** Every `_write(LEADS_FILE, data)` is a whole-file, all-tenants snapshot (verified: writers at caller.py:492/858/908/2087/2105 read-modify-write the ENTIRE list; deletes happen by omission, e.g. `DELETE /leads/{id}` at 2092-2105). A bare upsert-by-id therefore NEVER removes deleted rows → PG accumulates stale rows → `shadow_diff` never reaches 0. So the mirror MUST, in ONE txn: `UPSERT` every id present in the snapshot **AND `DELETE` every row whose id is not in the snapshot** (scoped to the tenants represented — for whole-file stores, all). Implement as: temp-load incoming ids → `INSERT … ON CONFLICT DO UPDATE` for each → `DELETE FROM <t> WHERE id <> ALL(:incoming_ids)` (admin GUC, since a file snapshot spans tenants). **⚠ EMPTY-SNAPSHOT GUARD (see RED-TEAM B2): `id <> ALL(ARRAY[]::text[])` is TRUE for every row, so an empty/failed snapshot would DELETE the whole table. NEVER run delete-by-omission when the incoming id-set is empty AND PG is non-empty; and NEVER reconcile from a `_read` that raised (a transient read error must not be read as "0 rows").**
     - **(b) NON-BLOCKING — never stall the event loop.** `_write` runs SYNC on the loop thread; a full-snapshot reconcile can take 100s of ms and would stall the `/run` dial loop under load. The mirror is OFF the request path — but it is **NOT** a free `create_task` per write (see RED-TEAM B1: that races and permanently breaks shadow_diff). **MANDATORY: a single per-store background worker that always applies the LATEST pending snapshot and coalesces/drops superseded ones** (every write is a whole-file snapshot, so only the newest matters). Enqueue the snapshot to a bounded `asyncio.Queue` (depth 1, replace-on-full) consumed by one long-lived task started in `store.init`; if no loop is running (import-time / sync script) skip the mirror. Wrap each mirror in `STORE_PG_TIMEOUT_MS`; on failure increment `pg_writes_fail`, log, swallow. The JSON write already returned to the caller before any PG work starts.
   - `pg` (leads) → write PG inside `db.session`; on success ALSO keep a JSON shadow write (so a rollback to json mode loses nothing) UNLESS explicitly "frozen". Default: pg mode still shadow-writes JSON (cheap insurance) — only stop shadowing after U-cutover proves stability.
5. **awrite(path, data):** ⚠ **DEAD PATH IN P1 (see RED-TEAM B-confirm).** Verified: there are ZERO `await _awrite(...)` call sites in caller.py — leads/calls/suppression/retry are ALL written via the SYNC `_write` (grep: 492/501/817/858/908/1493/1505/2087/2105/3393), and even `_wa_thread_write` (1056) takes `_STORE_LOCK` directly rather than calling `_awrite`. So the strangler seam in P1 is effectively `_read`/`_write` only. Keep an `awrite` shim wired (so the seam is complete if a future caller uses it) but it MUST behave identically to the `dual`/`pg` `write` path above — same per-store coalescing worker, same (a)+(b) rules — with the JSON write held inside `_STORE_LOCK`. Do NOT design a second, divergent mirror mechanism for it.
6. The "tenant_id" for PG writes: store rows already carry `org_id`/`tenant_id` per object; the mirror sets the session GUC to the ADMIN context for whole-file mirrors (a file write is a multi-tenant batch) — i.e. mirror runs with `is_admin=True` GUC so RLS doesn't reject a batched multi-tenant write. **Reads via `read()` for `pg` leads, however, MUST scope to the caller's tenant** — so `store.read` for leads takes the tenant from a contextvar set by caller.py per request (see §7 wiring), NOT admin. (This is why leads-pg is gated behind explicit per-request tenant plumbing; until that contextvar is wired, leads stays at `dual`.)

> The whole module is wrapped so that ANY failure degrades to the original JSON behavior. The bar: with all stores at default `json`, `store.py` is a transparent pass-through and the regression gate is byte-identical.

caller.py wiring (minimal, cite lines):
- ⚠ **INIT-ORDER HAZARD (see RED-TEAM B4).** `_store` MUST be defined `= None` at module top **before line 469/504/683** — because `_migrate_to_admin()` (runs at import, 504) and `CALLS = _read(CALLS_FILE, [])` (683) call the rewritten shims AT IMPORT TIME. If `_store` is first bound only at the `store.init` site below 683, the shim references an unassigned global → `NameError` → swallowed by `_migrate_to_admin`'s bare `except` (482) → the import-time admin tenant_id migration **silently no-ops**. The U3 byte-identical gate would still pass (all-json), so this corruption is INVISIBLE to the gate. Therefore: put `_store = None` next to `_STORE_LOCK` (≈259), and the shims must guard `_store is not None` (not just truthiness).
- After defining `_read`/`_write`/`_awrite` (412-433) and config load, add:
  ```python
  _store = None   # ALSO declared at ~259 so import-time shim calls (504/683) are safe
  try:
      import store as _store_mod
      _store_mod.init(_read_raw, _write_raw, _awrite_raw, _STORE_LOCK, config)
      _store = _store_mod
  except Exception:
      _store = None
  ```
  Rename the current bodies to `_read_raw`/`_write_raw`/`_awrite_raw`, and make `_read`/`_write`/`_awrite` thin shims: `return _store.read(path, default) if (_store is not None and _store.mode_of(path)!="json") else _read_raw(path, default)` (and likewise). Keeps every existing call-site unchanged. Assign `_store` only AFTER `init` returns so a half-initialized module can never be used.

---

## 7. MEMORY RE-KEY BY TENANT (the cross-tenant bleed fix)

Three coordinated edits (one unit, deploy together, restart BOTH services):

**memory.py:**
```python
_TENANT_SCOPED = os.getenv("MEMORY_TENANT_SCOPED", "1") != "0"   # default ON (the fix)

def _path_for(tenant_id: str, phone: str) -> Path:
    safe_p = re.sub(r"[^0-9]", "", phone or "") or "unknown"
    safe_t = re.sub(r"[^A-Za-z0-9_-]", "", tenant_id or "")
    if _TENANT_SCOPED and safe_t:
        return _MEM_DIR / safe_t / f"{safe_p}.json"
    return _MEM_DIR / f"{safe_p}.json"            # legacy flat (fallback / disabled)

def load_memory(phone: str, tenant_id: str = "") -> dict | None:
    # try tenant-scoped first, then legacy flat (back-compat, zero loss), never raise
    for p in _candidate_paths(tenant_id, phone):
        if p.exists():
            try: return json.loads(p.read_text(encoding="utf-8"))
            except Exception: return None
    return None

def save_memory(phone: str, history, summary: str = "", tenant_id: str = "") -> None:
    # writes ONLY to the tenant-scoped path (or flat if scoping off / no tid)
```
- `_candidate_paths` = `[tenant-scoped, legacy-flat]` when scoped, else `[flat]`. Reads fall back to legacy so existing memories keep working; writes go to the new scoped path so they self-migrate on next call. **No bulk migration needed** (and a bulk migration is unsafe — we can't attribute an existing flat `<phone>.json` to a tenant; leave it as a read-only fallback that naturally ages out).
- Signatures keep `tenant_id=""` default ⇒ any un-updated caller still compiles.

**caller.py:1644** — add tenant_id to dispatch metadata:
```python
md_obj = {"campaign_id": cid, "lead_name": it.get("name", ""), "tenant_id": tenant_id}
```
(`tenant_id` is already in scope — used at 1665 for the call record.)

**agent.py** (near 336 / 370 / 402 / 610):
```python
tenant_id = (meta.get("tenant_id") or "").strip()
if not tenant_id and camp:
    tenant_id = (camp.get("tenant_id") or "").strip()   # fallback: campaign file carries tenant_id
...
recap = mem.build_recap(mem.load_memory(phone, tenant_id))      # was load_memory(phone)
...
mem.save_memory(phone, turns, tenant_id=tenant_id)              # both 402 and 610
```

**WhatsApp threads (caller.py:1047)** — same bleed, caller-side (tenant_id in scope at every call site 1152/1156/1237/2931):
```python
def _wa_thread_path(phone: str, tenant_id: str = "") -> Path:
    safe = re.sub(r"[^0-9]", "", phone or "") or "unknown"
    safe_t = re.sub(r"[^A-Za-z0-9_-]", "", tenant_id or "")
    if safe_t:
        return WA_THREADS_DIR / safe_t / f"{safe}.json"
    return WA_THREADS_DIR / f"{safe}.json"
```
Thread read/write helpers (`_wa_thread_read`/`_wa_thread_write`, 1052/1056) gain a `tenant_id` param; the listing glob at 2931 changes from `WA_THREADS_DIR.glob("*.json")` to `WA_THREADS_DIR.glob("*/*.json")` for scoped + a legacy `*.json` pass, filtering by `tenant_id` on the record (already stored). Keep legacy flat read fallback.

> The PK `(org_id, phone)` on the `wa_threads` table (§3.4) and the per-tenant directory both encode the fix; even if the file layer regresses, the eventual PG store can't bleed.

ACCEPTANCE for this unit: create two tenants; place (or simulate) a call to the SAME phone under each; confirm `var/memory/<tenantA>/<phone>.json` and `var/memory/<tenantB>/<phone>.json` are SEPARATE files; tenant B's recap never contains tenant A's summary. Existing flat memory for an already-seen phone still loads (fallback) on a call by its original tenant.

---

## 8. backfill.py + shadow_diff.py

**backfill.py** — `python backfill.py <entity> [--commit]` (dry-run by default, prints counts; `--commit` writes):
- For each entity: read the JSON store via the SAME loader caller.py uses (so coercion matches), map each record → a row (promoted columns + full object into `data jsonb`), UPSERT by natural id (`ON CONFLICT (id) DO UPDATE`, or `(org_id,phone)`/`(org_id,id)` per the table PK). Idempotent — re-running converges.
- **Append-only / no-natural-id tables (`events`, `wa_log`, `webhook_log`) — idempotency rule:** these have NO natural id in JSON. Their PK is a **deterministic content hash** — `id = sha256(canonical-serialization-of-the-record)` (for `events`: the raw JSONL line verbatim; for `wa_log`/`webhook_log`: `json.dumps(record, sort_keys=True, ensure_ascii=False)`). Backfill uses `ON CONFLICT (id) DO NOTHING`. Re-running (which the crash-safe protocol expects) is a no-op for already-loaded rows → `shadow_diff` count stays exact. The SAME hash is computed by the dual-mode mirror on ongoing appends, so a record can never be inserted twice across backfill + live mirror. (Same trick already used implicitly for `usage_events`/`cost_ledger`.)
- org_id source: the record's `tenant_id` (default `admin` for legacy rows missing it — matches `calls_for` fallback at caller.py:823). For `ledger`, org_id from the per-tenant filename.
- Runs with admin GUC (`db.session("", is_admin=True)`) since it batches all tenants.
- Entities + order: `orgs,users,memberships` (from tenants.json) → `campaigns` → `leads` → `calls` → `suppression` → `retry_queue` → `webhooks,webhook_log` → `wa_log,wa_threads` → `billing,ledger` → `usage_events,cost_ledger` → `events` (from audit_log.jsonl).
- Prints `BACKFILL <entity>: json=<n> pg=<m> upserted=<k>`.

**shadow_diff.py** — `python shadow_diff.py <entity>` → exit 0 iff PG matches JSON:
- Load JSON list + PG rows (admin GUC). Compare: (a) count; (b) set of ids; (c) for each id, the `data jsonb` vs the JSON object (normalize: same json.dumps sort_keys). Report `+only_json`, `+only_pg`, `~field_drift` per id, capped sample. Exit nonzero on any drift.
- This is the gate before any `dual→pg` flip and the periodic drift report (U-RLS).

---

## 9. STEP ORDER + PER-STEP ACCEPTANCE (the build sequence)

> Every unit: back up changed files locally (`*.p1bak.<ts>`) + on box before deploy; deploy ONE unit; run the
> REGRESSION GATE; write a build_log entry under `memory/build_log/`; commit. A crash costs at most one unit.
> **REGRESSION GATE (run after EVERY unit):** legacy `X-Auth: FamitCall2026` → 200 on `/campaigns`;
> `/auth/login` issues tokens; `/leads /run /billing/overview /me /stats` all 200; `/run` dispatches a job;
> `famit-caller` + `famit-agent` both `active`; `md5 local==deployed` for changed files; NO paid call placed.

| # | Unit | Action | Acceptance test (prove on live box, no breakage) |
|---|------|--------|--------------------------------------------------|
| U1 | PROVISION | Run `_provision_pg.sh` on box. pip into venv: `sqlalchemy[asyncio] asyncpg psycopg2-binary alembic greenlet`. Back up `.env`; append `PG_DSN`, `PG_DSN_ASYNC` (localhost famit_app), `STORE_MODES=` (empty → all json), `STORE_PG_TIMEOUT_MS=800`, `MEMORY_TENANT_SCOPED=1`. | Script prints `PROVISION_OK`. `PGPASSWORD=… psql -h127.0.0.1 -Ufamit_app -dfamit -c 'select 1'` → 1. `python -c "import sqlalchemy,asyncpg,psycopg2"` OK in venv. **App untouched → regression gate green.** |
| U2 | SCHEMA | Add `db/__init__.py`, `db/engine.py`, `db/models.py`, `db/rls.sql`; `alembic init`; write `0001_init`. `alembic upgrade head`. | `\dt` shows all 17 tables; `\d leads` shows indexes; `SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname='leads'` → `t,t`. **Zero app code changed → regression gate green** (app still pure json; PG idle). |
| U3 | STORE SEAM | Add `store.py`; rewire `_read/_write/_awrite` to shims + `store.init(...)` at startup. Deploy. **STORE_MODES empty (all json).** RISKIEST. | **Byte-identical proof:** md5 of `leads.json`/`calls.json` before vs after a `/leads` POST is unchanged in shape; `GET /leads`,`/calls`,`/stats`,`/campaigns` all 200 with identical bodies vs a pre-deploy capture. `store.status()` (via new `/admin/store-status`, U8) shows every store `mode=json`. Regression gate green. |
| U4 | MEMORY RE-KEY | memory.py + agent.py + caller.py(1644) + wa_thread re-key. Deploy BOTH services. | Two-tenant same-phone test (§7) → separate files, no bleed; legacy flat memory still loads; a real metered test call (to 6375548830) still writes transcript+summary+memory under `var/memory/<tenant>/`. Regression gate green; voice path unaffected (eou/latency unchanged in logs). |
| U5 | LEADS→DUAL | Set `STORE_MODES=leads:dual`. Restart caller. | `POST /leads` (one lead) → appears in BOTH `leads.json` AND `SELECT * FROM leads WHERE phone=…`. `/admin/store-status` leads `mode=dual`, `pg_writes_ok>0`, `fail=0`. `GET /leads` still served from JSON, 200, unchanged. |
| U6 | BACKFILL leads | `python backfill.py leads --commit`. | `BACKFILL leads: json=N pg=N`. `python shadow_diff.py leads` → exit 0 (`shadow_diff=0`). Spot-check 10 leads: `data jsonb` == JSON object. |
| U7 | LEADS→PG (gated) | ONLY if §6.6 per-request tenant contextvar is wired AND shadow_diff=0: set `STORE_MODES=leads:pg`, restart. Else SKIP and leave leads at `dual` (acceptable P1 steady state). | `GET /leads` for vendorA returns ONLY vendorA leads (served from PG+RLS); admin sees all; create a lead → row in PG, served back. Then set leads back to `dual` (safe steady state) OR keep `pg` if the contextvar path proved clean. shadow_diff=0. Regression gate green. |
| U8 | ADMIN VISIBILITY | Add `GET /admin/store-status` + `GET /admin/shadow-diff?entity=` (admin-only, RBAC `manage_tenants`). | Both 200 for admin, 403 for vendor. store-status lists each store mode + pg ok/fail + last error; shadow-diff runs `shadow_diff.py` logic inline and returns the report. |
| U9 | BACKFILL REST + DUAL | `backfill.py` for orgs/users/memberships, campaigns, calls, suppression, retry_queue, webhooks(+log), wa_log/wa_threads, billing/ledger, usage_events/cost_ledger, events. `shadow_diff` each → 0. Flip the SAFE ones to `dual` (calls, suppression, retry_queue, webhooks, billing, ledger, usage_events, cost_ledger, events). Leave campaigns/transcripts/wa_threads at `json` (or campaigns `dual` read-only-mirror). | Each entity: `shadow_diff <entity>` exit 0. After dual flips, a `/run` cycle (suppression check, retry enqueue, ledger charge, cost rollup, audit row) writes JSON (authoritative, unchanged behavior) AND mirrors to PG (`pg_writes_fail=0`). Regression gate green. |
| U10 | RLS PROOF + INFRA | Run the §5 raw-SQL RLS proof. Install PgBouncer (`db/pgbouncer.ini`, transaction pooling, point `PG_DSN` at :6432) + apply `db/autovacuum.sql`. | RLS proof passes (vendor scope blocks cross-tenant SELECT/UPDATE; admin GUC sees all). App still green through PgBouncer (transaction-pooling compatible because we use `SET LOCAL` only, never session-level state). `SHOW pool_mode` = transaction. Autovacuum settings applied (`SELECT reloptions FROM pg_class WHERE relname='calls'`). |

PgBouncer note (§10 detail): we use **transaction** pooling. This is safe ONLY because every GUC is `SET LOCAL` (txn-scoped). Never introduce session-level `SET` (without LOCAL), prepared-statement reuse across txns, or advisory locks held across txns — they break transaction pooling. asyncpg + PgBouncer: disable client-side statement cache (`prepared_statement_cache_size=0` / `statement_cache_size=0`) to avoid the "prepared statement already exists" class of errors under transaction pooling.

---

## 10. PgBouncer + AUTOVACUUM PLAN

**PgBouncer** (`db/pgbouncer.ini`):
```ini
[databases]
famit = host=127.0.0.1 port=5432 dbname=famit
[pgbouncer]
listen_addr = 127.0.0.1
listen_port = 6432
auth_type = scram-sha-256   # ⚠ NOT md5 — see RED-TEAM B3. PG>=14 stores SCRAM verifiers by default.
auth_file = /etc/pgbouncer/userlist.txt
pool_mode = transaction
max_client_conn = 200
default_pool_size = 20
reserve_pool_size = 5
server_idle_timeout = 300
```
- `userlist.txt` holds the **SCRAM verifier** copied verbatim from `SELECT rolname, rolpassword FROM pg_authid WHERE rolname='famit_app'` (format `"famit_app" "SCRAM-SHA-256$…"`), NOT an md5 hash — see RED-TEAM B3. Discriminate at U1: read PG major from `select version()`; if ≥14 use `scram-sha-256` + SCRAM verifier (or `auth_query = SELECT rolname, rolpassword FROM pg_authid WHERE rolname=$1` with a dedicated lookup role); only fall back to `md5` if the cluster is somehow <14 / `password_encryption=md5`. App `PG_DSN` → `…@127.0.0.1:6432/famit`. asyncpg under transaction pooling: append `?prepared_statement_cache_size=0` **and** beware prepared-statement NAME collisions across pooled conns — prefer SQLAlchemy `poolclass=NullPool` on the async engine (PgBouncer owns the pool) or a unique prepared-statement-name function; `compiled_cache` does not need touching.
- Why transaction pooling is correct here: the entire tenant-scope mechanism is `SET LOCAL` (resets at txn end), so no per-session state survives a connection hand-off. This is the master-plan-mandated "PgBouncer at P1".

**Autovacuum** (`db/autovacuum.sql`) — tune the hot/append-heavy tables (calls, usage_events, cost_ledger, events, ledger, webhook_log grow fast):
```sql
ALTER TABLE calls        SET (autovacuum_vacuum_scale_factor=0.02, autovacuum_analyze_scale_factor=0.01);
ALTER TABLE usage_events SET (autovacuum_vacuum_scale_factor=0.02, autovacuum_analyze_scale_factor=0.01);
ALTER TABLE cost_ledger  SET (autovacuum_vacuum_scale_factor=0.02, autovacuum_analyze_scale_factor=0.01);
ALTER TABLE events       SET (autovacuum_vacuum_scale_factor=0.05);   -- insert-only, mostly needs ANALYZE + freeze
ALTER TABLE leads        SET (autovacuum_vacuum_scale_factor=0.05, autovacuum_analyze_scale_factor=0.02);
-- raise autovacuum workers/cost-limit at the instance level when on Managed PG (later); on the box keep defaults + per-table above.
```
- Rationale: default scale_factor 0.2 is too lax for append-heavy tables at SaaS volume → bloat + stale stats. Append-only `events` needs aggressive freeze (anti-wraparound) but little dead-tuple vacuum.
- When migrating to DO **Managed Postgres (blr)** (master plan target), these `ALTER TABLE` settings carry over; instance-level autovacuum workers are managed by DO.

> Scale trigger (from master plan, restate in build_log): at **>60k calls/day OR p95 lead-memory read >50ms**, FIRST split the orchestration DB from OLTP. P1 does not implement that — it just leaves the knobs (PgBouncer, per-table autovacuum) in place so the trigger is a config change, not a rewrite.

---

## 11. FEATURE FLAGS + ROLLBACK

Flags (all in `/opt/famit-agent/.env`, read via `config.get`):
- `PG_DSN` / `PG_DSN_ASYNC` — **absent ⇒ entire PG layer is a no-op, every store json.** The master kill-switch.
- `STORE_MODES` — comma list `name:mode` (e.g. `leads:dual,calls:dual`). Unlisted ⇒ json. Empty ⇒ all json.
- `STORE_PG_TIMEOUT_MS` — mirror write budget (default 800). 
- `MEMORY_TENANT_SCOPED` — `1` (default, the fix) / `0` (legacy flat).
- `LEGACY_TOKEN_ENABLED` — unchanged (P0); not flipped in P1.

Rollback ladder (fast → nuclear), each ~instant + non-destructive:
1. Bad behavior on one store → drop it from `STORE_MODES` (back to json) + restart caller. JSON was authoritative the whole time → zero data loss.
2. Any PG instability → blank `STORE_MODES` (all json) + restart. PG idle; site exactly as pre-P1.
3. Memory bleed-fix regression → `MEMORY_TENANT_SCOPED=0` + restart both → legacy flat behavior (the read-fallback already keeps both layouts working).
4. Nuclear → remove `PG_DSN` + restart → PG layer dark; `store.py` import-guarded; identical to today.
5. Code-level → restore the `*.p1bak.<ts>` of `caller.py`/`agent.py`/`memory.py` + restart. (Per-unit backups make this one-unit-granular.)

**Invariant that makes rollback safe:** JSON files remain WRITTEN AND AUTHORITATIVE for every store except a leads store explicitly flipped to `pg` (and even pg shadow-writes JSON until U-cutover proves stable). So at every step before U7, the JSON tree alone fully runs the product.

---

## 12. DEPENDENCIES + ENV

venv (`/opt/capsy-agent/.venv`): `sqlalchemy>=2.0`, `asyncpg`, `psycopg2-binary`, `alembic`, `greenlet`. System: `postgresql`, `postgresql-contrib`, `pgbouncer` (apt). `.env` additions (U1) listed in §11. No new frontend deps. No change to voice/LiveKit/SIP deps.

Order of dependency: U1(provision)→U2(schema needs db)→U3(store needs engine importable, but runs json so safe even if db down)→U4(memory, independent of PG; can even ship before U3 if desired)→U5/U6/U7(leads ladder)→U8(visibility)→U9(rest)→U10(RLS+infra). U4 (the bleed fix) is independent of the PG work and MAY be shipped first as a standalone win if the founder wants the security fix early.

---

## 13. MODEL ROUTING (for the implementing agent)

- **U1 PROVISION** — *haiku* (mechanical: run a script, pip, append env, verify markers). 
- **U2 SCHEMA (models + RLS DDL + alembic)** — *opus* (RLS/GUC correctness + lossless column design are subtle; get it right once).
- **U3 STORE SEAM** — *opus* (the riskiest unit; byte-identical pass-through + degrade-to-json correctness gates the whole phase).
- **U4 MEMORY RE-KEY** — *opus* (cross-service coordination caller↔agent↔memory + back-compat fallback; a security fix — no mistakes).
- **U5 leads→dual / U6 backfill / U9 backfill-rest** — *sonnet* (apply the spec'd pattern + run shadow_diff; mechanical once U3 exists).
- **U7 leads→pg (gated)** — *opus* (per-request tenant contextvar + RLS read path is the one place a tenant could see another's leads — highest blast radius).
- **U8 admin endpoints** — *sonnet*.
- **U10 RLS proof + PgBouncer + autovacuum** — *sonnet* for the infra configs; *opus* to author/verify the RLS proof script and confirm transaction-pooling safety.
- One-time *opus* review of the whole diff before declaring P1 done (RLS isolation + no-bleed are security-critical).

> Per the global rules: one agent per file/domain, sequential, each commits its unit before the next. `db/*` + `store.py` are P1-owned new files (no other session touches them). `caller.py`/`agent.py`/`memory.py` edits are surgical and must be done in the main thread or by a single owning agent — never two agents on caller.py at once.

---

## 14. WHAT P1 DELIBERATELY DOES **NOT** DO (scope fence)
- No pgvector / RAG tables (PHASE 2). No read replica / analytics DB split (triggered at >60k calls/day).
- No auth cutover to Postgres/Logto (PHASE 4) — tenants.json stays authoritative; orgs/users are a mirror.
- No pgmq / Hatchet (PHASE 3 async spine) — retry_queue stays JSON-authoritative (mirrored).
- No moving campaigns/transcripts/wa_threads to `pg` (agent-read / live-inbound stores stay file-served).
- No DO Managed Postgres migration yet (provision is local PG on the box first; Managed-PG move is a later, config-only DSN swap once the schema + app are proven).

---

## 15. FIRST 3 CONCRETE STEPS (start here)
1. **U1** — `scp` `_provision_pg.sh` to box, run it, confirm `PROVISION_OK`; pip the 5 deps into `/opt/capsy-agent/.venv`; back up `.env`, append the 5 P1 vars (all safe-default). Regression gate.
2. **U2** — author `db/engine.py` (import-safe, two engines, `session/asession` with `SET LOCAL` GUC), `db/models.py` (the §3 schema), `db/rls.sql` (§5); `alembic init` + `0001_init`; `alembic upgrade head`; verify `\dt` + `relforcerowsecurity=t`. App code still untouched → green.
3. **U3** — write `store.py` (registry + 3 modes + degrade-to-json), rewire the three seam funcs to shims + `store.init` at caller startup with `STORE_MODES` empty (all json); deploy; prove byte-identical `/leads`/`/calls` + all-200 regression. This is the gate the rest of the phase stands on.

---

## RED-TEAM FIXES (folded)

Adversarial principal review against live source (`droplet_work/caller.py`, `memory.py`, `auth.py`, `config.py`, `_provision_pg.sh`). All line claims in §0 re-verified. The strangler architecture is sound and the verdict stands; the following are correctness/safety fixes folded INTO the design (they do not change the strategy). **B1 and B2 are the headline: both silently defeat the `shadow_diff==0` cutover gate, which is the one thing that would let a build agent declare a store "cutover-ready" on a mirror that has actually diverged.**

- **B1 — [BLOCKING, folded into §6.4(b)/§6.5] Fire-and-forget `create_task` per write RACES and PERMANENTLY breaks `shadow_diff==0`.** Two rapid leads writes spawn mirror tasks A(snapshot S1) and B(S2=S1−Y). If B lands before A, PG settles on S1 (Y still present) while JSON is S2 — **persistent** drift, not transient lag (R8 does NOT cover this). It defeats the U6/U9 gate directly. FIX: removed `create_task`-per-write as the primary path; MANDATED a single long-lived per-store worker (started in `store.init`) fed by a depth-1 replace-on-full `asyncio.Queue` that always applies the LATEST snapshot and drops superseded ones. Because every write is a whole-file snapshot, last-snapshot-wins is correct AND coalesces burst cost. **Extra nuance found in source:** the two hot leads writers `_update_lead_status` (caller.py:850-858) and `_update_lead_after_call` (caller.py:894-908) call the sync `_write` **INSIDE `async with _STORE_LOCK`** — so the mirror trigger fires while holding the global store lock. The enqueue MUST be O(1) non-blocking (`put_nowait` + replace); an inline `await`/blocking PG call in the `_write` shim would serialize the entire dial loop behind the lock. The coalescing worker makes this safe.

- **B2 — [BLOCKING, folded into §6.4(a)] `DELETE FROM <t> WHERE id <> ALL(:ids)` wipes the table on an EMPTY snapshot.** `x <> ALL(ARRAY[]::text[])` is TRUE for every row in Postgres. A transient `_read` failure (returns the `default` `[]`) or a momentarily-empty file → reconcile DELETEs every PG row. Survivable in `dual` (JSON authoritative, mirror just trashed + shadow_diff spikes) but it is **real data loss in `pg` mode (U7)**. FIX: delete-by-omission is SKIPPED when the incoming id-set is empty while PG is non-empty; and the mirror NEVER reconciles from a `_read` that raised (distinguish "genuinely empty" from "read errored" — only the original `_read_raw` success path may drive a delete). Add to U6/U9 acceptance: after a mirror cycle, assert PG row-count did not drop to 0 unless JSON is legitimately empty.

- **B3 — [BLOCKING, folded into §10] PgBouncer `auth_type = md5` FAILS on the real box.** `_provision_pg.sh` does a bare `apt-get install postgresql` → PG 14 (Ubuntu 22.04) or 16 (24.04), both default `password_encryption = scram-sha-256`. The `famit_app` verifier in `pg_authid.rolpassword` is therefore a `SCRAM-SHA-256$…` string; an md5 `userlist.txt` can never match → every pooled connection auth-fails. This is the clearest "fails on the real box" item. FIX: `auth_type = scram-sha-256`; `userlist.txt` holds the SCRAM verifier copied verbatim from `pg_authid` (or use `auth_query`). Discriminate by PG major (from U1's `select version()`); md5 only if cluster is genuinely <14.

- **B4 — [BLOCKING, folded into §6 wiring] `_store` global must be `None` BEFORE import-time shim calls.** `_migrate_to_admin()` (caller.py:504) and `CALLS = _read(CALLS_FILE, [])` (caller.py:683) execute the rewritten shims AT IMPORT, before any `store.init` placed lower in the file. An unassigned `_store` → `NameError` → swallowed by `_migrate_to_admin`'s bare `except` (482) → the import-time admin-tenant_id backfill **silently no-ops**, and the U3 all-json gate stays GREEN (so the corruption is invisible to the gate). FIX: declare `_store = None` at module top (~259, next to `_STORE_LOCK`); shims guard `_store is not None`; assign `_store` only AFTER `init()` returns.

- **B-confirm — [folded into §6.5] `_awrite` is ENTIRELY DEAD in P1.** Verified: ZERO `await _awrite(...)` call sites in caller.py; leads/calls/suppression/retry all write via SYNC `_write` (492/501/817/858/908/1493/1505/2087/2105/3393); `_wa_thread_write` (1056) takes `_STORE_LOCK` directly rather than calling `_awrite`. The original spec framed §6.5 as "the awrite mirror path" — that path is never exercised. Reframed §6.5 as a complete-the-seam shim (identical mechanics to `write`, no second divergent mirror). Net: the P1 strangler seam is `_read`/`_write` only.

- **N1 — [NOTE, folded into §10/R4] asyncpg + SQLAlchemy under transaction pooling.** `prepared_statement_cache_size=0` alone is insufficient — prepared-statement NAME collisions across pooled conns still throw "prepared statement already exists". Prefer `poolclass=NullPool` on the async engine (PgBouncer owns pooling) or a unique-name function.

- **N2 — [NOTE] `.env` consumption confirmed, with one caveat.** `config.py:36 load_dotenv("/opt/famit-agent/.env", override=False)` loads the appended U1 vars at process start, BUT the optional Doppler overlay (config.py:84 `os.environ[k]=...`) wins if Doppler defines a key. U1 acceptance should assert `python -c "import config; print(bool(config.get('PG_DSN')))"` → `True` after restart, not merely "appended to .env".

- **N3 — [NOTE] §0 writer-line citations corrected.** The whole-list leads writers are caller.py **858 / 908 / 2087 / 2105** (+ migration writer 492), not "851/895" (those were the `_read` lines inside the lock blocks). Corrected in §6.4(a).

- **N4 — [NOTE] `db.available()` source-of-truth.** `store.mode_of` and the import-safe degrade both hinge on `db.available()` returning False when `PG_DSN` is unset OR the startup probe fails. Mirror `auth.py`'s `_ready` pattern exactly (set once in `init`, never raise on import). The startup probe MUST have its own short timeout — a hung TCP connect to a down PG at import would block `caller:app` from starting and take the live site down. Bound it (e.g. `connect_timeout=2`) and treat timeout as "unavailable → all json".

---

## OPEN RISKS / DECISIONS TO WATCH
- **R1 (leads→pg tenant scoping):** pure `pg` reads need the caller's tenant in a per-request contextvar so RLS filters correctly; until that's cleanly wired, leads steady-states at `dual` (PG mirrored, JSON served). Don't flip to `pg` to "look finished" — `dual` is a legitimate P1 end state. (U7 is explicitly gated.)
- **R2 (in-RAM CALLS list):** `caller.py:683 CALLS` + `record_call` mean calls can never be `pg` in P1 without rewriting that cache. Spec keeps calls at `dual` max. Don't let an agent "upgrade" calls to pg.
- **R3 (byte-identical fragility):** shadow_diff/md5 depend on `_write`'s exact `json.dumps(...indent=2,ensure_ascii=False)`. The `json` path must call the ORIGINAL writer untouched; never let store.py reserialize.
- **R4 (PgBouncer + asyncpg prepared statements):** transaction pooling breaks server-side prepared statements; must disable asyncpg statement cache **and** avoid prepared-statement name collisions (see RED-TEAM N1 → `NullPool` on the async engine). Also see RED-TEAM B3: `auth_type` must be `scram-sha-256`, not `md5`, on PG≥14. If unexplained "prepared statement does not exist / already exists" errors appear, this is why.
- **R5 (memory flat-file attribution):** existing `var/memory/<phone>.json` can't be safely attributed to a tenant, so they remain a READ-ONLY fallback that ages out — NOT bulk-migrated. Accept a brief window where an old shared memory is still readable by its original tenant only (the bleed is closed for all NEW writes immediately).
- **R6 (agent tenant_id source):** primary = dispatch metadata (caller change at 1644); fallback = `campaigns/<id>.json` `tenant_id`. If BOTH are somehow absent, memory falls back to flat (no bleed *introduced* vs today, just not yet scoped) — acceptable, logged.
- **R7 (DO Managed PG later):** local-PG-on-box is fine for P1 proof but is a SPOF on the voice box; the Managed-PG (blr) move (DSN swap + firewall) should follow soon after P1 — note it for PHASE 2 HA.
- **R8 (shadow_diff must run at quiescence):** the dual mirror is async, so JSON leads PG by a few ms during active traffic. Run `shadow_diff.py` / the U6/U9 gate with NO active campaign (`/run` idle) so a transient lag isn't misread as drift. `/admin/shadow-diff` should note "run when idle" and report active-job count. **NOTE: quiescence only hides TRANSIENT lag; it does NOT fix the RED-TEAM B1 last-writer-wins race, which is PERSISTENT drift. B1's coalescing worker is the actual fix — do not rely on R8 to mask a B1 regression.**
- **R9 (verify before backfilling `events`):** the audit JSONL path/line-format was taken from HANDOFF, not from `audit.py` source. Before writing the `events` backfill, open `audit.py` and confirm the file path (`var/audit_log.jsonl`) and the per-line keys (`actor/action/object_type/object_id/ip/channel/meta`). The deterministic PK hashes the RAW line, so format only affects the promoted columns, not idempotency.
- **R10 (campaign tenant_id on disk):** the agent's memory fallback `camp.get("tenant_id")` assumes `campaigns/<id>.json` carries `tenant_id` at TOP LEVEL. The API projection showing it isn't proof of on-disk shape — confirm by reading one `campaigns/<id>.json` on the box during U4. LOW risk: the PRIMARY path (dispatch metadata at caller.py:1644) supplies tenant_id regardless; the fallback only matters if metadata is ever missing.
