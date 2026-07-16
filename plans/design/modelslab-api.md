# ModelsLab Image API — Exact Contract (researched June 2026)

Goal: wire ModelsLab as the Creative Studio image provider (Stage-2 `provider.generate`)
to replace Pollinations. This doc is the EXACT API contract the adapter must implement.

Key (free-tier) lives in `C:\Users\kunal\Desktop\caps\.env.local` as `MODELSLAB_API_KEY`.
Free tier -> charge ₹0 (provider id goes in `FREE_PROVIDER_IDS`). Test EXACTLY 1 image.

---

## TL;DR — what the adapter does

1. POST a single JSON body (key inside the body) to the **realtime** text2img endpoint.
2. Realtime is **synchronous** (~2-3s) and returns the image URL(s) immediately in
   `output[]`. Use this as the primary path — simplest, no polling, low quota burn.
3. If (and only if) the response comes back `status: "processing"`, fall back to
   polling the `fetch_result` URL until `status: "success"`. (The realtime endpoint
   usually returns success directly; the community endpoint is the one that queues.)

---

## 1. Endpoint (use REALTIME — sync, fast, no model_id needed)

```
POST https://modelslab.com/api/v6/realtime/text2img
Content-Type: application/json
```

- Realtime = optimized built-in SD/Flux models, ~2-3s, returns the URL synchronously.
- Alternative (community models with a specific `model_id`, may be ASYNC/queued):
  `POST https://modelslab.com/api/v6/images/text2img`  ← only use if you must pick a
  named community model; otherwise prefer realtime.

## 2. Auth — key goes in the JSON BODY (NOT a header)

The API key is sent as the `"key"` field inside the POST JSON body. There is no
`Authorization` header. The only header needed is `Content-Type: application/json`.

## 3. Request body (realtime text2img)

```json
{
  "key": "MODELSLAB_API_KEY",
  "prompt": "ultra realistic product banner, studio lighting, ...",
  "negative_prompt": "low quality, blurry, watermark, text, deformed",
  "width": 1024,
  "height": 1024,
  "samples": 1,
  "safety_checker": true,
  "seed": null,
  "base64": false,
  "enhance_prompt": "yes",
  "webhook": null,
  "track_id": null
}
```

Param notes / limits:
- `prompt` (required), `negative_prompt` (optional string).
- `width` / `height`: integers, **max 1024** each (default 512). For ad banners use
  1024x1024 (square) or 1024x576-ish; clamp to 1024.
- `samples`: 1-4 (**keep at 1** — free quota / money rule). Default 1.
- `safety_checker`: bool — NSFW filter. Set **true** for brand-safe marketing output.
- `seed`: int or `null` (null = random; pass a fixed int for reproducibility).
- `base64`: false -> returns URLs (what we want; storage re-uploads to DO Spaces).
- `enhance_prompt`: "yes"/"no" — lets ML auto-improve the prompt; safe to send "yes".
- `num_inference_steps` / `guidance_scale`: accepted on the **community**
  (`/api/v6/images/text2img`) endpoint; on realtime the model is pre-optimized so
  these are not required. If using community: steps 21/31/41, guidance 1-20.
- `model_id`: NOT used by realtime. Used by `/api/v6/images/text2img` (see §6).

## 4. Response — SUCCESS (sync, HTTP 200)

```json
{
  "status": "success",
  "generationTime": 2.5,
  "id": 12345,
  "output": ["https://.../image.png"],
  "proxy_links": ["https://.../image.png"],
  "meta": {},
  "nsfw_content_detected": false
}
```

Adapter: take `output[0]` (the image URL), download it, hand bytes to storage
(DO Spaces presigned). Check `nsfw_content_detected` -> if true, treat as a soft
failure / regenerate-or-reject (do NOT publish).

## 5. Response — PROCESSING (async fallback) + POLLING

If queued, you get:

```json
{
  "status": "processing",
  "eta": 15,
  "message": "processing",
  "fetch_result": "https://modelslab.com/api/v6/realtime/fetch/12345",
  "id": 12345,
  "output": [],
  "meta": {}
}
```

Poll the `fetch_result` URL (it is given in the response — use it verbatim):

```
POST  <fetch_result>          e.g. https://modelslab.com/api/v6/realtime/fetch/{id}
Content-Type: application/json
{ "key": "MODELSLAB_API_KEY" }
```

Fetch response is the same shape: `status:"processing"` (output still `[]`, retry
after ~`eta` seconds) OR `status:"success"` with `output[]` populated. Poll loop:
respect `eta`, sleep ~2s between polls, cap at ~6-8 tries (~ eta+buffer) then error.
Error shape on any call: `{ "status": "error", "message": "..." }` (also covers
401 bad key / 400 bad params).

## 6. RECOMMENDED model_id for ad banners (photoreal / product)

- **Realtime endpoint: no model_id needed** — it serves an optimized SD/Flux model.
  This is the recommended default for our free-tier single-shot banner.
- If you switch to the community endpoint `/api/v6/images/text2img` and want a named
  model, the best photoreal/marketing pick is a **Flux** model:
  - `model_id: "fluxschnell"`  ← Flux.1 Schnell, fast + photorealistic, ~$0.0047/call,
    great for product/marketing banners. **Recommended community model.**
  - `model_id: "flux"` / `"v1fluxdevfp8"` (Flux dev) — higher fidelity, a bit slower.
  - SDXL community options (dreamshaper-v8, realistic-vision) also exist but Flux
    gives the cleanest photoreal product look for ads.
- Decision: **default = realtime endpoint (no model_id); make model_id an optional
  override** so the custom-prompt box / power users can request `fluxschnell` etc.

## 7. Free-tier limits & gotchas

- **Free trial: ~30-100 free calls, no credit card.** (Sources vary: "30 API calls"
  trial vs "100/day"; treat as small — MONEY RULE: test exactly ONE image, never loop.)
- **Rate/concurrency:** free tier has concurrency limits. ">100 calls/sec are queued."
  Batch advice from ML's own docs: add `sleep(2)` between requests. We only do 1 at a
  time, so fine — but the poll loop must sleep, not hammer.
- **Image URL expiry:** ModelsLab output URLs are temporary / can expire — DO NOT store
  the ModelsLab URL as the permanent asset. Download immediately and re-upload to DO
  Spaces (the pipeline already does presigned Spaces storage). This also fixes any
  hotlink/expiry breakage the founder may have seen.
- **NSFW:** `safety_checker:true` + `nsfw_content_detected` flag in response; gate on it.
- **Formats:** PNG/JPG only.
- **Realtime vs community:** realtime = sync (no polling, fast, no model_id) — preferred.
  community/`images` = can return `processing` and require polling — only for named models.

## 8. Minimal proven request (what the test must send — ONE image)

```bash
curl -X POST "https://modelslab.com/api/v6/realtime/text2img" \
  -H "Content-Type: application/json" \
  -d '{"key":"'"$MODELSLAB_API_KEY"'","prompt":"photorealistic product ad banner, premium studio lighting, clean background","negative_prompt":"low quality, blurry, watermark, text","width":1024,"height":1024,"samples":1,"safety_checker":true,"enhance_prompt":"yes"}'
```

Expect `{"status":"success","output":["https://...png"],...}`. If `processing`, poll
`fetch_result` with `{"key":...}` until `success`.

---

## Sources
- Realtime Stable Diffusion overview — https://docs.modelslab.com/image-generation/realtime-stable-diffusion/overview
- Realtime text2img endpoint (request/response shape) — https://docs.modelslab.com/image-generation/realtime-stable-diffusion/text-to-image
- Fetch queued images (polling) — https://docs.modelslab.com/image-generation/realtime-stable-diffusion/fetchimage
- Flux text2img / model docs — https://docs.modelslab.com/image-generation/flux/fluxtext2img
- Flux Schnell model page (model_id, price) — https://modelslab.com/models/modelslab/fluxschnell
- ModelsLab + Claude Code integration guide (free tier, curl, sleep(2)) — https://modelslab.com/blog/api/modelslab-api-claude-code-integration
- Image Generation API landing — https://modelslab.com/image-generation-api
- FAQ (rate limit ">100 calls/sec queued") — https://modelslab.com/faq
- Pricing — https://modelslab.com/pricing
