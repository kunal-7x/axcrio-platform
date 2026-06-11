# narrative-reports (service)

> Plane: **EXPERIENCE** · Build phase: **P1** · Runtime: NestJS (Fastify) · §20 deployable.
> EXPERIENCE plane (§3/§17). Trust surfaces: autopilot levels, approvals, the AI-CMO brief, the public API.

## Purpose
AI CMO Brief: daily WhatsApp voice note + card (spend, CPqL vs target, best/worst creative, 1 decision). Numbers from the metrics layer only (§17.4).

## Owns (write model — P2: no other service reads this DB)
brief composer, schedule

## Events
- **Emits:** report.briefed
- **Consumes:** metrics layer reads

## Status
**Phase-0 placeholder.** Contracts-first (P1): code lands only after this service's OpenAPI 3.1
(`contracts/openapi/narrative-reports.yaml`) + AsyncAPI 3 (`contracts/asyncapi/narrative-reports.yaml`) contract exists.
Built in phase **P1** (§21). Do not add business logic before then.
