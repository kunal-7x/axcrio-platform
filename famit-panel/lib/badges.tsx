// ONE badge language for the whole panel (feat/premium-ui).
//
// Before this, every page hand-rolled its own statusBadge/outcomeBadge/
// scoreBadge with raw `bg-green-100 text-green-700` Tailwind — the single
// biggest "cheap" tell. These helpers map every semantic value to a token-
// based <Badge> variant so badges look identical across Dashboard / Calls /
// Leads / Billing. Presentational only; no API/logic changes.

import Badge, { type BadgeVariant } from "@/components/Badge";

function humanize(s: string): string {
    return s.replace(/_/g, " ");
}

// Call / lead lifecycle status -> variant.
const STATUS_VARIANT: Record<string, BadgeVariant> = {
    answered: "success",
    done: "success",
    called: "success",
    qualified: "success",
    interested: "success",
    failed: "danger",
    opt_out: "danger",
    not_interested: "danger",
    busy: "warning",
    no_answer: "warning",
    voicemail: "warning",
    queued: "warning",
    calling: "info",
    in_progress: "info",
    new: "info",
    callback: "info",
    no_human: "neutral",
    suppressed: "neutral",
};

export function StatusBadge({ status }: { status?: string | null }) {
    if (!status) return <span className="text-t-tertiary">—</span>;
    const variant = STATUS_VARIANT[status] ?? "neutral";
    const dot = variant === "info" || variant === "success";
    return (
        <Badge variant={variant} dot={dot}>
            {humanize(status)}
        </Badge>
    );
}

// Call outcome (interested / callback / not_interested / ...).
export function OutcomeBadge({ outcome }: { outcome?: string | null }) {
    if (!outcome) return null;
    const variant = STATUS_VARIANT[outcome] ?? "neutral";
    return <Badge variant={variant}>{humanize(outcome)}</Badge>;
}

// Coarse interest level (high / medium / low) from the call detail.
export function InterestBadge({ interest }: { interest?: string | null }) {
    if (!interest) return null;
    const variant: BadgeVariant =
        interest === "high" ? "success" : interest === "medium" ? "warning" : "danger";
    return <Badge variant={variant}>{interest} interest</Badge>;
}

// Numeric lead/interest score (0-100) -> hot / warm / cold.
export function ScoreBadge({ score }: { score?: number | null }) {
    if (score == null) return <span className="text-t-tertiary">—</span>;
    const variant: BadgeVariant =
        score >= 70 ? "success" : score >= 40 ? "warning" : "neutral";
    const label = score >= 70 ? `${score} hot` : String(score);
    return <Badge variant={variant} dot={score >= 70}>{label}</Badge>;
}

// ───────────────────────────────────────────────────────────────────────────
// W15 — ONE business-friendly lead badge language (design/W15-UI-IA-PLAN.md §4).
//
// Founder rule: the customer-facing UI must NEVER show a raw score ("82 hot").
// It shows a WORD: Hot / Warm / Cold / Dead / Booked / Callback / Interested.
// LeadBadge derives the tier from whatever signals a row carries (status, stage,
// outcome, score) and renders the SAME <Badge> on the Dashboard, Leads & CRM, and
// Call Logs — one vocabulary everywhere. `ScoreBadge` stays available for the one
// admin/debug surface that wants the number; default UI uses LeadBadge.
//
// Derivation priority (first match wins, per §4):
//   opt_out / not_interested / dead / lost     -> Dead      (muted red)
//   booked / won / converted                   -> Booked    (green)
//   interested / qualified                     -> Interested(green)
//   callback                                   -> Callback  (blue)
//   else by score:  >=70 Hot · 40-69 Warm · 1-39 Cold · (null) Cold
//
// Accepts a loose `LeadLike` so it works against api.ts `Lead` (status/score/
// last_outcome/hot), `CallLog` (status/interest), and W14 report rows (lead_status)
// without forcing one shape. All fields optional → degrades gracefully.

export type LeadTier =
    | "Hot"
    | "Warm"
    | "Cold"
    | "Dead"
    | "Booked"
    | "Callback"
    | "Interested";

export type LeadLike = {
    status?: string | null;
    stage?: string | null;
    lead_status?: string | null;
    booking_status?: string | null;
    last_outcome?: string | null;
    outcome?: string | null;
    score?: number | null;
    conversion_prob?: number | null; // 0..1 (W14 hot-lead rows)
    hot?: boolean | null;
    booked?: boolean | null;
};

const TIER_VARIANT: Record<LeadTier, BadgeVariant> = {
    Hot: "success",
    Warm: "warning",
    Cold: "neutral",
    Dead: "danger",
    Booked: "success",
    Callback: "info",
    Interested: "success",
};

// Pure: signals -> tier. Exported so non-badge surfaces (filters, sorting) can
// reuse the SAME classification the badge shows — no drift between rail and pill.
export function leadTierOf(lead: LeadLike): LeadTier {
    const norm = (s?: string | null) => (s ?? "").toLowerCase().trim();
    const bag = [
        norm(lead.status),
        norm(lead.stage),
        norm(lead.lead_status),
        norm(lead.booking_status),
        norm(lead.last_outcome),
        norm(lead.outcome),
    ];
    const has = (...keys: string[]) =>
        bag.some((v) => keys.some((k) => v === k || v.includes(k)));

    // Score may arrive as 0..100 (Lead.score) or 0..1 (conversion_prob).
    let score: number | null = null;
    if (typeof lead.score === "number") score = lead.score;
    else if (typeof lead.conversion_prob === "number")
        score = Math.round(lead.conversion_prob * 100);

    if (has("opt_out", "opted_out", "not_interested", "dead", "lost")) return "Dead";
    if (lead.booked === true || has("booked", "won", "converted", "site_visit"))
        return "Booked";
    if (has("interested", "qualified")) return "Interested";
    if (has("callback")) return "Callback";

    if (lead.hot === true) return "Hot";
    if (score == null) return "Cold";
    if (score >= 70) return "Hot";
    if (score >= 40) return "Warm";
    return "Cold";
}

// The shared business-friendly lead badge — the ONE pill the customer-facing
// surfaces render. Dot on the high-signal tiers (Hot/Booked) for a calm cue.
export function LeadBadge({ lead }: { lead: LeadLike }) {
    const tier = leadTierOf(lead);
    const variant = TIER_VARIANT[tier];
    const dot = tier === "Hot" || tier === "Booked";
    return (
        <Badge variant={variant} dot={dot}>
            {tier}
        </Badge>
    );
}
