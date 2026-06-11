# experiments (service)

> Plane: **ACTIVATION** · Build phase: **P2** · Runtime: NestJS (Fastify) · §20 deployable.
> ACTIVATION plane (§3/§10). Money mutations are STRUCTURALLY gated: connectors accept writes ONLY from the executor, which only runs SIGNED ActionPlans (P4).

## Purpose
Gamma–Poisson posteriors per arm; Thompson allocation; learning-phase state machine (§12.1).

## Owns (write model — P2: no other service reads this DB)
arms, posteriors, allocations

## Events
- **Emits:** experiment.evaluated
- **Consumes:** ad.metrics.snapshot, lead.scored

## Status
**Phase-0 placeholder.** Contracts-first (P1): code lands only after this service's OpenAPI 3.1
(`contracts/openapi/experiments.yaml`) + AsyncAPI 3 (`contracts/asyncapi/experiments.yaml`) contract exists.
Built in phase **P2** (§21). Do not add business logic before then.
