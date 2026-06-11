"use client";

// ============================================================
// RouteEntitlementGate (CL-F0) — ONE app-wide route guard
//
// The DRY companion to per-page <EntitlementGuard>: instead of wrapping ~25
// vendor pages, this single gate (mounted once in app/providers.tsx, inside the
// EntitlementProvider) reads usePathname(), maps it to its registry feature_key,
// resolves the mode off the SAME live /me/entitlements store the sidebar uses,
// and applies the cosmetic verdict:
//   HIDE -> redirect to "/" (does-not-exist UX; backend returns a real 404 too)
//   LOCK -> render the page wrapped in <LockOverlay> (blurred + upsell; backend
//           still 402s the data route)
//   ON / unknown-path -> render normally.
//
// WHY a guard and not just the sidebar: hiding the nav link is not enough — a
// vendor can still TYPE /campaigns. The backend 404/402s the DATA fetch, but the
// page chrome renders (silent empty state). This gate makes a directly-typed URL
// to a hidden/locked page actually disappear / lock, matching the founder flow.
//
// SOURCE OF TRUTH: the PATHNAME->feature_key map is DERIVED from the same
// FEATURE_REGISTRY nav_href values lib/api.ts exports, so it can never drift from
// the nav keys. Longest-prefix match handles nested + dynamic routes (e.g.
// /crm/123 -> sell.crm, /campaigns/abc -> grow.campaigns).
//
// COSMETIC ONLY (spec §9.1): stripping this guard in devtools changes nothing —
// every /api/* fetch still hits the backend 404/402. This is UX, not the boundary.
// ============================================================

import { useEffect, useMemo } from "react";
import { usePathname, useRouter } from "next/navigation";
import {
    useEntitlement,
    useEntitlements,
    revalidateEntitlements,
} from "@/lib/entitlements";
import LockOverlay from "@/components/LockOverlay";
import { FEATURE_REGISTRY } from "@/lib/api";

// ── PATHNAME -> feature_key (the route map) ───────────────────────────────────
// Built ONCE from the registry: every node with a nav_href contributes
// `nav_href -> key`. We additionally alias the /billing/* sub-routes to the core
// money.billing key (so they resolve ON; core is never hidden) and add the
// /ai-manager root (which redirects to Overview) so the bare path resolves too.
// CORE keys (is_core) are intentionally EXCLUDED from the gate map so a core page
// (Dashboard, Billing, Settings) is never even evaluated for HIDE/LOCK.
type Rule = { prefix: string; key: string };

const ROUTE_RULES: Rule[] = (() => {
    const rules: Rule[] = [];
    for (const node of FEATURE_REGISTRY) {
        if (!node.nav_href) continue;
        if (node.is_core) continue; // core pages are never gated (Dashboard/Billing/Settings)
        rules.push({ prefix: node.nav_href.replace(/\/+$/, "") || "/", key: node.key });
    }
    // /ai-manager root → Overview's key (the bare path redirects to Overview).
    rules.push({ prefix: "/ai-manager", key: "ai_manager.overview" });
    // Longest prefix first so /ai-manager/overview wins over /ai-manager, and a
    // nested/dynamic child (/crm/123) matches its page prefix.
    rules.sort((a, b) => b.prefix.length - a.prefix.length);
    return rules;
})();

// Resolve a pathname to its governing feature_key (longest-prefix-wins), or null
// for an ungoverned/core path (rendered through untouched).
export function featureKeyForPathname(pathname: string | null): string | null {
    if (!pathname) return null;
    const p = pathname.split("?")[0].replace(/\/+$/, "") || "/";
    if (p === "/") return null; // dashboard / core root — never gated
    for (const r of ROUTE_RULES) {
        if (p === r.prefix || p.startsWith(r.prefix + "/")) return r.key;
    }
    return null;
}

const RouteEntitlementGate = ({ children }: { children: React.ReactNode }) => {
    const pathname = usePathname();
    const router = useRouter();
    const { loaded } = useEntitlements();

    const featureKey = useMemo(() => featureKeyForPathname(pathname), [pathname]);
    // useEntitlement re-renders this gate whenever a control write flips the key.
    const mode = useEntitlement(featureKey ?? undefined);

    // Revalidate the map on every route change (opportunistic refresh trigger) so
    // entering a just-downgraded page reconciles within a tick.
    useEffect(() => {
        void revalidateEntitlements();
    }, [pathname]);

    // HIDE -> bounce home, but only once we KNOW (a real load resolved) — never on
    // the optimistic resting default, which would flicker-bounce on first paint.
    useEffect(() => {
        if (featureKey && loaded && mode === "HIDE") {
            router.replace("/");
        }
    }, [featureKey, loaded, mode, router]);

    if (featureKey && loaded && mode === "HIDE") {
        // Render nothing while the redirect lands (does-not-exist UX).
        return null;
    }

    if (featureKey && mode === "LOCK") {
        const label = labelForKey(featureKey);
        return (
            <LockOverlay feature={label} upgradeHref="/billing/plan">
                {children}
            </LockOverlay>
        );
    }

    // ON / unknown-path / core / still-loading-optimistic -> render normally.
    return <>{children}</>;
};

// Human label for the LockOverlay copy (off the registry; falls back to the key).
function labelForKey(key: string): string {
    const node = FEATURE_REGISTRY.find((n) => n.key === key);
    return node?.label || key;
}

export default RouteEntitlementGate;
