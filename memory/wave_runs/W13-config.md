# W13 — Real-time Vendor Control Center + health-scored key pool/rotation (config seam)

Branch: `fix/realtime-voice-kernel-v2`. Disjoint tracked package: `voice_ops/config/`.
EARNER LAW honored: agent.py md5=98655dbf NEVER touched; caller.py live-patch is DOC-ONLY
(`design/W13-CONFIG-SEAM.md`). 0 droplet/agent imports at module load (all lazy).

## Goal (founder)
1. Real-time provider config + API-key ROTATION: add Groq/Sarvam/ElevenLabs/WhatsApp/telephony
   keys from the frontend → active IMMEDIATELY (no .env / restart / redeploy). HEALTH-SCORED key
   pool (capacity, rate-limit, latency, error-rate, reliability) → routes to healthiest key +
   instant failover, fail-LOUD not silent.
2. Vendor Profile / Control Center: per-vendor central config (human-handoff #, AI-Manager #,
   WhatsApp report-destination #, plan, phone numbers, provider-cred refs, retention policies,
   compliance) — FORCE-RLS, editable from frontend, live across workers/schedulers/agents.
3. Future-ready WhatsApp config (blank-but-present fields; activate when creds added).
4. Per-tenant retention/storage TTLs (recording vs transcript independent) — the layer W9
   (env-global) does NOT cover.

## Reuse seams (verified, file:line)
- AAD AES-256-GCM vault posture: copy `voice_ops/gcal/vault.py` (self-contained, tracked — must
  NOT import gitignored `droplet_work/provider_registry/credentials.py`). Same master-secret envs.
- Health pool primitive: `voice_kernel/providers/keypool.py` KeyPool (pick/report_failure/
  report_success/healthy_count). Router: `voice_kernel/providers/router.py` DefaultProviderRouter
  + build_provider_router factory (consumes pools dict).
- W8 EventBus: `voice_kernel.events` InMemoryEventBus / RedisEventBus; Event contract = (name,
  call_id, tenant_id, ts_iso, payload). Taxonomy append-only — ADD config_changed events.
- DB: lazy `from db import engine` → `eng.available()`, `eng.session(tenant_id=, is_admin=)`.
  Injectable store for tests (gcal `set_store_for_tests` pattern). FORCE-RLS DDL in module.

## Build plan / status
- [DONE] crypto vault (config/vault.py) — AAD AES-256-GCM, self-contained, no plaintext.
- [DONE] health pool (config/keyhealth.py) — capacity/ratelimit/latency/error/reliability score.
- [DONE] versioned real-time store (config/store.py) — version + cache-invalidate + RLS DDL + inject.
- [DONE] vendor profile model (config/profile.py) — Control Center fields + WA future-ready + retention.
- [DONE] provider-key store (config/keys.py) — encrypted key CRUD → feeds router pools live.
- [DONE] events (config/events.py) — config_changed via W8 bus, fail-soft.
- [DONE] router bridge (config/router_bridge.py) — build live router from key store, fail-loud failover.
- [DONE] config/__init__.py public surface.
- [DONE] tests (config/tests/test_config.py) — all green.
- [DONE] design/W13-CONFIG-SEAM.md seam DOC.
- [DONE] pytest voice_ops/ + voice_kernel/ green.

## Tests proven
added key joins rotation live; unhealthy key skipped + failover LOGGED (never silent); vendor-config
change propagates (version bump + cache invalidate + event); tenant-isolated (cross-tenant ciphertext
InvalidTag + RLS DDL); secrets never plaintext (mask + encrypted at rest); 0 droplet/agent imports.
