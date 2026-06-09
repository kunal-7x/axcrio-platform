"use client";

import { useEffect, useState, useCallback } from "react";
import Layout from "@/components/Layout";
import Card from "@/components/Card";
import { getAnalytics, getCampaigns, type AnalyticsFunnel, type Campaign } from "@/lib/api";
import {
    ResponsiveContainer,
    BarChart,
    Bar,
    XAxis,
    YAxis,
    CartesianGrid,
    Tooltip,
    FunnelChart,
    Funnel,
    LabelList,
    Cell,
} from "recharts";

const FUNNEL_COLORS = ["#6366f1", "#8b5cf6", "#a78bfa", "#c4b5fd", "#ddd6fe", "#e0e7ff", "#f0fdf4"];

function StatCard({ label, value, sub }: { label: string; value: number | string; sub?: string }) {
    return (
        <div className="card p-4 flex flex-col gap-1">
            <div className="text-caption text-t-tertiary">{label}</div>
            <div className="text-h5 text-t-primary">{value}</div>
            {sub && <div className="text-caption text-t-tertiary">{sub}</div>}
        </div>
    );
}

export default function AnalyticsPage() {
    const [data, setData] = useState<AnalyticsFunnel | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState("");
    const [campaigns, setCampaigns] = useState<Campaign[]>([]);
    const [campaignId, setCampaignId] = useState("");

    const load = useCallback(() => {
        setLoading(true);
        setError("");
        getAnalytics(campaignId ? { campaign_id: campaignId } : undefined)
            .then(setData)
            .catch((e) => setError(e instanceof Error ? e.message : "Failed to load analytics"))
            .finally(() => setLoading(false));
    }, [campaignId]);

    useEffect(() => {
        getCampaigns()
            .then((r) => setCampaigns(r.campaigns))
            .catch(() => {});
    }, []);

    useEffect(() => { load(); }, [load]);

    // Auto-refresh every 30s
    useEffect(() => {
        const t = setInterval(load, 30000);
        return () => clearInterval(t);
    }, [load]);

    const funnelData = data?.funnel ?? [];
    const convRate = data && data.dialed > 0
        ? ((data.answered / data.dialed) * 100).toFixed(1)
        : "—";
    const qualRate = data && data.answered > 0
        ? ((data.qualified / data.answered) * 100).toFixed(1)
        : "—";

    return (
        <Layout title="Analytics">
            {error && (
                <div className="mb-4 p-3 rounded-2xl bg-red-50 text-red-600 text-body-2 dark:bg-red-900/20 dark:text-red-400">
                    {error}
                </div>
            )}

            {/* Filters */}
            <div className="flex items-center gap-4 mb-6 flex-wrap">
                <div>
                    <label className="block text-caption text-t-secondary mb-1">Campaign</label>
                    <select
                        className="h-10 px-3 border border-s-stroke2 rounded-2xl text-body-2 text-t-primary outline-none bg-transparent hover:border-s-highlight focus:border-s-highlight"
                        value={campaignId}
                        onChange={(e) => setCampaignId(e.target.value)}
                    >
                        <option value="">All Campaigns</option>
                        {campaigns.map((c) => (
                            <option key={c.id} value={c.id}>{c.name}</option>
                        ))}
                    </select>
                </div>
                <button
                    onClick={load}
                    className="mt-5 h-10 px-4 border border-s-stroke2 rounded-2xl text-body-2 text-t-primary hover:border-s-highlight transition-colors"
                >
                    {loading ? "Refreshing…" : "Refresh"}
                </button>
                <span className="mt-5 text-caption text-t-tertiary">Auto-refreshes every 30s</span>
            </div>

            {/* Summary stat cards */}
            {data && (
                <div className="grid grid-cols-4 gap-4 mb-6 max-lg:grid-cols-2 max-sm:grid-cols-2">
                    <StatCard label="Dialed" value={data.dialed} />
                    <StatCard label="Answered" value={data.answered} sub={`${convRate}% connect rate`} />
                    <StatCard label="Interested" value={data.interested} />
                    <StatCard label="Qualified (score≥70)" value={data.qualified} sub={`${qualRate}% of answered`} />
                    <StatCard label="Callbacks" value={data.callback} />
                    <StatCard label="Opted Out" value={data.opted_out} />
                    <StatCard label="Voicemail" value={data.voicemail} />
                    <StatCard label="No Answer" value={data.no_answer} />
                </div>
            )}

            {loading && !data && (
                <div className="flex items-center justify-center py-16 text-t-secondary gap-2">
                    <svg className="animate-spin h-5 w-5" viewBox="0 0 24 24" fill="none">
                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/>
                        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/>
                    </svg>
                    Loading analytics…
                </div>
            )}

            <div className="grid grid-cols-2 gap-6 max-lg:grid-cols-1">
                {/* Conversion Funnel */}
                {funnelData.length > 0 && (
                    <Card title="Conversion Funnel">
                        <div className="px-4 pb-4">
                            <div className="h-72">
                                <ResponsiveContainer width="100%" height="100%">
                                    <FunnelChart>
                                        <Tooltip
                                            contentStyle={{
                                                background: "var(--backgrounds-surface2)",
                                                border: "1px solid var(--stroke-stroke2)",
                                                borderRadius: "12px",
                                            }}
                                        />
                                        <Funnel
                                            dataKey="count"
                                            data={funnelData}
                                            isAnimationActive
                                        >
                                            {funnelData.map((_, i) => (
                                                <Cell key={i} fill={FUNNEL_COLORS[i % FUNNEL_COLORS.length]} />
                                            ))}
                                            <LabelList
                                                position="right"
                                                fill="var(--text-secondary)"
                                                stroke="none"
                                                dataKey="stage"
                                                style={{ fontSize: "12px" }}
                                            />
                                        </Funnel>
                                    </FunnelChart>
                                </ResponsiveContainer>
                            </div>
                        </div>
                    </Card>
                )}

                {/* Outcome bar chart */}
                {data && (
                    <Card title="Outcome Breakdown">
                        <div className="px-4 pb-4">
                            <div className="h-72">
                                <ResponsiveContainer width="100%" height="100%">
                                    <BarChart
                                        data={[
                                            { name: "Answered", amt: data.answered },
                                            { name: "Interested", amt: data.interested },
                                            { name: "Qualified", amt: data.qualified },
                                            { name: "Callback", amt: data.callback },
                                            { name: "Voicemail", amt: data.voicemail },
                                            { name: "No Answer", amt: data.no_answer },
                                            { name: "Opted Out", amt: data.opted_out },
                                        ]}
                                        margin={{ top: 8, right: 8, left: 0, bottom: 0 }}
                                    >
                                        <XAxis
                                            dataKey="name"
                                            axisLine={false}
                                            tickLine={false}
                                            tick={{ fontSize: "11px", fill: "var(--text-tertiary)" }}
                                        />
                                        <YAxis
                                            axisLine={false}
                                            tickLine={false}
                                            tick={{ fontSize: "12px", fill: "var(--text-tertiary)" }}
                                            width={32}
                                        />
                                        <CartesianGrid strokeDasharray="5 7" vertical={false} stroke="var(--stroke-stroke2)" />
                                        <Tooltip
                                            contentStyle={{
                                                background: "var(--backgrounds-surface2)",
                                                border: "1px solid var(--stroke-stroke2)",
                                                borderRadius: "12px",
                                            }}
                                        />
                                        <Bar dataKey="amt" fill="var(--primary-02)" radius={[4, 4, 0, 0]} />
                                    </BarChart>
                                </ResponsiveContainer>
                            </div>
                        </div>
                    </Card>
                )}
            </div>

            {/* Funnel table */}
            {funnelData.length > 0 && (
                <Card title="Funnel Details" className="mt-6">
                    <div className="overflow-x-auto">
                        <table className="w-full text-body-2 [&_th]:h-13 [&_th,&_td]:px-5 [&_th,&_td]:py-3 [&_th]:align-middle [&_th]:text-left [&_th]:text-caption [&_th]:text-t-tertiary/80 [&_th]:font-normal">
                            <thead>
                                <tr>
                                    <th>Stage</th>
                                    <th>Count</th>
                                    <th>% of Dialed</th>
                                </tr>
                            </thead>
                            <tbody>
                                {funnelData.map((row, i) => (
                                    <tr key={i} className="border-t border-s-subtle">
                                        <td className="font-medium capitalize">{row.stage.replace(/_/g, " ")}</td>
                                        <td className="text-t-primary">{row.count}</td>
                                        <td className="text-t-secondary">
                                            {data && data.dialed > 0 ? `${((row.count / data.dialed) * 100).toFixed(1)}%` : "—"}
                                        </td>
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
