"use client";

// Payments-owned premium primitives. Kept here (not in any app-wide component
// or globals.css) so the Payments page speaks the SAME world-class visual
// language as Billing / Calls / Signal — without touching a shared file. These
// mirror the patterns in `app/billing/_shared.tsx` (HeroCard, status pills,
// money formatting) so the two Money-section areas are visually consistent.

import Badge, { type BadgeVariant } from "@/components/Badge";
import Icon from "@/components/Icon";
import type { IntentStatus, ProviderStatus } from "./_api";

// ---- formatting ------------------------------------------------------------

const CURRENCY_SYMBOL: Record<string, string> = {
    INR: "₹",
    USD: "$",
    EUR: "€",
    GBP: "£",
};

export function money(n: number | null | undefined, currency = "INR"): string {
    if (n == null) return "—";
    const sym = CURRENCY_SYMBOL[currency] || (currency ? `${currency} ` : "");
    const body = n.toLocaleString(undefined, {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
    });
    return `${sym}${body}`;
}

export function moneyShort(n: number | null | undefined, currency = "INR"): string {
    if (n == null) return "—";
    const sym = CURRENCY_SYMBOL[currency] || (currency ? `${currency} ` : "");
    const abs = Math.abs(n);
    if (abs >= 1_000_000) return `${sym}${(n / 1_000_000).toFixed(1)}M`;
    if (abs >= 1_000) return `${sym}${(n / 1_000).toFixed(1)}k`;
    return `${sym}${n.toFixed(n % 1 === 0 ? 0 : 2)}`;
}

export function fmt(d: string | undefined | null): string {
    if (!d) return "—";
    const dt = new Date(d);
    if (isNaN(dt.getTime())) return d;
    return dt.toLocaleString(undefined, {
        month: "short",
        day: "numeric",
        hour: "numeric",
        minute: "2-digit",
    });
}

export function fmtRelative(d: string | undefined | null): string {
    if (!d) return "";
    const t = new Date(d).getTime();
    if (isNaN(t)) return "";
    const diff = Date.now() - t;
    const past = diff >= 0;
    const min = Math.round(Math.abs(diff) / 60000);
    const tag = (s: string) => (past ? `${s} ago` : `in ${s}`);
    if (min < 1) return "just now";
    if (min < 60) return tag(`${min}m`);
    const hr = Math.round(min / 60);
    if (hr < 24) return tag(`${hr}h`);
    const day = Math.round(hr / 24);
    return tag(`${day}d`);
}

// ---- semantic mapping ------------------------------------------------------

// Payment-intent lifecycle -> badge tone. Mirrors lib/badges semantics but
// owned here for the payments-specific vocabulary (refunded / expired / ...).
const INTENT_VARIANT: Record<IntentStatus, BadgeVariant> = {
    created: "neutral",
    issued: "info",
    paid: "success",
    failed: "danger",
    expired: "warning",
    refunded: "neutral",
    partially_refunded: "warning",
};

export function IntentBadge({ status }: { status?: IntentStatus | string | null }) {
    if (!status) return <span className="text-t-tertiary">—</span>;
    const variant = INTENT_VARIANT[status as IntentStatus] ?? "neutral";
    const dot = variant === "success" || variant === "info";
    return (
        <Badge variant={variant} dot={dot}>
            {String(status).replace(/_/g, " ")}
        </Badge>
    );
}

export function ProviderPill({
    status,
    label,
}: {
    status: ProviderStatus;
    label: string;
}) {
    const map: Record<ProviderStatus, { variant: BadgeVariant; text: string; dot?: boolean }> = {
        configured: { variant: "success", text: "Connected", dot: true },
        not_configured: { variant: "neutral", text: "Not connected" },
        error: { variant: "danger", text: "Error" },
    };
    const s = map[status] ?? map.not_configured;
    return (
        <div className="flex items-center justify-between gap-3 px-4 py-3 rounded-2xl bg-b-surface2 ring-1 ring-s-subtle ring-inset dark:bg-shade-04/30">
            <span className="text-body-2 font-medium text-t-primary">{label}</span>
            <Badge variant={s.variant} dot={s.dot}>
                {s.text}
            </Badge>
        </div>
    );
}

// ---- premium hero KPI card (billing-language, payments-owned) ---------------

export function HeroCard({
    label,
    glyph,
    glyphClass,
    value,
    loading,
    foot,
    accent,
    delay = 0,
    aside,
}: {
    label: string;
    glyph: string;
    glyphClass?: string;
    value: React.ReactNode;
    loading?: boolean;
    foot?: React.ReactNode;
    accent?: string;
    delay?: number;
    aside?: React.ReactNode;
}) {
    return (
        <div
            className="kpi rise-in group"
            style={delay ? { animationDelay: `${delay}ms` } : undefined}
        >
            {accent && (
                <span
                    aria-hidden
                    className="pointer-events-none absolute -top-16 -right-16 size-40 rounded-full opacity-[0.13] blur-2xl transition-opacity duration-500 group-hover:opacity-20"
                    style={{ background: accent }}
                />
            )}
            <div className="flex items-start justify-between gap-3">
                <div className="kpi-label">
                    <span className={`kpi-glyph ${glyphClass || ""}`}>
                        <Icon name={glyph} className="fill-inherit" />
                    </span>
                    {label}
                </div>
                {aside}
            </div>
            {loading ? (
                <div className="skeleton h-10 w-44" />
            ) : (
                <div className="kpi-value relative z-1">{value}</div>
            )}
            {foot && <div className="kpi-foot relative z-1">{foot}</div>}
        </div>
    );
}

// One labelled progress meter row (share of a total) — collections composition.
export function ShareRow({
    label,
    value,
    pct,
    color,
    badge,
    delay = 0,
}: {
    label: string;
    value: string;
    pct: number;
    color: string;
    badge?: React.ReactNode;
    delay?: number;
}) {
    return (
        <div className="rise-in" style={delay ? { animationDelay: `${delay}ms` } : undefined}>
            <div className="flex items-center justify-between gap-3 mb-1.5">
                <div className="flex items-center gap-2 min-w-0">
                    <span className="size-2.5 rounded-sm shrink-0" style={{ background: color }} />
                    <span className="text-body-2 text-t-primary truncate">{label}</span>
                    {badge}
                </div>
                <div className="flex items-center gap-2 shrink-0">
                    <span className="text-body-2 font-medium text-t-primary tabular-nums">{value}</span>
                    <span className="text-caption text-t-tertiary tabular-nums w-10 text-right">
                        {pct.toFixed(0)}%
                    </span>
                </div>
            </div>
            <div className="meter">
                <div
                    className="meter-fill"
                    style={{ width: `${Math.max(pct, value === "—" ? 0 : 2)}%`, background: color }}
                />
            </div>
        </div>
    );
}

export function ErrorBanner({ msg }: { msg: string }) {
    if (!msg) return null;
    return (
        <div className="mb-4 flex items-center gap-2 p-3.5 rounded-2xl bg-primary-03/8 border border-primary-03/20 text-primary-03 text-body-2">
            <Icon name="info" className="size-4 fill-primary-03 shrink-0" />
            {msg}
        </div>
    );
}

// The "gateway not connected" panel — the graceful dormant state. Shown whenever
// the backend reports the module is not_configured (no Razorpay/Stripe creds).
export function NotConfiguredPanel({
    providers,
}: {
    providers: { label: string; status: ProviderStatus }[];
}) {
    return (
        <div className="surface p-6 rise-in">
            <div className="flex items-start gap-4 max-sm:flex-col">
                <span className="shrink-0 inline-flex size-12 items-center justify-center rounded-2xl bg-primary-01/10">
                    <Icon name="wallet" className="size-6 fill-primary-01" />
                </span>
                <div className="min-w-0 flex-1">
                    <div className="text-sub-title-1 text-t-primary">
                        Payment gateway not connected yet
                    </div>
                    <p className="mt-1 text-body-2 text-t-secondary max-w-2xl">
                        Collections run fully end-to-end once a Razorpay (primary, INR) or Stripe
                        account is connected. Until then, payment links you create are saved here as
                        draft intents — no charges are made and nothing breaks. Connect a provider in
                        Settings to start collecting.
                    </p>
                    <div className="mt-4 grid grid-cols-2 gap-2 max-sm:grid-cols-1">
                        {providers.map((p) => (
                            <ProviderPill key={p.label} status={p.status} label={p.label} />
                        ))}
                    </div>
                </div>
            </div>
        </div>
    );
}

export const ghostBtnCls =
    "inline-flex items-center justify-center gap-2 h-9 px-3.5 rounded-full border border-s-subtle text-button text-t-secondary bg-b-surface2 transition-all hover:border-s-highlight hover:text-t-primary hover:shadow-widget active:scale-[0.98] disabled:opacity-50";

// Collections accent palette (chart series + share meters). CSS-var tokens only.
export const PAY_COLORS = [
    "var(--primary-02)", // green — paid
    "var(--primary-01)", // blue — issued/pending
    "var(--primary-05)", // amber — failed/at-risk
    "var(--primary-04)", // purple — refunded
];
