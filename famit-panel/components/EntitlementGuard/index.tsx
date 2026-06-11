"use client";

// ============================================================
// EntitlementGuard (CL-F0) — per-page route guard, sibling to AuthGuard
//
// Mirrors the backend choke-point COSMETICALLY (design/control-ui.md §4):
//   HIDE -> redirect to "/" (the does-not-exist UX; same shape AuthGuard uses
//           for no-token). The backend returns a real 404 regardless.
//   LOCK -> render the page wrapped in <LockOverlay> (blurred + upsell). The
//           backend still 402s the underlying /api/* route.
//   ON   -> render the page normally.
//
// It also revalidates the entitlement map on route change (one of the three
// opportunistic refresh triggers from the realtime-enforcement design), so
// entering a just-downgraded page reconciles within a tick.
//
// COSMETIC ONLY (spec §9.1): a user who strips this guard in devtools still
// hits the backend 404/402 on every data fetch. This guard never grants access.
//
// USAGE (per gated page — added in the later page waves, NOT this unit):
//   export default function CallsPage() {
//     return <EntitlementGuard featureKey="engage.calls"> ...page... </EntitlementGuard>;
//   }
// While the map is still loading we render children optimistically (the backend
// is the real gate); a flip resolves on the next store tick.
// ============================================================

import { useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";
import {
    useEntitlement,
    useEntitlements,
    revalidateEntitlements,
} from "@/lib/entitlements";
import LockOverlay from "@/components/LockOverlay";

type EntitlementGuardProps = {
    // The registry feature_key for this route (e.g. "engage.calls").
    featureKey: string;
    // Human label for the LockOverlay copy (defaults to the key).
    featureLabel?: string;
    // Where HIDE redirects (default "/").
    redirectTo?: string;
    // Where the LOCK "Upgrade" CTA routes.
    upgradeHref?: string;
    children: React.ReactNode;
};

const EntitlementGuard = ({
    featureKey,
    featureLabel,
    redirectTo = "/",
    upgradeHref,
    children,
}: EntitlementGuardProps) => {
    const pathname = usePathname();
    const router = useRouter();
    const mode = useEntitlement(featureKey);
    const { loaded } = useEntitlements();

    // Revalidate on route change (opportunistic refresh trigger).
    useEffect(() => {
        void revalidateEntitlements();
    }, [pathname]);

    // HIDE -> bounce to a safe route once we actually KNOW it's hidden (after a
    // real load, never on the optimistic resting default — avoids flicker-bounce
    // on first paint).
    useEffect(() => {
        if (loaded && mode === "HIDE") {
            router.replace(redirectTo);
        }
    }, [loaded, mode, redirectTo, router]);

    if (loaded && mode === "HIDE") {
        // Render nothing while the redirect lands (does-not-exist UX).
        return null;
    }

    if (mode === "LOCK") {
        return (
            <LockOverlay feature={featureLabel || featureKey} upgradeHref={upgradeHref}>
                {children}
            </LockOverlay>
        );
    }

    // ON (or still-loading optimistic) -> render the page.
    return <>{children}</>;
};

export default EntitlementGuard;
