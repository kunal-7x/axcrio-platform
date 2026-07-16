# W5 — Sarvam-Silence + Speech-Planner + Turn-Detection SEAM NOTE

Status: **SEAM NOTE ONLY — no live file edited this wave.**
Branch: `fix/realtime-voice-kernel-v2`. Earner law honoured: `droplet_work/agent.py`
md5 = `98655dbf` (unchanged); `aim_voice_agent.py` and `caller.py` **not edited**.

This documents the LATER, flag-gated cutover that wires the W5 modules built this
wave (`voice_kernel/speech/`, `voice_kernel/providers/`) into the live agents. It
records the exact `file:line`, the env flags, and the one-line revert for each
change. NONE of this is applied here — it is the recipe a future box-mutating wave
follows, one change at a time, each with an integrated real-call smoke + revert.

The W5 modules are **disjoint and additive**: registered via
`build_kernel(cfg, speech=build_speech_planner(choice.tts), router=build_provider_router(...))`.
The default kernel build still uses the Null pass-through impls, so with the kernel
flag OFF the live path is byte-identical (proven: `test_w5_parity.py`, 10/10).

---

## FIX 1 — SARVAM TTS SILENT on lean plans (founder complaint e)

### Root cause (live, read-only)
`droplet_work/aim_voice_agent.py`:

- **`:2437`** — `_prov_lock_on = _env_flag("INBOUND_PROV_LOCK", False)` → the
  provider-lock defaults **OFF**, so `resolve_providers()` is never consulted.
- **`:2446`** — `_tts_provider = _prov.get("tts") if _prov_lock_on else "elevenlabs"`
  → with the flag off this is **hard-wired to ElevenLabs**, so the Sarvam build path
  at **`:424-439`** (`_build_tts_sarvam`) is **unreachable**. Lean/Standard tiers that
  should speak Sarvam Bulbul always speak ElevenLabs.
- **`:451`** — `tts=_build_tts(_tts_provider)`; and `_build_tts` (`:445-...`) silently
  falls back EL on a Sarvam construction error (logged WARNING only), while the
  session log records the **intended** provider — "billed Sarvam, actually spoke EL".

### The flag-gated fix (LATER)
1. Replace the ad-hoc resolver with the **authoritative** `DefaultProviderRouter`
   (`voice_kernel/providers/router.py`). It maps plan tier → TTS engine
   (`lean/standard → sarvam`, `growth/premium/enterprise → elevenlabs`) and an
   explicit `tts_provider` field override wins. The SAME `ProviderChoice` is read by
   **preview, live, usage AND billing** (no second divergent default).
2. Make selection **authoritative**, not gated behind an off-by-default flag: the
   router always resolves; there is no "skip the resolver" branch. Keep a single
   master kernel flag (`KERNEL_INBOUND`) so the whole seam is reversible, but DO NOT
   reintroduce `INBOUND_PROV_LOCK`-style default-OFF that strands Sarvam.
3. Make fallback **fail-LOUD**: on a Sarvam build/stream failure call
   `router.on_error("sarvam", code)` → returns an EXPLICIT `ProviderChoice` whose
   `reason` names the fallback, AND it is logged at INFO. `ProviderDiagnostics`
   records `selected_tts` vs `actual_tts`; `diag.silent_swap` is a loud anomaly flag.
   Billing reads `actual_tts`, never the intended one — kills the cost divergence.
4. Sarvam realtime streaming uses `SARVAM_WS_CONTRACT` (router.py): `min_buffer_size=30`,
   `max_chunk_length=250`, `output_audio_codec="mulaw"`, `output_sample_rate=8000`,
   `model="bulbul:v2"` (v3 lacks `enable_preprocessing` → we normalize upstream in the
   Speech Planner, so v2/v3 sound identical).

### Wiring point (LATER)
At session construction (`aim_voice_agent.py:2446-2451`), behind `KERNEL_INBOUND=1`:
```python
choice = kernel.svc.router.resolve(call_ctx)        # authoritative, once per call
tts = _build_tts(choice.tts)                          # existing builder, unchanged
# on a Sarvam failure inside _build_tts: choice = kernel.svc.router.on_error("sarvam", code)
```
### Flags / revert
- Flag: `KERNEL_INBOUND=1` (inbound only; earner outbound stays OFF). Default OFF.
- Revert: `KERNEL_INBOUND=0` → byte-identical to today (resolver dormant, EL default).

---

## FIX 2 — HALF-WORDS / truncated sentences (founder complaint a)

### Root cause (live, read-only)
`droplet_work/agent.py`:
- **`:617`** — `max_completion_tokens=int(os.getenv("GROQ_MAX_TOKENS", "90"))`. A 90-token
  ceiling guillotines the LLM **mid-sentence / mid-word** when the model ignores the
  "1-2 short sentences" rule. No monitoring for pegging; on a peg the turn can cut off.
- The comment at **`:614`** already prescribes the fix: "RAISE GROQ_MAX_TOKENS and tighten
  the prompt instead."

### The flag-gated fix (LATER), two layers
1. **Generation layer (live, env-only):** raise `GROQ_MAX_TOKENS` to ~`160` (env override,
   fully reversible, no code edit needed — it is already `os.getenv`). A normal Hinglish
   beat is ~35-50 tokens, so 160 leaves headroom for the model to FINISH a sentence
   before the cap, instead of being chopped at 90. Pair with the existing prompt brevity
   rule so latency stays low (a finished 2-sentence beat is still short).
2. **Text-layer backstop (W5, this wave):** the `SpeechPlanner` runs
   `repair_truncation()` (`voice_kernel/speech/segment.py`) between LLM and TTS — if the
   text still ends mid-sentence it drops the dangling clause to the last complete
   sentence boundary (or closes it cleanly), so the TTS **never speaks a half-word**.
   This is provider-agnostic and active whenever the kernel speech step is wired.

### Flags / revert
- Generation: env `GROQ_MAX_TOKENS=160` (no code change). Revert: set back to `90`.
- Text backstop: active via `KERNEL_INBOUND=1` speech step. Revert: `KERNEL_INBOUND=0`.

---

## FIX 3 — Semantic turn-detection (latency / barge-in quality)

### Current state (live, read-only)
- `aim_voice_agent.py:367-378` — `_resolve_turn_detection()` already supports
  `TURN_DETECTION=semantic` (LiveKit `MultilingualModel`), defaulting to `vad`.
- `agent.py:630` (earner) — hard-wired `turn_detection="vad"` (fast, no heavy model);
  endpointing `:623 MIN_EP_DELAY=0.25`, `:624 MAX_EP_DELAY=0.45`.

### The flag-gated fix (LATER)
- INBOUND first (non-earner): set `TURN_DETECTION=semantic` so the multilingual
  semantic endpointer reduces false barge-ins / clipped turns on code-mixed Hinglish.
  Already env-gated in `aim_voice_agent.py`; no code edit — flip the env on the box,
  smoke a real inbound call, revert with `TURN_DETECTION=vad`.
- OUTBOUND (earner `agent.py:630`) is a literal `"vad"` — changing it IS a code edit to
  the earner, so it is **explicitly deferred** to a dedicated box-mutating wave with a
  ringing real outbound call before+after. Do NOT bundle it with the inbound flip.

### Flags / revert
- Inbound: `TURN_DETECTION=semantic` (env). Revert: `TURN_DETECTION=vad`.
- Outbound: deferred (would require editing `agent.py:630` — earner-gated, separate wave).

---

## Cutover discipline (founder law)
One box-mutating change at a time. Order: (1) inbound `GROQ_MAX_TOKENS` env raise →
smoke; (2) inbound `KERNEL_INBOUND=1` (router + speech step) → smoke a lean-tier call,
confirm Sarvam audio + diagnostics show `selected==actual==sarvam`; (3) inbound
`TURN_DETECTION=semantic` → smoke. Each step has a one-env revert above. The earner
outbound path (`agent.py`) is touched LAST, in its own wave, only after inbound proves
the modules in production.
