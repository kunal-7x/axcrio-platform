# UNIT W2 — PORT PAGES (comms-settings) — STATE

Owner: W2 agent. Owns ONLY: app/whatsapp, app/suppression, app/webhooks,
app/vendors, app/analytics, app/settings. MUST NOT edit components/, globals.css,
layout.tsx, contstants/ (W1 owns shell — import its components).

## Per-page port plan (from design/ui-page-port-map.md)
- whatsapp   → MessagesPage/CustomerList recipe. ADAPT: log = CustomerList card (Search+Table); send = Field form card.
- suppression → CustomerList (Search + Table + FieldFiles bulk upload). REUSE-DIRECT.
- webhooks    → SettingsPage section pattern (Field + Switch + Button) list. ADAPT.
- vendors     → SettingsPage-style sectioned config / CustomerList list. ADAPT (admin-gated).
- analytics   → Income/StatementsPage (one chart + one table). ADAPT.
- settings    → SettingsPage (sticky Menu + anchored Field/Switch cards). REUSE-DIRECT.

## Cross-cutting transforms (every page)
1. DELETE PageHeader import + masthead. Title via <Layout title> only.
2. bespoke data-table -> reference Table/TableRow.
3. skeleton/state-block/state-glyph/toast -> Spinner + token empty block + token error banner.
4. raw inputs -> Field/Select/Switch/FieldFiles/Search.
5. ZERO raw hex (kill #EF9D0E, #2A85FF, #FF6A55).
Keep ALL existing _lib/api data wiring + routes. Do NOT change shared prop signatures. Do NOT run npm build.

## Progress
- [x] whatsapp   DONE (CustomerList card recipe + Field send form)
- [x] suppression DONE (CustomerList Search+Table + upload card)
- [x] webhooks    DONE (CustomerList Table + Field/Checkbox create card)
- [x] vendors     DONE (CustomerList Table + Field/Select create card)
- [x] analytics   DONE (Income KPI strip + funnel chart + details table)
- [x] settings    DONE (SettingsPage sticky Menu + anchored Field/Switch cards)
All 6: PageHeader removed, raw hex removed, reference Table/TableRow/Spinner/Field/Select/Search used.
