# brand-kit (service)

> Plane: **CREATIVE** · Build phase: **P2** · Runtime: NestJS (Fastify) · §20 deployable.
> CREATIVE plane (§3/§15). Pipelines, not prompts; deterministic typography; REUSE the live AI Asset Service for gen-backgrounds.

## Purpose
Logos, palette, self-hosted licensed fonts, tone axes, do/dont, locale variants; auto-extracted at onboarding; versioned (§15.1).

## Owns (write model — P2: no other service reads this DB)
brand kit versions

## Events
- **Emits:** brandkit.updated
- **Consumes:** onboarding crawl

## Status
**Phase-0 placeholder.** Contracts-first (P1): code lands only after this service's OpenAPI 3.1
(`contracts/openapi/brand-kit.yaml`) + AsyncAPI 3 (`contracts/asyncapi/brand-kit.yaml`) contract exists.
Built in phase **P2** (§21). Do not add business logic before then.
