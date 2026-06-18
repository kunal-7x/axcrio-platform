# W17-EVAL — voice-brain EVAL HARNESS (prove the brain BEFORE deploy)

Branch: `fix/realtime-voice-kernel-v2` · Date: 2026-06-18 · Scope: BRANCH-ONLY,
disjoint new package `voice_ops/eval/` (no box edits, no agent/caller import, no
restart). Earner live = `98655dbf` (KERNEL_OUTBOUND=0), untouched. EARNER LAW honored.

## Goal
A harness that PROVES the voice brain is good BEFORE a cutover, so a deploy can
never again regress the live earner. Encode the founder's 10 hard regression rules
as AUTOMATED GATES over the REAL kernel output + golden conversation sets per
vertical + a call-replay scaffold + the metrics that matter (TTFA, cost-per-outcome).

## What shipped (all new tracked files under voice_ops/eval/)
- `verticals.py` — 5 GOLDEN conversation sets (real-estate sales, e-com support,
  clinic reminder, insurance renewal, fintech complaint) + 2 broken-fixture stubs.
  Each set carries fields (drive the kernel), per-turn caller utterances with
  expected mirrored language, `pushes_sale`, `forbidden_vertical_terms`,
  `expect_provider`.
- `regression_gates.py` — the 10 founder rules (R1..R10) as gate functions over the
  kernel + the REPO-WIDE #1 scanner (`scan_repo_for_ai_self_label`) + `run_all_gates()`
  returning a `GateReport` whose `.passed` IS the deploy decision. Drives the kernel
  only through `voice_kernel.integrations.outbound` with `KERNEL_OUTBOUND` flipped
  in-process via `kernel_outbound_on()` (restored after). All imports lazy.
- `replay.py` — CALL-REPLAY scaffold: `replay_conversation(RecordedCall)` runs WARM
  prefix once + HOT `on_turn` per caller turn, asserts R1/R2/R3/R5/R7 end-to-end.
  `recorded_call_from_transcript` ingests the stored `[{role,text,lang}]` shape
  (transcripts/{room}.json / ai_manager_sessions turns) so any real call replays.
- `metrics.py` — TTFA (times the sync await-free `assemble_prefix_core`), token
  footprint, and COST-PER-APPOINTMENT (`total_cost / appointments_booked`, not
  per-turn; None when 0 booked).
- `tests/` — 48 tests: 10 gates green on the fixed kernel + every negative control
  bites; per-vertical replay; cross-vertical no-leak; metrics + import isolation.

## The gate list (founder regression list -> assertions)
R1 no AI self-label (#1; kernel + repo-wide) · R2 vendor script authoritative ·
R3 brief lossless+fenced · R4 selected TTS provider used (Sarvam when selected) ·
R5 exactly one greeting · R6 neutral prosody (fillers off, sensitive lines clean) ·
R7 language adapts per turn / keeps prior / never English-only · R8 no half-words ·
R9 casual Hinglish (no literary) · R10 cross-vertical (support≠sales, no RE leak).

## Verification (REAL, run on disk)
- `pytest voice_ops/eval/` = **48 passed**.
- `pytest voice_ops/ voice_kernel/` = **765 passed, 0 failed** (8.1s).
- `run_all_gates().passed` = True (R1, R1-repo, R2..R10 all green on the fixed kernel).
- EARNER LAW: after `run_all_gates()`, sys.modules has **0** `droplet_work`/`agent`
  modules and 0 heavy SDKs (livekit/boto3/redis/qdrant) — verified.
- Negative controls confirm each gate FAILS on a broken fixture (banned self-label
  instruction, wrong provider, double greeting, forced fillers, wrong expected
  language, dangling token, literary Hindi, support-pushing-sales, real-estate leak).
- TTFA core measured sub-millisecond (<50ms bound enforced); cost-per-appointment
  computed over the golden batch (2 booked of 5).

## Learnings (banked)
- The kernel resolves the industry pack by `industry` field matching pack id /
  LABEL / a `match` keyword — a bare `industry="real_estate"` matches NOTHING (id is
  `real_estate.v1`, label is "real estate" with a space); use a real match keyword
  (e.g. "property") or the label to force a pack. This is exactly why cross-vertical
  leak is rare by default (NEUTRAL pack unless a real keyword hits) — good for safety,
  a trap for a naive negative-control fixture.
- STT language code is AUTHORITATIVE over text-classify in `TurnLanguageResolver`:
  a code-mixed Devanagari+Latin utterance with `stt_lang="hi-IN"` resolves to HINDI
  (not Hinglish). Golden `expect_lang` must reflect the STT-code-wins priority.
- Drive the kernel through the integration façade (the agent's real seam), NOT the
  adapter's fresh Null-impl kernel — the façade wires the real W2-W7 impls.

## RED-TEAM FOLD (B1/B2/B3 — folded at VERIFY before this became the deploy gate)
The first cut passed all gates, but the red-team proved 3 were NOT honest (passed
vacuously / tautology) — a regressed brain could still pass. Folded all three:
- **B1 — R1 not airtight (the #1 rule had a hole).** A vendor `ai_disclosure="I am an
  automated system, a robot from F"` survived VERBATIM into the spoken disclosure:
  `BANNED_PHRASES` omitted robot / automated-system / machine / computer-program /
  virtual-being and the Gujarati/Tamil/Telugu script forms (`contains_banned_phrase`
  returned False — proven live). FIX: expanded `voice_kernel/brain_packs/disclosure.py`
  `BANNED_PHRASES` to every self-label FORM + LANGUAGE; the structural builder already
  routes the vendor line through the block-list, so the banned line is now REJECTED →
  clean Tier-0 fallback (proven through the kernel gate). Added a parametrized neg-ctrl
  over all forms + a monkeypatched leaky-builder test that proves R1 FLIPS TO FAIL when
  a banned label reaches the spoken line.
- **B2 — R2 could not fail (echo, not override).** The kernel pastes the parsed script
  into the `<campaign_brief>` fence, so "hook in prompt" was True for ANY non-empty
  script and the negative control was a tautology. FIX: R2 now asserts the hook drives
  a FLOW SLOT (`TALKING POINTS`/`QUALIFYING`/`OBJECTIONS`/`CLOSING` — fed by the parsed
  stage structure in `context_engine._apply_vendor_script`) via the new
  `hook_drives_flow()`. Neg-ctrl monkeypatches an echo-only prompt → gate FAILS
  ("present but NOT on a flow slot"); + a unit test of the echo-vs-override discriminator.
- **B3 — R5 vacuously green.** Greeting-cue count is 0 on every golden, so `hits > 1`
  never tripped and a "zero opener" regression also passed. FIX: R5 now asserts EXACTLY
  ONE structural `OPENING:` directive (not 0 = no opener, not >1 = double) via
  `_count_openers()` + keeps the surplus-fresh-greeting-cue check. Neg-ctrls run THROUGH
  the gate on a double-opener AND a missing-opener prompt → both FAIL.

Re-verified after the fold: `pytest voice_ops/eval/` = **67 passed** (was 48; +19 neg-ctrls).
`pytest voice_ops/ voice_kernel/` = **798 passed, 0 failed**. `run_all_gates().passed`=True
(R1, R1-repo, R2..R10 all green). EARNER LAW: 0 droplet_work/agent + 0 heavy-SDK imports
after `run_all_gates()` (re-verified). The B1 fix touches the DORMANT kernel
(`disclosure.py`; KERNEL_OUTBOUND=0 live), so the live earner (98655dbf) is unaffected.

## Docs
- `design/W17-EVAL-HARNESS.md` — full gate spec + how it gates every future deploy.
- `W17_EVAL_STATE.md` (repo root) — crash-safe build ledger.
