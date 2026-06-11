# GROWTH OS — Phase 0 / Phase 1 Build Architecture

> Status: **Phase 0 design (this doc) → Phase 0 build**. Authoritative companion to
> `GROWTH-OS-BUILD-SPEC.md` (the bible; §2 P1–P12 are LAW). This doc fixes the four
> things Phase 0 must nail before any service code: (1) the monorepo layout + which
> deployables exist in Phase 0–1, (2) the **Origin Platform Connector** contract that
> reuses the LIVE Famit platform as Tenant Zero, (3) the infra/deploy plan, and (4) the
> exact contracts inventory Phase 0 ships.
>
> Scope discipline (P-phase): this doc plans Phase 0 + the Phase-1 boundary it must not
> violate. **Do not build Phase 1+ services.** Phase 0 = skeleton, rails, contracts, the
> modular core app, bus + Temporal + OTel + CI. Contracts-first (P1): no service code
> before its contract exists in `/contracts`.

---

## 0. Decisions locked for Phase 0 (read first)

| # | Decision | Rationale (spec ref) |
|---|----------|----------------------|
| D1 | **One modular NestJS app = `core`** bundling gateway+tenants+integration-hub+ledger+flags+notify+billing-stub as internal modules, not 7 deploys. | §20 "core … as ONE modular NestJS app"; P12 boring tech; bounded contexts now, extract later. |
| D2 | **Temporal** is the durable-workflow engine for GROWTH OS (NOT Hatchet). | §4 decided; §7.8. Hatchet (`memory/brain/orchestration-hatchet.md`) stays the **Famit-side** spine (F3) — it orchestrates the live caller.py flows that *feed* the Origin Connector. GROWTH OS owns its own Temporal. They meet only at the event envelope, never share a workflow engine. |
| D3 | **Redpanda** (Kafka API) is the event bus + a JSON-Schema registry. Famit/Hatchet stay on Postgres-broker; the bridge is the Origin Connector's HTTP+webhook door, not a shared Kafka topic. | §4, §6, P2. Keeps the live earner decoupled from a new bus. |
| D4 | **Origin Connector = a provider inside `integration-hub`** (`provider: origin`), with its own inbound REST + webhook + report-pull surface, NOT a separate deployable. | §7.3 "Origin Platform Connector = first-class provider `origin`". |
| D5 | **Auth in Phase 0 = a stub** (dev JWT mint + a fixed tenant) behind the same `packages/auth` interface that Phase 3 swaps for OIDC (Logto is already live for Famit; reuse later, not now). | §21 Phase 0 "auth stub"; P12 buy-don't-build auth. |
| D6 | **Money/spend = STRUCTURALLY impossible in Phase 0.** No connector mutation path exists yet; the only "spend-shaped" object is the Ledger entry + ActionPlan contract. Real spend arrives Phase 1 behind Budget Governor + signed ActionPlan (P4). | P4; §21 phase split. |
| D7 | Envelope, 15 core event schemas, CIB, MediaPlan, ActionPlan are **frozen-after-merge** JSON Schemas; CI fails on drift. | P1; §6.2; Appendix B. |
| D8 | Local toolchain present (Node 22 / pnpm 10 / uv 0.11 / Docker 29) → typecheck + lint + JSON-Schema-validate + contract-drift test **run here**. Full compose stack (postgres/redpanda/clickhouse/temporal/redis/minio) is written as files and **documented as box-required to actually boot** (this Windows laptop may not run all six; DO droplets 3/3 full → prod needs a box). | Orchestrator HONEST ENV NOTE. |

---

## 1. Monorepo layout (Phase 0–1 deployables)

Per §20. The repo holds the full ~30-service skeleton as **directories with contracts**,
but only the Phase 0–1 **deployables** get code. Everything else is a stub dir + its
contract placeholder so the bounded-context split lines are visible from day one.

```
growth-os/
  CLAUDE.md
  GROWTH-OS-BUILD-SPEC.md
  package.json                 # pnpm + turbo root
  pnpm-workspace.yaml          # packages/* services/* agents/* apps/* contracts tools evals
  turbo.json
  tsconfig.base.json
  .github/workflows/ci.yml     # lint · typecheck · contract-drift · schema-validate · unit
  docs/
    architecture-phase0.md     # THIS FILE
  contracts/                   # §1 of the contracts inventory below — the SOURCE OF TRUTH (P1)
    openapi/                   # one .yaml per sync surface (REST)
    asyncapi/                  # one .yaml per event-producing service
    schemas/                   # JSON Schema 2020-12: envelope, 15 events, CIB, MediaPlan, ActionPlan
    registry/                  # generated index + drift snapshot the CI diffs against
  packages/                    # shared libs (built Phase 0)
    events/                    # ★ typed event envelope + codegen'd TS types from /contracts/schemas
    sdk/                       #   internal HTTP client (typed, from openapi) — stub Phase 0
    auth/                      # ★ auth interface + DEV stub (D5); OIDC impl deferred to Phase 3
    metering/                  #   credit.consumed emitter helper — interface Phase 0
    config/                    # ★ env + feature-flag loader (typed, zod-validated)
    ui/                        #   shadcn shell — Phase 1 (dashboard)
  services/
    core/                      # ★ PHASE 0 DEPLOY — modular NestJS (Fastify) app (D1)
      src/modules/
        gateway/               #   edge auth(stub), tenant resolution, trace IDs, BFF, SSE feed
        tenants/               #   orgs/workspaces/members/roles; GET /me/permissions
        integration-hub/       #   connections, token-vault(stub), webhook-registry,
          providers/origin/    #   ★ ORIGIN PLATFORM CONNECTOR (D4, §3 below)
        ledger/                #   hash-chained actions (prev_hash); POST /actions, /sign
        flags/                 #   per-tenant autopilot/thresholds/caps; changes = events
        notify/                #   console sink Phase 0 (in-app/email/WA later)
        billing/               #   STUB Phase 0 (credit.consumed sink); live Phase 3
    # ---- below = Phase 1+ deployables: DIRS + CONTRACTS exist Phase 0, CODE later ----
    ingestion/  tracking/  identity/  signals/                 # data (Phase 1)
    campaign-compiler/  executor/  connector-meta/             # activation (Phase 1)
    budget-governor/  optimizer/                                # activation (Phase 1)
    creative-studio/  creative-qa/  dam/                        # creative (Phase 1)
    warehouse-api/  attribution/  benchmarks/                   # data (Phase 2+)
    connector-google/  audiences/  experiments/  compliance-engine/
    brand-kit/  video-studio/  copy/  landing-pages/  catalog/
    whatsapp/  voice-adapter/  journeys/  crm-sync/             # ENGAGEMENT = adapters over LIVE Famit
    approval-inbox/  ai-manager/  narrative-reports/  public-api/
  agents/                      # Python / FastAPI + uv workspace
    llm-gateway/  agent-orchestrator/  knowledge/  lead-scoring/   # agents-core (Phase 1)
    insight-miner/  memory/  forecast/  strategy-compiler/
  apps/
    dashboard/                 # Next.js — Phase 1 (minimal connect→wizard→feed→approvals→report)
    lp-runtime/                # landing-page SSR — Phase 2
  infra/
    docker-compose.dev.yml     # ★ postgres redpanda redis clickhouse temporal minio (D8)
    temporal/  redpanda/  clickhouse/   # init configs
    terraform/  helm/          # prod IaC — Phase 4
  evals/                       # golden CIB requests etc — Phase 2
  tools/
    codegen/                   # JSON-Schema → TS types (events pkg) + openapi → sdk client
    seed/                      # dev tenant + Tenant-Zero (Famit) connection seed
    sandbox-fixtures/          # Meta/Google sandbox golden payloads — Phase 1
```

**Phase 0 deployables (what actually runs):** `core` (modular NestJS), `infra/docker-compose.dev.yml`
stack, a Temporal `HelloSaga` worker, and the demo publisher/consumer that proves the
loop. **Phase 1 adds** (separate sessions, per §21): data (ingestion+tracking+identity+signals),
activation (compiler+executor+connector-meta+governor+optimizer), creative
(studio+qa+dam), agents-core (gateway+orchestrator+knowledge+scoring), dashboard.

**The "6 Phase 0–1 deploy bundles"** named in §20, mapped to dirs:
`core` = services/core · `data` = ingestion+tracking+identity+signals ·
`activation` = campaign-compiler+executor+connector-meta+budget-governor+optimizer ·
`creative` = creative-studio+creative-qa+dam · `agents-core` =
agents/{llm-gateway,agent-orchestrator,knowledge,lead-scoring} · `dashboard` = apps/dashboard.

---

## 2. Reuse map — the LIVE Famit platform as Tenant Zero

GROWTH OS does **not** rebuild voice / WhatsApp / AI-Manager / creative generation. It
wraps them. Grounded in the live system (verified via `memory/brain/*`):

| GROWTH OS plane | LIVE Famit asset (reuse, don't rebuild) | How it connects |
|---|---|---|
| `whatsapp` service | live `whatsapp.py` send path + `whatsapp_builder/` module (`/whatsapp/campaign/*`, `FEATURE_WHATSAPP=1` live, real `META_WA_TOKEN`) | **adapter** — same contract; emits `wa.message.*` via Origin Connector |
| `voice-adapter` | live LiveKit/Vobiz `agent.py` + caller.py `/run` dial loop + `_classify_outcome` | **wraps** — outbound trigger in, `call.completed`+`call.outcome` out via Origin Connector |
| `creative-studio` gen-background | **AI Asset Service** `127.0.0.1:8310` (`/generate`, OpenRouter `gemini-2.5-flash-image`, wallet-metered, DO Spaces) | direct call for the gen step; AssetRef registered in DAM. Asset svc is already a dedicated service mirroring the AIM blueprint. |
| `ai-manager` | live AI Manager (`ai_manager/` in caller.py, Test Console, firewall PIN, 35-route surface, `creative.*` ToolSpecs) | **extends** — AIM commands map to the SAME ActionPlan path (§17.3). AIM already routes `campaign.requested`-shaped intents. |
| `approval-inbox` | live WhatsApp interactive buttons + AIM firewall step-up | WA Approve/Reject as a `notify` channel + Temporal signal |
| Origin Connector (NEW seam) | caller.py campaigns/leads/calls/wa data | **the bridge** — §3 below |

**Money & safety primitives already live (reuse as the model, run GROWTH OS's own copy):**
wallet.py (INTEGER paise, `reserve(tenant_id,amount_minor,resource_type,resource_id,idem_key)->hold_id`,
no-double-spend proven), firewall.py (PIN + HS256 step-up, sub-bound), immutable audit
(PG `events` leg). GROWTH OS's Ledger + Budget Governor mirror this discipline (P4/P5),
but on its own Postgres/RLS — no cross-service DB reads (P2).

---

## 3. ★ THE ORIGIN PLATFORM CONNECTOR CONTRACT

The single bridge that lets the **standalone** GROWTH OS reuse the live Famit platform as
Tenant Zero — and stay sellable to *other* origin platforms later. It is a `provider:origin`
inside `integration-hub` (D4). Two directions:

- **PUSH (Famit → GROWTH OS):** Famit posts canonical business facts to one hardened
  inbound endpoint; the connector verifies → normalizes to the §6.1 envelope → publishes
  to the bus. Never inline; always via the bus (P2).
- **PULL (Famit ← GROWTH OS):** Famit reads campaign/lead/report state via the public API
  surface (a read projection), so the live panel can show GROWTH OS results.

### 3.1 Auth model (service token)

- Famit authenticates to GROWTH OS with a **per-connection service token**
  (`ORIGIN_SERVICE_TOKEN`, opaque, stored in `integration-hub` connections table,
  envelope-encrypted; mirrors the live `AIASSET_SERVICE_TOKEN` / `AIM_SERVICE_TOKEN`
  pattern). Sent as `Authorization: Bearer <token>` (NOT the panel's `X-Auth` header —
  that's the live-panel convention; the connector is a clean Bearer surface).
- Token → resolves a **single `connection`** → which pins **`tenant_id` + `workspace_id`**
  GROWTH-OS-side. **Tenant is derived from the TOKEN, never from the request body**
  (the load-bearing isolation rule the live AIM/asset services already enforce; negative
  control = a body `tenant_id` must NOT be able to forge another tenant). P6.
- **Idempotency:** every push carries `Idempotency-Key` (Famit's source event id). The
  connector dedups on `(connection_id, idempotency_key)` → exactly-once envelope emit (P3).
- **Webhook integrity (reverse, GROWTH OS → Famit):** signed with an HMAC-SHA256
  `X-GrowthOS-Signature` over the body using a per-connection secret (same shape as the
  live WABA/Meta webhook verification). Famit verifies before acting. Fail-closed.
- **Rate/abuse:** the connector sits behind gateway's per-app + per-connection token-bucket
  (§5.3 governor) so a noisy origin can't starve the bus.

### 3.2 PUSH endpoint (inbound REST)

```
POST /v1/origin/events          # the ONE inbound door (batch-capable)
  Authorization: Bearer <ORIGIN_SERVICE_TOKEN>
  Idempotency-Key: <famit_source_event_id>
  body: { events: [ <OriginEvent>, ... ] }       # 1..N, all same connection/tenant

POST /v1/origin/webhook/{kind}  # provider-style webhook variant (Famit can push raw, we normalize)
  kind ∈ { call, wa, lead, campaign }
```

`OriginEvent` (the wire shape Famit sends — deliberately small; the connector maps it to
the full §6.1 envelope so Famit never has to know GROWTH OS internals):

```jsonc
{
  "origin_type": "call.completed",        // see map §3.4
  "origin_ref":  "c17e55e9f3:+9199...",   // Famit's own id (campaign_id:phone / wamid / lead_id)
  "occurred_at": "2026-06-11T08:15:02Z",
  "correlation_hint": { "phone": "+9199...", "wamid": "...", "lead_id": "...", "ctwa_clid": "..." },
  "payload": { /* origin-native fields, normalized in §3.4 */ }
}
```

### 3.3 PULL surface (reports & state back to Famit)

```
GET  /v1/origin/campaigns/{ref}           # GROWTH-OS campaign + media-plan + live status
GET  /v1/origin/reports/daily?date=...     # the metrics-layer daily brief (CPL/CPqL/spend) for the panel
GET  /v1/origin/leads/{ref}/score          # lead.scored result (so the panel shows quality)
GET  /v1/origin/signals/health             # the Signal Health card (EMQ/dedup/latency) §11
  Authorization: Bearer <ORIGIN_SERVICE_TOKEN>   # same token, read scope
```

All reads are RLS-scoped to the token's tenant and served from the metrics layer / read
projections only — never ad-hoc numbers (P10, §8.5).

### 3.4 ★ ORIGIN EVENT MAP (the deliverable)

Mapping **existing Famit data → the GROWTH OS canonical event** (§6.1 envelope; topic
`plane.entity.verb`; extend-never-mutate §6.2). The connector mints `correlation_id` from
the journey rule (§6.3): E.164 phone is king in India; `ctwa_clid`/`fbclid` next.

| Famit source (live) | `origin_type` | → GROWTH OS canonical event (topic) | Key field mapping |
|---|---|---|---|
| caller.py `/campaigns` create + `/run` start | `campaign.requested` | `campaign.requested` (campaign.lifecycle.requested) | famit `campaign_id`→`origin_ref`; leads CSV count→`payload.audience_size`; objective default `leads` |
| caller.py dial loop finishes a call (`_classify_outcome`) | `call.completed` | `call.completed` (engagement.call.completed) | `phone`→correlation key; `duration`,`status`(answered/no-answer/suppressed)→payload; transcript ref |
| AIM/agent post-call intent extraction | `call.outcome` | `call.outcome` (engagement.call.outcome) | `answered`,`duration`,`intents[]`(budget_mentioned/timeline/booking),`qualification`,`booking`→payload (feeds lead-scoring §9.5 & signals §11) |
| `whatsapp.py` send (`/whatsapp/send`, template/free-form) | `wa.message.sent` | `wa.message.sent` (engagement.wa.message.sent) | `wamid`→`origin_ref`; `to`(phone)→correlation; `template`/`category`→payload (cost meter) |
| `/whatsapp/inbound` webhook (incl CTWA referral) | `wa.message.received` | `wa.message.received` (engagement.wa.message.received) | inbound `wamid`; **`ctwa_clid` + source ad id** → payload (the §11.2 CTWA loop); body→intent hints |
| WABA status webhook | `wa.message.status` | `wa.message.template.status` (engagement.wa.template.status) | delivered/read/failed + quality rating |
| Form/landing/CTWA first touch (lead created) | `lead.captured` | `lead.captured` (data.lead.captured) | `lead_id`→`origin_ref`; `{phone,name}`→`person_hint`; `source{platform,ad_id,ctwa_clid,fbclid,utm}`→payload; **mints `correlation_id`** |
| booking module `booking.created`/`attended` | `booking.created` / `booking.attended` | `booking.created` / `booking.attended` (engagement.booking.*) | `booking_id`, slot, `person` correlation |
| payments module sale/payment | `sale.recorded` / `payment.received` | `sale.recorded` / `payment.received` (engagement.sale.*) | `order_value`(INR paise)→`payload.value` — the true Purchase value §11.1 |
| AI Asset Service `/generate` result | `creative.generated` | `creative.generated` (creative.creative.generated) | `asset_id`,`asset_type`(banner/video_cover),DO-Spaces `url`, DNA tags→DAM |

> Every mapped envelope carries: `event_id`(uuidv7), `tenant_id`/`workspace_id`(from token),
> `correlation_id`(journey), `causation_id`(the OriginEvent id), `actor{kind:webhook,id:origin}`,
> `idempotency_key`(famit source id). **`call.outcome`, `lead.captured`+`lead.scored`, and the
> CTWA `wa.message.received` are the crown-jewel signal feed (§11 — the moat).**

### 3.5 What Phase 0 ships for the connector vs Phase 1

- **Phase 0 (this build):** the **contract only** — `contracts/openapi/origin-connector.yaml`
  (the PUSH/PULL routes above) + `contracts/asyncapi/integration-hub.yaml` (the envelopes it
  emits) + the `OriginEvent` JSON Schema. Plus a `tools/seed` entry that registers Famit as
  the Tenant-Zero `connection` with a dev service token. **No live Famit wiring** (that is a
  Famit-side, flag-gated, dormant-safe unit the orchestrator owns later — the live earner is
  never touched in Phase 0).
- **Phase 1:** implement `/v1/origin/events` → verify → normalize → publish; the `lead.captured`
  + `call.outcome` + CTWA path drive lead-scoring v1 + signals v1 (the thin closed loop §21).

---

## 4. Infra / deploy plan

### 4.1 Local dev (`infra/docker-compose.dev.yml`) — files now, boot on a capable box

Services: **postgres:16** (schema-per-service + RLS), **redpanda** (Kafka API + console;
acts as bus + we run a JSON-Schema registry sidecar), **redis:7** (cache/locks/rate-buckets),
**clickhouse** (events_raw + metrics — Phase 1 onward, container present Phase 0), **temporal**
(+ temporal-ui; durable workflows), **minio** (S3-compat object store / DAM).

```
pnpm dev   →  turbo: docker compose -f infra/docker-compose.dev.yml up -d  &&  start core + temporal worker
```

**HONEST ENV NOTE (D8):** Node 22 / pnpm 10 / uv 0.11 / Docker 29 are present on the build
laptop, so `pnpm install`, `pnpm typecheck`, `pnpm lint`, `pnpm contracts:validate`, and the
**contract-drift test** run here and gate CI. The **full six-container compose stack is
RAM/CPU-heavy** (clickhouse + redpanda + temporal + postgres) and may not boot on this Windows
laptop; it is written as complete, correct files and **documented as box-required to actually
`up`**. Phase 0 acceptance that needs a running bus/Temporal (publish→consume→ledger→trace) is
proven either on a capable dev box or in CI's ephemeral services — not faked.

### 4.2 Production note (needs a box; reuse-vs-new)

DO droplets are **3/3 full** (livekit, panel-2, hatchet — `orchestration-hatchet.md`); a DO
limit raise / new box is required before GROWTH OS prod runs. Reuse-vs-new verdict:

| Component | Verdict | Why |
|---|---|---|
| **Postgres** | **NEW instance** (own schema-per-service + RLS) | P2 no cross-service DB reads; the live Famit PG holds the earner — do not couple GROWTH OS OLTP to it. (Famit PG is reached only via the Origin Connector, never directly.) |
| **Object store** | **REUSE DO Spaces** | already the live artifact store (asset svc + WhatsApp banners); MinIO is dev-only. |
| **Temporal** | **NEW** | §4 decided; Hatchet (existing box) stays Famit-side (D2). Don't overload the hatchet box. |
| **Redpanda / Kafka** | **NEW** | no event bus exists today; Famit is Postgres-broker. The bus is GROWTH OS's nervous system (P2) and must be its own. |
| **ClickHouse** | **NEW** | no analytics warehouse exists; needed for events_raw + metrics layer. |
| **Redis** | **NEW (or shared small)** | rate-buckets + locks; light. |
| **LLM Gateway providers** | **REUSE keys** | OpenRouter (`OPNEROUTER_API_KEY` — founder typo), Groq pool already live; route via the gateway (P8), don't add SDK calls. |
| **AI Asset Service / voice / WhatsApp** | **REUSE live (Tenant Zero)** | via the Origin Connector + Engagement adapters — never rebuilt. |

Production target shape: GROWTH OS gets its **own box** (or managed: Postgres + ClickHouse +
a Kafka-API service + Temporal Cloud are all rentable, dodging the droplet-limit wall) and
talks to the live Famit box **only** over the Origin Connector's authenticated HTTP surface.

### 4.3 Observability & CI

OTel traces across HTTP + bus (P10); RED metrics per module; per-tenant cost meters →
billing-stub. CI (`.github/workflows/ci.yml`): `lint · typecheck · contracts:validate
(JSON-Schema 2020-12) · contract-drift (snapshot diff — fails on an intentional schema edit,
the Phase 0 acceptance) · unit`.

---

## 5. Contracts inventory — what Phase 0 MUST produce (P1)

The source of truth; service code is forbidden before its contract exists. All under
`/contracts`. **Frozen-after-merge** (a new field ⇒ version bump; §6.2 extend-never-mutate).

### 5.1 Event envelope + the 15 core event schemas (`/contracts/schemas/`)
1. `event-envelope.schema.json` — §6.1 (event_id uuidv7, type, version, occurred_at, tenant_id,
   workspace_id, correlation_id, causation_id, actor, idempotency_key, payload). **The root.**
2. `campaign.requested` · 3. `research.completed` · 4. `strategy.compiled` ·
5. `campaign.compiled` · 6. `campaign.launched` · 7. `creative.generated` ·
8. `creative.qa.passed` · 9. `action.plan.signed` · 10. `lead.captured` · 11. `lead.scored` ·
12. `call.completed` · 13. `call.outcome` · 14. `wa.message.sent` (+`received` variant) ·
15. `signal.dispatched` · (+ `optimization.decision` as the 15th business-critical schema).
   These are the §21 Phase 0 "15 core events" + the loop spine §3.1.

### 5.2 The three frozen artifact schemas (`/contracts/schemas/`)
- `campaign_intelligence_brief.schema.json` — CIB, §9.3 normative (Appendix B), frozen-after-merge.
- `media_plan.schema.json` — MediaPlan, §9.9 (campaign/adset/ad tree, budgets, experiment design).
- `action_plan.schema.json` — ActionPlan + Explanation, §7.4 + P5
  (`{action,evidence[],expected_effect,confidence,reversible,approval_required,undo_plan}`).

### 5.3 OpenAPI 3.1 (sync surfaces — `/contracts/openapi/`)
- `core.yaml` — gateway/tenants/flags/ledger/notify public REST (`GET /me/permissions`,
  `POST /actions`, `POST /actions/{id}/sign`, `GET /actions?journey=`, flags CRUD).
- `origin-connector.yaml` — **the §3 Origin Connector** (PUSH `/v1/origin/events`,
  `/v1/origin/webhook/{kind}`; PULL `/v1/origin/{campaigns,reports,leads,signals}`),
  auth = Bearer service token, `Idempotency-Key`, HMAC webhook-out.

### 5.4 AsyncAPI 3 (event-producing surfaces — `/contracts/asyncapi/`)
- `integration-hub.yaml` — channels the Origin Connector publishes (campaign.requested,
  call.completed, call.outcome, lead.captured, wa.message.*).
- `ledger.yaml` — `action.plan.created|signed|executed` channels.
- `core-bus.yaml` — the envelope contract + topic-naming convention `plane.entity.verb`.

### 5.5 Schema registry artifacts (`/contracts/registry/`)
- generated `index.json` (all schemas + versions) + a `drift-snapshot.json` the CI diffs
  against — the mechanism behind the Phase 0 acceptance "contract-drift test fails on an
  intentional schema edit."

---

## 6. Phase 0 acceptance (the bar this architecture must hit)

Per §21 Phase 0: `pnpm dev` boots the stack (on a capable box/CI); a demo publishes
`campaign.requested` → a consumer handles it → a Ledger entry is written (hash-chained) →
the OTel trace is visible end-to-end; and the **contract-drift test fails** when a schema is
intentionally edited. No spend path exists (D6). The Origin Connector exists as a **contract +
seeded Tenant-Zero connection**, with live Famit wiring deferred to a later, flag-gated,
dormant-safe unit that never touches the live earner.

---

## Appendix — load-bearing live-platform facts (so Phase 1 doesn't re-derive)

- **AI Asset Service** = dedicated FastAPI, `127.0.0.1:8310`, OpenRouter `gemini-2.5-flash-image`,
  wallet-metered (reserve→settle, no double-charge), DO Spaces; reached from panel via
  frontend-box nginx `/api/assets/ → :8310`; service-token + scoped tenant token.
- **Wallet** (reuse as the money model): INTEGER **paise** INR, `reserve(tenant_id,
  amount_minor,resource_type,resource_id,idem_key)->hold_id|None`, `settle(hold_id,actual)`,
  `release(hold_id)`; no-double-spend proven; `idem_key` is the exactly-once primitive (P3).
- **Firewall**: PIN (Argon2id per-user in AIM; salted-sha256 tenant-level in monolith) +
  HS256 step-up token, sub-bound to caller, TTL 300s. Step-up scope vocab `spend|bulk|destructive`.
- **Audit**: immutable PG `events` leg (not JSONL); money rows ride inside the wallet txn.
- **Tenant isolation rule (non-negotiable)**: tenant from the **token**, never the request
  body; FORCE-RLS per table; negative control proves the test has teeth. Mirror this exactly
  in the Origin Connector (§3.1).
- **Env gotchas**: OpenRouter key var is the founder typo **`OPNEROUTER_API_KEY`**; box Python
  3.12; `/run` + `/suppression` take **Form fields not JSON**; live caller uses `X-Auth` header,
  but the clean Origin Connector uses `Authorization: Bearer`.
- **Orchestration**: Famit = Hatchet (F3, own box, Postgres-broker); GROWTH OS = Temporal
  (own). They bridge only at the Origin Connector envelope.
```
