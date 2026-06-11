# fix-render-generation.md — why Creative Studio "Generate" sticks on
# "THINKING / Rendering creative / 0 of 1 ready" forever, and the fix

Status: DIAGNOSED + REPRODUCED live (2026-06-11). No code changed yet (backup-first).
Box: AI Asset svc `famit@168.144.153.145` -> `/opt/famit-aiasset` (:8310, priv 10.122.0.4).
Panel: FORTRESS `root@143.110.247.249:/opt/famit-panel` (Next.js).

---

## TL;DR

The job SUCCEEDS and the image IS stored (proven: an n=1 pollinations job reached
`state: succeeded`, est_cost_minor=0). The generation panel sticks for TWO
independent reasons, in order of impact:

1. **PRIMARY — the SSE progress stream 401s in the browser.** The frontend opens
   `GET /api/assets/jobs/{id}/stream?token=<hmac>` (EventSource — which physically
   cannot set request headers, so it passes the auth token as a `?token=` query
   param). But the backend `extract_cred()` reads the credential ONLY from the
   `Authorization`/`X-Auth` **headers** — it NEVER looks at a `token` query param.
   So `_tid(request)` -> None -> **401**. The browser EventSource gets an immediate
   error/close; `useGenerationJob`'s `onerror` deliberately stays in `"loading"`
   (it treats a closed stream as "dormant/unreachable"). The terminal `succeeded`
   frame is therefore NEVER delivered to the browser -> the `<GenerationLoader>`
   never receives `state="completed"`, never collapses, never fires `onCompleted`,
   `jobId` is never cleared -> the loader is pinned on the last phase the browser
   saw. Since the very first frame 401s, that's the fallback line "Rendering
   creative" and "0 of 1 ready" — forever.

2. **SECONDARY — even after #1 is fixed, the result image is a broken private
   URL.** When the loader finally collapses, the cards render `<img src>` =
   `asset.thumb_url || asset.url` = the DIRECT DO-Spaces URL
   `https://capsy-recordings.sgp1.digitaloceanspaces.com/creative/...`. That bucket
   is PRIVATE (ACLs disabled) -> the browser GET returns **403 AccessDenied**. The
   panel's `<Image>` starts `opacity-0` and only reveals on `onLoad`, which never
   fires on a 403 -> blank/empty card (the "broken-image icon + empty space"
   symptom). This is the same root cause as the Library/thumbnail breakage and is
   fixed by serving a **presigned** Spaces URL (see fix-creative-render.md / below).

---

## Live reproduction (one n=1 pollinations job, zero spend, no loop)

Minted the real panel credential = `admin.HMAC_SHA256(secret, "admin")` (the exact
`tenant_id.hmac(tenant_id, SECRET)` token the panel `/login` issues; secret =
`/opt/famit-agent/var/secret`). Then:

```
POST /generate  {platform:meta, asset_type:banner, count:1,
                 instruction:"diagnostic test banner", provider:"pollinations"}
  -> 200 {"status":"ok","job_id":"gj_8aee0ba3ac9048a7","state":"queued","est_cost_minor":0}

# job lifecycle (polled the row): queued -> running -> streaming(rendering) ->
#   scoring -> done, terminal state = "succeeded", n_succeeded=1, progress {total:1,done:1}

GET /jobs/{id}/stream?token=<hmac>     (the browser EventSource path)  -> 401  <-- BUG
GET /jobs/{id}/stream  (X-Auth header) (EventSource CANNOT set headers) -> 200
```

So the stream works ONLY with a header the browser cannot send. The `?token=`
fallback the frontend relies on is rejected. PROVEN.

The stored URLs (from `ai_asset_versions`, tenant=admin, RLS GUC set):
```
url       = https://capsy-recordings.sgp1.digitaloceanspaces.com/creative/admin/banner/.../0.jpeg
thumb_url = (same private base)            storage = spaces
```
From an open-egress host:
```
GET <direct private url>  -> HTTP 403 application/xml  <Code>AccessDenied</Code>   (what <img> hits)
GET <presigned url>       -> HTTP 200 image/jpeg  63436 bytes                       (the fix)
```
`creative/asset_library/spaces.py` already HAS `presign(key, expires=)` using
boto3 `generate_presigned_url`; it is just not used when serializing the asset.

---

## Frontend lifecycle (so the fix is verifiable)

- `app/creative/page.tsx` holds `jobId`; passes it to `<GenerationQueue>`.
- `<GenerationQueue>` uses `useGenerationJob(jobId)` (hooks/useGenerationJob.ts),
  which owns the `EventSource` on `/api/assets/jobs/{id}/stream?token=...`.
- `mapEvent` maps backend `state:"succeeded"|"done"|"completed"` -> loader
  `state:"completed"`. THIS MAPPING IS CORRECT — it just never receives the frame.
- On `state==="completed"`: `<GenerationLoader>` collapses -> `onCompleted` ->
  `setCollapsed(true)`; an effect pulls `getJob` -> `listAssets` -> `setVariants`
  and calls `onJobDone()` (page clears `jobId`). Then the idle wall renders
  `<AssetCard>`s whose `<img src>` is the (broken) private URL.
- `es.onerror` (useGenerationJob.ts:146) intentionally does NOT flip to "failed"
  on a closed stream, to keep the loader running when the backend is "dormant".
  That well-meant choice is exactly what masks the 401 as an eternal spinner.

---

## THE FIX (two parts; both small, additive, regression-safe)

### A. Make the SSE stream accept the `?token=` query param (PRIMARY — unsticks it)

EventSource cannot set headers; the frontend already passes `?token=`. The backend
must read it. Smallest change: in `ai_asset/auth.py:extract_cred()`, after the
header checks, fall back to the `token` query param:

```python
# ...after the X-Auth header check, before returning "":
try:
    qp = request.query_params  # Starlette/FastAPI Request
    t = qp.get("token") or qp.get("access_token") or ""
    if t:
        return t
except Exception:
    pass
return ""
```

This is exactly what the frontend comment in `useGenerationJob.ts` already
PROMISES ("the stream endpoint accepts either" — the backend just never
implemented the query-param leg). It only affects how the credential is *read*;
the same JWT/hmac verification still runs, so it cannot widen access (an invalid
`?token` still -> None -> 401). Scope it tightly if desired: only `/jobs/{id}/stream`
needs it, but a global `extract_cred` fallback is simplest and harmless (other
routes already require a valid token regardless of where it came from).

Verify: `GET /jobs/{id}/stream?token=<valid>` -> 200 text/event-stream; the browser
loader now receives `succeeded` and collapses.

### B. Serve a browser-loadable (presigned) image URL (SECONDARY — shows the image)

The bucket is private and DO Spaces ACLs are disabled, so the clean default is a
**presigned GET URL** (keeps the bucket private; no `<img>` auth-header problem).
When serializing an asset/version that has a Spaces object, return a freshly
presigned URL as the display field instead of the raw private `url`. Lowest-risk
place = `store.public_dict()` (or the endpoints that call it: list/get/raw/job),
mapping a Spaces object to `spaces.presign(key, expires=86400)`:

```python
# when storage == "spaces" and we have the object key, overwrite url/thumb_url
# with a 24h presigned GET so the browser <img src> loads (200 image/*),
# instead of the direct private URL (403). presign() already exists & is proven.
```

(The object key is recoverable from the stored `url` — strip the
`https://<bucket>.<region>.digitaloceanspaces.com/` prefix — or persist
`spaces_key` on the version row, which the studio already sets as `img["spaces_key"]`.)

Alternative (if presign is awkward at serialize time): make the existing
`/assets/{id}/raw` proxy tokenizable (accept `?token=`, same as fix A) and point
`<img src>` at `assetRawUrl(id)+"?token="+famit_token`. Presign is the cleaner
default and is what this doc recommends.

Verify: `<direct private url>` -> 403; `<presigned url>` -> 200 image/jpeg (proven
above). After the fix, list/detail/recent/library all return presigned URLs and
the `<Image>` `onLoad` fires -> cards become visible.

---

## Deploy / guardrails

- BACKUP first (`*.bak.<ts>`), edit on the box, then `sudo systemctl restart
  famit-aiasset` ONLY (do NOT touch famit-caller / voice; the live earner is
  untouched — these are additive reads in the asset service).
- Money rule honoured: reproduction used EXACTLY ONE pollinations (free) image,
  est_cost_minor=0, never OpenRouter, no loop.
- Fix A is the unblocker (stuck spinner). Fix B makes the produced image visible.
  Ship both; A alone still leaves a blank card, B alone still leaves the spinner.
```
