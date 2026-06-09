# Credit/Wallet Ledger + Action Firewall + AI-Decision Audit — Execution-Ready Design Spec

> **Status:** READY TO BUILD. Strangler / non-breaking / behind feature flags. Live system at
> `panel.famit.in` keeps earning untouched.
> **Box:** `famit@168.144.153.145` → `/opt/famit-agent/` (service `famit-caller`, uvicorn `caller:app :8209`).
> SSH: `ssh -i C:\Users\kunal\.ssh\do-blr-test\id_ed25519 famit@168.144.153.145`.
> venv: `/opt/capsy-agent/.venv` (py3.12.3). Local source of truth: `C:\Users\kunal\Desktop\caps\droplet_work\`.
> **Author:** staff-eng spec. A build agent implements this verbatim.

---

## 0. VERDICT & SCOPE (settled — do not relitigate)

This is the **one deliberate BUILD-don't-compose exception** in the OCEAN master plan: a narrow ACID
credit/wallet ledger for money custody (no OSS tool safely real-time-gates money; Lago only updates at
invoice finalization). Three subsystems, one wave:

1. **Wallet ledger** — 4 Postgres tables (`wallet_accounts`, `wallet_transactions`, `wallet_holds`,
   `wallet_idempotency`) that real-time-gate spend (calls / WhatsApp / ads) with **no double-spend** and
   **no oversell**, via atomic conditional `UPDATE` + holds (reserve→settle→release).
2. **Action Firewall** — PIN/OTP step-up gates on spend-sensitive + destructive actions, reusing the
   existing HS256 / `var/secret` signing already in `auth.py`.
3. **Immutable AI-decision audit ledger** — every AI decision (call outcome, autonomous spend, copilot
   CRUD) appended immutably, reusing the existing `audit.py` append-only JSONL + the agent→caller
   file-drain pattern, with money-mutating audit rows written in the **same DB transaction** as the charge.

### Why Postgres, not JSON (decisive)
The task names **ACID / holds / idempotency / no-double-spend** — a relational transactional design.
The current substrate physically cannot deliver it: `_STORE_LOCK = asyncio.Lock()` (`caller.py:259`) is
**single-process only**, and Phase 2 of the master plan adds a second app instance + DO load-balancer.
A JSON balance guarded by that lock silently loses its no-double-spend guarantee the moment it scales —
the exact latent money-custody bug the build-don't-compose carve-out exists to prevent. **Postgres,
committed.** No JSON fallback for the authoritative balance.

### What keeps it non-breaking (blast radius, stated explicitly)
The wallet is the **prepaid real-time-enforcement engine ONLY**.
- **Postpaid is today's default** for every existing tenant (`_default_billing` → `plan:"postpaid"`,
  `caller.py:1292-1296`). Postpaid needs no real-time gate — it accrues and bills in arrears.
- Therefore: **`WALLET_ENABLED` flag default OFF.** When OFF, or for any postpaid tenant, the code path
  is byte-identical to today: existing `_charge_call` (`caller.py:1336`) accrual + the existing `/run`
  402 gate (`caller.py:2134-2140`). The Postgres wallet governs **only** tenants explicitly moved to
  `plan:"prepaid_wallet"` AND only while the flag is ON.
- **Rollback = flip the flag** (`WALLET_ENABLED=false` in `.env` → restart). You are back to today.
- Decoupled from P1's risky migration: these 4 tables are **brand new** — they migrate no existing JSON
  store, so they need **none** of P1's `store.py` dual/shadow-diff machinery (P1 U3, "RISKIEST unit").
  They depend ONLY on Postgres being **provisioned** (P1 U1 — the safe part: `apt`, db, restricted role,
  DSN). They get their own schema + their own asyncpg engine, talking transactions directly.

---

## 1. DEPENDENCIES & PRE-FLIGHT

| Dep | State | Action |
|---|---|---|
| Postgres provisioned (db `famit`, restricted role `famit_app`, DSN in `.env`) | P1 U1 `IN PROGRESS` (`P1_FOUNDATION_STATE.md:46`) — **may not be done** | **Step 0 of this build is to confirm/finish it.** See Step 0. |
| `asyncpg` in venv | from P1 U1 | `pip show asyncpg`; if absent install (Step 0) |
| `alembic` in venv | from P1 U1 | used for migration; if absent, fall back to a raw idempotent DDL script (`db/ddl_wallet.sql`) run via psql — DDL is `CREATE TABLE IF NOT EXISTS`, safe to re-run |
| `PyJWT` in venv | DONE (P0, `auth.py` uses it) | reused by the firewall step-up token |
| `redis` 6380 | DONE (P0 ratelimit) | not required by wallet; OTP-rate-limit may reuse it later |
| `var/secret` | DONE (HMAC/JWT signing secret) | reused for firewall step-up token + PIN salt pepper |

**Pre-flight commands (run first, read-only):**
```bash
ssh -i C:\Users\kunal\.ssh\do-blr-test\id_ed25519 famit@168.144.153.145 \
  'systemctl is-active famit-caller famit-agent; \
   grep -c PG_DSN /opt/famit-agent/.env; \
   sudo -u postgres psql -lqt 2>/dev/null | grep -c famit; \
   /opt/capsy-agent/.venv/bin/python -c "import asyncpg,jwt;print(\"asyncpg+jwt ok\")"'
```
Interpretation: if `PG_DSN` count is 0 OR the `famit` db count is 0 → **P1 U1 is NOT done → do Step 0 fully**.

---

## 2. FILES TO CREATE / EDIT (exact paths)

All local edits in `C:\Users\kunal\Desktop\caps\droplet_work\`, then deploy by scp to
`famit@168.144.153.145:/opt/famit-agent/` + `sudo systemctl restart famit-caller` (+ `famit-agent` only
for the agent-side audit-drop unit).

### CREATE
| Path (local `droplet_work\`) | Purpose | Owner step |
|---|---|---|
| `wallet.py` | The ledger transactional core: asyncpg pool, `reserve()` / `settle()` / `release()` / `topup()` / `balance()`, atomic conditional UPDATE, idempotency, hold-TTL sweep. Import-safe degrade (no PG → `available()==False`, all calls no-op, flag forced OFF). | 2 |
| `db/ddl_wallet.sql` | Raw idempotent DDL (4 tables + indexes + RLS policies). Used directly OR as the body of the Alembic migration. | 1 |
| `db/migrations/` (alembic) | Alembic env + one migration `xxxx_wallet_ledger.py` wrapping the DDL. (Skip if alembic unavailable; use the .sql via psql.) | 1 |
| `firewall.py` | Action Firewall: `mint_step_up(tenant, scope)` / `verify_step_up(request, scope)` (HS256 step-up token, `amr:pin`, short TTL), PIN set/verify (hashed like `pass_hash`), `require_step_up(scope)` FastAPI-style guard mirroring `can()`. OTP-over-WhatsApp stub (dormant). | 4 |
| `aidecision.py` | Thin helper around `audit.py.record(...)` for `channel="ai"` decision rows + `drain_ai_decisions()` that folds `var/ai_decisions_raw/<room>.json` into the audit log (reuses the `_drain_usage_raw` pattern). | 5 |
| `WALLET_FIREWALL_STATE.md` | Per-unit IN PROGRESS/DONE ledger (crash-safe resume). Created at Step 0, updated every step. | 0 |

### EDIT
| Path | Edit | Owner step |
|---|---|---|
| `caller.py` | (a) import `wallet`, `firewall`, `aidecision` defensively; (b) `init()` calls in startup; (c) **hold gate** in `run_job` dial loop (~line 1634, beside existing per-call gates); (d) **settle** in `_finalize_call` (~1495, replacing/wrapping `_charge_call` for wallet tenants); (e) **release** of leftover hold in finalize + on failed-dial; (f) hold-TTL sweep call in `scheduler_loop` (~3300); (g) new endpoints `/wallet*`, `/firewall/*`, extend `/billing` config to set `plan:"prepaid_wallet"`; (h) wrap destructive/spend endpoints with `require_step_up`. | 3,4 |
| `agent.py` | Drop a per-room AI-decision file `var/ai_decisions_raw/<room>.json` at call end (outcome/interest/next_action/opt_out + any autonomous decision), mirroring how it already drops usage-raw + transcript. **No DB connection in agent.py.** | 5 |
| `/opt/famit-agent/.env` (box only, NOT git) | Append `WALLET_ENABLED=false`, `PG_DSN_ASYNC=...`, `FIREWALL_ENABLED=false`, `WALLET_HOLD_TTL_S=900`, `WALLET_DEFAULT_RATE_PER_MIN=...`. Back up `.env` first. | 0,3,4 |

---

## 3. SCHEMA (db/ddl_wallet.sql) — the 4 tables

> Currency = **integer minor units (paise)**. NEVER float for money. `balance_minor BIGINT`.
> All money math is integer. (Display layer divides by 100.)
> `tenant_id TEXT` = the existing tenant id (== org_id), matching `tenants.json` ids.

```sql
-- ============ wallet ledger (BUILD-don't-compose ACID core) ============
-- Money in INTEGER MINOR UNITS (paise). No floats. One account row per (tenant, currency).

CREATE TABLE IF NOT EXISTS wallet_accounts (
    tenant_id       TEXT        NOT NULL,
    currency        TEXT        NOT NULL DEFAULT 'INR',
    -- available = spendable now (already net of active holds). held = sum of open holds.
    available_minor BIGINT      NOT NULL DEFAULT 0,
    held_minor      BIGINT      NOT NULL DEFAULT 0,
    -- lifetime counters for audit/reconcile (never decremented)
    lifetime_topup_minor   BIGINT NOT NULL DEFAULT 0,
    lifetime_spend_minor   BIGINT NOT NULL DEFAULT 0,
    version         BIGINT      NOT NULL DEFAULT 0,   -- optimistic-concurrency / debug
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, currency),
    CONSTRAINT wallet_available_nonneg CHECK (available_minor >= 0),
    CONSTRAINT wallet_held_nonneg      CHECK (held_minor >= 0)
);

-- Immutable, append-only money movements. The audit trail of every credit/debit.
-- kind: topup | hold | hold_settle | hold_release | charge | refund | adjust
CREATE TABLE IF NOT EXISTS wallet_transactions (
    id            BIGSERIAL    PRIMARY KEY,
    tenant_id     TEXT         NOT NULL,
    currency      TEXT         NOT NULL DEFAULT 'INR',
    kind          TEXT         NOT NULL,
    amount_minor  BIGINT       NOT NULL,            -- signed: +credit / -debit to available
    held_delta_minor BIGINT    NOT NULL DEFAULT 0,  -- signed change to held_minor
    -- linkage to the spend event + its hold (nullable for topup/adjust)
    resource_type TEXT         NOT NULL DEFAULT '', -- call | whatsapp | ads | manual
    resource_id   TEXT         NOT NULL DEFAULT '', -- call_id / message_id / campaign spend id
    hold_id       BIGINT       NULL,
    idempotency_key TEXT       NULL,
    balance_after_minor BIGINT NOT NULL,            -- available_minor AFTER this row (snapshot)
    actor         TEXT         NOT NULL DEFAULT '',
    meta          JSONB        NOT NULL DEFAULT '{}'::jsonb,
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_wtx_tenant_time ON wallet_transactions (tenant_id, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_wtx_resource    ON wallet_transactions (resource_type, resource_id);

-- Open reservations against a balance (a call/WA/ads in flight). state machine.
-- state: open -> settled | released | expired
CREATE TABLE IF NOT EXISTS wallet_holds (
    id            BIGSERIAL    PRIMARY KEY,
    tenant_id     TEXT         NOT NULL,
    currency      TEXT         NOT NULL DEFAULT 'INR',
    amount_minor  BIGINT       NOT NULL,            -- reserved estimate (>0)
    state         TEXT         NOT NULL DEFAULT 'open',
    resource_type TEXT         NOT NULL DEFAULT '',
    resource_id   TEXT         NOT NULL DEFAULT '', -- the call_id etc. this hold guards
    settled_minor BIGINT       NULL,                -- actual charged at settle
    expires_at    TIMESTAMPTZ  NOT NULL,            -- TTL; sweep releases if still open past this
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT now(),
    closed_at     TIMESTAMPTZ  NULL,
    CONSTRAINT wallet_hold_amt_pos CHECK (amount_minor > 0)
);
CREATE INDEX IF NOT EXISTS ix_hold_open ON wallet_holds (state, expires_at) WHERE state = 'open';
CREATE INDEX IF NOT EXISTS ix_hold_resource ON wallet_holds (resource_type, resource_id);

-- Idempotency: makes reserve/settle/topup safe to retry / replay. Key per (tenant, op, dedup-id).
-- A second call with the same key returns the FIRST result, never re-applies the money move.
CREATE TABLE IF NOT EXISTS wallet_idempotency (
    idem_key      TEXT         PRIMARY KEY,        -- e.g. "settle:call:<call_id>"
    tenant_id     TEXT         NOT NULL,
    op            TEXT         NOT NULL,           -- reserve | settle | release | topup
    result        JSONB        NOT NULL,           -- the stored response to replay
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT now()
);

-- ============ RLS (twice-enforced isolation, matching P1 pattern) ============
-- App connects as restricted role famit_app (NOT owner). Per-request: SET LOCAL app.tenant_id.
ALTER TABLE wallet_accounts     ENABLE ROW LEVEL SECURITY;
ALTER TABLE wallet_accounts     FORCE  ROW LEVEL SECURITY;
ALTER TABLE wallet_transactions ENABLE ROW LEVEL SECURITY;
ALTER TABLE wallet_transactions FORCE  ROW LEVEL SECURITY;
ALTER TABLE wallet_holds        ENABLE ROW LEVEL SECURITY;
ALTER TABLE wallet_holds        FORCE  ROW LEVEL SECURITY;
ALTER TABLE wallet_idempotency  ENABLE ROW LEVEL SECURITY;
ALTER TABLE wallet_idempotency  FORCE  ROW LEVEL SECURITY;

-- policy: a row is visible/mutable only when its tenant_id == current_setting('app.tenant_id').
-- An admin bypass is handled in-app by setting app.tenant_id to the row's tenant for admin ops,
-- NOT by a superuser connection. (Mirrors P1's restricted-role + GUC design.)
DO $$
DECLARE t TEXT;
BEGIN
  FOREACH t IN ARRAY ARRAY['wallet_accounts','wallet_transactions','wallet_holds','wallet_idempotency']
  LOOP
    EXECUTE format(
      'DROP POLICY IF EXISTS rls_tenant ON %I; '
      'CREATE POLICY rls_tenant ON %I USING (tenant_id = current_setting(''app.tenant_id'', true)) '
      'WITH CHECK (tenant_id = current_setting(''app.tenant_id'', true));', t, t);
  END LOOP;
END $$;

GRANT SELECT, INSERT, UPDATE ON wallet_accounts, wallet_transactions, wallet_holds, wallet_idempotency TO famit_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO famit_app;
```

---

## 4. THE TRANSACTIONAL CORE (wallet.py) — exact semantics

> **Two correctness invariants. If the spec violates either, the money is subtly broken. Non-negotiable.**

### INVARIANT 1 — no oversell via ONE atomic conditional UPDATE (never read-check-write)
`reserve()` MUST be a single statement that both checks and decrements:
```sql
UPDATE wallet_accounts
   SET available_minor = available_minor - $amt,
       held_minor      = held_minor + $amt,
       version         = version + 1,
       updated_at      = now()
 WHERE tenant_id = $t AND currency = $c AND available_minor >= $amt
 RETURNING available_minor, version;
```
- 0 rows returned ⇒ **insufficient funds** ⇒ reserve fails (caller refuses the spend). No race window.
- Run inside a txn that also `INSERT`s the `wallet_holds` row + a `wallet_transactions` `kind='hold'`
  row, then `COMMIT`. The `CHECK (available_minor >= 0)` constraint is the belt-and-suspenders backstop.
- If the spec ever says "SELECT balance; if balance >= amt: UPDATE" → **WRONG**, the race is back.

### INVARIANT 2 — settlement is idempotent, keyed by the resource id (`call_id`)
`settle(hold_id, actual_minor, idem_key="settle:call:<call_id>")`:
1. `INSERT INTO wallet_idempotency(idem_key,...) ... ON CONFLICT (idem_key) DO NOTHING RETURNING idem_key`.
   - If **no row returned** (conflict) → this settle already ran → `SELECT result` and **return it; apply
     nothing**. This is the double-charge guard.
2. Else, in the same txn: load the hold `FOR UPDATE`; if `state != 'open'` return its stored outcome.
   Compute `actual = min(actual_minor, hold.amount_minor)` (never charge more than reserved — extra is a
   separate `charge` op with its own gate); `refund = hold.amount_minor - actual`.
   - `held_minor -= hold.amount_minor` (release the whole reservation),
   - `available_minor += refund` (return the unspent remainder),
   - `lifetime_spend_minor += actual`,
   - hold `state='settled', settled_minor=actual, closed_at=now()`,
   - append `wallet_transactions` rows: `kind='hold_settle'` (held_delta = -hold.amount), `kind='charge'`
     (amount = -actual is already reflected; record the real spend + `balance_after`),
   - store the result JSON in `wallet_idempotency`. COMMIT.

**Why idempotency is load-bearing DAY ONE (verified against live code):** The scheduler reconciliation
sweep (`caller.py:3333-3393`) re-reconciles any `done` call lacking `_reconciled` once its transcript
lands. **Confirmed: that sweep does NOT currently call `_charge_call`** (settlement happens once, in
`_finalize_call:1495`). So today's accrual ledger does not double-charge. BUT for the wallet:
- finalize can be reached more than once across a process restart / crash-replay of an in-flight call;
- a future change could route settlement through the sweep for a more-accurate post-transcript duration.
Either path would double-charge a real balance without the idempotency table. So the 4th table is
**load-bearing from day one**, and `settle` MUST be idempotent on `call_id`. (This is the concrete,
in-codebase justification for the idempotency table — not a theoretical nicety.)

### release(hold_id) — unused/leftover reservation
For a hold that should be voided (failed dial before any spend, expired hold, leftover after settle is
handled inside settle): in one txn, if hold `state='open'`: `held_minor -= amount`,
`available_minor += amount`, hold `state='released', closed_at=now()`, append `kind='hold_release'`.
Idempotent via `release:<resource_type>:<resource_id>` key.

### topup(tenant, amount_minor, actor, idem_key) — admin/payment credit
`available_minor += amount`, `lifetime_topup_minor += amount`, append `kind='topup'`. Idempotent on
`topup:<payment_ref>` (so a Razorpay webhook retry can't double-credit).

### Hold-estimate policy (define it, don't hand-wave)
For a CALL: `estimate_minor = ceil(max_call_seconds/60) * rate_per_min_minor + rate_per_call_minor`,
where `max_call_seconds = WALLET_MAX_CALL_S` (default 600 = 10 min, env-tunable) and rates come from the
tenant billing record (`_billing_for`, `caller.py:1305`). This caps worst-case exposure per call; settle
returns the unspent remainder. For WhatsApp: a flat per-message estimate. For ads: hold the requested
spend cap; settle on the platform's reported actual (async — settle when the ads API reports, NOT at
request time).

### Hold-TTL release sweep (crash-safety unit)
A crashed/lost call would otherwise leak its hold and wedge the balance forever. Reuse the existing
60-second `scheduler_loop` (`caller.py:3298`): each tick, `SELECT id FROM wallet_holds WHERE state='open'
AND expires_at < now()` → `release()` each (idempotent). `expires_at = now() + WALLET_HOLD_TTL_S` (default
900s) set at reserve. This is the subsystem's explicit crash-safety mechanism.

### asyncpg engine + RLS GUC (pooled-conn leak guard)
- One module-global `asyncpg.create_pool(dsn=PG_DSN_ASYNC, min_size=1, max_size=8)` created on `init()`.
- **Every** wallet op acquires a connection and runs, as the FIRST statement in its txn,
  `await con.execute("SELECT set_config('app.tenant_id', $1, true)", tenant_id)` (`true` = LOCAL, scoped
  to the txn — prevents GUC leak across pooled reuse, matching P1's `SET LOCAL` design).
- For admin cross-tenant reads, set `app.tenant_id` to the target tenant per query (no superuser conn).
- **Import-safe degrade:** if `PG_DSN_ASYNC` unset OR pool creation fails at `init()` →
  `wallet.available()` returns False; **every wallet entrypoint becomes a no-op that signals "unavailable"
  so caller.py forces the postpaid/legacy path** and `WALLET_ENABLED` is treated as OFF. The live site
  never breaks because Postgres is down.

---

## 5. INTEGRATION SEAMS IN caller.py (exact lines)

### Seam A — admission gate stays, hold gate is the real gate (per-dial)
- The `/run` 402 check (`caller.py:2134-2140`) is **coarse admission only** (balance<=0). KEEP it as a
  fast fail, but extend its condition: for `plan in ("prepaid","prepaid_wallet")` AND wallet ON, do a
  cheap `wallet.balance(tenant) <= 0` pre-check (same 402 shape). Concurrent spend happens per-dial, so:
- **The real gate is the HOLD in the dial loop**, placed beside the existing per-call gates at
  `caller.py:1634-1640` (per-tenant concurrency cap + daily cap), **before** `create_room` /
  `create_sip_participant` (`caller.py:1656-1659`):
  ```python
  # WALLET: reserve funds for this call BEFORE dialing (only for wallet tenants + flag ON).
  hold_id = None
  if WALLET_ENABLED and _wallet_plan(tenant):
      hold_id = await wallet.reserve(tenant_id, _call_estimate_minor(camp_fields, tenant),
                                     resource_type="call", resource_id=<future call_id>,
                                     idem_key=f"reserve:call:{<call_id>}")
      if hold_id is None:        # insufficient funds -> skip this lead, mark + record
          it["status"] = "no_funds"; idx += 1
          record_call({... "status":"no_funds","outcome":"insufficient_balance" ...})
          continue
  ```
  Generate the `call_id` (`uuid.uuid4().hex[:10]`) BEFORE the reserve so the hold, the call rec, and the
  settle idem-key all share it. Stash `hold_id` on `it["_hold_id"]` and on the call rec.

### Seam B — settle on finalize (the single settlement touch-point)
- In `_finalize_call` (`caller.py:1472`), the existing line `await _charge_call(tenant_id, rec)`
  (`caller.py:1495`) becomes a branch:
  ```python
  if WALLET_ENABLED and _wallet_plan_for(tenant_id) and rec.get("_hold_id"):
      actual_minor = _actual_call_cost_minor(rec)   # real cost: cost_ledger if present, else duration*rate
      await wallet.settle(rec["_hold_id"], actual_minor,
                          idem_key=f"settle:call:{rec['id']}")   # idempotent on call_id
  else:
      await _charge_call(tenant_id, rec)            # UNCHANGED legacy accrual path (postpaid/flag OFF)
  ```
- `duration_s` is already computed in finalize (`now_t - launched_at`, `caller.py:1480`) so actual cost is
  available at settle time — no need to defer to the reconcile sweep.

### Seam C — release on failed dial
- In the dial-loop `except` (`caller.py:1676-1682`, dial raised) and on the `no_funds` path: if a
  `hold_id` was taken, `await wallet.release(hold_id, idem_key=f"release:call:{call_id}")`. (Dial failed
  → nothing was spent → return the whole reservation.)

### Seam D — TTL sweep wired into scheduler_loop
- In `scheduler_loop` (`caller.py:3298`), add one call per tick (guarded by `WALLET_ENABLED`):
  `await wallet.sweep_expired_holds()`.

### Seam E — startup init
- Near the other `init()` calls in caller.py startup, add (defensive try/except, never raise):
  ```python
  try:
      import wallet, firewall, aidecision
      wallet.init(os.getenv("PG_DSN_ASYNC",""))            # async pool; degrades if absent
      firewall.init(SECRET, VAR/"pins.json")               # reuse var/secret + a pins store
      aidecision.init(VAR/"ai_decisions_raw", audit)       # reuse audit.py
  except Exception: ...  # site must start even if wallet import fails
  ```

---

## 6. ACTION FIREWALL (firewall.py) — step-up gate

Reuse, don't reinvent: the HS256 + `var/secret` machinery is already in `auth.py` (`_make_access`,
`_jwt.encode/decode`). The firewall mints a **short-TTL step-up token** proving a recent PIN/OTP.

- **PIN store** `var/pins.json`: `{tenant_id: {salt, pin_hash, set_at}}`, `pin_hash = sha256(salt+":"+pin)`
  — identical hashing to the existing tenant `pass_hash` (HANDOFF: "salted sha256"). Never store the PIN.
- `POST /firewall/pin` (X-Auth, self) form `pin` → set/replace own PIN. Audited.
- `POST /firewall/step-up` (X-Auth) form `pin` (or later `otp`) → on match, mint
  `step_up = jwt.encode({sub:tenant_id, amr:"pin", scope:"spend", exp:now+300}, SECRET, HS256)` →
  `{step_up_token, expires_in:300}`. On miss → 401 + audited `firewall.stepup.fail` (rate-limit via the
  existing redis token bucket; lockout after N misses).
- `require_step_up(request, scope)` — a guard mirroring `can(tenant, action)` (`caller.py:561`): reads
  `X-Step-Up` header, verifies HS256 + `scope` + exp; missing/invalid → **403** `{error:"step-up
  required","scope":...}`. Returns None (proceed) on success.
- **Gated actions** (wrap these endpoints with `require_step_up(scope="spend")` / `"destructive"`, only
  when `FIREWALL_ENABLED` AND tenant has a PIN set — otherwise pass-through so nothing breaks today):
  - spend scope: `POST /wallet/topup` (admin set balance is admin+step-up), large `POST /run` above a
    configurable spend threshold, autonomous-ads spend (future), `POST /whatsapp/send` bulk.
  - destructive scope: `DELETE /tenants/{id}` (future), `DELETE /campaigns/{id}` bulk, billing-plan
    change `POST /billing/{tid}`.
- **OTP-over-WhatsApp**: stub `request_otp()/verify_otp()` now (returns `not_configured`), live when the
  dormant Meta WA pipeline (HANDOFF WAVE A2) is enabled. Same `amr:"otp"` step-up token shape.
- **Flag:** `FIREWALL_ENABLED=false` default. OFF → `require_step_up` always returns None (no gating).

---

## 7. IMMUTABLE AI-DECISION AUDIT LEDGER (aidecision.py)

Reuse the existing immutable substrate (`audit.py` append-only JSONL, `record()`), add an AI channel +
the agent→caller drain (agent runs in a separate process; **no DB connection in agent.py**).

- **agent.py** at call end writes `var/ai_decisions_raw/<room>.json` =
  `{room, outcome, interest, next_action, opt_out, callback_at, model, variant_id, decided_at, [autonomous
  actions...]}` — mirrors how it already drops `usage_events_raw/<room>.json` + the transcript.
- **aidecision.drain_ai_decisions()** (called each `scheduler_loop` tick, like `_drain_usage_raw`,
  `caller.py:1415`): for each raw file whose `room` resolves to a known call rec, emit one
  `audit.record(actor=tenant_id, action="ai.decision", object_type="call", object_id=call_id,
  channel="ai", meta={...})`, then unlink the file. Tenant attribution via `_call_by_room`
  (`caller.py:1409`).
- **Money-mutating AI decisions** (autonomous spend the AI initiates): the audit row MUST be written in
  the **same asyncpg transaction** as the `wallet_transactions` row (add an `audit_event` insert into a
  small PG table OR pass the audit line through within the wallet txn) so audit can never diverge from the
  charge. For non-money AI decisions, the JSONL channel is sufficient.
- `GET /audit?channel=ai` already supported by `audit.py.tail` shape (extend the existing `/audit`
  endpoint's filter to accept `channel`). Read-only, admin=all / vendor=own, newest-first (unchanged).

---

## 8. NEW / CHANGED ENDPOINTS (strict contract)

All `X-Auth` (or JWT), tenant-scoped, RBAC via `can()`; admin sees all. Additive — no existing endpoint
changes shape.

| Method · Path | Auth | Body / Query | Returns |
|---|---|---|---|
| `GET /wallet` | self | — | `{tenant_id,currency,available,held,plan,lifetime_topup,lifetime_spend}` (major units) |
| `GET /wallet/transactions?limit=100` | self | — | `{transactions:[{id,kind,amount,resource_type,resource_id,balance_after,at}],total}` |
| `GET /wallet/holds?state=open` | self | — | `{holds:[{id,amount,state,resource_type,resource_id,expires_at}]}` |
| `POST /wallet/topup/{tenant_id}` | **admin** + step-up | form `amount`,`payment_ref`(idem) | updated `/wallet` body. 402-safe. |
| `POST /billing/{tenant_id}` (EXTEND existing `caller.py:~2470`) | admin + step-up | add `plan:"prepaid_wallet"` accepted | seeds a `wallet_accounts` row (0 balance) when switching a tenant to wallet plan |
| `POST /firewall/pin` | self | form `pin` | `{ok:true}` |
| `POST /firewall/step-up` | self | form `pin` | `{step_up_token,expires_in}` / 401 |
| `GET /firewall/status` | self | — | `{pin_set:bool, firewall_enabled:bool}` |
| `GET /audit?channel=ai` (EXTEND existing) | admin/self | `channel`,`action`,`limit`,`offset` | existing audit shape, filtered |
| `POST /run` (EXTEND) | — | — | new refusal: **402** `{error:"insufficient balance"...}` already exists; the per-dial hold may also mark leads `no_funds` in `/status` |

---

## 9. STEP ORDER (each: one verifiable unit, deploy, test, record, commit — NEVER batch)

> Write `WALLET_FIREWALL_STATE.md` first; flip each unit IN PROGRESS→DONE as it verifies.
> After EACH unit: back up the box file (`cp x x.walletbak.$(date +%s)`), deploy, run the unit's
> ACCEPTANCE TEST, append to `build_log/wave-wallet-firewall.md`, commit.

### STEP 0 — Postgres provisioned + DSN (prereq; may already be P1 U1)
**Do:** Confirm `famit` db + restricted role `famit_app` + `PG_DSN`/`PG_DSN_ASYNC` in `.env`. If missing,
provision per `P1_FOUNDATION_STATE.md:28-30` (apt postgresql; `CREATE DATABASE famit`; `CREATE ROLE
famit_app LOGIN PASSWORD ... NOSUPERUSER`; `GRANT`; FORCE-RLS-capable). `pip install asyncpg alembic` in
the venv if absent. Append `WALLET_ENABLED=false FIREWALL_ENABLED=false WALLET_HOLD_TTL_S=900
WALLET_MAX_CALL_S=600` to `.env` (backup `.env` first).
**ACCEPTANCE:** `python -c "import asyncpg,asyncio; asyncio.run(asyncpg.connect('<PG_DSN_ASYNC>').close())"`
prints nothing + exit 0; `systemctl is-active famit-caller famit-agent` = active (untouched). Site
`curl -s -o /dev/null -w '%{http_code}' https://panel.famit.in/api/health` = 200.
**ROLLBACK:** none needed (no app change). **MODEL: sonnet.**

### STEP 1 — Schema (DDL + migration), no behavior change, flag OFF
**Do:** Create `db/ddl_wallet.sql` (Section 3). Apply via alembic migration OR `sudo -u postgres psql
famit -f ddl_wallet.sql` (CREATE IF NOT EXISTS → re-runnable). Grant to `famit_app`.
**ACCEPTANCE:** `\dt wallet_*` shows 4 tables; `\d wallet_accounts` shows the CHECK constraints;
`SELECT * FROM pg_policies WHERE tablename LIKE 'wallet_%'` shows 4 `rls_tenant` policies;
inserting a row as `famit_app` WITHOUT `app.tenant_id` set returns 0 rows on select (RLS active). No
caller.py change yet → site + services unaffected (re-curl /health = 200).
**ROLLBACK:** `DROP TABLE wallet_* CASCADE` (no app depends on them yet). **MODEL: sonnet** (DDL only).

### STEP 2 — wallet.py transactional core + the OVERSELL TEST (the hard unit)
**Do:** Implement `wallet.py` (Section 4): pool, `init/available`, `reserve/settle/release/topup/balance/
sweep_expired_holds`, atomic conditional UPDATE, idempotency, `SET LOCAL app.tenant_id`. Import into
caller.py defensively (Seam E) but **wire NO endpoints/gates yet** — flag still OFF, zero behavior change.
**ACCEPTANCE (must ship WITH this unit — this is the proof of no-oversell, not a "charge works" test):**
write `tests/test_wallet_concurrency.py` run by `/opt/capsy-agent/.venv/bin/python`:
1. topup a test tenant to cover exactly **N** charges; fire **3N concurrent** `reserve()+settle(full)`
   coroutines (`asyncio.gather`) → assert **exactly N succeed**, `available_minor` ends `>= 0` and never
   went negative, `held_minor` ends 0.
2. settle the **same `call_id` twice** → balance debited **once** (idempotency hit).
3. reserve then let TTL pass (set `expires_at` in the past) → `sweep_expired_holds()` releases it →
   `available_minor` restored, hold `state='expired'/'released'`.
Run against the live Postgres using a throwaway tenant id `wallettest`; **DELETE its rows after**
(`DELETE FROM wallet_* WHERE tenant_id='wallettest'`). Live site untouched (flag OFF, no caller.py gate).
**ROLLBACK:** remove the import (no-op since unwired). **MODEL: opus** (concurrency reasoning + the
oversell test must ship together — do NOT split the core from its concurrency test).

### STEP 3 — wire hold/settle/release/sweep behind WALLET_ENABLED, ON for ONE test tenant
**Do:** Seams A–D in caller.py. Create a prepaid-wallet test tenant; `POST /wallet/topup`; set
`WALLET_ENABLED=true` (box `.env`) restart. **All existing tenants are postpaid → still on the legacy
path; only the test tenant hits the wallet.**
**ACCEPTANCE (on the live box, one real metered call to the test tenant):**
- top up test tenant ₹50; `/run` one lead to `6375548830` → `/wallet/holds` shows an `open` hold
  immediately; after the call, `/wallet/transactions` shows `hold` then `hold_settle`+`charge`, `held`
  back to 0, `available` reduced by the real call cost only (remainder refunded).
- drain balance below the per-call estimate → next `/run` lead marked `no_funds` in `/status`, **no SIP
  call placed**, `available` unchanged.
- **Regression (the non-breaking proof):** a normal **admin/postpaid** `/run` to the same number still
  dials and still accrues via the untouched `_charge_call` (check `var/ledger/admin.json` grew, NOT a
  wallet hold). `/campaigns /stats /billing/overview /me` all 200. `famit-caller`+`famit-agent` active.
- kill the box mid-call (or simulate: leave a hold open, advance `expires_at`) → TTL sweep releases it
  within one scheduler tick; balance not wedged.
**ROLLBACK:** `WALLET_ENABLED=false` + restart → instantly back to legacy accrual for everyone.
**MODEL: opus** (it owns the gate placement + crash-safety; same engineer as Step 2).

### STEP 4 — Action Firewall (firewall.py) behind FIREWALL_ENABLED, OFF by default
**Do:** Implement `firewall.py` + `/firewall/*` endpoints + wrap the gated spend/destructive endpoints
with `require_step_up` (pass-through when flag OFF or no PIN). Reuse `auth.py` HS256/`var/secret`.
**ACCEPTANCE:** with `FIREWALL_ENABLED=true` + a PIN set on the test tenant: `POST /run` above the spend
threshold WITHOUT `X-Step-Up` → **403** `{error:"step-up required"}`; `POST /firewall/step-up` with the
right PIN → token; same `/run` WITH `X-Step-Up` → proceeds; wrong PIN → 401 + an audit row
`firewall.stepup.fail`. Flag OFF → all the same calls pass (no gating). Legacy admin flows unaffected.
**ROLLBACK:** `FIREWALL_ENABLED=false`. **MODEL: sonnet.**

### STEP 5 — AI-decision audit (aidecision.py + agent.py drop + drain)
**Do:** agent.py drops `var/ai_decisions_raw/<room>.json` at call end; `aidecision.drain_ai_decisions()`
in `scheduler_loop`; extend `/audit` with `channel` filter; money-mutating AI rows written in the wallet
txn (Section 7). Deploy agent.py too (`restart famit-agent`).
**ACCEPTANCE:** a real call → after one scheduler tick, `GET /audit?channel=ai` shows one `ai.decision`
row for that call_id with outcome/interest in `meta`; the raw file is consumed (gone). No transcript /
metering / voice regression (the agent already drops 2 other per-room files; this is a 3rd, same pattern).
Voice latency unchanged (file write only, no network).
**ROLLBACK:** stop draining (rows just accumulate harmlessly) / revert agent.py from `*.walletbak.*`.
**MODEL: sonnet** (mechanical, mirrors `_drain_usage_raw`); **opus** only for the same-txn money-audit
coupling if it proves fiddly.

### STEP 6 — Frontend (separate agent, against `caps/famit-panel`)
**Do:** Wallet page (`GET /wallet` card + `/wallet/transactions` table + admin top-up form handling 402);
firewall PIN-set + step-up modal (intercept 403 `step-up required` → prompt PIN → retry with `X-Step-Up`);
AI-decision audit view (`GET /audit?channel=ai`). `lib/api.ts` wrappers. Build `npm install
--legacy-peer-deps && npm run build` until exit 0; deploy per HANDOFF recipe.
**ACCEPTANCE:** login → Wallet page renders balance; admin top-up reflects; a gated action triggers the
PIN modal then succeeds; build green; `panel.famit.in` 200. **MODEL: sonnet.**

---

## 10. FEATURE FLAGS & ROLLBACK (summary)

| Flag (box `.env`) | Default | ON effect | Rollback |
|---|---|---|---|
| `WALLET_ENABLED` | `false` | wallet governs `prepaid_wallet` tenants (hold/settle/gate) | set `false` + restart → legacy accrual for all |
| `FIREWALL_ENABLED` | `false` | step-up required on gated actions (tenants with a PIN) | set `false` + restart → no gating |
| per-tenant `plan` | `postpaid` | only `prepaid_wallet` tenants use the wallet | set tenant back to `postpaid` |
| `PG_DSN_ASYNC` unset / PG down | — | `wallet.available()=False` → forced legacy path | inherent safe degrade |

**Global invariant:** with all flags at default, the system is **byte-for-byte today's behavior** — every
existing (postpaid) tenant, the voice path, and all current endpoints are untouched. Ship dark, enable per
test tenant, expand.

---

## 11. RISKS / OPEN ITEMS

1. **P1 U1 not done** → Step 0 is the gate. If Postgres can't be provisioned this session, STOP after a
   schema-design commit; do NOT ship a JSON wallet (it cannot satisfy no-oversell under the Phase-2
   2-instance topology — that's the whole reason this is build-don't-compose).
2. **Actual call cost at settle:** the real per-call vendor cost (`cost_ledger`) may land slightly AFTER
   finalize (usage drain lag, HANDOFF WAVE A). MVP settles on `duration_s × tenant rate_per_min` (always
   available); a later refinement can true-up via a `kind='adjust'` row once `cost_ledger` reconciles.
   Document this as an explicit MVP simplification, not a bug.
3. **RLS + asyncpg pool GUC leak:** every op MUST `SET LOCAL app.tenant_id` inside its txn. A missed one
   = cross-tenant exposure. The oversell test should also assert a second tenant cannot see tenant-1
   holds/transactions (add a cross-tenant RLS assertion to Step 2's test).
4. **Razorpay/Stripe not yet connected** (master plan BLOCKER #3): `topup` is admin/manual until payment
   keys land. The `payment_ref` idempotency key is already in the schema so the webhook path drops in
   later without a migration.
5. **OTP path dormant** until the Meta WA pipeline is enabled (HANDOFF WAVE A2). PIN-only firewall ships
   now; OTP is the same step-up token with `amr:"otp"`.
6. **Integer-paise discipline:** any float touching money is a defect. Enforce in review; the schema is
   `BIGINT` minor units end-to-end; display layer is the only place that divides by 100.

---

## RED-TEAM FIXES (folded)

> Adversarial principal review, 2026-06-09. Verdict **GO-to-build, CONDITIONAL** (gates at the end).
> Every claim below was checked against live source under `droplet_work\` at the cited line. Fixes are
> folded as **amendments** to the sections above — where a fix contradicts the body, **the fix wins.**

### 🔴 BLOCKER F1 — Seam A/C `call_id` ordering is wrong; the hold/settle WOULD orphan (FIX MANDATORY)
**Bug (verified `caller.py:1616-1682`):** Section 5 Seam A says place the reserve "at `:1634-1640`,
generate the `call_id` BEFORE the reserve, stash `hold_id` on `it["_hold_id"]` and the rec." **None of
that is possible at 1634:**
- The call rec and its `id` are generated at **1665, INSIDE the `try`, AFTER `create_sip_participant`
  succeeds** (`rec = {"id": uuid.uuid4().hex[:10], ...}`). `it["_rec"]` is set at **1672** — also only on
  success. So at 1634 there is no rec to stash on, and if you pre-generate a `call_id` for the reserve,
  the code at 1665 mints a *different* uuid → `settle:call:{rec['id']}` ≠ `reserve:call:{call_id}` →
  **the settle never matches the hold; every wallet call double-holds and never settles.**
- The dial-failure `except` (**1676**) cannot "release off the rec" (Seam C) because `it["_rec"]` does
  not exist on the failure path. Literally impossible as written.

**FIX (exploits the existing `room` hoist at 1642 as precedent):**
1. **Hoist the id** beside `room` at **1642**, both before `create_room`:
   `room = f"famit-{num[1:]}-{uuid.uuid4().hex[:6]}"` → add `call_id = uuid.uuid4().hex[:10]`.
2. **Reserve AFTER the cap checks (1635-1640), BEFORE `create_room` (1656)**, keyed
   `reserve:call:{call_id}`. `idx` was ALREADY incremented at **1641** — on the no-funds branch
   `continue` **without** bumping `idx` again (the §5 pseudocode's `idx += 1` here is a double-increment
   bug → skips a lead) and **without** bumping `ACTIVE_CALLS` (no call placed).
3. At **1665**, build `rec = {"id": call_id, ...}` **reusing the hoisted id** (delete the inline
   `uuid.uuid4().hex[:10]`); set `rec["_hold_id"] = hold_id`.
4. **except at 1676:** release off the **local** `hold_id`/`call_id`
   (`await wallet.release(hold_id, idem_key=f"release:call:{call_id}")` if `hold_id`), NOT off the rec.

This makes the reserve/settle/release idem-keys all share one id. **§5 Seam A/C are amended accordingly;
the inline pseudocode in §5 is superseded by this block.**

### 🔴 BLOCKER F2 — §7 audit "same-txn" is UNSATISFIABLE as written (FIX MANDATORY)
§7 says money-mutating AI audit rows are written "in the same asyncpg transaction … (an `audit_event` PG
table **OR** pass the audit line through within the wallet txn)." If "pass through" means the existing
`audit.py` **JSONL append**, it **cannot be atomic with a Postgres COMMIT** — a file write and a DB commit
are separate durability domains: PG commits, the process dies before/with a failed file append, and the
audit diverges from the money — defeating the entire stated guarantee.
**FIX:** Money-mutating AI/audit rows are written **as a Postgres row inside the wallet txn** — either a
dedicated `wallet_audit` table (same DDL/RLS pattern as the other 4) **or** the existing
`wallet_transactions.meta` JSONB (carry `actor`, `action`, `decision` in `meta`). **Delete the ambiguous
"OR pass the audit line through."** JSONL (`audit.py`) remains the substrate for **non-money** AI
decisions only (§7 drain path unchanged). One sentence, one source of truth for money.

### 🔴 SECURITY F3 — step-up token is NOT bound to the caller → cross-tenant replay (FIX MANDATORY)
§6 `require_step_up` "verifies HS256 + scope + exp." It does **not** verify `sub == the authenticated
tenant`. A step-up token leaked/misrouted from tenant A is then **replayable by tenant B** — a privilege
escalation on the very *Action Firewall* meant to stop it.
**FIX:** `require_step_up(request, scope)` MUST also assert `claims["sub"] == resolve_tenant(request)`
(the X-Auth/JWT identity of THIS request); mismatch → **403** `{error:"step-up identity mismatch"}`.
Amount-binding (tying a spend token to a specific amount/resource) is a noted nice-to-have, **not** MVP.
**§6 is amended:** the mint already sets `sub:tenant_id`; the verify must enforce it.

### 🟠 MISSING TESTS (fold into the step that ships the code — do NOT defer)
- **T-A (Step 2): CONCURRENT double-settle.** §4-INV2 / Step-2 test (2) settles the same `call_id`
  *sequentially* — that proves nothing about the real hazard (finalize crash-replay **racing** the
  reconcile sweep). Fire **two `settle()` of the same `call_id` in one `asyncio.gather`** → assert balance
  debited **exactly once**, both return the same stored result. **Corollary the test must also assert:**
  the idempotency `result` JSON is populated **inside the txn (UPDATE-before-COMMIT)**, else the losing
  racer reads an empty/locked row and the replay returns nothing.
- **T-B (Step 3): release-on-dial-failure (Seam C).** Step 3 covers no-funds + TTL sweep but **not** the
  F1 except-path. Add: reserve succeeds, then `create_sip_participant` **raises** → assert the hold is
  released **immediately** (within that tick, not 900s later via the sweep) and `available_minor` is
  restored. This is the regression guard for F1's step 4.
- **T-C (Step 2): cross-tenant RLS** (already named in §11.3) is **promoted to a hard assertion** in the
  Step-2 test: as tenant `wallettest2`, attempt to `SELECT`/settle a `wallettest` hold → 0 rows / refused.

### 🟠 OPERATIONAL F4 — Step 6 frontend deploy target is STALE (FIX BEFORE Step 6)
The spec header + HANDOFF **body** point the frontend at the OLD box `168.144.125.155`/`root/famit-panel`.
Per HANDOFF **top banner (2026-06-08)** that box was **compromised + DELETED**; the panel now lives on
`famit-panel-2` **`143.110.247.249`**, app at `/opt/famit-panel` (systemd `famit-panel`, runs as
`deployuser`), SSH `ssh -i C:\Users\kunal\.ssh\do-blr-test\id_ed25519 root@143.110.247.249`. **Step 6 MUST
deploy there**, not the dead box. (Backend `168.144.153.145` is UNCHANGED and correct — verified.) Also:
site go-live is **pending a re-scoped Cloudflare token**; a Step-6 `panel.famit.in 200` check may fail for
infra reasons unrelated to the wallet — verify the new box's `next -p 3001` directly if the public URL is
not yet fronted.

### 🟡 PRECISION FIXES (fold; cheap, prevents a build-agent stumble)
- **F5 — Seam A balance pre-check is now an `await` in the admission path.** §5 Seam A extends the 402 gate
  (`:2134-2140`, verified `plan=="prepaid"`-only today) to `plan in ("prepaid","prepaid_wallet")` with a
  `wallet.balance(tenant) <= 0` pre-check. `/run` is `async def`, so the `await` is fine — but `balance()`
  MUST be a cheap single-row `SELECT` (no hold scan) and MUST degrade to "skip the wallet pre-check, fall
  through to legacy" if `wallet.available()` is False, so a PG blip never 402s a postpaid tenant. State
  this in §4 `balance()`.
- **F6 — `init()` is async; startup is async.** §5 Seam E shows `wallet.init(...)` bare. `create_pool` is
  awaitable; the startup hook in caller.py must `await wallet.init(...)` (or `init` schedules pool
  creation). Don't call an async pool builder synchronously. (Mark `firewall.init`/`aidecision.init` sync;
  only `wallet.init` is async.)
- **F7 — RLS `GRANT ... ALL SEQUENCES` is point-in-time.** §3 `GRANT USAGE,SELECT ON ALL SEQUENCES` only
  covers sequences existing **when it runs**. The 4 `BIGSERIAL` sequences are created by the `CREATE TABLE`
  in the same script, so order is fine **as long as the GRANT runs last** (it does). Add
  `ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE,SELECT ON SEQUENCES TO famit_app;` so a later
  table doesn't silently break inserts for `famit_app`.
- **F8 — admin cross-tenant via GUC needs the policy to actually allow it.** §3/§4 say admin ops set
  `app.tenant_id` to the target tenant (no superuser). Correct — but then an admin **listing ALL tenants'**
  wallets (e.g. a future `/billing/overview`-style sweep) cannot be one query under `FORCE RLS`. For MVP
  the admin endpoints are **per-tenant** (`/wallet/topup/{tenant_id}` sets the GUC to that id) — fine.
  **Do NOT add a cross-tenant aggregate wallet endpoint without a deliberate `BYPASSRLS` service path**;
  noted so a build agent doesn't "helpfully" add one and silently get empty results.

### Residual risks (accepted; documented, NOT blocking)
1. **PG round-trip per dial.** `reserve()` adds one in-band PG call before `create_sip_participant`.
   Negligible vs SIP setup (~hundreds of ms), but the pool `max_size=8` is **shared** across
   reserve/settle/balance/sweep; a multi-tenant burst can queue. Fine for this single box; **revisit pool
   size at Phase 2** (2-instance topology → size per-instance, consider PgBouncer per the master plan).
2. **`wallet_transactions` growth.** ~3 rows/call (hold, hold_settle, charge). At the master plan's
   100k-calls/day ceiling that's ~300-400k rows/day → a retention/partition plan is a **Phase 2** item, not
   MVP. Add a `created_at` BRIN index when it matters; today's btree is fine.
3. **Settle accuracy (already §11.2).** MVP settles on `duration_s × rate` at finalize; true vendor cost
   (`cost_ledger`) lands later via the drain — true-up with a `kind='adjust'` row. Confirmed acceptable;
   the hold caps worst-case exposure regardless.
4. **OTP/Razorpay dormant (already §11.4/5).** Confirmed non-blocking; schema carries the idem keys.

### What I confirmed CORRECT (do not relitigate)
- Reconciliation sweep (`caller.py:3327-3393`) does **NOT** call `_charge_call` → the §4-INV2 day-one
  idempotency justification stands. ✓
- 402 gate at `:2134-2140` is `plan=="prepaid"`-only → extending to `prepaid_wallet` is the right,
  non-breaking edit. ✓
- `_charge_call` at `:1336`; called once in `_finalize_call` at **:1495**; `duration_s` computed at
  **:1480** (so actual cost IS available at settle — no need to defer to the sweep). ✓
- Backend box `168.144.153.145` unchanged; `auth.py` HS256/`var/secret`/`_make_access` exist as cited;
  `_drain_usage_raw` (:1415), `_call_by_room` (:1409), `can()` (:561) all verified. ✓
- Postgres-not-JSON verdict, plan-scoped non-breaking flag design, build-don't-compose scope: **correct
  and appropriately minimal.** Do NOT expand scope; do NOT relitigate build-vs-compose.

### GO / NO-GO (this subsystem)
**GO-to-build — CONDITIONAL.** Build proceeds **only** when:
- **(G0)** Step 0 Postgres gate passes (db `famit` + role `famit_app` + `PG_DSN_ASYNC`). If PG can't be
  provisioned this session → STOP after a schema-design commit; **do NOT ship a JSON wallet** (§11.1).
- **(G1)** Blocker **F1** (call_id hoist/threading) folded into the Step-3 edit — else every wallet call
  orphans its hold.
- **(G2)** Blocker **F2** (audit money-row is a PG row in the txn, ambiguous "OR" deleted) folded before
  Step 5 ships money-mutating audit.
- **(G3)** Security **F3** (step-up `sub`==caller) folded before Step 4 enables the firewall.
- Tests **T-A/T-B/T-C** ship **with** their steps (2/3/2), not after.
F5-F8 are precision corrections to apply inline. With G0-G3 satisfied, this is a clean, well-scoped,
non-breaking build that leaves the live system earning.
