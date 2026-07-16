"use client";

// Self-contained API client for the "Famit Growth" — Realtime All-Ads-Platform Analysis
// dashboard. Mirrors lib/api.ts auth exactly (BASE, X-Auth from localStorage, 401 -> /login).
// The /grow/platforms + /grow/advisor surfaces are FEATURE_GROW-gated on the backend; reads
// degrade to a calm dormant state, never an error wall. Shapes match grow.platforms /
// grow.advisor public() 1:1.

const BASE =
    typeof process !== "undefined" && process.env.NEXT_PUBLIC_API_BASE
        ? process.env.NEXT_PUBLIC_API_BASE
        : "/api";

function authHeaders(): HeadersInit {
    if (typeof window === "undefined") return {};
    const token = localStorage.getItem("famit_token");
    return token ? { "X-Auth": token } : {};
}

function handle401(res: Response) {
    if (res.status === 401 && typeof window !== "undefined") {
        localStorage.removeItem("famit_token");
        localStorage.removeItem("famit_me");
        window.location.href = "/login";
        throw new Error("Unauthorized");
    }
}

/* ----------------------------------------------------------- backend types */

export type PlatformStatus = "live" | "demo" | "no_creds" | "error" | string;

export type LocationRow = { name: string; spend_minor: number; conversions: number };
export type DeviceRow = { name: string; share: number };
export type TopAd = { name: string; spend_minor: number; ctr: number; conversions: number };

export type PlatformMetric = {
    platform: string;
    label: string;
    icon: string;
    kind: string;
    status: PlatformStatus;
    currency: string;
    period: string;
    spend_minor: number;
    impressions: number;
    clicks: number;
    conversions: number;
    reach: number;
    ctr: number;
    cpc_minor: number;
    cpm_minor: number;
    cpi_minor: number;
    cvr: number;
    by_location: LocationRow[];
    by_device: DeviceRow[];
    top_ads: TopAd[];
    reason: string;
};

export type Insight = { platform: string; label: string; value: number } | null;

export type GrowthSummary = {
    total_platforms: number;
    active_platforms: number;
    active_platform_keys: string[];
    currency: string;
    total_spend_minor: number;
    total_impressions: number;
    total_clicks: number;
    total_conversions: number;
    avg_ctr: number;
    avg_cpc_minor: number;
    avg_cpm_minor: number;
    avg_cpi_minor: number;
    cheapest_cpc: Insight;
    cheapest_cpi: Insight;
    best_ctr: Insight;
    best_cvr: Insight;
    top_spender: Insight;
    same_type_ads: { concept: string; platforms: string[] }[];
    period: string;
};

export type GrowthSnapshot = { period: string; platforms: PlatformMetric[]; summary: GrowthSummary };

export type Recommendation = { action: string; platform?: string; text: string; impact: string };
export type RecommendResponse = {
    goal: string;
    recommendations: Recommendation[];
    allocation: { platform: string; label: string; share: number }[];
    summary_text: string;
};
export type ChatResponse = { answer: string; intent: string; used: string };
export type Goal = "min_cost" | "max_conversions" | "max_reach";

/* ---------------------------------------------- discriminated read result */

export type ReadResult<T> =
    | { kind: "ok"; data: T }
    | { kind: "dormant"; reason: string }
    | { kind: "error"; message: string };

async function read<T>(path: string): Promise<ReadResult<T>> {
    let res: Response;
    try {
        res = await fetch(`${BASE}${path}`, { headers: authHeaders() });
    } catch {
        return { kind: "dormant", reason: "unreachable" };
    }
    handle401(res);
    if (res.status === 404 || res.status === 501 || res.status === 503) {
        return { kind: "dormant", reason: `http_${res.status}` };
    }
    if (!res.ok) {
        let msg = `Request failed (${res.status})`;
        try {
            const b = await res.json();
            if (b && typeof b.detail === "string") msg = b.detail;
            else if (b && typeof b.error === "string") msg = b.error;
        } catch {
            /* non-JSON */
        }
        return { kind: "error", message: msg };
    }
    try {
        return { kind: "ok", data: (await res.json()) as T };
    } catch {
        return { kind: "error", message: "Malformed response" };
    }
}

async function write<T>(path: string, body: Record<string, unknown>): Promise<T> {
    const res = await fetch(`${BASE}${path}`, {
        method: "POST",
        headers: { ...authHeaders(), "Content-Type": "application/json" },
        body: JSON.stringify(body),
    });
    handle401(res);
    if (res.status === 404 || res.status === 501 || res.status === 503) {
        throw new Error("Famit Growth is not enabled yet — set FEATURE_GROW=1 on the backend.");
    }
    if (!res.ok) throw new Error(`Action failed (${res.status})`);
    return res.json();
}

/* --------------------------------------------------- public reads (never throw) */

export const getGrowthSnapshot = (period = "30d") =>
    read<GrowthSnapshot>(`/grow/platforms?period=${encodeURIComponent(period)}`);

export const recommend = (goal: Goal) =>
    write<RecommendResponse>("/grow/advisor/recommend", { goal });

export const chat = (question: string) =>
    write<ChatResponse>("/grow/advisor/chat", { question });

/* ------------------------------------------------------------------ helpers */

export function fmtMoney(minor?: number | null, currency = "INR"): string {
    if (!minor) return "—";
    const major = minor / 100;
    const sym = currency === "INR" ? "₹" : currency === "USD" ? "$" : "";
    try {
        return `${sym}${major.toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
    } catch {
        return `${sym}${major}`;
    }
}

export function fmtNum(n?: number | null): string {
    if (n === null || n === undefined) return "—";
    if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
    if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
    return String(n);
}

export function fmtPct(x?: number | null): string {
    if (x === null || x === undefined) return "—";
    return `${(x * 100).toFixed(2)}%`;
}

export function statusVariant(s: PlatformStatus): "success" | "warning" | "info" | "danger" | "neutral" {
    if (s === "live") return "success";
    if (s === "demo") return "info";
    if (s === "error") return "danger";
    return "neutral"; // no_creds
}

export function statusLabel(s: PlatformStatus): string {
    const map: Record<string, string> = { live: "Live", demo: "Demo", no_creds: "Connect", error: "Error" };
    return map[s] || s;
}
