"use client";

// Ad-Engine · Command Center tab — the at-a-glance ROI cockpit (W7.2).
//
// The single-screen answer to "is the spend working?": a money KPI hero strip
// (Spend / Reach / Leads / Qualified / ROAS / Cost-per-qualified), the 8-stage
// acquisition funnel (spend → reach → click → lead → qualified → visit → book),
// a ROAS / spend-mix donut by platform, a spend-over-time area chart, and live
// per-campaign pacing meters (today's spend vs daily cap).
//
// PIXEL-IDENTICAL to the existing Core_2 pages by construction — it reuses the
// SAME widgets verbatim: HeroStat / KpiCard / Card / GlobalFilters from the kit,
// FunnelDiagram + chartTooltip from ../_charts, CenterDonut from the dashboard,
// and the recharts AreaChart config copied from app/analytics/page.tsx (clay
// gradient, token grid/axis colours). Zero raw hex; every colour via a token.
//
// Dormant-safe: while the /ads router is unmounted (FEATURE_ADS=0) every read
// 404s → {kind:"dormant"} and we keep the honest "coming soon" explainer — never
// an error wall. Each live panel carries its own loading (Skeleton) / empty
// (state-block) / error (state-block + Retry) state in the interface's voice.
//
// The KPI strip + explainer below are LIFTED VERBATIM from the original inline
// Overview; W7.2 adds the funnel / donut / area / pacing widgets beneath them.

import { useCallback, useEffect, useMemo, useState } from "react";
import Icon from "@/components/Icon";
import Badge from "@/components/Badge";
import Card from "@/components/Card";
import Button from "@/components/Button";
import KpiCard from "@/components/KpiCard";
import Table from "@/components/Table";
import TableRow from "@/components/TableRow";
import Skeleton, { SkeletonBar, SkeletonStats, SkeletonLines } from "@/components/Skeleton";
import GlobalFilters, { useGlobalFilters } from "@/components/GlobalFilters";
import { CenterDonut } from "@/app/_dashboard-charts";
import {
    ResponsiveContainer,
    AreaChart,
    Area,
    XAxis,
    YAxis,
    CartesianGrid,
    Tooltip,
} from "recharts";
import {
    fmtMoney,
    getAdsAnalytics,
    useRealtimeRefresh,
    type AdsHealth,
    type AdsAnalyticsResponse,
    type ReadResult,
} from "../_lib";
import { HeroStat, FlowStep } from "../_shared";
import {
    FunnelDiagram,
    FUNNEL_LABEL,
    FUNNEL_COLORS,
    chartTooltip,
    StageBreakdownBar,
    type FunnelStage,
    type StageSegment,
} from "../_charts";

export type CommandTabProps = {
    hc: AdsHealth | null;
    health: ReadResult<AdsHealth> | null;
    loading: boolean;
    moduleDormant: boolean;
    activeCount: number;
    pendingCount: number;
    totalCount: number;
    spendTodayMinor: number;
    currency: string;
};

// The canonical acquisition-funnel ORDER for the Command Center (spec §2.2).
// Differs from the analytics lead funnel; passed to the shared FunnelDiagram.
const AD_FUNNEL_STAGES = ["spend", "reach", "click", "lead", "qualified", "visit", "book"];

// Spend-mix donut palette — the single clay ramp (Book Cloth → warm → neutral),
// pure tokens, mirrors the funnel/analytics colour discipline. Active = clay.
const MIX_COLORS = ["var(--primary-01)", "var(--primary-02)", "var(--primary-04)", "var(--primary-05)"];

// Safe numeric pluck from the loose analytics Record (totals are untyped at W7.0).
function num(rec: Record<string, unknown> | undefined, ...keys: string[]): number {
    if (!rec) return 0;
    for (const k of keys) {
        const v = rec[k];
        if (typeof v === "number" && Number.isFinite(v)) return v;
    }
    return 0;
}

function numList(v: unknown): number[] {
    return Array.isArray(v) ? v.filter((n): n is number => typeof n === "number") : [];
}

// The 7-stage ad-funnel definition for the per-row "Stage breakdown" stacked bar
// (the VOICE per-turn latency-bar language, reused). Spend → reach → click →
// lead → qualified → visit → book, each mapped to the shared FUNNEL_COLORS ramp
// so a row's bar reads 1:1 with the Acquisition funnel above it. Absent stages
// are dropped (never a fabricated 0); a spend-only row collapses to one clay
// "Spend" segment so the column still aligns.
const FUNNEL_STAGE_DEFS: Array<{ key: string; label: string }> = [
    { key: "reach", label: "Reach" },
    { key: "click", label: "Click" },
    { key: "lead", label: "Lead" },
    { key: "qualified", label: "Qualified" },
    { key: "visit", label: "Visit" },
    { key: "book", label: "Booked" },
];

function rowStageSegments(row: Record<string, unknown>): StageSegment[] {
    const segs: StageSegment[] = [];
    FUNNEL_STAGE_DEFS.forEach((d, i) => {
        const v = num(row, d.key, `${d.key}s`, `${d.key}_count`);
        if (v > 0) {
            segs.push({ key: d.key, label: d.label, value: v, color: FUNNEL_COLORS[(i + 1) % FUNNEL_COLORS.length] });
        }
    });
    if (segs.length === 0) {
        const spend = num(row, "spend_minor", "spend");
        if (spend > 0) segs.push({ key: "spend", label: "Spend", value: spend, color: FUNNEL_COLORS[0] });
    }
    return segs;
}

export default function CommandTab({
    hc,
    loading,
    moduleDormant,
    activeCount,
    pendingCount,
    totalCount,
    spendTodayMinor,
    currency,
}: CommandTabProps) {
    const { range, campaign } = useGlobalFilters();
    const filters = useMemo(
        () => ({ from: range.from, to: range.to, range: range.preset, campaign: campaign || undefined }),
        [range.from, range.to, range.preset, campaign],
    );

    // ---- analytics reads (funnel drives KPIs + funnel; per-platform the donut) ----
    const [funnelRes, setFunnelRes] = useState<ReadResult<AdsAnalyticsResponse> | null>(null);
    const [mixRes, setMixRes] = useState<ReadResult<AdsAnalyticsResponse> | null>(null);
    const [busy, setBusy] = useState(true);

    const load = useCallback(() => {
        setBusy(true);
        Promise.all([
            getAdsAnalytics("funnel", filters),
            getAdsAnalytics("per-platform", filters),
        ])
            .then(([f, m]) => {
                setFunnelRes(f);
                setMixRes(m);
            })
            .finally(() => setBusy(false));
    }, [filters]);

    // Initial + on-filter-change load, then the 30s visibility-gated poll spine.
    useEffect(() => {
        load();
    }, [load]);
    useRealtimeRefresh(load, 30000);

    const metaOn = hc?.providers.meta === "configured";
    const googleOn = hc?.providers.google === "configured";
    const anyProvider = metaOn || googleOn;
    const liveSpend = anyProvider && !hc?.dry_run;
    const dailyCap = hc?.caps.daily_cap_minor ?? 0;

    // The whole analytics surface is dormant when the module itself is dormant OR
    // both reads 404 — render the explainer, never an error wall.
    const analyticsDormant =
        moduleDormant ||
        (funnelRes?.kind === "dormant" && mixRes?.kind === "dormant") ||
        (!anyProvider && funnelRes?.kind !== "ok");

    const funnel: FunnelStage[] = funnelRes?.kind === "ok" ? funnelRes.data.funnel ?? [] : [];
    const totals = funnelRes?.kind === "ok" ? funnelRes.data.totals : undefined;
    const funnelTop = funnel.length ? Math.max(...funnel.map((s) => s.count), 1) : 1;

    // KPI numbers — real values only, derived from the funnel `totals` block.
    const spendMinor = num(totals as Record<string, unknown>, "spend_minor", "spend_today_minor") || spendTodayMinor;
    const reach = num(totals as Record<string, unknown>, "reach");
    const leads = num(totals as Record<string, unknown>, "leads");
    const qualified = num(totals as Record<string, unknown>, "qualified");
    const revenueMinor = num(totals as Record<string, unknown>, "revenue_minor");
    const roas = spendMinor > 0 ? revenueMinor / spendMinor : 0;
    const cpqMinor = qualified > 0 ? Math.round(spendMinor / qualified) : null;
    const spendSpark = numList((totals as Record<string, unknown> | undefined)?.["spend_series"]);
    const roasSpark = numList((totals as Record<string, unknown> | undefined)?.["roas_series"]);

    // Spend-over-time series for the area chart: [{ date, spend }] in MAJOR units
    // for a legible axis (recharts plots, fmtMoney formats the tooltip).
    const series = useMemo(() => {
        const raw = (totals as Record<string, unknown> | undefined)?.["spend_over_time"];
        if (!Array.isArray(raw)) return [] as { date: string; spend: number }[];
        return raw
            .map((p) => {
                const r = p as Record<string, unknown>;
                const date = typeof r.date === "string" ? r.date : typeof r.day === "string" ? r.day : "";
                const minor = num(r, "spend_minor", "spend");
                return { date, spend: minor / 100 };
            })
            .filter((p) => p.date);
    }, [totals]);

    // Spend-mix donut slices by platform — active slice is the brand clay.
    const mixSlices = useMemo(() => {
        const rows = mixRes?.kind === "ok" ? mixRes.data.rows ?? [] : [];
        return rows
            .map((r, i) => {
                const name = String(r.platform ?? r.provider ?? r.name ?? "—");
                const value = num(r as Record<string, unknown>, "spend_minor", "spend") / 100;
                return { name: name.charAt(0).toUpperCase() + name.slice(1), value, color: MIX_COLORS[i % MIX_COLORS.length] };
            })
            .filter((s) => s.value > 0);
    }, [mixRes]);
    const mixTotal = mixSlices.reduce((a, s) => a + s.value, 0);

    // Spend & funnel breakdown rows — one row per campaign/platform, each carrying
    // the VOICE stage-breakdown stacked bar (its 7-stage ad-funnel split) plus the
    // per-metric columns the founder asked for: Spend / Leads / Qualified / CPL /
    // ROAS. Sourced from the per-platform analytics rows (the same payload that
    // feeds the spend-mix donut); the backend key is "campaign" when grouped by
    // campaign, else "platform"/"provider". Sorted by spend, biggest first.
    const breakdownRows = useMemo(() => {
        const rows = mixRes?.kind === "ok" ? mixRes.data.rows ?? [] : [];
        return rows
            .map((raw) => {
                const r = raw as Record<string, unknown>;
                const name = String(r.campaign ?? r.platform ?? r.provider ?? r.name ?? "—");
                const spend = num(r, "spend_minor", "spend");
                const rLeads = num(r, "leads", "lead", "lead_count");
                const rQualified = num(r, "qualified", "qualified_count");
                const cplMinor = num(r, "cpl_minor");
                const revenue = num(r, "revenue_minor");
                const rowRoas = num(r, "roas") || (spend > 0 ? revenue / spend : 0);
                return {
                    name: name.charAt(0).toUpperCase() + name.slice(1),
                    segments: rowStageSegments(r),
                    spend,
                    leads: rLeads,
                    qualified: rQualified,
                    cplMinor: cplMinor > 0 ? cplMinor : rLeads > 0 ? Math.round(spend / rLeads) : 0,
                    roas: rowRoas,
                };
            })
            .filter((r) => r.spend > 0 || r.segments.length > 0)
            .sort((a, b) => b.spend - a.spend);
    }, [mixRes]);

    // Live pacing — today's spend vs daily cap per active provider/campaign. We
    // surface the org-level spend-vs-cap from health when present (per-campaign
    // rows arrive with the campaigns payload, shown on the Campaigns tab).
    const pacing = useMemo(() => {
        const items: { label: string; spend: number; cap: number }[] = [];
        if (dailyCap > 0) {
            items.push({ label: "Today across active campaigns", spend: spendMinor, cap: dailyCap });
        }
        const orgCap = hc?.caps.org_daily_cap_minor ?? 0;
        if (orgCap > 0) {
            items.push({ label: "Organisation daily cap", spend: spendMinor, cap: orgCap });
        }
        return items;
    }, [dailyCap, hc, spendMinor]);

    const funnelError = funnelRes?.kind === "error" ? funnelRes.message : null;

    return (
        <div className="space-y-3">
            {/* Hero KPI strip — config + spend signals (verbatim original), always shown */}
            <div className="grid grid-cols-4 gap-3 max-lg:grid-cols-2 max-sm:grid-cols-1">
                <HeroStat
                    label="Ad Platforms"
                    glyph="promote"
                    glyphClass="fill-primary-01"
                    accent="var(--primary-01)"
                    loading={loading && !hc}
                    value={anyProvider ? `${[metaOn && "Meta", googleOn && "Google"].filter(Boolean).join(" + ")}` : "Not connected"}
                    foot={anyProvider ? "Marketing API linked" : "Awaiting Meta / Google credentials"}
                />
                <HeroStat
                    label="Live Campaigns"
                    glyph="feather"
                    glyphClass="fill-primary-02"
                    accent="var(--primary-02)"
                    delay={60}
                    loading={loading && !hc}
                    value={String(activeCount)}
                    foot={
                        pendingCount > 0
                            ? `${pendingCount} awaiting approval`
                            : totalCount === 0
                            ? "No campaigns yet"
                            : "All reviewed"
                    }
                />
                <HeroStat
                    label="Spend Today"
                    glyph="wallet"
                    glyphClass="fill-primary-04"
                    accent="var(--primary-04)"
                    delay={120}
                    loading={loading && !hc}
                    value={liveSpend ? fmtMoney(spendTodayMinor, currency) : fmtMoney(0, currency)}
                    foot={
                        dailyCap > 0
                            ? `of ${fmtMoney(dailyCap, currency)} hard cap`
                            : liveSpend
                            ? "across active campaigns"
                            : "Dry-run — nothing spends yet"
                    }
                />
                <HeroStat
                    label="Spend Guard"
                    glyph="lock"
                    glyphClass="fill-primary-05"
                    accent="var(--primary-05)"
                    delay={180}
                    loading={loading && !hc}
                    value={hc?.require_approval ? "Approval + breaker" : "Breaker"}
                    foot={
                        hc
                            ? `Auto-pause every ${hc.caps.poll_minutes}m on breach`
                            : "Human approval before any spend"
                    }
                />
            </div>

            {analyticsDormant ? (
                /* ---- DORMANT: the honest "coming soon" explainer (verbatim) ---- */
                <div className="card overflow-hidden">
                    <div className="relative p-6 max-lg:p-4">
                        <span
                            aria-hidden
                            className="pointer-events-none absolute -top-20 -right-16 size-56 rounded-full opacity-[0.10] blur-3xl"
                            style={{ background: "var(--primary-01)" }}
                        />
                        <div className="relative flex items-start gap-4 max-sm:flex-col">
                            <span className="grid place-items-center size-12 shrink-0 rounded-2xl bg-b-surface2 ring-1 ring-s-subtle fill-primary-01">
                                <Icon name="promote" className="size-6 fill-inherit" />
                            </span>
                            <div className="min-w-0 flex-1">
                                <div className="flex items-center gap-2 flex-wrap">
                                    <h3 className="text-h6 text-t-primary">Autonomous ads are coming soon</h3>
                                    <Badge variant="info" dot>
                                        In setup
                                    </Badge>
                                </div>
                                <p className="text-body-2 text-t-secondary mt-2 max-w-2xl">
                                    The spend-safety engine is built and offline-verified — hard daily caps,
                                    a cost-per-lead breaker, a human approval gate and an immutable audit
                                    trail. The platforms light up once your Meta or Google Ads account is
                                    connected on the server. Until then you can draft campaigns safely: in
                                    dry-run nothing can spend a rupee.
                                </p>
                                <div className="mt-4 grid grid-cols-3 gap-3 max-md:grid-cols-1">
                                    <FlowStep
                                        n={1}
                                        icon="magic-pencil"
                                        title="Brief"
                                        text="Describe the campaign in a line. The AI drafts copy, audience and objective — capped to your budget."
                                    />
                                    <FlowStep
                                        n={2}
                                        icon="lock"
                                        title="Approve"
                                        text="Nothing goes live without a human step-up. The draft waits, paused, until you sign off."
                                    />
                                    <FlowStep
                                        n={3}
                                        icon="feather"
                                        title="Auto-pilot"
                                        text="A breaker pauses any campaign that blows its budget or CPL; the optimizer scales winners, kills losers."
                                    />
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            ) : (
                <>
                    {/* ---- LIVE: ROI KPI row (real money only, single GlobalFilters) ---- */}
                    <Card
                        title="Return on ad spend"
                        headContent={<GlobalFilters className="mr-3" show={{ range: true, campaign: true }} />}
                    >
                        <div className="px-3 pb-1">
                            {busy && !totals ? (
                                <SkeletonStats count={4} />
                            ) : funnelError ? (
                                <div className="state-block">
                                    <span className="state-glyph">
                                        <Icon name="chart" className="fill-inherit" />
                                    </span>
                                    <div className="state-title">We couldn&apos;t load your ROI</div>
                                    <div className="state-sub max-w-md mx-auto">{funnelError}</div>
                                    <Button isStroke className="mt-4" onClick={load}>
                                        Try again
                                    </Button>
                                </div>
                            ) : (
                                <div className="grid grid-cols-4 gap-3 max-lg:grid-cols-2 max-sm:grid-cols-1">
                                    <KpiCard
                                        label="Spend"
                                        value={fmtMoney(spendMinor, currency)}
                                        icon="wallet"
                                        tone="info"
                                        spark={spendSpark}
                                        meter={dailyCap > 0 ? spendMinor / dailyCap : null}
                                        sub={dailyCap > 0 ? `of ${fmtMoney(dailyCap, currency)} cap` : "this range"}
                                    />
                                    <KpiCard
                                        label="Reach"
                                        value={reach.toLocaleString()}
                                        icon="earth"
                                        tone="neutral"
                                        sub={`${leads.toLocaleString()} leads · ${qualified.toLocaleString()} qualified`}
                                    />
                                    <KpiCard
                                        label="ROAS"
                                        value={roas > 0 ? `${roas.toFixed(2)}×` : "—"}
                                        icon="chart"
                                        tone={roas >= 1 ? "success" : "warning"}
                                        spark={roasSpark}
                                        sub={revenueMinor > 0 ? `${fmtMoney(revenueMinor, currency)} returned` : "Revenue lands here once leads convert"}
                                    />
                                    <KpiCard
                                        label="Cost per qualified"
                                        value={cpqMinor != null ? fmtMoney(cpqMinor, currency) : "—"}
                                        icon="check-circle"
                                        tone="neutral"
                                        sub={qualified > 0 ? `${qualified.toLocaleString()} qualified leads` : "No qualified leads yet"}
                                    />
                                </div>
                            )}
                        </div>
                    </Card>

                    {/* ---- Funnel + spend-mix donut (2-up) ---- */}
                    <div className="grid grid-cols-2 gap-3 max-lg:grid-cols-1">
                        <Card title="Acquisition funnel">
                            <div className="px-4 pb-4 pt-1">
                                {busy && !funnel.length ? (
                                    <SkeletonLines lines={7} />
                                ) : funnel.length === 0 ? (
                                    <div className="state-block">
                                        <span className="state-glyph">
                                            <Icon name="chart" className="fill-inherit" />
                                        </span>
                                        <div className="state-title">No funnel data in this range</div>
                                        <div className="state-sub max-w-md mx-auto">
                                            Spend lights up the funnel from reach to booking. Pick a wider range or wait for the next spend tick.
                                        </div>
                                    </div>
                                ) : (
                                    <FunnelDiagram funnel={funnel} top={funnelTop} stages={AD_FUNNEL_STAGES} />
                                )}
                            </div>
                        </Card>

                        <Card title="Spend mix">
                            <div className="px-4 pb-4 pt-2 min-h-44">
                                {busy && !mixSlices.length ? (
                                    <SkeletonLines lines={4} />
                                ) : mixSlices.length === 0 ? (
                                    <div className="state-block">
                                        <span className="state-glyph">
                                            <Icon name="cube" className="fill-inherit" />
                                        </span>
                                        <div className="state-title">No spend to split yet</div>
                                        <div className="state-sub max-w-md mx-auto">
                                            Once a campaign spends, you&apos;ll see the split across Meta, Google and WhatsApp here.
                                        </div>
                                    </div>
                                ) : (
                                    <CenterDonut
                                        data={mixSlices}
                                        total={Math.round(mixTotal)}
                                        centerLabel={roas > 0 ? `${roas.toFixed(2)}× ROAS` : "Spend"}
                                    />
                                )}
                            </div>
                        </Card>
                    </div>

                    {/* ---- Spend & funnel breakdown (the VOICE stage-breakdown table) ---- */}
                    <Card title="Spend & funnel breakdown">
                        <div className="p-1 pt-3 max-lg:px-0">
                            {busy && !breakdownRows.length ? (
                                <Table
                                    cellsThead={
                                        <>
                                            <th>Campaign</th>
                                            <th>Stage breakdown</th>
                                            <th className="text-right">Spend</th>
                                            <th className="text-right">Leads</th>
                                            <th className="text-right">Qualified</th>
                                            <th className="text-right">CPL</th>
                                            <th className="text-right">ROAS</th>
                                        </>
                                    }
                                >
                                    <Skeleton.TableRows rows={4} cols={7} />
                                </Table>
                            ) : breakdownRows.length === 0 ? (
                                <div className="flex flex-col items-center text-center py-12 px-5">
                                    <div className="flex justify-center items-center size-14 mb-3 rounded-full bg-b-surface1">
                                        <Icon className="fill-t-secondary" name="chart" />
                                    </div>
                                    <div className="text-body-2 text-t-secondary max-w-72">
                                        The per-campaign spend &amp; funnel breakdown appears
                                        once a connected account starts spending in this range.
                                    </div>
                                </div>
                            ) : (
                                <Table
                                    cellsThead={
                                        <>
                                            <th>Campaign</th>
                                            <th className="min-w-[11rem]">Stage breakdown</th>
                                            <th className="text-right">Spend</th>
                                            <th className="text-right">Leads</th>
                                            <th className="text-right">Qualified</th>
                                            <th className="text-right">CPL</th>
                                            <th className="text-right">ROAS</th>
                                        </>
                                    }
                                >
                                    {breakdownRows.map((r, i) => (
                                        <TableRow key={`${r.name}-${i}`}>
                                            <td className="font-medium text-t-primary">{r.name}</td>
                                            <td className="min-w-[11rem] pr-4">
                                                <StageBreakdownBar segments={r.segments} />
                                            </td>
                                            <td className="text-t-primary tabular-nums text-right">
                                                {fmtMoney(r.spend, currency)}
                                            </td>
                                            <td className="text-t-secondary tabular-nums text-right">
                                                {r.leads.toLocaleString()}
                                            </td>
                                            <td className="text-t-secondary tabular-nums text-right">
                                                {r.qualified.toLocaleString()}
                                            </td>
                                            <td className="text-t-secondary tabular-nums text-right">
                                                {r.cplMinor > 0 ? fmtMoney(r.cplMinor, currency) : "—"}
                                            </td>
                                            <td className="text-t-primary tabular-nums text-right">
                                                {r.roas > 0 ? `${r.roas.toFixed(2)}×` : "—"}
                                            </td>
                                        </TableRow>
                                    ))}
                                </Table>
                            )}
                        </div>
                    </Card>

                    {/* ---- Spend over time (clay area) ---- */}
                    <Card title="Spend over time">
                        <div className="px-3 pb-4 pt-2 h-64">
                            {busy && !series.length ? (
                                <SkeletonBar className="h-full w-full" />
                            ) : series.length === 0 ? (
                                <div className="flex h-full flex-col items-center justify-center text-center">
                                    <div className="text-body-2 text-t-secondary max-w-72">
                                        Spend over time appears here once campaigns start spending in this range.
                                    </div>
                                </div>
                            ) : (
                                <ResponsiveContainer width="100%" height="100%">
                                    <AreaChart data={series} margin={{ top: 8, right: 12, left: -16, bottom: 0 }}>
                                        <defs>
                                            <linearGradient id="adsSpendVol" x1="0" y1="0" x2="0" y2="1">
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
                                            width={36}
                                        />
                                        <Tooltip
                                            {...chartTooltip}
                                            formatter={(v: number) => [fmtMoney(Math.round(v * 100), currency), "Spend"]}
                                        />
                                        <Area
                                            type="monotone"
                                            dataKey="spend"
                                            stroke="var(--primary-01)"
                                            strokeWidth={2}
                                            fill="url(#adsSpendVol)"
                                            name="Spend"
                                        />
                                    </AreaChart>
                                </ResponsiveContainer>
                            )}
                        </div>
                    </Card>

                    {/* ---- Live pacing meters (spend vs cap) ---- */}
                    {pacing.length > 0 && (
                        <Card title="Live pacing">
                            <div className="px-5 pb-5 pt-1 space-y-4 max-lg:px-3">
                                {pacing.map((p) => {
                                    const ratio = p.cap > 0 ? Math.min(1, p.spend / p.cap) : 0;
                                    const pct = Math.round(ratio * 100);
                                    // Calm under 80% (clay), warning near the cap, danger at breaker.
                                    const tone =
                                        ratio >= 1
                                            ? "var(--primary-03)"
                                            : ratio >= 0.8
                                            ? "var(--primary-05)"
                                            : "var(--primary-01)";
                                    return (
                                        <div key={p.label}>
                                            <div className="flex items-center justify-between text-caption mb-1.5">
                                                <span className="text-t-secondary truncate">{p.label}</span>
                                                <span className="text-t-primary tabular-nums shrink-0">
                                                    {fmtMoney(p.spend, currency)}
                                                    <span className="text-t-tertiary"> / {fmtMoney(p.cap, currency)} · {pct}%</span>
                                                </span>
                                            </div>
                                            <div className="meter">
                                                <div className="meter-fill" style={{ width: `${pct}%`, background: tone }} />
                                            </div>
                                        </div>
                                    );
                                })}
                            </div>
                        </Card>
                    )}
                </>
            )}
        </div>
    );
}
