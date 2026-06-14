// KB Management API client — wraps the 4 backend endpoints added in RAG W3.
//
// All calls are tenant-scoped on the backend (resolve_tenant from JWT), so no
// tenant_id is ever passed in the request body. Auth header: X-Auth JWT.
//
// Endpoints:
//   GET  /kb/sources         -> KbSourcesResponse
//   POST /kb/upload          -> multipart text= or pdf=File -> KbUploadResponse
//   POST /kb/test-retrieve   -> { query, channel?, campaign?, top_k? } -> KbRetrieveResponse
//   GET  /kb/gaps?days=&limit= -> KbGapsResponse

const BASE =
    typeof process !== "undefined" && process.env.NEXT_PUBLIC_API_BASE
        ? process.env.NEXT_PUBLIC_API_BASE
        : "/api";

function getToken(): string | null {
    if (typeof window === "undefined") return null;
    return localStorage.getItem("famit_token");
}

function authHeaders(): Record<string, string> {
    const token = getToken();
    return token ? { "X-Auth": token } : {};
}

async function handle401(res: Response) {
    if (res.status === 401 && typeof window !== "undefined") {
        localStorage.removeItem("famit_token");
        localStorage.removeItem("famit_me");
        window.location.href = "/login";
        throw new Error("Unauthorized");
    }
}

// ---------- Types ----------

export type KbSource = {
    id: string;
    title: string;
    kind: string;          // "text" | "pdf" | ...
    scope: string;         // "global" | "campaign:<id>" | null
    channel_scope: string | null;
    status: string;        // "active" | "processing" | ...
    kb_version: number;
    is_shared: boolean;    // true = _global source visible to all tenants
    chunks: number;
    created_at: string;
    updated_at: string;
};

export type KbSourcesResponse = {
    sources: KbSource[];
    total: number;
    global_count: number;
};

export type KbUploadResponse = {
    ok: boolean;
    source_id: string;
    document_id: string;
    chunks: number;
    embedded: number;
    reason: string;
    title: string;
};

export type KbChunk = {
    id: string;
    source_id: string;
    document_id: string;
    section: string | null;
    snippet: string;
    score: number;
    leg: string;   // "sparse" | "dense"
};

export type KbRetrieveResponse = {
    query: string;
    grounded: boolean;
    count: number;
    chunks: KbChunk[];
};

export type KbGap = {
    query: string;
    count: number;
    last_seen: string;
    channels: string[];
};

export type KbGapsResponse = {
    gaps: KbGap[];
    total: number;
    window_days: number;
};

// ---------- API calls ----------

export async function getKbSources(scopeCampaignId?: string): Promise<KbSourcesResponse> {
    const params = scopeCampaignId ? `?scope_campaign_id=${encodeURIComponent(scopeCampaignId)}` : "";
    const res = await fetch(`${BASE}/kb/sources${params}`, { headers: authHeaders() });
    await handle401(res);
    if (!res.ok) throw new Error(`kb/sources ${res.status}`);
    return res.json();
}

export async function uploadKbText(opts: {
    text: string;
    title?: string;
    scopeCampaignId?: string;
}): Promise<KbUploadResponse> {
    const fd = new FormData();
    fd.append("text", opts.text);
    if (opts.title) fd.append("title", opts.title);
    if (opts.scopeCampaignId) fd.append("scope_campaign_id", opts.scopeCampaignId);
    const res = await fetch(`${BASE}/kb/upload`, {
        method: "POST",
        headers: authHeaders(),
        body: fd,
    });
    await handle401(res);
    if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error((err as { detail?: string }).detail || `kb/upload ${res.status}`);
    }
    return res.json();
}

export async function uploadKbPdf(opts: {
    file: File;
    scopeCampaignId?: string;
}): Promise<KbUploadResponse> {
    const fd = new FormData();
    fd.append("pdf", opts.file);
    if (opts.scopeCampaignId) fd.append("scope_campaign_id", opts.scopeCampaignId);
    const res = await fetch(`${BASE}/kb/upload`, {
        method: "POST",
        headers: authHeaders(),
        body: fd,
    });
    await handle401(res);
    if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error((err as { detail?: string }).detail || `kb/upload ${res.status}`);
    }
    return res.json();
}

export async function testRetrieve(opts: {
    query: string;
    channel?: string;
    campaign?: string;
    top_k?: number;
}): Promise<KbRetrieveResponse> {
    const res = await fetch(`${BASE}/kb/test-retrieve`, {
        method: "POST",
        headers: { ...authHeaders(), "Content-Type": "application/json" },
        body: JSON.stringify(opts),
    });
    await handle401(res);
    if (!res.ok) throw new Error(`kb/test-retrieve ${res.status}`);
    return res.json();
}

export async function getKbGaps(opts?: {
    days?: number;
    limit?: number;
}): Promise<KbGapsResponse> {
    const params = new URLSearchParams();
    if (opts?.days) params.set("days", String(opts.days));
    if (opts?.limit) params.set("limit", String(opts.limit));
    const qs = params.toString() ? `?${params}` : "";
    const res = await fetch(`${BASE}/kb/gaps${qs}`, { headers: authHeaders() });
    await handle401(res);
    if (!res.ok) throw new Error(`kb/gaps ${res.status}`);
    return res.json();
}
