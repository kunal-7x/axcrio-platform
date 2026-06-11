# ai-manager (service)

> Plane: **EXPERIENCE** · Build phase: **P3** · Runtime: NestJS (Fastify) · §20 deployable.
> EXPERIENCE plane (§3/§17). Trust surfaces: autopilot levels, approvals, the AI-CMO brief, the public API.

## Purpose
Phone/WA command center — EXTENDS the live AI Manager. Commands -> SAME ActionPlan path (no side door); caller verify + read-back for money (§17.3).

## Owns (write model — P2: no other service reads this DB)
NLU intent map, command grammar

## Events
- **Emits:** action.plan.created
- **Consumes:** voice/WA inbound commands

## Status
**Phase-0 placeholder.** Contracts-first (P1): code lands only after this service's OpenAPI 3.1
(`contracts/openapi/ai-manager.yaml`) + AsyncAPI 3 (`contracts/asyncapi/ai-manager.yaml`) contract exists.
Built in phase **P3** (§21). Do not add business logic before then.
