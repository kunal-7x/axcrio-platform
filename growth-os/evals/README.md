# evals/ — agent & optimizer eval harness (§22)

Autonomous spend = paranoia. This is where correctness is *proven*, not asserted.

Planned suites (land with their phase, §21/§22):
- **agent evals** — 20+ golden campaign requests per industry → CIB graded against a rubric (§9.3).
- **optimizer replay evals** — historical metric streams replayed → assert guardrails G1–G6 fire,
  learning phases respected, kill precision/recall, counterfactual ₹ saved (§12, §14.3).
- **money chaos tests** — runaway-CPM → sentinel pauses within 1 tick; duplicate webhooks → no
  double-signal (§13.2, §22).
- **compliance fixtures** — planted RERA-less / health-overclaim / finance-promise → all blocked (§10.9).
- **signal-quality evals** — dedup ≥90%, EMQ ≥8 on the optimization event, latency p95 <15min (§11.3).
- **load** — 4h ingest @ 1k accounts; webhook burst 100/s (§22).

Phase-0 = placeholder. The drift-check + schema-validate gates (run in CI now) are the first
"eval" the repo enforces; the rest land as the brains/optimizer come online.

## golden/
Golden fixtures (committed) live under `evals/golden/` per suite. Empty in Phase 0.
