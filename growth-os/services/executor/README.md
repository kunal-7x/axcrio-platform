# executor (service)

> Plane: **ACTIVATION** · Build phase: **P1** · Runtime: NestJS (Fastify) · §20 deployable.
> ACTIVATION plane (§3/§10). Money mutations are STRUCTURALLY gated: connectors accept writes ONLY from the executor, which only runs SIGNED ActionPlans (P4).

## Purpose
The ONLY component allowed to call connector mutations; consumes SIGNED ActionPlans; Temporal LaunchSaga + compensation (§10.2, P4).

## Owns (write model — P2: no other service reads this DB)
execution saga, platform-id writeback

## Events
- **Emits:** action.executed, action.failed, action.rolled_back
- **Consumes:** action.plan.signed

## Status
**Phase-0 placeholder.** Contracts-first (P1): code lands only after this service's OpenAPI 3.1
(`contracts/openapi/executor.yaml`) + AsyncAPI 3 (`contracts/asyncapi/executor.yaml`) contract exists.
Built in phase **P1** (§21). Do not add business logic before then.
