// lib/pmodel.ts — API client + shared types for the 2D→3D Property Studio.
// Auth mirrors lib/api.ts (X-Auth header, famit_token in localStorage). All errors
// resolve softly (dormant) so the studio never error-walls.

const BASE =
    typeof process !== "undefined" && process.env.NEXT_PUBLIC_API_BASE
        ? `${process.env.NEXT_PUBLIC_API_BASE}/pmodel`
        : "/api/pmodel";

function token(): string | null {
    return typeof window === "undefined" ? null : localStorage.getItem("famit_token");
}
function auth(): HeadersInit {
    const t = token();
    return t ? { "X-Auth": t } : {};
}

// ---- shared geometry types (mirror droplet_work/pmodel/builder.py SceneSpec) ----
export type Vec2 = [number, number];
export type Vec3 = [number, number, number];

export interface WallPanel {
    position: Vec3;
    size: Vec3; // [length, height, thickness]
    rotationY: number;
    kind: "solid" | "sill" | "header" | string;
}
export interface Wall {
    panels: WallPanel[];
    height: number;
}
export interface Floor {
    name: string;
    type: string;
    material: string;
    area_sqm: number;
    polygon: Vec2[];
    center: Vec2;
    y: number;
}
export interface Opening {
    kind: "door" | "window" | "arch" | string;
    position: Vec3;
    rotationY: number;
    width: number;
    height: number;
    sill: number;
    thickness: number;
}
export interface Furniture {
    kind: string;
    position: Vec3;
    rotationY: number;
    room: string;
    glb?: string; // presigned generated-mesh url (only when assets3d is enabled)
}
export interface SceneLight {
    kind: "sun" | "ceiling" | string;
    position: Vec3;
    intensity: number;
    color: string;
}
export interface CameraWaypoint {
    name: string;
    position: Vec3;
    target: Vec3;
}
export interface SceneSpec {
    units: string;
    meta: {
        title: string;
        area_sqm: number;
        area_sqft: number;
        rooms: number;
        bedrooms: number;
        baths: number;
        eye_height: number;
    };
    bounds: { min: Vec2; max: Vec2; width: number; depth: number; center: Vec2 };
    palette: {
        wall: string;
        trim: string;
        glass: string;
        door: string;
        floor: Record<string, string>;
    };
    walls: Wall[];
    floors: Floor[];
    openings: Opening[];
    furniture: Furniture[];
    lights: SceneLight[];
    cameras: { dollhouse: { position: Vec3; target: Vec3 }; waypoints: CameraWaypoint[] };
}

export interface ProjectSummary {
    id: string;
    name: string;
    source: string;
    state: string;
    public: boolean;
    share_token: string;
    rooms: number;
    area_sqft: number;
    created_at: number;
    updated_at: number;
}
export interface ProjectFull extends ProjectSummary {
    schema: unknown;
    scene: SceneSpec | null;
    plan_key: string;
}
export interface BuildResult {
    id: string;
    state: string;
    scene: SceneSpec;
    name: string;
    share_token: string;
}
export interface SampleInfo {
    kind: string;
    title: string;
    desc: string;
}
export interface ShareData {
    name: string;
    scene: SceneSpec;
    plan_url: string;
    branding: { brand: string; cta_label: string; cta_href: string; tagline: string };
}

export class PModelError extends Error {
    code: string;
    constructor(code: string, message?: string) {
        super(message || code);
        this.code = code;
    }
}

async function jsonOrThrow(res: Response, fallback = "request_failed") {
    if (res.status === 503) {
        const body = await res.json().catch(() => ({}));
        throw new PModelError(body?.error || "not_configured");
    }
    if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new PModelError(body?.error || fallback);
    }
    return res.json();
}

// ---- API ----
export interface StudioStatus {
    enabled: boolean;
    vision: boolean;
    vision_provider?: string;
    assets3d?: boolean;
    hdrender?: boolean;
}
export async function getStatus(): Promise<StudioStatus> {
    try {
        const r = await fetch(`${BASE}/status`, { headers: auth(), cache: "no-store" });
        if (!r.ok) return { enabled: false, vision: false };
        return r.json();
    } catch {
        return { enabled: false, vision: false };
    }
}

// Generate realistic GLB meshes for the project's furniture (dormant unless the
// assets3d backend is configured). Returns a summary.
export async function generateFurniture(id: string): Promise<{ enabled: boolean; generated: number }> {
    const r = await fetch(`${BASE}/projects/${encodeURIComponent(id)}/furniture/generate`, {
        method: "POST",
        headers: auth(),
    });
    return jsonOrThrow(r, "assets3d_failed");
}

export interface RenderJob {
    job?: string;
    state: "queued" | "running" | "done" | "failed" | "unknown";
    url?: string;
    error?: string;
}
export async function renderHd(id: string): Promise<RenderJob> {
    const r = await fetch(`${BASE}/projects/${encodeURIComponent(id)}/render`, {
        method: "POST",
        headers: auth(),
    });
    return jsonOrThrow(r, "hdrender_failed");
}
export async function renderStatus(job: string): Promise<RenderJob> {
    const r = await fetch(`${BASE}/render/${encodeURIComponent(job)}`, { headers: auth() });
    if (!r.ok) return { state: "unknown" };
    return r.json();
}

export async function getSamples(): Promise<SampleInfo[]> {
    try {
        const r = await fetch(`${BASE}/samples`, { headers: auth() });
        if (!r.ok) return [];
        return (await r.json()).samples ?? [];
    } catch {
        return [];
    }
}

export async function listProjects(): Promise<ProjectSummary[]> {
    const r = await fetch(`${BASE}/projects`, { headers: auth() });
    if (!r.ok) return [];
    return (await r.json()).projects ?? [];
}

export async function getProject(id: string): Promise<ProjectFull> {
    const r = await fetch(`${BASE}/projects/${encodeURIComponent(id)}`, { headers: auth() });
    return jsonOrThrow(r, "not_found");
}

export async function createProject(name: string): Promise<ProjectSummary> {
    const fd = new FormData();
    fd.append("name", name);
    const r = await fetch(`${BASE}/projects`, { method: "POST", headers: auth(), body: fd });
    return jsonOrThrow(r, "create_failed");
}

export async function deleteProject(id: string): Promise<void> {
    await fetch(`${BASE}/projects/${encodeURIComponent(id)}`, { method: "DELETE", headers: auth() });
}

export async function renameProject(id: string, name: string): Promise<ProjectSummary> {
    const fd = new FormData();
    fd.append("name", name);
    const r = await fetch(`${BASE}/projects/${encodeURIComponent(id)}/rename`, {
        method: "POST",
        headers: auth(),
        body: fd,
    });
    return jsonOrThrow(r, "rename_failed");
}

export async function analyzeImage(id: string, plan: File): Promise<BuildResult> {
    const fd = new FormData();
    fd.append("plan", plan); // key MUST be 'plan' (matches router)
    const r = await fetch(`${BASE}/projects/${encodeURIComponent(id)}/analyze`, {
        method: "POST",
        headers: auth(), // NO Content-Type on multipart — browser sets the boundary
        body: fd,
    });
    return jsonOrThrow(r, "analyze_failed");
}

export async function buildFromText(id: string, prompt: string): Promise<BuildResult> {
    const fd = new FormData();
    fd.append("prompt", prompt);
    const r = await fetch(`${BASE}/projects/${encodeURIComponent(id)}/from-text`, {
        method: "POST",
        headers: auth(),
        body: fd,
    });
    return jsonOrThrow(r, "analyze_failed");
}

export async function buildFromSample(id: string, kind: string): Promise<BuildResult> {
    const fd = new FormData();
    fd.append("kind", kind);
    const r = await fetch(`${BASE}/projects/${encodeURIComponent(id)}/sample`, {
        method: "POST",
        headers: auth(),
        body: fd,
    });
    return jsonOrThrow(r, "sample_failed");
}

export async function setShare(
    id: string,
    isPublic: boolean,
): Promise<{ public: boolean; share_token: string; path: string }> {
    const fd = new FormData();
    fd.append("public", isPublic ? "true" : "false");
    const r = await fetch(`${BASE}/projects/${encodeURIComponent(id)}/share`, {
        method: "POST",
        headers: auth(),
        body: fd,
    });
    return jsonOrThrow(r, "share_failed");
}

// Public — no auth. Used by the customer share page.
export async function getShare(token: string): Promise<ShareData> {
    const r = await fetch(`${BASE}/share/${encodeURIComponent(token)}`);
    return jsonOrThrow(r, "not_found");
}

// Convenience: create a project then build it from a sample in one call.
export async function quickSample(name: string, kind: string): Promise<BuildResult> {
    const p = await createProject(name);
    return buildFromSample(p.id, kind);
}
