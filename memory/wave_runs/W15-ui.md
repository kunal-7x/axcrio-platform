# W15 — UI Information-Architecture Consolidation (wave run)

Branch: `fix/realtime-voice-kernel-v2` · Scope: FRONTEND ONLY (`famit-panel/`) · No `.py` · No box deploy.
Plan: `design/W15-UI-IA-PLAN.md` · Reuse-map: `design/spec-core2-reuse-map.md` · UI contract: `design/W14-REPORTING-AIM-SEAM.md §7`.
Date: 2026-06-18.

## What shipped (all units, build green)

Reused the Core_2 kit + existing page layouts/components — rewired data + fixed PLACEMENT/grouping.
Never invented a component. Each unit: `npx tsc --noEmit` + `npm run build` EXIT 0, then commit.

### SHELL (commit 1 — `feat(ui/W15): shell …`)
- `contstants/navigation.tsx` — rail regrouped into plain task language:
  **WORK** (Dashboard, Leads & CRM, Call Logs, Bookings, AI Manager) ·
  **GROW** (Campaigns, Run, Creative Studio, Ad Automation, Funnels, Forms) ·
  **MESSAGE** (WhatsApp, Customer Support) · **INTELLIGENCE** (Reports, Knowledge) ·
  **MONEY** (Billing hub tabs, Payments) · **BUILD** (Workflows, Webhooks, Integrations) ·
  Super Admin unchanged. **AI-Manager 9 children → 1 link** (in-page tabs own the sub-routes).
  Foundation (Do-Not-Call, admin Vendors) folded into the Settings footer (`navigationUser`).
  Every `feature_key`/`roles` gate for a still-visible entry PRESERVED VERBATIM.
- `lib/badges.tsx` — added **LeadBadge** + `leadTierOf` (one business-friendly vocabulary:
  Hot/Warm/Cold/Dead/Booked/Callback/Interested) derived from status/stage/outcome/score;
  accepts a loose `LeadLike` so it works on Lead, CallLog, and W14 report rows. No raw scores.
- `components/GlobalFilters/` — the ONE shared filter bar (date-range presets [Today default] +
  campaign + lead-status), composing existing `Select`/`CampaignSelect`. URL-param state
  (`?range/campaign/status/from/to`) via next/navigation so it persists across the
  Dashboard→Reports→Calls drill-down. Drops into a `Card` `headContent` slot — no new layout primitive.
- `lib/report.ts` — the W14 §5/§7 reporting client. **Tries the real `/report*` seam first**
  (range-aware, event-fed) and, since those routes are NOT mounted on the box yet (W14 = seam note),
  **dormant-safely COMPOSES the same `Report` shape from the live `/stats`+`/analytics`+`/leads`**.
  Marks `live_seam:false` on the fallback (UI shows an honest note). Exported `BASE`/`authHeaders`
  from `lib/api.ts` (additive).

### Pages
- **Dashboard `/`** (commit 2) — the consolidated Today-first cockpit. Absorbs the scatter:
  top-line KPI strip (calls/connected/booked/hot) + GlobalFilters in the Card head, the conversion
  **funnel inline** (was the isolated `/analytics`), call-volume area chart, hot-leads via **LeadBadge**
  → `/crm?status=hot`, Usage tile → Billing hub. "Full report" deep-links to Reports carrying the range.
  Suspense-wrapped (useSearchParams). Same Core_2 Card/Table/recharts chrome — data source swapped.
- **Call Logs `/calls`** (commit 3) — Calls | Callbacks as URL-driven tabs (`?tab=callbacks`);
  `/callbacks` kept as a redirect alias (no orphan). One call surface.
- **Reports `/analytics`** (commit 3) — relabeled "Reports"; mounts the shared GlobalFilters so the
  Dashboard→Reports hop carries `?range/campaign`; funnel + funnel-details tables preserved.
- **Leads** (commit 3) — raw `ScoreBadge` → `LeadBadge` (column Score→Lead).
- **CRM** (commit 3) — Suspense-wrapped; honors the shared `?status=` deep-link (status=hot → Hot view;
  a tier word matching a stage selects that stage tab). CRM's own `StageBadge` already token-clean.

## Consolidated (scatter killed)
- Funnel + volume + KPI → **Dashboard** (was split Dashboard + isolated `/analytics`).
- `/analytics` → **Reports** = the deep drill-down the Dashboard links into (one analytics UX, two depths).
- `/callbacks` → **Call Logs** Callbacks tab (alias preserved).
- AI-Manager 9 nav children → **1 link** + in-page tabs.
- Foundation group (Do-Not-Call, admin Vendors) → **Settings footer**.
- Lead scores everywhere → **one LeadBadge vocabulary** (Dashboard + Leads); CRM aligned to the same words.
- One **GlobalFilters** bar on Dashboard + Reports (Today default, URL-shared params).

## Verification
- `npx tsc --noEmit` EXIT 0 after every unit.
- `npm run build` EXIT 0 — **59/59 static pages generated**, no errors. (next.config has
  `typescript.ignoreBuildErrors` + `eslint.ignoreDuringBuilds`, but tsc was run separately and is green.)
- Feature-key audit: only the intentionally-folded leaf keys + the dissolved `mod.sell` group key were
  dropped; every still-visible rail gate is byte-identical to HEAD~3.

## NOT done / honest gaps (founder steer)
- The real **per-range/real-time** numbers need the W14 `/report*` seam mounted on the box (separate
  founder-signed wiring wave, agent.py untouched). Until then the dashboard/Reports show the live coarse
  `/stats`+`/analytics` data (real, not range-sliced) with an in-UI note. `lib/report.ts` upgrades
  automatically the moment the seam is live — no UI change needed.
- WhatsApp/Communication fold and the Billing 6-tab hub were left as nav-level consolidation only this
  pass (routes grouped under MESSAGE/MONEY); the in-page tab merge for those two is a safe follow-up unit.
- No box deploy (panel deploys to FORTRESS separately, later gated).

## Files changed
- `famit-panel/contstants/navigation.tsx`
- `famit-panel/lib/badges.tsx`, `famit-panel/lib/report.ts` (new), `famit-panel/lib/api.ts` (export BASE/authHeaders)
- `famit-panel/components/GlobalFilters/index.tsx` (new)
- `famit-panel/app/page.tsx` (Dashboard)
- `famit-panel/app/calls/page.tsx`, `famit-panel/app/callbacks/page.tsx`
- `famit-panel/app/analytics/page.tsx` (Reports)
- `famit-panel/app/leads/page.tsx`, `famit-panel/app/crm/page.tsx`
- `famit-panel/W15_UI_STATE.md` (state ledger)
