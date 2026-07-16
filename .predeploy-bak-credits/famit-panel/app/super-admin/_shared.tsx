"use client";

// Shared helpers for the Super Admin Control Center sub-pages (CL-F1).
//
// This is the ADMIN PLANE — the sharpest knife. The backend middleware
// (require_super_admin, which EXCLUDES the legacy static-password auth) is the
// real boundary; everything here is the admin-only fleet *view*. We reuse the
// app shell + the billing-area premium primitives (HeroCard / ErrorBanner) so
// the whole Super Admin surface speaks the same world-class "Signal" language
// as the rest of the panel — never invented from scratch.
//
// Kept tiny + presentational. The ONE net-new control-plane primitive here is
// `StatusPill` (design/control-ui.md §5): a vendor account-status → Badge map.

import Link from "next/link";
import { usePathname } from "next/navigation";
import Icon from "@/components/Icon";
import Badge, { type BadgeVariant } from "@/components/Badge";
import type { VendorAccountStatus } from "@/lib/api";

// ---- self-contained presentational primitives -----------------------------
// These used to be re-exported from `@/app/billing/_shared`, but that coupled
// the admin plane to a sibling unit's private file (which has since been
// refactored, breaking us). Per the W2 charter the Super-Admin area depends ONLY
// on the W1 shell (Icon/Card/Badge) + @theme tokens — so we own these locally.
// Pure, token-based, dark-mode safe; no raw hex.

// Ghost (icon + label) action button — used for every "Refresh" affordance.
export const ghostBtnCls =
    "inline-flex items-center gap-2 h-10 px-4 rounded-full text-button text-t-secondary border border-s-subtle transition-all hover:border-s-highlight hover:text-t-primary disabled:opacity-50 disabled:cursor-not-allowed";

// One inline error banner, token-based (no raw red hex). Mirrors the reference
// inline-message treatment.
export function ErrorBanner({ msg }: { msg: string }) {
    if (!msg) return null;
    return (
        <div className="mb-4 flex items-center gap-2 p-3.5 rounded-3xl bg-primary-03/8 border border-primary-03/20 text-primary-03 text-body-2">
            <Icon name="info" className="size-4 fill-primary-03 shrink-0" />
            {msg}
        </div>
    );
}

// KPI hero tile — the fleet/KPI stat card. Built on the shared `.kpi` utility
// (globals.css, W1) plus an optional left accent rule. Ported from the reference
// Overview stat tiles; real signals only, no fabricated deltas.
export function HeroCard({
    label,
    glyph,
    glyphClass,
    accent,
    value,
    foot,
    loading,
    delay = 0,
}: {
    label: string;
    glyph: string;
    glyphClass?: string;
    accent?: string;
    value: React.ReactNode;
    foot?: React.ReactNode;
    loading?: boolean;
    delay?: number;
}) {
    return (
        <div
            className="kpi rise-in relative overflow-hidden"
            style={delay ? { animationDelay: `${delay}ms` } : undefined}
        >
            {accent && (
                <span
                    className="absolute left-0 top-0 bottom-0 w-1 rounded-r-full"
                    style={{ background: accent }}
                    aria-hidden
                />
            )}
            <div className="kpi-label">
                <span className={`kpi-glyph ${glyphClass || "fill-t-secondary"}`}>
                    <Icon name={glyph} className="fill-inherit" />
                </span>
                {label}
            </div>
            {loading ? (
                <div className="skeleton h-9 w-24 mt-1" />
            ) : (
                <div className="kpi-value">{value}</div>
            )}
            {foot && <div className="kpi-foot">{foot}</div>}
        </div>
    );
}

// ---- Section sub-nav (tab strip) ------------------------------------------
// REFERENCE-ALIGNED (ui-design-principles.md §2, §7): the page title is a SINGLE
// clean line rendered ONCE by `Layout`/`Header` (text-h4) — NO eyebrow, NO
// subtitle, NO second stacked heading. So AdminHeader renders ONLY the section
// sub-nav (the pill tab strip that lets the admin move between the Control pages)
// plus an optional right-aligned actions slot. The `title`/`subtitle` props are
// kept in the type so existing callers compile, but `subtitle` is intentionally
// IGNORED and `title` is no longer re-rendered (Layout owns it). This kills the
// "two stacked headings + subtitle" clutter the founder rejects.
const ADMIN_TABS = [
    { label: "Overview", href: "/super-admin" },
    { label: "Clients", href: "/super-admin/clients" },
    { label: "Vendors", href: "/super-admin/vendors" },
    // CL-F3 — Feature Flags / Plans / Usage / Audit (these 4 pages).
    { label: "Feature Flags", href: "/super-admin/flags" },
    { label: "Plans", href: "/super-admin/plans" },
    // Per-tenant Sidebar Builder — drag/show/hide/relabel any tenant's sidebar.
    { label: "Sidebar", href: "/super-admin/sidebar" },
    { label: "Usage", href: "/super-admin/usage" },
    { label: "Audit", href: "/super-admin/audit" },
    // LPR — platform LLM/STT provider keys (Groq/Sarvam/SambaNova/OpenRouter).
    { label: "API Keys", href: "/super-admin/api-keys" },
    // Universal Provider / Connector registry (the all-tenants console twin).
    { label: "Integrations", href: "/super-admin/integrations" },
];

export function AdminHeader({
    title: _title,
    subtitle: _subtitle,
    actions,
}: {
    /** @deprecated the page title is rendered once by `Layout title=…` (Header). */
    title?: string;
    /** @deprecated ignored — reference headers have no subtitle. */
    subtitle?: React.ReactNode;
    actions?: React.ReactNode;
}) {
    const pathname = usePathname();
    return (
        <div className="flex items-center justify-between gap-4 mb-5 flex-wrap">
            {/* ROUND-2 §1c — transparent-pill tab strip, matching BillingTabs (the
                canon). Was the grey-box "segmented control" (bg-b-surface2 ring +
                bg-b-surface1 shadow active chip); now a flat rounded-full border pill
                row: inactive = border-transparent text-t-secondary, active =
                border-s-stroke2 text-t-primary. Identical idiom to app/billing
                BillingTabs so every tab strip in the panel reads the same. The
                ADMIN_TABS list + usePathname active logic are UNCHANGED. */}
            <div className="flex flex-wrap gap-1 max-w-full overflow-x-auto scrollbar-none">
                {ADMIN_TABS.map((t) => {
                    const active =
                        pathname === t.href ||
                        (t.href === "/super-admin/vendors" && pathname.startsWith("/super-admin/vendors"));
                    return (
                        <Link
                            key={t.href}
                            href={t.href}
                            className={`shrink-0 flex justify-center items-center h-12 px-5.5 rounded-full border text-button transition-colors hover:text-t-primary ${
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
            {actions && <div className="flex items-center gap-3 shrink-0">{actions}</div>}
        </div>
    );
}

// ---- StatusPill (design/control-ui.md §5) --------------------------------
// active → success · trial → info · suspended → warning · disabled → danger ·
// expired → neutral. Pure Badge map — the ONLY net-new control-plane primitive,
// and it is built entirely from the existing token-based Badge.
const STATUS_MAP: Record<VendorAccountStatus, { label: string; variant: BadgeVariant; dot?: boolean }> = {
    active: { label: "Active", variant: "success", dot: true },
    trial: { label: "Trial", variant: "info", dot: true },
    suspended: { label: "Suspended", variant: "warning", dot: true },
    disabled: { label: "Disabled", variant: "danger" },
    expired: { label: "Expired", variant: "neutral" },
};

export function StatusPill({ status }: { status?: VendorAccountStatus }) {
    const s = STATUS_MAP[status ?? "active"] ?? STATUS_MAP.active;
    return (
        <Badge variant={s.variant} dot={s.dot}>
            {s.label}
        </Badge>
    );
}

// ---- formatting helpers ---------------------------------------------------
export function fmtDate(d?: string): string {
    if (!d) return "—";
    try {
        return new Date(d).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
    } catch {
        return d;
    }
}

export function fmtDateTime(d?: string): string {
    if (!d) return "—";
    try {
        return new Date(d).toLocaleString();
    } catch {
        return d;
    }
}

// Compact integer ("12.3k") for KPI tiles so large fleet counts never overflow.
export function num(n: number | null | undefined): string {
    if (n == null) return "—";
    const abs = Math.abs(n);
    if (abs >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
    if (abs >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
    return String(n);
}

// "2 days ago" style relative recency for the last-activity column.
export function ago(d?: string): string {
    if (!d) return "—";
    const t = new Date(d).getTime();
    if (Number.isNaN(t)) return "—";
    const s = Math.max(0, (Date.now() - t) / 1000);
    if (s < 60) return "just now";
    const m = s / 60;
    if (m < 60) return `${Math.floor(m)}m ago`;
    const h = m / 60;
    if (h < 24) return `${Math.floor(h)}h ago`;
    const days = h / 24;
    if (days < 30) return `${Math.floor(days)}d ago`;
    const mo = days / 30;
    if (mo < 12) return `${Math.floor(mo)}mo ago`;
    return `${Math.floor(mo / 12)}y ago`;
}

// ============================================================================
// CL-F3 ADDITIONS — Feature Flags / Plans / Usage / Audit chrome + helpers.
// Appended (never edits CL-F1's exports above). The Flags/Plans/Usage/Audit
// pages import from here so the whole Super-Admin area shares one vocabulary.
// ============================================================================

// The Flags/Plans/Usage/Audit pages use this name; it IS the shared AdminHeader
// (one masthead + the full tab strip). Aliased so a future rename of either side
// can't desync the two halves of this shared file.
export const SuperAdminHeaderF3 = AdminHeader;

import { useRouter } from "next/navigation";
import { useEffect } from "react";
import Spinner from "@/components/Spinner";
import { useMe, isAdmin } from "@/lib/auth";
import type { FeatureMode } from "@/lib/api";

// Admin gate (cosmetic — the server is the real boundary: every /admin/* route
// is require_super_admin, 403 for vendors/legacy-pw). While /me loads we show a
// spinner; a confirmed non-admin is bounced to "/" (does-not-exist UX). Wrap a
// page body in this so a vendor who guesses the URL never sees the chrome.
export function SuperAdminGuard({ children }: { children: React.ReactNode }) {
    const { me, loading } = useMe();
    const router = useRouter();
    const admin = isAdmin(me);
    useEffect(() => {
        if (!loading && me && !admin) router.replace("/");
    }, [loading, me, admin, router]);
    if (loading && !me) {
        return (
            <div className="flex items-center justify-center py-32">
                <Spinner />
            </div>
        );
    }
    if (me && !admin) return null;
    return <>{children}</>;
}

// mode -> badge (the 3-state HIDE/LOCK/ON language).
export const MODE_META: Record<FeatureMode, { label: string; variant: BadgeVariant; dot?: boolean }> = {
    on: { label: "On", variant: "success", dot: true },
    locked: { label: "Locked", variant: "warning" },
    hidden: { label: "Hidden", variant: "neutral" },
};

export function ModeBadge({ mode }: { mode: FeatureMode }) {
    const m = MODE_META[mode] ?? MODE_META.hidden;
    return (
        <Badge variant={m.variant} dot={m.dot}>
            {m.label}
        </Badge>
    );
}

// The ordered 3-state cycle (On -> Locked -> Hidden), used by the segmented control.
export const MODE_ORDER: FeatureMode[] = ["on", "locked", "hidden"];

// Provenance pill: where an effective mode came from in the resolution chain.
export function ProvenanceBadge({ provenance }: { provenance: string }) {
    const map: Record<string, { label: string; variant: BadgeVariant }> = {
        global: { label: "global", variant: "neutral" },
        plan: { label: "plan", variant: "info" },
        override: { label: "override", variant: "warning" },
        status: { label: "status", variant: "danger" },
    };
    const p = map[provenance] ?? map.global;
    return <Badge variant={p.variant}>{p.label}</Badge>;
}

// A registry kind -> a short human label + tone for the kind chip.
export const KIND_META: Record<string, { label: string; variant: BadgeVariant }> = {
    module: { label: "Module", variant: "info" },
    page: { label: "Page", variant: "neutral" },
    feature: { label: "Feature", variant: "neutral" },
    action: { label: "Action", variant: "neutral" },
    integration: { label: "Integration", variant: "warning" },
    ai_agent: { label: "AI Agent", variant: "info" },
    api: { label: "API", variant: "neutral" },
};

// Turn an action string ("control.override.set") into a readable label.
export function humanizeAction(action: string): string {
    return action
        .replace(/^control\./, "")
        .split(/[._]/)
        .map((w) => (w ? w[0].toUpperCase() + w.slice(1) : w))
        .join(" ");
}

// Friendly names for plan limit keys.
export const LIMIT_LABELS: Record<string, string> = {
    max_concurrency: "Max concurrency",
    daily_call_cap: "Daily call cap",
    monthly_minutes_cap: "Monthly minutes",
    monthly_credits: "Monthly credits",
    seats: "Seats",
    max_leads: "Max leads",
    max_campaigns: "Max campaigns",
};

// The standard limit keys a plan editor exposes as numeric fields.
export const LIMIT_KEYS: string[] = [
    "max_concurrency",
    "daily_call_cap",
    "monthly_minutes_cap",
    "monthly_credits",
    "seats",
];

export function limitLabel(key: string): string {
    return LIMIT_LABELS[key] || key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

// Inline toast (reuses the .toast utilities used by app/vendors).
export type Toast = { msg: string; type: "success" | "error" };

export function ToastView({ toast, onClose }: { toast: Toast | null; onClose: () => void }) {
    if (!toast) return null;
    return (
        <div className={`toast ${toast.type === "success" ? "toast-success" : "toast-error"}`}>
            <span className="flex items-center gap-2">
                <span className="size-1.5 rounded-full bg-current" />
                {toast.msg}
            </span>
            <button onClick={onClose} className="shrink-0 opacity-60 hover:opacity-100 text-lg leading-none">
                ×
            </button>
        </div>
    );
}
