# BRAIN — GROWTH OS (autonomous-ads flagship, NEW monorepo)

Durable facts + learnings for the GROWTH OS build. Append, never delete.
Monorepo: `C:\Users\kunal\Desktop\caps\growth-os\`. Bible: `growth-os/GROWTH-OS-BUILD-SPEC.md`
(§2 P1–P12 = LAW; 25 sections + appendices). Builder rules: `growth-os/CLAUDE.md`.
This is a STANDALONE product; the LIVE Famit/Axcrio platform is **Tenant Zero** (reuse, never rebuild).

## PHASE 0 ARCHITECTURE — locked (`growth-os/docs/architecture-phase0.md`, 2026-06-11)
The Phase-0/1 build architecture doc. 8 decisions locked (D1–D8):
- **D1** core = ONE modular NestJS(Fastify) app bundling gateway+tenants+integration-hub+ledger+flags+notify+billing-stub.
- **D2** GROWTH OS uses **Temporal** for durable workflows; **Famit keeps Hatchet** (F3, own box). They bridge ONLY at the
  Origin Connector envelope — never share a workflow engine.
- **D3** event bus = **Redpanda** (Kafka API) + JSON-Schema registry; Famit stays Postgres-broker (bridge = the connector's HTTP door).
- **D4** Origin Platform Connector = a `provider:origin` INSIDE integration-hub, NOT a separate deployable.
- **D5** Phase-0 auth = dev JWT stub behind `packages/auth`; OIDC (Logto already live for Famit) swaps in Phase 3.
- **D6** money/spend STRUCTURALLY impossible in Phase 0 (no connector mutation path; only Ledger+ActionPlan contract exist).
- **D7** envelope + 15 core events + CIB + MediaPlan + ActionPlan = frozen-after-merge JSON Schemas; CI fails on drift.
- **D8** local toolchain present (Node 22 / pnpm 10 / uv 0.11 / Docker 29) → typecheck/lint/schema-validate/contract-drift
  RUN locally; full 6-container compose (postgres/redpanda/clickhouse/temporal/redis/minio) is written as FILES but
  **box-required to boot** (laptop too small + DO droplets 3/3 full → prod needs a box/limit-raise).

## ★ ORIGIN PLATFORM CONNECTOR (the bridge — §3 of the doc)
- TWO directions: **PUSH** Famit→GROWTH OS (`POST /v1/origin/events` batch + `/v1/origin/webhook/{kind}`) and
  **PULL** Famit←GROWTH OS (`GET /v1/origin/{campaigns,reports,leads,signals}` read projections for the panel).
- AUTH = per-connection **service token** (`ORIGIN_SERVICE_TOKEN`, Bearer; mirrors live `AIASSET_SERVICE_TOKEN`/
  `AIM_SERVICE_TOKEN`). **Tenant from TOKEN, never body** (the live isolation rule; negative control must fail to forge).
  `Idempotency-Key` = Famit source id → exactly-once. Webhook-OUT signed HMAC-SHA256 `X-GrowthOS-Signature`, fail-closed.
- EVENT MAP (existing Famit data → canonical event, §6.1 envelope, topic `plane.entity.verb`):
  caller `/campaigns`+`/run`→`campaign.requested`; dial-loop `_classify_outcome`→`call.completed`; AIM post-call→
  `call.outcome`(intents/qualification/booking — the moat feed); `whatsapp.py`/inbound→`wa.message.sent|received`
  (CTWA `ctwa_clid`+ad id = §11.2 loop); form/CTWA first touch→`lead.captured`(mints correlation_id; phone=king in India);
  booking→`booking.created|attended`; payments→`sale.recorded`(order_value INR paise = true Purchase value);
  asset svc `/generate`→`creative.generated`. Crown jewels: `call.outcome` + `lead.captured/scored` + CTWA `wa.received`.
- Phase 0 ships the CONTRACT ONLY (openapi/origin-connector.yaml + asyncapi/integration-hub.yaml + OriginEvent schema)
  + a `tools/seed` Tenant-Zero connection. LIVE Famit wiring = a LATER flag-gated dormant-safe Famit-side unit (orchestrator-owned);
  the live earner is NEVER touched in Phase 0.

## REUSE MAP (Tenant Zero — verified from memory/brain/*)
- whatsapp = adapter over live `whatsapp.py`+`whatsapp_builder/` (FEATURE_WHATSAPP=1 live, real META_WA_TOKEN).
- voice-adapter = wraps LiveKit/Vobiz `agent.py` + caller.py `/run`+`_classify_outcome`.
- creative-studio gen-bg = **AI Asset Service :8310** (OpenRouter gemini-2.5-flash-image, wallet-metered, DO Spaces).
- ai-manager = extends live AIM (Test Console, firewall PIN, `creative.*` ToolSpecs); commands → SAME ActionPlan path (§17.3).
- Money model to MIRROR (own copy, own PG/RLS — P2 no cross-DB reads): wallet.py (paise, idem_key=exactly-once),
  firewall.py (PIN+HS256 step-up sub-bound TTL300), immutable PG `events` audit.

## CONTRACTS INVENTORY Phase 0 must produce (P1 — code forbidden before contract)
- `/contracts/schemas/`: event-envelope + 15 core events (campaign.requested, research.completed, strategy.compiled,
  campaign.compiled, campaign.launched, creative.generated, creative.qa.passed, action.plan.signed, lead.captured,
  lead.scored, call.completed, call.outcome, wa.message.sent/received, signal.dispatched, optimization.decision)
  + 3 frozen artifacts (CIB §9.3, MediaPlan §9.9, ActionPlan+Explanation §7.4/P5).
- `/contracts/openapi/`: core.yaml + origin-connector.yaml.  `/contracts/asyncapi/`: integration-hub, ledger, core-bus.
- `/contracts/registry/`: index.json + drift-snapshot.json (the CI contract-drift mechanism = Phase 0 acceptance).

## ✅ EVENT BACKBONE DELIVERED (2026-06-11) — `contracts/schemas/` + `contracts/asyncapi/bus.yaml`
- **Envelope** `event-envelope.schema.json` (JSON Schema 2020-12, `$id` base `https://contracts.growth-os.dev/schemas/`):
  event_id (uuidv7, regex-pinned `-7xxx-[89ab]`), type (lowercase `plane.entity.verb`-ish dotted), version (semver),
  occurred_at, tenant_id, workspace_id, correlation_id (journey), causation_id (nullable), actor{kind∈agent|user|system|webhook,id},
  idempotency_key, payload (open obj — narrowed per-type), +optional `trace{traceparent}` (P10). `additionalProperties:false`.
  Mandatory tenant_id/workspace_id = P6. FROZEN-AFTER-MERGE.
- **15 core event payload schemas** (task list, all written): campaign.requested, research.completed, strategy.compiled,
  campaign.compiled, campaign.launched, creative.generated, **creative.qa.evaluated** (verdict passed|fix_suggested|block —
  the spec's `creative.qa.passed` expressed as a verdict so ONE event type covers pass/fix/block, extend-never-mutate §6.2),
  action.plan.created, action.plan.signed, action.executed (result executed|failed|rolled_back doubles for failed/rolled_back),
  ad.metrics.snapshot, lead.captured, lead.scored, signal.dispatched, optimization.decision. **+4 engagement core** (Origin
  Connector domain, additive): call.completed, call.outcome, wa.message.sent, wa.message.received (CTWA `referral.ctwa_clid`).
  = **20 schema files mine**. Money everywhere = INR **paise** integers (mirrors live wallet). Appendix-A shapes are canonical
  (lead.scored score:78/tier/reasons/model/features_ref; signal.dispatched event_id=hash(journey+step)/match_keys/value/INR;
  optimization.decision scope/platform_ref/decision/rule/explanation{summary_en,summary_hi,evidence[],undo_plan}/action_plan_id).
- **Each event schema carries `x-event-type` + `x-topic` + `x-contract-version`** so the topic map + registry generate from the
  files (no hand-maintained drift). Topic map (`plane.entity.verb`): campaign.lifecycle.{requested,compiled,launched},
  campaign.research.completed, campaign.strategy.compiled, creative.creative.generated, creative.qa.evaluated,
  activation.action_plan.{created,signed,executed}, metrics.ad.snapshot, metrics.optimization.decision,
  data.lead.{captured,scored}, signals.signal.dispatched, engagement.{call.completed,call.outcome,wa.message.sent,wa.message.received}.
- **`contracts/asyncapi/bus.yaml`** = AsyncAPI 3.0.0; **19 channels = 19 operations(all `send`) = 19 messages**; every message =
  envelope `allOf` with `type:{const}` + `payload:$ref` to the event schema (ONE envelope def, no drift); Redpanda servers
  (dev localhost:9092 + prod var). Consumers (`receive`) live in each service's own asyncapi doc — bus.yaml is the canonical
  PRODUCER + topic map.
- **VALIDATED locally** (Node22, ajv 2020 + ajv-formats + js-yaml in a scratch dir, now removed): all **25** schema files
  (my 20 + sibling agent's 5 artifacts CIB/MediaPlan/ActionPlan/explanation/creative_dna) meta-validate against 2020-12 and
  cross-$ref-resolve cleanly (no $id collision — sibling used same `$id` base, good coordination). Positive+negative instance
  tests pass: missing tenant_id / bad uuid / bad type-pattern / extra-prop / score>100 / bad enum all REJECT. bus.yaml parses,
  is AsyncAPI 3.0.0, all channel addresses match `plane.entity.verb`. registry topics == bus topics (consistent).
- **`contracts/registry/event-backbone.{index,drift-snapshot}.json`** = MY group only (scoped, not the global index — avoid
  clobbering sibling registry work); sha256 over LF-normalized bytes = the CI drift mechanism. A top-level `index.json` should
  MERGE the per-group fragments later.
- LEARNING: ajv rejects adding+compiling the same `$id` twice ("already exists") — register once via addSchema, then resolve
  with `getSchema($id)`, don't re-`compile`. Use `strict:false, allowUnionTypes:true` for 2020-12 docs with `x-` keywords.

## PROD reuse-vs-new (box note)
NEW: Postgres(own, RLS) · Temporal · Redpanda · ClickHouse · Redis. REUSE: DO Spaces (object store), OpenRouter/Groq
LLM keys (via gateway P8), AI-Asset/voice/WhatsApp (via Origin Connector). DO droplets 3/3 full → prod = limit-raise/new box
OR managed (Postgres+ClickHouse+Kafka-API+Temporal Cloud dodge the droplet wall). GROWTH OS talks to live Famit ONLY over
the Origin Connector HTTP surface.

## CONTRACTS — OpenAPI Phase-0 core (DONE, 2026-06-11)
- 6 OpenAPI 3.1 specs written under `contracts/openapi/`, ONE per core surface (cleaner
  bounded-context split than the doc's single core.yaml): `gateway.yaml` (BFF/auth-stub/
  tenant-resolution + SSE feed + dev-token mint), `tenants.yaml` (orgs/workspaces/members/
  roles/invites/entitlements + `GET /me/permissions`), `integration-hub.yaml` (connections+
  oauth-start/test + the ★Origin Connector PUSH `/v1/origin/events`+`/webhook/{kind}` & PULL
  `/campaigns|reports|leads|signals`), `ledger.yaml` (§7.4 Action Ledger: POST /actions,
  /{id}/sign, GET /actions?journey=, +/verify chain integrity), `flags.yaml` (per-tenant
  policy-config: autopilot per action-class, thresholds, budget caps, kill-rule multipliers,
  versioned), `notify.yaml` (channels/templates/send/preferences quiet-hours).
- Shared primitives in `contracts/openapi/_shared/common.yaml` (Error envelope, Page cursor,
  securitySchemes `bearerUserJwt`(D5 dev stub) + `serviceToken`(origin, Bearer), reusable
  4xx/429 responses, headers). Every surface `$ref`s it — one source of truth for errors/auth.
- LEDGER ENTRY = the frozen artifact itself: ledger.yaml responses `$ref`
  `../schemas/action_plan.schema.json` DIRECTLY (it owns status/signatures[]/approval/step_up/
  budget_impact+governor_stamp/ledger.prev_hash/hash). Did NOT re-model the entry (would drift).
  Only API-layer DTOs kept: `ProposeActionRequest{plan}` + `SignActionRequest{expected_hash,
  step_up_token,confirm_money,note}`. Sign body's step_up mirrors live firewall.py.
- ORIGIN auth contract enforced in-spec: PUSH/PULL use `serviceToken` (Bearer); tenant from
  TOKEN not body (P6); `Idempotency-Key` REQUIRED on PUSH; reused-key-different-body => 409
  (the negative control). PULL daily report stamps `source: metrics_layer` (P10, numbers only).
- `OriginEvent` wire shape defined INLINE in integration-hub.yaml (schemas role hadn't landed
  `origin_event.schema.json` at write time) — origin_type enum = the §3.4 map; correlation_hint
  {phone,ctwa_clid,fbclid,gclid,wamid,lead_id}; tenant_id NEVER in body. KEEP IN SYNC if schemas
  role later adds origin_event.schema.json.
- VALIDATION: all 6 pass `redocly lint` (valid, 0 errors; only stylistic warnings — license/
  tag-desc, and oauthCallback 302-only by design). External `$ref` to action_plan.schema.json
  proven to fully deref via `redocly bundle`. GOTCHA: inline-flow YAML `description:` values
  containing `:`/`,` (e.g. "CPqL = spend/qualified_leads (NORTH STAR, §8.5)") MUST be quoted or
  the flow-map parse breaks. Node 22.11 < redocly's wanted 22.12 (warning only, runs fine).
  Run lint via `pnpm --package=@redocly/cli dlx redocly lint` (plain dlx errors: multiple bins).

## GOTCHAS carried from the live platform (don't re-derive)
- OpenRouter env var = founder typo **`OPNEROUTER_API_KEY`** (fallback to OPENROUTER_API_KEY).
- Live caller uses `X-Auth: <token>` header; the clean Origin Connector uses `Authorization: Bearer`.
- `/run` + `/suppression` take **Form fields not JSON** (JSON silently ignored).
- Box Python 3.12 (NOT local 3.14); wallet reserve()->hold_id|None, release() takes NO amount, settle(hold_id,actual).

## ✅ MONOREPO SCAFFOLD DELIVERED (2026-06-11) — Phase 0, §20
- Full Turborepo+pnpm(TS)/uv(Py) tree at `growth-os/`. Root dotfiles (.editorconfig/.gitignore/
  .npmrc/.nvmrc/.prettier*/eslint.config.mjs flat/README/pyproject.toml uv-workspace-root). 9 pnpm
  workspace projects. Skeleton: 6 packages, 35 service dirs (all §20 except core; README placeholders
  via idempotent `tools/scaffold/make-placeholders.mjs`), 8 agents (uv members: pyproject +
  src/growth_os_<name>/__init__.py), 2 apps, infra/, evals/, tools/.
- **PARTITION (two parallel sessions in ONE monorepo):** a `services/core` session OWNS
  `packages/{events,auth,config,otel}`, `services/core`, and core codegen
  `tools/codegen/{lib,validate-schemas,build-registry,generate-types}.mjs`. The scaffold session OWNS
  `packages/{sdk,metering,ui}`, ALL other service/agent/app dirs, infra, evals, CI, and codegen
  `tools/codegen/{generate-sdk,generate}.mjs`. Disjoint, no clobbering. RECONCILE ON DISK each turn —
  files appeared/changed under me mid-task (auth/config/otel landed late; lockfile went stale when
  core added `packages/otel`). A plain `pnpm install` reconciles; the last session to touch the
  lockfile must re-run install so CI `--frozen-lockfile` passes.
- **codegen pipeline (P1):** `pnpm codegen` -> generate-types (JSON Schemas -> @growth-os/events) +
  generate-sdk (OpenAPI 3.1 -> @growth-os/sdk/src/generated, via `openapi-typescript` v7
  default(url)->AST then `astToString`, namespaced re-export per surface to avoid paths/components
  collisions). Generated code COMMITTED; CI re-runs codegen + `git diff --quiet` on generated dirs =
  the "types can't silently lag schemas" gate, alongside the sha256 `contracts:drift` gate.
- **CI (.github/workflows/ci.yml, working-directory: growth-os):** jobs = contracts(validate+drift+
  codegen-fresh+redocly lint), typescript(turbo lint+typecheck+test), python(uv ruff+mypy). Verified
  locally: contracts:validate (25 schemas, 6/6 neg controls), contracts:drift (clean), codegen (24
  types + 6 SDK modules, idempotent), eslint root 0/0, my 3 packages typecheck clean, redocly valid.
- **infra/docker-compose.dev.yml** (pinned: postgres:16.4 / redpanda:v24.2.7 + console / redis:7.4 /
  clickhouse:24.8 / temporalio auto-setup:1.25.1 + ui:2.31.2 / minio). Port gotcha: ClickHouse-native
  takes host 9000, so MinIO S3 mapped to host 9002. Temporal reuses the same Postgres (auto-setup
  makes temporal/temporal_visibility DBs). NOT booted (laptop+droplets) — box/managed required.
- LEARNING: json-schema-to-typescript IGNORES the `typeName` arg when the schema has a `title` — it
  names the interface from `title`. The core agent's generate-types.mjs hit this (catalog imports
  `<Name>Payload`, payloads export `<Name>` from title) + duplicate `Explanation`/`CreativeDNA` from
  shared $refs -> `@growth-os/events` build BREAKS. Fix in generate-types.mjs (core agent's file):
  strip/override `title` before compile (or align the export suffix) + dedupe externally-referenced
  shared types. Reported to orchestrator; not fixed by scaffold session (domain boundary).
- LEARNING: `pnpm-workspace.yaml` already globs services/agents/apps/tools/* — so adding agent
  pyprojects doesn't pull them into the PNPM graph (no package.json there), only the uv workspace
  (`pyproject.toml [tool.uv.workspace] members=["agents/*"]`). Clean TS/Py separation by file type.

## ✅ CORE MODULAR APP SCAFFOLDED (2026-06-11) — `services/core` (D1) + packages events/auth/config
- **services/core** = ONE NestJS(Fastify) app, modules gateway+tenants+flags+ledger+notify+billing-stub,
  base path `/v1` (matches OpenAPI servers). Each controller maps 1:1 to its committed OpenAPI surface.
  TYPECHECK GREEN (full workspace `pnpm typecheck` = 14/14). 28 tests pass (events 6, core 16, auth 2, config 4).
- **★ Hash-chain ledger** (`src/modules/ledger/hash-chain.ts`, PURE/no-IO): per-tenant append-only chain,
  `hash(n)=sha256(prev_hash || "\n" || canonical(plan_n))`, genesis prev_hash = 64 zeros. **Canonicalize =
  recursively SORT object keys, PRESERVE array order, EXCLUDE top-level {ledger,signatures}** so the
  proposed→signed status flip + signature appends never invalidate the hash. NOTE: `status` IS in the hashed
  bytes; the verifier recomputes with status pinned to 'proposed' (`rehashView`). `verifyChain()` detects
  content tampering AND broken prev_hash links (both tested). 9 hash-chain + 7 ledger-service tests green.
- **Ledger entry = the frozen artifact**: the stored `plan` jsonb IS `action_plan.schema.json` (+ `ledger`
  linkage attached, excluded from hash). `propose()` validates the FULL plan against the committed schema
  via `ContractValidator` BEFORE persisting (P1) — the ledger-service test asserts the RETURNED entry
  conforms (drift = test failure). Sign enforces action:sign RBAC + step-up token + governor stamp +
  confirm_money for spend/destructive plans (P4); proposed→signed is the ONLY mutation (DB trigger + service).
- **RLS migration** `src/db/migrations/0001_init.sql`: every business table ENABLE + FORCE RLS, policy
  `tenant_id = core.current_tenant()` where `current_tenant()` reads GUC `app.current_tenant` (NULL→no rows,
  fail-closed). `DbService.withTenant(tenantId, fn)` opens a txn + `set_config('app.current_tenant',…,true)`
  (txn-local, never leaks across pooled conns). Tenant ALWAYS from token (P6); ledger immutability =
  BEFORE UPDATE/DELETE trigger allowing only proposed→signed + locking chain/identity cols.
- **packages/auth** = OIDC-shaped `TokenVerifier` iface + `DevJwtVerifier` (HS256 dev stub, D5) +
  `mintDevToken`; tenant/workspace/role from token CLAIMS. **packages/config** = zod env loader with derived
  `isProd/devTokenEnabled(off in prod)/dbEnabled(needs DATABASE_URL)/busInMemory(no KAFKA_BROKERS)`.
  **packages/events** completed (sibling left envelope.ts only): added topics.ts (19-event type→topic map
  matching registry), validator.ts (ajv2020 loads committed schemas), create-envelope.ts (uuidv7+OTel
  traceparent), bus.ts (InMemoryEventBus dev + KafkaEventBus box, validates before publish), index.ts.
  Sibling/linter later added idempotency.ts + OffContractEventError/assertOnContract (exported from index).
- **GOTCHA (carried)**: ajv `import Ajv2020 from 'ajv/dist/2020.js'` (default) → "no construct signatures"
  under NodeNext+esModuleInterop. FIX = NAMED import `{ Ajv2020 }`, type via `InstanceType<typeof Ajv2020>`,
  and normalize addFormats: `((x as {default?}).default ?? x) as FormatsPlugin`. Hit in core/contract-validator
  AND events/validator. Also: bare `import 'fastify'` types need `fastify` as a DIRECT dep of services/core
  (it's only transitive via @nestjs/platform-fastify; TS won't resolve it otherwise). pg bigint → string.
- **Laptop vs box (D8)**: app BOOTS in degraded no-db/in-memory-bus mode for the contract surface; DB-backed
  paths + the publish→consume→ledger demo need real Postgres+Redpanda (compose, box/CI). `pnpm --filter
  @growth-os/core migrate` applies the DDL+RLS. Documented in services/core/README.md + .env.example.
  Empty sibling packages (temporal-worker/demo-phase0/sdk) fail `vitest run` ("no test files"→exit 1) — my
  packages use `--passWithNoTests` or have real tests; those 3 are sibling-owned (not fixed here).

## ✅ PHASE-0 RAILS DELIVERED (2026-06-11) — events runtime + OTel + Temporal HelloSaga + demo + drift test
- **packages/otel** (NEW, mine): `tracing.ts` NodeTracerProvider + ConsoleSpanExporter (dev) / OTLP (box);
  `spans.ts` `withSpan`/`injectTraceContext`/`extractTraceContext`/`continueFromEnvelope`. The bus carries
  W3C traceparent in `envelope.trace`; consumer `continueFromEnvelope` makes the consume span a CHILD of the
  publish span → ONE trace spans the bus hop (proven: same traceId, consume.parentId=publish.span). 4 tests pass.
  OTel **1.30.1** API: `new Resource({...})` (NOT `resourceFromAttributes` — that's 2.x); `NodeTracerProvider({resource, spanProcessors:[...]})`
  ctor option works (also `addSpanProcessor`); attrs from `@opentelemetry/semantic-conventions` `ATTR_SERVICE_NAME/VERSION`.
- **services/temporal-worker** (NEW, mine): HelloSaga workflow (`workflows.ts`, deterministic, proxyActivities) with a
  COMPENSATION/rollback step (the §10.2 LaunchSaga pattern); `activities.ts` emit `campaign.requested` + compensating
  `optimization.decision` onto the bus (durable workflow drives the event backbone); `worker.ts`+`trigger-hello.ts`
  (`GROWTH_OS_SAGA_FAIL=1` exercises rollback). @temporalio **1.11.6**. Box-required to RUN (needs temporal:7233);
  typecheck + 3 activity tests pass on the laptop. Worker uses `Worker.create({connection,namespace,taskQueue,workflowsPath,activities})`
  + `NativeConnection.connect`; client uses `Connection.connect`+`new Client`+`client.workflow.start<typeof WF>('HelloSaga',...)`.
- **tools/demo-phase0** (mine, REPLACED the sibling stub that said "owned by core"): `run.ts` + `ledger.ts`
  (`HashChainedLedger` prev_hash→hash, `verify()`, tamper negative-control). DEMO RUNS ON LAPTOP (in-memory bus, no Docker):
  publish campaign.requested → consume → ledger seq0 → publish lead.captured → ledger seq1 (chained) → trace printed →
  tamper detected. Exits non-zero on failure ⇒ its `test` script IS the demo (a CI acceptance test). Acceptance: PASS.
- **Contract-drift test** (`tools/codegen/drift.test.mjs`, 3 cases): (1) live repo matches snapshot, (2) logic: editing a
  schema changes its sha256, (3) CLI end-to-end: copy contracts+lib.mjs+build-registry.mjs to a TEMP dir, edit a schema
  on disk, `--check` exits NON-ZERO + reports `DRIFT in lead.scored`. Windows gotcha: `cpSync` of the whole codegen dir
  hits EPERM on pnpm's symlinked node_modules → copy ONLY lib.mjs + build-registry.mjs (no ajv needed by the checker).
- **Registry snapshot now covers ALL 25 frozen schemas** (was 20 event-backbone only; added the 5 artifacts
  CIB/MediaPlan/ActionPlan/explanation/creative_dna — all frozen-after-merge D7). Format kept = established
  `{schemas:{name:{version,sha256}}}` map (didn't break the sibling's convention). My LF-normalized hasher reproduced all
  20 pre-existing sha256 exactly (cross-OS stable confirmed). `pnpm contracts:drift` passes.
- **FIXED a real typecheck bug in the sibling's events/validator.ts**: ajv 2020 ESM-interop — `import Ajv2020 from 'ajv/dist/2020.js'`
  default = namespace (not constructable). FIX: `import { Ajv2020, type ValidateFunction } from 'ajv/dist/2020.js'` (NAMED export
  is the class, usable as type+value) + `import addFormatsImport, { type FormatsPlugin } from 'ajv-formats'` then cast
  `(addFormatsImport.default ?? addFormatsImport) as FormatsPlugin`. Added `OffContractEventError`+`assertOnContract`
  (strict unknown-type rejection for the bus boundary — "rejects off-contract events").
- **generate-types.mjs** (mine, wired into the sibling's `generate.mjs` umbrella): single-pass compile via a synthetic
  root that `$ref`s every schema → json-schema-to-typescript emits each shared sub-type (Explanation, CreativeDNA) ONCE
  (no duplicate-interface redeclare). Interface names come from the schema `title` (PascalCased), NOT my passed name+`Payload`.
  Catalog exports the typed-payload layer (`PayloadByType`,`TypedEnvelope`,`AnyEvent`,`EVENT_CATALOG`) — complements (does
  not duplicate) the sibling's hand-maintained `topics.ts` (which stays the runtime topic/version registry; its `EventType`
  is the canonical one — catalog's `EventType` NOT re-exported to avoid a clash).
- **FULL WORKSPACE GREEN**: typecheck 14/14, `pnpm test` 15/15 (incl sibling core + the demo), contracts:validate (25 schemas
  + 6 negative controls) + contracts:drift pass, lint clean. Empty-test-script gotcha: `vitest run` with no test files exits 1
  → the demo package's `test` runs the demo instead (self-asserting).
- PARALLEL-SESSION DISCIPLINE: the sibling owns packages/events core + services/core + infra + CI + codegen umbrella;
  I own packages/otel + services/temporal-worker + tools/demo-phase0 + the drift test + the registry/validator fixes.
  Reconciled by reading-before-writing every shared file (index.ts/validator.ts mutated mid-session by the sibling — re-read + additive edits only).
