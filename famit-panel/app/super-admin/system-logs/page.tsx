"use client";

// ============================================================
// System Logs — /super-admin/system-logs
// A native, white-labeled, multi-tab observability explorer:
//   • Logs      — the structured event/error store (filter + detail + AI "why & fix")
//   • Errors    — recurring errors + AI remediation + error operations (from traces)
//   • Traces    — trace list → waterfall → span details (distributed-tracing explorer)
//   • Requests  — RED per route + status-code distribution + throughput
// No vendor (SigNoz/Grafana/Prometheus) branding ever surfaces.
// ============================================================

import { useEffect, useMemo, useState, useCallback } from "react";
import Layout from "@/components/Layout";
import Icon from "@/components/Icon";
import Badge from "@/components/Badge";
import Search from "@/components/Search";
import Select from "@/components/Select";
import Spinner from "@/components/Spinner";
import {
    getSystemLogs, getSystemLogSummary, getSystemLogDetail, suggestSystemLogFix,
    getSystemLogHealth, emitTestSystemLog,
    getObsTraces, getObsTrace, getObsRoutes, getObsStatus, getObsRed, getObsErrors,
    type SystemEvent, type SystemLogSummary, type ObsRow, type SystemLogHealth,
} from "@/lib/api";
import { SuperAdminGuard, SuperAdminHeaderF3, ErrorBanner, ghostBtnCls, fmtDateTime, ago } from "../_shared";
import type { SelectOption } from "@/types/select";
import {
    useObsControls, ObsControls, Panel, TimeSeries, Donut, EmptyChart,
    n, fmtNum, fmtMs, agoMs, statusTone, fmtDateTime as fmtDateTimeMs,
} from "../_obs";

type Tab = "logs" | "errors" | "traces" | "requests";
const TABS: { id: Tab; label: string; icon: string }[] = [
    { id: "logs", label: "Logs", icon: "list" },
    { id: "errors", label: "Errors", icon: "info" },
    { id: "traces", label: "Traces", icon: "chart" },
    { id: "requests", label: "Requests", icon: "arrow" },
];

const LEVEL_OPTIONS: SelectOption[] = [
    { id: 1, name: "All levels" }, { id: 2, name: "Critical" }, { id: 3, name: "Error" },
    { id: 4, name: "Warning" }, { id: 5, name: "Info" },
];
const LEVEL_FILTER: Record<number, string> = { 1: "", 2: "critical", 3: "error", 4: "warning", 5: "info" };

function levelTone(l?: string): "success" | "danger" | "warning" | "info" | "neutral" {
    const x = (l || "").toLowerCase();
    if (x === "critical" || x === "error") return "danger";
    if (x === "warning") return "warning";
    if (x === "info") return "info";
    return "neutral";
}
const LevelBadge = ({ level }: { level?: string }) => (
    <Badge variant={levelTone(level)} dot={levelTone(level) === "danger"}>{level || "info"}</Badge>
);

// ════════════════ LOGS TAB ════════════════
function LogsTab() {
    const PAGE = 80;
    const [events, setEvents] = useState<SystemEvent[]>([]);
    const [total, setTotal] = useState(0);
    const [offset, setOffset] = useState(0);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState("");
    const [search, setSearch] = useState("");
    const [level, setLevel] = useState<SelectOption>(LEVEL_OPTIONS[0]);
    const [openId, setOpenId] = useState<string | null>(null);
    const [detail, setDetail] = useState<SystemEvent | null>(null);
    const [suggestion, setSuggestion] = useState("");
    const [suggesting, setSuggesting] = useState(false);
    const lvl = LEVEL_FILTER[Number(level.id)] ?? "";

    const load = useCallback((off: number) => {
        setLoading(true); setError("");
        getSystemLogs({ limit: PAGE, offset: off, level: lvl })
            .then((r) => { setEvents(r.events); setTotal(r.total); setOffset(r.offset); })
            .catch((e) => setError(e instanceof Error ? e.message : "Failed"))
            .finally(() => setLoading(false));
    }, [lvl]);
    useEffect(() => { load(0); }, [load]);

    // Capture self-test: surface whether the store is live + writable, and let the operator
    // emit a synthetic event to confirm end-to-end capture in one click.
    const [health, setHealth] = useState<SystemLogHealth | null>(null);
    const [testing, setTesting] = useState(false);
    const loadHealth = useCallback(() => { getSystemLogHealth().then(setHealth).catch(() => {}); }, []);
    useEffect(() => { loadHealth(); }, [loadHealth]);
    const runTest = useCallback(async () => {
        setTesting(true);
        try { if (await emitTestSystemLog()) { load(0); loadHealth(); } }
        finally { setTesting(false); }
    }, [load, loadHealth]);
    const captureOk = !!(health && health.ready && health.writable);

    const openDetail = useCallback(async (id: string) => {
        setOpenId(id); setDetail(null); setSuggestion("");
        const d = await getSystemLogDetail(id); setDetail(d); setSuggestion(d?.suggestion || "");
    }, []);
    const genFix = useCallback(async () => {
        if (!openId) return; setSuggesting(true);
        // force=true so "Regenerate" bypasses the per-fingerprint cache and re-asks the LLM
        // (otherwise every click returned the same cached answer).
        try { setSuggestion((await suggestSystemLogFix(openId, true)) || "No suggestion (check GROQ_API_KEY)."); }
        finally { setSuggesting(false); }
    }, [openId]);

    const rows = useMemo(() => {
        const q = search.trim().toLowerCase();
        if (!q) return events;
        return events.filter((e) => `${e.message} ${e.source} ${e.error_type || ""} ${e.tenant_id || ""} ${e.call_id || ""}`.toLowerCase().includes(q));
    }, [events, search]);

    return (
        <>
            <div className="flex items-center gap-3 mb-4 flex-wrap">
                <div className="w-72 max-md:w-full"><Search value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search message, source, tenant, call…" isGray /></div>
                <Select className="min-w-44" value={level} onChange={setLevel} options={LEVEL_OPTIONS} />
                <div className="ml-auto flex items-center gap-3 flex-wrap">
                    {health && (
                        <span title={`store: ${health.path || "—"}\nwritable: ${health.writable ? "yes" : "NO"} · buffered: ${health.ring_count ?? 0} · seq: ${health.latest_seq ?? 0}${health.telegram ? "\nTelegram alerts: on" : ""}${health.ai_fix ? "\nAI fix: on" : ""}`}>
                            <Badge variant={captureOk ? "success" : "danger"} dot>{captureOk ? "Capture live" : "Capture down"}</Badge>
                        </span>
                    )}
                    <span className="text-caption text-t-tertiary tabular-nums">{total.toLocaleString()} events</span>
                    <button onClick={runTest} className={ghostBtnCls} disabled={testing} title="Emit a synthetic event to verify capture end-to-end">
                        <Icon name="check-circle" className={`size-4 fill-current ${testing ? "animate-pulse" : ""}`} />{testing ? "Testing…" : "Test"}
                    </button>
                    <button onClick={() => { load(offset); loadHealth(); }} className={ghostBtnCls} disabled={loading}>
                        <Icon name="clock" className={`size-4 fill-current ${loading ? "animate-spin" : ""}`} />Refresh
                    </button>
                </div>
            </div>
            <ErrorBanner msg={error} />
            <Panel title="Event stream">
                {loading && events.length === 0 ? <div className="py-16"><Spinner /></div>
                    : rows.length === 0 ? <div className="state-block"><div className="state-title">No events</div></div>
                        : (
                            <div className="divide-y divide-s-subtle -m-3">
                                {rows.map((e) => (
                                    <button key={e.id} onClick={() => openDetail(e.id)} className="w-full flex items-start gap-3 px-4 py-3 text-left transition-colors hover:bg-b-surface3/50 max-md:flex-col max-md:gap-1.5">
                                        <div className="shrink-0 w-24"><LevelBadge level={e.level} /></div>
                                        <div className="min-w-0 flex-1">
                                            <div className="text-body-2 text-t-primary truncate">{e.message}</div>
                                            <div className="flex items-center gap-x-3 mt-0.5 text-caption text-t-tertiary flex-wrap">
                                                <span className="font-mono">{e.source}</span>
                                                {e.error_type && <span className="text-primary-03">{e.error_type}</span>}
                                                {e.tenant_id && <span>tenant {e.tenant_id}</span>}
                                                {e.call_id && <span>call {e.call_id}</span>}
                                                {!!e.count && e.count > 1 && <span>×{e.count}</span>}
                                            </div>
                                        </div>
                                        <div className="shrink-0 text-caption text-t-tertiary whitespace-nowrap" title={fmtDateTime(e.ts)}>{ago(e.ts)}</div>
                                    </button>
                                ))}
                            </div>
                        )}
            </Panel>
            {total > PAGE && (
                <div className="flex items-center justify-between gap-3 mt-4">
                    <button onClick={() => load(Math.max(0, offset - PAGE))} disabled={loading || offset === 0} className={ghostBtnCls}>Newer</button>
                    <div className="text-caption text-t-tertiary tabular-nums">{Math.floor(offset / PAGE) + 1} / {Math.max(1, Math.ceil(total / PAGE))}</div>
                    <button onClick={() => load(offset + PAGE)} disabled={loading || offset + PAGE >= total} className={ghostBtnCls}>Older</button>
                </div>
            )}
            {openId && (
                <Overlay onClose={() => setOpenId(null)}>
                    {!detail ? <div className="py-16"><Spinner /></div> : (
                        <>
                            <div className="flex items-center gap-2 flex-wrap mb-3">
                                <LevelBadge level={detail.level} />
                                <span className="font-mono text-caption text-t-secondary">{detail.source}</span>
                                {detail.error_type && <span className="font-mono text-caption text-primary-03">{detail.error_type}</span>}
                                {!!detail.count && detail.count > 1 && <span className="text-caption text-t-tertiary">seen ×{detail.count}</span>}
                            </div>
                            <div className="text-body-1 text-t-primary whitespace-pre-wrap break-words mb-4">{detail.message}</div>
                            <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-caption mb-4 max-md:grid-cols-1">
                                <Meta label="When" value={fmtDateTime(detail.ts)} />
                                {detail.tenant_id && <Meta label="Tenant" value={detail.tenant_id} mono />}
                                {detail.call_id && <Meta label="Call" value={detail.call_id} mono />}
                                {detail.fingerprint && <Meta label="Fingerprint" value={detail.fingerprint} mono />}
                            </dl>
                            {detail.context && Object.keys(detail.context).length > 0 && (
                                <pre className="text-caption font-mono text-t-secondary bg-b-surface2 rounded-2xl p-3 overflow-x-auto whitespace-pre-wrap break-words mb-4">{JSON.stringify(detail.context, null, 2)}</pre>
                            )}
                            <div className="rounded-3xl bg-primary-01/[0.06] ring-1 ring-primary-01/20 p-4">
                                <div className="flex items-center justify-between gap-3 mb-2">
                                    <div className="flex items-center gap-2 text-button text-t-primary"><Icon name="help" className="size-4 fill-primary-01" />Suggested fix</div>
                                    <button onClick={genFix} disabled={suggesting} className="inline-flex items-center gap-2 h-9 px-4 rounded-full bg-primary-01 text-white text-button hover:brightness-110 disabled:opacity-50">{suggesting ? "Analyzing…" : suggestion ? "Regenerate" : "Suggest a fix"}</button>
                                </div>
                                {suggestion ? <div className="text-body-2 text-t-secondary whitespace-pre-wrap break-words">{suggestion}</div>
                                    : <div className="text-caption text-t-tertiary">Generate an AI root-cause + concrete fix steps for this issue.</div>}
                            </div>
                        </>
                    )}
                </Overlay>
            )}
        </>
    );
}

// ════════════════ ERRORS TAB ════════════════
function ErrorsTab() {
    const c = useObsControls(4);
    const [summary, setSummary] = useState<SystemLogSummary | null>(null);
    const [ops, setOps] = useState<ObsRow[]>([]);
    const [loading, setLoading] = useState(true);
    const load = useCallback(() => {
        setLoading(true);
        Promise.all([getSystemLogSummary(), getObsErrors(c.minutes, c.svc, 30)])
            .then(([s, o]) => { setSummary(s); setOps(o.rows || []); }).finally(() => setLoading(false));
    }, [c.minutes, c.svc]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
    useEffect(() => { load(); }, [c.minutes, c.svc]);
    const by = summary?.by_level || {};
    return (
        <>
            <ObsControls c={c} right={<button onClick={load} className={ghostBtnCls} disabled={loading}><Icon name="clock" className={`size-4 fill-current ${loading ? "animate-spin" : ""}`} />Refresh</button>} />
            <div className="grid grid-cols-4 gap-3 mb-3 max-md:grid-cols-2">
                <Stat label="Errors (24h)" value={fmtNum(n(summary?.errors_24h))} tone="#FF6A55" />
                <Stat label="Critical" value={fmtNum(n((by as Record<string, number>).critical))} />
                <Stat label="Events (24h)" value={fmtNum(n(summary?.last_24h))} />
                <Stat label="Error ops" value={fmtNum(ops.length)} sub="in window" />
            </div>
            <div className="grid grid-cols-2 gap-3 max-lg:grid-cols-1">
                <Panel title="Top recurring issues" subtitle="from the event store · click for AI fix">
                    {!summary || summary.top_errors.length === 0 ? <EmptyChart msg="No recurring errors" /> : (
                        <div className="divide-y divide-s-subtle -m-3">
                            {summary.top_errors.map((t) => (
                                <a key={t.fingerprint} href={`#${t.last_id || ""}`} className="flex items-center gap-3 px-4 py-3">
                                    <LevelBadge level={t.level} />
                                    <span className="min-w-0 flex-1 truncate text-body-2 text-t-primary">{t.message}</span>
                                    <span className="shrink-0 text-caption text-t-tertiary">{t.source}</span>
                                    <span className="shrink-0 inline-flex items-center justify-center min-w-7 h-6 px-2 rounded-full bg-primary-03/10 text-primary-03 text-caption font-semibold tabular-nums">×{t.count}</span>
                                </a>
                            ))}
                        </div>
                    )}
                </Panel>
                <Panel title="Error operations" subtitle="error spans grouped by operation (from traces)">
                    {ops.length === 0 ? <EmptyChart msg="No error spans in window" /> : (
                        <div className="divide-y divide-s-subtle -m-3">
                            {ops.map((o, i) => (
                                <div key={i} className="flex items-center gap-3 px-4 py-3">
                                    <Icon name="info" className="size-4 fill-primary-03 shrink-0" />
                                    <span className="min-w-0 flex-1 truncate font-mono text-body-2 text-t-primary">{String(o.op)}</span>
                                    <span className="shrink-0 text-caption text-t-tertiary">{String(o.service)}</span>
                                    <span className="shrink-0 text-caption text-t-tertiary">{agoMs(n(o.last_ms))}</span>
                                    <span className="shrink-0 inline-flex items-center justify-center min-w-7 h-6 px-2 rounded-full bg-primary-03/10 text-primary-03 text-caption font-semibold tabular-nums">×{fmtNum(n(o.calls))}</span>
                                </div>
                            ))}
                        </div>
                    )}
                </Panel>
            </div>
            <div className="mt-3 text-caption text-t-tertiary">Tip: open the <b className="text-t-secondary">Logs</b> tab and click any error for a one-click AI root-cause + fix.</div>
        </>
    );
}

// ════════════════ TRACES TAB ════════════════
function TracesTab() {
    const c = useObsControls(2);
    const [rows, setRows] = useState<ObsRow[]>([]);
    const [loading, setLoading] = useState(true);
    const [errOnly, setErrOnly] = useState(false);
    const [q, setQ] = useState("");
    const [openTrace, setOpenTrace] = useState<string | null>(null);
    const load = useCallback(() => {
        setLoading(true);
        getObsTraces({ minutes: c.minutes, service: c.svc, errors_only: errOnly ? 1 : 0, q, limit: 80 })
            .then((r) => setRows(r.rows || [])).finally(() => setLoading(false));
    }, [c.minutes, c.svc, errOnly, q]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
    useEffect(() => { load(); }, [c.minutes, c.svc, errOnly]);

    return (
        <>
            <ObsControls c={c} right={
                <div className="flex items-center gap-3 flex-wrap">
                    <div className="w-56"><Search value={q} onChange={(e) => setQ(e.target.value)} placeholder="trace id / operation…" isGray /></div>
                    <button onClick={() => setErrOnly((v) => !v)} className={`inline-flex items-center gap-1.5 h-10 px-4 rounded-full border text-button transition-colors ${errOnly ? "border-primary-03/40 text-primary-03" : "border-s-subtle text-t-secondary hover:text-t-primary"}`}>
                        <Icon name="info" className="size-4 fill-current" />Errors only
                    </button>
                    <button onClick={load} className={ghostBtnCls} disabled={loading}><Icon name="clock" className={`size-4 fill-current ${loading ? "animate-spin" : ""}`} />Search</button>
                </div>
            } />
            <Panel title="Traces" subtitle={`${rows.length} traces`}>
                {loading && rows.length === 0 ? <div className="py-16"><Spinner /></div>
                    : rows.length === 0 ? <EmptyChart msg="No traces in this window" /> : (
                        <div className="overflow-x-auto -m-3">
                            <table className="data-table">
                                <thead><tr><th>Time</th><th>Root operation</th><th>Service</th><th className="text-right">Duration</th><th className="text-right">Spans</th><th className="text-right">Errors</th><th>Trace ID</th></tr></thead>
                                <tbody>
                                    {rows.map((r) => {
                                        const errs = n(r.error_count);
                                        return (
                                            <tr key={String(r.trace_id)} onClick={() => setOpenTrace(String(r.trace_id))} className="cursor-pointer hover:bg-b-surface3/50">
                                                <td className="text-t-tertiary text-caption whitespace-nowrap" title={fmtDateTimeMs(n(r.ts_ms))}>{agoMs(n(r.ts_ms))}</td>
                                                <td className="font-mono text-t-primary truncate max-w-[260px]">{String(r.root_name || "—")}</td>
                                                <td className="text-t-secondary">{String(r.root_service || "—")}</td>
                                                <td className="text-right tabular-nums">{fmtMs(n(r.duration_ms))}</td>
                                                <td className="text-right tabular-nums text-t-secondary">{n(r.span_count)}</td>
                                                <td className="text-right">{errs > 0 ? <span className="text-primary-03 tabular-nums font-medium">{errs}</span> : <span className="text-t-tertiary">0</span>}</td>
                                                <td className="font-mono text-caption text-t-tertiary truncate max-w-[140px]">{String(r.trace_id).slice(0, 16)}…</td>
                                            </tr>
                                        );
                                    })}
                                </tbody>
                            </table>
                        </div>
                    )}
            </Panel>
            {openTrace && <TraceDrawer traceId={openTrace} onClose={() => setOpenTrace(null)} />}
        </>
    );
}

function TraceDrawer({ traceId, onClose }: { traceId: string; onClose: () => void }) {
    const [spans, setSpans] = useState<ObsRow[]>([]);
    const [loading, setLoading] = useState(true);
    const [sel, setSel] = useState<ObsRow | null>(null);
    useEffect(() => {
        setLoading(true);
        getObsTrace(traceId).then((r) => { setSpans(r.rows || []); setSel((r.rows || [])[0] || null); }).finally(() => setLoading(false));
    }, [traceId]);

    // geometry in MICROSECONDS (start_us survives JS Number precision; durations converted ns->us)
    const { t0, span } = useMemo(() => {
        if (!spans.length) return { t0: 0, span: 0 };
        const starts = spans.map((s) => n(s.start_us));
        const ends = spans.map((s) => n(s.start_us) + n(s.duration_nano) / 1000);
        const min = Math.min(...starts), max = Math.max(...ends);
        return { t0: min, span: Math.max(1, max - min) };
    }, [spans]);

    return (
        <Overlay onClose={onClose} wide>
            <div className="flex items-center gap-2 flex-wrap mb-1">
                <span className="text-button text-t-primary">Trace</span>
                <span className="font-mono text-caption text-t-tertiary">{traceId}</span>
            </div>
            <div className="text-caption text-t-tertiary mb-4">{spans.length} spans · {fmtMs(span / 1e6)}</div>
            {loading ? <div className="py-16"><Spinner /></div> : (
                <div className="flex gap-4 max-lg:flex-col">
                    {/* waterfall */}
                    <div className="flex-1 min-w-0 space-y-1">
                        {spans.map((s) => {
                            const left = ((n(s.start_us) - t0) / span) * 100;
                            const width = Math.max(0.5, ((n(s.duration_nano) / 1000) / span) * 100);
                            const isErr = s.has_error === true || s.has_error === 1 || s.has_error === "true";
                            const active = sel?.span_id === s.span_id;
                            return (
                                <button key={String(s.span_id)} onClick={() => setSel(s)} className={`w-full text-left rounded-lg px-2 py-1.5 transition-colors ${active ? "bg-primary-01/10 ring-1 ring-primary-01/30" : "hover:bg-b-surface3/50"}`}>
                                    <div className="flex items-center gap-2 mb-1">
                                        <span className="font-mono text-caption text-t-primary truncate flex-1">{String(s.name)}</span>
                                        <span className="text-caption text-t-tertiary tabular-nums shrink-0">{fmtMs(n(s.duration_nano) / 1e6)}</span>
                                    </div>
                                    <div className="relative h-2 rounded-full bg-b-surface3">
                                        <div className="absolute top-0 bottom-0 rounded-full" style={{ left: `${left}%`, width: `${width}%`, background: isErr ? "#FF6A55" : "#2A85FF" }} />
                                    </div>
                                </button>
                            );
                        })}
                    </div>
                    {/* span detail */}
                    {sel && (
                        <div className="w-80 shrink-0 max-lg:w-full rounded-2xl bg-b-surface2 ring-1 ring-s-subtle ring-inset p-4 self-start">
                            <div className="text-button text-t-primary mb-3 break-words">{String(sel.name)}</div>
                            <dl className="space-y-2 text-caption">
                                <Meta label="Service" value={String(sel.service)} mono />
                                <Meta label="Duration" value={fmtMs(n(sel.duration_nano) / 1e6)} />
                                <Meta label="Kind" value={String(sel.kind || "—")} />
                                {sel.http_method ? <Meta label="Method" value={String(sel.http_method)} mono /> : null}
                                {sel.http_route ? <Meta label="Route" value={String(sel.http_route)} mono /> : null}
                                {sel.status_code ? <Meta label="HTTP status" value={String(sel.status_code)} mono /> : null}
                                <Meta label="Error" value={(sel.has_error === true || sel.has_error === 1 || sel.has_error === "true") ? "yes" : "no"} />
                                {sel.status_message ? <Meta label="Status msg" value={String(sel.status_message)} /> : null}
                                <Meta label="Span ID" value={String(sel.span_id)} mono />
                            </dl>
                        </div>
                    )}
                </div>
            )}
        </Overlay>
    );
}

// ════════════════ REQUESTS TAB ════════════════
function RequestsTab() {
    const c = useObsControls(2);
    const [routes, setRoutes] = useState<ObsRow[]>([]);
    const [status, setStatus] = useState<ObsRow[]>([]);
    const [red, setRed] = useState<ObsRow[]>([]);
    const [loading, setLoading] = useState(true);
    const load = useCallback(() => {
        setLoading(true);
        Promise.all([getObsRoutes(c.minutes, c.svc, 100), getObsStatus(c.minutes, c.svc), getObsRed(c.minutes, c.svc)])
            .then(([r, s, rd]) => { setRoutes(r.rows || []); setStatus(s.rows || []); setRed(rd.rows || []); }).finally(() => setLoading(false));
    }, [c.minutes, c.svc]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
    useEffect(() => { load(); }, [c.minutes, c.svc]);
    const throughput = useMemo(() => red.map((r) => ({ t: n(r.t), calls: n(r.calls), errors: n(r.errors) })), [red]);
    const statusDonut = useMemo(() => status.map((r) => ({ name: String(r.code), value: n(r.calls), color: statusTone(String(r.code)) })), [status]);

    return (
        <>
            <ObsControls c={c} right={<button onClick={load} className={ghostBtnCls} disabled={loading}><Icon name="clock" className={`size-4 fill-current ${loading ? "animate-spin" : ""}`} />Refresh</button>} />
            <div className="grid grid-cols-2 gap-3 mb-3 max-lg:grid-cols-1">
                <Panel title="Throughput" subtitle="requests & errors"><TimeSeries data={throughput} series={[{ key: "calls", label: "Requests", color: "#2A85FF", area: true }, { key: "errors", label: "Errors", color: "#FF6A55", area: true }]} /></Panel>
                <Panel title="Status codes"><Donut data={statusDonut} centerLabel="responses" /></Panel>
            </div>
            <Panel title="Requests by route" subtitle={`${routes.length} routes · RED metrics`}>
                {loading && routes.length === 0 ? <div className="py-16"><Spinner /></div>
                    : routes.length === 0 ? <EmptyChart /> : (
                        <div className="overflow-x-auto -m-3">
                            <table className="data-table">
                                <thead><tr><th>Method</th><th>Route</th><th className="text-right">Calls</th><th className="text-right">Err %</th><th className="text-right">p50</th><th className="text-right">p95</th><th className="text-right">p99</th></tr></thead>
                                <tbody>
                                    {routes.map((r, i) => (
                                        <tr key={i}>
                                            <td><span className="font-mono text-caption px-1.5 py-0.5 rounded bg-b-surface3 text-t-secondary">{String(r.method || "—")}</span></td>
                                            <td className="font-mono text-t-primary truncate max-w-[300px]">{String(r.route)}</td>
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
        </>
    );
}

// ════════════════ shared bits ════════════════
function Stat({ label, value, sub, tone }: { label: string; value: string; sub?: string; tone?: string }) {
    return (
        <div className="rounded-3xl bg-b-surface2 ring-1 ring-s-subtle ring-inset p-4">
            <div className="text-caption text-t-tertiary">{label}</div>
            <div className="mt-1 text-h5 tabular-nums leading-none" style={{ color: tone || "var(--text-primary)" }}>{value}</div>
            {sub && <div className="mt-1.5 text-caption text-t-tertiary">{sub}</div>}
        </div>
    );
}
function Meta({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
    return (
        <div className="flex items-start gap-2">
            <dt className="text-t-tertiary shrink-0 w-24">{label}</dt>
            <dd className={`text-t-secondary break-words min-w-0 ${mono ? "font-mono" : ""}`}>{value}</dd>
        </div>
    );
}
function Overlay({ children, onClose, wide }: { children: React.ReactNode; onClose: () => void; wide?: boolean }) {
    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-shade-01/50 backdrop-blur-sm" onClick={onClose}>
            <div className={`w-full ${wide ? "max-w-5xl" : "max-w-2xl"} max-h-[88vh] overflow-y-auto rounded-3xl bg-b-surface1 ring-1 ring-s-subtle shadow-2xl p-6 max-md:p-4`} onClick={(e) => e.stopPropagation()}>
                <button onClick={onClose} className="float-right grid place-items-center size-8 rounded-full text-t-tertiary hover:text-t-primary hover:bg-b-surface2"><Icon name="close" className="size-4 fill-current" /></button>
                {children}
            </div>
        </div>
    );
}

function SystemLogsInner() {
    const [tab, setTab] = useState<Tab>("logs");
    return (
        <Layout title="System Logs">
            <SuperAdminHeaderF3 />
            <div className="flex gap-1 mb-5 flex-wrap">
                {TABS.map((t) => (
                    <button key={t.id} onClick={() => setTab(t.id)} className={`inline-flex items-center gap-2 h-10 px-4 rounded-full border text-button transition-colors ${tab === t.id ? "border-s-stroke2 text-t-primary bg-b-surface2" : "border-transparent text-t-secondary hover:text-t-primary"}`}>
                        <Icon name={t.icon} className="size-4 fill-current" />{t.label}
                    </button>
                ))}
            </div>
            {tab === "logs" && <LogsTab />}
            {tab === "errors" && <ErrorsTab />}
            {tab === "traces" && <TracesTab />}
            {tab === "requests" && <RequestsTab />}
        </Layout>
    );
}

export default function SystemLogsPage() {
    return <SuperAdminGuard><SystemLogsInner /></SuperAdminGuard>;
}
