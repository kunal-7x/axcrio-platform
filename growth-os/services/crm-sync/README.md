# crm-sync (service)

> Plane: **ENGAGEMENT** · Build phase: **P3** · Runtime: NestJS (Fastify) · §20 deployable.
> ENGAGEMENT plane (§3/§16). WRAPS the existing Famit stack (voice/WhatsApp) via adapters + the Origin Connector — do NOT rebuild.

## Purpose
Bi-directional CRM field mapping (HubSpot/Zoho/Sheets/origin); ours is journey source of truth (§16.4).

## Owns (write model — P2: no other service reads this DB)
field maps, sync log

## Events
- **Emits:** crm.synced
- **Consumes:** lead.*, booking.*, sale.recorded

## Status
**Phase-0 placeholder.** Contracts-first (P1): code lands only after this service's OpenAPI 3.1
(`contracts/openapi/crm-sync.yaml`) + AsyncAPI 3 (`contracts/asyncapi/crm-sync.yaml`) contract exists.
Built in phase **P3** (§21). Do not add business logic before then.
