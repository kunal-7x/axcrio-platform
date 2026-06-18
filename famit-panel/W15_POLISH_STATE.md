# W15 — Secondary-page CONSISTENCY POLISH PASS (state ledger)

Branch: `fix/realtime-voice-kernel-v2` · Scope: FRONTEND ONLY (`famit-panel/`) · No `.py` · No box deploy.
Plan: `design/W15-UI-IA-PLAN.md` · Build-phase wave-run: `memory/wave_runs/W15-ui.md`.
Date: 2026-06-18. Goal: make the SECONDARY pages (Bookings, Knowledge, WhatsApp, AI Manager,
Creative Studio, Billing, Settings, Run-Campaign) consistent with the new shell + GlobalFilters +
Core_2 components + typography/spacing from the Build phase. Reuse components, never from scratch.
Additive/consistent edits only — do NOT break the Build-phase shell/pages.

## GROUND TRUTH (explore)
A prior ui-overhaul wave + the W15 Build phase already normalized MOST pages:
- Every page uses a single `<Layout title="…">` (the bespoke `PageHeader` masthead is fully retired —
  zero `<PageHeader` usages remain; the header zone is uniform).
- Secondary pages already use Core_2 `Card`/`Tabs`/`Table`/`Modal`/`Badge` + token classes + calm
  empty states (`state-block` / centered empty cards). AI Manager already collapsed 7→4 tabs.
- So the consistency gaps left are NARROW and concrete (below), not a rebuild.

## POLISH UNITS (each: tsc+build green, then commit; index.lock retry up to 6×)
- [ ] UNIT 1 — Run-Campaign (founder's explicit #5: cramped fonts + raw scores):
      swap raw `ScoreBadge` ("82 hot") → business-friendly `LeadBadge` in the manual picker;
      bump cramped primary `text-caption` guidance → readable `text-body-2`; align temperature
      vocabulary to the one badge language. Same stepper/cards — just data/typography polish.
- [ ] UNIT 2 — Knowledge Base: replace hardcoded sub-readable `fontSize:10/11`/`text-0` micro-text
      with token `text-caption`; keep the Tabs rhythm consistent with AI Manager (`Tabs mb-5`).
- [ ] UNIT 3 — Consistency sweep verify (Bookings, WhatsApp, AI Manager, Creative, Billing,
      Settings): confirm single Layout title + Core_2 chrome + token type; fix any stray cramped
      micro-text. (Most already consistent — additive touch-ups only.)

## DONE
(append as units verify)
</content>
</invoke>
