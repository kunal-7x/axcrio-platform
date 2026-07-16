"use client";

import { ThemeProvider } from "next-themes";
import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { QueryClientProvider } from "@tanstack/react-query";
import { makeQueryClient } from "@/lib/query-client";
import { EntitlementProvider } from "@/lib/entitlements";
import RouteEntitlementGate from "@/components/RouteEntitlementGate";
import SessionBeacon from "@/components/SessionBeacon";

function AuthGuard({ children }: { children: React.ReactNode }) {
    const pathname = usePathname();
    const router = useRouter();

    useEffect(() => {
        if (pathname === "/login" || pathname === "/signup") return;
        const token = localStorage.getItem("famit_token");
        if (!token) {
            router.replace("/login");
        }
    }, [pathname, router]);

    return <>{children}</>;
}

// CL-F0: mount the entitlement poller ONCE for the authenticated app. On the
// login route there's no token, so we skip the provider (its fetch would just
// 401/404-degrade harmlessly, but skipping avoids a needless request loop on
// the unauthenticated screen).
const Providers = ({ children }: { children: React.ReactNode }) => {
    const pathname = usePathname();
    const authed = pathname !== "/login" && pathname !== "/signup";
    // PERF UNIT-3: one QueryClient for the app's lifetime. useState (not a module
    // const) so it survives Fast Refresh in dev and is created once per mount,
    // never shared across server requests.
    const [queryClient] = useState(makeQueryClient);
    return (
        <QueryClientProvider client={queryClient}>
            <ThemeProvider disableTransitionOnChange>
                <AuthGuard>
                    {authed ? (
                        <EntitlementProvider>
                            {/* CL-F0: one app-wide route guard. HIDE-redirects / LOCK-
                                overlays a directly-typed URL to a gated page, using the
                                same /me/entitlements store the sidebar reads. Cosmetic —
                                the backend 404/402 is the real boundary. */}
                            <RouteEntitlementGate>{children}</RouteEntitlementGate>
                            {/* Advanced monitoring: one best-effort location/device
                                beacon per authed load. */}
                            <SessionBeacon />
                        </EntitlementProvider>
                    ) : (
                        children
                    )}
                </AuthGuard>
            </ThemeProvider>
        </QueryClientProvider>
    );
};

export default Providers;
