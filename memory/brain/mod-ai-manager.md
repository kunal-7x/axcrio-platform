# BRAIN — AI Manager voice/chat command center (`ai_manager` module)

Durable facts + hard-won learnings. Append, never delete.
Spec: `design/platform-ai-manager.md`. Build log: `memory/build_log/wave-build-mod-ai-manager.md`.
State: `droplet_work/ai_manager/AI_MANAGER_STATE.md`. Built 2026-06-10.

## WHAT IT IS / SCOPE
- The voice-first (and chat) COMMAND CENTER: registered-number identity -> per-number permissions ->
  intent->tool-routing over the workforce framework -> PIN/step-up firewall gate on risky actions ->
  multi-agent delegation to the role agents. Highest-privilege human-facing surface (a phone call that
  can spend money + trigger bulk outreach). Package `droplet_work/ai_manager/` (underscore — NOT the
  task's hyphen `ai-manager`, which isn't importable).
- BUILT: the orchestration + command intake (the deterministic safety machine, offline-tested 8/8).
  DEFERRED: the LiveKit voice front (`inbound_agent.py` is an import-safe stub) — "thin later wire".

## THE KEY ARCHITECTURAL FACTS (don't re-derive)
1. **IN-PROCESS composition, NOT cross-plane HTTP.** The spec's §3.2 HTTP transport was written when
   firewall/workforce/audit were designed-only on a hypothetically-separate box. They are BUILT in the
   same `droplet_work/` tree, and the voice front is deferred, so this module imports them directly
   (firewall_bridge->`import firewall`, audit_bridge->`import audit`, delegate->`workforce.run_agent`),
   exactly like `workforce.default_deps()` imports firewall/wallet. The cross-plane HTTP client is part
   of the deferred voice wire and was NOT built. A dormant seam (config.service_token_present + api_base)
   marks where it goes.
2. **Delegate to a WORKER role, never the bare `manager` role.** roles.py `manager` has only
   default_scopes=("delegate",) and there is NO `delegate` tool in the registry -> run_agent(role=
   "manager") => blocked:unknown_tool, executes nothing. `delegate._INTENT_ROLE` maps intent ->
   telecaller|whatsapp|ad|strategist|analytics|ops and calls run_agent(role=<worker>,
   trigger="manager_voice"). THIS module IS the intent->role seam workforce RT-1 deferred to it.
3. **Real firewall symbols (the spec prose uses names that don't exist):** `check_pin(tenant,pin)` (NOT
   verify_pin), `mint_step_up(tenant,scope)` (returns None if firewall not init'd), verify_step_up_token,
   has_pin, set_pin. verify_otp exists but is dormant (not_configured). firewall_bridge.authenticate()
   wraps both S2 login (scope="") and S6 step-up (scope set -> mints a token). Fail-CLOSED on auth.
4. **Action vocabulary = WORKFORCE tool-scopes** (ads.set_budget, leads.enqueue_calls, whatsapp.send,
   analytics.read), NOT firewall.classify's separate set (ads.spend, whatsapp.bulk_send). If the names
   don't match the workforce gate won't recognize the delegated action.
5. **Two distinct gates (defense in depth):** S2 login PIN proves WHO is calling (mints a tenant access
   token posture); S6 step-up PIN authorizes THIS specific risky action (fresh, scoped, 300s). A single
   login can never silently authorize a money action. The voice-side classify_risk is a deterministic
   PRE-FILTER; the workforce runner re-enforces its own risk_class/caps/kill-switch/wallet at execute.

## DETERMINISTIC SAFETY (the LLM never holds authority)
- identity.classify_risk: money(ads.set_budget/create_campaign/invoices.create/wallet.topup) ->
  bulk(leads.enqueue_calls/whatsapp.send) -> destructive(delete/export/price/refund/pause_all) -> safe.
  A model that self-labels its action "safe" is IGNORED — only this table decides (test asserts it).
- identity.permits(role, grants, action): role-family AND per-number-grant must BOTH allow (default-deny).
  Roles: admin(all) / manager(operate, no billing write) / operator(no ad spend, no destructive).
- state_machine: S0 connect -> S1 verify (caller-ID is a HINT) -> S2 auth (PIN/OTP, BEFORE any data) ->
  S3 context -> S4 intent -> S5 permit -> S6 step-up (risky only, fresh+scoped) -> S7 confirm (amount
  read back) -> S8 delegate+execute -> S9 report. Lockout after config.max_pin_attempts (3); number
  flipped to status=locked in registry.

## PIN HYGIENE (text AND audio — spec §6.5)
- The spoken PIN transits STT + call recording. state_machine wraps EVERY collect_secret() span with
  recorder.pause()/resume() (a SpyRecorder in the test asserts pause==resume count == #secret spans).
  Digits consumed in-memory; transcript stores a masked turn (never the value); PIN absent from session
  record AND the audit ledger (test greps both for the raw PIN -> 0 hits). endpoints._sanitize_session
  re-scrubs on the API box (never trusts the client to have masked).

## DORMANCY (provider-agnostic, never raises)
- intent/driver.py: default `none` -> deterministic keyword/regex matcher over a CLOSED ENUM (offline
  path; the matcher extracts rupee->minor amounts, channel, segment). groq/claude branches inert
  (_llm_parse returns None -> stub fallback). is_configured() False for `none`. Off-enum/low-conf ->
  clarify, never executes.
- otp/sender.py: twilio|msg91|whatsapp|none; dormant -> voice-PIN fallback (safety never depends on OTP).
- endpoints.py: router DEFINED but NOT mounted (9 routes); FastAPI imported defensively (router=None if
  absent so the package + offline test import without FastAPI). /numbers/lookup + POST /sessions are
  SERVICE-TOKEN (the voice worker, dormant until AIM_SERVICE_TOKEN); grants/revoke require firewall step-up.

## LEARNINGS / GOTCHAS
- Box python is 3.14 with pyjwt PRESENT -> the firewall step-up path actually fires in the offline test
  (real mint + real verify). Use a >=32-byte test secret for firewall.init or pyjwt emits an
  InsecureKeyLengthWarning (cosmetic; real var/secret is fine).
- delegate.execute with runner=None falls back to importing workforce.run_agent — which IS present in
  this tree, so a "no creds" path still runs the REAL AgentRunner (StubPlanner, no LLM) and returns a
  real run_id. To assert the not_configured branch you must inject a StubDelegate; the offline test does.
- The runner always routes through its planner — there is no "execute this EXACT action" entry. For an
  exact amount read-back, the action's args ride in the `task` dict + the offline test injects a
  StubDelegate (spec §9). FLAG: live delegate<->planner explicit-action is a deferred workforce-integration
  seam (StubPlanner currently drives; a live LLM plan would need the action hint honored).
- caller.py uses @app.<verb> decorators directly (no APIRouter / include_router yet). Our additive router
  is the first include_router; the un-applied diff adds it in a try/except so a missing module can't break
  startup. caller.py has 0 references to ai_manager today (wiring un-applied). agent.py byte-untouched.

## AUDIT-ACCURACY (folded post-review — don't regress)
- state_machine records `executed = (runner status == "done")`, NOT a hardcoded True. A parked/killed/
  not_configured/error delegation is executed:False and does NOT increment n_actions. The over-cap money
  action the engine refuses (defense in depth) must surface as refused, not executed. Guard:
  test_engine_reenforces_caps (spec §9.9) — it fails against any hardcoded executed:True.

## CREDS AWAITED (server-side only, never git)
AIM_VOICE_DID + AIM_VOICE_SIP_TRUNK_ID + AIM_ENABLED=true (telephony); GROQ_API_KEY|ANTHROPIC_API_KEY +
AIM_LLM_PROVIDER (intent LLM, else stub); TWILIO_*|MSG91_*|Meta-WA + AIM_OTP_PROVIDER (OTP, else voice
PIN); AIM_API_BASE + AIM_SERVICE_TOKEN (ONLY if voice worker is a separate host); per-tenant firewall PIN.

## FRONTEND PAGE (famit-panel app/ai-manager/) — built 2026-06-10
- Files: `famit-panel/app/ai-manager/page.tsx` + `famit-panel/app/ai-manager/_lib.ts` (the ONLY two; no nav
  link / no globals.css / no lib/api.ts edit — nav+build+deploy is the orchestrator's ship step).
- 3 in-page tabs (NOT sub-routes): Command Center (status hero + dormancy/coming-soon explainer + config
  board + command vocabulary), Registered Numbers (data-table + manager+ register form, verify/revoke),
  Voice Sessions (PIN-masked list). Premium "Signal" language only: Layout/PageHeader/Card/KpiCard/Badge/
  Tabs/Icon/Button + verified globals.css utils (kpi*, state-block, pill-*, data-table, meter, rise-in/lift,
  toast, input-base, page-head, shadow-widget). Reused billing/overview HeroCard pattern (inlined, no cross-page import).
- DORMANT-FIRST is the PRIMARY state: router is DEFINED-NOT-MOUNTED so every /ai-manager/* call 404s today;
  `_lib.ts` read() maps 404/501/503 + network fail -> {kind:"dormant"} (never throws) -> premium coming-soon
  panels. Mutations throw a friendly msg (403 -> "permission or needs step-up PIN").
- WIRING GOTCHAS (don't re-derive): (1) /ai-manager endpoints take a JSON Body(dict) — POST JSON, NOT FormData
  (unlike the older /campaigns,/leads,/run which use FormData). (2) Auth = `X-Auth: <localStorage famit_token>`
  header, BASE = NEXT_PUBLIC_API_BASE||"/api" — mirror lib/api.ts exactly (NOT Bearer/Authorization).
  (3) Self-contained _lib.ts on purpose: keeps a dormant surface out of the shared lib/api.ts + avoids parallel-
  session edit conflicts. (4) Icon is an inline SVG-path map (~80 names) — using an unknown name renders BLANK;
  valid voice-relevant: mobile,lock,chat,send,bell,check-circle,check,clock,info,dashboard,chart,cube,plus,block,wallet.
  (5) globals.css is FROZEN — copying Core_2 markup verbatim would reference classes that don't exist here.
- Gating: writes behind canWrite(me); revoke additionally behind isAdmin(me) (server ALSO firewall step-up gates
  grants/revoke — `_require_step_up(scope="destructive")`, pass-through while firewall dormant). No client PIN flow.
- Verified: `npx tsc --noEmit` EXIT 0 project-wide; `next lint` on both files EXIT 0 (caught+fixed 1 unused import).
