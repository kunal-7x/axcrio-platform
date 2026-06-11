# voice-adapter (service)

> Plane: **ENGAGEMENT** · Build phase: **P1** · Runtime: NestJS (Fastify) · §20 deployable.
> ENGAGEMENT plane (§3/§16). WRAPS the existing Famit stack (voice/WhatsApp) via adapters + the Origin Connector — do NOT rebuild.

## Purpose
Wraps the existing AI calling (LiveKit/Vobiz agent.py). Outbound trigger; consumes call.completed+transcript -> call.outcome; hot-lead SLA<=60s (§16.2).

## Owns (write model — P2: no other service reads this DB)
call triggers, outcome mapper

## Events
- **Emits:** call.outcome
- **Consumes:** call.completed, lead.scored(hot)

## Status
**Phase-0 placeholder.** Contracts-first (P1): code lands only after this service's OpenAPI 3.1
(`contracts/openapi/voice-adapter.yaml`) + AsyncAPI 3 (`contracts/asyncapi/voice-adapter.yaml`) contract exists.
Built in phase **P1** (§21). Do not add business logic before then.
