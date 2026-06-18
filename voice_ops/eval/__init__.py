"""voice_ops.eval — the W17 VOICE-BRAIN EVAL HARNESS.

A NEW, git-TRACKED, additive, droplet-free harness that PROVES the voice brain is
good BEFORE a deploy — so a kernel cutover can NEVER again regress the live earner.

WHY THIS EXISTS
---------------
The founder's hard regression list (the things that broke on a live cutover) is
encoded here as AUTOMATED GATES that run in CI against the REAL kernel output. A
deploy is only allowed when every gate is green on the current FIXED kernel; the
same gates FAIL on a deliberately-broken fixture (negative controls), so the
harness itself is proven to bite.

THE TEN FOUNDER RULES (each a gate in `regression_gates`):
  R1  NEVER says "AI assistant" / any AI self-label — ANY path/vertical/language
      (the #1 rule; also a REPO-WIDE gate over shipped voice prompt sources).
  R2  Vendor script OVERRIDES the default flow (its hook word reaches the prompt).
  R3  Campaign brief is NOT lossy (full brief context reaches the prompt, fenced).
  R4  The SELECTED TTS provider is actually used (Sarvam when selected, no swap).
  R5  EXACTLY ONE greeting (no double opener).
  R6  NEUTRAL pace/loudness (bounded prosody at kernel output, not just source).
  R7  Language ADAPTS to the user per turn; keeps prior on uncertainty; never
      English-only.
  R8  No half-words (speech planner repairs truncation).
  R9  Casual Hinglish grammar (no "aapne call kiya"-class literary errors).
  R10 Cross-vertical: support does NOT push sales; real-estate language never
      leaks into a non-real-estate call.

HOW IT DRIVES THE BRAIN
-----------------------
It NEVER touches droplet_work/agent.py or any box. It drives the kernel ONLY
through the tracked integration façade `voice_kernel.integrations.outbound`
(and `.inbound`), turning the KERNEL_OUTBOUND flag ON for the duration of a gate
run via the environment — the SAME seam the agent uses, so a green gate means the
real cutover path is good. Every kernel/impl import is LAZY (inside a function),
so `import voice_ops.eval` pulls ZERO droplet_work modules and ZERO heavy SDKs.

PUBLIC SURFACE
--------------
  - verticals:        GOLDEN_SETS, GoldenConversation, GoldenTurn, all_goldens()
  - regression_gates: run_all_gates(), the 10 gate functions, GateResult,
                      scan_repo_for_ai_self_label() (the repo-wide #1 gate)
  - replay:           replay_conversation(), ReplayResult — feed a recorded
                      transcript turn-by-turn through the kernel + assert invariants
  - metrics:          ConversationMetrics, MetricsCollector — TTFA, tokens,
                      cost-per-outcome (cost-per-appointment, not per-turn)
"""
from __future__ import annotations

__version__ = "0.1.0"

__all__ = [
    "__version__",
]
