// WhatsApp Media Library — DORMANT-SAFE client (W16).
//
// Talks to the voice_ops/whatsapp media seam at /api/whatsapp/media. Like waapi.ts,
// EVERY call DEGRADES CLEANLY: a 404 / 503 / network failure / not_configured body
// resolves to a benign result — NEVER throws, NEVER error-walls. Until the backend
// route is mounted, uploads still preview LOCALLY (object URL) so the founder can
// build + preview a campaign today; saved-asset reuse activates the moment the API
// lands (zero UI change — the same `listMedia()`/`uploadMedia()` calls go live).

import { BASE, authHeaders } from "@/lib/api";
import { type WaMedia, type WaMediaKind } from "./types";

const MEDIA_BASE = `${BASE}/whatsapp/media`;

// Per-kind client-side validation mirrors the backend MediaLibrary.validate
// rules (MIME prefix + size ceiling) so a bad file is caught before any upload.
const KIND_RULES: Record<WaMediaKind, { accept: string; maxMB: number; mimes: string[] }> = {
    banner: { accept: "image/*", maxMB: 5, mimes: ["image/"] },
    image: { accept: "image/*", maxMB: 5, mimes: ["image/"] },
    video: { accept: "video/*", maxMB: 16, mimes: ["video/"] },
    brochure: { accept: "application/pdf", maxMB: 100, mimes: ["application/pdf"] },
};

export function acceptFor(kind: WaMediaKind): string {
    return KIND_RULES[kind].accept;
}

// Returns "" if valid, else a friendly error string.
export function validateFile(kind: WaMediaKind, file: File): string {
    const r = KIND_RULES[kind];
    const ct = (file.type || "").split(";")[0].trim().toLowerCase();
    const okMime = r.mimes.some((m) => (m.endsWith("/") ? ct.startsWith(m) : ct === m));
    if (!okMime) return `${kind} must be ${r.accept} (got ${ct || "unknown"})`;
    if (file.size === 0) return "empty file";
    if (file.size > r.maxMB * 1024 * 1024) return `file too large (max ${r.maxMB}MB)`;
    return "";
}

// A purely-local WaMedia from a freshly-picked File (preview-only, not persisted).
export function localMediaFromFile(kind: WaMediaKind, file: File): WaMedia {
    return {
        id: `local_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
        kind,
        title: file.name,
        url: typeof URL !== "undefined" ? URL.createObjectURL(file) : "",
        content_type: file.type,
        size_bytes: file.size,
        local: true,
        source: "uploaded",
    };
}

// List saved media (optionally one kind). Dormant-safe: [] on any failure.
export async function listMedia(kind?: WaMediaKind): Promise<{ configured: boolean; media: WaMedia[] }> {
    try {
        const q = kind ? `?kind=${encodeURIComponent(kind)}` : "";
        const res = await fetch(`${MEDIA_BASE}${q}`, { headers: { ...authHeaders() } });
        if (!res.ok) return { configured: false, media: [] };
        const body = await res.json().catch(() => null);
        if (!body || body.status === "not_configured") return { configured: false, media: [] };
        const media: WaMedia[] = Array.isArray(body.media) ? body.media : Array.isArray(body) ? body : [];
        return { configured: true, media };
    } catch {
        return { configured: false, media: [] };
    }
}

// Upload a file to the saved library. Dormant-safe: on any failure we still return
// a LOCAL preview asset so the builder keeps working; `configured:false` tells the
// UI it wasn't persisted (a "saved when the engine connects" hint).
export async function uploadMedia(
    kind: WaMediaKind,
    file: File,
    opts?: { title?: string; campaign_id?: string }
): Promise<{ configured: boolean; asset: WaMedia; error?: string }> {
    const localErr = validateFile(kind, file);
    if (localErr) return { configured: false, asset: localMediaFromFile(kind, file), error: localErr };
    try {
        const fd = new FormData();
        fd.append("kind", kind);
        fd.append("file", file);
        if (opts?.title) fd.append("title", opts.title);
        if (opts?.campaign_id) fd.append("campaign_id", opts.campaign_id);
        const res = await fetch(MEDIA_BASE, { method: "POST", headers: { ...authHeaders() }, body: fd });
        if (!res.ok) return { configured: false, asset: localMediaFromFile(kind, file) };
        const body = await res.json().catch(() => null);
        if (!body || body.status === "not_configured" || body.ok === false) {
            return { configured: false, asset: localMediaFromFile(kind, file), error: body?.error };
        }
        const a = body.asset || body;
        return { configured: true, asset: { ...localMediaFromFile(kind, file), ...a, local: false } };
    } catch {
        return { configured: false, asset: localMediaFromFile(kind, file) };
    }
}

// Delete a saved asset (no-op-safe when dormant).
export async function deleteMedia(id: string): Promise<boolean> {
    try {
        const res = await fetch(`${MEDIA_BASE}/${encodeURIComponent(id)}`, {
            method: "DELETE",
            headers: { ...authHeaders() },
        });
        return res.ok;
    } catch {
        return false;
    }
}

export function prettyBytes(n?: number): string {
    if (!n) return "—";
    if (n < 1024) return `${n} B`;
    if (n < 1024 * 1024) return `${Math.round(n / 1024)} KB`;
    return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}
