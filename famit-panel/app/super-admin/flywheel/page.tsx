"use client";

// ============================================================
// HAPTICA FLYWHEEL — /super-admin/flywheel
// The read/approve console over the backend RLHF/RLAIF self-improvement engine
// (prefix /flywheel). Six sections, each its own data load:
//   Overview    — the flywheel cockpit: moat size, % outcome-anchored, judge↔outcome
//                 correlation, coverage grid, and a LOUD Goodhart-canary monitor strip.
//   Moves       — which play lifts the booking rate (lift is the hero column).
//   Bandit      — the contextual-bandit arm leaderboard (Beta posterior mean as %).
//   Moat        — the preference-pair browser (chosen vs rejected, honesty badges).
//   Challengers — proposed config changes; promotion is HUMAN-gated (Approve / Reject).
//   Labels      — the human calibration queue (good/bad) that tunes the judge.
// White-labeled + dormant-safe: when FLYWHEEL_ENABLED is off the loaders resolve to
// empty shapes (api.ts 404 → empty) and we render a friendly enable card. Never throws
// in render — every loader catches and surfaces via <ErrorBanner>. Mirrors the
// voice-performance / research page primitives EXACTLY; no invented styling.
// ============================================================

import { useCallback, useEffect, useMemo, useState } from "react";
import Layout from "@/components/Layout";
import Icon from "@/components/Icon";
import Badge from "@/components/Badge";
import {
    getFlywheelHealth, getFlywheelDashboard, getFlywheelMoves, getFlywheelBandit,
    getFlywheelPreferences, getFlywheelChallengers, getFlywheelLabels, getFlywheelMonitors,
    approveFlywheelChallenger, rejectFlywheelChallenger, submitFlywheelLabel,
    getFlywheelCausal, getFlywheelCritic, getFlywheelPolicy, getFlywheelPlayLibrary,
    getFlywheelArchetypes, getFlywheelSimRollouts, getFlywheelDistill,
    type FlywheelHealth, type FlywheelDashboard, type FlywheelMove, type FlywheelArm,
    type FlywheelPair, type FlywheelChallenger, type FlywheelLabel, type FlywheelMonitor,
    type FlywheelCATE, type FlywheelCritic, type FlywheelPolicy, type FlywheelPlay,
    type FlywheelArchetype, type FlywheelSimRollout, type FlywheelDistillRun,
} from "@/lib/api";
import { useMe, isAdmin } from "@/lib/auth";
import {
    SuperAdminGuard, SuperAdminHeaderF3, ErrorBanner, HeroCard, StatusPill,
    ghostBtnCls, num, ago,
} from "../_shared";
import { Panel, EmptyChart, useAutoRefresh } from "../_obs";
import type { VendorAccountStatus } from "@/lib/api";

// ── tabs ────────────────────────────────────────────────────────────────────
const TABS = [
    { key: "overview", label: "Overview" },
    { key: "moves", label: "Moves" },
    { key: "causal", label: "Causal" },
    { key: "critic", label: "Critic" },
    { key: "policy", label: "Policy" },
    { key: "world", label: "World Model" },
    { key: "bandit", label: "Bandit" },
    { key: "moat", label: "Moat" },
    { key: "challengers", label: "Challengers" },
    { key: "labels", label: "Labels" },
] as const;
type TabKey = (typeof TABS)[number]["key"];

const tabCls = (active: boolean) =>
    `shrink-0 inline-flex items-center justify-center h-9 px-4 rounded-full text-button transition-colors ${
        active
            ? "bg-b-surface2 text-t-primary ring-1 ring-inset ring-s-subtle"
            : "text-t-secondary hover:bg-b-surface2/60 hover:text-t-primary"
    }`;

// ── tiny formatting helpers (mirrors _obs / research conventions) ────────────
const dec = (v: number | null | undefined, dp = 2): string =>
    v == null || Number.isNaN(v) ? "—" : v.toFixed(dp);
// chosen→1 / rejected→0 fraction is sometimes already a percentage; treat <=1 as fraction.
const asPct = (v: number | null | undefined, dp = 1): string =>
    v == null || Number.isNaN(v) ? "—" : Math.abs(v) <= 1 ? `${(v * 100).toFixed(dp)}%` : `${v.toFixed(dp)}%`;

// a known challenger status → the shared StatusPill (cast onto the vendor-status map).
function ChallengerStatus({ status }: { status: string }) {
    const map: Record<string, VendorAccountStatus> = {
        proposed: "trial",
        shadow: "trial",
        approved: "active",
        promoted: "active",
        rejected: "disabled",
        expired: "expired",
        archived: "expired",
    };
    return <StatusPill status={map[status] ?? "suspended"} />;
}

function Inner() {
    const { me } = useMe();
    const admin = isAdmin(me);
    const [tab, setTab] = useState<TabKey>("overview");

    // ── Overview state ──
    const [ovLoading, setOvLoading] = useState(true);
    const [ovErr, setOvErr] = useState("");
    const [health, setHealth] = useState<FlywheelHealth | null>(null);
    const [dash, setDash] = useState<FlywheelDashboard | null>(null);
    const [monitors, setMonitors] = useState<FlywheelMonitor[]>([]);

    const loadOverview = useCallback(() => {
        setOvLoading(true);
        setOvErr("");
        Promise.all([getFlywheelHealth(), getFlywheelDashboard(43200), getFlywheelMonitors(43200)])
            .then(([h, d, m]) => {
                setHealth(h);
                setDash(d);
                setMonitors(m.monitors || []);
                if (d.error || m.error) setOvErr(d.error || m.error || "");
            })
            .catch((e) => setOvErr(e?.message || "Failed to load flywheel overview"))
            .finally(() => setOvLoading(false));
    }, []);

    useEffect(() => { loadOverview(); }, [loadOverview]);
    const Auto = useAutoRefresh(loadOverview, 30000);

    // dormant: engine off OR no signal anywhere.
    const dormant = useMemo(() => {
        if (!dash) return false;
        const off = dash.enabled === false || (health && !health.enabled);
        const empty =
            (dash.trajectory?.calls || 0) === 0 &&
            (dash.preferences?.pairs || 0) === 0 &&
            (dash.coverage_grid?.length || 0) === 0 &&
            monitors.length === 0;
        return Boolean(off) || empty;
    }, [dash, health, monitors]);

    return (
        <Layout title="Flywheel">
            <SuperAdminHeaderF3 actions={
                <div className="flex items-center gap-2">
                    {tab === "overview" && <Auto />}
                    <button onClick={() => window.location.reload()} className={ghostBtnCls}>
                        <Icon name="clock" className="size-4 fill-current" />
                        Refresh
                    </button>
                </div>
            } />

            {/* engine status ribbon */}
            {health && (
                <div className="flex flex-wrap items-center gap-2 mb-4 text-caption text-t-tertiary">
                    <Badge variant={health.active ? "success" : "neutral"} dot={health.active}>
                        {health.active ? "Flywheel active" : "Dormant"}
                    </Badge>
                    {health.judge_enabled && <Badge variant="info">Judge {health.judge_model || "on"} · {asPct(health.judge_sample_rate, 0)} sampled</Badge>}
                    {health.bandit_enabled && <Badge variant="info">Bandit ε {dec(health.bandit_epsilon, 2)}</Badge>}
                    {health.optimizer_enabled && <Badge variant="info">Optimizer</Badge>}
                    <Badge variant={health.auto_promote ? "warning" : "neutral"}>
                        {health.auto_promote ? "Auto-promote ON" : "Human-gated promotion"}
                    </Badge>
                    {health.rubric_version && <span>rubric {health.rubric_version}</span>}
                    {health.holdout_pct > 0 && <span>· {asPct(health.holdout_pct, 0)} holdout</span>}
                </div>
            )}

            {/* tab strip */}
            <div className="flex flex-wrap gap-1 mb-5">
                {TABS.map((t) => (
                    <button key={t.key} onClick={() => setTab(t.key)} className={tabCls(tab === t.key)}>
                        {t.label}
                    </button>
                ))}
            </div>

            {tab === "overview" && (
                <OverviewTab
                    loading={ovLoading} err={ovErr} dormant={dormant}
                    dash={dash} monitors={monitors}
                />
            )}
            {tab === "moves" && <MovesTab />}
            {tab === "causal" && <CausalTab />}
            {tab === "critic" && <CriticTab />}
            {tab === "policy" && <PolicyTab />}
            {tab === "world" && <WorldModelTab />}
            {tab === "bandit" && <BanditTab />}
            {tab === "moat" && <MoatTab />}
            {tab === "challengers" && <ChallengersTab admin={admin} autoPromote={Boolean(health?.auto_promote)} />}
            {tab === "labels" && <LabelsTab admin={admin} />}
        </Layout>
    );
}

// ── friendly dormant card (research/obs pattern) ─────────────────────────────
function DormantCard() {
    return (
        <div className="rounded-3xl bg-b-surface2 ring-1 ring-s-subtle ring-inset p-10 text-center">
            <div className="mx-auto mb-4 grid size-12 place-items-center rounded-2xl bg-b-surface3">
                <Icon name="layers" className="size-6 fill-t-tertiary" />
            </div>
            <div className="text-h6 text-t-primary mb-1.5">The flywheel is dormant</div>
            <p className="mx-auto max-w-md text-body-2 text-t-tertiary">
                Set <code className="px-1.5 py-0.5 rounded bg-b-surface3 text-t-secondary">FLYWHEEL_ENABLED=1</code> on the
                agent worker to start collecting trajectories, judging turns, and building the preference moat. Signals
                appear here as calls flow — promotion of any learned change stays human-gated.
            </p>
        </div>
    );
}

// ════════════════════════════════════════════════════════════════════════════
// OVERVIEW
// ════════════════════════════════════════════════════════════════════════════
function OverviewTab({ loading, err, dormant, dash, monitors }: {
    loading: boolean; err: string; dormant: boolean;
    dash: FlywheelDashboard | null; monitors: FlywheelMonitor[];
}) {
    const tr = dash?.trajectory;
    const pr = dash?.preferences;

    const outcomeAnchoredPct = pr && pr.pairs > 0 ? pr.outcome_anchored / pr.pairs : null;
    const highConfPct = pr?.pair_conf ?? null; // 0..1 share of high-confidence pairs
    const judgeCorr = useMemo(() => {
        const m = monitors.find((x) =>
            /judge.*(outcome|corr)|corr/i.test(x.metric));
        return m?.value;
    }, [monitors]);

    if (err) {
        return (
            <>
                <ErrorBanner msg={err} />
                {!loading && dormant && <DormantCard />}
            </>
        );
    }
    if (!loading && dormant) return <DormantCard />;

    return (
        <div className="space-y-5">
            {/* HERO KPIs */}
            <div className="grid grid-cols-6 gap-3 max-2xl:grid-cols-3 max-md:grid-cols-2 max-sm:grid-cols-1">
                <HeroCard label="Moat size" glyph="layers" accent="var(--primary-01)"
                    value={num(pr?.pairs)} foot="preference pairs" loading={loading} delay={0} />
                <HeroCard label="Outcome-anchored" glyph="check-circle" glyphClass="fill-primary-02"
                    value={asPct(outcomeAnchoredPct)} foot={`${num(pr?.outcome_anchored)} of ${num(pr?.pairs)}`}
                    loading={loading} delay={40} />
                <HeroCard label="High-confidence" glyph="chart" glyphClass="fill-primary-04"
                    value={asPct(highConfPct)} foot="pair confidence" loading={loading} delay={80} />
                <HeroCard label="Calls captured" glyph="profile"
                    value={num(tr?.calls)} foot={`${num(tr?.turns)} turns`} loading={loading} delay={120} />
                <HeroCard label="Avg reward" glyph="arrow"
                    value={dec(tr?.avg_reward, 3)} foot={`${num(tr?.judged_turns)} judged`} loading={loading} delay={160} />
                <HeroCard label="Judge↔outcome corr" glyph="help"
                    value={judgeCorr == null ? "—" : dec(judgeCorr, 2)} foot="from monitors"
                    loading={loading} delay={200} />
            </div>

            {/* GOODHART CANARY — loud on breach */}
            <Panel title="Goodhart monitors" subtitle="proxy metrics vs guardrail thresholds — a red pill means the optimizer may be gaming a proxy">
                {loading ? (
                    <div className="py-8 text-center text-caption text-t-tertiary">Loading…</div>
                ) : monitors.length === 0 ? (
                    <EmptyChart msg="No monitor samples in window" />
                ) : (
                    <div className="flex flex-wrap gap-2.5 p-1">
                        {monitors.map((m, i) => (
                            <div key={`${m.metric}-${m.arm_id}-${i}`}
                                className={`min-w-[10rem] rounded-2xl px-3.5 py-2.5 ring-1 ring-inset ${
                                    m.threshold_breached
                                        ? "bg-primary-03/10 ring-primary-03/40"
                                        : "bg-b-surface3 ring-s-subtle"
                                }`}>
                                <div className="flex items-center justify-between gap-2">
                                    <span className="text-caption text-t-secondary truncate">{m.metric}</span>
                                    {m.threshold_breached && <Badge variant="danger" dot>Breached</Badge>}
                                </div>
                                <div className="mt-1 text-h6 tabular-nums leading-none"
                                    style={{ color: m.threshold_breached ? "var(--primary-03)" : "var(--text-primary)" }}>
                                    {dec(m.value, 3)}
                                </div>
                                <div className="mt-1 text-[11px] text-t-tertiary">
                                    {m.arm_id ? `arm ${m.arm_id} · ` : ""}{ago(m.ts)}
                                </div>
                            </div>
                        ))}
                    </div>
                )}
            </Panel>

            {/* COVERAGE GRID — objection_type × lead_temperature counts */}
            <Panel title="Coverage grid" subtitle="how much signal we have per objection × lead-temperature bucket">
                {loading ? (
                    <div className="py-8 text-center text-caption text-t-tertiary">Loading…</div>
                ) : !dash?.coverage_grid?.length ? (
                    <EmptyChart msg="No coverage yet" />
                ) : (
                    <CoverageGrid cells={dash.coverage_grid} />
                )}
            </Panel>
        </div>
    );
}

function CoverageGrid({ cells }: { cells: FlywheelDashboard["coverage_grid"] }) {
    const temps = useMemo(
        () => Array.from(new Set(cells.map((c) => c.lead_temperature))).filter(Boolean).sort(),
        [cells]);
    const objs = useMemo(
        () => Array.from(new Set(cells.map((c) => c.objection_type))).filter(Boolean).sort(),
        [cells]);
    const lookup = useMemo(() => {
        const m = new Map<string, number>();
        for (const c of cells) m.set(`${c.objection_type}|${c.lead_temperature}`, (m.get(`${c.objection_type}|${c.lead_temperature}`) || 0) + c.n);
        return m;
    }, [cells]);
    const max = useMemo(() => Math.max(1, ...cells.map((c) => c.n)), [cells]);

    return (
        <div className="overflow-x-auto">
            <table className="data-table">
                <thead>
                    <tr>
                        <th>Objection \ Temp</th>
                        {temps.map((t) => <th key={t} className="text-right">{t}</th>)}
                    </tr>
                </thead>
                <tbody>
                    {objs.map((o) => (
                        <tr key={o}>
                            <td className="text-t-primary">{o}</td>
                            {temps.map((t) => {
                                const v = lookup.get(`${o}|${t}`) || 0;
                                const a = v > 0 ? 0.08 + 0.42 * (v / max) : 0;
                                return (
                                    <td key={t} className="text-right tabular-nums"
                                        style={{ background: v > 0 ? `rgba(108,114,255,${a})` : undefined }}>
                                        <span className={v > 0 ? "text-t-primary" : "text-t-tertiary"}>{v > 0 ? num(v) : "·"}</span>
                                    </td>
                                );
                            })}
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    );
}

// ════════════════════════════════════════════════════════════════════════════
// MOVES — which play is positive / negative. lift is the hero column.
// ════════════════════════════════════════════════════════════════════════════
function MovesTab() {
    const [loading, setLoading] = useState(true);
    const [err, setErr] = useState("");
    const [moves, setMoves] = useState<FlywheelMove[]>([]);
    const [vertical, setVertical] = useState("");

    const load = useCallback((v: string) => {
        setLoading(true);
        setErr("");
        getFlywheelMoves(v)
            .then((r) => { setMoves(r.moves || []); if (r.error) setErr(r.error); })
            .catch((e) => setErr(e?.message || "Failed to load moves"))
            .finally(() => setLoading(false));
    }, []);

    useEffect(() => { load(vertical); }, [load, vertical]);

    const sorted = useMemo(() => [...moves].sort((a, b) => (b.lift || 0) - (a.lift || 0)), [moves]);

    return (
        <div className="space-y-3">
            <ErrorBanner msg={err} />
            <div className="flex items-center gap-2">
                <input
                    value={vertical}
                    onChange={(e) => setVertical(e.target.value)}
                    placeholder="Filter vertical…"
                    className="h-9 px-3 rounded-full bg-b-surface2 ring-1 ring-inset ring-s-subtle text-caption text-t-primary placeholder:text-t-tertiary focus:outline-none focus:ring-s-highlight w-48"
                />
                {vertical && <button className={ghostBtnCls} onClick={() => setVertical("")}>Clear</button>}
            </div>
            <Panel title="Learned moves" subtitle="sorted by lift — which play moves the booking rate, with honest CIs">
                {loading ? (
                    <div className="py-8 text-center text-caption text-t-tertiary">Loading…</div>
                ) : sorted.length === 0 ? (
                    <EmptyChart msg="No moves learned yet" />
                ) : (
                    <div className="overflow-x-auto">
                        <table className="data-table">
                            <thead>
                                <tr>
                                    <th>Move</th><th>Objection</th><th>Regime</th><th>Temp</th>
                                    <th className="text-right">Lift</th>
                                    <th className="text-right">Book rate</th>
                                    <th className="text-right">Baseline</th>
                                    <th className="text-right">n</th>
                                    <th className="text-right">95% CI</th>
                                </tr>
                            </thead>
                            <tbody>
                                {sorted.map((m, i) => {
                                    const up = (m.lift || 0) >= 0;
                                    return (
                                        <tr key={`${m.move_type}-${m.objection_type}-${m.regime}-${i}`}>
                                            <td className="text-t-primary">{m.move_type || "—"}</td>
                                            <td className="text-t-secondary">{m.objection_type || "—"}</td>
                                            <td className="text-t-tertiary">{m.regime || "—"}</td>
                                            <td className="text-t-tertiary">{m.lead_temperature || "—"}</td>
                                            <td className="text-right tabular-nums font-medium"
                                                style={{ color: up ? "#00A656" : "#FF6A55" }}>
                                                {up ? "+" : ""}{asPct(m.lift, 1)}
                                            </td>
                                            <td className="text-right tabular-nums text-t-secondary">{asPct(m.book_rate, 1)}</td>
                                            <td className="text-right tabular-nums text-t-tertiary">{asPct(m.baseline_rate, 1)}</td>
                                            <td className="text-right tabular-nums text-t-secondary">{num(m.n_samples)}</td>
                                            <td className="text-right tabular-nums text-t-tertiary whitespace-nowrap">
                                                [{asPct(m.ci_low, 1)}, {asPct(m.ci_high, 1)}]
                                            </td>
                                        </tr>
                                    );
                                })}
                            </tbody>
                        </table>
                    </div>
                )}
            </Panel>
        </div>
    );
}

// ════════════════════════════════════════════════════════════════════════════
// CAUSAL — which move actually CAUSES bookings (CATE), not just correlates.
// raw_lift (the old Moves number) sits side-by-side with the causal CATE + its CI.
// Promote only when cate_lower > 0; overlap_min < 0.02 = an untrustworthy cell.
// ════════════════════════════════════════════════════════════════════════════
function CausalTab() {
    const [loading, setLoading] = useState(true);
    const [err, setErr] = useState("");
    const [moves, setMoves] = useState<FlywheelCATE[]>([]);
    const [vertical, setVertical] = useState("");

    const load = useCallback((v: string) => {
        setLoading(true);
        setErr("");
        getFlywheelCausal(v)
            .then((r) => { setMoves(r.moves || []); if (r.error) setErr(r.error); })
            .catch((e) => setErr(e?.message || "Failed to load causal effects"))
            .finally(() => setLoading(false));
    }, []);

    useEffect(() => { load(vertical); }, [load, vertical]);

    const sorted = useMemo(() => [...moves].sort((a, b) => (b.cate || 0) - (a.cate || 0)), [moves]);

    // the causal "promote-only-when-lower-bound>0" colour signal.
    const cateColor = (m: FlywheelCATE): string =>
        (m.cate_lower || 0) > 0 ? "#00A656" : (m.cate_upper || 0) < 0 ? "#FF6A55" : "#9A9FA5";

    return (
        <div className="space-y-3">
            <ErrorBanner msg={err} />
            <div className="flex items-center gap-2">
                <input
                    value={vertical}
                    onChange={(e) => setVertical(e.target.value)}
                    placeholder="Filter vertical…"
                    className="h-9 px-3 rounded-full bg-b-surface2 ring-1 ring-inset ring-s-subtle text-caption text-t-primary placeholder:text-t-tertiary focus:outline-none focus:ring-s-highlight w-48"
                />
                {vertical && <button className={ghostBtnCls} onClick={() => setVertical("")}>Clear</button>}
            </div>
            <Panel title="Causal effects (CATE)" subtitle="which move actually CAUSES bookings — the de-confounded CATE vs the correlational raw_lift from the Moves tab. Promote a cell only when the CI lower bound > 0 (green).">
                {loading ? (
                    <div className="py-8 text-center text-caption text-t-tertiary">Loading…</div>
                ) : sorted.length === 0 ? (
                    <EmptyChart msg="No causal estimates yet" />
                ) : (
                    <div className="overflow-x-auto">
                        <table className="data-table">
                            <thead>
                                <tr>
                                    <th>Move</th><th>Objection</th><th>Regime</th><th>Temp</th>
                                    <th className="text-right">raw lift</th>
                                    <th className="text-right">CATE</th>
                                    <th className="text-right">95% CI</th>
                                    <th className="text-right">n treated</th>
                                    <th className="text-right">overlap</th>
                                    <th className="text-center">sign</th>
                                </tr>
                            </thead>
                            <tbody>
                                {sorted.map((m, i) => {
                                    const c = cateColor(m);
                                    const lowOverlap = (m.overlap_min ?? 1) < 0.02;
                                    return (
                                        <tr key={`${m.move_type}-${m.objection_type}-${m.regime}-${m.lead_temperature}-${i}`}>
                                            <td className="text-t-primary">{m.move_type || "—"}</td>
                                            <td className="text-t-secondary">{m.objection_type || "—"}</td>
                                            <td className="text-t-tertiary">{m.regime || "—"}</td>
                                            <td className="text-t-tertiary">{m.lead_temperature || "—"}</td>
                                            {/* the OLD correlational number, kept dim for contrast */}
                                            <td className="text-right tabular-nums text-t-tertiary">{asPct(m.raw_lift, 1)}</td>
                                            {/* the CAUSAL number, coloured by the lower-bound>0 rule */}
                                            <td className="text-right tabular-nums font-medium" style={{ color: c }}>
                                                {(m.cate || 0) >= 0 ? "+" : ""}{asPct(m.cate, 1)}
                                            </td>
                                            <td className="text-right tabular-nums whitespace-nowrap" style={{ color: c }}>
                                                [{asPct(m.cate_lower, 1)}, {asPct(m.cate_upper, 1)}]
                                            </td>
                                            <td className="text-right tabular-nums text-t-secondary">{num(m.n_treated)}</td>
                                            <td className="text-right tabular-nums whitespace-nowrap"
                                                style={{ color: lowOverlap ? "#FF6A55" : undefined }}
                                                title={lowOverlap ? "untrustworthy cell — no positivity overlap" : undefined}>
                                                {dec(m.overlap_min, 3)}{lowOverlap ? " ⚠" : ""}
                                            </td>
                                            <td className="text-center">
                                                <span style={{ color: m.sign_agree ? "#00A656" : "#FF6A55" }}>
                                                    {m.sign_agree ? "✓" : "✗"}
                                                </span>
                                            </td>
                                        </tr>
                                    );
                                })}
                            </tbody>
                        </table>
                    </div>
                )}
            </Panel>
        </div>
    );
}

// ════════════════════════════════════════════════════════════════════════════
// CRITIC — the learned V(state)=P(book) value model (+ trained reward potential).
// ════════════════════════════════════════════════════════════════════════════
function CriticTab() {
    const [loading, setLoading] = useState(true);
    const [err, setErr] = useState("");
    const [critics, setCritics] = useState<FlywheelCritic[]>([]);

    const load = useCallback(() => {
        setLoading(true);
        setErr("");
        getFlywheelCritic()
            .then((r) => { setCritics(r.critics || []); if (r.error) setErr(r.error); })
            .catch((e) => setErr(e?.message || "Failed to load critic models"))
            .finally(() => setLoading(false));
    }, []);

    useEffect(() => { load(); }, [load]);

    return (
        <div className="space-y-3">
            <ErrorBanner msg={err} />
            <p className="text-caption text-t-tertiary px-1">
                The learned <span className="text-t-secondary">V(state)=P(book)</span> value model powering live momentum + the trained reward potential.
            </p>
            {loading ? (
                <Panel title="Critic models"><div className="py-8 text-center text-caption text-t-tertiary">Loading…</div></Panel>
            ) : critics.length === 0 ? (
                <Panel title="Critic models"><EmptyChart msg="No critic models trained yet" /></Panel>
            ) : (
                <div className="grid grid-cols-3 gap-3 max-2xl:grid-cols-2 max-md:grid-cols-1">
                    {critics.map((c, i) => {
                        const eceOk = (c.ece ?? 1) <= 0.1;
                        return (
                            <div key={`${c.vertical}-${c.model_type}-${c.ts}-${i}`}
                                className="rounded-3xl bg-b-surface2 ring-1 ring-s-subtle ring-inset p-4">
                                <div className="flex items-center justify-between gap-2 mb-3">
                                    <div>
                                        <div className="text-button text-t-primary">{c.vertical || "global"}</div>
                                        <div className="text-caption text-t-tertiary font-mono">{c.model_type || "—"}</div>
                                    </div>
                                    <StatusPill status={c.active ? "active" : "disabled"} />
                                </div>
                                <div className="grid grid-cols-2 gap-2">
                                    <div className="rounded-2xl bg-b-surface3 ring-1 ring-inset ring-s-subtle px-3 py-2">
                                        <div className="text-[11px] uppercase tracking-wide text-t-tertiary">AUC</div>
                                        <div className="text-h6 tabular-nums text-t-primary">{dec(c.auc, 3)}</div>
                                    </div>
                                    <div className="rounded-2xl bg-b-surface3 ring-1 ring-inset ring-s-subtle px-3 py-2">
                                        <div className="text-[11px] uppercase tracking-wide text-t-tertiary">ECE</div>
                                        <div className="text-h6 tabular-nums" style={{ color: eceOk ? "#00A656" : "#FF6A55" }}>{dec(c.ece, 3)}</div>
                                    </div>
                                </div>
                                <div className="mt-2.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-caption text-t-tertiary">
                                    <span>{num(c.n_rows)} rows</span>
                                    <span>· Platt a={dec(c.platt_a, 2)} b={dec(c.platt_b, 2)}</span>
                                    <span className="ml-auto">{ago(c.ts)}</span>
                                </div>
                            </div>
                        );
                    })}
                </div>
            )}
        </div>
    );
}

// ════════════════════════════════════════════════════════════════════════════
// POLICY — contextual-policy models with the 3-leg OPE + the rebuttal play library.
// ════════════════════════════════════════════════════════════════════════════
function PolicyTab() {
    const [loading, setLoading] = useState(true);
    const [err, setErr] = useState("");
    const [policies, setPolicies] = useState<FlywheelPolicy[]>([]);
    const [plays, setPlays] = useState<FlywheelPlay[]>([]);
    const [campaign, setCampaign] = useState("");

    const load = useCallback((c: string) => {
        setLoading(true);
        setErr("");
        Promise.all([getFlywheelPolicy(c), getFlywheelPlayLibrary("")])
            .then(([p, pl]) => {
                setPolicies(p.policies || []);
                setPlays(pl.templates || []);
                if (p.error || pl.error) setErr(p.error || pl.error || "");
            })
            .catch((e) => setErr(e?.message || "Failed to load policy models"))
            .finally(() => setLoading(false));
    }, []);

    useEffect(() => { load(campaign); }, [load, campaign]);

    return (
        <div className="space-y-3">
            <ErrorBanner msg={err} />
            <div className="flex items-center gap-2">
                <input
                    value={campaign}
                    onChange={(e) => setCampaign(e.target.value)}
                    placeholder="Filter campaign_id…"
                    className="h-9 px-3 rounded-full bg-b-surface2 ring-1 ring-inset ring-s-subtle text-caption text-t-primary placeholder:text-t-tertiary focus:outline-none focus:ring-s-highlight w-56"
                />
                {campaign && <button className={ghostBtnCls} onClick={() => setCampaign("")}>Clear</button>}
            </div>
            <Panel title="Contextual policy models" subtitle="off-policy-evaluated (SNIPS / FQE / MAGIC) — promote only when the pessimistic ope_lower > 0">
                {loading ? (
                    <div className="py-8 text-center text-caption text-t-tertiary">Loading…</div>
                ) : policies.length === 0 ? (
                    <EmptyChart msg="No policy models yet" />
                ) : (
                    <div className="overflow-x-auto">
                        <table className="data-table">
                            <thead>
                                <tr>
                                    <th>Campaign</th><th>Vertical</th><th>Knob</th>
                                    <th className="text-right">features</th>
                                    <th className="text-right">SNIPS</th>
                                    <th className="text-right">FQE</th>
                                    <th className="text-right">MAGIC</th>
                                    <th className="text-right">OPE lower</th>
                                    <th className="text-center">Active</th>
                                    <th className="text-right">When</th>
                                </tr>
                            </thead>
                            <tbody>
                                {policies.map((p, i) => {
                                    const safe = (p.ope_lower || 0) > 0;
                                    return (
                                        <tr key={`${p.campaign_id}-${p.knob}-${p.ts}-${i}`}>
                                            <td className="font-mono text-caption text-t-primary">{p.campaign_id || "—"}</td>
                                            <td className="text-t-tertiary">{p.vertical || "—"}</td>
                                            <td className="text-t-secondary">{p.knob || "—"}</td>
                                            <td className="text-right tabular-nums text-t-tertiary">{num(p.n_features)}</td>
                                            <td className="text-right tabular-nums text-t-secondary">{dec(p.ope_snips, 3)}</td>
                                            <td className="text-right tabular-nums text-t-secondary">{dec(p.ope_fqe, 3)}</td>
                                            <td className="text-right tabular-nums text-t-secondary">{dec(p.ope_magic, 3)}</td>
                                            <td className="text-right tabular-nums font-medium" style={{ color: safe ? "#00A656" : "#FF6A55" }}>{dec(p.ope_lower, 3)}</td>
                                            <td className="text-center">{p.active
                                                ? <Badge variant="success" dot>active</Badge>
                                                : <Badge variant="neutral">—</Badge>}</td>
                                            <td className="text-right text-t-tertiary whitespace-nowrap">{ago(p.ts)}</td>
                                        </tr>
                                    );
                                })}
                            </tbody>
                        </table>
                    </div>
                )}
            </Panel>
            <Panel title="Play library" subtitle="learned rebuttal templates keyed by objection">
                {loading ? (
                    <div className="py-8 text-center text-caption text-t-tertiary">Loading…</div>
                ) : plays.length === 0 ? (
                    <EmptyChart msg="No rebuttal templates yet" />
                ) : (
                    <div className="overflow-x-auto">
                        <table className="data-table">
                            <thead>
                                <tr>
                                    <th>Objection</th><th>Template</th><th>Label</th>
                                </tr>
                            </thead>
                            <tbody>
                                {plays.map((t, i) => (
                                    <tr key={`${t.template_id}-${i}`}>
                                        <td className="text-t-secondary whitespace-nowrap">{t.objection_type || "—"}</td>
                                        <td className="text-t-primary">{t.text || "—"}</td>
                                        <td className="text-t-tertiary whitespace-nowrap">{t.label || "—"}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}
            </Panel>
        </div>
    );
}

// ════════════════════════════════════════════════════════════════════════════
// WORLD MODEL — caller archetypes + FILTER-ONLY sim rollouts (proposes/removes
// challengers, never promotes).
// ════════════════════════════════════════════════════════════════════════════
function WorldModelTab() {
    const [loading, setLoading] = useState(true);
    const [err, setErr] = useState("");
    const [archetypes, setArchetypes] = useState<FlywheelArchetype[]>([]);
    const [rollouts, setRollouts] = useState<FlywheelSimRollout[]>([]);

    const load = useCallback(() => {
        setLoading(true);
        setErr("");
        Promise.all([getFlywheelArchetypes(), getFlywheelSimRollouts(43200)])
            .then(([a, r]) => {
                setArchetypes(a.archetypes || []);
                setRollouts(r.rollouts || []);
                if (a.error || r.error) setErr(a.error || r.error || "");
            })
            .catch((e) => setErr(e?.message || "Failed to load world model"))
            .finally(() => setLoading(false));
    }, []);

    useEffect(() => { load(); }, [load]);

    return (
        <div className="space-y-3">
            <ErrorBanner msg={err} />
            <p className="text-caption text-t-tertiary px-1">
                The caller simulator is <span className="text-t-secondary">FILTER-ONLY</span> — it proposes/removes challengers, never promotes.
            </p>
            <Panel title="Caller archetypes" subtitle="the synthetic personas the world-model simulates against">
                {loading ? (
                    <div className="py-8 text-center text-caption text-t-tertiary">Loading…</div>
                ) : archetypes.length === 0 ? (
                    <EmptyChart msg="No archetypes learned yet" />
                ) : (
                    <div className="grid grid-cols-3 gap-3 max-2xl:grid-cols-2 max-md:grid-cols-1 p-1">
                        {archetypes.map((a, i) => (
                            <div key={`${a.archetype_id}-${i}`}
                                className="rounded-3xl bg-b-surface2 ring-1 ring-s-subtle ring-inset p-4">
                                <div className="flex items-center justify-between gap-2 mb-2">
                                    <div className="text-button text-t-primary">{a.label || a.archetype_id || "—"}</div>
                                    <Badge variant="neutral">{a.temperament || "—"}</Badge>
                                </div>
                                <div className="grid grid-cols-3 gap-2">
                                    <div className="rounded-2xl bg-b-surface3 ring-1 ring-inset ring-s-subtle px-3 py-2">
                                        <div className="text-[11px] uppercase tracking-wide text-t-tertiary">Coverage</div>
                                        <div className="text-body-1 tabular-nums text-t-primary">{asPct(a.weight, 0)}</div>
                                    </div>
                                    <div className="rounded-2xl bg-b-surface3 ring-1 ring-inset ring-s-subtle px-3 py-2">
                                        <div className="text-[11px] uppercase tracking-wide text-t-tertiary">Book rate</div>
                                        <div className="text-body-1 tabular-nums text-t-primary">{asPct(a.base_book_rate, 1)}</div>
                                    </div>
                                    <div className="rounded-2xl bg-b-surface3 ring-1 ring-inset ring-s-subtle px-3 py-2">
                                        <div className="text-[11px] uppercase tracking-wide text-t-tertiary">Calls</div>
                                        <div className="text-body-1 tabular-nums text-t-primary">{num(a.n_calls)}</div>
                                    </div>
                                </div>
                            </div>
                        ))}
                    </div>
                )}
            </Panel>
            <Panel title="Recent sim rollouts" subtitle="filter-only pre-evals — ece > 0.15 means the sim self-disabled (low fidelity)">
                {loading ? (
                    <div className="py-8 text-center text-caption text-t-tertiary">Loading…</div>
                ) : rollouts.length === 0 ? (
                    <EmptyChart msg="No sim rollouts in window" />
                ) : (
                    <div className="overflow-x-auto">
                        <table className="data-table">
                            <thead>
                                <tr>
                                    <th>Archetype</th><th>Policy</th><th>Outcome</th>
                                    <th className="text-right">Reward</th>
                                    <th className="text-right">Turns</th>
                                    <th className="text-right">USI</th>
                                    <th className="text-right">ECE</th>
                                    <th className="text-right">When</th>
                                </tr>
                            </thead>
                            <tbody>
                                {rollouts.map((r, i) => {
                                    const lowFid = (r.ece || 0) > 0.15;
                                    return (
                                        <tr key={`${r.archetype_id}-${r.challenger_id}-${r.ts}-${i}`}>
                                            <td className="text-t-secondary">{r.archetype_id || "—"}</td>
                                            <td className="text-t-tertiary">{r.policy_label || "—"}</td>
                                            <td className="text-t-primary">{r.sim_outcome || "—"}</td>
                                            <td className="text-right tabular-nums text-t-secondary">{dec(r.sim_reward, 3)}</td>
                                            <td className="text-right tabular-nums text-t-tertiary">{num(r.turns)}</td>
                                            <td className="text-right tabular-nums text-t-tertiary">{dec(r.usi, 2)}</td>
                                            <td className="text-right tabular-nums"
                                                style={{ color: lowFid ? "#FF6A55" : undefined }}
                                                title={lowFid ? "sim self-disabled / low fidelity" : undefined}>
                                                {dec(r.ece, 3)}{lowFid ? " ⚠" : ""}
                                            </td>
                                            <td className="text-right text-t-tertiary whitespace-nowrap">{ago(r.ts)}</td>
                                        </tr>
                                    );
                                })}
                            </tbody>
                        </table>
                    </div>
                )}
            </Panel>
        </div>
    );
}

// ════════════════════════════════════════════════════════════════════════════
// BANDIT — arm leaderboard, grouped by knob.
// ════════════════════════════════════════════════════════════════════════════
function BanditTab() {
    const [loading, setLoading] = useState(true);
    const [err, setErr] = useState("");
    const [arms, setArms] = useState<FlywheelArm[]>([]);
    const [campaign, setCampaign] = useState("");

    const load = useCallback((c: string) => {
        setLoading(true);
        setErr("");
        getFlywheelBandit(c)
            .then((r) => { setArms(r.arms || []); if (r.error) setErr(r.error); })
            .catch((e) => setErr(e?.message || "Failed to load bandit arms"))
            .finally(() => setLoading(false));
    }, []);

    useEffect(() => { load(campaign); }, [load, campaign]);

    const byKnob = useMemo(() => {
        const m = new Map<string, FlywheelArm[]>();
        for (const a of arms) {
            const k = a.knob || "(unknobbed)";
            const arr = m.get(k) || [];
            arr.push(a);
            m.set(k, arr);
        }
        for (const arr of m.values()) arr.sort((a, b) => (b.mean || 0) - (a.mean || 0));
        return Array.from(m.entries());
    }, [arms]);

    return (
        <div className="space-y-3">
            <ErrorBanner msg={err} />
            <div className="flex items-center gap-2">
                <input
                    value={campaign}
                    onChange={(e) => setCampaign(e.target.value)}
                    placeholder="Filter campaign_id…"
                    className="h-9 px-3 rounded-full bg-b-surface2 ring-1 ring-inset ring-s-subtle text-caption text-t-primary placeholder:text-t-tertiary focus:outline-none focus:ring-s-highlight w-56"
                />
                {campaign && <button className={ghostBtnCls} onClick={() => setCampaign("")}>Clear</button>}
            </div>
            {loading ? (
                <div className="py-8 text-center text-caption text-t-tertiary">Loading…</div>
            ) : byKnob.length === 0 ? (
                <Panel title="Bandit arms"><EmptyChart msg="No arms yet" /></Panel>
            ) : (
                byKnob.map(([knob, list]) => (
                    <Panel key={knob} title={knob} subtitle={`${list.length} arms · Thompson sampling (Beta posterior)`}>
                        <div className="overflow-x-auto">
                            <table className="data-table">
                                <thead>
                                    <tr>
                                        <th>#</th><th>Arm</th><th>Context</th>
                                        <th className="text-right">Mean</th>
                                        <th className="text-right">Plays</th>
                                        <th className="text-right">α / β</th>
                                        <th className="text-right">Opt-out</th>
                                        <th className="text-right">Cost / booking</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {list.map((a, i) => {
                                        const hot = (a.guardrail_optout_rate || 0) > 0.15;
                                        return (
                                            <tr key={`${a.arm_id}-${a.context_bucket}-${i}`}>
                                                <td className="tabular-nums text-t-tertiary">{i + 1}</td>
                                                <td className="text-t-primary font-mono text-caption">{a.arm_id || "—"}</td>
                                                <td className="text-t-tertiary">{a.context_bucket || "—"}</td>
                                                <td className="text-right tabular-nums text-t-primary font-medium">{asPct(a.mean, 1)}</td>
                                                <td className="text-right tabular-nums text-t-secondary">{num(a.plays)}</td>
                                                <td className="text-right tabular-nums text-t-tertiary whitespace-nowrap">{dec(a.alpha, 1)} / {dec(a.beta, 1)}</td>
                                                <td className="text-right tabular-nums"
                                                    style={{ color: hot ? "#FF6A55" : undefined }}>
                                                    {asPct(a.guardrail_optout_rate, 1)}
                                                </td>
                                                <td className="text-right tabular-nums text-t-tertiary">{dec(a.guardrail_cost_per_booking, 2)}</td>
                                            </tr>
                                        );
                                    })}
                                </tbody>
                            </table>
                        </div>
                    </Panel>
                ))
            )}
        </div>
    );
}

// ════════════════════════════════════════════════════════════════════════════
// MOAT — chosen vs rejected preference-pair browser.
// ════════════════════════════════════════════════════════════════════════════
function MoatTab() {
    const [loading, setLoading] = useState(true);
    const [err, setErr] = useState("");
    const [pairs, setPairs] = useState<FlywheelPair[]>([]);
    const [objection, setObjection] = useState("");
    const [temp, setTemp] = useState("");

    const load = useCallback((o: string, t: string) => {
        setLoading(true);
        setErr("");
        getFlywheelPreferences(o, t, 100)
            .then((r) => { setPairs(r.pairs || []); if (r.error) setErr(r.error); })
            .catch((e) => setErr(e?.message || "Failed to load preference pairs"))
            .finally(() => setLoading(false));
    }, []);

    useEffect(() => { load(objection, temp); }, [load, objection, temp]);

    return (
        <div className="space-y-3">
            <ErrorBanner msg={err} />
            <div className="flex flex-wrap items-center gap-2">
                <input
                    value={objection}
                    onChange={(e) => setObjection(e.target.value)}
                    placeholder="Objection…"
                    className="h-9 px-3 rounded-full bg-b-surface2 ring-1 ring-inset ring-s-subtle text-caption text-t-primary placeholder:text-t-tertiary focus:outline-none focus:ring-s-highlight w-44"
                />
                <input
                    value={temp}
                    onChange={(e) => setTemp(e.target.value)}
                    placeholder="Temperature…"
                    className="h-9 px-3 rounded-full bg-b-surface2 ring-1 ring-inset ring-s-subtle text-caption text-t-primary placeholder:text-t-tertiary focus:outline-none focus:ring-s-highlight w-44"
                />
                {(objection || temp) && <button className={ghostBtnCls} onClick={() => { setObjection(""); setTemp(""); }}>Clear</button>}
            </div>
            {loading ? (
                <Panel title="Preference pairs"><div className="py-8 text-center text-caption text-t-tertiary">Loading…</div></Panel>
            ) : pairs.length === 0 ? (
                <Panel title="Preference pairs"><EmptyChart msg="No pairs match" /></Panel>
            ) : (
                <div className="space-y-3">
                    {pairs.map((p) => <PairCard key={p.pair_id} p={p} />)}
                </div>
            )}
        </div>
    );
}

function PairCard({ p }: { p: FlywheelPair }) {
    return (
        <div className="rounded-3xl bg-b-surface2 ring-1 ring-s-subtle ring-inset p-4">
            <div className="flex flex-wrap items-center gap-2 mb-3 text-caption text-t-tertiary">
                <span className="text-t-secondary">{p.objection_type || "—"}</span>
                <span>·</span><span>{p.lead_temperature || "—"}</span>
                {p.regime && <><span>·</span><span>{p.regime}</span></>}
                {p.vertical && <><span>·</span><span>{p.vertical}</span></>}
                <span className="ml-auto flex flex-wrap items-center gap-1.5">
                    <Badge variant="info">margin {dec(p.margin, 2)}</Badge>
                    {p.source && <Badge variant="neutral">{p.source}</Badge>}
                    {p.survived_swap && <Badge variant="success" dot>survived swap</Badge>}
                    {p.compliant && <Badge variant="success">compliant</Badge>}
                    {p.outcome_anchored
                        ? <Badge variant="success">outcome-anchored</Badge>
                        : <Badge variant="warning">judge-only</Badge>}
                    <span className="text-[11px] text-t-tertiary">{ago(p.ts)}</span>
                </span>
            </div>
            <div className="grid grid-cols-2 gap-3 max-md:grid-cols-1">
                <div className="rounded-2xl bg-primary-02/8 ring-1 ring-inset ring-primary-02/20 p-3">
                    <div className="text-[11px] uppercase tracking-wide text-t-tertiary mb-1">Chosen</div>
                    <div className="text-body-2 text-t-primary whitespace-pre-wrap">{p.chosen_text || "—"}</div>
                </div>
                <div className="rounded-2xl bg-primary-03/8 ring-1 ring-inset ring-primary-03/20 p-3">
                    <div className="text-[11px] uppercase tracking-wide text-t-tertiary mb-1">Rejected</div>
                    <div className="text-body-2 text-t-secondary whitespace-pre-wrap">{p.rejected_text || "—"}</div>
                </div>
            </div>
        </div>
    );
}

// ════════════════════════════════════════════════════════════════════════════
// CHALLENGERS — proposed config changes; promotion is HUMAN-gated.
// ════════════════════════════════════════════════════════════════════════════
function ChallengersTab({ admin, autoPromote }: { admin: boolean; autoPromote: boolean }) {
    const [loading, setLoading] = useState(true);
    const [err, setErr] = useState("");
    const [rows, setRows] = useState<FlywheelChallenger[]>([]);
    const [statusFilter, setStatusFilter] = useState("");
    const [busyId, setBusyId] = useState("");

    // POWER-UP: self-hosted shadow distillation runs (shadow-only, never live Riya).
    const [distillLoading, setDistillLoading] = useState(true);
    const [distillErr, setDistillErr] = useState("");
    const [distillRuns, setDistillRuns] = useState<FlywheelDistillRun[]>([]);

    const load = useCallback((s: string) => {
        setLoading(true);
        setErr("");
        getFlywheelChallengers(s)
            .then((r) => { setRows(r.challengers || []); if (r.error) setErr(r.error); })
            .catch((e) => setErr(e?.message || "Failed to load challengers"))
            .finally(() => setLoading(false));
    }, []);

    const loadDistill = useCallback(() => {
        setDistillLoading(true);
        setDistillErr("");
        getFlywheelDistill()
            .then((r) => { setDistillRuns(r.runs || []); if (r.error) setDistillErr(r.error); })
            .catch((e) => setDistillErr(e?.message || "Failed to load distill runs"))
            .finally(() => setDistillLoading(false));
    }, []);

    useEffect(() => { load(statusFilter); }, [load, statusFilter]);
    useEffect(() => { loadDistill(); }, [loadDistill]);

    const onApprove = useCallback(async (id: string) => {
        if (!confirm("Approve & promote this challenger? This applies the proposed config.")) return;
        setBusyId(id);
        try {
            await approveFlywheelChallenger(id);
            load(statusFilter);
        } catch (e) {
            setErr(e instanceof Error ? e.message : "Approve failed");
        } finally {
            setBusyId("");
        }
    }, [load, statusFilter]);

    const onReject = useCallback(async (id: string) => {
        const reason = prompt("Reject reason?") || "";
        if (reason === null) return;
        setBusyId(id);
        try {
            await rejectFlywheelChallenger(id, reason);
            load(statusFilter);
        } catch (e) {
            setErr(e instanceof Error ? e.message : "Reject failed");
        } finally {
            setBusyId("");
        }
    }, [load, statusFilter]);

    return (
        <div className="space-y-3">
            <ErrorBanner msg={err} />
            <div className="flex flex-wrap items-center gap-2">
                {["", "proposed", "shadow", "approved", "rejected"].map((s) => (
                    <button key={s || "all"} onClick={() => setStatusFilter(s)}
                        className={tabCls(statusFilter === s)}>
                        {s || "All"}
                    </button>
                ))}
                <span className="ml-auto text-caption text-t-tertiary">
                    {autoPromote
                        ? "Auto-promote is ON — but you can still review here."
                        : "Promotion is human-gated. Nothing applies without your approval."}
                </span>
            </div>
            <Panel title="Challengers" subtitle="proposed config changes — gates_passed + shadow_ok + OPE are decision aids, not auto-apply">
                {loading ? (
                    <div className="py-8 text-center text-caption text-t-tertiary">Loading…</div>
                ) : rows.length === 0 ? (
                    <EmptyChart msg="No challengers" />
                ) : (
                    <div className="overflow-x-auto">
                        <table className="data-table">
                            <thead>
                                <tr>
                                    <th>Challenger</th><th>Kind</th><th>Status</th>
                                    <th className="text-center">Gates</th>
                                    <th className="text-center">Shadow</th>
                                    <th className="text-right">TTFT</th>
                                    <th className="text-right">Cost / appt</th>
                                    <th className="text-right">Reward lift</th>
                                    <th className="text-right">OPE (SNIPS)</th>
                                    <th className="text-center">Seq sig</th>
                                    <th className="text-right">Reward CS≥</th>
                                    <th className="text-right">Sim lift</th>
                                    <th className="text-right">When</th>
                                    {admin && <th className="text-right">Action</th>}
                                </tr>
                            </thead>
                            <tbody>
                                {rows.map((c) => {
                                    const pending = c.status === "proposed" || c.status === "shadow";
                                    const up = (c.reward_lift || 0) >= 0;
                                    return (
                                        <tr key={c.challenger_id}>
                                            <td className="font-mono text-caption text-t-primary" title={c.rationale}>{c.challenger_id}</td>
                                            <td className="text-t-secondary">{c.kind || "—"}</td>
                                            <td><ChallengerStatus status={c.status} /></td>
                                            <td className="text-center">{c.gates_passed
                                                ? <Badge variant="success" dot>pass</Badge>
                                                : <Badge variant="danger">fail</Badge>}</td>
                                            <td className="text-center">{c.shadow_ok
                                                ? <Badge variant="success">ok</Badge>
                                                : <Badge variant="neutral">—</Badge>}</td>
                                            <td className="text-right tabular-nums text-t-secondary">{c.ttft_ms ? `${num(c.ttft_ms)}ms` : "—"}</td>
                                            <td className="text-right tabular-nums text-t-tertiary">{dec(c.cost_per_appointment, 2)}</td>
                                            <td className="text-right tabular-nums" style={{ color: up ? "#00A656" : "#FF6A55" }}>
                                                {up ? "+" : ""}{asPct(c.reward_lift, 1)}
                                            </td>
                                            <td className="text-right tabular-nums text-t-tertiary">{dec(c.ope_snips_value, 3)}</td>
                                            {/* POWER-UP: sequential confidence-sequence verdict + sim pre-eval lift */}
                                            <td className="text-center">{c.seq_significant == null
                                                ? <span className="text-t-tertiary text-caption">—</span>
                                                : c.seq_significant
                                                    ? <Badge variant="success" dot>sig</Badge>
                                                    : <Badge variant="neutral">—</Badge>}</td>
                                            <td className="text-right tabular-nums" style={{ color: c.reward_cs_lower == null ? undefined : (c.reward_cs_lower > 0 ? "#00A656" : "#FF6A55") }}>
                                                {c.reward_cs_lower == null ? "—" : dec(c.reward_cs_lower, 3)}
                                            </td>
                                            <td className="text-right tabular-nums" style={{ color: c.sim_reward_lift == null ? undefined : (c.sim_reward_lift >= 0 ? "#00A656" : "#FF6A55") }}>
                                                {c.sim_reward_lift == null ? "—" : `${c.sim_reward_lift >= 0 ? "+" : ""}${asPct(c.sim_reward_lift, 1)}`}
                                            </td>
                                            <td className="text-right text-t-tertiary whitespace-nowrap">{ago(c.ts)}</td>
                                            {admin && (
                                                <td className="text-right whitespace-nowrap">
                                                    {pending ? (
                                                        <span className="inline-flex gap-1.5">
                                                            <button
                                                                disabled={busyId === c.challenger_id}
                                                                onClick={() => onApprove(c.challenger_id)}
                                                                className="h-8 px-3 rounded-full text-caption bg-primary-02/15 text-primary-02 ring-1 ring-inset ring-primary-02/30 hover:bg-primary-02/25 transition-colors disabled:opacity-50">
                                                                Approve
                                                            </button>
                                                            <button
                                                                disabled={busyId === c.challenger_id}
                                                                onClick={() => onReject(c.challenger_id)}
                                                                className="h-8 px-3 rounded-full text-caption bg-primary-03/15 text-primary-03 ring-1 ring-inset ring-primary-03/30 hover:bg-primary-03/25 transition-colors disabled:opacity-50">
                                                                Reject
                                                            </button>
                                                        </span>
                                                    ) : (
                                                        <span className="text-t-tertiary text-caption">{c.approved_by ? `by ${c.approved_by}` : "—"}</span>
                                                    )}
                                                </td>
                                            )}
                                        </tr>
                                    );
                                })}
                            </tbody>
                        </table>
                    </div>
                )}
            </Panel>

            {/* DISTILL — self-hosted shadow training runs (shadow-only, never live Riya). */}
            <ErrorBanner msg={distillErr} />
            <Panel title="Shadow distillation" subtitle="self-hosted shadow training runs — these train a shadow adapter only, NEVER the live Riya">
                {distillLoading ? (
                    <div className="py-8 text-center text-caption text-t-tertiary">Loading…</div>
                ) : distillRuns.length === 0 ? (
                    <EmptyChart msg="No distillation runs yet" />
                ) : (
                    <div className="overflow-x-auto">
                        <table className="data-table">
                            <thead>
                                <tr>
                                    <th>Run</th><th>Method</th><th>Base model</th>
                                    <th className="text-right">+desirable</th>
                                    <th className="text-right">−undesirable</th>
                                    <th>Status</th>
                                    <th className="text-right">When</th>
                                </tr>
                            </thead>
                            <tbody>
                                {distillRuns.map((r, i) => (
                                    <tr key={`${r.run_id}-${i}`}>
                                        <td className="font-mono text-caption text-t-primary truncate max-w-[180px]" title={r.adapter_uri}>{r.run_id || "—"}</td>
                                        <td className="text-t-secondary">{r.method || "—"}</td>
                                        <td className="text-t-tertiary font-mono text-caption">{r.base_model || "—"}</td>
                                        <td className="text-right tabular-nums text-t-secondary">{num(r.n_desirable)}</td>
                                        <td className="text-right tabular-nums text-t-secondary">{num(r.n_undesirable)}</td>
                                        <td>{r.status
                                            ? <Badge variant={/done|complete|success/i.test(r.status) ? "success" : /fail|error/i.test(r.status) ? "danger" : "info"}>{r.status}</Badge>
                                            : <Badge variant="neutral">—</Badge>}</td>
                                        <td className="text-right text-t-tertiary whitespace-nowrap">{ago(r.ts)}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}
            </Panel>
        </div>
    );
}

// ════════════════════════════════════════════════════════════════════════════
// LABELS — human calibration queue (good/bad).
// ════════════════════════════════════════════════════════════════════════════
function LabelsTab({ admin }: { admin: boolean }) {
    const [loading, setLoading] = useState(true);
    const [err, setErr] = useState("");
    const [labels, setLabels] = useState<FlywheelLabel[]>([]);
    const [busy, setBusy] = useState("");

    const load = useCallback(() => {
        setLoading(true);
        setErr("");
        getFlywheelLabels()
            .then((r) => { setLabels(r.labels || []); if (r.error) setErr(r.error); })
            .catch((e) => setErr(e?.message || "Failed to load labels"))
            .finally(() => setLoading(false));
    }, []);

    useEffect(() => { load(); }, [load]);

    const submit = useCallback(async (l: FlywheelLabel, label: string) => {
        const key = `${l.call_id}-${l.turn_num}`;
        const rationale = prompt(`Rationale for "${label}"? (optional)`) ?? "";
        setBusy(key);
        try {
            await submitFlywheelLabel(l.call_id, l.turn_num, label, rationale);
            load();
        } catch (e) {
            setErr(e instanceof Error ? e.message : "Label failed");
        } finally {
            setBusy("");
        }
    }, [load]);

    return (
        <div className="space-y-3">
            <ErrorBanner msg={err} />
            <Panel title="Calibration queue" subtitle="human good/bad labels that calibrate the judge against real outcomes">
                {loading ? (
                    <div className="py-8 text-center text-caption text-t-tertiary">Loading…</div>
                ) : labels.length === 0 ? (
                    <EmptyChart msg="Queue is empty" />
                ) : (
                    <div className="overflow-x-auto">
                        <table className="data-table">
                            <thead>
                                <tr>
                                    <th>Call</th><th className="text-right">Turn</th>
                                    <th>Trigger</th><th>Label</th><th>Labeler</th>
                                    <th className="text-center">Calibration</th>
                                    <th className="text-right">When</th>
                                    {admin && <th className="text-right">Label it</th>}
                                </tr>
                            </thead>
                            <tbody>
                                {labels.map((l) => {
                                    const key = `${l.call_id}-${l.turn_num}`;
                                    return (
                                        <tr key={key}>
                                            <td className="font-mono text-caption text-t-primary truncate max-w-[180px]" title={l.rationale}>{l.call_id}</td>
                                            <td className="text-right tabular-nums text-t-secondary">#{l.turn_num}</td>
                                            <td className="text-t-tertiary">{l.trigger || "—"}</td>
                                            <td>{l.label
                                                ? <Badge variant={/good|pos/i.test(l.label) ? "success" : /bad|neg/i.test(l.label) ? "danger" : "neutral"}>{l.label}</Badge>
                                                : <span className="text-t-tertiary text-caption">unlabeled</span>}</td>
                                            <td className="text-t-tertiary">{l.labeler || "—"}</td>
                                            <td className="text-center">{l.used_for_calibration
                                                ? <Badge variant="info">used</Badge>
                                                : <Badge variant="neutral">—</Badge>}</td>
                                            <td className="text-right text-t-tertiary whitespace-nowrap">{ago(l.ts)}</td>
                                            {admin && (
                                                <td className="text-right whitespace-nowrap">
                                                    <span className="inline-flex gap-1.5">
                                                        <button disabled={busy === key} onClick={() => submit(l, "good")}
                                                            className="h-8 px-3 rounded-full text-caption bg-primary-02/15 text-primary-02 ring-1 ring-inset ring-primary-02/30 hover:bg-primary-02/25 transition-colors disabled:opacity-50">
                                                            Good
                                                        </button>
                                                        <button disabled={busy === key} onClick={() => submit(l, "bad")}
                                                            className="h-8 px-3 rounded-full text-caption bg-primary-03/15 text-primary-03 ring-1 ring-inset ring-primary-03/30 hover:bg-primary-03/25 transition-colors disabled:opacity-50">
                                                            Bad
                                                        </button>
                                                    </span>
                                                </td>
                                            )}
                                        </tr>
                                    );
                                })}
                            </tbody>
                        </table>
                    </div>
                )}
            </Panel>
        </div>
    );
}

export default function FlywheelPage() {
    return <SuperAdminGuard><Inner /></SuperAdminGuard>;
}
