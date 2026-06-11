# landing-pages (service)

> Plane: **CREATIVE** · Build phase: **P2** · Runtime: NestJS (Fastify) · §20 deployable.
> CREATIVE plane (§3/§15). Pipelines, not prompts; deterministic typography; REUSE the live AI Asset Service for gen-backgrounds.

## Purpose
Block-based SSR LPs; message-match per ad angle; forms->instant lead.captured; click-ID capture; CWV budget (§15.6).

## Owns (write model — P2: no other service reads this DB)
LP blocks, message-match engine

## Events
- **Emits:** lead.captured, lp.cta.click
- **Consumes:** creative.approved

## Status
**Phase-0 placeholder.** Contracts-first (P1): code lands only after this service's OpenAPI 3.1
(`contracts/openapi/landing-pages.yaml`) + AsyncAPI 3 (`contracts/asyncapi/landing-pages.yaml`) contract exists.
Built in phase **P2** (§21). Do not add business logic before then.
