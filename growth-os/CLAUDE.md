# GROWTH OS — builder instructions

**Read `GROWTH-OS-BUILD-SPEC.md` fully before any task.**

- The §2 design principles **P1–P12 are LAW** (contracts-first; event-sourced; idempotency; money is sacred; explanations; tenant isolation; degrade gracefully; LLM via gateway; respect learning phases; observable; India-first; boring tech).
- **Build ONLY the phase the orchestrator names** (§21). NEVER "build everything." Stop at the phase's acceptance criteria.
- **Contracts-first (P1):** never write a service's code before its OpenAPI 3.1 / AsyncAPI 3 contract + JSON Schemas exist in `/contracts`. CI must fail on contract drift.
- `⚠ VERIFY-LIVE` items: check the current external API docs at build time, do not trust the static spec.
- **Reuse the live Famit/Axcrio platform (Tenant Zero)** per the spec's "Orchestrator Notes": do NOT rebuild voice/WhatsApp/AI-Manager/AI-Asset — wrap them via the Engagement/Creative planes + the Origin Platform Connector.
- Pseudocode in the spec = the required algorithm. Schema field names = canonical.
