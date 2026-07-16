"use client";

// Famit Research — scientific visualisations (parallel to app/_dashboard-charts.tsx).
// All on-brand (Anthropic clay palette, --chart-* / --text-* CSS vars), all REAL filter output.
// The signature widget is AffectTrace: a smooth latent Arousal/Friction line drawn WITH its
// Kalman ±1σ uncertainty band (the honest "this is a measurement, here is its error" view) plus
// per-turn regime markers — the visual payoff of the SciML pitch with none of the fake physics.

import { useMemo } from "react";
import {
    Area,
    Bar,
    BarChart,
    CartesianGrid,
    ComposedChart,
    Line,
    LineChart,
    ReferenceDot,
    ReferenceLine,
    ResponsiveContainer,
    Tooltip,
    XAxis,
    YAxis,
} from "recharts";
import type { ResearchTurn } from "@/lib/api";
import { bandData, C, regimeMeta, riskCurve, type BandPoint } from "./_lib";

const TOOLTIP = {
    contentStyle: {
        background: "var(--backgrounds-surface2)",
        border: "1px solid var(--stroke-stroke2)",
        borderRadius: "12px",
        boxShadow: "var(--box-shadow-dropdown)",
        fontSize: "12px",
    },
    labelStyle: { color: "var(--text-tertiary)", marginBottom: "2px" },
    itemStyle: { color: "var(--text-primary)" },
};

const AXIS = { fontSize: 11, fill: "var(--text-tertiary)" } as const;
const axisLine = { stroke: "var(--stroke-stroke2)" };

// ── Confidence / provenance badge ────────────────────────────────────────────
// Honesty made visible: every metric panel shows HOW it was measured and how confident we are.
export function ConfidenceBadge({
    source,
    confidence,
    lowConf,
}: {
    source: string;
    confidence: number;
    lowConf?: boolean;
}) {
    const pct = Math.round((confidence || 0) * 100);
    const warn = lowConf || pct < 45;
    return (
        <span
            className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-medium"
            style={{
                background: warn ? "color-mix(in srgb, var(--primary-05) 35%, transparent)" : "var(--backgrounds-surface3)",
                color: "var(--text-secondary)",
            }}
            title={
                warn
                    ? "Low-confidence: narrow-band (8 kHz) telephony degrades fine acoustic estimates. Treat as exploratory."
                    : "Feature confidence from voiced fraction and sample rate."
            }
        >
            <span className="size-1.5 rounded-full" style={{ background: warn ? "var(--primary-03)" : "var(--chart-green)" }} />
            {source} · {pct}% conf
            {warn ? " · low-conf" : ""}
        </span>
    );
}

export function RegimeChip({ regime, small }: { regime: string; small?: boolean }) {
    const m = regimeMeta(regime);
    return (
        <span
            className={`inline-flex items-center gap-1.5 rounded-full font-medium ${small ? "px-2 py-0.5 text-[10px]" : "px-2.5 py-1 text-[11px]"}`}
            style={{ background: `color-mix(in srgb, ${m.color} 16%, transparent)`, color: "var(--text-secondary)" }}
            title={m.desc}
        >
            <span className="size-1.5 rounded-full" style={{ background: m.color }} />
            {m.label}
        </span>
    );
}

type BandTooltipProps = {
    active?: boolean;
    payload?: Array<{ payload: BandPoint }>;
    color: string;
};

function BandTooltip({ active, payload, color }: BandTooltipProps) {
    if (!active || !payload?.length) return null;
    const p: BandPoint = payload[0]?.payload;
    if (!p) return null;
    const sigma = Math.round((p.span / 2) * 10) / 10;
    const m = regimeMeta(p.regime);
    return (
        <div style={TOOLTIP.contentStyle as React.CSSProperties}>
            <div style={TOOLTIP.labelStyle}>Turn {p.turn} · {p.t.toFixed(1)}s</div>
            <div className="font-medium" style={{ color }}>
                {p.center.toFixed(1)} <span className="text-t-tertiary">± {sigma}</span>
            </div>
            <div className="mt-1 flex items-center gap-1.5 text-[11px]" style={{ color: "var(--text-tertiary)" }}>
                <span className="size-1.5 rounded-full" style={{ background: m.color }} />
                {m.label} · {Math.round(p.confidence * 100)}% conf
            </div>
        </div>
    );
}

// ── AffectTrace — latent state with ±1σ uncertainty band + baseline + regime dots ────────────
export function AffectTrace({
    turns,
    kind,
    height = 260,
}: {
    turns: ResearchTurn[];
    kind: "arousal" | "friction" | "engagement";
    height?: number;
}) {
    const color = kind === "arousal" ? C.arousal : kind === "friction" ? C.friction : C.engagement;
    const data = useMemo(
        () => bandData(turns, kind, `${kind}_var` as "arousal_var" | "friction_var" | "engagement_var"),
        [turns, kind]
    );
    return (
        <div style={{ height }}>
            <ResponsiveContainer width="100%" height="100%">
                <ComposedChart data={data} margin={{ top: 8, right: 10, bottom: 4, left: -18 }}>
                    <CartesianGrid stroke="var(--stroke-stroke2)" strokeDasharray="3 3" vertical={false} />
                    <XAxis dataKey="t" tick={AXIS} axisLine={axisLine} tickLine={false}
                        tickFormatter={(v) => `${Math.round(v)}s`} />
                    <YAxis domain={[0, 100]} ticks={[0, 25, 50, 75, 100]} tick={AXIS} axisLine={false} tickLine={false} />
                    <ReferenceLine y={50} stroke="var(--text-tertiary)" strokeDasharray="4 4"
                        label={{ value: "baseline", position: "insideLeft", fontSize: 10, fill: "var(--text-tertiary)" }} />
                    {/* ±1σ band via the stacked-area trick (invisible lo + translucent span) */}
                    <Area dataKey="lo" stackId="b" stroke="none" fill="transparent" isAnimationActive={false} />
                    <Area dataKey="span" stackId="b" stroke="none" fill={color} fillOpacity={0.14} isAnimationActive={false} />
                    <Line dataKey="center" stroke={color} strokeWidth={2.25} dot={false} isAnimationActive={false} />
                    <Tooltip content={<BandTooltip color={color} />} />
                </ComposedChart>
            </ResponsiveContainer>
        </div>
    );
}

// ── Conversion-risk curve (Phase 2) with the conformal intervene marker ──────
export function ConversionRiskCurve({ turns, height = 240 }: { turns: ResearchTurn[]; height?: number }) {
    const data = useMemo(() => riskCurve(turns), [turns]);
    const firstFire = data.find((d) => d.intervene);
    const hasRisk = data.some((d) => d.risk > 0);
    if (!hasRisk)
        return <div className="flex h-[240px] items-center justify-center text-caption text-t-tertiary">No conversion-risk scored yet.</div>;
    return (
        <div style={{ height }}>
            <ResponsiveContainer width="100%" height="100%">
                <ComposedChart data={data} margin={{ top: 8, right: 10, bottom: 4, left: -18 }}>
                    <defs>
                        <linearGradient id="risk-grad" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="0%" stopColor={C.risk} stopOpacity="0.28" />
                            <stop offset="100%" stopColor={C.risk} stopOpacity="0.02" />
                        </linearGradient>
                    </defs>
                    <CartesianGrid stroke="var(--stroke-stroke2)" strokeDasharray="3 3" vertical={false} />
                    <XAxis dataKey="t" tick={AXIS} axisLine={axisLine} tickLine={false} tickFormatter={(v) => `${Math.round(v)}s`} />
                    <YAxis domain={[0, 100]} ticks={[0, 25, 50, 75, 100]} tick={AXIS} axisLine={false} tickLine={false} />
                    <Area dataKey="risk" stroke="none" fill="url(#risk-grad)" isAnimationActive={false} />
                    <Line dataKey="risk" stroke={C.risk} strokeWidth={2.25} dot={false} isAnimationActive={false} />
                    {firstFire && (
                        <ReferenceLine x={firstFire.t} stroke="var(--primary-03)" strokeDasharray="4 4"
                            label={{ value: "intervene", position: "top", fontSize: 10, fill: "var(--primary-03)" }} />
                    )}
                    {firstFire && <ReferenceDot x={firstFire.t} y={firstFire.risk} r={4} fill="var(--primary-03)" stroke="none" />}
                    <Tooltip {...TOOLTIP} formatter={(v: number) => [`${Math.round(v)}`, "risk"]} />
                </ComposedChart>
            </ResponsiveContainer>
        </div>
    );
}

export function IntentChip({ intent, small }: { intent?: string; small?: boolean }) {
    if (!intent) return null;
    const danger = ["objecting", "price-resistant", "annoyed"].includes(intent);
    const warn = intent === "hesitant";
    const color = danger ? "var(--primary-03)" : warn ? "var(--primary-05)" : intent === "interested" ? "var(--chart-green)" : "var(--text-tertiary)";
    return (
        <span className={`inline-flex items-center gap-1.5 rounded-full font-medium capitalize ${small ? "px-2 py-0.5 text-[10px]" : "px-2.5 py-1 text-[11px]"}`}
            style={{ background: `color-mix(in srgb, ${color} 16%, transparent)`, color: "var(--text-secondary)" }}>
            <span className="size-1.5 rounded-full" style={{ background: color }} />
            {intent.replace("-", " ")}
        </span>
    );
}

// ── Pitch contour (F0 mean, voiced) ──────────────────────────────────────────
export function PitchContour({ turns, height = 200 }: { turns: ResearchTurn[]; height?: number }) {
    const data = useMemo(
        () => (turns || []).map((t) => ({ t: t.t_sec, f0: t.f0_mean_hz || null })),
        [turns]
    );
    const hasF0 = data.some((d) => d.f0 && d.f0 > 0);
    if (!hasF0)
        return (
            <div className="flex h-[200px] flex-col items-center justify-center text-center text-caption text-t-tertiary">
                No acoustic pitch on this call yet.
                <span className="mt-1 max-w-xs text-[11px]">
                    Pitch/loudness come from the <b>post-call</b> acoustic pass (pYIN over the recording). The in-call signal is speech-rate + pauses only.
                </span>
            </div>
        );
    return (
        <div style={{ height }}>
            <ResponsiveContainer width="100%" height="100%">
                <LineChart data={data} margin={{ top: 8, right: 10, bottom: 4, left: -10 }}>
                    <CartesianGrid stroke="var(--stroke-stroke2)" strokeDasharray="3 3" vertical={false} />
                    <XAxis dataKey="t" tick={AXIS} axisLine={axisLine} tickLine={false} tickFormatter={(v) => `${Math.round(v)}s`} />
                    <YAxis tick={AXIS} axisLine={false} tickLine={false} unit="Hz" width={48} />
                    <Line dataKey="f0" stroke={C.pitch} strokeWidth={2.25} dot={false} connectNulls isAnimationActive={false} />
                    <Tooltip {...TOOLTIP} />
                </LineChart>
            </ResponsiveContainer>
        </div>
    );
}

// ── Prosody mini-bars (speech rate, pause ratio) ─────────────────────────────
export function ProsodyBars({
    turns,
    metric,
    height = 180,
}: {
    turns: ResearchTurn[];
    metric: "speech_rate_sps" | "pause_ratio";
    height?: number;
}) {
    const color = metric === "speech_rate_sps" ? C.rate : C.pause;
    const data = useMemo(
        () => (turns || []).map((t) => ({ turn: t.turn_num, v: Math.round((t[metric] as number) * 100) / 100 })),
        [turns, metric]
    );
    return (
        <div style={{ height }}>
            <ResponsiveContainer width="100%" height="100%">
                <BarChart data={data} margin={{ top: 8, right: 10, bottom: 4, left: -18 }}>
                    <CartesianGrid stroke="var(--stroke-stroke2)" strokeDasharray="3 3" vertical={false} />
                    <XAxis dataKey="turn" tick={AXIS} axisLine={axisLine} tickLine={false} />
                    <YAxis tick={AXIS} axisLine={false} tickLine={false} />
                    <Bar dataKey="v" fill={color} radius={[4, 4, 0, 0]} isAnimationActive={false} />
                    <Tooltip {...TOOLTIP} cursor={{ fill: "var(--stroke-subtle)" }} />
                </BarChart>
            </ResponsiveContainer>
        </div>
    );
}

// ── Regime strip — one cell per turn, coloured by detected regime ────────────
export function RegimeStrip({ turns }: { turns: ResearchTurn[] }) {
    return (
        <div className="flex flex-wrap gap-1">
            {(turns || []).map((t) => {
                const m = regimeMeta(t.regime);
                return (
                    <div
                        key={t.turn_num}
                        title={`Turn ${t.turn_num} · ${m.label} — ${m.desc}`}
                        className="h-7 flex-1 min-w-[14px] rounded-md transition-transform hover:scale-y-110"
                        style={{ background: t.regime === "steady" ? "var(--stroke-stroke2)" : m.color, opacity: t.regime === "steady" ? 0.5 : 0.9 }}
                    />
                );
            })}
        </div>
    );
}

// ── Outcomes Lab correlation — won vs lost trajectory shape ──────────────────
// The closed-loop centrepiece (descriptive, on real held-out calls): do callers who CONVERT show a
// different friction/arousal trajectory than those who don't? Grouped bars make the contrast legible.
export function OutcomeCorrelation({
    won,
    lost,
    height = 240,
}: {
    won: { avg_friction_peak: number; avg_arousal_trend: number; avg_friction_trend: number };
    lost: { avg_friction_peak: number; avg_arousal_trend: number; avg_friction_trend: number };
    height?: number;
}) {
    const data = [
        { metric: "Peak friction", Won: won.avg_friction_peak, Lost: lost.avg_friction_peak },
        { metric: "Arousal trend", Won: won.avg_arousal_trend, Lost: lost.avg_arousal_trend },
        { metric: "Friction trend", Won: won.avg_friction_trend, Lost: lost.avg_friction_trend },
    ];
    return (
        <div style={{ height }}>
            <ResponsiveContainer width="100%" height="100%">
                <BarChart data={data} margin={{ top: 8, right: 10, bottom: 4, left: -18 }}>
                    <CartesianGrid stroke="var(--stroke-stroke2)" strokeDasharray="3 3" vertical={false} />
                    <XAxis dataKey="metric" tick={AXIS} axisLine={axisLine} tickLine={false} />
                    <YAxis tick={AXIS} axisLine={false} tickLine={false} />
                    <ReferenceLine y={0} stroke="var(--text-tertiary)" />
                    <Bar dataKey="Won" fill={C.arousal} radius={[4, 4, 0, 0]} isAnimationActive={false} />
                    <Bar dataKey="Lost" fill={C.friction} radius={[4, 4, 0, 0]} isAnimationActive={false} />
                    <Tooltip {...TOOLTIP} cursor={{ fill: "var(--stroke-subtle)" }} />
                </BarChart>
            </ResponsiveContainer>
        </div>
    );
}

// ── Regime counts (horizontal mini-bars) ─────────────────────────────────────
export function RegimeCounts({ counts }: { counts: Record<string, number> }) {
    const entries = Object.entries(counts || {}).sort((a, b) => b[1] - a[1]);
    const max = Math.max(1, ...entries.map(([, v]) => v));
    if (!entries.length)
        return <div className="py-6 text-center text-caption text-t-tertiary">No regime events in range.</div>;
    return (
        <div className="space-y-3">
            {entries.map(([k, v]) => {
                const m = regimeMeta(k);
                return (
                    <div key={k} className="flex items-center gap-3">
                        <div className="w-28 shrink-0 text-caption text-t-secondary">{m.label}</div>
                        <div className="h-2.5 flex-1 overflow-hidden rounded-full" style={{ background: "var(--stroke-stroke2)" }}>
                            <div className="h-full rounded-full" style={{ width: `${(v / max) * 100}%`, background: m.color }} />
                        </div>
                        <div className="w-8 text-right text-caption tabular-nums text-t-primary">{v}</div>
                    </div>
                );
            })}
        </div>
    );
}
