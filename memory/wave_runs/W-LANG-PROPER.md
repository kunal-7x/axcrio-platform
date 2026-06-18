# W-LANG-PROPER — adaptive per-turn language seam (shared kernel)

Branch: `fix/realtime-voice-kernel-v2`
Earner law: do NOT touch/restart famit-agent (outbound earner, md5 480d23c3). This wave
touches ONLY shared `voice_kernel/` (language + on_turn) + (later) re-deploy INBOUND
(aim-voice-agent restart only).

## GOAL (founder's correct spec — the WRONG heavy LanguageTracker forcing was reverted in aea9a92)
STT auto-detects the spoken language per utterance -> that detected language flows to the
LLM -> the LLM responds in the user's current language -> TTS speaks in that language.
ADAPTIVE both ways, NEVER hardcoded, NEVER force English. If detection is uncertain/short,
KEEP the prior turn's language (NO English-only failure mode). Preserve W5 casual-Hinglish
+ no-half-words. Minimal — NO heavy LanguageTracker forcing.

## RESULT (DONE — 340 passed)
- NEW `voice_kernel/language.py`: pure droplet-free classifier + `normalize_lang` +
  `tts_lang_code` + `TurnLanguageResolver` (seed Hinglish not English; STT-authoritative;
  text-classify fallback; UNCERTAIN -> keep prior; never force English; never raises).
- WIRED `voice_kernel/integrations/{inbound,outbound}.py` `on_turn`: per-call lazy
  `_lang_resolver`, resolved label feeds TurnContext.detected_lang (soft `USER LANGUAGE:
  <lang> — mirror it.` directive) + returns `{reply_lang, tts_lang, lang_switched,
  rag_suffix, speech_plan}`.
- TESTS: `voice_kernel/tests/test_language.py` (NEW) + updated both integration suites
  (OFF inert + ON shape + adaptive both-ways + keep-prior-on-uncertain + never-default-english).
- `python -m pytest voice_kernel/` = 340 passed. Zero droplet/agent/livekit imports at load.
- DOC: `design/W-LANG-PROPER-SEAM.md` (incl. Sarvam STT auto-detect box config check +
  outbound-redeploy gate). STT CONFIG: verify `SARVAM_STT_LANG` is unset/`unknown` on the
  box (if locked to hi-IN -> remove it; that lock is the English-only root cause).
- EARNER: outbound agent.py UNTOUCHED (only shared tracked voice_kernel/, flag-gated OFF).
  INBOUND redeploy = restart aim-voice-agent only + the box config check.

## PLAN / STATUS
- [DONE] explore (provided): STT default `language="unknown"` (auto-detect) in both agents;
  Sarvam result surfaces detected lang per turn; inbound never read/mirrored it; the kernel
  `_render_turn_layer` already emits a SOFT `USER LANGUAGE: <lang> — mirror it.` line — but
  only when lang non-empty, and on_turn passed raw detected_lang straight through with NO
  uncertain->keep-prior rule and NO light-classify fallback -> blank => `_to_tts_lang("")`
  returns en-IN = the English-only trap.
- [IN PROGRESS] BUILD voice_kernel/language.py — pure droplet-free classifier +
  per-call TurnLanguageResolver (sticky, keep-prior-on-uncertain, never-force-English).
- [ ] WIRE on_turn (inbound + outbound) to use the resolver; return resolved reply_lang
  (TTS code) + flow resolved lang into TurnContext so the soft mirror directive uses it.
- [ ] TESTS voice_kernel/tests/test_language.py + on_turn integration cases.
- [ ] `python -m pytest voice_kernel/` green.
- [ ] design/W-LANG-PROPER-SEAM.md (incl. Sarvam STT auto-detect box config + outbound-redeploy gate).
- [ ] commit per unit.

## DECISIONS
- New module `voice_kernel/language.py` (NOT importing droplet_work/langdetect.py — kernel
  import-isolation forbids droplet imports; the box langdetect.py is the proven heuristic we
  port the SCRIPT-RATIO + MARKER logic from, minus the heavy sticky LanguageTracker forcing).
- Resolver is per-call, turn-scoped, soft. Canonical labels: hindi|english|hinglish|gujarati.
- "keep prior on uncertain": if STT lang blank AND text classify confidence < floor -> reuse
  the resolver's last resolved language (seeded from call locale, default hinglish — NEVER en).
- TTS code: hinglish/hindi/gujarati -> hi-IN ; english -> en-IN. Gujarati degrades to hi audio
  (flash can't speak gu) but is understood — matches box langdetect.py contract.
- Soft directive stays the existing `USER LANGUAGE: <lang> — mirror it.` in _render_turn_layer;
  we simply feed it the RESOLVED (sticky) lang instead of a possibly-blank raw value.
