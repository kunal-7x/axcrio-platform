# AI ASSET SERVICE — BACKEND DESIGN (READ-ONLY design wave, 2026-06-11)

> Dedicated coarse SERVICE that powers **Creative Studio** (the panel UI). Phase 1 = static
> image/banner/ad-image only. Conforms to `caps/CREATIVE_STUDIO_MASTER_PROMPT.md` (42 DNA sections +
> the architecture decision). This doc = the backend: PG `ai_asset_*` schema (FORCE-RLS) + the
> campaign-aware pipeline + Hatchet async job model + wallet billing + the authed API + the build units.
>
> **Status: DESIGN ONLY.** No app code, no deploy, no git in this wave.
>
> **Companion design docs (conform to these — same wave):** `design/asset-service-architecture.md` (the
> SERVICE shape: standalone FastAPI `/opt/famit-aiasset/`, port `127.0.0.1:8310`, systemd `famit-aiasset` +
> `famit-aiasset-worker`, panel reaches it via the **frontend-box nginx** `location /api/assets/ → :8310`,
> service auth `AIASSET_SERVICE_TOKEN` + AIM `POST /api/internal/mint-scoped-token`, gated `AIASSET_ENABLED=0`,
> `_mode=lib|http` extraction seam) and `design/asset-provider-research.md` (OpenRouter image-gen facts: same
> `/v1/chat/completions` + `modalities:["image","text"]`, base64 data-URL out, default `google/gemini-2.5-flash-image`,
> **env var is the founder typo `OPNEROUTER_API_KEY`** — adapter reads `OPNEROUTER_API_KEY or OPENROUTER_API_KEY`).
> This doc = the DATA + PIPELINE + API + JOB-MODEL + BUILD-UNIT detail under that decided shape; where the
> two diverge on transport, the architecture doc wins (standalone service + `/api/assets/*`, not an in-caller mount).

---

## 0. REUSE INVENTORY (assess-first; this is NOT a from-scratch build)

The backend tree (`droplet_work/`) ALREADY contains a large, dormant `creative/*` prototype. The decided
architecture (`ai_asset_*` PG-RLS dedicated service) is a **formalization + promotion** of that prototype,
not a rewrite. What we REUSE verbatim vs BUILD new:

| Existing asset (`droplet_work/`) | What it gives us | Verdict |
|---|---|---|
| `creative/image_banner_studio/providers/{base,fake,ideogram,recraft,gpt_image,flux_hosted,flux_selfhost}.py` | The **Provider protocol** (`status/estimate_cost/generate/generate_async`, read-keys-fresh, dormant, never-raises) + 6 working adapters | **REUSE as-is.** This IS the model-agnostic provider abstraction the spec demands. **ADD** one adapter: `openrouter.py` (the spec's first provider). |
| `creative/image_banner_studio/{types,router,batch,safety,meter}.py` | brief/result dataclasses, job_type→provider routing ladder, batch cross-product expansion, denylist safety prefilter, usage metering | **REUSE the logic**, re-home under the service. `types.ImageBrief` becomes the in-process variant brief; routing/safety/batch are pure and portable. |
| `creative/image_banner_studio/context.py` | `enrich(spec, tenant_id)` — the campaign-aware seam, **currently a DORMANT no-op** | **BUILD the real body** = the §17 Campaign Context Reader (this doc §4). The seam already exists; we fill it. |
| `creative/shared/llm.py` | injected-callable LLM seam to the in-house `llm-router` (or Groq/Claude), dormant-safe | **REUSE** as the LLM transport for the AIPromptBuilder. |
| `creative/asset_library/models.py` (`AssetRef`, `AssetQuery`, `SearchPage`) | the canonical asset record shape + search facets + `public_dict()` (drops `local_path`) | **REUSE the field set** → it becomes the `ai_assets` table columns 1:1 (the JSONL `AssetRef` is promoted to a PG row). |
| `creative/image_banner_studio/storage.py` + `asset_library/{storage,spaces}.py` | `var/creatives/` JSONL writes + DO Spaces (boto3 S3-compat) writer | **REPLACE the index** (JSONL→PG) but **REUSE the bytes writer** (filesystem now, Spaces when `SPACES_*` lands). |
| `media_gen/spaces.py` | shared DO-Spaces boto3 writer (dormant when `SPACES_*` unset) | **REUSE** as the single artifact-store backend. |
| `wallet.py` (`reserve/settle/release/balance`, INTEGER PAISE, idempotency) | the proven no-double-spend ACID money core | **REUSE** — replace the prototype's `creative/shared/cost.py` JSON hold-shim with the real wallet (§6). |
| `firewall.py` (`check_pin/mint_step_up/verify_step_up_token/require_step_up`) | PIN step-up gate, sub-bound F3 tokens | **REUSE** at the route layer for spend/destructive actions. |
| `audit.py` (`audit.record(actor,action,...,channel=,tenant_id=)`) | immutable PG `events` ledger leg | **REUSE**, `channel="ai_asset"`. |
| `db/engine.py` `session(tenant_id, is_admin)` | proven FORCE-RLS GUC-in-txn + admin escape hatch | **REUSE** — every asset op = one `with engine.session() as s:` block (same invariant as wallet). |
| `creative/ads_engine/spine_link.py` | authenticated loopback read pattern (`httpx` GET to monolith `/leads`,`/analytics` w/ service-token Bearer, dormant, never-raises) + `handoff.jsonl` drain | **REUSE the pattern** for the Campaign Reader's monolith reads + the WhatsApp/Adbot handoff. |
| `creative/ads_engine/*` (bandit/experiment/attribution/optimizer) | the Adbot test→kill-losers→scale-winners loop | **INTEGRATION TARGET** (§7 attach + §10 perf-learning), not part of this service's core. |

**Net new in this service** (what does NOT exist yet): the `ai_asset_*` **PG schema**, the **AIPromptBuilder**
(LLM campaign-field→N-angle-variant-brief transform, §20 no-invent guardrails), the **Hatchet async job
model** (queued→running→streaming→succeeded/failed), the real **Campaign Context Reader**, the **creative
scorer**, **versioning/regeneration**, the **approval lifecycle**, **brand-kit memory**, and the **authed
token-deriving API**. Everything visual/provider is reuse; everything stateful/safety/intelligence is build.

---

## 1. SERVICE SHAPE

- **Package / deploy:** `ai_asset/` (underscore — importable; "ai-asset" is a display label). Per the
  architecture doc this ships as a **standalone FastAPI service** at `/opt/famit-aiasset/` (own venv), bound
  **`127.0.0.1:8310`**, systemd `famit-aiasset` (API) + `famit-aiasset-worker` (the Hatchet worker — separate
  unit so heavy generation never blocks API/voice). Co-located on the backend box now (DO droplet limit 3/3);
  extractable to a GPU droplet later via the `_mode=lib|http` seam.
- **Panel reach:** the `/api` proxy is on the **frontend box**, NOT the backend box — the panel calls the
  service through nginx `location /api/assets/ → 127.0.0.1:8310`. So the public API base is **`/api/assets/*`**
  (not an in-caller `/*` mount). The monolith is NOT modified to mount this router.
- **Composition:** while co-located (`_mode=lib`) the service imports `wallet`, `firewall`, `audit`,
  `db.engine` directly (the `ai_manager` precedent); it reads campaign data over **authenticated localhost
  loopback** to the monolith (`spine_link` pattern) using `AIASSET_SERVICE_TOKEN` + AIM's
  `POST /api/internal/mint-scoped-token` for a scoped tenant token (RLS re-enforced on the executing side),
  NOT a direct `caller.py` import. On extraction (`_mode=http`) those direct imports flip to HTTP calls.
- **Dormant-until-creds, never-raises** (the `whatsapp.py` contract, enforced repo-wide): with no provider
  key + `AIASSET_ENABLED=0`, every entry point returns `{"status":"not_configured"}`, does zero network I/O,
  never raises → the live system is byte-identical. The `fake` provider keeps the whole pipeline exercisable
  offline with zero spend.
- **Two-stage engine (spec KEY FLOW):** LLM (AIPromptBuilder) builds the rich per-variant prompt from
  campaign context → image Provider renders. Stage 1 is text/cheap; stage 2 is the metered image call.

---

## 2. POSTGRES SCHEMA — `ai_asset_*` (db/ddl_ai_asset.sql)

Mirrors `db/ddl_wallet.sql` posture exactly: **idempotent** (`CREATE ... IF NOT EXISTS` / `DROP POLICY IF
EXISTS`), applied standalone as `famit_app` (off the P1 Alembic chain), **all money in INTEGER PAISE**,
`tenant_id TEXT` == the existing org id. **FORCE ROW LEVEL SECURITY** on every table with the **P1 admin-GUC
policy shape**. `famit_app` is `NOSUPERUSER/NOBYPASSRLS` so FORCE binds even the owner.

### 2.1 Tables (8)

**`ai_asset_providers`** — model/provider registry (model-agnostic core). Seeded, tenant-agnostic (RLS:
admin-only write; readable to all for routing). One row per `(provider_id, model_id)`.
```
provider_id   TEXT  -- openrouter | ideogram | recraft | gpt_image | flux_hosted | flux_selfhost | fake
model_id      TEXT  -- e.g. 'openrouter:google/gemini-2.5-flash-image' , 'ideogram-v2' , 'flux.1-schnell'
display_name  TEXT
modality      TEXT  DEFAULT 'image'          -- image now; video/threed later (forward-compat)
capabilities  JSONB DEFAULT '{}'             -- {indic_text:true, svg:true, max_size:'1536x1536', ref_image:true}
cost_minor    BIGINT DEFAULT 0               -- rate-card est INR paise per image (router/estimator input)
status        TEXT  DEFAULT 'active'         -- active | deprecated | disabled
license_class TEXT  DEFAULT 'commercial_ok'  -- commercial_ok | needs_license (flux -dev/klein-9b gate)
created_at    TIMESTAMPTZ DEFAULT now()
PRIMARY KEY (provider_id, model_id)
```

**`ai_brand_kits`** — brand memory (spec §13). One+ per tenant (a tenant may keep brand variants).
```
id            TEXT PRIMARY KEY              -- bk_<uuid4hex>
tenant_id     TEXT NOT NULL
name          TEXT DEFAULT 'Default'
logo_url      TEXT DEFAULT ''
palette       JSONB DEFAULT '[]'            -- ['#0B5','#FFF',...]
fonts         JSONB DEFAULT '[]'
tone          TEXT DEFAULT ''               -- premium | local | bold | emotional | trust | minimal
default_cta   TEXT DEFAULT ''
language_pref TEXT DEFAULT 'en'             -- en | hi | hinglish | gu
do_not_use    JSONB DEFAULT '{}'            -- {words:[...], styles:['cheap_discount'], colors:[...]}
best_style    TEXT DEFAULT ''               -- learned: top-performing visual style
is_default    BOOLEAN DEFAULT false
created_at    TIMESTAMPTZ DEFAULT now()
updated_at    TIMESTAMPTZ DEFAULT now()
```

**`ai_generation_jobs`** — one row per "Create banner" request (the async UNIT the UI polls/streams).
```
id              TEXT PRIMARY KEY            -- gj_<uuid4hex>
tenant_id       TEXT NOT NULL
campaign_id     TEXT DEFAULT ''
brand_kit_id    TEXT DEFAULT ''
request         JSONB NOT NULL              -- the normalized GenerateSpec (platform, type, count, instruction, model)
campaign_ctx    JSONB DEFAULT '{}'          -- the snapshot the Reader resolved (provenance; §20 audit of what AI used)
state           TEXT NOT NULL DEFAULT 'queued'   -- queued|running|streaming|succeeded|partial|failed|cancelled
phase           TEXT DEFAULT 'queued'       -- queued|reading_campaign|building_prompts|rendering|scoring|storing|done
progress        JSONB DEFAULT '{}'          -- {total:N, done:k, streaming_variant:'va_..'} -> premium live loader
hatchet_run_id  TEXT DEFAULT ''             -- the Hatchet workflow run id (durable handle)
hold_id         BIGINT NULL                 -- wallet hold reserved up-front (settle/refund at finish)
est_cost_minor  BIGINT DEFAULT 0
actual_cost_minor BIGINT DEFAULT 0
n_requested     INT DEFAULT 0
n_succeeded     INT DEFAULT 0
error           TEXT DEFAULT ''
idempotency_key TEXT NULL                   -- dedupe double-submit (UI retry); UNIQUE per tenant
created_at      TIMESTAMPTZ DEFAULT now()
updated_at      TIMESTAMPTZ DEFAULT now()
finished_at     TIMESTAMPTZ NULL
UNIQUE (tenant_id, idempotency_key)
```

**`ai_assets`** — the Asset Library record. Columns promote `creative/asset_library/models.AssetRef` 1:1
(the JSONL record becomes a PG row). **The current approved/live version is denormalized here for fast
library queries; full history lives in `ai_asset_versions`.**
```
id            TEXT PRIMARY KEY             -- ca_<uuid4hex>  (keep the existing convention)
tenant_id     TEXT NOT NULL
campaign_id   TEXT DEFAULT ''
job_id        TEXT DEFAULT ''              -- originating ai_generation_jobs.id
brand_kit_id  TEXT DEFAULT ''
kind          TEXT DEFAULT 'banner'        -- banner|image|social|offer|product|logo|... (AssetRef KINDS)
platform      TEXT DEFAULT ''              -- meta|ig_story|whatsapp|google|carousel|hero
size          TEXT DEFAULT ''              -- 1080x1080 | 1080x1920 | 1200x628 ...
angle         TEXT DEFAULT ''              -- price|location|emotion|urgency|trust|problem_solution|benefit|offer|retargeting|comparison
headline      TEXT DEFAULT ''
subhead       TEXT DEFAULT ''
cta           TEXT DEFAULT ''
language      TEXT DEFAULT 'en'
hypothesis    TEXT DEFAULT ''              -- the §9 testing hypothesis (for Adbot)
status        TEXT DEFAULT 'draft'         -- draft|needs_review|approved|rejected|used|archived (spec §28)
current_version_id TEXT DEFAULT ''         -- FK -> ai_asset_versions.id (the live render)
score         JSONB DEFAULT '{}'           -- the creative-score object (denormalized latest)
metrics       JSONB DEFAULT '{}'           -- impressions/clicks/ctr/leads/cpl/wa_replies (from Adbot)
source        TEXT DEFAULT 'generated'     -- generated|uploaded|registered
tags          JSONB DEFAULT '[]'
meta          JSONB DEFAULT '{}'           -- {ai_generated:true, route_reason, model_id, ...}
created_at    TIMESTAMPTZ DEFAULT now()
updated_at    TIMESTAMPTZ DEFAULT now()
```

**`ai_asset_versions`** — every render is an immutable version; edit/regenerate creates a NEW one, the
original is **never overwritten** (spec §26/§41). Approval/rollback flips `ai_assets.current_version_id`.
```
id             TEXT PRIMARY KEY            -- av_<uuid4hex>
asset_id       TEXT NOT NULL              -- parent ai_assets.id
tenant_id      TEXT NOT NULL
version_no     INT NOT NULL               -- 1,2,3...
parent_version_id TEXT DEFAULT ''         -- the version this was edited/regen'd from (lineage)
job_id         TEXT DEFAULT ''            -- the job that produced THIS version
provider_id    TEXT DEFAULT ''
model_id       TEXT DEFAULT ''
prompt         TEXT DEFAULT ''            -- the rendered image prompt (provenance/debug)
edit_instruction TEXT DEFAULT ''          -- the NL edit that spawned it ("make it premium", "remove price")
storage        TEXT DEFAULT 'local'       -- local | spaces
url            TEXT DEFAULT ''            -- public URL OR /assets/<id>/raw
thumb_url      TEXT DEFAULT ''
format         TEXT DEFAULT 'png'
width          INT DEFAULT 0
height         INT DEFAULT 0
bytes          BIGINT DEFAULT 0
sha256         TEXT DEFAULT ''            -- integrity only (NOT dedupe)
local_path     TEXT DEFAULT ''           -- on-droplet; NEVER exposed via API (public view drops it)
est_cost_minor BIGINT DEFAULT 0
created_at     TIMESTAMPTZ DEFAULT now()
UNIQUE (asset_id, version_no)
```

**`ai_creative_scores`** — the §30 creative score per version (kept separate so re-scoring is append-only +
auditable). Latest is denormalized into `ai_assets.score`.
```
id          TEXT PRIMARY KEY             -- cs_<uuid4hex>
version_id  TEXT NOT NULL
asset_id    TEXT NOT NULL
tenant_id   TEXT NOT NULL
scores      JSONB NOT NULL               -- {clarity,readability,cta,brand_match,platform_fit,quality,
                                         --  conversion,relevance,text_amount,offer_visibility} each 0-100
overall     INT DEFAULT 0                -- weighted 0-100
scored_by   TEXT DEFAULT 'rule'          -- rule | llm | human
notes       TEXT DEFAULT ''
created_at  TIMESTAMPTZ DEFAULT now()
```

**`ai_asset_usage`** — links an asset/version to where it was USED (WhatsApp template, Adbot experiment,
workflow node) so performance flows back and reuse is tracked (spec §28/§31).
```
id          TEXT PRIMARY KEY             -- au_<uuid4hex>
asset_id    TEXT NOT NULL
version_id  TEXT DEFAULT ''
tenant_id   TEXT NOT NULL
channel     TEXT NOT NULL                -- whatsapp | meta_ads | google_ads | workflow | landing
ref_id      TEXT DEFAULT ''             -- wa_template_id | ads_experiment_id | workflow_run_id
status      TEXT DEFAULT 'attached'      -- attached | published | live | ended
metrics     JSONB DEFAULT '{}'           -- per-placement perf snapshot
created_at  TIMESTAMPTZ DEFAULT now()
updated_at  TIMESTAMPTZ DEFAULT now()
```

**`ai_asset_idempotency`** — generate-submit dedupe (UI double-click / retry), mirrors `wallet_idempotency`.
```
idem_key   TEXT PRIMARY KEY
tenant_id  TEXT NOT NULL
op         TEXT NOT NULL                 -- generate | edit | regenerate | variation
result     JSONB NOT NULL                -- the stored {job_id,...} to replay
created_at TIMESTAMPTZ DEFAULT now()
```

### 2.2 Indexes
`ai_assets (tenant_id, created_at DESC)`, `ai_assets (tenant_id, campaign_id)`,
`ai_assets (tenant_id, status)`, `ai_assets (tenant_id, platform)`,
`ai_asset_versions (asset_id, version_no)`, `ai_generation_jobs (tenant_id, state)`,
`ai_generation_jobs (state) WHERE state IN ('queued','running','streaming')` (worker poll),
`ai_asset_usage (asset_id)`, `ai_creative_scores (version_id)`.

### 2.3 RLS (FORCE; admin-GUC escape hatch — verbatim the `db/ddl_wallet.sql` `DO $rls$` loop)
Every `ai_asset_*` table: `ENABLE` + `FORCE ROW LEVEL SECURITY`; policy
`USING/WITH CHECK ( current_setting('app.is_admin',true)='1' OR tenant_id = current_setting('app.tenant_id',true) )`.
`ai_asset_providers` is the one tenant-agnostic table: read to all, write requires `app.is_admin='1'`
(seeded by admin; tenants never write the model registry). Grants: `SELECT,INSERT,UPDATE` to `famit_app`
(NO `DELETE` — lifecycle is status flips: `rejected`/`archived`/`trashed`, never hard-delete, spec §41).
`ALTER DEFAULT PRIVILEGES ... GRANT USAGE,SELECT ON SEQUENCES` (F7, though we use TEXT ids not serials).

### 2.4 Idempotency
- **Submit:** `(tenant_id, idempotency_key)` UNIQUE on `ai_generation_jobs` + `ai_asset_idempotency` →
  a retried POST returns the SAME `job_id`, never double-charges or double-renders.
- **Per-variant render:** the Hatchet task is keyed by `(job_id, variant_id)`; a Hatchet retry that
  re-runs a completed variant is a no-op (the version row already exists → `INSERT ... ON CONFLICT (asset_id,
  version_no) DO NOTHING`, the same self-locking pattern wallet uses).
- **Money:** wallet's own `idem_key` (`reserve:job:<job_id>`, `settle:job:<job_id>`) is the no-double-spend
  primitive — reused, not reinvented (media-gen lesson: flow the idem_key, tag the hold backend).

---

## 3. PIPELINE (the campaign-aware engine — spec §3-6, §8-9, §17, §20)

```
POST /generate
   │  (token-derived tenant; normalize GenerateSpec; idempotency claim)
   ▼
[1] Campaign Context Reader  ──reads──> monolith GET /campaigns/{id} (+ /me, brand_kit)  ........ §4
   │      builds CampaignContext {business, product, audience, objective, funnel_stage,
   │      platform, offer, brand, location, price, goal→cta, language}  (NO-INVENT: only real fields)
   ▼
[2] Wallet ESTIMATE + HOLD  ──reserve(est_cost)──> wallet.py  (refuse if insufficient; UI "≈30 credits?")  §6
   │      persist ai_generation_jobs {state:queued, hold_id, est_cost_minor, campaign_ctx snapshot}
   ▼
[3] Hatchet ENQUEUE  ──ai_asset_generate_workflow(job_id)──> Hatchet (durable)  ...................... §5
   │      return {job_id, state:queued} immediately  → UI shows premium live loader
   ▼   ════════════ async, in the ai-asset-worker process ════════════
[4] AIPromptBuilder (LLM)  ── creative/shared/llm.generate ──>  N DIFFERENT ANGLES  ................. §3.1
   │      one VariantBrief per angle: {angle, headline, subhead, cta, visual_direction, size,
   │      platform, hypothesis, language} — §20 guardrails strip any invented price/claim
   ▼
[5] Provider RENDER (per variant, fan-out tasks)  ── router → Provider.generate_async ──>  image bytes  §3.2
   │      reuse image_banner_studio.router ladder; ADD openrouter adapter; safety prefilter before spend
   │      stream each finished variant → update ai_generation_jobs.progress (state:streaming)
   ▼
[6] STORE  ── spaces.py | filesystem ──>  ai_asset_versions row + ai_assets row (status:needs_review)  §2
   ▼
[7] SCORE  ── rule/llm scorer ──>  ai_creative_scores + denormalize ai_assets.score  ............... §30
   ▼
[8] SETTLE  ── wallet.settle(actual) / refund unused on partial/fail ──>  job state:succeeded|partial  §6
   │      audit.record(channel="ai_asset", actor=tenant, action="asset.generate", meta={...})
   ▼
   Asset Library  →  (approve)  →  WhatsApp / Adbot / Workflow  ........................................ §7
```

### 3.1 AIPromptBuilder (NET NEW — the intelligence core, spec §8/§9/§10/§17/§20)
- **Input:** `CampaignContext` + the `GenerateSpec` (platform, asset_type, count N, free-text instruction,
  language). **Output:** `N` `VariantBrief`s, each a DIFFERENT marketing angle (price / location / emotion /
  urgency / trust / problem-solution / benefit / offer / retargeting / comparison) — NOT N random images.
- **Transport:** `creative/shared/llm.generate(prompt, response_format=json)` (the injected-callable seam;
  prod = in-house llm-router or Groq JSON-mode / Claude Opus 4.8 `output_config.format`, temp=0; test =
  `fake_llm`). Strict JSON, validated; on bad JSON retry-once then fall back to a deterministic angle table
  (the `DEFAULT_ANGLES` in `types.py` already exists) so the pipeline never stalls.
- **Each `VariantBrief`:** `{angle, purpose, headline(3-8 words), subhead, cta(goal-matched), visual_direction,
  style(premium|local|bold|emotional|trust|minimal), platform, size, language, hypothesis}` →
  `image_banner_studio.types.ImageBrief` (the existing render contract) + the structured copy that lands in
  the `ai_assets`/`ai_asset_versions` columns.
- **§20 NO-INVENT GUARDRAIL (critical, fail-closed):** a deterministic post-LLM validator scrubs every
  VariantBrief — any price / discount % / location / phone / RERA / guarantee / amenity / testimonial / award
  / "100% / approved / certified" claim that is **not present verbatim in `CampaignContext`** is STRIPPED (or
  the field blanked + a `missing_field` note raised for the UI to ask). The LLM is an INPUT, never the
  authority on facts — same posture as `ai_manager` (model's risk label ignored & recomputed). This validator
  is unit-tested with a negative control (feed an invented "50% OFF" not in context → asserted stripped).

### 3.2 Provider render (REUSE)
- `image_banner_studio.router.route(brief)` picks the provider (logo→recraft, indic→gpt_image/openrouter,
  english-headline→ideogram, photoreal→flux, nothing-configured→fake). **ADD** `providers/openrouter.py`
  (the spec's first provider) implementing the existing `Provider` protocol; confirm OpenRouter's
  image-gen model support at enable (spec BLOCKER) — if a chosen OpenRouter model lacks image output, the
  router ladder falls through to the next configured provider (graceful, no crash).
- Safety prefilter (`safety.py`) runs BEFORE any paid call (likeness/denylist first-line). License gate
  (`flux_selfhost.py`) blocks non-commercial weights unless `BFL_COMMERCIAL_LICENSE=1`. Both already exist.

---

## 4. CAMPAIGN CONTEXT READER (fills the dormant `context.enrich` seam)

- **Pattern:** `creative/ads_engine/spine_link.py` — authenticated localhost loopback `httpx` GET to the
  monolith with a service-token (`AIASSET_SERVICE_TOKEN`, a real manager/admin tenant token, dormant-until-set).
  **Reads** (confirmed monolith routes): `GET /campaigns/{id}` → `{campaign:{id, fields:{...}}}`,
  `GET /me` (business profile), `GET /leads?...` (audience/stage signal), `GET /analytics`/`GET /stats`
  (best-performing signal for brand-memory learning). **Auth note:** the monolith legacy header is
  `X-Auth: <token>` (NOT Bearer) for the famit token; the loopback uses the service token in the header the
  monolith expects — confirm at wiring.
- **Output `CampaignContext`** (the §6 "AI understands before creating" object):
  `{business_name, industry, product, location, price, offer, audience, goal, benefits, lead_type,
  funnel_stage, platform, images[], logo_url, brand_style, language}` — every field tagged with provenance
  (`from_campaign | from_brand_kit | from_me | absent`) so §20 can enforce no-invent and the UI's "Campaign
  Context Panel" can show "what data AI is using".
- **Missing-data policy (spec §18):** if enough to generate → proceed; if a KEY field is missing (which
  campaign? WhatsApp or Meta? premium or offer? include price?) → the job returns `state:needs_input` with a
  short `clarify` list, never a full re-spec demand, never an invented value.
- **Dormant-safe:** no service token → returns `not_configured`, pipeline runs on the explicit GenerateSpec +
  brand-kit only (no campaign enrichment), never raises (exact `enrich()` contract).

---

## 5. ASYNC JOB MODEL — Hatchet (spec §3 live progress + premium loading)

- **Engine:** the F3 `famit-hatchet` box (priv `10.122.0.3:7077`, hatchet-lite, Postgres-broker). The
  cross-box gRPC cutover prereqs (open `7077` from the backend box, set `SERVER_GRPC_BROADCAST_ADDRESS`,
  **regenerate the token after** — it embeds the broadcast address) are listed in the Hatchet brain and are a
  prereq for live async; **until that lands**, the worker runs in **inline/threaded fallback mode** in-process
  (a `BackgroundTasks`-style runner) so the pipeline is demoable without the gRPC cutover. Same dormant-first
  discipline as everywhere else.
- **Workflow `ai_asset_generate_workflow(job_id)`** (durable), steps map 1:1 to `ai_generation_jobs.phase`:
  `read_campaign → build_prompts → fan_out_render(variants) → score → store → settle`. Each step updates
  `ai_generation_jobs.{state,phase,progress}` so the UI poll/stream reflects live state.
  Per-variant render = a fanned-out child task (Hatchet parallelism) keyed `(job_id, variant_id)` (idempotent
  retry). hatchet-sdk 1.33.6: use `input_validator=` (NOT `input_type=`).
- **State machine:** `queued → running → streaming → (succeeded | partial | failed | cancelled)`.
  `streaming` = at least one variant rendered, more in flight → drives the "liquid-wave" loader (the UI
  shows the animated placeholder until each variant's bytes land, ChatGPT-image-gen style).
- **Streaming to the UI:** `GET /jobs/{id}/stream` = Server-Sent Events reading `ai_generation_jobs.
  progress` + emitting each finished `version` as it's stored. `GET /jobs/{id}` = the poll fallback
  (same payload, single shot) for clients without SSE.
- **Crash-safety:** a worker death mid-job leaves the wallet hold OPEN; the **wallet TTL sweep**
  (`sweep_expired_holds`) reclaims it, and a `reconcile` pass marks the job `failed` + refunds — no money
  leaks (reuses the proven wallet primitive, no new mechanism).

---

## 6. BILLING — wallet hold / estimate / settle / refund (spec §35; REUSE `wallet.py`)

- **Estimate** (before submit): sum `ai_asset_providers.cost_minor` over the routed N variants ×
  `AIASSET_COST_SAFETY` (ceil, never under-reserve — the media-gen FX/ceil lesson). Surface to the UI:
  "Generating 10 banners ≈ 30 credits. Continue?".
- **Reserve** (at submit): `wallet.reserve(tenant_id, est_cost_minor, resource_type="ai_asset",
  resource_id=job_id, idem_key="reserve:job:<job_id>", actor=tenant)` → `hold_id` stored on the job. `None`
  (insufficient funds / PG down) → job not enqueued, return a clean `over_budget` (never a 500, never a
  silent free render). **TWO BALANCES caveat** (F4): `prepaid` plan uses legacy `billing.balance`;
  `prepaid_wallet` uses `wallet_accounts` — the gate branches on plan, NEVER sums them.
- **Settle** (at finish): `wallet.settle(hold_id, actual_cost_minor, idem_key="settle:job:<job_id>")` →
  charges actual, refunds the unused remainder atomically (idempotent, double-settle-safe — proven).
- **Refund/release on failure:** a fully-failed job → `wallet.release(hold_id)` (full reserved returned);
  a partial job settles only the produced variants' actual cost, the rest refunds. Per-variant cost is
  metered (`meter.py`) and summed into `ai_generation_jobs.actual_cost_minor`.
- **Tag the hold backend** on the job (`wallet` vs the JSON shim) so settle/release dispatch to the SAME
  minting backend (the media-gen silent-no-op lesson — a JSON `hold_<hex>` must never hit `wallet.settle(int)`).
- **NEVER auto-launch a paid AD with this credit gate** — this gate caps image-GENERATION cost only; live
  ad-spend caps + kill-switch live in `ads_engine` (the existing RED-TEAM caveat, carried forward).

---

## 7. INTEGRATIONS (handoff, not core)

- **Attach-to-WhatsApp** (spec WhatsApp module change): `POST /assets/{id}/attach`
  `{channel:"whatsapp", template_id}` → writes an `ai_asset_usage` row + hands the asset URL to the WA path
  via the proven `handoff.jsonl` drain (never imports the WA client). AI-create-template variant: build the
  template copy from `CampaignContext` + attach the chosen version. Only **approved** assets attach (unless
  an explicit auto-mode flag).
- **Adbot loop** (spec §32): `POST /assets/{id}/attach {channel:"meta_ads", experiment_id}` registers
  the asset's variants (each carries its §9 `hypothesis`) into `ads_engine` experiment slots; `ads_engine`'s
  bandit/optimizer runs the low-budget test, kills losers, scales winners, and writes performance back to
  `ai_assets.metrics` + `ai_asset_usage.metrics` → feeds §10 learning (more variants from winners).
- **Workflow nodes** (spec §32): the service's API surface IS the node contract — a workflow step calls
  `POST /generate` / `POST /assets/{id}/approve` / `.../attach`; no special integration needed
  beyond the authed endpoints (the Workflow Studio already calls service APIs as nodes).
- **AI Manager** (spec §33): AIM routes static-image voice/chat commands here. AIM's deterministic risk
  table already classifies `creative.generate_*` as money-risk → a voice "create 5 ad banners" hits
  `POST /generate` AFTER AIM's PIN/step-up gate; video→Video AI, brochure→Brochure AI (AIM dispatch).

---

## 8. API SURFACE (authed; token-derives tenant; standalone service, base `/api/assets/*`)

**Auth contract (every route):** tenant is **token-derived** (the scoped tenant token minted via AIM's
`mint-scoped-token`; RLS re-enforced on the executing side), NEVER read from the body (the platform's #1
isolation rule). Writes behind `can(tenant,"write")`; spend/destructive behind `firewall.require_step_up(scope)`;
by-id routes enforce `row.tenant_id == token_tenant` else `404` (no info leak). `AIASSET_ENABLED` feature-gates
the whole surface → `503 asset_not_enabled` (the UI's dormant state) except `/api/assets/status` (the un-gated
dormancy probe). Paths below are shown without the `/api/assets` base prefix for brevity.

| Method · Path | Auth | Purpose |
|---|---|---|
| `GET /status` | self (un-gated) | readiness: providers configured, AIASSET_ENABLED, schema_ready, wallet/hatchet up |
| `GET /providers` | self | model registry (id, display, capabilities, est cost) for the UI model selector |
| `POST /generate` | write + step-up(spend) | the main entry: `{campaign_id?, platform, asset_type, count, instruction, language, model?, brand_kit_id?}` → estimate+hold+enqueue → `{job_id, state, est_cost}` (idempotent) |
| `GET /jobs` | self | list jobs (state filter) for the Generation Queue |
| `GET /jobs/{id}` | self (owner) | job status + progress (poll) |
| `GET /jobs/{id}/stream` | self (owner) | **SSE** live progress + variants as they render (premium loader) |
| `POST /jobs/{id}/cancel` | write (owner) | cancel a running job → release hold |
| `GET /assets` | self | Asset Library list + filters: campaign/platform/type/status/angle/size/date/best-performing (AssetQuery facets) |
| `GET /assets/{id}` | self (owner) | asset detail: current version, all versions, score, status, usage, metrics |
| `GET /assets/{id}/raw` | self (owner) | the image bytes (filesystem now / Spaces redirect later); `local_path` never exposed |
| `POST /assets/{id}/edit` | write + step-up(spend) | NL edit ("make it premium","remove price","change CTA","Hinglish","story size") → NEW version (original kept) |
| `POST /assets/{id}/regenerate` | write + step-up(spend) | variations ("5 more like this","new angle","cleaner") → new versions/assets |
| `POST /assets/{id}/approve` | write | status→approved (gates Adbot/WhatsApp) |
| `POST /assets/{id}/reject` | write | status→rejected (+reason; teaches brand-memory) |
| `POST /assets/{id}/attach` | write (+step-up if it triggers spend) | attach to whatsapp \| meta_ads \| workflow → `ai_asset_usage` + handoff |
| `POST /variation-from-upload` | write + step-up(spend) | "create this kind of banner" + an uploaded reference image → generate (multipart; reference_image flows to the provider) |
| `GET /brand-kits` · `POST /brand-kits` · `PUT /brand-kits/{id}` | self / write | brand memory CRUD (logo/palette/tone/cta/language/do-not-use) |
| `POST /webhooks/provider` | provider-signed (service token, NOT tenant) | async provider completion callback (per-provider signature verify, fail-closed) → advance the job |

---

## 9. MULTI-TENANCY + ISOLATION TEST PLAN (gates `AIASSET_ENABLED`)

Two layers (the `ai_manager`/`wallet` precedent): **(a)** token-derived tenant (never body), **(b)** FORCE-RLS
GUC per table. Probes (each must pass before activation; a NEGATIVE CONTROL proves teeth):

1. **RLS per-table (×8):** as `app.tenant_id=A`, `SELECT` returns 0 rows of B's
   assets/versions/jobs/scores/usage/brand_kits; A sees its own (not over-blocking). Admin-GUC `is_admin='1'`
   sees both (the escape hatch works).
2. **Cross-tenant by-id forge matrix:** authed as A, `GET/POST /assets/{B_id}`, `/jobs/{B_id}`,
   `/brand-kits/{B_id}`, `/assets/{B_id}/raw` → **404**, no field leak, no bytes.
3. **Body-override attack:** authed as A, POST `/generate` with `tenant_id=B` in the body → the job is
   created for **A** (body ignored), B's wallet untouched, B's campaign not read.
4. **Step-up replay (F3):** A's `X-Step-Up` token replayed on a B-scoped spend → **403** sub-mismatch.
5. **Wallet isolation:** A's generate reserves against A's `wallet_accounts` only; B's balance unchanged;
   a hold never crosses tenants.
6. **NEGATIVE CONTROL (teeth):** on a throwaway copy of the generate route that reads `tenant_id` from the
   BODY, the forge in (3) SUCCEEDS — proving the real test would fail a broken impl.
7. **No-invent guardrail test:** a CampaignContext with no price + an LLM that returns "₹58L / 50% OFF" →
   asserted STRIPPED from the stored VariantBrief (the §20 validator's negative control).
8. **Money safety:** double-submit (same idem_key) → ONE job, ONE hold; double-settle → charged once
   (reuses the proven `test_wallet_concurrency.py` guarantees, exercised through the asset path).
9. **Raw-bytes leak:** `local_path` absent from every API response (`public_dict()` enforced); `/raw` checks
   ownership before streaming.

---

## 10. BRAND MEMORY + PERFORMANCE LEARNING (spec §13, §31)

- **Brand memory:** `ai_brand_kits` is read by the Campaign Reader + AIPromptBuilder (logo/palette/tone/cta/
  language/do-not-use enforced in every prompt; e.g. never a cheap-discount banner for a premium brand unless
  asked). A **reject** (spec §28) appends the rejected style to `do_not_use` (the system learns); an **approve
  + win** updates `best_style` (the system reinforces).
- **Performance learning:** Adbot writes impressions/clicks/ctr/leads/cpl/wa_replies/bookings back to
  `ai_assets.metrics` + `ai_asset_usage.metrics`; the §10 "more like the winner" regenerate reads the
  winning version's brief + metrics and biases the next batch's angles toward it. (Learning is a bias on
  prompt-building, not a model retrain — Phase 1.)

---

## 11. BUILD UNITS (each = one verifiable, committable deliverable; offline-provable)

| # | Unit | Deliverable | Verify (offline, zero network/spend) |
|---|---|---|---|
| U1 | **Schema** | `db/ddl_ai_asset.sql` (8 tables + RLS + indexes + grants), idempotent | apply as `famit_app`; assert 8 tables, FORCE-RLS + isolation policies present, `DELETE` not granted |
| U2 | **Store core** | `ai_asset/store.py` — every op one `engine.session(tenant_id)` block; CRUD + idempotency + version append + status flips; `public_dict()` drops `local_path` | RLS cross-tenant test (probe 1/2/9); JSON-safe; degrades to []/None on PG down |
| U3 | **Provider + openrouter** | reuse `image_banner_studio/providers/*`; ADD `openrouter.py` (Provider protocol) + register in `ai_asset_providers` | provider `status()` dormant w/o key; `fake` renders; routing ladder unit test |
| U4 | **Campaign Reader** | `ai_asset/campaign.py` — fill `enrich`, loopback reads, `CampaignContext` + provenance | dormant w/o service token; mocked monolith JSON → correct context; never-raises fuzz |
| U5 | **AIPromptBuilder + no-invent** | `ai_asset/prompt_builder.py` — N-angle VariantBriefs via `shared/llm` + the §20 validator | `fake_llm` → N distinct angles; negative control (invented price stripped, probe 7); bad-JSON retry→fallback |
| U6 | **Billing** | `ai_asset/billing.py` — estimate/reserve/settle/release via `wallet.py`, hold-backend tag | seam-signature guard (reserve has `amount_minor`+`idem_key`); over_budget path; double-settle once (probe 8) |
| U7 | **Job + Hatchet** | `ai_asset/jobs.py` + `workflow.py` — state machine, phases, inline-fallback runner, SSE progress | inline runner drives queued→...→succeeded offline; cancel releases hold; crash→TTL-sweep reconcile |
| U8 | **Scorer** | `ai_asset/score.py` — rule-based creative score (LLM optional) → `ai_creative_scores` | deterministic scores 0-100, denormalized to `ai_assets.score`; never-raises |
| U9 | **Versioning/edit/regen** | edit/regenerate → new `ai_asset_versions`, original immutable, approve flips `current_version_id` | original kept after edit; lineage `parent_version_id`; rollback works |
| U10 | **API router** | `ai_asset/endpoints.py` — `build_router(resolve_tenant, can, need_auth, forbidden, firewall)` (token-deriving, NOT a module-level router — the media-gen security lesson) | full forge matrix (probe 2/3/4); AIASSET_ENABLED gate→503; `/status` un-gated |
| U11 | **Integrations** | attach (whatsapp/meta_ads/workflow) → `ai_asset_usage` + `handoff.jsonl`; perf write-back | usage rows; approved-only attach; handoff drained-by-spine contract |
| U12 | **Isolation suite + activation** | `ai_asset/tests/test_isolation.py` (9 probes + negative controls) | all green on live PG before flipping `AIASSET_ENABLED` for ONE test tenant |

**Sequencing:** U1→U2 (schema+store) serial first; U3/U4/U5 parallel (disjoint files); U6→U7 (billing
before jobs); U8/U9 parallel; U10 composes; U11/U12 last. Mode: ADDITIVE, dormant-first, NO `caller.py`/
`agent.py` run-path edits (router is `include_router`'d additively + feature-gated OFF until U12 passes).

---

## 12. CREDS / BLOCKERS (server-side only, never git)
- `OPENROUTER_API_KEY` (spec — first provider; **confirm OpenRouter image-gen model support** at enable).
- `SPACES_KEY/SECRET/BUCKET/REGION/ENDPOINT` (prod storage; interim = box filesystem — `spaces.py` dormant).
- `AIASSET_SERVICE_TOKEN` (loopback campaign reads — a real manager/admin tenant token).
- Hatchet cross-box gRPC cutover (open `7077` from backend box + broadcast addr + **regenerate token**) —
  prereq for live async; inline-fallback runner works without it.
- `AIASSET_ENABLED=true` (master gate, default OFF). Optional per-provider keys (ideogram/recraft/openai/flux)
  + caps (`AIASSET_DAILY/MONTHLY_CAP_INR`, `AIASSET_MAX_BATCH`, `AIASSET_COST_SAFETY`).
- Later providers (Leonardo/Flux/Stability/Google) drop in via the Provider protocol — no schema change.
```
