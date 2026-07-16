"use client";

// Shared helpers for the Billing sub-pages — ported to the reference
// Income/* visual language. Each page sets its single title via
// <Layout title="..."> (NO PageHeader, NO eyebrow, NO subtitle). Cross-route
// navigation is a plain token-based pill row (BillingTabs), rendered in the
// page body the way the reference puts its in-card controls — never as a
// masthead. Presentational primitives below mirror the reference Balance
// "Statistics" strip and the Countries cost-share bar so the whole Billing
// area looks identical to the reference money pages.

import type { VendorStatus } from "@/lib/api";
import Badge, { type BadgeVariant } from "@/components/Badge";
import Icon from "@/components/Icon";
import ProviderLogo from "@/components/ProviderLogo";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
    ResponsiveContainer,
    AreaChart,
    Area,
} from "recharts";

// ---- cross-route tab strip (replaces the old PageHeader masthead) ----------
// Plain pill row matching the reference Tabs aesthetic. No title/eyebrow/
// subtitle here — the page title lives in <Layout title>.
const BILLING_TABS = [
    { label: "Overview", href: "/billing/overview" },
    { label: "Vendors", href: "/billing/vendors" },
    { label: "Spending", href: "/billing/explorer" },
    { label: "Plan", href: "/billing/plan" },
    { label: "Audit", href: "/billing/audit" },
    // ROUND-2 §1b — Money is now ONE rail entry; Payments (collections) joins the
    // billing tab hub instead of being a separate rail child. /payments mounts
    // <BillingTabs /> so it lives inside this same strip; active-state keys off
    // pathname below (exact `/payments` match — it is not under /billing/*).
    { label: "Payments", href: "/payments" },
];

export function BillingTabs() {
    const pathname = usePathname();
    return (
        <div className="flex flex-wrap gap-1 mb-5 max-md:mb-4">
            {BILLING_TABS.map((t) => {
                const active =
                    pathname === t.href ||
                    (t.href.includes("/vendors") && pathname.startsWith("/billing/vendors"));
                return (
                    <Link
                        key={t.href}
                        href={t.href}
                        className={`flex justify-center items-center h-12 px-5.5 rounded-full border text-button transition-colors hover:text-t-primary ${
                            active
                                ? "border-s-stroke2 text-t-primary"
                                : "border-transparent text-t-secondary"
                        }`}
                    >
                        {t.label}
                    </Link>
                );
            })}
        </div>
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

// Vendor-config status on the shared token-based Badge — matches the pills
// used across Dashboard / Calls / Leads. Same props as before.
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

// One inline error banner, token-based (no raw red hex).
export function ErrorBanner({ msg }: { msg: string }) {
    if (!msg) return null;
    return (
        <div className="mb-4 flex items-center gap-2 p-3.5 rounded-3xl bg-primary-03/8 border border-primary-03/20 text-primary-03 text-body-2">
            <Icon name="info" className="size-4 fill-primary-03 shrink-0" />
            {msg}
        </div>
    );
}

// Compact money for chart axes / dense chips (12.3k / 1.2M). Kept for [id].
export function moneyShort(n: number | null | undefined, currency: string): string {
    if (n == null) return "—";
    const sym = currency ? `${currency} ` : "";
    const abs = Math.abs(n);
    if (abs >= 1_000_000) return `${sym}${(n / 1_000_000).toFixed(1)}M`;
    if (abs >= 1_000) return `${sym}${(n / 1_000).toFixed(1)}k`;
    return `${sym}${n.toFixed(n % 1 === 0 ? 0 : 2)}`;
}

// Vendor brand accents for the cost-share bars. Cycles if more vendors than
// colors. Token-only (no raw hex).
export const VENDOR_COLORS = [
    "var(--primary-01)",
    "var(--primary-02)",
    "var(--primary-04)",
    "var(--primary-05)",
    "var(--chart-green)",
    "var(--primary-03)",
];

// ---- reference "Balance" statistics strip --------------------------------
// Ported from templates/Income/StatementsPage/Statistics: an icon circle, a
// sub-title-1 label, and a big number. Horizontal flex of these inside a Card,
// divided by hairlines. No fabricated % deltas (real signals only).
export function StatStrip({ children }: { children: React.ReactNode }) {
    return (
        <div className="card max-md:overflow-hidden mb-3">
            <div className="relative">
                <div className="flex gap-8 p-5 max-lg:gap-6 max-lg:p-3 max-md:overflow-auto max-md:scrollbar-none max-md:-mx-3 max-md:px-6">
                    {children}
                </div>
            </div>
        </div>
    );
}

export function StatItem({
    title,
    icon,
    value,
    foot,
    loading,
}: {
    title: string;
    icon: string;
    value: React.ReactNode;
    foot?: React.ReactNode;
    loading?: boolean;
}) {
    return (
        <div className="flex-1 pr-6 border-r border-s-subtle last:border-r-0 max-lg:last:border-r-0 max-md:w-60 max-md:shrink-0 max-md:flex-auto">
            <div className="flex items-center justify-center size-16 mb-8 rounded-full bg-b-surface1 max-lg:mb-5">
                <Icon className="fill-t-primary" name={icon} />
            </div>
            <div className="text-sub-title-1 mb-2">{title}</div>
            {loading ? (
                <div className="h-9 w-32 rounded-lg bg-b-surface1 animate-pulse" />
            ) : (
                <div className="text-h3 tabular-nums max-lg:text-h4">{value}</div>
            )}
            {foot && (
                <div className="mt-2 text-body-2 text-t-tertiary">{foot}</div>
            )}
        </div>
    );
}

// ---- reference "Countries" cost-share bar --------------------------------
// Ported from components/CountryItem: a colour swatch, label, value, and a
// track+fill share meter. Real share (vendor cost / grand total) only.
export function BarRow({
    label,
    value,
    pct,
    color,
    badge,
    provider,
}: {
    label: string;
    value: string;
    pct: number; // 0..100
    color: string;
    badge?: React.ReactNode;
    provider?: string; // when set, lead with the REAL vendor logo, not a swatch
}) {
    return (
        <div className="flex items-center">
            {provider ? (
                <ProviderLogo provider={provider} size={38} className="!rounded-xl" />
            ) : (
                <span className="size-3 rounded-sm shrink-0" style={{ background: color }} />
            )}
            <div className="grow pl-4 min-w-0">
                <div className="flex justify-between gap-3 mb-2 text-sub-title-2">
                    <span className="flex items-center gap-2 min-w-0">
                        <span className="truncate">{label}</span>
                        {badge}
                    </span>
                    <span className="shrink-0 tabular-nums">{value}</span>
                </div>
                <div className="relative h-3 rounded-[2px] bg-shade-09 dark:bg-shade-04">
                    <div
                        className="absolute top-0 left-0 bottom-0 rounded-[2px]"
                        style={{ width: `${Math.max(pct, 2)}%`, background: color, opacity: 0.85 }}
                    />
                </div>
            </div>
        </div>
    );
}

// Tiny inline area sparkline (real timeseries only). Used by the vendor [id]
// detail page.
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
