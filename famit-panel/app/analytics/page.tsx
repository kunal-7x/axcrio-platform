"use client";

import { Suspense, useEffect, useMemo, useState, useCallback } from "react";
import Layout from "@/components/Layout";
import Card from "@/components/Card";
import Icon from "@/components/Icon";
import Spinner from "@/components/Spinner";
import Table from "@/components/Table";
import TableRow from "@/components/TableRow";
import GlobalFilters, { useGlobalFilters } from "@/components/GlobalFilters";
import KpiCard from "@/components/KpiCard";
import { getCampaigns, type Campaign } from "@/lib/api";
import {
    getReport,
    exportReportSummary,
    exportReportLeads,
    type Report,
    type FunnelStage,
} from "@/lib/report";
import {
    ResponsiveContainer,
    PieChart,
    Pie,
    Cell,
    AreaChart,
    Area,
    XAxis,
    YAxis,
    CartesianGrid,
    Tooltip,
} from "recharts";

// Clamp a 0..100 percentage to [0,100] — guards against a backend that returns a
// step-conversion or share above 100 from a coarse fallback count.
const clampPct = (n: number) => Math.max(0, Math.min(100, Math.round(n)));

// A 0..1 conversion_prob -> a sane 0..100 % string-number. lib/report already
// normalizes hot-lead probs to 0..1, but this is a belt-and-suspenders clamp so the
// report can NEVER render "8000%" even if an un-normalized value slips through.
const convPct = (p: number) => clampPct((p > 1 ? p / 100 : p) * 100);

// Business-friendly funnel-stage labels (the ONE vocabulary — mirrors the Dashboard).
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

// Lead-temperature palette (brand → cool descent).
const TEMP_COLORS = [
    "var(--primary-01)",
    "var(--color-chart-yellow, #FFB13C)",
    "var(--primary-02)",
    "var(--text-tertiary)",
];

// 8-stage funnel ramp: top stages cool/blue, deepening toward warm/green as the
// lead progresses to converted (a visual "heating up" down the funnel).
const FUNNEL_COLORS: string[] = [
    "#7CB1FF", // uploaded  — light blue
    "#5A9CFF", // dialed
    "#2A85FF", // connected — brand
    "#7F5FFF", // interested — purple
    "#FF9D34", // warm      — amber
    "#FF6B3D", // hot       — orange-red
    "#22B07D", // booked    — green
    "#00A656", // converted — deep green
];

// Order matters: matches lib/report FUNNEL_ORDER.
const FUNNEL_STAGES = [
    "uploaded",
    "dialed",
    "connected",
    "interested",
    "warm",
    "hot",
    "booked",
    "converted",
];

// W15 / ROUND4 §B2 — "Reports": the DEEP drill-down the Dashboard links INTO,
// driven by the SHARED GlobalFilters range+campaign (?range/campaign/from/to). The
// previous build read getAnalytics() WITHOUT the range, so day-filters did nothing;
// it now reads getReport(range, {campaign}) (lib/report.ts forwards from/to) so
// today/7d/30d/this-month all visibly narrow the numbers. The funnel shows COUNTS
// (+ step-conversion %), not stretched ratios.
export default function AnalyticsPage() {
    return (
        <Suspense fallback={<Layout title="Reports"><div className="py-24"><Spinner /></div></Layout>}>
            <ReportsInner />
        </Suspense>
    );
}

function ReportsInner() {
    const { range, campaign: urlCampaign } = useGlobalFilters();
    const [report, setReport] = useState<Report | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState("");
    const [campaigns, setCampaigns] = useState<Campaign[]>([]);

    // The campaign filter is the shared URL param (set by GlobalFilters). Reports
    // reads the global one — it does not own a separate campaign select.
    const selectedCampaignId = urlCampaign || "";
    const selectedCampaignName = useMemo(
        () => campaigns.find((c) => c.id === selectedCampaignId)?.name ?? "All campaigns",
        [campaigns, selectedCampaignId]
    );

    // §B2 day-filter FIX — forward the active range (range.from/to) AND the campaign
    // to getReport. lib/report.ts forwards from/to to /analytics + /leads, so the
    // KPIs, funnel and temperature all move with today/7d/30d/this-month.
    const load = useCallback(() => {
        setLoading(true);
        setError("");
        getReport(range, selectedCampaignId ? { campaign: selectedCampaignId } : undefined)
            .then(setReport)
            .catch((e) => setError(e instanceof Error ? e.message : "Failed to load report"))
            .finally(() => setLoading(false));
    }, [range, selectedCampaignId]);

    useEffect(() => {
        getCampaigns()
            .then((r) => setCampaigns(r.campaigns))
            .catch(() => {});
    }, []);

    useEffect(() => { load(); }, [load]);

    // Auto-refresh every 30s — gate on tab visibility (don't drain in the background).
    useEffect(() => {
        const t = setInterval(() => {
            if (typeof document === "undefined" || document.visibilityState === "visible") load();
        }, 30000);
        const onVis = () => {
            if (document.visibilityState === "visible") load();
        };
        document.addEventListener("visibilitychange", onVis);
        return () => {
            clearInterval(t);
            document.removeEventListener("visibilitychange", onVis);
        };
    }, [load]);

    const totals = report?.totals;
    const funnel = report?.funnel ?? [];
    // Top-of-funnel count for the per-row bar width (numbers, not ratios).
    const funnelTop = funnel[0]?.count || 1;
    const hasFunnel = funnel.some((f) => f.count > 0);

    // ── Lead-temperature donut (hot/warm/cold/dead from by_status) ──
    const byStatus = report?.by_status;
    const pieData = useMemo(() => {
        if (!byStatus) return [];
        return [
            { name: "Hot", value: byStatus.hot ?? 0 },
            { name: "Warm", value: byStatus.warm ?? 0 },
            { name: "Cold", value: byStatus.cold ?? 0 },
            { name: "Dead", value: byStatus.dead ?? 0 },
        ].filter((d) => d.value > 0);
    }, [byStatus]);
    const pieTotal = useMemo(() => pieData.reduce((s, d) => s + d.value, 0), [pieData]);

    // ── Call-volume trend (the real /stats series via report.timeline) ──
    const series = report?.timeline ?? [];
    const hasSeries = series.some((p) => (p.calls ?? 0) > 0);

    const kpis = totals
        ? [
              { label: "Total calls", value: totals.calls, sub: "in range" },
              { label: "Connected", value: totals.connected, sub: `${totals.connect_rate}% connect rate` },
              { label: "Interested", value: totals.interested, sub: "showed intent" },
              { label: "Booked", value: totals.booked, sub: `${totals.conversion_rate}% of calls` },
              { label: "Callbacks", value: totals.callbacks, sub: "scheduled" },
              { label: "Hot leads", value: totals.hot, sub: "ready to convert" },
          ]
        : [];

    // ── Varied analytics derived metrics (NOT bars) ──
    // Pull the biggest single-step drop-off so the founder sees WHERE leads leak.
    const biggestDrop = useMemo(() => {
        let worst: { from: string; to: string; lost: number; rate: number } | null = null;
        for (let i = 1; i < funnel.length; i++) {
            const prev = funnel[i - 1];
            const cur = funnel[i];
            if (prev.count <= 0) continue;
            const lost = prev.count - cur.count;
            const rate = Math.round((lost / prev.count) * 100);
            if (lost > 0 && (!worst || lost > worst.lost)) {
                worst = {
                    from: FUNNEL_LABEL[prev.stage] ?? prev.stage,
                    to: FUNNEL_LABEL[cur.stage] ?? cur.stage,
                    lost,
                    rate,
                };
            }
        }
        return worst;
    }, [funnel]);

    // End-to-end yield: converted / uploaded (the one number that matters most).
    const overallYield = useMemo(() => {
        const top = funnel[0]?.count ?? 0;
        const conv = funnel.find((f) => f.stage === "converted")?.count ?? 0;
        return top > 0 ? Math.round((conv / top) * 1000) / 10 : 0;
    }, [funnel]);

    // Hot-lead share of all scored leads (engagement intensity).
    const hotShare = useMemo(() => {
        const tot = pieTotal || 0;
        return tot > 0 ? Math.round(((byStatus?.hot ?? 0) / tot) * 100) : 0;
    }, [byStatus, pieTotal]);

    // Avg talk time formatted mm:ss (real field; 0 → em-dash in render).
    const talkTime = totals?.avg_talk_time_s ?? 0;
    const talkFmt =
        talkTime > 0
            ? `${Math.floor(talkTime / 60)}:${String(Math.round(talkTime % 60)).padStart(2, "0")}`
            : "—";

    // Real call-volume series for the inline sparklines on the metric cards.
    const volSpark = useMemo(() => series.map((p) => p.calls ?? 0), [series]);

    const chartTooltip = {
        contentStyle: {
            background: "var(--backgrounds-surface2)",
            border: "1px solid var(--stroke-stroke2)",
            borderRadius: "12px",
            fontSize: "12px",
        },
        labelStyle: { color: "var(--text-tertiary)", marginBottom: "2px" },
    };

    // ── Report DOWNLOAD (CSV / Excel) — client-side blob, no backend route ──
    const canExport = !!report && !loading;
    const onExport = (kind: "summary" | "leads", excel: boolean) => {
        if (!report) return;
        if (kind === "summary") exportReportSummary(report, excel);
        else exportReportLeads(report, excel);
    };

    return (
        <Layout title="Reports">
            {error && (
                <div className="mb-4 flex items-center gap-3 p-4 rounded-3xl bg-b-surface2 border border-primary-03/40 text-body-2 text-t-secondary">
                    <Icon className="shrink-0 fill-primary-03" name="info" />
                    <span className="text-t-primary">{error}</span>
                </div>
            )}

            {loading && !report ? (
                <div className="py-24"><Spinner /></div>
            ) : (
                <div className="flex flex-col gap-3">
                    {/* KPI strip — shared GlobalFilters bar + the download menu */}
                    <Card
                        title="Overview"
                        headContent={
                            <div className="flex flex-wrap items-center gap-2">
                                <GlobalFilters show={{ range: true, campaign: true, status: false }} />
                                <DownloadMenu disabled={!canExport} onExport={onExport} />
                            </div>
                        }
                    >
                        <div className="flex flex-wrap px-5 pb-2 max-lg:px-3">
                            {kpis.map((k, i) => (
                                <div
                                    key={k.label}
                                    className={`flex-1 min-w-[33%] md:min-w-0 py-2 ${i > 0 ? "md:pl-6 md:border-l border-s-subtle" : ""}`}
                                >
                                    <div className="text-caption text-t-tertiary">{k.label}</div>
                                    <div className="mt-1 text-h4 text-t-primary tabular-nums">
                                        {k.value.toLocaleString()}
                                    </div>
                                    <div className="mt-1 text-caption text-t-secondary">{k.sub}</div>
                                </div>
                            ))}
                        </div>
                    </Card>

                    {/* Conversion funnel (left) + temperature donut (right) */}
                    <div className="grid grid-cols-3 gap-3 max-lg:grid-cols-1">
                        <div className="col-span-2 max-lg:col-span-1">
                            <Card
                                title="Conversion funnel"
                                headContent={
                                    <span className="mr-3 text-caption text-t-tertiary">{selectedCampaignName}</span>
                                }
                            >
                                {/* REAL top-to-bottom funnel DIAGRAM (ROUND5 §B):
                                    stacked trapezoids that narrow at each level, top
                                    (uploaded) widest → bottom (converted) narrowest.
                                    HOVER any band → the absolute COUNT + step-conv %.
                                    Custom SVG (no stretched-ratio FunnelChart shape). */}
                                <div className="px-5 pb-5 pt-1 max-lg:px-3">
                                    {!hasFunnel ? (
                                        <div className="flex flex-col items-center text-center py-12 px-5">
                                            <div className="flex justify-center items-center size-16 mb-4 rounded-full bg-b-surface1">
                                                <Icon className="fill-t-secondary" name="chart" />
                                            </div>
                                            <div className="text-sub-title-1 text-t-primary">No funnel data yet</div>
                                            <div className="mt-1 text-body-2 text-t-secondary max-w-80">
                                                Once leads are dialed in this range, your end-to-end conversion funnel appears here.
                                            </div>
                                        </div>
                                    ) : (
                                        <FunnelDiagram funnel={funnel} top={funnelTop} />
                                    )}
                                </div>
                            </Card>
                        </div>

                        {/* Lead-temperature donut with center total */}
                        <Card title="Lead temperature">
                            <div className="px-5 pb-5 pt-1 max-lg:px-3">
                                {pieData.length > 0 ? (
                                    <>
                                        <div className="relative h-52">
                                            <ResponsiveContainer width="100%" height="100%">
                                                <PieChart>
                                                    <Pie
                                                        data={pieData}
                                                        dataKey="value"
                                                        nameKey="name"
                                                        innerRadius="62%"
                                                        outerRadius="92%"
                                                        paddingAngle={2}
                                                        stroke="none"
                                                    >
                                                        {pieData.map((_, i) => (
                                                            <Cell key={i} fill={TEMP_COLORS[i % TEMP_COLORS.length]} />
                                                        ))}
                                                    </Pie>
                                                    <Tooltip {...chartTooltip} />
                                                </PieChart>
                                            </ResponsiveContainer>
                                            <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
                                                <div className="text-h4 text-t-primary tabular-nums">
                                                    {pieTotal.toLocaleString()}
                                                </div>
                                                <div className="text-caption text-t-tertiary">leads</div>
                                            </div>
                                        </div>
                                        <div className="mt-3 grid grid-cols-2 gap-2">
                                            {pieData.map((d, i) => (
                                                <div key={d.name} className="flex items-center gap-2 text-caption">
                                                    <span
                                                        className="size-2.5 rounded-full shrink-0"
                                                        style={{ background: TEMP_COLORS[i % TEMP_COLORS.length] }}
                                                    />
                                                    <span className="text-t-secondary">{d.name}</span>
                                                    <span className="ml-auto text-t-primary tabular-nums">
                                                        {d.value.toLocaleString()}
                                                    </span>
                                                </div>
                                            ))}
                                        </div>
                                    </>
                                ) : (
                                    <div className="flex flex-col items-center text-center py-12">
                                        <div className="flex justify-center items-center size-14 mb-3 rounded-full bg-b-surface1">
                                            <Icon className="fill-t-secondary" name="chart" />
                                        </div>
                                        <div className="text-body-2 text-t-secondary max-w-60">
                                            Lead temperature appears once calls are scored.
                                        </div>
                                    </div>
                                )}
                            </div>
                        </Card>
                    </div>

                    {/* Varied analytics cards (NOT bars) — premium metric tiles with
                        real meters / sparklines / drop-off insight. */}
                    <div className="grid grid-cols-4 gap-3 max-lg:grid-cols-2 max-sm:grid-cols-1">
                        <KpiCard
                            label="End-to-end yield"
                            value={`${overallYield}%`}
                            icon="chart"
                            tone="success"
                            sub="converted ÷ uploaded"
                            meter={overallYield / 100}
                        />
                        <KpiCard
                            label="Connect rate"
                            value={`${totals?.connect_rate ?? 0}%`}
                            icon="mobile"
                            tone="info"
                            sub={`${(totals?.connected ?? 0).toLocaleString()} connected`}
                            meter={(totals?.connect_rate ?? 0) / 100}
                            spark={volSpark.length > 1 ? volSpark : undefined}
                        />
                        <KpiCard
                            label="Hot-lead share"
                            value={`${hotShare}%`}
                            icon="profile"
                            tone="danger"
                            sub={`${(byStatus?.hot ?? 0).toLocaleString()} hot leads`}
                            meter={hotShare / 100}
                        />
                        {biggestDrop ? (
                            <KpiCard
                                label="Biggest drop-off"
                                value={`-${biggestDrop.lost.toLocaleString()}`}
                                icon="arrow"
                                tone="warning"
                                sub={`${biggestDrop.from} → ${biggestDrop.to} (${biggestDrop.rate}% lost)`}
                                meter={biggestDrop.rate / 100}
                            />
                        ) : (
                            <KpiCard
                                label="Avg talk time"
                                value={talkFmt}
                                icon="clock"
                                tone="neutral"
                                sub="per connected call"
                            />
                        )}
                    </div>

                    {/* Call-volume trend over the range */}
                    <Card title="Call volume">
                        <div className="px-3 pb-4 pt-2 h-64">
                            {hasSeries ? (
                                <ResponsiveContainer width="100%" height="100%">
                                    <AreaChart data={series} margin={{ top: 8, right: 12, left: -16, bottom: 0 }}>
                                        <defs>
                                            <linearGradient id="repVol" x1="0" y1="0" x2="0" y2="1">
                                                <stop offset="0%" stopColor="var(--primary-01)" stopOpacity={0.35} />
                                                <stop offset="100%" stopColor="var(--primary-01)" stopOpacity={0} />
                                            </linearGradient>
                                        </defs>
                                        <CartesianGrid stroke="var(--stroke-stroke2)" strokeOpacity={0.4} vertical={false} />
                                        <XAxis
                                            dataKey="date"
                                            tick={{ fill: "var(--text-tertiary)", fontSize: 11 }}
                                            tickLine={false}
                                            axisLine={false}
                                        />
                                        <YAxis
                                            tick={{ fill: "var(--text-tertiary)", fontSize: 11 }}
                                            tickLine={false}
                                            axisLine={false}
                                            allowDecimals={false}
                                            width={36}
                                        />
                                        <Tooltip {...chartTooltip} />
                                        <Area
                                            type="monotone"
                                            dataKey="calls"
                                            stroke="var(--primary-01)"
                                            strokeWidth={2}
                                            fill="url(#repVol)"
                                            name="Calls"
                                        />
                                    </AreaChart>
                                </ResponsiveContainer>
                            ) : (
                                <div className="flex h-full flex-col items-center justify-center text-center">
                                    <div className="text-body-2 text-t-secondary max-w-72">
                                        Call volume over time appears here once calls land in this range.
                                    </div>
                                </div>
                            )}
                        </div>
                    </Card>

                    {/* Funnel details (left) + Hot leads (right) — SIDE-BY-SIDE on
                        desktop (was stacked with a big empty gap), stacking only on
                        small screens. Each table is `table-fixed` with explicit per-
                        column widths so the numeric columns sit in tidy aligned
                        columns instead of being stretched to the far right of a wide
                        auto-width table. */}
                    {(hasFunnel || (report?.hot_leads?.length ?? 0) > 0) && (
                        <div className="grid grid-cols-2 gap-3 max-lg:grid-cols-1 items-start">
                            {hasFunnel && (
                                <Card title="Funnel details">
                                    <div className="p-1 pt-3 max-lg:px-0 [&_table]:table-fixed">
                                        <Table
                                            cellsThead={
                                                <>
                                                    <th style={{ width: "40%" }}>Stage</th>
                                                    <th className="text-right" style={{ width: "20%" }}>Count</th>
                                                    <th className="text-right" style={{ width: "20%" }}>Step conv.</th>
                                                    <th className="text-right" style={{ width: "20%" }}>% of top</th>
                                                </>
                                            }
                                        >
                                            {funnel.map((row, i) => (
                                                <TableRow key={i}>
                                                    <td className="font-medium text-t-primary capitalize">
                                                        {FUNNEL_LABEL[row.stage] ?? row.stage.replace(/_/g, " ")}
                                                    </td>
                                                    <td className="text-t-primary tabular-nums text-right">
                                                        {row.count.toLocaleString()}
                                                    </td>
                                                    <td className="text-t-secondary tabular-nums text-right">
                                                        {i === 0 || row.stage === "uploaded" ? "—" : `${clampPct(row.step_conv)}%`}
                                                    </td>
                                                    <td className="text-t-secondary tabular-nums text-right">
                                                        {clampPct(row.pct_of_top)}%
                                                    </td>
                                                </TableRow>
                                            ))}
                                        </Table>
                                    </div>
                                </Card>
                            )}

                            {(report?.hot_leads?.length ?? 0) > 0 && (
                                <Card
                                    title="Hot leads"
                                    headContent={
                                        <span className="mr-3 text-caption text-t-tertiary">Top {report!.hot_leads.length}</span>
                                    }
                                >
                                    <div className="p-1 pt-3 max-lg:px-0 [&_table]:table-fixed">
                                        <Table
                                            cellsThead={
                                                <>
                                                    <th style={{ width: "45%" }}>Name</th>
                                                    <th style={{ width: "30%" }}>Phone</th>
                                                    <th className="text-right" style={{ width: "25%" }}>Conversion prob.</th>
                                                </>
                                            }
                                        >
                                            {report!.hot_leads.map((l, i) => (
                                                <TableRow key={l.call_id || i}>
                                                    <td className="font-medium text-t-primary truncate" title={l.name || ""}>{l.name || "—"}</td>
                                                    <td className="text-t-secondary tabular-nums truncate">{l.phone_masked || l.phone || "—"}</td>
                                                    <td className="text-t-primary tabular-nums text-right">
                                                        {l.conversion_prob != null ? `${convPct(l.conversion_prob)}%` : "—"}
                                                    </td>
                                                </TableRow>
                                            ))}
                                        </Table>
                                    </div>
                                </Card>
                            )}
                        </div>
                    )}
                </div>
            )}
        </Layout>
    );
}

// ── Real top-to-bottom funnel diagram ───────────────────────────────────────
// A clean custom SVG: each stage is a trapezoid whose top edge = the previous
// stage's bottom width and whose bottom edge scales with this stage's count, so
// the shape NARROWS monotonically from uploaded (full width) to converted. Each
// band carries its stage label + COUNT inline; HOVERING a band raises a tooltip
// with the absolute number + step-conversion %. SVG so the narrowing geometry is
// exact and the hover hit-area is the whole trapezoid.
function FunnelDiagram({ funnel, top }: { funnel: FunnelStage[]; top: number }) {
    const [hover, setHover] = useState<number | null>(null);

    // Order the stages canonically; missing stages render as 0-width slivers.
    const byStage = new Map(funnel.map((f) => [f.stage, f]));
    const stages = FUNNEL_STAGES.map(
        (s) => byStage.get(s) ?? { stage: s, count: 0, pct_of_top: 0, step_conv: 0 },
    ).map((s, i) => ({ ...s, color: FUNNEL_COLORS[i % FUNNEL_COLORS.length] }));

    const W = 100; // viewBox width units
    const rowH = 40; // px per band
    const gap = 6;
    const H = stages.length * rowH + (stages.length - 1) * gap;
    const minW = 12; // floor width % so a tiny/zero stage is still a visible sliver

    // Width (in viewBox units) for a given count, floored so labels stay readable.
    const widthFor = (count: number) =>
        Math.max(minW, (count / (top || 1)) * W);

    return (
        <div className="relative pt-1">
            <svg
                viewBox={`0 0 ${W} ${H}`}
                preserveAspectRatio="none"
                className="w-full"
                style={{ height: H }}
            >
                {stages.map((s, i) => {
                    const wTop = i === 0 ? W : widthFor(stages[i - 1].count);
                    const wBot = widthFor(s.count);
                    const y = i * (rowH + gap);
                    const xTopL = (W - wTop) / 2;
                    const xTopR = (W + wTop) / 2;
                    const xBotL = (W - wBot) / 2;
                    const xBotR = (W + wBot) / 2;
                    const dim = hover != null && hover !== i;
                    return (
                        <polygon
                            key={s.stage}
                            points={`${xTopL},${y} ${xTopR},${y} ${xBotR},${y + rowH} ${xBotL},${y + rowH}`}
                            fill={s.color}
                            opacity={dim ? 0.35 : 1}
                            style={{ transition: "opacity .15s", cursor: "pointer" }}
                            onMouseEnter={() => setHover(i)}
                            onMouseLeave={() => setHover(null)}
                        />
                    );
                })}
            </svg>

            {/* Overlay labels (HTML so text never skews with preserveAspectRatio). */}
            <div className="pointer-events-none absolute inset-0 flex flex-col">
                {stages.map((s, i) => (
                    <div
                        key={s.stage}
                        className="flex items-center justify-between px-4 text-caption"
                        style={{ height: rowH, marginTop: i === 0 ? 4 : gap }}
                    >
                        <span className="font-medium text-white/95 drop-shadow-sm">
                            {FUNNEL_LABEL[s.stage] ?? s.stage}
                        </span>
                        <span className="font-semibold text-white tabular-nums drop-shadow-sm">
                            {s.count.toLocaleString()}
                        </span>
                    </div>
                ))}
            </div>

            {/* Hover tooltip — the ABSOLUTE number + step-conversion, not a ratio. */}
            {hover != null && (
                <div
                    className="pointer-events-none absolute left-1/2 -translate-x-1/2 z-20 px-3 py-2 rounded-xl bg-b-surface2 border border-s-stroke2 shadow-depth text-caption whitespace-nowrap"
                    style={{ top: hover * (rowH + gap) + rowH + 8 }}
                >
                    <div className="text-t-primary font-medium">
                        {FUNNEL_LABEL[stages[hover].stage] ?? stages[hover].stage}
                    </div>
                    <div className="mt-0.5 text-t-secondary tabular-nums">
                        {stages[hover].count.toLocaleString()} leads
                        {hover > 0 && stages[hover].step_conv > 0 && (
                            <span className="text-t-tertiary">
                                {" · "}
                                {stages[hover].step_conv}% from {FUNNEL_LABEL[stages[hover - 1].stage]}
                            </span>
                        )}
                    </div>
                    <div className="mt-0.5 text-t-tertiary tabular-nums">
                        {stages[hover].pct_of_top}% of top
                    </div>
                </div>
            )}
        </div>
    );
}

// ── Download menu — CSV / Excel for the report + the leads list ──
// Plain Core_2-styled dropdown (no extra dependency). Client-side blob export.
function DownloadMenu({
    disabled,
    onExport,
}: {
    disabled: boolean;
    onExport: (kind: "summary" | "leads", excel: boolean) => void;
}) {
    const [open, setOpen] = useState(false);

    // Close on outside click / Escape.
    useEffect(() => {
        if (!open) return;
        const onDoc = () => setOpen(false);
        const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
        document.addEventListener("click", onDoc);
        document.addEventListener("keydown", onKey);
        return () => {
            document.removeEventListener("click", onDoc);
            document.removeEventListener("keydown", onKey);
        };
    }, [open]);

    const pick = (kind: "summary" | "leads", excel: boolean) => {
        onExport(kind, excel);
        setOpen(false);
    };

    return (
        <div className="relative" onClick={(e) => e.stopPropagation()}>
            <button
                type="button"
                disabled={disabled}
                onClick={() => setOpen((o) => !o)}
                className="flex items-center gap-2 h-10 px-4 rounded-3xl border border-s-stroke2 text-button text-t-primary transition-colors hover:bg-b-surface1 disabled:opacity-40 disabled:cursor-not-allowed"
            >
                Download
                <Icon className="size-4 fill-t-secondary" name="arrow-up-right" />
            </button>
            {open && !disabled && (
                <div className="absolute right-0 z-20 mt-2 w-60 p-2 rounded-2xl bg-b-surface2 border border-s-subtle shadow-depth">
                    <div className="px-2 pt-1 pb-1.5 text-caption text-t-tertiary">Summary report</div>
                    <MenuItem label="Download CSV" onClick={() => pick("summary", false)} />
                    <MenuItem label="Download for Excel" onClick={() => pick("summary", true)} />
                    <div className="my-1.5 border-t border-s-subtle" />
                    <div className="px-2 pt-1 pb-1.5 text-caption text-t-tertiary">Leads list</div>
                    <MenuItem label="Download CSV" onClick={() => pick("leads", false)} />
                    <MenuItem label="Download for Excel" onClick={() => pick("leads", true)} />
                </div>
            )}
        </div>
    );
}

function MenuItem({ label, onClick }: { label: string; onClick: () => void }) {
    return (
        <button
            type="button"
            onClick={onClick}
            className="flex w-full items-center gap-2 px-2 py-2 rounded-xl text-left text-body-2 text-t-primary transition-colors hover:bg-b-surface1"
        >
            {label}
        </button>
    );
}
