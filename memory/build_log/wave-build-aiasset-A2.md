# wave-build-aiasset — A2: OpenRouter provider + campaign-aware prompt pipeline

> Unit A2 of the AI Asset Service (Creative Studio generation engine). Backend lane, own dir, NO git.
> Does NOT edit caller.py / restart famit-caller/agent / deploy the panel. Ships DORMANT (AIASSET_ENABLED=0,
> no key -> MockLLM/fake). Built on top of A1 (service live + dormant, engine deployed, schema applied).

## What A2 delivers (the two-stage campaign-aware engine, spec sec 3-6 / 8-9 / 10 / 17 / 20)
Stage 1 (LLM, cheap text) builds N DIFFERENT-ANGLE creative briefs from campaign facts; Stage 2 renders each
via the reused image engine (OpenRouter). No money/Hatchet/DB-rows yet (those are U2/U6/U7) — A2 proves the
prompt -> image -> store assembly, runnable OFFLINE at zero spend and identically with a real key.

## Files added
- `droplet_work/creative/image_banner_studio/providers/openrouter.py` — the missing Provider ABC impl.
  Calls `POST {base}/api/v1/chat/completions` with `modalities:["image","text"]`; parses the image at
  `choices[0].message.images[0].image_url.url` (a base64 data-URL) -> decodes to PNG bytes -> hands
  `bytes_data` to storage.py (box fs interim). The raw data-URL is NEVER returned upward / stored in PG.
  Reads `OPNEROUTER_API_KEY` (founder typo) -> `OPENROUTER_API_KEY` -> per-tenant `..._API_KEY__<tenant_id>`.
  COST: prefers LIVE `usage.cost` (USD) from the response -> settle ACTUAL (estimated=False); rate-card
  (`AIASSET_IMAGE_RATE_USD`, default 0.039) is the PRE-flight estimate ONLY. Dormant w/o key
  (status=not_configured), NEVER raises. Cloned the b64-parse discipline from `gpt_image.py`.
- `droplet_work/creative/image_banner_studio/providers/__init__.py` — +1 registry line (`openrouter`),
  added to `REAL_PROVIDER_IDS` ladder head (Phase-1 generalist).
- `droplet_work/creative/image_banner_studio/router.py` — added `openrouter` to the universal fallback chain.
- `droplet_work/ai_asset/prompt_builder.py` — STAGE-1 (the intelligence core):
  - `CampaignContext` (sec-6 fact object, provenance-tagged) + `GenerateSpec` + `VariantBrief` dataclasses.
  - `build_variants(ctx, spec)` -> N VariantBriefs, each a DIFFERENT angle (sec 8-9 diversity; duplicate
    angles rolled to the next unused canonical angle). Each carries headline(3-8w)/subhead/goal-matched-CTA/
    visual_direction/style/platform/size/language/hypothesis/variant_label + a rich Stage-2 `render_prompt`.
  - sec-10 goal-matched CTA tables (real-estate->Book Site Visit, salon->Book Appointment, clinic->Book
    Consultation, coaching->Book Free Demo, ecommerce->Shop Now, cafe->Order Now).
  - sec-20 NO-INVENT validator (`_strip_no_invent`): fail-closed regex scrub of price/discount%/phone/RERA +
    a denylist of guarantee/award/no.1/cure/"approved-certified" claims. A claim is KEPT only if it is
    verbatim in `CampaignContext.fact_blob()`; otherwise STRIPPED with a `stripped` note (UI "missing field").
    A fully-blanked headline falls back to the grounded business name (never renders an empty/broken prompt).
  - Stage-1 LLM = `google/gemini-2.5-flash` via OpenRouter (built-in `_openrouter_text`), but the call is an
    INJECTED callable (`set_llm_fn`) so tests/dry-runs pass a MockLLM with ZERO network. Bad/again-bad JSON ->
    deterministic angle-table fallback (`DEFAULT_ANGLES`) so the pipeline never stalls.
- `droplet_work/ai_asset/pipeline.py` — wires the two stages: `campaign -> prompt_builder.build_variants ->
  image_banner_studio.router.select -> providers.resolve(pid).generate -> storage.save_job -> variants`.
  `generate(..., dry_run=False)` is GATED behind `config.enabled()` (returns `not_enabled` when OFF);
  `dry_run=True` is an offline stage-1 assembly check (no render, no spend). NEVER raises.
- `droplet_work/ai_asset/tests/test_a2_dry_run.py` (+ `tests/__init__.py`) — the MOCK-keyed dry run.

## VERIFY (all offline, ZERO real spend)
1. Dry run (`python -m ai_asset.tests.test_a2_dry_run`, PYTHONUTF8=1) -> **RESULT: PASS**. With an
   adversarial MockLLM that INJECTS "₹58L / 50% OFF / RERA Approved / Call 98765 43210" into a context with
   NO such facts: 4 DISTINCT angles, full variant DNA on each, goal-matched CTA "Book Site Visit", and the
   no-invent validator STRIPPED all four invented facts (`['phone:98765 43210','price:50% OFF','price:₹58L',
   'rera:RERA Approved Project']`); the fully-invented "RERA Approved Project" headline fell back to the
   grounded business name. POSITIVE control: a price ("₹58L") that IS verbatim in context was KEPT. spent==0.
2. openrouter provider (mocked HTTP, fake key): status configured; decodes a base64 data-URL -> 69-byte PNG
   (`bytes_data` present for storage, data-URL not stored); reads `usage.cost`=$0.039 -> ACTUAL ₹3.393
   (×87 FX, estimated=False); router selects `openrouter` for a default banner.
3. Full pipeline (fake provider, AIASSET_ENABLED=1): 3/3 variants rendered + stored to disk (0.png each),
   status ready. Gated path: AIASSET_ENABLED unset -> `generate` returns `not_enabled` (live byte-identical).
   No-key dry_run -> deterministic fallback still yields distinct grounded variants (never stalls).

## Dormancy / safety posture (unchanged from A1)
- AIASSET_ENABLED=0 default -> the live generate path is gated off. No key -> providers not_configured +
  fake keeps the pipeline exercisable. No LLM key -> MockLLM/fallback. ZERO network on the dormant path.
- All new code is import-safe and NEVER raises. No edits to caller.py/agent.py; no service restart.

## DEPLOY NOTE (for the box, when activating)
Add the OpenRouter key to the service `.env` on the box (value lives in `caps/.env.local` as
`OPNEROUTER_API_KEY`). The adapter + stage-1 LLM both read it (founder typo first). Until then everything
runs offline at ₹0 via fake/MockLLM. The real-banner proof (Wave E) flips AIASSET_ENABLED + the key.

## Sample dry-run output (the assembled prompt + variant structure)
Stage-1 LLM prompt (head): "You are a senior performance-marketing ad creative strategist. Build 4 DIFFERENT
static ad-banner variants ... CAMPAIGN FACTS (the ONLY source of truth ...): {business_name, industry,
product, location, audience, ...}  RULES: ... NEVER invent price/discount/location/phone/RERA/guarantees..."
Variant example (post no-invent):
  [Variant 2: Price Drop] angle=price-drop size=1200x628 style=bold
   headline 'Now From Only'  (was "Now From ₹58L Only" -> ₹58L stripped)
   subhead  'Limited booking' (was "Limited 50% OFF booking" -> 50% OFF stripped)
   cta 'Book Site Visit'  stripped ['price:50% OFF','price:₹58L']
   render_prompt 'Bold ad banner for a real-estate business (Skyline Residences) — ... Headline text in
   image: "Now From Only". ... Call-to-action button: "Book Site Visit". ... no distorted text, correct spelling'
