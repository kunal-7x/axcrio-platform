# communication/_BUILD-LOG.md — per-phase build conclusions (APPEND-ONLY)

> Each phase appends its conclusion under a per-phase heading. The final phase also
> appends one line to `caps/WORKFLOW_LEDGER.md` + updates `communication/README.md`.

---

## W1-P0 — DB + TOKEN (Telegram, founder tenant) · 2026-06-14 19:53 UTC · backend, no caller.py

**Scope:** Apply the Wave-1 comm DDL (4 FORCE-RLS tables) to the live box PG + store the
founder Telegram bot token AAD-encrypted in the LIVE provider_credentials vault. NO caller.py,
NO agent.py, additive-only, backup-not-needed (additive — drop is the rollback). Branch
`fe/unify-run-wavec`.

### Earner gate (BEFORE + AFTER — box `famit@168.144.153.145`, the voice box `famit-livekit`)
| Check | BEFORE | AFTER |
|---|---|---|
| `agent.py` md5 (expect `9150fabe4ff62b4b4470f9a87df346e5`) | `9150fabe…` UNCHANGED | `9150fabe…` UNCHANGED |
| famit-agent MainPID (must not restart by my work) | 2808658 active | 2808658 active (SAME) |
| caller `/health` (port 8209) | 200 | 200 |
| famit-caller / famit-panel | active / inactive | active / inactive (untouched) |
| caller 5xx (last 20m) | — | 0 |
> NOTE: the lock file cited PID 1477083; the live famit-agent has since been restarted by a
> PRIOR wave to PID 2808658, but the **byte-identical** md5 `9150fabe…` is the earner truth and
> is UNCHANGED. THIS phase did not restart any service (DB + vault only). No ring placed.

### DDL — `communication/db/ddl_comm.sql` (box: `/opt/famit-agent/communication/db/ddl_comm.sql`, md5 `3abd30fbf3d0136788c78f573185d016`)
Four FORCE-RLS tables, `tenant_id TEXT`, INTEGER paise, idempotent `IF NOT EXISTS`, applied via the
live `db.engine` as `famit_app` (NOSUPERUSER/NOBYPASSRLS — confirmed). Key line ranges:
- `comm_sessions` — DDL lines **31–55** (LLM brain rolling-20 window; UNIQUE `(tenant,channel,external_chat_id,provider_def_id)` — no shared bot across tenants, S4).
- `comm_send_log` — DDL lines **61–90** (append-at-create; `cost_minor BIGINT` paise; `idempotency_key` UNIQUE = `comms:{message_id}`; `outcome` CAPI col day-1).
- `comm_consent_log` — DDL lines **97–115** (the `channel × purpose` model; `consent_basis` derived from `lead_source`; **append-only HARD**).
- `comm_asset_cache` — DDL lines **120–134** (Telegram `file_id` reuse; UNIQUE `(tenant,spaces_key,channel)`).
- RLS `DO $rls$` admin-GUC block (ddl_ai_wa.sql shape verbatim) — DDL lines **139–161**.
- Append-only hardening (REVOKE + immutability trigger) — DDL lines **165–192**.

### RLS / append-only PROOF (live, as `famit_app`)
- **4 tables rls=t force=t:** `comm_sessions`, `comm_send_log`, `comm_consent_log`, `comm_asset_cache` — all `(True, True)`. ✅
- **4 isolation policies present** (`comm_*_isolation`). ✅
- **comm_consent_log append-only:** `famit_app` grants = `INSERT, SELECT, REFERENCES, TRIGGER, TRUNCATE` — **NO UPDATE, NO DELETE** (REVOKE worked); trigger `comm_consent_no_update` present. ✅
- **Cross-tenant SELECT = 0:** insert a `comm_sessions` row as tenant `admin` → `admin` sees 1, `tenant_b` cross-read = **0**. PASS. ✅
- **consent immutable:** UPDATE → blocked (ProgrammingError), DELETE → blocked, row survives (count=1). PASS. ✅

### TOKEN — founder Telegram bot stored AAD-encrypted in the LIVE vault (zero new crypto)
- Token read from `.env.local` at RUNTIME (first line `TELEGRAM_BOT_TOKEN=`), bot `mr_kunal_bot`. Verified LIVE via `getMe` → `ok:true`, username `mr_kunal_bot`. **Never hardcoded, never committed, never logged, never on argv** (piped over the ssh stdin env, dropped from `os.environ` immediately after read).
- Stored under tenant **`admin`** (the founder tenant — `caller.py:598`, legacy panel login → admin), channel **telegram**, reusing the live registry vault:
  - `provider_definitions` row **`95ed8978-8bfe-4de2-8506-52e989d09f0e`** — slug `telegram-founder`, display "Telegram (mr_kunal_bot)", `provider_type=tool_connector`, capabilities `[webhook, tool_call]`, `base_url=https://api.telegram.org`, `named_provider=telegram`, `cost_per_unit_micros=0`.
  - `provider_credentials` row **`d3303376-701a-4a22-bef5-8308898160a6`** — `scope=integration` (founder's own, revealable via step-up), `is_active=true`, `key_version=1`, AAD `admin||95ed8978-8bfe-4de2-8506-52e989d09f0e||1`.
- **Decrypt-roundtrip MATCH = True**, masked **`8934…O7Js`** (matches the live getMe identity).
- **NO plaintext in DB:** the `ciphertext` bytea (74 bytes = 12-byte nonce + GCM) does NOT contain the plaintext token bytes; `ciphertext != token`. ✅
- **AAD binding holds:** copying admin's ciphertext into a `tenant_b` cred shape → decrypt raises **InvalidTag** (cross-tenant copy refused, no plaintext). ✅ (This is the T-VAULT probe shape.)
- **NO plaintext in logs:** caller journal + postgres journal (last 20m) → **0** hits for the bot-id portion. ✅

### Flags
None flipped this phase (DB + token only). The W1 code flags (`COMM_ENABLED`, `COMM_TELEGRAM_ENABLED`,
`FEATURE_TELEGRAM_FOUNDER_ALERT`, `FEATURE_TELEGRAM_FOLLOWUP`) stay OFF; they flip ON for the founder
tenant only AFTER the W1 code + security probes ship. Resting state is byte-identical (no code path
reads these tables until the comm package + caller.py mount land in a later phase).

### Rollback
`DROP TABLE comm_sessions, comm_send_log, comm_consent_log, comm_asset_cache;` (additive — nothing
else altered) + `DELETE FROM provider_credentials WHERE id='d3303376-…'` and the def row (vault rows are
inert until the adapter reads them).

### Files
- NEW `communication/db/ddl_comm.sql` (the 4-table DDL).
- NEW `communication/_BUILD-LOG.md` (this log).
- Box: `/opt/famit-agent/communication/db/ddl_comm.sql` (md5-gated copy).

**Status: DONE. DB live + token stored + earner gate green (before+after). Next phase: the comm
package (channels/base + telegram adapter, founder_alert, post_call, send_log, consent, router) +
the caller.py `_finalize_call` insertions under the CALLER_EDIT_LOCK.**
