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
import { type MetaError, type WhatsAppSendResult } from "@/lib/api";

// ── Meta send-error → plain English ──────────────────────────────────────────
// The backend (fix/wafx-whatsapp-meta-error-surfacing) now returns Meta's REAL
// Graph error on a failed send/submit. This turns the known reasons into a calm,
// founder-readable note — and ALWAYS exposes Meta's own raw line + code in a
// small muted string for debugging. Never fabricates a reason: when we don't
// recognise the code we fall back to Meta's own error_user_msg/message.
//
// The approved templates that actually deliver today (env WAFX_APPROVED_TEMPLATES).
export const WAFX_APPROVED_TEMPLATES = ["post_call_followup"] as const;

export type MetaExplain = {
    // headline reason in plain language
    title: string;
    // one-line body the founder can act on
    detail: string;
    // muted debug string: Meta's own message + code (for the support line)
    debug?: string;
    // tone hint for the surfacing card
    tone: "warning" | "danger" | "info";
};

function metaDebugLine(code: string | number | undefined, m?: MetaError): string | undefined {
    const bits: string[] = [];
    const raw = m?.error_user_msg || m?.message;
    if (raw) bits.push(raw.trim());
    const codeStr =
        m?.code != null
            ? `code ${m.code}${m.error_subcode != null ? `/${m.error_subcode}` : ""}`
            : typeof code === "number"
            ? `code ${code}`
            : typeof code === "string" && code && code !== "unknown"
            ? code
            : "";
    if (codeStr) bits.push(codeStr);
    if (m?.fbtrace_id) bits.push(`trace ${m.fbtrace_id}`);
    return bits.length ? `Meta: ${bits.join(" · ")}` : undefined;
}

// Map a failed WhatsApp send result → friendly explanation. Reads the structured
// `meta_error` first (richest), then the machine `error`/`status` code.
export function explainMetaError(r: {
    error?: string;
    status?: string;
    meta_error?: MetaError;
    approved_templates?: string[];
}): MetaExplain {
    const m = r.meta_error;
    const code = m?.code;
    const subcode = m?.error_subcode;
    const machine = (r.error || r.status || "").toString();
    const approved =
        (r.approved_templates && r.approved_templates.length
            ? r.approved_templates
            : [...WAFX_APPROVED_TEMPLATES]
        ).join(", ");
    const debug = metaDebugLine(code ?? machine, m);

    // unregistered / unknown template name (backend code or Meta side)
    if (machine.includes("template_not_registered") || code === 132001 || subcode === 2494011) {
        return {
            tone: "warning",
            title: "That template isn’t registered with Meta",
            detail: `Only approved templates can be sent. Use ${approved || "an approved template"}, or submit a new template for Meta review first.`,
            debug,
        };
    }
    // hello_world is a Meta test-only template (131058 etc.)
    if (machine.includes("hello_world") || code === 131058) {
        return {
            tone: "warning",
            title: "hello_world is a Meta test-only template",
            detail: `“hello_world” can only be sent from Meta’s public test numbers. Use an approved business template (${approved || "post_call_followup"}) for real recipients.`,
            debug,
        };
    }
    // payment method / billing block — 141006
    if (code === 141006 || machine.includes("141006")) {
        return {
            tone: "danger",
            title: "Add a payment method on Meta",
            detail: "Your Meta WhatsApp account needs a payment method before messages can be delivered. Add billing in WhatsApp Manager, then try again.",
            debug,
        };
    }
    // business not verified / messaging-tier limit (TIER_250 / throughput)
    if (
        machine.toUpperCase().includes("TIER_250") ||
        machine.toLowerCase().includes("not_verified") ||
        machine.toLowerCase().includes("verification") ||
        code === 131056 ||
        code === 131048
    ) {
        return {
            tone: "warning",
            title: "Meta is still reviewing your business",
            detail: "Sending is limited until business verification completes. You can send to a small number of recipients now; full volume unlocks once Meta finishes review.",
            debug,
        };
    }
    // media header upload failed (subcode 2388043 — banner handle missing)
    if (subcode === 2388043 || machine.includes("2388043") || machine.toLowerCase().includes("header_handle")) {
        return {
            tone: "warning",
            title: "The banner couldn’t be uploaded to Meta",
            detail: "The image header didn’t resolve. Re-attach an approved banner, or send the template without an image header.",
            debug,
        };
    }
    // credentials genuinely not set on the box
    if (machine === "skipped_no_config" || machine === "not_configured" || r.status === "skipped_no_config") {
        return {
            tone: "info",
            title: "WhatsApp isn’t connected on this account",
            detail: "No WhatsApp provider is configured for this account yet. Once it’s connected, sending starts working.",
            debug,
        };
    }
    // generic Meta error — surface Meta's OWN words (never invented)
    if (m?.error_user_title || m?.error_user_msg) {
        return {
            tone: "danger",
            title: m.error_user_title || "Meta couldn’t deliver this message",
            detail: m.error_user_msg || "Meta returned an error. See the details below, or try again in a moment.",
            debug,
        };
    }
    return {
        tone: "danger",
        title: "Message couldn’t be delivered",
        detail: "Meta returned an error for this send. The raw reason is shown below — try again in a moment, or check WhatsApp Manager.",
        debug: debug || (machine && machine !== "unknown" ? `Meta: ${machine}` : undefined),
    };
}

// Convenience: explain straight from a sendWhatsApp() result.
export function explainSendResult(r: WhatsAppSendResult): MetaExplain {
    return explainMetaError({
        error: r.error,
        status: r.status,
        meta_error: r.meta_error,
        approved_templates: r.approved_templates,
    });
}

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
    // The persisted row carries `template_id` + lifecycle `status` + a `compliance`
    // object. We thread template_id through so the builder can later approve →
    // submit-to-Meta → poll meta-status against THIS exact row (the LIVE path).
    const templateId =
        (r.template_id as string) ?? (r.id as string) ?? undefined;
    const compliance = (r.compliance && typeof r.compliance === "object"
        ? (r.compliance as Record<string, unknown>)
        : null);
    // Meta-valid enough to submit? Tolerant of a few backend shapes; defaults to
    // true (the approve gate is the real authority — we never block optimistically).
    const canSubmit =
        compliance == null
            ? true
            : (compliance.ok as boolean | undefined) ??
              (compliance.valid as boolean | undefined) ??
              (Array.isArray(compliance.errors) ? compliance.errors.length === 0 : true);
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
        template_id: templateId,
        status: (r.status as string) ?? undefined,
        canSubmit,
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
    // The engine produced templates but flagged the run as partial (e.g. a model
    // hiccup fell back to deterministic copy). NOT a failure — show the cards + a
    // small note. `ok` stays true; `partial` just drives the advisory banner.
    partial?: boolean;
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
            //   • "accepted" / "draft" / "partial"  → SUCCESS shape (real templates).
            //   • "error" / "error:<code>"           → real failure (credits/empty/…).
            // CRITICAL (the fix): a "partial" bundle that STILL carries templates is
            // a SUCCESS — the founder gets the AI/fallback cards plus a small note,
            // NEVER a "couldn't generate / try again" wall. We only fail on a status
            // that starts with "error" OR a genuinely empty grid.
            const statusStr = String(d.status ?? "");
            const rawErr =
                (d.error as string) ??
                (statusStr.startsWith("error:") ? statusStr.slice("error:".length) : "") ??
                "";
            const estimateMinor =
                typeof d.estimate_minor === "number" ? d.estimate_minor : undefined;
            const partial = statusStr === "partial" || statusStr.startsWith("partial");
            // A real failure = an explicit error status/code. A non-empty grid is a
            // success even when the status string is unexpected (forward-compatible).
            const hadError = statusStr.startsWith("error") || (!!rawErr && suggestions.length === 0);
            const ok = !hadError && suggestions.length > 0;
            return {
                suggestions,
                rationale: (d.rationale as string) ?? undefined,
                ok,
                partial: ok && partial,
                errorCode: rawErr || (hadError ? "unknown" : suggestions.length ? undefined : "empty"),
                message: ok
                    ? undefined
                    : explainGenError(rawErr || "empty", estimateMinor),
                estimateMinor,
            };
        }
    );
}

// ── ③b Submit-to-Meta — the LIVE builder gate → Meta review ─────────────────
// The persisted ai_wa_templates row drives three real routes (all token-derived,
// prefix /whatsapp/campaign):
//   POST …/templates/{id}/approve        — builder-internal gate (must pass first)
//   POST …/templates/{id}/attach-banner  — bind an approved Creative asset_id as
//                                           the IMAGE header (backend then resolves
//                                           bytes → DO Spaces → Meta resumable handle)
//   POST …/templates/{id}/submit-to-meta — submit the APPROVED template to Meta
//   GET  …/templates/{id}/meta-status    — poll PENDING/APPROVED/REJECTED
// All dormant-safe: a 404/503/network resolves to {configured:false} (the surface
// shows a calm "not connected" note), NEVER an error wall.

export type MetaReview = "none" | "pending" | "approved" | "rejected";

function normalizeReview(s: unknown): MetaReview {
    const v = String(s ?? "").toLowerCase();
    if (v === "approved") return "approved";
    if (v === "rejected") return "rejected";
    if (v === "pending" || v === "submitted" || v === "in_review") return "pending";
    return "none";
}

// Bind an APPROVED Creative asset as the template's IMAGE header. The backend
// resolves the asset's URL → resumable upload → header_handle at submit time.
export async function attachBanner(
    templateId: string,
    assetId: string
): Promise<Dormant<{ ok: boolean; error?: string }>> {
    return safePost(
        `/whatsapp/campaign/templates/${encodeURIComponent(templateId)}/attach-banner`,
        { asset_id: assetId },
        (data) => {
            const d = (data ?? {}) as Record<string, unknown>;
            const status = String(d.status ?? "");
            return {
                ok: status !== "refused" && status !== "error",
                error: (d.error as string) ?? undefined,
            };
        }
    );
}

// Approve (builder gate) → optionally attach a banner → submit to Meta, in one
// call the founder triggers from one "Submit to Meta" button. Returns the live
// review state + any human-readable reason. Dormant-safe end to end.
export type SubmitResult = {
    submitted: boolean;
    review: MetaReview;
    metaTemplateId?: string;
    // a founder-readable reason when NOT submitted (refused gate / Meta error)
    message?: string;
    // Meta's own raw line + code, when Meta rejected the submission (for the
    // small muted debug line — never invented).
    metaDebug?: string;
};

function explainSubmit(code: string): string {
    switch (code) {
        case "template_not_approved":
            return "The template didn’t pass the internal quality gate, so it wasn’t sent to Meta. Edit the copy and try again.";
        case "asset_not_approved":
            return "The attached banner isn’t approved yet. Approve the banner first, then submit.";
        case "asset_not_found_or_cross_tenant":
        case "cross_tenant_asset":
            return "That banner couldn’t be found for your account. Pick a banner you own, then submit.";
        case "not_configured":
            return "WhatsApp isn’t connected on this account yet, so the template can’t be submitted to Meta.";
        default:
            return code.startsWith("http_")
                ? "Meta couldn’t accept the template just now. Try again in a moment."
                : "The template couldn’t be submitted to Meta right now. Try again.";
    }
}

export async function submitTemplateToMeta(input: {
    templateId: string;
    assetId?: string; // optional banner to bind as the IMAGE header before submit
}): Promise<Dormant<SubmitResult>> {
    const { templateId, assetId } = input;
    if (!templateId) return { configured: false, reason: "no_template" };

    // 1) builder-internal approve gate (submit-to-Meta requires status=approved)
    const appr = await safePost(
        `/whatsapp/campaign/templates/${encodeURIComponent(templateId)}/approve`,
        {},
        (data) => {
            const d = (data ?? {}) as Record<string, unknown>;
            return { status: String(d.status ?? ""), error: (d.error as string) ?? "" };
        }
    );
    if (!appr.configured) return { configured: false, reason: appr.reason };
    if (appr.status === "refused") {
        return { configured: true, submitted: false, review: "none", message: explainSubmit(appr.error || "template_not_approved") };
    }

    // 2) optional banner attach (best-effort — a failed attach must NOT block a
    //    text-only submit; we surface it only if it refuses)
    if (assetId) {
        const at = await attachBanner(templateId, assetId);
        if (at.configured && !at.ok) {
            return { configured: true, submitted: false, review: "none", message: explainSubmit(at.error || "asset_not_approved") };
        }
    }

    // 3) submit to Meta
    return safePost(
        `/whatsapp/campaign/templates/${encodeURIComponent(templateId)}/submit-to-meta`,
        {},
        (data) => {
            const d = (data ?? {}) as Record<string, unknown>;
            const status = String(d.status ?? "");
            const submitted = status === "submitted";
            const code = (d.error as string) || (d.detail as string) || status;
            // When Meta itself rejected the submission the backend now returns its
            // real Graph error — map it to plain language (template not registered /
            // billing / verification) and keep Meta's raw line for debugging,
            // instead of the generic "try again".
            const metaError = (d.meta_error && typeof d.meta_error === "object"
                ? (d.meta_error as MetaError)
                : undefined);
            const metaSurfaced =
                !submitted && (metaError || (code && code.startsWith("meta_error")));
            const explained = metaSurfaced
                ? explainMetaError({ error: code, status, meta_error: metaError })
                : null;
            return {
                submitted,
                review: submitted ? normalizeReview(d.review_status ?? "PENDING") : "none",
                metaTemplateId: (d.meta_template_id as string) || undefined,
                message: submitted
                    ? undefined
                    : explained
                    ? `${explained.title} — ${explained.detail}`
                    : explainSubmit(code || "unknown"),
                metaDebug: explained?.debug,
            };
        }
    );
}

// Poll a submitted template's Meta review state (for the PENDING→APPROVED badge).
export async function getMetaStatus(
    templateId: string
): Promise<Dormant<{ review: MetaReview; rejectionReason?: string }>> {
    if (!templateId) return { configured: false, reason: "no_template" };
    return safeGet(
        `/whatsapp/campaign/templates/${encodeURIComponent(templateId)}/meta-status`,
        (data) => {
            const d = (data ?? {}) as Record<string, unknown>;
            return {
                review: normalizeReview(d.review_status),
                rejectionReason: (d.rejection_reason as string) || undefined,
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
