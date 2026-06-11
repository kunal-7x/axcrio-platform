# approval-inbox (service)

> Plane: **EXPERIENCE** · Build phase: **P1** · Runtime: NestJS (Fastify) · §20 deployable.
> EXPERIENCE plane (§3/§17). Trust surfaces: autopilot levels, approvals, the AI-CMO brief, the public API.

## Purpose
Unified approval queue (dashboard + WhatsApp interactive Approve/Reject/Ask-why); Temporal signal on response; auto-escalate (§17.2).

## Owns (write model — P2: no other service reads this DB)
approval queue, escalation timers

## Events
- **Emits:** approval.granted, approval.denied
- **Consumes:** approval.requested

## Status
**Phase-0 placeholder.** Contracts-first (P1): code lands only after this service's OpenAPI 3.1
(`contracts/openapi/approval-inbox.yaml`) + AsyncAPI 3 (`contracts/asyncapi/approval-inbox.yaml`) contract exists.
Built in phase **P1** (§21). Do not add business logic before then.
