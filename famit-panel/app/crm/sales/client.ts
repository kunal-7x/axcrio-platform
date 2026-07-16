// Colocated client for the Sales CRM (Twenty-powered) surface.
//
// Talks to the Haptica backend's /twenty/* router (NOT to Twenty directly — the
// workspace API key lives server-side). Mirrors app/crm/client.ts's auth preamble
// (X-Auth token + 401 → /login) because lib/api.ts's helpers are module-private
// and this page scopes its own files. The backend is dormant-safe: reads return
// `{ connected: false }` + empty collections when no Twenty workspace is connected,
// so the page renders a calm "Connect your Twenty CRM" state instead of an error.

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

// ── Types (mirror twenty_crm/normalize.py byte-for-byte) ─────────────────────
export type TwentyStatus = {
    connected: boolean;
    source: "tenant" | "self_host" | "env" | null;
    base_url: string;
    key_masked: string;
    connected_at: string | null;
    can_write?: boolean;
    // true when Twenty is self-hosted inside Haptica -> the panel auto-provisions a
    // workspace per tenant (no API-key form).
    self_host?: boolean;
    workspace_id?: string | null;
};

export type Stage = { value: string; label: string; color?: string | null };

export type Company = {
    id: string;
    name: string;
    domain: string;
    employees?: number | null;
    city: string;
    country: string;
    linkedin: string;
    peopleCount?: number | null;
    opportunitiesCount?: number | null;
    createdAt?: string | null;
    updatedAt?: string | null;
};

export type Person = {
    id: string;
    name: string;
    firstName: string;
    lastName: string;
    email: string;
    phone: string;
    jobTitle: string;
    city: string;
    avatarUrl: string;
    companyId?: string | null;
    companyName?: string | null;
    createdAt?: string | null;
    updatedAt?: string | null;
};

export type Opportunity = {
    id: string;
    name: string;
    stage: string;
    amount?: number | null;
    currencyCode: string;
    closeDate?: string | null;
    companyId?: string | null;
    companyName?: string | null;
    pointOfContactId?: string | null;
    pointOfContactName?: string | null;
    position?: number | null;
    createdAt?: string | null;
    updatedAt?: string | null;
};

export type Note = { id: string; title: string; body: string; createdAt?: string | null };
export type Task = {
    id: string;
    title: string;
    body: string;
    status: string;
    dueAt?: string | null;
    createdAt?: string | null;
};

export type CompaniesResponse = {
    connected: boolean;
    companies: Company[];
    total?: number | null;
    next_cursor?: string | null;
};
export type PeopleResponse = {
    connected: boolean;
    people: Person[];
    total?: number | null;
    next_cursor?: string | null;
};
export type OpportunitiesResponse = {
    connected: boolean;
    opportunities: Opportunity[];
    total?: number | null;
    next_cursor?: string | null;
};
export type PipelineResponse = {
    connected: boolean;
    stages: Stage[];
    columns: Record<string, Opportunity[]>;
};

export type RecordDetail<T> = {
    connected: boolean;
    record: T | null;
    people?: Person[];
    opportunities?: Opportunity[];
    notes?: Note[];
    tasks?: Task[];
};

export type SyncResult = {
    ok: boolean;
    imported: number;
    total: number;
    results: { ok: boolean; name: string; created?: boolean; error?: string }[];
};

// ── low-level ────────────────────────────────────────────────────────────────
async function tGet<T>(path: string): Promise<T> {
    const res = await fetch(`${BASE}${path}`, { headers: authHeaders() });
    handle401(res);
    if (!res.ok) {
        let msg = "";
        try {
            msg = (await res.json())?.error || "";
        } catch {
            /* non-JSON */
        }
        throw new Error(msg || `Request failed (${res.status})`);
    }
    return res.json() as Promise<T>;
}

async function tSend<T>(method: string, path: string, body?: unknown): Promise<T> {
    const res = await fetch(`${BASE}${path}`, {
        method,
        headers: authHeaders(true),
        body: body === undefined ? undefined : JSON.stringify(body),
    });
    handle401(res);
    if (!res.ok) {
        let msg = "";
        try {
            msg = (await res.json())?.error || "";
        } catch {
            /* non-JSON */
        }
        throw new Error(msg || `Request failed (${res.status})`);
    }
    return res.json() as Promise<T>;
}

function qs(params: Record<string, string | number | undefined>): string {
    const sp = new URLSearchParams();
    for (const [k, v] of Object.entries(params)) {
        if (v !== undefined && v !== "" && v !== null) sp.set(k, String(v));
    }
    const s = sp.toString();
    return s ? `?${s}` : "";
}

// ── connection lifecycle ──────────────────────────────────────────────────────
export const getStatus = () => tGet<TwentyStatus>("/twenty/status");
export const connect = (base_url: string, api_key: string) =>
    tSend<{ ok: boolean } & TwentyStatus>("POST", "/twenty/connect", { base_url, api_key });
// Self-hosted zero-touch: provision (or return) this tenant's own Twenty workspace.
export const provision = () => tSend<{ ok: boolean } & TwentyStatus>("POST", "/twenty/provision");
export const disconnect = () => tSend<{ ok: boolean } & TwentyStatus>("POST", "/twenty/disconnect");
export const getStages = () => tGet<{ connected: boolean; stages: Stage[] }>("/twenty/meta/stages");

// ── companies ─────────────────────────────────────────────────────────────────
export const getCompanies = (o?: { q?: string; limit?: number; cursor?: string }) =>
    tGet<CompaniesResponse>(`/twenty/companies${qs({ q: o?.q, limit: o?.limit, cursor: o?.cursor })}`);
export const getCompany = (id: string) =>
    tGet<RecordDetail<Company>>(`/twenty/companies/${encodeURIComponent(id)}`);
export const createCompany = (data: Partial<Company>) =>
    tSend<{ ok: boolean; record: Company }>("POST", "/twenty/companies", data);
export const updateCompany = (id: string, data: Partial<Company>) =>
    tSend<{ ok: boolean; record: Company }>("PATCH", `/twenty/companies/${encodeURIComponent(id)}`, data);
export const deleteCompany = (id: string) =>
    tSend<{ ok: boolean }>("DELETE", `/twenty/companies/${encodeURIComponent(id)}`);

// ── people ────────────────────────────────────────────────────────────────────
export const getPeople = (o?: { q?: string; limit?: number; cursor?: string }) =>
    tGet<PeopleResponse>(`/twenty/people${qs({ q: o?.q, limit: o?.limit, cursor: o?.cursor })}`);
export const getPerson = (id: string) =>
    tGet<RecordDetail<Person>>(`/twenty/people/${encodeURIComponent(id)}`);
export const createPerson = (data: Partial<Person>) =>
    tSend<{ ok: boolean; record: Person }>("POST", "/twenty/people", data);
export const updatePerson = (id: string, data: Partial<Person>) =>
    tSend<{ ok: boolean; record: Person }>("PATCH", `/twenty/people/${encodeURIComponent(id)}`, data);
export const deletePerson = (id: string) =>
    tSend<{ ok: boolean }>("DELETE", `/twenty/people/${encodeURIComponent(id)}`);

// ── opportunities (+ pipeline kanban) ──────────────────────────────────────────
export const getOpportunities = (o?: { q?: string; limit?: number; cursor?: string }) =>
    tGet<OpportunitiesResponse>(
        `/twenty/opportunities${qs({ q: o?.q, limit: o?.limit, cursor: o?.cursor })}`
    );
export const getPipeline = () => tGet<PipelineResponse>("/twenty/opportunities?group=stage");
export const getOpportunity = (id: string) =>
    tGet<RecordDetail<Opportunity>>(`/twenty/opportunities/${encodeURIComponent(id)}`);
export const createOpportunity = (data: Partial<Opportunity>) =>
    tSend<{ ok: boolean; record: Opportunity }>("POST", "/twenty/opportunities", data);
export const updateOpportunity = (id: string, data: Partial<Opportunity>) =>
    tSend<{ ok: boolean; record: Opportunity }>(
        "PATCH",
        `/twenty/opportunities/${encodeURIComponent(id)}`,
        data
    );
export const deleteOpportunity = (id: string) =>
    tSend<{ ok: boolean }>("DELETE", `/twenty/opportunities/${encodeURIComponent(id)}`);

// ── notes / tasks / value bridge ────────────────────────────────────────────────
export type ActivityTarget = "company" | "person" | "opportunity";
export const addNote = (p: { title?: string; body: string; target_type: ActivityTarget; target_id: string }) =>
    tSend<{ ok: boolean; note: Note }>("POST", "/twenty/notes", p);
export const addTask = (p: {
    title: string;
    body?: string;
    due_at?: string;
    target_type: ActivityTarget;
    target_id: string;
}) => tSend<{ ok: boolean; task: Task }>("POST", "/twenty/tasks", p);

export const syncLeads = (
    leads: { name: string; phone?: string; email?: string; company?: string; status?: string; amount?: number }[],
    create_opportunity = true
) => tSend<SyncResult>("POST", "/twenty/sync/leads", { leads, create_opportunity });
