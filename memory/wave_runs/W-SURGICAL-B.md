# W-SURGICAL-B — BRAIN-ONLY outbound integration (wave run log)

> Branch `fix/realtime-voice-kernel-v2`. **BUILD/verify ONLY — NO deploy.**
> Executes `design/W-VOICE-SURGICAL-PLAN.md` **Part B**: old PERFECT voice, new
> BRAIN. The W1–W7 kernel feeds **ONLY the SYSTEM PROMPT** to the old worker via
> the existing façade `voice_kernel/integrations/outbound.py`, gated
> `KERNEL_OUTBOUND` (default OFF).
> 🚨 EARNER LAW (SACRED): OUTBOUND earner = `droplet_work/agent.py`, LIVE box md5
> `98655dbf` / `prompt.py fb87ea56`, `KERNEL_OUTBOUND` UNSET. NO box edit, NO
> agent.py edit, NO deploy. The deployable patch = **ONLY Patches A+B+C** (instruction
> swap + OFF-gated entrypoint lines); **Patch D (TTS/Sarvam) / E (per-turn hook) /
> F (post-call memory) / G (box-memory bind) are DELIBERATELY OMITTED** — they are the
> VOICE PATH and stay the old worker's, byte-identical. The opener is still SPOKEN by
> the old worker's `session.say()`. NO voice/TTS/prosody/opener-mechanics/turn-taking change.

## Phase: BUILD — DONE (all green)

### What was already in place (verified, not rebuilt)
- `voice_kernel/integrations/outbound.py` — the TRACKED façade already provides ONLY
  the system prompt via `assemble_outbound_instructions` (OFF/None ⇒ byte-identical
  `legacy_render()`; ON ⇒ `ik.kernel.assemble_prefix(ctx)` — the W1–W7 prompt prefix:
  vendor-script flow + full lossless brief (C3-fenced) + RAG + memory). Item (1) is
  satisfied by construction — A+B+C call ONLY this function; it touches no TTS/prosody.
- `voice_ops/eval/regression_gates.py` — W17 `run_all_gates()` (R1..R10 + repo scan).
- `voice_ops/eval/replay.py` — offline transcript replay scaffold (no call/box).
- `voice_kernel/integrations/tests/test_outbound_integration.py` — OFF byte-identity
  across the FIVE field shapes + ON kernel-prompt + fail-closed tenant + provider tests.

### Files created this wave (all absolute under `C:\Users\kunal\Desktop\caps\`)
- `design/W-INT-OUTBOUND-PATCH-BRAINONLY.md` — the A+B+C-only patch doc; explicitly
  OMITS D/E/F/G with the per-patch voice-path rationale (table); includes the gated
  deploy runbook (systemd drop-in, not shared `.env`; W17 + real-call canary; instant
  `=0` revert; voice-path-untouched evidence).
- `voice_kernel/integrations/tests/test_voice_unchanged_brainonly.py` — the
  VOICE-UNCHANGED STATIC assertion (the part W17 does not cover, B.4.2). Locates the
  voice-constructor spans (`elevenlabs.TTS`/`VoiceSettings`/`sarvam.STT`/`groq.LLM`/
  `AgentSession`/`session.say(opener`) BY CODE LANDMARK (drift-robust: box `98655dbf`,
  local `6c577b9b`) and asserts the two brain-patch anchors (`instructions =
  base_instructions` seam + the post-`lead_name` flag slot) fall OUTSIDE every voice
  span ⇒ A+B+C edit ZERO voice lines. Logic also proven on a synthetic fixture so the
  guarantee runs in CI even if `droplet_work/agent.py` is absent. Droplet-free (reads
  agent.py as TEXT; never imports the box module). **5 tests, PASS.**
- `voice_ops/eval/tests/test_surgical_b_brainonly.py` — the brain-only per-conversation
  hard checks on a REAL regressed-transcript shape, kernel ON: ITEM-1 contract
  (`assemble_outbound_instructions` provides ONLY the system prompt — router/speech
  tripwires assert it touches NEITHER), single greeting (1 `OPENING:`, 0 greeting cues),
  no username-repeat (per-turn suffix carries no greeting / no name re-intro; the env
  hack `OPENER_ALREADY_SAID` is NOT reintroduced ON — the kernel prompt owns it), no
  double-greet (cue total <=1 across WARM + all turns), smarter-brain proof (vendor flow
  + lossless C3-fenced brief + no self-label + injection HACKED stays fenced), language
  tracks the caller both ways (hindi→english→keep-prior→hindi), and the W17 named gates
  R1/R2/R3/R5/R7/R10 + full `run_all_gates().passed`. **14 tests, PASS.**

### Incidental fix
- `voice_ops/config/tests/test_config.py::test_no_droplet_or_agent_imports` — was
  flaky under full-run ordering (it inspected GLOBAL `sys.modules`, which an earlier
  test polluted with `sqlalchemy`). Fixed to measure the DELTA of importing
  `voice_ops.config` (stronger, correct formulation). `voice_ops.config` is genuinely
  SDK-free at import (verified in a clean process). Keeps the "0-droplet imports green"
  requirement reliable.

### Verification (this wave)
- `python -m pytest voice_kernel/ voice_ops/` ⇒ **895 passed** (0 fail). (Was 875
  passed / 1 ordering-fail before; +19 new tests, +1 ordering fix.)
- `run_all_gates().passed` ⇒ **True**; failing gates **[]**. R1/R2/R3/R5/R7/R10 all PASS.
- 0-droplet at load: importing `voice_kernel.integrations.outbound` +
  `voice_ops.eval.regression_gates` leaks NO `droplet_work`/`agent`/`caller`/
  `livekit`/`redis`/`boto3`/`sqlalchemy` into `sys.modules`. Verified **[]**.
- Offline transcript replay (regressed shape): single greeting + no username-repeat +
  no double-greet + language adapts ⇒ all invariants PASS.

### The clean split this wave enforces
- **BRAIN (changed by A+B+C):** the `instructions` system-prompt STRING only.
- **VOICE (never touched — D/E/F/G omitted):** `elevenlabs.TTS` (`QTKSa2Iyv0yoxvXY2V8a`
  @ stability 0.45 / speed 1.08), `sarvam.STT`, `groq.LLM`, `AgentSession` (VAD/timing/
  interruption), opener `session.say()`, the language mirror, the post-call write.
- OFF (default) ⇒ `instructions == base_instructions` ⇒ byte-identical to `98655dbf`.

## Phase: DEPLOY — NOT DONE (founder-gated, separate)
The `KERNEL_OUTBOUND` flip is the separate, most dangerous, founder-gated step
(W-VOICE-SURGICAL-PLAN Part C). Runbook in
`design/W-INT-OUTBOUND-PATCH-BRAINONLY.md §5`: pre-flight backup → apply A+B+C +
deploy `voice_kernel/` (flag OFF) → OFF-identity real ring → W17 + replay green →
flip via **systemd drop-in (NOT shared `.env`)** → real-call canary (single greeting,
name once, no "AI assistant", voice unchanged) → instant `KERNEL_OUTBOUND=0` revert if
any regression (no voice risk — D/E omitted). The founder's REAL outbound ring is the
only acceptance truth.

## NEXT
- (Founder) validate Part A first (the "AI assistant" → "{company} से" fix), THEN gate
  the Part B `KERNEL_OUTBOUND` flip per the runbook.
- (Later, separate ring-gated waves) Patch D (Sarvam router), E (per-turn RAG inject),
  F/G (post-call + box memory) — each with its own canary; NOT part of brain-only.
