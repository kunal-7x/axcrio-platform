# benchmarks (service)

> Plane: **DATA** · Build phase: **P3** · Runtime: NestJS (Fastify) · §20 deployable.
> DATA & SIGNALS plane (§3/§8). Deterministic journey truth: click-ID -> conversation -> call -> booking -> sale.

## Purpose
Anonymized cross-tenant CPL/CPqL/CTR/CVR by industry×geo×objective; k-anon (cells>=8) + noise (§8.7, moat 4).

## Owns (write model — P2: no other service reads this DB)
benchmark cells, cohort priors

## Events
- **Emits:** benchmark.updated
- **Consumes:** creative_dna_perf (aggregated)

## Status
**Phase-0 placeholder.** Contracts-first (P1): code lands only after this service's OpenAPI 3.1
(`contracts/openapi/benchmarks.yaml`) + AsyncAPI 3 (`contracts/asyncapi/benchmarks.yaml`) contract exists.
Built in phase **P3** (§21). Do not add business logic before then.
