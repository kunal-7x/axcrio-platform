# _COST_GUARDS_STATE.md — Wave-3 cost-guards build (IN PROGRESS)

Task: implement + PROVE the 6 cost guards (master plan §6). Each returns PASS/FAIL + file:lines.

## The 6 guards
1. Per-message metering via real wallet.reserve->settle/release (NO wallet.debit)  — engine wiring
2. Per-tenant daily budget ceiling (comm_daily_budget_minor, ~₹500/day -> blocked_budget)
3. Per-contact per-day frequency cap (all channels)
4. Spend-anomaly alert (spend > 3x trailing-7-day median -> founder alert + throttle)
5. Per-(identity,channel) deliverability state (chat_id -> dead on 403)
6. Per-bot async token-bucket (30/s global, 1/s per chat; founder/hot-lead priority lane)

## Plan
- DDL: communication/db/ddl_comm_cost.sql — comm_daily_spend, comm_freq_counter, comm_deliverability (FORCE-RLS, tenant_id TEXT, BIGINT paise) [DONE]
- comm/cost_guards.py — budget ceiling + frequency cap + spend-anomaly + deliverability (DB-backed, RLS, never-raise) [DONE]
- comm/metering.py — per-message reserve->settle/release wrapper over wallet.py [DONE]
- comm/token_bucket.py — async per-bot token bucket + per-chat + priority lane [DONE]
- engine.send wired to: deliverability precheck -> budget/freq precheck -> token-bucket acquire -> metering reserve -> adapter.send -> settle(ok)/release(fail) -> deliverability post (403->dead) [DONE]
- config.py: new flags/caps (budget default 50000 paise=₹500, freq default 8/contact/day, anomaly 3x) [DONE]
- tests: comm/tests/test_cost_guards_offline.py (each guard PASS/FAIL) [DONE]

## Earner law
- All guards default-permissive when their flag/PG unavailable (NEVER block a send on a guard fault).
- Metering reserve fault -> send proceeds at cost 0 (Telegram free) — never crash the detached task.
- NEVER raises; no agent.py import; resting byte-identical (flags OFF / no new env -> old behaviour).

## Status: COMPLETE — see communication/_BUILD-LOG.md (W3-COSTGUARDS)
