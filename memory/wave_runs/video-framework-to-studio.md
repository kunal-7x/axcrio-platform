# Video Framework → Studio (end-to-end) — wave run log

Spec: `design/VIDEO-STUDIO-MASTER-PLAN.md` + `design/PROVIDER-FRAMEWORK-PLAN.md` §14 (the unified
W1–W12 roadmap). Canonical branch `fe/unify-run-wavec`. One box-mutating wave at a time, serialized
vs RAG/Vault/Video on caller.py. Earner-safe (agent.py `9150fabe` NEVER imported/touched; restart
ONLY famit-caller / famit-aiasset / the video worker — NEVER famit-agent).

---

## W5 — strangler video cut-over (REGISTRY_FOR_VIDEO) — ✅ DONE + DEPLOYED (2026-06-14)

**Scope (plan §14 W5):** rewire `media_gen/video/client._resolve_key` so that when
`REGISTRY_FOR_VIDEO` is ON it asks the provider registry (`registry.get_provider(tenant,
"video_gen")`) for the provider+key, and on a registry MISS falls back to the legacy
`config.fal_key(...)` path. Flag default OFF → today behavior (resting byte-identical).

### EARNER GATE — BEFORE
| Check | Value |
|---|---|
| agent.py md5 (box) | `9150fabe4ff62b4b4470f9a87df346e5` UNCHANGED |
| famit-agent MainPID | `1477083` (NOT restarted) |
| famit-caller MainPID | `2745889` |
| caller /health (8209) | 200 |
| 5xx (caller, last 15m) | 0 |
| `PROVIDER_REGISTRY_ENABLED` | `1` (registry ON since W4) · `REGISTRY_FOR_VIDEO` absent (default OFF) |
| ring | NO ring (no calls placed) |

### THE CHANGE (file:lines — registry-then-fallback path)
- `droplet_work/media_gen/video/config.py:67-77` (NEW `registry_for_video()`) — call-time read of
  `REGISTRY_FOR_VIDEO`, lenient truthy (`1/true/yes/on/y/t`); default OFF. Purely additive (diff vs
  box golden `b68a1dc6` = `66a67,77`, 0 deletion/modification lines). New box md5 `02bb49dc`.
- `droplet_work/media_gen/video/client.py:304-355` — `_resolve_key` is now a thin dispatcher:
  ```
  def _resolve_key(provider, tenant_id=""):
      if config.registry_for_video():           # flag ON
          key = _registry_resolve_key(provider, tenant_id)   # registry FIRST
          if key:
              return key                          # registry hit wins
      return _legacy_resolve_key(provider, tenant_id)         # MISS / flag-OFF -> legacy env path
  ```
  - `_registry_resolve_key` (`:311-329`): lazy `from provider_registry import registry`; calls
    `registry.get_provider(tenant_id, capability="video_gen", routing_hint=<provider slug>)`; on
    `client.ok` returns `client._key` (decrypted in-process, AAD-bound via the get_secret seam);
    returns `""` on ANY miss (package absent / not ok / empty key / exception → legacy fallback).
    Never raises — a resolution problem degrades to legacy, never breaks a render. NEVER imports
    agent.py (earner-safe); the registry rides caller.py + the AI-asset process.
  - `_legacy_resolve_key` (`:332-345`): the ORIGINAL per-tenant env-var resolution
    (`config.fal_key`/`replicate_token`/`luma_key`/`higgsfield_key`/`selfhost_token`/`generic_key`),
    byte-identical to the pre-W5 `_resolve_key`. This is the flag-OFF path.
  - client.py diff vs box golden `58af1c8a` = additive only (`302a303,309` doc comment +
    `304c311,331` def-rename + `318a346,355` new dispatcher); legacy branch logic unchanged. New box
    md5 `be38c169`.

### FLAG-OFF BYTE-IDENTICAL + REGISTRY-THEN-FALLBACK — 6 OFFLINE PROOFS (all PASS)
1. flag OFF → `_resolve_key == _legacy_resolve_key` for every provider
   (`fal/replicate/luma/higgsfield/selfhost/generic/""`) — byte-identical to today.
2. flag ON + registry `ok` → registry key wins (`REGISTRY_KEY_123`).
3. flag ON + registry `not ok` (miss) → legacy fallback (`LEGACY_FAL_KEY`).
4. flag ON + registry raises (e.g. PG down) → legacy fallback (never breaks render).
5. flag ON + registry `ok` but EMPTY key → legacy fallback (video has no auth='none').
6. flag ON + `provider_registry` package absent (ImportError) → legacy fallback.

### DEPLOY (FORTRESS recipe, famit-caller-only)
- Edited FROM the box golden (local `client.py` `58af1c8a` == box; `config.py` matched box
  `b68a1dc6` — PLAYBOOK rule 16).
- Backups: `client.py.W5bak.20260614-220716` + `config.py.W5bak.20260614-220716` (in
  `/opt/famit-agent/media_gen/video/`).
- scp to /tmp → md5-gate (staged == local: `be38c169` / `02bb49dc`) → caller-venv
  `py_compile` OK → atomic `mv` swap → `chown famit:famit` → box import-check
  `registry_for_video()=False` (flag absent).
- Restarted **famit-caller ONLY** (PID 2745889 → 2757508, NRestarts=0). famit-aiasset (2364219),
  aim-voice-agent (2739156), famit-agent (1477083) all UNTOUCHED.
- `REGISTRY_FOR_VIDEO` NOT added to `.env` (absent → default OFF → resting byte-identical, the
  required end-state for this wave).
- The media_gen/video files live under `/opt/famit-agent` (gitignored scratch); imported lazily by
  `provider_registry/named_transforms.py` (caller.py graph). The video studio submit path that
  actually calls `_resolve_key` is W8 (not yet mounted) — W5 is purely the key-resolution seam.

### EARNER GATE — AFTER (PASS)
| Check | Value |
|---|---|
| agent.py md5 | `9150fabe4ff62b4b4470f9a87df346e5` UNCHANGED |
| famit-agent MainPID | `1477083` NOT restarted |
| aim-voice-agent / famit-aiasset | `2739156` / `2364219` UNTOUCHED |
| caller /health (8209) | 200 |
| 5xx / tracebacks (since restart) | 0 |
| `REGISTRY_FOR_VIDEO` | absent → default OFF → resting byte-identical |
| ring | NO ring (no calls placed) |

### ROLLBACK
Set/leave `REGISTRY_FOR_VIDEO` absent or `0` (instant, no deploy — already the resting state; flag
OFF → legacy env path verbatim). To fully remove the code: restore
`client.py.W5bak.20260614-220716` + `config.py.W5bak.20260614-220716`, restart famit-caller.

### NEXT (W6)
VID: engine.py seam fix + PG video schema + live-library bridge (`FEATURE_VIDEO_LIBRARY`) — on the
AI-asset service (`:8310`), NOT caller.py.

---

## INTEGRATIONS UI — the crazy Provider/Connector management page — ✅ BUILT + GREEN (FE only, NOT deployed)

**Scope:** the universal Provider/Integrations management page (PROVIDER-FRAMEWORK-PLAN §9 + §14 W11
FE + video-flex-framework-design `DESIGN [crazy-ui-security]` §B), consuming the LIVE
`/provider-registry` API (W4-mounted, flag ON). FE-only — built + committed to `fe/unify-run-wavec`,
`tsc --noEmit` + `npm run build` GREEN locally, **panel NOT deployed** (single deploy after
voice-core-surgery, per the no-panel-deploy-race rule). Zero box mutation, agent.py never touched.

### THE API CONTRACT (verified on disk vs the live BE — endpoints.py)
The live registry mounts under **`/provider-registry`** (NOT the spec's `/admin/providers`; the bare
`/providers` prefix is shadowed by the legacy LLM-router list). FE proxies caller.py at `/api`, auth =
`X-Auth` header (lib/api.ts convention). Shapes consumed: list `{providers:[_def_public_dict + masked +
circuit]}`, health (`registry.resolve_status`, normalized to rows), create/update/delete, `POST
/{id}/credential` → `{stored,key_masked,scope}`, the 3-step PIN reveal (`/firewall/verify-pin` Form →
`/{id}/reveal-init` aud-bound single-use → `/{id}/reveal` `X-Step-Up` → plaintext once), `POST
/{id}/test` → `{healthy,latency_ms,detail,circuit}`, and the `/admin/*` super-admin twin surface.
DORMANT-SAFE: every route 404s when flag-off/not-entitled → reads degrade to a calm coming-soon card,
never an error wall (mutations surface a typed `IntegrationError`).

### FILES (path:line)
- `famit-panel/lib/integrations.ts` (NEW) — typed fetchers + `IntegrationError` + `humanizeError`
  (ssrf_blocked/https-only/step_up/field_map → human msgs) + hooks `useProviders` (`:~360`),
  `useIntegrations(capability)` (`:~395` — the Video Studio BYO-key picker seam), `useProviderHealth`
  (30s poll, NOT 5s) + display dicts (CAPABILITY/AUTH/TRANSFORM labels, SELFHOST_PRESETS, `fmtCost`
  micro-USD→"$/sec"). The 3-step reveal is `verifyPin`+`revealInit`+`revealCredential`+`revealFlow`.
- `famit-panel/app/integrations/page.tsx` (NEW) — the vendor page: `EntitlementGuard
  featureKey="integrations.providers"` → `Layout title="Integrations"` → `IntegrationsBody` (shared,
  also drives the admin twin). 4 views via `SubNav` pill-strip (Providers / Self-hosted / Health /
  Audit). Dormant → coming-soon card. Add-provider + self-hosted seed + edit modals.
- `famit-panel/app/integrations/_shared.tsx` (NEW) — `SubNav`, `HealthBadge` (circuit→Badge: closed=
  Healthy green / half_open=Recovering amber / open=Down danger / unknown=Unchecked), `CapabilityChips`,
  `TypePill`, `PlatformLock`, `InfoStrip`, `ghostBtnCls`/`textBtnCls`.
- `famit-panel/app/integrations/_provider-card.tsx` (NEW) — one provider Card (port of api-keys
  ProviderCard/KeyRow): type pill + HealthBadge + capability chips + base_url/model/cost + masked
  credential row (RevealPin for own `integration` key; `PlatformLock` masked-only for `is_global`/
  platform key per Vault §9) + enable Switch + BYO-key add/rotate + "Test connection" inline result +
  two-step confirm-delete.
- `famit-panel/app/integrations/_add-provider-modal.tsx` (NEW) — `Modal isSlidePanel` add/edit:
  display_name/slug/capability-multiselect/type/base_url (Hosted) OR SSRF-decomposed host+port +
  server-preset (Self-hosted, admin-only)/auth_scheme/auth_header_name (api_key_header only)/transform
  /model/cost/api_key. `seedSelfHosted` (admin) pre-selects the SSRF form. Vendor type Select hides
  Self-hosted (BE 403s it). custom_field_map → the FieldMapper.
- `famit-panel/app/integrations/_field-mapper.tsx` (NEW, the ONE net-new leaf) — the visual JSONPath
  request/response field-mapper (the "connect ANY tool, no code" lever). `validatePath`/`validateMap`
  = client-side JSONPath-only, depth≤5, no-eval/expression refusal (mirrors the BE
  `adapter.validate_field_map` gate) — emits the JSONB map without hand-editing JSON.
- `famit-panel/app/integrations/_reveal-pin.tsx` (NEW) — inline PIN-pad + 30s countdown-ring reveal.
  **Plaintext lives in a `useRef`, NEVER react-state**; wiped on timeout/unmount/Hide; copy-without-
  revealing (clipboard from the ref). Glyph = `lock` + TEXT buttons (eye/copy/key don't exist).
- `famit-panel/app/integrations/_health-table.tsx` (NEW) — Health tab: ok/recovering/down count strip
  + per-provider circuit/latency/detail table, 30s poll, dormant-safe.
- `famit-panel/app/integrations/_audit-drawer.tsx` (NEW) — Audit tab: provider.* events from the
  existing `/audit` feed (immutable control leg, no new endpoint) + Export CSV (text button — download
  glyph absent) + a right slide-over event-detail drawer. Plaintext never in the audit (key_masked only).
- `famit-panel/app/super-admin/integrations/page.tsx` (NEW) — the super-admin TWIN: SuperAdminGuard +
  AdminHeader strip + `IntegrationsBody admin` (drives `/provider-registry/admin/*`: `_global` catalogue
  + all-tenants, self-hosted register, platform-key add).
- `famit-panel/app/super-admin/_shared.tsx` — +1 `ADMIN_TABS` line (Integrations).
- `famit-panel/contstants/navigation.tsx` — +Integrations under Automate (manager-gated,
  `feature_key="integrations.providers"`, glyph reuse) + super-admin group child.

### SECURITY / CRAZY-UI (design §E folded)
Reveal-policy half-gate as defence-in-depth: platform (`ai_provider`/`is_global`) key → `PlatformLock`,
NO reveal/rotate surfaced; vendor `integration` key → RevealPin (PIN step-up, single-use jti, plaintext
in ref). SSRF surfaced: host+port separate fields + "Will probe …" preview + "SSRF-validated on save"
badge + the BE `ssrf_blocked:<reason>` mapped to a human refusal. FieldMapper = JSONPath-only no-eval.
EntitlementGuard HIDE/LOCK cosmetic; the BE 404/402 is the boundary. Registry prefix is the literal
`/integrations` route (entitlement matcher = literal-prefix, no `*`).

### GLYPH GROUND-TRUTH (verified vs Icon/index.tsx)
USED (all registered): chain, lock, clock-1, info, check, check-circle, chevron, plus, trash, arrow.
NEVER used (absent → invisible): shield, eye, copy, key, refresh, download, plug, server, globe, play.

### VERIFY (GREEN, FE-only)
`npx tsc --noEmit` = exit 0. `npm run build` = exit 0 (both `/integrations` + `/super-admin/integrations`
compiled, 229 kB each). Raw-hex scan on all new files = EMPTY (semantic @theme tokens only). gitleaks
`protect --staged` = 0 leaks (99 KB scanned). EARNER UNTOUCHED (FE-only, no box mutation, no restart, no
ring; agent.py `9150fabe` never imported). **Panel NOT deployed** (single deploy after voice-core-surgery
from the latest fe/unify-run-wavec). Commit on `fe/unify-run-wavec`.

### NEXT
Video Studio page (U6/W9: `app/creative/video/page.tsx` + TierTabs + AssetMedia split + Images↔Videos
toggle) consumes `useIntegrations("video_gen")` from this lib for its BYO-key picker — the seam is ready.
