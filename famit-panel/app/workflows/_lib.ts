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

import type { SelectOption } from "@/types/select";

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

// The engine sub-object the LIVE backend emits (workflow/__init__.py status()).
// `engine:"in_process"` is the synchronous in-process interpreter — a REAL
// executor (live-verified: publish -> run drains to a terminal/parked status).
export type WfEngineInfo = {
    engine?: string; // "in_process" | "hatchet" | …
    available?: boolean; // durable (Hatchet) spine bound
    store_mode?: string; // "memory" | "pg"
    hatchet_configured?: boolean;
    killswitch?: boolean;
    [k: string]: unknown;
};

// The LIVE /workflows/status contract (verified 2026-06-11): `engine` is an
// OBJECT (not the string "configured"), `store` is a mode string ("memory"|"pg"),
// and there is NO top-level `enabled`. The old shape here lied about the contract
// and pinned `engineLive` to false forever (Run permanently disabled). Everything
// is optional/loose so the dormant-coming-soon path still renders cleanly.
export type WfStatus = {
    module?: string;
    enabled?: boolean; // legacy/optional — never sent by the live engine
    engine?: WfEngineInfo | string; // OBJECT live; string only in older shapes
    store?: string; // "memory" | "pg" | "configured"
    config?: WfEngineInfo;
    templates?: number;
    registry_tools?: string[];
    // Optional per-dependency signals (rendered if a future status emits them).
    wallet?: string;
    firewall?: string;
    audit?: string;
    registry?: string;
    llm_provider?: string;
    workflows_total?: number;
    published_total?: number;
    runs_total?: number;
};

// Is the engine able to RUN a published workflow right now? The live backend runs
// synchronously via the in-process interpreter (no Hatchet needed), so treat
// `engine.available === true` OR `engine.engine === "in_process"` as run-capable.
// Falls back to the legacy string contract for safety.
export function isEngineLive(st: WfStatus | null | undefined): boolean {
    if (!st) return false;
    const eng = st.engine;
    if (typeof eng === "object" && eng) {
        return eng.available === true || eng.engine === "in_process";
    }
    return eng === "configured";
}

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

/* ============================================ inspector field schema (spec §2/§3) */

// A tiny, declarative per-type field map. The inspector renders these generically
// with the ported Core_2 Field / Select / Switch — zero bespoke form code per type.
// `path` is where the value lives on the RF node.data object:
//   "config.<key>"  -> node.data.config[key]   (the inspector-edited object)
//   "label"         -> node.data.label         (studio-only display label)
//   "role"          -> node.data.role          (ai_agent persona)
//   "money"         -> node.data.money         (advisory "can spend" flag)
//   "args"          -> node.data.config.args   (the repeatable key/val sub-editor)
export type FieldKind = "text" | "number" | "textarea" | "select" | "switch" | "args";

export type FieldDef = {
    path: string;
    label: string;
    kind: FieldKind;
    placeholder?: string;
    tooltip?: string;
    options?: string[]; // for kind="select" — raw enum values
    when?: { path: string; equals: string }; // conditional visibility (e.g. event only when kind=event)
    help?: string;
};

// The curated tool registry options (spec §2: ship the tools the engine already
// names; later hydrate from GET /workflows/status registry signal).
export const TOOL_OPTIONS = [
    "leads.enqueue_calls",
    "whatsapp.send",
    "crm.update_lead",
    "booking.create",
    "payments.create_invoice",
    "ads.set_budget",
    "brain.retrieve",
    "email.send",
];

export const AI_ROLE_OPTIONS = [
    "ai_telecaller",
    "campaign_strategist",
    "support_agent",
    "data_analyst",
    "content_writer",
];

// Every type opens with a studio label field, then its type-specific config.
const LABEL_FIELD: FieldDef = {
    path: "label",
    label: "Label",
    kind: "text",
    placeholder: "A short name for this step",
    help: "Studio-only — shown on the node card; not part of execution.",
};

export const INSPECTOR_FIELDS: Record<WfNodeType, FieldDef[]> = {
    trigger: [
        LABEL_FIELD,
        {
            path: "config.trigger_kind",
            label: "Trigger kind",
            kind: "select",
            options: ["manual", "schedule", "event", "webhook", "wait"],
            tooltip: "How a run of this workflow is fired.",
        },
        {
            path: "config.event",
            label: "Event",
            kind: "select",
            options: [
                "lead.created",
                "lead.replied",
                "call.completed",
                "lead.qualified",
                "payment.received",
                "form.submitted",
                "booking.made",
            ],
            when: { path: "config.trigger_kind", equals: "event" },
            tooltip: "Which lifecycle event triggers the run.",
        },
        {
            path: "config.cron",
            label: "Schedule (cron)",
            kind: "text",
            placeholder: "0 9 * * *",
            when: { path: "config.trigger_kind", equals: "schedule" },
        },
        { path: "config.segment", label: "Segment", kind: "text", placeholder: "hot" },
    ],
    condition: [
        LABEL_FIELD,
        {
            path: "config.expr",
            label: "Expression",
            kind: "textarea",
            placeholder: "lead.interest >= 7 && !lead.opted_out",
            tooltip: "A sandboxed boolean — emits a true and a false branch.",
            help: "Branches the flow. Wire one edge from the true handle and one from false.",
        },
    ],
    delay: [
        LABEL_FIELD,
        { path: "config.after_hours", label: "Delay (hours)", kind: "number", placeholder: "24" },
        { path: "config.after_minutes", label: "…or minutes", kind: "number", placeholder: "0" },
        {
            path: "config.event_key",
            label: "Wait-for event key",
            kind: "text",
            placeholder: "lead.replied",
            help: "Leave delay blank and set this to wait for an event instead (durable wait).",
        },
        { path: "config.timeout_hours", label: "Wait timeout (hours)", kind: "number", placeholder: "48" },
    ],
    ai_agent: [
        LABEL_FIELD,
        {
            path: "role",
            label: "Workforce role",
            kind: "select",
            options: AI_ROLE_OPTIONS,
            tooltip: "Which AI-workforce persona runs this step (reads the Business Brain + KB).",
        },
        { path: "config.tool", label: "Tool", kind: "select", options: TOOL_OPTIONS },
        { path: "args", label: "Arguments", kind: "args" },
        {
            path: "money",
            label: "This step can spend",
            kind: "switch",
            help: "Advisory only — the runtime recomputes spend from the resolved tool + args.",
        },
    ],
    action: [
        LABEL_FIELD,
        {
            path: "config.tool",
            label: "Tool",
            kind: "select",
            options: TOOL_OPTIONS,
            tooltip: "One deterministic registry tool call, gated by its own metadata.",
        },
        { path: "args", label: "Arguments", kind: "args" },
        {
            path: "money",
            label: "This step can spend",
            kind: "switch",
            help: "Advisory only — the runtime recomputes spend from the resolved tool + args.",
        },
    ],
    integration: [
        LABEL_FIELD,
        {
            path: "config.tool",
            label: "Adapter",
            kind: "select",
            options: ["ads.set_budget", "email.send", "whatsapp.send", "calendar.create", "webhook.post"],
            tooltip: "A dormant-until-creds external adapter.",
        },
        { path: "args", label: "Arguments", kind: "args" },
        {
            path: "money",
            label: "This step can spend",
            kind: "switch",
            help: "Advisory only — the runtime recomputes spend from the resolved tool + args.",
        },
    ],
    budget: [
        LABEL_FIELD,
        {
            path: "config.cap_inr",
            label: "Cap (₹)",
            kind: "number",
            placeholder: "2000",
            tooltip: "Reserves a run-scoped wallet hold. Every money node downstream settles against it.",
        },
        { path: "config.threshold_inr", label: "Approval threshold (₹)", kind: "number", placeholder: "500" },
        {
            path: "config.on_exceed",
            label: "On exceed",
            kind: "select",
            options: ["park_for_approval", "reject"],
        },
    ],
    approval: [
        LABEL_FIELD,
        { path: "config.require", label: "Require", kind: "select", options: ["pin", "otp"] },
        { path: "config.role", label: "Approver role", kind: "select", options: ["owner", "manager", "admin"] },
        { path: "config.threshold_inr", label: "Threshold (₹)", kind: "number", placeholder: "0" },
        { path: "config.timeout_h", label: "Timeout (hours)", kind: "number", placeholder: "24" },
        {
            path: "config.on_timeout",
            label: "On timeout",
            kind: "select",
            options: ["reject", "park", "notify"],
        },
    ],
    error: [
        LABEL_FIELD,
        {
            path: "config.action",
            label: "On failure",
            kind: "select",
            options: ["terminate", "notify", "human_handover", "retry"],
            tooltip: "What happens when an upstream node fails (wire its on-error edge here).",
        },
        { path: "config.reason", label: "Reason / note", kind: "text", placeholder: "Escalate to a human" },
    ],
    data: [
        LABEL_FIELD,
        { path: "args", label: "Set (key / value)", kind: "args" },
        {
            path: "config.read_tool",
            label: "Read from",
            kind: "select",
            options: ["brain.retrieve", "crm.get_lead", "none"],
        },
        { path: "config.bag_key", label: "Store into bag key", kind: "text", placeholder: "summary" },
    ],
};

// SelectOption.id is a NUMBER in the ported kit; our enums are strings. Build a
// stable index-keyed option list + resolve the selected option from a string.
export function selOpts(values: string[]): SelectOption[] {
    return values.map((name, i) => ({ id: i, name }));
}
export function selFind(values: string[], current: unknown): SelectOption | null {
    const cur = current == null ? "" : String(current);
    const i = values.indexOf(cur);
    return i >= 0 ? { id: i, name: cur } : null;
}

/* --------------------------------- graph mapping: RF Node[]/Edge[] ⇄ DSL JSON */

// The single React-Flow custom node type. The DSL `type` lives in data.wfType so
// the canvas owns ONE renderer while the engine sees the real 10-type taxonomy.
export const RF_NODE_TYPE = "wfNode" as const;

// What rides on each RF node (mirrors WfNode minus the layout x/y, which RF owns).
export type WfNodeData = {
    wfType: WfNodeType;
    label?: string;
    role?: string;
    config: Record<string, unknown>;
    money?: boolean;
    on_error?: string;
};

export type RFNode = {
    id: string;
    type: typeof RF_NODE_TYPE;
    position: { x: number; y: number };
    data: WfNodeData;
};
export type RFEdge = {
    id: string;
    source: string;
    target: string;
    sourceHandle?: string | null;
    data?: { when?: "true" | "false"; error?: boolean };
};

export const NODE_ID_RE = /^[A-Za-z0-9_\-]{1,64}$/;

let _idSeq = 0;
export function newNodeId(type: WfNodeType): string {
    _idSeq += 1;
    return `n_${type}_${Date.now().toString(36)}${_idSeq}`;
}

// DSL WfDefinition -> React-Flow nodes + edges (load / template "Edit"). Auto-lays
// any node missing x/y left-to-right (reusing the template auto-layout intent).
export function fromDefinition(def: WfDefinition): { nodes: RFNode[]; edges: RFEdge[] } {
    const all = [def.trigger, ...def.nodes];
    const nodes: RFNode[] = all.map((n, i) => ({
        id: n.node_id,
        type: RF_NODE_TYPE,
        position: {
            x: typeof n.x === "number" ? n.x : 40 + i * 230,
            y: typeof n.y === "number" ? n.y : 200,
        },
        data: {
            wfType: n.type,
            label: n.label,
            role: n.role,
            config: { ...(n.config || {}) },
            money: n.money,
            on_error: n.on_error,
        },
    }));
    const edges: RFEdge[] = def.edges.map((e, i) => ({
        id: `e_${e.from}_${e.to}_${i}`,
        source: e.from,
        target: e.to,
        sourceHandle: e.when ? e.when : null,
        data: { when: e.when, error: e.error },
    }));
    return { nodes, edges };
}

// React-Flow nodes + edges -> DSL WfDefinition (save / validate / publish). The
// canvas owns x/y; the engine ignores them, so layout never corrupts execution.
export function toDefinition(
    nodes: RFNode[],
    edges: RFEdge[],
    base: Partial<WfDefinition> & { workflow_id: string; name: string }
): WfDefinition {
    const triggerNode = nodes.find((n) => n.data.wfType === "trigger");
    const toWf = (n: RFNode): WfNode => ({
        node_id: n.id,
        type: n.data.wfType,
        label: n.data.label,
        role: n.data.role,
        config: n.data.config || {},
        money: n.data.money,
        on_error: n.data.on_error,
        x: Math.round(n.position.x),
        y: Math.round(n.position.y),
    });
    const trigger: WfNode = triggerNode
        ? toWf(triggerNode)
        : {
              node_id: "n_trigger",
              type: "trigger",
              label: "Trigger",
              config: { trigger_kind: "manual" },
              x: 40,
              y: 200,
          };
    const others = nodes.filter((n) => n.id !== trigger.node_id).map(toWf);
    const dslEdges: WfEdge[] = edges.map((e) => {
        const when = (e.sourceHandle as "true" | "false" | null) || e.data?.when;
        const out: WfEdge = { from: e.source, to: e.target };
        if (when === "true" || when === "false") out.when = when;
        if (e.data?.error) out.error = true;
        return out;
    });
    return {
        schema_version: base.schema_version ?? 1,
        workflow_id: base.workflow_id,
        name: base.name,
        version: base.version ?? 1,
        status: base.status ?? "draft",
        industry_pack: base.industry_pack,
        trigger,
        nodes: others,
        edges: dslEdges,
        guards:
            base.guards ?? {
                max_actions: 500,
                calling_window: "09:00-21:00 IST",
                respect_dnd: true,
                respect_consent: true,
                kill_switch: false,
            },
    };
}

/* ---- human-language node label resolver (spec requirement) ---- */

// Converts raw WfNode metadata into a plain-English label a non-technical
// founder can read at a glance. Used by WfNodeView instead of raw `d.wfType`.
// Priority: explicit `label` field (set by the inspector) > derived from config > fallback.
export function humanLabel(data: WfNodeData): string {
    if (data.label && data.label !== nodeMeta(data.wfType).label) {
        // User has set a custom label — use it verbatim.
        return data.label;
    }
    // Derive from config for the most common cases:
    switch (data.wfType) {
        case "trigger": {
            const kind = data.config?.trigger_kind as string | undefined;
            const seg = data.config?.segment as string | undefined;
            if (kind === "lead.created") return seg ? `When a ${seg} lead arrives` : "When a new lead arrives";
            if (kind === "call.completed") return "When a call completes";
            if (kind === "payment.received") return "When payment is received";
            if (kind === "booking.made") return "When a booking is made";
            if (kind === "form.submitted") return "When a form is submitted";
            if (kind === "lead.replied") return "When a lead replies";
            if (kind === "lead.qualified") return "When a lead qualifies";
            if (kind === "schedule") {
                const cron = data.config?.cron as string | undefined;
                return cron ? `On schedule: ${cron}` : "On a schedule";
            }
            if (kind === "webhook") return "On webhook";
            if (kind === "event") {
                const ev = data.config?.event as string | undefined;
                return ev ? `On event: ${ev.replace(/\./g, " ")}` : "On an event";
            }
            return data.label || "Start here";
        }
        case "condition": {
            const expr = data.config?.expr as string | undefined;
            if (expr) return `Check: ${expr.length > 28 ? expr.slice(0, 28) + "…" : expr}`;
            return "Check a condition";
        }
        case "delay": {
            const h = data.config?.after_hours as number | undefined;
            const m = data.config?.after_minutes as number | undefined;
            const ev = data.config?.event_key as string | undefined;
            if (ev) return `Wait for: ${ev.replace(/\./g, " ")}`;
            if (h && h > 0) return `Wait ${h} hour${h === 1 ? "" : "s"}`;
            if (m && m > 0) return `Wait ${m} minute${m === 1 ? "" : "s"}`;
            return "Wait / delay";
        }
        case "ai_agent": {
            const tool = data.config?.tool as string | undefined;
            if (tool === "leads.enqueue_calls") return "Start calling";
            if (tool === "whatsapp.send") return "Send on WhatsApp";
            if (tool === "crm.update_lead") return "Update lead in CRM";
            if (tool === "booking.create") return "Create a booking";
            const role = data.role;
            if (role === "ai_telecaller") return "AI voice call";
            if (role === "campaign_strategist") return "AI: plan campaign";
            if (role === "support_agent") return "AI: support agent";
            if (role === "data_analyst") return "AI: analyse data";
            return data.label || "AI agent step";
        }
        case "action": {
            const tool = data.config?.tool as string | undefined;
            if (tool === "leads.enqueue_calls") return "Start calling";
            if (tool === "whatsapp.send") return "Send WhatsApp message";
            if (tool === "crm.update_lead") return "Update lead record";
            if (tool === "booking.create") return "Create booking";
            if (tool === "payments.create_invoice") return "Create invoice";
            if (tool === "ads.set_budget") return "Set ad budget";
            if (tool === "brain.retrieve") return "Look up knowledge";
            if (tool === "email.send") return "Send email";
            return data.label || "Run an action";
        }
        case "integration": {
            const tool = data.config?.tool as string | undefined;
            if (tool === "ads.set_budget") return "Adjust ad budget";
            if (tool === "whatsapp.send") return "WhatsApp via integration";
            if (tool === "email.send") return "Send email";
            if (tool === "calendar.create") return "Create calendar event";
            if (tool === "webhook.post") return "Call a webhook";
            return data.label || "External integration";
        }
        case "budget": {
            const cap = data.config?.cap_inr as number | undefined;
            if (cap) return `Budget cap: ₹${cap.toLocaleString()}`;
            return "Set spend limit";
        }
        case "approval": {
            const role = data.config?.role as string | undefined;
            const req = data.config?.require as string | undefined;
            if (role && req) return `${role} approves (${req})`;
            if (role) return `${role} must approve`;
            return "Human approval";
        }
        case "error":
            return data.label || "Handle errors";
        case "data": {
            const read = data.config?.read_tool as string | undefined;
            if (read === "brain.retrieve") return "Read from Brain";
            if (read === "crm.get_lead") return "Read lead data";
            return data.label || "Read / write data";
        }
    }
}

// The default human-friendly label to pre-populate when a node is first dropped.
// These are the "nice defaults" — the inspector's Label field can override them.
export const HUMAN_DEFAULT_LABELS: Record<WfNodeType, string> = {
    trigger: "When a new lead arrives",
    condition: "Check a condition",
    delay: "Wait",
    ai_agent: "Start calling",
    action: "Run an action",
    integration: "External integration",
    budget: "Set spend limit",
    approval: "Human approval",
    error: "Handle errors",
    data: "Read / write data",
};

// The "starter: call run" working template — the backend-verified linear flow.
// Trigger -> ai_agent(leads.enqueue_calls). The backend `starter_call_run` template
// compiles to this graph. We render it as the one-click "Load template" option.
export const STARTER_CALL_TEMPLATE: WfDefinition = {
    schema_version: 1,
    workflow_id: "wf_tpl_starter_call_run",
    name: "Starter: call new leads",
    version: 1,
    status: "draft",
    industry_pack: "generic",
    trigger: {
        node_id: "n_trigger",
        type: "trigger",
        label: "When a new lead arrives",
        config: { trigger_kind: "lead.created", segment: "hot" },
        x: 80,
        y: 220,
    },
    nodes: [
        {
            node_id: "n_call",
            type: "ai_agent",
            label: "Start calling",
            role: "ai_telecaller",
            config: { tool: "leads.enqueue_calls" },
            money: false,
            x: 340,
            y: 220,
        },
    ],
    edges: [{ from: "n_trigger", to: "n_call" }],
    guards: {
        max_actions: 500,
        calling_window: "09:00-21:00 IST",
        respect_dnd: true,
        respect_consent: true,
        kill_switch: false,
    },
};

// A blank starter graph for "New workflow" — just a trigger node, centered.
export function blankGraph(): { nodes: RFNode[]; edges: RFEdge[] } {
    return {
        nodes: [
            {
                id: "n_trigger",
                type: RF_NODE_TYPE,
                position: { x: 80, y: 220 },
                data: { wfType: "trigger", label: "Trigger", config: { trigger_kind: "manual" } },
            },
        ],
        edges: [],
    };
}

// A fresh, blank WfDefinition for "New workflow" — a brand-new id, an editable
// name, draft status, the default guards, and ONLY a single manual Trigger node.
// This is the from-scratch entry point (spec §C): page.tsx loads this so the user
// builds from zero instead of re-opening the demo SAMPLE_WORKFLOW every time.
export function blankDefinition(): WfDefinition {
    const rand = Math.random().toString(36).slice(2, 8);
    return {
        schema_version: 1,
        workflow_id: `wf_${rand}`,
        name: "Untitled workflow",
        version: 1,
        status: "draft",
        trigger: {
            node_id: "n_trigger",
            type: "trigger",
            label: "Trigger",
            config: { trigger_kind: "manual" },
            x: 80,
            y: 220,
        },
        nodes: [],
        edges: [],
        guards: {
            max_actions: 500,
            calling_window: "09:00-21:00 IST",
            respect_dnd: true,
            respect_consent: true,
            kill_switch: false,
        },
    };
}

// The single node-data factory used by BOTH click-to-add and drag-drop in the
// editor (spec §B) so the two paths build an identical node (one source of truth).
// Uses human-language defaults (HUMAN_DEFAULT_LABELS) so nodes are readable
// immediately without the inspector needing to be opened.
export function newNodeData(wfType: WfNodeType): WfNodeData {
    const meta = nodeMeta(wfType);
    const label = HUMAN_DEFAULT_LABELS[wfType] ?? meta.label;
    return { wfType, label, config: {}, money: meta.money };
}

// Edge validation (spec §2): which source type may connect to which target.
// trigger has no incoming; error/budget/approval are not connection-restricted
// beyond the trigger rule; a node cannot connect to itself.
export function isValidWfConnection(
    sourceType: WfNodeType | undefined,
    targetType: WfNodeType | undefined,
    sameNode: boolean
): boolean {
    if (sameNode) return false;
    if (!sourceType || !targetType) return false;
    if (targetType === "trigger") return false; // nothing connects INTO a trigger
    return true;
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

async function write<T>(
    path: string,
    body: Record<string, unknown>,
    method: "POST" | "PUT" = "POST"
): Promise<T> {
    const res = await fetch(`${BASE}${path}`, {
        method,
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

// Fetch a server-stored workflow and normalise it into an editable WfDefinition.
// The backend wraps the graph as { definition: { workflow_id, name, status,
// current_version, industry_pack, draft:{…graph} } }. We lift the draft graph,
// stamp the authoritative server workflow_id/name on it, and return a def the
// canvas can open (fromDefinition auto-lays any node missing x/y). On any miss we
// return null so the caller can fall back to the static template definition.
export async function loadServerWorkflow(id: string): Promise<WfDefinition | null> {
    const res = await read<{
        definition?: {
            workflow_id?: string;
            name?: string;
            status?: string;
            current_version?: number;
            industry_pack?: string;
            draft?: Partial<WfDefinition>;
        };
    }>(`/workflows/${encodeURIComponent(id)}`);
    if (res.kind !== "ok") return null;
    const d = res.data?.definition;
    const draft = d?.draft;
    if (!d || !draft || !draft.trigger) return null;
    markCreated(d.workflow_id || id);
    return {
        schema_version: draft.schema_version ?? 1,
        workflow_id: d.workflow_id || id,
        name: draft.name || d.name || "Untitled workflow",
        version: draft.version ?? (d.current_version || 1),
        status: (draft.status as WfDefinition["status"]) || (d.status as WfDefinition["status"]) || "draft",
        industry_pack: draft.industry_pack || d.industry_pack || undefined,
        trigger: draft.trigger as WfNode,
        nodes: (draft.nodes as WfNode[]) || [],
        edges: (draft.edges as WfEdge[]) || [],
        guards:
            (draft.guards as WfGuards) || {
                max_actions: 500,
                calling_window: "09:00-21:00 IST",
                respect_dnd: true,
                respect_consent: true,
                kill_switch: false,
            },
    };
}

// Trigger a run of the published workflow. The in-process engine runs it
// synchronously and returns a terminal/parked status inline:
//   { ok, run_id, engine:"in_process", status:"completed"|"awaiting_approval"|…, steps }
// On refusal: { ok:false, reason:"not_published"|"budget_no_funds"|… }.
export const runWorkflow = (id: string) =>
    write<{
        ok: boolean;
        run_id?: string;
        engine?: string;
        status?: string;
        steps?: number;
        reason?: string;
    }>(`/workflows/${encodeURIComponent(id)}/run`, {});

export const approveRun = (runId: string, pin: string) =>
    write<{ ok: boolean }>(`/workflows/runs/${encodeURIComponent(runId)}/approve`, { pin });

export const rejectRun = (runId: string) =>
    write<{ ok: boolean }>(`/workflows/runs/${encodeURIComponent(runId)}/reject`, {});

export const cancelRun = (runId: string) =>
    write<{ ok: boolean }>(`/workflows/runs/${encodeURIComponent(runId)}/cancel`, {});

/* ----------------------------------------- editor mutations (spec §5 — added) */

// These hit the SAME defined-not-mounted router. Each 404/501/503 ⇒ the friendly
// "engine not configured yet" throw from write(), so the editor degrades to a
// local-only canvas (Save/Publish show the premium dormant toast) and lights up
// the moment the wiring diff lands — zero frontend change at cutover (spec §5).

// Load a single workflow's editable draft + version history.
export const getWorkflow = (id: string) =>
    read<{ definition: WfDefinition; versions?: { version: number; status: string; updated_at?: string }[] }>(
        `/workflows/${encodeURIComponent(id)}`
    );

// Persist the canvas as the workflow draft (the DSL JSON is the contract).
export const saveWorkflow = (id: string, def: WfDefinition) =>
    write<{ ok: boolean; version: number; definition?: unknown }>(
        `/workflows/${encodeURIComponent(id)}`,
        { draft: def },
        "PUT"
    );

// Whether a workflow_id is a server-created (persisted) row vs a client-minted
// "wf_<rand>" id that has NOT yet been POST-created on the backend. A from-scratch
// blankDefinition() id is client-side until the first save creates the server row.
// We persist the mapping so a reload still knows the row exists server-side.
const CREATED_KEY = "wf_created_ids";
function loadCreated(): Set<string> {
    if (typeof window === "undefined") return new Set();
    try {
        return new Set(JSON.parse(localStorage.getItem(CREATED_KEY) || "[]") as string[]);
    } catch {
        return new Set();
    }
}
function markCreated(id: string): void {
    if (typeof window === "undefined") return;
    try {
        const s = loadCreated();
        s.add(id);
        localStorage.setItem(CREATED_KEY, JSON.stringify([...s]));
    } catch {
        /* non-fatal */
    }
}
export function isServerCreated(id: string): boolean {
    return loadCreated().has(id);
}

// THE save contract (live-verified 2026-06-11):
//   PUT /workflows/{id} returns {ok:false} unless the row was POST-created first
//   (update_draft requires a pre-existing row). POST /workflows MINTS ITS OWN id
//   and IGNORES any client workflow_id. So: on first save of a from-scratch graph
//   we POST to create the row, ADOPT the server id, rewrite def.workflow_id to it,
//   then PUT. Subsequent saves PUT straight to the (now server-known) id.
//
// Returns the AUTHORITATIVE workflow_id the caller must use for every later
// validate / publish / run (it differs from the client id on first save).
export async function upsertWorkflow(
    id: string,
    def: WfDefinition
): Promise<{ workflow_id: string; created: boolean }> {
    if (isServerCreated(id)) {
        await saveWorkflow(id, def);
        return { workflow_id: id, created: false };
    }
    // First server save: create the row, adopt the server-minted id, then PUT.
    const res = await createWorkflow({ name: def.name, industry_pack: def.industry_pack });
    const serverId = res.workflow_id || id;
    markCreated(serverId);
    await saveWorkflow(serverId, { ...def, workflow_id: serverId });
    return { workflow_id: serverId, created: true };
}

// Static validator + dominator compile. The LIVE backend returns
// { ok, errors:[{code,node_ids,msg}], classified, reachable }; older shapes used
// { ok, code, node_ids, message }. Type covers both so callers can read either.
export type WfValidationError = { code?: string; node_ids?: string[]; msg?: string };
export type ValidateResult = {
    ok: boolean;
    code?: string;
    node_ids?: string[];
    message?: string;
    errors?: WfValidationError[];
};
export const validateWorkflow = (id: string, def: WfDefinition) =>
    write<ValidateResult>(`/workflows/${encodeURIComponent(id)}/validate`, { draft: def });

// Freeze the current draft as a published version. Refused (ok:false + errors)
// unless dominator-valid; on success returns { ok, version, hash }.
export const publishWorkflow = (id: string) =>
    write<{ ok: boolean; version?: number; hash?: string; errors?: WfValidationError[] }>(
        `/workflows/${encodeURIComponent(id)}/publish`,
        {}
    );

/* --------------------------------------------- local draft fallback (spec §F) */

// Until the engine is mounted, a Save persists the DSL to localStorage so a
// from-scratch graph survives a reload. Keyed by workflow_id. Live save (PUT)
// remains the source of truth once the router is mounted.
const DRAFT_PREFIX = "wf_draft_";

export function saveDraftLocal(def: WfDefinition): void {
    if (typeof window === "undefined") return;
    try {
        localStorage.setItem(DRAFT_PREFIX + def.workflow_id, JSON.stringify(def));
    } catch {
        /* quota / disabled — non-fatal, the canvas stays in memory */
    }
}

export function loadDraftLocal(id: string): WfDefinition | null {
    if (typeof window === "undefined") return null;
    try {
        const raw = localStorage.getItem(DRAFT_PREFIX + id);
        if (!raw) return null;
        const def = JSON.parse(raw) as WfDefinition;
        if (def && def.workflow_id === id && def.trigger) return def;
    } catch {
        /* corrupt entry — ignore */
    }
    return null;
}

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
