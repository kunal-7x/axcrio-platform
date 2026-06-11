# agents/ — INTELLIGENCE plane (Python 3.12 / FastAPI)

The Research War Room + brains (§9, §14). A **uv workspace** (root `pyproject.toml` →
`[tool.uv.workspace] members = ["agents/*"]`). Each agent is a FastAPI service + a uv member.

| agent | phase | role |
|-------|-------|------|
| llm-gateway | P2 | All model calls (tiers reasoning/bulk/cheap), structured-output validation, per-tenant token budgets, cache, eval traces (§9.1, P8) |
| agent-orchestrator | P2 | Research War Room: Temporal workflow → typed agent activities → Synthesizer → CIB (§9.2/§9.3) |
| knowledge | P2 | Vendor Brain / RAG (pgvector), grounds all agents (§9.4) |
| **lead-scoring★** | P1 | Score 0-100 + tier + reasons; feeds the flagship signal loop (§9.5) |
| insight-miner | P2 | Conversation→Creative nightly clustering → insight.discovered (§9.6) |
| memory | P2 | Learning memory + cross-tenant priors; write via memory.updated only (§14) |
| forecast | P2 | War-Game Monte-Carlo; min_viable_test, reverse planner (§14.5) |
| strategy-compiler | P1 | CIB → MediaPlan (deterministic; validated vs media_plan.schema.json) (§9.9) |

**Rules:** P1 contracts-first; every structured output validates against `/contracts/schemas`.
P8 no raw provider SDK calls — everything via the LLM Gateway. India-first (P11): vernacular
first-class. Code lands per phase (§21); today these are placeholders + uv member pyprojects.

```bash
uv sync          # resolve the Python workspace (box/dev env)
uv run pytest    # once agents have code
```
