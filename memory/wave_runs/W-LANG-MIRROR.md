# W-LANG-MIRROR — per-turn adaptive language mirror (inbound + outbound)

Founder verdict: inbound call was PERFECT, ONE fix: per-turn LANGUAGE ADAPTATION
not adapting. He speaks Hindi (agent replies Hindi, good) but switches to English
mid-call -> agent STAYS Hindi. REQUIRED: mirror the user's language EVERY turn —
Hindi->Hindi, English->English, switch-back->switch — adaptive, NEVER hardcoded.
He ALREADY solved this in LIVE OUTBOUND (droplet_work/langdetect.py +
agent.py:_MirrorAgent.on_user_turn_completed). Port that exact proven behavior.

EARNER LAW: live OUTBOUND agent.py md5=98655dbf — NEVER edited/imported/restarted.
Build in SHARED tracked voice_kernel/. Flag-OFF byte-identity must stay green.

## Phase: BUILD

### DONE — self-contained port + wired into BOTH integrations
- NEW module `voice_kernel/language/` (zero droplet imports, self-contained port of langdetect):
  - `detector.py` — classify_text (script-ratio + Hinglish/English lexicon), LanguageTracker
    (hysteresis; V2 inbound config conf_floor=0.30 min_streak=1), TTS-code map (gu->hi dead-air fix),
    reply_instruction strings (casual Hinglish Devanagari + English steer).
  - `mirror.py` — mirror_turn()/mirror_once() -> MirrorDecision{reply_language, tts_lang_code,
    changed, instruction}. Adaptive: active lang from the caller's per-call tracker, NO hardcoded default.
  - `__init__.py` — re-exports.
- WIRED into on_turn of BOTH `integrations/inbound.py` + `integrations/outbound.py`:
  per-call lazy LanguageTracker on the façade (`_lang_tracker`); each turn re-detects from
  user_text; feeds the LANGUAGE NAME into the kernel TurnContext -> kernel renders TURN-SCOPED
  `USER LANGUAGE: <lang> — mirror it.` + appends `MIRROR: <casual reply instruction>` to the L5
  suffix (cache-safe; stable prefix never rewritten); reply_lang = SPEAKABLE tts code (hi|en).
- TESTS: voice_kernel/language/tests/{test_detector,test_mirror}.py + integrations/tests/
  test_lang_mirror_integration.py.
- PROOF (real wired on_turn, KERNEL_INBOUND=1): Hindi->hi/hindi, English->en/english,
  switch-back->hi/hindi, Hinglish->hi/hinglish. droplet_work leaked: NONE.
- pytest voice_kernel/ = 357 passed (321 baseline + 36 new), 0 fail. OFF byte-identity + isolation green.
- W5 preserved: mirror only sets LANGUAGE; SpeechPlanner still renders casual + no-half-words.

## Phase: VERIFY + COMMIT + REDEPLOY-INBOUND (2026-06-18)

### VERIFY
- `python -m pytest voice_kernel/` = 357 passed / 0 fail (321 baseline + 36 new).
  Subset (off-identity + off-path + no-droplet-import + stable-prefix + lang/mirror) = 77 passed.
- gitleaks (staged + pre-commit hook) = 0 leaks.

### COMMIT
- sha `c08d2346fbe26dba8e86445dcd16404667f098df` on branch `fix/realtime-voice-kernel-v2`.
- "feat(kernel): per-turn adaptive language mirror (shared inbound+outbound, ported from proven LANG_MIRROR_V2)".
- Staged ONLY (no git add -A): voice_kernel/language/** + integrations/{inbound,outbound}.py
  + integrations/tests/test_lang_mirror_integration.py + memory/wave_runs/W-LANG-MIRROR.md.
  voice_kernel/__init__.py NOT touched (integrations use `from voice_kernel import language`).

### REDEPLOY -> INBOUND box famit-livekit (168.144.153.145)
- EARNER GATE BEFORE: agent.py md5=98655dbfc71d5c3da36bcfe3f848082c, famit-agent active,
  aim-voice-agent active, caller /health=200 (ports 8208+8209), KERNEL_INBOUND=1 (systemd drop-in).
- Backup: /opt/famit-agent/voice_kernel.WINTbak.20260618-192729 (+ .preswap.135821). rsync absent
  locally -> shipped via tar-over-ssh + atomic dir swap (excludes __pycache__).
- Synthetic adaptive check (box interpreter): Hindi->tts hi, English->english/en (switched), back->hindi/hi. OK.
- Restarted ONLY aim-voice-agent. journalctl clean: "registered worker" agent_name=manager
  ws://127.0.0.1:7880, NRestarts=0, no traceback. (The one "Failed result=timeout" line was the OLD
  instance's slow stop during restart; new instance Started + registered immediately after.)
- EARNER GATE AFTER: agent.py md5 STILL 98655dbf..., famit-agent active (uptime unchanged since
  2026-06-15 = NOT restarted, no ring), aim-voice-agent active, caller /health=200 both ports.
- ROLLBACK if needed: restore /opt/famit-agent/voice_kernel.WINTbak.20260618-192729 (or set
  KERNEL_INBOUND=0 in the systemd drop-in) + restart aim-voice-agent.

### FOUNDER RE-TEST
- Call +918071583488. Speak HINDI first (agent replies Hindi), then SWITCH to ENGLISH mid-call
  -> agent must follow to English on the next turn, then switch BACK to Hindi -> agent follows back.

## Phase: REVERTED (2026-06-18) — lang-mirror caused English-only regression

- FOUNDER REAL-CALL VERDICT: the per-turn LanguageTracker forcing made the LIVE language WORSE
  (English-only). The forced LANGUAGE directive overrode the perfect-call brain's natural mirroring.
- ACTION: `git revert --no-edit c08d2346` on branch fix/realtime-voice-kernel-v2 (NO conflicts —
  lang-mirror only touched voice_kernel/language/ + integrations/{inbound,outbound}.py + a test,
  disjoint from concurrent W9 voice_ops/recording).
- RESULT: revert commit `1aa9ccb`. voice_kernel/language/ deleted + stale __pycache__ purged
  (module now unimportable). integrations/{inbound,outbound}.py byte-identical to pre-lang-mirror
  cdabe84 (empty diff) — NO forced language directive. `python -m pytest voice_kernel/` = 321 passed
  / 0 fail (the 36 lang-mirror tests removed by the revert; off-identity + integration tests green).
- KERNEL STATE: back to the founder's PERFECT-call behavior. No forced per-turn language.
- NEXT: proper STT-auto-detect fix to follow (let STT detect the spoken language; do NOT force it).
