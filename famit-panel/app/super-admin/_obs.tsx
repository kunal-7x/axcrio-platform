"use client";

// Shared toolkit for the native, white-labeled observability dashboards (System Logs + Performance).
// Time-range + service "variables" (Grafana-style), a panel chrome, and recharts chart primitives
// (multi-series time-series, donut, bar-list) — all on the core design tokens. No vendor branding.

import { useEffect, useMemo, useRef, useState, useCallback } from "react";
import {
    ResponsiveContainer, AreaChart, Area, LineChart, Line, XAxis, YAxis, Tooltip,
    CartesianGrid, PieChart, Pie, Cell,
} from "recharts";
import Icon from "@/components/Icon";
import Select from "@/components/Select";
import { getObsServices, type ObsRow } from "@/lib/api";
import type { SelectOption } from "@/types/select";

// ── number/time helpers (ClickHouse returns numbers as strings) ───────────────
export const n = (v: unknown): number => {
    const x = typeof v === "number" ? v : Number(v);
    return Number.isFinite(x) ? x : 0;
};
export const fmtNum = (v: number): string => {
    if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}M`;
    if (v >= 1_000) return `${(v / 1_000).toFixed(1)}k`;
    return `${Math.round(v)}`;
};
export const fmtMs = (ms: number): string => (ms >= 1000 ? `${(ms / 1000).toFixed(2)}s` : `${ms.toFixed(ms < 10 ? 1 : 0)}ms`);
export const fmtClock = (msOrSec: number): string => {
    const ms = msOrSec > 1e12 ? msOrSec : msOrSec * 1000;
    try { return new Date(ms).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }); } catch { return ""; }
};
export const fmtDateTime = (ms: number): string => {
    try { return new Date(ms).toLocaleString(); } catch { return ""; }
};
export const agoMs = (ms: number): string => {
    const s = Math.max(0, (Date.now() - ms) / 1000);
    if (s < 60) return `${Math.floor(s)}s ago`;
    if (s < 3600) return `${Math.floor(s / 60)}m ago`;
    if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
    return `${Math.floor(s / 86400)}d ago`;
};

// recharts series palette (theme-ish, distinct)
export const SERIES = ["#2A85FF", "#8E59FF", "#00A656", "#EF9D0E", "#FF6A55", "#2BC8B4", "#EC4899", "#6C72FF"];

export function statusTone(code: string | number): string {
    const c = String(code);
    if (c.startsWith("2")) return "#00A656";
    if (c.startsWith("3")) return "#2A85FF";
    if (c.startsWith("4")) return "#EF9D0E";
    if (c.startsWith("5")) return "#FF6A55";
    return "#9A9FA5";
}

const CHART_TOOLTIP = {
    contentStyle: {
        background: "var(--backgrounds-surface2)", border: "1px solid var(--stroke-stroke2)",
        borderRadius: "12px", boxShadow: "var(--box-shadow-dropdown)", fontSize: "12px",
    },
    labelStyle: { color: "var(--text-tertiary)", marginBottom: "2px" },
    itemStyle: { color: "var(--text-primary)" },
};

// ── time-range (Grafana-style variable) ───────────────────────────────────────
export const TIME_RANGES: { id: number; name: string; minutes: number }[] = [
    { id: 1, name: "Last 15 min", minutes: 15 },
    { id: 2, name: "Last 1 hour", minutes: 60 },
    { id: 3, name: "Last 6 hours", minutes: 360 },
    { id: 4, name: "Last 24 hours", minutes: 1440 },
    { id: 5, name: "Last 7 days", minutes: 10080 },
];

const ALL_SERVICES: SelectOption = { id: 0, name: "All services" };

export function useObsControls(defaultRangeId = 2) {
    // resolve the default by id (robust to reordering TIME_RANGES), not array index
    const def = useMemo(() => TIME_RANGES.find((r) => r.id === defaultRangeId) ?? TIME_RANGES[1], [defaultRangeId]);
    const [range, setRange] = useState<SelectOption>(def);
    const [service, setService] = useState<SelectOption>(ALL_SERVICES);
    const [services, setServices] = useState<SelectOption[]>([ALL_SERVICES]);
    const minutes = useMemo(() => TIME_RANGES.find((r) => r.id === range.id)?.minutes ?? 60, [range]);
    const svc = service.id === 0 ? "" : String(service.name);

    useEffect(() => {
        getObsServices(10080).then((r) => {
            const opts = (r.rows || []).map((row, i) => ({ id: i + 1, name: String(row.service) }));
            // reuse the SAME ALL_SERVICES object reference so the Listbox keeps its selected marker
            setServices([ALL_SERVICES, ...opts]);
        }).catch(() => {});
    }, []);

    return { range, setRange, service, setService, services, minutes, svc };
}

export function ObsControls({ c, right }: { c: ReturnType<typeof useObsControls>; right?: React.ReactNode }) {
    return (
        <div className="flex items-center gap-3 mb-5 flex-wrap">
            <Select className="min-w-44" value={c.service} onChange={c.setService} options={c.services} />
            <Select className="min-w-40" value={c.range} onChange={c.setRange} options={TIME_RANGES} />
            {right}
        </div>
    );
}

// ── panel chrome ──────────────────────────────────────────────────────────────
export function Panel({ title, subtitle, actions, children, className }: {
    title: string; subtitle?: string; actions?: React.ReactNode; children: React.ReactNode; className?: string;
}) {
    return (
        <div className={`rounded-3xl bg-b-surface2 ring-1 ring-s-subtle ring-inset ${className || ""}`}>
            <div className="flex items-center justify-between gap-3 px-4 py-3 border-b border-s-subtle">
                <div className="min-w-0">
                    <div className="text-button text-t-primary truncate">{title}</div>
                    {subtitle && <div className="text-caption text-t-tertiary truncate">{subtitle}</div>}
                </div>
                {actions}
            </div>
            <div className="p-3">{children}</div>
        </div>
    );
}

export function EmptyChart({ msg = "No data in this window" }: { msg?: string }) {
    return <div className="h-full grid place-items-center text-caption text-t-tertiary py-10">{msg}</div>;
}

// ── time-series (multi-series area or line) ───────────────────────────────────
export type TSeries = { key: string; label: string; color: string; area?: boolean };

export function TimeSeries({ data, series, unit = "", height = 220 }: {
    data: Record<string, number>[]; series: TSeries[]; unit?: string; height?: number;
}) {
    if (!data.length) return <div style={{ height }}><EmptyChart /></div>;
    const useArea = series.some((s) => s.area);
    const Chart = useArea ? AreaChart : LineChart;
    return (
        <div style={{ height }}>
            <ResponsiveContainer width="100%" height="100%">
                <Chart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
                    <defs>
                        {series.map((s) => (
                            <linearGradient key={s.key} id={`grad-${s.key}`} x1="0" y1="0" x2="0" y2="1">
                                <stop offset="0%" stopColor={s.color} stopOpacity={0.3} />
                                <stop offset="100%" stopColor={s.color} stopOpacity={0} />
                            </linearGradient>
                        ))}
                    </defs>
                    <CartesianGrid stroke="var(--stroke-stroke2)" strokeDasharray="3 3" vertical={false} />
                    <XAxis dataKey="t" tickFormatter={(v) => fmtClock(Number(v))} minTickGap={50}
                        tick={{ fontSize: 11, fill: "var(--text-tertiary)" }} stroke="var(--stroke-stroke2)" />
                    <YAxis tick={{ fontSize: 11, fill: "var(--text-tertiary)" }} stroke="var(--stroke-stroke2)"
                        width={46} unit={unit} />
                    <Tooltip {...CHART_TOOLTIP} labelFormatter={(v) => fmtClock(Number(v))} />
                    {series.map((s) =>
                        useArea ? (
                            <Area key={s.key} type="monotone" dataKey={s.key} name={s.label} stroke={s.color}
                                strokeWidth={2} fill={`url(#grad-${s.key})`} isAnimationActive={false} />
                        ) : (
                            <Line key={s.key} type="monotone" dataKey={s.key} name={s.label} stroke={s.color}
                                strokeWidth={2} dot={false} isAnimationActive={false} />
                        )
                    )}
                </Chart>
            </ResponsiveContainer>
        </div>
    );
}

// ── donut (name/value/color) ──────────────────────────────────────────────────
export function Donut({ data, total, centerLabel, height = 220 }: {
    data: { name: string; value: number; color: string }[]; total?: number; centerLabel?: string; height?: number;
}) {
    const sum = total ?? data.reduce((a, b) => a + b.value, 0);
    if (!data.length) return <div style={{ height }}><EmptyChart /></div>;
    return (
        <div className="flex items-center gap-4 max-sm:flex-col" style={{ minHeight: height }}>
            <div className="relative h-44 w-44 shrink-0">
                <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                        <Pie data={data} dataKey="value" nameKey="name" cx="50%" cy="50%"
                            innerRadius="66%" outerRadius="100%" paddingAngle={2} stroke="none"
                            startAngle={90} endAngle={-270} isAnimationActive={false}>
                            {data.map((d, i) => <Cell key={i} fill={d.color} />)}
                        </Pie>
                        <Tooltip {...CHART_TOOLTIP} />
                    </PieChart>
                </ResponsiveContainer>
                <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
                    <div className="text-h5 text-t-primary tabular-nums leading-none">{fmtNum(sum)}</div>
                    {centerLabel && <div className="mt-1 text-caption text-t-tertiary">{centerLabel}</div>}
                </div>
            </div>
            <div className="flex-1 space-y-2 min-w-0 max-h-44 max-sm:max-h-none overflow-y-auto w-full">
                {data.map((d) => (
                    <div key={d.name} className="flex items-center gap-2.5">
                        <span className="size-2.5 shrink-0 rounded-full" style={{ background: d.color }} />
                        <span className="flex-1 truncate text-caption text-t-secondary">{d.name}</span>
                        <span className="text-caption text-t-primary tabular-nums font-medium">{fmtNum(d.value)}</span>
                        <span className="w-10 text-right text-caption text-t-tertiary tabular-nums">
                            {sum > 0 ? Math.round((d.value / sum) * 100) : 0}%
                        </span>
                    </div>
                ))}
            </div>
        </div>
    );
}

// ── refresh control (auto + manual) ───────────────────────────────────────────
export function useAutoRefresh(fn: () => void, ms = 30000) {
    const saved = useRef(fn);
    saved.current = fn;
    const [on, setOn] = useState(true);
    useEffect(() => {
        if (!on) return;
        const id = setInterval(() => saved.current(), ms);
        return () => clearInterval(id);
    }, [on, ms]);
    const Toggle = useCallback(() => (
        <button onClick={() => setOn((o) => !o)}
            className={`inline-flex items-center gap-1.5 h-9 px-3 rounded-full text-caption border transition-colors ${
                on ? "border-s-stroke2 text-t-primary" : "border-s-subtle text-t-tertiary"}`}>
            <Icon name="clock" className="size-3.5 fill-current" />
            {on ? "Auto" : "Paused"}
        </button>
    ), [on]);
    return Toggle;
}
