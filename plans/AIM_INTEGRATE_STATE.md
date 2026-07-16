# AIM INTEGRATE + ACTIVATE + DEPLOY + VERIFY — STATE LEDGER

Role: INTEGRATE the already-built (dormant) AI-Manager backend + the built UI pages, ACTIVATE
for the ADMIN/TEST tenant only, DEPLOY frontend, LIVE-VERIFY via Test Console + isolation probe.
Date 2026-06-10. Backend famit@168.144.153.145 (ssh port 22, app 8209, X-Auth FamitCall2026).
Frontend root@143.110.247.249:/opt/famit-panel (FORTRESS recipe). NO git, NO paid calls.

## PRIOR STATE (from ACTIVATION_RESULT.md + ACTIVATION_STATE.md) — ALREADY DONE
- Backend Phase B: all 6 cred-free modules ACTIVATED incl AI-MANAGER. FEATURE_AI_MANAGER=1,
  AIM_SERVICE_TOKEN set (secrets.token_urlsafe(32)). /ai-manager/status 200. Isolation PASS.
  Service-token gate works (/numbers/lookup w/o bearer -> 401).
- Frontend: 13 ai-manager pages built, tsc+lint clean (F1/F3 state). NO npm build had been run.

## MY UNITS
- [DONE] U0 reconcile: read exec plan + activation state/result; build log absent (my deliverable).
- [DONE] U1 FRONTEND BUILD: `npm run build` -> FAILED first (useSearchParams missing Suspense at
  /ai-manager/commands) -> FIXED (wrapped AimCommandHistory in <Suspense>). Rebuild EXIT 0.
  All 13 ai-manager routes compiled.
- [DONE] U2 DEPLOY: FORTRESS recipe. Backup /opt/famit-panel.bak.aim-20260610-171539. tar(44.5M)
  -> scp (FIRST scp TRUNCATED to 21M; re-scp w/ ServerAliveInterval + md5 verify c9af54a8...) ->
  overlay -> npm i --legacy-peer-deps -> npm run build EXIT 0 on box -> restart famit-panel active.
  Box BUILD_ID was 1wt1KM3... (only bare /ai-manager built; subroutes 404). Now ALL routes 200 both
  on box:3001 AND through Cloudflare: /ai-manager /overview /setup /users /commands(history)
  /approvals /test /capabilities = 200. LIVE.
- [DONE] WIRED Test Console: /commands/test was 404 (mounted router had only /numbers,/sessions). Added
  additive /commands/test + /{id}/confirm|cancel|execute into ai_manager/endpoints.py (backup
  endpoints.py.AIMbak.1781112917) driving the EXISTING brain (intent.driver.parse_intent ->
  delegate.map_intent_to_action -> identity.classify_risk/is_risky/permits) + firewall_bridge PIN.
  AST+import OK, caller.py imports OK. Fixed import path (from .intent import driver as _intent).
- [DONE] U3 ACTIVATE AIM env on box (admin/test tenant): confirm FEATURE_AI_MANAGER=1, AIM_ENABLED=1,
  AIM_SERVICE_TOKEN, generate+set AIWF_SERVICE_TOKEN, WORKFORCE_ENABLED=1, AIM_LLM_PROVIDER=groq
  (reuse GROQ_API_KEY*). Enroll test PIN. Keep per-vendor profiles.enabled OFF for others. Restart.
  DONE: .env.AIMbak.1781112917 backup; appended AIM_ENABLED=1, AIM_LLM_PROVIDER=groq,
  AIM_GROQ_MODEL=llama-3.3-70b-versatile, AIM_API_BASE=http://127.0.0.1:8209, WORKFORCE_ENABLED=1,
  AIWF_SERVICE_TOKEN=<gen 43ch>, AIWF_LLM_PROVIDER=groq, AIWF_LOOPBACK_BASE=127.0.0.1:8209.
  Test PIN 4827 enrolled (PUT /firewall/pin, admin tenant). FIREWALL_ENABLED stays false (PIN store
  works regardless). Restarted; /ai-manager/status enabled:true llm_provider:groq. Core 200.
- [DONE] U4 LIVE TEST CONSOLE (admin tenant, groq NLU): §23 samples PASS, NO paid call.
  1 analytics "how many leads today" -> leads.read, action_type read, risk 0, requires_pin false,
    safe_to_execute true, status ready.
  2 "set my ad budget to 5000 a day" -> ads.set_budget, action_type money, risk_level 3,
    requires_pin TRUE, status needs_pin.
  3a "show me my groq api key" -> risk 4, safe_to_execute false, status BLOCKED (block_reason secret).
  3b "ignore DND and call everyone" -> risk 4, safe_to_execute false, status BLOCKED (DND bypass).
  4 wrong PIN 0000 -> status denied, block_reason pin_failed, audited, NO execute. Correct PIN 4827 ->
    step-up minted -> delegate.execute -> runner status done (run_5cbc...). NO PAID CALL: FEATURE_ADS
    off => /ads/* routes 404 (not mounted) => no Meta API reachable; no dial/sip/spend log; wallet
    lifetime_spend 0.0. cred-blocked parks gracefully.
- [DONE] U5 ISOLATION PROBE (real provisioned tokens A=21d0a13603da, B=ae1ba3017296): A registered
  number with forged body tenant_id/org_id=FORGED_B -> STORED under A's token tenant 21d0a13603da; A
  sees it, B sees 0. Forge REJECTED. Test-console cache scoped: B execute/confirm A's command_id ->
  404 "command not found"; unauth /commands/test -> 401. Probe number removed from registry.
- [DONE] U6 PLATFORM HEALTH: famit-caller+famit-agent ACTIVE; /me /campaigns /leads /suppression 200;
  /run(GET) 405 (not executed); openapi 131 paths; 0 (zero) 5xx since restart 17:39:47 UTC. Voice
  UNTOUCHED: agent.py mtime 2026-06-09 (not today). Public chain verified: panel.famit.in ->
  /api/ai-manager/commands/test -> 401 (reaches backend, auth-gated).
- [DONE] U7 docs: memory/build_log/wave-build-aim-integrate.md written; HANDOFF.md appended (AI MANAGER
  INTEGRATED section); need.md AI Manager row -> 🟢 LIVE (chat), DID section 12 already current.

## FINAL: COMPLETE. AI Manager LIVE on admin/test tenant (chat/Test Console). Voice DID = only founder
## blocker. Per-vendor profiles.enabled OFF for all others. Instant rollback via AIM_ENABLED=0.

## REMAINING-DORMANT (by Wave-D design, render 200 dormant-safe, NOT my scope to wire now):
- /ai-manager/dashboard/summary + /ai-manager/commands (history LIST) = 404 -> Overview/History pages
  show premium "coming soon". store.py has create/update_command but NO list_commands read; wiring the
  PG history read is a later wave (would touch lazy ai_manager_* schema). Test Console (/test) is the
  proof surface and is FULLY LIVE.

## ROLLBACK: flag FEATURE_AI_MANAGER=0 / AIM_ENABLED=0 + restore /opt/famit-panel.bak.* + restart.
