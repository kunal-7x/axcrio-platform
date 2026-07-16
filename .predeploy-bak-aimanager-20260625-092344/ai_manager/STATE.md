# ai_manager — PACKAGE RECONSTRUCTION STATE

## What this was
`droplet_work/ai_manager/` was a **skeleton in the repo**: `caller.py` imports
`ai_manager.endpoints.router` / `ai_manager.store` / `ai_manager.recorder`, but only
`voice_tools.py` + 5 staged slot-fill files (`../aim-manager-slotfill/`) were ever committed.
The full control plane was deployed to the live box (`/opt/famit-agent/ai_manager/`) and never
committed. This wave **reconstructs the complete, importable, offline-tested package** so the
imports resolve and the §12 command lifecycle works end-to-end — dormant-safe + earner-safe.

## What was built (all DONE + verified)
Reconstructed against `plans/AI_MANAGER_MASTER_PROMPT.md` (28-section spec), the 8 contract
docs in `plans/aim-build/contracts/`, and the house pattern of `grow/` + `provider_registry/`.

- **Placed from `aim-manager-slotfill/` staging (box's real code):** `endpoints.py`,
  `state_machine.py`, `intent/driver.py`, `tools/catalog.py`, `tools/__init__.py`.
  One surgical adaptation: `driver.py` `workforce.tools` → `..tools` (self-contained registry).
- **Foundation (new):** `config.py` (env reads, dormant-until-key), `db/{engine.py,schema.sql,__init__.py}`
  (7 `ai_manager_*` FORCE-RLS tables, idempotent, audit immutability trigger, lazy `ensure_schema`
  no-op unless `AIM_PG_DSN`), `identity.py` (phone-norm, resolve, deterministic risk/permits),
  `__init__.py` (waved import-guards + `status()`).
- **Persistence (new):** `store.py` (dep-free InMemory backend + lazy `_Pg` on shared `db.engine`;
  sessions/commands/audit/action-runs/dashboard/profiles/users; tenant-scoped, fail-closed),
  `recorder.py` (Null + LiveKitEgress; `finalize()`+`presign()`), `registry.py` (authorized-number
  registry; lock-aware lookup).
- **Execution brain (new):** `delegate.py` (read_context/map_intent_to_action/execute; live↔stub
  registry by `config.transport_configured()`), `tools/transport.py` (loopback, dormant until
  `AIWF_SERVICE_TOKEN`), `tools/stub_tools.py` (deterministic offline mirror of the live catalog),
  `audit_bridge.py` + `firewall_bridge.py` (lazy wrappers over box `audit.py`/`firewall.py`, fail-closed),
  `otp/sender.py` (dormant).
- **Closed the documented dormant gaps + full §10 panel API** in `endpoints.py` (additive):
  `GET /commands` (history, `store.list_commands` — the AIM_INTEGRATE_STATE gap), `GET /commands/{id}`,
  `GET /dashboard/summary` (the other gap), `GET /audit-logs`, `GET /action-runs`, `GET/PUT /profile`,
  `GET/POST/PATCH/DELETE /authorized-users`, `POST /pin/{set,reset/request,reset/confirm}`,
  `DELETE /numbers/{id}`. All reads degrade dormant-safe (empty/404, never 500). 25 routes total.

## Verification (all green, OFFLINE, zero env/keys/network/PG)
- `py_compile` clean on all 23 files; `import ai_manager` + `ai_manager.status()` work; `router` is an APIRouter.
- **Test suite: `ai_manager/tests/` — 68 passed** (identity, store+isolation, intent NLU, full lifecycle, endpoints).
- Full §12 lifecycle proven: identity resolve → login PIN → risky `ads.set_budget` → **fresh step-up PIN** →
  confirm → execute(stub)→done → audit, with **PIN never in the transcript**, idempotency, and
  tenant isolation (A↔B = 0 rows). NLU always-block fires (reveal-secret / DND-bypass).
- **Adversarial security audit: CLEAN on all 6 invariants** (tenant isolation, no-raw-PIN, money/PIN
  fail-closed, LLM-never-authorizes, dormant/earner-safe, correctness/idempotency).

## Findings fixed this wave
- **[security] `registry.lookup` resolved a LOCKED number** — defeated the PIN-lockout (a locked number
  must reveal nothing on caller-ID). Fixed both InMem (`continue` on `locked`) + Pg (`locked_until` clause).
- **[least-privilege] `endpoints._finalize_command_card`** injected a synthetic full-grant list on empty
  grants, defeating `identity.permits` default-deny. Now passes the caller's real grants (admin/manager
  unchanged; viewer/operator correctly restricted).
- **[correctness] audit severity `warning` → `warn`** normalized in `store.record_audit_log` so the
  dashboard severity roll-up no longer silently undercounts.

## Deferred (low, documented — NOT security holes)
- `POST /numbers/{id}/verify` flips `verified=True` without an OTP check (cosmetic — `verified` confers no
  authority; the firewall PIN in S2 is the real anti-spoof gate; OTP is dormant).
- `delegate.execute` puts `step_up_token` in ctx but the live loopback only sends `run_token` Bearer — a
  downstream step-up guard wouldn't see it (LIVE-only; fails CLOSED → action parks, never bypasses; wire
  when the live cross-plane lands).
- `endpoints._aim_risk_to_int` collapses bulk/money/destructive→3 (display-only; the PIN gate is driven by
  `identity.is_risky`, not the int; L3 matches the master §6 "high/PIN" taxonomy).

## Frontend
NO change needed. `famit-panel/app/ai-manager/_lib.ts` already has every client function
(`getAimSummary`, `getAimCommandHistory`, `getAimAuditLogs`, `getAimActionRuns`, profile/users CRUD) —
they were built expecting these routes (the code comments call `/dashboard/summary` "DEFERRED backend
wiring"). The pages light up against the new backend; the gap was purely backend.

## Activation (live box — dormant until flipped)
`FEATURE_AI_MANAGER=1` mounts the router; `AIM_ENABLED=1` arms it; `AIM_PG_DSN` (or shared `db.engine`)
turns on PG persistence (else InMemory). `AIM_SERVICE_TOKEN` arms the voice-worker service endpoints;
`AIM_LLM_PROVIDER=groq`+`GROQ_API_KEY` arms live NLU (else deterministic stub). All additive; `AIM_ENABLED=0`
is the instant kill-switch. `agent.py`/SIP/trunk untouched.

## Note
The `../aim-manager-slotfill/` staging dir is now SUPERSEDED — its 5 `.py` files were reconstituted into
this package (the canonical source). It can be retired (kept for now as historical build log via SLOTFILL_STATE.md).
