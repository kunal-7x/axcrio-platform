# W17 EVAL HARNESS — build state (crash-safe ledger)

Branch: fix/realtime-voice-kernel-v2  | EARNER LAW: never edit/import/restart agent or box.
Build DISJOINT tracked code under `voice_ops/eval/` only. REUSE voice_kernel + W-VOICE-FIX gate.

## SEAM (verified)
- Drive kernel via `voice_kernel.integrations.outbound` (and `.inbound`):
  - `build_for_call(... )` needs KERNEL_OUTBOUND=1 (monkeypatch); else None.
  - `assemble_outbound_instructions(ik, legacy_render=...)` -> system prompt string.
  - `on_turn(ik, user_text=, detected_lang=)` -> {reply_lang, tts_lang, lang_switched, rag_suffix, ...}
  - `choose_tts(ik)` -> ProviderChoice(.tts).
- fields levers: use_case (override wins), industry, raw_script (vendor authoritative),
  product_summary (fenced brief), plan (lean->sarvam / premium->elevenlabs).
- Banned-phrase scanner: voice_kernel.brain_packs.disclosure.contains_banned_phrase / strip_guardrail.

## PLAN / UNITS (flip DONE as each verifies)
1. [DONE] voice_ops/eval/__init__.py
2. [DONE] voice_ops/eval/verticals.py — golden conversation sets per vertical
3. [DONE] voice_ops/eval/regression_gates.py — 10 founder rules + repo-wide #1 scanner
4. [DONE] voice_ops/eval/replay.py — call-replay scaffold
5. [DONE] voice_ops/eval/metrics.py — TTFA / tokens / cost-per-outcome
6. [DONE] voice_ops/eval/tests/test_regression_gates.py — 10 gates pass + negative controls FAIL
7. [DONE] voice_ops/eval/tests/test_golden_replay.py — replay + cross-vertical no-leak
8. [DONE] voice_ops/eval/tests/test_metrics.py + test_import_isolation.py
9. [DONE] design/W17-EVAL-HARNESS.md
10. [DONE] memory/wave_runs/W17-eval.md append

## VERIFY
- `pytest voice_ops/eval/` = 48 passed. `pytest voice_ops/ voice_kernel/` = 765 passed, 0 failed.
- Earner law: 0 droplet_work/agent/heavy-SDK imports after run_all_gates() (verified).
- 11 gates green on fixed kernel (R1, R1-repo, R2..R10); every negative control bites.

## RED-TEAM FOLD (B1/B2/B3) — DONE at VERIFY
- [DONE] B1: expanded `voice_kernel/brain_packs/disclosure.py` BANNED_PHRASES to robot/
  automated-system/machine/computer-program/virtual-being + Gujarati/Tamil/Telugu forms;
  vendor banned `ai_disclosure` now rejected -> Tier-0 fallback. +parametrized neg-ctrl +
  monkeypatched leaky-builder test (R1 flips to FAIL).
- [DONE] B2: R2 now asserts hook drives a FLOW SLOT (`hook_drives_flow`), not echo. Neg-ctrl
  monkeypatches echo-only prompt -> R2 FAILS.
- [DONE] B3: R5 now asserts EXACTLY ONE `OPENING:` directive (`_count_openers`); neg-ctrls
  on double-opener + missing-opener -> both FAIL.
- RE-VERIFY: `pytest voice_ops/eval/` = 67 passed (was 48). `voice_ops/ voice_kernel/` = 798
  passed, 0 fail. run_all_gates().passed=True. Earner law re-verified (0 box/heavy imports).
  B1 touches DORMANT kernel (KERNEL_OUTBOUND=0 live) -> earner 98655dbf unaffected.
