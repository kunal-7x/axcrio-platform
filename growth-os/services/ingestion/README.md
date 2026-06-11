# ingestion (service)

> Plane: **DATA** · Build phase: **P1** · Runtime: NestJS (Fastify) · §20 deployable.
> DATA & SIGNALS plane (§3/§8). Deterministic journey truth: click-ID -> conversation -> call -> booking -> sale.

## Purpose
One hardened front door for ALL inbound webhooks; verify sig -> persist raw -> normalize -> emit canonical event (§8.2).

## Owns (write model — P2: no other service reads this DB)
webhooks_raw, verify tokens, normalizers

## Events
- **Emits:** lead.captured, wa.message.received, call.completed, sale.recorded
- **Consumes:** (external webhooks: Meta leadgen, WABA, Razorpay, origin)

## Status
**Phase-0 placeholder.** Contracts-first (P1): code lands only after this service's OpenAPI 3.1
(`contracts/openapi/ingestion.yaml`) + AsyncAPI 3 (`contracts/asyncapi/ingestion.yaml`) contract exists.
Built in phase **P1** (§21). Do not add business logic before then.
