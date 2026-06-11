# identity (service)

> Plane: **DATA** · Build phase: **P1** · Runtime: NestJS (Fastify) · §20 deployable.
> DATA & SIGNALS plane (§3/§8). Deterministic journey truth: click-ID -> conversation -> call -> booking -> sale.

## Purpose
One person_id per human across phone/wa_id/email/click-IDs/CRM; deterministic merge; DPDP erasure entry (§8.3).

## Owns (write model — P2: no other service reads this DB)
persons, identifiers, merges, journey<->person map

## Events
- **Emits:** identity.resolved (re-keys correlation_id)
- **Consumes:** lead.captured, call.completed, wa.message.*

## Status
**Phase-0 placeholder.** Contracts-first (P1): code lands only after this service's OpenAPI 3.1
(`contracts/openapi/identity.yaml`) + AsyncAPI 3 (`contracts/asyncapi/identity.yaml`) contract exists.
Built in phase **P1** (§21). Do not add business logic before then.
