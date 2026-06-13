"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import Layout from "@/components/Layout";
import Card from "@/components/Card";
import Table from "@/components/Table";
import TableRow from "@/components/TableRow";
import Percentage from "@/components/Percentage";
import Icon from "@/components/Icon";
import { StatusBadge, ScoreBadge } from "@/lib/badges";
import { useStats, useCalls, useLeads } from "@/lib/queries";
import {
    getUsage,
    type CallLog,
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
    const [usage, setUsage] = useState<UsageData | null>(null);

    // PERF UNIT-3: cached reads — these share the SAME cache entries as the Calls,
    // Leads and dashboard-stats reads elsewhere, so cross-tab navigation is instant.
    const statsQuery = useStats();
    const stats = statsQuery.data ?? null;
    const statsLoading = statsQuery.isLoading && !stats;
    const error =
        statsQuery.error instanceof Error ? statsQuery.error.message : "";

    const callsQuery = useCalls({ limit: 200, order: "desc", slim: true });
    const allCalls: CallLog[] = useMemo(
        () => callsQuery.data?.calls ?? [],
        [callsQuery.data]
    );
    const calls: CallLog[] = useMemo(() => allCalls.slice(0, 8), [allCalls]);
    const callsLoading = callsQuery.isLoading && allCalls.length === 0;

    const hotLeadsQuery = useLeads({ hot: true });
    const hotLeads: Lead[] = useMemo(
        () => (hotLeadsQuery.data?.leads ?? []).slice(0, 5),
        [hotLeadsQuery.data]
    );

    useEffect(() => {
        getUsage()
            .then(setUsage)
            .catch(() => {});
    }, []);

    // Real derived signals only (no prior-period data exists → no fake deltas).
    const series = stats?.series ?? [];
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

    return (
        <Layout title="Dashboard">
            {error && (
                <div className="mb-3 flex items-center gap-2 p-3.5 rounded-3xl bg-primary-03/8 text-primary-03 text-body-2">
                    <Icon name="info" className="size-4 fill-primary-03 shrink-0" />
                    {error}
                </div>
            )}

            <div className="flex max-lg:block">
                {/* ── col-left: volume chart + recent calls ── */}
                <div className="col-left">
                    {/* Call volume */}
                    <Card title="Call volume">
                        <div className="px-5 pb-5 max-lg:px-3">
                            {/* Headline numbers */}
                            <div className="flex flex-wrap items-end gap-x-8 gap-y-4 mb-4">
                                <Stat
                                    label="Total calls"
                                    value={
                                        statsLoading
                                            ? null
                                            : (stats?.total ?? 0).toLocaleString()
                                    }
                                    delta={trendDelta}
                                />
                                <Stat
                                    label="Answered"
                                    value={
                                        statsLoading
                                            ? null
                                            : (stats?.answered ?? 0).toLocaleString()
                                    }
                                    sub={
                                        answerRate != null
                                            ? `${answerRate}% answer rate`
                                            : undefined
                                    }
                                />
                                <Stat
                                    label="In progress"
                                    value={
                                        statsLoading
                                            ? null
                                            : (stats?.in_progress ?? 0).toLocaleString()
                                    }
                                    sub={
                                        usage
                                            ? `${usage.active_now} active now`
                                            : undefined
                                    }
                                />
                                <Stat
                                    label="Campaigns"
                                    value={
                                        statsLoading
                                            ? null
                                            : (stats?.campaigns ?? 0).toLocaleString()
                                    }
                                />
                            </div>

                            {/* Real-series area chart */}
                            <div className="h-56 max-lg:h-44">
                                {statsLoading ? (
                                    <div className="flex h-full items-end gap-2 pb-6">
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
                                                right: 8,
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
                                                    boxShadow:
                                                        "var(--box-shadow-dropdown)",
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
                                            No activity yet — your call trend
                                            renders here once a campaign runs.
                                        </div>
                                    </div>
                                )}
                            </div>
                        </div>
                    </Card>

                    {/* Recent calls */}
                    <Card
                        title="Recent calls"
                        headContent={
                            <Link href="/calls" className="action mr-1">
                                All calls
                                <Icon name="arrow-up-right" />
                            </Link>
                        }
                    >
                        <div className="pt-3 overflow-x-auto">
                            <Table
                                cellsThead={
                                    <>
                                        <th>Name</th>
                                        <th className="max-lg:hidden">Phone</th>
                                        <th className="max-md:hidden">
                                            Campaign
                                        </th>
                                        <th>Status</th>
                                        <th className="text-right">Started</th>
                                    </>
                                }
                            >
                                {callsLoading ? (
                                    [...Array(5)].map((_, i) => (
                                        <TableRow key={i}>
                                            {[...Array(5)].map((__, j) => (
                                                <td key={j}>
                                                    <div className="skeleton h-4 w-20" />
                                                </td>
                                            ))}
                                        </TableRow>
                                    ))
                                ) : calls.length === 0 ? (
                                    <TableRow>
                                        <td colSpan={5}>
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
                                                    results stream in here.
                                                </div>
                                            </div>
                                        </td>
                                    </TableRow>
                                ) : (
                                    calls.map((c) => (
                                        <TableRow key={c.id}>
                                            <td className="text-sub-title-1">
                                                {c.name}
                                            </td>
                                            <td className="text-t-secondary td-num max-lg:hidden">
                                                {c.phone}
                                            </td>
                                            <td className="text-t-secondary max-md:hidden">
                                                {c.campaign_name}
                                            </td>
                                            <td>
                                                <StatusBadge status={c.status} />
                                            </td>
                                            <td className="text-t-secondary whitespace-nowrap text-right">
                                                <span title={fmt(c.started_at)}>
                                                    {fmtCompact(c.started_at)}
                                                </span>
                                            </td>
                                        </TableRow>
                                    ))
                                )}
                            </Table>
                        </div>
                    </Card>
                </div>

                {/* ── col-right: hot leads + usage ── */}
                <div className="col-right">
                    {/* Hot leads */}
                    <Card
                        title="Hot leads"
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
                                        <Icon
                                            name="profile"
                                            className="fill-inherit"
                                        />
                                    </span>
                                    <div className="state-title">
                                        No hot leads yet
                                    </div>
                                    <div className="state-sub">
                                        Leads that score 70+ on a call surface
                                        here automatically.
                                    </div>
                                </div>
                            ) : (
                                <div className="flex flex-col">
                                    {hotLeads.map((l) => (
                                        <Link
                                            key={l.id}
                                            href="/leads?hot=1"
                                            className="group flex items-center justify-between gap-3 px-2 py-3 rounded-2xl transition-colors hover:bg-b-surface1/60 dark:hover:bg-shade-04/30"
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
                                            <ScoreBadge score={l.score} />
                                        </Link>
                                    ))}
                                </div>
                            )}
                        </div>
                    </Card>

                    {/* Usage this month */}
                    <Card title="Usage this month">
                        <div className="px-5 pb-5 max-lg:px-3">
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
                                    {usage.limits.monthly_minutes_cap > 0 ? (
                                        <div>
                                            <div className="flex items-end justify-between mb-2">
                                                <div>
                                                    <div className="eyebrow mb-1">
                                                        Minutes this month
                                                    </div>
                                                    <div className="text-h5 text-t-primary tabular-nums">
                                                        {usage.month.minutes}
                                                        <span className="text-h6 text-t-tertiary">
                                                            {" "}
                                                            /{" "}
                                                            {
                                                                usage.limits
                                                                    .monthly_minutes_cap
                                                            }
                                                        </span>
                                                    </div>
                                                </div>
                                                <div className="text-sub-title-2 text-t-secondary tabular-nums">
                                                    {(
                                                        (usage.month.minutes /
                                                            usage.limits
                                                                .monthly_minutes_cap) *
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
                                                            (usage.month
                                                                .minutes /
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
                                            <div className="text-h5 text-t-primary tabular-nums">
                                                {usage.month.minutes}
                                            </div>
                                        </div>
                                    )}

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
                                            sub="this period"
                                        />
                                    </div>
                                </div>
                            )}
                        </div>
                    </Card>
                </div>
            </div>
        </Layout>
    );
}

function Stat({
    label,
    value,
    sub,
    delta,
}: {
    label: string;
    value: string | null;
    sub?: string;
    delta?: number | null;
}) {
    return (
        <div>
            <div className="eyebrow mb-1.5">{label}</div>
            <div className="flex items-end gap-2">
                <div className="text-h4 text-t-primary tabular-nums max-lg:text-h5">
                    {value === null ? (
                        <span className="skeleton inline-block h-8 w-16 align-bottom" />
                    ) : (
                        value
                    )}
                </div>
                {delta != null && <Percentage className="mb-1" value={delta} />}
            </div>
            {sub && (
                <div className="mt-1 text-caption text-t-tertiary">{sub}</div>
            )}
        </div>
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
