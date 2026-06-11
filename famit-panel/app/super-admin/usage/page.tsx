"use client";

// ============================================================
// CL-F3 · Usage Analytics — /super-admin/usage
//
// Executive per-vendor usage across the fleet. Ports the Core_2
// Customers/OverviewPage archetype: a KPI strip (fleet rollup) + a per-vendor
// leaderboard table with a "fleet vs one vendor" selector. design/control-ui.md §2.6.
//
// Reads GET /admin/vendors (CL-F1 binding — richer summary + a /usage/all+/tenants
// fallback so it renders real numbers even before /admin/vendors is mounted).
// Pure read; no writes (executive view).
//
// SECURITY: cosmetic admin view; require_super_admin is the real boundary.
// ============================================================

import { useEffect, useMemo, useState, useCallback } from "react";
import Layout from "@/components/Layout";
import Card from "@/components/Card";
import Icon from "@/components/Icon";
import Search from "@/components/Search";
import Select from "@/components/Select";
import Spinner from "@/components/Spinner";
import { getAdminVendors, type AdminVendor } from "@/lib/api";
import {
    SuperAdminGuard,
    SuperAdminHeaderF3,
    StatusPill,
    num,
    ago,
    ErrorBanner,
    ghostBtnCls,
} from "../_shared";
import type { SelectOption } from "@/types/select";

// Hero metric tile (matches the billing/_shared HeroCard look without importing
// recharts — pure number tiles). Built on the .kpi utility.
function StatTile({
    label,
    glyph,
    glyphClass,
    value,
    loading,
    foot,
    delay = 0,
}: {
    label: string;
    glyph: string;
    glyphClass?: string;
    value: React.ReactNode;
    loading?: boolean;
    foot?: React.ReactNode;
    delay?: number;
}) {
    return (
        <div className="kpi rise-in" style={delay ? { animationDelay: `${delay}ms` } : undefined}>
            <div className="kpi-label">
                <span className={`kpi-glyph ${glyphClass || "fill-t-secondary"}`}>
                    <Icon name={glyph} className="fill-inherit" />
                </span>
                {label}
            </div>
            {loading ? <div className="skeleton h-9 w-24 mt-1" /> : <div className="kpi-value">{value}</div>}
            {foot && <div className="kpi-foot">{foot}</div>}
        </div>
    );
}

type SortKey = "calls_30d" | "minutes_30d" | "calls_today" | "active_now";
const SORT_OPTIONS: SelectOption[] = [
    { id: 1, name: "Calls (30d)" },
    { id: 2, name: "Minutes (30d)" },
    { id: 3, name: "Calls today" },
    { id: 4, name: "Active now" },
];
const SORT_KEY: Record<number, SortKey> = {
    1: "calls_30d",
    2: "minutes_30d",
    3: "calls_today",
    4: "active_now",
};

function usageVal(v: AdminVendor, k: SortKey): number {
    const u = v.usage_summary || {};
    return (u[k] as number) ?? 0;
}

export default function UsageAnalyticsPage() {
    const [vendors, setVendors] = useState<AdminVendor[]>([]);
    const [summary, setSummary] = useState<{
        total: number;
        active: number;
        suspended: number;
        trial?: number;
        calls_today?: number;
        minutes_30d?: number;
        credits_burned?: number;
        alerts?: number;
    } | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState("");
    const [search, setSearch] = useState("");
    const [sort, setSort] = useState<SelectOption>(SORT_OPTIONS[0]);

    const load = useCallback(() => {
        setLoading(true);
        setError("");
        getAdminVendors()
            .then((r) => {
                setVendors(r.vendors);
                setSummary(r.summary ?? null);
            })
            .catch((e) => setError(e instanceof Error ? e.message : "Failed to load usage"))
            .finally(() => setLoading(false));
    }, []);

    useEffect(() => {
        load();
    }, [load]);

    // derive a fleet rollup when the backend omits a summary.
    const fleet = useMemo(() => {
        if (summary) return summary;
        const s = {
            total: vendors.length,
            active: vendors.filter((v) => v.status === "active").length,
            suspended: vendors.filter((v) => v.status === "suspended").length,
            trial: vendors.filter((v) => v.status === "trial").length,
            calls_today: 0,
            minutes_30d: 0,
            credits_burned: 0,
            alerts: 0,
        };
        for (const v of vendors) {
            const u = v.usage_summary || {};
            s.calls_today += u.calls_today ?? 0;
            s.minutes_30d += u.minutes_30d ?? 0;
            s.credits_burned += u.credits_burned ?? 0;
        }
        return s;
    }, [vendors, summary]);

    const sortKey = SORT_KEY[Number(sort.id)] ?? "calls_30d";

    const rows = useMemo(() => {
        const q = search.trim().toLowerCase();
        return vendors
            .filter(
                (v) =>
                    !q ||
                    v.name.toLowerCase().includes(q) ||
                    v.email.toLowerCase().includes(q) ||
                    v.tenant_id.toLowerCase().includes(q)
            )
            .sort((a, b) => usageVal(b, sortKey) - usageVal(a, sortKey));
    }, [vendors, search, sortKey]);

    const maxVal = useMemo(
        () => Math.max(1, ...rows.map((v) => usageVal(v, sortKey))),
        [rows, sortKey]
    );

    return (
        <SuperAdminGuard>
            <Layout title="Usage">
                <SuperAdminHeaderF3
                    actions={
                        <button onClick={load} className={ghostBtnCls} disabled={loading}>
                            <Icon name="clock" className={`size-4 fill-current ${loading ? "animate-spin" : ""}`} />
                            {loading ? "Refreshing…" : "Refresh"}
                        </button>
                    }
                />
                <ErrorBanner msg={error} />

                {/* fleet KPI strip */}
                <div className="grid grid-cols-4 gap-4 mb-6 max-xl:grid-cols-2 max-md:grid-cols-1">
                    <StatTile
                        label="Vendors"
                        glyph="profile"
                        glyphClass="fill-primary-01"
                        value={num(fleet.total)}
                        loading={loading}
                        foot={
                            <span className="text-t-tertiary">
                                {fleet.active} active · {fleet.trial ?? 0} trial · {fleet.suspended} suspended
                            </span>
                        }
                        delay={0}
                    />
                    <StatTile
                        label="Calls today"
                        glyph="chat"
                        glyphClass="fill-primary-02"
                        value={num(fleet.calls_today ?? 0)}
                        loading={loading}
                        delay={60}
                    />
                    <StatTile
                        label="Minutes (30d)"
                        glyph="clock"
                        glyphClass="fill-primary-04"
                        value={num(fleet.minutes_30d ?? 0)}
                        loading={loading}
                        delay={120}
                    />
                    <StatTile
                        label="Live now"
                        glyph="promote"
                        glyphClass="fill-primary-05"
                        value={num(vendors.reduce((s, v) => s + (v.usage_summary?.active_now ?? 0), 0))}
                        loading={loading}
                        foot={<span className="text-t-tertiary">active calls across the fleet</span>}
                        delay={180}
                    />
                </div>

                {/* per-vendor leaderboard */}
                <Card
                    title="Per-vendor usage"
                    headContent={
                        <div className="flex items-center gap-3 ml-auto mr-3 max-md:hidden">
                            <div className="w-56">
                                <Search
                                    value={search}
                                    onChange={(e) => setSearch(e.target.value)}
                                    placeholder="Search vendors…"
                                    isGray
                                />
                            </div>
                            <Select
                                className="min-w-44"
                                value={sort}
                                onChange={setSort}
                                options={SORT_OPTIONS}
                            />
                        </div>
                    }
                >
                    <div className="overflow-x-auto px-3 pb-2">
                        <table className="data-table w-full">
                            <thead>
                                <tr>
                                    <th>Vendor</th>
                                    <th>Status</th>
                                    <th className="text-right">Calls today</th>
                                    <th className="text-right">Calls 30d</th>
                                    <th className="text-right">Minutes 30d</th>
                                    <th className="text-right">Live</th>
                                    <th>Last activity</th>
                                </tr>
                            </thead>
                            <tbody>
                                {loading && rows.length === 0 ? (
                                    [...Array(5)].map((_, i) => (
                                        <tr key={i}>
                                            {[...Array(7)].map((_, j) => (
                                                <td key={j}>
                                                    <div className="skeleton h-4 w-16" />
                                                </td>
                                            ))}
                                        </tr>
                                    ))
                                ) : rows.length === 0 ? (
                                    <tr>
                                        <td colSpan={7}>
                                            <div className="state-block">
                                                <span className="state-glyph">
                                                    <Icon name="profile" className="fill-inherit" />
                                                </span>
                                                <div className="state-title">No vendors</div>
                                                <div className="state-sub">
                                                    {vendors.length === 0
                                                        ? "No vendor accounts yet."
                                                        : "No vendor matches your search."}
                                                </div>
                                            </div>
                                        </td>
                                    </tr>
                                ) : (
                                    rows.map((v) => {
                                        const u = v.usage_summary || {};
                                        const lead = usageVal(v, sortKey);
                                        const pct = Math.round((lead / maxVal) * 100);
                                        return (
                                            <tr key={v.tenant_id}>
                                                <td>
                                                    <div className="min-w-0">
                                                        <div className="font-medium text-t-primary truncate">{v.name}</div>
                                                        <div className="text-caption text-t-tertiary truncate">
                                                            {v.email || v.tenant_id}
                                                        </div>
                                                    </div>
                                                    <div className="meter mt-1.5 max-w-40">
                                                        <div
                                                            className="meter-fill"
                                                            style={{ width: `${Math.max(pct, 2)}%`, background: "var(--primary-01)" }}
                                                        />
                                                    </div>
                                                </td>
                                                <td>
                                                    <StatusPill status={v.status} />
                                                </td>
                                                <td className="td-num text-right text-t-primary tabular-nums">
                                                    {num(u.calls_today ?? 0)}
                                                </td>
                                                <td className="td-num text-right text-t-primary tabular-nums">
                                                    {num(u.calls_30d ?? 0)}
                                                </td>
                                                <td className="td-num text-right text-t-primary tabular-nums">
                                                    {num(u.minutes_30d ?? 0)}
                                                </td>
                                                <td className="td-num text-right tabular-nums">
                                                    {(u.active_now ?? 0) > 0 ? (
                                                        <span className="text-primary-02">{u.active_now}</span>
                                                    ) : (
                                                        <span className="text-t-tertiary">0</span>
                                                    )}
                                                </td>
                                                <td className="text-t-secondary whitespace-nowrap">
                                                    {ago(v.health?.last_activity || v.health?.last_call_at)}
                                                </td>
                                            </tr>
                                        );
                                    })
                                )}
                            </tbody>
                        </table>
                    </div>
                </Card>
            </Layout>
        </SuperAdminGuard>
    );
}
