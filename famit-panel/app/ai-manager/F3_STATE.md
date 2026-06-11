# AI Manager FRONTEND F3 — build state

Owner: F3 agent. Routes owned: /ai-manager/commands, /ai-manager/sessions/[id],
/ai-manager/approvals, /ai-manager/capabilities. Plus _lib.ts additive extension,
_f3.tsx shared module, nav wiring.

Backend /api/ai-manager/* = DEFINED-NOT-MOUNTED + flag OFF -> every read degrades to
a premium dormant view (404/501/503/network -> {kind:"dormant"} -> NoFound/DormantPanel).
Do NOT edit shared components/. Do NOT npm build.

API contract (master §10):
- GET  /api/ai-manager/commands?status&channel&risk&from&to&user&module&limit  (Command History)
- GET  /api/ai-manager/commands/:id
- GET  /api/ai-manager/sessions/:id            (transcript + command chain + provider meta)
- GET  /api/ai-manager/audit-logs?session_id&command_id
- GET  /api/ai-manager/action-runs?command_id&session_id
- POST /api/ai-manager/commands/:id/confirm | /execute | /cancel
- POST /api/ai-manager/pin/verify
- POST /api/ai-manager/commands/test (Test Console — NOT my page, but adapter added to _lib)

Risk levels (master §6): L0 safe / L1 low / L2 medium / L3 high / L4 blocked.
Command status (§8): pending / needs_confirmation / needs_pin / executing / succeeded / failed / denied / cancelled.

## UNITS
1. _lib.ts additive extension (types + reads + writes + INTENT_CATALOG) — DONE
2. _f3.tsx shared header + helpers — DONE
3. /ai-manager/commands (Command History) — DONE
4. /ai-manager/sessions/[id] (Session Detail) — DONE
5. /ai-manager/approvals (Pending Approvals) — DONE
6. /ai-manager/capabilities (Capability Catalog) — DONE
7. nav wiring (Command group -> AI Manager subgroup) — DONE
8. tsc typecheck on new files — DONE (0 errors project-wide)
9. next lint on all 4 pages + 3 shared files — DONE (0 warnings/errors)

VERIFIED 2026-06-10: tsc --noEmit = 0 errors; next lint = clean. Reused existing
_shared.tsx (AimHeader/fmt/parseRiskVariant/parseRiskLabel/statusVariant/rupees/
ErrorBanner/DormantPanel/AimStat) + existing _lib.ts client (read/write/dormant,
confirmCommand/executeCommand/cancelCommand, AimChannel/AimSession). Added only the
missing F3 reads (getAimCommandHistory/getAimSessionDetail/getAimAuditLogs/
getAimActionRuns) + detail types + INTENT_CATALOG. No shared component edited.
No npm build run.

## RE-VERIFY PASS 2026-06-10 (resume reconcile — trust disk not memory)
All 4 F3 pages re-read on disk + re-verified end-to-end:
- commands/page.tsx (491L), approvals/page.tsx (451L), capabilities/page.tsx (257L),
  sessions/[id]/page.tsx (503L). F3 shared bits live in _shared.tsx (NOT a separate
  _f3.tsx — that filename in the unit list above was never created; helpers were
  consolidated into _shared.tsx). _lib.ts F3 block (lines ~508-878) present + correct.
- `npx tsc --noEmit` -> EXIT 0, zero ai-manager errors.
- `npx next lint` on all 4 route files -> "No ESLint warnings or errors", EXIT 0.
- All 21 Icon names used verified present in components/Icon map (no blank glyphs).
- Component props verified: Badge{variant,dot,className}, Card{title,headContent,
  className}, Button{isBlack} — all match usage. lib/auth useMe/canWrite/isAdmin present.
- Nav (contstants/navigation.tsx) + _shared.tsx tab-rail both reference /commands,
  /approvals, /capabilities. Session Detail reached via deep-link from history rows.
- /sessions/[id]/play link is conditional on s.recording_url (always undefined while
  dormant) -> never-rendered forward-ref to add-on page #12, NOT owned by F3. Graceful.
VERDICT: F3 COMPLETE + VERIFIED. No edits needed beyond this state note.
