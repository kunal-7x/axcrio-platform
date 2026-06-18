# 04 — SESSION HISTORY (the chronological journey) + FOUNDER PREFERENCES

> **Purpose:** the founder is about to compact and start fresh. This file preserves the
> chronological "what happened" across every past session/compaction so a new session
> understands the JOURNEY — not just the current state. State lives in `MASTER-INDEX.md`;
> the *story* lives here. Reconstructed 2026-06-18 from the transcripts
> (`.claude/projects/.../*.jsonl`), the per-compaction summaries, and the on-disk ledgers
> (`MASTER-INDEX.md`, `WORKFLOW_LEDGER.md`, `ORCHESTRATOR.md`, `memory/*`).
>
> **Range reconstructed: 2026-06-03 → 2026-06-18** (≈15 dated session-segments).
> Earner-safety law held throughout: live `agent.py` md5 `9150fabe4ff62b4b4470f9a87df346e5`
> was NEVER edited without sign-off; the only real outbound ring was a founder-authorized test.

---

## PART A — THE CHRONOLOGICAL STORY (dated)

### 2026-06-03 — Voice agent latency (session start)
- **ASK:** "The call latency is very high, can you reduce it." (live Riya/Godrej call agent.)
- **DONE:** Latency tuning on the famit-livekit droplet — TCP trunk, iptables RTP, model/voice
  tuning. Established the live low-latency voice setup.
- **DECIDED:** Keep Groq for the LLM (don't swap off). LiveKit semantic turn-detector flagged as
  future work.

### 2026-06-03 → 2026-06-05 — Real billing meter + WhatsApp backend (v3)
- **ASK:** "I want to see actual costs" per call (ElevenLabs / Groq / Sarvam / Vobiz).
- **DONE:** v3 real metered billing (vendor-API metered + Vobiz CDR), multi-tab sidebar billing UI,
  WhatsApp automation pipeline (dormant until Meta creds).
- **DECIDED:** WhatsApp stays dormant until Meta WABA credentials are provided.

### 2026-06-05 → 2026-06-06 — Typography polish + voice-architecture research
- **ASK:** UI looks bad → wanted polish; plus research on making the voice agent more human.
- **DONE:** Typography wave; `VOICE_ARCHITECTURE_RESEARCH.md` (research-only).
- **DECIDED (phased path):** semantic turn-detector → per-stage flow layer → eval harness → (only
  then, gated) LoRA. Don't bother with Pipecat / exotic RAG / blind fine-tuning / swapping off Groq.

### 2026-06-06 → 2026-06-08 — FORTRESS security rebuild (EMERGENCY)
- **WHAT BROKE:** The frontend box `famit-voice-2 168.144.125.155` was COMPROMISED (outbound DDoS).
- **DONE:** Old box deleted; frontend rebuilt on born-hardened `famit-panel-2 143.110.247.249`
  (egress-locked DO firewall, Telegram alerts, Cloudflare-fronted). `agent.py` gained Groq(6)/Sarvam(5)
  key round-robin.
- **DECIDED:** Born-hardened topology going forward; reusable playbook `fortress/FORTRESS_DEPLOY.md`.

### 2026-06-08 → 2026-06-09 — Foundation services (F3/F4): Hatchet · Wallet · Firewall · Logto
- **ASK:** Build the durable-orchestration + money custody + auth spine for a production multi-tenant SaaS.
- **DONE:** Hatchet-lite on new `famit-hatchet` droplet; ACID Wallet ledger + Action Firewall (PIN
  step-up) + immutable audit on the voice box (NO-DOUBLE-SPEND proven, 24-concurrent); Logto
  self-hosted OIDC (Docker on hatchet box).
- **DECIDED:** Wallet/firewall flags default-OFF (live voice path untouched). caller.py integration
  deferred (legacy auth still works). **DO droplet limit now 3/3 FULL.**

### 2026-06-09 → 2026-06-11 — Foundation Control Layer (Super-Admin control plane)
- **ASK:** A super-admin plane to HIDE/LOCK/enable features per vendor, suspend tenants, act-as
  impersonation, immutable audit.
- **DONE:** Control Layer LIVE + ENFORCING (2026-06-11). `CONTROL_ENABLED=1`. **18/18 T1–T18**
  isolation probes PASS over real HTTP.
- **DECIDED / #1 finding:** the static legacy password `FamitCall2026` = a permanent un-revocable
  admin bearer → MUST be excluded from `/admin/*` (→ 403). Fail-closed everywhere (HIDDEN=404,
  LOCKED=402, unknown=DENY).

### 2026-06-11 — Sales proposal + positioning/pricing research
- **ASK:** Build a customer-facing proposal to SELL Famit/Axcrio to a business owner.
- **DONE:** Web-researched proposal blueprint + positioning/pricing/ROI → interactive HTML proposal
  (Signal blue, anchor-hero-decoy 3-tier ₹9,999 / ₹24,999 / ₹75k+, interactive ROI calc, animated
  revenue-loop). Category = **"Revenue OS"** (owns the WHOLE loop Ad→Call→WhatsApp→Book→Sale→CAPI).
- **DECIDED:** Never fabricate testimonials/metrics — show only REAL artifacts (96 calls / 8 campaigns
  / ~₹68/mo meter). Moat = the Revenue-Truth Signal Loop.

### 2026-06-11 → 2026-06-13 — UI overhaul · AI Manager · Creative Studio · premium UI
- **ASK:** "My from-scratch UI looks bad" → reuse Core_2. Build the AI Manager (voice/WhatsApp command-
  brain) + Creative Studio (AI banner/image gen).
- **DONE:** Core_2-Capsy dashboard kit ported; AI Manager service scaffolding; Creative Studio (AI
  Asset Service, model-agnostic provider abstraction); premium-UI branch (`feat/premium-ui`, the main
  branch). Adopted Inter Display (dropped the broken 2-weight Gilroy).
- **DECIDED:** ALWAYS reuse Core_2, never build UI from scratch. Default Creative Studio to FREE image
  gen (Pollinations / Gemini-free) — never burn paid OpenRouter credits.

### 2026-06-13 — DID carrier spam-block (CRITICAL earner issue)
- **WHAT BROKE:** Outbound calls stopped ringing. Diagnosed: DID `+91…488` carrier-spam-blocked
  (486/480/603 immediate, no ring) since ~12:51 UTC — NOT a code regression.
- **DECIDED:** NO outbound test calls (a real ring is the founder's job; test calls deepen the flag).
  Rest the DID. Founder must clear/rotate via Vobiz.

### 2026-06-13 → 2026-06-14 — Voice-brain megaplan · RAG · Provider Framework · Video Studio · Telephony
- **ASK:** Make the voice agent a real adaptive human brain; ground it with RAG; make providers
  swappable; build a video studio; achieve telephony independence.
- **DONE (massive parallel read-only design + earner-safe builds):**
  - **Voice brain:** vendor-script→adaptive persona (W1), context cache (W2, 277× faster),
    multi-channel memory (W3/W4), multilingual adaptive mirror, Sarvam Bulbul v3 (fixes romanized-Hindi
    garbling), **P0-LEAK** cross-tenant memory/WA leak CLOSED.
  - **RAG:** FTS-only grounding LIVE (W0 kill-switch → W1 hardening → W2 120-chunk telecaller corpus →
    W3 KB-mgmt backend → W7 Knowledge UI). 6–12ms.
  - **Provider Framework:** universal config-driven provider registry (W1–W5), AAD AES-256-GCM creds,
    SSRF guard, PIN-reveal. LIVE (`PROVIDER_REGISTRY_ENABLED=1`).
  - **Video Studio:** real composite MP4 rendering (ffmpeg, $0-key floor); 2 real MP4s rendered;
    LIVE + USABLE at `panel.famit.in/creative/video`.
  - **Telephony:** `trunk_registry` designed + T1–T3 built (flag OFF dormant); 4 red-teams folded.
- **DECIDED:** caller.py SERIALIZED — only ONE of {RAG / Vault / Registry / Video / Telephony / Comm}
  edits caller.py at a time (claim `CALLER_EDIT_LOCK`). Framework-first, then Video on it; composite
  tier ships with ZERO paid key.

### 2026-06-14 (night) — Autonomous night build + the orchestration operating-system
- **ASK:** "Keep building autonomously through the night; don't lose context; treasure everything."
- **DONE:** Built the orchestration brain — `START_HERE.md`, `MAX_AUTONOMY_PROMPT.md` (Parts A–Q),
  `BUILD_TREE_PROTOCOL.md` (5-layer subagent tree), `ULTRACODE_UNIVERSE.md` (conductor of many
  workflows), `MASTER-INDEX.md`, the session-summaries archive. Performance overhaul (90% smaller
  payloads, virtualized, cached). Gold-mine sweep (27 net-new backlog items).
- **DECIDED:** Compaction-proof EVERYTHING — durable on-disk state, the forever-learning loop
  (`AGENT_LEARNINGS.md` + `PLAYBOOK.md`), never lose a line. Model routing per task complexity.

### 2026-06-14 — Scheduler retry bug (CRITICAL — the T0 hard gate)
- **WHAT BROKE:** `scheduler_loop` retry bug — exhausted (3/3) retries RE-FIRE → auto-dialed 6 numbers
  → deepened the carrier spam-flag → burned Vobiz balance. Queue PAUSED
  (`var/retry_queue.json.PAUSED_20260614-201754.bak`).
- **DECIDED:** **T0** = the scheduler retry-bug fix is the HARD GATE — must be the next caller.py wave
  before any campaign resume or telephony rotation.

### 2026-06-15 — Communication/Telegram build → HOLD for founder test
- **ASK:** Build the unified Communication tab (Telegram first); then HOLD and personally test it.
- **DONE:** Communication Wave 1 — Telegram LIVE end-to-end (real message landed message_id 4;
  `comm/poll_worker.py` two-way conversation; hot-lead alert + post-call summary wired; **6/6**
  security probes; FE tab built+committed). Founder chat_id `1862240811` persisted. 26/27 verify PASS.
- **DECIDED:** **STANDING HOLD** — do NOT launch any new wave until the founder personally tests
  Telegram and confirms. Telegram first (zero compliance gates); Email/SMS behind DLT/SPF.

### 2026-06-15 (later) — DID swap → outbound RESTORED · warm-transfer RESTORED · leads-mgmt LIVE
> Full detail: `memory/session-summaries/2026-06-15-did-swap-transfer-leads-restore.md`.
- **WHAT BROKE (founder's real test):** outbound still not ringing; human/warm transfer not connecting;
  no Telegram follow-up after an INBOUND call; leads screen had no delete/sort.
- **DONE:**
  - **Outbound RESTORED** — founder bought a NEW Vobiz DID; created new trunk **`ST_bpGqmc9TL9Ph`** +
    repointed `.env` `LIVEKIT_SIP_TRUNK_ID` (caller-ID lives in the LiveKit trunk `numbers`, not
    env/code; LiveKit v1.8 can't `UpdateSIPOutboundTrunk`). Founder-authorized ONE test call →
    **`inviteToRingingMs: 3463`** (rang 3.46s). agent.py UNCHANGED.
  - **Warm-transfer RESTORED** — code was correct & firing; the running `aim-voice-agent` still held
    the OLD trunk in memory → restarted `aim-voice-agent` to reload the new trunk-id. Transfer is
    **INBOUND-ONLY** (outbound `agent.py` has no transfer tool).
  - **Leads-mgmt LIVE** — `/leads` delete+sort, `/run` sort; BUILD_ID **`xF8YUvBmTwYj_yP4w7WY4`**;
    this deploy also made the Communication tab + Video Studio VISIBLE.
  - **Telegram ecosystem diagnosed** (`design/TELEGRAM-ECOSYSTEM-DIAGNOSIS.md`): the post-call hook is
    wired into the OUTBOUND finalize only → no inbound follow-up; #1 fix = seed `comm_sessions`
    post-call so the brain stops hallucinating.
- **⭐ KEY LEARNING:** an `.env` change reaches only the processes you restart — **caller restart ≠
  voice-agent reload.** Env-affecting changes must restart the SPECIFIC process (`aim-voice-agent`).
- **DECIDED:** a fresh DID is a clock-reset, NOT immunity (the block follows behaviour) → the real fix
  is a 140-series DID on a DLT-registered route (founder action).

### 2026-06-15 → 2026-06-18 — Voice bug fixes (branch-first) + callback-retry rebuild
> Branch `fix/callback-retry-scheduling`. Baseline snapshot commit `683b0e5`.
- **ASK 1 (voice, 06-15):** fix 4 bugs on a TEST branch before prod — (1) username spoken too
  loud/fast, (2) broken language auto-switching, (3) double greeting on turn-1, (4) hardcoded end
  filler ("namaste, namaste"). *"Don't hardcore anything, everything should be adaptive… test before
  deploying final."*
- **DONE:** diagnosed (`DIAGNOSIS_AND_SPEC.md`) + 4 env-gated, default-OFF fixes — FIX A
  `add_to_chat_ctx=False` on opener (BUG3), FIX B Groq `_llm_close` w/ goodbye fallback (BUG4), FIX C
  env-only `EL_STABILITY` ladder (BUG1), FIX D unify to ONE language detector / `LANG_MIRROR_V2` (BUG2).
  Commits `1b5600c`, `422d66c` (default `OPENER_ALREADY_SAID=0` so the deployed build is byte-identical
  until flagged), baseline `683b0e5`. RISK noted: FIX D may add TTS-reconnect churn → deploy last.
- **ASK 2 (callbacks, 06-16):** *"Callback every 2 hours non-stop — got 10–11 calls last night, even
  after pickup. Should retry MAX 2×, only if no-answer. If user says 'call me at evening', reschedule
  then. NO MORE retries after 2 attempts."*
- **DONE:** `DESIGN_SPEC.md` (explore+research) + **hotfix `6aa1f32`** — `RETRY_SCHEDULER_ENABLED`
  kill-switch (default OFF) around the dial point in `scheduler_loop` to STOP the runaway spam;
  retry_queue cleared; first-calls (`run_job`) unaffected. Full rebuild (≤2 retries · next-day cadence ·
  no-retry-on-pickup · busy-reschedule · dedup · frontend control) PENDING.
- **CONTEXT LIMIT:** weekly limit hit; reset 2026-06-18 ~08:30 Kolkata. Resume = continue the
  callback-retry rebuild + verify the voice fixes (do NOT re-run diagnosis — checkpoints exist).

---

## PART B — FOUNDER PREFERENCES / WORKING STYLE (consolidated, standing)

> These are the founder's repeated, explicit rules. Treat them as law in every session.

1. **Non-technical ("I am not a developer / I am a noob").** Never hand him a technical step (cloud
   console, terminal, git) without either doing it yourself via tools/API or producing a dead-simple,
   click-by-click HOWTO. Never make him type git.

2. **Full autonomy — act like a founder.** He gives rough, partial, sometimes-wrong sketches and
   forgets layers. INFER the true intent and **build the whole thing — the 99% he didn't name** (frontend
   + backend + DB + security + integration). Don't bounce small decisions back; you have the final call
   and may override a wrong instruction in service of the actual goal.

3. **Ask with the AskUserQuestion tool, NEVER as prose.** Multiple-choice + custom-answer + a short
   recommendation per option keeps the session ALIVE. Typing questions as numbered prose STOPS the
   session and burns ~30–40% of the limit on restart — his explicit #1 "never do this." Reserve
   questions for genuine forks; otherwise pick the safe default and ACT.

4. **Compaction-proof EVERYTHING / "treasure everything, never lose a line."** Durable on-disk state
   (MASTER-INDEX, ORCHESTRATOR, WORKFLOW_LEDGER, wave_runs, session-summaries). On resume: save the
   harness summary verbatim, read the ledgers, reconcile against the box. The forever-learning loop
   (`AGENT_LEARNINGS.md` + `PLAYBOOK.md`) means **no mistake is ever made twice.**

5. **Never break the EARNER.** The live voice agent (`agent.py` md5 `9150fabe…`) is production. NEVER
   edit/restart it without sign-off + a real ring before+after. Every new capability is ADDITIVE +
   ISOLATED + earner-regression-gated; inbound work lives in `aim_voice_agent.py`/`caller.py`. ONE
   box-mutating wave at a time.

6. **A green report ≠ a working product.** Only the founder's REAL call / WhatsApp / click is truth.
   Never declare "fixed/done" until he confirms on his real flow; state honestly what only his test can prove.

7. **Every backend capability ships with a FRONTEND control UI** (full CRUD + configure + test/preview,
   real-time). He's hit "you built the backend but I can't use it from my screen" too many times — pre-empt it.

8. **Reuse the Core_2 dashboard kit — never build UI from scratch** (his from-scratch UI "looks bad").
   Inter Display font, zero raw hex, use the frontend-design skill.

9. **Be FAST, don't waste the limit.** Token economy is first-class: narrow with search then read only
   what's needed; delegate heavy exploration to subagents that return conclusions (file:line), not dumps;
   never paste big files/logs back.

10. **Never burn PAID credits.** Free providers first (Pollinations / Gemini-free / ElevenLabs preview);
    1 paid test max. OpenRouter $ is REAL money; the internal Famit wallet is a test meter.

11. **Don't hardcode — everything adaptive, env-gated, default-OFF; test on a branch/box before the
    prod cutover.** (Voice fixes, callback fixes: all behind flags so the deployed build is byte-identical
    until flagged.)

12. **Delegate as the orchestrator.** Break work into scoped units; right model per difficulty (Haiku
    mechanical / Sonnet normal coding / Opus hard reasoning, red-team, earner surgery, design). Hold the
    plan; agents do the bulk and report back compressed. Sequential + scoped + verified beats parallel +
    buggy. Granular waves so a throttle/crash costs ≤1 unit.

13. **EXPLORE the real box/logs FIRST for root cause** — the prime suspect is often a red herring (it was
    the call-window, Vobiz ₹0.19 balance, Groq daily-quota, a carrier block, a missed restart, or a
    decoupled override flag — not a code regression). Prove it with evidence (SIP codes, balance API,
    journal, byte-diff).

14. **Born production-grade, billion-dollar, sellable.** Think multi-tenant isolation, security, scale,
    low-latency, cost — not a prototype. Proactively add the differentiated/sellable features he didn't name.

15. **Simplicity — don't over-engineer.** Repeated friction: *"I already told you not to make a
    complicated system," "this is so easy, you are just making it complex," "don't explore forever — make
    a decision and build."* Ship the simplest thing that actually works; reserve heavy machinery for when
    it's genuinely needed.

16. **Deliver REAL, not fake.** *"Don't make me a fool — deliver real working features, not fake"* (came
    up over fake/plain-text "generated" images and green reports on a broken live product). The voice agent
    must *"behave like a real salesperson with a human touch,"* not a robotic script.

17. **If blocked, deploy a new resource rather than stall** — a new droplet, API key, DID, etc. Don't loop;
    unblock. (He'd rather you provision than bounce the decision back.)

### THE EMOTIONAL / FRICTION ARC (so a new session reads the room)
The journey was mistake-heavy and the founder got justifiably frustrated at recurring breakage of the
LIVE earner — *"you broke the entire system," "why are you taking too much time? nothing is working,"*
and, after compactions, *"don't forget what you learned."* Almost every "broke" event traced to: editing
shared outbound infra for an inbound feature, test-calling the DID into a carrier flag, a missed process
restart, a decoupled override flag, or losing context to compaction. **This is exactly why** the standing
laws exist (earner-safe / additive / one-wave-at-a-time / box-is-truth / compaction-proof / green-report-
≠-working). Honor them and the friction disappears; violate one and you reproduce a past outage.

---

## PART C — POINTERS (for the fresh session)
- **State (what IS):** `MASTER-INDEX.md` (read-first) → `MASTER_DNA_PLAN.md` → `ORCHESTRATOR.md` →
  `WORKFLOW_LEDGER.md` → `NEXT-BIG-BUILDS.md`.
- **Story (what HAPPENED):** this file + `memory/session-summaries/*.md`.
- **Rules / mistakes:** `PLAYBOOK.md` + `AGENT_LEARNINGS.md` (read before any wave).
- **Current standing order:** `HOLD-STATE.md` (HOLD pending the founder's Telegram test) — but note
  the later 06-15→06-18 work moved on to DID/leads restore + voice bugs + the callback-retry rebuild
  (branch `fix/callback-retry-scheduling`), which is the live in-flight work to resume.
- **Gated founder actions:** `MASTER-INDEX.md §5` (Vobiz 140/DLT DID, BotFather token, Meta WhatsApp,
  ModelScope bind, DO droplet raise, Resend/MSG91 keys, etc.).
