// Colocated presentational helpers for the Forms & Surveys workspace.
//
// Lives under app/forms (this page's own files) rather than lib/badges.tsx,
// which is shared and off-limits for this build. It REUSES the shared <Badge> /
// pill-* language (no new tokens) and just maps the forms vocabularies (status,
// kind, field type, sentiment) onto it so the page stays cohesive with the rest
// of the panel.

import Badge, { type BadgeVariant } from "@/components/Badge";
import type { FieldType, FormKind, FormStatus } from "./client";

// Publish lifecycle (core.update_form allows draft|published|closed).
const STATUS_VARIANT: Record<string, BadgeVariant> = {
    draft: "neutral",
    published: "success",
    closed: "danger",
};

const STATUS_LABEL: Record<string, string> = {
    draft: "Draft",
    published: "Published",
    closed: "Closed",
};

export function StatusBadge({ status }: { status?: FormStatus | string | null }) {
    if (!status) return <span className="text-t-tertiary">—</span>;
    const variant = STATUS_VARIANT[status] ?? "neutral";
    return (
        <Badge variant={variant} dot={variant === "success"}>
            {STATUS_LABEL[status] ?? status}
        </Badge>
    );
}

// form vs survey — different intent, different icon.
export function KindBadge({ kind }: { kind?: FormKind | string | null }) {
    const isSurvey = kind === "survey";
    return (
        <Badge variant={isSurvey ? "info" : "neutral"}>
            {isSurvey ? "Survey" : "Form"}
        </Badge>
    );
}

export function kindIcon(kind?: FormKind | string | null): string {
    return kind === "survey" ? "chart" : "font";
}

// Field-type metadata: a human label + an icon glyph from the panel's set, used
// in the schema editor and the field-type picker. Every icon name below exists
// in components/Icon (verified) — a missing name renders blank, so this is the
// allow-list of safe glyphs.
export const FIELD_TYPE_META: Record<
    FieldType,
    { label: string; icon: string; hint: string; hasOptions: boolean }
> = {
    text: { label: "Short text", icon: "font", hint: "A single line of text", hasOptions: false },
    textarea: { label: "Paragraph", icon: "list", hint: "A multi-line text area", hasOptions: false },
    email: { label: "Email", icon: "envelope", hint: "An email address", hasOptions: false },
    phone: { label: "Phone", icon: "chat", hint: "A phone number (feeds CRM)", hasOptions: false },
    number: { label: "Number", icon: "income", hint: "A numeric value", hasOptions: false },
    select: { label: "Dropdown", icon: "chevron", hint: "Pick one of several options", hasOptions: true },
    multiselect: { label: "Multi-select", icon: "list", hint: "Pick several options", hasOptions: true },
    checkbox: { label: "Checkbox", icon: "check-square", hint: "A yes/no toggle", hasOptions: false },
    date: { label: "Date", icon: "calendar", hint: "A calendar date", hasOptions: false },
    rating: { label: "Rating", icon: "star-fill", hint: "A numeric rating", hasOptions: false },
    nps: { label: "NPS (0–10)", icon: "promote", hint: "Net Promoter Score, 0–10", hasOptions: false },
    csat: { label: "CSAT (1–5)", icon: "heart", hint: "Satisfaction score, 1–5", hasOptions: false },
    hidden: { label: "Hidden", icon: "lock", hint: "Hidden value (not shown publicly)", hasOptions: false },
};

export function fieldTypeMeta(type?: string) {
    return (
        FIELD_TYPE_META[(type ?? "text") as FieldType] ?? {
            label: type ?? "Field",
            icon: "font",
            hint: "",
            hasOptions: false,
        }
    );
}

// Sentiment bucket -> badge (survey insights).
export function SentimentBadge({ sentiment }: { sentiment?: string | null }) {
    if (!sentiment) return <span className="text-t-tertiary">—</span>;
    const variant: BadgeVariant =
        sentiment === "promoter"
            ? "success"
            : sentiment === "detractor"
            ? "danger"
            : "warning";
    const label =
        sentiment.charAt(0).toUpperCase() + sentiment.slice(1);
    return <Badge variant={variant}>{label}</Badge>;
}

// Field-key allow-list, mirrors core._KEY_RE = ^[a-z0-9_]{1,40}$ exactly so we
// reject client-side before the round-trip (and surface a clear inline error).
export const FIELD_KEY_RE = /^[a-z0-9_]{1,40}$/;

// Derive a safe field key from a human label (lowercase, underscores, trimmed).
export function slugifyKey(label: string): string {
    return label
        .toLowerCase()
        .trim()
        .replace(/[^a-z0-9]+/g, "_")
        .replace(/^_+|_+$/g, "")
        .slice(0, 40);
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

// Render one stored answer value for the submissions table (lists, bools, etc).
export function fmtAnswer(val: unknown): string {
    if (val == null || val === "") return "—";
    if (Array.isArray(val)) return val.length ? val.join(", ") : "—";
    if (typeof val === "boolean") return val ? "Yes" : "No";
    return String(val);
}
