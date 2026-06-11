# strategy-compiler (agent)

> Plane: **INTELLIGENCE** · Build phase: **P1** · Runtime: Python 3.12 / FastAPI · uv workspace member · §20 deployable.

## Purpose
CIB -> MediaPlan (concrete campaign/adset/ad tree per platform). Deterministic given CIB+config; validated vs media_plan.schema.json (§9.9).

## Status
**Phase-0 placeholder.** Contracts-first (P1). All structured outputs are validated against the
JSON Schemas in `/contracts/schemas`. All model calls go through the LLM Gateway (P8) — no raw
provider SDK calls. Built in phase **P1** (§21).

## uv workspace
A `pyproject.toml` (package `growth_os_strategy_compiler`) makes this a uv workspace member
(root `pyproject.toml` -> `[tool.uv.workspace] members = ["agents/*"]`). Code lands in its phase.
