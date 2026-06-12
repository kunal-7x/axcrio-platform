"use client";

// LIVE CALLS MONITOR — /ai-manager/live.
//
// Renders the in-progress state of active calls from GET /ai-manager/live, with
// the HUMAN-ESCALATION (handoff) progression front and centre: as the AI rings the
// handoff team in priority order, the backend emits "Dialing #1" → "Dialing #2" →
// "Bridged" (or "Failed → callback + WhatsApp"). We turn that into a live stepper.
//
// Polls every 3s while mounted. Dormant (router not mounted / 404) → a calm "no
// live calls" state, never an error wall. Read-only safe (pure read surface).
// Premium reference-kit (Card / Badge / Icon), Inter Display, zero raw hex.
// Touches no app-wide component, no globals.css.

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Layout from "@/components/Layout";
import Card from "@/components/Card";
import Icon from "@/components/Icon";
import Badge from "@/components/Badge";
import { DormantPanel, ErrorBanner } from "../_shared";
import {
    getAimLive,
    aimLiveCalls,
    liveCallRoom,
    liveCallCaller,
    handoffPhase,
    handoffAttemptNo,
    type AimLiveCall,
    type AimLivePayload,
    type AimHandoffPhase,
    type ReadResult,
} from "../_lib";

const POLL_MS = 3000;

/* ----------------------------------------------------------------- helpers */

function phaseBadge(phase: AimHandoffPhase): React.ReactNode {
    switch (phase) {
        case "bridged":
            return (
                <Badge variant="success" dot>
                    Bridged
                </Badge>
            );
        case "failed":
            return <Badge variant="danger">Callback + WhatsApp</Badge>;
        case "dialing":
            return (
                <Badge variant="warning" dot>
                    Ringing team
                </Badge>
            );
        default:
            return (
                <Badge variant="info" dot>
                    In progress
                </Badge>
            );
    }
}

// Build the ordered step trail for one call. Prefer an explicit per-attempt trail
// (handoff_attempts) when the backend supplies it; otherwise synthesize from the
// "Dialing #N" label + the current target so "#1 … #N" always renders.
type Step = { idx: number; number: string; state: "done" | "active" | "pending" | "bridged" | "failed" };

function buildSteps(c: AimLiveCall): Step[] {
    const phase = handoffPhase(c.handoff);
    const attempts = Array.isArray(c.handoff_attempts) ? c.handoff_attempts : [];

    if (attempts.length > 0) {
        return attempts.map((a, i) => {
            const num = a.number || a.phone || "+91…";
            const last = i === attempts.length - 1;
            const oc = (a.outcome || "").toLowerCase();
            let state: Step["state"] = "done";
            if (last && phase === "bridged") state = "bridged";
            else if (last && phase === "failed") state = "failed";
            else if (last && phase === "dialing") state = "active";
            else if (/answer|bridg/.test(oc)) state = "bridged";
            else state = "done";
            return { idx: a.attempt || i + 1, number: num, state };
        });
    }

    // No trail — synthesize from the label. "Dialing #N" → steps 1..N where N is
    // active (or bridged/failed at the terminal phase). Earlier steps are "done".
    const n = handoffAttemptNo(c.handoff) ?? (phase === "idle" ? 0 : 1);
    if (n <= 0) return [];
    const steps: Step[] = [];
    for (let i = 1; i <= n; i++) {
        const last = i === n;
        const isTarget = last && !!c.handoff_target;
        let state: Step["state"] = "done";
        if (last) {
            if (phase === "bridged") state = "bridged";
            else if (phase === "failed") state = "failed";
            else state = "active";
        }
        steps.push({ idx: i, number: isTarget ? c.handoff_target! : "+91…", state });
    }
    return steps;
}

const STEP_TONE: Record<Step["state"], string> = {
    done: "bg-b-surface1 ring-s-subtle text-t-tertiary dark:bg-shade-04/50",
    active: "bg-primary-05/12 ring-primary-05/30 text-primary-05",
    bridged: "bg-primary-02/12 ring-primary-02/30 text-primary-02",
    failed: "bg-primary-03/10 ring-primary-03/25 text-primary-03",
    pending: "bg-b-surface1 ring-s-subtle text-t-tertiary dark:bg-shade-04/50",
};

const STEP_GLYPH: Record<Step["state"], string> = {
    done: "check",
    active: "mobile",
    bridged: "check-circle-fill",
    failed: "block",
    pending: "clock",
};

/* ============================================================ the live row */

function LiveCallRow({ c }: { c: AimLiveCall }) {
    const phase = handoffPhase(c.handoff);
    const steps = buildSteps(c);
    const caller = liveCallCaller(c) || "Unknown caller";
    const campaign = c.campaign_name || c.campaign;
    const hasHandoff = steps.length > 0 || phase !== "idle";

    return (
        <li className="rounded-2xl bg-b-surface2 ring-1 ring-s-subtle ring-inset p-4 max-lg:p-3 rise-in">
            <div className="flex items-center gap-3 flex-wrap">
                <span className="grid place-items-center size-10 shrink-0 rounded-xl bg-b-surface1 ring-1 ring-s-subtle fill-t-secondary dark:bg-shade-04/50">
                    <Icon name="mobile" className="size-5 fill-inherit" />
                </span>
                <div className="min-w-0 flex-1">
                    <div className="text-body-2 text-t-primary font-medium td-num truncate">{caller}</div>
                    <div className="text-caption text-t-tertiary truncate">
                        {campaign ? campaign : liveCallRoom(c) || "Live call"}
                    </div>
                </div>
                {hasHandoff ? phaseBadge(phase) : <Badge variant="info" dot>Live</Badge>}
            </div>

            {/* handoff progression stepper */}
            {hasHandoff && (
                <div className="mt-3 pt-3 border-t border-s-subtle">
                    <div className="text-caption text-t-tertiary mb-2.5">
                        {phase === "bridged"
                            ? "A human answered and was bridged into the call."
                            : phase === "failed"
                            ? "No one answered — the hot lead was sent to WhatsApp and a callback was logged."
                            : "Ringing the handoff team in priority order…"}
                    </div>
                    <div className="flex items-center gap-2 flex-wrap">
                        {steps.map((s, i) => (
                            <div key={i} className="flex items-center gap-2">
                                <span
                                    className={`inline-flex items-center gap-1.5 h-8 pl-2 pr-3 rounded-full ring-1 ring-inset text-caption ${STEP_TONE[s.state]}`}
                                >
                                    <span className="grid place-items-center size-5 rounded-full bg-current/15">
                                        <Icon name={STEP_GLYPH[s.state]} className="size-3 fill-current" />
                                    </span>
                                    <span className="font-medium">#{s.idx}</span>
                                    <span className="td-num opacity-80">{s.number}</span>
                                </span>
                                {i < steps.length - 1 && (
                                    <Icon name="arrow" className="size-3.5 fill-t-tertiary shrink-0" />
                                )}
                            </div>
                        ))}
                        {phase === "bridged" && (
                            <>
                                <Icon name="arrow" className="size-3.5 fill-t-tertiary shrink-0" />
                                <span className="inline-flex items-center gap-1.5 h-8 px-3 rounded-full ring-1 ring-inset ring-primary-02/30 bg-primary-02/12 text-primary-02 text-caption font-medium">
                                    <Icon name="check-circle-fill" className="size-3.5 fill-current" />
                                    Bridged
                                </span>
                            </>
                        )}
                        {phase === "failed" && (
                            <>
                                <Icon name="arrow" className="size-3.5 fill-t-tertiary shrink-0" />
                                <span className="inline-flex items-center gap-1.5 h-8 px-3 rounded-full ring-1 ring-inset ring-primary-03/25 bg-primary-03/10 text-primary-03 text-caption font-medium">
                                    <Icon name="chat" className="size-3.5 fill-current" />
                                    WhatsApp + callback
                                </span>
                            </>
                        )}
                    </div>
                </div>
            )}
        </li>
    );
}

/* ============================================================== the page */

export default function LiveCallsPage() {
    const [res, setRes] = useState<ReadResult<AimLivePayload> | null>(null);
    const [firstLoad, setFirstLoad] = useState(true);
    const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

    const load = useCallback(async () => {
        const r = await getAimLive();
        setRes(r);
        setFirstLoad(false);
    }, []);

    useEffect(() => {
        load();
        pollRef.current = setInterval(load, POLL_MS);
        return () => {
            if (pollRef.current) clearInterval(pollRef.current);
        };
    }, [load]);

    const calls = useMemo(() => (res?.kind === "ok" ? aimLiveCalls(res.data) : []), [res]);
    const dormant = res?.kind === "dormant";
    const err = res?.kind === "error" ? res.message : "";

    return (
        <Layout title="Live Calls">
            <ErrorBanner msg={err} />

            <div className="max-w-3xl">
                <Card
                    title="Live calls"
                    headContent={
                        <div className="ml-auto flex items-center gap-2">
                            {!dormant && (
                                <span className="inline-flex items-center gap-1.5 text-caption text-t-tertiary">
                                    <span className="relative flex size-2">
                                        <span className="absolute inline-flex h-full w-full rounded-full bg-primary-02 opacity-60 animate-ping" />
                                        <span className="relative inline-flex size-2 rounded-full bg-primary-02" />
                                    </span>
                                    Live · refreshes every 3s
                                </span>
                            )}
                        </div>
                    }
                >
                    <div className="px-5 max-lg:px-3 pb-3">
                        <p className="text-body-2 text-t-secondary">
                            When a caller asks for a human or a lead is hot, the AI rings your{" "}
                            <span className="text-t-primary">handoff team</span> in order — the
                            first available is bridged live; if none answer, the hot lead goes to
                            their WhatsApp. Each transfer&apos;s progress shows below as it happens.
                        </p>
                    </div>

                    {firstLoad && !res ? (
                        <div className="px-5 max-lg:px-3 pb-5 space-y-2">
                            {[...Array(2)].map((_, i) => (
                                <div key={i} className="skeleton h-24 w-full rounded-2xl" />
                            ))}
                        </div>
                    ) : dormant || calls.length === 0 ? (
                        <div className="px-5 max-lg:px-3 pb-4">
                            <DormantPanel
                                icon="mobile"
                                title={dormant ? "Live monitor lights up once the line is live" : "No active calls right now"}
                                sub={
                                    dormant
                                        ? "When the AI Manager line is provisioned, every in-progress call — and each warm transfer to your handoff team — appears here in real time."
                                        : "When a call is in progress you'll see it here, including the live Dialing #1 → #2 → Bridged handoff progression."
                                }
                            />
                        </div>
                    ) : (
                        <ul className="px-3 max-lg:px-2 pb-4 space-y-2.5">
                            {calls.map((c, i) => (
                                <LiveCallRow key={liveCallRoom(c) || i} c={c} />
                            ))}
                        </ul>
                    )}
                </Card>
            </div>
        </Layout>
    );
}
