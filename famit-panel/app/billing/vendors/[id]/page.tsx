"use client";

import { useEffect, useState, useCallback, useMemo } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import Layout from "@/components/Layout";
import Card from "@/components/Card";
import Icon from "@/components/Icon";
import { getBillingVendor, type BillingVendorDetail } from "@/lib/api";
import {
    money,
    moneyShort,
    fmt,
    StatusBadge,
    ErrorBanner,
    ghostBtnCls,
    HeroCard,
    Sparkline,
} from "../../_shared";
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
    const series = useMemo(() => data?.timeseries ?? [], [data]);
    // Real signals from the series — peak day + daily average.
    const peak = useMemo(
        () => series.reduce((m, r) => (r.cost > m.cost ? r : m), { date: "", cost: 0 }),
        [series]
    );
    const avg = series.length ? series.reduce((s, r) => s + r.cost, 0) / series.length : 0;

    return (
        <Layout title={`Billing · ${data?.display_name || "Vendor"}`}>
            <ErrorBanner msg={error} />

            <div className="flex items-center justify-between mb-3 flex-wrap gap-3">
                <Link
                    href="/billing/vendors"
                    className="inline-flex items-center gap-1.5 text-body-2 text-t-secondary hover:text-t-primary transition-colors"
                >
                    <Icon name="arrow" className="size-4 fill-current rotate-180" />
                    All vendors
                </Link>
                <button onClick={load} className={ghostBtnCls} disabled={loading}>
                    <Icon name="clock" className={`size-4 fill-current ${loading ? "animate-spin" : ""}`} />
                    {loading ? "Refreshing…" : "Refresh"}
                </button>
            </div>

            <div className="grid grid-cols-3 gap-3 mb-3 max-sm:grid-cols-1">
                <HeroCard
                    label="Total Cost"
                    glyph="wallet"
                    glyphClass="fill-primary-04"
                    accent="var(--primary-04)"
                    loading={loading && !data}
                    value={money(data?.total_cost, currency)}
                    aside={
                        series.length >= 2 ? (
                            <Sparkline data={series} color="var(--primary-04)" />
                        ) : undefined
                    }
                    foot={`${data?.rows ?? 0} metered row${(data?.rows ?? 0) === 1 ? "" : "s"}`}
                />
                <HeroCard
                    label="Peak Day"
                    glyph="chart"
                    glyphClass="fill-primary-01"
                    accent="var(--primary-01)"
                    delay={70}
                    loading={loading && !data}
                    value={series.length ? money(peak.cost, currency) : "—"}
                    foot={series.length ? peak.date : "No timeseries yet"}
                />
                <HeroCard
                    label="Daily Average"
                    glyph="income"
                    glyphClass="fill-primary-02"
                    accent="var(--primary-02)"
                    delay={140}
                    loading={loading && !data}
                    value={series.length ? money(avg, currency) : "—"}
                    aside={data ? <StatusBadge status={data.status} stale={data.stale} /> : undefined}
                    foot={
                        series.length
                            ? `Span ${moneyShort(Math.min(...series.map((s) => s.cost)), currency)}–${moneyShort(peak.cost, currency)}/day`
                            : `Last sync ${fmt(data?.synced_at)}`
                    }
                />
            </div>

            {data?.status === "not_configured" && (
                <div className="mb-3 p-3.5 rounded-2xl bg-primary-05/8 text-primary-05 text-body-2 ring-1 ring-inset ring-primary-05/20 flex items-center gap-2">
                    <Icon name="info" className="size-4 fill-current shrink-0" />
                    This vendor is not configured — add API keys on the server to enable live cost reporting.
                </div>
            )}

            <Card title="Cost Over Time">
                <div className="px-4 pb-4 pt-1">
                    {loading && !data ? (
                        <div className="skeleton h-72 w-full rounded-2xl" />
                    ) : series.length === 0 ? (
                        <div className="state-block">
                            <span className="state-glyph">
                                <Icon name="chart" className="fill-inherit" />
                            </span>
                            <div className="state-title">No timeseries data yet</div>
                            <div className="state-sub">
                                A cost trend appears here once this vendor reports daily usage.
                            </div>
                        </div>
                    ) : (
                        <div className="h-72">
                            <ResponsiveContainer width="100%" height="100%">
                                <AreaChart data={series} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                                    <defs>
                                        <linearGradient id="vendorCost" x1="0" y1="0" x2="0" y2="1">
                                            <stop offset="5%" stopColor="var(--primary-01)" stopOpacity={0.35} />
                                            <stop offset="95%" stopColor="var(--primary-01)" stopOpacity={0} />
                                        </linearGradient>
                                    </defs>
                                    <XAxis
                                        dataKey="date"
                                        axisLine={false}
                                        tickLine={false}
                                        tick={{ fontSize: "11px", fill: "var(--text-tertiary)" }}
                                        dy={6}
                                    />
                                    <YAxis
                                        axisLine={false}
                                        tickLine={false}
                                        tick={{ fontSize: "11px", fill: "var(--text-tertiary)" }}
                                        width={48}
                                    />
                                    <CartesianGrid strokeDasharray="4 6" vertical={false} stroke="var(--stroke-stroke2)" />
                                    <Tooltip
                                        cursor={{ stroke: "var(--stroke-stroke2)", strokeWidth: 1 }}
                                        contentStyle={{
                                            background: "var(--backgrounds-surface2)",
                                            border: "1px solid var(--stroke-stroke2)",
                                            borderRadius: "12px",
                                            boxShadow: "0 8px 24px -8px rgba(8,8,8,0.25)",
                                            fontSize: "12px",
                                        }}
                                        labelStyle={{ color: "var(--text-tertiary)" }}
                                        formatter={(val: number) => [money(val, currency), "Cost"]}
                                    />
                                    <Area
                                        type="monotone"
                                        dataKey="cost"
                                        stroke="var(--primary-01)"
                                        fill="url(#vendorCost)"
                                        strokeWidth={2}
                                        activeDot={{ r: 4, strokeWidth: 0, fill: "var(--primary-01)" }}
                                    />
                                </AreaChart>
                            </ResponsiveContainer>
                        </div>
                    )}
                </div>
            </Card>

            {series.length > 0 && (
                <Card title="Daily Breakdown">
                    <div className="overflow-x-auto px-3 pb-2">
                        <table className="data-table">
                            <thead>
                                <tr>
                                    <th>Date</th>
                                    <th className="text-right">Cost</th>
                                    <th className="!w-56">vs. peak</th>
                                </tr>
                            </thead>
                            <tbody>
                                {series.map((row, i) => {
                                    const pct = peak.cost > 0 ? (row.cost / peak.cost) * 100 : 0;
                                    return (
                                        <tr key={i}>
                                            <td className="text-t-secondary">{row.date}</td>
                                            <td className="td-num text-right font-medium text-t-primary">
                                                {money(row.cost, currency)}
                                            </td>
                                            <td>
                                                <div className="meter">
                                                    <div
                                                        className="meter-fill bg-primary-01"
                                                        style={{ width: `${Math.max(pct, 2)}%` }}
                                                    />
                                                </div>
                                            </td>
                                        </tr>
                                    );
                                })}
                            </tbody>
                        </table>
                    </div>
                </Card>
            )}
        </Layout>
    );
}
