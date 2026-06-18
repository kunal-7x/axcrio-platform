# W15 — UI Information-Architecture Consolidation (BUILD STATE)

Branch: `fix/realtime-voice-kernel-v2` · Scope: FRONTEND ONLY (`famit-panel/`) · No .py · No box deploy.
Plan: `design/W15-UI-IA-PLAN.md` · Reuse-map: `design/spec-core2-reuse-map.md`.

## Build order (crash-safe per unit; tsc+build green per unit; commit each)

1. [DONE] SHELL — nav rewire (`contstants/navigation.tsx`): WORK/GROW/MESSAGE/INTELLIGENCE/MONEY/BUILD; AI-Manager 9->1+tabs; preserve every feature_key/roles.
2. [DONE] SHELL — `LeadBadge` (`lib/badges.tsx`): business-friendly tier helper (Hot/Warm/Cold/Dead/Booked/Callback/Interested).
3. [DONE] SHELL — `GlobalFilters` (`components/GlobalFilters`): compose Select+DateAndTime+CampaignSelect+Tabs; URL-param state; Today default.
4. [DONE] SHELL — `lib/report.ts` reporting client (W14 §5/§7 contract, dormant-safe fallback to live /analytics+/stats).
5. [DONE] Dashboard `/` — consolidate analytics (funnel + volume + KPI) + GlobalFilters + LeadBadge; "View full report" -> Reports.
6. [DONE] Call Logs `/calls` — Callbacks as a tab; LeadBadge in transcript area.
7. [DONE] Reports `/analytics` — relabel + GlobalFilters + share params; funnel + breakdown tables.
8. [PENDING] CRM/Leads polish — LeadBadge wired (leads already uses ScoreBadge; swap to LeadBadge).

## Key facts learned (ground truth)
- `/report*` W14 routes are NOT mounted on the box yet (seam note only). LIVE routes: `/analytics`, `/stats`, `/calls`, `/leads`, `/callbacks`. So `lib/report.ts` builds the W14-shaped report by COMPOSING the live endpoints (dormant-safe), and will prefer real `/report*` when present.
- Card head row: `<Card title headContent={...}>` is the canonical chrome slot (used for GlobalFilters).
- Nav: groups = `{title,icon,list:[...]}` (no href) -> Dropdown; links = `{title,icon,href}`. `feature_key`/`roles` gating in `resolveNav`. MUST preserve keys verbatim.
- Badge variants: success/danger/warning/info/neutral -> `pill-*`. LeadBadge composes `<Badge>`.
- Lead type: {status, score, last_outcome, hot}. CallLog: {status, interest}.
- Tabs/Select option type: `{id:number, name:string}`.

## Guardrails
- No .py. No box deploy. No backend/route signature change. Reuse Core_2 — compose, never invent.
- Every previously-live route still resolves (tab anchor or alias). Zero orphans.
- index.lock retry up to 6x. Do NOT edit ORCHESTRATOR.md.
