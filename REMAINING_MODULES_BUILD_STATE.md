# REMAINING MODULES — BUILD STATE & DEFERRED-WIRING CHECKLIST

Date: 2026-06-10. Scope: the 9 feature modules just built under `droplet_work/`.
All are ADDITIVE, dormant-until-creds, **routers DEFINED-NOT-MOUNTED**, no `caller.py`/`agent.py`
edit, no deploy, no git. Foundation they compose: F1 Postgres/RLS · F2 CRM/brain/KB ·
F4 firewall(PIN+step-up)/wallet/immutable-audit · `workforce/` role agents.

> This file is the single source of truth for the next session's **final-wiring** step (the
> sequential spine edit to `caller.py`). Read this before touching `caller.py`.

---

## PER-MODULE STATE

### 1. ai-manager — `droplet_work/ai_manager/`
- **Files:** `__init__.py`, `config.py`, `registry.py`, `identity.py`, `firewall_bridge.py`,
  `audit_bridge.py`, `delegate.py`, `state_machine.py`, `intent/driver.py` (dormant),
  `otp/sender.py` (dormant), `endpoints.py` (router, not mounted), `inbound_agent.py`
  (deferred LiveKit stub), `wiring/caller_endpoints.diff` + `wiring/sip_dispatch.md` (un-applied),
  `tests/test_offline.py`, `AI_MANAGER_STATE.md`.
- **Composes:** firewall (PIN `check_pin` + scoped HS256 step-up: S2 login, fresh per-action S6) ·
  audit (`aimanager_voice.*` immutable trail) · `workforce/` as delegation target
  (`run_agent(role=<worker>, trigger="manager_voice")`, proven end-to-end with a real run_id) · brain.
- **Router:** prefix `/ai-manager`. `GET /status`, `POST /numbers`, `POST /numbers/{id}/verify`,
  `GET /numbers`, `GET /numbers/lookup`, `POST /numbers/{id}/grants`, `POST /numbers/{id}/revoke`,
  `POST /sessions`, `GET /sessions`.
- **Mount surface:** **bare-OK.** Module-level `endpoints.router`; tenant is token-derived via a lazy
  `caller.resolve_tenant` import inside the routes (NOT from body). Risky mutations call firewall step-up.
- **Creds awaited:** `AIM_SERVICE_TOKEN` (dashboard service auth); voice front `AIM_VOICE_DID`,
  `AIM_VOICE_SIP_TRUNK_ID`, `AIM_VOICE_AGENT_NAME`; `AIM_OTP_PROVIDER`, `AIM_LLM_PROVIDER`, `AIM_API_BASE`.
  LLM delegation uses shared `GROQ_API_KEY*`.
- **Deferred:** LiveKit voice front (`inbound_agent.py` stub) + SIP dispatch (`wiring/sip_dispatch.md`).
  The command CALL path is LiveKit/chat, NOT HTTP — it does not pass through `caller.py`.

### 2. workflow-studio — `droplet_work/workflow-studio/workflow/`
- **Files:** `dsl.py`, expr-sandbox, `compiler.py` (graph-dominator + tool-resolve + immutable freeze),
  `nodes.py` (10 executors), `interpreter.py` (single durable engine-agnostic interpreter),
  `engine.py` (Hatchet binding, dormant), store (InMemory+Pg) + `schema.sql` (6 RLS tables),
  `events.py` bridge, `analytics.py`, `templates.py`, `audit_bridge.py`, `config.py`, `endpoints.py`,
  `__init__.py`; `workflow_wiring.diff` (un-applied, the only `caller.py` change).
- **Composes:** the single durable interpreter (dominator check, expr sandbox, immutable audit,
  idempotent crash-replay) · F4 wallet/firewall/approval surface (owns it; funnels delegate here) ·
  Hatchet F3 box `10.122.0.3:7077` (dormant) · spine event emits → workflow triggers.
- **Router:** prefix `/workflows` (set inside build_router). 18 route objects / 16 paths:
  `GET/POST /workflows`, `GET /status`, `GET/POST /templates` + `POST /templates/{id}/instantiate`,
  `GET /runs`, `GET /runs/{id}`, `POST /runs/{id}/{approve,reject,cancel}`, `POST /killswitch`,
  `GET/PUT /workflows/{id}`, `POST /workflows/{id}/{validate,publish}`.
- **Mount surface:** **`build_router(resolve_tenant, can, need_auth, forbidden, firewall)` — REQUIRED.**
  ⚠ NEVER mount the bare module-level `workflow.endpoints.router` (it reads `tenant_id` from the body
  for decoupled testing → cross-tenant escalation; RLS can't save it, the GUC gets set to the attacker's
  value). build_router derives tenant from the TOKEN and enforces `can(role,action)` on every write;
  killswitch admin-only; approve verifies the firewall step-up token bound to the authed tenant.
  Also call `attach_event_bridge(app)` after include.
- **Creds awaited:** `HATCHET_CLIENT_TOKEN`, `HATCHET_CLIENT_HOST_PORT` (engine dormant → in-process
  interpreter until set). Tuning: `WORKFLOW_STORE`, `WORKFLOW_PACKS_DIR`, `WORKFLOW_DEFAULT_TENANT_CONC`.
- **Deferred:** Hatchet durable engine activation. Per-tenant runtime **killswitch** exists (NOT a mount flag).

### 3. ads-engine — `droplet_work/ads_engine/`
- **Files (18):** `__init__.py`, `config.py`, `base_logging.py`, `metrics.py`, `guardrails.py`,
  `store.py`, `schema.sql`, `creative.py`, `planner.py`, `meter.py`, `service.py`, `endpoints.py`,
  `providers/{__init__,base,noop,meta,google}.py`, `tests/test_ads_offline.py`, `ADS_ENGINE_STATE.md`.
  (UNDERSCORE pkg; distinct from pre-existing `creative/ads_engine`.)
- **Composes:** firewall — `guardrails.require_approval` → injected
  `firewall.verify_step_up_token(token,"spend",expected_sub=tenant_id)`, **fails CLOSED** if firewall
  absent while approval required (bad/missing token → `blocked_not_approved`, provider create never runs) ·
  wallet — `approve_campaign` → `wallet.reserve(...)` on live path only (None → `blocked_insufficient_funds`;
  accrue-and-settle-ON-PAUSE, no double-spend) · immutable audit (`channel="ads"` on every op).
- **Router:** prefix `/ads`. `GET /health`, `POST /campaigns/propose`, `GET /campaigns`,
  `GET /campaigns/{plan_id}`, `POST /campaigns/{plan_id}/approve` (X-Step-Up header),
  `POST /campaigns/{plan_id}/pause`, `POST /optimize`.
- **Mount surface:** **bare-OK.** Module-level `endpoints.router` (prefix `/ads`); auth via lazy
  `caller.resolve_tenant`/`need_auth`/`can` (`_auth_helpers()`); tenant token-derived, NOT from body.
  Mutating routes require `can(t,"write")` (manager+). Defense-in-depth: optionally also wrap approve with
  `firewall.require_step_up` at the edge (deferred).
- **Creds awaited:** Meta — `META_ADS_ACCESS_TOKEN`, `META_ADS_ACCOUNT_ID`, `META_ADS_APP_ID`,
  `META_ADS_APP_SECRET`. Google — `GOOGLE_ADS_DEVELOPER_TOKEN`, `GOOGLE_ADS_CLIENT_ID`,
  `GOOGLE_ADS_CLIENT_SECRET`, `GOOGLE_ADS_REFRESH_TOKEN`, `GOOGLE_ADS_CUSTOMER_ID`,
  `GOOGLE_ADS_LOGIN_CUSTOMER_ID`. `LLM_ROUTER_URL` for creative. Until set → `noop` provider.
- **Deferred:** live Meta/Google provider activation (noop until creds).

### 4. media-gen — `droplet_work/media_gen/`
- **Files:** `__init__.py`, `STATE.md`, `router.py` (unified `build_router()`, not mounted),
  `spaces.py` (DO Spaces artifact writer, dormant when `SPACES_*` unset); `video/` =
  `schema.py`, `config.py`, `store.py`, `providers.py` (fal|replicate|luma|higgsfield|selfhost|generic +
  license gate), `pricing.py`, `safety.py`, `cost.py`, `approval.py`, `audit_hook.py`, `client.py`;
  `image/__init__.py` + `threed/__init__.py` (thin re-exports of `creative/image_banner_studio` +
  `creative/threed_model` — no duplication); `tests/test_video_offline.py`.
- **Composes:** the lower ENGINE layer the `creative/*` STUDIO layers wait on. Video is the net-new build:
  cost estimate→cap→reserve/settle/release (wallet seam) · pre-submit safety/likeness screen ·
  human-approval gate · spine audit bridge · per-provider signed webhook verify.
- **Router:** prefix `/media`. `GET /status`, video: `POST /video/jobs`, `GET /video/jobs`,
  `GET /video/jobs/{id}`, `GET /video/jobs/{id}/poll`, `POST /video/jobs/{id}/{approve,reject,cancel}`,
  `POST /video/webhook` (provider-signed, no auth); image: `GET /image/status`, `POST /image/generate`;
  threed: `GET /threed/status`.
- **Mount surface:** **`build_router()` (NO args).** ⚠ It does NOT inject an auth seam — several routes
  read `tenant_id=body.get(...)`. Before mounting, the next session MUST either (a) refactor
  `build_router` to accept and apply `resolve_tenant/need_auth/can` (preferred — mirror forms-surveys),
  or (b) gate it admin-only. Do not mount as-is for tenant traffic. Webhook is intentionally unauthed
  (provider signature verified inside).
- **Creds awaited:** artifacts — `SPACES_KEY`, `SPACES_SECRET`, `SPACES_BUCKET`, `SPACES_REGION`,
  `SPACES_ENDPOINT`, `SPACES_PUBLIC_BASE`. Video providers — `VIDEO_PROVIDER`, `VIDEO_API_KEY`
  (or `REPLICATE_API_TOKEN`/`LUMA_API_KEY`/`HIGGSFIELD_API_KEY`/`VIDEO_SELFHOST_TOKEN`).
- **Deferred:** the auth-seam refactor on `build_router` (see mount surface) — treat as a mount-time fix.

### 5. booking — `droplet_work/booking/`
- **Files:** `__init__.py`, `config.py`, `models.py` (own SQLAlchemy Base, 5 tables), `rls.sql`
  (ENABLE+FORCE RLS + anti-double-book partial unique index + grants), `identity.py`, `core.py` (engine),
  `calendar_sync.py` (Google Calendar dormant), `router.py` (not mounted),
  `tests/conftest.py` + `tests/test_booking.py` (25), `STATE.md`.
- **Composes:** F1 RLS via `db.engine.session(tenant_id,is_admin)` GUC (degrades to `not_configured`
  when PG down) · F2 CRM (bookings link to deterministic `contact_id`; `crm.record_timeline(kind='booking')`
  into the pre-cut crm-core §3.3 slot, no-op until crm ships) · firewall (`check_pin` on reminder
  actuation, FAIL-CLOSED if absent/unset) · wallet (spend-gated reminders
  `reserve(idem_key='booking_reminder:<rid>')`, no double-spend) · immutable `booking_events` ledger.
- **Router:** prefix `/booking`. `GET /status`, `POST /resources`, `GET /availability`, `POST /book`,
  `GET /bookings`, `GET /bookings/{id}`, `POST /bookings/{id}/{reschedule,cancel,complete}`, `POST /tick`.
- **Mount surface:** **`include_router(router, ...)` BUT override `get_ctx` at mount.** ⚠ The default
  `get_ctx` reads the `X-Tenant-Id` header (spoofable, dev-only). The mount step MUST replace `get_ctx`
  with `caller.resolve_tenant`-backed resolution (FastAPI dependency_overrides) before serving tenant
  traffic. Do NOT mount with the default header-trust ctx.
- **Creds awaited:** `BOOKING_REMINDERS_ENABLE` (reminder loop); Google Calendar sync —
  `GOOGLE_CALENDAR_CLIENT_ID`, `GOOGLE_CALENDAR_CLIENT_SECRET`, `GOOGLE_CALENDAR_REFRESH_TOKEN`,
  `GOOGLE_CALENDAR_ACCESS_TOKEN`. Var dir `FAMIT_VAR`.
- **Deferred:** Google Calendar two-way sync (dormant port); reminder cron loop (runs every 60s once enabled).

### 6. payments — `droplet_work/payments/`
- **Files:** `schema.sql` (3 tables: payment_intents/events/followups, FORCE-RLS admin-GUC, BIGINT minor
  units), `core.py`, `router.py` (not mounted), `_http.py`, `__init__.py`,
  `providers/{__init__,base,razorpay,stripe}.py`, `tests/{_smoke_payments.py,_box_roundtrip.py,...}`,
  `STATE.md`.
- **Composes:** `db.engine` RLS tenant sessions (P1 admin-GUC) · firewall — refund/risky guarded by
  `firewall.require_step_up(request,"spend",tenant)`, PASS-THROUGH when `FIREWALL_ENABLE` off · immutable
  payment_events ledger · provider webhooks signature-verified inside core (machine call, not tenant-auth).
- **Router:** mounted at prefix `/payments`. `GET /health`, `POST /links`, `GET /links`,
  `GET /links/{id}`, `GET /links/{id}/{invoice,receipt}`, `POST /links/{id}/{mark-paid,refund}`,
  `GET /followups`, `POST /webhooks/{provider}` (signature-verified, dormant → `not_configured` no-op).
- **Mount surface:** **`payments.router.wire(resolve_tenant, can, need_auth, forbidden, firewall=...)`
  THEN `include_router(payments.router.router, prefix="/payments")`.** Must `wire(...)` BEFORE include.
- **Creds awaited:** Razorpay — `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, `RAZORPAY_WEBHOOK_SECRET`.
  Stripe — `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`. Select via `PAYMENTS_DEFAULT_PROVIDER`.
  Tuning: `PAYMENTS_LINK_TTL_S`, `PAYMENTS_FOLLOWUP_MAX_ATTEMPTS`, `PAYMENTS_FOLLOWUP_BACKOFF_S`.
- **Deferred:** live provider activation (dormant → `not_configured`).

### 7. support — `droplet_work/support/`
- **Files:** `schema.sql` (`support_tickets`+`support_messages`, FORCE-RLS admin-GUC, deterministic PKs),
  `core.py` (thread-identity grouping, idempotent inbound, KB-grounded-or-escalate draft, escalation/
  handover with §8 AI-summary, claim/resolve/human-reply), `sentiment.py` (deterministic lexicon, EN +
  Hinglish/Devanagari, no LLM/network), `agent.py` (`SupportAgent` reply-service + `triage()`),
  `router.py` (not mounted), `__init__.py`, `tests/_smoke_support.py`.
- **Composes:** F2 KB (`kb.retrieve` RAG, grounded-or-escalate) · workforce `support` RoleSpec
  (system_prompt + `handover_on` sourced, not re-declared) · shared dormant LLM driver
  (`workforce.llm.driver`; extractive KB draft until creds) · immutable audit (channel='ai') ·
  CRM (`upsert_contact` + contact_id link, best-effort).
- **Router:** mounted at prefix `/support`. `GET /health`, `POST /inbound`, `GET /tickets`,
  `GET /tickets/{id}`, `POST /tickets/{id}/{draft,reply,escalate,claim,resolve}`,
  `POST /webhooks/{channel}`.
- **Mount surface:** **`support.router.wire(resolve_tenant, can, need_auth, forbidden, firewall=...)`
  THEN `include_router(support.router.router, prefix="/support")`.** Must `wire(...)` BEFORE include.
- **Creds awaited:** `GROQ_API_KEY*` / `ANTHROPIC_API_KEY` (LLM draft; extractive KB until set);
  channel ingest — `SUPPORT_VOICE_INGEST_TOKEN`, `SUPPORT_WEB_WIDGET_SECRET`. `FIREWALL_ENABLE`.
  Tuning: `SUPPORT_AUTO_REPLY`, `SUPPORT_CONFIDENCE_FLOOR`, `SUPPORT_KB_TOP_K`, `SUPPORT_OPEN_WINDOW_S`.
- **Deferred:** generative LLM drafting (extractive KB until creds); channel webhook adapters.

### 8. funnels — `droplet_work/funnels/`
- **Files:** `config.py`, `stages.py` (8 canonical stages + STAGE_MAP), `model.py`, `compiler.py`
  (lower FunnelSpec → workflow §3 DSL + auto-gating + stage tagging), `tools.py` (dormant integrations),
  `store.py`, `analytics.py`, `schema.sql` (FORCE-RLS), `__init__.py`, `templates.py` (3 starters),
  `endpoints.py` (not mounted), `funnel_wiring.diff` (deferred), `tests/test_offline.py`,
  `_smoke_funnels.py`, `STATE.md`.
- **Composes:** a funnel COMPILES DOWN to the workflow-studio §3 DSL; publish/run DELEGATE to
  `workflow.publish/run` (the single durable interpreter — inherits dominator check, expr sandbox,
  immutable audit, idempotent crash-replay, F4 wallet/firewall/approval). Reinvents nothing.
- **Router:** prefix `/funnels`. `GET /status`, `GET /templates`, `POST /templates/{id}/instantiate`,
  `GET/POST /funnels`, `POST /validate`, `GET /funnels/{id}`,
  `POST /funnels/{id}/{validate,publish,run}`, `GET /funnels/{id}/analytics`.
- **Mount surface:** ⚠⚠ **NOT A CLEAN MOUNT — DEFERRED BUILD BLOCKER.** `endpoints.py` reads
  `tenant_id=payload.get("tenant_id","")` from the request BODY (line ~14 documents this) and the
  shipped `funnel_wiring.diff` mounts it BARE (`app.include_router(funnels_router)`, no auth injection).
  That is the exact cross-tenant hole workflow-studio's `build_router` was built to close — and delegating
  to `workflow.publish/run` does NOT save it, because the attacker-supplied body `tenant_id` is what flows
  down. **Before mounting**, funnels needs a token-deriving surface (a `build_router(resolve_tenant, can,
  need_auth, forbidden)` like workflow-studio/forms-surveys). DO NOT apply `funnel_wiring.diff` as-is.
- **Creds awaited:** none to run (compiles/runs on the workflow engine). Optional dormant integrations —
  `FUNNELS_LANDING_API_KEY` (`LANDING_KEY`), `FUNNELS_REVIEW_API_KEY` (`REVIEW_KEY`). Kill: `FUNNELS_KILL`.
- **Deferred:** the token-deriving router (mount blocker, above); dormant landing/review integrations.
  Requires `workflow-studio/` on PYTHONPATH (imports `workflow` lazily). Mount workflow BEFORE funnels.

### 9. forms-surveys — `droplet_work/forms-surveys/`  (+ `forms_surveys/` alias)
- **Files:** `schema.sql` (`forms`+`form_submissions`, ENABLE+FORCE RLS admin-GUC-OR-org_id), `core.py`
  (form CRUD, allow-list validation, token→org resolve, public submit pipeline, deterministic survey
  insights, injected hooks), `identity.py` (crm-compatible contact_id, `link_contact`→`crm.upsert_contact`
  read-model-safe), `config.py`, `endpoints.py` (`build_router`, not mounted), `__init__.py`,
  `_bootstrap.py` (hyphenated-package alias loader), `_smoke_forms.py`, `tests/`.
- **Composes:** F1 RLS (`db.engine.session`) · F2 CRM (`upsert_contact`/contact_id — NOT a leads write) ·
  immutable audit (tenant-scoped submit row, server-side) · `ratelimit.allow` on public routes.
  Leads-store write + workflow-trigger emission are injected hooks
  (`core.init(emit_lead=, emit_workflow=, audit=)`), dormant by default.
- **Router:** no prefix (paths absolute). Authed: `GET/POST /forms`, `GET/PUT /forms/{id}`,
  `POST /forms/{id}/rotate-token`, `GET /forms/{id}/submissions`, `GET /forms/{id}/insights`,
  `GET /forms/status`. Public (NO auth, by design): `GET /f/{public_token}` (render — strips org
  internals), `POST /f/{public_token}/submit` (honeypot + allow-list + captcha + strict rate-limit).
- **Mount surface:** **`build_router(resolve_tenant, can, need_auth, forbidden)`.** Authed routes derive
  tenant from token; public `/f/*` routes are intentionally unauthenticated (token-scoped + rate-limited).
  ⚠ Import note: hyphenated dir — import via the `_bootstrap` alias (`import forms_surveys`), NOT a plain
  `import forms-surveys` (illegal identifier). The `forms_surveys/` underscore alias dir exists for this.
- **Creds awaited:** captcha — `FORMS_CAPTCHA_PROVIDER`, `FORMS_CAPTCHA_SECRET`; `FORMS_NOTIFY_ENABLE`.
- **Deferred:** leads-store + workflow-trigger emit hooks (off by default); captcha enforcement.

---

## SINGLE CONSOLIDATED DEFERRED-WIRING CHECKLIST  (next session, in `caller.py`)

This is the sequential spine step. Each `include_router` is additive and behind the existing auth deps.
Do it as ONE ordered pass; wrap every mount in the import-guard pattern so a missing package can never
break startup (precedent: `workflow_wiring.diff`). **Order matters where noted.**

### A. PYTHONPATH / import prep (do first)
1. Add `droplet_work/workflow-studio/` to PYTHONPATH (so `import workflow` resolves; funnels needs it).
2. forms-surveys: import via `forms_surveys` alias (the `_bootstrap` loader), never `import forms-surveys`.

### B. Routers to mount — exact call per module
| # | Module | Mount call | Order/blocker |
|---|--------|-----------|---------------|
| 1 | ai-manager | `include_router(ai_manager.endpoints.router)` — **bare-OK** (token-derived) | — |
| 2 | ads-engine | `include_router(ads_engine.endpoints.router)` — **bare-OK** (`/ads`, token-derived) | — |
| 3 | workflow-studio | `build_router(resolve_tenant, can, need_auth, forbidden, firewall)` → include; then `attach_event_bridge(app)`. **NEVER the bare `router`.** | mount BEFORE funnels |
| 4 | forms-surveys | `build_router(resolve_tenant, can, need_auth, forbidden)` → include (no prefix) | — |
| 5 | payments | `payments.router.wire(resolve_tenant, can, need_auth, forbidden, firewall=...)` → `include_router(payments.router.router, prefix="/payments")` | wire BEFORE include |
| 6 | support | `support.router.wire(resolve_tenant, can, need_auth, forbidden, firewall=...)` → `include_router(support.router.router, prefix="/support")` | wire BEFORE include |
| 7 | booking | `include_router(booking.router.router)` **+ override `get_ctx`** with a `caller.resolve_tenant`-backed dependency (FastAPI `dependency_overrides`). DO NOT mount with default header-trust ctx. | mount-time fix REQUIRED |
| 8 | media-gen | `build_router()` (no args) — **but first** add/apply an auth seam (route reads `tenant_id` from body) OR gate admin-only. | mount-time fix REQUIRED |
| 9 | funnels | ⚠ **BLOCKED.** Bare `funnel_wiring.diff` is a cross-tenant hole (tenant from body). **BUILD a token-deriving `build_router(resolve_tenant, can, need_auth, forbidden)` first**, then mount. Do NOT apply the shipped diff as-is. | build-blocker; mount AFTER workflow |

**Clean bare mounts (2):** ai-manager, ads-engine.
**`build_router` mounts (2 clean):** workflow-studio (+events), forms-surveys.
**`wire()`-then-include (2):** payments (`/payments`), support (`/support`).
**Mount-time security fix required before serving tenant traffic (3):** booking (override get_ctx),
media-gen (add auth seam / admin-gate), funnels (BUILD token-deriving router — true blocker).

### C. Feature flags (default OFF — propose one convention)
No uniform mount flag exists today. Adopt: **`FEATURE_<MODULE>=0` (default OFF)** gating each
`include_router` block, e.g. `FEATURE_AI_MANAGER`, `FEATURE_WORKFLOWS`, `FEATURE_ADS`, `FEATURE_MEDIA`,
`FEATURE_BOOKING`, `FEATURE_PAYMENTS`, `FEATURE_SUPPORT`, `FEATURE_FUNNELS`, `FEATURE_FORMS`.
A module mounts only when its flag is explicitly `1`/`true`. These are **mount-time** flags — distinct
from per-tenant runtime killswitches that already exist in code (`workflow` killswitch endpoint,
`FUNNELS_KILL`/`WORKFLOW_KILL`, `BOOKING_REMINDERS_ENABLE`, `payments`/`support` `FIREWALL_ENABLE`).

### D. Credential blockers (exact env var names; module stays dormant/`not_configured` until set)
- **ai-manager:** `AIM_SERVICE_TOKEN`; voice: `AIM_VOICE_DID`, `AIM_VOICE_SIP_TRUNK_ID`,
  `AIM_VOICE_AGENT_NAME`; `AIM_OTP_PROVIDER`, `AIM_LLM_PROVIDER`.
- **workflow-studio:** `HATCHET_CLIENT_TOKEN`, `HATCHET_CLIENT_HOST_PORT` (else in-process interpreter).
- **ads-engine:** Meta `META_ADS_ACCESS_TOKEN`, `META_ADS_ACCOUNT_ID`, `META_ADS_APP_ID`,
  `META_ADS_APP_SECRET`; Google `GOOGLE_ADS_DEVELOPER_TOKEN`, `GOOGLE_ADS_CLIENT_ID`,
  `GOOGLE_ADS_CLIENT_SECRET`, `GOOGLE_ADS_REFRESH_TOKEN`, `GOOGLE_ADS_CUSTOMER_ID`,
  `GOOGLE_ADS_LOGIN_CUSTOMER_ID`; `LLM_ROUTER_URL`. (noop provider until set.)
- **media-gen:** artifacts `SPACES_KEY`, `SPACES_SECRET`, `SPACES_BUCKET`, `SPACES_REGION`,
  `SPACES_ENDPOINT`, `SPACES_PUBLIC_BASE`; video `VIDEO_PROVIDER`+`VIDEO_API_KEY` (or
  `REPLICATE_API_TOKEN`/`LUMA_API_KEY`/`HIGGSFIELD_API_KEY`/`VIDEO_SELFHOST_TOKEN`).
- **booking:** `BOOKING_REMINDERS_ENABLE`; calendar `GOOGLE_CALENDAR_CLIENT_ID`,
  `GOOGLE_CALENDAR_CLIENT_SECRET`, `GOOGLE_CALENDAR_REFRESH_TOKEN`, `GOOGLE_CALENDAR_ACCESS_TOKEN`.
- **payments:** `PAYMENTS_DEFAULT_PROVIDER`; Razorpay `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`,
  `RAZORPAY_WEBHOOK_SECRET`; Stripe `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`.
- **support:** `GROQ_API_KEY*`/`ANTHROPIC_API_KEY` (LLM draft); `SUPPORT_VOICE_INGEST_TOKEN`,
  `SUPPORT_WEB_WIDGET_SECRET`.
- **funnels:** none to run on the workflow engine; optional `FUNNELS_LANDING_API_KEY`,
  `FUNNELS_REVIEW_API_KEY`.
- **forms-surveys:** `FORMS_CAPTCHA_PROVIDER`, `FORMS_CAPTCHA_SECRET`, `FORMS_NOTIFY_ENABLE`.

### E. Verify after wiring
Mount behind flags (default OFF), boot `caller.py`, confirm: no startup regression with all flags OFF;
each module's `GET .../status|health` returns `not_configured` until its creds land; bare-router modules
reject body-supplied tenant (token wins); funnels NOT mounted until its token-deriving router exists.
