# Wave W8 — Event-Driven Backbone + Canonical Timestamps

Branch: `fix/realtime-voice-kernel-v2`. Earner: agent.py md5 `98655dbf` UNCHANGED;
caller.py / aim_voice_agent.py UNTOUCHED. All work in DISJOINT new files under
`voice_kernel/events/`.

## Phase: RESEARCH
Decisions in `voice_kernel/events/RESEARCH-DECISIONS.md` (Redis Streams over
Pub/Sub/Kafka; per-tenant stream + group-per-sink; at-least-once + iid
idempotency; emit never blocks; canonical UTC-store / vendor-tz-render).

## Phase: BUILD
Built the event-driven backbone + canonical timestamp utility against the FROZEN
`EventBus` Protocol (`contracts.py:222`) / `Event` dataclass (`contracts.py:138`),
with `NullEventBus` remaining the OFF default. Registration via
`build_kernel(cfg, event_bus=impl)` (added `event_bus`/`eventbus`/`events` aliases
to `kernel.py::_IMPL_ALIASES`).

Files created (all under `voice_kernel/events/`):
- `__init__.py` — package surface (bus, fake, config, consumer, taxonomy, timeutil).
- `bus.py` — `RedisEventBus`: async fire-and-forget `emit` (hard 0.25s timeout,
  never raises -> drops like Null on dead Redis), per-tenant stream
  `vk:events:{tenant_id}`, XADD IDMP on Redis 8.6+ else plain XADD, two-phase
  `subscribe` (PEL drain -> live `>`), auto-XACK, separate consumer connection.
- `fake.py` — `InMemoryEventBus`: dep-free, models per-tenant streams + per-group
  cursor + iid dedup + fire-and-forget (tests + local fallback).
- `taxonomy.py` — `EventName` closed enum + typed factories covering the founder's
  FULL list (call_started/connected/ended/failed, recording_ready,
  transcript_ready, summary_ready, lead_hot/warm/cold/dead via lead_classified,
  callback_scheduled, site_visit_booked, handoff_requested/done, whatsapp_sent,
  provider_failed, daily_report). `ts_iso` is first-class (stamped UTC; a payload
  ts_iso is lifted to the event timestamp -> stable idempotency).
- `timeutil.py` — canonical layer: `now_utc_iso()` (Z-suffixed), `parse_iso`
  (naive == UTC, the storage contract), `to_vendor`/`vendor_date`/`render_vendor`
  (Asia/Kolkata, fixed +05:30 fallback if no tzdata), `humanize` (relative label
  computed on VENDOR-LOCAL dates — the "1 day ago" fix).
- `config.py` — `EventBusConfig` (EVENTBUS_ENABLED default OFF; emit_timeout 0.25,
  block 2000ms, maxlen 100k, min_idle 60s, claim 50, max_deliveries 3) +
  `stream_for`/`dlq_for`/`dedup_key` (fail-closed on empty tenant — no wildcard).
- `serde.py` — Event<->stream-field encode/decode (payload = one JSON field;
  tolerant decode for DLQ routing) + `idempotency_id` (name:call_id:digest8).
- `consumer.py` — `SinkConsumer` (per-sink loop, iid dedup, handler) +
  `reclaim_and_dlq` (XAUTOCLAIM janitor -> per-tenant DLQ after max_deliveries).

Also edited (additive, non-earner): `voice_kernel/kernel.py::_IMPL_ALIASES` (+3
aliases for `event_bus` registration).

### Tests (pytest, mock Redis — repo asyncio.run() convention)
- `tests/test_events_bus.py` (12) — Protocol conformance; emit->consumable;
  idempotent re-emit deduped; tenant-scoped no cross-tenant bleed; empty-tenant
  dropped (fail-closed); emit never raises on a sabotaged bus; subscribe delivers
  + auto-acks; two groups read independently; SinkConsumer dedup+handler;
  build_kernel(event_bus=) frozen-spec registration; idempotency stable+distinct.
- `tests/test_events_redis.py` (12) — serde round-trip (nested payload preserved);
  tolerant decode (garbage + bytes fields); IDMP on 8.6 vs plain XADD on 7.4;
  empty-tenant dropped; emit never raises on dead client; emit times out without
  blocking (5s sleep, returns <1s); XAUTOCLAIM->DLQ on poison; under-threshold
  retained; reclaim no-op without client.
- `tests/test_events_timeutil.py` (8) — Z-suffix + round-trip; Z/offset/naive all
  UTC; IST offset render; **the "1 day ago" bug fixed** (19:05Z == 00:35 IST next
  day reads fresh, not "yesterday"; vendor_date = next day); humanize buckets;
  future clamps to "just now"; ensure_utc naive==UTC; render_vendor string.
- `tests/test_events_off_identity.py` (14) — zero droplet/agent imports (AST-level
  + sys.modules); **flag-OFF byte-identity 12/12** (6 field variants x 2
  directions: OFF assembly identical with NO bus / InMemoryEventBus /
  RedisEventBus registered).

### Result
`pytest voice_kernel/tests voice_kernel/integrations/tests` = **291 passed**
(44 new W8 + 247 existing, zero regressions). agent.py md5 still `98655dbf`.

### Seam note
`design/W8-EVENT-SEAM.md` — the LATER founder-signed wiring wave: outbound
emit-sites in `caller.py::_finalize_call` (`caller.py:2715`, 1:1 beside the
existing `_emit_webhook` calls at :2749/:2760/:2781/:2790/:2799), inbound in
`aim_voice_agent.py` session-shutdown hook, the panel SSE consumer replacing the
Run-page poll (`app/run/page.tsx:161/219`), all behind `EVENTBUS_ENABLED` (systemd
drop-in, not shared .env), with smoke + revert.

## Phase: VERIFY + RED-TEAM FOLD (W8 commit gate)

Red-team review (RVK2) found 2 real defects in the consumer redelivery path
(dormant until the LATER seam runs sinks, so the live earner was never at risk;
folded BEFORE commit anyway). All fixes are confined to `voice_kernel/events/`.

- **BLOCKER-1 — handler failure ACKed & LOST (at-most-once-then-drop).** `_read`
  XACKed unconditionally after the `yield` resumed, but `SinkConsumer.run`
  swallowed the handler exception with `continue` — so a failed handler was acked
  and the event dropped. FIX: `SinkConsumer.run` now drives `subscribe(...)` as a
  manual async-generator and `.athrow(_AckSkip)`s a handler failure BACK INTO the
  generator at its yield; `_read` catches `_AckSkip` and SKIPS the XACK, leaving
  the entry in the PEL for XAUTOCLAIM redelivery. True at-least-once restored.
  Regression: `test_handler_failure_redelivers_not_drops` (fails twice, delivered
  >=3x, never dropped); the in-memory fake models leave-in-PEL (no cursor advance
  on `_AckSkip`).
- **BLOCKER-2 — PEL drain abandoned entries beyond claim_count.** `_read` flipped
  `start_id` to `>` after the FIRST `0` batch, so a restarted consumer owning >50
  pending entries only re-read the first 50. FIX: keep re-reading with `0` until a
  `0` read returns empty, THEN return so the caller switches to live `>`. No
  unconditional flip. Regression: `test_pel_drains_fully_beyond_claim_count`
  (120-entry PEL, claim_count 50 -> all 120 redelivered via repeated `0` reads).
- **FIX-NOW 3 — `daily_report` iid not stable per (tenant, day).** It let
  `make_event` stamp wall-clock `now`, so the docstring's "stable per (tenant,
  day)" was false and re-runs would NOT dedupe. FIX: pin `ts_iso` to
  `{report_date}T00:00:00Z`. Regression: `test_daily_report_idempotent_per_tenant_day`.

Files touched in the fold: `events/bus.py` (`_AckSkip` sentinel + conditional ack
+ full PEL drain), `events/consumer.py` (manual-generator drive + `athrow`),
`events/fake.py` (`_AckSkip` -> no cursor advance), `events/taxonomy.py`
(`daily_report` ts pin). Frozen `EventBus` Protocol (emit + subscribe) UNCHANGED.

### Final result
`pytest voice_kernel/` = **321 passed** (events suite now 46: the original 44 +
3 new regression tests, with prior count reconciliation; off-identity **12/12**;
zero leaked droplet/agent imports AST + sys.modules). agent.py md5 still
`98655dbf`; caller.py / aim_voice_agent.py UNTOUCHED. Branch
`fix/realtime-voice-kernel-v2`. gitleaks --staged = 0.
