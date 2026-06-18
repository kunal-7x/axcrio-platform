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

## Phase: VERIFY + COMMIT + REDEPLOY-INBOUND (2026-06-18)
**STATUS: ✅ DONE — committed `1610ed5` (BUILD already in HEAD; this phase = VERIFY + redeploy
INBOUND so the seam is LIVE, not inert). Inbound `aim-voice-agent` restarted with the new
`voice_kernel/`; earner `famit-agent` NEVER touched.**

### Red-team verdict folded
SHIP the kernel module — it was INERT in prod until the inbound agent had it. Confirmed:
`UserInputTranscribedEvent.language` exists + is populated from `SpeechData.language` (Sarvam
per-utterance `language_code`), so the detection path is real; the live agent's `on_turn` is
wired to pass `ev.language` → `on_turn(detected_lang=...)` and apply `tts_lang`. The five
red-team questions all clear (both-ways switch w/ no hysteresis; NO path defaults to English —
every give-up branch carries PRIOR lang; truly soft single suffix line, no forcing/lock;
STT-auto-detect dependency has a safe fallback chain blank→text-classify→carry-prior; W5
casual-Hinglish/no-half-words untouched). One real point: "re-deploys INBOUND" only changes
behavior once the box has the new tree — which this phase did.

### VERIFY (local)
- `python -m pytest voice_kernel/` = **340 passed**. `test_language.py` + off-identity
  (`test_adapter_off_identity` + `test_events_off_identity`) = **42 passed**.
- Synthetic both-ways: Hindi(stt hi-IN)→hindi/hi-IN; switch(stt en-IN)→english/en-IN
  switched=True; back→hindi/hi-IN switched=True; short "ok" w/ blank STT → source=`carried`,
  keeps PRIOR lang (NOT English). The English-only trap is closed.
- gitleaks `detect --log-opts="-1 1610ed5"` = **0 leaks** (38.7 KB scanned).
- EARNER source `droplet_work/agent.py` md5 = `98655dbf` (tree golden, frozen, untouched).

### EARNER GATE — before / after (box `famit@168.144.153.145`)
Box-deployed earner md5 = `480d23c3f2e1daf4814b9a3a9c9695d4` (the live KERNEL_OUTBOUND=1 build).
| Phase | agent.py md5 | famit-agent | famit-agent MainPID | caller /health | aim-voice-agent |
|---|---|---|---|---|---|
| BEFORE | `480d23c3` ✅ | active | 3979046 (uptime 14:44:47Z) | 200 | active |
| AFTER  | `480d23c3` ✅ UNCHANGED | active | **3979046 (uptime 14:44:47Z — NOT restarted)** | 200 | active (NEW pid 3988655) |
- ZERO drift. famit-agent MainPID + uptime identical before/after = earner never restarted/touched.
- NO outbound ring placed.

### REDEPLOY INBOUND (aim-voice-agent only)
- Flag already ON: drop-in `/etc/systemd/system/aim-voice-agent.service.d/kernel-inbound.conf`
  = `KERNEL_INBOUND=1` (unchanged; lives ONLY in the drop-in, never the shared `.env`).
- No Sarvam STT config change needed: STT already runs `language="unknown"` (auto-detect) in the
  inbound agent — the seam consumes the per-utterance detected lang; no hi-IN lock to remove.
- Shipped `voice_kernel/` via tar-over-ssh, ATOMIC swap with timestamped backup:
  - box backup of prior tree → `/opt/famit-agent/voice_kernel.LANGbak.20260618-152053`
  - LIVE `voice_kernel/language.py` md5 on box = `b1c05080f5a41cd510c8be0084dba63c`
  - (box had NO `language.py` before — confirms the seam was committed but inert in prod.)
- Pre-restart box import check (box python): `import voice_kernel.language` + `...integrations.inbound`
  OK, `on_turn` present, synthetic resolve correct (Hindi→hindi, switch→english, carry→prior).
- `sudo systemctl restart aim-voice-agent` ONLY. New MainPID 3988655, all 4 workers
  `process initialized` + `AIM prewarm: Silero VAD loaded`, HTTP :8091, `registered worker
  agent_name="manager" id=AW_zD59Xv2uKwGJ`. Journal new generation = **0** Traceback/ImportError.
  (The 15:23:14 `Failed to kill control group`/`result 'timeout'` lines = OLD-gen teardown during
  the stop phase, not a flag-ON error.)

### ROLLBACK (instant)
- Disable kernel: flip the drop-in to `KERNEL_INBOUND=0` + `daemon-reload` + restart `aim-voice-agent`.
- Or restore the prior tree: `sudo rm -rf /opt/famit-agent/voice_kernel && sudo mv
  /opt/famit-agent/voice_kernel.LANGbak.20260618-152053 /opt/famit-agent/voice_kernel && sudo
  systemctl restart aim-voice-agent`.
- Either path touches `aim-voice-agent` ONLY; `famit-agent`/`agent.py` never affected.

### FOUNDER RE-TEST
Call **+918071583488**. Start in **Hindi**, then **switch to English mid-call** — the agent must
follow your language both ways (and back). A short "ok"/"haan" must NOT flip it to English.

### GATED OUTBOUND-REDEPLOY PLAN (ship the same fix to the earner LATER)
The flag is already ON for outbound (`KERNEL_OUTBOUND=1`, agent.py `480d23c3`), so the earner
already routes through `voice_kernel.integrations.outbound.on_turn` — which is wired to the same
resolver. To give the OUTBOUND earner this language fix: ship the SAME new `voice_kernel/` to the
box (it is shared — this redeploy already put `language.py` there, so outbound picks it up on its
NEXT restart), then by EARNER LAW do a super-gated `famit-agent` redeploy as its OWN founder step:
backup-record `480d23c3`, restart `famit-agent` ONLY during a quiet window, EARNER GATE before/after,
and the FOUNDER places ONE real outbound ring on his own number (Hindi→English switch) to confirm.
Instant rollback = `KERNEL_OUTBOUND=0` + restart, or restore `agent.py.WOUTbak.1781793303`. Do NOT
restart `famit-agent` in this wave (founder is testing the earner).
