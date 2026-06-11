# creative-qa (service)

> Plane: **CREATIVE** · Build phase: **P1** · Runtime: NestJS (Fastify) · §20 deployable.
> CREATIVE plane (§3/§15). Pipelines, not prompts; deterministic typography; REUSE the live AI Asset Service for gen-backgrounds.

## Purpose
Gate before launchable: spec/brand/compliance/pre-flight score + Entity-ID cluster-risk diversity rubric (block <8/10) (§15.4).

## Owns (write model — P2: no other service reads this DB)
QA rubric, cluster detector

## Events
- **Emits:** creative.qa.evaluated
- **Consumes:** creative.generated

## Status
**Phase-0 placeholder.** Contracts-first (P1): code lands only after this service's OpenAPI 3.1
(`contracts/openapi/creative-qa.yaml`) + AsyncAPI 3 (`contracts/asyncapi/creative-qa.yaml`) contract exists.
Built in phase **P1** (§21). Do not add business logic before then.
