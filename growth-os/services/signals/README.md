# signals (service)

> Plane: **DATA** · Build phase: **P1** · Runtime: NestJS (Fastify) · §20 deployable.
> DATA & SIGNALS plane (§3/§8). Deterministic journey truth: click-ID -> conversation -> call -> booking -> sale.

## Purpose
★FLAGSHIP (§11): ground-truth outcomes -> CAPI/Enhanced-Conversions with value=lead_score; dedup, EMQ reports.

## Owns (write model — P2: no other service reads this DB)
event-mapping config, dispatch log, dedup keys, EMQ

## Events
- **Emits:** signal.dispatched
- **Consumes:** lead.scored, booking.*, sale.recorded, call.outcome

## Status
**Phase-0 placeholder.** Contracts-first (P1): code lands only after this service's OpenAPI 3.1
(`contracts/openapi/signals.yaml`) + AsyncAPI 3 (`contracts/asyncapi/signals.yaml`) contract exists.
Built in phase **P1** (§21). Do not add business logic before then.
