"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import Layout from "@/components/Layout";
import Card from "@/components/Card";
import PageHeader from "@/components/PageHeader";
import KpiCard from "@/components/KpiCard";
import Percentage from "@/components/Percentage";
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
    AreaChart,
    Area,
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

// Compact "x ago / time" for the recent-calls list — calmer than a full
// locale string, keeps rows scannable. Falls back to fmt() for old dates.
function fmtCompact(dateStr: string) {
    if (!dateStr) return "—";
    const d = new Date(dateStr);
    if (isNaN(d.getTime())) return dateStr;
    const diff = Date.now() - d.getTime();
    const min = Math.floor(diff / 60000);
    if (min < 1) return "just now";
    if (min < 60) return `${min}m ago`;
    const hr = Math.floor(min / 60);
    if (hr < 24) return `${hr}h ago`;
    const day = Math.floor(hr / 24);
    if (day < 7) return `${day}d ago`;
    return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

export default function DashboardPage() {
    const [stats, setStats] = useState<Stats | null>(null);
    const [calls, setCalls] = useState<CallLog[]>([]);
    const [error, setError] = useState("");
    const [hotLeads, setHotLeads] = useState<Lead[]>([]);
    const [usage, setUsage] = useState<UsageData | null>(null);
    const [callsLoading, setCallsLoading] = useState(true);
    const [statsLoading, setStatsLoading] = useState(true);

    useEffect(() => {
        getStats()
            .then(setStats)
            .catch((e) => setError(e.message))
            .finally(() => setStatsLoading(false));
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

    // Honest day-over-day delta for Total Calls — derived ONLY from the real
    // series (last point vs the previous). No fabricated period comparisons.
    const trendDelta = useMemo(() => {
        if (series.length < 2) return null;
        const last = series[series.length - 1].amt;
        const prev = series[series.length - 2].amt;
        if (prev <= 0) return null;
        const pct = Math.round(((last - prev) / prev) * 100);
        if (pct === 0) return null; // Percentage renders 0 as "down" — skip flat.
        return pct;
    }, [series]);

    const peakDay = useMemo(() => {
        if (series.length === 0) return null;
        return series.reduce((a, b) => (b.amt > a.amt ? b : a));
    }, [series]);

    return (
        <Layout title="Dashboard">
            <PageHeader
                eyebrow="Overview"
                title="Dashboard"
                subtitle="Your live calling operation at a glance — volume, answer rate, hot leads and usage against your plan."
            />
            {error && (
                <div className="mb-3 flex items-center gap-2 p-3.5 rounded-2xl bg-primary-03/8 border border-primary-03/20 text-primary-03 text-body-2 rise-in">
                    <Icon name="info" className="size-4 fill-primary-03 shrink-0" />
                    {error}
                </div>
            )}

            {/* ── HERO: dominant call-volume metric + integrated trend chart ── */}
            <div className="kpi rise-in mb-3 !p-0 overflow-hidden">
                <div className="grid grid-cols-[minmax(0,0.9fr)_minmax(0,1.6fr)] max-lg:grid-cols-1">
                    {/* Left rail — the headline number */}
                    <div className="relative flex flex-col justify-between gap-6 p-6 max-lg:p-5 max-lg:pb-0">
                        <div className="flex items-center gap-2 text-overline text-t-tertiary">
                            <span className="kpi-glyph fill-primary-02">
                                <Icon name="chart" className="fill-inherit" />
                            </span>
                            Total Calls
                        </div>

                        <div>
                            <div className="flex items-end gap-3 flex-wrap">
                                <div className="text-h1 text-t-primary tracking-tight tabular-nums max-lg:text-h2">
                                    {statsLoading ? (
                                        <span className="skeleton inline-block h-12 w-28 align-bottom" />
                                    ) : (
                                        (stats?.total ?? "—")
                                    )}
                                </div>
                                {trendDelta != null && (
                                    <Percentage
                                        value={trendDelta}
                                        className="mb-2"
                                    />
                                )}
                            </div>
                            <div className="mt-2 text-body-2 text-t-secondary">
                                {series.length > 0 ? (
                                    <>
                                        Across the last{" "}
                                        <span className="text-t-primary font-medium">
                                            {series.length} days
                                        </span>
                                        {trendDelta != null && (
                                            <>
                                                {" · "}
                                                <span
                                                    className={
                                                        trendDelta > 0
                                                            ? "text-primary-02"
                                                            : "text-primary-03"
                                                    }
                                                >
                                                    {trendDelta > 0 ? "up" : "down"}{" "}
                                                    vs prior day
                                                </span>
                                            </>
                                        )}
                                    </>
                                ) : (
                                    "Live call volume will appear here."
                                )}
                            </div>

                            {/* Mini real-signal chips */}
                            <div className="flex flex-wrap items-center gap-2 mt-4 max-lg:mb-1">
                                {answerRate != null && (
                                    <span className="inline-flex items-center gap-1.5 h-7 px-2.5 rounded-full bg-b-surface1 text-caption text-t-secondary dark:bg-shade-04/50">
                                        <span className="size-1.5 rounded-full bg-primary-02" />
                                        {answerRate}% answered
                                    </span>
                                )}
                                {peakDay && peakDay.amt > 0 && (
                                    <span className="inline-flex items-center gap-1.5 h-7 px-2.5 rounded-full bg-b-surface1 text-caption text-t-secondary dark:bg-shade-04/50">
                                        Peak {peakDay.amt} · {peakDay.name}
                                    </span>
                                )}
                                {usage && (
                                    <span className="inline-flex items-center gap-1.5 h-7 px-2.5 rounded-full bg-b-surface1 text-caption text-t-secondary dark:bg-shade-04/50">
                                        {usage.active_now} active now
                                    </span>
                                )}
                            </div>
                        </div>
                    </div>

                    {/* Right — full-bleed gradient area chart (real series) */}
                    <div className="relative min-h-56 p-2 pt-4 max-lg:min-h-44 border-l border-s-subtle max-lg:border-l-0 max-lg:border-t">
                        {statsLoading ? (
                            <div className="flex h-full items-end gap-2 px-4 pb-6">
                                {[...Array(9)].map((_, i) => (
                                    <div
                                        key={i}
                                        className="skeleton flex-1 rounded-md"
                                        style={{
                                            height: `${30 + ((i * 37) % 60)}%`,
                                        }}
                                    />
                                ))}
                            </div>
                        ) : series.length > 0 ? (
                            <ResponsiveContainer width="100%" height="100%">
                                <AreaChart
                                    data={series}
                                    margin={{
                                        top: 8,
                                        right: 12,
                                        left: 0,
                                        bottom: 0,
                                    }}
                                >
                                    <defs>
                                        <linearGradient
                                            id="heroArea"
                                            x1="0"
                                            y1="0"
                                            x2="0"
                                            y2="1"
                                        >
                                            <stop
                                                offset="5%"
                                                stopColor="var(--primary-02)"
                                                stopOpacity={0.22}
                                            />
                                            <stop
                                                offset="95%"
                                                stopColor="var(--primary-02)"
                                                stopOpacity={0}
                                            />
                                        </linearGradient>
                                    </defs>
                                    <XAxis
                                        dataKey="name"
                                        axisLine={false}
                                        tickLine={false}
                                        tick={{
                                            fontSize: "12px",
                                            fill: "var(--text-tertiary)",
                                        }}
                                        height={28}
                                        dy={8}
                                        minTickGap={16}
                                    />
                                    <YAxis
                                        axisLine={false}
                                        tickLine={false}
                                        tick={{
                                            fontSize: "12px",
                                            fill: "var(--text-tertiary)",
                                        }}
                                        width={32}
                                        allowDecimals={false}
                                    />
                                    <CartesianGrid
                                        strokeDasharray="5 7"
                                        vertical={false}
                                        stroke="var(--stroke-stroke2)"
                                    />
                                    <Tooltip
                                        cursor={{
                                            stroke: "var(--stroke-stroke2)",
                                        }}
                                        contentStyle={{
                                            background:
                                                "var(--backgrounds-surface2)",
                                            border: "1px solid var(--stroke-stroke2)",
                                            borderRadius: "12px",
                                            boxShadow: "var(--box-shadow-dropdown)",
                                            fontSize: "12px",
                                        }}
                                        labelStyle={{
                                            color: "var(--text-tertiary)",
                                            marginBottom: "2px",
                                        }}
                                    />
                                    <Area
                                        type="monotone"
                                        dataKey="amt"
                                        name="Calls"
                                        stroke="var(--primary-02)"
                                        strokeWidth={2.5}
                                        fillOpacity={1}
                                        fill="url(#heroArea)"
                                        activeDot={{
                                            r: 5,
                                            fill: "var(--backgrounds-surface2)",
                                            stroke: "var(--primary-02)",
                                            strokeWidth: 3,
                                        }}
                                    />
                                </AreaChart>
                            </ResponsiveContainer>
                        ) : (
                            <div className="flex h-full items-center justify-center">
                                <div className="state-sub text-center">
                                    No activity yet — your call trend renders here
                                    once a campaign runs.
                                </div>
                            </div>
                        )}
                    </div>
                </div>
            </div>

            {/* Secondary KPI row — real sub-signals, no fabricated deltas */}
            <div className="grid grid-cols-3 gap-3 mb-3 max-md:grid-cols-1">
                <KpiCard
                    label="Answered"
                    value={stats?.answered ?? "—"}
                    icon="check-circle"
                    tone="success"
                    spark={sparkData}
                    sub={
                        answerRate != null ? (
                            <span className="text-primary-02">
                                {answerRate}% answer rate
                            </span>
                        ) : undefined
                    }
                    meter={answerRate != null ? answerRate / 100 : null}
                    style={{ animationDelay: "60ms" }}
                />
                <KpiCard
                    label="In Progress"
                    value={stats?.in_progress ?? "—"}
                    icon="clock"
                    tone="warning"
                    sub={usage ? `${usage.active_now} active now` : undefined}
                    style={{ animationDelay: "120ms" }}
                />
                <KpiCard
                    label="Campaigns"
                    value={stats?.campaigns ?? "—"}
                    icon="dashboard"
                    tone="info"
                    sub={
                        usage
                            ? `${usage.month.calls} calls this month`
                            : undefined
                    }
                    style={{ animationDelay: "180ms" }}
                />
            </div>

            {/* Hot Leads + Usage */}
            <div className="grid grid-cols-2 gap-3 mb-3 max-lg:grid-cols-1">
                {/* Hot Leads */}
                <Card
                    title="Hot Leads"
                    headContent={
                        <Link href="/leads?hot=1" className="action mr-1">
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
                                {hotLeads.map((l, i) => (
                                    <Link
                                        key={l.id}
                                        href={`/leads?hot=1`}
                                        className="group flex items-center justify-between gap-3 px-2 py-3 rounded-2xl transition-colors hover:bg-b-surface1/60 dark:hover:bg-shade-04/30 rise-in"
                                        style={{
                                            animationDelay: `${i * 50}ms`,
                                        }}
                                    >
                                        <div className="flex items-center gap-3 min-w-0">
                                            <span className="flex items-center justify-center size-9 shrink-0 rounded-full bg-b-surface1 text-sub-title-2 text-t-secondary transition-colors group-hover:text-t-primary dark:bg-shade-04/60">
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
                                    </Link>
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
                                        <td className="text-t-secondary whitespace-nowrap">
                                            <span title={fmt(c.started_at)}>
                                                {fmtCompact(c.started_at)}
                                            </span>
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
