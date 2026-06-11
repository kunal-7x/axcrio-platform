# public-api (service)

> Plane: **EXPERIENCE** · Build phase: **P3** · Runtime: NestJS (Fastify) · §20 deployable.
> EXPERIENCE plane (§3/§17). Trust surfaces: autopilot levels, approvals, the AI-CMO brief, the public API.

## Purpose
Everything the dashboard can do, the API can do; signed webhooks lead.*/optimization.decision/report.*. Sellable standalone (§17.5).

## Owns (write model — P2: no other service reads this DB)
public REST, signed webhooks-out

## Events
- **Emits:** webhook.delivered
- **Consumes:** (all canonical events)

## Status
**Phase-0 placeholder.** Contracts-first (P1): code lands only after this service's OpenAPI 3.1
(`contracts/openapi/public-api.yaml`) + AsyncAPI 3 (`contracts/asyncapi/public-api.yaml`) contract exists.
Built in phase **P3** (§21). Do not add business logic before then.
