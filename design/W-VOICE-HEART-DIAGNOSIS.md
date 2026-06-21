# W-VOICE-HEART-DIAGNOSIS — why INBOUND felt human and OUTBOUND is a scripted bot

> READ-ONLY DIAGNOSIS. No box mutation. Branch `fix/callback-retry-scheduling`.
> EARNER LAW: the OUTBOUND earner is `droplet_work/agent.py` (box md5 `98655dbf`,
> local working copy `6c577b9b`). Nothing here is deployed; this is the root-cause
> map + the exact surgical fix plan + the CONSTANT prosody values derived from the
> GOOD inbound voice.

---

## 0. The one-sentence verdict

The founder loved INBOUND because **the LLM brain owns the entire call and the
TTS is a single, low-stability, constant voice** — the greeting is one short
spoken line that the LLM never sees, the name is never injected, and there is no
hardcoded opener/closer to collide with the model. OUTBOUND is a scripted bot
because **two layers speak**: the old worker SPEAKS a hardcoded/Groq-built opener
via `session.say()` AND a hardcoded `_goodbye_line()` close, while the LLM
independently greets and closes on top of them — and the worker injects the
lead-name into the opener + every-turn prompt at a higher, more variable TTS
stability (0.65 vs 0.45). **The brain-only kernel patch (A+B+C) does NOT fix
this** — it swaps only the system prompt and DELIBERATELY leaves the spoken
opener (`session.say`) and the spoken close in place (Patches D/E/F/G omitted).
To get the inbound feel on outbound, the kernel must own greeting + conversation
+ closing as ONE LLM voice, the worker's hardcoded opener/closer must be
suppressed when the kernel is on, and the TTS must be pinned to the inbound
constants.

---

## 1. The GOOD inbound — structural reasons it sounds human

Source: `_inbound_ref/aim_voice_agent.LIVE.py` (the call the founder loved).

| Property | Inbound mechanism (file:line) | Why it reads human |
|---|---|---|
| **Single greeting, never re-greets** | `:576-581` — greeting is a fixed Python f-string spoken via `transport.speak(_greeting)` BEFORE the LLM session is handed control. The greeting text **never enters the LLM chat context**. | The model picks up from turn 1 as a blank slate. A second greeting is *structurally impossible* — there is no opener turn in the LLM history for it to echo. |
| **Name not injected** | The greeting uses agent/company only (`_agent_voice`, `_company`); the caller's name is **not** placed in the opener or appended to every turn. | The LLM uses the name only when natural (once, if at all). No per-turn "Kumar जी," prefix → normal human rhythm. |
| **LLM drives everything else** | After the greeting the whole session is handed to the LLM/command brain (`:623-640`); no hardcoded mid-call lines, no hardcoded close. | One consistent authored voice; pacing/word-choice come from one source, so it doesn't lurch between "scripted line" and "LLM line". |
| **Constant, low-stability TTS** | `_build_tts()` `:735-750`: `stability=0.45, similarity_boost=0.80, style=0.0, use_speaker_boost=False, speed=1.08, model=eleven_flash_v2_5, voice_id=QTKSa2Iyv0yoxvXY2V8a`. | These are applied identically to every utterance. No per-token emphasis, no style swing. Low stability (0.45) = expressive/human; **constant** across turns = no loudness/pace variability. |
| **Natural Hinglish** | STT `language="unknown"` (`:706`) = code-mix auto-detect, never forced `hi-IN`; the brain replies in the caller's register. | No "Mahatvapurn"-style formal Hindi; matches "हाँ भाई" / English-word Hinglish. |

> NOTE: inbound `LIVE.py` is the **AI-Manager PIN-gated** path (greeting = "say your
> 4-digit PIN"), not a telecaller. What the founder loved is its **voice quality
> and conversational structure**, not its words. The fix ports the *structure +
> prosody*, not the PIN script.

---

## 2. The BAD outbound — the two-speaker collision (root cause)

Source: `droplet_work/agent.py` (local `6c577b9b`; box `98655dbf`).

The outbound call has **TWO things that speak**, and they fight:

1. **The old worker SPEAKS a hardcoded/LLM-built opener.**
   - `_llm_opener()` at `:214` builds an opening line with Groq, injecting
     `name_part = f"{lead_name} जी, "` (`:221`) and telling the model to greet
     by name (`:249`).
   - It is spoken at `:912`: `await session.say(opener, allow_interruptions=True,
     add_to_chat_ctx=_opener_in_ctx)`.
2. **The LLM also greets**, because the system prompt's OPENING/FLOW section tells
   it to greet + confirm identity. The `OPENER_ALREADY_SAID` block (`:475-481`)
   is a **behavioral patch** appended to the system prompt asking the model "you
   already opened, don't re-greet". It is a soft instruction, not a structural
   guarantee — on any turn the model under-weights it, it re-greets → the
   live-proven **double "नमस्ते {name}"**.
3. **The old worker SPEAKS a hardcoded close.** `_goodbye_line()` at `:359` returns
   a fixed string; it is spoken at `:726` `session.say(line, ...)`. `_llm_close()`
   (`:370`, gated `LLM_CLOSE`) generates an LLM close, but `_goodbye_line` remains
   the fallback and the closure is a **separate speech event** that can layer on
   top of an LLM-authored goodbye turn → the "ok perfect" + repeated bye.
4. **The name is injected every turn.** `:466`:
   `base_instructions += "...LEAD NAME ... {lead_name} — opener में इसी naam से
   greet करो।"` The model reads this as license to keep saying the name → "Kumar
   जी," at the head of nearly every assistant turn.
5. **TTS is patched the WRONG way.** `_build_tts()` `:598-605`:
   `stability=0.65` (env default; inbound = 0.45) and `speed=1.0` (inbound =
   1.08). A prior patch RAISED stability to 0.65 to fight "swinging pace/loudness".
   But the swing is **not** caused by low stability — it is caused by the
   LLM-authored name-shouting and the collision of two speakers. Raising stability
   made the voice MORE robotic without removing the actual variability source.

### 2a. Why the brain-only kernel patch does NOT fix it

`design/W-INT-OUTBOUND-PATCH-BRAINONLY.md` applies **only Patches A+B+C** (swap
the system-prompt string via `assemble_outbound_instructions`) and
**deliberately OMITS Patches D/E/F/G** (the voice path). Concretely, with
`KERNEL_OUTBOUND=1` and brain-only:
- `session.say(opener)` at `:912` **still fires** (the worker still speaks the
  hardcoded opener) → double-greet source UNCHANGED.
- `_goodbye_line()` / `session.say(line)` at `:726` **still fires** → hardcoded
  close UNCHANGED.
- `_build_tts()` `stability=0.65` **still applies** (Patch D omitted) → prosody
  UNCHANGED.

So the brain-only patch upgrades the *brief/flow* of the prompt but leaves EVERY
ONE of the founder's six complaints' mechanisms in place. **The fix the founder
is asking for is a SUPERSET of brain-only** — it must touch the spoken
opener/closer mechanics and the TTS constants, which brain-only forbids.

---

## 3. Complaint → root cause → surgical fix (the map)

| # | Founder complaint | Root cause (file:line) | Surgical fix |
|---|---|---|---|
| **1** | Double greeting + double intro ("नमस्ते {name}…" then "main bol rahi hoon…" again) | TWO speakers: hardcoded `session.say(opener)` `agent.py:912` (from `_llm_opener` `:214`) **plus** the LLM re-greeting from the system prompt's OPENING/FLOW; suppression is only a soft prompt clause (`OPENER_ALREADY_SAID` `:475`). | **The kernel owns a SINGLE greeting.** When `KERNEL_OUTBOUND=1`: gate OUT the worker's `session.say(opener)` (do not speak it) and let the LLM produce exactly one greeting authored by the kernel's single `OPENING:` directive. Mirror inbound's structural guarantee — one source greets, never two. (Or, if keeping a spoken opener: speak it via `session.say(..., add_to_chat_ctx=False)` AND remove the OPENING step from the prompt so only one greets. The clean port is: kernel/LLM greets, worker stays silent.) |
| **2** | Hardcoded opener AND hardcoded ending — everything must be LLM-generated | Opener templated in `_llm_opener` `:214`/`:221`/`:249`; close hardcoded in `_goodbye_line` `:359` and spoken at `:726`. | **Kernel/LLM generates BOTH.** Suppress `session.say(opener)` and `_goodbye_line`/`session.say(line)` on the kernel-on path. The greeting and the close become normal LLM turns governed by the kernel's `OPENING:` and a `CLOSING:` directive. Nothing hardcoded is spoken. |
| **3a** | Name repeated every line | `:466` injects "use this naam to greet" into the system prompt every call; the model generalizes it to every turn. | Replace `:466` with a **name-sparingly** rule: "caller's name is X; use it AT MOST once, naturally, never as a per-turn prefix; do NOT repeat it." The kernel `OPENING:` directive names once; the conversation rule forbids repetition. |
| **3b** | Name too LOUD + too fast (per-token emphasis on the name) | The name lives in the spoken-opener path at a higher, more expressive TTS state, and EL with variable stability adds emphasis on injected tokens. | **Constant prosody + no name in a special speech event.** Pin TTS to the inbound constants (§4) so there is NO per-token loudness/speed variation; with the name no longer in a separate `session.say` opener, it is spoken as ordinary in-sentence text at the same constant prosody as everything else. |
| **4** | "Mahatvapurn" / too-formal Hindi instead of natural Hinglish | Older worker prompt over-formalized; STT/brain register drifts formal. | **Natural Hinglish from the kernel brain + inbound style.** STT `language="unknown"` (already inbound's setting, `:706`) — never force `hi-IN`. Kernel prompt mandates बोलचाल/conversational Hinglish (mirror caller register), explicitly banning formal-register words like "महत्वपूर्ण". Use the inbound brain's natural-Hinglish directive. |
| **5** | Sounds like a scripted bot, not a human | The two-speaker collision + hardcoded lines + name-every-turn = the model lurches between scripted strings and LLM text. | The sum of fixes 1+2+3+4: ONE authored voice (LLM/kernel) for greeting + conversation + close, name once, constant prosody, natural Hinglish — exactly the inbound structure. |
| **6** | Pacing/loudness/stability VARIABILITY — must be CONSTANT, same across all turns, no special name emphasis | `_build_tts()` `:598-605` uses `stability=0.65, speed=1.0` (env), patched the wrong direction; variability actually comes from the scripted-line/LLM-line collision, not from low stability. | **Pin the CONSTANT inbound prosody** (§4): `stability=0.45, similarity_boost=0.80, style=0.0, use_speaker_boost=False, speed=1.08`. Apply identically to every utterance (already how EL works once these are fixed). Removing the separate opener/closer speech events removes the lurch; the constant low-stability voice is what the founder loved. |
| **(7)** | Cross-vertical: auto-adapt from the campaign brief (sales/support/inbound/collections), NOT a hardcoded mode | Today's prompt is real-estate-telecaller-shaped (`prompt.py:330+` is a hardcoded RE flow). | The kernel's W3 ContextEngine + VendorScript compile the **campaign brief / vendor `raw_script`** into the flow/persona at runtime (`outbound.py:185-265`). No hardcoded vertical — the brief drives greet→qualify→pitch→close. This is the kernel-on win and is additive to the voice fixes. |

---

## 4. The CONSTANT prosody values (derived from the GOOD inbound voice)

These are the LOAD-BEARING constants. Source of truth =
`_inbound_ref/aim_voice_agent.LIVE.py::_build_tts()` `:735-750` (the call the
founder loved). Apply them IDENTICALLY to every utterance on outbound; do NOT
introduce any per-turn or per-token variation.

| Param | INBOUND (loved, target) | OUTBOUND now (wrong) | Set outbound to |
|---|---|---|---|
| `stability` | **0.45** | 0.65 | **0.45** |
| `similarity_boost` | **0.80** | (verify; set explicit) | **0.80** |
| `style` | **0.0** | 0.0 | **0.0** (never raise — style>0 adds swing) |
| `use_speaker_boost` | **False** | (verify) | **False** |
| `speed` | **1.08** | 1.0 | **1.08** |
| `model` | `eleven_flash_v2_5` | same | `eleven_flash_v2_5` |
| `voice_id` | `QTKSa2Iyv0yoxvXY2V8a` | same | `QTKSa2Iyv0yoxvXY2V8a` |
| `auto_mode` | `True` | same | `True` |

**Why 0.45, not the founder's guessed 0.50 or the current 0.65:** ElevenLabs
stability is *consistency vs expressiveness*. 0.3–0.5 = expressive, human,
natural prosody; 0.7+ = flat/robotic but monotone. The GOOD inbound ran at
**0.45** and that is the exact value to copy — the founder said he was guessing
at 0.50; the empirical answer from the loved call is 0.45. The perceived
"variability" the founder heard on outbound was NOT from low stability — it was
from the scripted-opener/LLM-line collision and the name being shouted in a
separate speech event. Fix those (§3) and pin 0.45 constant → expressive AND
stable, which is exactly what made inbound feel human.

**Constant = no per-token emphasis on the name:** because the name is no longer
spoken in a dedicated `session.say(opener)` event and the prompt forbids
name-repetition, the name is rendered as ordinary in-sentence text at the same
0.45/1.08 as every other word. There is no mechanism left to emphasize it.

---

## 5. The exact fix plan (what to build, in order)

This is a **VOICE-PATH** change (it must touch the spoken opener/closer + TTS),
so it is NOT the brain-only A+B+C cutover — it is the FULL kernel-drives-voice
path, kernel-on-gated, with the inbound prosody. Earner-safe: every hunk gated by
`KERNEL_OUTBOUND` (default OFF) so OFF = byte-identical to `98655dbf`; revert =
flag off + restart.

1. **Kernel owns the single greeting (fixes 1, 2-opener, 3a-name-once).**
   On `KERNEL_OUTBOUND=1`: do NOT call `session.say(opener)` (`agent.py:912`) and
   do NOT call `_llm_opener` (`:214`). The kernel system prompt authors exactly
   one `OPENING:` directive following the learned PATTERN (good morning/afternoon
   → "greetings from {company}" → "क्या मैं {name} जी से बात कर रही हूँ?" → WAIT →
   reason + permission → proceed). The LLM speaks it as its first turn. One
   speaker, structurally — mirror inbound. Remove the `OPENER_ALREADY_SAID` hack
   on the kernel path (no longer needed; nothing pre-spoke).

2. **Kernel owns the close (fixes 2-ending).**
   On `KERNEL_OUTBOUND=1`: do NOT speak `_goodbye_line()` / `session.say(line)`
   (`:726`). The kernel prompt carries a `CLOSING:` directive; the close is a
   normal LLM turn. Nothing hardcoded is spoken at hangup.

3. **Name sparingly (fixes 3a).**
   Replace `agent.py:466` injection with: "caller's naam = X; use it at most once,
   naturally; NEVER prefix turns with it; do not repeat." The kernel `OPENING:`
   names once; the conversation rule bans repetition.

4. **Pin the constant prosody (fixes 3b, 6).**
   Set `_build_tts()` (`agent.py:598-605`) to the §4 constants:
   `stability=0.45, similarity_boost=0.80, style=0.0, use_speaker_boost=False,
   speed=1.08`. Simplest earner-safe deploy = set the env on the outbound unit
   (`EL_STABILITY=0.45`, `EL_SPEED=1.08`) via a systemd drop-in (not shared
   `.env`) so it is isolated to `famit-agent`; long-term also fix the in-code
   defaults so a bare box is correct. Apply identically every utterance.

5. **Natural Hinglish (fixes 4).**
   Keep STT `language="unknown"` (auto code-mix; never force `hi-IN`). The kernel
   brain prompt mandates conversational Hinglish, mirrors the caller's register,
   and bans formal-register words (e.g. "महत्वपूर्ण"). Port inbound's
   natural-Hinglish directive.

6. **Cross-vertical auto-adapt (fixes 7).**
   This is already what the kernel ON path does: W3 ContextEngine + VendorScript
   compile the campaign brief / vendor `raw_script` into the flow + persona at
   runtime (`outbound.py:185-265`). No hardcoded vertical/mode — the brief drives
   greet→qualify→pitch→close for sales/support/inbound/collections alike.

7. **Earner-safe gating + revert.**
   Every hunk above guarded by `KERNEL_OUTBOUND` (default OFF). OFF = the worker
   speaks the opener/closer exactly as today, TTS env default stays 0.65 unless
   the drop-in is applied → byte-identical to `98655dbf`. Flip via a systemd
   drop-in on `famit-agent` only. Revert = delete the drop-in / `KERNEL_OUTBOUND=0`
   + restart (instant), or restore the `98655dbf` backup. One box-mutating change
   at a time; the founder's REAL outbound ring is the only acceptance truth.

---

## 6. Code anchors (ground truth, re-locate by surrounding code, not raw line)

- Inbound greeting (single, pre-LLM): `_inbound_ref/aim_voice_agent.LIVE.py:576-581`
- Inbound TTS constants (the loved voice): `_inbound_ref/aim_voice_agent.LIVE.py:735-750`
- Inbound STT auto code-mix: `_inbound_ref/aim_voice_agent.LIVE.py:706`
- Outbound hardcoded opener builder (Groq + name): `droplet_work/agent.py:214-249`
- Outbound opener SPOKEN: `droplet_work/agent.py:912`
- Outbound name injected every call: `droplet_work/agent.py:466`
- Outbound `OPENER_ALREADY_SAID` soft suppression: `droplet_work/agent.py:475-481`
- Outbound hardcoded close + spoken: `droplet_work/agent.py:359` (`_goodbye_line`), `:726` (`session.say(line)`)
- Outbound `_llm_close` (gated, still has the hardcoded fallback): `droplet_work/agent.py:370`
- Outbound TTS (wrong constants): `droplet_work/agent.py:598-605`
- Greeting PATTERN already learned (kept): `droplet_work/prompt.py:330-348` (the RE-shaped flow to be replaced by the kernel brief-driven flow on the kernel path)
- Kernel façade (already built, kernel-drives capability): `voice_kernel/integrations/outbound.py` — `assemble_outbound_instructions` (brain), `on_turn` (per-turn lang/RAG), `choose_tts` (provider), `persist_post_call` (memory)
- Brain-only patch (insufficient for these complaints — omits the voice path): `design/W-INT-OUTBOUND-PATCH-BRAINONLY.md` §3 (D/E/F/G omitted)
