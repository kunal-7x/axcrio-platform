# FIX-CONTROL-2 — SHIPPED (frontend control-layer enforcement)

**Date:** 2026-06-11. **Scope:** frontend only (backend untouched — it already enforced).
Fixes the one broken link from `fix-control-2.md`: the deployed vendor bundle never
consumed the `/me/entitlements` map it polls.

## What changed (3 files, 1 new component)
1. `famit-panel/contstants/navigation.tsx` — added `feature_key` to every module
   GROUP + every CHILD (mirrors lib/api.ts FEATURE_REGISTRY 1:1). Deployed nav
   `feature_key` count 0 → 31. CORE surfaces left UNKEYED on purpose: Command/
   Dashboard, the whole Money group (protects core `money.billing`), the whole
   Foundation group (core `foundation.settings`), Creative Studio (dormant-safe via
   its own status endpoint), and the admin-only Super Admin group (role-gated).
2. `famit-panel/components/RouteEntitlementGate/index.tsx` — NEW. One app-wide route
   guard. `usePathname()` → `featureKeyForPathname()` (longest-prefix map DERIVED
   from FEATURE_REGISTRY nav_href, so it can't drift; handles dynamic routes like
   /crm/123) → `useEntitlement(key)` → HIDE redirect "/" / LOCK `<LockOverlay>`.
   Core "/" never gated. Cosmetic — backend 404/402 is the real boundary.
3. `famit-panel/app/providers.tsx` — mount `<RouteEntitlementGate>` inside the
   existing `<EntitlementProvider>` (authed only; shares the one poller/store).

UNTOUCHED (correct as-is): `lib/entitlements.ts`, `lib/api.ts getEntitlements`,
`EntitlementProvider`, `EntitlementGuard`, `LockOverlay`, the Super Admin write path
(`super-admin/vendors/[id]/page.tsx` handleSet → setVendorEntitlement, optimistic +
version reconcile — ALREADY worked), and ALL backend files.

## How the toggle persists (re-verified live, NOT bypassing the UI chain)
The Super Admin Permissions toggle already wrote correctly; re-proved post-deploy
against the live backend with a REAL vendor token (`21d0a13603da`, is_admin=false)
and the EXACT endpoint the UI fires:
- `PUT /admin/vendors/21d0a13603da/entitlements/grow.campaigns mode=hidden`
  → `{ok:true, after:"hidden", version 30→31}` (optimistic + version bump in the UI).
- vendor `/me/entitlements` flipped `grow.campaigns` → `hidden`; vendor `GET /campaigns` → 404.
- `DELETE .../grow.campaigns` → `on`, version 32; `GET /campaigns` → 200.
Vendor LEFT RESTORED to `on` (version 32). No test state lingering.

## How the vendor view now ENFORCES (the fix)
Verified the SHIPPED resolver code against real payloads:
- `grow.campaigns:hidden` → Campaigns DROPPED from the Grow sidebar group.
- `grow.campaigns:locked` → Campaigns flagged `locked` (dimmed "Locked" pill).
- `grow:hidden` (module) → the whole Grow group disappears.
- `money:hidden` → Money group SURVIVES, core Billing stays (unkeyed-group protection).
- Route gate: `/campaigns`, `/campaigns/abc`, `/crm/123` → their keys; `/` → null (core never gated).
Live bundle proof: all 26 module/page keys present in `.next/static/chunks`; the gate's
`ai-manager`→`ai_manager.overview` rule + `ROUTE_RULES prefix:` survived minification in
`app/layout-*.js`; LockOverlay present.

## Deploy + regression
- Box `root@143.110.247.249:/opt/famit-panel`. Backup: `/opt/famit-panel-ctrlbak-20260611-172745.tgz`
  + `*.ctrlbak.20260611-172745` siblings of nav/providers.
- Rebuilt `.next` (OOM on first try at 1.9GB RAM → added temp 4G swap + NODE_OPTIONS
  --max-old-space-size=1536, build exit 0, ~190s; temp swap removed after). Restarted
  `famit-panel.service` (active).
- Regression GREEN: public /api/campaigns /leads /me = 401 (healthy unauth); / /campaigns
  /workflows /super-admin/vendors = 200 (no 5xx); famit-caller + famit-bridge (voice) active.

## Rollback (if ever needed)
`cd /opt/famit-panel && tar xzf /opt/famit-panel-ctrlbak-20260611-172745.tgz` (restores
nav+providers, removes the new component dir contents), then `npm run build` (with the
swap/heap caps) + `systemctl restart famit-panel`.
