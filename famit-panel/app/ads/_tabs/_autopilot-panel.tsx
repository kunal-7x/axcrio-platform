"use client";

// Ad-Engine · AUTO-PILOT panel (Wave 2).
//
// The autonomy surface for the orchestrator: a live phase timeline
// (idle → proposing → creating_creative → moderating → viability →
// launch_pending → launched), an on/off toggle, an "Advance one step" operator
// kick, and the preconditions checklist (connected key / funded budget / brief).
//
// EARNER-SAFE: enabling here adds NO new spend authority — every launch still
// needs the global autolaunch flag + the per-tenant opt-in + the same step-up
// gate, and dry-run still means nothing spends. The panel just makes the existing
// gated pipeline visible and operable.
//
// Reuses the design system verbatim — Card / Badge / Button / Switch / state-block
// / skeleton. Zero raw hex; every colour a token. Dormant-safe: the status read
// degrades to {kind:"dormant"} and renders the honest "coming soon" state.

import { useCallback, useEffect, useMemo, useState } from "react";
import Icon from "@/components/Icon";
import Card from "@/components/Card";
import Badge from "@/components/Badge";
import Button from "@/components/Button";
import Switch from "@/components/Switch";
import Select from "@/components/Select";
import { SkeletonLines } from "@/components/Skeleton";
import {
    getAutorunStatus,
    enableAutorun,
    disableAutorun,
    advanceAutorun,
    useRealtimeRefresh,
    fmtTs,
    ADS_OBJECTIVES,
    AUTORUN_PHASES,
    type AutorunStatus,
    type AutorunPhase,
    type ReadResult,
} from "../_lib";
import type { ToastFn } from "../_shared";

// Per-phase presentation — label + glyph (all icon keys verified to exist).
const PHASE_META: Record<string, { label: string; icon: string }> = {
    idle: { label: "Idle", icon: "clock" },
    proposing: { label: "Proposing", icon: "magic-pencil" },
    creating_creative: { label: "Creative", icon: "camera" },
    moderating: { label: "Moderating", icon: "check-circle" },
    viability: { label: "Viability", icon: "chart" },
    launch_pending: { label: "Launch pending", icon: "lock" },
    launched: { label: "Launched", icon: "promote" },
};

// Friendly copy for the blocked / precondition reasons the backend returns.
const REASON_COPY: Record<string, string> = {
    no_brief: "Add a campaign brief to begin.",
    no_connected_key: "Connect a Meta or Google ad account first.",
    no_funded_budget: "Fund your ad budget or name a daily budget in the brief.",
    blocked_insufficient_funds: "Not enough budget to launch — top up to continue.",
    terminal: "This brief cycle is complete.",
};

type ObjOption = { id: number; name: string };
const OBJECTIVE_OPTIONS: ObjOption[] = ADS_OBJECTIVES.map((o, i) => ({
    id: i,
    name: o.charAt(0).toUpperCase() + o.slice(1),
}));

export type AutopilotPanelProps = {
    writable: boolean;
    toast: ToastFn;
    currency?: string;
};

export default function AutopilotPanel({ writable, toast }: AutopilotPanelProps) {
    const [res, setRes] = useState<ReadResult<AutorunStatus> | null>(null);
    const [busy, setBusy] = useState(true);
    const [acting, setActing] = useState(false);

    const load = useCallback(() => {
        setBusy(true);
        getAutorunStatus()
            .then(setRes)
            .finally(() => setBusy(false));
    }, []);

    useEffect(() => {
        load();
    }, [load]);
    useRealtimeRefresh(load, 15000);

    const status = res?.kind === "ok" ? res.data : null;
    const dormant = res?.kind === "dormant";
    const enabled = !!status?.enabled;
    const phase: AutorunPhase = status?.phase || "idle";
    const blocked = phase === "blocked";
    const done = phase === "done";
    const pre = status?.preconditions;
    const preOk = !!status?.preconditions_ok;

    // ---- brief form (only needed to turn auto-pilot ON) ----
    const [product, setProduct] = useState("");
    const [objective, setObjective] = useState<ObjOption>(OBJECTIVE_OPTIONS[0]);
    const [budgetMajor, setBudgetMajor] = useState("");
    const [autolaunch, setAutolaunch] = useState(false);

    const budgetMinor = useMemo(() => {
        const n = Number(budgetMajor.replace(/[^\d.]/g, ""));
        return Number.isFinite(n) && n > 0 ? Math.round(n * 100) : 0;
    }, [budgetMajor]);

    const turnOn = useCallback(async () => {
        if (!product.trim()) {
            toast("Tell auto-pilot what you're advertising first.", "error");
            return;
        }
        setActing(true);
        try {
            const r = await enableAutorun(
                {
                    product: product.trim(),
                    objective: objective.name.toLowerCase(),
                    budget_daily_minor: budgetMinor || undefined,
                },
                { autopilotLaunch: autolaunch },
            );
            if (r.ok) {
                toast("Auto-pilot is on. It'll work through each step on its own.", "success");
                load();
            } else {
                toast(r.error || "Couldn't turn on auto-pilot.", "error");
            }
        } catch (e) {
            toast(e instanceof Error ? e.message : "Couldn't turn on auto-pilot.", "error");
        } finally {
            setActing(false);
        }
    }, [product, objective, budgetMinor, autolaunch, toast, load]);

    const turnOff = useCallback(async () => {
        setActing(true);
        try {
            await disableAutorun();
            toast("Auto-pilot is off. Nothing will advance until you turn it back on.", "success");
            load();
        } catch (e) {
            toast(e instanceof Error ? e.message : "Couldn't turn off auto-pilot.", "error");
        } finally {
            setActing(false);
        }
    }, [toast, load]);

    const onToggle = useCallback(
        (next: boolean) => {
            if (acting) return;
            if (next) turnOn();
            else turnOff();
        },
        [acting, turnOn, turnOff],
    );

    const advance = useCallback(async () => {
        setActing(true);
        try {
            const r = await advanceAutorun();
            if (r.status) setRes({ kind: "ok", data: r.status });
            const adv = r.result?.advanced;
            const reason = r.result?.reason;
            toast(
                adv
                    ? `Advanced to ${PHASE_META[r.result?.phase || ""]?.label || r.result?.phase || "next step"}.`
                    : REASON_COPY[reason || ""] || "Nothing to advance right now.",
                adv ? "success" : "error",
            );
            load();
        } catch (e) {
            toast(e instanceof Error ? e.message : "Couldn't advance auto-pilot.", "error");
        } finally {
            setActing(false);
        }
    }, [toast, load]);

    // Current position in the linear phase track (done = past the end).
    const currentIdx = done ? AUTORUN_PHASES.length : AUTORUN_PHASES.indexOf(phase);

    const headerBadge = dormant ? (
        <Badge variant="neutral" dot>Coming soon</Badge>
    ) : blocked ? (
        <Badge variant="danger" dot>Blocked</Badge>
    ) : enabled && done ? (
        <Badge variant="success" dot>Cycle complete</Badge>
    ) : enabled ? (
        <Badge variant="success" dot>Running</Badge>
    ) : (
        <Badge variant="neutral" dot>Off</Badge>
    );

    return (
        <Card
            title="Auto-pilot"
            headContent={
                <div className="flex items-center gap-3 mr-3">
                    {headerBadge}
                    {writable && !dormant && (
                        <Switch checked={enabled} onChange={onToggle} />
                    )}
                </div>
            }
        >
            <div className="px-5 pb-5 pt-1 space-y-5 max-lg:px-3">
                {busy && !status ? (
                    <SkeletonLines lines={4} />
                ) : dormant ? (
                    <div className="state-block">
                        <span className="state-glyph">
                            <Icon name="feather" className="fill-inherit" />
                        </span>
                        <div className="state-title">Autonomous mode is coming soon</div>
                        <div className="state-sub max-w-md mx-auto">
                            Once the engine is live on the server, auto-pilot will draft, create, moderate
                            and stage campaigns on its own — every launch still waiting on your approval.
                        </div>
                    </div>
                ) : (
                    <>
                        {/* Phase timeline */}
                        <div>
                            <div className="flex items-center justify-between mb-3">
                                <span className="text-overline uppercase tracking-[0.06em] text-t-tertiary">
                                    Pipeline
                                </span>
                                {status?.dry_run && (
                                    <span className="text-caption text-t-tertiary inline-flex items-center gap-1.5">
                                        <Icon name="lock" className="size-3.5 fill-primary-01" />
                                        Dry-run · nothing spends
                                    </span>
                                )}
                            </div>
                            <ol className="flex items-start gap-0 overflow-x-auto scrollbar-none pb-1">
                                {AUTORUN_PHASES.map((p, i) => {
                                    const meta = PHASE_META[p];
                                    const isDone = i < currentIdx;
                                    const isCurrent = i === currentIdx && !done;
                                    const isBlockedHere = isCurrent && blocked;
                                    return (
                                        <li key={p} className="flex items-center shrink-0">
                                            <div className="flex flex-col items-center w-20 max-md:w-16">
                                                <span
                                                    className={`grid place-items-center size-9 rounded-full ring-1 ring-inset transition-colors ${
                                                        isBlockedHere
                                                            ? "bg-primary-03/10 ring-primary-03/40 fill-primary-03"
                                                            : isDone
                                                            ? "bg-primary-01/12 ring-primary-01/30 fill-primary-01"
                                                            : isCurrent
                                                            ? "bg-b-surface1 ring-s-highlight fill-primary-01 shadow-widget dark:bg-shade-04"
                                                            : "bg-b-surface2 ring-s-subtle fill-t-tertiary"
                                                    }`}
                                                >
                                                    <Icon
                                                        name={isDone ? "check" : meta.icon}
                                                        className="size-4 fill-inherit"
                                                    />
                                                </span>
                                                <span
                                                    className={`mt-1.5 text-caption text-center leading-tight ${
                                                        isCurrent || isDone ? "text-t-primary" : "text-t-tertiary"
                                                    }`}
                                                >
                                                    {meta.label}
                                                </span>
                                            </div>
                                            {i < AUTORUN_PHASES.length - 1 && (
                                                <span
                                                    className={`h-px w-5 max-md:w-3 -mt-5 shrink-0 ${
                                                        i < currentIdx ? "bg-primary-01/40" : "bg-s-subtle"
                                                    }`}
                                                />
                                            )}
                                        </li>
                                    );
                                })}
                            </ol>
                            {blocked && status?.blocked_reason && (
                                <div className="mt-3 flex items-start gap-2 text-caption text-t-secondary p-3 rounded-2xl bg-primary-03/8 ring-1 ring-primary-03/20 ring-inset">
                                    <Icon name="info" className="size-4 shrink-0 fill-primary-03 mt-0.5" />
                                    <span>{REASON_COPY[status.blocked_reason] || status.blocked_reason}</span>
                                </div>
                            )}
                        </div>

                        {/* Preconditions checklist */}
                        <div>
                            <span className="text-overline uppercase tracking-[0.06em] text-t-tertiary">
                                Ready to run
                            </span>
                            <div className="mt-2 grid grid-cols-3 gap-2 max-md:grid-cols-1">
                                <PreItem ok={!!pre?.connected_key} label="Ad account connected" />
                                <PreItem ok={!!pre?.funded_budget} label="Budget in place" />
                                <PreItem ok={!!pre?.has_brief} label="Campaign brief" />
                            </div>
                        </div>

                        {/* Brief form — shown only when OFF (turning on needs a brief) */}
                        {!enabled && writable && (
                            <div className="space-y-3 p-4 rounded-2xl bg-b-surface2 ring-1 ring-s-subtle ring-inset">
                                <div className="text-sub-title-2 text-t-primary">Brief for auto-pilot</div>
                                <label className="block">
                                    <span className="text-caption text-t-tertiary">What are you advertising?</span>
                                    <input
                                        value={product}
                                        onChange={(e) => setProduct(e.target.value)}
                                        placeholder="e.g. 3BHK launch in Whitefield"
                                        className="mt-1.5 w-full h-11 px-4 rounded-2xl bg-b-surface1 ring-1 ring-s-subtle ring-inset outline-none text-body-2 text-t-primary focus:ring-s-highlight dark:bg-shade-04"
                                    />
                                </label>
                                <div className="grid grid-cols-2 gap-3 max-md:grid-cols-1">
                                    <label className="block">
                                        <span className="text-caption text-t-tertiary">Goal</span>
                                        <Select
                                            className="mt-1.5"
                                            value={objective}
                                            onChange={setObjective}
                                            options={OBJECTIVE_OPTIONS}
                                        />
                                    </label>
                                    <label className="block">
                                        <span className="text-caption text-t-tertiary">Daily budget (optional)</span>
                                        <div className="mt-1.5 flex items-center h-11 px-4 rounded-2xl bg-b-surface1 ring-1 ring-s-subtle ring-inset focus-within:ring-s-highlight dark:bg-shade-04">
                                            <span className="text-t-tertiary mr-1">₹</span>
                                            <input
                                                inputMode="decimal"
                                                value={budgetMajor}
                                                onChange={(e) => setBudgetMajor(e.target.value)}
                                                placeholder="1000"
                                                className="w-full bg-transparent outline-none text-body-2 text-t-primary tabular-nums"
                                            />
                                        </div>
                                    </label>
                                </div>
                                <label className="flex items-center gap-2.5 cursor-pointer select-none pt-1">
                                    <Switch checked={autolaunch} onChange={setAutolaunch} />
                                    <span className="text-caption text-t-secondary">
                                        Let it launch automatically once a draft passes every gate
                                        <span className="text-t-tertiary"> (still dry-run-safe; respects approval)</span>
                                    </span>
                                </label>
                                <Button isBlack onClick={turnOn} disabled={acting} className="w-full">
                                    {acting ? "Turning on…" : "Turn on auto-pilot"}
                                </Button>
                            </div>
                        )}

                        {/* Running controls */}
                        {enabled && (
                            <div className="flex items-center justify-between gap-3 flex-wrap">
                                <div className="text-caption text-t-tertiary">
                                    {status?.history && status.history.length > 0
                                        ? `Last step ${fmtTs(status.history[status.history.length - 1]?.ts)}`
                                        : "No steps run yet"}
                                </div>
                                <div className="flex items-center gap-3">
                                    {writable && (
                                        <Button isStroke onClick={turnOff} disabled={acting}>
                                            Turn off
                                        </Button>
                                    )}
                                    {writable && (
                                        <Button
                                            isBlack
                                            icon="arrow"
                                            onClick={advance}
                                            disabled={acting || done || (!preOk && !blocked)}
                                        >
                                            {acting ? "Working…" : "Advance one step"}
                                        </Button>
                                    )}
                                </div>
                            </div>
                        )}
                    </>
                )}
            </div>
        </Card>
    );
}

function PreItem({ ok, label }: { ok: boolean; label: string }) {
    return (
        <div
            className={`flex items-center gap-2.5 p-3 rounded-2xl ring-1 ring-inset ${
                ok ? "bg-primary-02/8 ring-primary-02/20" : "bg-b-surface2 ring-s-subtle"
            }`}
        >
            <span
                className={`grid place-items-center size-6 shrink-0 rounded-full ${
                    ok ? "fill-primary-02" : "fill-t-tertiary"
                }`}
            >
                <Icon name={ok ? "check-circle-fill" : "info"} className="size-5 fill-inherit" />
            </span>
            <span className={`text-body-2 ${ok ? "text-t-primary" : "text-t-secondary"}`}>{label}</span>
        </div>
    );
}
