// ============================================================
// AI ASSET SERVICE client — the typed /api/assets/* binding for Creative Studio.
//
// The whole Creative Studio frontend (S1–S11 + L1–L10) talks to ONE backend: the
// AI Asset Service, LIVE at backend :8310, reached via nginx `location /api/assets/`.
// The surface is FROZEN (design/asset-service-backend.md §8 / cs-workspace-final.md §16):
//   GET  /status                       — the ONLY un-gated route (dormancy probe)
//   GET  /providers                    — model registry (Advanced model selector)
//   POST /generate                     — {job_id,state,est_cost}; 402 over_budget; needs_input
//   GET  /jobs · /jobs/{id} · /jobs/{id}/stream(SSE) · POST /jobs/{id}/cancel
//   GET  /assets?<facets>              — newest-first, tenant-scoped, paginated
//   GET  /assets/{id}                  — current+all versions, score, status, usage, metrics
//   GET  /assets/{id}/raw              — bytes (local_path never exposed)
//   POST /assets/{id}/edit|/regenerate|/approve|/reject|/attach|/attach-whatsapp
//   POST /variation-from-upload (multipart)
//   GET/POST/PUT /brand-kits  (+ POST /brand-kits/extract — F1)
//
// EVERY route except /status is 503-gated by AIASSET_ENABLED. So this client is
// DORMANT-SAFE: a 503/404 never throws an error-wall — it resolves to a calm
// "disabled" shape so each screen renders its dormant state. Tenant is ALWAYS
// token-derived server-side (never sent in the body); by-id routes 404 on
// cross-tenant. The UI never sees a provider key.
//
// Conventions mirror lib/api.ts: same BASE, same X-Auth header, same handle401.
// ============================================================

const ASSET_BASE =
    typeof process !== "undefined" && process.env.NEXT_PUBLIC_API_BASE
        ? `${process.env.NEXT_PUBLIC_API_BASE}/assets`
        : "/api/assets";

function getToken(): string | null {
    if (typeof window === "undefined") return null;
    return localStorage.getItem("famit_token");
}

function authHeaders(): HeadersInit {
    const token = getToken();
    return token ? { "X-Auth": token } : {};
}

// The AI Asset Service (:8310) is an OPTIONAL, dormant-by-design surface. A 401
// from it means the asset service couldn't authenticate the panel's token — it
// must NEVER nuke the whole-panel session or redirect to /login. Only lib/api.ts
// (the MONOLITH client, the source of truth for the session) is allowed to log
// out. So this is a deliberate NO-OP: a 401 is treated as a soft failure and the
// existing per-call try/catch fallbacks resolve it to the calm dormant/empty
// shape (same as a 503/404). See design/fix-creative-logout.md §4b.
async function handle401(_res: Response): Promise<void> {
    /* intentionally empty — asset-service auth failures are soft, never a logout */
}

/** Sentinel thrown by mutating calls when the surface is dormant (503) so callers
 *  can show the calm "activate your workspace" banner instead of a raw error. */
export class AssetDormantError extends Error {
    constructor(msg = "Creative Studio isn't enabled for this workspace yet.") {
        super(msg);
        this.name = "AssetDormantError";
    }
}

/** A mutating call's 402 over-budget / 409 needs-approval shape, surfaced inline. */
export class AssetGuardError extends Error {
    status: number;
    code: string; // over_budget | needs_input | not_approved | blocked | generic
    body: Record<string, unknown>;
    constructor(status: number, code: string, message: string, body: Record<string, unknown>) {
        super(message);
        this.name = "AssetGuardError";
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

// Map a non-OK mutating response onto a typed guard/dormant error.
async function throwAsset(res: Response, fallback: string): Promise<never> {
    if (res.status === 503) throw new AssetDormantError();
    const body = await readBody(res);
    const msg =
        (typeof body.message === "string" && body.message) ||
        (typeof body.error === "string" && body.error) ||
        fallback;
    if (res.status === 402) throw new AssetGuardError(402, "over_budget", msg, body);
    if (res.status === 409) throw new AssetGuardError(409, "not_approved", msg, body);
    if (res.status === 422) throw new AssetGuardError(422, "needs_input", msg, body);
    throw new AssetGuardError(res.status, "generic", msg, body);
}

// ---- TYPES ---------------------------------------------------------------

/** GET /status — the un-gated dormancy probe (every screen calls this first). */
export type AssetStatus = {
    enabled: boolean;
    schema_ready?: boolean;
    providers?: number;
    wallet?: { balance_minor?: number; currency?: string };
    hatchet?: boolean;
};

/** GET /providers — the model registry (Advanced "Model" select; "Auto" default). */
export type AssetProvider = {
    provider_id: string;
    display_name: string;
    capabilities?: string[];
    cost_minor?: number;
};

export type AssetAngle =
    | "price"
    | "location"
    | "emotion"
    | "urgency"
    | "trust"
    | "problem_solution"
    | "benefit"
    | "offer"
    | "retargeting"
    | "comparison"
    | string;

export type AssetStatusValue =
    | "draft"
    | "needs_review"
    | "approved"
    | "rejected"
    | "used"
    | "archived"
    | string;

export type AssetScore = {
    overall?: number; // 0–100
    sub?: { label: string; value: number }[];
    why?: string;
};

export type AssetUsage = {
    channel: string; // whatsapp | meta_ads | landing | workflow
    ref_id?: string;
    label?: string;
    metrics?: Record<string, number>;
    at?: string;
};

export type AssetVersion = {
    id: string;
    version_no: number;
    thumb_url?: string;
    url?: string;
    edit_instruction?: string; // the NL edit that spawned it ("make it premium")
    parent_version_id?: string | null;
    model?: string;
    cost_minor?: number;
    created_at?: string;
    is_current?: boolean;
};

/** One asset row (card + detail). Optional-rich so a partial backend degrades. */
export type Asset = {
    id: string;
    campaign_id?: string;
    campaign_name?: string;
    kind?: string; // banner | image | social | offer | poster | product | logo
    platform?: string; // meta | whatsapp | ig_story | google | carousel | hero
    size?: string;
    angle?: AssetAngle;
    headline?: string;
    subheadline?: string;
    cta?: string;
    language?: string;
    status?: AssetStatusValue;
    score?: AssetScore;
    thumb_url?: string;
    url?: string;
    model?: string;
    cost_minor?: number;
    created_at?: string;
    source?: "generated" | "uploaded" | string;
    tags?: string[];
    versions?: AssetVersion[];
    current_version_id?: string;
    usage?: AssetUsage[];
    metrics?: Record<string, number>;
    hypothesis?: string;
};

export type AssetListPage = {
    assets: Asset[];
    total: number;
    limit: number;
    offset: number;
};

/** The facet query for GET /assets (cs-asset-library L2). */
export type AssetQuery = {
    limit?: number;
    offset?: number;
    campaign?: string;
    platform?: string;
    kind?: string;
    status?: string;
    angle?: string;
    size?: string;
    from?: string;
    to?: string;
    sort?: string; // newest | oldest | best_score | best_ctr | most_used | cheapest
    q?: string;
    winners?: boolean;
};

export type GenerateBody = {
    campaign_id?: string;
    platform: string;
    asset_type: string;
    count: number;
    instruction: string;
    language?: string;
    model?: string;
    brand_kit_id?: string;
    idempotency_key?: string;
    /** The vendor's own raw image prompt. When present the backend SKIPS the
     *  Stage-1 LLM prompt-builder and sends this text VERBATIM to the image AI
     *  (ai_asset prompt_builder short-circuit). Blank → auto campaign prompt. */
    custom_prompt?: string;
};

export type GenerateResult = {
    job_id: string;
    state: string; // queued | running | over_budget | needs_input
    est_cost?: number; // credits estimate (master §34)
    est_cost_minor?: number;
    clarify?: { id: string; question: string }[]; // needs_input chips
};

export type JobStatus = {
    job_id: string;
    state: string; // queued | running | streaming | succeeded | partial | failed | cancelled
    phase?: string;
    progress?: { total: number; done: number };
    actual_cost_minor?: number;
    asset_ids?: string[];
};

/** GET /brand-kits — the brand memory the AI honours. */
export type BrandKit = {
    id: string;
    name?: string;
    logo_url?: string;
    palette?: string[];
    tone?: string[];
    language_pref?: string;
    default_cta?: string[];
    do_not_use?: { words?: string[]; styles?: string[]; colors?: string[] };
    best_style?: string[];
};

/** The campaign-context snapshot the AI resolved (S3 trust surface). Each fact is
 *  provenance-tagged so the UI can render filled vs hollow dots (no-invent §20). */
export type Provenance = "from_campaign" | "from_brand_kit" | "from_me" | "absent";
export type CampaignContextFact = {
    key: string;
    label: string;
    value?: string;
    provenance: Provenance;
};
export type CampaignContextSnapshot = {
    campaign_id?: string;
    campaign_name?: string;
    facts: CampaignContextFact[];
    brand_kit_id?: string;
};

// ---- CALLS ---------------------------------------------------------------

/** GET /status — the dormancy probe. NEVER throws on 503/404: resolves to a
 *  disabled shape so every screen renders its calm dormant state. */
export async function getAssetStatus(): Promise<AssetStatus> {
    try {
        const res = await fetch(`${ASSET_BASE}/status`, { headers: authHeaders(), cache: "no-store" });
        await handle401(res);
        if (!res.ok) return { enabled: false };
        const data = (await res.json()) as Partial<AssetStatus>;
        return { enabled: !!data.enabled, ...data } as AssetStatus;
    } catch {
        // dormant / unreachable backend -> render the dormant state, never error
        return { enabled: false };
    }
}

/** GET /providers — model registry. Empty list when dormant (Advanced shows "Auto" only). */
export async function getProviders(): Promise<{ providers: AssetProvider[] }> {
    try {
        const res = await fetch(`${ASSET_BASE}/providers`, { headers: authHeaders() });
        await handle401(res);
        if (!res.ok) return { providers: [] };
        const data = await res.json();
        return { providers: Array.isArray(data?.providers) ? data.providers : [] };
    } catch {
        return { providers: [] };
    }
}

/** POST /generate — kicks a generation job. Throws AssetDormantError on 503,
 *  AssetGuardError on 402 (over_budget) / 422 (needs_input).
 *
 *  The backend `/generate` reads a JSON `Body(dict)` (ai_asset/endpoints.py:108) —
 *  it canNOT parse multipart form-data (a FormData POST 422s with
 *  `dict_type / "Input should be a valid dictionary"`, which surfaced to the user
 *  as "Couldn't start generation" and meant NO job ever started). So this MUST
 *  send a JSON body. `count` is clamped to 1..5 (n=1 is honoured by the backend,
 *  which produces exactly one). See design/fix-creative-gen.md. */
export async function generate(body: GenerateBody): Promise<GenerateResult> {
    const count = Math.max(1, Math.min(5, Math.round(Number(body.count) || 1)));
    const payload: Record<string, unknown> = {
        platform: body.platform,
        asset_type: body.asset_type,
        count,
        instruction: body.instruction,
        idempotency_key: body.idempotency_key || cryptoRandom(),
    };
    if (body.campaign_id) payload.campaign_id = body.campaign_id;
    if (body.language) payload.language = body.language;
    if (body.model) payload.model = body.model;
    if (body.brand_kit_id) payload.brand_kit_id = body.brand_kit_id;
    // The vendor's own prompt goes STRAIGHT to the image AI (backend skips Stage-1).
    if (body.custom_prompt && body.custom_prompt.trim())
        payload.custom_prompt = body.custom_prompt.trim();
    const res = await fetch(`${ASSET_BASE}/generate`, {
        method: "POST",
        headers: { ...(authHeaders() as Record<string, string>), "Content-Type": "application/json" },
        body: JSON.stringify(payload),
    });
    await handle401(res);
    if (!res.ok) return throwAsset(res, "Couldn't start generation");
    return res.json();
}

/** GET /jobs/{id} — single-shot poll fallback (the SSE owner is useGenerationJob). */
export async function getJob(jobId: string): Promise<JobStatus> {
    const res = await fetch(`${ASSET_BASE}/jobs/${encodeURIComponent(jobId)}`, { headers: authHeaders() });
    await handle401(res);
    if (res.status === 503) throw new AssetDormantError();
    if (!res.ok) throw new Error("Failed to fetch job");
    return res.json();
}

/** POST /jobs/{id}/cancel — releases the wallet hold. */
export async function cancelJob(jobId: string): Promise<{ ok: boolean }> {
    const res = await fetch(`${ASSET_BASE}/jobs/${encodeURIComponent(jobId)}/cancel`, {
        method: "POST",
        headers: authHeaders(),
    });
    await handle401(res);
    if (!res.ok) return { ok: false };
    return res.json().catch(() => ({ ok: true }));
}

/** GET /assets?<facets> — the Library/picker list. Dormant -> empty page (no throw). */
export async function listAssets(q: AssetQuery = {}): Promise<AssetListPage> {
    const params = new URLSearchParams();
    if (q.limit != null) params.set("limit", String(q.limit));
    if (q.offset != null) params.set("offset", String(q.offset));
    if (q.campaign) params.set("campaign", q.campaign);
    if (q.platform) params.set("platform", q.platform);
    if (q.kind) params.set("kind", q.kind);
    if (q.status) params.set("status", q.status);
    if (q.angle) params.set("angle", q.angle);
    if (q.size) params.set("size", q.size);
    if (q.from) params.set("from", q.from);
    if (q.to) params.set("to", q.to);
    if (q.sort) params.set("sort", q.sort);
    if (q.q) params.set("q", q.q);
    if (q.winners) params.set("winners", "1");
    const qs = params.toString();
    const empty: AssetListPage = { assets: [], total: 0, limit: q.limit ?? 30, offset: q.offset ?? 0 };
    try {
        const res = await fetch(`${ASSET_BASE}/assets${qs ? `?${qs}` : ""}`, { headers: authHeaders() });
        await handle401(res);
        // 401 (asset-service can't auth the token) / 503 (dormant) / 404 (route
        // not mounted) all resolve to the calm empty page — never an error-wall,
        // never a logout. The gallery shows its empty state instead.
        if (res.status === 401 || res.status === 503 || res.status === 404) return empty;
        if (!res.ok) throw new Error("Failed to fetch assets");
        const data = (await res.json()) as Partial<AssetListPage>;
        return {
            assets: Array.isArray(data.assets) ? data.assets : [],
            total: data.total ?? (data.assets?.length || 0),
            limit: data.limit ?? empty.limit,
            offset: data.offset ?? empty.offset,
        };
    } catch (e) {
        if (e instanceof Error && e.message === "Unauthorized") throw e;
        // any other read failure resolves to empty so the gallery shows its empty
        // state, not an error-wall. Callers surface a soft error via a separate flag.
        throw e;
    }
}

/** GET /assets/{id} — full record (owner-checked → 404 cross-tenant). */
export async function getAsset(id: string): Promise<Asset> {
    const res = await fetch(`${ASSET_BASE}/assets/${encodeURIComponent(id)}`, { headers: authHeaders() });
    await handle401(res);
    if (res.status === 503) throw new AssetDormantError();
    if (!res.ok) throw new Error("Failed to fetch asset");
    return res.json();
}

/** The raw-bytes URL for an asset/version preview (Image src). Never exposes local_path. */
export function assetRawUrl(id: string, versionId?: string): string {
    const v = versionId ? `?version=${encodeURIComponent(versionId)}` : "";
    return `${ASSET_BASE}/assets/${encodeURIComponent(id)}/raw${v}`;
}

/** POST /assets/{id}/edit — natural-language edit → a NEW version (original kept). */
export async function editAsset(id: string, instruction: string): Promise<Asset> {
    const fd = new FormData();
    fd.append("instruction", instruction);
    const res = await fetch(`${ASSET_BASE}/assets/${encodeURIComponent(id)}/edit`, {
        method: "POST",
        headers: authHeaders(),
        body: fd,
    });
    await handle401(res);
    if (!res.ok) return throwAsset(res, "Couldn't apply that edit");
    return res.json();
}

/** POST /assets/{id}/regenerate — "5 more like this" / new angle/size → new job or versions. */
export async function regenerateAsset(
    id: string,
    opts?: { variant?: string; count?: number }
): Promise<GenerateResult> {
    const fd = new FormData();
    if (opts?.variant) fd.append("variant", opts.variant);
    if (opts?.count != null) fd.append("count", String(opts.count));
    const res = await fetch(`${ASSET_BASE}/assets/${encodeURIComponent(id)}/regenerate`, {
        method: "POST",
        headers: authHeaders(),
        body: fd,
    });
    await handle401(res);
    if (!res.ok) return throwAsset(res, "Couldn't regenerate");
    return res.json();
}

/** POST /assets/{id}/approve | /reject — the status lifecycle (gates attach). */
export async function approveAsset(id: string): Promise<{ ok: boolean; status?: string }> {
    const res = await fetch(`${ASSET_BASE}/assets/${encodeURIComponent(id)}/approve`, {
        method: "POST",
        headers: authHeaders(),
    });
    await handle401(res);
    if (!res.ok) return throwAsset(res, "Couldn't approve");
    return res.json().catch(() => ({ ok: true, status: "approved" }));
}

export async function rejectAsset(id: string, reason?: string): Promise<{ ok: boolean; status?: string }> {
    const fd = new FormData();
    if (reason) fd.append("reason", reason);
    const res = await fetch(`${ASSET_BASE}/assets/${encodeURIComponent(id)}/reject`, {
        method: "POST",
        headers: authHeaders(),
        body: fd,
    });
    await handle401(res);
    if (!res.ok) return throwAsset(res, "Couldn't reject");
    return res.json().catch(() => ({ ok: true, status: "rejected" }));
}

/** Restore a version (rollback): flips current_version_id. Reuses the approve/version path. */
export async function restoreVersion(id: string, versionId: string): Promise<{ ok: boolean }> {
    const fd = new FormData();
    fd.append("version_id", versionId);
    const res = await fetch(`${ASSET_BASE}/assets/${encodeURIComponent(id)}/restore`, {
        method: "POST",
        headers: authHeaders(),
        body: fd,
    });
    await handle401(res);
    if (!res.ok) return throwAsset(res, "Couldn't restore that version");
    return res.json().catch(() => ({ ok: true }));
}

export type AttachChannel = "whatsapp" | "meta_ads" | "landing" | "workflow";

/** POST /assets/{id}/attach {channel, ref_id} — the ONE cross-platform reuse verb.
 *  approved-only (409 if not) → ai_asset_usage row + handoff drain. */
export async function attachAsset(
    id: string,
    channel: AttachChannel,
    refId?: string,
    extra?: Record<string, string>
): Promise<{ ok: boolean }> {
    const fd = new FormData();
    fd.append("channel", channel);
    if (refId) fd.append("ref_id", refId);
    if (extra) for (const [k, v] of Object.entries(extra)) fd.append(k, v);
    const res = await fetch(`${ASSET_BASE}/assets/${encodeURIComponent(id)}/attach`, {
        method: "POST",
        headers: authHeaders(),
        body: fd,
    });
    await handle401(res);
    if (!res.ok) return throwAsset(res, "Couldn't attach this asset");
    return res.json().catch(() => ({ ok: true }));
}

/** POST /variation-from-upload (multipart) — "make this kind of banner". */
export async function variationFromUpload(
    file: File,
    body: { campaign_id?: string; platform?: string; asset_type?: string; instruction?: string }
): Promise<GenerateResult> {
    const fd = new FormData();
    fd.append("reference", file);
    if (body.campaign_id) fd.append("campaign_id", body.campaign_id);
    if (body.platform) fd.append("platform", body.platform);
    if (body.asset_type) fd.append("asset_type", body.asset_type);
    if (body.instruction) fd.append("instruction", body.instruction);
    const res = await fetch(`${ASSET_BASE}/variation-from-upload`, {
        method: "POST",
        headers: authHeaders(),
        body: fd,
    });
    await handle401(res);
    if (!res.ok) return throwAsset(res, "Couldn't use that reference");
    return res.json();
}

/** GET /brand-kits — the brand memory. Dormant -> empty (no throw). */
export async function getBrandKits(): Promise<{ brand_kits: BrandKit[] }> {
    try {
        const res = await fetch(`${ASSET_BASE}/brand-kits`, { headers: authHeaders() });
        await handle401(res);
        if (!res.ok) return { brand_kits: [] };
        const data = await res.json();
        return { brand_kits: Array.isArray(data?.brand_kits) ? data.brand_kits : [] };
    } catch {
        return { brand_kits: [] };
    }
}

export async function saveBrandKit(kit: Partial<BrandKit>): Promise<BrandKit> {
    const res = await fetch(`${ASSET_BASE}/brand-kits`, {
        method: kit.id ? "PUT" : "POST",
        headers: { ...(authHeaders() as Record<string, string>), "Content-Type": "application/json" },
        body: JSON.stringify(kit),
    });
    await handle401(res);
    if (!res.ok) return throwAsset(res, "Couldn't save the brand kit");
    return res.json();
}

/** POST /brand-kits/extract — F1 auto-extract (logo / website URL). Dormant-safe:
 *  surfaces a dormant error the caller catches into a "coming soon" note. */
export async function extractBrandKit(input: { url?: string; logo?: File | null }): Promise<BrandKit> {
    const fd = new FormData();
    if (input.url) fd.append("url", input.url);
    if (input.logo) fd.append("logo", input.logo);
    const res = await fetch(`${ASSET_BASE}/brand-kits/extract`, {
        method: "POST",
        headers: authHeaders(),
        body: fd,
    });
    await handle401(res);
    if (res.status === 404) throw new AssetDormantError("Brand auto-extract isn't available yet.");
    if (!res.ok) return throwAsset(res, "Couldn't extract a brand kit");
    return res.json();
}

/** GET the resolved campaign-context snapshot for a campaign (S3 trust surface).
 *  Dormant-safe: resolves to empty facts so S3 shows its "pick a campaign" state. */
export async function getCampaignContext(campaignId: string): Promise<CampaignContextSnapshot> {
    try {
        const res = await fetch(
            `${ASSET_BASE}/campaign-context?campaign_id=${encodeURIComponent(campaignId)}`,
            { headers: authHeaders() }
        );
        await handle401(res);
        if (!res.ok) return { campaign_id: campaignId, facts: [] };
        const data = (await res.json()) as Partial<CampaignContextSnapshot>;
        return {
            campaign_id: data.campaign_id ?? campaignId,
            campaign_name: data.campaign_name,
            facts: Array.isArray(data.facts) ? data.facts : [],
            brand_kit_id: data.brand_kit_id,
        };
    } catch {
        return { campaign_id: campaignId, facts: [] };
    }
}

// ---- small helpers -------------------------------------------------------

function cryptoRandom(): string {
    try {
        if (typeof crypto !== "undefined" && crypto.randomUUID) return crypto.randomUUID();
    } catch {
        /* no crypto */
    }
    return `ck_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 10)}`;
}

/** minor units (paise) -> a human credits string. */
export function toCredits(minor?: number): string {
    if (minor == null || !Number.isFinite(minor)) return "";
    const credits = Math.round(minor / 100);
    return `${credits} credit${credits === 1 ? "" : "s"}`;
}

/** Map an asset status -> a Badge variant (one semantic colour map, no raw hex). */
export function statusVariant(status?: string): "success" | "warning" | "danger" | "info" | "neutral" {
    switch ((status || "").toLowerCase()) {
        case "approved":
            return "success";
        case "needs_review":
            return "warning";
        case "rejected":
            return "danger";
        case "used":
            return "info";
        default:
            return "neutral"; // draft | archived | unknown
    }
}

/** Pretty label for a status value. */
export function statusLabel(status?: string): string {
    switch ((status || "").toLowerCase()) {
        case "needs_review":
            return "Needs review";
        case "approved":
            return "Approved";
        case "rejected":
            return "Rejected";
        case "used":
            return "Used";
        case "archived":
            return "Archived";
        default:
            return "Draft";
    }
}

/** Pretty label for an angle value. */
export function angleLabel(angle?: string): string {
    if (!angle) return "Variant";
    return angle
        .replace(/_/g, " ")
        .replace(/\b\w/g, (c) => c.toUpperCase());
}
