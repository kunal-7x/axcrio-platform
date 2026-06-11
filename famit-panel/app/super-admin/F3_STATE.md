# CL-F3 — SUPER ADMIN: Feature Flags + Plans + Usage + Audit (FE wave C9)

> **W2 RESKIN (2026-06-11, premium-UI):** all `/super-admin/*` pages now pass the
> ui-design-principles checklist. `AdminHeader`/`SuperAdminHeaderF3` in `_shared.tsx`
> NO LONGER uses `PageHeader` (dropped eyebrow + subtitle + the duplicate title) — it
> renders ONLY the section tab strip + actions; the single page title is `<Layout title>`
> (plain page name, not "Super Admin · X"). `subtitle=` props removed from every caller.
> `_shared.tsx` no longer re-exports `HeroCard/ghostBtnCls/Sparkline` from `app/billing/_shared`
> (that sibling unit refactored those away, which broke us) — `HeroCard`, `ghostBtnCls`,
> `ErrorBanner` are now defined LOCALLY in `_shared.tsx` from the W1 shell + tokens.
> Raw hex purged (`vendors/[id]`: #FF6A55→primary-03, #0F8F53/#3FD089→primary-02,
> #C77E08/#EF9D0E→primary-05); invalid icon names fixed (`arrow-right`/`arrow-left` are
> not in the Icon dict → `arrow` / rotated `chevron`). `tsc --noEmit` = 0 errors.


Owner: this unit. Routes under `app/super-admin/{flags,plans,usage,audit}`. Ports Core_2
settings/table/analytics/notifications archetypes in the panel's "Signal" style. Reuses shell
components (Layout/Card/Tabs/Badge/Table/Select/Field/Button/PageHeader/KpiCard/Search/Spinner).
Does NOT edit `components/`. Does NOT npm build (gate is the C12 wave).

Backend contract (LIVE, shipped CL-B3, behind CONTROL_ENABLED): caller.py
- GET  /admin/features                    -> {features:[registry rows]}
- GET  /admin/flags                       -> {flags:{key:mode}}
- PUT  /admin/flags/{key}  Form(mode)     -> {ok, feature_key, before, after}
- GET  /admin/plans                       -> {plans:[{plan_id,name,is_default,entitlements,limits}]}
- POST /admin/plans  Form(plan_id,name,description)
- PUT  /admin/plans/{id}  JSON {entitlements:{k:mode}, limits:{k:int}}
- GET  /admin/vendors                     -> {vendors:[{tenant_id,name,email,status,plan,usage,health}]}
- GET  /usage/all                         -> {tenants:[TenantUsageRow]}  (executive usage)
- GET  /audit?channel=control&limit=&offset=&action= -> {events:[...], total, limit, offset}
  event = {ts, actor, actor_role, action, object_type, object_id, ip, channel, tenant_id,
           meta:{target_tenant, feature_key, old_value, new_value, reason, real_admin, auth_method}}

Resting-state: every /admin/* + /me/entitlements degrades gracefully (CONTROL off -> all-on,
older box -> route 404 -> empty-but-valid UI). Admin-only: pages self-gate on isAdmin(me) (mirrors
app/vendors/page.tsx). Nav group is added by the C6/C7 owner (shared navigation.tsx) — NOT here.

## Units — ✅ ALL DONE 2026-06-11 (tsc --noEmit -p tsconfig.json => exit 0, project-wide clean)
- [DONE] api.ts bindings (additive, graceful 404): getAdminFeatures/getAdminFlags/setAdminFlag/
  getAdminPlans/createAdminPlan/updateAdminPlan/getControlAudit + types FeatureMode/
  FeatureRegistryRow/AdminPlan/SetFlagResult/AuditEvent/AuditPage. REUSE CL-F1's getAdminVendors/
  AdminVendor (did NOT duplicate — removed my early dup AdminVendorRow/getAdminVendors to avoid a
  redeclare collision; Usage page consumes CL-F1's richer summary+fallback list).
- [DONE] app/super-admin/_shared.tsx — EXTENDED CL-F1's shared file additively (did not edit their
  exports): added my 4 tabs to ADMIN_TABS, alias SuperAdminHeaderF3=AdminHeader, + SuperAdminGuard,
  ModeBadge, ProvenanceBadge, MODE_META/MODE_ORDER, KIND_META, humanizeAction, LIMIT_KEYS/labels,
  ToastView. Reuse CL-F1's StatusPill/num/ago/fmtDate/fmtDateTime + billing ErrorBanner/ghostBtnCls.
- [DONE] app/super-admin/flags/page.tsx — global feature-flag grid: SettingsPage/Menu archetype
  (sticky module index + per-module Card), 3-state On/Lock/Hide segmented control per row, core rows
  Lock/Hide disabled (anti-lockout floor). PUT /admin/flags/{key}, optimistic + rollback.
- [DONE] app/super-admin/plans/page.tsx — UpgradeToPro/Pricing gallery cards + NewProductPage editor
  Modal (left = 4-state Default/On/Lock/Hide per feature by module; right rail = limit Fields).
  POST /admin/plans, PUT /admin/plans/{id} (JSON entitlements+limits).
- [DONE] app/super-admin/usage/page.tsx — Customers/OverviewPage archetype: fleet KPI strip +
  per-vendor leaderboard (sort Select + Search + share meter). GET /admin/vendors (CL-F1).
- [DONE] app/super-admin/audit/page.tsx — Notifications archetype: control-event feed (action badge,
  feature, target vendor, old→new chips, reason, actor, relTime) + action Select filter + free-text
  search + pagination. GET /audit?channel=control.

## Cross-unit fix (build-blocking, not mine but fixed to keep the tree green)
- lib/api.ts:982,1007 referenced `coerceStatus` (undefined) — a leftover from CL-F1's in-flight
  rename to `coerceVendorStatus`. Fixed both call sites to `coerceVendorStatus` (same signature).
  Without this the WHOLE project failed tsc; now exit 0.

## NOT done here (other units own these — no collision):
- The "Super Admin" nav GROUP in contstants/navigation.tsx (shared file — C6/C7 owner adds it).
- Overview (/super-admin) + Vendors list/workspace (/super-admin/vendors[/id]) = CL-F1/C7.
- EntitlementToggle component + Permissions tab = C8. No npm build (C12 gate).
</content>
</invoke>
