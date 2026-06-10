# WAVE-BUILD-F4 (part 2) — CREDIT/WALLET ACID LEDGER + ACTION FIREWALL + AUDIT (PLATFORM-ENG)

Spec (followed verbatim, RED-TEAM fixes folded — fix wins on conflict): `design/credit-ledger-firewall.md`.
Roadmap: `MASTER_PLATFORM_ROADMAP.md` F4. (F4 part 1 = Logto OIDC, separate box — see `wave-build-F4-logto.md`.)
Box: famit@168.144.153.145 `/opt/famit-agent/` (priv 10.122.0.4), venv `/opt/capsy-agent/.venv` (py3.12),
svc `famit-caller` (uvicorn :8209) + `famit-agent`. SSH key `...\do-blr-test\id_ed25519`. Local SoT
`droplet_work/`. Mode: ADDITIVE / non-breaking / live system keeps earning. NO git (orchestrator commits).
STATE ledger: `droplet_work/F4_WALLET_FIREWALL_STATE.md`.

## RECONCILE (2026-06-10, session start)
- caller/store/auth/audit local==box md5 (caller `6d7b0696`, store `2b2b0774`, auth `12617761`, audit
  `d2420471`) — NO drift (box synced to local after F2).
- Box: both svcs active. PG 16. `PG_DSN`(psycopg2)+`PG_DSN_ASYNC`(asyncpg) set -> local `famit` db.
  STORE_MODES = 12 stores dual. asyncpg/jwt/sqlalchemy2.0.50/psycopg2 all in venv.
- **G0 Postgres gate PASS** (db famit + role famit_app + both DSNs present). NO wallet_* tables, NO
  wallet.py/firewall.py/aidecision.py yet — clean slate.

## THE ARCHITECTURE DECISION (advisor-greenlit; deviates from spec §4 — improvement)
The spec §4 says build a RAW `asyncpg.create_pool` in wallet.py with its own `SET LOCAL app.tenant_id`.
**Rejected in favor of REUSING P1's `db/engine.py`** `session(tenant_id, is_admin)` (sync, psycopg2):
- Gets the proven FORCE-RLS GUC-in-txn + **admin-GUC escape hatch** for free; NO 3rd connection pool to
  the same DB (= spec's own residual-risk #1); NO duplicated GUC plumbing. caller.py already runs the
  `_read/_write` seam sync inside async routes -> a sync wallet core is consistent + non-event-loop-blocking.
- The correctness primitives are **driver-independent**: the atomic conditional `UPDATE ... WHERE
  available_minor >= :amt RETURNING` is self-locking under READ COMMITTED; `FOR UPDATE` + `INSERT ON
  CONFLICT DO NOTHING` behave identically on psycopg2. **Proven by the concurrency test below.**
- **HARD INVARIANT honored:** every wallet op = EXACTLY ONE `with engine.session() as s:` block (idem
  INSERT + balance UPDATE + hold mutation + result-store share ONE txn / ONE COMMIT).

## SCHEMA (db/ddl_wallet.sql — applied on box as famit_app; idempotent CREATE IF NOT EXISTS)
4 tables, money in INTEGER MINOR UNITS (paise) end-to-end, BIGINT, no floats:
- **wallet_accounts** (PK tenant_id,currency): `available_minor`, `held_minor`, lifetime topup/spend,
  `version`. CHECK `available_minor>=0` + `held_minor>=0` (the DB-level no-oversell backstop).
- **wallet_transactions** (BIGSERIAL): immutable append-only money movements. kind = topup|hold|
  hold_settle|hold_release|charge|refund|adjust. signed `amount_minor`, `held_delta_minor`,
  `balance_after_minor` snapshot, `meta` jsonb, resource_type/id, hold_id, idempotency_key.
- **wallet_holds** (BIGSERIAL): open reservations, state open->settled|released|expired, `expires_at` TTL.
  CHECK `amount_minor>0`. Partial idx on (state,expires_at) WHERE state='open'.
- **wallet_idempotency** (PK idem_key): the double-charge guard. result jsonb replayed on a repeat key.
- **RLS:** all 4 `ENABLE`+`FORCE ROW LEVEL SECURITY` with the **P1 admin-GUC policy shape** (`db/rls.sql`)
  `USING/WITH CHECK (current_setting('app.is_admin',true)='1' OR tenant_id=current_setting('app.tenant_id',
  true))`. **DEVIATION from spec §3** (which omits the admin leg): adopted for consistency with the rest
  of the platform + so admin top-up (`POST /wallet/topup/{tid}`, app.is_admin='1' in-txn) acts on a target
  tenant with NO superuser conn. Grants to famit_app + ALTER DEFAULT PRIVILEGES (F7).
- VERIFIED on box: 4 tables, 2 CHECK constraints, 4 *_isolation policies, relrowsecurity=t/relforce=t.

## wallet.py — the transactional core (reserve/settle/release/topup/balance/sweep_expired_holds)
- **reserve()** = INVARIANT 1 (no oversell): one txn — idem claim -> atomic conditional `UPDATE ... WHERE
  available_minor >= :amt RETURNING` (0 rows == insufficient funds, no race window) -> insert hold + a
  `kind='hold'` tx -> store idem result. Returns hold_id or None.
- **settle(hold_id, actual, idem_key='settle:call:<id>')** = INVARIANT 2 (idempotent capture): one txn —
  `INSERT ... ON CONFLICT DO NOTHING` claims the key (a CONCURRENT loser BLOCKS on the PK lock, then reads
  the winner's in-txn-stored result) -> hold `FOR UPDATE` -> `charged=min(actual,reserved)`, refund the
  remainder, release the whole held amount, lifetime_spend += charged -> `hold_settle` + `charge` tx rows.
- **release(hold_id)**: void an open hold (dial failed/expired) -> return reserved to available. Idempotent.
- **topup()**: admin/payment credit, idempotent on `topup:<payment_ref>` (webhook-retry safe).
- **balance()**: cheap single-row SELECT; degrades to None on PG blip (F5 — never 402 a postpaid tenant).
- **sweep_expired_holds()**: release every open hold past expires_at (crash-safety). Per-hold idempotent.
- **import-safe degrade:** `available()` False when PG down -> reserve->None, settle/topup->{ok:False}.

## ⭐ THE NO-DOUBLE-SPEND PROOF (tests/test_wallet_concurrency.py — on box, live PG, PROOF_EXIT=0, ALL PASS)
Concurrency is REAL (ThreadPoolExecutor — sync sessions overlap only across threads, each its own pooled
conn; a for-loop proves nothing). Throwaway tenants `wallettest`/`wallettest2`, rows DELETED after.
1. **NO-OVERSELL under 24 concurrent** reserve+settle on a balance covering exactly N=8: **exactly 8
   succeed**, available never < 0, ended 0, held ended 0, no negative account row.
2. **NEGATIVE CONTROL (the teeth):** repeat with BOTH backstops removed — the app `>= :amt` guard
   (`_UNSAFE_NO_OVERSELL_GUARD`) AND the DB CHECK constraint (dropped+restored on the table) — it
   **OVERSELLS**: 24 succeed, balance drives to **-16000**. Proves the test would FAIL a broken wallet, so
   check 1's pass has meaning. (Incidental finding: with only the app guard removed, the FIRST run hit
   `CheckViolation` — i.e. the DB CHECK is a live second backstop. Two independent no-oversell defenses.)
3. **CONCURRENT double-settle (red-team T-A):** two `settle(call_id)` in parallel threads -> charged
   **exactly once** (1500), 500 refunded, **exactly ONE `charge` tx row**, both return the identical
   stored result. This works because `INSERT ON CONFLICT DO NOTHING` BLOCKS the loser until the winner
   COMMITs, then the loser reads the result the winner stored IN THE SAME TXN (a SELECT-then-INSERT would
   reopen the race).
4. **hold -> capture remainder:** settle(1200) of a 3000 hold -> charged 1200, refunded 1800, available
   restored. **release:** a fresh open hold released -> full 2000 returned, held 0.
5. **TTL sweep:** backdate expires_at -> `sweep_expired_holds()` releases it, available restored, state
   `expired`.
6. **CROSS-TENANT RLS:** wallettest2 sees **0** of wallettest's accounts/holds/transactions, but DOES see
   its own row (RLS not over-blocking).
7. **LEDGER INTEGRITY INVARIANT (proven):** `available_minor + held_minor == SUM(amount_minor)` holds BOTH
   mid-open-hold AND at quiescence. So `amount_minor` is the signed delta to **TOTAL funds** (not to
   available); **`balance_after_minor` is the reconciliation source of truth for AVAILABLE**,
   `held_delta_minor` for held. (Closed an advisor catch: the spec-copied schema comment misdescribed
   `amount_minor` as "delta to available" — corrected in ddl_wallet.sql to "delta to TOTAL", and the
   Step-6 frontend must NOT compute a running available balance by `SUM(amount_minor)`.)
Post-run: zero residue (all wallet tables 0 rows), CHECK constraint restored, svcs active.

## ACTION FIREWALL (firewall.py) — PIN step-up gate
- Reuses the existing HS256 + `var/secret` (SECRET) machinery (auth.py precedent). PIN store
  `var/pins.json` = `{tenant_id:{salt,pin_hash,set_at}}`, `pin_hash=sha256(salt+":"+pin)` — IDENTICAL to
  caller._hash_pw (pass_hash). PIN never stored raw. `check_pin` uses `secrets.compare_digest`.
- **mint_step_up** -> `jwt.encode({sub:tenant_id, amr:"pin", scope, type:"step_up", exp:now+300}, SECRET,
  HS256)`. **verify_step_up_token** asserts signature+exp+type+scope **AND (G3/F3 SECURITY BLOCKER) sub ==
  the authenticated caller** — a leaked tenant-A token is NOT replayable by tenant-B (-> 403 "step-up
  identity mismatch").
- **require_step_up(request, scope, tenant)** = guard mirroring `can()`. PASS-THROUGH (non-breaking) when
  `FIREWALL_ENABLED` OFF / firewall unavailable / tenant has NO PIN. Else reads `X-Step-Up` header,
  verifies; missing/invalid -> raises `StepUpDenied(403/...)`. `classify(action)` maps an action name ->
  scope (spend|destructive|"").
- OTP-over-WhatsApp = dormant stub (`request_otp/verify_otp` -> not_configured; same amr:"otp" shape later).
- FLAG `FIREWALL_ENABLED` default OFF.

## AUDIT (item 3) — extended, IN SCOPE; agent.py drain DEFERRED
- `audit.record` (existing append-only `var/audit_log.jsonl`, immutable) wired into: firewall verify
  (`firewall.stepup.ok` / `.fail`), the 403 deny path (`firewall.stepup.denied`), PIN set
  (`firewall.pin.set`), and `wallet.topup` (with amount/payment_ref/ok in meta).
- `audit.tail` + `GET /audit` extended with a **`channel` filter** (`?channel=ai` -> 200), so the future
  AI-decision rows are queryable. Every AI/spend decision recorded with actor+action+result.
- **IMMUTABLE leg CONFIRMED (not just JSONL):** the deliverable's immutability comes from the append-only
  P1 PG `events` table (JSONL rotates/is mutable). `events:dual` is on -> `audit.record` ->
  `store.mirror_event` landed the F4 rows in PG: VERIFIED via admin-GUC `SELECT ... FROM events` ->
  `firewall.pin.set:2, firewall.stepup.denied:2, .fail:2, .ok:2, wallet.topup:6` (14 rows). So the spend/
  firewall decisions are in the immutable PG ledger, append-only, RLS-scoped. (Closed an advisor catch —
  was assumed, now proven.) These test-traffic event rows are append-only-immutable by design -> left
  in place (same posture as F2's gate-test audit rows; harmless).
- **DEFERRED (explicitly):** the agent.py per-room `var/ai_decisions_raw/<room>.json` drop +
  `aidecision.drain_ai_decisions()` (spec §7 / Step 5 second half) — it touches the VOICE process (needs
  `restart famit-agent`) + a real call to prove, = over-reach for "ledger+firewall+proof". The same-txn
  money-audit coupling (red-team F2) is **moot until the AI-Manager exists** (no autonomous-spend path
  yet) — when it ships, the money-mutating audit row goes in the wallet txn as `wallet_transactions.meta`
  (the F2-blessed shape), NOT a JSONL append (which can't be atomic with a PG COMMIT).

## ADDITIVE ENDPOINTS (no existing route/run-path changed)
| Method · Path | Auth | Notes |
|---|---|---|
| GET /wallet | self | balance in MAJOR units (rupees) + plan; clean shape when unavailable |
| GET /wallet/ledger?limit=100 | self | wallet_transactions newest-first, major units |
| GET /wallet/holds?state= | self | reservations |
| POST /wallet/topup/{tenant_id} | **admin + step-up(spend)** | idempotent on payment_ref; audited |
| PUT /firewall/pin | self | set/replace own PIN (salted-hash); audited |
| POST /firewall/verify-pin | self | PIN -> mint step-up token / 401 + audit fail |
| GET /firewall/status | self | {pin_set, firewall_enabled, available} |
| GET /audit?channel=ai (EXTENDED) | admin/self | channel filter added |

## ⭐ LIVE PROOF (on box, HTTP via legacy X-Auth admin) — PASS=21 FAIL=0
- REGRESSION: legacy X-Auth **200** on /campaigns /leads /billing/overview /me.
- Wallet: GET /wallet, /wallet/ledger, /wallet/holds -> 200; topup ok+credited 50; idempotent (still 50
  on payment_ref replay, NOT 100).
- FIREWALL (flag ON + admin PIN set): gated topup **WITHOUT X-Step-Up -> 403**; wrong PIN -> **401**;
  correct PIN -> **token minted**; gated topup **WITH X-Step-Up -> 200**.
- AUDIT: rows `firewall.stepup.fail` / `.ok` / `.denied` / `wallet.topup` all present; `?channel=ai`->200.
- /run DISPATCH regression (NO paid call): `POST /run` bad-campaign -> **404** (never dials; the 404 at
  caller.py:2482 fires before the dial loop), 0 calls rows created in window, no 5xx/traceback in journal.
- CLEANUP: `FIREWALL_ENABLED` restored to **false**, throwaway PIN removed, wallet rows wiped (0 residue).
- Both svcs **active** throughout.

## NON-BREAKING / WHAT'S ADDITIVE (blast radius)
- caller.py edits are PURELY ADDITIVE: +2 import blocks (wallet/firewall, defensive), +1 firewall init at
  startup, +8 new routes, +1 channel kwarg on /audit + audit.tail. NO existing route/seam/run-path touched.
- INSTANTIATE-smoke (exec_module caller.py in venv) BEFORE restart confirmed import-clean + all 7 new
  routes present + existing routes intact + wallet/firewall loaded. (AST-parse alone is insufficient —
  VOICEFIX lesson.)
- wallet uses db.engine (already wired by store.init) — needs no own init. firewall.init reuses SECRET.
- With all flags at default (`FIREWALL_ENABLED=false`, no `WALLET_ENABLED` yet, no wallet tenants), the
  system is byte-for-byte today's behavior; the wallet core is exercised only by the additive endpoints
  + the proof harness.

## md5 box==local (zero drift) + ROLLBACK
- caller.py `c404f1c0`, audit.py `190fa1b6`, firewall.py `1ac4f699`, wallet.py `1890d41f`,
  db/ddl_wallet.sql `1f908299` — all box==local.
- Backups on box: `caller.py.F4bak.1781039853`, `audit.py.F4bak.1781039853`, `.env.F4bak.*`.
- **ROLLBACK:** `cp caller.py.F4bak.<ts> caller.py && cp audit.py.F4bak.<ts> audit.py && sudo systemctl
  restart famit-caller` -> drops the 8 routes + channel filter; wallet/firewall modules become unimported/
  inert. The 4 wallet_* tables are ADDITIVE (nothing in the run-path reads them) — leave or DROP. No
  permanent `.env` change (FIREWALL_ENABLED restored to false). Zero data migrated; voice path untouched.

## DEFERRED (named so the next builder doesn't chase ghosts; these are the LATER units)
1. **caller.py dial-loop hold/settle/release wiring** (spec §5 Seams A-D + red-team **F1 call_id hoist** at
   caller.py:~1642, generate call_id BESIDE `room` before create_room, thread one id through reserve/
   rec/settle/release) behind a `WALLET_ENABLED` flag, ON for ONE `prepaid_wallet` test tenant — the REAL
   run-path spend gate. Needs a real metered call to prove. = spec Step 3.
   ⚠ **TWO SEPARATE BALANCES, segregated by plan — NEVER sum them.** `billing.json.balance` governs plan
   `prepaid` (the existing 402 gate at caller.py:2494, untouched); `wallet_accounts.available_minor`
   governs plan `prepaid_wallet` (the new wallet). The deferred Seam-A admission gate MUST branch on
   `plan`: prepaid -> legacy billing.balance check; prepaid_wallet -> `wallet.balance()`; postpaid ->
   neither (accrues). Summing the two = double-counting money.
2. **agent.py per-room AI-decision drop + aidecision.drain** (spec §7 / Step 5b) — touches the voice
   process; gate on the latency regression test before wiring anything into the agent.
3. **same-txn money-audit** (red-team F2): when the AI-Manager autonomous-spend path ships, the audit row
   goes in `wallet_transactions.meta` inside the wallet txn (NOT JSONL — can't be atomic with a PG COMMIT).
4. **Wiring the firewall into the AI-Manager / ad-spend / Workflow Studio** — `classify()` + the action
   name set (`_SPEND_ACTIONS`/`_DESTRUCTIVE_ACTIONS`) are ready; those callers call `require_step_up`
   before executing spend/bulk/delete. `brain.write_ai` scope (F2 RT-2) is registered for the AI-Manager
   Brain-write path. These are LATER units (the AI-Manager doesn't exist yet).
5. **Razorpay/Stripe topup webhook** (payment_ref idem key already in schema -> drops in, no migration).
   **OTP-over-WhatsApp** (dormant; Meta WA pipeline). **Frontend** wallet card + PIN/step-up modal +
   AI-audit view (spec Step 6, against famit-panel-2 143.110.247.249 — the OLD box was deleted, red-team F4).
6. **wallet_transactions growth/partition** + **pool sizing at Phase-2 2-instance topology** — Phase-2 items.

## ARTIFACTS (local SoT droplet_work/, box==local)
- NEW: `db/ddl_wallet.sql`, `wallet.py`, `firewall.py`, `tests/test_wallet_concurrency.py`, `tests/__init__.py`.
- EDITED: `caller.py` (+imports/init/8 routes/channel kwarg), `audit.py` (+channel filter).
- Smoke/proof harnesses (local+box-runnable): `_run_wallet_proof.sh`, `_live_proof_u3u4.sh`,
  `_run_dispatch_check.sh`, `_apply_ddl_wallet.sh`, `_deploy_smoke_u3u4.sh`. STATE:
  `F4_WALLET_FIREWALL_STATE.md`.
