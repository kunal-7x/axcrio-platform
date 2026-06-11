# attribution (service)

> Plane: **DATA** · Build phase: **P4** · Runtime: NestJS (Fastify) · §20 deployable.
> DATA & SIGNALS plane (§3/§8). Deterministic journey truth: click-ID -> conversation -> call -> booking -> sale.

## Purpose
Deterministic journey attribution + incrementality (geo-holdout, MMM-lite). Never present platform ROAS as truth (§8.6).

## Owns (write model — P2: no other service reads this DB)
journey attribution, holdout config

## Events
- **Emits:** insight.discovered (lift)
- **Consumes:** journeys, spend_daily

## Status
**Phase-0 placeholder.** Contracts-first (P1): code lands only after this service's OpenAPI 3.1
(`contracts/openapi/attribution.yaml`) + AsyncAPI 3 (`contracts/asyncapi/attribution.yaml`) contract exists.
Built in phase **P4** (§21). Do not add business logic before then.
