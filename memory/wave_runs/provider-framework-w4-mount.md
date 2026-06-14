# Provider Framework W4 — mount the connector API — wave run log

Spec: `design/PROVIDER-FRAMEWORK-PLAN.md` §8 (endpoints + flags) + §14 W4 (the caller.py mount).
Canonical branch `fe/unify-run-wavec`. Flag `PROVIDER_REGISTRY_ENABLED` default OFF (resting
byte-identical). Earner-safe: agent.py never imported/touched; only additive caller.py + the
additive firewall reveal scope deploy this wave. Serialized vs RAG/Vault/Video (only ONE edits
caller.py at a time — RAG done, voice-fix done; this is the next caller.py edit).

## START — earner gate BEFORE (2026-06-14) — IN PROGRESS

| Check | Result |
|---|---|
| agent.py md5 (box) | `9150fabe4ff62b4b4470f9a87df346e5` UNCHANGED |
| famit-agent MainPID | `1477083` (NOT restarted) |
| box firewall.py md5 | `cd1ac5d1a57d26363d683ed2f11250ce` (pristine — reveal scope NOT yet deployed) |
| box caller.py md5 | `52c59291584d948e258d264cd50206ae` |
| local caller.py md5 | `52c59291584d948e258d264cd50206ae` — **MATCHES box** (RECOVERY-STATE `592e6b94` was stale; inbound-voice-fix commits advanced it). Safe to edit from local = box golden. |
| local firewall.py md5 | `b77c2cbea7f6acbae22e1988ba4c0e91` = box golden `cd1ac5d1` + ONLY the additive W3 reveal scope (`diff` = `339a340,475`, **0 deletion/modification lines**). |
| caller `/health` (8209) | 200 |
| 5xx (caller, last 15m) | 0 |
| ring | NO ring (no calls placed) |

PLAN: build `provider_registry/endpoints.py` (token-deriving `build_router`) → mount in caller.py
under `PROVIDER_REGISTRY_ENABLED` (import-guarded + mount-guarded, default OFF) → deploy the W3
firewall reveal scope WITH the mount (golden the existing firewall byte-identical) → backup-first,
py_compile, restart famit-caller only → earner gate AFTER → commit fe/unify-run-wavec.

## W4 — mount the connector API — ✅ DONE + DEPLOYED (2026-06-14)

**Status:** ✅ DONE. Built `endpoints.py` (the token-deriving `build_router`), added the W4 WRITE
functions to `store.py`, mounted in caller.py under `PROVIDER_REGISTRY_ENABLED` (default OFF), and
DEPLOYED the package + the W3 firewall reveal scope to the box. Resting byte-identical (flag OFF →
routes 404/not-mounted). famit-caller restarted only; earner UNTOUCHED.

### THE ENDPOINTS (16 routes, prefix `/provider-registry`)
⚠ PREFIX is `/provider-registry`, NOT the bare `/providers` — caller.py already has a live
`@app.get("/providers")` (the legacy LLM-router provider list, caller.py:4124, which this framework
later STRANGLES per plan §3). A bare-`/providers` mount would be SHADOWED by that earlier-registered
route. The registry uses its OWN namespace = fully isolated + collision-free. FE maps to it.

| Method + path | Role | Behavior |
|---|---|---|
| `GET  /provider-registry` | tenant | list defs visible to tenant (own + `_global`, RLS), masked creds, circuit badge |
| `GET  /provider-registry/health` | tenant | per-provider circuit state + resolution diagnostic (non-secret) |
| `POST /provider-registry` | tenant(write) | vendor adds OWN hosted-api def (self_hosted→403; http→400 https-only); optional BYO key scope='integration' |
| `PUT  /provider-registry/{id}` | tenant(write) | update own def (`_global`→403; RLS-scoped); field-map validated |
| `DELETE /provider-registry/{id}` | tenant(write) | delete own def (cascades creds) |
| `POST /provider-registry/{id}/credential` | tenant(write) | AAD-encrypt + store own key (scope='integration', rotation-aware) |
| `POST /provider-registry/{id}/reveal-init` | tenant | mint a 60s aud-bound single-use provider.reveal step-up token |
| `POST /provider-registry/{id}/reveal` | tenant | reveal plaintext (X-Step-Up token, single-use jti; `ai_provider` scope→403; replay→403) |
| `POST /provider-registry/{id}/test` | tenant | SSRF-guarded test-connection (NO generation — list-models/health GET) + breaker update |
| `GET  /provider-registry/admin/all` | super-admin | list defs across ALL tenants + `_global` |
| `POST /provider-registry/admin` | super-admin | create def (may be `_global` OR self_hosted SSRF-validated); optional platform cred scope='ai_provider' |
| `PUT  /provider-registry/admin/{id}` | super-admin | update ANY def (self_hosted re-SSRF-validated) |
| `DELETE /provider-registry/admin/{id}` | super-admin | delete ANY def |
| `POST /provider-registry/admin/{id}/reveal` | super-admin | reveal ANY credential (any scope), step-up + single-use jti, audited |
| `POST /provider-registry/admin/{id}/test` | super-admin | SSRF-guarded test for any def (decrypts platform cred for the auth'd probe) |
| `GET  /provider-registry/admin/health` | super-admin | per-provider circuit state across all tenants |

### FILE:LINES
- `droplet_work/provider_registry/endpoints.py` (NEW, md5 local `ccdfb188`) — `build_router(
  resolve_tenant, can, need_auth, forbidden, *, require_super_admin=, firewall=, audit=)` at
  endpoints.py:~225. All routes token-derive the tenant (`resolve_tenant`), never body. Every route
  first checks `config.is_enabled()` → 404 when flag OFF (per-route defense-in-depth over the
  mount-guard). SSRF gate `_validate_self_hosted_ssrf` (endpoints.py:~135) + `_real_probe` (the
  no-generation, redirect-revalidated, SSRF-guarded test, endpoints.py:~175). Reveal step-up via
  `firewall.consume_reveal_step_up` (X-Step-Up header) — fail-closed if firewall absent.
- `droplet_work/provider_registry/store.py` (EXTENDED, md5 `5a497adc`) — added W4 WRITES:
  `create_definition` / `update_definition` / `delete_definition` (whitelisted cols, jsonb CAST,
  RLS WITH-CHECK enforces `_global` write-lock for non-admin) + `upsert_credential` (deactivate-then-
  insert, rotation-aware) + `write_health_row` (append-only, best-effort) + `StoreWriteError`. All
  run inside `engine.session(tenant_id, is_admin)`; the super-admin surface passes is_admin=True.
- `droplet_work/provider_registry/__init__.py` — W4 import-guard surface (`build_router`); version
  `0.4.0-w4`.
- `droplet_work/provider_registry/tests/test_endpoints_offline.py` (NEW) — 12/12 PASS.

### THE MOUNT (caller.py)
- caller.py:7309–7349 (additive insertion) — `try: from provider_registry.endpoints import
  build_router as _build_provreg_router` (import-guarded) + `PROVIDER_REGISTRY_ENABLED = cfg_get(...)
  default OFF` + `if PROVIDER_REGISTRY_ENABLED and _build_provreg_router is not None:` →
  `app.include_router(_build_provreg_router(resolve_tenant, can, need_auth, _forbidden,
  require_super_admin=require_super_admin, firewall=_firewall_mod, audit=_audit))` wrapped in a
  try/except that logs-and-continues (a mount failure can NEVER crash the spine). Mirrors the
  media-gen / workflow / forms settled mount pattern.
- **caller.py golden byte-diff:** box golden `52c59291` → deployed `310ea9c9` = single contiguous
  insertion `7309a7310,7349`, **0 deletion/modification lines** (purely additive).

### FIREWALL-UNCHANGED GOLDEN
- Deployed box firewall `b77c2cbea7f6acbae22e1988ba4c0e91` = pristine box golden
  `cd1ac5d1a57d26363d683ed2f11250ce` + ONLY the additive provider.reveal step-up insertion
  `339a340,475`, **0 deletion/modification lines**. Box smoke (venv python): generic
  `mint_step_up`+`verify_step_up_token` = PASS (byte-identical behavior); reveal single-use
  (mint→consume once→replay→None) = PASS.

### OFFLINE PROOFS (12/12 — `test_endpoints_offline.py`, green on box venv python too)
dormant-404-when-flag-OFF · super-admin gate honors require_super_admin denial (legacy-pw exclusion
path) · SSRF blocks self_hosted→metadata(169.254.169.254) + →localhost(127.0.0.1) · vendor cannot
create self_hosted (403) · custom_field_map eval-injection refused (400) · vendor create hosted+BYO
key with NO plaintext leak in the masked list · vendor hosted must be https (400) · reveal requires
step-up (403) · **reveal single-use then REPLAY→403** (single-use jti, the live replay gap closed) ·
platform `ai_provider` scope NOT vendor-revealable (403) · RLS-scoped update→delete→404.

### DEPLOY (FORTRESS recipe, famit-caller-only)
Backups: `caller.py.W4bak.20260614-210229` + `firewall.py.W4bak.20260614-210229` on box.
SCP md5-gated (all local==box). Box py_compile OK (venv python). Atomic swap caller.py+firewall.py.
Restarted **famit-caller ONLY** (twice — once for the initial deploy, once after the prefix-collision
fix). Flag NOT added to `.env` (absent → default OFF → resting byte-identical). Package NOT on box
before W4 (W1-W3 were local-only; only the DDL was applied to PG).

### EARNER GATE (before + after, PASS)
| Check | Before | After |
|---|---|---|
| agent.py md5 | `9150fabe4ff62b4b4470f9a87df346e5` | `9150fabe4ff62b4b4470f9a87df346e5` UNCHANGED |
| famit-agent MainPID | `1477083` | `1477083` NOT restarted |
| caller `/health` (8209) | 200 | 200 |
| 5xx (caller) | 0 | 0 |
| ring | NO ring | NO ring (no calls placed) |
| registry routes (flag OFF) | n/a | `/provider-registry*` → 404 (dormant); legacy `/providers` → 401 (intact) |
| flag-ON in-process proof | n/a | `caller.app` mounts 16 registry routes (13 distinct paths) when `PROVIDER_REGISTRY_ENABLED=1` |

### ROLLBACK
Set flag→0 / leave absent (instant, no deploy — already the resting state). To fully remove: restore
`caller.py.W4bak.20260614-210229` + `firewall.py.W4bak.20260614-210229`, `rm -rf
/opt/famit-agent/provider_registry`, restart famit-caller. The 3 PG tables are additive (drop-safe).

### NEXT (W5)
Strangler cut-over VIDEO first (`REGISTRY_FOR_VIDEO`): `media_gen/video/client._resolve_key` asks
the registry, falls back to `config.fal_key(...)` on miss. The legacy `@app.get("/providers")`
LLM-router list is the eventual strangle target (plan §3) — left untouched this wave.
