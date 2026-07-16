"use client";

// Self-contained API client for the Ads command-center page.
//
// WHY local (not lib/api.ts): the /ads router (ads_engine) is DEFINED-NOT-MOUNTED
// on the backend today — every endpoint 404s until the deferred wiring + Meta/
// Google creds land. Rather than couple the shared api module to a dormant
// surface (and risk a parallel session editing it), this page owns its own thin
// client. It mirrors lib/api.ts auth EXACTLY: BASE = NEXT_PUBLIC_API_BASE ||
// "/api", `X-Auth` header from localStorage `famit_token`, 401 -> /login.
//
// The list/health reads treat a non-200 as DORMANCY (the page renders a premium
// "not configured / coming soon" state) — they never throw. Mutations DO throw a
// friendly message so the form/buttons can surface it.
//
// Shapes match the backend ads_engine 1:1 (service.status / config.healthcheck /
// service.propose_campaign / approve / pause / optimize).

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

// The module status vocabulary (config.py + service.py). A campaign carries one
// of these; the page maps each to a Badge tone + a human label.
export type AdsStatus =
    | "draft"
    | "pending_approval"
    | "active"
    | "paused"
    | "dry_run"
    | "not_configured"
    | "blocked_cap_exceeded"
    | "blocked_cpl_breach"
    | "blocked_no_conversion_tracking"
    | "blocked_not_approved"
    | "blocked_insufficient_funds"
    | string;

export type AdsProviderStatus = "configured" | "not_configured" | "error" | string;

// GET /ads/health (and the embedded `config` block on /ads/campaigns).
export type AdsHealth = {
    module: string;
    dry_run: boolean;
    require_approval: boolean;
    providers: { meta: AdsProviderStatus; google: AdsProviderStatus };
    active_provider: string; // "meta" | "google" | "not_configured"
    caps: {
        daily_cap_minor: number;
        lifetime_cap_minor: number;
        org_daily_cap_minor: number;
        cpl_max_minor: number;
        cpl_min_conversions: number;
        poll_minutes: number;
        currency: string;
    };
};

// One ad variant inside a plan (planner._variants).
export type AdVariant = {
    variant_id: string;
    headline: string;
    primary_text: string;
    description: string;
    state: string;
};

// The CampaignPlan payload (planner.plan_campaign).
export type AdsPlan = {
    name: string;
    objective: string; // OUTCOME_LEADS | OUTCOME_SALES | ...
    provider: string; // meta | google | noop
    audience?: Record<string, unknown>;
    geo?: string[];
    creatives?: AdVariant[];
    copy?: {
        headlines?: string[];
        primary_texts?: string[];
        descriptions?: string[];
        _source?: string;
        [k: string]: unknown;
    };
    budget_daily_minor?: number;
    caps?: Record<string, number>;
    bid_strategy?: string;
    [k: string]: unknown;
};

// A persisted campaign record (store.upsert rec shape).
export type AdsCampaign = {
    plan_id: string;
    org_id: string;
    provider: string;
    name: string;
    objective: string;
    plan: AdsPlan;
    status: AdsStatus;
    campaign_ref: string;
    daily_cap_minor: number;
    lifetime_cap_minor: number;
    cpl_max_minor: number;
    approved_by?: string;
    approved_ts?: number | null;
    spend_today_minor: number;
    spend_life_minor: number;
    last_cpl_minor?: number | null;
    last_polled_ts?: number | null;
    pause_reason?: string;
};

// GET /ads/campaigns (service.status, no plan_id).
export type AdsStatusResponse = {
    ok: boolean;
    config: AdsHealth;
    campaigns: AdsCampaign[];
    count: number;
    spend_today_minor: number;
    org_daily_cap_minor: number;
};

// POST /ads/optimize (service.optimize).
export type OptimizeMove = {
    plan_id: string;
    move: "hold" | "kill_loser" | "scale_winner" | string;
    reason: string;
    cpl_minor?: number;
};
export type OptimizeResponse = { ok: boolean; dry_run: boolean; moves: OptimizeMove[] };

// The brief a propose request carries (planner.plan_campaign reads these).
export type AdsBrief = {
    name?: string;
    product?: string;
    objective?: string; // leads | sales | traffic | awareness | engagement
    audience?: Record<string, unknown>;
    geo?: string[];
    budget_daily_minor?: number;
    variants?: number;
    caps?: Record<string, number>;
};

// The objective enum the planner understands (planner._OBJECTIVE_MAP keys).
export const ADS_OBJECTIVES = ["leads", "sales", "traffic", "awareness", "engagement"] as const;
export type AdsObjective = (typeof ADS_OBJECTIVES)[number];

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
        // Network / not-deployed — treat as dormant, not a hard error.
        return { kind: "dormant", reason: "unreachable" };
    }
    handle401(res);
    // 404 (router not mounted) or 501/503 (feature off / auth seam absent) => dormant.
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

async function write<T>(path: string, body: Record<string, unknown>, headers?: HeadersInit): Promise<T> {
    const res = await fetch(`${BASE}${path}`, {
        method: "POST",
        headers: { ...authHeaders(), "Content-Type": "application/json", ...(headers || {}) },
        body: JSON.stringify(body),
    });
    handle401(res);
    if (res.status === 404 || res.status === 501 || res.status === 503) {
        throw new Error("This action is not available yet — the Ads engine backend is not configured.");
    }
    if (!res.ok) {
        let msg = `Action failed (${res.status})`;
        if (res.status === 403)
            msg = "You do not have permission to do that, or this action needs a step-up PIN.";
        try {
            const b = await res.json();
            if (b && typeof b.detail === "string") msg = b.detail;
            else if (b && typeof b.error === "string") msg = b.error;
        } catch {
            /* non-JSON */
        }
        throw new Error(msg);
    }
    return res.json();
}

/* --------------------------------------------------- public reads (never throw) */

export const getAdsHealth = () => read<AdsHealth>("/ads/health");
export const getAdsCampaigns = () => read<AdsStatusResponse>("/ads/campaigns");

/* ------------------------------------------ public mutations (throw friendly) */

export type ProposeResponse = { ok: boolean; status: AdsStatus; plan_id: string; plan: AdsPlan };
export const proposeCampaign = (brief: AdsBrief) =>
    write<ProposeResponse>("/ads/campaigns/propose", { brief });

// Approve & launch. In the dormant deployment there is NO step-up token seam, so
// the backend's fail-closed gate returns `blocked_not_approved` — the page
// surfaces that honestly rather than faking a launch. The X-Step-Up header is
// passed through when a token is available (future: a real step-up handshake).
export type ApproveResponse = {
    ok: boolean;
    status: AdsStatus;
    plan_id: string;
    reason?: string;
    campaign_ref?: string;
    spending?: boolean;
};
export const approveCampaign = (planId: string, stepUpToken?: string) =>
    write<ApproveResponse>(
        `/ads/campaigns/${encodeURIComponent(planId)}/approve`,
        {},
        stepUpToken ? { "X-Step-Up": stepUpToken } : undefined,
    );

export type PauseResponse = { ok: boolean; status: AdsStatus; plan_id: string; already?: boolean };
export const pauseCampaign = (planId: string, reason = "manual_pause") =>
    write<PauseResponse>(`/ads/campaigns/${encodeURIComponent(planId)}/pause`, { reason });

export const runOptimize = (dryRun = true) =>
    write<OptimizeResponse>("/ads/optimize", { dry_run: dryRun });

/* ------------------------------------------------------------------ helpers */

// minor units (paise) -> "₹1,500". `0` and unset render as "—" via the caller.
export function fmtMoney(minor?: number | null, currency = "INR"): string {
    if (minor === null || minor === undefined) return "—";
    const major = minor / 100;
    const symbol = currency === "INR" ? "₹" : currency === "USD" ? "$" : "";
    try {
        return `${symbol}${major.toLocaleString(undefined, {
            minimumFractionDigits: major % 1 === 0 ? 0 : 2,
            maximumFractionDigits: 2,
        })}`;
    } catch {
        return `${symbol}${major}`;
    }
}

export function fmtTs(ts?: number | null): string {
    if (!ts) return "—";
    try {
        return new Date(ts * 1000).toLocaleString();
    } catch {
        return "—";
    }
}
