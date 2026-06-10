"use client";

// Self-contained API client + static funnel knowledge for the Funnels page.
//
// WHY local (not lib/api.ts): the /funnels router is DEFINED-NOT-MOUNTED on the
// backend today (REMAINING_MODULES_BUILD_STATE.md §8 — it needs a token-deriving
// build_router before it can be mounted safely). So every endpoint 404s until
// the deferred wiring lands. Rather than couple the shared api module to a
// dormant surface (and risk a parallel session editing it), this page owns its
// own thin client. It mirrors lib/api.ts auth EXACTLY: BASE = NEXT_PUBLIC_API_BASE
// || "/api", `X-Auth` header from localStorage `famit_token`, 401 -> /login.
//
// Reads treat a non-200 as DORMANCY (the page renders a premium "not configured
// / coming soon" state) — they never throw. Mutations DO throw a friendly
// message so the form can surface it. Writes send a JSON body (the funnels
// build_router does `await request.json()`), NOT FormData.
//
// The stage pipeline + starter templates are embedded as STATIC, cred-free
// constants (re-declared from droplet_work/funnels/stages.py + templates.py).
// This is pure knowledge — it lets the dormant state render a rich, educational
// pipeline + template gallery instead of an empty wall, with any live data
// overlaid on top when the backend lights up.

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

/* ------------------------------------------------------------------ types */

// The 8 canonical funnel stages, in order (mirrors stages.CANONICAL_STAGES).
export type StageKey =
    | "ad"
    | "landing"
    | "lead"
    | "call"
    | "whatsapp"
    | "booking"
    | "payment"
    | "review";

// Static per-stage knowledge (mirrors stages.STAGE_MAP). `placeholder` = the
// sibling module isn't built yet (compiles to an inert marker node).
export type StageMeta = {
    key: StageKey;
    display: string;
    blurb: string;
    icon: string;
    money: boolean; // moves external money -> auto budget + approval gate
    bulk: boolean; // bulk/destructive -> requires a budget dominator
    placeholder: boolean; // dormant-until-sibling-module
    compilesTo: string; // the workflow DSL node it lowers to
    accent: string; // css var for the stage accent
};

export const STAGES: StageMeta[] = [
    {
        key: "ad",
        display: "Ad spend",
        blurb: "Set and govern paid-ad budget. Money — auto-gated by a budget cap + human approval.",
        icon: "promote",
        money: true,
        bulk: false,
        placeholder: false,
        compilesTo: "integration · ads.set_budget",
        accent: "var(--primary-01)",
    },
    {
        key: "landing",
        display: "Landing page",
        blurb: "Drive traffic to a hosted landing page. Lights up when the Website module ships.",
        icon: "desktop",
        money: false,
        bulk: false,
        placeholder: true,
        compilesTo: "data · placeholder marker",
        accent: "var(--primary-02)",
    },
    {
        key: "lead",
        display: "Lead capture",
        blurb: "The funnel entry — a new lead or a submitted form starts every run.",
        icon: "profile",
        money: false,
        bulk: false,
        placeholder: false,
        compilesTo: "trigger · lead.created / form.submitted",
        accent: "var(--primary-03)",
    },
    {
        key: "call",
        display: "AI voice call",
        blurb: "An AI telecaller dials the lead. Bulk — gated by a budget dominator.",
        icon: "mobile",
        money: false,
        bulk: true,
        placeholder: false,
        compilesTo: "ai_agent · leads.enqueue_calls",
        accent: "var(--primary-04)",
    },
    {
        key: "whatsapp",
        display: "WhatsApp follow-up",
        blurb: "Send a templated WhatsApp nudge. Bulk — gated by a budget dominator.",
        icon: "chat",
        money: false,
        bulk: true,
        placeholder: false,
        compilesTo: "action · whatsapp.send",
        accent: "var(--primary-05)",
    },
    {
        key: "booking",
        display: "Booking",
        blurb: "Durable pause until the lead books — the engine waits on booking.made.",
        icon: "calendar",
        money: false,
        bulk: false,
        placeholder: false,
        compilesTo: "wait · booking.made",
        accent: "var(--primary-02)",
    },
    {
        key: "payment",
        display: "Payment",
        blurb: "Durable pause until paid — the engine waits on payment.received.",
        icon: "wallet",
        money: false,
        bulk: false,
        placeholder: false,
        compilesTo: "wait · payment.received",
        accent: "var(--primary-04)",
    },
    {
        key: "review",
        display: "Review request",
        blurb: "Ask the happy customer for a review. Lights up when the Reviews module ships.",
        icon: "heart",
        money: false,
        bulk: false,
        placeholder: true,
        compilesTo: "data · placeholder marker",
        accent: "var(--primary-01)",
    },
];

export const STAGE_BY_KEY: Record<string, StageMeta> = Object.fromEntries(
    STAGES.map((s) => [s.key, s])
);

// Starter templates (mirrors templates._TEMPLATES — id/name/pack/stage list).
export type FunnelTemplate = {
    id: string;
    name: string;
    industry_pack: string;
    blurb: string;
    stages: StageKey[];
};

export const STARTER_TEMPLATES: FunnelTemplate[] = [
    {
        id: "real_estate_site_visit",
        name: "Real-estate site-visit funnel",
        industry_pack: "real_estate",
        blurb: "The full loop — paid ad to landing page to AI call to WhatsApp nudge to booked site-visit, payment and a review request.",
        stages: ["ad", "landing", "lead", "call", "whatsapp", "booking", "payment", "review"],
    },
    {
        id: "clinic_appointment",
        name: "Clinic appointment funnel",
        industry_pack: "healthcare",
        blurb: "Lead to AI confirmation call to WhatsApp reminder to a booked appointment, then a review request — no ad spend.",
        stages: ["lead", "call", "whatsapp", "booking", "review"],
    },
    {
        id: "lead_to_call_nurture",
        name: "Lead → call → WhatsApp nurture",
        industry_pack: "generic",
        blurb: "The lean nurture — every new lead gets an AI call and a WhatsApp follow-up. The fastest funnel to ship.",
        stages: ["lead", "call", "whatsapp"],
    },
];

// ---- live record shapes (match the backend 1:1) ----

export type FunnelStatusIntegration = "configured" | "not_configured" | string;

export type FunnelStatus = {
    module: string;
    config: {
        module: string;
        store_mode: string;
        killswitch: boolean;
        workflow_engine_present: boolean;
        integrations: {
            landing_publish: FunnelStatusIntegration;
            review_request: FunnelStatusIntegration;
        };
        engine: Record<string, unknown>;
    };
    tools: Record<string, unknown>;
    store: string;
    workflow_engine: { status?: string; [k: string]: unknown };
    stages: string[];
    templates: number;
};

export type FunnelRow = {
    funnel_id: string;
    tenant_id: string;
    name: string;
    status: "draft" | "published" | string;
    industry_pack: string;
    workflow_id: string;
    current_version: number;
    // present on the in-memory backend listing only:
    spec?: { stages?: ({ stage: string } | string)[]; guards?: Record<string, unknown> };
    created_at?: string;
    updated_at?: string;
};

export type FunnelStageAnalytics = {
    stage: string;
    display: string;
    node_id: string;
    reached: number;
    spend_minor: number;
    placeholder: boolean;
    conversion_from_prev?: number;
};

export type FunnelAnalytics = {
    funnel_id: string;
    name: string;
    stages: FunnelStageAnalytics[];
    entered: number;
    converted: number;
    overall_conversion: number;
    drop_off: { from_stage: string; to_stage: string; conversion: number } | null;
    runs: Record<string, number>;
    spend_minor_total: number;
};

// Discriminated read result: ok | dormant (endpoint missing/404/disabled) | error.
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
    // 404 (router not mounted) or 501/503 (feature off) => dormant, render coming-soon.
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
        throw new Error("This action is not available yet — the Funnels backend is not configured.");
    }
    if (!res.ok) {
        let msg = `Action failed (${res.status})`;
        if (res.status === 403)
            msg = "You don't have permission to do that, or this action needs a step-up PIN.";
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

// ---- public reads (never throw) ----
// NOTE: no trailing slash on the list path (avoids a 307 redirect).
export const getFunnelStatus = () => read<FunnelStatus>("/funnels/status");
export const getFunnels = () => read<{ funnels: FunnelRow[] }>("/funnels");
export const getFunnelAnalytics = (id: string) =>
    read<FunnelAnalytics>(`/funnels/${encodeURIComponent(id)}/analytics`);

// ---- public mutations (throw friendly on failure) ----
export const instantiateTemplate = (templateId: string, name?: string) =>
    write<{ ok: boolean; funnel_id?: string; reason?: string }>(
        `/funnels/templates/${encodeURIComponent(templateId)}/instantiate`,
        name ? { name } : {}
    );

export const createFunnel = (body: {
    name: string;
    stages: ({ stage: StageKey } | StageKey)[];
    industry_pack?: string;
    guards?: Record<string, unknown>;
}) => write<{ ok: boolean; funnel_id?: string; reason?: string }>("/funnels", body);

export const publishFunnel = (id: string) =>
    write<{ ok: boolean; reason?: string; errors?: string[]; version?: number }>(
        `/funnels/${encodeURIComponent(id)}/publish`,
        {}
    );

export const runFunnel = (id: string) =>
    write<{ ok: boolean; reason?: string; run_id?: string; status?: string }>(
        `/funnels/${encodeURIComponent(id)}/run`,
        {}
    );

/* ---------------------------------------------------------------- helpers */

export function stageMeta(key: string): StageMeta | undefined {
    return STAGE_BY_KEY[key];
}

// Pull the ordered stage-key list out of a funnel row's spec (best-effort —
// the in-memory backend returns the spec; the PG listing does not).
export function rowStages(row: FunnelRow): StageKey[] {
    const raw = row.spec?.stages || [];
    const keys = raw
        .map((s) => (typeof s === "string" ? s : s.stage))
        .filter((k): k is StageKey => !!STAGE_BY_KEY[k]);
    return keys;
}

export function fmtDate(d?: string): string {
    if (!d) return "—";
    try {
        return new Date(d).toLocaleDateString(undefined, {
            month: "short",
            day: "numeric",
            year: "numeric",
        });
    } catch {
        return d;
    }
}
