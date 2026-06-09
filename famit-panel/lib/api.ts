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
export async function getLeads(opts?: { hot?: boolean; sort?: string }): Promise<{ leads: Lead[] }> {
    const params = new URLSearchParams();
    if (opts?.hot) params.set("hot", "1");
    if (opts?.sort) params.set("sort", opts.sort);
    const qs = params.toString();
    const res = await fetch(`${BASE}/leads${qs ? `?${qs}` : ""}`, {
        headers: authHeaders(),
    });
    await handle401(res);
    if (!res.ok) throw new Error("Failed to fetch leads");
    return res.json();
}

export async function addLeads(
    text: string,
    file?: File | null
): Promise<{ added: number; total: number }> {
    const fd = new FormData();
    fd.append("leads", text);
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
export async function getCalls(): Promise<{ calls: CallLog[] }> {
    const res = await fetch(`${BASE}/calls?limit=200`, {
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
export type Voice = {
    voice_id: string;
    name: string;
};

export async function getVoices(): Promise<{ voices: Voice[] }> {
    const res = await fetch(`${BASE}/voices`, {
        headers: authHeaders(),
    });
    await handle401(res);
    if (!res.ok) throw new Error("Failed to fetch voices");
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
export type WhatsAppSendResult = {
    ok: boolean;
    status: string;       // "sent" | "skipped_no_config" | ...
    to: string;
    configured: boolean;
};

export async function sendWhatsApp(data: { to: string; template?: string; text?: string; params?: string }): Promise<WhatsAppSendResult> {
    const fd = new FormData();
    fd.append("to", data.to);
    if (data.template) fd.append("template", data.template);
    if (data.text) fd.append("text", data.text);
    if (data.params) fd.append("params", data.params);
    const res = await fetch(`${BASE}/whatsapp/send`, { method: "POST", headers: authHeaders(), body: fd });
    await handle401(res);
    if (!res.ok) return throwForStatus(res, "Failed to send WhatsApp message");
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
};

export async function getWhatsAppLog(): Promise<{ log: WhatsAppLogEntry[] }> {
    const res = await fetch(`${BASE}/whatsapp/log`, { headers: authHeaders() });
    await handle401(res);
    if (!res.ok) throw new Error("Failed to fetch WhatsApp log");
    return res.json();
}
