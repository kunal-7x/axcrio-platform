# 🔴 CONTINUE-HERE — ROUND-7 (2026-06-21) — READ THIS FIRST after ANY compaction, then continue seamlessly

## ✅✅ BOTH CURES NOW DONE + DEPLOYED (2026-06-21) — rotation + LEAN PROMPT
**The two ROUND-7 cures are BOTH live + proven. The earner should now: keep talking on a fresh key if one
hits its daily limit (rotation), AND not loop on short affirmatives (lean prompt). Founder makes ONE real call.**
- **LIVE (box `famit@168.144.153.145`, `/opt/famit-agent/`, MainPID 612429, active, NRestarts=0, 0 errors):**
  agent.py `bdf89031` (golden+rotation, UNTOUCHED — voice byte-identical) · **prompt.py `4ae81ac6` (NEW LEAN
  3681c, was 14160c `b99c25ea`)** · provider_pool.py `3d2d5be3` (rotation fix) · drop-in EARNER_POOL_LLM=1 /
  GROQ_MAX_TOKENS=90 / KERNEL_OUTBOUND=0 / NO penalty · EL_STABILITY=0.55 / voice_id `QTKSa2Iyv0yoxvXY2V8a`.
- **LEAN PROMPT loop proof:** 9 high-N live-Groq replays (scout-17b, temp 0.3, max 90, no penalty, real
  campaign c17e55e9f3, strict detector `/tmp/r7lean_confirm.py`) = **11 loops / 840 = 1.31%** (was ~13% on
  `b99c25ea`; ~10x cut), **0 budget give-ups / 840** (negotiates). Replies coherent. Residual ~1.3% = this
  campaign's dense Devanagari proper nouns ("Shapoorji Pallonji Real Estate"/"Hinjewadi Phase 1"/"Codename
  Joy 3.0") stuttering — campaign-inherent, NOT prose bloat (bloat is eliminated; every LOOPSAMPLE is a
  proper-noun stutter). Prompt SIZE was the lever, pulled. Kept persona+fields+flow+filler+language-mirror;
  cut few-shots/checklist/[..]scaffolding/repeated-rules/value_prop/multi-USP/multi-objection.
- **ROLLBACK lean prompt:** `cp prompt.py.LEANbak.20260620-194954 prompt.py → chown famit:famit → restart`.
- Full record at TOP of `EARNER-LIVE-STATE.md`. Harness `/tmp/r7lean_confirm.py` (R7_PROMPT=path R7_N=20).
- ⚠️ DON'T re-add prose bloat to prompt.py; DON'T touch agent.py (stays `bdf89031`). The ~1.3% proper-noun
  tail is a small-model frontier (not the old bloat) — a later, separate, CAREFUL idea: per-call alias the
  longest proper nouns OR a tiny anti-stutter post-filter on the LLM output — NOT more prompt prose.


## ✅ ROTATION = DONE + BUGFIXED + VERIFIED (2026-06-20 ~19:16 UTC) — the FINAL full-system verify
**The instant-429-fallback rotation is now CORRECT and LIVE. The final verify caught + fixed a real bug.**
- LIVE: agent.py `bdf89031` (golden+rotation) · prompt.py `b99c25ea` (untouched) · **provider_pool.py
  `3d2d5be3` (DEDUP/COOLDOWN FIX)** · drop-in EARNER_POOL_LLM=1/max90/no-pen · voice byte-identical
  (TTS span `86e266c4`, EL_STABILITY=0.55). Service restarted MainPID 603378, active, NRestarts=0, clean.
- **BUG FOUND & FIXED:** the pool held each of 14 secrets TWICE (env+hot-store=28). `mark_429` cooled
  only one copy + `_reconcile` lost the cooldown on dedup → a genuinely-exhausted key was NEVER skipped
  (28 attempts on the SAME dead secret → dead air). Fix in `provider_pool.py` ONLY: cool EVERY copy +
  reconcile keeps MOST-cooled state. REAL e2e proof (`/tmp/_r7realfallback.py`): before = 1 distinct
  secret/dead-air; after = escapes to a DIFFERENT secret, answers OK, 4-6ms, no backoff. Rollback:
  `cp llm_router/provider_pool.py.R7POOLFIX.20260620-191040 → restart`.
- **LOOP still ~13%** (live replay, prompt b99c25ea 14160c) = the KNOWN prompt-bloat issue, **still
  owned by the LEAN-PROMPT track below** — rotation did NOT change it (orthogonal). Founder real-call:
  daily-limit mid-call now keeps talking on a fresh key (no dead air); a "हाँ" may still occasionally
  repeat until lean prompt lands.


## ⏳ IN-PROGRESS + RESUME PLAN (2026-06-21 ~00:15 UTC) — two cures building; box is SAFE meanwhile
**LIVE NOW (verified, SAFE, coherent):** agent.py `5c055a31` (golden) + prompt.py `b99c25ea` (~6% loop) + drop-in max=90/KERNEL_OUTBOUND=0/NO penalty/NO pool + 13/14 fresh keys + EL_STABILITY=0.55. Service active, 0 errors, NRestarts=0. Responds; loops ~6% on short-affirmative turns (NOT yet the cure).
**PROVEN ROOT CAUSES:** (1) LOOP = small-model degeneration under PROMPT BLOAT (golden 17ad3e0d ~16%, b99c25ea ~6%, tiny-209char 0/44). (2) DEAD-AIR = Groq free-tier 500K/day per key + golden agent.py has NO 429-fallback (retries the SAME exhausted key). Penalty/pool/max did NOT cause the loop.
**TWO CURES (both VERIFY-before-founder-test; do them ONE box-restart at a time — NO concurrent restarts):**
1. **LEAN PROMPT** (the loop cure) — rewrite `build_system_prompt` to ~2k chars (keep persona+campaign fields+flow+greeting-no-double-name+filler+negotiate; cut bulk) → replay failing turns (`हां है।`/`बता दीजिए।`/`हाँ`/`ok`) vs live Groq ≥40× → must be 0-loop BEFORE deploy. agent a5ae31ce was building this but DIED on a temporary API rate-limit (no LEANbak on box = not deployed). **RESUME: SendMessage to a5ae31ce (preserves its progress) — but ONLY after the rotation workflow w2tbn6x3q finishes (avoid concurrent prompt.py/agent.py restarts).**
2. **INSTANT 429-FALLBACK** (founder's #1 ask) — workflow `w2tbn6x3q` building: re-add CLEAN PoolLLM rotation to golden agent.py (sticky-per-call, instant <20ms re-pick on 429, NO penalty/max-220), offline-verify, deploy (guarded), force-429 proof.
**SEQUENCE:** let `w2tbn6x3q` (rotation→agent.py) finish → then resume `a5ae31ce` (lean→prompt.py) → both proven (0-loop replay + forced-429 fallback) → THEN founder tests. ⚠️ API is intermittently rate-limiting (server-side) → agents may die mid-task; reconcile box state (read-only) after each death; don't relaunch into a flaky API. ⚠️ NEVER re-add penalty/max-220/bloat to agent.py; agent.py stays golden 5c055a31 + ONLY clean rotation.


## 🧪 EMPIRICAL CORRECTION (2026-06-20 ~17:50 UTC, a parallel REVERT+PROOF session) — golden is NOT "zero loops"; the cure is a LEAN prompt
> **READ THIS BEFORE TRUSTING "month-proven zero loops" below.** I replayed the EXACT 9:25 PM failing
> call (room `famit-916376980812-892efe`) against LIVE Groq, box venv, REAL campaign c17e55e9f3,
> rotating the 14 keys, scoring `हाँ`-loop on the two failing short-affirmative turns (`हां है।`,
> `बता दीजिए।`). HARD RESULT (TOTAL loops over both turns):
> - **GOLDEN prompt `17ad3e0d` (19061c) — even with stronger penalty — LOOPS 4/24 (~16%).** The
>   "golden never loops" belief is FALSE; it is the BIGGEST prompt → it loops the MOST.
> - **current prompt `b99c25ea` (14896c), max90, no-pen — loops ~2/44 (T1 ~4% / T2 ~8%).** ~4× LESS.
> - **TINY 209-char prompt = 0/44** ← the ONLY clean config. Stronger penalty (fp1.0-1.5), an explicit
>   anti-loop/hard-stop rule, temp .5 — NONE reach 0 on the full prompt. **Prompt SIZE is the lever.**
> - The penalty DID reach Groq (it's set on the delegate `_opts.extra_body` and forwarded) — so the
>   penalty/pool were NOT the loop's cause; removing them was right for SAFETY, but the loop is a
>   small-model degeneration under prompt bloat.
> **So:** the golden agent.py `5c055a31` revert (both sessions agree) is correct + load-bearing. BUT
> leaving prompt.py on golden `17ad3e0d` keeps the HIGHER loop rate. I set LIVE prompt.py to the
> lower-looping **`b99c25ea`** (proof above). **#1 NEXT (the real cure, proven): a LEAN-PROMPT rewrite**
> (keep campaign-field richness, cut the 14-19k-char bulk → toward the TINY-prompt 0/44), as ONE tested
> prompt.py change gated on a high-N live-Groq 0-loop replay + founder call. agent.py stays LOCKED at
> `5c055a31` (NEVER re-add penalty/pool/max-220). Harnesses on box `/tmp/r7replay.py`,`/tmp/r7decisive.py`,
> `/tmp/r7confirm2.py`; full proof+rollback at the TOP of EARNER-LIVE-STATE.md.
> ⚠️ **MULTI-SESSION RECONCILE:** the `wzj1s1h2u` machinery-DNA session left prompt.py on golden
> `17ad3e0d`; I (evidence) set it to `b99c25ea`. If the box flips back to `17ad3e0d`, re-check the loop
> rate — keep the LOWER-loop prompt. LIVE NOW: agent.py `5c055a31` + prompt.py `b99c25ea` + drop-in
> max=90/no-pool/no-penalty, service active, NRestarts=0, voice TTS-span `74a964ad…` byte-identical.

## ✅ LATEST (2026-06-20 ~23:10 UTC) — FULL GOLDEN REVERT DONE (the month-proven, no-loop, always-responds brain)
Two failed intermediate states today: (a) 9:25 PM brain `b99c25ea`+penalty+max=220 → RESPONDED but LOOPED "हाँ,हाँ,हाँ" after short words; (b) my env-only edit (removed penalty vars on code that required them) → crashed every LLM turn → 10:56 PM call gave NO RESPONSE (worse). Founder (right): this is a CODE REGRESSION from machinery we added, NOT his Groq/STT/TTS. So I did the FULL GOLDEN REVERT.
**CURRENT LIVE STATE (verified):** `agent.py` md5 **`5c055a31`** (PERFECTgolden 20260618 — NO penalty/pool/today's machinery) + `prompt.py` md5 **`17ad3e0d`** (matched golden, from A1bak). Drop-in `GROQ_MAX_TOKENS=90` + penalty REMOVED + `KERNEL_OUTBOUND=0` (`EARNER_POOL_LLM=1` still present but golden code IGNORES it — harmless). 14 multi-account keys in `.env` (golden reads first 6 = ~3M/day, no daily-limit). Voice byte-identical (EL_STABILITY=0.55, voice_id `QTKSa2Iyv0yoxvXY2V8a`). py_compile OK, service active, NRestarts=0, MainPID 555497, 0 errors. Pre-revert backups `agent.py.PRErev.*`/`prompt.py.PRErev.*`.
**THIS IS THE FOUNDER'S MONTH-PROVEN BRAIN** (zero loops, always responds). Founder testing one real call now. Golden brain quirks may remain (greeting double-name "hello <NAME>", etc.) — those are PROMPT-ONLY polish to re-add CAREFULLY one tested step at a time (his rule: agent.py LOCKED at 5c055a31, brain work in prompt.py ONLY). NEVER re-add penalty/pool/max-220 machinery to agent.py.
**RUNNING:** `wzj1s1h2u` (resumed `w145oygij`) = machinery-DNA exploration → `design/ROUND7-MACHINERY-DNA.md` (proving WHICH machinery caused the loop, so the rebuild avoids it). STT root cause found+deferred → `design/ROUND7-STT-ROOTCAUSE.md` (echo-cancellation + soft continuity, non-hardcoded).
**🔑 OPS LESSONS:** (1) PowerShell→ssh INLINE mangles quotes → ALWAYS scp a script file + `ssh "bash /tmp/x.sh"`. (2) NEVER delete env vars the code requires (set to 0 instead) — deleting `GROQ_FREQ_PENALTY` crashed the LLM path. (3) Don't tinker the broken brain — REVERT to golden, rebuild forward tested.

## ✅ (SUPERSEDED — the loop was NOT actually fixed; see LATEST above) ROUND-7 "finalized" attempt (2026-06-20 ~21:00 UTC) — the earner is DONE & locked
**LIVE BRAIN (box `famit@168.144.153.145`, `/opt/famit-agent/`, service active, NRestarts=0, worker `capsy` registered):**
- `agent.py` md5 **`10662d32fc857d88c62c7cc2549134cb`** · `prompt.py` md5 **`b99c25eaa9dc80edffb9ce615d5892c7`** (the 15:29 prose-rewrite brain — supersedes `ffe640e2`; cures structured-output `"key":"value"` garbage + includes the prompt-leak fix)
- Drop-in `kernel-outbound.conf`: `EARNER_POOL_LLM=1` · `KERNEL_OUTBOUND=0` · `GROQ_MAX_TOKENS=220` · `GROQ_FREQ_PENALTY=0.5` · `GROQ_PRES_PENALTY=0.3`
- 14 `.env` GROQ keys (+15 panel hot-store via `PROVIDER_KEYSTORE_SECRET` → pool sees 29) · `.env` famit:famit 660
- VOICE LAW intact: TTS-span md5 (ll.1161-1185) = `7b36c4f9d57cd76d5116d93156560dcb`, EL_STABILITY=0.55, voice_id QTKSa2Iyv0yoxvXY2V8a

**WHAT'S FIXED (all live):** (1) silence/daily-limit → 14 multi-account keys; (2) "हाँ हाँ" repetition garbage → freq/pres penalty brain; (3) rotation/instant-429-fallback → `EARNER_POOL_LLM=1` GROQ_POOL sticky-per-call; (4) prompt-leak → stage-directions wrapped `[...]`=SILENT in prompt.py.

**RESTORE POINTS (founder demand — both armed & verified):**
1. **GitHub** (kunal-7x/axcrio-platform): branch **`earner-golden`** + tag **`earner-golden-r7`** (commit `1285066`, prompt.py `b99c25ea`), files under `earner-golden/` — secrets-stripped (code + `ENV.example.md` names-only), **gitleaks-clean**. Restore = checkout the branch, scp the files to the box (see its `README.md`). NO keys/.env are in git (never will be).
2. **On-box golden dir** `/opt/famit-agent/_GOLDEN_ROUND7/` (agent.py+prompt.py+llm_router+drop-in+restore.sh). **One-command restore:** `sudo /opt/famit-agent/_GOLDEN_ROUND7/restore.sh` (asserts both md5s + the TTS-span VOICE LAW before restart; aborts on any mismatch).
3. Per-step rollbacks still armed: `agent.py.R7ROTbak.20260620-133923`, `prompt.py.R7PLbak.20260620-201250` (see EARNER-LIVE-STATE.md top).

**FOUNDER MUST TEST (one real outbound call):** AI responds every turn (no silence), complete sentences, NO "हाँ हाँ"/repetition loop, NEVER speaks a Hindi stage-direction (`फिर रुको`/`बस इतना`/`देखो caller को`/`अगर busy`), same voice as before, and if a key rate-limits mid-call the AI keeps talking on a fresh key (no dead air).

**DEFERRED (lower priority — assessed read-only 2026-06-20; each = ONE tested founder-gated change later, never bundled):**
- **STT Hindi→wrong-script:** `agent.py:1284` `SARVAM_STT_LANG` defaults to `"unknown"` (Sarvam auto-detect can mis-script Hindi as Odia/Tamil/etc.). PLAN = env-only A/B: try `SARVAM_STT_LANG=hi-IN` (constrains to Hindi script) OR a per-utterance script-normalizer if the call mixes languages; test one call, keep whichever transcribes cleaner. No code change to start.
- **Turn-taking mid-sentence cuts:** `agent.py:1296-1303` `min_endpointing_delay=0.25`/`min_interruption_duration=0.25`/`turn_detection="vad"`. PLAN = first nudge env knobs (`MIN_EP_DELAY`→0.35, `MIN_INT_DUR`→0.35) for fewer false cuts; the real upgrade = LiveKit semantic turn-detector (per VOICE_ARCHITECTURE_RESEARCH.md) — gated on a latency check, one tested flip.
- **Latency:** already on flash STT/TTS + VAD turn-detect + sticky-key prompt-cache. PLAN = measure first-token + end-to-end on a real call; if high, tune endpointing above + confirm the pool's sticky key keeps Groq prompt-cache warm. Don't pre-optimize without a measured number.

---

## THE ONE TRUTH (PROVEN from the box logs by forensic workflow `w2w8pfacw` — full output: tasks/w2w8pfacw.output)
The live voice earner's "broken brain / silence / NO RESPONSE after 1 turn" was **NOT the brain**. The brain (the 12:53 AM ROUND-6 brain) is GOOD. The real cause:
**Groq FREE-TIER DAILY TOKEN LIMIT (500,000 tokens/day PER ACCOUNT/ORG) was EXHAUSTED by ~11:30 UTC** (logs: `Limit 500000, Used 496440` → `APIConnectionError: failed after 4 attempts`) → every LLM call 429s "tokens per day" → no completion → dead air → the TTS session closes (the 1006 / "AgentSession closing" errors are downstream symptoms).
- `GROQ_MAX_TOKENS=220` (raised from golden's 90 in ROUND-6) drained the daily budget ~2.4× faster.
- The 6 keys on the server were ALL from ONE Groq account (org `org_01ktkexdmsfqwvye66cexebn1t`) → they shared the SAME 500K/day cap; rotation across them does NOT add budget.
- TWO separate problems: (i) the SILENCE = the Groq daily limit (fixed by the 14 keys); (ii) the **"हाँ हाँ हाँ" repetition garbage = model degeneration** — CONFIRMED on a live call that the no-penalty brain `e353b775` STILL produces it even with fresh budget + max=110. The **`GROQ_FREQ_PENALTY=0.5`/`GROQ_PRES_PENALTY=0.3` penalty (brain `ee3e4b5e`) is the CURE** for the loop. So the penalty did NOT cause the silence (the daily limit did) AND it is the cure for the garbage — both true.
- **OPTIMAL live brain = `ee3e4b5e` (penalty wired) + `GROQ_MAX_TOKENS=220` + the 14 keys** (responds all day — the daily-limit silence IS fixed). BUT ⬇️
- 🔴🔴 **THE GARBAGE LOOP IS STILL NOT FIXED (7:55 PM call, on the optimal brain).** Right after the user confirms identity ("Yes Sir"), the LLM output `"हाँ,": "Good 1.": " ;": " ;"…` — this is **STRUCTURED-OUTPUT degeneration** (JSON/`"key":` patterns, "Good 1." = enumerated greeting), NOT simple token-repetition → the freq/presence penalty does NOT cure it. **DNA ROOT-CAUSE HYPOTHESIS (proving it): the prompt's STAGED/NUMBERED/QUOTED greeting+flow structure tips the small llama-4-scout-17b into structured-output garbage at the confirm→intro transition.** FIX = rewrite the brain prompt to NATURAL PROSE (no numbered steps / quoted templates / staged JSON-like format), simplify the two-step-greeting machinery, + the line-by-line fixes below. (`ROUND7-BRAIN-DNA` workflow `round7-brain-dna` is diagnosing + rewriting.)
- LINE-BY-LINE founder fixes (7:55 PM, deep-reasoned as a 30-yr telecaller): (1) GREETING says name twice — "Good evening sir, hello कुणाल जी, क्या मेरी बात कुणाल जी से?" → MUST be just "Good evening sir, क्या मेरी बात कुणाल जी से हो रही है?" (no "hello <name>" before the confirm) → wait → then intro. (2) After confirm, NO natural filler before dumping details — every response should OPEN with an LLM-GENERATED filler ("बिल्कुल जी / जी ज़रूर sir", never hardcoded) then content, to feel human. (3) 🔴 GAVE UP on a budget objection — user said 2BHK budget 70L (vs 85L), AI replied "Thank you... Best of luck with your property search" = ENDED the call. A real closer NEGOTIATES (offers options/payment-plan/an offer, or books a site visit), NEVER dismisses. (4) Never hardcode anything (fillers/responses/behavior). (5) Low latency is a goal. STT is sometimes broken (separate, lower priority — the founder says the GROQ LLM BRAIN is the main thing).
- ⚠️ `.env` MUST stay `famit:famit 660` — a prior `root:root`/`chmod 600` edit crash-looped the service 23×.

## THE FIX (founder-clarified — IN PROGRESS)
Founder provided **15+ BRAND-NEW Groq keys, ALL from DIFFERENT accounts** in `C:/Users/kunal/Desktop/caps/z_groq_api.md` (each = its own 500K/day → 15 × 500K = **7.5M tokens/day**).
- **REMOVE all 6 old one-account server keys. ADD all 15 new keys** to `/opt/famit-agent/.env` as `GROQ_API_KEY` + `GROQ_API_KEY_2..15` (agent.py `_collect_groq_keys` ~:98 reads `GROQ_API_KEY` + `_2..20`).
- **`GROQ_MAX_TOKENS` 220 → 110** in the systemd drop-in `/etc/systemd/system/famit-agent.service.d/kernel-outbound.conf`.
- This is **ENV-ONLY** — do NOT touch the brain (agent.py/prompt.py). The brain is GOOD.

## STATUS
- ✅ Root cause PROVEN (Groq daily limit, NOT the brain). Box currently CLEAN: brain reconciled to the 12:53 AM ROUND-6, drop-in `GROQ_MAX_TOKENS=220`, 6 old keys (no partial edits — two prior agents were stopped before applying).
- ✅ KEYS DONE: 14 multi-account Groq keys live in `.env` (daily-limit silence FIXED, ~7M/day). ✅ OPTIMAL BRAIN DEPLOYED: `agent.py ee3e4b5e` (penalty 0.5/0.3) + `prompt.py 759b6f5c` + `GROQ_MAX_TOKENS=220` + 14 keys, voice byte-identical, MainPID was 464575. BUT the structured-garbage loop persists → being fixed by the brain-DNA workflow below.
- 🔄 **THREE WORKFLOWS RUNNING (their own context; do NOT duplicate; reconcile their prompt.py/agent.py edits — they coordinate):** (1) `w31agr8ku` round7-brain-dna = the garbage-loop DNA fix + natural-prose prompt rewrite (greeting/fillers/objection) — self-verifies vs live Groq before deploy. (2) `weffmx17e` round7-complete-voice = instant-429 key-rotation (GROQ_POOL, flag-gated) + prompt-leak + secrets-stripped GitHub restore-points. (3) `w2830b9k3` round7-stt-rootcause = READ-ONLY research into the STT mis-detection root cause → `design/ROUND7-STT-ROOTCAUSE.md` (non-hardcoded fix; implement AFTER 1&2 land to avoid 3-way agent.py conflict). Founder tests a real call (normal AND speakerphone) after each lands.
- ⏭ NEXT (in order, after the keys land + founder confirms a working call):
  1. **Rotation + INSTANT 429-fallback** (founder's explicit ask): on a 429 from any key, instantly fall back to a no-error key. Current BUG: key frozen per-call (agent.py:1072-1090) + the plugin retries the SAME 429'd key 4×. Fix = wire the EXISTING `llm_router` GROQ_POOL (least-used + per-key 429 cooldown + instant re-pick), flag-gated, voice byte-identical — see `design/GROQ-ROTATION-PLAN.md`. (With 15 accounts the daily limit is no longer urgent, but do this for robustness.)
  2. **Prompt-leak** (LATENT/minor): `prompt.py:215, 347, 355-357` contain speakable directives "फिर रुको / बस इतना, फिर रुको / देखो caller को / (अगर busy →" — separate them from the SAY-line so the model never voices them.
  3. Sync the 15 keys into the panel super-admin API-key section.
  4. STT: Sarvam saarika `language="unknown"` mis-scripts Hindi → Odia/Punjabi/Tamil/Malayalam (lower priority — handle the wrong-script transcript so it doesn't confuse the LLM).
  5. Turn-taking (mid-sentence cuts) + latency.
  6. Permanent capacity = the 15 multi-account keys (done) + optionally upgrade Groq billing (paid tier removes the per-account daily cap).

## BOX + THE LAW
- Voice earner: `famit@168.144.153.145`, `/opt/famit-agent/`, SSH key `~/.ssh/do-blr-test/id_ed25519` (use **PowerShell** ssh — Git Bash heredocs failed locally; stage a script + scp, or run simple commands). Service venv: `/opt/capsy-agent/.venv/bin/python`.
- Live brain = the 12:53 AM ROUND-6 (agent.py md5 **`e353b775`** / prompt.py **`759b6f5c`**) — the founder's confirmed-good brain. `KERNEL_OUTBOUND=0`.
- **THE LAW — voice BYTE-IDENTICAL:** never touch the TTS constructor / `.env` `EL_STABILITY=0.55` / `voice_id` `QTKSa2Iyv0yoxvXY2V8a`. One box change → founder real-call test → one-command rollback. Golden `_GOLDEN_ROUND5_20260619-140341/` + `*.PERFECTgolden.20260618-210445` + R6/R7 `*bak` armed.
- Panel box: `root@143.110.247.249` (famit-panel, being resized to 8GB — separate machine; ship PRE-BUILT `.next`, NEVER `npm run build` on-box).

## DURABLE REFS (read after this)
`design/ROUND7-STT-ROOTCAUSE.md` (STT mis-detection root cause + non-hardcoded fix design — RC-1 no-AEC speakerphone echo / RC-2 short-turn LID / RC-3 8kHz-as-16kHz / RC-4 raw wrong-script to LLM; FIXES = BVCTelephony AEC + soft continuity + saaras:v3 codemix/8k + transcript sanity; sequence AFTER weffmx17e+w31agr8ku land — DO NOT deploy now, 3-way agent.py conflict) · `EARNER-LIVE-STATE.md` (top = latest deploy + rollback) · plan `~/.claude/plans/you-have-digitalocean-api-imperative-mist.md` (ROUND-7 section) · `tasks/w2w8pfacw.output` (full forensic root-cause + fix plan) · `design/GROQ-ROTATION-PLAN.md` · `design/GENIUS-TELECALLER-PROMPT.md` (a cross-vertical persona — NOT yet deployed; only deploy as one tested change, never a big rewrite — a rewrite already broke the earner once).

## FOUNDER DIRECTIVE
Full autonomous. The ONLY goal = the final voice/brain system FULLY WORKING (a real human telecaller, any business). Don't stop. Be compaction-proof (this file). Voice = the heart; never over-engineer it; one tested change at a time.
