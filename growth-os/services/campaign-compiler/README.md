# campaign-compiler (service)

> Plane: **ACTIVATION** · Build phase: **P1** · Runtime: NestJS (Fastify) · §20 deployable.
> ACTIVATION plane (§3/§10). Money mutations are STRUCTURALLY gated: connectors accept writes ONLY from the executor, which only runs SIGNED ActionPlans (P4).

## Purpose
MediaPlan -> exact platform payloads (Meta MAPI v25+ baked, ⚠VERIFY-LIVE); budget floor; dry-run diff (§10.1).

## Owns (write model — P2: no other service reads this DB)
platform payload builders, dry-run differ

## Events
- **Emits:** campaign.compiled
- **Consumes:** strategy.compiled

## Status
**Phase-0 placeholder.** Contracts-first (P1): code lands only after this service's OpenAPI 3.1
(`contracts/openapi/campaign-compiler.yaml`) + AsyncAPI 3 (`contracts/asyncapi/campaign-compiler.yaml`) contract exists.
Built in phase **P1** (§21). Do not add business logic before then.
