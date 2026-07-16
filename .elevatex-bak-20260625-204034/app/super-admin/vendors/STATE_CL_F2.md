# CL-F2 — Super Admin Vendor Workspace + Permission Matrix (STATE)

Owner: this unit. Route owned: `app/super-admin/vendors/[id]`. Sibling CL-F1 owns
the vendors LIST (`app/super-admin/vendors/page.tsx` + `_shared.tsx` + `getAdminVendors`).
DO NOT touch components/ (reuse only). DO NOT npm build (per orchestrator).

## Plan / units
- [DONE] U1 api.ts: AdminVendorDetail type + getAdminVendor(id) (graceful fallback),
         FeatureRegistryNode/Provenance/ResolvedEntitlement types, the static
         FEATURE_REGISTRY seed (from design/control-datamodel.md §0), and the writes:
         setVendorEntitlement / clearVendorEntitlement / setVendorPlan / setVendorStatus,
         getAdminPlans (graceful).
- [DONE] U2 components/EntitlementToggle/index.tsx — the 3-state On/Lock/Hide row
         (Badge provenance pill + Tabs-style segmented control + Reset + core-floor lock).
- [DONE] U3 app/super-admin/vendors/[id]/page.tsx — DetailsPage port: left identity/actions
         rail (StatusPill + status Select->Modal w/ reason, plan Select, credits btn stub) +
         right 5-tab body (Overview / Usage / Permissions[the matrix] / Billing / Audit).

## Key decisions
- Route family is `/super-admin/*` (CL-F1 already established it; nav + _shared use it),
  NOT `/admin/*` from the design doc. API paths stay `/admin/*` (backend contract).
- Graceful fallback everywhere: backend /admin/vendors/{id} may 404 (CONTROL_ENABLED=0).
  Compose detail from /tenants + /usage/all + a static FEATURE_REGISTRY (all modes 'on').
- Optimistic writes + toast-on-failure (reuse app/vendors/page.tsx toast pattern) +
  onAccessSignal-style revalidate. version bump reflected by re-fetch.
- Matrix grouped module->page->action via parent_key; hidden/locked parent dims children.
- is_core rows: Lock/Hide disabled (self-lockout floor).

## Verify — DONE
- `npx tsc --noEmit` exits 0 across the WHOLE project (twice). Zero errors in my files.
- All 3 deliverables intact: page (769 ln), EntitlementToggle (209 ln), api.ts CL-F2 block.
- No duplicate exports in api.ts (reconciled around the parallel CL-F1/CL-F3 sessions).

## Integration note (NOT mine to fix)
- A parallel session (CL-F3) owns the top control-plane block in lib/api.ts; CL-F1 owns
  the fleet view-model adapter (getFleetVendors). They reconciled a transient duplicate
  getAdminVendors mid-session. My block reuses their FeatureMode / AdminPlan / getAdminPlans
  / VendorAccountStatus / coerceStatus — no re-declaration. Build is green now.
