# UNIT W2 — Port pages (ai-manager + ads/payments/support/workflows)

Owner: W2 agent. Branch: feat/premium-ui. NO npm build here (deploy agent builds).

## Rule
PORT reference kit (core-2-dashboard-builder-react) markup; swap our /api data only.
Import W1 shell components (Layout, Card, Tabs, Table, TableRow, Badge, Button,
Select, Search, Field, NoFound, Spinner). Do NOT edit components/, globals.css,
layout.tsx, contstants/. Tokens only, zero raw hex. One `<Layout title>` heading,
NO PageHeader/eyebrow/subtitle. Preserve Control-Layer entitlement (Sidebar HIDE/LOCK).

## Scope + plan
1. ai-manager: COLLAPSE 7 sub-routes -> 3 tabs (Home / Try it / Setup). Delete
   _shared pill-rail (AimHeader) + spinner redirect. Show Safe/Needs-approval/Blocked
   badges, not L0-L4. Keep _lib.ts data wiring. Make /ai-manager the index page.
   - Home = Overview + Command History + Approvals (tabs inside page).
   - Try it = Test console (single input + response).
   - Setup = Setup + Capabilities + Team (sections).
   - Keep sessions/[id] detail route. Drop command-center, overview, test, setup,
     capabilities, users, approvals, commands separate route files -> redirect or remove.
2. ads (app/ads/page.tsx + _lib.ts) -> PromotePage pattern.
3. payments (app/payments/page.tsx + _api.ts + _shared.tsx) -> Income/PayoutsPage.
4. support (app/support/page.tsx + api.ts) -> MessagesPage chat OR Notifications list.
5. workflows (keep React Flow; reskin chrome with Layout title + reference tokens).

## Progress
- [DONE] Read design docs + shared component signatures + _lib/_shared + ALL owned pages.
- [DONE] Confirmed globals.css utilities (kpi/data-table/state-block/surface/card OK to keep;
  eyebrow/page-head-*/signal-glyph = founder-rejected decoration -> remove body usages).
- [IN PROGRESS] ads: remove PageHeader masthead, title via Layout only, Tabs component.
- [ ] payments: remove PaymentsHeader + drawer page-head-eyebrow/signal-glyph.
- [ ] support: remove PageHeader masthead + body eyebrow usages.
- [ ] workflows: remove PageHeader masthead; keep React Flow; Tabs component.
- [DONE] ads: removed PageHeader masthead; title via Layout; Refresh inline w/ tabs.
- [DONE] payments: removed PaymentsHeader + drawer page-head-eyebrow/signal-glyph; PaymentsHeader deleted from _shared.
- [DONE] support: removed PageHeader masthead; .eyebrow -> text-overline; activity panels -> Card.
- [DONE] workflows: removed PageHeader masthead; title via Layout; Refresh inline; React Flow untouched.
- [DONE] ai-manager: removed AimHeader pill-rail from _shared; new index page.tsx (Layout title + reference Tabs
      Home/Try-it/Setup); built _home.tsx (overview+history+approvals), _tryit.tsx (test console),
      _setup.tsx (profile+team+capabilities). Plain Safe/Needs-approval/Blocked via parseRiskLabel.
- [DONE] Converted old 8 sub-route pages -> thin client redirects to /ai-manager(?tab=...).
- [DONE] sessions/[id]: replaced AimHeader masthead with plain back-link + Refresh row; title via Layout.
- [DONE] VERIFIED: tsc --noEmit EXIT=0 (whole project); next lint app/ai-manager = no warnings/errors.

## CROSS-CUTTING NOTE FOR W1 / DEPLOY AGENT (contstants/ is W1-owned, NOT edited here)
contstants/navigation.tsx lines 74-80 still list the 7 OLD AI Manager sub-routes as children
(/ai-manager/overview, /test, /commands, /approvals, /capabilities, /setup, /users). They all
REDIRECT now so nothing breaks, but to match the simplified IA the AI Manager nav group should
collapse to either ONE leaf  { title:"AI Manager", href:"/ai-manager" }  OR 3 children:
  Home  -> /ai-manager
  Try it -> /ai-manager?tab=tryit
  Setup -> /ai-manager?tab=setup
(W1 owns nav; flagged for them to apply.)

## DONE — all W2 pages compliant
PageHeader/AimHeader/PaymentsHeader mastheads removed everywhere; single <Layout title> heading;
zero eyebrow/subtitle; tokens only; AI Manager 7 routes -> 3 tabs; plain Safe/Needs-approval/Blocked.

## Key finding
Every owned page already uses reference Card + data-table + token utilities well.
The ONE cross-cutting violation = bespoke masthead (PageHeader/AimHeader/PaymentsHeader =
eyebrow+title+subtitle) which the founder explicitly rejects. Fix = title via <Layout title>
only; lift any top-right action button into the page body. Keep ALL _lib/_api data wiring.

## Decisions
- NoFound component is hardcoded e-commerce keywords -> use lightweight inline
  empty blocks inside Cards instead (MiniEmpty pattern), per principles §9.
- Risk display: Safe/Needs approval/Blocked via Badge tone; keep L-code in tooltip/detail.
