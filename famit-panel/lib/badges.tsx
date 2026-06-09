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
