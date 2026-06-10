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

async function write<T>(path: string, body: Record<string, unknown>): Promise<T> {
    const res = await fetch(`${BASE}${path}`, {
        method: "POST",
        headers: { ...authHeaders(), "Content-Type": "application/json" },
        body: JSON.stringify(body),
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
    return res.json();
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
