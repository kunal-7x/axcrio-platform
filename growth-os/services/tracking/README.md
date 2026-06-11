# tracking (service)

> Plane: **DATA** · Build phase: **P1** · Runtime: NestJS (Fastify) · §20 deployable.
> DATA & SIGNALS plane (§3/§8). Deterministic journey truth: click-ID -> conversation -> call -> booking -> sale.

## Purpose
1P measurement: pixel, click-ID capture (fbclid/gclid/wbraid), UTM canon, session stitching, server-side tag (§8.1).

## Owns (write model — P2: no other service reads this DB)
pixel endpoint, sessions, click-ID store

## Events
- **Emits:** lead.captured (mints correlation_id), page.view
- **Consumes:** —

## Status
**Phase-0 placeholder.** Contracts-first (P1): code lands only after this service's OpenAPI 3.1
(`contracts/openapi/tracking.yaml`) + AsyncAPI 3 (`contracts/asyncapi/tracking.yaml`) contract exists.
Built in phase **P1** (§21). Do not add business logic before then.
