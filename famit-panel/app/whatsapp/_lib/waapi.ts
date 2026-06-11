// WhatsApp Campaign Builder — DORMANT-SAFE bindings for the AI-template-gen +
// Creative-attach surfaces (the parallel whatsapp-builder backend wave).
//
// These call the AI Asset Service (LIVE at backend :8310, reached via nginx
// /api/assets/, AIASSET_ENABLED=1 for admin) and the new wa-template-gen route
// (/api/whatsapp/templates/generate, being built in the parallel wave).
//
// THE RULE (spec §5, integrations §0): every one of these must DEGRADE CLEANLY.
// A 404 / 503 / network failure / {"status":"not_configured"} body resolves to a
// `{ configured: false }` sentinel — NEVER throws, NEVER error-walls. The step
// then renders the premium ComingSoon card. The LIVE send/log path
// (lib/api.ts sendWhatsApp/getWhatsAppLog) is untouched and never routed here.

import {
    type AssetRef,
    type TemplateSuggestion,
    type CampaignContext,
} from "./types";
import { type CampaignContextSnapshot } from "@/lib/assets";

const BASE =
    typeof process !== "undefined" && process.env.NEXT_PUBLIC_API_BASE
        ? process.env.NEXT_PUBLIC_API_BASE
        : "/api";

function authHeaders(): HeadersInit {
    if (typeof window === "undefined") return {};
    const token = localStorage.getItem("famit_token");
    return token ? { "X-Auth": token } : {};
}

// A response that is ALWAYS safe to render. `configured:false` ⇒ ComingSoon.
export type Dormant<T> =
    | ({ configured: true } & T)
    | { configured: false; reason?: string };

// HTTP statuses / shapes that mean "the feature isn't wired on this box yet".
const DORMANT_STATUS = new Set([404, 501, 502, 503, 423]);

async function safeGet<T>(
    path: string,
    map: (data: unknown) => T
): Promise<Dormant<T>> {
    try {
        const res = await fetch(`${BASE}${path}`, { headers: authHeaders() });
        if (res.status === 401 && typeof window !== "undefined") {
            // mirror lib/api.ts handle401 (session expiry is a real redirect,
            // NOT a dormant feature)
            localStorage.removeItem("famit_token");
            localStorage.removeItem("famit_me");
            window.location.href = "/login";
            return { configured: false, reason: "unauthorized" };
        }
        if (DORMANT_STATUS.has(res.status)) {
            return { configured: false, reason: `http_${res.status}` };
        }
        if (!res.ok) return { configured: false, reason: `http_${res.status}` };
        const data = await res.json().catch(() => null);
        // explicit backend "not yet configured" sentinel
        if (data && typeof data === "object" && (data as Record<string, unknown>).status === "not_configured") {
            return { configured: false, reason: "not_configured" };
        }
        return { configured: true, ...map(data) } as Dormant<T>;
    } catch {
        // network error / dormant box → coming-soon, never crash
        return { configured: false, reason: "network" };
    }
}

async function safePost<T>(
    path: string,
    body: FormData | Record<string, unknown>,
    map: (data: unknown) => T
): Promise<Dormant<T>> {
    try {
        const isForm = body instanceof FormData;
        const res = await fetch(`${BASE}${path}`, {
            method: "POST",
            headers: isForm
                ? authHeaders()
                : { ...(authHeaders() as Record<string, string>), "Content-Type": "application/json" },
            body: isForm ? body : JSON.stringify(body),
        });
        if (res.status === 401 && typeof window !== "undefined") {
            localStorage.removeItem("famit_token");
            localStorage.removeItem("famit_me");
            window.location.href = "/login";
            return { configured: false, reason: "unauthorized" };
        }
        if (DORMANT_STATUS.has(res.status) || !res.ok) {
            return { configured: false, reason: `http_${res.status}` };
        }
        const data = await res.json().catch(() => null);
        if (data && typeof data === "object" && (data as Record<string, unknown>).status === "not_configured") {
            return { configured: false, reason: "not_configured" };
        }
        return { configured: true, ...map(data) } as Dormant<T>;
    } catch {
        return { configured: false, reason: "network" };
    }
}

// ── normalizers (tolerant of partial/missing fields) ─────────────────────────
function asAsset(r: Record<string, unknown>): AssetRef {
    return {
        id: String(r.id ?? r.asset_id ?? ""),
        title: (r.title as string) ?? undefined,
        kind: (r.kind as string) ?? undefined,
        platform: (r.platform as string) ?? undefined,
        status: (r.status as AssetRef["status"]) ?? "draft",
        url: (r.url as string) ?? (r.preview_url as string) ?? undefined,
        thumb_url: (r.thumb_url as string) ?? (r.url as string) ?? undefined,
        angle: (r.angle as string) ?? undefined,
        score: typeof r.score === "number" ? r.score : undefined,
        used_count: typeof r.used_count === "number" ? r.used_count : undefined,
        version: typeof r.version === "number" ? r.version : undefined,
        root_asset_id: (r.root_asset_id as string) ?? undefined,
        edit_label: (r.edit_label as string) ?? undefined,
        campaign_id: (r.campaign_id as string) ?? undefined,
        metrics: (r.metrics as AssetRef["metrics"]) ?? undefined,
    };
}

function asSuggestion(r: Record<string, unknown>, i: number): TemplateSuggestion {
    // The LIVE backend (/whatsapp/campaign/{id}/generate-templates) returns a
    // rich Meta-template shape: body/header/footer are objects ({text,example}),
    // and the CTA lives in buttons[0].text. The older flat shape (body:string,
    // cta:string) is still accepted. Read both.
    const bodyObj = (r.body && typeof r.body === "object" ? r.body : null) as
        | { text?: string }
        | null;
    const buttons = Array.isArray(r.buttons) ? (r.buttons as Record<string, unknown>[]) : [];
    const firstBtn = buttons.length ? buttons[0] : null;
    return {
        id: String(r.id ?? r.template_id ?? `t${i}`),
        name: String(r.name ?? r.template_name ?? `Template ${i + 1}`),
        body: String(bodyObj?.text ?? r.body ?? r.text ?? ""),
        cta:
            (r.cta as string) ??
            (r.cta_label as string) ??
            (firstBtn?.text as string | undefined) ??
            undefined,
        angle: (r.angle as string) ?? undefined,
        media_rec: (r.media_rec as string) ?? (r.media_recommendation as string) ?? undefined,
        language: (r.language as string) ?? undefined,
        rationale: (r.rationale as string) ?? undefined,
    };
}

// ── ③ AI Template Generation — LIVE ──────────────────────────────────────────
// The real backend route is campaign-scoped: POST /whatsapp/campaign/{id}/
// generate-templates (JSON body), returning an AI-generated bundle of
// Meta-compliant templates (validator-as-authority, no_invent_flags). The older
// /whatsapp/templates/generate path was never mounted (404). A campaign_id is
// REQUIRED — without one the surface stays dormant (the wizard gates ③ on a
// chosen campaign anyway).
//
// THREE outcomes, not two (this is the fix — a 200 with no templates is NOT a
// dormant feature, it's a real failure the founder must SEE):
//   • configured:false              → route truly absent on this box (404/503/
//                                      network) → premium ComingSoon + manual path.
//   • configured:true, ok:true      → real AI templates → suggestion cards.
//   • configured:true, ok:false     → the engine RAN but couldn't produce copy
//                                      (insufficient credits / empty / model
//                                      error). Carries a human `message` + a
//                                      machine `errorCode` so the step shows a
//                                      real "add credits / retry / write manually"
//                                      panel — NEVER a silent blank grid.
export type GenerateResult = {
    suggestions: TemplateSuggestion[];
    rationale?: string;
    ok: boolean;
    errorCode?: string; // e.g. "insufficient_credits"
    message?: string; // founder-readable explanation
    estimateMinor?: number; // credits the run would cost (paise)
};

// Turn a backend error code (status:"error:*" / error:"*") into plain English.
function explainGenError(code: string, estimateMinor?: number): string {
    const credits =
        typeof estimateMinor === "number" && estimateMinor > 0
            ? ` (needs about ${(estimateMinor / 100).toFixed(0)} credits)`
            : "";
    switch (code) {
        case "insufficient_credits":
            return `Not enough wallet credits to generate templates${credits}. Top up your wallet, or write a template manually below.`;
        case "no_context":
        case "no_campaign_context":
            return "This campaign has no business details yet, so the AI has nothing to write from. Add product / offer details to the campaign, or write a template manually below.";
        case "model_error":
        case "provider_error":
            return "The language engine couldn't be reached just now. Try again in a moment, or write a template manually below.";
        default:
            return "The AI couldn't generate templates right now. Try again, or write a template manually below.";
    }
}

export async function generateTemplates(input: {
    campaign_id?: string;
    objective?: string;
    audience?: string;
    language?: string;
    n?: number;
}): Promise<Dormant<GenerateResult>> {
    if (!input.campaign_id) {
        return { configured: false, reason: "no_campaign" };
    }
    const body: Record<string, unknown> = { n: input.n ?? 4 };
    if (input.objective) body.objective = input.objective;
    if (input.audience) body.audience = input.audience;
    if (input.language) body.language = input.language;
    return safePost(
        `/whatsapp/campaign/${encodeURIComponent(input.campaign_id)}/generate-templates`,
        body,
        (data) => {
            const d = (data ?? {}) as Record<string, unknown>;
            const items = Array.isArray(d.templates)
                ? d.templates
                : Array.isArray(d.suggestions)
                ? d.suggestions
                : [];
            const suggestions = items.map((x, i) =>
                asSuggestion(x as Record<string, unknown>, i)
            );
            // The route answers 200 even on failure, signalling via
            // status:"error:<code>" and/or error:"<code>". Normalize that.
            const statusStr = String(d.status ?? "");
            const rawErr =
                (d.error as string) ??
                (statusStr.startsWith("error:") ? statusStr.slice("error:".length) : "") ??
                "";
            const estimateMinor =
                typeof d.estimate_minor === "number" ? d.estimate_minor : undefined;
            const hadError = !!rawErr || statusStr.startsWith("error");
            const ok = !hadError && suggestions.length > 0;
            return {
                suggestions,
                rationale: (d.rationale as string) ?? undefined,
                ok,
                errorCode: rawErr || (hadError ? "unknown" : suggestions.length ? undefined : "empty"),
                message: ok
                    ? undefined
                    : explainGenError(rawErr || "empty", estimateMinor),
                estimateMinor,
            };
        }
    );
}

// ── ④ Creative Selection — browse the Asset Library (DORMANT until :8310 wired)
// GET /assets?campaign_id&platform=whatsapp&kind=…&status=approved&sort=top_ctr
export async function searchAssets(opts?: {
    campaign_id?: string;
    platform?: string;
    kind?: string;
    status?: string;
    angle?: string;
    text?: string;
    sort?: string;
    root_asset_id?: string;
}): Promise<Dormant<{ items: AssetRef[]; total: number }>> {
    const p = new URLSearchParams();
    if (opts?.campaign_id) p.set("campaign_id", opts.campaign_id);
    p.set("platform", opts?.platform ?? "whatsapp");
    if (opts?.kind) p.set("kind", opts.kind);
    if (opts?.status) p.set("status", opts.status);
    if (opts?.angle) p.set("angle", opts.angle);
    if (opts?.text) p.set("text", opts.text);
    if (opts?.sort) p.set("sort", opts.sort);
    if (opts?.root_asset_id) p.set("root_asset_id", opts.root_asset_id);
    const qs = p.toString();
    return safeGet(`/assets${qs ? `?${qs}` : ""}`, (data) => {
        const d = (data ?? {}) as Record<string, unknown>;
        const items = Array.isArray(d.items)
            ? d.items
            : Array.isArray(d.assets)
            ? d.assets
            : [];
        return {
            items: items.map((x) => asAsset(x as Record<string, unknown>)),
            total: typeof d.total === "number" ? d.total : items.length,
        };
    });
}

// ── ⑤ Banner Studio — generate banners (DORMANT until provider key) ──────────
// POST /assets/generate {campaign_id,kind:wa_poster,platform:whatsapp,n} → job_id
export async function generateBanner(input: {
    campaign_id?: string;
    instruction?: string;
    n?: number;
    size?: string;
}): Promise<Dormant<{ job_id: string; batch_id?: string; estimate_minor?: number }>> {
    const fd = new FormData();
    if (input.campaign_id) fd.append("campaign_id", input.campaign_id);
    fd.append("kind", "wa_poster");
    fd.append("platform", "whatsapp");
    if (input.instruction) fd.append("instruction", input.instruction);
    fd.append("n", String(input.n ?? 4));
    if (input.size) fd.append("size", input.size);
    return safePost("/assets/generate", fd, (data) => {
        const d = (data ?? {}) as Record<string, unknown>;
        return {
            job_id: String(d.job_id ?? ""),
            batch_id: (d.batch_id as string) ?? undefined,
            estimate_minor: typeof d.estimate_minor === "number" ? d.estimate_minor : undefined,
        };
    });
}

// Poll one generation job's assets (used after the loader completes).
export async function getJobAssets(
    jobId: string
): Promise<Dormant<{ status: string; assets: AssetRef[] }>> {
    return safeGet(`/assets/jobs/${encodeURIComponent(jobId)}`, (data) => {
        const d = (data ?? {}) as Record<string, unknown>;
        const items = Array.isArray(d.assets) ? d.assets : [];
        return {
            status: String(d.status ?? d.state ?? "running"),
            assets: items.map((x) => asAsset(x as Record<string, unknown>)),
        };
    });
}

// ── ⑦ Approval — flip an asset draft→approved (DORMANT until :8310) ──────────
export async function approveAsset(id: string): Promise<Dormant<{ asset: AssetRef }>> {
    return safePost(`/assets/${encodeURIComponent(id)}/approve`, new FormData(), (data) => ({
        asset: asAsset((data ?? {}) as Record<string, unknown>),
    }));
}

// ── ⑪ Analytics — performance per variant (DORMANT until writeback lands) ────
export type VariantPerf = {
    asset_id: string;
    title: string;
    angle?: string;
    delivered?: number;
    read?: number;
    replied?: number;
    ctr?: number;
    status?: string;
};

export async function getCampaignPerformance(
    campaignId?: string
): Promise<Dormant<{ variants: VariantPerf[]; funnel: { stage: string; count: number }[] }>> {
    const p = new URLSearchParams();
    if (campaignId) p.set("campaign_id", campaignId);
    p.set("platform", "whatsapp");
    return safeGet(`/assets/performance?${p.toString()}`, (data) => {
        const d = (data ?? {}) as Record<string, unknown>;
        const variants = Array.isArray(d.variants) ? d.variants : [];
        const funnel = Array.isArray(d.funnel) ? d.funnel : [];
        return {
            variants: variants.map((v) => {
                const r = v as Record<string, unknown>;
                return {
                    asset_id: String(r.asset_id ?? ""),
                    title: String(r.title ?? "Variant"),
                    angle: (r.angle as string) ?? undefined,
                    delivered: typeof r.delivered === "number" ? r.delivered : undefined,
                    read: typeof r.read === "number" ? r.read : undefined,
                    replied: typeof r.replied === "number" ? r.replied : undefined,
                    ctr: typeof r.ctr === "number" ? r.ctr : undefined,
                    status: (r.status as string) ?? undefined,
                };
            }),
            funnel: funnel.map((f) => {
                const r = f as Record<string, unknown>;
                return { stage: String(r.stage ?? ""), count: Number(r.count ?? 0) };
            }),
        };
    });
}

// Derive a read-only Campaign Context (master panel) from a campaign record.
// Pure client-side — never invents a value the record didn't carry (master §20).
export function contextFromCampaign(c: {
    name?: string;
    company?: string;
    product?: string;
}): CampaignContext {
    return {
        business: c.company || undefined,
        product: c.product || undefined,
        goal: c.name || undefined,
    };
}

// Map the AI Asset Service's resolved snapshot (provenance-tagged facts) onto the
// master Campaign Context panel. Each fact carries a `key` (business/product/
// offer/price/location/audience/goal/language/…) and a `value`; we project the
// known keys and drop `absent`/value-less facts so nothing is invented (§20).
// Returns `null` when the snapshot carried no usable facts (dormant Asset Service)
// so the caller can fall back to contextFromCampaign(c).
export function ctxFromSnapshot(snapshot?: CampaignContextSnapshot): CampaignContext | null {
    const facts = snapshot?.facts;
    if (!Array.isArray(facts) || facts.length === 0) return null;

    // fact.key → CampaignContext field (tolerant of the backend's aliasing)
    const KEY_MAP: Record<string, keyof CampaignContext> = {
        business: "business",
        company: "business",
        product: "product",
        service: "product",
        location: "location",
        city: "location",
        price: "price",
        offer: "offer",
        deal: "offer",
        audience: "audience",
        goal: "goal",
        objective: "goal",
        brand: "brand",
        brand_style: "brand",
        language: "language",
    };

    const ctx: CampaignContext = {};
    let filled = false;
    for (const f of facts) {
        if (!f || f.provenance === "absent") continue;
        const v = (f.value || "").trim();
        if (!v) continue;
        const field = KEY_MAP[(f.key || "").toLowerCase()];
        if (!field || ctx[field]) continue; // first non-empty wins
        ctx[field] = v;
        filled = true;
    }
    return filled ? ctx : null;
}
