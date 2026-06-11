"use client";

// Self-contained API client for the AI Manager command-center page.
//
// WHY local (not lib/api.ts): the /ai-manager router is DEFINED-NOT-MOUNTED on
// the backend today, so every endpoint 404s until the deferred wiring + creds
// land. Rather than couple the shared api module to a dormant surface (and risk
// a parallel session editing it), this page owns its own thin client. It mirrors
// lib/api.ts auth EXACTLY: BASE = NEXT_PUBLIC_API_BASE || "/api", `X-Auth`
// header from localStorage `famit_token`, 401 -> bounce to /login.
//
// The list/status reads treat a non-200 as DORMANCY (the page renders a premium
// "not configured / coming soon" state) — they never throw. Mutations DO throw a
// friendly message so the form can surface it.

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

// ---- types (match the backend record shapes 1:1) ----
export type AimVerifyMode = "voice_pin" | "otp";
export type AimRole = "manager" | "admin" | "operator";
export type AimNumberStatus = "active" | "locked" | "revoked";

export type AimSubStatus = {
    // status_dict() shape from intent/driver + otp/sender + firewall_bridge.
    status?: string; // "configured" | "not_configured" | "error"
    provider?: string;
    configured?: boolean;
    [k: string]: unknown;
};

export type AimStatus = {
    module: string;
    enabled: boolean;
    sip: "configured" | "not_configured" | string;
    agent_name: string;
    llm_provider: string;
    otp_provider: string;
    cross_plane: "configured" | "in_process" | string;
    max_pin_attempts: number;
    lock_ttl_s: number;
    intent_llm?: AimSubStatus;
    otp?: AimSubStatus;
    firewall?: AimSubStatus;
};

export type AimNumber = {
    number_id: string;
    tenant_id: string;
    phone: string;
    label: string;
    role: AimRole;
    verify_mode: AimVerifyMode;
    grants: string[];
    verified: boolean;
    status: AimNumberStatus;
    registered_by?: string;
    registered_at: string;
    updated_at?: string;
};

export type AimSessionAction = {
    intent?: string;
    risk?: string;
    stepup?: boolean;
    executed?: boolean;
    result_status?: string;
    [k: string]: unknown;
};

export type AimSession = {
    session_id: string;
    tenant_id?: string;
    number_id?: string;
    caller_id?: string;
    started_at?: string;
    ended_at?: string;
    authed?: boolean;
    auth_method?: string;
    turns?: { role: string; text: string }[];
    actions?: AimSessionAction[];
    outcome?: string;
    n_actions?: number;
};

// The capability families a number can be granted (mirrors registry.KNOWN_GRANTS).
export const KNOWN_GRANTS = [
    "campaigns",
    "leads",
    "calls",
    "whatsapp",
    "ads",
    "ads:read",
    "analytics",
    "contacts",
    "billing",
] as const;

export const AIM_ROLES: AimRole[] = ["manager", "admin", "operator"];
export const AIM_VERIFY_MODES: AimVerifyMode[] = ["voice_pin", "otp"];

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
    // 404 (router not mounted) or 501/503 (feature off) => dormant, render coming-soon.
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

// Core mutation: any HTTP method, JSON body optional. Throws a friendly message
// on failure (403 => permission/step-up PIN). Used by the POST/PUT/PATCH/DELETE
// wrappers below so every mutation shares one dormant + error story.
async function mutate<T>(
    method: "POST" | "PUT" | "PATCH" | "DELETE",
    path: string,
    body?: Record<string, unknown>
): Promise<T> {
    const res = await fetch(`${BASE}${path}`, {
        method,
        headers: {
            ...authHeaders(),
            ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
        },
        ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
    });
    handle401(res);
    if (res.status === 404 || res.status === 501 || res.status === 503) {
        throw new Error("This action is not available yet — the AI Manager backend is not configured.");
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
    // 204 / empty body tolerated.
    try {
        return (await res.json()) as T;
    } catch {
        return {} as T;
    }
}

function write<T>(path: string, body: Record<string, unknown>): Promise<T> {
    return mutate<T>("POST", path, body);
}
function writePut<T>(path: string, body: Record<string, unknown>): Promise<T> {
    return mutate<T>("PUT", path, body);
}
function writePatch<T>(path: string, body: Record<string, unknown>): Promise<T> {
    return mutate<T>("PATCH", path, body);
}
function writeDelete<T>(path: string): Promise<T> {
    return mutate<T>("DELETE", path);
}

// ---- public reads (never throw) ----
export const getAimStatus = () => read<AimStatus>("/ai-manager/status");
export const getAimNumbers = () => read<{ numbers: AimNumber[] }>("/ai-manager/numbers");
export const getAimSessions = (limit = 50) =>
    read<{ sessions: AimSession[] }>(`/ai-manager/sessions?limit=${limit}`);

// ---- public mutations (throw friendly on failure) ----
export const registerAimNumber = (body: {
    phone: string;
    label?: string;
    role?: AimRole;
    verify_mode?: AimVerifyMode;
    grants?: string[];
}) => write<AimNumber & { ok: boolean; otp?: unknown }>("/ai-manager/numbers", body);

export const verifyAimNumber = (id: string) =>
    write<AimNumber & { ok: boolean }>(`/ai-manager/numbers/${encodeURIComponent(id)}/verify`, {});

export const setAimGrants = (id: string, grants: string[]) =>
    write<AimNumber & { ok: boolean }>(`/ai-manager/numbers/${encodeURIComponent(id)}/grants`, { grants });

export const revokeAimNumber = (id: string) =>
    write<AimNumber & { ok: boolean }>(`/ai-manager/numbers/${encodeURIComponent(id)}/revoke`, {});

/* ============================================================================
 * F2 — SETUP (ai_manager_profiles) + AUTHORIZED USERS (ai_manager_authorized_users)
 * Master spec §8 (DB), §10 (APIs), §6 (risk L0–L4). Raw PIN is NEVER sent in a
 * read response nor logged — only pin_set_at / failed_pin_attempts / locked_until.
 * ========================================================================== */

// Risk level a setting (require-PIN-from) is keyed on. L0 safe → L4 blocked (§6).
export type AimRiskLevel = "L0" | "L1" | "L2" | "L3" | "L4";

export const AIM_RISK_LEVELS: { value: AimRiskLevel; label: string; hint: string }[] = [
    { value: "L0", label: "L0 — Safe reads", hint: "Today's report, balances, hot-lead count" },
    { value: "L1", label: "L1 — Low-risk writes", hint: "Draft a campaign, add a note, schedule a reminder" },
    { value: "L2", label: "L2 — Medium execution", hint: "WhatsApp selected leads, schedule limited calls, edit copy" },
    { value: "L3", label: "L3 — High execution", hint: "Change budget, bulk call/WA, billing, export data, delete" },
    { value: "L4", label: "L4 — Blocked", hint: "Always refused — secrets, ownership, bypass compliance" },
];

export const AIM_LANGUAGES: { value: string; label: string }[] = [
    { value: "en", label: "English" },
    { value: "hi", label: "Hindi" },
    { value: "hinglish", label: "Hinglish (mixed)" },
    { value: "ta", label: "Tamil" },
    { value: "te", label: "Telugu" },
    { value: "bn", label: "Bengali" },
    { value: "mr", label: "Marathi" },
];

export const AIM_VOICE_PROVIDERS: { value: string; label: string }[] = [
    { value: "sarvam", label: "Sarvam" },
    { value: "elevenlabs", label: "ElevenLabs" },
    { value: "google", label: "Google" },
    { value: "azure", label: "Azure" },
];

// A practical subset of IANA zones — India-first, then common APAC/EU/US.
export const AIM_TIMEZONES: string[] = [
    "Asia/Kolkata",
    "Asia/Dubai",
    "Asia/Singapore",
    "Asia/Dhaka",
    "Asia/Karachi",
    "Europe/London",
    "America/New_York",
    "America/Los_Angeles",
    "UTC",
];

// ai_manager_profiles record (§8). All fields optional on read so a first-run
// (no row yet) hydrates cleanly into the form defaults.
export type AimProfile = {
    id?: string;
    vendor_id?: string;
    enabled: boolean;
    ai_manager_phone_number: string | null;
    language_preference: string | null;
    default_voice_provider: string | null;
    require_pin_for_level: AimRiskLevel | null;
    daily_spend_limit: number | null; // rupees (₹) — UI unit; backend stores its own
    monthly_spend_limit: number | null;
    max_bulk_leads_without_pin: number | null;
    allowed_call_start_time: string | null; // "HH:MM"
    allowed_call_end_time: string | null; // "HH:MM"
    timezone: string | null;
    created_at?: string;
    updated_at?: string;
};

// Sensible first-run defaults when /profile returns dormant or an empty row.
export const AIM_PROFILE_DEFAULTS: AimProfile = {
    enabled: false,
    ai_manager_phone_number: null,
    language_preference: "hinglish",
    default_voice_provider: "sarvam",
    require_pin_for_level: "L3",
    daily_spend_limit: 5000,
    monthly_spend_limit: 100000,
    max_bulk_leads_without_pin: 50,
    allowed_call_start_time: "09:00",
    allowed_call_end_time: "20:00",
    timezone: "Asia/Kolkata",
};

// ai_manager_authorized_users record (§8). `permissions` is the capability
// allow-list (json) — we render it as KNOWN_GRANTS chips. pin_hash is NEVER
// returned; we only ever see the derived pin status fields.
export type AimAuthUser = {
    id: string;
    vendor_id?: string;
    user_id?: string | null;
    name: string;
    phone_number: string;
    normalized_phone_number?: string;
    role: AimRole;
    permissions: string[];
    is_active: boolean;
    pin_set_at: string | null; // null => no PIN enrolled yet
    failed_pin_attempts: number;
    locked_until: string | null; // ISO ts when a lockout lifts, else null
    last_used_at?: string | null;
    created_at?: string;
    updated_at?: string;
};

// ---- Setup (profile) ----
export const getAimProfile = () => read<AimProfile>("/ai-manager/profile");

export const putAimProfile = (body: Partial<AimProfile>) =>
    writePut<AimProfile & { ok?: boolean }>("/ai-manager/profile", body);

// ---- Authorized users ----
export const getAimUsers = () =>
    read<{ users: AimAuthUser[] }>("/ai-manager/authorized-users");

export const createAimUser = (body: {
    name: string;
    phone_number: string;
    role?: AimRole;
    permissions?: string[];
    is_active?: boolean;
}) => write<AimAuthUser & { ok?: boolean }>("/ai-manager/authorized-users", body);

export const patchAimUser = (
    id: string,
    body: Partial<Pick<AimAuthUser, "name" | "phone_number" | "role" | "permissions" | "is_active">>
) => writePatch<AimAuthUser & { ok?: boolean }>(`/ai-manager/authorized-users/${encodeURIComponent(id)}`, body);

export const deleteAimUser = (id: string) =>
    writeDelete<{ ok: boolean }>(`/ai-manager/authorized-users/${encodeURIComponent(id)}`);

// ---- PIN flows (raw PIN never logged/returned) ----
// Set / enrol a PIN for a given authorized user.
export const setAimUserPin = (userId: string, pin: string) =>
    write<{ ok: boolean; pin_set_at?: string }>("/ai-manager/pin/set", { user_id: userId, pin });

// Admin-initiated reset: clears the PIN + lockout so the user can re-enrol.
// Backend may require an OTP confirm step; we expose both legs.
export const requestAimPinReset = (userId: string) =>
    write<{ ok: boolean; otp_sent?: boolean }>("/ai-manager/pin/reset/request", { user_id: userId });

export const confirmAimPinReset = (userId: string, code: string, newPin?: string) =>
    write<{ ok: boolean; pin_set_at?: string | null }>("/ai-manager/pin/reset/confirm", {
        user_id: userId,
        code,
        ...(newPin ? { pin: newPin } : {}),
    });

/* ============================================================================
 * F1 — TEST CONSOLE + OVERVIEW.
 *
 * The /commands/test + /dashboard/summary routes are DEFERRED backend wiring
 * (router defined-not-mounted today) — so these reads/writes degrade to the
 * SAME premium dormant path as every other call here. The parse shape mirrors
 * the master spec §22 NLU schema 1:1 so the Test Console renders the engine's
 * REAL decision (intent · risk · confirm/PIN gate · summary · safety) without
 * a phone — the proof the command engine works.
 *
 * NOTE: F2 above already owns `AimRiskLevel` as the L0–L4 SETTING enum. The NLU
 * parse `risk_level` is a different axis (0–4 int OR a token like "money") — so
 * it is typed locally as `AimParseRisk` to avoid clobbering that enum. The
 * shared riskVariant()/riskLabel() in _shared.tsx normalise either form.
 * ========================================================================== */

export type AimChannel = "dashboard" | "whatsapp" | "phone_sim";
export const AIM_CHANNELS: { value: AimChannel; label: string }[] = [
    { value: "dashboard", label: "Dashboard" },
    { value: "whatsapp", label: "WhatsApp" },
    { value: "phone_sim", label: "Phone (sim)" },
];

// risk axis on a parse: a 0–4 integer OR a string token
// ("safe" | "low" | "bulk" | "money" | "destructive" | "blocked").
export type AimParseRisk = number | string;

// The NLU classification record (master spec §22). The engine NEVER self-
// executes — it only classifies/extracts/summarises. `safe_to_execute` is the
// engine's gate; requires_confirmation / requires_pin drive the UI step-up.
export type AimParse = {
    command_id?: string;
    intent?: string;
    action_type?: string; // "read" | "write" | "money" | "destructive" | ...
    confidence?: number;
    risk_level?: AimParseRisk;
    requires_confirmation?: boolean;
    requires_pin?: boolean;
    entities?: Record<string, unknown>;
    missing_fields?: string[];
    assumptions?: string[];
    user_facing_summary?: string;
    safe_to_execute?: boolean;
    block_reason?: string | null;
    // post-confirm / post-execute fields:
    status?: string; // needs_confirmation | needs_pin | executed | cancelled | blocked | denied
    execution_result?: Record<string, unknown> | string | null;
    cost_estimate_minor?: number; // paise
    cost_actual_minor?: number; // paise
    action_run_id?: string;
    error?: string | null;
};

// A persisted command row (history / overview "recent risky actions").
export type AimCommand = {
    command_id: string;
    session_id?: string;
    created_at?: string;
    channel?: string;
    actor?: string;
    caller_id?: string;
    command_text?: string;
    intent?: string;
    risk_level?: AimParseRisk;
    status?: string;
    cost_minor?: number;
    result_status?: string;
};

// /dashboard/summary rollup (master §14 Overview). All counts are real engine
// aggregates; every field is optional so a partial/empty backend still renders.
export type AimSummary = {
    enabled?: boolean;
    phone_number?: string; // the AI Manager inbound number, when provisioned
    commands_today?: number;
    commands_succeeded?: number;
    commands_failed_or_denied?: number;
    pending_approvals?: number;
    credit_impact_minor?: number; // net paise spent by the AI Manager today
    wallet_balance_minor?: number;
    recent_sessions?: AimSession[];
    recent_risky?: AimCommand[];
    // engine config echo (so Overview can show config without a 2nd call)
    sip?: string;
    llm_provider?: string;
    otp_provider?: string;
};

// ---- public reads (never throw) ----
export const getAimSummary = () => read<AimSummary>("/ai-manager/dashboard/summary");

export const getAimCommands = (params?: {
    status?: string;
    channel?: string;
    risk?: string;
    limit?: number;
}) => {
    const q = new URLSearchParams();
    if (params?.status) q.set("status", params.status);
    if (params?.channel) q.set("channel", params.channel);
    if (params?.risk) q.set("risk", params.risk);
    q.set("limit", String(params?.limit ?? 50));
    return read<{ commands: AimCommand[] }>(`/ai-manager/commands?${q.toString()}`);
};

// ---- Test Console mutations (throw friendly on failure) ----
// Send a natural-language utterance to the SAME command engine the phone uses.
// Returns the §22 parse + a command_id the confirm/execute/cancel calls target.
export const testCommand = (text: string, channel: AimChannel = "dashboard") =>
    write<AimParse>("/ai-manager/commands/test", { text, channel });

export const confirmCommand = (id: string) =>
    write<AimParse>(`/ai-manager/commands/${encodeURIComponent(id)}/confirm`, {});

export const cancelCommand = (id: string) =>
    write<AimParse>(`/ai-manager/commands/${encodeURIComponent(id)}/cancel`, {});

// Execute a parsed command. For PIN-gated actions, pass the freshly collected
// PIN — sent ONCE to be verified+hashed server-side, never logged. The engine
// re-checks policy/caps/step-up before any adapter runs.
export const executeCommand = (id: string, pin?: string) =>
    write<AimParse>(
        `/ai-manager/commands/${encodeURIComponent(id)}/execute`,
        pin ? { pin } : {}
    );

/* ============================================================================
 * F3 — COMMAND HISTORY · SESSION DETAIL · PENDING APPROVALS · CAPABILITIES
 * ----------------------------------------------------------------------------
 * Additive. Reuses the existing read/write + dormant mapping, AimChannel,
 * AimParseRisk, AimSession, confirm/cancel/executeCommand above. The lighter
 * AimCommand + getAimCommands (Overview "recent risky") stay untouched; F3 adds
 * a richer history row + the full server-side filter set + the detail reads
 * (session / audit-logs / action-runs) the existing client did not cover.
 * Record shapes mirror the backend ai_manager_* tables 1:1 (master §8/§10/§22).
 * Backend is DEFINED-NOT-MOUNTED today -> every read degrades to {kind:"dormant"}.
 * ========================================================================== */

// Risk taxonomy (master §6 L0–L4). Canonical definition lives in the F2 block
// above (`export type AimRiskLevel = "L0" | … | "L4"`) — the SETTING enum and the
// command/catalog risk axis are the same L0–L4 ladder, so they share one type.
// (A backend that emits a numeric/token risk is coerced by _shared.riskVariant.)

// Command lifecycle status (master §8 ai_manager_commands.status).
export type AimCommandStatus =
    | "pending"
    | "needs_confirmation"
    | "needs_pin"
    | "needs_review"
    | "executing"
    | "succeeded"
    | "failed"
    | "denied"
    | "cancelled"
    | string;

// Cost estimate / actual. Backend money is INTEGER paise everywhere — prefer the
// *_minor fields and render with _shared.rupees(). The legacy dict form is kept
// tolerant in case an older payload sends {amount,currency}.
export type AimCost = {
    estimate_minor?: number;
    actual_minor?: number;
    amount?: number;
    currency?: string;
    unit?: string;
    [k: string]: unknown;
};

// A full Command History / Pending Approvals row — superset of the lighter
// AimCommand, tolerant of both `command_id`/`id` and `command_text`/`raw_text`
// so it binds to whatever the backend serialises.
export type AimHistoryCommand = {
    id?: string;
    command_id?: string;
    session_id?: string;
    vendor_id?: string;
    user_id?: string;
    actor?: string; // human label of who issued it
    caller_id?: string;
    caller_phone?: string;
    channel?: AimChannel | string;
    created_at?: string;
    updated_at?: string;
    command_text?: string;
    raw_text?: string;
    normalized_text?: string;
    intent?: string;
    detected_intent?: string;
    action_type?: string;
    module?: string;
    risk_level?: AimRiskLevel;
    status?: AimCommandStatus;
    result_status?: string;
    confirmation_required?: boolean;
    confirmation_status?: string;
    requires_confirmation?: boolean;
    pin_required?: boolean;
    requires_pin?: boolean;
    pin_verified?: boolean;
    permission_result?: Record<string, unknown> & { allowed?: boolean; reason?: string };
    cost_minor?: number; // convenience: actual-or-estimate paise
    cost_estimate?: AimCost;
    cost_estimate_minor?: number;
    cost_actual_minor?: number;
    execution_result?: Record<string, unknown> | string | null;
    error_message?: string;
    error?: string | null;
    user_facing_summary?: string;
    block_reason?: string | null;
    action_run_id?: string;
};

// Convenience: the canonical id of a history/approval row regardless of which
// field the backend used.
export function commandId(c: AimHistoryCommand): string {
    return c.id || c.command_id || "";
}
export function commandText(c: AimHistoryCommand): string {
    return c.command_text || c.raw_text || c.normalized_text || "";
}
export function commandIntent(c: AimHistoryCommand): string {
    return c.intent || c.detected_intent || c.action_type || "";
}

// A single transcript turn inside a session (PIN-masked server-side per §7).
export type AimTurn = {
    role: string; // "user" | "assistant" | "system"
    text: string;
    at?: string;
    masked?: boolean;
};

// Full session record (master §8 ai_manager_sessions + nested commands/meta).
// Superset of the list-shape AimSession so the detail page can read both.
export type AimSessionDetail = {
    id?: string;
    session_id?: string;
    tenant_id?: string;
    vendor_id?: string;
    user_id?: string;
    channel?: AimChannel | string;
    provider_call_id?: string;
    caller_phone?: string;
    caller_id?: string;
    status?: string; // active/completed/failed/blocked
    outcome?: string;
    started_at?: string;
    ended_at?: string;
    authed?: boolean;
    auth_method?: string;
    transcript_text?: string;
    turns?: AimTurn[];
    commands?: AimHistoryCommand[];
    actions?: AimSessionAction[];
    stt_provider?: string;
    tts_provider?: string;
    llm_provider?: string;
    recording_url?: string;
    metadata?: Record<string, unknown>;
};

// Immutable audit event (master §8 ai_manager_audit_logs).
export type AimAuditLog = {
    id: string;
    vendor_id?: string;
    user_id?: string;
    session_id?: string;
    command_id?: string;
    event_type?: string;
    severity?: string; // info/notice/warning/critical
    message?: string;
    metadata?: Record<string, unknown>;
    created_at?: string;
};

// Async action run (master §8 ai_manager_action_runs).
export type AimActionRun = {
    id: string;
    command_id?: string;
    vendor_id?: string;
    action_type?: string;
    target_module?: string;
    status?: string; // queued/running/succeeded/failed/retried/cancelled
    job_id?: string;
    input?: Record<string, unknown>;
    output?: Record<string, unknown>;
    error?: Record<string, unknown> | string;
    started_at?: string;
    completed_at?: string;
    created_at?: string;
};

// Full server-side filter set for Command History (master §14: status/channel/
// risk/date/user/module). All optional; tenant-scoped server-side.
export type AimCommandFilters = {
    status?: string;
    channel?: string;
    risk?: string;
    from?: string; // ISO date (yyyy-mm-dd)
    to?: string;
    user?: string;
    module?: string;
    q?: string; // free-text on command text
    limit?: number;
};

function aimQs(params: Record<string, string | number | undefined>): string {
    const u = new URLSearchParams();
    for (const [k, v] of Object.entries(params)) {
        if (v === undefined || v === null || v === "") continue;
        u.set(k, String(v));
    }
    const s = u.toString();
    return s ? `?${s}` : "";
}

// ---- F3 reads (never throw — ReadResult + dormant mapping) ----

// Command History with the full filter set (superset of getAimCommands).
export const getAimCommandHistory = (f: AimCommandFilters = {}) =>
    read<{ commands: AimHistoryCommand[]; total?: number }>(
        `/ai-manager/commands${aimQs({
            status: f.status,
            channel: f.channel,
            risk: f.risk,
            from: f.from,
            to: f.to,
            user: f.user,
            module: f.module,
            q: f.q,
            limit: f.limit ?? 100,
        })}`,
    );

export const getAimCommandDetail = (id: string) =>
    read<AimHistoryCommand>(`/ai-manager/commands/${encodeURIComponent(id)}`);

export const getAimSessionDetail = (id: string) =>
    read<AimSessionDetail>(`/ai-manager/sessions/${encodeURIComponent(id)}`);

export const getAimAuditLogs = (q: { session_id?: string; command_id?: string; limit?: number } = {}) =>
    read<{ logs: AimAuditLog[] }>(
        `/ai-manager/audit-logs${aimQs({ session_id: q.session_id, command_id: q.command_id, limit: q.limit ?? 200 })}`,
    );

export const getAimActionRuns = (q: { command_id?: string; session_id?: string; limit?: number } = {}) =>
    read<{ runs: AimActionRun[] }>(
        `/ai-manager/action-runs${aimQs({ command_id: q.command_id, session_id: q.session_id, limit: q.limit ?? 200 })}`,
    );

/* ---- INTENT CATALOG (master §11 taxonomy) — static, ships with the bundle ----
 * Powers the Capability Catalog page (browse what the AI Manager can do, by risk)
 * with ZERO backend. `grant` = the KNOWN_GRANTS family a number must hold; `risk`
 * = the typical L-level (the engine may escalate per-policy at runtime). Example
 * utterances mirror master §23 (Hinglish ok). `parked` = cred-blocked module. */

export type AimCapability = {
    intent: string; // e.g. "lead.call_hot"
    module: string;
    grant: string; // KNOWN_GRANTS family gating it
    risk: AimRiskLevel; // typical L-level
    label: string;
    example: string;
    billable?: boolean;
    parked?: boolean;
};

export const INTENT_CATALOG: AimCapability[] = [
    // analytics (L0 read)
    { intent: "analytics.today_summary", module: "analytics", grant: "analytics", risk: "L0", label: "Today's summary", example: "Aaj ka business kaisa raha?" },
    { intent: "analytics.campaign_summary", module: "analytics", grant: "analytics", risk: "L0", label: "Campaign summary", example: "Meri campaigns kaisi chal rahi hain?" },
    { intent: "analytics.lead_summary", module: "analytics", grant: "analytics", risk: "L0", label: "Lead summary", example: "Aaj kitne hot leads aaye?" },
    { intent: "analytics.cost_summary", module: "analytics", grant: "analytics", risk: "L0", label: "Cost summary", example: "Aaj ka kharcha kitna hua?" },
    { intent: "analytics.send_report", module: "analytics", grant: "analytics", risk: "L1", label: "Send report", example: "Aaj ka report WhatsApp kar do" },
    { intent: "analytics.compare_periods", module: "analytics", grant: "analytics", risk: "L0", label: "Compare periods", example: "Is week vs last week dikhao" },
    // campaign
    { intent: "campaign.list", module: "campaign", grant: "campaigns", risk: "L0", label: "List campaigns", example: "Kaun kaun si campaigns active hain?" },
    { intent: "campaign.create_draft", module: "campaign", grant: "campaigns", risk: "L1", label: "Draft a campaign", example: "Diwali offer ka draft banao" },
    { intent: "campaign.pause", module: "campaign", grant: "campaigns", risk: "L2", label: "Pause campaign", example: "Gurgaon campaign rok do" },
    { intent: "campaign.resume", module: "campaign", grant: "campaigns", risk: "L2", label: "Resume campaign", example: "Wahi campaign phir se chalu karo" },
    { intent: "campaign.update_budget", module: "campaign", grant: "campaigns", risk: "L3", label: "Change budget", example: "Budget 500 a day kar do", billable: true },
    { intent: "campaign.launch", module: "campaign", grant: "campaigns", risk: "L3", label: "Launch campaign", example: "Naya offer launch kar do", billable: true },
    { intent: "campaign.kill_losers", module: "campaign", grant: "campaigns", risk: "L3", label: "Kill losing ads", example: "Jo chal nahi rahi unko band karo" },
    { intent: "campaign.scale_winners", module: "campaign", grant: "campaigns", risk: "L3", label: "Scale winners", example: "Best ad ka budget badha do", billable: true },
    // lead
    { intent: "lead.list_hot", module: "lead", grant: "leads", risk: "L0", label: "Hot leads", example: "Hot leads dikhao" },
    { intent: "lead.call_hot", module: "lead", grant: "leads", risk: "L3", label: "Call all hot leads", example: "Saare hot leads ko call karo", billable: true },
    { intent: "lead.update_status", module: "lead", grant: "leads", risk: "L2", label: "Update lead stage", example: "Is lead ko interested mark karo" },
    { intent: "lead.add_note", module: "lead", grant: "leads", risk: "L1", label: "Add a note", example: "Note add karo — callback at 5" },
    { intent: "lead.assign", module: "lead", grant: "leads", risk: "L2", label: "Assign lead", example: "Ye lead Rahul ko de do" },
    { intent: "lead.export", module: "lead", grant: "leads", risk: "L3", label: "Export leads", example: "Aaj ke leads export karo" },
    { intent: "lead.schedule_followup", module: "lead", grant: "leads", risk: "L2", label: "Schedule follow-up", example: "Kal subah follow-up laga do" },
    // call
    { intent: "call.start_bulk", module: "call", grant: "calls", risk: "L3", label: "Bulk call", example: "5 baje ke baad sab hot leads ko call karo", billable: true },
    { intent: "call.call_single_lead", module: "call", grant: "calls", risk: "L2", label: "Call one lead", example: "Is lead ko abhi call karo", billable: true },
    { intent: "call.stop_queue", module: "call", grant: "calls", risk: "L2", label: "Stop call queue", example: "Calling rok do" },
    { intent: "call.retry_failed", module: "call", grant: "calls", risk: "L2", label: "Retry failed", example: "Jo miss hue unko dobara try karo", billable: true },
    { intent: "call.send_summary", module: "call", grant: "calls", risk: "L1", label: "Call summary", example: "Aaj ki calls ka summary bhejo" },
    { intent: "call.get_recording", module: "call", grant: "calls", risk: "L1", label: "Get recording", example: "Us call ki recording do" },
    // whatsapp
    { intent: "whatsapp.send_brochure", module: "whatsapp", grant: "whatsapp", risk: "L2", label: "Send brochure", example: "Brochure WhatsApp pe bhejo" },
    { intent: "whatsapp.send_followup", module: "whatsapp", grant: "whatsapp", risk: "L2", label: "Send follow-up", example: "Follow-up message bhejo" },
    { intent: "whatsapp.send_bulk", module: "whatsapp", grant: "whatsapp", risk: "L3", label: "Bulk WhatsApp", example: "Sab leads ko offer bhejo", billable: true },
    { intent: "whatsapp.stop_sequence", module: "whatsapp", grant: "whatsapp", risk: "L2", label: "Stop sequence", example: "Wo sequence band karo" },
    { intent: "whatsapp.template_status", module: "whatsapp", grant: "whatsapp", risk: "L0", label: "Template status", example: "Template approve hua kya?" },
    // workflow (LIVE module)
    { intent: "workflow.create_draft", module: "workflow", grant: "campaigns", risk: "L1", label: "Draft a workflow", example: "Naya lead aate hi WhatsApp ka flow banao" },
    { intent: "workflow.activate", module: "workflow", grant: "campaigns", risk: "L3", label: "Activate workflow", example: "Wo workflow chalu kar do" },
    { intent: "workflow.pause", module: "workflow", grant: "campaigns", risk: "L2", label: "Pause workflow", example: "Workflow pause kar do" },
    { intent: "workflow.run_now", module: "workflow", grant: "campaigns", risk: "L2", label: "Run now", example: "Abhi ek baar run karo" },
    { intent: "workflow.show_runs", module: "workflow", grant: "campaigns", risk: "L0", label: "Show runs", example: "Is workflow ke runs dikhao" },
    // billing (read)
    { intent: "billing.balance", module: "billing", grant: "billing", risk: "L0", label: "Wallet balance", example: "Balance kitna hai?" },
    { intent: "billing.usage_today", module: "billing", grant: "billing", risk: "L0", label: "Usage today", example: "Aaj kitna kharch hua?" },
    { intent: "billing.usage_month", module: "billing", grant: "billing", risk: "L0", label: "Usage this month", example: "Is mahine ka usage batao" },
    { intent: "billing.cost_breakdown", module: "billing", grant: "billing", risk: "L0", label: "Cost breakdown", example: "Kis cheez pe kitna gaya?" },
    { intent: "billing.low_balance_alert", module: "billing", grant: "billing", risk: "L0", label: "Low balance alert", example: "Balance kam ho to batana" },
    // booking (LIVE module)
    { intent: "booking.today", module: "booking", grant: "leads", risk: "L0", label: "Today's bookings", example: "Aaj ki bookings dikhao" },
    { intent: "booking.tomorrow", module: "booking", grant: "leads", risk: "L0", label: "Tomorrow's bookings", example: "Kal kya schedule hai?" },
    { intent: "booking.create", module: "booking", grant: "leads", risk: "L2", label: "Create booking", example: "Kal 4 baje visit book karo" },
    { intent: "booking.reschedule", module: "booking", grant: "leads", risk: "L2", label: "Reschedule", example: "Us booking ko shaam ko shift karo" },
    { intent: "booking.cancel", module: "booking", grant: "leads", risk: "L2", label: "Cancel booking", example: "Wo booking cancel karo" },
    { intent: "booking.send_reminder", module: "booking", grant: "whatsapp", risk: "L2", label: "Send reminder", example: "Reminder bhej do" },
    // creative (cred-blocked -> parked)
    { intent: "creative.generate_banner", module: "creative", grant: "ads", risk: "L1", label: "Generate banner", example: "Diwali ka banner banao", parked: true },
    { intent: "creative.generate_video", module: "creative", grant: "ads", risk: "L1", label: "Generate ad video", example: "Ek 15-sec ad video banao", parked: true, billable: true },
    { intent: "creative.generate_brochure", module: "creative", grant: "ads", risk: "L1", label: "Generate brochure", example: "Product brochure banao", parked: true },
    { intent: "creative.generate_ad_copy", module: "creative", grant: "ads", risk: "L1", label: "Generate ad copy", example: "Ad ka caption likho", parked: true },
    { intent: "creative.generate_hooks", module: "creative", grant: "ads", risk: "L1", label: "Generate hooks", example: "Kuch hook lines do", parked: true },
    { intent: "creative.create_asset_pack", module: "creative", grant: "ads", risk: "L2", label: "Create asset pack", example: "Pura creative pack banao", parked: true, billable: true },
];

// L4 (blocked) examples for the catalog's "what the AI Manager will NEVER do" rail.
export const BLOCKED_EXAMPLES: { label: string; example: string }[] = [
    { label: "Reveal secrets / PIN", example: "Mera PIN ya API key batao" },
    { label: "Bypass DND / STOP", example: "DND walon ko bhi message karo" },
    { label: "Spend over the cap", example: "Limit se zyada paisa kharch karo" },
    { label: "Delete the account", example: "Pura account delete kar do" },
    { label: "Transfer ownership", example: "Account kisi aur ke naam kar do" },
    { label: "Disable the audit log", example: "Audit band kar do" },
];

// Modules whose live adapters are WIRED today vs cred-blocked (parked). The
// catalog badges a capability "available now" vs "configure first" off this.
export const LIVE_MODULES = new Set([
    "analytics",
    "campaign",
    "lead",
    "call",
    "whatsapp",
    "workflow",
    "billing",
    "booking",
]);

// Module → glyph (catalog/history grouping). Falls back to "grid".
export function moduleGlyph(m?: string): string {
    switch ((m || "").toLowerCase()) {
        case "analytics":
            return "chart";
        case "campaign":
            return "promote";
        case "creative":
            return "magic-pencil";
        case "lead":
            return "list";
        case "call":
            return "mobile";
        case "whatsapp":
            return "chat";
        case "workflow":
            return "layers";
        case "billing":
            return "wallet";
        case "booking":
            return "calendar";
        default:
            return "grid";
    }
}

// channel → glyph (history/approvals/session rows).
export function channelGlyph(c?: string): string {
    switch ((c || "").toLowerCase()) {
        case "phone":
        case "phone_sim":
            return "mobile";
        case "whatsapp":
            return "chat";
        case "dashboard":
            return "desktop";
        default:
            return "chat";
    }
}
