# BRAIN — AI Manager voice/chat command center (`ai_manager` module)

Durable facts + hard-won learnings. Append, never delete.
Spec: `design/platform-ai-manager.md`. Build log: `memory/build_log/wave-build-mod-ai-manager.md`.
State: `droplet_work/ai_manager/AI_MANAGER_STATE.md`. Built 2026-06-10.
NLU+Policy+Risk+Security design (dedicated-service brain): `design/aim-nlu-policy-security.md` (2026-06-10).

## NLU/POLICY/SECURITY DESIGN — KEY DECISIONS (design/aim-nlu-policy-security.md)
- **Dedicated service owns `ai_manager_*` PG schema (6 tables, FORCE-RLS admin-GUC, P1 shape).** Absorbs the
  thin mounted `/ai-manager` router's JSONL number/session stores -> RLS PG `ai_manager_authorized_users` +
  `ai_manager_sessions`. Migration starts every user at pin_hash=NULL (no re-use of weaker hash).
- **PIN = Argon2id PER-USER** (argon2-cffi; t=3, m=64MiB, p=2, 16B salt) + HMAC(var/secret, pin) PEPPER
  before Argon2id. DELIBERATE delta: master §3.9 mandates Argon2/bcrypt; monolith firewall.py uses tenant-
  level salted-sha256. AIM keeps its OWN per-user Argon2id store; still calls `firewall.mint_step_up` AFTER
  its Argon2id verify to get the cross-service `X-Step-Up` token (sub==caller, F3). Two PIN stores by design.
- **Risk = deterministic code table (§2), model's risk_level IGNORED & recomputed.** Maps to firewall scope
  vocabulary (`spend|bulk|destructive`) so downstream `require_step_up(scope)` recognizes it. Escalation
  rules only RAISE. Bulk floor by COUNT vs `max_bulk_leads_without_pin` (not the model's word "bulk").
- **PolicyEngine.decide = pure fn, FAIL-CLOSED, first-match-wins order:** always-block -> permission(default-
  deny) -> compliance(NEVER PIN-overridable) -> spend-ceiling(hard cap = BLOCK not PIN; insufficient credit =
  block) -> bulk floor -> risk floor(max with tenant policy) -> gate(L0 allow/L1 light/L2 confirm/L3 pin-
  after-confirm) -> default block. money/bulk/destructive/export/security can NEVER resolve to allow.
- **ALWAYS-BLOCK (L4, no PIN unlocks, any channel):** reveal secret/key/PIN/token; bypass DND/STOP/consent/
  hours/spam; delete account/transfer ownership; disable/erase audit/security; cross-tenant; spend over hard
  ceiling; self-modify safety (turn off PIN/lower require_pin_for_level). NLU first-line block + PolicyEngine
  final authority.
- **NLU strict JSON (§22 expanded):** Groq JSON-mode (`response_format=json_object`, temp=0) or Claude Opus
  4.8 `output_config.format` (NO temperature). amount in INTEGER PAISE never float. confidence<0.55 or
  missing_fields -> clarify, never execute. Validate->recompute risk->PolicyEngine EVERY call (model = input,
  not authority). Retry-once on bad JSON/unknown intent, then clarify. ctx = read-only vendor-scoped
  campaigns/leads/wallet/grants; deterministic resolver matches campaign_ref (model never resolves the id).
- **Audit:** reuse `audit.record` channel="ai_manager", actor=verified tenant (never "system"); immutable leg
  = PG `events`; money-mutating rows ride INSIDE the wallet txn as wallet_transactions.meta (F2 — JSONL can't
  be atomic with PG COMMIT). `ai_manager_audit_logs` grants famit_app SELECT+INSERT only (no UPDATE/DELETE).
- **Tenant isolation test (§7):** two layers — token-derived tenant (NEVER body vendor_id) + FORCE-RLS GUC
  probes per table; per-endpoint forge matrix (authed as A, id/vendor=B -> 404, no info leak); step-up replay
  A-token-on-B-execute -> 403 sub-mismatch; NEGATIVE CONTROL (read vendor_id from body on a throwaway copy ->
  forge succeeds) proves the test has teeth.

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
- endpoints.py: router DEFINED but NOT mounted; FastAPI imported defensively (router=None if
  absent so the package + offline test import without FastAPI). /numbers/lookup + POST /sessions are
  SERVICE-TOKEN (the voice worker, dormant until AIM_SERVICE_TOKEN); grants/revoke require firewall step-up.

## B3 — §10 API SURFACE (35 routes; built 2026-06-10, `B3_STATE.md`, smoke_b3 6/6)
- endpoints.py grew 9->35 routes = the full master-spec §10 the dashboard UI (_lib.ts) already calls:
  profile GET/PUT · authorized-users GET/POST/PATCH/DELETE · pin set/verify/reset-request/reset-confirm
  (raw PIN NEVER returned — firewall.check_pin/set_pin + a one-way per-user sha256 mirror for the UI's
  has_pin/pin_set_at status only) · sessions GET+:id (nested commands+audit) · commands GET(+§14 filters)
  +:id(+action_runs)+POST /commands/test+:id/{confirm,cancel,execute} · dashboard/summary, audit-logs,
  action-runs · voice+whatsapp webhooks = SAFE STUBS (service-token gated, DORMANT->401, create a session
  shell, dispatched:false — no DID, deferred voice wire).
- FEATURE GATE: `_require_tenant(gate_feature=True)` checks FEATURE_AI_MANAGER (then AIM_ENABLED) AFTER
  auth/permission -> 503 'ai_manager_not_enabled' which _lib.ts maps to the premium dormant state. ONLY
  /status is un-gated (it IS the dormancy probe; returns feature_enabled).
- TEST CONSOLE reuses the deterministic engine, NOT a new path: _run_test_command = nlu.parse ->
  intent.driver._nlu_to_match -> RECOMPUTE risk via identity.classify_risk (model never authorizes,
  safe_to_execute always false) -> persist ai_manager_commands row -> return §22 parse + real command_id.
  _transition_command(confirm|cancel|execute) re-checks the gate each hop; execute on a risky cmd REQUIRES
  a valid firewall PIN (verified+discarded) -> scoped step-up -> delegate.execute (runner re-enforces caps).
- store.py gained the read/list/profile/user/summary helpers: ALL RLS-scoped (db.engine.session(
  tenant_id=vendor_id)), JSON-safe (datetime->ISO), degrade to []/None when PG down (NO 500). pin_hash is
  NEVER selected (only derived has_pin/pin_set_at). _exec got fetch_all. list_commands does the §14 filter
  set (channel-join, risk token->int floor, from/to/q).
- GOTCHA: a FastAPI path-op CANNOT take **kwargs (`**_`) — it breaks request binding (empty body). Read
  extra query params off request.query_params instead. Also: caller.py needs livekit so it WON'T import on
  the local box — endpoints lazily imports it inside _resolve_tenant and degrades; the smoke injects a fake
  `caller` into sys.modules to exercise the real HTTP path offline.

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

## F2 FRONTEND (Setup + Authorized Users) — VERIFIED 2026-06-10
- Routes `app/ai-manager/setup/page.tsx` + `app/ai-manager/users/page.tsx` are FULLY BUILT (co-built in a
  prior session with the shared `_shared.tsx`/`_lib.ts`). Both wired into nav (`contstants/navigation.tsx`
  AI Manager group → Setup + Authorized Users children).
- Setup: 5 anchored sections (General/Voice&language/Confirmation&PIN/Spend limits/Calling hours), sticky
  section menu, risk-legend table keyed off `require_pin_for_level`, ConfirmModal before save (spend/PIN
  changes are sensitive). Binds getAimProfile/putAimProfile. Read-only when !canWrite OR dormant.
- Users: data-table (User/Role/Permissions/PIN/Last-used/Status/Actions), search + All/Active/Locked tabs,
  UserModal (add/edit + KNOWN_GRANTS chips), SetPinModal (4/6-digit, confirm-match), ResetPinModal (2-step
  request→confirm OTP, admin-only banner). PIN status only — raw PIN never rendered. Disable=patch
  is_active:false (NOT delete — there's no hard-delete UI). canWrite gates writes; isAdmin shown on reset.
- LINT FIX this session: removed dead `deleteAimUser` import (page disables, never hard-deletes) + wrapped
  `rows` in useMemo (was a fresh [] each render → destabilised two useMemo deps). tsc EXIT 0 project-wide,
  next lint EXIT 0 on both files. No npm build (per instructions), no shared component / globals.css edits.

## B4 — DORMANT BACKEND VERIFY (2026-06-10) — live untouched, spine proven (build_log: wave-build-mod-ai-manager.md §B4)
- Box reality (NOT what the task assumed): running caller env has **FEATURE_AI_MANAGER=1** (router MOUNTED),
  FIREWALL_ENABLED=false, AIM_ENABLED unset. Core 200 (`/me`,`/campaigns`,`/leads`,`POST /run/preview`); ZERO 5xx;
  both services active throughout; caller.py + agent.py untouched.
- Deployed `endpoints.py` = **B1-era 9 routes** (status,numbers/*,sessions), md5 `cd0daf4472`. `/ai-manager/status`->200
  `{enabled:false,...,persistence:{schema_ready:true,mode:pg_native}}` (un-gated dormancy probe + PG schema ALREADY
  applied live). `/numbers`,`/sessions`->200 empty. **`/profile`,`/commands`,`/dashboard/summary`->404 because the B3
  35-route expansion is LOCAL-ONLY, not deployed** (404=route-absent=dormant-safe, NOT a 503 gate).
- ⚠ SOURCE-OF-TRUTH = THE BOX, not `droplet_work/`. Box files NEWER for `intent/driver.py` (633L `22d280a3` vs local
  296L), identity/delegate/store. The box driver bakes §23 always-block into the keyword stub (reveal_secret +
  compliance_bypass guards); the stale local 296L driver mis-routes "Ignore DND and call everyone"->enqueue_calls.
  **Re-sync local FROM box before more B-wave work.** (local endpoints.py is the only file LOCAL-ahead = B3.)
- Offline spine: `tests/test_offline.py` 10/10 PASS; new `tests/smoke_b4_samples.py` drives §23. Authoritative §23
  table run on the BOX: query=4, command=5, clarify=11. Every dangerous/always-block cmd -> 0 side-effects; only the
  risky bulk "Call all hot leads" executes and ONLY with a step_up_token attached. "Show my API key"/"Ignore DND"/
  "Delete all leads" -> 0 exec. creative.generate_video classifies money but delegation parks (not wired). NO activation done.

## 2026-06-10 — INTEGRATE+ACTIVATE+DEPLOY (admin/test tenant) — LIVE on chat/Test Console
- The mounted in-process `ai_manager` router (caller.py) only ships /status,/numbers,/sessions. The
  frontend Test Console calls `POST /api/ai-manager/commands/test` which did NOT exist -> 404. Wired 4
  ADDITIVE routes into `ai_manager/endpoints.py` (/commands/test + /{id}/confirm|cancel|execute) that
  drive the EXISTING brain: `from .intent import driver as _intent` (parse_intent) ->
  delegate.map_intent_to_action -> identity.classify_risk/is_risky/permits -> firewall_bridge PIN.
  Backup endpoints.py.AIMbak.1781112917. (parse_intent is in intent.driver, NOT the intent package.)
- Activation flags: **AIM_ENABLED** is the master flag (config.py), SEPARATE from FEATURE_AI_MANAGER
  (mount-only). Workforce needs WORKFORCE_ENABLED=1 + AIWF_SERVICE_TOKEN (mints per-run loopback tokens).
  AIM_LLM_PROVIDER=groq + AIM_GROQ_MODEL=llama-3.3-70b-versatile (reuse box GROQ_API_KEY*). Enrolled test
  PIN via PUT /firewall/pin (works even with FIREWALL_ENABLED=false — the PIN store is independent).
- PROVEN live (no paid call): analytics=safe read; ads.set_budget=money risk3 requires_pin; secrets/DND
  =risk4 BLOCKED; wrong PIN=denied+audited; correct PIN=step-up+execute. FEATURE_ADS off => /ads/* 404 =>
  no Meta API reachable. Test-console cache is tenant-scoped (B execute A's cmd -> 404). Isolation PASS.
- Frontend: fix `useSearchParams()` MUST be `<Suspense>`-wrapped for static prerender (next build catches
  it; tsc/lint do NOT). md5-verify scp'd tarballs before tar (a truncated tarball = "unexpected EOF").
- STILL DORMANT by Wave-D design: /dashboard/summary + /commands history LIST (store.py has no list read).
- Founder-blocked: inbound voice DID + SIP trunk + DLT (need.md §12). Chat path fully live without it.

## B3 — AI MANAGER CREATIVE WIRING -> LIVE ASSET SERVICE (2026-06-11) ✅ real banner via voice/chat
- The parked workforce `creative.*` adapters now call the LIVE AI Asset Service (:8310) instead of the dead
  `/media/*` routes. PROVEN E2E via Test Console (admin): "Create 2 ad banners for the Codename Joy 3.0
  campaign" -> NLU `creative.generate_banner` risk=money(3) requires_pin -> PIN 2468 -> step-up ->
  delegate -> `run_agent(role=creative)` -> adapter -> asset `/generate` -> OpenRouter gemini-2.5-flash-image
  -> REAL 1.2MB PNG (1200x628, uploaded to DO Spaces). Wallet settled ACTUAL Rs6.76 NO double-charge
  (one hold->settle, held=0); immutable audit; re-execute -> `command not found` (terminal, no 2nd job).
  Regression PASS (core 200, services active, 0 5xx, agent.py untouched). Build log
  `build_log/wave-build-aim-creative-wiring-B3.md`; ledger `droplet_work/B3_CREATIVE_WIRING_STATE.md`.
- ⚠ TWO non-obvious fixes were REQUIRED beyond re-pointing the URL (don't re-derive):
  (1) `delegate._task_for` must emit `task['plan']` — the workforce **StubPlanner reads `task['plan']`, NOT
  `task['actions']`** (the LLM driver `propose()` is still a DORMANT stub returning None regardless of
  AIWF_LLM_PROVIDER=groq, so StubPlanner ALWAYS drives). Without `plan` the planner ran nothing.
  (2) `delegate.execute` must MINT + thread `run_token` (`transport.mint_run_token(tenant_dict)` ->
  `run_agent(run_token=...)`); it was never passed -> empty Bearer -> asset svc 401. Token = the
  AUTHENTICATED tenant's access JWT; the asset svc verifies it with the shared monolith secret.
- MONEY-PATH: creative is `money=True` workforce-side BUT `recompute_spend_minor`=0 (no amount_minor in
  args) so the runner does NOT reserve — the **asset service is the sole money-path** (reserve/settle
  ACTUAL internally). NO double-charge by construction. Adapter returns actual_spend_minor=0.
- New seam: `workforce/config.asset_service_base()` (env `AIASSET_LOOPBACK_BASE` default :8310) +
  `transport.call_service(...,base=...)` (arbitrary base, Bearer run_token, 30s). Box catalog has THREE
  creative tools (`creative.generate_{video,banner,brochure}`) — video=cover-only, banner/brochure share
  the image fn -> asset `/generate` asset_type banner|video_cover.

## FIX-B — EXECUTE TRUTH + HUMAN SUMMARY + read DATA + campaign API (2026-06-11) ✅ build_log/wave-build-fix-ai-manager-execute-B.md
- ⚠ ASSET SVC BINDS TO VPC IP, NOT 127.0.0.1. The asset service listens on **`10.122.0.4:8310`** (VPC),
  so `AIASSET_LOOPBACK_BASE` MUST = `http://10.122.0.4:8310` in `.env` (default 127.0.0.1:8310 -> every
  creative.* call = `transport_error:ConnectionError` -> honest noop). The B3 var had been LOST; re-set this
  session. If creative no-ops again, CHECK THIS FIRST. `.env.FIXBbak.*` backup.
- A2 TRUTH-IN-REPORTING (the false-"executed" killer): the runner finalizes `status="done"` even when its
  only tool PARKED (`{ok:False,reason:not_configured}` — module FEATURE_* off). PG `list_steps` STRIPS the
  tool result body, so the runner now also returns `result={outcome,tools_ok,tools_failed,last_reason,data}`
  (`outcome=effective|noop|empty`). `delegate._normalize_result` hoists `effective=(done AND outcome==effective)`
  + `data`. `endpoints.commands_execute` sets `executed=result.effective` (NOT bare status=="done"). A
  done-but-parked run now reports HONESTLY, never a false success. (runner edits are ADDITIVE result keys —
  workforce HTTP routes + offline tests unaffected.)
- A4 READS NOW EXECUTE INLINE + return REAL data: `_aim_parse_card` QUERY branch runs the read via
  `delegate.execute` (safe: no PIN/spend/idempotent), returns `data` (the last-ok tool body, surfaced via
  runner `result.data`) + `status:"executed"`. PROVEN: analytics funnel + wallet balance = REAL live figures.
- B2 HUMAN SUMMARY at EVERY state (Hinglish business tone), built in `endpoints._aim_human_outcome` +
  `_TOOL_LABEL`/`_REASON_HUMAN` (reason normalized: `transport_error:Conn..`->`transport_error`). e.g.
  "Done! ad banner successfully ho gaya." / "Abhi ad budget update nahi ho paaya — is spend ke liye extra
  approval pending hai." / read "Ho gaya — aaj ka performance report ready hai...". FE can now drop the raw
  `<pre>` and render `user_facing_summary` + `data` (FE not edited this wave).
- SPEND CMD still re-parks: ads.set_budget(amount>0) -> runner gate `awaiting_approval` even with AIM
  step-up token, because the runner needs a matched APPROVAL ROW not just task.step_up_token. Now reported
  HONESTLY (executed:False). Wiring AIM step-up -> runner approval/resume = deferred. Reads + creative (no
  reserve) execute fully today.
- CAMPAIGN API (founder dropdown): LIST `GET /campaigns`->{campaigns:[{id,name,company,product,status,
  created_at}]} (clean, 8 live). DETAIL = **`GET /campaigns/{id}`** -> {campaign:{...,fields:{company_name,
  product_name,product_summary,goal,location,price_offer,usps,value_prop,language,agent_name,wa_template_*}}}
  (RICH, real). ⚠ `GET /assets/campaign-context` DOES NOT EXIST (asset svc :8310 has only /generate+regenerate
  -> 404; FE getCampaignContext always falls back). The CampaignSelect detail source should be `/campaigns/{id}`,
  NOT campaign-context. NO backend change needed for the dropdown.
