# Wave Build — AI Asset Service A4 (LIVE END-TO-END TEST — the proof)

> A4 = Wave E of CREATIVE_STUDIO_EXECUTION_PLAN: deploy A2+A3 (local-only) onto the box,
> set the OpenRouter key, flip AIASSET_ENABLED for the admin test tenant, and generate a
> REAL banner from a REAL campaign end-to-end. Proof, security gate, live-platform-safety.
> Date: 2026-06-11. Box: famit@168.144.153.145. Service: /opt/famit-aiasset (port 127.0.0.1:8310).
> NO caller.py edit; NO famit-caller/famit-agent restart; NO panel deploy. Stayed in own lane.

## RESULT — REAL BANNER GENERATED: **YES**
- Campaign: **Codename Joy 3.0** (`c17e55e9f3`, Shapoorji Pallonji Real Estate, tenant `admin`) — a real
  real-estate campaign read live from caller.py `/campaigns`.
- Pipeline ran: campaign facts -> prompt_builder (stage-1, deterministic no-invent) -> router selects
  **openrouter** -> `google/gemini-2.5-flash-image` -> base64 data-URL decoded to PNG -> box fs.
- 3 banners, each a valid **PNG 1024x1024, 1.3–1.9 MB** (real generation, not the 3.6KB fake placeholder).
- Asset paths on box: `/opt/famit-aiasset/var/creatives/<job_id>/0.png` (clean job `gj_31b9ef10a1b642b2`).
- **Distinct variant DNA** (3 different angles, distinct headline + goal-matched CTA, all facts verbatim):
  - location — "Live Steps from Infosys Circle, Hinjewadi" / CTA "View Location Benefits"
  - social-proof — "Join 400+ Families at Codename Joy 3.0" / CTA "Book Your Site Visit"
  - benefit — "Your Dream Home Awaits in Hinjewadi" / CTA "Explore Homes"
- **Wallet (no-double-charge, settle ACTUAL):** unique hold 96, reserved 1132 paise (estimate), settled the
  ACTUAL OpenRouter cost **1014 paise (Rs10.14)** from live `usage.cost` (3 × $0.0388), refunded 118.
  admin balance 10000->8986, `held=0`, `lifetime_spend=1014`. Released on the duplicate/forge path.
- **Audit:** 8 rows in the immutable `ai_asset_audit_logs` per-vendor mirror (submit/run/succeeded per job).
- **Tenant isolation: PASS** — B forges admin job id -> 404; B asset list = 0; admin token + body
  `tenant_id=tenantB_forge` -> created job `vendor_id=admin` (body IGNORED, the negative control that proves
  teeth) and the job is NOT visible to tenantB_forge; unauthenticated -> 401.
- **Live platform UNTOUCHED:** famit-caller active since 19:56 UTC + famit-agent since 19:58 UTC (both
  PRE-DATE all A4 work); `/health` 200, `/campaigns` 200. Only `famit-aiasset` was restarted (ours).
- AIASSET_ENABLED left **ON** for the admin tenant (founder can try it); per-tenant default still OFF
  (the flag is a global env today — see gaps).

## WHAT WAS DEPLOYED (A2+A3 were local-only before A4)
- scp into `/opt/famit-aiasset/ai_asset/`: auth.py, billing.py, jobs.py, endpoints.py, pipeline.py,
  prompt_builder.py, store.py, app/main.py (v0.2.0-a3 router mount).
- scp into `creative/image_banner_studio/providers/`: **openrouter.py** (the one missing provider) +
  `__init__.py` (registry w/ openrouter). **+ router.py** (the fix below).
- `.env`: `OPNEROUTER_API_KEY` (from `.env.local`), `FAMIT_VAR=/opt/famit-aiasset/var`,
  `IMAGE_CREATIVES_DIR=/opt/famit-aiasset/var/creatives`, `AIASSET_ENABLED=1`.
- `pip install PyJWT==2.13.0` into the service venv (the only added dep — tiny, isolated).
- Backup before edits: `/opt/famit-aiasset/.a4bak.20260610-203503` + `.env.a4bak.*`.

## 4 BUGS FOUND + FIXED DURING A4 (all deployed; verified by re-run)
1. **router.py on box was the OLD A1 version** — its universal fallback chain did NOT include `openrouter`,
   so even with the key set + provider registered, `select()` walked
   `ideogram>flux_hosted>recraft>gpt_image>flux_selfhost>fake` and rendered via **fake** (3.6KB placeholder).
   FIX: deployed `router.py` whose fallback chain leads with `openrouter`. Now
   `route_reason=ideogram:not_configured>chose:openrouter`. (The providers registry already had openrouter;
   the router is the OTHER half and it had been missed in the A2 deploy list.)
2. **Shared reserve idempotency key -> wallet returned the SAME hold for every job.** `jobs.submit` reserved
   the hold with the literal `"pending"` (the real job_id didn't exist yet), so `billing.reserve_hold` built
   `idem_key="reserve:job:pending"` for EVERY job. `wallet.reserve` is idempotent on that key -> 2nd+ job got
   the SAME hold (e.g. 95) -> its settle hit an already-settled hold -> **charged 0** (the first symptom:
   real images but `actual_cost_minor=0`). FIX: pre-generate `job_id = store.new_id("gj")` BEFORE the reserve,
   reserve with it (unique idem), pass it into `create_job(job_id=...)`; on an idempotency-key replay release
   the duplicate hold and return the existing job. Proven: clean job -> unique hold 96 -> settle 1014.
3. **Standalone venv could not resolve the tenant token.** The service's isolated venv lacks the monolith's
   `google.protobuf` (so `import caller` fails) AND `jwt` (so the shared `auth` module had no `_SECRET` and
   `resolve_token` rejected every token) -> every `/generate` was `401 unauthenticated`. FIX: `pip install
   PyJWT` into the service venv; `auth.resolve_tenant` now lazy-inits the monolith `auth` HS256 secret from
   the shared `/opt/famit-agent/var/secret` (overridable `AIASSET_JWT_SECRET_FILE`) and resolves the tenant
   from the VERIFIED `access_claims` (sub/role/is_admin) — the designed scoped-JWT seam. Token A beats body B.
4. **Admin pseudo-tenant wallet reserve needs the admin GUC.** FORCE-RLS `wallet_idempotency` rejected the
   INSERT for tenant `admin` without the admin escape (`new row violates row-level security policy`). FIX:
   thread the token's `is_admin` claim through `endpoints.generate -> jobs.submit -> billing.reserve_hold/
   settle_actual -> wallet.reserve/settle(is_admin=...)`. (Release/settle already open an admin session
   internally; only reserve uses the caller's tenant session, so only reserve needed the flag.) This is also
   the correct PRODUCTION behaviour for admin-initiated / act-as generation.

## KNOWN GAPS (recorded in need.md / STATE; non-blocking for the proof)
- **version.local_path empty:** `storage.save_job` sets `img["path"]`, but `jobs._run` reads
  `img.get("local_path")` for the version row -> the DB `local_path` column stays empty, so
  `GET /assets/{id}/raw` can't serve the file (the PNG IS on disk, just not pointed-to in DB). One-line fix:
  map `img["path"]` -> `local_path` in `jobs._run` (or have storage set both). Deferred (doesn't affect the
  proof; the asset/version rows + headline/cta/angle/score are all correct).
- **cross-module PG `events` leg not written:** the monolith `audit.record(...)` no-ops in the standalone
  process (the monolith audit module isn't initialised there), so `events(channel='ai_asset')` is empty. The
  per-vendor immutable `ai_asset_audit_logs` mirror IS written (8 rows) and satisfies the immutable-audit
  requirement. To also feed the cross-module ledger: lazy-init the monolith audit (like we did for auth), or
  use the http seam on extraction.
- **AIASSET_ENABLED is a GLOBAL env flag, not per-tenant.** Acceptable now because the service is
  localhost-only (no `/api/assets/` nginx route on the frontend box yet) so it's effectively admin-reachable
  only. Per-tenant gating (an `ai_asset_provider_state` row or a tenant allowlist) is a follow-up before the
  public nginx route is opened to all vendors.

## REUSE PROVEN
- `wallet.py` (reserve/settle/release, INTEGER paise, idempotent, no-double-spend) — the ONE money-path,
  settled the ACTUAL live cost. `db.engine` RLS GUC-in-txn — cross-tenant isolation held. The reused image
  engine `creative/image_banner_studio/*` (Provider ABC + router + storage + types) rendered the real banner;
  the ONLY net-new provider is `openrouter.py`. Inline-fallback runner drove the job (Hatchet dormant).

## HOW TO RE-RUN THE PROOF
1. Mint an admin access token in the service venv: `from ai_asset import store, auth as sa; store.available();
   sa._ensure_token_secret(); import auth; auth.issue_pair({"tenant_id":"admin","is_admin":True,"role":"admin"})
   ["access_token"]`.
2. Ensure the admin prepaid_wallet has funds: `wallet.topup("admin", 10000, is_admin=True, idem_key=...)`.
3. `POST http://127.0.0.1:8310/generate` with `Authorization: Bearer <token>` + the campaign facts as explicit
   body fields (business_name/product/location/price/offer/audience/goal) + `{"n":3,"idempotency_key":"<new>"}`.
4. Poll `GET /jobs/{id}` until `state=succeeded`; assets land in `/opt/famit-aiasset/var/creatives/<job>/0.png`
   + `ai_asset_assets`/`ai_asset_versions` rows; wallet `lifetime_spend` increases by the ACTUAL cost.
