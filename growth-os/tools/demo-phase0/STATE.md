# Phase-0 RAILS build — STATE (agent: rails — events/bus/temporal/otel/demo)

Role: scaffold the rails. Reconciled with a PARALLEL session that built the `packages/events`
core + packages/{auth,config,metering,sdk,ui} + services/core + infra/compose + CI + codegen umbrella.

## DONE — all green
- [x] Root monorepo files reconciled (package.json scripts, pnpm-workspace, turbo, tsconfig.base).
- [x] tools/codegen: lib.mjs, build-registry.mjs (drift mechanism, `{schemas:{name:{version,sha256}}}`),
      validate-schemas.mjs, bundle-schemas.mjs, generate-types.mjs (single-pass, no dup interfaces),
      drift.test.mjs (3 tests incl CLI end-to-end intentional-edit-fails). package.json added.
- [x] Registry snapshot regenerated to cover ALL 25 frozen schemas (was 20; added the 5 sibling artifacts). `--check` passes.
- [x] FIXED sibling validator.ts ajv ESM-interop typecheck bug (named import Ajv2020 + FormatsPlugin cast).
      Added OffContractEventError + assertOnContract (strict unknown-type rejection) — sibling picked up the exports.
- [x] packages/events: my envelope.ts + idempotency.ts (exported from index). Typed catalog layer (generated) exported.
      6 tests pass, build+typecheck clean.
- [x] packages/otel: tracing.ts (NodeTracerProvider + ConsoleSpanExporter dev / OTLP box; OTel 1.30 API:
      new Resource(), spanProcessors ctor) + spans.ts (withSpan / inject/extract / continueFromEnvelope for
      bus trace continuity). 4 tests pass (incl trace spans the bus hop). build+typecheck clean.
- [x] services/temporal-worker: activities.ts (emit campaign.requested + saga compensation -> bus),
      workflows.ts (HelloSaga w/ compensation/rollback), worker.ts, trigger-hello.ts, shared.ts, index.ts.
      3 activity tests pass. typecheck clean. @temporalio 1.11.6.
- [x] tools/demo-phase0: run.ts + ledger.ts (HashChainedLedger prev_hash->hash, verify(), tamper negative-control)
      + README + package.json (test = the demo, self-asserting). DEMO PASSES: publish campaign.requested ->
      consume -> ledger seq0 -> publish lead.captured -> ledger seq1 (chained) -> trace continuity proven
      (consume span child of publish, same traceId) -> tamper detected. acceptance: PASS.
- [x] CI: added phase0-demo job (runs the demo on the in-memory bus — acceptance proven in CI, not faked).
- [x] FULL WORKSPACE: typecheck 14/14, test 15/15 (incl sibling core), contracts:validate + drift pass, lint clean.

## VERIFY-LIVE / box-required (documented, not faked — D8)
- Real Redpanda bus, durable Temporal HelloSaga run, OTLP->Tempo all need infra/docker-compose.dev.yml (6 containers).
  See tools/demo-phase0/README.md "What needs Docker". DO droplets 3/3 full -> prod needs a box/limit-raise.

## NO open forks. NO git (not asked).
