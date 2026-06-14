"use client";

// ============================================================================
// lib/video.ts — the typed client for the VIDEO STUDIO upper orchestrator,
// mounted in caller.py under `FEATURE_VIDEO_STUDIO` at `/creative/video/*`
// (verified vs droplet_work/creative/video_studio/endpoints.py).
//
// The panel proxies caller.py at `/api`, so every call here is
// `/api/creative/video/*`, auth = the same `X-Auth` header the rest of the
// panel uses (lib/api.ts convention).
//
// DORMANT-SAFE by design — the WHOLE surface 404s when the flag is OFF (default).
// Reads resolve to a calm empty/`not_configured` shape (never an error wall,
// never a logout — only lib/api.ts owns the session). Mutations surface a typed
// VideoError so the studio can show a precise reason (over-budget / paid-gate /
// not-configured). The render itself is async by construction → ZERO added to the
// voice loop; the engine never spends without a wallet hold + the 1-paid-test gate.
//
// COST-TRUTH (master plan §6/§13b-H1): the COMPOSITE tier is the $0-gen-key floor
// (Sarvam TTS, metered honestly, never silent). Hosted-gen + ElevenLabs are PAID,
// gated to a 1-paid-test choke on first use. The UI labels every paid path.
// ============================================================================

import { useCallback, useEffect, useRef, useState } from "react";

const BASE =
    typeof process !== "undefined" && process.env.NEXT_PUBLIC_API_BASE
        ? process.env.NEXT_PUBLIC_API_BASE
        : "/api";

const VIDEO_BASE = `${BASE}/creative/video`;

function getToken(): string | null {
    if (typeof window === "undefined") return null;
    return localStorage.getItem("famit_token");
}

function authHeaders(extra?: Record<string, string>): HeadersInit {
    const token = getToken();
    return { ...(token ? { "X-Auth": token } : {}), ...(extra || {}) };
}

/** A mutating call's typed failure (paid-gate / over-budget / dormant / generic). */
export class VideoError extends Error {
    status: number;
    code: string; // not_configured | paid_gate | over_budget | forbidden | generic
    body: Record<string, unknown>;
    constructor(status: number, code: string, message: string, body: Record<string, unknown> = {}) {
        super(message);
        this.name = "VideoError";
        this.status = status;
        this.code = code;
        this.body = body;
    }
}

async function readBody(res: Response): Promise<Record<string, unknown>> {
    try {
        return (await res.json()) as Record<string, unknown>;
    } catch {
        return {};
    }
}

// Map a status string the BE returns (e.g. "error:no_such_batch", "not_configured")
// onto a typed VideoError code + a human message.
function classify(status: number, body: Record<string, unknown>, fallback: string): VideoError {
    const raw = String(body.status || body.error || "");
    const msg =
        (typeof body.message === "string" && body.message) ||
        humanizeVideo(raw) ||
        fallback;
    if (status === 404 || raw === "not_configured") return new VideoError(status, "not_configured", msg, body);
    if (status === 402 || raw.includes("over_budget") || raw.includes("cap")) return new VideoError(status, "over_budget", msg, body);
    if (status === 403) return new VideoError(status, "forbidden", msg, body);
    if (raw.includes("paid") || raw.includes("gate")) return new VideoError(status, "paid_gate", msg, body);
    return new VideoError(status, "generic", msg, body);
}

export function humanizeVideo(raw: string): string {
    if (!raw) return "";
    if (raw === "not_configured")
        return "Video Studio isn't configured yet — add a provider key or enable the free composite tier.";
    if (raw.startsWith("error:no_such_batch")) return "That batch no longer exists.";
    if (raw.startsWith("error:no_such_asset")) return "That video no longer exists.";
    if (raw.startsWith("error:bad_status")) return "That isn't a valid status change.";
    if (raw.includes("over_budget")) return "This batch would exceed your daily video budget.";
    if (raw.startsWith("error:")) return "Something went wrong. Please try again.";
    return "";
}

// ---- TYPES (match service._shape + the job records) ------------------------

export type VideoTier = "composite" | "ai_motion" | "premium";
export type TtsProvider = "sarvam" | "elevenlabs";
export type VideoAspect = "9:16" | "1:1" | "16:9";

/** GET /creative/video/campaigns — the campaign dropdown source. */
export type VideoCampaign = { id: string; name: string };

/** One render job inside a batch (the variant card binds to this). */
export type VideoJob = {
    job_id?: string;
    id?: string;
    variant_key?: string; // the angle: pain_point | social_proof | …
    angle?: string;
    status?: string; // queued | running | succeeded | failed | cancelled
    provider?: string; // compose | fal | …
    tier?: string;
    progress?: number; // 0..100
    render_url?: string; // presigned MP4 when succeeded
    poster_url?: string;
    duration_s?: number;
    with_audio?: boolean;
    library_asset_id?: string; // set once the bridge lands it in ai_asset_*
    error?: string;
    hook?: string; // the script hook line (preview copy)
};

/** A batch record (propose / status). `not_configured` is the dormant signal. */
export type VideoBatch = {
    status: string; // ok | awaiting_approval | rendering | complete | not_configured | error:*
    batch_id: string;
    configured?: boolean;
    estimated_cost_usd?: string;
    scripts?: { variant_key?: string; angle?: string; hook?: string; script?: string; cta?: string; lang?: string }[];
    jobs?: VideoJob[];
    asset_ids?: string[];
    approval?: { required?: boolean; approved?: boolean; reason?: string; forced_size?: number; auto_approve?: boolean };
    error?: string;
};

export type VideoStatus = {
    /** the studio surface is mounted + configured (composite floor OR a gen-key) */
    enabled: boolean;
    configured?: boolean;
    /** the composite ($0-gen-key) floor is available */
    composite?: boolean;
};

export type ProposeBody = {
    campaign_id: string;
    size?: number; // variant count
    with_audio?: boolean;
    aspect?: VideoAspect | string;
    route?: string; // hook | offer | …
    duration_s?: number;
    tier?: VideoTier;
    tts_provider?: TtsProvider;
    idempotency_key?: string;
};

// ---- CALLS -----------------------------------------------------------------

/** A dormancy probe. There's no dedicated /status route on the studio (the whole
 *  surface 404s when off), so we probe `GET /campaigns`: 200 → enabled, 404 →
 *  dormant. Never throws. We also surface the composite floor via a propose
 *  dry-read is avoided (no spend) — composite availability is inferred from a
 *  batch's `configured` once one exists; default the floor to true when enabled. */
export async function getVideoStatus(): Promise<VideoStatus> {
    try {
        const res = await fetch(`${VIDEO_BASE}/campaigns`, {
            headers: authHeaders(),
            cache: "no-store",
        });
        if (res.status === 404) return { enabled: false };
        if (res.status === 401) return { enabled: false }; // soft — never a logout
        if (!res.ok) return { enabled: false };
        return { enabled: true, composite: true };
    } catch {
        return { enabled: false };
    }
}

/** GET /creative/video/campaigns — dropdown source. Dormant → empty. */
export async function listVideoCampaigns(): Promise<VideoCampaign[]> {
    try {
        const res = await fetch(`${VIDEO_BASE}/campaigns`, { headers: authHeaders() });
        if (!res.ok) return [];
        const data = (await res.json()) as { campaigns?: VideoCampaign[] };
        return Array.isArray(data.campaigns) ? data.campaigns : [];
    } catch {
        return [];
    }
}

/** POST /creative/video/batches — propose (build + gate) a batch. Throws VideoError
 *  on a non-2xx OR a `not_configured`/`error:*` shape (the BE returns 200 with a
 *  status field, so we inspect the body too). */
export async function proposeBatch(body: ProposeBody): Promise<VideoBatch> {
    const payload: Record<string, unknown> = {
        campaign_id: body.campaign_id,
        size: body.size,
        with_audio: body.with_audio ?? true,
        aspect: body.aspect || "9:16",
        route: body.route || "hook",
        tier: body.tier || "composite",
        tts_provider: body.tts_provider || "sarvam",
        idempotency_key: body.idempotency_key || cryptoRandom(),
    };
    if (body.duration_s != null) payload.duration_s = body.duration_s;
    const res = await fetch(`${VIDEO_BASE}/batches`, {
        method: "POST",
        headers: authHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify(payload),
    });
    const data = await readBody(res);
    if (!res.ok) throw classify(res.status, data, "Couldn't start that batch.");
    const status = String(data.status || "");
    if (status === "not_configured" || status.startsWith("error")) {
        throw classify(status === "not_configured" ? 404 : 422, data, "Couldn't start that batch.");
    }
    return data as VideoBatch;
}

/** GET /creative/video/batches/{id} — poll one batch. Dormant → not_configured shape. */
export async function getBatch(batchId: string): Promise<VideoBatch> {
    try {
        const res = await fetch(`${VIDEO_BASE}/batches/${encodeURIComponent(batchId)}`, {
            headers: authHeaders(),
        });
        if (res.status === 404) return { status: "not_configured", batch_id: batchId, configured: false };
        if (!res.ok) return { status: "error", batch_id: batchId };
        return (await res.json()) as VideoBatch;
    } catch {
        return { status: "error", batch_id: batchId };
    }
}

/** GET /creative/video/batches — list this tenant's batches. Dormant → empty. */
export async function listBatches(): Promise<VideoBatch[]> {
    try {
        const res = await fetch(`${VIDEO_BASE}/batches`, { headers: authHeaders() });
        if (!res.ok) return [];
        const data = (await res.json()) as { batches?: VideoBatch[] };
        return Array.isArray(data.batches) ? data.batches : [];
    } catch {
        return [];
    }
}

async function batchAction(batchId: string, action: "approve" | "reject" | "cancel"): Promise<VideoBatch> {
    const res = await fetch(`${VIDEO_BASE}/batches/${encodeURIComponent(batchId)}/${action}`, {
        method: "POST",
        headers: authHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({}),
    });
    const data = await readBody(res);
    if (!res.ok) throw classify(res.status, data, `Couldn't ${action} that batch.`);
    return data as VideoBatch;
}

export const approveBatch = (id: string) => batchAction(id, "approve");
export const rejectBatch = (id: string) => batchAction(id, "reject");
export const cancelBatch = (id: string) => batchAction(id, "cancel");

/** POST /creative/video/collect/{id} — idempotent poll → land finished videos in
 *  the live ai_asset_* library (the bridge §5). Best-effort; dormant-safe. */
export async function collectBatch(batchId: string): Promise<VideoBatch> {
    try {
        const res = await fetch(`${VIDEO_BASE}/collect/${encodeURIComponent(batchId)}`, {
            method: "POST",
            headers: authHeaders(),
        });
        if (!res.ok) return { status: "error", batch_id: batchId };
        return (await res.json()) as VideoBatch;
    } catch {
        return { status: "error", batch_id: batchId };
    }
}

/** POST /creative/video/assets/{id}/promote — winner | paused | trashed. */
export async function promoteVideo(assetId: string, status = "winner"): Promise<{ status: string }> {
    const res = await fetch(`${VIDEO_BASE}/assets/${encodeURIComponent(assetId)}/promote`, {
        method: "POST",
        headers: authHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({ status }),
    });
    const data = await readBody(res);
    if (!res.ok) throw classify(res.status, data, "Couldn't update that video.");
    return data as { status: string };
}

// ---- HOOKS -----------------------------------------------------------------

/** The studio dormancy probe (mirrors useAssetStatus). */
export function useVideoStatus() {
    const [status, setStatus] = useState<VideoStatus | null>(null);
    const [loading, setLoading] = useState(true);
    useEffect(() => {
        let active = true;
        getVideoStatus()
            .then((s) => active && setStatus(s))
            .finally(() => active && setLoading(false));
        return () => {
            active = false;
        };
    }, []);
    return { status, enabled: !!status?.enabled, composite: !!status?.composite, loading };
}

/** Poll an in-flight batch every `interval` ms until it reaches a terminal state,
 *  calling `collect` opportunistically so finished videos land in the library.
 *  Stops on terminal (complete/error/cancelled) or when batchId clears. */
export function useBatchPoll(batchId: string | null, interval = 2500) {
    const [batch, setBatch] = useState<VideoBatch | null>(null);
    const collected = useRef(false);

    useEffect(() => {
        collected.current = false;
        setBatch(null);
        if (!batchId) return;
        let active = true;
        const terminal = (s: string) =>
            s === "complete" || s === "completed" || s === "done" || s.startsWith("error") || s === "cancelled" || s === "rejected";

        const tick = async () => {
            const b = await getBatch(batchId);
            if (!active) return;
            setBatch(b);
            const done = b.jobs?.filter((j) => (j.status || "").toLowerCase() === "succeeded").length || 0;
            const total = b.jobs?.length || 0;
            // once at least one job is succeeded, collect so the library bridge fires
            if (done > 0 && !collected.current) {
                collected.current = true;
                await collectBatch(batchId);
            }
            if (terminal((b.status || "").toLowerCase()) || (total > 0 && done === total)) {
                if (active) await collectBatch(batchId); // final reconcile
                return "stop";
            }
        };

        let timer: ReturnType<typeof setTimeout>;
        const loop = async () => {
            const r = await tick();
            if (active && r !== "stop") timer = setTimeout(loop, interval);
        };
        loop();
        return () => {
            active = false;
            clearTimeout(timer!);
        };
    }, [batchId, interval]);

    return batch;
}

// ---- helpers ---------------------------------------------------------------

function cryptoRandom(): string {
    try {
        if (typeof crypto !== "undefined" && crypto.randomUUID) return crypto.randomUUID();
    } catch {
        /* no crypto */
    }
    return `vk_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 10)}`;
}

/** A friendly label for a batch status. */
export function batchStatusLabel(status?: string): string {
    switch ((status || "").toLowerCase()) {
        case "awaiting_approval":
            return "Awaiting approval";
        case "rendering":
            return "Rendering";
        case "complete":
        case "completed":
            return "Complete";
        case "not_configured":
            return "Not configured";
        case "ok":
            return "Ready";
        default:
            return (status || "").startsWith("error") ? "Failed" : status || "—";
    }
}

/** The angle/variant key → a human label (mirrors lib/assets angleLabel). */
export function variantLabel(key?: string): string {
    if (!key) return "Variant";
    return key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}
