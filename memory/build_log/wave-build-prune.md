# Wave: Frontend Route Prune

**Date:** 2026-06-10
**Box:** famit-panel-2 (root@143.110.247.249) — NOT the backend box
**Scope:** Remove template-leftover `app/` route dirs that are absent from sidebar nav
**Result:** BUILD EXIT 0 + tsc EXIT 0 + panel.famit.in 200 + deleted routes 404

---

## Routes pruned (app/ dirs deleted)

| Route | app/ dir deleted |
|-------|-----------------|
| /products/* | `app/products/` (6 sub-pages: /, drafts, comments, released, scheduled, new) |
| /shop/* | `app/shop/` (2 sub-pages: /, details) |
| /income/* | `app/income/` (4 sub-pages: earning, payouts, refunds, refunds/details, statements) |
| /customers/* | `app/customers/` (3 sub-pages: /, customer-list, customer-list/details) |
| /promote | `app/promote/` |
| /explore-creators | `app/explore-creators/` |
| /affiliate-center | `app/affiliate-center/` |
| /upgrade-to-pro | `app/upgrade-to-pro/` |
| /messages | `app/messages/` |
| /notifications | `app/notifications/` |

**Total: 10 top-level route dirs, ~21 page.tsx files removed.**

---

## What was NOT deleted (intentionally)

- `templates/` subdirs for the above routes — dead code but type-clean; removing them risks
  shared-component cascade. Left in place per advisor review.
- `mocks/` files (messages, promote, creators, affiliate-center) — dead code, compile-clean.
- `components/Header/Notifications`, `components/Header/Messages`, `components/NewCustomers`,
  `components/PopularProducts` — verified NOT imported by any kept page or by the live Header.
- `contstants/navigation.tsx` — already clean (none of the 10 routes appear in sidebar nav).

---

## Verification

- Local: `npm install --legacy-peer-deps && npm run build` → EXIT 0
- Local: `npx tsc --noEmit` → EXIT 0
- Box backup: `/opt/famit-panel.bak-prune-20260610-112345`
- Deploy: rsync (via WSL rsync 3.2.7), npm install --production, systemctl restart
- Service: `systemctl is-active famit-panel` → `active`
- Local curl: `/ = 200 | /products = 404 | /campaigns = 200`
- Public: `panel.famit.in/ = 200 | panel.famit.in/products = 404`
- Sidebar nav: all 8 sections intact (Command/Grow/Sell/Engage/Automate/Money/Intelligence/Foundation)

---

## Rollback

```bash
ssh -i C:\Users\kunal\.ssh\do-blr-test\id_ed25519 root@143.110.247.249
cp -a /opt/famit-panel.bak-prune-20260610-112345 /opt/famit-panel
systemctl restart famit-panel
```
