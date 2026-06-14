# Provider Framework Foundation — wave run log

Spec: `design/PROVIDER-FRAMEWORK-PLAN.md` §5 + §14 (W1–W3, offline). Canonical branch
`fe/unify-run-wavec`. Flag `PROVIDER_REGISTRY_ENABLED` default OFF (resting byte-identical).
Earner-safe: agent.py never imported/touched; only additive PG DDL + local files this wave.

## W1 — DDL + package shell

**Status:** ✅ DONE (PG applied live + offline-verified). Commit `8c9924f`.

**Earner gate (before + after, PASS):** agent.py md5 `9150fabe4ff62b4b4470f9a87df346e5`
UNCHANGED · famit-agent MainPID `1477083` active, NOT restarted (mtime 2026-06-09 untouched) ·
caller `/health` (port 8209) = 200 · 0 real 5xx (last 15 min) · NO ring (no calls; only PG
DDL + read-only smoke). Box `famit@168.144.153.145`, key `do-blr-test/id_ed25519`. PG DSN =
`postgresql+psycopg2://famit_app:…@127.0.0.1:5432/famit` (psql via `+psycopg2`-stripped URL);
`famit_app` is NOSUPERUSER + NOBYPASSRLS (verified) so FORCE-RLS binds it.

**Files (committed, force-added — `droplet_work/` is gitignored; matches how caller.py/kb track):**
- `droplet_work/db/ddl_provider_registry.sql` — 3 FORCE-RLS tables, idempotent `IF NOT EXISTS`,
  manual `psql -f` apply. Notable design calls:
  - `provider_definitions` (table 1, §5): config-driven spec. `_global` read-share
    (USING: admin GUC OR own tenant OR `_global`) + write-lock (WITH CHECK: admin GUC OR
    own-tenant-AND-`tenant_id <> '_global'`) — the explicit anti-privilege-escalation
    exclude the kb_* tables lack. `cost_per_unit_micros BIGINT` (micro-USD, no floats).
    gin index on `capabilities`; `(tenant_id, slug)` UNIQUE.
  - `provider_credentials` (table 2, §5): AAD-bound AES-256-GCM `ciphertext bytea` +
    `key_aad` + `scope` (`integration`=vendor-revealable | `ai_provider`=platform-masked);
    strictly per-tenant RLS (NO `_global` read-share — creds are always tenant-private).
  - `provider_health_log` (table 3, §5): append-only. **Design change vs spec text:** the
    spec said `REVOKE UPDATE, DELETE`, but the FK `ON DELETE CASCADE` to provider_definitions
    needs famit_app's DELETE priv for a legit def-delete to cascade (proven: a blanket REVOKE
    aborts the def delete with "permission denied"). Replaced with a `BEFORE UPDATE OR DELETE`
    trigger `provider_health_log_append_only()` that raises on any UPDATE and on a DELETE at
    `pg_trigger_depth() <= 1` (direct app delete) but allows depth>1 (FK cascade). Same end
    state the spec wants ("health-log UPDATE/DELETE blocked") without breaking def deletion.
- `droplet_work/provider_registry/__init__.py` — import-guarded shell; re-exports the W1
  surface (`is_enabled`, `registry_config`, `FLAG_ENV`, all dataclasses/enums). `0.1.0-w1`.
- `droplet_work/provider_registry/config.py` — call-time `os.environ` reads (mirrors
  `droplet_work/config.py`), empty-env safe, never raises at import. `is_enabled()` default
  OFF; `registry_config()` snapshot (health interval/fail-threshold=3/backoff-base=60,
  SSRF allow-hosts + block-self-hosted, `VAULT_BACKEND` default `local`). NEVER returns a secret.
- `droplet_work/provider_registry/schema.py` — pure stdlib (dataclasses/enum/typing). Enums:
  `Capability`/`TransformType`/`ProviderType`/`AuthScheme`/`CredentialScope`. Dataclasses
  `ProviderDef` (+ `is_global`) / `ProviderCred` (+ `is_revealable_by_vendor`, + the canonical
  `expected_aad(tenant, def_id, ver) = "{t}||{d}||{v}"` AAD formula). Lenient `from_any` (DB
  row → dataclass, tolerates missing/extra keys, preserves forward-compatible unknown enum
  values verbatim). No I/O; never raises.
- (uncommitted scratch) `droplet_work/db/_probe_provider_rls.sql` — the RLS probe; left
  untracked (gitignored + a probe, not a deliverable).

**RLS proof (live box, famit_app via GUC, 12/12 PASS):**
```
A_sees_own=1 · A_health_inserted=1
B_sees_A_defs_xtenant=0 · B_sees_A_health_xtenant=0 · B_sees_A_creds_xtenant=0   (cross-tenant SELECT iso)
B_reads_global=1        (_global read-share)
B_global_writelock=PASS_blocked   (RLS WITH CHECK blocks non-admin _global insert)
health_direct_update=PASS_blocked · health_direct_delete=PASS_blocked  (append-only trigger)
A_def_deleted=PASS · A_health_cascade_gone=PASS  (legit def delete + FK cascade)
remaining_probe=0       (self-cleaned)
```
FORCE-RLS state: `provider_definitions/credentials/health_log` all `relrowsecurity=t` +
`relforcerowsecurity=t`. Tables present in `pg_tables`. Backup: box has NO scheduled pg_dump
cron (whole-DB pg_dump is the FORTRESS-recipe backup mechanism); a plain `pg_dump famit`
includes all 3 `provider_*` tables (`CREATE TABLE provider_` count = 3) — public schema, no
exclusion → auto-covered.

**Shell smoke (local, empty env):** py_compile OK on all 3 files; `import provider_registry`
on `env -i` → version `0.1.0-w1`, `is_enabled()`=False; flag flip `=1`/`=true`→True, `=0`→False;
`ProviderDef.from_any` round-trips (is_global/type/transform coerce correctly);
`ProviderCred.is_revealable_by_vendor` False for `ai_provider`; AAD formula `t1||def-1||1`.

**No caller.py edit. No service restart. Flag stays OFF.** gitleaks staged = 0.

## W2 — guard + adapter + named-transforms + creds (offline)

**Status:** ✅ DONE (local + offline tests green). Local-only; NO mount, NO box write, flag OFF.

**Deliverables (all on disk, `droplet_work/provider_registry/`):**
- `ssrf_guard.py` — `validate_endpoint(host,port,scheme)` HARD gate: host/port/scheme split,
  DNS-resolve-ALL, RFC1918/loopback/link-local/metadata/reserved denylist, IP-literal
  canonicalize (defeats hex/octal/dword/IPv6-mapped/NAT64), `revalidate_redirect_location`
  (redirect-deny hook), injectable resolver, never raises.
- `adapter.py` — 3-tier transform `build_request`/`parse_response`: Tier-1 openai_compat,
  Tier-2 named_provider dispatch, Tier-3 custom_field_map with a TINY inline JSONPath subset
  (`$.a.b` / `$[0]` / `$['k']`, depth≤5, ≤64 entries, NO eval/Jinja/wildcard/recursion);
  `validate_field_map` is the ONLY write-time raiser.
- `named_transforms.py` — REGISTERS the existing `media_gen/video/providers` builders verbatim
  (fal/replicate/luma/higgsfield/selfhost/generic, import-guarded) + pure-local anthropic/gemini
  text transforms. REUSE, never rewrite.
- `credentials.py` — AAD-bound AES-256-GCM (`encrypt_credential`/`decrypt_credential`,
  AAD=`tenant||def_id||version`, nonce-prepended), via an injectable `get_key` seam (interim
  Fernet-era derives sha256 of the existing box keystore secret); InvalidTag propagates on a
  cross-tenant ciphertext copy (no plaintext). `mask()` for the UI.
- tests: `test_ssrf_guard.py` + `test_adapter_fieldmap.py`.

**Two W2 correctness bugs found + fixed making the suite green (16/16 adapter + ssrf):**
1. `_auth_headers` leaked the dataclass bearer-default `auth_value_tmpl="Bearer {key}"` into the
   `api_key_header` scheme → `x-api-key: Bearer <key>` instead of the raw key. Fix: added
   `_DEFAULT_BEARER_TMPL` sentinel; a non-bearer scheme treats that default as "unset" and uses
   its own scheme-appropriate default; a genuinely custom template is still honored.
2. `_envelope_to_video_brief` left `webhook_url` in `brief.extra`, which `_common_input`'s
   `d.update(brief.extra)` then leaked into the fal/replicate body → drift from the
   `providers.build_submit` golden (webhook is the explicit 5th arg + URL-appended). Fix: exclude
   `webhook_url` from `extra`. Now the named-`fal`/`replicate`/`luma` builds BYTE-MATCH the golden.

**Verify:** `python -m pytest provider_registry/tests/ -q` → `2 passed`; py_compile OK on all
W2 files. gitleaks staged = 0. Earner UNTOUCHED (no box write; agent.py never imported).
Commit `8f9464c` on `fe/unify-run-wavec`.

## W3 — resolve + health + reveal (offline)

**Status:** ✅ DONE (local + offline tests green). Local-only; NO mount, NO box write, NO service
restart, NO deploy, flag `PROVIDER_REGISTRY_ENABLED` OFF. The firewall reveal scope is built
LOCALLY only — it deploys with the W4 mount (box firewall.py stays `cd1ac5d1`).

**Deliverables (all `droplet_work/`):**
- `provider_registry/store.py` — tenant reads, `is_admin=False` HARDCODED (RLS surface). Lazy
  `db.engine` import + `available()` guard + `_query` under `engine.session(tenant_id, is_admin=
  False)` (GUC-in-txn, mirrors ai_manager/store.py). `list_definitions(capability, enabled_only)`
  ordered priority-asc (the fallback chain) using `capabilities @> jsonb` containment;
  `get_definition`/`get_definition_by_slug` (tenant override beats `_global`);
  `get_active_credential` (highest active key_version, rotation-aware) + `list_credentials_masked`.
  NEVER decrypts; NEVER returns plaintext; degrade-to-empty on PG-down (strangler).
- `provider_registry/admin_store.py` — super-admin reads, `is_admin=True` (the `app.is_admin='1'`
  RLS leg), mounted ONLY under require_super_admin (W4). `list_all_definitions` /
  `get_any_definition` / `get_any_credential` (the audited reveal-path ciphertext fetch). Reuses
  `store._engine`; never decrypts.
- `provider_registry/registry.py` — **`get_provider(tenant_id, capability, routing_hint,
  *, get_key, now_fn) -> ProviderClient`** = the single capability-keyed resolution point. Order:
  flag-OFF→`registry_disabled` · PG-down→`not_configured` · list enabled defs (RLS own+`_global`,
  priority asc) · routing_hint slug pinned first · SKIP circuit-open (`health.is_open`) · first
  with a usable credential (decrypted ONLY via the `credentials.decrypt_credential` get_secret
  seam, AAD-bound) wins · auth_scheme='none'→usable w/o cred · else `no_credential`/`not_configured`.
  NEVER raises (a problem → ok=False, the consumer falls back). `ProviderClient` holds the plaintext
  in-process only, repr-suppressed, never logged. `resolve_status` = non-secret UI diagnostic.
- `provider_registry/health.py` — in-memory circuit breaker (§2f): per (tenant,def) state in a
  process-local locked dict (NO PG on the hot path). 3 consecutive fails → OPEN; backoff doubles
  60→120→240 (capped 1h); half-open trial after the window; a success closes + resets. Injectable
  `now_fn` (deterministic offline). `run_probe(prober, log_writer)` orchestrator drives the breaker
  from a (real W4 SSRF-guarded / fake offline) prober; best-effort health-log write never affects
  the breaker.
- `firewall.py` (DEPLOYED file — box md5 `cd1ac5d1` == local, confirmed byte-identical; **extended
  ADDITIVELY, NOT deployed**) — NEW `provider.reveal` step-up pair, fully isolated from the generic
  path: `mint_reveal_step_up(tenant, provider_def_id)` (60s TTL, `aud=provider_def_id`,
  fresh 16-byte jti) + `consume_reveal_step_up(token, provider_def_id, expected_sub)` (verify
  sig+exp+type+scope+F3-sub+aud, then **CONSUME the jti single-use** — replay→None). Single-use
  state in its OWN file `var/provider_used_jti.json` (never touches pins.json/pin_lockout.json),
  pruned at 2×TTL. **Fix found:** PyJWT auto-validates an `aud` claim and raises
  `InvalidAudienceError` even without `audience=`; resolved by `options={"verify_aud": False}` +
  explicit self-check (sig+exp still verified). This closes the live jti-replay gap for the reveal
  path (the generic `verify_step_up_token` mints a jti but never consumes it — left UNCHANGED).
- tests: `provider_registry/tests/test_reveal_stepup.py` (10/10) +
  `provider_registry/tests/test_registry_offline.py` (10/10).

**Offline proofs (the wave's required returns):**
- **resolve RLS (A never gets B):** a fake `db.engine` ENFORCES the §5 RLS GUC in Python.
  `get_provider(A,'video_gen')` → A's `a-fal` (priority 10); `client.tried` NEVER contains B's
  `b-fal`. `store.list_definitions(A)` owners exclude B; `store.get_active_credential(A, DEF_B)`
  → None (creds strictly tenant-private, no `_global` share).
- **cross-tenant ciphertext copy → skipped:** B's sealed-under-B blob pasted into A's DEF_A row →
  `decrypt_credential` recomputes AAD `A‖DEF_A‖1` ≠ seal AAD `B‖DEF_B‖1` → `InvalidTag` → that
  provider is SKIPPED, A falls back to DEF_A2 (B's key is NEVER returned as A's).
- **circuit-open fallback by priority:** 3 fails open DEF_A (priority 10) → resolve falls back to
  DEF_A2 (priority 50); `a-fal` is in `client.tried` (tried + skipped).
- **jti-replay → 403:** `consume_reveal_step_up` succeeds once, the SAME token (same jti) → None
  (single-use). Plus aud-mismatch→None, F3 sub-mismatch→None, generic-token-can't-reveal,
  reveal-token-can't-satisfy-generic, expired→None, no-jti→None.
- **existing-firewall UNCHANGED golden:** `diff <box-golden cd1ac5d1> firewall.py` = a single
  contiguous insertion `339a340,473`, **0 deletion/modification lines**; the generic
  mint/verify/PIN/change/lockout/classify behavior tests = PASS (byte-identical behaviour).
- `not_configured` (no provider) + `registry_disabled` (flag OFF) + PG-down degrade all return
  ok=False without raising. Empty-env import = clean, version `0.3.0-w3`, flag default OFF.

**Verify:** `python -m pytest provider_registry/tests/ -q` → **4 passed** (W2 + W3, ~36 assertions).
py_compile OK on store/admin_store/registry/health/firewall. gitleaks staged = 0.

**EARNER GATE (before + after, PASS):** agent.py md5 `9150fabe4ff62b4b4470f9a87df346e5` UNCHANGED ·
famit-agent PID `1477083` alive (python), NOT restarted · box firewall.py still `cd1ac5d1` (reveal
scope NOT deployed — W4 mounts) · caller `/health` (8209) = 200 · NO ring (offline wave, no calls).

---

## W1-W3 INTEGRATED VERIFY — 2026-06-14 ✅ ALL GREEN

**Triggered by:** serialized handoff verification before W4 (caller.py mount).

### Per-item PASS/FAIL

| Item | Result |
|---|---|
| 3 tables FORCE-RLS live (`relrowsecurity=t` + `relforcerowsecurity=t`) | ✅ PASS — all 3 confirmed via `pg_class` on live box |
| health-log append-only trigger exists | ✅ PASS — `provider_health_log_append_only_trg` present in `pg_trigger` |
| cross-tenant SELECT = 0 (RLS iso) | ✅ PASS — proven W1 RLS probe 12/12 + W3 offline AAD-copy test |
| SSRF full suite | ✅ PASS — `test_ssrf_guard.py` (16 assertions) in 4-suite run |
| adapter 3-tier (openai_compat/named/custom_field_map) | ✅ PASS — `test_adapter_fieldmap.py` (16 assertions) |
| named-builder byte-match (`providers.py` golden) | ✅ PASS — covered in adapter suite (webhook_url bug fixed W2) |
| AAD cross-tenant → `InvalidTag` | ✅ PASS — `test_registry_offline.py` (10 assertions) |
| get_provider RLS (A never gets B) | ✅ PASS — `test_registry_offline.py` |
| circuit-open fallback by priority | ✅ PASS — `test_registry_offline.py` |
| jti single-use (replay→None/403) | ✅ PASS — `test_reveal_stepup.py` (10 assertions) |
| existing firewall PIN/step-up byte-identical golden | ✅ PASS — `diff box-golden local` = 0 deletion/modification lines (`339a340,473` only) |
| **Total offline suites** | **4 passed / 0 failed** (run 2026-06-14) |
| py_compile all provider_registry + firewall | ✅ OK |
| gitleaks staged | ✅ 0 leaks |

### Earner Gate (fresh, 2026-06-14)

| Check | Result |
|---|---|
| agent.py md5 | `9150fabe4ff62b4b4470f9a87df346e5` UNCHANGED |
| famit-agent MainPID | `1477083` active (python), NOT restarted |
| box firewall.py md5 | `cd1ac5d1a57d26363d683ed2f11250ce` (reveal scope NOT deployed — W4 mounts) |
| caller `/health` | 200 |
| 5xx | 0 |
| ring | NO ring (offline wave) |

### W4 Readiness

All W1-W3 offline proofs confirmed. W4 is the **first caller.py MOUNT** of the registry —
additive, flag `PROVIDER_REGISTRY_ENABLED` default OFF, earner-gated. W4 MUST be serialized
against RAG (currently LIVE+DEPLOYED), Vault (deferred), and Video waves (only ONE caller.py
edit in flight at a time). W4 deliverable: `provider_registry/endpoints.py` + caller.py import
block; resting state byte-identical (route table probe + golden exit 0); legacy-pw→403 on
`/admin/providers/*`; earner gate PASS before + after.
