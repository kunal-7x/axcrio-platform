// W15: exported (additive) so the reporting client (lib/report.ts) can hit the
// W14 /report* seam through the SAME base + auth as every other call. No behaviour
// change — these were already the module-internal base/auth used everywhere.
export const BASE =
    typeof process !== "undefined" && process.env.NEXT_PUBLIC_API_BASE
        ? process.env.NEXT_PUBLIC_API_BASE
        : "/api";

function getToken(): string | null {
    if (typeof window === "undefined") return null;
    return localStorage.getItem("famit_token");
}

export function authHeaders(): HeadersInit {
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

// ---- Types ----
export type Campaign = {
    id: string;
    name: string;
    company: string;
    product: string;
    status: string;
    created_at: string;
    // present on GET /campaigns/{cid} (nested under {campaign:{...}}); the audience-builder reads
    // `fields` to hydrate the Voice & Providers card with the campaign's saved tier / voice / providers.
    fields?: CampaignFields;
};

// PVS Phase-1 per-campaign provider+voice config (a subset of the full campaign `fields` object).
// Persisted via POST /campaigns/{cid}. `tier` drives the slider; the *_provider + voice_id are the
// resolved/Advanced overrides; est_avg_call_min + budget_cap_inr feed the cost meter.
export type CampaignTier = "lean" | "standard" | "premium" | "custom";
export type CampaignFields = {
    tier?: CampaignTier;
    voice_id?: string;
    voice_provider?: string;
    stt_provider?: string;
    llm_provider?: string;
    tts_provider?: string;
    custom_provider_id?: string;
    est_avg_call_min?: number;
    budget_cap_inr?: number | string;
    // the backend snapshots the resolved triple so a later tiers.py edit never rewrites in-flight runs.
    tier_resolved?: Record<string, unknown>;
    // catch-all: a campaign carries many other fields we don't touch here (preserve on save).
    [key: string]: unknown;
};

export type Lead = {
    id: string;
    name: string;
    phone: string;
    status: string;
    added_at: string;
    // P0.6 lead scoring
    score?: number;
    last_outcome?: string;
    last_call_at?: string;
    hot?: boolean;
    // Run-Campaign audience builder (additive, back-compat) — present only on
    // leads added via a file upload; legacy rows omit these.
    tags?: string[];
    batch_id?: string;
    source_file?: string;
};

// An uploaded-file lead batch (one CSV/XLSX import = one logical batch).
export type UploadBatch = {
    batch_id: string;
    source_file: string;
    count: number;
    added_at: string;
};

export type CallLog = {
    id: string;
    name: string;
    phone: string;
    campaign_name: string;
    status: string;
    started_at: string;
    ended_at: string;
    duration_s: number;
    // P0.6
    interest?: number;
};

export type Stats = {
    total: number;
    answered: number;
    in_progress: number;
    campaigns: number;
    series: { name: string; amt: number }[];
    // P0.4
    voicemail?: number;
    no_answer?: number;
};

export type ExtractedFields = {
    company_name: string;
    agent_name: string;
    product_name: string;
    product_summary: string;
    location: string;
    price_offer: string;
    usps: string[];
    talking_points: string[];
    objections: { q: string; a: string }[];
    qualifying_questions: string[];
    language: string;
};

export type StatusLead = {
    name: string;
    num: string;
    status: "queued" | "calling" | "done" | "failed";
};

export type JobStatus = {
    state: string;
    leads: StatusLead[];
};

// ---- Auth ----
export type Role = "admin" | "manager" | "agent";

export type LoginResult = {
    token: string;
    tenant_id: string;
    name: string;
    is_admin: boolean;
    role?: Role;
};

export async function login(email: string, password: string): Promise<LoginResult> {
    const fd = new FormData();
    fd.append("email", email);
    fd.append("password", password);
    const res = await fetch(`${BASE}/login`, { method: "POST", body: fd });
    if (!res.ok) throw new Error("Invalid credentials");
    return res.json();
}

// ---- RBAC (Wave 3) ----
export type Me = {
    tenant_id: string;
    email: string;
    name: string;
    role: Role;
    is_admin: boolean;
};

export async function getMe(): Promise<Me> {
    const res = await fetch(`${BASE}/me`, { headers: authHeaders() });
    await handle401(res);
    if (!res.ok) throw new Error("Failed to fetch current user");
    return res.json();
}

// ---- Control Layer (CL-F0) — versioned entitlements ----
// The 3-state verdict the backend resolves per feature_key. Matches the
// `/me/entitlements` contract in design/control-realtime-enforcement.md §1.2.
//   "on"     -> fully available
//   "locked" -> visible-but-locked (upsell overlay; backend 402s the route)
//   "hidden" -> gone everywhere   (backend 404s the route — no existence leak)
export type EntitlementMode = "on" | "locked" | "hidden";

export type EntitlementsPayload = {
    version: number;
    status: string; // active | trial | suspended | disabled | expired
    plan: string;
    modes: Record<string, EntitlementMode>;
};

// Conditional GET with If-None-Match. Returns:
//   { payload, etag }  on a 200 (a real change — caller swaps the map)
//   { notModified:true, etag } on a 304 (cheap no-op — nothing changed)
// Never throws on 304; a 401 still redirects via handle401. A missing/older
// backend (404 on the route) resolves to a permissive all-on map so the panel
// degrades to its pre-control behaviour (resting-state parity).
export type EntitlementsFetch =
    | { notModified: true; etag: string | null; status: number }
    | { notModified: false; payload: EntitlementsPayload; etag: string | null; status: number };

export async function getEntitlements(etag?: string | null): Promise<EntitlementsFetch> {
    const headers: Record<string, string> = { ...(authHeaders() as Record<string, string>) };
    if (etag) headers["If-None-Match"] = etag;
    const res = await fetch(`${BASE}/me/entitlements`, { headers, cache: "no-store" });
    await handle401(res);
    const respEtag = res.headers.get("ETag");
    if (res.status === 304) {
        return { notModified: true, etag: etag ?? respEtag, status: 304 };
    }
    if (res.status === 404) {
        // Backend hasn't shipped the endpoint yet (CONTROL disabled / older box).
        // Resolve to a permissive map so nothing is hidden/locked pre-control.
        return {
            notModified: false,
            status: 404,
            etag: null,
            payload: { version: 0, status: "active", plan: "", modes: {} },
        };
    }
    if (!res.ok) throw new Error("Failed to fetch entitlements");
    const payload = (await res.json()) as EntitlementsPayload;
    return { notModified: false, payload, etag: respEtag ?? null, status: 200 };
}

// ============================================================
// CL-F3 — SUPER ADMIN control plane (/admin/*) bindings.
// All admin-gated server-side (require_super_admin -> 403 for vendors / legacy-pw;
// tenant ALWAYS token-derived). Every write is audited to the immutable events leg
// (channel=control). These are COSMETIC clients — the backend choke-point is the
// only real boundary. Each call degrades gracefully on a 404 (older box / CONTROL
// off / route not mounted) to an empty-but-valid shape so the page never error-walls.
// Contract: caller.py /admin/{features,flags,plans,vendors} + /audit?channel=control.
// ============================================================

// The 3-state verdict, reused from the entitlement contract above.
export type FeatureMode = EntitlementMode; // "on" | "locked" | "hidden"

// One row of the global feature_registry catalog.
export type FeatureRegistryRow = {
    key: string;
    kind: string; // module | page | feature | action | integration | ai_agent | api
    parent_key: string | null;
    label: string;
    nav_href: string | null;
    api_prefixes?: string[];
    default_mode: FeatureMode;
    is_core: boolean;
    min_role?: string | null;
    sort_order?: number;
};

export async function getAdminFeatures(): Promise<{ features: FeatureRegistryRow[] }> {
    const res = await fetch(`${BASE}/admin/features`, { headers: authHeaders() });
    await handle401(res);
    if (res.status === 404) return { features: [] };
    if (!res.ok) throw new Error("Failed to fetch feature catalog");
    return res.json();
}

// Global default_mode per feature_key (the baseline every vendor inherits).
export async function getAdminFlags(): Promise<{ flags: Record<string, FeatureMode> }> {
    const res = await fetch(`${BASE}/admin/flags`, { headers: authHeaders() });
    await handle401(res);
    if (res.status === 404) return { flags: {} };
    if (!res.ok) throw new Error("Failed to fetch global flags");
    return res.json();
}

export type SetFlagResult = { ok: boolean; feature_key: string; before?: FeatureMode; after?: FeatureMode };

// Set the GLOBAL baseline for one feature (affects ALL vendors unless overridden).
export async function setAdminFlag(featureKey: string, mode: FeatureMode): Promise<SetFlagResult> {
    const fd = new FormData();
    fd.append("mode", mode);
    const res = await fetch(`${BASE}/admin/flags/${encodeURIComponent(featureKey)}`, {
        method: "PUT",
        headers: authHeaders(),
        body: fd,
    });
    await handle401(res);
    if (!res.ok) return throwForStatus(res, "Failed to set flag");
    return res.json();
}

// A plan = a reusable bundle of per-feature entitlements + usage limits.
export type AdminPlan = {
    plan_id: string;
    name: string;
    is_default: boolean;
    entitlements: Record<string, FeatureMode>; // only features it overrides off-default
    limits: Record<string, number>; // max_concurrency, daily_call_cap, monthly_minutes_cap, ...
};

export async function getAdminPlans(): Promise<{ plans: AdminPlan[] }> {
    const res = await fetch(`${BASE}/admin/plans`, { headers: authHeaders() });
    await handle401(res);
    if (res.status === 404) return { plans: [] };
    if (!res.ok) throw new Error("Failed to fetch plans");
    return res.json();
}

export async function createAdminPlan(data: { plan_id: string; name?: string; description?: string }): Promise<{ ok: boolean; plan_id: string; name: string }> {
    const fd = new FormData();
    fd.append("plan_id", data.plan_id);
    if (data.name) fd.append("name", data.name);
    if (data.description) fd.append("description", data.description);
    const res = await fetch(`${BASE}/admin/plans`, { method: "POST", headers: authHeaders(), body: fd });
    await handle401(res);
    if (!res.ok) return throwForStatus(res, "Failed to create plan");
    return res.json();
}

// Replace a plan's entitlement + limit bundle (the backend wipes + re-inserts both
// sets, then bumps every tenant on the plan). Sent as JSON per the PUT contract.
export async function updateAdminPlan(
    planId: string,
    body: { entitlements: Record<string, FeatureMode>; limits: Record<string, number> }
): Promise<{ ok: boolean; plan_id: string; entitlements: Record<string, FeatureMode>; limits: Record<string, number> }> {
    const res = await fetch(`${BASE}/admin/plans/${encodeURIComponent(planId)}`, {
        method: "PUT",
        headers: { ...(authHeaders() as Record<string, string>), "Content-Type": "application/json" },
        body: JSON.stringify(body),
    });
    await handle401(res);
    if (!res.ok) return throwForStatus(res, "Failed to update plan");
    return res.json();
}

// Executive vendor row for the Usage analytics + Audit vendor filter.
// NOTE: the vendor list type + getAdminVendors() live in the CL-F1 block below
// (richer AdminVendor / AdminVendorsResponse with an executive summary + a
// /usage/all+/tenants fallback). This unit (CL-F3) reuses those — see Usage page.

// One immutable audit event (the events leg, channel=control). meta carries the
// permission-change before/after, the target vendor, and the acting admin.
export type AuditEvent = {
    ts?: string;
    epoch?: number;
    actor: string;
    actor_role?: string;
    action: string;
    object_type?: string;
    object_id?: string;
    ip?: string;
    channel: string;
    tenant_id: string;
    meta?: {
        target_tenant?: string | null;
        feature_key?: string | null;
        old_value?: string | null;
        new_value?: string | null;
        reason?: string;
        real_admin?: string;
        act_as?: string | null;
        auth_method?: string;
    };
};

export type AuditPage = {
    events: AuditEvent[];
    total: number;
    limit: number;
    offset: number;
    note?: string;
};

// The permission-change log. channel defaults to "control" (every /admin/* write).
export async function getControlAudit(opts?: { limit?: number; offset?: number; action?: string; channel?: string }): Promise<AuditPage> {
    const params = new URLSearchParams();
    params.set("channel", opts?.channel ?? "control");
    if (opts?.limit != null) params.set("limit", String(opts.limit));
    if (opts?.offset != null) params.set("offset", String(opts.offset));
    if (opts?.action) params.set("action", opts.action);
    const res = await fetch(`${BASE}/audit?${params.toString()}`, { headers: authHeaders() });
    await handle401(res);
    if (res.status === 404) return { events: [], total: 0, limit: opts?.limit ?? 100, offset: opts?.offset ?? 0 };
    if (!res.ok) throw new Error("Failed to fetch audit log");
    return res.json();
}

// ============================================================================
// LPR — PLATFORM PROVIDER KEYS (super-admin). Groq / Sarvam / SambaNova /
// OpenRouter keys the founder adds in the panel; stored encrypted on the box;
// the live AIM rotation HOT-RELOADS them (no redeploy). Raw key is NEVER
// returned by the API — only a `masked` value. All routes are require_super_admin.
// ============================================================================
export type ProviderName = "groq" | "sarvam" | "sambanova" | "openrouter";

export type ProviderKeyRow = {
    id: string;
    label: string;
    enabled: boolean;
    added_at: string;
    last_ok_at: number;
    masked: string;
};

export type ProviderKeyStatusRow = {
    id: string;
    label: string;
    masked: string;
    source: "env" | "store";
    enabled: boolean;
    available: boolean;
    cooling: boolean;
    cooling_until: number;
    cooldown_remaining_s: number;
    pick_count: number;
    last_ok_at: number;
    last_429_at: number;
};

const EMPTY_PROVIDERS = { groq: [], sarvam: [], sambanova: [], openrouter: [] };

// List the founder-managed keys per provider (masked). 404/unavailable → empty.
export async function getProviderKeys(): Promise<{ providers: Record<ProviderName, ProviderKeyRow[]> }> {
    try {
        const res = await fetch(`${BASE}/admin/provider-keys`, { headers: authHeaders() });
        await handle401(res);
        if (!res.ok) return { providers: { ...EMPTY_PROVIDERS } as Record<ProviderName, ProviderKeyRow[]> };
        return res.json();
    } catch {
        return { providers: { ...EMPTY_PROVIDERS } as Record<ProviderName, ProviderKeyRow[]> };
    }
}

// Live pool view (cooling / pick_count / available) — polled by the page ~5s.
export async function getProviderKeyStatus(): Promise<{ status: Record<ProviderName, ProviderKeyStatusRow[]> }> {
    try {
        const res = await fetch(`${BASE}/admin/provider-keys/status`, { headers: authHeaders() });
        await handle401(res);
        if (!res.ok) return { status: { ...EMPTY_PROVIDERS } as Record<ProviderName, ProviderKeyStatusRow[]> };
        return res.json();
    } catch {
        return { status: { ...EMPTY_PROVIDERS } as Record<ProviderName, ProviderKeyStatusRow[]> };
    }
}

export async function addProviderKey(provider: ProviderName, key: string, label?: string): Promise<{ ok: boolean; id: string; provider: string; masked: string; deduped?: boolean }> {
    const fd = new FormData();
    fd.append("provider", provider);
    fd.append("key", key);
    if (label) fd.append("label", label);
    const res = await fetch(`${BASE}/admin/provider-keys`, { method: "POST", headers: authHeaders(), body: fd });
    await handle401(res);
    if (!res.ok) return throwForStatus(res, "Failed to add key");
    return res.json();
}

export async function updateProviderKey(id: string, body: { enabled?: boolean; label?: string }): Promise<{ ok: boolean; id: string }> {
    const fd = new FormData();
    if (body.enabled != null) fd.append("enabled", body.enabled ? "1" : "0");
    if (body.label != null) fd.append("label", body.label);
    const res = await fetch(`${BASE}/admin/provider-keys/${encodeURIComponent(id)}`, { method: "PUT", headers: authHeaders(), body: fd });
    await handle401(res);
    if (!res.ok) return throwForStatus(res, "Failed to update key");
    return res.json();
}

export async function deleteProviderKey(id: string): Promise<{ ok: boolean; deleted: boolean; id: string }> {
    const res = await fetch(`${BASE}/admin/provider-keys/${encodeURIComponent(id)}`, { method: "DELETE", headers: authHeaders() });
    await handle401(res);
    if (!res.ok) return throwForStatus(res, "Failed to delete key");
    return res.json();
}

// ---- Campaigns ----
export async function getCampaigns(): Promise<{ campaigns: Campaign[] }> {
    const res = await fetch(`${BASE}/campaigns`, {
        headers: authHeaders(),
    });
    await handle401(res);
    if (!res.ok) throw new Error("Failed to fetch campaigns");
    return res.json();
}

export async function saveCampaign(
    fields: Record<string, unknown>
): Promise<{ id: string; name: string }> {
    const fd = new FormData();
    fd.append("fields_json", JSON.stringify(fields));
    const res = await fetch(`${BASE}/campaigns`, {
        method: "POST",
        headers: authHeaders(),
        body: fd,
    });
    await handle401(res);
    if (!res.ok) throw new Error("Failed to save campaign");
    return res.json();
}

export async function deleteCampaign(id: string): Promise<{ deleted: boolean }> {
    const res = await fetch(`${BASE}/campaigns/${id}`, {
        method: "DELETE",
        headers: authHeaders(),
    });
    await handle401(res);
    if (!res.ok) throw new Error("Failed to delete campaign");
    return res.json();
}

// Single campaign detail. The backend envelope is NESTED: {campaign:{...,fields:{...}}}.
// Dormant-safe: 404/offline -> null so the audience builder just shows defaults.
export async function getCampaign(cid: string): Promise<Campaign | null> {
    try {
        const res = await fetch(`${BASE}/campaigns/${encodeURIComponent(cid)}`, {
            headers: authHeaders(),
        });
        await handle401(res);
        if (!res.ok) return null;
        const data = await res.json();
        return (data?.campaign ?? null) as Campaign | null;
    } catch {
        return null;
    }
}

// Update an existing campaign's fields (incl. PVS tier/voice/provider) via POST /campaigns/{cid}.
// The backend merges these into the full `fields` object + rebuilds the system prompt. Callers MUST
// pass the FULL fields object (merge their delta onto the campaign's existing fields first) — the
// backend replaces `fields` wholesale, it does not patch.
export async function updateCampaign(
    cid: string,
    fields: Record<string, unknown>
): Promise<{ id: string; name: string }> {
    const fd = new FormData();
    fd.append("fields_json", JSON.stringify(fields));
    const res = await fetch(`${BASE}/campaigns/${encodeURIComponent(cid)}`, {
        method: "POST",
        headers: authHeaders(),
        body: fd,
    });
    await handle401(res);
    if (!res.ok) throw new Error("Failed to update campaign");
    return res.json();
}

// ---- Extract ----
export async function extract(brief: string): Promise<ExtractedFields> {
    const fd = new FormData();
    fd.append("brief", brief);
    const res = await fetch(`${BASE}/extract`, {
        method: "POST",
        headers: authHeaders(),
        body: fd,
    });
    await handle401(res);
    if (!res.ok) throw new Error("Failed to extract");
    return res.json();
}

// ---- Leads ----
// PERF UNIT-3: opt-in server pagination (backend UNIT-1 contract). Legacy callers
// (no limit/offset) get ALL leads exactly as before; `total`/`next` are additive
// sibling keys so the response is backward-compatible. Pass `limit`/`offset` to page.
export type LeadsPage = {
    leads: Lead[];
    total?: number;
    offset?: number;
    limit?: number;
    next?: number | null;
};
export async function getLeads(opts?: {
    hot?: boolean;
    sort?: string;
    batch?: string;
    limit?: number;
    offset?: number;
}): Promise<LeadsPage> {
    const params = new URLSearchParams();
    if (opts?.hot) params.set("hot", "1");
    if (opts?.sort) params.set("sort", opts.sort);
    if (opts?.batch) params.set("batch", opts.batch);
    if (opts?.limit != null) params.set("limit", String(opts.limit));
    if (opts?.offset != null && opts.offset > 0) params.set("offset", String(opts.offset));
    const qs = params.toString();
    const res = await fetch(`${BASE}/leads${qs ? `?${qs}` : ""}`, {
        headers: authHeaders(),
    });
    await handle401(res);
    if (!res.ok) throw new Error("Failed to fetch leads");
    return res.json();
}

// Distinct upload batches for the tenant. Graceful: if the backend has not
// shipped GET /leads/batches yet (404), resolve to an empty list so the UI
// degrades to all-stored instead of erroring.
export async function getLeadBatches(): Promise<{ batches: UploadBatch[] }> {
    const res = await fetch(`${BASE}/leads/batches`, { headers: authHeaders() });
    await handle401(res);
    if (res.status === 404) return { batches: [] };
    if (!res.ok) throw new Error("Failed to fetch lead batches");
    const data = await res.json().catch(() => ({}));
    return { batches: Array.isArray(data?.batches) ? data.batches : [] };
}

export async function addLeads(
    text: string,
    file?: File | null
): Promise<{ added: number; total: number; batch_id?: string; source_file?: string }> {
    const fd = new FormData();
    fd.append("leads", text);
    // CSV + XLSX both ride the same "csv" form field; the server routes by
    // filename/content-type (openpyxl for .xlsx, stdlib csv otherwise).
    if (file) fd.append("csv", file);
    const res = await fetch(`${BASE}/leads`, {
        method: "POST",
        headers: authHeaders(),
        body: fd,
    });
    await handle401(res);
    if (!res.ok) throw new Error("Failed to add leads");
    return res.json();
}

// ---- Lead deletes (tenant-scoped, BOLA-guarded on the backend) ----
// Single lead by id. Backend: DELETE /leads/{id} (404 if missing/not owned).
export async function deleteLead(id: string): Promise<{ deleted: string; total: number }> {
    const res = await fetch(`${BASE}/leads/${encodeURIComponent(id)}`, {
        method: "DELETE",
        headers: authHeaders(),
    });
    await handle401(res);
    if (!res.ok) throw new Error("Failed to delete lead");
    return res.json();
}

// Bulk delete a set of ids (multi-select). Idempotent: unknown/cross-tenant ids
// are skipped server-side. Backend: POST /leads/delete (form field `ids`).
export async function deleteLeadsBulk(ids: string[]): Promise<{ deleted: number; total: number }> {
    const fd = new FormData();
    fd.append("ids", ids.join(","));
    const res = await fetch(`${BASE}/leads/delete`, {
        method: "POST",
        headers: authHeaders(),
        body: fd,
    });
    await handle401(res);
    if (!res.ok) throw new Error("Failed to delete leads");
    return res.json();
}

// Delete ALL of this tenant's leads (destructive, confirm-gated). The backend
// requires ?confirm=DELETE and is STRICTLY tenant-scoped (never cross-tenant).
export async function deleteAllLeads(): Promise<{ deleted: number; total: number }> {
    const res = await fetch(`${BASE}/leads?confirm=DELETE`, {
        method: "DELETE",
        headers: authHeaders(),
    });
    await handle401(res);
    if (!res.ok) throw new Error("Failed to delete all leads");
    return res.json();
}

// ---- Run ----
export type RunPayload = {
    campaign_id: string;
    leads: string;
    use_stored?: boolean;
    concurrency?: number;
    hourly_cap?: number;
    daily_cap?: number;
    csv?: File | null;
    force?: boolean;
    // Run-Campaign audience builder: explicit, resolved audience. When present
    // the backend dials exactly these (BOLA-guarded to the tenant's own leads)
    // and ignores use_stored/leads. Sent as a comma-separated string for
    // maximum form-field compatibility.
    lead_ids?: string[];
};

export type RunResult = {
    job_id: string;
    count: number;
    queued_out_of_window?: boolean;
    window?: string;
    suppressed_count?: number;
};

// Typed error for /run failures. Carries the parsed body so callers can
// surface the 402 insufficient-balance shape (Wave 3) without crashing.
export class RunError extends Error {
    status: number;
    code: string; // "insufficient_balance" | "monthly_cap" | "permission" | "generic"
    body: Record<string, unknown>;
    constructor(status: number, code: string, message: string, body: Record<string, unknown>) {
        super(message);
        this.name = "RunError";
        this.status = status;
        this.code = code;
        this.body = body;
    }
}

export async function run(
    payload: RunPayload
): Promise<RunResult> {
    const fd = new FormData();
    fd.append("campaign_id", payload.campaign_id);
    fd.append("leads", payload.leads);
    if (payload.use_stored) fd.append("use_stored", "1");
    if (payload.concurrency != null)
        fd.append("concurrency", String(payload.concurrency));
    if (payload.hourly_cap != null)
        fd.append("hourly_cap", String(payload.hourly_cap));
    if (payload.daily_cap != null)
        fd.append("daily_cap", String(payload.daily_cap));
    if (payload.csv) fd.append("csv", payload.csv);
    if (payload.force) fd.append("force", "1");
    if (payload.lead_ids && payload.lead_ids.length > 0)
        fd.append("lead_ids", payload.lead_ids.join(","));
    const res = await fetch(`${BASE}/run`, {
        method: "POST",
        headers: authHeaders(),
        body: fd,
    });
    await handle401(res);
    if (!res.ok) {
        let body: Record<string, unknown> = {};
        try { body = await res.json(); } catch { /* non-JSON */ }
        const err = typeof body.error === "string" ? body.error : "";
        if (res.status === 402) {
            throw new RunError(402, "insufficient_balance",
                (typeof body.message === "string" && body.message) || "Insufficient balance — top up to continue.", body);
        }
        if (res.status === 429) {
            throw new RunError(429, "monthly_cap", err || "Monthly minutes cap reached.", body);
        }
        if (res.status === 403) {
            throw new RunError(403, "permission", err || "You don't have permission to run calls.", body);
        }
        throw new RunError(res.status, "generic", err || "Failed to start run", body);
    }
    return res.json();
}

// ---- Status ----
export async function getStatus(job: string): Promise<JobStatus> {
    const res = await fetch(`${BASE}/status?job=${encodeURIComponent(job)}`, {
        headers: authHeaders(),
    });
    await handle401(res);
    if (!res.ok) throw new Error("Failed to fetch status");
    return res.json();
}

// ---- Calls ----
// PERF UNIT-3: opt-in server pagination (backend UNIT-1 contract). A bare
// getCalls() is byte-identical to the legacy call (`/calls?limit=200`, full rows,
// storage order) so existing call sites keep working untouched. Pass opts to
// paginate: `offset`/`order=desc`/`slim=1` trigger the SLIM newest-first paged
// response `{calls, total, offset, limit, next}` (`next` = the offset to fetch the
// next page, or null on the last page).
export type CallsPage = {
    calls: CallLog[];
    total?: number;
    offset?: number;
    limit?: number;
    next?: number | null;
};
export type GetCallsOpts = {
    limit?: number;
    offset?: number;
    order?: "desc";
    slim?: boolean;
    campaign_id?: string;
    outcome?: string;
};
export async function getCalls(opts?: GetCallsOpts): Promise<CallsPage> {
    const params = new URLSearchParams();
    params.set("limit", String(opts?.limit ?? 200));
    if (opts?.offset != null && opts.offset > 0) params.set("offset", String(opts.offset));
    if (opts?.order === "desc") params.set("order", "desc");
    if (opts?.slim) params.set("slim", "1");
    if (opts?.campaign_id) params.set("campaign_id", opts.campaign_id);
    if (opts?.outcome) params.set("outcome", opts.outcome);
    const res = await fetch(`${BASE}/calls?${params.toString()}`, {
        headers: authHeaders(),
    });
    await handle401(res);
    if (!res.ok) throw new Error("Failed to fetch calls");
    return res.json();
}

export type CallTranscriptTurn = {
    role: string;
    content: string;
};

export type CallDetail = {
    call: CallLog;
    transcript: {
        turns: CallTranscriptTurn[];
        summary: string;
        outcome: string;
        interest: string;
        next_action: string;
        // P0.3 opt-out
        opt_out?: boolean;
    };
};

export async function getCallDetail(id: string): Promise<CallDetail> {
    const res = await fetch(`${BASE}/calls/${encodeURIComponent(id)}`, {
        headers: authHeaders(),
    });
    await handle401(res);
    if (!res.ok) throw new Error("Failed to fetch call detail");
    return res.json();
}

// ---- Voices ----
// PVS Phase-1: the backend now un-strips ElevenLabs' free public `preview_url` and adds
// accent/gender/language + a `sample_url` (the /voice-preview proxy path). Sarvam returns a
// fixed speaker catalogue with the same shape. All additive + back-compat (legacy callers that
// only read voice_id/name still work).
export type Voice = {
    voice_id: string;
    name: string;
    preview_url?: string;
    accent?: string;
    gender?: string;
    language?: string;
    sample_url?: string;
};

export type VoiceProvider = "elevenlabs" | "sarvam";

// getVoices(provider?) — omit for ElevenLabs (default), pass "sarvam" for the Bulbul speakers.
// Dormant-safe: any failure resolves to an empty list so the UI degrades, never an error wall.
export async function getVoices(
    provider?: VoiceProvider
): Promise<{ provider: string; voices: Voice[] }> {
    try {
        const qs = provider ? `?provider=${encodeURIComponent(provider)}` : "";
        const res = await fetch(`${BASE}/voices${qs}`, { headers: authHeaders() });
        await handle401(res);
        if (!res.ok) return { provider: provider || "elevenlabs", voices: [] };
        return res.json();
    } catch {
        return { provider: provider || "elevenlabs", voices: [] };
    }
}

// FREE play-preview URL for the shared <audio>. ElevenLabs -> 307 to the public GCS clip (no key,
// no synth, zero burn); Sarvam -> the pre-hosted one-time sample. The token is appended as a query
// param because an <audio src> cannot send the X-Auth header. NOTE: /voice-preview is behind
// authed() which reads X-Auth; the panel proxies /api/* through Next so same-origin <audio> works
// when the token is in the header path — for the <audio> we rely on the existing /api proxy auth.
export function voicePreviewUrl(provider: VoiceProvider, id: string): string {
    const params = new URLSearchParams({ provider, id });
    const tok = getToken();
    if (tok) params.set("t", tok); // backend ignores unknown params; harmless if proxy injects auth
    return `${BASE}/voice-preview?${params.toString()}`;
}

// ---- Providers (built-in + custom) per role ----
export type ProviderInfo = {
    id: string;
    name: string;
    builtin: boolean;
    kinds: string[];
    available: boolean;
    // custom-only extras
    kind?: string;
    model?: string;
    base_url?: string;
    enabled?: boolean;
    masked?: string;
};

export type ProvidersByRole = {
    stt: { id: string; name: string; builtin: boolean; available: boolean }[];
    llm: { id: string; name: string; builtin: boolean; available: boolean }[];
    tts: { id: string; name: string; builtin: boolean; available: boolean }[];
};

const EMPTY_BY_ROLE: ProvidersByRole = { stt: [], llm: [], tts: [] };

// Dormant-safe: 404/offline -> empty so the Voice & Providers card simply shows no providers.
export async function getProviders(): Promise<{ providers: ProviderInfo[]; by_role: ProvidersByRole }> {
    try {
        const res = await fetch(`${BASE}/providers`, { headers: authHeaders() });
        await handle401(res);
        if (!res.ok) return { providers: [], by_role: { ...EMPTY_BY_ROLE } };
        return res.json();
    } catch {
        return { providers: [], by_role: { ...EMPTY_BY_ROLE } };
    }
}

// ---- Tiers (single source of truth for the slider mapping + cost-meter math) ----
export type TierRole = { provider: string; model: string; rate_key: string };
export type TierVoice = { provider: string; voice_id: string };
export type Tier = {
    key: "lean" | "standard" | "premium";
    name: string;
    quality: string;
    blurb: string;
    est_inr_per_min: number;
    stt: TierRole;
    llm: TierRole;
    tts: TierRole;
    voice: TierVoice;
};
export type RateCard = {
    assumptions: {
        tts_chars_per_min: number;
        llm_tokens_per_min: number;
        default_avg_call_min: number;
    };
    stt: Record<string, { label: string; inr_per_min: number }>;
    llm: Record<string, { label: string; inr_per_mtok: number }>;
    tts: Record<string, { label: string; inr_per_1k: number }>;
    telephony_inr_per_min: number;
    // ── WAVE C honesty fields (all OPTIONAL → dormant-safe) ──
    // Telephony (Vobiz SIP) has NO published per-min rate. When `telephony_verified`
    // is falsy the cost meter renders an "est. — pending your real Vobiz CDR" caption
    // and NEVER a hard fabricated ₹. Set true only once a real CDR rate is wired.
    telephony_verified?: boolean;
    telephony_note?: string;
    // Source attribution per row (URL + date) for the ⓘ tooltips in the breakdown.
    sources?: Record<string, string>;
    fx_usd_inr?: number;
};
export type TiersPayload = {
    tiers: Tier[];
    order: string[];
    default: string;
    rate_card: RateCard;
    cost_formula?: Record<string, string>;
    phase_note?: string;
    ob_prov_pending?: boolean;
    // ── WAVE C: provider-lock live state ──
    // false / undefined → CONFIG-ONLY (today's truth: engine still honours its
    // configured outbound provider; the per-campaign override is saved but the
    // OUTBOUND honoring is gated). true → LIVE (selected provider runs + is billed).
    ob_prov_live?: boolean;
    // Inbound provider-lock label is truthful NOW (session-log); outbound gated.
    inbound_prov_lock?: boolean;
};

// Dormant-safe: returns the set of lead IDs already called in this campaign so the
// audience step can offer an "exclude already-called" toggle. Reuses GET /calls
// filtered by campaign — no new backend route. Any failure / 404 → empty set
// (toggle silently excludes nothing). Matches on call.id AND phone so it works
// whether the run payload is keyed by lead id or number.
export async function getCalledLeadKeys(campaignId: string): Promise<Set<string>> {
    const keys = new Set<string>();
    if (!campaignId) return keys;
    try {
        const page = await getCalls({ campaign_id: campaignId, limit: 1000 });
        for (const c of page.calls || []) {
            if (c.id) keys.add(String(c.id));
            if (c.phone) keys.add(String(c.phone));
        }
    } catch {
        /* dormant-safe: no rows → exclude nothing */
    }
    return keys;
}

// Dormant-safe campaign-level Cost-Per-Lead summary. Joins the billing cost
// explorer total ÷ qualified-call count (reuses GET /billing/explorer — no new
// route). Returns nulls on any failure so the CPL line simply hides.
export type CampaignCPL = {
    totalCost: number | null;
    calls: number;
    qualified: number;
    cpl: number | null; // total ÷ qualified
    cpc: number | null; // total ÷ calls
    currency: string;
};
export async function getCampaignCPL(campaignId: string): Promise<CampaignCPL> {
    const empty: CampaignCPL = {
        totalCost: null,
        calls: 0,
        qualified: 0,
        cpl: null,
        cpc: null,
        currency: "INR",
    };
    if (!campaignId) return empty;
    try {
        const ex = await getBillingExplorer({ campaign_id: campaignId });
        const rows = ex.rows || [];
        const calls = rows.length;
        // "qualified" = a connected outcome that progressed (heuristic, no new field):
        // any outcome that isn't a plain no-answer / failed / voicemail.
        const isQualified = (o?: string) => {
            const s = (o || "").toLowerCase();
            if (!s) return false;
            return !/no[\s_-]?answer|failed|busy|voicemail|declined|missed/.test(s);
        };
        const qualified = rows.filter((r) => isQualified(r.outcome)).length;
        const total = typeof ex.total === "number" ? ex.total : null;
        return {
            totalCost: total,
            calls,
            qualified,
            cpl: total != null && qualified > 0 ? total / qualified : null,
            cpc: total != null && calls > 0 ? total / calls : null,
            currency: ex.currency || "INR",
        };
    } catch {
        return empty;
    }
}

// Dormant-safe: returns null on any failure so the card hides the slider gracefully.
export async function getTiers(): Promise<TiersPayload | null> {
    try {
        const res = await fetch(`${BASE}/tiers`, { headers: authHeaders() });
        await handle401(res);
        if (!res.ok) return null;
        return res.json();
    } catch {
        return null;
    }
}

// ---- Custom providers (super-admin; isolated Fernet store, NOT the live key pool) ----
export type CustomProvider = {
    id: string;
    name: string;
    kind: "stt" | "llm" | "tts";
    base_url: string;
    model: string;
    enabled: boolean;
    added_at?: string;
    masked: string;
    available: boolean;
};

export async function getCustomProviders(): Promise<{ custom_providers: CustomProvider[] }> {
    try {
        const res = await fetch(`${BASE}/admin/custom-providers`, { headers: authHeaders() });
        await handle401(res);
        if (!res.ok) return { custom_providers: [] };
        return res.json();
    } catch {
        return { custom_providers: [] };
    }
}

export async function addCustomProvider(data: {
    name: string;
    kind: "stt" | "llm" | "tts";
    base_url: string;
    model: string;
    key: string;
}): Promise<{ ok: boolean; id: string; name: string; kind: string; model: string; masked: string }> {
    const fd = new FormData();
    fd.append("name", data.name);
    fd.append("kind", data.kind);
    fd.append("base_url", data.base_url);
    fd.append("model", data.model);
    if (data.key) fd.append("key", data.key);
    const res = await fetch(`${BASE}/admin/custom-providers`, {
        method: "POST",
        headers: authHeaders(),
        body: fd,
    });
    await handle401(res);
    if (!res.ok) return throwForStatus(res, "Failed to add custom provider");
    return res.json();
}

export async function updateCustomProvider(
    id: string,
    body: { enabled?: boolean; name?: string; base_url?: string; model?: string; key?: string }
): Promise<{ ok: boolean; id: string }> {
    const fd = new FormData();
    if (body.enabled != null) fd.append("enabled", body.enabled ? "1" : "0");
    if (body.name != null) fd.append("name", body.name);
    if (body.base_url != null) fd.append("base_url", body.base_url);
    if (body.model != null) fd.append("model", body.model);
    if (body.key != null) fd.append("key", body.key);
    const res = await fetch(`${BASE}/admin/custom-providers/${encodeURIComponent(id)}`, {
        method: "PUT",
        headers: authHeaders(),
        body: fd,
    });
    await handle401(res);
    if (!res.ok) return throwForStatus(res, "Failed to update custom provider");
    return res.json();
}

export async function deleteCustomProvider(
    id: string
): Promise<{ ok: boolean; deleted: boolean; id: string }> {
    const res = await fetch(`${BASE}/admin/custom-providers/${encodeURIComponent(id)}`, {
        method: "DELETE",
        headers: authHeaders(),
    });
    await handle401(res);
    if (!res.ok) return throwForStatus(res, "Failed to delete custom provider");
    return res.json();
}

// ---- Tenants ----
export type Tenant = {
    tenant_id: string;
    email: string;
    name: string;
    is_admin: boolean;
    role?: Role;
    created_at: string;
};

export async function getTenants(): Promise<{ tenants: Tenant[] }> {
    const res = await fetch(`${BASE}/tenants`, {
        headers: authHeaders(),
    });
    await handle401(res);
    if (!res.ok) throw new Error("Failed to fetch tenants");
    return res.json();
}

export async function createTenant(data: { name: string; email: string; password: string; role?: Role }): Promise<{ tenant_id: string; email: string; name: string; role: Role }> {
    const fd = new FormData();
    fd.append("name", data.name);
    fd.append("email", data.email);
    fd.append("password", data.password);
    if (data.role) fd.append("role", data.role);
    const res = await fetch(`${BASE}/tenants`, {
        method: "POST",
        headers: authHeaders(),
        body: fd,
    });
    await handle401(res);
    if (!res.ok) throw new Error("Failed to create vendor");
    return res.json();
}

// ============================================================
// CONTROL LAYER (CL-F1) — Super Admin fleet binding (THE canonical /admin/vendors
// client; CL-F3's Usage/Audit pages reuse AdminVendor + getAdminVendors from here,
// per the note in the CL-F3 block above). The /admin/* surface is the admin plane:
// admin-gated server-side by require_super_admin (which EXCLUDES the legacy static
// password — the #1 security finding) and tenant ALWAYS token-derived. This is a
// COSMETIC read; the backend choke-point is the only real boundary.
//
// GRACEFUL: if /admin/vendors isn't mounted yet (404 while CONTROL_ENABLED=0), we
// compose an equivalent list from the two endpoints that ARE live + admin-gated —
// /usage/all (per-tenant calls/minutes) joined with /tenants (name/email/role) —
// so the Super Admin pages render real data today and auto-upgrade to the richer
// payload the moment the route lands.
// ============================================================

// A vendor (tenant) account status in the control plane.
export type VendorAccountStatus =
    | "active"
    | "trial"
    | "suspended"
    | "disabled"
    | "expired";

// One vendor row as the Super Admin pages render it (a flattened executive view
// of the spec's {tenant_id,name,email,plan,status,created_at,usage_summary,health}).
// All rollup fields optional so a partial backend / the composed fallback degrade
// gracefully.
export type AdminVendor = {
    tenant_id: string;
    name: string;
    email: string;
    plan?: string;
    status?: VendorAccountStatus;
    created_at?: string;
    role?: Role;
    usage_summary?: {
        calls_today?: number;
        calls_30d?: number;
        minutes_30d?: number;
        credits_burned?: number;
        active_now?: number;
    };
    health?: {
        last_activity?: string;
        last_login?: string;
        last_call_at?: string;
        alerts?: number;
    };
};

export type AdminVendorSummary = {
    total: number;
    active: number;
    suspended: number;
    trial?: number;
    disabled?: number;
    expired?: number;
    calls_today?: number;
    minutes_30d?: number;
    credits_burned?: number;
    alerts?: number;
};

export type AdminVendorsResponse = {
    vendors: AdminVendor[];
    // Fleet KPI rollup the Control Overview reads directly. Optional: derived
    // client-side when a backend omits it (and always supplied by the fallback).
    summary?: AdminVendorSummary;
    currency?: string;
};

function coerceVendorStatus(s?: string | null): VendorAccountStatus {
    const v = (s || "").toLowerCase();
    if (v === "suspended" || v === "disabled" || v === "expired" || v === "trial" || v === "active") {
        return v as VendorAccountStatus;
    }
    // Legacy tenant store has no status field yet — treat as active.
    return "active";
}

// Normalize a raw /admin/vendors row into the flat AdminVendor view. The backend
// may send the executive `{usage:{today,month}, health:{active_now,last_call}}`
// shape (spec §4) OR already-flattened `usage_summary`/`health` — accept both.
function toAdminVendor(r: Record<string, unknown>): AdminVendor {
    const usage = (r.usage ?? {}) as { today?: { calls?: number; minutes?: number }; month?: { calls?: number; minutes?: number } };
    const us = (r.usage_summary ?? {}) as AdminVendor["usage_summary"];
    const h = (r.health ?? {}) as { active_now?: number; last_call?: string; last_activity?: string; last_call_at?: string; last_login?: string; alerts?: number };
    return {
        tenant_id: String(r.tenant_id ?? ""),
        name: String(r.name ?? r.tenant_id ?? ""),
        email: String(r.email ?? ""),
        role: r.role as Role | undefined,
        plan: (r.plan as string | null) ?? undefined,
        status: coerceVendorStatus(r.status as string | undefined),
        created_at: r.created_at as string | undefined,
        usage_summary: {
            calls_today: us?.calls_today ?? usage.today?.calls ?? 0,
            calls_30d: us?.calls_30d ?? usage.month?.calls ?? 0,
            minutes_30d: us?.minutes_30d ?? usage.month?.minutes ?? 0,
            credits_burned: us?.credits_burned ?? 0,
            active_now: us?.active_now ?? h.active_now ?? 0,
        },
        health: {
            last_activity: h.last_activity ?? h.last_call ?? undefined,
            last_call_at: h.last_call_at ?? h.last_call ?? undefined,
            last_login: h.last_login ?? undefined,
            alerts: h.alerts ?? 0,
        },
    };
}

function deriveVendorSummary(vendors: AdminVendor[]): AdminVendorSummary {
    const count = (st: string) => vendors.filter((v) => (v.status ?? "active") === st).length;
    return {
        total: vendors.length,
        active: count("active"),
        suspended: count("suspended"),
        trial: count("trial"),
        disabled: count("disabled"),
        expired: count("expired"),
        calls_today: vendors.reduce((s, v) => s + (v.usage_summary?.calls_today ?? 0), 0),
        minutes_30d: vendors.reduce((s, v) => s + (v.usage_summary?.minutes_30d ?? 0), 0),
        credits_burned: vendors.reduce((s, v) => s + (v.usage_summary?.credits_burned ?? 0), 0),
        alerts: vendors.reduce((s, v) => s + (v.health?.alerts ?? 0), 0),
    };
}

// GET /admin/vendors — the fleet list (THE single /admin/vendors client).
export async function getAdminVendors(): Promise<AdminVendorsResponse> {
    const res = await fetch(`${BASE}/admin/vendors`, { headers: authHeaders() });
    await handle401(res);
    if (res.ok) {
        const data = (await res.json()) as { vendors?: Record<string, unknown>[]; summary?: AdminVendorSummary; currency?: string };
        const vendors = (data.vendors || []).map(toAdminVendor);
        return { vendors, summary: data.summary ?? deriveVendorSummary(vendors), currency: data.currency };
    }
    if (res.status !== 404) throw new Error("Failed to load vendors");

    // ---- Fallback: compose from /usage/all + /tenants (both admin-gated) ----
    const [usage, tenants] = await Promise.all([
        getUsageAll().catch(() => ({ tenants: [] as TenantUsageRow[] })),
        getTenants().catch(() => ({ tenants: [] as Tenant[] })),
    ]);
    const tById = new Map(tenants.tenants.map((t) => [t.tenant_id, t]));
    const uById = new Map(usage.tenants.map((u) => [u.tenant_id, u]));
    const ids = new Set<string>([...tById.keys(), ...uById.keys()]);

    const vendors: AdminVendor[] = [...ids].map((id) => {
        const t = tById.get(id);
        const u = uById.get(id);
        return {
            tenant_id: id,
            name: t?.name || u?.name || id,
            email: t?.email || "",
            role: t?.role,
            plan: undefined,
            status: coerceVendorStatus(undefined),
            created_at: t?.created_at,
            usage_summary: {
                calls_today: u?.today.calls ?? 0,
                calls_30d: u?.month.calls ?? 0,
                minutes_30d: u?.month.minutes ?? 0,
                active_now: u?.active_now ?? 0,
            },
            health: {},
        };
    });

    return { vendors, summary: deriveVendorSummary(vendors) };
}

// ---- Back-compat aliases for the CL-F1 pages (authored against Fleet* names).
// Same single binding — no extra fetch. Keeps both naming worlds compiling.
export type FleetVendor = AdminVendor;
export type FleetSummary = AdminVendorSummary;
export type FleetVendorsResponse = AdminVendorsResponse;
export const getFleetVendors = getAdminVendors;

// ============================================================
// CONTROL LAYER (CL-F2) — Vendor Workspace + the PERMISSION MATRIX
// The single-vendor admin surface: GET /admin/vendors/{id} returns the full
// profile + the RESOLVED entitlement map (effective mode + provenance) + usage
// + health + wallet. The matrix writes per-vendor overrides. Every write is
// admin-gated + audited server-side (channel="control"); the BACKEND middleware
// (require_super_admin, legacy-auth EXCLUDED) is the only real boundary — these
// bindings are cosmetic admin tooling. tenant_id is token-derived, never body.
// Reuses CL-F3's FeatureMode + AdminPlan/getAdminPlans + CL-F1's
// VendorAccountStatus (one client, no re-declaration).
// Contract: design/spec-control-layer.md §4 + design/control-datamodel.md §3.
// ============================================================

// Where a resolved mode came from (the resolution chain) — drives the
// provenance pill in the matrix. "status" = forced by a suspended/disabled gate;
// "parent" = rolled down from a hidden/locked ancestor module.
export type EntitlementProvenance =
    | "global"
    | "plan"
    | "override"
    | "status"
    | "parent";

// One catalog node of the feature_registry (design/control-datamodel.md §0).
export type FeatureRegistryNode = {
    key: string; // canonical dot-path, e.g. "engage.calls"
    kind: "module" | "page" | "feature" | "action" | "integration" | "ai_agent" | "api";
    parent_key: string | null;
    label: string;
    nav_href?: string | null;
    is_core?: boolean;
    sort_order?: number;
};

// One resolved matrix row: the catalog node + its effective mode for THIS vendor
// + where that mode came from + (if set) the raw per-vendor override + the
// global/plan hints.
export type ResolvedEntitlement = FeatureRegistryNode & {
    mode: FeatureMode; // effective, post-rolldown
    provenance: EntitlementProvenance;
    override?: FeatureMode | null; // the explicit per-vendor override row, if any
    default_mode?: FeatureMode; // the global registry baseline
    plan_mode?: FeatureMode | null; // the plan-layer mode, if the plan sets one
};

// GET /admin/vendors/{id} payload — one fetch feeds the whole workspace.
export type AdminVendorDetail = {
    tenant_id: string;
    name: string;
    email: string;
    phone?: string;
    role?: Role;
    plan?: string;
    status?: VendorAccountStatus;
    created_at?: string;
    ent_version?: number;
    entitlements: ResolvedEntitlement[]; // the resolved permission matrix
    usage?: {
        calls_today?: number;
        calls_30d?: number;
        minutes_30d?: number;
        credits_burned?: number;
        active_now?: number;
        leads?: number;
        campaigns?: number;
        whatsapp_30d?: number;
        spend_30d?: number;
    };
    limits?: {
        max_concurrency?: number;
        daily_call_cap?: number;
        monthly_minutes_cap?: number;
    };
    health?: {
        last_activity?: string;
        last_login?: string;
        last_call_at?: string;
        last_campaign_at?: string;
        alerts?: number;
    };
    wallet?: {
        balance?: number;
        held?: number;
        currency?: string;
    };
};

// ---- STATIC FEATURE REGISTRY SEED -------------------------------------------
// Verbatim from design/control-datamodel.md §0 (the catalog derived 1:1 from the
// live nav). The fallback catalog when the backend hasn't shipped
// /admin/vendors/{id} yet (CONTROL_ENABLED=0): every row resolves to "on" so the
// matrix renders the real feature tree on the current backend and auto-upgrades
// to the server's resolved map the moment it lands. Admin-only nav is excluded
// (role-gated, never entitlement-gated — §0 note).
export const FEATURE_REGISTRY: FeatureRegistryNode[] = [
    // KEY ALIGNMENT (2026-06-11 fix): module keys MUST carry the backend `mod.`
    // prefix and billing the `money.billing_overview` key — the live backend
    // /me/entitlements `modes` map (var/control/registry.json) keys every module
    // as `mod.*`. The premium-UI nav previously authored bare `grow`/`sell`/...
    // which are ABSENT from the backend map -> resolved permissive "on" -> a
    // module HIDE never dropped the group header in the sidebar. Page child keys
    // (grow.campaigns, sell.leads, ...) already matched and are unchanged. This
    // registry feeds RouteEntitlementGate's pathname->key map + the CONTROL_ENABLED=0
    // fallback matrix; with control LIVE the matrix uses the backend's own keys.
    { key: "mod.command", kind: "module", parent_key: null, label: "Command", is_core: true, sort_order: 0 },
    { key: "command.dashboard", kind: "page", parent_key: "mod.command", label: "Dashboard", nav_href: "/", is_core: true, sort_order: 1 },

    { key: "mod.ai_manager", kind: "module", parent_key: null, label: "AI Manager", sort_order: 10 },
    { key: "ai_manager.overview", kind: "page", parent_key: "mod.ai_manager", label: "Overview", nav_href: "/ai-manager/overview", sort_order: 11 },
    { key: "ai_manager.test", kind: "page", parent_key: "mod.ai_manager", label: "Test Console", nav_href: "/ai-manager/test", sort_order: 12 },
    { key: "ai_manager.commands", kind: "page", parent_key: "mod.ai_manager", label: "Command History", nav_href: "/ai-manager/commands", sort_order: 13 },
    { key: "ai_manager.approvals", kind: "page", parent_key: "mod.ai_manager", label: "Pending Approvals", nav_href: "/ai-manager/approvals", sort_order: 14 },
    { key: "ai_manager.capabilities", kind: "page", parent_key: "mod.ai_manager", label: "Capabilities", nav_href: "/ai-manager/capabilities", sort_order: 15 },
    { key: "ai_manager.setup", kind: "page", parent_key: "mod.ai_manager", label: "Setup", nav_href: "/ai-manager/setup", sort_order: 16 },
    { key: "ai_manager.users", kind: "page", parent_key: "mod.ai_manager", label: "Authorized Users", nav_href: "/ai-manager/users", sort_order: 17 },

    { key: "mod.grow", kind: "module", parent_key: null, label: "Grow", sort_order: 20 },
    { key: "grow.campaigns", kind: "page", parent_key: "mod.grow", label: "Campaigns", nav_href: "/campaigns", sort_order: 21 },
    { key: "grow.campaigns.create", kind: "action", parent_key: "grow.campaigns", label: "Create campaign", sort_order: 22 },
    { key: "grow.ads", kind: "page", parent_key: "mod.grow", label: "Ad Automation", nav_href: "/ads", sort_order: 23 },
    { key: "grow.funnels", kind: "page", parent_key: "mod.grow", label: "Funnels", nav_href: "/funnels", sort_order: 24 },
    { key: "grow.forms", kind: "page", parent_key: "mod.grow", label: "Form Builder", nav_href: "/forms", sort_order: 25 },

    { key: "mod.sell", kind: "module", parent_key: null, label: "Sell", sort_order: 30 },
    { key: "sell.leads", kind: "page", parent_key: "mod.sell", label: "Leads", nav_href: "/leads", sort_order: 31 },
    { key: "sell.leads.export", kind: "action", parent_key: "sell.leads", label: "Export leads", sort_order: 32 },
    { key: "sell.crm", kind: "page", parent_key: "mod.sell", label: "CRM", nav_href: "/crm", sort_order: 33 },

    { key: "mod.engage", kind: "module", parent_key: null, label: "Engage", sort_order: 40 },
    { key: "engage.run", kind: "page", parent_key: "mod.engage", label: "Run a Campaign", nav_href: "/run", sort_order: 41 },
    { key: "engage.calls", kind: "page", parent_key: "mod.engage", label: "Call Logs", nav_href: "/calls", sort_order: 42 },
    { key: "engage.callbacks", kind: "page", parent_key: "mod.engage", label: "Callbacks", nav_href: "/callbacks", sort_order: 43 },
    { key: "engage.whatsapp", kind: "page", parent_key: "mod.engage", label: "WhatsApp", nav_href: "/whatsapp", sort_order: 44 },
    { key: "engage.support", kind: "page", parent_key: "mod.engage", label: "Customer Support", nav_href: "/support", sort_order: 45 },
    { key: "engage.booking", kind: "page", parent_key: "mod.engage", label: "Booking", nav_href: "/booking", sort_order: 46 },

    { key: "mod.automate", kind: "module", parent_key: null, label: "Automate", sort_order: 50 },
    { key: "automate.workflows", kind: "page", parent_key: "mod.automate", label: "Workflows", nav_href: "/workflows", sort_order: 51 },
    { key: "automate.webhooks", kind: "page", parent_key: "mod.automate", label: "Webhooks", nav_href: "/webhooks", sort_order: 52 },

    { key: "mod.money", kind: "module", parent_key: null, label: "Money", sort_order: 60 },
    { key: "money.payments", kind: "page", parent_key: "mod.money", label: "Payments", nav_href: "/payments", sort_order: 61 },
    { key: "money.billing_overview", kind: "page", parent_key: "mod.money", label: "Billing", nav_href: "/billing/overview", is_core: true, sort_order: 62 },

    { key: "mod.intelligence", kind: "module", parent_key: null, label: "Intelligence", sort_order: 70 },
    { key: "intelligence.analytics", kind: "page", parent_key: "mod.intelligence", label: "Analytics", nav_href: "/analytics", sort_order: 71 },

    { key: "mod.foundation", kind: "module", parent_key: null, label: "Foundation", is_core: true, sort_order: 80 },
    { key: "foundation.suppression", kind: "page", parent_key: "mod.foundation", label: "Do-Not-Call", nav_href: "/suppression", sort_order: 81 },
    { key: "core.settings", kind: "page", parent_key: "mod.foundation", label: "Settings", nav_href: "/settings", is_core: true, sort_order: 82 },
];

// Compose the fallback resolved matrix: every catalog node resolves to "on" with
// provenance "global" (the resting/default-plan state — byte-identical to today).
function fallbackEntitlements(): ResolvedEntitlement[] {
    return FEATURE_REGISTRY.map((n) => ({
        ...n,
        mode: "on" as FeatureMode,
        provenance: "global" as EntitlementProvenance,
        override: null,
        default_mode: "on" as FeatureMode,
        plan_mode: null,
    }));
}

// GET /admin/vendors/{id} — the full workspace payload. GRACEFUL: if the backend
// hasn't shipped the route (404 while CONTROL_ENABLED=0), compose an equivalent
// shape from /tenants + /usage/all + the static registry so the workspace renders
// real identity + usage and the full (all-"on") matrix on the current backend,
// and auto-upgrades to the server's resolved map the moment it lands.
export async function getAdminVendor(id: string): Promise<AdminVendorDetail> {
    const res = await fetch(`${BASE}/admin/vendors/${encodeURIComponent(id)}`, { headers: authHeaders() });
    await handle401(res);
    if (res.ok) {
        const data = (await res.json()) as Partial<AdminVendorDetail>;
        return {
            tenant_id: data.tenant_id || id,
            name: data.name || id,
            email: data.email || "",
            phone: data.phone,
            role: data.role,
            plan: data.plan,
            status: coerceVendorStatus(data.status),
            created_at: data.created_at,
            ent_version: data.ent_version,
            entitlements: data.entitlements && data.entitlements.length ? data.entitlements : fallbackEntitlements(),
            usage: data.usage,
            limits: data.limits,
            health: data.health,
            wallet: data.wallet,
        };
    }
    if (res.status !== 404) throw new Error("Failed to load vendor");

    // ---- Fallback: compose from /tenants + /usage/all (both admin-gated) ----
    const [tenants, usage] = await Promise.all([
        getTenants().catch(() => ({ tenants: [] as Tenant[] })),
        getUsageAll().catch(() => ({ tenants: [] as TenantUsageRow[] })),
    ]);
    const t = tenants.tenants.find((x) => x.tenant_id === id);
    const u = usage.tenants.find((x) => x.tenant_id === id);
    return {
        tenant_id: id,
        name: t?.name || u?.name || id,
        email: t?.email || "",
        role: t?.role,
        plan: undefined,
        status: coerceVendorStatus(undefined),
        created_at: t?.created_at,
        entitlements: fallbackEntitlements(),
        usage: {
            calls_today: u?.today.calls ?? 0,
            calls_30d: u?.month.calls ?? 0,
            minutes_30d: u?.month.minutes ?? 0,
            active_now: u?.active_now ?? 0,
        },
        limits: u?.limits,
        health: {},
        wallet: {},
    };
}

// PUT /admin/vendors/{id}/entitlements/{feature_key} — set a per-vendor override
// (on|locked|hidden). Bumps the tenant's ent_version server-side (real-time
// invalidation). Audited (set_override). Optimistic-friendly: the caller flips
// the row first and reconciles on resolve/failure.
export async function setVendorEntitlement(
    id: string,
    featureKey: string,
    mode: FeatureMode,
    reason?: string
): Promise<{ ok: boolean; version?: number }> {
    const fd = new FormData();
    fd.append("mode", mode);
    if (reason) fd.append("reason", reason);
    const res = await fetch(
        `${BASE}/admin/vendors/${encodeURIComponent(id)}/entitlements/${encodeURIComponent(featureKey)}`,
        { method: "PUT", headers: authHeaders(), body: fd }
    );
    await handle401(res);
    if (!res.ok) return throwForStatus(res, "Failed to update permission");
    return res.json().catch(() => ({ ok: true }));
}

// DELETE the per-vendor override → revert to plan/global. Audited (set_override).
export async function clearVendorEntitlement(
    id: string,
    featureKey: string
): Promise<{ ok: boolean; version?: number }> {
    const res = await fetch(
        `${BASE}/admin/vendors/${encodeURIComponent(id)}/entitlements/${encodeURIComponent(featureKey)}`,
        { method: "DELETE", headers: authHeaders() }
    );
    await handle401(res);
    if (!res.ok) return throwForStatus(res, "Failed to reset permission");
    return res.json().catch(() => ({ ok: true }));
}

// PUT /admin/vendors/{id}/plan — assign a plan (writes plan limits → caps).
// Bumps ent_version. Audited (set_plan).
export async function setVendorPlan(id: string, planId: string): Promise<{ ok: boolean }> {
    const fd = new FormData();
    fd.append("plan_id", planId);
    const res = await fetch(`${BASE}/admin/vendors/${encodeURIComponent(id)}/plan`, {
        method: "PUT",
        headers: authHeaders(),
        body: fd,
    });
    await handle401(res);
    if (!res.ok) return throwForStatus(res, "Failed to assign plan");
    return res.json().catch(() => ({ ok: true }));
}

// PUT /admin/vendors/{id}/status — active/trial/suspended/disabled/expired.
// `disabled` needs a firewall step-up server-side; the reason is REQUIRED for
// suspend/disable (captured in the confirm Modal). Bumps ent_version. Audited
// (set_status). Suspension = instant token revoke + data preserved (spec §8.2).
export async function setVendorStatus(
    id: string,
    status: VendorAccountStatus,
    reason?: string
): Promise<{ ok: boolean }> {
    const fd = new FormData();
    fd.append("status", status);
    if (reason) fd.append("reason", reason);
    const res = await fetch(`${BASE}/admin/vendors/${encodeURIComponent(id)}/status`, {
        method: "PUT",
        headers: authHeaders(),
        body: fd,
    });
    await handle401(res);
    if (!res.ok) return throwForStatus(res, "Failed to update status");
    return res.json().catch(() => ({ ok: true }));
}

// ---- Stats ----
export async function getStats(): Promise<Stats> {
    const res = await fetch(`${BASE}/stats`, {
        headers: authHeaders(),
    });
    await handle401(res);
    if (!res.ok) throw new Error("Failed to fetch stats");
    return res.json();
}

// ---- P0.2 Suppression / DND ----
export type SuppressionEntry = {
    phone: string;
    reason: string;
    source: string;
    added_at: string;
};

export async function getSuppression(): Promise<{ numbers: SuppressionEntry[]; total: number }> {
    const res = await fetch(`${BASE}/suppression`, { headers: authHeaders() });
    await handle401(res);
    if (!res.ok) throw new Error("Failed to fetch suppression list");
    return res.json();
}

export async function addSuppression(text: string, file?: File | null): Promise<{ added: number; total: number }> {
    const fd = new FormData();
    fd.append("numbers", text);
    if (file) fd.append("csv", file);
    const res = await fetch(`${BASE}/suppression`, {
        method: "POST",
        headers: authHeaders(),
        body: fd,
    });
    await handle401(res);
    if (!res.ok) throw new Error("Failed to add suppression entries");
    return res.json();
}

export async function deleteSuppression(phone: string): Promise<{ deleted: boolean }> {
    const res = await fetch(`${BASE}/suppression/${encodeURIComponent(phone)}`, {
        method: "DELETE",
        headers: authHeaders(),
    });
    await handle401(res);
    if (!res.ok) throw new Error("Failed to delete suppression entry");
    return res.json();
}

export async function optOut(phone: string, source: string = "manual", campaign_id?: string): Promise<{ ok: boolean }> {
    const fd = new FormData();
    fd.append("phone", phone);
    fd.append("source", source);
    if (campaign_id) fd.append("campaign_id", campaign_id);
    const res = await fetch(`${BASE}/optout`, {
        method: "POST",
        headers: authHeaders(),
        body: fd,
    });
    await handle401(res);
    if (!res.ok) throw new Error("Failed to opt-out");
    return res.json();
}

// ---- P0.5 Callbacks ----
export type CallbackEntry = {
    id: string;
    name: string;
    phone: string;
    campaign_id: string;
    next_attempt_at: string;
    reason: string;
    attempts: number;
    max_attempts: number;
    created_at: string;
};

export async function getCallbacks(all?: boolean): Promise<{ items: CallbackEntry[] }> {
    const qs = all ? "?all=1" : "";
    const res = await fetch(`${BASE}/callbacks${qs}`, { headers: authHeaders() });
    await handle401(res);
    if (!res.ok) throw new Error("Failed to fetch callbacks");
    return res.json();
}

export async function cancelCallback(id: string): Promise<{ cancelled: string }> {
    const res = await fetch(`${BASE}/callbacks/${encodeURIComponent(id)}`, {
        method: "DELETE",
        headers: authHeaders(),
    });
    await handle401(res);
    if (!res.ok) throw new Error("Failed to cancel callback");
    return res.json();
}

export async function addCallback(phone: string, campaign_id: string, when: string): Promise<{ ok: boolean }> {
    const fd = new FormData();
    fd.append("phone", phone);
    fd.append("campaign_id", campaign_id);
    fd.append("when", when);
    const res = await fetch(`${BASE}/callbacks`, {
        method: "POST",
        headers: authHeaders(),
        body: fd,
    });
    await handle401(res);
    if (!res.ok) throw new Error("Failed to add callback");
    return res.json();
}

// ---- P0.7 Usage ----
export type UsageData = {
    today: { calls: number; minutes: number };
    month: { calls: number; minutes: number };
    limits: {
        max_concurrency: number;
        daily_call_cap: number;
        monthly_minutes_cap: number;
    };
    active_now: number;
};

export async function getUsage(): Promise<UsageData> {
    const res = await fetch(`${BASE}/usage`, { headers: authHeaders() });
    await handle401(res);
    if (!res.ok) throw new Error("Failed to fetch usage");
    return res.json();
}

export type TenantUsageRow = {
    tenant_id: string;
    name: string;
    today: { calls: number; minutes: number };
    month: { calls: number; minutes: number };
    limits: { max_concurrency: number; daily_call_cap: number; monthly_minutes_cap: number };
    active_now: number;
};

export async function getUsageAll(): Promise<{ tenants: TenantUsageRow[] }> {
    const res = await fetch(`${BASE}/usage/all`, { headers: authHeaders() });
    await handle401(res);
    if (!res.ok) throw new Error("Failed to fetch usage/all");
    return res.json();
}

export async function setTenantLimits(id: string, limits: { max_concurrency?: number; daily_call_cap?: number; monthly_minutes_cap?: number }): Promise<{ ok: boolean }> {
    const fd = new FormData();
    if (limits.max_concurrency != null) fd.append("max_concurrency", String(limits.max_concurrency));
    if (limits.daily_call_cap != null) fd.append("daily_call_cap", String(limits.daily_call_cap));
    if (limits.monthly_minutes_cap != null) fd.append("monthly_minutes_cap", String(limits.monthly_minutes_cap));
    const res = await fetch(`${BASE}/tenants/${encodeURIComponent(id)}/limits`, {
        method: "POST",
        headers: authHeaders(),
        body: fd,
    });
    await handle401(res);
    if (!res.ok) throw new Error("Failed to set tenant limits");
    return res.json();
}

// ---- P1.B Analytics ----
export type AnalyticsFunnel = {
    dialed: number;
    connected: number;
    answered: number;
    interested: number;
    callback: number;
    qualified: number;
    opted_out: number;
    voicemail: number;
    no_answer: number;
    funnel: { stage: string; count: number }[];
};

export async function getAnalytics(opts?: { campaign_id?: string; from?: string; to?: string }): Promise<AnalyticsFunnel> {
    const params = new URLSearchParams();
    if (opts?.campaign_id) params.set("campaign_id", opts.campaign_id);
    if (opts?.from) params.set("from", opts.from);
    if (opts?.to) params.set("to", opts.to);
    const qs = params.toString();
    const res = await fetch(`${BASE}/analytics${qs ? `?${qs}` : ""}`, { headers: authHeaders() });
    await handle401(res);
    if (!res.ok) throw new Error("Failed to fetch analytics");
    return res.json();
}

// ============================================================
// WAVE 3 — Webhooks / A-B / Billing / WhatsApp
// ============================================================

// Helper: throw a friendly message on 403 (read-only role) for mutating calls.
async function throwForStatus(res: Response, fallback: string): Promise<never> {
    let body: Record<string, unknown> = {};
    try { body = await res.json(); } catch { /* non-JSON */ }
    const err = typeof body.error === "string" ? body.error : "";
    if (res.status === 403) throw new Error(err || "You don't have permission to do that.");
    throw new Error(err || fallback);
}

// ---- CRM Webhooks (Unit 2) ----
// Selectable events the backend emits.
export const WEBHOOK_EVENTS = [
    "call.completed",
    "lead.qualified",
    "callback.scheduled",
    "lead.opted_out",
] as const;
export type WebhookEvent = (typeof WEBHOOK_EVENTS)[number];

export type Webhook = {
    id: string;
    tenant_id: string;
    url: string;
    secret: string;
    events: string[];
    active: boolean;
    created_at: string;
};

export async function getWebhooks(): Promise<{ webhooks: Webhook[] }> {
    const res = await fetch(`${BASE}/webhooks`, { headers: authHeaders() });
    await handle401(res);
    if (!res.ok) throw new Error("Failed to fetch webhooks");
    return res.json();
}

export async function createWebhook(data: { url: string; secret?: string; events: string[] }): Promise<{ id: string; url: string; secret: string }> {
    const fd = new FormData();
    fd.append("url", data.url);
    if (data.secret) fd.append("secret", data.secret);
    // backend accepts space/comma-separated list
    fd.append("events", data.events.join(" "));
    const res = await fetch(`${BASE}/webhooks`, { method: "POST", headers: authHeaders(), body: fd });
    await handle401(res);
    if (!res.ok) return throwForStatus(res, "Failed to create webhook");
    return res.json();
}

export async function deleteWebhook(id: string): Promise<{ deleted: boolean }> {
    const res = await fetch(`${BASE}/webhooks/${encodeURIComponent(id)}`, { method: "DELETE", headers: authHeaders() });
    await handle401(res);
    if (!res.ok) return throwForStatus(res, "Failed to delete webhook");
    return res.json();
}

// ---- A/B Testing (Unit 3) ----
export type CampaignVariant = {
    id?: string;
    label: string;
    weight: number;
    fields_override: {
        opener?: string;
        agent_name?: string;
        voice_id?: string;
        [k: string]: unknown;
    };
};

export type ABVariantResult = {
    id: string;
    label: string;
    weight: number;
    dialed: number;
    connected: number;
    interested: number;
    qualified: number;
    avg_interest: number;
};

export type ABResults = {
    campaign_id: string;
    variants: ABVariantResult[];
};

export async function getCampaignAB(id: string): Promise<ABResults> {
    const res = await fetch(`${BASE}/campaigns/${encodeURIComponent(id)}/ab`, { headers: authHeaders() });
    await handle401(res);
    if (!res.ok) throw new Error("Failed to fetch A/B results");
    return res.json();
}

// ---- Script Studio (W1 vendor-script adopt-persona) ----
// A vendor pastes a free-form SCRIPT (greeting / tone / behaviour) into a campaign's
// `raw_script`; the inbound agent ADOPTS it losslessly. These two read-only endpoints
// let the founder PREVIEW the rendered brain and DRY-RUN one turn (free Groq, no DID,
// no real call). The backend forces the per-campaign persona ON for preview on a COPY
// of fields — it never mutates the stored campaign and never touches the global flag.

// GET /campaigns/{cid}/prompt-preview — the exact rendered system prompt the inbound
// agent would adopt, with the vendor persona forced on for preview.
export type PromptPreview = {
    campaign_id: string;
    name: string;
    vendor_script_present: boolean;
    vendor_script_active_in_preview: boolean;
    system_prompt: string;
    chars: number;
};

export async function getPromptPreview(cid: string): Promise<PromptPreview> {
    const res = await fetch(
        `${BASE}/campaigns/${encodeURIComponent(cid)}/prompt-preview`,
        { headers: authHeaders() }
    );
    await handle401(res);
    if (!res.ok) throw new Error("Failed to render prompt preview");
    return res.json();
}

// POST /campaigns/{cid}/dry-run — run ONE sample caller line through the inbound brain
// (free/cheap Groq turn) so the founder can SEE the adopted greeting/response. No DID,
// no real call, no charge.
export type DryRunResult = {
    campaign_id: string;
    name: string;
    vendor_script_present: boolean;
    vendor_script_active_in_preview: boolean;
    sample_user: string;
    agent_reply: string;
    used_llm: boolean;
    provider: string;
    model: string;
    note: string;
};

export async function dryRunCampaign(
    cid: string,
    message: string,
    asReturning = false
): Promise<DryRunResult> {
    const fd = new FormData();
    fd.append("message", message);
    fd.append("as_returning", asReturning ? "1" : "");
    const res = await fetch(
        `${BASE}/campaigns/${encodeURIComponent(cid)}/dry-run`,
        { method: "POST", headers: authHeaders(), body: fd }
    );
    await handle401(res);
    if (!res.ok) throw new Error("Dry-run failed");
    return res.json();
}

// Optional parsed persona hints the backend sanitizes from a script (never lossy over
// raw_script — a convenience projection only). Shown read-only in the Studio.
export type ScriptMeta = {
    tone?: string;
    greeting?: string;
    persona?: string;
    language?: string;
    style?: string;
    do?: string[];
    dont?: string[];
    do_list?: string[];
    dont_list?: string[];
    [k: string]: unknown;
};

// ---- Billing / Metering (Unit 4) ----
export type Billing = {
    tenant_id: string;
    plan: "prepaid" | "postpaid";
    currency: string;
    rate_per_min: number;
    rate_per_call: number;
    balance: number;
    included_minutes: number;
    month_to_date: { calls: number; minutes: number; cost: number };
};

export type LedgerEntry = {
    id: string;
    call_id: string;
    phone: string;
    campaign_id: string;
    duration_s: number;
    cost: number;
    currency: string;
    outcome: string;
    at: string;
};

export async function getBilling(): Promise<Billing> {
    const res = await fetch(`${BASE}/billing`, { headers: authHeaders() });
    await handle401(res);
    if (!res.ok) throw new Error("Failed to fetch billing");
    return res.json();
}

export async function getBillingLedger(limit = 100): Promise<{ ledger: LedgerEntry[]; total: number }> {
    const res = await fetch(`${BASE}/billing/ledger?limit=${limit}`, { headers: authHeaders() });
    await handle401(res);
    if (!res.ok) throw new Error("Failed to fetch billing ledger");
    return res.json();
}

export type BillingUpdate = {
    plan?: "prepaid" | "postpaid";
    rate_per_min?: number;
    rate_per_call?: number;
    currency?: string;
    balance?: number;        // absolute set
    included_minutes?: number;
    topup?: number;          // adds to balance
};

export async function setBilling(tenantId: string, data: BillingUpdate): Promise<Billing> {
    const fd = new FormData();
    if (data.plan != null) fd.append("plan", data.plan);
    if (data.rate_per_min != null) fd.append("rate_per_min", String(data.rate_per_min));
    if (data.rate_per_call != null) fd.append("rate_per_call", String(data.rate_per_call));
    if (data.currency != null) fd.append("currency", data.currency);
    if (data.balance != null) fd.append("balance", String(data.balance));
    if (data.included_minutes != null) fd.append("included_minutes", String(data.included_minutes));
    if (data.topup != null) fd.append("topup", String(data.topup));
    const res = await fetch(`${BASE}/billing/${encodeURIComponent(tenantId)}`, { method: "POST", headers: authHeaders(), body: fd });
    await handle401(res);
    if (!res.ok) return throwForStatus(res, "Failed to update billing");
    return res.json();
}

// ============================================================
// WAVE A — Real vendor-cost billing meter (multi-page Billing UI)
// Field names match the backend contract EXACTLY (see build_log/wave-A-billing-backend.md).
// ============================================================

export type VendorStatus = "configured" | "not_configured" | "error";

export type BillingPerVendor = {
    vendor: string;
    display_name: string;
    cost: number;
    status: VendorStatus;
};

export type BillingOverview = {
    currency: string;
    grand_total: number;
    month_to_date: number;
    per_vendor: BillingPerVendor[];
    updated_at: string;
};

export async function getBillingOverview(): Promise<BillingOverview> {
    const res = await fetch(`${BASE}/billing/overview`, { headers: authHeaders() });
    await handle401(res);
    if (!res.ok) throw new Error("Failed to fetch billing overview");
    return res.json();
}

export type BillingVendorRow = {
    vendor: string;
    display_name: string;
    status: VendorStatus;
    cost: number;
    synced_at: string;
    stale: boolean;
    estimated: boolean;
};

export async function getBillingVendors(): Promise<{ vendors: BillingVendorRow[]; currency: string }> {
    const res = await fetch(`${BASE}/billing/vendors`, { headers: authHeaders() });
    await handle401(res);
    if (!res.ok) throw new Error("Failed to fetch billing vendors");
    return res.json();
}

export type BillingVendorDetail = {
    vendor: string;
    display_name: string;
    status: VendorStatus;
    total_cost: number;
    currency: string;
    timeseries: { date: string; cost: number }[];
    rows: number;
    synced_at: string;
    stale: boolean;
};

export async function getBillingVendor(id: string): Promise<BillingVendorDetail> {
    const res = await fetch(`${BASE}/billing/vendor/${encodeURIComponent(id)}`, { headers: authHeaders() });
    await handle401(res);
    if (!res.ok) throw new Error("Failed to fetch vendor detail");
    return res.json();
}

export type BillingExplorerRow = {
    call_id: string;
    room: string;
    tenant_id: string;
    campaign_id: string;
    ts: string;
    total_cost: number;
    by_vendor: Record<string, number>;
    name: string;
    phone: string;
    campaign_name: string;
    outcome: string;
    duration_s: number;
};

export type BillingExplorer = {
    rows: BillingExplorerRow[];
    total: number;
    currency: string;
    filters: Record<string, unknown>;
};

export async function getBillingExplorer(opts?: { from?: string; to?: string; campaign_id?: string }): Promise<BillingExplorer> {
    const params = new URLSearchParams();
    if (opts?.from) params.set("from", opts.from);
    if (opts?.to) params.set("to", opts.to);
    if (opts?.campaign_id) params.set("campaign_id", opts.campaign_id);
    const qs = params.toString();
    const res = await fetch(`${BASE}/billing/explorer${qs ? `?${qs}` : ""}`, { headers: authHeaders() });
    await handle401(res);
    if (!res.ok) throw new Error("Failed to fetch cost explorer");
    return res.json();
}

export type BillingAuditVendor = {
    vendor: string;
    display_name: string;
    status: VendorStatus;
    synced_at: string;
    stale: boolean;
    error: string;
    internal_ledger_cost: number;
    vendor_reported: number | null;
};

export type BillingAudit = {
    vendors: BillingAuditVendor[];
    currency: string;
    note: string;
};

export async function getBillingAudit(): Promise<BillingAudit> {
    const res = await fetch(`${BASE}/billing/audit`, { headers: authHeaders() });
    await handle401(res);
    if (!res.ok) throw new Error("Failed to fetch billing audit");
    return res.json();
}

export type BillingSyncResult = {
    ok: boolean;
    synced_at: string;
    vendors: Record<string, { status: VendorStatus; synced_at: string; stale: boolean }>;
};

export async function postBillingSync(): Promise<BillingSyncResult> {
    const res = await fetch(`${BASE}/billing/sync`, { method: "POST", headers: authHeaders() });
    await handle401(res);
    if (!res.ok) return throwForStatus(res, "Failed to sync vendors");
    return res.json();
}

// ---- WhatsApp (Unit 5) ----
// Meta's REAL Graph error, surfaced verbatim by the backend (branch
// fix/wafx-whatsapp-meta-error-surfacing). Any/all fields may be present.
// We thread the raw shape through so the UI can map it to plain English AND
// show Meta's own message + code for debugging — never a fabricated reason.
export type MetaError = {
    code?: number;            // Meta Graph error code, e.g. 141006 / 131058
    error_subcode?: number;   // e.g. 2388043
    error_user_title?: string;
    error_user_msg?: string;  // Meta's own human-readable line
    message?: string;         // raw Graph "message"
    fbtrace_id?: string;
};

export type WhatsAppSendResult = {
    ok: boolean;
    status: string;       // "sent" | "skipped_no_config" | "meta_error:<code>" | ...
    to: string;
    configured: boolean;
    // present on failure (the backend now surfaces Meta's real error)
    error?: string;             // machine code, e.g. "template_not_registered" / "meta_error:141006"
    meta_error?: MetaError;     // Meta's structured Graph error
    approved_templates?: string[]; // returned with template_not_registered
};

export async function sendWhatsApp(data: { to: string; template?: string; text?: string; params?: string }): Promise<WhatsAppSendResult> {
    const fd = new FormData();
    fd.append("to", data.to);
    if (data.template) fd.append("template", data.template);
    if (data.text) fd.append("text", data.text);
    if (data.params) fd.append("params", data.params);
    const res = await fetch(`${BASE}/whatsapp/send`, { method: "POST", headers: authHeaders(), body: fd });
    await handle401(res);
    // A non-200 still carries Meta's real error JSON — return it instead of
    // throwing a generic "try again", so the UI can explain WHAT Meta said.
    if (!res.ok) {
        const body = (await res.json().catch(() => null)) as Partial<WhatsAppSendResult> | null;
        if (body && typeof body === "object") {
            return {
                ok: false,
                status: body.status ?? `http_${res.status}`,
                to: body.to ?? data.to,
                configured: body.configured ?? true,
                error: body.error,
                meta_error: body.meta_error,
                approved_templates: body.approved_templates,
            };
        }
        return throwForStatus(res, "Failed to send WhatsApp message");
    }
    return res.json();
}

export type WhatsAppLogEntry = {
    tenant_id: string;
    phone: string;
    template: string;
    kind: "manual" | "auto_followup";
    status: string;
    ok: boolean;
    at: string;
    // present on failed rows when the backend recorded Meta's reason
    error?: string;
    meta_error?: MetaError;
    // W16 delivery funnel (additive, back-compat) — populated once the
    // voice_ops/whatsapp delivery tracker + Meta status webhook are wired. Legacy
    // rows omit these; the delivery view falls back to `ok`/`status`.
    delivery_status?: "queued" | "sent" | "delivered" | "read" | "failed" | "opted_out" | "skipped_no_config";
    delivered_at?: string;
    read_at?: string;
    failed_at?: string;
    opted_out?: boolean;
    campaign_id?: string;
};

export async function getWhatsAppLog(): Promise<{ log: WhatsAppLogEntry[] }> {
    const res = await fetch(`${BASE}/whatsapp/log`, { headers: authHeaders() });
    await handle401(res);
    if (!res.ok) throw new Error("Failed to fetch WhatsApp log");
    return res.json();
}

// ============================================================
// HANDOFF TEAM — the per-tenant human-escalation roster the AI warm-transfers a
// live caller to (and WhatsApps a hot lead to when nobody answers). The backend
// is LIVE on caller.py, tenant-from-TOKEN, write-role gated, reached via the same
// /api proxy + X-Auth pattern as everything above. Contract:
//   GET    /brain/handoff            -> ordered [{ phone, whatsapp?, role?, hours?, priority, enabled }]
//   POST   /brain/handoff/add        -> add/UPDATE one (idempotent by phone; +91… or 400; auto-priority = max+1)
//   DELETE /brain/handoff/remove?phone=<E164> -> remove one (idempotent)
//   PUT    /brain/handoff { handoff:[…ordered…] } -> replace the whole list (REORDER / enable-toggle / bulk save)
// DORMANT-SAFE: a 404 (route not mounted / older box) or a network error resolves
// to an EMPTY list so the panel shows a calm "no team yet" state, never an error
// wall. Mutations surface the backend's {error} body as a readable message
// (e.g. invalid-phone 400 -> "That number must be an Indian +91 mobile number.").
// ============================================================

// One escalation contact. `priority` is the ring order (1 = first). `enabled`
// gates whether the AI dials it. `hours` is a free-form availability window
// ("24x7" / "09:00-20:00" — the backend parses it). All but phone are optional.
export type HandoffMember = {
    name?: string; // the person's display name — spoken to the caller on handoff
    phone: string;
    whatsapp?: string;
    role?: string;
    hours?: string;
    priority: number;
    enabled: boolean;
};

// Typed error for handoff mutations — carries the backend machine code so the
// form can map it to plain English (the most common is "invalid-phone" 400).
export class HandoffError extends Error {
    status: number;
    code: string;
    constructor(status: number, code: string, message: string) {
        super(message);
        this.name = "HandoffError";
        this.status = status;
        this.code = code;
    }
}

// Map a backend {error} body (or HTTP status) to a readable, founder-friendly line.
function explainHandoffError(status: number, code: string): string {
    const c = (code || "").toLowerCase();
    if (status === 400 && /phone|e164|invalid|\+91/.test(c))
        return "That number must be a valid Indian mobile number starting with +91.";
    if (status === 403)
        return "You don't have permission to change the handoff team.";
    if (status === 404)
        return "Handoff team isn't available on this account yet.";
    if (c) return c.replace(/_/g, " ");
    if (status >= 500) return "Something went wrong saving the handoff team — try again.";
    return "Couldn't save the handoff team — please try again.";
}

async function throwHandoff(res: Response): Promise<never> {
    let body: Record<string, unknown> = {};
    try {
        body = await res.json();
    } catch {
        /* non-JSON */
    }
    const code = typeof body.error === "string" ? body.error : typeof body.detail === "string" ? body.detail : "";
    throw new HandoffError(res.status, code, explainHandoffError(res.status, code));
}

// Normalize a raw backend row into a well-typed HandoffMember (tolerant of
// missing/odd fields so a partial payload never crashes the list).
function toHandoffMember(r: Record<string, unknown>, idx: number): HandoffMember {
    const prio = Number(r.priority);
    return {
        name: r.name ? String(r.name).trim() : undefined,
        phone: String(r.phone ?? "").trim(),
        whatsapp: r.whatsapp ? String(r.whatsapp).trim() : undefined,
        role: r.role ? String(r.role).trim() : undefined,
        hours: r.hours ? String(r.hours).trim() : undefined,
        // auto-fill priority from position when the backend omits/garbles it
        priority: Number.isFinite(prio) && prio > 0 ? prio : idx + 1,
        // default-true so already-seeded entries stay dialable (matches backend)
        enabled: r.enabled === undefined ? true : !!r.enabled,
    };
}

// GET the ordered roster. Never throws — dormant/empty -> []. Sorted by priority
// so callers can render the ring order directly.
export async function getHandoffTeam(): Promise<{ team: HandoffMember[] }> {
    let res: Response;
    try {
        res = await fetch(`${BASE}/brain/handoff`, { headers: authHeaders() });
    } catch {
        return { team: [] }; // not deployed / offline -> calm empty state
    }
    await handle401(res);
    if (res.status === 404) return { team: [] };
    if (!res.ok) return { team: [] }; // quiet inline note path; never an error wall
    const data = await res.json().catch(() => ({}));
    // backend may return a bare array OR { handoff:[...] } / { team:[...] }
    const raw: unknown = Array.isArray(data)
        ? data
        : Array.isArray((data as { handoff?: unknown }).handoff)
        ? (data as { handoff: unknown[] }).handoff
        : Array.isArray((data as { team?: unknown }).team)
        ? (data as { team: unknown[] }).team
        : [];
    const team = (raw as Record<string, unknown>[])
        .map(toHandoffMember)
        .sort((a, b) => a.priority - b.priority);
    return { team };
}

// Add OR update one member (idempotent by phone). Omit priority to auto-append
// (backend sets max+1). Throws a readable HandoffError on 400/403/etc.
export async function addHandoffMember(member: {
    name?: string;
    phone: string;
    whatsapp?: string;
    role?: string;
    hours?: string;
    priority?: number;
    enabled?: boolean;
}): Promise<{ ok: boolean }> {
    const fd = new FormData();
    if (member.name) fd.append("name", member.name);
    fd.append("phone", member.phone);
    if (member.whatsapp) fd.append("whatsapp", member.whatsapp);
    if (member.role) fd.append("role", member.role);
    if (member.hours) fd.append("hours", member.hours);
    if (member.priority != null) fd.append("priority", String(member.priority));
    if (member.enabled != null) fd.append("enabled", member.enabled ? "1" : "0");
    const res = await fetch(`${BASE}/brain/handoff/add`, {
        method: "POST",
        headers: authHeaders(),
        body: fd,
    });
    await handle401(res);
    if (!res.ok) return throwHandoff(res);
    return res.json().catch(() => ({ ok: true }));
}

// Remove one member by E.164 phone (idempotent — removing an absent number is fine).
export async function removeHandoffMember(phone: string): Promise<{ removed: boolean }> {
    const res = await fetch(`${BASE}/brain/handoff/remove?phone=${encodeURIComponent(phone)}`, {
        method: "DELETE",
        headers: authHeaders(),
    });
    await handle401(res);
    if (!res.ok) return throwHandoff(res);
    return res.json().catch(() => ({ removed: true }));
}

// Replace the WHOLE ordered list — the single call behind REORDER, enable/disable
// toggles and bulk save. Re-numbers priority from the array position (1-based) so
// the sent order is authoritative. Sent as JSON per the PUT contract.
export async function saveHandoffOrder(list: HandoffMember[]): Promise<{ ok: boolean }> {
    const handoff = list.map((m, i) => ({
        name: m.name || undefined,
        phone: m.phone,
        whatsapp: m.whatsapp || undefined,
        role: m.role || undefined,
        hours: m.hours || undefined,
        priority: i + 1,
        enabled: !!m.enabled,
    }));
    const res = await fetch(`${BASE}/brain/handoff`, {
        method: "PUT",
        headers: { ...(authHeaders() as Record<string, string>), "Content-Type": "application/json" },
        body: JSON.stringify({ handoff }),
    });
    await handle401(res);
    if (!res.ok) return throwHandoff(res);
    return res.json().catch(() => ({ ok: true }));
}
