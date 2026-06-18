# Run-page redesign — Phase 1 (FE only, NO deploy)

## Goal
Re-house the single-scroll 7-card Run page into a 4-step horizontal stepper +
sticky Launch-summary rail. PURE presentational re-housing — keep ALL state,
handlers, buildRunPayload, queue/force logic, getStatus poll, liveLeads verbatim.

## Steps
- ① Campaign & Audience — campaign Select + 4 source modes as Tabs row (progressive disclosure)
- ② Voice & Providers — reuse _voice-providers.tsx verbatim
- ③ Pacing & Handoff — Pacing Field grid + HandoffTeam compact
- ④ Review & Launch — read-only summary + queue notice + Launch button + Start anyway; Live Status below once jobId

## Units
- [DONE] U1: app/run/_stepper.tsx — Core_2-composed horizontal stepper (role=tablist, aria-current=step, clickable completed, lock-ahead, mobile pill+dots)
- [DONE] U2: refactor app/run/page.tsx into 4 steps + sticky summary rail
- [DONE] U3: npm run build LOCALLY green + commit (gitleaks 0)

## Facts
- Icon registry HAS: check-circle-fill, check-circle, chevron, arrow, check, clock, info, close. NO "send" (renders empty path silently — keep existing icon="send" as-is).
- Tokens only (globals.css): .card .surface .kpi/.kpi-label/.kpi-value .eyebrow .state-block/.state-glyph, text-h*/body/button/caption, bg-b-surface1/2/3, text-t-primary/secondary/tertiary, border-s-subtle/stroke2, primary-01..05, shadow-depth, Badge.
- Segmented-pattern reference: _voice-providers.tsx:362-401.
- NO deploy this phase.

## Status: COMPLETE — Phase 1 build green + Phase 2 deployed to FORTRESS.

## Phase 2 Deploy (2026-06-14)
- Local build: EXIT 0, /run = 16.8 kB, no TS errors
- BUILD_ID before: p6hSTJX9R46-NQdLf8Daw
- BUILD_ID after:  jcDEy4iclWbxS_zvVpvk0
- Tarball md5: 638736b0cc2b6461361489e2bd79924c (matched on box)
- Backup: /opt/famit-panel.bak-<timestamp>
- Loopback 200: http://127.0.0.1:3001/ + /run 200
- Edge 200: https://panel.famit.in/
- 0 recent 5xx
- EARNER GATE PASS: agent.py md5=9150fabe4ff62b4b4470f9a87df346e5 UNCHANGED, famit-agent=active, famit-caller /health=200
