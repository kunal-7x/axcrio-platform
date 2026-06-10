# AD-CREATIVE IMAGE GENERATION — Execution-Ready Design Spec

> **For the build agent:** implement this verbatim. This is a NEW automation module for the
> Famit AI Revenue OS — the "image" pillar of replacing the marketing/ad-creative team. It
> generates ad banners, social cards, product creatives, and brand assets (logos/vectors) from
> a text brief. It is **provider-agnostic** and **DORMANT-UNTIL-CREDS**: with no keys pasted it
> is a graceful no-op that returns `{"status":"not_configured"}` and never raises — exactly like
> the existing `whatsapp.py` module.
>
> **Hard rules from the project brief (do not violate):**
> - NEW code ONLY under `droplet_work/automation/`. **Do NOT edit `caller.py` / `agent.py`** —
>   final wiring into the backend spine is deferred to the orchestrator.
> - NO git operations (the orchestrator commits).
> - Every integration is **provider-agnostic + dormant-until-creds** (no-op + `{status:"not_configured"}`).
> - **Verifiable offline**: the acceptance test makes **zero live external calls**. A fake/local
>   provider proves the whole pipeline (validation → routing → spend guard → audit → storage)
>   without spending a paisa or needing a key.
> - Cost-optimized; self-host on DigitalOcean where it wins; production-grade, scalable.

---

## 0. TL;DR — the decisions that define this module (read before coding)

1. **Route by job, not by a single "best" model.** Ad creative is three different problems and no
   single model wins all three. The router picks a provider tier from the *brief's job type*:
   - **`banner` / `social` / `product` photoreal** → text-heavy composited cards. Default
     **Ideogram 3.0** (~95% Latin text-in-image accuracy) or **FLUX** (photoreal, cheapest).
   - **`logo` / `icon` / `vector`** → **Recraft V4** is the *only* model that emits **native SVG**
     (real paths, editable, infinitely scalable) — decisive for brand assets.
   - **`indic_text`** (Hindi/Devanagari/Tamil/etc. baked INTO the image) → **GPT Image 2** is, per
     2026 reporting, the **strongest** model at rendering Indic scripts legibly at headline sizes,
     where FLUX/Ideogram/Recraft/SDXL still tend to produce "confident squiggles" for Devanagari.
     **This is a major India-specific edge — but it is single-sourced (one vendor blog); the build
     agent / founder MUST verify it against OpenAI's primary image-API docs and a quick live test
     before betting spend on it.** The route is env-overridable, so the architecture survives if the
     ranking shifts. (See §1 evidence + caveat.)
   - **`bulk` / `draft` at very high volume, OR brand-LoRA / privacy** → **self-hosted FLUX.1
     [schnell]** (Apache-2.0, free commercial) or **SDXL** on a DigitalOcean GPU droplet — ~₹0
     *marginal* cost per image, but a ~$1,150/mo fixed GPU bill, so it only pays off at scale or
     for the control it buys (see decision #2). Low volume → use hosted, not this.

2. **The "self-host where it wins" line is licence-driven, and self-host's real win is NOT
   low-volume cost — it is control.** Be honest about the economics (see the breakeven math below):
   a 24/7 DO GPU droplet is ~**$1,150/month** (L40S/RTX-6000-Ada ≈ $1.57/hr), while hosted
   FLUX-schnell is ~**$0.003/image**. Breakeven vs schnell ≈ **~380,000 images/month**; vs hosted
   FLUX-*dev* ($0.025) ≈ **~46,000/month**. **Below that, hosted APIs are cheaper — self-host is a
   money loser purely on cost.** So self-hosting is justified by **(a) brand-LoRA / style control,
   (b) data privacy / no creative leaving your infra, (c) no per-image vendor lock-in, and (d) raw
   cost only at very high sustained volume (tens to hundreds of thousands of images/month).** Only
   the *commercially-free* weights may be self-hosted:
   - **FLUX.1 [schnell]** — **Apache-2.0** → free for commercial self-host. Fast, good enough for
     drafts/bulk. **This is the default self-host model.**
   - **SDXL** — OpenRAIL-M, commercial use permitted → free self-host, runs on an 8 GB GPU, the
     LoRA/brand-style king. **The primary reason to self-host: train a brand-consistency LoRA.**
   - **FLUX.1 [dev] / FLUX.2 [dev]** — weights are **NON-COMMERCIAL**. Self-hosting them for a
     commercial SaaS **requires a paid BFL commercial licence** (Builder/Platform/Professional
     tiers, §4). **Do NOT self-host -dev for production without that licence.** Until then, reach
     -dev/-pro quality only via the **hosted APIs** (fal/Replicate/BFL), where the per-image price
     already includes the commercial right.
   This module therefore treats *hosted FLUX-dev/pro* and *self-hosted FLUX-schnell/SDXL* as two
   distinct providers with different cost and licence profiles.

3. **Every provider is an adapter behind one stable interface.** `generate(brief) -> Result`.
   Adapters: `ideogram`, `recraft`, `gpt_image`, `flux_hosted` (fal/Replicate/BFL — one adapter,
   `IMAGE_HOSTED_PROVIDER` selects the backend), `flux_selfhost` (our DO GPU box), and a built-in
   `fake` provider for the offline test. Adding a provider = one file + one registry line. Swapping
   vendors = one env var. **No business logic knows a vendor's name.**

4. **Dormant-until-creds, byte-for-byte like `whatsapp.py`.** No keys → `status()=="not_configured"`,
   `generate()` returns `{"ok":False,"status":"not_configured",...}`, logs one line, **never raises,
   never dials**. The pipeline (validate → guard → audit → store) still runs end-to-end against the
   `fake` provider so the module is fully testable with zero credentials.

5. **Spend is gated BEFORE the call, metered AFTER, and every generation is audited.** A per-tenant
   **daily/monthly budget cap** + a **per-image price ceiling** are checked *before* any paid call;
   a generation over budget is refused with `{"status":"over_budget"}` (no spend). After a paid
   call, the estimated cost is written to the same `usage_events.json` stream the existing
   `vendors/*_meter.py` adapters use, so image spend shows up in the billing UI alongside
   Groq/ElevenLabs/Vobiz. Optional **human-approval gate** holds paid generations in a `pending`
   queue until a manager approves (off by default; flip one env var).

6. **Real-vs-hype, stated honestly (§9).** AI cannot yet produce a *finished, on-brand, legally
   cleared* ad with one prompt. What it reliably does in 2026: photoreal backgrounds, accurate
   English headline text (Ideogram), native editable vector logos (Recraft), Hindi headline text
   (GPT Image 2 only), and infinite cheap drafts (self-host FLUX). What still needs a human:
   pixel-exact brand kit lockups, final legal/claims review, and high-stakes hero creative. The
   module is positioned as a **draft/variation engine with a human approval gate**, not a
   fire-and-forget designer. We do not overclaim.

---

## 1. EVIDENCE — chosen tools + why (2026 web research, sources cited)

> Researched June 2026. Where a search summary contradicted primary docs (e.g. a summary claimed
> "FLUX has no LoRA support" — false; FLUX LoRAs are ubiquitous), the **primary source wins** and
> the claim is dropped. Licence facts are taken from BFL's own licensing page.

| Need | Chosen tool | Why (evidence) | Price (2026) | Licence |
|---|---|---|---|---|
| **English/Latin text in banner** | **Ideogram 3.0** | ~90–95% text-in-image accuracy vs ~30–40% for Midjourney; built for posters/packaging/ads | $0.03 (std) – $0.09 (quality) /img | Hosted API (commercial OK) |
| **Logos / icons / editable vector** | **Recraft V4** | *Only* model emitting **native SVG** (real paths, layers, clean geometry); #1 on HF logo benchmark | $0.04 raster / $0.08 SVG | Hosted API (commercial OK) |
| **Hindi / Devanagari / Indic text in image** | **GPT Image 2** | *Reportedly* the strongest 2026 model at rendering Devanagari/CJK/Arabic legibly at headline sizes, where others tend to fail. **Single-sourced — verify vs OpenAI primary docs + a live test before betting spend** | ~$0.006 (low) / ~$0.053 (med) / ~$0.211 (high) per 1024² | Hosted API (commercial OK), token-billed |
| **Photoreal product / people / backgrounds (hosted)** | **FLUX.2 [dev] / FLUX 1.1 [pro]** via fal/Replicate | Best photorealism + prompt adherence; hosted price *includes* commercial right | dev $0.025 (fal) / $0.030 (Replicate); pro $0.05 | Hosted = commercial OK |
| **High-volume bulk / brand-LoRA (SELF-HOST)** | **FLUX.1 [schnell]** | Apache-2.0 → free commercial; fast; "good enough" for drafts. **Self-host wins only at ~40k–380k img/mo OR for LoRA/privacy/no-lock-in — NOT for low-volume cost (hosted is cheaper below that)** | ~$0.003/img hosted, ~₹0 self-host *marginal* (but ~$1,150/mo GPU fixed) | **Apache-2.0 (free commercial)** |
| **Brand-style LoRA / 8 GB GPU self-host** | **SDXL** | OpenRAIL-M commercial; runs on 8 GB (RTX 3060-class); the LoRA/customization king | free self-host | OpenRAIL-M (commercial OK) |
| **Serverless GPU broker (no key per model)** | **fal.ai** (primary), **Replicate** (alt) | fal = predictable **per-image/per-MP** pricing; Replicate = per-GPU-second (good for custom models). Aggregators ~30–50% cheaper than direct | fal A100 $0.99/h, H100 $1.89/h; FLUX schnell $0.003/MP | pay-per-use |

**Self-host vs hosted, the decision rule baked into the router (§3) — with HONEST breakeven math:**
- A 24/7 DO GPU droplet (L40S / RTX 6000 Ada, 48 GB) ≈ **$1.57/hr ≈ $1,150/month**. Hosted
  FLUX-schnell ≈ **$0.003/image**; hosted FLUX-dev ≈ **$0.025/image**.
- **Cost breakeven:** ~$1,150/mo ÷ $0.003 ≈ **~380,000 schnell-grade images/month**; ÷ $0.025 ≈
  **~46,000 dev-grade images/month**. **Below these volumes, hosted is cheaper — do NOT self-host
  for cost.** (You can shrink the GPU bill by autoscaling/spinning the box down when idle, which
  lowers the crossover, but it never approaches a few thousand/month.)
- **Self-host because of CONTROL, not low-volume cost:** brand-LoRA / style consistency (SDXL),
  data privacy (creative never leaves your infra), no per-image vendor lock-in, and raw cost only
  at the very-high sustained volumes above.
- **Always keep premium/Indic/vector/text jobs on the hosted APIs** — you cannot match Ideogram's
  English text, GPT-Image's Hindi, or Recraft's native SVG by self-hosting schnell/SDXL.
- The module ships **both paths** and routes per-job; the founder flips `IMAGE_SELFHOST_URL` on
  when the GPU box exists (for LoRA/privacy or true high volume). Until then everything routes to
  hosted/`fake`. The default `IMAGE_SELFHOST_THRESHOLD_IMG_MONTH` advisory is set conservatively
  (e.g. 40,000), not a few thousand.

**Sources:**
- https://melies.co/compare/ai-image-models
- https://pricepertoken.com/image
- https://apiscout.dev/guides/flux-vs-ideogram-vs-recraft-image-gen-api-2026
- https://www.digitalapplied.com/blog/ai-image-generation-api-pricing-comparison-2026
- https://fal.ai/learn/tools/ai-image-generators
- https://zsky.ai/blog/flux-vs-stable-diffusion-2026
- https://www.glmimages.com/blog/flux-vs-sdxl-comparison-2026
- https://bfl.ai/licensing
- https://huggingface.co/black-forest-labs/FLUX.1-dev
- https://bfl.ai/legal/non-commercial-license-terms
- https://www.mindstudio.ai/blog/what-is-recraft-v4-vector-generate-svg-logos-icons-ai
- https://replicate.com/blog/recraft-v4
- https://ideogram.ai/models/3.0/
- https://www.mindstudio.ai/blog/what-is-ideogram-v3
- https://blog.segmind.com/ai-image-generation-api-gpt-image-2-review-real-world-use-cases-2026/  (GPT Image 2 Indic/CJK/Devanagari rendering)
- https://wavespeed.ai/blog/posts/gpt-image-2-pricing-2026/
- https://developers.openai.com/api/docs/pricing
- https://costbench.com/software/ai-ml-platforms/fal/
- https://replicate.com/blog (per-second pricing model)
- https://www.koyeb.com/blog/best-serverless-gpu-platforms-for-ai-apps-and-inference-in-2026

---

## 2. FILES TO CREATE (all NEW, under `droplet_work/automation/`)

```
C:\Users\kunal\Desktop\caps\droplet_work\automation\
  __init__.py
  README.md                     # what it does, cred list, how to run the offline test
  image\
    __init__.py                 # public API: generate(), generate_async(), status(), providers_status()
    types.py                    # ImageBrief, ImageResult dataclasses + normalize/validate helpers
    router.py                   # job-type -> provider selection; honors env overrides
    budget.py                   # per-tenant spend caps + per-image ceiling + approval gate
    meter.py                    # image_meter: status() + cost estimate + write usage_event (mirrors vendors/*_meter.py)
    storage.py                  # write image bytes/SVG to var/creatives/, write job record JSON
    audit_hook.py               # thin wrapper that calls droplet_work/audit.py if importable, else no-op
    providers\
      __init__.py               # PROVIDER REGISTRY: id -> adapter module; resolve()
      base.py                   # Provider protocol: status(), generate(brief)->ImageResult, estimate_cost()
      fake.py                   # OFFLINE provider: deterministic 1x1 PNG, zero network — powers the test
      ideogram.py               # Ideogram 3.0 adapter (dormant w/o IDEOGRAM_API_KEY)
      recraft.py                # Recraft V4 adapter incl. SVG path (dormant w/o RECRAFT_API_KEY)
      gpt_image.py              # GPT Image 2 adapter — the Indic/Hindi path (dormant w/o OPENAI_API_KEY)
      flux_hosted.py            # FLUX via fal | replicate | bfl (IMAGE_HOSTED_PROVIDER selects)
      flux_selfhost.py          # our DO GPU box (ComfyUI/SD-API HTTP) — dormant w/o IMAGE_SELFHOST_URL
  tests\
    __init__.py
    test_image_offline.py       # THE acceptance test — runs fully offline against `fake`
  selfhost\
    README.md                   # how to stand up the DO GPU droplet (founder HOWTO, click-by-click)
    docker-compose.yml          # ComfyUI/SDXL+FLUX-schnell HTTP server (commented; deploy later)
```

Mirror conventions already in the repo (verified against source):
- **never-raise / no-op-when-unconfigured** → `whatsapp.py` (`is_configured()`, `{"status":"not_configured"}`).
- **vendor adapter shape** (`status()->configured|not_configured|error`, redact secrets, short
  timeout + backoff, never raise) → `vendors/__init__.py` docstring, `vendors/_http.py`.
- **internal metering → usage_events** (no billing API; cost = metered × rate card, `estimated:True`)
  → `vendors/groq_meter.py`.
- **append-only audit, best-effort, IST timestamps, swallow all exceptions** → `audit.py`.
- **optional config resolver** → `config.py` (`get()/require()`); use `config.get()` so Doppler
  works later, but fall back to `os.getenv` if `config` isn't importable in this package.

---

## 3. PUBLIC INTERFACE (the only surface `caller.py` will later import)

```python
# droplet_work/automation/image/__init__.py
from .types import ImageBrief, ImageResult

def status() -> dict: ...
    # {"status":"ready"|"not_configured", "configured_providers":[...],
    #  "selfhost": bool, "default_provider": "...", "budget": {...}}

def providers_status() -> dict: ...
    # {"ideogram":"configured"|"not_configured"|"error", "recraft":..., "gpt_image":...,
    #  "flux_hosted":..., "flux_selfhost":..., "fake":"configured"}

def generate(brief: "ImageBrief | dict", *, tenant_id: str = "",
             dry_run: bool = False) -> "ImageResult": ...
    #   1. normalize+validate brief (size, count, job_type, prompt non-empty, safety prefilter)
    #   2. router.select(brief) -> provider_id (honor brief.provider override + env default)
    #   3. budget.check(tenant_id, est_cost) -> ok | over_budget | needs_approval
    #   4. if not ok: return ImageResult(ok=False, status="over_budget"|"pending_approval")
    #   5. provider.generate(brief)  (fake provider if nothing configured & not dry_run-blocked)
    #   6. storage.save(...) ; meter.record(...) ; audit_hook.log(...)
    #   7. return ImageResult(ok, status, provider, images=[paths/urls], est_cost_inr, ...)

async def generate_async(...) -> "ImageResult": ...   # async twin (FastAPI event loop)
```

### `ImageBrief` (input contract) — `types.py`
```python
@dataclass
class ImageBrief:
    prompt: str                       # the creative brief / scene description
    job_type: str = "banner"          # banner|social|product|logo|vector|indic_text|bulk|draft
    headline: str = ""                # text to render IN the image (drives Ideogram/GPT-Image route)
    language: str = "en"              # en|hi|ta|... ; non-Latin -> forces gpt_image route
    size: str = "1024x1024"           # WxH; validated against an allowlist
    n: int = 1                        # 1..MAX_BATCH (default cap 4)
    style: str = ""                   # optional style/preset tag
    brand: dict | None = None         # {logo_url, palette:[...], font, ...} for brand lockups
    reference_image: str | None = None# url/path for edit/variation jobs
    provider: str = ""                # optional hard override of the router
    tenant_id: str = ""               # data owner (also passed as kwarg)
    output_format: str = "png"        # png|jpg|webp|svg (svg only valid for recraft vector jobs)
    seed: int | None = None           # reproducibility
```

### `ImageResult` (output contract)
```python
@dataclass
class ImageResult:
    ok: bool
    status: str                       # ready|not_configured|over_budget|pending_approval|
                                      #   invalid|blocked|error:<...>
    provider: str
    job_id: str                       # ulid-ish; names the var/creatives/<job_id>/ dir
    images: list[dict]                # [{"path":..., "url":..., "format":"png", "bytes": int}]
    est_cost_inr: float               # 0.0 for fake/self-host/not_configured
    estimated: bool                   # True (rate-card based, like groq_meter)
    latency_ms: int
    meta: dict                        # {model, size, n, language, route_reason}
```

### Router logic (`router.py`) — deterministic, env-overridable
```
override order:  brief.provider  >  per-job-type env map  >  built-in default ladder
built-in ladder (only providers whose status()=="configured" are eligible; else -> fake):
  job_type == logo|vector|svg            -> recraft
  language not in LATIN  OR job_type==indic_text
                                          -> gpt_image          # ONLY Indic-capable path
  headline != "" (text-in-image, Latin)  -> ideogram
  job_type in (bulk, draft)              -> flux_selfhost if up else flux_hosted(schnell)
  default (photoreal banner/product)     -> flux_hosted(dev) if up else ideogram
fallback: if the chosen provider is not_configured, step down the ladder; if NONE configured,
          use `fake` (so the pipeline is always exercisable). route_reason records every hop.
```

Env overrides (all optional): `IMAGE_DEFAULT_PROVIDER`, `IMAGE_ROUTE_LOGO`, `IMAGE_ROUTE_INDIC`,
`IMAGE_ROUTE_TEXT`, `IMAGE_ROUTE_BULK`, `IMAGE_ROUTE_DEFAULT`.

---

## 4. PROVIDER ADAPTERS — interface + per-vendor request shapes

Every adapter implements the same `base.Provider` protocol and obeys the project rules: reads keys
via `config.get()`/`os.getenv`, **dormant when unconfigured**, **never raises** (mirror
`vendors/_http.py`: short timeout, retry on 429/5xx, return error string not exception), redacts
secrets in logs.

```python
# providers/base.py
class Provider(Protocol):
    id: str
    def status(self) -> str: ...                 # "configured"|"not_configured"|"error"
    def estimate_cost(self, brief: ImageBrief) -> float: ...   # INR, rate-card based
    def generate(self, brief: ImageBrief) -> ImageResult: ...  # never raises
    async def generate_async(self, brief: ImageBrief) -> ImageResult: ...
```

**`fake` (offline)** — `status()=="configured"` always; `generate()` returns a deterministic 1×1
(or `size`-filled) PNG synthesized in-memory (stdlib `zlib`+PNG chunks or a checked-in tiny PNG),
zero network, `est_cost_inr=0.0`. Powers the acceptance test and every unconfigured fallback.

**`ideogram`** — env `IDEOGRAM_API_KEY`. `POST https://api.ideogram.ai/v1/ideogram-v3/generate`
(version pinned in `IDEOGRAM_API_VERSION`), header `Api-Key: <key>`, body `{prompt, rendering_speed,
aspect_ratio, magic_prompt}`. Returns image URL(s) → adapter downloads bytes → `storage.save`.

**`recraft`** — env `RECRAFT_API_KEY`. Raster: `POST .../v1/images/generations` (`style`,
`size`). **Vector/SVG**: the SVG endpoint (`recraft_style:"vector_illustration"`/`text-to-vector`)
returning an **`.svg`**. Adapter sets `output_format="svg"` for logo/vector jobs.

**`gpt_image`** — env `OPENAI_API_KEY` (+ optional `OPENAI_BASE_URL` for Azure/proxy).
`POST {base}/v1/images/generations`, model `gpt-image-2`, `{prompt, size, quality:low|medium|high,
n}`. **The Indic/Hindi route** — selected whenever `language` is non-Latin or `job_type=="indic_text"`.
Returns b64/URL. Cost is token-based → adapter estimates from `quality`+`size` using a rate card
(low≈$0.006, med≈$0.053, high≈$0.211 per 1024²; `IMAGE_GPT_RATE_*` overridable).

**`flux_hosted`** — `IMAGE_HOSTED_PROVIDER = fal | replicate | bfl`, key from the matching env
(`FAL_KEY` | `REPLICATE_API_TOKEN` | `BFL_API_KEY`). `IMAGE_FLUX_MODEL` picks schnell|dev|pro.
- fal: `POST https://fal.run/fal-ai/flux/<variant>` header `Authorization: Key <FAL_KEY>`.
- replicate: `POST https://api.replicate.com/v1/predictions` header `Authorization: Bearer <token>`
  (poll until `succeeded`).
- bfl: `POST https://api.bfl.ai/v1/flux-<variant>` header `x-key: <BFL_API_KEY>` (poll result).
Cost from a per-variant rate card (`IMAGE_FLUX_RATE_*`).

**`flux_selfhost`** — env `IMAGE_SELFHOST_URL` (e.g. `http://10.x.x.x:8188`). Talks to a ComfyUI /
SD-WebUI-API / vLLM-image HTTP server on a DO GPU droplet running **FLUX.1-schnell (Apache-2.0)**
and/or **SDXL (OpenRAIL)** — the only commercially-free self-host weights. `est_cost_inr=0.0`
(marginal; GPU is a fixed monthly cost surfaced separately). Dormant when the URL is unset.
**`docker-compose.yml` + `selfhost/README.md`** describe standing it up; deployment is deferred.

> **LICENCE GUARDRAIL (enforce in `flux_selfhost.generate`):** if the configured self-host model is
> a `-dev`/`-pro` FLUX variant, require `BFL_COMMERCIAL_LICENSE=1` (founder asserts they hold a paid
> BFL licence) else refuse with `status="blocked:noncommercial_weights"`. schnell/SDXL are always
> allowed. This keeps the product legally clean by default.

---

## 5. SPEND / APPROVAL / AUDIT GUARDRAILS (§ project requirement)

**Pre-call budget gate — `budget.py`.** Reads caps from env (per-tenant overridable later via a
small JSON in `var/`):
- `IMAGE_DAILY_BUDGET_INR` (default e.g. 500), `IMAGE_MONTHLY_BUDGET_INR` (default e.g. 5000).
- `IMAGE_MAX_COST_PER_IMAGE_INR` — refuse any single job whose `estimate_cost` exceeds it (stops a
  fat `high`/`pro`/`n=8` request from surprising the bill).
- `IMAGE_MAX_BATCH` (default 4). Counts today's/this-month's spend by summing `usage_events.json`
  rows with `vendor=="image"` (same store the meters use). Over cap → `{"status":"over_budget"}`,
  **no external call, zero spend**, audited as `image.refused_budget`.

**Human-approval gate (optional, off by default).** `IMAGE_REQUIRE_APPROVAL=1` → paid jobs are not
executed; instead a record is written to `var/creatives/pending/<job_id>.json` and the result is
`{"status":"pending_approval"}`. A later (deferred) `POST /creatives/{job_id}/approve` endpoint (or
manual approve helper) flips it and runs it. **`fake`/self-host (₹0) jobs skip the gate.** This is
the "spend approval" control the brief asks for, kept dormant so nothing blocks today's testing.

**Metering — `meter.py` (mirrors `vendors/groq_meter.py`).** After a *paid* generation, append a
usage event so image spend appears in the existing billing UI:
```json
{"ts":"<IST>","vendor":"image","provider":"ideogram","model":"ideogram-v3",
 "tenant_id":"<t>","job_id":"<id>","n":2,"unit":"image","est_cost_inr":5.0,"estimated":true}
```
`image_meter.summarize(usage_events)` sums `vendor=="image"` rows → `{status, vendor:"image",
images, cost, estimated:true}`, same shape the other meters expose. `status()=="configured"`
(internal metering, no external billing API). FX: `IMAGE_USD_INR` (default ~87) converts USD rate
cards to INR; every cost is flagged `estimated:true` (honest — like the Groq meter).

**Audit — `audit_hook.py`.** Best-effort import of `droplet_work/audit.py`; if present, `record()`
every generation: `action="image.generate"|"image.refused_budget"|"image.pending_approval"`,
`object_type="creative"`, `object_id=job_id`, `channel="image"`, `meta={provider, job_type, n,
est_cost_inr}`. If `audit.py` isn't importable in this context, no-op (never breaks generation).
Secrets are NEVER logged (reuse the `redact()` pattern from `vendors/__init__.py`).

**Safety prefilter (cheap, local).** Before any paid call, a small denylist/regex blocks obviously
disallowed briefs (explicit, hateful, real-person-likeness/deepfake of a named public figure,
weapons-for-sale, etc.) → `status="blocked"`, audited, **no spend**. This is a first-line filter,
not a substitute for the provider's own moderation.

---

## 6. STORAGE & DATA (`storage.py`) — `var/creatives/`

```
/opt/famit-agent/var/creatives/
  <job_id>/
    brief.json          # the normalized ImageBrief (prompt, route_reason, tenant)
    result.json         # the ImageResult (provider, cost, latency, image manifest)
    0.png / 0.svg ...   # the actual asset bytes (downloaded from hosted URL or self-host)
  pending/<job_id>.json # only when approval gate holds a job
  index.jsonl           # append-only one-line-per-job index (tenant, job_type, cost, ts) for listing
```
- `job_id` = time-sortable id (`YYYYMMDD-HHMMSS-<rand>` IST). Dir is created lazily; failures are
  swallowed (best-effort, like `audit.py`) and downgrade `status` to `error:storage` without raising.
- Assets are stored locally on the droplet first; an optional `IMAGE_S3_*` / DO Spaces sink is a
  **later follow-up** (interface stub present, dormant). Listing reads `index.jsonl` newest-first
  with offset/limit, tenant-scoped — same pagination shape as `audit.tail()`.

---

## 7. ENDPOINTS (designed now, **wired later by the orchestrator** — DO NOT edit `caller.py`)

These are the FastAPI routes the orchestrator will mount. Documented here so the contract is fixed;
the module exposes plain functions so wiring is a 5-line `include`/`add_api_route` later.

| Method/Path | Body / Query | Returns | Notes |
|---|---|---|---|
| `POST /creatives/generate` | `ImageBrief` JSON | `ImageResult` | dormant-safe; `fake` when unconfigured |
| `GET /creatives/status` | – | `status()` dict | provider readiness + budget snapshot |
| `GET /creatives/{job_id}` | – | `result.json` | tenant-scoped |
| `GET /creatives` | `?limit&offset` | list from `index.jsonl` | newest-first, tenant-scoped |
| `GET /creatives/{job_id}/asset/{i}` | – | image bytes | `Content-Type` per format |
| `POST /creatives/{job_id}/approve` | – | `ImageResult` | only when approval gate on; manager role |

All write/refuse/approve paths call `audit_hook`. Auth/tenant scoping reuses the existing
`auth.py`/middleware the orchestrator already applies to other routes (not re-implemented here).

---

## 8. EXACT CREDENTIALS / ACCOUNTS THE FOUNDER MUST PROVIDE

**The module runs and is fully testable with NONE of these (dormant-until-creds).** Paste only the
providers you want live. Add to `/opt/famit-agent/.env` then `sudo systemctl restart famit-*`.

| # | What to get | Env var(s) | Where / how (founder steps) | Needed for | Cost |
|---|---|---|---|---|---|
| 1 | **OpenAI API key** | `OPENAI_API_KEY` (opt `OPENAI_BASE_URL`) | platform.openai.com → API keys → create; add a few $ credit | **Hindi/Indic text-in-image (GPT Image 2)** — the India edge | usage-based, ~$0.006–0.21/img |
| 2 | **Ideogram API key** | `IDEOGRAM_API_KEY` (opt `IDEOGRAM_API_VERSION`) | ideogram.ai → API/developer → create key + add credit | English headline banners/posters | $0.03–0.09/img |
| 3 | **Recraft API key** | `RECRAFT_API_KEY` | recraft.ai → API → generate token + credit | **Logos / editable SVG vectors** | $0.04 raster / $0.08 SVG |
| 4 | **Hosted FLUX backend** (pick ONE) | `IMAGE_HOSTED_PROVIDER` = `fal`\|`replicate`\|`bfl` **and** `FAL_KEY` \| `REPLICATE_API_TOKEN` \| `BFL_API_KEY`; opt `IMAGE_FLUX_MODEL` | fal.ai \| replicate.com \| bfl.ai → API token + credit | Photoreal product/people creative (commercial right included in price) | $0.025–0.05/img |
| 5 | **(Later) Self-host GPU box** | `IMAGE_SELFHOST_URL` (+ `BFL_COMMERCIAL_LICENSE=1` ONLY if running FLUX-dev) | Create a DO GPU droplet, run the provided `selfhost/docker-compose.yml` (FLUX.1-schnell/SDXL) on the private VPC; paste its internal URL | Brand-LoRA / privacy / no-lock-in, OR raw cost only at very high volume (~40k–380k img/mo). **Below that, hosted is cheaper — don't provision this for low volume** | DO L40S/RTX-6000-Ada ≈ $1.57/hr ≈ **~$1,150/mo at 24/7** |
| 6 | **Budget caps (recommended, not secret)** | `IMAGE_DAILY_BUDGET_INR`, `IMAGE_MONTHLY_BUDGET_INR`, `IMAGE_MAX_COST_PER_IMAGE_INR`, `IMAGE_MAX_BATCH`, opt `IMAGE_REQUIRE_APPROVAL=1`, `IMAGE_USD_INR` | set in `.env` | – | Spend guardrails / approval gate | free |

> **DO NOT self-host FLUX.1-dev / FLUX.2-dev for production without a paid BFL commercial licence**
> (Builder / Platform / Professional tiers at bfl.ai/licensing — pricing is contact-sales/self-serve).
> The free self-host path is **FLUX.1-schnell (Apache-2.0)** and **SDXL (OpenRAIL-M)**; those need
> no licence. This is enforced in code (§4 licence guardrail).

**Recommended minimum to unlock the most value for an Indian ad workflow:** **#2 (Ideogram for
English banners)** + **#3 (Recraft for logos)** as the safe, well-proven core, plus **#1 (GPT
Image 2)** specifically for the Hindi/Indic-text edge — *after* a quick live verification that its
Devanagari rendering holds up for your creatives (the claim is single-sourced; §1 caveat). Add #4
for premium photoreal. **Add #5 (self-host) only for brand-LoRA/privacy or true high volume
(~40k+ img/mo) — never for low-volume cost savings, where it loses to the hosted APIs.**

---

## 9. REAL-vs-HYPE (honest, no overclaim)

**Real in 2026 (ship it):**
- Accurate **English** headline text inside an image (Ideogram ~95%).
- **Native editable SVG logos/icons** (Recraft) — genuinely new; real vector paths, not a traced raster.
- **Hindi/Devanagari headline text** inside an image — GPT Image 2 is *reported* to be the only
  model that does this legibly; **treat as promising-but-unverified until a live test confirms it**,
  not a hard guarantee.
- Photoreal backgrounds/products/people at hosted-API quality (FLUX dev/pro).
- **Infinite cheap drafts/variations** via self-hosted FLUX-schnell/SDXL.

**Hype / still needs a human (the module's approval gate exists for exactly this):**
- "One prompt → finished, on-brand, legally-cleared ad." No. Pixel-exact brand-kit lockups (logo
  safe-zones, exact hex, licensed font) are unreliable; treat AI output as a **draft/variation**,
  composite the real logo/legal line in a deterministic layer (or human pass).
- **Long body copy / small print** in-image is still error-prone in every model — render it as a
  real text layer over the image, don't ask the model to bake a paragraph.
- **Indic SCRIPTS other than via GPT Image 2** — do not promise Tamil/Telugu/Bengali baked-in text
  from FLUX/Ideogram/Recraft; route those to GPT Image 2 or overlay a text layer.
- **Claims/compliance** (RERA for real-estate creative, "guaranteed returns", competitor logos,
  real-person likeness) — must pass human/legal review; the safety prefilter is first-line only.
- **Brand consistency across a campaign** — needs a trained SDXL/FLUX LoRA or strong reference
  conditioning; not free out-of-the-box. (LoRA training = a later phase, the SDXL self-host path.)

Positioning: a **draft-and-variation creative engine with spend caps and a human approval gate**,
routing each job to the one model that actually does it well — not a fire-and-forget art director.

---

## 10. OFFLINE ACCEPTANCE TEST (`tests/test_image_offline.py`) — ZERO external calls

Run on the droplet venv or any Python 3.11+; **no keys, no network**. Proves the whole pipeline
deterministically via the `fake` provider.

```
pytest droplet_work/automation/tests/test_image_offline.py -q
# or:  python -m droplet_work.automation.tests.test_image_offline
```

**Assertions (each maps to a guarantee above):**
1. **Dormant-safe:** with all image env vars unset, `image.status()["status"]=="not_configured"`
   and `providers_status()` shows every real provider `"not_configured"`, `fake` `"configured"`.
   **Nothing raises.**
2. **Pipeline works via `fake`:** `generate(ImageBrief(prompt="a blue gym banner", job_type="banner"))`
   returns `ok=True`, `provider=="fake"`, writes `var/creatives/<job_id>/{brief.json,result.json,0.png}`,
   and the PNG is a valid PNG (magic-byte check), `est_cost_inr==0.0`.
3. **Routing is correct (no network):** monkeypatch each real adapter's `status()` to `"configured"`
   and assert `router.select`:
   - `job_type="logo"` → `recraft`;
   - `language="hi"` (or `job_type="indic_text"`) → `gpt_image`;
   - `headline="50% OFF"` Latin → `ideogram`;
   - `job_type="bulk"` with self-host up → `flux_selfhost`, else `flux_hosted`.
   - With NONE configured → falls back to `fake` (route_reason records the hops).
4. **Budget gate:** set `IMAGE_MAX_COST_PER_IMAGE_INR=0.001`, force a paid provider's `estimate_cost`
   high → `generate(...)` returns `status=="over_budget"`, **no provider call made** (assert via a
   spy that the adapter's `generate` was never invoked), audited `image.refused_budget`.
5. **Approval gate:** `IMAGE_REQUIRE_APPROVAL=1` + a "configured" paid provider → `status=="pending_approval"`,
   a `var/creatives/pending/<job_id>.json` exists, provider `generate` NOT called.
6. **Licence guardrail:** `flux_selfhost` configured to a `-dev` model w/o `BFL_COMMERCIAL_LICENSE`
   → `status=="blocked:noncommercial_weights"`; with schnell → allowed.
7. **Meter:** after a paid (mocked) generation, an `usage_events.json` row with `vendor=="image"`
   exists and `image_meter.summarize([...])` sums it; `estimated is True`.
8. **Safety prefilter:** a denylisted brief → `status=="blocked"`, no spend, audited.
9. **Never-raises fuzz:** feed malformed briefs (empty prompt, `n=999`, bad size, unknown job_type,
   non-dict) → each returns an `ImageResult` with an `invalid`/clamped status, **no exception**.

All "configured"/"paid" cases use **monkeypatch/mocks** so the test makes **no real HTTP call**.
The `fake` provider path uses no network at all. Exit non-zero on any failure (CI-gateable).

---

## 11. BUILD ORDER (for the implementing agent — small verifiable units, no git)

1. `types.py` + `providers/base.py` + `providers/fake.py` + `__init__.py` skeleton → test #1,#2 pass.
2. `router.py` → test #3.
3. `budget.py` + `meter.py` + `audit_hook.py` → tests #4,#5,#7,#8.
4. Real adapters `ideogram.py`, `recraft.py`, `gpt_image.py`, `flux_hosted.py`, `flux_selfhost.py`
   (dormant; HTTP via a local `_http`-style helper) → test #6, and `providers_status()` shape.
5. `storage.py` finalize + `index.jsonl` listing.
6. `selfhost/` (compose + README) — docs only, no deploy.
7. Run the full offline test → green → STOP (orchestrator wires endpoints + commits).

Reuse, don't reinvent: copy the retry/no-raise HTTP helper pattern from `vendors/_http.py`; the
`redact()` from `vendors/__init__.py`; the meter shape from `vendors/groq_meter.py`; the audit
`record()` contract from `audit.py`; the dormant `is_configured()/not_configured` pattern from
`whatsapp.py`. Read secrets via `config.get()` with an `os.getenv` fallback.
