"use client";

// Famit Research · Outcomes Lab — the closed loop. Does the affect TRAJECTORY SHAPE correlate with
// the outcome? We show a descriptive won-vs-lost comparison (real held-out calls), then frame the
// learning loop HONESTLY: an offline reasoning model (DeepSeek-R1 / Claude via OpenRouter) DRAFTS
// playbook suggestions from the patterns; a human approves them. It NEVER auto-mutates a live prompt.

import Card from "@/components/Card";
import KpiCard from "@/components/KpiCard";
import { useResearchDashboard } from "./_lib";
import { OutcomeCorrelation } from "./_charts";
import { Citations, DemoPill, MethodNote } from "./_shared";

export default function OutcomesTab({ minutes }: { minutes: number }) {
    const { data } = useResearchDashboard(minutes);
    const won = data?.outcomes?.won;
    const lost = data?.outcomes?.lost;

    const frictionGap = lost && won ? Math.round((lost.avg_friction_peak - won.avg_friction_peak) * 10) / 10 : 0;
    const arousalGap = won && lost ? Math.round((won.avg_arousal_trend - lost.avg_arousal_trend) * 10) / 10 : 0;

    return (
        <div className="space-y-5">
            <div className="flex flex-wrap items-center gap-3">
                <div className="mr-auto">
                    <div className="text-h6 text-t-primary">Does the trajectory predict the outcome?</div>
                    <div className="text-caption text-t-tertiary">
                        Won vs lost calls, compared on the shape of their Arousal/Friction trajectories.
                    </div>
                </div>
                <DemoPill demo={data?.demo} enabled={data?.enabled} />
            </div>

            {/* headline contrasts */}
            <div className="grid grid-cols-3 gap-3 max-sm:grid-cols-1">
                <KpiCard label="Won calls" icon="check-circle" tone="success" value={won?.n ?? "—"}
                    sub={`peak friction ${won?.avg_friction_peak ?? "—"} · arousal ${trend(won?.avg_arousal_trend)}`} />
                <KpiCard label="Lost calls" icon="arrow-percent" tone="danger" value={lost?.n ?? "—"}
                    sub={`peak friction ${lost?.avg_friction_peak ?? "—"} · arousal ${trend(lost?.avg_arousal_trend)}`} />
                <KpiCard label="Friction gap" icon="arrow-up-right" tone="warning" value={`+${frictionGap}`}
                    sub="lost calls peak this much higher" />
            </div>

            <div className="grid grid-cols-2 gap-5 max-lg:grid-cols-1">
                <Card title="Won vs lost · trajectory shape">
                    <div className="px-3 pb-3">
                        {won && lost ? <OutcomeCorrelation won={won} lost={lost} /> : <Empty />}
                        <div className="mt-2 flex items-center gap-4 px-2 text-[11px] text-t-tertiary">
                            <Legend color="var(--primary-01)" label="Won" />
                            <Legend color="var(--primary-03)" label="Lost" />
                        </div>
                    </div>
                </Card>

                <Card title="What the pattern says">
                    <div className="space-y-3 px-5 pb-4 max-lg:px-3">
                        <MethodNote>
                            In this window, <b>won</b> calls warm up (arousal {trend(won?.avg_arousal_trend)}) with
                            friction <b>resolving</b> ({trend(won?.avg_friction_trend)}); <b>lost</b> calls cool down
                            (arousal {trend(lost?.avg_arousal_trend)}) with friction <b>escalating</b>{" "}
                            ({trend(lost?.avg_friction_trend)}). The separation in peak friction is{" "}
                            <b>+{frictionGap}</b> and in arousal direction <b>{arousalGap}</b> points — a real,
                            descriptive effect on held-out calls, <b>not</b> a causal claim.
                        </MethodNote>
                        <div className="text-caption leading-relaxed text-t-secondary">
                            The actionable read: when friction crosses ~60 and keeps rising on a price beat, the
                            current playbook is not handling the objection. That is the moment to intervene — with a
                            value-justification pivot, not more pace.
                        </div>
                    </div>
                </Card>
            </div>

            {/* the honest closed loop */}
            <Card title="Closed-loop learning — how it actually works">
                <div className="grid grid-cols-3 gap-4 px-5 pb-5 pt-1 max-lg:grid-cols-1 max-lg:px-3">
                    <LoopStep n={1} title="Observe" body="Every analysed call writes its per-turn Arousal/Friction trajectory + the outcome (lead status, booking, deal value) to the research store." />
                    <LoopStep n={2} title="Draft (offline)" body="A reasoning model (DeepSeek-R1 / Claude via OpenRouter) reviews the failing-trajectory patterns OFF the live path and drafts a concrete playbook tweak for the friction point." />
                    <LoopStep n={3} title="Human approves" body="A human reviews the draft and ships it as a new playbook VERSION. The live agent never self-mutates its prompt — no silent drift, full audit trail." />
                </div>
                <div className="px-5 pb-5 max-lg:px-3">
                    <DraftSuggestion />
                </div>
            </Card>

            <Citations />
        </div>
    );
}

function DraftSuggestion() {
    return (
        <div className="rounded-2xl border p-4" style={{ borderColor: "var(--stroke-stroke2)", background: "var(--backgrounds-surface3)" }}>
            <div className="mb-2 flex items-center gap-2">
                <span className="rounded-full px-2 py-0.5 text-[11px] font-medium"
                    style={{ background: "color-mix(in srgb, var(--primary-05) 45%, transparent)", color: "var(--text-secondary)" }}>
                    Draft · awaiting approval
                </span>
                <span className="text-[11px] text-t-tertiary">from 4 lost calls with rising-friction on the price beat</span>
            </div>
            <div className="text-caption leading-relaxed text-t-secondary">
                &ldquo;When acoustic friction crosses ~0.60 and keeps rising during a price mention, stop script
                progression and pivot to value-justification (localised performance + EMI framing) before re-quoting.
                Do not increase pace.&rdquo;
            </div>
            <div className="mt-3 flex gap-2">
                <button className="rounded-full px-3 py-1 text-caption text-t-tertiary" style={{ background: "var(--backgrounds-surface2)" }} disabled>
                    Approve &amp; ship (preview)
                </button>
                <button className="rounded-full px-3 py-1 text-caption text-t-tertiary" style={{ background: "var(--backgrounds-surface2)" }} disabled>
                    Dismiss
                </button>
            </div>
        </div>
    );
}

function LoopStep({ n, title, body }: { n: number; title: string; body: string }) {
    return (
        <div className="flex gap-3">
            <div className="flex size-7 shrink-0 items-center justify-center rounded-full text-caption font-medium"
                style={{ background: "color-mix(in srgb, var(--primary-01) 14%, transparent)", color: "var(--primary-01)" }}>
                {n}
            </div>
            <div>
                <div className="text-caption font-medium text-t-primary">{title}</div>
                <div className="mt-1 text-[12px] leading-relaxed text-t-tertiary">{body}</div>
            </div>
        </div>
    );
}

function Legend({ color, label }: { color: string; label: string }) {
    return (
        <span className="flex items-center gap-1.5">
            <span className="size-2.5 rounded-sm" style={{ background: color }} /> {label}
        </span>
    );
}

function Empty() {
    return <div className="py-14 text-center text-caption text-t-tertiary">Not enough outcome-labelled calls yet.</div>;
}

function trend(v?: number): string {
    if (v == null) return "—";
    const r = Math.round(v * 10) / 10;
    return r > 0 ? `+${r}` : `${r}`;
}
