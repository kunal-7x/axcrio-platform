# W14 — Real-Time Reporting + AI-Manager Live Data — BUILD STATE

Branch: fix/realtime-voice-kernel-v2 (per EARNER LAW; prompt also names fix/realtime-voice-kernel-v2)
Earner-safe: 0 droplet/agent imports, all lazy. Reuse W8 EventBus + W7 lifecycle.
Baseline pytest (voice_ops + voice_kernel): 497 passed.
Python: C:/Users/kunal/AppData/Local/Python/bin/python (3.14.3, pytest 9.0.3) — repo .venv is broken.

## PLAN (units, each verified + then next)
1. voice_ops/reporting/ — real-time reporting data layer  [IN PROGRESS]
   - daterange.py   : presets (today/yesterday/7d/30d/this-month/prev-month/custom) -> UTC [from,to) windows, vendor-tz aware (reuse timeutil)  [DONE]
   - model.py       : canonical FactCall record + funnel stage map + lifecycle/source/status enums  [DONE]
   - store.py       : tenant-scoped read-model store; injectable backend (in-mem default; PG lazy). available()/upsert/query  [DONE]
   - aggregate.py    : pure aggregation — totals, funnel math, drill-down filters, agent/source/follow-up analytics, daily timeline  [DONE]
   - consumer.py     : W8 SinkConsumer handler -> materialize FactCall from events (call_*, summary_ready, lead_*, callback, booking, whatsapp)  [DONE]
   - service.py      : query API surface (date-range recalculated per range, drill-down, funnels, timeline)  [DONE]
   - config.py       : ReportingConfig (vendor tz, flag, backend)  [DONE]
   - __init__.py
   - tests/          : date-range recalculation, drill-down filters, funnel math, tenant isolation, consumer materialize  [DONE]
2. voice_ops/ai_manager_live/ — AI-Manager live-data adapter  [DONE]
   - adapter.py     : answers operational questions FROM reporting layer (not stale cache)  [DONE]
   - commands.py    : parser ("send today's report","show hot leads","campaign X perf")  [DONE]
   - summary.py     : daily executive summary generator (totals + hot-lead names + AI summaries + next actions)  [DONE]
   - delivery.py    : WhatsApp-ready deliver to registered number (dormant until WA creds)  [DONE]
   - service.py     : top-level façade tying parser->adapter->summary->delivery  [DONE]
   - config.py
   - __init__.py
   - tests/          : AIM returns LIVE numbers matching reporting layer; commands parse; daily summary lists hot leads + next actions; tenant-isolated  [DONE]
3. design/W14-REPORTING-AIM-SEAM.md  — caller.py/worker + panel API seam DOC + UI contract for W15  [DONE]
4. memory/wave_runs/W14-reporting.md — append run record  [DONE]

## DECISIONS
- READ-MODEL approach: events -> a per-tenant FactCall read-model (one row per call, latest-wins on
  call_id) maintained by a SinkConsumer. Query API aggregates that read-model per requested date range.
  This is the "nothing updates in real time" fix: push (events) replaces poll; queries are O(rows-in-range).
- Backend is injectable: default in-memory dict (CI/tests + safe fallback); a PG-backed store can be
  injected on the box later (lazy, never imported at module load — mirrors booking/store.py).
- All timestamps canonical UTC; date-range windows + day-grouping computed in VENDOR tz via timeutil
  (fixes the off-by-one "1 day ago" bug). Range windows are half-open [from, to).
- AI-Manager live reads go THROUGH reporting.service (the same aggregates the dashboard sees) — so the
  manager can NEVER answer from a stale separate cache. This is founder pain #2.
- Funnel stages (8): uploaded -> dialed -> connected -> interested -> warm -> hot -> booked -> converted.
- WhatsApp delivery is a pluggable sender; dormant (returns queued/not_configured) until WA creds wired.

## DONE — ALL UNITS COMPLETE + GREEN
- voice_ops/reporting/ + voice_ops/ai_manager_live/ built (TRACKED, 0 droplet/agent imports, verified).
- pytest voice_ops/reporting/ = 37 passed; voice_ops/ai_manager_live/ = 25 passed (62 new).
- FULL pytest voice_ops/ + voice_kernel/ = 607 passed (baseline 497).
- design/W14-REPORTING-AIM-SEAM.md written (caller/worker seam + panel API + W15 UI contract).
- memory/wave_runs/W14-reporting.md appended.
