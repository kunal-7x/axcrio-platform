"use client";

// Famit Research · Call Detail — the per-call deep dive. Arousal & Friction latent traces WITH
// their ±1σ uncertainty bands, the regime strip, prosody (pitch contour + speech-rate/pause), and a
// turn-by-turn transcript timeline annotated with the state. This is the "see the call as a dynamical
// system" view the SciML pitch promised — built on a real Bayesian filter, honestly badged.

import { useMemo } from "react";
import Card from "@/components/Card";
import { useResearchCall, useResearchDashboard } from "./_lib";
import {
    AffectTrace,
    ConfidenceBadge,
    ConversionRiskCurve,
    IntentChip,
    PitchContour,
    ProsodyBars,
    RegimeChip,
    RegimeStrip,
} from "./_charts";
import { DemoPill, MethodNote, OutcomeBadge } from "./_shared";

export default function CallDetailTab({
    callId,
    minutes,
    onOpenCall,
}: {
    callId: string;
    minutes: number;
    onOpenCall: (id: string) => void;
}) {
    const { data: dash } = useResearchDashboard(minutes);
    const calls = dash?.calls || [];
    const effectiveId = callId || calls[0]?.call_id || "";
    const { data, isLoading } = useResearchCall(effectiveId || null);

    const turns = useMemo(() => data?.turns || [], [data]);
    const call = data?.call;
    const source = useMemo(() => turns[0]?.source || "asr_metadata", [turns]);
    const conf = useMemo(
        () => (turns.length ? turns.reduce((s, t) => s + (t.confidence || 0), 0) / turns.length : 0),
        [turns]
    );
    const lowConf = turns.some((t) => t.low_conf);

    return (
        <div className="space-y-5">
            {/* call picker */}
            <div className="flex flex-wrap items-center gap-2">
                <span className="mr-1 text-caption text-t-tertiary">Call</span>
                <div className="flex max-w-full gap-2 overflow-x-auto pb-1">
                    {calls.map((c) => (
                        <button
                            key={c.call_id}
                            onClick={() => onOpenCall(c.call_id)}
                            className={`shrink-0 rounded-full border px-3 py-1 font-mono text-[11px] transition-colors ${
                                c.call_id === effectiveId ? "text-t-primary" : "text-t-tertiary hover:text-t-secondary"
                            }`}
                            style={{
                                borderColor: c.call_id === effectiveId ? "var(--primary-01)" : "var(--stroke-stroke2)",
                                background: c.call_id === effectiveId ? "color-mix(in srgb, var(--primary-01) 12%, transparent)" : "transparent",
                            }}
                        >
                            {c.call_id}
                        </button>
                    ))}
                </div>
                <div className="ml-auto">
                    <DemoPill demo={data?.demo} enabled={dash?.enabled} />
                </div>
            </div>

            {/* summary chips */}
            {call && (
                <div className="flex flex-wrap items-center gap-2">
                    <Chip label="Turns" value={String(call.turns)} />
                    <Chip label="Duration" value={`${Math.round(call.duration_s)}s`} />
                    <Chip label="Peak friction" value={String(call.friction_peak)} tone="var(--primary-03)" />
                    <Chip label="Peak arousal" value={String(call.arousal_peak)} tone="var(--primary-01)" />
                    {call.conversion_risk != null && (
                        <Chip label="Conv. risk" value={`${Math.round(call.conversion_risk)}`}
                            tone={call.conversion_risk >= 60 ? "var(--primary-03)" : "var(--chart-green)"} />
                    )}
                    {(call.intervene === true || call.intervene === 1) && (
                        <span className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-medium"
                            style={{ background: "color-mix(in srgb, var(--primary-03) 18%, transparent)", color: "var(--primary-03)" }}>
                            ⚡ intervened
                        </span>
                    )}
                    <OutcomeBadge outcome={call.outcome} converted={call.converted} has_outcome={call.has_outcome} />
                    <ConfidenceBadge source={source} confidence={conf} lowConf={lowConf} />
                </div>
            )}

            {isLoading && <div className="py-16 text-center text-caption text-t-tertiary">Loading call…</div>}

            {!isLoading && (
                <>
                    {/* affect traces with uncertainty bands — the 3 multimodal axes */}
                    <div className="grid grid-cols-3 gap-5 max-lg:grid-cols-1">
                        <Card title="Emotional arousal" headContent={<TraceLegend color="var(--primary-01)" />}>
                            <div className="px-3 pb-3">
                                <AffectTrace turns={turns} kind="arousal" height={220} />
                            </div>
                        </Card>
                        <Card title="Cognitive friction" headContent={<TraceLegend color="var(--primary-03)" />}>
                            <div className="px-3 pb-3">
                                <AffectTrace turns={turns} kind="friction" height={220} />
                            </div>
                        </Card>
                        <Card title="Engagement" headContent={<TraceLegend color="var(--chart-green)" />}>
                            <div className="px-3 pb-3">
                                <AffectTrace turns={turns} kind="engagement" height={220} />
                            </div>
                        </Card>
                    </div>

                    {/* predictive: conversion-risk curve + conformal intervene marker */}
                    <Card title="Conversion risk" headContent={
                        <span className="text-[11px] text-t-tertiary">predictive · calibrated · descriptive (not causal)</span>}>
                        <div className="px-3 pb-3">
                            <ConversionRiskCurve turns={turns} />
                        </div>
                    </Card>

                    {/* regime strip */}
                    <Card title="Regime timeline">
                        <div className="space-y-3 px-5 pb-4 max-lg:px-3">
                            <RegimeStrip turns={turns} />
                            <div className="flex flex-wrap gap-2">
                                {["warming", "rising_friction", "disengaging", "resolving"].map((r) => (
                                    <RegimeChip key={r} regime={r} small />
                                ))}
                            </div>
                        </div>
                    </Card>

                    {/* prosody */}
                    <div className="grid grid-cols-3 gap-5 max-lg:grid-cols-1">
                        <Card title="Pitch contour (F0)">
                            <div className="px-3 pb-3">
                                <PitchContour turns={turns} />
                            </div>
                        </Card>
                        <Card title="Speech rate">
                            <div className="px-3 pb-3">
                                <ProsodyBars turns={turns} metric="speech_rate_sps" />
                            </div>
                        </Card>
                        <Card title="Pause ratio">
                            <div className="px-3 pb-3">
                                <ProsodyBars turns={turns} metric="pause_ratio" />
                            </div>
                        </Card>
                    </div>

                    {/* transcript timeline */}
                    <Card title="Turn-by-turn">
                        <div className="px-2 pb-2">
                            <div className="divide-y" style={{ borderColor: "var(--stroke-stroke2)" }}>
                                {turns.map((t) => (
                                    <div key={t.turn_num} className="flex items-start gap-3 px-3 py-2.5">
                                        <div className="w-8 shrink-0 pt-0.5 text-[11px] tabular-nums text-t-tertiary">#{t.turn_num}</div>
                                        <div className="min-w-0 flex-1">
                                            <div className="truncate text-caption text-t-secondary">
                                                {t.transcript || <span className="text-t-tertiary">—</span>}
                                            </div>
                                            <div className="mt-1 flex flex-wrap items-center gap-1.5">
                                                <RegimeChip regime={t.regime} small />
                                                <IntentChip intent={t.intent} small />
                                                {t.intervene && (
                                                    <span className="rounded-full px-2 py-0.5 text-[10px] font-medium"
                                                        style={{ background: "color-mix(in srgb, var(--primary-03) 18%, transparent)", color: "var(--primary-03)" }}>
                                                        intervene
                                                    </span>
                                                )}
                                            </div>
                                        </div>
                                        <Mini label="A" value={t.arousal} color="var(--primary-01)" />
                                        <Mini label="F" value={t.friction} color="var(--primary-03)" />
                                    </div>
                                ))}
                            </div>
                        </div>
                    </Card>

                    <MethodNote>
                        The shaded band on each trace is the filter&apos;s ±1σ covariance — wider where the turn was
                        short or low-confidence. F0 / loudness appear only on calls processed by the{" "}
                        <b>post-call acoustic pass</b> (pYIN over the recording); the cheap in-call signal carries
                        speech-rate and pauses only. Jitter/shimmer are intentionally <b>not headlined</b> — they are
                        unreliable on narrow-band running speech and don&apos;t predict stress.
                    </MethodNote>
                </>
            )}
        </div>
    );
}

function TraceLegend({ color }: { color: string }) {
    return (
        <span className="flex items-center gap-2 text-[11px] text-t-tertiary">
            <span className="inline-block h-0.5 w-4 rounded" style={{ background: color }} /> mean
            <span className="ml-1 inline-block h-2.5 w-3 rounded-sm" style={{ background: `color-mix(in srgb, ${color} 22%, transparent)` }} /> ±1σ
        </span>
    );
}

function Chip({ label, value, tone }: { label: string; value: string; tone?: string }) {
    return (
        <span className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px]"
            style={{ background: "var(--backgrounds-surface3)", color: "var(--text-secondary)" }}>
            <span className="text-t-tertiary">{label}</span>
            <span className="font-medium tabular-nums" style={{ color: tone || "var(--text-primary)" }}>{value}</span>
        </span>
    );
}

function Mini({ label, value, color }: { label: string; value: number; color: string }) {
    return (
        <div className="w-12 shrink-0 text-right">
            <div className="text-[10px] text-t-tertiary">{label}</div>
            <div className="text-caption tabular-nums font-medium" style={{ color }}>{Math.round(value)}</div>
        </div>
    );
}
