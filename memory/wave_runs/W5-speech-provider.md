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

## Phase: VERIFY+COMMIT (2026-06-18)

RECONCILE-FIRST: the W5 modules (`voice_kernel/speech/` 5 files + `voice_kernel/
providers/` 3 files) were already in HEAD via a prior session + the red-team fold
commit `2cb06ac` (half-word / paise-drop / bare-number-leak / Devanagari-corruption
blockers fixed in disjoint edits to speech/ only). This VERIFY phase re-ran every
gate against that tree; the only NEW commit here folds the seam note + this wave log.

Gates (all GREEN):
- `python -m pytest voice_kernel/` = **212 passed / 0 failed** (was 178 at red-team
  time; suite grew, none weakened). The 7 `context/` Stage.PITCH failures the
  red-team flagged as a different wave's bug are now resolved in HEAD.
- W5-scoped subset (speech/provider/planner/normalize/hinglish/prosody/segment/
  parity/identity/router/keypool) = **55 passed**.
- `test_adapter_off_identity.py` ran for REAL (not skipped) = **12/12 PASSED**
  (outbound+inbound × field-sets) — flag-OFF byte-identity invariant intact;
  default `build_kernel` still binds Null impls.
- EARNER LAW: `md5sum droplet_work/agent.py` = `98655dbfc71d5c3da36bcfe3f848082c`
  (branch-baseline snapshot, UNCHANGED); `aim_voice_agent.py` / `caller.py` not
  edited; `git status droplet_work/` clean.
- **0 leaked imports**: no executable `import droplet_work.agent` / `.caller` /
  `aim_voice_agent` anywhere in `voice_kernel/` (the 3 hits are comments / the
  isolated-load docstring in `rag/backends.py`, not live imports).
- gitleaks: `protect --staged` = 0 + `detect` over the staged seam note + wave log
  = 0.
- Staged ONLY: `design/W5-SARVAM-AND-SPEECH-SEAM.md`, `memory/wave_runs/
  W5-speech-provider.md`, `WORKFLOW_LEDGER.md` (never `git add -A`).

FROZEN W5 PUBLIC SURFACE (bound to the W1 contracts, now implemented):
- `SpeechPlanner.plan` (sync, HOT-path) → `DefaultSpeechPlanner` in
  `voice_kernel/speech/planner.py`; FAIL-OPEN (raw text on any error, never drops a
  turn). Returns `SpeechPlan`.
- `ProviderRouter` (fail-LOUD) → `DefaultProviderRouter` in
  `voice_kernel/providers/router.py`; `resolve`/`on_error` log every fallback (never
  a silent EL swap), `ProviderDiagnostics.silent_swap` anomaly flag, `SARVAM_WS_
  CONTRACT`. Returns `ProviderChoice`. Health-scored `keypool.py` (429 demote +
  cooldown recover; exhausted → explicit None).
- Both register via `build_kernel(cfg, speech=impl, provider_router=impl)`.
