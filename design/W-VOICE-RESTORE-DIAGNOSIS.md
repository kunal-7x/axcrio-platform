# W-VOICE-RESTORE — DIAGNOSIS (read-only, doc-only)

**Date:** 2026-06-18
**Box:** `famit@168.144.153.145` (`/opt/famit-agent/`)
**Verified live state:** `agent.py` md5 `98655dbf` · `prompt.py` md5 `fb87ea56` · `KERNEL_OUTBOUND` UNSET (no drop-in active)
**Decision being executed:** roll the OUTBOUND earner back to the PERFECT old worker — keep the VOICE PATH 100% untouched, upgrade ONLY the BRAIN, remove "AI assistant" with a MINIMAL change.

> SCOPE: this file is a diagnosis only. It does NOT mutate the box, edit any `.py`, deploy, or rebuild. It separates what is VOICE (keep byte-identical) from what is BRAIN (safe to upgrade), and names the ONE true remaining problem.

---

## 0. TL;DR (the verdict in five lines)

1. The old worker's VOICE PATH (TTS prosody, STT, LLM construct, endpointing/VAD, opener delivery, language-mirror) is **PERFECT and is already what `98655dbf` contains byte-identical.** The month of fixes (anonymous/garbled voice, loud/inconsistent pace+loudness, repeated-username, latency) all live in this exact file's constructor defaults.
2. My cutover changed things that **should NOT have been touched**: (a) the prosody drop-in / env overrides (`EL_STABILITY=0.55`), (b) opener-suppression env (`OPENER_ALREADY_SAID=1`, `OPENER_IN_CTX=0`), (c) Unit-A opener/ex_role/disclosure prompt edits, (d) the KERNEL_OUTBOUND drop-in that replaced the voice path wholesale.
3. The rollback to **code `98655dbf` / `fb87ea56` with NO drop-in (`KERNEL_OUTBOUND=0`)** restores the perfect voice PATH — **EXCEPT** the `.env` still carries three of my overrides (`EL_STABILITY=0.55`, `OPENER_ALREADY_SAID=1`, `OPENER_IN_CTX=0`) that the OLD perfect build NEVER had. **To be byte-faithful to the perfect voice, those three env lines must be removed so the code DEFAULTS take over** (`EL_STABILITY` → `0.45`, `OPENER_IN_CTX` → `1`, `OPENER_ALREADY_SAID` → off).
4. The ONE true remaining problem is the **BRAIN** (conversation logic / system prompt) — NOT the voice. Plus one cosmetic string: the hardcoded **"AI assistant"** disclosure fallback (`agent.py:218`).
5. The founder's required greeting pattern ("good morning / greetings from <Company>, am I speaking with Mr/Ms ___?" → WAIT → reason+permission → proceed) is **ALREADY present, learned not hardcoded**, in `prompt.py:308-310`. Keep it; the brain upgrade refines it, it does not invent it.

---

## 1. CONFIRMED — the old worker's VOICE PATH is perfect, and `98655dbf` IS that voice path

Every voice-path knob below was read live from `98655dbf` and matches the documented "perfect" baseline byte-for-byte. These are the mechanics that the month of fixes produced. **DO NOT TOUCH ANY OF THESE.**

| Concern (what was broken → fixed) | Mechanism in `98655dbf` | file:line | Default value (the fix) |
|---|---|---|---|
| Anonymous/garbled voice | ElevenLabs voice_id pinned | `agent.py:565` | `QTKSa2Iyv0yoxvXY2V8a` |
| Garbled Hinglish transcription | Sarvam STT language auto-detect | `agent.py:599` | `language="unknown"` (NOT `hi-IN`) |
| Loud / inconsistent loudness | speaker_boost off, style=0 | `agent.py:574-575` | `style=0.0`, `use_speaker_boost=False` |
| Inconsistent/flat expressiveness | low stability = expressive | `agent.py:572` | **`EL_STABILITY` default `0.45`** |
| Voice timbre consistency | similarity boost | `agent.py:573` | `EL_SIMILARITY` default `0.80` |
| Unnaturally slow pace (~18s opener) | speed bump | `agent.py:579` | **`EL_SPEED` default `1.08`** |
| First-audio latency | sentence streaming + flash model | `agent.py:566,581` | `eleven_flash_v2_5`, `auto_mode=True` |
| 3-4 sentence monologues | token cap | `agent.py:617` | `max_completion_tokens=90` |
| Brain model | Groq llama-4-scout | `agent.py:603` | `meta-llama/llama-4-scout-17b-16e-instruct`, temp `0.3` |
| High latency (~6s endpointing) | endpointing window | `agent.py:623-624` | `MIN_EP_DELAY 0.25` / `MAX_EP_DELAY 0.45` |
| 3s start delay | AEC warmup removed | `agent.py:625` | `aec_warmup_duration=0.0` |
| Can't barge-in | interruption window | `agent.py:628-629` | `min_interruption_duration=0.25`, `false_interruption_timeout=1.0` |
| Heavy turn model latency | fast VAD | `agent.py:630` | `turn_detection="vad"` |
| Pre-gen speedup | preemptive generation | `agent.py:622` | `preemptive_generation=True` |
| Opener delivery (not an LLM turn) | `session.say()` | `agent.py:884` | `say(opener, allow_interruptions=True, add_to_chat_ctx=_opener_in_ctx)` |
| Per-turn 2.5s TTFT spikes | cache-safe one-line language mirror | `agent.py` `_MirrorAgent` / `_apply_language_switch` | system prompt written ONCE, TTS-only nudge |

**Conclusion:** the voice PATH is not something to rebuild — it already IS `98655dbf`. The rollback's whole job is to make the LIVE behavior equal to running this file with its CODE DEFAULTS.

---

## 2. CONFIRMED — exactly what my changes touched that should NOT have been

These are the four mistakes. Two are inert after the code rollback; **two survive in the live `.env` and still alter the perfect voice.**

### 2a. Prosody drop-in / env override — STILL ACTIVE, must be reverted
- **`EL_STABILITY=0.55`** is set in the live `/opt/famit-agent/.env`.
- **Proof it is a regression:** I traced EL_STABILITY across **all 43** `.env.*bak*` backups going back to the original working build (`.env.bak.vobizact`, the v3-era voice). **NONE of them set `EL_STABILITY` at all.** The old perfect voice therefore ran on the **code default `0.45`**. My `0.55` is a *higher* stability = *less* expressive = flatter voice than the perfect build. This is the prosody change the founder felt.
- **EL_SPEED:** never set in any backup either → old build ran on code default `1.08` (already the fix). Live `.env` does NOT set EL_SPEED → currently correct. Leave it unset.
- **FIX:** delete the `EL_STABILITY=0.55` line from `.env` so the code default `0.45` is used. (Brain-wave action, not done here.)

### 2b. Opener-suppression env — STILL ACTIVE, must be reverted to match old build
- Live `.env` sets **`OPENER_ALREADY_SAID=1`** and **`OPENER_IN_CTX=0`**.
- **Proof it is new:** neither var appears in ANY of the 43 backups. The old perfect build ran with both UNSET → code defaults: `OPENER_IN_CTX` default `"1"` (`agent.py:883`), `OPENER_ALREADY_SAID` default `"0"` (`agent.py:451`).
- These were my anti-double-greeting / anti-repeated-name fix for the KERNEL brain. They are coupled to the kernel system prompt. With the brain rolled back, keeping them changes opener/turn-1 behavior away from the perfect build.
- **FIX:** delete both lines from `.env` to return to the old build's defaults. (Re-evaluate during the brain upgrade — see §5.)

### 2c. Unit-A opener / ex_role / disclosure prompt edits — INERT after code rollback
- The Unit-A edits (ElevenLabs default bumps, `ex_role`/opener wording, the `OPENER_ALREADY_SAID` gating) lived in the pre-rollback file `agent.py.bak.20260615-180938` (md5 `9150fabe`). The live file is `98655dbf`, which is the curated perfect-voice file — these source edits are **already gone** from the live `.py`. No action on code; only the matching `.env` lines in §2a/§2b remain.

### 2d. KERNEL_OUTBOUND drop-in (replaced the voice path) — INERT, confirmed off
- The drop-in was the worst mistake: it swapped in a kernel worker whose own voice path / opener / prosody overrode the perfect one. `grep KERNEL_OUTBOUND` in the live `agent.py` returns **nothing**, and the env does not set it → **no drop-in is active.** The live worker is the plain `98655dbf`. Correct. Keep `KERNEL_OUTBOUND=0` (i.e. unset).

---

## 3. CONFIRMED — the rollback restores the perfect voice (with one caveat)

- **Code:** live `agent.py`=`98655dbf`, `prompt.py`=`fb87ea56`, no drop-in. This IS the perfect-voice code. ✅
- **Caveat (the gap the rollback alone does NOT close):** the perfect voice is a function of *code defaults*, and the live `.env` overrides three of them (§2a/§2b). **A pure code rollback is necessary but not sufficient** — the live behavior is byte-faithful to the perfect build ONLY after these three `.env` lines are removed:
  - `EL_STABILITY=0.55`  → remove → code default `0.45`
  - `OPENER_ALREADY_SAID=1` → remove → code default off
  - `OPENER_IN_CTX=0` → remove → code default `1`
- **LANG_MIRROR_V2=1 / LANG_MIRROR_FLOOR=0.30:** also not in old backups, but these are the *language-mirror* (a brain/behavior concern, not the TTS prosody the founder complained about) and are documented as a cache-safe improvement. NOT part of the voice-quality regression. Decision deferred to the brain wave; default-safe to leave OR remove. Flagged, not load-bearing for "perfect voice".
- After those three env removals + restart, the live voice equals the perfect old worker. ✅

---

## 4. ISOLATED — the ONE true remaining problem = the BRAIN

The voice was never the real problem after the month of fixes — the founder said the only remaining issue was the BRAIN (conversation logic). The brain is upgradeable WITHOUT touching the voice path because of the clean split below. The W1–W7 kernel intelligence should be folded into the **system prompt / context only**, never the voice constructors.

### 4a. The one cosmetic string: "AI assistant"
- **Location:** `agent.py:218` — `disc_phrase = (disclosure_phrase or f"{company} की एक AI assistant").strip()`, consumed at `:231-232` inside `_llm_opener`'s sysmsg ("तुम {disc_phrase} हो").
- **Behavior in evidence:** the LLM adopted "AI assistant" verbatim in openers AND volunteered it mid-call ("Shapoorji Pallonji Real Estate की AI assistant बोल रही हूँ"). 710 historical occurrences in the journal.
- **Current live openers (Jun 18) no longer say it** because the live campaigns pass an empty/own disclosure, so the fallback isn't hit — but the hardcoded fallback is still a latent landmine for any campaign without its own `ai_disclosure`.
- **MINIMAL fix (brain wave, not done here):** change ONLY the fallback string at `agent.py:218` (e.g. to a neutral company affiliation, or empty so no AI label is volunteered) and/or the `disc_clause` wording at `:231-232`. This is a one-line surgical change inside the BRAIN region — it does NOT touch any voice constructor.

### 4b. The founder's greeting PATTERN is already present (learned, not hardcoded)
- **Location:** `prompt.py:308-310` (the proven human-telecaller flow):
  - Step 1: "गर्मजोशी से greet (नमस्ते / good morning) + {company} का नाम, फिर naam confirm करो — क्या मैं {lead_name} जी से बात कर रही हूँ? caller के हाँ कहने का WAIT करो।"
  - Step 2: "PERMISSION + one-line reason: मैंने {product} के बारे में call किया था — क्या अभी दो minute बात हो सकती है? फिर रुको।"
- This is **exactly** the founder's pattern: greeting → identity (company) → "am I speaking with Mr/Ms ___?" → **WAIT for confirmation** → reason + permission → proceed. It is parameterized by `{company}`, `{lead_name}`, `{product}` — **learned per campaign, not a hardcoded script.** Keep it; the brain upgrade tunes wording/objection-handling around it.

---

## 5. CLEAN SEPARATION — VOICE (keep byte-identical) vs BRAIN (upgrade)

### VOICE PATH — TOUCH NOTHING (code + the three env defaults)
- `agent.py:563-582` ElevenLabs TTS + VoiceSettings (and its env defaults `EL_STABILITY 0.45`, `EL_SPEED 1.08`, `EL_SIMILARITY 0.80`)
- `agent.py:592-601` Sarvam STT (`language="unknown"`, `saarika:v2.5`)
- `agent.py:602-618` Groq LLM construct (model, temp `0.3`, `max_completion_tokens=90`)
- `agent.py:621-631` AgentSession latency/turn knobs (endpointing, interruption, `turn_detection="vad"`, preemptive)
- `agent.py:_apply_language_switch` / `_MirrorAgent.on_user_turn_completed` (cache-safe language nudge)
- `agent.py:878-884` opener delivery via `session.say(... add_to_chat_ctx=_opener_in_ctx)` + the `OPENER_IN_CTX` default `1`
- `agent.py:451-457` `OPENER_ALREADY_SAID` gating (default off)
- Groq/Sarvam key round-robin machinery
- **`.env` discipline:** to restore the perfect voice, REMOVE `EL_STABILITY=0.55`, `OPENER_ALREADY_SAID=1`, `OPENER_IN_CTX=0` so code defaults apply. Keep `KERNEL_OUTBOUND` unset (no drop-in).

### BRAIN — SAFE TO UPGRADE (prompt/context only, with W1–W7 kernel intelligence)
- `prompt.py`: `SYSTEM_PROMPT`, `build_system_prompt()`, the flow block (`:305-315`+), `SHARED_RULES`, objection/negotiation/closing logic, persona — fold in the W1–W7 kernel intelligence here. KEEP the greeting pattern at `:308-310`.
- `agent.py:218` — the single "AI assistant" fallback string (MINIMAL one-line change).
- `agent.py:231-242` — the `_llm_opener` sysmsg wording (`disc_clause`) — refine the disclosure/identity wording here, NOT the say()/TTS path.
- `agent.py:440-460` — `base_instructions` assembly (system prompt + lead-name note + the OPENER_ALREADY_SAID injection text) — brain text only.

---

## 6. ACTION ITEMS for the BRAIN wave (recorded, NOT executed here)

1. **Pure rollback already in place** (code `98655dbf`/`fb87ea56`, no drop-in) — ✅ verified live.
2. **Remove three `.env` overrides** so the perfect voice defaults apply: `EL_STABILITY=0.55`, `OPENER_ALREADY_SAID=1`, `OPENER_IN_CTX=0`. (Re-test the opener double-greet with the rolled-back brain; if the brain-only build still double-greets, prefer fixing it IN THE PROMPT, not by re-introducing the env overrides.)
3. **Decide LANG_MIRROR_V2/FLOOR:** keep (language behavior, not prosody) or remove for strict parity — non-load-bearing for "perfect voice".
4. **MINIMAL "AI assistant" removal:** change ONLY `agent.py:218` fallback (and optionally `:231-232` wording). One line. No voice constructor touched.
5. **Upgrade the BRAIN** with W1–W7 kernel intelligence inside `prompt.py` only, preserving the greeting pattern at `prompt.py:308-310`.
6. **Earner-gate:** one box-mutating change at a time; real outbound call rings + voice subjectively matches the perfect build BEFORE and AFTER; immediate revert path (`.env`/`.py` backups already present on box).
