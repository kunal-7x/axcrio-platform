# FIX-CONTROL-2 — "vendor STILL sees locked/hidden pages" (LIVE founder-flow reproduction)

**Date:** 2026-06-11. **Method:** reproduced the WHOLE chain a real vendor token
hits — NOT an API stub, NOT the admin/legacy token (which resolves to admin =
everything ON). Backend box `famit@168.144.153.145` (`127.0.0.1:8209`,
`CONTROL_ENABLED=1`, `FIREWALL_ENABLED=true`), deployed frontend box
`root@143.110.247.249:/opt/famit-panel`.

---

## TL;DR — the one broken link (unchanged from fix-control-enforce.md, now PROVEN live)

The **DEPLOYED vendor frontend never reads a `feature_key` for any nav item or
page**, so the entitlement map it already polls is resolved against `undefined`,
which `lib/entitlements.ts:202-204 modeOfIn` hard-codes to `"ON"`. The Super Admin
toggle WRITES correctly, the backend RESOLVES + 404/402s correctly for a real
vendor, but the vendor's sidebar still lists the page and the page chrome still
renders — only the in-page `/api/*` data fetch 404/402s (often a silent empty
state). To the founder that looks like "control isn't working."

- (1) WRITE PERSIST + version bump → ✅ WORKS (proven on a real vendor)
- (3) BACKEND MIDDLEWARE 404/402 → ✅ WORKS (proven on a real vendor token)
- (2) DEPLOYED FRONTEND READ+APPLY → ❌ **BROKEN — `feature_key` wired to nothing in the live bundle**

---

## PROOF 1 — full toggle→persist→vendor-read→enforce chain (REAL vendor token)

Vendor `21d0a13603da` (axcrio, `is_admin=false`). Token minted exactly as
`caller.py:511 _make_token` does (`tenant_id.hmac(tenant_id, var/secret)`).
Admin write = the EXACT endpoint the UI toggle hits
(`PUT /admin/vendors/{id}/entitlements/grow.campaigns`, `mode=hidden`, form body —
matches `lib/api.ts:1026 setVendorEntitlement` + `super-admin/vendors/[id]/page.tsx:163`).

| Step | Call (as vendor unless noted) | Result |
|---|---|---|
| baseline | `/me/entitlements` `grow.campaigns` | **`on`**, version 28 |
| baseline | `GET /campaigns` | **200** |
| write (legacy pw) | `PUT /admin/.../grow.campaigns` `X-Auth: FamitCall2026` | **403** (legacy correctly excluded from /admin/*) |
| write (admin hmac) | same, admin token | **200** `{ok:true, before:null, after:"hidden", version:29}` |
| after | `/me/entitlements` `grow.campaigns` | **`hidden`**, version 29 |
| after | `GET /campaigns` | **404** (HIDE enforced for the vendor) |
| restore | `DELETE /admin/.../grow.campaigns` | **200**, version 30 |
| restore | `/me/entitlements` / `GET /campaigns` | **`on`** / **200** |

→ Write persists, version bumps, vendor's own `/me/entitlements` flips, and the
path→feature_key middleware 404s the vendor's data route. **Backend is correct.**

## PROOF 2 — the deployed frontend bundle is INERT

On the live box `root@143.110.247.249:/opt/famit-panel`:
- `grep -c feature_key contstants/navigation.tsx` → **0** (no nav entry carries a key)
- `grep -rl EntitlementGuard app/` → **(none)** — `components/EntitlementGuard`
  ships but is imported by ZERO pages → no route-level HIDE redirect / LOCK overlay
- served chunks contain `feature_key` only **5×** — the `NavItem`/`NavChild` TYPE
  field + the two `resolveNav` reads (`item.feature_key`, `c.feature_key`); the nav
  DATA carries none → `entOf(undefined)` → `modeOfIn(...,undefined)="ON"` for every
  item (`Sidebar/index.tsx:74,79,105`). The Sidebar gate code shipped but is dead.

So a real vendor whose `/me/entitlements` says `grow.campaigns:"hidden"` STILL gets
the Campaigns link in the sidebar and the page still renders. Exactly the founder's
complaint.

---

## EXACT broken link

**Link (2): `contstants/navigation.tsx` carries ZERO `feature_key` fields, and no
page wraps in `EntitlementGuard`.** `Sidebar/index.tsx resolveNav` is fully built to
HIDE/LOCK by `entOf(item.feature_key)` — but every key it reads is `undefined`.
Root: the premium-UI "Signal" nav rewrite shipped `roles:` gating only and never
re-added `feature_key`; the page-guard wave that was supposed to wrap pages never ran.

## THE FIX (frontend-only; never touch the backend — it is the live earner and it works)

**Fix A — `contstants/navigation.tsx`: add `feature_key` to every group + child**,
joining each `href` to its LIVE registry key (the vendor `/me/entitlements` modes
map IS the authoritative key list; e.g. `mod.grow`+`grow.campaigns`/`grow.ads`/
`grow.funnels`/`grow.forms`; `mod.engage`+`engage.run`/`engage.calls`/...;
`mod.ai_manager`+`ai_manager.*`; `mod.money`+`money.*`; `mod.foundation`+
`foundation.suppression`/`foundation.vendors`). Leave `core.*` and the admin-only
Super Admin group UNKEYED (admins bypass; core never hides). `NavItem`/`NavChild`
already declare `feature_key?` (`Sidebar/index.tsx:36,47`) — no type change.

**Fix B — gate the pages.** Either wrap each vendor page in
`<EntitlementGuard featureKey=... featureLabel=... upgradeHref="/billing/plan">`,
OR (DRY, preferred — avoids touching ~25 pages) add ONE `PATHNAME→feature_key` map
+ a single `<RouteEntitlementGate>` in `app/providers.tsx` next to the
`EntitlementProvider`, using `usePathname()` → `useEntitlement(key)` →
HIDE-redirect / LOCK-overlay. Keep that map beside the nav key list (one source of
truth).

**Do NOT change:** `lib/entitlements.ts`, `lib/api.ts getEntitlements`,
`EntitlementProvider` (already mounted + polling), `LockOverlay`, the Super Admin
write path, ANY backend file.

## VERIFY after the fix (founder flow, browser)
1. Super Admin → vendor → Permissions → `grow.campaigns` = Hidden (toggle already writes — proven).
2. As that vendor: the **Campaigns link disappears** from the sidebar AND typing
   `/campaigns` **redirects to `/`** (HIDE) or shows the **blurred LockOverlay** (Locked).
   Today both still show.
3. Reset → On: link returns, page opens. (Backend already passes — see PROOF 1.)

## Regression gate (held green this diagnosis, read-only — nothing changed)
Public `https://panel.famit.in`: `/api/campaigns` 200, `/api/leads` 200, `/api/me` 200.
Vendor restore left `grow.campaigns` = `on` (version 30). No writes left in place.
