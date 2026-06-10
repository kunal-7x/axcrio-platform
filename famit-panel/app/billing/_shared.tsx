"use client";

// Shared helpers for the Billing sub-pages. Kept tiny + presentational so each
// page stays focused on its own endpoint. Billing-owned premium primitives
// (hero cards, sparkline, cost-share bars, donut) live here so the whole
// Billing area speaks ONE world-class visual language without touching any
// app-wide component or globals.css.

import type { VendorStatus } from "@/lib/api";
import Badge, { type BadgeVariant } from "@/components/Badge";
import Icon from "@/components/Icon";
import Link from "next/link";
import { usePathname } from "next/navigation";
import PageHeader from "@/components/PageHeader";
import {
    ResponsiveContainer,
    AreaChart,
    Area,
    PieChart,
    Pie,
    Cell,
} from "recharts";

// Shared Billing masthead — the unified PageHeader + a tab strip so every
// billing sub-page shares one premium header and is navigable between tabs.
const BILLING_TABS = [
    { label: "Overview", href: "/billing/overview" },
    { label: "Vendors", href: "/billing/vendors" },
    { label: "Cost Explorer", href: "/billing/explorer" },
    { label: "Audit", href: "/billing/audit" },
    { label: "Plan & Ledger", href: "/billing/plan" },
];

export function BillingHeader({
    title,
    subtitle,
    actions,
}: {
    title: string;
    subtitle?: React.ReactNode;
    actions?: React.ReactNode;
}) {
    const pathname = usePathname();
    return (
        <>
            <PageHeader eyebrow="Billing" title={title} subtitle={subtitle} actions={actions} />
            <div className="flex items-center gap-1 mb-5 p-1 rounded-full bg-b-surface2 ring-1 ring-s-subtle w-fit max-w-full overflow-x-auto scrollbar-none">
                {BILLING_TABS.map((t) => {
                    const active = pathname === t.href || (t.href.includes("/vendors") && pathname.startsWith("/billing/vendors"));
                    return (
                        <Link
                            key={t.href}
                            href={t.href}
                            className={`shrink-0 inline-flex items-center h-8 px-3.5 rounded-full text-button transition-colors ${
                                active
                                    ? "bg-b-surface1 text-t-primary shadow-widget dark:bg-shade-04"
                                    : "text-t-secondary hover:text-t-primary"
                            }`}
                        >
                            {t.label}
                        </Link>
                    );
                })}
            </div>
        </>
    );
}

export function money(n: number | null | undefined, currency: string): string {
    if (n == null) return "—";
    return `${currency || ""} ${n.toFixed(2)}`.trim();
}

// Map a call outcome string to a semantic badge tone. Shared by the explorer
// and plan ledger so call rows speak the same status language.
export function outcomeVariant(
    outcome: string
): "success" | "danger" | "warning" | "neutral" {
    const o = outcome.toLowerCase();
    if (/(connect|complete|success|answered|interested|booked|converted)/.test(o)) return "success";
    if (/(fail|error|declin|reject|no_?answer|busy|unreach|disconnect)/.test(o)) return "danger";
    if (/(voicemail|callback|pending|partial)/.test(o)) return "warning";
    return "neutral";
}

export function fmt(d: string | undefined): string {
    if (!d) return "—";
    try {
        return new Date(d).toLocaleString();
    } catch {
        return d;
    }
}

// Vendor-config status, now on the shared token-based Badge so it matches the
// pills used across Dashboard / Calls / Leads. Same props as before.
export function StatusBadge({ status, stale }: { status: VendorStatus; stale?: boolean }) {
    const map: Record<VendorStatus, { label: string; variant: BadgeVariant; dot?: boolean }> = {
        configured: stale
            ? { label: "Live · stale", variant: "warning", dot: true }
            : { label: "Live", variant: "success", dot: true },
        not_configured: { label: "Not configured", variant: "neutral" },
        error: { label: "Error", variant: "danger" },
    };
    const s = map[status] ?? map.error;
    return (
        <Badge variant={s.variant} dot={s.dot}>
            {s.label}
        </Badge>
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

export const selectCls =
    "h-10 px-3 border border-s-stroke2 rounded-2xl text-body-2 text-t-primary outline-none bg-transparent transition-colors hover:border-s-highlight focus:border-s-focus";

export const btnCls =
    "inline-flex items-center justify-center gap-2 h-10 px-4 border border-s-stroke2 rounded-2xl text-button text-t-secondary transition-colors hover:border-s-highlight hover:text-t-primary disabled:opacity-50";

// A pill-shaped primary refresh button used in the sub-page toolbars. Same
// behaviour as btnCls (a plain styled <button>), just the premium variant.
export const ghostBtnCls =
    "inline-flex items-center justify-center gap-2 h-9 px-3.5 rounded-full border border-s-subtle text-button text-t-secondary bg-b-surface2 transition-all hover:border-s-highlight hover:text-t-primary hover:shadow-widget active:scale-[0.98] disabled:opacity-50";

// ---- premium presentational primitives (billing-owned) --------------------

// Compact money for chart axes / dense chips. Keeps the symbol, trims to a
// readable magnitude (12.3k / 1.2M) so big numbers never overflow a chip.
export function moneyShort(n: number | null | undefined, currency: string): string {
    if (n == null) return "—";
    const sym = currency ? `${currency} ` : "";
    const abs = Math.abs(n);
    if (abs >= 1_000_000) return `${sym}${(n / 1_000_000).toFixed(1)}M`;
    if (abs >= 1_000) return `${sym}${(n / 1_000).toFixed(1)}k`;
    return `${sym}${n.toFixed(n % 1 === 0 ? 0 : 2)}`;
}

// Vendor brand accents (chart series + share bars). Cycles if more vendors
// than colors. Pulled from the existing chart token palette.
export const VENDOR_COLORS = [
    "var(--primary-01)", // blue
    "var(--primary-02)", // green
    "var(--primary-04)", // purple
    "var(--primary-05)", // amber
    "var(--chart-green)",
    "#FF6A55",
];

// Hero metric card. Big tabular number, eyebrow label with glyph chip, a
// footer slot (real signal — share, count, sparkline), and an optional accent
// spotlight. Built on the .kpi utility so it matches the app KPI language.
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
    accent?: string; // css color for the corner spotlight
    delay?: number;
    aside?: React.ReactNode; // right-aligned content (e.g. sparkline)
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

// Tiny inline area sparkline for a hero card (real timeseries only).
export function Sparkline({
    data,
    color = "var(--primary-01)",
    width = 116,
    height = 40,
}: {
    data: { cost: number }[];
    color?: string;
    width?: number;
    height?: number;
}) {
    if (!data || data.length < 2) return null;
    const id = `spark-${Math.random().toString(36).slice(2, 8)}`;
    return (
        <div style={{ width, height }} className="shrink-0">
            <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={data} margin={{ top: 4, right: 0, left: 0, bottom: 0 }}>
                    <defs>
                        <linearGradient id={id} x1="0" y1="0" x2="0" y2="1">
                            <stop offset="0%" stopColor={color} stopOpacity={0.35} />
                            <stop offset="100%" stopColor={color} stopOpacity={0} />
                        </linearGradient>
                    </defs>
                    <Area
                        type="monotone"
                        dataKey="cost"
                        stroke={color}
                        strokeWidth={2}
                        fill={`url(#${id})`}
                        isAnimationActive={false}
                        dot={false}
                    />
                </AreaChart>
            </ResponsiveContainer>
        </div>
    );
}

// Donut composition of real per-vendor cost. Center shows total + label.
export function CostDonut({
    slices,
    centerValue,
    centerLabel,
    size = 168,
}: {
    slices: { name: string; value: number; color: string }[];
    centerValue: string;
    centerLabel: string;
    size?: number;
}) {
    const positive = slices.filter((s) => s.value > 0);
    return (
        <div className="relative shrink-0" style={{ width: size, height: size }}>
            <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                    <Pie
                        data={positive.length ? positive : [{ name: "—", value: 1, color: "var(--stroke-stroke2)" }]}
                        dataKey="value"
                        innerRadius={size * 0.34}
                        outerRadius={size * 0.48}
                        startAngle={90}
                        endAngle={-270}
                        paddingAngle={positive.length > 1 ? 2 : 0}
                        stroke="none"
                        isAnimationActive={false}
                    >
                        {(positive.length ? positive : [{ color: "var(--stroke-stroke2)" }]).map((s, i) => (
                            <Cell key={i} fill={s.color} />
                        ))}
                    </Pie>
                </PieChart>
            </ResponsiveContainer>
            <div className="absolute inset-0 flex flex-col items-center justify-center text-center">
                <div className="text-h6 text-t-primary tabular-nums leading-tight">{centerValue}</div>
                <div className="text-caption text-t-tertiary mt-0.5">{centerLabel}</div>
            </div>
        </div>
    );
}

// One row of the cost-share breakdown: label, value, and a real share meter
// (vendor cost / grand total). No fabricated period deltas — pure composition.
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
    pct: number; // 0..100
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
                    style={{ width: `${Math.max(pct, 2)}%`, background: color }}
                />
            </div>
        </div>
    );
}
