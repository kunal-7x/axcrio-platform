# W-LANG-PROPER — adaptive per-turn language seam (shared voice_kernel)

Status: BUILT + GREEN (`python -m pytest voice_kernel/` = 340 passed).
Branch: `fix/realtime-voice-kernel-v2`. Flag-gated (KERNEL_INBOUND / KERNEL_OUTBOUND,
default OFF) — OFF path is byte-identical to today.

## 1. The founder's CORRECT spec (and the WRONG one we reverted)

WRONG (reverted in commit `aea9a92`): a heavy stateful `LanguageTracker` that
accumulated state and emitted a HARD "force-reply-in-X" directive. It locked the
agent to one reply language and caused an **English-only** regression.

CORRECT (this wave): the pipeline is purely ADAPTIVE and FOLLOWS the caller:

```
Sarvam STT auto-detects the spoken language per utterance
  -> that detected language flows to the kernel each turn
  -> resolved adaptively (prefer STT code; else light text classify;
     else UNCERTAIN -> keep the PRIOR turn's language — NEVER force English)
  -> the LLM gets a SOFT per-turn signal: "USER LANGUAGE: <lang> — mirror it."
  -> the TTS language code is set to that language for the turn.
```

No hardcoded reply language. No forced lock. Switching is immediate when the
caller switches (Hindi -> English -> Hindi mid-call). W5 casual-Hinglish +
no-half-words are untouched (they run downstream in the SpeechPlanner).

## 2. What was built

### (A) `voice_kernel/language.py` — NEW, pure, droplet-free
- `classify_text(text) -> (canonical_lang, confidence)` — script-ratio + small
  marker lexicon (ported from the proven `droplet_work/langdetect.py`, **without**
  its heavy sticky `LanguageTracker`). Canonical labels: `hindi | english |
  hinglish | gujarati`. SHORT-utterance dampener: a 1-word Latin reply ("ok",
  "haan", a name) returns LOW confidence — too thin to flip the whole call.
- `normalize_lang(raw_code) -> label | ""` — maps a Sarvam/ISO code
  (`hi-IN`, `en-IN`, `gu-IN`, `hi`, `en`) to a label; returns `""` for the Sarvam
  auto-detect placeholder (`""`, `unknown`, `auto`, `und`) or anything
  unrecognised, so the caller light-classifies the text instead — never silently
  defaults to English.
- `tts_lang_code(label) -> "hi-IN" | "en-IN"` — SPEAKABLE telephony codes.
  Gujarati DEGRADES to `hi-IN` audio (the realtime flash model has no `gu` and
  goes silent on it — matches the box `langdetect.py` contract: understand the
  Gujarati caller, reply in Hindi audio). Never empty, never English by default.
- `TurnLanguageResolver(seed_locale=...)` — per-call, turn-scoped, SOFT resolver.
  Seeded from the call locale (default **Hinglish**, NEVER English). `.resolve(
  stt_lang, user_text) -> ResolvedLang(lang, tts_lang, source, switched,
  confidence)`. Priority: (1) a real STT code (authoritative, conf 1.0); (2) else
  light text classify if it clears the 0.45 floor; (3) else UNCERTAIN -> carry the
  PRIOR language. Never raises.

### (B) `voice_kernel/integrations/inbound.py` + `outbound.py` — `on_turn` wired
- Each per-call façade (`InboundKernel` / `OutboundKernel`) now holds a lazily
  built `_lang_resolver` (seeded from `base_ctx.meta.locale`), so the sticky
  keep-prior state survives across turns of one call.
- `on_turn(detected_lang=<raw Sarvam STT lang>, user_text=...)` now:
  1. resolves the language adaptively via the per-call resolver,
  2. feeds the **resolved (sticky)** label into `TurnContext.detected_lang`, so the
     existing soft `USER LANGUAGE: <lang> — mirror it.` directive in
     `kernel._render_turn_layer` uses the resolved value (not a possibly-blank raw
     code) — this is the cache-safe, turn-scoped L5 seam, unchanged in shape,
  3. returns a richer plain dict (no kernel types leak):
     `{"reply_lang": <label>, "tts_lang": <"hi-IN"|"en-IN">,
       "lang_switched": bool, "rag_suffix": str|None, "speech_plan": None}`.
- The agent uses `result["tts_lang"]` to set the per-turn TTS language code, and
  `result["reply_lang"]` flows into `plan_speech(..., lang=reply_lang)` (the
  SpeechPlanner's `_to_tts_lang` maps the canonical label consistently to the same
  code).

### Return-shape change (intentional, additive keys)
`on_turn` gained `tts_lang` + `lang_switched`. The existing integration tests that
pinned the exact dict were updated. The OFF / None-ik path still returns an inert
dict (`reply_lang` = raw input, `tts_lang` = "", no switch) so the agent's legacy
turn is unchanged.

## 3. The English-only failure mode — closed

Root cause that the explore identified: when STT surfaced no language (auto-detect
placeholder) `on_turn` passed a blank `detected_lang` straight through, and the
planner's `_to_tts_lang("")` returns `en-IN`. A blank/uncertain turn therefore
defaulted to English audio. Now:
- a blank STT code -> light text classify;
- an uncertain classify -> CARRY the prior language;
- the seed is Hinglish (hi-IN), never English;
so an uncertain or cold turn resolves to `hi-IN`, never English. Verified by
`test_on_turn_uncertain_first_turn_never_defaults_english` and
`test_resolver_keeps_prior_on_uncertain_never_english`.

## 4. ⚠️ Sarvam STT auto-detect — BOX CONFIG (verify on the droplet)

The kernel can only follow the language the STT actually DETECTS. The explore
confirmed both agents build the Sarvam STT with `language=os.getenv(
"SARVAM_STT_LANG", "unknown")`, and `"unknown"` is the saarika:v2.5 **auto-detect /
code-mix** default — correct. The one remaining risk is an env OVERRIDE.

REQUIRED CHECK on each voice box, before/at INBOUND redeploy:

```bash
grep -n SARVAM_STT_LANG /opt/famit-agent/.env || echo "SARVAM_STT_LANG not set (good: auto-detect)"
```

- If `SARVAM_STT_LANG` is **unset** or `=unknown` -> auto-detect is ON. No change
  needed; the kernel seam works as designed.
- If it is set to a fixed locale (e.g. `hi-IN`) -> the STT is LOCKED and **cannot
  detect English** — that alone is the English-only root cause. FIX: remove the
  line (or set `SARVAM_STT_LANG=unknown`) and restart ONLY the inbound service.

This is a CONFIG change on the box, not a code change. Apply it on the INBOUND box
when the inbound agent reads the new `on_turn` contract.

## 5. Deploy gate (earner law)

- **OUTBOUND earner (`famit-agent`, agent.py md5 `480d23c3`, KERNEL_OUTBOUND live):
  DO NOT touch or restart in this wave.** This wave only changed the SHARED
  tracked `voice_kernel/` modules (language + integration `on_turn`), which are
  additive and KERNEL_OUTBOUND-gated. The outbound *agent.py* is unchanged. When
  the founder finishes testing the outbound earner, a separate gated redeploy can
  pick up the new shared seam (the outbound agent must start reading
  `result["tts_lang"]` + passing the raw Sarvam STT lang as `detected_lang`).
- **INBOUND (`aim-voice-agent`): redeploy + restart ONLY this service.** The
  inbound agent's `on_turn` call site must: (a) pass the raw Sarvam STT detected
  language (`event.alternatives[0].language`, or "" when not surfaced) as
  `detected_lang`; (b) set the per-turn TTS `language_code` from
  `result["tts_lang"]`; (c) the soft directive rides in `result["rag_suffix"]`
  (already appended to the LLM turn context when KERNEL_INBOUND=1).
- Both behind flags default OFF -> resting build byte-identical until flagged.

## 6. Tests (all green)

- `voice_kernel/tests/test_language.py` — classifier (Hindi/English/Hinglish/
  Gujarati/short-uncertain), normalize_lang (codes + auto-detect placeholder),
  tts_lang_code (speakable, gu->hi), resolver (seed=Hinglish-not-English,
  STT-authoritative, adapts both ways, keep-prior-on-uncertain-never-English,
  never raises), and zero droplet/agent imports at load.
- `voice_kernel/integrations/tests/test_{inbound,outbound}_integration.py` —
  updated OFF inert dict + ON dict shape; NEW
  `test_on_turn_adapts_language_both_ways_and_keeps_prior_on_uncertain`
  (Hindi->English->ok-keeps-english->Hindi) and (inbound)
  `test_on_turn_uncertain_first_turn_never_defaults_english`.
- Full suite: `python -m pytest voice_kernel/` = **340 passed**.
