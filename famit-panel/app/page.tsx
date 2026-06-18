"use client";

// W15 — the CONSOLIDATED dashboard (design/W15-UI-IA-PLAN.md §1, dest #1).
//
// This is the Today-first executive cockpit. It ABSORBS the scatter: the funnel
// (was on /analytics), the call-volume chart, the KPI hero, hot-leads and the usage
// tile now live in ONE home, driven by the shared GlobalFilters range and the W14
// reporting client (lib/report.ts). "View full report" deep-links into Reports
// (/analytics) carrying the same range — one analytics experience, two depths.
//
// Reuses the SAME Core_2 chrome it always had (Layout / Card / Table / TableRow /
// recharts area) — the only change is the data source (the report client) + the
// consolidated funnel/summary + LeadBadge + the GlobalFilters mount in the top
// Card's headContent slot. Nothing is built from scratch.

import { Suspense, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import Layout from "@/components/Layout";
import Card from "@/components/Card";
import Table from "@/components/Table";
import TableRow from "@/components/TableRow";
import Percentage from "@/components/Percentage";
import Icon from "@/components/Icon";
import GlobalFilters, { useGlobalFilters } from "@/components/GlobalFilters";
import { StatusBadge, LeadBadge } from "@/lib/badges";
import { useStats, useCalls } from "@/lib/queries";
import { getReport, type Report } from "@/lib/report";
import { getUsage, type CallLog, type UsageData } from "@/lib/api";
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

// Human label for the 8 canonical funnel stages (W14 model.FUNNEL_STAGES).
const FUNNEL_LABEL: Record<string, string> = {
    uploaded: "Uploaded",
    dialed: "Dialed",
    connected: "Connected",
    interested: "Interested",
    warm: "Warm",
    hot: "Hot",
    booked: "Booked",
    converted: "Converted",
};

// useSearchParams (via useGlobalFilters) must be under a Suspense boundary for the
// App-Router static prerender — same pattern as app/ai-manager/page.tsx.
export default function DashboardPage() {
    return (
        <Suspense fallback={<Layout title="Dashboard"><div /></Layout>}>
            <DashboardInner />
        </Suspense>
    );
}

function DashboardInner() {
    const { range, campaign, status } = useGlobalFilters();
    const [usage, setUsage] = useState<UsageData | null>(null);

    // The consolidated report (range-aware; dormant-safe). Re-fetches when the
    // shared range/campaign/status filter changes.
    const [report, setReport] = useState<Report | null>(null);
    const [reportLoading, setReportLoading] = useState(true);
    const [error, setError] = useState("");

    useEffect(() => {
        let active = true;
        setReportLoading(true);
        getReport(range, {
            campaign: campaign || undefined,
            lead_status: status || undefined,
        })
            .then((r) => {
                if (!active) return;
                setReport(r);
                setError("");
            })
            .catch((e) => active && setError(e instanceof Error ? e.message : "Failed to load report"))
            .finally(() => active && setReportLoading(false));
        return () => {
            active = false;
        };
    }, [range, campaign, status]);

    // Recent calls (cached; shared cache with the Calls page).
    const callsQuery = useCalls({ limit: 200, order: "desc", slim: true });
    const allCalls: CallLog[] = useMemo(
        () => callsQuery.data?.calls ?? [],
        [callsQuery.data]
    );
    const calls: CallLog[] = useMemo(() => allCalls.slice(0, 8), [allCalls]);
    const callsLoading = callsQuery.isLoading && allCalls.length === 0;

    // Day-over-day delta from the (real) stats series — honest, no fabricated periods.
    const statsQuery = useStats();
    const trendDelta = useMemo(() => {
        const series = statsQuery.data?.series ?? [];
        if (series.length < 2) return null;
        const last = series[series.length - 1].amt;
        const prev = series[series.length - 2].amt;
        if (prev <= 0) return null;
        const pct = Math.round(((last - prev) / prev) * 100);
        return pct === 0 ? null : pct;
    }, [statsQuery.data]);

    useEffect(() => {
        getUsage()
            .then(setUsage)
            .catch(() => {});
    }, []);

    const totals = report?.totals;
    const funnel = report?.funnel ?? [];
    const series = report?.timeline ?? [];
    const hotLeads = report?.hot_leads ?? [];
    const funnelTop = funnel[0]?.count || 1;

    // Link that carries the active range into Reports (one shared filter mental model).
    const reportsHref = useMemo(() => {
        const sp = new URLSearchParams();
        if (range.preset !== "today") sp.set("range", range.preset);
        if (range.preset === "custom") {
            sp.set("from", range.from);
            sp.set("to", range.to);
        }
        if (campaign) sp.set("campaign", campaign);
        if (status) sp.set("status", status);
        const qs = sp.toString();
        return qs ? `/analytics?${qs}` : "/analytics";
    }, [range, campaign, status]);

    return (
        <Layout title="Dashboard">
            {error && (
                <div className="mb-3 flex items-center gap-2 p-3.5 rounded-3xl bg-primary-03/8 text-primary-03 text-body-2">
                    <Icon name="info" className="size-4 fill-primary-03 shrink-0" />
                    {error}
                </div>
            )}

            {/* ── Executive summary: range filter + top-line KPI strip ── */}
            <Card
                title="Overview"
                className="mb-3"
                headContent={<GlobalFilters show={{ range: true, campaign: true, status: true }} />}
            >
                <div className="px-5 pb-5 max-lg:px-3">
                    <div className="grid grid-cols-4 gap-3 max-2xl:grid-cols-2 max-md:grid-cols-2">
                        <Kpi
                            label="Total calls"
                            value={reportLoading ? null : (totals?.calls ?? 0).toLocaleString()}
                            delta={trendDelta}
                        />
                        <Kpi
                            label="Connected"
                            value={reportLoading ? null : (totals?.connected ?? 0).toLocaleString()}
                            sub={totals ? `${totals.connect_rate}% connect rate` : undefined}
                        />
                        <Kpi
                            label="Booked"
                            value={reportLoading ? null : (totals?.booked ?? 0).toLocaleString()}
                            sub={totals ? `${totals.conversion_rate}% of calls` : undefined}
                        />
                        <Kpi
                            label="Hot leads"
                            value={reportLoading ? null : (totals?.hot ?? 0).toLocaleString()}
                            sub={
                                totals
                                    ? `${totals.warm} warm · ${totals.cold} cold`
                                    : undefined
                            }
                        />
                    </div>
                    {report && !report.live_seam && (
                        <div className="mt-3 text-caption text-t-tertiary">
                            Showing your latest activity. Real-time per-range totals
                            activate when the reporting stream is enabled on your box.
                        </div>
                    )}
                </div>
            </Card>

            <div className="flex max-lg:block">
                {/* ── col-left: volume chart + funnel + recent calls ── */}
                <div className="col-left">
                    {/* Call volume */}
                    <Card title="Call volume">
                        <div className="px-5 pb-5 max-lg:px-3">
                            <div className="h-56 max-lg:h-44">
                                {reportLoading ? (
                                    <div className="flex h-full items-end gap-2 pb-6">
                                        {[...Array(9)].map((_, i) => (
                                            <div
                                                key={i}
                                                className="skeleton flex-1 rounded-md"
                                                style={{ height: `${30 + ((i * 37) % 60)}%` }}
                                            />
                                        ))}
                                    </div>
                                ) : series.length > 0 ? (
                                    <ResponsiveContainer width="100%" height="100%">
                                        <AreaChart
                                            data={series}
                                            margin={{ top: 8, right: 8, left: 0, bottom: 0 }}
                                        >
                                            <defs>
                                                <linearGradient id="heroArea" x1="0" y1="0" x2="0" y2="1">
                                                    <stop offset="5%" stopColor="var(--primary-02)" stopOpacity={0.22} />
                                                    <stop offset="95%" stopColor="var(--primary-02)" stopOpacity={0} />
                                                </linearGradient>
                                            </defs>
                                            <XAxis
                                                dataKey="date"
                                                axisLine={false}
                                                tickLine={false}
                                                tick={{ fontSize: "12px", fill: "var(--text-tertiary)" }}
                                                height={28}
                                                dy={8}
                                                minTickGap={16}
                                            />
                                            <YAxis
                                                axisLine={false}
                                                tickLine={false}
                                                tick={{ fontSize: "12px", fill: "var(--text-tertiary)" }}
                                                width={32}
                                                allowDecimals={false}
                                            />
                                            <CartesianGrid
                                                strokeDasharray="5 7"
                                                vertical={false}
                                                stroke="var(--stroke-stroke2)"
                                            />
                                            <Tooltip
                                                cursor={{ stroke: "var(--stroke-stroke2)" }}
                                                contentStyle={{
                                                    background: "var(--backgrounds-surface2)",
                                                    border: "1px solid var(--stroke-stroke2)",
                                                    borderRadius: "12px",
                                                    boxShadow: "var(--box-shadow-dropdown)",
                                                    fontSize: "12px",
                                                }}
                                                labelStyle={{ color: "var(--text-tertiary)", marginBottom: "2px" }}
                                            />
                                            <Area
                                                type="monotone"
                                                dataKey="calls"
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
                                            No activity yet — your call trend renders here once a campaign runs.
                                        </div>
                                    </div>
                                )}
                            </div>
                        </div>
                    </Card>

                    {/* Conversion funnel (was the isolated /analytics page) */}
                    <Card
                        title="Conversion funnel"
                        headContent={
                            <Link href={reportsHref} className="action mr-1">
                                Full report
                                <Icon name="arrow-up-right" />
                            </Link>
                        }
                    >
                        <div className="px-5 pb-5 pt-1 max-lg:px-3">
                            {reportLoading ? (
                                <div className="space-y-3 pt-2">
                                    {[...Array(5)].map((_, i) => (
                                        <div key={i} className="skeleton h-9 rounded-xl" style={{ width: `${100 - i * 14}%` }} />
                                    ))}
                                </div>
                            ) : funnel.length === 0 || funnelTop <= 1 ? (
                                <div className="state-sub py-6 text-center">
                                    Run a campaign — the funnel from upload to booked appears here.
                                </div>
                            ) : (
                                <div className="space-y-2.5 pt-1">
                                    {funnel.map((s) => {
                                        const pct = Math.max(4, Math.round((s.count / funnelTop) * 100));
                                        return (
                                            <div key={s.stage} className="flex items-center gap-3">
                                                <div className="w-20 shrink-0 text-caption text-t-secondary">
                                                    {FUNNEL_LABEL[s.stage] ?? s.stage}
                                                </div>
                                                <div className="relative flex-1 h-9 rounded-xl bg-b-surface1 dark:bg-shade-04/30 overflow-hidden">
                                                    <div
                                                        className="absolute inset-y-0 left-0 rounded-xl bg-primary-01/85 transition-all"
                                                        style={{ width: `${pct}%` }}
                                                    />
                                                    <div className="absolute inset-0 flex items-center justify-between px-3 text-caption">
                                                        <span className="font-medium text-t-primary tabular-nums">
                                                            {s.count.toLocaleString()}
                                                        </span>
                                                        {s.step_conv > 0 && s.stage !== "uploaded" && (
                                                            <span className="text-t-tertiary tabular-nums">
                                                                {s.step_conv}%
                                                            </span>
                                                        )}
                                                    </div>
                                                </div>
                                            </div>
                                        );
                                    })}
                                </div>
                            )}
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
                                        <th className="max-md:hidden">Campaign</th>
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
                                                    <Icon name="chat" className="fill-inherit" />
                                                </span>
                                                <div className="state-title">No calls yet</div>
                                                <div className="state-sub">
                                                    Run a campaign and your call results stream in here.
                                                </div>
                                            </div>
                                        </td>
                                    </TableRow>
                                ) : (
                                    calls.map((c) => (
                                        <TableRow key={c.id}>
                                            <td className="text-sub-title-1">{c.name}</td>
                                            <td className="text-t-secondary td-num max-lg:hidden">{c.phone}</td>
                                            <td className="text-t-secondary max-md:hidden">{c.campaign_name}</td>
                                            <td>
                                                <StatusBadge status={c.status} />
                                            </td>
                                            <td className="text-t-secondary whitespace-nowrap text-right">
                                                <span title={fmt(c.started_at)}>{fmtCompact(c.started_at)}</span>
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
                    {/* Hot leads — now uses the business-friendly LeadBadge */}
                    <Card
                        title="Hot leads"
                        headContent={
                            <Link href="/crm?status=hot" className="action mr-1">
                                View all
                                <Icon name="arrow-up-right" />
                            </Link>
                        }
                    >
                        <div className="px-3 pb-3">
                            {reportLoading ? (
                                <div className="space-y-2 p-2">
                                    {[...Array(4)].map((_, i) => (
                                        <div key={i} className="skeleton h-12 rounded-2xl" />
                                    ))}
                                </div>
                            ) : hotLeads.length === 0 ? (
                                <div className="state-block">
                                    <span className="state-glyph">
                                        <Icon name="profile" className="fill-inherit" />
                                    </span>
                                    <div className="state-title">No hot leads yet</div>
                                    <div className="state-sub">
                                        Leads that score 70+ on a call surface here automatically.
                                    </div>
                                </div>
                            ) : (
                                <div className="flex flex-col">
                                    {hotLeads.slice(0, 6).map((l) => (
                                        <Link
                                            key={l.call_id}
                                            href="/crm?status=hot"
                                            className="group flex items-center justify-between gap-3 px-2 py-3 rounded-2xl transition-colors hover:bg-b-surface1/60 dark:hover:bg-shade-04/30"
                                        >
                                            <div className="flex items-center gap-3 min-w-0">
                                                <span className="flex items-center justify-center size-9 shrink-0 rounded-full bg-b-surface1 text-sub-title-2 text-t-secondary transition-colors group-hover:text-t-primary dark:bg-shade-04/60">
                                                    {(l.name || "?").charAt(0).toUpperCase()}
                                                </span>
                                                <div className="min-w-0">
                                                    <div className="text-body-2 font-medium text-t-primary truncate">
                                                        {l.name}
                                                    </div>
                                                    <div className="text-caption text-t-tertiary tabular-nums">
                                                        {l.phone_masked}
                                                    </div>
                                                </div>
                                            </div>
                                            <LeadBadge
                                                lead={{ conversion_prob: l.conversion_prob, booked: l.booked }}
                                            />
                                        </Link>
                                    ))}
                                </div>
                            )}
                        </div>
                    </Card>

                    {/* Usage this month — links to the Billing hub */}
                    <Card
                        title="Usage this month"
                        headContent={
                            <Link href="/billing/overview" className="action mr-1">
                                Billing
                                <Icon name="arrow-up-right" />
                            </Link>
                        }
                    >
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
                                                    <div className="eyebrow mb-1">Minutes this month</div>
                                                    <div className="text-h5 text-t-primary tabular-nums">
                                                        {usage.month.minutes}
                                                        <span className="text-h6 text-t-tertiary">
                                                            {" "}/ {usage.limits.monthly_minutes_cap}
                                                        </span>
                                                    </div>
                                                </div>
                                                <div className="text-sub-title-2 text-t-secondary tabular-nums">
                                                    {(
                                                        (usage.month.minutes / usage.limits.monthly_minutes_cap) *
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
                                                            (usage.month.minutes / usage.limits.monthly_minutes_cap) * 100
                                                        )}%`,
                                                    }}
                                                />
                                            </div>
                                        </div>
                                    ) : (
                                        <div>
                                            <div className="eyebrow mb-1">Minutes this month</div>
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

function Kpi({
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
        <div className="flex flex-col gap-1 p-4 rounded-2xl bg-b-surface1/60 dark:bg-shade-04/30">
            <div className="eyebrow">{label}</div>
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
            {sub && <div className="text-caption text-t-tertiary">{sub}</div>}
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
