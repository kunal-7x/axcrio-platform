# Wave Build — UI Overhaul (Core_2 reskin → Inter Display + clean headings)

Durable build report for the UI-overhaul wave (founder rejected from-scratch UI;
port the `core-2-dashboard-builder-react` kit, Inter Display app-wide, no
heading subtitles). Append per unit; never delete.

---

## UNIT W3 — BUILD GREEN + DEPLOY (2026-06-11) — SHIPPED ✅

**Scope:** verify the whole panel compiles after the shell (W1) + page-group
ports, then deploy LIVE to the FORTRESS frontend box and verify the font/heading
change is visible in served HTML.

### 1. Build (local) — EXIT 0
- `npm install --legacy-peer-deps` → up to date (523 pkgs). Node v22.11.0 local.
- `npm run build` → **✓ Compiled successfully, EXIT_CODE=0**. No PageHeader /
  Gilroy / missing-component errors to fix — the W1 shell port left the tree
  green. All routes rendered (49 entries in the route table).
- Font source confirmed in tree before deploy:
  - `app/layout.tsx`: only `interDisplay` localFont on `<body>` (5 weights
    300–700), `${interDisplay.variable}` + `font-inter` className; NO gilroy.
  - `app/globals.css:204` `--font-inter: var(--font-inter-display)`;
    `:285` html font-family leads with `var(--font-inter-display)`. No `--font-gilroy`.

### 2. Deploy (FORTRESS recipe) → root@143.110.247.249:/opt/famit-panel
- Box: node v20.20.2 / npm 10.8.2, service `famit-panel.service` (Type=simple,
  User=deployuser, `next start -H 127.0.0.1 -p 3001`, nginx-fronted, hardened
  unit). SSH key `C:\Users\kunal\.ssh\do-blr-test\id_ed25519`.
- **Tarball:** `tar` excl `node_modules/.next/.git/.env.local/famit-panel.tgz/build.log/*.tsbuildinfo/*.DS_Store`
  → 22M (the bulk = the 5 Inter Display woff2 in `public/fonts`). NOTE: the source
  tree carried two stray bloat files (`famit-panel.tgz` 21M, `build.log`) — excluded.
- **scp** → `/tmp/famit-panel-new.tar.gz` (SCP_EXIT=0).
- **BACKUP FIRST:** `cp -a /opt/famit-panel /opt/famit-panel.bak.20260611-014711` (1.1G full copy). Rollback target.
- **Extract:** removed stale source dirs (app/components/templates/hooks/lib/mocks/
  types/contstants/public + config files) so deletions propagate, KEEPING
  `node_modules/.next/.env.local`; then `tar -xzf` new code over it. `.env.local`
  preserved (box value `NEXT_PUBLIC_API_BASE=/api`, identical to local). `chown -R deployuser:deployuser`.
- **As deployuser:** `npm install --legacy-peer-deps` OK → `npm run build` →
  **✓ Compiled successfully, BUILD_EXIT=0**.
- `systemctl restart famit-panel` → active, listening 127.0.0.1:3001.

### 3. VERIFY
- **localhost:3001** — all 25 app routes 200 (/, /campaigns, /leads, /run, /calls,
  /billing/overview, /crm, /forms, /funnels, /booking, /ads, /ai-manager,
  /payments, /support, /workflows, /super-admin, /suppression, /billing/explorer,
  /settings, /analytics, /whatsapp, /vendors, /callbacks, /webhooks, /login).
- **https://panel.famit.in** — 17 spot-checked public routes all 200.
- **Font proof (served HTML/CSS):** `/login` body class = `__variable_10e869 ...
  font-inter ...` — ONE font variable (interDisplay), NO Gilroy anywhere in HTML.
  Served CSS `/_next/static/css/1a82ce307b898c9c.css` references exactly **5
  woff2** (the 5 Inter Display weights) and **ZERO `gilroy`** strings. Font change
  is definitively LIVE and visible.
- **Heading proof (served HTML):** `/` uses `text-h4`/`text-h5` title tokens and
  has NO `page-head-sub` / `page-head-eyebrow` / `signal-glyph` classes — clean
  single-line titles, no subtitle/eyebrow/accent clutter.
- Cleanup: removed `/tmp/famit-panel-new.tar.gz` on box + local tarballs. Disk 39% (29G free).

### Rollback (if ever needed)
```
ssh root@143.110.247.249
systemctl stop famit-panel
rm -rf /opt/famit-panel && mv /opt/famit-panel.bak.20260611-014711 /opt/famit-panel
systemctl start famit-panel
```

### Notes / open items for later waves (NOT blocking — build is green & live)
- The nav DATA was renamed in W1 (Suppression→Do-Not-Call, Cost Explorer→Spending,
  Test Console→Try it, etc.) but the **route folders were NOT moved** — live routes
  are still `/suppression`, `/billing/explorer`, `/billing/plan`, and the AI-Manager
  sub-routes (`/ai-manager/{overview,approvals,capabilities,setup,test,users,...}`)
  still exist. The W3 task referenced renamed `do-not-call`/`spending`/`team` URLs;
  those renames are label-only so far. If the founder wants the URLs themselves
  renamed, that's a follow-up unit (move folders + add redirects from old paths).
- Stray `famit-panel.tgz` (21M) + `build.log` still sit in the local source tree —
  consider `.gitignore`/removing them.
