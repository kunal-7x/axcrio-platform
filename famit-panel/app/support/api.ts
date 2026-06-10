// app/support/api.ts — colocated fetch layer for the Customer Support page.
//
// Deliberately self-contained: the shared lib/api.ts does NOT export its token
// helpers (getToken / authHeaders / handle401), and this wave forbids editing
// shared files, so the few lines of auth plumbing are re-implemented here.
//
// Backend contract (droplet_work/support/router.py, mounted at prefix /support):
//   GET  /support/health
//   GET  /support/tickets        ?status&channel&assigned_to&limit
//   GET  /support/tickets/{id}   -> { ticket, messages }
//   POST /support/tickets/{id}/{draft,reply,escalate,claim,resolve}
//   POST /support/inbound
// The panel reverse-proxy strips /api, so BASE=/api maps to backend /support.
//
// DORMANCY: the router is NOT mounted yet this wave (caller.py wiring is a later
// step). Every call therefore tolerates a 404 / network failure WITHOUT throwing
// in a way that crashes the page — getSupportHealth() returns null on any failure
// so the page can render a premium "coming soon / not configured" state, and the
// list/detail calls degrade to empty. Mutations surface a typed error so action
// buttons can show "not available yet" / "no permission" gracefully.

const BASE =
    typeof process !== "undefined" && process.env.NEXT_PUBLIC_API_BASE
        ? process.env.NEXT_PUBLIC_API_BASE
        : "/api";

function getToken(): string | null {
    if (typeof window === "undefined") return null;
    return localStorage.getItem("famit_token");
}

function authHeaders(): HeadersInit {
    const token = getToken();
    return token ? { "X-Auth": token } : {};
}

// Mirror lib/api.ts: a 401 means the session died — clear it and bounce to login.
async function handle401(res: Response) {
    if (res.status === 401 && typeof window !== "undefined") {
        localStorage.removeItem("famit_token");
        localStorage.removeItem("famit_me");
        window.location.href = "/login";
        throw new Error("Unauthorized");
    }
}

// Read the cached /me blob (set at login) so the page can gate write actions on
// role without an extra round-trip. Never throws.
export type SupportRole = "admin" | "manager" | "agent";
export function getCachedRole(): SupportRole | null {
    if (typeof window === "undefined") return null;
    try {
        const raw = localStorage.getItem("famit_me");
        if (!raw) return null;
        const me = JSON.parse(raw) as { role?: SupportRole; is_admin?: boolean };
        if (me.is_admin) return "admin";
        return me.role ?? null;
    } catch {
        return null;
    }
}

export function canWrite(role: SupportRole | null): boolean {
    return role === "admin" || role === "manager";
}

// A mutation error that carries enough to render a friendly inline message.
export class SupportActionError extends Error {
    status: number;
    code: "dormant" | "permission" | "generic";
    constructor(status: number, code: SupportActionError["code"], message: string) {
        super(message);
        this.name = "SupportActionError";
        this.status = status;
        this.code = code;
    }
}

// ---- Types (mirror support/schema.sql column names exactly) ----

export type TicketStatus = "open" | "pending_human" | "resolved" | "closed";
export type TicketChannel = "whatsapp" | "voice" | "email" | "web" | string;
export type TicketPriority = "low" | "normal" | "high" | "urgent" | string;
export type TicketSentiment =
    | "positive"
    | "neutral"
    | "negative"
    | "angry"
    | string;

export type SupportTicket = {
    id: string;
    org_id: string;
    channel: TicketChannel;
    channel_thread_id: string;
    contact_phone: string;
    contact_email: string;
    contact_name: string;
    contact_id: string;
    subject: string;
    status: TicketStatus;
    priority: TicketPriority;
    sentiment: TicketSentiment;
    sentiment_score: number;
    assigned_to: string; // "ai" | a user id
    escalated: boolean;
    escalation_reason: string;
    ai_summary: string;
    msg_count: number;
    last_inbound_at: string | null;
    last_reply_at: string | null;
    created_at: string;
    updated_at: string;
    resolved_at: string | null;
    data?: Record<string, unknown>;
};

export type SupportMessage = {
    id: string;
    org_id: string;
    ticket_id: string;
    seq: number;
    direction: "inbound" | "outbound" | string;
    author: string; // "customer" | "ai" | a user id
    channel: string;
    body: string;
    reply_state: string; // "" | drafted | pending_send | sent | suppressed
    kb_grounded: boolean;
    confidence: number;
    sentiment: string;
    provider_msg_id: string;
    at: string;
    data?: Record<string, unknown>;
};

export type SupportHealth = {
    pg_available: boolean;
    schema_ready: boolean;
    tickets_count: number | null;
    kb: unknown;
    llm: unknown;
    auto_reply?: boolean;
    confidence_floor?: number;
    mode?: string;
};

export type TicketDetail = {
    ticket: SupportTicket;
    messages: SupportMessage[];
};

// ---- Health: the dormancy gate. Returns null on ANY failure (404 / network /
// not-wired) so the page renders coming-soon instead of crashing. ----
export async function getSupportHealth(): Promise<SupportHealth | null> {
    try {
        const res = await fetch(`${BASE}/support/health`, {
            headers: authHeaders(),
        });
        await handle401(res);
        if (!res.ok) return null;
        return (await res.json()) as SupportHealth;
    } catch {
        return null;
    }
}

export async function getTickets(opts?: {
    status?: string;
    channel?: string;
    assigned_to?: string;
    limit?: number;
}): Promise<SupportTicket[]> {
    const params = new URLSearchParams();
    if (opts?.status) params.set("status", opts.status);
    if (opts?.channel) params.set("channel", opts.channel);
    if (opts?.assigned_to) params.set("assigned_to", opts.assigned_to);
    params.set("limit", String(opts?.limit ?? 200));
    try {
        const res = await fetch(`${BASE}/support/tickets?${params.toString()}`, {
            headers: authHeaders(),
        });
        await handle401(res);
        if (!res.ok) return [];
        const body = (await res.json()) as { tickets?: SupportTicket[] };
        return body.tickets ?? [];
    } catch {
        return [];
    }
}

export async function getTicketDetail(id: string): Promise<TicketDetail> {
    const res = await fetch(`${BASE}/support/tickets/${encodeURIComponent(id)}`, {
        headers: authHeaders(),
    });
    await handle401(res);
    if (!res.ok) {
        throw new SupportActionError(
            res.status,
            res.status === 404 ? "dormant" : "generic",
            "Failed to load ticket"
        );
    }
    return (await res.json()) as TicketDetail;
}

// ---- Mutations: map the dormant/permission cases to a typed error. ----
async function postAction(
    id: string,
    action: "draft" | "reply" | "escalate" | "claim" | "resolve",
    fields?: Record<string, string>
): Promise<Record<string, unknown>> {
    const fd = new FormData();
    if (fields) for (const [k, v] of Object.entries(fields)) fd.append(k, v);
    let res: Response;
    try {
        res = await fetch(
            `${BASE}/support/tickets/${encodeURIComponent(id)}/${action}`,
            { method: "POST", headers: authHeaders(), body: fd }
        );
    } catch {
        throw new SupportActionError(0, "dormant", "Support service is not reachable yet.");
    }
    await handle401(res);
    if (!res.ok) {
        let body: Record<string, unknown> = {};
        try {
            body = await res.json();
        } catch {
            /* non-JSON */
        }
        const err = typeof body.error === "string" ? body.error : "";
        if (res.status === 404 || res.status === 503) {
            throw new SupportActionError(
                res.status,
                "dormant",
                "Support agent isn't configured yet — this action will work once it's live."
            );
        }
        if (res.status === 403) {
            throw new SupportActionError(
                403,
                "permission",
                err || "You don't have permission to do that."
            );
        }
        throw new SupportActionError(res.status, "generic", err || `Failed to ${action} ticket`);
    }
    return res.json();
}

export const draftReply = (id: string, question?: string) =>
    postAction(id, "draft", question ? { question } : undefined);
export const sendReply = (id: string, body: string) =>
    postAction(id, "reply", { body });
export const escalateTicket = (id: string, reason?: string) =>
    postAction(id, "escalate", reason ? { reason } : undefined);
export const claimTicket = (id: string) => postAction(id, "claim");
export const resolveTicket = (id: string, note?: string) =>
    postAction(id, "resolve", note ? { note } : undefined);
