# voice_kernel/events — Redis Streams EventBus: RESEARCH + DECISIONS (W8)

Researched 2026-06-18 (web + Context7 /redis/docs). Binds the FROZEN contract:
`Protocol EventBus` (async, fire-and-forget) · `Event(name, call_id, tenant_id, ts_iso, payload)` ·
register via `build_kernel(cfg, event_bus=impl)`. NO edit/import of agent.py / caller.py /
aim_voice_agent.py — the emit-sites are a LATER flag-gated seam (SEAM NOTE §9 below).

## FROZEN contract we bind to (do NOT change)
- `voice_kernel/contracts.py:138` `@dataclass(frozen=True) Event: name, call_id, tenant_id, ts_iso, payload(dict)`.
- `voice_kernel/contracts.py:222` `EventBus(Protocol)`:
  - `async def emit(event: Event) -> None` — "must never block the dial loop (fire-and-forget, own timeouts)".
  - `async def subscribe(stream: str, group: str) -> AsyncIterator[Event]`.
- `KernelSession.tenant_id` (contracts.py:59) is the server-stamped tenant identity; every tenant-scoped
  service receives it. `Event.tenant_id` is the same value — it is the partition + RLS key.
- Existing safe default: `NullEventBus` (null_impls.py:164) drops emit, yields nothing. Our Redis impl is the
  REAL backend; Null stays the OFF/degraded fallback (same degrade-to-empty discipline RAG used).

---

## 1. WHY Redis Streams (not Pub/Sub, not Kafka) — DECIDED
- **Pub/Sub is fire-and-forget with NO persistence, NO replay, NO consumer tracking** — a disconnected
  dashboard/CRM/analytics consumer loses every event. Unacceptable for a billing/audit-adjacent earner.
- **Redis Streams = durable append-only log + consumer groups**: at-least-once delivery, per-group cursor,
  independent fan-out, replay, and a Pending Entries List (PEL) for crash recovery. This is the right
  primitive for "fan-out to dashboard / CRM / analytics" where each consumer must see every event.
- **Kafka is overkill** for our scale + adds an ops box. We ALREADY run Redis on the voice box (RAG L1 cache
  reuses "the EventBus Redis" — rag/RESEARCH-DECISIONS.md §8). One Redis, one dependency. Real-world precedent:
  payments platforms run 15–40k events/s at <10ms p99 fan-out on Redis Streams with 3 consumer groups.
- **HYBRID for the live dashboard tail**: Streams is the source of truth (durable). The dashboard pusher is a
  consumer group that reads the stream and pushes over SSE/WS. We do NOT also dual-write Pub/Sub — the SSE
  consumer's `BLOCK` read already gives sub-100ms latency and keeps ONE delivery story (durable + replayable).

## 2. TOPOLOGY — stream-per-tenant, consumer-group-per-sink — DECIDED
- **Stream key = `vk:events:{tenant_id}`** (one stream per tenant). Rationale: hard multi-tenant isolation
  (a CRM consumer for tenant A literally cannot read tenant B's stream), independent per-tenant trim/retention,
  and natural load distribution. `Event.tenant_id` selects the stream — never a wildcard, never `%` (mirrors the
  RLS rule W1 proved).
  - Trade-off: thousands of tenants = thousands of streams. Acceptable (Redis handles it; streams are cheap when
    trimmed). If tenant count explodes we shard by `vk:events:{hash(tenant)%N}` and keep tenant_id in the entry —
    contract unchanged. Documented as the only future scaling knob.
- **Consumer groups = one per downstream SINK**, each independent on the SAME stream, each with its own cursor:
  - `dashboard`  → SSE/WebSocket live tail to the panel.
  - `crm`        → upsert call/lead state into the CRM/PG.
  - `analytics`  → roll-ups / metering aggregation.
  Adding a sink = `XGROUP CREATE ... MKSTREAM` with `$` (start at tail) — zero impact on existing sinks. This is
  the fan-out: one append, N independent at-least-once readers.
- **Group create is idempotent + lazy**: `XGROUP CREATE key group $ MKSTREAM`, swallow BUSYGROUP. MKSTREAM means a
  consumer can bootstrap a tenant's stream before the first emit (no NOMKSTREAM races).

## 3. ORDERING — DECIDED
- Stream IDs are `ms-seq`, **monotonically increasing**; XADD rejects a smaller ID. Within one stream
  (= one tenant) events are **totally ordered** in append order. We let Redis stamp the ID (`*`) — we do NOT pass
  `Event.ts_iso` as the stream ID (clock skew would break monotonicity); `ts_iso` rides in the payload as the
  business timestamp. Per-tenant total order is exactly what the dashboard/CRM need (per-call ordering is implied
  since a call_id's events are all in its tenant's stream).
- Cross-tenant ordering is intentionally NOT guaranteed (different streams) — irrelevant for isolated tenants.

## 4. AT-LEAST-ONCE + IDEMPOTENCY — DECIDED (two layers)
- **Delivery = at-least-once** via consumer groups: `XREADGROUP > ` delivers, message enters PEL, consumer
  `XACK`s only AFTER successful processing. Crash before ACK → redelivered (see §5). This means consumers MUST be
  idempotent. "Exactly-once" is a myth; we do at-least-once + idempotent sinks.
- **Producer-side dedup (Redis 8.6+, native): `XADD key IDMP {pid} {iid} * ...`**. We set
  `pid = tenant_id`, `iid = call_id + ":" + event_seq` (or the event's natural unique key) so a retried emit
  (e.g. our own timeout-retry) does NOT create a duplicate stream entry — at-most-once PRODUCTION. Configure TTL
  window per stream via `XCFGSET key IDMP-DURATION <s> IDMP-MAXSIZE <n>`.
  - **Version-gated**: if the live Redis is < 8.6 (probe `INFO server` redis_version at connect), fall back to a
    plain `XADD * ` and rely purely on consumer-side idempotency. The IDMP path is a capability, not a requirement
    — degrade cleanly. (Confirmed signatures from /redis/docs: `XADD mystream IDMP producer1 msg1 * f v`,
    `XADD mystream IDMPAUTO producer2 * f v`.)
- **Consumer-side idempotency (always on, the real safety net)**: each consumer keeps a tenant-scoped processed-set
  `vk:dedup:{tenant_id}:{group}` (Redis SET or a short-TTL string per `iid`) and SKIPs already-seen ids before
  doing the side-effect, then XACKs. Idempotency key = the producer `iid` (stable across redelivery).

## 5. CRASH RECOVERY / POISON / DLQ — DECIDED
- **Startup recovery (two-phase)**: on consumer boot, first drain its own backlog with
  `XREADGROUP GROUP g consumer 0` (re-read PEL it owned), then switch to `>` for new. Prevents loss of in-flight
  work when a specific consumer restarts.
- **Reassign abandoned work (janitor)**: a background coroutine per group runs every ~30s:
  `XAUTOCLAIM key group <thisconsumer> 60000 0-0 COUNT 50` — atomically claims entries idle > 60s from dead
  consumers (Redis 6.2+, replaces manual XPENDING+XCLAIM). min-idle-time **60_000 ms**, COUNT **50**/cycle.
- **Poison-pill / DLQ**: `XAUTOCLAIM` (and `XPENDING`) returns `times_delivered`. If a message has been delivered
  **>= 3** times and still fails, route it to a **dead-letter stream `vk:events:{tenant_id}:dlq`** (XADD the
  original fields + an error reason), then `XACK` the original so it leaves the PEL. DLQ is inspected by ops /
  surfaced in super-admin; never silently dropped.
- **PEL hygiene**: keep pending small (PEL is a separate radix tree; millions pending degrades XREADGROUP). Alert
  on `XINFO GROUPS` pending + lag.

## 6. TRIMMING / BACKPRESSURE / MEMORY — DECIDED
- **Bounded streams, always**: producer trims on every append with the approximate form
  `XADD key MAXLEN ~ {cap} IDMP ... * ...` (the `~` makes trim O(1) at macroblock boundary). Cap per tenant:
  start **`~ 100_000`** entries (~hours of a single call's events; cheap). Alert when length approaches cap.
- **Consumer-group-aware trimming (Redis 8.2+)**: plain MAXLEN can delete entries a slow group hasn't read =
  silent loss. Where the live Redis is >= 8.2 we prefer the consumer-group-aware variants (`XDELEX`/`XACKDEL`/the
  KEEPREF/DELREF semantics) so trimming respects un-consumed entries. Version-gated; < 8.2 falls back to
  conservative MAXLEN well above expected lag + a lag alert. (Confirmed from /redis/docs: "Starting with Redis 8.2,
  XACKDEL, XDELEX, XADD, and XTRIM offer enhanced control across multiple consumer groups.")
- **Backpressure**: backpressure shows up as Redis memory + group lag, NOT as a blocked dial loop (emit can't
  block — §7). If a sink falls behind, its group lag grows; the janitor + DLQ keep the PEL bounded; trimming caps
  memory (oldest-overflow policy by design — the durable record of record for billing is the PG audit leg, NOT this
  stream, so trim-loss of an old ephemeral UI event is acceptable). Operator alerts on lag/length are the
  backpressure signal.

## 7. EMIT MUST NEVER BLOCK THE DIAL LOOP — DECIDED (the earner-safety core)
- The LATER seam will call `emit()` from the voice path. Contract + LEARNINGS §4: emit is **fire-and-forget with
  its own timeout** and **never raises into the caller**.
- Impl: `emit()` wraps the `XADD` in `asyncio.wait_for(..., timeout=cfg.emit_timeout_s)` (default **0.25s**), and
  catches EVERYTHING (TimeoutError, ConnectionError, any RedisError) → logs at debug/warn and returns None. A dead
  or slow Redis can NEVER stall or crash a call — worst case the event is dropped, exactly like `NullEventBus`.
- Optional internal bounded `asyncio.Queue` + a background flusher so even the XADD round-trip is off the dial
  coroutine; if the queue is full we drop (never await) — preserve the call over the telemetry. Default to the
  simple guarded-await first; the queue is a documented knob.
- Use **redis.asyncio** (ships in redis-py); all commands are coroutines. **Separate connection for blocking
  consumer reads** (`XREADGROUP BLOCK`) vs the emit/producer connection — a blocking reader on a shared conn would
  stall producers. BLOCK timeout **2000ms** (not infinite) so the consumer loop can run the janitor + check
  shutdown.

## 8. THE CONSUMER CONTRACT (what a sink implements) — DECIDED
A sink registers with `subscribe(stream, group)` → async-iterates `Event`s. Per the Protocol, `subscribe` yields
decoded `Event` objects; the consuming code does its side-effect then must signal ACK. Two clean shapes (we ship
the helper):
- `async for event in bus.subscribe(stream=f"vk:events:{tenant}", group="crm"): handle(event); await bus.ack(...)`
  — but `ack` is NOT on the frozen Protocol, so we expose ack via a context-manager / the consumer loop XACKs after
  the `async for` body returns successfully (auto-ack-on-success), and on body exception we leave it in PEL for
  XAUTOCLAIM retry. This keeps the FROZEN 2-method Protocol intact while giving real at-least-once semantics.
- Consumer responsibilities (documented for sink authors): (1) be **idempotent** keyed on the producer `iid`;
  (2) keep per-item work < min-idle-time (60s) or it'll be reclaimed; (3) on permanent failure, the loop's DLQ
  routing handles it after 3 deliveries. Decode: stream fields are bytes → rebuild `Event(name, call_id, tenant_id,
  ts_iso, payload)`; `payload` is JSON-encoded in a single `payload` field on XADD (avoids field-name explosion +
  keeps nested dicts).

## 9. SEAM NOTE — the LATER flag-gated emit-site wiring (do NOT wire now)
- This wave BUILDS + TESTS the `RedisEventBus` against the FROZEN `EventBus` Protocol, with `NullEventBus` as the
  OFF default. We do NOT touch agent.py / caller.py / aim_voice_agent.py. The live earner is byte-identical
  (agent.py md5 unchanged = 98655dbf).
- LATER (separate founder-signed wave): the kernel/agent path constructs `Event`s at lifecycle points
  (call_started, stage_changed, lead_captured, call_ended, handoff, billing_tick…) and calls `kernel.emit(event)`,
  which forwards to the injected `event_bus`. Wiring is gated behind an env flag (e.g. `EVENTBUS_ENABLED`),
  default OFF → `build_kernel` keeps `NullEventBus` → zero behavior change. Flip to the `RedisEventBus` only with a
  real-flow smoke (call rings before+after) + a revert path, ONE box-mutating change at a time.
- Dashboard/CRM/analytics consumers run as SEPARATE processes/systemd units reading the streams — never inside the
  voice agent process. They scale independently and a crash there cannot touch the call.

## 10. FILES THIS WAVE CREATES (disjoint, under voice_kernel/events/) — PLAN
- `events/__init__.py` — exports `RedisEventBus`, `build_event_bus(cfg, redis=...)`, the consumer helpers.
- `events/bus.py` — `RedisEventBus` binding `EventBus`: guarded `emit` (§7), `subscribe` (§8), lazy idempotent
  group create, version-probe for IDMP (8.6) / CG-aware trim (8.2), serialize/deserialize `Event`.
- `events/consumer.py` — the consumer loop runtime: two-phase startup, BLOCK read, auto-ack-on-success,
  XAUTOCLAIM janitor, DLQ routing (the reusable base for dashboard/crm/analytics sinks).
- `events/config.py` (or extend the existing `EventBusConfig`) — redis url, emit_timeout_s=0.25, block_ms=2000,
  maxlen=100_000, min_idle_ms=60_000, claim_count=50, max_deliveries=3, stream/group name builders.
- `events/tests/` — fakeredis/real-redis tests: ordering, at-least-once redelivery, idempotent dedup, crash→
  XAUTOCLAIM reclaim, poison→DLQ, MAXLEN bound, **emit-never-blocks/never-raises when Redis is down** (the earner
  guarantee), tenant isolation (consumer for A cannot read B's stream).

---
## DECISIONS (one-liners)
1. Redis Streams (durable, consumer groups) — NOT Pub/Sub, NOT Kafka. Reuse the one Redis already on the box.
2. Stream-per-tenant `vk:events:{tenant_id}`; consumer-group-per-sink (dashboard/crm/analytics) — isolated fan-out.
3. Per-tenant total ordering via Redis-stamped `*` IDs; `ts_iso` is payload, not the stream ID.
4. At-least-once delivery + idempotent consumers; native IDMP producer-dedup on Redis 8.6+ (version-gated).
5. Crash recovery: two-phase startup read + XAUTOCLAIM janitor (idle 60s, COUNT 50); poison → DLQ after 3 deliveries.
6. Bounded streams `MAXLEN ~ 100k`; CG-aware trim on Redis 8.2+ (version-gated) to avoid trimming un-consumed lag.
7. emit() = guarded `asyncio.wait_for` (250ms) + catch-all → never blocks/raises into the dial loop (earner-safe).
8. Consumer contract = subscribe→async-iterate Event, auto-XACK-on-success, leave-in-PEL-on-failure, idempotent on iid.
9. Emit-site wiring is a LATER flag-gated seam (default OFF = NullEventBus); build+test module only; agent.py untouched.
