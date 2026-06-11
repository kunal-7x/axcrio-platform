# MASTER BUILD STATE — Famit/Axcrio (live orchestration ledger)

> **Purpose:** ONE always-current place that shows what every wave/agent is building,
> its run-ID (for crash-resume), status, what it touched, and what's pending. If anything
> breaks: read this + `git status` + the box health, then resume the in-flight wave by its
> run-ID. The orchestrator updates this on every launch/completion. APPEND-ONLY history —
> never delete past entries (founder rule).

Last updated: 2026-06-12

## 2026-06-12 — ⛔ INBOUND AI MANAGER E2E VERIFICATION: STILL BROKEN ON A REAL CALL (honest verdict)
**Brutally-honest verification of the inbound voice product. The prior wave's "VOICE FIX
COMPLETE / no longer crashes on STT" claim is FALSIFIED by live evidence.**

- ❌ **VOICE (item 1) = FAIL.** A REAL inbound call reached the box Jun 11 19:37:38
  (room `aim-_06375548830_…`, agent_name=manager) — so trunk/dispatch/SIP routing WORK.
  The agent then **crashed identically to before**: `APIConnectionError: Failed to connect
  to STT WebSocket` → `_resolve_host` CancelledError/TimeoutError → `process exiting` at
  19:38:09, BEFORE any greeting. The "fix" (widened `stt_conn_options` max_retry=6/timeout=20
  in `aim_voice_agent.py`, mtime 19:19, running pid 1728381) **was live and did NOT help** —
  each retry's DNS `_resolve_host` hung the full timeout. **6/6 inbound STT connects on Jun 11
  FAILED (0 ever reached "connected successfully").**
- 🔬 **Root cause is NOT keys/network/venv** — proven: from the agent's *exact* venv+env in a
  standalone process, `sarvam.STT().stream()` → "WebSocket connected successfully" (clean).
  And the EARNER (`agent.py`, same Sarvam STT, same `.env`, same `/opt/capsy-agent/.venv`)
  = **30/30 STT connects succeeded** over 3 days, last real call 18:48:47 connected in 0.4s.
  DNS resolves fine now (api.sarvam.ai→20.235.220.20, 22ms connect). **The hang is specific to
  the inbound LiveKit job subprocess at session startup** — most likely the inbound entrypoint/
  imports starve the job-process event loop (or its getaddrinfo thread-executor) during the
  window STT tries to resolve DNS, so every retry's `_resolve_host` times out. NOT isolated to a
  single line yet, but the empirical split (inbound 0/6 vs earner 30/30, same box) is unambiguous.
- ❌ **LOGGED (item 2) = FAIL (by consequence).** `ai_manager_sessions` = **0 rows**,
  `ai_manager_session_turns` = **0 rows**. No call has ever survived to produce a transcript/
  recording. Schema + read API + recorder exist but have never recorded a real call.
- ⚠️ **PANEL (item 3) = PARTIAL.** `panel.famit.in/ai-manager` 200, Calls tab + Session Detail
  routes render 200 — but the list is **empty** (no sessions exist). Cannot prove a real
  transcript/recording renders until a call actually completes.
- ✅ **REGRESSION (item 4) = PASS.** Earner UNTOUCHED + HEALTHY: `agent.py` md5
  `9150fabe4ff62b4b4470f9a87df346e5` (matches prior), famit-agent NRestarts=0, all 4 services
  active, ports 8090+8091 listening, famit-caller :8209 /health=200, last earner call ran full
  ~2.5min lifecycle clean, **0 Traceback/ERROR/APIConnection in earner since 19:00**, zero 5xx.

**REMAINING GAP / NEXT STEP (the real fix, not another retry band-aid):** the STT connect must
not depend on the job subprocess's event loop being free at startup. Options, in order:
(1) **prewarm the STT/DNS** — resolve api.sarvam.ai + warm an aiohttp connector in the worker
`prewarm_fnc` (runs in the parent, before the job loop is busy), or pin a short-TTL DNS cache;
(2) audit the inbound entrypoint for any sync/blocking call before/around `session.start` that
starves the loop and move it off-thread / after first audio; (3) start the AgentSession with STT
deferred until after greeting (greet on join is TTS-only, doesn't need STT) so a slow STT connect
can't gate the greeting. Verify by a REAL test call (founder-gated on Vobiz routing + a call from
+917861019021) showing "WebSocket connected successfully" + audible greeting + a logged session row.
Build log: `memory/build_log/wave-build-inbound-aim.md`. HOWTO (honest): `HOWTO-inbound-call.md`.

## 2026-06-11 — ARCHITECTURE DOC WAVE (master ARCHITECTURE.md + 6 deep-dives) ✅
- Wrote `ARCHITECTURE.md` at repo root — the single onboarding map a new Claude-Code teammate reads to
  understand the whole platform. Synthesizes the six `docs/architecture/0{1..6}-*.md` deep-dives into one
  doc with all 10 required parts (what-is-this; system-context; container/topology; codebase mindmap;
  backend/ai-asset/frontend/deployment/growth-os sections; end-to-end flow sequences + ER data model;
  file-map tables; tech stack; how-to-run + boxes/services quick-ref; glossary of the moat / closed loop /
  Revenue-Truth Signal Loop / strangler / RLS / Control Layer / Tenant Zero / Origin Connector).
- 13 Mermaid blocks, all GitHub-renderable + validated (26 fence lines = 13 balanced pairs; 5×graph,
  1×mindmap, 4×sequenceDiagram, 2×erDiagram; sequence alt/loop/end balance = 0). System-context, topology,
  and mindmap are NEW synthesis diagrams; the rest lifted verbatim from the already-validated source docs.
  Every box/edge grounded in real `file:line` via the six deep-dives.
- The six deep-dives (each Mermaid-validated, file:line-grounded): `01-backend.md` (caller.py monolith),
  `02-ai-asset-service.md` (:8310 Creative Studio), `03-frontend.md` (famit-panel), `04-deployment.md`
  (infra topology), `05-growth-os.md` (new microservices monorepo, Phase-0 scaffold), `06-flows-data.md`
  (5 journeys + full PG data model). Report: `memory/build_log/wave-build-architecture.md`.
- READ-ONLY: docs only, NO app code edited, NO deploy, NO git. Carried-forward caveats: AI-Asset live
  `/status` probe unverified (backend box rejected the SSH key); live-box `ai_manager` internals may be
  newer than the local tree (re-sync before AI-Manager edits).

## 2026-06-11 — 6-FLOW END-TO-END VERIFY (live public API) + WhatsApp path fix
- Ran the 6 demo flows against the LIVE public surface (panel.famit.in/api, admin X-Auth). Results:
  (1) Creative PASS load+status (/creative 200, /assets/status 200 enabled); public generate needs a real
  login JWT (legacy X-Auth correctly rejected by the standalone svc) -> already JWT-proven in C3.
  (2) Control Layer: entitlements live (v1/91 modes/all-on for admin), middleware passes admin; /admin/*
  correctly 403s the legacy pw (the #1 security control) -> HIDE/LOCK write already 18/18 probes PASS.
  (3) **AI Manager FULL LOOP PASS LIVE** — safe read = human Hinglish; risky "Saare hot leads ko call karo"
  -> leads.enqueue_calls risk=3 needs_pin; no-pin blocked; wrong-pin denied; PIN 2468 -> executed=True
  run_id=run_20864727e4 outcome=effective "Done! calls successfully ho gaya." (NEVER raw JSON to user).
  (4) WhatsApp PASS after fix — live POST /whatsapp/campaign/{id}/generate-templates returns 3 Meta-compliant
  templates (compliance.valid, no_invent_flags:[], score 1.0). **BUG FOUND+FIXED**: frontend waapi.ts called
  the never-mounted /whatsapp/templates/generate (404); repointed to the live campaign-scoped route + mapped
  the nested body/buttons shape (tsc 0 errors). (5) Workflow PASS — _editor.tsx real React Flow v12, addNode
  (click+drop) + fullscreen+Esc. (6) Regression PASS — core 200, 11 public routes 200, zero 5xx.
- ONE local change: famit-panel/app/whatsapp/_lib/waapi.ts (branch feat/premium-ui, NOT yet deployed).
  Reports: memory/build_log/wave-build-e2e-verify.md + E2E_VERIFY_STATE.md. PENDING: deploy the waapi fix
  (FORTRESS, backup-first); a real admin login pw to exercise public-JWT Creative generate + control-plane writes.

## 2026-06-11 — C3 END-TO-END VERIFY (the demo proof) ✅ + the one panel-path blocker
- Verified Creative Studio + WhatsApp Builder END-TO-END for the demo. **Creative Studio** (panel-equivalent
  VPC path, real admin Bearer JWT): `POST /generate` (Codename Joy 3.0, n=2) -> job `gj_9792a293b4974ac6`
  -> SSE stream emitted REAL phases (streaming/rendering done 0/2 -> succeeded/done 2/2, real progress, no
  fake %) -> 2 openrouter banners in **DO Spaces** (`creative/admin/banner/20260611-043239-w26y7a-{0,1}/
  0.png`, 1.38MB+901KB, valid 1024² PNG) -> **presigned URL GET 200 image/png** (panel can fetch) -> wallet
  settled **ACTUAL Rs6.76 (676 paise), no double-charge** (avail 7172->6496, held 0, spend 2828->3504).
  **WhatsApp Builder**: `POST /whatsapp/campaign/c17e55e9f3/generate-templates` -> bundle
  `wab_61741da7...`, 3 Meta-compliant MARKETING templates, **validator-as-authority** (caught a real
  "body cannot start with a placeholder" violation), `no_invent_flags:[]`. **Isolation** PASS both (forge
  tenant-B -> 404/0; admin token + body tenant_id=B -> owner=admin, body IGNORED; B-token/unauth -> 401).
  **Live earner UNTOUCHED**: famit-caller/agent/aiasset/**bridge** active, core 200, /run/preview 200, 0
  5xx, caller/agent never restarted by me.
- **THE ONE BLOCKER to a clickable browser demo:** public `panel.famit.in/api/assets/*` TIMES OUT (000)
  while sibling `/api/campaigns`,`/api/me`,`/api/whatsapp/inbound` reach the backend fine. The
  `famit-aiasset` journal shows NO request arriving on 8310 during a panel hit; a direct VPC hit
  `10.122.0.4:8310` IS logged + 200. => **the FRONTEND-box nginx `location /api/assets/` upstream is stale**
  (not repointed at `10.122.0.4:8310` after the service moved its bind to the VPC IP). Backend ufw already
  ALLOWS 8310 from 10.122.0.2. Fix = one-line FE-nginx `proxy_pass http://10.122.0.4:8310;` + reload.
  No SSH to the FE box in this session -> founder/eng-blocked. Everything behind it is GREEN.
- Cosmetic gaps (non-blocking): asset `version.storage='local'` though bytes ARE in Spaces +
  presigned-fetchable; per-tenant AIASSET_ENABLED still a global env flag. Build log:
  `memory/build_log/wave-build-C3-e2e-verify.md`; state `droplet_work/ai_asset/C3_VERIFY_STATE.md`.

## A. CURRENT SNAPSHOT (what's live / building / queued)
- **LIVE & verified:** voice calling (Run-a-Campaign), leads/calls/billing meter, multi-tenant Postgres+RLS, the 6 cred-free modules (forms, support, ai-manager-basic, workflow-studio, booking, funnels), Run-Campaign upgrade (CSV+Excel+filters), React-Flow Workflow builder, premium "Signal" UI + **Gilroy font + real logo**, the overhauled module pages. panel.famit.in healthy.
- **AI MANAGER: ✅ DONE + ACTIVATED + 🎉 TEST CONSOLE FOUNDER-VERIFIED (2026-06-10)** — PIN `2468` set for tenant `admin`; the live Test Console runs the full loop (safe command read-only, risky command demands PIN `2468`, unsafe command blocked). All §10 routes 200 (`POST /ai-manager/commands/test` live). Note: PIN UI lives on `/ai-manager/users` (not `/setup`); `/ai-manager/history` should redirect to `/ai-manager/commands` — both minor, queued for frontend polish. Flags: `AIM_ENABLED=1 FEATURE_AI_MANAGER=1 AIM_LLM_PROVIDER=groq WORKFORCE_ENABLED=1`.
- **AI MANAGER INBOUND PHONE LINE: ✅ ARMED our-side + ARM-VERIFIED (2026-06-11)** — call +918071583488 -> a SEPARATE LiveKit worker `agent_name="manager"` (`aim-voice-agent.service`, :8091, worker `AW_oB4R2aoYkBBp`) answers -> PIN -> NLU -> risk gate -> step-up -> EXECUTE via the AIM brain (same `CommandMachine`/`delegate.execute` as the chat Test Console). PIN now **`4827`** (firewall `check_pin("admin","4827")=True`). ADDITIVE: new inbound trunk `ST_K785ASpNh5ow` + dispatch `SDR_RaCvweSMA2p5` + tcp/5060 listener + 10-Vobiz-IP DOCKER-USER/UFW allowlist; **outbound earner trunks/agent BYTE-IDENTICAL + a live outbound call ran during wiring AND during arm-verify (0 5xx, 0 errors today)**. Arm-verify FOUND+FIXED 2 enrollment gaps (Unit 6 was never applied): seeded `ai_manager` registry for +917861019021 (3 caller-ID forms, tenant=admin/role=admin/verified) + set full `KNOWN_GRANTS` — else the live call would have hit `reject:unregistered` before the PIN, and risky cmds were perm-denied. End-to-end brain proof PASSES (PIN 4827 verifies, safe cmd no re-PIN, risky cmd demands step-up, scope-bound token mints+verifies, wrong-scope=None, 0 PIN leak). **REMAINING (founder-only):** point Vobiz inbound trunk URI -> `sip:168.144.153.145:5060` Transport **TCP** + link DID, then place the live call. Founder HOWTO: `caps/HOWTO-inbound-call.md`. Ledger `droplet_work/INBOUND_AIM_DEPLOY_STATE.md`; build log `memory/build_log/wave-build-inbound-aim.md`.
- **BUILDING NOW:** (a) Control Layer build — run `wf_f3ae354a-1a7` (entitlement engine + HIDE=404/LOCK=402 middleware + Super Admin UI, dormant until T1–T18). (b) **UI OVERHAUL research** (read-only) — run `wf_d1baa873-edb`: founder VERY frustrated with UI; port his NEW reference React kit `C:\Users\kunal\Desktop\core-2-dashboard-builder-react` to ALL pages, fix font (looked unchanged = Gilroy 2-weight fallback to Inter), clean headings (no subtitle), consult frontend-design skill. → `UI_OVERHAUL_PLAN.md`.
- **QUEUED (after Control Layer build; UI overhaul + voice can run parallel = different boxes):** (1) **UI OVERHAUL BUILD** — port the reference kit to every page + adopt its font app-wide + clean headings + simplify (esp. AI Manager); supersedes the minor polish (also fixes `/ai-manager/history`→`/commands`, PIN UI on setup). (2) ✅ DONE — AI Manager INBOUND voice wiring ARMED + ARM-VERIFIED 2026-06-11 (TCP 5060 + 10 Vobiz IPs + inbound trunk `ST_K785ASpNh5ow`/dispatch `SDR_RaCvweSMA2p5` -> `manager` agent + registry/grants seeded; PIN `4827`). Only Vobiz-side URI->TCP + DID-link remains, then the founder's live call. See the AI MANAGER INBOUND line above + `HOWTO-inbound-call.md`.

## B. WAVE LEDGER (run-IDs for resume; newest first)
| Wave | Run ID | Status | Builds / Result |
|---|---|---|---|
| Creative+WA frontend W3 (build/nginx/deploy) | (agent W3) | ✅ DONE + LIVE (2026-06-11) | local+box build EXIT 0; nginx `/api/assets/`→`10.122.0.4:8310` added (more-specific, SSE-ready, `nginx -t` ok, reloaded); FORTRESS deploy `/opt/famit-panel` (backup `.bak.20260610-214804`); **all public routes 200** (`/ /login /campaigns /whatsapp /creative /creative/library /creative/brand /ai-manager /super-admin /run /leads /billing/overview /workflows`); GenerationLoader + font(inter, 0 gilroy) proven. ⚠️ BLOCKER: backend `:8310` CLOSED to VPC → `/api/assets/*` 504 (routing PROVEN correct; Creative/WA-AI stay dormant-safe). Report: `memory/build_log/wave-build-creative-wa-frontend.md` |
| Creative Studio frontend design | `wf_2281222c-977` | ✅ DONE (read-only) | dot-matrix loading component + premium workspace + asset library + out-of-box → `CREATIVE_STUDIO_FRONTEND_PLAN.md` |
| WhatsApp Campaign Builder design | `wf_8768c619-466` | 🔄 RUNNING (read-only) | AI template gen + Creative Studio integration + delivery/analytics/learn → `WHATSAPP_CAMPAIGN_BUILDER_PLAN.md` |
| AI Asset Service backend (A1–A4) | `wf_d5fb022d-209` | ✅ DONE — **LIVE REAL-BANNER PROOF PASSED (A4, 2026-06-11)** | NEW service `:8310` LIVE on the box; A2+A3 deployed; OpenRouter `gemini-2.5-flash-image` generated 3 REAL banners (1024², 1.3–1.9MB) from a real campaign; wallet settled ACTUAL Rs10.14 no-double-charge; isolation PASS (forge B→404, body-override ignored); live platform UNTOUCHED. `AIASSET_ENABLED=1` for admin tenant. Report: `memory/build_log/wave-build-aiasset-A4.md` |
| UI overhaul build | `wf_3bdaf0b5-4f1` | 🔄 RUNNING (frontend lane) | port `core-2-dashboard-builder-react` to all pages, Inter Display app-wide, clean headings (no subtitle), simplify AI Manager 7→3 tabs, reskin super-admin |
| Control Layer build | `wf_f3ae354a-1a7` | ✅ DONE + LIVE (2026-06-11) | entitlement engine + HIDE=404/LOCK=402 middleware + /admin + act-as + suspend + Super Admin UI; `CONTROL_ENABLED=1`; **18/18 live probes PASS**; /super-admin 200. Residual: panel hmac no-jti (status-floor); deferred C10 copilot gate |
| AI Manager build | `wf_8be3686e-0f6` | ✅ DONE + ACTIVATED | schema+RLS+no-double-execute, Groq NLU + 25 tools, /ai-manager+/setup live; /history 404 gap |
| Vobiz inbound setup | (agent, done) | ✅ DONE | `ai_manager_INBOUND_SETUP.md` + `design/aim-inbound-wiring-plan.md` |
| Control Layer research | `wf_3e8535b5-b0b` | ✅ DONE | design/control-*.md + CONTROL_LAYER_EXECUTION_PLAN.md |
| AI Manager design | `wf_6f9aee7a-6a0` | ✅ DONE | design/aim-*.md + AI_MANAGER_EXECUTION_PLAN.md (found ~80% pre-built) |
| Wave 2 features | `wf_135ac91c-e2a` | ✅ DONE | Run-Campaign + Workflow builder + module-page overhaul, deployed |
| Foundation + research | `wf_97c13a78-109` | ✅ DONE | Gilroy font + real logo + Core_2 shell LIVE; run-campaign/workflow/reuse specs |
| Make-it-real | `wf_9d2b98c3-ab9` | ✅ DONE | activated 6 modules (isolation-proven) + UI uplift + need.md |
| Mount reconcile | (agent, done) | ✅ DONE | 9/9 module routers mounted (flag-gated) |

## C. PENDING FROM FOUNDER (the only things blocking "fully done")
1. **Vobiz inbound:** ✅ Trunk ID received = `317a5dce-9237-4ff9-8de9-54b85c2dfe2d` (`.env.local` `TRUNK_ID`). ✅ Source IPs RESOLVED (2026-06-10, web): Vobiz publishes 10 SIP-signaling IPs at `docs.vobiz.ai/concepts/ip-whitelisting` — `13.203.7.132, 65.2.100.211, 13.126.98.234, 13.235.11.131, 13.233.44.61, 3.111.255.163, 3.111.128.110, 43.204.64.203, 15.207.232.91, 35.154.133.28` (all AWS ap-south-1; candidate `13.203.7.132` confirmed as #1). Box allows only `13.203.7.132` today → wiring step must allowlist all 10 (UFW + DOCKER-USER + `allowed_addresses`). Still pending: choose + enroll AI Manager PIN (dashboard). IPs "subject to change" per Vobiz; optional belt-and-braces = ask Vobiz which IP serves this DID.
2. **Raise DigitalOcean droplet limit** (3/3 used) + a payment method — lets AI Manager get its own box + frees infra headroom.
3. **need.md credentials** (by impact): Meta WhatsApp · Meta/Google Ads · Razorpay/Stripe · AI media key (video/image/3D) + DO Spaces · optional paid Groq · Logto Google OAuth · re-scoped Cloudflare token.
5. **Expose backend `:8310` (AI Asset service) to the VPC** — nginx `/api/assets/`→`10.122.0.4:8310` is wired + live on the frontend box, but `:8310` is CLOSED/FILTERED from the frontend priv IP (10.122.0.2), so Creative Studio generation + WA AI-templates run dormant-safe (coming-soon). Fix on the BACKEND box: open its firewall to 10.122.0.2 on 8310 (UFW + DOCKER-USER if dockerized) and/or bind the asset service to the private iface. Verify: `curl https://panel.famit.in/api/assets/status` returns JSON (not 504).
4. **(optional)** full Gilroy paid font weights (400–700) — looks good now with the Inter fallback.

## D. RESUME PROTOCOL (on any crash/glitch)
1. Read this file + `git status` + box health (ssh famit@168.144.153.145: services active, `/campaigns` 200, `caller.py` AST-OK; curl panel.famit.in/login 200).
2. Find the 🔄 RUNNING wave above → relaunch `Workflow({scriptPath, resumeFromRunId})` (cached agents return instantly).
3. Per-wave detail lives in `memory/build_log/wave-build-*.md` (durable) + the `.wf/*.js` scripts + the `design/*.md` specs. Nothing is lost.

## 2026-06-11 — WhatsApp + DO Spaces creds received & tested (report: WHATSAPP_GOLIVE.md)
- DO Spaces creds VALID (PUT/GET/DELETE roundtrip PASS, bucket capsy-recordings/sgp1).
- WhatsApp webhook DEPLOYED & VERIFIED: callback `https://panel.famit.in/api/whatsapp/inbound`, verify token `evsaivoiceagent` (matches box .env). Meta GET handshake returns 200/echo. Founder just pasted wrong URL.
- WhatsApp SEND BLOCKED: META_WA_TOKEN is App-ID-shaped → Graph 401. Replace with permanent System-User token before sends work.
- Post-Control-Layer apply wave: fix META_WA_TOKEN, set FEATURE_WHATSAPP, add Spaces creds to AI Asset env, restart famit-caller, re-test. READ-ONLY this pass (no box edits/restarts/deploy).

## 2026-06-11 (update) — WhatsApp LIVE end-to-end
Real EAA token in ALL_CREDENTIALS.md. WhatsApp SEND PASS (real msg delivered to +917861019021, wamid). Number Cloud-API-registered. Webhook already connected on Meta (panel.famit.in/api/whatsapp/inbound). Open items: WABA branded "MedFlow"/+91 97550 40013 (confirm); only hello_world approved (need real template for cold sends); box .env still has OLD token → update + FEATURE_WHATSAPP + restart famit-caller in post-Control-Layer wave. Report: WHATSAPP_GOLIVE.md.

## 2026-06-11 (update) — UI OVERHAUL W3: BUILD GREEN + DEPLOYED LIVE
Inter Display app-wide (Gilroy removed from body cascade) + clean single-line headings (PageHeader subtitle/eyebrow/accent stripped). Local `npm run build` EXIT 0. FORTRESS deploy to root@143.110.247.249:/opt/famit-panel: tar(excl node_modules/.next/.git/.env.local)→scp→**backup `/opt/famit-panel.bak.20260611-014711`** (rollback target)→extract over live (preserve node_modules/.next/.env.local)→chown deployuser→`npm install --legacy-peer-deps`→`npm run build` EXIT 0→`systemctl restart famit-panel` (active). VERIFIED: 25/25 app routes 200 on localhost:3001; 17/17 public https://panel.famit.in routes 200. FONT PROOF in served HTML/CSS: `/login` body=`font-inter` only (no Gilroy anywhere in HTML); served CSS references exactly 5 woff2 (Inter Display 300–700) + ZERO `gilroy`. HEADING PROOF: `/` uses `text-h4`/`text-h5` tokens, NO `page-head-sub`/`page-head-eyebrow`/`signal-glyph`. NOTE: nav LABELS renamed in W1 but route folders NOT moved — live URLs still `/suppression`, `/billing/explorer`, `/billing/plan`, `/ai-manager/*` (URL renames = follow-up unit). Report: build_log/wave-build-ui-overhaul.md. ROLLBACK = `systemctl stop famit-panel; rm -rf /opt/famit-panel; mv /opt/famit-panel.bak.20260611-014711 /opt/famit-panel; systemctl start famit-panel`.

## 2026-06-11 — AI MANAGER CREATIVE WIRING (B3): voice/chat command -> REAL banner ✅
- Wired the parked workforce `creative.*` adapters to the LIVE AI Asset Service (`:8310 POST /generate`).
  An AI-Manager command now generates a real banner. PROVEN via Test Console (admin): "Create 2 ad banners
  for the Codename Joy 3.0 campaign" -> NLU `creative.generate_banner` risk=money(3) requires_pin -> PIN
  2468 -> step-up -> delegate -> `run_agent(role=creative)` -> adapter -> asset `/generate` -> OpenRouter
  gemini-2.5-flash-image -> REAL 1.2MB PNG (1200x628, uploaded to DO Spaces). Wallet settled ACTUAL Rs6.76
  NO double-charge (one hold->settle, held=0, lifetime_spend 2028); immutable audit; re-execute->`command
  not found` (terminal). Isolation: asset /generate unauth/bad-bearer->401, token-derived, RLS sees 0
  cross-tenant. Regression PASS (core 200, all 3 services active, 0 5xx, caller/agent untouched).
- 4 box files (backups *.B3bak.20260610-215522, restart famit-caller ONLY): `workforce/config.py`
  (+asset_service_base), `workforce/tools/transport.py` (+call_service base=...), `workforce/tools/
  catalog.py` (creative adapters -> /generate, asset_type banner|video_cover), `ai_manager/delegate.py`
  (mint+thread run_token + emit task['plan']). TRAP: workforce StubPlanner reads `task['plan']` not
  `task['actions']`, LLM planner still dormant-stub -> delegate MUST set plan + run_token. Single
  money-path = the asset svc (workforce `recompute_spend_minor(creative)`=0 -> no workforce reserve).
- Founder-blocked: real Meta-approved template + confirm MedFlow WABA number (to PUBLISH, not generate).
  Eng follow-up: per-tenant AIASSET_ENABLED (global env today) + AIM campaign-name->id resolver.
  Build log: `memory/build_log/wave-build-aim-creative-wiring-B3.md`.

## 2026-06-11 — AI ASSET SERVICE: LIVE REAL-BANNER PROOF (A4 / Wave E) ✅
- Deployed A2+A3 (were local-only) into `/opt/famit-aiasset`; set `OPNEROUTER_API_KEY` + `FAMIT_VAR`; flipped `AIASSET_ENABLED=1` for the `admin` test tenant; restarted **famit-aiasset ONLY** (caller/agent untouched, both active since before the work; `/health`+`/campaigns` 200).
- **Real banner: YES.** Campaign "Codename Joy 3.0" (Shapoorji Pallonji, `c17e55e9f3`) -> prompt_builder -> `google/gemini-2.5-flash-image` -> 3 PNGs `1024x1024 1.3-1.9MB` at `/opt/famit-aiasset/var/creatives/<job>/0.png`. 3 distinct angles (location/social-proof/benefit) with distinct headline+CTA, all facts verbatim (no-invent held).
- **Wallet settled ACTUAL** Rs10.14 (1014 paise) from live `usage.cost`, est 1132, refund 118, no double-charge; immutable `ai_asset_audit_logs` rows written. **Isolation PASS** (B forges admin job->404; admin token+body tenant_id=B -> job vendor=admin, body ignored; unauth->401).
- Fixed 4 deploy bugs (router missing openrouter in ladder; shared reserve idem-key -> same hold -> charged 0; standalone-venv token auth via PyJWT + shared-secret lazy-init + verified access_claims; admin-GUC threaded through the wallet path). All in `wave-build-aiasset-A4.md`.
- Gaps (need.md): version.local_path unset (PNG on disk, /raw can't serve); cross-module PG events leg not written (per-vendor mirror is); per-tenant flip is a global env today. DO Spaces creds already VALID -> swap box-fs for prod storage next.

## 2026-06-11 — INVESTOR PITCH DECK: VISUAL QA + FINALIZE ✅
- Artifact `investor/Famit-Investor-Pitch-Deck.html` (~78KB, 14 slides, NO git) — VC seed-raise
  deck (company-as-investment), separate from the `sales/` buyer proposal. Companion
  `investor/README.md` (present via arrow keys / Ctrl-Cmd+P -> Save as PDF landscape, background
  graphics ON). Build log: `memory/build_log/wave-build-investor-deck.md`.
- QA PASS (all): self-contained/offline (both logos base64-embedded, decode to valid PNG;
  white-on-dark on all 14 dark slides; Inter+system-fallback) · nav (arrows/Space/PgUp-Dn/Home/End,
  click-halves, swipe, buttons; embedded JS `node --check` clean) · counter+progress (total set
  from slides.length, 14==14) · print (one clean 1280x720 landscape slide/page).
- FIXES this pass: HARDENED `@media print` (fixed-px 56/84 padding; pinned all `vw/vh` clamp() type
  to fixed px so heads/title/sub/kpi/pull can't overflow the 720px page; tightened dense-slide
  rhythm) -> deterministic PDF, no clipping regardless of viewport. Added `prefers-reduced-motion`
  guard. Content fix slide 6 (removed jargon "posterior of hundreds" -> plain-English network-effect).
  Structure 14/14 sections, 274/274 divs balanced.
- FOUNDER-TO-FILL (blank by design, never invented): slide 12 Team x3 (CEO/founding-eng/GTM-advisor
  real names+backgrounds); slide 14 Ask = raise amount + runway months + valuation. All other
  numbers real/sourced or tagged Roadmap; traction honest pilot-scale (96 calls/8 campaigns/18-18/
  metered COGS).
- SALES PROPOSAL — VISUAL QA + FINALIZE pass (2026-06-11) DONE on
  `sales/Famit-AI-Revenue-Platform-Proposal.html`. Verified via headless-Chrome CDP (no deps,
  built-in WS client): self-contained OK (logo base64 = byte-identical 1454x1454 PNG, decoded 89,378 B
  matches source; only external refs = Google Fonts CDN w/ system fallback + panel.famit.in CTAs +
  mailto). ROI JS computes live & matches headline (500 leads/5%->6.25%/Rs15k/Rs30k/Growth =
  Rs98,751 net · 5.0x · ~6 days · Rs11.85L/yr). Tag balance 347/347 div, 11/11 section, JS `node --check` OK.
  No lorem/TODO/placeholder. FIXED 3 issues: (1) mobile horizontal-overflow 18px->0 — root cause
  `.card-moat{grid-column:span 6}` auto-created 5 implicit grid cols on the 1-col mobile bento; fix =
  `grid-column:1 / -1` + `min-width:0` on bento/moat/sigflow children; (2) print: `.section` was
  `page-break-inside:avoid` (forced whole sections -> gaps) and `.roi-shell`(1338px > page) avoid-break
  -> changed sections + large containers (roi-shell/loop-stage/bento/tiers/steps) to break-inside:auto,
  kept avoid only on small cards; (3) static "+6" extra-customers -> "+6.3" to match JS. Print verified:
  0 hidden reveals in print media, nav+sticky hidden, 8-page clean PDF, no cut cards. Mobile+desktop
  overflow_px=0 at true window sizes. README.md written for founder (open / Ctrl+P->PDF / swap
  logo+testimonials). NO git. _qa scratch (chrome profiles/screens/scripts) removed after pass.

- FIX-FOUNDER-FLOWS wave (2026-06-11) — the 3 "still broken in the browser" flows, verified at the
  USER->backend chain (not API bypass), then deployed. Report `memory/build_log/wave-build-fix-founder-flows.md`,
  ledger `caps/FIX_WAVE_STATE.md`.
  • FLOW 1 CONTROL = **FIXED + DEPLOYED**. Stale doc was wrong (nav already had feature_key + RouteEntitlementGate
    mounted). REAL bug = FE/backend KEY MISMATCH: nav authored bare module keys `grow`/`sell`/`engage`/`ai_manager`/
    `command`/`automate`/`intelligence`, but `/me/entitlements` modes uses `mod.grow`... -> module HIDE never dropped
    the sidebar group (page children matched, so only the empty group header lingered). Live bundle confirmed buggy.
    FE-only fix in `contstants/navigation.tsx` + `lib/api.ts FEATURE_REGISTRY` (module keys->mod.*, billing->
    money.billing_overview). tsc/build clean. Deployed to live panel (backup `.next.CLfixbak.20260611-183733`).
    Final live flow: admin HIDE mod.grow -> vendor modes['mod.grow']=hidden -> nav drops Grow + /campaigns 404;
    LOCK->402; admin bypass; restore->on/200. Vendor genuinely cannot see it now. Backend untouched (already correct).
  • FLOW 2 WORKFLOW = **PASS** (already built; engine LIVE). /workflows mounted (FEATURE_WORKFLOWS=1). Editor has
    blank-from-scratch + click-to-add node + fullscreen+Esc. Live chain: create->save{draft}->validate ok->publish
    v1->RUN ok run_id engine:in_process status:COMPLETED steps:2. Add node + save + publish + RUN executes for real.
  • FLOW 3 WHATSAPP = **PASS**. whatsapp_builder mounted (FEATURE_WHATSAPP_BUILDER=1). AI generate (funded admin)
    -> 3 Meta-compliant templates (groq llama-4-scout); validate authority passed; submit-to-meta route present.
    Broke vendor -> insufficient_credits (₹4 est) = correct credit gate, not a bug.
  • REGRESSION = **PASS**: core /campaigns /leads /me /me/entitlements /calls 200; famit-caller + famit-bridge(voice)
    active; zero 5xx; test tenant clean; temp scripts removed from both boxes.

## 2026-06-11 — CREATIVE STUDIO image-render fix (broken-icon / stuck-on-Rendering) ✅
- SYMPTOM: thumbnails = broken-image icon; Generate sticks on "Rendering / 0 of 1" though the job
  SUCCEEDS and the image IS stored. Browser couldn't DISPLAY the bytes.
- ROOT CAUSE: private DO Spaces bucket (`capsy-recordings`, ACLs disabled) → direct private URL 403s
  an `<img>`, and the `/raw` proxy needs X-Auth an `<img>` can't send → 401. FIX (already built by a
  prior session, now VERIFIED LIVE): backend `ai_asset/store.py:_presign_row_urls` rewrites
  url/thumb_url to a fresh 24h boto3 presigned GET (`creative.asset_library.spaces.presign`);
  `/raw` 302-redirects spaces versions to it; frontend `app/creative/_components/AssetImage.tsx` =
  native `<img>` (not next/image) with onError placeholder.
- LIVE PROOF (curl as the browser `<img>`, UNAUTHENTICATED): list → presigned spaces url returns
  **200 image/jpeg 63436 bytes** (magic ffd8ffe1). Generate n=1 pollinations (₹0, no OpenRouter) →
  succeeded → new asset `ca_f500eeccdf8e4343` storage=spaces → presigned url **200 image/jpeg 63436b**.
- SECONDARY (NOT code-fixable): 24 orphaned `local` rows (admin tenant) have EMPTY local_path AND url
  (pre-Spaces failures, no bytes anywhere) → always broken icon. Recommend one-time DB cleanup.
- FRONTEND DEPLOY: panel-box source == local (md5 identical). Rebuilt+redeployed panel so live build
  embeds the verified AssetImage; backup `.next.renderfixbak.20260611-165608`. Build OOM-SIGKILLed on
  the 1.9Gi box; added temp 3G swap (`/swapfile.build`) to complete it.
- REGRESSION: caller/agent/bridge/aim-voice-agent/aiasset active; /campaigns 200; aiasset /status 200;
  OpenRouter never called. Live earner untouched. Detail: `memory/build_log/wave-build-fix-platform.md` §image-render.
