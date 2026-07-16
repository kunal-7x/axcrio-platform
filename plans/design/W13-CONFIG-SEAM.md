# W13 — Real-time Vendor Control Center + health-scored key pool: the live-reload SEAM

Status: **SEAM NOTE ONLY — NOTHING WIRED.** This wave built + tested the
`voice_ops/config/` package (disjoint, tracked, droplet-free). The earner is
byte-identical: `droplet_work/agent.py` md5 = `98655dbf` (unchanged); `caller.py`
/ `aim_voice_agent.py` untouched. Append-only additions were made to the W8
taxonomy (`config_changed`, `provider_key_added`, `provider_key_revoked`,
`key_pool_exhausted`) + exports — no existing W8 behaviour changed (471 tests
green across `voice_ops/` + `voice_kernel/`).

This file is the precise, file:line recipe for the SEPARATE, founder-signed
wiring wave — one box-mutating change, real-flow smoke (a real outbound call
rings before + after), revert path. Until then everything below is INERT.

---

## 0. The founder problem this closes

Today, adding a Groq/Sarvam/ElevenLabs/WhatsApp/telephony key, or changing a
vendor's handoff number / AI-Manager number / report number / plan / retention,
means editing `.env` on the box and RESTARTING — so it is NOT real-time and the
non-technical founder cannot do it from the panel. And the live key rotation is a
blind `itertools.cycle` (agent.py:79-85, 107-125) that keeps using a
rate-limited/dead key (silent failure). W13 fixes both:

- a panel-added key/secret becomes active IMMEDIATELY (no `.env`, no restart, no
  redeploy) and joins a HEALTH-SCORED pool that routes to the healthiest key and
  fails over instantly + LOUDLY;
- one central Vendor Control Center (handoff #, AI-Manager #, WhatsApp report #,
  plan, phone numbers, provider-cred refs, retention, compliance, future-ready
  WhatsApp) editable from the panel, live across workers/schedulers/agents.

## 1. What exists now (the built surface — all tracked, all tested)

- `voice_ops/config/vault.py` — `encrypt_secret / decrypt_secret / mask /
  fingerprint`. AAD-bound AES-256-GCM, self-contained re-impl of the W4
  `provider_registry/credentials.py` posture (which is GITIGNORED). SAME master
  secret env precedence (`PROVIDER_REGISTRY_KEYSTORE_SECRET` →
  `PROVIDER_KEYSTORE_SECRET` → `FAMIT_KEYSTORE_SECRET` → `CONFIG_VAULT_SECRET`)
  and SAME key-derivation → ciphertexts are byte-compatible with the live vault.
  AAD = `tenant|provider|version` ⇒ cross-tenant/cross-provider ciphertext fails
  closed (InvalidTag). Plaintext never logged.
- `voice_ops/config/store.py` — `ConfigStore` (versioned, cache-invalidating,
  tenant-scoped) over the FORCE-RLS `config_state` table (`RLS_DDL` in-module).
  `InMemoryBackend` + `set_backend_for_tests` for CI. Atomic version-bumping
  UPSERT (`RETURNING version`). Cheap version-poll throttle (`version_poll_ttl_s`,
  default 1s) so a hot reader picks up a change within ≤1s with ~zero cost.
- `voice_ops/config/keyhealth.py` — `HealthScoredKeyPool`: per-key
  capacity/rate-limit/latency/error-rate/reliability → composite score; circuit
  breaker (3 fails → open, 30→60→120→240s backoff like
  `provider_registry.health`); `pick()` returns the healthiest closed-circuit key
  (round-robin among ties) or `None` (LOUD). `snapshot()` = the health-badge data
  (NO secrets — fingerprints only).
- `voice_ops/config/keys.py` — `ProviderKeyStore`: encrypted key CRUD
  (`add_key/disable_key/enable_key/remove_key`), `list_keys` (masked, no
  plaintext), `fingerprints(provider)` (pool membership), `decrypt(provider, fp)`
  (the ONLY call-time plaintext materialization). Hot-reloads from the versioned
  store ⇒ a panel-added key shows up on the next read with no restart.
- `voice_ops/config/profile.py` — `VendorProfile` + `VendorProfileStore` (the
  Control Center) with `RetentionPolicy` (per-tenant recording vs transcript vs
  summary TTLs + storage quota — the per-vendor override W9's env-global
  `RECORDING_RETENTION_DAYS` lacks), `ComplianceSettings`, and future-ready
  `WhatsAppConfig` (`is_active(has_whatsapp_key)`).
- `voice_ops/config/router_bridge.py` — `KeyRouter.resolve_key(provider)` →
  `ResolvedKey(found, fingerprint, plaintext, reason)` (healthiest live key, LOUD
  failover); `report_success/report_failure/observe_latency/set_capacity`;
  `LiveProviderRouter` + `build_w5_router(tenant_id)` (a W5
  `DefaultProviderRouter` whose pools are seeded LIVE from the key store).
- `voice_ops/config/events.py` — `set_event_bus(bus)` + fire-and-forget
  `emit_config_changed / emit_provider_key_added / emit_provider_key_revoked /
  emit_key_pool_exhausted` over the W8 bus. A dead/throwing bus NEVER breaks a
  write (proven).

## 2. DDL to apply (mount step — alongside booking/rls.sql + gcal RLS_DDL)

```sql
-- from voice_ops/config/store.py : RLS_DDL
CREATE TABLE IF NOT EXISTS config_state ( ... );  -- FORCE ROW LEVEL SECURITY, policy on app.tenant_id
```

Apply with the admin GUC set (same path the wallet/gcal DDL uses). No data
migration: a tenant with no row gets a DEFAULT `VendorProfile` (blank fields,
lean plan) — nothing breaks for existing tenants.

## 3. caller.py seam (DOC ONLY — additive routes, do NOT edit the live file yet)

Mount a small router (mirror `provider_registry.endpoints.build_router` mounted
at `caller.py:7446`, and the gcal endpoints). All routes resolve the tenant from
the TOKEN (`resolve_tenant`, caller.py:404) — NEVER from the body — and gate
writes with `can(..., "manage_tenants")` / the existing role check.

```
# at startup (once), wire the event bus so config writes push live:
from voice_ops.config import set_event_bus
from voice_kernel.events import RedisEventBus           # already the W8 prod bus
set_event_bus(RedisEventBus())                          # same Redis the W8 wave uses

# Vendor Control Center
GET  /config/vendor-profile            -> VendorProfileStore().get(tenant).__dict__ (masked)
PUT  /config/vendor-profile            -> VendorProfileStore().put(VendorProfile.from_doc(tenant, body), updated_by=actor)
PATCH/config/vendor-profile            -> VendorProfileStore().patch(tenant, body, updated_by=actor)

# Provider keys (real-time rotation)
GET  /config/keys                      -> ProviderKeyStore().list_keys(tenant)          # masked, no plaintext
POST /config/keys                      -> ProviderKeyStore().add_key(tenant, body.provider, body.secret, label=, added_by=actor)
DELETE /config/keys/{provider}/{fp}    -> ProviderKeyStore().remove_key(tenant, provider, fp, actor=)
POST /config/keys/{provider}/{fp}/disable|enable

# Health badge (founder dashboard)
GET  /config/keys/health               -> KeyRouter(tenant).health()                    # scores, NO secrets
```

These are PURE-ADDITIVE (new path prefix `/config/*`); they touch no existing
route, no auth path, no dial path. Resting behaviour is byte-identical.

## 4. WORKER / SCHEDULER live-reload seam (no restart)

Any worker/scheduler that needs a vendor setting reads it through the store on
each unit of work — the version-poll makes this cheap and self-invalidating:

```
from voice_ops.config import VendorProfileStore, KeyRouter
prof = VendorProfileStore().get(tenant_id)            # ≤1s-fresh, cached, no restart
handoff = prof.human_handoff_number                   # live value
rec_ttl = prof.retention.recording_retention_days     # per-tenant TTL (W9 sweep reads this)

kr = KeyRouter(tenant_id)                              # one per tenant per process
rk = kr.resolve_key("groq")
if not rk.found:                                       # LOUD: pool exhausted / no keys
    log.error("no healthy groq key: %s", rk.reason)    # surfaced, never a silent default
    ... # fail loud / alert (key_pool_exhausted already emitted on the bus)
else:
    use(rk.plaintext)                                  # call-time only
    # on the response:
    kr.report_success("groq", rk.fingerprint, latency_ms=dt) or kr.report_failure("groq", rk.fingerprint, 429)
```

W9 retention sweep: replace the env-global `RecordingConfig.retention_days` read
with `VendorProfileStore().get(tenant).retention.recording_retention_days`
(and `.transcript_retention_days` for the transcript sweep). Strictly additive —
absent profile ⇒ defaults match today's env defaults (30 / forever).

## 5. agent.py bridge seam (the NEW realtime-voice-kernel-v2 path ONLY — never edit agent.py)

agent.py md5 `98655dbf` STAYS FROZEN. The new kernel-v2 dial path (the disjoint
code under `voice_ops/` / `voice_kernel/`, NOT the live `agent.py`) calls
`KeyRouter.resolve_key(...)` instead of the bare `itertools.cycle(_GROQ_KEYS)`
(agent.py:79-85) / `_SARVAM_CYCLE` (107-125) / `os.environ["ELEVENLABS_API_KEY"]`
(564). The live `agent.py` is left exactly as-is; the cutover to the v2 path is a
SEPARATE founder-signed wave with its own real-call smoke + revert.

## 6. Earner-safety + rollback

- agent.py md5 unchanged (`98655dbf`); caller.py/aim_voice_agent.py untouched.
- `set_event_bus(None)` (the default) ⇒ config writes still work, just no push
  (poll still catches changes) — so even a Redis outage can't block a save.
- Rollback = unmount the `/config/*` router + drop the `config_state` table (data
  is non-load-bearing for the live path until the worker/agent seams are wired).
- One box-mutating change at a time: (a) apply DDL + mount read-only GETs, smoke;
  (b) enable writes; (c) wire the W9 retention read; (d) cut the kernel-v2 key
  path. A real outbound call must ring before AND after each step.
```
