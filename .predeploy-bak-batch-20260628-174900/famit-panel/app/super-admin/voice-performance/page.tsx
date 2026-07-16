"use client";

// ============================================================
// Voice Performance Analytics — /super-admin/voice-performance
// Per-call + sentence-level voice latency over the agent-written haptica_voice_* ClickHouse tables
// (via /admin/obs/voice/*). Live dashboard (avg/P95/P99, success/error rate, throughput, active
// providers) + filters (agent/phone/campaign/provider/model/service/status/time) + a per-call
// stage timeline (User → STT → LLM → TTS → Audio). White-labeled; dormant-safe (empty when the
// telemetry backend isn't configured / no calls yet). Mirrors the Performance page's primitives.
// ============================================================

import { useCallback, useEffect, useMemo, useState } from "react";
import Layout from "@/components/Layout";
import Icon from "@/components/Icon";
import Select from "@/components/Select";
import Search from "@/components/Search";
import Badge from "@/components/Badge";
import {
    getVoiceSummary, getVoiceRed, getVoiceCalls, getVoiceFilterOptions, getVoiceCall, getVoiceStack,
    getVoiceCallQuality,
    type ObsRow, type VoiceFilters, type VoiceFilterOptions, type TranscriptQuality, type VoiceCost,
} from "@/lib/api";
import type { SelectOption } from "@/types/select";
import { SuperAdminGuard, SuperAdminHeaderF3, ErrorBanner, ghostBtnCls } from "../_shared";
import {
    useAutoRefresh, Panel, TimeSeries, Donut, EmptyChart,
    n, fmtNum, fmtMs, fmtDateTime, agoMs, SERIES, TIME_RANGES,
} from "../_obs";

const STAGE_LABEL: Record<string, string> = { eou: "Turn detect", stt: "STT", llm: "LLM", tts: "TTS" };
const STAGE_COLOR: Record<string, string> = { stt: "#2A85FF", llm: "#8E59FF", tts: "#00A656", eou: "#EF9D0E" };
const STAGE_ORDER = ["eou", "stt", "llm", "tts"];

// Technical CALL-QUALITY score (0-100) from the real metrics — latency, reliability (429/errors),
// network and completion. The honest "quality meter" (content/transcript quality is a separate, LLM
// pass — see the note in the panel). Higher = a snappier, cleaner, more reliable call.
function qualityScore(detail: ObsRow, latency: ObsRow): number {
    let s = 100;
    const avg = Number(latency.avg_ms) || 0;            // avg per-turn response latency
    if (avg > 3500) s -= 45; else if (avg > 2500) s -= 30; else if (avg > 1800) s -= 16; else if (avg > 1200) s -= 6;
    const r429 = Number(detail.rate_limit_429) || 0; if (r429 > 0) s -= Math.min(30, r429 * 6);
    const errs = Number(detail.errors) || 0; if (errs > 0) s -= Math.min(20, errs * 5);
    const net = String(detail.net_quality || "").toUpperCase();
    if (net === "LOST") s -= 30; else if (net === "POOR") s -= 16;
    if (String(detail.status || "") !== "completed") s -= 15;
    return Math.max(0, Math.min(100, Math.round(s)));
}
const qualityTone = (q: number) => (q >= 80 ? "#00A656" : q >= 60 ? "#EF9D0E" : "#FF6A55");
const qualityLabel = (q: number) => (q >= 80 ? "Good" : q >= 60 ? "Fair" : "Poor");

function Stat({ label, value, sub, tone }: { label: string; value: string; sub?: string; tone?: string }) {
    return (
        <div className="rounded-3xl bg-b-surface2 ring-1 ring-s-subtle ring-inset p-4">
            <div className="text-caption text-t-tertiary">{label}</div>
            <div className="mt-1 text-h5 tabular-nums leading-none" style={tone ? { color: tone } : { color: "var(--text-primary)" }}>{value}</div>
            {sub && <div className="mt-1.5 text-caption text-t-tertiary">{sub}</div>}
        </div>
    );
}

// One filter dropdown over a string[] of values, with an "All" option. Maps Select's numeric id
// back to the underlying string (SelectOption.id is strictly numeric in this design system).
function FilterSelect({ label, value, values, onChange }: {
    label: string; value: string; values: string[]; onChange: (v: string) => void;
}) {
    const all = useMemo(() => ["", ...values.filter(Boolean)], [values]);
    const opts: SelectOption[] = all.map((v, i) => ({ id: i, name: i === 0 ? `All ${label}` : v }));
    const idx = Math.max(0, all.indexOf(value));
    return (
        <div className="min-w-[9.5rem] max-md:w-full">
            <Select value={opts[idx] || opts[0]} onChange={(o) => onChange(all[o.id as number] || "")} options={opts} />
        </div>
    );
}

function VoicePerfInner() {
    const [rangeId, setRangeId] = useState(2);
    const minutes = useMemo(() => TIME_RANGES.find((r) => r.id === rangeId)?.minutes ?? 360, [rangeId]);

    const [filters, setFilters] = useState<VoiceFilters>({});
    const [phoneInput, setPhoneInput] = useState("");
    const [opts, setOpts] = useState<NonNullable<VoiceFilterOptions["row"]>>({});

    const [loading, setLoading] = useState(true);
    const [err, setErr] = useState("");
    const [sum, setSum] = useState<ObsRow>({});
    const [byStage, setByStage] = useState<ObsRow[]>([]);
    const [red, setRed] = useState<ObsRow[]>([]);
    const [calls, setCalls] = useState<ObsRow[]>([]);

    const [openCall, setOpenCall] = useState<string | null>(null);
    const [callDetail, setCallDetail] = useState<ObsRow | null>(null);
    const [timeline, setTimeline] = useState<ObsRow[]>([]);
    const [callLatency, setCallLatency] = useState<ObsRow>({});
    const [callCost, setCallCost] = useState<VoiceCost | null>(null);
    const [callLoading, setCallLoading] = useState(false);
    const [stack, setStack] = useState<{ combos: ObsRow[]; stages: ObsRow[] }>({ combos: [], stages: [] });
    const [quality, setQuality] = useState<TranscriptQuality | null>(null);
    const [qualityLoading, setQualityLoading] = useState(false);

    // stable filter signature so the load effect doesn't loop on object identity
    const fKey = JSON.stringify({ minutes, ...filters });

    const load = useCallback(() => {
        setLoading(true);
        setErr("");
        Promise.all([
            getVoiceSummary(minutes, filters),
            getVoiceRed(minutes, filters),
            getVoiceCalls(minutes, filters, 200),
            getVoiceStack(minutes, filters),
        ]).then(([s, r, c, st]) => {
            if (s.error && r.error) setErr("Voice telemetry backend not reachable yet. It populates as calls flow (needs VOICE_ANALYTICS_ENABLED + the ClickHouse tables).");
            setSum(s.row || {});
            setByStage(s.latency_by_stage || []);
            setRed(r.rows || []);
            setCalls(c.rows || []);
            setStack({ combos: st.combos || [], stages: st.stages || [] });
        }).finally(() => setLoading(false));
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [fKey]);

    // eslint-disable-next-line react-hooks/exhaustive-deps
    useEffect(() => { load(); }, [fKey]);
    useEffect(() => { getVoiceFilterOptions(1440).then((o) => setOpts(o.row || {})).catch(() => {}); }, []);
    const Auto = useAutoRefresh(load, 15000);

    const setF = useCallback((patch: Partial<VoiceFilters>) => setFilters((p) => ({ ...p, ...patch })), []);

    const openDetail = useCallback(async (callId: string) => {
        setOpenCall(callId);
        setCallDetail(null);
        setTimeline([]);
        setQuality(null);
        setCallLoading(true);
        try {
            const b = await getVoiceCall(callId);
            setCallDetail(b.detail || {});
            setCallCost(b.cost || null);
            setTimeline(b.timeline || []);
            setCallLatency(b.latency || {});
        } finally {
            setCallLoading(false);
        }
        // peek an already-cached transcript analysis (free; never auto-spends an LLM call)
        getVoiceCallQuality(callId, { cachedOnly: true }).then((q) => { if (q.ok) setQuality(q); }).catch(() => {});
    }, []);

    const analyzeQuality = useCallback(async (force = false) => {
        if (!openCall) return;
        setQualityLoading(true);
        try {
            setQuality(await getVoiceCallQuality(openCall, { force }));
        } finally {
            setQualityLoading(false);
        }
    }, [openCall]);

    // chart series
    const latency = useMemo(() => red.map((r) => ({ t: n(r.t), p50: n(r.p50), p95: n(r.p95), p99: n(r.p99) })), [red]);
    const throughput = useMemo(() => red.map((r) => ({ t: n(r.t), events: n(r.events) })), [red]);
    const stageDonut = useMemo(
        () => STAGE_ORDER
            .map((st) => byStage.find((r) => String(r.stage) === st))
            .filter(Boolean)
            .map((r) => ({ name: STAGE_LABEL[String(r!.stage)] || String(r!.stage), value: n(r!.p95), color: STAGE_COLOR[String(r!.stage)] || "#6C72FF" })),
        [byStage]
    );
    const stageP95 = (st: string) => n(byStage.find((r) => String(r.stage) === st)?.p95);

    // group the per-event timeline into per-turn rows (pivot stage → latency)
    const turns = useMemo(() => {
        const m = new Map<number, { turn: number; ts: number; stt: number; eou: number; llm: number; tts: number; net: number; in_tok: number; out_tok: number }>();
        for (const ev of timeline) {
            const ti = n(ev.turn_index);
            const cur = m.get(ti) || { turn: ti, ts: n(ev.ts_ms), stt: 0, eou: 0, llm: 0, tts: 0, net: 0, in_tok: 0, out_tok: 0 };
            const st = String(ev.stage);
            if (st === "stt" || st === "eou" || st === "llm" || st === "tts") cur[st] = n(ev.latency_ms);
            cur.net = Math.max(cur.net, n(ev.net_rtt_ms));   // telecom RTT snapshot for the turn (0 = unknown)
            cur.in_tok += n(ev.prompt_tokens);
            cur.out_tok += n(ev.completion_tokens);
            cur.ts = Math.min(cur.ts || n(ev.ts_ms), n(ev.ts_ms));
            m.set(ti, cur);
        }
        return Array.from(m.values()).sort((a, b) => a.turn - b.turn);
    }, [timeline]);

    const successPct = n(sum.success_pct);
    const errorPct = n(sum.error_pct);

    return (
        <Layout title="Voice Performance Analytics">
            <SuperAdminHeaderF3 actions={
                <div className="flex items-center gap-2">
                    <Auto />
                    <button onClick={load} className={ghostBtnCls} disabled={loading}>
                        <Icon name="clock" className={`size-4 fill-current ${loading ? "animate-spin" : ""}`} />
                        {loading ? "…" : "Refresh"}
                    </button>
                </div>
            } />

            {/* ── filter bar ── */}
            <div className="flex flex-wrap items-center gap-2 mb-3 max-md:flex-col max-md:items-stretch">
                <Select
                    className="min-w-[8rem] max-md:w-full"
                    value={TIME_RANGES.map((r) => ({ id: r.id, name: r.name })).find((r) => r.id === rangeId) || null}
                    onChange={(o) => setRangeId(o.id)}
                    options={TIME_RANGES.map((r) => ({ id: r.id, name: r.name }))}
                />
                <FilterSelect label="campaigns" value={filters.campaign_id || ""} values={opts.campaigns || []} onChange={(v) => setF({ campaign_id: v })} />
                <FilterSelect label="agents" value={filters.agent_name || ""} values={opts.agents || []} onChange={(v) => setF({ agent_name: v })} />
                <FilterSelect label="providers" value={filters.provider || ""} values={[...(opts.llm_providers || []), ...(opts.tts_providers || []), ...(opts.stt_providers || [])].filter((v, i, a) => v && a.indexOf(v) === i)} onChange={(v) => setF({ provider: v })} />
                <FilterSelect label="models" value={filters.model || ""} values={opts.models || []} onChange={(v) => setF({ model: v })} />
                <FilterSelect label="statuses" value={filters.status || ""} values={opts.statuses || []} onChange={(v) => setF({ status: v })} />
                <div className="w-44 max-md:w-full">
                    <Search
                        value={phoneInput}
                        onChange={(e) => setPhoneInput(e.target.value)}
                        placeholder="Phone…"
                        isGray
                    />
                </div>
                <button
                    className={ghostBtnCls}
                    onClick={() => setF({ phone: phoneInput.trim() })}
                >
                    Apply
                </button>
                {(filters.campaign_id || filters.agent_name || filters.provider || filters.model || filters.status || filters.phone) && (
                    <button className={ghostBtnCls} onClick={() => { setFilters({}); setPhoneInput(""); }}>Clear</button>
                )}
            </div>

            <ErrorBanner msg={err} />

            {/* ── KPI strip ── */}
            <div className="grid grid-cols-6 gap-3 mb-3 max-2xl:grid-cols-4 max-xl:grid-cols-3 max-md:grid-cols-2 max-sm:grid-cols-1">
                <Stat label="Calls" value={fmtNum(n(sum.calls))} sub={`${fmtNum(n(sum.total_turns))} turns`} />
                <Stat label="Avg duration" value={`${n(sum.avg_dur_s).toFixed(1)}s`} />
                <Stat label="Success rate" value={`${successPct.toFixed(1)}%`} tone={successPct < 90 && n(sum.calls) > 0 ? "#EF9D0E" : "#00A656"} sub={`${fmtNum(n(sum.failed))} failed`} />
                <Stat label="Error rate" value={`${errorPct.toFixed(2)}%`} tone={errorPct > 1 ? "#FF6A55" : undefined} sub={`${fmtNum(n(sum.errors))} errors · ${fmtNum(n(sum.rate_limits))} 429s`} />
                <Stat label="LLM p95" value={fmtMs(stageP95("llm"))} sub={`p99 ${fmtMs(n(byStage.find((r) => String(r.stage) === "llm")?.p99))}`} />
                <Stat label="TTS p95" value={fmtMs(stageP95("tts"))} sub={`STT p95 ${fmtMs(stageP95("stt"))}`} />
            </div>

            {/* ── live latency + throughput ── */}
            <div className="grid grid-cols-2 gap-3 mb-3 max-lg:grid-cols-1">
                <Panel title="Response latency" subtitle="LLM first-token p50 / p95 / p99 (ms)">
                    {latency.length === 0 ? <EmptyChart /> : (
                        <TimeSeries data={latency} unit="ms" series={[
                            { key: "p50", label: "p50", color: "#00A656" },
                            { key: "p95", label: "p95", color: "#EF9D0E" },
                            { key: "p99", label: "p99", color: "#FF6A55" },
                        ]} />
                    )}
                </Panel>
                <Panel title="Throughput" subtitle="metric events / interval">
                    {throughput.length === 0 ? <EmptyChart /> : (
                        <TimeSeries data={throughput} series={[{ key: "events", label: "Events", color: "#2A85FF", area: true }]} />
                    )}
                </Panel>
            </div>

            {/* ── per-stage latency breakdown ── */}
            <div className="grid grid-cols-2 gap-3 mb-3 max-lg:grid-cols-1">
                <Panel title="Latency by stage" subtitle="p95 per pipeline stage (ms)">
                    {stageDonut.length === 0 ? <EmptyChart /> : <Donut data={stageDonut} centerLabel="p95 ms" />}
                </Panel>
                <Panel title="Pipeline" subtitle="User speech → STT → LLM → TTS → audio (p95)">
                    <div className="flex flex-col gap-3 p-1">
                        {STAGE_ORDER.map((st) => {
                            const p95 = stageP95(st);
                            const max = Math.max(1, ...STAGE_ORDER.map((s) => stageP95(s)));
                            return (
                                <div key={st} className="flex items-center gap-3">
                                    <span className="w-24 shrink-0 text-caption text-t-secondary">{STAGE_LABEL[st]}</span>
                                    <div className="flex-1 h-3 rounded-full bg-b-surface3 overflow-hidden">
                                        <div className="h-full rounded-full" style={{ width: `${Math.min(100, (p95 / max) * 100)}%`, backgroundColor: STAGE_COLOR[st] }} />
                                    </div>
                                    <span className="w-16 shrink-0 text-right text-caption tabular-nums text-t-primary">{fmtMs(p95)}</span>
                                </div>
                            );
                        })}
                    </div>
                </Panel>
            </div>

            {/* ── per-call drill-down ── */}
            {openCall && (
                <Panel
                    title="Call timeline"
                    subtitle={openCall}
                    actions={<button className={ghostBtnCls} onClick={() => setOpenCall(null)}><Icon name="close" className="size-4 fill-current" />Close</button>}
                    className="mb-3"
                >
                    {callLoading ? <div className="py-10 text-center text-caption text-t-tertiary">Loading…</div>
                        : !callDetail || Object.keys(callDetail).length === 0 ? <EmptyChart msg="No telemetry for this call" />
                            : (
                                <>
                                    {(() => {
                                        const q = qualityScore(callDetail, callLatency);
                                        const net = String(callDetail.net_quality || "");
                                        const cavg = (st: "stt" | "eou" | "llm" | "tts") => {
                                            const v = turns.map((t) => t[st]).filter((x) => x > 0);
                                            return v.length ? Math.round(v.reduce((a, b) => a + b, 0) / v.length) : 0;
                                        };
                                        const pipes = [
                                            { label: "STT", color: STAGE_COLOR.stt, provider: String(callDetail.stt_provider || ""), model: String(callDetail.stt_model || ""), metric: `finalize ${fmtMs(cavg("stt"))}`, extra: `${fmtNum(n(callDetail.stt_calls))} utterances · speech ${(n(callDetail.speech_ms) / 1000).toFixed(1)}s` },
                                            { label: "LLM", color: STAGE_COLOR.llm, provider: String(callDetail.llm_provider || ""), model: String(callDetail.llm_model || ""), metric: `ttft ${fmtMs(cavg("llm"))}`, extra: `${fmtNum(n(callDetail.in_tokens))}↓ ${fmtNum(n(callDetail.out_tokens))}↑ tokens` },
                                            { label: "TTS", color: STAGE_COLOR.tts, provider: String(callDetail.tts_provider || ""), model: String(callDetail.tts_model || ""), metric: `ttfb ${fmtMs(cavg("tts"))}`, extra: callDetail.voice_id ? `voice ${String(callDetail.voice_name || callDetail.voice_id)} · ${fmtNum(n(callDetail.characters))} chars` : `${fmtNum(n(callDetail.characters))} chars` },
                                        ];
                                        return (
                                            <>
                                                {/* who we called + quality meter */}
                                                <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
                                                    <div>
                                                        <div className="text-h6 text-t-primary">{String(callDetail.lead_name || "Unknown caller")}</div>
                                                        <div className="text-caption text-t-tertiary">
                                                            <span className="font-mono">{String(callDetail.phone || "—")}</span>
                                                            {callDetail.campaign_id ? <> · {String(callDetail.campaign_id)}</> : null}
                                                            {callDetail.agent_name ? <> · agent {String(callDetail.agent_name)}</> : null}
                                                            {callDetail.language ? <> · {String(callDetail.language)}</> : null}
                                                        </div>
                                                    </div>
                                                    <div className="flex items-center gap-3">
                                                        <div className="text-right">
                                                            <div className="text-caption text-t-tertiary">Quality</div>
                                                            <div className="text-h5 tabular-nums leading-none" style={{ color: qualityTone(q) }}>{q}<span className="text-caption text-t-tertiary"> /100</span></div>
                                                        </div>
                                                        <Badge variant={q >= 80 ? "success" : "warning"} dot>{qualityLabel(q)}</Badge>
                                                    </div>
                                                </div>

                                                {/* response-latency rollup — avg / median / p95 / total / telecom */}
                                                <div className="grid grid-cols-2 md:grid-cols-6 gap-2.5 mb-4">
                                                    <Stat label="Avg response" value={fmtMs(n(callLatency.avg_ms))} />
                                                    <Stat label="Median response" value={fmtMs(n(callLatency.median_ms))} />
                                                    <Stat label="P95 response" value={fmtMs(n(callLatency.p95_ms))} />
                                                    <Stat label="Total latency" value={fmtMs(n(callLatency.total_ms))} sub={`across ${fmtNum(n(callDetail.turns))} turns`} />
                                                    <Stat label="Telecom" value={n(callDetail.net_rtt_ms) > 0 ? fmtMs(n(callDetail.net_rtt_ms)) : (net || "—")} sub="phone-leg network" />
                                                    <Stat label="Duration" value={`${(n(callDetail.duration_ms) / 1000).toFixed(1)}s`} />
                                                </div>

                                                {/* full pipeline: STT · LLM · TTS with provider + VERSION + metrics */}
                                                <div className="grid grid-cols-1 md:grid-cols-3 gap-2.5 mb-4">
                                                    {pipes.map((p) => (
                                                        <div key={p.label} className="rounded-2xl bg-b-surface2 ring-1 ring-s-subtle ring-inset p-3">
                                                            <div className="flex items-center gap-2 mb-1">
                                                                <span className="size-2 rounded-full" style={{ background: p.color }} />
                                                                <span className="text-caption text-t-tertiary">{p.label}</span>
                                                            </div>
                                                            <div className="text-button text-t-primary capitalize truncate">{p.provider || "—"}</div>
                                                            <div className="text-caption text-t-secondary truncate" title={p.model}>{p.model || "—"}</div>
                                                            <div className="mt-1.5 text-caption text-t-tertiary truncate" title={p.extra}>{p.metric} · {p.extra}</div>
                                                        </div>
                                                    ))}
                                                </div>

                                                {/* per-call cost — real 4-component breakdown (telephony+STT+LLM+TTS) */}
                                                {callCost && callCost.total > 0 && (
                                                    <div className="rounded-2xl bg-b-surface2 ring-1 ring-s-subtle ring-inset p-3 mb-4">
                                                        <div className="flex flex-wrap items-center justify-between gap-3">
                                                            <div>
                                                                <span className="text-caption text-t-tertiary">Call cost</span>
                                                                <div className="text-h6 tabular-nums text-t-primary">
                                                                    ₹{callCost.total.toFixed(2)}
                                                                    <span className="text-caption text-t-tertiary"> · ₹{callCost.per_min.toFixed(2)}/min · {callCost.duration_min.toFixed(1)} min</span>
                                                                </div>
                                                            </div>
                                                            <div className="flex flex-wrap gap-x-4 gap-y-1 text-caption text-t-secondary tabular-nums">
                                                                <span>TTS ₹{callCost.tts.toFixed(2)}</span>
                                                                <span>STT ₹{callCost.stt.toFixed(2)}</span>
                                                                <span>LLM ₹{callCost.llm.toFixed(2)}</span>
                                                                <span>Telephony ₹{callCost.telephony.toFixed(2)}</span>
                                                            </div>
                                                        </div>
                                                    </div>
                                                )}

                                                {/* network + per-call counters */}
                                                <div className="flex flex-wrap gap-x-5 gap-y-2 mb-4 text-caption text-t-secondary">
                                                    <span>Network <Badge variant={["EXCELLENT", "GOOD"].includes(net.toUpperCase()) ? "success" : net ? "warning" : "neutral"}>{net || "n/a"}</Badge></span>
                                                    {n(callDetail.net_rtt_ms) > 0 ? <span>RTT <span className="text-t-primary tabular-nums">{fmtMs(n(callDetail.net_rtt_ms))}</span></span> : null}
                                                    <span>429s <span className="tabular-nums" style={{ color: n(callDetail.rate_limit_429) > 0 ? "#EF9D0E" : undefined }}>{fmtNum(n(callDetail.rate_limit_429))}</span></span>
                                                    <span>Errors <span className="tabular-nums" style={{ color: n(callDetail.errors) > 0 ? "#FF6A55" : undefined }}>{fmtNum(n(callDetail.errors))}</span></span>
                                                    <span>Outcome <span className="text-t-primary">{String(callDetail.outcome || "—")}</span></span>
                                                    <span>Status <Badge variant={String(callDetail.status) === "completed" ? "success" : "warning"}>{String(callDetail.status || "—")}</Badge></span>
                                                </div>
                                            </>
                                        );
                                    })()}

                                    {/* Transcript CONTENT quality — LLM analysis of the actual dialogue */}
                                    <div className="rounded-2xl bg-b-surface2 ring-1 ring-s-subtle ring-inset p-4 mb-4">
                                        <div className="flex items-center justify-between gap-3 mb-2">
                                            <div>
                                                <div className="text-button text-t-primary">Transcript quality</div>
                                                <div className="text-caption text-t-tertiary">LLM read of the dialogue — repetition · hanging · listening · goal progress</div>
                                            </div>
                                            {quality?.ok ? (
                                                <button className={ghostBtnCls} onClick={() => analyzeQuality(true)} disabled={qualityLoading}>
                                                    <Icon name="clock" className={`size-4 fill-current ${qualityLoading ? "animate-spin" : ""}`} />{qualityLoading ? "…" : "Re-analyze"}
                                                </button>
                                            ) : (
                                                <button className="inline-flex items-center justify-center h-9 px-4 rounded-2xl bg-b-surface3 text-button text-t-primary transition-colors hover:bg-b-surface1 disabled:opacity-50" onClick={() => analyzeQuality(false)} disabled={qualityLoading}>
                                                    {qualityLoading ? "Analyzing…" : "Analyze transcript"}
                                                </button>
                                            )}
                                        </div>
                                        {qualityLoading && !quality?.ok ? (
                                            <div className="py-4 text-center text-caption text-t-tertiary">Reading the conversation…</div>
                                        ) : quality?.ok ? (
                                            <>
                                                <div className="flex items-center gap-4 mb-3">
                                                    <div className="text-h4 tabular-nums leading-none" style={{ color: qualityTone(n(quality.score)) }}>{n(quality.score)}<span className="text-caption text-t-tertiary"> /100</span></div>
                                                    <Badge variant={n(quality.score) >= 80 ? "success" : "warning"}>{String(quality.grade || "")}</Badge>
                                                    <div className="text-caption text-t-secondary flex-1">{String(quality.summary || "")}</div>
                                                </div>
                                                {quality.dims ? (
                                                    <div className="grid grid-cols-2 md:grid-cols-5 gap-2 mb-3">
                                                        {Object.entries(quality.dims).map(([k, v]) => (
                                                            <div key={k}>
                                                                <div className="flex items-center justify-between text-caption text-t-tertiary mb-0.5"><span className="capitalize">{k.replace(/_/g, " ")}</span><span className="tabular-nums">{n(v)}</span></div>
                                                                <div className="h-1.5 rounded-full bg-b-surface3 overflow-hidden"><div className="h-full rounded-full" style={{ width: `${Math.max(0, Math.min(100, n(v)))}%`, background: qualityTone(n(v)) }} /></div>
                                                            </div>
                                                        ))}
                                                    </div>
                                                ) : null}
                                                {(quality.issues || []).length > 0 ? (
                                                    <div className="space-y-2">
                                                        {(quality.issues || []).map((it, i) => (
                                                            <div key={i} className="rounded-xl bg-b-surface3/50 p-2.5">
                                                                <div className="flex items-center gap-2 text-caption mb-1">
                                                                    <span className="size-2 rounded-full shrink-0" style={{ background: it.severity === "high" ? "#FF6A55" : it.severity === "medium" ? "#EF9D0E" : "#9AA0A6" }} />
                                                                    <span className="text-t-primary capitalize">{String(it.type || "").replace(/_/g, " ")}</span>
                                                                    <span className="text-t-tertiary truncate">· {String(it.note || "")}</span>
                                                                </div>
                                                                {it.quote ? <div className="text-caption text-t-secondary italic pl-4">“{String(it.quote)}”</div> : null}
                                                            </div>
                                                        ))}
                                                    </div>
                                                ) : <div className="text-caption text-t-tertiary">No content issues flagged — clean conversation.</div>}
                                            </>
                                        ) : (
                                            <div className="text-caption text-t-tertiary">{quality && !quality.ok && quality.error && quality.error !== "not_analyzed" ? String(quality.message || quality.error) : "Not analyzed yet — grade this call's dialogue (~2¢, cached after)."}</div>
                                        )}
                                    </div>

                                    {turns.length === 0 ? <EmptyChart msg="No per-turn events" /> : (
                                        <div className="overflow-x-auto">
                                            <table className="data-table">
                                                <thead>
                                                    <tr>
                                                        <th>Turn</th><th>Stage breakdown</th>
                                                        <th className="text-right">STT</th><th className="text-right">Turn-detect</th>
                                                        <th className="text-right">LLM</th><th className="text-right">TTS</th>
                                                        <th className="text-right">Telecom</th><th className="text-right">Tokens</th>
                                                    </tr>
                                                </thead>
                                                <tbody>
                                                    {turns.map((t) => {
                                                        const total = Math.max(1, t.stt + t.eou + t.llm + t.tts);
                                                        return (
                                                            <tr key={t.turn}>
                                                                <td className="tabular-nums text-t-secondary">#{t.turn}</td>
                                                                <td className="min-w-[200px]">
                                                                    <div className="flex h-3 w-full rounded-full overflow-hidden bg-b-surface3">
                                                                        {(["stt", "eou", "llm", "tts"] as const).map((st) => t[st] > 0 && (
                                                                            <div key={st} title={`${STAGE_LABEL[st]} ${fmtMs(t[st])}`} style={{ width: `${(t[st] / total) * 100}%`, backgroundColor: STAGE_COLOR[st] }} />
                                                                        ))}
                                                                    </div>
                                                                </td>
                                                                <td className="text-right tabular-nums text-t-secondary">{t.stt ? fmtMs(t.stt) : "—"}</td>
                                                                <td className="text-right tabular-nums text-t-secondary">{t.eou ? fmtMs(t.eou) : "—"}</td>
                                                                <td className="text-right tabular-nums text-t-secondary">{t.llm ? fmtMs(t.llm) : "—"}</td>
                                                                <td className="text-right tabular-nums text-t-secondary">{t.tts ? fmtMs(t.tts) : "—"}</td>
                                                                <td className="text-right tabular-nums text-t-secondary" title="Telecom / phone-leg network RTT">{t.net ? fmtMs(t.net) : "—"}</td>
                                                                <td className="text-right tabular-nums text-t-tertiary">{t.in_tok}↓ {t.out_tok}↑</td>
                                                            </tr>
                                                        );
                                                    })}
                                                </tbody>
                                            </table>
                                        </div>
                                    )}
                                </>
                            )}
                </Panel>
            )}

            {/* ── AI stack & versions actually running ── */}
            <Panel title="Stack & versions" subtitle="the STT · LLM · TTS in use + each pipeline stage's metrics" className="mb-3">
                {stack.combos.length === 0 ? <EmptyChart msg="No stack data in this window" /> : (
                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                        <div className="space-y-2">
                            {stack.combos.slice(0, 5).map((c, i) => (
                                <div key={i} className="rounded-2xl bg-b-surface2 ring-1 ring-s-subtle ring-inset p-3 text-caption">
                                    <div className="flex items-center justify-between mb-2">
                                        <span className="text-t-secondary">{fmtNum(n(c.calls))} calls</span>
                                        <span className="text-t-tertiary">{agoMs(n(c.last_ms))}</span>
                                    </div>
                                    <div className="grid grid-cols-3 gap-2">
                                        {([["STT", c.stt_provider, c.stt_model], ["LLM", c.llm_provider, c.llm_model], ["TTS", c.tts_provider, c.tts_model]] as const).map(([lab, prov, mod]) => (
                                            <div key={lab} className="min-w-0">
                                                <div className="text-t-tertiary">{lab}</div>
                                                <div className="text-t-primary capitalize truncate">{String(prov || "—")}</div>
                                                <div className="text-t-secondary truncate" title={String(mod || "")}>{String(mod || "—")}</div>
                                            </div>
                                        ))}
                                    </div>
                                    {c.voice_id ? <div className="mt-2 text-t-tertiary">TTS voice <span className="text-t-secondary">{String(c.voice_name || c.voice_id)}</span></div> : null}
                                </div>
                            ))}
                        </div>
                        <div className="overflow-x-auto">
                            <table className="data-table">
                                <thead><tr><th>Stage</th><th className="text-right">avg</th><th className="text-right">p50</th><th className="text-right">p95</th><th className="text-right">events</th></tr></thead>
                                <tbody>
                                    {STAGE_ORDER.map((st) => {
                                        const r = stack.stages.find((x) => String(x.stage) === st);
                                        return (
                                            <tr key={st}>
                                                <td><span className="inline-flex items-center gap-1.5"><span className="size-2 rounded-full" style={{ background: STAGE_COLOR[st] }} />{STAGE_LABEL[st]}</span></td>
                                                <td className="text-right tabular-nums text-t-secondary">{r ? fmtMs(n(r.avg)) : "—"}</td>
                                                <td className="text-right tabular-nums text-t-secondary">{r ? fmtMs(n(r.p50)) : "—"}</td>
                                                <td className="text-right tabular-nums text-t-secondary">{r ? fmtMs(n(r.p95)) : "—"}</td>
                                                <td className="text-right tabular-nums text-t-tertiary">{r ? fmtNum(n(r.n)) : "—"}</td>
                                            </tr>
                                        );
                                    })}
                                </tbody>
                            </table>
                            <div className="mt-2 text-caption text-t-tertiary">
                                LLM ~{n(stack.stages.find((x) => String(x.stage) === "llm")?.tps).toFixed(0)} tok/s · {fmtNum(n(stack.stages.find((x) => String(x.stage) === "tts")?.chars))} TTS chars synthesised
                            </div>
                        </div>
                    </div>
                )}
            </Panel>

            {/* ── call list ── */}
            <Panel title="Calls" subtitle="newest first — click a row for the full per-call picture">
                {calls.length === 0 ? <EmptyChart msg="No calls in this window" /> : (
                    <div className="overflow-x-auto">
                        <table className="data-table">
                            <thead>
                                <tr>
                                    <th>When</th><th>Who we called</th><th>Phone</th><th>Campaign</th>
                                    <th>LLM</th><th>Net</th><th className="text-right">Dur</th><th className="text-right">Turns</th>
                                    <th className="text-right">429</th><th>Status</th>
                                </tr>
                            </thead>
                            <tbody>
                                {calls.map((c) => (
                                    <tr key={String(c.call_id)} className="cursor-pointer" onClick={() => openDetail(String(c.call_id))}>
                                        <td className="text-t-secondary whitespace-nowrap" title={fmtDateTime(n(c.ts_ms))}>{agoMs(n(c.ts_ms))}</td>
                                        <td className="text-t-primary truncate max-w-[140px]">{String(c.lead_name || "—")}</td>
                                        <td className="font-mono text-t-secondary">{String(c.phone || "—")}</td>
                                        <td className="text-t-secondary truncate max-w-[140px]">{String(c.campaign_id || "—")}</td>
                                        <td className="text-t-tertiary truncate max-w-[150px]">{String(c.llm_provider || "")} {String(c.llm_model || "")}</td>
                                        <td className="text-t-tertiary">{c.net_quality ? <Badge variant={["EXCELLENT", "GOOD"].includes(String(c.net_quality).toUpperCase()) ? "success" : "warning"}>{String(c.net_quality)}</Badge> : "—"}</td>
                                        <td className="text-right tabular-nums text-t-secondary">{(n(c.duration_ms) / 1000).toFixed(1)}s</td>
                                        <td className="text-right tabular-nums text-t-secondary">{fmtNum(n(c.turns))}</td>
                                        <td className="text-right tabular-nums" style={{ color: n(c.rate_limit_429) > 0 ? "#EF9D0E" : undefined }}>{fmtNum(n(c.rate_limit_429))}</td>
                                        <td><Badge variant={String(c.status) === "completed" ? "success" : "warning"} dot={String(c.status) !== "completed"}>{String(c.status || "—")}</Badge></td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}
            </Panel>
        </Layout>
    );
}

export default function VoicePerformancePage() {
    return <SuperAdminGuard><VoicePerfInner /></SuperAdminGuard>;
}
