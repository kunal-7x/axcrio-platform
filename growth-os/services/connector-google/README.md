# connector-google (service)

> Plane: **ACTIVATION** · Build phase: **P3** · Runtime: NestJS (Fastify) · §20 deployable.
> ACTIVATION plane (§3/§10). Money mutations are STRUCTURALLY gated: connectors accept writes ONLY from the executor, which only runs SIGNED ActionPlans (P4).

## Purpose
Google Search/PMax + Enhanced Conversions + offline adjustments; test accounts; write = executor-only (§10.4).

## Owns (write model — P2: no other service reads this DB)
Google Ads client, rate buckets

## Events
- **Emits:** ad.metrics.snapshot
- **Consumes:** executor mutation commands

## Status
**Phase-0 placeholder.** Contracts-first (P1): code lands only after this service's OpenAPI 3.1
(`contracts/openapi/connector-google.yaml`) + AsyncAPI 3 (`contracts/asyncapi/connector-google.yaml`) contract exists.
Built in phase **P3** (§21). Do not add business logic before then.
