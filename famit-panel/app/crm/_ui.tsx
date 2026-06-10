// Colocated presentational helpers for the CRM workspace + profile.
//
// Lives under app/crm (this page's own files) rather than lib/badges.tsx, which
// is shared and off-limits for this build. It REUSES the shared <Badge> /
// pill-* language (no new tokens), just maps the crm-specific stage + timeline
// vocabularies onto it so the page stays cohesive with the rest of the panel.

import Badge, { type BadgeVariant } from "@/components/Badge";

// CRM lifecycle stage (§4.1) -> the one badge language. Won/booked/qualified
// read as "good", lost/opted_out as "bad", dormant as muted, the rest as
// progressing.
const STAGE_VARIANT: Record<string, BadgeVariant> = {
    new: "info",
    contacted: "info",
    engaged: "warning",
    qualified: "success",
    booked: "success",
    won: "success",
    lost: "danger",
    opted_out: "danger",
    dormant: "neutral",
};

const STAGE_LABEL: Record<string, string> = {
    new: "New",
    contacted: "Contacted",
    engaged: "Engaged",
    qualified: "Qualified",
    booked: "Booked",
    won: "Won",
    lost: "Lost",
    opted_out: "Opted out",
    dormant: "Dormant",
};

export function StageBadge({ stage }: { stage?: string | null }) {
    if (!stage) return <span className="text-t-tertiary">—</span>;
    const variant = STAGE_VARIANT[stage] ?? "neutral";
    const dot = variant === "success" || variant === "info";
    return (
        <Badge variant={variant} dot={dot}>
            {STAGE_LABEL[stage] ?? stage.replace(/_/g, " ")}
        </Badge>
    );
}

// Timeline event kind (§3.3) -> a glyph from the panel's icon set + an accent
// fill class. Used by the profile feed.
export const KIND_META: Record<string, { icon: string; fill: string; label: string }> = {
    call: { icon: "chat", fill: "fill-primary-01", label: "Call" },
    whatsapp: { icon: "send", fill: "fill-primary-02", label: "WhatsApp" },
    support: { icon: "help", fill: "fill-primary-05", label: "Support" },
    booking: { icon: "calendar", fill: "fill-primary-01", label: "Booking" },
    purchase: { icon: "bag", fill: "fill-primary-02", label: "Purchase" },
    note: { icon: "feather", fill: "fill-t-secondary", label: "Note" },
    consent: { icon: "lock", fill: "fill-primary-03", label: "Consent" },
    campaign: { icon: "promote", fill: "fill-primary-01", label: "Campaign" },
    system: { icon: "info", fill: "fill-t-tertiary", label: "System" },
};

export function kindMeta(kind?: string) {
    return KIND_META[kind ?? ""] ?? KIND_META.system;
}

export function initials(name?: string): string {
    if (!name) return "?";
    const parts = name.trim().split(/\s+/).filter(Boolean);
    if (parts.length === 0) return "?";
    if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
    return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

export function fmtDate(d?: string | null): string {
    if (!d) return "—";
    try {
        return new Date(d).toLocaleDateString(undefined, {
            day: "numeric",
            month: "short",
            year: "numeric",
        });
    } catch {
        return d;
    }
}

export function fmtDateTime(d?: string | null): string {
    if (!d) return "—";
    try {
        return new Date(d).toLocaleString(undefined, {
            day: "numeric",
            month: "short",
            hour: "2-digit",
            minute: "2-digit",
        });
    } catch {
        return d;
    }
}

// Relative "2h ago" / "3d ago" — falls back to a short date past a week.
export function fmtRelative(d?: string | null): string {
    if (!d) return "—";
    let t: number;
    try {
        t = new Date(d).getTime();
    } catch {
        return d;
    }
    if (Number.isNaN(t)) return d;
    const diff = Date.now() - t;
    const min = Math.floor(diff / 60000);
    if (min < 1) return "just now";
    if (min < 60) return `${min}m ago`;
    const hr = Math.floor(min / 60);
    if (hr < 24) return `${hr}h ago`;
    const day = Math.floor(hr / 24);
    if (day < 7) return `${day}d ago`;
    return fmtDate(d);
}

// Action verb (§4.3 NBA) -> human label + accent + glyph for the NBA card.
// NOTE: `bg`/`fill` are FULL static class strings (not interpolated tones) —
// Tailwind 4's JIT only sees classes that appear literally in source, so a
// constructed `bg-${tone}/12` would be purged and render blank.
type NbaMeta = { label: string; icon: string; bg: string; fill: string };

export const NBA_META: Record<string, NbaMeta> = {
    place_call: { label: "Place a call", icon: "chat", bg: "bg-primary-01/12", fill: "fill-primary-01" },
    retry_call: { label: "Retry the call", icon: "chat", bg: "bg-primary-01/12", fill: "fill-primary-01" },
    send_whatsapp: { label: "Send WhatsApp", icon: "send", bg: "bg-primary-02/12", fill: "fill-primary-02" },
    reengage: { label: "Re-engage", icon: "promote", bg: "bg-primary-05/12", fill: "fill-primary-05" },
    nurture: { label: "Nurture", icon: "heart", bg: "bg-primary-02/12", fill: "fill-primary-02" },
    none: { label: "No action needed", icon: "check-circle", bg: "bg-b-surface1 dark:bg-shade-04/60", fill: "fill-t-secondary" },
};

export function nbaMeta(action?: string): NbaMeta {
    return (
        NBA_META[action ?? ""] ?? {
            label: (action ?? "Review").replace(/_/g, " "),
            icon: "magic-pencil",
            bg: "bg-primary-01/12",
            fill: "fill-primary-01",
        }
    );
}
