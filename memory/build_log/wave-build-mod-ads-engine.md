# WAVE BUILD — MODULE: ads-engine (Autonomous Paid-Ads Engine) — PLATFORM-ENG

Date: 2026-06-10. Spec: `design/automation-ads.md` (RED-TEAM fixes folded; fix-wins).
Roadmap: "Ad Automation = OCEAN Phase-8; spend-capped Meta/Google; depends on Auth, Action Firewall,
Wallet/Budget, Integrations."

Mode: NEW files only under `droplet_work/ads_engine/`. PROVIDER-AGNOSTIC + DORMANT-UNTIL-CREDS.
Router DEFINED-not-mounted. Did NOT edit caller.py/agent.py, did NOT restart services, did NOT
deploy/place calls. Build + offline import/instantiate-smoke locally only. NO git.

## WHAT WAS BUILT (18 files, 2376 LOC) — under `droplet_work/ads_engine/`
- `__init__.py`        — import-safe package facade (re-exports config; never fails on empty env).
- `config.py`          — Doppler-over-env resolver + status vocab + *_configured() gates + flags.
- `base_logging.py`    — shared logger factory (pair with metrics.redact for any secret-bearing log).
- `metrics.py`         — the normalized `MetricsSnapshot` (§4.3) + `redact` + `derive_cpl_minor`.
- `guardrails.py`      — THE INVARIANT CORE: caps / check_spend / check_cpl(min-sample) / evaluate /
                         require_approval (firewall step-up via injected verifier).
- `store.py`           — PG-native RLS store + lazy ensure_schema + IN-MEMORY fallback + injectable backend.
- `schema.sql`         — `ads_campaigns` table, ENABLE+FORCE RLS admin-GUC (P1/kb/wallet/crm shape).
- `creative.py`        — ad-copy via INJECTED LLM callable -> llm-router (gated) -> deterministic fallback.
- `planner.py`         — brief -> CampaignPlan (rules skeleton + LLM copy; budget clamped to cap).
- `meter.py`           — estimated window reserve + settle-delta (estimates; platform is authoritative).
- `service.py`         — THE FACADE: propose / approve / poll_and_enforce / optimize / pause_campaign /
                         pause_all / status (+ _async twins). All foundation INJECTED.
- `endpoints.py`       — FastAPI APIRouter DEFINED (prefix `/ads`), NOT mounted; deferred-seam docstring.
- `providers/{__init__,base,noop,meta,google}.py` — AdProvider ABC + noop + lazy-SDK Meta/Google adapters.
- `tests/test_ads_offline.py` — 10 ZERO-network acceptance tests (pytest + self-running harness).
- `ADS_ENGINE_STATE.md` — durable per-unit ledger.

## WHAT IT COMPOSES (the F4/F2 foundation)
- **F4 firewall** (PIN/step-up on risky actions): `guardrails.require_approval` -> the INJECTED
  `firewall.verify_step_up_token(token, "spend", expected_sub=tenant_id)`. Enforces Invariant B —
  nothing activates without a fresh step-up token bound to the caller (sub). Bad/missing -> never
  touches a platform. Default verifier lazily resolves the box `firewall.py`; fails CLOSED if absent
  while approval is required (don't let money move unguarded).
- **F4 wallet** (spend gate, no double-spend): `approve_campaign` -> `wallet.reserve(tenant, cap,
  resource_type="ad_campaign", resource_id=plan_id, idem_key=...)` on the LIVE activation path. None ->
  blocked_insufficient_funds, create_campaign never called. Settle-on-pause captures min(actual,reserved).
- **Immutable audit**: every propose/approve/pause/poll-pause/optimize -> `audit.record(channel="ads",
  meta={...})` (Invariant C). Composes the F4 append-only events leg; NO separate spend_ledger.jsonl.
- **P1 RLS**: `ads_campaigns` is PG-native, admin-GUC RLS via `db.engine.session(tenant_id, is_admin)`
  — the SAME shape kb_chunks / wallet_* / contacts use.
- **F2 LLM seam**: ad copy via the in-house llm-router (`POST /v1/llm/generate`, injected callable,
  NO new vendor). Gated on LLM_ROUTER_URL -> network-free + deterministic fallback when unset.

## THE ROUTER ENDPOINTS (for the later mount; `router = APIRouter(prefix="/ads")`)
- `POST /ads/campaigns/propose`         -> service.propose_campaign  (write/manager)
- `GET  /ads/campaigns`                 -> service.status            (read)
- `GET  /ads/campaigns/{plan_id}`       -> service.status            (read)
- `POST /ads/campaigns/{plan_id}/approve` -> service.approve_campaign (write + X-Step-Up token)
- `POST /ads/campaigns/{plan_id}/pause` -> service.pause_campaign (SCOPED, write)
- `POST /ads/optimize`                  -> service.optimize (dry_run default, write)
- `GET  /ads/health`                    -> config.healthcheck        (public)
Wiring note (in endpoints.py docstring): spine does `app.include_router(router)` + a scheduler tick
calling `poll_and_enforce` every poll_minutes + OPTIONAL edge `firewall.require_step_up(request,
"spend", tenant)` defense-in-depth. NONE wired this phase.

## DEFENSE-IN-DEPTH SPEND SAFETY (§5)
L1 platform daily budget set <= cap at create (the REAL floor). L2 local polling breaker pauses on
cap/CPL. L3 firewall approval gate. L4 immutable audit. Wallet reserve = a 5th money-custody backstop.
HONEST: the polling breaker is NOT cent-perfect (inter-poll latency window); the platform daily budget
is the floor (§5.5 verbatim). CPL is only as real as the founder's Pixel+CAPI / conversion action.

## PROOF — 10/10 offline tests GREEN (pytest + harness, ZERO network)
dormant+socket-sentinel (incl. no-LLM propose path) · spend-cap breaker · CPL+min-sample(15)+
no-pause-at-3-conv+no-conv-tracking+cap-still-fires · approval gate (bad token never creates) ·
wallet insufficient-funds (never creates) · audit-on-every-decision · provider parity (platform-blind)
· router defined-not-mounted (7 routes) · scoped pause (pauses ONE) · wallet settle-on-pause-only.
Local venv: fastapi 0.115.6 / pydantic 2.13.4 present -> router imports + smokes locally.

## ADVISOR CATCHES CLOSED (pre-log review — these would have overclaimed the brain map)
1. Dormancy not actually proven + 20s llm-router hang on default propose -> gated on LLM_ROUTER_URL,
   socket-sentinel-tested the no-LLM path. 2. `/pause` killed ALL campaigns -> added scoped
   `pause_campaign`. 3. per-poll `settle` closed the hold (campaign ran unbacked) -> accrue-and-settle-
   ON-PAUSE; MULTI-WINDOW settle->re-reserve loop DEFERRED + recorded UNPROVEN (FakeWallet can't
   surface F4 settle-closes-hold). minors: dry_run short-circuits BEFORE reserve; budget typo fixed.

## CREDS AWAITED (module = graceful no-op until then)
Meta: META_ADS_APP_ID/SECRET, META_ADS_ACCESS_TOKEN (System-User: ads_management/ads_read/
business_management), META_ADS_ACCOUNT_ID (act_<digits>), META_ADS_PAGE_ID, META_BUSINESS_ID,
META_PIXEL_ID+META_CAPI_TOKEN (CPL; CAPI-only, offline-conv API dead 2025-05-14), META_ADS_API_VERSION
(~v25). On-platform: Business Verification + Advanced-Access App Review (multi-day, founder-side);
payment method on ad account.
Google: GOOGLE_ADS_DEVELOPER_TOKEN (MCC, approval req), GOOGLE_ADS_CLIENT_ID/SECRET,
GOOGLE_ADS_REFRESH_TOKEN, GOOGLE_ADS_LOGIN_CUSTOMER_ID (MCC), GOOGLE_ADS_CUSTOMER_ID,
GOOGLE_ADS_API_VERSION (>=v22). On-platform: conversion action (CPL else cap-only); billing.
Flags (safe defaults): ADS_DRY_RUN=1, ADS_REQUIRE_APPROVAL=1, ADS_DAILY/LIFETIME/CPL_MAX_MINOR,
ADS_CPL_MIN_CONVERSIONS=15, ADS_POLL_MINUTES=30, ADS_ORG_DAILY_CAP_MINOR (R4). LLM_ROUTER_URL.

## DEFERRED (named)
- Mount router + scheduler poll tick into caller.py (the spine seam; sequential wiring unit).
- Real Meta facebook-business / Google google-ads SDK calls (sketched behind cred gate; dormant).
- MULTI-WINDOW wallet settle->re-reserve loop (advisor #3) — build against REAL wallet on box.
- ORG-level spend ceiling enforcement (sum across tenants) — knob defined; multi-tenant-activation unit.
- API-version EOL health warning (R6). Creative IMAGE gen (creative/image_banner_studio owns it).

## NAMING NOTE (avoid future confusion)
Orchestrator label "ads-engine" -> Python package `droplet_work/ads_engine/` (UNDERSCORE — a hyphen
is not a valid module name; can't import/mount). This SPEND engine is DISTINCT from the pre-existing
`droplet_work/creative/ads_engine/` (creative -> ad-asset linking). No import collision.

## DEVIATIONS FROM SPEC (fix-wins; F4/CRM precedent)
- §4 store: PG-native `ads_campaigns` + RLS, NOT var/ads/*.json (task: "RLS via P1 pattern" = PG admin-GUC).
- §2 layout: top-level `ads_engine/`, NOT `automation/ads/` (the automation/ sibling doesn't exist; FIX 2).
- Spend history -> audit.record(channel="ads"), NOT spend_ledger.jsonl (composes immutable audit).
- Approval gate BUILT on firewall.verify_step_up_token (FIX 1: no firewall.py "step-up to reuse" beyond it).
