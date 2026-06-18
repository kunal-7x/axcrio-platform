# W-VOICE-HEART — build the kernel-driven outbound voice heart (BUILD wave, no box mutation)

> Branch `fix/callback-retry-scheduling`. Baseline before this wave: `python -m pytest
> voice_kernel/ voice_ops/` = **895 passed**. Local `droplet_work/agent.py` md5
> `6c577b9b688169419895909052c08365`; box golden `98655dbf…` (gitignored, box-only).

## GOAL
The KERNEL drives greeting(script-pattern)+conversation+closing on OUTBOUND (LLM, no
hardcode, single greeting, name-sparingly, natural Hinglish, cross-vertical from brief,
auto-language). The OLD worker is reduced to the TTS ENGINE (same voice). Prosody set
CONSTANT (the derived inbound value), no name-emphasis. All gated `KERNEL_OUTBOUND`
(default OFF = byte-identical to box). NO box mutation in this wave — BUILD + tests + the
deployable patch + gated-deploy params only.

## GROUND TRUTH RECONCILED (plan vs red-team)
- W-VOICE-HEART-PLAN says: build the kernel cutover + Hunks H/I/J (suppress worker
  opener/closer/name-inject) + Hunk D (constant prosody 0.45/1.08).
- REDTEAM-OUTBOUND-VOICE-FIX warned: flipping `KERNEL_OUTBOUND` re-introduces the
  double-greet because the kernel prefix has NO opener-already-said + emits an OPENING
  greet directive WHILE the worker still `session.say()`s the opener.
- RESOLUTION: the red-team reviewed the BRAIN-ONLY patch (keeps the worker opener). THIS
  wave SUPERSETS it with Hunk H — the worker opener `say()` is SUPPRESSED on kernel-on, so
  there is exactly ONE speaker (the kernel LLM). The kill-shot is neutralised structurally.
  Belt-and-suspenders: I ALSO add an explicit "single-greeting / no re-greet / name-once"
  directive to the kernel persona so the ON prompt cannot re-greet even by another door
  (closes the red-team's grep-found gap directly), and add W17 gates that BITE on it.
- PROSODY 0.45/1.08: empirically confirmed = the GOOD inbound voice
  (`_inbound_ref/aim_voice_agent.LIVE.py:_build_tts` stability 0.45 speed 1.08). The current
  outbound 0.65/1.0 was tuned to fight a "swing" that was actually the opener/closer speech
  COLLISION (removed by H/I), not low stability. Still env-overridable + drop-in deployed =
  instant revert to 0.65/1.0 if the real ring disagrees. Documented as the one tension.

## UNITS (each verified before the next)
- [DONE] U0 — read plan + red-team + real code; baseline 895 green; md5 confirmed.
- [DONE] U1 — kernel persona: add CLOSING directive + name-once/no-emphasis + single-greet/
  no-re-greet directive (tracked voice_kernel/, inert until flag). Unit tests.
- [DONE] U2 — W17: new gates R11 no-double-intro, R12 name-≤N, R13 no-Mahatvapurn(class),
  R14 LLM-close-not-hardcoded, R15 constant-prosody/no-name-emphasis. Negative controls.
- [DONE] U3 — offline replay of the BAD outbound transcript through the new path:
  regressions GONE (double-greet, hardcoded close, name-every-turn, Mahatvapurn).
- [DONE] U4 — deployable agent.py patch doc (Hunks A+B+C+H+I+J+D), each KERNEL_OUTBOUND-gated;
  static OFF-identity test (hunks outside voice-constructor spans). Drop-in template.
- [DONE] U5 — pytest voice_kernel/ + voice_ops/ green; run_all_gates green; replay green.

## RESULT — DONE (build wave complete, no box mutation)
- pytest voice_kernel/ + voice_ops/ = **931 passed** (baseline 895; +36 new).
- run_all_gates() = **ALL GREEN, 16 gates** (R1-R15 + R1-repo). New: R11 no-double-intro,
  R12 name-≤2x/no-emphasis, R13 no-formal-Hindi, R14 LLM-close-not-hardcoded, R15 constant-
  prosody/no-name-emphasis — each with negative controls that BITE.
- 5/5 golden replays pass; BAD-outbound-transcript replay = all voice-heart regressions GONE
  (R11/R12/R13/R14 True).
- Static OFF-identity proof (test_voice_unchanged_voice_heart.py, 4 pass against REAL agent.py):
  every hunk outside the TTS-engine spans; Hunk D edits ONLY VoiceSettings knobs.

### FILES
TRACKED kernel: voice_kernel/brain_packs/{model.py,provider.py,packs_data.py,delivery.py(NEW)}
  · voice_ops/eval/{regression_gates.py,replay.py} · voice_ops/eval/tests/{test_regression_gates.py,
  test_bad_outbound_replay.py(NEW)} · voice_kernel/integrations/tests/test_voice_unchanged_voice_heart.py(NEW)
  · voice_kernel/systemd/famit-agent.service.d-voice-heart.conf(NEW)
DEPLOYABLE (box agent.py, gitignored): design/W-VOICE-HEART-DEPLOYABLE-PATCH.md (Hunks A+B+C+H+I+J+D).

### GATED-DEPLOY PARAMS (founder-gated, one box-variable at a time)
- Drop-in voice_kernel/systemd/famit-agent.service.d-voice-heart.conf:
  STEP 4 prosody-only: EL_STABILITY=0.45, EL_SPEED=1.08, EL_SIMILARITY=0.80 (derived from the
  GOOD inbound voice; env wins -> instant revert to 0.65/1.0 if the real ring swings).
  STEP 5 flip brain: uncomment KERNEL_OUTBOUND=1 (scoped to famit-agent only, never shared .env).
- OFF (default) = byte-identical to box 98655dbf. Worst case at flip = old brain + perfect voice
  (TTS engine + voice_id QTKSa2Iyv0yoxvXY2V8a never touched).
- ONE behavioral unknown to verify on the canary: session.generate_reply() greeting kickoff on
  the box's pinned livekit-agents version (Hunk H fails OPEN to model turn-1, never crashes).
