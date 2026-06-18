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

---

## CONSISTENCY POLISH PASS — secondary pages (2026-06-18, commit `f63e2e1`)

Goal: make the SECONDARY pages (Bookings, Knowledge, WhatsApp, AI Manager, Creative Studio, Billing,
Settings, Run-Campaign) consistent with the new shell + Core_2 components + Build-phase typography.
Reuse-only, additive — did NOT break the Build-phase shell/pages.

### Ground truth (explore)
A prior ui-overhaul wave + the W15 Build phase had already normalized MOST surfaces:
every page is on a single `<Layout title>` (bespoke `PageHeader` fully retired — **0** `<PageHeader`
usages), Core_2 `Card`/`Tabs`/`Table`/`Modal`/`Badge` + token classes + calm empty states; AI Manager
already 7→4 tabs; Billing already a tabbed hub; Settings on the `SettingsPage` menu archetype. So the
remaining gaps were NARROW, not a rebuild.

### What shipped
- **Run-Campaign** (founder's explicit #5 — "cramped fonts", "no raw scores"):
  - Manual-picker raw `ScoreBadge` ("82 hot") → business-friendly **`LeadBadge`** (Hot/Warm/Cold/
    Dead/Booked/Callback/Interested word). Column header "Score" → "Status". One badge vocabulary now
    on Run too (matches Dashboard/Leads/Calls/CRM).
  - Cramped `text-caption text-t-tertiary` PRIMARY guidance → readable `text-body-2 text-t-secondary`
    on the audience-compose, temperature-legend, pacing-caps and calling-window helper lines.
- **Knowledge Base**: sub-readable hardcoded `fontSize:10`/`text-0` micro-text (chunk-rank pill,
  "asks" label) → token `text-caption`.
- **Bookings / WhatsApp / AI Manager / Creative / Billing / Settings**: VERIFIED already consistent
  (single Layout title, Core_2 chrome, token type, calm states) — no edits needed.

### Verification
- `npx tsc --noEmit` EXIT 0.
- `npm run build` EXIT 0 — all routes compiled (/run 21.4 kB, /knowledge 5.55 kB).
- gitleaks staged scan: 0 leaks.

### Honest scope notes
- Bookings status `Tabs` already consistent; deferred mounting GlobalFilters there (dormant module,
  list not date-range driven yet — would need URL-param wiring; out of the additive remit).
- Workflows editor/preview micro-text is in the BUILD nav group, not a secondary page — left untouched.
- No box deploy (FORTRESS panel deploy is a later gated step). No `.py` touched.

### Files changed (polish pass)
- `famit-panel/app/run/page.tsx`
- `famit-panel/app/knowledge/page.tsx`
- `famit-panel/W15_POLISH_STATE.md` (new ledger)
