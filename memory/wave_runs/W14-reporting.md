# W14 — Real-Time Reporting + AI-Manager Live Data

**Wave:** W14-reporting (build-only, disjoint, earner-safe)
**Status:** ✅ BUILT + GREEN — NOTHING wired to the earner. Seam DOC written for the
founder-signed wiring wave.
**Branch:** fix/realtime-voice-kernel-v2
**Date (UTC):** 2026-06-18
**Earner NOT touched:** `droplet_work/agent.py` / `caller.py` / `aim_voice_agent.py`
not edited, imported, or restarted. Verified: importing both new packages pulls NO
`droplet_work` / `agent` / `caller` / `livekit` / `psycopg` / `redis` module.

---

## What it solves (founder pains 1–5)
1. "Nothing updates in real time" → an event-fed **read-model** the dashboard
   queries (push, not poll).
2. "AI Manager fetches WRONG details" → the manager reads the SAME live aggregates
   the dashboard does (no separate stale cache).
3. Universal reporting: Today default + yesterday/7d/30d/this-month/prev-month/
   custom, every metric recalculated per range, 6 drill-down dims, 8-stage funnel,
   agent/source/follow-up analytics, daily activity timeline.
4. Daily executive WhatsApp summary (totals + hot-lead names + AI summaries + next
   actions), deliverable to the registered number — dormant until WA creds.
5. AI-Manager WhatsApp command center (deterministic NL parser).

## Files built (all TRACKED, disjoint)
### voice_ops/reporting/
- `__init__.py`, `config.py` (ReportingConfig)
- `daterange.py` — `resolve_range` + `DateRange` (vendor-tz, half-open windows; the
  off-by-one fix). Reuses `voice_kernel.events.timeutil`.
- `model.py` — `FactCall` + `FUNNEL_STAGES` (8) + LeadStatus/CallStatus/BookingStatus.
  LeadStatus mirrors W7 `Lifecycle`.
- `store.py` — `ReportingStore` over injectable `ReportingBackend`
  (`InMemoryReportingBackend` default; PG injected on box later, lazy).
- `aggregate.py` — pure totals/funnel/drill/agent·source·campaign·followup
  analytics/timeline/status-breakdowns/`aggregate`.
- `consumer.py` — `EventReducer` + `build_consumer_handler(store)` (W8 SinkConsumer
  handler; events → FactCall upserts; never raises).
- `service.py` — `ReportingService` (the query API).
- `tests/` — `test_daterange.py`, `test_aggregate.py`, `test_consumer_service.py`.

### voice_ops/ai_manager_live/
- `__init__.py`, `config.py` (AIManagerLiveConfig)
- `commands.py` — deterministic `parse_command` → `Command`.
- `adapter.py` — `LiveAdapter` (metric/totals/report/hot_leads/campaign_performance/
  funnel — all LIVE from ReportingService).
- `summary.py` — `build_daily_summary` → `DailySummary` (+ WhatsApp-ready text).
- `delivery.py` — `ReportDelivery` (`NullWhatsAppSender` default = dormant;
  injectable real sender + number_resolver; fail-closed; masks recipient).
- `service.py` — `AIManagerLiveService.handle()` + `.daily_summary()`.
- `tests/` — `test_commands.py`, `test_live_service.py`.

### Docs
- `design/W14-REPORTING-AIM-SEAM.md` — caller.py/worker seam (reuses W8 emit-sites),
  reporting-consumer worker, panel API routes, and the UI contract for W15.
- `voice_ops/W14_REPORTING_AIM_STATE.md` — build ledger.

## Key design decisions
- **Read-model, not re-query:** events → per-tenant FactCall (latest-wins on
  call_id) → query API aggregates per requested range. Push replaces poll.
- **AI-Manager reads the SAME `ReportingService`** as the dashboard → cannot drift
  to a stale cache (pain #2). `metric()` == `report.totals[key]` by construction
  (asserted in tests).
- **All date math in the vendor tz** (timeutil) on half-open `[from,to)` windows →
  00:30 IST calls bucket on the correct day (the "1 day ago" fix), no double-count.
- **Funnel = cumulative monotone** ("reached at least stage S"); 8 stages
  uploaded→…→converted.
- **Everything injected** (PG backend, WhatsApp sender, number resolver, `now`) →
  zero droplet/agent imports; CI uses in-mem + fakes; WA delivery dormant until creds.
- Reuses W8 EventBus/taxonomy/SinkConsumer + W7 Lifecycle.

## Verification
- `pytest voice_ops/reporting/` → 37 passed.
- `pytest voice_ops/ai_manager_live/` → 25 passed.
- `pytest voice_ops/ voice_kernel/` → **607 passed** (baseline 497 + 110 new).
- End-to-end test drives a real `voice_kernel.events.SinkConsumer` off an
  `InMemoryEventBus` → FactCall materialized → service + AI-Manager return matching
  live numbers; tenant isolation asserted (cross-tenant bleed = 0).
- Tests cover: date-range recalculation per preset, custom range (inclusive `to`),
  off-by-one midnight, half-open contains; all 6 drill-down filters + combined;
  funnel math + step conversion; agent/source/follow-up/timeline analytics;
  consumer reduce/latest-wins/skip-non-call/never-raise; AIM metric==reporting;
  command parsing (send report / hot leads / campaign perf / metric / funnel /
  ranges / deliver); daily summary lists hot leads + next actions; delivery dormant
  + real-sender injected; tenant isolation across reporting + AI-Manager.

## NOT done (the wiring wave — founder-signed, one box-mutating change)
- Wire W8 emits at the caller.py/aim_voice_agent.py sites (per W8 seam) carrying the
  richer payload (lead_name/summary/next_action/campaign/source/agent).
- Stand up the reporting-consumer systemd unit + (recommended) PgReportingBackend
  (FORCE-RLS `reporting_fact_calls`).
- Panel API routes (`/report*`) + SSE bridge + `lib/events.ts` invalidation.
- Replace the AI-Manager `analytics.*` stub with `AIManagerLiveService`.
- Schedule the daily executive summary per tenant (cron/Hatchet, vendor tz);
  inject the real WhatsApp sender + number resolver when Meta WA creds land.
- W15 universal-reporting UI (Core_2 kit) against the §7 UI contract.
---

## VERIFY+COMMIT (2026-06-18)
- Red-team verdict: SHIP, no blockers (5/5 questions clean: date/tz correctness, no stale AIM numbers, tenant isolation, no cross-tenant summary leak, no call-path blocking).
- 611 passed (full voice_ops + voice_kernel); 62 W14-only. agent.py md5 98655dbf unchanged. Zero forbidden imports (runtime check = NONE). gitleaks staged = 0.
- Staged ONLY voice_ops/reporting/ + voice_ops/ai_manager_live/ + design/W14-REPORTING-AIM-SEAM.md + memory/wave_runs/W14-reporting.md + voice_ops/W14_REPORTING_AIM_STATE.md (never git add -A).
- Committed `dfb94a2` on branch fix/realtime-voice-kernel-v2.
