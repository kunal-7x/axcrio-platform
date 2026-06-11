# video-studio (service)

> Plane: **CREATIVE** · Build phase: **P2** · Runtime: NestJS (Fastify) · §20 deployable.
> CREATIVE plane (§3/§15). Pipelines, not prompts; deterministic typography; REUSE the live AI Asset Service for gen-backgrounds.

## Purpose
Script->storyboard->scene sourcing->TTS VO->Remotion render->DAM (§15.3).

## Owns (write model — P2: no other service reads this DB)
video render pipeline

## Events
- **Emits:** creative.generated
- **Consumes:** creative.requested

## Status
**Phase-0 placeholder.** Contracts-first (P1): code lands only after this service's OpenAPI 3.1
(`contracts/openapi/video-studio.yaml`) + AsyncAPI 3 (`contracts/asyncapi/video-studio.yaml`) contract exists.
Built in phase **P2** (§21). Do not add business logic before then.
