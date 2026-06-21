# W-VOICE-HEART-PLAN — the RIGHT outbound integration (kernel drives the words, old worker is only the TTS engine)

> READ-ONLY ARCHITECTURE / BUILD PLAN. No box mutation in this wave. Branch `fix/callback-retry-scheduling`.
>
> 🚨 EARNER LAW: the OUTBOUND earner is `droplet_work/agent.py` (LIVE box md5
> `98655dbf…`, local working copy `6c577b9b`). `droplet_work/` is GITIGNORED +
> box-only. The integration BULK is the TRACKED `voice_kernel/` package. Every
> hunk in this plan is gated by `KERNEL_OUTBOUND` (default OFF) so OFF =
> byte-identical to `98655dbf`. Revert = flag off + restart, or restore the
> `98655dbf` backup.
>
> Source of truth for the diagnosis: `design/W-VOICE-HEART-DIAGNOSIS.md`. This
> plan turns that diagnosis into the EXACT line-level edit set: which `agent.py`
> lines change, which stay, and the CONSTANT prosody values — derived from the
> GOOD inbound voice (`_inbound_ref/aim_voice_agent.LIVE.py`).

---

## 0. The architecture in one diagram

```
          ┌──────────────────────────── OUTBOUND CALL (KERNEL_OUTBOUND=1) ────────────────────────────┐
          │                                                                                           │
  campaign│  ┌─────────── THE BRAIN (kernel) — owns ALL the WORDS ───────────┐   ┌─ THE ENGINE (worker) ─┐
  brief + │  │ voice_kernel/  W3 ContextEngine + VendorScript + brain_packs  │   │ droplet_work/agent.py │
  vendor  │  │   → assemble_outbound_instructions() → ONE system prompt that │   │   - elevenlabs.TTS(...) │
  raw_    │──┤   authors: greeting PATTERN (greet→confirm-identity→WAIT→     │──▶│   - sarvam.STT(...)     │
  script  │  │   reason+permission→qualify→pitch→objection→CLOSE), name-once,│   │   - groq.LLM(...)       │
          │  │   natural Hinglish, cross-vertical (sales/support/collections │   │   - AgentSession(...)    │
          │  │   /booking/reminder auto-picked from the brief, NOT hardcoded)│   │   - turn loop            │
          │  └──────────────────────────────────────────────────────────────┘   └────────────────────────┘
          │                          ▲  the LLM speaks every line                 ▲ CONSTANT prosody:
          │                          │  (greeting + body + close)                 │ stability 0.45, speed 1.08,
          │   ❌ SUPPRESSED on kernel-on:                                          │ style 0.0, spk_boost False
          │      - _llm_opener()/session.say(opener)  (the 2nd speaker)            │ (the GOOD inbound voice)
          │      - _goodbye_line()/session.say(line)  (the hardcoded close)        │
          │      - LEAD NAME "greet by this naam" injection (name-every-turn)      │
          └───────────────────────────────────────────────────────────────────────────────────────────┘

  ONE voice authors every word (mirror inbound). The worker NEVER speaks a scripted line.
  The TTS ENGINE (model + voice_id) stays the founder's; only the prosody KNOBS become CONSTANT.
```

The split is clean and load-bearing:

| Layer | Who owns it on `KERNEL_OUTBOUND=1` | What changes |
|---|---|---|
| **The WORDS** (greeting, identity confirm, reason, qualify, pitch, objections, close) | THE KERNEL BRAIN (one LLM voice) | NEW: the kernel's system prompt authors a single `OPENING:` + `CLOSING:` directive. The worker stops speaking any scripted line. |
| **The TTS ENGINE** (which model, which voice_id, the STT, the LLM construct, the AgentSession, the turn loop) | THE OLD WORKER (`agent.py`) | UNCHANGED — same `eleven_flash_v2_5` + `QTKSa2Iyv0yoxvXY2V8a`, same Sarvam STT, same Groq LLM, same session. |
| **The PROSODY KNOBS** (stability/speed/style/speaker_boost) | THE OLD WORKER's `VoiceSettings` | CHANGED to the CONSTANT inbound values (0.45 / 1.08 / 0.0 / False). Applied identically to every utterance. |

> This is the SUPERSET of the brain-only patch (`W-INT-OUTBOUND-PATCH-BRAINONLY.md`),
> which deliberately omitted the voice path and therefore left ALL six founder
> complaints' MECHANISMS in place (it kept `session.say(opener)`, kept
> `_goodbye_line`, kept `stability=0.65`). This plan applies the brain-only A+B+C
> swap **AND** the voice-path hunks D-prosody + H-opener-suppress + I-close-suppress
> + J-name-sparing that brain-only forbade. It does NOT touch the TTS *engine
> selection* (provider/voice_id/model) — only the prosody knobs + the spoken-line
> suppression. The Sarvam provider router (full Patch D) stays a separate later wave.

---

## 1. WHY this is the right design (not brain-only, not a rewrite)

`design/W-VOICE-HEART-DIAGNOSIS.md` §2 proved the outbound is a scripted bot
because **TWO layers speak and fight**: the worker's `session.say(opener)` +
`_goodbye_line` are hardcoded speech events on TOP of the LLM that also greets and
closes from the system prompt. The inbound the founder LOVED has exactly ONE
speaker (the LLM/brain) plus a single fixed pre-LLM greeting line, a constant
low-stability voice, and the name never injected.

So the RIGHT outbound = **mirror inbound's structure**: the kernel brain owns
greeting + body + close as ONE LLM voice; the worker is reduced to the TTS engine;
prosody is pinned to the inbound constants. We do NOT rewrite `agent.py` (that
risks the earner) and we do NOT settle for brain-only (it fixes none of the six
complaints). We apply the minimal voice-path hunks, each `KERNEL_OUTBOUND`-gated.

Founder complaint → this plan's fix (all six + the cross-vertical one):

| # | Complaint | This plan |
|---|---|---|
| 1 | double greeting + double intro | Hunk H suppresses `session.say(opener)`; the kernel `OPENING:` is the ONLY greeting. One speaker, structurally — like inbound. |
| 2 | hardcoded opener AND hardcoded ending | Hunk H suppresses the opener `say()`; Hunk I suppresses `_goodbye_line`/`session.say(line)`. Greeting + close become normal LLM turns the kernel authors. Nothing hardcoded is spoken. |
| 3a | name repeated every line | Hunk J removes the "greet by this naam" injection (`agent.py:466`); the kernel persona says the name AT MOST once, never as a per-turn prefix. |
| 3b | name too LOUD + too fast | Hunk D pins CONSTANT prosody; with no separate opener `say()`, the name is ordinary in-sentence text at the same 0.45/1.08 as every word — no mechanism left to emphasize it. |
| 4 | "Mahatvapurn" formal Hindi, not Hinglish | STT stays `language="unknown"` (Hunk: NO CHANGE — already inbound's setting at `:625`); the kernel persona mandates conversational Hinglish + bans formal-register words. |
| 5 | scripted bot, not human | The SUM of 1+2+3+4: one authored LLM voice, name once, constant prosody, natural Hinglish = the inbound structure. |
| 6 | pacing/loudness VARIABILITY must be CONSTANT | Hunk D = the CONSTANT inbound prosody, identical every utterance; removing the opener/closer speech events removes the lurch. |
| (7) | auto-adapt from the brief (sales/support/inbound/collections), NOT hardcoded mode | Already the kernel-on path: `brain_packs/packs_data.py` encodes per-vertical `opening_style`/`push_stop_handoff` as DATA; W3 ContextEngine + VendorScript compile the brief/`raw_script` into the flow at runtime. No hardcoded vertical. |

---

## 2. THE EXACT EDIT SET — which `agent.py` lines CHANGE

> Re-locate every anchor by the SURROUNDING CODE, not the raw line number (the
> founder bumps lines with env-gated fixes; local copy is `6c577b9b`, box is
> `98655dbf`). Every hunk is gated by the per-call `_KERNEL_OUTBOUND` flag from
> Patch A. With the flag OFF every hunk is inert ⇒ byte-identical to `98655dbf`.

### Hunk A+B+C — the BRAIN swap (verbatim from `W-INT-OUTBOUND-PATCH-BRAINONLY.md`)

Apply A+B+C exactly as that doc specifies (re-locate by literal code):
- **Patch A** — flag slot right after `lead_name` is read (entrypoint top, `:428`):
  `_KERNEL_OUTBOUND = os.getenv("KERNEL_OUTBOUND","0") in ("1","true","True")` and `_OK=None`.
- **Patch B+C** — at the seam `instructions = base_instructions` (`:485`, literal
  `instructions = base_instructions`): build the per-call façade
  `_ko.build_for_call(...)` (campaign-owner tenant, fail-closed) and choose
  `instructions = _ko.assemble_outbound_instructions(_OK, legacy_render=lambda: base_instructions, fields=fields, recap=recap)` when ON, else the verbatim legacy string.

This makes the kernel author the WHOLE system prompt (the WORDS), including the
single `OPENING:` greeting-pattern directive and the name-once / natural-Hinglish
/ no-"AI assistant" rules already encoded in `voice_kernel/brain_packs/` +
`context/context_engine.py` (GREET→PERMISSION→INTRO + vendor `greeting` override)
+ `disclosure.py` (warm-human-named-once). NOTHING else from `voice_kernel` is
imported on this path.

### Hunk H — SUPPRESS the worker's spoken opener (fixes 1, 2-opener, 3b)

Anchor: `agent.py:894-912` — `opener = _llm_opener(...)` … `await
session.say(opener, allow_interruptions=True, add_to_chat_ctx=_opener_in_ctx)`.

CHANGE: guard the whole opener-build-and-say block on `not _KERNEL_OUTBOUND`. When
the kernel is ON, the worker does NOT call `_llm_opener` and does NOT call
`session.say(opener)`. The kernel's `OPENING:` directive makes the LLM speak the
greeting as its own first turn (mirror inbound — one speaker). When OFF, the block
runs exactly as today (byte-identical).

```python
    # W-HEART Hunk H: on kernel-on, the KERNEL owns the single greeting (the LLM
    # speaks it as turn 1 from the OPENING: directive). Suppress the worker's
    # second-speaker opener entirely — this is the structural single-greeting
    # guarantee (mirror inbound). OFF => the old opener path, byte-identical.
    if not _KERNEL_OUTBOUND:
        _disclose_ai = bool(fields.get("disclose_ai", True))
        _disc_phrase = str(fields.get("ai_disclosure") or "").strip()
        opener = _llm_opener(
            fields.get("agent_name") or "Riya",
            fields.get("company_name") or "Famit",
            fields.get("product_name") or "हमारी property",
            lead_name,
            gender=agent_gender,
            disclose=_disclose_ai,
            disclosure_phrase=_disc_phrase,
        )
        logger.info("opener: %s", opener[:200])
        _opener_in_ctx = os.getenv("OPENER_IN_CTX", "0") not in ("0", "false", "False")
        await session.say(opener, allow_interruptions=True, add_to_chat_ctx=_opener_in_ctx)
    else:
        # Kernel-on: nudge the agent to emit its first (greeting) turn. The greeting
        # text comes from the LLM authored by the kernel OPENING: directive — never
        # a hardcoded string. session.generate_reply() with no user input prompts the
        # opening turn (LiveKit AgentSession API). If unavailable on the pinned
        # plugin version, leave it to the model's turn-1 (the OPENING: directive still
        # fires on first user audio); verify on the canary which the box supports.
        logger.info("kernel-on: greeting owned by the brain (OPENING: directive); worker opener suppressed")
        try:
            await session.generate_reply()
        except Exception as exc:  # noqa: BLE001 — never break the earner
            logger.warning("kernel greeting kickoff fell through to model turn-1: %r", exc)
```

> NOTE on the greeting kickoff: inbound speaks its fixed greeting BEFORE handing
> to the LLM. Outbound has no fixed greeting (the brief drives it), so the kernel
> needs the LLM to produce turn-1. The cleanest LiveKit-native way is
> `session.generate_reply()` (or the version's equivalent "say hello first"
> entrypoint) right after `session.start()`. The deploy wave MUST confirm the
> exact API on the box's pinned `livekit-agents` version on the canary call; the
> `try/except` makes a wrong guess fail OPEN to the model's natural turn-1, never
> a crash. This is the ONE behavioral unknown — it is verified on the real ring,
> not assumed.

### Hunk I — SUPPRESS the hardcoded close (fixes 2-ending, 5)

Anchor: `agent.py:708-733` — `_confirm_then_hangup(signal)` builds `line` from
`_llm_close` or `_goodbye_line` and `session.say(line, allow_interruptions=False)`.

CHANGE: on `_KERNEL_OUTBOUND`, do NOT build/say `line` from `_goodbye_line` /
`_llm_close`. The kernel persona carries a `CLOSING:` directive so the close is a
normal LLM turn the brain already spoke; `_confirm_then_hangup` only does the room
teardown. When OFF, runs exactly as today.

```python
    async def _confirm_then_hangup(signal: str) -> None:
        if ctl["closing"]:
            return
        ctl["closing"] = True
        try:
            if not _KERNEL_OUTBOUND:
                _agent_nm = fields.get("agent_name") or "Riya"
                _company_nm = fields.get("company_name") or "Famit"
                if os.getenv("LLM_CLOSE", "0") in ("1", "true", "True"):
                    line = _llm_close(signal, _agent_nm, _company_nm, agent_gender, turns)
                else:
                    line = _goodbye_line(signal, _agent_nm, _company_nm, agent_gender)
                logger.info("P2 closure signal=%s -> goodbye: %s", signal, line[:120])
                handle = session.say(line, allow_interruptions=False)
                try:
                    await handle.wait_for_playout()
                except Exception:  # noqa: BLE001
                    await asyncio.sleep(2.5)
                await asyncio.sleep(0.4)
            else:
                # Kernel-on: the brain already spoke the close (CLOSING: directive) as a
                # normal LLM turn. Give it a moment to play, then tear down — NEVER speak
                # a hardcoded goodbye on top of the LLM's authored close.
                logger.info("kernel-on closure signal=%s: brain owns the close; worker says nothing", signal)
                await asyncio.sleep(1.2)
        except Exception as exc:  # noqa: BLE001
            logger.warning("closure say failed: %r", exc)
        finally:
            try:
                await ctx.delete_room(room_name=room_name)
            except Exception as exc:  # noqa: BLE001
                logger.warning("delete_room failed: %r", exc)
```

> The kernel `CLOSING:` directive must instruct the LLM to deliver the goodbye as
> its turn when the close signal is reached, so by the time `_confirm_then_hangup`
> fires the brain's close has already been spoken. The 1.2s grace lets it finish
> playout before room teardown. If the close-signal plumbing means the LLM has not
> yet spoken a goodbye at teardown, this is acceptable for the first canary (a
> clean hangup beats a double "ok perfect"); a later refinement can wait on the
> brain's close turn explicitly. Verified on the real ring.

### Hunk J — name SPARINGLY, not every turn (fixes 3a)

Anchor: `agent.py:464-466`:
```python
    base_instructions = system_prompt
    if lead_name:
        base_instructions += f"\n\nLEAD NAME (इस caller का naam): {lead_name} — opener में इसी naam से greet करो।"
```

On the kernel-on path this injection is SKIPPED — the kernel persona already
carries the name-once rule and feeds `lead_name` to the `OPENING:` directive
(named once, never a per-turn prefix). But because A+B+C wrap `base_instructions`
in `legacy_render=lambda: base_instructions`, the cleanest edit is to gate the
APPEND, not the lambda. Replace the `if lead_name:` append with:

```python
    base_instructions = system_prompt
    if lead_name and not _KERNEL_OUTBOUND:
        # OFF (legacy): keep the proven append byte-identical.
        base_instructions += f"\n\nLEAD NAME (इस caller का naam): {lead_name} — opener में इसी naam से greet करो।"
    # ON (kernel): the lead_name flows to the kernel via build_for_call(fields=...);
    # the persona uses it AT MOST ONCE in the OPENING: directive and forbids per-turn
    # name prefixes (brain_packs/disclosure + the name-sparing rule). No "greet by
    # this naam every turn" license is injected.
```

> Likewise the `OPENER_ALREADY_SAID` block (`agent.py:474-481`) must NOT be
> appended on the kernel-on path — there is no pre-spoken opener to suppress, and
> the no-re-greet behavior lives in the kernel persona. Gate it the same way:
> `if (not _KERNEL_OUTBOUND) and os.getenv("OPENER_ALREADY_SAID","1") in (...):`.
> (On OFF it stays byte-identical.) Note: `_KERNEL_OUTBOUND` must be defined
> BEFORE this block — Patch A reads `lead_name` at `:428` and sets the flag, which
> is above `:464`, so ordering is satisfied. If the working copy orders Patch A
> below `:464`, hoist the flag read above the `base_instructions` assembly.

### Hunk D — PIN the CONSTANT prosody (fixes 3b, 6)

Anchor: `agent.py:587-608` — `tts = elevenlabs.TTS(... voice_settings=VoiceSettings(
stability=float(os.getenv("EL_STABILITY","0.65")), similarity_boost=…, style=0.0,
use_speaker_boost=False, speed=float(os.getenv("EL_SPEED","1.0")) ) ...)`.

The DEFAULTS are wrong (0.65 / 1.0). Two-part fix, both earner-safe:

1. **In-code defaults** → flip the env DEFAULTS to the inbound constants so a bare
   box is correct (the env still overrides for live tuning):
   ```python
       voice_settings=VoiceSettings(
           stability=float(os.getenv("EL_STABILITY", "0.45")),       # was "0.65" — the GOOD inbound value
           similarity_boost=float(os.getenv("EL_SIMILARITY", "0.80")),
           style=0.0,                                                # never raise; style>0 = swing
           use_speaker_boost=False,                                  # no loudness pumping
           speed=float(os.getenv("EL_SPEED", "1.08")),               # was "1.0" — the GOOD inbound value
       ),
   ```
2. **Live pin via the systemd drop-in** (no code redeploy needed to flip): set
   `EL_STABILITY=0.45` and `EL_SPEED=1.08` in the kernel-outbound drop-in (§4) so
   it is scoped to `famit-agent` ONLY (never the shared `.env`).

> IMPORTANT — Hunk D is NOT gated by `KERNEL_OUTBOUND`. The constant prosody is the
> RIGHT voice with OR without the kernel brain (it is the inbound voice the founder
> loved). Flipping the in-code defaults changes the resting `agent.py` (so it is the
> ONE intentional byte change vs `98655dbf` outside the gated brain swap). If the
> deploy wave wants a literally byte-identical resting agent.py, keep the in-code
> defaults at 0.65/1.0 and pin 0.45/1.08 PURELY via the drop-in env — then OFF with
> no drop-in = byte-identical, and the drop-in alone delivers the constant voice.
> RECOMMENDATION: ship the drop-in pin first (zero code-default risk, instantly
> revertible by editing the drop-in), then flip the in-code defaults in a later
> commit once the 0.45/1.08 voice is confirmed on the real ring. The drop-in is the
> safe lever; the code default is the long-term correctness.

---

## 3. WHICH `agent.py` LINES STAY (the TTS ENGINE — DO NOT TOUCH)

These are the founder's voice ENGINE. They are byte-identical ON or OFF. The
kernel changes the WORDS and the prosody KNOBS; it NEVER changes which model/voice
speaks them.

| Stays unchanged | Anchor | Why |
|---|---|---|
| **TTS engine + voice** | `elevenlabs.TTS(api_key=…, voice_id=… "QTKSa2Iyv0yoxvXY2V8a", model="eleven_flash_v2_5", auto_mode=True)` `agent.py:587-608` | THIS is the founder's voice. We touch ONLY the `VoiceSettings` knobs (Hunk D), never the engine/voice_id/model. The Sarvam provider router (full Patch D from the other doc) is a SEPARATE later ring-gated wave. |
| **STT auto code-mix** | `sarvam.STT(language=os.getenv("SARVAM_STT_LANG","unknown"), model="saarika:v2.5")` `agent.py:618-626` | Already inbound's setting (`unknown` = per-utterance detect). Forcing `hi-IN` garbled Hinglish. NO CHANGE — auto language detect via STT is exactly what we want (complaint 4). |
| **LLM construct** | `groq.LLM(...)` + key round-robin `agent.py:612-617+` | The hot-path LLM + its key rotation are the proven low-latency setup. The kernel feeds the SYSTEM PROMPT into it; the LLM construct itself is untouched. |
| **AgentSession + turn loop** | `session = AgentSession(stt=…, llm=…, tts=…)` + `on_user_turn_completed` path | The session, VAD, endpointing, interruption handling, language-nudge per turn — all the founder's. The brain-only patch's Patch E (per-turn `on_turn` injection) is NOT applied here either. |
| **`session.start()`** | `agent.py:885-888` | Unchanged. Hunk H's greeting kickoff fires AFTER it. |
| **Language-mirror per turn** | `tts.update_options(language=code)` `agent.py:696-700` | The live per-turn language nudge stays (it keeps TTS/STT language in sync). Not a prosody knob. |
| **`_llm_opener` / `_goodbye_line` / `_llm_close` function DEFINITIONS** | `:214`, `:359`, `:370` | The function bodies STAY (used on the OFF path). Only the CALLS are gated out on the kernel-on path (Hunks H, I). |

> Net: the kernel-on path changes the WORDS (system prompt) + suppresses two
> spoken-line CALLS + pins the prosody KNOBS. The TTS/STT/LLM/session ENGINE is
> not touched. This is why the worst case at the flip is "old brain + the perfect
> voice" — there is zero voice-ENGINE risk.

---

## 4. CONSTANT prosody values — the load-bearing constants (from the GOOD inbound)

Source of truth = `_inbound_ref/aim_voice_agent.LIVE.py::_build_tts()` (the call
the founder loved). Apply IDENTICALLY to every utterance; introduce NO per-turn /
per-token variation.

| Param | Set outbound to | Now (wrong) | Inbound (loved) |
|---|---|---|---|
| `stability` | **0.45** | 0.65 | 0.45 |
| `similarity_boost` | **0.80** | 0.80 | 0.80 |
| `style` | **0.0** | 0.0 | 0.0 |
| `use_speaker_boost` | **False** | False | False |
| `speed` | **1.08** | 1.0 | 1.08 |
| `model` | `eleven_flash_v2_5` | same | same |
| `voice_id` | `QTKSa2Iyv0yoxvXY2V8a` | same | same |
| `auto_mode` | `True` | same | same |

**Why 0.45 (not the founder's guessed 0.50, not 0.65):** ElevenLabs stability =
consistency-vs-expressiveness. 0.3–0.5 = expressive/human/natural prosody; 0.7+ =
flat/monotone-robotic. The GOOD inbound ran **0.45** — that is the empirical answer
from the loved call (the founder said 0.50 was a guess). The perceived
"variability" on outbound was NOT from low stability — it was the
scripted-opener/LLM-line COLLISION and the name shouted in a separate speech event.
Fix those (Hunks H/I/J) and pin 0.45 CONSTANT → expressive AND stable = the inbound
feel. "Constant" is automatic once the separate opener/closer speech events are
gone: the name is ordinary in-sentence text at the same 0.45/1.08 as every word, so
there is no mechanism left to emphasize it.

---

## 5. THE KERNEL PROMPT must carry OPENING: + CLOSING: (the only kernel-side requirement)

The agent.py hunks suppress the worker's speech; the kernel must now PRODUCE the
greeting + close as LLM turns. Verify (and, if absent, add) in the kernel persona /
`assemble_prefix` path:

- **`OPENING:` directive** — already structurally present: `context/context_engine.py`
  emits the GREET→PERMISSION→INTRO flow (`:155 _FLOW_TO_TALKING`) with a vendor
  `greeting` override (`:180-182`); `brain_packs/packs_data.py` `opening_style` per
  vertical ("Full greet→confirm→intro→reason→permission skeleton" for sales, etc.).
  REQUIRED text (learn the PATTERN, do NOT hardcode words): **good morning/afternoon
  → "greetings from {company}" → "क्या मैं {lead_name} जी से बात कर रही हूँ?" → WAIT
  for the answer → reason for calling + permission → proceed.** Confirm the assembled
  prefix instructs the LLM to OPEN with this as turn 1 and to use `lead_name` exactly
  ONCE here.
- **`CLOSING:` directive** — confirm the persona instructs the LLM to deliver a
  natural goodbye when the outcome is reached (booked / not interested / callback),
  in the caller's register, never a canned line. (The vertical packs carry
  `push_stop_handoff`; the close should be one warm LLM line.)
- **Name-once rule** — `brain_packs/disclosure.py:210/212` already says "introduce
  by name … as a warm human, never AI/assistant." ADD (if not present): "use the
  caller's name AT MOST once, naturally; NEVER prefix turns with it; do not repeat."
- **Natural-Hinglish rule** — `brain_packs/language.py` keeps names/English nouns
  un-translated in Hindi. ADD (if not present) an explicit ban on formal-register
  words ("महत्वपूर्ण" etc.) and a "बोलचाल/conversational Hinglish, mirror the
  caller's register" mandate, matching the inbound feel.

> These are TRACKED `voice_kernel/` edits (not the gitignored box file), so they are
> normal commits with unit tests. They are inert until `KERNEL_OUTBOUND=1`. If the
> kernel persona ALREADY emits all four (likely — the brain_packs above show it
> largely does), this section is a verification checklist, not new code.

---

## 6. GATED DEPLOY RUNBOOK — the founder-gated `KERNEL_OUTBOUND` flip

> BUILD/verify ONLY in this wave. The flip is the separate, most dangerous,
> founder-gated, one-box-mutating step. The founder's REAL outbound ring is the
> only acceptance truth.

1. **Pre-flight (no mutation).** Confirm box `agent.py` md5 `98655dbf`, `KERNEL_OUTBOUND`
   unset, no kernel drop-in. Back up: `cp /opt/famit-agent/agent.py
   agent.py.HEARTbak.<ts>`, `cp .env .env.HEARTbak.<ts>`. Snapshot a known-good
   outbound recording for A/B. `python -m pytest voice_kernel/ voice_ops/` green.
2. **Apply the agent.py hunks** (A+B+C brain swap + H opener-suppress + I
   close-suppress + J name-sparing) to the box `agent.py`, re-locating anchors by
   surrounding code. Deploy the tracked `voice_kernel/` package to the box (import-safe,
   droplet-free). Do NOT apply the Sarvam provider router (full Patch D) or the per-turn
   Patch E. Keep `KERNEL_OUTBOUND` UNSET and NO prosody drop-in yet.
3. **OFF-identity ring.** Restart `famit-agent`. With the flag OFF, every hunk is
   inert ⇒ a real ring is byte-identical to today (old opener `say`, old close,
   stability 0.65). Place ONE real outbound call → confirm ZERO change. This proves
   the hunks are correctly gated before any behavior flips.
4. **Pin the constant prosody FIRST (smallest box-mutating step).** Install the
   drop-in with ONLY `EL_STABILITY=0.45` + `EL_SPEED=1.08` (still `KERNEL_OUTBOUND`
   UNSET):
   ```ini
   # /etc/systemd/system/famit-agent.service.d/voice-heart.conf
   [Service]
   Environment=EL_STABILITY=0.45
   Environment=EL_SPEED=1.08
   ```
   `systemctl daemon-reload && systemctl restart famit-agent`. Verify it did NOT leak
   to the inbound agent (`tr '\0' '\n' < /proc/$(pgrep -f aim_voice_agent)/environ |
   grep EL_` → EMPTY). Place a real ring → confirm the OLD brain now speaks in the
   CONSTANT inbound voice (expressive, even pace/loudness). If the voice regresses,
   revert = delete the drop-in + restart. This isolates the prosody change from the
   brain change — one variable at a time.
5. **Flip the brain.** Add `Environment=KERNEL_OUTBOUND=1` to the SAME drop-in,
   `daemon-reload && restart`. (Drop-in scopes it to `famit-agent` only — never the
   shared `.env`, which leaks to the inbound agent per W3 LEARNINGS §2.)
6. **Real-call canary (the only acceptance truth).** Founder places a few REAL
   outbound calls. Confirm: **SINGLE greeting** following the script pattern,
   **name said once** (not loud, not fast), **everything LLM-generated** (no "ok
   perfect" canned line, no hardcoded bye), **natural Hinglish** (no "महत्वपूर्ण"),
   **constant pace/loudness** every turn, voice = the loved inbound timbre. Watch the
   journal for double-greets, a crash on `session.generate_reply()` (Hunk H unknown),
   and latency. Verify on the box: the voice-constructor ranges (`elevenlabs.TTS` /
   `sarvam.STT` / `groq.LLM` / `AgentSession`) diff EMPTY vs `98655dbf` except the
   Hunk-D `VoiceSettings` knobs.
7. **Instant revert (always armed).** Any regression ⇒ `KERNEL_OUTBOUND=0` (or delete
   the drop-in) + restart ⇒ back to old brain + (constant or old) voice. Voice issue ⇒
   remove the prosody lines too. Total failure ⇒ `cp agent.py.HEARTbak agent.py` +
   restore `.env` + restart ⇒ `98655dbf`. Because the voice ENGINE was never touched,
   the worst case is the old brain with the perfect voice — no voice-engine risk.

---

## 7. DEFINITION OF DONE (this BUILD wave — no deploy)

- [ ] `agent.py` hunks A+B+C+H+I+J authored as a reviewable diff against the local
      working copy, each `KERNEL_OUTBOUND`-gated; OFF = byte-identical to `98655dbf`
      (a static test asserts the gated hunks fall outside the voice-constructor spans,
      same shape as `test_voice_unchanged_brainonly.py`).
- [ ] Hunk D prosody constants documented + the drop-in template written
      (`voice_kernel/systemd/famit-agent.service.d-voice-heart.conf` = EL_STABILITY
      0.45 / EL_SPEED 1.08 [+ KERNEL_OUTBOUND=1 for the flip step]).
- [ ] §5 kernel persona verified to emit OPENING: (script pattern, one greeting,
      name once, WAIT) + CLOSING: + name-once + natural-Hinglish/no-"महत्वपूर्ण";
      add the missing rules as TRACKED `voice_kernel/brain_packs|context` edits with
      unit tests. Inert until the flag flips.
- [ ] `python -m pytest voice_kernel/ voice_ops/` green; the brain-only OFF-identity
      + only-the-system-prompt tests still pass (the new hunks are agent-side, gated).
- [ ] The deploy runbook (§6) ready for the founder-gated flip. NO box mutation in
      this wave.

---

## 8. Code anchors (ground truth — re-locate by surrounding code, not raw line)

- Brain swap seam: `droplet_work/agent.py:485` (`instructions = base_instructions`)
- Name injection (gate on kernel-on, Hunk J): `agent.py:464-466`
- `OPENER_ALREADY_SAID` block (gate on kernel-on, Hunk J): `agent.py:474-481`
- TTS `VoiceSettings` (Hunk D prosody): `agent.py:587-608` (stability `:599`, speed `:605`)
- STT auto code-mix (STAYS): `agent.py:618-626` (`language=…"unknown"` `:625`)
- Closure say (suppress on kernel-on, Hunk I): `agent.py:708-733` (`_goodbye_line` build `:724`, `session.say(line)` `:726`)
- Opener build+say (suppress on kernel-on, Hunk H): `agent.py:894-912` (`_llm_opener` `:894`, `session.say(opener)` `:912`)
- `_llm_opener` def (STAYS, OFF path): `agent.py:214-249` (name inject `:221`, greet-by-name `:249`)
- `_goodbye_line` / `_llm_close` defs (STAY, OFF path): `agent.py:359`, `:370`
- Kernel façade (the brain): `voice_kernel/integrations/outbound.py` — `assemble_outbound_instructions` `:271`, `build_for_call` `:85`, `kernel_outbound_enabled` `:52`
- Kernel greeting flow (GREET→PERMISSION→INTRO + vendor greeting override): `voice_kernel/context/context_engine.py:155, 180-182`
- Per-vertical opening_style (cross-vertical auto-adapt, complaint 7): `voice_kernel/brain_packs/packs_data.py:44, 54, 65, 76, 87`
- Warm-human-named-once / no-"AI assistant": `voice_kernel/brain_packs/disclosure.py:210-212`
- Prosody text-shaping (fillers OFF by default — NOT the TTS knobs): `voice_kernel/speech/prosody.py:34-40`
- Inbound GOOD voice (prosody source of truth): `_inbound_ref/aim_voice_agent.LIVE.py::_build_tts()` (stability 0.45, speed 1.08)
- Inbound single pre-LLM greeting (structural model for Hunk H): `_inbound_ref/aim_voice_agent.LIVE.py:576-581`
- Brain-only patch (the SUBSET this plan supersets): `design/W-INT-OUTBOUND-PATCH-BRAINONLY.md`
- Diagnosis (root cause): `design/W-VOICE-HEART-DIAGNOSIS.md`
