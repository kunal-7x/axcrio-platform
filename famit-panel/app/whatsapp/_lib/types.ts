// WhatsApp Campaign Builder — local types + step definitions.
// Kept local to app/whatsapp per the "logic in app/<route>/_lib" rule.

import { type TabsOption } from "@/types/tabs";

// ── The 11-step pipeline (design/wa-builder-frontend.md §0) ──────────────────
// One route /whatsapp driven by a horizontal step rail (Tabs stepper), default
// landing = ① Launchpad. Steps advance left-to-right; nothing is hidden.
export type StepKey =
    | "launchpad"
    | "campaign"
    | "templates"
    | "creative"
    | "banner"
    | "preview"
    | "approval"
    | "audience"
    | "schedule"
    | "delivery"
    | "analytics";

export type StepDef = TabsOption & { key: StepKey; live: boolean };

// `live: true`  → the surface works today (send/log/campaign/audience/preview).
// `live: false` → DORMANT-SAFE: degrades to a premium coming-soon card on 404/503
//                  until the parallel whatsapp-builder + creative-attach wave lands.
export const STEPS: StepDef[] = [
    { id: 1, key: "launchpad", name: "Launchpad", live: true },
    { id: 2, key: "campaign", name: "Campaign", live: true },
    { id: 3, key: "templates", name: "AI Templates", live: false },
    { id: 4, key: "creative", name: "Creative", live: false },
    { id: 5, key: "banner", name: "Banner Studio", live: false },
    { id: 6, key: "preview", name: "Preview", live: true },
    { id: 7, key: "approval", name: "Approval", live: false },
    { id: 8, key: "audience", name: "Audience", live: true },
    { id: 9, key: "schedule", name: "Schedule", live: true },
    { id: 10, key: "delivery", name: "Delivery", live: true },
    { id: 11, key: "analytics", name: "Analytics", live: false },
];

// ── The campaign-context the AI reads (master "Campaign Context Panel") ──────
// Rendered read-only on ② so the user SEES the inputs before the AI runs. All
// fields optional — hydrated from the real campaign record; never invented.
export type CampaignContext = {
    business?: string;
    product?: string;
    location?: string;
    price?: string;
    offer?: string;
    audience?: string;
    goal?: string;
    brand?: string;
    language?: string;
};

// ── A creative asset (the AI Asset Service `AssetRef`, integrations §1) ──────
// Only the fields this UI reads. Dormant-safe: when the service is off, the
// gallery is empty and the steps render their coming-soon state.
export type AssetRef = {
    id: string;
    title?: string;
    kind?: string; // wa_poster | banner | offer_image | image
    platform?: string;
    status?: "draft" | "approved" | "winner" | string;
    url?: string; // preview / CDN url (for the phone mock + gallery thumb)
    thumb_url?: string;
    angle?: string; // price | urgency | trust | offer | …
    score?: number; // creative quality / performance score
    used_count?: number; // "used in N campaigns"
    version?: number;
    root_asset_id?: string;
    edit_label?: string;
    campaign_id?: string;
    metrics?: {
        ctr?: number;
        delivered?: number;
        read?: number;
        clicks?: number;
        replied?: number;
    };
};

// ── An AI-written WhatsApp template suggestion (③) ──────────────────────────
export type TemplateSuggestion = {
    id: string;
    name: string;
    body: string; // body copy with {{1}} personalization tokens
    cta?: string; // CTA button label
    angle?: string; // marketing angle (Price / Urgency / Trust / Offer …)
    media_rec?: string; // "pair with a WhatsApp poster"
    language?: string;
    rationale?: string; // "Built from: objective=…, audience=…"
};

// ── The draft template being assembled (carried across steps) ───────────────
export type TemplateDraft = {
    name?: string;
    body: string;
    cta?: string;
    cta_url?: string;
    header?: string;
    footer?: string;
    language?: string;
    angle?: string;
    // attached banner (binds an asset_id, never bytes — integrations §5)
    asset_id?: string;
    asset_url?: string; // preview only
    campaign_id?: string;
    // gates (surfaced as chips on ⑦/⑨)
    asset_approved?: boolean;
    meta_template_status?: "none" | "pending" | "approved" | "rejected";
};

export const EMPTY_DRAFT: TemplateDraft = {
    body: "",
    language: "English",
    meta_template_status: "none",
};

// Languages offered (master §14).
export const LANGUAGES: TabsOption[] = [
    { id: 1, name: "English" },
    { id: 2, name: "Hindi" },
    { id: 3, name: "Hinglish" },
    { id: 4, name: "Gujarati" },
];

// ── The shared builder state every step reads/writes (lifted into page.tsx) ──
// Steps are presentational; the page owns the state + advances the rail.
import { type Campaign } from "@/lib/api";

export type BuilderState = {
    campaign: Campaign | null;
    context: CampaignContext;
    draft: TemplateDraft;
    writable: boolean;
};

export type StepCtx = BuilderState & {
    setDraft: (patch: Partial<TemplateDraft>) => void;
    setCampaign: (c: Campaign | null, ctx: CampaignContext) => void;
    goTo: (key: StepKey) => void;
    /** push a toast to the workspace */
    notify: (msg: string, type?: "success" | "error") => void;
};
