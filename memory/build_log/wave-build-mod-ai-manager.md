# WAVE BUILD — module `ai-manager` (AI Manager voice/chat command center)

Built 2026-06-10. Spec: `design/platform-ai-manager.md`. Module dir: `droplet_work/ai_manager/`.
Append-only build record. ADDITIVE, NO git (orchestrator commits), NO spine edits, NO deploy.

## WHAT IT IS
The voice-first (and chat) COMMAND CENTER — the platform's highest-privilege human-facing surface. A
registered number speaks a natural command; a DETERMINISTIC state machine VERIFIES identity -> loads
business context -> checks permission -> demands a FRESH SCOPED PIN/OTP for risky actions -> DELEGATES to
the AI-Workforce role agents -> executes across modules -> reads the result back. The LLM only FILLS SLOTS;
risk class, permission, PIN check, confirm read-back, and delegation routing are ALL deterministic code.

## FILES CREATED (all NEW under droplet_work/ai_manager/)
- `__init__.py`          — public surface: run_command_offline, CommandMachine, status(), get_router()
- `config.py`            — env-driven config; all flags default to SAFE/dormant; var-dir overridable
- `registry.py`          — registered-number store (JSONL, last-write-wins) + per-number grants; TENANT-SCOPED
- `identity.py`          — caller-ID resolve + RBAC permission table (role x grant, default-deny) +
                           DETERMINISTIC risk classifier (money|bulk|destructive|safe)
- `firewall_bridge.py`   — thin wrapper over REAL firewall.py (check_pin/mint_step_up/verify_step_up_token);
                           authenticate() does BOTH S2 login + S6 scoped step-up; fail-CLOSED
- `audit_bridge.py`      — wrapper over REAL audit.py; prefix `aimanager_voice.`, channel "ai"; secrets redacted
- `delegate.py`          — intent -> WORKER role -> workforce.run_agent (IN-PROCESS); map_intent_to_action;
                           read_context; carries step-up token + pre_approved into the runner's task
- `state_machine.py`     — THE machine (S0..S_END); channel-agnostic (injected transport+recorder);
                           PIN-audio suppression via recorder.pause/resume; lockout; full audit trail
- `intent/driver.py`     — provider-agnostic intent parser; default `none` => deterministic keyword matcher
                           over a CLOSED ENUM; groq/claude branches inert-but-wired (DORMANT)
- `otp/sender.py`        — provider-agnostic OTP (twilio|msg91|whatsapp|none); DORMANT => voice-PIN fallback
- `endpoints.py`         — FastAPI APIRouter, 9 routes, DEFINED-NOT-MOUNTED; import-safe (FastAPI optional);
                           auth via lazy caller.resolve_tenant/can; service-token + step-up on risky routes
- `inbound_agent.py`     — DEFERRED LiveKit persona stub (import-safe, NO livekit dep); documents the seam
- `wiring/caller_endpoints.diff` — un-applied: try/except include_router(ai_manager router)
- `wiring/sip_dispatch.md`       — un-applied ops recipe: inbound SIP trunk + dispatch rule -> agent "manager"
- `tests/test_offline.py`        — offline acceptance (spec §9); 8 tests; REAL firewall + REAL audit + stubs
- `AI_MANAGER_STATE.md`          — state ledger + the spec corrections folded

## WHAT IT COMPOSES (the built foundation — IN-PROCESS, not HTTP)
- F4 `firewall.py`  — PIN store (salted sha256) + HS256 scoped step-up token (F3 sub-binding). Used for
  S2 login-auth AND fresh per-action S6 step-up. Module imported directly (same as workforce.default_deps).
- `audit.py`        — immutable append-only JSONL ledger; every transition recorded as `aimanager_voice.*`.
- `workforce/` (AI-Workforce framework) — DELEGATION TARGET. delegate.py maps intent -> a worker role
  (telecaller|whatsapp|ad|strategist|analytics|ops) and calls `workforce.run_agent(role, task, ctx,
  trigger="manager_voice")`. The runner re-runs its OWN guardrails (scope/caps/kill-switch/DND/idempotency)
  + the ACID wallet (defense in depth) — voice is NOT trusted to be the only gate. PROVEN end-to-end:
  delegate.execute('analytics.read') drove the real AgentRunner and returned a real run_id.
- `brain` (Business Brain) — read_context() pulls the profile for the S3 greeting/headline (degrade-safe).
- F4 `wallet.py`    — inherited via the runner; voice owns NO money math.

## ROUTER ENDPOINTS (for the later mount — wiring/caller_endpoints.diff)
| Method | Path | Auth |
|---|---|---|
| GET  | /ai-manager/status                  | manager+ |
| POST | /ai-manager/numbers                 | manager+ (sends ownership OTP, dormant) |
| POST | /ai-manager/numbers/{id}/verify     | manager+ |
| GET  | /ai-manager/numbers                 | manager+ (tenant-scoped list) |
| GET  | /ai-manager/numbers/lookup?phone=   | SERVICE TOKEN (voice worker caller-ID hop) |
| POST | /ai-manager/numbers/{id}/grants     | admin + step-up |
| POST | /ai-manager/numbers/{id}/revoke     | admin + step-up |
| POST | /ai-manager/sessions                | SERVICE TOKEN (voice worker ships masked session) |
| GET  | /ai-manager/sessions                | manager+ (transcripts, PIN masked) |

## CREDS AWAITED (light up dormant modules; server-side only, never git — spec §10)
- Inbound telephony: `AIM_VOICE_DID`, `AIM_VOICE_SIP_TRUNK_ID` (reuse self-hosted LiveKit+SIP) + flip
  `AIM_ENABLED=true`. Activate via wiring/sip_dispatch.md.
- Intent LLM (pick one, or leave blank => deterministic stub): `GROQ_API_KEY` + `AIM_LLM_PROVIDER=groq`,
  OR `ANTHROPIC_API_KEY` + `AIM_LLM_PROVIDER=claude` (claude-opus-4-8; NO temperature/budget_tokens).
- OTP (only if verify_mode:"otp"): `TWILIO_*` (Verify) OR `MSG91_*` OR reuse Meta WA; `AIM_OTP_PROVIDER=...`.
- Cross-plane (ONLY if the voice worker is a SEPARATE host): `AIM_API_BASE` + `AIM_SERVICE_TOKEN`.
  In-process composition (current build) needs NONE of these.
- Per-tenant PIN: set via the existing firewall PIN-set path (var/pins.json).

## DEFERRED (named, not built)
1. `inbound_agent.py` LIVE LiveKit persona (entrypoint + VoiceTransport + WorkerOptions(agent_name=
   "manager")) — the "thin later wire" the task explicitly defers; stub is import-safe today.
2. LIVE intent LLM (groq/claude) in intent/driver.py — `_llm_parse` returns None (stub fallback) until then.
3. LIVE OTP send/verify (twilio/msg91/whatsapp) in otp/sender.py — returns deferred:activation_unit.
4. Mounting the router into caller.py (wiring/caller_endpoints.diff stays un-applied; orchestrator wires).
5. Cross-plane HTTP transport (registry/firewall/delegate HTTP clients) — only needed IF the voice worker
   runs on a SEPARATE host. The HTTP client is part of the deferred voice wire, not built here.
6. The live analytics readout join (leads/revenue/wallet) for query answers — wired when the brain blob lands.

## SPEC CORRECTIONS FOLDED (advisor-greenlit, against built source on disk)
- The spec's §3.2 cross-plane HTTP transport assumed firewall/workforce/audit were designed-only on a
  separate box. They are BUILT in the same droplet_work/ tree and the voice front is deferred, so this
  orchestration composes IN-PROCESS (import firewall/audit/workforce directly). HTTP seam kept dormant.
- Real firewall symbol is `check_pin` (NOT `verify_pin`); mint_step_up returns None if not init'd (handled).
- Delegate to a WORKER role (not bare `manager`, whose only scope `delegate` has no tool => unknown_tool).
- Action vocabulary = WORKFORCE tool-scopes (ads.set_budget, leads.enqueue_calls), NOT firewall.classify's.
- Dir = `ai_manager` (underscore) — task wrote `ai-manager`; hyphen isn't an importable package (repo
  precedent: WORKFORCE_STATE overrode `aiwf`->`workforce` for the same reason).

## VERIFICATION
`python -m pytest ai_manager/tests/test_offline.py -q` => 10 passed (zero keys/network/telephony):
dormant/import-safe; unregistered rejected with no context revealed; 3 wrong PINs -> lockout (no data
before auth); query answered with no step-up/no execute; risky -> step-up + confirm (amount read back) ->
execute WITH token attached (audit order authed->stepup_ok->execute); model self-labeled "safe" re-
classified money; permission denied (no PIN prompt, no execute); PIN absent from transcript + audit;
recorder paused/resumed around every secret span; ENGINE re-enforces caps (over-cap money action refused
by the runner is recorded executed:False / n_actions not incremented — defense in depth, spec §9.9);
garbage-to-parser -> clarify never a command. Full-package import smoke OK; caller.py/agent.py untouched.

## AUDIT-ACCURACY FIX (folded post-review)
state_machine S8->S9 originally hardcoded `executed: True` on every delegation. Corrected: `executed =
(runner status == "done")`; a parked/killed/not_configured/error result is recorded executed:False and
does NOT increment n_actions. The immutable session/audit record now reflects ground truth on the
highest-privilege surface. test_engine_reenforces_caps is the regression guard.
