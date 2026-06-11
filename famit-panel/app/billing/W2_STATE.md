# UNIT W2 — Billing pages port (Income/* templates)

Owner: W2 agent. Scope: app/billing/* ONLY (overview/plan/vendors/explorer/audit + _shared.tsx + [id]).
Reference: core-2-dashboard-builder-react templates/Income/* + UpgradeToProPage.

## Plan (port map rows 12-16)
- overview  -> Income/EarningPage (Balance hero strip + Countries cost-share + Transactions). DONE-criteria: no PageHeader, Layout title only, Cards, tokens.
- vendors   -> EarningPage/Countries ranked list (CountryItem bar) + Table. 
- explorer  -> Income/StatementsPage (Statistics strip + Transactions table + Filters).
- audit     -> StatementsPage/Transactions (read-only reconcile table).
- plan      -> UpgradeToProPage (Pricing cards adapted to plan/rates) + Transactions ledger + admin panel.
- [id]      -> keep working (uses HeroCard+Sparkline from _shared); light token cleanup only.

## Key decisions
- REMOVE BillingHeader (PageHeader eyebrow+subtitle+tab-strip) from all 5 pages. Title via <Layout title="..."> ONLY.
- Add token-based `BillingTabs` (plain pill row, reference Tabs aesthetic) for cross-route nav, rendered in page body (NOT a masthead, no eyebrow/subtitle).
- Reference stat strip = icon-circle + sub-title-1 + big number. NO fabricated % deltas (memory rule) -> drop Percentage on heroes.
- Keep _shared: money, fmt, StatusBadge, ErrorBanner, outcomeVariant, moneyShort, VENDOR_COLORS, HeroCard, Sparkline (latter two used by [id]).
- Drop CostDonut/ShareRow/ghostBtnCls/HeroCard usage from the 5 main pages; reuse reference Card/Table/TableRow/Search/Select/Button/Badge.
- Keep ALL data wiring/api routes unchanged. Keep admin-gated logic in plan/audit.

## Progress — ALL DONE (tsc --noEmit = 0 errors across whole project)
- [x] _shared.tsx rewrite (removed BillingHeader/PageHeader/HeroCard/CostDonut/ShareRow/ghostBtnCls/selectCls/btnCls; added BillingTabs + StatStrip/StatItem + BarRow; kept money/fmt/StatusBadge/ErrorBanner/outcomeVariant/moneyShort/VENDOR_COLORS/Sparkline)
- [x] overview  -> EarningPage (StatStrip + vendor Table + Countries-style BarRow col-right)
- [x] vendors   -> Table with Countries-style share bar; row -> /billing/vendors/[id]
- [x] explorer  -> StatementsPage (StatStrip + Filters card + per-call Table)
- [x] audit     -> reconcile Table (admin Sync now preserved)
- [x] plan      -> UpgradeToProPage Pricing-style plan card + ledger Table + admin panel (admin gate preserved)
- [x] [id]      -> StatStrip + Sparkline + BillingTabs; chart shadow tokenized
- ZERO raw hex in all .tsx. All titles via <Layout title>. No PageHeader anywhere.
