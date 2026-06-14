# Integrations / Provider UI — build STATE (crash-safe)

Wave: video-framework-to-studio (FE phase = the crazy Integrations/Provider page).
Branch: fe/unify-run-wavec. BUILD + commit only — DO NOT deploy the panel (single deploy after voice-core-surgery).

## CONTRACT (verified on disk — live BE)
- BE prefix LIVE = `/provider-registry` (NOT /admin/providers). FE base `/api` → `/api/provider-registry...`.
- Auth header = `X-Auth: <famit_token>` (lib/api.ts convention). getToken from localStorage `famit_token`.
- LIST: `GET /provider-registry?capability=` → `{providers:[_def_public_dict + masked + circuit], capability}`.
  - `_def_public_dict` keys: id, tenant_id, is_global, slug, display_name, provider_type
    (hosted_api|self_hosted|tool_connector|platform_builtin), capabilities[], base_url, auth_scheme
    (bearer|api_key_header|api_key_query|basic|oauth2_cc|none), auth_header_name, transform_type
    (openai_compat|named_provider|custom_field_map), named_provider, model_default, cost_per_unit_micros,
    cost_unit, health_check_path, priority, rate_limit_rpm, is_enabled, is_platform_default, created_at, updated_at.
  - row also gets `.masked` (string|null, from a matched credential) + `.circuit` (health.circuit_state).
- HEALTH: `GET /provider-registry/health?capability=` → registry.resolve_status (per-provider circuit+diag).
- CREATE (vendor): `POST /provider-registry` body=def fields + optional api_key (scope=integration). self_hosted→403; http→400.
- UPDATE: `PUT /provider-registry/{id}`. DELETE: `DELETE /provider-registry/{id}` → {deleted,id}.
- CREDENTIAL: `POST /provider-registry/{id}/credential` body {api_key} → {stored,key_masked,scope:integration}.
- REVEAL: init `POST /provider-registry/{id}/reveal-init` → {step_up_token,expires_in:60,scope:provider.reveal,aud}.
  then `POST /provider-registry/{id}/reveal` header `X-Step-Up: <token>` → {provider_id, credential:plaintext}.
  ai_provider scope → 403; replay → 403. PIN-pad first: `POST /firewall/verify-pin` Form(pin,scope=provider.reveal)→{ok,...}.
- TEST: `POST /provider-registry/{id}/test` → {provider_id,slug,healthy,latency_ms,detail,circuit}.
- ADMIN: GET /provider-registry/admin/all?capability=&tenant_id= ; POST/PUT/DELETE /provider-registry/admin[/{id}] ;
  POST /provider-registry/admin/{id}/test ; reveal admin path. admin row adds has_credential.
- FLAG-OFF: every route → 404 (config.is_enabled() false). Dormant-safe: render calm empty/coming-soon, never error wall.

## GLYPH GROUND-TRUTH (Icon/index.tsx — missing name = invisible)
SAFE: chain link link-1 camera-video video lock clock-1 info check check-circle check-circle-fill upload
magic-pencil plus trash dots chevron search filters bell list grid send layers chart close.
ABSENT (NEVER use): shield eye copy key refresh download plug server globe play pause switch-h.
→ Reveal=lock, Rotate=clock-1, Health=Badge dot, Self-hosted/Connector nav=chain, Test/Copy/Export=text buttons.

## ROUTE MAP (design crazy-ui-security §F)
- app/integrations/page.tsx (tenant) — sub-nav pill-strip Providers/Self-hosted/Health/Audit. EntitlementGuard featureKey="integrations.providers".
- app/super-admin/integrations/page.tsx (super-admin twin) — _global catalogue + all-tenants. SuperAdminGuard. +1 ADMIN_TABS line.
- lib/integrations.ts — typed fetchers + hooks.
- contstants/navigation.tsx — +Integrations top-level (icon chain).
NEW leaves: _sub-nav, _provider-card, _add-provider-modal, _selfhost-modal, _test-conn, _health-table, _audit-drawer, _reveal-pin, _field-mapper.

## PORT SOURCES (verbatim, never approximate)
- app/super-admin/api-keys/page.tsx (ProviderCard/KeyRow/AddKeyModal grammar).
- app/super-admin/api-keys/_custom-providers.tsx (AddCustomModal: name/kind/base_url/model/key + Select).
- app/super-admin/_shared.tsx (SuperAdminGuard, ToastView, ghostBtnCls, ErrorBanner, StatusPill, AdminHeader, fmtDateTime).
- components: Card Tabs Select Switch Modal Badge Field Button Layout Spinner Dropdown NoFound EntitlementGuard.
- Tabs: {items,value,setValue} TabsOption{id,name}. Select: {value,onChange,options} SelectOption{id,name}.
- Modal: {open,onClose,classWrapper,isSlidePanel,children}. Badge: {variant,dot,children}.

## STATUS
- [DONE] explore + contract verified.
- [DONE] build lib/integrations.ts + 8 component leaves + 2 pages + nav. tsc 0, build 0, hex 0, gitleaks 0.
- [DONE] committed fe/unify-run-wavec. Panel NOT deployed (single deploy after voice-core-surgery).
