# frontend-ship-nav-deploy — wiring new pages into the panel + deploying

Durable learnings from the P5 ship wave (2026-06-10). Reuse for any future
famit-panel nav change or frontend deploy.

## The IA is fixed: MASTER_PLATFORM_ROADMAP.md §0a (8 collapsible sections)
A=Command B=Grow C=Sell D=Engage E=Automate F=Money G=Intelligence H=Foundation.
`navigation.tsx` already implements this. Each section is `{title, icon, list:[...]}`
(no parent `href`). Dashboard = top-level link; Create Studio = coming-soon group
(children have `comingSoon:true`, NOT `href` → render dimmed "Soon", never 404);
Settings lives in `navigationUser`, not the main rail.

## nav ≠ build (the load-bearing fact)
Next.js routes come from the `app/` FILESYSTEM, not the sidebar. Editing
`contstants/navigation.tsx`:
- CANNOT break `npm run build` and CANNOT 404 a live route.
- To genuinely stage-out a non-compiling page: rename its dir `app/x` → `app/_x`
  (underscore = private/unrouted) AND drop it from nav. Relative `./api`/`./_lib`
  imports survive the rename.
- Only real risk = mistyping an existing href. So COPY hrefs, never retype; after
  editing, grep every `href:` and confirm each maps to a real `app/.../page.tsx`.

## Role-gating convention
Module PAGES self-gate writes (`canWrite = admin|manager` from `lib/auth`), so nav
READ stays broad. Add `roles:"manager"` only on spend/command-sensitive nav entries
(ai-manager, ads, payments, whatsapp, webhooks); `roles:"admin"` on admin-only
(vendors). The Sidebar hides a group whose children are all role-filtered out.
ai-manager's internal `isAdmin` checks do NOT mean the nav entry must be admin-only.

## Icons are a CLOSED set
Valid icon names = the keys in `components/Icon/index.tsx` (~70). An unknown name
renders BLANK (no error). Used safely for sections: grid, promote, usd-circle, chat,
layers, wallet, chart, edit, profile, dashboard, edit-profile. Validate every
`icon:` against that file before shipping.

## Verify before deploy
`npm install --legacy-peer-deps` (React 19 ⇒ REQUIRED) → `npm run build` must print
"✓ Compiled successfully" EXIT 0 → `npx tsc --noEmit` EXIT 0. The full build (not a
per-page isolated-distDir build) is what proves the page SET compiles together.

## Deploy recipe (FORTRESS) — box root@143.110.247.249, app /opt/famit-panel
systemd unit `famit-panel` = `next start -H 127.0.0.1 -p 3001`; nginx + Cloudflare front.
SSH key: `C:\Users\kunal\.ssh\do-blr-test\id_ed25519` (root key-only; deployuser too).
1. BACKUP FIRST: `cp -a /opt/famit-panel /opt/famit-panel.bak.<ts>`. Rollback = restore
   that dir + `systemctl restart famit-panel`.
2. `tar czf fp.tgz --exclude=node_modules --exclude=.next --exclude=.git -C famit-panel .`
   — ⚠ use a RELATIVE output filename; `tar -f C:/...` treats the colon as a remote host.
3. scp → `/tmp/fp.tgz`; on box `cd /opt/famit-panel && tar xzf /tmp/fp.tgz` (overlays the
   excluded node_modules/.next from the prior deploy); `chown -R deployuser:deployuser`.
4. `sudo -u deployuser bash -lc 'cd /opt/famit-panel && npm install --legacy-peer-deps && npm run build'`.
5. `systemctl restart famit-panel`; `systemctl is-active famit-panel`;
   `curl 127.0.0.1:3001/login` → 200.
6. Public verify (Cloudflare): `curl -o /dev/null -w '%{http_code}' https://panel.famit.in/<route>`
   for /login + each new page. `<title>Famit</title>` + `_next/static` chunks = real app live.

## Box facts (2026-06-10)
node v20.20.2, npm 10.8.2, 39G free disk, ~1.4G mem free + 2G swap (build fits).
Last good deploy BUILD_ID oxHHUWlj3yxTiLzP_FqlP. Backup `/opt/famit-panel.bak.20260610-013243`.
