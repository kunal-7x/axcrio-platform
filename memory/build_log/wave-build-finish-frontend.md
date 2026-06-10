# wave-build-finish-frontend — P5 sidebar IA regroup + new-module nav + LIVE deploy

Date: 2026-06-10. Owner: finish-frontend ship agent. Scope: surface the 9 new module
pages in the famit-panel sidebar, build green, deploy to the FORTRESS frontend box.
Result: **LIVE** on panel.famit.in. No git (orchestrator commits).

## What shipped
- Rewrote `famit-panel/contstants/navigation.tsx` into the canonical **8-section IA**
  from `MASTER_PLATFORM_ROADMAP.md §0a` (P5 = "the §7 sidebar regroup"). Presentation-
  only; **every previously-live href preserved verbatim** (regroup, not rebuild — no
  page orphaned, no route 404). Sections:
  - **A Command** — AI Manager (`/ai-manager`, manager+)
  - **B Grow** — Campaigns, Ad Automation (`/ads`, manager+), Funnels (`/funnels`), Form Builder (`/forms`)
  - **C Sell** — Leads, CRM (`/crm`)
  - **D Engage** — Run, Call Logs, Callbacks, WhatsApp (mgr+), Customer Support (`/support`), Booking (`/booking`)
  - **E Automate** — Workflows (`/workflows`), Webhooks (mgr+)
  - **F Money** — Payments (`/payments`, mgr+), Billing Overview/Vendors/Cost Explorer/Audit/Plan
  - **G Intelligence** — Analytics
  - **H Foundation** — Do-Not-Call (`/suppression`), Vendors (`/vendors`, admin)
  - Dashboard stays a top-level link; **Create Studio** preserved as the coming-soon group; Settings stays in `navigationUser`.
- 9 new module routes now reachable from the rail: ai-manager, ads, funnels, forms,
  crm, support, booking, workflows, payments. (The pages were built prior waves but
  intentionally did NOT touch nav — that was the ship step's job; now done.)

## Role-gating (pages self-gate writes via canWrite=admin|manager; nav read stays broad)
- `manager` nav gate on spend/command-sensitive entries: AI Manager, Ad Automation,
  Payments (+ pre-existing WhatsApp, Webhooks).
- `admin` on Vendors (admin page). No nav gate on crm/support/booking/forms/funnels/workflows.

## Build / verify (un-sandboxed)
- `npm install --legacy-peer-deps` → up to date (React 19 ⇒ legacy-peer-deps REQUIRED).
- `npm run build` → **✓ Compiled successfully**, EXIT 0. All 10 new routes present
  (`/ads /ai-manager /booking /crm /crm/[id] /forms /forms/[id] /funnels /payments /support /workflows`).
- `npx tsc --noEmit` → EXIT 0 clean.
- No page needed exclusion — all 9 compiled as a set (the per-page isolated-distDir
  builds in prior brain notes did NOT prove the set; the full build does).
- Verified: all 26 nav hrefs map to a real `app/.../page.tsx`; all 11 nav icons exist
  in `components/Icon/index.tsx`.

## KEY LEARNING — nav ≠ build
Next.js compiles every `app/*/page.tsx` from the FILESYSTEM; `navigation.tsx` only
drives the sidebar. So editing nav cannot break the build and cannot exclude a page.
To truly stage-out a broken page you rename its dir to `_<name>` (private folder =
unrouted) + omit from nav — relative `./api`/`./_lib` imports stay intact. Moving a
sidebar link can NEVER 404 a live route (routes come from folders). The only real
hazard is fat-fingering an existing href → so hrefs were copied, not retyped, and
grep-verified after.

## Deploy (FORTRESS recipe — HANDOVER_REPORT.md §8)
Box: `root@143.110.247.249` (famit-panel-2, born-hardened), app `/opt/famit-panel`,
systemd `famit-panel` runs `next start -H 127.0.0.1 -p 3001`, nginx + Cloudflare front.
1. **Backup first:** `cp -a /opt/famit-panel /opt/famit-panel.bak.20260610-013243` (1.1G, full).
   ROLLBACK = restore that dir + `systemctl restart famit-panel`.
2. `tar czf fp.tgz --exclude=node_modules --exclude=.next --exclude=.git -C famit-panel .`
   ⚠ tar `-f` with a `C:/...` path is parsed as a remote host (colon) → use a RELATIVE
   output path and run from the caps dir.
3. `scp fp.tgz root@…:/tmp/` → `cd /opt/famit-panel && tar xzf /tmp/fp.tgz` (overlay on
   existing node_modules/.next) → `chown -R deployuser:deployuser`.
4. As deployuser: `npm install --legacy-peer-deps && npm run build` → Compiled OK,
   new BUILD_ID `oxHHUWlj3yxTiLzP_FqlP`.
5. `systemctl restart famit-panel` → active; `curl 127.0.0.1:3001/login` = 200.

## Live verification (through Cloudflare)
All 200: `/login /  /ai-manager /ads /funnels /forms /crm /support /booking /workflows
/payments /analytics`. `/login` `<title>Famit</title>`, real Next chunks served,
`Server: cloudflare`. **Status: LIVE.**

## Post-ship refinements (2nd deploy, BUILD on box OK, restart OK)
- **Dashboard moved INTO the Command section** (was a top-level link). Reason: Command's
  only other child (AI Manager) is `manager`-gated, so for a read-only AGENT the Sidebar
  would hide the whole Command section. Putting Dashboard under Command (where §0a places
  it) keeps the section ALWAYS visible and is more faithful to the IA. Re-verified build
  EXIT 0 + tsc clean + all public routes 200 after.
- **ALL 24 nav routes verified 200** through Cloudflare (the 9 new + the moved-but-
  unchanged: campaigns, leads, run, calls, callbacks, whatsapp, webhooks, billing/*,
  suppression, vendors, settings) — not just the new ones.

## Known dead routes (PRE-EXISTING, out of scope — flag for a future prune wave)
The original Next.js template's leftover routes are still compiled + publicly reachable
but absent from nav (Famit-irrelevant): `/products/* /shop/* /income/* /customers/*
/promote /explore-creators /affiliate-center /upgrade-to-pro /messages /notifications`.
They predate this wave; NOT touched here. A future wave should delete those `app/` dirs.

## State
- Backups on box (rollback path, restore + `systemctl restart famit-panel`):
  `/opt/famit-panel.bak.20260610-013243` (pre-1st-deploy) and
  `/opt/famit-panel.bak.20260610-015035` (pre-dashboard-move).
- Local + remote `fp.tgz` cleaned. No git (orchestrator owns commits).
