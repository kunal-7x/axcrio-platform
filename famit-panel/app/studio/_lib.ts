// Studio client — Coolify PaaS API (via /api/coolify/* BFF proxy).
// The API key stays server-side; the browser hits only the Next.js proxy route.
// Dormant-safe: StudioError with status 503 = "not configured" → show setup card.

export class StudioError extends Error {
    constructor(
        readonly code: string,
        message: string,
        readonly status: number,
    ) {
        super(message);
        this.name = "StudioError";
    }
}

export const isNotConfigured = (e: unknown): boolean =>
    e instanceof StudioError && (e.status === 503 || e.status === 502);

// ---- Coolify v4 types (subset we display) -----------------------------------

export type AppStatus = "running" | "stopped" | "restarting" | "exited" | "unknown";
export type DeployStatus = "queued" | "in_progress" | "finished" | "failed" | "cancelled";

export type CoolifyApp = {
    id: number;
    uuid: string;
    name: string;
    description?: string;
    status: AppStatus;
    fqdn?: string;
    git_repository?: string;
    git_branch?: string;
    build_pack?: string;
    updated_at: string;
    created_at: string;
};

export type CoolifyDeployment = {
    id: number;
    uuid: string;
    application_id: number;
    status: DeployStatus;
    logs?: string;
    commit?: string;
    created_at: string;
};

export type CoolifyServer = {
    id: number;
    uuid: string;
    name: string;
    ip: string;
    status: "reachable" | "unreachable";
    description?: string;
};

// ---- HTTP helpers -----------------------------------------------------------

const BASE = "/api/coolify";

async function req<T>(path: string, init: RequestInit = {}): Promise<T> {
    const res = await fetch(`${BASE}/${path}`, {
        headers: { "Content-Type": "application/json" },
        ...init,
    });
    const text = await res.text();
    const data = text ? (JSON.parse(text) as Record<string, unknown>) : {};
    if (!res.ok) {
        const code = (data.error as string | undefined) ?? `http_${res.status}`;
        const msg = (data.message as string | undefined) ?? `request failed (${res.status})`;
        throw new StudioError(code, msg, res.status);
    }
    return data as T;
}

const get = <T>(path: string) => req<T>(path);
const post = <T>(path: string, body?: unknown) =>
    req<T>(path, {
        method: "POST",
        ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
    });

// ---- API calls --------------------------------------------------------------

export async function listApplications(): Promise<CoolifyApp[]> {
    const d = await get<unknown>("applications");
    return Array.isArray(d) ? (d as CoolifyApp[]) : [];
}

export async function listDeployments(appUuid?: string): Promise<CoolifyDeployment[]> {
    const path = appUuid ? `deployments?application_uuid=${appUuid}` : "deployments";
    const d = await get<unknown>(path);
    return Array.isArray(d) ? (d as CoolifyDeployment[]) : [];
}

export async function triggerDeploy(uuid: string): Promise<{ message: string; deployment_uuid?: string }> {
    return post<{ message: string; deployment_uuid?: string }>(`deploy?uuid=${uuid}`);
}

export async function listServers(): Promise<CoolifyServer[]> {
    const d = await get<unknown>("servers");
    return Array.isArray(d) ? (d as CoolifyServer[]) : [];
}

// ---- Display helpers --------------------------------------------------------

export const APP_STATUS_LABEL: Record<AppStatus, string> = {
    running: "Running",
    stopped: "Stopped",
    restarting: "Restarting",
    exited: "Exited",
    unknown: "Unknown",
};

export const DEPLOY_STATUS_LABEL: Record<DeployStatus, string> = {
    queued: "Queued",
    in_progress: "Deploying",
    finished: "Done",
    failed: "Failed",
    cancelled: "Cancelled",
};

export function relTime(iso: string): string {
    const ms = Date.parse(iso);
    if (Number.isNaN(ms)) return iso;
    const s = Math.floor((Date.now() - ms) / 1000);
    if (s < 60) return "just now";
    if (s < 3600) return `${Math.floor(s / 60)}m ago`;
    if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
    return `${Math.floor(s / 86400)}d ago`;
}
