"use client";

// Ad-Engine · SHARED helpers + widgets (W7-spine).
//
// The reusable pieces that were INLINE in app/ads/page.tsx, lifted here so every
// `_tabs/*` file imports them from ONE place (no drift, no duplication). Pure
// presentational Core_2 widgets + the backend status→tone/label maps; zero raw
// hex, every colour via tokens. Nothing here owns state beyond the toast type.

import type React from "react";
import Icon from "@/components/Icon";
import type { BadgeVariant } from "@/components/Badge";
import { fmtMoney } from "./_lib";
import type { AdsStatus } from "./_lib";

/* ------------------------------------------------------------ shared types */

// The hand-rolled toast payload (the page owns the timer; tabs raise messages).
export type Toast = { msg: string; type: "success" | "error" };

// The toast-raiser signature threaded from page.tsx into every tab.
export type ToastFn = (msg: string, type?: "success" | "error") => void;

// The uniform prop contract for the dormant/stub tabs (Creative / Leads /
// Analytics / Connections). The data-rich tabs (Command / Campaigns / Decisions
// / Guardrails) extend this with their own specific props in their own files.
export type AdsTabProps = {
    writable: boolean;
    loading: boolean;
    toast: ToastFn;
    refresh: () => void;
};

/* ------------------------------------------------------ status → tone/label */

// Map a backend status -> a Badge tone + a human label.
export function statusVariant(s: AdsStatus): BadgeVariant {
    if (s === "active") return "success";
    if (s === "paused") return "warning";
    if (s === "pending_approval") return "info";
    if (s === "dry_run") return "info";
    if (typeof s === "string" && s.startsWith("blocked")) return "danger";
    return "neutral";
}

export function statusLabel(s: AdsStatus): string {
    const map: Record<string, string> = {
        active: "Live",
        paused: "Paused",
        pending_approval: "Awaiting approval",
        dry_run: "Dry run",
        not_configured: "Not configured",
        draft: "Draft",
        blocked_cap_exceeded: "Cap reached",
        blocked_cpl_breach: "CPL breach",
        blocked_no_conversion_tracking: "No CPL tracking",
        blocked_not_approved: "Step-up needed",
        blocked_insufficient_funds: "Low balance",
    };
    return map[s] || s;
}

export function objectiveLabel(o: string): string {
    return (o || "")
        .replace(/^OUTCOME_/, "")
        .toLowerCase()
        .replace(/^\w/, (c) => c.toUpperCase());
}

export function providerLabel(p?: string): string {
    if (!p || p === "noop" || p === "not_configured") return "Not connected";
    return p.charAt(0).toUpperCase() + p.slice(1);
}

export function providerIcon(p?: string): string {
    if (p === "meta") return "facebook";
    if (p === "google") return "earth";
    return "promote";
}

export function moveVariant(m: string): BadgeVariant {
    if (m === "scale_winner") return "success";
    if (m === "kill_loser") return "danger";
    return "neutral";
}

export function moveLabel(m: string): string {
    const map: Record<string, string> = {
        scale_winner: "Scale winner",
        kill_loser: "Kill loser",
        hold: "Hold",
    };
    return map[m] || m;
}

export function moveReason(r: string): string {
    const map: Record<string, string> = {
        cpl_at_or_below_target: "CPL at or below target",
        cpl_above_target: "CPL above target",
        below_min_sample: "Sample too small to act",
        blocked_no_conversion_tracking: "No conversion tracking",
    };
    return map[r] || r.replace(/_/g, " ");
}

/* ------------------------------------------------------------ shared widgets */

// The premium "coming soon / not configured" panel — the PRIMARY state until the
// backend router is mounted and ad-platform creds land. On-brand, never an error.
export function DormantPanel({
    icon = "promote",
    title,
    sub,
    children,
}: {
    icon?: string;
    title: string;
    sub: string;
    children?: React.ReactNode;
}) {
    return (
        <div className="state-block">
            <span className="state-glyph">
                <Icon name={icon} className="fill-inherit" />
            </span>
            <div className="state-title">{title}</div>
            <div className="state-sub max-w-md mx-auto">{sub}</div>
            {children}
        </div>
    );
}

export function HeroStat({
    label,
    glyph,
    glyphClass,
    value,
    foot,
    accent,
    delay = 0,
    loading,
}: {
    label: string;
    glyph: string;
    glyphClass?: string;
    value: React.ReactNode;
    foot?: React.ReactNode;
    accent?: string;
    delay?: number;
    loading?: boolean;
}) {
    return (
        <div className="kpi rise-in group" style={delay ? { animationDelay: `${delay}ms` } : undefined}>
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
            </div>
            {loading ? (
                <div className="skeleton h-9 w-28 mt-1" />
            ) : (
                <div className="kpi-value relative z-1 !text-h4">{value}</div>
            )}
            {foot && <div className="kpi-foot relative z-1">{foot}</div>}
        </div>
    );
}

export function ConfigRow({
    icon,
    label,
    hint,
    children,
}: {
    icon: string;
    label: string;
    hint: string;
    children: React.ReactNode;
}) {
    return (
        <div className="flex items-center justify-between gap-4 py-3.5">
            <div className="flex items-center gap-3 min-w-0">
                <span className="grid place-items-center size-9 shrink-0 rounded-xl bg-b-surface2 ring-1 ring-s-subtle fill-t-secondary">
                    <Icon name={icon} className="size-4.5 fill-inherit" />
                </span>
                <div className="min-w-0">
                    <div className="text-body-2 text-t-primary truncate">{label}</div>
                    <div className="text-caption text-t-tertiary truncate">{hint}</div>
                </div>
            </div>
            <div className="shrink-0">{children}</div>
        </div>
    );
}

export function FlowStep({ n, icon, title, text }: { n: number; icon: string; title: string; text: string }) {
    return (
        <div className="relative p-4 rounded-2xl bg-b-surface2 ring-1 ring-s-subtle ring-inset dark:bg-shade-04/30">
            <div className="flex items-center gap-2 mb-1.5">
                <span className="grid place-items-center size-7 rounded-full bg-b-surface1 ring-1 ring-s-subtle fill-primary-01 dark:bg-shade-04">
                    <Icon name={icon} className="size-4 fill-inherit" />
                </span>
                <span className="text-caption text-t-tertiary tabular-nums">Step {n}</span>
            </div>
            <div className="text-sub-title-2 text-t-primary">{title}</div>
            <div className="text-caption text-t-secondary mt-1">{text}</div>
        </div>
    );
}

export function GuardCard({ icon, title, body }: { icon: string; title: string; body: string }) {
    return (
        <div className="lift group flex items-start gap-3 p-4 rounded-2xl bg-b-surface2 ring-1 ring-s-subtle ring-inset dark:bg-shade-04/30">
            <span className="grid place-items-center size-9 shrink-0 rounded-xl bg-b-surface1 ring-1 ring-s-subtle fill-primary-01 dark:bg-shade-04">
                <Icon name={icon} className="size-4.5 fill-inherit" />
            </span>
            <div className="min-w-0 flex-1">
                <div className="text-sub-title-2 text-t-primary">{title}</div>
                <div className="text-caption text-t-secondary mt-1">{body}</div>
            </div>
        </div>
    );
}

// Re-export the toast helper's companion formatter so a tab can `import { fmtMoney }
// from "../_shared"` alongside the widgets if it prefers one import source. (The
// canonical home stays _lib.ts; this is a convenience pass-through.)
export { fmtMoney };
