# FRONTEND DEPLOY — 3-page fixes (super-admin / workflows / whatsapp) — 2026-06-11

Scope: build the famit-panel frontend (3 page fixes already in tree on branch
feat/premium-ui), then FORTRESS-deploy LIVE. Frontend-only; no backend change.

## BUILD (local, gate before deploy)
- `npm install --legacy-peer-deps` -> "up to date, 523 packages" (deps satisfied).
- `npm run build` -> EXIT 0. 50+ routes compiled incl /super-admin*, /workflows,
  /whatsapp, /campaigns. Node v22.11.0, next 15.2.0, react 19.

## DEPLOY (FORTRESS recipe)
Box `root@143.110.247.249`, `/opt/famit-panel` (deployuser; systemd `famit-panel`
runs `next start -H 127.0.0.1 -p 3001`). nginx `/`->3001, `/api/`->backend
(VPC 10.122.0.4:8209 caller.py + :8310). SSH key do-blr-test/id_ed25519.
- BASELINE captured pre-deploy: MainPID 103050 (start 12:10:55 UTC); public /login /
  /super-admin /workflows /whatsapp /campaigns all 200; backend /api/{campaigns,
  leads,me} 401 unauth / 200 auth (X-Auth FamitCall2026); disk 44%.
- BACKUP: `cp -a /opt/famit-panel /opt/famit-panel.bak.1781180692` (2.3G). ROLLBACK =
  `rm -rf /opt/famit-panel && mv /opt/famit-panel.bak.1781180692 /opt/famit-panel &&
  systemctl restart famit-panel` (then confirm fresh pid start time).
- TAR local source excl node_modules/.next/.git/.env.local/*.tsbuildinfo/*.md AND
  stray bloat (famit-panel.tgz 21M, build.log, .wf-backup-workflows from another
  active session) -> 22M tgz. scp to /tmp; md5 verified match
  255bcdbdfbe50a76d16e64fcc7e01450. Extract over /opt/famit-panel (preserves
  node_modules/.next/.env.local NEXT_PUBLIC_API_BASE=/api) -> chown deployuser.
- BUILD ON BOX (deployuser): `npm install --legacy-peer-deps` (no-op, deps current)
  + `npm run build` -> "Compiled successfully", 53 routes, BUILD_ID
  Jorw6rg8FJDVtaPLKXE6F written 12:38:23 UTC.
- RESTART: famit-panel MainPID 103050 -> 105480 (start 12:42:11 UTC, AFTER build).
  Gotcha avoided: confirmed new pid start time > build time + served HTML embeds
  BUILD_ID Jorw6rg8FJDVtaPLKXE6F (not stale .next).

## REGRESSION GATE — PASS
- Frontend routes 200 on all three paths (next:3001 direct, nginx Host header, and
  real public https://panel.famit.in via Cloudflare): /login / /super-admin
  /workflows /whatsapp /campaigns. (whatsapp/campaigns flicked 000 once = transient
  client curl timeout on bigger bundles; 200 on retry w/ longer timeout + UA.)
- Backend unchanged + healthy through proxy: /api/{campaigns,leads,me} 401 unauth /
  200 auth. No 5xx. caller.py (backend) active via VPC proxy.
- /workflows + /whatsapp SSR HTML render real content (workflow/canvas; WhatsApp/
  Template/Message). /super-admin is client-rendered post-auth (200, clean logs).
- panel journal since restart: zero error/exception. famit-panel + nginx active.
- Cleaned /tmp tarball + sentinels on box.

## STATUS: LIVE on https://panel.famit.in with the new build.
