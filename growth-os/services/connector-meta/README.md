# connector-meta (service)

> Plane: **ACTIVATION** · Build phase: **P1** · Runtime: NestJS (Fastify) · §20 deployable.
> ACTIVATION plane (§3/§10). Money mutations are STRUCTURALLY gated: connectors accept writes ONLY from the executor, which only runs SIGNED ActionPlans (P4).

## Purpose
Meta read (async insights, entity sync, learning-phase, Ad Library) + write (executor-only); SANDBOX mode (§10.3).

## Owns (write model — P2: no other service reads this DB)
Meta API client, rate buckets, sandbox

## Events
- **Emits:** ad.metrics.snapshot
- **Consumes:** executor mutation commands

## Status
**Phase-0 placeholder.** Contracts-first (P1): code lands only after this service's OpenAPI 3.1
(`contracts/openapi/connector-meta.yaml`) + AsyncAPI 3 (`contracts/asyncapi/connector-meta.yaml`) contract exists.
Built in phase **P1** (§21). Do not add business logic before then.
