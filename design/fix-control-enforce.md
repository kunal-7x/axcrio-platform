# FIX — Control Layer "hide/lock a vendor's page but they still see it"

**Status:** ROOT CAUSE FOUND (read-only diagnosis, end-to-end, live boxes).
**Date:** 2026-06-11. **Verdict:** Backend enforces correctly. **The FRONTEND is the broken link.**

---

## TL;DR (the one broken link)

The vendor panel **never reads a `feature_key` for any page or nav item**, so the
entitlement map it polls is resolved against `undefined` → always `"ON"`. The Super
Admin write persists AND the backend 404/402s the data API correctly — but the
vendor's **sidebar still lists the page and the page chrome still renders**, so the
founder sees "they still see/use it."

- Link (a) WRITE PERSIST → ✅ WORKS (proven: write returns `after:"hidden"`, version 1→2).
- Link (c) BACKEND ENFORCE → ✅ WORKS (proven: vendor `GET /campaigns` → **404** after HIDE).
- Link (b) FRONTEND READ+APPLY → ❌ **BROKEN — `feature_key` is wired to nothing.**

---

## What the live test proved (backend is fine)

Box `famit@168.144.153.145`, `CONTROL_ENABLED=1`, `FIREWALL_ENABLED=true`. Test
tenant `013a13841fd5` (p0sectest, non-admin). Minted a real vendor hmac token
(`tenant_id.hmac(tenant_id, var/secret)`) and ran the full cycle:

| Step | Call | Result |
|---|---|---|
| baseline | vendor `GET /campaigns` | **200** |
| baseline | vendor `/me/entitlements` `grow.campaigns` | `on`, version 1 |
| legacy-pw write | `PUT /admin/.../entitlements/grow.campaigns` w/ `X-Auth: FamitCall2026` | **403** (legacy pw correctly excluded from /admin/*) |
| admin write | same with admin hmac token, `mode=hidden` | `{ok:true, after:"hidden", version:2}` |
| after | vendor `/me/entitlements` `grow.campaigns` | **`hidden`, version 2** |
| after | vendor `GET /campaigns` | **404** (HIDE enforced) |
| after | vendor `GET /leads` | **200** (scoped — only campaigns hidden) |
| restore | `DELETE .../entitlements/grow.campaigns` → vendor `GET /campaigns` | **200** |

The write persists, version bumps, `/me/entitlements` reflects it, and the
middleware (`caller.py:366 _enforce_entitlement_mw` → `feature_key_for_path` →
`evaluate` → `hidden`=404 / `locked`=402, core-bypass, admin-bypass, fail-closed)
does exactly what the spec says. **Nothing to fix on the backend.**

---

## The broken FRONTEND link — exact location

The FE entitlement plumbing is fully built and mounted, but **nothing consumes it
with a real `feature_key`:**

### Fault 1 — `contstants/navigation.tsx` has ZERO `feature_key` fields
`components/Sidebar/index.tsx` `resolveNav` (lines 66–90) drops a HIDE child and
dims a LOCK child by calling `entOf(item.feature_key)` / `entOf(c.feature_key)`.
But **every entry in `navigation.tsx` carries only `roles:` — never `feature_key`.**
`modeOfIn(payload, undefined)` returns `"ON"` (lib/entitlements.ts:202–205,
`if (!key) return "ON"`). So `resolveNav` evaluates `entOf(undefined)="ON"` for
every item → **the sidebar never hides or locks anything based on entitlements.**
Only role gating works. (Confirmed: `git log -S feature_key -- navigation.tsx`
returns nothing — the key was never in the committed nav; the premium-UI "Signal"
nav rewrite shipped without it.)

### Fault 2 — `components/EntitlementGuard` is built but wraps ZERO pages
`EntitlementGuard` (HIDE→`router.replace("/")`, LOCK→`<LockOverlay>`) is correct,
but a repo-wide search finds it imported/used by **no page** — only its own
docstring references it (`grep EntitlementGuard app/` = 0 usages). So there is **no
route-level HIDE redirect and no LOCK overlay on any vendor page.** A hidden/locked
page renders its full chrome on the client; only its `/api/*` data fetch 404/402s.

**Net effect the founder sees:** hide a page → vendor's sidebar STILL shows the
link, the page STILL opens and renders; only the data inside fails (often a silent
empty/skeleton state, not an obvious "blocked"). Looks like "control isn't working."

---

## THE FIX (frontend only — backend untouched)

### Fix A — add `feature_key` to every nav entry (`contstants/navigation.tsx`)
Tag each link/child/group with its registry key so `resolveNav` can act. Use the
LIVE registry keys (from `var/control/registry.json`). Examples:

```
// groups → module key; children → their page key
{ title: "Grow", icon: "promote", feature_key: "mod.grow", list: [
    { title: "Campaigns",   href: "/campaigns",     feature_key: "grow.campaigns" },
    { title: "Ad Automation", href: "/ads", roles:"manager", feature_key: "grow.ads" },
    { title: "Funnels",     href: "/funnels",       feature_key: "grow.funnels" },
    { title: "Form Builder", href: "/forms",        feature_key: "grow.forms" },
]},
{ title: "AI Manager", icon:"chat-think", roles:"manager", feature_key:"mod.ai_manager", list:[
    { title:"Overview", href:"/ai-manager/overview", feature_key:"ai_manager.overview" },
    { title:"Try it",   href:"/ai-manager/test",     feature_key:"ai_manager.test" }, ...
]},
// Sell→mod.sell (sell.leads, sell.crm); Engage→mod.engage (engage.run, engage.calls,
// engage.callbacks, engage.whatsapp, engage.support, engage.booking);
// Automate→mod.automate (automate.workflows, automate.webhooks); Money→mod.money; etc.
```
`NavItem`/`NavChild` already declare `feature_key?` (Sidebar/index.tsx:32–51) — no
type change. CORE keys (core.*) and the admin-only "Super Admin" group should stay
unkeyed (admins bypass; core never hidden). One-time chore: map each href to its
registry key (the registry already stores `nav_href` per key — join on that).

### Fix B — wrap each gated page in `<EntitlementGuard featureKey=...>`
Add the guard at the top of every vendor-facing page so a directly-typed URL gets
the HIDE redirect / LOCK overlay (not just an empty data state):

```tsx
// app/campaigns/page.tsx
export default function CampaignsPage() {
  return (
    <EntitlementGuard featureKey="grow.campaigns" featureLabel="Campaigns" upgradeHref="/billing/plan">
      {/* existing page */}
    </EntitlementGuard>
  );
}
```
Lower-effort alternative (DRY, one place): add a `PATHNAME → feature_key` map and a
single `<RouteEntitlementGate>` in `app/providers.tsx` (next to `AuthGuard`) that
looks up `usePathname()`, resolves the mode, and applies HIDE-redirect/LOCK-overlay
globally. Either works; the map-in-providers approach avoids touching ~25 pages and
keeps the key list beside the nav key list (single source of truth).

### Do NOT change
- `lib/entitlements.ts`, `lib/api.ts getEntitlements`, `EntitlementProvider`
  (mounted in providers.tsx, polling works), `LockOverlay` — all correct as-is.
- Anything on the backend. It enforces. Touching it risks the live earner.

---

## Verify after the fix (same loop, now FE-visible)
1. Super Admin → a test vendor → Permissions → set `grow.campaigns` = Hidden.
2. Log in AS that vendor (or impersonate): the **Campaigns link disappears from the
   sidebar**, and typing `/campaigns` **redirects to `/`** (HIDE) or shows the
   **blurred LockOverlay** (if set to Locked). Today: link stays, page opens.
3. Reset to On → link returns, page opens. (Backend already passes this — see table.)

## One-line summary
Backend control enforcement is LIVE and correct (404/402 proven on a real vendor
token); the FE is inert because **no nav item or page carries a `feature_key`** —
add `feature_key` to `navigation.tsx` (Fault 1) and wrap gated pages in the existing
`EntitlementGuard` (Fault 2). FE-only fix; never touch the backend.
