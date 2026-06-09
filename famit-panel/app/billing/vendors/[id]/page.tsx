"use client";

import { useEffect, useState, useCallback } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import Layout from "@/components/Layout";
import Card from "@/components/Card";
import { getBillingVendor, type BillingVendorDetail } from "@/lib/api";
import { money, fmt, StatusBadge, ErrorBanner, btnCls } from "../../_shared";
import {
    ResponsiveContainer,
    AreaChart,
    Area,
    XAxis,
    YAxis,
    CartesianGrid,
    Tooltip,
} from "recharts";

export default function VendorDetailPage() {
    const params = useParams();
    const id = String(params?.id || "");
    const [data, setData] = useState<BillingVendorDetail | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState("");

    const load = useCallback(() => {
        if (!id) return;
        setLoading(true);
        setError("");
        getBillingVendor(id)
            .then(setData)
            .catch((e) => setError(e instanceof Error ? e.message : "Failed to load vendor"))
            .finally(() => setLoading(false));
    }, [id]);

    useEffect(() => { load(); }, [load]);

    const currency = data?.currency || "";
    const series = data?.timeseries ?? [];

    return (
        <Layout title={`Billing · ${data?.display_name || "Vendor"}`}>
            <ErrorBanner msg={error} />

            <div className="flex items-center justify-between mb-6 flex-wrap gap-3">
                <Link href="/billing/vendors" className="text-body-2 text-t-secondary hover:text-t-primary transition-colors">
                    ← All vendors
                </Link>
                <button onClick={load} className={btnCls}>{loading ? "Refreshing…" : "Refresh"}</button>
            </div>

            <div className="grid grid-cols-3 gap-4 mb-6 max-sm:grid-cols-1">
                <div className="card p-4 flex flex-col gap-1">
                    <div className="text-caption text-t-tertiary">Total Cost</div>
                    <div className="text-h5 text-t-primary">{loading ? "…" : money(data?.total_cost, currency)}</div>
                </div>
                <div className="card p-4 flex flex-col gap-2">
                    <div className="text-caption text-t-tertiary">Status</div>
                    {data ? <StatusBadge status={data.status} stale={data.stale} /> : <div className="text-t-secondary">…</div>}
                </div>
                <div className="card p-4 flex flex-col gap-1">
                    <div className="text-caption text-t-tertiary">Rows · Last Sync</div>
                    <div className="text-body-1 font-medium text-t-primary">{data?.rows ?? 0}</div>
                    <div className="text-caption text-t-tertiary">{fmt(data?.synced_at)}</div>
                </div>
            </div>

            {data?.status === "not_configured" && (
                <div className="mb-6 p-3 rounded-2xl bg-amber-50 text-amber-700 text-body-2 dark:bg-amber-900/20 dark:text-amber-400">
                    This vendor is not configured — add API keys on the server to enable live cost reporting.
                </div>
            )}

            <Card title="Cost Over Time">
                <div className="px-4 pb-4">
                    {series.length === 0 ? (
                        <div className="py-12 text-center text-t-tertiary">No timeseries data yet</div>
                    ) : (
                        <div className="h-72">
                            <ResponsiveContainer width="100%" height="100%">
                                <AreaChart data={series} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                                    <defs>
                                        <linearGradient id="vendorCost" x1="0" y1="0" x2="0" y2="1">
                                            <stop offset="5%" stopColor="var(--primary-02)" stopOpacity={0.4} />
                                            <stop offset="95%" stopColor="var(--primary-02)" stopOpacity={0} />
                                        </linearGradient>
                                    </defs>
                                    <XAxis
                                        dataKey="date"
                                        axisLine={false}
                                        tickLine={false}
                                        tick={{ fontSize: "11px", fill: "var(--text-tertiary)" }}
                                    />
                                    <YAxis
                                        axisLine={false}
                                        tickLine={false}
                                        tick={{ fontSize: "12px", fill: "var(--text-tertiary)" }}
                                        width={48}
                                    />
                                    <CartesianGrid strokeDasharray="5 7" vertical={false} stroke="var(--stroke-stroke2)" />
                                    <Tooltip
                                        contentStyle={{
                                            background: "var(--backgrounds-surface2)",
                                            border: "1px solid var(--stroke-stroke2)",
                                            borderRadius: "12px",
                                        }}
                                        formatter={(val: number) => money(val, currency)}
                                    />
                                    <Area
                                        type="monotone"
                                        dataKey="cost"
                                        stroke="var(--primary-02)"
                                        fill="url(#vendorCost)"
                                        strokeWidth={2}
                                    />
                                </AreaChart>
                            </ResponsiveContainer>
                        </div>
                    )}
                </div>
            </Card>

            {/* Fallback table view of the same data */}
            {series.length > 0 && (
                <Card title="Daily Breakdown" className="mt-6">
                    <div className="overflow-x-auto">
                        <table className="w-full text-body-2 [&_th]:h-13 [&_th,&_td]:px-5 [&_th,&_td]:py-3 [&_th]:align-middle [&_th]:text-left [&_th]:text-caption [&_th]:text-t-tertiary/80 [&_th]:font-normal">
                            <thead>
                                <tr><th>Date</th><th>Cost</th></tr>
                            </thead>
                            <tbody>
                                {series.map((row, i) => (
                                    <tr key={i} className="border-t border-s-subtle">
                                        <td className="text-t-secondary">{row.date}</td>
                                        <td className="font-medium">{money(row.cost, currency)}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </Card>
            )}
        </Layout>
    );
}
