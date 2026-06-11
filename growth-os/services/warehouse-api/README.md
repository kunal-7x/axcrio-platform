# warehouse-api (service)

> Plane: **DATA** · Build phase: **P2** · Runtime: NestJS (Fastify) · §20 deployable.
> DATA & SIGNALS plane (§3/§8). Deterministic journey truth: click-ID -> conversation -> call -> booking -> sale.

## Purpose
ClickHouse read API + the SEMANTIC METRICS LAYER (CPL, CPqL=NORTH STAR, ROAS...). One metric definition everywhere (§8.5).

## Owns (write model — P2: no other service reads this DB)
metrics layer, ad_metrics_4h, journeys, spend_daily

## Events
- **Emits:** benchmark.updated (rollups)
- **Consumes:** ad.metrics.snapshot, all events (mirror)

## Status
**Phase-0 placeholder.** Contracts-first (P1): code lands only after this service's OpenAPI 3.1
(`contracts/openapi/warehouse-api.yaml`) + AsyncAPI 3 (`contracts/asyncapi/warehouse-api.yaml`) contract exists.
Built in phase **P2** (§21). Do not add business logic before then.
