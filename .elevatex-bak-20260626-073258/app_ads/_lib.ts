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
//
// W7.0 EXTENSION: the additive read/write helpers for the new ad-engine sub-paths
// (analytics / decisions / guardrails / leads / consent / creative) + a tiny
// page-level realtime hook are appended below. The 6 core fns above remain
// BYTE-STABLE — every later wave only imports the new helpers, never edits these.

import { useEffect } from "react";

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

/* ================================================================= W7.0 ADD
 *
 * Additive read/write helpers for the deferred ad-engine sub-paths
 * (ARCHITECTURE.md §4). All reuse `read`/`write` above, so they inherit the
 * SAME auth (`X-Auth`), 401→/login handler, dormant degradation (404/501/503 →
 * {kind:"dormant"} on reads), and friendly throw + step-up 403 copy on writes.
 * Money stays `_minor` (paise) end-to-end. None of the 6 core fns change.
 * =========================================================================== */

// Build a `?k=v` query string from a flat filter bag (drops empty values). Used
// by every read helper that takes filters so dormant routes still 404 cleanly.
function qs(filters?: Record<string, string | number | undefined | null>): string {
    if (!filters) return "";
    const parts: string[] = [];
    for (const [k, v] of Object.entries(filters)) {
        if (v === undefined || v === null || v === "") continue;
        parts.push(`${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`);
    }
    return parts.length ? `?${parts.join("&")}` : "";
}

type Filters = Record<string, string | number | undefined | null>;

/* ----------------------------------------------------------------- analytics */

// The four analytics sub-paths the engine exposes. Each returns its own shape;
// callers pass the kind + filters (range/campaign/platform) and get a dormant-
// safe ReadResult back. Shapes are intentionally loose (Record) at W7.0 — the
// Analytics + Command waves narrow them when they render.
export type AdsAnalyticsKind = "funnel" | "per-ad" | "per-platform" | "real-vs-reported";

export type AdsAnalyticsResponse = {
    kind?: string;
    rows?: Array<Record<string, unknown>>;
    funnel?: Array<{ stage: string; count: number; pct_of_top: number; step_conv: number }>;
    totals?: Record<string, number>;
    [k: string]: unknown;
};

export const getAdsAnalytics = (kind: AdsAnalyticsKind, filters?: Filters) =>
    read<AdsAnalyticsResponse>(`/ads/analytics/${kind}${qs(filters)}`);

/* ------------------------------------------------------------------ decisions */

// One row of the append-only AI decision feed (decision_log.json).
export type AdsDecision = {
    id: string;
    ts: number;
    campaign?: string;
    plan_id?: string;
    decision: string; // scale | realloc | pause | redial | ...
    inputs?: Record<string, unknown>;
    guard_chain?: Array<{ guard: string; result: string }>;
    outcome: string; // auto_applied | needs_approval | blocked_* | ...
    reversible?: boolean;
    revert_ref?: string;
    [k: string]: unknown;
};

export type AdsDecisionsResponse = { ok: boolean; decisions: AdsDecision[]; count?: number };

export const getAdsDecisions = (filters?: Filters) =>
    read<AdsDecisionsResponse>(`/ads/decisions${qs(filters)}`);

/* ----------------------------------------------------------------- guardrails */

// The configurable caps / breaker / approval gate (GET) + the save body (POST).
export type AdsGuardrails = {
    daily_cap_minor: number;
    org_daily_cap_minor: number;
    per_account_cap_minor?: number;
    cpl_max_minor: number;
    cpl_breaker_on: boolean;
    anomaly_breaker_on?: boolean;
    require_approval: boolean;
    no_tracking_gate?: boolean;
    poll_minutes?: number;
    currency?: string;
    // live state echoed back for the spend-vs-cap meters
    spend_today_minor?: number;
    current_cpl_minor?: number | null;
    [k: string]: unknown;
};

export const getAdsGuardrails = () => read<AdsGuardrails>("/ads/guardrails");

// Spend-mutating → step-up gated; passes X-Step-Up when a token is available.
export type SaveGuardrailsResponse = { ok: boolean; guardrails: AdsGuardrails };
export const saveAdsGuardrails = (body: Partial<AdsGuardrails>, stepUpToken?: string) =>
    write<SaveGuardrailsResponse>(
        "/ads/guardrails",
        { ...body },
        stepUpToken ? { "X-Step-Up": stepUpToken } : undefined,
    );

/* ---------------------------------------------------------------------- leads */

// One ad-lead row with its consent + gate decision + call outcome.
export type AdsLead = {
    id: string;
    name?: string;
    phone_masked?: string;
    source?: string; // meta_leadgen | ctwa | form | ...
    consent_status?: string; // dpdp_ok | dca_dlt_ok | blocked_no_consent | ...
    gate_decision?: string; // allowed | blocked_ncpr | blocked_cooloff | ...
    score?: string | number; // hot | warm | cold | numeric
    call_outcome?: string; // booked | qualified | no_answer | ...
    cpl_minor?: number | null;
    campaign?: string;
    ts?: number;
    [k: string]: unknown;
};

export type AdsLeadsResponse = {
    ok: boolean;
    leads: AdsLead[];
    next_cursor?: string | null;
    count?: number;
};

export const getAdsLeads = (cursor?: string | null, filters?: Filters) =>
    read<AdsLeadsResponse>(`/ads/leads${qs({ cursor: cursor || undefined, ...filters })}`);

export const getAdsLead = (id: string) =>
    read<AdsLead>(`/ads/leads/${encodeURIComponent(id)}`);

export type RedialResponse = { ok: boolean; status: string; lead_id: string };
export const redialLead = (id: string, stepUpToken?: string) =>
    write<RedialResponse>(
        `/ads/leads/${encodeURIComponent(id)}/redial`,
        {},
        stepUpToken ? { "X-Step-Up": stepUpToken } : undefined,
    );

// Dead-lead revival — ingest a consented lead list back into the engine. The
// caller MUST attest a signed DPA / lead consent (`dpa_acknowledged`); the backend
// fail-closes if it's absent. `column_map` maps the engine's canonical fields
// (name/phone/email/source/campaign) onto the uploaded columns. `rows` carries
// the parsed records (header + data) or the caller passes raw `csv` text — the
// backend accepts either. Re-contacting prior leads SPENDS dial budget, so this
// is step-up gated (X-Step-Up passed through when a token is available).
export type ImportLeadsResult = {
    ok: boolean;
    imported: number;
    skipped?: number;
    duplicates?: number;
    rejected?: Array<{ row: number; reason: string }>;
    batch_id?: string;
};
export const importLeads = (
    body: {
        dpa_acknowledged: boolean;
        source?: string;
        campaign?: string;
        column_map?: Record<string, string>;
        rows?: Array<Record<string, string>>;
        csv?: string;
    },
    stepUpToken?: string,
) =>
    write<ImportLeadsResult>(
        "/ads/leads/import",
        { ...body },
        stepUpToken ? { "X-Step-Up": stepUpToken } : undefined,
    );

/* -------------------------------------------------------------------- consent */

// The immutable consent ledger snapshot for a lead (hash-chained, read-only).
export type AdsConsentResponse = {
    ok: boolean;
    lead_id: string;
    entries: Array<{
        ts: number;
        kind: string; // dpdp | dca_dlt | revoke | ...
        status: string;
        hash?: string;
        prev_hash?: string;
        [k: string]: unknown;
    }>;
};

export const getAdsConsent = (leadId: string) =>
    read<AdsConsentResponse>(`/ads/consent/${encodeURIComponent(leadId)}`);

export type ConsentMutationResponse = { ok: boolean; lead_id: string; status: string };
export const postConsent = (leadId: string, body: Record<string, unknown>) =>
    write<ConsentMutationResponse>("/ads/consent", { lead_id: leadId, ...body });
export const revokeConsent = (leadId: string, reason = "user_request") =>
    write<ConsentMutationResponse>("/ads/consent/revoke", { lead_id: leadId, reason });

/* ------------------------------------------------------------------- creative */

// An ad-variant generation job + its produced variants with a moderation verdict.
export type CreativeJob = {
    job_id: string;
    state: string; // queued | running | done | failed | ...
    prompt?: string;
    created_ts?: number;
    variant_ids?: string[];
    [k: string]: unknown;
};

export type CreativeVariant = {
    variant_id: string;
    job_id?: string;
    url?: string;
    headline?: string;
    primary_text?: string;
    moderation_status?: string; // pending | approved | blocked | ...
    moderation_reason?: string;
    [k: string]: unknown;
};

export type SubmitCreativeResponse = { ok: boolean; job_id: string; state: string };
export const submitCreative = (body: Record<string, unknown>) =>
    write<SubmitCreativeResponse>("/ads/creative/generate", { ...body });

export const getCreativeJobs = () =>
    read<{ ok: boolean; jobs: CreativeJob[] }>("/ads/creative/jobs");

export const getCreativeVariants = (filters?: Filters) =>
    read<{ ok: boolean; variants: CreativeVariant[] }>(`/ads/creative/variants${qs(filters)}`);

export type ModerateResponse = { ok: boolean; variant_id: string; moderation_status: string };
export const moderateVariant = (
    id: string,
    decision: "approved" | "blocked",
    stepUpToken?: string,
) =>
    write<ModerateResponse>(
        `/ads/creative/variants/${encodeURIComponent(id)}/moderate`,
        { decision },
        stepUpToken ? { "X-Step-Up": stepUpToken } : undefined,
    );

/* ----------------------------------------------------------- realtime refresh */

// Visibility-gated polling — the verified app/analytics/page.tsx:128-141 idiom.
// Fires `load` on an interval ONLY while the tab is visible, and re-loads on
// focus; cleans up on unmount. This is the page-level realtime spine every tab
// shares (the page also keeps its manual Refresh button). Pass a `useCallback`-
// stable `load` so the interval isn't torn down every render.
export function useRealtimeRefresh(load: () => void, intervalMs = 30000): void {
    useEffect(() => {
        const t = setInterval(() => {
            if (typeof document === "undefined" || document.visibilityState === "visible") load();
        }, intervalMs);
        const onVis = () => {
            if (document.visibilityState === "visible") load();
        };
        if (typeof document !== "undefined") document.addEventListener("visibilitychange", onVis);
        return () => {
            clearInterval(t);
            if (typeof document !== "undefined")
                document.removeEventListener("visibilitychange", onVis);
        };
    }, [load, intervalMs]);
}
