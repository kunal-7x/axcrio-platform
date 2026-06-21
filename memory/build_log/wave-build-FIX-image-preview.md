# Wave build — FIX: image preview / asset-click = blank (AI Asset service)

Date: 2026-06-13. Scope: AI Asset service ONLY (`famit-aiasset`). Earner UNTOUCHED.

## Symptom (founder)
"IMAGE PREVIEW / ASSET CLICK = EMPTY." Generated banners show blank in Creative
Studio.

## Root cause (proven, not guessed)
The known root cause (private Spaces object → `<img>` 403 → blank) was already
fixed for the LIST surface: `ai_asset/store.public_dict()` →
`_presign_row_urls()` re-presigns the Spaces url at read time (shipped
2026-06-11). PROVEN LIVE: `GET /assets` returns a presigned url that HTTP-GETs
**200 image/jpeg 63436B**; the raw unsigned url → **403** (private bucket).

The REMAINING bug was the **asset-click DETAIL preview**:
- `GET /assets/{id}` → `{asset, versions[]}`. The `versions[]` were presigned,
  but the `asset` object carries **no `url`/`thumb_url`** (the asset table stores
  no image — bytes live on the version row).
- FE `app/creative/_components/AssetDetail.tsx:97`:
  `src = a.thumb_url || a.url || assetRawUrl(a.id, a.current_version_id)` → both
  empty → falls through to the **X-Auth-gated `/raw` proxy**. An `<img src>` can't
  send X-Auth → `/raw` **401** → blank preview on click.
  (PROVEN: `/raw` no-auth=401, with-auth=200.)

Secondary gotcha (noted, not load-bearing here): the stored Spaces url is
PATH-style (`sgp1.digitaloceanspaces.com/capsy-recordings/<key>`) while
`public_base()` is VIRTUAL-HOSTED — so `_spaces_key_for`'s url-strip branch fails
for path-style; key recovery works only via the `local_path`/`storage=spaces`
branch.

## Fix (additive, 2 files)
1. **Backend** `ai_asset/endpoints.py get_asset`: fold the current (else newest)
   version's already-presigned `url`/`thumb_url` onto the asset object when it has
   none → asset-detail API is self-sufficient; FE never hits `/raw`.
   Backup `endpoints.py.FIXbak.20260613-162358` (md5 fb93296a→dadadbe6).
2. **Frontend** `app/creative/_components/AssetDetail.tsx`: `src` also tries
   `currentVersion?.thumb_url || currentVersion?.url` (from the already-presigned
   `a.versions[]`) before the `/raw` fallback. Commit `1005ccb`.

## Asset-detail API shape (for FE)
`GET /api/assets/{id}` →
`{asset:{id, headline, kind, platform, size, angle, cta, language, status,
current_version_id, score, metrics, tags, meta, created_at, url(presigned ~24h),
thumb_url(presigned)}, versions:[{id, version_no, url(presigned),
thumb_url(presigned), storage:"spaces", model, cost_minor, created_at,
is_current}]}`.
List `GET /api/assets?<facets>` →
`{assets:[{...,url(presigned),thumb_url(presigned),storage}], total, limit, offset}`.
Auth = X-Auth tenant hmac `tenant.hmac(tenant,SECRET)` (bare `FamitCall2026` →
401 unauthenticated).

## Deploy + gates
- py_compile on `/opt/famit-aiasset/.venv` OK; `systemctl restart famit-aiasset`
  ONLY → active, `/status`=200, 0 errors.
- SMOKE PASS: detail `asset.url` presigned=True → GET **200 image/jpeg 63436B**
  (was empty → /raw 401 → blank).
- EARNER GATE before+after PASS: agent.py md5 `9150fabe4ff62b4b4470f9a87df346e5`
  UNCHANGED, famit-agent MainPID `1477083`/ActiveEnter 2026-06-10 NEVER restarted,
  caller `/health`=200.

## NEXT
- Deploy `AssetDetail.tsx` to the FORTRESS panel (frontend unit).
- BUG-2: tenant-scoped transcript-per-call API + CRM lead chat-view.
