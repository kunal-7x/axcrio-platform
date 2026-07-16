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
    llm_model?: string;       // per-campaign Groq model (Advanced → LLM model); env default when unset
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
    if (!res.ok) {
        let msg = "Invalid email or password.";
        try {
            const b = await res.json();
            if (b && typeof b.error === "string" && b.error) msg = b.error;
        } catch {
            /* non-JSON */
        }
        throw new Error(msg);
    }
    return res.json();
}

// ---- RBAC (Wave 3) ----
export type Me = {
    tenant_id: string;
    email: string;
    name: string;
    role: Role;
    is_admin: boolean;
    status?: string;
    restricted?: string[];
    demo?: boolean;
    demo_minutes?: number;
    demo_remaining_s?: number;
};

export async function getMe(): Promise<Me> {
    const res = await fetch(`${BASE}/me`, { headers: authHeaders() });
    await handle401(res);
    if (!res.ok) throw new Error("Failed to fetch current user");
    return res.json();
}

// ---- Client management (Super Admin) ----
export type ClientInfo = {
    tenant_id: string;
    email: string;
    name: string;
    role: Role;
    is_admin: boolean;
    status: string; // "active" | "suspended"
    created_at: string;
    restricted: string[];
    demo: boolean;
    demo_minutes?: number;
    demo_started_at?: string;
    demo_remaining_s?: number;
    demo_expired?: boolean;
};

export async function getClients(): Promise<{ clients: ClientInfo[]; total: number }> {
    const res = await fetch(`${BASE}/admin/clients`, { headers: authHeaders() });
    await handle401(res);
    if (!res.ok) return throwForStatus(res, "Failed to load clients");
    return res.json();
}

export async function createClient(body: {
    email: string; password: string; name?: string; role?: Role;
    demo?: boolean; demo_minutes?: number; restricted?: string[];
}): Promise<{ client: ClientInfo }> {
    const fd = new FormData();
    fd.append("email", body.email);
    fd.append("password", body.password);
    if (body.name) fd.append("name", body.name);
    fd.append("role", body.role || "manager");
    fd.append("demo", body.demo ? "1" : "0");
    fd.append("demo_minutes", String(body.demo_minutes ?? 0));
    fd.append("restricted", JSON.stringify(body.restricted || []));
    const res = await fetch(`${BASE}/admin/clients`, { method: "POST", headers: authHeaders(), body: fd });
    await handle401(res);
    if (!res.ok) return throwForStatus(res, "Failed to create client");
    return res.json();
}

export async function updateClient(tid: string, body: Partial<{
    name: string; email: string; role: Role; status: string;
    demo: boolean; demo_minutes: number; demo_reset: boolean; restricted: string[];
}>): Promise<{ client: ClientInfo }> {
    const fd = new FormData();
    if (body.name != null) fd.append("name", body.name);
    if (body.email != null) fd.append("email", body.email);
    if (body.role != null) fd.append("role", body.role);
    if (body.status != null) fd.append("status", body.status);
    if (body.demo != null) fd.append("demo", body.demo ? "1" : "0");
    if (body.demo_minutes != null) fd.append("demo_minutes", String(body.demo_minutes));
    if (body.demo_reset) fd.append("demo_reset", "1");
    if (body.restricted != null) fd.append("restricted", JSON.stringify(body.restricted));
    const res = await fetch(`${BASE}/admin/clients/${encodeURIComponent(tid)}`, { method: "PUT", headers: authHeaders(), body: fd });
    await handle401(res);
    if (!res.ok) return throwForStatus(res, "Failed to update client");
    return res.json();
}

export async function setClientStatus(tid: string, status: "active" | "suspended"): Promise<{ ok: boolean; status: string }> {
    const fd = new FormData();
    fd.append("status", status);
    const res = await fetch(`${BASE}/admin/clients/${encodeURIComponent(tid)}/status`, { method: "POST", headers: authHeaders(), body: fd });
    await handle401(res);
    if (!res.ok) return throwForStatus(res, "Failed to change status");
    return res.json();
}

export async function resetClientPassword(tid: string, password: string): Promise<{ ok: boolean }> {
    const fd = new FormData();
    fd.append("password", password);
    const res = await fetch(`${BASE}/admin/clients/${encodeURIComponent(tid)}/password`, { method: "POST", headers: authHeaders(), body: fd });
    await handle401(res);
    if (!res.ok) return throwForStatus(res, "Failed to reset password");
    return res.json();
}

export async function deleteClient(tid: string): Promise<{ ok: boolean; purged: Record<string, number> }> {
    const res = await fetch(`${BASE}/admin/clients/${encodeURIComponent(tid)}`, { method: "DELETE", headers: authHeaders() });
    await handle401(res);
    if (!res.ok) return throwForStatus(res, "Failed to delete client");
    return res.json();
}

// ---- Public signup (email + 4-digit OTP) ----
export async function signupStart(body: { email: string; password: string; name?: string }): Promise<{ ok: boolean; sent_to: string }> {
    const fd = new FormData();
    fd.append("email", body.email);
    fd.append("password", body.password);
    if (body.name) fd.append("name", body.name);
    const res = await fetch(`${BASE}/signup/start`, { method: "POST", body: fd });
    if (!res.ok) {
        let m = "Could not start signup.";
        try { const b = await res.json(); if (b && typeof b.error === "string") m = b.error; } catch { /* */ }
        throw new Error(m);
    }
    return res.json();
}

export async function signupVerify(email: string, otp: string): Promise<LoginResult & { ok: boolean }> {
    const fd = new FormData();
    fd.append("email", email);
    fd.append("otp", otp);
    const res = await fetch(`${BASE}/signup/verify`, { method: "POST", body: fd });
    if (!res.ok) {
        let m = "Verification failed.";
        try { const b = await res.json(); if (b && typeof b.error === "string") m = b.error; } catch { /* */ }
        throw new Error(m);
    }
    return res.json();
}

export async function getSignupSettings(): Promise<{ default_role: string }> {
    const res = await fetch(`${BASE}/admin/signup-settings`, { headers: authHeaders() });
    await handle401(res);
    if (!res.ok) return throwForStatus(res, "Failed to load signup settings");
    return res.json();
}

export async function setSignupDefaultRole(role: "agent" | "manager"): Promise<{ ok: boolean; default_role: string }> {
    const fd = new FormData();
    fd.append("default_role", role);
    const res = await fetch(`${BASE}/admin/signup-settings`, { method: "PUT", headers: authHeaders(), body: fd });
    await handle401(res);
    if (!res.ok) return throwForStatus(res, "Failed to save signup settings");
    return res.json();
}

// ---- Advanced monitoring: sessions / location / device ----
export type SessionRow = {
    ts: string;
    ip: string;
    browser: string;
    os: string;
    device: string; // Desktop | Mobile | Tablet
    ua?: string;
    country?: string;
    country_code?: string;
    region?: string;
    city?: string;
    lat?: number | null;
    lon?: number | null;
    isp?: string;
    ip_timezone?: string;
    // browser-provided
    tz?: string;
    locale?: string;
    screen?: string;
    platform?: string;
    geo_lat?: number | null;
    geo_lon?: number | null;
    geo_acc?: number | null;
    // derived (server)
    location?: string;
    flag?: string;
};

export type ProfileInfo = {
    tenant_id: string;
    email: string;
    name: string;
    role: Role;
    is_admin: boolean;
    status: string;
    created_at: string;
    self_signup: boolean;
    demo: boolean;
    demo_minutes?: number;
    demo_remaining_s?: number;
    first_seen: string;
    sessions_count: number;
    last_session: SessionRow;
    recent_sessions: SessionRow[];
};

// Full client profile for the Super-Admin monitoring panel.
export type ClientProfile = ClientInfo & {
    self_signup: boolean;
    first_seen: string;
    sessions_count: number;
    last_session: SessionRow;
    sessions: SessionRow[];
};

// Browser signals captured at app load (precise GPS only when consented).
export type BeaconPayload = {
    tz?: string;
    locale?: string;
    screen?: string;
    platform?: string;
    geo_lat?: number;
    geo_lon?: number;
    geo_acc?: number;
};

export async function sendSessionBeacon(payload: BeaconPayload): Promise<{ ok: boolean; session: SessionRow } | null> {
    try {
        const res = await fetch(`${BASE}/session/beacon`, {
            method: "POST",
            headers: { ...(authHeaders() as Record<string, string>), "Content-Type": "application/json" },
            body: JSON.stringify(payload || {}),
        });
        if (!res.ok) return null;
        return res.json();
    } catch {
        return null; // monitoring is best-effort; never break the app
    }
}

export async function getProfile(): Promise<ProfileInfo> {
    const res = await fetch(`${BASE}/profile`, { headers: authHeaders() });
    await handle401(res);
    if (!res.ok) return throwForStatus(res, "Failed to load profile");
    return res.json();
}

export async function getClientProfile(tid: string): Promise<ClientProfile> {
    const res = await fetch(`${BASE}/admin/clients/${encodeURIComponent(tid)}/profile`, { headers: authHeaders() });
    await handle401(res);
    if (!res.ok) return throwForStatus(res, "Failed to load client profile");
    const data = await res.json();
    return data.profile as ClientProfile;
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

// ============================================================
// SIDEBAR / NAV CONFIG (Super-Admin Sidebar Builder)
// Per-tenant {order, hidden, labels, childOrder} applied client-side over the
// static nav. Keyed by a stable nav key (href, or "group:<title>"). Cosmetic.
// ============================================================
// A super-admin-created nav entry. isSection => a new top-level category (no href);
// otherwise a link {href} that lives under `parent` (a section key).
export type NavCustomItem = {
    key: string;
    label: string;
    isSection?: boolean;
    href?: string;
    parent?: string;
    icon?: string;
};

export type NavConfig = {
    order?: string[]; // ordered top-level nav keys
    hidden?: string[]; // nav keys to hide (top-level OR child)
    labels?: Record<string, string>; // nav key -> custom label
    childOrder?: Record<string, string[]>; // group key -> ordered child keys
    parentOf?: Record<string, string>; // child key -> new parent (move to another category)
    custom?: NavCustomItem[]; // admin-created links / sections
};

// The logged-in tenant's own sidebar config (the Sidebar applies it). Swallows
// errors -> empty config so the sidebar NEVER breaks if the endpoint is down.
export async function getMyNavConfig(): Promise<{ config: NavConfig }> {
    try {
        const res = await fetch(`${BASE}/me/nav-config`, { headers: authHeaders() });
        if (!res.ok) return { config: {} };
        return await res.json();
    } catch {
        return { config: {} };
    }
}

// Super-admin: read a specific tenant's sidebar config (for the builder).
export async function getAdminNavConfig(
    tenantId: string
): Promise<{ tenant_id: string; config: NavConfig }> {
    const res = await fetch(
        `${BASE}/admin/nav-config?tenant_id=${encodeURIComponent(tenantId)}`,
        { headers: authHeaders() }
    );
    await handle401(res);
    if (!res.ok) throw new Error("Failed to load sidebar config");
    return res.json();
}

// Super-admin: save a tenant's sidebar config.
export async function saveAdminNavConfig(
    tenantId: string,
    config: NavConfig
): Promise<{ ok: boolean; config: NavConfig }> {
    const fd = new FormData();
    fd.append("tenant_id", tenantId);
    fd.append("config", JSON.stringify(config));
    const res = await fetch(`${BASE}/admin/nav-config`, {
        method: "POST",
        headers: authHeaders(),
        body: fd,
    });
    await handle401(res);
    if (!res.ok) throw new Error("Failed to save sidebar config");
    return res.json();
}

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
// SYSTEM LOGS & ERRORS — super-admin observability ("System Logs" in the panel).
// Backed by /admin/logs* (logging_service). All super-admin-gated; degrade to a
// clean empty shape on 404 so the page never throws when the module is dormant.
// ============================================================================
export type SystemLogLevel = "debug" | "info" | "warning" | "error" | "critical";

export type SystemEvent = {
    id: string;
    seq: number;
    ts: string;
    level: SystemLogLevel;
    source: string;
    message: string;
    error_type?: string;
    tenant_id?: string;
    call_id?: string;
    fingerprint?: string;
    context?: Record<string, unknown>;
    // present on the detail endpoint:
    count?: number;
    first_seen?: string;
    last_seen?: string;
    suggestion?: string;
};

export type SystemLogsPage = {
    events: SystemEvent[];
    total: number;
    limit: number;
    offset: number;
    note?: string;
};

export type SystemLogSummary = {
    by_level: Partial<Record<SystemLogLevel, number>>;
    total: number;
    last_24h: number;
    errors_24h: number;
    top_errors: {
        fingerprint: string;
        level: SystemLogLevel;
        source: string;
        message: string;
        count: number;
        last_seen?: string;
        last_id?: string;
    }[];
    note?: string;
};

export type NotificationFeed = {
    events: SystemEvent[];
    latest_seq: number;
    unread: number;
    unread_errors: number;
};

export async function getSystemLogs(opts?: {
    limit?: number; offset?: number; level?: string; source?: string;
    tenant_id?: string; q?: string; since?: string;
}): Promise<SystemLogsPage> {
    const params = new URLSearchParams();
    if (opts?.limit != null) params.set("limit", String(opts.limit));
    if (opts?.offset != null) params.set("offset", String(opts.offset));
    if (opts?.level) params.set("level", opts.level);
    if (opts?.source) params.set("source", opts.source);
    if (opts?.tenant_id) params.set("tenant_id", opts.tenant_id);
    if (opts?.q) params.set("q", opts.q);
    if (opts?.since) params.set("since", opts.since);
    const res = await fetch(`${BASE}/admin/logs?${params.toString()}`, { headers: authHeaders() });
    await handle401(res);
    if (res.status === 404) return { events: [], total: 0, limit: opts?.limit ?? 100, offset: opts?.offset ?? 0 };
    if (!res.ok) throw new Error("Failed to fetch system logs");
    return res.json();
}

export async function getSystemLogSummary(): Promise<SystemLogSummary> {
    const res = await fetch(`${BASE}/admin/logs/summary`, { headers: authHeaders() });
    await handle401(res);
    if (!res.ok) return { by_level: {}, total: 0, last_24h: 0, errors_24h: 0, top_errors: [] };
    return res.json();
}

export async function getSystemLogDetail(id: string): Promise<SystemEvent | null> {
    const res = await fetch(`${BASE}/admin/logs/${encodeURIComponent(id)}`, { headers: authHeaders() });
    await handle401(res);
    if (!res.ok) return null;
    return res.json();
}

export async function suggestSystemLogFix(id: string, force = false): Promise<string> {
    try {
        const res = await fetch(`${BASE}/admin/logs/${encodeURIComponent(id)}/suggest${force ? "?force=1" : ""}`, {
            method: "POST",
            headers: authHeaders(),
        });
        await handle401(res);
        if (!res.ok) return "";
        const d = (await res.json().catch(() => ({}))) as { suggestion?: string };
        return d.suggestion || "";
    } catch {
        return "";
    }
}

export type SystemLogHealth = {
    ready: boolean;
    path?: string;
    writable?: boolean;
    file_exists?: boolean;
    file_bytes?: number;
    ring_count?: number;
    agg_groups?: number;
    latest_seq?: number;
    telegram?: boolean;
    ai_fix?: boolean;
    init_ok?: boolean;
    note?: string;
};

// Self-test: is capture live, where does it write, can it write? Backs the System Logs status
// chip. Returns {ready:false} on any failure (the route 503s when not ready but still sends JSON).
export async function getSystemLogHealth(): Promise<SystemLogHealth> {
    try {
        const res = await fetch(`${BASE}/admin/logs/health`, { headers: authHeaders() });
        await handle401(res);
        return (await res.json()) as SystemLogHealth;
    } catch {
        return { ready: false };
    }
}

// Emit a synthetic event so an operator can SEE capture working end-to-end.
export async function emitTestSystemLog(): Promise<boolean> {
    try {
        const res = await fetch(`${BASE}/admin/logs/test`, { method: "POST", headers: authHeaders() });
        await handle401(res);
        const d = (await res.json().catch(() => ({}))) as { ok?: boolean };
        return !!d.ok;
    } catch {
        return false;
    }
}

export async function getNotifications(opts?: { after?: number; limit?: number }): Promise<NotificationFeed> {
    try {
        const params = new URLSearchParams();
        if (opts?.after != null) params.set("after", String(opts.after));
        if (opts?.limit != null) params.set("limit", String(opts.limit));
        const res = await fetch(`${BASE}/admin/notifications?${params.toString()}`, { headers: authHeaders() });
        await handle401(res);
        if (!res.ok) return { events: [], latest_seq: 0, unread: 0, unread_errors: 0 };
        return res.json();
    } catch {
        return { events: [], latest_seq: 0, unread: 0, unread_errors: 0 };
    }
}

// ============================================================================
// PERFORMANCE — white-labeled metrics for the super-admin Performance page. Thin proxy to the
// observability backend's Prometheus query API via /admin/metrics/*. Returns the Prometheus
// JSON shape; the page extracts scalars + series. NEVER throws (degrades to an error status).
// ============================================================================
export type PromValue = [number, string];
export type PromSeries = { metric: Record<string, string>; value?: PromValue; values?: PromValue[] };
export type PromResponse = { status: string; data?: { resultType: string; result: PromSeries[] }; error?: string };

export async function getMetricInstant(query: string): Promise<PromResponse> {
    try {
        const res = await fetch(`${BASE}/admin/metrics/instant?query=${encodeURIComponent(query)}`,
            { headers: authHeaders() });
        await handle401(res);
        if (!res.ok) return { status: "error", error: `http_${res.status}` };
        return res.json();
    } catch {
        return { status: "error", error: "unreachable" };
    }
}

export async function getMetricRange(query: string, minutes = 60, step = 60): Promise<PromResponse> {
    try {
        const p = new URLSearchParams({ query, minutes: String(minutes), step: String(step) });
        const res = await fetch(`${BASE}/admin/metrics/range?${p.toString()}`, { headers: authHeaders() });
        await handle401(res);
        if (!res.ok) return { status: "error", error: `http_${res.status}` };
        return res.json();
    } catch {
        return { status: "error", error: "unreachable" };
    }
}

// ============================================================================
// OBSERVABILITY ANALYTICS — trace/APM/request data for the native System Logs (Traces/Requests)
// + Performance dashboards. Backed by /admin/obs/* (ClickHouse). ClickHouse returns numeric
// columns as STRINGS in JSONEachRow, so consumers Number() the values. NEVER throws.
// ============================================================================
export type ObsRow = Record<string, string | number | boolean | null>;
export type ObsResponse = { rows: ObsRow[]; error?: string; row?: ObsRow };

async function obsGet(path: string, params: Record<string, string | number>): Promise<ObsResponse> {
    try {
        const p = new URLSearchParams();
        Object.entries(params).forEach(([k, v]) => {
            if (v !== "" && v != null) p.set(k, String(v));
        });
        const qs = p.toString();
        const res = await fetch(`${BASE}${path}${qs ? `?${qs}` : ""}`, { headers: authHeaders() });
        await handle401(res);
        if (!res.ok) return { rows: [], error: `http_${res.status}` };
        return res.json();
    } catch {
        return { rows: [], error: "unreachable" };
    }
}

export const getObsServices = (minutes = 1440) => obsGet("/admin/obs/services", { minutes });
export const getObsSummary = (minutes: number, service: string) => obsGet("/admin/obs/summary", { minutes, service });
export const getObsRed = (minutes: number, service: string) => obsGet("/admin/obs/red", { minutes, service });
export const getObsRoutes = (minutes: number, service: string, limit = 50) => obsGet("/admin/obs/routes", { minutes, service, limit });
export const getObsStatus = (minutes: number, service: string) => obsGet("/admin/obs/status", { minutes, service });
export const getObsServiceDist = (minutes: number) => obsGet("/admin/obs/service-dist", { minutes });
export const getObsErrors = (minutes: number, service: string, limit = 20) => obsGet("/admin/obs/errors", { minutes, service, limit });
export const getObsTraces = (opts: { minutes: number; service: string; errors_only?: number; q?: string; limit?: number }) =>
    obsGet("/admin/obs/traces", { minutes: opts.minutes, service: opts.service, errors_only: opts.errors_only ?? 0, q: opts.q ?? "", limit: opts.limit ?? 60 });
export const getObsTrace = (traceId: string) => obsGet(`/admin/obs/trace/${encodeURIComponent(traceId)}`, {});

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

// ---- P3 Service Control Center: the MANAGED (encrypted) provider layer (/admin/provider-pool/*) ----
export type ProviderPoolKey = {
    fingerprint: string;
    status?: string;          // healthy | degraded | cooling
    score?: number;
    open?: boolean;
    trips?: number;
    latency_ewma_ms?: number;
    reliability?: number;
    success_count?: number;
    fail_count?: number;
    rate_limit_count?: number;
    success_rate?: number;
    last_used_ts?: number;
    retry_in_s?: number;
    last_error?: string;
};
export type ProviderPoolHealth = { provider: string; healthy: number; total: number; keys: ProviderPoolKey[] };
export type ProviderPoolUsageRow = {
    provider: string;
    fingerprint: string;
    calls?: number;
    success?: number;
    failures?: number;
    rate_limits?: number;
    latency_ms_avg?: number;
    score?: number;
    status?: string;
    success_pct?: number;
    last_used_ms?: number;
};

export async function getProviderPoolHealth(provider?: string): Promise<{ health: Record<string, ProviderPoolHealth>; platform_tenant?: string; error?: string }> {
    try {
        const q = provider ? `?provider=${encodeURIComponent(provider)}` : "";
        const res = await fetch(`${BASE}/admin/provider-pool/health${q}`, { headers: authHeaders() });
        await handle401(res);
        if (!res.ok) return { health: {}, error: res.status === 503 ? "unavailable" : "error" };
        return res.json();
    } catch {
        return { health: {}, error: "unreachable" };
    }
}

export async function getProviderPoolUsage(minutes = 1440): Promise<{ durable: ProviderPoolUsageRow[]; durable_error?: string }> {
    try {
        const res = await fetch(`${BASE}/admin/provider-pool/usage?minutes=${minutes}`, { headers: authHeaders() });
        await handle401(res);
        if (!res.ok) return { durable: [], durable_error: "unavailable" };
        const d = await res.json();
        return { durable: Array.isArray(d.durable) ? d.durable : [], durable_error: d.durable_error };
    } catch {
        return { durable: [], durable_error: "unreachable" };
    }
}

export async function addProviderPoolKey(provider: string, key: string, label?: string): Promise<{ ok: boolean; fingerprint?: string; error?: string; detail?: string }> {
    const fd = new FormData();
    fd.append("provider", provider);
    fd.append("key", key);
    if (label) fd.append("label", label);
    const res = await fetch(`${BASE}/admin/provider-pool/keys`, { method: "POST", headers: authHeaders(), body: fd });
    await handle401(res);
    return res.json().catch(() => ({ ok: false, error: "bad response" }));
}

export async function setProviderPoolKeyEnabled(provider: string, fingerprint: string, enabled: boolean): Promise<{ status?: string; error?: string }> {
    const fd = new FormData();
    fd.append("enabled", enabled ? "1" : "0");
    const res = await fetch(`${BASE}/admin/provider-pool/keys/${encodeURIComponent(provider)}/${encodeURIComponent(fingerprint)}`, { method: "PUT", headers: authHeaders(), body: fd });
    await handle401(res);
    return res.json().catch(() => ({ error: "bad response" }));
}

export async function deleteProviderPoolKey(provider: string, fingerprint: string): Promise<{ ok?: boolean; error?: string }> {
    const res = await fetch(`${BASE}/admin/provider-pool/keys/${encodeURIComponent(provider)}/${encodeURIComponent(fingerprint)}`, { method: "DELETE", headers: authHeaders() });
    await handle401(res);
    return res.json().catch(() => ({ ok: false, error: "bad response" }));
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
// AI-draft a campaign call-script with Claude Sonnet 3.5 (Script Studio "Generate with AI").
// Read-only on the campaign — returns the drafted text; the operator edits + saves it. Never throws.
export async function generateCampaignScript(
    cid: string,
    brief?: string
): Promise<{ ok: boolean; script?: string; model_label?: string; error?: string; message?: string }> {
    try {
        const res = await fetch(`${BASE}/campaigns/${encodeURIComponent(cid)}/script/generate`, {
            method: "POST",
            headers: { ...authHeaders(), "Content-Type": "application/json" },
            body: JSON.stringify({ brief: brief || "" }),
        });
        await handle401(res);
        const d = (await res.json().catch(() => ({}))) as {
            ok?: boolean; script?: string; model_label?: string; error?: string; message?: string;
        };
        if (!res.ok || !d.ok) return { ok: false, error: d.error || `http_${res.status}`, message: d.message };
        return { ok: true, script: d.script, model_label: d.model_label };
    } catch {
        return { ok: false, error: "unreachable" };
    }
}

// P7.3: AI-draft ONE Script Studio 2.0 block. Returns the block fields to merge onto the block.
export type GeneratedBlock = {
    type?: string; text?: string; items?: string[];
    qa?: { q: string; a: string }[]; options?: string[]; goal?: string;
};
export async function generateScriptBlock(
    cid: string, blockType: string, brief?: string,
): Promise<{ ok: boolean; block?: GeneratedBlock; model_label?: string; error?: string; message?: string }> {
    try {
        const res = await fetch(`${BASE}/campaigns/${encodeURIComponent(cid)}/script/generate-block`, {
            method: "POST",
            headers: { ...authHeaders(), "Content-Type": "application/json" },
            body: JSON.stringify({ block_type: blockType, brief: brief || "" }),
        });
        await handle401(res);
        const d = (await res.json().catch(() => ({}))) as {
            ok?: boolean; block?: GeneratedBlock; model_label?: string; error?: string; message?: string;
        };
        if (!res.ok || !d.ok) return { ok: false, error: d.error || `http_${res.status}`, message: d.message };
        return { ok: true, block: d.block, model_label: d.model_label };
    } catch {
        return { ok: false, error: "unreachable" };
    }
}

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
    // W-FRONTEND-RECONCILE §3 Fix 2 — dashboard GlobalFilters forward these so
    // the box can narrow server-side. Safe if the live /leads ignores any it
    // doesn't support (extra query params are dropped, not errored); the
    // composeReport client-side post-filter is the guaranteed fallback.
    from?: string;
    to?: string;
    campaign_id?: string;
    status?: string;
}): Promise<LeadsPage> {
    const params = new URLSearchParams();
    if (opts?.hot) params.set("hot", "1");
    if (opts?.sort) params.set("sort", opts.sort);
    if (opts?.batch) params.set("batch", opts.batch);
    if (opts?.limit != null) params.set("limit", String(opts.limit));
    if (opts?.offset != null && opts.offset > 0) params.set("offset", String(opts.offset));
    if (opts?.from) params.set("from", opts.from);
    if (opts?.to) params.set("to", opts.to);
    if (opts?.campaign_id) params.set("campaign_id", opts.campaign_id);
    if (opts?.status) params.set("status", opts.status);
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
    // Retention & Storage step — how long the backend keeps the call recording /
    // transcript. Day counts the backend understands: 0 = don't store (discard at
    // call end), -1 = keep forever, N = auto-trash after N days. The backend now
    // accepts these on POST /run (Egress + transcript persistence + auto-delete
    // sweep). Optional + degrades safely (server ignores unknown fields).
    recording_retention_days?: number;
    transcript_retention_days?: number;
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
    // Retention & Storage — persist the founder's recording/transcript retention
    // choice into the real run payload (0=don't store, -1=forever, N=N-day TTL).
    // Sent as form fields so the backend's POST /run handler can configure Egress
    // + transcript persistence + the auto-delete sweep. -1/0 ARE meaningful values
    // (forever / off), so we forward whenever the field is provided, not just > 0.
    if (payload.recording_retention_days != null)
        fd.append("recording_retention_days", String(payload.recording_retention_days));
    if (payload.transcript_retention_days != null)
        fd.append("transcript_retention_days", String(payload.transcript_retention_days));
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

// ---- Stop a running campaign job (halts new dialing; in-flight calls drain) ----
export async function stopJob(job: string): Promise<{ ok: boolean; state?: string }> {
    const res = await fetch(`${BASE}/jobs/${encodeURIComponent(job)}/stop`, {
        method: "POST",
        headers: authHeaders(),
    });
    await handle401(res);
    if (!res.ok) throw new Error("Failed to stop campaign");
    return res.json();
}

// ---- Pre-launch readiness (real provider RTT + db/redis/livekit + recent call latency) ----
export type PreflightCheck = {
    id: string;
    label: string;
    status: "green" | "yellow" | "red";
    latency_ms: number | null;
    detail: string;
};
export type PreflightResult = {
    ok: boolean;
    verdict: "ok" | "slow" | "down";
    headline: string;
    worst_latency_ms: number | null;
    checks: PreflightCheck[];
    at?: string;
};
export async function getPreflight(cid: string): Promise<PreflightResult> {
    const res = await fetch(`${BASE}/campaigns/${encodeURIComponent(cid)}/preflight`, {
        headers: authHeaders(),
    });
    await handle401(res);
    if (!res.ok) throw new Error("Failed to run preflight");
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
    order?: "asc" | "desc";
    slim?: boolean;
    campaign_id?: string;
    outcome?: string;
    from?: string;   // inclusive date-range filter on started_at (YYYY-MM-DD or ISO) — dashboard range
    to?: string;
    // Lane C SPEED — ask the backend to sort across ALL records (not just the
    // loaded page). `sort_by` names the column; `order` the direction. The call
    // sites keep a client-side sort fallback for a backend that ignores these.
    sort_by?: string;
};
export async function getCalls(opts?: GetCallsOpts): Promise<CallsPage> {
    const params = new URLSearchParams();
    params.set("limit", String(opts?.limit ?? 200));
    if (opts?.offset != null && opts.offset > 0) params.set("offset", String(opts.offset));
    if (opts?.order) params.set("order", opts.order);
    if (opts?.sort_by) params.set("sort_by", opts.sort_by);
    if (opts?.slim) params.set("slim", "1");
    if (opts?.campaign_id) params.set("campaign_id", opts.campaign_id);
    if (opts?.outcome) params.set("outcome", opts.outcome);
    if (opts?.from) params.set("from", opts.from);
    if (opts?.to) params.set("to", opts.to);
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

// ---- Call recording (presigned player URL) ----
// GET /calls/{id}/recording returns the freshly-minted, range-streamable presigned
// URL for an OUTBOUND call's audio plus availability metadata. The recording lands
// in DO Spaces seconds after hangup and this endpoint self-heals the URL on read —
// so the player can appear within seconds of a call ending (we poll for it). The
// `/calls/{id}` detail endpoint does NOT carry this URL, which is why the Call-Logs
// modal never showed a player; this is the missing wiring. Dormant-safe: any
// failure resolves to `{ playable:false }` so the UI shows the calm "preparing"
// state, never an error wall.
export type CallRecording = {
    playable: boolean;
    recording_presigned_url?: string | null;
    size_bytes?: number | null;
    duration_s?: number | null;
    recording_status?: string | null;
};

export async function getCallRecording(id: string): Promise<CallRecording> {
    try {
        const res = await fetch(
            `${BASE}/calls/${encodeURIComponent(id)}/recording`,
            { headers: authHeaders() }
        );
        await handle401(res);
        if (!res.ok) return { playable: false };
        const data = (await res.json().catch(() => ({}))) as Record<string, unknown>;
        // Tolerate field drift: the player URL may arrive under any of these keys.
        const url =
            (typeof data.recording_presigned_url === "string" && data.recording_presigned_url) ||
            (typeof data.url === "string" && data.url) ||
            (typeof data.recording_url === "string" && data.recording_url) ||
            null;
        const dur = Number(data.duration_s);
        return {
            playable: Boolean(data.playable) || !!url,
            recording_presigned_url: url,
            size_bytes:
                typeof data.size_bytes === "number" ? data.size_bytes : null,
            duration_s: Number.isFinite(dur) && dur > 0 ? dur : null,
            recording_status:
                typeof data.recording_status === "string"
                    ? data.recording_status
                    : null,
        };
    } catch {
        return { playable: false }; // offline / route absent -> calm "preparing"
    }
}

// Word-accurate, audio-aligned transcript for the synced playback highlight. The
// backend re-transcribes the recording (cached) for per-word timestamps; when it
// can't (no recording / disabled / failure) it returns {timed:false} and the panel
// uses its estimate instead. NEVER throws.
export type TimedWordApi = { w: string; s: number; e: number };
export type TimedTurnApi = { role: string; text: string; t0: number; t1: number; words?: TimedWordApi[] };
export type TimedTranscriptApi = { timed: boolean; turns?: TimedTurnApi[]; duration?: number };

export async function getCallTranscriptTimed(id: string): Promise<TimedTranscriptApi> {
    try {
        const res = await fetch(
            `${BASE}/calls/${encodeURIComponent(id)}/transcript/timed`,
            { headers: authHeaders() }
        );
        await handle401(res);
        if (!res.ok) return { timed: false };
        const d = (await res.json().catch(() => ({}))) as TimedTranscriptApi;
        return d && d.timed && Array.isArray(d.turns) ? d : { timed: false };
    } catch {
        return { timed: false };
    }
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

// Realtime provider network-health for the Providers "Live status" row: signal bars + latency,
// graded green/yellow/red. Polled ~5s by the Voice & Providers card. Dormant-safe -> [] on any error.
export type ProviderHealth = {
    id: string;
    role: string; // "llm" | "tts" | "stt" | ""
    label: string;
    available: boolean;
    reachable: boolean;
    latency_ms: number | null;
    bars: number; // 0..5
    status: "green" | "yellow" | "red";
    note?: string;
};

export async function getProviderHealth(ids?: string[]): Promise<ProviderHealth[]> {
    try {
        const q = ids && ids.length ? `?ids=${encodeURIComponent(ids.join(","))}` : "";
        const res = await fetch(`${BASE}/providers/health${q}`, { headers: authHeaders() });
        await handle401(res);
        if (!res.ok) return [];
        const d = (await res.json()) as { providers?: ProviderHealth[] };
        return Array.isArray(d.providers) ? d.providers : [];
    } catch {
        return [];
    }
}

// ---- P1 Voice Performance Analytics (reads over the agent-written haptica_voice_* CH tables) ----
// All dormant-safe: a missing/empty obs backend -> empty shapes so the page shows a calm empty state.
export type VoiceFilters = {
    tenant_id?: string; campaign_id?: string; agent_name?: string; phone?: string;
    provider?: string; model?: string; status?: string; stage?: string;
};
export type VoiceSummary = { row?: ObsRow; latency_by_stage?: ObsRow[]; error?: string };
export type VoiceFilterOptions = {
    row?: {
        agents?: string[]; campaigns?: string[]; llm_providers?: string[]; tts_providers?: string[];
        stt_providers?: string[]; models?: string[]; statuses?: string[]; tenants?: string[];
    };
    error?: string;
};
export type VoiceCallBundle = { detail?: ObsRow; timeline?: ObsRow[]; latency?: ObsRow; error?: string };
export type VoiceStack = { combos: ObsRow[]; stages: ObsRow[]; error?: string };

function voiceQS(minutes: number, f?: VoiceFilters, extra?: Record<string, string | number>): string {
    const p = new URLSearchParams();
    p.set("minutes", String(minutes));
    if (f) for (const [k, v] of Object.entries(f)) if (v) p.set(k, String(v));
    if (extra) for (const [k, v] of Object.entries(extra)) p.set(k, String(v));
    return p.toString();
}

export async function getVoiceSummary(minutes: number, f?: VoiceFilters): Promise<VoiceSummary> {
    try {
        const res = await fetch(`${BASE}/admin/obs/voice/summary?${voiceQS(minutes, f)}`, { headers: authHeaders() });
        await handle401(res);
        if (!res.ok) return { row: {}, latency_by_stage: [], error: "unavailable" };
        return res.json();
    } catch {
        return { row: {}, latency_by_stage: [], error: "unreachable" };
    }
}

export async function getVoiceRed(minutes: number, f?: VoiceFilters): Promise<{ rows: ObsRow[]; error?: string }> {
    try {
        const res = await fetch(`${BASE}/admin/obs/voice/red?${voiceQS(minutes, f)}`, { headers: authHeaders() });
        await handle401(res);
        if (!res.ok) return { rows: [], error: "unavailable" };
        return res.json();
    } catch {
        return { rows: [], error: "unreachable" };
    }
}

export async function getVoiceCalls(minutes: number, f?: VoiceFilters, limit = 100): Promise<{ rows: ObsRow[]; error?: string }> {
    try {
        const res = await fetch(`${BASE}/admin/obs/voice/calls?${voiceQS(minutes, f, { limit })}`, { headers: authHeaders() });
        await handle401(res);
        if (!res.ok) return { rows: [], error: "unavailable" };
        return res.json();
    } catch {
        return { rows: [], error: "unreachable" };
    }
}

export async function getVoiceFilterOptions(minutes = 1440): Promise<VoiceFilterOptions> {
    try {
        const res = await fetch(`${BASE}/admin/obs/voice/filters?minutes=${minutes}`, { headers: authHeaders() });
        await handle401(res);
        if (!res.ok) return { row: {} };
        return res.json();
    } catch {
        return { row: {} };
    }
}

export async function getVoiceCall(callId: string): Promise<VoiceCallBundle> {
    try {
        const res = await fetch(`${BASE}/admin/obs/voice/call/${encodeURIComponent(callId)}`, { headers: authHeaders() });
        await handle401(res);
        if (!res.ok) return { detail: {}, timeline: [], latency: {}, error: "unavailable" };
        return res.json();
    } catch {
        return { detail: {}, timeline: [], latency: {}, error: "unreachable" };
    }
}

export async function getVoiceStack(minutes: number, f?: VoiceFilters): Promise<VoiceStack> {
    try {
        const res = await fetch(`${BASE}/admin/obs/voice/stack?${voiceQS(minutes, f)}`, { headers: authHeaders() });
        await handle401(res);
        if (!res.ok) return { combos: [], stages: [], error: "unavailable" };
        return res.json();
    } catch {
        return { combos: [], stages: [], error: "unreachable" };
    }
}

// ---- Transcript content-quality (LLM analysis of the actual dialogue) ----
export type TranscriptIssue = { type?: string; severity?: string; quote?: string; note?: string };
export type TranscriptQuality = {
    ok: boolean;
    score?: number;
    grade?: string;
    summary?: string;
    dims?: Record<string, number>;
    issues?: TranscriptIssue[];
    cached?: boolean;
    error?: string;
    message?: string;
};
export async function getVoiceCallQuality(callId: string, opts?: { force?: boolean; cachedOnly?: boolean }): Promise<TranscriptQuality> {
    const qs = opts?.force ? "?force=1" : opts?.cachedOnly ? "?cached=1" : "";
    try {
        const res = await fetch(`${BASE}/admin/obs/voice/call/${encodeURIComponent(callId)}/quality${qs}`, { headers: authHeaders() });
        await handle401(res);
        if (!res.ok) return { ok: false, error: "unavailable" };
        return res.json();
    } catch {
        return { ok: false, error: "unreachable" };
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
// Service categories the founder can register. The voice agent consumes stt/llm/tts today;
// the rest are stored for routing / integration use. Mirrors _KINDS in custom_providers.py.
export type ServiceKind =
    | "stt" | "llm" | "tts" | "embedding" | "rerank" | "vad" | "telephony" | "realtime" | "webhook" | "other";

export const SERVICE_KINDS: { id: ServiceKind; label: string; hint: string }[] = [
    { id: "llm", label: "LLM", hint: "Chat / completion model (OpenAI-compatible)" },
    { id: "stt", label: "STT", hint: "Speech-to-text" },
    { id: "tts", label: "TTS", hint: "Text-to-speech" },
    { id: "embedding", label: "Embedding", hint: "Vector embeddings" },
    { id: "rerank", label: "Rerank", hint: "Reranker / relevance scorer" },
    { id: "vad", label: "VAD", hint: "Voice-activity detection" },
    { id: "telephony", label: "Telephony", hint: "SIP / PSTN trunk" },
    { id: "realtime", label: "Realtime", hint: "Realtime / streaming voice" },
    { id: "webhook", label: "Webhook", hint: "Outbound webhook / integration" },
    { id: "other", label: "Other", hint: "Any other service" },
];

export type CustomProvider = {
    id: string;
    name: string;
    kind: ServiceKind;
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
    kind: ServiceKind;
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
    { key: "grow.famit_growth", kind: "page", parent_key: "mod.grow", label: "Famit Growth", nav_href: "/growth", sort_order: 19 },
    { key: "grow.signal_loop", kind: "page", parent_key: "mod.grow", label: "Signal Loop", nav_href: "/grow", sort_order: 20 },
    { key: "grow.campaigns", kind: "page", parent_key: "mod.grow", label: "Campaigns", nav_href: "/campaigns", sort_order: 21 },
    { key: "grow.campaigns.create", kind: "action", parent_key: "grow.campaigns", label: "Create campaign", sort_order: 22 },

    // REVENUE TOOLS — the ad-acquisition cluster (Ad Automation / Funnels / Form
    // Builder), promoted out of Grow into its OWN module so a super-admin can
    // HIDE/LOCK the whole section for a vendor that shouldn't see it. The page
    // KEYS are PRESERVED VERBATIM (grow.ads / grow.funnels / grow.forms) so the
    // backend's existing per-page entitlement still gates each child; only the
    // parent module changes (mod.grow → mod.revenue_tools). BACKEND DEPENDENCY:
    // /me/entitlements must register `mod.revenue_tools` for the module-level
    // HIDE/LOCK to take effect (until then it resolves permissive "on" and the
    // group hides only when all three child page-keys are hidden).
    { key: "mod.revenue_tools", kind: "module", parent_key: null, label: "Revenue Tools", sort_order: 26 },
    { key: "grow.ads", kind: "page", parent_key: "mod.revenue_tools", label: "Ad Automation", nav_href: "/ads", sort_order: 23 },
    { key: "grow.funnels", kind: "page", parent_key: "mod.revenue_tools", label: "Funnels", nav_href: "/funnels", sort_order: 24 },
    { key: "grow.forms", kind: "page", parent_key: "mod.revenue_tools", label: "Form Builder", nav_href: "/forms", sort_order: 25 },

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

    // Money → renamed "Credits" (label is cosmetic; KEYS are preserved verbatim so the backend
    // entitlement mirror keeps matching). The credit wallet is the CORE money surface (is_core →
    // never hidden by an entitlement). Payments (collections) + Billing fold into the same hub.
    { key: "mod.money", kind: "module", parent_key: null, label: "Credits", sort_order: 60 },
    { key: "money.credits", kind: "page", parent_key: "mod.money", label: "Credits", nav_href: "/credits", is_core: true, sort_order: 60 },
    { key: "money.payments", kind: "page", parent_key: "mod.money", label: "Payments", nav_href: "/payments", sort_order: 61 },
    { key: "money.billing_overview", kind: "page", parent_key: "mod.money", label: "Billing", nav_href: "/billing/overview", is_core: true, sort_order: 62 },

    { key: "mod.intelligence", kind: "module", parent_key: null, label: "Intelligence", sort_order: 70 },
    { key: "intelligence.analytics", kind: "page", parent_key: "mod.intelligence", label: "Analytics", nav_href: "/analytics", sort_order: 71 },

    // FAMIT RESEARCH — the premium "instrumented conversation science" lab (per-call affect/prosody
    // dynamics + the closed-loop Outcomes correlation). Its OWN module so a super-admin can gate it
    // as a high-end add-on per-tenant (mod.research → HIDE/LOCK drops/locks the rail entry + route).
    { key: "mod.research", kind: "module", parent_key: null, label: "Famit Research", sort_order: 72 },
    { key: "research.lab", kind: "page", parent_key: "mod.research", label: "Research Lab", nav_href: "/research", sort_order: 73 },

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
    asReturning = false,
    history?: { role: "user" | "assistant"; content: string }[],
): Promise<DryRunResult> {
    const fd = new FormData();
    fd.append("message", message);
    fd.append("as_returning", asReturning ? "1" : "");
    if (history && history.length) fd.append("history", JSON.stringify(history));
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

// ============================================================================
// CREDITS — credit-wallet + buy-credits + service costing matrix (/credits/*).
// The whole tree is DORMANT-SAFE: when FEATURE_CREDITS is off (404) or the box is
// older, every reader resolves to null / an empty-but-valid shape so the Credits
// hub degrades to a calm "not enabled yet" state instead of an error wall. Amounts
// arrive in BOTH ₹ (INR) and CREDITS (1 credit = ₹credit_rate_inr).
// ============================================================================
export type CreditWallet = {
    tenant_id: string;
    currency: string;
    credit_rate_inr: number;
    plan: string;
    balance_inr: number;
    balance_credits: number;
    held_inr: number;
    held_credits: number;
    lifetime_topup_inr: number;
    lifetime_topup_credits: number;
    lifetime_spend_inr: number;
    lifetime_spend_credits: number;
    mtd_spend_inr: number;
    mtd_spend_credits: number;
    low_balance: boolean;
    low_balance_threshold_inr: number;
    wallet_available: boolean;
    engine: string;
};

export type CreditLedgerEntry = {
    id: string;
    kind: "topup" | "grant" | "adjust" | "debit";
    service: string;
    description: string;
    amount_inr: number;
    amount_credits: number;
    status: string;
    ref: string;
    at: string;
};

export type CreditUsageService = {
    service: string;
    label: string;
    category: string;
    unit: string;
    qty: number;
    count: number;
    cost_inr: number;
    cost_credits: number;
};

export type CreditUsage = {
    currency: string;
    credit_rate_inr: number;
    from: string;
    to: string;
    total_inr: number;
    total_credits: number;
    services: CreditUsageService[];
    series: { date: string; cost_inr: number; cost_credits: number }[];
};

export type CreditPricingService = {
    key: string;
    label: string;
    category: string;
    unit: string;
    basis_inr: number;
    markup_pct: number;
    price_inr: number;
    price_credits: number;
    margin_inr: number;
    margin_pct: number | null;
    metered: boolean;
    description: string;
};

export type CreditPricingMatrix = {
    currency: string;
    credit_rate_inr: number;
    services: CreditPricingService[];
    rate_card?: Record<string, unknown>;
};

export type CreditGatewayInfo = { configured: boolean; currency: string; display_name: string };

export type CreditHealth = {
    ok: boolean;
    engine: string;
    credit_rate_inr: number;
    gateways: Record<string, CreditGatewayInfo>;
    default_gateway: string;
    topup_enabled: boolean;
};

export type CreditPackage = {
    id: string;
    credits: number;
    bonus: number;
    popular: boolean;
    price_inr: number;
    total_credits: number;
    bonus_pct: number;
};

export type CreditPackages = {
    packages: CreditPackage[];
    credit_rate_inr: number;
    gateways: Record<string, CreditGatewayInfo>;
    default_gateway: string;
    topup_enabled: boolean;
    min_topup_inr: number;
};

export type CreditCheckoutResult = {
    status: "created" | "not_configured" | "error";
    provider?: string;
    // razorpay
    order_id?: string;
    key_id?: string;
    // stripe
    session_id?: string;
    checkout_url?: string;
    amount_inr?: number;
    amount_minor?: number;
    credits?: number;
    currency?: string;
    message?: unknown;
};

export type CreditAdminTenant = {
    tenant_id: string;
    name: string;
    email: string;
    plan: string;
    balance_inr: number;
    balance_credits: number;
    mtd_spend_inr: number;
    low_balance: boolean;
};

export type CreditAdminOverview = {
    currency: string;
    credit_rate_inr: number;
    engine: string;
    tenants: CreditAdminTenant[];
    tenant_count: number;
    outstanding_inr: number;
    outstanding_credits: number;
    mtd_revenue_inr: number;
    mtd_cost_inr: number;
    mtd_margin_inr: number;
    gateways: Record<string, CreditGatewayInfo>;
    error?: string;
};

async function _creditsGet<T>(path: string): Promise<T | null> {
    try {
        const res = await fetch(`${BASE}${path}`, { headers: authHeaders() });
        await handle401(res);
        if (!res.ok) return null; // 404 (CREDITS off) / 5xx → dormant-safe
        return (await res.json()) as T;
    } catch {
        return null;
    }
}

export async function getCreditsHealth(): Promise<CreditHealth | null> {
    return _creditsGet<CreditHealth>("/credits/health");
}

export async function getCreditsWallet(): Promise<CreditWallet | null> {
    return _creditsGet<CreditWallet>("/credits/wallet");
}

export async function getCreditsLedger(limit = 100): Promise<{ ledger: CreditLedgerEntry[]; total: number }> {
    const data = await _creditsGet<{ ledger: CreditLedgerEntry[]; total: number }>(
        `/credits/ledger?limit=${limit}`
    );
    return data ?? { ledger: [], total: 0 };
}

export async function getCreditsUsage(opts?: { from?: string; to?: string }): Promise<CreditUsage | null> {
    const p = new URLSearchParams();
    if (opts?.from) p.set("from", opts.from);
    if (opts?.to) p.set("to", opts.to);
    const qs = p.toString();
    return _creditsGet<CreditUsage>(`/credits/usage${qs ? `?${qs}` : ""}`);
}

export async function getCreditsPricing(): Promise<CreditPricingMatrix | null> {
    return _creditsGet<CreditPricingMatrix>("/credits/pricing");
}

export async function getCreditsPackages(): Promise<CreditPackages | null> {
    return _creditsGet<CreditPackages>("/credits/packages");
}

// Create a Razorpay order / Stripe session for a top-up. Never throws — returns the
// gateway result (incl. {status:"not_configured"} when no gateway is keyed).
export async function createCreditsCheckout(input: {
    amount_inr?: number;
    credits?: number;
    package_id?: string;
    provider?: string;
}): Promise<CreditCheckoutResult> {
    try {
        const fd = new FormData();
        if (input.amount_inr != null) fd.append("amount_inr", String(input.amount_inr));
        if (input.credits != null) fd.append("credits", String(input.credits));
        if (input.package_id) fd.append("package_id", input.package_id);
        if (input.provider) fd.append("provider", input.provider);
        const res = await fetch(`${BASE}/credits/topup/checkout`, {
            method: "POST",
            headers: authHeaders(),
            body: fd,
        });
        await handle401(res);
        if (res.status === 404) return { status: "not_configured" };
        const body = (await res.json().catch(() => ({}))) as CreditCheckoutResult;
        return body && body.status ? body : { status: "error" };
    } catch {
        return { status: "error" };
    }
}

// ---- Super-admin credits control ----
export async function getCreditsAdminOverview(): Promise<CreditAdminOverview | null> {
    return _creditsGet<CreditAdminOverview>("/credits/admin/overview");
}

export async function getCreditsAdminPricing(): Promise<CreditPricingMatrix | null> {
    return _creditsGet<CreditPricingMatrix>("/credits/admin/pricing");
}

export async function saveCreditsPricing(
    overrides: Record<string, Partial<CreditPricingService>>
): Promise<CreditPricingMatrix | { ok: false }> {
    try {
        const res = await fetch(`${BASE}/credits/admin/pricing`, {
            method: "PUT",
            headers: { ...(authHeaders() as Record<string, string>), "Content-Type": "application/json" },
            body: JSON.stringify({ overrides }),
        });
        await handle401(res);
        if (!res.ok) return { ok: false };
        return (await res.json()) as CreditPricingMatrix;
    } catch {
        return { ok: false };
    }
}

export async function grantCredits(input: {
    tenant_id: string;
    credits?: number;
    amount_inr?: number;
    note?: string;
}): Promise<{ ok: boolean; credited_credits?: number; balance_credits?: number }> {
    try {
        const fd = new FormData();
        fd.append("tenant_id", input.tenant_id);
        if (input.credits != null) fd.append("credits", String(input.credits));
        if (input.amount_inr != null) fd.append("amount_inr", String(input.amount_inr));
        if (input.note) fd.append("note", input.note);
        const res = await fetch(`${BASE}/credits/admin/grant`, {
            method: "POST",
            headers: authHeaders(),
            body: fd,
        });
        await handle401(res);
        if (!res.ok) return { ok: false };
        return (await res.json()) as { ok: boolean; credited_credits?: number; balance_credits?: number };
    } catch {
        return { ok: false };
    }
}

// ════════════════════════════════════════════════════════════════════════════════════════════════
// Tolex — agent tooling & capability system (super-admin control plane). All dormant-safe: a missing
// backend module (503) resolves to empty/disabled shapes so the console renders a calm state.
// ════════════════════════════════════════════════════════════════════════════════════════════════
export type TolexCriticality = "normal" | "sensitive" | "critical";
export type TolexMode = "off" | "allow" | "confirm" | "pin" | "approve";

export type TolexTool = {
    key: string;
    name: string;
    category: string;          // info | data | scheduling | comms | handoff | transaction
    criticality: TolexCriticality;
    description: string;
    params: { type: string; properties: Record<string, unknown>; required?: string[] };
};

export type TolexToolGrant = { mode: TolexMode; max_amount?: number; hours?: string; dry_run?: boolean };

export type TolexGrants = {
    campaign_id: string;
    inherited: boolean;        // true ⇒ showing the default profile this campaign would inherit
    enabled: boolean;
    tools: Record<string, TolexToolGrant>;
};

export type TolexOp = {
    id: string; ts: string; campaign_id?: string; tenant_id?: string; phone?: string;
    tool: string; name?: string; criticality?: TolexCriticality; mode?: string;
    action: string;            // execute | queue | deny
    result?: string;           // executed | queued | denied | error
    needs?: string | null; reason?: string; detail?: string;
};

const EMPTY_TOLEX_GRANTS = (cid: string): TolexGrants =>
    ({ campaign_id: cid, inherited: false, enabled: false, tools: {} });

export async function getTolexCatalog(): Promise<{ catalog: TolexTool[]; runtime_enabled: boolean }> {
    try {
        const res = await fetch(`${BASE}/admin/tolex/catalog`, { headers: authHeaders() });
        await handle401(res);
        if (!res.ok) return { catalog: [], runtime_enabled: false };
        return res.json();
    } catch {
        return { catalog: [], runtime_enabled: false };
    }
}

export async function getTolexGrants(campaignId = ""): Promise<{ grants: TolexGrants }> {
    try {
        const q = campaignId ? `?campaign_id=${encodeURIComponent(campaignId)}` : "";
        const res = await fetch(`${BASE}/admin/tolex/grants${q}`, { headers: authHeaders() });
        await handle401(res);
        if (!res.ok) return { grants: EMPTY_TOLEX_GRANTS(campaignId) };
        return res.json();
    } catch {
        return { grants: EMPTY_TOLEX_GRANTS(campaignId) };
    }
}

export async function saveTolexGrants(data: {
    campaign_id: string; enabled: boolean; tools: Record<string, TolexToolGrant>;
}): Promise<{ ok: boolean; grants: TolexGrants }> {
    const res = await fetch(`${BASE}/admin/tolex/grants`, {
        method: "PUT",
        headers: { ...authHeaders(), "Content-Type": "application/json" },
        body: JSON.stringify(data),
    });
    await handle401(res);
    if (!res.ok) return throwForStatus(res, "Failed to save Tolex grants");
    return res.json();
}

export async function enableRecommendedTolex(campaignId = ""): Promise<{ ok: boolean; grants: TolexGrants }> {
    const q = campaignId ? `?campaign_id=${encodeURIComponent(campaignId)}` : "";
    const res = await fetch(`${BASE}/admin/tolex/grants/enable-recommended${q}`, {
        method: "POST", headers: authHeaders(),
    });
    await handle401(res);
    if (!res.ok) return throwForStatus(res, "Failed to enable recommended");
    return res.json();
}

export async function getTolexOps(campaignId = "", limit = 200): Promise<{ ops: TolexOp[] }> {
    try {
        const p = new URLSearchParams();
        if (campaignId) p.set("campaign_id", campaignId);
        p.set("limit", String(limit));
        const res = await fetch(`${BASE}/admin/tolex/ops?${p.toString()}`, { headers: authHeaders() });
        await handle401(res);
        if (!res.ok) return { ops: [] };
        return res.json();
    } catch {
        return { ops: [] };
    }
}

// ---- Tenant surface (/tolex/*) — a tenant manages ONLY its own agent's tooling. Same shapes; the
// scope is the caller's auth-derived tenant (server-enforced). Used by the Grow "Agent Tools" page. ----
export const TolexApiAdmin = { getCatalog: getTolexCatalog, getGrants: getTolexGrants, saveGrants: saveTolexGrants, enableRecommended: enableRecommendedTolex, getOps: getTolexOps };

export async function getMyToolsCatalog(): Promise<{ catalog: TolexTool[]; runtime_enabled: boolean }> {
    try {
        const res = await fetch(`${BASE}/tolex/catalog`, { headers: authHeaders() });
        await handle401(res);
        if (!res.ok) return { catalog: [], runtime_enabled: false };
        return res.json();
    } catch {
        return { catalog: [], runtime_enabled: false };
    }
}

export async function getMyToolsGrants(campaignId = ""): Promise<{ grants: TolexGrants }> {
    try {
        const q = campaignId ? `?campaign_id=${encodeURIComponent(campaignId)}` : "";
        const res = await fetch(`${BASE}/tolex/grants${q}`, { headers: authHeaders() });
        await handle401(res);
        if (!res.ok) return { grants: EMPTY_TOLEX_GRANTS(campaignId) };
        return res.json();
    } catch {
        return { grants: EMPTY_TOLEX_GRANTS(campaignId) };
    }
}

export async function saveMyToolsGrants(data: {
    campaign_id: string; enabled: boolean; tools: Record<string, TolexToolGrant>;
}): Promise<{ ok: boolean; grants: TolexGrants }> {
    const res = await fetch(`${BASE}/tolex/grants`, {
        method: "PUT",
        headers: { ...authHeaders(), "Content-Type": "application/json" },
        body: JSON.stringify(data),
    });
    await handle401(res);
    if (!res.ok) return throwForStatus(res, "Failed to save agent tools");
    return res.json();
}

export async function enableRecommendedMyTools(campaignId = ""): Promise<{ ok: boolean; grants: TolexGrants }> {
    const q = campaignId ? `?campaign_id=${encodeURIComponent(campaignId)}` : "";
    const res = await fetch(`${BASE}/tolex/grants/enable-recommended${q}`, { method: "POST", headers: authHeaders() });
    await handle401(res);
    if (!res.ok) return throwForStatus(res, "Failed to enable recommended");
    return res.json();
}

export async function getMyToolsOps(campaignId = "", limit = 200): Promise<{ ops: TolexOp[] }> {
    try {
        const p = new URLSearchParams();
        if (campaignId) p.set("campaign_id", campaignId);
        p.set("limit", String(limit));
        const res = await fetch(`${BASE}/tolex/ops?${p.toString()}`, { headers: authHeaders() });
        await handle401(res);
        if (!res.ok) return { ops: [] };
        return res.json();
    } catch {
        return { ops: [] };
    }
}

export const TolexApiTenant = { getCatalog: getMyToolsCatalog, getGrants: getMyToolsGrants, saveGrants: saveMyToolsGrants, enableRecommended: enableRecommendedMyTools, getOps: getMyToolsOps };

export type TolexApi = typeof TolexApiAdmin;

// ════════════════════════════════════════════════════════════════════════════
// FAMIT RESEARCH — instrumented conversation science. Mirrors the backend wire contract
// (voice_ops/research/schema.py + droplet_work/research_query.py). Every value carries a
// `confidence` / `source` so the UI can badge provenance honestly; arousal/friction each carry a
// variance so the chart draws an uncertainty band. `demo:true` ⇒ the dataset is the real affect
// filter over scripted archetype calls (labelled in-product), not a live tenant's numbers.
// ════════════════════════════════════════════════════════════════════════════
export type ResearchSource = "asr_metadata" | "acoustic_pyin" | "egemaps" | "demo" | string;
export type ResearchRegime =
    | "steady" | "warming" | "rising_friction" | "disengaging" | "resolving" | string;

export type ResearchTurn = {
    turn_num: number;
    t_sec: number;
    ts_iso?: string;
    speaker?: string;
    // prosody (the shippable 8 kHz-telephony set)
    f0_mean_hz: number;
    f0_range_hz: number;
    f0_slope_hz_s: number;
    f0_var_hz: number;
    loudness_db: number;
    speech_rate_sps: number;
    pause_ratio: number;
    turn_latency_ms: number;
    voiced_sec: number;
    // latent affect (online multimodal Kalman) — index 0..100, 50 = caller baseline; *_var = variance
    arousal: number;
    arousal_var: number;
    friction: number;
    friction_var: number;
    engagement: number;           // conversational engagement/entrainment axis
    engagement_var: number;
    valence_hint: number;
    // multimodal channels (Upgrades #1-#3) + predictive (Phase 2)
    llm_valence?: number | null;
    intent?: string;              // LLM/heuristic stance (interested|objecting|price-resistant|...)
    objection?: number | null;
    buying_intent?: number | null;
    talk_share?: number | null;
    backchannel_rate?: number | null;
    entrainment?: number | null;
    ssl_arousal?: number | null;  // live learned-SER arousal estimate (0..1) when the tap is on
    conversion_risk?: number | null; // 0..100 cumulative through this turn
    intervene?: boolean;          // conformal "intervene now" flag
    // honesty metadata
    confidence: number;
    source: ResearchSource;
    regime: ResearchRegime;
    low_conf: boolean;
    transcript?: string;
    // optional clinical extras — never headline (telephone-band unreliable)
    jitter_local?: number | null;
    shimmer_local?: number | null;
    hnr_db?: number | null;
};

export type ResearchCallSummary = {
    call_id: string;
    tenant_id?: string;
    ts?: string;
    turns: number;
    duration_s: number;
    arousal_mean: number;
    arousal_peak: number;
    friction_mean: number;
    friction_peak: number;
    arousal_trend: number;
    friction_trend: number;
    engagement_mean?: number;
    engagement_peak?: number;
    engagement_trend?: number;
    conversion_risk?: number;     // final calibrated conversion-risk 0..100
    intervene?: boolean | number; // the call crossed the conformal intervene trigger
    top_intent?: string;
    f0_mean_hz: number;
    speech_rate_sps: number;
    pause_ratio: number;
    confidence: number;
    source: ResearchSource;
    regimes: string[] | string;
    outcome: string;
    converted: boolean | number;
    has_outcome?: boolean | number;
    deal_value: number;
};

export type ResearchOutcomeArm = {
    n: number;
    avg_friction_peak: number;
    avg_arousal_trend: number;
    avg_friction_trend: number;
};

export type ResearchDashboard = {
    demo: boolean;
    enabled?: boolean;
    range: { minutes: number };
    summary: {
        calls: number;
        resolved?: number; // calls with a known outcome (has_outcome=1)
        unknown_outcome?: number; // calls not yet resolved
        turns: number;
        avg_arousal: number;
        avg_friction: number;
        peak_friction: number;
        avg_engagement?: number;
        avg_conversion_risk?: number;
        intervened?: number;     // calls that crossed the intervene trigger
        avg_speech_rate: number;
        confidence: number;
        converted: number;
        conversion_rate: number; // over RESOLVED calls only
    };
    outcomes: { won: ResearchOutcomeArm; lost: ResearchOutcomeArm };
    regime_counts: Record<string, number>;
    calls: ResearchCallSummary[];
    error?: string;
};

export type ResearchCallDetail = {
    demo: boolean;
    call: ResearchCallSummary;
    turns: ResearchTurn[];
    error?: string;
};

export async function getResearchDashboard(minutes = 1440): Promise<ResearchDashboard> {
    const res = await fetch(`${BASE}/research/dashboard?minutes=${minutes}`, { headers: authHeaders() });
    await handle401(res);
    if (!res.ok) throw new Error(`research dashboard ${res.status}`);
    return res.json();
}

export async function getResearchCall(callId: string): Promise<ResearchCallDetail> {
    const res = await fetch(`${BASE}/research/call/${encodeURIComponent(callId)}`, { headers: authHeaders() });
    await handle401(res);
    if (!res.ok) throw new Error(`research call ${res.status}`);
    return res.json();
}

// ════════════════════════════════════════════════════════════════════════════
// HAPTICA FLYWHEEL — the read/approve seam over the backend RLHF/RLAIF
// self-improvement engine (prefix /flywheel). Mirrors getResearchDashboard's
// shape EXACTLY: GETs use authHeaders(), a 404 (FLYWHEEL_ENABLED=0 / older box)
// resolves to a clean empty shape so the console never throws when dormant, and
// real non-ok statuses throw after handle401. POSTs are FormData (super-admin
// only). Every value carries provenance/confidence so the UI badges honestly.
// Backend dataclasses: voice_ops/flywheel/* (judge / bandit / preferences /
// optimizer / monitors / labels). HUMAN-gated promotion — challengers are
// proposed, never auto-applied without an explicit approve.
// ════════════════════════════════════════════════════════════════════════════

export type FlywheelHealth = {
    enabled: boolean;
    store_configured: boolean;
    read_configured: boolean;
    judge_enabled: boolean;
    judge_model: string;
    judge_sample_rate: number;
    bandit_enabled: boolean;
    bandit_epsilon: number;
    optimizer_enabled: boolean;
    auto_promote: boolean;
    rubric_version: string;
    holdout_pct: number;
    worker_interval_s: number;
    active: boolean;
};

export type FlywheelCoverageCell = {
    objection_type: string;
    lead_temperature: string;
    n: number;
};

export type FlywheelDashboard = {
    enabled?: boolean;
    error?: string;
    trajectory: {
        turns: number;
        calls: number;
        avg_reward: number;
        confidence: number;
        low_conf_turns: number;
        judged_turns: number;
    };
    preferences: {
        pairs: number;
        outcome_anchored: number;
        survived_swap: number;
        pair_conf: number;
    };
    coverage_grid: FlywheelCoverageCell[];
};

// A learned "move" — does this play (in this regime / objection / temperature
// bucket) lift the booking rate vs the baseline? lift is the hero signal; the
// CI [ci_low, ci_high] keeps it honest at low n_samples.
export type FlywheelMove = {
    move_type: string;
    objection_type: string;
    regime: string;
    lead_temperature: string;
    book_rate: number;
    baseline_rate: number;
    lift: number;
    n_samples: number;
    ci_low: number;
    ci_high: number;
};

// One contextual-bandit arm (Thompson sampling: alpha/beta Beta posterior).
// guardrail_* are the safety rails that must hold for an arm to keep playing.
export type FlywheelArm = {
    campaign_id: string;
    vertical: string;
    knob: string;
    arm_id: string;
    context_bucket: string;
    alpha: number;
    beta: number;
    plays: number;
    reward_sum: number;
    discounted: number;
    guardrail_optout_rate: number;
    guardrail_cost_per_booking: number;
    ts: string;
    mean: number;
};

// A preference pair = the Moat. chosen vs rejected text the engine learned from,
// with the margin, where it came from (source), and honesty badges (survived a
// swap test, compliant, outcome-anchored vs judge-only).
export type FlywheelPair = {
    pair_id: string;
    ts: string;
    objection_type: string;
    lead_temperature: string;
    regime: string;
    vertical: string;
    chosen_text: string;
    rejected_text: string;
    margin: number;
    source: string;
    survived_swap: boolean;
    confidence: number;
    compliant: boolean;
    outcome_anchored: boolean;
    campaign_id: string;
};

// A proposed config change (new prompt/knob/policy). Promotion is HUMAN-gated:
// gates_passed + shadow_ok + the OPE (SNIPS) value are decision aids, never an
// auto-apply. status moves proposed → approved/rejected by a super-admin.
export type FlywheelChallenger = {
    challenger_id: string;
    ts: string;
    kind: string;
    campaign_id: string;
    proposed_config_json: string;
    rationale: string;
    ope_snips_value: number;
    gates_passed: boolean;
    replay_delta: number;
    shadow_ok: boolean;
    status: string;
    approved_by: string;
    reward_lift: number;
    ttft_ms: number;
    cost_per_appointment: number;
    // POWER-UP tier (additive, all optional — older boxes omit them). The backend
    // Challenger now carries the sequential confidence-sequence verdict (anytime-valid
    // significance + the reward CS lower bound), the OPE confidence interval, the
    // world-model sim pre-eval lift, and an is_shadow flag (shadow-only, never live Riya).
    seq_significant?: boolean;
    reward_cs_lower?: number;
    ope_cs_lower?: number;
    ope_cs_upper?: number;
    sim_reward_lift?: number;
    is_shadow?: boolean;
};

// A human calibration label on a turn (good/bad) — feeds the judge calibration.
export type FlywheelLabel = {
    call_id: string;
    turn_num: number;
    ts: string;
    trigger: string;
    label: string;
    labeler: string;
    rationale: string;
    used_for_calibration: boolean;
};

// A Goodhart canary: a tracked metric vs its threshold. threshold_breached=true
// means the optimizer may be gaming a proxy — the UI makes this visually loud.
export type FlywheelMonitor = {
    metric: string;
    ts: string;
    value: number;
    arm_id: string;
    threshold_breached: boolean;
};

// One turn of a credited trajectory (the per-turn reward decomposition the
// engine learns from): the move, the latent state, the chosen arm, propensity,
// and the reward (raw → capped) with confidence + low-conf honesty flag.
export type FlywheelTurn = {
    turn_num: number;
    ts: string;
    move_type: string;
    objection_type: string;
    state_friction: number;
    state_arousal: number;
    state_regime: string;
    arm_model: string;
    arm_voice: string;
    arm_variant: string;
    propensity: number;
    affect_delta: number;
    judge_score: number;
    credit_advantage: number;
    reward_raw: number;
    reward_capped: number;
    confidence: number;
    low_conf: boolean;
    agent_text: string;
    caller_text: string;
};

// Empty shapes returned on 404 (dormant) so the console renders a friendly
// "enable FLYWHEEL_ENABLED" card instead of throwing.
const EMPTY_FLYWHEEL_DASHBOARD: FlywheelDashboard = {
    enabled: false,
    trajectory: { turns: 0, calls: 0, avg_reward: 0, confidence: 0, low_conf_turns: 0, judged_turns: 0 },
    preferences: { pairs: 0, outcome_anchored: 0, survived_swap: 0, pair_conf: 0 },
    coverage_grid: [],
};

const EMPTY_FLYWHEEL_HEALTH: FlywheelHealth = {
    enabled: false,
    store_configured: false,
    read_configured: false,
    judge_enabled: false,
    judge_model: "",
    judge_sample_rate: 0,
    bandit_enabled: false,
    bandit_epsilon: 0,
    optimizer_enabled: false,
    auto_promote: false,
    rubric_version: "",
    holdout_pct: 0,
    worker_interval_s: 0,
    active: false,
};

export async function getFlywheelHealth(): Promise<FlywheelHealth> {
    const res = await fetch(`${BASE}/flywheel/health`, { headers: authHeaders() });
    await handle401(res);
    if (res.status === 404) return { ...EMPTY_FLYWHEEL_HEALTH };
    if (!res.ok) throw new Error(`flywheel health ${res.status}`);
    return res.json();
}

export async function getFlywheelDashboard(minutes = 43200): Promise<FlywheelDashboard> {
    const res = await fetch(`${BASE}/flywheel/dashboard?minutes=${minutes}`, { headers: authHeaders() });
    await handle401(res);
    if (res.status === 404) return { ...EMPTY_FLYWHEEL_DASHBOARD };
    if (!res.ok) throw new Error(`flywheel dashboard ${res.status}`);
    return res.json();
}

export async function getFlywheelMoves(vertical = ""): Promise<{ moves: FlywheelMove[]; error?: string }> {
    const qs = vertical ? `?vertical=${encodeURIComponent(vertical)}` : "";
    const res = await fetch(`${BASE}/flywheel/moves${qs}`, { headers: authHeaders() });
    await handle401(res);
    if (res.status === 404) return { moves: [] };
    if (!res.ok) throw new Error(`flywheel moves ${res.status}`);
    return res.json();
}

export async function getFlywheelBandit(campaignId = ""): Promise<{ arms: FlywheelArm[]; error?: string }> {
    const qs = campaignId ? `?campaign_id=${encodeURIComponent(campaignId)}` : "";
    const res = await fetch(`${BASE}/flywheel/bandit${qs}`, { headers: authHeaders() });
    await handle401(res);
    if (res.status === 404) return { arms: [] };
    if (!res.ok) throw new Error(`flywheel bandit ${res.status}`);
    return res.json();
}

export async function getFlywheelPreferences(
    objection = "",
    temp = "",
    limit = 100,
): Promise<{ pairs: FlywheelPair[]; error?: string }> {
    const q = new URLSearchParams();
    if (objection) q.set("objection", objection);
    if (temp) q.set("temp", temp);
    q.set("limit", String(limit));
    const res = await fetch(`${BASE}/flywheel/preferences?${q.toString()}`, { headers: authHeaders() });
    await handle401(res);
    if (res.status === 404) return { pairs: [] };
    if (!res.ok) throw new Error(`flywheel preferences ${res.status}`);
    return res.json();
}

export async function getFlywheelChallengers(status = ""): Promise<{ challengers: FlywheelChallenger[]; error?: string }> {
    const qs = status ? `?status=${encodeURIComponent(status)}` : "";
    const res = await fetch(`${BASE}/flywheel/challengers${qs}`, { headers: authHeaders() });
    await handle401(res);
    if (res.status === 404) return { challengers: [] };
    if (!res.ok) throw new Error(`flywheel challengers ${res.status}`);
    return res.json();
}

export async function getFlywheelLabels(): Promise<{ labels: FlywheelLabel[]; error?: string }> {
    const res = await fetch(`${BASE}/flywheel/labels`, { headers: authHeaders() });
    await handle401(res);
    if (res.status === 404) return { labels: [] };
    if (!res.ok) throw new Error(`flywheel labels ${res.status}`);
    return res.json();
}

export async function getFlywheelMonitors(minutes = 43200): Promise<{ monitors: FlywheelMonitor[]; error?: string }> {
    const res = await fetch(`${BASE}/flywheel/monitors?minutes=${minutes}`, { headers: authHeaders() });
    await handle401(res);
    if (res.status === 404) return { monitors: [] };
    if (!res.ok) throw new Error(`flywheel monitors ${res.status}`);
    return res.json();
}

export async function getFlywheelTrajectory(
    callId: string,
): Promise<{ call_id: string; turns: FlywheelTurn[]; error?: string }> {
    const res = await fetch(`${BASE}/flywheel/trajectory/${encodeURIComponent(callId)}`, { headers: authHeaders() });
    await handle401(res);
    if (res.status === 404) return { call_id: callId, turns: [] };
    if (!res.ok) throw new Error(`flywheel trajectory ${res.status}`);
    return res.json();
}

// ── HUMAN-gated promotion + calibration writes (FormData, super-admin only) ──
export async function approveFlywheelChallenger(
    id: string,
): Promise<{ ok: boolean; challenger_id: string; config?: unknown }> {
    const res = await fetch(`${BASE}/flywheel/challengers/${encodeURIComponent(id)}/approve`, {
        method: "POST",
        headers: authHeaders(),
        body: new FormData(),
    });
    await handle401(res);
    if (!res.ok) throw new Error(`flywheel approve ${res.status}`);
    return res.json();
}

export async function rejectFlywheelChallenger(
    id: string,
    reason: string,
): Promise<{ ok: boolean; challenger_id: string }> {
    const fd = new FormData();
    fd.append("reason", reason);
    const res = await fetch(`${BASE}/flywheel/challengers/${encodeURIComponent(id)}/reject`, {
        method: "POST",
        headers: authHeaders(),
        body: fd,
    });
    await handle401(res);
    if (!res.ok) throw new Error(`flywheel reject ${res.status}`);
    return res.json();
}

export async function submitFlywheelLabel(
    callId: string,
    turn: number,
    label: string,
    rationale: string,
): Promise<{ ok: boolean }> {
    const fd = new FormData();
    fd.append("label", label);
    fd.append("rationale", rationale);
    const res = await fetch(
        `${BASE}/flywheel/labels/${encodeURIComponent(callId)}/${encodeURIComponent(String(turn))}`,
        { method: "POST", headers: authHeaders(), body: fd },
    );
    await handle401(res);
    if (!res.ok) throw new Error(`flywheel label ${res.status}`);
    return res.json();
}

// ════════════════════════════════════════════════════════════════════════════
// HAPTICA FLYWHEEL — POWER-UP TIER. The next layer over the same /flywheel seam:
// CAUSAL effects (CATE, not correlation), the learned reward/value CRITIC, the
// contextual POLICY (+ OPE 3-leg) & rebuttal PLAY library, the caller WORLD MODEL
// (archetypes + filter-only sim rollouts), SEQUENTIAL confidence-sequences, and
// self-hosted shadow DISTILL runs. SAME contract as the base block: GET +
// authHeaders(), a 404 (FLYWHEEL_ENABLED=0 / older box / route not mounted)
// resolves to a clean empty shape so the console never error-walls when dormant,
// real non-ok statuses throw after handle401. Everything human-gated / shadow-only.
// ════════════════════════════════════════════════════════════════════════════

// A CAUSAL effect estimate — the CATE (conditional average treatment effect) of a
// move in a cell, i.e. how much this play actually CAUSES bookings (vs the merely
// correlational raw_lift). Promote only when the CI lower bound (cate_lower) > 0.
// overlap_min < 0.02 = an untrustworthy cell (no positivity); sign_agree = the
// causal sign matches the correlational sign.
export type FlywheelCATE = {
    move_type: string;
    objection_type: string;
    regime: string;
    lead_temperature: string;
    cate: number;
    cate_lower: number;
    cate_upper: number;
    raw_lift: number;
    n_treated: number;
    overlap_min: number;
    sign_agree: boolean;
};

// A learned critic model row: the V(state)=P(book) value model (+ trained reward
// potential) powering live momentum. platt_a/platt_b = the Platt calibration; auc
// + ece (expected calibration error) are the quality gates; active = currently live.
export type FlywheelCritic = {
    ts: string;
    vertical: string;
    model_type: string;
    platt_a: number;
    platt_b: number;
    auc: number;
    ece: number;
    n_rows: number;
    active: boolean;
    coef_json: string;
};

// A contextual-policy model (per campaign/knob) with the 3-leg OPE: SNIPS / FQE /
// MAGIC and the pessimistic ope_lower (the promote-only-when-lower-bound>0 floor).
export type FlywheelPolicy = {
    ts: string;
    campaign_id: string;
    vertical: string;
    knob: string;
    n_features: number;
    ope_snips: number;
    ope_fqe: number;
    ope_magic: number;
    ope_lower: number;
    active: boolean;
    arms_json: string;
};

// A rebuttal template in the play library, keyed by objection_type.
export type FlywheelPlay = {
    template_id: string;
    objection_type: string;
    text: string;
    label: string;
};

// A caller-archetype = a synthetic persona the world-model simulates against. weight
// is its coverage weight; base_book_rate is its prior; the *_json hold the objection
// histogram + affect template the simulator samples from.
export type FlywheelArchetype = {
    archetype_id: string;
    label: string;
    temperament: string;
    base_book_rate: number;
    weight: number;
    n_calls: number;
    objection_hist_json: string;
    affect_template_json: string;
};

// One simulated rollout from the FILTER-ONLY caller simulator (it proposes/removes
// challengers, never promotes). ece > 0.15 = the sim self-disabled (low fidelity).
export type FlywheelSimRollout = {
    ts: string;
    archetype_id: string;
    challenger_id: string;
    policy_label: string;
    sim_outcome: string;
    sim_reward: number;
    turns: number;
    usi: number;
    ece: number;
};

// One state of a sequential (anytime-valid) confidence sequence for a challenger's
// metric. significant=true once the CS [cs_lower, cs_upper] excludes 0.
export type FlywheelSeqState = {
    challenger_id: string;
    metric: string;
    n: number;
    running_mean: number;
    cs_lower: number;
    cs_upper: number;
    significant: boolean;
};

// A self-hosted shadow distillation run (DPO/KTO/etc). status moves
// queued→running→done/failed; adapter_uri is the trained shadow adapter. SHADOW-ONLY
// — these never touch live Riya.
export type FlywheelDistillRun = {
    ts: string;
    run_id: string;
    method: string;
    base_model: string;
    n_desirable: number;
    n_undesirable: number;
    status: string;
    adapter_uri: string;
};

export async function getFlywheelCausal(vertical = ""): Promise<{ moves: FlywheelCATE[]; error?: string }> {
    const qs = vertical ? `?vertical=${encodeURIComponent(vertical)}` : "";
    const res = await fetch(`${BASE}/flywheel/causal${qs}`, { headers: authHeaders() });
    await handle401(res);
    if (res.status === 404) return { moves: [] };
    if (!res.ok) throw new Error(`flywheel causal ${res.status}`);
    return res.json();
}

export async function getFlywheelCritic(): Promise<{ critics: FlywheelCritic[]; error?: string }> {
    const res = await fetch(`${BASE}/flywheel/critic`, { headers: authHeaders() });
    await handle401(res);
    if (res.status === 404) return { critics: [] };
    if (!res.ok) throw new Error(`flywheel critic ${res.status}`);
    return res.json();
}

export async function getFlywheelPolicy(campaignId = ""): Promise<{ policies: FlywheelPolicy[]; error?: string }> {
    const qs = campaignId ? `?campaign_id=${encodeURIComponent(campaignId)}` : "";
    const res = await fetch(`${BASE}/flywheel/policy${qs}`, { headers: authHeaders() });
    await handle401(res);
    if (res.status === 404) return { policies: [] };
    if (!res.ok) throw new Error(`flywheel policy ${res.status}`);
    return res.json();
}

export async function getFlywheelPlayLibrary(objection = ""): Promise<{ templates: FlywheelPlay[]; error?: string }> {
    const qs = objection ? `?objection=${encodeURIComponent(objection)}` : "";
    const res = await fetch(`${BASE}/flywheel/play-library${qs}`, { headers: authHeaders() });
    await handle401(res);
    if (res.status === 404) return { templates: [] };
    if (!res.ok) throw new Error(`flywheel play-library ${res.status}`);
    return res.json();
}

export async function getFlywheelArchetypes(): Promise<{ archetypes: FlywheelArchetype[]; error?: string }> {
    const res = await fetch(`${BASE}/flywheel/archetypes`, { headers: authHeaders() });
    await handle401(res);
    if (res.status === 404) return { archetypes: [] };
    if (!res.ok) throw new Error(`flywheel archetypes ${res.status}`);
    return res.json();
}

export async function getFlywheelSimRollouts(minutes = 43200): Promise<{ rollouts: FlywheelSimRollout[]; error?: string }> {
    const res = await fetch(`${BASE}/flywheel/sim-rollouts?minutes=${minutes}`, { headers: authHeaders() });
    await handle401(res);
    if (res.status === 404) return { rollouts: [] };
    if (!res.ok) throw new Error(`flywheel sim-rollouts ${res.status}`);
    return res.json();
}

export async function getFlywheelSequential(challengerId = ""): Promise<{ states: FlywheelSeqState[]; error?: string }> {
    const qs = challengerId ? `?challenger_id=${encodeURIComponent(challengerId)}` : "";
    const res = await fetch(`${BASE}/flywheel/sequential${qs}`, { headers: authHeaders() });
    await handle401(res);
    if (res.status === 404) return { states: [] };
    if (!res.ok) throw new Error(`flywheel sequential ${res.status}`);
    return res.json();
}

export async function getFlywheelDistill(): Promise<{ runs: FlywheelDistillRun[]; error?: string }> {
    const res = await fetch(`${BASE}/flywheel/distill`, { headers: authHeaders() });
    await handle401(res);
    if (res.status === 404) return { runs: [] };
    if (!res.ok) throw new Error(`flywheel distill ${res.status}`);
    return res.json();
}
