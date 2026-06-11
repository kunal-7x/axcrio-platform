# optimizer (service)

> Plane: **ACTIVATION** · Build phase: **P1** · Runtime: NestJS (Fastify) · §20 deployable.
> ACTIVATION plane (§3/§10). Money mutations are STRUCTURALLY gated: connectors accept writes ONLY from the executor, which only runs SIGNED ActionPlans (P4).

## Purpose
Draft/Trash/Promote brain: guardrails G1–G6, promote, mitosis; every decision emits an Explanation (§12, P5).

## Owns (write model — P2: no other service reads this DB)
decision engine, guardrail rules

## Events
- **Emits:** optimization.decision, memory.updated
- **Consumes:** experiment.evaluated, ad.metrics.snapshot

## Status
**Phase-0 placeholder.** Contracts-first (P1): code lands only after this service's OpenAPI 3.1
(`contracts/openapi/optimizer.yaml`) + AsyncAPI 3 (`contracts/asyncapi/optimizer.yaml`) contract exists.
Built in phase **P1** (§21). Do not add business logic before then.
