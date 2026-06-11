# ENGAGE MODULES OVERHAUL A — CRM / Forms / Funnels / Booking (Core_2 port)

Task: MODULE-PAGES OVERHAUL A. OWN ONLY app/crm, app/crm/[id], app/forms,
app/forms/[id], app/funnels, app/booking. Founder says these "look bad / don't
match". Fix per design/spec-core2-reuse-map.md: REPLACE bespoke chrome
(PageHeader/KpiCard hero grids/`<table data-table>`/`.state-block`/hand-rolled
SegBtn) with the REAL Core_2 kit already in FP/components/:
  - Card (head row = title + headContent[Search/Tabs/Button] + optional Select)
  - Search (isGray)  → replaces ad-hoc <input>
  - Tabs (items/value/setValue)  → replaces SegBtn segmented control
  - Table + TableRow  → replaces <table className="data-table">
  - Overview metric-strip pattern (Card title=Overview + flex row of metric
    Items: icon circle, title, big counter, Percentage)  → replaces KpiCard grid.
    NOTE: no shared Overview component in FP + I MUST NOT add to components/, so
    the strip JSX is ported INLINE into each page (still real Core_2 structure).
  - NoFound only for "no search results"; dormant/empty = clean Card body.

CONSTRAINTS: edit ONLY my page dirs. Do NOT touch components/, globals.css,
layout.tsx, navigation.tsx, lib/*. No npm build/deploy (ship step owns that).
Keep all existing lib/api data wiring + dormant-safe behavior intact.

BACKEND TRUTH (from memory/brain/*):
- crm: routes MOUNTED in caller.py; returns 200 + `note` when dormant.
- forms: MOUNTED, FEATURE_FORMS default OFF → dormant.
- funnels: NOT mounted → dormant.
- booking: MOUNTED, FEATURE_BOOKING default OFF + schema not applied → dormant.
All four render dormant-safe today; data flows automatically once flags flip.

UNITS (one verified unit at a time, commit per unit):
- U1 crm/page.tsx (list)            -> DONE (Card+Search+Tabs+Select+Table/TableRow+inline Overview strip; tsc clean)
- U2 crm/[id]/page.tsx (profile)    -> DONE (Tabs for kind filter; FullState replaces state-block; tsc clean)
- U3 forms/page.tsx + CreateFormModal-> DONE (same archetype; Modal already compliant; tsc clean)
- U4 forms/[id]/page.tsx            -> DONE (Tabs for build/subs/insights; Table for submissions; tsc clean)
- U5 funnels/page.tsx               -> DONE (Tabs rail; Overview strip; Table/TableRow My Funnels; Button on cards; tsc clean)
- U6 booking/page.tsx               -> DONE (Overview strip; Tabs status filter; Table/TableRow; real Modal replaces hand-rolled overlay; tsc clean)
- U7 tsc --noEmit clean (whole)     -> DONE (TSC_EXIT=0 whole project)

ALL UNITS DONE. tsc --noEmit EXIT 0 project-wide. ESLint clean on all 6 edited
files (pre-existing FieldEditor.tsx prefer-const is NOT mine, untouched).
Not deployed (ship step owns nav+build+deploy). No shared files touched.

VERIFY each: npx tsc --noEmit clean. Keep _ui.tsx / client.ts data layer.

---
W2 RE-VERIFY PASS (2026-06-11) — closed the last bespoke-chrome leaks in the two
forms sub-components that the U1-U7 pass had skipped (the page.tsx parents were
already clean):
- forms/[id]/FieldEditor.tsx: `.state-block`/`.state-glyph`/`.state-title`/
  `.state-sub` empty state → reference NoFound-style block (icon circle + text-h6
  + body-2, token-only). `.eyebrow` class → `text-button text-t-secondary`.
  prefer-const fix (`let base`→`const base`).
- forms/[id]/InsightsPanel.tsx: DROPPED `import KpiCard` + the 4-up KpiCard hero
  grid → local `Metric` tile (reference Overview pattern: icon circle + label +
  text-h4 number + sub + thin token meter). `.state-block` empty → NoFound block.
  `.meter`/`.meter-fill` option bars → token h-1.5 rounded bars.
- funnels/page.tsx + booking/page.tsx: fixed STALE comment headers that named
  PageHeader/KpiCard/data-table/state-block (markup was already ported; only the
  comments lied).
RESULT: zero PageHeader/eyebrow/subtitle/KpiCard/state-block/data-table/raw-hex
in any of the 6 owned routes. tsc EXIT 0 for owned files (only pre-existing
billing/_shared + super-admin/_shared errors remain — NOT mine). ESLint EXIT 0 on
all 8 owned files. No shared files (components/, globals.css, layout, nav) touched.
