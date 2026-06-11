# wave-build-B2 — WhatsApp + DO Spaces GO-LIVE (no more dummy)

> Durable build report. Append-only. Companion to `mod-whatsapp-builder.md`, `media-gen.md`,
> `WHATSAPP_GOLIVE.md`. Date 2026-06-11. Box famit@168.144.153.145.

## WHAT SHIPPED (live, regression-gated)
Activated the real WhatsApp send path + routed AI-Asset banners to DO Spaces. Three small,
backed-up code fixes + two env updates + one pip install. Live voice path untouched.

### ENV (backups *.B2bak.20260610-213324)
- `/opt/famit-agent/.env`: `META_WA_TOKEN` set to the real permanent **EAA… (202 chars)** token
  (was EMPTY on box — docs said old `4234..` but it was blank); added `FEATURE_WHATSAPP=1`.
- `/opt/famit-aiasset/.env`: added `SPACES_KEY/SECRET/BUCKET=capsy-recordings/REGION=sgp1/
  ENDPOINT=https://sgp1.digitaloceanspaces.com`.
- `pip install boto3` (1.43.27) into the aiasset venv — **was MISSING** → `spaces_configured()`
  was False even with env (the silent blocker).

### CODE FIXES (all backed up; live earner safe)
1. **`creative/image_banner_studio/storage.py`** (deployed in aiasset) — NEW `_spaces_mirror()` wired
   into `save_job()` after the local `write_bytes`: best-effort mirror of the banner bytes to DO Spaces
   via the EXISTING dormant `asset_library.spaces.put_bytes` (no new S3 client). Attaches
   `spaces_key`/`spaces_url`/`storage="spaces"` to the image dict on success. Dormant-safe (no creds /
   no boto3 → `not_configured` → keeps local path, byte-identical) and NEVER raises (a failed cloud
   mirror is NOT a storage error — bytes stay safe on disk). The pipeline writes BOTH local + Spaces.
2. **`whatsapp.py`** `_meta_to()` — strips the leading `+` from the recipient at the single Meta-body
   boundary. Upstream `caller.norm()` returns `+E.164`; Graph Cloud API **404s** on a `+`-prefixed `to`.
   Applied in `_meta_template_body` + `_meta_text_body`. (backup `whatsapp.py.WABbak.20260610-213324`)
3. **`caller.py`** `_wa_send(..., is_text)` — the in-app `/whatsapp/send` route was passing free-form
   TEXT as `template_or_text` into `send_whatsapp_async`, which (Meta-configured) ALWAYS built a
   **template** body → Graph **#132001 "Template name does not exist"**. Added `is_text` so a raw-text
   send routes to `send_whatsapp_text_async` (Meta TEXT path). Route sets `is_text` when `text` given &
   no `template`. Default False preserves every existing template caller (auto-followup etc.).
   (backup `caller.py.WABbak.20260610-213324`)
4. **`creative/asset_library/spaces.py`** `put_bytes` — the bucket `capsy-recordings` has
   **object-ownership enforced (ACLs disabled)** → `ACL: public-read` rejected with
   `UnsupportedAclConfigurationException` (wrapped in boto3 `ClientError`). Added a one-shot retry
   WITHOUT the ACL (detected via the error response text, not the wrapper class name). Public access
   is then governed by the bucket policy; objects are served via PRESIGNED URLs (bucket is private).
   (backup `spaces.py.B2bak.20260610-213324`)

## LIVE TEST RESULTS
- **TEST a — in-app WhatsApp send (PASS).** `POST /whatsapp/send` (X-Auth admin, `to=917861019021`,
  `text=...`) → `{"ok":true,"status":"sent:200","configured":true}`, HTTP 200. Real message delivered;
  **wamid `wamid.HBgMOTE3ODYxMDE5MDIxFQIAERgSQkYzMkQ4MkYwRDg4MkUyMTE4AA==`**. Token authenticates
  (no 401). Honest bound: free-form text works only inside the 24h session; COLD sends still need a real
  approved Meta template (`hello_world` is test-number-only) — the founder's one-time Meta gate.
- **TEST b — banner → DO Spaces (PASS).** AI-Asset pipeline (OpenRouter `gemini-2.5-flash-image`,
  1.38 MB PNG) → `storage=spaces`, key `creative/admin/banner/<job>/0.png`, HEAD confirms
  ContentLength 1376484 / ContentType image/png in `capsy-recordings`. Public direct URL → 403
  (bucket private, ACLs disabled) → served via PRESIGNED URL (works). No longer box-fs-only.

## REGRESSION (GREEN)
core /campaigns /leads /me 200 · POST /run/preview 200 · builder routes 404 (FEATURE_WHATSAPP_BUILDER
OFF — byte-identical) · /whatsapp/inbound verify 200 (live receive path intact) · famit-caller +
famit-aiasset active · famit-agent/famit-bridge/livekit (voice earner) active/untouched · zero 5xx.

## NOTES / OPEN (founder gates, unchanged by this wave)
- Cold (outside-24h) template send still blocked on a REAL approved Meta template (only `hello_world`).
- WABA is branded "MedFlow" / +91 97550 40013 — confirm it's the intended Famit number.
- Spaces bucket is PRIVATE (ACLs disabled). If raw public banner URLs are wanted, set a bucket public
  policy or a CDN/`DO_SPACES_CDN_BASE`; otherwise serve via presigned URL / the asset `/raw` route.
- ROLLBACK: restore the four *.B2bak/*.WABbak.20260610-213324 files + `META_WA_TOKEN=`/drop SPACES_*,
  restart both services.
