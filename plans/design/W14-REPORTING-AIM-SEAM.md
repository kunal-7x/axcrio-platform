# W14 — Real-Time Reporting + AI-Manager Live Data: the SEAM

Status: **SEAM NOTE ONLY — NOTHING WIRED TO THE EARNER.** This wave built + tested,
fully disjoint + tracked, two new packages:

- `voice_ops/reporting/` — the real-time reporting **read-model** + query API.
- `voice_ops/ai_manager_live/` — the AI-Manager **live-data adapter** + WhatsApp
  command center + daily executive summary.

The earner is untouched: `droplet_work/agent.py` md5 unchanged, `caller.py` /
`aim_voice_agent.py` not edited. 0 droplet/agent imports (verified: importing both
packages pulls no `droplet_work` / `agent` / `caller` / `livekit` / `psycopg` /
`redis` module). All PG/Redis/WhatsApp dependencies are **injected** lazily.

`pytest voice_ops/ voice_kernel/` = **607 passed** (baseline 497 + 110 across the
two new packages and their deps).

This file is the precise, file:line recipe for the SEPARATE, founder-signed wiring
wave (one box-mutating change at a time, real-flow smoke, revert path). It is the
DOWNSTREAM half of `design/W8-EVENT-SEAM.md` — W8 emits events; W14 consumes them
into a read-model + serves the dashboard/AI-Manager.

---

## 0. The founder problems this closes

1. "Nothing updates in real time" — dashboards/CRM/analytics stale after calls.
   → W14 replaces the flat-file in-memory poll with an event-fed **read-model** the
   dashboard queries; a push (SSE) invalidates the browser cache instantly.
2. "AI Manager fetches WRONG details" — it walks the same stale flat list.
   → `ai_manager_live` reads the **same** reporting aggregates the dashboard does
   (`ReportingService`), so it can never diverge into a stale cache.
3. Universal reporting dashboard — default Today + Yesterday/7d/30d/this-month/
   prev-month/custom, every metric recalculated per range, drill-down by
   campaign/lead-status/source/agent/call-status/booking-status, 8-stage funnel,
   agent/source/follow-up analytics, daily activity timeline.
   → `voice_ops/reporting/{daterange,aggregate,service}.py`.
4. Daily executive WhatsApp summary (totals + hot-lead names + AI summaries + next
   actions) → `ai_manager_live/summary.py` + `delivery.py` (dormant until WA creds).
5. AI-Manager WhatsApp command center (natural language) → `ai_manager_live/
   {commands,service}.py`.

---

## 1. What this wave built (the surface)

### `voice_ops/reporting/`
- `daterange.py` — `resolve_range(preset, now=, frm=, to=, tz_name=)` → a half-open
  `[start_utc, end_utc)` `DateRange`. Presets: `today / yesterday / 7d / 30d /
  this-month / prev-month / custom`. **All day math is in the vendor tz** (reuses
  `voice_kernel.events.timeutil`), so a 00:30 IST call (= 19:00 UTC prev day) lands
  in the right "today" — the off-by-one fix. `DateRange.contains(ts)` is half-open;
  `.vendor_dates()` gives the timeline buckets.
- `model.py` — `FactCall` (one denormalized, latest-wins row per call: dimensions
  campaign/source/agent/lead_status/call_status/booking_status + measures +
  PII-light lead name/masked phone + ai_summary/next_action) and the 8 `FUNNEL_STAGES`
  (`uploaded→dialed→connected→interested→warm→hot→booked→converted`). `LeadStatus`
  mirrors `voice_kernel.packet.Lifecycle` (W7) — reporting records, never reclassifies.
- `store.py` — `ReportingStore` over an injectable `ReportingBackend`. Default
  `InMemoryReportingBackend` (dep-free, thread-safe, latest-wins on `(tenant,call_id)`).
  Tenant-scoped + fail-closed on empty tenant/call id. A PG backend is injected on
  the box later (mirrors `voice_ops/booking/store.py` lazy-load).
- `aggregate.py` — pure functions: `totals`, `build_funnel` (cumulative monotone),
  `drill` (the 6 drill dims), `agent_performance` / `source_analytics` /
  `campaign_analytics`, `followup_analytics`, `daily_timeline` (zero-filled,
  vendor-day grouped), `status_breakdowns`, and `aggregate()` (the full report).
- `consumer.py` — `EventReducer.reduce(prior, event)` maps each W8 event onto the
  FactCall; `build_consumer_handler(store)` is the async handler a
  `voice_kernel.events.SinkConsumer` drives. Non-call events skipped; never raises.
- `service.py` — `ReportingService` (the query API: `report / totals / metric /
  funnel / timeline / agents / sources / campaigns / followups / hot_leads`).
- `config.py` — `ReportingConfig` (vendor tz, `consumer_group="reporting"`, default
  preset, hot-lead limit).

### `voice_ops/ai_manager_live/`
- `commands.py` — deterministic `parse_command(msg)` → `Command{kind, preset,
  target, metric, filters, deliver}`. Kinds: `send_report / hot_leads /
  campaign_perf / metric / funnel / unknown`. Recognizes range phrases, metric
  synonyms, lead-status + source filters, and "send/whatsapp" → `deliver=True`.
- `adapter.py` — `LiveAdapter` wraps `ReportingService`: `metric / totals / report /
  hot_leads / campaign_performance / funnel` — all LIVE, range-aware. Campaign name
  fuzzy-matches the campaign breakdown.
- `summary.py` — `build_daily_summary(adapter, tenant, preset)` → `DailySummary`
  (totals + hot-lead names + AI summaries + next actions) and a WhatsApp-ready
  rendered `.text`.
- `delivery.py` — `ReportDelivery(sender, number_resolver)`; default
  `NullWhatsAppSender` ⇒ `{"status":"not_configured"}` (DORMANT, never sends blind).
  Fail-closed on empty tenant / no registered number. Masks the recipient in the
  envelope/logs.
- `service.py` — `AIManagerLiveService.handle(tenant, message)` (parse→answer→
  optionally deliver) and `.daily_summary(tenant, deliver=)`. Returns a structured
  envelope; the voice agent speaks `reply`, WhatsApp sends the same text.

---

## 2. The gate (default OFF until the wiring wave)

`ReportingConfig.enabled` defaults `False`. The query API still works against an
empty store (dashboard sees zeros, never an error). Enable per box via a **systemd
drop-in** env (`REPORTING_ENABLED=1`), NEVER the shared `.env` (W8/LEARNINGS §2: a
shared-.env flag leaks across inbound + the outbound earner on restart). The
reporting consumer + the SSE bridge are SEPARATE systemd units (never inside the
voice agent — W8 RESEARCH-DECISIONS §9).

---

## 3. Producer seam — reuse W8 emit-sites (NO new caller.py edits beyond W8)

W14 **consumes** the exact events `design/W8-EVENT-SEAM.md §3–4` already specifies
emitting from `caller.py::_finalize_call` and `aim_voice_agent.py`. The reducer
(`consumer.py`) is built to that taxonomy 1:1:

| W8 emit (file:line in W8 doc) | event | FactCall effect |
|---|---|---|
| dial placed (`run_job` launch) | `call_started` | row created, status DIALING, stage→dialed |
| media established | `call_connected` | connected=True, status CONNECTED, stage→connected |
| `caller.py:2781` call.completed | `call_ended` + `summary_ready` | duration, status COMPLETED, lifecycle, conversion_prob, ai_summary, next_action |
| `caller.py:2790` score≥70 | `lead_classified(...,"hot")` | lead_status HOT, interested, stage→hot |
| `caller.py:2760` callback | `callback_scheduled` | callback_scheduled=True, next_action |
| booking confirmed (booking svc) | `site_visit_booked` | booked=True, booking_status BOOKED, lead HOT, stage→booked |
| `caller.py:2799` notify_handoff | `handoff_requested` | handoff=True |
| `_send_whatsapp` ok (`:2770`) | `whatsapp_sent` | whatsapp_sent=True |
| recordings presign | `recording_ready` / `transcript_ready` | has_recording / has_transcript |

**The richer payload fields the reducer reads** (`campaign_id`, `source`, `agent`,
`lead_name`, `lead_phone_masked`, `summary`, `next_action`, `interested`,
`converted`) are OPTIONAL `**extra` on the W8 factories — when the wiring wave has
them at the emit site, pass them; when absent the reducer degrades gracefully.
Recommended additions at the W8 emit sites (additive, no contract change):
`vke.summary_ready(cid, tenant_id, lifecycle=lc, conversion_prob=score/100,
summary=short, next_action=na, lead_name=name, lead_phone_masked=mask, campaign_id=,
source=, agent=)`. The reducer pins `ts_iso` to the `call_started` event so
range-filtering is stable (the storage half of the "1 day ago" fix).

`converted` (the 8th funnel stage) is a business signal (deal closed). Until a
true conversion event exists, emit it as `summary_ready(..., converted=True)` (or a
future `LEAD_CONVERTED` taxonomy entry — append-only). Today `booked` is the
strongest signal the funnel reaches.

---

## 4. Reporting consumer worker seam (NEW separate systemd unit)

A tiny long-running worker per box (or one multi-tenant worker), NOT inside the
voice process:

```python
# voice_ops_reporting_worker.py  (new, on the box; reads the box's Redis)
import asyncio
from voice_kernel.events import EventBusConfig, RedisEventBus, SinkConsumer, reclaim_and_dlq
from voice_ops.reporting import ReportingStore, ReportingConfig, build_consumer_handler
# from voice_ops.reporting.pg_backend import PgReportingBackend   # box-only, lazy

cfg   = EventBusConfig.from_env()                 # EVENTBUS_REDIS_URL
bus   = RedisEventBus(cfg)
store = ReportingStore(backend=PgReportingBackend(...))  # or default in-mem
rcfg  = ReportingConfig(enabled=True)             # REPORTING_ENABLED=1 in the drop-in
handler = build_consumer_handler(store)

async def main():
    consumers = [SinkConsumer(bus, cfg, t, rcfg.consumer_group, handler) for t in active_tenants()]
    # run each consumer + a ~30s reclaim_and_dlq janitor per (tenant, group)
    await asyncio.gather(*[c.run() for c in consumers])
```

- Tenant set: resolve from the box's tenant registry; one `SinkConsumer` per
  tenant stream (`vk:events:{tenant_id}`), `group="reporting"` (own group, so it
  gets EVERY event independent of `dashboard`/`crm`/`analytics` groups).
- Run `reclaim_and_dlq(bus, cfg, tenant, "reporting")` on a 30s timer (crashed-peer
  PEL recovery + poison→DLQ), per the W8 consumer helper.
- **PG read-model (recommended on the box):** a `PgReportingBackend` implementing
  `upsert/get/scan/clear` over a FORCE-RLS `reporting_fact_calls` table (one row per
  `(tenant_id, call_id)`, indexed on `(tenant_id, ts_iso)`), admin-GUC tenant
  isolation mirroring `db/ddl_wallet.sql`. Lazy psycopg import (mirror
  `voice_ops/booking/store.py`). Until then the in-mem backend is a valid cache
  (rebuilt from the stream replay on restart).

---

## 5. Panel API seam (the dashboard's data source — founder pain #3)

Replace the flat-file `/analytics` + `/stats` reads with reporting-service-backed
routes. Add to the panel backend (FastAPI on the box, tenant **token-derived**,
mirror `caller.py:404 resolve_tenant` — NEVER from the body):

| New route | Backs onto |
|---|---|
| `GET /report?preset=today&from=&to=&campaign=&lead_status=&source=&agent=&call_status=&booking_status=` | `ReportingService.report(tenant, preset, frm, to, filters)` |
| `GET /report/funnel?preset=&...` | `.funnel(...)` |
| `GET /report/timeline?preset=&...` | `.timeline(...)` |
| `GET /report/agents?preset=` `…/sources` `…/campaigns` `…/followups` | the matching service methods |
| `GET /report/hot-leads?preset=&limit=` | `.hot_leads(...)` |
| `GET /report/metric/{key}?preset=&...` | `.metric(...)` |

Construct ONE process-wide `ReportingService(store, config)` sharing the SAME store
the consumer writes (same PG, or the same in-mem instance if co-located). Filters
map 1:1 to `aggregate.DRILL_DIMS` (`campaign / lead_status / source / agent /
call_status / booking_status`). Every response already carries the resolved range
(`from`/`to`/`preset`/`tz`) so the panel renders the window unambiguously.

### Real-time push (replace the 30s poll)
- A consumer/SSE bridge (new unit or a panel route): `SinkConsumer(bus, cfg,
  tenant, group="dashboard", handler=push_to_sse)` tails the tenant stream → SSE.
- Panel client `lib/events.ts`: `EventSource` → on each event,
  `queryClient.invalidateQueries(['report', …])` so React Query refetches the
  report routes above instantly. Render every timestamp via `Intl.DateTimeFormat`
  with `timeZone:'Asia/Kolkata'` (JS mirror of `timeutil.to_vendor`).

---

## 6. AI-Manager seam (founder pain #2 + #5)

The inbound AI-Manager state machine (`ai_manager/state_machine.py::_answer_query`)
currently returns a **stub** for `analytics.send_report` / `analytics.today_summary`.
Replace those stubs with `AIManagerLiveService`:

```python
from voice_ops.ai_manager_live import AIManagerLiveService
from voice_ops.ai_manager_live.delivery import ReportDelivery
# wa_sender = the box's live WhatsApp client (lazy); number_resolver = registered number lookup
aim_live = AIManagerLiveService(
    reporting_service,                                  # the SAME service the panel uses
    delivery=ReportDelivery(sender=wa_sender, number_resolver=registered_number_for),
)
env = aim_live.handle(tenant_id, user_utterance)        # parse + LIVE answer + (deliver)
return env["reply"]                                     # speak it (voice) — WA sent if deliver
```

- `handle()` covers "send today's report", "show hot leads", "campaign X
  performance", "how many calls today", "show the funnel" — all reading LIVE
  numbers, identical to the dashboard.
- **Daily executive summary (pain #4):** schedule `aim_live.daily_summary(tenant,
  preset="today", deliver=True)` at end-of-day (a cron / Hatchet job per tenant in
  the vendor tz). The summary lists totals + hot-lead names + short AI summaries +
  next actions; `deliver=True` sends it to the registered WhatsApp number. **Dormant
  until Meta WA creds:** inject the real `sender`; until then `NullWhatsAppSender`
  returns `not_configured` and nothing is sent.
- The `number_resolver` returns the tenant's **registered** WhatsApp number (one
  per tenant) — token/tenant-scoped, never a body-supplied number.

---

## 7. The UI contract for W15 (what the dashboard build consumes)

The W15 universal-reporting UI (Core_2 kit, never from scratch) binds to the §5
routes. Stable shapes the components can rely on:

- **Range chips** (default **Today**): `today | yesterday | 7d | 30d | this-month |
  prev-month | custom` → `?preset=` (custom adds `?from=YYYY-MM-DD&to=YYYY-MM-DD`,
  `to` inclusive). Every panel reflects the active range; the response echoes
  `range:{preset,from,to,tz}`.
- **Drill-down filter bar:** `campaign | lead_status(hot/warm/cold/dead) | source |
  agent | call_status | booking_status` → query params; combine freely (AND).
  Badge counts from `report.by_status`.
- **Top-line cards:** `report.totals` → calls / connected (+connect_rate) /
  interested / booked / converted / hot·warm·cold·dead / callbacks / whatsapp_sent /
  handoff / avg_talk_time_s / conversion_rate.
- **Funnel widget:** `report.funnel` = 8 stages, each `{stage,count,pct_of_top,
  step_conv}` — render a monotone funnel with step drop-off labels.
- **Daily activity timeline:** `report.timeline` = `[{date,calls,connected,booked,
  converted}]`, zero-filled across the range, vendor-local dates → a per-day chart.
- **Analytics tables:** `report.agents` / `report.sources` / `report.campaigns` =
  `[{key,calls,connected,booked,converted,talk_time_s,connect_rate,book_rate}]`
  sorted by calls desc → sortable tables. `report.followups` =
  `{callbacks_scheduled,whatsapp_followups,handoffs,pending_followups}`.
- **Hot-leads panel + CRM drill:** `GET /report/hot-leads` rows = `{call_id,name,
  phone_masked,campaign_id,source,booked,conversion_prob,summary,next_action,ts_iso}`
  → a hot-lead list that deep-links to the CRM lead profile; the same payload feeds
  the daily WhatsApp summary so the screen and the message agree.
- **AI-Manager command box (chat):** POST a free-text command → the
  `AIManagerLiveService.handle` envelope `{command, reply, data, delivery?}`;
  render `reply` (and a "Send to WhatsApp" affordance that sets `deliver`).
- **Timezone rule for the UI:** render every timestamp with
  `Intl.DateTimeFormat(..., {timeZone:'Asia/Kolkata'})`. All wire timestamps are
  UTC `…Z`; never parse them as local.

---

## 8. Smoke + revert (the wiring wave's DoD)

- Real outbound call RINGS before AND after (the earner regression gate; agent.py
  md5 unchanged).
- With `REPORTING_ENABLED=1` + the consumer running: place a test call → within a
  second the read-model has the FactCall → `GET /report?preset=today` shows it →
  the AI-Manager "how many calls today" returns the SAME number → the daily summary
  lists the hot lead (if hot). Tenant isolation: a second tenant sees none of it.
- Revert path: stop the consumer + SSE units, unset `REPORTING_ENABLED`, point the
  panel back at the legacy `/analytics`/`/stats` routes. The earner is untouched
  throughout (W14 is pure consumer + read API).
```
