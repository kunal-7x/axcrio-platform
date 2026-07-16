"use client";

// ============================================================
// Performance — /super-admin/performance
// A native, white-labeled APM + infrastructure dashboard (Grafana-grade) over the observability
// backend: service + time-range variables, RED time-series, status/service distributions, a
// top-endpoints table, and host infra. No vendor branding ever surfaces.
// ============================================================

import { useCallback, useEffect, useMemo, useState } from "react";
import Layout from "@/components/Layout";
import Icon from "@/components/Icon";
import {
    getObsSummary, getObsRed, getObsStatus, getObsServiceDist, getObsRoutes,
    getMetricRange, type ObsRow, type PromSeries,
} from "@/lib/api";
import { SuperAdminGuard, SuperAdminHeaderF3, ErrorBanner, ghostBtnCls } from "../_shared";
import {
    useObsControls, ObsControls, useAutoRefresh, Panel, TimeSeries, Donut, EmptyChart,
    n, fmtNum, fmtMs, fmtClock, statusTone, SERIES,
} from "../_obs";

function Stat({ label, value, sub, tone }: { label: string; value: string; sub?: string; tone?: string }) {
    return (
        <div className="rounded-3xl bg-b-surface2 ring-1 ring-s-subtle ring-inset p-4">
            <div className="text-caption text-t-tertiary">{label}</div>
            <div className="mt-1 text-h5 tabular-nums leading-none" style={tone ? { color: tone } : { color: "var(--text-primary)" }}>{value}</div>
            {sub && <div className="mt-1.5 text-caption text-t-tertiary">{sub}</div>}
        </div>
    );
}

function PerformanceInner() {
    const c = useObsControls(2);
    const [loading, setLoading] = useState(true);
    const [err, setErr] = useState("");
    const [sum, setSum] = useState<ObsRow>({});
    const [red, setRed] = useState<ObsRow[]>([]);
    const [status, setStatus] = useState<ObsRow[]>([]);
    const [svcDist, setSvcDist] = useState<ObsRow[]>([]);
    const [routes, setRoutes] = useState<ObsRow[]>([]);
    const [cpu, setCpu] = useState<Record<string, number>[]>([]);
    const [mem, setMem] = useState<Record<string, number>[]>([]);

    const promSeries = useCallback((resp: { status?: string; data?: { result: PromSeries[] } }): Record<string, number>[] => {
        const s = resp?.data?.result?.[0];
        return (s?.values || []).map(([t, v]) => ({ t: Number(t), v: Number(v) })).filter((r) => Number.isFinite(r.v));
    }, []);

    const load = useCallback(() => {
        setLoading(true);
        setErr("");
        const { minutes, svc } = c;
        Promise.all([
            getObsSummary(minutes, svc), getObsRed(minutes, svc), getObsStatus(minutes, svc),
            getObsServiceDist(minutes), getObsRoutes(minutes, svc, 50),
            getMetricRange(`100 - (avg(rate(node_cpu_seconds_total{mode="idle",host="haptica-prod"}[5m]))*100)`, minutes, 0),
            getMetricRange(`(1-(node_memory_MemAvailable_bytes{host="haptica-prod"}/node_memory_MemTotal_bytes{host="haptica-prod"}))*100`, minutes, 0),
        ]).then(([s, r, st, sv, rt, cpuR, memR]) => {
            if (s.error && r.error) setErr("Telemetry backend not reachable. It populates as traffic flows.");
            setSum(s.row || {});
            setRed(r.rows || []);
            setStatus(st.rows || []);
            setSvcDist(sv.rows || []);
            setRoutes(rt.rows || []);
            setCpu(promSeries(cpuR));
            setMem(promSeries(memR));
        }).finally(() => setLoading(false));
    }, [c, promSeries]);

    // eslint-disable-next-line react-hooks/exhaustive-deps
    useEffect(() => { load(); }, [c.minutes, c.svc]);
    const Auto = useAutoRefresh(load, 30000);

    const throughput = useMemo(() => red.map((r) => ({ t: n(r.t), calls: n(r.calls), errors: n(r.errors) })), [red]);
    const latency = useMemo(() => red.map((r) => ({ t: n(r.t), p50: n(r.p50), p95: n(r.p95), p99: n(r.p99) })), [red]);
    const statusDonut = useMemo(() => status.map((r) => ({ name: String(r.code), value: n(r.calls), color: statusTone(String(r.code)) })), [status]);
    const svcDonut = useMemo(() => svcDist.map((r, i) => ({ name: String(r.service), value: n(r.calls), color: SERIES[i % SERIES.length] })), [svcDist]);

    return (
        <Layout title="Performance">
            <SuperAdminHeaderF3 actions={
                <div className="flex items-center gap-2">
                    <Auto />
                    <button onClick={load} className={ghostBtnCls} disabled={loading}>
                        <Icon name="clock" className={`size-4 fill-current ${loading ? "animate-spin" : ""}`} />
                        {loading ? "…" : "Refresh"}
                    </button>
                </div>
            } />
            <ObsControls c={c} />
            <ErrorBanner msg={err} />

            {/* KPI row */}
            <div className="grid grid-cols-5 gap-3 mb-3 max-xl:grid-cols-3 max-md:grid-cols-2">
                <Stat label="Requests" value={fmtNum(n(sum.calls))} sub={`${n(sum.rps).toFixed(2)}/s`} />
                <Stat label="Error rate" value={`${n(sum.err_pct).toFixed(2)}%`} tone={n(sum.err_pct) > 1 ? "#FF6A55" : undefined} sub={`${fmtNum(n(sum.errors))} errors`} />
                <Stat label="Latency p50" value={fmtMs(n(sum.p50))} />
                <Stat label="Latency p95" value={fmtMs(n(sum.p95))} />
                <Stat label="Latency p99" value={fmtMs(n(sum.p99))} />
            </div>

            {/* RED time-series */}
            <div className="grid grid-cols-2 gap-3 mb-3 max-lg:grid-cols-1">
                <Panel title="Throughput" subtitle="requests & errors / interval">
                    <TimeSeries data={throughput} series={[
                        { key: "calls", label: "Requests", color: "#2A85FF", area: true },
                        { key: "errors", label: "Errors", color: "#FF6A55", area: true },
                    ]} />
                </Panel>
                <Panel title="Latency" subtitle="p50 / p95 / p99 (ms)">
                    <TimeSeries data={latency} unit="ms" series={[
                        { key: "p50", label: "p50", color: "#00A656" },
                        { key: "p95", label: "p95", color: "#EF9D0E" },
                        { key: "p99", label: "p99", color: "#FF6A55" },
                    ]} />
                </Panel>
            </div>

            {/* distributions */}
            <div className="grid grid-cols-2 gap-3 mb-3 max-lg:grid-cols-1">
                <Panel title="Status codes"><Donut data={statusDonut} centerLabel="responses" /></Panel>
                <Panel title="Requests by service"><Donut data={svcDonut} centerLabel="spans" /></Panel>
            </div>

            {/* top endpoints */}
            <Panel title="Top endpoints" subtitle="RED per route" className="mb-3">
                {routes.length === 0 ? <EmptyChart /> : (
                    <div className="overflow-x-auto">
                        <table className="data-table">
                            <thead>
                                <tr>
                                    <th>Method</th><th>Route</th><th className="text-right">Calls</th>
                                    <th className="text-right">Err %</th><th className="text-right">p50</th>
                                    <th className="text-right">p95</th><th className="text-right">p99</th>
                                </tr>
                            </thead>
                            <tbody>
                                {routes.map((r, i) => (
                                    <tr key={i}>
                                        <td><span className="font-mono text-caption px-1.5 py-0.5 rounded bg-b-surface3 text-t-secondary">{String(r.method || "—")}</span></td>
                                        <td className="font-mono text-t-primary truncate max-w-[280px]">{String(r.route)}</td>
                                        <td className="text-right tabular-nums">{fmtNum(n(r.calls))}</td>
                                        <td className="text-right tabular-nums" style={{ color: n(r.err_pct) > 1 ? "#FF6A55" : undefined }}>{n(r.err_pct).toFixed(1)}%</td>
                                        <td className="text-right tabular-nums text-t-secondary">{fmtMs(n(r.p50))}</td>
                                        <td className="text-right tabular-nums text-t-secondary">{fmtMs(n(r.p95))}</td>
                                        <td className="text-right tabular-nums text-t-secondary">{fmtMs(n(r.p99))}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}
            </Panel>

            {/* infra */}
            <div className="grid grid-cols-2 gap-3 max-lg:grid-cols-1">
                <Panel title="CPU — haptica-prod" subtitle="%">
                    <TimeSeries data={cpu.map((d) => ({ t: d.t, v: d.v }))} unit="%" series={[{ key: "v", label: "CPU", color: "#2A85FF", area: true }]} />
                </Panel>
                <Panel title="Memory — haptica-prod" subtitle="%">
                    <TimeSeries data={mem.map((d) => ({ t: d.t, v: d.v }))} unit="%" series={[{ key: "v", label: "Memory", color: "#8E59FF", area: true }]} />
                </Panel>
            </div>
        </Layout>
    );
}

export default function PerformancePage() {
    return <SuperAdminGuard><PerformanceInner /></SuperAdminGuard>;
}
