# PREMIUM-UI WAVE — STATE (feat/premium-ui)

Founder #2 priority: make the panel WORLD-BEST (Linear/Vercel/Ramp/Stripe), not generic.
NON-BREAKING: reuse existing components + endpoints. No API/route/logic changes.
Branch: feat/premium-ui (off main). Baseline build GREEN (exit 0) before any change.

## HARD CONSTRAINTS (from advisor + lib/api.ts review)
- NO prior-period data anywhere (Stats/Usage/Billing/BillingOverview have no last-period field).
  => DO NOT fabricate "+12%" deltas. Use ONLY real signals: series sparklines, cap-ratios,
     answer-rate = answered/total, outcome breakdowns. Delta only when a real prior exists.
- Keep shared component PROP SIGNATURES unchanged (Card/Button/Table/Select). Restyle internals/CSS only.
- Build-green != looks-premium (can't see pixels). This is the LIVE revenue panel =>
  bias to STAGE-FOR-REVIEW on the branch unless confident. Do NOT blind-deploy a half-baked redesign.
- Badge consolidation = the #1 cheap->premium lever (5 hand-rolled bg-green-100 fns today).

## TASKS
- [DONE] Ground: read pages, components, tokens, lib/api.ts, kits. Baseline build exit 0.
- [DONE] U1 design system: globals.css premium utilities + new Badge/KpiCard/Sparkline + lib/badges. COMMIT.
- [DONE] U2 Dashboard (app/page.tsx). COMMIT.
- [DONE] U3 Call Logs (app/calls/page.tsx). COMMIT.
- [DONE] U4 Leads (app/leads/page.tsx). COMMIT.
- [DONE] U5 Billing overview (app/billing/overview/page.tsx) + adopt Badge in _shared. COMMIT.
- [DONE] VERIFY full build exit 0. (exit 0, all 42 routes compiled, zero TS/lint errors)
- [DONE] Decide deploy vs stage; staged-for-review (visual review needed on live revenue panel).
- [DONE] Write build_log/wave-build-premium-ui.md + update HANDOFF + brain.

## ROLLBACK POINT
- Pre-wave: branch main @ commit 670bf09-era tree. Live box /opt/famit-panel UNCHANGED (staged, not deployed).
- All work isolated on feat/premium-ui; main untouched.

## STATUS: COMPLETE — staged for founder visual review (NOT deployed to live).
