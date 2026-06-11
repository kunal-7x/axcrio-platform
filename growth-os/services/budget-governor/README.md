# budget-governor (service)

> Plane: **ACTIVATION** · Build phase: **P1** · Runtime: NestJS (Fastify) · §20 deployable.
> ACTIVATION plane (§3/§10). Money mutations are STRUCTURALLY gated: connectors accept writes ONLY from the executor, which only runs SIGNED ActionPlans (P4).

## Purpose
Money safety as architecture: budget tree, hard caps, anomaly sentinel; every spend-changing plan needs a Governor stamp (§13, P4).

## Owns (write model — P2: no other service reads this DB)
budget tree, caps, stamps, sentinel

## Events
- **Emits:** budget.threshold.crossed, budget.anomaly.detected
- **Consumes:** ad.metrics.snapshot, action.plan.created

## Status
**Phase-0 placeholder.** Contracts-first (P1): code lands only after this service's OpenAPI 3.1
(`contracts/openapi/budget-governor.yaml`) + AsyncAPI 3 (`contracts/asyncapi/budget-governor.yaml`) contract exists.
Built in phase **P1** (§21). Do not add business logic before then.
