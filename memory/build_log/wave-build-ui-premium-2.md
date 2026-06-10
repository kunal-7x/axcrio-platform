# WAVE — UI PREMIUM 2 (FRONTEND-ENG) — ✅ DEPLOYED LIVE 2026-06-10

Founder asks (5 fixes) on the live panel (panel.famit.in). NON-BREAKING:
restyle/structure only, NO API/route/logic change. No git (orchestrator commits).
Built on the existing "Signal" design system (already live). Core_2-Capsy-Dashboard
IS this same template (`C:\Users\kunal\Desktop\Core_2-Capsy-Dashboard\extracted\
core-2-dashboard-builder-react`), so the design language was already shared — "reuse
Core_2" meant cohesion + the template's own collapsible Dropdown mechanism, NOT
importing its marketing/3D bits (the prior premium-ui wave already rejected those).

## STATUS: ✅ LIVE on https://panel.famit.in (verified end-to-end through nginx).
Rollback point (box): `/opt/famit-panel.bak.1781052937` (cp -a before deploy).
Rollback = `rm -rf /opt/famit-panel && mv /opt/famit-panel.bak.1781052937
/opt/famit-panel && systemctl restart famit-panel`.

## THE 5 FIXES (all done + verified in the LIVE served HTML)
1. **Collapsible sidebar GROUPS for the WHOLE rail + a "Create Studio" COMING-SOON
   group.** The flat ~12-item list is now organized expandable groups reusing the
   EXISTING Sidebar/Dropdown `list:` mechanism (the same one Billing always used):
   - Dashboard (standalone link, top)
   - **Outreach** → Campaigns, Leads, Run a Campaign, Callbacks
   - **Intelligence** → Call Logs, Analytics
   - **Compliance** → Do-Not-Call
   - **Channels** → WhatsApp, Webhooks  (children `roles:"manager"`)
   - **Billing** → Overview, Vendors, Cost Explorer, Audit, Plan & Ledger (unchanged)
   - **Create Studio** (COMING SOON) → Script Builder, Voice Studio, Flow Designer,
     A/B Lab — rendered DISABLED (dimmed `<div>` + brand-blue "Soon" pill, NEVER a
     `<Link>`, so they can't 404). Pages intentionally NOT built.
   - **Admin** (`roles:"admin"`) → Vendors
   Every existing route still works; nothing removed.
2. **Removed the dark-mode toggle from the top navbar.** Deleted `<ThemeButton>` +
   its import from `components/Header/index.tsx`. The toggle SURVIVES in the sidebar
   footer (and the floating one when sidebar is hidden) → theme switching still works.
   LIVE check: themeTogglePill count in served `/` HTML = 1 (was 2).
3. **Removed the vertical "dividing line" between sidebar and content.** There was NO
   literal border-right/border-left in the shell (body, Sidebar, Header are all
   `bg-b-surface1` — same color, no seam). ROOT CAUSE (inferred, advisor-confirmed):
   the sidebar scroll area used `scrollbar-track-b-surface2` — surface2 ≠ surface1,
   and with the long nav list overflowing, that lighter track sat flush at the
   sidebar's right edge and read as a vertical line. FIX: `scrollbar-track-transparent`
   + thinner thumb (`scrollbar-thin scrollbar-thumb-t-tertiary/30`). ⚠️ This root
   cause is INFERRED (no pixel render in harness); if a line persists, next step is a
   screenshot to identify it. Grouping (Fix 1) also reduces overflow so the line is
   gone in collapsed states regardless.
4. **Removed the DUPLICATE page heading in the top navbar.** The page title showed
   twice — once as a signal-glyph + `text-sub-title-1` block in `Header`, once as the
   big `PageHeader` masthead on the page. Removed the Header title block; the `title`
   prop is still accepted (Layout passes it) but no longer rendered. Added `ml-auto`
   to the Header actions container so "Run a Campaign"/User stay right-aligned (the
   removed title block's `mr-auto` was what right-aligned them). LIVE check:
   `text-sub-title-1` in served `/` HTML = 0.
5. **Premium polish (Core_2 token language).** The highest-leverage premium uplift
   here is the SHELL regrouping itself (flat rail → organized collapsible console) +
   the brand-blue `.nav-soon` roadmap pill + a cleaner thin/transparent scrollbar —
   all on top of the existing rich "Signal" system (wordmark, signal-glyph, page
   mastheads, KPI/surface/data-table/pill token language already live). Deliberately
   did NOT churn the 19 content pages (can't eyeball pixels in this harness, and the
   pages already wear the Signal language) — that would be staged-for-review per this
   repo's established discipline, not blind-shipped on the live earner. If the founder
   wants more per-page visual depth, that's the bounded next step.

## FILES TOUCHED (all in caps/famit-panel; restyle/structure only)
- `contstants/navigation.tsx` — regrouped flat pages into collapsible `list:` groups;
  added Create Studio coming-soon group; added per-CHILD `roles` + `comingSoon` fields.
- `components/Sidebar/index.tsx` — new `resolveNav()` filters group CHILDREN by role
  AND drops a group left with no visible children (so an agent never sees a manager
  link, a vendor never sees the admin Vendors link, even inside a group). Scrollbar
  track → transparent (Fix 3). Removed now-dead `.section` overline render.
- `components/Sidebar/Dropdown/index.tsx` — children support `comingSoon` (dimmed
  non-link row + Soon pill) and `roles`; active-detection changed from
  `pathname.includes(href)` to exact/segment-boundary match (so `/billing/vendors`
  no longer co-expands the Admin group's `/vendors` child — prefix-collision fix).
- `components/Header/index.tsx` — removed `<ThemeButton>` + import (Fix 2); removed
  the title block (Fix 4); `ml-auto` on actions.
- `app/globals.css` — added `.nav-soon` pill class (brand-blue, tiny, uppercase) in
  the Signal `@layer components` block.

## ADVISOR-CAUGHT LANDMINES (all honored)
- Dropdown rendered ALL list children unconditionally → would leak role-gated links
  inside groups. Fixed via per-child `roles` + `resolveNav` empty-group drop.
- Coming-soon children CANNOT be NavLinks (always `<Link href>` → 404). Rendered as
  disabled `<div>` + Soon pill.
- Dashboard kept STANDALONE (not a list child) — `pathname.includes("/")` is always
  true, would mis-activate.
- Removing the Header title left-shifts actions → added `ml-auto`.
- `/billing/vendors` includes `/vendors` → segment-boundary active match.

## VERIFY (what was construction-verified)
- `npx tsc --noEmit` EXIT 0 (2 type errors found + fixed: NavLink requires
  `href:string`, narrowed the value objects in Sidebar + Dropdown).
- REAL un-sandboxed `npm run build` EXIT 0 (checked PIPESTATUS, not a sandbox false
  exit-0) — all 46 routes compiled, 0 errors. Repeated after the active-match fix.
- Local `next start` + curl 10 app routes → all 200; served-HTML grep confirmed all
  4 fixes BEFORE deploy (groups + Soon pill present; themeTogglePill=1; header
  title=0; scrollbar-track-transparent=1).
- On box: source greps confirmed all 4 fixes landed; build = BUILD_DONE_OK, fresh
  BUILD_ID.
- ⚠️ NOT seen: actual pixels / dark-mode rendering (no browser in harness). Dark mode
  is token-based (b-/t-/s- + the Signal layer), reasoned-safe; the Soon pill uses
  `primary-01` which is theme-independent.

## DEPLOY (FORTRESS recipe) — LIVE + verified
Box `root@143.110.247.249`, `/opt/famit-panel` (deployuser, `next start -H 127.0.0.1
-p 3001`, systemd `famit-panel`). nginx `/`→3001, `/api/`→backend.
- BACKUP: `cp -a /opt/famit-panel /opt/famit-panel.bak.1781052937` (rollback point).
- tar local famit-panel (excl node_modules/.next/.git/.env.local/STATE+SPEC docs) →
  scp /tmp → extract into /opt/famit-panel (preserved `.env.local`
  NEXT_PUBLIC_API_BASE=/api) → chown deployuser → as deployuser `npm install
  --legacy-peer-deps && npm run build` (BUILD_DONE_OK) → `systemctl restart
  famit-panel`.
- ⚠️ GOTCHA HIT: the FIRST `systemctl restart` (issued while the build was still
  running / mangled by PowerShell quoting) did NOT take — the OLD next-server (pid
  74156, started 18:06) kept serving the OLD `.next`, so served HTML still showed the
  old shell despite correct source + fresh BUILD_ID. A genuine second restart spun a
  NEW process (pid 76936, 19:40) that serves the new build. LESSON: after a box
  build, CONFIRM the running next-server's START TIME is AFTER the build, and grep the
  SERVED HTML for the change — don't trust "systemctl restart returned" or a fresh
  BUILD_ID alone.
- VERIFIED LIVE (public https through nginx): /login,/,/campaigns,/calls,
  /billing/vendors,/run = 200; served `/` HTML → Outreach/Intelligence/Create
  Studio/Soon present, themeTogglePill=1, header title=0, scrollbar-track-transparent
  =1; authed `/api/stats`=200, unauthed=401 (backend wiring intact, non-breaking).

## ROLLBACK
`rm -rf /opt/famit-panel && mv /opt/famit-panel.bak.1781052937 /opt/famit-panel &&
systemctl restart famit-panel` (then confirm the running pid's start time is fresh).
