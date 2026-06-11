# AI Asset Service — Provider Abstraction + OpenRouter Image-Gen Research

> READ-ONLY DESIGN (design wave). No app code, no deploy. Conforms to
> `CREATIVE_STUDIO_MASTER_PROMPT.md` (42 DNA sections + the architecture decision:
> AI Asset Service = a dedicated coarse SERVICE, model-agnostic, OpenRouter = the
> FIRST provider impl, NOT the architecture).
> Author: provider-abstraction + OpenRouter research agent · 2026-06-11.

---

## 0. TL;DR (the load-bearing answers)

1. **Can OpenRouter generate images? YES.** It is a real, first-class capability (not text-only).
2. **How:** the SAME chat endpoint `POST https://openrouter.ai/api/v1/chat/completions`
   with a top-level `"modalities": ["image", "text"]` field. The image comes back as a
   **base64 data-URL** at `choices[0].message.images[0].image_url.url`
   (`data:image/png;base64,...`). No separate `/images/generations` route.
3. **Recommended image model (Phase 1):** `google/gemini-2.5-flash-image` (a.k.a.
   "Nano Banana") — best price/quality, native edit + multi-turn, ~$0.039/image. Fallback
   inside OpenRouter: `black-forest-labs/flux.2-pro` / `flux.2-flex`; premium-text route:
   `openai/gpt-5-image`.
4. **Two-stage pipeline:** LLM (`google/gemini-2.5-flash` over OpenRouter, same key) builds
   the rich prompt from campaign data → image model renders. One key, one vendor, two calls.
5. **It fits the EXISTING abstraction.** There is already a complete `Provider` protocol +
   registry + router at `droplet_work/creative/image_banner_studio/`. OpenRouter is ONE NEW
   adapter file + ONE registry line — do NOT invent a new abstraction.
6. **The env var name is misspelled:** `OPNEROUTER_API_KEY` (typo "OPNE", not "OPEN").
   Value is present `[FOUND]`. The adapter MUST read this exact misspelled name (with an
   `OPENROUTER_API_KEY` alias fallback so a future fix doesn't break it).

---

## 1. The OpenRouter key (env)

- File: `C:\Users\kunal\Desktop\caps\.env.local`
- **Var name: `OPNEROUTER_API_KEY`** — note the founder's typo ("OPNE…" not "OPEN…"). **[FOUND]** (value present; not printed).
- ⚠️ IMPLEMENTER ACTION: the adapter reads the key via
  `os.getenv("OPNEROUTER_API_KEY") or os.getenv("OPENROUTER_API_KEY")` so it works today and
  survives a later rename. Do NOT hard-code only the correct spelling — the live file has the typo.
- This is a single shared OpenRouter key (Phase-1 testing). For multi-tenant, layer the
  media_gen per-tenant key convention `<ENV>__<tenant_id>` on top (see §8) before any
  tenant-billable production use.

---

## 2. Does OpenRouter do image generation? YES — exact mechanics

OpenRouter exposes image generation through its **unified Chat Completions endpoint**, not a
dedicated image route. You opt into image output with the `modalities` field.

### 2.1 Endpoint + headers

```
POST https://openrouter.ai/api/v1/chat/completions
Authorization: Bearer <OPNEROUTER_API_KEY>
Content-Type: application/json
# optional attribution headers (recommended, not required):
HTTP-Referer: https://panel.famit.in
X-Title: Famit Creative Studio
```

### 2.2 EXACT request body (text → image)

```json
{
  "model": "google/gemini-2.5-flash-image",
  "messages": [
    { "role": "user", "content": "<the rich prompt built in stage 1>" }
  ],
  "modalities": ["image", "text"],
  "image_config": {
    "aspect_ratio": "1:1",
    "image_size": "2K"
  }
}
```

- `modalities`: `["image","text"]` for models that emit both; `["image"]` for image-only models.
- `image_config` (optional, model-dependent) common fields observed in the docs:
  `aspect_ratio` (`"1:1" | "16:9" | "9:16" | "4:5" | "2:3" | "3:2" | …`),
  `image_size` (`"0.5K" | "1K" | "2K" | "4K"`), `strength` (0.0–1.0, image-to-image),
  `rgb_colors`, `background_rgb_color`, `text_layout` (`[{text, bbox}]`), `style`.
  Treat `image_config` as best-effort: unknown fields are ignored by models that don't support
  them, so it never hard-fails — but DON'T rely on `text_layout` to render exact pricing/RERA
  text (master-spec §20 NEVER-invent rule: the safe text path is gpt_image/ideogram or
  client-side text compositing, not model-rendered legal claims).

### 2.3 EXACT response shape — where the image bytes live

```json
{
  "id": "gen-...",
  "choices": [
    {
      "message": {
        "role": "assistant",
        "content": "Here is your banner.",
        "images": [
          {
            "type": "image_url",
            "image_url": { "url": "data:image/png;base64,iVBORw0KGgoAAAANS..." }
          }
        ]
      }
    }
  ],
  "usage": { "prompt_tokens": ..., "completion_tokens": ..., "total_tokens": ... }
}
```

- **The image is at `choices[0].message.images[i].image_url.url`** as a base64 **data-URL**,
  PNG by default. Multiple images → multiple entries in the `images` array.
- Parse: strip the `data:image/png;base64,` prefix → `base64.b64decode(...)` → bytes →
  land in storage (§7). This is the SAME `bytes_data` shape the existing `gpt_image.py`
  adapter already produces (`{"bytes_data": b, "format": "png", "bytes": len(b)}`), so it
  drops straight into the existing store/meter/audit pipeline.

### 2.4 Image EDITING / image-to-image / variation (one mechanism)

Same endpoint. Put the input image into the `messages` content as an `image_url` part
(base64 data-URL or https URL) ALONGSIDE the edit instruction, keep `modalities:["image","text"]`,
and (optionally) set `image_config.strength`:

```json
{
  "model": "google/gemini-2.5-flash-image",
  "messages": [{
    "role": "user",
    "content": [
      { "type": "text", "text": "Make it premium, remove the price, add the logo top-left." },
      { "type": "image_url", "image_url": { "url": "data:image/png;base64,<input>" } }
    ]
  }],
  "modalities": ["image", "text"],
  "image_config": { "strength": 0.6 }
}
```

- This single mechanism covers the master-spec's **edit** ("make it premium", "less text",
  "remove price", "add logo", "change CTA"), **variation** ("5 more like this", "more like the
  winner"), and the **upload-a-reference** flow ("create this kind of banner" + uploaded image).
- Multi-turn: Gemini Flash Image keeps prior images in the conversation, enabling iterative
  refinement (master-spec §26 versioning — every edit = a NEW version, original kept).

---

## 3. OpenRouter image-capable models + pricing (Phase-1 menu)

Discover programmatically: `GET https://openrouter.ai/api/v1/models?output_modalities=image`
(or the Models page filtered by output modality). Snapshot (Jun 2026):

| Model slug | Price | Notes / use |
|---|---|---|
| `google/gemini-2.5-flash-image` ("Nano Banana") | $0.30/M in · $2.50/M out · **~$0.039/image** (1290 out-tokens) | ⭐ DEFAULT. Best price/quality, native edit + multi-turn, controllable aspect ratio. |
| `google/gemini-3.1-flash-image-preview` | $0.50/M in · $3/M out | Newer, extended aspect ratios. Optional premium default once stable. |
| `google/gemini-3-pro-image-preview` | $2/M in · $12/M out | Highest Google quality; reserve for hero/premium-brand jobs. |
| `black-forest-labs/flux.2-pro` | $0.015/MP in · $0.03 first MP + $0.015/MP | ⭐ Photoreal banner/product fallback (no in-image text). |
| `black-forest-labs/flux.2-flex` | $0.06/MP in+out | Flexible quality/cost knob. |
| `black-forest-labs/flux.2-klein-4b` | $0.014 first MP + $0.001/MP | Cheapest bulk/draft route. |
| `black-forest-labs/flux.2-max` | $0.03/MP in · $0.07 first MP + $0.03/MP | Top Flux quality. |
| `openai/gpt-5-image` | $10/M in · $10/M out | Strong text-in-image (Indic/headline legibility) via OpenRouter. |
| `openai/gpt-5-image-mini` | $2.50/M in · $2/M out | Cheaper GPT-image text route. |
| `bytedance-seed/seedream-4.5` | **$0.04/output image** | Flat-per-image alternative. |
| `sourceful/riverflow-v2-standard-preview`, Recraft V3/V4, `microsoft/mai-image-2.5`, `x-ai/grok-imagine-image-*` | varies | Additional options; some good for logo/vector (Recraft). |

⚠️ **Pricing discrepancy to verify live:** Gemini-2.5-flash-image lists $2.50/M output tokens on
its model page, yet the per-image figure ($0.039) implies ~$30/M for image output tokens (image
tokens billed differently from text tokens). **Do NOT hard-code a per-image cost** — read the
actual `usage` block per response and/or the live model rate-card, and apply the existing
`_common.usd_to_inr()` FX (default 87) → INR for the wallet hold. The estimate is a rate-card
seed (like `groq_meter`); settle on the real `usage` after the call.

### Limits / operational notes
- Rate limits: per-key + per-model; the shared `vendors/_http.py` already retries 429/5xx.
- Provider routing: OpenRouter may route a model across upstream providers; pin with
  `provider: {"order":[...], "allow_fallbacks": true}` if a specific upstream is required.
- Free tiers (`:free` slugs) exist for Gemini image preview but are heavily rate-limited and
  unstable — fine for smoke tests, NOT for the live pipeline. Use the paid slug in production.
- Image output is **synchronous** in the chat response (no webhook/poll for OpenRouter image),
  which differs from the async video providers — so OpenRouter image can run inline OR be wrapped
  in a Hatchet job for batch/queue UX (master-spec §36 "liquid wave" loading) without needing a
  callback.

---

## 4. Verdict: OpenRouter vs direct providers

**OpenRouter is the right Phase-1 default** and is genuinely strong for image-gen — it gives one
key + one HTTP shape across Gemini, Flux.2, GPT-image, Seedream, Recraft. It is NOT weak/absent.

Keep direct providers behind the SAME abstraction for when they win on price/control/SLA:

| Need | Direct provider (same `Provider` interface) | Why over OpenRouter |
|---|---|---|
| Cheapest high-volume photoreal | **Flux via Replicate / fal / BFL direct** | per-MP billing, self-host option (`flux_selfhost` already exists) |
| Crispest in-image headline text (Indic) | **OpenAI Images direct** (`gpt_image.py` exists) or **Ideogram** (`ideogram.py` exists) | dedicated text-rendering quality; master-spec §20 text-accuracy |
| Logos / vectors / SVG | **Recraft direct** (`recraft.py` exists) | true vector output |
| Brand-trained styles, fine control | **Leonardo / Stability** | elements, presets, control |
| Lowest latency / no markup | **Google AI Studio (Gemini direct)** | skip OpenRouter's ~5% markup |

The architecture makes this a config choice, not a rewrite: every one of the above is just
another adapter behind `Provider`, selected per-job-type/per-tenant via the existing `router.py`
ladder + env. **OpenRouter now, direct providers when a model earns it.**

---

## 5. The two-stage pipeline (campaign-aware → image)

Master-spec KEY FLOW: `Campaign → AI Prompt Builder (rich prompt) → Image Model → Asset Library`.

```
                         ┌─────────────────────────── AI Asset Service ───────────────────────────┐
 Campaign data ──▶ context.enrich() ──▶ STAGE 1: Prompt Builder (LLM) ──▶ STAGE 2: Image Render
 (product, price,        (pull brand,        google/gemini-2.5-flash         google/gemini-2.5-flash-image
  location, offer,        logo, palette,      via OpenRouter (text)            via OpenRouter (image)
  audience, goal,         do-not-use,         → per-variant rich prompt        → base64 PNG → bytes
  platform, lead-stage)   best style)         + headline/CTA/angle/size        → store → meter → audit
                                              (5 marketing angles, §8-9)       → ImageResult
                         └────────────────────────────────────────────────────────────────────────┘
```

### Stage 1 — Prompt Builder (LLM)
- **Model:** `google/gemini-2.5-flash` (OpenRouter, SAME key). $0.30/M in · $2.50/M out — cheap,
  fast, strong structured/JSON output, multimodal (can read a reference/brand image).
  Cheaper floor: `google/gemini-2.5-flash-lite` ($0.10/$0.40). Premium-quality copy:
  `anthropic/claude-haiku-4.5` or `anthropic/claude-sonnet` for high-value brands.
- **Input:** enriched campaign context (business name, product, price→"From ₹58L", location,
  offer, audience, goal→CTA, USP→headline, tone→style, platform→size, lead-stage, brand kit,
  do-not-use list, approved/rejected history).
- **Output (structured JSON, one object per variant, ~5 variants = 5 angles):**
  ```json
  {
    "variants": [
      { "angle": "price", "headline": "From ₹58L", "subheadline": "...", "cta": "Book Site Visit",
        "visual_direction": "premium evening skyline, warm lighting, real-estate hero",
        "platform": "meta_feed", "size": "1200x628", "language": "en",
        "image_prompt": "<the rich, model-ready prompt — composition, style, palette, NO invented claims>",
        "hypothesis": "price-led CTR beats benefit for cold audience" },
      { "angle": "location", ... }, { "angle": "trust", ... }, ...
    ]
  }
  ```
- **Guardrail (master-spec §20, CRITICAL):** the system prompt HARD-FORBIDS inventing
  price/discount/RERA/phone/guarantees/testimonials/awards. If a fact isn't in the campaign data,
  the builder omits it or flags `needs_input`, never fabricates. This is enforced at the
  prompt-builder layer (cheap, auditable) BEFORE any image spend.

### Stage 2 — Image Render
- Takes each variant's `image_prompt` + `size`/`aspect_ratio` → `Provider.generate(ImageBrief)`
  → the OpenRouter adapter (§2) → base64 → bytes → store/meter/audit.
- The router (`router.py`) still chooses the BEST model per job-type: in-image Indic text →
  gpt_image/ideogram; photoreal → flux/gemini; logo/vector → recraft. OpenRouter-Gemini is the
  new general default; existing routes are preserved.

### Recommended model pairing given the provided OpenRouter key
| Stage | Default | Premium | Cheap floor |
|---|---|---|---|
| 1 — Prompt/Copy (text) | `google/gemini-2.5-flash` | `anthropic/claude-haiku-4.5` | `google/gemini-2.5-flash-lite` |
| 2 — Image render | `google/gemini-2.5-flash-image` | `google/gemini-3-pro-image-preview` / `openai/gpt-5-image` (text-heavy) | `black-forest-labs/flux.2-klein-4b` (bulk/draft) |

---

## 6. The Provider abstraction (REUSE the existing one — do not reinvent)

⭐ **There is ALREADY a complete provider abstraction** at
`droplet_work/creative/image_banner_studio/`. It is exactly the model-swap-without-UI-change
abstraction the master spec asks for. The job is to ADD an OpenRouter adapter, not design a new
interface. The mandate ("models swap without UI changes") is ALREADY met by this design.

### 6.1 The `Provider` protocol (existing — `providers/base.py`)
```python
@runtime_checkable
class Provider(Protocol):
    id: str
    def status(self) -> str: ...                          # 'configured'|'not_configured'|'error'
    def estimate_cost(self, brief: ImageBrief) -> float: ...   # INR, rate-card, never raises
    def generate(self, brief: ImageBrief) -> ImageResult: ...  # NEVER raises; non-ok result on fail
    async def generate_async(self, brief: ImageBrief) -> ImageResult: ...
```
- House contract (`providers/base.py` docstring): read keys fresh via `os.getenv` each call
  (Doppler/.env live-reload); **dormant when unconfigured** (`status()=="not_configured"`,
  `generate()` returns a non-ok `ImageResult`, NEVER raises, NEVER calls out); short timeout +
  429/5xx retry via the shared `_common.request_json`; redact secrets in logs.
- Data types (`types.py`): `ImageBrief` (prompt/job_type/headline/language/size/n/style/brand/
  reference_image/provider/tenant_id/output_format/seed/batch_id/variant_id/variant_label) and
  `ImageResult` (ok/status/provider/job_id/images[{path,url,format,bytes,bytes_data}]/
  est_cost_inr/estimated/latency_ms/meta).
- Registry (`providers/__init__.py`): `REGISTRY` id→class, `resolve(id)` (cached, unknown→fake),
  `all_status()`. Existing adapters: `fake, ideogram, recraft, gpt_image, flux_hosted,
  flux_selfhost`. **No `openrouter` yet — that is the gap.**
- Router (`router.py`): override > per-job-type env > built-in ladder; only `configured`
  providers eligible; falls to `fake` so the pipeline is always exercisable; records `route_reason`.

### 6.2 What to ADD (the only new code at the provider layer)
1. **`providers/openrouter.py`** — `OpenRouterProvider(id="openrouter")` implementing the protocol:
   - `status()`: `configured` iff `os.getenv("OPNEROUTER_API_KEY") or os.getenv("OPENROUTER_API_KEY")`.
   - `generate(brief)`: build the chat body (§2.2 / §2.4 for edit when `brief.reference_image`),
     POST via `_common.request_json`, parse `choices[0].message.images[*].image_url.url`,
     base64-decode → `{"bytes_data": b, "format": "png", "bytes": len(b)}`, set
     `est_cost_inr` from `usage`-derived rate-card via `_common.usd_to_inr`, set `meta`
     (`model, size, n, route_reason, usage`). NEVER raises. Honor `IMAGE_OPENROUTER_MODEL`
     env (default `google/gemini-2.5-flash-image`).
   - `estimate_cost(brief)`: rate-card seed × n → INR (overridable
     `IMAGE_OPENROUTER_RATE_USD`, default ~0.039).
   - `generate_async`: async twin (the others delegate to sync; keep parity).
2. **`providers/__init__.py`** — one import + one `REGISTRY["openrouter"]` line; add to
   `REAL_PROVIDER_IDS` ladder (slot it high as the new general default).
3. **`router.py`** — optional: make `IMAGE_DEFAULT_PROVIDER=openrouter` the default ladder head;
   no structural change needed (env already supported).
4. **(separate file) Stage-1 prompt builder** — a `prompt_builder.py` (in the asset-service
   layer, NOT a provider) that calls the OpenRouter TEXT model and emits the per-variant briefs.
   This is new but small; it feeds normalized `ImageBrief`s into the existing pipeline.

### 6.3 The 6 abstraction capabilities the spec asks for — mapping
| Spec capability | How it's satisfied (no UI change) |
|---|---|
| **generate** | `Provider.generate(ImageBrief)` (exists) |
| **edit** | `ImageBrief.reference_image` + edit instruction → §2.4 single mechanism (OpenRouter Gemini supports natively; adapter passes the image in `messages`) |
| **variation** | same as edit with a "more like this" instruction / new seed; batch.py expands |
| **upscale** | new optional `job_type:"upscale"` routed to an upscale-capable model (Recraft/Flux) — additive, no interface change |
| **model registry** | `providers/__init__.py` REGISTRY + `resolve()` (exists) |
| **per-tenant model selection** | `ImageBrief.provider` override + per-job-type env + (new) a per-tenant `IMAGE_DEFAULT_PROVIDER`/model column in `ai_asset_*` settings, read by `router.py` |
| **cost reporting** | `estimate_cost()` + `ImageResult.est_cost_inr/estimated` + live `usage` settle → wallet (exists; OpenRouter adapter fills it from `usage`) |

---

## 7. Storage abstraction (DO Spaces vs interim box FS)

⭐ **Already abstracted.** Two layers exist:
- `creative/image_banner_studio/storage.py` — the studio-local artifact writer (box filesystem,
  `var/creatives/<job_id>/`), used for testing TODAY.
- `media_gen/spaces.py` — the shared engine-owned **DO Spaces** writer (boto3 S3-compatible),
  **dormant when `SPACES_*` env unset**, used by all media types for production relocation.

**Design = one `AssetStore` seam, two backends, env-switched:**
```
put(tenant_id, job_id, variant_id, bytes, fmt) -> {backend, path|url, bytes}
```
- **Interim (now):** box FS under `var/creatives/<tenant>/<job_id>/<variant>.png`. Zero creds.
- **Production:** DO Spaces (S3) via `media_gen/spaces.py` once founder provides
  `SPACES_KEY/SECRET/BUCKET/REGION/ENDPOINT`. Same `put()` signature → the asset record stores a
  Spaces URL (or a signed URL) instead of a local path.
- Selection: if `SPACES_*` configured → Spaces, else FS. Per-tenant prefix isolates objects;
  the `ai_asset_*` FORCE-RLS schema owns the metadata row (preview/campaign/type/platform/size/
  angle/headline/CTA/status/score/cost/date/used-in/performance per master-spec §30).
- ⚠️ The base64 data-URL from OpenRouter must be decoded to bytes and written through THIS seam
  — never store the raw multi-MB data-URL in Postgres; store bytes in the object store + a URL/path
  + small metadata in PG.

---

## 8. Security / multi-tenant hooks (reuse the spine — do not re-derive)

- **Per-tenant API keys:** media_gen convention `<ENV>__<tenant_id>` (e.g.
  `OPNEROUTER_API_KEY__<tenant_id>`) overrides the shared key when present. The shared key is
  Phase-1 only; gate tenant-billable production on per-tenant keys + AUP/likeness screen
  BEFORE spend (shared-key abuse protection, per media_gen RTF-1).
- **Wallet (F4):** reserve a hold BEFORE a batch (estimate × n, USD→INR-paise CEIL via the
  `IMAGE_USD_INR` FX seam, never under-reserve), settle the ACTUAL from `usage`, release unused on
  failure. Tag `hold_backend` ("wallet"|"json") on the job so settle/release hit the SAME backend
  (the silent-no-op seam-bug lesson in `memory/brain/media-gen.md`). `wallet.reserve(tenant_id,
  amount_minor:int, resource_type, resource_id, idem_key, currency='INR', actor) -> hold_id|None`;
  flow `idem_key` (the real no-double-spend primitive).
- **Audit:** `audit.record(actor, action, object_type, object_id, channel, tenant_id, actor_role,
  meta)` on generate/edit/approve/spend — immutable PG `events` ledger when present.
- **RLS:** `ai_asset_*` schema FORCE-RLS, tenant from TOKEN not body (caller.py `resolve_tenant`
  pattern); the router that mounts these endpoints overwrites `brief["tenant_id"]=token_tenant`
  (the media_gen `build_router` security fix — body tenant must never win).
- **Hatchet (F3):** wrap batch image jobs as durable Hatchet jobs for the queue/"liquid-wave"
  loading UX; OpenRouter image is synchronous so no webhook needed, but Hatchet gives
  retry/idempotency/queue depth for multi-variant batches.

---

## 9. Recommended config defaults (env — for the implementer)

```
# OpenRouter (NOTE the misspelled var name in the live .env.local)
OPNEROUTER_API_KEY=<set>            # adapter also accepts OPENROUTER_API_KEY as alias
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1     # optional override
IMAGE_OPENROUTER_MODEL=google/gemini-2.5-flash-image # stage-2 default
IMAGE_OPENROUTER_RATE_USD=0.039     # rate-card seed/image; live usage settles actual
PROMPT_BUILDER_MODEL=google/gemini-2.5-flash         # stage-1 default
IMAGE_DEFAULT_PROVIDER=openrouter   # make OpenRouter the ladder head
IMAGE_USD_INR=87                    # FX (existing _common default)
# storage
SPACES_KEY= / SPACES_SECRET= / SPACES_BUCKET= / SPACES_REGION= / SPACES_ENDPOINT=  # unset -> box FS
```

---

## 10. Sources

- OpenRouter — Image Generation guide: https://openrouter.ai/docs/guides/overview/multimodal/image-generation
- OpenRouter — Multimodal overview: https://openrouter.ai/docs/guides/overview/multimodal/overview
- OpenRouter — Image Models collection (pricing): https://openrouter.ai/collections/image-models
- OpenRouter — Nano Banana / Gemini 2.5 Flash Image (model + pricing): https://openrouter.ai/google/gemini-2.5-flash-image
- OpenRouter — Gemini 2.5 Flash Image API quickstart: https://openrouter.ai/google/gemini-2.5-flash-image/api
- OpenRouter — GPT-5 Image: https://openrouter.ai/openai/gpt-5-image
- OpenRouter — Gemini 2.5 Flash (text, stage-1): https://openrouter.ai/google/gemini-2.5-flash
- OpenRouter — Gemini 2.5 Flash Lite: https://openrouter.ai/google/gemini-2.5-flash-lite
- OpenRouter — API reference: https://openrouter.ai/docs/api/reference/overview
- Google Developers Blog — Gemini 2.5 Flash Image: https://developers.googleblog.com/en/introducing-gemini-2-5-flash-image/
- HyperAI — Gemini Nano-Banana base64 image workflow: https://hyper.ai/en/stories/1cb45a4542e13a7f795071dd6ff7befe
- Tenten — Gemini 2.5 Flash Image via OpenRouter: https://developer.tenten.co/unlocking-advanced-image-generation-with-gemini-25-flash-image-through-openrouter
- n8n — Nano Banana product mockups (base64 decode flow): https://n8n.io/workflows/8194-generate-product-mockups-with-nano-banana-gemini-25-flash-image/
- Pricing context: https://costgoat.com/pricing/openrouter , https://www.teamday.ai/blog/top-ai-models-openrouter-2026

### EXISTING CODE THIS DESIGN REUSES (no reinvention)
- `droplet_work/creative/image_banner_studio/providers/base.py` — Provider protocol (the abstraction)
- `droplet_work/creative/image_banner_studio/providers/__init__.py` — registry (`REGISTRY`/`resolve`)
- `droplet_work/creative/image_banner_studio/router.py` — job_type→provider ladder
- `droplet_work/creative/image_banner_studio/types.py` — ImageBrief/ImageResult/BatchSpec
- `droplet_work/creative/image_banner_studio/providers/_common.py` — http/redact/usd_to_inr/download
- `droplet_work/creative/image_banner_studio/providers/gpt_image.py` — closest template (b64 parse)
- `droplet_work/media_gen/spaces.py` — DO Spaces (S3) writer (production storage backend)
- `droplet_work/media_gen/video/cost.py` — wallet hold pattern (USD→INR-paise, hold_backend tag)
- `memory/brain/media-gen.md` — the silent-no-op seam-bug lesson + wallet signatures
```
