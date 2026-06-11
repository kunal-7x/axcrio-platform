# Wave build — UNIT B3: AI MANAGER CREATIVE WIRING (voice/chat -> real banners) ✅ PASSED

Date: 2026-06-11 · Box: famit@168.144.153.145 (backend, NO git) · App: /opt/famit-agent · Asset svc:
/opt/famit-aiasset (:8310). State ledger: `droplet_work/B3_CREATIVE_WIRING_STATE.md`.

## WHAT SHIPPED
Pointed the parked workforce `creative.*` adapters at the LIVE AI Asset Service so an AI-Manager command
("create N ad banners for <campaign>") generates a REAL banner via the asset service — credit-gated (the
asset service owns the money-path), NO double-charge, audited, isolation intact, ZERO regression. PROVEN
end-to-end through the Test Console (`POST /ai-manager/commands/test` -> `/execute`) for the admin tenant.

## THE FLOW (verified)
Test Console `POST /ai-manager/commands/test {text}` -> Groq NLU maps "Create 2 ad banners for the
Codename Joy 3.0 campaign" -> intent `creative.generate_banner`, risk=money(3), requires_pin, slots
{count:2, campaign:"Codename Joy 3.0"} -> command cached. `/commands/{id}/execute {pin:2468}` -> firewall
`check_pin` -> mint step-up -> `ai_manager.delegate.execute` -> `workforce.run_agent(role="creative")` ->
StubPlanner reads `task['plan']` -> runner gate (creative money but amount_minor=0 so wallet NOT reserved
workforce-side) -> `catalog._creative_generate_image(args, ctx{run_token})` -> `transport.call_service(
POST /generate, base=:8310, Bearer run_token)` -> Asset Service 2-stage prompt -> OpenRouter
gemini-2.5-flash-image -> real PNG + reserve/settle ACTUAL -> returns job -> AIM status `executed/done`.

## THE 4 FILES CHANGED (box source-of-truth; backups *.B3bak.20260610-215522; all py_compile OK)
1. `workforce/config.py` (md5 6744743628…): + `asset_service_base()` -> env `AIASSET_LOOPBACK_BASE`
   default `http://127.0.0.1:8310`.
2. `workforce/tools/transport.py` (md5 2ccb4b5b60…): + `call_service(method, path, *, run_token, base,
   json, params, timeout=30)` — same Bearer-run_token auth as `call()` but ARBITRARY base (the standalone
   asset service); 30s timeout (image gen is slow); guards `no_run_token`; NEVER raises.
3. `workforce/tools/catalog.py` (md5 9bf8e97e5f…): re-pointed creative adapters from the DEAD
   `/media/video/jobs` + `/media/image/generate` to the LIVE asset `POST /generate`. New `_asset_generate(
   args, ctx, *, asset_type)` maps AIM slots -> the /generate payload (campaign_id, count, instruction,
   platform, language, + explicit campaign facts business_name/industry/product/location/price/offer/
   audience/goal/style/size, idempotency_key). `_creative_generate_image` -> asset_type=banner (the
   real-banner path); `_creative_generate_video` -> asset_type=video_cover (cover/hero only, full video
   out-of-scope per integrations spec); brochure shares the image fn. 503->not_configured park,
   402->insufficient_credits, settles via the asset svc so `actual_spend_minor=0` workforce-side. + import
   `from .. import config as _cfg`.
4. `ai_manager/delegate.py` (md5 f6d4a71d4d…): TWO fixes that made the chain actually execute —
   (a) `_task_for` now also emits `task['plan']=[one]` mirroring `actions` (the workforce **StubPlanner
   reads `task['plan']`, NOT `task['actions']`** — without this the planner saw no plan and ran nothing;
   pre-existing latent gap, harmless while creative was parked). (b) `execute()` now MINTS the per-run
   loopback token via `transport.mint_run_token(tenant_dict)` and threads `run_token=` into `run_agent`
   (it was never passed -> empty Bearer -> asset svc 401). Token derived from the AUTHENTICATED tenant_dict
   (RT-3), never a model field.

## WHY NO DOUBLE-CHARGE (load-bearing — single money-path)
- Workforce `recompute_spend_minor(creative)` = `args.get("amount_minor") or 0` = **0** (creative args have
  no amount_minor) -> runner's reserve branch `if gate.money and gate.amount_minor>0` is SKIPPED -> the
  workforce wallet is NEVER charged for creative.
- The AI ASSET SERVICE is the sole money-path: `jobs.submit -> billing.reserve(reserve:job:<id>) ->
  settle ACTUAL(settle:job:<id>)`, per-job idem keys, F4 ON CONFLICT. The adapter returns
  `actual_spend_minor=0` (asset svc authoritative on cost).

## LIVE PROOF (admin tenant, real spend)
- Test parse: "Create 2 ad banners for the Codename Joy 3.0 campaign" -> `creative.generate_banner`,
  risk money(3), requires_pin, count=2, campaign extracted. PIN `2468` -> execute -> `{status:"executed",
  execution_result:{status:"done", run_id:"run_065667a6e9"}}`.
- Asset job `gj_87f260bf3bbd43f0` -> **state=succeeded**. Real PNG `0.png` **1,214,550 bytes (1.2MB)**,
  1200x628, provider=`openrouter` model `google/gemini-2.5-flash-image`, `estimated:false`, cost from live
  `usage.cost=0.0387588 USD`. **Auto-uploaded to DO Spaces** (`capsy-recordings.sgp1...`, storage=spaces —
  Spaces creds now active).
- WALLET (no double-charge): ONE clean cycle — `hold +755 (reserve:job:gj_87…)` then
  `hold_settle -755 + charge -676 (settle:job:gj_87…)`, balance_after 7972, held=0, lifetime_spend 2028.
  Estimate 755 -> actual 676 -> 79 auto-refunded.
- AUDIT: immutable `ai_asset_audit_logs` rows `asset.generate.submit -> run -> succeeded`.
- IDEMPOTENT: re-`execute` same command id -> `command not found` (terminal cmd popped from `_TEST_CMDS`;
  no 2nd job, job count + wallet unchanged at 5 / 2028).
- ISOLATION: asset `/generate` unauth->401, bad-bearer->401, only `/status`->200; tenant token-derived
  (body tenant_id ignored, A4-proven); RLS as `__nobody__` sees 0 admin jobs.
- NO-INVENT held: slot carried the campaign NAME (not the resolved id) -> asset svc got bare explicit
  fields -> generic benefit-angle copy ("Unlock Your Potential"), NO fabricated price/RERA — the safe
  NO-INVENT default working as designed.

## REGRESSION GATE (pre + post restart) — PASS
Core `/campaigns /me /leads` 200, `POST /run/preview` 200; famit-caller + famit-agent + famit-aiasset all
ACTIVE; ZERO 5xx/Tracebacks in caller journal since restart; caller.py AST OK; agent.py byte-untouched.
Restarted **famit-caller ONLY** (workforce+AIM run in-process in caller.py). Rollback = restore *.B3bak.* +
restart famit-caller.

## FOUNDER-BLOCKED / FOLLOW-UPS (recorded in need.md)
1. **Per-tenant asset gating** is still a GLOBAL `AIASSET_ENABLED` env (admin-only today). Before opening
   creative to all vendors via voice, add a per-tenant allowlist / `ai_asset_provider_state` row (need.md
   item). Localhost-only + AIM-PIN-gated mitigates for now; RLS+token-derivation isolation IS enforced.
2. **Campaign name->id resolver:** the AIM slot carries the campaign NAME; the asset svc enriches context
   from a real `campaign_id` (U4 reader) only when an id is passed. A deterministic name->id resolver in
   the AIM (the brain's "campaign_ref resolver") would feed the full campaign facts (price/offer/location)
   so banners carry verbatim campaign facts instead of generic copy. NOT a defect (NO-INVENT-safe today) —
   a quality upgrade. (Founder-independent; future unit.)
3. **A real Meta-approved template** for cold WhatsApp sends + **confirm the MedFlow WABA number**
   (+91 97550 40013) — unchanged from WHATSAPP_GOLIVE; needed only to PUBLISH a generated banner to a cold
   contact, not for the creative-generation proof.
