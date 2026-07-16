# EARNER-LIVE-STATE — current live outbound earner (2026-06-19, POST-REVERT)

> READ-FIRST after any compaction. GROUND TRUTH verified directly on the box (golden snapshot
> 20260618-210445). Do NOT trust older notes that say the kernel is live — it was REVERTED.

## ✅ CURRENT LIVE STATE (the founder's PERFECT VOICE) — verified
- Voice box: `famit@168.144.153.145`, service `famit-agent` = **active**, worker "capsy" registered.
- `agent.py` md5 = **`5c055a31b2608d6381ab475af1e64761`** (the OLD-brain path).
- **`KERNEL_OUTBOUND=0`** (drop-in `kernel-outbound.conf`). The W1–W7 kernel is **OFF**.
- `prompt.py` md5 = **`17ad3e0d133721c4a673f258f6420df5`** (BRAIN-V2 Step 1 DEPLOYED 2026-06-19:
  de-hardcoded single greeting / natural Hinglish + banned-literary list / name-sparingly /
  cross-vertical auto-adapt / instant language-switch / short complete turns — voice byte-identical,
  agent.py+.env+KERNEL_OUTBOUND all UNCHANGED, worker registered, 0 restarts/errors). AWAITING founder
  test call. Golden/rollback prompt = `660f1ec6` (`prompt.py.PERFECTgolden.20260618-210445` +
  `prompt.py.BRAINv2bak.*`). Known-deferred to Step 1.5 (agent.py, voice-touching, gated):
  double-goodbye (`_confirm_then_hangup` 2nd say) + hard 90-token truncation + lang-detect race.
- `.env` **`EL_STABILITY=0.55`** (founder's setting). TTS/voice path untouched.
- **Founder test-confirmed (2026-06-19): this state = PERFECT VOICE.** Only the BRAIN behavior
  (old scripted: greeting/Hinglish/cross-vertical/memory) needs improving — see [[voice-is-perfect-brain-is-the-job]].
- GOLDEN backup of this exact state on box: `agent.py.PERFECTgolden.20260618-210445`,
  `prompt.py.PERFECTgolden.*`, `.env.PERFECTgolden.*`.

## ✅ A1 LANGUAGE FIX — FOUNDER-VALIDATED 2026-06-19 (voice perfect + language switch WORKS) — NEW BASELINE
- 3 files edited (`langdetect.py` + `agent.py` + `prompt.py`), BRAIN/LOGIC-ONLY, **voice byte-identical**
  (agent.py TTS region 540-640 unchanged, `EL_STABILITY=0.55`, `KERNEL_OUTBOUND=0`, worker "capsy" re-registered,
  0 errors). New PID 4155915.
- WHAT: replaced the HARD `role="system"` reply-language COMMAND (the reverted-bug pattern; `LANG_MIRROR_V2=1`
  was live) with a SOFT `role="user"` `[Language this turn: X]` hint; carry-prior on <4-word fragments (NEVER
  default English); Gurmukhi/Indic block (≥4 chars) → degrade-to-Hindi (TTS `hi`, never `gu`/`pa`); strong
  FINAL-OVERRIDE mirror rule appended at END of `build_system_prompt` (recency). Box check:
  `classify_text('<punjabi>')` → `('hindi',1.0)` (was `('hinglish',0.0)`).
- ROLLBACK (A1 only): restore `*.A1bak.20260619-022912` (langdetect/agent/prompt) + `sudo systemctl restart
  famit-agent`. ULTIMATE golden: the `*.PERFECTgolden.20260618-210445` set.
- ✅ DONE: founder confirmed all 5 language scenarios + voice perfect. NEW known-good baseline. Backups
  `*.A1bak.20260619-022912` + ultimate `*.PERFECTgolden.20260618-210445`. Next (full-autonomous): A2 (time
  greeting) → A3 (11Labs punctuation/fillers + normalize) → A4 (kernel-wire, KERNEL_OUTBOUND flip = founder-gated).

## ✅ A2 + A3a DEPLOYED 2026-06-19 (full-autonomous batch — voice byte-identical)
- **A2:** time-aware LLM greeting (real IST time injected into `_llm_opener` + prompt; never hardcoded). Backups `*.A2bak.20260619-084951`.
- **A3a:** ElevenLabs prompt rules (numbers-in-words/no-symbols, adaptive punctuation + non-hardcoded fillers, Devanagari-only). prompt.py only; backups `*.A3bak.20260619-085614`.
- **A3b (normalize `tts_node`) DEFERRED** — `normalize_text` failed 4 real-line quality checks (`3-5 din`→"teen May din", `45000`→digit-by-digit) → NOT wired (A3a gets the benefit at the source, zero live risk). Fix notes in `A2_A3_BRAIN_STATE.md`.
- Voice TTS block byte-identical across all deploys (live md5 `f20e1348`); `EL_STABILITY=0.55`; `LLM_CLOSE=1`. Live agent.py md5 `7791e50f`→`9db54337` (A1+A2+A4-wiring). Rollback chain: A4bak→A3bak→A2bak→A1bak→PERFECTgolden.
- **A4 KERNEL BRAIN — FLIPPED ON 2026-06-19, `KERNEL_OUTBOUND=1`+`W5_SPEECH=0` (genius brain LIVE; AWAITING FOUNDER TEST CALL; verified active, NRestarts=0, worker "capsy" PID 4183457, 0 errors, `EL_STABILITY=0.55` intact). REVERT to perfect-voice-no-kernel: drop-in `KERNEL_OUTBOUND=0` + restart, OR restore `agent.py.A4bak.20260619-092230`.**
  W1-W7 kernel wired into agent.py (4 seams via OFF-identity adapter); **W5 speech-planner FORCE-OFF** gate
  (`W5_SPEECH=0` — the voice-breaker disabled even when kernel ON; commit `f03b6f3`); voice block byte-identical
  (md5 `f20e1348` both); 45 identity tests pass; `.env` untouched. Box backups `agent.py.A4bak.20260619-092230`
  + `voice_kernel/*.A4bak.*`. **FLIP (founder test):** drop-in `KERNEL_OUTBOUND=1`+`W5_SPEECH=0` + restart
  famit-agent. **ROLLBACK:** `cp agent.py.A4bak.20260619-092230 agent.py` + restart. State: `KERNEL_OUTBOUND_STAGING_STATE.md`.

## 🔌 STREAM C — live-data backbone ACTIVATED 2026-06-19 (famit-caller only; earner untouched)
Flags ON via `famit-caller` drop-in (EVENTBUS/RECORDING_FINALIZE+R2←SPACES/REPORTING/LEAD_LIFECYCLE); `voice-ops-reporting.service` worker active; `/report` 503→200; W7 DDL applied. CALLBACK+RETRY HELD OFF (T0 fix + `enqueue_smart` splice CONFIRMED present). `caller.py af64ab4d` UNCHANGED (drop-in only). Empty until a real call proves it. State: `.wireops_work/DEPLOY_STATE.md`. Rollback: remove drop-in lines + restart famit-caller; stop/disable worker.

## 🧠 BRAIN RECON (from real call logs — NEXT improvements; A4 kernel + targeted prompt)
1. **First-call hallucination** ("पिछली बात हुई थी" on FRESH leads) — returning-lead recap fires for new leads → trust damage. FIX: gate recap on ACTUAL prior-call memory.
2. **Monologuing → mid-sentence cutoffs** (`GROQ_MAX_TOKENS=90` + packing 3-4 clauses) → one fact + one question per turn.
3. **Weak objection handling** (mirrors, no reframe/value-anchor; exits to callback while engaged) → A4 cross-vertical brain.
4. **Retail placeholder leak:** spoke literal "#XYZ" order number → bind real data or omit.
5. Repetition/scripted feel; opener commits hard-Hindi before caller's language is known.
(#1 Punjabi-drift in the recon was PRE-A1 logs — A1 fixed it; founder validated.)

## 🟢 VOICE START/END FIX (P1) — DEPLOYED 2026-06-19 (awaiting founder test; voice byte-identical; A4/kernel STAYS ON)
All 8 start/end bugs fixed BRAIN/LOGIC-ONLY (kernel brain ON, middle untouched): repeat-opener killed
(single-greeting directive + `OPENER_IN_CTX=1` + `OPENER_ALREADY_SAID=1`); never-mention-recording
(`record_consent` default False); good-morning/hello-sir greeting (namaste BANNED); named confirm
("क्या मेरी बात {name} से हो रही है?"); hello-collision (`OPENER_DELAY_S=0.8` + opener `allow_interruptions=False`);
single goodbye (closure on USER bye-turn + farewell guard); anti-shout (no "ठीक है!"); AGARO→Agaro (campaigns
`18a29b5cec`+`1fd3218528`). Files: `voice_kernel/brain_packs/{delivery,disclosure,provider}.py` +
`voice_kernel/integrations/outbound.py` + `agent.py` + drop-in (`OPENER_IN_CTX=1`/`OPENER_ALREADY_SAID=1`/`PREEMPTIVE_GEN`) +
box campaign JSONs. **Commit `25a9010`.** Voice-safe PROVEN: TTS/VoiceSettings byte-identical, `EL_STABILITY=0.55`,
`KERNEL_OUTBOUND=1`/`W5_SPEECH=0`, worker "capsy" registered, 0 errors. Backups `*.VSEbak.20260619-111356`.
State: `VOICE_START_END_FIX_STATE.md`. PENDING: founder test. Per-fix env knobs allow toggling ONE fix without redeploy.

## 🔌 P2 — REAL LIVE DATA FIXED 2026-06-19 (caller.py only; earner untouched)
ROOT CAUSE = split-brain read-model: the reporting worker filled a store in ITS process; `caller.py`'s
`/report` route read a SEPARATE empty in-process `_REPSTORE` (code comment literally said "dashboard sees
zeros"). FIX: `_w14_hydrate(tenant)` replays the Redis stream into `_REPSTORE` on each `/report*` query
(XRANGE, no consumer-group → no worker interference, fail-safe). + `/stats` date filter + `/leads`
`from/to/campaign_id/status` filters + UTC-labelled call timestamps. VERIFIED LIVE: `/report?preset=today` =
calls:5/connected:4/talk:340s (was 0); `/stats?from` + `/leads?status=hot` work; `/contacts` top = founder's
number, correct time. `caller.py af64ab4d`→`99c9e95a`; backup `caller.py.P2bak.20260619-113223`; agent.py
UNCHANGED, famit-agent active. CAVEAT: live-forward only (~5 calls since EVENTBUS on, not the 363 backfill).
TODO(UI): dashboard `getStats()` should forward the GlobalFilters range (backend now accepts it).

## 🟢 VP3 VOICE POLISH — DEPLOYED 2026-06-19 (commit `8e94347`; voice byte-identical; awaiting founder test)
Greeting = ENGLISH "good morning/afternoon/evening + hello sir" (banned सुप्रभात/शुभ रात्रि/नमस्ते; IST bucket was
CORRECT — the "good night" was the LLM speaking the Hindi label literally, fixed by English labels); first-name
"Kunal ji" (not full name); "अलविदा" REMOVED (deterministic `_strip_alvida`); English brand names in Latin.
Files: `voice_kernel/brain_packs/delivery.py` (+ closing_directive + english_names_directive) + `agent.py`
(added `import re`, `_fix_opener_greeting`, `_strip_alvida`, English `_ist_time_of_day` labels). Crash-loop hit
on first deploy (missing `import re`) → auto-rolled-back → fixed (+module-import smoke) → clean. Voice-safe PROVEN
(TTS md5 `9d7572ff` unchanged, EL_STABILITY=0.55, KERNEL_OUTBOUND=1/W5_SPEECH=0, worker registered, 0 errors).
Backups `*.VP3bak.20260619-070109`. Live agent.py now includes A1+A2+A4-wiring+VP3.

## ❌ What BROKE the voice (now OFF, do not re-deploy as-is)
- The **W-VOICE-HEART kernel build**: `agent.py` `1567f79e` + `KERNEL_OUTBOUND=1` + `.env` 0.45/1.08.
- Founder's real call on it = **too fast, half-sentences, no pauses** (broken). Cause = the bundled
  flip changed the VOICE (.env prosody 0.45/1.08 + kernel filler-injection) AND the brain AND blew
  the prompt to ~2800 tok (TTFT/truncation) ALL AT ONCE. Offline gates were green; the real call failed.
- Reverted via `agent.py.HEARTbak.1781812510` + `.env.HEARTbak` + `kernel-outbound.conf.HEARTbak`.

## The W1–W7 PIPELINE (all built; the VALUE we add INCREMENTALLY, voice never touched)
- W1 kernel core (context packet/FSM/adapter), W2 brain packs (cross-vertical behavior),
  W3 campaign card (full context), W4 RAG runtime (corpus EMPTY — never seeded),
  W5 speech planner/router (prosody/fillers = the voice-risky part — AVOID), W7 lead memory
  (PG schema NOT run + injection patch omitted = not wired). Code in `voice_kernel/`.
- LESSON: do NOT flip the whole kernel. Add pieces ONE AT A TIME onto the perfect-voice path,
  each WITHOUT changing .env/TTS/fillers, each founder-tested, each reversible.

## STEP-BY-STEP integration order (lowest risk first; voice byte-identical each step)
1. **Brain behavior on the perfect-voice path** (prompt.py only, kernel OFF): single greeting,
   natural Hinglish, name sparingly, cross-vertical auto-adapt, auto language-switch, short
   complete turns. RUNNING: workflow `wf_3de22749-576`. Founder tests one call. ← current step.
2. **Lead memory** (W7): run `ddl_lead_memory.sql` + wire continuity injection (small, flag-gated).
3. **RAG** (W4): seed corpus + wire retrieve-when-needed (famit-caller / aim-voice only).
4. (Skip W5 prosody/fillers — that's what broke the voice.)

## ARMED ROLLBACK to PERFECT (always)
`ssh -i ~/.ssh/do-blr-test/id_ed25519 famit@168.144.153.145 'cp /opt/famit-agent/agent.py.PERFECTgolden.20260618-210445 /opt/famit-agent/agent.py && cp /opt/famit-agent/prompt.py.PERFECTgolden.20260618-210445 /opt/famit-agent/prompt.py && cp /opt/famit-agent/.env.PERFECTgolden.20260618-210445 /opt/famit-agent/.env && sudo systemctl restart famit-agent'`

## Sibling state
- Panel box `143.110.247.249` crashed (npm build OOM filled disk) → **RESTORED from DO daily backup
  `233367954` (2026-06-18 12:06 pre-crash)** via DO API `restore` action. Same IP, hardening intact,
  full product live. **Panel CRM/dashboard fixes DEPLOYED 2026-06-19** (commit `960035b`, BUILD_ID
  `xfSbVtQ3BBWoNYVV4kfGw`, public 200): dormant-removed, timestamp TZ fix, 10s auto-refresh, hot/warm/cold/
  dead filters, sort/delete, lazy recordings, 8 KPI cards. **+ FULL IA OVERHAUL deployed (commit `9f6a379`,
  BUILD_ID `LcX_6UESoY4uHwPqjey7l`, backup `.next.UIbak.20260619-060409`): sidebar de-clutter (AI-Manager single
  link, Creative Studio own section, Money/Super-Admin one entry, Report→Work, Intelligence removed, KB→Build,
  Call-Logs+Callbacks+DND merged, "Run Campaign", Ad-Tools hideable, transparent tabs); premium dashboard
  (bar/line/pie + Top Campaigns); CRM temperature column + filter restructure + dustbin; call-logs recording
  column + karaoke transcript; campaign retention step.** Prior backup `.next.A1bak.20260619-031324`.
  ⚠ LEARNING: the panel box CANNOT `npm run build` on-box (kernel OOM-kills the webpack worker even with 4GB
  swap — Next 15 mmaps ~50GB virtual). WORKING deploy = **ship the pre-built local `.next`** — it runs on
  Linux because `next.config.ts` has `images:{unoptimized:true}` → `sharp` never runs at runtime → the
  `.next` is pure JS/JSON, platform-independent. (Red-team's "Windows-.next-won't-run" concern = mitigated by unoptimized images.)
- Frontend full product restored (pre-W15). Merged build (nav+dashboard+filters) built, deploy pending box recovery.
- W-WIRE-OPS: caller.py live-data backbone wired + deployed dormant (flags OFF), caller.py only.
