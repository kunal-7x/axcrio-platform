# journeys (service)

> Plane: **ENGAGEMENT** · Build phase: **P2** · Runtime: NestJS (Fastify) · §20 deployable.
> ENGAGEMENT plane (§3/§16). WRAPS the existing Famit stack (voice/WhatsApp) via adapters + the Origin Connector — do NOT rebuild.

## Purpose
Declarative follow-up DSL (WA+voice); every step consent+cap-checked; the journey IS the signal factory (§16.3).

## Owns (write model — P2: no other service reads this DB)
journey defs, step runner

## Events
- **Emits:** wa.message.sent, call.initiated
- **Consumes:** lead.captured, wa.message.received, call.outcome

## Status
**Phase-0 placeholder.** Contracts-first (P1): code lands only after this service's OpenAPI 3.1
(`contracts/openapi/journeys.yaml`) + AsyncAPI 3 (`contracts/asyncapi/journeys.yaml`) contract exists.
Built in phase **P2** (§21). Do not add business logic before then.
