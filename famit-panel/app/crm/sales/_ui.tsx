// Presentational helpers for the Sales CRM (Twenty) surface.
//
// Reuses the shared <Badge> pill language + the CRM workspace's date/initials
// helpers so the two CRM surfaces never drift. Adds the Twenty-specific bits:
// stage chips (colored by the live SELECT option color), money formatting, and a
// person avatar.

import Badge, { type BadgeVariant } from "@/components/Badge";
import { initials } from "@/app/crm/_ui";
import type { Stage } from "./client";

export { initials };
export { fmtRelative, fmtDate, fmtDateTime } from "@/app/crm/_ui";

// Twenty SELECT-option color name -> our semantic Badge variant (for stage chips).
const COLOR_VARIANT: Record<string, BadgeVariant> = {
    red: "danger",
    orange: "danger",
    yellow: "warning",
    green: "success",
    turquoise: "success",
    teal: "success",
    sky: "info",
    blue: "info",
    purple: "info",
    pink: "info",
    gray: "neutral",
    grey: "neutral",
};

// Twenty color name -> an actual hex, used as an inline accent (kanban column dot /
// rail). Inline style keeps the real Twenty color without fighting Tailwind's JIT
// purge (a constructed `bg-${color}` class would be stripped from the build).
const COLOR_HEX: Record<string, string> = {
    red: "#FB6F6F",
    orange: "#F5A35C",
    yellow: "#E8B53D",
    green: "#3FB97E",
    turquoise: "#34C7B5",
    teal: "#34C7B5",
    sky: "#5AB0F0",
    blue: "#2A85FF",
    purple: "#9B7BF0",
    pink: "#EC7BB5",
    gray: "#9AA0AA",
    grey: "#9AA0AA",
};

export function stageVariant(color?: string | null): BadgeVariant {
    return COLOR_VARIANT[(color || "").toLowerCase()] ?? "neutral";
}

export function stageColor(color?: string | null): string {
    return COLOR_HEX[(color || "").toLowerCase()] ?? "#9AA0AA";
}

// Build a value->Stage lookup once and reuse across rows.
export function stageIndex(stages: Stage[]): Map<string, Stage> {
    return new Map(stages.map((s) => [s.value, s]));
}

export function stageMeta(idx: Map<string, Stage>, value?: string | null): Stage {
    const v = value || "";
    return idx.get(v) ?? { value: v, label: v ? v.replace(/_/g, " ") : "—", color: "gray" };
}

export function StageChip({ stage }: { stage: Stage }) {
    const variant = stageVariant(stage.color);
    return (
        <Badge variant={variant} dot={variant === "success" || variant === "info"}>
            {stage.label}
        </Badge>
    );
}

// Money — Intl, tolerant of a null amount. Compacts large sums (₹1.2M) so a card
// stays readable.
export function fmtMoney(amount?: number | null, currency = "USD"): string {
    if (amount == null) return "—";
    try {
        return new Intl.NumberFormat("en-IN", {
            style: "currency",
            currency: currency || "USD",
            notation: amount >= 100000 ? "compact" : "standard",
            maximumFractionDigits: amount >= 100000 ? 1 : 0,
        }).format(amount);
    } catch {
        return `${currency} ${Math.round(amount).toLocaleString()}`;
    }
}

export function Avatar({
    name,
    url,
    size = 11,
    accent,
}: {
    name?: string;
    url?: string;
    size?: number;
    accent?: boolean;
}) {
    const cls = `grid place-items-center shrink-0 rounded-full overflow-hidden text-button font-semibold ${
        accent ? "bg-primary-02/12 text-primary-02" : "bg-b-surface1 text-t-secondary"
    }`;
    const dim = { width: `${size * 0.25}rem`, height: `${size * 0.25}rem` };
    if (url) {
        // Native <img>: avatar URLs are external (Twenty CDN); next/image would need
        // host allow-listing. Object-cover keeps it circular.
        // eslint-disable-next-line @next/next/no-img-element
        return <img src={url} alt={name || ""} className={`${cls} object-cover`} style={dim} />;
    }
    return (
        <span className={cls} style={dim}>
            {initials(name)}
        </span>
    );
}
