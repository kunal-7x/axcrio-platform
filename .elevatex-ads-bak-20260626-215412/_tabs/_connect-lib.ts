// Ad-Engine · CONNECT + FUND client (BLINDSPOTS B4 / B16 / B17 / B13-B15).
//
// Self-contained API client for the /ads/connect/* sub-router (a SEPARATE backend module from the
// main /ads surface). Kept in its own file (not _lib.ts) so it composes cleanly with parallel work
// on the connections wizard. Auth mirrors _lib.ts EXACTLY: BASE = NEXT_PUBLIC_API_BASE || "/api",
// X-Auth from localStorage("famit_token"). All reads degrade dormant-safe (never throw a wall).

const BASE =
    typeof process !== "undefined" && process.env.NEXT_PUBLIC_API_BASE
        ? process.env.NEXT_PUBLIC_API_BASE
        : "/api";

function authHeaders(): HeadersInit {
    if (typeof window === "undefined") return {};
    const token = localStorage.getItem("famit_token");
    return token ? { "X-Auth": token } : {};
}

async function get<T>(path: string): Promise<T | null> {
    try {
        const res = await fetch(`${BASE}${path}`, { headers: authHeaders() });
        if (!res.ok) return null;
        return (await res.json()) as T;
    } catch {
        return null;
    }
}

async function post<T>(path: string, body: Record<string, unknown>): Promise<T | null> {
    try {
        const res = await fetch(`${BASE}${path}`, {
            method: "POST",
            headers: { "Content-Type": "application/json", ...authHeaders() },
            body: JSON.stringify(body),
        });
        if (!res.ok) return null;
        return (await res.json()) as T;
    } catch {
        return null;
    }
}

/* ------------------------------------------------------------------ types */

export type ConnectProvider = "meta" | "google";

export type ConnectProviderStatus = {
    provider: ConnectProvider;
    connected: boolean;
    app_configured: boolean; // founder registered the Meta/Google app + redirect URI
    redirect_uri: string;
    live: boolean; // ADS_OAUTH_LIVE armed (real token exchange) vs dry-run
};

export type ConnectStartResult = {
    ok: boolean;
    authorize_url?: string;
    state?: string;
    redirect_uri?: string;
    reason?: string; // ok | app_not_configured | unsupported_provider
};

export type ClaimKind = "page" | "dataset" | "wa-phone";

export type ClaimResult = {
    ok: boolean;
    kind?: ClaimKind;
    id?: string;
    proven?: string; // asserted | me_accounts
    reason?: string; // not_owned | already_claimed_by_other_tenant | ...
    linked_at?: number;
};

export type ClaimRow = { id: string; kind: string; linked_at?: number; updated_at?: number };

export type SubscribeResult = {
    ok: boolean;
    simulated?: boolean;
    status?: string; // subscribed | simulated | dry_run | subscribe_failed | page_not_claimed
    page_id?: string;
    reason?: string;
};

export type FundingStatus = {
    ok: boolean;
    model: "vendor_own_card" | "managed" | string;
    funded: boolean | null; // null = unknown (dry-run / not live) → show "connect a card"
    reason: string; // ok | not_configured | dry_run | read_failed | ...
    account_status?: number | string | null;
    funding_source?: boolean | null;
    manage_url?: string;
    balance_minor?: number;
    currency?: string;
};

export type FundingPrecheck = {
    ok: boolean;
    blocked: boolean;
    status: string; // ok | blocked_insufficient_funds
    reason: string;
    model?: string;
};

/* --------------------------------------------------------------- endpoints */

export const getConnectProviders = () =>
    get<{ ok: boolean; providers: ConnectProviderStatus[] }>("/ads/connect/providers");

export const startConnect = (provider: ConnectProvider) =>
    get<ConnectStartResult>(`/ads/connect/${encodeURIComponent(provider)}/start`);

export const claimAsset = (kind: ClaimKind, id: string, businessId?: string) =>
    post<ClaimResult>(`/ads/connect/claim/${encodeURIComponent(kind)}`, {
        id,
        ...(businessId ? { business_id: businessId } : {}),
    });

export const listClaims = () =>
    get<{ ok: boolean; claims: ClaimRow[] }>("/ads/connect/claims");

export const subscribeLeadgen = (pageId: string) =>
    post<SubscribeResult>("/ads/connect/subscribe/leadgen", { page_id: pageId });

export const getFundingStatus = () => get<FundingStatus>("/ads/connect/funding/status");

export const getFundingPrecheck = (requiredMinor = 0) =>
    get<FundingPrecheck>(`/ads/connect/funding/precheck?required_minor=${requiredMinor}`);

export const getFundingManageLink = () =>
    get<{ ok: boolean; url: string; model: string }>("/ads/connect/funding/manage-link");
