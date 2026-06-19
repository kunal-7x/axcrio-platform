"use client";

// Dashboard premium chart helpers (B1). Small, self-contained widgets that give
// the home cockpit VARIED chart types beyond bars — a center-total donut, a
// radial progress gauge, and a calls-by-hour heatmap — all on-brand (theme CSS
// vars), all REAL-data driven, all built from recharts + plain SVG. Reused only
// by app/page.tsx; nothing existing is changed. No new UI primitives invented —
// these are thin compositions over recharts + the existing Card chrome.

import { useMemo } from "react";
import {
    ResponsiveContainer,
    PieChart,
    Pie,
    Cell,
    Tooltip,
    RadialBarChart,
    RadialBar,
    PolarAngleAxis,
} from "recharts";

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

// ── Center-total donut ──────────────────────────────────────────────────────
// A premium donut with the grand total + caption rendered in the hole. Used for
// lead-temperature; each slice carries its own brand color + a tidy legend with
// counts. Replaces the plain pie — same data, richer read.
export type DonutSlice = { name: string; value: number; color: string };

export function CenterDonut({
    data,
    total,
    centerLabel,
}: {
    data: DonutSlice[];
    total: number;
    centerLabel: string;
}) {
    return (
        <div className="flex items-center gap-4 max-sm:flex-col">
            <div className="relative h-44 w-44 shrink-0 max-sm:h-40 max-sm:w-40">
                <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                        <Pie
                            data={data}
                            dataKey="value"
                            nameKey="name"
                            cx="50%"
                            cy="50%"
                            innerRadius="68%"
                            outerRadius="100%"
                            paddingAngle={2}
                            stroke="none"
                            startAngle={90}
                            endAngle={-270}
                        >
                            {data.map((d, i) => (
                                <Cell key={i} fill={d.color} />
                            ))}
                        </Pie>
                        <Tooltip {...TOOLTIP} />
                    </PieChart>
                </ResponsiveContainer>
                <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
                    <div className="text-h4 text-t-primary tabular-nums leading-none">
                        {total.toLocaleString()}
                    </div>
                    <div className="mt-1 text-caption text-t-tertiary">{centerLabel}</div>
                </div>
            </div>
            <div className="flex-1 space-y-2.5 min-w-0">
                {data.map((d) => {
                    const pct = total > 0 ? Math.round((d.value / total) * 100) : 0;
                    return (
                        <div key={d.name} className="flex items-center gap-2.5">
                            <span
                                className="size-2.5 shrink-0 rounded-full"
                                style={{ background: d.color }}
                            />
                            <span className="flex-1 truncate text-caption text-t-secondary">
                                {d.name}
                            </span>
                            <span className="text-caption text-t-primary tabular-nums font-medium">
                                {d.value.toLocaleString()}
                            </span>
                            <span className="w-9 text-right text-caption text-t-tertiary tabular-nums">
                                {pct}%
                            </span>
                        </div>
                    );
                })}
            </div>
        </div>
    );
}

// ── Radial progress gauge ───────────────────────────────────────────────────
// A single-arc radial gauge (value / cap) with the value + caption in the hole.
// Used for Bookings and Callbacks "of total calls" — a calmer alternative to a
// bar that fills the right column nicely.
export function RadialGauge({
    value,
    max,
    label,
    suffix,
    color = "var(--primary-01)",
}: {
    value: number;
    max: number;
    label: string;
    suffix?: string;
    color?: string;
}) {
    const cap = max > 0 ? max : 1;
    const data = [{ name: label, value: Math.min(value, cap), fill: color }];
    const pct = max > 0 ? Math.round((value / max) * 100) : 0;
    return (
        <div className="relative h-32">
            <ResponsiveContainer width="100%" height="100%">
                <RadialBarChart
                    innerRadius="72%"
                    outerRadius="100%"
                    data={data}
                    startAngle={210}
                    endAngle={-30}
                    barSize={9}
                >
                    <PolarAngleAxis
                        type="number"
                        domain={[0, cap]}
                        angleAxisId={0}
                        tick={false}
                    />
                    <RadialBar
                        background={{ fill: "var(--stroke-stroke2)" }}
                        dataKey="value"
                        cornerRadius={9}
                    />
                </RadialBarChart>
            </ResponsiveContainer>
            <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
                <div className="text-h5 text-t-primary tabular-nums leading-none">
                    {value.toLocaleString()}
                </div>
                <div className="mt-1 text-caption text-t-tertiary">
                    {label}
                    {suffix ? ` · ${suffix}` : pct > 0 ? ` · ${pct}%` : ""}
                </div>
            </div>
        </div>
    );
}

// ── Calls-by-hour heatmap ───────────────────────────────────────────────────
// A 24-cell day strip (IST hours) colored by call volume — instantly shows when
// the agent is busiest. Plain CSS grid + opacity ramp (no recharts), so it stays
// crisp at small sizes and matches the brand without a new dependency.
const HOUR_LABELS = [0, 6, 12, 18];

export function CallsHeatmap({ buckets }: { buckets: number[] }) {
    const max = useMemo(() => Math.max(1, ...buckets), [buckets]);
    return (
        <div>
            <div className="grid grid-cols-12 gap-1.5">
                {buckets.map((n, h) => {
                    const intensity = n / max; // 0..1
                    const bg =
                        n === 0
                            ? "var(--stroke-stroke2)"
                            : `color-mix(in srgb, var(--primary-01) ${Math.round(
                                  18 + intensity * 82
                              )}%, transparent)`;
                    return (
                        <div
                            key={h}
                            title={`${String(h).padStart(2, "0")}:00 — ${n} call${
                                n === 1 ? "" : "s"
                            }`}
                            className="group relative aspect-square rounded-md transition-transform hover:scale-110"
                            style={{ background: bg }}
                        >
                            {n > 0 && (
                                <span className="absolute inset-0 flex items-center justify-center text-[10px] font-medium tabular-nums text-t-primary opacity-0 group-hover:opacity-100">
                                    {n}
                                </span>
                            )}
                        </div>
                    );
                })}
            </div>
            <div className="mt-2 flex justify-between px-0.5 text-[10px] text-t-tertiary tabular-nums">
                {HOUR_LABELS.map((h) => (
                    <span key={h}>{String(h).padStart(2, "0")}h</span>
                ))}
                <span>23h</span>
            </div>
        </div>
    );
}
