# W17 — VOICE-BRAIN EVAL HARNESS (the deploy gate)

**Status:** BUILT + GREEN + RED-TEAM-HARDENED (798 passed across `voice_ops/` +
`voice_kernel/`; 67 in `voice_ops/eval/`). Branch `fix/realtime-voice-kernel-v2`.
Tracked, disjoint, droplet-free.

> **Red-team fold (B1/B2/B3 — blockers fixed before this could be the deploy gate):**
> The first cut passed all gates but three were not HONEST — they passed vacuously
> or tested a tautology, so a regressed brain could still pass.
> - **B1 — R1 was not airtight (the #1 rule had a hole).** The block-list omitted
>   ROBOT / AUTOMATED SYSTEM / MACHINE / COMPUTER PROGRAM / VIRTUAL BEING and the
>   Gujarati/Tamil/Telugu script forms, so a vendor `ai_disclosure="I am an automated
>   system, a robot"` survived verbatim into the SPOKEN disclosure. FIX: expanded
>   `disclosure.BANNED_PHRASES` to every self-label form + language; the structural
>   builder already routes the vendor line through the (now-wider) block-list, so the
>   banned line is rejected → clean Tier-0 fallback. Negative controls feed each form
>   THROUGH the kernel gate (parametrized) + a monkeypatched leaky builder proves the
>   gate FLIPS TO FAIL when a banned label actually reaches the spoken line.
> - **B2 — R2 could not fail (echo, not override).** The kernel pastes the parsed
>   script into the `<campaign_brief>` fence, so "hook in prompt" was True for ANY
>   non-empty script and the real regression (vendor script IGNORED, default flow
>   used) was undetectable. FIX: R2 now asserts the hook drives a FLOW SLOT
>   (`TALKING POINTS:`/`QUALIFYING`/`OBJECTIONS`/`CLOSING` — the slots the parsed
>   stage structure feeds via `context_engine._apply_vendor_script`), via
>   `hook_drives_flow()`. Negative control monkeypatches an echo-only prompt and
>   proves the gate flips to FAIL ("present but NOT on a flow slot").
> - **B3 — R5 was vacuously green.** Greeting-cue count is 0 on every golden, so
>   `hits > 1` could never trip and a "zero opener" regression also passed. FIX: R5
>   now asserts EXACTLY ONE structural `OPENING:` directive (not 0 = missing opener,
>   not >1 = double opener) + the surplus-fresh-greeting-cue check. Negative controls
>   run THROUGH the gate on a double-opener AND a missing-opener prompt and prove both
>   flip to FAIL.

## Why this exists
A live voice cutover regressed the earner before: the brain said "AI assistant",
ignored the vendor script, lost the campaign brief, silently swapped TTS away from
the selected Sarvam, double-greeted, drifted to English-only, spoke literary Hindi,
and pushed a sale in a support call. Per-component green reports masked it.

**W17 is the gate that makes that impossible to ship again.** It encodes the
founder's hard regression list as AUTOMATED ASSERTIONS over the REAL kernel output
and runs them in CI. A deploy is allowed **only** when every gate is green on the
current (fixed) kernel — and the same gates are PROVEN to FAIL on deliberately
broken fixtures (negative controls), so a green suite means the brain is actually
good, not that the gate is asleep.

## Where it lives
```
voice_ops/eval/
  __init__.py            package doc + public surface
  verticals.py           GOLDEN conversation sets per vertical + negative-control fixtures
  regression_gates.py    the 10 founder rules as gates + the repo-wide #1 scanner + run_all_gates()
  replay.py              the CALL-REPLAY scaffold (recorded transcript -> kernel -> invariants)
  metrics.py             TTFA / tokens / cost-per-appointment collector
  tests/
    test_regression_gates.py   10 gates green + negative controls bite
    test_golden_replay.py      per-vertical replay + cross-vertical no-leak
    test_metrics.py            TTFA bound + cost-per-appointment unit metric
    test_import_isolation.py   zero droplet/heavy-SDK imports
```

## How it drives the brain (earner-safe by construction)
It NEVER imports, restarts, or mutates `droplet_work/agent.py` or any box. It drives
the kernel ONLY through the tracked integration façade
`voice_kernel.integrations.outbound` — the SAME seam the live agent uses — turning the
`KERNEL_OUTBOUND` flag ON in-process for the duration of a gate run (and restoring
it after) via `kernel_outbound_on()`. Every kernel/impl import is LAZY, so importing
`voice_ops.eval` and running a full gate batch pulls **zero** `droplet_work` modules
and zero heavy SDKs (asserted by `test_import_isolation`). A green gate therefore
proves the REAL cutover path, never the box itself.

Entry points used (verified stable, mirror `test_outbound_integration.py`):
- `build_for_call(...)` → `OutboundKernel` (kernel ON).
- `assemble_outbound_instructions(ik, legacy_render=...)` → the WARM system prompt.
- `on_turn(ik, user_text=, detected_lang=)` → `{reply_lang, tts_lang, lang_switched, ...}` (HOT).
- `choose_tts(ik)` / `plan_speech(ik, ...)` → provider + speech plan.

## The gate list (the founder's regression list, R1..R10)
| Gate | Founder rule | What it asserts over the kernel |
|------|--------------|---------------------------------|
| **R1** | NEVER says "AI assistant" / any AI self-label — **#1 rule** | No banned self-label (AI / bot / **robot / automated system / machine / computer program / virtual being**, in English/Hinglish/**Gujarati/Tamil/Telugu**) in the SPOKEN disclosure of every golden vertical × language (`strip_guardrail` + `contains_banned_phrase`); a banned vendor `ai_disclosure` is rejected → clean Tier-0 fallback; no banned self-intro instruction in the rendered prompt. |
| **R1-repo** | #1 rule, **repo-wide** | `scan_repo_for_ai_self_label()` greps the shipped voice-prompt sources (`disclosure.py`, `context_engine.py`, `packet.py`, legacy `prompt.py`) for a hard-coded *instruction to say* the banned label (speech-verb + token); block-list entries / prohibitions are allowed. |
| **R2** | Vendor script OVERRIDES the default flow | The vendor hook **drives a FLOW SLOT** (`TALKING POINTS`/`QUALIFYING`/`OBJECTIONS`/`CLOSING`) — proving the parsed stage STRUCTURE shaped the rendered flow, not merely echoed in the brief blob (`hook_drives_flow`). |
| **R3** | Campaign brief NOT lossy | The full brief marker reaches the prompt AND sits INSIDE the `<campaign_brief>` C3 fence (lossless + untrusted-fenced). |
| **R4** | Selected TTS provider actually used | `choose_tts` resolves the golden's `expect_provider` (lean/standard→Sarvam, growth/premium→ElevenLabs); the choice flows to the speech planner (no silent swap). |
| **R5** | EXACTLY ONE greeting | The rendered prompt carries **exactly ONE** structural `OPENING:` directive (not 0 = missing opener, not >1 = double opener) AND ≤ 1 fresh-greeting cue (no double opener by another door). |
| **R6** | NEUTRAL pace/loudness | `apply_prosody` at kernel output injects NO verbal-nod filler by default (neutral) and leaves price/booking SENSITIVE lines byte-clean. |
| **R7** | Language ADAPTS per turn; keeps prior; never English-only | Multi-turn `on_turn` replay tracks the caller Hindi↔English↔Hinglish turn-by-turn against each golden's `expect_lang`; a 1-word filler KEEPS prior; turn-0 is never cold-forced to English. |
| **R8** | No half-words | `repair_truncation` + `split_sentences` leave no dangling partial token on mid-word stream cuts. |
| **R9** | Casual Hinglish grammar | `enforce_casual_hinglish` replaces literary Hindi (mahatvapurn→zaroori); `has_literary_hindi` flags a literary input and not the cleaned one. |
| **R10** | Cross-vertical isolation | A non-selling mode (support/complaint/feedback/booking/reminder) carries NO sales-push directive; real-estate vocabulary never leaks into a non-real-estate call's VERTICAL TERMS. |

## Golden conversation sets (per vertical)
`verticals.GOLDEN_SETS` — 5 self-contained, PII-free fixtures crafted to exercise the
whole regression list across modes, verticals and languages:
1. **real_estate_sales_lean_sarvam** — canonical earner: vendor script authoritative,
   lean→Sarvam, lossless brief, Hindi→English→(filler keeps prior)→Hindi.
2. **support_ecommerce_premium_elevenlabs** — support must resolve not sell; no
   real-estate leak; premium→ElevenLabs.
3. **reminder_clinic_lean_sarvam** — one calm nudge, zero pressure; Gujarati-script turn.
4. **renewal_insurance_standard_sarvam** — retain/push-value mode; insurance vocab only.
5. **complaint_fintech_lean_sarvam** — de-escalate, never sell.

Each carries `pushes_sale`, `forbidden_vertical_terms`, `expect_provider`, and per-turn
`expect_lang` so the gates and replay assert behaviour, not just shape.

## Call-replay scaffold
`replay.replay_conversation(RecordedCall)` replays a recorded/golden conversation
turn-by-turn through the kernel (WARM prefix once, then HOT `on_turn` per caller
utterance) and re-derives what the brain WOULD have instructed — no call, no box.
It asserts the per-conversation invariants (R1/R2/R3/R5/R7). `recorded_call_from_transcript`
ingests the stored transcript shape (`[{role,text,lang}]` — the same shape
`transcripts/{room}.json` and inbound `ai_manager_sessions` turns use), so ANY real
recorded call can be replayed through the kernel before a deploy.

## Metrics that matter
`metrics.MetricsCollector`:
- **TTFA (core)** — `measure_ttfa_core_ms` times the SYNC, await-free
  `assemble_prefix_core` (the brain's TTFA share; the opener fires off this with no
  network I/O). The test asserts a wall-clock bound (< 50ms; sub-ms on the box),
  enforcing the kernel's "no await between prefix-core and the opener" contract as a
  measured bound, not a comment.
- **Tokens** — system-prompt footprint via the kernel's own `estimate_tokens`.
- **Cost-per-APPOINTMENT (not per-turn)** — `total_llm_cost / appointments_booked`
  over a batch. A brain cheap per turn that never books is expensive; this is the
  unit-economics number (mirrors the sales-research cost-per-resolved-contact).
  Zero bookings → `None` ("n/a (0 booked)"), surfaced explicitly, never a silent 0.

## How this gates EVERY future voice deploy
1. Before any kernel cutover (flipping `KERNEL_OUTBOUND` / `KERNEL_INBOUND` on the box),
   CI runs `pytest voice_ops/eval/` — **must be green**.
2. `regression_gates.run_all_gates()` returns a `GateReport` whose `.passed` is the
   binary DEPLOY DECISION; `.summary()` is the human report. The cutover script calls
   it and refuses to deploy unless `.passed` (and refuses if `scan_repo_for_ai_self_label`
   trips — the #1 rule is also a static gate).
3. Add the campaign of any newly-onboarded vertical as a golden set; the gates then
   cover it automatically. Replay any real recorded call that regressed to reproduce
   it offline and lock it with a golden + gate.
4. The negative-control tests are part of the suite: they prove each gate still bites,
   so the gate can never silently rot into a no-op.

**This EXTENDS, never replaces, the live earner-gate discipline** (agent.py md5
unchanged, one box-mutating change at a time, integrated real-flow smoke + revert
path). W17 is the pre-deploy proof; the founder's own real call remains the final truth.
