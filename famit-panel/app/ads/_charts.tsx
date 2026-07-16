"use client";

// Shared chart helpers for the Ad-Engine page (Command + Analytics tabs).
//
// These are EXTRACTED VERBATIM from app/analytics/page.tsx (where they live as
// page-local helpers) so the two ad tabs render an identical funnel + tooltip
// without re-deriving them. Keeping ONE copy here avoids drift between the
// Command Center funnel and the Analytics funnel.
//
// Colour discipline: the chart tooltip uses pure design tokens
// (var(--backgrounds-surface2) / var(--stroke-stroke2) / var(--text-tertiary)).
// The single-hue clay funnel ramp is reproduced EXACTLY as analytics renders it
// today — the HARD RULE (pixel-identical to the existing pages) is binding, and
// this ramp IS the canonical Core_2 funnel look. Its two anchor stops map to
// brand tokens (#ebdbbc = --primary-05 Manilla at the top, #cc785c = --primary-01
// Book Cloth at "hot"); the intermediate stops are the verified clay gradient.

import { useMemo, useState } from "react";

// One funnel stage row — mirrors lib/report.ts FunnelStage 1:1 so any caller can
// pass either the analytics report funnel or the ad-engine funnel payload.
export type FunnelStage = {
    stage: string;
    count: number;
    pct_of_top: number; // 0..100
    step_conv: number; // 0..100 vs previous stage
};

// Business-friendly funnel-stage labels (mirrors analytics + dashboard). Extends
// the lead funnel with the ad-acquisition stages (spend → reach → click → lead →
// qualified → visit → book) so the Command Center funnel can label them too.
export const FUNNEL_LABEL: Record<string, string> = {
    // lead funnel (analytics)
    uploaded: "Uploaded",
    dialed: "Dialed",
    connected: "Connected",
    interested: "Interested",
    warm: "Warm",
    hot: "Hot",
    booked: "Booked",
    converted: "Converted",
    // ad-acquisition funnel (Command Center)
    spend: "Spend",
    reach: "Reach",
    click: "Click",
    lead: "Lead",
    qualified: "Qualified",
    visit: "Visit",
    book: "Booked",
};

// Lead-temperature palette (brand → cool descent) — copied from analytics.
export const TEMP_COLORS = [
    "var(--primary-01)",
    "var(--color-chart-yellow, #FFB13C)",
    "var(--primary-02)",
    "var(--text-tertiary)",
];

// 8-stage funnel ramp — single-hue GEIST clay: light Manilla at the top,
// deepening to rich Book Cloth + deep clay at the win (the funnel "warms up"
// toward conversion). Reproduced EXACTLY from analytics so the two funnels are
// indistinguishable. ONE accent hue, legible on both light + dark surfaces.
export const FUNNEL_COLORS: string[] = [
    "#ecdcc0", // top — Manilla
    "#e3c7a3",
    "#dcb088",
    "#d99c72",
    "#d48860",
    "#cc785c", // Book Cloth (--primary-01)
    "#b35f44",
    "#974c34", // deep clay — the win
];

// recharts tooltip styling — pure tokens, shared by every chart on the page.
export const chartTooltip = {
    contentStyle: {
        background: "var(--backgrounds-surface2)",
        border: "1px solid var(--stroke-stroke2)",
        borderRadius: "12px",
        fontSize: "12px",
    },
    labelStyle: { color: "var(--text-tertiary)", marginBottom: "2px" },
};

// A vertically-stacked SVG funnel: each band's TOP edge matches the previous
// stage's bottom width and whose bottom edge scales with this stage's count, so
// the shape NARROWS monotonically from the top stage (full width) to the win.
// Each band carries its stage label + COUNT inline; HOVERING a band raises a
// tooltip with the absolute number + step-conversion %. SVG so the narrowing
// geometry is exact and the hover hit-area is the whole trapezoid.
//
// `stages` lets a caller pass the canonical stage ORDER (the ad funnel differs
// from the lead funnel); defaults to the lead funnel order from analytics.
export function FunnelDiagram({
    funnel,
    top,
    stages: order = [
        "uploaded",
        "dialed",
        "connected",
        "interested",
        "warm",
        "hot",
        "booked",
        "converted",
    ],
}: {
    funnel: FunnelStage[];
    top: number;
    stages?: string[];
}) {
    const [hover, setHover] = useState<number | null>(null);

    // Order the stages canonically; missing stages render as 0-width slivers.
    const byStage = new Map(funnel.map((f) => [f.stage, f]));
    const stages = order
        .map((s) => byStage.get(s) ?? { stage: s, count: 0, pct_of_top: 0, step_conv: 0 })
        .map((s, i) => ({ ...s, color: FUNNEL_COLORS[i % FUNNEL_COLORS.length] }));

    const W = 100; // viewBox width units
    const rowH = 40; // px per band
    const gap = 6;
    const H = stages.length * rowH + (stages.length - 1) * gap;
    const minW = 12; // floor width % so a tiny/zero stage is still a visible sliver

    // Width (in viewBox units) for a given count, floored so labels stay readable.
    const widthFor = (count: number) => Math.max(minW, (count / (top || 1)) * W);

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

// ============================================================================
// StageBreakdownBar — the VOICE per-turn "Stage breakdown" stacked bar, reused.
//
// The founder loves the voice latency view: each metrics-table ROW carries a
// horizontal SEGMENTED stacked bar (blue/orange/purple/green = STT / Turn-detect
// / LLM / TTS), where every segment's WIDTH is that stage's share of the row
// total. This component reproduces that exact visual language so the Ad-Engine
// tables read 1:1 with the voice table:
//   • one rounded-full, overflow-hidden flex track (h-2.5)
//   • N inline segments, each width = value / total * 100% (floored so a tiny
//     non-zero stage stays a visible sliver, like the voice bar)
//   • hover raises a token-styled tooltip (the funnel/analytics chartTooltip
//     vocabulary) with the segment label + value + its share %
//   • a tiny dotted legend underneath (same dot vocabulary as the spend-mix
//     donut legend), optional.
//
// Colour discipline (HARD RULE — pixel-identical, zero raw hex): the four voice
// stages map to the SAME brand primary tokens the rest of the page uses, in the
// voice order blue→orange→purple→green ≈ primary-01 → primary-05 → primary-02 →
// primary-04. A caller that passes its own per-segment `color` (e.g. the 7-stage
// funnel ramp from FUNNEL_COLORS) overrides them, so the SAME bar renders either
// the 4-stage voice palette OR the ad funnel ramp without changing geometry.
// ============================================================================

// One stacked-bar segment — value drives the width, label/color the look.
export type StageSegment = {
    key: string;
    label: string;
    value: number; // share is value / Σvalue
    color?: string; // optional token override; defaults to the voice palette by index
};

// The VOICE stage palette in its canonical order (STT / Turn-detect / LLM / TTS)
// expressed in brand tokens — blue → orange → purple → green. Reused verbatim so
// a 4-segment bar with no per-segment colour looks exactly like the voice bar.
export const STAGE_COLORS: string[] = [
    "var(--primary-01)", // STT       (clay/blue anchor)
    "var(--primary-05)", // Turn-detect (warm Manilla — the "orange" stage)
    "var(--primary-02)", // LLM       (the "purple" cool stage)
    "var(--primary-04)", // TTS       (the "green" stage)
];

export function StageBreakdownBar({
    segments,
    height = "h-2.5",
    showLegend = false,
}: {
    segments: StageSegment[];
    height?: string; // bar thickness token; voice default is h-2.5
    showLegend?: boolean;
}) {
    const [hover, setHover] = useState<number | null>(null);

    const total = useMemo(
        () => segments.reduce((s, x) => s + (x.value > 0 ? x.value : 0), 0),
        [segments],
    );

    // Empty / all-zero → a calm flat track (never a divide-by-zero), so a row with
    // no spend yet still aligns with the rest of the column.
    if (total <= 0) {
        return (
            <div className={`w-full ${height} rounded-full bg-b-surface1`} aria-hidden />
        );
    }

    const minPct = 2; // floor % so a tiny non-zero stage stays a visible sliver

    return (
        <div className="relative">
            <div
                className={`flex w-full ${height} overflow-hidden rounded-full bg-b-surface1`}
            >
                {segments.map((s, i) => {
                    const raw = s.value > 0 ? s.value : 0;
                    if (raw <= 0) return null;
                    const pct = Math.max(minPct, (raw / total) * 100);
                    const color = s.color ?? STAGE_COLORS[i % STAGE_COLORS.length];
                    const dim = hover != null && hover !== i;
                    return (
                        <div
                            key={s.key}
                            className="h-full first:rounded-l-full last:rounded-r-full transition-opacity duration-150"
                            style={{ width: `${pct}%`, background: color, opacity: dim ? 0.4 : 1 }}
                            onMouseEnter={() => setHover(i)}
                            onMouseLeave={() => setHover(null)}
                        />
                    );
                })}
            </div>

            {/* Hover tooltip — same token vocabulary as the funnel/chartTooltip. */}
            {hover != null && segments[hover] && (
                <div className="pointer-events-none absolute left-0 -top-1 z-20 -translate-y-full px-3 py-2 rounded-xl bg-b-surface2 border border-s-stroke2 shadow-depth text-caption whitespace-nowrap">
                    <div className="flex items-center gap-1.5 text-t-primary font-medium">
                        <span
                            className="size-2 rounded-full shrink-0"
                            style={{
                                background:
                                    segments[hover].color ??
                                    STAGE_COLORS[hover % STAGE_COLORS.length],
                            }}
                        />
                        {segments[hover].label}
                    </div>
                    <div className="mt-0.5 text-t-secondary tabular-nums">
                        {Math.round((segments[hover].value / total) * 100)}% of total
                    </div>
                </div>
            )}

            {/* Optional dotted legend — mirrors the spend-mix donut legend dots. */}
            {showLegend && (
                <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1">
                    {segments.map((s, i) => (
                        <div key={s.key} className="flex items-center gap-1.5 text-caption">
                            <span
                                className="size-2 rounded-full shrink-0"
                                style={{ background: s.color ?? STAGE_COLORS[i % STAGE_COLORS.length] }}
                            />
                            <span className="text-t-tertiary">{s.label}</span>
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
}
