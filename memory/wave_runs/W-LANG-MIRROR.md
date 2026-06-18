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
