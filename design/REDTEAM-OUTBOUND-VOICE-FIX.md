# RED-TEAM — Outbound voice human-fix plan (brain-only kernel cutover)

Date 2026-06-19. READ-ONLY adversarial review. No box mutation. Verdict: **DO NOT FLIP
`KERNEL_OUTBOUND=1` as the founder's voice fix — it will RE-INTRODUCE the double-greet
and is a voice-regression risk. The double-greet + hardcoded-ending fixes the founder
asked for are ALREADY 90% present in the LOCAL `6c577b9b` agent.py via env flags; the
kernel cutover is a DIFFERENT, larger change that does NOT close these specific bugs and
adds new regression surface.**

## GROUND TRUTH (verified in code, not assumed)
- LOCAL `droplet_work/agent.py` md5 = `6c577b9b` (NOT the `98655dbf` golden the patch doc
  assumes; NOT what's necessarily on the box). prompt.py = `5940c0b1`.
- The opener is HARDCODED-mechanism (not text): `_llm_opener(...)` (agent.py:214) →
  `session.say(opener, add_to_chat_ctx=OPENER_IN_CTX)` (agent.py:912). Text is LLM-authored
  but it is ALWAYS spoken by the worker, every call. That is fine and is NOT the double-greet.
- DOUBLE-GREET is prevented ONLY by `OPENER_ALREADY_SAID` (default "1", agent.py:475-481):
  it appends a "तुम पहले ही OPEN कर चुके हो… दोबारा greeting मत करो" block to `base_instructions`.
  Paired with `OPENER_IN_CTX=0` (agent.py:911) so the opener isn't echoed into chat ctx.
- The ending is `_confirm_then_hangup` → `_goodbye_line` (HARDCODED, agent.py:359) by default,
  OR `_llm_close` (agent.py:370) when `LLM_CLOSE=1`. Default today = hardcoded goodbye.
- Prosody is ALREADY the founder's "constant" fix in the local copy (agent.py:587-608):
  stability **0.65** (NOT 0.45), speed **1.0**, style **0.0**, speaker_boost **False**.
  These are CONSTANT per-call (set once at AgentSession build, never per-turn, never per-name).

## THE KILL-SHOT FINDING (why the kernel cutover regresses the double-greet)
The brain-only ON path (`assemble_outbound_instructions`, outbound.py:271) **REPLACES the
entire `base_instructions` string** with `ik.kernel.assemble_prefix(ctx)`. That throws away
the `OPENER_ALREADY_SAID` block — the ONLY thing suppressing the re-greet.

The kernel prefix it substitutes in:
- Has NO "opener already said / do not re-greet / do not repeat naam" directive. Grep of
  `voice_kernel/` for `opener_said` / `already_said` / `दोबारा` / "re-greet" = ZERO hits in
  prod code. packet.py:12 only NAMES "opener-said" as a concern in a docstring — no field, no
  render. `render_call_suffix` (packet.py:418) emits LEAD NAME / lifecycle / last-call — never
  an opener-said line.
- ACTIVELY carries `OPENING: Full greet->confirm->intro->reason->permission skeleton`
  (brain_packs/provider.py:140 + packs_data.py:44). So while the worker STILL `session.say()`s
  the spoken opener, the kernel prompt TELLS the model to greet+confirm+intro on turn 1 →
  **the exact live-proven double "नमस्ते {name}" regression returns.**
- The patch doc (`W-INT-OUTBOUND-PATCH-BRAINONLY.md` §2, line 121) openly states the
  `OPENER_ALREADY_SAID` env hack is "NOT reintroduced ON" and that single-greeting "now lives
  in the PROMPT." THAT PROMPT DIRECTIVE DOES NOT EXIST IN THE KERNEL. This is the plan's #1
  false assumption.

## RED-TEAM ANSWERS to the founder's 8 questions
1. Will it regress the voice (anonymous/different voice)? — **LOW on the OFF path** (D/E omitted →
   `elevenlabs.TTS` voice_id/stability untouched). **But** the kernel `choose_tts` router
   (outbound.py:414) CAN route lean/standard plans → Sarvam; brain-only omits D so it's inert NOW,
   but the founder must NEVER let D ship without a ring test — Sarvam = different voice = the exact
   3x-burn regression. VERDICT: voice itself safe ONLY while D/E/F/G stay omitted AND flag default OFF.
2. Is prosody truly CONSTANT (no per-turn / per-name variability)? — **YES in the LOCAL code**
   (stability 0.65 / speed 1.0 / style 0 / boost off, set once). The kernel does NOT touch
   VoiceSettings on the brain-only path. The founder's "guess ~0.50" is WRONG — 0.45 was the
   over-expressive setting that CAUSED the swing; 0.65 is the correct constant already in place.
   DO NOT lower it to 0.50. RISK: nobody per-turn calls `update_options` with style/stability —
   verified only `language=` is updated per turn (agent.py:696). Name is NOT emphasized by any
   TTS knob; loudness on the name is a TEXT/SSML artifact, not a setting — fixed by prompt, see §below.
3. EXACTLY ONE greeting (no double)? — **NO under the kernel ON path** (re-introduces double, see
   kill-shot). **YES under the current local OFF path** (`OPENER_ALREADY_SAID=1` + `OPENER_IN_CTX=0`).
4. Ending LLM-generated (not hardcoded)? — **NO by default** (LLM_CLOSE=0 → `_goodbye_line` hardcoded).
   Founder explicitly wants LLM-generated. FIX = set `LLM_CLOSE=1` (the code path exists, agent.py:721-722,
   with `_goodbye_line` as crash-safe fallback). This is independent of the kernel — a one-env-flag win.
5. Name used sparingly + normal volume? — **PARTIALLY.** prompt.py:220 already says 'जी" बार-बार मत
   दोहराओ'. But there is NO explicit "use the name at most once or twice in the WHOLE call" rule, and
   no "say the name at NORMAL volume, no emphasis" rule. The loud/fast-on-name is a prosody-from-text
   effect (the model writes the name with emphasis/exclamation; flash_v2_5 renders it louder). FIX =
   a prompt rule, NOT a TTS knob. The kernel does NOT add this rule either → cutover does not fix it.
6. Natural Hinglish not "Mahatvapurn"/too-formal? — **PROMPT-level, NOT fixed by the cutover.** Need an
   explicit "बोलचाल की Hinglish, English words जहाँ natural; 'महत्वपूर्ण'/'आवश्यक' जैसे formal/shuddh शब्द
   मत बोलो" rule. The GOOD inbound feel came from the inbound prompt — port that wording, don't assume
   the kernel carries it (it carries `language_directive()` generically, provider.py:142 — verify its text).
7. Does the kernel drive the greeting PATTERN (good-morning→greetings from Co→Am I speaking with___?
   →WAIT→reason+permission) on outbound? — **The PATTERN already exists in the WORKER opener**
   (`_llm_opener` sysmsg, agent.py:246-258: naam-greet → naam+company disclosure → "हमने आपको {product}
   के बारे में call किया" → "क्या अभी दो minute बात हो सकती है?"). The "WAIT after Am-I-speaking-with"
   pattern is in prompt.py:337 (`naam confirm… caller के हाँ कहने का WAIT करो`). The kernel's
   `OPENING:` directive is more generic; it does NOT improve on this and CONFLICTS with the
   already-said worker opener (double-greet). VERDICT: the worker already drives the pattern; the
   kernel does not add value here and breaks single-greet.
8. Auto language detect working? — **YES, STT-driven** (Sarvam auto-detect → per-turn mirror,
   agent.py:688-702; `LANG_MIRROR_V2` unifies LLM-note + TTS code). `safe_tts_language_code` clamps
   unspeakable langs to 'hi' (NEVER send 'gu' → TTS death, agent.py:682-688 — live-verified). This is a
   SOLVED, hardened path. The kernel `on_turn` lang resolver (outbound.py:327) is a SEPARATE mechanism
   (Patch E) that is OMITTED on brain-only → no change → fine. Do NOT enable E (double-detector desync risk,
   same class as the V1/V2 bug noted at agent.py:763-766).
9. Cross-vertical from brief (sales/support/collections auto, not hardcoded mode)? — This is the ONE thing
   the kernel genuinely adds (brain_packs L1 use-case + L2 industry from the brief). BUT it's gated behind
   the SAME ON flip that regresses the double-greet. Cannot get cross-vertical without the regression unless
   the kernel prompt is FIRST fixed to suppress re-greet. So cross-vertical is BLOCKED on the §FIX below.

## MUST-PASS CHECKS (gate ANY box change)
- [ ] Confirm the ACTUAL box md5 of agent.py BEFORE anything (local is 6c577b9b; doc assumes 98655dbf —
      drift is real and unverified). Re-locate every anchor by surrounding code, never line number.
- [ ] OFF-identity ring: with the flag unset, a REAL outbound call is byte-identical (founder hears no change).
- [ ] Single-greeting ring: exactly ONE "नमस्ते {name}" in the whole call (the bug that burned him 3x).
- [ ] Name said ≤1-2x total, at normal volume, no exclamation/emphasis on the name token.
- [ ] Ending is LLM-generated and context-aware (not the canned _goodbye_line), with a no-dead-air fallback.
- [ ] Hinglish is colloquial — zero "महत्वपूर्ण/आवश्यक"-class formal words in the transcript.
- [ ] Prosody constant: stability stays 0.65 (NOT 0.50/0.45), speed 1.0, style 0, boost off; verify NO per-turn
      VoiceSettings mutation (only `language=` may change per turn).
- [ ] Voice unchanged: voice_id `QTKSa2Iyv0yoxvXY2V8a`, ElevenLabs, NOT Sarvam. D/E/F/G stay OMITTED.
- [ ] Instant revert armed: env flag back / restore backup → old brain + perfect voice, before each step.

## RECOMMENDED PATH (lowest-risk, closes the founder's actual 6 bugs WITHOUT the kernel regression)
The founder's 6 complaints are PROMPT + ENV fixes on the existing `6c577b9b` worker — NOT a kernel cutover:
- **A. Keep `KERNEL_OUTBOUND=0`** (do not flip — it regresses double-greet; cross-vertical is the only loss,
  defer it to a SEPARATE wave that FIRST adds an opener-already-said + name-sparingly directive to the kernel
  packet so the ON prompt matches the worker's already-said opener).
- **B. `OPENER_ALREADY_SAID=1` + `OPENER_IN_CTX=0`** (already the local defaults) — single greeting. VERIFY on box.
- **C. `LLM_CLOSE=1`** — LLM-generated ending (code exists, _goodbye_line fallback). One env flag.
- **D. Prompt edits (prompt.py + _llm_opener/_llm_close sysmsg), additive, env-revertible via a prompt backup):**
  (i) explicit "naam पूरी call में ज़्यादा-से-ज़्यादा एक-दो बार, normal आवाज़ में, बिना ज़ोर/exclamation";
  (ii) explicit "बोलचाल की Hinglish; 'महत्वपूर्ण/आवश्यक/अत्यंत' जैसे formal/shuddh शब्द मत बोलो — रोज़मर्रा के
  English words natural रखो" (port the inbound wording the founder LOVED);
  (iii) reinforce single-greet pattern wording already present.
- **E. Prosody: LEAVE 0.65/1.0/0/off. Do NOT set 0.50.** If founder still hears swing, the lever is the PROMPT
  (over-punctuated/exclamatory text), not stability.
- **F. One box-mutating change at a time, each with a real outbound ring + immediate revert.** prompt.py first
  (revertible by file backup), then env flags. NEVER stack.

## TOP RISKS (ranked)
1. **Flipping KERNEL_OUTBOUND re-introduces the double-greet** (kernel prompt has NO opener-already-said + emits
   an OPENING greet directive while the worker still says() the opener). HIGHEST — it is the exact 3x-burn bug.
2. **Box drift** — acting on the doc's 98655dbf anchors when the box may be 6c577b9b/other → wrong-line patch → broken earner.
3. **Sarvam via choose_tts (Patch D)** — if ever shipped, anonymous/different voice = the voice-identity regression.
4. **Per-turn kernel hook (Patch E)** — double-detector desync with the existing V2 lang mirror (same class as the
   already-noted V1/V2 double-feed bug). Keep OMITTED.
5. **Name loudness is mis-attributed to a TTS knob** — it's a text/prosody-from-punctuation effect; "fix" by lowering
   stability would WORSEN consistency. Fix in prompt.
6. **"Mahatvapurn"/formal Hindi is NOT fixed by the cutover** — it's a prompt-wording gap; the kernel won't close it.
7. **Hardcoded ending stays hardcoded unless LLM_CLOSE=1** — the cutover (brain-only) does NOT touch the closer
   (doc §3: closure left verbatim). So the founder's "ending must be LLM-generated" is NOT delivered by the cutover at all.
