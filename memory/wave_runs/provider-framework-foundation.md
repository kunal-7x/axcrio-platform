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

---

**Next:** W2 — `ssrf_guard.py` + `adapter.py` + `named_transforms.py` (register the existing
`media_gen/video/providers.build_submit/parse_result` for fal/replicate/luma/higgsfield/
selfhost/generic) + `credentials.py` (AAD-bound interim Fernet via the get_secret seam).
Local + offline tests; no mount. Then W3 (resolve/health/reveal), then W4 (the caller.py mount,
serialized against RAG/Vault/Video).
