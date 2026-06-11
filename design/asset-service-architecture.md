# AI ASSET SERVICE — DEDICATED-SERVICE ARCHITECTURE + MICROSERVICE VERDICT (`asset-service-architecture.md`)

> **Wave role:** SERVICE ARCHITECTURE + the founder's microservice verdict. **READ-ONLY DESIGN** — this file is the
> single source of truth for the dedicated **AI Asset Service** (the generation ENGINE behind Creative Studio).
> No app code edited, no deploy, no git.
> **Conforms to:** `CREATIVE_STUDIO_MASTER_PROMPT.md` (42 founder DNA sections + the architecture decision).
> **Mirrors the proven blueprint of:** `design/aim-architecture.md` (the AI Manager dedicated service — same
> deploy/RLS/wallet/audit/Hatchet/dormant-gate pattern, adapted from a *command brain* to a *generation engine*).
> **Reuses, never rebuilds:** `wallet.py` (credit holds), `audit.py` (immutable trail), `db.engine` RLS/GUC,
> Hatchet (F3 async jobs), `media_gen/` (the existing dormant engine — assessed below), the monolith `/api`.
> Verified against LIVE box source on disk 2026-06-11 (`famit@168.144.153.145:/opt/famit-agent/`).

---

## 0. GROUND TRUTH (read off the live box, not memory — 2026-06-11)

| Asset on the box | Fact (verified) | How the Asset Service uses it |
|---|---|---|
| `media_gen/` package | EXISTS at `/opt/famit-agent/media_gen/` (router.py, spaces.py, video/, image/, threed/, tests/). Mounted ONLY behind `FEATURE_MEDIA=1` (**default OFF → not mounted, byte-identical live**). | **ABSORBED + extended** (see §2). The Asset Service is the *productionised, schema-backed, Studio-aware* evolution of `media_gen`. |
| `media_gen/video/` | The ONE complete, real engine: `providers.py` (PURE per-provider request/parse/verify SWITCH, no I/O), `schema.py` (`JobStatus` lifecycle + `VideoBrief`), `cost.py` (wallet+caps seam), `pricing.py`, `safety.py`, `approval.py`, `audit_hook.py`, `client.py` (never-raises httpx). | **The GOLD-STANDARD pattern** the image engine is cloned from. `JobStatus`, the spaces writer, the cost/wallet seam and the audit_hook are **directly reusable**. |
| `media_gen/image/` | A **1-file STUB** that `try: from creative import image_banner_studio`. **`creative/` is NOT on the box** (`ls` → No such file or directory) → stub degrades to `{"engine":"absent"}`. BUT the real engine **EXISTS in the local repo** at `droplet_work/creative/image_banner_studio/` (full Provider ABC `providers/base.py` + registry + adapters fake/ideogram/recraft/gpt_image/flux_hosted/flux_selfhost). So the image engine is **BUILT but NOT DEPLOYED**. | The Asset Service is the **production home that DEPLOYS this existing engine** + **adds an `openrouter` provider adapter** (it's the one missing impl). NOT a from-scratch build, NOT a clone — deploy + extend what's already written. |
| `media_gen/spaces.py` | SHARED DO-Spaces S3 writer (boto3 lazy, dormant-until-`SPACES_*`, never raises, `put_from_url`/`put_bytes`). | **Reused as-is** (moved into the service or imported) as the artifact sink. Interim (no creds) → box filesystem fallback. |
| `media_gen/router.py` | `build_router(resolve_tenant, can, need_auth, forbidden, firewall=None)` — token-deriving authed mount surface; `_bare_router()` (DO-NOT-MOUNT) reads tenant from body. Submit OVERWRITES `brief["tenant_id"]=token_tenant`; by-job_id routes enforce ownership. | Pattern reused for the service's HTTP surface; in the dedicated service tenant comes from the validated `X-Auth` token (same seam). |
| `wallet.py` | `available()`, `balance(tenant_id, currency)`, `reserve(tenant_id, amount_minor:int, resource_type, resource_id, idem_key, ...) -> hold_id:int\|None`, `settle(hold_id:int, actual_minor:int, idem_key, ...)`, `release(hold_id:int, idem_key, reason)`. INTEGER PAISE, ACID, no-double-spend PROVEN. | **CostGuard** reserves BEFORE generation, settles ACTUAL provider cost after, releases on failure. Never re-implements money math. |
| `audit.py` | `record(actor, action, object_type, object_id, channel, tenant_id, meta)` — append-only JSONL DUAL-mirrored to immutable PG `events` (content-hash PK). Never raises. | Every generation lifecycle event audited, `channel="ai_asset"`, actor = verified tenant. |
| `db.engine` | `session(tenant_id, is_admin)` → `SET LOCAL app.tenant_id/app.is_admin` in-txn (PgBouncer-safe). RLS shape = `db/rls.sql` (admin-GUC OR `vendor_id`=`app.tenant_id`, FORCE RLS, `famit_app` NOSUPERUSER/NOBYPASSRLS). | The service's own DB layer mirrors this; every `ai_asset_*` table FORCE-RLS by `vendor_id`, admin-GUC policy copied verbatim. |
| Hatchet F3 | Engine `famit-hatchet` priv `10.122.0.3:7077`, token on box, `TLS_STRATEGY=none`, Postgres-broker, durable proven. **gRPC currently 127.0.0.1-bound → cross-box not reachable yet** (the AIM "cutover prereqs" apply identically). | Generation jobs = Hatchet workflows (`ai_asset_jobs`). Service = Hatchet client + worker. Dormant if Hatchet env unset → bounded inline fallback. |
| Monolith `/api` | `caller.py` uvicorn `:8209`, header `X-Auth`, `resolve_tenant(request)` (token-derived tenant, NEVER body). nginx `/api` proxy is on the **frontend box**, NOT this box (no nginx /api here). | The service calls `/api` over the VPC to read campaign/brand/lead context and to publish assets into WhatsApp/Adbot/workflow. nginx routing change lives on the frontend box. |
| Python / venvs | Box Python **3.12.3**; venvs `/opt/famit-agent/.venv`, `/opt/capsy-agent/.venv`, `/opt/caps/.venv`. | The service gets its OWN venv `/opt/famit-aiasset/.venv` (independent dep set). |
| `.env` | **No `OPENROUTER_*`, `SPACES_*`, `FEATURE_MEDIA`, or image keys set** today. Backups `.env.*bak.*` exist. | Ships DORMANT. Activation = founder pastes OpenRouter key + (later) Spaces creds + `AIASSET_ENABLED=1`. |

**Net architecture in one line:** a standalone FastAPI app (`/opt/famit-aiasset/`, own venv, own port `:8310`,
own systemd unit `famit-aiasset` + a Hatchet-worker unit, own Postgres schema `ai_asset_*` FORCE-RLS) that owns the
**campaign-context → AI-prompt-build → image-model render → variants → asset library → publish** engine, reuses
`wallet.py`/`audit.py`/RLS/Hatchet/`media_gen`-spaces, is **model-agnostic** (a `Provider` abstraction; OpenRouter =
first impl), and **calls the monolith `/api` over the VPC** for campaign context + publishing. Co-located on the
backend box NOW (droplet limit 3/3); **extractable to a GPU droplet later by changing three env URLs**.

---

## 1. THE MICROSERVICE VERDICT (founder's whole-platform list)

> The founder asked for the explicit "service vs module" call across the platform, with the SCALE TRIGGERS that
> would later justify extraction. The principle (per `famit-architecture-decision` + the AIM/Creative decisions):
> **a FEW coarse-grained services around a service-extractable modular monolith — NOT a microservice swarm.**
> A new service is justified ONLY when a domain has a *distinct scaling axis, a distinct failure domain, or a
> distinct dependency/runtime* that would otherwise destabilise the monolith. Everything else stays an in-monolith
> module behind a clean interface, extractable the day a trigger fires.

| Domain | Verdict | WHY | Scale trigger that would later force extraction |
|---|---|---|---|
| **AI Asset Service** (Creative Studio engine) | **DEDICATED SERVICE** ✅ (this doc) | Distinct runtime (GPU-capable later), distinct deps (boto3/image-SDKs/provider HTTP), bursty/long-running generation queue, fast-evolving provider matrix, large binary artifacts. A heavy generation burst must NEVER stall the API/voice loop. | Already a service. Extraction to its OWN GPU droplet triggers when: self-host image/video models are turned on (GPU needed), OR generation QPS saturates the shared box CPU/RAM, OR DO Spaces egress/storage warrants isolation. |
| **AI Manager** (command brain) | **DEDICATED SERVICE** ✅ (`design/aim-architecture.md`) | The highest-privilege human surface (a phone call that can spend money); distinct voice/telephony scaling; orchestration brain. | Extraction triggers when inbound voice concurrency needs dedicated CPU/SIP, or the command volume warrants its own box. |
| **Workflow engine** | **ALREADY A SEPARATE ENGINE (Hatchet, F3)** ✅ | Durable multi-day orchestration is its own runtime concern; Hatchet is purpose-built and already on its own droplet (`famit-hatchet`). The panel's *Workflow Studio* stays an in-monolith UI/DSL module that DELEGATES to Hatchet. | None needed — already separated. The Studio module extracts only if its draft/validate load grows large (unlikely). |
| **Voice plane** (LiveKit + SIP dialer) | **ALREADY SEPARATE RUNTIME** ✅ | Real-time media (RTP/SIP/STT/TTS) is a fundamentally different runtime from a request/response API. Lives on `famit-livekit`. | Already separate; scales by adding worker personas / a media droplet. |
| **Integrations Hub** (WhatsApp/Meta/Google/CRM connectors) | **MONOLITH MODULE (for now)** ⏸ | Mostly thin, stateless, credential-bound HTTP connectors — no distinct scaling axis. Cheaper in-process. | Extract when connector count + webhook ingestion volume (esp. WhatsApp inbound at scale) needs independent throughput/retry isolation, or a noisy connector threatens API latency. |
| **Analytics / Reporting** | **MONOLITH MODULE (for now)** ⏸ | Read-mostly over the same Postgres; today's volume is fine inline. | Extract to a read-replica/OLAP service when reporting queries start contending with transactional load, or a columnar store (ClickHouse/DuckDB) is introduced. |
| **Foundation Control Layer** (admin plane / entitlements) | **CORE — INLINE BOUNDARY (never a separate service)** 🛡 | It is the *entitlement boundary that wraps every request*. Per `design/control-security.md`, the admin plane is the sharpest knife — it must be enforced INLINE (fail-closed middleware), not reachable as a network hop that could be bypassed. Splitting it out would create a trust gap. | NEVER extracted as a callable service. (Its read-side dashboards may surface via the monolith; enforcement stays inline.) |
| **Adbot / Ads engine** | **MONOLITH MODULE** ⏸ | Spend-gated module reusing wallet/firewall/audit; in-process today (`ads_engine`, FEATURE_ADS). | Extract only if autonomous-bidding loops become compute-heavy or need their own scheduler beyond Hatchet. |
| **Billing / Wallet / Firewall / Audit** | **CORE SHARED LIBS (in-monolith, importable)** 🔒 | Money custody + safety primitives must be one source of truth, transactionally co-located with the data they protect. Every service REUSES them (lib now, network on extraction). | Never extracted — they are the spine every service composes. |

**Verdict in one line:** *AI Asset Service = service · AI Manager = service · Workflow = Hatchet (already) ·
Voice = separate runtime (already) · Integrations + Analytics + Adbot = monolith-for-now · Control Layer = core
inline boundary · Wallet/Audit/Firewall = core shared libs.* Four coarse services around one modular monolith.

---

## 2. EXISTING `media_gen/` — REUSE / ABSORB DECISION (assessed on the box)

**Decision: ABSORB + EXTEND, do not start from scratch, do not run two parallel image engines.**

What the engine code actually is (verified on box + local repo): a **dormant engine layer** with TWO complete
implementations — `media_gen/video/` (deployed to the box) and `creative/image_banner_studio/` (the real image
engine, present in the LOCAL repo `droplet_work/creative/image_banner_studio/` but NOT deployed — which is why the
box's `media_gen/image/` stub degrades to `engine:absent`). The image engine is **BUILT but UNDEPLOYED**, and it
ALREADY carries the full Provider abstraction the master spec asks for. So the real Phase-1 work is **deploy it +
add the one missing `openrouter` provider adapter**, NOT re-architecting. Concretely:

- **REUSE DIRECTLY (move/import into the service, unchanged):**
  - `media_gen/spaces.py` — the shared S3/Spaces artifact writer (dormant-until-`SPACES_*`, never raises). The
    Asset Service's storage layer IS this, plus a box-filesystem fallback for the interim (no Spaces creds yet).
  - `media_gen/video/schema.py::JobStatus` — the exact async lifecycle vocabulary
    (`queued → awaiting_approval → submitted → running → succeeded/failed/cancelled/not_configured`, with TERMINAL set).
  - `media_gen/video/cost.py` + `pricing.py` pattern — the estimate→reserve→settle→release wallet seam (with the
    USD→INR-paise CEIL FX learning baked in; see `media-gen.md` brain: never under-reserve, tag the hold backend).
  - `media_gen/video/audit_hook.py` — the `audit.record`-compatible logger.
  - `media_gen/video/safety.py` + `approval.py` — content/likeness screen BEFORE spend; approval gate.
- **DEPLOY + EXTEND THE EXISTING IMAGE ENGINE (the real Phase-1 work — NOT a clone):**
  - `creative/image_banner_studio/` (local repo) already has the full Provider protocol (`providers/base.py`:
    id/status/estimate_cost/generate/generate_async → `ImageResult`), a registry (`providers/__init__.py`), a
    job-type ladder (`router.py`), shared `_common.py` (http/redact/usd_to_inr), and adapters
    fake/ideogram/recraft/gpt_image/flux_hosted/flux_selfhost. The Asset Service **deploys this verbatim** and
    **adds one file `providers/openrouter.py`** (the missing impl) + one registry line. **Do NOT design a new
    abstraction** — the abstraction the master spec asks for is already written.
  - OpenRouter specifics (verified by the provider-research wave, see `media-gen.md` brain): same chat endpoint
    `POST /api/v1/chat/completions` + `"modalities":["image","text"]`; image returns SYNCHRONOUS as a base64
    data-URL at `choices[0].message.images[0].image_url.url` (model the b64 parse on `gpt_image.py`). Default model
    `google/gemini-2.5-flash-image`. **⚠ Env var is misspelled `OPNEROUTER_API_KEY`** — read both spellings.
  - `media_gen/video/providers.py` (the PURE submit/parse/verify SWITCH for `fal|replicate|luma|…`) remains the
    pattern for the LATER **video** providers under the same unified API; nothing to clone for image.
- **REPLACE (do NOT delegate to it):**
  - `media_gen/image/__init__.py` (the stub) is dead weight once the real engine is deployed in the service; retired.
- **DEFER (Phase 2+, keep dormant):**
  - `media_gen/video/` (full video engine) and `media_gen/threed/` — out of Creative Studio Phase 1 (static
    visuals only). They REMAIN as the video/3D engines the Asset Service later exposes through the SAME unified
    API + provider abstraction. No throwaway: image now, video/3D plug into the identical contract.

**Why absorb (not import the package as-is):** the dedicated service needs schema-backed jobs/assets/versions
(`ai_asset_*` FORCE-RLS tables), a Studio-aware two-stage flow (campaign-context → AI-prompt-build → image model),
and a long-lived asset LIBRARY with versions/scores/performance — none of which the dormant brief-in/brief-out
`media_gen` package models. The service is the *productionised home* for that engine code, with `media_gen`'s
proven primitives moved in. The old `media_gen` router stays unmounted (FEATURE_MEDIA off) and is retired in a
later caller.py cleanup, exactly like the AIM in-process router.

---

## 3. PROCESS / DEPLOY MODEL

### 3.1 Where it runs (now vs later)
- **NOW (co-located):** new dir **`/opt/famit-aiasset/`** on the backend box `168.144.153.145`, **own venv**
  `/opt/famit-aiasset/.venv` (independent dep set: fastapi, uvicorn, sqlalchemy, psycopg2, httpx, hatchet-sdk,
  pydantic, pyjwt, boto3, Pillow). Listens on **`127.0.0.1:8310`** (localhost-only; never world-exposed). Uses its
  **own Postgres schema** `ai_asset_*` in the SAME PG cluster the monolith uses (same `famit_app` role + RLS).
  Artifacts → box filesystem `/opt/famit-aiasset/var/assets/<vendor_id>/...` (interim) until `SPACES_*` lands.
- **LATER (extracted, GPU droplet):** copy `/opt/famit-aiasset/`, point `AIASSET_MONOLITH_BASE_URL` at the backend
  box private IP, `AIASSET_PG_DSN` at the shared/managed PG, `AIASSET_HATCHET_HOST_PORT` at the F3 box. **Zero code
  change** — three env values move; the service was network-call-only to the monolith from day one. Self-host image
  models (FLUX/SDXL on a GPU) become a `selfhost` provider impl behind the same abstraction.

### 3.2 systemd units (`/etc/systemd/system/`)
```ini
# famit-aiasset.service — the HTTP API
[Unit]
Description=Famit AI Asset Service (Creative Studio generation engine)
After=network-online.target postgresql.service
[Service]
User=famit
WorkingDirectory=/opt/famit-aiasset
EnvironmentFile=/opt/famit-aiasset/.env
ExecStart=/opt/famit-aiasset/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8310 --workers 2
Restart=on-failure
RestartSec=3
[Install]
WantedBy=multi-user.target
```
A SECOND unit **`famit-aiasset-worker.service`** runs the Hatchet generation worker
(`ExecStart=…/.venv/bin/python -m app.workers.hatchet_worker`) — the async render executor (§5). Installed
`disabled`; off until enabled. (No voice unit — Asset Service has no telephony surface.)

### 3.3 How the service authenticates to the monolith `/api`
- Reuses a **`AIASSET_SERVICE_TOKEN`** (new, alongside `AIM_SERVICE_TOKEN`). Outbound calls to `caller.py` carry
  `Authorization: Bearer <AIASSET_SERVICE_TOKEN>` for the *service hops* (campaign-context read, asset-publish).
- **Tenant impersonation, the safe way (same as AIM):** for a verified vendor the service asks the monolith to
  mint a **short-lived scoped tenant token** (`POST /api/internal/mint-scoped-token`, service-token only — the
  SAME endpoint the AIM design introduces, reused). Reads of campaign/brand/lead context and writes that publish
  an asset into WhatsApp/Adbot/workflow execute **as that tenant token** (`X-Auth: <tenant_token>`), so the
  monolith's own `resolve_tenant` + RLS re-enforce scope on the executing side — defense in depth.
- Localhost/VPC-only; no new public surface (the monolith ufw already allows `:8209` from the VPC).

### 3.4 How the panel reaches the service (nginx proxy, on the FRONTEND box)
- New nginx location on the **frontend box** vhost (the `/api` proxy lives there, NOT the backend box):
  `location /api/assets/ { proxy_pass http://<backend-priv-ip>:8310/; proxy_set_header X-Auth $http_x_auth; … }`
  — Creative Studio calls `/api/assets/*` exactly like every other `/api/*` route; nginx routes THIS prefix to the
  Asset Service. The panel keeps sending its `X-Auth` tenant token; the service validates it (calls monolith
  `GET /api/me`, or verifies the HMAC token shape locally with the shared `SECRET`).
- The dormant `media_gen` `/media/*` router stays unmounted; no cutover collision (different prefix `/api/assets`).

### 3.5 Resting state / flag gate (ships DORMANT + safe)
- Whole service gated by **`AIASSET_ENABLED`** (default `0`). When `0`: the service still starts, serves
  `GET /assets/status` → `{"enabled":false,...}` and `GET /health`; every generate/publish endpoint returns
  `{"status":"not_configured","enabled":false}` 200 with **zero** side effects.
- `ensure_schema()` is a no-op unless `AIASSET_PG_DSN` is set AND `db.available()` (only creates `ai_asset_*`
  tables; touches nothing live).
- Worker is a separate `disabled` systemd unit. nginx `/api/assets/` location can be left commented until cutover.
- **Until the founder pastes the OpenRouter key + sets `AIASSET_ENABLED=1` + reloads nginx, the live platform is
  byte-for-byte unchanged.** Per-vendor double gate: even enabled globally, a vendor row off → that vendor's
  Studio is off (founder rolls out vendor-by-vendor).

---

## 4. DATABASE SCHEMA — `ai_asset_*` (FORCE RLS by `vendor_id`)

> **Posture:** standalone `ai_asset/schema.sql`, applied as `famit_app` via lazy `ensure_schema()` (mirrors
> `crm/schema.sql`, `db/ddl_wallet.sql`, `ai_manager/schema.sql`). **NOT an Alembic revision** — off the live P1
> chain. Every table: `vendor_id text NOT NULL`, `ENABLE`+`FORCE ROW LEVEL SECURITY`, the **identical admin-GUC
> isolation policy** from `db/rls.sql`. Money never lives here (wallet owns it). Large binaries never live here
> (Spaces/box-fs owns them; only the URL + metadata persist).

Tables (8):
1. **`ai_asset_brand_kits`** — one per vendor (logo URL, colors[], fonts, tone, preferred CTA/language,
   do-not-use words/styles, approved/rejected style memory). The brand DNA (master §13).
2. **`ai_asset_generation_jobs`** — one generation request (campaign_id, instruction, platform, asset_type,
   provider, model, variant_count, `JobStatus`, `job_id` Hatchet run, cost_estimate jsonb, hold_id, idem_key
   UNIQUE per vendor). The lifecycle row (§6).
3. **`ai_asset_assets`** — one generated asset/variant (job_id, campaign_id, type, platform, size/aspect, angle,
   headline, subheadline, CTA, prompt_used, provider/model, storage_url, thumb_url, status
   `draft|needs_review|approved|rejected|used|archived`, creative_score jsonb, cost_minor, used_in[]).
4. **`ai_asset_versions`** — every edit/regeneration = a new VERSION row (parent_asset_id, change_instruction,
   storage_url, created_at). Original is never overwritten (master §26 NEVER-overwrite).
5. **`ai_asset_performance`** — per-asset metrics (impressions, clicks, CTR, leads, CPL, conversions, WA replies,
   bookings, spend) fed back from Adbot/Analytics for the learning loop (master §31).
6. **`ai_asset_audit_logs`** — IMMUTABLE per-vendor event trail (mirrors `audit.py` events; queryable here).
   `famit_app` SELECT+INSERT only (no UPDATE/DELETE) = append-only.
7. **`ai_asset_idempotency`** — generic op idempotency (shape == `wallet_idempotency`); `(vendor_id, idem_key)`.
8. **`ai_asset_provider_state`** — per-vendor provider/model preferences + per-provider configured flags + last
   error (drives the model selector UI + dormancy display).

RLS: every table `ENABLE`+`FORCE ROW LEVEL SECURITY` with policy
`USING (current_setting('app.is_admin',true)='1' OR vendor_id=current_setting('app.tenant_id',true))`
`WITH CHECK (...same...)`. Grants: full DML to `famit_app` on all EXCEPT `ai_asset_audit_logs` (SELECT+INSERT only).
**Tenant invariant (tested):** every read/write opens `db.session(vendor_id=…)`; a forged body `vendor_id` is
ignored (vendor always token-derived); cross-vendor probe (auth A, forge B) → 0 rows on BOTH service tables AND
the monolith side (scoped tenant token).

---

## 5. SERVICE DECOMPOSITION + ASYNC GENERATION (Hatchet, F3)

### 5.1 File skeleton (`/opt/famit-aiasset/`)
```
/opt/famit-aiasset/
  app/
    main.py                 # FastAPI factory; AIASSET_ENABLED gate; ensure_schema() on startup; /health /status
    config.py               # env reader (dormant-until-key); URLs/tokens; never raises at import
    db/{engine.py,schema.sql,rls.sql,bootstrap.py,repo.py}   # own engine + GUC session + 8 ai_asset_* tables, vendor-scoped CRUD
    engine/
      studio_engine.py      # AssetStudioEngine — the orchestrator (§6 two-stage lifecycle)
      context.py            # CampaignContextBuilder — pulls business/campaign/brand/lead data from /api (read)
      prompt_builder.py     # AIPromptBuilder — campaign data + angle -> rich image prompt (LLM, stage 1)
      variants.py           # VariantPlanner — ~5 DIFFERENT marketing angles (price/location/emotion/urgency/...)
      cost_guard.py         # CostGuard — estimate -> reserve(hold) -> settle/release via wallet.py (reuse media_gen/video/cost pattern)
      safety.py             # content/likeness/text-accuracy screen BEFORE spend (NEVER invent price/RERA/claims)
      scoring.py            # creative score (clarity/readability/CTA/brand-match/platform-fit/...)
      audit_service.py      # dual write: audit.py events + ai_asset_audit_logs (secret-scrub)
    providers/
      __init__.py           # ImageProvider ABC + REGISTRY (selection via config)
      image/{openrouter.py,leonardo.py,flux.py,openai_images.py,google.py,stability.py,selfhost.py}  # PURE switch — cloned from media_gen/video/providers.py
      client.py             # never-raises httpx round-trip (cloned from media_gen/video/client.py)
      llm.py                # LLMProvider ABC + GroqLLM/Claude + MockLLM (the prompt-builder LLM)
    storage/
      spaces.py             # REUSED media_gen/spaces.py (S3/Spaces) + box-fs fallback for interim
    adapters/
      monolith_client.py    # httpx -> caller.py /api (service token + scoped tenant token)
      whatsapp.py adbot.py workflow.py campaigns.py   # PUBLISH an approved asset into each consumer
    workers/{hatchet_worker.py, workflows.py}   # async render jobs -> ai_asset_generation_jobs
    api/{status.py, brand_kit.py, generate.py, assets.py, versions.py, library.py, publish.py, performance.py, dashboard.py}
  tests/  .env  .venv/  requirements.txt
  systemd/{famit-aiasset.service, famit-aiasset-worker.service}
  var/assets/             # interim local artifact store (until Spaces)
```

### 5.2 Provider abstraction (model-agnostic — master §rule 10/13)
```python
class ImageProvider(ABC):
    name: str                              # "openrouter" | "leonardo" | "flux" | ...
    def is_configured(self) -> bool: ...
    def build_submit(self, brief, model, key) -> tuple[url, headers, body]   # PURE
    def parse_submit(self, resp) -> JobRef                                   # PURE
    def build_status(self, job_ref, key) -> tuple[url, headers]              # PURE
    def parse_result(self, resp) -> tuple[artifact_url|bytes, JobStatus]     # PURE
    def verify_webhook(self, headers, body, secret) -> bool                  # PURE
```
**OpenRouter is the FIRST impl, not the architecture.** Selection via `config.py` (`AIASSET_IMAGE_PROVIDER`,
`AIASSET_IMAGE_MODEL`). Each `is_configured()`-gated (dormant-until-key). `MockProvider` returns a deterministic
placeholder for zero-key offline tests. Swapping Leonardo/Flux/Stability later = a new file, **no UI/workflow
change**. ⚠ Open-question recorded in §8: confirm OpenRouter actually serves an image-generation model surface;
if it only proxies chat/LLM, the first concrete image impl is OpenAI-Images/Stability/Leonardo via the SAME ABC —
the abstraction makes this a one-file swap, not a rearchitecture.

### 5.3 Async generation via Hatchet (reuse F3)
- A generate request (esp. multi-variant batches) is NOT rendered inline. The engine creates an
  `ai_asset_generation_jobs` row (`status=queued`) and **triggers a Hatchet workflow** (`generate_pack_wf`); the
  service is a Hatchet client (`AIASSET_HATCHET_HOST_PORT` → `10.122.0.3:7077`, token on box, `TLS_STRATEGY=none`).
- `workers/workflows.py` defines `generate_pack_wf` (one task per variant: build prompt → call provider → store
  artifact → write `ai_asset_assets` row → update job). Durable: a worker crash resumes from Hatchet's Postgres
  broker (F3 proven). On task start/finish the worker updates the job row + each asset row.
- The UI's **"liquid"-wave loading** (master §36, ChatGPT-image-gen style) is fed by polling
  `GET /assets/jobs/{id}` / a stream of per-variant `running → succeeded` transitions off these rows.
- **Resting state:** if Hatchet env unset → bounded inline executor for small jobs; large packs marked
  `status=failed, error={not_configured: hatchet}`. Never blocks, never crashes.
- **Cross-box reachability** is the SAME F3 prerequisite the AIM design notes (open `hatchet-fw` tcp/7077 from the
  backend box priv IP + set `SERVER_GRPC_BROADCAST_ADDRESS=10.122.0.3:7077` + regenerate token) — shared with AIM.

---

## 6. GENERATION LIFECYCLE (two-stage, master KEY FLOW) — as code flow

`AssetStudioEngine.generate()` persists state to `ai_asset_generation_jobs` at every hop:
1. **receive** → create `ai_asset_generation_jobs` row (`status=queued`); audit `asset.generate.received`.
2. **context** → `CampaignContextBuilder` reads the campaign (business/product/location/price/offer/audience/goal/
   brand kit/lead-type/platform) from `/api` as the scoped tenant token. Missing key info → ask ONE clarifying
   question (master §17/§18), never re-spec.
3. **plan variants** → `VariantPlanner` picks ~5 DIFFERENT marketing angles (price/location/emotion/urgency/trust/
   …), each with a testing hypothesis (for Adbot).
4. **safety (BEFORE spend)** → `safety.screen()` — text-accuracy guard (NEVER invent price/discount/location/phone/
   RERA/guarantee/claim/testimonial — master §20 critical), likeness/content check. Violations → strip or clarify.
5. **prompt build (stage 1, LLM)** → `AIPromptBuilder` turns campaign data + angle into a rich image prompt
   (platform-aware size, brand style, CTA, text hierarchy). The LLM builds the PROMPT; it never authorises spend.
6. **estimate + reserve** → `CostGuard.estimate()` (per-provider/per-variant pricing) → "≈ N credits, continue?"
   (master §35); on confirm `wallet.reserve(hold)` (idempotent on idem_key, INTEGER PAISE, USD→INR-paise CEIL).
7. **render (stage 2, image model)** → async via Hatchet (§5.3): each variant → provider `build_submit` → `client`
   httpx → poll/webhook → artifact to Spaces/box-fs → `ai_asset_assets` row (`status=draft`). `JobStatus` advances.
8. **score** → `scoring.score()` per asset (clarity/readability/CTA/brand-match/platform-fit/…).
9. **settle/release** → success: `CostGuard.settle(actual_provider_cost)`; failure: `CostGuard.release()`.
10. **audit + return** → write results, audit `asset.generated`/`failed`, return the variant grid for Creative Studio.

**Edit/regenerate** (master §26) = a new `ai_asset_versions` row (original kept); natural-language instruction →
`prompt_builder` delta → re-render that variant. **Approval** flips `ai_asset_assets.status`; only `approved` →
Adbot (unless auto mode); rejections feed `ai_asset_brand_kits` style memory. **Publish** (`adapters/*`) pushes an
approved asset into WhatsApp template / Adbot test / workflow node, as the scoped tenant token.

**Idempotency:** step 1 enforces `(vendor_id, idem_key)` UNIQUE → a replayed generate returns the stored result
(no double-render, no double-spend) — same guarantee as `wallet_idempotency`.

> **Deploy note (shared-lib NOW vs network LATER) — the only co-location coupling:** while co-located, CostGuard/
> AuditService reuse `wallet.py`/`audit.py` by **direct import** (same box; `sys.path` add to `/opt/famit-agent`).
> On extraction these become **network calls** to existing monolith routes (`/api/wallet/*`, `/api/audit`) via a
> `_mode = "lib"|"http"` switch in `config.py` — extraction flips one env value, not the call sites. Campaign-context
> reads and asset-publish are HTTP from day one.

---

## 7. HOW EACH CONSUMER CALLS THE SERVICE (the integration map)

| Caller | Path | How it reaches the Asset Service |
|---|---|---|
| **Creative Studio (panel UI)** | `/api/assets/*` via frontend-box nginx → `:8310` | Vendor `X-Auth` token; the primary surface (generate/library/edit/approve/publish). |
| **AI Manager** (voice/chat `creative.*` intents) | service→service over VPC → `:8310` (service token + scoped tenant token) | The AIM execution router gets a `creative` adapter that calls the Asset Service ("create 5 ad banners for this campaign", "make it premium", "send approved banner to WhatsApp campaign"). Video→Video AI, brochure→Brochure AI (out of scope). |
| **WhatsApp module** | panel → `/api/assets/library` + `/api/assets/{id}/attach` | Browse/preview/filter Creative Studio assets, attach to a WA template; AI can create the template from the campaign + attach the banner (master WhatsApp changes). |
| **Adbot / Ads engine** | monolith module → `:8310` (service token + scoped token) | Pulls approved variants for low-budget tests; pushes performance back into `ai_asset_performance` (the learning loop, master §32). |
| **Workflow (Hatchet)** | workflow node → `:8310` | "new campaign → make 5 Meta + 3 WA banners → save → approve → Adbot"; asset generation as a workflow node (master §33). |
| **Monolith `caller.py`** | does NOT call out | The Asset Service calls IN to `caller.py /api` (context read + publish). caller.py stays untouched; its dormant `media_gen` router is unmounted/retired later. |

---

## 8. RESTING STATE + OPEN FORKS (founder-side; recorded, not blocking design)
- **`AIASSET_ENABLED=0`** default → live platform byte-identical until the founder enables + reloads nginx.
- **OpenRouter API key** — NOT on the box `.env` today (spec says it's in `.env.local`; not present server-side).
  Founder pastes it server-side. ⚠ **Confirm OpenRouter exposes an IMAGE-generation model** — if it's chat/LLM
  only, the first concrete image impl is OpenAI-Images/Stability/Leonardo via the SAME `ImageProvider` ABC (one-file
  swap, no rearchitecture). The two-stage design (LLM prompt-build is provider-agnostic) is unaffected either way.
- **DO Spaces creds** (`SPACES_KEY/SECRET/BUCKET/REGION/ENDPOINT`) — interim = box filesystem `var/assets/`.
- **Hatchet cross-box reachability** — same F3 prereq as AIM (open tcp/7077 from backend priv IP + broadcast addr
  + regen token). Until then → bounded inline render for small jobs.
- **DO droplet limit (3/3)** — blocks true extraction to a GPU box; co-located until raised. Self-host image/video
  models gated on that GPU droplet.
- **Reasoning LLM key** (Groq/Claude) for the stage-1 prompt builder — reuse box `GROQ_API_KEY*`; MockLLM until set.

---

## 9. DEPLOY / INTEGRATION MAP (one-screen summary)

```
                         FRONTEND BOX (panel.famit.in, nginx)
                          location /api/assets/  ── proxy ─┐
                          location /api/*         ── proxy ─┼──► caller.py :8209 (monolith /api)
                                                            │
   Creative Studio UI ──X-Auth──► /api/assets/* ───────────┘
                                                            │ (VPC)
                          BACKEND BOX 168.144.153.145       ▼
   ┌──────────────────────────────────────────────────────────────────────────────────┐
   │  caller.py :8209 (monolith) ── wallet.py · audit.py · firewall.py · db.engine RLS  │ core shared libs
   │        ▲  /api/internal/mint-scoped-token   /api/me   /api/campaigns ...           │
   │        │ (service token + scoped tenant token)                                     │
   │  ┌─────┴───────────────────────────────────────────────────────────────────────┐  │
   │  │  famit-aiasset.service  :8310  (own venv /opt/famit-aiasset/.venv)            │  │ DEDICATED SERVICE
   │  │   app/ engine(studio,context,prompt,variants,cost,safety,scoring,audit)      │  │
   │  │   providers/image/* (ABC: openrouter→leonardo→flux→… ; PURE switch)          │  │
   │  │   storage/spaces.py (REUSED media_gen) + var/assets fallback                 │  │
   │  │   adapters/(whatsapp,adbot,workflow,campaigns)  db: ai_asset_* FORCE-RLS     │  │
   │  └──────────────┬──────────────────────────────────────────────────────────────┘  │
   │  famit-aiasset-worker.service  ── Hatchet client ──► gRPC 10.122.0.3:7077 (F3 box)  │ async render
   └──────────────────────────────────────────────────────────────────────────────────┘
   Consumers (all via :8310): AI Manager (creative.* intents) · WhatsApp (attach asset) ·
   Adbot (pull variants / push performance) · Workflow node (generate-pack).
   Artifacts: box-fs now → DO Spaces later.  Extraction: copy dir + 3 env URLs → GPU droplet.
```

**Build-unit note (for the later build wave):** mirror the AIM 14-unit crash-safe model — skeleton+flag-gate →
schema+RLS → repo+isolation test → providers ABC + OpenRouter + MockProvider → cost-guard (wallet) → prompt/
variants/safety → studio engine lifecycle (offline test, idempotent) → api routers → Hatchet worker + workflows →
adapters/publish → wiring (nginx `/api/assets/`, `mint-scoped-token` reuse, systemd) as un-applied diffs behind
`AIASSET_ENABLED=0`. Safety (schema/RLS/cost/text-accuracy) lands before any real render; live platform untouched
until the final wiring unit.
```
