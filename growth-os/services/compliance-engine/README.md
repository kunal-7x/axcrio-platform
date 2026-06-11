# compliance-engine (service)

> Plane: **ACTIVATION** · Build phase: **P1** · Runtime: NestJS (Fastify) · §20 deployable.
> ACTIVATION plane (§3/§10). Money mutations are STRUCTURALLY gated: connectors accept writes ONLY from the executor, which only runs SIGNED ActionPlans (P4).

## Purpose
Deterministic rule packs per platform/category/geo (RERA, finance, health) + LLM policy critic; pass|fix|block (§10.9).

## Owns (write model — P2: no other service reads this DB)
rule packs, policy critic

## Events
- **Emits:** creative.qa.evaluated (compliance verdict)
- **Consumes:** creative.generated, lp.published

## Status
**Phase-0 placeholder.** Contracts-first (P1): code lands only after this service's OpenAPI 3.1
(`contracts/openapi/compliance-engine.yaml`) + AsyncAPI 3 (`contracts/asyncapi/compliance-engine.yaml`) contract exists.
Built in phase **P1** (§21). Do not add business logic before then.
