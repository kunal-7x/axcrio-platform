// Colocated CRM-core API client.
//
// WHY here and not lib/api.ts: the build task scopes edits to this page's own
// files under app/crm. lib/api.ts is the shared client and is off-limits, and
// its auth helpers (getToken/authHeaders/handle401) are module-private — so we
// replicate the small auth preamble here and import only the public TYPES we
// reuse (Lead, CallLog shapes are not needed; CRM has its own contract).
//
// Contract = design/platform-crm-core.md §7 (byte-exact field names so the page
// lights up the moment the orchestrator MOUNTS the crm router). The crm router
// is currently DEFINED-NOT-MOUNTED on the live API, so every /contacts* call
// returns 404 today. We translate that (and 501 / network failure) into a
// CrmDormantError sentinel the UI renders as a premium "not configured" state,
// while a genuine 401 still bounces to /login exactly like lib/api.ts does.

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

// Raised when the crm-core backend is not reachable as a *feature* (module down
// / PG down / route not mounted / unreachable). Distinct from a hard error so
// the page can show a graceful "coming soon" instead of an error toast.
export class CrmDormantError extends Error {
    status: number;
    constructor(status: number, message = "CRM module is not configured yet") {
        super(message);
        this.name = "CrmDormantError";
        this.status = status;
    }
}

// Raised on a genuine 404 (the crm routes ARE mounted in caller.py, so a 404 on
// a detail/timeline/nba call means "this contact doesn't exist", NOT dormant).
export class CrmNotFoundError extends Error {
    constructor(message = "Contact not found") {
        super(message);
        this.name = "CrmNotFoundError";
    }
}

// Central fetch wrapper: 401 -> logout+redirect (matches lib/api.ts handle401);
// 404 -> not-found; 501/503/network -> dormant; other non-OK -> generic Error.
async function crmFetch<T>(path: string): Promise<T> {
    let res: Response;
    try {
        res = await fetch(`${BASE}${path}`, { headers: authHeaders() });
    } catch {
        // Network / CORS / offline — treat as dormant so the UI degrades calmly.
        throw new CrmDormantError(0, "CRM module is unreachable");
    }
    if (res.status === 401 && typeof window !== "undefined") {
        localStorage.removeItem("famit_token");
        localStorage.removeItem("famit_me");
        window.location.href = "/login";
        throw new Error("Unauthorized");
    }
    // 404 = genuine not-found (routes are mounted). 501/503 = module/PG degraded.
    if (res.status === 404) {
        throw new CrmNotFoundError();
    }
    if (res.status === 501 || res.status === 503) {
        throw new CrmDormantError(res.status);
    }
    if (!res.ok) {
        let body: Record<string, unknown> = {};
        try {
            body = await res.json();
        } catch {
            /* non-JSON */
        }
        const err = typeof body.error === "string" ? body.error : "";
        throw new Error(err || `Request failed (${res.status})`);
    }
    return res.json() as Promise<T>;
}

// ── Types (mirror design/platform-crm-core.md §3 + §7 exactly) ──────────────

// Lifecycle stage (§3.1 / §4.1 derivation). Order roughly = funnel progression.
export type ContactStage =
    | "new"
    | "contacted"
    | "engaged"
    | "qualified"
    | "booked"
    | "won"
    | "lost"
    | "dormant"
    | "opted_out";

// List-row shape from GET /contacts.
export type ContactListItem = {
    id: string;
    phone_display: string;
    name: string;
    stage: string;
    score: number;
    hot: boolean;
    last_outcome: string;
    last_activity_at: string | null;
};

export type ContactsResponse = {
    contacts: ContactListItem[];
    total: number;
    // The live API returns 200 with a `note` (not a 404) when the crm module or
    // its Postgres is unavailable — the UI treats these as "dormant", same as a
    // 404 on a not-yet-mounted route. See DORMANT_NOTES.
    note?: string;
    error?: string;
};

// `note`/`error` values the backend emits when the read-model can't serve real
// data — surfaced as the graceful "coming soon / preparing" state, not an
// empty table or an error toast.
export const DORMANT_NOTES = new Set([
    "crm module unavailable",
    "pg_unavailable",
]);

export function isDormantResponse(r: { note?: string; error?: string }): boolean {
    return !!(r.note && DORMANT_NOTES.has(r.note)) || !!r.error;
}

// Full contact (§3.1). Reads tolerate missing optional fields.
export type ContactFull = {
    id: string;
    org_id?: string;
    phone_key?: string;
    phone_display: string;
    name: string;
    email?: string;
    stage: string;
    score: number;
    hot: boolean;
    last_outcome: string;
    last_activity_at: string | null;
    lifecycle_state?: string;
    consent_call?: boolean;
    consent_wa?: boolean;
    created_at?: string;
    updated_at?: string;
    data?: Record<string, unknown>;
};

// The authoritative lead row joined alongside the contact (§7 GET /contacts/{id}).
export type ContactLead = {
    id?: string;
    name?: string;
    phone?: string;
    status?: string;
    score?: number;
    hot?: boolean;
    last_outcome?: string;
    last_call_at?: string;
    added_at?: string;
    [k: string]: unknown;
};

// Next-Best-Action (§4.3). Rule-based; requires_pin gates risky/spend actions.
export type Nba = {
    action: string;
    reason: string;
    confidence?: number;
    params?: Record<string, unknown>;
    requires_pin: boolean;
};

// As-built (caller.py GET /contacts/{phone}) returns {contact, timeline, nba}.
// Lead truth is PROJECTED INTO `contact` (stage/score/hot/last_outcome) by
// project_contact — there is NO separate top-level `lead` key on the live API,
// so the profile reads lead-ish fields off `contact`. `lead` is kept optional
// for forward-compat in case a future build adds it back. `timeline` is the
// embedded first-page (newest-first) the detail endpoint already includes.
export type ContactDetailResponse = {
    contact: ContactFull;
    timeline?: TimelineRow[];
    lead?: ContactLead | null;
    nba: Nba;
};

// Unified timeline row (§3.3 / §7).
export type TimelineKind =
    | "call"
    | "whatsapp"
    | "support"
    | "booking"
    | "purchase"
    | "note"
    | "consent"
    | "campaign"
    | "system";

export type TimelineRow = {
    kind: string;
    direction: string; // inbound | outbound | ""
    title: string;
    body: string;
    outcome: string;
    amount?: number | null;
    currency?: string;
    at: string;
    source?: string;
    source_id?: string;
};

export type TimelineResponse = {
    timeline: TimelineRow[];
    contact_id: string;
};

// Saved segment (§3.4) — used only to populate the workspace segment filter.
export type Segment = {
    id: string;
    name: string;
    member_count?: number;
    active?: boolean;
};

export type SegmentsResponse = {
    segments: Segment[];
};

// ── Calls (all colocated, contract-faithful) ─────────────────────────────────

export type ContactsQuery = {
    stage?: string;
    hot?: boolean;
    segment?: string;
    q?: string;
    sort?: string;
    limit?: number;
};

export async function getContacts(opts?: ContactsQuery): Promise<ContactsResponse> {
    const params = new URLSearchParams();
    if (opts?.stage) params.set("stage", opts.stage);
    if (opts?.hot) params.set("hot", "1");
    if (opts?.segment) params.set("segment", opts.segment);
    if (opts?.q) params.set("q", opts.q);
    if (opts?.sort) params.set("sort", opts.sort);
    if (opts?.limit != null) params.set("limit", String(opts.limit));
    const qs = params.toString();
    return crmFetch<ContactsResponse>(`/contacts${qs ? `?${qs}` : ""}`);
}

export async function getContact(id: string): Promise<ContactDetailResponse> {
    return crmFetch<ContactDetailResponse>(`/contacts/${encodeURIComponent(id)}`);
}

export async function getContactTimeline(
    id: string,
    opts?: { kinds?: string; limit?: number }
): Promise<TimelineResponse> {
    const params = new URLSearchParams();
    if (opts?.kinds) params.set("kinds", opts.kinds);
    if (opts?.limit != null) params.set("limit", String(opts.limit));
    const qs = params.toString();
    return crmFetch<TimelineResponse>(
        `/contacts/${encodeURIComponent(id)}/timeline${qs ? `?${qs}` : ""}`
    );
}

export async function getContactNba(id: string): Promise<Nba> {
    return crmFetch<Nba>(`/contacts/${encodeURIComponent(id)}/nba`);
}

// ── Recordings (Part 2 unit D — call audio for one lead) ─────────────────────
//
// GET /contacts/{phone}/recordings unifies INBOUND (ai_manager_sessions) +
// OUTBOUND (calls) audio for the lead, each with a freshly-minted PRESIGNED,
// range-streamable + downloadable URL (1h TTL) and metadata. Tenant-scoped (RLS,
// tenant from token) exactly like /contacts. The bucket is PRIVATE, so the URL is
// minted per-read; a row with no playable URL yet (still uploading / finalize
// pending) surfaces a calm "preparing" state rather than a broken player.

export type Recording = {
    call_id: string;
    direction: string; // inbound | outbound | ""
    phone: string;
    started_at: string | null;
    duration_s?: number | null;
    status: string; // uploaded | recording | pending | failed | ""
    // freshly-minted presigned URL (preferred). `recording_url` is a legacy/static
    // fallback if a build ever persisted one.
    url?: string;
    presigned_url?: string;
    recording_url?: string;
};

export type RecordingsResponse = {
    recordings: Recording[];
    // dormant/degraded markers, mirroring ContactsResponse.
    note?: string;
    error?: string;
};

// Never throws — a dormant module / not-yet-mounted route / network error all
// resolve to an empty list so the profile renders a calm empty state, never an
// error wall. A genuine 401 still bounces to /login.
export async function getContactRecordings(phone: string): Promise<RecordingsResponse> {
    let res: Response;
    try {
        res = await fetch(`${BASE}/contacts/${encodeURIComponent(phone)}/recordings`, {
            headers: authHeaders(),
        });
    } catch {
        return { recordings: [] }; // offline / route absent -> calm empty
    }
    if (res.status === 401 && typeof window !== "undefined") {
        localStorage.removeItem("famit_token");
        localStorage.removeItem("famit_me");
        window.location.href = "/login";
        return { recordings: [] };
    }
    if (!res.ok) return { recordings: [] }; // 404 / 501 / 5xx -> dormant-safe empty
    const data = (await res.json().catch(() => ({}))) as Record<string, unknown>;
    const raw: unknown = Array.isArray(data)
        ? data
        : Array.isArray((data as { recordings?: unknown }).recordings)
        ? (data as { recordings: unknown[] }).recordings
        : [];
    const recordings = (raw as Record<string, unknown>[])
        .map(toRecording)
        // newest first (matches the timeline feed); rows with no timestamp sink last.
        .sort((a, b) => (b.started_at || "").localeCompare(a.started_at || ""));
    return { recordings, note: typeof data.note === "string" ? data.note : undefined };
}

// Normalize one backend row, tolerant of field-name drift so a partial payload
// never crashes the section.
function toRecording(r: Record<string, unknown>, idx: number): Recording {
    const dur = Number(r.duration_s);
    const firstUrl = (...keys: string[]): string | undefined => {
        for (const k of keys) {
            const v = r[k];
            if (typeof v === "string" && v.trim()) return v;
        }
        return undefined;
    };
    return {
        call_id: String(r.call_id ?? r.id ?? r.room ?? `rec-${idx}`),
        direction: String(r.direction ?? "").trim(),
        phone: String(r.phone ?? "").trim(),
        started_at: r.started_at ? String(r.started_at) : r.created_at ? String(r.created_at) : null,
        duration_s: Number.isFinite(dur) && dur > 0 ? dur : null,
        status: String(r.status ?? "").trim().toLowerCase(),
        url: firstUrl("url", "presigned_url", "recording_presigned_url", "recording_url"),
    };
}

export async function getSegments(): Promise<SegmentsResponse> {
    return crmFetch<SegmentsResponse>(`/segments`);
}
