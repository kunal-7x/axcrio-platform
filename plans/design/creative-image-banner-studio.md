# CREATIVE STUDIO — IMAGE / BANNER STUDIO — Execution-Ready Design Spec

> **Module id:** `image-banner-studio`  ·  **Code path:** `droplet_work/creative/image/`
> **Creative-Studio sub-page it powers:** **"Image & Banner Studio"** (the visual-asset sub-page
> of the Creative Studio sidebar section — siblings: Ad Copy/Hooks, Video, 3D, Landing Pages,
> Brochure/Catalog, WhatsApp Creatives).
> **Date:** 2026-06-09  ·  Research sources inline + listed in §12.

> **For the build agent — implement this verbatim.** This is a NEW module of the Famit Autonomous
> Business OS "Creative Studio": it auto-generates the **image/banner portion of a creative BATCH**
> (ad banners, offer images, product cards, social cards, brand logos/vectors) from a vendor's
> stored business + product + campaign data, selected via a **dropdown** on the Creative Studio page.
>
> **Hard rules from the project brief (do NOT violate):**
> - NEW code ONLY under `droplet_work/creative/`. **Do NOT edit `caller.py` / `agent.py`** (backend
>   spine; wiring deferred to the orchestrator).
> - **NO git** (the orchestrator commits).
> - Every integration is **PROVIDER-AGNOSTIC + DORMANT-UNTIL-CREDS**: a graceful no-op that returns
>   `{"status":"not_configured"}` and **NEVER raises** until the founder pastes keys — byte-for-byte
>   the `droplet_work/whatsapp.py` pattern.
> - **Verifiable OFFLINE**: the acceptance test makes **zero live external calls**. A built-in `fake`
>   provider proves the whole pipeline (validate → route → spend-guard → audit → store → meter)
>   without spending a paisa or needing a key.
> - Cost-optimized; self-host on DigitalOcean where it wins; production-grade, scalable.
>
> **Relationship to `design/automation-image.md`:** that earlier doc designed the same image engine
> under the OLD `automation/` path as a standalone "ad-creative image" pillar. **This spec is the
> Creative-Studio-era home of that engine**: same provider/router/guardrail core (reused, not
> reinvented), but relocated to `creative/image/`, reframed around the **dropdown-driven BATCH** +
> **Creative Studio sub-page**, and explicitly wired to the batch orchestrator that fans assets out to
> ads/leads/CRM/voice/WhatsApp/analytics. **Reconcile the two paths at wiring time** (orchestrator's
> call); the likely outcome is `creative/image/` canonical with `automation/image/` a thin re-export
> shim, but that decision is deferred and not asserted here.

---

## 0. TL;DR — the decisions that define this module

1. **Route by JOB, not by one "best" model.** Banner creative is three different problems; the
   router picks a provider tier from the brief's `job_type`:
   - **`banner` / `social` / `product` / `offer`** (text-heavy composited cards) → **Ideogram v3**
     (near-perfect Latin text-in-image) or **FLUX** (photoreal, cheapest).
   - **`logo` / `icon` / `vector`** → **Recraft V4 Vector** — the *only* model emitting **native,
     editable SVG** (real paths, not traced raster). Decisive for brand assets.
   - **`indic_text`** (Hindi/Devanagari/Tamil/etc. baked INTO the image) → **GPT Image 2**, the
     strongest 2026 model at legible non-Latin scripts at headline sizes (now corroborated by 2+
     sources, §1; still verify with a live test before betting spend).
   - **`bulk` / `draft` at high volume, OR brand-LoRA / privacy** → **self-hosted FLUX.1-schnell or
     FLUX.2 Klein (both Apache-2.0)** / **SDXL (OpenRAIL++)** on a DO GPU box (§3 economics).

2. **The studio's job is a BATCH, not one image.** The Creative Studio promise is: vendor picks a
   product/campaign from a dropdown → AI emits a **testing batch** (e.g. **10 banners** across
   sizes/angles). So the public API has a **`generate_batch(spec)`** that expands one product/campaign
   into N briefs (sizes × angles × headlines) and runs them through the single-image pipeline. Each
   variant is independently routed, spend-gated, stored, and tagged with a `batch_id` + `variant_id`
   so the **autonomous-ads** layer can launch them as A/B variants and report CTR/CPC/ROI back per
   variant.

3. **Every provider is an adapter behind one interface** — `generate(brief) -> ImageResult`. Adapters:
   `ideogram`, `recraft`, `gpt_image`, `flux_hosted` (fal | replicate | bfl — one adapter, env
   selects backend), `flux_selfhost` (our DO GPU box), and a built-in `fake`. Adding a provider = one
   file + one registry line; swapping vendors = one env var. **No business logic knows a vendor name.**

4. **Dormant-until-creds, exactly like `whatsapp.py`.** No keys → `status()=="not_configured"`,
   `generate()` returns `{"ok":False,"status":"not_configured",...}`, logs one line, **never raises,
   never calls out**. The full pipeline still runs against `fake`, so the module is testable with zero
   credentials.

5. **Spend gated BEFORE the call, metered AFTER, every generation audited.** Per-tenant daily/monthly
   budget caps + a per-image price ceiling are checked *before* any paid call (batch cost is summed
   and gated as a whole); over budget → `{"status":"over_budget"}`, zero spend. After a paid call the
   estimated cost is written to the same `usage_events.json` stream the `vendors/*_meter.py` adapters
   use, so image spend shows in the billing UI beside Groq/ElevenLabs/Vobiz. An optional **human
   approval gate** holds paid batches in a `pending` queue (off by default).

6. **Honest scope (§10).** This is a **draft-and-variation engine with a human approval gate**, not a
   fire-and-forget art director. AI reliably gives: photoreal backgrounds, accurate English headline
   text (Ideogram), native editable SVG logos (Recraft), Hindi headline text (GPT Image 2), infinite
   cheap drafts (self-host FLUX). Still needs a human: pixel-exact brand-kit lockups, long body copy,
   final legal/claims review. We composite the real logo/legal line in a deterministic layer; we do
   not ask the model to bake a paragraph.

---

## 1. CHOSEN TOOLS + WHY (researched 2026-06, all ACTIVE; sources §12)

| Need | Chosen tool | Why (evidence) | Price (2026) | Licence |
|---|---|---|---|---|
| **English/Latin text in banner** | **Ideogram v3** | The only model that reliably renders complex text-in-image; built for posters/packaging/ads | $0.03 (base) – $0.09 (quality) /img on fal | Hosted API (commercial OK) |
| **Logos / icons / editable vector** | **Recraft V4 Vector** | *Only* model emitting **native SVG** (mathematical paths, layers, discrete color regions); #1 on Text-to-Image Arena | $0.04 raster / $0.08 SVG | Hosted API (commercial OK) |
| **Hindi / Devanagari / Indic text in image** | **GPT Image 2** | First model that reliably renders Devanagari, Tamil, Kannada, CJK at headline/sub-headline sizes where FLUX/Ideogram/Recraft fail (segmind + 2026 round-ups). **Verify w/ live test before betting spend** | ~$0.006 (low)–$0.21 (high) /1024² | Hosted API, token-billed |
| **Photoreal product/people/background (hosted)** | **FLUX.2 [pro] / FLUX 1.1 [pro]** via fal/Replicate | Best photorealism + prompt adherence; hosted price *includes* commercial right | $0.02–0.10 /img | Hosted = commercial OK |
| **Bulk/draft + brand-LoRA (SELF-HOST)** | **FLUX.1-schnell / FLUX.2 Klein** | **Both Apache-2.0 → free commercial output**; fast; "good enough" for drafts. Klein runs on an 8 GB card. **Self-host wins at high volume OR for LoRA/privacy — NOT low-volume cost** | ~$0.003/img hosted; ~₹0 marginal self-host (but GPU is a fixed bill) | **Apache-2.0** |
| **Brand-style LoRA / 8 GB self-host** | **SDXL** | OpenRAIL++ commercial; runs on 8 GB; the LoRA/customization king | free self-host | **OpenRAIL++** |
| **Serverless GPU broker (one key, many models)** | **fal.ai** (primary), **Replicate** (alt) | fal = predictable per-image price + one key for Ideogram/Recraft/FLUX; Replicate = per-GPU-second (good for custom models) | per-use | pay-per-use |
| **Self-host runtime** | **ComfyUI** (HTTP/API mode) | Production-grade graph/API backend; serves SDXL + FLUX over an HTTP endpoint; integrates into pipelines | self-host | GPL (run as separate service, called over HTTP) |

**LICENCE GUARDRAIL (decisive):** the only weights this module may self-host for a commercial SaaS
are **FLUX.1-schnell**, **FLUX.2 Klein** (Apache-2.0) and **SDXL** (OpenRAIL++). **FLUX.1-dev /
FLUX.2-dev are NON-COMMERCIAL** — self-hosting them in production needs a paid BFL commercial licence.
Reach -dev/-pro quality via the **hosted APIs** (fal/Replicate/BFL), where the per-image price already
includes the commercial right. This is enforced in code (§4).

**Self-host vs hosted — HONEST breakeven (baked into the router §3):** a 24/7 DO GPU droplet
(L40S / RTX-6000-Ada, 48 GB) ≈ **$1.57/hr ≈ ~$1,150/mo**; hosted FLUX-schnell ≈ **$0.003/img**,
hosted FLUX-dev ≈ **$0.025/img**. Breakeven ≈ **~380k schnell-grade img/mo** or **~46k dev-grade
img/mo**. **Below that, hosted is cheaper — self-host is justified by CONTROL (brand-LoRA, privacy,
no lock-in), not low-volume cost.** Always keep premium/Indic/vector/text jobs on hosted (you cannot
match Ideogram English, GPT-Image Hindi, or Recraft SVG by self-hosting schnell/SDXL).

---

## 2. FILES TO CREATE (all NEW, under `droplet_work/creative/`)

```
droplet_work/creative/
  __init__.py
  README.md                       # what it does, cred list, how to run the offline test
  image/
    __init__.py                   # PUBLIC API: status(), providers_status(), generate(),
                                  #   generate_async(), generate_batch(), expand_batch()
    types.py                      # ImageBrief, ImageResult, BatchSpec, BatchResult dataclasses + validate/normalize
    router.py                     # job_type -> provider selection; env overrides; fallback ladder
    batch.py                      # expand_batch(BatchSpec)->[ImageBrief]; run+aggregate -> BatchResult
    budget.py                     # per-tenant spend caps + per-image ceiling + approval gate (batch-aware)
    meter.py                      # image_meter: status()+cost estimate+write usage_event (mirrors vendors/groq_meter.py)
    storage.py                    # write bytes/SVG to var/creatives/, write job/batch record JSON, index.jsonl
    audit_hook.py                 # thin wrapper -> droplet_work/audit.py if importable, else no-op
    context.py                    # pull tenant business/product/campaign data (the dropdown source) -> brief defaults
    providers/
      __init__.py                 # PROVIDER REGISTRY: id -> adapter; resolve()
      base.py                     # Provider protocol: status(), estimate_cost(), generate(), generate_async()
      fake.py                     # OFFLINE provider: deterministic in-memory PNG, zero network — powers the test
      ideogram.py                 # Ideogram v3 (dormant w/o IDEOGRAM_API_KEY)
      recraft.py                  # Recraft V4 incl. native-SVG path (dormant w/o RECRAFT_API_KEY)
      gpt_image.py                # GPT Image 2 — the Indic/Hindi route (dormant w/o OPENAI_API_KEY)
      flux_hosted.py              # FLUX via fal | replicate | bfl (IMAGE_HOSTED_PROVIDER selects)
      flux_selfhost.py            # our DO GPU box (ComfyUI HTTP) — dormant w/o IMAGE_SELFHOST_URL
    tests/
      __init__.py
      test_image_offline.py       # THE acceptance test — fully offline against `fake`
    selfhost/
      README.md                   # founder click-by-click: stand up the DO GPU droplet + ComfyUI
      docker-compose.yml          # ComfyUI serving SDXL + FLUX-schnell/Klein over HTTP (commented; deploy later)
```

**Reuse, don't reinvent** (verified against repo source):
- never-raise / no-op-when-unconfigured → `whatsapp.py` (`is_configured()`, `{"status":"not_configured"}`).
- retry/no-raise HTTP helper → `vendors/_http.py` (`request_json` returns `(ok, json, err)`).
- redact secrets in logs → `vendors/__init__.py` `redact()`.
- internal metering → usage_events (no billing API; cost = metered × rate card, `estimated:True`) →
  `vendors/groq_meter.py`.
- append-only audit, best-effort, IST timestamps, swallows all exceptions → `audit.py`.
- config: read env fresh inside functions via `os.getenv` (optional `config.get()` passthrough works
  because `config.py` merges Doppler under `os.environ` at import).

---

## 3. PUBLIC INTERFACE (the only surface the orchestrator imports)

```python
# droplet_work/creative/image/__init__.py
from .types import ImageBrief, ImageResult, BatchSpec, BatchResult

def status() -> dict: ...
    # {"status":"ready"|"not_configured", "configured_providers":[...], "selfhost":bool,
    #  "default_provider":"...", "budget":{...}}

def providers_status() -> dict: ...
    # {"ideogram":"configured"|"not_configured"|"error", "recraft":..., "gpt_image":...,
    #  "flux_hosted":..., "flux_selfhost":..., "fake":"configured"}

def generate(brief: "ImageBrief | dict", *, tenant_id: str = "", dry_run: bool = False) -> "ImageResult": ...
    #   1. normalize+validate brief (size, n, job_type, prompt non-empty, safety prefilter)
    #   2. router.select(brief) -> provider_id  (honor brief.provider override + env default)
    #   3. budget.check(tenant_id, est_cost) -> ok | over_budget | needs_approval
    #   4. if not ok: ImageResult(ok=False, status="over_budget"|"pending_approval")
    #   5. provider.generate(brief)            (fake provider when nothing configured)
    #   6. storage.save(...) ; meter.record(...) ; audit_hook.log(...)
    #   7. ImageResult(ok, status, provider, images=[paths/urls], est_cost_inr, ...)

async def generate_async(...) -> "ImageResult": ...      # async twin (FastAPI loop)

def expand_batch(spec: "BatchSpec | dict") -> list["ImageBrief"]: ...
    #   pure, no I/O: cross product of (sizes × angles × headlines) capped at spec.count,
    #   each brief tagged batch_id + variant_id + variant_label. Drives the dropdown->10-banners flow.

def generate_batch(spec: "BatchSpec | dict", *, tenant_id: str = "") -> "BatchResult": ...
    #   1. context.enrich(spec, tenant_id) -> fills brand/palette/product from stored vendor data
    #   2. briefs = expand_batch(spec)
    #   3. budget.check_batch(tenant_id, sum(est_cost))  -> gate the WHOLE batch (one decision)
    #   4. for each brief: generate(...) (sequential; bounded concurrency in async twin)
    #   5. aggregate -> BatchResult(batch_id, variants=[ImageResult...], total_cost_inr, status)
    #   6. one batch record in var/creatives/batches/<batch_id>/  (manifest of all variants)
```

### `BatchSpec` (the dropdown-driven input) — `types.py`
```python
@dataclass
class BatchSpec:
    tenant_id: str
    product_id: str = ""              # selected from the Creative Studio dropdown
    campaign_id: str = ""             # selected from the dropdown (optional)
    job_type: str = "banner"          # banner|social|product|offer|logo|vector|indic_text|bulk
    count: int = 10                   # testing-batch size (default 10 banners); capped by IMAGE_MAX_BATCH
    sizes: list[str] | None = None    # ["1080x1080","1080x1920","1200x628",...]; default per job_type
    angles: list[str] | None = None   # ["benefit","urgency","social-proof","price-drop",...] hooks
    headlines: list[str] | None = None# explicit headline texts to render (else derived from angles)
    language: str = "en"              # non-Latin -> forces gpt_image route per variant
    brand: dict | None = None         # {logo_url,palette,font,...}; auto-filled by context.enrich()
    provider: str = ""                # optional hard override
```

### `ImageBrief` (per-variant) — `types.py`
```python
@dataclass
class ImageBrief:
    prompt: str
    job_type: str = "banner"          # banner|social|product|offer|logo|vector|indic_text|bulk|draft
    headline: str = ""                # text to render IN the image (drives Ideogram/GPT-Image route)
    language: str = "en"              # en|hi|ta|...; non-Latin -> forces gpt_image
    size: str = "1024x1024"           # WxH; validated against an allowlist
    n: int = 1
    style: str = ""
    brand: dict | None = None         # {logo_url, palette:[...], font, ...} for brand lockups
    reference_image: str | None = None
    provider: str = ""                # optional router override
    tenant_id: str = ""
    output_format: str = "png"        # png|jpg|webp|svg (svg only valid for recraft vector jobs)
    seed: int | None = None
    batch_id: str = ""                # set by expand_batch; "" for one-off generate()
    variant_id: str = ""              # set by expand_batch; lets autonomous-ads track per-variant ROI
    variant_label: str = ""           # human label, e.g. "1080x1080 / urgency"
```

### `ImageResult` (per-variant output)
```python
@dataclass
class ImageResult:
    ok: bool
    status: str                       # ready|not_configured|over_budget|pending_approval|invalid|blocked|error:<...>
    provider: str
    job_id: str                       # time-sortable; names var/creatives/<job_id>/
    images: list[dict]                # [{"path":..,"url":..,"format":"png","bytes":int}]
    est_cost_inr: float               # 0.0 for fake/self-host/not_configured
    estimated: bool                   # True (rate-card based, like groq_meter)
    latency_ms: int
    batch_id: str = ""
    variant_id: str = ""
    meta: dict                        # {model,size,n,language,route_reason}
```

### `BatchResult`
```python
@dataclass
class BatchResult:
    ok: bool
    status: str                       # ready|partial|over_budget|pending_approval|not_configured|error
    batch_id: str
    tenant_id: str
    requested: int                    # count asked for
    produced: int                     # variants that succeeded
    variants: list[ImageResult]
    total_cost_inr: float
    estimated: bool
    meta: dict                        # {product_id,campaign_id,job_type,route_summary}
```

### Router logic (`router.py`) — deterministic, env-overridable
```
override order:  brief.provider  >  per-job-type env map  >  built-in default ladder
built-in ladder (only providers whose status()=="configured" are eligible; else step down -> fake):
  job_type in (logo, vector, svg)              -> recraft
  language not in LATIN  OR job_type==indic_text -> gpt_image        # ONLY Indic-capable path
  headline != "" (text-in-image, Latin)        -> ideogram
  job_type in (bulk, draft)                     -> flux_selfhost if up else flux_hosted(schnell)
  default (photoreal banner/product/offer)      -> flux_hosted(dev/pro) if up else ideogram
fallback: if chosen provider not_configured, step down the ladder; if NONE configured -> `fake`
          (pipeline always exercisable). route_reason records every hop.
```
Env overrides (all optional): `IMAGE_DEFAULT_PROVIDER`, `IMAGE_ROUTE_LOGO`, `IMAGE_ROUTE_INDIC`,
`IMAGE_ROUTE_TEXT`, `IMAGE_ROUTE_BULK`, `IMAGE_ROUTE_DEFAULT`.

---

## 4. PROVIDER ADAPTERS — interface + per-vendor request shapes

Every adapter implements the same `base.Provider` protocol and obeys the house contract: reads keys
fresh via `os.getenv`, **dormant when unconfigured**, **never raises** (mirror `vendors/_http.py`:
short timeout, retry on 429/5xx, return error string not exception), redacts secrets in logs.

```python
# providers/base.py
class Provider(Protocol):
    id: str
    def status(self) -> str: ...                                # "configured"|"not_configured"|"error"
    def estimate_cost(self, brief: ImageBrief) -> float: ...    # INR, rate-card based
    def generate(self, brief: ImageBrief) -> ImageResult: ...   # never raises
    async def generate_async(self, brief: ImageBrief) -> ImageResult: ...
```

- **`fake` (offline)** — `status()=="configured"` always; `generate()` returns a deterministic
  in-memory PNG (stdlib `zlib`+PNG chunks, filled to `size`), zero network, `est_cost_inr=0.0`.
  Powers the acceptance test and every unconfigured fallback.
- **`ideogram`** — env `IDEOGRAM_API_KEY`. `POST https://api.ideogram.ai/v1/ideogram-v3/generate`
  (version pinned in `IDEOGRAM_API_VERSION`), header `Api-Key: <key>`, body `{prompt, rendering_speed,
  aspect_ratio, magic_prompt}`. Returns image URL(s) → adapter downloads bytes → `storage.save`.
- **`recraft`** — env `RECRAFT_API_KEY`. Raster: `POST https://api.recraft.ai/v1/images/generations`
  (`style`, `size`). **Vector/SVG**: the vector model (`recraft_style:"vector_illustration"` /
  text-to-vector) returning an **`.svg`**. Adapter sets `output_format="svg"` for logo/vector jobs.
- **`gpt_image`** — env `OPENAI_API_KEY` (+ optional `OPENAI_BASE_URL`). `POST {base}/v1/images/generations`,
  model `gpt-image-2`, `{prompt, size, quality:low|medium|high, n}`. **The Indic/Hindi route.** Cost is
  token-based → estimate from `quality`+`size` rate card (`IMAGE_GPT_RATE_*` overridable).
- **`flux_hosted`** — `IMAGE_HOSTED_PROVIDER = fal | replicate | bfl`, key from the matching env
  (`FAL_KEY` | `REPLICATE_API_TOKEN` | `BFL_API_KEY`); `IMAGE_FLUX_MODEL` picks schnell|dev|pro.
  - fal: `POST https://fal.run/fal-ai/flux/<variant>`, header `Authorization: Key <FAL_KEY>`.
  - replicate: `POST https://api.replicate.com/v1/predictions`, `Authorization: Bearer <token>` (poll).
  - bfl: `POST https://api.bfl.ai/v1/flux-<variant>`, header `x-key: <BFL_API_KEY>` (poll).
  Cost from a per-variant rate card (`IMAGE_FLUX_RATE_*`).
- **`flux_selfhost`** — env `IMAGE_SELFHOST_URL` (e.g. `http://10.x.x.x:8188`). Talks to a **ComfyUI**
  HTTP/API server on a DO GPU droplet running **FLUX.1-schnell / FLUX.2 Klein (Apache-2.0)** and/or
  **SDXL (OpenRAIL++)**. `est_cost_inr=0.0` (marginal; GPU is a fixed monthly cost surfaced separately).
  Dormant when the URL is unset. `selfhost/docker-compose.yml` + `selfhost/README.md` describe standing
  it up; deployment is deferred.

> **LICENCE GUARDRAIL (enforce in `flux_selfhost.generate`):** if the configured self-host model is a
> `-dev`/`-pro` FLUX variant, require `BFL_COMMERCIAL_LICENSE=1` (founder asserts a paid BFL licence)
> else refuse with `status="blocked:noncommercial_weights"`. schnell / Klein / SDXL are always allowed.

---

## 5. ASYNC-JOB PATTERN (media gen results return automatically)

Image jobs are usually fast (1–45 s), but a 10-banner batch — or any future video/3D sibling — must
not block an HTTP request. The pattern (offline-testable, no external queue required):

- **`generate_batch()` is the SYNCHRONOUS core** (runs all variants, returns the aggregated
  `BatchResult` — this is what the offline test exercises). It is NOT itself fire-and-forget.
- **The async/fire-and-forget behaviour lives at the HTTP layer, not in the function.** The
  `POST /creatives/batch` endpoint schedules `generate_batch()` on a background task (FastAPI
  `BackgroundTasks` / an asyncio task on the existing event loop — **no Celery/Redis dependency**, to
  keep the spine light, mirroring the in-process choice in `automation-marketing.md` §1.1) and returns
  `{batch_id, status:"accepted"}` immediately. (`"accepted"` is an ENDPOINT-level status, distinct
  from the `BatchResult.status` enum.) Each variant, on completion, writes its `result.json` and
  appends to the batch manifest, so **results return to the platform automatically** via the
  filesystem store + `index.jsonl`; the UI polls `GET /creatives/batch/{batch_id}` for the aggregated
  `BatchResult`.
- **Hosted providers that are themselves async** (Replicate predictions, BFL polling) are handled
  inside the adapter: submit → poll `IMAGE_POLL_INTERVAL`/`IMAGE_POLL_TIMEOUT` → download. The adapter
  is the only place that knows a provider is async; the pipeline sees a normal `ImageResult`.
- **Status/poll surface:** `GET /creatives/batch/{batch_id}` returns
  `{status, produced, requested, variants:[...]}` so the Creative Studio UI polls until done. A
  webhook sink (`IMAGE_WEBHOOK_URL`, dormant) can POST the manifest when a batch finishes — the hook
  the autonomous-ads layer subscribes to.
- **Crash-safety:** the batch manifest is written incrementally; on restart a half-done batch is
  resumable from `var/creatives/batches/<batch_id>/manifest.jsonl` (which variants already have a
  `result.json`). No variant is generated twice (idempotent by `variant_id`).

---

## 6. SPEND / APPROVAL / AUDIT GUARDRAILS (project requirement)

**Pre-call budget gate — `budget.py` (batch-aware).** Reads caps fresh from env:
- `IMAGE_DAILY_BUDGET_INR` (default e.g. 500), `IMAGE_MONTHLY_BUDGET_INR` (default e.g. 5000).
- `IMAGE_MAX_COST_PER_IMAGE_INR` — refuse any single variant whose `estimate_cost` exceeds it.
- `IMAGE_MAX_BATCH` (default 10, hard ceiling e.g. 50) — clamps `BatchSpec.count`.
- **Batch gate:** `check_batch` sums all variant estimates and refuses the WHOLE batch if it would
  breach the remaining daily/monthly cap → `{"status":"over_budget"}`, **no external call, zero spend**,
  audited `image.refused_budget`. Spent-so-far is computed by summing `usage_events.json` rows with
  `vendor=="image"` (same store the meters read).

**Human-approval gate (optional, off by default).** `IMAGE_REQUIRE_APPROVAL=1` → paid batches are not
executed; a record is written to `var/creatives/pending/<batch_id>.json` and the result is
`{"status":"pending_approval"}`. A later `POST /creatives/batch/{batch_id}/approve` (manager role)
flips it and runs it. **`fake` / self-host (₹0) jobs skip the gate** so today's testing is never blocked.
This is the **ad-spend approval control** the brief asks for, kept dormant by default.

**Metering — `meter.py` (mirrors `vendors/groq_meter.py`).** After each *paid* generation, append a
usage event so image spend appears in the existing billing UI:
```json
{"ts":"<IST>","vendor":"image","provider":"ideogram","model":"ideogram-v3",
 "tenant_id":"<t>","batch_id":"<b>","variant_id":"<v>","job_id":"<id>",
 "n":1,"unit":"image","est_cost_inr":2.6,"estimated":true}
```
`image_meter.summarize(usage_events)` sums `vendor=="image"` rows → `{status,vendor:"image",images,
cost,estimated:true}`, same shape the other meters expose. `status()=="configured"` (internal
metering, no external billing API). FX: `IMAGE_USD_INR` (default ~87) converts USD rate cards to INR;
every cost is flagged `estimated:true` (honest — like the Groq meter).

**Audit — `audit_hook.py`.** Best-effort import of `droplet_work/audit.py`; if present, `record()`
every generation: `action="image.generate"|"image.batch"|"image.refused_budget"|"image.pending_approval"`,
`object_type="creative"`, `object_id=job_id|batch_id`, `channel="creative"`, `meta={provider,job_type,
n,est_cost_inr}`. If `audit.py` isn't importable, no-op (never breaks generation). Secrets are NEVER
logged (reuse `redact()`).

**Safety prefilter (cheap, local).** Before any paid call, a small denylist/regex blocks obviously
disallowed briefs (explicit, hateful, named-public-figure likeness/deepfake, weapons-for-sale, etc.)
→ `status="blocked"`, audited, **no spend**. First-line filter, not a substitute for provider moderation.

---

## 7. STORAGE & DATA (`storage.py`) — `var/creatives/`

```
/opt/famit-agent/var/creatives/
  <job_id>/
    brief.json          # the normalized ImageBrief (prompt, route_reason, tenant, batch/variant ids)
    result.json         # the ImageResult (provider, cost, latency, image manifest)
    0.png / 0.svg ...   # the actual asset bytes (downloaded from hosted URL or self-host)
  batches/<batch_id>/
    spec.json           # the normalized BatchSpec
    manifest.jsonl      # one line per variant (variant_id, job_id, status, cost) — append-only, resumable
    batch.json          # the aggregated BatchResult
  pending/<batch_id>.json  # only when the approval gate holds a batch
  index.jsonl           # append-only one-line-per-job index (tenant, job_type, batch_id, cost, ts)
```
- `job_id`/`batch_id` = time-sortable `YYYYMMDD-HHMMSS-<rand>` (IST). Dirs created lazily; failures
  swallowed (best-effort, like `audit.py`) and downgrade `status` to `error:storage` without raising.
- Assets stored locally on the droplet first; an optional `IMAGE_S3_*` / DO Spaces sink is a later
  follow-up (interface stub present, dormant). Listing reads `index.jsonl` newest-first with
  offset/limit, tenant-scoped — same pagination shape as `audit.tail()`.

---

## 8. HOW IT CONNECTS TO THE REST (ads / leads / CRM / voice / WhatsApp / analytics)

The Image/Banner Studio is the **asset-producing head** of the revenue loop. It does not call the
other modules directly (spine wiring is deferred) — it produces **tagged, addressable assets** that
the orchestrator routes:

- **→ Autonomous Ads.** Each batch variant carries `batch_id` + `variant_id` + `variant_label`. The
  ads module (`automation-ads.md`) launches the variants as A/B creatives at small test budgets on
  Meta/Google/YouTube, then reads back CTR/CPC/ROI/conversions **per `variant_id`** to auto-scale
  winners / pause losers / reallocate budget. The studio exposes `GET /creatives/batch/{batch_id}`
  (the variant manifest with asset URLs) as the launch payload; the ads module reports performance
  back keyed by `variant_id` (closing the loop). The `IMAGE_WEBHOOK_URL` sink fires when a batch is
  ready so ads can pick it up automatically.
- **→ Marketing / WhatsApp.** WhatsApp-creative and social variants (`job_type` sized for those
  channels) feed `whatsapp.py` (media message) and the marketing suite's social/email senders. The
  studio just stores them; the marketing drip sequencer references the asset URL.
- **→ Leads / CRM.** Ad clicks become leads; the lead record stores which `variant_id` it came from,
  so the CRM and analytics can attribute conversions to the exact creative.
- **→ Voice (caller.py / agent.py).** Out of scope for image bytes, but the SAME tenant
  business/product/campaign data (read by `context.enrich`) that drives the banner copy also drives
  the voice script — one source of truth, consistent messaging across channels.
- **→ Analytics / Billing.** Per-image `usage_events.json` rows (`vendor:"image"`) flow into the
  existing billing meter → the multi-tab billing UI; per-variant ad performance flows into the
  analytics dashboard. Spend and ROI are joinable on `variant_id`.

**`context.py`** is the bridge to the dropdown: given `tenant_id` + `product_id` + `campaign_id` it
loads the vendor's stored business profile / product catalog / campaign goals (best-effort, dormant if
the data store isn't reachable) and fills `BatchSpec.brand`, default sizes, and seed headlines/angles.
This is what makes "pick a product from a dropdown → get 10 on-brand banners" work.

---

## 9. ENDPOINTS (designed now, **wired later by the orchestrator** — DO NOT edit `caller.py`)

The module exposes plain functions; wiring is a small `add_api_route` block later. Contract fixed here:

| Method/Path | Body / Query | Returns | Notes |
|---|---|---|---|
| `POST /creatives/generate` | `ImageBrief` JSON | `ImageResult` | dormant-safe; `fake` when unconfigured |
| `POST /creatives/batch` | `BatchSpec` JSON | `{batch_id,status}` | the dropdown→batch entrypoint; async |
| `GET /creatives/batch/{batch_id}` | – | `BatchResult` + variant manifest | poll surface; ads launch payload |
| `POST /creatives/batch/{batch_id}/approve` | – | `BatchResult` | only when approval gate on; manager role |
| `GET /creatives/status` | – | `status()` dict | provider readiness + budget snapshot |
| `GET /creatives/{job_id}` | – | `result.json` | tenant-scoped |
| `GET /creatives` | `?limit&offset&batch_id` | list from `index.jsonl` | newest-first, tenant-scoped |
| `GET /creatives/{job_id}/asset/{i}` | – | image bytes | `Content-Type` per format |

All write/refuse/approve paths call `audit_hook`. Auth/tenant scoping reuses the existing `auth.py` /
middleware the orchestrator already applies (not re-implemented here).

---

## 10. REAL-vs-HYPE (honest, no overclaim)

**Real in 2026 (ship it):** accurate English headline text (Ideogram ~95%); native editable SVG
logos/icons (Recraft — real vector paths); Hindi/Devanagari headline text (GPT Image 2 — *verify live*,
strong but treat as promising-not-guaranteed); photoreal backgrounds/products/people (hosted FLUX
dev/pro); infinite cheap drafts/variations (self-host FLUX-schnell/Klein/SDXL).

**Hype / still needs a human (the approval gate exists for this):** "one prompt → finished, on-brand,
legally-cleared ad" — no. Pixel-exact brand-kit lockups (logo safe-zones, exact hex, licensed font)
are unreliable → composite the real logo/legal line in a deterministic layer. Long body copy / small
print in-image is error-prone in every model → render as a real text layer. Indic scripts other than
via GPT Image 2 → don't promise baked-in Tamil/Telugu from FLUX/Ideogram/Recraft; route to GPT Image 2
or overlay a text layer. Claims/compliance (RERA, "guaranteed returns", competitor logos, real-person
likeness) → must pass human/legal review; the safety prefilter is first-line only. Brand consistency
across a campaign → needs a trained SDXL/FLUX LoRA (a later self-host phase).

**Positioning:** a draft-and-variation banner engine with spend caps + a human approval gate, routing
each job to the one model that does it well — not a fire-and-forget art director.

---

## 11. OFFLINE ACCEPTANCE TEST (`tests/test_image_offline.py`) — ZERO external calls

```
pytest droplet_work/creative/image/tests/test_image_offline.py -q
# or:  python -m droplet_work.creative.image.tests.test_image_offline
```
Runs on any Python 3.11+; **no keys, no network**. Proves the whole pipeline via the `fake` provider.

**Assertions (each maps to a guarantee above):**
1. **Dormant-safe:** all image env unset → `status()["status"]=="not_configured"`; `providers_status()`
   shows every real provider `"not_configured"`, `fake` `"configured"`. **Nothing raises.**
2. **Single pipeline via `fake`:** `generate(ImageBrief(prompt="a blue gym banner", job_type="banner"))`
   → `ok=True`, `provider=="fake"`, writes `var/creatives/<job_id>/{brief.json,result.json,0.png}`,
   PNG passes a magic-byte check, `est_cost_inr==0.0`.
3. **Batch expansion (pure, no I/O):** `expand_batch(BatchSpec(count=10, sizes=[a,b], angles=[x,y,z]))`
   returns exactly 10 briefs, each with a unique `variant_id`, distinct `variant_label`s, capped at
   `count`.
4. **Batch run via `fake`:** `generate_batch(BatchSpec(count=6))` → `produced==6`, a
   `var/creatives/batches/<batch_id>/{spec.json,manifest.jsonl,batch.json}` exists, `total_cost_inr==0.0`.
5. **Routing (no network):** monkeypatch each real adapter `status()` to `"configured"` and assert
   `router.select`: `logo`→`recraft`; `language="hi"`/`indic_text`→`gpt_image`; `headline="50% OFF"`
   Latin→`ideogram`; `bulk` w/ self-host up→`flux_selfhost`, else `flux_hosted`; NONE configured→`fake`
   (route_reason records hops).
6. **Budget gate (single + batch):** `IMAGE_MAX_COST_PER_IMAGE_INR=0.001` + a paid provider with high
   `estimate_cost` → `generate(...)` `status=="over_budget"`, provider `generate` **never called**
   (spy); and a batch over the daily cap → `BatchResult.status=="over_budget"`, zero variants run,
   audited `image.refused_budget`.
7. **Approval gate:** `IMAGE_REQUIRE_APPROVAL=1` + a "configured" paid provider → batch
   `status=="pending_approval"`, `var/creatives/pending/<batch_id>.json` exists, provider `generate`
   NOT called.
8. **Licence guardrail:** `flux_selfhost` set to a `-dev` model w/o `BFL_COMMERCIAL_LICENSE` →
   `status=="blocked:noncommercial_weights"`; with schnell/Klein → allowed.
9. **Meter:** after a paid (mocked) generation, a `usage_events.json` row `vendor=="image"` exists and
   `image_meter.summarize([...])` sums it; `estimated is True`.
10. **Safety prefilter:** a denylisted brief → `status=="blocked"`, no spend, audited.
11. **Never-raises fuzz:** malformed inputs (empty prompt, `n=999`, `count=999`, bad size, unknown
    job_type, non-dict) → each returns an `ImageResult`/`BatchResult` with an `invalid`/clamped status,
    **no exception**.

All "configured"/"paid" cases use monkeypatch/mocks → **no real HTTP call**. The `fake` path uses no
network at all. Exit non-zero on any failure (CI-gateable).

---

## 12. EXACT CREDENTIALS / ACCOUNTS THE FOUNDER MUST PROVIDE

**The module runs and is fully testable with NONE of these (dormant-until-creds).** Paste only the
providers you want live, into `/opt/famit-agent/.env`, then `sudo systemctl restart famit-*`.

| # | What to get | Env var(s) | Where / how (founder steps) | Needed for | Cost |
|---|---|---|---|---|---|
| 1 | **Ideogram API key** | `IDEOGRAM_API_KEY` (opt `IDEOGRAM_API_VERSION`) | ideogram.ai → developer/API → create key + add credit | **English headline banners/posters** (the core) | $0.03–0.09/img |
| 2 | **Recraft API key** | `RECRAFT_API_KEY` | recraft.ai → API → generate token + credit | **Logos / editable SVG vectors** | $0.04 raster / $0.08 SVG |
| 3 | **OpenAI API key** | `OPENAI_API_KEY` (opt `OPENAI_BASE_URL`) | platform.openai.com → API keys → create + add credit | **Hindi/Indic text-in-image (GPT Image 2)** — the India edge | ~$0.006–0.21/img |
| 4 | **Hosted FLUX backend** (pick ONE) | `IMAGE_HOSTED_PROVIDER`=`fal`\|`replicate`\|`bfl` + `FAL_KEY`\|`REPLICATE_API_TOKEN`\|`BFL_API_KEY`; opt `IMAGE_FLUX_MODEL` | fal.ai \| replicate.com \| bfl.ai → API token + credit | Photoreal product/people creative | $0.02–0.10/img |
| 5 | **(Later) Self-host GPU box** | `IMAGE_SELFHOST_URL` (+ `BFL_COMMERCIAL_LICENSE=1` ONLY if running FLUX-dev) | Create a DO GPU droplet, run `selfhost/docker-compose.yml` (ComfyUI + FLUX-schnell/Klein/SDXL) on the private VPC; paste its internal URL | Brand-LoRA / privacy / no lock-in, OR raw cost at very high volume (~40k–380k img/mo). **Below that, hosted is cheaper** | DO L40S/RTX-6000-Ada ≈ **~$1,150/mo @ 24/7** |
| 6 | **Budget caps (recommended, not secret)** | `IMAGE_DAILY_BUDGET_INR`, `IMAGE_MONTHLY_BUDGET_INR`, `IMAGE_MAX_COST_PER_IMAGE_INR`, `IMAGE_MAX_BATCH`, opt `IMAGE_REQUIRE_APPROVAL=1`, `IMAGE_USD_INR` | set in `.env` | – | Spend guardrails / approval gate | free |

> **Recommended minimum to unlock most value for an Indian ad workflow:** **#1 Ideogram (English
> banners)** + **#2 Recraft (logos/SVG)** as the proven core, plus **#3 GPT Image 2** for the
> Hindi/Indic edge *after a live verification* that its Devanagari rendering holds up. Add **#4** for
> premium photoreal. Add **#5 self-host** only for brand-LoRA/privacy or true high volume — never for
> low-volume cost savings (hosted wins below ~40k img/mo).

**Sources (2026 web research):**
- https://fal.ai/learn/tools/ai-image-generators
- https://melies.co/compare/ai-image-models
- https://pricepertoken.com/image
- https://www.digitalapplied.com/blog/ai-image-generation-api-pricing-comparison-2026
- https://www.atlascloud.ai/blog/guides/best-ai-image-generation-apis-in-2026-complete-developer-guide
- https://fal.ai/models/fal-ai/recraft/v4/text-to-vector
- https://www.mindstudio.ai/blog/what-is-recraft-v4-vector-generate-svg-logos-icons-ai
- https://www.recraft.ai/docs/recraft-models/recraft-V4
- https://blog.segmind.com/ai-image-generation-api-gpt-image-2-review-real-world-use-cases-2026/  (GPT Image 2 Devanagari/Indic/CJK)
- https://www.serverman.co.uk/ai/comfyui/best-models-comfyui-2026/  (SDXL/FLUX OpenRAIL++/Apache, ComfyUI API)
- https://github.com/comfy-org/comfyui  (ComfyUI HTTP/API backend)
- https://botmonster.com/ai/how-to-set-up-flux-2-dev-locally-in-2026/  (FLUX.2 Klein Apache-2.0, VRAM)
- https://bfl.ai/licensing  (FLUX-dev non-commercial; schnell free)

---

## RED-TEAM FIXES (folded)

Adversarial review 2026-06-09. Internal reuse claims **verified against repo source** and correct:
`whatsapp.py` (the `{"status":"not_configured"}` never-raise pattern at lines 107/178/254),
`vendors/groq_meter.py` (`summarize()` shape + `estimated:True`), `vendors/_http.py`
(`request_json` returns `(ok, json, err)`), and `audit.py` all exist and match. The three core
external models were **verified live as real, active 2026 products** (not confabulated): GPT Image 2
(OpenAI, launched 2026-04-21, Devanagari/Indic confirmed), Recraft V4 Vector (Feb 2026, native SVG
confirmed), FLUX.2 Klein (Black Forest Labs, 2026-01-15). The architecture is GO-grade. The
following corrections are folded in; they refine, not replace, the design above.

**FIX 1 — AUTONOMOUS AD-SPEND IS NOT GATED BY THIS MODULE (the load-bearing safety caveat).**
The §6 budget gate caps **image-GENERATION cost only** (the $0.03–0.21 model call). It does **NOT**
cap **ad spend** — the real money the ads module (§8) puts on Meta/Google/YouTube to "launch
variants at small test budgets… auto-scale winners / reallocate budget." That is autonomous money
movement with **zero hard cap in anything this spec controls**, and the §6 approval gate is **OFF by
default and guards the CHEAP thing** (generation), leaving the EXPENSIVE thing (ad budget) ungoverned
here. **Do not read "spend gated + approval gate" as "ad spend is safe."** Hard rule for the build
agent and orchestrator: autonomous ad-spend caps (per-tenant daily/lifetime media-budget ceiling),
a kill-switch, and a real-money approval gate **MUST live in `automation-ads.md` and are explicitly
OUT OF SCOPE here.** This module only emits tagged creative assets; it never moves ad money. Until
`automation-ads.md` ships those caps, **no creative produced here may be auto-launched with a live ad
budget** — manual launch only.

**FIX 2 — FLUX.2 KLEIN IS NOT UNIFORMLY APACHE-2.0 (licensing trap — code guardrail correction).**
Verified on Hugging Face / BFL: only **FLUX.2 [klein] 4B** is **Apache-2.0** (free commercial
self-host). The **FLUX.2 [klein] 9B** variant ships under the **FLUX.2-dev NON-COMMERCIAL license** —
self-hosting it for this SaaS needs a paid BFL licence, exactly like `-dev`/`-pro`. Everywhere this
spec says "FLUX.2 Klein (Apache-2.0)" (TL;DR §1.4, §1 table, §1 guardrail, §4) it means **Klein-4B
specifically.** Update the §4 / §1 LICENCE GUARDRAIL to pin the variant: the self-host allowlist is
**FLUX.1-schnell, FLUX.2-klein-4B, SDXL** only. `flux_selfhost.generate` must treat **klein-9B (and
any `-dev`/`-pro`)** as non-commercial → require `BFL_COMMERCIAL_LICENSE=1` else
`status="blocked:noncommercial_weights"`. Test #8 must add a **klein-9B → blocked** case alongside
the existing `-dev → blocked` / `schnell → allowed` cases. (schnell Apache-2.0 and `-dev`
non-commercial both re-confirmed.)

**FIX 3 — API ToS IS A SEPARATE COMPLIANCE AXIS FROM WEIGHTS-LICENCE (and is UNVERIFIED).**
The §1/§4 licence guardrail governs **self-hosted weights**. It says nothing about **hosted-API Terms
of Service**, which is a distinct, per-provider surface that gates go-live: (a) **SaaS resale** — may
we generate creatives *on behalf of our vendors' end-customers* and bill for it? (b) **automated /
bulk** generation rights; (c) **real-person likeness, political ads, and regulated-claims** content
(Ideogram, Recraft, OpenAI/GPT Image 2, fal/Replicate/BFL each have their own usage policy — e.g.
OpenAI's image policy restricts certain likeness/political/medical content beyond what our local
§6 prefilter catches). **None of these ToS rights are verified in this spec.** Before any provider
goes live the founder/orchestrator MUST confirm, per provider, that resale + automated-ad-creative
generation is permitted. The §6 local safety prefilter is **first-line only** and is **not** a ToS
compliance layer. Add this as an explicit pre-go-live checklist item per credential in §12.

**FIX 4 — ASYNC "RESUMABLE / IDEMPOTENT" NEEDS A TRIGGER AND A LOOKUP (or soften the claim).**
§5 claims a half-done batch is "resumable from `manifest.jsonl`" and "idempotent by `variant_id`,"
but: (a) FastAPI `BackgroundTasks` dies with the process and **nothing re-triggers the batch on
restart** — "resumable" has no *who*. Either name the trigger (a startup sweep that re-enqueues
batches whose `batch.json` status is not terminal, or a cron/orchestrator resume hook) or downgrade
the wording to "**manifest is durable and inspectable; automatic resume is deferred to the
orchestrator.**" (b) "idempotent by `variant_id`" contradicts §7's **random** per-call
`job_id` — `generate()` does NOT currently check the manifest before running, so a re-run WOULD
regenerate. To honour idempotency, `generate_batch` must **skip variants whose `variant_id` already
has a terminal `result.json` in the manifest** before calling `generate()`. Pick one: implement the
skip-check, or drop the idempotency claim. Recommend the skip-check (cheap, and makes resume real).

**FIX 5 — minor, fold at build time (not verdict-affecting):**
- Pricing in §1/§12 is directional and every cost is correctly flagged `estimated:true` + FX-adjusted
  (`IMAGE_USD_INR`); treat the numbers as a rate-card seed to confirm at integration, not gospel.
  GPT Image 2 is **token-billed** (size×quality), so its per-image INR will swing more than the
  flat-rate providers — keep the `IMAGE_GPT_RATE_*` overrides and re-baseline after the first live day.
- §8 asserts the ads module reports ROI "back keyed by `variant_id`." That return path is **owned by
  `automation-ads.md`**, not guaranteed by this spec. State it as a *requirement on* that module, not
  a capability of this one.
- `context.enrich` (§8) reads a tenant data store that is **dormant/best-effort**; confirm at wiring
  time that the dropdown's `product_id`/`campaign_id` actually resolve, else batches fall back to
  generic briefs silently. Add a `route_reason`-style note when enrichment is skipped.

**Net:** **GO.** No core model is hallucinated; the dormant-until-creds + provider-agnostic +
pre-call-gate + offline-`fake`-test architecture is sound and non-breaking (creates only new files
under `creative/`, edits nothing on the spine). The corrections above are scoping/guardrail
tightenings, the most important being **FIX 1** (this module does not and must not gate autonomous
ad spend) and **FIX 2** (pin Klein-**4B**, not "Klein," in the licence guardrail).

---

## 13. BUILD ORDER (small verifiable units, no git)

1. `types.py` + `providers/base.py` + `providers/fake.py` + `__init__.py` skeleton → tests #1,#2 pass.
2. `batch.py` (`expand_batch`) → test #3.
3. `router.py` → test #5.
4. `budget.py` + `meter.py` + `audit_hook.py` → tests #6,#7,#9,#10.
5. `storage.py` + `index.jsonl`/`manifest.jsonl` + `generate_batch` aggregate → test #4.
6. Real adapters `ideogram.py`, `recraft.py`, `gpt_image.py`, `flux_hosted.py`, `flux_selfhost.py`
   (dormant; HTTP via a `_http`-style helper) → test #8 + `providers_status()` shape.
7. `context.py` (dropdown enrichment, best-effort/dormant).
8. `selfhost/` (compose + README) — docs only, no deploy.
9. Run the full offline test → green → STOP (orchestrator wires endpoints + commits).
```
```
