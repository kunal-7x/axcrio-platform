"use client";

// Famit Research · Overview — the cockpit: hero affect KPIs, the analysed-call list (click → Call
// Detail), the regime distribution, and the honest method banner with in-product citations.

import { useRouter } from "next/navigation";
import Card from "@/components/Card";
import KpiCard from "@/components/KpiCard";
import { isConverted, useResearchDashboard, asRegimes } from "./_lib";
import { IntentChip, RegimeChip, RegimeCounts } from "./_charts";
import { Citations, DemoPill, MethodNote, OutcomeBadge, fmtTrend } from "./_shared";
import type { ResearchCallSummary } from "@/lib/api";

const RANGES = [
    { label: "24h", v: 1440 },
    { label: "7d", v: 10080 },
    { label: "30d", v: 43200 },
];

export default function OverviewTab({ minutes, onOpenCall }: { minutes: number; onOpenCall: (id: string) => void }) {
    const router = useRouter();
    const { data, isLoading } = useResearchDashboard(minutes);
    const s = data?.summary;

    const setRange = (v: number) => router.replace(`/research?range=${v}`, { scroll: false });

    return (
        <div className="space-y-5">
            {/* intro + provenance + range */}
            <div className="flex flex-wrap items-center gap-3">
                <div className="mr-auto">
                    <div className="text-h6 text-t-primary">Conversation dynamics</div>
                    <div className="text-caption text-t-tertiary">
                        Per-call Arousal &amp; Friction as a calibrated latent state — measured, not guessed.
                    </div>
                </div>
                <DemoPill demo={data?.demo} enabled={data?.enabled} />
                <div className="flex rounded-full p-0.5" style={{ background: "var(--backgrounds-surface3)" }}>
                    {RANGES.map((r) => (
                        <button
                            key={r.v}
                            onClick={() => setRange(r.v)}
                            className={`rounded-full px-3 py-1 text-caption transition-colors ${
                                minutes === r.v ? "text-t-primary" : "text-t-tertiary hover:text-t-secondary"
                            }`}
                            style={minutes === r.v ? { background: "var(--backgrounds-surface2)" } : undefined}
                        >
                            {r.label}
                        </button>
                    ))}
                </div>
            </div>

            {/* hero KPIs */}
            <div className="grid grid-cols-3 gap-3 max-lg:grid-cols-2 max-sm:grid-cols-1">
                <KpiCard label="Calls analysed" icon="chart" value={fmt(s?.calls)} sub={`${fmt(s?.turns)} turns`} />
                <KpiCard label="Avg arousal" icon="arrow-up-right" tone="info" value={fmt(s?.avg_arousal)}
                    meter={(s?.avg_arousal ?? 50) / 100} sub="0–100 · 50 = baseline" />
                <KpiCard label="Avg friction" icon="arrow-percent" tone="danger" value={fmt(s?.avg_friction)}
                    meter={(s?.avg_friction ?? 50) / 100} sub={`peak ${fmt(s?.peak_friction)}`} />
                <KpiCard label="Avg engagement" icon="heart-fill" tone="success" value={fmt(s?.avg_engagement)}
                    meter={(s?.avg_engagement ?? 50) / 100} sub="entrainment + turn-taking" />
                <KpiCard label="Avg conversion risk" icon="arrow-up-right" tone="warning" value={fmt(s?.avg_conversion_risk)}
                    meter={(s?.avg_conversion_risk ?? 0) / 100} sub={`${fmt(s?.intervened)} calls flagged to intervene`} />
                <KpiCard label="Conversion" icon="check-circle" tone="success" value={`${fmt(s?.conversion_rate)}%`}
                    sub={`${fmt(s?.converted)} of ${fmt(s?.resolved ?? s?.calls)} won`} meter={(s?.conversion_rate ?? 0) / 100} />
                <KpiCard label="Mean confidence" icon="income" tone="warning" value={`${Math.round((s?.confidence ?? 0) * 100)}%`}
                    sub="8 kHz telephony · feature reliability" meter={s?.confidence ?? 0} />
            </div>

            <div className="grid grid-cols-3 gap-5 max-lg:grid-cols-1">
                {/* analysed calls */}
                <Card title="Analysed calls" className="col-span-2 max-lg:col-span-1">
                    <div className="px-2 pb-2">
                        {isLoading && <div className="py-10 text-center text-caption text-t-tertiary">Loading…</div>}
                        {!isLoading && !data?.calls?.length && (
                            <div className="py-10 text-center text-caption text-t-tertiary">No analysed calls in range.</div>
                        )}
                        <div className="divide-y" style={{ borderColor: "var(--stroke-stroke2)" }}>
                            {(data?.calls || []).map((c) => (
                                <CallRow key={c.call_id} c={c} onOpen={() => onOpenCall(c.call_id)} />
                            ))}
                        </div>
                    </div>
                </Card>

                {/* regimes + method */}
                <div className="space-y-5">
                    <Card title="Regime events">
                        <div className="px-5 pb-4 pt-1 max-lg:px-3">
                            <RegimeCounts counts={data?.regime_counts || {}} />
                        </div>
                    </Card>
                    <Card title="Method">
                        <div className="space-y-3 px-5 pb-4 max-lg:px-3">
                            <MethodNote>
                                Affect is tracked as a smooth latent state with an online{" "}
                                <b>Bayesian (Kalman) filter</b> — measurement noise scaled by feature confidence, so
                                8 kHz telephony uncertainty shows up as honest error bands. Prosody features
                                (F0, loudness, ASR-derived speech rate, pauses) are the shippable signal; this is{" "}
                                <b>one weak modality fused with transcript signal — not ground truth.</b>
                            </MethodNote>
                            <Citations />
                        </div>
                    </Card>
                </div>
            </div>
        </div>
    );
}

function CallRow({ c, onOpen }: { c: ResearchCallSummary; onOpen: () => void }) {
    const tr = fmtTrend(c.arousal_trend);
    const fr = fmtTrend(c.friction_trend);
    const regimes = asRegimes(c.regimes);
    return (
        <button onClick={onOpen}
            className="flex w-full items-center gap-3 px-3 py-3 text-left transition-colors hover:bg-[var(--backgrounds-surface3)]">
            <div className="min-w-0 flex-1">
                <div className="truncate font-mono text-caption text-t-primary">{c.call_id}</div>
                <div className="mt-1 flex flex-wrap items-center gap-1.5">
                    {c.top_intent && <IntentChip intent={c.top_intent} small />}
                    {regimes.slice(0, 2).map((r, i) => <RegimeChip key={i} regime={r} small />)}
                    {(c.intervene === true || c.intervene === 1) && (
                        <span className="rounded-full px-2 py-0.5 text-[10px] font-medium"
                            style={{ background: "color-mix(in srgb, var(--primary-03) 18%, transparent)", color: "var(--primary-03)" }}>⚡ intervene</span>
                    )}
                    {!regimes.length && !c.top_intent && <span className="text-[11px] text-t-tertiary">steady throughout</span>}
                </div>
            </div>
            <div className="hidden w-24 text-right sm:block">
                <div className="text-caption tabular-nums text-t-secondary">{c.turns} turns</div>
                <div className="text-[11px] tabular-nums text-t-tertiary">{Math.round(c.duration_s)}s</div>
            </div>
            <div className="hidden w-24 text-right md:block">
                <div className="text-[11px] text-t-tertiary">arousal</div>
                <div className="text-caption tabular-nums" style={{ color: tr.color }}>{tr.text}</div>
            </div>
            <div className="hidden w-24 text-right md:block">
                <div className="text-[11px] text-t-tertiary">friction</div>
                <div className="text-caption tabular-nums" style={{ color: fr.color }}>{fr.text}</div>
            </div>
            <div className="w-20 text-right">
                <OutcomeBadge outcome={c.outcome} converted={c.converted} has_outcome={c.has_outcome} />
                {isConverted(c) && c.deal_value > 0 && (
                    <div className="mt-1 text-[11px] tabular-nums text-t-tertiary">₹{(c.deal_value / 1000).toFixed(0)}k</div>
                )}
            </div>
        </button>
    );
}

function fmt(v: number | undefined): string {
    if (v == null) return "—";
    return Number.isInteger(v) ? v.toLocaleString() : v.toLocaleString(undefined, { maximumFractionDigits: 1 });
}
