"use client";

// Self-contained API client for the Haptica Grow command-center page (/grow).
//
// WHY local (not lib/api.ts): the /grow router is FLAG-GATED (FEATURE_GROW) and
// dormant-until-enabled on the backend — every endpoint 404s until it's mounted.
// Rather than couple the shared api module to a dormant surface (and risk a
// parallel session editing it), this page owns its own thin client. It mirrors
// lib/api.ts auth EXACTLY: BASE = NEXT_PUBLIC_API_BASE || "/api", `X-Auth` header
// from localStorage `famit_token`, 401 -> /login.
//
// Reads treat a non-200 as DORMANCY (the page renders a premium "not configured"
// state) — they never throw. The score "try-it" write throws a friendly message.
// Shapes match grow.model.*.public() 1:1 (the backend's PII-safe response dicts).

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

// The five L5 tiers (grow.model.LeadTier).
export type LeadTier = "hot" | "warm" | "investor" | "end_user" | "junk" | string;

// The CAPI dispatch status (grow.model.SignalStatus).
export type SignalStatus = "shadow" | "queued" | "sent" | "acked" | "failed" | "deduped" | string;

// GET /grow/health = GrowConfig.status() + an embedded signal_health card.
export type GrowHealth = {
    enabled: boolean;
    pack: string;
    thresholds: { hot: number; warm: number; junk: number };
    signals: {
        shadow_mode: boolean;
        meta_live: boolean;
        google_live: boolean;
        meta_configured: boolean;
        meta_test_mode: boolean;
        google_configured: boolean;
    };
    signal_health: SignalHealth;
};

// GET /grow/signals/health (also embedded in /grow/health).
export type SignalHealth = {
    total: number;
    unique: number;
    by_status: Record<string, number>;
    ladder_coverage: Record<string, number>;
    avg_emq_estimate: number;
    dedup_rate: number;
    click_id_coverage: number;
    live_dispatched: number;
    shadow_dispatched: number;
    failed: number;
    mode: "shadow" | "live" | string;
};

// One scored lead (grow.model.ScoredLead.public()).
export type ScoredLead = {
    lead_id: string;
    journey_id: string;
    phone_masked: string;
    score: number;
    tier: LeadTier;
    confidence: number;
    reasons: string[];
    sales_ready: boolean;
    model: string;
    source_platform: string;
    scored_at: string | null;
};

// One CAPI dispatch-ledger row (grow.model.SignalEvent.public()).
export type SignalEvent = {
    event_id: string;
    journey_id: string;
    lead_id: string;
    platform: string;
    endpoint: string;
    event_name: string; // Lead | QualifiedLead | Schedule | Attended | Purchase
    value: number;
    currency: string;
    match_keys: string[];
    status: SignalStatus;
    emq_estimate: number;
    reason: string;
    dispatched_at: string | null;
};

// One journey (grow.model.Journey.public()).
export type Journey = {
    journey_id: string;
    phone_masked: string;
    source_platform: string;
    source_ad_id: string;
    has_ctwa: boolean;
    has_click_id: boolean;
    status: string;
    first_touch_at: string | null;
    updated_at: string | null;
};

export type LeadsResponse = { leads: ScoredLead[]; count: number };
export type SignalsResponse = { signals: SignalEvent[]; count: number };
export type JourneysResponse = { journeys: Journey[]; count: number };

// L8 funnel + ROI (grow.metrics.*)
export type FunnelStage = {
    key: string; label: string; count: number;
    of_captured: number; step_rate: number | null;
};
export type Funnel = { stages: FunnelStage[]; captured: number; qualified: number; booked: number; won: number };
export type Sla = {
    runs: number; fired: number; sla_met: number; sla_met_rate: number;
    avg_latency_ms: number; p50_latency_ms: number; p95_latency_ms: number;
};
export type Roi = {
    currency: string; spend_minor: number; spend_connected: boolean;
    leads: number; qualified: number; booked: number; won: number;
    cpl_minor: number; cpql_minor: number; cost_per_booking_minor: number;
    cost_per_won_minor: number; north_star: string;
};
export type GrowSummary = {
    funnel: Funnel;
    tier_distribution: Record<string, number>;
    by_source: Record<string, { leads: number; qualified: number }>;
    sla: Sla;
    roi: Roi;
    signal_health: SignalHealth;
};

// The "try-it" scorer request (a subset of grow.model.ScoringInput).
export type ScoreInput = {
    phone?: string;
    name?: string;
    source_platform?: string;
    phone_valid?: boolean;
    call_answered?: boolean;
    call_duration_s?: number;
    interest_score?: number;
    budget_mentioned?: boolean;
    timeline_mentioned?: boolean;
    decision_authority?: boolean;
    site_visit_ready?: boolean;
    booking_made?: boolean;
    investor_intent?: boolean;
    end_user_intent?: boolean;
    last_outcome?: string;
    wa_replied?: boolean;
    wa_depth?: number;
};

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
    // 404 (router not mounted / FEATURE_GROW off) or 501/503 => dormant.
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
        throw new Error("Grow is not enabled yet — set FEATURE_GROW=1 on the backend.");
    }
    if (!res.ok) {
        let msg = `Action failed (${res.status})`;
        if (res.status === 403) msg = "You do not have permission to do that.";
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

export const getGrowHealth = () => read<GrowHealth>("/grow/health");
export const getGrowLeads = (q: { tier?: string; sales_ready?: boolean } = {}) => {
    const p = new URLSearchParams();
    if (q.tier) p.set("tier", q.tier);
    if (q.sales_ready) p.set("sales_ready", "1");
    const qs = p.toString();
    return read<LeadsResponse>(`/grow/leads${qs ? `?${qs}` : ""}`);
};
export const getGrowSignals = (journeyId?: string) =>
    read<SignalsResponse>(`/grow/signals/log${journeyId ? `?journey_id=${encodeURIComponent(journeyId)}` : ""}`);
export const getGrowJourneys = () => read<JourneysResponse>("/grow/journeys");
export const getGrowSummary = (spendMinor = 0) =>
    read<GrowSummary>(`/grow/summary${spendMinor > 0 ? `?spend_minor=${spendMinor}` : ""}`);

/* ------------------------------------------ public mutation (throws friendly) */

export const scoreLeadPreview = (input: ScoreInput) => write<ScoredLead>("/grow/score", input);

/* ------------------------------------------------------------------ helpers */

export function tierVariant(t: LeadTier): "success" | "warning" | "info" | "danger" | "neutral" {
    if (t === "hot") return "success";
    if (t === "investor") return "info";
    if (t === "warm") return "warning";
    if (t === "end_user") return "neutral";
    return "danger"; // junk
}

export function tierLabel(t: LeadTier): string {
    const map: Record<string, string> = {
        hot: "Hot", warm: "Warm", investor: "Investor", end_user: "End-user", junk: "Junk",
    };
    return map[t] || t;
}

export function signalStatusVariant(s: SignalStatus): "success" | "warning" | "info" | "danger" | "neutral" {
    if (s === "acked" || s === "sent") return "success";
    if (s === "shadow" || s === "queued") return "info";
    if (s === "deduped") return "neutral";
    if (s === "failed") return "danger";
    return "neutral";
}

export function signalStatusLabel(s: SignalStatus): string {
    const map: Record<string, string> = {
        shadow: "Shadow", queued: "Queued", sent: "Sent", acked: "Acked",
        failed: "Failed", deduped: "Deduped",
    };
    return map[s] || s;
}

// "919876543210"-style reasons -> a clean human chip label, e.g.
// "budget_mentioned(+18)" -> "Budget mentioned +18".
export function prettyReason(r: string): string {
    const m = r.match(/^([a-z0-9_]+)\(([^)]*)\)$/i);
    const base = (m ? m[1] : r).replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());
    const delta = m && m[2] ? ` ${m[2].replace(/^\+?/, "+").replace("++", "+")}` : "";
    return (base + delta).replace(/\s+\+/, " +").trim();
}

export function fmtTs(ts?: string | null): string {
    if (!ts) return "—";
    try {
        return new Date(ts).toLocaleString();
    } catch {
        return "—";
    }
}

export function fmtPct(x?: number | null): string {
    if (x === null || x === undefined) return "—";
    return `${Math.round(x * 100)}%`;
}

// minor units (paise) -> "₹1,200". 0/unset -> "—".
export function fmtMoney(minor?: number | null, currency = "INR"): string {
    if (!minor) return "—";
    const major = minor / 100;
    const sym = currency === "INR" ? "₹" : currency === "USD" ? "$" : "";
    try {
        return `${sym}${major.toLocaleString(undefined, {
            minimumFractionDigits: major % 1 === 0 ? 0 : 2, maximumFractionDigits: 2,
        })}`;
    } catch {
        return `${sym}${major}`;
    }
}
