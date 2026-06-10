# PREMIUM-UI WAVE 2 — "SIGNAL" (founder said "still looks cheap")

Goal: WORLD-BEST premium (Linear/Vercel/Stripe/Ramp), DISTINCTIVE, cohesive ACROSS
ALL pages. Restyle-only: NO API/route/logic/prop changes. Tokens only (b-/t-/s-),
no raw hex / bg-white / bg-green-100. Dark-mode correct. Build exit 0. Ship LIVE if
cohesive + build solid (advisor: don't stage-by-default; 3rd stage fails the goal).

## ROOT CAUSE (verified)
Only 3 pages (dashboard/calls/leads) deeply restyled. The SHELL (Sidebar/Header/
Logo/Layout) + LOGIN + ~16 pages still wear template chrome. Many pages use RAW
Tailwind colors (bg-green-100, text-red-600, bg-red-50) off the token system +
inline SVG spinners + hand-rolled modals. That mix = "cheap". Fix = elevate the
shell + login + a SIGNATURE, then make every page speak ONE language.

## DESIGN DIRECTION — "Signal" (a precise voice-ops console)
- SIGNATURE MOTIF: a brand-blue (primary-01 #2A85FF) signal/waveform. Famit places
  voice calls -> a tiny 3-bar equalizer glyph beside the wordmark + a thin blue
  signal-line accent under the active sidebar item + a left accent bar on page
  headers. Calm, not flashy.
- WORDMARK: real "Famit" wordmark (Inter Display semibold, tight tracking) + the
  signal glyph, replacing the generic PNG logo / "F" gradient box. Token colors.
- UNIFIED PAGE HEADER: new components/PageHeader (eyebrow + title + subtitle +
  action slot) used on every page so all pages share one masthead rhythm.
- SHELL: sidebar nav group label/section, refined active state (signal accent),
  cleaned header (REMOVE dead "Create -> /products/new", template Search/Msgs that
  don't work; keep theme + user menu + a real page title).

## HARD CONSTRAINTS
- Never touch a shared component's PROP signature. Restyle via className/markup/CSS.
- No lib/api.ts, form-handler, fetch, or route changes.
- Tokens only. After edits: grep changed files for bg-white|text-black|bg-(green|red|
  yellow|blue)-[0-9]|text-(green|red)-[0-9] -> must be ZERO (dark-mode safety).
- Verify past build-green: next build exit 0 + next start + curl routes 200.

## UNITS (verify each; crash-safe)
- [DONE] U0 Orient + plan + advisor + frontend-design. Baseline build EXIT 0 (confirmed).
- [DONE] U1 Signature + shell: globals.css ("signal" eq glyph, page-head, toast, nav-section,
  nav-active-bar, brand-glow), components/PageHeader, Logo wordmark (bg-shade-01 always-dark),
  Sidebar group labels, Header (removed dead Create->/products/new + fake Search/Notif/Msgs,
  added "Run a Campaign" + ThemeButton + signal title), NavLink signal active bar. BUILD EXIT 0.
- [DONE] U2 Login: branded split (always-dark bg-shade-01 brand panel + signal motif + glow +
  feature chips), token-correct, input-base fields. BUILD EXIT 0. (white-on-dark utils OK there.)
- [DONE] U3 Converted 8 off-token pages to ONE language + PageHeader: campaigns(ref), run,
  callbacks, suppression, webhooks, whatsapp, vendors, analytics(funnel recolored brand-blue,
  not purple), settings. All raw bg-*-100/text-*-600 -> Badge/pill-*/toast-*/state-block/data-table.
  Each grep-clean. BUILD EXIT 0 (incremental checkpoints all passed).
- [DONE] U4 Billing: new BillingHeader (PageHeader + tab strip) in _shared.tsx, added to
  overview/vendors/explorer/audit/plan. Added PageHeader to dashboard/calls/leads too. BUILD running.
- [DONE] U5 FULL VERIFY: un-sandboxed `next build` EXIT 0 (46 routes); tsc no new "Cannot find
  name"; NO dangling statusBadge/reasonBadge refs; raw-color clean (only login white-on-dark);
  local next start + curl all 19 routes 200; signature renders; zero runtime errors.
- [DONE] U6 DEPLOYED LIVE per FORTRESS recipe. Backup /opt/famit-panel.bak.1781028098.
  Box 127.0.0.1:3001 + public https://panel.famit.in/login = 200 w/ new look; authed /api = 200.
- [DONE] U7 Appended build_log/wave-build-premium-ui.md (WAVE 2 section) + brain/mistakes+patterns.

## ✅ STATUS: LIVE on https://panel.famit.in. Rollback = restore /opt/famit-panel.bak.1781028098 + restart.

## ROLLBACK
- Pre-wave tree = feat/premium-ui working copy (incl uncommitted base-uplift). NO git by me.
- Live box /opt/famit-panel: BACK UP before deploy. Rollback = restore backup + systemctl restart famit-panel.
