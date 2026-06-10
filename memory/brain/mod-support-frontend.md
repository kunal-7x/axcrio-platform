# mod-support-frontend — Customer Support page (app/support)

Built: 2026-06-10. Frontend-only page for the `support` module, in `famit-panel`.

## Files (the ONLY two created; no shared files touched)
- `famit-panel/app/support/page.tsx` — premium page: PageHeader (Engage eyebrow),
  KPI cards (Open/Resolution Rate/AI Handled/Needs Attention — all from REAL ticket
  fields), Channel-Mix + Ticket-Volume activity strip, status-filterable ticket table,
  and a thread/detail modal with AI summary, escalation banner, message bubbles, a
  human-reply composer, and action buttons (AI draft / claim / escalate / resolve).
- `famit-panel/app/support/api.ts` — COLOCATED fetch layer (lib/api.ts is shared &
  off-limits; its token helpers are NOT exported, so getToken/authHeaders/handle401
  are re-implemented here). Types mirror support/schema.sql columns exactly.

## Hard-won specifics (reuse for the other 8 dormant module pages)
- API path: `${BASE}/support/...` where BASE=`/api`; panel reverse-proxy strips /api
  → backend `/support` (router mounted at prefix /support, deferred this wave).
- DORMANCY GATE: gate the page on `getSupportHealth()` returning non-null (fetch
  SUCCESS), NOT a status field — health returns {pg_available, schema_ready, ...} with
  no top-level status:"ok". Health returns null on ANY 404/network failure → render a
  premium ComingSoon state (state-block / state-glyph), never a crash/raw error. The
  router is NOT mounted yet so /api/support/* 404s today — handled gracefully.
- Writes need manager+: read role from localStorage `famit_me` (is_admin→admin) via
  getCachedRole(); canWrite()=admin|manager. Mutations also catch 403→"no permission"
  and 404/503→"not configured yet" via a typed SupportActionError.
- Reused panel components: Layout, PageHeader, Card (headContent slot for filter pills),
  KpiCard, Sparkline, Badge, Icon. CSS: surface, rise-in, data-table is-clickable,
  state-block/glyph, eyebrow, skeleton, kpi-glyph, td-num, scrollbar-thin. Detail-modal
  pattern lifted from app/calls/page.tsx (call→ticket, transcript turns→support_messages).
  Built page-local Status/Priority/Sentiment badge mappers (lib/badges.tsx is call-specific).
- Confirmed-valid Icon names used: chat, chat-think, envelope, feather, info, check-circle,
  bell, close, chart, filters, emoji, desktop. (Unknown icon names render blank.)

## Verification
- `npx tsc --noEmit` → exit 0 (clean).
- `next build` into an isolated distDir (.next-verify) → "Compiled successfully",
  Route /support 8.68 kB / 214 kB First Load. (Plain `next build` EPERM-locks on
  .next/trace because OTHER concurrent agent sessions hold a dev server — do NOT kill
  their node procs; build to a temp distDir + restore next.config.ts instead.)

## NOT done (out of scope — ship step owns these)
- Nav entry in components/Sidebar (navigation), the real `next build`, and deploy.
