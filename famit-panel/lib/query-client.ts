// PERF UNIT-3 — single app-wide React Query client.
//
// THE highest-ROI perf fix (plan R1, design/latency-diagnosis-v2-PERF-PLAN.md):
// before this, EVERY tab switch re-fetched from scratch (no cache) = the 10-20s
// pain. With a shared QueryClient + sane staleTime, leaving a tab and coming back
// is INSTANT — served from the in-memory cache and revalidated in the background
// (stale-while-revalidate). No backend change.
//
// Defaults chosen for an internal admin panel (read-heavy, low write-rate):
//  - staleTime 30s   : a re-visit within 30s shows cached data with NO network hit
//                      at all; after 30s it shows cache instantly + revalidates in bg.
//  - gcTime 5min     : unused query data is kept 5 min so a quick tab round-trip is
//                      still a cache hit even past staleTime.
//  - refetchOnWindowFocus off : avoid a refetch storm every time the user alt-tabs.
//  - retry 1         : one quiet retry, then surface — don't hammer a degraded box.
//  - placeholderData keepPreviousData is applied PER-HOOK (lib/queries.ts) where it
//    matters (paginated/filtered lists) so the old page stays on screen while the
//    next page loads instead of flashing a skeleton.

import { QueryClient } from "@tanstack/react-query";

export function makeQueryClient(): QueryClient {
    return new QueryClient({
        defaultOptions: {
            queries: {
                staleTime: 30_000,
                gcTime: 5 * 60_000,
                refetchOnWindowFocus: false,
                refetchOnReconnect: true,
                retry: 1,
            },
        },
    });
}
