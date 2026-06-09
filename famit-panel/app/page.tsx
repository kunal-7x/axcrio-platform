"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import Layout from "@/components/Layout";
import Card from "@/components/Card";
import KpiCard from "@/components/KpiCard";
import Icon from "@/components/Icon";
import { StatusBadge, ScoreBadge } from "@/lib/badges";
import {
    getCalls,
    getStats,
    getLeads,
    getUsage,
    type CallLog,
    type Stats,
    type Lead,
    type UsageData,
} from "@/lib/api";
import {
    ResponsiveContainer,
    BarChart,
    Bar,
    XAxis,
    YAxis,
    CartesianGrid,
    Tooltip,
} from "recharts";

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
    const [callsLoading, setCallsLoading] = useState(true);

    useEffect(() => {
        getStats()
            .then(setStats)
            .catch((e) => setError(e.message));
        getCalls()
            .then((r) => setCalls(r.calls.slice(0, 20)))
            .catch(() => {})
            .finally(() => setCallsLoading(false));
        getLeads({ hot: true })
            .then((r) => setHotLeads(r.leads.slice(0, 5)))
            .catch(() => {});
        getUsage()
            .then(setUsage)
            .catch(() => {});
    }, []);

    // Real derived signals only (no prior-period data exists → no fake deltas).
    const series = stats?.series ?? [];
    const sparkData = series.map((s) => s.amt);
    const answerRate =
        stats && stats.total > 0
            ? Math.round((stats.answered / stats.total) * 100)
            : null;

    return (
        <Layout title="Dashboard">
            {error && (
                <div className="mb-6 flex items-center gap-2 p-3.5 rounded-2xl bg-primary-03/8 border border-primary-03/20 text-primary-03 text-body-2">
                    <Icon name="info" className="size-4 fill-primary-03 shrink-0" />
                    {error}
                </div>
            )}

            {/* Hero KPI row */}
            <div className="mb-3">
                <div className="grid grid-cols-4 gap-3 max-lg:grid-cols-2 max-sm:grid-cols-1">
                    <KpiCard
                        label="Total Calls"
                        value={stats?.total ?? "—"}
                        icon="chat"
                        tone="info"
                        spark={sparkData}
                        sub={
                            series.length > 0
                                ? `${series.length} day window`
                                : undefined
                        }
                        style={{ animationDelay: "0ms" }}
                    />
                    <KpiCard
                        label="Answered"
                        value={stats?.answered ?? "—"}
                        icon="check-circle"
                        tone="success"
                        sub={
                            answerRate != null ? (
                                <span className="text-primary-02">
                                    {answerRate}% answer rate
                                </span>
                            ) : undefined
                        }
                        meter={
                            answerRate != null ? answerRate / 100 : null
                        }
                        style={{ animationDelay: "60ms" }}
                    />
                    <KpiCard
                        label="In Progress"
                        value={stats?.in_progress ?? "—"}
                        icon="clock"
                        tone="warning"
                        sub={
                            usage
                                ? `${usage.active_now} active now`
                                : undefined
                        }
                        style={{ animationDelay: "120ms" }}
                    />
                    <KpiCard
                        label="Campaigns"
                        value={stats?.campaigns ?? "—"}
                        icon="dashboard"
                        tone="neutral"
                        sub={
                            usage
                                ? `${usage.month.calls} calls this month`
                                : undefined
                        }
                        style={{ animationDelay: "180ms" }}
                    />
                </div>
            </div>

            {/* Activity chart */}
            {series.length > 0 && (
                <Card title="Call Activity" className="mb-3">
                    <div className="px-4 pb-4">
                        <div className="h-64">
                            <ResponsiveContainer width="100%" height="100%">
                                <BarChart
                                    data={series}
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
                                        cursor={{
                                            fill: "var(--backgrounds-surface3)",
                                        }}
                                        contentStyle={{
                                            background:
                                                "var(--backgrounds-surface2)",
                                            border: "1px solid var(--stroke-stroke2)",
                                            borderRadius: "12px",
                                            boxShadow: "var(--box-shadow-dropdown)",
                                        }}
                                    />
                                    <Bar
                                        dataKey="amt"
                                        fill="var(--primary-02)"
                                        radius={[6, 6, 0, 0]}
                                        maxBarSize={48}
                                    />
                                </BarChart>
                            </ResponsiveContainer>
                        </div>
                    </div>
                </Card>
            )}

            {/* Hot Leads + Usage */}
            <div className="grid grid-cols-2 gap-3 mb-3 max-lg:grid-cols-1">
                {/* Hot Leads */}
                <Card
                    title="Hot Leads"
                    headContent={
                        <Link
                            href="/leads?hot=1"
                            className="action mr-1"
                        >
                            View all
                            <Icon name="arrow-up-right" />
                        </Link>
                    }
                >
                    <div className="px-3 pb-3">
                        {hotLeads.length === 0 ? (
                            <div className="state-block">
                                <span className="state-glyph">
                                    <Icon name="profile" className="fill-inherit" />
                                </span>
                                <div className="state-title">No hot leads yet</div>
                                <div className="state-sub">
                                    Leads that score 70+ on a call surface here
                                    automatically.
                                </div>
                            </div>
                        ) : (
                            <div className="flex flex-col">
                                {hotLeads.map((l) => (
                                    <div
                                        key={l.id}
                                        className="flex items-center justify-between gap-3 px-2 py-3 rounded-2xl transition-colors hover:bg-b-surface1/60 dark:hover:bg-shade-04/30"
                                    >
                                        <div className="flex items-center gap-3 min-w-0">
                                            <span className="flex items-center justify-center size-9 shrink-0 rounded-full bg-b-surface1 text-sub-title-2 text-t-secondary dark:bg-shade-04/60">
                                                {(l.name || "?")
                                                    .charAt(0)
                                                    .toUpperCase()}
                                            </span>
                                            <div className="min-w-0">
                                                <div className="text-body-2 font-medium text-t-primary truncate">
                                                    {l.name}
                                                </div>
                                                <div className="text-caption text-t-tertiary tabular-nums">
                                                    {l.phone}
                                                </div>
                                            </div>
                                        </div>
                                        <div className="flex items-center gap-2 shrink-0">
                                            {l.last_outcome && (
                                                <span className="text-caption text-t-tertiary capitalize max-md:hidden">
                                                    {l.last_outcome.replace(
                                                        /_/g,
                                                        " "
                                                    )}
                                                </span>
                                            )}
                                            <ScoreBadge score={l.score} />
                                        </div>
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>
                </Card>

                {/* Usage */}
                <Card title="Usage This Month">
                    <div className="px-5 pb-5">
                        {!usage ? (
                            <div className="space-y-4 pt-2">
                                <div className="skeleton h-10 w-1/2" />
                                <div className="skeleton h-2 w-full" />
                                <div className="grid grid-cols-2 gap-4">
                                    <div className="skeleton h-12" />
                                    <div className="skeleton h-12" />
                                </div>
                            </div>
                        ) : (
                            <div className="space-y-5">
                                {/* Headline: minutes vs cap with meter */}
                                {usage.limits.monthly_minutes_cap > 0 ? (
                                    <div>
                                        <div className="flex items-end justify-between mb-2">
                                            <div>
                                                <div className="eyebrow mb-1">
                                                    Minutes this month
                                                </div>
                                                <div className="text-h4 text-t-primary tabular-nums">
                                                    {usage.month.minutes}
                                                    <span className="text-h6 text-t-tertiary">
                                                        {" "}
                                                        / {usage.limits.monthly_minutes_cap}
                                                    </span>
                                                </div>
                                            </div>
                                            <div className="text-sub-title-2 text-t-secondary tabular-nums">
                                                {(
                                                    (usage.month.minutes /
                                                        usage.limits.monthly_minutes_cap) *
                                                    100
                                                ).toFixed(0)}
                                                %
                                            </div>
                                        </div>
                                        <div className="meter">
                                            <div
                                                className="meter-fill bg-primary-02"
                                                style={{
                                                    width: `${Math.min(
                                                        100,
                                                        (usage.month.minutes /
                                                            usage.limits
                                                                .monthly_minutes_cap) *
                                                            100
                                                    )}%`,
                                                }}
                                            />
                                        </div>
                                    </div>
                                ) : (
                                    <div>
                                        <div className="eyebrow mb-1">
                                            Minutes this month
                                        </div>
                                        <div className="text-h4 text-t-primary tabular-nums">
                                            {usage.month.minutes}
                                        </div>
                                    </div>
                                )}

                                {/* Secondary stats grid */}
                                <div className="grid grid-cols-3 gap-3 pt-1 max-sm:grid-cols-1">
                                    <UsageStat
                                        label="Calls today"
                                        value={usage.today.calls}
                                        sub={`of ${usage.limits.daily_call_cap} cap`}
                                    />
                                    <UsageStat
                                        label="Active now"
                                        value={usage.active_now}
                                        sub={`of ${usage.limits.max_concurrency} max`}
                                    />
                                    <UsageStat
                                        label="Calls / month"
                                        value={usage.month.calls}
                                        sub="this billing period"
                                    />
                                </div>
                            </div>
                        )}
                    </div>
                </Card>
            </div>

            {/* Recent calls */}
            <Card
                title="Recent Calls"
                headContent={
                    <Link href="/calls" className="action mr-1">
                        All calls
                        <Icon name="arrow-up-right" />
                    </Link>
                }
            >
                <div className="overflow-x-auto">
                    <table className="data-table">
                        <thead>
                            <tr>
                                <th>Name</th>
                                <th>Phone</th>
                                <th>Campaign</th>
                                <th>Status</th>
                                <th>Started</th>
                                <th className="text-right">Duration</th>
                            </tr>
                        </thead>
                        <tbody>
                            {callsLoading ? (
                                [...Array(5)].map((_, i) => (
                                    <tr key={i}>
                                        {[...Array(6)].map((__, j) => (
                                            <td key={j}>
                                                <div className="skeleton h-4 w-20" />
                                            </td>
                                        ))}
                                    </tr>
                                ))
                            ) : calls.length === 0 ? (
                                <tr>
                                    <td colSpan={6}>
                                        <div className="state-block">
                                            <span className="state-glyph">
                                                <Icon
                                                    name="chat"
                                                    className="fill-inherit"
                                                />
                                            </span>
                                            <div className="state-title">
                                                No calls yet
                                            </div>
                                            <div className="state-sub">
                                                Run a campaign and your call
                                                results will stream in here.
                                            </div>
                                        </div>
                                    </td>
                                </tr>
                            ) : (
                                calls.map((c) => (
                                    <tr key={c.id}>
                                        <td className="font-medium text-t-primary">
                                            {c.name}
                                        </td>
                                        <td className="text-t-secondary td-num">
                                            {c.phone}
                                        </td>
                                        <td className="text-t-secondary">
                                            {c.campaign_name}
                                        </td>
                                        <td>
                                            <StatusBadge status={c.status} />
                                        </td>
                                        <td className="text-t-secondary">
                                            {fmt(c.started_at)}
                                        </td>
                                        <td className="text-t-secondary td-num text-right">
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

function UsageStat({
    label,
    value,
    sub,
}: {
    label: string;
    value: number | string;
    sub?: string;
}) {
    return (
        <div className="flex flex-col gap-0.5 p-3 rounded-2xl bg-b-surface1/60 dark:bg-shade-04/30">
            <div className="eyebrow">{label}</div>
            <div className="text-h6 text-t-primary tabular-nums">{value}</div>
            {sub && <div className="text-caption text-t-tertiary">{sub}</div>}
        </div>
    );
}
