# ROUND 5 — FRONTEND SHIP STATE (2026-06-19)

## STATUS: DEPLOYED LIVE ✅ (PANEL BOX ONLY — voice box untouched)

- **Box:** `famit-panel-2` `root@143.110.247.249` (PANEL only). Service `famit-panel` = **active**.
- **Live BUILD_ID:** `5QSKx7TnwhQTRGnBthPCl` (served on http://127.0.0.1:3001 and https://panel.famit.in)
- **Commit:** `dfce83c` on `fix/realtime-voice-kernel-v2` — "feat(panel): Round-5 frontend wireup"
- **Build:** local `npm run build` EXIT 0 (no TS errors). gitleaks staged = 0.
- **Deploy:** pre-built `.next` (images.unoptimized=true → runs on Linux; NO on-box build). Extracted over `/opt/famit-panel`, node_modules preserved, chown deployuser. (No `.git` in deploy dir — expected.)

## Verify results
- `systemctl is-active famit-panel` → active
- `/opt/famit-panel/.next/BUILD_ID` → 5QSKx7TnwhQTRGnBthPCl (= local)
- http://127.0.0.1:3001/ → **200** (served HTML contains new BUILD_ID)
- https://panel.famit.in/ → **200**

## What shipped (24 files, +1059/-163)
Dashboard data wiring (`app/page.tsx`, GlobalFilters, lib/queries/api/report), CRM (`app/crm/page.tsx`, client.ts), super-admin provider logos (new `components/ProviderLogo/`, vendors/api-keys pages), AI-Manager, communication/whatsapp previews, creative/brand, analytics, calls, payments, integrations.

## Still DEPENDS ON BACKEND (UI renders; data needs API)
- Dashboard **temperature / hot-leads** data
- CRM **name** field, **sort_by** params
- **brand-kit**, **whatsapp**, **add-number** endpoints

## ROLLBACK (one shot)
```
ssh -i ~/.ssh/do-blr-test/id_ed25519 root@143.110.247.249 \
 'cd /opt/famit-panel && rm -rf .next && cp -a .next.R5UIbak.20260619-143037 .next && systemctl restart famit-panel'
```
Backup on box: `/opt/famit-panel/.next.R5UIbak.20260619-143037`
