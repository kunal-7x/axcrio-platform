# catalog (service)

> Plane: **CREATIVE** · Build phase: **P4** · Runtime: NestJS (Fastify) · §20 deployable.
> CREATIVE plane (§3/§15). Pipelines, not prompts; deterministic typography; REUSE the live AI Asset Service for gen-backgrounds.

## Purpose
E-comm feed: Shopify/Woo -> normalized -> Meta catalog + Google Merchant Center; diagnostics; powers Advantage+ DPA/PMax (§15.7).

## Owns (write model — P2: no other service reads this DB)
product feed, sync state

## Events
- **Emits:** catalog.synced
- **Consumes:** shopify/woo webhooks

## Status
**Phase-0 placeholder.** Contracts-first (P1): code lands only after this service's OpenAPI 3.1
(`contracts/openapi/catalog.yaml`) + AsyncAPI 3 (`contracts/asyncapi/catalog.yaml`) contract exists.
Built in phase **P4** (§21). Do not add business logic before then.
