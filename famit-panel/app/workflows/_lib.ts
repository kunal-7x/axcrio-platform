"use client";

// Self-contained API client + domain model for the Workflow Studio page.
//
// WHY local (not lib/api.ts): the /workflows router is DEFINED-NOT-MOUNTED on the
// backend today (the durable Hatchet interpreter + the 6 Postgres tables + the
// additive APIRouter all ship behind a deferred, un-applied wiring diff). Every
// endpoint 404s until that wiring + creds land. Rather than couple the shared api
// module to a dormant surface (and risk a parallel session editing it), this page
// owns its own thin client. It mirrors lib/api.ts auth EXACTLY: BASE =
// NEXT_PUBLIC_API_BASE || "/api", `X-Auth` header from localStorage `famit_token`,
// 401 -> bounce to /login.
//
// The list/status reads treat a non-200 as DORMANCY (the page renders a premium
// "not configured / coming soon" state) — they never throw. Mutations DO throw a
// friendly message so the UI can surface it.
//
// This file also ships the STATIC product artifacts the canvas renders while the
// engine is dormant: the §3 DSL sample workflow + a small industry-pack template
// library. These are real product definitions (the spec's template library), NOT
// fabricated runtime metrics — the canvas is an honest preview of the studio, and
// every "live" count/stat degrades to an honest zero / "coming soon".

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
        // The whole page is auth-gated by Layout; a true 401 means the session
        // expired. Mirror lib/api.ts and bounce to login.
        localStorage.removeItem("famit_token");
        localStorage.removeItem("famit_me");
        window.location.href = "/login";
        throw new Error("Unauthorized");
    }
}

/* ============================================================ DOMAIN TYPES */

// The 10 hard-spec node types (design/platform-workflow-studio.md §4).
export type WfNodeType =
    | "trigger"
    | "condition"
    | "ai_agent"
    | "action"
    | "budget"
    | "approval"
    | "delay"
    | "data"
    | "integration"
    | "error";

export type WfNode = {
    node_id: string;
    type: WfNodeType;
    label?: string;
    role?: string; // ai_agent: which workforce persona
    config?: Record<string, unknown>;
    money?: boolean;
    on_error?: string;
    // Canvas layout (studio-authored; not part of execution semantics).
    x: number;
    y: number;
};

export type WfEdge = {
    from: string;
    to: string;
    when?: "true" | "false"; // condition branch label
    error?: boolean; // on_error edge
};

export type WfGuards = {
    max_actions: number;
    calling_window: string;
    respect_dnd: boolean;
    respect_consent: boolean;
    kill_switch: boolean;
};

export type WfDefinition = {
    schema_version: number;
    workflow_id: string;
    tenant_id?: string;
    name: string;
    version: number;
    status: "draft" | "published" | "archived";
    industry_pack?: string;
    trigger: WfNode;
    nodes: WfNode[];
    edges: WfEdge[];
    guards: WfGuards;
    updated_at?: string;
};

export type WfRunStatus =
    | "queued"
    | "running"
    | "awaiting_approval"
    | "sleeping"
    | "completed"
    | "failed"
    | "killed";

export type WfRun = {
    run_id: string;
    workflow_id: string;
    workflow_name?: string;
    version: number;
    trigger_kind?: string;
    status: WfRunStatus;
    started_at?: string;
    ended_at?: string;
    steps?: number;
    spend_minor?: number;
};

export type WfStatus = {
    module: string;
    enabled: boolean;
    // Each dependency reports configured / not_configured — the dormant story.
    engine: "configured" | "not_configured" | string; // Hatchet durable spine
    store: "configured" | "not_configured" | string; // Postgres + RLS tables
    wallet: "configured" | "not_configured" | string; // BUDGET node ledger
    firewall: "configured" | "not_configured" | string; // APPROVAL step-up
    audit: "configured" | "not_configured" | string; // immutable audit log
    registry: "configured" | "not_configured" | string; // AI-Manager tool registry
    llm_provider?: string; // AI-Agent reasoning (dormant -> deterministic default)
    workflows_total?: number;
    published_total?: number;
    runs_total?: number;
};

// A template = a publishable starter workflow (the industry-pack library).
export type WfTemplate = {
    template_id: string;
    name: string;
    industry_pack: string;
    summary: string;
    icon: string;
    node_count: number;
    has_money: boolean;
    has_approval: boolean;
    definition: WfDefinition;
};

/* ----------------------------------------- node-type display metadata (static) */

export type NodeMeta = {
    type: WfNodeType;
    label: string;
    icon: string;
    group: "Flow" | "Workforce" | "Safety" | "Data";
    accent: string; // a CSS var for the node accent
    blurb: string;
    side_effecting: boolean;
    money: boolean;
    gate: string;
};

export const NODE_META: Record<WfNodeType, NodeMeta> = {
    trigger: {
        type: "trigger",
        label: "Trigger",
        icon: "send",
        group: "Flow",
        accent: "var(--primary-01)",
        blurb: "The entry point — manual, schedule, event or webhook fires a run.",
        side_effecting: false,
        money: false,
        gate: "none",
    },
    condition: {
        type: "condition",
        label: "Condition",
        icon: "filters",
        group: "Flow",
        accent: "var(--primary-02)",
        blurb: "Branch on a sandboxed boolean expression — no side effect.",
        side_effecting: false,
        money: false,
        gate: "none",
    },
    delay: {
        type: "delay",
        label: "Delay / Wait",
        icon: "clock",
        group: "Flow",
        accent: "var(--primary-05)",
        blurb: "Durable real-time sleep or wait-for-event — survives restarts.",
        side_effecting: false,
        money: false,
        gate: "none",
    },
    ai_agent: {
        type: "ai_agent",
        label: "AI Agent",
        icon: "magic-pencil",
        group: "Workforce",
        accent: "var(--primary-03)",
        blurb: "Delegate to an AI-workforce role reading the Business Brain + KB.",
        side_effecting: true,
        money: false,
        gate: "credit + audit",
    },
    action: {
        type: "action",
        label: "Action",
        icon: "feather",
        group: "Workforce",
        accent: "var(--primary-04)",
        blurb: "One deterministic registry tool call, gated by its own metadata.",
        side_effecting: true,
        money: false,
        gate: "credit + audit",
    },
    integration: {
        type: "integration",
        label: "Integration",
        icon: "link",
        group: "Workforce",
        accent: "var(--primary-01)",
        blurb: "A dormant-until-creds external adapter — ads, email, BSP, calendar.",
        side_effecting: true,
        money: false,
        gate: "BUDGET + audit",
    },
    budget: {
        type: "budget",
        label: "Budget",
        icon: "wallet",
        group: "Safety",
        accent: "var(--primary-02)",
        blurb: "Reserves a run-scoped wallet hold — money nodes settle against it.",
        side_effecting: false,
        money: false,
        gate: "reserves the hold",
    },
    approval: {
        type: "approval",
        label: "Approval",
        icon: "lock",
        group: "Safety",
        accent: "var(--primary-05)",
        blurb: "Pauses for a PIN-verified human step-up before any spend over cap.",
        side_effecting: false,
        money: false,
        gate: "firewall step-up",
    },
    error: {
        type: "error",
        label: "Error Handling",
        icon: "info",
        group: "Safety",
        accent: "var(--primary-03)",
        blurb: "Catches failures — notify, hand over to a human, retry or terminate.",
        side_effecting: false,
        money: false,
        gate: "audit",
    },
    data: {
        type: "data",
        label: "Data / Memory",
        icon: "cube",
        group: "Data",
        accent: "var(--primary-02)",
        blurb: "Reads / writes the run data bag and Business Brain memory.",
        side_effecting: true,
        money: false,
        gate: "audit",
    },
};

// Ordered palette groups for the node library rail.
export const NODE_GROUPS: { group: NodeMeta["group"]; types: WfNodeType[] }[] = [
    { group: "Flow", types: ["trigger", "condition", "delay"] },
    { group: "Workforce", types: ["ai_agent", "action", "integration"] },
    { group: "Safety", types: ["budget", "approval", "error"] },
    { group: "Data", types: ["data"] },
];

export function nodeMeta(t: WfNodeType): NodeMeta {
    return NODE_META[t] || NODE_META.action;
}

/* ----------------------------------------------- the §3 reference sample DSL */

// A concrete, on-spec sample (the design doc §3 "Hot-lead 5-touch nurture") used
// to render the canvas as a premium preview while the engine is dormant. Layout
// coordinates are studio metadata. This is a product artifact, not fake metrics.
export const SAMPLE_WORKFLOW: WfDefinition = {
    schema_version: 1,
    workflow_id: "wf_sample_hotlead",
    name: "Hot-lead 5-touch nurture",
    version: 7,
    status: "published",
    industry_pack: "real_estate",
    trigger: {
        node_id: "n_trigger",
        type: "trigger",
        label: "New hot lead",
        config: { trigger_kind: "lead.created", segment: "hot" },
        x: 40,
        y: 200,
    },
    nodes: [
        {
            node_id: "n_budget",
            type: "budget",
            label: "Cap ₹2,000 / run",
            config: { cap_inr: 2000, window: "run", on_exceed: "park_for_approval" },
            x: 260,
            y: 200,
        },
        {
            node_id: "n_call",
            type: "ai_agent",
            label: "AI telecaller",
            role: "ai_telecaller",
            config: { tool: "leads.enqueue_calls", args: { campaign_id: "C2", max: 1 } },
            money: false,
            x: 480,
            y: 200,
        },
        {
            node_id: "n_delay",
            type: "delay",
            label: "Wait 24h",
            config: { after_hours: 24 },
            x: 700,
            y: 200,
        },
        {
            node_id: "n_cond",
            type: "condition",
            label: "Interested?",
            config: { expr: "lead.interest >= 7 && !lead.opted_out" },
            x: 920,
            y: 200,
        },
        {
            node_id: "n_wa",
            type: "action",
            label: "WhatsApp nudge",
            config: { tool: "whatsapp.send", args: { template: "nudge1" } },
            money: false,
            x: 1140,
            y: 90,
        },
        {
            node_id: "n_approval",
            type: "approval",
            label: "Manager approval",
            config: { threshold_inr: 0, require: "pin", role: "manager", timeout_h: 24 },
            x: 1140,
            y: 320,
        },
        {
            node_id: "n_ads",
            type: "integration",
            label: "Boost ad budget",
            config: { tool: "ads.set_budget", args: { daily_inr: 1500 } },
            money: true,
            x: 1360,
            y: 320,
            on_error: "n_err",
        },
        {
            node_id: "n_err",
            type: "error",
            label: "Handover",
            config: { action: "human_handover" },
            x: 1360,
            y: 90,
        },
    ],
    edges: [
        { from: "n_trigger", to: "n_budget" },
        { from: "n_budget", to: "n_call" },
        { from: "n_call", to: "n_delay" },
        { from: "n_delay", to: "n_cond" },
        { from: "n_cond", to: "n_wa", when: "true" },
        { from: "n_cond", to: "n_approval", when: "false" },
        { from: "n_approval", to: "n_ads" },
        { from: "n_ads", to: "n_err", error: true },
    ],
    guards: {
        max_actions: 500,
        calling_window: "09:00-21:00 IST",
        respect_dnd: true,
        respect_consent: true,
        kill_switch: false,
    },
};

/* ----------------------------------------------------- template library (static) */

function tpl(
    id: string,
    name: string,
    pack: string,
    icon: string,
    summary: string,
    def: WfDefinition
): WfTemplate {
    const has_money = def.nodes.some((n) => n.money);
    const has_approval = def.nodes.some((n) => n.type === "approval");
    return {
        template_id: id,
        name,
        industry_pack: pack,
        summary,
        icon,
        node_count: def.nodes.length + 1,
        has_money,
        has_approval,
        definition: def,
    };
}

function defOf(
    name: string,
    pack: string,
    trigger: Omit<WfNode, "x" | "y">,
    nodes: Omit<WfNode, "x" | "y">[],
    edges: WfEdge[]
): WfDefinition {
    // Auto-lay nodes left-to-right in a single lane for the template preview.
    const laidTrigger: WfNode = { ...trigger, x: 40, y: 180 };
    const laidNodes: WfNode[] = nodes.map((n, i) => ({
        ...n,
        x: 260 + i * 210,
        y: 180 + (i % 2 === 0 ? 0 : 0),
    }));
    return {
        schema_version: 1,
        workflow_id: `wf_tpl_${name.toLowerCase().replace(/[^a-z0-9]+/g, "_")}`,
        name,
        version: 1,
        status: "draft",
        industry_pack: pack,
        trigger: laidTrigger,
        nodes: laidNodes,
        edges,
        guards: {
            max_actions: 200,
            calling_window: "09:00-21:00 IST",
            respect_dnd: true,
            respect_consent: true,
            kill_switch: false,
        },
    };
}

export const TEMPLATES: WfTemplate[] = [
    tpl(
        "tpl_hotlead",
        "Hot-lead 5-touch nurture",
        "Real Estate",
        "send",
        "Call a new hot lead, wait, qualify by interest, then WhatsApp-nudge or route to a manager — capped and audited.",
        SAMPLE_WORKFLOW
    ),
    tpl(
        "tpl_missed_call",
        "Missed-call instant callback",
        "Services",
        "reply",
        "When a call is missed, instantly enqueue a callback and send a WhatsApp acknowledgement so no lead goes cold.",
        defOf(
            "Missed-call instant callback",
            "Services",
            { node_id: "n_t", type: "trigger", label: "Call missed", config: { trigger_kind: "call.completed" } },
            [
                { node_id: "n_cb", type: "action", label: "Enqueue callback", config: { tool: "leads.enqueue_calls" } },
                { node_id: "n_wa", type: "action", label: "WhatsApp ack", config: { tool: "whatsapp.send" } },
            ],
            [
                { from: "n_t", to: "n_cb" },
                { from: "n_cb", to: "n_wa" },
            ]
        )
    ),
    tpl(
        "tpl_payment",
        "Payment-received upsell",
        "Commerce",
        "wallet",
        "After a payment lands, thank the customer, wait a week, then trigger a personalised upsell campaign.",
        defOf(
            "Payment-received upsell",
            "Commerce",
            { node_id: "n_t", type: "trigger", label: "Payment received", config: { trigger_kind: "payment.received" } },
            [
                { node_id: "n_data", type: "data", label: "Tag customer", config: {} },
                { node_id: "n_delay", type: "delay", label: "Wait 7 days", config: { after_hours: 168 } },
                { node_id: "n_ai", type: "ai_agent", label: "Upsell strategist", role: "campaign_strategist", config: {} },
            ],
            [
                { from: "n_t", to: "n_data" },
                { from: "n_data", to: "n_delay" },
                { from: "n_delay", to: "n_ai" },
            ]
        )
    ),
    tpl(
        "tpl_winback",
        "Dormant customer win-back",
        "Retention",
        "heart",
        "Re-engage customers who have gone quiet with a budgeted, approval-gated ad boost plus a WhatsApp offer.",
        defOf(
            "Dormant customer win-back",
            "Retention",
            { node_id: "n_t", type: "trigger", label: "90 days quiet", config: { trigger_kind: "schedule" } },
            [
                { node_id: "n_b", type: "budget", label: "Cap ₹1,000", config: { cap_inr: 1000 } },
                { node_id: "n_ap", type: "approval", label: "Approve spend", config: { require: "pin" } },
                { node_id: "n_ads", type: "integration", label: "Retarget ad", money: true, config: { tool: "ads.set_budget" } },
            ],
            [
                { from: "n_t", to: "n_b" },
                { from: "n_b", to: "n_ap" },
                { from: "n_ap", to: "n_ads" },
            ]
        )
    ),
    tpl(
        "tpl_booking",
        "Booking confirmation + reminder",
        "Appointments",
        "calendar",
        "Confirm a new booking, then send a timed reminder before the appointment to cut no-shows.",
        defOf(
            "Booking confirmation + reminder",
            "Appointments",
            { node_id: "n_t", type: "trigger", label: "Booking made", config: { trigger_kind: "booking.made" } },
            [
                { node_id: "n_c", type: "action", label: "Confirm on WhatsApp", config: { tool: "whatsapp.send" } },
                { node_id: "n_d", type: "delay", label: "Until 2h before", config: {} },
                { node_id: "n_r", type: "action", label: "Send reminder", config: { tool: "whatsapp.send" } },
            ],
            [
                { from: "n_t", to: "n_c" },
                { from: "n_c", to: "n_d" },
                { from: "n_d", to: "n_r" },
            ]
        )
    ),
    tpl(
        "tpl_review",
        "Post-service review request",
        "Reputation",
        "star-fill",
        "A day after a job completes, ask happy customers for a review and route unhappy ones to a human.",
        defOf(
            "Post-service review request",
            "Reputation",
            { node_id: "n_t", type: "trigger", label: "Job completed", config: { trigger_kind: "call.completed" } },
            [
                { node_id: "n_d", type: "delay", label: "Wait 1 day", config: { after_hours: 24 } },
                { node_id: "n_cond", type: "condition", label: "Was it positive?", config: { expr: "lead.csat >= 4" } },
                { node_id: "n_ask", type: "action", label: "Request review", config: { tool: "whatsapp.send" } },
                { node_id: "n_err", type: "error", label: "Human follow-up", config: {} },
            ],
            [
                { from: "n_t", to: "n_d" },
                { from: "n_d", to: "n_cond" },
                { from: "n_cond", to: "n_ask", when: "true" },
                { from: "n_cond", to: "n_err", when: "false" },
            ]
        )
    ),
];

/* ============================================================ read result type */

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
    // 404 (router not mounted) or 501/503 (feature off) => dormant, coming-soon.
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
        throw new Error(
            "This action is not available yet — the Workflow Studio engine is not configured on the server."
        );
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

/* ----------------------------------------------------------- public reads */

export const getWfStatus = () => read<WfStatus>("/workflows/status");
export const getWorkflows = () => read<{ workflows: WfDefinition[] }>("/workflows");
export const getWfRuns = (limit = 50) =>
    read<{ runs: WfRun[] }>(`/workflows/runs?limit=${limit}`);
export const getWfTemplates = () => read<{ templates: WfTemplate[] }>("/workflows/templates");

/* ------------------------------------------------------- public mutations */

export const createWorkflow = (body: { name: string; industry_pack?: string }) =>
    write<{ ok: boolean; workflow_id: string }>("/workflows", body);

export const instantiateTemplate = (templateId: string) =>
    write<{ ok: boolean; workflow_id: string }>(
        `/workflows/templates/${encodeURIComponent(templateId)}/instantiate`,
        {}
    );

export const runWorkflow = (id: string) =>
    write<{ ok: boolean; run_id: string }>(`/workflows/${encodeURIComponent(id)}/run`, {});

export const approveRun = (runId: string, pin: string) =>
    write<{ ok: boolean }>(`/workflows/runs/${encodeURIComponent(runId)}/approve`, { pin });

export const rejectRun = (runId: string) =>
    write<{ ok: boolean }>(`/workflows/runs/${encodeURIComponent(runId)}/reject`, {});

export const cancelRun = (runId: string) =>
    write<{ ok: boolean }>(`/workflows/runs/${encodeURIComponent(runId)}/cancel`, {});

/* ------------------------------------------------------------ small helpers */

export function fmtDate(d?: string): string {
    if (!d) return "—";
    try {
        return new Date(d).toLocaleString();
    } catch {
        return d;
    }
}

export function runStatusVariant(
    s: WfRunStatus
): "success" | "danger" | "warning" | "info" | "neutral" {
    if (s === "completed") return "success";
    if (s === "failed" || s === "killed") return "danger";
    if (s === "awaiting_approval") return "warning";
    if (s === "running" || s === "queued") return "info";
    return "neutral";
}
