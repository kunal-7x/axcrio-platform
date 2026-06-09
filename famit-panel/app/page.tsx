"use client";

import { useEffect, useState } from "react";
import Layout from "@/components/Layout";
import Card from "@/components/Card";
import { getCalls, getStats, getLeads, getUsage, type CallLog, type Stats, type Lead, type UsageData } from "@/lib/api";
import {
    ResponsiveContainer,
    BarChart,
    Bar,
    XAxis,
    YAxis,
    CartesianGrid,
    Tooltip,
} from "recharts";

function StatCard({
    label,
    value,
}: {
    label: string;
    value: number | string;
}) {
    return (
        <div className="card p-5 flex flex-col gap-2">
            <div className="text-caption text-t-tertiary">{label}</div>
            <div className="text-h4 text-t-primary">{value}</div>
        </div>
    );
}

function statusBadge(status: string) {
    const map: Record<string, string> = {
        answered: "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400",
        done: "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400",
        failed: "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400",
        calling: "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400",
        in_progress: "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400",
        queued: "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400",
    };
    return (
        <span
            className={`inline-flex px-2 py-0.5 rounded-full text-caption font-medium ${map[status] || "bg-b-surface3 text-t-secondary"}`}
        >
            {status}
        </span>
    );
}

function fmt(dateStr: string) {
    if (!dateStr) return "—";
    try {
        return new Date(dateStr).toLocaleString();
    } catch {
        return dateStr;
    }
}

export default function DashboardPage() {
    const [stats, setStats] = useState<Stats | null>(null);
    const [calls, setCalls] = useState<CallLog[]>([]);
    const [error, setError] = useState("");
    const [hotLeads, setHotLeads] = useState<Lead[]>([]);
    const [usage, setUsage] = useState<UsageData | null>(null);

    useEffect(() => {
        getStats()
            .then(setStats)
            .catch((e) => setError(e.message));
        getCalls()
            .then((r) => setCalls(r.calls.slice(0, 20)))
            .catch(() => {});
        getLeads({ hot: true })
            .then((r) => setHotLeads(r.leads.slice(0, 5)))
            .catch(() => {});
        getUsage()
            .then(setUsage)
            .catch(() => {});
    }, []);

    return (
        <Layout title="Dashboard">
            {error && (
                <div className="mb-4 p-3 rounded-2xl bg-red-50 text-red-600 text-body-2 dark:bg-red-900/20 dark:text-red-400">
                    {error}
                </div>
            )}

            {/* Stat cards */}
            <div className="grid grid-cols-4 gap-4 mb-6 max-lg:grid-cols-2 max-sm:grid-cols-1">
                <StatCard label="Total Calls" value={stats?.total ?? "—"} />
                <StatCard label="Answered" value={stats?.answered ?? "—"} />
                <StatCard
                    label="In Progress"
                    value={stats?.in_progress ?? "—"}
                />
                <StatCard
                    label="Campaigns"
                    value={stats?.campaigns ?? "—"}
                />
            </div>

            {/* Bar chart */}
            {stats?.series && stats.series.length > 0 && (
                <Card title="Call Activity" className="mb-6">
                    <div className="px-4 pb-4">
                        <div className="h-60">
                            <ResponsiveContainer width="100%" height="100%">
                                <BarChart
                                    data={stats.series}
                                    margin={{
                                        top: 8,
                                        right: 8,
                                        left: 0,
                                        bottom: 0,
                                    }}
                                >
                                    <XAxis
                                        dataKey="name"
                                        axisLine={false}
                                        tickLine={false}
                                        tick={{
                                            fontSize: "12px",
                                            fill: "var(--text-tertiary)",
                                        }}
                                    />
                                    <YAxis
                                        axisLine={false}
                                        tickLine={false}
                                        tick={{
                                            fontSize: "12px",
                                            fill: "var(--text-tertiary)",
                                        }}
                                        width={32}
                                    />
                                    <CartesianGrid
                                        strokeDasharray="5 7"
                                        vertical={false}
                                        stroke="var(--stroke-stroke2)"
                                    />
                                    <Tooltip
                                        contentStyle={{
                                            background: "var(--backgrounds-surface2)",
                                            border: "1px solid var(--stroke-stroke2)",
                                            borderRadius: "12px",
                                        }}
                                    />
                                    <Bar
                                        dataKey="amt"
                                        fill="var(--primary-02)"
                                        radius={[4, 4, 0, 0]}
                                    />
                                </BarChart>
                            </ResponsiveContainer>
                        </div>
                    </div>
                </Card>
            )}

            {/* Hot Leads + Usage widgets */}
            <div className="grid grid-cols-2 gap-6 mb-6 max-lg:grid-cols-1">
                {/* Hot Leads widget */}
                <Card title="Hot Leads">
                    <div className="px-5 pb-5">
                        {hotLeads.length === 0 ? (
                            <div className="py-6 text-center text-t-secondary text-body-2">
                                No hot leads yet
                            </div>
                        ) : (
                            <div className="space-y-2">
                                {hotLeads.map((l) => (
                                    <div key={l.id} className="flex items-center justify-between py-2 border-b border-s-subtle last:border-0">
                                        <div>
                                            <div className="text-body-2 font-medium text-t-primary">{l.name}</div>
                                            <div className="text-caption text-t-secondary">{l.phone}</div>
                                        </div>
                                        <div className="flex items-center gap-2">
                                            {l.score != null && (
                                                <span className="inline-flex px-2 py-0.5 rounded-full text-caption font-medium bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400">
                                                    {l.score} hot
                                                </span>
                                            )}
                                            {l.last_outcome && (
                                                <span className="text-caption text-t-tertiary">{l.last_outcome.replace(/_/g, " ")}</span>
                                            )}
                                        </div>
                                    </div>
                                ))}
                                <a href="/leads?hot=1" className="block text-caption text-center text-t-secondary hover:text-t-primary mt-2 transition-colors">
                                    View all hot leads
                                </a>
                            </div>
                        )}
                    </div>
                </Card>

                {/* Usage widget */}
                <Card title="Usage This Month">
                    <div className="px-5 pb-5">
                        {!usage ? (
                            <div className="py-6 text-center text-t-secondary text-body-2">Loading usage…</div>
                        ) : (
                            <div className="space-y-4">
                                <div className="grid grid-cols-2 gap-4">
                                    <div>
                                        <div className="text-caption text-t-tertiary">Calls today</div>
                                        <div className="text-h5 text-t-primary">{usage.today.calls}</div>
                                        <div className="text-caption text-t-tertiary">of {usage.limits.daily_call_cap} cap</div>
                                    </div>
                                    <div>
                                        <div className="text-caption text-t-tertiary">Minutes this month</div>
                                        <div className="text-h5 text-t-primary">{usage.month.minutes}</div>
                                        <div className="text-caption text-t-tertiary">of {usage.limits.monthly_minutes_cap} cap</div>
                                    </div>
                                    <div>
                                        <div className="text-caption text-t-tertiary">Active calls now</div>
                                        <div className="text-h5 text-t-primary">{usage.active_now}</div>
                                        <div className="text-caption text-t-tertiary">of {usage.limits.max_concurrency} max</div>
                                    </div>
                                    <div>
                                        <div className="text-caption text-t-tertiary">Monthly calls</div>
                                        <div className="text-h5 text-t-primary">{usage.month.calls}</div>
                                        <div className="text-caption text-t-tertiary">
                                            {usage.limits.daily_call_cap > 0
                                                ? `${((usage.today.calls / usage.limits.daily_call_cap) * 100).toFixed(0)}% of daily cap`
                                                : ""}
                                        </div>
                                    </div>
                                </div>
                                {/* Monthly minutes progress bar */}
                                {usage.limits.monthly_minutes_cap > 0 && (
                                    <div>
                                        <div className="flex justify-between text-caption text-t-tertiary mb-1">
                                            <span>Monthly minutes</span>
                                            <span>{((usage.month.minutes / usage.limits.monthly_minutes_cap) * 100).toFixed(1)}%</span>
                                        </div>
                                        <div className="w-full bg-b-surface3 rounded-full h-2">
                                            <div
                                                className="bg-primary-02 h-2 rounded-full transition-all"
                                                style={{ width: `${Math.min(100, (usage.month.minutes / usage.limits.monthly_minutes_cap) * 100)}%` }}
                                            />
                                        </div>
                                    </div>
                                )}
                            </div>
                        )}
                    </div>
                </Card>
            </div>

            {/* Recent calls table */}
            <Card title="Recent Calls">
                <div className="overflow-x-auto">
                    <table className="w-full text-body-2 [&_th]:h-13 [&_th,&_td]:px-5 [&_th,&_td]:py-3 [&_th]:align-middle [&_th]:text-left [&_th]:text-caption [&_th]:text-t-tertiary/80 [&_th]:font-normal">
                        <thead>
                            <tr>
                                <th>Name</th>
                                <th>Phone</th>
                                <th>Campaign</th>
                                <th>Status</th>
                                <th>Started</th>
                                <th>Duration</th>
                            </tr>
                        </thead>
                        <tbody>
                            {calls.length === 0 ? (
                                <tr>
                                    <td
                                        colSpan={6}
                                        className="py-8 text-center text-t-secondary"
                                    >
                                        No calls yet
                                    </td>
                                </tr>
                            ) : (
                                calls.map((c) => (
                                    <tr
                                        key={c.id}
                                        className="border-t border-s-subtle"
                                    >
                                        <td>{c.name}</td>
                                        <td>{c.phone}</td>
                                        <td>{c.campaign_name}</td>
                                        <td>{statusBadge(c.status)}</td>
                                        <td className="text-t-secondary">
                                            {fmt(c.started_at)}
                                        </td>
                                        <td className="text-t-secondary">
                                            {c.duration_s != null
                                                ? `${c.duration_s}s`
                                                : "—"}
                                        </td>
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
