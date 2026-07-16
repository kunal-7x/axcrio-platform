# fix-render-storage — why Creative Studio images won't display, and the fix

DIAGNOSE-3 verdict. Live-probed 2026-06-11 against the AI Asset service
(`famit@168.144.153.145:/opt/famit-aiasset`, :8310) and the DO Spaces bucket
`capsy-recordings` (sgp1). The store is fine — **the bug is URL serving, not storage.**

---

## 1. The bug in one sentence

Images generate + upload to DO Spaces fine, but the asset API hands the browser a
**direct PRIVATE Spaces URL** as the `<img src>`. The bucket is private, so the
browser's unauthenticated `GET` returns **403 AccessDenied** → broken-image icon;
the generation panel never sees an image so it sticks on "0 of 1 ready".

## 2. Confirmed bucket / Spaces state (live evidence)

- Bucket: `capsy-recordings`, region `sgp1`, endpoint `https://sgp1.digitaloceanspaces.com`.
  Service creds resolve (`spaces_configured() == True`); boto3 present; objects exist,
  e.g. `creative/21d0a13603da/banner/20260611-201938-1x10dw-0/0.jpeg`.
- **Bucket is PRIVATE (object-ownership enforced / ACLs disabled).** Prior note
  "ACL public-read rejected, bucket ACLs disabled" is correct — `put_object` with
  `ACL=public-read` raises `UnsupportedAclConfiguration`, and the uploader already
  falls back to a no-ACL PUT (`spaces.py put_bytes`). So every object lands private.
- **Direct URL (what's stored now) → 403:**
  `GET https://capsy-recordings.sgp1.digitaloceanspaces.com/creative/.../0.jpeg`
  → `HTTP 403 Forbidden`. This is exactly the string used as `<img src>`.
- **Presigned GET → 200 image (works unauthenticated):**
  `boto3 generate_presigned_url("get_object", ...)` →
  `https://sgp1.digitaloceanspaces.com/capsy-recordings/creative/.../0.jpeg?X-Amz-...`
  → `HTTP 200 Content-Type: image/jpeg`. Proven from the box, no auth header.

## 3. Where the broken URL comes from (data flow)

1. `ai_asset/jobs.py:266` — on job success, sets
   `_img_url = img.url || img.spaces_url`, then `store.add_version(... url=_img_url,
   thumb_url=img.thumb_url || _img_url ...)`. That `spaces_url` is the **direct private**
   URL built by `creative/asset_library/spaces.py public_url()` =
   `https://<bucket>.<region>.digitaloceanspaces.com/<key>` (config `public_base()`).
2. `ai_asset/store.py` — `_VERSION_COLS` keeps `url`, `thumb_url`, and the private
   `spaces` key path in `local_path`/`storage`. `public_dict()` only strips `local_path`;
   it returns `url`/`thumb_url` **as-is** (the private URL).
3. `ai_asset/endpoints.py` — `GET /assets` (`:192`), `GET /assets/{id}` (`:205`) return
   `public_dict(...)` → frontend gets the private `url`/`thumb_url`.
4. Frontend `famit-panel/app/creative/_components/AssetCard.tsx:61`:
   `const src = asset.thumb_url || asset.url || assetRawUrl(...)` → `<Image src>` →
   browser loads the private URL → **403 → broken image**. The `/raw` fallback
   (`endpoints.py:207`) is X-Auth–gated and also returns the same private `url` as JSON
   when `local_path` is empty, so it cannot rescue an `<img>` either.

## 4. Decision — chosen approach

**(A) PRESIGNED Spaces URLs returned by the API.** Recommended and chosen.

Justification vs the alternatives:

- **(A) Presigned — CHOSEN.** Keeps the bucket PRIVATE (no posture change, no recordings
  bucket made public), proven 200 unauthenticated, zero infra/DNS/CDN work, no
  img-auth-header problem (the signature is in the query string so a plain `<img src>`
  loads it). `spaces.presign()` already exists and works. Only a small read-time change
  to where the API emits `url`/`thumb_url`. Trade-off: URLs expire (use ~24h) and are
  minted per read — fine for a gallery; we re-presign on every list/detail fetch.
- **(B) Make bucket/prefix public-read + direct URLs.** Simplest at render time but
  **rejected**: this is the shared `capsy-recordings` bucket that also holds call
  RECORDINGS — making it (or even a prefix, via bucket policy) public exposes private
  customer data to anyone with a URL. Not acceptable for a multi-tenant earner. Also
  ACLs are disabled, so it would need a bucket-wide policy edit (riskier, broad).
- **(C) Tokenized backend proxy `/raw?token=`.** Works and keeps the bucket private,
  but routes every image byte through the app server (bandwidth + latency + a new
  signed-token scheme to build/verify), and needs the panel to embed a token in the
  URL. Strictly more code and load than presign for no extra benefit. Keep as a
  fallback only if we later need hotlink control or per-view audit.

> Founder's question "should we use something else for storing images?" — **No.**
> DO Spaces is the right store and the bytes are safe. The defect is purely how the
> URL is served to the browser. Do **not** migrate the store.

## 5. Exact implementation (server-side, the only change needed)

Goal: the API must return a **browser-loadable presigned GET URL** wherever it currently
returns the private `url`/`thumb_url`. Mint it at READ time from the stored Spaces key.

**5a. Make the key recoverable (storage/jobs).**
- `ai_asset/jobs.py` (~`:266`): when storing a Spaces-backed version, persist the
  **object key** alongside the URL. Easiest: keep `local_path` carrying the Spaces key
  (`img.spaces_key`) when `storage == "spaces"`, OR add a `spaces_key` column. Today
  `img["spaces_key"]` is set in `image_banner_studio/storage.py _spaces_mirror`, and the
  ai_asset job has `_img_url`; ensure `spaces_key` (or the key parsed from the URL) is
  written so the read layer can presign. If only the URL is available, derive the key by
  stripping `public_base()` prefix from the stored `url` (it's deterministic:
  `<base>/<key>`).

**5b. Presign at read time (store + endpoints — the load-bearing change).**
- In `ai_asset/store.py public_dict(row)`: after building the public row, if the version
  is Spaces-backed (`storage == "spaces"` or `url` starts with the Spaces base), compute
  `disp = spaces.presign(key, expires=86400)` and set `row["url"] = disp` and
  `row["thumb_url"] = disp` (or add `row["display_url"] = disp` and leave `url` as the
  canonical record — but since the frontend reads `thumb_url || url`, overwriting both is
  the smallest change and needs no frontend deploy). Import is
  `from creative.asset_library import spaces` (already on the box). Presign is
  best-effort and never raises; on '' fall back to the existing value.
- Apply identically in the two endpoints that surface versions to the panel:
  `GET /assets` (`endpoints.py:192`) and `GET /assets/{id}` (`:205`) — both already call
  `public_dict`, so doing it inside `public_dict` covers both plus pickers/detail.
- `GET /assets/{id}/raw` (`endpoints.py:207`): when `local_path` is empty and the version
  is Spaces-backed, instead of returning `{"url": <private url>}`, return an HTTP **302
  redirect to the presigned URL** (or stream the bytes). This makes `/raw` itself a
  valid `<img src>` for the no-token path, as a belt-and-suspenders fallback.

**5c. Frontend (optional, no change strictly required).**
Because 5b overwrites `url`/`thumb_url` with the presigned URL, `AssetCard.tsx:61`
(`asset.thumb_url || asset.url || assetRawUrl(...)`) works unchanged — `<Image unoptimized>`
loads the presigned URL directly. If we instead add a separate `display_url` field, update
`lib/assets.ts` `Asset`/`AssetVersion` types + `AssetCard` `src` to prefer `display_url`.
Keep `assetRawUrl()` as the final fallback. The generation panel's "0 of 1 ready" clears
once the first version carries a loadable URL.

**5d. Deploy.** Backup the touched files first (`*.presignbak.<ts>`), then
`sudo systemctl restart famit-aiasset` ONLY (it owns :8310). Do **not** touch
`famit-caller`/voice. Frontend deploy via FORTRESS only if 5c's `display_url` route is
chosen; the overwrite-in-public_dict route needs **no** panel redeploy.

## 6. Test / regression gate
- Re-run the box presign probe: list one `creative/...` object → `presign` → `curl`
  unauthenticated → expect **200 image/\***. (Done above: 200 image/jpeg.)
- After 5b: `GET /api/assets/assets?limit=1` (with a real panel X-Auth token) → the
  returned `url`/`thumb_url` must be an `...?X-Amz-Signature=...` presigned URL, and
  pasting it in a browser must render the image.
- Generate EXACTLY 1 FREE image (`provider=pollinations`, count=1, never paid, never
  loop) → confirm it appears in Studio + Library, no broken icon, panel reaches "1 of 1".
- Voice earner untouched: do not restart `famit-caller`; only `famit-aiasset` restarts.

## 7. Files to touch
- `ai_asset/store.py` — `public_dict()`: presign Spaces-backed `url`/`thumb_url` (MAIN FIX).
- `ai_asset/jobs.py` (~:266) — ensure the Spaces object **key** is persisted (or derivable).
- `ai_asset/endpoints.py:207` — `/raw`: 302-redirect to presigned for Spaces-backed bytes.
- (optional) `famit-panel/lib/assets.ts` + `app/creative/_components/AssetCard.tsx` —
  only if adding a separate `display_url` field instead of overwriting `url`.
