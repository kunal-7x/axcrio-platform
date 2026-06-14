# 🎯 PLAYBOOK — distilled MISTAKES-checklist + HOW-TO-WORK for every future session

> Read this RIGHT AFTER `MASTER_PLAN.md`. It is the compressed wisdom of a very long, mistake-heavy session — the exact things I got wrong and the rule that prevents each. **Do not relearn these the hard way.** And §6: every session APPENDS its own new mistakes/learnings to `AGENT_LEARNINGS.md` + (the rule, distilled) here — so the next session is even sharper. This compounds.

## 0. 🟥 ON RESUME AFTER COMPACTION — STEP 0 (before anything else)
The harness gave you a big summary at the top of this context. **Immediately save it** (verbatim) to `memory/session-summaries/<YYYY-MM-DD-HHMM>-<tag>.md` + index it — full protocol in `memory/session-summaries/README.md`. THEN read `MASTER_PLAN.md` → this PLAYBOOK → `ORCHESTRATOR.md` → `NEXT-BIG-BUILDS.md` → `AGENT_LEARNINGS.md`, and continue the autonomous build. This way no compaction summary is ever lost across chained compactions.

## 1. 🟥 MISTAKES I MADE — DON'T REPEAT (each one cost hours or broke the live product)
1. **I broke the live EARNER** editing shared outbound infra (firewall/SIP) for an inbound feature → dropped 219 outbound INVITEs. → **NEVER touch `agent.py` (md5 9150fabe4ff62b4b4470f9a87df346e5), trunks, firewall, SIP for any new feature.** Every change ADDITIVE + ISOLATED + earner-gated. Inbound work lives in `aim_voice_agent.py`/`caller.py`, never the earner.
2. **I declared things "FIXED" off green subagent reports / isolated smokes** — they were broken on the founder's REAL call. → **A green report ≠ a working product.** Only the founder's real use is truth. NEVER say "fixed/done" to him until he confirms on his real flow. State honestly what only his test can prove.
3. **I read a SIP `486 Busy` as "it rang"** for many waves — it was the carrier rejecting pre-ring (no `180`). → A REAL ring = `inviteToRingingMs>0` / 180 / 200 in the **livekit-sip container** log, NOT the agent-join line. A `486/4xx` with ONLY `inviteToTryingMs` = never rang.
4. **I hammered the DID with per-wave "earner test calls"** → spam-flagged it with the carrier → outbound earner went dead (immediate 486, no ring). → 🟥 **NEVER place real outbound test calls to gate a wave.** Verify "earner untouched" via **agent.py md5 UNCHANGED + famit-agent (MainPID 1477083) NOT restarted + /health 200 + 0 5xx ONLY.** A real call is the FOUNDER's job.
5. **I ran many box-mutating waves in PARALLEL** → the Anthropic server rate-limited me (recurring) + file collisions. → **ONE box-mutating wave at a time.** Read-only research can parallelize; builds are sequential. On "Server temporarily limiting requests": WAIT, then resume.
6. **I stopped/killed a near-finished wave casually** → wasted ~hour of work. → Don't kill; waves are **granular + resumable** (`resumeFromRunId` returns cached phases). If you must stop, resume from cache. Make every wave granular (per-unit agents) so a drop/throttle costs ≤1 unit.
7. **I burned $5 of OpenRouter** testing image-gen at volume. → **Never burn the founder's PAID credits.** Free providers (Pollinations / ElevenLabs free preview_url / ModelScope-free). 1 test max.
8. **I FORGOT planned items after each emergency** (the founder's #1 frustration). → Keep `MASTER_PLAN.md` + `NEXT-BIG-BUILDS.md` + `ORCHESTRATOR.md` CURRENT; read them FIRST every session; never re-discover; never drop a queued item.
9. **I misread ROOT CAUSES** — assumed a code regression when it was the call-window, Vobiz balance (₹0.19→402), Groq daily-quota, a carrier block, or a decoupled override flag. → **EXPLORE the real logs/box FIRST.** The "prime suspect" is often a red herring — prove it with evidence (SIP codes, balance API, journal, byte-diff). Don't guess.
10. **Decoupled override flag**: the panel "Start anyway" sent `force=true` but the backend gated on a different field → silent no-op. → **Trace any override/flag END-TO-END** (UI → API → the engine toggle it's meant to control).
11. **On-box `next build` OOMs the 2GB FORTRESS box; SCP truncates silently.** → Build the panel LOCALLY → backup-first → **md5-gate the scp before extract** → atomic swap → `chown deployuser` → restart famit-panel.
12. **The private-Spaces-URL → 403 blank bug RECURS** (images, recordings, video). → Always serve a **presigned** GET url for external fetch; HEAD-verify the object is non-empty before presigning (a 486-busy OGG decodes to silence).
13. **Voice PROMPT bugs**: the small Groq model ANNOUNCED ("kya main transfer karoon?") instead of firing the tool; a STRICT tool schema → Groq 400-storm → dead air; a forced "Hinglish" pin stopped language-mirroring. → Voice tools = loose/strict-OFF; instructions IMPERATIVE same-turn ("call the tool IMMEDIATELY; talking ≠ doing"); language = MIRROR the caller, never pinned.
14. **A subagent looked in the wrong path for the SSH key** and falsely reported "no box access". → The key is `C:\Users\kunal\.ssh\do-blr-test\id_ed25519` (verified working). Verify before believing a "can't reach box".
15. **NEVER deploy a lone feature branch to FORTRESS** when multiple FE waves have shipped — it silently reverts other waves' live features (Run page lost Wave C cost-meter; CRM lost Memory tab). → **ALWAYS unify all FE branches first** (merge all live FE waves onto one branch), build ONCE, then deploy the unified build. The safe pattern: `git merge --no-ff <each-fe-wave-branch>` → tsc 0 / build green / gitleaks 0 → scp tarball → md5-gate → atomic .next swap → restart famit-panel only.

## 2. ✅ HOW TO WORK (the pipeline, every substantive task)
Know the issue → **EXPLORE the real codebase/logs/box** for the true root cause (ground truth, not assumptions) → deep production-grade **RESEARCH** (web-search; security/multi-tenant-isolation/scale/low-latency/cost) → **DESIGN** → **EXECUTE** (backend all-green → frontend control-UI → DB → end-to-end → deploy → **VERIFY on the real flow**) → **fill every missing layer + autonomously add the out-of-box / sellable features the founder didn't name**. Think billion-dollar, not prototype. Every backend capability ships with a frontend control UI (Core_2 kit, Inter Display, zero raw hex).

## 3. 🤝 HOW TO DELEGATE (waves / subagents)
- **One scoped deliverable per agent**, with an explicit verify step. Agents return CONCLUSIONS (file:line, pass/fail), not file dumps.
- **GRANULAR waves** (per-unit `agent()` calls) = crash/throttle-safe checkpoints; deploy FORTRESS ONCE near the end, not per-FE-unit.
- **Sequential for box-mutating; parallel only for read-only research.** Never two waves on the same files/box. Never end a turn with zero waves running while queue remains (the completion notification re-fires the loop).
- Right model for the job; don't burn opus on grep. Each wave: backup-first, py_compile, restart only the changed service, commit, update the ledgers.

## 4. 🚫 GATED / FOUNDER-ONLY (never build until cleared; flag, don't ask)
Earner edits (OB-PROV, earner LLM-fallback) = agent.py sign-off + ring-gate. ModelScope = Alibaba bind. WhatsApp delivery = Meta WABA fix. Credits/Razorpay = on-hold. Ads = OAuth. Outbound dialing = DID carrier-block (Vobiz). See `MASTER_PLAN.md §5`.

## 5. 🔑 FACTS to never re-discover
Boxes/creds/venvs/the SIP-ring oracle/the FORTRESS deploy recipe/the presign pattern → `MASTER_PLAN.md §6`. Read it; don't rediscover.

## 6. ♻️ KEEP THIS COMPOUNDING (instruction to every future session)
After ANY wave or mistake: **append the new learning to `AGENT_LEARNINGS.md`** (dated, one tight line: context — lesson) AND, if it's a NEW class of mistake, add a numbered rule to §1 above. Every wave's agents READ `AGENT_LEARNINGS.md` + this PLAYBOOK before starting. This is how the next session is sharper than this one — and the session after that sharper still. Never let a mistake be made twice.
