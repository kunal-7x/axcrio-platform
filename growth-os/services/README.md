# services/ — NestJS (Fastify) bounded contexts

~30 deployables at maturity (§3), grouped by plane. **Phase 0–1 deploys collapse these into a few
processes** (§20): `core` (gateway+tenants+integration-hub+ledger+flags+notify+billing-stub as ONE
modular app), `data`, `activation`, `creative`. Each directory here is a **bounded context** = a
future split line; most are Phase-0 README placeholders today.

| plane | services |
|-------|----------|
| CORE | core* (modular: gateway, tenants, integration-hub, ledger, flags, notify), billing |
| DATA & SIGNALS | ingestion, tracking, identity, **signals★**, warehouse-api, attribution, benchmarks |
| ACTIVATION | campaign-compiler, executor, connector-meta, connector-google, audiences, budget-governor, experiments, optimizer, compliance-engine |
| CREATIVE | brand-kit, creative-studio, video-studio, copy, creative-qa, dam, landing-pages, catalog |
| ENGAGEMENT (reuse Famit) | whatsapp, voice-adapter, journeys, crm-sync |
| EXPERIENCE | approval-inbox, ai-manager, narrative-reports, public-api |

\* `core` is built by the core session; the Origin Platform Connector lives **inside** its
integration-hub module as `provider:origin` (D4), not as a separate deployable.

**Rules:** P1 contracts-first (no code before the contract). P2 each service owns its write model —
**no service reads another's DB**; cross-service only via events. P4 money mutations only through the
executor on a signed ActionPlan. See each service README for purpose/owns/emits/consumes/phase.
