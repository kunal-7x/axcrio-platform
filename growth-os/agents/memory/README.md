# memory (agent)

> Plane: **INTELLIGENCE** · Build phase: **P2** · Runtime: Python 3.12 / FastAPI · uv workspace member · §20 deployable.

## Purpose
Learning Memory: per-tenant playbooks, creative_dna_perf (gene-level), negative_memory; write ONLY via memory.updated events; read via memory.read (§14).

## Status
**Phase-0 placeholder.** Contracts-first (P1). All structured outputs are validated against the
JSON Schemas in `/contracts/schemas`. All model calls go through the LLM Gateway (P8) — no raw
provider SDK calls. Built in phase **P2** (§21).

## uv workspace
A `pyproject.toml` (package `growth_os_memory`) makes this a uv workspace member
(root `pyproject.toml` -> `[tool.uv.workspace] members = ["agents/*"]`). Code lands in its phase.
