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

## Phase: VERIFY + RED-TEAM FOLD (2026-06-18)
- RECONCILE-FIRST: BUILD already in HEAD as `b30f9de`. This phase re-ran every gate and folded the
  red-team BLOCKER, committed as `e98cd2f` on `fix/realtime-voice-kernel-v2`.
- GATES (all green):
  - `python -m pytest voice_ops/` = 151 passed
  - `python -m pytest voice_kernel/` = 321 passed / 0 failed
  - W13 config suite = 24 passed (23 + 1 new regression)
  - import isolation = NONE (clean-process probe: `import voice_ops.config` pulls 0
    livekit/agent/caller/droplet/elevenlabs/sarvam/groq/openai/torch/numpy modules)
  - EARNER LAW: `droplet_work/agent.py` md5 `98655dbfc71d5c3da36bcfe3f848082c` UNCHANGED;
    not edited/imported/restarted; caller.py/aim_voice_agent.py not edited.
  - gitleaks `protect --staged` = 0 (no leaks; ~2.97 KB scanned).
- BLOCKER-1 (FIXED, folded in `e98cd2f`): bad/rotated/missing key caused a SILENT-then-CRASH.
  `keys.ProviderKeyStore.decrypt` (the only place plaintext is materialized) raised straight through
  on (a) founder ROTATES `FAMIT_KEYSTORE_SECRET`, (b) on-disk/row ciphertext TAMPER/corruption,
  (c) master secret ABSENT in a worker env — crashing the live voice path instead of returning the
  documented ResolvedKey(found=False) + key_pool_exhausted.
  FIX at `voice_ops/config/keys.py:186-196`: wrap base64+decrypt_secret in try/except → log LOUD
  (fingerprint + error TYPE only, NEVER the secret/ciphertext) → return None; resolve_key's existing
  decrypt-miss path drives clean failover / KEY_POOL_EXHAUSTED.
  Regression test: `tests/test_config.py::test_decrypt_failure_fails_closed_not_crash` (rotation AND
  missing-secret both → found=False, no crash, no plaintext in the signal, KEY_POOL_EXHAUSTED emitted) = PASS.
- Red-team axes verified CLEAN: secret-leakage (canary in no repr/list/fingerprints/health/rows/events),
  tenant isolation (AAD tenant|provider|version GCM → cross-tenant/cross-provider InvalidTag → fail-closed;
  FORCE-RLS config_state), live propagation w/o redeploy (≤1s version-poll belt + config_changed event
  suspenders; atomic single-statement version-bump UPSERT; fail-soft emit).
  LiveProviderRouter.key_for routes through guarded KeyRouter.resolve_key (inherits the fix); on_error safe.
- STAGED ONLY: voice_ops/config/keys.py + voice_ops/config/tests/test_config.py (the only dirty W13
  files; design/W13-CONFIG-SEAM.md + this wave-log already committed in b30f9de). Never `git add -A`;
  left untracked voice_ops/{compliance,db,telephony}/ + W12 tests for their own waves.
- NO box deploy (founder-gated seam per design/W13-CONFIG-SEAM.md). Did NOT edit ORCHESTRATOR.md.
- COMMIT: `e98cd2f` feat(ops): W13 real-time provider config + key-health rotation/failover + vendor control center + retention
