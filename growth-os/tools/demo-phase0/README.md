# Phase-0 Demo — the rails, proven

The Phase-0 acceptance (`GROWTH-OS-BUILD-SPEC.md` §21; `docs/architecture-phase0.md` §6):

> a demo publishes `campaign.requested` → a consumer handles it → a Ledger entry is written
> (hash-chained) → the OTel trace is visible end-to-end; and the contract-drift test fails on
> an intentional schema edit.

This directory delivers the demo. It runs **on the laptop with no Docker** (in-memory bus,
console OTel exporter), so the rails are proven without the heavy compose stack (D8 honest-env).
It does NOT depend on the `services/core` HTTP app booting — the Phase-0 acceptance is the
event backbone + ledger chain + trace, which this proves self-contained.

## Run it

```bash
pnpm demo:phase0          # from the repo root
# or:  pnpm --filter @growth-os/demo-phase0 demo
```

What you'll see (and what it proves):

| Step | Proves |
|------|--------|
| 1. OTel init (console exporter) | P10 observability; spans print to stdout |
| 2. Consumer subscribes | the event-driven consume path |
| 3. Publish `campaign.requested` in a publish span | typed `createEnvelope` + bus + **schema validation on publish** (P1: off-contract events are rejected) |
| 3b. Consumer writes a ledger entry | "consumed → ledger entry"; the consume span is a **child of the publish span** (one trace spans the bus hop) |
| 4. Publish `lead.captured` | a second hash-chain link in the same journey (`correlation_id`) |
| 5. Ledger hash chain printed + verified | §7.4/§5.5 tamper-evident `prev_hash → hash` chain |
| 6. Tamper negative-control | mutating an earlier entry **breaks** `verify()` — the chain has teeth |

The script **exits non-zero** if any assertion fails, so it doubles as a CI test
(`pnpm test` runs it; see `.github/workflows/ci.yml` job `phase0-demo`).

### Trace continuity

The publish span and the consume span share a `traceId`, and the consume span's `parentId`
is the publish span — the W3C `traceparent` rides inside `envelope.trace` across the bus
(`injectTraceContext` on publish, `continueFromEnvelope` on consume). That's the single
end-to-end trace the acceptance asks for.

## The contract-drift test

```bash
pnpm contracts:drift                          # CLI: passes when frozen schemas match the snapshot
pnpm --filter @growth-os/codegen test          # the unit test (3 cases incl. an intentional edit -> non-zero exit)
```

`tools/codegen/build-registry.mjs --check` recomputes the sha256 of every frozen schema
(LF-normalized, cross-OS stable) and fails if any differs from
`contracts/registry/event-backbone.drift-snapshot.json`. A legitimate change is re-frozen with
`pnpm contracts:snapshot` and must carry a version bump (§6.2 extend-never-mutate).

## What needs Docker / a box (NOT this demo)

The demo deliberately avoids them. The following are **written as files** but require the
`infra/docker-compose.dev.yml` stack (postgres, redpanda, redis, clickhouse, temporal, minio)
which is RAM/CPU-heavy and box-required to boot (D8; DO droplets 3/3 full):

- **Real bus (Redpanda):** set `KAFKA_BROKERS` (or `REDPANDA_BROKERS`) and the same code uses
  `KafkaEventBus` instead of the in-memory bus (`packages/events/src/bus.ts`) — validation,
  tenant-partitioning, and trace headers identical.
- **Temporal HelloSaga (durable):** `pnpm infra:up` then
  `pnpm --filter @growth-os/temporal-worker worker` (worker) and
  `pnpm --filter @growth-os/temporal-worker trigger:hello` (start a run;
  `GROWTH_OS_SAGA_FAIL=1` exercises the compensation/rollback path). Connects to
  `temporal:7233`. The workflow + activities are fully typechecked + unit-tested here; only the
  durable execution needs the server.
- **OTLP traces → Grafana Tempo:** set `OTEL_EXPORTER_OTLP_ENDPOINT`; the OTel SDK swaps the
  console exporter for OTLP with no code change (`packages/otel/src/tracing.ts`).
