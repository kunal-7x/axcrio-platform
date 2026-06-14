# Telephony Foundation T1+T2 — wave run log

Spec: `design/TELEPHONY-INDEPENDENCE-PLAN.md` §2.2 + §3 (red-team B1/D) + §5 (T1/T2).
Branch `fe/unify-run-wavec`. Flag `TRUNK_REGISTRY_ENABLED` default OFF (resting byte-identical).
Twin of the LIVE `provider_registry` (W1) — same FORCE-RLS / `_global` write-lock / AAD AES-256-GCM
creds / append-only health trigger. `agent.py` (`9150fabe…`) NEVER imported/touched. Box
`famit@168.144.153.145`, key `do-blr-test/id_ed25519`, PG via `PG_DSN` (`+psycopg2` stripped for psql),
`famit_app` = NOSUPERUSER + NOBYPASSRLS (verified) so FORCE-RLS binds the owner.

This wave = T1 (additive PG DDL + seed) ONLY. NO `caller.py` edit, NO trunk_registry package, NO
service restart, NO calls. The T3 mount is deferred (cross-product serialization vs the running video wave).


## T1 — DDL + seed (PG applied live, flag stays OFF)

**Status:** DONE (PG applied live + verified). NO caller.py edit, NO trunk_registry package,
NO service restart, NO call. Box `famit@168.144.153.145`.

**DDL file:** `droplet_work/db/ddl_trunk_registry.sql` (md5 `e96da9966fe7ab3d44d4cede237ac7c8`),
3 FORCE-RLS tables cloned column-for-column from `ddl_provider_registry.sql`:
- `sip_trunks` (lines 47-116): trunk spec. `trunk_type` CHECK sip_provider|gsm_gateway|direct_sip;
  `sip_host`/`sip_port`/`transport`/`encryption`/`auth_username`; `did_pool` jsonb + `caller_id`;
  `max_concurrency` (>=1 CHECK); `cost_per_minute_paise` INTEGER (no floats). COMPLIANCE gates
  `is_140_series`/`dlt_entity_id`/`dlt_status`/`per_did_daily_cap`. **RED-TEAM B1**: line 101-102
  `is_campaign_eligible boolean GENERATED ALWAYS AS (is_140_series AND dlt_status='registered') STORED`
  + CHECK `sip_trunks_campaign_gate_ck` (110-112) — unbypassable at the DB layer. `_global` RLS:
  READ-share (siptrunk_read 119-123) + WRITE-lock (siptrunk_write 125-131). **RED-TEAM D**:
  `is_undeletable` col + `sip_trunks_protect_undeletable_trg` (DELETE refused, 152-162) +
  `sip_trunks_lock_undeletable_trg` (TRUE->FALSE flip refused, 168-176).
- `sip_trunk_credentials` (181-201): AAD AES-256-GCM SIP-password ciphertext + `key_aad` +
  `scope` CHECK integration|platform; strictly per-tenant RLS (no `_global` share).
- `sip_trunk_health_log` (208-228): per-DID `did` col + `event`/`sip_code`; append-only via
  `sip_trunk_health_log_append_only_trg` (UPDATE + direct DELETE blocked, FK cascade allowed).

**FORCE-RLS proof (live box, `pg_class`):** all 3 = `relrowsecurity=t` + `relforcerowsecurity=t`.
Triggers present: `sip_trunk_health_log_append_only_trg`, `sip_trunks_protect_undeletable_trg`,
`sip_trunks_lock_undeletable_trg`. `is_campaign_eligible` = STORED generated (`attgenerated='s'`).

**Behavioural RLS + red-team proofs (famit_app via GUC, NOSUPERUSER/NOBYPASSRLS):**
- `A_reads_global=1` (tenant reads the `_global` Vobiz trunk → flag-on dials the SAME trunk).
- `A_sees_global_cred=0` (SIP password never `_global` read-shared — strictly private).
- `_global` write-lock: tenant-A INSERT into `_global` → "violates row-level security policy" (blocked).
- cross-tenant: `B_sees_A_trunk=0`, `B_sees_global=1` (only the shared row).
- **B1 gate**: `a-compliant` (is_140_series=true, dlt_status=registered) → `is_campaign_eligible=t`;
  `a-noncompliant` → `is_campaign_eligible=f`. Derived, not user-set.
- **append-only**: direct UPDATE blocked; direct DELETE blocked (both raise insufficient_privilege).
- **RED-TEAM D**: DELETE of the un-deletable Vobiz `_global` trunk → REFUSED even under admin GUC;
  clearing `is_undeletable` → REFUSED. Vobiz row intact after both refused ops.
- FK cascade still works: deleting the 3 test trunks cascaded their health rows (depth>1 allowed)
  while direct health delete stays blocked. Cleanup left ONLY the Vobiz seed (REMAIN_TRUNKS=1,
  REMAIN_CREDS=1, REMAIN_HEALTH=0).

**Seeded Vobiz row (`_global`, UN-DELETABLE — red-team D):** id `9896cddf-4d54-4b45-aee6-458c4af51249`,
slug `vobiz-outbound-tcp`, `livekit_trunk_id=ST_fmtVmNJmpzKa` (the EXACT live trunk), host
`2c24f731.sip.vobiz.ai`, transport TCP, DID/caller-ID `+918071583488`, auth user `capsy-project`,
encryption disable, `max_concurrency=1`, priority 10, `is_enabled=t`, `is_test_verified=t`,
`is_undeletable=t`. **`is_campaign_eligible=f`** (is_140_series=false, dlt_status=unregistered) —
so flag-on dials the same trunk for a founder TEST/manual dial but is BLOCKED from the campaign pool
until a 140/DLT route is bought (§7). Values mirror the live `lk sip outbound list` (read-only).

**Seeded cred:** id `1560f76a-...`, `_global`/trunk, AAD `_global||9896cddf-...||1`, `scope=platform`
(masked-only), 47-byte AES-256-GCM ciphertext. Plaintext is a sentinel `__livekit_managed__` (the live
SIP digest password is held INSIDE the LiveKit trunk object — READ-ONLY mandate forbade extracting it,
and flag-on dials via `livekit_trunk_id` so the registry never needs the raw SIP password for the Vobiz
`_global` row; the sentinel proves the cred table + AAD crypto end-to-end without touching the live
Vobiz SIP path). Decrypt verified via the box `provider_registry/credentials.py` (caller python
`/opt/capsy-agent/.venv`, env `/opt/famit-agent/.env`, `PROVIDER_KEYSTORE_SECRET` set): roundtrip_ok,
no plaintext in DB.

**Earner gate (before + after, PASS):** agent.py md5 `9150fabe4ff62b4b4470f9a87df346e5` UNCHANGED ·
famit-agent MainPID `1477083` active, NRestarts=0, NOT restarted · caller `/health` (8209) = 200 ·
0 5xx (last 15 min) · NO ring (PG DDL + read-only smoke only; no calls). gitleaks staged = 0.
NO caller.py edit; T3 mount deferred (serialized vs the running video wave). Commit on `fe/unify-run-wavec`.
