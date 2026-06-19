"use client";

import { Suspense, useEffect, useMemo, useState, useCallback } from "react";
import Layout from "@/components/Layout";
import Card from "@/components/Card";
import Icon from "@/components/Icon";
import Spinner from "@/components/Spinner";
import Table from "@/components/Table";
import TableRow from "@/components/TableRow";
import GlobalFilters, { useGlobalFilters } from "@/components/GlobalFilters";
import { getCampaigns, type Campaign } from "@/lib/api";
import {
    getReport,
    exportReportSummary,
    exportReportLeads,
    type Report,
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
                                {/* Compact, capped-height funnel ROWS: each shows the
                                    COUNT (number) + step-conversion %, bar width is the
                                    share of the top stage. Ported from the Dashboard
                                    (un-stretched; no FunnelChart ratio shape). */}
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

                    {/* Funnel details table — COUNTS + step-conversion + share of top */}
                    {hasFunnel && (
                        <Card title="Funnel details">
                            <div className="p-1 pt-3 max-lg:px-0">
                                <Table
                                    cellsThead={
                                        <>
                                            <th>Stage</th>
                                            <th className="text-right">Count</th>
                                            <th className="text-right">Step conv.</th>
                                            <th className="text-right">% of top</th>
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
                                                {i === 0 || row.stage === "uploaded" ? "—" : `${row.step_conv}%`}
                                            </td>
                                            <td className="text-t-secondary tabular-nums text-right">
                                                {row.pct_of_top}%
                                            </td>
                                        </TableRow>
                                    ))}
                                </Table>
                            </div>
                        </Card>
                    )}

                    {/* Hot leads surfaced by the report */}
                    {(report?.hot_leads?.length ?? 0) > 0 && (
                        <Card
                            title="Hot leads"
                            headContent={
                                <span className="mr-3 text-caption text-t-tertiary">Top {report!.hot_leads.length}</span>
                            }
                        >
                            <div className="p-1 pt-3 max-lg:px-0">
                                <Table
                                    cellsThead={
                                        <>
                                            <th>Name</th>
                                            <th>Phone</th>
                                            <th className="text-right">Conversion prob.</th>
                                        </>
                                    }
                                >
                                    {report!.hot_leads.map((l, i) => (
                                        <TableRow key={l.call_id || i}>
                                            <td className="font-medium text-t-primary">{l.name || "—"}</td>
                                            <td className="text-t-secondary tabular-nums">{l.phone_masked || "—"}</td>
                                            <td className="text-t-primary tabular-nums text-right">
                                                {l.conversion_prob != null ? `${Math.round(l.conversion_prob * 100)}%` : "—"}
                                            </td>
                                        </TableRow>
                                    ))}
                                </Table>
                            </div>
                        </Card>
                    )}
                </div>
            )}
        </Layout>
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
