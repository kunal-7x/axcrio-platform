# AI Manager F1 — Test Console + Overview (build state)

Owner: frontend F1 subagent. Branch: feat/premium-ui.
Convention: ON-DISK premium-ui "Signal" component language (Layout/PageHeader/Card/Badge/Button/
Field/Icon + globals.css utilities kpi/state-block/data-table/pill/meter/skeleton/rise-in/toast),
mirroring app/billing/_shared.tsx. NOT raw Core_2 ports (the MEMORY note is superseded by the branch).
Dormant-safe by construction: /api/ai-manager/* is DEFINED-NOT-MOUNTED -> 404/501/503/network => dormant.

## Units
- [DONE] U1 _lib.ts extend: types (AimParse §22, AimCommand, AimSummary) + testCommand/confirmCommand/
  executeCommand/cancelCommand/getAimSummary/getAimCommands. read() never throws; write() throws friendly.
- [DONE] U2 _shared.tsx: AimHeader (PageHeader eyebrow "AI Manager" + pill tab-rail) + riskVariant/
  riskLabel/statusVariant + AimStat (KPI tile) + ErrorBanner + AimDormant panel + FlowStep + selectCls.
- [DONE] U3 test/page.tsx: Test Console hero. Chat composer -> POST /commands/test -> NLU result card
  (intent/risk/requires_confirmation/requires_pin/entities/missing/summary/safe). Confirm/cancel row,
  PIN modal, JSON-trace tab, example chips, dormant + error states.
- [DONE] U4 overview/page.tsx: Overview dashboard (status, phone#, today/succeeded/failed-denied/
  pending/credit-impact KPIs, recent sessions, recent risky actions, quick test input, config board).
- [DONE] U5 page.tsx: redirect /ai-manager -> /ai-manager/overview.

## API binding (master §10/§22)
- POST /api/ai-manager/commands/test {text, channel} -> {command_id, ...§22 parse}
- POST /api/ai-manager/commands/:id/confirm | /execute | /cancel
- POST /api/ai-manager/pin/verify {command_id?, pin}
- GET /api/ai-manager/dashboard/summary
- GET /api/ai-manager/status, /sessions?limit=, /commands?risk=&limit=

## §22 NLU schema (the AI bubble card)
{intent, action_type, confidence, risk_level(0-4|safe/bulk/money/destructive), requires_confirmation,
 requires_pin, entities{}, missing_fields[], assumptions[], user_facing_summary, safe_to_execute, block_reason}

## Verify
- [DONE] tsc --noEmit -p tsconfig.json -> EXIT 0 (whole project clean).
- [DONE] next lint on all F1 files -> "No ESLint warnings or errors".
- NO npm build per instructions.

## Reconciliation notes (multi-session)
- _lib.ts + _shared.tsx were co-edited by the F2 (Setup/Users) session. F1 additions
  appended without clobbering: parse-risk axis named AimParseRisk (F2 owns the L0–L4
  `AimRiskLevel` setting enum). Added parseRiskLevel/Variant/Label, statusVariant, rupees,
  AimStat to _shared; testCommand/confirm/execute/cancel + getAimSummary/getAimCommands +
  AimParse/AimCommand/AimSummary/AimChannel to _lib.
- Fixed a pre-existing lint break in _shared.tsx (unused default `Badge` import → type-only).
- /ai-manager/page.tsx -> redirect to /overview; legacy board copied verbatim to
  /ai-manager/command-center/page.tsx (import fixed ./_lib -> ../_lib). Tab-rail "Command
  Center" href repointed to /command-center.
</content>
</invoke>
