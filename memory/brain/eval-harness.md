# BRAIN — Offline Eval / Replay Harness (model-swap & fine-tune GATE)

Durable facts + hard-won learnings for the eval harness. Append, never delete.

## WHAT IT IS
- Package: `caps/droplet_work/eval/` (NOT top-level `caps/eval/`). Spec: `caps/design/eval-harness.md`.
- The GATE that lets us safely swap the voice agent's LLM model/prompt and later fine-tune a LoRA.
  Contract: **a worse model/prompt MUST make the gate exit non-zero.**
- Offline, read-only on prod data, structurally call-free (imports only `prompt.build_system_prompt`,
  `langdetect`, and a verbatim copy of `caller.py:_classify_outcome`). Never dials, never restarts.
- Turn-level / off-policy-aware: for each logged MAIN-LLM assistant turn, rebuild the exact context
  (`build_system_prompt` + appended LEAD NAME line + turns[0:i]), ask the candidate for that turn,
  time + score it in isolation. Opener (turn 0, `_llm_opener`) + scripted closure are EXCLUDED from
  generation but kept as context.

## THE GATE (gate.py, paired vs frozen baseline)
1. `latency_p95_ceiling` — ABSOLUTE, clean samples only. **BOX-ONLY metric.**
2. `guard_violations_zero_tolerance` — count==0 (guarantee_price / claim_human / tts_unspeakable).
3. `language_match_no_regress` — ≥ baseline − 0.03.
4. `monologue_no_regress` — ≤ baseline + 0.03.
5. `judge_overall_no_regress` — ≥ baseline − 0.3 (soft; skippable). Teeth = the deterministic checks.
- 3b FAITHFULNESS is a hard VALIDITY precondition: replay baseline on real turns, assert reply matches
  logged agent in language + ballpark length; fail → run is `invalid` (exit 2), never pass/fail.

## FROZEN BASELINE (the reference, frozen ON BOX by prior agent 2026-06-09)
`droplet_work/eval_data/eval/baselines/prod_live.json`:
model `meta-llama/llama-4-scout-17b-16e-instruct`, judge `llama-3.3-70b-versatile`, rubric v1.
p95 **1332ms** (p50 615, max 2864, 31 clean) | lang **.968** | monologue **.419** | guards **0** |
judge overall **3.387**. Gate ceiling `LATENCY_P95_CEILING_MS=1865` (~1.4x box p95).

## HOW TO RUN (the env that actually works)
From inside `droplet_work/` (so package + sibling prompt.py/langdetect.py resolve):
```
export GROQ_API_KEY=<from caps/.env.local>   # NOT auto-loaded by the harness
unset GROQ_LLM_MODEL                          # .env.local sets it to llama-3.1-8b-instant (wrong model)
export EVAL_VAR_DIR=<abs path>/droplet_work/eval_data   # else CWD path-doubles → data not found
python -m eval.run_eval --candidate-model meta-llama/llama-4-scout-17b-16e-instruct \
   --baseline prod_live --include-transcripts --max-transcripts N --max-turns N --judge
python -m eval.selftest_bad_model --baseline prod_live   # marquee: exit 0 == gate rejected all bad
python -m pytest eval/tests/ -q                          # 33 green, fully offline, no LLM
```

## HARD-WON LEARNINGS (do not relearn these)
- **`eval` is a bash builtin** → `ls .../eval` via the Bash tool fails with an EOF parse error. Use
  PowerShell for listing, or run python from a `cd ... &&` compound.
- **Latency is BOX-ONLY.** A home-box single-free-tier-key run 429-storms every call → 0 clean samples
  → `p95=None` → latency check ALWAYS fails, *independent of the ceiling value* (it's an `is None`
  branch, not a threshold). Bumping `EVAL_LATENCY_P95_CEILING_MS` does nothing. Re-freezing doesn't
  help (absolute, not relative). Measure latency ONLY on the box. Locally, prove teeth on
  guards/monologue/judge — those are clean.
- **Gate teeth are latency-independent** (verified offline 2026-06-09): guard_bait → 12 guard
  violations (zero-tolerance) + monologue 1.0; prompt_stripped → monologue .909 + judge 2.545. Both
  FAIL the gate even with latency removed. So the marquee proof does NOT need on-box latency.
- **No separate EVAL_GROQ_API_KEY** exists today → the harness shares the live key pool. Run small +
  off-peak (the ONE way a read-only harness can still 429 real calls). A separate eval key is the fix.
- Same-config-vs-baseline offline: all 4 quality checks PASS (lang 1.0, mono .25, guards 0, judge 3.25),
  faithfulness 12/12 — only latency "fails" (artifact). The harness logic is sound. CAVEAT: run used a
  smaller corpus slice (16 turns) than the freeze (31) → suggestive, not a strictly-paired no-false-
  positive proof (README open-risk #8: no-regress checks need matched --max-transcripts/--max-turns).
  A clean exit-0 same-config needs BOTH the box (latency) AND matched corpus params. The MARQUEE teeth
  proof is unaffected — guard_bait fails on the absolute, corpus-robust zero-tolerance guard check.

## STATUS / OPEN
- All v1 units (U1–U6) built + faithful + offline-re-verified. U7 (optional flag-gated live capture in
  agent.py) deferred — serialize on the voice track, never two agents on agent.py.
- ONLY remaining real step: re-run `--freeze-baseline` + `selftest_bad_model` ON THE BOX
  (`famit@168.144.153.145`, code `/opt/famit-agent/`, venv `/opt/capsy-agent/.venv`) to exercise the
  latency half + confirm same-config exit 0 in the prod environment. Gate behind off-peak Groq usage.
