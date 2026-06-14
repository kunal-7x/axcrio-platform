"use client";

// ============================================================================
// lib/integrations.ts — typed client for the Universal Provider / Connector
// Registry (design/PROVIDER-FRAMEWORK-PLAN.md §4/§8, video-flex-framework-design
// DESIGN[crazy-ui-security]).
//
// The LIVE backend mounts the registry under `/provider-registry` (caller.py W4 —
// NOT the spec's logical /admin/providers; the bare /providers prefix is shadowed
// by the legacy LLM-router list). The panel proxies caller.py at `/api`, so every
// call here is `/api/provider-registry/*`. Auth is the same `X-Auth` header the
// rest of the panel uses (lib/api.ts convention).
//
// DORMANT-SAFE: when `PROVIDER_REGISTRY_ENABLED` is OFF for the box (or the tenant
// is not entitled), every route 404s. Every fetcher here returns a calm empty
// shape on a non-2xx (never throws for a list/health read) so the page renders a
// coming-soon card, never an error wall. Mutations DO surface a typed error so the
// modal can show a precise message.
//
// SECURITY: the raw key is NEVER returned by a list/detail read — only `masked`.
// Reveal is a 3-step PIN-gated flow (verify-pin → reveal-init → reveal) and the
// plaintext is handled by the caller in a useRef, wiped on unmount/timeout — never
// in react-state. Platform (`ai_provider`) credentials are masked-only (no reveal).
// ============================================================================

import { useCallback, useEffect, useRef, useState } from "react";

// ---- transport (mirrors lib/api.ts) ----------------------------------------
const BASE =
    typeof process !== "undefined" && process.env.NEXT_PUBLIC_API_BASE
        ? process.env.NEXT_PUBLIC_API_BASE
        : "/api";

function getToken(): string | null {
    if (typeof window === "undefined") return null;
    return localStorage.getItem("famit_token");
}

function authHeaders(extra?: Record<string, string>): HeadersInit {
    const token = getToken();
    return {
        ...(token ? { "X-Auth": token } : {}),
        ...(extra || {}),
    };
}

export class IntegrationError extends Error {
    status: number;
    code: string;
    constructor(message: string, status: number, code = "") {
        super(message);
        this.name = "IntegrationError";
        this.status = status;
        this.code = code;
    }
}

// A read that degrades to a fallback on ANY non-2xx (dormant-safe). The boolean
// `disabled` flag tells the page the surface is off (404) vs. a transient error.
async function readJson<T>(path: string, fallback: T): Promise<{ data: T; disabled: boolean }> {
    try {
        const res = await fetch(`${BASE}${path}`, { headers: authHeaders(), cache: "no-store" });
        if (res.status === 404) return { data: fallback, disabled: true };
        if (!res.ok) return { data: fallback, disabled: false };
        return { data: (await res.json()) as T, disabled: false };
    } catch {
        return { data: fallback, disabled: false };
    }
}

// A mutation that throws a typed IntegrationError on a non-2xx so the form can
// render the precise reason (https-only / ssrf_blocked / step_up_required / …).
async function writeJson<T>(
    path: string,
    method: "POST" | "PUT" | "DELETE",
    body?: unknown,
    extraHeaders?: Record<string, string>,
): Promise<T> {
    const res = await fetch(`${BASE}${path}`, {
        method,
        headers: authHeaders({ "Content-Type": "application/json", ...(extraHeaders || {}) }),
        body: body === undefined ? undefined : JSON.stringify(body),
    });
    let json: Record<string, unknown> = {};
    try {
        json = (await res.json()) as Record<string, unknown>;
    } catch {
        /* empty body */
    }
    if (!res.ok) {
        const raw = String(json.error || json.reason || "");
        throw new IntegrationError(humanizeError(raw, res.status), res.status, raw);
    }
    return json as T;
}

// Map a raw backend error string to a human, actionable message.
export function humanizeError(raw: string, status: number): string {
    if (raw.startsWith("ssrf_blocked")) {
        const reason = raw.split(":").slice(1).join(":") || "blocked";
        return `Endpoint refused by the SSRF guard (${reason}). Private, loopback and cloud-metadata addresses are never allowed.`;
    }
    if (raw === "hosted base_url must be https" || raw === "hosted_base_url_must_be_https")
        return "A hosted provider's base URL must be https://";
    if (raw.startsWith("invalid field_map"))
        return `That field-map is invalid — JSONPath only, max depth 5, no expressions. (${raw.replace("invalid field_map:", "").trim()})`;
    if (raw === "step_up_required" || raw === "step_up_invalid")
        return "Enter your security PIN to reveal this key.";
    if (raw === "step_up_unavailable")
        return "Reveal is unavailable — the security firewall isn't configured.";
    if (raw === "no_credential") return "No key is stored for this provider yet.";
    if (raw === "decrypt_failed") return "Could not decrypt the stored key (it may have been rotated).";
    if (raw === "credential required") return "Paste a key first.";
    if (raw === "not_found") return "That provider no longer exists.";
    if (status === 403) return "You don't have permission for that — platform keys are managed by the admin.";
    if (status === 402) return "This feature is locked on your plan.";
    return raw || "Something went wrong. Please try again.";
}

// ---- types (match endpoints._def_public_dict + masked + circuit) -----------
export type ProviderType = "hosted_api" | "self_hosted" | "tool_connector" | "platform_builtin";
export type AuthScheme = "bearer" | "api_key_header" | "api_key_query" | "basic" | "oauth2_cc" | "none";
export type TransformType = "openai_compat" | "named_provider" | "custom_field_map";
export type Capability =
    | "text_gen"
    | "image_gen"
    | "video_gen"
    | "tts"
    | "stt"
    | "embed"
    | "rerank"
    | "tool_call"
    | "webhook"
    | "storage";
export type CircuitState = "closed" | "open" | "half_open" | "unknown";

export type ProviderDef = {
    id: string;
    tenant_id: string;
    is_global: boolean;
    slug: string;
    display_name: string;
    provider_type: ProviderType;
    capabilities: Capability[];
    base_url: string;
    auth_scheme: AuthScheme;
    auth_header_name?: string | null;
    transform_type: TransformType;
    named_provider?: string | null;
    request_field_map?: Record<string, string> | null;
    response_field_map?: Record<string, string> | null;
    model_default?: string | null;
    cost_per_unit_micros?: number | null;
    cost_unit?: string | null;
    health_check_path?: string | null;
    priority: number;
    rate_limit_rpm?: number | null;
    is_enabled: boolean;
    is_platform_default: boolean;
    created_at?: string | null;
    updated_at?: string | null;
    // list-augment fields
    masked?: string | null; // a masked credential preview if one is stored
    circuit?: CircuitState;
    has_credential?: boolean;
};

export type TestResult = {
    provider_id: string;
    slug: string;
    healthy: boolean;
    latency_ms: number;
    detail: string;
    circuit: CircuitState;
};

export type RevealInit = {
    step_up_token: string;
    expires_in: number;
    scope: string;
    aud: string;
};

export type HealthRow = {
    provider_id?: string;
    slug?: string;
    display_name?: string;
    capability?: string;
    healthy?: boolean;
    circuit?: CircuitState;
    latency_ms?: number;
    detail?: string;
    status?: string;
};

// The write body for create/update (a curated subset; tenant_id/id are server-set).
export type ProviderDefInput = {
    slug: string;
    display_name: string;
    provider_type: ProviderType;
    capabilities: Capability[];
    base_url: string;
    auth_scheme: AuthScheme;
    auth_header_name?: string;
    auth_value_tmpl?: string;
    transform_type: TransformType;
    named_provider?: string;
    request_field_map?: Record<string, string>;
    response_field_map?: Record<string, string>;
    model_default?: string;
    cost_per_unit_micros?: number;
    cost_unit?: string;
    health_check_path?: string;
    priority?: number;
    rate_limit_rpm?: number;
    is_enabled?: boolean;
    api_key?: string;
};

// ============================================================================
// TENANT (vendor) surface — /provider-registry
// ============================================================================
export async function listProviders(capability = ""): Promise<{ providers: ProviderDef[]; disabled: boolean }> {
    const q = capability ? `?capability=${encodeURIComponent(capability)}` : "";
    const { data, disabled } = await readJson<{ providers: ProviderDef[] }>(
        `/provider-registry${q}`,
        { providers: [] },
    );
    return { providers: data.providers || [], disabled };
}

export async function getProvidersHealth(capability = ""): Promise<{ rows: HealthRow[]; disabled: boolean }> {
    const q = capability ? `?capability=${encodeURIComponent(capability)}` : "";
    const { data, disabled } = await readJson<Record<string, unknown>>(
        `/provider-registry/health${q}`,
        {},
    );
    return { rows: normalizeHealth(data), disabled };
}

export function createProvider(input: ProviderDefInput): Promise<ProviderDef> {
    return writeJson<ProviderDef>("/provider-registry", "POST", input);
}

export function updateProvider(id: string, patch: Partial<ProviderDefInput>): Promise<ProviderDef> {
    return writeJson<ProviderDef>(`/provider-registry/${id}`, "PUT", patch);
}

export function deleteProvider(id: string): Promise<{ deleted: boolean; id: string }> {
    return writeJson(`/provider-registry/${id}`, "DELETE");
}

export function storeCredential(
    id: string,
    apiKey: string,
): Promise<{ stored: boolean; key_masked: string; scope: string }> {
    return writeJson(`/provider-registry/${id}/credential`, "POST", { api_key: apiKey });
}

export function testConnection(id: string, admin = false): Promise<TestResult> {
    const path = admin ? `/provider-registry/admin/${id}/test` : `/provider-registry/${id}/test`;
    return writeJson<TestResult>(path, "POST");
}

// ---- the 3-step PIN-gated reveal --------------------------------------------
// 1) verify-pin (Form) → a generic step-up; 2) reveal-init → an aud-bound single-
//    use provider.reveal token; 3) reveal with X-Step-Up → plaintext (once).
export async function verifyPin(pin: string, scope = "provider.reveal"): Promise<boolean> {
    const form = new URLSearchParams({ pin, scope });
    const res = await fetch(`${BASE}/firewall/verify-pin`, {
        method: "POST",
        headers: authHeaders({ "Content-Type": "application/x-www-form-urlencoded" }),
        body: form.toString(),
    });
    return res.ok;
}

export function revealInit(id: string): Promise<RevealInit> {
    return writeJson<RevealInit>(`/provider-registry/${id}/reveal-init`, "POST");
}

export function revealCredential(id: string, stepUpToken: string): Promise<{ provider_id: string; credential: string }> {
    return writeJson(`/provider-registry/${id}/reveal`, "POST", undefined, { "X-Step-Up": stepUpToken });
}

// The full flow as one call — PIN already verified by the caller's PIN pad.
export async function revealFlow(id: string): Promise<string> {
    const init = await revealInit(id);
    const res = await revealCredential(id, init.step_up_token);
    return res.credential;
}

// ============================================================================
// SUPER-ADMIN surface — /provider-registry/admin
// ============================================================================
export async function adminListAll(
    capability = "",
    tenantId = "",
): Promise<{ providers: ProviderDef[]; disabled: boolean }> {
    const qs = new URLSearchParams();
    if (capability) qs.set("capability", capability);
    if (tenantId) qs.set("tenant_id", tenantId);
    const q = qs.toString() ? `?${qs.toString()}` : "";
    const { data, disabled } = await readJson<{ providers: ProviderDef[] }>(
        `/provider-registry/admin/all${q}`,
        { providers: [] },
    );
    return { providers: data.providers || [], disabled };
}

export async function adminHealth(): Promise<{ rows: HealthRow[]; disabled: boolean }> {
    const { data, disabled } = await readJson<Record<string, unknown>>(
        `/provider-registry/admin/health`,
        {},
    );
    return { rows: normalizeHealth(data), disabled };
}

export function adminCreateProvider(
    input: ProviderDefInput & { owner_tenant_id?: string; credential_scope?: string },
): Promise<ProviderDef> {
    return writeJson<ProviderDef>("/provider-registry/admin", "POST", input);
}

export function adminUpdateProvider(id: string, patch: Partial<ProviderDefInput>): Promise<ProviderDef> {
    return writeJson<ProviderDef>(`/provider-registry/admin/${id}`, "PUT", patch);
}

export function adminDeleteProvider(id: string): Promise<{ deleted: boolean; id: string }> {
    return writeJson(`/provider-registry/admin/${id}`, "DELETE");
}

// ---- shaping helpers --------------------------------------------------------
// The /health route returns registry.resolve_status, whose shape is flexible
// (a list, a {providers:[...]}, or a {slug: {...}} map). Normalize to rows so the
// Health table never breaks on a shape change.
function normalizeHealth(data: unknown): HealthRow[] {
    if (!data) return [];
    if (Array.isArray(data)) return data as HealthRow[];
    const obj = data as Record<string, unknown>;
    if (Array.isArray(obj.providers)) return obj.providers as HealthRow[];
    if (Array.isArray(obj.rows)) return obj.rows as HealthRow[];
    // a {slug|id: {...}} map
    const rows: HealthRow[] = [];
    for (const [k, v] of Object.entries(obj)) {
        if (v && typeof v === "object" && !Array.isArray(v)) {
            rows.push({ slug: k, ...(v as HealthRow) });
        }
    }
    return rows;
}

// ============================================================================
// HOOKS
// ============================================================================
// One list hook — used by both the page and the Video Studio BYO-key picker.
// `admin` switches to the all-tenants console source. Returns dormant flag.
export function useProviders(opts?: { capability?: string; admin?: boolean; tenantId?: string }) {
    const { capability = "", admin = false, tenantId = "" } = opts || {};
    const [providers, setProviders] = useState<ProviderDef[]>([]);
    const [loading, setLoading] = useState(true);
    const [dormant, setDormant] = useState(false);

    const reload = useCallback(async () => {
        const res = admin
            ? await adminListAll(capability, tenantId)
            : await listProviders(capability);
        setProviders(res.providers);
        setDormant(res.disabled);
        setLoading(false);
    }, [capability, admin, tenantId]);

    useEffect(() => {
        let alive = true;
        (async () => {
            const res = admin
                ? await adminListAll(capability, tenantId)
                : await listProviders(capability);
            if (!alive) return;
            setProviders(res.providers);
            setDormant(res.disabled);
            setLoading(false);
        })();
        return () => {
            alive = false;
        };
    }, [capability, admin, tenantId]);

    return { providers, loading, dormant, reload };
}

// Convenience for the Video Studio (and any future consumer): the enabled
// providers for a capability, ready for a Select. Used by U6/W9's BYO-key picker.
export function useIntegrations(capability: Capability) {
    const { providers, loading, dormant } = useProviders({ capability });
    const enabled = providers.filter((p) => p.is_enabled);
    return { providers: enabled, loading, dormant };
}

// Health polling hook (30s — health is cheap-but-not-free, NOT the 5s key-pool poll).
export function useProviderHealth(opts?: { admin?: boolean; capability?: string }) {
    const { admin = false, capability = "" } = opts || {};
    const [rows, setRows] = useState<HealthRow[]>([]);
    const [dormant, setDormant] = useState(false);
    const timer = useRef<ReturnType<typeof setInterval> | null>(null);

    useEffect(() => {
        let alive = true;
        const poll = async () => {
            const res = admin ? await adminHealth() : await getProvidersHealth(capability);
            if (!alive) return;
            setRows(res.rows);
            setDormant(res.disabled);
        };
        poll();
        timer.current = setInterval(poll, 30_000);
        return () => {
            alive = false;
            if (timer.current) clearInterval(timer.current);
        };
    }, [admin, capability]);

    return { rows, dormant };
}

// ---- display dictionaries (single source of truth for chips/labels) ---------
export const CAPABILITY_LABEL: Record<Capability, string> = {
    text_gen: "Text",
    image_gen: "Image",
    video_gen: "Video",
    tts: "TTS",
    stt: "STT",
    embed: "Embed",
    rerank: "Rerank",
    tool_call: "Tools",
    webhook: "Webhook",
    storage: "Storage",
};

export const ALL_CAPABILITIES: Capability[] = [
    "text_gen",
    "image_gen",
    "video_gen",
    "tts",
    "stt",
    "embed",
    "rerank",
    "tool_call",
    "webhook",
    "storage",
];

export const PROVIDER_TYPE_LABEL: Record<ProviderType, string> = {
    hosted_api: "Hosted API",
    self_hosted: "Self-hosted",
    tool_connector: "Connector",
    platform_builtin: "Built-in",
};

export const AUTH_SCHEME_LABEL: Record<AuthScheme, string> = {
    bearer: "Bearer token",
    api_key_header: "API-key header",
    api_key_query: "API-key query",
    basic: "Basic auth",
    oauth2_cc: "OAuth2 (client credentials)",
    none: "No auth",
};

export const TRANSFORM_LABEL: Record<TransformType, string> = {
    openai_compat: "OpenAI-compatible (zero-config)",
    named_provider: "Named provider",
    custom_field_map: "Custom field-map",
};

// Self-hosted server presets (RESEARCH[self-hosted-serving]) → default health path.
export const SELFHOST_PRESETS: { id: number; name: string; kind: string; health: string }[] = [
    { id: 0, name: "OpenAI-compatible (vLLM / Ollama / TGI v1.4+)", kind: "openai_compat", health: "/health" },
    { id: 1, name: "ComfyUI (Wan / LTX / Mochi video)", kind: "comfyui", health: "/queue" },
    { id: 2, name: "Automatic1111 (Stable Diffusion)", kind: "a1111", health: "/sdapi/v1/sd-models" },
    { id: 3, name: "TGI (native, legacy)", kind: "tgi", health: "/health" },
    { id: 4, name: "Generic (field-map)", kind: "generic", health: "/health" },
];

// micro-USD → a readable "$0.05 / sec" cost label.
export function fmtCost(micros?: number | null, unit?: string | null): string {
    if (micros == null) return "—";
    const usd = micros / 1_000_000;
    const u = unit ? unit.replace("per_", "/ ").replace("_", " ") : "";
    return `$${usd < 0.01 ? usd.toFixed(4) : usd.toFixed(2)} ${u}`.trim();
}
