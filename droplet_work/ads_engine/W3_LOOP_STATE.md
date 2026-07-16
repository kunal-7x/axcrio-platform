# W3 — Parity Optimization Loop (build state)

Branch feat/elevatex-ad-engine · worktree elevatex. EARNER-SAFE: propose-only, dry-run default,
fail-closed guardrails, NO new spend authority, no agent.py/voice/caller edits beyond the one
additive sub-router registration in endpoints.py.

REUSE (do NOT rewrite): optimization.py (TTTS bandit + GP-UCB/knapsack), guardrails.py
(fail-closed chain), feedback.py (emit_quality CAPI), tick.py (detached bounded loop),
store.py (tenant-scoped accessors), orchestrator.py.

## Units (commit per unit: `ads/v2-w3: <unit>`)
1. [DONE] store.py minimal edit — register ad_events (per-tenant) + audience_state / fatigue_state /
   learning_state / reallocation_state (collections) + thin ad_events accessors.
2. [DONE] ad_events.py — conversion-signal substrate: pixel/server event ingest (append-only,
   idempotent), quality mapping -> feedback.emit_quality same-day CAPI, signal aggregation
   feeding optimization.update_arm (qualified/hot, not form-submit).
3. [DONE] fatigue.py — CTR/engagement decay detection + auto-rotation proposal; >70% delivery-share
   guard; rotate before aggregate ROAS drops (leading CTR indicator).
4. [DONE] audience.py — autonomous audience expansion: seed -> new converting segments, soft ceiling,
   proposal-only + guardrailed.
5. [DONE] learning_phase.py — learning-phase state/awareness (50 conv/7d Meta thresholds, do_not_edit,
   UI-facing status); writes learning_lock into guardrail_state.
6. [DONE] continuous.py — continuous optimization daemon: feed live ad_events signals -> bandit reward,
   propose_allocation reallocate-to-winners through guardrails (dry-run), reversal_payload on every
   move, + fatigue/audience/learning/capi sub-passes. Called by tick on a cadence (minimal edit).
7. [DONE] routes_optimize.py — NEW sub-router (events ingest, learning status, fatigue, audience,
   reallocation preview) + one additive register() line in endpoints.py.
8. [DONE] _smoke_w3_loop.py — signal->reallocate dry-run; fatigue rotate; audience proposal; learning
   phase; ad_events idempotency. Run ALL ads_engine smokes. py_compile clean.

VERIFY: all `_smoke_*` green + new smoke green; py_compile clean; earner untouched.
