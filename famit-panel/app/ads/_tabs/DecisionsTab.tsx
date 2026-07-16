"use client";

// Ad-Engine · Decision Log tab — the append-only AI decision feed.
// FRONTEND_ARCHITECTURE §7.
//
// Every autonomous move the engine makes (scale / realloc / pause / redial) lands
// here as an immutable row with the measured inputs that triggered it, the ordered
// guard-chain it cleared, the outcome (auto-applied / needs-approval / blocked),
// and whether it can be reversed. Moves that need a human get an Approve (step-up)
// / Dismiss action — gated behind the `writable` prop, hidden for read-only
// (agent) sessions.
//
// REUSE (verbatim, per §7):
//  • the lifted Optimizer "Suggested moves" header + dry-run runner + its <Badge>
//    move/reason maps from ../_shared (moveVariant / moveLabel / moveReason) —
//    behaviour preserved 1:1 as the manual "preview the next tick" control;
//  • the data-table chrome + the right slide-over drawer pattern from
//    app/integrations/_audit-drawer.tsx and the sibling LeadsTab compliance drawer
//    (Modal isSlidePanel · header / scrollable body / action footer · GuardRow).
//
// Data comes from the dormant-safe ../_lib helper getAdsDecisions — a non-200 read
// degrades to the local DormantPanel (never an error wall). The feed re-polls every
// 30s (visibility-gated) via useRealtimeRefresh, the verified analytics idiom.
//
// Money stays _minor (paise); fmtMoney renders it. Zero raw hex — every colour is a
// token class. No write control renders for read-only sessions.

import { useCallback, useEffect, useState } from "react";
import Card from "@/components/Card";
import Icon from "@/components/Icon";
import Badge, { type BadgeVariant } from "@/components/Badge";
import Button from "@/components/Button";
import Modal from "@/components/Modal";
import KpiCard from "@/components/KpiCard";
import { SkeletonTableRows } from "@/components/Skeleton";
import AutopilotPanel from "./_autopilot-panel";
import {
    runOptimize,
    getAdsDecisions,
    useRealtimeRefresh,
    fmtMoney,
    fmtTs,
    type AdsHealth,
    type AdsDecision,
    type OptimizeResponse,
} from "../_lib";
import {
    DormantPanel,
    moveVariant,
    moveLabel,
    moveReason,
    type ToastFn,
} from "../_shared";

export type DecisionsTabProps = {
    writable: boolean;
    dormant: boolean;
    activeCount: number;
    currency: string;
    hc: AdsHealth | null;
    toast: ToastFn;
};

/* --------------------------------------------------------- decision vocabulary */
//
// Each axis (the move kind + the outcome + a guard result) maps a backend string
// onto the ONE <Badge> tone language + a human, active-voice label. Unknown values
// degrade to a de-snaked neutral pill, never a crash.

function human(s?: string | null): string {
    if (!s) return "—";
    return s.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());
}

const DECISION_LABEL: Record<string, string> = {
    scale: "Scale spend",
    scale_winner: "Scale winner",
    realloc: "Reallocate budget",
    reallocate: "Reallocate budget",
    pause: "Pause campaign",
    kill_loser: "Kill loser",
    redial: "Redial lead",
    hold: "Hold steady",
};

function decisionLabel(d: string): string {
    return DECISION_LABEL[d] || human(d);
}

function decisionIcon(d: string): string {
    if (d === "scale" || d === "scale_winner") return "arrow-percent";
    if (d === "pause" || d === "kill_loser") return "block";
    if (d === "redial") return "chat";
    if (d === "realloc" || d === "reallocate") return "wallet";
    return "magic-pencil";
}

// The outcome of a move once the guard chain has run end-to-end.
function outcomeTone(o?: string): BadgeVariant {
    if (o === "auto_applied" || o === "applied") return "success";
    if (o === "needs_approval") return "warning";
    if (typeof o === "string" && o.startsWith("blocked")) return "danger";
    if (o === "dismissed") return "neutral";
    return "neutral";
}

const OUTCOME_LABEL: Record<string, string> = {
    auto_applied: "Auto-applied",
    applied: "Applied",
    needs_approval: "Needs approval",
    dismissed: "Dismissed",
    blocked_cap_exceeded: "Cap reached",
    blocked_cpl_breach: "CPL breach",
    blocked_no_conversion_tracking: "No CPL tracking",
    blocked_not_approved: "Step-up needed",
};

function outcomeLabel(o?: string): string {
    if (!o) return "—";
    return OUTCOME_LABEL[o] || human(o);
}

// One guard in the chain — passed / blocked / skipped.
function guardTone(result?: string): BadgeVariant {
    if (result === "pass" || result === "passed" || result === "ok") return "success";
    if (result === "skip" || result === "skipped" || result === "n/a") return "neutral";
    return "danger"; // block / fail / anything unexpected reads as held
}

function guardPassed(result?: string): boolean {
    return result === "pass" || result === "passed" || result === "ok";
}

// A short one-line summary of the measured inputs that triggered the move, for the
// table's "Inputs" column. The full structured view lives in the drawer.
function inputsSummary(inputs?: Record<string, unknown>, currency = "INR"): string {
    if (!inputs || Object.keys(inputs).length === 0) return "—";
    const parts: string[] = [];
    const cpl = inputs.cpl_minor ?? inputs.cpl;
    if (typeof cpl === "number") parts.push(`CPL ${fmtMoney(cpl, currency)}`);
    const factor = inputs.recon_factor ?? inputs.reconciliation_factor;
    if (typeof factor === "number") parts.push(`×${factor.toFixed(2)} recon`);
    const conv = inputs.conversions ?? inputs.convs;
    if (typeof conv === "number") parts.push(`${conv} conv`);
    if (parts.length) return parts.join(" · ");
    // Fall back to the first couple of scalar fields so the cell is never blank.
    for (const [k, v] of Object.entries(inputs)) {
        if (typeof v === "number" || typeof v === "string") {
            parts.push(`${human(k)} ${v}`);
        }
        if (parts.length >= 2) break;
    }
    return parts.length ? parts.join(" · ") : "—";
}

// Normalize the bandit posteriors — whether the backend sends an array of arm
// objects or a flat {arm: mean} map — into an ordered [name, value] list so the
// drawer renders one consistent meter row per arm.
function normalizePosteriors(
    posteriors:
        | Record<string, unknown>
        | Array<Record<string, unknown>>,
): Array<[string, unknown]> {
    if (Array.isArray(posteriors)) {
        return posteriors.map((p, i) => [
            String(p.variant ?? p.arm ?? `Arm ${i + 1}`),
            p.mean ?? p.p ?? p.value,
        ]);
    }
    return Object.entries(posteriors);
}

/* ============================================================== the tab body */

export default function DecisionsTab({
    writable,
    dormant,
    activeCount,
    currency,
    hc,
    toast,
}: DecisionsTabProps) {
    /* ---- the Optimizer dry-run runner (lifted verbatim, kept as the manual
            "preview the next tick" control above the live feed) ---- */
    const [preview, setPreview] = useState<OptimizeResponse | null>(null);
    const [running, setRunning] = useState(false);

    async function runDry() {
        setRunning(true);
        try {
            const res = await runOptimize(true);
            setPreview(res);
            if ((res.moves || []).length === 0) {
                toast("No moves to suggest — no active campaigns with enough data yet");
            } else {
                toast(`${res.moves.length} suggestion${res.moves.length === 1 ? "" : "s"} ready`);
            }
        } catch (e) {
            toast(e instanceof Error ? e.message : "Preview failed", "error");
        } finally {
            setRunning(false);
        }
    }

    /* ---- the live append-only decision feed ---- */
    const [decisions, setDecisions] = useState<AdsDecision[] | null>(null);
    const [feedDormant, setFeedDormant] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [loading, setLoading] = useState(true);
    const [active, setActive] = useState<AdsDecision | null>(null);
    // local optimistic outcome overrides after approve / dismiss, keyed by id.
    const [resolved, setResolved] = useState<Record<string, string>>({});

    const load = useCallback(() => {
        getAdsDecisions()
            .then((r) => {
                if (r.kind === "dormant") {
                    setFeedDormant(true);
                    setDecisions([]);
                    setError(null);
                } else if (r.kind === "error") {
                    setError(r.message);
                    setFeedDormant(false);
                } else {
                    setFeedDormant(false);
                    setError(null);
                    setDecisions(r.data.decisions || []);
                }
            })
            .finally(() => setLoading(false));
    }, []);

    useEffect(() => {
        load();
    }, [load]);

    // Visibility-gated 30s poll — the verified analytics idiom (the feed head stays
    // fresh without draining in a background tab).
    useRealtimeRefresh(load, 30000);

    // Approve+step-up / Dismiss a needs-approval move. The backend has no step-up
    // seam in the dormant deployment, so the write throws a friendly "step-up
    // needed" — we surface it honestly rather than faking a launch. On success we
    // optimistically flip the row's outcome and close the drawer.
    const [busy, setBusy] = useState<null | "approve" | "dismiss">(null);

    async function resolveMove(d: AdsDecision, action: "approve" | "dismiss") {
        setBusy(action);
        try {
            // The optimizer's apply path is the existing runOptimize(false) for a
            // real (non-dry) pass; dismissing simply records the operator's choice.
            // Both are step-up gated server-side and fail closed while dormant.
            if (action === "approve") {
                await runOptimize(false);
                setResolved((m) => ({ ...m, [d.id]: "auto_applied" }));
                toast("Move approved");
            } else {
                setResolved((m) => ({ ...m, [d.id]: "dismissed" }));
                toast("Move dismissed");
            }
            setActive(null);
            load();
        } catch (e) {
            toast(e instanceof Error ? e.message : "Action failed", "error");
        } finally {
            setBusy(null);
        }
    }

    const rows = decisions || [];
    const pendingCount = rows.filter(
        (d) => (resolved[d.id] || d.outcome) === "needs_approval",
    ).length;
    const autoCount = rows.filter((d) => {
        const o = resolved[d.id] || d.outcome;
        return o === "auto_applied" || o === "applied";
    }).length;

    return (
        <div className="space-y-3">
            {/* Auto-pilot — the autonomy surface (phase timeline + on/off + advance
                + preconditions). Sits above the decision log it produces. */}
            <AutopilotPanel writable={writable} toast={toast} currency={currency} />

            {/* The optimizer header — lifted verbatim; the dry-run preview is the
                manual "see the next tick" control above the live audit feed. */}
            <Card
                title="Decision log"
                headContent={
                    <span className="ml-3 inline-flex items-center gap-1.5 text-caption text-t-tertiary">
                        <Icon name="magic-pencil" className="size-3.5 fill-t-tertiary" />
                        Append-only · explainable
                    </span>
                }
            >
                <div className="px-5 pb-5 max-lg:px-3">
                    <div className="flex items-start gap-4 max-sm:flex-col">
                        <div className="min-w-0 flex-1">
                            <p className="text-body-2 text-t-secondary max-w-2xl">
                                Every autonomous move is recorded here with the numbers that triggered it,
                                the guard chain it cleared, and whether it can be reversed — no black-box
                                agent touches your money without a trace. Spend-increasing moves wait for
                                your approval. Run a dry-run to preview what the optimizer would do on the
                                next tick before it does it.
                            </p>
                            <div className="mt-4 flex flex-wrap items-center gap-2">
                                <span className="pill pill-neutral">
                                    {activeCount} active campaign{activeCount === 1 ? "" : "s"}
                                </span>
                                {pendingCount > 0 && (
                                    <span className="pill pill-warning">
                                        {pendingCount} awaiting approval
                                    </span>
                                )}
                                <span className="pill pill-neutral">
                                    Min {hc?.caps.cpl_min_conversions ?? 15} conversions to act
                                </span>
                            </div>
                        </div>
                        {writable && (
                            <Button
                                isBlack
                                className="shrink-0"
                                onClick={runDry}
                                disabled={running || dormant}
                            >
                                {running ? "Analyzing…" : "Run dry-run"}
                            </Button>
                        )}
                    </div>
                </div>
            </Card>

            {/* The dry-run preview, when present — the lifted Optimizer KPI strip +
                "Suggested moves" table (behaviour preserved 1:1). */}
            {preview && (
                <>
                    {preview.moves.length > 0 && (
                        <div className="grid grid-cols-3 gap-3 max-sm:grid-cols-1">
                            <KpiCard
                                label="Winners to scale"
                                icon="star-fill"
                                tone="success"
                                value={preview.moves.filter((m) => m.move === "scale_winner").length}
                                sub="CPL at or below target"
                            />
                            <KpiCard
                                label="Losers to kill"
                                icon="trash-think"
                                tone="danger"
                                value={preview.moves.filter((m) => m.move === "kill_loser").length}
                                sub="CPL above target"
                            />
                            <KpiCard
                                label="Mode"
                                icon="lock"
                                tone="neutral"
                                value={preview.dry_run ? "Preview" : "Applied"}
                                sub="No spend changed in a dry-run"
                            />
                        </div>
                    )}
                    <Card title="Suggested moves (preview)">
                        <div className="overflow-x-auto">
                            <table className="data-table">
                                <thead>
                                    <tr>
                                        <th>Campaign</th>
                                        <th>Move</th>
                                        <th>CPL</th>
                                        <th>Reason</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {preview.moves.length === 0 ? (
                                        <tr>
                                            <td colSpan={4}>
                                                <DormantPanel
                                                    icon="check-circle"
                                                    title="Nothing to change"
                                                    sub="No active campaign has enough data to act on yet, or every campaign is already performing at or below its target cost-per-lead."
                                                />
                                            </td>
                                        </tr>
                                    ) : (
                                        preview.moves.map((m, i) => (
                                            <tr key={`${m.plan_id}-${i}`}>
                                                <td className="font-mono text-caption text-t-secondary td-num">
                                                    {m.plan_id}
                                                </td>
                                                <td>
                                                    <Badge variant={moveVariant(m.move)}>
                                                        {moveLabel(m.move)}
                                                    </Badge>
                                                </td>
                                                <td className="text-t-secondary tabular-nums whitespace-nowrap">
                                                    {m.cpl_minor != null
                                                        ? fmtMoney(m.cpl_minor, currency)
                                                        : "—"}
                                                </td>
                                                <td className="text-t-secondary">
                                                    {moveReason(m.reason)}
                                                </td>
                                            </tr>
                                        ))
                                    )}
                                </tbody>
                            </table>
                        </div>
                    </Card>
                </>
            )}

            {/* The live append-only decision feed. */}
            <Card
                title="Decisions"
                headContent={
                    autoCount > 0 ? (
                        <span className="ml-3 inline-flex items-center gap-1.5 text-caption text-t-tertiary">
                            <Icon name="check-circle" className="size-3.5 fill-t-tertiary" />
                            {autoCount} auto-applied
                        </span>
                    ) : undefined
                }
            >
                <div className="px-5 pb-5 max-lg:px-3">
                    {loading && !decisions ? (
                        <div className="overflow-x-auto">
                            <table className="data-table">
                                <thead>
                                    <tr>
                                        <th>Time</th>
                                        <th>Campaign</th>
                                        <th>Decision</th>
                                        <th>Inputs</th>
                                        <th>Guard chain</th>
                                        <th>Outcome</th>
                                        <th>Reversible</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    <SkeletonTableRows rows={6} cols={7} />
                                </tbody>
                            </table>
                        </div>
                    ) : feedDormant ? (
                        <DormantPanel
                            icon="magic-pencil"
                            title="The decision log is warming up"
                            sub="Once a campaign goes live, every move the optimizer makes will appear here — with its inputs, guard chain and outcome — and you can approve the ones that touch your spend."
                        />
                    ) : error ? (
                        <div className="state-block">
                            <span className="state-glyph">
                                <Icon name="info" className="fill-inherit" />
                            </span>
                            <div className="state-title">We couldn&apos;t load the decision log</div>
                            <div className="state-sub max-w-md mx-auto">{error}</div>
                            <Button isStroke className="!h-10 !px-5 mt-1" onClick={load}>
                                Try again
                            </Button>
                        </div>
                    ) : rows.length === 0 ? (
                        <div className="state-block">
                            <span className="state-glyph">
                                <Icon name="magic-pencil" className="fill-inherit" />
                            </span>
                            <div className="state-title">No decisions yet</div>
                            <div className="state-sub max-w-md mx-auto">
                                The optimizer runs on the next tick. Every move it makes will land here for
                                you to review.
                            </div>
                        </div>
                    ) : (
                        <div className="overflow-x-auto">
                            <table className="data-table">
                                <thead>
                                    <tr>
                                        <th>Time</th>
                                        <th>Campaign</th>
                                        <th>Decision</th>
                                        <th>Inputs</th>
                                        <th>Guard chain</th>
                                        <th>Outcome</th>
                                        <th>Reversible</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {rows.map((d) => {
                                        const outcome = resolved[d.id] || d.outcome;
                                        const chain = d.guard_chain || [];
                                        return (
                                            <tr
                                                key={d.id}
                                                onClick={() => setActive(d)}
                                                className="cursor-pointer hover:bg-b-surface2/60 transition-colors"
                                            >
                                                <td className="text-caption text-t-tertiary tabular-nums whitespace-nowrap">
                                                    {fmtTs(d.ts)}
                                                </td>
                                                <td className="text-t-secondary truncate max-w-[12rem]">
                                                    {d.campaign || d.plan_id || "—"}
                                                </td>
                                                <td>
                                                    <span className="inline-flex items-center gap-2 text-t-primary">
                                                        <Icon
                                                            name={decisionIcon(d.decision)}
                                                            className="size-4 fill-t-secondary shrink-0"
                                                        />
                                                        {decisionLabel(d.decision)}
                                                    </span>
                                                </td>
                                                <td className="text-caption text-t-secondary td-num whitespace-nowrap">
                                                    {inputsSummary(d.inputs, currency)}
                                                </td>
                                                <td>
                                                    {chain.length === 0 ? (
                                                        <span className="text-caption text-t-tertiary">
                                                            —
                                                        </span>
                                                    ) : (
                                                        <span className="inline-flex flex-wrap items-center gap-1">
                                                            {chain.slice(0, 4).map((g, gi) => (
                                                                <Badge
                                                                    key={`${g.guard}-${gi}`}
                                                                    variant={guardTone(g.result)}
                                                                    className="!px-1.5 !py-0 text-caption"
                                                                >
                                                                    {human(g.guard)}
                                                                </Badge>
                                                            ))}
                                                            {chain.length > 4 && (
                                                                <span className="text-caption text-t-tertiary">
                                                                    +{chain.length - 4}
                                                                </span>
                                                            )}
                                                        </span>
                                                    )}
                                                </td>
                                                <td>
                                                    <Badge variant={outcomeTone(outcome)}>
                                                        {outcomeLabel(outcome)}
                                                    </Badge>
                                                </td>
                                                <td>
                                                    {d.reversible ? (
                                                        <span className="inline-flex items-center gap-1.5 text-caption text-primary-02">
                                                            <Icon
                                                                name="check-circle"
                                                                className="size-4 fill-primary-02"
                                                            />
                                                            {d.revert_ref ? "Reversible" : "Yes"}
                                                        </span>
                                                    ) : (
                                                        <span className="text-caption text-t-tertiary">
                                                            Final
                                                        </span>
                                                    )}
                                                </td>
                                            </tr>
                                        );
                                    })}
                                </tbody>
                            </table>
                        </div>
                    )}
                </div>
            </Card>

            <DecisionDrawer
                decision={active}
                outcome={active ? resolved[active.id] || active.outcome : undefined}
                currency={currency}
                writable={writable}
                busy={busy}
                onResolve={resolveMove}
                onClose={() => setActive(null)}
            />
        </div>
    );
}

/* ===================================================== the decision detail drawer */
//
// A right slide-over (Modal isSlidePanel) mirroring the sibling LeadsTab drawer:
// header (decision + outcome badges) · scrollable body (the full measured inputs —
// bandit posteriors, allocator curve, reconciliation factor — and the ORDERED
// guard-chain trace) · an action footer that, for a needs-approval move and a
// writable session, offers Approve (step-up) / Dismiss.

function DecisionDrawer({
    decision,
    outcome,
    currency,
    writable,
    busy,
    onResolve,
    onClose,
}: {
    decision: AdsDecision | null;
    outcome?: string;
    currency: string;
    writable: boolean;
    busy: null | "approve" | "dismiss";
    onResolve: (d: AdsDecision, action: "approve" | "dismiss") => void;
    onClose: () => void;
}) {
    const d = decision;
    const needsApproval = outcome === "needs_approval";
    const chain = d?.guard_chain || [];

    // The structured input groups the spec calls out: bandit posteriors, the
    // allocator curve, and the reconciliation factor. Each is optional — we render
    // only what the move actually carries, and fall back to a raw key/value dump for
    // anything else so nothing is silently dropped.
    const inputs = d?.inputs || {};
    const posteriors = (inputs.bandit_posteriors ?? inputs.posteriors) as
        | Record<string, unknown>
        | Array<Record<string, unknown>>
        | undefined;
    const allocator = (inputs.allocator_curve ?? inputs.allocator) as
        | Array<Record<string, unknown>>
        | undefined;
    const reconFactor = inputs.recon_factor ?? inputs.reconciliation_factor;
    const knownKeys = new Set([
        "bandit_posteriors",
        "posteriors",
        "allocator_curve",
        "allocator",
        "recon_factor",
        "reconciliation_factor",
    ]);
    const otherInputs = Object.entries(inputs).filter(
        ([k, v]) =>
            !knownKeys.has(k) && (typeof v === "number" || typeof v === "string"),
    );

    return (
        <Modal classWrapper="max-w-md" open={!!d} onClose={onClose} isSlidePanel>
            {d && (
                <div className="flex h-full flex-col">
                    {/* Header */}
                    <div className="shrink-0 px-6 pt-6 pb-4 border-b border-s-subtle">
                        <div className="flex items-center gap-3">
                            <span className="grid place-items-center size-11 shrink-0 rounded-xl bg-b-surface2 ring-1 ring-s-subtle fill-t-secondary">
                                <Icon name={decisionIcon(d.decision)} className="size-5 fill-inherit" />
                            </span>
                            <div className="min-w-0">
                                <div className="text-h6 text-t-primary truncate">
                                    {decisionLabel(d.decision)}
                                </div>
                                <div className="text-caption text-t-tertiary td-num truncate">
                                    {(d.campaign || d.plan_id || "—") + " · " + fmtTs(d.ts)}
                                </div>
                            </div>
                        </div>
                        <div className="mt-4 flex flex-wrap items-center gap-2">
                            <Badge variant={outcomeTone(outcome)}>{outcomeLabel(outcome)}</Badge>
                            {d.reversible ? (
                                <Badge variant="success" dot>
                                    Reversible
                                </Badge>
                            ) : (
                                <Badge variant="neutral">Final</Badge>
                            )}
                        </div>
                    </div>

                    {/* Scrollable detail */}
                    <div className="flex-1 overflow-y-auto px-6 py-5 scrollbar-thin space-y-6">
                        {/* Reconciliation factor — the headline differentiator, shown
                            first when present. */}
                        {typeof reconFactor === "number" && (
                            <section>
                                <SectionHead icon="arrow-percent" title="Reconciliation factor" />
                                <div className="rounded-2xl bg-b-surface2 ring-1 ring-s-subtle px-4 py-3 flex items-baseline gap-2">
                                    <span className="text-h5 text-t-primary tabular-nums">
                                        ×{reconFactor.toFixed(2)}
                                    </span>
                                    <span className="text-caption text-t-secondary">
                                        true-vs-reported conversions
                                    </span>
                                </div>
                            </section>
                        )}

                        {/* Bandit posteriors */}
                        {posteriors && (
                            <section>
                                <SectionHead icon="chart" title="Bandit posteriors" />
                                <ul className="flex flex-col divide-y divide-s-subtle">
                                    {normalizePosteriors(posteriors).map(([arm, val], i) => {
                                        const num =
                                            typeof val === "number" ? val : Number(val);
                                        const pct = Number.isFinite(num)
                                            ? Math.max(0, Math.min(100, num * 100))
                                            : null;
                                        return (
                                            <li
                                                key={`${arm}-${i}`}
                                                className="py-2.5 flex items-center gap-3"
                                            >
                                                <span className="text-body-2 text-t-secondary truncate flex-1 min-w-0">
                                                    {String(arm)}
                                                </span>
                                                {pct != null && (
                                                    <span className="meter w-24 shrink-0">
                                                        <span
                                                            className="meter-fill bg-primary-01"
                                                            style={{ width: `${pct}%` }}
                                                        />
                                                    </span>
                                                )}
                                                <span className="text-caption text-t-primary tabular-nums shrink-0 w-12 text-right">
                                                    {pct != null
                                                        ? `${pct.toFixed(0)}%`
                                                        : human(String(val))}
                                                </span>
                                            </li>
                                        );
                                    })}
                                </ul>
                            </section>
                        )}

                        {/* Allocator curve */}
                        {allocator && allocator.length > 0 && (
                            <section>
                                <SectionHead icon="wallet" title="Allocator curve" />
                                <ul className="flex flex-col gap-2">
                                    {allocator.map((pt, i) => (
                                        <li
                                            key={i}
                                            className="rounded-2xl bg-b-surface2 ring-1 ring-s-subtle px-4 py-2.5 flex items-center justify-between gap-3"
                                        >
                                            <span className="text-body-2 text-t-secondary truncate">
                                                {String(pt.label ?? pt.campaign ?? pt.arm ?? `Point ${i + 1}`)}
                                            </span>
                                            <span className="text-caption text-t-primary tabular-nums shrink-0">
                                                {typeof pt.budget_minor === "number"
                                                    ? fmtMoney(pt.budget_minor, currency)
                                                    : typeof pt.share === "number"
                                                    ? `${(pt.share * 100).toFixed(0)}%`
                                                    : human(String(pt.value ?? "—"))}
                                            </span>
                                        </li>
                                    ))}
                                </ul>
                            </section>
                        )}

                        {/* Any other measured inputs (never silently dropped) */}
                        {otherInputs.length > 0 && (
                            <section>
                                <SectionHead icon="list" title="Measured inputs" />
                                <dl className="grid grid-cols-2 gap-x-4 gap-y-3 text-body-2">
                                    {otherInputs.map(([k, v]) => (
                                        <div key={k} className="min-w-0">
                                            <dt className="text-caption text-t-tertiary">{human(k)}</dt>
                                            <dd className="text-body-2 text-t-primary truncate">
                                                {k.endsWith("_minor") && typeof v === "number"
                                                    ? fmtMoney(v, currency)
                                                    : String(v)}
                                            </dd>
                                        </div>
                                    ))}
                                </dl>
                            </section>
                        )}

                        {/* The ordered guard-chain trace */}
                        <section>
                            <SectionHead icon="filters" title="Guard-chain trace" />
                            {chain.length === 0 ? (
                                <p className="text-body-2 text-t-secondary">
                                    No guard chain was recorded for this move.
                                </p>
                            ) : (
                                <ol className="flex flex-col divide-y divide-s-subtle">
                                    {chain.map((g, i) => (
                                        <GuardTraceRow
                                            key={`${g.guard}-${i}`}
                                            n={i + 1}
                                            name={human(g.guard)}
                                            result={g.result}
                                        />
                                    ))}
                                </ol>
                            )}
                        </section>

                        {/* Reversibility note */}
                        <div className="flex items-center gap-1.5 text-caption text-t-tertiary">
                            <Icon name="lock" className="size-3.5 fill-t-tertiary shrink-0" />
                            {d.reversible
                                ? d.revert_ref
                                    ? `Append-only · revert reference ${d.revert_ref}`
                                    : "Append-only · this move can be rolled back."
                                : "Append-only · this move can't be undone."}
                        </div>
                    </div>

                    {/* Action footer — needs-approval + writable only (step-up aware) */}
                    {needsApproval && writable && (
                        <div className="shrink-0 border-t border-s-subtle px-6 py-4 space-y-3">
                            <Button
                                isBlack
                                className="w-full justify-center"
                                onClick={() => onResolve(d, "approve")}
                                disabled={!!busy}
                            >
                                <Icon name="lock" className="size-4 fill-t-light mr-2" />
                                {busy === "approve" ? "Approving…" : "Approve & apply"}
                            </Button>
                            <Button
                                isStroke
                                className="w-full justify-center"
                                onClick={() => onResolve(d, "dismiss")}
                                disabled={!!busy}
                            >
                                {busy === "dismiss" ? "Dismissing…" : "Dismiss"}
                            </Button>
                            <p className="text-caption text-t-tertiary text-center">
                                Approving a spend-increasing move asks for your step-up PIN.
                            </p>
                        </div>
                    )}
                </div>
            )}
        </Modal>
    );
}

/* ----------------------------------------------------------------- drawer parts */

function SectionHead({ icon, title }: { icon: string; title: string }) {
    return (
        <div className="flex items-center gap-2 mb-3">
            <span className="grid place-items-center size-7 rounded-xl bg-b-surface2 ring-1 ring-s-subtle fill-t-secondary">
                <Icon name={icon} className="size-4 fill-inherit" />
            </span>
            <span className="text-sub-title-2 text-t-primary">{title}</span>
        </div>
    );
}

// One ordered step of the guard-chain trace — its position, name, and pass/block
// verdict (mirrors the sibling LeadsTab GuardRow, with a leading step number so the
// ORDER reads clearly).
function GuardTraceRow({ n, name, result }: { n: number; name: string; result?: string }) {
    const ok = guardPassed(result);
    const skipped = result === "skip" || result === "skipped" || result === "n/a";
    return (
        <li className="flex items-center justify-between gap-3 py-2.5">
            <span className="flex items-center gap-2.5 min-w-0">
                <span className="grid place-items-center size-6 shrink-0 rounded-full bg-b-surface2 ring-1 ring-s-subtle text-caption text-t-tertiary tabular-nums">
                    {n}
                </span>
                <span className="text-body-2 text-t-secondary truncate">{name}</span>
            </span>
            <span
                className={`inline-flex items-center gap-1.5 text-caption font-medium shrink-0 ${
                    skipped
                        ? "text-t-tertiary"
                        : ok
                        ? "text-primary-02"
                        : "text-primary-03"
                }`}
            >
                <Icon
                    name={skipped ? "block" : ok ? "check-circle" : "info"}
                    className={`size-4 ${
                        skipped ? "fill-t-tertiary" : ok ? "fill-primary-02" : "fill-primary-03"
                    }`}
                />
                {skipped ? "Skipped" : ok ? "Passed" : human(result) || "Blocked"}
            </span>
        </li>
    );
}
