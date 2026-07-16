// Colocated client for the Auto Lead surface → Haptica backend /auto-lead/*.
// Mirrors the app/crm auth preamble (X-Auth token + 401 → /login).

const BASE =
    typeof process !== "undefined" && process.env.NEXT_PUBLIC_API_BASE
        ? process.env.NEXT_PUBLIC_API_BASE
        : "/api";

function getToken(): string | null {
    if (typeof window === "undefined") return null;
    return localStorage.getItem("famit_token");
}
function authHeaders(json = false): HeadersInit {
    const token = getToken();
    const h: Record<string, string> = {};
    if (token) h["X-Auth"] = token;
    if (json) h["Content-Type"] = "application/json";
    return h;
}
function handle401(res: Response) {
    if (res.status === 401 && typeof window !== "undefined") {
        localStorage.removeItem("famit_token");
        localStorage.removeItem("famit_me");
        window.location.href = "/login";
        throw new Error("Unauthorized");
    }
}

// ── types (mirror the backend) ───────────────────────────────────────────────
export type ConfigField = {
    key: string;
    label: string;
    type: "text" | "password" | "number" | "select";
    placeholder?: string;
    required?: boolean;
    options?: { value: string; label: string }[];
};
export type SourceType = {
    type: string;
    label: string;
    mode: "push" | "pull";
    icon: string;
    desc: string;
    fields: ConfigField[];
};

export type Mapping = { name?: string; phone?: string; email?: string; company?: string };
export type Validation = {
    require_phone?: boolean;
    valid_phone_only?: boolean;
    require_email?: boolean;
    dedupe?: boolean;
};
export type Routing = {
    status?: string;
    tags?: string[];
    mark_hot?: boolean;
    sync_crm?: boolean;
};
export type SourceStats = {
    ingested?: number;
    accepted?: number;
    rejected?: number;
    last_at?: string | null;
    last_status?: string | null;
};
export type Source = {
    id: string;
    type: string;
    name: string;
    enabled: boolean;
    token: string;
    mode: "push" | "pull";
    icon: string;
    type_label: string;
    config: Record<string, string>;
    mapping: Mapping;
    validation: Validation;
    routing: Routing;
    honeypot: string;
    stats: SourceStats;
    created_at?: string;
    updated_at?: string;
};

export type FeedEvent = {
    id: string;
    at: string;
    source_id: string;
    source_name: string;
    source_type: string;
    channel: string;
    name: string;
    phone: string;
    email: string;
    company: string;
    accepted: boolean;
    reason: string;
    lead_id?: string | null;
    actions: string[];
    ip?: string;
};

export type Overview = {
    total_sources: number;
    active_sources: number;
    total_ingested: number;
    total_accepted: number;
    total_rejected: number;
    accepted_today: number;
    rejected_today: number;
    by_source: {
        id: string;
        name: string;
        type: string;
        icon: string;
        ingested: number;
        accepted: number;
        enabled: boolean;
    }[];
    recent: FeedEvent[];
};

// ── low-level ────────────────────────────────────────────────────────────────
async function tGet<T>(path: string): Promise<T> {
    const res = await fetch(`${BASE}${path}`, { headers: authHeaders() });
    handle401(res);
    if (!res.ok) throw new Error((await res.json().catch(() => ({})))?.error || `Request failed (${res.status})`);
    return res.json() as Promise<T>;
}
async function tSend<T>(method: string, path: string, body?: unknown): Promise<T> {
    const res = await fetch(`${BASE}${path}`, {
        method,
        headers: authHeaders(true),
        body: body === undefined ? undefined : JSON.stringify(body),
    });
    handle401(res);
    if (!res.ok) throw new Error((await res.json().catch(() => ({})))?.error || `Request failed (${res.status})`);
    return res.json() as Promise<T>;
}

// ── api ──────────────────────────────────────────────────────────────────────
export const getTypes = () => tGet<{ types: SourceType[] }>("/auto-lead/types");
export const getSources = () => tGet<{ sources: Source[]; can_write: boolean }>("/auto-lead/sources");
export const createSource = (data: Partial<Source>) =>
    tSend<{ ok: boolean; source: Source }>("POST", "/auto-lead/sources", data);
export const updateSource = (id: string, data: Partial<Source>) =>
    tSend<{ ok: boolean; source: Source }>("PATCH", `/auto-lead/sources/${id}`, data);
export const deleteSource = (id: string) => tSend<{ ok: boolean }>("DELETE", `/auto-lead/sources/${id}`);
export const testSource = (id: string, payload?: Record<string, unknown>) =>
    tSend<{ ok: boolean; would_accept: boolean; reason: string; parsed: Record<string, string> }>(
        "POST",
        `/auto-lead/sources/${id}/test`,
        payload ?? {}
    );
export const syncSource = (id: string) =>
    tSend<{ ok: boolean; fetched: number; accepted: number }>("POST", `/auto-lead/sources/${id}/sync`);
export const getFeed = (o?: { source?: string; status?: string; limit?: number }) => {
    const sp = new URLSearchParams();
    if (o?.source) sp.set("source", o.source);
    if (o?.status) sp.set("status", o.status);
    if (o?.limit) sp.set("limit", String(o.limit));
    const q = sp.toString();
    return tGet<{ events: FeedEvent[] }>(`/auto-lead/feed${q ? `?${q}` : ""}`);
};
export const getOverview = () => tGet<Overview>("/auto-lead/overview");

// The public webhook URL external systems POST to (built client-side from the token).
export function ingestUrl(token: string): string {
    const origin = typeof window !== "undefined" ? window.location.origin : "";
    return `${origin}/api/auto-lead/ingest/${token}`;
}
