# W8 — Event-Driven Backbone: the LATER flag-gated emit-site SEAM

Status: **SEAM NOTE ONLY — NOTHING WIRED.** This wave built + tested the
`voice_kernel/events/` module against the frozen `EventBus` contract with
`NullEventBus` as the OFF default. The earner is byte-identical:
`droplet_work/agent.py` md5 = `98655dbf` (unchanged); `caller.py` /
`aim_voice_agent.py` untouched.

This file is the precise, file:line recipe for the SEPARATE, founder-signed
wiring wave — one box-mutating change, real-flow smoke, revert path.

---

## 0. The founder problem this closes

"Nothing updates in real time" — a call happens but the dashboard / CRM /
recordings / hot-lead count / booking stay stale; "timeline shows 1 day ago for
a call just now." Fix = every meaningful action emits ONE event to a per-tenant
Redis Stream; the panel tails it and re-renders instantly. Plus a canonical
timestamp layer (store UTC, render Asia/Kolkata) so the "1 day ago" off-by-one
is gone.

## 1. What exists now (the built surface)

- `voice_kernel/events/bus.py` — `RedisEventBus(cfg, client=None)` (Redis
  Streams; fire-and-forget `emit`, hard `emit_timeout_s=0.25`, never raises;
  per-tenant stream `vk:events:{tenant_id}`; XADD IDMP on Redis 8.6+ else plain).
- `voice_kernel/events/fake.py` — `InMemoryEventBus` (dep-free, same semantics).
- `voice_kernel/events/taxonomy.py` — `EventName` enum + typed factories for the
  founder's full list (call_started/connected/ended/failed, recording_ready,
  transcript_ready, summary_ready, lead_hot/warm/cold/dead via
  `lead_classified`, callback_scheduled, site_visit_booked,
  handoff_requested/done, whatsapp_sent, provider_failed, daily_report).
- `voice_kernel/events/timeutil.py` — `now_utc_iso()` (Z-suffixed), `parse_iso`,
  `to_vendor`, `vendor_date`, `humanize` (the bug-free relative label).
- `voice_kernel/events/consumer.py` — `SinkConsumer` (per-sink loop, iid dedup,
  auto-ack) + `reclaim_and_dlq` (XAUTOCLAIM janitor + dead-letter).
- Registration: `build_kernel(cfg, event_bus=impl)` (alias added in
  `kernel.py` `_IMPL_ALIASES`: `event_bus`/`eventbus`/`events` -> `events`).

## 2. The gate (default OFF — must stay OFF until the wiring wave)

`voice_kernel/events/config.py::EventBusConfig.enabled` reads `EVENTBUS_ENABLED`
(default `"0"`). The emit-site (below) checks this and falls back to a no-op when
OFF. Place `EVENTBUS_ENABLED=1` in the **systemd drop-in** for the box being
wired, **never the shared `.env`** (LEARNINGS §2: a shared-.env flag leaks across
inbound + the outbound earner on restart). Redis URL via `EVENTBUS_REDIS_URL`
(reuse the box's existing Redis — RAG L1 already does).

## 3. OUTBOUND emit-site — `caller.py::_finalize_call` (file:line)

`droplet_work/caller.py:2715 async def _finalize_call(it, now_t, tenant_id, cid, camp_fields)`
is the single post-call touch-point (already AWAITED in the dial loop at
`run_job` ~`:2845`, and it ALREADY fire-and-forgets via `_emit_webhook`). The
event emits sit RIGHT BESIDE the existing `_emit_webhook(...)` calls — same facts,
new transport. EARNER LAW: emit is fire-and-forget + own timeout, so it cannot
block/raise into the loop (the `RedisEventBus.emit` contract already guarantees
this; still wrap the call site in try/except for defence in depth).

Wiring (behind `EVENTBUS_ENABLED`, module-level singleton bus built once):

```python
# top of caller.py, near other singletons (NOT inside the loop):
from voice_kernel.events import EventBusConfig, RedisEventBus, NullEventBus  # type: ignore
import voice_kernel.events as vke
_EVCFG = EventBusConfig.from_env()
_EVBUS = RedisEventBus(_EVCFG) if _EVCFG.enabled else None  # None => skip entirely

async def _ev(make_event_call):
    if _EVBUS is None:
        return
    try:
        await _EVBUS.emit(make_event_call)   # emit() already non-blocking + never-raises
    except Exception:
        pass
```

Then beside each existing `_emit_webhook` in `_finalize_call` (map 1:1):

| existing line | webhook topic | NEW event (taxonomy factory) |
|---|---|---|
| `caller.py:2749` | `lead.opted_out` | `vke.lead_classified(rec["id"], tenant_id, "dead")` + `vke.call_ended(...)` |
| `caller.py:2760` | `callback.scheduled` | `vke.callback_scheduled(rec["id"], tenant_id, preferred_ts=cb)` |
| `caller.py:2781` | `call.completed` | `vke.call_ended(rec["id"], tenant_id, duration_s=rec["duration_s"])` + `vke.summary_ready(... lifecycle, conversion_prob=score/100)` |
| `caller.py:2790` | `lead.qualified` (score>=70) | `vke.lead_classified(rec["id"], tenant_id, "hot", conversion_prob=score/100)` |
| `caller.py:2799` | `notify_handoff_team` | `vke.handoff_requested(rec["id"], tenant_id, reason="hot_lead")` |
| `_send_whatsapp` ok (`:2770`) | (none today) | `vke.whatsapp_sent(rec["id"], tenant_id, template=...)` on success |

Call-START / FAILED: emit `vke.call_started(...)` where the dial is placed (the
launch path that sets `it["launched_at"]`), `vke.call_failed(...)` on the
no-answer/SIP-error branch. RECORDING: emit `vke.recording_ready(call_id,
tenant_id, url=presigned)` where the egress presigned URL is produced (recordings
pipeline; mirrors REC-A/C presign fix). **Always pass a UTC timestamp** — the
factories default to `now_utc_iso()`; do NOT pass a naive `datetime.now()`.

`rec` carries `started_at`/`ended_at` as `datetime.now().isoformat()` (LOCAL,
naive — `caller.py:2722`). When wiring, convert those to UTC via
`voice_kernel.events.timeutil.ensure_utc` BEFORE they become an event `ts_iso`,
or (better) switch those two writes to `now_utc_iso()`. This is the storage half
of the "1 day ago" fix.

## 4. INBOUND emit-site — `aim_voice_agent.py`

The inbound agent persists a session on hangup (`ai_manager_sessions` +
`ai_manager_commands`, the room-disconnect shutdown hooks ~`aim_voice_agent.py`
session-logging block around `:190`/`:1926`). Emit `vke.call_started` at connect,
`vke.transcript_ready` + `vke.call_ended` + `vke.summary_ready` in the same
shutdown hook that writes the session row. Same `EVENTBUS_ENABLED` gate, same
fire-and-forget wrapper. Keep inbound + outbound flags independent (separate
systemd drop-ins).

## 5. The PANEL real-time consumer (the founder-visible half)

Today the Run page POLLS: `famit-panel/app/run/page.tsx:161` (`pollRef` +
`setInterval` at `:219`); React Query caches with `staleTime` in
`famit-panel/lib/queries.ts:169/200`. The event backbone REPLACES the poll with a
push.

Two pieces, both SEPARATE processes (never inside the voice agent —
RESEARCH-DECISIONS §9):

1. **A consumer/SSE bridge service** (new systemd unit, or a FastAPI route on the
   panel backend): `SinkConsumer(bus, cfg, tenant_id, group="dashboard",
   handler)` (`voice_kernel/events/consumer.py`) tails `vk:events:{tenant_id}`
   and pushes each event to the browser over SSE/WebSocket. Tenant is
   TOKEN-DERIVED (never body) — mirror `resolve_tenant` (caller.py:404). One
   consumer group per sink: `dashboard`, `crm`, `analytics`, `reports`.
2. **Panel client**: add `lib/events.ts` opening an `EventSource` to that SSE
   route; on each event, `queryClient.invalidateQueries(...)` for the matching
   key (calls list, lead row, hot-lead count, bookings) so React Query refetches
   instantly. Render every timestamp through an `Intl.DateTimeFormat` with
   `timeZone: 'Asia/Kolkata'` (the JS mirror of `timeutil.to_vendor`) — this is
   the render half of the "1 day ago" fix.

Run the janitor (`reclaim_and_dlq`) on a ~30s timer inside the consumer service
to recover crashed-peer PEL entries and route poison to `vk:events:{tenant}:dlq`.

## 6. Smoke + revert (the wiring wave's DoD)

- Real outbound call RINGS before AND after (the earner regression gate).
- `/proc/<pid>/environ` shows `EVENTBUS_ENABLED` ONLY on the wired process.
- A live call produces events on `vk:events:{tenant}` (`XLEN` > 0); the panel
  updates WITHOUT a manual refresh; the just-now call shows a fresh IST label.
- agent.py md5 still `98655dbf`.
- Revert = remove the systemd drop-in line (`EVENTBUS_ENABLED`) + restart ->
  `_EVBUS` is None -> zero emits -> byte-identical to today.
