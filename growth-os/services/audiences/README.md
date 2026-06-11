# audiences (service)

> Plane: **ACTIVATION** · Build phase: **P3** · Runtime: NestJS (Fastify) · §20 deployable.
> ACTIVATION plane (§3/§10). Money mutations are STRUCTURALLY gated: connectors accept writes ONLY from the executor, which only runs SIGNED ActionPlans (P4).

## Purpose
Customer-list (hashed, consent-checked), engagement + ★conversation-outcome audiences; exclusion hygiene (§10.5).

## Owns (write model — P2: no other service reads this DB)
audience defs, hashed lists

## Events
- **Emits:** audience.health
- **Consumes:** lead.scored, call.outcome, sale.recorded

## Status
**Phase-0 placeholder.** Contracts-first (P1): code lands only after this service's OpenAPI 3.1
(`contracts/openapi/audiences.yaml`) + AsyncAPI 3 (`contracts/asyncapi/audiences.yaml`) contract exists.
Built in phase **P3** (§21). Do not add business logic before then.
