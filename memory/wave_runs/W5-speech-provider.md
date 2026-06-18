# Wave W5 — Speech Planner + Provider Router

Branch: `fix/realtime-voice-kernel-v2`. Earner law: `droplet_work/agent.py` md5
`98655dbf` unchanged; `aim_voice_agent.py` / `caller.py` NOT edited. Disjoint new
files under `voice_kernel/speech/` + `voice_kernel/providers/`; registered via
`build_kernel(cfg, speech=..., router=...)`. Default kernel build still uses the
Null impls → flag-OFF byte-identity (10/10, proven).

## Phase: BUILD

Built (DISJOINT, additive):
- `voice_kernel/speech/` — `DefaultSpeechPlanner` (binds frozen `SpeechPlanner.plan`):
  - `normalize.py` — numbers/₹-lakh-crore/phone(digit-by-digit)/date/time/percent/
    unit/acronym → SPOKEN words (EN + casual Hinglish), Indian 3:2:2 grouping.
  - `hinglish.py` — banned literary-Hindi → casual (mahatvapurn→zaroori; Latin +
    Devanagari forms), English loan-words kept in Latin.
  - `segment.py` — complete-sentence guard (`repair_truncation` = text-layer
    half-word fix) + safe sentence chunking.
  - `prosody.py` — adaptive, SPARSE fillers + prosody punctuation; NONE on
    price/phone/booking/compliance lines.
  - `planner.py` — pipeline + provider-keyed render (Sarvam code-mix vs EL concise);
    FAIL-OPEN (raw text, normalized=False on any error — never drops a turn).
- `voice_kernel/providers/` — `DefaultProviderRouter` (binds frozen `ProviderRouter`):
  - `keypool.py` — health-scored key pool (429 demote + cooldown recovery; 400 no-op;
    exhausted → explicit None).
  - `router.py` — AUTHORITATIVE selection (lean→sarvam, premium→EL, explicit override);
    `resolve`/`on_error` fail-LOUD + LOGGED fallback (never silent EL swap);
    `ProviderDiagnostics` (selected vs actual, `silent_swap` anomaly flag);
    `SARVAM_WS_CONTRACT` (min_buffer_size/max_chunk_length/mulaw-8k/bulbul:v2).

Tests (pytest GREEN, 37 new):
- `test_speech_planner.py` — paragraph never yields a half-word; mahatvapurn-class
  replaced; ₹58 lakh / phone / date / time / 2BHK render spoken; no filler on
  price line; tts_lang stamped; build_kernel registration; 0 droplet imports (AST).
- `test_provider_router.py` — lean→Sarvam (never silent EL); fallback LOGGED not
  silent; 429 rotate-key vs no-healthy-key loud fallback; keypool demote/recover;
  WS contract; build_kernel registration; 0 droplet imports (AST).
- `test_w5_parity.py` — default kernel uses Null W5 impls; flag-OFF Null
  pass-through byte-identical 10/10; W5 planner deterministic 10/10; registering W5
  doesn't mutate the default kernel.

Verification:
- `pytest voice_kernel/tests/` = **168 passed** (1 pre-existing UNRELATED failure in
  `test_brain_packs.py::test_support_modelayer_carries_no_real_estate_vocab`, an
  untracked W2 file outside this wave's scope — deselected, not introduced by W5).
- `md5sum droplet_work/agent.py` = `98655dbf` (earner byte-identical).
- `git status droplet_work/` clean (no live-file edits).

Seam doc written (no live edit): `design/W5-SARVAM-AND-SPEECH-SEAM.md` — documents
the LATER flag-gated cutover for INBOUND_PROV_LOCK Sarvam-silence (aim_voice_agent.py
:2437/:2446/:424-439/:451), GROQ_MAX_TOKENS raise (agent.py:617), and semantic
turn-detection (aim_voice_agent.py:367; agent.py:630 earner-deferred), with file:line,
flags, and one-env reverts.
