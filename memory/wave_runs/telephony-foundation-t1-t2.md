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


## T2 — trunk_registry package (flag OFF) — DONE

**Status:** DONE (local + offline-tested; flag `TRUNK_REGISTRY_ENABLED` default OFF). NO caller.py
edit, NO box mutation, NO service restart, NO calls. T3 mount remains deferred (caller.py
serialization vs the video wave). The package lives in `droplet_work/trunk_registry/` (force-added
to git the same way `provider_registry/` + the T1 DDL are — `droplet_work/` is broadly gitignored;
curated source is `git add -f`'d).

**11 modules shipped (`droplet_work/trunk_registry/`):**
- **REUSE (import-share provider_registry, do NOT rewrite):**
  - `credentials.py` (`:36-118`) — thin TRUNK-AAD wrapper over `provider_registry.credentials`
    (the live AAD AES-256-GCM). AAD = `tenant_id||trunk_id||key_version` via `_AadAdapter` (`:121-154`)
    that maps trunk_id -> the shared primitive's 2nd id so the AAD STRING is byte-identical. ONE crypto
    impl on the box; Vault flip in one place. Absent provider_registry -> CredentialError (never
    plaintext).
  - `ssrf_guard.py` (`:21-54`) — thin RE-EXPORT of `provider_registry.ssrf_guard.validate_endpoint`
    / `revalidate_redirect_location`; FAIL-CLOSED stand-in if absent.
  - `health.py` (`:27-136`) — RE-USES the in-memory circuit breaker (`is_open`/`record_*`/`run_probe`,
    3-fail open, 60->120->240 backoff) keyed per (tenant, trunk_id) + trunk-friendly aliases
    `trunk_is_degraded` / `trunk_health_snapshot`. Local fallback breaker if absent.
- **CLONE provider_registry (column-for-column for the sip_trunks shape):**
  - `config.py` — call-time env reads, `TRUNK_REGISTRY_ENABLED` default OFF + the concurrency/velocity/
    quarantine knobs (box-global cap 90, velocity 8s/200·hr, ring-out burst 5/600s, disable@3 quarantines).
  - `schema.py` (`:120-313`) — `SipTrunk`/`SipTrunkCred`/`SipTrunkHealth` dataclasses + enums
    (TrunkType/Direction/Transport/Encryption/DltStatus/RotationStrategy/CredentialScope/**Purpose**);
    `is_campaign_eligible` carried as the DB-DERIVED read-only field; `is_quarantined()` helper; `dids`
    falls back to caller_id.
  - `store.py` (`:88-371`) — is_admin=False RLS reads/writes for the 3 tables; **B1 filter**
    `campaign_eligible_only` (`:106-107`) + `exclude_quarantined` (`:108-109`); `soft_disable_trunk`
    (red-team D default), `set_quarantine`, `recent_did_ringouts` (the B-rel signal query),
    `count_trunk_quarantines` (B3), append-only `write_health_row`; `is_campaign_eligible`/`is_undeletable`
    NOT in the write whitelist (DB-derived / admin-seed-only).
  - `admin_store.py` — is_admin=True super-admin reads (require_super_admin-only at T3).
  - `registry.py` (`:85-159`) — **THE choke-point `get_trunk(tenant, purpose)`**. RED-TEAM B1 enforced
    TWICE: the store filter (`campaign_eligible_only=want_campaign`) AND a per-trunk re-check
    `_is_campaign_eligible` (`:140`) on the DB-derived column — a non-140/unregistered trunk is NEVER
    campaign-returned even via a direct write; purpose='test'/'manual' skip the gate (the founder single
    dial on the non-140 Vobiz `_global` trunk). Skips circuit-open + no-DID + no-livekit-trunk; never raises.
- **NEW (genuinely net-new, per §8):**
  - `concurrency.py` (`:89-205`) — **IN-PROCESS** per-trunk counter (red-team C-rel: box is uvicorn
    --workers 1, NOT the fail-open Redis :6380). `acquire` does atomic check-AND-reserve under ONE lock
    (no A2 TOCTOU oversell), `release` paired in try/finally (no A1 leak; double/None release = no-op).
    Enforces velocity (per-DID min spacing + calls/hour), GSM 1-SIM=1-call (A3), per-trunk cap, box-global
    cap (A4). Injectable clock.
  - `rotation.py` (`:70-222`) — DID round_robin/least_used/sticky (skip `avoid`); **RED-TEAM B-rel**
    `note_call_outcome` QUARANTINES on a zero-duration RING-OUT BURST (the signal that EXISTS — caller.py
    `wait_until_answered=False` never captures the 486); **RED-TEAM B3** >=K quarantines -> DISABLE trunk +
    LOUD alert naming the +918071583488 pool-burn pattern; **RED-TEAM E** `manual_quarantine_did` kill switch.
  - `livekit_sync.py` (`:84-241`) — pure request BUILDERS (outbound/inbound trunk + dispatch-rule w/
    `metadata:{tenant_id}`) + injected-async-client create/delete (NO container restart, native multi-trunk).
    SDK imported lazily -> dict mirror when absent (offline-assertable; SIP password NEVER echoed, only
    `auth_password_present`). **RED-TEAM D** `is_protected_trunk_id` + `delete_trunk` REFUSE the env
    `LIVEKIT_SIP_TRUNK_ID` / any protected id (+ empty id) unless `force_protected` (PIN-gated at T3).
    NEVER imports agent.py.

**Offline tests — 31/31 PASS (3 suites, no network / no PG / no LiveKit SDK):**
- `tests/test_registry_offline.py` (9/9) — a fake PG engine ENFORCES the §2.2 RLS GUC in pure Python.
  B1 campaign picks ONLY the 140-eligible trunk (not the lower-pri non-140); a 'test' dial allows the
  non-140 `_global` Vobiz trunk; no-eligible-campaign-trunk REFUSES; A never sees/reads B (RLS+cred);
  cross-tenant ciphertext copy -> InvalidTag (no plaintext); quarantined/circuit-open skipped+fallback;
  flag OFF -> registry_disabled; routing_hint pins.
- `tests/test_concurrency_offline.py` (8/8) — per-trunk cap never oversold; release-in-finally no leak;
  double/None release no-op; box-global cap across trunks; GSM 1-SIM=1-call; velocity spacing + hourly
  cap (fake clock).
- `tests/test_rotation_livekit_offline.py` (14/14) — RR/least-used/sticky + avoid; connected/below-threshold
  no-quarantine; ring-out BURST quarantines; B3 K-quarantines disables+alerts (names 918071583488);
  manual kill switch; livekit request shapes (no pw echo, tenant metadata); red-team-D delete refuses
  protected live trunk (force allows); create wires the injected client.
- Regression: `provider_registry` reused suites still green (registry 10/10, ssrf 39/39 — no drift).
- Dormancy: flag-OFF `get_trunk` -> `registry_disabled`, zero I/O (resting byte-identical).

**py_compile:** all 12 modules + 3 test files compile clean. Package imports with empty env (no `db`,
no LiveKit SDK) -> `__version__` `0.2.0-t2` (all surfaces loaded via the import guards).

**EARNER GATE (read-only box, PASS):** agent.py md5 `9150fabe4ff62b4b4470f9a87df346e5` UNCHANGED ·
famit-agent MainPID `1477083` active NRestarts=0 NOT restarted · caller `/health` (8209) = 200 ·
famit-caller active (PID 2774834) · 0 5xx (last 15 min) · NO ring (pure-local build + offline tests;
no box mutation, no restart, no calls). gitleaks staged = 0. Commit on `fe/unify-run-wavec`.

**NEXT = T3** (additive `/trunk-registry/*` + `/trunks/byo/*` guarded mount in caller.py, flag OFF;
/test-call rate-limited; DELETE soft-disables + refuses `_global`/env; `POST /quarantine-did` kill switch)
— DEFERRED until caller.py frees from the video wave (cross-product serialization, PLAYBOOK #5).
