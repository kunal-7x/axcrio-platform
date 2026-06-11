# llm-gateway (agent)

> Plane: **INTELLIGENCE** · Build phase: **P2** · Runtime: Python 3.12 / FastAPI · uv workspace member · §20 deployable.

## Purpose
All model calls route here: tiers reasoning|bulk|cheap; structured-output validation vs /contracts/schemas; per-tenant token budgets->credit.consumed; cache; eval traces (§9.1, P8). NO raw SDK calls in services.

## Status
**Phase-0 placeholder.** Contracts-first (P1). All structured outputs are validated against the
JSON Schemas in `/contracts/schemas`. All model calls go through the LLM Gateway (P8) — no raw
provider SDK calls. Built in phase **P2** (§21).

## uv workspace
A `pyproject.toml` (package `growth_os_llm_gateway`) makes this a uv workspace member
(root `pyproject.toml` -> `[tool.uv.workspace] members = ["agents/*"]`). Code lands in its phase.
