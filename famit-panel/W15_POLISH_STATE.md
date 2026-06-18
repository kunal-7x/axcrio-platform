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
- [x] UNIT 1 — Run-Campaign (founder's explicit #5: cramped fonts + raw scores):
      raw `ScoreBadge` ("82 hot") → `LeadBadge` in the manual picker; column "Score" → "Status";
      cramped `text-caption` primary guidance → readable `text-body-2` (audience / temperature /
      pacing-caps / window helper). Same stepper/cards — data + typography only.
- [x] UNIT 2 — Knowledge Base: hardcoded sub-readable `fontSize:10`/`text-0` micro-text (chunk
      rank pill, "asks") → token `text-caption`. Tabs rhythm already matches AI Manager (`Tabs mb-5`).
- [x] UNIT 3 — Consistency sweep VERIFY (Bookings, WhatsApp, AI Manager, Creative, Billing,
      Settings): all confirmed ALREADY consistent — single `<Layout title>` (bespoke PageHeader
      fully retired, zero usages), Core_2 `Card`/`Tabs`/`Table`/`Modal`/`Badge`, token type, calm
      empty states, AI Manager 7→4 tabs, Billing tabbed hub, Settings menu archetype. No edits
      needed (additive-only mandate honored). Workflows editor micro-text is in the BUILD group,
      out of this secondary-page scope — intentionally untouched.

## DONE
- Commit `f63e2e1` — UNIT 1 + UNIT 2 (+ this ledger). tsc EXIT 0, next build EXIT 0
  (all routes compiled, /run 21.4 kB, /knowledge 5.55 kB).
- Files changed: `app/run/page.tsx`, `app/knowledge/page.tsx`, `W15_POLISH_STATE.md`.
- Bookings left as-is: status `Tabs` already consistent; it is a dormant module whose list is not
  date-range driven, so mounting GlobalFilters there is deferred (would need URL-param wiring to its
  query) — out of the additive/consistent polish remit.
</content>
</invoke>
