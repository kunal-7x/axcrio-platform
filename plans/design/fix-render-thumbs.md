# DIAGNOSE-1 — Creative Studio broken thumbnails (root cause + fix)

Date: 2026-06-11 · Box: AI Asset service `famit@168.144.153.145` -> `/opt/famit-aiasset` (:8310, bind 10.122.0.4)
Frontend: `caps/famit-panel app/creative*` + `lib/assets.ts` -> deployed to FORTRESS panel `root@143.110.247.249:/opt/famit-panel`

## SYMPTOM
Every asset card / Recent-assets / Library tile shows a BROKEN-IMAGE icon. The job succeeds and the
image IS stored (disk + DO Spaces), but the browser cannot DISPLAY it.

## WHAT THE FRONTEND USES AS `<img src>` (traced)
The same fallback chain is used in EVERY render site:
- `app/creative/_components/AssetCard.tsx:61` — `asset.thumb_url || asset.url || assetRawUrl(asset.id, asset.current_version_id)`
- `app/creative/_components/AssetDetail.tsx:97` — same chain
- `app/creative/_components/LibraryGallery.tsx:370` — `a.thumb_url || assetRawUrl(...)` (bg-image)
- `app/creative/_components/VersionTimeline.tsx:49,170` — same chain
- `app/creative/_components/UsePicker.tsx:125,179,226` — same chain
- `lib/assets.ts:410 assetRawUrl()` -> `"/api/assets/assets/{id}/raw?version=..."`

So the `<img src>` resolves to ONE of two URLs, and BOTH fail in a browser:

### Path A (the one actually firing now) — the `/raw` proxy -> 401
LIVE PROOF (service journal, 15:53, from the panel box 10.122.0.2):
`GET /assets/ca_.../raw?version=av_... HTTP/1.1" 401 Unauthorized` (repeated ~30x).
Reproduced: `curl http://10.122.0.4:8310/assets/<id>/raw?version=<v>` with NO header -> **HTTP 401**.
Reason: `/assets/{id}/raw` requires auth (`_tid(request)` -> `_need_auth()` = 401 when no token). An
`<img>` tag CANNOT send the `X-Auth` header, so every `/raw` load is 401 -> broken image.
(The list response is reaching the frontend WITHOUT a browser-loadable `thumb_url`/`url`, so the chain
falls through to `assetRawUrl()`.)

### Path B (the underlying field) — the private Spaces URL -> 403
The persisted version row stores `url`/`thumb_url` = the DIRECT private Spaces URL.
`ai_asset/jobs.py:266-272`: `_img_url = img.get("url") or img.get("spaces_url")` then
`add_version(... url=_img_url, thumb_url=img.get("thumb_url") or _img_url ...)`.
The stored value (from a real job's result.json):
`https://capsy-recordings.sgp1.digitaloceanspaces.com/creative/admin/banner/.../0.jpeg`
Reproduced as a plain browser GET (no auth):
`HTTP 403  ctype=application/xml` body `<Error><Code>AccessDenied</Code>...`.
Reason: bucket `capsy-recordings` (sgp1) is PRIVATE — ACLs disabled, so the uploader's `public-read`
retry strips the ACL (`creative/asset_library/spaces.py put_bytes`), and no `DO_SPACES_CDN_BASE`/
`PUBLIC_BASE` is set, so `public_url()` returns the raw private URL. -> 403 in the browser.

## THE FIX (proven)
Serve a browser-loadable PRESIGNED Spaces URL as a NEW display field on the asset/version, and make the
frontend use it FIRST as the `<img src>` (keeps the bucket private; no img-auth-header problem).

- Backend already has the seam: `creative/asset_library/spaces.py presign(key, expires=...)` (boto3
  `generate_presigned_url("get_object")`).
- PROVEN LIVE: presign of the same key returned `PRESIGNED GET -> 200 image/jpeg bytes 63436`.
- Add a `display_url` (presigned GET, ~24h) computed from the version's `spaces_key`/`storage` and
  returned by `GET /assets` and `GET /assets/{id}` in `store.public_dict()` (or the endpoint serializer).
  Persist `spaces_key` on the version (it's in result.json; jobs.py currently drops it) so the API can
  presign on read.
- Frontend: prefer `asset.display_url` (and `version.display_url`) ahead of `thumb_url`/`url`/`/raw` in
  the chain (`AssetCard.tsx:61`, `AssetDetail.tsx:97`, `LibraryGallery.tsx:370`, `VersionTimeline.tsx`,
  `UsePicker.tsx`).
- BACKUP-FIRST + restart ONLY `famit-aiasset` (never famit-caller / voice). Free test = pollinations,
  exactly 1 image, never paid OpenRouter.

### Alt fallback (cheaper, but keeps the auth/private problem off-bucket)
Make `/raw` accept a `?token=` query param (tokenized proxy) AND, when `local_path` is missing, redirect
to a presigned URL instead of returning `JSONResponse({"url": ...})` (endpoints.py:226 currently returns
JSON, not bytes — so even an authed `<img>` to `/raw` for a Spaces-only asset shows a broken image).
Presigned `display_url` is the clean default and avoids both issues.

## SECONDARY (not the thumbnail RC, but the "0 of 1 ready forever") 
`endpoints.py:226` `/raw` returns `JSONResponse({"url": url})` (application/json) instead of streaming
bytes when there is no `local_path` — an `<img>` would render this as broken even if authed. And the
job/asset persistence into `ai_asset_*` (jobs.py `_run` -> create_asset/add_version) appears not to be
populating rows the panel polls in some runs (FORCE-RLS tables; verify the job finalize path writes and
that the poller reads the same tenant). Track separately from the thumbnail fix.
