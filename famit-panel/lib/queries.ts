// PERF UNIT-3 — cached useQuery hooks (the highest-ROI perf fix, plan R1).
//
// Each hook wraps the EXISTING lib/api.ts (and lib/assets.ts / crm/client.ts) fn —
// no fetch logic is duplicated, the network contract is unchanged. The win is the
// cache: leaving a tab and coming back is served instantly from the in-memory
// React Query cache (and revalidated in the background) instead of a full
// 10-20s re-fetch. Pages opt in by swapping their useEffect+useState fetch for one
// of these hooks; nothing here forces a page to change, so adoption is incremental
// and safe.
//
// Query keys are stable + parameterised so two pages reading the same data (e.g.
// the CRM list and the Run-page audience both read leads) SHARE one cache entry.
//
// `placeholderData: keepPreviousData` on the filtered/paged lists keeps the prior
// result on screen while a new filter/page loads — no skeleton flash mid-browse.

"use client";

import {
    useQuery,
    useInfiniteQuery,
    keepPreviousData,
    type UseQueryOptions,
} from "@tanstack/react-query";

import {
    getCalls,
    getLeads,
    getCampaigns,
    getStats,
    getVoices,
    getStatus,
    type CallsPage,
    type GetCallsOpts,
    type LeadsPage,
    type Campaign,
    type Stats,
    type Voice,
    type VoiceProvider,
    type JobStatus,
} from "@/lib/api";
import { listAssets, type AssetQuery, type AssetListPage } from "@/lib/assets";
import {
    getContacts,
    type ContactsQuery,
    type ContactsResponse,
} from "@/app/crm/client";

// ── Stable query-key factory ────────────────────────────────────────────────
// Centralised so keys never drift between a reader and an invalidator.
export const qk = {
    calls: (opts?: GetCallsOpts): unknown[] => ["calls", opts ?? {}],
    leads: (opts?: Record<string, unknown>): unknown[] => ["leads", opts ?? {}],
    // Infinite (paged) variants — keyed separately from the one-shot reads so a
    // page consuming the cursor never collides with a flat-list cache entry.
    callsInfinite: (opts?: GetCallsOpts): unknown[] => ["calls-infinite", opts ?? {}],
    leadsInfinite: (opts?: Record<string, unknown>): unknown[] => ["leads-infinite", opts ?? {}],
    campaigns: (): unknown[] => ["campaigns"],
    stats: (): unknown[] => ["stats"],
    voices: (provider?: VoiceProvider): unknown[] => ["voices", provider ?? "elevenlabs"],
    contacts: (opts?: ContactsQuery): unknown[] => ["contacts", opts ?? {}],
    assets: (q?: AssetQuery): unknown[] => ["assets", q ?? {}],
    jobStatus: (job: string): unknown[] => ["job-status", job],
};

// Allow each call site to override defaults (e.g. enabled, refetchInterval) while
// keeping the wrapper terse. T = the queryFn's resolved type.
type Extra<T> = Partial<Omit<UseQueryOptions<T, Error, T>, "queryKey" | "queryFn">>;

// ── Calls ───────────────────────────────────────────────────────────────────
export function useCalls(opts?: GetCallsOpts, extra?: Extra<CallsPage>) {
    return useQuery<CallsPage, Error, CallsPage>({
        queryKey: qk.calls(opts),
        queryFn: () => getCalls(opts),
        placeholderData: keepPreviousData,
        ...extra,
    });
}

// ── Calls (infinite / paged) ─────────────────────────────────────────────────
// PERF UNIT-4: consume the backend UNIT-1 cursor contract. Each page is a slim
// newest-first `{calls,total,offset,limit,next}`; `next` = the offset to fetch the
// next page (or null on the last page). The page list virtualizes the flattened
// rows and calls `fetchNextPage()` as the viewport nears the end, so the call-logs
// page loads ONE page at a time instead of every row at once.
//
// `pageSize` becomes the `limit` per page; `order`/`slim` are forced on so the
// response is the trimmed paged shape. `campaign_id`/`outcome` filters re-key the
// query (a new filter starts a fresh page-0 fetch).
export function useCallsInfinite(opts?: {
    pageSize?: number;
    campaign_id?: string;
    outcome?: string;
    // Lane C SPEED — backend sort across ALL records. Re-keys the query (a new
    // sort starts a fresh page-0 fetch); the page keeps a client sort fallback.
    sort_by?: string;
    order?: "asc" | "desc";
}) {
    const pageSize = opts?.pageSize ?? 60;
    const base: GetCallsOpts = {
        limit: pageSize,
        order: opts?.order ?? "desc",
        sort_by: opts?.sort_by,
        slim: true,
        campaign_id: opts?.campaign_id,
        outcome: opts?.outcome,
    };
    return useInfiniteQuery<CallsPage, Error>({
        queryKey: qk.callsInfinite(base),
        queryFn: ({ pageParam }) =>
            getCalls({ ...base, offset: (pageParam as number) ?? 0 }),
        initialPageParam: 0,
        // `next` is the absolute offset for the next page, or null on the last page.
        getNextPageParam: (last) => (last.next == null ? undefined : last.next),
    });
}

// ── Leads ───────────────────────────────────────────────────────────────────
export function useLeads(
    opts?: { hot?: boolean; sort?: string; batch?: string; limit?: number; offset?: number },
    extra?: Extra<LeadsPage>
) {
    return useQuery<LeadsPage, Error, LeadsPage>({
        queryKey: qk.leads(opts),
        queryFn: () => getLeads(opts),
        placeholderData: keepPreviousData,
        ...extra,
    });
}

// ── Leads (infinite / paged) ─────────────────────────────────────────────────
// PERF UNIT-4: consume the backend UNIT-1 `{leads,total,offset,limit,next}` cursor.
// The leads page virtualizes the flattened rows and fetches the next page as the
// viewport nears the end. `hot` re-keys the query (All<->Hot starts a fresh fetch).
export function useLeadsInfinite(opts?: {
    pageSize?: number;
    hot?: boolean;
    sort?: string;
    // Temperature band (hot|warm|cold|dead) -> the backend ?status= filter, so EVERY
    // band pages server-side (no more client-only partial filter that broke Warm/Cold/
    // Dead). `hot` stays for back-compat; when `status` is set it is the source of truth.
    status?: string;
}) {
    const pageSize = opts?.pageSize ?? 60;
    const base = {
        limit: pageSize,
        hot: opts?.status ? undefined : opts?.hot,
        sort: opts?.sort,
        status: opts?.status || undefined,
    };
    return useInfiniteQuery<LeadsPage, Error>({
        queryKey: qk.leadsInfinite(base),
        queryFn: ({ pageParam }) =>
            getLeads({ ...base, offset: (pageParam as number) ?? 0 }),
        initialPageParam: 0,
        getNextPageParam: (last) => (last.next == null ? undefined : last.next),
    });
}

// ── Campaigns ───────────────────────────────────────────────────────────────
export function useCampaigns(extra?: Extra<{ campaigns: Campaign[] }>) {
    return useQuery<{ campaigns: Campaign[] }, Error, { campaigns: Campaign[] }>({
        queryKey: qk.campaigns(),
        queryFn: () => getCampaigns(),
        ...extra,
    });
}

// ── Dashboard stats ─────────────────────────────────────────────────────────
export function useStats(extra?: Extra<Stats>) {
    return useQuery<Stats, Error, Stats>({
        queryKey: qk.stats(),
        queryFn: () => getStats(),
        ...extra,
    });
}

// ── Voices (already dormant-safe in api.ts: never throws) ────────────────────
export function useVoices(
    provider?: VoiceProvider,
    extra?: Extra<{ provider: string; voices: Voice[] }>
) {
    return useQuery<{ provider: string; voices: Voice[] }, Error>({
        queryKey: qk.voices(provider),
        queryFn: () => getVoices(provider),
        // voices rarely change — cache longer.
        staleTime: 5 * 60_000,
        ...extra,
    });
}

// ── CRM contacts list (already PG-paginated server-side) ─────────────────────
export function useContacts(opts?: ContactsQuery, extra?: Extra<ContactsResponse>) {
    return useQuery<ContactsResponse, Error, ContactsResponse>({
        queryKey: qk.contacts(opts),
        queryFn: () => getContacts(opts),
        placeholderData: keepPreviousData,
        ...extra,
    });
}

// ── Creative assets library (dormant-safe in assets.ts) ──────────────────────
export function useAssets(q?: AssetQuery, extra?: Extra<AssetListPage>) {
    return useQuery<AssetListPage, Error, AssetListPage>({
        queryKey: qk.assets(q),
        queryFn: () => listAssets(q ?? {}),
        placeholderData: keepPreviousData,
        ...extra,
    });
}

// ── Job status (Run page) — short cache, callers set refetchInterval ─────────
export function useJobStatus(job: string | null, extra?: Extra<JobStatus>) {
    return useQuery<JobStatus, Error, JobStatus>({
        queryKey: qk.jobStatus(job ?? ""),
        queryFn: () => getStatus(job as string),
        enabled: !!job,
        staleTime: 0,
        ...extra,
    });
}
