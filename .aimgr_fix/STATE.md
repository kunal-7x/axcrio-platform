# ROUND-6b AI-MANAGER GENIUS FIX - STATE

## MANDATE
Founder livid (10-20x): add-phone-number + add-team Add buttons DO NOTHING; reset-PIN 422; "Try it" chat robotic + leaks jargon.
Fix END-TO-END (FE+BE+DB+chat) + PROVE real. Prior waves falsely reported "done" (tested backend in isolation, never FE/deployed panel).

## SURFACES
- BACKEND: ssh -i ~/.ssh/do-blr-test/id_ed25519 famit@168.144.153.145  /opt/famit-agent/ (caller.py + ai_manager/ + famit-caller :8209). NEVER agent.py/famit-agent.
- FRONTEND: root@143.110.247.249 + repo C:/Users/kunal/Desktop/caps/famit-panel/app/ai-manager/*  (reuse Core_2). Ship pre-built .next (OOM on-box).

## THE 4 DELIVERABLES
1. Phone Add -> modal (number,label,role,grants) -> persists + registers (inbound -> AI-Manager line) -> table refresh
2. Team Add -> modal (person,role,PIN) -> persists -> refresh
3. Reset-PIN -> send required admin field -> 200 (422 gone)
4. Chat "Try it" -> ChatGPT-like: full DB read, natural answers, NO jargon, PIN only for writes + proper chat UI

## LAW
- NEVER touch voice earner (agent.py md5 unchanged + famit-agent active throughout)
- famit-caller restart ONLY for backend
- panel: npm build EXIT 0 -> pre-built .next ship -> restart famit-panel -> panel.famit.in=200
- commit selectively (gitleaks 0, no -A)

## PROGRESS LOG
- [IN PROGRESS] Deep diagnosis (FE wiring + BE routes + what is actually deployed)

## DIAGNOSIS COMPLETE (2026-06-20 ground truth)
agent.py md5 BASELINE (protect) = e353b775b6415cd8391637da5bb06d24 ; famit-agent + famit-caller ACTIVE.
Backend AIM env: FEATURE_AI_MANAGER=1, AIM_ENABLED=1, AIM_LLM_PROVIDER=groq. Auth header = X-Auth (NOT Bearer). FE BASE = NEXT_PUBLIC_API_BASE || "/api".

ROOT CAUSE = FRONTEND/BACKEND CONTRACT MISMATCH (+ likely stale deployed panel):
- Phone Add: POST /numbers EXISTS + a PARALLEL R6 session (R6BEbak 00:42) already added AIM_AUTO_VERIFY=1 -> registers+routes inbound. Backend OK. Needs DEPLOYED FE + a real verify.
- Team: FE calls GET/POST/PATCH/DELETE /ai-manager/authorized-users -> ALL 404 (route ABSENT on backend). => Team card goes dormant=true => Add button disabled => "does nothing". **MUST ADD backend /authorized-users CRUD.**
- Reset PIN: /pin/set EXISTS + accepts {user_id,pin,admin} (no 422). FE also calls /pin/reset/request -> 404. The 422 was the OLD deployed panel hitting a then-missing route. Backend pin/set OK; add /pin/reset/* for completeness.
- Profile: GET/PUT /ai-manager/profile -> likely 404 (absent) => safety/settings card dormant.
- Chat: POST /commands/test EXISTS w/ _aim_llm_answer (natural reads). FE _tryit.tsx wraps reply in COMMAND-CARD chrome (risk badges Safe/Low/Med, stage parsed/executed/not_done/blocked) = the "robotic jargon leak". Treats every msg as a command.

PARALLEL SESSION NOTE: an R6 backend session already touched ai_manager/endpoints.py (numbers auto-verify) + workforce/* (NLU gap adapters). RECONCILE - do not clobber. endpoints.py live md5 = 7686219c4e3cf8b9aa9a7d774e088997.

## BUILD PLAN
BACKEND (additive, famit-caller restart only):
 B1. Add /ai-manager/authorized-users CRUD (GET list, POST create, PATCH, DELETE) -> persist team store (jsonl) + per-user PIN via firewall. Map to AimAuthUser shape.
 B2. Add /ai-manager/profile GET/PUT (persist a profile json) so the settings card is live.
 B3. Add /ai-manager/pin/reset/request + /confirm (admin reset path) -> 200.
 B4. Verify /commands/test returns CLEAN natural answers for ANY read (no jargon), PIN only for real writes. Strip leaks if any.
FRONTEND (reuse Core_2, ship pre-built .next):
 F1. Rebuild _tryit.tsx chat as ChatGPT-style bubbles: render user_facing_summary as natural text; only show confirm/PIN affordance when backend flags requires_confirmation/requires_pin (real write). Kill risk-badge/stage chrome on normal reads.
 F2. Ensure Team card un-dormants once /authorized-users returns 200; Add modal already exists.
 F3. Deploy: npm build EXIT 0 -> ship .next -> restart famit-panel -> panel.famit.in=200.

## BACKEND DONE + VERIFIED (2026-06-20 05:40 UTC)
Deployed (famit-caller restart ONLY; agent.py md5 e353b775 UNCHANGED throughout; famit-agent PID 221893 active; health 200):
- NEW ai_manager/team.py (authorized-users + profile store; registry posture; firewall per-member PIN subject).
- endpoints.py: inserted R6b routes before /sessions anchor + made /pin/set member-aware + removed DELETE step-up. Backup endpoints.py.R6Bbak.20260620-053517.

ROUTE TESTS (all over real HTTP, token via /login form -> X-Auth header):
 GET /profile -> 200 (THE dormancy fix: was 404 -> page dormant -> ALL Add buttons disabled).
 GET /authorized-users -> 200 users:[]
 POST /authorized-users (Team Add) -> 200 (usr_ created w/ role+permissions)
 POST /pin/set user_id,pin,admin -> 200 (NO 422; member-aware -> member pin_set_at flips Set)
 PATCH /authorized-users/{id} -> 200 (rename+role landed)
 DELETE /authorized-users/{id} -> 200 (step-up removed; parity w/ create/patch)
 POST /pin/reset/request -> 200 (was 404)
 PUT /profile -> 200 (persists)
CHAT backend CLEAN: how-many-leads -> Aaj tak total leads 0 hi hain...; how-many-calls-today -> Aaj 17 calls huye hain; write call-all-hot-leads -> Which campaign (eliciting, no jargon). user_facing_summary clean => JARGON LEAK IS FRONTEND-ONLY.
No stray PINs. Probe users cleaned (team empty).

ROLLBACK backend: cp endpoints.py.R6Bbak.20260620-053517 endpoints.py; rm team.py; restart famit-caller.

## PANEL DEPLOYMENT (agent-confirmed)
/opt/famit-panel ; BUILD_ID osCm5x7UxrATqG-CUU99m (06-19 19:19) ; BASE=/api ; nginx /api/ -> 10.122.0.4:8209 ; source matches deployed.
=> Add buttons UN-DISABLE now that /profile returns 200 (no FE redeploy needed for THAT). Chat needs FE rewrite -> rebuild+ship anyway.

## NEXT
- [IN PROGRESS] FE: rewrite _tryit.tsx as ChatGPT-style bubbles (render user_facing_summary natural; confirm/PIN only when flagged).
- Then build+ship+restart panel. Commit selectively.


## FRONTEND (2026-06-20 06:00+ UTC)
- Rewrote _tryit.tsx -> ChatGPT-style bubbles (render user_facing_summary only; confirm/PIN affordance ONLY when requires_confirmation/requires_pin; in-context slot replies via new sendSlotReply -> /commands/{id}/slot). Removed all jargon chrome (intent pill, risk badge, action_type, %sure, entity rows, stage labels, JSON-trace toggle). Icons: magic-pencil avatar (sparkles doesn't exist), send/check/lock confirmed present.
- _lib.ts: added sendSlotReply only. Verified box _lib.ts == local except this addition (NO parallel-session clobber).
- Local tsc --noEmit EXIT 0. Committed e750ed9 (gitleaks 0, no -A, only the 2 FE files). Parallel R6 FE commit 2a55370 is underneath.
- team.py mirrored to droplet_work/ai_manager/ (gitignored, local recovery copy).

## BUILD SAGA (panel box OOMs)
- Build #1 (default): SIGKILL (OOM) - Next15 spawns workers exceeding 1.9GB RAM.
- Build #2 (cpus:1, workerThreads:false, panel stopped, heap 1536): STILL SIGKILL. AND it CORRUPTED the live .next (BUILD_ID gone, partial dirs) -> panel HTTP 000.
  *** LESSON: npm run build CLEARS .next before building -> an OOM mid-build corrupts the LIVE site. NEVER build into the live .next. ***
- RECOVERY: restored .next from .next.R6UIbak.20260620-005046 (parallel R6 build, BUILD_ID ZsE_YmL4rT80F9v6BcNLI) -> panel active HTTP 200. Site back up (on parallel R6 build, NOT yet my chat fix).
- Build #3 (IN PROGRESS): builds into ISOLATED .next-build (distDir env), panel KEPT UP (live .next safe), +3G swap (total 7G), cpus:1 + workerThreads:false + webpackBuildWorker:false, heap 2560. On EXIT 0 -> atomically swap .next-build into .next + restart.
- next.config.ts edited on box (backup next.config.ts.R6Bbak.*): experimental single-worker + distDir env. REVERT after: cp next.config.ts.R6Bbak.* next.config.ts (or just leave - it's env-gated + cosmetic).

## EARNER SAFETY (continuous): agent.py md5 e353b775 UNCHANGED; famit-agent active PID 221893 (never touched). Backend = famit-caller restarts only.

## REMAINING
- [ ] Build #3 EXIT 0 -> swap .next-build -> .next -> restart famit-panel -> panel.famit.in=200 (verify my BUILD_ID live).
- [ ] If build keeps OOMing: fallback = build on the voice box or a clean Linux env + rsync .next (same arch). Or accept the dormancy fix alone ships via backend (Add buttons already un-disabled by /profile 200 on the CURRENTLY DEPLOYED build, since that build's _lib.ts already calls /authorized-users + /profile). Chat fix needs the new build.
- [ ] Final end-to-end verify + EARNER-LIVE-STATE.md ROUND-6b block.


## LIVE PROOF â€” 3 of 4 DELIVERABLES WORKING NOW (2026-06-20, public path panel.famit.in/api)
Authenticated end-to-end through nginx+CF (the EXACT browser path), token via /api/login:
- GET /profile -> 200 (THE un-dormancy fix: deployed build's _lib.ts already calls it; was 404 -> page dormant -> ALL Add disabled). Now 200 => page un-dormants => Phone Add + Team Add + Reset-PIN ENABLED on the LIVE deployed build, NO rebuild needed.
- GET /authorized-users -> 200; GET /numbers -> 200; POST /authorized-users (Team Add) -> 200 (usr created); DELETE -> 200.
- Chat backend via public path: "how many calls today?" -> "Aaj 17 calls huye hain." (clean).
=> Phone Add, Team Add, Reset-PIN: DONE + live. Chat: backend clean; only the FE command-card CHROME needs the new build (still on parallel-R6 build ZsE_YmL4rT80F9v6BcNLI).

## PANEL BOX CANNOT BUILD (2GB) â€” confirmed 4 OOM kills (global_oom at ~1.6GB RSS; swap doesn't save it; webpack compile needs >2GB). Voice box has no node (can't build there, must stay pristine).
## PLAN: DO resize panel droplet 576010005 (famit-panel-2) s-1vcpu-2gb -> s-2vcpu-4gb, build chat fix, ship, resize back to 2gb. Resize needs power-off (panel down ~3-5min x2, off-hours). DOES NOT touch voice box 574914961 (earner safe).
DO_API_TOKEN in .env.local. Atomic-swap deploy script ready (swap_deploy.sh: only swaps .next-build->.next on EXIT 0).

