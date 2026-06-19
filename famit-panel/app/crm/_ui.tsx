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

// ── Temperature (lifecycle heat) — the single source CRM + Leads share ────────
//
// The founder's round-2 spec asks for a Hot/Warm/Cold/Dead "Temperature" column
// + filter EVERYWHERE a status filter appears. `lifecycle` is the canonical
// signal, but list rows don't always carry it — so `tempOf` mirrors the
// precedence of lib/report.ts `statusOf` (stage + outcome + score) to derive the
// temperature client-side, and degrades gracefully when fields are absent.
//
// Temperature -> Badge map lives here ONCE (Hot=danger/red, Warm=warning,
// Cold=info, Dead=neutral) and is imported wherever a temperature is shown, so
// CRM and Leads never drift.
export type Temperature = "hot" | "warm" | "cold" | "dead";

const TEMP_VARIANT: Record<Temperature, BadgeVariant> = {
    hot: "danger",
    warm: "warning",
    cold: "info",
    dead: "neutral",
};

const TEMP_LABEL: Record<Temperature, string> = {
    hot: "Hot",
    warm: "Warm",
    cold: "Cold",
    dead: "Dead",
};

const TEMP_DOT: Record<Temperature, boolean> = {
    hot: true,
    warm: true,
    cold: false,
    dead: false,
};

// Anything we can classify by temperature — contacts, leads, projected rows.
// Every field is optional so a partial payload never crashes the deriver.
export type TempLike = {
    lifecycle?: string | null;
    lifecycle_state?: string | null;
    stage?: string | null;
    status?: string | null;
    last_outcome?: string | null;
    outcome?: string | null;
    score?: number | null;
    conversion_prob?: number | null; // 0..1
    hot?: boolean | null;
    booked?: boolean | null;
};

// Pure: signals -> temperature. Honors an explicit lifecycle value first (the
// canonical source), otherwise derives it the way report.ts `statusOf` does:
// dead/booked > stage/outcome keywords > score bands > hot flag.
export function tempOf(row: TempLike): Temperature {
    const norm = (s?: string | null) => (s ?? "").toLowerCase().trim();

    // 1) Explicit lifecycle wins (booked collapses into hot for the heat axis).
    const explicit = norm(row.lifecycle) || norm(row.lifecycle_state);
    if (explicit === "hot" || explicit === "warm" || explicit === "cold" || explicit === "dead")
        return explicit as Temperature;
    if (explicit === "booked" || explicit === "won" || explicit === "converted") return "hot";

    const bag = [norm(row.stage), norm(row.status), norm(row.last_outcome), norm(row.outcome)];
    const has = (...keys: string[]) =>
        bag.some((v) => keys.some((k) => v === k || v.includes(k)));

    // Score may be 0..100 (score) or 0..1 (conversion_prob).
    let score: number | null = null;
    if (typeof row.score === "number") score = row.score;
    else if (typeof row.conversion_prob === "number")
        score = Math.round(row.conversion_prob * 100);

    // 2) Hard outcomes.
    if (has("opt_out", "opted_out", "not_interested", "dead", "lost")) return "dead";
    if (row.booked === true || has("booked", "won", "converted", "site_visit", "qualified", "interested"))
        return "hot";

    // 3) Flags + score bands.
    if (row.hot === true) return "hot";
    if (score != null) {
        if (score >= 70) return "hot";
        if (score >= 40) return "warm";
        if (score > 0) return "cold";
    }

    // 4) Engagement-ish stages with no score -> warm; brand-new -> cold.
    if (has("engaged", "contacted", "callback")) return "warm";
    return "cold";
}

export function TempBadge({
    lifecycle,
    row,
}: {
    // Pass an explicit temperature/lifecycle string OR a row to derive from.
    lifecycle?: string | null;
    row?: TempLike;
}) {
    const explicit = (lifecycle ?? "").toLowerCase().trim();
    const temp: Temperature =
        explicit === "hot" || explicit === "warm" || explicit === "cold" || explicit === "dead"
            ? (explicit as Temperature)
            : row
            ? tempOf(row)
            : "cold";
    return (
        <Badge variant={TEMP_VARIANT[temp]} dot={TEMP_DOT[temp]}>
            {TEMP_LABEL[temp]}
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

// Treat timezone-naive strings from the backend as UTC by appending Z if there is
// no timezone offset already present.  Without this, new Date("2026-06-14 10:00:00")
// is parsed as local time in the browser, causing a ~5.5h IST shift that makes
// recent events appear to have happened "5 days ago".
function toUTC(d: string): Date {
    // Already has tz info: ends with Z, +HH:MM, or -HH:MM
    if (/Z$|[+-]\d{2}:\d{2}$/.test(d.trim())) return new Date(d);
    // ISO with offset like +0530 (no colon)
    if (/[+-]\d{4}$/.test(d.trim())) return new Date(d);
    // Naive string — assume UTC
    return new Date(d.trim() + "Z");
}

const IST_FMT = new Intl.DateTimeFormat("en-IN", {
    timeZone: "Asia/Kolkata",
    dateStyle: "medium",
    timeStyle: "short",
});
const IST_DATE_FMT = new Intl.DateTimeFormat("en-IN", {
    timeZone: "Asia/Kolkata",
    dateStyle: "medium",
});

export function fmtDate(d?: string | null): string {
    if (!d) return "—";
    try {
        return IST_DATE_FMT.format(toUTC(d));
    } catch {
        return d;
    }
}

export function fmtDateTime(d?: string | null): string {
    if (!d) return "—";
    try {
        return IST_FMT.format(toUTC(d));
    } catch {
        return d;
    }
}

// Relative "2h ago" / "3d ago" — falls back to a short IST date past a week.
export function fmtRelative(d?: string | null): string {
    if (!d) return "—";
    let t: number;
    try {
        t = toUTC(d).getTime();
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
