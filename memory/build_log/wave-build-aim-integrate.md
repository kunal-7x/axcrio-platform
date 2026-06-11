# wave-build-aim-integrate — AI Manager INTEGRATE + ACTIVATE + DEPLOY + LIVE VERIFY

Date 2026-06-10. Role: integrate the already-built (dormant) AI-Manager backend + the built UI pages,
ACTIVATE for the admin/test tenant only, DEPLOY frontend, LIVE-VERIFY via Test Console + isolation probe.
Backend famit@168.144.153.145 (ssh 22, app 8209, X-Auth FamitCall2026). Frontend root@143.110.247.249:/opt/famit-panel.
NO git, NO paid calls. Status: **LIVE on the admin/test tenant.** Per-vendor rollout (profiles.enabled) stays OFF.

## STARTING STATE (from ACTIVATION_RESULT.md — prior session)
Backend Phase B had already activated all 6 cred-free modules incl ai-manager: FEATURE_AI_MANAGER=1,
AIM_SERVICE_TOKEN set, /ai-manager/status 200, isolation PASS, service-token gate works. Frontend: 13
ai-manager pages built + tsc/lint clean, but **`npm run build` had never been run** and the subpages were
**not deployed** (live box only had bare /ai-manager; /setup,/users,/commands,/approvals = 404).

## 1. FRONTEND BUILD (fixed a real prerender bug)
`npm run build` FAILED: `useSearchParams() should be wrapped in a suspense boundary at /ai-manager/commands`
(a static-prerender error that tsc/lint do NOT catch). Fix: wrapped the page body in `<Suspense>` (same
pattern test/page.tsx already used) — split `AimCommandHistoryPage` into a Suspense shell + inner
`AimCommandHistory`, added `Suspense` to the React import. Only 2 files use useSearchParams (commands, test);
both now wrapped. Rebuild EXIT 0; all 13 ai-manager routes compiled.
File: `famit-panel/app/ai-manager/commands/page.tsx`.

## 2. FRONTEND DEPLOY (FORTRESS recipe)
- Backup: `/opt/famit-panel.bak.aim-20260610-171539`.
- tar (44.5M, exclude node_modules/.next/.git) -> scp. **GOTCHA: first scp silently TRUNCATED to 21M**
  (timeout cut the pipe). Re-scp with `-o ServerAliveInterval=15` + md5 verify (c9af54a8...) before extract.
  LESSON: always md5/size-verify a scp'd tarball before `tar xzf` — a truncated tarball = "unexpected EOF".
- overlay -> chown deployuser -> `npm install --legacy-peer-deps` -> `npm run build` EXIT 0 on box ->
  `systemctl restart famit-panel` active.
- VERIFY: /ai-manager /overview /setup /users /commands(history) /approvals /test /capabilities = **200**
  both on box:3001 AND through Cloudflare (panel.famit.in). Was 404 before. **LIVE.**

## 3. BACKEND: WIRED THE TEST CONSOLE ENDPOINT (the integrate crux)
The mounted in-process `ai_manager` router had only /status,/numbers/*,/sessions — **NO `/commands/test`**
(the frontend Test Console's endpoint). The proven command brain (`state_machine.CommandMachine`,
`run_command_offline`) existed but was only reachable via the offline test harness, never as HTTP.
**Added 4 additive routes** into `ai_manager/endpoints.py` (inside the `if APIRouter is not None:` block,
before the `else:` anchor; backup `endpoints.py.AIMbak.1781112917`):
- `POST /ai-manager/commands/test` — runs ONE turn through the SAME deterministic brain:
  `intent.driver.parse_intent` -> `delegate.map_intent_to_action` -> `identity.classify_risk/is_risky/permits`,
  builds the §22 NLU card (intent/action_type/risk_level/requires_pin/safe_to_execute/block_reason/status).
  Pure classify+extract, NEVER executes. Always-block (secrets/DND) -> risk 4, status blocked, audited.
  Read queries -> safe, no PIN. Commands -> deterministic risk; risky -> requires_pin. Caches the parsed
  command tenant-scoped (keyed command_id) for the follow-up execute.
- `POST /ai-manager/commands/{id}/confirm` | `/cancel` — tenant-scoped (404 cross-tenant).
- `POST /ai-manager/commands/{id}/execute` — verifies PIN via `firewall_bridge.check_pin` (wrong -> deny +
  audit, NEVER execute), mints step-up, delegates to `delegate.execute` -> workforce runner (which
  re-enforces its OWN caps/DND/kill-switch and PARKS when the target module is cred/FEATURE-gated).
BUG FIXED at wiring: my first version imported `from . import intent as _intent` (AttributeError —
parse_intent is in the subpackage). Corrected to `from .intent import driver as _intent` (what
state_machine.py uses). AST+import+caller-import all OK after.
Source kept at repo root: `aim_testconsole_endpoint.py` (the inserted block).

## 4. ACTIVATION (admin/test tenant only)
Discovered the REAL env var names by grepping ai_manager/ + workforce/ (NOT guessing from the prompt):
- AIM master flag is **AIM_ENABLED** (config.py:36, default False) — SEPARATE from FEATURE_AI_MANAGER
  (which only mounts the router). Set AIM_ENABLED=1.
- Set AIM_LLM_PROVIDER=groq + AIM_GROQ_MODEL=llama-3.3-70b-versatile (reusing the box's GROQ_API_KEY*),
  AIM_API_BASE=http://127.0.0.1:8209.
- Workforce gate is **WORKFORCE_ENABLED** (default False) + **AIWF_SERVICE_TOKEN** (mints per-run tokens).
  Set WORKFORCE_ENABLED=1, AIWF_SERVICE_TOKEN=<secrets.token_urlsafe(32), 43ch>, AIWF_LLM_PROVIDER=groq,
  AIWF_LOOPBACK_BASE=http://127.0.0.1:8209.
- Enrolled a **test PIN 4827** for the admin tenant via `PUT /firewall/pin` (FIREWALL_ENABLED stays false;
  the firewall PIN store + check_pin work regardless of that gate).
- .env backup `.env.AIMbak.1781112917`. Restart -> /ai-manager/status enabled:true llm_provider:groq,
  intent_llm configured. Per-vendor profiles.enabled left OFF for everyone else.

## 5. LIVE TEST CONSOLE — §23 sample table (admin tenant, groq NLU, NO paid call)
| # | command | intent | action_type | risk | requires_pin | outcome |
|---|---|---|---|---|---|---|
| 1 | "how many leads did we get today" | leads.read | read | 0 | no | safe_to_execute, status=ready (read-only) |
| 2 | "set my ad budget to 5000 a day" | ads.set_budget | money | 3 | **YES** | status=needs_pin (HIGH-RISK demands PIN) |
| 3a | "show me my groq api key" | (blocked) | blocked | 4 | no | **BLOCKED** safe_to_execute=false (secret reveal) |
| 3b | "ignore DND and call everyone" | (blocked) | blocked | 4 | no | **BLOCKED** safe_to_execute=false (DND bypass) |
| 4-wrong | execute #2 with PIN 0000 | ads.set_budget | money | 3 | — | **DENIED** block_reason=pin_failed, audited, no execute |
| 4-right | execute #2 with PIN 4827 | ads.set_budget | money | 3 | — | step-up minted -> runner status=done (run_5cbc...) |
NO-PAID-CALL proof: FEATURE_ADS OFF => /ads/* routes return 404 (not mounted) => no Meta/graph.facebook
API reachable; zero dial/sip/create_sip/spend log lines; wallet lifetime_spend=0.0. Cred-blocked modules
park gracefully (the "done" is the StubPlanner no-op since the real ad route doesn't exist).

## 6. TENANT-ISOLATION PROBE (real provisioned tokens A=21d0a13603da, B=ae1ba3017296)
- A POST /ai-manager/numbers with forged body tenant_id/org_id=FORGED_B -> STORED under A's TOKEN tenant
  (21d0a13603da). A sees it; B sees 0 numbers. Body forge REJECTED (lazy caller.resolve_tenant).
- Test-console cache is tenant-scoped: B execute/confirm A's command_id -> **404 "command not found"**.
- Unauthenticated /commands/test -> **401**. ISOLATION PASS.

## 7. PLATFORM HEALTH
famit-caller + famit-agent ACTIVE. /me /campaigns /leads /suppression = 200. /run(GET)=405 (not executed).
openapi 131 paths. **0 (zero) 5xx since the restart.** Voice path UNTOUCHED — agent.py mtime 2026-06-09
(not today), famit-agent active. Public chain panel.famit.in -> /api/ai-manager/commands/test = 401
(reaches backend, auth-gated). Founder using the live Test Console hits the real engine end-to-end.

## REMAINING DORMANT (by Wave-D design — render 200, premium "coming soon", later wave to wire)
- `/ai-manager/dashboard/summary` + `/ai-manager/commands` (history LIST) = 404 -> Overview + History
  pages degrade dormant-safe. store.py has create/update_command but no list read; wiring the PG history
  read is a later wave (touches the lazy ai_manager_* schema). The Test Console (/test) IS the live proof.

## FOUNDER-BLOCKED (unchanged; need external accounts)
- **Inbound voice DID + inbound SIP trunk + DLT registration** (AIM_VOICE_DID/AIM_VOICE_SIP_TRUNK_ID) ->
  blocks ONLY live inbound VOICE commands. Chat/Test-Console path is fully live without it.
- Paid Groq key (free works for low volume), Meta WhatsApp creds, Hatchet cross-box reachability (async
  parks inline), DO droplet limit (extraction later). ads/payments/media stay OFF.

## ROLLBACK
- Backend: set AIM_ENABLED=0 (instant inert) and/or FEATURE_AI_MANAGER=0 in /opt/famit-agent/.env +
  `sudo systemctl restart famit-caller`. Restore endpoints.py.AIMbak.1781112917 + .env.AIMbak.1781112917.
- Frontend: restore /opt/famit-panel.bak.aim-20260610-171539 + `systemctl restart famit-panel`.
