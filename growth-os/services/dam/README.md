# dam (service)

> Plane: **CREATIVE** · Build phase: **P1** · Runtime: NestJS (Fastify) · §20 deployable.
> CREATIVE plane (§3/§15). Pipelines, not prompts; deterministic typography; REUSE the live AI Asset Service for gen-backgrounds.

## Purpose
Asset + metadata store: Creative DNA tags, embeddings, perf rollup, fatigue, rights, approval state (§15.5).

## Owns (write model — P2: no other service reads this DB)
assets, DNA, embeddings, rights

## Events
- **Emits:** creative.approved, creative.fatigued
- **Consumes:** creative.qa.evaluated, optimization.decision

## Status
**Phase-0 placeholder.** Contracts-first (P1): code lands only after this service's OpenAPI 3.1
(`contracts/openapi/dam.yaml`) + AsyncAPI 3 (`contracts/asyncapi/dam.yaml`) contract exists.
Built in phase **P1** (§21). Do not add business logic before then.
