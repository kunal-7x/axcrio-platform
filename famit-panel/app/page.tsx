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
import Icon from "@/components/Icon";
import KpiCard from "@/components/KpiCard";
import Sparkline from "@/components/Sparkline";
import GlobalFilters, { useGlobalFilters } from "@/components/GlobalFilters";
import { StatusBadge, LeadBadge } from "@/lib/badges";
import Badge from "@/components/Badge";
import { useStats, useCalls } from "@/lib/queries";
import { getReport, type Report } from "@/lib/report";
import { getUsage, type CallLog, type UsageData } from "@/lib/api";
import { CenterDonut, RadialGauge, CallsHeatmap } from "./_dashboard-charts";
import {
    ResponsiveContainer,
    AreaChart,
    Area,
    RadialBarChart,
    RadialBar,
    PolarAngleAxis,
    LineChart,
    Line,
    Legend,
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

// Parse a potentially timezone-naive backend string as UTC (same logic as
// crm/_ui.tsx toUTC — keeps dashboard timestamps consistent with the CRM).
function parseUTC(dateStr: string): Date {
    if (!dateStr) return new Date(NaN);
    if (/Z$|[+-]\d{2}:\d{2}$/.test(dateStr.trim())) return new Date(dateStr);
    if (/[+-]\d{4}$/.test(dateStr.trim())) return new Date(dateStr);
    return new Date(dateStr.trim() + "Z");
}

// Compact "x ago / time" for the recent-calls list — calmer than a full
// locale string, keeps rows scannable. Falls back to short date for old dates.
function fmtCompact(dateStr: string) {
    if (!dateStr) return "—";
    const d = parseUTC(dateStr);
    if (isNaN(d.getTime())) return dateStr;
    const diff = Date.now() - d.getTime();
    const min = Math.floor(diff / 60000);
    if (min < 1) return "just now";
    if (min < 60) return `${min}m ago`;
    const hr = Math.floor(min / 60);
    if (hr < 24) return `${hr}h ago`;
    const day = Math.floor(hr / 24);
    if (day < 7) return `${day}d ago`;
    return d.toLocaleDateString("en-IN", { timeZone: "Asia/Kolkata", month: "short", day: "numeric" });
}

// Trim leading/trailing zeros from a per-hour series so a sparkline shows the
// active window (keeps a crest legible). Guarantees ≥2 points so the spark draws.
function trimSeries(arr: number[]): number[] {
    let start = arr.findIndex((n) => n > 0);
    let end = arr.length - 1;
    while (end > 0 && arr[end] === 0) end--;
    if (start < 0) return [0, 0];
    if (start > 0) start -= 1; // one quiet hour of lead-in for a nicer curve
    const slice = arr.slice(start, end + 1);
    return slice.length >= 2 ? slice : [...slice, ...slice];
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

    // Recent calls — fetch only 8 initially; "Show more" loads the next page.
    const [callsPage, setCallsPage] = useState(8);
    const callsQuery = useCalls({ limit: callsPage, order: "desc", slim: true });
    const calls: CallLog[] = useMemo(
        () => callsQuery.data?.calls ?? [],
        [callsQuery.data]
    );
    const callsTotal = callsQuery.data?.total ?? 0;
    const callsLoading = callsQuery.isLoading && calls.length === 0;
    const hasMoreCalls = calls.length < callsTotal;

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

    // ── Outcome distribution (radial) — connected→interested→booked progression
    // as concentric arcs, each measured against total calls. Real data; a varied
    // chart type (radial, not bars) that reads as a premium gauge stack.
    const outcomeRadial = useMemo(() => {
        if (!totals) return [];
        // Ordered inner→outer; each arc's domain is total calls so the fill % is
        // honestly "share of all calls reaching this outcome".
        return [
            { name: "Booked", value: totals.booked ?? 0, fill: "var(--primary-01)" },
            { name: "Interested", value: totals.interested ?? 0, fill: "var(--chart-green)" },
            { name: "Connected", value: totals.connected ?? 0, fill: "var(--primary-02)" },
        ];
    }, [totals]);
    const outcomeTotal = totals?.calls ?? 0;
    const outcomeHasData = useMemo(
        () => outcomeRadial.some((d) => d.value > 0),
        [outcomeRadial]
    );

    // ── Lead-temperature donut — hot/warm/cold/dead split. PREFERS the richer
    // report.temperature_distribution (count + share + day-over-day delta) the W14
    // seam may emit; falls back to the coarse by_status counts when it's absent.
    // On-brand slice colors (blue→amber→green→neutral). Lights up either way.
    const byStatus = report?.by_status;
    const tempDist = report?.temperature_distribution;
    const TEMP_META: Record<string, { name: string; color: string }> = {
        hot: { name: "Hot", color: "var(--primary-01)" },
        warm: { name: "Warm", color: "var(--primary-05)" },
        cold: { name: "Cold", color: "var(--primary-02)" },
        dead: { name: "Dead", color: "var(--text-tertiary)" },
    };
    const tempDonut = useMemo(() => {
        // Forward-compat path: the backend-populated distribution wins.
        if (tempDist && tempDist.length) {
            return tempDist
                .map((b) => ({
                    name: TEMP_META[b.tier]?.name ?? b.tier,
                    value: b.count ?? 0,
                    color: TEMP_META[b.tier]?.color ?? "var(--text-tertiary)",
                    delta: b.delta,
                }))
                .filter((d) => d.value > 0);
        }
        if (!byStatus) return [];
        return (["hot", "warm", "cold", "dead"] as const)
            .map((tier) => ({
                name: TEMP_META[tier].name,
                value: byStatus[tier] ?? 0,
                color: TEMP_META[tier].color,
                delta: undefined as number | undefined,
            }))
            .filter((d) => d.value > 0);
    }, [tempDist, byStatus]);
    const tempTotal = useMemo(
        () => tempDonut.reduce((s, d) => s + d.value, 0),
        [tempDonut]
    );
    // Single dominant temperature (largest slice) — used by the AI recommendation.
    const tempLeader = useMemo(
        () => [...tempDonut].sort((a, b) => b.value - a.value)[0],
        [tempDonut]
    );

    // ── Calls-by-hour heatmap (IST) — 24 buckets from the loaded recent-calls
    // window. Real data; shows when the agent is busiest. Fills the right column.
    const hourBuckets = useMemo(() => {
        const b = new Array(24).fill(0);
        for (const c of calls) {
            const d = parseUTC(c.started_at);
            if (isNaN(d.getTime())) continue;
            const hr = Number(
                new Intl.DateTimeFormat("en-GB", {
                    timeZone: "Asia/Kolkata",
                    hour: "2-digit",
                    hour12: false,
                }).format(d)
            );
            if (hr >= 0 && hr < 24) b[hr % 24] += 1;
        }
        return b;
    }, [calls]);
    const hourTotal = useMemo(() => hourBuckets.reduce((s, n) => s + n, 0), [hourBuckets]);

    // Per-KPI spark series from the real call-volume timeline (calls/day). Used as
    // a calm trend hint inside the hero KPI cards — never fabricated.
    const callsSpark = useMemo(() => series.map((p) => p.calls), [series]);

    // ── Top campaigns mini-leaderboard — derived from the recent-calls page,
    // grouped by campaign_name with a connect-rate (LIVE/connected statuses count
    // as connected). Honest: it reflects the loaded recent window, not all-time.
    const topCampaigns = useMemo(() => {
        // group by campaign; track total, connected, and a per-hour mini-series
        // (IST hour bucket) for the sparkline crest.
        const map = new Map<
            string,
            { total: number; connected: number; spark: number[] }
        >();
        for (const c of calls) {
            const key = c.campaign_name || "—";
            const e = map.get(key) ?? { total: 0, connected: 0, spark: new Array(24).fill(0) };
            e.total += 1;
            const d = parseUTC(c.started_at);
            if (!isNaN(d.getTime())) {
                const hr = Number(
                    new Intl.DateTimeFormat("en-GB", {
                        timeZone: "Asia/Kolkata",
                        hour: "2-digit",
                        hour12: false,
                    }).format(d)
                );
                if (hr >= 0 && hr < 24) e.spark[hr] += 1;
            }
            const st = (c.status ?? "").toLowerCase();
            if (
                st.includes("connect") ||
                st.includes("answer") ||
                st.includes("complete") ||
                st.includes("interest") ||
                st.includes("book")
            ) {
                e.connected += 1;
            }
            map.set(key, e);
        }
        return [...map.entries()]
            .map(([name, e]) => ({
                name,
                total: e.total,
                rate: e.total > 0 ? Math.round((e.connected / e.total) * 100) : 0,
                // trim leading/trailing empty hours so the spark crest is legible
                spark: trimSeries(e.spark),
            }))
            .sort((a, b) => b.total - a.total)
            .slice(0, 3);
    }, [calls]);
    const topCampaignsMax = topCampaigns[0]?.total || 1;

    // Has any timeline series got real connected/booked numbers (the W14 seam), or
    // only call volume? Drives whether the multi-series line shows those series.
    const timelineHasOutcomes = useMemo(
        () => series.some((p) => (p.connected ?? 0) > 0 || (p.booked ?? 0) > 0),
        [series]
    );

    // ── AI Recommendation (deterministic, REAL-data driven) ────────────────────
    // Not a fabricated LLM blurb — a rules engine over the live report that names
    // the single highest-leverage next action. Picks the most urgent signal:
    //  • hot leads waiting → chase them (highest revenue intent)
    //  • low connect rate → retune dialing window / retry
    //  • good connect but low booking → tighten the pitch / offer
    //  • healthy → keep volume up.
    // Returns null while loading so the card shows a calm skeleton.
    const aiRec = useMemo(() => {
        if (!totals) return null;
        const t = totals;
        const hotWaiting = hotLeads.length;
        // 1) Hot leads sitting unbooked = the sharpest knife.
        if (hotWaiting > 0 && t.booked < hotWaiting) {
            return {
                tone: "danger" as const,
                icon: "heart-fill",
                title: `Call your ${hotWaiting} hot lead${hotWaiting === 1 ? "" : "s"} now`,
                body: `${hotWaiting} lead${hotWaiting === 1 ? " is" : "s are"} scoring 70+ and not yet booked. They cool fast — a follow-up within the hour converts best.`,
                cta: { label: "Open hot leads", href: "/crm?status=hot" },
            };
        }
        // 2) Weak connect rate → the dialing window / retries need work.
        if (t.calls >= 10 && t.connect_rate < 45) {
            return {
                tone: "warning" as const,
                icon: "mobile",
                title: `Connect rate is ${t.connect_rate}% — lift it`,
                body: `Most dials aren't being answered. Shift calling into 11am–1pm / 5pm–7pm IST and enable a 2nd retry to recover unanswered numbers.`,
                cta: { label: "Tune campaign", href: "/campaigns" },
            };
        }
        // 3) Good connect but thin bookings → the pitch/offer is the bottleneck.
        if (t.connected >= 10 && t.conversion_rate < 12) {
            return {
                tone: "info" as const,
                icon: "chat",
                title: `Conversations land, bookings lag (${t.conversion_rate}%)`,
                body: `People answer but few book. Sharpen the offer and add a clear single ask in the script — ${t.interested} showed interest without booking.`,
                cta: { label: "Edit script", href: "/campaigns" },
            };
        }
        // 4) Healthy → keep the engine fed.
        if (t.calls > 0) {
            return {
                tone: "success" as const,
                icon: "check",
                title: "Pipeline looks healthy",
                body: `${t.connect_rate}% connect · ${t.conversion_rate}% booked. The system is converting — load more leads to scale revenue at this rate.`,
                cta: { label: "Run a campaign", href: "/run" },
            };
        }
        // 5) Cold start.
        return {
            tone: "info" as const,
            icon: "magic-pencil",
            title: "Start your first campaign",
            body: "Upload leads and launch a run — your AI caller will work the list and these insights light up with real results.",
            cta: { label: "Run a campaign", href: "/run" },
        };
    }, [totals, hotLeads]);

    // ── Two compact analytics tiles beside Recent Calls ────────────────────────
    // (a) Pipeline velocity = booked / connected (how well conversations close).
    // (b) Lead quality = (hot+warm) share of scored leads. Both REAL, range-aware.
    const pipelineVelocity = useMemo(() => {
        if (!totals || totals.connected <= 0) return null;
        return Math.round((totals.booked / totals.connected) * 100);
    }, [totals]);
    const leadQuality = useMemo(() => {
        if (tempTotal <= 0) return null;
        const hotWarm =
            tempDonut
                .filter((d) => d.name === "Hot" || d.name === "Warm")
                .reduce((s, d) => s + d.value, 0) ?? 0;
        return Math.round((hotWarm / tempTotal) * 100);
    }, [tempDonut, tempTotal]);

    const chartTooltip = {
        cursor: { fill: "var(--stroke-stroke2)", opacity: 0.25 },
        contentStyle: {
            background: "var(--backgrounds-surface2)",
            border: "1px solid var(--stroke-stroke2)",
            borderRadius: "12px",
            boxShadow: "var(--box-shadow-dropdown)",
            fontSize: "12px",
        },
        labelStyle: { color: "var(--text-tertiary)", marginBottom: "2px" },
    };

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
                    <div className="grid grid-cols-4 gap-3 max-2xl:grid-cols-4 max-lg:grid-cols-2 max-md:grid-cols-2">
                        <KpiCard
                            label="Total calls"
                            icon="chat"
                            tone="info"
                            value={reportLoading ? <SkVal /> : (totals?.calls ?? 0).toLocaleString()}
                            spark={callsSpark}
                            sub={
                                trendDelta != null ? (
                                    <>
                                        <span className={trendDelta >= 0 ? "text-primary-02" : "text-primary-03"}>
                                            {trendDelta >= 0 ? "▲" : "▼"} {Math.abs(trendDelta)}%
                                        </span>
                                        <span className="text-t-tertiary">vs prev day</span>
                                    </>
                                ) : undefined
                            }
                        />
                        <KpiCard
                            label="Connected"
                            icon="check"
                            tone="success"
                            value={reportLoading ? <SkVal /> : (totals?.connected ?? 0).toLocaleString()}
                            meter={totals ? totals.connect_rate / 100 : null}
                            sub={totals ? `${totals.connect_rate}% connect rate` : undefined}
                        />
                        <KpiCard
                            label="Booked"
                            icon="calendar"
                            tone="info"
                            value={reportLoading ? <SkVal /> : (totals?.booked ?? 0).toLocaleString()}
                            meter={totals ? totals.conversion_rate / 100 : null}
                            sub={totals ? `${totals.conversion_rate}% of calls` : undefined}
                        />
                        <KpiCard
                            label="Hot leads"
                            icon="heart-fill"
                            tone="danger"
                            value={reportLoading ? <SkVal /> : (totals?.hot ?? 0).toLocaleString()}
                            sub={
                                totals
                                    ? `${totals.warm} warm · ${totals.cold} cold`
                                    : undefined
                            }
                        />
                        <KpiCard
                            label="Interested"
                            tone="neutral"
                            value={reportLoading ? <SkVal /> : totals?.interested != null ? totals.interested.toLocaleString() : "—"}
                        />
                        <KpiCard
                            label="Callbacks"
                            tone="neutral"
                            value={reportLoading ? <SkVal /> : totals?.callbacks != null ? totals.callbacks.toLocaleString() : "—"}
                        />
                        <KpiCard
                            label="Avg talk time"
                            tone="neutral"
                            value={
                                reportLoading ? (
                                    <SkVal />
                                ) : totals?.avg_talk_time_s != null && totals.avg_talk_time_s > 0 ? (
                                    `${Math.floor(totals.avg_talk_time_s / 60)}m ${Math.round(totals.avg_talk_time_s % 60)}s`
                                ) : (
                                    "—"
                                )
                            }
                        />
                        <KpiCard
                            label="Connect rate"
                            tone="success"
                            value={
                                reportLoading ? (
                                    <SkVal />
                                ) : totals?.connect_rate != null ? (
                                    `${totals.connect_rate}%`
                                ) : (
                                    "—"
                                )
                            }
                            meter={totals?.connect_rate != null ? totals.connect_rate / 100 : null}
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

            {/* ── Trends line (full width): calls vs connected vs booked ── */}
            <div className="mb-3">
                <Card title="Trends">
                    <div className="px-5 pb-5 max-lg:px-3">
                        <div className="h-60 max-lg:h-48">
                            {reportLoading ? (
                                <div className="skeleton h-full w-full rounded-2xl" />
                            ) : series.length > 0 ? (
                                <ResponsiveContainer width="100%" height="100%">
                                    <LineChart data={series} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                                        <CartesianGrid strokeDasharray="5 7" vertical={false} stroke="var(--stroke-stroke2)" />
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
                                        <Tooltip {...chartTooltip} />
                                        <Legend
                                            iconType="plainline"
                                            wrapperStyle={{ fontSize: "12px", color: "var(--text-tertiary)" }}
                                        />
                                        <Line type="monotone" dataKey="calls" name="Calls" stroke="var(--primary-02)" strokeWidth={2.5} dot={false} />
                                        {timelineHasOutcomes && (
                                            <>
                                                <Line type="monotone" dataKey="connected" name="Connected" stroke="var(--color-chart-green)" strokeWidth={2.5} dot={false} />
                                                <Line type="monotone" dataKey="booked" name="Booked" stroke="var(--primary-01)" strokeWidth={2.5} dot={false} />
                                            </>
                                        )}
                                    </LineChart>
                                </ResponsiveContainer>
                            ) : (
                                <div className="flex h-full items-center justify-center">
                                    <div className="state-sub text-center">
                                        Calls, connected and booked trends render here once a campaign runs.
                                    </div>
                                </div>
                            )}
                        </div>
                        {!reportLoading && series.length > 0 && !timelineHasOutcomes && (
                            <div className="mt-2 text-caption text-t-tertiary">
                                Showing call volume. Per-day connected/booked series activate when the reporting stream is enabled on your box.
                            </div>
                        )}
                    </div>
                </Card>

            </div>

            {/* ── Insight row: outcome radial · temperature donut · activity heatmap.
                 Three varied chart types side-by-side; all REAL data. ── */}
            <div className="grid grid-cols-3 gap-3 mb-3 max-xl:grid-cols-2 max-md:grid-cols-1">
                {/* Outcome funnel as concentric radial arcs */}
                <Card title="Outcome breakdown">
                    <div className="px-5 pb-5 max-lg:px-3">
                        <div className="h-56 max-lg:h-48">
                            {reportLoading ? (
                                <div className="skeleton h-full w-full rounded-2xl" />
                            ) : outcomeHasData ? (
                                <div className="flex h-full items-center gap-3">
                                    <div className="relative h-full flex-1">
                                        <ResponsiveContainer width="100%" height="100%">
                                            <RadialBarChart
                                                innerRadius="38%"
                                                outerRadius="100%"
                                                data={outcomeRadial}
                                                startAngle={90}
                                                endAngle={-270}
                                                barSize={13}
                                            >
                                                <PolarAngleAxis
                                                    type="number"
                                                    domain={[0, outcomeTotal || 1]}
                                                    angleAxisId={0}
                                                    tick={false}
                                                />
                                                <RadialBar
                                                    background={{ fill: "var(--stroke-stroke2)" }}
                                                    dataKey="value"
                                                    cornerRadius={8}
                                                />
                                                <Tooltip {...chartTooltip} />
                                            </RadialBarChart>
                                        </ResponsiveContainer>
                                    </div>
                                    <div className="shrink-0 space-y-2.5 pr-1">
                                        {outcomeRadial.map((d) => (
                                            <div key={d.name} className="flex items-center gap-2">
                                                <span className="size-2.5 shrink-0 rounded-full" style={{ background: d.fill }} />
                                                <span className="text-caption text-t-secondary">{d.name}</span>
                                                <span className="text-caption text-t-primary tabular-nums font-medium">
                                                    {d.value.toLocaleString()}
                                                </span>
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            ) : (
                                <div className="flex h-full items-center justify-center">
                                    <div className="state-sub text-center">
                                        Outcome breakdown appears here once calls complete.
                                    </div>
                                </div>
                            )}
                        </div>
                    </div>
                </Card>

                {/* Lead-temperature donut with center total */}
                <Card title="Lead temperature">
                    <div className="px-5 pb-5 max-lg:px-3">
                        <div className="h-56 max-lg:h-48 flex items-center">
                            {reportLoading ? (
                                <div className="skeleton h-44 w-full rounded-2xl" />
                            ) : tempTotal > 0 ? (
                                <CenterDonut data={tempDonut} total={tempTotal} centerLabel="leads" />
                            ) : (
                                <div className="flex h-full w-full items-center justify-center">
                                    <div className="state-sub text-center">
                                        Hot / warm / cold / dead split appears here once leads are scored.
                                    </div>
                                </div>
                            )}
                        </div>
                    </div>
                </Card>

                {/* Activity-by-hour heatmap (IST) */}
                <Card title="Activity by hour">
                    <div className="px-5 pb-5 max-lg:px-3">
                        <div className="h-56 max-lg:h-48 flex flex-col justify-center">
                            {callsLoading ? (
                                <div className="skeleton h-32 w-full rounded-2xl" />
                            ) : hourTotal > 0 ? (
                                <>
                                    <CallsHeatmap buckets={hourBuckets} />
                                    <div className="mt-3 text-caption text-t-tertiary">
                                        {hourTotal.toLocaleString()} calls across the recent window, by IST hour.
                                    </div>
                                </>
                            ) : (
                                <div className="flex h-full items-center justify-center">
                                    <div className="state-sub text-center">
                                        Your busiest calling hours light up here once a campaign runs.
                                    </div>
                                </div>
                            )}
                        </div>
                    </div>
                </Card>
            </div>

            {/* ── Leaderboard row: compact top-campaigns (with sparkline) +
                 bookings/callbacks radial gauges. ── */}
            <div className="grid grid-cols-3 gap-3 mb-3 max-lg:grid-cols-1">
                {/* Top campaigns — single column, top-3, sparkline crest */}
                <Card
                    title="Top campaigns"
                    className="col-span-2 max-lg:col-span-1"
                    headContent={
                        <Link href="/campaigns" className="action mr-1">
                            All campaigns
                            <Icon name="arrow-up-right" />
                        </Link>
                    }
                >
                    <div className="px-5 pb-5 pt-1 max-lg:px-3">
                        {callsLoading ? (
                            <div className="space-y-3 pt-2">
                                {[...Array(3)].map((_, i) => (
                                    <div key={i} className="skeleton h-12 rounded-xl" />
                                ))}
                            </div>
                        ) : topCampaigns.length === 0 ? (
                            <div className="state-sub py-6 text-center">
                                Your busiest campaigns rank here once calls start flowing.
                            </div>
                        ) : (
                            <div className="space-y-2 pt-1">
                                {topCampaigns.map((c, i) => {
                                    const pct = Math.max(6, Math.round((c.total / topCampaignsMax) * 100));
                                    return (
                                        <div
                                            key={c.name}
                                            className="flex items-center gap-3 rounded-2xl p-2.5 transition-colors hover:bg-b-surface1/60 dark:hover:bg-shade-04/30"
                                        >
                                            <span className="flex items-center justify-center size-7 shrink-0 rounded-lg bg-b-surface1 text-caption font-semibold text-t-secondary tabular-nums dark:bg-shade-04/60">
                                                {i + 1}
                                            </span>
                                            <div className="min-w-0 flex-1">
                                                <div className="truncate text-body-2 font-medium text-t-primary" title={c.name}>
                                                    {c.name}
                                                </div>
                                                <div className="mt-1 h-1.5 rounded-full bg-b-surface1 dark:bg-shade-04/30 overflow-hidden">
                                                    <div
                                                        className="h-full rounded-full bg-primary-02/80 transition-all"
                                                        style={{ width: `${pct}%` }}
                                                    />
                                                </div>
                                            </div>
                                            <Sparkline
                                                data={c.spark}
                                                color="var(--primary-01)"
                                                width={72}
                                                height={28}
                                                className="shrink-0 max-sm:hidden"
                                            />
                                            <div className="shrink-0 text-right">
                                                <div className="text-sub-title-2 text-t-primary tabular-nums">
                                                    {c.total.toLocaleString()}
                                                </div>
                                                <div className="text-caption text-t-tertiary tabular-nums">
                                                    {c.rate}% conn.
                                                </div>
                                            </div>
                                        </div>
                                    );
                                })}
                            </div>
                        )}
                    </div>
                </Card>

                {/* Bookings & callbacks radial gauges */}
                <Card title="Bookings & callbacks">
                    <div className="px-5 pb-5 pt-1 max-lg:px-3">
                        {reportLoading ? (
                            <div className="grid grid-cols-2 gap-3">
                                <div className="skeleton h-32 rounded-2xl" />
                                <div className="skeleton h-32 rounded-2xl" />
                            </div>
                        ) : (
                            <div className="grid grid-cols-2 gap-3 max-sm:grid-cols-1">
                                <RadialGauge
                                    value={totals?.booked ?? 0}
                                    max={totals?.calls ?? 0}
                                    label="Booked"
                                    color="var(--primary-01)"
                                />
                                <RadialGauge
                                    value={totals?.callbacks ?? 0}
                                    max={totals?.calls ?? 0}
                                    label="Callbacks"
                                    color="var(--primary-05)"
                                />
                            </div>
                        )}
                        <div className="mt-3 text-caption text-t-tertiary">
                            Share of {(totals?.calls ?? 0).toLocaleString()} calls in range.
                        </div>
                    </div>
                </Card>
            </div>

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
                                        <th className="text-center max-sm:hidden">Score</th>
                                        <th className="text-right">Started</th>
                                    </>
                                }
                            >
                                {callsLoading ? (
                                    [...Array(5)].map((_, i) => (
                                        <TableRow key={i}>
                                            {[...Array(6)].map((__, j) => (
                                                <td key={j}>
                                                    <div className="skeleton h-4 w-20" />
                                                </td>
                                            ))}
                                        </TableRow>
                                    ))
                                ) : calls.length === 0 ? (
                                    <TableRow>
                                        <td colSpan={6}>
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
                                            <td className="text-center max-sm:hidden">
                                                {typeof c.interest === "number" ? (
                                                    <ScorePill score={c.interest} />
                                                ) : (
                                                    <span className="text-t-tertiary">—</span>
                                                )}
                                            </td>
                                            <td className="text-t-secondary whitespace-nowrap text-right">
                                                <span title={fmt(c.started_at)}>{fmtCompact(c.started_at)}</span>
                                            </td>
                                        </TableRow>
                                    ))
                                )}
                            </Table>
                            {!callsLoading && hasMoreCalls && (
                                <div className="flex justify-center py-3">
                                    <button
                                        type="button"
                                        className="action text-caption"
                                        onClick={() => setCallsPage((p) => p + 20)}
                                    >
                                        Show more
                                    </button>
                                </div>
                            )}
                        </div>
                    </Card>
                </div>

                {/* ── col-right: AI rec + analytics + hot leads + usage ── */}
                <div className="col-right">
                    {/* AI Recommendation — the single highest-leverage next action,
                        derived deterministically from the live report (REAL data). */}
                    <Card title="AI recommendation">
                        <div className="px-5 pb-5 pt-1 max-lg:px-3">
                            {reportLoading || !aiRec ? (
                                <div className="space-y-3 pt-1">
                                    <div className="skeleton h-10 w-10 rounded-2xl" />
                                    <div className="skeleton h-4 w-3/4 rounded-md" />
                                    <div className="skeleton h-12 w-full rounded-md" />
                                </div>
                            ) : (
                                <div className="flex flex-col gap-3 pt-1">
                                    <div className="flex items-start gap-3">
                                        <span className={`flex items-center justify-center size-10 shrink-0 rounded-2xl ${recToneBg(aiRec.tone)}`}>
                                            <Icon name={aiRec.icon} className={`size-5 ${recToneFill(aiRec.tone)}`} />
                                        </span>
                                        <div className="min-w-0">
                                            <div className="text-sub-title-1 text-t-primary leading-snug">
                                                {aiRec.title}
                                            </div>
                                        </div>
                                    </div>
                                    <p className="text-body-2 text-t-secondary leading-relaxed">
                                        {aiRec.body}
                                    </p>
                                    <Link href={aiRec.cta.href} className="action self-start">
                                        {aiRec.cta.label}
                                        <Icon name="arrow-up-right" />
                                    </Link>
                                </div>
                            )}
                        </div>
                    </Card>

                    {/* Two compact analytics tiles — pipeline velocity + lead quality.
                        Both REAL, range-aware; radial gauges (varied chart type). */}
                    <Card title="Pipeline analytics">
                        <div className="px-5 pb-5 pt-1 max-lg:px-3">
                            {reportLoading ? (
                                <div className="grid grid-cols-2 gap-3">
                                    <div className="skeleton h-32 rounded-2xl" />
                                    <div className="skeleton h-32 rounded-2xl" />
                                </div>
                            ) : (
                                <div className="grid grid-cols-2 gap-3 max-sm:grid-cols-1">
                                    {pipelineVelocity != null ? (
                                        <RadialGauge
                                            value={pipelineVelocity}
                                            max={100}
                                            label="Close rate"
                                            suffix={`${pipelineVelocity}%`}
                                            color="var(--primary-01)"
                                        />
                                    ) : (
                                        <AnalyticEmpty label="Close rate" />
                                    )}
                                    {leadQuality != null ? (
                                        <RadialGauge
                                            value={leadQuality}
                                            max={100}
                                            label="Lead quality"
                                            suffix={`${leadQuality}%`}
                                            color="var(--primary-05)"
                                        />
                                    ) : (
                                        <AnalyticEmpty label="Lead quality" />
                                    )}
                                </div>
                            )}
                            <div className="mt-3 text-caption text-t-tertiary">
                                Close rate = booked ÷ connected. Lead quality = hot + warm share of scored leads.
                            </div>
                        </div>
                    </Card>

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

// Skeleton placeholder for a KpiCard value while the report loads.
function SkVal() {
    return <span className="skeleton inline-block h-7 w-16 align-bottom rounded-md" />;
}

// Tone → soft icon-chip background for the AI recommendation card.
function recToneBg(tone: "danger" | "warning" | "info" | "success"): string {
    switch (tone) {
        case "danger":
            return "bg-primary-03/12";
        case "warning":
            return "bg-primary-05/12";
        case "success":
            return "bg-primary-02/12";
        default:
            return "bg-primary-01/12";
    }
}

// Tone → icon fill color for the AI recommendation card.
function recToneFill(tone: "danger" | "warning" | "info" | "success"): string {
    switch (tone) {
        case "danger":
            return "fill-primary-03";
        case "warning":
            return "fill-primary-05";
        case "success":
            return "fill-primary-02";
        default:
            return "fill-primary-01";
    }
}

// Empty state for a single analytics gauge (no data in range yet).
function AnalyticEmpty({ label }: { label: string }) {
    return (
        <div className="flex h-32 flex-col items-center justify-center gap-1 rounded-2xl bg-b-surface1/60 dark:bg-shade-04/30">
            <div className="text-h6 text-t-tertiary tabular-nums">—</div>
            <div className="text-caption text-t-tertiary">{label}</div>
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

// Ported from app/calls/page.tsx:765 — the interest/score pill (green 70+, amber
// 40+, neutral below). Kept identical so the Score reads the same across pages.
function ScorePill({ score }: { score: number }) {
    const variant = score >= 70 ? "success" : score >= 40 ? "warning" : "neutral";
    return (
        <Badge variant={variant} dot={score >= 70}>
            {score}
        </Badge>
    );
}
