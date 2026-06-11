# wave-build-wa-builder — WhatsApp-Builder module (Unit B1)

> Durable build report. Append-only. Companion to `memory/brain/mod-whatsapp-builder.md`
> and the spec `design/wa-template-ai-backend.md`.

## 2026-06-11 — BUILT (offline-green) + caller.py mount staged

**What shipped** — a thin `whatsapp_builder/` MODULE (NOT a new service; droplets 3/3, AIM
in-process precedent). Two-layer brain: the LLM (reused Groq→OpenRouter seam) PROPOSES; a
deterministic **Meta-compliance validator is the AUTHORITY**. Files (all NEW, bare imports,
deploy root `/opt/famit-agent/whatsapp_builder/`):

- `validate.py` (THE AUTHORITY) — Meta 2026 grammar (name `[a-z0-9_]`≤512; lang code; header
  TEXT≤60-≤1var OR media; body≤1024 + `{{n}}` sequential-from-1 gap-free no-dup non-adjacent,
  not at start/end, example-per-placeholder; footer≤60 no-var; buttons≤10 / ≤2 URL / ≤1 phone,
  text≤25, https URL ≤1 trailing var, E.164 phone) + **category auto-classify**
  (MARKETING/UTILITY/AUTHENTICATION, weighted-phrase, validator decides not the model) +
  **NO-INVENT scrub** (regex strips fabricated price/RERA[+modifier]/%off/guarantee/phone NOT in
  the campaign context → `needs_fact`, cannot be approved) + heuristic `score` + `can_approve`.
- `personalize.py` — named tokens (`{{name}}`…) → Meta positional `{{1}}/{{2}}` (first-seen order,
  repeated token keeps index) + `ai_wa_personalization` binding (lead_field/fallback/sample) +
  `examples_for` / `sample_render` / `live_render` (missing field → fallback, never a literal `{{2}}`).
- `context.py` (read-only campaign context, injectable loader for offline) + `prompt.py`
  (schema-constrained NO-INVENT prompt + industry CTA few-shots + performance-bias).
- `llm.py` — reuse Groq→OpenRouter (JSON-mode, 1-retry-per-provider, never raises, dormant);
  httpx imported lazily so the offline test patches it to RAISE. **OpenRouter env = founder typo
  `OPNEROUTER_API_KEY`** (fallback `OPENROUTER_API_KEY`).
- `credit.py` — `wallet.reserve/settle/release` (resource_type=`wa_template_gen`, idem_key);
  no-wallet → proceed free; failed gen → release (refund), never charges.
- `generate.py` — orchestration; `structure.py` — sequence + CTA map + deterministic templated
  FALLBACK (valid Meta shape, no AI copy) so generation works with ZERO creds.
- `store.py` — `ai_wa_*` PG via `db.engine.session(tenant_id,is_admin)` (RLS) + JSONL fallback.
- `meta_submit.py` (DORMANT submit seam, correct `POST /{waba}/message_templates` body) ;
  `audit_hook.py` (channel=`whatsapp_builder`, actor-first, redacted, no-op if absent).
- `__init__.py` public API (generate/list/get/select/regenerate/approve/reject/submit-to-meta/
  attach-banner/meta-status/status) ; `attach_banner` is creative.* tenant-checked (pluggable
  resolver; cross-tenant asset refused).
- `router.py` — token-deriving `build_router(resolve_tenant, can, need_auth, forbidden, firewall)`
  (funnels/workflow shape) → 11 routes under `/whatsapp/campaign`. Tenant ALWAYS from token.
- `db/ddl_ai_wa.sql` — 4 FORCE-RLS tables (admin-GUC, idempotent, standalone like ddl_wallet.sql).

**caller.py mount** — appended after the funnels block (the last mount). Import-guarded, default
OFF `FEATURE_WHATSAPP_BUILDER` → byte-identical live path. Mounts ONLY the token-deriving
build_router (no bare body-tenant router exists). `caller.py` re-parses clean (`ast.parse` OK).

**Validator smoke (standalone):** fabricated `Rs 50,00,000` + `RERA Approved` + `20% off` NOT in
context → all 3 flagged, stripped from body, template → `needs_fact` (cannot approve). Grammar:
body>1024 / adjacent `{{1}}{{2}}` / footer-variable / 30-char button each caught with a specific
error; a clean template valid. Category: promo→MARKETING, "your enquiry details"→UTILITY,
OTP+"do not share"→AUTHENTICATION.

**Offline acceptance test** `whatsapp_builder/tests/test_builder_offline.py` — **ALL 13
ASSERTIONS PASSED, exit 0**, httpx patched-to-RAISE the whole run (proves ZERO network), env
unset (dormant), JSONL store (no Postgres), wallet/audit spied in-memory. Covers: dormant
fallback · LLM gen (3 templates ≥2 variations + plan + CTA + media) · grammar · renumber+binding ·
category · NO-INVENT · credit reserve/settle/release + idem no-double-reserve · select+approve
gate (needs_fact refused) · attach-banner tenant-check (cross-tenant refused) · RLS scoping ·
submit dormant + payload shape · learning bias · never-raises fuzz.

**Bug fixed during build:** dict-spread order in `approve`/`attach_banner` refusal returns
(`{"status":"refused", **tpl}` let `tpl["status"]` overwrite "refused" → flipped to `{**tpl, "status":"refused"}`).

## DEFERRED (orchestrator wiring, when going live)
- Apply `db/ddl_ai_wa.sql` via psql as `famit_app` (off the Alembic chain).
- Register the `whatsapp.generate_templates` ToolSpec in the AI-Manager / Workflow ToolRegistry.
- Wire the `/whatsapp/inbound` status webhook → `ai_wa_templates.metrics` writeback (learning loop).
- Banner last-mile: resolve attached AssetRef → Meta media upload (resumable header_handle).
- Set `FEATURE_WHATSAPP_BUILDER=1` + restart only after the schema is applied.

## CREDS (per WHATSAPP_GOLIVE.md) — generation runs TODAY with #1/#3 already on the box
1 LLM (Groq pool + OPNEROUTER) PRESENT · 2 Meta token (submit/send) PRESENT-pending-.env-update ·
3 wallet balance (F4) live · 4 a real approved Meta template = the #1 cold-send blocker (Meta's gate).

## 2026-06-11 — UNIT C2 GO-LIVE (schema applied · ToolSpec registered · flag ON · smoke GREEN)
Box `famit@168.144.153.145`, caller=uvicorn :8209 (`/opt/famit-agent/caller.py`), DB `famit_app@127.0.0.1/famit`.
ALL deferred items above DONE except the inbound-metric writeback + banner last-mile (still deferred).

1. **SCHEMA APPLIED** — `psql -U famit_app -f whatsapp_builder/db/ddl_ai_wa.sql` (md5 e854c922…, exit 0,
   idempotent). The 4 `ai_wa_*` tables now EXIST (`suggestion_bundles/templates/variations/personalization`);
   each `relrowsecurity=t` AND `relforcerowsecurity=t`; isolation policy present per table. ⚠ The brain's
   B1 note claimed the DDL was "standalone-applied" — it was NOT (pre-state count=0); the C2 task was right,
   verified-don't-trust. **Isolation PROVEN:** seed tenantA row → read as tenantB (GUC app.tenant_id=B,
   is_admin=0) = 0 rows; read as tenantA = 1; no-GUC-at-all = 0 (FORCE-RLS default-deny has teeth); seed cleaned.

2. **ToolSpec `whatsapp.generate_templates` REGISTERED** (the BOX catalog is source-of-truth — it carries the
   B3 creative wiring; local droplet_work/ was stale). Edits (backed up `*.C2bak.20260611`):
   - `workforce/tools/catalog.py` — `_whatsapp_generate_templates(args,ctx)` → loopback
     `POST /whatsapp/campaign/{campaign_id}/generate-templates` (campaign_id REQUIRED; `_result_parkable`
     → clean `not_configured` when flag OFF) + `ToolSpec(side_effecting,money,risk_class=risky)`. spend=0 (the
     builder meters its OWN credit, like the asset svc → no double-charge).
   - `workforce/tools/stub_tools.py` — mirror stub (same name/scopes/risk/money; registries stay symmetric).
   - `workforce/roles.py` — granted to `whatsapp` (primary owner) + `ops` (the AIM generalist delegate target).
   Verified on box venv: present in LIVE+STUB registries with correct gates; `policy.resolve(whatsapp|ops)`
   admin → can_use=True; unauthed `{}` tenant → False; scope→`write` action (admin/manager-gated, same as
   every other spend tool). Workforce offline test 14/15 (the 1 fail = `test_import_safe_and_dormant` asserts
   `llm.status==not_configured`, but the box HAS Groq creds → pre-existing env artifact, unrelated to C2;
   `test_D_cross_tenant` + `test_role_registry_default_deny` PASS).

3. **FLAG ON + RESTART** — appended `FEATURE_WHATSAPP_BUILDER=1` to `/opt/famit-agent/.env` (`.env.C2bak.*`);
   `systemctl restart famit-caller` → active, clean startup.

4. **SMOKE GREEN** — `POST /whatsapp/campaign/c17e55e9f3/generate-templates` (admin "Codename Joy 3.0",
   X-Auth admin) → **HTTP 200** (was 404). `status:accepted`, `model:groq:meta-llama/llama-4-scout-17b-…`,
   **3 templates** (benefit_focus/social_proof/urgency), all `category=MARKETING` (validator auto-classify),
   `compliance.valid=true errors=[] no_invent_flags=[]` (validator authority, NO fabricated facts), named→
   positional `{{1}}` + examples. Persisted: `ai_wa_templates` = 6 admin rows (FORCE-RLS). Money proven: hold
   id99 `resource_type=wa_template_gen amount=4.0 settled=4.0` (reserve Rs4→settle Rs4, no stuck hold, no
   double-charge). Route auth: no-X-Auth → 401 (no leak); admin list → 200.

**TWO BUGS FOUND+FIXED during go-live (both REQUIRED, both backed up `*.C2bak.20260611`):**
- **`whatsapp_builder/router.py`** — `from fastapi import APIRouter,Request,Body` lived INSIDE `build_router`,
  so with `from __future__ import annotations` FastAPI could not resolve the STRING annotation `"Request"`
  against the module globals → mis-classified `request` as a required QUERY param → **422 `query.request
  required`** on every call (and `/openapi.json` 500 `PydanticUserError ForwardRef('Request') not fully
  defined`). FIX = hoist the FastAPI import to MODULE scope (guarded; booking/router.py uses this exact
  pattern). After fix: route 200 + `/openapi.json` 200 (156 paths) + all 11 builder paths schema-valid.
- **`whatsapp_builder/credit.py` + `generate.py`** — `credit.reserve()` called `wallet.reserve()` WITHOUT
  `is_admin`, so its in-txn INSERT into `wallet_idempotency` (is_admin=0 GUC session) was REFUSED by FORCE-RLS
  (`new row violates row-level security policy for table "wallet_idempotency"`) → reserve returned None →
  spurious **`insufficient_credits`** even with Rs79.72 available. wallet.settle/release already run
  is_admin=True internally; only reserve takes the caller flag (the asset svc reserves as admin for the same
  reason). FIX = thread `is_admin` through `credit.reserve` and pass `is_admin=is_admin` from
  `generate_templates`. After fix: reserve→settle clean (hold id99).

**REGRESSION GREEN:** core `/me /campaigns /leads` 200, `POST /run/preview` 200, `/health` 200; services
active incl. **famit-bridge (voice)** + famit-aiasset; ZERO request-path 5xx; agent.py + the live
`/whatsapp/send` path BYTE-UNTOUCHED. ROLLBACK = flag OFF (`sed FEATURE_WHATSAPP_BUILDER=0` + restart) +
restore `*.C2bak.20260611` (router/credit/generate/catalog/stub_tools/roles) — all backups on box.

**STILL DEFERRED:** `/whatsapp/inbound` status-webhook → `ai_wa_templates.metrics` learning writeback · banner
last-mile (attach AssetRef → Meta resumable header_handle) · submit-to-meta + cold-send still gated on a real
approved Meta template (founder's Meta gate, only `hello_world` exists).
