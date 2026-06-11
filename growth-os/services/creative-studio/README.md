# creative-studio (service)

> Plane: **CREATIVE** · Build phase: **P1** · Runtime: NestJS (Fastify) · §20 deployable.
> CREATIVE plane (§3/§15). Pipelines, not prompts; deterministic typography; REUSE the live AI Asset Service for gen-backgrounds.

## Purpose
Statics PIPELINE (not a prompt): brief->layout->background->deterministic typography->brand->locale->DAM. REUSE the live AI Asset Service for gen-background (§15.2).

## Owns (write model — P2: no other service reads this DB)
render pipeline, compositor

## Events
- **Emits:** creative.generated
- **Consumes:** creative.requested (from CIB cells)

## Status
**Phase-0 placeholder.** Contracts-first (P1): code lands only after this service's OpenAPI 3.1
(`contracts/openapi/creative-studio.yaml`) + AsyncAPI 3 (`contracts/asyncapi/creative-studio.yaml`) contract exists.
Built in phase **P1** (§21). Do not add business logic before then.
