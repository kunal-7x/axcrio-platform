"use client";

// Ad-Engine · ANALYTICS tab (W7.3) — deep per-ad / per-platform / cost-per-
// everything / real-vs-reported analytics with CSV/Excel export.
//
// MIRRORS app/analytics/page.tsx VERBATIM in look + idiom: the KpiCard derived-
// metric row, the recharts Pie (innerR 62% / outerR 92%) + Area configs, the
// shared `chartTooltip` token style, the Table/TableRow detail tables, and the
// client-side CSV/Excel Download menu in a Card headContent. Zero raw hex —
// every colour via tokens / the shared _charts ramps. Reuses the verbatim
// Core_2 kit (Card, KpiCard, Percentage, Table, TableRow, VirtualRows,
// GlobalFilters, Badge, Button, Skeleton) and the Spine helpers (_lib
// getAdsAnalytics, _shared DormantPanel/types, _charts chartTooltip + ramps).
//
// DORMANT-SAFE: every read is a `ReadResult` — a 404 (router not mounted) → the
// `DormantPanel` "coming soon" card, NEVER an error wall. Real non-200s → an
// inline state-block with the parsed message + a Retry button. 30s visibility-
// gated poll via the shared `useRealtimeRefresh`. Money stays `_minor` (paise);
// `fmtMoney` formats it. This tab is READ-ONLY — there are no spend-mutating
// controls, so `writable` gates nothing destructive; the export menu is a safe
// client-side action and stays available to every role.

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Card from "@/components/Card";
import Icon from "@/components/Icon";
import Badge from "@/components/Badge";
import Button from "@/components/Button";
import KpiCard from "@/components/KpiCard";
import Percentage from "@/components/Percentage";
import Table from "@/components/Table";
import TableRow from "@/components/TableRow";
import VirtualRows from "@/components/VirtualRows";
import GlobalFilters, { useGlobalFilters } from "@/components/GlobalFilters";
import Skeleton from "@/components/Skeleton";
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
    Legend,
} from "recharts";
import {
    getReport,
    exportReportSummary,
    exportReportLeads,
    type ResolvedRange,
} from "@/lib/report";
import {
    getAdsAnalytics,
    fmtMoney,
    useRealtimeRefresh,
    type AdsAnalyticsResponse,
    type ReadResult,
} from "../_lib";
import { DormantPanel, type AdsTabProps } from "../_shared";
import {
    chartTooltip,
    TEMP_COLORS,
    StageBreakdownBar,
    FUNNEL_COLORS,
    type StageSegment,
} from "../_charts";

/* --------------------------------------------------------------- row shapes */

// Per-platform aggregate row (GET /ads/analytics/per-platform). Loose at the
// edges (the backend shape is additive) but the fields the table binds are typed.
type PlatformRow = {
    platform: string; // meta | google | whatsapp | ...
    spend_minor?: number;
    leads?: number;
    cpl_minor?: number | null;
    roas?: number | null;
    [k: string]: unknown;
};

// Per-ad row (GET /ads/analytics/per-ad) — one creative variant's performance.
type AdRow = {
    ad_id?: string;
    variant?: string;
    placement?: string;
    spend_minor?: number;
    ctr?: number | null; // 0..100
    cpl_minor?: number | null;
    moderation_status?: string; // pending | approved | blocked
    [k: string]: unknown;
};

// Real-vs-reported series point (GET /ads/analytics/real-vs-reported) — the
// headline differentiator: platform-reported conversions vs the CRM-true count.
type ReconPoint = {
    date: string;
    platform_reported?: number;
    crm_true?: number;
    [k: string]: unknown;
};

/* ----------------------------------------------------- platform display map */

// Friendly platform label.
const PLATFORM_LABEL: Record<string, string> = {
    meta: "Meta",
    google: "Google",
    whatsapp: "WhatsApp",
    telephony: "Telephony",
    noop: "Unrouted",
};
function platformLabel(p?: string): string {
    if (!p) return "—";
    return PLATFORM_LABEL[p] ?? p.charAt(0).toUpperCase() + p.slice(1);
}

// Per-ad moderation status → Badge tone (reuses the one Badge vocabulary).
function moderationVariant(s?: string): "success" | "warning" | "danger" | "neutral" {
    if (s === "approved") return "success";
    if (s === "pending") return "warning";
    if (s === "blocked") return "danger";
    return "neutral";
}
function moderationLabel(s?: string): string {
    const map: Record<string, string> = {
        approved: "Approved",
        pending: "In review",
        blocked: "Blocked",
    };
    return s ? (map[s] ?? s) : "—";
}

// Pct formatter (CTR etc.) — em-dash when absent, one decimal otherwise.
function fmtPct(v?: number | null): string {
    if (v === null || v === undefined) return "—";
    return `${(Math.round(v * 10) / 10).toLocaleString()}%`;
}
function fmtRoas(v?: number | null): string {
    if (v === null || v === undefined) return "—";
    return `${(Math.round(v * 100) / 100).toLocaleString()}×`;
}

// ── Stage-breakdown segments (the VOICE stacked-bar language) ──────────────
// The 7-stage ad funnel — spend → reach → click → lead → qualified → visit →
// book — mapped to the shared FUNNEL_COLORS ramp so the per-row stacked bar
// reads 1:1 with the Command Center funnel + the voice latency bar. We build
// segments from whatever funnel counts a loose row carries; absent stages are
// simply dropped (never a fabricated 0), and a row with only spend collapses to
// a single clay "Spend" segment so the column still aligns.
const FUNNEL_STAGE_DEFS: Array<{ key: string; label: string }> = [
    { key: "reach", label: "Reach" },
    { key: "click", label: "Click" },
    { key: "lead", label: "Lead" },
    { key: "qualified", label: "Qualified" },
    { key: "visit", label: "Visit" },
    { key: "book", label: "Booked" },
];

function pluck(bag: Record<string, unknown>, ...keys: string[]): number {
    for (const k of keys) {
        const v = bag[k];
        if (typeof v === "number" && Number.isFinite(v)) return v;
    }
    return 0;
}

// Build the stacked-bar segments for one row. Prefers the funnel counts; falls
// back to a single Spend segment (in major units) so the bar is never empty.
function rowStageSegments(row: Record<string, unknown>): StageSegment[] {
    const segs: StageSegment[] = [];
    FUNNEL_STAGE_DEFS.forEach((d, i) => {
        const v = pluck(row, d.key, `${d.key}s`, `${d.key}_count`);
        if (v > 0) {
            segs.push({ key: d.key, label: d.label, value: v, color: FUNNEL_COLORS[(i + 1) % FUNNEL_COLORS.length] });
        }
    });
    if (segs.length === 0) {
        const spend = pluck(row, "spend_minor", "spend");
        if (spend > 0) segs.push({ key: "spend", label: "Spend", value: spend, color: FUNNEL_COLORS[0] });
    }
    return segs;
}

// Pull a number off a loose totals bag (cost-per metrics live on `totals`).
// Returns null when absent so the KPI renders an em-dash, never a fabricated 0.
function num(bag: Record<string, unknown> | undefined, key: string): number | null {
    if (!bag) return null;
    const v = bag[key];
    return typeof v === "number" ? v : null;
}

export default function AnalyticsTab({ writable: _writable, toast }: AdsTabProps) {
    // The shared URL filter state — range + campaign persist across every tab.
    const { range, campaign } = useGlobalFilters();

    // Three additive analytics reads. Each is dormant-safe (never throws).
    const [perAd, setPerAd] = useState<ReadResult<AdsAnalyticsResponse> | null>(null);
    const [perPlatform, setPerPlatform] = useState<ReadResult<AdsAnalyticsResponse> | null>(null);
    const [recon, setRecon] = useState<ReadResult<AdsAnalyticsResponse> | null>(null);
    const [loading, setLoading] = useState(true);

    // Virtualized per-ad scroll container (VirtualRows needs a scrollRef).
    const adScrollRef = useRef<HTMLDivElement | null>(null);

    const filters = useMemo(
        () => ({
            range: range.preset,
            from: range.from,
            to: range.to,
            campaign: campaign || undefined,
        }),
        [range.preset, range.from, range.to, campaign],
    );

    // `load` reads the latest `perAd` to decide whether to show the skeleton, but
    // we don't want that to re-create the callback (it would tear down the poll
    // every render). A ref tracks "do we already have data?" instead.
    const hasDataRef = useRef(false);
    const load = useCallback(() => {
        if (!hasDataRef.current) setLoading(true);
        Promise.all([
            getAdsAnalytics("per-ad", filters),
            getAdsAnalytics("per-platform", filters),
            getAdsAnalytics("real-vs-reported", filters),
        ])
            .then(([a, p, r]) => {
                setPerAd(a);
                setPerPlatform(p);
                setRecon(r);
                hasDataRef.current = true;
            })
            .finally(() => setLoading(false));
    }, [filters]);

    useEffect(() => {
        load();
    }, [load]);

    // 30s visibility-gated poll (the codebase's cleanest realtime idiom).
    useRealtimeRefresh(load, 30000);

    // ── Dormancy: if EVERY read is dormant, the module is not mounted yet → the
    //    premium DormantPanel (never an error wall). One mounted read is enough
    //    to render the live shell (the rest degrade to empty states).
    const allDormant =
        perAd?.kind === "dormant" &&
        perPlatform?.kind === "dormant" &&
        recon?.kind === "dormant";

    // First non-dormant error → the inline error state (with Retry).
    const firstError =
        (perAd?.kind === "error" && perAd.message) ||
        (perPlatform?.kind === "error" && perPlatform.message) ||
        (recon?.kind === "error" && recon.message) ||
        "";

    // ── Unwrap OK payloads (dormant/error → undefined so the shell still renders).
    const adData = perAd?.kind === "ok" ? perAd.data : undefined;
    const platData = perPlatform?.kind === "ok" ? perPlatform.data : undefined;
    const reconData = recon?.kind === "ok" ? recon.data : undefined;

    // ── Cost-per-everything KPI row (totals bag off per-ad, then per-platform).
    //    Deltas show a Percentage chip ONLY when the backend emits *_delta_pct —
    //    no fabricated movement (the analytics page's discipline). For cost
    //    metrics, a NEGATIVE delta is GOOD, so we flip the sign into Percentage
    //    (which colours positive = green/down-arrow).
    const costTotals = (adData?.totals ?? platData?.totals) as
        | Record<string, unknown>
        | undefined;
    const cpm = num(costTotals, "cpm_minor");
    const cpc = num(costTotals, "cpc_minor");
    const cpl = num(costTotals, "cpl_minor");
    const cpq = num(costTotals, "cp_qualified_minor");
    const cpmDelta = num(costTotals, "cpm_delta_pct");
    const cpcDelta = num(costTotals, "cpc_delta_pct");
    const cplDelta = num(costTotals, "cpl_delta_pct");
    const cpqDelta = num(costTotals, "cp_qualified_delta_pct");
    const sparkOf = (key: string): number[] | undefined => {
        const s = costTotals?.[key];
        return Array.isArray(s) && s.length > 1 ? (s as number[]) : undefined;
    };
    // Sub-line: a delta chip when present, else a plain descriptor.
    const costSub = (delta: number | null, descriptor: string) =>
        delta != null ? (
            <span className="inline-flex items-center gap-2">
                <Percentage value={-delta} /> vs prior
            </span>
        ) : (
            descriptor
        );

    // ── Per-platform donut + table ──
    const platRows = useMemo<PlatformRow[]>(
        () => (platData?.rows as PlatformRow[] | undefined) ?? [],
        [platData],
    );
    const pieData = useMemo(
        () =>
            platRows
                .map((r) => ({
                    name: platformLabel(r.platform),
                    value: r.spend_minor ?? 0,
                }))
                .filter((d) => d.value > 0),
        [platRows],
    );
    const pieTotal = useMemo(() => pieData.reduce((s, d) => s + d.value, 0), [pieData]);

    // ── Per-ad rows (virtualized) ──
    const adRows = useMemo<AdRow[]>(
        () => (adData?.rows as AdRow[] | undefined) ?? [],
        [adData],
    );

    // ── Real-vs-reported series + clamped reconciliation factor ──
    const reconSeries = useMemo<ReconPoint[]>(
        () => (reconData?.rows as ReconPoint[] | undefined) ?? [],
        [reconData],
    );
    const hasRecon = reconSeries.some(
        (p) => (p.platform_reported ?? 0) > 0 || (p.crm_true ?? 0) > 0,
    );
    // The factor the backend reports (crm_true / platform_reported), clamped to a
    // sane [0,2] band so a divide-by-tiny doesn't blow up the tile.
    const reconFactorRaw = num(
        reconData?.totals as Record<string, unknown> | undefined,
        "reconciliation_factor",
    );
    const reconFactor =
        reconFactorRaw === null ? null : Math.max(0, Math.min(2, reconFactorRaw));
    // Tone: a healthy factor sits near 1.0; a wide divergence warns the founder
    // that the platform's numbers can't be trusted.
    const reconTone: "success" | "warning" | "danger" =
        reconFactor === null
            ? "warning"
            : Math.abs(reconFactor - 1) <= 0.15
              ? "success"
              : Math.abs(reconFactor - 1) <= 0.4
                ? "warning"
                : "danger";

    // ── CSV / Excel export — client-side blob via lib/report's exporters, on the
    //    shared funnel/range report (Asia/Kolkata, default today). No backend
    //    route, no extra dependency. The menu lives in the first Card headContent.
    const [exporting, setExporting] = useState(false);
    const onExport = useCallback(
        async (kind: "summary" | "leads", excel: boolean) => {
            setExporting(true);
            try {
                const report = await getReport(
                    range as ResolvedRange,
                    campaign ? { campaign } : undefined,
                );
                if (kind === "summary") exportReportSummary(report, excel);
                else exportReportLeads(report, excel);
                toast(`${kind === "summary" ? "Report" : "Leads"} exported`, "success");
            } catch (e) {
                toast(e instanceof Error ? e.message : "Export failed", "error");
            } finally {
                setExporting(false);
            }
        },
        [range, campaign, toast],
    );

    /* ----------------------------------------------------------------- dormant */
    if (allDormant) {
        return (
            <DormantPanel
                icon="chart"
                title="Ad analytics is warming up"
                sub="Connect a Meta or Google account to light up per-ad, per-platform and real-vs-reported numbers here."
            />
        );
    }

    /* ------------------------------------------------------------------- error */
    if (firstError && !adData && !platData && !reconData) {
        return (
            <div className="state-block">
                <span className="state-glyph">
                    <Icon name="info" className="fill-inherit" />
                </span>
                <div className="state-title">We couldn&apos;t load analytics</div>
                <div className="state-sub max-w-md mx-auto">{firstError}</div>
                <Button isStroke icon="clock" onClick={load} className="mt-4">
                    Try again
                </Button>
            </div>
        );
    }

    /* ------------------------------------------------------------------ loading */
    if (loading && !adData && !platData && !reconData) {
        return (
            <div className="flex flex-col gap-3">
                <Skeleton.Stats count={4} />
                <div className="grid grid-cols-3 gap-3 max-lg:grid-cols-1">
                    <Card title="Spend by platform" className="col-span-2 max-lg:col-span-1">
                        <Table
                            cellsThead={
                                <>
                                    <th>Platform</th>
                                    <th>Stage breakdown</th>
                                    <th className="text-right">Spend</th>
                                    <th className="text-right">Leads</th>
                                    <th className="text-right">CPL</th>
                                    <th className="text-right">ROAS</th>
                                </>
                            }
                        >
                            <Skeleton.TableRows rows={5} cols={6} />
                        </Table>
                    </Card>
                    <Card title="Reconciliation">
                        <div className="px-3 pb-4 pt-2">
                            <Skeleton.Lines lines={4} />
                        </div>
                    </Card>
                </div>
                <Card title="Per-ad performance">
                    <Table
                        cellsThead={
                            <>
                                <th>Ad variant</th>
                                <th>Stage breakdown</th>
                                <th>Placement</th>
                                <th className="text-right">Spend</th>
                                <th className="text-right">CTR</th>
                                <th className="text-right">CPL</th>
                                <th>Moderation</th>
                            </>
                        }
                    >
                        <Skeleton.TableRows rows={8} cols={7} />
                    </Table>
                </Card>
            </div>
        );
    }

    /* -------------------------------------------------------------------- live */
    return (
        <div className="flex flex-col gap-3">
            {/* 1 — Cost-per-everything KPI row, with the shared filter bar + the
                CSV/Excel export menu in the first Card headContent (analytics idiom). */}
            <Card
                title="Cost per outcome"
                headContent={
                    <div className="flex flex-wrap items-center gap-2">
                        <GlobalFilters show={{ range: true, campaign: true, status: false }} />
                        <DownloadMenu disabled={exporting} onExport={onExport} />
                    </div>
                }
            >
                <div className="grid grid-cols-4 gap-3 px-3 pb-3 max-lg:grid-cols-2 max-sm:grid-cols-1">
                    <KpiCard
                        label="CPM"
                        value={fmtMoney(cpm)}
                        icon="desktop"
                        tone="info"
                        sub={costSub(cpmDelta, "per 1,000 impressions")}
                        spark={sparkOf("cpm_spark")}
                    />
                    <KpiCard
                        label="CPC"
                        value={fmtMoney(cpc)}
                        icon="arrow-up-right"
                        tone="info"
                        sub={costSub(cpcDelta, "per click")}
                        spark={sparkOf("cpc_spark")}
                    />
                    <KpiCard
                        label="CPL"
                        value={fmtMoney(cpl)}
                        icon="income"
                        tone="success"
                        sub={costSub(cplDelta, "per lead captured")}
                        spark={sparkOf("cpl_spark")}
                    />
                    <KpiCard
                        label="Cost per qualified"
                        value={fmtMoney(cpq)}
                        icon="check-circle"
                        tone="warning"
                        sub={costSub(cpqDelta, "per qualified lead")}
                        spark={sparkOf("cp_qualified_spark")}
                    />
                </div>
            </Card>

            {/* 2 — Per-platform table (left, 2/3) + the spend-mix donut. */}
            <div className="grid grid-cols-3 gap-3 max-lg:grid-cols-1">
                <div className="col-span-2 max-lg:col-span-1">
                    <Card title="Spend by platform">
                        <div className="p-1 pt-3 max-lg:px-0">
                            {platRows.length > 0 ? (
                                <Table
                                    cellsThead={
                                        <>
                                            <th>Platform</th>
                                            <th className="min-w-[10rem]">Stage breakdown</th>
                                            <th className="text-right">Spend</th>
                                            <th className="text-right">Leads</th>
                                            <th className="text-right">CPL</th>
                                            <th className="text-right">ROAS</th>
                                        </>
                                    }
                                >
                                    {platRows.map((r, i) => (
                                        <TableRow key={r.platform || i}>
                                            <td className="font-medium text-t-primary">
                                                {platformLabel(r.platform)}
                                            </td>
                                            <td className="min-w-[10rem] pr-4">
                                                <StageBreakdownBar segments={rowStageSegments(r)} />
                                            </td>
                                            <td className="text-t-primary tabular-nums text-right">
                                                {fmtMoney(r.spend_minor)}
                                            </td>
                                            <td className="text-t-secondary tabular-nums text-right">
                                                {(r.leads ?? 0).toLocaleString()}
                                            </td>
                                            <td className="text-t-secondary tabular-nums text-right">
                                                {fmtMoney(r.cpl_minor)}
                                            </td>
                                            <td className="text-t-primary tabular-nums text-right">
                                                {fmtRoas(r.roas)}
                                            </td>
                                        </TableRow>
                                    ))}
                                </Table>
                            ) : (
                                <div className="flex flex-col items-center text-center py-12 px-5">
                                    <div className="flex justify-center items-center size-14 mb-3 rounded-full bg-b-surface1">
                                        <Icon className="fill-t-secondary" name="chart" />
                                    </div>
                                    <div className="text-body-2 text-t-secondary max-w-72">
                                        Spend by platform appears once a connected
                                        account starts running ads in this range.
                                    </div>
                                </div>
                            )}
                        </div>
                    </Card>
                </div>

                {/* Spend-mix donut with the blended total in the centre. */}
                <Card title="Spend mix">
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
                                                    <Cell
                                                        key={i}
                                                        fill={TEMP_COLORS[i % TEMP_COLORS.length]}
                                                    />
                                                ))}
                                            </Pie>
                                            <Tooltip {...chartTooltip} />
                                        </PieChart>
                                    </ResponsiveContainer>
                                    <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
                                        <div className="text-h5 text-t-primary tabular-nums">
                                            {fmtMoney(pieTotal)}
                                        </div>
                                        <div className="text-caption text-t-tertiary">spend</div>
                                    </div>
                                </div>
                                <div className="mt-3 flex flex-col gap-2">
                                    {pieData.map((d, i) => (
                                        <div
                                            key={d.name}
                                            className="flex items-center gap-2 text-caption"
                                        >
                                            <span
                                                className="size-2.5 rounded-full shrink-0"
                                                style={{
                                                    background: TEMP_COLORS[i % TEMP_COLORS.length],
                                                }}
                                            />
                                            <span className="text-t-secondary">{d.name}</span>
                                            <span className="ml-auto text-t-primary tabular-nums">
                                                {fmtMoney(d.value)}
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
                                    The spend mix appears once ads start spending.
                                </div>
                            </div>
                        )}
                    </div>
                </Card>
            </div>

            {/* 3 — Per-ad performance table (virtualized for large variant sets). */}
            <Card
                title="Per-ad performance"
                headContent={
                    adRows.length > 0 ? (
                        <span className="mr-3 text-caption text-t-tertiary tabular-nums">
                            {adRows.length.toLocaleString()} ads
                        </span>
                    ) : undefined
                }
            >
                {adRows.length > 0 ? (
                    <div
                        ref={adScrollRef}
                        className="max-h-[28rem] overflow-y-auto scrollbar-none p-1 pt-3 max-lg:px-0"
                    >
                        <Table
                            cellsThead={
                                <>
                                    <th>Ad variant</th>
                                    <th className="min-w-[10rem]">Stage breakdown</th>
                                    <th>Placement</th>
                                    <th className="text-right">Spend</th>
                                    <th className="text-right">CTR</th>
                                    <th className="text-right">CPL</th>
                                    <th>Moderation</th>
                                </>
                            }
                        >
                            <VirtualRows
                                items={adRows}
                                rowKey={(r, i) => r.ad_id || `${r.variant ?? "ad"}-${i}`}
                                scrollRef={adScrollRef}
                                colSpan={7}
                                estimateRowH={56}
                                renderRow={(r) => (
                                    <tr className="border-t border-s-subtle hover:bg-b-highlight transition-colors">
                                        <td className="font-medium text-t-primary">
                                            {r.variant || "—"}
                                        </td>
                                        <td className="min-w-[10rem] pr-4">
                                            <StageBreakdownBar segments={rowStageSegments(r)} />
                                        </td>
                                        <td className="text-t-secondary">{r.placement || "—"}</td>
                                        <td className="text-t-primary tabular-nums text-right">
                                            {fmtMoney(r.spend_minor)}
                                        </td>
                                        <td className="text-t-secondary tabular-nums text-right">
                                            {fmtPct(r.ctr)}
                                        </td>
                                        <td className="text-t-secondary tabular-nums text-right">
                                            {fmtMoney(r.cpl_minor)}
                                        </td>
                                        <td>
                                            <Badge variant={moderationVariant(r.moderation_status)}>
                                                {moderationLabel(r.moderation_status)}
                                            </Badge>
                                        </td>
                                    </tr>
                                )}
                            />
                        </Table>
                    </div>
                ) : (
                    <div className="flex flex-col items-center text-center py-12 px-5">
                        <div className="flex justify-center items-center size-14 mb-3 rounded-full bg-b-surface1">
                            <Icon className="fill-t-secondary" name="chart" />
                        </div>
                        <div className="text-sub-title-1 text-t-primary">No ad data yet</div>
                        <div className="mt-1 text-body-2 text-t-secondary max-w-80">
                            Per-ad spend, CTR and CPL appear here once your variants
                            start delivering in this range.
                        </div>
                    </div>
                )}
            </Card>

            {/* 4 — Real-vs-reported: the headline differentiator. Two-series compare
                of platform-reported vs CRM-true conversions + the clamped
                reconciliation factor as a tone-warning KpiCard. */}
            <div className="grid grid-cols-3 gap-3 max-lg:grid-cols-1">
                <div className="col-span-2 max-lg:col-span-1">
                    <Card
                        title="Real vs reported"
                        headContent={
                            <span className="mr-3 text-caption text-t-tertiary">
                                Platform claims vs CRM truth
                            </span>
                        }
                    >
                        <div className="px-3 pb-4 pt-2 h-64">
                            {hasRecon ? (
                                <ResponsiveContainer width="100%" height="100%">
                                    <AreaChart
                                        data={reconSeries}
                                        margin={{ top: 8, right: 12, left: -16, bottom: 0 }}
                                    >
                                        <defs>
                                            <linearGradient
                                                id="adsReported"
                                                x1="0"
                                                y1="0"
                                                x2="0"
                                                y2="1"
                                            >
                                                <stop
                                                    offset="0%"
                                                    stopColor="var(--primary-04)"
                                                    stopOpacity={0.3}
                                                />
                                                <stop
                                                    offset="100%"
                                                    stopColor="var(--primary-04)"
                                                    stopOpacity={0}
                                                />
                                            </linearGradient>
                                            <linearGradient id="adsTrue" x1="0" y1="0" x2="0" y2="1">
                                                <stop
                                                    offset="0%"
                                                    stopColor="var(--primary-01)"
                                                    stopOpacity={0.35}
                                                />
                                                <stop
                                                    offset="100%"
                                                    stopColor="var(--primary-01)"
                                                    stopOpacity={0}
                                                />
                                            </linearGradient>
                                        </defs>
                                        <CartesianGrid
                                            stroke="var(--stroke-stroke2)"
                                            strokeOpacity={0.4}
                                            vertical={false}
                                        />
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
                                        <Legend
                                            iconType="circle"
                                            wrapperStyle={{
                                                fontSize: 12,
                                                color: "var(--text-secondary)",
                                            }}
                                        />
                                        <Area
                                            type="monotone"
                                            dataKey="platform_reported"
                                            name="Platform reported"
                                            stroke="var(--primary-04)"
                                            strokeWidth={2}
                                            fill="url(#adsReported)"
                                        />
                                        <Area
                                            type="monotone"
                                            dataKey="crm_true"
                                            name="CRM true"
                                            stroke="var(--primary-01)"
                                            strokeWidth={2}
                                            fill="url(#adsTrue)"
                                        />
                                    </AreaChart>
                                </ResponsiveContainer>
                            ) : (
                                <div className="flex h-full flex-col items-center justify-center text-center">
                                    <div className="text-body-2 text-t-secondary max-w-72">
                                        Once conversions flow back from your CRM, the
                                        real-vs-reported comparison appears here.
                                    </div>
                                </div>
                            )}
                        </div>
                    </Card>
                </div>

                {/* Reconciliation factor KpiCard — tone warns when platform numbers
                    diverge from CRM truth. */}
                <Card title="Reconciliation">
                    <div className="px-3 pb-4 pt-2">
                        <KpiCard
                            label="Reconciliation factor"
                            value={reconFactor === null ? "—" : `${reconFactor.toFixed(2)}×`}
                            icon="filters"
                            tone={reconTone}
                            sub={
                                reconFactor === null
                                    ? "Awaiting CRM conversions"
                                    : reconTone === "success"
                                      ? "Platform numbers match CRM truth"
                                      : reconFactor < 1
                                        ? "Platform over-reports conversions"
                                        : "Platform under-reports conversions"
                            }
                            meter={reconFactor === null ? null : Math.min(1, reconFactor / 2)}
                        />
                        <div className="mt-3 text-caption text-t-tertiary leading-relaxed">
                            We clamp the platform&apos;s reported conversions against
                            your CRM&apos;s true outcomes. A factor near 1.0 means the
                            platform&apos;s numbers can be trusted; a wide gap means
                            your spend is being optimised on inflated signals.
                        </div>
                    </div>
                </Card>
            </div>
        </div>
    );
}

/* ----------------------------------------------- Download menu (CSV / Excel) */
// Mirrors app/analytics/page.tsx's DownloadMenu VERBATIM — the Core_2-styled
// dropdown (no extra dependency), client-side blob export of the summary report
// + the leads list. Closes on outside-click / Escape.
function DownloadMenu({
    disabled,
    onExport,
}: {
    disabled: boolean;
    onExport: (kind: "summary" | "leads", excel: boolean) => void;
}) {
    const [open, setOpen] = useState(false);

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
                Export
                <Icon className="size-4 fill-t-secondary" name="arrow-up-right" />
            </button>
            {open && !disabled && (
                <div className="absolute right-0 z-20 mt-2 w-60 p-2 rounded-2xl bg-b-surface2 border border-s-subtle shadow-depth">
                    <div className="px-2 pt-1 pb-1.5 text-caption text-t-tertiary">
                        Summary report
                    </div>
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
