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
    | "opted_out";

// List-row shape from GET /contacts.
// `lifecycle`/`lifecycle_state` + `campaign` are OPTIONAL/back-compat: the list
// endpoint may not project them yet, so the UI derives temperature client-side
// (see _ui.tsx tempOf) and falls back to "—" for campaign when absent.
export type ContactListItem = {
    id: string;
    phone_display: string;
    name: string;
    stage: string;
    score: number;
    hot: boolean;
    last_outcome: string;
    last_activity_at: string | null;
    lifecycle?: string | null;
    lifecycle_state?: string | null;
    campaign?: string | null;
    campaign_name?: string | null;
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
    lifecycle?: string;
    segment?: string;
    q?: string;
    sort?: string;
    limit?: number;
};

export async function getContacts(opts?: ContactsQuery): Promise<ContactsResponse> {
    const params = new URLSearchParams();
    if (opts?.stage) params.set("stage", opts.stage);
    if (opts?.hot) params.set("hot", "1");
    if (opts?.lifecycle) params.set("lifecycle", opts.lifecycle);
    if (opts?.segment) params.set("segment", opts.segment);
    if (opts?.q) params.set("q", opts.q);
    if (opts?.sort) params.set("sort", opts.sort);
    if (opts?.limit != null) params.set("limit", String(opts.limit));
    const qs = params.toString();
    return crmFetch<ContactsResponse>(`/contacts${qs ? `?${qs}` : ""}`);
}

// DELETE /contacts/{id} — role-gated; the caller must hold the right role.
// Never throws a dormant-style error — a missing route / 404 on an id that
// doesn't exist both resolve to a plain Error so the caller can surface a toast.
export async function deleteContact(id: string): Promise<void> {
    let res: Response;
    try {
        res = await fetch(`${BASE}/contacts/${encodeURIComponent(id)}`, {
            method: "DELETE",
            headers: authHeaders(),
        });
    } catch {
        throw new Error("Network error — could not delete contact");
    }
    if (res.status === 401 && typeof window !== "undefined") {
        localStorage.removeItem("famit_token");
        localStorage.removeItem("famit_me");
        window.location.href = "/login";
        throw new Error("Unauthorized");
    }
    if (!res.ok) {
        let body: Record<string, unknown> = {};
        try { body = await res.json(); } catch { /* non-JSON */ }
        const msg = typeof body.error === "string" ? body.error : "";
        throw new Error(msg || `Delete failed (${res.status})`);
    }
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

// ── Relationship memory (VOICE-BRAIN W4) ────────────────────────────────────
// The durable, cross-channel lead_memory profile + lead_episodes history, served
// by GET /leads/{phone}/memory and /leads/{phone}/episodes (tenant-scoped, RLS).
// Both endpoints are DORMANT-SAFE on the backend (LEAD_MEMORY_PG flag off / no
// rows => memory:null / episodes:[]); the client mirrors that — it NEVER throws,
// resolving every degraded state (route absent, PG down, network) to the empty
// shape so the panel renders a calm "no memory yet" state instead of an error.

// The lead_memory profile row (durable cross-channel relationship facts).
export type LeadMemory = {
    profile: Record<string, unknown>;
    durable_facts: Record<string, unknown>;
    preferences: Record<string, unknown>;
    last_outcome: Record<string, unknown>;
    next_best_action: Record<string, unknown>;
    episode_count: number;
    version: number;
    last_channel: string;
    last_seen_at: string;
    updated_at: string;
};

export type LeadMemoryResponse = {
    phone: string;
    memory: LeadMemory | null;
};

// One lead_episodes row (a single call or WhatsApp conversation, summarised).
export type LeadEpisode = {
    id: number;
    channel: string; // 'call' | 'whatsapp'
    summary: string;
    objections: string[];
    sentiment: string; // positive | neutral | negative | mixed
    outcome: string; // booked | interested | callback | not_interested | …
    transcript_ref: string;
    meta: Record<string, unknown>;
    created_at: string;
};

export type LeadEpisodesResponse = {
    phone: string;
    episodes: LeadEpisode[];
    total: number;
    offset: number;
    limit: number;
    next: number | null;
};

// Never throws: any degraded state -> {memory:null}. A genuine 401 still logs out.
export async function getLeadMemory(phone: string): Promise<LeadMemoryResponse> {
    const empty: LeadMemoryResponse = { phone, memory: null };
    let res: Response;
    try {
        res = await fetch(`${BASE}/leads/${encodeURIComponent(phone)}/memory`, {
            headers: authHeaders(),
        });
    } catch {
        return empty; // offline / route absent
    }
    if (res.status === 401 && typeof window !== "undefined") {
        localStorage.removeItem("famit_token");
        localStorage.removeItem("famit_me");
        window.location.href = "/login";
        return empty;
    }
    if (!res.ok) return empty; // 404 / 501 / 5xx -> dormant-safe
    const data = (await res.json().catch(() => ({}))) as Partial<LeadMemoryResponse>;
    return {
        phone: typeof data.phone === "string" ? data.phone : phone,
        memory: (data.memory as LeadMemory | null) ?? null,
    };
}

// Never throws: any degraded state -> {episodes:[]}. Newest-first, paginated.
export async function getLeadEpisodes(
    phone: string,
    opts?: { limit?: number; offset?: number }
): Promise<LeadEpisodesResponse> {
    const off = Math.max(0, opts?.offset ?? 0);
    const lim = Math.min(Math.max(1, opts?.limit ?? 50), 200);
    const empty: LeadEpisodesResponse = {
        phone,
        episodes: [],
        total: 0,
        offset: off,
        limit: lim,
        next: null,
    };
    const qs = new URLSearchParams({ limit: String(lim), offset: String(off) });
    let res: Response;
    try {
        res = await fetch(
            `${BASE}/leads/${encodeURIComponent(phone)}/episodes?${qs.toString()}`,
            { headers: authHeaders() }
        );
    } catch {
        return empty;
    }
    if (res.status === 401 && typeof window !== "undefined") {
        localStorage.removeItem("famit_token");
        localStorage.removeItem("famit_me");
        window.location.href = "/login";
        return empty;
    }
    if (!res.ok) return empty;
    const data = (await res.json().catch(() => ({}))) as Partial<LeadEpisodesResponse>;
    const rawEps = Array.isArray(data.episodes) ? data.episodes : [];
    const episodes: LeadEpisode[] = rawEps.map((e) => {
        const r = (e ?? {}) as Record<string, unknown>;
        const objs = r.objections;
        return {
            id: Number(r.id ?? 0),
            channel: String(r.channel ?? "").trim(),
            summary: String(r.summary ?? ""),
            objections: Array.isArray(objs) ? objs.map((o) => String(o)) : [],
            sentiment: String(r.sentiment ?? "").trim(),
            outcome: String(r.outcome ?? "").trim(),
            transcript_ref: String(r.transcript_ref ?? ""),
            meta: (r.meta as Record<string, unknown>) ?? {},
            created_at: String(r.created_at ?? ""),
        };
    });
    return {
        phone: typeof data.phone === "string" ? data.phone : phone,
        episodes,
        total: Number(data.total ?? episodes.length),
        offset: Number(data.offset ?? off),
        limit: Number(data.limit ?? lim),
        next: typeof data.next === "number" ? data.next : null,
    };
}

// ── Transcript (call chat-view — full ordered turns for ONE call) ────────────
//
// GET /calls/{call_id}/transcript returns the FULL ordered transcript for one
// call, UNIFIED across both directions (outbound transcripts/{room}.json +
// inbound ai_manager_sessions turns). `call_id` accepts the call id, the room,
// OR an inbound session_id — exactly the `source_id` a timeline "call" row
// carries (crm/core.py records source_id = call.id || room). The backend
// NORMALIZES each turn's role to the chat-bubble side:
//   ai | assistant | agent  -> "ai"        (rendered on the LEFT)
//   user | customer | caller -> "customer" (rendered on the RIGHT)
// Tenant-scoped from the token (outbound = BOLA-guarded 404, inbound = RLS).
// VERIFIED LIVE 2026-06-13: room famit-916375548830-ad08ff (admin tenant) → 200,
// 94 turns, direction=outbound, distinct roles = {ai, customer} only; same room
// on the founder tenant → 404 (no cross-tenant leak). The blank-image bug is GONE
// (asset-detail folded version url GETs 200 image/jpeg ~50–63KB on founder+admin).

export type TranscriptRole = "ai" | "customer";

export type TranscriptTurn = {
    role: TranscriptRole;
    text: string;
    ts: string; // ISO/string timestamp; "" for outbound (no per-turn ts)
    seq: number;
};

export type CallTranscript = {
    call_id: string;
    direction: string; // inbound | outbound | ""
    phone: string;
    name: string;
    turns: TranscriptTurn[];
    total: number;
};

// Never throws — a dormant module / not-yet-mounted route / 404 / network error
// all resolve to an empty transcript so the chat-view shows a calm "no transcript
// for this call" note rather than an error wall. A genuine 401 bounces to /login.
export async function getCallTranscript(callId: string): Promise<CallTranscript> {
    const empty: CallTranscript = {
        call_id: callId,
        direction: "",
        phone: "",
        name: "",
        turns: [],
        total: 0,
    };
    if (!callId) return empty;
    let res: Response;
    try {
        res = await fetch(`${BASE}/calls/${encodeURIComponent(callId)}/transcript`, {
            headers: authHeaders(),
        });
    } catch {
        return empty; // offline / route absent -> calm empty
    }
    if (res.status === 401 && typeof window !== "undefined") {
        localStorage.removeItem("famit_token");
        localStorage.removeItem("famit_me");
        window.location.href = "/login";
        return empty;
    }
    if (!res.ok) return empty; // 404 / 501 / 5xx -> dormant-safe empty
    const data = (await res.json().catch(() => ({}))) as Record<string, unknown>;
    const rawTurns: unknown = Array.isArray((data as { turns?: unknown }).turns)
        ? (data as { turns: unknown[] }).turns
        : [];
    const turns = (rawTurns as Record<string, unknown>[])
        .map(toTurn)
        .filter((t): t is TranscriptTurn => !!t);
    return {
        call_id: String(data.call_id ?? callId),
        direction: String(data.direction ?? "").trim(),
        phone: String(data.phone ?? "").trim(),
        name: String(data.name ?? "").trim(),
        turns,
        total: Number.isFinite(Number(data.total)) ? Number(data.total) : turns.length,
    };
}

// Normalize one stored turn, tolerant of field drift. Drops empty-text turns.
// Any non-customer role collapses to "ai" (system/tool lines sit on the agent side).
function toTurn(t: Record<string, unknown>, idx: number): TranscriptTurn | null {
    const text = String(t.text ?? t.content ?? "").trim();
    if (!text) return null;
    const r = String(t.role ?? "").trim().toLowerCase();
    const role: TranscriptRole =
        r === "customer" || r === "user" || r === "caller" || r === "human" || r === "lead"
            ? "customer"
            : "ai";
    const seq = Number(t.seq);
    return {
        role,
        text,
        ts: String(t.ts ?? t.created_at ?? ""),
        seq: Number.isFinite(seq) ? seq : idx,
    };
}

export async function getSegments(): Promise<SegmentsResponse> {
    return crmFetch<SegmentsResponse>(`/segments`);
}
