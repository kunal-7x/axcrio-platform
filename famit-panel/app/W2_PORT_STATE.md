# UNIT W2 — core-ops page port (dashboard, campaigns, run, leads, calls, callbacks)

OWN ONLY these 6 page files. Do NOT edit components/, globals.css, layout.tsx, contstants/.
Import W1 shell: Layout, Card, Table, TableRow, Tabs, Select, Field, Search, Button, Badge, NoFound, Spinner.
Keep ALL data wiring (_lib/api/lib) + routes + api contract. Change ONLY presentation.

## Rules applied per page
- DELETE PageHeader usage (eyebrow/subtitle) -> title via <Layout title> only.
- Port the reference list pattern: one .card, header row = title + Search/Tabs (min-h-12),
  body = Table/TableRow. Reference = templates/Customers/CustomerList/CustomerListPage.
- Zero raw hex. Token classes only. Restrained: <=3-4 sections, two-column rhythm.

## Progress
- [DONE] callbacks  — simplest: drop PageHeader, Table/TableRow, one card, toggle as Tabs.
- [DONE] leads      — list card (title+Search+seg Tabs) + Table/TableRow; add-leads col-right.
- [DONE] calls      — list card + Table/TableRow (clickable rows -> detail modal kept). Trim KPI clutter.
- [DONE] campaigns  — list card + Table/TableRow; create-campaign col-right (kept).
- [DONE] dashboard  — 2-col reference rhythm (col-left charts+recent calls, col-right hot leads+usage). Drop hero KPI block.
- [DONE] run        — already uses Tabs/Card/Table; just drop PageHeader + raw-hex toast.

## Notes for deploy agent
- Removed every PageHeader import in these 6 files; PageHeader component itself untouched (W1 owns).
- Replaced raw-hex warning-toast in run/page.tsx with token classes (primary-05).
- `tsc --noEmit` = 0 errors across whole project after changes (verified). W2 did NOT run npm build.
- ALL 6 DONE.
