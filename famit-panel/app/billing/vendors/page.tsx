"use client";

import { useEffect, useState, useCallback, useMemo } from "react";
import { useRouter } from "next/navigation";
import Layout from "@/components/Layout";
import Card from "@/components/Card";
import Icon from "@/components/Icon";
import { getBillingVendors, type BillingVendorRow } from "@/lib/api";
import {
    money,
    fmt,
    StatusBadge,
    ErrorBanner,
    ghostBtnCls,
    VENDOR_COLORS,
    BillingHeader,
} from "../_shared";

export default function BillingVendorsPage() {
    const router = useRouter();
    const [vendors, setVendors] = useState<BillingVendorRow[]>([]);
    const [currency, setCurrency] = useState("");
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState("");

    const load = useCallback(() => {
        setLoading(true);
        setError("");
        getBillingVendors()
            .then((r) => { setVendors(r.vendors); setCurrency(r.currency); })
            .catch((e) => setError(e instanceof Error ? e.message : "Failed to load vendors"))
            .finally(() => setLoading(false));
    }, []);

    useEffect(() => { load(); }, [load]);

    const sorted = useMemo(
        () => [...vendors].sort((a, b) => b.cost - a.cost),
        [vendors]
    );
    const total = useMemo(
        () => sorted.reduce((s, v) => s + Math.max(v.cost, 0), 0),
        [sorted]
    );

    return (
        <Layout title="Billing · Vendors">
            <BillingHeader
                title="Vendor Spend"
                subtitle="Per-vendor metered cost with sync status — drill into any vendor for its full timeseries."
                actions={
                    <button onClick={load} className={ghostBtnCls} disabled={loading}>
                        <Icon name="clock" className={`size-4 fill-current ${loading ? "animate-spin" : ""}`} />
                        {loading ? "Refreshing…" : "Refresh"}
                    </button>
                }
            />
            <ErrorBanner msg={error} />

            <div className="flex items-center justify-between mb-3 flex-wrap gap-3">
                <div className="flex items-center gap-2 text-caption text-t-tertiary">
                    <Icon name="cube" className="size-3.5 fill-t-tertiary" />
                    {loading ? "Loading vendors…" : `${vendors.length} vendor${vendors.length === 1 ? "" : "s"} metered`}
                </div>
                <button onClick={load} className={`${ghostBtnCls} max-md:hidden`} disabled={loading}>
                    <Icon name="clock" className={`size-4 fill-current ${loading ? "animate-spin" : ""}`} />
                    {loading ? "Refreshing…" : "Refresh"}
                </button>
            </div>

            <Card title="Vendors">
                <div className="overflow-x-auto px-3 pb-2">
                    <table className="data-table">
                        <thead>
                            <tr>
                                <th>Vendor</th>
                                <th>Status</th>
                                <th className="text-right">Cost</th>
                                <th className="!w-44">Share</th>
                                <th>Last Sync</th>
                            </tr>
                        </thead>
                        <tbody>
                            {loading && vendors.length === 0 ? (
                                [...Array(4)].map((_, i) => (
                                    <tr key={i}>
                                        <td><div className="skeleton h-4 w-28" /></td>
                                        <td><div className="skeleton h-5 w-16 rounded-md" /></td>
                                        <td><div className="skeleton h-4 w-16 ml-auto" /></td>
                                        <td><div className="skeleton h-1.5 w-32" /></td>
                                        <td><div className="skeleton h-4 w-24" /></td>
                                    </tr>
                                ))
                            ) : vendors.length === 0 ? (
                                <tr>
                                    <td colSpan={5}>
                                        <div className="state-block">
                                            <span className="state-glyph">
                                                <Icon name="cube" className="fill-inherit" />
                                            </span>
                                            <div className="state-title">No vendors yet</div>
                                            <div className="state-sub">
                                                Configured vendors appear here once a sync runs.
                                            </div>
                                        </div>
                                    </td>
                                </tr>
                            ) : (
                                sorted.map((v, i) => {
                                    const pct = total > 0 ? (Math.max(v.cost, 0) / total) * 100 : 0;
                                    const color = VENDOR_COLORS[i % VENDOR_COLORS.length];
                                    return (
                                        <tr
                                            key={v.vendor}
                                            className="is-clickable cursor-pointer"
                                            onClick={() => router.push(`/billing/vendors/${v.vendor}`)}
                                        >
                                            <td>
                                                <div className="flex items-center gap-2.5">
                                                    <span className="size-2.5 rounded-sm shrink-0" style={{ background: color }} />
                                                    <span className="font-medium text-t-primary">{v.display_name}</span>
                                                    {v.estimated && (
                                                        <span className="text-caption text-t-tertiary">(est.)</span>
                                                    )}
                                                </div>
                                            </td>
                                            <td><StatusBadge status={v.status} stale={v.stale} /></td>
                                            <td className="td-num text-right font-medium text-t-primary">
                                                {money(v.cost, currency)}
                                            </td>
                                            <td>
                                                <div className="flex items-center gap-2">
                                                    <div className="meter flex-1">
                                                        <div
                                                            className="meter-fill"
                                                            style={{ width: `${Math.max(pct, 2)}%`, background: color }}
                                                        />
                                                    </div>
                                                    <span className="text-caption text-t-tertiary tabular-nums w-8 text-right">
                                                        {pct.toFixed(0)}%
                                                    </span>
                                                </div>
                                            </td>
                                            <td className="text-t-secondary">{fmt(v.synced_at)}</td>
                                        </tr>
                                    );
                                })
                            )}
                        </tbody>
                    </table>
                </div>
            </Card>
        </Layout>
    );
}
