# ROUND 6 — FE + BE Deploy State (2026-06-20)

## Status: SHIPPED ✅

### Frontend (panel.famit.in, box 143.110.247.249)
- `npm run build` = EXIT 0, no TS errors (all 4 lanes clean).
- New BUILD_ID: **osCm5x7UxrATqG-CUU99m** (prev ZsE_YmL4rT80F9v6BcNLI).
- Shipped pre-built `.next` + app/ lib/ contstants/ components/ public/ via tar+scp.
- node_modules preserved; chowned deployuser.
- famit-panel restarted, `active`, listening 127.0.0.1:3001.
- VERIFY: local 3001 = 200; https://panel.famit.in/ = 200;
  new `_buildManifest.js` (osCm5...) = 200; OLD build = 404 → clean cutover.
- Commit: **2a55370** (16 files, +856/-215; navRegistry.ts + profile.ts new).
- gitleaks staged = 0; pushed e2741b5..2a55370 to origin/fix/realtime-voice-kernel-v2.

### Backend (voice box, famit@168.144.153.145)
- famit-agent service = **active** (ActiveEnter 2026-06-19 19:13:42 UTC).
- Live /opt/famit-agent/agent.py md5 = **e353b775** (mtime 19:09, backup
  agent.py.R6bak.20260620-000715 present) — the R6 backend lane DID deploy a NEWER
  agent.py. NOTE: this differs from the c33c03e2 in the task brief, which is the
  OLDER local repo snapshot (droplet_work/agent.py). Live = newer R6 build, healthy.
  Voice heart untouched by this FE deploy.

### Rollback
- Panel: `cp -r /opt/famit-panel/.next.R6UIbak.20260620-005046 /opt/famit-panel/.next`
  (rm current .next first) then `systemctl restart famit-panel`.
- Backend: agent.py backups on box (R6bak/R5VFbak/golden ROUND5).

### Needs founder
- Real call/WhatsApp smoke to confirm live voice brain (only the real flow is truth).
- Confirm panel UI lanes look right end-to-end in browser.
