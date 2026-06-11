# UNIT B2 — WhatsApp + Spaces GO-LIVE — STATE

Box: famit@168.144.153.145  app /opt/famit-agent  aiasset /opt/famit-aiasset
Goal: real EAA WA token live (in-app send), generated banners land in DO Spaces.

## BASELINE FACTS (verified on box, read-only)
- famit-caller + famit-aiasset ACTIVE. AIASSET_ENABLED=1.
- /opt/famit-agent/.env line 43 `META_WA_TOKEN=` is EMPTY (docs said old 4234.. — actually blank).
  phone_id/waba/app_secret/verify_token all present & correct. No FEATURE_WHATSAPP flag.
- whatsapp.py:92 reads META_WA_TOKEN via os.getenv. /whatsapp/send (caller.py:4313) NOT flag-gated.
- aiasset /opt/famit-aiasset/.env has NO SPACES_* keys. OPNEROUTER_API_KEY present (box-specific key).
- ⭐ STORAGE GAP: ai_asset/pipeline.py -> image_banner_studio/storage.py:save_job ONLY writes box-fs.
  asset_library/spaces.py uploader EXISTS (put_bytes, dormant-safe) but is NOT wired into save_job.
  => env alone does NOT route banners to Spaces. Need a 1-spot wire in save_job.
- ⭐ boto3 NOT installed in aiasset venv => spaces_configured() False even with env. Must pip install boto3.
- asset_library/config.py accepts DO_SPACES_* AND SPACES_* (resolution chain). object_key =
  creative/<tenant>/<kind>/<asset_id>/<filename>.

## PLAN (each step: backup -> change -> verify -> record)
1. [DONE-PLAN] Edit local image_banner_studio/storage.py save_job: best-effort Spaces upload after
   local write (reuse asset_library.spaces.put_bytes), attach spaces_url/spaces_key. Dormant-safe.
2. Backup box copies (*.B2bak.<ts>): /opt/famit-agent/.env, /opt/famit-aiasset/.env,
   /opt/famit-aiasset/creative/image_banner_studio/storage.py.
3. Set META_WA_TOKEN=<real EAA> + FEATURE_WHATSAPP=1 (+FEATURE_WHATSAPP_BUILDER stays OFF — schema not applied) in famit-agent/.env.
4. Add SPACES_KEY/SECRET/BUCKET=capsy-recordings/REGION=sgp1/ENDPOINT=https://sgp1.digitaloceanspaces.com to aiasset/.env.
5. pip install boto3 into aiasset venv.
6. scp patched storage.py to box; py_compile + import smoke in aiasset venv.
7. Restart famit-caller + famit-aiasset.
8. TEST a: in-app WA send /whatsapp/send to +917861019021 (token authenticates, no 401; report wamid or exact block).
9. TEST b: generate a banner via aiasset; confirm PNG object in Spaces (key + served).
10. Regression: core /campaigns /leads /me 200, /run/preview 200, both services active, zero 5xx.
11. Rollback on any failure (.env + storage.py backups). build_log.

## ROLLBACK
- /opt/famit-agent/.env.B2bak.<ts> ; /opt/famit-aiasset/.env.B2bak.<ts> ;
  /opt/famit-aiasset/creative/image_banner_studio/storage.py.B2bak.<ts>
- restart both services after restore.

## PROGRESS LOG
- (init) baseline captured. starting edits.
- DONE: META_WA_TOKEN set (202c EAAm), FEATURE_WHATSAPP=1. SPACES_* added to aiasset env. boto3 installed.
- DONE: storage.py _spaces_mirror wired into save_job (best-effort, dormant-safe). Shipped+compiled.
- FIX1 (whatsapp.py): _meta_to() strips leading '+' (Graph 404 on '+'-prefixed to). Shipped, backup WABbak.
- FIX2 (caller.py): _wa_send is_text routes free-form text -> send_whatsapp_text_async (route was
  sending raw text as a TEMPLATE NAME -> Graph #132001). Route passes is_text. Shipped, backup WABbak.
- FIX3 (asset_library/spaces.py): put_bytes retries WITHOUT ACL on UnsupportedAclConfiguration
  (bucket has object-ownership enforced / ACLs disabled). Shipped, backup B2bak.
- TEST a PASS: in-app /whatsapp/send text -> sent:200, wamid HBgMOTE3ODYxMDE5MDIxFQIAERgSQkYzMkQ4MkYwRDg4MkUyMTE4AA==
- TEST b PASS: pipeline banner gen (OpenRouter 1.38MB png) -> Spaces key
  creative/admin/banner/20260611-031402-g2pmfq-0/0.png ; HEAD 1376484 image/png. Public URL 403
  (bucket private, ACLs disabled) -> served via PRESIGNED url (works). storage=spaces.
- NEXT: restart aiasset, regression gate.
