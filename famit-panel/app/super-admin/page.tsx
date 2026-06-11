"use client";

// Control Overview — the Super Admin fleet dashboard (CL-F1, design/control-ui.md §2.1).
//
// Archetype: Dashboard (fleet KPIs + leaderboard + recent feed). Ported from
// the Core_2 HomePage KPI strip + Customers/OverviewPage stat cards, rewired
// onto our live admin-gated data: GET /admin/vendors (which gracefully composes
// from /usage/all + /tenants until the richer endpoint ships).
//
// ADMIN PLANE NOTE: the whole /super-admin section is nav-gated `roles:"admin"`
// AND the backend require_super_admin is the real boundary (it EXCLUDES the
// legacy static-password auth — the #1 security finding). This page is the
// fleet *read*; no mutation happens here.

import { useEffect, useState, useCallback, useMemo } from "react";
import Link from "next/link";
import Layout from "@/components/Layout";
import Card from "@/components/Card";
import Icon from "@/components/Icon";
import { getFleetVendors, type FleetVendor, type FleetSummary } from "@/lib/api";
import {
    AdminHeader,
    HeroCard,
    ErrorBanner,
    ghostBtnCls,
    StatusPill,
    SuperAdminGuard,
    num,
    ago,
} from "./_shared";

function ControlOverviewInner() {
    const [vendors, setVendors] = useState<FleetVendor[]>([]);
    const [summary, setSummary] = useState<FleetSummary | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState("");

    const load = useCallback(() => {
        setLoading(true);
        setError("");
        getFleetVendors()
            .then((r) => {
                setVendors(r.vendors);
                setSummary(r.summary ?? null);
            })
            .catch((e) => setError(e instanceof Error ? e.message : "Failed to load fleet"))
            .finally(() => setLoading(false));
    }, []);

    useEffect(() => {
        load();
    }, [load]);

    // Prefer the backend-provided summary; otherwise derive from the vendor rows
    // so the KPIs are always real (the composed fallback also supplies summary).
    const kpis = useMemo(() => {
        if (summary) return summary;
        const s = (st: string) => vendors.filter((v) => v.status === st).length;
        return {
            total: vendors.length,
            active: s("active"),
            suspended: s("suspended"),
            trial: s("trial"),
            disabled: s("disabled"),
            expired: s("expired"),
            calls_today: vendors.reduce((a, v) => a + (v.usage_summary?.calls_today ?? 0), 0),
            minutes_30d: vendors.reduce((a, v) => a + (v.usage_summary?.minutes_30d ?? 0), 0),
            credits_burned: vendors.reduce((a, v) => a + (v.usage_summary?.credits_burned ?? 0), 0),
            alerts: vendors.reduce((a, v) => a + (v.health?.alerts ?? 0), 0),
        };
    }, [summary, vendors]);

    const activeNow = useMemo(
        () => vendors.reduce((a, v) => a + (v.usage_summary?.active_now ?? 0), 0),
        [vendors]
    );

    // Busiest vendors by 30-day call volume — the executive leaderboard.
    const leaders = useMemo(
        () =>
            [...vendors]
                .sort((a, b) => (b.usage_summary?.calls_30d ?? 0) - (a.usage_summary?.calls_30d ?? 0))
                .slice(0, 8),
        [vendors]
    );

    return (
        <Layout title="Control Overview">
            <AdminHeader
                actions={
                    <button onClick={load} className={ghostBtnCls} disabled={loading}>
                        <Icon name="clock" className={`size-4 fill-current ${loading ? "animate-spin" : ""}`} />
                        {loading ? "Refreshing…" : "Refresh"}
                    </button>
                }
            />
            <ErrorBanner msg={error} />

            {/* live ribbon */}
            <div className="flex items-center gap-2 mb-3 text-caption text-t-tertiary">
                <span className="relative flex size-1.5">
                    <span className="absolute inline-flex h-full w-full rounded-full bg-primary-02 opacity-60 animate-ping" />
                    <span className="relative inline-flex size-1.5 rounded-full bg-primary-02" />
                </span>
                {loading ? "Loading fleet…" : `${activeNow} call${activeNow === 1 ? "" : "s"} in flight · ${kpis.total} vendor${kpis.total === 1 ? "" : "s"}`}
            </div>

            {/* Fleet KPI strip — real signals only */}
            <div className="grid grid-cols-4 gap-3 mb-3 max-2xl:grid-cols-2 max-md:grid-cols-1">
                <HeroCard
                    label="Total Vendors"
                    glyph="profile"
                    glyphClass="fill-primary-01"
                    accent="var(--primary-01)"
                    loading={loading && vendors.length === 0}
                    value={num(kpis.total)}
                    foot={
                        <>
                            <span className="font-medium text-t-secondary">{num(kpis.active)} active</span>
                            {kpis.trial ? <>· {num(kpis.trial)} trial</> : null}
                        </>
                    }
                />
                <HeroCard
                    label="Active Accounts"
                    glyph="check-circle"
                    glyphClass="fill-primary-02"
                    accent="var(--primary-02)"
                    delay={60}
                    loading={loading && vendors.length === 0}
                    value={num(kpis.active)}
                    foot={
                        <>
                            <Icon name="profile" className="size-3.5 fill-t-tertiary" />
                            {kpis.suspended ? `${num(kpis.suspended)} suspended` : "All in good standing"}
                        </>
                    }
                />
                <HeroCard
                    label="Calls Today"
                    glyph="chat"
                    glyphClass="fill-primary-04"
                    accent="var(--primary-04)"
                    delay={120}
                    loading={loading && vendors.length === 0}
                    value={num(kpis.calls_today)}
                    foot={
                        <>
                            <Icon name="chart" className="size-3.5 fill-t-tertiary" />
                            {num(kpis.minutes_30d)} minutes · 30d
                        </>
                    }
                />
                <HeroCard
                    label="Open Alerts"
                    glyph="bell"
                    glyphClass={(kpis.alerts ?? 0) > 0 ? "fill-primary-03" : "fill-primary-02"}
                    accent={(kpis.alerts ?? 0) > 0 ? "var(--primary-03)" : "var(--primary-02)"}
                    delay={180}
                    loading={loading && vendors.length === 0}
                    value={num(kpis.alerts ?? 0)}
                    foot={
                        <>
                            <Icon name="info" className="size-3.5 fill-t-tertiary" />
                            {(kpis.alerts ?? 0) > 0 ? "Needs attention" : "Nothing flagged"}
                        </>
                    }
                />
            </div>

            {/* Busiest vendors leaderboard */}
            <Card
                title="Busiest Vendors"
                headContent={
                    <Link
                        href="/super-admin/vendors"
                        className="ml-3 inline-flex items-center gap-1 text-caption text-t-secondary hover:text-t-primary transition-colors"
                    >
                        View all
                        <Icon name="arrow" className="size-3.5 fill-current" />
                    </Link>
                }
            >
                <div className="overflow-x-auto px-3 pb-2">
                    <table className="data-table">
                        <thead>
                            <tr>
                                <th>Vendor</th>
                                <th>Status</th>
                                <th className="text-right">Calls · 30d</th>
                                <th className="text-right">Minutes</th>
                                <th>Last active</th>
                            </tr>
                        </thead>
                        <tbody>
                            {loading && vendors.length === 0 ? (
                                [...Array(5)].map((_, i) => (
                                    <tr key={i}>
                                        <td><div className="skeleton h-4 w-32" /></td>
                                        <td><div className="skeleton h-5 w-16 rounded-md" /></td>
                                        <td><div className="skeleton h-4 w-12 ml-auto" /></td>
                                        <td><div className="skeleton h-4 w-12 ml-auto" /></td>
                                        <td><div className="skeleton h-4 w-20" /></td>
                                    </tr>
                                ))
                            ) : leaders.length === 0 ? (
                                <tr>
                                    <td colSpan={5}>
                                        <div className="state-block">
                                            <span className="state-glyph">
                                                <Icon name="profile" className="fill-inherit" />
                                            </span>
                                            <div className="state-title">No vendors yet</div>
                                            <div className="state-sub">
                                                Vendor accounts appear here once they are onboarded to the platform.
                                            </div>
                                        </div>
                                    </td>
                                </tr>
                            ) : (
                                leaders.map((v) => (
                                    <tr key={v.tenant_id}>
                                        <td>
                                            <Link
                                                href={`/super-admin/vendors?focus=${encodeURIComponent(v.tenant_id)}`}
                                                className="group inline-flex items-center gap-2.5"
                                            >
                                                <span className="grid place-items-center size-8 shrink-0 rounded-xl bg-b-surface1 text-button text-t-secondary dark:bg-shade-04/60">
                                                    {(v.name || "?").charAt(0).toUpperCase()}
                                                </span>
                                                <span className="min-w-0">
                                                    <span className="block font-medium text-t-primary truncate group-hover:underline">{v.name}</span>
                                                    {v.email && <span className="block text-caption text-t-tertiary truncate">{v.email}</span>}
                                                </span>
                                            </Link>
                                        </td>
                                        <td><StatusPill status={v.status} /></td>
                                        <td className="td-num text-right font-medium text-t-primary">{num(v.usage_summary?.calls_30d ?? 0)}</td>
                                        <td className="td-num text-right text-t-secondary">{num(v.usage_summary?.minutes_30d ?? 0)}</td>
                                        <td className="text-t-secondary whitespace-nowrap">{ago(v.health?.last_activity || v.health?.last_call_at)}</td>
                                    </tr>
                                ))
                            )}
                        </tbody>
                    </table>
                </div>
            </Card>
        </Layout>
    );
}

// Admin-gated wrapper (cosmetic — the backend require_super_admin is the real
// boundary). A vendor who guesses the URL is bounced to "/".
export default function ControlOverviewPage() {
    return (
        <SuperAdminGuard>
            <ControlOverviewInner />
        </SuperAdminGuard>
    );
}
