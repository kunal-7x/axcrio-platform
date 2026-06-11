# copy (service)

> Plane: **CREATIVE** · Build phase: **P2** · Runtime: NestJS (Fastify) · §20 deployable.
> CREATIVE plane (§3/§15). Pipelines, not prompts; deterministic typography; REUSE the live AI Asset Service for gen-backgrounds.

## Purpose
Copy generation along the diversity matrix (5 hooks x 1 body before 1 x 5); per-language register (§15).

## Owns (write model — P2: no other service reads this DB)
copy variants

## Events
- **Emits:** creative.generated (copy)
- **Consumes:** creative.requested

## Status
**Phase-0 placeholder.** Contracts-first (P1): code lands only after this service's OpenAPI 3.1
(`contracts/openapi/copy.yaml`) + AsyncAPI 3 (`contracts/asyncapi/copy.yaml`) contract exists.
Built in phase **P2** (§21). Do not add business logic before then.
