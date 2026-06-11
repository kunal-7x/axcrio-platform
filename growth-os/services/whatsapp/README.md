# whatsapp (service)

> Plane: **ENGAGEMENT** · Build phase: **P1** · Runtime: NestJS (Fastify) · §20 deployable.
> ENGAGEMENT plane (§3/§16). WRAPS the existing Famit stack (voice/WhatsApp) via adapters + the Origin Connector — do NOT rebuild.

## Purpose
WABA template lifecycle + category-aware cost meter + window-aware sends. ADAPTER over the live whatsapp.py (§16.1, Tenant Zero).

## Owns (write model — P2: no other service reads this DB)
template registry, send scheduler

## Events
- **Emits:** wa.message.sent
- **Consumes:** wa.message.received, journey steps

## Status
**Phase-0 placeholder.** Contracts-first (P1): code lands only after this service's OpenAPI 3.1
(`contracts/openapi/whatsapp.yaml`) + AsyncAPI 3 (`contracts/asyncapi/whatsapp.yaml`) contract exists.
Built in phase **P1** (§21). Do not add business logic before then.
