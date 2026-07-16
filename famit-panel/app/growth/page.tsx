"use client";

// Famit Growth — Realtime All-Ads-Platform Analysis System (with proper recommendation
// for our goal). Implements the Figma: an aggregate insight strip, a per-platform card grid
// (Google / Facebook / Instagram / YouTube / LinkedIn / Twitter-X / TikTok) with metrics +
// location/device/top-ad breakdowns, an AI Summary + goal-driven Recommendation, and a Chat
// over the live ads data. Built on the Core_2 kit + a dormant-safe colocated client; edits
// only app/growth/*. With GROW_PLATFORMS_DEMO=1 the whole board renders immediately.

import { useCallback, useEffect, useRef, useState } from "react";
import Layout from "@/components/Layout";
import Card from "@/components/Card";
import Icon from "@/components/Icon";
import Badge from "@/components/Badge";
import Button from "@/components/Button";
import Select from "@/components/Select";
import Field from "@/components/Field";
import { SelectOption } from "@/types/select";
import {
    getGrowthSnapshot, recommend, chat,
    fmtMoney, fmtNum, fmtPct, statusVariant, statusLabel,
    type GrowthSnapshot, type PlatformMetric, type ReadResult,
    type RecommendResponse, type Goal,
} from "./_lib";

const PERIODS: SelectOption[] = [
    { id: 0, name: "Last 7 days" }, { id: 1, name: "Last 30 days" }, { id: 2, name: "Last 90 days" },
];
const PERIOD_VAL = ["7d", "30d", "90d"];
const GOALS: SelectOption[] = [
    { id: 0, name: "Lowest cost / outcome" }, { id: 1, name: "Most conversions" }, { id: 2, name: "Most reach" },
];
const GOAL_VAL: Goal[] = ["min_cost", "max_conversions", "max_reach"];

type ChatMsg = { role: "you" | "ai"; text: string };

/* ----------------------------------------------------------------- bits */

function Kpi({ label, glyph, value, foot, accent }: {
    label: string; glyph: string; value: React.ReactNode; foot?: React.ReactNode; accent?: string;
}) {
    return (
        <div className="kpi rise-in group">
            {accent && <span aria-hidden className="pointer-events-none absolute -top-16 -right-16 size-40 rounded-full opacity-[0.13] blur-2xl" style={{ background: accent }} />}
            <div className="kpi-label"><span className="kpi-glyph"><Icon name={glyph} className="fill-inherit" /></span>{label}</div>
            <div className="kpi-value relative z-1 !text-h5">{value}</div>
            {foot && <div className="kpi-foot relative z-1">{foot}</div>}
        </div>
    );
}

function Bar({ label, value, max, right }: { label: string; value: number; max: number; right?: string }) {
    const pct = max > 0 ? Math.max(3, Math.round((value / max) * 100)) : 0;
    return (
        <div className="flex items-center gap-2 text-caption">
            <div className="w-20 shrink-0 text-t-tertiary truncate">{label}</div>
            <div className="flex-1 h-3 rounded bg-b-surface2 ring-1 ring-s-subtle overflow-hidden">
                <div className="h-full rounded bg-primary-01/30" style={{ width: `${pct}%` }} />
            </div>
            <div className="w-16 shrink-0 text-right text-t-secondary tabular-nums">{right}</div>
        </div>
    );
}

function PlatformCard({ m }: { m: PlatformMetric }) {
    const cur = m.currency;
    const locMax = Math.max(1, ...m.by_location.map((l) => l.spend_minor));
    const dormant = m.status === "no_creds";
    return (
        <div className="card !p-4">
            <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2.5">
                    <span className="grid place-items-center size-9 rounded-xl bg-b-surface2 ring-1 ring-s-subtle fill-t-secondary">
                        <Icon name={m.icon || "promote"} className="size-5 fill-inherit" />
                    </span>
                    <div className="text-sub-title-2 text-t-primary">{m.label}</div>
                </div>
                <Badge variant={statusVariant(m.status)} dot>{statusLabel(m.status)}</Badge>
            </div>
            {dormant ? (
                <div className="text-caption text-t-tertiary py-6 text-center">
                    Connect {m.label} to see live spend, devices, locations & cost-per-outcome.
                </div>
            ) : (
                <>
                    <div className="grid grid-cols-3 gap-2 mb-3">
                        <div><div className="text-button text-t-primary tabular-nums">{fmtMoney(m.spend_minor, cur)}</div><div className="text-caption text-t-tertiary">spend</div></div>
                        <div><div className="text-button text-t-primary tabular-nums">{fmtNum(m.conversions)}</div><div className="text-caption text-t-tertiary">outcomes</div></div>
                        <div><div className="text-button text-primary-02 tabular-nums">{fmtMoney(m.cpi_minor, cur)}</div><div className="text-caption text-t-tertiary">cost/outcome</div></div>
                        <div><div className="text-body-2 text-t-secondary tabular-nums">{fmtPct(m.ctr)}</div><div className="text-caption text-t-tertiary">CTR</div></div>
                        <div><div className="text-body-2 text-t-secondary tabular-nums">{fmtMoney(m.cpc_minor, cur)}</div><div className="text-caption text-t-tertiary">CPC</div></div>
                        <div><div className="text-body-2 text-t-secondary tabular-nums">{fmtNum(m.impressions)}</div><div className="text-caption text-t-tertiary">impressions</div></div>
                    </div>
                    {/* devices */}
                    {m.by_device.length > 0 && (
                        <div className="flex items-center gap-1.5 mb-3">
                            {m.by_device.map((d) => (
                                <div key={d.name} className="flex-1 text-center">
                                    <div className="h-1.5 rounded-full bg-primary-01/30 mb-1" style={{ width: `${Math.round(d.share * 100)}%`, marginInline: "auto" }} />
                                    <div className="text-caption text-t-tertiary capitalize">{d.name} {Math.round(d.share * 100)}%</div>
                                </div>
                            ))}
                        </div>
                    )}
                    {/* top locations */}
                    {m.by_location.length > 0 && (
                        <div className="space-y-1">
                            <div className="text-caption text-t-tertiary mb-0.5">Top locations</div>
                            {m.by_location.slice(0, 3).map((l) => (
                                <Bar key={l.name} label={l.name} value={l.spend_minor} max={locMax} right={fmtMoney(l.spend_minor, cur)} />
                            ))}
                        </div>
                    )}
                </>
            )}
        </div>
    );
}

/* ============================================================== the page */

export default function GrowthPage() {
    const [periodIdx, setPeriodIdx] = useState(1);
    const [snap, setSnap] = useState<ReadResult<GrowthSnapshot> | null>(null);
    const [goalIdx, setGoalIdx] = useState(0);
    const [rec, setRec] = useState<RecommendResponse | null>(null);
    const [recBusy, setRecBusy] = useState(false);
    const [msgs, setMsgs] = useState<ChatMsg[]>([]);
    const [q, setQ] = useState("");
    const [chatBusy, setChatBusy] = useState(false);
    const chatEnd = useRef<HTMLDivElement>(null);

    const load = useCallback(async () => {
        setSnap(await getGrowthSnapshot(PERIOD_VAL[periodIdx]));
    }, [periodIdx]);
    useEffect(() => { void load(); }, [load]);
    useEffect(() => { chatEnd.current?.scrollIntoView({ behavior: "smooth" }); }, [msgs]);

    const runRecommend = async () => {
        setRecBusy(true);
        try { setRec(await recommend(GOAL_VAL[goalIdx])); }
        catch { /* dormant */ } finally { setRecBusy(false); }
    };

    const send = async () => {
        const text = q.trim();
        if (!text || chatBusy) return;
        setMsgs((m) => [...m, { role: "you", text }]); setQ(""); setChatBusy(true);
        try {
            const r = await chat(text);
            setMsgs((m) => [...m, { role: "ai", text: r.answer }]);
        } catch {
            setMsgs((m) => [...m, { role: "ai", text: "Enable Famit Growth (FEATURE_GROW=1) to chat over live data." }]);
        } finally { setChatBusy(false); }
    };

    const dormant = snap?.kind === "dormant";
    const data = snap?.kind === "ok" ? snap.data : null;
    const s = data?.summary;
    const cur = s?.currency || "INR";

    return (
        <Layout title="Famit Growth">
            <div className="mb-4">
                <div className="flex items-start justify-between gap-4 flex-wrap">
                    <div>
                        <div className="text-h6 text-t-primary">Realtime All-Ads-Platform Analysis</div>
                        <div className="text-caption text-t-tertiary">Every platform, one view — with a proper recommendation for your goal.</div>
                    </div>
                    <div className="w-44">
                        <Select value={PERIODS[periodIdx]} options={PERIODS} onChange={(o) => setPeriodIdx(o.id)} />
                    </div>
                </div>
            </div>

            {dormant ? (
                <Card title="Famit Growth">
                    <div className="state-block">
                        <span className="state-glyph"><Icon name="promote" className="fill-inherit" /></span>
                        <div className="state-title">Ads analysis is ready — not enabled yet</div>
                        <div className="state-sub max-w-md mx-auto">Set FEATURE_GROW=1 (and GROW_PLATFORMS_DEMO=1 to preview) on the backend. Connect each ad platform’s account to stream live spend, devices, locations and cost-per-outcome here.</div>
                    </div>
                </Card>
            ) : (
                <>
                    {/* aggregate insight strip */}
                    {s && (
                        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3 mb-4">
                            <Kpi label="Platforms" glyph="promote" accent="#7C5CFF"
                                value={`${s.active_platforms}/${s.total_platforms}`} foot="active / total" />
                            <Kpi label="Total spend" glyph="wallet" value={fmtMoney(s.total_spend_minor, cur)} foot={`${s.period}`} />
                            <Kpi label="Avg cost/outcome" glyph="income" accent="#22C55E"
                                value={fmtMoney(s.avg_cpi_minor, cur)} foot={`${fmtNum(s.total_conversions)} outcomes`} />
                            <Kpi label="Avg CTR" glyph="chart" value={fmtPct(s.avg_ctr)} foot={`${fmtNum(s.total_clicks)} clicks`} />
                            <Kpi label="Cheapest" glyph="check" accent="#22C55E"
                                value={s.cheapest_cpi?.label || "—"} foot={s.cheapest_cpi ? `${fmtMoney(s.cheapest_cpi.value, cur)}/outcome` : ""} />
                            <Kpi label="Same-type ads" glyph="chain"
                                value={(s.same_type_ads?.length ?? 0).toString()} foot="overlapping concepts" />
                        </div>
                    )}

                    <div className="grid lg:grid-cols-3 gap-4">
                        {/* LEFT: summary + recommendation + chat */}
                        <div className="space-y-4">
                            <Card title="AI summary & recommendation" headContent={
                                <div className="w-40"><Select value={GOALS[goalIdx]} options={GOALS} onChange={(o) => setGoalIdx(o.id)} /></div>
                            }>
                                <Button isBlack className="mb-3" onClick={runRecommend} disabled={recBusy}>
                                    {recBusy ? "Thinking…" : "Recommend for this goal"}
                                </Button>
                                {rec ? (
                                    <div className="space-y-3">
                                        <div className="text-body-2 text-t-secondary">{rec.summary_text}</div>
                                        <div className="space-y-2">
                                            {rec.recommendations.map((r, i) => (
                                                <div key={i} className="flex gap-2 items-start">
                                                    <Badge variant={r.impact === "high" ? "success" : "info"}>{r.action.replace(/_/g, " ")}</Badge>
                                                    <div className="text-caption text-t-secondary flex-1">{r.text}</div>
                                                </div>
                                            ))}
                                        </div>
                                        {rec.allocation.length > 0 && (
                                            <div className="pt-2 border-t border-s-subtle">
                                                <div className="text-caption text-t-tertiary mb-1.5">Suggested budget split</div>
                                                {rec.allocation.map((a) => (
                                                    <Bar key={a.platform} label={a.label} value={a.share} max={1} right={`${Math.round(a.share * 100)}%`} />
                                                ))}
                                            </div>
                                        )}
                                    </div>
                                ) : (
                                    <div className="text-caption text-t-tertiary">Pick a goal and get a ranked, plain-language plan + budget split across platforms.</div>
                                )}
                            </Card>

                            <Card title="Chat with your ads data">
                                <div className="h-64 overflow-y-auto space-y-2 mb-3 pr-1">
                                    {msgs.length === 0 && (
                                        <div className="text-caption text-t-tertiary">Ask: “which platform is cheapest?”, “how much did we spend?”, “what should I do for more conversions?”</div>
                                    )}
                                    {msgs.map((m, i) => (
                                        <div key={i} className={`flex ${m.role === "you" ? "justify-end" : "justify-start"}`}>
                                            <div className={`max-w-[85%] px-3 py-2 rounded-2xl text-caption ${m.role === "you" ? "bg-primary-01/20 text-t-primary" : "bg-b-surface2 ring-1 ring-s-subtle text-t-secondary"}`}>{m.text}</div>
                                        </div>
                                    ))}
                                    <div ref={chatEnd} />
                                </div>
                                <div className="flex gap-2 items-end">
                                    <div className="flex-1">
                                        <Field label="" value={q} placeholder="Ask about your ads…"
                                            onChange={(e) => setQ(e.target.value)}
                                            onKeyDown={(e: React.KeyboardEvent) => { if (e.key === "Enter") void send(); }} />
                                    </div>
                                    <Button isBlack onClick={send} disabled={chatBusy}>{chatBusy ? "…" : "Ask"}</Button>
                                </div>
                            </Card>
                        </div>

                        {/* RIGHT: per-platform cards */}
                        <div className="lg:col-span-2">
                            <div className="text-sub-title-1 text-t-primary mb-3">Platforms</div>
                            {!data ? (
                                <div className="grid sm:grid-cols-2 gap-3">{[0, 1, 2, 3].map((i) => <div key={i} className="skeleton h-56 w-full" />)}</div>
                            ) : snap?.kind === "error" ? (
                                <Card title="Platforms"><div className="text-caption text-t-tertiary">{snap.message}</div></Card>
                            ) : (
                                <div className="grid sm:grid-cols-2 gap-3">
                                    {data.platforms.map((m) => <PlatformCard key={m.platform} m={m} />)}
                                </div>
                            )}
                        </div>
                    </div>
                </>
            )}
        </Layout>
    );
}
