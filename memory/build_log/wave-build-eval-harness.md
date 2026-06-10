# WAVE — OFFLINE EVAL / REPLAY HARNESS (the model-swap & fine-tune GATE)

Spec: `caps/design/eval-harness.md`. Package: `caps/droplet_work/eval/`.
Mandate: **a materially-worse model/prompt MUST make the gate exit non-zero**, offline +
read-only on prod data, structurally call-free (never imports caller.py dial loop / agent.py
session path; only pure fns `prompt.build_system_prompt` + `langdetect` + a verbatim classifier copy).

---

## RECONCILE (resume after the prior agent's socket crash)

The prior EVAL-ENG agent built the **entire** package before crashing and recorded it in
`eval/STATE.md` (U1–U6 marked DONE + "PROVEN ON BOX"). On resume I found:

- All spec files present under `caps/droplet_work/eval/` (config, corpus, labels, scorers,
  groq_client, replay, judge, gate, run_eval, selftest_bad_model, 7 scenarios, tests/, README,
  STATE) — plus `.pyc` caches (modules had been imported/run).
- A frozen baseline already on disk locally: `droplet_work/eval_data/eval/baselines/prod_live.json`
  (frozen on the BOX 2026-06-09T13:30Z against `meta-llama/llama-4-scout-17b-16e-instruct`,
  judge `llama-3.3-70b-versatile`, 31 turns: p95 1332ms / lang .968 / monologue .419 / judge 3.387).
- Local read-only data: `droplet_work/eval_data/` = 68 transcripts + calls.json + campaigns.
- `memory/build_log/wave-build-eval-harness.md` did NOT exist (crash hit before it was written) —
  this file is it. `memory/brain/` did not exist — created (see `brain/eval-harness.md`).

**Crucial reconciliation point:** STATE.md's "PROVEN ON BOX" is the *prior* agent's on-box result.
This resume is **offline-only / no live box** per task constraints, so I could NOT re-verify the
on-box exit-0 same-config claim myself. I independently re-verified everything reproducible OFFLINE
(below). The box claim is recorded as the prior agent's, not re-asserted as mine.

---

## WHAT WAS DONE THIS RESUME (verification, offline, no live box touched)

No source files were edited — the package was already complete and faithful to the spec. Work this
resume = **independent offline verification** of the deliverable + writing this log + brain.

Code-review pass (read every module against the spec, all match):
- `labels.classify_outcome` is **byte-identical** to live `caller.py:_classify_outcome`
  (now at caller.py:909; spec cited :862 — line drifted, logic verbatim-in-sync). ✓
- `replay.build_eval_context` reconstructs prod's instruction assembly: `build_system_prompt(fields)`
  + appended `LEAD NAME` line, recap omitted (R2), `[system] + _to_openai(turns[0:i])`. ✓
- `groq_client.complete` posts `max_tokens=140` to raw `/chat/completions` (NOT
  `max_completion_tokens` — B4/S1 honored); 429/5xx → backoff + key-rotate + `latency_clean=False`. ✓
- `gate.evaluate` = absolute latency p95 ceiling (clean samples only) + zero-tolerance guards +
  no-regress language/monologue/judge vs baseline. ✓
- `judge` pinned `llama-3.3-70b-versatile`, temp 0, json_object, anti-circularity guard. ✓

### V1 — deterministic core (pytest, fully offline, no network)
`cd droplet_work && python -m pytest eval/tests/ -q`  → **33 passed in 0.38s** (Python 3.14 local;
box is 3.12.3). Proves scorers (monologue/wrong-lang/guard flagging), corpus loader
(silent/empty/malformed tolerated), and gate math (identical→pass, degraded→fail) work without an LLM.

### V2 — baseline scorecard PRINTS (live Groq, small slice)  [VERIFY req #1]
Ran the full pipeline as the SAME model the baseline was frozen on, vs the frozen `prod_live` baseline.
Env: `GROQ_API_KEY` from `caps/.env.local` (single free-tier key — no separate `EVAL_GROQ_API_KEY`),
`EVAL_VAR_DIR=droplet_work/eval_data` (fixes a CWD-relative path-doubling gotcha — see GOTCHAS).
Cmd: `run_eval --candidate-model meta-llama/llama-4-scout-17b-16e-instruct --baseline prod_live
--include-transcripts --max-transcripts 3 --max-turns 3 --judge`

Scorecard printed (run `20260609T145608Z`), 7 scenarios + 3 transcripts, 16 turns (16 ok):
```
faithful:  valid=True (12/12)              <- context reconstruction CORRECT
latency_ms (clean only): p50=None p95=None  (n_clean=0, excluded=16)   <- box-only metric, see below
language_match_rate: 1.0      [PASS]  (baseline .968, ε .03)
monologue_rate:      0.25     [PASS]  (baseline .419)
guard_violations:    0        [PASS]
judge: overall=3.25           [PASS]  (baseline 3.387, ε .3 → floor 3.087)
GATE: FAIL (exit 1)  — only because latency_p95_ceiling FAILed (no clean samples)
```
**All FOUR quality no-regression checks PASS vs the box baseline.** CAVEAT (README open-risk #8,
paired-corpus discipline): this run used a smaller slice (`--max-transcripts 3 --max-turns 3` → 16
turns) than the freeze (6 transcripts / 31 turns), so these no-regression passes are *suggestive*,
not a rigorous "no false-positive" demonstration — the no-regress checks are only strictly paired when
candidate and freeze share identical `--max-transcripts`/`--max-turns`. A clean exit-0 same-config
(the real no-false-positive property) needs BOTH the box (for latency) AND matched corpus params.
The gate exited 1 ONLY on latency, which is **un-measurable offline** (see GOTCHAS / README
lines 136-149): every one of the 16 calls hit a 429 → backoff → retry on the single free-tier key
from a home box, so each sample is `latency_clean=False` and `p95=None`. Confirmed in the run JSON:
`ok=16, latency_clean=True for 0/16` (final-attempt gen_ms were 1.4–2.4s, but all preceded by a 429
backoff → correctly excluded). VERIFY req #1 ("run on baseline → prints scorecard") = **MET**; it does
not require exit 0, and exit 0 is structurally impossible offline because of the latency artifact.

### V3 — deliberately-worse candidate FAILS the gate (the MARQUEE proof)  [VERIFY req #2]
`python -m eval.selftest_bad_model --baseline prod_live --max-transcripts 2 --max-turns 2`
→ **SELFTEST_EXIT=0**  (== the gate correctly REJECTED every bad config; the script inverts+asserts).

```
[guard_bait]      REJECTED — caught_by: [latency_p95_ceiling, guard_violations_zero_tolerance,
                  monologue_no_regress, judge_overall_no_regress]
                  metrics: lang 1.0, monologue 1.0, guard_violation_count=12, judge_overall=2.818
[prompt_stripped] REJECTED — caught_by: [latency_p95_ceiling, guard_violations_zero_tolerance,
                  monologue_no_regress, judge_overall_no_regress]
                  metrics: lang 1.0, monologue 0.909, guard_violation_count=1, judge_overall=2.545
guard_bait caught by ZERO-TOLERANCE deterministic check: True
ALL bad configs rejected by the gate: True
SELF-TEST PASS (exit 0) — the gate has teeth
```

**TEETH ARE LATENCY-INDEPENDENT** (the key discriminator): both bad configs are caught on
**quality axes that do not involve latency** — `guard_bait` on `guard_violations_zero_tolerance`
(12 guarantee-promise violations injected; deterministic zero-variance check) and `monologue_no_regress`
(1.0 vs .419); `prompt_stripped` on `monologue_no_regress` (.909, long English dumps with length/lang
rules stripped) + `judge_overall_no_regress` (2.545 vs 3.387). Strip the latency check entirely and
**both still FAIL**. This is the master-plan PHASE 3 criterion "a worse model/prompt must FAIL the
harness," proven offline.

---

## BASELINE SCORECARD (frozen `prod_live`, on box, by prior agent — the reference)
```
model meta-llama/llama-4-scout-17b-16e-instruct | judge llama-3.3-70b-versatile | rubric v1
corpus: 7 scenarios + 6 transcripts, 31 turns | faithfulness 12/12
latency_ms (clean): p50 615  p95 1332  max 2864  (n_clean 31, excluded 0)   <- measured ON BOX
language_match_rate 0.968 | monologue_rate 0.419 | guard_violation_count 0
judge: objection 3.097 | qualification 3.581 | overall 3.387 (n 31)
gate ceiling LATENCY_P95_CEILING_MS=1865 (~1.4x box p95)
```

---

## GOTCHAS / LEARNINGS (this resume)

1. **`eval` collides with the bash builtin** — `ls .../eval/` in the Bash tool errors with an EOF
   parse error. Use PowerShell or quote differently; or just don't `ls eval` via bash.
2. **Package lives at `droplet_work/eval/`, NOT top-level `caps/eval/`** (STATE.md's "top-level
   tracked" plan was not realized). `prompt.py`/`langdetect.py` sit beside it at `droplet_work/`.
   So run `python -m eval.<x>` **from inside `droplet_work/`** so both the package and the sibling
   imports resolve. (conftest.py adds droplet_work to sys.path for pytest only.)
3. **CWD-relative path doubling** — `config.var_dir()` walks up from the package and joins
   `droplet_work/eval_data`. Run from inside `droplet_work/` and it computes
   `droplet_work/droplet_work/eval_data` (wrong) → baseline/transcripts not found, gate silently runs
   absolute-only. **FIX: always set `EVAL_VAR_DIR=<abs path to eval_data>`** for local runs. It also
   reroutes run/baseline/audit outputs there. (On the box this is a non-issue — data is at the abs
   `/opt/famit-agent/var`.)
4. **`.env.local` is NOT auto-loaded** by the harness (no dotenv in groq_client; keys read from
   os.environ at import). Export `GROQ_API_KEY` into the process env before invoking.
5. **`.env.local` GROQ_LLM_MODEL=`llama-3.1-8b-instant`** (a *smaller* model) — would override
   `config.PROD_MODEL` and silently change the candidate. **`unset GROQ_LLM_MODEL`** and pass
   `--candidate-model meta-llama/llama-4-scout-17b-16e-instruct` explicitly so the candidate matches
   the baseline's frozen model.
6. **Latency is a BOX-ONLY metric.** A home-box single-free-tier-key run 429-storms → 0 clean samples
   → `p95=None` → latency check always FAILs **regardless of the ceiling value** (it's an
   `is None` branch, not a threshold comparison — bumping `EVAL_LATENCY_P95_CEILING_MS` does nothing).
   Do NOT chase clean local latency or re-freeze for it. Prove teeth on guards/monologue/judge.

---

## STATUS

- **All v1 units (U1–U6) present, faithful to spec, and independently re-verified OFFLINE this resume.**
  Deterministic core 33/33 pytest green. Baseline scorecard prints. Deliberately-bad self-test exit 0
  (gate rejected both bad configs on latency-independent quality axes; guard_bait on the zero-tolerance
  deterministic check). VERIFY reqs #1 and #2 both MET offline.
- **NOT done offline:** the absolute latency-p95 gate cannot be exercised off-box (429 artifact). The
  prior agent's on-box same-config exit-0 + box baseline freeze are recorded as theirs, not re-run here
  (task: no live box). To finalize the latency half, re-run `--freeze-baseline` + `selftest_bad_model`
  on `famit@168.144.153.145` (README §Usage) — that's the only remaining box step, gated behind the
  voice track / off-peak Groq usage.
- **Live system UNTOUCHED:** no caller.py/agent.py edit, no service restart, no call placed; harness is
  read-only + structurally call-free. U7 (optional flag-gated live capture) deferred.
- No git (orchestrator commits).
