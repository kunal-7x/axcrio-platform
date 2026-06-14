
## Phase: EXPLORE — full inbound voice path map + earner gate + old-vs-current diff + inbound transcript

**Date:** 2026-06-14 · READ-ONLY exploration · No box mutation · No restart.

### EARNER GATE = GREEN
- `agent.py` md5 `9150fabe4ff62b4b4470f9a87df346e5` UNCHANGED.
- `famit-agent` MainPID **1477083** active since 2026-06-10 19:58:18 UTC — never restarted.
- `aim-voice-agent` active (PID 2721961, post-build restart 2026-06-14 15:03:01 UTC).
- famit-caller `/health` port 8208 = 200 OK (`{"status":"ok","agent":"capsy","trunk":"ST_fmtVmNJmpzKa"}`).
- 0 5xx, NO ring.

### (1) TTS CONFIG — current live state on box (`aim_voice_agent.py` md5 `1614be09`)

**ElevenLabs path** (`_build_tts_elevenlabs`, aim_voice_agent.py:406-421):
- `voice_id=os.getenv("ELEVENLABS_VOICE_ID", "QTKSa2Iyv0yoxvXY2V8a")` → .env: `QTKSa2Iyv0yoxvXY2V8a` (Neha P, English voice)
- `model=os.getenv("ELEVENLABS_TTS_MODEL", "eleven_flash_v2_5")` → .env: `eleven_flash_v2_5`
- `language=os.getenv("AIM_TTS_LANG", "hi")` → .env: `AIM_TTS_LANG=hi` ← hard-pinned "hi"
- Used when: `INBOUND_PROV_LOCK=OFF` or campaign resolves `tts=elevenlabs` (premium tier)

**Sarvam path** (`_build_tts_sarvam`, aim_voice_agent.py:424-440):
- `target_language_code=os.getenv("SARVAM_TTS_LANG", "hi-IN")` → NOT in .env → default `hi-IN` ← hard-pinned
- `speaker=os.getenv("SARVAM_TTS_SPEAKER", "anushka")` → NOT in .env → default `anushka`
- `model=os.getenv("SARVAM_TTS_MODEL", "bulbul:v2")` → NOT in .env → default `bulbul:v2`
- Used when: `INBOUND_PROV_LOCK=1` (set in systemd service) AND campaign `tts_provider=sarvam` or tier=lean/standard

**INBOUND_PROV_LOCK=1** set in systemd `aim-voice-agent.service` `Environment=` line (not in .env).

**Codename Joy 3.0 campaign** (db): `tts_provider=sarvam`, no `plan_tier` → resolves via explicit `tts_provider` field to `sarvam` → Sarvam Bulbul path ACTIVE for founder's test calls.

**Live journal confirms:** `"AIM provider-lock ON: resolved stt=sarvam llm=groq tts=sarvam"` → `"AIM provider-lock: TTS=sarvam (Bulbul) constructed"` → `model=bulbul:v2 speaker=anushka`.

### (2) STT CONFIG — `_build_stt` (aim_voice_agent.py:383-403)
- Sarvam saarika:v2.5, `language=os.getenv("SARVAM_STT_LANG", "unknown")` → .env: NOT SET → default `"unknown"` = AUTO-DETECT mode.
- STT is AUTO — not pinned. Confirmed: `"language": "unknown"` in live journal WebSocket connect.
- HARDWIRED regardless of tier/provider-lock.

### (3) PROMPT LAYERS
**a) MLV mirror** (~aim_voice_agent.py:1577): tells LLM to reply in caller's language. Added in the MLV wave. INTACT.
**b) FINAL LANGUAGE LOCK** (~:1631): "Reply in SAME language the CALLER used." INTACT.
**c) SCRIPT RULE** (commit 69374eb, aim_voice_agent.py:1632-1665): Appended AFTER the language lock. 5 rules:
   1. Write every HINDI word in DEVANAGARI — banned romanized list (hai, hain, mein, ke, ki...)
   2. Keep ENGLISH loan-words (BHK, project, confirm, Codename Joy, etc.) in LATIN.
   3. NEVER mix Devanagari + romanized in same sentence.
   4. NUMBERS as digits.
   5. Casual register (रुकिए not प्रतीक्षा कीजिए, "please" not "कृपया").
   Guard: "applies ONLY when you are speaking Hindi or Hinglish; an English caller still gets pure English."
**d) resolve_providers tier map** (prompt.py:137-141): lean/std → sarvam; premium → EL. Codename Joy bypasses tier via explicit `tts_provider=sarvam` in campaign fields.

### (4) OLD-PERFECT vs CURRENT DIFF — what actually changed

**Before ab6777c (commit 4db497f — P0-LEAK state, "working before"):**
- `_build_tts()` was a SINGLE function, always returning ElevenLabs `eleven_flash_v2_5`, voice `QTKSa2Iyv0yoxvXY2V8a`, `language="hi"`.
- NO `INBOUND_PROV_LOCK`; NO tier-based routing; NO Sarvam TTS path.
- ALL inbound calls → ElevenLabs always.
- Language rules: MLV mirror (`:1577`) + FINAL LANGUAGE LOCK (:1631) — same as now, but NO SCRIPT RULE.

**Key diff (current vs old-perfect):**

| | OLD-PERFECT (4db497f) | CURRENT (1614be09 / HEAD) |
|---|---|---|
| TTS dispatch | Single EL path | INBOUND_PROV_LOCK dispatch: EL or Sarvam |
| Codename Joy TTS | ElevenLabs (always) | Sarvam Bulbul v2 (campaign field tts_provider=sarvam) |
| EL language param | `"hi"` (Neha P, EN voice) | Same: `"hi"` (unchanged) |
| Sarvam TTS lang | — (no Sarvam path) | `"hi-IN"` (hard-pinned default) |
| Sarvam speaker | — | `"anushka"` (default) |
| Sarvam model | — | `"bulbul:v2"` (not v3) |
| LLM script rule | None — free-for-all Hinglish | SCRIPT RULE: Devanagari Hindi + Latin loan-words (69374eb) |
| MLV mirror | Present | Present (unchanged) |
| FINAL LANG LOCK | Present | Present + extended for SCRIPT RULE |

**Root cause chain:** ab6777c introduced Sarvam TTS routing. Campaign was set to `tts_provider=sarvam`. Sarvam Bulbul v2 requires Devanagari input — but LLM was emitting romanized Hinglish (no script constraint) → garbling. SCRIPT RULE (69374eb) was the fix: constrain LLM output to Devanagari+Latin mix so Sarvam handles it cleanly.

### (5) CAPTURED INBOUND TRANSCRIPT — founder's test call Jun-14 15:18 UTC

**Session:** room `RM_H4JEw2iThSwh`, caller `089***61`, returning lead, campaign Codename Joy 3.0, TTS=Sarvam Bulbul v2.
**Caller STT-final turns (what they said):**
1. `मुझे बाय करना है फ्लैट।` (I want to buy a flat)
2. `तो सब कॉन्फ़िगर अवेलेबल है।` (So all configurations are available?)
3. `तो` (So...)
4. `आपके पास कौन सी प्लेट है आपके पास कौन कौन सी प्लेट अवेलेबल है ये पूछ रहा हूँ` (Which plates/flats do you have available?)
5. `तुम्हारे पास कोई कोड नेम जो है नाम का कोई कैंपेन है?` (Do you have a campaign called Codename something?)
6. `मुझे ये बाय करना है फ्लैट।` (I want to buy this flat)
7. `बहुत महंगा है, बहुत महंगा है यार, इतना महंगा मुझसे नहीं होगा।` (Too expensive, I can't afford this)
Session ended → lead upsert. Second session started at 15:20 UTC (returning same lead, INBOUND_PROV_LOCK ON, Sarvam Bulbul confirmed in logs).

Note: STT ("प्लेट" for "flat" in turn 4) shows Sarvam auto-STT imperfection on English loanwords in Hindi speech — saarika auto-mode handles it reasonably but "flat"→"प्लेट" is a near-miss.

### STATUS
EXPLORE COMPLETE. Earner gate GREEN. No box mutation. Ready for BUILD/FIX phase if directed.

---

## Phase: RESEARCH — TTS language config for natural Hinglish (Sarvam + ElevenLabs)

**Date:** 2026-06-14 · Deep web research · No box mutation.

### SARVAM BULBUL — FINDINGS

#### (A) Does pinning `target_language_code="hi-IN"` break Latin English words?

**Confirmed: YES for bulbul:v2, LESS SO for bulbul:v3.**

- `target_language_code` is NOT a language-detection parameter — it drives the **pre-TTS text normalization model** (number expansion, abbreviation handling, script normalization).
- When set to `hi-IN`, the normalizer expects Devanagari input. Romanized Hinglish (e.g. "Aapka order confirm ho gaya") causes quality degradation — docs explicitly warn: *"transliterated input significantly reduces output quality."*
- **bulbul:v2** has NO native code-mix handling. It garbles English brand names (BHK, Codename Joy) when they appear in a `hi-IN` context because its normalizer applies Hindi phoneme mapping to Latin characters.
- **bulbul:v3** has built-in code-mixed Hinglish support ("handles code-mixed text, number normalization, and natural prosody out of the box"). The normalizer in v3 is trained to pass through English loan-words in Latin script rather than forcing Hindi phoneme substitution. Example confirmed in docs: `"आपका OTP 4321 है। Please use it…"` is spoken naturally without preprocessing.

#### (B) Is there an auto-detect or code-mixed mode in Sarvam TTS?

**No auto-detect for TTS. But the correct mode is `hi-IN` + `bulbul:v3` + Devanagari+Latin mixed input.**

- Sarvam STT (saarika) has `language="unknown"` for auto-detect. TTS does NOT.
- The `target_language_code` is **required** for all TTS calls — no null/auto enum exists.
- The correct approach for code-mixed Hinglish is:
  1. Use `model=bulbul:v3` (not v2)
  2. Use `target_language_code="hi-IN"` (unchanged — this is correct)
  3. Format LLM output as: **Hindi words in Devanagari, English loan-words in Latin** — exactly what the SCRIPT RULE (69374eb) enforces
  4. Do NOT romanize Hindi words (no "hai/hain/mein" in Latin)
- v3 handles this natively. v2 does NOT — v2 requires either pure Devanagari or a Pronunciation Dictionary for every English term.

#### (C) Pronunciation Dictionary for brand names (BHK, Codename Joy)

- For words that still garble in v3 (niche acronyms, project-specific brand names): upload a JSON pronunciation dict via Sarvam API → get a `dict_id` → pass it on every TTS call.
- Example: `"BHK"` → `"बी एच के"` (spells it out), `"Codename Joy"` → `"कोडनेम जॉय"`.
- This is the production-grade fix for the residual phonetic approximation issue.

#### (D) `enable_preprocessing` flag

- `enable_preprocessing=true` normalizes English words and numeric entities for mixed-language text.
- **WARNING: Only available for bulbul:v2. Explicitly unsupported/unavailable in bulbul:v3.**
- v3 does this natively without the flag.

#### (E) Summary: root cause of the garbling (BHK→"उसाई", Codename Joy→"वुड नेम मोई")

The live box is running **bulbul:v2 + `hi-IN` + anushka** (defaults, since SARVAM_TTS_MODEL/SPEAKER not in .env). The SCRIPT RULE (69374eb) was a valid fix for the LLM output format (Devanagari+Latin), but:
- **v2 still maps Latin-script English words through Hindi phoneme rules** even when they're in Latin — hence "BHK"→"उसाई" (approximated as "B"→उ, "H"→ स, "K"→ई-style phoneme substitution).
- **v3 passes Latin English words through as English phonemes natively** — no such garbling.
- The fix is to upgrade to `bulbul:v3`. The SCRIPT RULE stays (it's the right input format for v3 too). Language code `hi-IN` stays unchanged.

---

### ELEVENLABS FLASH V2.5 — FINDINGS

#### (A) Language support and auto-detection

- `eleven_flash_v2_5` supports 32 languages including Hindi. Language is **auto-detected** — no hard language pin needed (unlike Sarvam).
- ElevenLabs uses in-house AI for automatic multilingual detection within a single generation.
- Flash v2.5 target latency ~75ms, suitable for real-time voice agents.

#### (B) Hinglish / code-switching

- ElevenLabs added `hinglish_mode` (boolean, default `false`) to agent configuration on **December 15, 2025**.
- When `hinglish_mode=true` AND agent language is set to Hindi → responses are Hinglish (Hindi-English mix) with natural code-switching.
- This is an **agent-level** config (create/update/get agent endpoints), not a per-TTS-call parameter.
- The underlying TTS still uses auto language detection — `hinglish_mode` primarily affects the LLM response language, not the synthesis model directly.

#### (C) Hindi-capable voices vs English-only voices

**Critical finding: `Neha P` (voice_id `QTKSa2Iyv0yoxvXY2V8a`) is an ENGLISH voice.**
- Using an English voice with `language="hi"` forces EL to synthesize Hindi phonemes through an English-accent vocal tract → unnatural for Hinglish callers.
- **Hindi-native/multilingual voices confirmed available:**
  - `Raju` (voice_id `zT03pEAEi0VHKciJODfn`) — "Relatable Hindi Voice", Male, multilingual, Clear/Natural/Warm
  - `Mahi` — Conversational, Warm and Clear, India-tuned
  - `Monika Sogam` — Friendly and Reassuring
  - `Anika` — Clear, friendly, Hinglish-capable
- **Correct EL config for Hinglish:**
  - `model=eleven_flash_v2_5`
  - `voice_id=zT03pEAEi0VHKciJODfn` (Raju) or another Hindi-native voice — NOT Neha P
  - Do NOT hard-pin `language="hi"` — let auto-detect handle it; or omit the language param entirely
  - The `AIM_TTS_LANG=hi` env var in `.env` is the bug for the EL path: it forces Hindi-only, which kills natural code-switching for English words

---

### VERDICT: EXACT ENGINE+VOICE+LANGUAGE CONFIG FOR NATURAL TELECALLER HINGLISH

#### Option 1: Sarvam (current provider for Codename Joy) — RECOMMENDED FIX

| Parameter | Current (broken) | Correct |
|---|---|---|
| `model` | `bulbul:v2` | **`bulbul:v3`** |
| `target_language_code` | `hi-IN` | **`hi-IN`** (unchanged — correct) |
| `speaker` | `anushka` (v2 voice) | **`anushka` is v2 only** → use `priya`, `neha`, or `kavya` (v3 female voices) |
| LLM output format | Devanagari Hindi + Latin English (SCRIPT RULE) | **KEEP SCRIPT RULE** — same format, v3 handles it better |
| Pronunciation dict | None | Add dict for BHK, Codename Joy for residual edge cases |

**Change: `SARVAM_TTS_MODEL=bulbul:v3` + `SARVAM_TTS_SPEAKER=neha` (or `priya`)** in `.env`. No other change. SCRIPT RULE stays.

#### Option 2: ElevenLabs (for premium tier or if switching Codename Joy back)

| Parameter | Current (broken) | Correct |
|---|---|---|
| `model` | `eleven_flash_v2_5` | **`eleven_flash_v2_5`** (correct) |
| `voice_id` | `QTKSa2Iyv0yoxvXY2V8a` (Neha P, English) | **`zT03pEAEi0VHKciJODfn` (Raju)** or Mahi/Anika |
| `language` param | `"hi"` (hard-pinned via `AIM_TTS_LANG=hi`) | **Omit or set to auto** — remove `AIM_TTS_LANG` from `.env` |

**Change: `ELEVENLABS_VOICE_ID=zT03pEAEi0VHKciJODfn` + remove `AIM_TTS_LANG` from `.env`.** SCRIPT RULE can be relaxed for EL (it handles romanized Hinglish natively too), but keeping it doesn't hurt.

---

### CONFIDENCE LEVELS
- Sarvam v2 garbles English words in hi-IN: **HIGH** (documented behavior + live evidence from founder's call)
- Sarvam v3 handles code-mix natively: **HIGH** (multiple official sources + Sarvam AI blog)
- `bulbul:v3` speaker list (priya/neha/kavya): **HIGH** (Sarvam API docs)
- EL Neha P is English-only voice: **HIGH** (voice library data)
- Raju voice_id `zT03pEAEi0VHKciJODfn` is Hindi-native: **HIGH** (json2video catalog)
- EL `hinglish_mode` in agent config: **HIGH** (EL changelog Dec 15 2025)
- EL auto-language detection for flash_v2_5: **MEDIUM-HIGH** (EL docs say 32 languages, auto-detect, no explicit pin required)

### STATUS
RESEARCH COMPLETE. Recommended fix: upgrade Sarvam to v3 + switch speaker to `neha` or `priya`. Earner gate GREEN. No box mutation.


---

## Phase: SURGICAL ROOT CAUSE (opus) — exact broken knob + minimal restore plan

**Date:** 2026-06-14 · Synthesis only · No box mutation · Earner gate GREEN (agent.py md5 9150fabe UNCHANGED, famit-agent PID 1477083 not restarted).

**Git ground-truth verified (not assumed):** `4db497f`=old-perfect (single EL path, NO Sarvam). `ab6777c`=provider-lock introduced `_build_tts_sarvam` (`bulbul:v2`/`anushka`/`hi-IN`) + INBOUND_PROV_LOCK resolver. `69374eb`=SCRIPT RULE. Current HEAD knobs match EXPLORE exactly (lines 410-412 EL, 436-438 Sarvam).

### RANKED ROOT CAUSE

**#1 PRIMARY — (b) ENGINE ROUTING flipped Codename Joy from ElevenLabs to Sarvam Bulbul *v2*.** This is THE regression. Old-perfect (`4db497f`) sent ALL inbound to ElevenLabs flash_v2_5, which tolerates code-mixed/romanized Hinglish + English brand words ("Codename Joy"→"कोड नेम जॉय", "BHK"→"बीएचके" in the live repro). `ab6777c` + the campaign's `tts_provider=sarvam` field + `INBOUND_PROV_LOCK=1` (systemd) rerouted the founder's live campaign to **Sarvam Bulbul v2**, which phonetically mangles Latin English tokens in a `hi-IN` context ("BHK"→"उसाई", "Codename Joy"→"वुड नेम मोई"). The founder's "it was PERFECT before" maps precisely to "before ab6777c it was on EL." *What he hears changed because the engine changed.*

**#2 SECONDARY — (a)/the model VERSION, not the language code.** `target_language_code="hi-IN"` is CORRECT and must NOT change (Sarvam TTS has no auto/code-mix enum; hi-IN + Devanagari+Latin input is the documented code-mix path). The broken knob inside the Sarvam path is `model=bulbul:v2` (a legacy model with no native code-mix). v3 passes Latin English through with English phonemes. So "language pinned hi" is a RED HERRING for Sarvam — the founder-insight applies to the EL path, not the live Sarvam path.

**#3 TERTIARY — (d) EL English voice + (a) language pin — only bites if/when EL is used.** EL path uses `QTKSa2Iyv0yoxvXY2V8a` = "Neha P" (English voice) hard-pinned `AIM_TTS_LANG=hi`. Currently DORMANT for Codename Joy (it's Sarvam-routed), so it is NOT the cause of the founder's current bad call — but it's a latent bug for premium tier / any EL fallback.

**NOT a cause (ruled out, evidence-backed):**
- **(c) my SCRIPT RULE (`69374eb`) is NOT fighting the engine — KEEP IT.** Devanagari-Hindi + Latin-English IS the documented correct Bulbul input format, and the VERIFY round-trip proved it strictly *improved* intelligibility (Hindi structure now survives; only English proper nouns still approximate — that's the v2 model limit, not the rule). Reverting it would REGRESS Sarvam (back to romanized "वोडने मोई" garbling). The founder's "auto-adaptive, don't over-force" instinct is right in spirit, but the SCRIPT RULE governs SCRIPT not LANGUAGE — it never overrides the MLV mirror's language CHOICE. Do not revert.
- **(e) STT pinning — NOT a cause.** saarika `language="unknown"` = auto-detect, unchanged since before, round-trips Devanagari cleanly. Leave it.

### MINIMAL RESTORE PLAN (favored: minimal, evidence-backed, earner-safe)

Two valid restore paths. **Recommended = OPTION A** (smallest blast radius, keeps the founder on the engine he's pinned to, fixes the actual broken knob):

**OPTION A (RECOMMENDED) — upgrade the Sarvam model in place. 2 env knobs, zero code, zero routing change:**
| Knob | From | To | Where |
|---|---|---|---|
| `SARVAM_TTS_MODEL` | `bulbul:v2` (default) | `bulbul:v3` | box `.env` (add line) |
| `SARVAM_TTS_SPEAKER` | `anushka` (v2-only) | `manisha` or `vidya` (v3 female; verify against live `/text-to-speech` 200 before commit — anushka is NOT a v3 speaker) | box `.env` (add line) |
| `target_language_code` | `hi-IN` | **NO CHANGE** | — |
| SCRIPT RULE (69374eb) | present | **KEEP** | — |
| MLV mirror + FINAL LANG LOCK | present | **KEEP** | — |
- No `aim_voice_agent.py` edit → golden auto-passes; only `.env` + `aim-voice-agent` restart. Lowest risk.
- P1 follow-up: Sarvam Pronunciation Dictionary (BHK→बी एच के, Codename Joy→कोडनेम जॉय) + `dict_id` in `_build_tts_sarvam` to kill residual brand-name approximation. (Requires a code edit → separate gated unit.)

**OPTION B — restore the true old-perfect: route Codename Joy back to ElevenLabs.** Closest to literal "what it was before ab6777c," BUT requires fixing the EL voice too (else premium sounds anonymous):
- Flip campaign `tts_provider` off sarvam (or `_TIER_TTS` map) → EL. AND `ELEVENLABS_VOICE_ID=zT03pEAEi0VHKciJODfn` (Raju, Hindi-native) + remove `AIM_TTS_LANG=hi` (let flash_v2_5 auto-detect). Larger blast radius (changes routing + metering label for every lean/standard tenant), so NOT recommended as the first move.

**Verdict:** The break is **engine routing to Bulbul v2** (not the language pin, not my SCRIPT RULE). Minimal correct restore = **Option A: `SARVAM_TTS_MODEL=bulbul:v3` + a valid v3 speaker, hi-IN unchanged, SCRIPT RULE kept.** Validate with a real Sarvam v3 synth + round-trip STT on "Codename Joy 3.0 / 2 BHK / book / confirm" BEFORE restart. Keep STT, MLV mirror, FINAL LANG LOCK, RAG flags intact. Do NOT revert 69374eb. Earner untouched.

---

## Phase: SURGERY — apply minimal restore (Option A: bulbul:v3 + valid v3 speaker)

**Date:** 2026-06-14 · BUILD+DEPLOY · `.env`-ONLY change · aim-voice-agent restarted ONLY · earner UNTOUCHED.

### WHAT WAS BROKEN (confirmed live, not assumed)
- Box `.env` had NO `SARVAM_TTS_MODEL` / `SARVAM_TTS_SPEAKER` → code defaults `bulbul:v2` + `anushka` were live.
- `INBOUND_PROV_LOCK=1` set in systemd `aim-voice-agent.service` `Environment=` line (confirmed via `systemctl cat`); CTX_CACHE=1 + VENDOR_SCRIPT_INJECT=1 also there.
- Live journal (last call 15:20 UTC) confirmed `model=bulbul:v2 speaker=anushka` constructed on the founder's Sarvam-routed campaign.

### OBJECTIVE VALIDATION BEFORE RESTART (real Sarvam synth + saarika round-trip STT, capsy venv, keys read at runtime from .env, never hardcoded)
Test phrase: `आपके ₹2 करोड़ के budget में 2 BHK Codename Joy 3.0 available है। आप book और confirm कर सकते हैं।`
- **v2 anushka (broken, current):** STT → `...टू उसाई हुड नेमो 3.0...` — "2 BHK"→"टू उसाई", "Codename Joy"→"हुड नेमो", ₹2 dropped. GARBLED (matches founder's complaint).
- **v3 (every speaker tested priya/neha/kavya/ishita/shreya/simran):** STT → `...दो बीएचके कोड नेम जॉय 3.0 अवेलेबल है। आप बुक और कंफर्म कर सकते हैं।` — "BHK"→"बीएचके" (correct spell-out), "Codename Joy"→"कोड नेम जॉय" (correct), book/confirm→बुक/कंफर्म (correct), full ₹2 करोड़ preserved. **GARBLING GONE.**
- Authoritative v3 speaker list returned by API (anushka/manisha/vidya/arya/karun/hitesh/abhilash are v2-ONLY): aditya, ritu, ashutosh, priya, neha, rahul, pooja, rohan, simran, kavya, amit, dev, ishita, shreya, ratan, varun, manan, sumit, roopa, kabir, aayan, shubh, advait, anand, tanya, tarun, sunny, mani, gokul, vijay, shruti, suhani, mohit, kavitha, rehan, soham, rupali, niharika.
- **Chosen speaker = `priya`** (v3-native conversational female; objectively cleanest brand-name + full-numeric rendering in round-trip; greeting `मैं रिया बोल रही हूँ` clean — only proper-name "Shapoorji Pallonji" phonetically approximate, inherent/acceptable).

### EXACT CHANGE (file:line) — `.env` ONLY, ZERO code
- `/opt/famit-agent/.env` (appended 2 lines, idempotent grep-guard):
  - `SARVAM_TTS_MODEL=bulbul:v3`  (was unset → code default `bulbul:v2`)
  - `SARVAM_TTS_SPEAKER=priya`    (was unset → code default `anushka`, v2-only)
- `SARVAM_TTS_LANG` deliberately NOT set → code default `target_language_code="hi-IN"` UNCHANGED (correct code-mix path; NOT changed).
- Backup: `/opt/famit-agent/.env.SURGbak.20260614-154923` (md5 of pre-edit .env `1a8ffc07`).

### HOW LANGUAGE-AUTO IS SET PER ENGINE (the founder's auto-adaptive intent)
- **Sarvam (live engine for Codename Joy):** Sarvam TTS has NO auto/code-mix enum — the documented auto-adaptive path IS `target_language_code="hi-IN"` + `bulbul:v3` + Devanagari-Hindi+Latin-English input. v3's normalizer natively passes Latin English loan-words through as English phonemes (proven above). So "auto code-mix" = v3 + hi-IN + the SCRIPT RULE's mixed input. No language pin to fight.
- **STT:** saarika `language="unknown"` = full auto-detect (unchanged — round-trips Devanagari + English cleanly).
- **ElevenLabs (dormant, premium tier only):** still `language="hi"` + voice Neha-P. NOT touched this wave (Codename Joy is Sarvam-routed → EL path is dormant, NOT the founder's bad call). Latent EL fix (Hindi-capable voice `zT03pEAEi0VHKciJODfn` + drop `AIM_TTS_LANG=hi`) recorded as a separate gated unit for the premium tier — see P1 below.

### WHAT WAS REVERTED
- **NOTHING reverted.** Per the SURGICAL ROOT CAUSE phase, the SCRIPT RULE (commit `69374eb`) is the documented-correct Bulbul input format and IMPROVES intelligibility on both v2 and v3 — it is KEPT. The break was engine VERSION (v2), not the language pin and not the SCRIPT RULE. The founder's "revert my script rule" was offered as a fork; evidence shows the rule helps, so it stays. MLV mirror + FINAL LANG LOCK + RAG_INJECT_ENABLED + all flags KEPT intact.

### GOLDEN 5/5
- **Auto-PASS / N/A-by-construction:** ZERO edit to `aim_voice_agent.py` (box md5 `1614be09bfc10c8e3d91c2f68ea64e56` UNCHANGED before & after) and ZERO edit to `prompt.py` (`fb87ea56` untouched). `verify_golden.py` re-renders `prompt.build_system_prompt` — with `prompt.py` byte-identical the 5/5 byte-identical result is guaranteed (proven repeatedly in prior phases for the same unchanged file). This wave changed only `.env` knobs, which the golden does not render.

### EARNER GATE (before AND after) = GREEN
- `agent.py` md5 `9150fabe4ff62b4b4470f9a87df346e5` UNCHANGED.
- `famit-agent` MainPID **1477083** active — NOT restarted.
- `aim-voice-agent` restarted ONLY (old PID 2721961 → new PID **2739156**, NRestarts=0, all plugins incl. sarvam registered, "registered worker" agent_name=manager at 15:51:19, zero errors/tracebacks).
- `famit-caller` NOT restarted by me (PID 2739090 pre-existing); `/health` :8208 = 200.
- 0 voice/caller 5xx from this wave. (The single `POST /provider-registry 500` at 15:49:05 is the DORMANT W4 registry endpoint with `PROVIDER_REGISTRY_ENABLED` absent — pre-existing, unrelated to voice, predates my restart.)
- NO ring (no outbound test call placed — founder will test the inbound DID).
- Box scratch (`/tmp/_sarvam_v3_*.py`) cleaned; no Sarvam key ever written to a persisted/committed file.

### ACCEPTANCE = FOUNDER'S REAL INBOUND CALL
Call **+91 80 7158 3488** in Hindi, mention "Codename Joy 3.0 / 2 BHK / book / confirm". Expect: natural Hinglish with English words pronounced correctly (BHK→"बीएचके", Codename Joy→"कोड नेम जॉय", book/confirm clear) — NOT v2 garble ("उसाई"/"हुड नेमो"). English caller mid-call → clean English switch (MLV mirror intact).

### ROLLBACK (instant, if anything sounds worse)
`ssh famit@168.144.153.145 "cd /opt/famit-agent && cp .env.SURGbak.20260614-154923 .env && sudo systemctl restart aim-voice-agent"` (reverts to v2/anushka). Or just remove the 2 SARVAM_TTS_* lines.

### P1 FOLLOW-UP (separate gated unit — NOT this wave)
- Sarvam Pronunciation Dictionary for residual brand-name edge cases (most are already correct on v3) — needs a `_build_tts_sarvam` code edit + `dict_id`.
- EL premium-tier latent fix (Hindi-capable voice + drop `AIM_TTS_LANG=hi`) — dormant, founder-tier-gated.

**STATUS: SURGERY COMPLETE — minimal .env restore deployed (bulbul:v3 + priya), zero code, golden N/A-unchanged, earner GREEN. Awaiting founder real inbound call.**

---

## Phase: VERIFY + FE-DEPLOY — synthesis clips + inbound transcript FE + earner gate + docs

**Date:** 2026-06-14 · BUILD+DEPLOY · famit-panel ONLY restarted (FORTRESS box 143.110.247.249) · aim-voice-agent NOT restarted · earner UNTOUCHED.

### (1) SYNTHESIS VERIFICATION — Sarvam v3/priya round-trip STT PASS

Real Sarvam v3/priya synth + saarika STT (on-box capsy venv, keys from .env, never hardcoded):

**Test phrase:** `आपके ₹2 करोड़ के budget में 2 BHK Codename Joy 3.0 available है। आप book और confirm कर सकते हैं।`
- STT round-trip result: `...दो बीएचके कोड नेम जॉय 3.0 अवेलेबल है। आप बुक और कंफर्म कर सकते हैं।`
- "BHK" → "बीएचके" (correct spell-out) ✓
- "Codename Joy" → "कोड नेम जॉय" (correct) ✓
- "book" → "बुक", "confirm" → "कंफर्म" ✓
- ₹2 करोड़ preserved ✓
- Hindi casual "थोड़ी देर रुकिए" clean ✓

**English sentence test:**
- "We have 2 BHK flats available at Codename Joy 3.0. Would you like to confirm?"
- Round-trip: clean English — no Devanagari bleed-through ✓ (MLV mirror intact)

**v2/anushka (old broken):** "2 BHK"→"टू उसाई", "Codename Joy"→"हुड नेमो" — GARBLED
**v3/priya (deployed):** all terms correct — GARBLING GONE ✓

### (2) FE TRANSCRIPT BUG FIX — /ai-manager/sessions page DEPLOYED to FORTRESS

**Root cause of bug:** `contact_timeline` has 0 rows for inbound calls (aim_voice_agent never writes CRM timeline entries). So CRM page never showed inbound call rows to click. The existing `/ai-manager/sessions/[id]` detail view existed but required navigating via AI Manager → Calls tab.

**Fix shipped:**
- NEW page: `famit-panel/app/ai-manager/sessions/page.tsx` (committed `73054f9` on `fe/unify-run-wavec`)
- Route: `/ai-manager/sessions`
- Shows all inbound sessions list (caller phone avatar+number, started time, duration, status pill, outcome)
- Click row → `TranscriptModal` slide-over: AI-left (b-surface2), customer-right (primary-01/12 tint), spinner
- `fetchTranscript(session_id)` → `GET /api/calls/{session_id}/transcript` (existing endpoint that resolves both outbound+inbound via `_inbound_transcript_turns`)
- `ChatBubble` with per-turn timestamp; empty/error/dormant states all handled

**Build+deploy:**
- Built locally (node v22.11.0 Windows) — box build fails OOM on 2GB panel box
- Full `.next` synced to root@143.110.247.249:/opt/famit-panel/.next/ (4.21MB zip, atomic swap)
- famit-panel restarted (PID 318530 → new PID after restart)
- Verified: `http://localhost:3001/ai-manager/sessions` = 200 ✓
- CF edge: `https://panel.famit.in/ai-manager/sessions` = 200 ✓
- Core routes unchanged: `/crm` = 200, `/ai-manager` = 200 ✓

**Existing flow also works:** AI Manager → Calls tab → session → `/ai-manager/sessions/[id]` (pre-existing; 25 turns visible for session vs_07c19d8f8b0b confirmed via GET).

### (3) GOLDEN 5/5 + EARNER GATE — ALL PASS

**Golden verify (verify_golden.py):** EARNER GATE PASS — 5/5 byte-identical ✓
- aim_voice_agent.py box md5 `1614be09` UNCHANGED (zero code edit this phase) ✓
- prompt.py `fb87ea56` UNCHANGED ✓

**Earner gate PASS (fresh check post-deploy):**
- `agent.py` md5 `9150fabe4ff62b4b4470f9a87df346e5` UNCHANGED ✓
- `famit-agent` MainPID **1477083** NOT restarted ✓
- `/health` port 8209 = 200 ✓
- 0 voice 5xx, NO ring ✓

**STATUS: VERIFY+FE+DEPLOY COMPLETE — synthesis PASS (BHK/Codename Joy clean), /ai-manager/sessions LIVE at CF edge, 5/5 golden PASS, earner GREEN. Founder live-test: call +918071583488 in Hindi → see transcript at panel.famit.in/ai-manager/sessions.**
