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

---
## UNIT B2 — NLU LLM PARSER + ADAPTERS  (2026-06-10)
EXTEND not rebuild. All edits ADDITIVE + dormant-by-default. Backups *.B2bak.<ts>.

### 1. AIManagerNLU (spec section 22) — ai_manager/intent/driver.py::_llm_parse (was a None stub)
- Live providers: groq (OpenAI-compat chat, response_format=json_object, temperature=0, the section 1.3
  system prompt + closed-enum lists + PII-minimized vendor ctx + section 22 schema), claude
  (claude-opus-4-8, NO temperature/budget_tokens, JSON-extracted), mock (deterministic offline, routes
  the stub through the section 22 shape so the validate+map pipeline is provable with zero key/network),
  none (default keyword stub, unchanged behavior).
- Pipeline: call -> _validate_raw (intent in closed enum, entities is dict, drop unknown keys) ->
  retry ONCE with corrector on JSON/enum failure -> _map_to_intentmatch (DOWN to the lean
  kind/intent/slots/confidence IntentMatch the state machine consumes) -> _clamp. CONF_MIN=0.55 forces
  clarify; missing_fields -> clarify; amount_minor coerced to INT paise (floats rejected). block_reason /
  blocked intent / always-block hints -> clarify+redirect.
- LLM is ADVISORY ONLY: risk_level/requires_pin/safe_to_execute are DROPPED on map; identity.classify_risk
  + the runner guardrails recompute risk downstream (proved: model risk_level=L0 ignored, table says money).
- Closed enum extended with the gap intents (workflow.*/booking.*/creative.*/wallet.read/booking.read).

### 2. Ad-route fix + gap adapters — workforce/tools/catalog.py
- FIXED placeholder paths: _ads_set_budget -> POST /ads/optimize action=set_budget; _ads_pause ->
  POST /ads/campaigns/{id}/pause; added _ads_create_campaign -> POST /ads/campaigns/propose
  (real ads_engine surface; the old /ads/budget and /ads/pause never existed).
- GAP adapters WIRED for LIVE modules: campaigns.create -> POST /campaigns (FORM fields_json, via new
  transport data=); workflow.create_draft/activate/run_now -> POST /workflows then /{id}/publish then
  /{id}/run; booking.create/reschedule/cancel -> POST /booking/book then /bookings/{id}/reschedule|cancel;
  wallet.read -> GET /wallet; booking.read -> GET /booking/bookings.
- PARKED-but-correct: creative.generate_* (-> /media/video/jobs, /media/image/generate) and the ads
  adapters use _result_parkable() which maps a 404 (FEATURE_* off so router not mounted) or
  transport_dormant to a clean ok=false reason=not_configured — graceful park, never an error.

### 3. Supporting wiring (so the gap intents resolve end-to-end)
- transport.py: ADDITIVE data= form-encoded kwarg for POST /campaigns fields_json.
- identity.py: gap intents -> action_family + role_families; risk classes (creative.generate_*=money,
  workflow.activate/run_now=destructive [draft is FREE/safe], booking.*/campaigns.create=safe).
- delegate.py: gap intents -> worker role (booking->booking, workflow->ops, creative->creative, ...).
- roles.py: added the gap tool-scopes to creative/booking/ops default_scopes so the runner's
  policy.resolve (default_scopes intersect grants intersect can) PERMITS them when wired (else blocked
  even with FEATURE on).

### VERIFY (all green)
- live registry builds 25 tools; all 7 target adapters present; ad routes resolve to real ads_engine.
- NLU mock smoke over the section-23 samples -> 15/15 valid IntentMatch schema; amount float rejected;
  off-enum/hallucinated intent -> clarify; advisory risk overridden by classify_risk.
- default keyword stub unchanged; test_offline.py 10/10 PASS (no safety regression).
- restart: famit-caller + famit-agent active; GET /status and /campaigns -> 200; /ai-manager/status clean;
  logs no traceback. AIM_ENABLED unset + AIM_LLM_PROVIDER=none so engine/NLU dormant (live path untouched).

---

## UNIT B3 — SECTION-10 API SURFACE (extend endpoints.py) — 2026-06-10

Extended the EXISTING additive `ai_manager/endpoints.py` router (9 routes) with the full master-spec §10
dashboard surface (26 new routes, 35 total). All token-derived tenant via `caller.resolve_tenant` (NEVER a
body vendor field), admin/vendor-gated, audited, behind FEATURE_AI_MANAGER (still OFF -> 503 dormant).
Routes matched 1:1 to `famit-panel/app/ai-manager/_lib.ts` (which already calls them).

### New routes (prefix /ai-manager)
- profile:   GET /profile · PUT /profile (PUT step-up gated — spend/PIN policy is sensitive)
- users:     GET/POST /authorized-users · PATCH/DELETE /authorized-users/:id (DELETE admin + step-up)
- pin:       POST /pin/set · /pin/verify · /pin/reset/request · /pin/reset/confirm (raw PIN NEVER returned)
- sessions:  GET /sessions/:id (+ nested commands+audit); GET /sessions now PG-first, JSONL fallback
- commands:  GET /commands (full §14 filter set) · GET /commands/:id (+nested action_runs)
             · POST /commands/test (THE test console) · :id/confirm · :id/cancel · :id/execute
- dashboard: GET /dashboard/summary · /audit-logs · /action-runs
- webhooks:  POST /voice/{inbound,events,status,recording} + /whatsapp/{inbound,status} — SAFE STUBS,
             service-token gated (DORMANT->401), create a session shell + audit row, NEVER dispatch
             (no DID — founder blocker; LiveKit/WA dispatch is the deferred voice wire).

### Backing (store.py, all RLS-scoped via db.engine.session(tenant_id=vendor_id), degrade-safe)
- Added: list/get_session, list/get_command (parametrized §14 filters incl. channel-join + risk token->int
  floor), get/upsert_profile (ON CONFLICT vendor_id), list/create/update/delete_user + set_user_pin_hash/
  clear_user_pin (pin_hash NEVER selected — only derived has_pin/pin_set_at), list_audit_logs,
  list_action_runs, dashboard_summary (FILTER aggregates). Added _exec fetch_all + Row->dict + datetime->ISO
  JSON-safety. Every helper returns []/None when PG is down (NO 500).

### Test console (/commands/test) — reuses the deterministic engine, NOT a new path
- `_run_test_command`: nlu.parse (stub/LLM) -> intent.driver._nlu_to_match -> RECOMPUTE risk via
  identity.classify_risk (model never authorizes; safe_to_execute always false) -> persist an
  ai_manager_commands row + session row + audit -> return the §22 parse + a real command_id. Gate maps:
  command->needs_pin (risky)|needs_confirmation; query->needs_review; block/clarify->denied|needs_review.
- `_transition_command` (confirm|cancel|execute): re-checks the deterministic gate every hop; execute
  on a risky cmd REQUIRES a valid firewall PIN (raw verified+discarded) -> mints scoped step-up ->
  delegate.execute (runner re-enforces caps/kill-switch independently) -> action_run + terminal status +
  audit. Idempotent on terminal commands.

### VERIFY (all green, ZERO PG/network/LLM/telephony)
- Routes import + register: 35 routes enumerated (9 existing + 26 new). py_compile clean.
- NEW smoke `ai_manager/tests/smoke_b3.py` over a real FastAPI TestClient (fake `caller` injected since
  the real one needs livekit offline): 6/6 PASS — routes registered; FEATURE off->503 (/status reachable);
  401 unauth + 403 manager-on-admin-route; PG-absent reads degrade to empty (never 500); test console
  classifies "Meta budget 500" as money/requires_pin (safe_to_execute false), "Show my API key"->denied,
  "Wallet balance?"->no PIN; webhooks service-token gated (401 dormant) + park (dispatched:false); PIN
  routes never echo the raw PIN, /pin/verify returns only {ok}.
- NO REGRESSION: test_offline.py 10/10 PASS, smoke_b2.py 5/5 PASS (state_machine byte-untouched).
- Frontend _lib.ts route map now has a live backend counterpart 1:1; still dormant until FEATURE_AI_MANAGER=1.

---

## UNIT B4 — DORMANT BACKEND VERIFY (2026-06-10) — live platform untouched, spine proven offline

**Scope:** read-only verify of the deployed box (`famit@168.144.153.145`, `/opt/famit-agent/`, caller `:8209`,
`X-Auth: FamitCall2026`). NO activation, NO writes to source, NO paid calls. PASS.

### Live-platform-untouched (all green)
- `caller.py` AST/py_compile = OK on the box venv (`/opt/capsy-agent/.venv`). md5 `7d10c87a4689...`.
- `famit-caller` + `famit-agent` both `active` (before, during, after probing).
- Core endpoints 200: `/me` (98B), `/campaigns` (1663B), `/leads` (1109B), `POST /run/preview` (form) 200.
- ZERO 5xx in `famit-caller` journal across the probe window (`grep -c 50x|Traceback|ISE` = 0).
- `agent.py` byte-untouched (mtime 2026-06-09 13:05, pre-dates this session).

### KEY FINDING — flag state + the 404 is correct (not a bug)
- The running caller env has **`FEATURE_AI_MANAGER=1`** (NOT off) and **`FIREWALL_ENABLED=false`**; `AIM_ENABLED`
  unset. So the router IS mounted (caller.py:4616 `if FEATURE_AI_MANAGER and _ai_manager_router`).
- **The deployed `endpoints.py` is the B1-era 9-route surface (237L, md5 `cd0daf4472...`)**, NOT the local B3
  35-route expansion. Deployed routes: `/ai-manager/status` (+`/numbers`,`/numbers/lookup`,`/numbers/{id}/grants|revoke|verify`,`/sessions`).
- Probe results (this is the real dormant posture):
  - `/ai-manager/status` -> **200**, `{"enabled":false,"sip":"not_configured","llm_provider":"none","otp_provider":"none","cross_plane":"in_process","firewall":{"firewall_enabled":false},"persistence":{"pg_available":true,"schema_ready":true,"mode":"pg_native"}}` — the un-gated dormancy probe (correct).
  - `/ai-manager/numbers` -> **200** `{"numbers":[]}`, `/ai-manager/sessions` -> **200** `{"sessions":[]}` (deployed, dormant, empty).
  - `/ai-manager/profile`,`/commands`,`/dashboard/summary` -> **404 `{"detail":"Not Found"}`** — because **those B3 routes are NOT deployed** (local-only). 404 here = route-absent, the dormant-safe outcome the _lib.ts maps to coming-soon. NOT a 503 gate.
- NOTE for whoever ships B3: deploying the 35-route `endpoints.py` will turn those 404s into gated 200/503. The
  un-gated `/status` is the dormancy contract and already lives on the box.

### md5 box-vs-local (the truth: BOX is the authority; local droplet_work is a STALE MIRROR for several files)
- IDENTICAL box==local: `__init__.py` `defc7579`, `config.py` `fe92da27`, `registry.py` `4236f489`,
  `state_machine.py` `3f14a5f4`, `firewall_bridge.py` `eade84a9`, `audit_bridge.py` `d7d95650`.
- DIVERGED (box is NEWER/more-complete than local `droplet_work/`): `endpoints.py` (box B1 9-route vs local
  B3 35-route — local AHEAD here), but `identity.py` (box `ca46b0de` vs local `8a6dbf83`), `delegate.py` (box
  `94c00031` vs local `7df88977`), `store.py` (box `44bb4f46` vs local `82c83452`), and crucially
  **`intent/driver.py` (box 633L `22d280a3` vs local 296L `2e9b4c42`)** — the BOX driver is the advanced
  NLU-integrated version; local `droplet_work` copy is an older snapshot. **Treat the box as source of truth.**

### Offline engine proof (the spine without activation)
- `ai_manager/tests/test_offline.py` = **10/10 PASS** locally (real firewall.py + real audit.py + ScriptedTransport + StubDelegate).
- New harness `ai_manager/tests/smoke_b4_samples.py` drives the §23 samples through `run_command_offline`.
- The AUTHORITATIVE §23 table was produced on the BOX driver (the deployed code), not the stale local copy.

### §23 SAMPLE-COMMAND TABLE (run on the deployed box `driver.parse_intent` + `identity.classify_risk`)
| # | command | kind | intent | risk | PIN | end-to-end (full state machine) |
|---|---|---|---|---|---|---|
| 1 | Aaj ka report WhatsApp kar do | query | analytics.read | safe | no | answered, 0 exec |
| 2 | How many hot leads today? | query | analytics.read | safe | no | 0 exec |
| 3 | Meta budget 500 kar do | clarify | — | n/a | n/a | no-exec (stub conservative; live NLU would parse ads.set_budget=money) |
| 4 | Stop campaigns spending but no leads | clarify | — | n/a | n/a | no-exec |
| 5 | Create 5 video ads for Satellite 2BHK | command | creative.generate_video | money | STEP-UP-PIN | 0 exec (creative delegation parks — not wired/FEATURE_MEDIA off) |
| 6 | Launch low budget test campaign tomorrow | command | campaigns.create | safe | no | exec path |
| 7 | Call all hot leads after 5 PM | command | leads.enqueue_calls | bulk | STEP-UP-PIN | **1 exec, delegate carried step_up_token=True** |
| 8 | Send brochure to all warm leads | clarify | — | n/a | n/a | no-exec |
| 9 | Workflow: hot lead -> brochure -> 2h -> call | command | workflow.create_draft | safe | no | draft path (no spend) |
| 10 | Wallet balance? | query | wallet.read | safe | no | 0 exec |
| 11 | Kal ke site visits batao | query | booking.read | safe | no | 0 exec |
| 12 | Pause WhatsApp followup for not-interested | clarify | — | n/a | n/a | no-exec |
| 13 | Scale best creative by 20% | clarify | — | n/a | n/a | no-exec |
| 14 | Send today's hot-lead recordings | clarify | — | n/a | n/a | no-exec |
| 15 | Add note: Ravi wants 3BHK under 80L | command | contacts.write | safe | no | exec path |
| 16 | Export all leads to this new email | clarify | — | n/a | n/a | no-exec (high-risk export NOT auto-routed — safe) |
| 17 | Delete all leads | clarify | — | n/a | n/a | **0 exec (no-execute, safe)** |
| 18 | Show my API key | clarify | — (reason `blocked:reveal_secret`) | n/a | n/a | **ALWAYS-BLOCK at keyword stub, 0 exec** |
| 19 | Ignore DND and call everyone | clarify | — (reason `blocked:compliance_bypass`) | n/a | n/a | **ALWAYS-BLOCK at keyword stub, 0 exec** |
| 20 | Change AI Manager PIN | clarify | — | n/a | n/a | no-exec |

KIND TOTALS (box): query=4, command=5, clarify=11. Every dangerous/always-block command => 0 side-effects.
Only the genuinely-risky bulk action (#7) executes, and ONLY with a step-up PIN token attached to the delegation.

### Learnings (don't regress)
- The DEPLOYED box `intent/driver.py` already bakes the §23 always-block guards into the deterministic keyword
  stub (box lines 195-202): `(api key|secret|password|pin|token)+(show|reveal|tell|read|give)` ->
  `blocked:reveal_secret`; `(ignore|bypass|disable|turn off)+(dnd|consent|stop|opt-out|compliance|audit)` ->
  `blocked:compliance_bypass`. The OLD `droplet_work/ai_manager/intent/driver.py` (296L) LACKS these — it
  mis-routed "Ignore DND and call everyone" -> leads.enqueue_calls. **The box is the source of truth; the local
  droplet_work mirror is stale for driver/identity/delegate/store. Re-sync FROM the box before further B-wave work.**
- Stub conservativeness is by design: many natural §23 commands -> clarify because the live NLU LLM is dormant
  (`llm_provider=none`). clarify = never-guess-a-command = the safe default. The live Groq/Claude NLU (Wave C)
  is what upgrades #3/#4/#16 etc. into parsed-but-gated commands.
- `persistence.schema_ready=true, mode=pg_native` on `/status` => the `ai_manager_*` PG schema is ALREADY applied
  on the live box (the JSONL->PG absorption happened). Dormant data plane is live-ready.
