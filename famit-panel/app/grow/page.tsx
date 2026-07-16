"use client";

// Haptica Grow — the Revenue-Truth Signal-Loop command center (/grow).
//
// The visible surface for the moat: the AI-call/WhatsApp GROUND TRUTH is scored
// (L5: hot / warm / investor / end-user / junk + why) and fed back to Meta/Google
// as Conversions-API events with value = lead-quality score (L7), so the platforms
// hunt for people who actually buy — not form-fillers. This page shows the scored
// leads, the Signal Health card (EMQ / dedup / ladder / mode), the CAPI dispatch
// ledger, and a "try-it" scorer so an operator can see exactly how a lead grades.
//
// The /grow backend is FLAG-GATED (FEATURE_GROW) + SHADOW-by-default, so the
// graceful "not enabled yet" path is a first-class state — reads degrade to a
// premium dormant view, never an error wall. Built on the in-app Signal component
// language (Layout / Card / Icon / Badge / Button / Select / Checkbox / Field) +
// verified globals.css utilities. Edits only this route's own files (app/grow/*).

import { useCallback, useEffect, useMemo, useState } from "react";
import Layout from "@/components/Layout";
import Card from "@/components/Card";
import Icon from "@/components/Icon";
import Badge from "@/components/Badge";
import Button from "@/components/Button";
import Select from "@/components/Select";
import Checkbox from "@/components/Checkbox";
import Field from "@/components/Field";
import { SelectOption } from "@/types/select";
import { useMe, canWrite } from "@/lib/auth";
import {
    getGrowHealth,
    getGrowLeads,
    getGrowSignals,
    getGrowSummary,
    scoreLeadPreview,
    tierVariant,
    tierLabel,
    signalStatusVariant,
    signalStatusLabel,
    prettyReason,
    fmtTs,
    fmtPct,
    fmtMoney,
    type GrowHealth,
    type GrowSummary,
    type ScoredLead,
    type SignalEvent,
    type ScoreInput,
    type ReadResult,
    type LeadsResponse,
    type SignalsResponse,
} from "./_lib";

type TabKey = "funnel" | "leads" | "signals" | "tryit";
type Toast = { msg: string; type: "success" | "error" };

const TIER_FILTER: SelectOption[] = [
    { id: 0, name: "All tiers" },
    { id: 1, name: "Hot" },
    { id: 2, name: "Investor" },
    { id: 3, name: "Warm" },
    { id: 4, name: "End-user" },
    { id: 5, name: "Junk" },
];
const TIER_FILTER_VALUE = ["", "hot", "investor", "warm", "end_user", "junk"];

/* ----------------------------------------------------------------- bits */

function DormantPanel({ title, sub, children }: { title: string; sub: string; children?: React.ReactNode }) {
    return (
        <div className="state-block">
            <span className="state-glyph">
                <Icon name="promote" className="fill-inherit" />
            </span>
            <div className="state-title">{title}</div>
            <div className="state-sub max-w-md mx-auto">{sub}</div>
            {children}
        </div>
    );
}

function Kpi({ label, glyph, value, foot, accent, loading }: {
    label: string; glyph: string; value: React.ReactNode; foot?: React.ReactNode;
    accent?: string; loading?: boolean;
}) {
    return (
        <div className="kpi rise-in group">
            {accent && (
                <span aria-hidden className="pointer-events-none absolute -top-16 -right-16 size-40 rounded-full opacity-[0.13] blur-2xl"
                    style={{ background: accent }} />
            )}
            <div className="kpi-label">
                <span className="kpi-glyph"><Icon name={glyph} className="fill-inherit" /></span>
                {label}
            </div>
            {loading ? <div className="skeleton h-9 w-24 mt-1" />
                : <div className="kpi-value relative z-1 !text-h4">{value}</div>}
            {foot && <div className="kpi-foot relative z-1">{foot}</div>}
        </div>
    );
}

function ReasonChips({ reasons }: { reasons: string[] }) {
    if (!reasons?.length) return <span className="text-caption text-t-tertiary">—</span>;
    return (
        <div className="flex flex-wrap gap-1.5">
            {reasons.slice(0, 6).map((r, i) => (
                <span key={i} className="inline-flex items-center px-2 py-0.5 rounded-lg text-caption bg-b-surface2 ring-1 ring-s-subtle text-t-secondary">
                    {prettyReason(r)}
                </span>
            ))}
        </div>
    );
}

/* ============================================================== the page */

export default function GrowPage() {
    const { me } = useMe();
    const writable = canWrite(me);

    const [tab, setTab] = useState<TabKey>("funnel");
    const [toast, setToast] = useState<Toast | null>(null);
    const showToast = (msg: string, type: "success" | "error" = "success") => {
        setToast({ msg, type });
        setTimeout(() => setToast(null), 4200);
    };

    const [health, setHealth] = useState<ReadResult<GrowHealth> | null>(null);
    const [leads, setLeads] = useState<ReadResult<LeadsResponse> | null>(null);
    const [signals, setSignals] = useState<ReadResult<SignalsResponse> | null>(null);
    const [summary, setSummary] = useState<ReadResult<GrowSummary> | null>(null);
    const [tierIdx, setTierIdx] = useState(0);

    const loadHealth = useCallback(async () => setHealth(await getGrowHealth()), []);
    const loadLeads = useCallback(async () => {
        setLeads(await getGrowLeads({ tier: TIER_FILTER_VALUE[tierIdx] || undefined }));
    }, [tierIdx]);
    const loadSignals = useCallback(async () => setSignals(await getGrowSignals()), []);
    const loadSummary = useCallback(async () => setSummary(await getGrowSummary()), []);

    useEffect(() => { void loadHealth(); }, [loadHealth]);
    useEffect(() => { if (tab === "funnel") void loadSummary(); }, [tab, loadSummary]);
    useEffect(() => { if (tab === "leads") void loadLeads(); }, [tab, loadLeads]);
    useEffect(() => { if (tab === "signals") void loadSignals(); }, [tab, loadSignals]);

    const dormant = health?.kind === "dormant"
        || (health?.kind === "ok" && !health.data.enabled);

    const hd = health?.kind === "ok" ? health.data : null;
    const sh = hd?.signal_health;

    const leadRows = leads?.kind === "ok" ? leads.data.leads : [];
    const salesReadyCount = useMemo(
        () => leadRows.filter((l) => l.sales_ready).length, [leadRows]);

    return (
        <Layout title="Grow — Signal Loop">
            {/* mode banner */}
            {hd && (
                <div className="mb-4">
                    <Card title="Revenue-Truth Signal Loop" headContent={
                        <div className="flex items-center gap-2">
                            <Badge variant={sh?.mode === "live" ? "success" : "info"} dot>
                                {sh?.mode === "live" ? "Live — sending to Meta/Google" : "Shadow — logging only"}
                            </Badge>
                            <Badge variant="neutral">{hd.pack.replace(/_/g, " ")}</Badge>
                        </div>
                    }>
                        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                            <Kpi label="Signal mode" glyph="send"
                                value={sh?.mode === "live" ? "Live" : "Shadow"}
                                foot={hd.signals.meta_configured ? "Meta CAPI configured" : "Meta creds pending"}
                                accent="#7C5CFF" />
                            <Kpi label="Signals dispatched" glyph="promote"
                                value={(sh?.total ?? 0).toLocaleString()}
                                foot={`${sh?.live_dispatched ?? 0} live · ${sh?.shadow_dispatched ?? 0} shadow`} />
                            <Kpi label="Avg EMQ (est.)" glyph="link"
                                value={(sh?.avg_emq_estimate ?? 0).toFixed(1)}
                                foot="match quality 0–10 · target ≥8" accent="#22C55E" />
                            <Kpi label="Sales-ready leads" glyph="income"
                                value={salesReadyCount.toLocaleString()}
                                foot={`${leadRows.length} scored · ${fmtPct(sh?.click_id_coverage)} click-id`} />
                        </div>
                    </Card>
                </div>
            )}

            {/* tabs */}
            <div className="flex items-center gap-2 mb-4">
                {([["funnel", "Funnel & ROI"], ["leads", "Scored leads"], ["signals", "Signal ledger"], ["tryit", "Try-it scorer"]] as [TabKey, string][])
                    .map(([k, label]) => (
                        <Button key={k} isStroke={tab !== k} isBlack={tab === k}
                            onClick={() => setTab(k)}>{label}</Button>
                    ))}
            </div>

            {dormant ? (
                <Card title="Haptica Grow">
                    <DormantPanel
                        title="Signal Loop is ready — not enabled yet"
                        sub="Set FEATURE_GROW=1 on the backend to turn on lead scoring and the CAPI signal loop. It runs in SHADOW (logging the would-send conversion events, sending nothing) until Meta CAPI creds + GROW_SIGNALS_LIVE=1 are set — so enabling it carries zero live-spend risk." />
                </Card>
            ) : tab === "funnel" ? (
                <FunnelTab result={summary} loading={!summary} />
            ) : tab === "leads" ? (
                <LeadsTab rows={leadRows} loading={!leads} result={leads} tierIdx={tierIdx}
                    onTier={(i) => setTierIdx(i)} hotThreshold={hd?.thresholds.hot ?? 70} />
            ) : tab === "signals" ? (
                <SignalsTab result={signals} loading={!signals} health={sh} />
            ) : (
                <TryItTab writable={writable} onResult={() => void loadHealth()} showToast={showToast} />
            )}

            {toast && (
                <div className={`fixed bottom-6 right-6 z-50 px-4 py-3 rounded-xl shadow-lg text-button ${
                    toast.type === "success" ? "bg-primary-02 text-white" : "bg-primary-03 text-white"}`}>
                    {toast.msg}
                </div>
            )}
        </Layout>
    );
}

/* ----------------------------------------------------------------- funnel tab */

function FunnelTab({ result, loading }: { result: ReadResult<GrowSummary> | null; loading: boolean }) {
    if (loading) return <Card title="Funnel & ROI"><div className="space-y-2">{[0, 1, 2, 3].map((i) => <div key={i} className="skeleton h-12 w-full" />)}</div></Card>;
    if (result?.kind === "error") return <Card title="Funnel & ROI"><DormantPanel title="Couldn't load metrics" sub={result.message} /></Card>;
    if (result?.kind !== "ok") return <Card title="Funnel & ROI"><DormantPanel title="No data yet" sub="Metrics appear once leads start flowing through the loop." /></Card>;
    const s = result.data;
    const roi = s.roi;
    const tierEntries = Object.entries(s.tier_distribution).filter(([, v]) => v > 0);
    const sources = Object.entries(s.by_source);

    return (
        <div className="space-y-4">
            {/* ROI strip */}
            <Card title="Return on spend" headContent={
                <Badge variant={roi.spend_connected ? "success" : "neutral"} dot>
                    {roi.spend_connected ? "Spend connected" : "Connect ad spend for ₹/outcome"}
                </Badge>
            }>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                    <Kpi label="Cost / qualified (CPqL)" glyph="income" accent="#22C55E"
                        value={roi.spend_connected ? fmtMoney(roi.cpql_minor, roi.currency) : "—"}
                        foot="north star · cost per REAL outcome" />
                    <Kpi label="Cost / lead (CPL)" glyph="promote"
                        value={roi.spend_connected ? fmtMoney(roi.cpl_minor, roi.currency) : "—"}
                        foot={`${roi.leads} leads`} />
                    <Kpi label="Cost / booking" glyph="calendar"
                        value={roi.spend_connected ? fmtMoney(roi.cost_per_booking_minor, roi.currency) : "—"}
                        foot={`${roi.booked} booked`} />
                    <Kpi label="Cost / won" glyph="wallet"
                        value={roi.spend_connected ? fmtMoney(roi.cost_per_won_minor, roi.currency) : "—"}
                        foot={`${roi.won} won`} />
                </div>
            </Card>

            {/* the funnel */}
            <Card title="Stranger → buyer funnel">
                <div className="space-y-2.5">
                    {s.funnel.stages.map((st) => (
                        <div key={st.key} className="flex items-center gap-3">
                            <div className="w-40 shrink-0 text-body-2 text-t-secondary">{st.label}</div>
                            <div className="flex-1 h-7 rounded-lg bg-b-surface2 ring-1 ring-s-subtle overflow-hidden relative">
                                <div className="h-full rounded-lg bg-primary-01/25"
                                    style={{ width: `${Math.max(2, Math.round(st.of_captured * 100))}%` }} />
                                <span className="absolute inset-y-0 left-2 flex items-center text-caption text-t-primary tabular-nums">
                                    {st.count.toLocaleString()}
                                </span>
                            </div>
                            <div className="w-28 shrink-0 text-right text-caption text-t-tertiary tabular-nums">
                                {Math.round(st.of_captured * 100)}% of top
                                {st.step_rate != null && <span className="text-t-secondary"> · {Math.round(st.step_rate * 100)}% step</span>}
                            </div>
                        </div>
                    ))}
                </div>
            </Card>

            <div className="grid md:grid-cols-2 gap-4">
                {/* tier mix */}
                <Card title="Lead quality mix">
                    {tierEntries.length === 0 ? (
                        <div className="text-caption text-t-tertiary">No scored leads yet.</div>
                    ) : (
                        <div className="space-y-2">
                            {tierEntries.map(([tier, count]) => (
                                <div key={tier} className="flex items-center justify-between">
                                    <Badge variant={tierVariant(tier)}>{tierLabel(tier)}</Badge>
                                    <span className="tabular-nums text-t-primary">{count}</span>
                                </div>
                            ))}
                        </div>
                    )}
                </Card>

                {/* per-source + SLA */}
                <Card title="By platform · speed">
                    <div className="space-y-1.5 mb-4">
                        {sources.length === 0 ? <div className="text-caption text-t-tertiary">No sources yet.</div> :
                            sources.map(([src, v]) => (
                                <div key={src} className="flex items-center justify-between text-body-2">
                                    <span className="text-t-secondary capitalize">{src}</span>
                                    <span className="tabular-nums text-t-tertiary">
                                        {v.leads} leads · <span className="text-primary-02">{v.qualified} qualified</span>
                                    </span>
                                </div>
                            ))}
                    </div>
                    <div className="pt-3 border-t border-s-subtle grid grid-cols-3 gap-2 text-center">
                        <div><div className="text-h5 tabular-nums text-t-primary">{fmtPct(s.sla.sla_met_rate)}</div><div className="text-caption text-t-tertiary">&lt;60s SLA</div></div>
                        <div><div className="text-h5 tabular-nums text-t-primary">{(s.sla.p50_latency_ms / 1000).toFixed(1)}s</div><div className="text-caption text-t-tertiary">p50 to fire</div></div>
                        <div><div className="text-h5 tabular-nums text-t-primary">{(s.sla.p95_latency_ms / 1000).toFixed(1)}s</div><div className="text-caption text-t-tertiary">p95 to fire</div></div>
                    </div>
                </Card>
            </div>
        </div>
    );
}

/* ----------------------------------------------------------------- leads tab */

function LeadsTab({ rows, loading, result, tierIdx, onTier, hotThreshold }: {
    rows: ScoredLead[]; loading: boolean; result: ReadResult<LeadsResponse> | null;
    tierIdx: number; onTier: (i: number) => void; hotThreshold: number;
}) {
    return (
        <Card title="Scored leads" headContent={
            <div className="w-44">
                <Select value={TIER_FILTER[tierIdx]} options={TIER_FILTER}
                    onChange={(o) => onTier(o.id)} />
            </div>
        }>
            {loading ? (
                <div className="space-y-2">{[0, 1, 2, 3].map((i) => <div key={i} className="skeleton h-14 w-full" />)}</div>
            ) : result?.kind === "error" ? (
                <DormantPanel title="Couldn't load leads" sub={result.message} />
            ) : rows.length === 0 ? (
                <DormantPanel title="No scored leads yet"
                    sub={`Leads are scored automatically after each AI call. A lead clears HOT at ${hotThreshold}+. Run a campaign or use the Try-it scorer to preview the rubric.`} />
            ) : (
                <div className="overflow-x-auto">
                    <table className="w-full text-left border-collapse">
                        <thead>
                            <tr className="text-caption text-t-tertiary border-b border-s-subtle">
                                <th className="py-2.5 pr-3 font-normal">Lead</th>
                                <th className="py-2.5 px-3 font-normal">Tier</th>
                                <th className="py-2.5 px-3 font-normal tabular-nums">Score</th>
                                <th className="py-2.5 px-3 font-normal tabular-nums">Conf.</th>
                                <th className="py-2.5 px-3 font-normal">Why</th>
                                <th className="py-2.5 px-3 font-normal">Source</th>
                                <th className="py-2.5 pl-3 font-normal">Scored</th>
                            </tr>
                        </thead>
                        <tbody>
                            {rows.map((l) => (
                                <tr key={l.lead_id} className="border-b border-s-subtle/60 align-top">
                                    <td className="py-3 pr-3">
                                        <div className="text-body-2 text-t-primary">{l.phone_masked || l.lead_id}</div>
                                        {l.sales_ready && <span className="text-caption text-primary-02">→ route to sales</span>}
                                    </td>
                                    <td className="py-3 px-3"><Badge variant={tierVariant(l.tier)}>{tierLabel(l.tier)}</Badge></td>
                                    <td className="py-3 px-3 tabular-nums text-t-primary">{l.score}</td>
                                    <td className="py-3 px-3 tabular-nums text-t-secondary">{fmtPct(l.confidence)}</td>
                                    <td className="py-3 px-3 max-w-md"><ReasonChips reasons={l.reasons} /></td>
                                    <td className="py-3 px-3 text-caption text-t-secondary">{l.source_platform || "—"}</td>
                                    <td className="py-3 pl-3 text-caption text-t-tertiary whitespace-nowrap">{fmtTs(l.scored_at)}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            )}
        </Card>
    );
}

/* --------------------------------------------------------------- signals tab */

function SignalsTab({ result, loading, health }: {
    result: ReadResult<SignalsResponse> | null; loading: boolean;
    health?: GrowHealth["signal_health"];
}) {
    const rows: SignalEvent[] = result?.kind === "ok" ? result.data.signals : [];
    return (
        <div className="space-y-4">
            {health && (
                <Card title="Signal health">
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                        <Kpi label="Dedup rate" glyph="check" value={fmtPct(health.dedup_rate)}
                            foot="idempotent re-sends" />
                        <Kpi label="Click-ID coverage" glyph="chain" value={fmtPct(health.click_id_coverage)}
                            foot="CTWA / fbc keyed" />
                        <Kpi label="Failed" glyph="block" value={(health.failed ?? 0).toLocaleString()}
                            foot="dispatch errors" />
                        <Kpi label="Ladder steps" glyph="chart"
                            value={Object.keys(health.ladder_coverage || {}).length}
                            foot={Object.entries(health.ladder_coverage || {}).map(([k, v]) => `${k}:${v}`).join(" · ") || "—"} />
                    </div>
                </Card>
            )}
            <Card title="CAPI dispatch ledger">
                {loading ? (
                    <div className="space-y-2">{[0, 1, 2].map((i) => <div key={i} className="skeleton h-12 w-full" />)}</div>
                ) : rows.length === 0 ? (
                    <DormantPanel title="No signals dispatched yet"
                        sub="Each scored lead fires a CAPI 'Lead' event (value = score); a qualified lead also fires 'QualifiedLead'. They appear here the moment a call finalizes." />
                ) : (
                    <div className="overflow-x-auto">
                        <table className="w-full text-left border-collapse">
                            <thead>
                                <tr className="text-caption text-t-tertiary border-b border-s-subtle">
                                    <th className="py-2.5 pr-3 font-normal">Event</th>
                                    <th className="py-2.5 px-3 font-normal">Status</th>
                                    <th className="py-2.5 px-3 font-normal tabular-nums">Value</th>
                                    <th className="py-2.5 px-3 font-normal tabular-nums">EMQ</th>
                                    <th className="py-2.5 px-3 font-normal">Match keys</th>
                                    <th className="py-2.5 px-3 font-normal">Platform</th>
                                    <th className="py-2.5 pl-3 font-normal">When</th>
                                </tr>
                            </thead>
                            <tbody>
                                {rows.map((s) => (
                                    <tr key={s.event_id} className="border-b border-s-subtle/60">
                                        <td className="py-3 pr-3 text-body-2 text-t-primary">{s.event_name}</td>
                                        <td className="py-3 px-3">
                                            <Badge variant={signalStatusVariant(s.status)}>{signalStatusLabel(s.status)}</Badge>
                                        </td>
                                        <td className="py-3 px-3 tabular-nums text-t-secondary">{s.value} {s.currency}</td>
                                        <td className="py-3 px-3 tabular-nums text-t-secondary">{s.emq_estimate.toFixed(1)}</td>
                                        <td className="py-3 px-3 text-caption text-t-secondary">{s.match_keys.join(", ") || "—"}</td>
                                        <td className="py-3 px-3 text-caption text-t-secondary">{s.platform}/{s.endpoint}</td>
                                        <td className="py-3 pl-3 text-caption text-t-tertiary whitespace-nowrap">{fmtTs(s.dispatched_at)}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}
            </Card>
        </div>
    );
}

/* ---------------------------------------------------------------- try-it tab */

const BOOL_FIELDS: { key: keyof ScoreInput; label: string }[] = [
    { key: "call_answered", label: "Call answered" },
    { key: "budget_mentioned", label: "Budget mentioned" },
    { key: "timeline_mentioned", label: "Timeline mentioned" },
    { key: "decision_authority", label: "Decision-maker" },
    { key: "site_visit_ready", label: "Site-visit ready" },
    { key: "booking_made", label: "Booking made" },
    { key: "investor_intent", label: "Investor intent" },
    { key: "end_user_intent", label: "End-user intent" },
    { key: "wa_replied", label: "Replied on WhatsApp" },
];

function TryItTab({ writable, onResult, showToast }: {
    writable: boolean; onResult: () => void; showToast: (m: string, t?: "success" | "error") => void;
}) {
    const [input, setInput] = useState<ScoreInput>({
        phone: "", call_duration_s: 0, interest_score: 0, wa_depth: 0, phone_valid: true,
    });
    const [busy, setBusy] = useState(false);
    const [result, setResult] = useState<ScoredLead | null>(null);

    const setBool = (k: keyof ScoreInput, v: boolean) => setInput((s) => ({ ...s, [k]: v }));
    const setNum = (k: keyof ScoreInput, v: string) =>
        setInput((s) => ({ ...s, [k]: Math.max(0, parseInt(v || "0", 10) || 0) }));

    const run = async () => {
        setBusy(true);
        try {
            const r = await scoreLeadPreview(input);
            setResult(r);
        } catch (e) {
            showToast(e instanceof Error ? e.message : "Scoring failed", "error");
        } finally {
            setBusy(false);
        }
    };

    return (
        <div className="grid md:grid-cols-2 gap-4">
            <Card title="Try-it scorer">
                <p className="text-caption text-t-tertiary mb-4">
                    Preview how the L5 rubric grades a lead — no data is stored or dispatched.
                </p>
                <div className="grid grid-cols-2 gap-3 mb-4">
                    <Field label="Phone (optional)" type="tel" value={input.phone || ""}
                        onChange={(e) => setInput((s) => ({ ...s, phone: e.target.value }))} placeholder="+91…" />
                    <Field label="Source" value={input.source_platform || ""}
                        onChange={(e) => setInput((s) => ({ ...s, source_platform: e.target.value }))} placeholder="meta / google / manual" />
                    <Field label="Call duration (s)" type="number" value={String(input.call_duration_s ?? 0)}
                        onChange={(e) => setNum("call_duration_s", e.target.value)} />
                    <Field label="Agent interest (0–100)" type="number" value={String(input.interest_score ?? 0)}
                        onChange={(e) => setNum("interest_score", e.target.value)} />
                </div>
                <div className="grid grid-cols-2 gap-2.5 mb-5">
                    {BOOL_FIELDS.map(({ key, label }) => (
                        <Checkbox key={key} label={label} checked={!!input[key]}
                            onChange={(v) => setBool(key, v)} />
                    ))}
                </div>
                <Button isBlack onClick={run} disabled={busy || !writable}>
                    {busy ? "Scoring…" : "Score this lead"}
                </Button>
                {!writable && <div className="text-caption text-t-tertiary mt-2">Read-only role.</div>}
            </Card>

            <Card title="Result">
                {!result ? (
                    <DormantPanel title="No score yet" sub="Set the signals on the left and run the scorer to see the tier, score, and the human-readable reasons the engine used." />
                ) : (
                    <div>
                        <div className="flex items-center gap-4 mb-4">
                            <div className="text-h2 tabular-nums text-t-primary">{result.score}</div>
                            <div>
                                <Badge variant={tierVariant(result.tier)}>{tierLabel(result.tier)}</Badge>
                                <div className="text-caption text-t-tertiary mt-1">
                                    confidence {fmtPct(result.confidence)} · {result.sales_ready ? "sales-ready" : "nurture"}
                                </div>
                            </div>
                        </div>
                        <div className="text-caption text-t-tertiary mb-2">Why this score</div>
                        <ReasonChips reasons={result.reasons} />
                    </div>
                )}
            </Card>
        </div>
    );
}
