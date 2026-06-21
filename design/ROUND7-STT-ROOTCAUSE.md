# ROUND-7 — STT LANGUAGE MIS-DETECTION: ROOT CAUSE + NON-HARDCODED FIX DESIGN

**Status:** READ-ONLY design. NO box mutation. Implement ONLY after the running brain
workflows `weffmx17e` (round7-complete-voice) and `w31agr8ku` (round7-brain-dna) land and
their `agent.py`/`prompt.py` edits are reconciled — deploying now causes a **3-way agent.py
conflict**. Voice LAW: TTS constructor / `.env EL_STABILITY=0.55` / `voice_id
QTKSa2Iyv0yoxvXY2V8a` stay BYTE-IDENTICAL. STT + room-audio-input tuning ONLY.
**Hard founder constraint: the language must stay AUTO-DETECT (multilingual). NEVER hardcode
`language="hi"` — the founder tried that and it broke Hinglish/English.**

Box (read-only): `ssh -i ~/.ssh/do-blr-test/id_ed25519 famit@168.144.153.145`,
`/opt/famit-agent/` (`agent.py`, `langdetect.py`). Plugin source the venv actually imports:
`/opt/caps/.venv/lib/python3.12/site-packages/livekit/plugins/sarvam/stt.py`.

---

## THE SYMPTOM (confirmed, not guessed)

Caller speaks Hindi ("haan", "haanji boliye") → Sarvam `saarika:v2.5` (`language=unknown`)
returns the WRONG Indic script — Odia `ହଁ ହଁ ହଁ।`, Punjabi/Gurmukhi `ਹਾਂਜੀ ਬੋਲੀਏ`, Tamil
`ம்`, Gujarati/Malayalam — → Groq mirrors that wrong script and replies in Punjabi/Odia → the
caller says "you spoke a different language" and hangs up. **47 of 414 saved transcripts (11%)
contain wrong-script user text; 105 wrong-script turns; 46% are 1–2 words, 67% are <4 words.**
WORSE on speakerphone, but also wrong on normal earpiece calls.

---

## (A) RANKED ROOT CAUSES — each PROVEN (evidence + file:line + web cite)

### RC-1 (PRIMARY for speakerphone) — NO acoustic echo cancellation / noise suppression on the LiveKit room input
**Evidence (code):** `agent.py:1729-1732` calls `await session.start(room=ctx.room, agent=agent)`
with **no `room_input_options=` argument** — a project-wide grep for `RoomInputOptions` /
`noise_cancellation` / `BVC` returns only this line + a comment. The LiveKit
`livekit-plugins-noise-cancellation` package is **NOT installed** in the venv (`pip show` →
empty). `/opt/livekit/livekit.yaml` has **no server-side audio-processing directives** (no AEC,
no noise-suppress). So the raw SIP/RTP caller audio is fed to Sarvam unprocessed.
**Mechanism:** on speakerphone the phone mic re-captures the AI's own ElevenLabs TTS (20–40 dB
more acoustic coupling than earpiece, where the speaker is sealed to the ear). That echo travels
SIP → LiveKit room → Sarvam, so Sarvam receives **AI-Hindi-voice + caller-Hindi-voice mixed**.
`language=unknown` LID must pick ONE script for the mixed signal and lands on an
acoustically-adjacent wrong Indic language. This is the single biggest lever for the
speakerphone-specific worsening, and it is **explicitly in scope** (room-input tuning allowed).
**Web cite:** LiveKit docs — `noise_cancellation.BVCTelephony()` passed via
`RoomInputOptions(noise_cancellation=...)` is the purpose-built enhancement for 8 kHz telephony
input (`docs.livekit.io` → Agents → "Noise & echo cancellation"; the Krisp/BVC telephony model
performs AEC + denoise on the input track). No room_input_options ⇒ none of it runs.

### RC-2 (STRUCTURAL, both call types) — short-utterance auto-detect instability + no acoustic language continuity
**Evidence:** the mis-detects cluster on tiny turns — `ହଁ` (1 char), `ਹਾਂਜੀ` (1–2 words);
46% are 1–2 words. A 1–3-syllable backchannel ("haan"/"ji"/"hmm") carries almost no
phonetic LID signal, so saarika's per-utterance detector returns a near-random adjacent Indic
script. **Sarvam re-runs LID FRESH per utterance** — there is no acoustic carry-over of the
language it already detected confidently earlier in the SAME call, so a short turn that follows
ten confident Hindi turns can still flip to Odia.
**Web cite:** Sarvam STT docs note `language-code=unknown` performs **automatic per-utterance
language identification**; short/low-energy segments are documented as the weakest case for any
streaming LID (general ASR-LID literature: LID confidence scales with utterance duration).

### RC-3 (DEGRADES every Indic LID feature) — 8 kHz telephony narrowband sent to Sarvam as 16 kHz
**Evidence (code):** `agent.py:1277-1286` constructs `sarvam.STT(...)` with only 3 args
(`api_key`, `language`, `model`) — **`sample_rate` is left at the plugin default
`16000`** (`stt.py:301` `sample_rate: int = 16000`, sent verbatim to the API at `stt.py:402-403`
`params["sample_rate"]=str(opts.sample_rate)`). But India PSTN/Vobiz SIP is **G.711 µ-law at 8
kHz narrowband** (spectral content capped at 4 kHz). The audio is up-resampled to 16 kHz (or the
room_io 24 kHz default) but the **acoustic information above 4 kHz is permanently absent** — yet
Sarvam is told it is true wideband 16 kHz. saarika's LID filterbank features above 4 kHz are
zeroed/garbage, so the language posterior is computed on degraded features → wrong Indic script.
**Web cite:** Sarvam STT streaming docs — "for 8 kHz audio, set `sample_rate=8000` both when
opening the connection and per chunk; mismatched rates cause transcription degradation."

### RC-4 (AMPLIFIER, not origin) — wrong script reaches Groq RAW before any sanity layer
**Evidence (code):** `langdetect.py` already degrades other-Indic script → "hindi" reply-language
(`:105-116`, `_ORIYA`/`_GURMUKHI`/`_TAMIL`… ranges at `:36-42`) and `agent.py:1572-1583`
carries the prior language on <4-word turns and never defaults to English. BUT that logic only
steers the **reply language hint**; the **raw wrong-script transcript itself is still inserted
into the Groq chat context** (it is `new_message` in `on_user_turn_completed`, already added by
LiveKit before the hook runs). So Groq SEES `ਹਾਂਜੀ ਬੋਲੀਏ` verbatim and mirrors Punjabi even when
the reply-hint says "hindi". There is **no transcript-normalization seam** that rewrites the
user message before the LLM consumes it. (Logging gap: `journalctl` only prints the post-
langdetect bucket `lang mirror v2 -> hindi`, never the raw script — the wrong script is invisible
in the journal, visible only in `var/transcripts/{room}.json`.)

**Ranking:** RC-1 explains "worse on speakerphone"; RC-2 + RC-3 explain "wrong on normal calls
too" and the short-turn clustering; RC-4 is why a single wrong transcript still derails Groq
despite the existing langdetect degrade. The robust fix is **all four, layered** (acoustic →
detector → STT params → text sanity), each independently reversible.

---

## (B) FIX DESIGN — voice byte-identical, NEVER hardcode the language, keeps auto-adapt

> Every fix below is **additive + flag/env-gated + default-OFF or default-identical**, so OFF =
> the exact current behavior. None touches the TTS constructor, `EL_STABILITY`, or `voice_id`.

### FIX-1 — Acoustic echo cancellation + noise suppression on the room input (the speakerphone root fix → RC-1)
Install `livekit-plugins-noise-cancellation` and pass it ONLY via room input options, gated:
```python
# agent.py, at session.start (~1729). Default OFF => byte-identical.
_rio = None
if os.getenv("ROOM_NC", "0") not in ("0", "false", "False"):
    from livekit.plugins import noise_cancellation
    from livekit.agents import RoomInputOptions
    _rio = RoomInputOptions(noise_cancellation=noise_cancellation.BVCTelephony())
await session.start(room=ctx.room, agent=agent, room_input_options=_rio)
```
`BVCTelephony()` is the 8 kHz-phone variant (does AEC + denoise on the INPUT track only — it
never touches TTS output, so the voice is byte-identical). This strips the AI's re-captured TTS
echo before Sarvam sees it, so LID detects only the caller. **Does NOT hardcode language** —
auto-detect is unchanged; it just gets a clean signal.

### FIX-2 — SOFT language continuity (carry prior confident language on short/ambiguous turns; treat wrong-script as degrade-to-prior, NEVER a hard lock, NEVER default English → RC-2)
The `_LangTracker` (`langdetect.py:231-258`) + the `agent.py:1572-1583` carry-prior block are the
**A1b soft-hint** approach already half-built. Strengthen it (still soft):
- On any turn whose dominant script is other-Indic (Odia/Punjabi/Tamil/Mal/Guj/Beng/Tel/Kan via
  the ranges at `langdetect.py:36-42`), **do not let it switch the active language** — classify it
  as a **degrade-to-prior** (keep `tracker.active`), exactly as `classify_text` already maps it to
  "hindi" at `:105-116`, but ALSO suppress `lang_tracker.update()` from flipping `active` on it.
- Extend the existing `<4-word` carry-prior guard (`agent.py:1576`) so it carries the prior
  language on ANY low-confidence turn (`conf < conf_floor`), not only short ones.
- **Never a hard `language=` lock and never default English** — the carried value is whatever was
  last *confidently* detected (could be english/hinglish/gujarati), so a genuine language switch on
  a LONG confident turn still flips. This preserves multilingual auto-adapt.
Gated by the existing `_lang_v2` flag; OFF = current behavior.

### FIX-3 — Sarvam soft-bias / code-mix params that KEEP auto-adapt (→ RC-2/RC-3)
Two non-hardcoding STT knobs, env-gated, A/B-tested one real call each:
- **(3a) `sample_rate=8000`** to match the real G.711 SIP narrowband (RC-3). Env:
  `SARVAM_STT_RATE` (default keeps `16000` = current). Plugin accepts it (`stt.py:301,402-403`).
  This is NOT a language constraint — it only tells Sarvam the true acoustic rate so its LID
  features are computed correctly.
- **(3b) Move to `saaras:v3` + `mode="codemix"`** (env `SARVAM_STT_MODEL=saaras:v3`,
  `SARVAM_STT_MODE=codemix`). Proven from plugin source: `saarika:v2.5` has
  `supports_vad_params=False` (`stt.py:152`) and NO codemix; **`saaras:v3` has
  `supports_vad_params=True` (`stt.py:174`)** and is the model that supports `codemix`
  (`stt.py:64,287`) + fine-grained VAD (`positive_speech_threshold`, `min_speech_frames`,
  `pre_speech_pad_frames`) that stabilize short-turn detection. `codemix` is explicitly
  multilingual/auto-adapt — it does NOT force one language; it transcribes Hinglish/code-mixed
  speech in its real mixed script. This is the most "root-cause + auto-adapt-preserving" lever, but
  it is a model swap → test carefully (latency + accuracy) before keeping.

### FIX-4 — Transcript sanity layer so wrong-script NEVER reaches the LLM raw (→ RC-4)
Add a seam in `on_user_turn_completed` (BEFORE the kernel/langdetect branches at `agent.py:1535`)
that inspects `new_message` and, when the dominant script is other-Indic (reuse the
`langdetect._script_counts` ranges), **rewrites the user message content** that Groq will read —
either (a) replace with the Sarvam `translit`/Devanagari form if available, or (b) prepend a
neutral `[caller spoke Hindi]` and strip the rogue-script tokens — so Groq never mirrors Punjabi/
Odia. Default OFF (`STT_SANITY=0`). Also **log the RAW transcript** here (closes the journal
blind-spot) so future calls are diagnosable. This is text-only, never affects voice.

---

## (C) PER-FIX: offline verify · founder real-call test · rollback · sequencing

**SEQUENCING (mandatory):** do NONE of these until `weffmx17e` AND `w31agr8ku` have landed and
their `agent.py`/`prompt.py` are reconciled to one md5 — implementing now = 3-way conflict. Then
apply ONE fix at a time, founder real-call test (NORMAL earpiece AND SPEAKERPHONE) after each,
re-assert the TTS-span md5 (`agent.py` ll.1161-1185 = `7b36c4f9d57cd76d5116d93156560dcb`) +
`EL_STABILITY=0.55` + `voice_id` before/after. Recommended order: **FIX-1 → FIX-4 → FIX-2 →
FIX-3** (acoustic + sanity are highest-leverage and safest; the model swap last).

| Fix | Offline verify | Founder real-call test | One-command rollback |
|---|---|---|---|
| **FIX-1 AEC** | `pip show livekit-plugins-noise-cancellation` installs; import `noise_cancellation.BVCTelephony` OK; service boots, worker `capsy` registers, NRestarts=0; play a TTS-echo sample file through the input and confirm LID stops flipping. | Place a real call on **SPEAKERPHONE**, speak Hindi "haanji boliye" + short backchannels — AI replies in Hindi, never Punjabi/Odia; voice sounds identical. Repeat on earpiece. | `ROOM_NC=0` in the systemd drop-in → `systemctl restart famit-agent` (env-only, no redeploy). |
| **FIX-2 continuity** | Unit-test `_LangTracker`: feed [hindi×5, `ਹਾਂਜੀ`, `ਹਾਂ`] → `active` stays "hindi"; feed a long confident english turn → flips to english (switch still works); low-conf turn keeps prior, never english. | Real call: open with Hindi, drop short "haan/ji/ok" turns → AI stays Hindi; then speak a full English sentence → AI mirrors English (proves not a hard lock). | `_lang_v2=0` (or revert the langdetect block) → restart. `langdetect.py.bak` armed. |
| **FIX-3a rate / 3b saaras-codemix** | Offline: send a known 8 kHz µ-law sample to Sarvam at `sample_rate=8000` and at `saaras:v3 codemix`; compare transcript script-correctness vs current; measure added latency (first-token + end-to-end) — must not regress. | Real call A/B: one call current, one call new; founder confirms cleaner Hindi script AND no latency/voice regression AND English/Hinglish still transcribe correctly (auto-adapt intact). | `SARVAM_STT_RATE=16000` / `SARVAM_STT_MODEL=saarika:v2.5` / unset `SARVAM_STT_MODE` in drop-in → restart (env-only). |
| **FIX-4 sanity layer** | Unit-test: feed `ਹਾਂਜੀ ਬੋਲੀਏ` → rewritten message contains no Gurmukhi before it reaches the LLM context; feed clean Hindi/English → passthrough unchanged. Confirm raw transcript now logged. | Real call: even if Sarvam still mis-scripts once, Groq replies in Hindi (never echoes Punjabi/Odia); call does not collapse. | `STT_SANITY=0` → restart. `agent.py.*bak` armed. |

**Each is reversible env-only (or one `*bak` restore) with `_GOLDEN_ROUND7/restore.sh` as the
full backstop.** None deploys now.

---

Pointer appended to `CONTINUE-HERE-ROUND7.md`.
