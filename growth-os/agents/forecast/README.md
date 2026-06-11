# forecast (agent)

> Plane: **INTELLIGENCE** · Build phase: **P2** · Runtime: Python 3.12 / FastAPI · uv workspace member · §20 deployable.

## Purpose
Forecast + War-Game: Monte-Carlo pre-launch from cohort posteriors -> min_viable_test, P(hit target), expected range; powers the reverse planner (§14.5).

## Status
**Phase-0 placeholder.** Contracts-first (P1). All structured outputs are validated against the
JSON Schemas in `/contracts/schemas`. All model calls go through the LLM Gateway (P8) — no raw
provider SDK calls. Built in phase **P2** (§21).

## uv workspace
A `pyproject.toml` (package `growth_os_forecast`) makes this a uv workspace member
(root `pyproject.toml` -> `[tool.uv.workspace] members = ["agents/*"]`). Code lands in its phase.
