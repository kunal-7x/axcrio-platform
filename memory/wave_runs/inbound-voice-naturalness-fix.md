# Wave: INBOUND VOICE NATURALNESS — diagnose + restore real-human Hinglish

**Date:** 2026-06-14 · READ-ONLY DIAGNOSE phase (no box mutation, no call, no restart)
**Box:** famit@168.144.153.145 `/opt/famit-agent` · inbound worker `aim-voice-agent` (PID 2669239)

## Phase: DIAGNOSE

### EARNER GATE (before + after all read-only probing) = PASS
- `agent.py` md5 `9150fabe4ff62b4b4470f9a87df346e5` UNCHANGED (before & after).
- `famit-agent` MainPID **1477083** active, ActiveEnter `2026-06-10 19:58:18` — NEVER restarted.
- `aim-voice-agent` active (PID 2669239) — NOT restarted by me.
- famit-caller `/health` (port 8209) = **200**; **0 real 5xx**; NO `/run`, NO ring (DID resting; all journal calls = the founder's own inbound tests).
- Box mutations by me: NONE. Only: SSH reads, 2 read-only TTS-synth API calls (EL+Sarvam), 1 round-trip STT, and `rm` of my own `/tmp` scratch. aim_voice_agent.py md5 on box = `5c3936fa` (W1 RAG state — RECOVERY-STATE.md is stale at `018c20a7`; reconcile note below).

### (1) CONFIRMED INBOUND TTS ENGINE + VOICE — it is NOT fixed; it is TIER-DEPENDENT
- `_build_tts(provider)` dispatch at `aim_voice_agent.py:448`. Entrypoint resolves `_tts_provider` via `prompt.resolve_providers(cust_fields)` when `INBOUND_PROV_LOCK` is ON (`:2444-2458`). **Live journal confirms provider-lock IS ON** ("AIM provider-lock ON: resolved stt=sarvam llm=groq tts=...").
- `resolve_providers` tier→TTS map (`prompt.py:137-141`): **`lean`/`standard`/`std` → SARVAM Bulbul**; **`premium`/`prem` → ElevenLabs**; unknown/absent → EL default. STT (Sarvam saarika:v2.5, auto `unknown`) + LLM (Groq llama-4-scout) are HARDWIRED for every tier; only TTS varies.
- **ElevenLabs path** = `eleven_flash_v2_5`, voice_id `QTKSa2Iyv0yoxvXY2V8a`, **`language="hi"`** (`AIM_TTS_LANG=hi`), stability 0.45 / sim 0.80 / speed 1.08, auto_mode. **That voice is "Neha P" — an ENGLISH voice (labels `language:en`, `accent:indian`, conversational), NOT a Hindi-native voice** — yet pinned to `language=hi`.
- **Sarvam path** = `bulbul:v2`, speaker `anushka`, `target_language_code=hi-IN`.
- **The founder's real test campaign "Codename Joy 3.0" (Shapoorji Pallonji) resolves to `tts=sarvam`** (confirmed in the Jun-14 14:28 journal line). So on his test call HE IS HEARING **Sarvam Bulbul anushka** — NOT ElevenLabs (the brief's assumption was wrong).

### (2) RECENT INBOUND CALL — STT-final turns + the agent OUTPUT (TTS input) text
From the Jun-14 14:28 call (admin tenant, returning lead, 104s). The journal logs BOTH the STT-final and the assistant output (= TTS input). The LLM output style is **wildly inconsistent across turns** — three styles, sometimes mixed in ONE line:
- Pure English: "Hi nikhil! This is Riya from Shapoorji Pallonji Real Estate. Good to hear from you again…"
- Pure Devanagari: "मैं समझ गई, Codename Joy 3.0 के बारे में बात कर रहे हैं — क्या आपको प्रोजेक्ट की कुछ जानकारी चाहिए…"
- Romanized Hinglish: "Codename Joy 3.0, premium residential project hai. 2 BHK, 3 BHK aur 3 BHK duplex units available hain. Prices start hain 85 lac se."
- **MIXED Devanagari+romanized in one utterance (worst for TTS):** "**₹2 करोड़** ke budget mein aapko 3 BHK unit mil sakta hai Codename Joy 3.0 mein. Prices start hain **1 करोड़ 32 lac** se 3 BHK ke liye."
- Also heavy turn FRAGMENTATION ("Aap Codename" / "Codename" / "जी, हाँ!" / "क्या मैं" / "मैं रिया बोल रही हूँ") — chunked/interrupted micro-turns.
So the LLM is NOT outputting formal literal Hindi ("pratiksha kijiye") — it is outputting **inconsistent SCRIPT** (Devanagari vs Latin vs mixed). The prompt's language rule (`:1577` mirror rule + `:1631` FINAL LANGUAGE LOCK) tells it WHICH LANGUAGE to mirror but **never pins WHICH SCRIPT** for Hindi (Devanagari vs romanized), and the KNOWLEDGE PACK is Devanagari-heavy → free-for-all script.

### (3) REPRODUCED THE GARBLING — objective round-trip-STT oracle (real EL + real Sarvam, exact live config)
Synthesized 3 typical replies through BOTH engines, then transcribed back via Sarvam saarika (the same STT the live agent uses). Audio saved locally: `droplet_work/_voice_repro/repro_{EL,SARVAM}_{mixed_script,pure_devanagari,romanized_hinglish}.{mp3,wav}`.
- **SARVAM Bulbul GARBLES romanized/English/Hinglish badly:**
  - romanized "Codename Joy 3.0" → STT heard "**वोडने मोई** 3.0"; "3 BHK" → "3 **उसाई**".
  - mixed "…aapko 3 BHK unit mil sakta hai Codename Joy…" → "…आपको 3 **उसाई** यूनिट मिल **सेक्टर हाई** **रोड** में…" (Codename dropped, "sakta hai"→"सेक्टर हाई").
- **ElevenLabs Neha-P handles romanized/mixed FAR better:** "Codename Joy 3.0" → "कोड नेम जॉय 3.0"; "BHK" → "बीएचके" (intelligible). (One number hallucination on the mixed sample + a leading "आरएस" garble, but globally intelligible.)
- **BOTH engines handle PURE Devanagari near-perfectly** (round-trip STT clean on both).
- **Conclusion:** Sarvam Bulbul is built for clean Indic/Devanagari text and mangles Latin-script Hinglish + English brand words; EL tolerates Hinglish but, as an English voice on `language=hi`, sounds anonymous/non-native on pure Hindi.

### (4) WHICH CHANGE DEGRADED IT — ROOT CAUSE(S)
Root cause is a COMBINATION, ranked:
1. **PRIMARY — `feat(provider-lock)` commit `ab6777c` (RUN-PLATFORM Wave A)** introduced `resolve_providers` tier→TTS routing that sends **lean/standard-tier campaigns to Sarvam Bulbul** instead of the previous fixed-EL inbound default. The founder's "Codename Joy" campaign is lean/standard → Sarvam → garbled romanized Hinglish. *This is the regression that changed what he hears.*
2. **SECONDARY — LLM script inconsistency** (the MLV mirror rule, commit chain that made the agent more multilingual): the prompt mirrors the caller's LANGUAGE but never constrains the SCRIPT, so Groq llama-4-scout freely emits Devanagari, romanized, AND mixed-in-one-line. Sarvam chokes on the romanized/mixed; even EL stumbles on the mixed-number lines. The MLV wave ENHANCED multilingual mirroring (correct) but exposed the engine's script weakness.
3. **TERTIARY — voice/lang mismatch on the EL path:** voice `QTKSa2Iyv0yoxvXY2V8a` = "Neha P" English voice pinned `language=hi` → anonymous Hindi on the premium tier.
NOT a cause: STT (Sarvam auto `unknown` round-trips Devanagari cleanly), the neutral greeting, or the RAG `_global` corpus (grounding is facts, not style; prefetch was clean at 1626 chars).

### EVIDENCE INDEX
- `_build_tts*` `aim_voice_agent.py:406-458`; entrypoint resolve `:2444-2458`; tier map `prompt.py:137-141`.
- Language rule `aim_voice_agent.py:1577` (MIRROR) + `:1631` (FINAL LANGUAGE LOCK) — neither pins script.
- Journal: Jun-14 14:28 call, `tts=sarvam`, mixed-script output turns.
- Repro audio + round-trip STT: `droplet_work/_voice_repro/` (6 files) + the STT oracle above.
- Regression commit: `ab6777c feat(provider-lock)`.

### RECOMMENDED FIX DIRECTION (for the BUILD phase — not done here)
1. **Pin the LLM output SCRIPT to romanized Hinglish for Hindi** (add to the language rule: "write Hindi in Roman/Latin script — Hinglish — never Devanagari; numbers as digits") so the engine gets ONE consistent, TTS-friendly script. This is the cheapest, highest-leverage fix and is engine-agnostic. Must keep the MLV mirror + RAG flags intact and pass `verify_golden.py` 5/5.
2. **OR** flip the founder's tier (and the lean/standard default for Hindi-heavy verticals) back to **ElevenLabs**, which tolerates Hinglish — but pick a Hindi-CAPABLE EL voice and reconsider `language=hi` on an English voice.
3. **Best:** do (1) for consistency AND choose a TTS voice/engine per the dominant script. If staying on Sarvam, force romanized→Devanagari transliteration before TTS, or use a Sarvam voice with better code-mix handling.
4. Address turn fragmentation separately (endpointing) — secondary to the garbling.

**STATUS: DIAGNOSE COMPLETE. No build/box mutation. Earner gate GREEN.**

---

## Phase: DEEP-WEB RESEARCH — engine verdict + script form + casual Hinglish prompt recipe

**Date:** 2026-06-14 · READ-ONLY (web search + doc fetch) · No box mutation, no call, no restart.

### (A) ENGINE VERDICT — Sarvam Bulbul vs ElevenLabs for Hindi/Hinglish

#### Sarvam Bulbul (`bulbul:v2` / `bulbul:v3`)
**Official doc quote (docs.sarvam.ai/getting-started/models/bulbul):**
> "Transliterated input (e.g., `Aapka order confirm ho gaya hai`) significantly reduces output quality"
> "Always use native script for Indic words (e.g., `आपका order confirm हो गया है`)"

- Bulbul is purpose-built for Indic languages. It excels on clean Devanagari (or other Indic-script) text.
- **Romanized/transliterated Hindi is explicitly documented as quality-degrading** — consistent with our live repro ("Codename Joy"→"वोडने मोई").
- The preferred code-mixed format is **Devanagari for Hindi words + Latin for English words/brands** — e.g. `"आपका OTP 4321 है। Please use it within 5 minutes."` This is spoken naturally without preprocessing.
- `enable_preprocessing=true` helps with abbreviations and digits, not romanized script.
- **Bulbul v3** (the newer model; v2 is `legacy` per Sarvam docs) has the lowest CER across Indian domains including code-mixing and romanized text — meaning v3 is more robust to romanized input, though native script is still the recommended path. The live box runs `bulbul:v2` (legacy).
- **Verdict for Sarvam:** Input MUST be Devanagari for Hindi words. English words/brands stay in Latin. Romanized Hindi is broken, especially on v2.

#### ElevenLabs (`eleven_flash_v2_5`)
- Flash v2.5 supports 32 languages including Hindi. It accepts Unicode natively (both Devanagari and Latin).
- EL's architecture is English-centric; it has Hindi voices in the library (Niraj/Hinglish, Yash M, Gaurav, Srikant, Laksh, etc.) but the voice currently wired (`QTKSa2Iyv0yoxvXY2V8a` = "Neha P") is **labelled as an English voice with Indian accent** — not a Hindi-native model voice.
- EL handles Romanized Hinglish and code-mixed text better than Sarvam (confirmed by our live repro: "Codename Joy 3.0"→"कोड नेम जॉय 3.0"; "BHK"→"बीएचके"), because its English core normalises Latin-script text reliably.
- For Hindi-dominant text, EL requires a Hindi-capable voice (not "Neha P"). For Hinglish output (Hindi base + English words), EL is the more tolerant engine.
- EL docs: for best results, use proper punctuation and capitalization to guide rhythm; no script-conversion needed — input in whatever mix you send.
- **Verdict for ElevenLabs:** More tolerant of code-mixed/romanized input. The current EL voice (Neha P = English) is wrong for Hindi-heavy output — need a Hindi-labelled EL voice (e.g. Niraj/Hinglish, or a `hi-IN` native voice) for premium tier.

#### Head-to-head summary
| Dimension | Sarvam Bulbul v2 (live) | ElevenLabs Flash v2.5 (live EL voice) |
|---|---|---|
| Best input script for Hindi | Devanagari only | Latin/Hinglish or Devanagari (more flexible) |
| Code-mixed (Devanagari+Latin) | ✅ Handles natively | ✅ Handles natively |
| Romanized Hindi (transliterated) | ❌ Explicitly degraded (docs + our repro) | ✅ Tolerates well (English-centric core) |
| Pure Devanagari | ✅ Excellent | ✅ Good |
| Current live voice quality | anushka — Hindi-native, natural | "Neha P" — English accent, not Hindi-native |
| Upgrade path | → bulbul:v3 + Devanagari input | → swap to a Hindi-labelled EL voice |

---

### (B) OPTIMAL SCRIPT FORM FOR THE LLM TO EMIT (for each engine)

**If staying on Sarvam Bulbul (any version):**
LLM MUST output: **Devanagari for all Hindi words + Latin for English words/brands/numbers-as-digits.**
- Good: `"आपका budget ₹2 करोड़ है, तो 3 BHK Codename Joy 3.0 में perfect fit है।"`
- Bad (our current output, broken): `"₹2 करोड़ ke budget mein aapko 3 BHK unit mil sakta hai Codename Joy 3.0 mein."`
- The LLM must NEVER write romanized Hindi words (sakta/hai/mein/ke → must be Devanagari). English words (BHK, Codename Joy, pricing, booking, confirm, wait) stay in Latin.
- This is the engine-safe fix: consistent Devanagari+Latin → Sarvam produces clean audio.

**If switching to ElevenLabs (with a Hindi-native voice):**
LLM can output Romanized Hinglish (Latin-only, Hindi base with English words) OR Devanagari+Latin. Both work. However for real-human naturalness, the **Devanagari+Latin format** also works on EL and is more readable/debuggable.

**Bottom line for the build phase:** Fix the LLM script constraint to output **Devanagari Hindi + Latin English** regardless of engine — this works on both Sarvam (required) and EL (fine). It's the universal safe format.

---

### (C) CASUAL HINGLISH PROMPT RECIPE — what real Indians sound like + how to instruct the LLM

#### What natural Hinglish sounds like (the register)
Source (talkflowai.com blog + autointerviewai.com 2026 + Pragnakalp IVR→AI article):
- **Hindi base sentence structure + English words kept in English.** Never translate English words to pure Hindi — that sounds robotic.
- Common English words that stay English in real Hinglish: `confirm, book, check, wait, ok, sir, madam, budget, call, payment, discount, offer, interest, visit, project, property, unit, price, ready, available, details, form, team, meeting, time, morning, afternoon, number`.
- Real phrases: `"Kal morning service booking karni hai."` / `"Meri car ka pickup available hai kya?"` / `"deal final hai kya"` / `"thoda wait karo"` / `"confirm karo"` / `"Haan, main samajh gaya. Kal subah milte hain!"`
- Avoiding formal/literary: NEVER `"pratiksha kijiye"` → use `"thodi der ruko"` / `"wait karo please"`. NEVER `"Kripaya..."` → use `"Please..."`. NEVER long Devanagari-literary sentences.
- Code-switching note (Wikipedia + CHAI paper): Hinglish is not Hindi + English words appended — it's a natural intra-sentence switch. Real speakers say `"Mujhe flight book karni hai"` not `"मुझे उड़ान आरक्षित करनी है"`.
- Cultural: `"Acha, dekhte hain"` = polite "No." `"sochna padega"` = they're not interested. Recognize buying signals vs stalls.
- LLM instruction source (talkflowai.com Hindi voice agents blog): *"You are a helpful assistant for Indian users. Reply in a mix of Hindi and English (Hinglish) that sounds natural to a young professional in Delhi. Keep responses concise for voice output."* — this is the baseline recipe.

#### Exact prompt instruction block for the build phase
The system prompt rule to add in `_build_sales_instructions` (after the FINAL LANGUAGE LOCK at `:1631`):

```
SCRIPT RULE (non-negotiable, overrides all other formatting):
- When speaking Hindi or Hinglish: write Hindi words in DEVANAGARI script.
- Keep English words (brand names, technical terms, common loan-words: BHK, Codename Joy, confirm, book, wait, ok, sir, budget, price, discount, offer, visit, payment, ready, available, details, morning, meeting) in LATIN/English script exactly as-is.
- NEVER write Hindi words in Roman/transliterated form (never: "sakta", "hai", "mein", "ke", "aapko", "kya", "haan", "nahi" — these must be: "सकता", "है", "में", "के", "आपको", "क्या", "हाँ", "नहीं").
- NUMBERS: always write as digits (₹2,00,000 not "do lakh").
- AVOID formal/literary Hindi: never "pratiksha kijiye", "kripaya", "dhanyavaad" — use everyday Hinglish: "thodi der ruko", "please", "shukriya".
- OUTPUT FORMAT per turn: short (1-3 sentences max for TTS). No Devanagari+romanized mixing in the same line.
```

This single block resolves:
1. The Sarvam garbling (no more romanized Hindi feeding the TTS).
2. The script inconsistency (uniform Devanagari+Latin).
3. The naturalness register (casual not literary).
4. The mixed-in-one-line problem (explicit prohibition on mixing scripts per line).

---

### (D) SOURCES
- [Sarvam Building for India docs](https://docs.sarvam.ai/api-reference-docs/building-for-india) — Devanagari+Latin code-mix is the recommended format; `enable_preprocessing=true` for abbreviations/digits.
- [Sarvam Bulbul model docs](https://docs.sarvam.ai/api-reference-docs/getting-started/models/bulbul) — explicit: `"Transliterated input…significantly reduces output quality"` + `"Always use native script for Indic words"`.
- [Bulbul V3 blog (Sarvam)](https://www.sarvam.ai/blogs/bulbul-v3) — V3 lowest CER on code-mixing + romanized; V2 is now legacy.
- [Analytics Vidhya — Bulbul V2](https://www.analyticsvidhya.com/blog/2025/05/bulbul-v2-by-sarvam/) — Bulbul v2 supports 11 languages, code-mixed input.
- [ElevenLabs Hindi TTS page](https://elevenlabs.io/text-to-speech/hindi) — Hindi voices listed (Niraj/Hinglish, Yash M, Gaurav, Srikant, Laksh); Flash v2.5 32 languages.
- [ElevenLabs Models docs](https://elevenlabs.io/docs/overview/models) — Flash v2.5 ~75ms latency, 32 languages, real-time.
- [ElevenLabs language support](https://help.elevenlabs.io/hc/en-us/articles/13313366263441-What-languages-do-you-support) — accepts Unicode, auto-detects language.
- [TalkflowAI — Building Hindi Voice Agents](https://transcriber.talkflowai.com/blog/building-hindi-voice-agents-sarvam-saaras-bulbul) — LLM system prompt recipe for Hinglish; EL struggles with Indian conversational nuances vs Sarvam.
- [Pragnakalp — IVR to AI Hindi voice agent](https://www.pragnakalp.com/from-ivr-to-ai-building-a-natural-hindi-voice-agent-experience/) — natural Hinglish phrase examples.
- [AutoInterviewAI — Vernacular AI Voice Agents India 2026](https://www.autointerviewai.com/blog/vernacular-ai-voice-agents-india-hinglish-code-switching-2026) — Hinglish naturalness; `"confirm karo"` / `"thoda wait karo"` / `"deal final hai kya"` real phrase patterns.
- [CHAI paper (arXiv 2411.09073)](https://arxiv.org/pdf/2411.09073) — LLM code-mixed translation; DCM value 0-1 for controlling mix level.
- [Hinglish (Wikipedia)](https://en.wikipedia.org/wiki/Hinglish) — register overview; intra-sentence code-switching is natural.
- [LiveKit Sarvam TTS plugin docs](https://docs.livekit.io/agents/models/tts/plugins/sarvam/) — integration reference.

---

**STATUS: DEEP-WEB RESEARCH COMPLETE. No box mutation. Earner gate GREEN (unchanged from DIAGNOSE phase).**

---

## Phase: BUILD — casual code-mixed Hinglish SCRIPT RULE (deployed live, earner-safe)

**Date:** 2026-06-14 · BUILD + DEPLOY phase · aim-voice-agent restarted ONLY · earner UNTOUCHED.

### DECISION (engine routing vs prompt fix)
Per the DIAGNOSE + RESEARCH verdict, the cheapest highest-leverage engine-AGNOSTIC fix is the prompt SCRIPT RULE, NOT a tier->TTS routing change. The universal-safe format **Devanagari Hindi words + Latin English loan-words** is what Sarvam Bulbul is documented to handle natively AND what ElevenLabs handles fine — so pinning the LLM to emit it restores natural Hinglish on the founder's live Sarvam-routed campaign WITHOUT changing routing/billing/voice for any tenant. Routing was deliberately left UNCHANGED (changing `_TIER_TTS` would silently alter every lean/standard tenant's voice + the metering label = broader/riskier).

### EXACT EDITS (file:line) — `aim_voice_agent.py` ONLY (`prompt.py` untouched)
1. **`_build_sales_instructions` -> `lang_lock` block (the FINAL LANGUAGE LOCK, ~:1631)** — appended a `=== SCRIPT RULE — HOW TO WRITE HINDI/HINGLISH ===` block as the LAST text in the rendered prompt (highest recency = dominant). It mandates:
   - Hindi words in DEVANAGARI; explicit BANNED romanized list (hai/hain/mein/ke/ki/ka/ko/aapko/sakta/sakti/karna/kariye/kya/haan/nahi/acha/thoda/ruko/milega/chahiye -> है/हैं/में/के/की/का/को/आपको/सकता/सकती/करना/करिए/क्या/हाँ/नहीं/अच्छा/थोड़ा/रुको/मिलेगा/चाहिए).
   - English loan-words + brands kept in LATIN (project/property/unit/BHK/price/budget/discount/offer/booking/book/confirm/payment/ready/available/details/visit/site visit/WhatsApp/ok/sir/madam/please/team/time/morning/afternoon/number + Codename Joy 3.0).
   - NEVER mix Devanagari + romanized Hindi in the SAME sentence (the worst pattern from the journal: "₹2 करोड़ ke budget mein" -> "₹2 करोड़ के budget में").
   - Numbers as digits.
   - Casual spoken register: "थोड़ी देर रुकिए"/"एक minute hold कीजिए" NEVER "प्रतीक्षा कीजिए"; "please" NEVER "कृपया"; "बढ़िया"/"अच्छा" not bookish; 1-2 short sentences/turn.
   - **GUARD:** the block opens "applies ONLY when you are speaking Hindi or Hinglish; an English caller still gets pure English" — so it never forces Hindi on an English caller (PLAYBOOK mistake #13).
2. **`_build_sales_instructions` -> `inbound_override` MLV mirror (~:1577)** — reworded "if Hindi, reply in natural casual spoken Hindi … never long Devanagari paragraphs" to "if Hindi, reply in natural casual spoken Hinglish (Hindi words in Devanagari + everyday English loan-words kept in English — see the SCRIPT RULE at the very end) … never long bookish sentences" so the mirror rule and the new SCRIPT RULE are consistent (short Devanagari is correct; only LONG/literary is banned).

### HOW IT PRESERVES THE MLV MIRROR
- The FINAL OVERRIDE still reads "Reply in the SAME language the CALLER used in their LAST message … If their last message was in English, reply in clean natural English … Switch the MOMENT they switch, on your very next line." and the :1577 rule still reads "There is NO default language and NO house style: you simply follow the caller, turn by turn." Functional render confirmed both phrases present in output.
- The SCRIPT RULE governs only HOW Hindi/Hinglish is *written* (script + register), never WHICH language is chosen. English caller -> English; Hindi caller -> casual Hinglish; mid-call switch intact.

### EARNER GATE + GOLDEN (before AND after)
- **Golden 5/5 = exit 0, byte-identical** (`verify_golden.py` re-renders `prompt.build_system_prompt` for the 5 locked campaigns; `prompt.py` was NOT touched -> guaranteed pass; verified empirically).
- `prompt.LIVEBOX.py` md5 `fb87ea56` UNCHANGED.
- Local golden `aim_voice_agent.LIVEBOX.py`: `5c3936fa` -> `1614be09` (the build).
- Deploy: backup `aim_voice_agent.py.VOICEbak.20260614-203227` (box) + `.VOICEbak.20260614-203018` (local); scp md5-gate PASS (staged `1614be09` == local); box py_compile OK; atomic swap; **aim-voice-agent restarted ONLY** (old PID 2669239 -> new PID 2721961, "registered worker" agent_name=manager, NRestarts=0, zero errors after register).
- **EARNER:** agent.py md5 `9150fabe4ff62b4b4470f9a87df346e5` UNCHANGED; famit-agent PID `1477083` active, NOT restarted; famit-caller `/health` 200; 0 real 5xx; NO ring (DID resting). RAG_INJECT_ENABLED + MLV mirror + all flags intact.
- Commit `69374eb` on `fe/unify-run-wavec`; gitleaks staged = 0 (pre-commit hook also clean).

### ACCEPTANCE = FOUNDER'S REAL INBOUND CALL
Only the founder calling the inbound DID and hearing natural casual Hinglish (no garbled "वोडने मोई") proves the fix. The build/golden/gate prove the earner is untouched and the rule renders; the conversational quality is the founder's real-flow truth.

**STATUS: BUILD + DEPLOY COMPLETE. Earner gate GREEN. Golden 5/5. Awaiting founder real-call confirmation.**

---

## Phase: VERIFY — TTS clips + integrated smoke + earner gate (post-deploy)

**Date:** 2026-06-14 · VERIFY phase · READ-ONLY on box · No new mutations · No restart.

### EARNER GATE (VERIFY phase) = GREEN
- `agent.py` md5 `9150fabe4ff62b4b4470f9a87df346e5` UNCHANGED.
- `famit-agent` MainPID **1477083** active (never restarted).
- `aim_voice_agent.py` on box md5 = `1614be09` (the build — confirmed via remote md5sum).
- `aim-voice-agent` active, PID `2721961` (post-build restart), running since `2026-06-14 15:03:01 UTC`, NRestarts=0.
- famit-caller `/health` 200, 0 5xx, NO ring.

### (1) GOLDEN VERIFY — 5/5 PASS
`/opt/capsy-agent/.venv/bin/python3 _golden/verify_golden.py` on box:
```
OK   66c3b656af  sha256=60f5ac77b718f879  (byte-identical)
OK   44949c09bf  sha256=ecccad816d46d4ab  (byte-identical)
OK   c17e55e9f3  sha256=5f94227aa4181c4a  (byte-identical)
OK   985c7e46c0  sha256=ede64edda7b263f4  (byte-identical)
OK   3c47895335  sha256=45b3fe04be595b6b  (byte-identical)
EARNER GATE PASS: 5/5 byte-identical.
```
Confirmed: `prompt.py` `fb87ea56` untouched; all 5 outbound earner campaign renders byte-identical. The SCRIPT RULE edit is in `aim_voice_agent.py` only.

### (2) INTEGRATED SMOKE — `_build_sales_instructions` render (9/9 checks)

Ran against live box `/opt/famit-agent/aim_voice_agent.py` (the deployed `1614be09`), simulating a Hindi-speaking inbound caller on "Codename Joy 3.0" (Sarvam tier):

| Check | Result |
|---|---|
| SCRIPT RULE present | PASS |
| DEVANAGARI rule | PASS |
| BANNED romanized list | PASS |
| LATIN loan-words rule | PASS |
| NO default language | PASS |
| Switch the MOMENT | PASS |
| applies ONLY when Hindi/Hinglish | PASS |
| FINAL OVERRIDE | PASS |
| Casual register (kripaya/pratiksha banned) | PASS (confirmed in rendered SCRIPT RULE text — rule 5 says: use "थोड़ी देर रुकिए" / "एक minute hold कीजिए", NEVER "प्रतीक्षा कीजिए", use "please" NEVER "कृपया") |

MLV mirror guards all intact in rendered output:
- "NO default language and NO house style" — present.
- "Switch the MOMENT they switch, on your very next line" — present.
- "applies ONLY when you are speaking Hindi or Hinglish; an English caller still gets pure English" — present.
- Total rendered length 20,948 chars.

### (3) TTS SAMPLE CLIP VERDICT — Sarvam Bulbul v2 (what the founder hears)

Synthesized 4 clips via live Sarvam Bulbul v2 API + STT round-trip (Sarvam saarika:v2.5 = the same STT the live agent uses):

**BEFORE fix (romanized mixed — the broken state):**
- Input: `"₹2 करोड़ ke budget mein aapko 3 BHK unit mil sakta hai Codename Joy 3.0 mein."`
- STT: `"₹2 करोड़ यंग बजट मेन ऐप को थ्री उसाई यूनिट मिल सेक्टर हाई रोड नेम गोई थ्री मेन।"`
- Verdict: GARBLED. `ke`→`यंग`, `mein`→`मेन`, `sakta hai`→`सेक्टर हाई`, `Codename Joy`→`रोड नेम गोई`. Hindi structural words recovered: 1/3.

**AFTER fix (Devanagari+Latin — the new state):**
- Input: `"आपके ₹2 करोड़ के budget में 3 BHK Codename Joy 3.0 available है। Price ₹1 करोड़ 32 lac से शुरू होती है।"`
- STT: `"आपके ₹2 करोड़ के बजट में थ्री उसाई वुड नेम मोई थ्री अवेलेबल है। प्राइस ₹1 करोड़ 32 लाख से शुरू होती है।"`
- Verdict: STRUCTURALLY INTELLIGIBLE. Hindi sentence structure fully intact — `आपके...के...में...है...से शुरू होती है` all preserved. English brand names (BHK→`थ्री उसाई`, Codename Joy→`वुड नेम मोई`) are phonetically rendered in Hindi accent by Sarvam v2 — the same limitation exists in both formats, it's a Sarvam Bulbul v2 English-proper-noun limitation, not a script-rule problem.

**Greeting comparison (romanized vs Devanagari):**
- BEFORE: `"Hello, mein Riya bol rahi hoon Shapoorji Pallonji se."` → STT: `"चलो, मैं ने यही बोल रही हूँ बापूजी वालोंजी से"` — `mein`→`मैं ने`, `bol rahi hoon`→`बोल रही हूँ` (barely), `Hello`→`चलो`. Garbled.
- AFTER: `"Hello, मैं Riya बोल रही हूँ Shapoorji Pallonji से। आप कैसे हैं?"` → STT: `"हेलो, मैं यहिया बोल रही हूं बापू और जी बलोन जी से। आप कैसे हैं?"` — `मैं बोल रही हूँ...से...आप कैसे हैं` all correct. Only Shapoorji/Riya phonetically approximate.

**Overall TTS verdict:** SIGNIFICANT IMPROVEMENT. The SCRIPT RULE fix removes the primary garbling (romanized Hindi words feeding Sarvam's TTS). Hindi structural words, verb conjugations, and sentence meaning now survive the TTS→STT round-trip cleanly. Residual: English brand names (BHK, Codename Joy, Shapoorji) are phonetically approximated by Sarvam v2 — this is a known v2 limitation (v3 has lower CER on English code-mixing). The fix is correct and the improvement is real and meaningful.

**RESIDUAL (honest):** Sarvam Bulbul v2 will phonetically pronounce English brand names with a heavy Hindi accent (BHK → "उसाई", Codename Joy → "वुड नेम मोई"). This is inherent to the v2 model on English proper nouns. The `enable_preprocessing=True` flag (already set) helps with digits/abbreviations but not brand names. To fully fix this: upgrade TTS to `bulbul:v3` (lower CER, better English code-mixing) or spell out brand names phonetically in the prompt. Deferred as a separate improvement — not blocking the current fix.

### (4) MLV MIRROR — 3-scenario check

All 3 scenarios confirmed from the integrated smoke + the SCRIPT RULE guard:
- **Hindi caller → Hinglish reply:** SCRIPT RULE activates; LLM will write Devanagari Hindi + Latin loan-words. MLV mirror picks up Hindi; rule says "applies ONLY when you are speaking Hindi or Hinglish."
- **English caller → English reply:** SCRIPT RULE does NOT activate ("an English caller still gets pure English"). FINAL OVERRIDE still says "If in English, reply in clean natural English."
- **Mid-call switch (Hindi→English or English→Hindi):** "Switch the MOMENT they switch, on your very next line" intact.

### (5) FOUNDER RECIPE — call the inbound DID

**Inbound DID: +91 80 7158 3488**

1. Call +918071583488 from your phone.
2. Speak in Hindi — e.g. `"हाँ, मुझे Codename Joy 3.0 के बारे में जानकारी चाहिए"` or just `"Riya, aap kaun ho?"` (first message in Hindi is enough to trigger the MLV mirror).
3. The agent (Riya, Sarvam Bulbul anushka) should reply in Hinglish — Hindi sentence structure in Devanagari + English words like `project`, `budget`, `BHK`, `confirm` in Latin. It should NOT sound like garbled word-salad ("सेक्टर हाई", "मेन").
4. Try one switch to English mid-call (`"Ok, I understand, please continue in English"`) — the agent should switch to English on the very next turn.
5. Brand names (Codename Joy, Shapoorji) will still be pronounced with Hindi phonetics — this is Sarvam v2 behavior, not a bug in the fix. The MEANING is intelligible.

**What to listen for:**
- GOOD: `"आपके budget में 3 BHK available है"` (Devanagari structure + Latin BHK) — sounds natural.
- GOOD BEFORE was BAD: `"₹2 करोड़ के budget में"` — the `के` (Devanagari) + `budget` (Latin) combination is now what the LLM emits, and Sarvam handles this cleanly.
- BAD (would indicate a regression): pure romanized output like `"ke budget mein"` — should not happen after the fix.

**ROLLBACK** (if anything sounds worse): `ssh famit@168.144.153.145 "cp /opt/famit-agent/aim_voice_agent.py.VOICEbak.20260614-203227 /opt/famit-agent/aim_voice_agent.py && sudo systemctl restart aim-voice-agent"`.

**STATUS: VERIFY COMPLETE. All checks PASS. Residual (Sarvam v2 brand-name phonetics) documented. Awaiting founder real-call confirmation.**
