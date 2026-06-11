"use client";

// Shared helpers for the AI Manager section (formatting, semantic colour, small
// presentational bits). The page is now ONE route (`/ai-manager`) with three
// in-page tabs (Home / Try it / Setup) per the design system, so there is no
// masthead/pill-rail here any more — the title is the single `<Layout title>`
// and the tabs are the reference `Tabs` rhythm. Touches no app-wide component
// and no globals.css.

import Icon from "@/components/Icon";
import { type BadgeVariant } from "@/components/Badge";
import type { AimRiskLevel } from "./_lib";

// ---- shared formatting --------------------------------------------------

export function fmt(d?: string | null): string {
    if (!d) return "—";
    try {
        return new Date(d).toLocaleString();
    } catch {
        return d;
    }
}

export function fmtDate(d?: string | null): string {
    if (!d) return "—";
    try {
        return new Date(d).toLocaleDateString();
    } catch {
        return d;
    }
}

// ---- shared semantic colour language (single source) --------------------

// Risk level → badge tone (§6: L0 safe → L4 blocked).
export function riskVariant(r?: AimRiskLevel | string | null): BadgeVariant {
    switch ((r || "").toUpperCase()) {
        case "L0":
            return "success";
        case "L1":
            return "info";
        case "L2":
            return "warning";
        case "L3":
        case "L4":
            return "danger";
        default:
            return "neutral";
    }
}

// Authorized-user role → badge tone.
export function roleVariant(role?: string | null): BadgeVariant {
    switch ((role || "").toLowerCase()) {
        case "admin":
            return "danger";
        case "manager":
            return "info";
        case "operator":
            return "neutral";
        default:
            return "neutral";
    }
}

// ---- shared inline error banner (matches Billing) -----------------------

export function ErrorBanner({ msg }: { msg: string }) {
    if (!msg) return null;
    return (
        <div className="mb-4 flex items-center gap-2 p-3.5 rounded-2xl bg-primary-03/8 border border-primary-03/20 text-primary-03 text-body-2">
            <Icon name="info" className="size-4 fill-primary-03 shrink-0" />
            {msg}
        </div>
    );
}

// ---- premium dormant / empty panel (the PRIMARY state until creds land) -

export function DormantPanel({
    icon = "cube",
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

// ---- shared input class tokens (match the existing AI Manager forms) ----

export const inputCls = "input-base w-full h-11 px-4 rounded-2xl text-body-2";
export const selectCls = `${inputCls} appearance-none`;

// A small labelled field wrapper used across Setup + the user modal.
export function FormRow({
    label,
    hint,
    children,
}: {
    label: string;
    hint?: string;
    children: React.ReactNode;
}) {
    return (
        <div>
            <label className="block text-button mb-2 text-t-primary">{label}</label>
            {children}
            {hint && <p className="text-caption text-t-tertiary mt-1.5">{hint}</p>}
        </div>
    );
}

/* ============================================================ F1 additions
 * Test Console + Overview shared bits. The NLU parse `risk_level` is a SEPARATE
 * axis from the F2 setting enum (riskVariant above): it can be a 0–4 integer OR
 * a token ("safe" | "low" | "bulk" | "money" | "destructive" | "blocked"). We
 * normalise either form here, leaving the existing riskVariant() untouched.
 * ========================================================================== */

// Normalise a parse risk (int|string) to a 0–4 level. Unknown → 0 (treat as safe
// for COLOUR only; the engine's own gate, not this label, governs execution).
export function parseRiskLevel(r?: number | string | null): number {
    if (r == null) return 0;
    if (typeof r === "number") return Math.max(0, Math.min(4, Math.round(r)));
    const t = String(r).trim().toLowerCase();
    const asNum = Number(t.replace(/^l/, ""));
    if (Number.isFinite(asNum)) return Math.max(0, Math.min(4, Math.round(asNum)));
    switch (t) {
        case "safe":
        case "read":
            return 0;
        case "low":
            return 1;
        case "medium":
            return 2;
        case "bulk":
        case "high":
            return 3;
        case "money":
        case "spend":
        case "destructive":
        case "delete":
        case "blocked":
        case "block":
            return 4;
        default:
            return 0;
    }
}

const PARSE_RISK_META: { variant: BadgeVariant; label: string }[] = [
    { variant: "success", label: "Safe" }, // 0
    { variant: "info", label: "Low" }, // 1
    { variant: "warning", label: "Medium" }, // 2
    { variant: "danger", label: "High" }, // 3
    { variant: "danger", label: "Blocked" }, // 4
];

export function parseRiskVariant(r?: number | string | null): BadgeVariant {
    return PARSE_RISK_META[parseRiskLevel(r)].variant;
}

export function parseRiskLabel(r?: number | string | null): string {
    // Prefer the engine's own token when it's descriptive; else the level label.
    if (typeof r === "string" && r.trim() && !/^l?\d$/i.test(r.trim())) {
        const t = r.trim();
        return t.charAt(0).toUpperCase() + t.slice(1);
    }
    return PARSE_RISK_META[parseRiskLevel(r)].label;
}

// Map a command/status string to a badge tone (executed/denied/blocked/...).
export function statusVariant(s?: string | null): BadgeVariant {
    const t = (s || "").toLowerCase();
    if (/(executed|done|success|ok|complete|confirmed)/.test(t)) return "success";
    if (/(blocked|denied|reject|fail|error|lockout)/.test(t)) return "danger";
    if (/(needs_pin|needs_confirmation|pending|review|await)/.test(t)) return "warning";
    if (/(cancel)/.test(t)) return "neutral";
    return "neutral";
}

// ₹ from paise (backend money is INTEGER paise everywhere). null-safe.
export function rupees(minor?: number | null): string {
    if (minor == null) return "—";
    const r = minor / 100;
    return `₹${r.toLocaleString("en-IN", { maximumFractionDigits: r % 1 === 0 ? 0 : 2 })}`;
}

// A KPI metric tile — the .kpi utility language, matching the Billing HeroCard
// and the existing command-center HeroStat. Real signals only (no fake deltas).
export function AimStat({
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
            <div className="kpi-label">
                <span className={`kpi-glyph ${glyphClass || ""}`}>
                    <Icon name={glyph} className="fill-inherit" />
                </span>
                {label}
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
